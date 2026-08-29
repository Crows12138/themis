"""Deterministic whole-analysis report assembler.

Turns one already-computed Themis result into a single human-readable
Markdown document — the deterministic counterpart to the LLM-facing
``response_rendering.md`` bridge. It is a *passive assembler* (per
``themis/output``): it reads only fields the runtime already put on the
result / program and NEVER re-runs reasoning or calls ``verify``.

What it foregrounds — and what makes it *Themis's* report rather than a
generic causal-analysis summary — follows the order
``response_rendering.md`` mandates: the **answer first**, then how it was
arrived at, then the two things Causal-Copilot-style tools omit — an
honest **verification** status (which independent re-checks recompute this
answer, per :mod:`themis.audits`) and the **assumptions + data gaps** (what
must hold, and what data would strengthen or unblock the answer).

    from themis.output.analysis_report import build_analysis_report
    md = build_analysis_report(result, program=program)

``result`` is one entry from ``themis.run(...)["results"]`` /
``themis.estimate(...)["results"]``. ``program`` (the kernel_ast dict) is
optional but lets the report render the causal model and edge provenance.
``audited`` is an optional caller-supplied ``themis.audit(program, result)``
return — the assembler never runs a re-check itself.
"""
from __future__ import annotations

from typing import Callable, NamedTuple, Protocol, assert_never

from .. import answers, audits, blocks, questions, refusals, risk_provenance
# Aliased because the ledger renderer's own argument is the ledger itself,
# and a module shadowed by a local reads as the local everywhere below it.
from .. import ledger as ledger_vocab
from ..refusals import Kind
from . import derivation_glossary, envelope_glossary, formula_text
from .. import gaps
from .. import intervals
from .. import language


#: How the report frames a refusal's three parts around the occasion.
#:
#: The decoration is this surface's: markdown emphasis, a dash the browser
#: does not draw, and the colon that introduces what happened this time.
#: What the parts SAY is shared with the browser, which frames them its own
#: way — so the frame lives here and the parts live below.
_KIND_FRAME: language.Words = {
    "zh": "**{lead} —— {head}**：",
    "en": "**{lead} — {head}**: ",
}


def _kind_parts(kind) -> tuple[language.Words, ...] | None:
    """What each kind of refusal says, as lead, head and tail.

    The registry owns which kinds exist and which species falls under
    each; this owns the words, the way ``assumption_glossary`` owns the
    words for an assumption id.

    A ``match`` rather than a table keyed by kind, because what has to be
    guaranteed is that the reader's half of the taxonomy is complete, and
    that is a claim about branches. ``assert_never`` makes a sixth kind a
    type error in this file; a table could only be compared against the
    registry by a test, after the fact. Both are still here — the test
    below asks the other question, whether each branch actually says
    something, which no checker can see.

    Three parts rather than one sentence, and the browser has been three
    all along (``REFUSAL_KIND_WORDS``). One sentence here meant the join
    between the occasion and the tail had no author, so it fell to whatever
    ``reason`` happened to end with: five English templates read
    ``...here.This decides nothing...``, and Chinese — needing no gap —
    read correctly, which is why nobody saw it. The gap is the language's
    (:data:`themis.language.BETWEEN_SENTENCES`) and the parts are the
    kind's; neither is the template's to remember.

    The argument is whatever the envelope carried and not a :class:`Kind`,
    for the reason the registry reads wider than it writes: an envelope
    from another kernel may name a kind this one has never heard of, and
    that one gets no sentence rather than the wrong one.
    """
    known = refusals.KIND_BY_NAME.get(str(kind))
    if known is None:
        return None
    match known:
        case Kind.GRAPH:
            return (
                {"zh": "没有给出数值", "en": "No number"},
                {"zh": "这是关于因果图的结论",
                 "en": "this is a conclusion about the causal graph"},
                {"zh": "再多同样的数据也不会改变它；要改变的是图或问题本身。",
                 "en": "More of the same data will not change it; what would "
                       "is the graph, or the question."},
            )
        case Kind.DATA:
            return (
                {"zh": "没有给出数值", "en": "No number"},
                {"zh": "这批数据支撑不住",
                 "en": "these data cannot support one"},
                {"zh": "结构上是可识别的，缺的是数据本身能提供的支持。",
                 "en": "It is identifiable structurally; what is missing is "
                       "the support the data themselves would have to "
                       "provide."},
            )
        case Kind.UNBUILT:
            return (
                {"zh": "没有给出数值", "en": "No number"},
                {"zh": "Themis 还没有建这个情形",
                 "en": "Themis has not built this case"},
                {"zh": "问题成立、也已被识别，这是工具的边界，不是问题或数据的毛病。",
                 "en": "The question is well posed and has been identified; "
                       "this is the tool's boundary, not a fault in the "
                       "question or the data."},
            )
        case Kind.REQUEST:
            return (
                {"zh": "没有给出数值", "en": "No number"},
                {"zh": "需要你改一处输入",
                 "en": "one of your inputs has to change"},
                {"zh": "改掉之后重跑即可。", "en": "Change it and run again."},
            )
        case Kind.BACKEND:
            return (
                {"zh": "没有算出数值", "en": "No number was produced"},
                {"zh": "数值例程没有返回结果",
                 "en": "the numeric routine returned nothing"},
                {"zh": "这没有对问题或数据设计做出任何判定。",
                 "en": "This decides nothing about the question or about the "
                       "data design."},
            )
    assert_never(known)


#: The occasion's own way out, after the kind has said what kind of dead end
#: this is. Two sentences rather than one clause, because they answer at
#: different grains and a reader acting on the second should not have to
#: find it inside the first.
_ON_THIS_OCCASION: language.Words = {
    "zh": "这一次能走的路：{routes}。",
    "en": "On this occasion: {routes}.",
}


def _routes_said(failure: dict, *, lang: language.Lang | str) -> str:
    """The routes past THIS refusal, or nothing if it offered none.

    A route this build has never heard of is dropped rather than printed,
    for the reason :func:`_kind_words` gives about kinds: an envelope may
    come from another kernel, and the honest answer to a token we cannot
    read is to say nothing rather than to say it in a language nobody
    reads. The producer's side of that is loud — :func:`themis.refusals.route`
    raises — because there the token is being written, not read.
    """
    said = []
    for row in failure.get("remedies") or ():
        if not isinstance(row, dict):
            continue
        try:
            said.append(refusals.route(row.get("remedy"), row.get("subject"),
                                       lang))
        except (ValueError, KeyError):
            continue
    if not said:
        return ""
    return language.fill(
        _ON_THIS_OCCASION, lang,
        routes=language.fill(language.BETWEEN_STATEMENTS, lang).join(said))


def _kind_words(kind) -> language.Words | None:
    """The framed sentence, still holding ``{reason}`` for the occasion.

    Assembled rather than written, so that the gap between the occasion and
    the tail comes from the language every time instead of from whoever
    typed the template.
    """
    parts = _kind_parts(kind)
    if parts is None:
        return None
    lead, head, tail = parts
    return {
        lang: language.fill(_KIND_FRAME, lang,
                            lead=language.fill(lead, lang),
                            head=language.fill(head, lang))
        + language.sentences("{reason}", language.fill(tail, lang), lang=lang)
        for lang in sorted(language.written())
    }

def _kind_word(kind, lang: language.Lang | str = language.DEFAULT
               ) -> str | None:
    """The template above, in one language.

    Split from the match so that every gloss the registry names answers
    the same shape — ``(value, lang) -> str`` — and the registry can ask
    each of them once per language this build declares."""
    words = _kind_words(kind)
    return None if words is None else language.say(words, lang, unknown="")


# The badge the report leads with. Seven, because the vocabulary is seven:
# the two counterfactual statuses were absent and fell to
# ``_STATUS_BADGE.get(status, status)``, so a solved counterfactual was
# headed by the identifier while the browser's table said the words.
_STATUS_BADGE = {
    "structurally_solved": {"zh": "✅ 已解决（结构层）", "en": "✅ solved (structural)"},
    "numerically_solved": {"zh": "📊 已估计（数值层）", "en": "📊 estimated (numeric)"},
    "needs_investigation": {"zh": "⚠️ 需补充数据 / 假设",
                            "en": "⚠️ needs more data / an assumption"},
    "needs_assumption": {"zh": "⚠️ 需补充假设", "en": "⚠️ needs an assumption"},
    "outside_language": {"zh": "✋ 超出可表达范围",
                         "en": "✋ outside what can be expressed"},
    "counterfactual_solved": {"zh": "✅ 反事实已解", "en": "✅ counterfactual solved"},
    "counterfactual_bounded": {"zh": "📐 反事实（区间）",
                               "en": "📐 counterfactual (interval)"},
}

# How much a MISSING INPUT blocks an answer. The ledger's severities are a
# different vocabulary answering a different question — how the conclusion
# dies if an assumption is false — and they live with the other two fields
# of a ledger line, in :mod:`themis.ledger`. One dict held both, which is
# not wrong to read but says severity is one vocabulary when it is two; the
# browser copied that reading and took three of the six.
_GAP_SEVERITY_WORDS = {
    "blocking": {"zh": "阻断", "en": "blocking"},
    "important": {"zh": "重要", "en": "important"},
    "informational": {"zh": "提示", "en": "for information"},
}

_TIER_WORDS = {
    "point": {"zh": "点估计", "en": "a point estimate"},
    "interval": {"zh": "区间", "en": "an interval"},
    "none": {"zh": "暂无数值答案", "en": "no number yet"},
}

# What a bounds interval brackets, in the reader's language. Pinned against
# the schema's own enums by tests: an interval reaches this surface as two
# numbers, and two numbers about the wrong quantity read exactly like two
# numbers about the right one.
_BOUNDS_ESTIMAND_WORDS = {
    "arm_probability": {"zh": "干预到所问的那一档之后，目标事件发生的概率",
                        "en": "the probability of the target event after "
                              "intervening to the arm you asked about"},
}
_BOUNDS_CONTRAST_WORDS = {
    "ace": {"zh": "平均因果效应（ACE）", "en": "the average causal effect (ACE)"},
}


def _bounds_interval(b: dict) -> str:
    return f"[{_fmt(b['lower_value'])}, {_fmt(b['upper_value'])}]"


_RESTS_ON: language.Words = {
    "zh": "假设 {assumptions}", "en": "assuming {assumptions}"}
_RESTS_ON_NOTHING: language.Words = {
    "zh": "无假设", "en": "assumption-free"}


def _bounds_rests_on(b: dict, *, lang: language.Lang | str) -> str:
    """What one bounds row assumes, for a reader choosing between rows.

    An interval is unreadable beside another one until this is said: the
    two bracket the same quantity and differ only in what they were
    allowed to assume.
    """
    assumptions = b.get("assumptions") or ()
    if not assumptions:
        return language.fill(_RESTS_ON_NOTHING, lang)
    return language.fill(_RESTS_ON, lang, assumptions=", ".join(assumptions))


def _fmt(x) -> str:
    """Compact numeric formatting (mirrors explainer's ``.4g``)."""
    try:
        return f"{float(x):.4g}"
    except (TypeError, ValueError):
        return str(x)


_TITLE: language.Words = {
    "zh": "# 因果分析报告", "en": "# Causal analysis report"}
_STATUS_LINE: language.Words = {
    "zh": "**状态**：{badge}", "en": "**Status**: {badge}"}
_SECTION_QUESTION: language.Words = {"zh": "问题", "en": "The question"}
_SECTION_ANSWER: language.Words = {"zh": "答案", "en": "The answer"}
_SECTION_ROUTE: language.Words = {
    "zh": "怎么算出来的", "en": "How it was arrived at"}
_SECTION_MODEL: language.Words = {"zh": "因果模型", "en": "The causal model"}
_SECTION_VERIFICATION: language.Words = {"zh": "验证", "en": "Verification"}
_SECTION_ASSUMPTIONS: language.Words = {"zh": "假设", "en": "Assumptions"}
_SECTION_GAPS: language.Words = {
    "zh": "数据缺口与下一步", "en": "Data gaps, and what to do next"}


def build_analysis_report(
    result: dict,
    *,
    program: dict | None = None,
    audited: list[dict] | None = None,
    lang: language.Lang | str = language.DEFAULT,
) -> str:
    """Assemble a Markdown analysis report from one result envelope.

    Pure presentation over already-computed fields — no reasoning is
    re-run and no audit is called. ``audited`` may carry what a separate
    ``themis.audit(program, result)`` returned so the report can stamp
    each re-check ✓ / ✗; left ``None`` the report lists which re-checks
    apply without claiming any of them ran.

    It takes the audit rows rather than one boolean because "was this
    verified" is not one question: thirteen entry points re-derive
    different things, and which of them apply is a fact about the
    envelope that :mod:`themis.audits` already answers. A boolean could
    only carry ``verify``'s verdict, which is absent on every envelope
    whose answer came from a recovery estimator or from partial
    identification.

    ``lang`` has its default HERE and nowhere below. This is the entry
    point, which is where a caller not saying which language actually
    happens; a default on each of the renderers underneath would be one
    silent exit apiece for the reader's language to be dropped through.
    """
    status = result.get("status", "?")
    badge = language.gloss(_STATUS_BADGE, status, lang)

    parts: list[str] = [
        language.fill(_TITLE, lang), "",
        language.fill(_STATUS_LINE, lang, badge=badge), "",
    ]

    parts += _section(language.fill(_SECTION_QUESTION, lang),
                      _render_question(result, program, lang=lang))
    answer = _render_answer(result, lang=lang)
    parts += _section(
        language.fill(_SECTION_ANSWER, lang),
        answer + _refusal_beside_the_answer(result, answer, lang=lang))
    route = _render_route(result, lang=lang)
    if route:
        parts += _section(language.fill(_SECTION_ROUTE, lang), route)
    if program is not None:
        parts += _section(language.fill(_SECTION_MODEL, lang),
                          _render_model(program, lang=lang))
    parts += _section(language.fill(_SECTION_VERIFICATION, lang),
                      _render_verification(result, audited, lang=lang))
    assumptions = _render_assumptions(result, lang=lang)
    if assumptions:
        parts += _section(language.fill(_SECTION_ASSUMPTIONS, lang),
                          assumptions)
    gaps = _render_gaps(result, lang=lang)
    if gaps:
        parts += _section(language.fill(_SECTION_GAPS, lang), gaps)

    footer = _render_footer(result, lang=lang)
    if footer:
        parts += ["---", "", footer, ""]

    return "\n".join(parts).rstrip() + "\n"


def _section(title: str, body: str) -> list[str]:
    return [f"## {title}", "", body, ""]


# The second place the occasion sits between two fixed halves, and it read
# correctly only because ``_FULL_STOP`` happened to carry a trailing space in
# English. Split for the same reason ``_kind_parts`` is: the gap belongs to
# the language, and a template that holds it is a template free to forget it.
_ALSO_REFUSED_HEAD: language.Words = {
    "zh": "\n\n> **另有一项没能给出**（上面这个数不受影响）：",
    "en": "\n\n> **Something else could not be produced** (the number above "
          "is unaffected): ",
}
_ALSO_REFUSED_TAIL: language.Words = {
    "zh": "（来自 `{estimator}`，拒答类型 `{species}`）",
    "en": "(from `{estimator}`, refusal type `{species}`)",
}


def _refusal_beside_the_answer(result: dict, answer: str, *,
                               lang: language.Lang | str) -> str:
    """A refusal that coexists with an answer is a note under it.

    ``estimator_failure`` carries two different things: why there is no
    number, and why something SUPPLEMENTARY to the number was not produced —
    a correction the caller asked for, a precision cost on a design this
    package has no split for. The answer renderer reads the first, and
    reaches the field only once nothing above it has fired, so the second was
    reaching no reader at all: a caller who declared what they knew about
    their outcome got the right number and not one word about the assessment
    they had asked for.

    Keyed on the rendered answer rather than on a second field. What decides
    this is whether the refusal has already been said, and the text is the
    only thing that knows — a flag would be a second record of it, free to
    disagree.
    """
    failure = result.get("estimator_failure")
    if not isinstance(failure, dict):
        return ""
    species = failure.get("failure_type")
    if not species or str(species) in answer:
        return ""
    return language.fill(_ALSO_REFUSED_HEAD, lang) + language.sentences(
        _sentence(refusals.said(failure, lang), lang=lang),
        language.fill(_ALSO_REFUSED_TAIL, lang,
                      estimator=failure.get("estimator", "?"),
                      species=species),
        lang=lang)




def _sentence(reason: str | None, *, lang: language.Lang | str) -> str:
    """A refusal's sentence, ended so it can sit inside a longer one.

    The sentence itself is :func:`themis.refusals.said`, assembled here
    because here is where the reader's language is known — it was written
    at the moment of refusing until #411, and this function's whole job
    used to be not running the next clause into somebody else's prose.
    That job stays: where the sentence ends is the sentence's business and
    where the next one begins is this template's, and two callers were
    trimming and re-punctuating identically.
    """
    text = (reason or "").strip().rstrip(".")
    if text and text[-1] not in "。！？!?":
        text += language.fill(language.FULL_STOP, lang)
    return text


# --- question -----------------------------------------------------------------
#
# One renderer per kind of question, bound to :mod:`themis.questions`. Four
# kinds had a branch here and six echoed their enum token back at the
# reader; of the four, ``assoc`` tested for ``"association"`` — a string no
# query kind has — so it never fired, and underneath that it read ``from``
# / ``to``, which are the *cause* query's fields. A branch that cannot fire
# cannot be wrong out loud, which is how the second bug kept.
#
# Each renderer takes the query dict or ``None`` (the report is often built
# without the program) and reads only fields ``$defs.query.oneOf`` declares
# for its kind; a test builds one query per kind from that same schema and
# holds the line to naming what it was asked about.


def _find_query(program: dict | None, query_id: str | None = None) -> dict | None:
    """The query THIS result answers.

    Keyed on ``query_id`` — required on every query statement — rather
    than "the first query statement in the program". A program may carry
    several; the report is built per result. With one query the two agree,
    which is every fixture in the suite, so an ``assoc`` result rendered
    the ``cause`` query's question line and asked "x 是否因果影响 y" about
    a question that was never asked.

    No match means the question is not in the program that was handed in.
    Returning ``None`` puts the kind's own prose in the line; returning
    some other query's atoms is how this was wrong in the first place.
    """
    if not program:
        return None
    queries = [s for s in program.get("statements", [])
               if s.get("kind") == "query"]
    if query_id is None:
        return queries[0].get("query") if queries else None
    for stmt in queries:
        if stmt.get("id") == query_id:
            return stmt.get("query")
    return None


def _atom_pred(atom_dict: dict | None) -> str:
    # The ``or {}`` was always here; the signature is what did not say so.
    return (atom_dict or {}).get("predicate", "?")


def _atom_preds(atoms, lang: language.Lang | str) -> str:
    """Several atoms of one role, joined in this reader's punctuation.

    A role that holds a set needs this and a role that holds one does not,
    which is why it is a second function rather than a widened one: the
    single case would otherwise pay a list join to say one name.
    """
    return language.listing([_atom_pred(a) for a in atoms or ()], lang) or "?"


def _valued(a: dict) -> str:
    atom = a.get("atom", a)
    val = a.get("value")
    pred = _atom_pred(atom)
    return f"{pred}={val}" if val is not None else pred


_GIVEN: language.Words = {
    "zh": "（条件于 {conditions}）", "en": " (given {conditions})"}

_Q_EFFECT: language.Words = {
    "zh": "估计 **干预 {intervention}** 对 **{target}** 的因果效应。",
    "en": "Estimate the causal effect of **intervening {intervention}** on "
          "**{target}**.",
}
_Q_EFFECT_BARE: language.Words = {
    "zh": "估计一次干预的因果效应有多大。",
    "en": "How large is the causal effect of an intervention?",
}
_Q_CAUSE: language.Words = {
    "zh": "**{cause}** 是否因果影响 **{effect}**？",
    "en": "Does **{cause}** causally affect **{effect}**?",
}
_Q_CAUSE_BARE: language.Words = {
    "zh": "一个变量是否因果影响另一个变量？",
    "en": "Does one variable causally affect another?",
}
_Q_ASSOC: language.Words = {
    "zh": "**{left}** 与 **{right}** 是否（在图中）相关联？",
    "en": "Are **{left}** and **{right}** associated (in the graph)?",
}
_Q_ASSOC_BARE: language.Words = {
    "zh": "两个变量在图中是否相关联？",
    "en": "Are two variables associated in the graph?",
}
_Q_IDENTIFY: language.Words = {
    "zh": "**干预 {intervention}** 对 **{target}** 的效应，"
          "是否可从观测数据**非参数识别**？",
    "en": "Is the effect of **intervening {intervention}** on **{target}** "
          "**nonparametrically identifiable** from observational data?",
}
_Q_IDENTIFY_BARE: language.Words = {
    "zh": "目标效应是否可从观测数据**非参数识别**？",
    "en": "Is the target effect **nonparametrically identifiable** from "
          "observational data?",
}
_Q_PROBABILITY: language.Words = {
    "zh": "求 **{target}** 的概率。",
    "en": "The probability of **{target}**.",
}
_Q_PROBABILITY_BARE: language.Words = {
    "zh": "求某个事件在模型下的概率。",
    "en": "The probability of an event under the model.",
}
_Q_COUNTERFACTUAL: language.Words = {
    "zh": "已知 **{observed}**，若当初 **{intervention}**，"
          "**{target}** 的概率是多少？",
    "en": "Given **{observed}**, had **{intervention}** been the case "
          "instead, what is the probability of **{target}**?",
}
_Q_COUNTERFACTUAL_BARE: language.Words = {
    "zh": "求反事实联合分布中某一格的值。",
    "en": "One cell of the counterfactual joint distribution.",
}
_Q_CAUSATION: language.Words = {
    "zh": "**{cause}** 对 **{effect}** 的归因概率 —— "
          "必要性 PN / 充分性 PS / 两者兼备 PNS。",
    "en": "The probabilities of causation of **{cause}** for **{effect}** — "
          "necessity PN / sufficiency PS / both PNS.",
}
_Q_CAUSATION_BARE: language.Words = {
    "zh": "求归因概率 —— 必要性 PN / 充分性 PS / PNS。",
    "en": "The probabilities of causation — necessity PN / sufficiency PS / "
          "PNS.",
}
_Q_SCM_COUNTERFACTUAL: language.Words = {
    "zh": "在线性结构方程模型下，若这个个体当初 **{intervention}**，"
          "其 **{target}** 会是多少？",
    "en": "Under a linear structural equation model, had this individual "
          "**{intervention}**, what would their **{target}** have been?",
}
_Q_SCM_COUNTERFACTUAL_BARE: language.Words = {
    "zh": "在线性结构方程模型下，求某个个体的反事实结局。",
    "en": "Under a linear structural equation model, one individual's "
          "counterfactual outcome.",
}
_Q_CONJUNCTION_ONE: language.Words = {
    "zh": "求这 1 个反事实事件的概率。",
    "en": "The probability of this one counterfactual event.",
}
_Q_CONJUNCTION: language.Words = {
    "zh": "求 {count} 个反事实事件**同时成立**的概率。",
    "en": "The probability that {count} counterfactual events **hold "
          "together**.",
}
_Q_CONJUNCTION_GIVEN: language.Words = {
    "zh": "（以另外 {count} 个反事实事件为条件）",
    "en": " (conditional on {count} further counterfactual events)",
}
_Q_CONJUNCTION_BARE: language.Words = {
    "zh": "求多个反事实事件同时成立的概率。",
    "en": "The probability that several counterfactual events hold together.",
}
_Q_PROXIMAL: language.Words = {
    "zh": "**{treatment}** 对 **{outcome}** 的效应 —— 混杂 **{latent}** "
          "没有数据，用代理 **{treatment_proxy}** / **{outcome_proxy}** "
          "把它校正掉。",
    "en": "The effect of **{treatment}** on **{outcome}** — the confounder "
          "**{latent}** has no data, so the proxies **{treatment_proxy}** / "
          "**{outcome_proxy}** correct for it.",
}
_Q_PROXIMAL_BARE: language.Words = {
    "zh": "用代理变量校正未测混杂后，求因果效应。",
    "en": "The causal effect, after correcting for unmeasured confounding "
          "with proxies.",
}


def _given(entries, describe, *, lang: language.Lang | str) -> str:
    """The conditioning clause three question lines share."""
    if not entries:
        return ""
    joined = language.listing((describe(e) for e in entries), lang)
    return language.fill(_GIVEN, lang, conditions=joined)


def _q_effect(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_EFFECT_BARE, lang)
    line = language.fill(
        _Q_EFFECT, lang, intervention=_valued(q.get("intervention", {})),
        target=_valued(q.get("target", {})))
    return line + _given(q.get("given") or [], _valued, lang=lang)


def _q_cause(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_CAUSE_BARE, lang)
    return language.fill(_Q_CAUSE, lang, cause=_atom_pred(q.get("from")),
                         effect=_atom_pred(q.get("to")))


def _q_assoc(q: dict | None, *, lang: language.Lang | str) -> str:
    """The kind whose question line was never rendered — twice over.

    The branch tested ``kind == "association"``; the enum value is
    ``assoc``, so it could not fire and one of the three questions whose
    answer IS the verdict was asked as ``（查询类型：assoc）``. Underneath
    that, the branch read ``from`` / ``to`` — the *cause* query's fields.
    An assoc query carries ``left`` / ``right``, so even with the string
    corrected it would have asked ``**?** 与 **?** 是否相关联``. A dead
    branch cannot be wrong out loud, which is what kept the second bug.
    """
    if q is None:
        return language.fill(_Q_ASSOC_BARE, lang)
    line = language.fill(_Q_ASSOC, lang, left=_atom_pred(q.get("left")),
                         right=_atom_pred(q.get("right")))
    return line + _given(q.get("given") or [], _atom_pred, lang=lang)


def _q_identify(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_IDENTIFY_BARE, lang)
    return language.fill(
        _Q_IDENTIFY, lang, intervention=_valued(q.get("intervention", {})),
        target=_valued(q.get("target", {})))


def _q_probability(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_PROBABILITY_BARE, lang)
    line = language.fill(_Q_PROBABILITY, lang,
                         target=_valued(q.get("target", {})))
    return line + _given(q.get("given") or [], _valued, lang=lang)


def _q_counterfactual(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_COUNTERFACTUAL_BARE, lang)
    # ``observed`` is one grounded atom, not a list — the schema settles
    # this and intuition gets it wrong, the same way ``assoc`` carries
    # ``left`` / ``right`` where the branch above it reads ``from`` / ``to``.
    return language.fill(
        _Q_COUNTERFACTUAL, lang, observed=_valued(q.get("observed", {})),
        intervention=_valued(q.get("counterfactual_intervention", {})),
        target=_valued(q.get("counterfactual_target", {})))


def _q_causation(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_CAUSATION_BARE, lang)
    return language.fill(_Q_CAUSATION, lang, cause=_atom_pred(q.get("cause")),
                         effect=_atom_pred(q.get("effect")))


def _q_scm_counterfactual(q: dict | None, *,
                          lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_SCM_COUNTERFACTUAL_BARE, lang)
    return language.fill(
        _Q_SCM_COUNTERFACTUAL, lang,
        intervention=_valued(q.get("intervention", {})),
        target=_valued(q.get("target", {})))


def _q_counterfactual_conjunction(q: dict | None, *,
                                  lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_CONJUNCTION_BARE, lang)
    n = len(q.get("events") or [])
    line = (language.fill(_Q_CONJUNCTION_ONE, lang) if n == 1
            else language.fill(_Q_CONJUNCTION, lang, count=n))
    if q.get("condition"):
        line += language.fill(_Q_CONJUNCTION_GIVEN, lang,
                              count=len(q["condition"]))
    return line


def _q_proximal_effect(q: dict | None, *, lang: language.Lang | str) -> str:
    if q is None:
        return language.fill(_Q_PROXIMAL_BARE, lang)
    return language.fill(
        _Q_PROXIMAL, lang, treatment=_atom_pred(q.get("treatment")),
        outcome=_atom_pred(q.get("outcome")),
        latent=_atom_pred(q.get("latent")),
        treatment_proxy=_atom_preds(q.get("treatment_proxy"), lang),
        outcome_proxy=_atom_preds(q.get("outcome_proxy"), lang))


