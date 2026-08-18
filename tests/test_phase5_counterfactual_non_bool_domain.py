"""Phase 5 §C: non-boolean domain counterfactual degrades to outside_language
instead of crashing the kernel.

Regression for the bug where `_observational_joint_xy` was called
outside the try/except that catches `CounterfactualBoundsError`, so a
categorical-domain program propagated a raw exception out of
`themis.run`.
"""
from __future__ import annotations

from themis.input.syntactic_validator import validate_result
from themis.kernel import run


def _categorical_counterfactual_ast() -> dict:
    major_atom = {"predicate": "major", "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "major", "domain": ["cs", "history"]},
            {"kind": "variable", "predicate": "higher_income", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "major", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "higher_income", "args": [{"type": "const", "name": "me"}]},
            },
            {
                "kind": "probability",
                "target": {"atom": major_atom, "value": "cs"},
                "given": [],
                "value": 0.3,
            },
            {
                "kind": "probability",
                "target": {"atom": major_atom, "value": "history"},
                "given": [],
                "value": 0.7,
            },
            {
                "kind": "query",
                "id": "q_cf",
                "query": {
                    "kind": "counterfactual",
                    "observed": {
                        "atom": {"predicate": "major", "args": [{"type": "const", "name": "me"}]},
                        "value": "history",
                    },
                    "counterfactual_intervention": {
                        "atom": {"predicate": "major", "args": [{"type": "const", "name": "me"}]},
                        "value": "cs",
                    },
                    "counterfactual_target": {
                        "atom": {"predicate": "higher_income", "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "assumptions": {"monotonicity": "non_decreasing"},
                },
            },
        ],
    }


def test_categorical_counterfactual_returns_outside_language_not_crash():
    out = run(_categorical_counterfactual_ast())

    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "outside_language"
    # The reason travels in the field the schema declares for it, bearing
    # the species its exception declares — the same one the data end
    # raises for the same failure. It used to be prose in an extensions
    # block that no surface read.
    failure = result["estimator_failure"]
    assert failure["failure_type"] == "counterfactual_cell_out_of_scope"
    assert failure["kind"] == "unbuilt"
    assert "boolean domain" in failure["reason"]
