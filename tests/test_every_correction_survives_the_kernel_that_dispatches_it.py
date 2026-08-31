# -*- coding: utf-8 -*-
"""Seven corrections share one derivation terminal, and one of them could not
get through it.

``numeric_measurement_correction_estimate`` is the terminal every
measurement-correction route ends on, and its rule opens with a closed list
of the methods it accepts. Five of the six producers were on that list. The
sixth — the differential correction — was not, so ``themis.verify`` rejected
every answer that route ever produced. Not with a weaker audit: with a
refusal, on the flagship contract of the package.

**What made it invisible is where the audits were called from.** Each route
has a dedicated numeric verifier, the kernel dispatches to it by method name,
and every test of those routes calls that verifier DIRECTLY — so the tests
proved the arithmetic re-derives while the kernel could not reach the code
that re-derives it. The dedicated verifier for the differential route had
been written, exported, and wired into ``kernel.verify``; it had simply never
run, because the generic rule raised four lines earlier.

So this file audits the one thing calling a verifier directly cannot: that a
result a route actually produces survives ``themis.verify``. The roster is
read off ``dispatch`` by AST rather than listed, because a seventh route that
nobody adds a case for is exactly how a sixth came to have none.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis

#: Which function builds this terminal is what makes a route one of these,
#: and it is read rather than listed for the reason in the header.
TERMINAL_BUILDER = "_build_measurement_correction_derivation_dict"


def _producers() -> tuple[str, ...]:
    """Every dispatch function that ends a result on this terminal."""
    source = (pathlib.Path(themis.__file__).parent / "estimation"
              / "dispatch.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and getattr(call.func, "id", None) == TERMINAL_BUILDER
    }
    return tuple(sorted(found))


# --- one program, two frames --------------------------------------------------


def _atom(name: str) -> dict:
    return {"predicate": name, "args": [{"type": "const", "name": "p"}]}


def _program(exposure: str, *, domains: bool) -> dict:
    """X → Y with Z confounding both — the back-door design every correction
    here standardises over."""
    declared: dict = {"domain": [False, True]} if domains else {}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": exposure, **declared},
            {"kind": "variable", "predicate": "y", **declared},
            {"kind": "variable", "predicate": "z", **declared},
            {"kind": "cause", "from": _atom(exposure), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom(exposure)},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom(exposure), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }


SE, SP = 0.9, 0.85
SIGMA2_U, DELTA, BETA_X = 0.5, 0.3, 0.8
MATRIX = [[SP, 1 - SE], [1 - SP, SE]]


def _binary_frame(n=40_000, seed=0, *, noisy_x=False, noisy_y=False):
    """Bools whose recorded columns are misclassified at (SE, SP)."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = rng.random(n) < np.where(x, 0.6, 0.4) + np.where(z, 0.1, -0.1)

    def blur(truth):
        keep = np.where(truth, SE, SP)
        return np.where(rng.random(n) < keep, truth, ~truth)

    return pd.DataFrame({
        "x": blur(x) if noisy_x else x,
        "y": blur(y) if noisy_y else y,
        "z": z,
    })


