"""A time-varying strategy names its variables as columns, and a column is one node.

``options.longitudinal`` lists the treatments, the covariates measured
before each and the outcome by name, and each name is a column of the wide
table the estimators read. On a program unrolled in time a variable has a
node per step. The structural route read each name off the graph by
predicate and kept whichever node of it the graph listed last. Measured:
writing the same statements in another order moved the declared treatment
from A@t to A@t-1 and changed nothing else about the answer; the block named
that node, and the verifier, reading the block's own labels and comparing
only predicates, took either.

Which step a name meant is written nowhere, so the answer says that, beside
the gap it already gives for a name the graph does not have at all.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.kernel import _refusal_facts as _facts
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_longitudinal_identification

_SUBJECT = [{"type": "const", "name": "subj"}]


def _atom(predicate, time=None):
    atom = {"predicate": predicate, "args": _SUBJECT}
    if time is not None:
        atom["time_index"] = {"kind": "relative", "value": time}
    return atom


def _program(edges, declared, ask):
    predicates = sorted({atom["predicate"] for pair in edges for atom in pair})
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in predicates]
    statements += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": ask[0], "value": True},
        "target": {"atom": ask[1], "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "subj"}]},
            "options": {"longitudinal": dict(
                declared, strategy_treated=1, strategy_control=0)},
            "statements": statements}


_NOW = (_atom("A", 0), _atom("Y", 0))

#: Two steps of one strategy, unrolled: L and A at t-1 and at t, Y at t.
_UNROLLED = [
    (_atom("L", -1), _atom("A", -1)), (_atom("L", -1), _atom("Y", 0)),
    (_atom("A", -1), _atom("L", 0)), (_atom("A", -1), _atom("Y", 0)),
    (_atom("L", 0), _atom("A", 0)), (_atom("L", 0), _atom("Y", 0)),
    (_atom("A", 0), _atom("Y", 0)),
]
#: The same, with a cause of the earlier treatment the history never names.
_CONFOUNDED = _UNROLLED + [(_atom("C", -1), _atom("A", -1)),
                           (_atom("C", -1), _atom("Y", 0))]
_ONCE = {"treatments": ["A"], "confounders_by_time": [["L"]], "outcome": "Y"}
_TWICE = {"treatments": ["A", "A"], "confounders_by_time": [["L"], ["L"]],
          "outcome": "Y"}


def _touching_the_current_treatment_first(edges):
    now = _atom("A", 0)
    return ([e for e in edges if now in e]
            + [e for e in edges if now not in e])


UNROLLED = {
    "names_each_variable_once": _program(_UNROLLED, _ONCE, _NOW),
    "names_each_variable_once_per_step": _program(_UNROLLED, _TWICE, _NOW),
    "an_earlier_treatment_is_confounded": _program(_CONFOUNDED, _ONCE, _NOW),
    "the_same_written_in_another_order": _program(
        _touching_the_current_treatment_first(_CONFOUNDED), _ONCE, _NOW),
}

#: Time indices on every atom, and still one node per declared name.
ONE_NODE_EACH = _program(
    [(_atom("L", -1), _atom("A", 0)), (_atom("L", -1), _atom("Y", 0)),
     (_atom("A", 0), _atom("Y", 0))], _ONCE, _NOW)


def _run(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _asks(result):
    return sorted(row["name"] for row in result.get("missing_information") or ())


# ================================================================ honest first


@pytest.mark.parametrize("name", sorted(UNROLLED))
def test_a_name_the_graph_holds_at_several_steps_is_asked_about(name):
    program = UNROLLED[name]
    result = _run(program)
    assert result["status"] == "needs_investigation"
    assert "longitudinal_identification" not in (result.get("extensions") or {})
    assert _asks(result) == ["longitudinal:name_holds_several_nodes:A",
                             "longitudinal:name_holds_several_nodes:L"]
    themis.verify_answer_claims(program, result)
    themis.verify_refusal(program, result)


def test_the_order_the_statements_are_written_in_does_not_move_the_answer():
    first = _run(UNROLLED["an_earlier_treatment_is_confounded"])
    second = _run(UNROLLED["the_same_written_in_another_order"])
    assert first["status"] == second["status"]
    assert first["missing_information"] == second["missing_information"]


def test_the_ask_names_every_node_the_name_could_be():
    result = _run(UNROLLED["names_each_variable_once"])
    row = next(r for r in result["missing_information"]
               if r["name"].endswith(":A"))
    assert set(row["said"]["atoms"].split(", ")) == {"A(subj)@t-1", "A(subj)@t"}


def test_time_indices_alone_are_not_what_is_asked_about():
    """Every atom carries a step, and every declared name is still one
    node: the route reads it exactly as before."""
    result = _run(ONE_NODE_EACH)
    assert result["status"] == "structurally_solved"
    block = result["extensions"]["longitudinal_identification"]
    assert block["treatments"] == ["A(subj)@t"]
    assert block["confounders_by_time"] == [["L(subj)@t-1"]]
    themis.verify(ONE_NODE_EACH, result)


# ============================================================== the forgery


#: What the route wrote before, on the first of the unrolled programs.
_A_STEP_NOBODY_CHOSE = {
    "estimand": "time_varying_strategy_contrast",
    "treatments": ["A(subj)@t"], "outcome": "Y(subj)@t",
    "confounders_by_time": [["L(subj)@t-1"]], "identified": False,
    "assumptions": [
        "sequential_exchangeability_no_unmeasured_time_varying_confounding",
        "positivity_each_treatment_level_observed_within_history_strata",
        "consistency_well_defined_sustained_treatment_strategy"],
}


def test_a_block_naming_one_of_several_nodes_is_not_about_the_declaration():
    program = UNROLLED["names_each_variable_once"]
    facts = _facts(program, "q")
    with pytest.raises(VerificationError, match="written nowhere"):
        verify_longitudinal_identification(
            copy.deepcopy(_A_STEP_NOBODY_CHOSE),
            program["options"]["longitudinal"], facts.graph, facts.bidirected)


def test_the_door_refuses_that_block_on_the_honest_answer():
    program = UNROLLED["names_each_variable_once"]
    forged = copy.deepcopy(_run(program))
    forged.setdefault("extensions", {})["longitudinal_identification"] = (
        copy.deepcopy(_A_STEP_NOBODY_CHOSE))
    with pytest.raises(VerificationError, match="written nowhere"):
        themis.verify_answer_claims(program, forged)
