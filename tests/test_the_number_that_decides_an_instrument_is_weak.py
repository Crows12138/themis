"""The first-stage F was computed from the data and re-derived by nothing.

Stock and Yogo's threshold is applied to one number, and a reader consults
it to decide whether an instrument is weak enough that the point estimate
should not be trusted at all. It was computed from the raw frame, written
onto the envelope, and named in no derivation step — so no rule could
re-derive it, and none did. An F of 0.1 and an F of a hundred thousand
were equally acceptable to the public door.

Not a display copy that disagreed with its record: a number with no
record. The producer now records the residualised second moments of (Z, X)
after the exogenous block, which are sufficient for the statistic, and two
routes reach it — the producer forms it from two sums of squares, the
verifier from the moments. Sharing the arithmetic would make the two sides
agree by construction, which is a check that cannot fail.

The over-identified path needed nothing recorded: its joint F is a
q-restriction test over the moment matrices the Sargan statistic already
rests on, so the same number was derivable there all along and simply was
not derived.

WHAT IS STILL TRUSTED. The moments themselves, as everywhere in this
package: recounting them needs the frame. What that leaves a forger is a
whole regression to move consistently — and on the just-identified path
the Anderson-Rubin set records the same three numbers, so the confidence
set has to move with it.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(instruments, *, conditioning=()):
    names = (*instruments, "x", "y", *conditioning)
    stmts = [{"kind": "variable", "predicate": p, "scale": "continuous"}
             for p in names]
    stmts += [{"kind": "cause", "from": _atom(z), "to": _atom("x")}
              for z in instruments]
    stmts += [
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    ]
    for w in conditioning:
        stmts += [{"kind": "cause", "from": _atom(w), "to": _atom(z)}
                  for z in instruments]
        stmts.append({"kind": "cause", "from": _atom(w), "to": _atom("y")})
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": 1.0},
        "target": {"atom": _atom("y"), "value": 1.0}, "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _frame(n=4000, seed=7, *, strength=0.8, instruments=("z",),
           conditioning=()):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    cols = {}
    for w in conditioning:
        cols[w] = rng.standard_normal(n)
    shift = sum(0.5 * cols[w] for w in conditioning) if conditioning else 0.0
    zs = []
    for z in instruments:
        cols[z] = shift + rng.standard_normal(n)
        zs.append(cols[z])
    x = strength * sum(zs) + 0.9 * u + 0.4 * rng.standard_normal(n)
    y = 1.1 * x + 1.4 * u + 0.5 * rng.standard_normal(n)
    if conditioning:
        y = y + sum(0.6 * cols[w] for w in conditioning)
    cols["x"], cols["y"] = x, y
    return pd.DataFrame(cols)


JUST = _program(("z",))
OVERID = _program(("z1", "z2", "z3"))


@pytest.fixture(scope="module")
def just():
    return themis.estimate(JUST, _frame(), ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def overid():
    frame = _frame(instruments=("z1", "z2", "z3"), strength=0.6, seed=3)
    return themis.estimate(OVERID, frame, ci_bootstrap=0)["results"][0]


def _inputs(result):
    return result["derivation"]["steps"][-1]["inputs"]


# ================================================================ honest first


def test_the_honest_answers_pass_and_carry_the_record(just, overid):
    """First, or every refusal below proves nothing. The just-identified
    path now records what the F is a ratio of; the over-identified one
    needed nothing new, since its joint F falls out of the moment matrices
    the Sargan statistic already rests on."""
    assert just["numeric_estimate"]["first_stage_f_stat"] > 10
    assert {"first_stage_f_stat", "first_stage_s_zz", "first_stage_s_zx",
            "first_stage_s_xx", "first_stage_n_obs",
            "first_stage_n_exog"} <= set(_inputs(just))
    themis.verify(JUST, just)

    assert overid["numeric_estimate"]["method"] == "iv_2sls_overid"
    assert overid["numeric_estimate"]["first_stage_f_stat"] > 10
    themis.verify(OVERID, overid)


def test_a_conditioned_first_stage_verifies():
    """The degrees of freedom depend on how many columns were partialled
    out, so a design with an exogenous block is its own case — a check
    that had the count wrong would pass on the unconditioned answer above
    and fail here."""
    prog = _program(("z",), conditioning=("w",))
    frame = _frame(instruments=("z",), conditioning=("w",), seed=9)
    res = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    assert _inputs(res)["first_stage_n_exog"] == 1
    themis.verify(prog, res)


# ==================================================== the verdict, forged

def test_the_f_a_reader_is_shown_is_the_one_the_step_recorded(just):
    """Move the envelope's copy alone and the two records disagree."""
    bad = copy.deepcopy(just)
    bad["numeric_estimate"]["first_stage_f_stat"] = 0.1
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(JUST, bad)


