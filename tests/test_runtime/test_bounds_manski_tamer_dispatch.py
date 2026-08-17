"""Phase 12.MT — scheduler dispatch picks MTR over Manski natural when
program.extensions['monotonicity'] declares the relevant pair.
"""
from __future__ import annotations

import themis


def _base_program() -> dict:
    """Effect query whose point identification fails (latent confounder
    u between x and y, no admissible backdoor adjustment) — bounds
    layer fires.
    """
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "u", "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "x", "args": [{"type": "var", "name": "X"}]},
            },
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "u", "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "y", "args": [{"type": "var", "name": "X"}]},
            },
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "x", "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "y", "args": [{"type": "var", "name": "X"}]},
            },
            {
                "kind": "query",
                "id": "mtr_test_query",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {
                            "predicate": "y",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                    "intervention": {
                        "atom": {
                            "predicate": "x",
                            "args": [{"type": "const", "name": "me"}],
                        },
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }


def _result_of(program: dict) -> dict:
    out = themis.run(program)
    return out["results"][0]


def test_no_monotonicity_declaration_falls_back_to_manski_natural():
    """Baseline: without an MTR declaration, we get the assumption-free
    Manski natural bound."""
    res = _result_of(_base_program())
    bounds = res.get("bounds_result")
    assert bounds is not None, "bounds layer should fire on unidentifiable effect"
    assert bounds["method"] == "manski_natural"
    # Manski natural carries no assumptions (the field is optional in
    # the serialized envelope when empty).
    assert not bounds.get("assumptions")


def test_monotonicity_non_decreasing_picks_manski_tamer():
    """When the program asserts y is non-decreasing in x for the same
    target+treatment pair as the query, dispatch picks MTR."""
    program = _base_program()
    program["extensions"] = {
        "monotonicity": {
            "target": "y",
            "treatment": "x",
            "direction": "non_decreasing",
        }
    }
    bounds = _result_of(program)["bounds_result"]
    assert bounds["method"] == "manski_tamer_monotonicity"
    assert "mtr_non_decreasing" in bounds["assumptions"]


def test_monotonicity_non_increasing_picks_manski_tamer():
    program = _base_program()
    program["extensions"] = {
        "monotonicity": {
            "target": "y",
            "treatment": "x",
            "direction": "non_increasing",
        }
    }
    bounds = _result_of(program)["bounds_result"]
    assert bounds["method"] == "manski_tamer_monotonicity"
    assert "mtr_non_increasing" in bounds["assumptions"]


def test_monotonicity_for_other_pair_does_not_apply():
    """MTR declaration for an unrelated (target, treatment) pair must
    NOT hijack a query about a different pair — falls back to Manski
    natural."""
    program = _base_program()
    program["extensions"] = {
        "monotonicity": {
            "target": "y",
            "treatment": "u",  # not the queried treatment (x is queried)
            "direction": "non_decreasing",
        }
    }
    bounds = _result_of(program)["bounds_result"]
    assert bounds["method"] == "manski_natural"


def test_monotonicity_list_form_supports_multiple_pairs():
    """extensions.monotonicity may carry a list of declarations; the
    one matching the queried pair is used."""
    program = _base_program()
    program["extensions"] = {
        "monotonicity": [
            {"target": "u", "treatment": "x", "direction": "non_decreasing"},
            {"target": "y", "treatment": "x", "direction": "non_decreasing"},
        ]
    }
    bounds = _result_of(program)["bounds_result"]
    assert bounds["method"] == "manski_tamer_monotonicity"


def test_monotonicity_invalid_direction_falls_back():
    """A garbled direction string is ignored — we don't crash, we just
    fall back to the assumption-free Manski natural."""
    program = _base_program()
    program["extensions"] = {
        "monotonicity": {
            "target": "y",
            "treatment": "x",
            "direction": "monotone-ish",  # not in the enum
        }
    }
    bounds = _result_of(program)["bounds_result"]
    assert bounds["method"] == "manski_natural"


def test_mtr_lower_tightens_to_marginal_in_envelope():
    """End-to-end shape check: the lower expression in the dispatched
    bounds matches the MTR-tightened marginal P(y=true)."""
    program = _base_program()
    program["extensions"] = {
        "monotonicity": {
            "target": "y",
            "treatment": "x",
            "direction": "non_decreasing",
        }
    }
    bounds = _result_of(program)["bounds_result"]
    # Querying do(x=true) under Y(1)>=Y(0): lower tightens.
    assert bounds["lower_expression"] == "P(y=true)"
    assert "P(x=false)" in bounds["upper_expression"]
