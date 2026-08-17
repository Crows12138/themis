"""Features added separately, exercised together.

Each feature here arrived with tests of its own, in isolation. Passing
in isolation says nothing about two of them meeting in one program, and
the failure that shape produces is not a wrong number in one layer but
an output where one feature's field is missing because another feature's
branch ran instead.

So each test drives 2-5 features through the full pipeline at once and
asserts the cross-feature invariants: that every expected block is
present, and that no feature's presence silently withdraws another's.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# Composition 1: monotonicity first-class + MTR bounds
# + bounds verifier + verify_bounds_result public entry
# ---------------------------------------------------------------------------


def test_the_assumptions_field_reaches_bounds_and_its_verifier():
    """A program with EffectQuery.assumptions.monotonicity
    must trigger MTR bounds via producer AND audit cleanly
    via verifier path."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "compositional_mtr",
             "query": {
                 "kind": "effect",
                 "target": {"atom": {"predicate": "y",
                                     "args": [{"type": "const",
                                               "name": "me"}]},
                            "value": True},
                 "intervention": {"atom": {"predicate": "x",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                 "given": [],
                 # The first-class assumptions field, in a real program
                 # with the MTR producer and its verifier downstream.
                 "assumptions": {"monotonicity": "non_decreasing"},
             }},
        ],
    }
    out = themis.run(program)
    result = out["results"][0]

    # the MTR producer fired
    bounds = result.get("bounds_result")
    assert bounds is not None
    assert bounds["method"] == "manski_tamer_monotonicity"
    assert "mtr_non_decreasing" in bounds["assumptions"]

    # the public bounds-audit entry accepts it
    themis.verify_bounds_result(program, result)

    # Tampering caught by audit
    result["bounds_result"]["lower_expression"] = "P(y=false)"
    with pytest.raises(VerificationError):
        themis.verify_bounds_result(program, result)


# ---------------------------------------------------------------------------
# Composition 2: transport identification (Phase 9 §T9.1) + transport numeric
# + post-stratification fields end-to-end
# ---------------------------------------------------------------------------


