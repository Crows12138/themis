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

from ..types import (
    Atom,
    ConstantExpr,
    ConstTerm,
    DataGap,
    DataGapReport,
    FormulaExpr,
    NumericResult,
    ProbabilityRefExpr,
    ProductExpr,
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
                **({"reason": m.reason} if m.reason is not None else {}),
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
        if rd.confounders_required:
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
