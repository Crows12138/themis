"""A count of rows, written twice, and read in neither place.

A proximal run solves a second bridge for the treatment, and that bridge is
a reciprocal probability: fitted, it can come out below zero, and where it
does the inverse-probability reading of the answer stops being an average
of anything. The estimator counts the rows it happened on, arm by arm, and
writes the share in two places — onto the arm beside its cross-moments,
where an auditor of the moments finds it, and, where the worst of them
crosses a line, into the warning it occasions, where a reader does.

Neither place had a reader. The share is the one figure in that record no
second implementation can re-derive: it counts rows, and an envelope of
moments carries moments. That is a true reason not to recompute it and it
was taken for a reason to read it nowhere — so a run could count a quarter
of the control arm and tell the reader four percent, or count a quarter and
warn about nothing at all, and every door agreed. The same sentence sits
over ``gg``: the verifier forms ``MᵀΩM`` for itself rather than believing a
recorded operator, which is right, and which left the Gram that operator
was built FROM — a different matrix — with nobody reading it either.

What is asserted here:

- the arithmetic those records cannot escape, each by the edit it exists to
  catch: the first row of ``gg`` moved away from the first row of ``M``
  (both designs carry the constant in their first column, so those are one
  arm's span moments written twice), its leading entry moved away from the
  arm's share of the sample, and a share of rows that does not come back
  whole when multiplied by the rows it was counted over
- the warning held against the arms in both directions — the share it
  prints, the level it names as worst, how many levels it says there were,
  and the two silences: arms past the line with no warning, and a warning
  with every arm inside it
- both spellings, because a contrast names its two arms and a curve keys
  them by level, and the sentences differ in exactly that
- the line and the two statement names restated here, and pinned equal to
  the producer's — a verifier that imported the constant would agree with
  it by construction
- and the one lie this pair cannot catch, asserted as passing so that the
  declared remainder and this file move together.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError
from themis.verifier.bridge_share_rules import (_AT_A_LEVEL, _BETWEEN_ARMS,
                                                _KIND, _LINE)

_STEP = "numeric_proximal_bridge_estimate"

#: β, so a sample can be read without a literal in every assertion.
_BETA = 1.4


# --- the corpus ---------------------------------------------------------

def _atom(p: str) -> dict:
    return {"predicate": p, "args": []}


def _var(p: str, **kw) -> dict:
    return {"kind": "variable", "predicate": p, **kw}


def _cause(a: str, b: str) -> dict:
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _factor(variable: str, dimension: int) -> dict:
    return {"variable": _atom(variable), "basis": "polynomial",
            "dimension": dimension}


def _terms(variable: str, dimension: int, dose: int = 0) -> list:
    """One term, carrying the treatment beside the proxy where asked.

    A curve is one bridge evaluated at many levels, so a curve's outcome
    bridge that does not name the treatment is the same function at every
    one of them — and is refused at the door for saying so.
    """
    factors = [_factor(variable, dimension)]
    if dose:
        factors.append(_factor("x", dose))
    return [{"factors": factors}]


def _program(x_declaration: dict, *, d_h: int, m_h: int, d_q: int,
             m_q: int, dose: int = 0) -> dict:
    """Miao model (f) with both bridges declared: U→{X,Y,Z,W}, Z→X, W→Y.

    The treatment bridge takes the proxies the other way round from the
    outcome bridge's, and is wider on the moment side, because two bridges
    built out of each other's designs are refused at the door: square both
    ways they solve to the same number and the doubly robust guarantee is
    worth nothing.
    """
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            x_declaration, _var("y", scale="continuous"), _var("u"),
            _var("z", scale="continuous"), _var("w", scale="continuous"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom("z")],
                "outcome_proxy": [_atom("w")],
                "channel": {
                    "kind": "bridge_channel",
                    "estimator": "inverse_probability",
                    "outcome_bridge": {
                        "span_terms": _terms("w", d_h, dose),
                        "moment_terms": _terms("z", m_h, dose)},
                    "treatment_bridge": {"span_terms": _terms("z", m_q),
                                         "moment_terms": _terms("w", d_q)},
                },
            }},
        ],
    }


def _contrast_program() -> dict:
    return _program(_var("x", domain=[True, False]),
                    d_h=4, m_h=6, m_q=4, d_q=6)


def _curve_program() -> dict:
    return _program(_var("x", scale="discrete", domain=[0, 1, 2]),
                    d_h=3, m_h=5, m_q=4, d_q=6, dose=3)


def _contrast_sample(n: int = 12000, seed: int = 3) -> pd.DataFrame:
    """A propensity bent in ``U``, which is what makes the true ``q`` need
    columns a short sieve does not have — so the fit dips below zero on a
    quarter of one arm rather than on a handful of rows."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    logit = 0.9 * u + 1.6 * (u ** 2 - 1.0)
    x = rng.random(n) < 1 / (1 + np.exp(-logit))
    return pd.DataFrame({
        "x": x,
        "y": _BETA * x + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.5 * rng.standard_normal(n),
        "w": 0.9 * u + 0.5 * rng.standard_normal(n),
    })


