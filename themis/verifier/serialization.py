"""Derivation serialization (slice V2).

Round-trippable JSON form for ``tuple[DerivationStep, ...]``. The
serialization layer pins a tagged representation for every value type
that can appear inside a derivation's inputs or output.

Scope V2 covers:

- DerivationStep → dict and back
- All value types that V0/V1 rules use:
  primitive / Atom / ValuedAtom / VarRef / StepRef / nx.DiGraph /
  StructuralResult / NumericResult / FormulaExpr variants /
  tuple of Atom / frozenset of Atom / tuple of ValuedAtom

What V2 deliberately does NOT serialize:

- VerificationContext itself (graph / theta / query). Those remain
  Python-object inputs the caller passes to ``verify_*``. Each step
  does still carry an inline graph in its ``inputs`` dict — that
  graph round-trips through the serializer too, and the verifier's
  ``_assert_same_graph`` will reject mismatches against the context
  as usual.

External tools therefore get:

1. A canonical JSON form for the derivation, validated against
   ``derivation.schema.json`` (outer structure) and the verifier
   itself (rule-specific input/output shapes).
2. The ability to store / diff / display a derivation.
3. The ability to re-hydrate it into Python objects and re-run
   ``verify_identify`` / ``verify_numeric`` against an in-memory
   context.
"""
from __future__ import annotations

from typing import Any

import networkx as nx

from ..types import (
    Atom,
    BindDecl,
    ConstantExpr,
    ConstTerm,
    DerivationStep,
    FormulaExpr,
    NumericInterval,
    NumericResult,
    ProbabilityRefExpr,
    ProductExpr,
    StepRef,
    StructuralResult,
    SumExpr,
    Term,
    ValuedAtom,
    VarRef,
    VarTerm,
)

DERIVATION_VERSION = "0.1"
DERIVATION_KIND = "derivation"


class DerivationSerializationError(ValueError):
    """Raised when the JSON form can't be round-tripped — unknown
    ``kind`` tag, missing required field, type mismatch. Purely a
    shape error; semantic verification happens later."""


# =============================================================== encode

def derivation_to_dict(
    derivation: tuple[DerivationStep, ...],
) -> dict:
    """Serialize a derivation to a JSON-ready dict matching
    ``derivation.schema.json``."""
    return {
        "version": DERIVATION_VERSION,
        "kind": DERIVATION_KIND,
        "steps": [_step_to_dict(s) for s in derivation],
    }


def _step_to_dict(step: DerivationStep) -> dict:
    d: dict = {
        "rule": step.rule,
        "inputs": {k: _value_to_json(v) for k, v in step.inputs.items()},
        "output": _value_to_json(step.output),
    }
    if step.step_id is not None:
        d["step_id"] = step.step_id
    return d


