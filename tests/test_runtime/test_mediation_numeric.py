"""v0.1.4 Fix 1 — end-to-end mediation numeric evaluation tests.

Drives full ``themis.run`` on mediation programs and verifies the
kernel computes TE / NDE / NIE / CDE numerically rather than emitting
structural-only identification.

The flagship case is CLadder Q1358 (medication → blood pressure →
heart condition), where the LLM-Themis arm previously stayed at
STRUCTURALLY_SOLVED and the agent had to plug numbers into the formula
by hand — which is exactly where Themis lost to vanilla LLMs on
CLadder Phase 1b.

Identity checks (Pearl 2001 decomposition) and ``themis.verify``
round-trips guard the kernel against drift between the runtime
evaluator and the verifier's paired implementation.
"""
from __future__ import annotations

import themis


def _q1358_program() -> dict:
    """CLadder Q1358 setup. X=medication, M=blood_pressure, Y=heart_condition.

    Graph: X → M, X → Y, M → Y (mediator on the X→Y path plus a direct edge).

    Parameters (all from CLadder Q1358 prompt):
      P(Y=1 | X=0, M=0) = 0.71      P(Y=1 | X=1, M=0) = 0.81
      P(Y=1 | X=0, M=1) = 0.46      P(Y=1 | X=1, M=1) = 0.33
      P(M=1 | X=0) = 0.75           P(M=1 | X=1) = 0.31

    CLadder ground-truth NIE at X=0 reference is 0.11.
    """
    def atom(pred: str) -> dict:
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    def grounded(pred: str, value) -> dict:
        return {"atom": atom(pred), "value": value}

    def prob(target_pred: str, target_v, given_pairs: list, value: float) -> dict:
        return {
            "kind": "probability",
            "target": grounded(target_pred, target_v),
            "given": [grounded(p, v) for p, v in given_pairs],
            "value": value,
        }

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "m",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "y",
             "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("m")},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "cause", "from": atom("m"), "to": atom("y")},
            # P(Y=1 | X, M)
            prob("y", True, [("x", False), ("m", False)], 0.71),
            prob("y", True, [("x", False), ("m", True)],  0.46),
            prob("y", True, [("x", True),  ("m", False)], 0.81),
            prob("y", True, [("x", True),  ("m", True)],  0.33),
            # P(M=1 | X) — partial-distribution completion fills the M=0 side
            prob("m", True, [("x", False)], 0.75),
            prob("m", True, [("x", True)],  0.31),
            # Query: effect of X=1 on Y=1 with mediator M
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": grounded("y", True),
                "given": [],
                "mediator": atom("m"),
            }},
        ],
    }


# ---------------------------------------------------------------------------
# End-to-end: Q1358 numeric resolution
# ---------------------------------------------------------------------------


def test_q1358_resolves_to_numerically_solved():
    """Kernel should reach NUMERICALLY_SOLVED for Q1358 — the pre-Fix-1
    behavior of STRUCTURALLY_SOLVED on an LLM-supplied theta-complete
    mediation program was the bug this fix closes."""
    out = themis.run(_q1358_program())
    result = out["results"][0]
    assert result["status"] == "numerically_solved", (
        f"expected numerically_solved, got {result['status']}"
    )


def test_q1358_te_is_pearl_decomposition_sum():
    """Pearl 2001 identity: TE = NDE_at_control + NIE_at_treated.
    A kernel that gets the decomposition right must satisfy this on
    every numerically-solved mediation result.
    """
    out = themis.run(_q1358_program())
    numeric = out["results"][0]["extensions"]["mediation_decomposition"]["numeric"]
    te = numeric["te"]
    nde = numeric["nde_at_control"]
    nie = numeric["nie_at_treated"]
    assert abs(te - (nde + nie)) < 1e-9, (
        f"TE ({te}) must equal NDE_at_control ({nde}) + NIE_at_treated ({nie})"
    )


def test_q1358_nie_at_control_matches_cladder_ground_truth():
    """CLadder Q1358 expected NIE at X=0 reference is 0.11.

    NIE_at_control = E[Y(X=0, M(X=1))] − E[Y(X=0)]
                   = Σ_v P(Y=1|X=0, V2=v)·[P(V2=v|X=1) − P(V2=v|X=0)]
                   = 0.11

    Kernel now exposes both Pearl decompositions; we read NIE_at_control
    directly from extensions.
    """
    out = themis.run(_q1358_program())
    numeric = out["results"][0]["extensions"]["mediation_decomposition"]["numeric"]
    nie_at_control = numeric["nie_at_control"]
    assert abs(nie_at_control - 0.11) < 0.005, (
        f"NIE_at_control expected ~0.11, got {nie_at_control:.4f}"
    )


