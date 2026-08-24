"""Slice V5: VerificationContext serialization.

The V5 contract: a context round-trips through JSON so an external
tool can hand both ``derivation`` and ``context`` payloads back to
the verifier and get accept/reject without touching any Python
objects that produced them.

Coverage:

- All six query types encode + decode (cause / assoc / identify /
  effect / probability / counterfactual).
- Graph nodes + edges survive.
- Theta entries + domains survive (including categorical domains).
- ``context_to_dict`` is stable (calling it twice yields the same
  dict).
- End-to-end: dispatch → serialize derivation + context → JSON
  string → parse → deserialize both → verify accepts.
- Tampering the JSON (graph edge, theta entry) is rejected by the
  verifier on the re-hydrated context.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime import theta_builder
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.runtime.scheduler import dispatch_all
from themis.ledger import Monotonicity
from themis.types import (
    AssocQuery,
    Atom,
    CauseQuery,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ProbabilityQuery,
    QueryKind,
    QueryStatement,
    ResultStatus,
    ValuedAtom,
)
from themis.verifier import (
    DerivationSerializationError,
    VerificationContext,
    VerificationError,
    context_from_dict,
    context_to_dict,
    derivation_from_dict,
    derivation_to_dict,
    verify_assoc,
    verify_counterfactual,
    verify_cause,
    verify_identify,
    verify_numeric,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "test_e2e" / "fixtures"
CONTEXT_SCHEMA_PATH = PROJECT_ROOT / "themis" / "schemas" / "verification_context.schema.json"


def _validate_context_schema(payload):
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    from themis.input.syntactic_validator import validator_for

    validator_for(CONTEXT_SCHEMA_PATH.name).validate(payload)


def _atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


# =========================================================== query round-trips

def _simple_graph():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_nodes_from([a, b])
    g.add_edge(a, b)
    return g, a, b


def test_cause_query_round_trip():
    g, a, b = _simple_graph()
    ctx = VerificationContext(graph=g, query=CauseQuery(from_atom=a, to_atom=b))
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, CauseQuery)
    assert back.query.from_atom == a
    assert back.query.to_atom == b


def test_assoc_query_round_trip():
    g, a, b = _simple_graph()
    c = _atom("c")
    g.add_node(c)
    ctx = VerificationContext(
        graph=g, query=AssocQuery(left=a, right=b, given=(c,)),
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, AssocQuery)
    assert back.query.left == a
    assert back.query.right == b
    assert back.query.given == (c,)


def test_identify_query_round_trip():
    g, a, b = _simple_graph()
    ctx = VerificationContext(
        graph=g,
        query=IdentifyQuery(
            target=b,
            intervention=Intervention(atom=a, value=False),
            given=(),
        ),
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, IdentifyQuery)
    assert back.query.target == b
    assert back.query.intervention.atom == a
    assert back.query.intervention.value is False


def test_effect_query_round_trip():
    g, a, b = _simple_graph()
    ctx = VerificationContext(
        graph=g,
        query=EffectQuery(
            target=ValuedAtom(atom=b, value=True),
            intervention=Intervention(atom=a, value=False),
            given=(),
        ),
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, EffectQuery)
    assert back.query.target.atom == b
    assert back.query.target.value is True
    assert back.query.intervention.value is False


def test_probability_query_round_trip():
    g, a, b = _simple_graph()
    ctx = VerificationContext(
        graph=g,
        query=ProbabilityQuery(
            target=ValuedAtom(atom=a, value=True),
            given=(ValuedAtom(atom=b, value=False),),
        ),
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, ProbabilityQuery)
    assert back.query.target.value is True
    assert back.query.given[0].atom == b
    assert back.query.given[0].value is False


def test_counterfactual_query_round_trip():
    g, a, b = _simple_graph()
    ctx = VerificationContext(
        graph=g,
        query=CounterfactualQuery(
            observed=ValuedAtom(atom=a, value=False),
            counterfactual_intervention=Intervention(atom=a, value=True),
            counterfactual_target=ValuedAtom(atom=b, value=True),
            assumptions=CounterfactualAssumptions(
                monotonicity=Monotonicity.NON_DECREASING
            ),
            factual_target_known=None,
        ),
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert isinstance(back.query, CounterfactualQuery)
    assert back.query.observed.value is False
    assert back.query.counterfactual_intervention.value is True
    assert back.query.counterfactual_target.value is True
    assert back.query.assumptions is not None
    assert back.query.assumptions.monotonicity is Monotonicity.NON_DECREASING


# =========================================================== theta round-trip

def test_theta_round_trip_boolean_domain():
    g, a, b = _simple_graph()
    key = ProbabilityKey(
        target_atom=b, target_value=True,
        given=frozenset({(a, True)}),
    )
    theta = Theta(entries={key: 0.7}, domains={a: (True, False)})
    ctx = VerificationContext(
        graph=g,
        query=ProbabilityQuery(
            target=ValuedAtom(atom=b, value=True),
            given=(ValuedAtom(atom=a, value=True),),
        ),
        theta=theta,
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert back.theta is not None
    assert back.theta.entries[key] == 0.7
    assert back.theta.domains[a] == (True, False)


def test_theta_round_trip_categorical_domain():
    """Non-boolean value domains must also round-trip."""
    g, a, _b = _simple_graph()
    weather = _atom("weather")
    g.add_node(weather)
    key = ProbabilityKey(
        target_atom=weather, target_value="sunny",
        given=frozenset(),
    )
    theta = Theta(
        entries={key: 0.6},
        domains={weather: ("sunny", "rain", "snow")},
    )
    ctx = VerificationContext(
        graph=g,
        query=ProbabilityQuery(
            target=ValuedAtom(atom=weather, value="sunny"), given=(),
        ),
        theta=theta,
    )
    payload = context_to_dict(ctx)
    _validate_context_schema(payload)
    back = context_from_dict(payload)
    assert back.theta.domains[weather] == ("sunny", "rain", "snow")
    assert back.theta.entries[key] == 0.6


def test_context_to_dict_is_stable():
    """Encoding twice must yield the same JSON."""
    g, a, b = _simple_graph()
    ctx = VerificationContext(graph=g, query=CauseQuery(from_atom=a, to_atom=b))
    assert context_to_dict(ctx) == context_to_dict(ctx)


# =========================================================== null theta

def test_theta_null_is_preserved():
    g, a, b = _simple_graph()
    ctx = VerificationContext(graph=g, query=CauseQuery(from_atom=a, to_atom=b))
    payload = context_to_dict(ctx)
    assert payload["theta"] is None
    back = context_from_dict(payload)
    assert back.theta is None


# =========================================================== e2e

def _run(path: Path):
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    ground = instantiate(program)
    graph = project(ground)
    theta = theta_builder.build_theta(ground)
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    return graph, theta, results, stmt_by_id


def _counterfactual_program_ast(*, factual_target_known: bool | None = None) -> dict:
    query: dict = {
        "kind": "counterfactual",
        "observed": {
            "atom": {
                "predicate": "chose_cs_major",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": False,
        },
        "counterfactual_intervention": {
            "atom": {
                "predicate": "chose_cs_major",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": True,
        },
        "counterfactual_target": {
            "atom": {
                "predicate": "higher_current_income",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": True,
        },
        "assumptions": {"monotonicity": "non_decreasing"},
    }
    if factual_target_known is not None:
        query["factual_target_known"] = factual_target_known

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "cause",
                "from": {
                    "predicate": "chose_cs_major",
                    "args": [{"type": "const", "name": "me"}],
                },
                "to": {
                    "predicate": "higher_current_income",
                    "args": [{"type": "const", "name": "me"}],
                },
            },
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_current_income", "domain": [True, False]},
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "chose_cs_major",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [],
                "value": 0.6,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "chose_cs_major",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                },
                "given": [],
                "value": 0.4,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "higher_current_income",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [
                    {
                        "atom": {
                            "predicate": "chose_cs_major",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    }
                ],
                "value": 0.7,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "higher_current_income",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                },
                "given": [
                    {
                        "atom": {
                            "predicate": "chose_cs_major",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    }
                ],
                "value": 0.3,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "higher_current_income",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [
                    {
                        "atom": {
                            "predicate": "chose_cs_major",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    }
                ],
                "value": 0.2,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "higher_current_income",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                },
                "given": [
                    {
                        "atom": {
                            "predicate": "chose_cs_major",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    }
                ],
                "value": 0.8,
            },
            {"kind": "query", "id": "q_cf", "query": query},
        ],
    }


def test_effect_derivation_verifies_from_fully_serialized_payload():
    """The headline V5 guarantee: hand a verifier JSON strings for
    both context and derivation, get back accept."""
    graph, theta, results, stmt_by_id = _run(
        FIXTURE_DIR / "numeric_backdoor.json"
    )
    r = next(
        x for x in results
        if x.query_kind is QueryKind.EFFECT
        and x.status is ResultStatus.NUMERICALLY_SOLVED
    )

    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    ctx_json = json.dumps(context_to_dict(ctx))
    deriv_json = json.dumps(derivation_to_dict(r.derivation))

    back_ctx = context_from_dict(json.loads(ctx_json))
    back_deriv = derivation_from_dict(json.loads(deriv_json))

    verify_numeric(back_deriv, back_ctx, r.numeric_result)


def test_identify_derivation_verifies_from_fully_serialized_payload():
    graph, _theta, results, stmt_by_id = _run(
        FIXTURE_DIR / "identify_backdoor.json"
    )
    r = next(
        x for x in results
        if x.query_kind is QueryKind.IDENTIFY
        and x.structural_result is not None
        and x.structural_result.value is True
    )
    ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
    back_ctx = context_from_dict(json.loads(json.dumps(context_to_dict(ctx))))
    back_deriv = derivation_from_dict(
        json.loads(json.dumps(derivation_to_dict(r.derivation)))
    )
    verify_identify(back_deriv, back_ctx, r.structural_result)


def test_assoc_positive_derivation_verifies_from_fully_serialized_payload():
    graph, _theta, results, stmt_by_id = _run(
        FIXTURE_DIR / "assoc_canonical.json"
    )
    r = next(
        x for x in results
        if x.query_kind is QueryKind.ASSOC
        and x.structural_result is not None
        and x.structural_result.value is True
    )
    ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
    back_ctx = context_from_dict(json.loads(json.dumps(context_to_dict(ctx))))
    back_deriv = derivation_from_dict(
        json.loads(json.dumps(derivation_to_dict(r.derivation)))
    )
    verify_assoc(back_deriv, back_ctx, r.structural_result)


def test_counterfactual_derivation_verifies_from_fully_serialized_payload():
    ast = _counterfactual_program_ast()
    program = validate_program(validate_ast(ast))
    ground = instantiate(program)
    graph = project(ground)
    theta = theta_builder.build_theta(ground)
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    r = next(
        x for x in results
        if x.query_kind is QueryKind.COUNTERFACTUAL
        and x.status is ResultStatus.COUNTERFACTUAL_SOLVED
    )
    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    back_ctx = context_from_dict(json.loads(json.dumps(context_to_dict(ctx))))
    back_deriv = derivation_from_dict(
        json.loads(json.dumps(derivation_to_dict(r.derivation)))
    )
    verify_counterfactual(back_deriv, back_ctx, r.numeric_result)


# =========================================================== tamper on context

def test_tampering_serialized_graph_edge_is_rejected_after_decode():
    """Remove an edge from the context JSON, then re-verify the
    original derivation against the altered context. Verifier should
    reject because the derivation's inline graph no longer matches
    the context."""
    graph, theta, results, stmt_by_id = _run(
        FIXTURE_DIR / "numeric_backdoor.json"
    )
    r = next(
        x for x in results
        if x.query_kind is QueryKind.EFFECT
        and x.status is ResultStatus.NUMERICALLY_SOLVED
    )
    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    ctx_payload = context_to_dict(ctx)
    assert ctx_payload["graph"]["edges"], "expected graph to have edges"
    ctx_payload["graph"]["edges"].pop()  # drop one edge
    bad_ctx = context_from_dict(ctx_payload)

    with pytest.raises(VerificationError):
        verify_numeric(r.derivation, bad_ctx, r.numeric_result)


def test_tampering_serialized_theta_entry_is_rejected_after_decode():
    """Change a theta entry's value in JSON; the verifier's R7
    recomputation now disagrees with the claimed evaluation."""
    graph, theta, results, stmt_by_id = _run(
        FIXTURE_DIR / "numeric_backdoor.json"
    )
    r = next(
        x for x in results
        if x.query_kind is QueryKind.EFFECT
        and x.status is ResultStatus.NUMERICALLY_SOLVED
    )
    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    ctx_payload = context_to_dict(ctx)
    assert ctx_payload["theta"]["entries"], "expected theta to have entries"
    # Shift every entry by +0.01 — R7 will now compute something
    # different from the derivation's claimed value.
    for entry in ctx_payload["theta"]["entries"]:
        entry["value"] = min(1.0, entry["value"] + 0.01)
    bad_ctx = context_from_dict(ctx_payload)

    with pytest.raises(VerificationError):
        verify_numeric(r.derivation, bad_ctx, r.numeric_result)


def test_tampering_counterfactual_theta_entry_is_rejected_after_decode():
    ast = _counterfactual_program_ast()
    program = validate_program(validate_ast(ast))
    ground = instantiate(program)
    graph = project(ground)
    theta = theta_builder.build_theta(ground)
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    r = next(
        x for x in results
        if x.query_kind is QueryKind.COUNTERFACTUAL
        and x.status is ResultStatus.COUNTERFACTUAL_SOLVED
    )
    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    ctx_payload = context_to_dict(ctx)
    assert ctx_payload["theta"]["entries"], "expected theta to have entries"
    changed = False
    for entry in ctx_payload["theta"]["entries"]:
        key = entry["key"]
        if (
            key["target_atom"]["predicate"] == "higher_current_income"
            and key["target_value"] is True
            and key["given"] == [
                {
                    "atom": {
                        "kind": "atom",
                        "predicate": "chose_cs_major",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                }
            ]
        ):
            entry["value"] = 0.1
            changed = True
            break
    assert changed, "expected to find P(higher_current_income=True|chose_cs_major=False)"
    bad_ctx = context_from_dict(ctx_payload)

    with pytest.raises(VerificationError):
        verify_counterfactual(r.derivation, bad_ctx, r.numeric_result)


# =========================================================== errors

def test_unknown_query_kind_is_rejected_on_decode():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {"kind": "frobnicated_query"},
        "theta": None,
    }
    with pytest.raises(DerivationSerializationError, match="query kind"):
        context_from_dict(payload)


def test_missing_cause_query_field_raises_serialization_error():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {
            "kind": "cause_query",
            "from_atom": {"kind": "atom", "predicate": "a", "args": []},
        },
        "theta": None,
    }
    with pytest.raises(DerivationSerializationError, match="to_atom"):
        context_from_dict(payload)


def test_missing_effect_query_target_raises_serialization_error():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {
            "kind": "effect_query",
            "intervention": {
                "kind": "intervention",
                "atom": {"kind": "atom", "predicate": "a", "args": []},
                "value": True,
            },
        },
        "theta": None,
    }
    with pytest.raises(DerivationSerializationError, match="target"):
        context_from_dict(payload)


def test_missing_theta_entry_value_raises_serialization_error():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {
            "kind": "probability_query",
            "target": {
                "kind": "valued_atom",
                "atom": {"kind": "atom", "predicate": "coin", "args": []},
                "value": True,
            },
        },
        "theta": {
            "kind": "theta",
            "entries": [
                {
                    "key": {
                        "kind": "probability_key",
                        "target_atom": {
                            "kind": "atom",
                            "predicate": "coin",
                            "args": [],
                        },
                        "target_value": True,
                        "given": [],
                    },
                }
            ],
            "domains": [],
        },
    }
    with pytest.raises(DerivationSerializationError, match="value"):
        context_from_dict(payload)


def test_context_schema_rejects_non_literal_probability_query_value():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {
            "kind": "probability_query",
            "target": {
                "kind": "valued_atom",
                "atom": {"kind": "atom", "predicate": "coin", "args": []},
                "value": {"kind": "step_ref", "step_id": "s1"},
            },
        },
        "theta": None,
    }
    with pytest.raises(Exception):
        _validate_context_schema(payload)


def test_context_decode_rejects_non_literal_effect_query_value():
    payload = {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": {
            "kind": "effect_query",
            "target": {
                "kind": "valued_atom",
                "atom": {"kind": "atom", "predicate": "coin", "args": []},
                "value": {"kind": "step_ref", "step_id": "s1"},
            },
            "intervention": {
                "kind": "intervention",
                "atom": {"kind": "atom", "predicate": "coin", "args": []},
                "value": False,
            },
        },
        "theta": None,
    }
    with pytest.raises(DerivationSerializationError, match="literal atom value"):
        context_from_dict(payload)


def test_wrong_context_kind_is_rejected():
    with pytest.raises(DerivationSerializationError, match="kind"):
        context_from_dict(
            {"version": "0.1", "kind": "something_else",
             "graph": {"kind": "graph", "nodes": [], "edges": []},
             "query": {"kind": "cause_query",
                       "from_atom": {"kind": "atom", "predicate": "a", "args": []},
                       "to_atom": {"kind": "atom", "predicate": "b", "args": []}}}
        )


# ======================================= intervention values must be literals

_IV_ATOM = {"kind": "atom", "predicate": "treat", "args": []}
_IV_VALUED_ATOM = {"kind": "valued_atom", "atom": _IV_ATOM, "value": True}


def _intervention(value):
    return {"kind": "intervention", "atom": _IV_ATOM, "value": value}


def _context_around(query: dict) -> dict:
    return {
        "version": "0.1",
        "kind": "verification_context",
        "graph": {"kind": "graph", "nodes": [], "edges": []},
        "query": query,
        "theta": None,
    }


# Every grammatical place a caller can spell an intervention, paired with
# the accessor that reads it back off the decoded query.
_INTERVENTION_SITES = [
    pytest.param(
        lambda v: {
            "kind": "identify_query",
            "target": _IV_ATOM,
            "intervention": _intervention(v),
            "given": [],
        },
        lambda q: q.intervention,
        id="identify_query.intervention",
    ),
    pytest.param(
        lambda v: {
            "kind": "effect_query",
            "target": _IV_VALUED_ATOM,
            "intervention": _intervention(v),
            "given": [],
        },
        lambda q: q.intervention,
        id="effect_query.intervention",
    ),
    pytest.param(
        lambda v: {
            "kind": "effect_query",
            "target": _IV_VALUED_ATOM,
            "intervention": _intervention(True),
            "given": [],
            "extra_interventions": [_intervention(v)],
        },
        lambda q: q.extra_interventions[0],
        id="effect_query.extra_interventions",
    ),
    pytest.param(
        lambda v: {
            "kind": "counterfactual_query",
            "observed": _IV_VALUED_ATOM,
            "counterfactual_intervention": _intervention(v),
            "counterfactual_target": _IV_VALUED_ATOM,
        },
        lambda q: q.counterfactual_intervention,
        id="counterfactual_query.counterfactual_intervention",
    ),
]


@pytest.mark.parametrize(("build_query", "read_back"), _INTERVENTION_SITES)
@pytest.mark.parametrize(
    "not_a_literal", [None, [1, 2], {"a": 1}], ids=["null", "list", "dict"],
)
def test_every_intervention_site_refuses_a_non_literal_value(
    build_query, read_back, not_a_literal,
):
    """Guards the one decoder with no schema standing behind it.

    ``context_from_dict`` is exported from ``themis.verifier`` and runs
    no jsonschema validation: every shape check inside it is written by
    hand, so a check nothing reaches is a check the next refactor can
    delete with the whole suite still green. This is that reach.

    ``Intervention.value`` is annotated as a literal atom value and the
    solvers downstream read it as one. Decoded without the check, a null
    or a container landed inside a ``VerificationContext`` its own
    annotation forbids, and verification then went ahead on that query —
    so whatever broke, broke somewhere else, far from the payload that
    caused it.

    An intervention can be spelled in four grammatical places. Narrowing
    three and leaving the fourth open is not a contract, so all four are
    asked the same question here.
    """
    with pytest.raises(
        DerivationSerializationError, match="literal atom value"
    ):
        context_from_dict(_context_around(build_query(not_a_literal)))


@pytest.mark.parametrize(("build_query", "read_back"), _INTERVENTION_SITES)
@pytest.mark.parametrize("literal", [True, False, 0, 1.5, "sunny"])
def test_literal_intervention_values_survive_the_narrowing_unchanged(
    build_query, read_back, literal,
):
    """Interventions were never boolean-only, and the check above must
    not quietly make them so.

    ``do(weather = "sunny")`` and ``do(dose = 1.5)`` are inside the
    language, so a guard spelled "must be a bool" would read as a bug
    fix and land as a contract change, shrinking what an external tool
    is allowed to hand the verifier. This holds the accepted set at
    exactly the literal atom values, type included: ``0`` must come back
    as ``0`` and not as ``False``.
    """
    query = context_from_dict(_context_around(build_query(literal))).query
    value = read_back(query).value

    assert value == literal
    assert type(value) is type(literal)
