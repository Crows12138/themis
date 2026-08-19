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

from typing import Callable, assert_never

from .. import answers, audits, blocks, questions, refusals, risk_provenance
# Aliased because the ledger renderer's own argument is the ledger itself,
# and a module shadowed by a local reads as the local everywhere below it.
from .. import ledger as ledger_vocab
from ..refusals import Kind
from . import derivation_glossary, envelope_glossary, formula_text


def _kind_zh(kind) -> str | None:
    """What each kind of refusal reads as, in the language of the report.

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

    The argument is whatever the envelope carried and not a :class:`Kind`,
    for the reason the registry reads wider than it writes: an envelope
    from another kernel may name a kind this one has never heard of, and
    that one gets no sentence rather than the wrong one.
    """
    try:
        known = Kind(kind)
    except ValueError:
        return None
    match known:
        case Kind.GRAPH:
            return (
                "**没有给出数值 —— 这是关于因果图的结论**：{reason}"
                "再多同样的数据也不会改变它；要改变的是图或问题本身。"
            )
        case Kind.DATA:
            return (
                "**没有给出数值 —— 这批数据支撑不住**：{reason}"
                "结构上是可识别的，缺的是数据本身能提供的支持。"
            )
        case Kind.UNBUILT:
            return (
                "**没有给出数值 —— Themis 还没有建这个情形**：{reason}"
                "问题成立、也已被识别，这是工具的边界，不是问题或数据的毛病。"
            )
        case Kind.REQUEST:
            return (
                "**没有给出数值 —— 需要你改一处输入**：{reason}"
                "改掉之后重跑即可。"
            )
        case Kind.BACKEND:
            return (
                "**没有算出数值 —— 数值例程没有返回结果**：{reason}"
                "这没有对问题或数据设计做出任何判定。"
            )
    assert_never(known)

# The badge the report leads with. Seven, because the vocabulary is seven:
# the two counterfactual statuses were absent and fell to
# ``_STATUS_BADGE.get(status, status)``, so a solved counterfactual was
# headed by the identifier while the browser's table said the words.
_STATUS_BADGE = {
    "structurally_solved": "✅ 已解决（结构层）",
    "numerically_solved": "📊 已估计（数值层）",
    "needs_investigation": "⚠️ 需补充数据 / 假设",
    "needs_assumption": "⚠️ 需补充假设",
    "outside_language": "✋ 超出可表达范围",
    "counterfactual_solved": "✅ 反事实已解",
    "counterfactual_bounded": "📐 反事实（区间）",
}

# How much a MISSING INPUT blocks an answer. The ledger's severities are a
# different vocabulary answering a different question — how the conclusion
# dies if an assumption is false — and they live with the other two fields
# of a ledger line, in :mod:`themis.ledger`. One dict held both, which is
# not wrong to read but says severity is one vocabulary when it is two; the
# browser copied that reading and took three of the six.
_GAP_SEVERITY_ZH = {
    "blocking": "阻断",
    "important": "重要",
    "informational": "提示",
}

_TIER_ZH = {"point": "点估计", "interval": "区间", "none": "暂无数值答案"}

# What a bounds interval brackets, in the reader's language. Pinned against
# the schema's own enums by tests: an interval reaches this surface as two
# numbers, and two numbers about the wrong quantity read exactly like two
# numbers about the right one.
_BOUNDS_ESTIMAND_ZH = {
    "arm_probability": "干预到所问的那一档之后，目标事件发生的概率",
}
_BOUNDS_CONTRAST_ZH = {
    "ace": "平均因果效应（ACE）",
}


def _bounds_interval(b: dict) -> str:
    return f"[{_fmt(b['lower_value'])}, {_fmt(b['upper_value'])}]"


def _bounds_rests_on(b: dict) -> str:
    """What one bounds row assumes, for a reader choosing between rows.

    An interval is unreadable beside another one until this is said: the
    two bracket the same quantity and differ only in what they were
    allowed to assume.
    """
    assumptions = b.get("assumptions") or ()
    return f"假设 {', '.join(assumptions)}" if assumptions else "无假设"


def _fmt(x) -> str:
    """Compact numeric formatting (mirrors explainer's ``.4g``)."""
    try:
        return f"{float(x):.4g}"
    except (TypeError, ValueError):
        return str(x)