class _QuestionLine(Protocol):
    """What one kind's question line is called with.

    A protocol rather than a ``Callable[...]``, because the reader's
    language arrives by keyword and a ``Callable`` can only describe
    positions.
    """

    def __call__(self, q: dict | None, *,
                 lang: language.Lang | str) -> str: ...


_QUESTION_LINES: dict = questions.bind({
    questions.EFFECT: _q_effect,
    questions.CAUSE: _q_cause,
    questions.ASSOC: _q_assoc,
    questions.IDENTIFY: _q_identify,
    questions.PROBABILITY: _q_probability,
    questions.COUNTERFACTUAL: _q_counterfactual,
    questions.CAUSATION: _q_causation,
    questions.SCM_COUNTERFACTUAL: _q_scm_counterfactual,
    questions.COUNTERFACTUAL_CONJUNCTION: _q_counterfactual_conjunction,
    questions.PROXIMAL_EFFECT: _q_proximal_effect,
})


def _render_question(result: dict, program: dict | None, *,
                     lang: language.Lang | str) -> str:
    q = _find_query(program, result.get("query_id"))
    kind = result.get("query_kind") or (q or {}).get("kind")
    if q is not None and q.get("kind") != kind:
        # A query of another kind carries other fields; handing it to this
        # kind's renderer is how both of today's question-line bugs read.
        # Reachable only when the result names no query_id and the program
        # leads with a different question.
        q = None
    line: _QuestionLine = _QUESTION_LINES[questions.reading_of(kind)]
    return line(q, lang=lang)


# --- answer -------------------------------------------------------------------


def _render_answer(result: dict, *, lang: language.Lang | str) -> str:
    """The one line that answers the question, chosen from what the run
    produced.

    The order below is not a ranking of fields by strength. It is: what
    the query asked for, then why it could not be had, then what was
    established about the graph on the way there. The numeric layers come
    first because a numeric question was asked, and an interval is an
    answer to it as much as a point is. A refusal comes next — it is the
    answer whenever there is no number, and unlike the fall-throughs
    below it knows why.

    The structural verdict comes last of the three, and that is the part
    worth stating. For a query whose answer really IS a verdict — cause,
    association, identify — nothing above it ever fires, so it loses
    nothing by sitting low. For a query that asked for a number it is
    scaffolding, and rendering scaffolding in the answer slot is how a
    positivity violation reached a reader as a confident "是".

    That last sentence was written about one branch and was true of five.
    The estimate's shape used to be recovered here by probing field names in
    order; a curve, a decomposition, a joint contrast and a counterfactual
    cell matched no probe, and 84 of them across one suite run fell all the
    way to the verdict. The shape is now declared by the method that
    produced it (:mod:`themis.answers`), so an unrenderable estimate says so
    instead of borrowing the sentence below it.

    The same correction, one layer over: a query answered from theta calls
    no estimator, so it has no shape to declare and puts its answer in a
    block instead. Those fell to the bare ``numeric_result`` value, which
    is a headline — for causation, one of three named quantities, printed
    with no name under a question line that had just asked for all three.
    """
    status = result.get("status")
    ne = result.get("numeric_estimate")
    nr = result.get("numeric_result")
    sr = result.get("structural_result")
    evaluated = [
        b for b in (result.get("bounds_results") or ())
        if isinstance(b, dict) and b.get("lower_value") is not None
    ]

    # 1. The data-path estimate, in whatever shape its estimand has.
    if ne:
        shape = answers.shape_of(ne)
        if shape is not None:
            shape_renderer: _ShapeRenderer = _ANSWER_RENDERERS[shape]
            return shape_renderer(ne, result, lang=lang)

    # 2. The theta path, whose answer is a block. Above the bare value
    #    below it because that value is a headline drawn FROM the block —
    #    for causation, one of the three quantities it holds, and the
    #    headline cannot say which one it is.
    extensions = result.get("extensions") or {}
    for block in blocks.rendered_in(blocks.Family.ANSWER):
        if extensions.get(block):
            block_renderer: _BlockRenderer = _ANSWER_BLOCK_RENDERERS[block]
            said = block_renderer(extensions[block], result, lang=lang)
            if said:
                return said

    # 3. Symbolic numeric value, for the paths that carry no block.
    if nr and nr.get("value") is not None:
        line = f"**{_fmt(nr['value'])}**"
        iv = nr.get("interval")
        if iv and len(iv) == 2:
            line += language.fill(_INTERVAL_SUFFIX, lang,
                                  lower=_fmt(iv[0]), upper=_fmt(iv[1]))
        if nr.get("unit"):
            line += f" {nr['unit']}"
        return line

    # 4. Bounds — partial identification. An interval is a weaker answer
    #    than a point and still an answer to the question that was asked.
    #    Which quantity it brackets is said out loud: this line used to print
    #    two numbers and a method name under a question about one arm, while
    #    the Balke-Pearl branch was bracketing the difference between two.
    #    There can be several: the bounds channel reports every method whose
    #    assumptions hold, and which interval rests on what is not a caveat
    #    here — it is the only thing that makes the numbers readable.
    if evaluated:
        estimand = language.gloss(
            _BOUNDS_ESTIMAND_WORDS, evaluated[0].get("estimand"), lang,
            unknown=language.fill(_THE_QUANTITY_ASKED, lang))
        if len(evaluated) == 1:
            said = language.fill(
                _ONE_INTERVAL, lang, interval=_bounds_interval(evaluated[0]),
                estimand=estimand,
                method=evaluated[0].get("method", "bounds"),
                tightness=_tightness_word(evaluated[0], lang=lang))
        else:
            rows = language.fill(language.BETWEEN_STATEMENTS, lang).join(
                language.fill(_INTERVAL_ROW, lang,
                              method=b.get("method", "bounds"),
                              rests_on=_bounds_rests_on(b, lang=lang),
                              tightness=_tightness_word(b, lang=lang),
                              interval=_bounds_interval(b))
                for b in evaluated
            )
            said = language.fill(_SEVERAL_INTERVALS, lang, estimand=estimand,
                                 count=len(evaluated), rows=rows)
        # Rows differing in width by a factor of two on one result is a fact
        # about which of them assumed what, and it reads as a fact about
        # precision unless the difference between the two is said.
        said += language.fill(language.BETWEEN_SENTENCES, lang)
        said += language.fill(
            _WIDTH_IS, lang,
            advice=language.fill(
                intervals.width_of(_BOUNDS_INTERVAL, {}).advice, lang))
        for b in evaluated:
            contrast = b.get("contrast")
            if isinstance(contrast, dict) and contrast.get("lower_value") is not None:
                named = language.gloss(
                    _BOUNDS_CONTRAST_WORDS, contrast.get("kind"), lang,
                    unknown=language.fill(_A_CONTRAST, lang))
                said += language.fill(
                    _ALSO_A_CONTRAST, lang, named=named,
                    lower=_fmt(contrast["lower_value"]),
                    upper=_fmt(contrast["upper_value"]),
                    reference=contrast.get("reference_value"))
        return said

    # 5. A refusal, which is an answer. Below the numeric branches, not
    #    above: dispatch attaches a refusal for a SUPPLEMENTARY estimate
    #    (the longitudinal path attaches to the first effect result) to a
    #    result that may already carry a genuine point or interval, and
    #    that number is still the answer there.
    failure = result.get("estimator_failure")
    if isinstance(failure, dict) and failure.get("failure_type"):
        reason = _sentence(refusals.said(failure, lang), lang=lang)
        words = _kind_words(failure.get("kind")) or _NO_NUMBER
        # "来自" rather than "估计器": identification refuses through this
        # same field, and it is not an estimator.
        return language.fill(
            _REFUSAL_SOURCE, lang,
            line=language.sentences(
                language.fill(words, lang, reason=reason),
                _routes_said(failure, lang=lang), lang=lang),
            estimator=failure.get("estimator", "?"),
            species=failure["failure_type"])

    # 5b. An estimate block carrying no answer at all. Stated here rather
    #     than falling through, because what it would fall to is a verdict
    #     about the graph standing in for the number that was asked for —
    #     the substitution the shape table removes, in the one case the
    #     table itself cannot rule out.
    if ne:
        return language.fill(_NOTHING_TO_SHOW, lang,
                             method=ne.get("method", "?"))

    # 6. The structural verdict, read as the proposition it asserts rather
    #    than as a bare 是 / 否. Which proposition that is depends on what
    #    was asked, and the boolean cannot say — it is the same field for
    #    a cause query, where it is the answer, and for an effect query,
    #    where it is a precondition (:mod:`themis.questions`).
    reading = questions.reading_of(result.get("query_kind"))
    if sr and sr.get("value") is not None:
        val = sr["value"]
        paths = sr.get("supporting_paths") or []
        note = (language.fill(_SUPPORTING_PATHS, lang, count=len(paths))
                if paths else "")
        if val is not True and val is not False:
            # The schema admits a string here; no producer writes one.
            return language.fill(_CONCLUSION, lang, verdict=val, note=note)
        settled = language.fill(
            reading.settles if val else reading.fails, lang)
        if reading.verdict_is_the_answer:
            return language.fill(
                _CONCLUSION_SETTLED, lang,
                verdict=language.fill(_YES if val else _NO, lang),
                settled=settled, note=note)
        if val is False:
            # Not a weak answer to "how large is it": the quantity cannot
            # be obtained at all, and saying so IS the answer. A bare 否
            # was not even a sentence about the question that was asked.
            return language.fill(_NOT_OBTAINABLE, lang, settled=settled)
        # Identifiable. The number's absence has some other cause, and the
        # branches below know which — this branch used to answer here and
        # 34 results in one suite run carried a ``formula``, so the line
        # they needed was already written directly underneath.

    # 7. Identified but needs data, or genuinely blocked. The proposition
    #    comes from the same table: this line said "效应可识别" to five
    #    ``probability`` queries in one suite run, which had asked for a
    #    probability and not for an effect.
    if result.get("formula") is not None:
        return language.fill(
            _IDENTIFIED_NEEDS_DATA, lang,
            settled=language.fill(reading.settles, lang))
    if sr and sr.get("value") is True:
        # Identification finished without producing an estimand a number
        # could be plugged into — a mediation decomposition, a proximal
        # matrix inversion. Reached only for the kinds that asked for a
        # number, since the verdict answers the others above.
        return language.fill(
            _IDENTIFIED_NO_ESTIMAND, lang,
            settled=language.fill(reading.settles, lang))
    if status in ("needs_investigation", "needs_assumption"):
        return language.fill(_NO_ANSWER_YET, lang)
    if status == "outside_language":
        return language.fill(_OUTSIDE_LANGUAGE, lang)
    return language.fill(_NO_ANSWER_FIELD, lang)


_INTERVAL_SUFFIX: language.Words = {
    "zh": "（区间 [{lower}, {upper}]）",
    "en": " (interval [{lower}, {upper}])",
}
_THE_QUANTITY_ASKED: language.Words = {
    "zh": "所问的量", "en": "the quantity that was asked about"}
_ONE_INTERVAL: language.Words = {
    "zh": "给出**区间** {interval}——{estimand}"
          "（部分识别的界，不是点估计；method=`{method}`，{tightness}）。",
    "en": "An **interval** {interval} — {estimand} (partial-identification "
          "bounds, not a point estimate; method=`{method}`, {tightness}).",
}
_INTERVAL_ROW: language.Words = {
    "zh": "`{method}`（{rests_on}；{tightness}）{interval}",
    "en": "`{method}` ({rests_on}; {tightness}) {interval}",
}
#: What the width of these intervals is a fact about. Said once under the
#: set rather than per row: it is true of all of them, and it is the
#: sentence that stops a reader reading the narrowest row as the best
#: estimate rather than as the one that assumed the most (#419). The
#: sentence itself comes from the vocabulary, so this template is about a
#: width and not about one of the three.
_WIDTH_IS: language.Words = {
    "zh": "关于宽度：{advice}。",
    "en": "About the width: {advice}.",
}
_SEVERAL_INTERVALS: language.Words = {
    "zh": "给出**区间**——{estimand}（部分识别的界，不是点估计）。"
          "共 {count} 条，界定的是同一个量，各自靠不同的假设："
          "{rows}。按你接受哪组假设来读，不要取交。",
    "en": "**Intervals** — {estimand} (partial-identification bounds, not a "
          "point estimate). {count} of them, all bracketing the same "
          "quantity and each resting on different assumptions: {rows}. Read "
          "whichever rests on assumptions you accept; do not intersect them.",
}
#: The pair of endpoints a bounds row brackets with. Asked of the census
#: rather than named here: the width of THIS slot is settled by the slot,
#: and a renderer that names the member instead is one more place the
#: classification would have to be kept in step (#419).
_BOUNDS_INTERVAL = intervals.pair_at(
    "$defs.boundsResult", "lower_value", "upper_value")
_A_CONTRAST: language.Words = {"zh": "对照", "en": "a contrast"}
_TIGHTNESS_UNSTATED: language.Words = {
    "zh": "紧度未声明", "en": "tightness unstated"}


def _tightness_word(row: dict, *, lang: language.Lang | str) -> str:
    """Whether a narrower set is consistent with the same assumptions.

    A row from an older build carries no answer, and saying "sharp" for it
    would be this surface deciding a question about a procedure it did not
    run — the same substitution the width above used to make.
    """
    said = row.get(intervals.TIGHTNESS_FIELD)
    if said is None:
        return language.fill(_TIGHTNESS_UNSTATED, lang)
    return language.fill(intervals.tightness_named(str(said)).words, lang)


_ALSO_A_CONTRAST: language.Words = {
    "zh": "同一批数据还给出**{named}** [{lower}, {upper}]"
          "——与 `{reference}` 那条臂相比的差值，"
          "它是另一个量，不是上面两个端点相减。",
    "en": "The same data also give **{named}** [{lower}, {upper}] — the "
          "difference against the `{reference}` arm. That is a different "
          "quantity, not the two endpoints above subtracted.",
}
_NO_NUMBER: language.Words = {
    "zh": "**没有给出数值**：{reason}", "en": "**No number**: {reason}"}
_REFUSAL_SOURCE: language.Words = {
    "zh": "{line}（来自 `{estimator}`，拒答类型 `{species}`）",
    "en": "{line}(from `{estimator}`, refusal type `{species}`)",
}
_NOTHING_TO_SHOW: language.Words = {
    "zh": "**没有给出数值**：估计器 `{method}` 返回的估计块里"
          "没有任何可呈现的答案。",
    "en": "**No number**: the estimate block `{method}` returned holds no "
          "answer that can be shown.",
}
_SUPPORTING_PATHS: language.Words = {
    "zh": "（支持路径 {count} 条）", "en": " ({count} supporting paths)"}
_CONCLUSION: language.Words = {
    "zh": "结论：**{verdict}**{note}", "en": "Conclusion: **{verdict}**{note}"}
_CONCLUSION_SETTLED: language.Words = {
    "zh": "结论：**{verdict}** —— {settled}{note}",
    "en": "Conclusion: **{verdict}** — {settled}{note}",
}
_YES: language.Words = {"zh": "是", "en": "yes"}
_NO: language.Words = {"zh": "否", "en": "no"}
_NOT_OBTAINABLE: language.Words = {
    "zh": "**{settled}** —— 问的是一个数，"
          "而这个量从当前的图与假设里得不出来。",
    "en": "**{settled}** — a number was asked for, and this quantity cannot "
          "be obtained from the graph and the assumptions as they stand.",
}
_IDENTIFIED_NEEDS_DATA: language.Words = {
    "zh": "**{settled}**（估计式见下方「怎么算出来的」），但当前"
          "**没有数据** → 需要数据才能给出具体数值。"
          "所需数据见下方「数据缺口」。",
    "en": "**{settled}** (the estimand is under \u201cHow it was arrived "
          "at\u201d below), but there are **no data** right now \u2192 data "
          "are what turn it into a number. What is needed is under "
          "\u201cData gaps\u201d below.",
}
_IDENTIFIED_NO_ESTIMAND: language.Words = {
    "zh": "**{settled}**，但这一轮**没有给出数值** —— "
          "识别到此为止，没有产出可直接代入的估计式；"
          "要得到具体数字需要数据。",
    "en": "**{settled}**, but this run produced **no number** — "
          "identification stopped here without an estimand data could be "
          "put into; a number would take data.",
}
_NO_ANSWER_YET: language.Words = {
    "zh": "当前**还不能给出答案** —— 缺口与补法见下方「数据缺口」。",
    "en": "**No answer yet** — what is missing, and how to supply it, is "
          "under \u201cData gaps\u201d below.",
}
_OUTSIDE_LANGUAGE: language.Words = {
    "zh": "该问题**超出 Themis 可表达 / 可识别的范围**。",
    "en": "This question is **outside what Themis can express or "
          "identify**.",
}
_NO_ANSWER_FIELD: language.Words = {
    "zh": "（无可呈现的答案字段）", "en": "(no answer field to show)"}


_POC_LABELS = (
    ("pn", {"zh": "必要性 PN（归因）", "en": "necessity PN (attribution)"}),
    ("ps", {"zh": "充分性 PS", "en": "sufficiency PS"}),
    ("pns", {"zh": "必要且充分 PNS", "en": "necessary and sufficient PNS"}),
)
"""The three quantities a causation query asks for, named once.

Two surfaces say them — the data path, where they arrive as an estimate's
bounds, and the theta path, where they arrive as a block. Named in one
place because the second was written ten rounds after the first and the
question the reader asked is the same one.
"""




_MONOTONE_PINNED: language.Words = {
    "zh": "单调性成立（X 从不阻止 Y），三者点识别：",
    "en": "Monotonicity holds (X never prevents Y), so all three are "
          "point-identified:",
}
_MONOTONE_STILL_BOUNDED: language.Words = {
    "zh": "已假设单调性，但三者仍只能给界：",
    "en": "Monotonicity was assumed, and all three are still only bounded:",
}
_NOT_MONOTONE: language.Words = {
    "zh": "未假设单调性，三者只能给界：",
    "en": "Monotonicity was not assumed, so all three are only bounded:",
}
#: The pair of ci keys on a probability of causation, and what it holds.
#: Asked rather than derived: this renderer used to decide between "CI" and
#: "外带" from ``point is not None``, in its own two-member table, while the
#: browser derived the same thing again and ``types.ts`` stated it a third
#: time in prose. The words are on :class:`themis.intervals.Width` now, with
#: what would narrow each beside them (#419).
_POC_CI = intervals.pair_at("$defs.causationEstimate", "ci_lower", "ci_upper")
_WITHOUT_MONOTONICITY: language.Words = {
    "zh": "无单调性假设时只能给到 [{lower}, {upper}]",
    "en": "without monotonicity it only reaches [{lower}, {upper}]",
}
_POC_ROW: language.Words = {
    "zh": "- {label}：{head}{aside}", "en": "- {label}: {head}{aside}"}
_POC_ASIDE: language.Words = {"zh": "（{items}）", "en": " ({items})"}
_ADJUSTMENT_SET: language.Words = {
    "zh": "，调整集 {variables}", "en": ", adjustment set {variables}"}
_INSTRUMENT_IS: language.Words = {
    "zh": "，工具变量 `{name}`", "en": ", instrument `{name}`"}
_FROM_RISKS: language.Words = {
    "zh": "由干预风险 P(Y|do X)={high}、P(Y|do ¬X)={low} 算出",
    "en": "computed from the interventional risks P(Y|do X)={high} and "
          "P(Y|do ¬X)={low}",
}
_NO_RISKS_USED: language.Words = {
    "zh": "没有用到任何干预风险",
    "en": "no interventional risk was used",
}
_RISK_ROW: language.Words = {
    "zh": "- {risks}（{note}）", "en": "- {risks} ({note})"}
_IF_MONOTONE: language.Words = {
    "zh": "- 若可假设单调性（X 从不阻止 Y），三者可点识别。",
    "en": "- If monotonicity can be assumed (X never prevents Y), all three "
          "become point-identified.",
}


def _render_causation(poc: dict, *, ci_level: float | None = None,
                      lang: language.Lang | str) -> str:
    """PN / PS / PNS, each said by name, wherever the three came from.

    Three entry points share this: the two shapes the data path comes out
    in, and the block the theta path puts its answer in. They used to be
    two renderers saying the same three names, and each knew half of what
    the reader needs — one the confidence band and the adjustment set, the
    other the point monotonicity buys and where the do-risks came from.

    Every quantity carries an interval; a point is there only when
    monotonicity was declared, so its absence is the statement that the
    assumption was not made rather than a hole in the answer.
    """
    lines: list[str] = []
    # A declared monotonicity reaches the two solvers at different places
    # because the two theorems have different places for it. Tian-Pearl takes
    # it as a second formula: the interval stays assumption-free and a point
    # appears beside it. The response-function program takes it as a
    # restriction of the model: it narrows the one interval and, in practice,
    # never pins it. So neither what was bought nor whether a point exists is
    # readable off the flag, and both are read off what came back.
    folded_in = (
        poc.get("interventional_risk_provenance") == "instrument_response_polytope"
    )
    #: Which of the three the bands under this block are. One flag settles it
    #: for all three quantities, so it is read off whichever row carries a
    #: band and said once, under them.
    width_said: intervals.Width | None = None
    for key, label in _POC_LABELS:
        q = poc.get(key) or {}
        point, lo, hi = q.get("point"), q.get("lower"), q.get("upper")
        bounded = lo is not None and hi is not None
        head = (
            f"**{_fmt(point)}**" if point is not None
            else f"**[{_fmt(lo)}, {_fmt(hi)}]**" if bounded
            else None
        )
        if head is None:
            continue
        # One pair of CI keys, two objects. Which one is on the row now, so
        # the reader is told the difference that decides what to do next:
        # more data narrows a point's interval and narrows a band on the
        # identified set only as far as that set.
        aside: list[str] = []
        ci_lo, ci_hi = q.get("ci_lower"), q.get("ci_upper")
        if ci_lo is not None and ci_hi is not None:
            level = f"{ci_level:.0%} " if ci_level is not None else ""
            width, said = intervals.width_or_unstated(_POC_CI, q)
            band = language.fill(said, lang)
            width_said = width or width_said
            aside.append(f"{level}{band} [{_fmt(ci_lo)}, {_fmt(ci_hi)}]")
        if point is not None and bounded and not folded_in:
            # Tian-Pearl bounds use no monotonicity, so this is exactly what
            # the assumption bought — the reader cannot weigh the point
            # without seeing the interval it replaced. Not sayable on the route
            # that folds the assumption into the interval: there the pair IS
            # the post-assumption answer, and this sentence would invert it.
            aside.append(language.fill(_WITHOUT_MONOTONICITY, lang,
                                       lower=_fmt(lo), upper=_fmt(hi)))
        joined = language.fill(language.BETWEEN_STATEMENTS, lang).join(aside)
        lines.append(language.fill(
            _POC_ROW, lang, label=language.fill(label, lang), head=head,
            aside=(language.fill(_POC_ASIDE, lang, items=joined)
                   if aside else "")))
    if not lines:
        return ""

    monotonic = bool(poc.get("monotonic"))
    pinned = any(
        (poc.get(key) or {}).get("point") is not None for key, _ in _POC_LABELS
    )
    head = language.fill(
        _MONOTONE_PINNED if pinned
        else _MONOTONE_STILL_BOUNDED if monotonic
        else _NOT_MONOTONE, lang)
    # WHERE the three numbers came from — on every route, not only the ones
    # that end with a pair of risks to print. One route reaches them without
    # any: the response-function program over an instrument. Hanging this line
    # off the risks being present left that route saying nothing at all.
    prov = poc.get("interventional_risk_provenance")
    if prov:
        note = risk_provenance.describe(prov, lang)
        adj = poc.get("adjustment")
        if adj:
            note += language.fill(_ADJUSTMENT_SET, lang, variables=_vars(adj))
        if poc.get("instrument"):
            note += language.fill(_INSTRUMENT_IS, lang,
                                  name=poc["instrument"])
        risk_hi, risk_lo = poc.get("p_y_do_x1"), poc.get("p_y_do_x0")
        risks = (
            language.fill(_FROM_RISKS, lang, high=_fmt(risk_hi),
                          low=_fmt(risk_lo))
            if risk_hi is not None and risk_lo is not None
            else language.fill(_NO_RISKS_USED, lang)
        )
        lines.append(language.fill(_RISK_ROW, lang, risks=risks, note=note))
    if not pinned and not monotonic:
        lines.append(language.fill(_IF_MONOTONE, lang))
    # The bands above have a name now; what the name is FOR is the sentence
    # beside it. Whether more rows would narrow this is the question the
    # reader is actually holding, and the two names answer it differently
    # (#419).
    if width_said is not None:
        lines.append(language.fill(
            _WIDTH_IS, lang,
            advice=language.fill(width_said.advice, lang)))
    return "\n".join([head] + lines)


_POINT_WITH_CI: language.Words = {
    "zh": "**{point}**　（{level}% CI [{lower}, {upper}]）",
    "en": "**{point}**  ({level}% CI [{lower}, {upper}])",
}


def _render_numeric_estimate(ne: dict, outcome_error: dict | None = None, *,
                             lang: language.Lang | str) -> str:
    point = _fmt(ne["point"])
    lines = []
    if ne.get("ci_lower") is not None and ne.get("ci_upper") is not None:
        lines.append(language.fill(
            _POINT_WITH_CI, lang, point=point,
            level=_fmt(ne.get("ci_level", 0.95) * 100),
            lower=_fmt(ne["ci_lower"]), upper=_fmt(ne["ci_upper"])))
    else:
        lines.append(f"**{point}**")

    lines.extend(_estimate_meta(ne, outcome_error, lang=lang))
    return "\n".join(lines)


def _ar_interval(ar: dict) -> str:
    """A weak-instrument-robust confidence set, written as the set it is.

    Three blocks produce one of these — the just-identified inversion, the
    stratified Wald's own moment, and the heteroskedasticity-robust
    polynomial — and only the last can come out in more than two pieces, so
    only it carries ``segments``. Reading that first and the endpoints
    second means one renderer rather than a branch per producer.
    """
    segments = ar.get("segments")
    if segments:
        return " ∪ ".join(
            f"[{_fmt(s['lower']) if s.get('lower') is not None else '−∞'}, "
            f"{_fmt(s['upper']) if s.get('upper') is not None else '+∞'}]"
            for s in segments
        )
    kind, lower, upper = ar.get("kind"), ar.get("lower"), ar.get("upper")
    if kind == "empty":
        return "∅"
    if kind == "whole_line":
        return "(−∞, +∞)"
    if kind == "disconnected":
        return f"(−∞, {_fmt(lower)}] ∪ [{_fmt(upper)}, +∞)"
    left = _fmt(lower) if lower is not None else "−∞"
    right = _fmt(upper) if upper is not None else "+∞"
    return f"[{left}, {right}]"