def test_transport_identification_composes_with_its_numeric_end():
    """Program with selection_node (S→Z, Phase 9 §T9.1) +
    target_marginal extension → both structural
    identification AND numeric_estimate.transport_post_stratification
    attach."""
    rng = np.random.default_rng(0)
    n = 1500
    z = (rng.random(n) < 0.5)
    x = (rng.random(n) < 0.5)
    y = 0.5 * x.astype(float) + 0.3 * z.astype(float) + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame({"x": x, "z": z, "y": y})

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "target_marginal": {
                "predicate": "z",
                "marginal": {True: 0.7, False: 0.3},
            },
        },
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "selection_node", "id": "s_z",
             "source_population": "trial",
             "target_population": "real_world",
             "affects": {"predicate": "z",
                         "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "compositional_transport",
             "query": {"kind": "effect",
                       "target_population": "real_world",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }
    out = themis.estimate(program, df)
    result = out["results"][0]

    # Phase 9 §T9.1 — transport_identification extension present
    transport_block = (result.get("extensions") or {}).get(
        "transport_identification"
    )
    assert transport_block is not None
    assert transport_block["target_population"] == "real_world"
    assert len(transport_block["adjustment_set"]) == 1

    # transport_post_stratification numeric_estimate attached
    estimate = result.get("numeric_estimate")
    assert estimate is not None
    assert estimate["method"] == "transport_post_stratification"
    assert "s_admissibility_of_adjustment_set" in estimate["assumptions"]


# ---------------------------------------------------------------------------
# Composition 3: collider gap + unmeasured_confounder_risk
# fire concurrently on a single query
# ---------------------------------------------------------------------------


def test_collider_conditioning_composes_with_unmeasured_confounding():
    """Program with both: (a) `given` containing a collider on the
    X-Y backdoor path → collider_conditioning_opens_backdoor fires;
    (b) the DAG declares no bidirected edges →
    unmeasured_confounder_risk fires. Both must attach to the same
    data_gap_report."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            # Confounder pattern — fires unmeasured_confounder_risk
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            # X → W ← Y collider — fires when `given` includes W
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "y",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "two_gaps",
             "query": {
                 "kind": "effect",
                 "target": {"atom": {"predicate": "y",
                                     "args": [{"type": "const",
                                               "name": "me"}]},
                            "value": True},
                 "intervention": {"atom": {"predicate": "x",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                 "given": [
                     {"atom": {"predicate": "w",
                               "args": [{"type": "const", "name": "me"}]},
                      "value": True},
                 ],
             }},
        ],
    }
    out = themis.run(program)
    result = out["results"][0]

    kinds = {g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", [])}
    assert "collider_conditioning_opens_backdoor" in kinds
    # unmeasured_confounder_risk is conditional on query_kind == EFFECT
    # and the program-shape signal (Z→X & Z→Y, no bidirected). Both
    # apply here.
    assert "unmeasured_confounder_risk" in kinds


# ---------------------------------------------------------------------------
# Composition 4: chain CDE on a 2-mediator program
# ---------------------------------------------------------------------------


def test_chain_cde_composes_with_the_audit_fields():
    """Chain CDE on a 2-mediator dataset. Verify estimate carries
    chain-specific audit fields (mediators tuple, mediator_values
    tuple, chain-specific assumption tag)."""
    from themis.estimation import estimate_cde_chain

    rng = np.random.default_rng(0)
    n = 2000
    x = (rng.random(n) < 0.5)
    m1 = (rng.random(n) < 0.5)
    m2 = (rng.random(n) < 0.5)
    y = (
        2.0 * x.astype(float)
        + 1.5 * m1.astype(float)
        + 1.0 * m2.astype(float)
        + rng.normal(size=n)
    )
    df = pd.DataFrame({"x": x, "m1": m1, "m2": m2, "y": y})

    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"),
        mediator_values=(True, True),
        ci_bootstrap=100,
    )
    # Direct effect of X (no X·M_i interaction in DGP) ≈ 2.0
    assert est.point == pytest.approx(2.0, abs=0.2)
    assert est.method == "cde_chain_linear"
    assert est.mediators == ("m1", "m2")
    assert est.mediator_values == (True, True)
    # Chain-specific assumption recorded
    assert any(
        "between_successive_mediators" in a for a in est.assumptions
    )
    # Bootstrap CI brackets point
    assert est.ci_lower < est.point < est.ci_upper


# ---------------------------------------------------------------------------
# Composition 5: weak IV + IV identification + IV numeric
# (Phase 6.iv + 7.3) on a single program
# ---------------------------------------------------------------------------


def test_weak_iv_composes_with_iv_identification_and_the_numeric_end():
    """Program with valid IV (z → x → y, latent u between x,y) +
    weak instrument data → IV identification PASS + IV numeric
    estimate ATTACH + the weak_iv_instrument gap FIRES."""
    rng = np.random.default_rng(0)
    n = 500
    # Weak instrument: z explains tiny share of x variance
    z = rng.normal(size=n)
    u = rng.normal(size=n)  # latent confounder
    x = 0.03 * z + u + rng.normal(size=n)
    # Outcome with ATE = 1.5
    y = 1.5 * x + u + rng.normal(size=n)
    df = pd.DataFrame({"x": x, "z": z, "y": y})

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "bidirected", "forall": ["I"],
             "left": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "weak_iv_compose",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": 1},  # value field placeholder
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": 1},
                       "given": []}},
        ],
    }
    out = themis.estimate(program, df)
    result = out["results"][0]

    # IV numeric estimate attached
    estimate = result.get("numeric_estimate")
    assert estimate is not None
    assert estimate["method"].startswith("iv_")
    # first_stage_f_stat carried on the estimate
    assert "first_stage_f_stat" in estimate
    assert estimate["first_stage_f_stat"] < 10.0  # weak

    # weak_iv_instrument gap fires
    kinds = {g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", [])}
    assert "weak_iv_instrument" in kinds

    # ⚠ line mirrored to explanation
    assert "first-stage f" in (result.get("explanation") or "").lower()
