"""The controlled direct effect, from a program rather than from a call.

Two facts about the same estimand, and each of them was wrong on its own:

**Nobody could reach it.** The identification layer reports
``strategy == "cde"`` when the natural effects do not survive the graph and
the controlled one does — the case the CDE exists for, and by the solver's
own count the commoner of the two outcomes once natural effects fail. On
that branch the dispatcher said ``numeric_end_not_built`` while
``estimate_cde`` sat written, exported and separately tested in
``mediation.py``. The tests that covered it all called it directly, which
is a shape of test that cannot see this at all.

**The level it names did nothing.** Its outcome model was ``Y ~ X + M + Z``
with no exposure-mediator product, so the fitted contrast could not depend
on where the mediator was held — while the estimand does, whenever the two
interact. Measured on a frame whose true CDE(m*) is ``1 + 2m*``, it
returned one number, 1.586, at m* = 0, 0.5, 1 and 2.

The conformance graph:

    X -> M -> Y,  X -> Y,  X <-> M

A latent confounder of treatment and mediator only. It destroys P(M_x), so
the natural effects go; under do(X, M) the offending path is cut at its
M -> Y edge, so the controlled one stays.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.mediation import estimate_cde, estimate_cde_curve
from themis.estimation.support import levels_over_support
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dgp(n=8000, seed=23, interaction=2.0):
    """Y = 1.4 X + 0.7 M + interaction·X·M + noise, so CDE(m*) =
    1.4 + interaction·m*. U reaches X and M and NOT Y, which is what the
    bidirected edge says."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-1.2 * u))
    xf = x.astype(float)
    m = 0.9 * xf + 0.8 * u + rng.standard_normal(n) * 0.3
    y = (1.4 * xf + 0.7 * m + interaction * xf * m
         + rng.standard_normal(n) * 0.3)
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _binary_mediator_dgp(n=8000, seed=29):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-1.2 * u))
    xf = x.astype(float)
    m = rng.random(n) < 1 / (1 + np.exp(-(0.9 * xf + 0.8 * u - 0.4)))
    y = (1.4 * xf + 0.7 * m.astype(float)
         + 2.0 * xf * m.astype(float) + rng.standard_normal(n) * 0.3)
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _program(mediator_scale="continuous"):
    m_decl = ({"kind": "variable", "predicate": "m", "scale": "continuous"}
              if mediator_scale == "continuous"
              else {"kind": "variable", "predicate": "m",
                    "domain": [True, False]})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            m_decl,
            {"kind": "variable", "predicate": "y", "scale": "continuous"},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("m")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "mediator": _atom("m"),
                "given": [],
            }},
        ],
    }


def _run(df, program=None, **kw):
    out = themis.estimate(program or _program(), df,
                          ci_bootstrap=kw.pop("ci_bootstrap", 0),
                          random_state=7, **kw)
    return out["results"][0]


# --------------------------------------------------------------- reach
def test_the_graph_that_kills_the_natural_effects_keeps_this_one():
    r = _run(_dgp())
    decomp = (r["extensions"] or {})["mediation_decomposition"]
    assert decomp["nde_nie"]["identifiable"] is False
    assert decomp["cde"]["identifiable"] is True
    assert decomp["strategy"] == "cde"


def test_a_program_on_that_graph_gets_a_number():
    """The branch that used to end in ``numeric_end_not_built``."""
    r = _run(_dgp())
    assert r["numeric_estimate"] is not None
    assert r["numeric_estimate"]["method"] == "cde_linear"
    assert r["numeric_estimate"]["controlled_direct_effect"]["levels"]


def test_the_curve_recovers_the_true_direct_effect_at_every_level():
    r = _run(_dgp(n=20000))
    rows = r["numeric_estimate"]["controlled_direct_effect"]["levels"]
    assert len(rows) >= 3
    for row in rows:
        truth = 1.4 + 2.0 * row["mediator_level"]
        assert abs(row["point"] - truth) < 0.06, (row, truth)


# ------------------------------------------------------- the level acts
def test_the_level_moves_the_answer_when_the_two_interact():
    r = _run(_dgp(n=20000))
    block = r["numeric_estimate"]["controlled_direct_effect"]
    points = [row["point"] for row in block["levels"]]
    assert block["varies_with_level"] is True
    assert max(points) - min(points) > 1.0


def test_a_frame_with_no_interaction_gives_a_flat_curve():
    """The degenerate point. Where the term this route added is zero in
    truth, the curve it produces is the one the old no-interaction model
    would have produced — so the change buys the interacting case without
    moving the non-interacting one."""
    r = _run(_dgp(n=20000, interaction=0.0))
    rows = r["numeric_estimate"]["controlled_direct_effect"]["levels"]
    points = [row["point"] for row in rows]
    assert max(points) - min(points) < 0.05
    for p in points:
        assert abs(p - 1.4) < 0.05


