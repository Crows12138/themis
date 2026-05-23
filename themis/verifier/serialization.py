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
    RelativeTimeIndex,
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
    # Phase 10: only emit success when False (back-compat — default True
    # means existing fixtures and rule emitters need not change).
    if not step.success:
        d["success"] = False
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
    if isinstance(v, dict):
        # Generic tagged-dict serialization for rules whose output is a
        # multi-quantity structured payload (e.g. mediation's TE / NDE /
        # NIE / CDE-per-m bundle). Keys must be strings (JSON limitation);
        # values recurse through _value_to_json so nested dicts / atoms /
        # tuples all work. Round-trips via "dict" decoder below.
        for k in v:
            if not isinstance(k, str):
                raise DerivationSerializationError(
                    f"dict keys must be strings (got {type(k).__name__})"
                )
        return {
            "kind": "dict",
            "items": {k: _value_to_json(val) for k, val in v.items()},
        }

    raise DerivationSerializationError(
        f"don't know how to serialize {type(v).__name__}"
    )


def _canonical_atom_order(atoms) -> list[Atom]:
    """Sort atoms by (predicate, args-names) so atom_set round-trips
    to the same JSON regardless of Python's hash randomness."""
    def key(a: Atom):
        time_key = None if a.time_index is None else ("relative", a.time_index.value)
        return (a.predicate, tuple(t.name for t in a.args), time_key)
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
    # V4: tuple of paths (each path = tuple of Atoms). Used by
    # cause_via_directed_path and d_connected_via_open_path to carry
    # the witnesses.
    if all(
        isinstance(p, tuple) and all(isinstance(a, Atom) for a in p)
        for p in tpl
    ):
        return {
            "kind": "atom_paths",
            "items": [
                [_atom_to_dict(a) for a in path] for path in tpl
            ],
        }
    raise DerivationSerializationError(
        f"tuple with mixed / unsupported element types: "
        f"{[type(x).__name__ for x in tpl]}"
    )


def _atom_to_dict(atom: Atom) -> dict:
    d = {
        "kind": "atom",
        "predicate": atom.predicate,
        "args": [_term_to_dict(t) for t in atom.args],
    }
    if atom.time_index is not None:
        d["time_index"] = {"kind": "relative", "value": atom.time_index.value}
    return d


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
        d_pr: dict = {
            "kind": "probability_ref",
            "target": _valued_atom_to_dict(expr.target),
            "given": [_valued_atom_to_dict(g) for g in expr.given],
        }
        # Fix 3+4: only emit population when set, so existing fixtures
        # (single-population formulas with population=None) serialize
        # identically to pre-fix and don't churn pinning tests.
        if expr.population is not None:
            d_pr["population"] = expr.population
        return d_pr
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
    # Phase 10: ``success`` is optional, default True. Failure-bearing
    # rules emit success=False so the DataGapReport generator can pick
    # them up when scanning derivation for unidentifiable / IV-missing /
    # transport-failure signals.
    success = d.get("success", True)
    if not isinstance(success, bool):
        raise DerivationSerializationError(
            f"steps[{step_index}].success must be a boolean"
        )
    return DerivationStep(
        rule=rule, inputs=inputs, output=output, step_id=step_id, success=success
    )


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
    try:
        return handler(v)
    except DerivationSerializationError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise DerivationSerializationError(
            f"malformed {kind!r} payload: {e}"
        ) from e


def _decode_atom(d: dict) -> Atom:
    pred = d.get("predicate")
    args_raw = d.get("args", [])
    if not isinstance(pred, str) or not isinstance(args_raw, list):
        raise DerivationSerializationError(
            "atom requires predicate:str and args:list"
        )
    time_raw = d.get("time_index")
    time_index = None
    if time_raw is not None:
        if not isinstance(time_raw, dict):
            raise DerivationSerializationError("atom.time_index must be a dict")
        if time_raw.get("kind") != "relative":
            raise DerivationSerializationError(
                "atom.time_index.kind must be 'relative'"
            )
        value = time_raw.get("value")
        if not isinstance(value, int) or isinstance(value, bool):
            raise DerivationSerializationError(
                "atom.time_index.value must be an integer"
            )
        time_index = RelativeTimeIndex(value=value)
    args = tuple(_decode_term(t) for t in args_raw)
    return Atom(predicate=pred, args=args, time_index=time_index)


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