#: Which design's residual a declared measurement error was priced against,
#: as ``outcome_error.design_kind``.
#:
#: The sentence STATES the number rather than standing beside it, because
#: what the number means is a fact about the design: on two of the three it
#: is the precision cost, on the third the influence function splits the
#: variance across terms only one of which carries the outcome residual, so
#: the same arithmetic returns a CEILING. A reader who meets the figure
#: first and the qualification second has already read it as the cost.
#:
#: Nothing on the envelope says which of the two it is — deliberately: a
#: field for it would be a second record of the design name, free to
#: disagree with it. This table is where it is said, and it is said once.
#:
#: What the error does to the POINT is here for the same reason. It is
#: nothing on the first two; on the front door it is nothing only while the
#: error is unrelated to the confounder the graph posits, and that premise
#: is about a variable nobody measured.
_OUTCOME_ERROR_DESIGN_WORDS: dict[str, language.Words] = {
    "back_door":
        {"zh": "区间比结局测准时宽 {factor} 倍 —— 后门调整设计：残差取自 Y 对（暴露＋调整集）"
        "的最小二乘投影，这个倍数就是精度代价本身；点估计不受影响",
         "en": "the interval is {factor} times wider than it would be with the "
               "outcome measured correctly — a back-door design: the residual "
               "comes from the least-squares projection of Y on (exposure + "
               "adjustment set), and that factor is the precision cost itself; "
               "the point estimate is unaffected"},
    "instrumental_variable":
        {"zh": "区间比结局测准时宽 {factor} 倍 —— 工具变量设计：残差是围绕 IV 系数的**结构**"
        "残差，不是最小二乘残差；2SLS 的夹心方差此时正好多出 σ²_v 一项，所以这个"
        "倍数同样是精度代价本身；点估计不受影响，它要的是误差与**工具**无关，"
        "而不是与暴露、调整集无关",
         "en": "the interval is {factor} times wider than it would be with the "
               "outcome measured correctly — an instrumental-variable design: "
               "the residual is the **structural** residual around the IV "
               "coefficient rather than a least-squares one, and the 2SLS "
               "sandwich variance gains exactly one σ²_v term here, so the "
               "factor is again the precision cost itself; the point estimate "
               "is unaffected, since what it needs is error independent of the "
               "**instrument**, not of the exposure and adjustment set"},
    "front_door":
        {"zh": "区间比结局测准时**至多**宽 {factor} 倍 —— 前门设计：残差取自 Y 对（暴露＋中介"
        "＋调整集）的结局模型；前门的方差里还有一项完全不含结局残差，σ²_v 折不"
        "进去，所以这个倍数是精度代价的**上界**而不是代价本身（本仓自己的前门"
        "估计量上实测：报 1.25 倍，真实区间只宽 1.09 倍）。而且这条路线上点估计"
        "**未必**不受影响：前门图假定了一个未观测的混杂，测量误差只要与它有关，"
        "动的就是点估计本身，而不只是区间",
         "en": "the interval is **at most** {factor} times wider than it "
               "would be "
               "with the outcome measured correctly — a front-door design: the "
               "residual comes from the outcome model of Y on (exposure + "
               "mediator + adjustment set); the front-door variance also "
               "carries a term with no outcome residual in it at all, into "
               "which σ²_v does not fold, so this factor is an **upper bound** "
               "on the precision cost rather than the cost itself (measured on "
               "this repository's own front-door estimator: it reports 1.25×, "
               "and the interval is only 1.09× wider). And on this route the "
               "point estimate is **not necessarily** unaffected: the "
               "front-door graph assumes an unobserved confounder, and "
               "measurement error related to it moves the point estimate "
               "itself rather than only the interval"},
}

#: An envelope that never said which design. Not silently read as the
#: back-door one: which residual the factor was taken around is exactly what
#: decides whether it is the cost or a ceiling on it, and an older build's
#: envelope is not evidence about a question that build never asked.
_OUTCOME_ERROR_DESIGN_UNSTATED: language.Words = {
    "zh": "区间比结局测准时宽 {factor} 倍 —— 但这份信封没有说这个倍数是围绕哪个"
          "设计的残差算出来的，也就无从判断它是精度代价本身还是代价的上界",
    "en": "the interval is {factor} times wider than it would be with the "
          "outcome measured exactly — but this envelope does not say which "
          "design's residual the factor was taken around, so there is no "
          "telling whether it is the precision cost itself or a ceiling on it",
}


_META_METHOD: language.Words = {
    "zh": "方法 `{method}`", "en": "method `{method}`"}
_META_SAMPLE_SIZE: language.Words = {
    "zh": "样本量 N={n}", "en": "N={n}"}
_META_ADJUSTMENT: language.Words = {
    "zh": "调整集 {variables}", "en": "adjustment set {variables}"}
_AR_ROW: language.Words = {
    "zh": "- 弱工具稳健区间（Anderson-Rubin {level}%）：{interval} —— {kind}",
    "en": "- Weak-instrument-robust interval (Anderson-Rubin {level}%): "
          "{interval} — {kind}",
}
_HANSEN: language.Words = {
    "zh": "Hansen J，异方差稳健",
    "en": "Hansen J, heteroskedasticity-robust",
}
_SARGAN: language.Words = {"zh": "Sargan", "en": "Sargan"}
_INSTRUMENTS_REJECTED: language.Words = {
    "zh": "**数据否定了这组工具**：至少有一个工具的排除限制不成立，"
          "上面这个数建立在一个被自己的数据驳倒的前提上",
    "en": "**the data reject this set of instruments**: at least one "
          "exclusion restriction does not hold, and the number above rests "
          "on a premise its own data refute",
}
_INSTRUMENTS_NOT_REJECTED: language.Words = {
    "zh": "数据没有否定这组工具（不通过不等于成立，只是这批数据看不出矛盾）",
    "en": "the data do not reject this set of instruments (not rejecting is "
          "not the same as holding — only that these data show no "
          "contradiction)",
}
_OVERID_ROW: language.Words = {
    "zh": "- 工具联合有效性（{test}）：p={p} —— {said}",
    "en": "- Joint instrument validity ({test}): p={p} — {said}",
}
_PROPENSITY_SPAN: language.Words = {
    "zh": "倾向分原始范围 [{lower}, {upper}]",
    "en": "the propensity scores run over [{lower}, {upper}]",
}
_OVERLAP_TRIMMED: language.Words = {
    "zh": "- 重叠（正性）：{span}，其中 {trimmed} 个个体被截到 "
          "[{floor}, {ceiling}] 之内权重才有限 —— 截掉的越多，"
          "说明处理组与对照组越难找到可比的人，这个数越依赖模型往数据外推。",
    "en": "- Overlap (positivity): {span}, and {trimmed} individuals had to "
          "be clipped into [{floor}, {ceiling}] for their weights to stay "
          "finite — the more are clipped, the harder it is to find "
          "comparable people across the treated and the untreated, and the "
          "more this number leans on the model extrapolating past the data.",
}
_OVERLAP_CLEAN: language.Words = {
    "zh": "- 重叠（正性）：{span}，没有个体需要截断。",
    "en": "- Overlap (positivity): {span}, and no individual had to be "
          "clipped.",
}
_OVB_TAIL: language.Words = {
    "zh": "；解释掉 {share} 就足以让它不再显著（α={alpha}）",
    "en": "; explaining away {share} is already enough to make it "
          "non-significant (α={alpha})",
}
_OVB_ROW: language.Words = {
    "zh": "- 稳健性（未测混杂，Cinelli-Hazlett）：一个未测混杂要同时解释掉"
          "处理与结局各 {share} 的残差变异，才能把这个效应抹平{tail}。",
    "en": "- Robustness (unmeasured confounding, Cinelli-Hazlett): an "
          "unmeasured confounder would have to explain {share} of the "
          "residual variation in the treatment and {share} of it in the "
          "outcome to explain this effect away{tail}.",
}
#: Assembled from the three numbers rather than from a sentence stating
#: them. The kernel wrote that sentence, so this row was one language's,
#: and the browser had already built its own row from the same numbers.
_PRECISION_ROW: language.Words = {
    "zh": "- 精度：现在 N={n} → 95% 置信区间 ±{half}；想把区间收到一半，"
          "需要 N≈{needed}（标准误按 1/√N 缩）",
    "en": "- Precision: at N={n} the 95% interval is ±{half}; halving it "
          "needs N≈{needed} (the standard error shrinks as 1/√N)",
}
_OUTCOME_ERROR_ROW: language.Words = {
    "zh": "- 结局测量误差：{said}。未解释变异中 {share} 是测量噪声，"
          "这部分宽度只能靠把结局测准，加样本量消不掉。",
    "en": "- Outcome measurement error: {said}. {share} of the unexplained "
          "variation is measurement noise, and that part of the width goes "
          "away only by measuring the outcome better — more subjects do not "
          "remove it.",
}
#: The reading first and the arithmetic behind it second. Both are this
#: surface's sentences now: the arithmetic used to arrive as prose the
#: kernel had assembled, which restated the four numbers beside it and, on
#: the continuous route, a caveat that follows from ``path``.
_EVALUE_ROW: language.Words = {
    "zh": "- 稳健性（E-value）：{said}{arithmetic}",
    "en": "- Robustness (E-value): {said}{arithmetic}"}
_EVALUE_VERDICT: language.Words = {
    "zh": "{band}（{basis}）。", "en": "{band} ({basis}). "}
_EVALUE_BINARY: language.Words = {
    "zh": "观测到的 RR {rr}（基线发生率 {baseline}）",
    "en": "the observed RR is {rr} (baseline rate {baseline})"}
_EVALUE_CONTINUOUS: language.Words = {
    "zh": "连续结局（SD={sd}）：RR ≈ exp(0.91·d) = {rr}（Chinn 2000 换算；"
          "0.91 这个因子假设组内标准差大致相等、结局大致服从对数正态，"
          "是流行病学的经验法则，不是一个紧的界）",
    "en": "continuous outcome (SD={sd}): RR ≈ exp(0.91·d) = {rr} (the Chinn "
          "2000 conversion; its 0.91 factor assumes roughly equal "
          "within-group SDs and a roughly log-normal outcome, and is the "
          "epidemiological rule of thumb rather than a tight bound)"}
_EVALUE_POINT: language.Words = {
    "zh": "点估计上的 E 值 = {e}",
    "en": "E-value on the point estimate = {e}"}
_EVALUE_CI_BOUND: language.Words = {
    "zh": "靠近零假设那一侧置信区间端点的 E 值 = {e}",
    "en": "E-value on the confidence bound nearer the null = {e}"}


def _estimate_meta(ne: dict, outcome_error: dict | None = None, *,
                   lang: language.Lang | str) -> list[str]:
    """The lines every answer shape shares, whatever its headline looks like.

    How it was computed, how precise it is, and what would overturn it. Kept
    in one place so a shape bound later cannot ship without them — the point
    shape had all of this and the four shapes that rendered nothing at all
    had, by construction, none of it.

    The instrument-strength, instrument-validity, overlap and omitted-variable
    lines are here rather than in a section of their own for the same reason
    the rest of it is: each qualifies the interval printed directly above,
    each arrives on a different estimator's path, and a section only some
    paths reach is a section most readers never learn exists.
    """
    lines: list[str] = []
    method = ne.get("method")
    n = ne.get("sample_size")
    meta = []
    if method:
        meta.append(language.fill(_META_METHOD, lang, method=method))
    if n is not None:
        meta.append(language.fill(_META_SAMPLE_SIZE, lang, n=n))
    adj = ne.get("adjustment")
    if adj:
        meta.append(language.fill(_META_ADJUSTMENT, lang,
                                  variables=_vars(adj)))
    if meta:
        lines.append("- " + language.fill(language.BETWEEN_CLAUSES, lang).join(meta))

    # Before the precision line, because it qualifies the interval printed
    # above both of them. A reader who takes the bootstrap CI at face value
    # and stops has been told the effect is bounded when the honest answer
    # from this data is that it is not.
    # Robust first where both are present, and they can be: it is valid
    # under weak identification AND heteroskedasticity, so the homoskedastic
    # one beside it is the same set computed under an assumption the data
    # may not support. Offering both would ask the reader to choose between
    # a test and its own weaker version. The stratified set answers for a
    # different estimand and the schema says it is never present with either.
    ar = (ne.get("robust_anderson_rubin_confidence_set")
          or ne.get("stratified_anderson_rubin_confidence_set")
          or ne.get("anderson_rubin_confidence_set"))
    if ar and ar.get("kind"):
        lines.append(language.fill(
            _AR_ROW, lang, level=_fmt(ar.get("ci_level", 0.95) * 100),
            interval=_ar_interval(ar),
            kind=envelope_glossary.ar_set_kind_word(ar["kind"], lang)))

    oid = ne.get("over_identification")
    if oid:
        # Hansen when it exists: it is the one that survives heteroskedasticity,
        # and reporting the homoskedastic Sargan beside it would offer the
        # reader a choice between a test and its own weaker version.
        p_value, named = oid.get("hansen_p_value"), _HANSEN
        if p_value is None:
            p_value, named = oid.get("sargan_p_value"), _SARGAN
        if p_value is not None:
            said = language.fill(
                _INSTRUMENTS_REJECTED if p_value < 0.05
                else _INSTRUMENTS_NOT_REJECTED, lang)
            lines.append(language.fill(
                _OVERID_ROW, lang, test=language.fill(named, lang),
                p=_fmt(p_value), said=said))

    ps = ne.get("propensity_summary")
    if ps and ps.get("raw_min") is not None:
        span = language.fill(_PROPENSITY_SPAN, lang,
                             lower=_fmt(ps["raw_min"]),
                             upper=_fmt(ps.get("raw_max")))
        trimmed, floor = ps.get("n_trimmed") or 0, ps.get("floor")
        if trimmed and floor is not None:
            lines.append(language.fill(
                _OVERLAP_TRIMMED, lang, span=span, trimmed=trimmed,
                floor=_fmt(floor), ceiling=_fmt(1 - floor)))
        else:
            lines.append(language.fill(_OVERLAP_CLEAN, lang, span=span))

    ovb = ne.get("ovb_sensitivity")
    if ovb and ovb.get("robustness_value_q") is not None:
        tail = ""
        if ovb.get("robustness_value_qa") is not None:
            tail = language.fill(
                _OVB_TAIL, lang,
                share=f"{ovb['robustness_value_qa']:.1%}",
                alpha=_fmt(ovb.get("alpha", 0.05)))
        lines.append(language.fill(
            _OVB_ROW, lang, share=f"{ovb['robustness_value_q']:.1%}",
            tail=tail))

    pb = ne.get("precision_budget")
    if pb and pb.get("n_to_halve_ci") is not None:
        lines.append(language.fill(
            _PRECISION_ROW, lang, n=ne.get("sample_size"),
            half=_fmt(pb.get("current_ci_half_width")),
            needed=pb["n_to_halve_ci"]))

    # Printed next to the precision hint on purpose: that hint says how many
    # more subjects would halve the interval, and part of this interval is
    # measurement noise that no number of subjects removes. Saying only the
    # first sends the reader to buy the wrong thing.
    if outcome_error and outcome_error.get("se_inflation"):
        words = _OUTCOME_ERROR_DESIGN_WORDS.get(
            str(outcome_error.get("design_kind") or ""),
            _OUTCOME_ERROR_DESIGN_UNSTATED)
        lines.append(language.fill(
            _OUTCOME_ERROR_ROW, lang,
            said=language.fill(
                words, lang,
                factor=f"{outcome_error['se_inflation']:.2f}"),
            share=f"{outcome_error['noise_share']:.0%}"))

    sa = ne.get("sensitivity_analysis")
    if sa:
        band = sa.get("interpretation_band")
        lines.append(language.fill(
            _EVALUE_ROW, lang, arithmetic=_evalue_arithmetic(sa, lang=lang),
            said="" if not band else language.fill(
                _EVALUE_VERDICT, lang,
                band=envelope_glossary.evalue_band_word(band, lang),
                basis=envelope_glossary.evalue_band_basis_word(
                    sa.get("band_basis"), lang))))

    return lines


def _evalue_arithmetic(sa: dict, *, lang: language.Lang | str) -> str:
    """How the E-value was arrived at, or why there is none.

    Two answers under one heading, and the block says which: an estimate
    with no E-value names its :class:`themis.estimation.sensitivity.Undefined`
    reason and nothing else.
    """
    if sa.get("e_value") is None:
        return language.spoke(sa.get("undefined_because"), lang)
    parts = [language.fill(
        _EVALUE_CONTINUOUS, lang, sd=_fmt(sa.get("outcome_sd")),
        rr=_fmt(sa.get("risk_ratio")))
        if sa.get("path") == "continuous" else
        language.fill(_EVALUE_BINARY, lang, rr=_fmt(sa.get("risk_ratio")),
                      baseline=_fmt(sa.get("baseline_rate")))]
    parts.append(language.fill(_EVALUE_POINT, lang, e=_fmt(sa["e_value"])))
    if sa.get("e_value_ci_bound") is not None:
        parts.append(language.fill(_EVALUE_CI_BOUND, lang,
                                   e=_fmt(sa["e_value_ci_bound"])))
    return language.fill(language.BETWEEN_STATEMENTS, lang).join(parts)


_BAND_SUFFIX: language.Words = {
    "zh": "（CI [{lower}, {upper}]）", "en": " (CI [{lower}, {upper}])"}


def _band(part: dict | None, *, lang: language.Lang | str) -> str:
    """One estimated quantity with its interval, or an empty string."""
    if not part or part.get("point") is None:
        return ""
    line = f"**{_fmt(part['point'])}**"
    if part.get("ci_lower") is not None and part.get("ci_upper") is not None:
        line += language.fill(_BAND_SUFFIX, lang,
                              lower=_fmt(part["ci_lower"]),
                              upper=_fmt(part["ci_upper"]))
    return line


class _ShapeRenderer(Protocol):
    """What one answer SHAPE's renderer is called with.

    A protocol rather than a ``Callable[...]``: the reader's language
    arrives by keyword, and a ``Callable`` can only describe positions.
    """

    def __call__(self, ne: dict, result: dict, *,
                 lang: language.Lang | str) -> str: ...


class _BlockRenderer(Protocol):
    """What one BLOCK's renderer is called with — answer, route or ledger.

    Positional-only, because what a family calls its container differs —
    an answer block, a route block, an assumption ledger — and what this
    fixes is the SHAPE. The reader's language, which is the point of
    having a protocol at all, arrives by keyword.
    """

    def __call__(self, block: dict, result: dict, /, *,
                 lang: language.Lang | str) -> str: ...


_LABELLED_ROW: language.Words = {
    "zh": "- {label}：{value}", "en": "- {label}: {value}"}
_DOSE_CURVE: language.Words = {
    "zh": "剂量-反应**曲线**", "en": "A dose-response **curve**"}
_DOSE_REFERENCE: language.Words = {
    "zh": "（相对参考剂量 x={dose}）",
    "en": " (against the reference dose x={dose})",
}
_DOSE_SAMPLED: language.Words = {
    "zh": "{head}，共 {count} 个采样剂量：",
    "en": "{head}, at {count} sampled doses:",
}
_DOSE_AT: language.Words = {
    "zh": "- x={x}：{effect}", "en": "- x={x}: {effect}"}
_DOSE_REST: language.Words = {
    "zh": "- …（其余 {count} 个剂量见 `numeric_estimate`）",
    "en": "- … ({count} further doses are in `numeric_estimate`)",
}


def _render_dose_response_curve(ne: dict, result: dict, *,
                                lang: language.Lang | str) -> str:
    """The effect at each sampled dose, against the reference dose.

    A curve has no single number to lead with, which is exactly why probing
    for one fell through to the graph verdict.
    """
    curve = ne.get("dose_response_curve") or []
    ref = ne.get("reference_point")
    head = language.fill(_DOSE_CURVE, lang)
    if ref is not None:
        head += language.fill(_DOSE_REFERENCE, lang, dose=_fmt(ref))
    lines = [language.fill(_DOSE_SAMPLED, lang, head=head, count=len(curve))]
    shown = curve[:6]
    for pt in shown:
        seg = language.fill(_DOSE_AT, lang, x=_fmt(pt.get("x")),
                            effect=_fmt(pt.get("effect")))
        if pt.get("ci_lower") is not None and pt.get("ci_upper") is not None:
            seg += language.fill(_BAND_SUFFIX, lang,
                                 lower=_fmt(pt["ci_lower"]),
                                 upper=_fmt(pt["ci_upper"]))
        lines.append(seg)
    if len(curve) > len(shown):
        lines.append(language.fill(_DOSE_REST, lang,
                                   count=len(curve) - len(shown)))
    lines.extend(_estimate_meta(ne, result.get("outcome_error"), lang=lang))
    return "\n".join(lines)


_DECOMPOSITION: language.Words = {
    "zh": "效应**分解**（总效应 = 直接 + 间接）：",
    "en": "The effect **decomposed** (total = direct + indirect):",
}
_DECOMPOSITION_PARTS = (
    ("te", {"zh": "总效应 TE", "en": "total effect TE"}),
    ("nde", {"zh": "自然直接效应 NDE（不经中介）",
             "en": "natural direct effect NDE (not through the mediator)"}),
    ("nie", {"zh": "自然间接效应 NIE（经中介）",
             "en": "natural indirect effect NIE (through the mediator)"}),
)
_PROPORTION_MEDIATED: language.Words = {
    "zh": "中介占比", "en": "proportion mediated"}
_CDE_PARTS = (
    ("reference_control",
     {"zh": "控制直接效应 CDE（中介固定在参考值）",
      "en": "controlled direct effect CDE (mediator held at its reference "
            "value)"}),
    ("reference_treated",
     {"zh": "控制直接效应 CDE（中介固定在处理值）",
      "en": "controlled direct effect CDE (mediator held at its treated "
            "value)"}),
)


def _render_mediation_decomposition(ne: dict, result: dict, *,
                                    lang: language.Lang | str) -> str:
    """Total effect split into what runs through the mediator and what does not."""
    d = ne.get("decomposition") or {}
    lines = [language.fill(_DECOMPOSITION, lang)]
    for key, label in _DECOMPOSITION_PARTS:
        band = _band(d.get(key), lang=lang)
        if band:
            lines.append(language.fill(
                _LABELLED_ROW, lang, label=language.fill(label, lang),
                value=band))
    pm = _band(d.get("proportion_mediated"), lang=lang)
    if pm:
        lines.append(language.fill(
            _LABELLED_ROW, lang,
            label=language.fill(_PROPORTION_MEDIATED, lang), value=pm))
    cde = d.get("cde") or {}
    for key, label in _CDE_PARTS:
        band = _band(cde.get(key), lang=lang)
        if band:
            lines.append(language.fill(
                _LABELLED_ROW, lang, label=language.fill(label, lang),
                value=band))
    lines.extend(_estimate_meta(ne, result.get("outcome_error"), lang=lang))
    return "\n".join(lines)


_JOINT_CONTRAST: language.Words = {
    "zh": "**联合干预对比**", "en": "**Joint-intervention contrast**"}
_JOINT_CORNERS: language.Words = {
    "zh": "（{treated} 对比 {control}）",
    "en": " ({treated} against {control})",
}
_JOINT_HEAD: language.Words = {
    "zh": "**联合干预对比**{corners}：{band}",
    "en": "**Joint-intervention contrast**{corners}: {band}",
}
_SCALE_DIFFERENCE: language.Words = {"zh": "差值", "en": "difference"}
_INTERACTION: language.Words = {
    "zh": "- {order} 阶交互（{scale} 尺度）：{band} —— "
          "各处理一起上，比各自效应之和多出来的部分",
    "en": "- Order-{order} interaction (on the {scale} scale): {band} — "
          "what giving the treatments together adds over the sum of their "
          "separate effects",
}
_INTERACTION_UNAVAILABLE: language.Words = {
    "zh": "- {order} 阶交互**给不出**：{reason}",
    "en": "- The order-{order} interaction is **not available**: {reason}",
}
#: WHICH way the K-way interaction went missing. The contrast survives both,
#: so both are a withholding rather than a refusal — but what a reader does
#: next differs, which is why this is two words and not one sentence: supply
#: the missing cell, or ask about fewer treatments at once.
_INTERACTION_UNAVAILABLE_WORDS: dict[str, language.Words] = {
    "corner_unsupported": {
        "zh": "这个有限差分要在处理的每一个取值组合上都站得住，而 {cells} "
              "上没有任何一行数据。上面那个对比不受影响——它取在全处理格与"
              "全对照格之间，两者都有观测——但交互项没法与在空格子上凭空"
              "补出来的东西分开。",
        "en": "the finite difference has to stand on every combination of "
              "treatment levels, and {cells} has no rows at all. The "
              "contrast above is unaffected — it is taken between the "
              "all-treated and all-control cells, both of them observed — "
              "but the interaction cannot be told apart from what gets "
              "made up on an empty cell.",
    },
    "order_above_cap": {
        "zh": "这个有限差分要走遍处理的每一个取值组合，而处理超过 {cap} 个时"
              "不做这趟枚举，所以没有走。上面那个对比不受影响——它只要两个"
              "格子。数据也许撑得住每一个组合，只是没有人去看。",
        "en": "the finite difference walks every combination of treatment "
              "levels, and past {cap} treatments that walk is not taken — "
              "so it was not. The contrast above is unaffected: it needs "
              "two cells. The data may well support every combination; "
              "nobody looked.",
    },
}


def _render_joint_contrast(ne: dict, result: dict, *,
                           lang: language.Lang | str) -> str:
    """The contrast between two joint corners, plus what riding together adds."""
    joint = ne.get("joint_effect") or {}
    lines = []
    band = _band(joint, lang=lang)
    corners = ""
    treated, control = joint.get("treated") or {}, joint.get("control") or {}
    if treated and control:
        corners = language.fill(_JOINT_CORNERS, lang,
                                treated=_corner(treated),
                                control=_corner(control))
    lines.append(language.fill(_JOINT_HEAD, lang, corners=corners, band=band)
                 if band else language.fill(_JOINT_CONTRAST, lang))

    inter = ne.get("interaction")
    if inter and inter.get("point") is not None:
        lines.append(language.fill(
            _INTERACTION, lang, order=inter.get("order"),
            scale=(inter.get("scale")
                   or language.fill(_SCALE_DIFFERENCE, lang)),
            band=_band(inter, lang=lang)))
    unavailable = ne.get("interaction_unavailable")
    if unavailable:
        lines.append(language.fill(
            _INTERACTION_UNAVAILABLE, lang,
            order=unavailable.get("order", ""),
            reason=_interaction_missing(unavailable, lang=lang)))
    lines.extend(_estimate_meta(ne, result.get("outcome_error"), lang=lang))
    return "\n".join(lines)


def _interaction_missing(block: dict, *, lang: language.Lang | str) -> str:
    """Which way the interaction went missing, said in the reader's language.

    The kernel records the species and the facts behind it; the sentence is
    made here, where the language is known. Both species get the same two
    facts offered — the cells for one, the cap for the other — because a
    slot the sentence does not name costs nothing and a missing one shows.
    """
    # A member of a closed vocabulary is a string; read as one here so the
    # table is asked in its own terms rather than in the envelope's.
    kind = str(block.get("kind") or "")
    words = _INTERACTION_UNAVAILABLE_WORDS.get(kind)
    if words is None:
        # A species this build has no sentence for: hand back the stand-in
        # the glossary gives rather than raising, which would take the whole
        # report down over one line of it.
        return language.gloss(_INTERACTION_UNAVAILABLE_WORDS, kind, lang)
    return language.fill(
        words, lang,
        cells=language.listing(
            (_corner(cell) for cell in block.get("unsupported_cells") or ()),
            lang),
        cap=block.get("cap", ""),
    )


def _corner(corner: dict) -> str:
    return "{" + ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(corner.items())) + "}"


_WAS_TREATED: language.Words = {
    "zh": "实际接受了处理", "en": "did receive the treatment"}
_WAS_UNTREATED: language.Words = {
    "zh": "实际没接受处理", "en": "did not receive the treatment"}
_AND_OUTCOME_OCCURRED: language.Words = {
    "zh": "、且结局发生了", "en": " and whose outcome occurred"}
_AND_OUTCOME_DID_NOT: language.Words = {
    "zh": "、且结局没发生", "en": " and whose outcome did not occur"}
_HAD_TREATED: language.Words = {
    "zh": "若当初接受了处理", "en": "had they received the treatment"}
_HAD_UNTREATED: language.Words = {
    "zh": "若当初没接受处理", "en": "had they not received the treatment"}
_THEN_OCCURS: language.Words = {
    "zh": "结局会发生", "en": "the outcome would occur"}
_THEN_DOES_NOT: language.Words = {
    "zh": "结局不会发生", "en": "the outcome would not occur"}
_CELL_QUESTION: language.Words = {
    "zh": "在**{was}**的那些个体里，**{instead}，{then}**的概率",
    "en": "Among the individuals who **{was}**, the probability that "
          "**{instead}, {then}**",
}


def _counterfactual_cell_question(cell: dict, *,
                                  lang: language.Lang | str) -> str:
    """Which counterfactual this interval is an interval ON.

    Four booleans say it — the factual treatment, the factual outcome when
    there is one, the intervened value and the outcome asked about — and the
    line above them used to open with "该反事实格", which names no cell. An
    interval on an unnamed quantity is not an answer a reader can check
    against the question they asked, and the four differ by exactly the
    substitutions that change what the number means.
    """
    was = language.fill(_WAS_TREATED if cell.get("observed_x")
                        else _WAS_UNTREATED, lang)
    factual = cell.get("factual_y")
    if factual is not None:
        was += language.fill(_AND_OUTCOME_OCCURRED if factual
                             else _AND_OUTCOME_DID_NOT, lang)
    instead = language.fill(_HAD_TREATED if cell.get("counterfactual_x")
                            else _HAD_UNTREATED, lang)
    then = language.fill(_THEN_OCCURS if cell.get("target_y")
                         else _THEN_DOES_NOT, lang)
    return language.fill(_CELL_QUESTION, lang, was=was, instead=instead,
                         then=then)


