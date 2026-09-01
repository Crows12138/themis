"""The transported effect was a number nothing re-derived.

Transport reweights a source population's strata by the target's covariate
distribution: the answer is Σ_z P*(z)·[E(Y|X=1,z) − E(Y|X=0,z)]. The route
attaches that number to a result whose derivation ends at
``identify_via_transport`` and appends no step of its own, so the rule that
holds a reader's copy to the record had no record to hold it against.

**A comparison with nothing to compare is silent, and at a door silence is
indistinguishable from finding nothing wrong.** Measured end to end before
this file existed: a transported effect of 0.4106 shown as 2.23, as −1.41,
and as 0.0, each accepted by ``themis.verify``.

Where the bootstrap produced an interval, #520's width-relative-to-effect
ratio caught a LONE point edit as a side effect — but only there, only
against the interval, and not at all against a forger who moves both. The
answer the suite's own transport program produces carries no interval, and
so was held by nothing whatever.

What closes it is not a second implementation. There is nothing to be
independent OF: the estimand's definition is restated over statistics the
producer now records, one entry per target-marginal cell.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.transport import estimate_transport
from themis.verifier import verify_post_stratification
from themis.verifier.errors import VerificationError

def _atom(predicate):
    return {"predicate": predicate,
            "args": [{"type": "const", "name": "me"}]}


def _cause(source, target):
    return {"kind": "cause", "from": _atom(source), "to": _atom(target)}


#: A trial that measured Z, and a target population whose Z distribution the
#: caller declares. The selection node is what makes this a transport rather
#: than an ordinary back-door question.
PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        _cause("z", "x"), _cause("z", "y"), _cause("x", "y"),
        {"kind": "selection_node", "id": "s_z", "affects": _atom("z"),
         "source_population": "trial", "target_population": "user"},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "given": [],
            "target": {"atom": _atom("y"), "value": True},
            "intervention": {"atom": _atom("x"), "value": True},
            "target_population": "user"}},
    ],
    "extensions": {
        "target_marginal": {"predicate": "z",
                            "marginal": {"true": 0.7, "false": 0.3}},
    },
}


def _sample(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.4
    x = rng.random(n) < (0.3 + 0.4 * z)
    y = 1.0 + 2.0 * x + 3.0 * z + 1.5 * x * z + rng.normal(0, 1.0, n)
    return pd.DataFrame({"z": z, "x": x, "y": y})


@pytest.fixture(scope="module")
def answer():
    out = themis.estimate(PROGRAM, _sample())
    result = out["results"][0]
    assert result["numeric_estimate"]["method"] == \
        "transport_post_stratification"
    return result


def _bend(answer, path, value):
    bad = copy.deepcopy(answer)
    node = bad["numeric_estimate"]
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


# ============================================================ honest first


def test_the_honest_answer_passes(answer):
    """First, because a forgery refused by a broken producer proves
    nothing."""
    themis.verify(PROGRAM, answer)


def test_the_answer_is_the_sum_the_reader_can_check(answer):
    """The strata reach the envelope, and adding them up by hand gives the
    number shown. Done here with the arithmetic spelled out, so this file
    disagrees with the rule if either drifts."""
    estimate = answer["numeric_estimate"]
    rows = estimate["post_stratification"]
    assert len(rows) == 2
    total = sum(
        row["probability"] * (row["sum_treated"] / row["n_treated"]
                              - row["sum_control"] / row["n_control"])
        for row in rows
    )
    assert total == pytest.approx(estimate["point"], abs=1e-9)
    assert sum(r["probability"] for r in rows) == pytest.approx(1.0)


# ================================================= the answer, and moving it


@pytest.mark.parametrize("factor", [3.0, -1.0, 0.0, 1.000_1])
def test_the_transported_effect_can_no_longer_be_any_number(answer, factor):
    """The whole of it. Every one of these passed the public door.

    The last is a nudge rather than a rewrite, and it is the one that shows
    this rule is doing the work: it sits inside the tolerance of the
    width-relative-to-effect ratio that incidentally caught the others.
    """
    shown = answer["numeric_estimate"]["point"]
    with pytest.raises(VerificationError):
        themis.verify(PROGRAM, _bend(answer, ("point",), shown * factor))


@pytest.mark.parametrize("leaf,value", [
    ("probability", 0.9),
    ("n_treated", 11),
    ("n_control", 11),
    ("sum_treated", 0.0),
    ("sum_control", 0.0),
])
def test_moving_what_the_answer_is_a_sum_over_is_refused(answer, leaf, value):
    """The mirror. Either side breaks the identity, which is what makes it
    an identity rather than a copy of one side — a forger who edits the
    statistics to fit an edited answer has to edit both consistently, and
    then the arithmetic is simply true."""
    with pytest.raises(VerificationError, match="producer's word twice"):
        themis.verify(PROGRAM,
                      _bend(answer, ("post_stratification", 0, leaf), value))


def test_a_relabelled_stratum_lands_on_a_cell_already_taken(answer):
    """Which cell a row describes is the one thing the sum does not read:
    relabel two rows and the arithmetic is untouched while a reader sees
    the target's weight for one stratum against another's numbers. Held to
    what survives with no record to check against."""
    bad = copy.deepcopy(answer)
    rows = bad["numeric_estimate"]["post_stratification"]
    rows[0]["values"] = dict(rows[1]["values"])
    with pytest.raises(VerificationError, match="already"):
        verify_post_stratification(bad)


def test_a_stratum_over_variables_this_answer_did_not_adjust_for(answer):
    """A row's coordinates are the variables adjusted for. Renaming one
    changes no number and changes which population the weight describes."""
    bad = copy.deepcopy(answer)
    row = bad["numeric_estimate"]["post_stratification"][0]
    row["values"] = {"not_z": next(iter(row["values"].values()))}
    with pytest.raises(VerificationError, match="adjusts for"):
        verify_post_stratification(bad)


def test_weights_that_do_not_describe_a_whole_population_are_refused(answer):
    """Two weights moved against each other leave the sum alone. A target
    marginal is a distribution, and this is what says so — an independent
    constraint rather than a second reading of the same one."""
    bad = copy.deepcopy(answer)
    rows = bad["numeric_estimate"]["post_stratification"]
    assert sum(r["probability"] for r in rows) == pytest.approx(1.0)
    for row in rows:
        row["probability"] /= 2
    with pytest.raises(VerificationError, match="whole population"):
        verify_post_stratification(bad)


def test_an_answer_that_records_no_strata_is_refused_not_skipped(answer):
    """The state this rule exists to make impossible to be in silently.

    Before the producer recorded anything, EVERY transported answer was in
    it, and the door said nothing. So the absence has to be the refusal
    rather than the exit — otherwise deleting one key restores the hole
    exactly.
    """
    bad = copy.deepcopy(answer)
    bad["numeric_estimate"].pop("post_stratification")
    with pytest.raises(VerificationError, match="re-derive it"):
        verify_post_stratification(bad)


def test_a_stratum_with_an_empty_arm_is_refused_rather_than_divided_by(
        answer):
    """A contrast that cannot have been taken. The estimator refuses this
    before it can reach an answer, so meeting it here means the record was
    edited — and dividing would raise where the reader deserves a
    sentence."""
    bad = copy.deepcopy(answer)
    bad["numeric_estimate"]["post_stratification"][0]["n_treated"] = 0
    with pytest.raises(VerificationError, match="empty arm"):
        verify_post_stratification(bad)


# ================================================================ denominator


def test_an_answer_of_another_method_is_left_alone():
    """The rule reads one method's block and must be silent everywhere
    else, or every other estimator would be refused for not carrying a
    stratum table it has no reason to have."""
    verify_post_stratification(
        {"numeric_estimate": {"method": "backdoor_linear", "point": 1.0}})
    verify_post_stratification({"numeric_estimate": {}})
    verify_post_stratification({})


def test_the_strata_account_for_no_more_units_than_the_run_has(answer):
    """Not equality: a target marginal names the cells it weights, and a
    source may hold rows in strata it never mentions. More units inside the
    strata than in the whole run is the direction that cannot happen."""
    estimate = answer["numeric_estimate"]
    counted = sum(r["n_treated"] + r["n_control"]
                  for r in estimate["post_stratification"])
    assert counted <= estimate["sample_size"]
    bad = copy.deepcopy(answer)
    bad["numeric_estimate"]["sample_size"] = 3
    with pytest.raises(VerificationError, match="account for"):
        verify_post_stratification(bad)


def test_the_estimator_records_one_entry_per_declared_cell():
    """Read off the estimator directly, so the envelope's shape is held to
    the target marginal rather than to whatever the dispatch copied."""
    est = estimate_transport(
        _sample(), treatment="x", outcome="y", adjustment=("z",),
        target_marginal={"predicate": "z", "marginal": {True: 0.7,
                                                        False: 0.3}},
        ci_bootstrap=0, ci_level=0.95, random_state=1,
    )
    assert len(est.strata) == 2
    assert {row["probability"] for row in est.strata} == {0.7, 0.3}
    for row in est.strata:
        assert row["n_treated"] > 0 and row["n_control"] > 0