def _decode_literal_atom_value(value, what: str):
    if isinstance(value, (bool, int, float, str)):
        return value
    raise DerivationSerializationError(
        f"{what} must be a literal atom value (bool/number/string)"
    )


def _decode_literal_valued_atom(d: dict, what: str) -> ValuedAtom:
    if not isinstance(d, dict):
        raise DerivationSerializationError(f"{what} must be a dict")
    atom_raw = d.get("atom")
    if not isinstance(atom_raw, dict):
        raise DerivationSerializationError(f"{what}.atom must be a dict")
    if "value" not in d:
        raise DerivationSerializationError(f"{what}.value is required")
    return ValuedAtom(
        atom=_decode_atom(atom_raw),
        value=_decode_literal_atom_value(d["value"], f"{what}.value"),
    )


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
    if paths_raw in (None, ()):
        paths = ()
    elif isinstance(paths_raw, list):
        decoded_paths = []
        for i, path in enumerate(paths_raw):
            if not isinstance(path, list):
                raise DerivationSerializationError(
                    f"structural_result.supporting_paths[{i}] must be a list of strings"
                )
            if not all(isinstance(node, str) for node in path):
                raise DerivationSerializationError(
                    f"structural_result.supporting_paths[{i}] must contain only strings"
                )
            decoded_paths.append(tuple(path))
        paths = tuple(decoded_paths)
    else:
        raise DerivationSerializationError(
            "structural_result.supporting_paths must be a list of string paths"
        )
    return StructuralResult(value=value, supporting_paths=paths)


def _decode_numeric_result(d: dict) -> NumericResult:
    value = d.get("value")
    interval_raw = d.get("interval")
    interval = None
    if interval_raw is None:
        interval = None
    elif isinstance(interval_raw, dict):
        if "low" not in interval_raw or "high" not in interval_raw:
            raise DerivationSerializationError(
                "numeric_result.interval requires both low and high"
            )
        interval = NumericInterval(
            low=float(interval_raw["low"]),
            high=float(interval_raw["high"]),
        )
    else:
        raise DerivationSerializationError(
            "numeric_result.interval must be an object when present"
        )
    unit = d.get("unit")
    return NumericResult(value=value, interval=interval, unit=unit)


def _decode_constant_expr(d: dict) -> ConstantExpr:
    if "value" not in d:
        raise DerivationSerializationError("constant.value is required")
    return ConstantExpr(value=float(d["value"]))


def _decode_probability_ref(d: dict) -> ProbabilityRefExpr:
    if "target" not in d:
        raise DerivationSerializationError("probability_ref.target is required")
    target = _decode_valued_atom(d["target"])
    given_raw = d.get("given", [])
    if not isinstance(given_raw, list):
        raise DerivationSerializationError("probability_ref.given must be a list")
    given = tuple(_decode_valued_atom(g) for g in given_raw)
    # Fix 3+4: optional population field. Missing = None (back-compat).
    population = d.get("population")
    if population is not None and not isinstance(population, str):
        raise DerivationSerializationError(
            "probability_ref.population must be a string when present"
        )
    return ProbabilityRefExpr(target=target, given=given, population=population)


def _decode_product(d: dict) -> ProductExpr:
    terms_raw = d.get("terms", [])
    if not isinstance(terms_raw, list):
        raise DerivationSerializationError("product.terms must be a list")
    terms = tuple(_value_from_json(t) for t in terms_raw)
    if not all(isinstance(term, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)) for term in terms):
        raise DerivationSerializationError("product.terms must contain only FormulaExpr values")
    return ProductExpr(terms=terms)


