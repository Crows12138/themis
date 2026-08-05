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
honest **verification** status (is the answer's derivation independently
auditable?) and the **assumptions + data gaps** (what must hold, and what
data would strengthen or unblock the answer).

    from themis.output.analysis_report import build_analysis_report
    md = build_analysis_report(result, program=program)

``result`` is one entry from ``themis.run(...)["results"]`` /
``themis.estimate(...)["results"]``. ``program`` (the kernel_ast dict) is
optional but lets the report render the causal model and edge provenance.
``verified`` is an optional caller-supplied verdict from a *separate*
``themis.verify`` call — the assembler never runs verification itself.
"""
from __future__ import annotations

from typing import assert_never

from .. import answers, blocks, questions, refusals
from ..refusals import Kind
from . import formula_text


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

_STATUS_BADGE = {
    "structurally_solved": "✅ 已解决（结构层）",
    "numerically_solved": "📊 已估计（数值层）",
    "needs_investigation": "⚠️ 需补充数据 / 假设",
    "needs_assumption": "⚠️ 需补充假设",
    "outside_language": "✋ 超出可表达范围",
}

_SEVERITY_ZH = {
    "invalidating": "作废级",
    "distorting": "扭曲级",
    "confidence_only": "仅影响置信",
    "blocking": "阻断",
    "important": "重要",
    "informational": "提示",
}

_TIER_ZH = {"point": "点估计", "interval": "区间", "none": "暂无数值答案"}


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
    verified: bool | None = None,
) -> str:
    """Assemble a Markdown analysis report from one result envelope.

    Pure presentation over already-computed fields — no reasoning is
    re-run and ``verify`` is never called. ``verified`` may carry the
    result of a separate ``themis.verify`` call so the report can stamp
    a ✓ / ✗; left ``None`` it reports auditability from the derivation.
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
    parts += _section("验证", _render_verification(result, verified))
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
    br = result.get("bounds_result")

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
    if br and br.get("lower_value") is not None:
        method = br.get("method", "bounds")
        return (
            f"给出**区间** [{_fmt(br['lower_value'])}, {_fmt(br['upper_value'])}]"
            f"（method=`{method}`）—— 这是部分识别的界，不是点估计。"
        )

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


_RISK_PROVENANCE_ZH = {
    "exogenous": "X 无父节点，干预风险即观测风险",
    "backdoor_adjustment": "干预风险经后门调整识别",
    "derived_identification": "干预风险由识别层从图上导出",
    "user_experimental": "干预风险来自调用方提供的实验数据",
}
"""Where the two do-risks came from — which is how much PN can be trusted.

Unlisted renders as its own token, the convention this file already uses
for identification patterns: a name a reader has to look up still beats a
sentence that leaves out where the number came from.
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
        if point is not None and bounded:
            # Tian-Pearl bounds use no monotonicity, so this is exactly what
            # the assumption bought — the reader cannot weigh the point
            # without seeing the interval it replaced.
            aside.append(f"无单调性假设时只能给到 [{_fmt(lo)}, {_fmt(hi)}]")
        lines.append(
            f"- {label}：{head}" + (f"（{'；'.join(aside)}）" if aside else "")
        )
    if not lines:
        return ""

    monotonic = bool(poc.get("monotonic"))
    head = (
        "单调性成立（X 从不阻止 Y），三者点识别："
        if monotonic
        else "未假设单调性，三者只能给界："
    )
    risk_hi, risk_lo = poc.get("p_y_do_x1"), poc.get("p_y_do_x0")
    if risk_hi is not None and risk_lo is not None:
        prov = poc.get("interventional_risk_provenance")
        note = _RISK_PROVENANCE_ZH.get(prov, f"`{prov}`") if prov else ""
        adj = poc.get("adjustment")
        if adj:
            note += f"，调整集 {{{', '.join(adj)}}}"
        lines.append(
            f"- 由干预风险 P(Y|do X)={_fmt(risk_hi)}、"
            f"P(Y|do ¬X)={_fmt(risk_lo)} 算出"
            + (f"（{note}）" if note else "")
        )
    if not monotonic:
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


def _estimate_meta(ne: dict, outcome_error: dict | None = None) -> list[str]:
    """The lines every answer shape shares, whatever its headline looks like.

    How it was computed, how precise it is, and what would overturn it. Kept
    in one place so a shape bound later cannot ship without them — the point
    shape had all of this and the four shapes that rendered nothing at all
    had, by construction, none of it.
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
    """Bounds on one counterfactual cell — a point would need monotonicity."""
    cell = ne.get("counterfactual_cell") or {}
    lo, hi = cell.get("lower"), cell.get("upper")
    lines = []
    if lo is not None and hi is not None:
        lines.append(
            f"该反事实格的**区间** [{_fmt(lo)}, {_fmt(hi)}]"
            "（无单调性假设，故为界而非点）"
        )
    else:
        lines.append("该反事实格没有给出可呈现的界。")
    adj = cell.get("adjustment")
    if adj:
        lines.append(f"- 干预风险经后门调整集 {{{', '.join(adj)}}} 识别")
    lines.append("- 若可假设单调性（X 从不阻止 Y），该格可点识别。")
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


