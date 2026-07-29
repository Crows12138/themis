"""Deterministic whole-analysis report assembler.

Turns one already-computed Themis result into a single human-readable
Markdown document — the deterministic counterpart to the LLM-facing
``response_rendering.md`` bridge. It is a *passive assembler* (per
``themis/output``): it reads only fields the runtime already put on the
result / program and NEVER re-runs reasoning or calls ``verify``.

What it foregrounds — and what makes it *Themis's* report rather than a
generic causal-analysis summary — follows the order
``response_rendering.md`` mandates: the **answer first**, then the two
things Causal-Copilot-style tools omit — an honest **verification**
status (is the answer's derivation independently auditable?) and the
**assumptions + data gaps** (what must hold, and what data would
strengthen or unblock the answer).

    from themis.output.analysis_report import build_analysis_report
    md = build_analysis_report(result, program=program)

``result`` is one entry from ``themis.run(...)["results"]`` /
``themis.estimate(...)["results"]``. ``program`` (the kernel_ast dict) is
optional but lets the report render the causal model and edge provenance.
``verified`` is an optional caller-supplied verdict from a *separate*
``themis.verify`` call — the assembler never runs verification itself.
"""
from __future__ import annotations

from .. import blocks

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


def _find_query(program: dict | None) -> dict | None:
    if not program:
        return None
    for stmt in program.get("statements", []):
        if stmt.get("kind") == "query":
            return stmt.get("query")
    return None


def _atom_pred(atom_dict: dict) -> str:
    return (atom_dict or {}).get("predicate", "?")


def _valued(a: dict) -> str:
    atom = a.get("atom", a)
    val = a.get("value")
    pred = _atom_pred(atom)
    return f"{pred}={val}" if val is not None else pred


def _render_question(result: dict, program: dict | None) -> str:
    q = _find_query(program)
    kind = (q or {}).get("kind") or result.get("query_kind") or "?"
    if q is None:
        return f"（查询类型：`{kind}`）"

    if kind == "effect":
        iv = _valued(q.get("intervention", {}))
        tgt = _valued(q.get("target", {}))
        line = f"估计 **干预 {iv}** 对 **{tgt}** 的因果效应。"
        given = q.get("given") or []
        if given:
            conds = "、".join(_valued(g) for g in given)
            line += f"（条件于 {conds}）"
        return line
    if kind == "cause":
        return f"**{_atom_pred(q.get('from'))}** 是否因果影响 **{_atom_pred(q.get('to'))}**？"
    if kind == "association":
        return f"**{_atom_pred(q.get('from'))}** 与 **{_atom_pred(q.get('to'))}** 是否（在图中）相关联？"
    if kind == "identify":
        tgt = q.get("target") or q.get("effect") or {}
        return f"目标效应是否可从观测数据**非参数识别**？（`identify`）"
    return f"（查询类型：`{kind}`）"


# --- answer -------------------------------------------------------------------


def _render_answer(result: dict) -> str:
    status = result.get("status")
    ne = result.get("numeric_estimate")
    nr = result.get("numeric_result")
    sr = result.get("structural_result")
    br = result.get("bounds_result")

    # 1. Data-path numeric estimate (strongest).
    if ne and ne.get("point") is not None:
        return _render_numeric_estimate(ne, result.get("outcome_error"))

    # 1b. Causation bounds answer (PN/PS/PNS recovered from data, non-monotone):
    #     no single point, but three identified intervals — render them.
    if ne and ne.get("probabilities_of_causation"):
        return _render_causation_bounds(ne["probabilities_of_causation"])

    # 2. Symbolic / theta-path numeric value.
    if nr and nr.get("value") is not None:
        line = f"**{_fmt(nr['value'])}**"
        iv = nr.get("interval")
        if iv and len(iv) == 2:
            line += f"（区间 [{_fmt(iv[0])}, {_fmt(iv[1])}]）"
        if nr.get("unit"):
            line += f" {nr['unit']}"
        return line

    # 3. Structural boolean (cause / association / identify).
    if sr and sr.get("value") is not None:
        val = sr["value"]
        verdict = "**是**" if val is True else ("**否**" if val is False else f"**{val}**")
        paths = sr.get("supporting_paths") or []
        note = f"（支持路径 {len(paths)} 条）" if paths else ""
        return f"结论：{verdict}{note}"

    # 4. Bounds (partial identification).
    if br and br.get("lower_value") is not None:
        method = br.get("method", "bounds")
        return (
            f"给出**区间** [{_fmt(br['lower_value'])}, {_fmt(br['upper_value'])}]"
            f"（method=`{method}`）—— 这是部分识别的界，不是点估计。"
        )

    # 5. Identified but needs data, or genuinely blocked.
    if result.get("formula") is not None:
        return (
            "效应**可识别**（估计式已生成，见文末审计），但当前**没有数据** → "
            "需要数据才能给出具体数值。所需数据见下方「数据缺口」。"
        )
    if status in ("needs_investigation", "needs_assumption"):
        return "当前**还不能给出答案** —— 缺口与补法见下方「数据缺口」。"
    if status == "outside_language":
        return "该问题**超出 Themis 可表达 / 可识别的范围**。"
    return "（无可呈现的答案字段）"


def _render_causation_bounds(poc: dict) -> str:
    """PN/PS/PNS recovered from data without monotonicity — three identified
    intervals (Tian-Pearl bounds). No point; a point would need monotonicity."""
    labels = (("pn", "必要性 PN（归因）"), ("ps", "充分性 PS"), ("pns", "必要且充分 PNS"))
    lines = ["数据可识别的**区间**（无单调性假设，故为界而非点）："]
    for key, label in labels:
        q = poc.get(key) or {}
        lo, hi = q.get("lower"), q.get("upper")
        if lo is None or hi is None:
            continue
        line = f"- {label} ∈ [{_fmt(lo)}, {_fmt(hi)}]"
        if q.get("ci_lower") is not None and q.get("ci_upper") is not None:
            line += f"（外带 [{_fmt(q['ci_lower'])}, {_fmt(q['ci_upper'])}]）"
        lines.append(line)
    adj = poc.get("adjustment")
    if adj:
        lines.append(f"- 干预风险经后门调整集 {{{', '.join(adj)}}} 识别")
    lines.append("- 若可假设单调性（X 从不阻止 Y），三者可点识别。")
    return "\n".join(lines)


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

    return "\n".join(lines)


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


def _render_assumptions(result: dict) -> str:
    ledger = (result.get("extensions") or {}).get(blocks.ASSUMPTION_LEDGER)
    if not ledger or not ledger.get("assumptions"):
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
        bits.append("估计式已生成（机器可读，见 `result.formula`）")
    ne = result.get("numeric_estimate") or {}
    ctx = result.get("estimation_context") or {}
    data_hash = ne.get("data_hash") or ctx.get("data_hash")
    if data_hash:
        bits.append(f"data_hash=`{data_hash[:12]}…`")
    if not bits:
        return ""
    return "*审计*：" + "　·　".join(bits)