def _continuous_frame(n=8000, seed=0, *, binary_outcome=False,
                      differential=False, outcome_tracks_the_arm=False):
    """W = X* + noise, with the noise optionally tracking the outcome — and,
    on the other channel, the OUTCOME carrying an error that tracks the arm.

    The exposure column the query names differs between the two: the first
    asks about the mismeasured ``w``, the second about the well-measured ``x``
    whose effect on a mismeasured ``y`` is what moved."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    linear = 1.0 + BETA_X * x + 0.4 * z
    y = linear + rng.normal(0, 1, n)
    if outcome_tracks_the_arm:
        residual = x - np.polyval(np.polyfit(z, x, 1), z)
        y = y + DELTA * residual + rng.normal(0, np.sqrt(SIGMA2_U), n)
    if differential:
        residual = y - np.polyval(np.polyfit(z, y, 1), z)
        w = x + DELTA * residual + rng.normal(0, np.sqrt(SIGMA2_U), n)
    else:
        w = x + rng.normal(0, np.sqrt(SIGMA2_U), n)
    if binary_outcome:
        y = rng.random(n) < 1.0 / (1.0 + np.exp(-(linear - linear.mean())))
    return pd.DataFrame({"w": w, "x": x, "y": y, "z": z})


def _misclassified(**channels):
    return {name: {"confusion_matrix": MATRIX, "states": [False, True]}
            for name in channels}


# --- what each route needs to be reached --------------------------------------


def _outcome_side():
    program = _program("x", domains=True)
    return program, themis.estimate(
        program, _binary_frame(noisy_y=True), ci_bootstrap=0,
        misclassification=_misclassified(y=True))


def _exposure_side():
    program = _program("x", domains=True)
    return program, themis.estimate(
        program, _binary_frame(noisy_x=True), ci_bootstrap=0,
        misclassification=_misclassified(x=True))


def _both_sides():
    program = _program("x", domains=True)
    return program, themis.estimate(
        program, _binary_frame(noisy_x=True, noisy_y=True), ci_bootstrap=0,
        misclassification=_misclassified(x=True, y=True))


def _continuous():
    program = _program("w", domains=False)
    return program, themis.estimate(
        program, _continuous_frame(), ci_bootstrap=0,
        measurement_error={"w": {"error_variance": SIGMA2_U}})


def _continuous_nonlinear():
    program = _program("w", domains=False)
    return program, themis.estimate(
        program, _continuous_frame(n=3000, binary_outcome=True),
        ci_bootstrap=0,
        measurement_error={"w": {"error_variance": SIGMA2_U,
                                 "outcome_model": "logistic"}})


def _tracks_the_outcome():
    program = _program("w", domains=False)
    frame = _continuous_frame(differential=True)
    residual = frame["y"] - np.polyval(
        np.polyfit(frame["z"], frame["y"], 1), frame["z"])
    total = SIGMA2_U + DELTA * DELTA * float(np.var(residual, ddof=1))
    return program, themis.estimate(
        program, frame, ci_bootstrap=0,
        measurement_error={"w": {"error_variance": total,
                                 "differential_by": "y",
                                 "differential_coefficient": DELTA}})


def _tracks_the_arm():
    """The other channel: the error is in the OUTCOME and tracks the exposure.

    Its σ²_v is composed rather than chosen, from the same conditional the
    correction takes its split against — a declaration assembled any other way
    would be testing whether the guard trips rather than whether the route
    survives the kernel.
    """
    program = _program("x", domains=False)
    frame = _continuous_frame(outcome_tracks_the_arm=True)
    residual = frame["x"] - np.polyval(
        np.polyfit(frame["z"], frame["x"], 1), frame["z"])
    total = SIGMA2_U + DELTA * DELTA * float(np.var(residual, ddof=1))
    return program, themis.estimate(
        program, frame, ci_bootstrap=0,
        measurement_error={"y": {"error_variance": total,
                                 "differential_by": "x",
                                 "differential_coefficient": DELTA}})


#: One case per producer, keyed by the producer it reaches. The key is what
#: the roster test holds against ``dispatch`` — a route with no case here is
#: a route nothing drives through the kernel, which is the state this file
#: exists to make impossible.
ROUTES = {
    "_try_measurement_correction_estimate": (
        _outcome_side, "measurement_error_correction"),
    "_try_exposure_measurement_correction_estimate": (
        _exposure_side, "exposure_measurement_error_correction"),
    "_try_combined_measurement_correction_estimate": (
        _both_sides, "combined_measurement_error_correction"),
    "_try_regression_calibration_estimate": (
        _continuous, "regression_calibration"),
    "_try_simex_estimate": (
        _continuous_nonlinear, "simex"),
    "_try_differential_error_estimate": (
        _tracks_the_outcome, "differential_regression_calibration"),
    "_try_differential_outcome_error_estimate": (
        _tracks_the_arm, "differential_outcome_correction"),
}


def test_every_producer_of_this_terminal_has_a_case():
    """The denominator, read off the code.

    Listing the routes here and testing the listed ones would pass on the
    day a seventh appears — which is the shape of the defect this file is
    about, one level up.
    """
    assert set(_producers()) == set(ROUTES), (
        f"dispatch builds {TERMINAL_BUILDER} in {sorted(_producers())}; this "
        f"file drives {sorted(ROUTES)}. A route with no case is a route "
        f"nothing puts through themis.verify"
    )


@pytest.mark.parametrize("producer", sorted(ROUTES))
def test_the_kernel_accepts_what_the_route_produced(producer):
    """The audit no direct call to a numeric verifier can perform.

    ``themis.verify`` returns None on accept and raises on rejection, so the
    absence of an exception IS the assertion. What it exercises that a direct
    call does not is the generic terminal rule the kernel runs first — which
    is where the differential route's answers were being turned away before
    the module written to check them could see them.
    """
    build, method = ROUTES[producer]
    program, out = build()
    result = out["results"][0]
    assert result.get("estimator_failure") is None, result["estimator_failure"]
    assert result["status"] == "numerically_solved"
    assert result["numeric_estimate"]["method"] == method
    themis.verify(program, result)


@pytest.mark.parametrize("producer", sorted(ROUTES))
def test_the_kernel_still_refuses_a_forged_point(producer):
    """The denominator for the test above: an audit that accepted everything
    would also accept every honest answer."""
    from themis.verifier.errors import VerificationError

    build, _method = ROUTES[producer]
    program, out = build()
    result = out["results"][0]
    result["numeric_estimate"]["point"] = (
        float(result["numeric_estimate"]["point"]) + 1.0)
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, result)