def _decode_sum(d: dict) -> SumExpr:
    bind_raw = d.get("bind")
    if not isinstance(bind_raw, dict):
        raise DerivationSerializationError("sum.bind must be an object")
    name = bind_raw.get("name")
    if not isinstance(name, str):
        raise DerivationSerializationError("sum.bind.name must be a string")
    bind = BindDecl(name=name)
    if "over" not in d:
        raise DerivationSerializationError("sum.over is required")
    over = _decode_atom(d["over"])
    if "body" not in d:
        raise DerivationSerializationError("sum.body is required")
    body = _value_from_json(d["body"])
    if not isinstance(body, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise DerivationSerializationError("sum.body must be a FormulaExpr")
    return SumExpr(bind=bind, over=over, body=body)


def _decode_atom_set(d: dict) -> frozenset:
    items = [_decode_atom(i) for i in d.get("items", [])]
    return frozenset(items)


def _decode_atom_tuple(d: dict) -> tuple:
    return tuple(_decode_atom(i) for i in d.get("items", []))


def _decode_valued_atom_tuple(d: dict) -> tuple:
    return tuple(_decode_valued_atom(i) for i in d.get("items", []))


def _decode_atom_paths(d: dict) -> tuple:
    items = d.get("items", [])
    if not isinstance(items, list):
        raise DerivationSerializationError("atom_paths.items must be a list")
    return tuple(
        tuple(_decode_atom(a) for a in path) for path in items
    )


def _decode_dict(d: dict) -> dict:
    items = d.get("items", {})
    if not isinstance(items, dict):
        raise DerivationSerializationError("dict.items must be a dict")
    return {k: _value_from_json(v) for k, v in items.items()}


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
    "atom_paths":         _decode_atom_paths,
    "dict":               _decode_dict,
}


# =========================================================================
# V5: VerificationContext serialization
# =========================================================================
#
# A VerificationContext is graph + query (+ optional theta). Encoding it
# together with a derivation lets external tools re-run verify_* end to
# end without any in-memory Python objects.
#
# Payload shape:
#
#   {
#     "version": "0.1",
#     "kind": "verification_context",
#     "graph": {"kind": "graph", ...},
#     "query": {"kind": "cause_query" | "assoc_query" | ...},
#     "theta": null | {"kind": "theta", "entries": [...], "domains": [...]}
#   }

from ..runtime.numeric_estimator import ProbabilityKey, Theta  # noqa: E402
from ..types import (  # noqa: E402
    AssocQuery,
    CauseQuery,
    CounterfactualAssumptions,
    CounterfactualQuery,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    Monotonicity,
    ProbabilityQuery,
)
from .context import VerificationContext  # noqa: E402


CONTEXT_VERSION = "0.1"
CONTEXT_KIND = "verification_context"


# ------------------------------------------------------------ query encode

def _intervention_to_dict(iv: Intervention) -> dict:
    return {
        "kind": "intervention",
        "atom": _atom_to_dict(iv.atom),
        "value": iv.value,
    }


def _query_to_dict(q) -> dict:
    if isinstance(q, CauseQuery):
        return {
            "kind": "cause_query",
            "from_atom": _atom_to_dict(q.from_atom),
            "to_atom": _atom_to_dict(q.to_atom),
        }
    if isinstance(q, AssocQuery):
        return {
            "kind": "assoc_query",
            "left": _atom_to_dict(q.left),
            "right": _atom_to_dict(q.right),
            "given": [_atom_to_dict(a) for a in q.given],
        }
    if isinstance(q, IdentifyQuery):
        return {
            "kind": "identify_query",
            "target": _atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_atom_to_dict(a) for a in q.given],
        }
    if isinstance(q, EffectQuery):
        d = {
            "kind": "effect_query",
            "target": _valued_atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_valued_atom_to_dict(a) for a in q.given],
        }
        if q.mediator is not None:
            d["mediator"] = _atom_to_dict(q.mediator)
        return d
    if isinstance(q, ProbabilityQuery):
        return {
            "kind": "probability_query",
            "target": _valued_atom_to_dict(q.target),
            "given": [_valued_atom_to_dict(a) for a in q.given],
        }
    if isinstance(q, CounterfactualQuery):
        d = {
            "kind": "counterfactual_query",
            "observed": _valued_atom_to_dict(q.observed),
            "counterfactual_intervention": _intervention_to_dict(
                q.counterfactual_intervention
            ),
            "counterfactual_target": _valued_atom_to_dict(
                q.counterfactual_target
            ),
        }
        if q.assumptions is not None and q.assumptions.monotonicity is not None:
            d["assumptions"] = {
                "monotonicity": q.assumptions.monotonicity.value
            }
        if q.factual_target_known is not None:
            d["factual_target_known"] = q.factual_target_known
        return d
    raise DerivationSerializationError(
        f"don't know how to serialize query type {type(q).__name__}"
    )


