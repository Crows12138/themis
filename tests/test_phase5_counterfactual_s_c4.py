"""Counterfactual gating: what a missing declaration actually costs.

Monotonicity used to be a precondition — no declaration, no answer. It is
now one more constraint the solver can use, so an undeclared monotonicity
costs precision, never the answer. What a counterfactual cell genuinely
cannot do without is the data: the observational joint and, for the cells
consistency and monotonicity leave open, P(Y=1 | do(x')).
"""
from __future__ import annotations

from themis.input.syntactic_validator import validate_result
from themis.kernel import run


def _counterfactual_ast(*, monotonicity: str | None) -> dict:
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
                "predicate": "higher_income",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": True,
        },
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}

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
                    "predicate": "higher_income",
                    "args": [{"type": "const", "name": "me"}],
                },
            },
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_income", "domain": [True, False]},
            {"kind": "query", "id": "q_cf", "query": query},
        ],
    }


def test_counterfactual_without_monotonicity_asks_for_data_not_the_assumption():
    """An undeclared monotonicity is no longer what blocks the answer."""
    out = run(_counterfactual_ast(monotonicity=None))

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "needs_investigation"
    assert result["missing_information"]
    names = {item["name"] for item in result["missing_information"]}
    assert "assumptions.monotonicity" not in names
    assert all(item["kind"] == "parameter" for item in result["missing_information"])
    assert {
        note["predicate"] for note in result["framing_notes"]
    } == {"chose_cs_major", "higher_income"}


def test_declaring_monotonicity_does_not_change_which_data_is_missing():
    """Both roads lead to the same data request — the assumption is not a
    substitute for the distribution."""
    without = run(_counterfactual_ast(monotonicity=None))["results"][0]
    with_mono = run(_counterfactual_ast(monotonicity="non_decreasing"))["results"][0]

    assert {i["name"] for i in without["missing_information"]} == {
        i["name"] for i in with_mono["missing_information"]
    }


def test_counterfactual_with_monotonicity_needs_theta_until_sc5_fixture_supplies_it():
    out = run(_counterfactual_ast(monotonicity="non_decreasing"))

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "needs_investigation"
    assert result["missing_information"]
    assert result["investigation_requests"]