def _mediation_arm(info: dict | None, label: str) -> str:
    """One arm of a decomposition — identifiable, and on what."""
    info = info or {}
    if not info.get("identifiable"):
        why = info.get("failed_condition")
        return f"  - {label}**不可识别**" + (f"：{why}" if why else "")
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
    lines.append(_mediation_arm(block.get("nde_nie"), "NDE / NIE（自然直接 / 间接效应）"))
    lines.append(_mediation_arm(block.get("cde"), "CDE（控制直接效应）"))
    return "\n".join(lines)


def _route_mediation_joint_decomposition(block: dict, result: dict) -> str:
    mediators = _vars(block.get("mediators"))
    if not block.get("mediator_set_valid", True):
        return f"- **中介集分解**：{mediators} 不构成这条效应的有效中介集"
    lines = [
        f"- **中介集分解**：中介集 {mediators} 整体当一个块处理 —— "
        "正是不需要给集合内部排序才使它可识别"
    ]
    lines.append(_mediation_arm(block.get("nde_nie"), "NDE / NIE（自然直接 / 间接效应）"))
    lines.append(_mediation_arm(block.get("cde"), "CDE（控制直接效应）"))
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


_MECHANISM_ZH = {
    "MCAR": "MCAR（完全随机缺失）",
    "MAR": "MAR（随机缺失，缺失只由观测到的变量决定）",
    "MNAR": "MNAR（非随机缺失，缺失与没测到的值本身有关）",
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


def _render_verification(result: dict, verified: bool | None) -> str:
    derivation = result.get("derivation")
    n_steps = _derivation_step_count(derivation)
    lines: list[str] = []

    if verified is True:
        lines.append("✓ **已独立复核通过**（`themis.verify` 未报错）。")
    elif verified is False:
        lines.append("✗ **独立复核未通过**（`themis.verify` 报错）—— 该答案不可信。")

    if derivation is not None:
        step_txt = f"（{n_steps} 步）" if n_steps is not None else ""
        lines.append(
            f"此答案携带一条**可独立复核的推导链**{step_txt}：每个数都从记录的"
            "充分统计量重新推导。运行 `themis.verify(program, result)` 会独立"
            "重导并逐项核对，对不上即抛错 —— 这是 Themis 与「相信算法输出」"
            "类工具的根本区别。"
        )
    else:
        lines.append(
            "此状态**不携带推导链**（尚未得出可复核的数值 / 结构结论）。"
            "改用 `themis.verify_data_gap_report(result)` 复核缺口报告本身"
            "（缺口审计不需要推导链）。"
        )
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
    for a in ledger["assumptions"]:
        sev = _SEVERITY_ZH.get(a.get("severity"), a.get("severity", ""))
        claim = a.get("claim", "")
        meta = []
        if a.get("layer"):
            meta.append(a["layer"])
        if a.get("provenance"):
            meta.append(f"来源 {a['provenance']}")
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
            sev = _SEVERITY_ZH.get(g.get("severity"), g.get("severity", ""))
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
