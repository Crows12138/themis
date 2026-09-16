"""Independent re-derivation of the VanderWeele-Ding E-value sensitivity
block (``verify_e_value``).

Mirrors ``test_sensitivity_ovb.py``: the block's E-value / CI-bound E-value
are a closed form of the audited headline ATE plus one recorded conversion
input (control-arm baseline rate, or outcome SD), so the verifier recomputes
them from scratch and must reject any tamper.

The oracle is threefold:
- **textbook literals** — a hand-built block whose numbers are the plain
  VanderWeele-Ding value E = RR + √(RR·(RR−1)) for RR=2 (= 2+√2) proves the
  verifier matches the formula, not merely the producer's own code;
- **producer round-trip** — a genuine block from ``themis.estimate`` passes;
- **tamper rejection** — mutating any reported number raises, and where
  there is no number, so does mutating why, the value in it, or the inputs
  that decided it.
"""
from __future__ import annotations

import copy
import json
import math
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import language
from themis.estimation.sensitivity import (
    e_value_from_ate_binary, e_value_from_ate_continuous,
)
from themis.verifier.verify import VerificationError, verify_e_value


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# --- genuine producer blocks -------------------------------------------------


def _confounded_bool_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _binary_result():
    rng = np.random.default_rng(0)
    n = 2000
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    p_y = np.clip(0.2 + 0.1 * z + 0.15 * x.astype(float), 0.01, 0.99)
    y = rng.random(n) < p_y
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    ast = _confounded_bool_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    return ast, out["results"][0]


def _continuous_result():
    rng = np.random.default_rng(1)
    n = 1500
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    y = 1.0 * z + 2.0 * x.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    ast = _confounded_bool_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    return ast, out["results"][0]


# --- textbook oracle (independent of the producer) ---------------------------


def test_textbook_oracle_binary_passes():
    """RR=2 ⇒ E = 2 + √2; RR=1.5 (CI bound) ⇒ E = 1.5 + √0.75. Literals
    computed here by plain arithmetic, NOT the E-value formula function."""
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.2,     # treated = 0.2+0.2 = 0.4 ⇒ RR = 2
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,          # 3.41421356…
            "e_value_ci_bound": 1.5 + 0.75 ** 0.5,  # RR_ci = 0.3/0.2 = 1.5
            # 2.366 < 2.5 ⇒ moderate. The point's 3.414 would have said
            # substantial, which is the whole of the distinction: the reading
            # follows the bound, and the two land in different bands here.
            "interpretation_band": "moderate",
            "band_basis": "ci_bound",
            "note": "textbook oracle",
        },
    }
    verify_e_value(est)  # must not raise


def test_textbook_oracle_continuous_passes():
    rr = math.exp(0.91 * (0.5 / 2.0))          # SMD = 0.25
    rr_ci = math.exp(0.91 * (0.2 / 2.0))        # CI bound = 0.2
    est = {
        "point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
        "sensitivity_analysis": {
            "path": "continuous",
            "baseline_rate": None,
            "outcome_sd": 2.0,
            "risk_ratio": rr,
            "e_value": rr + math.sqrt(rr * (rr - 1.0)),
            "e_value_ci_bound": rr_ci + math.sqrt(rr_ci * (rr_ci - 1.0)),
            # 1.418 < 1.5 ⇒ fragile, where the point's 1.822 says moderate.
            "interpretation_band": "fragile",
            "band_basis": "ci_bound",
            "note": "textbook oracle (continuous)",
        },
    }
    verify_e_value(est)  # must not raise


# --- producer round-trip -----------------------------------------------------


def test_verifier_accepts_genuine_binary_block():
    _, r = _binary_result()
    est = r["numeric_estimate"]
    assert est["sensitivity_analysis"]["path"] == "binary"
    verify_e_value(est)  # no raise


def test_verifier_accepts_genuine_continuous_block():
    _, r = _continuous_result()
    est = r["numeric_estimate"]
    assert est["sensitivity_analysis"]["path"] == "continuous"
    assert est["sensitivity_analysis"]["baseline_rate"] is None
    verify_e_value(est)  # no raise


# --- tamper rejection --------------------------------------------------------


def test_rejects_tampered_e_value():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["e_value"] = 9.99   # inflate to look robust
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_e_value_ci_bound():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["e_value_ci_bound"] = 42.0
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_risk_ratio():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["risk_ratio"] = 1.0001
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_baseline_rate():
    """Moving the recorded baseline changes the re-derived RR, so the recorded
    E-value no longer matches — caught."""
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["baseline_rate"] = 0.5
    with pytest.raises(VerificationError):
        verify_e_value(est)


# --- undefined consistency ---------------------------------------------------