def _curve_sample(n: int = 6000, seed: int = 23) -> pd.DataFrame:
    """The same bend on a clipped and rounded dose: ``1/f`` explodes in the
    tails, and the three levels come out at three different shares, which is
    what lets a test name one of them as the worst."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    dose = np.clip(np.round(1.0 + 0.9 * u + 0.8 * (u ** 2 - 1.0)
                            + 0.8 * rng.standard_normal(n)), 0, 2) + 0.0
    effect = np.where(dose == 0, 0.0, np.where(dose == 1, 1.0, 1.3))
    return pd.DataFrame({
        "x": dose,
        "y": effect + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.4 * rng.standard_normal(n),
        "w": 0.9 * u + 0.4 * rng.standard_normal(n),
    })


@pytest.fixture(scope="module")
def contrast() -> dict:
    out = themis.estimate(_contrast_program(), _contrast_sample(),
                          ci_bootstrap=0)["results"][0]
    assert out["status"] == "numerically_solved", out.get("estimator_failure")
    return out


@pytest.fixture(scope="module")
def curve() -> dict:
    out = themis.estimate(_curve_program(), _curve_sample(),
                          ci_bootstrap=0)["results"][0]
    assert out["status"] == "numerically_solved", out.get("estimator_failure")
    return out


# --- reading the record -------------------------------------------------

def _step(result: dict) -> dict:
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step
    raise AssertionError(f"no {_STEP} step in this derivation")


def _recorded(result: dict) -> dict:
    return _step(result)["inputs"]["measurement_channel"]["items"]


def _arms(result: dict) -> dict:
    """Each arm of the treatment bridge, still inside its wire wrappers."""
    bridge = _recorded(result)["treatment_bridge"]["items"]
    levels = bridge.get("arms")
    blocks = (levels["items"] if isinstance(levels, dict)
              else {name: bridge[name] for name in ("treated", "control")})
    return {name: block["items"] for name, block in blocks.items()}


def _shares(result: dict) -> dict:
    return {name: block["q_negative_fraction"]
            for name, block in _arms(result).items()}


def _warnings(result: dict) -> list:
    return [g for g in result["data_gap_report"]["gaps"]
            if g["kind"] == _KIND]


def _said(result: dict, sentence: str) -> dict:
    for gap in _warnings(result):
        for described in gap.get("describes") or ():
            if described.get("sentence") == sentence:
                return described["said"]
    raise AssertionError(f"no {sentence} on this answer")


def _refused(program: dict, forged: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program, forged)
    return str(raised.value)


def _program_for(which: str) -> dict:
    return _contrast_program() if which == "contrast" else _curve_program()


def _quiet_arm(result: dict) -> str:
    """An arm no warning speaks for, so a forgery of it reaches the record
    rule rather than the sentence one."""
    shares = _shares(result)
    worst = max(shares, key=lambda name: shares[name])
    return sorted(name for name in shares if name != worst)[0]


# --- the denominator ----------------------------------------------------

def test_a_truthful_contrast_verifies(contrast):
    themis.verify(_contrast_program(), contrast)


def test_a_truthful_curve_verifies(curve):
    themis.verify(_curve_program(), curve)


def test_the_two_records_carry_what_this_file_is_about(contrast, curve):
    """Every forgery below moves one of these. A fixture that had drifted
    inside the line, or onto one arm, would leave the file asserting
    nothing while still passing."""
    named, keyed = _shares(contrast), _shares(curve)
    assert sorted(named) == ["control", "treated"]
    assert sorted(keyed) == ["0.0", "1.0", "2.0"]
    for shares in (named, keyed):
        assert max(shares.values()) > _LINE, shares
        assert len(set(shares.values())) == len(shares), shares
    assert len(_warnings(contrast)) == 1
    assert len(_warnings(curve)) == 1
    assert set(_said(contrast, _BETWEEN_ARMS)) >= {"treated", "control"}
    assert set(_said(curve, _AT_A_LEVEL)) >= {"share", "level", "levels"}


# --- the line and the names, restated -----------------------------------

def test_the_line_is_the_one_the_estimator_draws():
    """Restated and not imported, so moving it is something somebody
    declares. This is the assertion that makes the copy honest."""
    from themis.estimation.dispatch import _Q_NEGATIVE_SHARE

    assert _LINE == _Q_NEGATIVE_SHARE


def test_the_warning_and_its_statements_are_the_ones_filed():
    from themis.gaps import Sentence
    from themis.types import GapKind

    assert _KIND == GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE
    assert _BETWEEN_ARMS == Sentence.THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE
    assert _AT_A_LEVEL == (
        Sentence.THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE_AT_A_LEVEL)


# --- the record: what an arm's own numbers are --------------------------

@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_moved_leading_gram_entry_is_refused(request, which):
    """``gg[0][0]`` is the constant against itself: the share of the sample
    this arm is, which the arm also records as a row count."""
    forged = copy.deepcopy(request.getfixturevalue(which))
    arm = _arms(forged)[sorted(_arms(forged))[0]]
    arm["gg"]["items"][0]["items"][0] += 0.05
    said = _refused(_program_for(which), forged)
    assert "treatment_bridge" in said


@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_moved_gram_row_is_refused(request, which):
    """The rest of that row is the arm's mean of each span function, and
    the cross-moments record the same means against the constant."""
    forged = copy.deepcopy(request.getfixturevalue(which))
    arm = _arms(forged)[sorted(_arms(forged))[0]]
    arm["gg"]["items"][0]["items"][1] += 0.05
    said = _refused(_program_for(which), forged)
    assert "first column" in said


@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_gram_of_the_wrong_width_is_refused(request, which):
    """Nothing else on this envelope reads ``gg``, so nothing else would
    have noticed it stop being a matrix of the span's width."""
    forged = copy.deepcopy(request.getfixturevalue(which))
    arm = _arms(forged)[sorted(_arms(forged))[0]]
    arm["gg"]["items"] = arm["gg"]["items"][:-1]
    said = _refused(_program_for(which), forged)
    assert "moments of the span" in said


