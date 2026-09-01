"""An answer from data reaches its reader twice, and only one copy was
audited.

The derivation's terminal step records what the estimator did, and every
rule in the verifier re-derives the answer from THAT record. Beside it
sits ``numeric_estimate``, which is what a reader, the report and the
browser actually read. They are one run written down twice.

Measured on a stratified-Wald answer by perturbing every leaf under
``numeric_estimate`` and running the public door on each: of forty-two,
thirty-eight passed. The stated confidence level, the sample size, every
cell of the stratum table, every endpoint of the confidence set — a
reader could be shown a set stretched to [-99, 99], or a first stage of
0.1 where the run computed a hundred thousand, and the door said the
answer verified. Only the point estimate and the sensitivity block held.

The rule that closes it needs no knowledge of any estimator: a name that
appears on both sides names the same thing. The nested views take one
step more, because a table rendered for a reader is not the flat columns
the step recorded — a prefix for the confidence sets, a written-out map
for the stratum table, and for the three cells the step never recorded,
the arithmetic that ties them to what it did.

THE ORDER IS THE MEANING. This runs after the derivation rules and not
before. Ahead of them it would answer for a tampered derivation before
the rule that re-derives it ever ran, and those rules would go
unexercised at the public door — which the suite said out loud: twenty-two
tests that tamper the record started failing on the wrong refusal.

WHAT REMAINS, MEASURED. Nothing, on this answer shape. One leaf held out
for a while — the first-stage F was not a copy that disagreed with its
record, it was a number with no record at all — and the last test in this
file is what it turned into once the producer gave it one.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import verify_numeric_display_agrees
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# w → z, w → y, z → x, x → y, x ↔ y. z is an instrument only once w is
# held fixed, which is what makes the answer a stratified Wald and gives
# the envelope a stratum table to show.
_P_W1 = 0.4
_STRATA = {True: (0.9, 0.3, 0.7, 0.4), False: (0.6, 0.2, 0.5, 0.2)}
_P_Z_GIVEN_W = {True: 0.5, False: 0.1}

PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        *({"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in ("x", "y", "z", "w")),
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": []}},
    ],
}


def _sample(n=40_000, seed=11):
    rng = np.random.default_rng(seed)
    w = rng.random(n) < _P_W1
    z = rng.random(n) < np.where(w, _P_Z_GIVEN_W[True], _P_Z_GIVEN_W[False])
    p_x, p_y = np.empty(n), np.empty(n)
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        m = (w == wv)
        p_x[m] = np.where(z[m], pxz1, pxz0)
        p_y[m] = np.where(z[m], pyz1, pyz0)
    return pd.DataFrame({"w": w, "z": z,
                         "x": rng.random(n) < p_x, "y": rng.random(n) < p_y})


@pytest.fixture(scope="module")
def answer():
    result = themis.estimate(
        PROGRAM, _sample(), ci_bootstrap=0)["results"][0]
    assert result["numeric_estimate"]["method"] == "iv_stratified_wald"
    return result


def _tamper(answer, path, value):
    r = copy.deepcopy(answer)
    node = r["numeric_estimate"]
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return r


# ============================================================ honest first


def test_the_honest_answer_passes(answer):
    """First, or every refusal below proves nothing."""
    themis.verify(PROGRAM, answer)


# ================================================== the sweep, as the gate


def _leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, path + (i,))
    else:
        yield path, node


def _bend(value):
    """A different value of the same species, inside the range the schema
    plausibly allows. A probability nudged out of [0,1] would be caught by
    the contract for the wrong reason, and a duplicated list or a reversed
    pair is an identity under set comparison — either would report a hole
    as closed."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1 if value >= 0 else value - 1
    if isinstance(value, float):
        return value / 2 + 0.01 if 0.0 < value < 1.0 else value * 1.5 + 0.5
    return None


#: Leaves with no witness on the envelope. Empty, and it was not: the
#: first-stage F used to be here, because it was computed from the raw
#: frame and named in no derivation step. The producer records the moments
#: it is a ratio of now, so it left this set by being closed rather than
#: by being excused — which is the only way anything should leave it.
UNWITNESSED: set = set()


