"""Serialize a typed QueryResult into the JSON shape described in
query_result.schema.json.

Responsibilities:
- enum -> string
- dataclass -> dict
- omit None-valued optional fields and empty collections
- emit structured formula AST (never stringify it)

v0.1 only implements the serialize direction (``to_dict``). The
deserialize direction (``from_dict``) is reserved for a later slice
and currently raises ``NotImplementedError``. ``syntactic_validator.
validate_result`` can still be used to confirm that a serialized
payload conforms to ``query_result.schema.json``, but reloading it
back into a typed ``QueryResult`` is not part of the v0.1.0 surface.
"""
from __future__ import annotations

from .. import blocks
from ..types import (
    Atom,
    CauseStatement,
    ConstantExpr,
    ConstTerm,
    DataGap,
    DataGapReport,
    FormulaExpr,
    FractionExpr,
    NumericResult,
    ProbabilityRefExpr,
    ProbabilityStatement,
    ProductExpr,
    Program,
    QueryResult,
    StructuralResult,
    SumExpr,
    Term,
    ValuedAtom,
    ValueExpr,
    VarRef,
    VarTerm,
)


def _structural_to_dict(sr: StructuralResult) -> dict:
    d: dict = {"value": sr.value}
    if sr.supporting_paths:
        d["supporting_paths"] = [list(p) for p in sr.supporting_paths]
    return d


def _numeric_to_dict(nr: NumericResult) -> dict:
    d: dict = {"value": nr.value}
    if nr.interval is not None:
        d["interval"] = {"low": nr.interval.low, "high": nr.interval.high}
    if nr.unit is not None:
        d["unit"] = nr.unit
    return d


def _term_to_dict(term: Term) -> dict:
    if isinstance(term, ConstTerm):
        return {"type": "const", "name": term.name}
    if isinstance(term, VarTerm):
        return {"type": "var", "name": term.name}
    raise TypeError(f"unknown term type: {type(term).__name__}")


def _atom_to_dict(atom: Atom) -> dict:
    d = {
        "predicate": atom.predicate,
        "args": [_term_to_dict(t) for t in atom.args],
    }
    if atom.time_index is not None:
        d["time_index"] = {"kind": "relative", "value": atom.time_index.value}
    return d


def _value_to_json(v: ValueExpr):
    if isinstance(v, VarRef):
        return {"kind": "var_ref", "name": v.name}
    return v  # bool / int / float / str literal


def _valued_atom_to_dict(va: ValuedAtom) -> dict:
    d: dict = {"atom": _atom_to_dict(va.atom)}
    if va.value is not None:
        d["value"] = _value_to_json(va.value)
    return d


def _formula_to_dict(expr: FormulaExpr) -> dict:
    if isinstance(expr, ConstantExpr):
        return {"kind": "constant", "value": expr.value}
    if isinstance(expr, ProbabilityRefExpr):
        return {
            "kind": "probability_ref",
            "target": _valued_atom_to_dict(expr.target),
            "given": [_valued_atom_to_dict(g) for g in expr.given],
        }
    if isinstance(expr, ProductExpr):
        return {
            "kind": "product",
            "terms": [_formula_to_dict(t) for t in expr.terms],
        }
    if isinstance(expr, SumExpr):
        return {
            "kind": "sum",
            "bind": {"name": expr.bind.name},
            "over": _atom_to_dict(expr.over),
            "body": _formula_to_dict(expr.body),
        }
    if isinstance(expr, FractionExpr):
        return {
            "kind": "fraction",
            "numerator": _formula_to_dict(expr.numerator),
            "denominator": _formula_to_dict(expr.denominator),
        }
    raise TypeError(f"unknown formula node: {type(expr).__name__}")