@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_share_that_is_not_a_count_of_rows_is_refused(request, which):
    """The one figure here no arithmetic reproduces still has a
    denominator: some of an arm's rows over all of them.

    Told of an arm no sentence speaks for, so what answers is the record's
    own arithmetic and not the warning beside it.
    """
    forged = copy.deepcopy(request.getfixturevalue(which))
    arm = _arms(forged)[_quiet_arm(forged)]
    counted = round(float(arm["q_negative_fraction"]) * arm["n"])
    arm["q_negative_fraction"] = (counted + 0.5) / arm["n"]
    said = _refused(_program_for(which), forged)
    assert "comes back whole" in said


@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_share_outside_nought_to_one_is_refused(request, which):
    forged = copy.deepcopy(request.getfixturevalue(which))
    _arms(forged)[_quiet_arm(forged)]["q_negative_fraction"] = -0.25
    said = _refused(_program_for(which), forged)
    assert "none of them and all of them" in said


# --- the warning: what a reader is shown --------------------------------

def test_a_contrast_share_printed_for_the_wrong_arm_is_refused(contrast):
    """The swap that reads as honest: both numbers are this answer's and
    the reader is told the wrong one about each arm."""
    forged = copy.deepcopy(contrast)
    said = _said(forged, _BETWEEN_ARMS)
    said["treated"], said["control"] = said["control"], said["treated"]
    assert "counted" in _refused(_contrast_program(), forged)