_CELL_INTERVAL: language.Words = {
    "zh": "{question}——**区间** [{lower}, {upper}]（界，不是点）",
    "en": "{question} — an **interval** [{lower}, {upper}] (bounds, not a "
          "point)",
}
_CELL_NO_BOUNDS: language.Words = {
    "zh": "该反事实格没有给出可呈现的界。",
    "en": "No bounds on this counterfactual cell can be shown.",
}
_NOTE_ROW: language.Words = {"zh": "- {note}", "en": "- {note}"}
_CELL_ADJUSTMENT: language.Words = {
    "zh": "- 干预风险经后门调整集 {variables} 识别",
    "en": "- The interventional risk is identified through the back-door "
          "adjustment set {variables}",
}
_CELL_RISK: language.Words = {
    "zh": "- 这一格用到的那个干预风险 P(结局 | do(处理)) = {risk}",
    "en": "- The one interventional risk this cell uses: "
          "P(outcome | do(treatment)) = {risk}",
}
_CELL_IF_MONOTONE: language.Words = {
    "zh": "- 若可假设单调性（X 从不阻止 Y），这一格会被收紧——"
          "在干预风险已知时收紧成一个点。",
    "en": "- If monotonicity can be assumed (X never prevents Y), this cell "
          "narrows — to a point, where the interventional risks are known.",
}
#: The cell's resampled band, and the pair of keys it arrives in. This
#: section printed the identified interval and dropped the band, so the one
#: number saying how much of the width is THIS sample never reached the
#: report at all — which is why the field naming its kind had no reader
#: here to add it to (#419).
_CELL_CI = intervals.pair_at(
    "numeric_estimate.counterfactual_cell", "ci_lower", "ci_upper")
_CELL_BAND_ROW: language.Words = {
    "zh": "- {band} [{lower}, {upper}]",
    "en": "- {band} [{lower}, {upper}]",
}
_CELL_REFUTED: language.Words = {
    "zh": "- **{share}% 的重抽样在所声明的单调性下无解** —— "
          "单调性一般被当作不可检验的假设，而这份数据已经在往推翻它的"
          "方向推；这个比例越高，上面那个区间越不该照单全收",
    "en": "- **{share}% of the resamples have no feasible solution under the "
          "declared monotonicity** — monotonicity is usually called "
          "untestable, and these data are already pushing towards refuting "
          "it; the higher this share, the less the interval above should be "
          "taken at face value",
}


def _render_counterfactual_cell_bounds(ne: dict, result: dict, *,
                                       lang: language.Lang | str) -> str:
    """Bounds on one counterfactual cell.

    WHY it is an interval is read off the licence rather than asserted. It
    used to be stated as "no monotonicity was assumed", which is one of the
    reasons and was the only one for as long as one solver could produce this
    block; a cell bounded over an instrument's response polytope is an
    interval because no interventional risk is point-identified, and a
    declared monotonicity narrows it without pinning it.
    """
    cell = ne.get("counterfactual_cell") or {}
    lo, hi = cell.get("lower"), cell.get("upper")
    lines = []
    if lo is not None and hi is not None:
        lines.append(language.fill(
            _CELL_INTERVAL, lang,
            question=_counterfactual_cell_question(cell, lang=lang),
            lower=_fmt(lo), upper=_fmt(hi)))
    else:
        lines.append(language.fill(_CELL_NO_BOUNDS, lang))
    ci_lo, ci_hi = cell.get("ci_lower"), cell.get("ci_upper")
    if ci_lo is not None and ci_hi is not None:
        width, said = intervals.width_or_unstated(_CELL_CI, cell)
        lines.append(language.fill(
            _CELL_BAND_ROW, lang, band=language.fill(said, lang),
            lower=_fmt(ci_lo), upper=_fmt(ci_hi)))
        if width is not None:
            lines.append(language.fill(
                _NOTE_ROW, lang,
                note=language.fill(_WIDTH_IS, lang,
                                   advice=language.fill(width.advice, lang))))
    prov = cell.get("interventional_risk_provenance")
    if prov:
        note = risk_provenance.describe(prov, lang)
        if cell.get("instrument"):
            note += language.fill(_INSTRUMENT_IS, lang,
                                  name=cell["instrument"])
        lines.append(language.fill(_NOTE_ROW, lang, note=note))
    adj = cell.get("adjustment")
    if adj:
        lines.append(language.fill(_CELL_ADJUSTMENT, lang,
                                   variables=_vars(adj)))
    # The one interventional arm this cell leans on, when it leans on one.
    # Null is not absence of information here: it is the statement that the
    # answer came out of the response-function program instead, which the
    # provenance line above has just said.
    risk = cell.get("p_y_do_x_cf")
    if risk is not None:
        lines.append(language.fill(_CELL_RISK, lang, risk=_fmt(risk)))
    if not cell.get("monotonicity"):
        lines.append(language.fill(_CELL_IF_MONOTONE, lang))
    # Not a diagnostic. A share of the resamples with NO feasible solution
    # under the declared monotonicity is a finite-sample measure of how close
    # that assumption is to being refuted by this data, and monotonicity is
    # the one usually described as untestable. Counted and reported rather
    # than silently skipped — and then said only by the detachable explainer.
    refuted = cell.get("bootstrap_draws_infeasible") or 0
    used = cell.get("bootstrap_draws_used") or 0
    if refuted and used + refuted:
        lines.append(language.fill(
            _CELL_REFUTED, lang,
            share=_fmt(100.0 * refuted / (used + refuted))))
    lines.extend(_estimate_meta(ne, result.get("outcome_error"), lang=lang))
    return "\n".join(lines)


def _render_causation_estimate(ne: dict, result: dict, *,
                               lang: language.Lang | str) -> str:
    """Both causation shapes, from the one renderer that says the names.

    Bound twice on purpose. Point-identified and bounded are two shapes of
    the same three quantities, and what separates them — a point inside
    each — is exactly what the renderer already keys off, so a second copy
    would be a second chance to say them differently.
    """
    return "\n".join(
        [_render_causation(ne["probabilities_of_causation"],
                           ci_level=ne.get("ci_level"), lang=lang)]
        + _estimate_meta(ne, result.get("outcome_error"), lang=lang)
    )


# Each shape, said once. ``bind`` refuses a set that misses one, so a shape
# added to the vocabulary cannot reach this surface and render nothing.
_ANSWER_RENDERERS = answers.bind({
    answers.POINT:
        lambda ne, result, *, lang: _render_numeric_estimate(
            ne, result.get("outcome_error"), lang=lang),
    answers.DOSE_RESPONSE_CURVE: _render_dose_response_curve,
    answers.MEDIATION_DECOMPOSITION: _render_mediation_decomposition,
    answers.JOINT_CONTRAST: _render_joint_contrast,
    answers.COUNTERFACTUAL_CELL_BOUNDS: _render_counterfactual_cell_bounds,
    answers.CAUSATION_POINTS: _render_causation_estimate,
    answers.CAUSATION_BOUNDS: _render_causation_estimate,
})


# --- the answer, when it is a block rather than an estimate -------------------
#
# Two query kinds are answered from theta alone: probabilities of
# causation come out of the joint distribution and the two interventional
# risks, and a linear-SCM counterfactual comes out of the equations by
# abduction. Neither calls an estimator, so neither leaves a
# ``numeric_estimate`` for an answer shape to describe, and each puts what
# it found in a block.
#
# The report reached past both to ``numeric_result``, which holds one
# number because a headline has to. For a counterfactual that number is
# the answer. For causation it is PN, one of three named quantities, and
# the answer section printed it with no name at all — under a question
# line that had just asked for all three.
#
# The same sentence turned out to be true of the DATA path, which does
# leave a ``numeric_estimate``: its method declared ``point`` for the
# monotone mode, so the sharper answer rendered as a bare headline while
# the blunter one named all three. Both paths now reach
# :func:`_render_causation`.


def _answer_causation(block: dict, result: dict, *,
                      lang: language.Lang | str) -> str:
    """The theta path's three quantities, said the way the data path says
    them — the block and the estimate carry the same envelope."""
    return _render_causation(block, lang=lang)


_SCM_VALUE: language.Words = {
    "zh": "**{value}**　（{target}，在该个体自身的外生扰动下）",
    "en": "**{value}**  ({target}, under this individual's own exogenous "
          "noise)",
}
_ABDUCTED_NOISE: language.Words = {
    "zh": "- 从观测值反推出的个体扰动：{items}",
    "en": "- The individual noise abduced from the observations: {items}",
}
_OTHER_COUNTERFACTUAL_VALUES: language.Words = {
    "zh": "- 同一反事实世界下的其他变量：{items}",
    "en": "- The other variables in the same counterfactual world: {items}",
}


def _answer_scm_counterfactual(block: dict, result: dict, *,
                               lang: language.Lang | str) -> str:
    """The counterfactual value, and the abduction that produced it.

    The value is also in ``numeric_result`` and the branch below would
    print it. What only this block has is the middle step: the noise
    abducted from what was actually observed is what makes the answer a
    counterfactual for THIS unit rather than a prediction for an average
    one, and it is the part a reader can check against the observations
    they supplied.
    """
    value = block.get("target_value")
    if value is None:
        return ""
    target = block.get("target") or "?"
    lines = [language.fill(_SCM_VALUE, lang, value=_fmt(value),
                           target=target)]

    joiner = language.fill(language.BETWEEN_CLAUSES, lang)
    noise = block.get("abducted_noise") or {}
    if noise:
        items = joiner.join(
            f"U_{name}={_fmt(v)}" for name, v in sorted(noise.items())
        )
        lines.append(language.fill(_ABDUCTED_NOISE, lang, items=items))
    cf = block.get("counterfactual_values") or {}
    others = {k: v for k, v in cf.items() if k != target}
    if others:
        items = joiner.join(f"{k}={_fmt(v)}" for k, v in sorted(others.items()))
        lines.append(language.fill(_OTHER_COUNTERFACTUAL_VALUES, lang,
                                   items=items))
    return "\n".join(lines)


#: What the region says about the vector as a whole. The four are a
#: partition of "did the data pin this down", and the reader needs the
#: distinction before any number: a bounded region and an unbounded one both
#: come with per-coefficient intervals, and only in the first case is every
#: one of them finite.
_REGION_SHAPE_WORDS = {
    "bounded": {
        "zh": "**数据把整组系数都框住了**（置信域有界）",
        "en": "**the data pin the whole coefficient vector down** (the "
              "region is bounded)",
    },
    "unbounded": {
        "zh": "**有方向是数据约束不了的**（置信域无界）——这些工具变量在"
              "那个方向上说不出话，不是算错了",
        "en": "**some direction is left unconstrained** (the region is "
              "unbounded) — these instruments say nothing along it, which "
              "is a fact about them and not an error",
    },
    "whole_space": {
        "zh": "**这些工具变量什么也没排除**（置信域是整个空间）",
        "en": "**nothing at all is ruled out** (the region is the whole "
              "space)",
    },
    "empty": {
        "zh": "**没有任何一组系数能通过检验**——在这个水平上，数据否掉了"
              "「这些工具有效 + 结果方程线性」这套假设本身",
        "en": "**no coefficient vector survives the test** — at this level "
              "the data refute the premise itself: these instruments being "
              "valid together with a linear outcome equation",
    },
}
_REGION_HEAD: language.Words = {
    "zh": "**{level}% Anderson-Rubin 置信域**（对 {variables} 这一组系数）："
          "{shape}",
    "en": "**{level}% Anderson-Rubin confidence region** for the "
          "coefficients on {variables}: {shape}",
}
_REGION_PROJECTION: language.Words = {
    "zh": "- `{treatment}`：{interval}",
    "en": "- `{treatment}`: {interval}",
}
_REGION_PROJECTION_NOTE: language.Words = {
    "zh": "- 上面每一行是把整个域投到那一个系数上得到的区间——单看一行是"
          "**保守**的（覆盖率不低于名义水平），域本身才是这些系数的联合陈述",
    "en": "- Each line above is the whole region projected onto that one "
          "coefficient — read alone it is **conservative** (it covers at "
          "least as often as the nominal level), and the region is the "
          "joint statement",
}
_REGION_POINT: language.Words = {
    "zh": "- 二阶段最小二乘点估计：{items}（这些工具足以定出它；它不必落"
          "在域内，落不进去说明过度识别约束被数据拉紧了）",
    "en": "- The two-stage least-squares point: {items} (these instruments "
          "determine one; it need not lie inside the region, and when it "
          "does not the over-identifying restrictions are strained)",
}
_REGION_WEAK_OK: language.Words = {
    "zh": "- 这个域的覆盖率与第一阶段强弱无关：工具弱会让它变大，不会让它变错",
    "en": "- The region's coverage does not depend on first-stage strength: "
          "weak instruments make it larger, not wrong",
}


def _interval_words(kind: str, lower, upper, *,
                    lang: language.Lang | str) -> str:
    """One coordinate's projection, as the reader reads intervals here."""
    lo = "-∞" if lower is None else _fmt(lower)
    hi = "+∞" if upper is None else _fmt(upper)
    if kind == "empty":
        return language.fill(_REGION_EMPTY_INTERVAL, lang)
    if kind == "whole_line":
        return "(-∞, +∞)"
    if kind == "disconnected":
        return f"(-∞, {lo}] ∪ [{hi}, +∞)"
    return f"[{lo}, {hi}]"


_REGION_EMPTY_INTERVAL: language.Words = {
    "zh": "空（无解）", "en": "empty (no value survives)"}


def _answer_anderson_rubin_region(block: dict, result: dict, *,
                                  lang: language.Lang | str) -> str:
    """The region, its shape, and one projected interval per coefficient.

    The shape comes first because it is the part that decides how to read
    everything after it — a projection reported without it looks like an
    ordinary confidence interval, and for an unbounded region that reading
    is wrong in the direction that matters.
    """
    region = block.get("region") or {}
    shape = region.get("shape")
    if shape is None:
        return ""
    level = int(round(float(region.get("ci_level") or 0.0) * 100))
    out = [language.fill(
        _REGION_HEAD, lang, level=level,
        variables=_vars(region.get("treatments") or ()),
        shape=language.gloss(_REGION_SHAPE_WORDS, shape, lang))]
    for p in region.get("projections") or ():
        out.append(language.fill(
            _REGION_PROJECTION, lang, treatment=p.get("treatment"),
            interval=_interval_words(
                p.get("kind") or "", p.get("lower"), p.get("upper"), lang=lang)))
    if region.get("projections"):
        out.append(language.fill(_REGION_PROJECTION_NOTE, lang))
    point = region.get("point")
    if point:
        joiner = language.fill(language.BETWEEN_CLAUSES, lang)
        items = joiner.join(
            f"{name}={_fmt(v)}"
            for name, v in zip(region.get("treatments") or (), point))
        out.append(language.fill(_REGION_POINT, lang, items=items))
    out.append(language.fill(_REGION_WEAK_OK, lang))
    return "\n".join(out)


# Each block of this family that no other channel carries, said once.
_ANSWER_BLOCK_RENDERERS = blocks.bind(blocks.Family.ANSWER, {
    blocks.Block.ANDERSON_RUBIN_REGION: _answer_anderson_rubin_region,
    blocks.Block.CAUSATION: _answer_causation,
    blocks.Block.SCM_COUNTERFACTUAL: _answer_scm_counterfactual,
})


# --- how it was computed ------------------------------------------------------
#
# The report had six sections and none of them was "how the answer was
# arrived at". Ten blocks exist to say exactly that — 369 of them across
# one suite run — and this file read exactly one extensions key, so not
# one of them ever reached a reader. The two FIRST-CLASS provenance
# fields fared no better: the footer said "估计式已生成（机器可读，见
# ``result.formula``）" and the verification section said the derivation
# has N steps. Two independent channels failing the same way is what
# says the missing thing is downstream of both — the section, not the
# renderers. ``scheduler`` had already written for it: the comment above
# the block it emits calls ``extensions["identification"]`` "the human
# surface", for "a renderer keying off" it that did not exist.


def _vars(names) -> str:
    """A set of variables, the way a reader reads one."""
    items = [str(n) for n in (names or ())]
    return "{" + ", ".join(items) + "}"


def _atoms(entries) -> str:
    """A set written as ``{predicate, args}`` objects, by predicate."""
    return _vars([(e or {}).get("predicate", "?") for e in (entries or ())])


_PATTERN_WORDS = {
    "backdoor": {"zh": "后门调整", "en": "back-door adjustment"},
    "front_door": {"zh": "前门调整", "en": "front-door adjustment"},
    "c_factor": {"zh": "ID 算法的一般解（c-factor 分解）",
                 "en": "the ID algorithm's general solution (c-factor "
                       "decomposition)"},
    "instrumental_variable": {"zh": "工具变量", "en": "an instrumental variable"},
}
"""What each recognised pattern is called for a reader.

An unlisted pattern renders as its own token rather than falling to a
default: this section exists because something said nothing, and a name a
reader has to look up still beats a sentence that omits it. The producer
(``scheduler._recognize_identification_pattern``) emits the first three;
the IV path writes the fourth.
"""


#: A gloss over one closed vocabulary of failed conditions. Positional,
#: unlike the renderers above — this is the shape every registered gloss
#: answers, and it is the registry that fixes it.
_ConditionWord = Callable[[str, "language.Lang | str"], str]

_ROUTE_PATTERN: language.Words = {
    "zh": "- **识别模式**：{pattern}",
    "en": "- **Identification pattern**: {pattern}",
}
_CONTROL_FOR: language.Words = {
    "zh": " —— 控制 {variables}", "en": " — control for {variables}"}
_NOTHING_TO_CONTROL: language.Words = {
    "zh": " —— 无需控制任何变量：图里没有开放的后门路径",
    "en": " — nothing needs controlling: the graph has no open back-door path",
}
_VIA_MEDIATOR: language.Words = {
    "zh": " —— 经中介 {variables}",
    "en": " — through the mediator {variables}",
}
_VIA_INSTRUMENT: language.Words = {
    "zh": " —— 工具 `{name}`", "en": " — instrument `{name}`"}
_VALID_GIVEN: language.Words = {
    "zh": "，在 {variables} 条件下有效", "en": ", valid given {variables}"}
_QUESTION_CONDITIONED_ON: language.Words = {
    "zh": "；问题本身条件于 {variables}",
    "en": "; the question itself is conditional on {variables}",
}
_IDC_RATIO: language.Words = {
    "zh": "（条件估计量，走 IDC 比值而非单纯调整）",
    "en": " (a conditional estimand — an IDC ratio rather than plain "
          "adjustment)",
}
_POINT_ALSO_NEEDS: language.Words = {
    "zh": "。点识别另需：{assumption}",
    "en": ". Point identification also needs: {assumption}",
}


def _route_identification(block: dict, result: dict, *,
                          lang: language.Lang | str) -> str:
    pattern = block.get("pattern", "?")
    line = language.fill(
        _ROUTE_PATTERN, lang,
        pattern=language.gloss(_PATTERN_WORDS, pattern, lang))
    if pattern == "backdoor":
        adj = block.get("adjustment_set")
        line += (language.fill(_CONTROL_FOR, lang, variables=_vars(adj))
                 if adj else language.fill(_NOTHING_TO_CONTROL, lang))
    elif pattern == "front_door":
        line += language.fill(_VIA_MEDIATOR, lang,
                              variables=_vars(block.get("mediator_set")))
    elif pattern == "instrumental_variable":
        line += language.fill(_VIA_INSTRUMENT, lang,
                              name=block.get("instrument", "?"))
        cond = block.get("conditioning")
        if cond:
            line += language.fill(_VALID_GIVEN, lang, variables=_vars(cond))
    if block.get("conditioned_on"):
        line += language.fill(_QUESTION_CONDITIONED_ON, lang,
                              variables=_vars(block["conditioned_on"]))
    if block.get("estimand") == "conditional_idc_ratio":
        line += language.fill(_IDC_RATIO, lang)
    if block.get("required_assumption"):
        line += language.fill(_POINT_ALSO_NEEDS, lang,
                              assumption=block["required_assumption"])
    return line


_IV_ALTERNATIVES: language.Words = {
    "zh": "图中共有 {count} 个候选工具，取的是这一个",
    "en": "the graph holds {count} candidate instruments, and this is the "
          "one taken",
}
_IV_HEAD: language.Words = {
    "zh": "- **工具变量**：{said}",
    "en": "- **Instrumental variable**: {said}",
}
_SUB_ROW: language.Words = {"zh": "  - {said}", "en": "  - {said}"}


def _route_iv_identification(block: dict, result: dict, *,
                             lang: language.Lang | str) -> str:
    """What the IV block knows that the pattern line does not.

    Its ``strategy`` / ``instrument`` / ``conditioning`` /
    ``required_assumption`` are written twice on purpose: the producer
    copies them into ``identification`` and calls that copy "the human
    surface". So the instrument is stated here only when no pattern line
    will state it — the numeric IV path emits this block alone — and
    otherwise this contributes the two facts that live nowhere else, that
    a choice was made among candidates and that a Wald ratio answers for
    compliers rather than for everyone.

    A renderer declining to repeat what another block on the same
    envelope already said is why the signature takes the whole result.
    Saying nothing is a legitimate outcome, and an empty line is dropped
    rather than printed as a bullet with a heading and no content.
    """
    already_said = (
        ((result.get("extensions") or {}).get(blocks.Block.IDENTIFICATION) or {})
        .get("pattern") == "instrumental_variable"
    )
    parts: list[str] = []
    if not already_said:
        head = f"`{block.get('instrument', '?')}`"
        cond = block.get("conditioning")
        if cond:
            head += language.fill(_VALID_GIVEN, lang, variables=_vars(cond))
        parts.append(head)
    n = block.get("alternatives_count")
    if isinstance(n, int) and n > 1:
        parts.append(language.fill(_IV_ALTERNATIVES, lang, count=n))
    caveat = block.get("late_caveat")
    if not parts and not caveat:
        return ""
    said = (language.fill(language.BETWEEN_STATEMENTS, lang).join(parts) if parts
            else str(caveat))
    out = [language.fill(_IV_HEAD, lang, said=said)]
    if parts and caveat:
        out.append(language.fill(_SUB_ROW, lang, said=caveat))
    return "\n".join(out)


_FEEDBACK_HEAD: language.Words = {
    "zh": "- **互为因果**：`{left}` 与 `{right}` 被声明为互相影响，"
          "干预之后这个环仍然影响结果",
    "en": "- **Reciprocal causation**: `{left}` and `{right}` were declared "
          "to move each other, and the loop still reaches the outcome after "
          "the intervention",
}
_FEEDBACK_WITHDREW: language.Words = {
    "zh": "所以调整类的路线在这里都不成立（调整是堵住一条路，而处理变量"
          "自己参与的反馈不是一条可以堵的路），报出来的数走的是工具变量",
    "en": "so the adjustment routes do not hold here — controlling for a "
          "covariate blocks a path, and a feedback the treatment is part of "
          "is not a path to block — and the number comes through an "
          "instrument instead",
}


def _route_feedback_loop(block: dict, result: dict, *,
                         lang: language.Lang | str) -> str:
    """Why the answer beside this took the route it did.

    The block that says an ordinary answer was NOT given. Without it a
    reader sees an instrumental-variable estimate on a graph whose
    back-door set is plainly sitting there, and has no way to learn that
    the set was withdrawn rather than overlooked.
    """
    left, right = block.get("left"), block.get("right")
    if not left or not right:
        return ""
    out = [language.fill(_FEEDBACK_HEAD, lang, left=left, right=right)]
    if block.get("reduction") == "simultaneous_equations":
        out.append(language.fill(
            _SUB_ROW, lang, said=language.fill(_FEEDBACK_WITHDREW, lang)))
    return "\n".join(out)


_SOURCE_POPULATION: language.Words = {
    "zh": "源总体", "en": "the source population"}
_TARGET_POPULATION: language.Words = {
    "zh": "目标总体", "en": "the target population"}
_TRANSPORT_HEAD: language.Words = {
    "zh": "- **跨总体迁移**：目标总体是 `{target}`",
    "en": "- **Transport across populations**: the target population is "
          "`{target}`",
}
_TRANSPORT_FROM: language.Words = {
    "zh": "\n  - 从 `{source}` 迁：",
    "en": "\n  - from `{source}`: ",
}
_TRANSPORT_S_NODES: language.Words = {
    "zh": "与目标分布不同的是 {variables}，",
    "en": "what is distributed differently from the target is {variables}, ",
}
_TRANSPORT_REWEIGHT: language.Words = {
    "zh": "靠 {variables} 上的重加权抹平",
    "en": "evened out by reweighting on {variables}",
}
_TRANSPORT_NO_REWEIGHT: language.Words = {
    "zh": "不必重加权，效应原样搬得过来",
    "en": "no reweighting needed — the effect carries over unchanged",
}
# What this one domain carried the effect to. Said per domain and not only
# once at the end, because when the domains disagree no single number is
# reported at all and these are the whole of the evidence for that.
_TRANSPORT_ROUTE_VALUE: language.Words = {
    "zh": "，算出来是 {value}",
    "en": ", which comes to {value}",
}
_TRANSPORT_BLOCKED_WORDS: dict[str, language.Words] = {
    "treatment_or_outcome_off_diagram": {
        "zh": "搬不过来——处理或结局根本不在这个源总体的选择图上",
        "en": "does not carry over — the treatment or the outcome is not on "
              "this source domain's selection diagram at all",
    },
    "no_s_admissible_set": {
        "zh": "搬不过来——没有哪个调整集能抹平它与目标总体的差别",
        "en": "does not carry over — no adjustment set evens out its "
              "difference from the target population",
    },
}


def _route_transport_identification(block: dict, result: dict, *,
                                    lang: language.Lang | str) -> str:
    """One line per source domain, because each one is its own diagram.

    A transport question has one target population and any number of source
    domains. What shifts between a given source and the target — and so what
    has to be re-weighted, or why nothing suffices — is that domain's own
    fact, and folding the domains into a single sentence would state one
    domain's answer as if it were every domain's.
    """
    tgt = (block.get("target_population")
           or language.fill(_TARGET_POPULATION, lang))
    line = language.fill(_TRANSPORT_HEAD, lang, target=tgt)
    # Which variable a selection node sits on is declared once, on the node;
    # a route names its nodes by id, so the shift is looked up rather than
    # carried twice.
    shifts = {
        sn.get("id"): (sn.get("affects") or {}).get("predicate", "?")
        for sn in (block.get("s_nodes") or ())
    }
    for route in (block.get("sources") or ()):
        src = (route.get("source_population")
               or language.fill(_SOURCE_POPULATION, lang))
        line += language.fill(_TRANSPORT_FROM, lang, source=src)
        shifted = [shifts[i] for i in (route.get("s_nodes") or ())
                   if i in shifts]
        if shifted:
            line += language.fill(_TRANSPORT_S_NODES, lang,
                                  variables=_vars(shifted))
        if not route.get("transportable"):
            kind = str(route.get("blocked_by") or "")
            words = _TRANSPORT_BLOCKED_WORDS.get(kind)
            line += (language.fill(words, lang) if words is not None
                     else language.gloss(_TRANSPORT_BLOCKED_WORDS, kind, lang))
            continue
        adj = route.get("adjustment_set")
        line += (language.fill(_TRANSPORT_REWEIGHT, lang, variables=_atoms(adj))
                 if adj else language.fill(_TRANSPORT_NO_REWEIGHT, lang))
        nm = route.get("numeric")
        if isinstance(nm, dict):
            line += language.fill(_TRANSPORT_ROUTE_VALUE, lang,
                                  value=_fmt(nm.get("value")))
    return line