def to_dict(result: QueryResult) -> dict:
    """Render a QueryResult dataclass as a schema-conformant dict."""
    d: dict = {
        "status": result.status.value,
        "query_kind": result.query_kind.value,
    }
    if result.query_id is not None:
        d["query_id"] = result.query_id
    if result.structural_result is not None:
        d["structural_result"] = _structural_to_dict(result.structural_result)
    if result.numeric_result is not None:
        d["numeric_result"] = _numeric_to_dict(result.numeric_result)
    if result.confidence is not None:
        d["confidence"] = result.confidence
    if result.confidence_sources:
        d["confidence_sources"] = [
            {
                "slot_label": s.slot_label,
                **({"source": s.source} if s.source is not None else {}),
                "confidence": s.confidence,
                "is_weakest": s.is_weakest,
            }
            for s in result.confidence_sources
        ]
    if result.formula is not None:
        d["formula"] = _formula_to_dict(result.formula)
    if result.missing_information:
        d["missing_information"] = [
            {
                "kind": m.kind.value,
                "name": m.name,
                "priority": m.priority.value,
                "gap": m.gap.value,
                **({"reason": m.reason} if m.reason is not None else {}),
                **(
                    {"observable": {
                        "variables": list(m.observable.variables),
                        **(
                            {"population": m.observable.population}
                            if m.observable.population is not None
                            else {}
                        ),
                    }}
                    if m.observable is not None
                    else {}
                ),
                **(
                    {"superseded_by_estimation": True}
                    if m.superseded_by_estimation
                    else {}
                ),
            }
            for m in result.missing_information
        ]
    if result.investigation_requests:
        out_requests = []
        for r in result.investigation_requests:
            row: dict = {
                "action": r.action.value,
                "target": r.target,
                "priority": r.priority.value,
            }
            if r.note is not None:
                row["note"] = r.note
            if r.group is not None:
                row["group"] = r.group
            if r.items:
                row["items"] = [
                    {
                        "target": it.target,
                        **({"reason": it.reason} if it.reason is not None else {}),
                        **({"skeleton": it.skeleton} if it.skeleton is not None else {}),
                        "gap": it.gap.value,
                        **(
                            {"superseded_by_estimation": True}
                            if it.superseded_by_estimation
                            else {}
                        ),
                    }
                    for it in r.items
                ]
            out_requests.append(row)
        d["investigation_requests"] = out_requests
    if result.framing_notes:
        d["framing_notes"] = [
            {"predicate": n.predicate, "missing": list(n.missing)}
            for n in result.framing_notes
        ]
    if result.explanation is not None:
        d["explanation"] = result.explanation
    if result.derivation:
        # Lazy import to keep this module's top-level deps narrow; the
        # verifier already owns the canonical derivation encoder.
        from ..verifier.serialization import derivation_to_dict
        d["derivation"] = derivation_to_dict(result.derivation)
    if result.extensions is not None:
        d["extensions"] = result.extensions
    if result.data_gap_report is not None:
        d["data_gap_report"] = _data_gap_report_to_dict(result.data_gap_report)
    if result.bounds_result is not None:
        d["bounds_result"] = _bounds_result_to_dict(result.bounds_result)
    if result.estimator_failure is not None:
        d["estimator_failure"] = result.estimator_failure
    return d


def _bounds_result_to_dict(b) -> dict:
    out: dict = {
        "method": b.method.value,
        "lower_expression": b.lower_expression,
        "upper_expression": b.upper_expression,
    }
    if b.assumptions:
        out["assumptions"] = list(b.assumptions)
    if b.data_required:
        out["data_required"] = list(b.data_required)
    if b.width_when_uninformative:
        out["width_when_uninformative"] = True
    if b.notes is not None:
        out["notes"] = b.notes
    return out


def _data_gap_report_to_dict(report: DataGapReport) -> dict:
    out: dict = {
        "summary": report.summary,
        "gaps": [_data_gap_to_dict(g) for g in report.gaps],
    }
    if report.actionable_next_steps:
        out["actionable_next_steps"] = list(report.actionable_next_steps)
    if report.answer_tier is not None:
        out["answer_tier"] = report.answer_tier.value
    return out


