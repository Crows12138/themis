"""Phase 5 §C / S.C.4: monotonicity gate + needs_assumption channel."""
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


def test_counterfactual_without_monotonicity_returns_needs_assumption():
    out = run(_counterfactual_ast(monotonicity=None))

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "needs_assumption"
    assert result["missing_information"] == [
        {
            "kind": "assumption",
            "name": "assumptions.monotonicity",
            "priority": "high",
            "reason": "首版反事实 bounds 只支持显式 monotonicity 假设",
        }
    ]
    assert result["investigation_requests"] == [
        {
            "action": "define_assumption",
            "target": "assumptions.monotonicity",
            "priority": "high",
            "note": "首版反事实 bounds 只支持显式 monotonicity 假设",
            "group": "assumption",
            "items": [
                {
                    "target": "assumptions.monotonicity",
                    "reason": "首版反事实 bounds 只支持显式 monotonicity 假设",
                }
            ],
        }
    ]
    assert {
        note["predicate"] for note in result["framing_notes"]
    } == {"chose_cs_major", "higher_income"}


def test_counterfactual_with_monotonicity_needs_theta_until_sc5_fixture_supplies_it():
    out = run(_counterfactual_ast(monotonicity="non_decreasing"))

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "needs_investigation"
    assert result["missing_information"]
    assert result["investigation_requests"]