_JOINT_ROUTE_HEAD: language.Words = {
    "zh": "- **联合干预**：同时干预 {variables}",
    "en": "- **Joint intervention**: intervening on {variables} together",
}
_JOINT_GENERAL_ID: language.Words = {
    "zh": "，无可用调整集，由集合版 ID 算法识别",
    "en": ", with no usable adjustment set — identified by the set-valued ID "
          "algorithm",
}
_JOINT_ADJUSTED: language.Words = {
    "zh": "，经联合后门调整集 {variables} 识别",
    "en": ", identified through the joint back-door adjustment set "
          "{variables}",
}
_JOINT_NO_ADJUSTMENT: language.Words = {
    "zh": "，联合后门无需调整",
    "en": ", and the joint back door needs no adjustment",
}
_CONDITIONED_ON: language.Words = {
    "zh": "；条件于 {variables}", "en": "; conditional on {variables}"}
_JOINT_INTERACTION: language.Words = {
    "zh": "。交互项在差值尺度上给出 —— 逐个单独干预再相加是拿不到它的",
    "en": ". The interaction is given on the difference scale — intervening "
          "on each separately and adding does not reach it",
}


def _route_joint_identification(block: dict, result: dict, *,
                                lang: language.Lang | str) -> str:
    line = language.fill(_JOINT_ROUTE_HEAD, lang,
                         variables=_vars(block.get("treatments")))
    if block.get("pattern") == "joint_general_id":
        line += language.fill(_JOINT_GENERAL_ID, lang)
    else:
        adj = block.get("adjustment_set")
        line += (language.fill(_JOINT_ADJUSTED, lang, variables=_vars(adj))
                 if adj else language.fill(_JOINT_NO_ADJUSTMENT, lang))
    if block.get("conditioned_on"):
        line += language.fill(_CONDITIONED_ON, lang,
                              variables=_vars(block["conditioned_on"]))
    if block.get("interaction"):
        line += language.fill(_JOINT_INTERACTION, lang)
    return line


_LONGITUDINAL_HEAD: language.Words = {
    "zh": "- **时变处理（g-formula）**：处理序列 {sequence} 对 `{outcome}`",
    "en": "- **Time-varying treatment (g-formula)**: the treatment sequence "
          "{sequence} on `{outcome}`",
}
_EMPTY_SEQUENCE: language.Words = {"zh": "（空）", "en": "(empty)"}
_CONFOUNDERS_BY_TIME: language.Words = {
    "zh": "；各时点已测混杂 {variables}",
    "en": "; the measured confounders at each time are {variables}",
}
_SEQUENTIAL_EXCHANGEABILITY: language.Words = {
    "zh": "  - 序贯可交换性成立：每个时点的处理，其后门路径都被此前测到的"
          "历史挡住了",
    "en": "  - Sequential exchangeability holds: at every time point the "
          "treatment's back-door paths are blocked by the history measured "
          "before it",
}
_SEQUENTIAL_EXCHANGEABILITY_FAILS: language.Words = {
    "zh": "  - 序贯可交换性**不成立**：某个时点的处理还有历史挡不住的后门路径，"
          "g-formula 会给出有偏的数",
    "en": "  - Sequential exchangeability **does not hold**: at some time "
          "point the treatment still has a back-door path the history does "
          "not block, and the g-formula returns a biased number",
}


def _route_longitudinal_identification(block: dict, result: dict, *,
                                       lang: language.Lang | str) -> str:
    treatments = [str(t) for t in (block.get("treatments") or ())]
    line = language.fill(
        _LONGITUDINAL_HEAD, lang,
        sequence=(" → ".join(f"`{t}`" for t in treatments)
                  or language.fill(_EMPTY_SEQUENCE, lang)),
        outcome=block.get("outcome", "?"))
    by_time = block.get("confounders_by_time") or []
    if by_time:
        line += language.fill(
            _CONFOUNDERS_BY_TIME, lang,
            variables=language.listing(
                (_vars(b) for b in by_time), lang))
    return "\n".join([line, language.fill(
        _SEQUENTIAL_EXCHANGEABILITY if block.get("identified")
        else _SEQUENTIAL_EXCHANGEABILITY_FAILS, lang)])


_NDE_NIE_LABEL: language.Words = {
    "zh": "NDE / NIE（自然直接 / 间接效应）",
    "en": "NDE / NIE (natural direct / indirect effect)",
}
_CDE_LABEL: language.Words = {
    "zh": "CDE（控制直接效应）",
    "en": "CDE (controlled direct effect)",
}
_ARM_UNIDENTIFIABLE: language.Words = {
    "zh": "  - {label}**不可识别**",
    "en": "  - {label} is **not identifiable**",
}
_ARM_UNIDENTIFIABLE_BECAUSE: language.Words = {
    "zh": "：{condition} —— {said}", "en": ": {condition} — {said}"}
_ARM_IDENTIFIABLE: language.Words = {
    "zh": "  - {label}可识别", "en": "  - {label} is identifiable"}
_ARM_ADJUSTING: language.Words = {
    "zh": "，调整 {variables}", "en": ", adjusting for {variables}"}
_ARM_NO_ADJUSTMENT: language.Words = {
    "zh": "，无需调整", "en": ", with no adjustment needed"}


def _mediation_arm(info: dict | None, label: language.Words,
                   condition_word: _ConditionWord, *,
                   lang: language.Lang | str) -> str:
    """One arm of a decomposition — identifiable, and on what.

    ``condition_word`` differs per arm because the two arms fail different
    theorems: the natural decomposition on Pearl 2001's four cross-world
    conditions, the controlled one on two back-door conditions. The labels
    are drawn from disjoint sets, so one table would read as one vocabulary
    and hide that ``M4`` and ``C2`` are different statements about the same
    adjustment set.
    """
    info = info or {}
    said = language.fill(label, lang)
    if not info.get("identifiable"):
        why = info.get("failed_condition")
        return language.fill(_ARM_UNIDENTIFIABLE, lang, label=said) + (
            language.fill(_ARM_UNIDENTIFIABLE_BECAUSE, lang, condition=why,
                          said=condition_word(why, lang)) if why else "")
    adj = info.get("adjustment")
    return language.fill(_ARM_IDENTIFIABLE, lang, label=said) + (
        language.fill(_ARM_ADJUSTING, lang, variables=_vars(adj)) if adj
        else language.fill(_ARM_NO_ADJUSTMENT, lang))


_MEDIATOR_INVALID: language.Words = {
    "zh": "- **中介分解**：`{mediator}` 不在任何 X → … → {mediator} → … → Y "
          "的有向路径上，它不是这条效应的中介",
    "en": "- **Mediation decomposition**: `{mediator}` lies on no directed "
          "path X → … → {mediator} → … → Y, so it is not a mediator of this "
          "effect",
}
_MEDIATION_HEAD: language.Words = {
    "zh": "- **中介分解**：中介 `{mediator}`",
    "en": "- **Mediation decomposition**: mediator `{mediator}`",
}


def _route_mediation_decomposition(block: dict, result: dict, *,
                                   lang: language.Lang | str) -> str:
    mediator = block.get("mediator", "?")
    if not block.get("mediator_valid", True):
        return language.fill(_MEDIATOR_INVALID, lang, mediator=mediator)
    return "\n".join([
        language.fill(_MEDIATION_HEAD, lang, mediator=mediator),
        _mediation_arm(block.get("nde_nie"), _NDE_NIE_LABEL,
                       envelope_glossary.nde_nie_condition_word, lang=lang),
        _mediation_arm(block.get("cde"), _CDE_LABEL,
                       envelope_glossary.cde_condition_word, lang=lang),
    ])


_MEDIATOR_SET_INVALID: language.Words = {
    "zh": "- **中介集分解**：{mediators} 不构成这条效应的有效中介集",
    "en": "- **Joint mediation decomposition**: {mediators} is not a valid "
          "mediator set for this effect",
}
_MEDIATION_SET_HEAD: language.Words = {
    "zh": "- **中介集分解**：中介集 {mediators} 整体当一个块处理 —— "
          "正是不需要给集合内部排序才使它可识别",
    "en": "- **Joint mediation decomposition**: the mediator set {mediators} "
          "is handled as one block — what makes it identifiable is precisely "
          "that no order within the set is needed",
}


def _route_mediation_joint_decomposition(block: dict, result: dict, *,
                                         lang: language.Lang | str) -> str:
    mediators = _vars(block.get("mediators"))
    if not block.get("mediator_set_valid", True):
        return language.fill(_MEDIATOR_SET_INVALID, lang, mediators=mediators)
    return "\n".join([
        language.fill(_MEDIATION_SET_HEAD, lang, mediators=mediators),
        _mediation_arm(block.get("nde_nie"), _NDE_NIE_LABEL,
                       envelope_glossary.nde_nie_condition_word, lang=lang),
        _mediation_arm(block.get("cde"), _CDE_LABEL,
                       envelope_glossary.cde_condition_word, lang=lang),
    ])


_PROXIMAL_HEAD: language.Words = {
    "zh": "- **近端识别**：未测混杂 `{latent}` 由代理变量约束 —— "
          "处理侧 {treatment_proxy}、结局侧 {outcome_proxy}",
    "en": "- **Proximal identification**: the unmeasured confounder "
          "`{latent}` is constrained by proxies — {treatment_proxy} on "
          "the treatment side and {outcome_proxy} on the outcome side",
}
#: Said when the question was asked within observed variables. Its own line
#: rather than a hole above, because the common question has no covariates
#: and a reader of that one should not meet an empty clause.
_PROXIMAL_WITHIN: language.Words = {
    "zh": "  - 以上都在给定 {covariates} 之下成立，效应最后对它们取平均",
    "en": "  - All of that holds given {covariates}, and the effect is "
          "averaged over them at the end",
}
_LATENT_CARDINALITY: language.Words = {
    "zh": "（未测混杂取 {count} 个值）",
    "en": " (the unmeasured confounder takes {count} values)",
}
# The continuous regime's counterpart of the line above, and it says two more
# things because there are two more to say: the cardinality of U is not
# assumed here at all, and what stands in its place — a function class and a
# penalty — is a pair of choices rather than a single posited number.
_BRIDGE_SIEVE: language.Words = {
    "zh": "（代理是连续的，所以解的是 bridge function：假设它落在 {dimension} "
          "个基函数张成的空间里——{design}——由 {instruments} 个矩条件定下来，"
          "取矩的方向是 {instrument_design}）",
    "en": " (the proxies are continuous, so what is solved for is the bridge "
          "function: assumed to lie in the span of {dimension} basis "
          "functions — {design} — pinned down by {instruments} moments taken "
          "along {instrument_design})",
}
#: The second bridge, when there is one. Said as the mirror it is, because
#: that is the fact a reader needs to hold both of them at once.
_TREATMENT_BRIDGE: language.Words = {
    "zh": "  - 还解了一座处理桥 q：它落在 {dimension} 个基函数里——{design}"
          "——由 {instruments} 个矩条件定下来，取矩的方向是 {instrument_design}。"
          "和结局桥正好反过来：h 是代理 W 的函数、在 Z 的矩上被检验，q 是 Z 的"
          "函数、在 W 的矩上被检验",
    "en": "  - A treatment bridge q was solved for as well: it lies in "
          "{dimension} basis functions — {design} — pinned down by "
          "{instruments} moments taken along {instrument_design}. The mirror "
          "of the outcome bridge: h is a function of the W proxies tested at "
          "moments of Z, and q is a function of Z tested at moments of W",
}
#: One sentence per estimator, and not one with the name in a hole. What
#: differs between them is not a word but the ARGUMENT — which assumption
#: has to hold — and an argument assembled from a slot is an argument no
#: reader can be shown in advance.
_ESTIMATOR_OUTCOME_REGRESSION: language.Words = {
    "zh": "  - 报出来的数是**结局回归**：先解出 h，再对全样本平均 "
          "h(W,1,C)−h(W,0,C)。它对不对，全看 h 是不是真的落在你声明的那个 "
          "span 里——落不进去，再多数据也救不回来",
    "en": "  - The number reported is the **outcome regression**: solve for h, "
          "then average h(W,1,C) − h(W,0,C) over the whole sample. Whether it "
          "is right turns entirely on whether h really lies in the span you "
          "declared — if it does not, more data does not recover it",
}
#: The same estimator answering the other shape. Its own sentence and not
#: a slot in the one above, because what changes is not the pair of levels
#: — it is that there is no pair: the curve is one bridge evaluated at each
#: level, and a reader told "average h(W,1,C) − h(W,0,C)" over a curve has
#: been told the arithmetic of a contrast that did not run.
_ESTIMATOR_OUTCOME_REGRESSION_CURVE: language.Words = {
    "zh": "  - 报出来的是一条**曲线**，走的是结局回归：解出**一座**桥 h，再把"
          "它在每个水平 a 上求值——`E[Y(a)]` 就是对全样本平均 h(W,a,C)"
          "（Cui et al. 2024 定理 2.1 式 (4)）。定理认的是「某个水平上的均值」"
          "，两个水平之差只是它的一个导出量，所以曲线不是多算了几次对比，"
          "是同一个东西被问全了",
    "en": "  - The answer is a **curve**, by outcome regression: solve for "
          "ONE bridge h and evaluate it at each level — `E[Y(a)]` is "
          "h(W,a,C) averaged over the whole sample (Cui et al. 2024, "
          "Theorem 2.1 eq. (4)). What the theorem identifies is the mean AT "
          "A LEVEL, and a contrast between two of them is one thing derived "
          "from it, so a curve is not several contrasts — it is the same "
          "quantity asked completely",
}
#: The other two, answering the curve. The asymmetry between the bridges is
#: the thing worth saying here and it has no counterpart in the contrast: q
#: is solved level by level through (8)'s indicator, so it is saturated in
#: the treatment whatever basis was declared, while h had to be TOLD how to
#: vary. A reader comparing the two curves is comparing one that assumed a
#: shape between the levels against one that assumed none.
_ESTIMATOR_INVERSE_PROBABILITY_CURVE: language.Words = {
    "zh": "  - 报出来的是一条**曲线**，走的是逆概率加权：每个水平上单独解一座"
          "处理桥 q，用它给那个水平的行赋权再平均 Y，整个过程不看 h。和结局"
          "回归那条不同的是：q 是靠式 (8) 里的示性 I(A=a) 一个水平一个水平定"
          "下来的，所以它在处理上**自动饱和**——你为它声明的基函数不决定曲线"
          "在水平之间的形状，因为它根本不在水平之间插值。代价是另一头：一个"
          "没有行的水平就没有臂，所以这条路只在观测到的水平上有定义",
    "en": "  - The answer is a **curve**, by inverse-probability weighting: a "
          "treatment bridge q is solved separately at each level, used to "
          "weight that level's rows, and Y averaged — h never consulted. "
          "Unlike the outcome regression, q is pinned down one level at a "
          "time through the indicator I(A=a) of eq. (8), so it is "
          "AUTOMATICALLY saturated in the treatment: the basis you declared "
          "for it does not decide the shape between levels, because it does "
          "not interpolate between them. The cost is at the other end — a "
          "level with no rows has no arm, so this route is defined only at "
          "levels the sample visits",
}
_ESTIMATOR_DOUBLY_ROBUST_CURVE: language.Words = {
    "zh": "  - 报出来的是一条**双稳健**的曲线：每个水平上，只要两座桥里**有"
          "一座**是对的，那个点就是对的，而且你不需要知道是哪一座（Cui et "
          "al. 2024 定理 3.2）。三条曲线都在信封上——把它们叠在一起看，就是"
          "把三个不同的假设叠在一起看。边界照旧：两座都错时它照样错，而且不"
          "会告诉你",
    "en": "  - The answer is a **doubly robust** curve: at each level it is "
          "right as long as **at least one** of the two bridges is, and you "
          "do not have to know which (Cui et al. 2024, Theorem 3.2). All "
          "three curves are on the envelope — laying them over each other "
          "lays three different assumptions over each other. The edge is "
          "unchanged: where both are wrong it is wrong too, and it does not "
          "announce that",
}
_ESTIMATOR_INVERSE_PROBABILITY: language.Words = {
    "zh": "  - 报出来的数是**逆概率加权**：用处理桥 q 给每一行赋权再平均 Y，"
          "整个过程一眼都不看 h。它对不对，全看 q 是不是落在你为它声明的 span "
          "里——所以它和上面那条读的是两个不同的假设，把两个数摆在一起看，"
          "就是把两个假设摆在一起看",
    "en": "  - The number reported is the **inverse-probability** estimate: "
          "weight each row by the treatment bridge q and average Y, never "
          "consulting h. Whether it is right turns entirely on whether q lies "
          "in the span you declared for it — a different assumption from the "
          "one above, which is why putting the two numbers side by side puts "
          "the two assumptions side by side",
}
_ESTIMATOR_DOUBLY_ROBUST: language.Words = {
    "zh": "  - 报出来的数是**双稳健**的那个：两座桥里只要**有一座**落在它声明的 "
          "span 里，这个数就是对的，而且你不需要知道是哪一座（Cui et al. 2024 "
          "定理 3.2）。它的边界也说清楚：两座都错时它照样错，而且不会告诉你",
    "en": "  - The number reported is the **doubly robust** one: it is right "
          "as long as **at least one** of the two bridges lies in its "
          "declared span, and you do not have to know which (Cui et al. 2024, "
          "Theorem 3.2). Its edge, stated: where both are wrong it is wrong "
          "too, and it does not announce that",
}
_ESTIMATOR_WORDS: "dict[str, language.Words]" = {
    "outcome_regression": _ESTIMATOR_OUTCOME_REGRESSION,
    "inverse_probability": _ESTIMATOR_INVERSE_PROBABILITY,
    "doubly_robust": _ESTIMATOR_DOUBLY_ROBUST,
}
#: The curve's own table, and short on purpose: only the outcome regression
#: answers this shape today. An estimator missing from here says nothing
#: rather than borrowing the contrast's sentence, which would describe a
#: two-arm arithmetic that did not run — the same rule the table above
#: follows for an estimator it has never heard of.
_CURVE_ESTIMATOR_WORDS: "dict[str, language.Words]" = {
    "outcome_regression": _ESTIMATOR_OUTCOME_REGRESSION_CURVE,
    "inverse_probability": _ESTIMATOR_INVERSE_PROBABILITY_CURVE,
    "doubly_robust": _ESTIMATOR_DOUBLY_ROBUST_CURVE,
}
#: One factor of one term. The family sits beside the variable it expands
#: because with several variables a family named on its own belongs to none
#: of them, which is what a single ``basis`` field used to mean here.
_BRIDGE_FACTOR: language.Words = {
    "zh": "{variable} 上 {dimension} 个{basis}基",
    "en": "{dimension} {basis}basis functions on {variable}",
}
#: A term over more than one variable. Said as a product because that is
#: what it is, and because the reader's next question — why is this design
#: so wide — is answered by seeing the multiplication.
_BRIDGE_INTERACTION: language.Words = {
    "zh": "{factors}的交互", "en": "the interaction of {factors}",
}
_BASIS_WORDS: dict[str, language.Words] = {
    "polynomial": {"zh": "多项式", "en": "polynomial "},
    "piecewise_linear": {"zh": "分段线性", "en": "piecewise-linear "},
    "cubic_spline": {"zh": "三次样条", "en": "cubic-spline "},
    # Named as what declaring it CLAIMS rather than as the functions it is
    # made of: a reader who is told "sines and cosines" learns which
    # arithmetic ran, and a reader told "periodic" learns what was assumed
    # about their variable — which is the half they can disagree with.
    "fourier": {"zh": "周期（傅里叶）", "en": "periodic (Fourier) "},
    "hermite": {"zh": "Hermite 正交多项式", "en": "orthogonal Hermite "},
}
_RIDGE_CHOSEN: language.Words = {
    "zh": "  - 正则化 λ={ridge}，是你在问题里选的",
    "en": "  - Regularisation λ={ridge}, which you chose in the question",
}
_RIDGE_DEFAULTED: language.Words = {
    "zh": "  - 正则化强度 **没有人选**——bridge 方程不加它就没有数值解，所以"
          "估计器按问题自身的尺度取了一个稳定化的小值；它稳定求解，不声称最优",
    "en": "  - The regularisation was **chosen by nobody** — the bridge "
          "equation has no numeric solution without one, so the estimator "
          "took a small value scaled to the problem's own magnitude. It "
          "stabilises the solve and claims nothing about being optimal",
}
#: The same pair for the second bridge. Separate members and not the two
#: above with the bridge in a slot, for the reason those two are separate
#: from each other: each says something a reader acts on differently, and
#: a λ nobody chose on ONE of two equations is its own fact.
_TREATMENT_RIDGE_CHOSEN: language.Words = {
    "zh": "  - 处理桥的正则化 λ={ridge}，是你在问题里选的。它和结局桥那一个是"
          "两个数：两条方程正则化的是两个不同的算子，各有各的尺度",
    "en": "  - The treatment bridge's regularisation λ={ridge}, which you "
          "chose in the question. A different number from the outcome "
          "bridge's: the two equations regularise two different operators, "
          "each with its own scale",
}
_TREATMENT_RIDGE_DEFAULTED: language.Words = {
    "zh": "  - 处理桥的正则化强度 **没有人选**——估计器按这条方程自身的尺度取了"
          "一个稳定化的小值，规则和结局桥那条相同，取到的数不同",
    "en": "  - The treatment bridge's regularisation was **chosen by nobody** "
          "— the estimator took a small value scaled to that equation's own "
          "magnitude, by the same rule as the outcome bridge's and arriving "
          "at a different number",
}
_DATA_CONDITIONS: language.Words = {
    "zh": "  - 数据须满足：{conditions}",
    "en": "  - The data have to satisfy: {conditions}",
}


def _quoted_names(names, lang: language.Lang | str) -> str:
    """Several column names, each in code ticks, joined for this reader.

    The ticks are per NAME rather than around the join: one pair of ticks
    around a joined list would put the reader's comma inside the code span,
    where it reads as part of a column name.
    """
    return language.listing([f"`{n}`" for n in names or ()], lang) or "`?`"


def _route_proximal_estimand(block: dict, result: dict, *,
                             lang: language.Lang | str) -> str:
    line = language.fill(
        _PROXIMAL_HEAD, lang, latent=block.get("latent", "?"),
        treatment_proxy=_quoted_names(block.get("treatment_proxy"), lang),
        outcome_proxy=_quoted_names(block.get("outcome_proxy"), lang))
    out = [line + _proximal_channel_line(block, lang=lang)]
    covariates = block.get("covariates") or ()
    if covariates:
        out.append(language.fill(
            _PROXIMAL_WITHIN, lang,
            covariates=_quoted_names(covariates, lang)))
    # Which SHAPE came back is a fact about the run and not about the
    # declaration, so it is read from the answer rather than from the
    # estimand block — the same channel answers either way and only the
    # treatment's cardinality decides which.
    curve = bool((result.get("numeric_estimate") or {}).get(
        "dose_response_curve"))
    out.extend(_proximal_bridge_lines(block, curve=curve, lang=lang))
    conds = block.get("data_conditions") or ()
    if conds:
        # Tokens off the envelope, looked up here and joined in this
        # reader's punctuation. The block used to carry the sentences
        # themselves, already joined by the producer.
        out.append(language.fill(
            _DATA_CONDITIONS, lang,
            conditions=language.listed(
                [{"vocabulary": "proximal_data_condition", "token": c}
                 for c in conds], lang)))
    return "\n".join(out)


def _proximal_channel_line(block: dict, *,
                           lang: language.Lang | str) -> str:
    """What replaced "U takes k values" when the proxies went continuous."""
    if block.get("channel_kind") == "bridge_channel":
        return _bridge_line(_BRIDGE_SIEVE, block, _OUTCOME_BRIDGE, lang)
    card = block.get("latent_cardinality")
    if card is None:
        return ""
    return language.fill(_LATENT_CARDINALITY, lang, count=card)


class _BridgeFields(NamedTuple):
    """Which flattened keys one bridge's four facts live under.

    Spelt out and not composed from a prefix. One reader serves both bridges
    — they are the same object twice — but a key assembled at read time is a
    key nothing can be checked against: it appears in no module, so a
    producer that renamed one would be found by nobody, and the schema, the
    producer and this reader would drift apart in silence.
    """

    span_terms: str
    moment_terms: str
    span_width: str
    moment_width: str
    ridge: str


_OUTCOME_BRIDGE = _BridgeFields(
    span_terms="outcome_bridge_span_terms",
    moment_terms="outcome_bridge_moment_terms",
    span_width="outcome_bridge_span_width",
    moment_width="outcome_bridge_moment_width",
    ridge="outcome_bridge_ridge",
)
_TREATMENT_BRIDGE_FIELDS = _BridgeFields(
    span_terms="treatment_bridge_span_terms",
    moment_terms="treatment_bridge_moment_terms",
    span_width="treatment_bridge_span_width",
    moment_width="treatment_bridge_moment_width",
    ridge="treatment_bridge_ridge",
)


def _bridge_line(words: language.Words, block: dict, fields: _BridgeFields,
                 lang: language.Lang | str) -> str:
    """One bridge's span and moments.

    One reader for both bridges because they are the same object twice: the
    span, its width, the moments, theirs. What differs is the sentence
    around them, which is the caller's argument and stays outside.
    """
    return language.fill(
        words, lang,
        dimension=block.get(fields.span_width, "?"),
        instruments=block.get(fields.moment_width, "?"),
        design=_sieve_design_line(block.get(fields.span_terms), lang),
        instrument_design=_sieve_design_line(
            block.get(fields.moment_terms), lang))


def _sieve_design_line(terms, lang: language.Lang | str) -> str:
    """The declared span, said as the terms it is the sum of.

    What a reader needs from a sieve is which variables were expanded and
    how far, and with several of them that is a list rather than a pair of
    numbers. The width is said once, above; this is what makes up the width.
    """
    said = []
    for term in terms or ():
        factors = [
            language.fill(
                _BRIDGE_FACTOR, lang,
                variable=f"`{f.get('variable', '?')}`",
                dimension=f.get("dimension", "?"),
                basis=language.gloss(_BASIS_WORDS, str(f.get("basis") or ""),
                                     lang, unknown=""))
            for f in term or ()
        ]
        said.append(
            factors[0] if len(factors) == 1
            else language.fill(_BRIDGE_INTERACTION, lang,
                               factors=language.listing(factors, lang)))
    return language.listing(said, lang)


def _proximal_bridge_lines(block: dict, *, curve: bool = False,
                           lang: language.Lang | str) -> "list[str]":
    """Which estimator ran, the second bridge if there is one, and both λs.

    Which ESTIMATOR is the sentence this list exists for. All three answers
    are the same shape and differ only in what has to be true for them to be
    right, so a report that named the method and not the assumption would be
    handing a reader a number whose whole content it had left out.

    Who chose each penalty is two sentences per bridge and not one with a
    hole, because the fact that separates them is not a value: a λ the caller
    named is a lever they can move and a λ nobody named is a lever they did
    not know they had. The ledger says the same thing one channel over — this
    is the reader's copy of it, and the reason it is here at all is that a
    number carrying an unattributed penalty reads exactly like a number
    without one.
    """
    if block.get("channel_kind") != "bridge_channel":
        return []
    out = []
    words = _CURVE_ESTIMATOR_WORDS if curve else _ESTIMATOR_WORDS
    estimator = words.get(str(block.get("estimator") or ""))
    if estimator is not None:
        out.append(language.fill(estimator, lang))
    if block.get(_TREATMENT_BRIDGE_FIELDS.span_terms) is not None:
        out.append(_bridge_line(_TREATMENT_BRIDGE, block,
                                _TREATMENT_BRIDGE_FIELDS, lang))
    for fields, chosen, defaulted in (
            (_OUTCOME_BRIDGE, _RIDGE_CHOSEN, _RIDGE_DEFAULTED),
            (_TREATMENT_BRIDGE_FIELDS, _TREATMENT_RIDGE_CHOSEN,
             _TREATMENT_RIDGE_DEFAULTED)):
        if fields.ridge not in block:
            continue
        ridge = block.get(fields.ridge)
        if ridge is None:
            # No number in this branch, and that is the shape of the fact:
            # this block holds the DECLARATION, a declaration of nothing has
            # no value in it, and what the reader needs here is who to argue
            # with rather than a float they did not pick. The value the
            # estimator settled on is in the derivation, where an auditor
            # looks for it.
            out.append(language.fill(defaulted, lang))
        else:
            out.append(language.fill(chosen, lang,
                                     ridge=language.occasion(ridge)))
    return out