def _data_gap_to_dict(gap: DataGap) -> dict:
    out: dict = {
        "kind": gap.kind.value,
        "severity": gap.severity.value,
        "description": gap.description,
        "blocks": gap.blocks.value,
        "provenance": [
            {"ref_kind": ref.ref_kind.value, "ref_id": ref.ref_id}
            for ref in gap.provenance
        ],
    }
    if gap.signature is not None:
        out["signature"] = gap.signature
    if gap.required_data is not None:
        rd = gap.required_data
        rd_out: dict = {}
        if rd.data_type is not None:
            rd_out["data_type"] = rd.data_type.value
        if rd.population is not None:
            rd_out["population"] = rd.population
        if rd.variables:
            rd_out["variables"] = list(rd.variables)
        if rd.min_sample_size is not None:
            rd_out["min_sample_size"] = rd.min_sample_size
        if rd.precision_target is not None:
            rd_out["precision_target"] = rd.precision_target
        if rd.sampling_point_count is not None:
            rd_out["sampling_point_count"] = rd.sampling_point_count
        # confounders_required: emit always when sampling_point_count is
        # set (i.e. dose-response gap context) so renderer can distinguish
        # 'tried but kernel couldn't extract' (empty array) from 'not
        # applicable' (key absent). Subagent real-test caught this: when
        # absent, the LLM filled in confounders by guessing.
        if rd.sampling_point_count is not None:
            rd_out["confounders_required"] = list(rd.confounders_required)
        elif rd.confounders_required:
            rd_out["confounders_required"] = list(rd.confounders_required)
        if rd.time_window is not None:
            rd_out["time_window"] = rd.time_window
        if rd.sutva_concerns:
            rd_out["sutva_concerns"] = list(rd.sutva_concerns)
        if rd_out:
            out["required_data"] = rd_out
    if gap.if_provided is not None:
        out["if_provided"] = gap.if_provided
    if gap.alternative_paths:
        out["alternative_paths"] = list(gap.alternative_paths)
    return out


def from_dict(payload: dict) -> QueryResult:
    """Inverse of ``to_dict``.

    Not implemented in v0.1. Serialized results can be schema-validated
    via ``syntactic_validator.validate_result`` but cannot yet be
    reconstructed into a typed ``QueryResult``. Listed in
    ``v0_1_scope.md`` under out-of-scope; a later slice will add it
    together with the fixtures that need round-trip.
    """
    raise NotImplementedError("from_dict is not part of the v0.1 surface")


# ---------------------------------------------------------------------------
# Fix 3+4 §3.2 — LLM-proposed review surface aggregator (v0.1.5)
# ---------------------------------------------------------------------------


def _atom_repr(atom: Atom) -> str:
    """Short rendered form of an atom for review-surface display."""
    args = ",".join(a.name for a in atom.args)
    return f"{atom.predicate}({args})" if args else atom.predicate


def _probability_statement_key_repr(stmt: ProbabilityStatement) -> str:
    """Render a ProbabilityStatement as a P(...|...) key string for
    the review surface. Mirrors the runtime's format_probability_key
    shape but doesn't go through ProbabilityKey (we want the original
    statement's surface, not a canonicalised key)."""
    target_part = (
        f"{_atom_repr(stmt.target.atom)}={stmt.target.value}"
    )
    if stmt.given:
        given_part = ",".join(
            f"{_atom_repr(va.atom)}={va.value}" for va in stmt.given
        )
        body = f"{target_part}|{given_part}"
    else:
        body = target_part
    prefix = "P" if stmt.population is None else f"P_{stmt.population}"
    return f"{prefix}({body})"