def test_q1358_both_pearl_decompositions_hold():
    """TE = NDE_at_control + NIE_at_treated  (treated reference)
    TE = NDE_at_treated + NIE_at_control  (control reference)
    Both must agree on TE — this is a Pearl 2001 identity, not a
    statistical estimate. Floating-point tolerance only.
    """
    out = themis.run(_q1358_program())
    numeric = out["results"][0]["extensions"]["mediation_decomposition"]["numeric"]
    te = numeric["te"]
    assert abs(te - (numeric["nde_at_control"] + numeric["nie_at_treated"])) < 1e-9
    assert abs(te - (numeric["nde_at_treated"] + numeric["nie_at_control"])) < 1e-9


def test_q1358_numeric_result_value_is_total_effect():
    """The QueryResult.numeric_result.value is the canonical "main"
    mediation answer — Total Effect — so external consumers that don't
    inspect extensions still get a meaningful number."""
    out = themis.run(_q1358_program())
    result = out["results"][0]
    te = result["extensions"]["mediation_decomposition"]["numeric"]["te"]
    assert result["numeric_result"]["value"] == te


def test_q1358_themis_verify_round_trip():
    """The independent verifier must accept the full mediation result
    end-to-end. This is the paired-implementation pin: kernel's runtime
    and verifier's rules.py must agree on every NDE/NIE/CDE quantity
    within 1e-9. A drift between the two would be caught here."""
    program = _q1358_program()
    out = themis.run(program)
    # Should not raise
    themis.verify(program, out["results"][0])


# ---------------------------------------------------------------------------
# Partial-theta fallback
# ---------------------------------------------------------------------------


def test_mediation_without_theta_stays_structurally_solved():
    """When the program declares no probability statements, NDE/NIE
    evaluation hits InsufficientTheta inside the helper and the kernel
    must leave status at STRUCTURALLY_SOLVED rather than mis-promote."""
    program = _q1358_program()
    # Strip all probability statements
    program["statements"] = [
        s for s in program["statements"]
        if s.get("kind") != "probability"
    ]
    out = themis.run(program)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    # No numeric_result populated (or value is None)
    nr = result.get("numeric_result")
    assert nr is None or nr.get("value") is None


def test_mediation_without_theta_records_failure_status_in_extensions():
    """The numeric_block surfaces the InsufficientTheta diagnostic so a
    follow-up turn (apply_patch_and_run with theta fill) can act on it."""
    program = _q1358_program()
    program["statements"] = [
        s for s in program["statements"]
        if s.get("kind") != "probability"
    ]
    out = themis.run(program)
    decomposition = out["results"][0]["extensions"]["mediation_decomposition"]
    # Numeric block exists with an nde_nie_status failure marker
    assert "numeric" in decomposition
    assert "nde_nie_status" in decomposition["numeric"]
    assert decomposition["numeric"]["nde_nie_status"]["status"] == "insufficient_theta"


# ---------------------------------------------------------------------------
# Identification gating
# ---------------------------------------------------------------------------


def test_mediation_with_x_descendant_confounder_stays_structurally_solved():
    """When an X-descendant U sits on the M-Y backdoor (M4 violation),
    NDE/NIE is not identifiable. CDE may still work, but TE is unavailable,
    so status stays STRUCTURALLY_SOLVED — the kernel does not invent a
    numeric_result.value out of CDE-only data."""

    def atom(pred: str) -> dict:
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    def grounded(pred: str, value) -> dict:
        return {"atom": atom(pred), "value": value}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "u",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "m",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "y",
             "domain": [True, False]},
            # X → U (intermediate); U → M; U → Y — U is an X-descendant
            # that confounds M-Y, so NDE/NIE M4 fails.
            {"kind": "cause", "from": atom("x"), "to": atom("u")},
            {"kind": "cause", "from": atom("u"), "to": atom("m")},
            {"kind": "cause", "from": atom("u"), "to": atom("y")},
            {"kind": "cause", "from": atom("x"), "to": atom("m")},
            {"kind": "cause", "from": atom("m"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": grounded("y", True),
                "given": [],
                "mediator": atom("m"),
            }},
        ],
    }
    out = themis.run(program)
    result = out["results"][0]
    # NDE/NIE structurally not identifiable here (M4 fails). Without TE
    # the kernel must not promote to numerically_solved.
    assert result["status"] == "structurally_solved"