_SELECTION_BACKDOOR_SET: language.Words = {
    "zh": "{indent}- 选择后门调整集 {variables}",
    "en": "{indent}- Selection back-door adjustment set {variables}",
}
_Z_PLUS: language.Words = {
    "zh": "{indent}- Z⁺={variables} —— 不是处理的后代，**挡后门路径的是它**",
    "en": "{indent}- Z⁺={variables} — not a descendant of the treatment, and "
          "**this is the part that blocks the back-door paths**",
}
_Z_MINUS: language.Words = {
    "zh": "{indent}- Z⁻={variables} —— 是处理的**后代**，挡不了后门；"
          "条件在它上面是为了让选择节点与结局条件独立，"
          "代价是恢复式里多一层 P(Z⁻ | 处理, Z⁺) 的重加权",
    "en": "{indent}- Z⁻={variables} — a **descendant** of the treatment, so "
          "it blocks no back door; conditioning on it is what makes the "
          "selection nodes conditionally independent of the outcome, at the "
          "cost of one more reweighting layer P(Z⁻ | treatment, Z⁺) in the "
          "recovery formula",
}


def _selection_adjustment(block: dict, indent: str = "    ", *,
                          lang: language.Lang | str) -> list[str]:
    """The two halves of Z, which do different jobs.

    Only Z⁺ — the part of Z that is not a descendant of the treatment — is
    checked for blocking, and blocking is what "back-door adjustment" means.
    Z⁻ is conditioned on so the selection nodes come out independent of the
    outcome, and it cannot shut a confounding path: it is downstream of the
    treatment. One line naming their union as the selection back-door set
    therefore tells a reader that a descendant of the treatment is holding a
    confounding path closed, which is the one thing it is there not to do.
    """
    z_plus = list(block.get("z_plus") or ())
    z_minus = list(block.get("z_minus") or ())
    if not z_plus and not z_minus:
        adj = block.get("adjustment_set")
        return [language.fill(_SELECTION_BACKDOOR_SET, lang, indent=indent,
                              variables=_vars(adj))] if adj else []
    out = []
    if z_plus:
        out.append(language.fill(_Z_PLUS, lang, indent=indent,
                                 variables=_vars(z_plus)))
    if z_minus:
        out.append(language.fill(_Z_MINUS, lang, indent=indent,
                                 variables=_vars(z_minus)))
    return out


_SELECTION_HEAD: language.Words = {
    "zh": "- **选择偏倚**：样本被 {variables} 限制过",
    "en": "- **Selection bias**: the sample was restricted by {variables}",
}
_SELECTION_RECOVERABLE: language.Words = {
    "zh": "  - 无偏效应**可从这份有偏样本恢复**",
    "en": "  - The unbiased effect **can be recovered from this biased "
          "sample**",
}
_SELECTION_NOT_RECOVERABLE: language.Words = {
    "zh": "  - 无偏效应**无法只从这份样本恢复**",
    "en": "  - The unbiased effect **cannot be recovered from this sample "
          "alone**",
}
_BECAUSE: language.Words = {"zh": "：{why}", "en": ": {why}"}
_EXTERNAL_DATA_NEEDED: language.Words = {
    "zh": "  - 还需要外部（未经选择的）数据：{items}",
    "en": "  - External, unselected data are needed as well: {items}",
}
_RECOVERY_FORMULA: language.Words = {
    "zh": "  - 恢复式：`{formula}`",
    "en": "  - Recovery formula: `{formula}`",
}

#: Both recovery searches enumerate candidate sets by size and stop at a
#: bound, so a negative verdict is a claim about the sets they looked at and
#: not about every set there is. The bound is the quantifier on that claim,
#: and a reader handed "not recoverable" without it is handed a stronger
#: statement than the one that was checked. Said only on the negative
#: branch: a positive verdict exhibits the set it found, and a bound
#: qualifies nothing there.
_SEARCH_RANGE: language.Words = {
    "zh": "（搜索范围：最多 {n} 个变量的集合）",
    "en": " (search range: sets of at most {n} variables)",
}


def _search_range(block: dict, *, lang: language.Lang | str) -> str:
    budget = block.get("search_budget")
    if not isinstance(budget, int) or isinstance(budget, bool):
        return ""
    return language.fill(_SEARCH_RANGE, lang, n=budget)


#: The other half of what a negative verdict owes its reader. Its
#: neighbour above gives the range the search covered; this one says
#: whether the test that produced the verdict is necessary as well as
#: sufficient — because "no set was found" and "no set exists" are
#: different claims, and a reader shown the first will read the second.
#: It used to be a clause inside the kernel's own sentence, written out
#: in whichever branch remembered to; a fact stated only inside a wording
#: is a fact nothing can branch on.
_NOT_A_PROOF: language.Words = {
    "zh": "（这个判据是充分条件，不是必要条件——「没找到」不等于"
          "「证明了恢复不出来」）",
    "en": " (the criterion is sufficient, not necessary — \"none was "
          "found\" is not \"none exists\")",
}


def _not_a_proof(block: dict, *, lang: language.Lang | str) -> str:
    if block.get("complete_criterion"):
        return ""
    return language.fill(_NOT_A_PROOF, lang)


_VECTOR_IV_HEAD: language.Words = {
    "zh": "- **多内生工具变量**：{variables} 一起被干预，用 {instruments} 作工具",
    "en": "- **Instruments for a treatment vector**: {variables} are "
          "intervened on together, instrumented by {instruments}",
}
_VECTOR_IV_MOVES: language.Words = {
    "zh": "  - `{instrument}` 移动的是 {variables}",
    "en": "  - `{instrument}` moves {variables}",
}
_VECTOR_IV_MOVES_NOTHING: language.Words = {
    "zh": "  - `{instrument}` 哪个处理都不移动——它仍是有效工具（有效性只要"
          "排他性与外生性），但它给检验添一个自由度而不添信息",
    "en": "  - `{instrument}` moves none of the treatments — still a valid "
          "instrument (validity asks only for exclusion and exogeneity), but "
          "it costs the test a degree of freedom and contributes nothing",
}
_VECTOR_IV_GIVEN: language.Words = {
    "zh": "  - 这些工具是在给定 {variables} 之后才有效的",
    "en": "  - The instruments are valid given {variables}",
}
_VECTOR_IV_UNDER_IDENTIFIED: language.Words = {
    "zh": "  - 工具数（{q}）少于被干预的处理数（{k}）：这一组系数**点识别"
          "不了**，所以答案是一个置信域而不是一组数——域在数据约束不了的那些"
          "方向上无界，那是如实的回答，不是失败",
    "en": "  - Fewer instruments ({q}) than treatments ({k}): the coefficient "
          "vector is **not point-identified**, so the answer is a confidence "
          "region rather than a set of numbers — unbounded in the directions "
          "the data cannot constrain, which is the honest answer and not a "
          "failure",
}
_VECTOR_IV_NO_RELEVANCE_NEEDED: language.Words = {
    "zh": "  - 这个置信域的覆盖率与第一阶段强弱无关——工具弱不影响它对不对，"
          "只影响它有多大",
    "en": "  - The region's coverage does not depend on how strong the first "
          "stage is — weak instruments make it larger, not wrong",
}


def _route_vector_iv_identification(block: dict, result: dict, *,
                                    lang: language.Lang | str) -> str:
    """Which instruments serve the whole vector, and what each one moves.

    The per-instrument relevance is the fact a reader needs and no other
    block carries: it is what predicts whether the region came back bounded,
    while being no part of what makes the region valid.
    """
    treatments = block.get("treatments") or ()
    instruments = block.get("instruments") or ()
    out = [language.fill(
        _VECTOR_IV_HEAD, lang,
        variables=_vars(treatments), instruments=_vars(instruments))]
    for row in block.get("relevance") or ():
        moves = row.get("moves") or ()
        out.append(
            language.fill(_VECTOR_IV_MOVES, lang,
                          instrument=row.get("instrument"),
                          variables=_vars(moves))
            if moves else
            language.fill(_VECTOR_IV_MOVES_NOTHING, lang,
                          instrument=row.get("instrument")))
    cond = block.get("conditioning")
    if cond:
        out.append(language.fill(_VECTOR_IV_GIVEN, lang, variables=_vars(cond)))
    if len(instruments) < len(treatments):
        out.append(language.fill(_VECTOR_IV_UNDER_IDENTIFIED, lang,
                                 q=len(instruments), k=len(treatments)))
    out.append(language.fill(_VECTOR_IV_NO_RELEVANCE_NEEDED, lang))
    return "\n".join(out)


def _route_selection_recovery(block: dict, result: dict, *,
                              lang: language.Lang | str) -> str:
    out = [language.fill(_SELECTION_HEAD, lang,
                         variables=_vars(block.get("selection_nodes")))]
    if block.get("recoverable"):
        out.append(language.fill(_SELECTION_RECOVERABLE, lang))
        out += _selection_adjustment(block, lang=lang)
    else:
        why = language.spoke(block.get("failure_reason"), lang)
        out.append(
            language.fill(_SELECTION_NOT_RECOVERABLE, lang)
            + (language.fill(_BECAUSE, lang, why=why) if why else "")
            + _search_range(block, lang=lang)
            + _not_a_proof(block, lang=lang))
    need = block.get("external_data_needed")
    if need:
        out.append(language.fill(
            _EXTERNAL_DATA_NEEDED, lang,
            items=language.listed(need, lang)))
    # The expression the criterion produced. "Recoverable" is a verdict and
    # this is what it licenses you to compute; the section states the
    # estimand for every other route from ``result.formula``, and a recovery
    # route writes its own instead, so the estimand line does not reach it.
    formula = block.get("recovery_formula")
    if formula:
        out.append(language.fill(_RECOVERY_FORMULA, lang, formula=formula))
    return "\n".join(out)


#: Mohan-Pearl-Tian's graphical classification, strongest first. ``none``
#: is a member: the classifier returns it when the program declares no
#: missingness indicator at all, which is not a weaker MNAR but the absence
#: of the question — and it was the one value with no word.
_MECHANISM_WORDS = {
    "MCAR": {"zh": "MCAR（完全随机缺失）", "en": "MCAR (missing completely at random)"},
    "MAR": {"zh": "MAR（随机缺失，缺失只由观测到的变量决定）",
            "en": "MAR (missing at random — what is missing depends only on "
                  "what was observed)"},
    "MNAR": {"zh": "MNAR（非随机缺失，缺失与没测到的值本身有关）",
             "en": "MNAR (missing not at random — what is missing depends on "
                   "the unmeasured value itself)"},
    "none": {"zh": "未声明（程序里没有任何缺失指示变量，无从判断机制）",
             "en": "not stated (the program declares no missingness indicator, "
                   "so the mechanism cannot be judged)"},
}

_CONDITIONAL_LAYER: language.Words = {
    "zh": "条件概率这一层", "en": "the conditional-probability layer"}
_COVARIATE_MARGINAL: language.Words = {
    "zh": "协变量边缘 {target}", "en": "the covariate marginal {target}"}
_FACTORS: language.Words = {
    "zh": "  - {label}拆成 {count} 个因子：{factors} —— "
          "每个因子各在自己那些变量都被观测到的行上估",
    "en": "  - {label} splits into {count} factors: {factors} — each factor "
          "is estimated on the rows where its own variables were observed",
}
_FACTOR_FORMULA: language.Words = {
    "zh": "  - {label}的恢复式：`{formula}`",
    "en": "  - Recovery formula for {label}: `{formula}`",
}


def _recovery_factorization(part: dict, label: str, *,
                            lang: language.Lang | str) -> list[str]:
    """The ordered factors a recovery is assembled from, and its formula.

    Recoverability under missingness is a claim about an ORDER: each factor
    has to be estimable on the rows where its own variables were observed,
    and which order works is the content of the theorem. A verdict without
    the factorization tells a reader that it worked and not what worked, and
    the formula is what they would have to compute themselves.
    """
    factors = list(part.get("factorization") or ())
    out = []
    if factors:
        said = " × ".join(
            f"P({f.get('factor')}"
            + (f" | {language.within(f.get('conditioned_on') or ())}"
               if f.get("conditioned_on") else "")
            + ")"
            for f in factors
        )
        out.append(language.fill(_FACTORS, lang, label=label,
                                 count=len(factors), factors=said))
    formula = part.get("recovery_formula")
    if formula and not factors:
        out.append(language.fill(_FACTOR_FORMULA, lang, label=label,
                                 formula=formula))
    return out


_MISSING_HEAD: language.Words = {
    "zh": "- **缺失数据**：机制 {mechanism}",
    "en": "- **Missing data**: mechanism {mechanism}",
}
_PARTIALLY_OBSERVED: language.Words = {
    "zh": "  - 部分观测的变量：{variables}",
    "en": "  - Partially observed variables: {variables}",
}
_ESTIMAND_RECOVERABLE: language.Words = {
    "zh": "  - 整条估计量**可从缺失数据恢复**",
    "en": "  - The whole estimand **can be recovered from the missing "
          "data**",
}
_ESTIMAND_REQUIRES: language.Words = {
    "zh": "（需要 {items} 都可恢复）",
    "en": " (provided {items} are all recoverable)",
}
_ESTIMAND_NOT_RECOVERABLE: language.Words = {
    "zh": "  - 整条估计量**不可恢复**",
    "en": "  - The whole estimand is **not recoverable**",
}
_ESTIMAND_RECOVERY_FORMULA: language.Words = {
    "zh": "  - 整条估计量的恢复式：`{formula}`",
    "en": "  - Recovery formula for the whole estimand: `{formula}`",
}


def _route_missing_data_recovery(block: dict, result: dict, *,
                                 lang: language.Lang | str) -> str:
    mech = block.get("mechanism") or "?"
    out = [language.fill(
        _MISSING_HEAD, lang,
        mechanism=language.gloss(_MECHANISM_WORDS, mech, lang))]
    partial = block.get("partially_observed")
    if partial:
        out.append(language.fill(_PARTIALLY_OBSERVED, lang,
                                 variables=_vars(partial)))
    estimand = block.get("estimand") or {}
    if estimand.get("recoverable"):
        requires = estimand.get("requires") or ()
        out.append(
            language.fill(_ESTIMAND_RECOVERABLE, lang)
            + (language.fill(
                _ESTIMAND_REQUIRES, lang,
                items=language.listed(requires, lang))
               if requires else ""))
    else:
        why = language.spoke(
            estimand.get("failure_reason") or block.get("failure_reason"),
            lang)
        out.append(
            language.fill(_ESTIMAND_NOT_RECOVERABLE, lang)
            + (language.fill(_BECAUSE, lang, why=why) if why else "")
            + _search_range(block, lang=lang)
            + _not_a_proof(block, lang=lang))
    out += _recovery_factorization(
        block, language.fill(_CONDITIONAL_LAYER, lang), lang=lang)
    covariate = block.get("covariate_recovery") or {}
    if covariate:
        out += _recovery_factorization(
            covariate,
            language.fill(_COVARIATE_MARGINAL, lang,
                          target=covariate.get("target") or "P(Z)"),
            lang=lang)
    formula = estimand.get("recovery_formula")
    if formula:
        out.append(language.fill(_ESTIMAND_RECOVERY_FORMULA, lang,
                                 formula=formula))
    return "\n".join(out)


# Each route, said once. ``bind`` refuses a set that misses one, so a
# block added to the family cannot reach this section and render nothing.
_ROUTE_RENDERERS = blocks.bind(blocks.Family.ROUTE, {
    blocks.Block.IDENTIFICATION: _route_identification,
    blocks.Block.FEEDBACK_LOOP: _route_feedback_loop,
    blocks.Block.IV_IDENTIFICATION: _route_iv_identification,
    blocks.Block.VECTOR_IV_IDENTIFICATION: _route_vector_iv_identification,
    blocks.Block.TRANSPORT_IDENTIFICATION: _route_transport_identification,
    blocks.Block.JOINT_IDENTIFICATION: _route_joint_identification,
    blocks.Block.LONGITUDINAL_IDENTIFICATION: _route_longitudinal_identification,
    blocks.Block.MEDIATION_DECOMPOSITION: _route_mediation_decomposition,
    blocks.Block.MEDIATION_JOINT_DECOMPOSITION: _route_mediation_joint_decomposition,
    blocks.Block.PROXIMAL_ESTIMAND: _route_proximal_estimand,
    blocks.Block.SELECTION_RECOVERY: _route_selection_recovery,
    blocks.Block.MISSING_DATA_RECOVERY: _route_missing_data_recovery,
})


# --- how the NUMBER was computed ----------------------------------------------
#
# The renderers above answer "how was the estimand identified" from the
# ``extensions`` blocks that record it. The other half of this section's
# question — what the estimator then did with the data — is recorded on
# ``numeric_estimate``, which that binding does not reach.
#
# This section has been caught by exactly that gap twice before, and both
# times it was patched by appending one hand-written line: ``formula`` is a
# field rather than a block, so for ten rounds the report said "机器可读，见
# result.formula"; the derivation chain lives under ``derivation``, so six
# query kinds got the heading and nothing under it. The third instance is ten
# blocks — a stratum table, two independent longitudinal routes, three
# corrections each carrying the uncorrected number that is the whole argument
# for applying it — and at ten, appending lines stops being a repair.
#
# Which blocks belong here is the schema's answer and not this table's: the
# container declares ``additionalProperties: false``, so its properties ARE
# the closed list, and ``tests/test_the_answer_has_no_silent_parts.py`` walks
# them and holds each to naming who says it to a reader. A second list of the
# same names in kernel code is the duplication that check exists to prevent.


_UNCONDITIONAL_CELL: language.Words = {
    "zh": "（无条件）", "en": "(unconditional)"}
_STRATIFIED_WALD_HEAD: language.Words = {
    "zh": "- **分层 Wald 的逐格明细**（{count} 格，按 {order} 依次切）："
          "总体 = 加权结局差 {outcome_shift} ÷ 加权处理差 {treatment_shift}；"
          "聚合的是两个加权和之比，不是各格比值的平均，所以单格没有自己的 "
          "Wald 估计",
    "en": "- **The stratified Wald, cell by cell** ({count} cells, cut by "
          "{order} in that order): the whole = weighted outcome shift "
          "{outcome_shift} ÷ weighted treatment shift {treatment_shift}; "
          "what is aggregated is a ratio of two weighted sums rather than an "
          "average of per-cell ratios, so no single cell has a Wald estimate "
          "of its own",
}
_STRATUM_ROW: language.Words = {
    "zh": "  - {cell}：权重 {weight}，n={n}（工具高 {high} / 低 {low}），"
          "结局差 {outcome_shift}，处理差 {treatment_shift}",
    "en": "  - {cell}: weight {weight}, n={n} (instrument high {high} / low "
          "{low}), outcome shift {outcome_shift}, treatment shift "
          "{treatment_shift}",
}


def _detail_stratified_wald(ne: dict, result: dict, *,
                            lang: language.Lang | str) -> str:
    """The cells the ratio of averages was aggregated from.

    The aggregate is a ratio of two weighted sums and not an average of
    per-stratum ratios, so no stratum has a Wald estimate of its own to print
    beside it. What each one contributes is its weight and its two shifts, and
    a reader asking which cell is pulling the number reads those against the
    totals in the heading.
    """
    sw = ne["stratified_wald"]
    order = list(sw.get("conditioning_order") or ())
    strata = list(sw.get("strata") or ())
    joiner = language.fill(language.BETWEEN_ITEMS, lang)
    # Ordered rather than as a variable set: the cell labels below are read
    # positionally against this, so brace notation would say the order does
    # not matter when it is the field's whole content.
    head = language.fill(
        _STRATIFIED_WALD_HEAD, lang, count=len(strata),
        order=joiner.join(str(name) for name in order),
        outcome_shift=_fmt(sw.get("outcome_shift")),
        treatment_shift=_fmt(sw.get("treatment_shift")))
    out = []
    for s in strata:
        cell = joiner.join(
            f"{name}={value}"
            for name, value in zip(order, s.get("values") or ())
        ) or language.fill(_UNCONDITIONAL_CELL, lang)
        out.append(language.fill(
            _STRATUM_ROW, lang, cell=cell, weight=_fmt(s.get("weight")),
            n=s.get("n_obs"), high=s.get("n_instrument_high"),
            low=s.get("n_instrument_low"),
            outcome_shift=_fmt(s.get("outcome_shift")),
            treatment_shift=_fmt(s.get("treatment_shift"))))
    return "\n".join([head] + out)


_RECOVERED_HEAD: language.Words = {
    "zh": "- **从有缺失的数据里恢复**：恢复值 {point}",
    "en": "- **Recovered from data with missing values**: the recovered "
          "value is {point}",
}
_RECOVERED_VS_LISTWISE: language.Words = {
    "zh": "；直接丢掉不完整的行（列表删除法）会得到 {naive} —— "
          "两者之差就是这套方法全部的作用，也是判断它值不值得用的依据",
    "en": "; simply dropping the incomplete rows (listwise deletion) would "
          "give {naive} — the difference between the two is everything this "
          "method does, and the basis for judging whether it is worth using",
}
_RECOVERED_NO_LISTWISE: language.Words = {
    "zh": "（这次没有算出列表删除法的对照值，无从判断恢复挪动了多少）",
    "en": " (no listwise-deletion comparison was computed this time, so "
          "there is no telling how far the recovery moved the number)",
}
_RECOVERED_ROWS: language.Words = {
    "zh": "  - 共 {total} 行，完全没有缺失的只有 {complete} 行；"
          "条件概率那一层用了 {conditional} 行、边缘分布那一层用了 "
          "{marginal} 行 —— 每个因子各用自己的完整行估计，"
          "这正是它与列表删除法的差别所在",
    "en": "  - {total} rows in all, of which only {complete} have nothing "
          "missing; the conditional-probability layer used {conditional} "
          "rows and the marginal layer {marginal} — each factor is estimated "
          "on its own complete rows, which is exactly where this differs "
          "from listwise deletion",
}
_MISSING_COLUMNS: language.Words = {
    "zh": "  - 有缺失的列：{variables}",
    "en": "  - Columns with missing values: {variables}",
}
_RECOVERED_SETTINGS: language.Words = {
    "zh": "  - 调整集 {variables}，分 {strata} 层，bootstrap {bootstrap} 次",
    "en": "  - Adjustment set {variables}, {strata} strata, {bootstrap} "
          "bootstrap resamples",
}


def _detail_recovered_ate(ne: dict, result: dict, *,
                          lang: language.Lang | str) -> str:
    """The recovered ATE beside the number listwise deletion would have given.

    The comparison is the method: recovering an effect from data with missing
    values is worth doing exactly insofar as it differs from dropping the
    incomplete rows, and a reader shown only the recovered point has been
    shown the answer with the argument for it removed.
    """
    ra = ne["recovered_ate"]
    naive = ra.get("naive_listwise_ate")
    head = language.fill(_RECOVERED_HEAD, lang, point=_fmt(ra.get("point")))
    head += (language.fill(_RECOVERED_VS_LISTWISE, lang, naive=_fmt(naive))
             if naive is not None
             else language.fill(_RECOVERED_NO_LISTWISE, lang))
    out = [
        head,
        language.fill(_RECOVERED_ROWS, lang, total=ra.get("n_total"),
                      complete=ra.get("n_complete_case"),
                      conditional=ra.get("n_conditional_rows"),
                      marginal=ra.get("n_marginal_rows")),
    ]
    missing = list(ra.get("missing_columns") or ())
    if missing:
        out.append(language.fill(_MISSING_COLUMNS, lang,
                                 variables=_vars(missing)))
    out.append(language.fill(
        _RECOVERED_SETTINGS, lang, variables=_vars(ra.get("adjustment")),
        strata=ra.get("n_strata"), bootstrap=ra.get("n_bootstrap")))
    return "\n".join(out)


_SELECTION_NUMERIC_HEAD: language.Words = {
    "zh": "- **从选择偏倚里恢复**：处理臂均值 {treated}，对照臂均值 "
          "{control}，上面那个数是两者之差",
    "en": "- **Recovered from selection bias**: the treated-arm mean is "
          "{treated} and the control-arm mean {control}; the number above is "
          "their difference",
}
_REFERENCE_SAMPLE: language.Words = {
    "zh": "  - 外部参照样本 N={n} —— 恢复出的数只在"
          "「这份样本代表未被筛过的人群」这句话成立时才成立",
    "en": "  - External reference sample N={n} — the recovered number holds "
          "only insofar as that sample represents the unselected population",
}
_SAMPLE_RESTRICTED_TO: language.Words = {
    "zh": "  - 样本被限制在：{said}",
    "en": "  - The sample was restricted to: {said}",
}


def _detail_selection_recovery_numeric(ne: dict, result: dict, *,
                                       lang: language.Lang | str) -> str:
    """The two arm means, and the external sample the recovery leaned on.

    Which half of Z needs an unselected sample is not a property of the half.
    The criterion asks whether Z as a whole is independent of the selection
    nodes: when it is, nothing comes from outside; when it is not and Z⁻ is
    empty, what is needed is the marginal of Z⁺; and when Z⁻ is non-empty it
    is the joint over the treatment and both halves. So the split is stated
    here for what it IS — one half blocks the back-door paths and the other
    cannot — and ``external_data_needed`` beside it says what the selected
    sample cannot supply, which is a different question with its own answer.
    """
    sr = ne["selection_recovery_numeric"]
    out = [language.fill(_SELECTION_NUMERIC_HEAD, lang,
                         treated=_fmt(sr.get("mu_treated")),
                         control=_fmt(sr.get("mu_control")))]
    out += _selection_adjustment(sr, indent="  ", lang=lang)
    if sr.get("reference_sample_size") is not None:
        out.append(language.fill(_REFERENCE_SAMPLE, lang,
                                 n=sr["reference_sample_size"]))
    selected = sr.get("selected_values") or {}
    if selected:
        out.append(language.fill(
            _SAMPLE_RESTRICTED_TO, lang,
            said=language.listing(
                (f"{k}={v}" for k, v in selected.items()), lang)))
    return "\n".join(out)


_MISCLASSIFICATION_HEAD: language.Words = {
    "zh": "- **误分类校正**：{side}",
    "en": "- **Misclassification correction**: {side}",
}
_UNCORRECTED_TO_CORRECTED: language.Words = {
    "zh": "  - 未校正 {naive} → 校正后 {point}，校正把这个数挪了 {shift}",
    "en": "  - Uncorrected {naive} → corrected {point}, a move of {shift}",
}
_UNCORRECTED_ONLY: language.Words = {
    "zh": "  - 未校正 {naive}", "en": "  - Uncorrected {naive}"}
_DIFFERENTIAL_BY: language.Words = {
    "zh": "  - 差分性误分类：错分概率随 {by} 而变，"
          "所以每一档各用自己的混淆矩阵求逆",
    "en": "  - Differential misclassification: the error probabilities vary "
          "with {by}, so each level inverts a confusion matrix of its own",
}
_DIFFERENTIAL_BY_UNKNOWN: language.Words = {
    "zh": "  - 差分性误分类：错分概率随另一个变量而变，"
          "所以每一档各用自己的混淆矩阵求逆",
    "en": "  - Differential misclassification: the error probabilities vary "
          "with another variable, so each level inverts a confusion matrix "
          "of its own",
}
_CONFUSION_DET: language.Words = {
    "zh": "  - 混淆矩阵行列式 det={det} —— 越接近 0，求逆越不稳定，"
          "校正后的数对矩阵本身的误差越敏感",
    "en": "  - Confusion-matrix determinant det={det} — the closer to 0, the "
          "less stable the inversion, and the more sensitive the corrected "
          "number is to error in the matrix itself",
}
_DET_CHANNELS = (
    ("det_exposure", {"zh": "暴露通道", "en": "the exposure channel"}),
    ("det_outcome", {"zh": "结局通道", "en": "the outcome channel"}),
    ("det_joint", {"zh": "联合", "en": "the two jointly"}),
)
_DET_ROW: language.Words = {
    "zh": "  - {label} det={det}", "en": "  - {label} det={det}"}
_OUT_OF_SIMPLEX: language.Words = {
    "zh": "  - **求逆的结果落到了概率单纯形之外**：说明声明的混淆矩阵与这批"
          "数据对不上，校正后的数不该照单全收",
    "en": "  - **The inversion landed outside the probability simplex**: the "
          "declared confusion matrix does not match these data, and the "
          "corrected number should not be taken at face value",
}