def _no_number(path, *, because, baseline=None, sd=None):
    """A block that converted nothing, saying why."""
    return {
        "path": path, "baseline_rate": baseline, "outcome_sd": sd,
        "risk_ratio": None, "e_value": None, "e_value_ci_bound": None,
        "interpretation_band": None, "band_basis": None,
        "undefined_because": because,
    }


def _why(token, **said):
    return {"vocabulary": "e_value_undefined", "token": token, "said": said}


#: Each reason there is no E-value, written out by hand: the estimate, the
#: block that says why, and the producer's own function asked about the same
#: inputs. The literal is the oracle and the producer is asked to agree with
#: it, so the verifier is not only matching the producer's code.
_NO_NUMBER = {
    "baseline_on_boundary": (
        {"point": 0.1, "ci_lower": 0.05, "ci_upper": 0.15},
        _no_number("binary", baseline=0.0,
                   because=_why("baseline_on_boundary", rate="0.000")),
        lambda: e_value_from_ate_binary(0.1, baseline_rate=0.0,
                                        ci_bound=0.05),
    ),
    "treated_rate_out_of_range": (
        {"point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8},
        _no_number("binary", baseline=0.9,          # treated = 1.4
                   because=_why("treated_rate_out_of_range", rate="1.400")),
        lambda: e_value_from_ate_binary(0.5, baseline_rate=0.9,
                                        ci_bound=0.2),
    ),
    "ate_not_finite": (
        {"point": math.inf, "ci_lower": None, "ci_upper": None},
        _no_number("continuous", sd=2.0,
                   because=_why("ate_not_finite", ate="inf")),
        lambda: e_value_from_ate_continuous(math.inf, outcome_sd=2.0),
    ),
    "outcome_sd_not_usable": (
        {"point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8},
        _no_number("continuous", sd=0.0,
                   because=_why("outcome_sd_not_usable", sd="0")),
        lambda: e_value_from_ate_continuous(0.5, outcome_sd=0.0,
                                            ci_bound=0.2),
    ),
}

#: Which conversion input each path reads.
_READS = {"binary": "baseline_rate", "continuous": "outcome_sd"}


def test_every_reason_there_is_has_a_block_written_out():
    assert set(_NO_NUMBER) == {
        str(member) for member in language.VOCABULARIES["e_value_undefined"]}


@pytest.mark.parametrize("reason", sorted(_NO_NUMBER))
def test_a_block_with_no_number_that_says_why_is_accepted(reason):
    """The producer says this reason for these inputs, and the verifier
    agrees rather than inventing a number or taking any reason at all."""
    estimate, block, produced = _NO_NUMBER[reason]
    assert produced().undefined_because == block["undefined_because"]
    verify_e_value({**estimate, "sensitivity_analysis": block})


def _told_otherwise(block):
    """Every other thing the block could say about why it has no number."""
    why = block["undefined_because"]
    for token in sorted(_NO_NUMBER):
        if token != why["token"]:
            yield f"reason {token}", {
                **block, "undefined_because": {**why, "token": token}}
    (hole,) = why["said"]
    yield f"{hole} 0.500", {
        **block, "undefined_because": {**why, "said": {hole: "0.500"}}}
    yield "no reason", {
        key: value for key, value in block.items()
        if key != "undefined_because"}


@pytest.mark.parametrize("reason", sorted(_NO_NUMBER))
def test_a_block_with_no_number_is_held_to_why(reason):
    """Why is the other branch of the conditions the numbers are computed
    under, from the same inputs. Only the branch that yields a number was
    re-derived, so a block with none was checked by two absences agreeing,
    and every one of these was accepted."""
    estimate, block, _ = _NO_NUMBER[reason]
    taken = []
    for lie, forged in _told_otherwise(block):
        try:
            verify_e_value({**estimate, "sensitivity_analysis": forged})
        except VerificationError as exc:
            assert "undefined_because" in str(exc), (lie, str(exc))
        else:
            taken.append(lie)
    assert taken == []


def test_the_input_that_decided_a_reason_is_held_by_it():
    """A baseline moved from one boundary to the other still converts to no
    number, and so does one moved inside (0,1) far enough that the treated
    rate leaves it. Each is a different sentence about why."""
    estimate, block, _ = _NO_NUMBER["baseline_on_boundary"]
    for baseline in (1.0, 0.95):
        forged = {**block, "baseline_rate": baseline}
        with pytest.raises(VerificationError, match="undefined_because"):
            verify_e_value({**estimate, "sensitivity_analysis": forged})


@pytest.mark.parametrize("reason", ["baseline_on_boundary",
                                    "outcome_sd_not_usable"])
def test_the_path_says_which_input_the_block_holds(reason):
    """A path is which conversion ran. Read as "no input, so nothing to
    convert", a block whose path was rewritten agreed with its own missing
    numbers."""
    estimate, block, _ = _NO_NUMBER[reason]
    other = next(path for path in _READS if path != block["path"])
    forgeries = {
        "the other path": {**block, "path": other},
        "no input": {**block, _READS[block["path"]]: None},
        "the other path's input beside it": {**block, _READS[other]: 0.3},
    }
    taken = []
    for lie, forged in forgeries.items():
        try:
            verify_e_value({**estimate, "sensitivity_analysis": forged})
        except VerificationError:
            continue
        taken.append(lie)
    assert taken == []


def test_a_block_converts_an_ate_the_estimate_reports():
    _, block, _ = _NO_NUMBER["baseline_on_boundary"]
    with pytest.raises(VerificationError, match="does not report"):
        verify_e_value({"sensitivity_analysis": block})


def test_a_block_with_a_number_gives_no_reason_for_having_none():
    _, r = _binary_result()
    est = copy.deepcopy(r["numeric_estimate"])
    assert est["sensitivity_analysis"]["e_value"] is not None
    est["sensitivity_analysis"]["undefined_because"] = _why(
        "baseline_on_boundary", rate="0.000")
    with pytest.raises(VerificationError, match="undefined_because"):
        verify_e_value(est)


def test_rejects_value_claimed_when_undefined():
    est = {
        "point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.9,       # treated = 1.4 ∉ (0,1) ⇒ undefined
            "outcome_sd": None,
            "risk_ratio": None,
            "e_value": 3.0,             # but a value is claimed
            "e_value_ci_bound": None,
            "note": "tampered — claims a value where none is defined",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_a_reading_taken_off_the_point():
    """The reading is audited like the numbers under it.

    The tamper is not a made-up band: it is the band this block would have
    carried under the rule the module used to apply — the point estimate's
    3.414 lands in ``substantial`` while the bound's 2.366 lands in
    ``moderate``. A verifier that re-derived the numbers and took the
    reading on trust would pass a block whose one reader-facing conclusion
    is the one that was wrong.
    """
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.2,
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,
            "e_value_ci_bound": 1.5 + 0.75 ** 0.5,
            "interpretation_band": "substantial",   # read off the point
            "band_basis": "point",
            "note": "tampered — the reading follows the wrong number",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_unknown_path():
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "logistic-magic",
            "baseline_rate": 0.2,
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,
            "e_value_ci_bound": None,
            "interpretation_band": "substantial",
            "band_basis": "point",
            "note": "unknown path",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_missing_block_is_noop():
    verify_e_value({"point": 0.2})  # no sensitivity_analysis → no raise


# --- end-to-end through the kernel verifier ----------------------------------


def test_e2e_verify_round_trips_binary():
    ast, r = _binary_result()
    themis.verify(ast, r)  # E-value block now audited inside the kernel


def test_e2e_verify_rejects_tampered_e_value():
    ast, r = _binary_result()
    r["numeric_estimate"]["sensitivity_analysis"]["e_value"] = 9.99
    with pytest.raises((VerificationError, Exception)):
        themis.verify(ast, r)


_SHAPES = pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json"
_NO_E_VALUE = "numerically_solved:effect:numeric_backdoor_estimate#292d9a"


def test_e2e_the_answer_with_no_e_value_is_held_to_why():
    """The one answer in the corpus whose estimate has no E-value: its
    untreated arm never has the outcome. What it said about why, and the
    baseline and path that decide it, passed every door however they were
    rewritten."""
    pair = json.loads(_SHAPES.read_text(encoding="utf-8"))[_NO_E_VALUE]
    block = pair["result"]["numeric_estimate"]["sensitivity_analysis"]
    assert block["e_value"] is None
    assert block["undefined_because"]["token"] == "baseline_on_boundary"
    themis.verify(pair["program"], pair["result"])

    def bent(change):
        result = copy.deepcopy(pair["result"])
        change(result["numeric_estimate"]["sensitivity_analysis"])
        return result

    lies = {
        "reason": lambda b: b["undefined_because"].update(
            token="treated_rate_out_of_range"),
        "rate": lambda b: b["undefined_because"]["said"].update(rate="1.000"),
        "baseline": lambda b: b.update(baseline_rate=1.0),
        "path": lambda b: b.update(path="continuous"),
    }
    taken = []
    for lie, change in lies.items():
        try:
            themis.verify(pair["program"], bent(change))
        except VerificationError as exc:
            assert "e_value" in str(exc), (lie, str(exc))
        else:
            taken.append(lie)
    assert taken == []