def test_every_leaf_of_the_readers_copy_is_held_to_the_record(answer):
    """The measurement, kept as the gate.

    A list of fields would pass on the day a new one is added beside them;
    this asks the question of whatever the envelope actually carries, so a
    field added without a witness arrives here as a failure with its own
    name in it.
    """
    survived = []
    for path, value in _leaves(answer["numeric_estimate"]):
        bent = _bend(value)
        if bent is None or bent == value:
            continue
        try:
            themis.verify(PROGRAM, _tamper(answer, path, bent))
        except Exception:
            continue
        survived.append(path)
    assert set(survived) == UNWITNESSED, sorted(
        ".".join(map(str, p)) for p in set(survived) ^ UNWITNESSED)


# =========================================== the edits a reader would act on


@pytest.mark.parametrize("path,value", [
    (("ci_level",), 0.5),
    (("sample_size",), 12),
    (("outcome",), "z"),
    (("stratified_anderson_rubin_confidence_set", "lower"), -99.0),
    (("stratified_anderson_rubin_confidence_set", "upper"), 99.0),
    (("stratified_wald", "strata", 0, "weight"), 0.99),
    (("stratified_wald", "outcome_shift"), 0.0),
], ids=["ci_level", "sample_size", "outcome", "set_lower", "set_upper",
        "stratum_weight", "aggregate_shift"])
def test_a_reader_and_an_auditor_are_not_shown_two_different_runs(
        answer, path, value):
    """Seven of the thirty-eight, named because a reader acts on each: the
    confidence level a set is claimed at, the sample it rests on, which
    variable the answer is even about, a confidence set stretched until it
    excludes nothing, a stratum reweighted to nine tenths of the study."""
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, _tamper(answer, path, value))


def test_a_relabelled_stratum_lands_on_a_cell_already_taken(answer):
    """Which cell a row describes is the one thing the step does not
    record, and it says which stratum a reader is looking at. Two rows of
    one table are two different cells, and that survives without a
    record."""
    r = copy.deepcopy(answer)
    rows = r["numeric_estimate"]["stratified_wald"]["strata"]
    rows[0]["values"] = list(rows[1]["values"])
    with pytest.raises(VerificationError, match="already describes"):
        themis.verify(PROGRAM, r)


def test_a_stratum_that_lost_its_units_is_refused(answer):
    """The three cells the step never recorded, held to the arithmetic
    that ties them to what it did: the arms are the whole of the stratum,
    and a weight is that stratum's share of the sample."""
    r = copy.deepcopy(answer)
    row = r["numeric_estimate"]["stratified_wald"]["strata"][0]
    row["n_instrument_high"] = row["n_instrument_high"] + 100
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, r)


# ================================================================ denominator


def test_an_answer_with_nothing_shown_twice_is_left_alone():
    """An answer with no numeric_estimate has no second copy, and a check
    that refused it would refuse everything above for a reason that had
    nothing to do with the copies.

    Asked of the rule rather than through the door, because the door
    declines a derivation-less result before reading any block and the
    shape wanted here is the opposite one: a chain present, a numeric
    estimate absent.
    """
    verify_numeric_display_agrees(
        {"derivation": {"steps": [{"rule": "r", "inputs": {"point": 1.0}}]}},
        {"steps": [{"rule": "r", "inputs": {"point": 1.0}}]})


def test_an_ordinary_backdoor_answer_still_verifies():
    """And the common shape, whose estimate shares half a dozen names with
    its step. A same-name rule that was wrong about any of them would show
    up here rather than on the IV path alone."""
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in ("x", "y", "z")),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }
    rng = np.random.default_rng(3)
    n = 2000
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    frame = pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                          "z": z.astype(bool)})
    res = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    themis.verify(prog, res)
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(prog, _tamper(res, ("outcome",), "z"))


# ================================================= the limit, written down


def test_the_first_stage_f_now_has_a_record_of_its_own(answer):
    """The one leaf this file used to record as unwitnessed.

    The number Stock and Yogo's threshold is applied to was computed from
    the raw frame and named in no derivation step, so nothing had ever
    re-derived it: an F of 0.1 and an F of a hundred thousand were equally
    acceptable. The step records the moments it is a ratio of now, and the
    display copy is held to the record like every other name.
    """
    estimate = answer["numeric_estimate"]
    assert estimate["first_stage_f_stat"] > 10
    inputs = answer["derivation"]["steps"][-1]["inputs"]
    assert {"first_stage_f_stat", "first_stage_s_zz", "first_stage_s_zx",
            "first_stage_s_xx", "first_stage_n_obs",
            "first_stage_n_exog"} <= set(inputs)
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, _tamper(answer, ("first_stage_f_stat",), 0.1))