# ------------------------------------------------------------ theta encode

def _probability_key_to_dict(key: ProbabilityKey) -> dict:
    # Canonical ordering of given pairs keeps the JSON stable.
    ordered = sorted(
        key.given,
        key=lambda pair: (
            pair[0].predicate,
            tuple(t.name for t in pair[0].args),
            str(pair[1]),
        ),
    )
    d: dict = {
        "kind": "probability_key",
        "target_atom": _atom_to_dict(key.target_atom),
        "target_value": key.target_value,
        "given": [
            {"atom": _atom_to_dict(a), "value": v}
            for (a, v) in ordered
        ],
    }
    # Fix 3+4: only emit population when set, so existing single-
    # population theta serialisations stay identical to pre-fix.
    if key.population is not None:
        d["population"] = key.population
    return d


def _theta_to_dict(theta: Theta) -> dict:
    # Stable serialisation: sort entries by predicate / args / value
    # and domains by atom identity.
    entry_list = []
    for key in sorted(
        theta.entries.keys(),
        key=lambda k: (
            k.target_atom.predicate,
            tuple(t.name for t in k.target_atom.args),
            str(k.target_value),
            tuple(
                (a.predicate, tuple(t.name for t in a.args), str(v))
                for (a, v) in sorted(
                    k.given,
                    key=lambda pair: (
                        pair[0].predicate,
                        tuple(t.name for t in pair[0].args),
                        None if pair[0].time_index is None else (
                            "relative", pair[0].time_index.value
                        ),
                        str(pair[1]),
                    ),
                )
            ),
        ),
    ):
        entry_list.append({
            "key": _probability_key_to_dict(key),
            "value": theta.entries[key],
        })

    domain_list = []
    for atom in _canonical_atom_order(theta.domains.keys()):
        domain_list.append({
            "atom": _atom_to_dict(atom),
            "values": list(theta.domains[atom]),
        })

    return {
        "kind": "theta",
        "entries": entry_list,
        "domains": domain_list,
    }


# ------------------------------------------------------------ entry point

def context_to_dict(ctx: VerificationContext) -> dict:
    """Serialize a VerificationContext to a JSON-ready dict.

    The result validates against ``verification_context.schema.json``
    and can be fed back to ``context_from_dict`` to reconstruct the
    same context.
    """
    return {
        "version": CONTEXT_VERSION,
        "kind": CONTEXT_KIND,
        "graph": _graph_to_dict(ctx.graph),
        "query": _query_to_dict(ctx.query),
        "theta": _theta_to_dict(ctx.theta) if ctx.theta is not None else None,
    }


# ------------------------------------------------------------ query decode

def _decode_intervention(d: dict) -> Intervention:
    if not isinstance(d, dict):
        raise DerivationSerializationError("intervention must be a dict")
    atom_raw = d.get("atom")
    if not isinstance(atom_raw, dict):
        raise DerivationSerializationError("intervention.atom must be a dict")
    if "value" not in d:
        raise DerivationSerializationError("intervention.value is required")
    return Intervention(atom=_decode_atom(atom_raw), value=d.get("value"))