@pytest.mark.parametrize("arm", ["treated", "control"])
def test_a_contrast_share_moved_is_refused(contrast, arm):
    forged = copy.deepcopy(contrast)
    _said(forged, _BETWEEN_ARMS)[arm] = "0.1%"
    said = _refused(_contrast_program(), forged)
    assert "which is written" in said


def test_a_curve_share_moved_is_refused(curve):
    forged = copy.deepcopy(curve)
    _said(forged, _AT_A_LEVEL)["share"] = "0.1%"
    assert "which is written" in _refused(_curve_program(), forged)


def test_a_curve_naming_a_level_that_was_not_the_worst_is_refused(curve):
    """Which level it was matters as much as the share: a reader deciding
    whether to trust the curve is deciding whether this is one point's
    problem or the whole curve's."""
    forged = copy.deepcopy(curve)
    shares = _shares(forged)
    worst = max(shares, key=lambda level: shares[level])
    said = _said(forged, _AT_A_LEVEL)
    said["level"] = sorted(level for level in shares if level != worst)[0]
    assert "another level" in _refused(_curve_program(), forged)


def test_a_curve_naming_a_level_this_bridge_has_not_got_is_refused(curve):
    forged = copy.deepcopy(curve)
    _said(forged, _AT_A_LEVEL)["level"] = "7.0"
    assert "the bridge records" in _refused(_curve_program(), forged)


def test_a_curve_miscounting_its_levels_is_refused(curve):
    forged = copy.deepcopy(curve)
    said = _said(forged, _AT_A_LEVEL)
    said["levels"] = str(len(_shares(forged)) + 1)
    assert "levels and this bridge" in _refused(_curve_program(), forged)


# --- the two silences ---------------------------------------------------

@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_arms_past_the_line_with_no_warning_are_refused(request, which):
    """The dangerous direction. A warning that is simply absent is what a
    clean run looks like, so the whole of the disclosure was that somebody
    remembered to make it."""
    forged = copy.deepcopy(request.getfixturevalue(which))
    report = forged["data_gap_report"]
    report["gaps"] = [g for g in report["gaps"] if g["kind"] != _KIND]
    said = _refused(_program_for(which), forged)
    assert "carries no" in said


@pytest.mark.parametrize("which", ["contrast", "curve"])
def test_a_warning_with_every_arm_inside_the_line_is_refused(request, which):
    """And the other direction, which costs a reader an answer they could
    have used."""
    forged = copy.deepcopy(request.getfixturevalue(which))
    for arm in _arms(forged).values():
        arm["q_negative_fraction"] = 0.0
    said = _refused(_program_for(which), forged)
    assert "within the" in said


# --- the one lie this pair cannot catch ---------------------------------

def test_a_quiet_arm_zeroed_is_not_caught(curve):
    """Measured, not assumed, and asserted so that it moves when the
    declared remainder does.

    A count of zero is a whole number, and the curve's warning speaks for
    the level that was worst — so an arm that is neither can be told to
    have gone negative on nobody and no reader of this record is any the
    wiser. A bridge that never went below zero and a producer who says so
    write the same thing down, which is the whole of it: the other three
    values this leaf can take are each refused above.
    """
    forged = copy.deepcopy(curve)
    shares = _shares(forged)
    worst = max(shares, key=lambda level: shares[level])
    quiet = sorted(level for level in shares if level != worst)[0]
    assert shares[quiet] > 0.0, shares
    _arms(forged)[quiet]["q_negative_fraction"] = 0.0
    themis.verify(_curve_program(), forged)