def test_varies_with_level_is_held_to_what_the_levels_say():
    flat = _run(_dgp(n=20000, interaction=0.0))
    block = flat["numeric_estimate"]["controlled_direct_effect"]
    # Flat to the eye is not flat to the arithmetic — the flag reports the
    # exact question, and the verifier holds it to the same one.
    points = [row["point"] for row in block["levels"]]
    assert block["varies_with_level"] == (max(points) != min(points))


# --------------------------------------------------------- which levels
def test_a_binary_mediator_is_read_at_the_levels_the_sample_holds():
    r = _run(_binary_mediator_dgp(), program=_program("binary"))
    block = r["numeric_estimate"]["controlled_direct_effect"]
    assert block["levels_observed"] is True
    assert [row["mediator_level"] for row in block["levels"]] == [0.0, 1.0]


def test_a_continuous_mediator_says_its_levels_are_a_models_answer():
    r = _run(_dgp())
    block = r["numeric_estimate"]["controlled_direct_effect"]
    assert block["levels_observed"] is False
    assert ("mediator_levels_read_at_quantiles_of_a_continuum"
            in r["numeric_estimate"]["assumptions"])


def test_the_levels_come_from_the_one_place_that_decides_them():
    df = _dgp()
    r = _run(df)
    expected, observed = levels_over_support(df["m"].to_numpy(dtype=float))
    block = r["numeric_estimate"]["controlled_direct_effect"]
    assert [row["mediator_level"] for row in block["levels"]] == list(expected)
    assert block["levels_observed"] is observed


# ------------------------------------------------------------- audited
def test_the_kernel_accepts_what_the_route_produced():
    program = _program()
    r = _run(_dgp(), program=program, ci_bootstrap=60)
    themis.verify(program, r)


@pytest.mark.parametrize("field", ["point", "risk_treated"])
def test_the_kernel_refuses_a_forged_curve(field):
    program = _program()
    r = _run(_dgp(), program=program)
    forged = json.loads(json.dumps(r))
    forged["numeric_estimate"]["controlled_direct_effect"][
        "levels"][0][field] += 1.0
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, forged)


def test_the_kernel_refuses_a_flag_that_disagrees_with_the_levels():
    program = _program()
    r = _run(_dgp(), program=program)
    forged = json.loads(json.dumps(r))
    block = forged["numeric_estimate"]["controlled_direct_effect"]
    block["varies_with_level"] = not block["varies_with_level"]
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, forged)


def test_the_linear_curve_is_re_derived_and_not_merely_re_checked():
    """A forgery consistent with its own two risks still fails, because the
    recorded coefficients settle the whole curve independently."""
    program = _program()
    r = _run(_dgp(), program=program)
    forged = json.loads(json.dumps(r))
    row = forged["numeric_estimate"]["controlled_direct_effect"]["levels"][0]
    row["point"] += 1.0
    row["risk_treated"] += 1.0        # self-consistent with risk_control
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, forged)


# ----------------------------------------------------- the two entries
def test_one_level_is_the_curve_at_one_level():
    df = _dgp()
    one = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                       mediator_value=0.5, ci_bootstrap=40, random_state=3)
    curve = estimate_cde_curve(df, treatment="x", outcome="y", mediator="m",
                               mediator_values=(0.5,), ci_bootstrap=40,
                               random_state=3)
    assert one.point == curve.levels[0].point
    assert one.ci_lower == curve.levels[0].ci_lower
    assert one.ci_upper == curve.levels[0].ci_upper


def test_every_level_stands_on_the_same_replicates():
    """One resample serves the whole curve, so a difference between two
    rows is curvature rather than two bootstraps disagreeing."""
    curve = estimate_cde_curve(
        _dgp(), treatment="x", outcome="y", mediator="m",
        mediator_values=(0.0, 1.0), ci_bootstrap=50, random_state=5)
    assert curve.draws is not None
    assert curve.draws.used == curve.draws.requested


# ------------------------------------------------------------ the page
def test_the_reader_is_shown_the_curve_and_not_a_verdict():
    program = _program()
    r = _run(_dgp(), program=program)
    report = themis.build_analysis_report(
        {"status": r["status"], "query_kind": r["query_kind"],
         "numeric_estimate": r["numeric_estimate"],
         "structural_result": r.get("structural_result"),
         "extensions": r.get("extensions") or {}},
        lang="zh",
    )
    text = json.dumps(report, ensure_ascii=False)
    assert "受控" in text or "固定" in text, text[:600]


def test_the_ledger_names_the_model_the_plug_in_stood_on():
    r = _run(_dgp())
    assumptions = r["numeric_estimate"]["assumptions"]
    assert "linear_outcome_regression" in assumptions