def test_a_recorded_f_the_moments_do_not_support_is_refused(just):
    """Move BOTH copies and the display check has nothing to say — which
    is what makes the re-derivation the thing that matters. A weak verdict
    planted on a strong first stage is the edit worth catching."""
    bad = copy.deepcopy(just)
    bad["numeric_estimate"]["first_stage_f_stat"] = 0.1
    _inputs(bad)["first_stage_f_stat"] = 0.1
    with pytest.raises(VerificationError, match="not the one this regression"):
        themis.verify(JUST, bad)


def test_moving_the_moments_instead_is_refused(just):
    """The mirror edit: leave the statistic and rewrite what it was
    computed from."""
    bad = copy.deepcopy(just)
    _inputs(bad)["first_stage_s_zx"] = _inputs(bad)["first_stage_s_zx"] / 8.0
    with pytest.raises(VerificationError, match="not the one this regression"):
        themis.verify(JUST, bad)


@pytest.mark.parametrize("dropped", [
    "first_stage_s_zz", "first_stage_s_zx", "first_stage_s_xx",
    "first_stage_n_obs", "first_stage_n_exog"])
def test_an_f_with_no_statistics_beside_it_is_refused(just, dropped):
    """Each of the five, because a record with a hole in it is the shape
    the whole change exists to prevent — and dropping the one nobody
    thought of is how it would come back."""
    bad = copy.deepcopy(just)
    del _inputs(bad)[dropped]
    with pytest.raises(VerificationError, match="the producer's word alone"):
        themis.verify(JUST, bad)


def test_statistics_with_no_f_to_check_are_refused(just):
    """And the other way round. Statistics recorded so a statistic can be
    checked, with no statistic beside them, are arithmetic with nothing at
    stake."""
    bad = copy.deepcopy(just)
    del bad["numeric_estimate"]["first_stage_f_stat"]
    del _inputs(bad)["first_stage_f_stat"]
    with pytest.raises(VerificationError, match="nothing here to check"):
        themis.verify(JUST, bad)


def test_one_regression_cannot_have_had_two_answers(just):
    """The just-identified path records the same three moments twice — once
    for the first stage, once for the Anderson-Rubin set. Neither audits
    the other's arithmetic; what the pair buys is that a forger who moves
    the first stage has to move the confidence set with it."""
    bad = copy.deepcopy(just)
    inputs = _inputs(bad)
    factor = 4.0
    inputs["first_stage_s_zz"] = inputs["first_stage_s_zz"] * factor
    inputs["first_stage_s_zx"] = inputs["first_stage_s_zx"] * factor
    inputs["first_stage_s_xx"] = inputs["first_stage_s_xx"] * factor
    inputs["first_stage_f_stat"] = inputs["first_stage_f_stat"]
    bad["numeric_estimate"]["first_stage_f_stat"] = \
        inputs["first_stage_f_stat"]
    with pytest.raises(VerificationError,
                       match="cannot have had two answers"):
        themis.verify(JUST, bad)


def test_the_joint_f_of_an_over_identified_system_is_re_derived(overid):
    """Three instruments, one F, and the moments were already recorded —
    this number was derivable all along and simply was not derived."""
    bad = copy.deepcopy(overid)
    bad["numeric_estimate"]["first_stage_f_stat"] = 0.4
    with pytest.raises(VerificationError,
                       match="not the one these moments support"):
        themis.verify(OVERID, bad)


# ================================================================ denominator


def test_an_honestly_weak_instrument_still_verifies():
    """The denominator, and the one a check written as "F must be large"
    would fail. A weak first stage is an honest answer about a hard
    design; what is audited is that the number is the number, not that a
    reader will like it."""
    prog = _program(("z",))
    frame = _frame(strength=0.02, seed=11)
    res = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    f = res["numeric_estimate"]["first_stage_f_stat"]
    assert f < 10, f
    themis.verify(prog, res)