def _detail_measurement_correction(ne: dict, result: dict, *,
                                   lang: language.Lang | str) -> str:
    """How far inverting the misclassification matrix moved the number.

    ``det`` is printed because it is what makes the correction unstable: a
    matrix near singular inverts into a large move that the data does not
    support, and the corrected point alone cannot tell that apart from a
    large real correction.
    """
    mc = ne["measurement_correction"]
    naive, point = mc.get("naive_point"), ne.get("point")
    out = [language.fill(
        _MISCLASSIFICATION_HEAD, lang,
        side=envelope_glossary.measurement_side_word(
            mc.get("side", "outcome"), lang))]
    if naive is not None and point is not None:
        out.append(language.fill(
            _UNCORRECTED_TO_CORRECTED, lang, naive=_fmt(naive),
            point=_fmt(point), shift=_fmt(point - naive)))
    elif naive is not None:
        out.append(language.fill(_UNCORRECTED_ONLY, lang, naive=_fmt(naive)))
    if mc.get("differential"):
        by = mc.get("differential_by")
        out.append(language.fill(_DIFFERENTIAL_BY, lang, by=by) if by
                   else language.fill(_DIFFERENTIAL_BY_UNKNOWN, lang))
    if mc.get("det") is not None:
        out.append(language.fill(_CONFUSION_DET, lang, det=_fmt(mc["det"])))
    for key, label in _DET_CHANNELS:
        if mc.get(key) is not None:
            out.append(language.fill(_DET_ROW, lang,
                                     label=language.fill(label, lang),
                                     det=_fmt(mc[key])))
    if mc.get("out_of_simplex"):
        out.append(language.fill(_OUT_OF_SIMPLEX, lang))
    return "\n".join(out)


_CALIBRATION_HEAD: language.Words = {
    "zh": "- **回归校准**（连续变量的经典加性测量误差）：暴露 `{exposure}`",
    "en": "- **Regression calibration** (classical additive measurement "
          "error on a continuous variable): exposure `{exposure}`",
}
_SLOPE_CORRECTED: language.Words = {
    "zh": "  - 未校正斜率 {naive} → 校正后 {point}，校正把这个数挪了 {shift}",
    "en": "  - Uncorrected slope {naive} → corrected {point}, a move of "
          "{shift}",
}
_RELIABILITY: language.Words = {
    "zh": "  - 可靠度 λ={value} —— λ=1 表示这个变量测得完全准，"
          "λ 越小衰减越重；校正做的就是把衰减除回去",
    "en": "  - Reliability λ={value} — λ=1 means the variable is measured "
          "exactly; the smaller λ, the heavier the attenuation, and the "
          "correction is that attenuation divided back out",
}
_ERROR_VARIANCES: language.Words = {
    "zh": "  - 声明的测量误差方差：{said}（这是外部知识，不是从数据里估的）",
    "en": "  - Declared measurement-error variances: {said} (external "
          "knowledge, not estimated from the data)",
}
_DESIGN_COLUMNS: language.Words = {
    "zh": "  - 设计矩阵列序：{variables}",
    "en": "  - Column order of the design matrix: {variables}",
}


def _detail_regression_calibration(ne: dict, result: dict, *,
                                   lang: language.Lang | str) -> str:
    """The attenuated slope, and the reliability that says how attenuated.

    λ is the whole correction — the corrected slope is the naive one divided
    through by it — so a reader who sees only the corrected number cannot
    tell a small measurement problem from a large one.
    """
    rc = ne["regression_calibration"]
    naive, point = rc.get("naive_point"), ne.get("point")
    out = [language.fill(_CALIBRATION_HEAD, lang,
                         exposure=rc.get("exposure"))]
    if naive is not None and point is not None:
        out.append(language.fill(
            _SLOPE_CORRECTED, lang, naive=_fmt(naive), point=_fmt(point),
            shift=_fmt(point - naive)))
    if rc.get("reliability") is not None:
        out.append(language.fill(_RELIABILITY, lang,
                                 value=_fmt(rc["reliability"])))
    variances = rc.get("error_variances") or {}
    if variances:
        out.append(language.fill(
            _ERROR_VARIANCES, lang,
            said=language.listing(
                (f"{k} σ²_u={_fmt(v)}" for k, v in variances.items()),
                lang)))
    design = list(rc.get("design_vars") or ())
    if design:
        out.append(language.fill(_DESIGN_COLUMNS, lang,
                                 variables=_vars(design)))
    return "\n".join(out)


_STRATEGY_CONTRAST: language.Words = {
    "zh": "  - 策略对比：全程 {treated} 下 E[{outcome}]={e_treated}，"
          "全程 {control} 下 E[{outcome}]={e_control}，上面那个数是两者之差",
    "en": "  - Strategies contrasted: under {treated} throughout, "
          "E[{outcome}]={e_treated}; under {control} throughout, "
          "E[{outcome}]={e_control}; the number above is their difference",
}
_TREATMENTS_AT_EACH_TIME: language.Words = {
    "zh": "  - 各时点的处理：{variables}",
    "en": "  - The treatments at each time: {variables}",
}
_ADJUSTED_AT_TIME: language.Words = {
    "zh": "    - 第 {index} 时点调整 {variables}",
    "en": "    - At time {index}, adjusting for {variables}",
}


def _longitudinal_common(block: dict, *,
                         lang: language.Lang | str) -> list[str]:
    """The lines both longitudinal routes state, in the same words.

    They contrast the same two strategies over the same times; only how they
    got there differs. Saying the shared part twice in two spellings would
    make a reader comparing the two routes reconcile the wording first.
    """
    out = [language.fill(
        _STRATEGY_CONTRAST, lang,
        treated=_fmt(block.get("strategy_treated")),
        control=_fmt(block.get("strategy_control")),
        outcome=block.get("outcome"),
        e_treated=_fmt(block.get("e_y_treated")),
        e_control=_fmt(block.get("e_y_control")))]
    treatments = list(block.get("treatments") or ())
    if treatments:
        out.append(language.fill(_TREATMENTS_AT_EACH_TIME, lang,
                                 variables=_vars(treatments)))
    by_time = list(block.get("confounders_by_time") or ())
    for i, names in enumerate(by_time, 1):
        out.append(language.fill(_ADJUSTED_AT_TIME, lang, index=i,
                                 variables=_vars(names)))
    return out


_GFORMULA_HEAD: language.Words = {
    "zh": "- **纵向 g-公式（g-computation）**：按时间顺序模拟每个时点的处理与"
          "协变量，再把结局在模拟出的人群上平均",
    "en": "- **Longitudinal g-formula (g-computation)**: simulate the "
          "treatment and the covariates at each time in order, then average "
          "the outcome over the simulated population",
}
_MONTE_CARLO: language.Words = {
    "zh": "  - 蒙特卡洛模拟 {n_sim} 次，bootstrap {n_bootstrap} 次",
    "en": "  - {n_sim} Monte-Carlo simulations, {n_bootstrap} bootstrap "
          "resamples",
}
_OTHER_ROUTE_IPW: language.Words = {
    "zh": "  - 另一条独立路线（IPW 边缘结构模型）这次没有跑："
          "它靠加权而不是靠模拟，两条算出来的数一致与否本身就是一个发现，"
          "这里没有这个发现",
    "en": "  - The other independent route (the IPW marginal structural "
          "model) was not run this time: it works by weighting rather than "
          "by simulation, and whether the two agree is itself a finding — "
          "one that is not available here",
}


def _detail_longitudinal_gformula(ne: dict, result: dict, *,
                                  lang: language.Lang | str) -> str:
    """The g-computation route, and the fact that a second route exists.

    The two longitudinal estimators answer one question from different
    assumptions, so whether they agree is itself a finding — and only one of
    them runs per query. A reader is told which one produced this number and
    that running the other is a check available to them, because otherwise
    the check looks like it was made and passed.
    """
    block = ne["longitudinal_gformula"]
    out = [language.fill(_GFORMULA_HEAD, lang)]
    out += _longitudinal_common(block, lang=lang)
    out.append(language.fill(_MONTE_CARLO, lang, n_sim=block.get("n_sim"),
                             n_bootstrap=block.get("n_bootstrap")))
    out.append(language.fill(_OTHER_ROUTE_IPW, lang))
    return "\n".join(out)


_IPW_MSM_HEAD: language.Words = {
    "zh": "- **纵向 IPW 边缘结构模型**：按每个时点接受该处理的概率给个体加权，"
          "在加权后的人群上拟合一个边缘模型",
    "en": "- **Longitudinal IPW marginal structural model**: weight each "
          "individual by their probability of receiving that treatment at "
          "each time, then fit a marginal model on the weighted population",
}
_STABILIZED: language.Words = {
    "zh": "稳定化权重", "en": "Stabilized weights"}
_UNSTABILIZED: language.Words = {
    "zh": "未稳定化权重", "en": "Unstabilized weights"}
_WEIGHT_SUMMARY: language.Words = {
    "zh": "  - {kind}：均值 {mean}，最大 {max} —— 最大值远高于均值，"
          "说明少数个体在主导这个数",
    "en": "  - {kind}: mean {mean}, maximum {max} — a maximum far above the "
          "mean means a handful of individuals carry this number",
}
_MSM_COEFFICIENTS: language.Words = {
    "zh": "  - 边缘结构模型系数：{said}",
    "en": "  - Marginal structural model coefficients: {said}",
}
_BOOTSTRAP_COUNT: language.Words = {
    "zh": "  - bootstrap {n} 次", "en": "  - {n} bootstrap resamples"}
_OTHER_ROUTE_GFORMULA: language.Words = {
    "zh": "  - 另一条独立路线（g-公式）这次没有跑：它靠模拟而不是靠加权，"
          "两条算出来的数一致与否本身就是一个发现，这里没有这个发现",
    "en": "  - The other independent route (the g-formula) was not run this "
          "time: it works by simulation rather than by weighting, and "
          "whether the two agree is itself a finding — one that is not "
          "available here",
}


def _detail_longitudinal_ipw_msm(ne: dict, result: dict, *,
                                 lang: language.Lang | str) -> str:
    """The IPW/MSM route, its weights, and the route it was not compared to.

    The weight summary is the diagnostic that matters here: a maximum far
    above the mean means a handful of subjects carry the estimate, which no
    confidence interval built from the same weights will say.
    """
    block = ne["longitudinal_ipw_msm"]
    out = [language.fill(_IPW_MSM_HEAD, lang)]
    out += _longitudinal_common(block, lang=lang)
    if block.get("weight_mean") is not None:
        out.append(language.fill(
            _WEIGHT_SUMMARY, lang,
            kind=language.fill(_STABILIZED if block.get("stabilized")
                               else _UNSTABILIZED, lang),
            mean=_fmt(block.get("weight_mean")),
            max=_fmt(block.get("weight_max"))))
    coefficients = list(block.get("msm_coefficients") or ())
    if coefficients:
        out.append(language.fill(
            _MSM_COEFFICIENTS, lang,
            said=", ".join(_fmt(c) for c in coefficients)))
    out.append(language.fill(_BOOTSTRAP_COUNT, lang,
                             n=block.get("n_bootstrap")))
    out.append(language.fill(_OTHER_ROUTE_GFORMULA, lang))
    return "\n".join(out)


#: The four components, in the order the identity states them, each with the
#: sentence that says what a reader would have to believe for it to be large.
#: Printing ``CDE`` / ``INTref`` / ``INTmed`` / ``PIE`` alone hands a reader
#: four acronyms and asks them to look up which is which.
_FOUR_WAY_PARTS: tuple[tuple[str, language.Words, language.Words], ...] = (
    ("cde",
     {"zh": "纯直接（CDE）", "en": "pure direct (CDE)"},
     {"zh": "既不经中介、也没借助处理与中介的交互",
      "en": "neither through the mediator nor by way of any "
            "treatment-mediator interaction"}),
    ("intref",
     {"zh": "仅交互（INTref）", "en": "interaction only (INTref)"},
     {"zh": "靠处理与中介的交互，但中介本身没有被处理改变",
      "en": "by the treatment-mediator interaction, though the mediator "
            "itself was not changed by the treatment"}),
    ("intmed",
     {"zh": "交互且经中介（INTmed）",
      "en": "interaction and mediation together (INTmed)"},
     {"zh": "既靠交互，又靠处理确实改变了中介",
      "en": "by the interaction and by the treatment actually changing the "
            "mediator"}),
    ("pie",
     {"zh": "纯中介（PIE）", "en": "pure mediation (PIE)"},
     {"zh": "完全经由中介，不涉及交互",
      "en": "entirely through the mediator, with no interaction involved"}),
)

_PROP_MEDIATED: language.Words = {
    "zh": "经中介的比例", "en": "the proportion mediated"}
_PROP_INTERACTION: language.Words = {
    "zh": "涉及交互的比例", "en": "the proportion involving interaction"}
_PROP_ELIMINATED: language.Words = {
    "zh": "把中介固定住能消掉的比例",
    "en": "the proportion eliminable by holding the mediator fixed",
}
_FOUR_WAY_PART_ROW: language.Words = {
    "zh": "  - {label}：{value} —— {gloss}",
    "en": "  - {label}: {value} — {gloss}",
}
_FOUR_WAY_HEAD: language.Words = {
    "zh": "- **四分解（VanderWeele，差分尺度）**：总效应 {te} 拆成四块，"
          "四块相加等于总效应",
    "en": "- **Four-way decomposition (VanderWeele, difference scale)**: the "
          "total effect {te} splits into four parts that add back up to it",
}
_ADDITIVE_INTERACTION: language.Words = {
    "zh": "  - 相加交互 {value} —— 处理与中介同时在场时，"
          "比两者各自贡献相加多出来的部分",
    "en": "  - Additive interaction {value} — what having the treatment and "
          "the mediator both present adds over the sum of their separate "
          "contributions",
}
_WHY_SPLIT: language.Words = {
    "zh": "  - 为什么值得拆：能靠改中介去掉的只有经中介那两块，"
          "交互那部分改中介去不掉",
    "en": "  - Why the split is worth having: only the two mediated parts "
          "can be removed by acting on the mediator; the interaction part "
          "cannot",
}


def _detail_four_way_decomposition(ne: dict, result: dict, *,
                                   lang: language.Lang | str) -> str:
    """VanderWeele's split of the total effect, on the difference scale.

    Four numbers that sum to the total, and the reason for reporting them is
    that they point at different interventions: what is mediated can be
    attacked at the mediator, what is interaction cannot.
    """
    fw = ne["four_way_decomposition"]
    out = [language.fill(_FOUR_WAY_HEAD, lang,
                         te=_band(fw.get("te"), lang=lang))]
    for key, label, gloss in _FOUR_WAY_PARTS:
        said = _band(fw.get(key), lang=lang)
        if said:
            out.append(language.fill(
                _FOUR_WAY_PART_ROW, lang, label=language.fill(label, lang),
                value=said, gloss=language.fill(gloss, lang)))
    for key, label in (("prop_mediated", _PROP_MEDIATED),
                       ("prop_interaction", _PROP_INTERACTION)):
        said = _band(fw.get(key), lang=lang)
        if said:
            out.append(language.fill(
                _LABELLED_ROW, lang, label=language.fill(label, lang),
                value=said))
    if fw.get("additive_interaction") is not None:
        out.append(language.fill(_ADDITIVE_INTERACTION, lang,
                                 value=_fmt(fw["additive_interaction"])))
    out.append(language.fill(_WHY_SPLIT, lang))
    return "\n".join(out)


_FOUR_WAY_RATIO_HEAD: language.Words = {
    "zh": "- **四分解（VanderWeele，比值尺度／超额相对风险）**："
          "总相对风险 {total_rr}，超额部分 {total_err} 拆成四块",
    "en": "- **Four-way decomposition (VanderWeele, ratio scale / excess "
          "relative risk)**: total relative risk {total_rr}, of which the "
          "excess {total_err} splits into four parts",
}


def _detail_four_way_ratio(ne: dict, result: dict, *,
                           lang: language.Lang | str) -> str:
    """The same split on the excess-relative-risk scale.

    A binary outcome makes the multiplicative scale the natural one, and the
    difference-scale block beside it is a different decomposition rather than
    the same numbers rescaled.
    """
    fr = ne["four_way_ratio"]
    out = [language.fill(
        _FOUR_WAY_RATIO_HEAD, lang,
        total_rr=_band(fr.get("total_rr"), lang=lang),
        total_err=_band(fr.get("total_err"), lang=lang))]
    for key, label, gloss in _FOUR_WAY_PARTS:
        said = _band(fr.get(f"err_{key}"), lang=lang)
        if said:
            out.append(language.fill(
                _FOUR_WAY_PART_ROW, lang, label=language.fill(label, lang),
                value=said, gloss=language.fill(gloss, lang)))
    for key, label in (("prop_mediated", _PROP_MEDIATED),
                       ("prop_interaction", _PROP_INTERACTION),
                       ("prop_eliminated", _PROP_ELIMINATED)):
        said = _band(fr.get(key), lang=lang)
        if said:
            out.append(language.fill(
                _LABELLED_ROW, lang, label=language.fill(label, lang),
                value=said))
    out.append(language.fill(
        _NOTE_ROW, lang,
        note=envelope_glossary.four_way_mediator_scale_word(
            fr.get("mediator_scale"), lang)))
    return "\n".join(out)


_FOUR_WAY_UNAVAILABLE: language.Words = {
    "zh": "- **四分解没有给出**：{reason} —— "
          "是算过之后判定在这种数据形状下不成立，不是没算",
    "en": "- **No four-way decomposition is given**: {reason} — it was "
          "computed and then judged not to hold for data of this shape, "
          "rather than never attempted",
}
_REASON_UNSTATED: language.Words = {
    "zh": "未说明原因", "en": "no reason stated"}


def _detail_four_way_unavailable(ne: dict, result: dict, *,
                                 lang: language.Lang | str) -> str:
    """Why the difference-scale split was attempted and withheld.

    A reader who is shown no decomposition cannot tell "not applicable here"
    from "nobody tried", and those call for different next steps.
    """
    reason = ne["four_way_unavailable"].get("reason")
    return language.fill(
        _FOUR_WAY_UNAVAILABLE, lang,
        reason=str(reason) if reason else language.fill(_REASON_UNSTATED,
                                                        lang))


_THETA_WALD_CUT: language.Words = {
    "zh": "，按 {order} 依次切）",
    "en": ", cut by {order} in that order)",
}
_THETA_WALD_UNCONDITIONAL: language.Words = {
    "zh": "，工具无条件）", "en": ", with an unconditional instrument)"}
_THETA_WALD_HEAD: language.Words = {
    "zh": "- **Wald 比值的逐格明细**（{count} 格{cut}：LATE = 加权结局差 "
          "{outcome_shift} ÷ 加权处理差 {treatment_shift} = {late}；"
          "分母就是依从者（会被工具推动的那部分人）占比，"
          "聚合的是两个加权和之比，不是各格比值的平均",
    "en": "- **The Wald ratio, cell by cell** ({count} cells{cut}: LATE = "
          "weighted outcome shift {outcome_shift} ÷ weighted treatment shift "
          "{treatment_shift} = {late}; the denominator is the share of "
          "compliers — the people the instrument moves — and what is "
          "aggregated is a ratio of two weighted sums rather than an average "
          "of per-cell ratios",
}
_THETA_STRATUM_ROW: language.Words = {
    "zh": "  - {cell}：权重 {weight}；工具取高时 P(结局)={py_high}、"
          "P(处理)={px_high}，取低时 P(结局)={py_low}、P(处理)={px_low}",
    "en": "  - {cell}: weight {weight}; with the instrument high, "
          "P(outcome)={py_high} and P(treatment)={px_high}; with it low, "
          "P(outcome)={py_low} and P(treatment)={px_low}",
}


def _detail_theta_wald(block: dict, result: dict, *,
                       lang: language.Lang | str) -> str:
    """The Wald ratio's cells when the instrument was evaluated against theta.

    The same table ``_detail_stratified_wald`` states for the data path, and
    the block's own ``late_caveat`` is what makes the omission a contradiction
    rather than a thin patch: that caveat is printed at the reader, in full,
    saying the value "aggregates the per-stratum LATEs in ``strata``" and that
    ``treatment_shift`` is the complier share — two fields the reader was then
    given no way to see.

    What each stratum contributes is the pair of conditional probabilities its
    two shifts are differences of. There are no counts to report because
    nothing was sampled: these come from a declared joint distribution.
    """
    nm = block["numeric"]
    order = list(nm.get("conditioning_order") or ())
    strata = list(nm.get("strata") or ())
    joiner = language.fill(language.BETWEEN_ITEMS, lang)
    head = language.fill(
        _THETA_WALD_HEAD, lang, count=len(strata),
        cut=(language.fill(_THETA_WALD_CUT, lang,
                           order=joiner.join(str(name) for name in order))
             if order else language.fill(_THETA_WALD_UNCONDITIONAL, lang)),
        outcome_shift=_fmt(nm.get("outcome_shift")),
        treatment_shift=_fmt(nm.get("treatment_shift")),
        late=_fmt(nm.get("late")))
    out = []
    for s in strata:
        cell = joiner.join(
            f"{name}={value}"
            for name, value in zip(order, s.get("values") or ())
        ) or language.fill(_UNCONDITIONAL_CELL, lang)
        out.append(language.fill(
            _THETA_STRATUM_ROW, lang, cell=cell,
            weight=_fmt(s.get("weight")),
            py_high=_fmt(s.get("p_y_given_z_treated")),
            px_high=_fmt(s.get("p_x_given_z_treated")),
            py_low=_fmt(s.get("p_y_given_z_control")),
            px_low=_fmt(s.get("p_x_given_z_control"))))
    return "\n".join([head] + out)


_STATUS_UNSTATED: language.Words = {"zh": "未说明", "en": "not stated"}
_AT_MEDIATOR_VALUE: language.Words = {
    "zh": "（中介固定在 {value} 时）",
    "en": " (with the mediator held at {value})",
}
_ARM_NO_NUMBER: language.Words = {
    "zh": "  - {arm} 这一支**没能算出数**{where}：{what}",
    "en": "  - The {arm} arm **produced no number**{where}: {what}",
}
_MISSING_KEY: language.Words = {
    "zh": "；缺的是 {key}", "en": "; what is missing is {key}"}
_REFERENCE_POINT_CAP: language.Words = {
    "zh": "（中介参考点有 {count} 个，超过上限 {cap}）",
    "en": " ({count} mediator reference points, over the cap of {cap})",
}


def _theta_mediation_status(status: dict, arm: language.Words, *,
                            lang: language.Lang | str) -> str:
    """Why one arm produced no numbers — the diagnostic, not silence.

    An arm the graph says is identifiable and the distribution cannot answer
    is a different situation from one the graph refuses, and the route block
    above states only the first. Without this the reader sees the arm called
    identifiable and then simply not there.
    """
    what = (gaps.said(status, lang) or status.get("status")
            or language.fill(_STATUS_UNSTATED, lang))
    missing = status.get("missing_key")
    at = status.get("mediator_value")
    said = language.fill(
        _ARM_NO_NUMBER, lang, arm=language.fill(arm, lang),
        where=(language.fill(_AT_MEDIATOR_VALUE, lang, value=at) if at
               else ""),
        what=what)
    if missing:
        said += language.fill(_MISSING_KEY, lang, key=missing)
    count, cap = status.get("reference_point_count"), status.get("cap")
    if count is not None and cap is not None:
        said += language.fill(_REFERENCE_POINT_CAP, lang, count=count,
                              cap=cap)
    return said


_THETA_MEDIATION_HEAD: language.Words = {
    "zh": "- **中介分解的数**（对着你声明的概率直接算，不是从数据估的）：",
    "en": "- **The mediation decomposition's numbers** (computed directly "
          "against the probabilities you declared, not estimated from "
          "data):",
}
_TOTAL_EFFECT_ROW: language.Words = {
    "zh": "  - 总效应 TE = {te}　（E[Y|全处理]={treated} − "
          "E[Y|全对照]={control}）",
    "en": "  - Total effect TE = {te}  (E[Y|all treated]={treated} − "
          "E[Y|all control]={control})",
}
_AGAINST_CONTROL: language.Words = {
    "zh": "以对照为参照", "en": "Against the control"}
_AGAINST_TREATED: language.Words = {
    "zh": "以处理为参照", "en": "Against the treated"}
_NDE_NIE_ROW: language.Words = {
    "zh": "  - {label}：直接效应 NDE={nde} ＋ 经中介的间接效应 NIE={nie}　"
          "（跨世界量 {cross}）",
    "en": "  - {label}: direct effect NDE={nde} + indirect effect through "
          "the mediator NIE={nie}  (cross-world quantity {cross})",
}
_OPPOSITE_DIRECTIONS: language.Words = {
    "zh": "　—— **两条通路方向相反**：一条在推高、另一条在压低，"
          "总效应是相互抵消之后剩下的那点",
    "en": "  — **the two pathways run in opposite directions**: one pushes "
          "up and the other pushes down, and the total effect is what is "
          "left after they cancel",
}
_CDE_AT: language.Words = {
    "zh": "  - 把中介固定在 {value} 时的直接效应 CDE = {number}",
    "en": "  - With the mediator held at {value}, the direct effect "
          "CDE = {number}",
}
_CDE_SIGN_FLIPS: language.Words = {
    "zh": "  - CDE 随中介取值**变号** —— 处理与中介之间存在交互，"
          "「直接效应」这句话本身要看中介被固定在哪里才成立",
    "en": "  - The CDE **changes sign** with the mediator's value — there is "
          "a treatment-mediator interaction, and \u201cthe direct "
          "effect\u201d is only a statement once the mediator is held "
          "somewhere",
}
_NDE_NIE_ARM: language.Words = {
    "zh": "自然直接/间接效应 NDE / NIE",
    "en": "natural direct / indirect effect NDE / NIE",
}
_CDE_ARM: language.Words = {
    "zh": "受控直接效应 CDE", "en": "controlled direct effect CDE"}
_THETA_MEDIATION_REFERENCES = (
    ("nde_at_control", "nie_at_treated", _AGAINST_CONTROL,
     "e_y_cross_treated_outer"),
    ("nde_at_treated", "nie_at_control", _AGAINST_TREATED,
     "e_y_cross_control_outer"),
)


def _detail_theta_mediation(block: dict, result: dict, *,
                            lang: language.Lang | str) -> str:
    """The decomposition itself, when it was computed against theta.

    The headline is TE, one number, and a mediation analysis is not one
    number: the two Pearl decompositions can disagree with each other, and the
    direct and indirect arms can point in OPPOSITE directions, which is the
    finding such an analysis exists to produce. The route block above says
    which arms are identifiable; this says what they came to.

    Stated here rather than as the answer because the headline already carries
    TE and because ``four_way_decomposition`` — the other split of the same
    total — is stated here too. A reader comparing the two reads one section.
    """
    nm = block["numeric"]
    out = [language.fill(_THETA_MEDIATION_HEAD, lang)]
    te = nm.get("te")
    if te is not None:
        out.append(language.fill(
            _TOTAL_EFFECT_ROW, lang, te=_fmt(te),
            treated=_fmt(nm.get("e_y_treated")),
            control=_fmt(nm.get("e_y_control"))))
    for direct, indirect, label, cross in _THETA_MEDIATION_REFERENCES:
        nde, nie = nm.get(direct), nm.get(indirect)
        if nde is None or nie is None:
            continue
        said = language.fill(
            _NDE_NIE_ROW, lang, label=language.fill(label, lang),
            nde=_fmt(nde), nie=_fmt(nie), cross=_fmt(nm.get(cross)))
        # Two numbers whose signs disagree is the whole content of a mediation
        # analysis, and it is not legible from the pair unless it is said: the
        # headline is their sum and reads as a single direction.
        if nde * nie < 0:
            said += language.fill(_OPPOSITE_DIRECTIONS, lang)
        out.append(said)
    cde = nm.get("cde") or {}
    for value, number in sorted(cde.items()):
        out.append(language.fill(_CDE_AT, lang, value=value,
                                 number=_fmt(number)))
    if len(cde) > 1 and min(cde.values()) * max(cde.values()) < 0:
        out.append(language.fill(_CDE_SIGN_FLIPS, lang))
    for key, arm in (("nde_nie_status", _NDE_NIE_ARM),
                     ("cde_status", _CDE_ARM)):
        status = nm.get(key)
        if status:
            out.append(_theta_mediation_status(status, arm, lang=lang))
    return "\n".join(out)