def build_llm_proposed_review(program: "Program") -> dict | None:
    """Walk the program's statements and collect every LLM-proposed
    element (cause edges + probability priors) into a single audit
    surface that the user must see before trusting the result.

    Two collection criteria:

    - **Edges** (``CauseStatement``): ``annotations.source`` contains
      "llm" (case-insensitive substring match). Picks up
      ``"llm_proposal"`` (A2 convention) and any variant. Edges
      sourced from evidence (PubMed, KB, user) are excluded — they
      are not LLM-proposed.
    - **Probability priors** (``ProbabilityStatement``):
      ``provenance == "llm_prior"``. Includes the prior value, the
      target/given key, the population label, and the reason
      (``annotations.source``, validated non-empty by F3.1
      ``llm_prior_requires_source``).

    Returns ``None`` when neither category found any entries —
    in that case there's nothing to disclose, and the absence of
    the field keeps single-population non-LLM-prior fixtures byte-
    identical to pre-Fix-3+4 serialisations.

    Summary text gives the user a single sentence to ground the
    audit: "N edges + M probability priors come from LLM common
    knowledge. Themis's math is correct, but the answer hinges on
    these priors being reasonable — please review before using."

    Caller (``kernel._run_typed``) attaches this dict to each result's
    ``extensions.llm_proposed_review``. The review is program-wide so
    multi-query programs see the same review on every result.

    Charter: FIX_3_4_CHARTER_llm_mediated_transport.md §3.2.
    """
    edges: list[dict] = []
    probabilities: list[dict] = []

    for stmt in program.statements:
        if isinstance(stmt, CauseStatement):
            if stmt.annotations is None:
                continue
            source = stmt.annotations.source or ""
            if "llm" not in source.lower():
                continue
            edges.append({
                "from": _atom_repr(stmt.from_atom),
                "to": _atom_repr(stmt.to_atom),
                "source": source,
            })
        elif isinstance(stmt, ProbabilityStatement):
            if stmt.provenance != "llm_prior":
                continue
            reason = (
                stmt.annotations.source
                if stmt.annotations is not None else ""
            ) or ""
            entry: dict = {
                "key": _probability_statement_key_repr(stmt),
                "value": stmt.value,
                "reason": reason,
            }
            if stmt.population is not None:
                entry["population"] = stmt.population
            probabilities.append(entry)

    if not edges and not probabilities:
        return None

    n_edges = len(edges)
    n_probs = len(probabilities)
    parts: list[str] = []
    if n_edges:
        parts.append(f"{n_edges} 条边")
    if n_probs:
        parts.append(f"{n_probs} 个概率参数")
    composition = " + ".join(parts)
    summary = (
        f"{composition}来自 LLM 常识 prior。"
        f"Themis 数学计算正确，但答案依赖这些 prior 的合理性 —— "
        f"请审核后再使用。"
    )

    return {
        "edges": edges,
        "probabilities": probabilities,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Mechanism-audit surface (slice C) — functional-form assumption parity
# ---------------------------------------------------------------------------


def build_mechanism_audit(
    *,
    target: str,
    form: str,
    method: str,
    assumption: str,
    provenance: str = "default",
) -> dict:
    """Aggregate a numeric estimate's functional-form (mechanism)
    assumption into an audit surface mirroring ``build_llm_proposed_review``.

    The third leg of the SCM triad: structure (``CauseStatement`` edges)
    and parameters (``ProbabilityStatement`` theta) already flow through
    propose -> annotate -> audit; the functional form a continuous
    estimator assumes (linear / forest / drlearner) did not. This pulls
    that assumption out of the flat ``assumptions`` list into a labelled,
    provenance-tagged element so the renderer can disclose it as a
    load-bearing choice the user must audit — the curve's *shape* is an
    assumption, not a measured quantity.

    ``provenance`` is ``"default"`` here (the estimator auto-selected the
    family by sample size). A later slice promotes user / LLM-proposed
    forms to first-class declarations; this builder already carries the
    field so that extension is purely additive.

    Caller (``estimation.dispatch._try_dose_response_estimate``) attaches
    the returned dict to ``result.extensions.mechanism_audit``.
    """
    mechanism = {
        "target": target,
        "form": form,
        "method": method,
        "provenance": provenance,
        "assumption": assumption,
    }
    origin = (
        "系统按样本量自动选择"
        if provenance == "default"
        else f"来源：{provenance}"
    )
    summary = (
        f"这个数字依赖一个假设的函数形式（{form}，{origin}）—— 它是模型"
        f"假设，不是数据测得。Themis 在该假设下的估计是对的，但这个形式"
        f"本身是否合理需要你审核。"
    )
    return {"mechanisms": [mechanism], "summary": summary}


# ---------------------------------------------------------------------------
# Assumption ledger — one severity-ranked view over the scattered channels
# ---------------------------------------------------------------------------

# Severity ordering drives the ledger sort. The axis is "if this
# assumption is false, how does the conclusion die":
#   invalidating  — the number is not a causal effect at all
#   distorting    — shape / magnitude skewed, the average often survives
#   confidence_only — only the confidence is affected
_SEVERITY_RANK = {"invalidating": 0, "distorting": 1, "confidence_only": 2}


def build_assumption_ledger(
    result: dict, *, identification_specs: tuple = (),
) -> dict | None:
    """Aggregate every load-bearing assumption scattered across the
    result envelope into ONE severity-ranked ledger.

    A VIEW, not a rewrite. It reads the existing channels —
    ``data_gap_report`` (which proposal edges are actually load-bearing,
    i.e. on the answer path — that analysis already ran there),
    ``extensions.llm_proposed_review`` (LLM theta priors),
    ``extensions.mechanism_audit`` (functional form), and the
    ``identification_specs`` argument (identification assumptions
    structured at source by the estimator, passed directly so the
    schema-validated ``numeric_estimate`` block stays untouched) — and
    re-presents them as
    first-class entries. The source channels stay untouched; this is the
    single place provenance + severity are assigned, so an assumption's
    prominence tracks how load-bearing it is instead of which channel it
    happened to land in.

    Severity by category:

    - identification (no unmeasured confounding, overlap) -> invalidating
    - proposal edge ACTUALLY on the answer path -> invalidating (a
      proposed-but-unused edge is not load-bearing, so it never enters
      the ledger — no false alarm)
    - functional form (curve shape) -> distorting
    - LLM theta prior -> distorting

    Each entry carries ``claim`` / ``layer`` / ``provenance`` /
    ``severity`` / ``testable`` (identification assumptions are
    untestable by design; a form can be probed by switching estimators;
    an edge needs evidence). Returns ``None`` when nothing is assumed.

    Caller (``estimation.dispatch._try_dose_response_estimate``) attaches
    the result to ``result.extensions.assumption_ledger``; the renderer
    leads with it instead of the individual channels.
    """
    extensions = result.get("extensions") or {}
    entries: list[dict] = []

    # 1) identification assumptions — structured at source by the
    #    estimator, passed directly (not via schema-validated numeric_estimate)
    for spec in identification_specs or ():
        entry = {
            "claim": spec.get("claim", ""),
            "layer": spec.get("layer", "identification"),
            "provenance": "inherent",
            "severity": spec.get("severity", "invalidating"),
            "testable": bool(spec.get("testable", False)),
        }
        # The flat declaration this spec is the structured form of. It is
        # what lets the fold below be exact instead of a rule about which
        # channel spoke; a spec without one is disclosed twice rather
        # than wrongly, which is the safe direction here.
        if spec.get("id"):
            entry["id"] = str(spec["id"])
        entries.append(entry)

    # 2a) structural edges — ONLY the load-bearing ones. The authoritative
    #     load-bearing analysis already ran in the data_gap_report
    #     generator (supporting_paths + DAG-walk), which emits one
    #     UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH gap per proposal edge the
    #     answer actually traverses. Sourcing from there — not from the
    #     full ``llm_proposed_review`` edge list — means a proposed-but-
    #     unused edge no longer shows up as "invalidating": that was the
    #     false alarm the flat edge list produced. Covers LLM- and
    #     discovery-proposed edges alike (the gap description names which).
    report = result.get("data_gap_report") or {}
    for gap in report.get("gaps") or []:
        if gap.get("kind") != "unverified_proposal_edge_on_query_path":
            continue
        desc = gap.get("description", "")
        provenance = "discovery" if "发现算法" in desc else "llm_proposal"
        entries.append({
            "claim": desc,
            "layer": "structural_edge",
            "provenance": provenance,
            "severity": "invalidating",
            "testable": True,
        })

    # 2b) LLM theta priors — used in the numeric computation when present,
    #     so they stay in the ledger (magnitude-affecting -> distorting).
    review = extensions.get(blocks.LLM_PROPOSED_REVIEW) or {}
    for prob in review.get("probabilities") or []:
        entries.append({
            "claim": f"{prob.get('key')} = {prob.get('value')}（LLM 常识 prior）",
            "layer": "parameter",
            "provenance": "llm_prior",
            "severity": "distorting",
            "testable": True,
        })

    # 3) functional form (curve shape)
    mech = extensions.get(blocks.MECHANISM_AUDIT) or {}
    for m in mech.get("mechanisms") or []:
        entries.append({
            "claim": (
                f"{m.get('target')} 的函数形式为 {m.get('form')}"
                f"（{m.get('assumption', '')}）"
            ),
            "layer": "functional_form",
            "provenance": m.get("provenance", "estimator_default"),
            "severity": "distorting",
            "testable": True,
        })

    return _ledger(entries)


def _ledger(entries: list[dict]) -> dict | None:
    """Sort by severity and write the one-line summary. Shared by the
    identification-time build and the post-estimate augmentation so the two
    never drift on ordering or wording."""
    if not entries:
        return None

    # A severity outside the vocabulary sorts FIRST, not last: the renderer
    # leads with the head of this list, so an unrecognised value must surface
    # for someone to fix rather than sink below "only affects the interval".
    entries.sort(key=lambda e: _SEVERITY_RANK.get(e["severity"], -1))

    n_inval = sum(1 for e in entries if e["severity"] == "invalidating")
    n_other = len(entries) - n_inval
    parts: list[str] = []
    if n_inval:
        parts.append(f"{n_inval} 条一旦不成立、整条因果结论作废")
    if n_other:
        parts.append(f"{n_other} 条影响形状 / 量级或置信度")
    summary = (
        f"这个结论依赖 {len(entries)} 条假设："
        + "；".join(parts)
        + "。下面按严重度从高到低列出 —— Themis 的计算在这些假设下是对的，"
        "但假设本身的真假需要你逐条审核。"
    )

    return {"assumptions": entries, "summary": summary}


def augment_assumption_ledger(result: dict) -> None:
    """Fold the estimator's own ``numeric_estimate.assumptions`` into the
    ledger, creating the ledger when the result has none.

    ``build_assumption_ledger`` reads the channels that exist at
    identification time plus whatever ``identification_specs`` the caller
    passes in. That leaves the flat ``assumptions`` list — the oldest channel,
    and the only one EVERY estimator populates — outside the ledger unless the
    estimator's dispatch path happens to pass structured specs. The ledger is
    the surface both ``analysis_report`` and ``response_rendering.md`` treat as
    the lead disclosure, so an estimator that did not opt in produced an answer
    whose assumptions were nowhere on that surface — silently, and silently
    again for the next estimator added.

    Called from the one funnel every numeric answer passes through, so the
    floor holds for estimators that exist today and for those added later.

    **A declaration is folded unless some entry has claimed it by id.** An
    estimator that supplies structured identification specs has said some of
    these things in better words, and the spec names which one it restates,
    so the structured wording wins and nothing else goes missing.

    That was a guess until it was a declaration, and the guess was "if the
    ledger carries any identification entry, the whole flat list is its
    unstructured twin". Nineteen estimator families took that branch, and
    what it dropped was everything they declare BESIDES identification:
    which weights an IPW used, that a TMLE is a targeted substitution
    estimator, that an interval is cluster-robust, that proximal rests on
    Miao's model f, that a causation answer came back as bounds because no
    monotonicity was assumed. The verifier, written independently, had
    reached for the same escape hatch — so nothing on either side saw it.
    """
    from .assumption_glossary import classify_assumption

    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    declared = estimate.get("assumptions") or ()
    measured = _outcome_error_premises(result)
    if not declared and not measured:
        return

    extensions = result.setdefault("extensions", {})
    existing = extensions.get(blocks.ASSUMPTION_LEDGER)
    if existing is not None:
        entries = list(existing.get("assumptions") or ())
    else:
        # No ledger yet — the other three channels have never been read for
        # this result either, so read them all rather than shipping a ledger
        # that discloses the estimator's assumptions and hides the audited
        # mechanism sitting next to them.
        entries = list((build_assumption_ledger(result) or {}).get("assumptions") or ())

    for item in measured:
        entry = classify_assumption(item)
        entry["provenance"] = "measurement_declared"
        entries.append(entry)

    claimed = {str(e["id"]) for e in entries if e.get("id")}
    for item in declared:
        if str(item) in claimed:
            continue
        entry = classify_assumption(item)
        entry["provenance"] = "estimator_declared"
        entries.append(entry)
        claimed.add(str(item))

    ledger = _ledger(entries)
    if ledger is not None:
        extensions[blocks.ASSUMPTION_LEDGER] = ledger


def _outcome_error_premises(result: dict) -> tuple[str, ...]:
    """The premises declared by an outcome measurement-error assessment."""
    block = result.get("outcome_error")
    if not isinstance(block, dict):
        return ()
    return tuple(
        a for a in (block.get("assumptions") or ()) if isinstance(a, str)
    )