def _decode_query(d: dict):
    if not isinstance(d, dict):
        raise DerivationSerializationError("query must be a dict")
    kind = d.get("kind")
    if kind == "cause_query":
        if "from_atom" not in d:
            raise DerivationSerializationError("cause_query.from_atom is required")
        if "to_atom" not in d:
            raise DerivationSerializationError("cause_query.to_atom is required")
        return CauseQuery(
            from_atom=_decode_atom(d["from_atom"]),
            to_atom=_decode_atom(d["to_atom"]),
        )
    if kind == "assoc_query":
        if "left" not in d:
            raise DerivationSerializationError("assoc_query.left is required")
        if "right" not in d:
            raise DerivationSerializationError("assoc_query.right is required")
        given_raw = d.get("given", [])
        if not isinstance(given_raw, list):
            raise DerivationSerializationError("assoc_query.given must be a list")
        return AssocQuery(
            left=_decode_atom(d["left"]),
            right=_decode_atom(d["right"]),
            given=tuple(_decode_atom(a) for a in given_raw),
        )
    if kind == "identify_query":
        if "target" not in d:
            raise DerivationSerializationError("identify_query.target is required")
        if "intervention" not in d:
            raise DerivationSerializationError(
                "identify_query.intervention is required"
            )
        given_raw = d.get("given", [])
        if not isinstance(given_raw, list):
            raise DerivationSerializationError("identify_query.given must be a list")
        return IdentifyQuery(
            target=_decode_atom(d["target"]),
            intervention=_decode_intervention(d["intervention"]),
            given=tuple(_decode_atom(a) for a in given_raw),
        )
    if kind == "effect_query":
        if "target" not in d:
            raise DerivationSerializationError("effect_query.target is required")
        if "intervention" not in d:
            raise DerivationSerializationError(
                "effect_query.intervention is required"
            )
        given_raw = d.get("given", [])
        if not isinstance(given_raw, list):
            raise DerivationSerializationError("effect_query.given must be a list")
        mediator_raw = d.get("mediator")
        return EffectQuery(
            target=_decode_literal_valued_atom(d["target"], "effect_query.target"),
            intervention=_decode_intervention(d["intervention"]),
            given=tuple(
                _decode_literal_valued_atom(a, f"effect_query.given[{i}]")
                for i, a in enumerate(given_raw)
            ),
            mediator=(
                _decode_atom(mediator_raw) if mediator_raw is not None else None
            ),
        )
    if kind == "probability_query":
        if "target" not in d:
            raise DerivationSerializationError(
                "probability_query.target is required"
            )
        given_raw = d.get("given", [])
        if not isinstance(given_raw, list):
            raise DerivationSerializationError(
                "probability_query.given must be a list"
            )
        return ProbabilityQuery(
            target=_decode_literal_valued_atom(
                d["target"], "probability_query.target"
            ),
            given=tuple(
                _decode_literal_valued_atom(a, f"probability_query.given[{i}]")
                for i, a in enumerate(given_raw)
            ),
        )
    if kind == "counterfactual_query":
        if "observed" not in d:
            raise DerivationSerializationError(
                "counterfactual_query.observed is required"
            )
        if "counterfactual_intervention" not in d:
            raise DerivationSerializationError(
                "counterfactual_query.counterfactual_intervention is required"
            )
        if "counterfactual_target" not in d:
            raise DerivationSerializationError(
                "counterfactual_query.counterfactual_target is required"
            )
        assumptions_raw = d.get("assumptions")
        assumptions = None
        if assumptions_raw is not None:
            if not isinstance(assumptions_raw, dict):
                raise DerivationSerializationError(
                    "counterfactual_query.assumptions must be a dict"
                )
            monotonicity = assumptions_raw.get("monotonicity")
            if monotonicity is None:
                raise DerivationSerializationError(
                    "counterfactual_query.assumptions.monotonicity is required"
                )
            try:
                monotonicity_enum = Monotonicity(monotonicity)
            except ValueError as e:
                raise DerivationSerializationError(
                    "counterfactual_query.assumptions.monotonicity "
                    "must be 'non_decreasing' or 'non_increasing'"
                ) from e
            assumptions = CounterfactualAssumptions(
                monotonicity=monotonicity_enum
            )
        return CounterfactualQuery(
            observed=_decode_literal_valued_atom(
                d["observed"], "counterfactual_query.observed"
            ),
            counterfactual_intervention=_decode_intervention(
                d["counterfactual_intervention"]
            ),
            counterfactual_target=_decode_literal_valued_atom(
                d["counterfactual_target"],
                "counterfactual_query.counterfactual_target",
            ),
            assumptions=assumptions,
            factual_target_known=d.get("factual_target_known"),
        )
    raise DerivationSerializationError(f"unknown query kind: {kind!r}")


# ------------------------------------------------------------ theta decode

