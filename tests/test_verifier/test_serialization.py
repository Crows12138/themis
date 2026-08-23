"""Slice V2: JSON round-trip for DerivationStep tuples.

The V2 contract is:

1. ``derivation_to_dict(d)`` produces a JSON-serializable dict that
   validates against ``derivation.schema.json``.
2. ``derivation_from_dict(to_dict(d))`` produces a derivation the
   verifier accepts against the same context / claimed result.
3. Serialization is stable: ``to_dict`` twice gives the same dict.
4. Tampering the JSON (changing a step's output, swapping a rule
   name, mutating a graph edge) causes verification to reject.

V2 deliberately does NOT serialize the ``VerificationContext``
itself (graph / theta / query); those remain Python-object inputs
to ``verify_*``. This keeps V2 focused on the derivation surface.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime import theta_builder
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    QueryKind,
    QueryStatement,
    ResultStatus,
)
from themis.verifier import (
    DerivationSerializationError,
    VerificationContext,
    VerificationError,
    derivation_from_dict,
    derivation_to_dict,
    verify_identify,
    verify_numeric,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "test_e2e" / "fixtures"
DERIVATION_SCHEMA_PATH = PROJECT_ROOT / "themis" / "schemas" / "derivation.schema.json"


def _load_derivation_schema():
    """Load the derivation JSON schema. Uses jsonschema if available,
    else returns None and validation-against-schema tests get skipped."""
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return None
    return json.loads(DERIVATION_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_schema(payload):
    """Best-effort JSON-schema validation; skip if jsonschema missing."""
    if _load_derivation_schema() is None:
        pytest.skip("jsonschema not installed")
    from themis.input.syntactic_validator import validator_for

    validator_for(DERIVATION_SCHEMA_PATH.name).validate(payload)


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


# =================================================================== schema

def test_derivation_schema_is_valid_jsonschema():
    import json as _json
    schema = _json.loads(DERIVATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("derivation.schema.json")
    assert schema["properties"]["version"]["const"] == "0.1"
    assert schema["properties"]["kind"]["const"] == "derivation"


def test_schema_rejects_incomplete_tagged_payloads():
    payload = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "x",
                "inputs": {},
                "output": {"kind": "probability_ref"},
            }
        ],
    }
    with pytest.raises(Exception):
        _validate_schema(payload)


# =================================================================== identify

def test_identify_derivation_round_trips_and_verifies():
    path = FIXTURE_DIR / "identify_backdoor.json"
    graph, _theta, results, stmt_by_id = _run(path)
    r = next(
        x for x in results
        if x.query_kind is QueryKind.IDENTIFY
        and x.structural_result is not None
        and x.structural_result.value is True
        and x.derivation
    )

    payload = derivation_to_dict(r.derivation)
    _validate_schema(payload)
    # Serialization is stable: exporting twice gives the same dict.
    assert derivation_to_dict(r.derivation) == payload

    # JSON can actually go through a string round-trip.
    as_string = json.dumps(payload)
    reparsed = json.loads(as_string)
    assert reparsed == payload

    back = derivation_from_dict(reparsed)
    assert len(back) == len(r.derivation)
    # Step ids and rules preserved exactly.
    for a, b in zip(r.derivation, back):
        assert a.step_id == b.step_id
        assert a.rule == b.rule
    # And the verifier still accepts the deserialized derivation.
    ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
    verify_identify(back, ctx, r.structural_result)


# =================================================================== numeric

def test_numeric_effect_derivation_round_trips_and_verifies():
    path = FIXTURE_DIR / "numeric_backdoor.json"
    graph, theta, results, stmt_by_id = _run(path)
    r = next(
        x for x in results
        if x.status is ResultStatus.NUMERICALLY_SOLVED
        and x.query_kind is QueryKind.EFFECT
        and x.derivation
    )

    payload = derivation_to_dict(r.derivation)
    _validate_schema(payload)
    back = derivation_from_dict(payload)

    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    verify_numeric(back, ctx, r.numeric_result)


def test_probability_derivation_round_trips_and_verifies():
    path = FIXTURE_DIR / "probability_no_graph.json"
    graph, theta, results, stmt_by_id = _run(path)
    r = next(
        x for x in results
        if x.status is ResultStatus.NUMERICALLY_SOLVED
        and x.query_kind is QueryKind.PROBABILITY
        and x.derivation
    )

    payload = derivation_to_dict(r.derivation)
    _validate_schema(payload)
    back = derivation_from_dict(payload)

    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    verify_numeric(back, ctx, r.numeric_result)


# =================================================================== tamper

def test_tampering_json_output_causes_verifier_reject_after_decode():
    """Mutate a step's numeric output in the JSON, deserialize, then
    watch the verifier reject. The JSON is the integrity surface —
    once it changes, the verifier must catch it."""
    path = FIXTURE_DIR / "numeric_backdoor.json"
    graph, theta, results, stmt_by_id = _run(path)
    r = next(
        x for x in results
        if x.status is ResultStatus.NUMERICALLY_SOLVED
        and x.query_kind is QueryKind.EFFECT
        and x.derivation
    )
    payload = derivation_to_dict(r.derivation)
    # Find the formula_evaluation step and bump its output.
    for step in payload["steps"]:
        if step["rule"] == "formula_evaluation":
            step["output"] = step["output"] + 1.0
            break
    bad = derivation_from_dict(payload)
    ctx = VerificationContext(
        graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
    )
    with pytest.raises(VerificationError):
        verify_numeric(bad, ctx, r.numeric_result)


def test_tampering_json_graph_edge_causes_verifier_reject():
    """Remove an edge from the serialized graph in an identify step,
    deserialize, and watch the verifier reject (graph in derivation
    won't match context graph)."""
    path = FIXTURE_DIR / "identify_backdoor.json"
    graph, _theta, results, stmt_by_id = _run(path)
    r = next(
        x for x in results
        if x.query_kind is QueryKind.IDENTIFY
        and x.structural_result is not None
        and x.structural_result.value is True
        and x.derivation
    )
    payload = derivation_to_dict(r.derivation)
    # Drop an edge from the first step's embedded graph.
    graph_payload = payload["steps"][0]["inputs"]["graph"]
    assert graph_payload["edges"], "expected at least one edge to tamper"
    graph_payload["edges"].pop()
    bad = derivation_from_dict(payload)
    ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
    with pytest.raises(VerificationError):
        verify_identify(bad, ctx, r.structural_result)


# =================================================================== errors

def test_unknown_kind_is_rejected_on_decode():
    payload = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "graph_is_dag",
                "inputs": {"graph": {"kind": "not_a_thing"}},
                "output": True,
                "step_id": "s1",
            }
        ],
    }
    with pytest.raises(DerivationSerializationError, match="unknown value kind"):
        derivation_from_dict(payload)


