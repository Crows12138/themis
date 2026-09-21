"""An arm records five blocks of moments and the replay took three.

``numeric_proximal_bridge_estimate`` says of itself that nothing on the
envelope is believed except the cross-moments, "which are second moments
of the data and are checked for the identities second moments have". Three
of the five had no identity checked. ``s_aa``, ``s_ab`` and ``s_ay`` are
answered for by the answer they produce — the first stage is re-inverted
out of them — while ``s_bb``, ``s_by`` and ``yy`` appeared nowhere in the
verifier at all.

They are not spare. They are the second stage's, and the number they
determine is the standard error: the figure a reader reads as this
answer's uncertainty, which was copied off the envelope rather than
re-derived. So the record held three blocks nobody read and one figure
nobody checked, and the two facts are one fact.

What is asserted here:

- the identities a block of second moments cannot escape, each by the
  edit it exists to catch: an off-diagonal moved alone (symmetry), a
  diagonal made negative (positivity), an outcome moment shrunk below
  what its own span explains (the joint block, whose Schur complement is
  a variance)
- that those identities are NOT the whole of it. A diagonal made LARGER
  stays inside the cone, and three such edits — to ``s_bb``, to ``s_by``,
  to ``yy`` — are refused here anyway, each by the standard error it
  moves. This is the half of the replay that was missing, and these three
  tests are the whole reason the rest is not enough.
- the arms of one roster add up to the sample, and the two rosters add up
  separately — a record whose outcome arms and whose treatment arms each
  cover the sample is honest, and adding them together would count every
  row twice. Both of the treatment bridge's spellings are here, because
  the first version of that rule named one of them and four row counts
  sat in the other.
- the curve regime, where there is one arm and one standard error per
  level
- and that every arm the record names is asked, counted off the record
  rather than listed here.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError
from themis.verifier.rules import (_bridge_sample_adds_up,
                                   _bridge_treatment_arms)
from themis.verifier.errors import RuleCheckFailed

_STEP = "numeric_proximal_bridge_estimate"

#: The three an arm records for the second stage, and which nothing read.
_SECOND_STAGE = ("s_bb", "s_by", "yy")


# --- the corpus ---------------------------------------------------------

def _var(p, **kw):
    return {"kind": "variable", "predicate": p, **kw}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _factor(variable, dimension):
    return {"variable": _atom(variable), "basis": "polynomial",
            "dimension": dimension}


def _program(*, binary: bool, treatment_bridge: bool = False) -> dict:
    """Miao model (f) with continuous proxies, in one regime or the other.

    A binary treatment gives the contrast regime — two arms, one standard
    error. A continuous one gives the curve — one arm, one standard error
    per level. The two record different things and this file needs both.

    The curve's bridge carries the treatment in both halves, because a
    curve is one bridge evaluated at many levels and a bridge that does
    not name the treatment is the same function at every one of them.
    """
    x = _var("x", scale="discrete", domain=[0, 1]) if binary else \
        _var("x", scale="continuous")
    span = [_factor("w", 2)] + ([] if binary else [_factor("x", 3)])
    moment = [_factor("z", 2)] + ([] if binary else [_factor("x", 3)])
    channel: dict = {"kind": "bridge_channel", "outcome_bridge": {
        "span_terms": [{"factors": span}],
        "moment_terms": [{"factors": moment}],
    }}
    if treatment_bridge:
        # The other bridge, with the proxies the other way round. It gives
        # the record a SECOND roster of arms, which is the only way to
        # exercise a rule about two rosters on a real answer. The
        # estimator comes with it: declaring a bridge that
        # ``outcome_regression`` never looks at is refused at the door,
        # and the estimators that do look at it record no analytic
        # standard error — so these rows exercise the rosters and the
        # identities, and the answer's uncertainty is held elsewhere.
        # Wider on the moment side than the outcome bridge's span, because
        # two bridges built from each other's designs are refused at the
        # door: square both ways, they would solve to the same number and
        # the doubly-robust guarantee would be worth nothing.
        channel["treatment_bridge"] = {
            "span_terms": [{"factors": [_factor("z", 2)]}],
            "moment_terms": [{"factors": [_factor("w", 3)]}],
        }
        channel["estimator"] = "inverse_probability"
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            x, _var("y", scale="continuous"), _var("u"),
            _var("z", scale="continuous"), _var("w", scale="continuous"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom("z")],
                "outcome_proxy": [_atom("w")],
                "channel": channel,
            }},
        ],
    }


def _sample(n: int = 4000, seed: int = 11, *, binary: bool) -> pd.DataFrame:
    """A latent-confounded SCM whose bridge is linear in ``w``."""
    rng = np.random.default_rng(seed)
    u = rng.normal(size=n)
    x = ((rng.random(n) < 1 / (1 + np.exp(-0.8 * u))).astype(float) if binary
         else 0.7 * u + rng.normal(scale=0.8, size=n))
    return pd.DataFrame({
        "x": x,
        "y": 1.5 * x + 1.0 * u + rng.normal(scale=0.5, size=n),
        "z": 1.2 * u + rng.normal(scale=0.7, size=n),
        "w": 0.9 * u + rng.normal(scale=0.7, size=n),
    })


@pytest.fixture(scope="module")
def contrast() -> dict:
    return themis.estimate(_program(binary=True), _sample(binary=True),
                           ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def curve() -> dict:
    return themis.estimate(_program(binary=False), _sample(binary=False),
                           ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def two_bridges() -> dict:
    """An answer whose record carries both rosters of arms."""
    program = _program(binary=True, treatment_bridge=True)
    return themis.estimate(program, _sample(binary=True),
                           ci_bootstrap=0)["results"][0]


def _plain(node):
    """The record with its container wrappers taken off.

    The envelope files every nested record as ``{"items": ..., "kind":
    ...}``; the rules read the decoded chain, so a test handing one of
    them a record has to take the wrappers off first.
    """
    if isinstance(node, dict):
        if set(node) <= {"items", "kind"} and "items" in node:
            return _plain(node["items"])
        return {k: _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    return node


def _channel(result: dict) -> dict:
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step["inputs"]["measurement_channel"]["items"]
    raise AssertionError(f"no {_STEP} step in this derivation")


def _forged(result: dict):
    bad = copy.deepcopy(result)
    return bad, _channel(bad)


def _refused(program: dict, bad: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program, bad)
    return str(raised.value)


def _matrix(block: dict, name: str) -> list:
    return block[name]["items"]


def _as_array(block: dict, name: str) -> np.ndarray:
    raw = block[name]["items"]
    if raw and isinstance(raw[0], dict):
        return np.array([row["items"] for row in raw], dtype=float)
    return np.array(raw, dtype=float)


def _still_a_gram(block: dict) -> bool:
    """Whether a forged arm is still inside the cone.

    Used to say which tests are about the identities and which are about
    the arithmetic: an edit this returns True for is one no identity can
    refuse, so a refusal of it comes from somewhere else.
    """
    s_bb = _as_array(block, "s_bb")
    s_by = _as_array(block, "s_by")
    yy = float(block["yy"])
    if not np.allclose(s_bb, s_bb.T, rtol=1e-9, atol=1e-12):
        return False
    d = s_bb.shape[0]
    joint = np.zeros((d + 1, d + 1))
    joint[:d, :d] = s_bb
    joint[:d, d] = joint[d, :d] = s_by
    joint[d, d] = yy
    return bool(np.linalg.eigvalsh((joint + joint.T) / 2).min() >= -1e-9)


# --- the denominator ----------------------------------------------------

def test_a_truthful_contrast_verifies(contrast):
    assert contrast["status"] == "numerically_solved"
    themis.verify(_program(binary=True), contrast)


def test_a_truthful_curve_verifies(curve):
    assert curve["status"] == "numerically_solved"
    themis.verify(_program(binary=False), curve)


def test_the_record_carries_what_this_file_is_about(contrast):
    """A scan reaching nothing would make every test below vacuous."""
    channel = _channel(contrast)
    assert isinstance(channel.get("standard_error"), float)
    arms = [k for k in ("treated", "control", "joint")
            if isinstance(channel.get(k), dict)]
    assert arms == ["control", "treated"] or arms == ["treated", "control"]
    for arm in arms:
        block = channel[arm]["items"]
        assert set(block) >= set(_SECOND_STAGE) | {"n", "s_aa", "s_ab", "s_ay"}


def test_every_arm_the_record_names_is_asked(contrast, curve):
    """Which arms exist is read off the record rather than listed here, so
    a regime that grows a third arm fails here instead of shipping with
    one nothing reads."""
    for result in (contrast, curve):
        channel = _channel(result)
        arms = [k for k, v in channel.items()
                if isinstance(v, dict) and "s_bb" in v.get("items", {})]
        assert arms, "no arm on this record carries second moments"
        for arm in arms:
            block = channel[arm]["items"]
            for name in _SECOND_STAGE:
                assert name in block


# --- the identities a Gram matrix cannot escape -------------------------

def test_an_off_diagonal_moved_alone_is_not_a_second_moment(contrast):
    """The sharp one. MᵀM/n is symmetric whatever the data were, so one
    cell moved on its own is refused by arithmetic and not by comparison."""
    bad, channel = _forged(contrast)
    block = channel["treated"]["items"]
    rows = _matrix(block, "s_bb")
    assert len(rows) >= 2
    rows[0]["items"][1] = rows[0]["items"][1] + 1.0
    said = _refused(_program(binary=True), bad)
    assert "symmetric" in said


def test_a_negative_diagonal_is_not_a_second_moment(contrast):
    bad, channel = _forged(contrast)
    rows = _matrix(channel["control"]["items"], "s_bb")
    rows[0]["items"][0] = -abs(rows[0]["items"][0]) - 1.0
    said = _refused(_program(binary=True), bad)
    assert "positive semidefinite" in said or "eigenvalue" in said


def test_an_outcome_moment_below_what_its_span_explains(contrast):
    """``yy`` shrunk until the span would explain more of Y than Y has:
    the joint block leaves the cone and its Schur complement, which is a
    variance, goes below zero."""
    bad, channel = _forged(contrast)
    block = channel["treated"]["items"]
    block["yy"] = float(block["yy"]) / 100.0
    said = _refused(_program(binary=True), bad)
    assert ("eigenvalue" in said or "residual variance" in said
            or "below zero" in said)


# --- and why the identities are not the whole of it ---------------------

@pytest.mark.parametrize("which", _SECOND_STAGE)
def test_a_block_bent_inside_the_cone_is_still_refused(contrast, which):
    """The point of the whole rule.

    A diagonal made larger, a coefficient halved, an outcome moment
    tripled — none of these leaves the cone, so no identity can refuse
    them. Each moves the standard error, and the standard error is now
    re-derived from exactly these blocks rather than read off the
    envelope. So the test asserts both halves: that the forged record is
    still a legitimate block of second moments, and that it is refused
    anyway.
    """
    bad, channel = _forged(contrast)
    block = channel["treated"]["items"]
    if which == "yy":
        block["yy"] = float(block["yy"]) * 3.0 + 1.0
    elif which == "s_by":
        block["s_by"]["items"] = [v / 2.0 for v in block["s_by"]["items"]]
    else:
        rows = _matrix(block, "s_bb")
        for i, row in enumerate(rows):
            row["items"][i] = row["items"][i] * 3.0 + 1.0
    assert _still_a_gram(block), (
        "this edit was meant to stay inside the cone; if it does not, the "
        "test is measuring an identity rather than the arithmetic"
    )
    said = _refused(_program(binary=True), bad)
    assert "standard error" in said


def test_the_standard_error_itself_is_held(contrast):
    bad, channel = _forged(contrast)
    channel["standard_error"] = float(channel["standard_error"]) * 2.0
    said = _refused(_program(binary=True), bad)
    assert "standard error" in said


# --- the rows -----------------------------------------------------------

def test_an_arm_that_lost_rows_is_refused(contrast):
    bad, channel = _forged(contrast)
    block = channel["treated"]["items"]
    block["n"] = int(block["n"]) - 1
    said = _refused(_program(binary=True), bad)
    assert "add to it" in said or "rows" in said


def _two_rosters(bridge: dict) -> dict:
    return {"n_total": 100,
            "treated": {"n": 60, "s_aa": ()}, "control": {"n": 40, "s_aa": ()},
            "treatment_bridge": bridge}


#: The treatment bridge's two spellings. A contrast writes its arms beside
#: each other under their own names; a curve keys them by level in an
#: ``arms`` table. Both are here because naming one of them is what left
#: four row counts unheld: the rule looked for ``arms``.
_SPELLINGS = {
    "beside each other": {"treated": {"n": 30, "gg": ()},
                          "control": {"n": 70, "gg": ()}},
    "keyed by level": {"arms": {"0.0": {"n": 30, "gg": ()},
                                "1.0": {"n": 70, "gg": ()}}},
}


@pytest.mark.parametrize("spelling", sorted(_SPELLINGS))
def test_the_two_rosters_add_up_separately(spelling):
    """A channel whose outcome arms and whose treatment arms each cover
    the sample is honest. Added together they would come to twice it, and
    a rule that added them would refuse every honest record carrying
    both."""
    bridge = copy.deepcopy(_SPELLINGS[spelling])
    channel = _two_rosters(bridge)
    _bridge_sample_adds_up(channel, "rule", 0)
    arm = (bridge["arms"]["1.0"] if "arms" in bridge else bridge["control"])
    arm["n"] = 69
    with pytest.raises(RuleCheckFailed, match="treatment bridge"):
        _bridge_sample_adds_up(channel, "rule", 0)


def test_an_arm_is_found_by_what_it_is(two_bridges):
    """Not by the word above it. A record carrying its own cross-moments
    and its own row count is an arm, whatever it is filed under, so the
    regime that keys them by level and the regime that writes them side
    by side are one reading and a third spelling arrives already held."""
    channel = _channel(two_bridges)
    bridge = channel["treatment_bridge"]
    found = _bridge_treatment_arms(_plain(bridge))
    assert found, "the treatment bridge's arms were not found at all"
    assert all(isinstance(a.get("n"), int) for a in found)
    assert sum(a["n"] for a in found) == channel["n_total"]


def test_a_second_roster_that_lost_a_row_is_refused(two_bridges):
    bad, channel = _forged(two_bridges)
    arms = [v["items"] for k, v in channel["treatment_bridge"]["items"].items()
            if isinstance(v, dict) and "gg" in v.get("items", {})]
    assert arms, "no treatment arm on this record"
    arms[0]["n"] = int(arms[0]["n"]) - 1
    said = _refused(_program(binary=True, treatment_bridge=True), bad)
    assert "treatment bridge" in said


# --- the curve ----------------------------------------------------------

def test_a_curve_carries_one_standard_error_per_level(curve):
    channel = _channel(curve)
    said = channel.get("standard_errors")
    assert isinstance(said, dict) and "items" in said
    assert len(said["items"]) == len(channel["levels"]["items"])


def test_a_curves_standard_error_is_re_derived(curve):
    bad, channel = _forged(curve)
    errors = channel["standard_errors"]["items"]
    errors[0] = float(errors[0]) * 2.0 + 1.0
    said = _refused(_program(binary=False), bad)
    assert "standard error" in said


def test_a_curves_outcome_moment_is_held(curve):
    bad, channel = _forged(curve)
    block = channel["joint"]["items"]
    block["yy"] = float(block["yy"]) * 3.0 + 1.0
    assert _still_a_gram(block)
    said = _refused(_program(binary=False), bad)
    assert "standard error" in said