def build_analysis_report(
    result: dict,
    *,
    program: dict | None = None,
    audited: list[dict] | None = None,
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
    """
    status = result.get("status", "?")
    badge = _STATUS_BADGE.get(status, status)

    parts: list[str] = ["# 因果分析报告", "", f"**状态**：{badge}", ""]

    parts += _section("问题", _render_question(result, program))
    parts += _section("答案", _render_answer(result))
    route = _render_route(result)
    if route:
        parts += _section("怎么算出来的", route)
    if program is not None:
        parts += _section("因果模型", _render_model(program))
    parts += _section("验证", _render_verification(result, audited))
    assumptions = _render_assumptions(result)
    if assumptions:
        parts += _section("假设", assumptions)
    gaps = _render_gaps(result)
    if gaps:
        parts += _section("数据缺口与下一步", gaps)

    footer = _render_footer(result)
    if footer:
        parts += ["---", "", footer, ""]

    return "\n".join(parts).rstrip() + "\n"


def _section(title: str, body: str) -> list[str]:
    return [f"## {title}", "", body, ""]


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


def _valued(a: dict) -> str:
    atom = a.get("atom", a)
    val = a.get("value")
    pred = _atom_pred(atom)
    return f"{pred}={val}" if val is not None else pred


def _q_effect(q: dict | None) -> str:
    if q is None:
        return "估计一次干预的因果效应有多大。"
    iv = _valued(q.get("intervention", {}))
    tgt = _valued(q.get("target", {}))
    line = f"估计 **干预 {iv}** 对 **{tgt}** 的因果效应。"
    given = q.get("given") or []
    if given:
        conds = "、".join(_valued(g) for g in given)
        line += f"（条件于 {conds}）"
    return line


def _q_cause(q: dict | None) -> str:
    if q is None:
        return "一个变量是否因果影响另一个变量？"
    return f"**{_atom_pred(q.get('from'))}** 是否因果影响 **{_atom_pred(q.get('to'))}**？"


def _q_assoc(q: dict | None) -> str:
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
        return "两个变量在图中是否相关联？"
    line = (f"**{_atom_pred(q.get('left'))}** 与 **{_atom_pred(q.get('right'))}** "
            f"是否（在图中）相关联？")
    given = q.get("given") or []
    if given:
        line += f"（条件于 {'、'.join(_atom_pred(g) for g in given)}）"
    return line


def _q_identify(q: dict | None) -> str:
    if q is None:
        return "目标效应是否可从观测数据**非参数识别**？"
    iv = _valued(q.get("intervention", {}))
    tgt = _valued(q.get("target", {}))
    return f"**干预 {iv}** 对 **{tgt}** 的效应，是否可从观测数据**非参数识别**？"


def _q_probability(q: dict | None) -> str:
    if q is None:
        return "求某个事件在模型下的概率。"
    line = f"求 **{_valued(q.get('target', {}))}** 的概率。"
    given = q.get("given") or []
    if given:
        line += f"（条件于 {'、'.join(_valued(g) for g in given)}）"
    return line


def _q_counterfactual(q: dict | None) -> str:
    if q is None:
        return "求反事实联合分布中某一格的值。"
    # ``observed`` is one grounded atom, not a list — the schema settles
    # this and intuition gets it wrong, the same way ``assoc`` carries
    # ``left`` / ``right`` where the branch above it reads ``from`` / ``to``.
    return (f"已知 **{_valued(q.get('observed', {}))}**，若当初 "
            f"**{_valued(q.get('counterfactual_intervention', {}))}**，"
            f"**{_valued(q.get('counterfactual_target', {}))}** 的概率是多少？")


def _q_causation(q: dict | None) -> str:
    if q is None:
        return "求归因概率 —— 必要性 PN / 充分性 PS / PNS。"
    return (f"**{_atom_pred(q.get('cause'))}** 对 **{_atom_pred(q.get('effect'))}** 的"
            f"归因概率 —— 必要性 PN / 充分性 PS / 两者兼备 PNS。")


def _q_scm_counterfactual(q: dict | None) -> str:
    if q is None:
        return "在线性结构方程模型下，求某个个体的反事实结局。"
    return (f"在线性结构方程模型下，若这个个体当初 "
            f"**{_valued(q.get('intervention', {}))}**，"
            f"其 **{_valued(q.get('target', {}))}** 会是多少？")


def _q_counterfactual_conjunction(q: dict | None) -> str:
    if q is None:
        return "求多个反事实事件同时成立的概率。"
    n = len(q.get("events") or [])
    line = ("求这 1 个反事实事件的概率。" if n == 1
            else f"求 {n} 个反事实事件**同时成立**的概率。")
    if q.get("condition"):
        line += f"（以另外 {len(q['condition'])} 个反事实事件为条件）"
    return line


def _q_proximal_effect(q: dict | None) -> str:
    if q is None:
        return "用代理变量校正未测混杂后，求因果效应。"
    return (f"**{_atom_pred(q.get('treatment'))}** 对 "
            f"**{_atom_pred(q.get('outcome'))}** 的效应 —— 混杂 "
            f"**{_atom_pred(q.get('latent'))}** 没有数据，用代理 "
            f"**{_atom_pred(q.get('treatment_proxy'))}** / "
            f"**{_atom_pred(q.get('outcome_proxy'))}** 把它校正掉。")


_QUESTION_LINES = questions.bind({
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


def _render_question(result: dict, program: dict | None) -> str:
    q = _find_query(program, result.get("query_id"))
    kind = result.get("query_kind") or (q or {}).get("kind")
    if q is not None and q.get("kind") != kind:
        # A query of another kind carries other fields; handing it to this
        # kind's renderer is how both of today's question-line bugs read.
        # Reachable only when the result names no query_id and the program
        # leads with a different question.
        q = None
    return _QUESTION_LINES[questions.reading_of(kind)](q)


# --- answer -------------------------------------------------------------------


def _render_answer(result: dict) -> str:
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
            return _ANSWER_RENDERERS[shape](ne, result)

    # 2. The theta path, whose answer is a block. Above the bare value
    #    below it because that value is a headline drawn FROM the block —
    #    for causation, one of the three quantities it holds, and the
    #    headline cannot say which one it is.
    extensions = result.get("extensions") or {}
    for block in blocks.rendered_in(blocks.ANSWER):
        if extensions.get(block):
            said = _ANSWER_BLOCK_RENDERERS[block](extensions[block], result)
            if said:
                return said

    # 3. Symbolic numeric value, for the paths that carry no block.
    if nr and nr.get("value") is not None:
        line = f"**{_fmt(nr['value'])}**"
        iv = nr.get("interval")
        if iv and len(iv) == 2:
            line += f"（区间 [{_fmt(iv[0])}, {_fmt(iv[1])}]）"
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
        estimand = _BOUNDS_ESTIMAND_ZH.get(
            str(evaluated[0].get("estimand")), "所问的量")
        if len(evaluated) == 1:
            said = (
                f"给出**区间** {_bounds_interval(evaluated[0])}"
                f"——{estimand}（部分识别的界，不是点估计；"
                f"method=`{evaluated[0].get('method', 'bounds')}`）。"
            )
        else:
            rows = "；".join(
                f"`{b.get('method', 'bounds')}`"
                f"（{_bounds_rests_on(b)}）{_bounds_interval(b)}"
                for b in evaluated
            )
            said = (
                f"给出**区间**——{estimand}（部分识别的界，不是点估计）。"
                f"共 {len(evaluated)} 条，界定的是同一个量，各自靠不同的假设："
                f"{rows}。按你接受哪组假设来读，不要取交。"
            )
        for b in evaluated:
            contrast = b.get("contrast")
            if isinstance(contrast, dict) and contrast.get("lower_value") is not None:
                said += (
                    f"同一批数据还给出"
                    f"**{_BOUNDS_CONTRAST_ZH.get(str(contrast.get('kind')), '对照')}**"
                    f" [{_fmt(contrast['lower_value'])}, {_fmt(contrast['upper_value'])}]"
                    f"——与 `{contrast.get('reference_value')}` 那条臂相比的差值，"
                    f"它是另一个量，不是上面两个端点相减。"
                )
        return said

    # 5. A refusal, which is an answer. Below the numeric branches, not
    #    above: dispatch attaches a refusal for a SUPPLEMENTARY estimate
    #    (the longitudinal path attaches to the first effect result) to a
    #    result that may already carry a genuine point or interval, and
    #    that number is still the answer there.
    failure = result.get("estimator_failure")
    if isinstance(failure, dict) and failure.get("failure_type"):
        reason = (failure.get("reason") or "").strip().rstrip(".")
        if reason and reason[-1] not in "。！？!?":
            reason += "。"
        template = _kind_zh(failure.get("kind"))
        line = (
            template.format(reason=reason) if template
            else f"**没有给出数值**：{reason}"
        )
        # "来自" rather than "估计器": identification refuses through this
        # same field, and it is not an estimator.
        return (
            f"{line}（来自 `{failure.get('estimator', '?')}`，"
            f"拒答类型 `{failure['failure_type']}`）"
        )

    # 5b. An estimate block carrying no answer at all. Stated here rather
    #     than falling through, because what it would fall to is a verdict
    #     about the graph standing in for the number that was asked for —
    #     the substitution the shape table removes, in the one case the
    #     table itself cannot rule out.
    if ne:
        return (
            f"**没有给出数值**：估计器 `{ne.get('method', '?')}` 返回的估计块里"
            "没有任何可呈现的答案。"
        )

    # 6. The structural verdict, read as the proposition it asserts rather
    #    than as a bare 是 / 否. Which proposition that is depends on what
    #    was asked, and the boolean cannot say — it is the same field for
    #    a cause query, where it is the answer, and for an effect query,
    #    where it is a precondition (:mod:`themis.questions`).
    reading = questions.reading_of(result.get("query_kind"))
    if sr and sr.get("value") is not None:
        val = sr["value"]
        paths = sr.get("supporting_paths") or []
        note = f"（支持路径 {len(paths)} 条）" if paths else ""
        if val is not True and val is not False:
            # The schema admits a string here; no producer writes one.
            return f"结论：**{val}**{note}"
        settled = _VERDICT_ZH[reading][0 if val else 1]
        if reading.verdict_is_the_answer:
            return f"结论：**{'是' if val else '否'}** —— {settled}{note}"
        if val is False:
            # Not a weak answer to "how large is it": the quantity cannot
            # be obtained at all, and saying so IS the answer. A bare 否
            # was not even a sentence about the question that was asked.
            return f"**{settled}** —— 问的是一个数，而这个量从当前的图与假设里得不出来。"
        # Identifiable. The number's absence has some other cause, and the
        # branches below know which — this branch used to answer here and
        # 34 results in one suite run carried a ``formula``, so the line
        # they needed was already written directly underneath.

    # 7. Identified but needs data, or genuinely blocked. The proposition
    #    comes from the same table: this line said "效应可识别" to five
    #    ``probability`` queries in one suite run, which had asked for a
    #    probability and not for an effect.
    if result.get("formula") is not None:
        return (
            f"**{_VERDICT_ZH[reading][0]}**（估计式见下方「怎么算出来的」），但当前"
            "**没有数据** → 需要数据才能给出具体数值。所需数据见下方「数据缺口」。"
        )
    if sr and sr.get("value") is True:
        # Identification finished without producing an estimand a number
        # could be plugged into — a mediation decomposition, a proximal
        # matrix inversion. Reached only for the kinds that asked for a
        # number, since the verdict answers the others above.
        return (
            f"**{_VERDICT_ZH[reading][0]}**，但这一轮**没有给出数值** —— "
            "识别到此为止，没有产出可直接代入的估计式；要得到具体数字需要数据。"
        )
    if status in ("needs_investigation", "needs_assumption"):
        return "当前**还不能给出答案** —— 缺口与补法见下方「数据缺口」。"
    if status == "outside_language":
        return "该问题**超出 Themis 可表达 / 可识别的范围**。"
    return "（无可呈现的答案字段）"


# What the structural boolean asserts, in the reader's language. One pair
# per query kind, checked against the vocabulary at import: the fallback it
# replaces (the web's 成立 / 不成立) is what a missing entry used to look
# like, and a fallback reads exactly like coverage.
_VERDICT_ZH = questions.bind({
    questions.CAUSE: ("存在因果影响", "不存在因果影响"),
    questions.ASSOC: ("两者相关联", "两者不相关联"),
    questions.IDENTIFY: ("可从观测数据非参数识别", "无法从这张图非参数识别"),
    questions.EFFECT: ("该效应可识别", "该效应无法从这张图识别"),
    questions.PROBABILITY: ("该概率可识别", "该概率无法从这张图识别"),
    questions.COUNTERFACTUAL: ("该反事实格可识别（点或界）", "该反事实格无法识别"),
    questions.CAUSATION: ("归因概率可识别", "归因概率无法识别"),
    questions.SCM_COUNTERFACTUAL: ("该个体的反事实值可解出", "该个体的反事实值解不出"),
    questions.COUNTERFACTUAL_CONJUNCTION: (
        "联合反事实可识别", "ID* 返回 hedge —— 不可识别"),
    questions.PROXIMAL_EFFECT: ("近端识别条件成立，效应可识别", "近端识别条件不成立"),
})


_POC_LABELS = (
    ("pn", "必要性 PN（归因）"),
    ("ps", "充分性 PS"),
    ("pns", "必要且充分 PNS"),
)
"""The three quantities a causation query asks for, named once.

Two surfaces say them — the data path, where they arrive as an estimate's
bounds, and the theta path, where they arrive as a block. Named in one
place because the second was written ten rounds after the first and the
question the reader asked is the same one.
"""




def _render_causation(poc: dict, *, ci_level: float | None = None) -> str:
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
        # One pair of CI keys, two meanings, decided by the same thing that
        # decides the shape: a point's sampling interval when there is a
        # point, the outer band on the identified set when there is not.
        aside: list[str] = []
        ci_lo, ci_hi = q.get("ci_lower"), q.get("ci_upper")
        if ci_lo is not None and ci_hi is not None:
            level = f"{ci_level:.0%} " if ci_level is not None else ""
            band = "CI" if point is not None else "外带"
            aside.append(f"{level}{band} [{_fmt(ci_lo)}, {_fmt(ci_hi)}]")
        if point is not None and bounded and not folded_in:
            # Tian-Pearl bounds use no monotonicity, so this is exactly what
            # the assumption bought — the reader cannot weigh the point
            # without seeing the interval it replaced. Not sayable on the route
            # that folds the assumption into the interval: there the pair IS
            # the post-assumption answer, and this sentence would invert it.
            aside.append(f"无单调性假设时只能给到 [{_fmt(lo)}, {_fmt(hi)}]")
        lines.append(
            f"- {label}：{head}" + (f"（{'；'.join(aside)}）" if aside else "")
        )
    if not lines:
        return ""

    monotonic = bool(poc.get("monotonic"))
    pinned = any(
        (poc.get(key) or {}).get("point") is not None for key, _ in _POC_LABELS
    )
    head = (
        "单调性成立（X 从不阻止 Y），三者点识别："
        if pinned
        else "已假设单调性，但三者仍只能给界："
        if monotonic
        else "未假设单调性，三者只能给界："
    )
    # WHERE the three numbers came from — on every route, not only the ones
    # that end with a pair of risks to print. One route reaches them without
    # any: the response-function program over an instrument. Hanging this line
    # off the risks being present left that route saying nothing at all.
    prov = poc.get("interventional_risk_provenance")
    if prov:
        note = risk_provenance.describe(prov)
        adj = poc.get("adjustment")
        if adj:
            note += f"，调整集 {{{', '.join(adj)}}}"
        if poc.get("instrument"):
            note += f"，工具变量 `{poc['instrument']}`"
        risk_hi, risk_lo = poc.get("p_y_do_x1"), poc.get("p_y_do_x0")
        risks = (
            f"由干预风险 P(Y|do X)={_fmt(risk_hi)}、P(Y|do ¬X)={_fmt(risk_lo)} 算出"
            if risk_hi is not None and risk_lo is not None
            else "没有用到任何干预风险"
        )
        lines.append(f"- {risks}（{note}）")
    if not pinned and not monotonic:
        lines.append("- 若可假设单调性（X 从不阻止 Y），三者可点识别。")
    return "\n".join([head] + lines)


def _render_numeric_estimate(ne: dict, outcome_error: dict | None = None) -> str:
    point = _fmt(ne["point"])
    lines = []
    if ne.get("ci_lower") is not None and ne.get("ci_upper") is not None:
        level = ne.get("ci_level", 0.95)
        lines.append(
            f"**{point}**　（{_fmt(level * 100)}% CI [{_fmt(ne['ci_lower'])}, "
            f"{_fmt(ne['ci_upper'])}]）"
        )
    else:
        lines.append(f"**{point}**")

    lines.extend(_estimate_meta(ne, outcome_error))
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


def _estimate_meta(ne: dict, outcome_error: dict | None = None) -> list[str]:
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
        meta.append(f"方法 `{method}`")
    if n is not None:
        meta.append(f"样本量 N={n}")
    adj = ne.get("adjustment")
    if adj:
        meta.append(f"调整集 {{{', '.join(adj)}}}")
    if meta:
        lines.append("- " + "，".join(meta))

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
        level = _fmt(ar.get("ci_level", 0.95) * 100)
        lines.append(
            f"- 弱工具稳健区间（Anderson-Rubin {level}%）：{_ar_interval(ar)}"
            f" —— {envelope_glossary.ar_set_kind_zh(ar['kind'])}"
        )

    oid = ne.get("over_identification")
    if oid:
        # Hansen when it exists: it is the one that survives heteroskedasticity,
        # and reporting the homoskedastic Sargan beside it would offer the
        # reader a choice between a test and its own weaker version.
        p_value, named = oid.get("hansen_p_value"), "Hansen J，异方差稳健"
        if p_value is None:
            p_value, named = oid.get("sargan_p_value"), "Sargan"
        if p_value is not None:
            said = (
                "**数据否定了这组工具**：至少有一个工具的排除限制不成立，"
                "上面这个数建立在一个被自己的数据驳倒的前提上"
                if p_value < 0.05 else
                "数据没有否定这组工具（不通过不等于成立，只是这批数据看不出矛盾）"
            )
            lines.append(f"- 工具联合有效性（{named}）：p={_fmt(p_value)} —— {said}")

    ps = ne.get("propensity_summary")
    if ps and ps.get("raw_min") is not None:
        span = f"倾向分原始范围 [{_fmt(ps['raw_min'])}, {_fmt(ps.get('raw_max'))}]"
        trimmed, floor = ps.get("n_trimmed") or 0, ps.get("floor")
        if trimmed and floor is not None:
            lines.append(
                f"- 重叠（正性）：{span}，其中 {trimmed} 个个体被截到 "
                f"[{_fmt(floor)}, {_fmt(1 - floor)}] 之内权重才有限 —— 截掉的越多，"
                "说明处理组与对照组越难找到可比的人，这个数越依赖模型往数据外推。"
            )
        else:
            lines.append(f"- 重叠（正性）：{span}，没有个体需要截断。")

    ovb = ne.get("ovb_sensitivity")
    if ovb and ovb.get("robustness_value_q") is not None:
        tail = ""
        if ovb.get("robustness_value_qa") is not None:
            tail = (f"；解释掉 {ovb['robustness_value_qa']:.1%} 就足以让它不再"
                    f"显著（α={_fmt(ovb.get('alpha', 0.05))}）")
        lines.append(
            f"- 稳健性（未测混杂，Cinelli-Hazlett）：一个未测混杂要同时解释掉处理与"
            f"结局各 {ovb['robustness_value_q']:.1%} 的残差变异，才能把这个效应抹平"
            f"{tail}。"
        )

    pb = ne.get("precision_budget")
    if pb and pb.get("hint"):
        lines.append(f"- 精度：{pb['hint']}")

    # Printed next to the precision hint on purpose: that hint says how many
    # more subjects would halve the interval, and part of this interval is
    # measurement noise that no number of subjects removes. Saying only the
    # first sends the reader to buy the wrong thing.
    if outcome_error and outcome_error.get("se_inflation"):
        lines.append(
            f"- 结局测量误差：区间比结局测准时宽 "
            f"{outcome_error['se_inflation']:.2f} 倍（未解释变异中 "
            f"{outcome_error['noise_share']:.0%} 是测量噪声）；点估计不受影响，"
            "但这部分宽度只能靠把结局测准、加样本量消不掉。"
        )

    sa = ne.get("sensitivity_analysis")
    if sa and sa.get("note"):
        lines.append(f"- 稳健性（E-value）：{sa['note']}")

    return lines


def _band(part: dict | None) -> str:
    """One estimated quantity with its interval, or an empty string."""
    if not part or part.get("point") is None:
        return ""
    line = f"**{_fmt(part['point'])}**"
    if part.get("ci_lower") is not None and part.get("ci_upper") is not None:
        line += f"（CI [{_fmt(part['ci_lower'])}, {_fmt(part['ci_upper'])}]）"
    return line


def _render_dose_response_curve(ne: dict, result: dict) -> str:
    """The effect at each sampled dose, against the reference dose.

    A curve has no single number to lead with, which is exactly why probing
    for one fell through to the graph verdict.
    """
    curve = ne.get("dose_response_curve") or []
    ref = ne.get("reference_point")
    head = "剂量-反应**曲线**"
    if ref is not None:
        head += f"（相对参考剂量 x={_fmt(ref)}）"
    lines = [head + f"，共 {len(curve)} 个采样剂量："]
    shown = curve[:6]
    for pt in shown:
        seg = f"- x={_fmt(pt.get('x'))}：{_fmt(pt.get('effect'))}"
        if pt.get("ci_lower") is not None and pt.get("ci_upper") is not None:
            seg += f"（CI [{_fmt(pt['ci_lower'])}, {_fmt(pt['ci_upper'])}]）"
        lines.append(seg)
    if len(curve) > len(shown):
        lines.append(f"- …（其余 {len(curve) - len(shown)} 个剂量见 `numeric_estimate`）")
    lines.extend(_estimate_meta(ne, result.get("outcome_error")))
    return "\n".join(lines)


def _render_mediation_decomposition(ne: dict, result: dict) -> str:
    """Total effect split into what runs through the mediator and what does not."""
    d = ne.get("decomposition") or {}
    lines = ["效应**分解**（总效应 = 直接 + 间接）："]
    for key, label in (
        ("te", "总效应 TE"),
        ("nde", "自然直接效应 NDE（不经中介）"),
        ("nie", "自然间接效应 NIE（经中介）"),
    ):
        band = _band(d.get(key))
        if band:
            lines.append(f"- {label}：{band}")
    pm = _band(d.get("proportion_mediated"))
    if pm:
        lines.append(f"- 中介占比：{pm}")
    cde = d.get("cde") or {}
    for key, label in (
        ("reference_control", "控制直接效应 CDE（中介固定在参考值）"),
        ("reference_treated", "控制直接效应 CDE（中介固定在处理值）"),
    ):
        band = _band(cde.get(key))
        if band:
            lines.append(f"- {label}：{band}")
    lines.extend(_estimate_meta(ne, result.get("outcome_error")))
    return "\n".join(lines)


def _render_joint_contrast(ne: dict, result: dict) -> str:
    """The contrast between two joint corners, plus what riding together adds."""
    joint = ne.get("joint_effect") or {}
    lines = []
    band = _band(joint)
    corners = ""
    treated, control = joint.get("treated") or {}, joint.get("control") or {}
    if treated and control:
        corners = (
            f"（{_corner(treated)} 对比 {_corner(control)}）"
        )
    lines.append(f"**联合干预对比**{corners}：{band}" if band else "**联合干预对比**")

    inter = ne.get("interaction")
    if inter and inter.get("point") is not None:
        order = inter.get("order")
        lines.append(
            f"- {order} 阶交互（{inter.get('scale', '差值')} 尺度）："
            f"{_band(inter)} —— 各处理一起上，比各自效应之和多出来的部分"
        )
    unavailable = ne.get("interaction_unavailable")
    if unavailable:
        lines.append(
            f"- {unavailable.get('order', '')} 阶交互**给不出**："
            f"{unavailable.get('reason', '')}"
        )
    lines.extend(_estimate_meta(ne, result.get("outcome_error")))
    return "\n".join(lines)


def _corner(corner: dict) -> str:
    return "{" + ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(corner.items())) + "}"


def _render_counterfactual_cell_bounds(ne: dict, result: dict) -> str:
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
        lines.append(f"该反事实格的**区间** [{_fmt(lo)}, {_fmt(hi)}]（界，不是点）")
    else:
        lines.append("该反事实格没有给出可呈现的界。")
    prov = cell.get("interventional_risk_provenance")
    if prov:
        note = risk_provenance.describe(prov)
        if cell.get("instrument"):
            note += f"，工具变量 `{cell['instrument']}`"
        lines.append(f"- {note}")
    adj = cell.get("adjustment")
    if adj:
        lines.append(f"- 干预风险经后门调整集 {{{', '.join(adj)}}} 识别")
    if not cell.get("monotonicity"):
        lines.append(
            "- 若可假设单调性（X 从不阻止 Y），这一格会被收紧——"
            "在干预风险已知时收紧成一个点。"
        )
    lines.extend(_estimate_meta(ne, result.get("outcome_error")))
    return "\n".join(lines)


def _render_causation_estimate(ne: dict, result: dict) -> str:
    """Both causation shapes, from the one renderer that says the names.

    Bound twice on purpose. Point-identified and bounded are two shapes of
    the same three quantities, and what separates them — a point inside
    each — is exactly what the renderer already keys off, so a second copy
    would be a second chance to say them differently.
    """
    return "\n".join(
        [_render_causation(ne["probabilities_of_causation"],
                           ci_level=ne.get("ci_level"))]
        + _estimate_meta(ne, result.get("outcome_error"))
    )


# Each shape, said once. ``bind`` refuses a set that misses one, so a shape
# added to the vocabulary cannot reach this surface and render nothing.
_ANSWER_RENDERERS = answers.bind({
    answers.POINT:
        lambda ne, result: _render_numeric_estimate(ne, result.get("outcome_error")),
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


def _answer_causation(block: dict, result: dict) -> str:
    """The theta path's three quantities, said the way the data path says
    them — the block and the estimate carry the same envelope."""
    return _render_causation(block)


def _answer_scm_counterfactual(block: dict, result: dict) -> str:
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
    lines = [f"**{_fmt(value)}**　（{target}，在该个体自身的外生扰动下）"]

    noise = block.get("abducted_noise") or {}
    if noise:
        items = "，".join(
            f"U_{name}={_fmt(v)}" for name, v in sorted(noise.items())
        )
        lines.append(f"- 从观测值反推出的个体扰动：{items}")
    cf = block.get("counterfactual_values") or {}
    others = {k: v for k, v in cf.items() if k != target}
    if others:
        items = "，".join(f"{k}={_fmt(v)}" for k, v in sorted(others.items()))
        lines.append(f"- 同一反事实世界下的其他变量：{items}")
    return "\n".join(lines)


# Each block of this family that no other channel carries, said once.
_ANSWER_BLOCK_RENDERERS = blocks.bind(blocks.ANSWER, {
    blocks.CAUSATION: _answer_causation,
    blocks.SCM_COUNTERFACTUAL: _answer_scm_counterfactual,
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


_PATTERN_ZH = {
    "backdoor": "后门调整",
    "front_door": "前门调整",
    "c_factor": "ID 算法的一般解（c-factor 分解）",
    "instrumental_variable": "工具变量",
}
"""What each recognised pattern is called for a reader.

An unlisted pattern renders as its own token rather than falling to a
default: this section exists because something said nothing, and a name a
reader has to look up still beats a sentence that omits it. The producer
(``scheduler._recognize_identification_pattern``) emits the first three;
the IV path writes the fourth.
"""


def _route_identification(block: dict, result: dict) -> str:
    pattern = block.get("pattern", "?")
    line = f"- **识别模式**：{_PATTERN_ZH.get(pattern, f'`{pattern}`')}"
    if pattern == "backdoor":
        adj = block.get("adjustment_set")
        line += (
            f" —— 控制 {_vars(adj)}" if adj
            else " —— 无需控制任何变量：图里没有开放的后门路径"
        )
    elif pattern == "front_door":
        line += f" —— 经中介 {_vars(block.get('mediator_set'))}"
    elif pattern == "instrumental_variable":
        line += f" —— 工具 `{block.get('instrument', '?')}`"
        cond = block.get("conditioning")
        if cond:
            line += f"，在 {_vars(cond)} 条件下有效"
    if block.get("conditioned_on"):
        line += f"；问题本身条件于 {_vars(block['conditioned_on'])}"
    if block.get("estimand") == "conditional_idc_ratio":
        line += "（条件估计量，走 IDC 比值而非单纯调整）"
    if block.get("required_assumption"):
        line += f"。点识别另需：{block['required_assumption']}"
    return line


def _route_iv_identification(block: dict, result: dict) -> str:
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
        ((result.get("extensions") or {}).get(blocks.IDENTIFICATION) or {})
        .get("pattern") == "instrumental_variable"
    )
    parts: list[str] = []
    if not already_said:
        head = f"`{block.get('instrument', '?')}`"
        cond = block.get("conditioning")
        if cond:
            head += f"，在 {_vars(cond)} 条件下有效"
        parts.append(head)
    n = block.get("alternatives_count")
    if isinstance(n, int) and n > 1:
        parts.append(f"图中共有 {n} 个候选工具，取的是这一个")
    caveat = block.get("late_caveat")
    if not parts and not caveat:
        return ""
    lines = ["- **工具变量**：" + ("；".join(parts) if parts else str(caveat))]
    if parts and caveat:
        lines.append(f"  - {caveat}")
    return "\n".join(lines)


def _route_transport_identification(block: dict, result: dict) -> str:
    src = block.get("source_population") or "源总体"
    tgt = block.get("target_population") or "目标总体"
    line = f"- **跨总体迁移**：从 `{src}` 迁到 `{tgt}`"
    s_nodes = [
        (sn.get("affects") or {}).get("predicate", "?")
        for sn in (block.get("s_nodes") or ())
    ]
    if s_nodes:
        line += f"；两地分布不同的是 {_vars(s_nodes)}"
    adj = block.get("adjustment_set")
    if adj:
        line += f"，靠 {_atoms(adj)} 上的重加权抹平"
    return line


def _route_joint_identification(block: dict, result: dict) -> str:
    line = f"- **联合干预**：同时干预 {_vars(block.get('treatments'))}"
    if block.get("pattern") == "joint_general_id":
        line += "，无可用调整集，由集合版 ID 算法识别"
    else:
        adj = block.get("adjustment_set")
        line += (
            f"，经联合后门调整集 {_vars(adj)} 识别" if adj
            else "，联合后门无需调整"
        )
    if block.get("conditioned_on"):
        line += f"；条件于 {_vars(block['conditioned_on'])}"
    if block.get("interaction"):
        line += "。交互项在差值尺度上给出 —— 逐个单独干预再相加是拿不到它的"
    return line


def _route_longitudinal_identification(block: dict, result: dict) -> str:
    treatments = [str(t) for t in (block.get("treatments") or ())]
    line = (
        f"- **时变处理（g-formula）**：处理序列 "
        f"{' → '.join(f'`{t}`' for t in treatments) or '（空）'}"
        f" 对 `{block.get('outcome', '?')}`"
    )
    by_time = block.get("confounders_by_time") or []
    if by_time:
        line += "；各时点已测混杂 " + "、".join(_vars(b) for b in by_time)
    lines = [line]
    lines.append(
        "  - 序贯可交换性成立：每个时点的处理，其后门路径都被此前测到的"
        "历史挡住了"
        if block.get("identified") else
        "  - 序贯可交换性**不成立**：某个时点的处理还有历史挡不住的后门路径，"
        "g-formula 会给出有偏的数"
    )
    return "\n".join(lines)


def _mediation_arm(info: dict | None, label: str, condition_zh) -> str:
    """One arm of a decomposition — identifiable, and on what.

    ``condition_zh`` differs per arm because the two arms fail different
    theorems: the natural decomposition on Pearl 2001's four cross-world
    conditions, the controlled one on two back-door conditions. The labels
    are drawn from disjoint sets, so one table would read as one vocabulary
    and hide that ``M4`` and ``C2`` are different statements about the same
    adjustment set.
    """
    info = info or {}
    if not info.get("identifiable"):
        why = info.get("failed_condition")
        return f"  - {label}**不可识别**" + (
            f"：{why} —— {condition_zh(why)}" if why else "")
    adj = info.get("adjustment")
    return (
        f"  - {label}可识别"
        + (f"，调整 {_vars(adj)}" if adj else "，无需调整")
    )


def _route_mediation_decomposition(block: dict, result: dict) -> str:
    mediator = block.get("mediator", "?")
    if not block.get("mediator_valid", True):
        return (
            f"- **中介分解**：`{mediator}` 不在任何 X → … → {mediator} → … → Y "
            "的有向路径上，它不是这条效应的中介"
        )
    lines = [f"- **中介分解**：中介 `{mediator}`"]
    lines.append(_mediation_arm(
        block.get("nde_nie"), "NDE / NIE（自然直接 / 间接效应）",
        envelope_glossary.nde_nie_condition_zh))
    lines.append(_mediation_arm(
        block.get("cde"), "CDE（控制直接效应）",
        envelope_glossary.cde_condition_zh))
    return "\n".join(lines)


def _route_mediation_joint_decomposition(block: dict, result: dict) -> str:
    mediators = _vars(block.get("mediators"))
    if not block.get("mediator_set_valid", True):
        return f"- **中介集分解**：{mediators} 不构成这条效应的有效中介集"
    lines = [
        f"- **中介集分解**：中介集 {mediators} 整体当一个块处理 —— "
        "正是不需要给集合内部排序才使它可识别"
    ]
    lines.append(_mediation_arm(
        block.get("nde_nie"), "NDE / NIE（自然直接 / 间接效应）",
        envelope_glossary.nde_nie_condition_zh))
    lines.append(_mediation_arm(
        block.get("cde"), "CDE（控制直接效应）",
        envelope_glossary.cde_condition_zh))
    return "\n".join(lines)


def _route_proximal_estimand(block: dict, result: dict) -> str:
    line = (
        f"- **近端识别**：未测混杂 `{block.get('latent', '?')}` "
        f"由两个代理变量约束 —— 处理侧 `{block.get('treatment_proxy', '?')}`、"
        f"结局侧 `{block.get('outcome_proxy', '?')}`"
    )
    card = block.get("latent_cardinality")
    if card is not None:
        line += f"（未测混杂取 {card} 个值）"
    lines = [line]
    conds = block.get("data_conditions")
    if conds:
        lines.append(f"  - 数据须满足：{conds}")
    return "\n".join(lines)


def _route_selection_recovery(block: dict, result: dict) -> str:
    sel = _vars(block.get("selection_nodes"))
    lines = [f"- **选择偏倚**：样本被 {sel} 限制过"]
    if block.get("recoverable"):
        adj = block.get("adjustment_set")
        lines.append(
            "  - 无偏效应**可从这份有偏样本恢复**"
            + (f"，经选择后门调整 {_vars(adj)}" if adj else "")
        )
    else:
        why = block.get("failure_reason")
        lines.append(
            "  - 无偏效应**无法只从这份样本恢复**" + (f"：{why}" if why else "")
        )
    need = block.get("external_data_needed")
    if need:
        lines.append(f"  - 还需要外部（未经选择的）数据：{'、'.join(str(n) for n in need)}")
    return "\n".join(lines)


#: Mohan-Pearl-Tian's graphical classification, strongest first. ``none``
#: is a member: the classifier returns it when the program declares no
#: missingness indicator at all, which is not a weaker MNAR but the absence
#: of the question — and it was the one value with no word.
_MECHANISM_ZH = {
    "MCAR": "MCAR（完全随机缺失）",
    "MAR": "MAR（随机缺失，缺失只由观测到的变量决定）",
    "MNAR": "MNAR（非随机缺失，缺失与没测到的值本身有关）",
    "none": "未声明（程序里没有任何缺失指示变量，无从判断机制）",
}


def _route_missing_data_recovery(block: dict, result: dict) -> str:
    mech = block.get("mechanism") or "?"
    lines = [f"- **缺失数据**：机制 {_MECHANISM_ZH.get(mech, mech)}"]
    partial = block.get("partially_observed")
    if partial:
        lines.append(f"  - 部分观测的变量：{_vars(partial)}")
    estimand = block.get("estimand") or {}
    if estimand.get("recoverable"):
        requires = estimand.get("requires") or ()
        lines.append(
            "  - 整条估计量**可从缺失数据恢复**"
            + (f"（需要 {'、'.join(str(r) for r in requires)} 都可恢复）"
               if requires else "")
        )
    else:
        why = estimand.get("failure_reason") or block.get("failure_reason")
        lines.append(
            "  - 整条估计量**不可恢复**" + (f"：{why}" if why else "")
        )
    return "\n".join(lines)


# Each route, said once. ``bind`` refuses a set that misses one, so a
# block added to the family cannot reach this section and render nothing.
_ROUTE_RENDERERS = blocks.bind(blocks.ROUTE, {
    blocks.IDENTIFICATION: _route_identification,
    blocks.IV_IDENTIFICATION: _route_iv_identification,
    blocks.TRANSPORT_IDENTIFICATION: _route_transport_identification,
    blocks.JOINT_IDENTIFICATION: _route_joint_identification,
    blocks.LONGITUDINAL_IDENTIFICATION: _route_longitudinal_identification,
    blocks.MEDIATION_DECOMPOSITION: _route_mediation_decomposition,
    blocks.MEDIATION_JOINT_DECOMPOSITION: _route_mediation_joint_decomposition,
    blocks.PROXIMAL_ESTIMAND: _route_proximal_estimand,
    blocks.SELECTION_RECOVERY: _route_selection_recovery,
    blocks.MISSING_DATA_RECOVERY: _route_missing_data_recovery,
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


def _detail_stratified_wald(ne: dict, result: dict) -> str:
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
    # Ordered rather than as a variable set: the cell labels below are read
    # positionally against this, so brace notation would say the order does
    # not matter when it is the field's whole content.
    head = (
        f"- **分层 Wald 的逐格明细**（{len(strata)} 格，"
        f"按 {'、'.join(str(name) for name in order)} 依次切）："
        f"总体 = 加权结局差 {_fmt(sw.get('outcome_shift'))} ÷ 加权处理差 "
        f"{_fmt(sw.get('treatment_shift'))}；聚合的是两个加权和之比，"
        f"不是各格比值的平均，所以单格没有自己的 Wald 估计"
    )
    lines = []
    for s in strata:
        cell = "、".join(
            f"{name}={value}"
            for name, value in zip(order, s.get("values") or ())
        ) or "（无条件）"
        lines.append(
            f"  - {cell}：权重 {_fmt(s.get('weight'))}，n={s.get('n_obs')}"
            f"（工具高 {s.get('n_instrument_high')} / 低 "
            f"{s.get('n_instrument_low')}），结局差 "
            f"{_fmt(s.get('outcome_shift'))}，处理差 "
            f"{_fmt(s.get('treatment_shift'))}"
        )
    return "\n".join([head] + lines)


def _detail_recovered_ate(ne: dict, result: dict) -> str:
    """The recovered ATE beside the number listwise deletion would have given.

    The comparison is the method: recovering an effect from data with missing
    values is worth doing exactly insofar as it differs from dropping the
    incomplete rows, and a reader shown only the recovered point has been
    shown the answer with the argument for it removed.
    """
    ra = ne["recovered_ate"]
    naive = ra.get("naive_listwise_ate")
    head = f"- **从有缺失的数据里恢复**：恢复值 {_fmt(ra.get('point'))}"
    if naive is not None:
        head += (
            f"；直接丢掉不完整的行（列表删除法）会得到 {_fmt(naive)} —— "
            f"两者之差就是这套方法全部的作用，也是判断它值不值得用的依据"
        )
    else:
        head += "（这次没有算出列表删除法的对照值，无从判断恢复挪动了多少）"
    lines = [
        head,
        f"  - 共 {ra.get('n_total')} 行，完全没有缺失的只有 "
        f"{ra.get('n_complete_case')} 行；条件概率那一层用了 "
        f"{ra.get('n_conditional_rows')} 行、边缘分布那一层用了 "
        f"{ra.get('n_marginal_rows')} 行 —— 每个因子各用自己的完整行估计，"
        f"这正是它与列表删除法的差别所在",
    ]
    missing = list(ra.get("missing_columns") or ())
    if missing:
        lines.append(f"  - 有缺失的列：{_vars(missing)}")
    lines.append(
        f"  - 调整集 {_vars(ra.get('adjustment'))}，分 {ra.get('n_strata')} 层，"
        f"bootstrap {ra.get('n_bootstrap')} 次"
    )
    return "\n".join(lines)


def _detail_selection_recovery_numeric(ne: dict, result: dict) -> str:
    """The two arm means, and the external sample the recovery leaned on.

    Z⁻ is the part that cannot come from the selected sample, so the reference
    sample is not a footnote: the recovered number is only as good as the
    claim that this second sample speaks for the population the first one was
    filtered out of.
    """
    sr = ne["selection_recovery_numeric"]
    lines = [
        f"- **从选择偏倚里恢复**：处理臂均值 {_fmt(sr.get('mu_treated'))}，"
        f"对照臂均值 {_fmt(sr.get('mu_control'))}，上面那个数是两者之差",
    ]
    z_plus, z_minus = list(sr.get("z_plus") or ()), list(sr.get("z_minus") or ())
    lines.append(
        f"  - 选择后门调整：Z⁺={_vars(z_plus)}（在这份被筛过的样本里就能估）；"
        f"Z⁻={_vars(z_minus)}（只能从外部样本估）"
    )
    if sr.get("reference_sample_size") is not None:
        lines.append(
            f"  - 外部参照样本 N={sr['reference_sample_size']} —— "
            f"恢复出的数只在「这份样本代表未被筛过的人群」这句话成立时才成立"
        )
    selected = sr.get("selected_values") or {}
    if selected:
        said = "、".join(f"{k}={v}" for k, v in selected.items())
        lines.append(f"  - 样本被限制在：{said}")
    return "\n".join(lines)


def _detail_measurement_correction(ne: dict, result: dict) -> str:
    """How far inverting the misclassification matrix moved the number.

    ``det`` is printed because it is what makes the correction unstable: a
    matrix near singular inverts into a large move that the data does not
    support, and the corrected point alone cannot tell that apart from a
    large real correction.
    """
    mc = ne["measurement_correction"]
    naive, point = mc.get("naive_point"), ne.get("point")
    head = f"- **误分类校正**：{envelope_glossary.measurement_side_zh(mc.get('side', 'outcome'))}"
    lines = [head]
    if naive is not None and point is not None:
        lines.append(
            f"  - 未校正 {_fmt(naive)} → 校正后 {_fmt(point)}，"
            f"校正把这个数挪了 {_fmt(point - naive)}"
        )
    elif naive is not None:
        lines.append(f"  - 未校正 {_fmt(naive)}")
    if mc.get("differential"):
        by = mc.get("differential_by")
        lines.append(
            "  - 差分性误分类：错分概率随"
            + (f" {by} " if by else "另一个变量")
            + "而变，所以每一档各用自己的混淆矩阵求逆"
        )
    if mc.get("det") is not None:
        lines.append(
            f"  - 混淆矩阵行列式 det={_fmt(mc['det'])} —— 越接近 0，"
            f"求逆越不稳定，校正后的数对矩阵本身的误差越敏感"
        )
    for key, label in (("det_exposure", "暴露通道"),
                       ("det_outcome", "结局通道"),
                       ("det_joint", "联合")):
        if mc.get(key) is not None:
            lines.append(f"  - {label} det={_fmt(mc[key])}")
    if mc.get("out_of_simplex"):
        lines.append(
            "  - **求逆的结果落到了概率单纯形之外**：说明声明的混淆矩阵与这批"
            "数据对不上，校正后的数不该照单全收"
        )
    return "\n".join(lines)


def _detail_regression_calibration(ne: dict, result: dict) -> str:
    """The attenuated slope, and the reliability that says how attenuated.

    λ is the whole correction — the corrected slope is the naive one divided
    through by it — so a reader who sees only the corrected number cannot
    tell a small measurement problem from a large one.
    """
    rc = ne["regression_calibration"]
    naive, point = rc.get("naive_point"), ne.get("point")
    lines = [
        f"- **回归校准**（连续变量的经典加性测量误差）：暴露 "
        f"`{rc.get('exposure')}`"
    ]
    if naive is not None and point is not None:
        lines.append(
            f"  - 未校正斜率 {_fmt(naive)} → 校正后 {_fmt(point)}，"
            f"校正把这个数挪了 {_fmt(point - naive)}"
        )
    if rc.get("reliability") is not None:
        lines.append(
            f"  - 可靠度 λ={_fmt(rc['reliability'])} —— λ=1 表示这个变量测得完全准，"
            f"λ 越小衰减越重；校正做的就是把衰减除回去"
        )
    variances = rc.get("error_variances") or {}
    if variances:
        said = "、".join(f"{k} σ²_u={_fmt(v)}" for k, v in variances.items())
        lines.append(f"  - 声明的测量误差方差：{said}（这是外部知识，不是从数据里估的）")
    design = list(rc.get("design_vars") or ())
    if design:
        lines.append(f"  - 设计矩阵列序：{_vars(design)}")
    return "\n".join(lines)


def _longitudinal_common(block: dict) -> list[str]:
    """The lines both longitudinal routes state, in the same words.

    They contrast the same two strategies over the same times; only how they
    got there differs. Saying the shared part twice in two spellings would
    make a reader comparing the two routes reconcile the wording first.
    """
    lines = [
        f"  - 策略对比：全程 {_fmt(block.get('strategy_treated'))} 下 "
        f"E[{block.get('outcome')}]={_fmt(block.get('e_y_treated'))}，"
        f"全程 {_fmt(block.get('strategy_control'))} 下 "
        f"E[{block.get('outcome')}]={_fmt(block.get('e_y_control'))}，"
        f"上面那个数是两者之差",
    ]
    treatments = list(block.get("treatments") or ())
    if treatments:
        lines.append(f"  - 各时点的处理：{_vars(treatments)}")
    by_time = list(block.get("confounders_by_time") or ())
    for i, names in enumerate(by_time, 1):
        lines.append(f"    - 第 {i} 时点调整 {_vars(names)}")
    return lines


def _detail_longitudinal_gformula(ne: dict, result: dict) -> str:
    """The g-computation route, and the fact that a second route exists.

    The two longitudinal estimators answer one question from different
    assumptions, so whether they agree is itself a finding — and only one of
    them runs per query. A reader is told which one produced this number and
    that running the other is a check available to them, because otherwise
    the check looks like it was made and passed.
    """
    block = ne["longitudinal_gformula"]
    lines = [
        "- **纵向 g-公式（g-computation）**：按时间顺序模拟每个时点的处理与协变量，"
        "再把结局在模拟出的人群上平均"
    ]
    lines += _longitudinal_common(block)
    lines.append(
        f"  - 蒙特卡洛模拟 {block.get('n_sim')} 次，bootstrap "
        f"{block.get('n_bootstrap')} 次"
    )
    lines.append(
        "  - 另一条独立路线（IPW 边缘结构模型）这次没有跑：它靠加权而不是靠模拟，"
        "两条算出来的数一致与否本身就是一个发现，这里没有这个发现"
    )
    return "\n".join(lines)


def _detail_longitudinal_ipw_msm(ne: dict, result: dict) -> str:
    """The IPW/MSM route, its weights, and the route it was not compared to.

    The weight summary is the diagnostic that matters here: a maximum far
    above the mean means a handful of subjects carry the estimate, which no
    confidence interval built from the same weights will say.
    """
    block = ne["longitudinal_ipw_msm"]
    lines = [
        "- **纵向 IPW 边缘结构模型**：按每个时点接受该处理的概率给个体加权，"
        "在加权后的人群上拟合一个边缘模型"
    ]
    lines += _longitudinal_common(block)
    stabilized = "稳定化权重" if block.get("stabilized") else "未稳定化权重"
    if block.get("weight_mean") is not None:
        lines.append(
            f"  - {stabilized}：均值 {_fmt(block.get('weight_mean'))}，"
            f"最大 {_fmt(block.get('weight_max'))} —— 最大值远高于均值，"
            f"说明少数个体在主导这个数"
        )
    coefficients = list(block.get("msm_coefficients") or ())
    if coefficients:
        lines.append(
            f"  - 边缘结构模型系数：{', '.join(_fmt(c) for c in coefficients)}"
        )
    lines.append(
        f"  - bootstrap {block.get('n_bootstrap')} 次"
    )
    lines.append(
        "  - 另一条独立路线（g-公式）这次没有跑：它靠模拟而不是靠加权，"
        "两条算出来的数一致与否本身就是一个发现，这里没有这个发现"
    )
    return "\n".join(lines)


#: The four components, in the order the identity states them, each with the
#: sentence that says what a reader would have to believe for it to be large.
#: Printing ``CDE`` / ``INTref`` / ``INTmed`` / ``PIE`` alone hands a reader
#: four acronyms and asks them to look up which is which.
_FOUR_WAY_PARTS: tuple[tuple[str, str, str], ...] = (
    ("cde", "纯直接（CDE）",
     "既不经中介、也没借助处理与中介的交互"),
    ("intref", "仅交互（INTref）",
     "靠处理与中介的交互，但中介本身没有被处理改变"),
    ("intmed", "交互且经中介（INTmed）",
     "既靠交互，又靠处理确实改变了中介"),
    ("pie", "纯中介（PIE）",
     "完全经由中介，不涉及交互"),
)


def _detail_four_way_decomposition(ne: dict, result: dict) -> str:
    """VanderWeele's split of the total effect, on the difference scale.

    Four numbers that sum to the total, and the reason for reporting them is
    that they point at different interventions: what is mediated can be
    attacked at the mediator, what is interaction cannot.
    """
    fw = ne["four_way_decomposition"]
    lines = [
        f"- **四分解（VanderWeele，差分尺度）**：总效应 {_band(fw.get('te'))} "
        f"拆成四块，四块相加等于总效应"
    ]
    for key, label, gloss in _FOUR_WAY_PARTS:
        said = _band(fw.get(key))
        if said:
            lines.append(f"  - {label}：{said} —— {gloss}")
    for key, label in (("prop_mediated", "经中介的比例"),
                       ("prop_interaction", "涉及交互的比例")):
        said = _band(fw.get(key))
        if said:
            lines.append(f"  - {label}：{said}")
    if fw.get("additive_interaction") is not None:
        lines.append(
            f"  - 相加交互 {_fmt(fw['additive_interaction'])} —— "
            f"处理与中介同时在场时，比两者各自贡献相加多出来的部分"
        )
    lines.append(
        "  - 为什么值得拆：能靠改中介去掉的只有经中介那两块，"
        "交互那部分改中介去不掉"
    )
    return "\n".join(lines)


def _detail_four_way_ratio(ne: dict, result: dict) -> str:
    """The same split on the excess-relative-risk scale.

    A binary outcome makes the multiplicative scale the natural one, and the
    difference-scale block beside it is a different decomposition rather than
    the same numbers rescaled.
    """
    fr = ne["four_way_ratio"]
    lines = [
        f"- **四分解（VanderWeele，比值尺度／超额相对风险）**："
        f"总相对风险 {_band(fr.get('total_rr'))}，超额部分 "
        f"{_band(fr.get('total_err'))} 拆成四块"
    ]
    for key, label, gloss in _FOUR_WAY_PARTS:
        said = _band(fr.get(f"err_{key}"))
        if said:
            lines.append(f"  - {label}：{said} —— {gloss}")
    for key, label in (("prop_mediated", "经中介的比例"),
                       ("prop_interaction", "涉及交互的比例"),
                       ("prop_eliminated", "把中介固定住能消掉的比例")):
        said = _band(fr.get(key))
        if said:
            lines.append(f"  - {label}：{said}")
    lines.append(
        f"  - {envelope_glossary.four_way_mediator_scale_zh(fr.get('mediator_scale'))}"
    )
    return "\n".join(lines)


def _detail_four_way_unavailable(ne: dict, result: dict) -> str:
    """Why the difference-scale split was attempted and withheld.

    A reader who is shown no decomposition cannot tell "not applicable here"
    from "nobody tried", and those call for different next steps.
    """
    reason = ne["four_way_unavailable"].get("reason")
    return (
        "- **四分解没有给出**：" + (str(reason) if reason else "未说明原因")
        + " —— 是算过之后判定在这种数据形状下不成立，不是没算"
    )


#: One renderer per composite part of ``numeric_estimate`` that says how the
#: NUMBER was computed, in the order a reader meets them: what the estimator
#: aggregated, what it recovered, what it corrected, what it contrasted over
#: time, what it decomposed.
_NUMERIC_DETAIL_RENDERERS: tuple[
    tuple[str, Callable[[dict, dict], str]], ...] = (
    ("stratified_wald", _detail_stratified_wald),
    ("recovered_ate", _detail_recovered_ate),
    ("selection_recovery_numeric", _detail_selection_recovery_numeric),
    ("measurement_correction", _detail_measurement_correction),
    ("regression_calibration", _detail_regression_calibration),
    ("longitudinal_gformula", _detail_longitudinal_gformula),
    ("longitudinal_ipw_msm", _detail_longitudinal_ipw_msm),
    ("four_way_decomposition", _detail_four_way_decomposition),
    ("four_way_ratio", _detail_four_way_ratio),
    ("four_way_unavailable", _detail_four_way_unavailable),
)


def _render_numeric_detail(result: dict) -> list[str]:
    """What the estimator did with the data, for whichever parts are present.

    Every one of these is exclusive to a single estimator, so at most two
    fire on any envelope (the two four-way scales are the pair that can
    co-occur). A part with nothing in it prints nothing rather than a heading
    over an empty line.
    """
    ne = result.get("numeric_estimate") or {}
    return [
        render(ne, result)
        for name, render in _NUMERIC_DETAIL_RENDERERS
        if ne.get(name)
    ]


def _render_derivation_chain(result: dict) -> str:
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
        line = f"  {i}. {derivation_glossary.describe(step.get('rule'))}"
        licence = (step.get("inputs") or {}).get(
            "interventional_risk_provenance")
        if licence:
            line += f"——{risk_provenance.describe(licence)}"
        said.append(line)
    return "\n".join(["- **推导链**（每一步都可被独立重导）："] + said)


def _render_route(result: dict) -> str:
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
    lines = [
        _ROUTE_RENDERERS[block](extensions[block], result)
        for block in blocks.rendered_in(blocks.ROUTE)
        if extensions.get(block)
    ]
    # The estimand itself, after the route that found it: the blocks name
    # the pattern, this is the expression the pattern produced. It is a
    # field rather than a block, so the binding above — which is what
    # catches a block nobody renders — never looked at it, and for ten
    # rounds the report said "机器可读，见 result.formula" instead.
    formula = result.get("formula")
    if formula is not None:
        lines.append(f"- **估计式**：`{formula_text.render(formula)}`")
    # The numeric half of this section's question, after the expression and
    # before the skeleton: the blocks above say which pattern identified the
    # estimand, these say what the estimator then did with the data. They are
    # here rather than under the answer because "怎么算出来的" is the question
    # they answer, and because reading them beside the identification route is
    # what lets a reader see the two halves as one argument.
    lines += _render_numeric_detail(result)
    # Last, because it is the skeleton and the lines above are the detail:
    # which pattern, on which set, which expression. A reader who wants
    # only the shape of the argument reads this; a reader checking it
    # reads what came before.
    lines.append(_render_derivation_chain(result))
    return "\n".join(line for line in lines if line)


# --- causal model -------------------------------------------------------------


def _edge_provenance(annotations: dict | None) -> str:
    if not annotations:
        return ""
    source = annotations.get("source")
    conf = annotations.get("confidence")
    conf_txt = f"，稳定度 {conf:.0%}" if isinstance(conf, (int, float)) else ""
    if source is None:
        return ""
    if source == "llm_proposal":
        return f" ⟨LLM 假设，待复核{conf_txt}⟩"
    if source.startswith("discovery:"):
        algo = source.split(":", 1)[1].upper()
        return f" ⟨发现算法 {algo}{conf_txt}⟩"
    return f" ⟨来源：{source}{conf_txt}⟩"


def _render_model(program: dict) -> str:
    directed: list[str] = []
    bidirected: list[str] = []
    for stmt in program.get("statements", []):
        kind = stmt.get("kind")
        if kind == "cause":
            frm = _atom_pred(stmt.get("from"))
            to = _atom_pred(stmt.get("to"))
            directed.append(f"- `{frm} → {to}`{_edge_provenance(stmt.get('annotations'))}")
        elif kind == "bidirected":
            a = _atom_pred(stmt.get("left"))
            b = _atom_pred(stmt.get("right"))
            bidirected.append(
                f"- `{a} ↔ {b}`（潜在共因）{_edge_provenance(stmt.get('annotations'))}"
            )

    lines: list[str] = []
    if directed:
        lines.append("**因果边**：")
        lines += directed
    if bidirected:
        lines.append("")
        lines.append("**双向边（未观测共因）**：")
        lines += bidirected

    ambiguities = ((program.get("extensions") or {}).get("ambiguities")) or []
    if ambiguities:
        lines.append("")
        lines.append("**方向待定**（从数据无法判定，需领域知识）：")
        for amb in ambiguities:
            endpoints = amb.get("endpoints") or []
            if len(endpoints) == 2:
                conf = amb.get("skeleton_confidence")
                ctxt = f"（稳定度 {conf:.0%}）" if isinstance(conf, (int, float)) else ""
                lines.append(f"- `{endpoints[0]} — {endpoints[1]}`{ctxt}")

    if not lines:
        return "（未提供因果边）"

    if any("⟨" in ln for ln in directed + bidirected):
        lines.append("")
        lines.append(
            "> 图例：⟨LLM 假设⟩ = 上游模型提出、未经证据支持；"
            "⟨发现算法⟩ = 从数据学出的提案；无标注 = 用户断言。"
            "标注为提案的边需复核。"
        )
    return "\n".join(lines)


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


def _render_verification(result: dict, audited: list[dict] | None) -> str:
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
    lines: list[str] = []

    if audited is not None:
        failed = [row for row in audited if not row.get("ok")]
        lines.append(
            f"✗ **{len(failed)} 项复核未通过** —— 内核照这张图各自重算，"
            "得到的和上面这份对不上。"
            if failed else
            f"✓ **{len(audited)} 项独立复核全部通过** —— 内核不看上面的结论，"
            "照记录下来的输入各自重算了一遍。"
        )

    if any(row.re_derives_answer for row in rows):
        lines.append(
            "上面那个答案**本身可以被独立重算**：换一份独立誊写的实现，从记录下来的"
            "输入重算一遍，对不上即报错 —— 这是 Themis 与「相信算法输出」类工具的"
            "根本区别。"
        )
    else:
        lines.append(
            "**没有能重算这个答案本身的复核**（还没得出数值 / 结构结论）；"
            "下面这些复核的是它旁边的事实。"
        )

    lines.append("")
    for row in rows:
        got = outcome.get(row.name)
        mark = "" if got is None else ("✓ " if got.get("ok") else "✗ ")
        lines.append(f"- {mark}{row.zh}（`{_call_form(row)}`）")
        if got is not None and not got.get("ok") and got.get("refusal"):
            lines.append(f"  - 未通过：{got['refusal']}")

    if audited is None:
        lines.append("")
        lines.append("一次跑完全部：`themis.audit(program, result)`。")
    return "\n".join(lines)


# --- assumptions --------------------------------------------------------------


def _assumption_ledger(ledger: dict, result: dict) -> str:
    """Every load-bearing assumption, worst first.

    The two other blocks of this family are not rendered beside it and
    not missing either: ``result_orchestrator`` reads them and folds what
    they hold into this ledger before the report ever sees the envelope,
    which their ``carried_by`` says.
    """
    if not ledger.get("assumptions"):
        return ""

    lines: list[str] = []
    summary = ledger.get("summary")
    if summary:
        lines.append(summary)
        lines.append("")
    # Three closed vocabularies on one line — which part of the answer this
    # holds up, how badly it dies, and who put it there. All three used to
    # reach the reader as the identifier the kernel writes, so a line ended
    # `（assumption／来源 inherent／不可检验）`: an assumption said to be an
    # assumption, from a source called inherent.
    for a in ledger["assumptions"]:
        sev = ledger_vocab.severity_zh(a.get("severity", ""))
        claim = a.get("claim", "")
        meta = []
        if a.get("layer"):
            meta.append(ledger_vocab.layer_zh(a["layer"]))
        if a.get("provenance"):
            meta.append(f"来源 {ledger_vocab.provenance_zh(a['provenance'])}")
        meta.append("可检验" if a.get("testable") else "不可检验")
        lines.append(f"- **[{sev}]** {claim}　（{'／'.join(meta)}）")
    return "\n".join(lines)


_ASSUMPTION_RENDERERS = blocks.bind(blocks.ASSUMPTION, {
    blocks.ASSUMPTION_LEDGER: _assumption_ledger,
})


def _render_assumptions(result: dict) -> str:
    extensions = result.get("extensions") or {}
    lines = [
        _ASSUMPTION_RENDERERS[block](extensions[block], result)
        for block in blocks.rendered_in(blocks.ASSUMPTION)
        if extensions.get(block)
    ]
    return "\n".join(line for line in lines if line)


# --- data gaps ----------------------------------------------------------------


def _render_gaps(result: dict) -> str:
    dg = result.get("data_gap_report")
    if not dg:
        return ""

    lines: list[str] = []
    tier = dg.get("answer_tier")
    if tier:
        lines.append(f"当前最强答案层级：**{_TIER_ZH.get(tier, tier)}**。")
    summary = dg.get("summary")
    if summary:
        lines.append(summary)

    gaps = dg.get("gaps") or []
    shown = [g for g in gaps if g.get("severity") in ("blocking", "important")]
    if not shown:
        shown = gaps[:3]  # nothing load-bearing — show a few for context
    if shown:
        lines.append("")
        for g in shown:
            sev = _GAP_SEVERITY_ZH.get(g.get("severity"), g.get("severity", ""))
            desc = g.get("description", "")
            lines.append(f"- **[{sev}]** {desc}")
            if g.get("if_provided"):
                lines.append(f"  - 补上可：{g['if_provided']}")
            alts = g.get("alternative_paths") or []
            if alts:
                lines.append(f"  - 或：{'；'.join(alts)}")

    steps = dg.get("actionable_next_steps") or []
    if steps:
        lines.append("")
        lines.append("**下一步**：")
        for s in steps:
            lines.append(f"- {s}")
    return "\n".join(lines)


# --- footer -------------------------------------------------------------------


def _render_footer(result: dict) -> str:
    bits: list[str] = []
    qid = result.get("query_id")
    if qid:
        bits.append(f"query_id=`{qid}`")
    n_steps = _derivation_step_count(result.get("derivation"))
    if n_steps is not None:
        bits.append(f"推导链 {n_steps} 步")
    if result.get("formula") is not None:
        bits.append("估计式已生成")
    ne = result.get("numeric_estimate") or {}
    ctx = result.get("estimation_context") or {}
    data_hash = ne.get("data_hash") or ctx.get("data_hash")
    if data_hash:
        bits.append(f"data_hash=`{data_hash[:12]}…`")
    if not bits:
        return ""
    return "*审计*：" + "　·　".join(bits)