def _decode_probability_key(d: dict) -> ProbabilityKey:
    if d.get("kind") != "probability_key":
        raise DerivationSerializationError(
            "probability_key must have kind='probability_key'"
        )
    if "target_atom" not in d:
        raise DerivationSerializationError("probability_key.target_atom is required")
    if "target_value" not in d:
        raise DerivationSerializationError(
            "probability_key.target_value is required"
        )
    given_raw = d.get("given", [])
    if not isinstance(given_raw, list):
        raise DerivationSerializationError("probability_key.given must be a list")
    given_pairs_list = []
    for i, pair in enumerate(given_raw):
        if not isinstance(pair, dict):
            raise DerivationSerializationError(
                f"probability_key.given[{i}] must be a dict"
            )
        if "atom" not in pair:
            raise DerivationSerializationError(
                f"probability_key.given[{i}].atom is required"
            )
        if "value" not in pair:
            raise DerivationSerializationError(
                f"probability_key.given[{i}].value is required"
            )
        given_pairs_list.append((_decode_atom(pair["atom"]), pair["value"]))
    given_pairs = frozenset(given_pairs_list)
    # Fix 3+4: optional population. Missing key = None (back-compat).
    population = d.get("population")
    if population is not None and not isinstance(population, str):
        raise DerivationSerializationError(
            "probability_key.population must be a string when present"
        )
    return ProbabilityKey(
        target_atom=_decode_atom(d["target_atom"]),
        target_value=d["target_value"],
        given=given_pairs,
        population=population,
    )


def _decode_theta(d: dict) -> Theta:
    if d.get("kind") != "theta":
        raise DerivationSerializationError("theta must have kind='theta'")
    entries_raw = d.get("entries", [])
    domains_raw = d.get("domains", [])
    if not isinstance(entries_raw, list) or not isinstance(domains_raw, list):
        raise DerivationSerializationError(
            "theta.entries and theta.domains must be lists"
        )
    entries: dict = {}
    for i, e in enumerate(entries_raw):
        if not isinstance(e, dict):
            raise DerivationSerializationError("theta entry must be a dict")
        if "key" not in e:
            raise DerivationSerializationError(
                f"theta.entries[{i}].key is required"
            )
        if "value" not in e:
            raise DerivationSerializationError(
                f"theta.entries[{i}].value is required"
            )
        entries[_decode_probability_key(e["key"])] = float(e["value"])
    domains: dict = {}
    for i, row in enumerate(domains_raw):
        if not isinstance(row, dict):
            raise DerivationSerializationError("theta domain must be a dict")
        if "atom" not in row:
            raise DerivationSerializationError(
                f"theta.domains[{i}].atom is required"
            )
        atom = _decode_atom(row["atom"])
        values = row.get("values", [])
        if not isinstance(values, list):
            raise DerivationSerializationError("theta domain.values must be a list")
        domains[atom] = tuple(values)
    return Theta(entries=entries, domains=domains)


def context_from_dict(payload: dict) -> VerificationContext:
    """Inverse of ``context_to_dict``. Rebuilds a VerificationContext
    usable by ``verify_*`` with no Python-object inputs outside the
    JSON payload."""
    if not isinstance(payload, dict):
        raise DerivationSerializationError("context payload must be a dict")
    if payload.get("kind") != CONTEXT_KIND:
        raise DerivationSerializationError(
            f"context.kind must be {CONTEXT_KIND!r}, got {payload.get('kind')!r}"
        )
    if payload.get("version") != CONTEXT_VERSION:
        raise DerivationSerializationError(
            f"context.version must be {CONTEXT_VERSION!r}, "
            f"got {payload.get('version')!r}"
        )

    graph_raw = payload.get("graph")
    if not isinstance(graph_raw, dict):
        raise DerivationSerializationError("context.graph must be a tagged dict")
    graph = _decode_graph(graph_raw)

    query_raw = payload.get("query")
    if not isinstance(query_raw, dict):
        raise DerivationSerializationError("context.query must be a tagged dict")
    query = _decode_query(query_raw)

    theta_raw = payload.get("theta")
    theta = None
    if theta_raw is not None:
        if not isinstance(theta_raw, dict):
            raise DerivationSerializationError(
                "context.theta must be a tagged dict or null"
            )
        theta = _decode_theta(theta_raw)

    return VerificationContext(graph=graph, query=query, theta=theta)
