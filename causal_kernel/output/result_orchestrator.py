"""Serialize a typed QueryResult into the JSON shape described in
query_result.schema.json.

Responsibilities:
- enum -> string
- dataclass -> dict
- omit None-valued optional fields and empty collections
- emit structured formula AST (never stringify it)

This is the reverse side of syntactic_validator.validate_result:
together they form a round-trip contract.
"""
from __future__ import annotations

from ..types import (
    Atom,
    ConstantExpr,
    ConstTerm,
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
    return {
        "predicate": atom.predicate,
        "args": [_term_to_dict(t) for t in atom.args],
    }


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
        d["investigation_requests"] = [
            {
                "action": r.action.value,
                "target": r.target,
                "priority": r.priority.value,
                **({"note": r.note} if r.note is not None else {}),
            }
            for r in result.investigation_requests
        ]
    if result.explanation is not None:
        d["explanation"] = result.explanation
    if result.extensions is not None:
        d["extensions"] = result.extensions
    return d


def from_dict(payload: dict) -> QueryResult:
    """Inverse of to_dict. Used for loading stored results in tests.

    Slice 1 only covers cause-query results. Later slices extend.
    """
    raise NotImplementedError