def test_wrong_top_level_kind_is_rejected():
    with pytest.raises(DerivationSerializationError, match="kind"):
        derivation_from_dict(
            {"version": "0.1", "kind": "something_else", "steps": []}
        )


def test_wrong_version_is_rejected():
    with pytest.raises(DerivationSerializationError, match="version"):
        derivation_from_dict(
            {"version": "9.9", "kind": "derivation", "steps": []}
        )


def test_missing_output_is_rejected():
    payload = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {"rule": "graph_is_dag", "inputs": {}, "step_id": "s1"}
        ],
    }
    with pytest.raises(DerivationSerializationError, match="output"):
        derivation_from_dict(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "version": "0.1",
                "kind": "derivation",
                "steps": [
                    {
                        "rule": "x",
                        "inputs": {},
                        "output": {"kind": "sum"},
                        }
                    ],
                },
                "sum.bind",
            ),
        (
            {
                "version": "0.1",
                "kind": "derivation",
                "steps": [
                    {
                        "rule": "x",
                        "inputs": {},
                        "output": {"kind": "numeric_result", "interval": {}},
                    }
                ],
            },
            "numeric_result.interval",
        ),
        (
            {
                "version": "0.1",
                "kind": "derivation",
                "steps": [
                    {
                        "rule": "x",
                        "inputs": {},
                        "output": {
                            "kind": "structural_result",
                            "value": True,
                            "supporting_paths": ["abc"],
                        },
                    }
                ],
            },
            "supporting_paths",
        ),
    ],
)
def test_malformed_tagged_payloads_raise_derivation_serialization_error(payload, message):
    with pytest.raises(DerivationSerializationError, match=message):
        derivation_from_dict(payload)


def _one_step_derivation(*, output=True, inputs=None) -> dict:
    """A well-formed derivation with one slot left open to poke."""
    return {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "graph_is_dag",
                "inputs": {} if inputs is None else inputs,
                "output": output,
                "step_id": "s1",
            }
        ],
    }


@pytest.mark.parametrize("position", ["output", "inputs"])
def test_a_non_string_value_kind_is_a_shape_error_whatever_its_type(position):
    """A malformed tag has to fail as malformed input, not as a crash
    inside the decoder.

    ``_value_from_json`` dispatches on ``payload["kind"]`` through a dict
    lookup, and JSON is free to put anything in that slot. For the two
    container types the lookup itself raised ``TypeError: unhashable
    type`` — CPython internals escaping the one function whose whole job
    is to turn bad payloads into this module's single error type, and
    walking straight past every caller that catches it.

    The five tags are checked together and against their exact messages,
    because the property at stake is that they all get *the same
    answer*: whether a bad tag happens to be hashable is a fact about
    CPython, not about the payload, and must not be something a caller
    can tell apart. Both positions are asked because the guard belongs
    to the shared decoder, not to one call site.
    """

    def decode(tag):
        tagged = {"kind": tag}
        payload = (
            _one_step_derivation(output=tagged)
            if position == "output"
            else _one_step_derivation(inputs={"graph": tagged})
        )
        with pytest.raises(DerivationSerializationError) as excinfo:
            derivation_from_dict(payload)
        return str(excinfo.value)

    assert {repr(tag): decode(tag) for tag in ([], {}, None, 3, True)} == {
        "[]": "unknown value kind: []",
        "{}": "unknown value kind: {}",
        "None": "unknown value kind: None",
        "3": "unknown value kind: 3",
        "True": "unknown value kind: True",
    }
