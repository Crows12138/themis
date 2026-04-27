"""S.12.4 wiring e2e — dispatch attaches BoundsResult to effect-query
results that needed_investigation."""
from __future__ import annotations

import themis


def _program(intervention_pred="x", target_pred="y", with_iv=False):
    """Simple bool effect program where backdoor identification fails
    (no observed confounder for X-Y; bidirected to force unidentifiable)."""
    statements = [
        {"kind": "variable", "predicate": target_pred, "domain": [True, False]},
        {"kind": "variable", "predicate": intervention_pred, "domain": [True, False]},
        {
            "kind": "cause",
            "from": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": target_pred,
                   "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        },
        {
            "kind": "bidirected",
            "left": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "right": {"predicate": target_pred,
                      "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        },
    ]
    if with_iv:
        statements.insert(2, {
            "kind": "variable", "predicate": "z", "domain": [True, False],
        })
        statements.append({
            "kind": "cause",
            "from": {"predicate": "z",
                     "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": intervention_pred,
                   "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {
                "atom": {"predicate": intervention_pred,
                         "args": [{"type": "const", "name": "me"}]},
                "value": True,
            },
            "target": {
                "atom": {"predicate": target_pred,
                         "args": [{"type": "const", "name": "me"}]},
                "value": True,
            },
            "given": [],
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


def test_unidentifiable_binary_effect_attaches_manski_bounds():
    """No backdoor + no IV → Manski natural bounds attached."""
    envelope = themis.run(_program())
    result = envelope["results"][0]
    assert result["status"] == "needs_investigation"
    assert result.get("bounds_result") is not None
    bounds = result["bounds_result"]
    assert bounds["method"] in ("manski_natural", "balke_pearl_iv")
    assert bounds["lower_expression"]
    assert bounds["upper_expression"]


def test_manski_bounds_use_actual_predicate_names():
    envelope = themis.run(_program(intervention_pred="aspirin",
                                    target_pred="heart_attack"))
    bounds = envelope["results"][0]["bounds_result"]
    assert "aspirin" in bounds["lower_expression"]
    assert "heart_attack" in bounds["lower_expression"]


def test_solved_query_has_no_bounds():
    """When point identification succeeds, bounds_result is null."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            # No bidirected — backdoor adjustment with empty W is identifiable
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    # Either solved or needs_investigation depending on Theta — but if
    # solved, no bounds_result should be attached
    if result["status"] != "needs_investigation":
        assert result.get("bounds_result") is None


def test_non_effect_query_no_bounds():
    """Cause / assoc queries don't get bounds (out of scope)."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "x",
                             "args": [{"type": "const", "name": "me"}]},
                    "to": {"predicate": "y",
                           "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    assert result.get("bounds_result") is None
