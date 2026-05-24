"""Fix 6 (v0.1.5, audit follow-up) — IV-in-effect Wald LATE dispatch.

Classic IV setup: Z → X → Y with X ↔ Y latent confounder. Backdoor
fails structurally (the bidirected X↔Y is unblockable by any
observable Z). Front-door fails (no X→M→Y mediator). With monotonicity
assumption + boolean treatment + boolean instrument, kernel can
compute Wald LATE.

The numeric is the COMPLIER LATE — average effect among the
subpopulation whose treatment shifts with the instrument — NOT the
population ATE. Extensions surface this caveat explicitly so the
Skill / agent can disclose; Themis's contract is "we report the
quantity the formula actually computes, not the quantity the user
might naively conflate it with".
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _gr(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target_pred, target_v, given_pairs, value):
    return {
        "kind": "probability",
        "target": _gr(target_pred, target_v),
        "given": [_gr(p, v) for p, v in given_pairs],
        "value": value,
    }


def _iv_program(monotonicity: str | None) -> dict:
    """Z (instrument) → X (treatment) → Y (outcome), with X ↔ Y latent
    confounder. Boolean throughout. Theta supplies the 4 conditionals
    Wald needs:

      P(Y=1 | Z=1) = 0.7,  P(Y=1 | Z=0) = 0.3
      P(X=1 | Z=1) = 0.8,  P(X=1 | Z=0) = 0.2

    Expected Wald LATE = (0.7 − 0.3) / (0.8 − 0.2) = 0.4 / 0.6 ≈ 0.667
    """
    stmts = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("y", True, [("z", True)],  0.7),
        _prob("y", True, [("z", False)], 0.3),
        _prob("x", True, [("z", True)],  0.8),
        _prob("x", True, [("z", False)], 0.2),
    ]
    query: dict = {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    stmts.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


# ---------------------------------------------------------------------------
# Happy path: IV numeric fires with monotonicity
# ---------------------------------------------------------------------------


def test_iv_with_monotonicity_resolves_to_numerically_solved():
    """Z→X→Y, X↔Y, theta supplied, monotonicity declared → status
    upgrades to numerically_solved via Wald LATE."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    assert r["status"] == "numerically_solved", (
        f"expected numerically_solved, got {r['status']}"
    )


def test_iv_wald_value_matches_textbook_formula():
    """Wald: LATE = (E[Y|Z=1] − E[Y|Z=0]) / (E[X|Z=1] − E[X|Z=0])
    = (0.7 − 0.3) / (0.8 − 0.2) = 2/3"""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    expected = (0.7 - 0.3) / (0.8 - 0.2)
    assert abs(r["numeric_result"]["value"] - expected) < 1e-9


def test_iv_extensions_block_carries_late_caveat():
    """extensions.iv_identification.late_caveat must explicitly tell
    downstream renderers LATE ≠ ATE. This is the substantive disclosure
    contract: vanilla IV deployments routinely conflate the two."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    ext = r["extensions"]["iv_identification"]
    assert "late_caveat" in ext
    assert "LATE" in ext["late_caveat"]
    assert "ATE" in ext["late_caveat"]


def test_iv_extensions_block_carries_numeric_components():
    """The 4 component conditionals + the derived LATE are exposed in
    extensions for the renderer / agent to surface (parallel to
    mediation_decomposition.numeric / transport_identification.numeric)."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    numeric = r["extensions"]["iv_identification"]["numeric"]
    for key in (
        "p_y_given_z_treated",
        "p_y_given_z_control",
        "p_x_given_z_treated",
        "p_x_given_z_control",
        "late",
    ):
        assert key in numeric


def test_iv_verify_round_trip():
    """Independent verifier accepts the IV Wald derivation —
    iv_criterion_check + identify_via_iv + iv_wald_numeric_evaluate +
    numeric_result, with the bundled rule re-running the 4 theta
    lookups + arithmetic independently."""
    program = _iv_program(monotonicity="non_decreasing")
    out = themis.run(program)
    themis.verify(program, out["results"][0])


# ---------------------------------------------------------------------------
# Without monotonicity: IV numeric skipped, kernel doesn't escalate
# ---------------------------------------------------------------------------


def test_iv_without_monotonicity_does_not_fire_wald():
    """Wald LATE requires the monotonicity assumption; without it,
    the kernel must NOT silently apply Wald and fabricate a LATE
    value. IV-numeric skipped → Tian fallback tries → if Tian also
    fails (hedge), stays needs_investigation."""
    out = themis.run(_iv_program(monotonicity=None))
    r = out["results"][0]
    assert r["status"] == "needs_investigation", (
        f"without monotonicity, IV-numeric must NOT silently fire; "
        f"got status={r['status']}"
    )


# ---------------------------------------------------------------------------
# Theta-incomplete IV: stays needs_investigation
# ---------------------------------------------------------------------------


def test_iv_with_incomplete_theta_falls_through():
    """If theta lacks any of the 4 Wald conditionals, IV-numeric must
    fall through to the next strategy (Tian) / final
    needs_investigation rather than crashing."""
    program = _iv_program(monotonicity="non_decreasing")
    # Drop one of the 4 needed conditionals
    program["statements"] = [
        s for s in program["statements"]
        if not (
            s.get("kind") == "probability"
            and s["target"]["atom"]["predicate"] == "x"
            and len(s["given"]) == 1
            and s["given"][0]["value"] is False
        )
    ]
    out = themis.run(program)
    r = out["results"][0]
    # Either Tian saves it (unlikely on hedge) or needs_investigation.
    # Either way, must NOT crash and must NOT silently produce a wrong LATE.
    assert r["status"] in ("needs_investigation", "structurally_solved")
