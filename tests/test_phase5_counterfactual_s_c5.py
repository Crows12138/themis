"""Phase 5 §C / S.C.5: counterfactual runtime e2e."""
from __future__ import annotations

import pytest

from themis.input.syntactic_validator import validate_result
from themis.kernel import run


def _program_ast(*, factual_target_known: bool | None = None) -> dict:
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


def _program_ast_with_boolean_complements_omitted() -> dict:
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
                        "predicate": "higher_current_income",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                },
                "given": [{"atom": {
                    "predicate": "chose_cs_major",
                    "args": [{"type": "const", "name": "me"}],
                }, "value": False}],
                "value": 0.3,
            },
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


def _program_ast_with_ancestral_marginalization() -> dict:
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
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "cause",
                "from": {
                    "predicate": "baseline_aptitude",
                    "args": [{"type": "const", "name": "me"}],
                },
                "to": {
                    "predicate": "chose_cs_major",
                    "args": [{"type": "const", "name": "me"}],
                },
            },
            {
                "kind": "cause",
                "from": {
                    "predicate": "baseline_aptitude",
                    "args": [{"type": "const", "name": "me"}],
                },
                "to": {
                    "predicate": "higher_current_income",
                    "args": [{"type": "const", "name": "me"}],
                },
            },
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
            {"kind": "variable", "predicate": "baseline_aptitude", "domain": [True, False]},
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_current_income", "domain": [True, False]},
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [],
                "value": 0.3,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                },
                "given": [],
                "value": 0.7,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "chose_cs_major",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [{
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                }],
                "value": 0.8,
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
                "given": [{
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                }],
                "value": 0.2,
            },
            {
                "kind": "probability",
                "target": {
                    "atom": {
                        "predicate": "chose_cs_major",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": False,
                },
                "given": [{
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                }],
                "value": 0.4,
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
                "given": [{
                    "atom": {
                        "predicate": "baseline_aptitude",
                        "args": [{"type": "const", "name": "me"}],
                    },
                    "value": True,
                }],
                "value": 0.6,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    },
                ],
                "value": 0.8,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    },
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
                    "value": False,
                },
                "given": [
                    {
                        "atom": {
                            "predicate": "chose_cs_major",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    },
                ],
                "value": 0.5,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": False,
                    },
                ],
                "value": 0.5,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                ],
                "value": 0.4,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                ],
                "value": 0.6,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                ],
                "value": 0.1,
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
                    },
                    {
                        "atom": {
                            "predicate": "baseline_aptitude",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                ],
                "value": 0.9,
            },
            {"kind": "query", "id": "q_cf", "query": query},
        ],
    }


def test_counterfactual_without_a_factual_outcome_is_point_identified():
    """P(Y_{x=1}=1 | X=0) is exact once the interventional risk is known.

    The joint is P(0,0)=.42 P(0,1)=.18 P(1,0)=.08 P(1,1)=.32 and X -> Y is
    unconfounded, so the effect identification returns P(y|do(x=1)) = 0.8
    and the ETT identity gives (0.8 - 0.32) / 0.6. The old path, which
    never asked for an interventional risk, could only bound this at
    [0.3, 1.0].
    """
    out = run(_program_ast())

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "counterfactual_solved"
    assert result["numeric_result"]["value"] == pytest.approx(0.8)


def test_counterfactual_collapses_to_point_when_factual_target_is_known():
    out = run(_program_ast(factual_target_known=True))

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "counterfactual_solved"
    assert result["numeric_result"] == {"value": 1.0}


def test_counterfactual_recovers_missing_boolean_complements():
    out = run(_program_ast_with_boolean_complements_omitted())

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "counterfactual_solved"
    assert result["numeric_result"]["value"] == pytest.approx(0.8)


def test_counterfactual_recovers_joint_by_ancestral_marginalization():
    """Z -> X, Z -> Y, X -> Y: the joint comes from marginalizing over Z and
    the interventional risk from the back-door adjustment on Z,
    0.3*0.5 + 0.7*0.9 = 0.78, giving (0.78 - 0.408) / 0.52."""
    out = run(_program_ast_with_ancestral_marginalization())

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "counterfactual_solved"
    assert result["numeric_result"]["value"] == pytest.approx(0.372 / 0.52)