_THETA_TRANSPORT: language.Words = {
    "zh": "- **迁移后的数**：{value}　（用 `{source}` 的数据，"
          "算的是 `{target}` 的效应）",
    "en": "- **The transported number**: {value}  (computed from "
          "`{source}`'s data, for the effect in `{target}`)",
}


_THETA_TRANSPORT_AGREED: language.Words = {
    "zh": "；另外 {others} 个源总体各自算出同一个数，这是一次通过了的检验",
    "en": "; {others} further source populations each arrive at the same "
          "number, which is a test that passed",
}


def _detail_theta_transport(block: dict, result: dict, *,
                            lang: language.Lang | str) -> str:
    """The transported value, and which two populations it crosses.

    The route block above says the transport formula exists and on what it
    re-weights; this is the number that came out of evaluating it, and the
    two population labels are repeated here because the value means nothing
    without them — it is an estimate FOR one population FROM another.

    When more than one source domain transports, they are several estimands
    of the one quantity, so their agreement is a restriction that could have
    failed and did not. That is worth more to a reader than the number alone,
    and it is said here rather than left to be inferred from the route list.
    """
    nm = block["numeric"]
    line = language.fill(
        _THETA_TRANSPORT, lang, value=_fmt(nm.get("value")),
        source=nm.get("source_population", "?"),
        target=nm.get("target_population", "?"))
    others = int(nm.get("agreeing_sources") or 1) - 1
    if others > 0:
        line += language.fill(_THETA_TRANSPORT_AGREED, lang, others=others)
    return line


class _DetailRenderer(Protocol):
    """What one detail renderer is called with.

    Positional-only, because the container it is handed goes by different
    names in the two families — an estimate on the data path, a block on
    the theta path — and what this fixes is the SHAPE. The reader's
    language, which is the point of the protocol, arrives by keyword.
    """

    def __call__(self, node: dict, result: dict, /, *,
                 lang: language.Lang | str) -> str: ...


#: One renderer per part of the envelope that says how the NUMBER was
#: computed, in the order a reader meets them: what was aggregated, what was
#: recovered, what was corrected, what was contrasted over time, what was
#: decomposed.
#:
#: Keyed by a PATH rather than by a property name, because a key that is a
#: property name is a table about one container, and the two paragraphs above
#: are the record of what that costs: this section had to grow a second table
#: when the details turned out to live on ``numeric_estimate`` rather than
#: under ``extensions``, and the comment there says "at ten, appending stops
#: being a repair" — then keyed the new table on one container too. What fell
#: outside both is the theta path: four route blocks carry a ``numeric``
#: holding what was computed from a declared joint distribution, none of it
#: reaching a reader, while the data path's identical breakdown was stated in
#: full. ``iv_identification.numeric`` and ``numeric_estimate.stratified_wald``
#: are the same table of the same strata; only the container differed.
_NUMERIC_DETAIL_RENDERERS: tuple[tuple[str, _DetailRenderer], ...] = (
    ("numeric_estimate.stratified_wald", _detail_stratified_wald),
    ("numeric_estimate.recovered_ate", _detail_recovered_ate),
    ("numeric_estimate.selection_recovery_numeric",
     _detail_selection_recovery_numeric),
    ("numeric_estimate.measurement_correction", _detail_measurement_correction),
    ("numeric_estimate.regression_calibration", _detail_regression_calibration),
    ("numeric_estimate.longitudinal_gformula", _detail_longitudinal_gformula),
    ("numeric_estimate.longitudinal_ipw_msm", _detail_longitudinal_ipw_msm),
    ("numeric_estimate.four_way_decomposition", _detail_four_way_decomposition),
    ("numeric_estimate.four_way_ratio", _detail_four_way_ratio),
    ("numeric_estimate.four_way_unavailable", _detail_four_way_unavailable),
    # The theta path: evaluated against a declared joint distribution rather
    # than estimated from data, which is why there is no interval on any of
    # them and no ``numeric_estimate`` for them to hang under.
    ("extensions.iv_identification.numeric", _detail_theta_wald),
    ("extensions.mediation_decomposition.numeric", _detail_theta_mediation),
    # One renderer, two paths: the joint block's ``numeric`` is a ``$ref`` to
    # the single-mediator one, filled by the same evaluator.
    ("extensions.mediation_joint_decomposition.numeric",
     _detail_theta_mediation),
    ("extensions.transport_identification.numeric", _detail_theta_transport),
)


def _render_numeric_detail(result: dict, *,
                           lang: language.Lang | str) -> list[str]:
    """What produced the number, for whichever parts are present.

    Every one of these is exclusive to a single route, so at most two fire on
    any envelope (the two four-way scales are the pair that can co-occur). A
    part with nothing in it prints nothing rather than a heading over an empty
    line.
    """
    out = []
    for path, render in _NUMERIC_DETAIL_RENDERERS:
        steps = path.split(".")
        node: dict = result
        for step in steps[:-1]:
            node = node.get(step) or {}
            if not isinstance(node, dict):
                node = {}
        if node.get(steps[-1]):
            out.append(render(node, result, lang=lang))
    return out


def _render_derivation_chain(result: dict, *,
                             lang: language.Lang | str) -> str:
    """The steps, in the order they ran, each said in words.

    The universal answer to this section's question, and the one it never
    read. A route is written as a BLOCK only by the identification
    patterns that produce one; every other way of arriving at a number —
    a d-separation verdict, the Tian-Pearl formulas,
    abduction-action-prediction — records what it did in ``step.rule``,
    which is a first-class field of every answered result. Binding the
    section to the block family therefore left it empty for six query
    kinds, the same way binding it to blocks left ``formula`` out; and
    the verification section made the omission plain by telling the
    reader there are N steps without ever saying what they were.

    Rendered for every result that has one, not as a fallback when the
    blocks said nothing. A fallback would hide exactly this: a path whose
    blocks say a little would keep looking answered.

    A step's sentence comes from its RULE, and a rule can have more than one
    route through it — the counterfactual cell reaches an interval by a
    consistency identity or over an instrument's response polytope under the
    same rule name. Which one ran is in the step's licence, and where the
    step recorded one it is said here, because a sentence covering both
    routes is the most a rule-keyed glossary can honestly be.
    """
    steps = (result.get("derivation") or {}).get("steps") or []
    if not steps:
        return ""
    said = []
    for i, step in enumerate(steps, 1):
        line = language.fill(
            _DERIVATION_STEP, lang, index=i,
            said=derivation_glossary.describe(step.get("rule"), lang))
        licence = (step.get("inputs") or {}).get(
            "interventional_risk_provenance")
        if licence:
            line += language.fill(
                _DERIVATION_LICENCE, lang,
                said=risk_provenance.describe(licence, lang))
        said.append(line)
    return "\n".join([language.fill(_DERIVATION_HEAD, lang)] + said)


_DERIVATION_HEAD: language.Words = {
    "zh": "- **推导链**（每一步都可被独立重导）：",
    "en": "- **The derivation chain** (every step can be re-derived "
          "independently):",
}
_DERIVATION_STEP: language.Words = {
    "zh": "  {index}. {said}", "en": "  {index}. {said}"}
_DERIVATION_LICENCE: language.Words = {
    "zh": "——{said}", "en": " — {said}"}


def _citations(node: object, found: list[str]) -> None:
    """Every ``reference`` on the envelope, in the order first met."""
    if isinstance(node, dict):
        said = node.get("reference")
        if isinstance(said, str) and said not in found:
            found.append(said)
        for value in node.values():
            _citations(value, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _citations(item, found)


_ONE_SOURCE: language.Words = {
    "zh": "- **依据文献**：{said}", "en": "- **Sources**: {said}"}
_SOURCES: language.Words = {
    "zh": "- **依据文献**：", "en": "- **Sources**:"}


def _render_citations(result: dict, *,
                      lang: language.Lang | str) -> list[str]:
    """The paper each part of this answer implements.

    Six containers write a citation — ``scm_counterfactual``,
    ``selection_recovery`` and ``missing_data_recovery`` under
    ``extensions``, and ``decomposition``, ``four_way_decomposition``
    and ``four_way_ratio`` under ``numeric_estimate`` — and none of them
    reached a reader. Every rendering table in this file is keyed by what
    ONE container holds: the block families, the answer shapes, the
    computation details. A citation is not a field OF a container, so in
    each of the six it was some other table's subject, and six
    independent decisions dropped it with no exception anywhere.

    Hence the walk. Binding this to the containers that carry a citation
    today would render the same six and lose the seventh in the same way,
    which is the whole of what went wrong: what a reader is owed here is
    every source the answer rests on, not the sources of the parts
    somebody remembered to enumerate.
    """
    found: list[str] = []
    _citations(result, found)
    if not found:
        return []
    if len(found) == 1:
        return [language.fill(_ONE_SOURCE, lang, said=found[0])]
    return [language.fill(_SOURCES, lang)] + [
        language.fill(_SUB_ROW, lang, said=said) for said in found]


_ESTIMAND_ROW: language.Words = {
    "zh": "- **估计式**：`{formula}`", "en": "- **Estimand**: `{formula}`"}


def _render_route(result: dict, *, lang: language.Lang | str) -> str:
    """How the estimand was identified — empty when nothing said.

    Read in declaration order, so the recognised pattern leads and the
    recoverability verdicts, which qualify whatever came before them,
    come last. The order lives in :mod:`themis.blocks` rather than in a
    list here: a second list is the thing that goes stale.

    A renderer may return nothing when its block adds nothing to what a
    block above it already said; that is dropped rather than printed as
    a heading over an empty line.
    """
    extensions = result.get("extensions") or {}
    out: list[str] = []
    for block in blocks.rendered_in(blocks.Family.ROUTE):
        if not extensions.get(block):
            continue
        render: _BlockRenderer = _ROUTE_RENDERERS[block]
        out.append(render(extensions[block], result, lang=lang))
    # The estimand itself, after the route that found it: the blocks name
    # the pattern, this is the expression the pattern produced. It is a
    # field rather than a block, so the binding above — which is what
    # catches a block nobody renders — never looked at it, and for ten
    # rounds the report said "机器可读，见 result.formula" instead.
    formula = result.get("formula")
    if formula is not None:
        out.append(language.fill(_ESTIMAND_ROW, lang,
                                 formula=formula_text.render(formula)))
    # The numeric half of this section's question, after the expression and
    # before the skeleton: the blocks above say which pattern identified the
    # estimand, these say what the estimator then did with the data. They are
    # here rather than under the answer because "怎么算出来的" is the question
    # they answer, and because reading them beside the identification route is
    # what lets a reader see the two halves as one argument.
    out += _render_numeric_detail(result, lang=lang)
    # Last, because it is the skeleton and the lines above are the detail:
    # which pattern, on which set, which expression. A reader who wants
    # only the shape of the argument reads this; a reader checking it
    # reads what came before.
    out.append(_render_derivation_chain(result, lang=lang))
    # Last of all, the sources: a reader who wants to check the method
    # against the literature rather than against us needs the paper named,
    # and it is the one line here that is about none of the lines above in
    # particular.
    out += _render_citations(result, lang=lang)
    return "\n".join(line for line in out if line)


# --- causal model -------------------------------------------------------------


_EDGE_STABILITY: language.Words = {
    "zh": "，稳定度 {confidence}", "en": ", stability {confidence}"}
_EDGE_FROM_LLM: language.Words = {
    "zh": " ⟨LLM 假设，待复核{stability}⟩",
    "en": " ⟨proposed by an LLM, to be reviewed{stability}⟩",
}
_EDGE_FROM_DISCOVERY: language.Words = {
    "zh": " ⟨发现算法 {algorithm}{stability}⟩",
    "en": " ⟨discovery algorithm {algorithm}{stability}⟩",
}
_EDGE_FROM_SOURCE: language.Words = {
    "zh": " ⟨来源：{source}{stability}⟩",
    "en": " ⟨source: {source}{stability}⟩",
}


def _edge_provenance(annotations: dict | None, *,
                     lang: language.Lang | str) -> str:
    if not annotations:
        return ""
    source = annotations.get("source")
    conf = annotations.get("confidence")
    stability = (language.fill(_EDGE_STABILITY, lang,
                               confidence=f"{conf:.0%}")
                 if isinstance(conf, (int, float)) else "")
    if source is None:
        return ""
    if source == "llm_proposal":
        return language.fill(_EDGE_FROM_LLM, lang, stability=stability)
    if source.startswith("discovery:"):
        return language.fill(_EDGE_FROM_DISCOVERY, lang, stability=stability,
                             algorithm=source.split(":", 1)[1].upper())
    return language.fill(_EDGE_FROM_SOURCE, lang, stability=stability,
                         source=source)


_DIRECTED_EDGE: language.Words = {
    "zh": "- `{cause} → {effect}`{provenance}",
    "en": "- `{cause} → {effect}`{provenance}",
}
_BIDIRECTED_EDGE: language.Words = {
    "zh": "- `{left} ↔ {right}`（潜在共因）{provenance}",
    "en": "- `{left} ↔ {right}` (a latent common cause){provenance}",
}
_CAUSAL_EDGES: language.Words = {
    "zh": "**因果边**：", "en": "**Causal edges**:"}
_BIDIRECTED_EDGES: language.Words = {
    "zh": "**双向边（未观测共因）**：",
    "en": "**Bidirected edges (unobserved common causes)**:",
}
_AMBIGUOUS_DIRECTIONS: language.Words = {
    "zh": "**方向待定**（从数据无法判定，需领域知识）：",
    "en": "**Direction undecided** (the data cannot settle it; domain "
          "knowledge is needed):",
}
_SKELETON_STABILITY: language.Words = {
    "zh": "（稳定度 {confidence}）", "en": " (stability {confidence})"}
_AMBIGUOUS_EDGE: language.Words = {
    "zh": "- `{left} — {right}`{stability}",
    "en": "- `{left} — {right}`{stability}",
}
_NO_EDGES: language.Words = {
    "zh": "（未提供因果边）", "en": "(no causal edges were supplied)"}
_EDGE_LEGEND: language.Words = {
    "zh": "> 图例：⟨LLM 假设⟩ = 上游模型提出、未经证据支持；"
          "⟨发现算法⟩ = 从数据学出的提案；无标注 = 用户断言。"
          "标注为提案的边需复核。",
    "en": "> Legend: ⟨proposed by an LLM⟩ = put forward by an upstream "
          "model, unsupported by evidence; ⟨discovery algorithm⟩ = a "
          "proposal learned from the data; unmarked = asserted by you. Edges "
          "marked as proposals need review.",
}


def _render_model(program: dict, *, lang: language.Lang | str) -> str:
    directed: list[str] = []
    bidirected: list[str] = []
    for stmt in program.get("statements", []):
        kind = stmt.get("kind")
        provenance = _edge_provenance(stmt.get("annotations"), lang=lang)
        if kind == "cause":
            directed.append(language.fill(
                _DIRECTED_EDGE, lang, cause=_atom_pred(stmt.get("from")),
                effect=_atom_pred(stmt.get("to")), provenance=provenance))
        elif kind == "bidirected":
            bidirected.append(language.fill(
                _BIDIRECTED_EDGE, lang, left=_atom_pred(stmt.get("left")),
                right=_atom_pred(stmt.get("right")), provenance=provenance))

    out: list[str] = []
    if directed:
        out.append(language.fill(_CAUSAL_EDGES, lang))
        out += directed
    if bidirected:
        out.append("")
        out.append(language.fill(_BIDIRECTED_EDGES, lang))
        out += bidirected

    ambiguities = ((program.get("extensions") or {}).get("ambiguities")) or []
    if ambiguities:
        out.append("")
        out.append(language.fill(_AMBIGUOUS_DIRECTIONS, lang))
        for amb in ambiguities:
            endpoints = amb.get("endpoints") or []
            if len(endpoints) == 2:
                conf = amb.get("skeleton_confidence")
                out.append(language.fill(
                    _AMBIGUOUS_EDGE, lang, left=endpoints[0],
                    right=endpoints[1],
                    stability=(language.fill(_SKELETON_STABILITY, lang,
                                             confidence=f"{conf:.0%}")
                               if isinstance(conf, (int, float)) else "")))

    if not out:
        return language.fill(_NO_EDGES, lang)

    if any("⟨" in ln for ln in directed + bidirected):
        out.append("")
        out.append(language.fill(_EDGE_LEGEND, lang))
    return "\n".join(out)


# --- verification -------------------------------------------------------------


def _derivation_step_count(derivation) -> int | None:
    if derivation is None:
        return None
    if isinstance(derivation, list):
        return len(derivation)
    if isinstance(derivation, dict):
        steps = derivation.get("steps")
        if isinstance(steps, list):
            return len(steps)
    return None


def _call_form(row) -> str:
    return (f"themis.{row.name}(program, result)" if row.needs_program
            else f"themis.{row.name}(result)")


_AUDITS_FAILED: language.Words = {
    "zh": "✗ **{count} 项复核未通过** —— 内核照这张图各自重算，"
          "得到的和上面这份对不上。",
    "en": "✗ **{count} re-checks did not pass** — the kernel recomputed each "
          "of them from this graph, and what came out does not match what is "
          "above.",
}
_AUDITS_PASSED: language.Words = {
    "zh": "✓ **{count} 项独立复核全部通过** —— 内核不看上面的结论，"
          "照记录下来的输入各自重算了一遍。",
    "en": "✓ **All {count} independent re-checks passed** — the kernel "
          "recomputed each of them from the recorded inputs, without looking "
          "at the conclusion above.",
}
_ANSWER_RE_DERIVABLE: language.Words = {
    "zh": "上面那个答案**本身可以被独立重算**：换一份独立誊写的实现，"
          "从记录下来的输入重算一遍，对不上即报错 —— "
          "这是 Themis 与「相信算法输出」类工具的根本区别。",
    "en": "The answer above **can itself be recomputed independently**: a "
          "separately written implementation redoes it from the recorded "
          "inputs and raises when the two disagree — which is what separates "
          "Themis from a tool that asks you to trust its output.",
}
_ANSWER_NOT_RE_DERIVABLE: language.Words = {
    "zh": "**没有能重算这个答案本身的复核**（还没得出数值 / 结构结论）；"
          "下面这些复核的是它旁边的事实。",
    "en": "**No re-check recomputes the answer itself** — no numeric or "
          "structural conclusion has been reached yet; the ones below "
          "re-check facts beside it.",
}
_AUDIT_ROW: language.Words = {
    "zh": "- {mark}{says}（`{call}`）", "en": "- {mark}{says} (`{call}`)"}
_AUDIT_DID_NOT_PASS: language.Words = {
    "zh": "  - 未通过：{refusal}", "en": "  - Did not pass: {refusal}"}
_RUN_ALL_AUDITS: language.Words = {
    "zh": "一次跑完全部：`themis.audit(program, result)`。",
    "en": "To run them all at once: `themis.audit(program, result)`.",
}


def _render_verification(result: dict, audited: list[dict] | None, *,
                         lang: language.Lang | str) -> str:
    """Which independent re-checks this envelope can be put through, in the
    reader's words, stamped when the caller already ran them.

    Read off :mod:`themis.audits`, which answers "what re-derives this"
    once, rather than off the presence of a derivation. The two are
    different questions and on 878 of 2803 envelopes in one suite run they
    gave opposite answers: an interval or a recovered ATE, no chain, and a
    registered auditor that recomputes exactly that answer. Keyed on the
    chain, this section told the reader of each of those that no
    re-checkable conclusion had been reached — directly under the number it
    had just printed — and sent them to the gap-report audit, which is not
    an audit of the answer.
    """
    rows = audits.applicable(result)
    if not rows:
        return ""
    outcome = {
        row.get("audit"): row for row in (audited or []) if isinstance(row, dict)
    }
    out: list[str] = []

    if audited is not None:
        failed = [row for row in audited if not row.get("ok")]
        out.append(
            language.fill(_AUDITS_FAILED, lang, count=len(failed)) if failed
            else language.fill(_AUDITS_PASSED, lang, count=len(audited)))

    out.append(language.fill(
        _ANSWER_RE_DERIVABLE if any(row.re_derives_answer for row in rows)
        else _ANSWER_NOT_RE_DERIVABLE, lang))

    out.append("")
    for row in rows:
        got = outcome.get(row.name)
        mark = "" if got is None else ("✓ " if got.get("ok") else "✗ ")
        says = language.say(row.words, lang, unknown=language.absent(
            "no_word_for_this_token", lang, token=row.name))
        out.append(language.fill(_AUDIT_ROW, lang, mark=mark, says=says,
                                 call=_call_form(row)))
        if got is not None and not got.get("ok") and got.get("refusal"):
            out.append(language.fill(_AUDIT_DID_NOT_PASS, lang,
                                     refusal=got["refusal"]))

    if audited is None:
        out.append("")
        out.append(language.fill(_RUN_ALL_AUDITS, lang))
    return "\n".join(out)


# --- assumptions --------------------------------------------------------------


_TESTABLE: language.Words = {"zh": "可检验", "en": "testable"}
_UNTESTABLE: language.Words = {"zh": "不可检验", "en": "not testable"}
_PROVENANCE_IS: language.Words = {
    "zh": "来源 {source}", "en": "source {source}"}
_META_SEPARATOR: language.Words = {"zh": "／", "en": " / "}
_ASSUMPTION_ROW: language.Words = {
    "zh": "- **[{severity}]** {claim}　（{meta}）",
    "en": "- **[{severity}]** {claim}  ({meta})",
}


def _assumption_ledger(ledger: dict, result: dict, *,
                       lang: language.Lang | str) -> str:
    """Every load-bearing assumption, worst first.

    The two other blocks of this family are not rendered beside it and
    not missing either: ``result_orchestrator`` reads them and folds what
    they hold into this ledger before the report ever sees the envelope,
    which their ``carried_by`` says.
    """
    if not ledger.get("assumptions"):
        return ""

    out: list[str] = []
    summary = ledger_vocab.summary(ledger["assumptions"], lang)
    if summary:
        out.append(summary)
        out.append("")
    # Three closed vocabularies on one line — which part of the answer this
    # holds up, how badly it dies, and who put it there. All three used to
    # reach the reader as the identifier the kernel writes, so a line ended
    # `（assumption／来源 inherent／不可检验）`: an assumption said to be an
    # assumption, from a source called inherent.
    for a in ledger["assumptions"]:
        meta = []
        if a.get("layer"):
            meta.append(ledger_vocab.layer_word(a["layer"], lang))
        if a.get("provenance"):
            meta.append(language.fill(
                _PROVENANCE_IS, lang,
                source=ledger_vocab.provenance_word(a["provenance"], lang)))
        meta.append(language.fill(
            _TESTABLE if a.get("testable") else _UNTESTABLE, lang))
        out.append(language.fill(
            _ASSUMPTION_ROW, lang,
            severity=ledger_vocab.severity_word(a.get("severity", ""), lang),
            claim=language.spoken(a.get("claim"), lang),
            meta=language.fill(_META_SEPARATOR, lang).join(meta)))
    return "\n".join(out)


_ASSUMPTION_RENDERERS = blocks.bind(blocks.Family.ASSUMPTION, {
    blocks.Block.ASSUMPTION_LEDGER: _assumption_ledger,
})


def _render_assumptions(result: dict, *, lang: language.Lang | str) -> str:
    extensions = result.get("extensions") or {}
    out: list[str] = []
    for block in blocks.rendered_in(blocks.Family.ASSUMPTION):
        if not extensions.get(block):
            continue
        render: _BlockRenderer = _ASSUMPTION_RENDERERS[block]
        out.append(render(extensions[block], result, lang=lang))
    return "\n".join(line for line in out if line)


# --- data gaps ----------------------------------------------------------------


_STRONGEST_TIER: language.Words = {
    "zh": "当前最强答案层级：**{tier}**。",
    "en": "The strongest answer available right now: **{tier}**.",
}
_GAP_ROW: language.Words = {
    "zh": "- **[{severity}]** {description}",
    "en": "- **[{severity}]** {description}",
}
_IF_PROVIDED: language.Words = {
    "zh": "  - 补上可：{said}",
    "en": "  - Supplying it would allow: {said}",
}
_OR_ALTERNATIVES: language.Words = {
    "zh": "  - 或：{said}", "en": "  - Or: {said}"}
_NEXT_STEPS: language.Words = {
    "zh": "**下一步**：", "en": "**Next steps**:"}
_STEP_ROW: language.Words = {"zh": "- {said}", "en": "- {said}"}


def _render_gaps(result: dict, *, lang: language.Lang | str) -> str:
    dg = result.get("data_gap_report")
    if not dg:
        return ""

    out: list[str] = []
    tier = dg.get("answer_tier")
    if tier:
        out.append(language.fill(
            _STRONGEST_TIER, lang,
            tier=language.gloss(_TIER_WORDS, tier, lang)))
    entries = dg.get("gaps") or []
    summary = gaps.summary(entries, tier, lang)
    if summary:
        out.append(summary)

    shown = [g for g in entries
             if g.get("severity") in ("blocking", "important")]
    if not shown:
        shown = entries[:3]  # nothing load-bearing — show a few for context
    if shown:
        out.append("")
        for g in shown:
            out.append(language.fill(
                _GAP_ROW, lang,
                severity=language.gloss(_GAP_SEVERITY_WORDS,
                                        g.get("severity"), lang),
                description=gaps.described(g, lang)))
            buys = gaps.if_provided(g, lang)
            if buys:
                out.append(language.fill(_IF_PROVIDED, lang, said=buys))
            alts = [gaps.went(a, lang)
                    for a in g.get("alternative_paths") or []]
            if alts:
                out.append(language.fill(
                    _OR_ALTERNATIVES, lang,
                    said=language.fill(language.BETWEEN_STATEMENTS,
                                       lang).join(alts)))

    steps = gaps.next_steps(entries, lang)
    if steps:
        out.append("")
        out.append(language.fill(_NEXT_STEPS, lang))
        for s in steps:
            out.append(language.fill(_STEP_ROW, lang, said=s))
    return "\n".join(out)


# --- footer -------------------------------------------------------------------


_DERIVATION_STEPS: language.Words = {
    "zh": "推导链 {count} 步", "en": "{count} derivation steps"}
_ESTIMAND_PRODUCED: language.Words = {
    "zh": "估计式已生成", "en": "an estimand was produced"}
_COVERS: language.Words = {
    "zh": "（覆盖 {columns}）", "en": " (covering {columns})"}
_FOOTER_SEPARATOR: language.Words = {"zh": "　·　", "en": "  ·  "}
_AUDIT_FOOTER: language.Words = {
    "zh": "*审计*：{bits}", "en": "*Audit*: {bits}"}


def _render_footer(result: dict, *, lang: language.Lang | str) -> str:
    bits: list[str] = []
    qid = result.get("query_id")
    if qid:
        bits.append(f"query_id=`{qid}`")
    n_steps = _derivation_step_count(result.get("derivation"))
    if n_steps is not None:
        bits.append(language.fill(_DERIVATION_STEPS, lang, count=n_steps))
    if result.get("formula") is not None:
        bits.append(language.fill(_ESTIMAND_PRODUCED, lang))
    ne = result.get("numeric_estimate") or {}
    ctx = result.get("estimation_context") or {}
    # The digest and the columns it covers are read off the SAME container.
    # They are two different sets — the answer's and the run's — and a
    # footer that took one from each would print a fingerprint beside
    # somebody else's denominator, which is the confusion the second list
    # exists to prevent.
    fingerprinted = ne if ne.get("data_hash") else ctx
    data_hash = fingerprinted.get("data_hash")
    if data_hash:
        # What the digest is OF. Without it, two runs whose hashes differ
        # can only say "not the same run".
        columns = [c for c in (fingerprinted.get("data_columns") or [])
                   if isinstance(c, str)]
        covers = (language.fill(
            _COVERS, lang,
            columns=language.listing(columns, lang)) if columns
            else "")
        bits.append(f"data_hash=`{data_hash[:12]}…`{covers}")
    if not bits:
        return ""
    return language.fill(
        _AUDIT_FOOTER, lang,
        bits=language.fill(_FOOTER_SEPARATOR, lang).join(bits))