def _value_to_json(v: Any) -> Any:
    # Primitives pass through unchanged.
    if v is None or isinstance(v, (bool, int, float, str)):
        return v

    if isinstance(v, Atom):
        return _atom_to_dict(v)
    if isinstance(v, ValuedAtom):
        return _valued_atom_to_dict(v)
    if isinstance(v, VarRef):
        return {"kind": "var_ref", "name": v.name}
    if isinstance(v, StepRef):
        return {"kind": "step_ref", "step_id": v.step_id}
    if isinstance(v, nx.DiGraph):
        return _graph_to_dict(v)
    if isinstance(v, StructuralResult):
        return _structural_result_to_dict(v)
    if isinstance(v, NumericResult):
        return _numeric_result_to_dict(v)
    if isinstance(v, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        return _formula_to_dict(v)
    if isinstance(v, frozenset):
        return {
            "kind": "atom_set",
            "items": [_value_to_json(a) for a in _canonical_atom_order(v)],
        }
    if isinstance(v, tuple):
        return _tuple_to_dict(v)

    raise DerivationSerializationError(
        f"don't know how to serialize {type(v).__name__}"
    )


def _canonical_atom_order(atoms) -> list[Atom]:
    """Sort atoms by (predicate, args-names) so atom_set round-trips
    to the same JSON regardless of Python's hash randomness."""
    def key(a: Atom):
        return (a.predicate, tuple(t.name for t in a.args))
    return sorted(atoms, key=key)


def _tuple_to_dict(tpl: tuple) -> dict:
    if not tpl:
        # Empty tuple is ambiguous — tag as the most common empty
        # container we use (atom_tuple). Deserializer will honor whichever
        # it sees; rules that expect a specific container type still
        # check isinstance(..., tuple) which matches both reconstructions.
        return {"kind": "atom_tuple", "items": []}
    if all(isinstance(a, Atom) for a in tpl):
        return {
            "kind": "atom_tuple",
            "items": [_atom_to_dict(a) for a in tpl],
        }
    if all(isinstance(a, ValuedAtom) for a in tpl):
        return {
            "kind": "valued_atom_tuple",
            "items": [_valued_atom_to_dict(a) for a in tpl],
        }
    raise DerivationSerializationError(
        f"tuple with mixed / unsupported element types: "
        f"{[type(x).__name__ for x in tpl]}"
    )


def _atom_to_dict(atom: Atom) -> dict:
    return {
        "kind": "atom",
        "predicate": atom.predicate,
        "args": [_term_to_dict(t) for t in atom.args],
    }


def _term_to_dict(term: Term) -> dict:
    if isinstance(term, ConstTerm):
        return {"type": "const", "name": term.name}
    if isinstance(term, VarTerm):
        return {"type": "var", "name": term.name}
    raise DerivationSerializationError(f"unknown term: {type(term).__name__}")


def _valued_atom_to_dict(va: ValuedAtom) -> dict:
    return {
        "kind": "valued_atom",
        "atom": _atom_to_dict(va.atom),
        "value": _value_to_json(va.value),
    }


def _graph_to_dict(g: nx.DiGraph) -> dict:
    """Encode a DiGraph of Atoms as {nodes: [atoms], edges: [[i, j], ...]}
    using node-list indices for edges. Nodes sorted canonically so the
    serialization is stable."""
    ordered_nodes = _canonical_atom_order(g.nodes())
    index_of = {a: i for i, a in enumerate(ordered_nodes)}
    edges = sorted(
        [index_of[u], index_of[v]] for (u, v) in g.edges()
    )
    return {
        "kind": "graph",
        "nodes": [_atom_to_dict(a) for a in ordered_nodes],
        "edges": edges,
    }


def _structural_result_to_dict(sr: StructuralResult) -> dict:
    d = {"kind": "structural_result", "value": sr.value}
    if sr.supporting_paths:
        d["supporting_paths"] = [list(p) for p in sr.supporting_paths]
    return d


def _numeric_result_to_dict(nr: NumericResult) -> dict:
    d: dict = {"kind": "numeric_result", "value": nr.value}
    if nr.interval is not None:
        d["interval"] = {"low": nr.interval.low, "high": nr.interval.high}
    if nr.unit is not None:
        d["unit"] = nr.unit
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
    raise DerivationSerializationError(
        f"unknown formula node: {type(expr).__name__}"
    )


# =============================================================== decode

def derivation_from_dict(payload: dict) -> tuple[DerivationStep, ...]:
    """Inverse of ``derivation_to_dict``. Validates the outer structure
    and re-hydrates each step's inputs / output into typed Python
    objects. Semantic verification is NOT performed here — call
    ``verify_identify`` / ``verify_numeric`` on the returned tuple."""
    if not isinstance(payload, dict):
        raise DerivationSerializationError("payload must be a dict")
    if payload.get("kind") != DERIVATION_KIND:
        raise DerivationSerializationError(
            f"kind must be {DERIVATION_KIND!r}, got {payload.get('kind')!r}"
        )
    if payload.get("version") != DERIVATION_VERSION:
        raise DerivationSerializationError(
            f"version must be {DERIVATION_VERSION!r}, "
            f"got {payload.get('version')!r}"
        )
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise DerivationSerializationError("steps must be a list")
    return tuple(_step_from_dict(s, i) for i, s in enumerate(steps))


def _step_from_dict(d: dict, step_index: int) -> DerivationStep:
    if not isinstance(d, dict):
        raise DerivationSerializationError(
            f"steps[{step_index}] must be a dict"
        )
    rule = d.get("rule")
    if not isinstance(rule, str) or not rule:
        raise DerivationSerializationError(
            f"steps[{step_index}].rule must be a non-empty string"
        )
    inputs_raw = d.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise DerivationSerializationError(
            f"steps[{step_index}].inputs must be a dict"
        )
    inputs = {k: _value_from_json(v) for k, v in inputs_raw.items()}
    if "output" not in d:
        raise DerivationSerializationError(
            f"steps[{step_index}] missing output"
        )
    output = _value_from_json(d["output"])
    step_id = d.get("step_id")
    if step_id is not None and not isinstance(step_id, str):
        raise DerivationSerializationError(
            f"steps[{step_index}].step_id must be a string or null"
        )
    return DerivationStep(rule=rule, inputs=inputs, output=output, step_id=step_id)


def _value_from_json(v: Any) -> Any:
    # Primitive pass-through.
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if not isinstance(v, dict):
        raise DerivationSerializationError(
            f"value must be primitive or tagged dict, got {type(v).__name__}"
        )
    kind = v.get("kind")
    handler = _DECODE_BY_KIND.get(kind)
    if handler is None:
        raise DerivationSerializationError(
            f"unknown value kind: {kind!r}"
        )
    return handler(v)


def _decode_atom(d: dict) -> Atom:
    pred = d.get("predicate")
    args_raw = d.get("args", [])
    if not isinstance(pred, str) or not isinstance(args_raw, list):
        raise DerivationSerializationError(
            "atom requires predicate:str and args:list"
        )
    args = tuple(_decode_term(t) for t in args_raw)
    return Atom(predicate=pred, args=args)


def _decode_term(d: dict) -> Term:
    if not isinstance(d, dict):
        raise DerivationSerializationError("term must be a dict")
    t = d.get("type")
    name = d.get("name")
    if not isinstance(name, str):
        raise DerivationSerializationError("term.name must be a string")
    if t == "const":
        return ConstTerm(name=name)
    if t == "var":
        return VarTerm(name=name)
    raise DerivationSerializationError(f"unknown term type: {t!r}")


def _decode_valued_atom(d: dict) -> ValuedAtom:
    atom_raw = d.get("atom")
    if not isinstance(atom_raw, dict):
        raise DerivationSerializationError("valued_atom.atom must be a dict")
    atom = _decode_atom(atom_raw)
    value = _value_from_json(d.get("value"))
    return ValuedAtom(atom=atom, value=value)


def _decode_var_ref(d: dict) -> VarRef:
    name = d.get("name")
    if not isinstance(name, str):
        raise DerivationSerializationError("var_ref.name must be a string")
    return VarRef(name=name)


def _decode_step_ref(d: dict) -> StepRef:
    sid = d.get("step_id")
    if not isinstance(sid, str):
        raise DerivationSerializationError("step_ref.step_id must be a string")
    return StepRef(step_id=sid)


def _decode_graph(d: dict) -> nx.DiGraph:
    nodes_raw = d.get("nodes", [])
    edges_raw = d.get("edges", [])
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        raise DerivationSerializationError(
            "graph.nodes and graph.edges must be lists"
        )
    nodes = [_decode_atom(n) for n in nodes_raw]
    g = nx.DiGraph()
    for a in nodes:
        g.add_node(a)
    for e in edges_raw:
        if not isinstance(e, list) or len(e) != 2:
            raise DerivationSerializationError(
                "graph.edges[i] must be a [src_idx, dst_idx] pair"
            )
        i, j = e
        if not (isinstance(i, int) and isinstance(j, int)):
            raise DerivationSerializationError(
                "graph edge indices must be ints"
            )
        if not (0 <= i < len(nodes) and 0 <= j < len(nodes)):
            raise DerivationSerializationError(
                "graph edge index out of range"
            )
        g.add_edge(nodes[i], nodes[j])
    return g


def _decode_structural_result(d: dict) -> StructuralResult:
    value = d.get("value")
    paths_raw = d.get("supporting_paths", ())
    if isinstance(paths_raw, list):
        paths = tuple(tuple(p) for p in paths_raw)
    else:
        paths = ()
    return StructuralResult(value=value, supporting_paths=paths)


def _decode_numeric_result(d: dict) -> NumericResult:
    value = d.get("value")
    interval_raw = d.get("interval")
    interval = None
    if isinstance(interval_raw, dict):
        interval = NumericInterval(
            low=float(interval_raw["low"]),
            high=float(interval_raw["high"]),
        )
    unit = d.get("unit")
    return NumericResult(value=value, interval=interval, unit=unit)


def _decode_constant_expr(d: dict) -> ConstantExpr:
    return ConstantExpr(value=float(d["value"]))


def _decode_probability_ref(d: dict) -> ProbabilityRefExpr:
    target = _decode_valued_atom(d["target"])
    given = tuple(_decode_valued_atom(g) for g in d.get("given", []))
    return ProbabilityRefExpr(target=target, given=given)


def _decode_product(d: dict) -> ProductExpr:
    terms = tuple(_value_from_json(t) for t in d.get("terms", []))
    return ProductExpr(terms=terms)


def _decode_sum(d: dict) -> SumExpr:
    bind = BindDecl(name=d["bind"]["name"])
    over = _decode_atom(d["over"])
    body = _value_from_json(d["body"])
    return SumExpr(bind=bind, over=over, body=body)


def _decode_atom_set(d: dict) -> frozenset:
    items = [_decode_atom(i) for i in d.get("items", [])]
    return frozenset(items)


def _decode_atom_tuple(d: dict) -> tuple:
    return tuple(_decode_atom(i) for i in d.get("items", []))


def _decode_valued_atom_tuple(d: dict) -> tuple:
    return tuple(_decode_valued_atom(i) for i in d.get("items", []))


_DECODE_BY_KIND = {
    "atom":               _decode_atom,
    "valued_atom":        _decode_valued_atom,
    "var_ref":            _decode_var_ref,
    "step_ref":           _decode_step_ref,
    "graph":              _decode_graph,
    "structural_result":  _decode_structural_result,
    "numeric_result":     _decode_numeric_result,
    "constant":           _decode_constant_expr,
    "probability_ref":    _decode_probability_ref,
    "product":            _decode_product,
    "sum":                _decode_sum,
    "atom_set":           _decode_atom_set,
    "atom_tuple":         _decode_atom_tuple,
    "valued_atom_tuple":  _decode_valued_atom_tuple,
}
