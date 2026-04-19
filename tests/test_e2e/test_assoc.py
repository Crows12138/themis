"""End-to-end test for slice 2: assoc (d-separation) vertical.

Runs assoc queries over the three canonical d-separation structures —
chain, fork, collider — with and without conditioning.

Expected truth table:

    id                  structure              given          open?
    ------------------  ---------------------  -------------  -----
    chain_open          smokes -> tar -> canc  {}             True
    chain_blocked       smokes -> tar -> canc  {tar}          False
    fork_open           ic <- hot -> drown     {}             True
    fork_blocked        ic <- hot -> drown     {hot_weather}  False
    collider_closed     flu -> fever <- covid  {}             False
    collider_opened     flu -> fever <- covid  {fever}        True
"""
from __future__ import annotations

from pathlib import Path

import pytest

from causal_kernel.input.parser import parse_json
from causal_kernel.input.semantic_validator import validate_program
from causal_kernel.input.syntactic_validator import validate_ast, validate_result
from causal_kernel.output.explainer import explain
from causal_kernel.output.result_orchestrator import to_dict
from causal_kernel.runtime.graph_projection import project
from causal_kernel.runtime.instantiation import instantiate
from causal_kernel.runtime.scheduler import dispatch_all
from causal_kernel.types import QueryKind, ResultStatus

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "assoc_canonical.json"


@pytest.fixture(scope="module")
def results_by_id() -> dict:
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    return {r.query_id: r for r in dispatch_all(program, graph)}


@pytest.mark.parametrize(
    "qid,expected,min_paths",
    [
        ("chain_open",       True,  1),
        ("chain_blocked",    False, 0),
        ("fork_open",        True,  1),
        ("fork_blocked",     False, 0),
        ("collider_closed",  False, 0),
        ("collider_opened",  True,  1),
    ],
)
def test_assoc_truth_table(results_by_id, qid, expected, min_paths):
    r = results_by_id[qid]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.ASSOC
    assert r.structural_result is not None
    assert r.structural_result.value is expected, f"{qid}: expected {expected}"
    assert len(r.structural_result.supporting_paths) >= min_paths


def test_chain_open_path_contents(results_by_id):
    r = results_by_id["chain_open"]
    assert r.structural_result.supporting_paths == (
        ("smokes(alice)", "tar(alice)", "cancer(alice)"),
    )


def test_fork_open_path_contents(results_by_id):
    r = results_by_id["fork_open"]
    assert r.structural_result.supporting_paths == (
        ("ice_cream(alice)", "hot_weather(alice)", "drowning(alice)"),
    )


def test_collider_opened_path_contents(results_by_id):
    r = results_by_id["collider_opened"]
    assert r.structural_result.supporting_paths == (
        ("flu(alice)", "fever(alice)", "covid(alice)"),
    )


def test_assoc_results_round_trip_through_schema(results_by_id):
    # Every assoc result must validate against query_result.schema.json.
    for qid, r in results_by_id.items():
        payload = to_dict(r)
        validate_result(payload)
        assert payload["query_kind"] == "assoc", qid


def test_assoc_explanations_reflect_outcome(results_by_id):
    opened = explain(results_by_id["collider_opened"])
    assert "开放路径" in opened
    assert "flu(alice)" in opened

    blocked = explain(results_by_id["collider_closed"])
    assert "d-分离" in blocked

    chain_blocked = explain(results_by_id["chain_blocked"])
    assert "d-分离" in chain_blocked
