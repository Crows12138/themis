# -*- coding: utf-8 -*-
"""The two channels that price somebody else's interval, and the premise
they file about the variance that price came from.

Both blocks read a declared variance, turn it into a share of the residual,
and report the factor every least-squares interval on that design is wider
by. Where a validation study measured that variance the factor stops being
one number: σ² = σ̂²·df/χ²_df makes it ``1/√(1 − share·df/X)``, and the
endpoints are exact quantiles of the study's own χ². That is already done
and audited.

What was not done is the sentence beside it. Both routes wrote the
"σ² is known and fixed" premise unconditionally, so a run whose factor had
just been widened by the study's uncertainty told its reader, on the ledger
line under the number, that the study's uncertainty was NOT propagated —
and sent them to the design-side family to find a route that already ran
here. The interval is the same two numbers on the page either way, so the
premise was the only thing that could have said so, and it said the
opposite.

This file pins the pair as ONE fact in three places: the id the run
declares, the interval the block reports, and the rule that keeps the two
from drifting apart again.
"""
from __future__ import annotations

import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.berkson import assess_berkson_error
from themis.estimation.dispatch import _berkson_block, _outcome_error_block
from themis.estimation.outcome_error import assess_outcome_error
from themis.ledger import Layer
from themis.output import assumption_glossary as glossary
from themis.verifier.berkson_rules import verify_berkson_error
from themis.verifier.errors import VerificationError
from themis.verifier.outcome_error_rules import verify_outcome_error

BETA_X = 0.8
SIGMA2_V = 0.3
SIGMA2_U = 0.5
DF = 24

#: The two ways one declaration can be settled, as they read at the tail of
#: a premise id.
EXACT = "_known_and_fixed_on_"
STUDIED = "_from_a_validation_study_on_"


# --- the two channels, each built through its own producer --------------------


def _outcome_frame(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 1, n)
    y = BETA_X * x + 0.4 * z + rng.normal(0, 1, n)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _berkson_frame(n=20_000, seed=0):
    """W is the NOMINAL value and the truth scatters around it."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    w = 0.6 * z + rng.normal(0, 1, n)
    x_true = w + rng.normal(0, np.sqrt(SIGMA2_U), n)
    y = 1.0 + BETA_X * x_true + 0.4 * z + rng.normal(0, 1.0, n)
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _slope(df, treatment, adjustment):
    design = np.column_stack(
        [np.ones(len(df))] + [df[c].to_numpy(float)
                              for c in (treatment, *adjustment)])
    return float(np.linalg.lstsq(design, df["y"].to_numpy(float),
                                 rcond=None)[0][1])


def _declared(value, df):
    """A bare number means exact; a spec with a df means a study measured it."""
    return value if df is None else {"error_variance": value,
                                     "validation_df": df}


def _outcome(df=None):
    frame = _outcome_frame()
    assessment = assess_outcome_error(
        frame, treatment="x", outcome="y", adjustment=("z",),
        error_variance=_declared(SIGMA2_V, df))
    block = _outcome_error_block(assessment, source=None)
    return assessment, {
        "outcome_error": block,
        "numeric_estimate": {"method": "backdoor_linear", "outcome": "y",
                             "adjustment": ["z"], "point": BETA_X},
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in assessment.assumptions]}},
    }


def _berkson(df=None):
    frame = _berkson_frame()
    assessment = assess_berkson_error(
        frame, treatment="w", outcome="y", adjustment=("z",),
        treatment_coefficient=_slope(frame, "w", ("z",)),
        error_variance=_declared(SIGMA2_U, df))
    block = _berkson_block(assessment)
    return assessment, {
        "berkson_error": block,
        "numeric_estimate": {"method": "backdoor_linear", "outcome": "y",
                             "point": block["treatment_coefficient"]},
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in assessment.assumptions]}},
    }


#: One row per channel: how to build it, which key holds its block, which
#: column the premise is about, which family the id begins with, and the
#: audit that reads it. Parametrising on this rather than writing each
#: channel's tests twice is the point — the two are one behaviour, and a
#: test written once per channel is where they last drifted apart.
CHANNELS = (
    pytest.param(_outcome, "outcome_error", "y", "outcome_error_variance",
                 verify_outcome_error, id="outcome"),
    pytest.param(_berkson, "berkson_error", "w", "berkson_scatter_variance",
                 verify_berkson_error, id="berkson"),
)


# --- the id follows the declaration -------------------------------------------


@pytest.mark.parametrize("build,key,column,family,audit", CHANNELS)
@pytest.mark.parametrize("df", (None, DF))
def test_the_id_says_which_of_the_two_ways_the_variance_was_settled(
    build, key, column, family, audit, df,
):
    """A bare number files the exact-value premise; a declared study files
    the other one. They are different CLAIMS — the second rests on the
    degrees of freedom being right and on the replicate errors being normal,
    neither of which the first needs — so they are different ids."""
    assessment, _envelope = build(df)
    tail = EXACT if df is None else STUDIED
    assert family + tail + column in assessment.assumptions
    # ...and never both. A reader handed the pair cannot tell which interval
    # they are looking at, which is the whole reason there are two ids.
    assert family + (STUDIED if df is None else EXACT) + column not in (
        assessment.assumptions)


@pytest.mark.parametrize("build,key,column,family,audit", CHANNELS)
@pytest.mark.parametrize("df", (None, DF))
def test_the_premise_and_the_factors_interval_are_one_fact(
    build, key, column, family, audit, df,
):
    """The defect, stated without quoting a word of either sentence.

    A factor with endpoints is a factor that priced a study; an id ending in
    ``from_a_validation_study`` says a study was priced. Those are the same
    claim written on two surfaces, and the failure this file exists for was
    them disagreeing — an interval of [1.39, ∞) under a premise saying the
    variance had been taken as exact.
    """
    assessment, envelope = build(df)
    block = envelope[key]
    priced = block["se_inflation_lower"] is not None
    said = any(a.startswith(family) and a.endswith(STUDIED + column)
               for a in assessment.assumptions)
    assert priced == said
    assert priced == (block["validation_df"] is not None)


@pytest.mark.parametrize("build,key,column,family,audit", CHANNELS)
@pytest.mark.parametrize("df", (None, DF))
def test_the_audit_confirms_the_honest_pair(
    build, key, column, family, audit, df,
):
    _assessment, envelope = build(df)
    audit(envelope)


# --- and refuses the mirror ---------------------------------------------------


@pytest.mark.parametrize("build,key,column,family,audit", CHANNELS)
@pytest.mark.parametrize(
    "df,swap",
    ((DF, (STUDIED, EXACT)), (None, (EXACT, STUDIED))),
    ids=("study-priced-premise-says-exact", "no-study-premise-claims-one"),
)
def test_the_audit_refuses_a_premise_that_says_the_opposite(
    build, key, column, family, audit, df, swap,
):
    """Both directions, because both are unreadable from the numbers.

    A reader told the study was priced, over a factor that held the variance
    still, is reading protection the interval does not have. The mirror is
    quieter and no better: a factor that did widen, under a premise saying
    it could not have. Neither shows on the page — the endpoints are the
    endpoints either way — so the audit is the only thing that can see it.
    """
    _assessment, envelope = build(df)
    forged = copy.deepcopy(envelope)
    said, instead = swap
    for holder in (forged[key]["assumptions"],):
        holder[:] = [a.replace(said, instead) for a in holder]
    forged["extensions"]["assumption_ledger"]["assumptions"] = [
        {"id": a.replace(said, instead)}
        for a in _assessment.assumptions]
    with pytest.raises(VerificationError, match=family):
        audit(forged)


# --- the reader's side --------------------------------------------------------


@pytest.mark.parametrize("build,key,column,family,audit", CHANNELS)
@pytest.mark.parametrize("df", (None, DF))
def test_both_spellings_reach_the_reader_as_a_sentence(
    build, key, column, family, audit, df,
):
    """An id no row matches keeps ITSELF as the token, which is the honest
    fallback and not an answer: the new premise would arrive on the page as
    ``outcome_error_variance_from_a_validation_study_on_y``. Both spellings
    are worded, and both sit in the confidence layer — on these two channels
    the variance buys width and never moves the point, whichever way it was
    settled."""
    assessment, _envelope = build(df)
    declared = [a for a in assessment.assumptions if a.startswith(family)]
    assert len(declared) == 1
    row = glossary.classify_assumption(declared[0])
    token = row["claim"][0]["token"]
    assert token == family + (EXACT if df is None else STUDIED)
    assert row["claim"][0]["said"] == {"suffix": column}
    assert glossary.layer_of(declared[0]) is Layer.CONFIDENCE


def test_a_run_through_the_front_door_carries_the_studied_premise():
    """End to end, because every layer above was checked in isolation and
    the defect was visible only where they meet: the ledger row a reader is
    handed, from a program and a frame, with nothing hand-built."""
    frame = _outcome_frame(n=6000)
    atom = {"predicate": "x", "args": [{"type": "const", "name": "u"}]}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": atom,
             "to": {"predicate": "y", "args": atom["args"]}},
            {"kind": "cause", "from": {"predicate": "z", "args": atom["args"]},
             "to": atom},
            {"kind": "cause", "from": {"predicate": "z", "args": atom["args"]},
             "to": {"predicate": "y", "args": atom["args"]}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom, "value": True},
                "target": {"atom": {"predicate": "y", "args": atom["args"]},
                           "value": True},
                "given": []}},
        ],
    }
    out = themis.estimate(
        program, frame, ci_bootstrap=0, random_state=1,
        measurement_error={"y": {"error_variance": SIGMA2_V,
                                 "validation_df": DF}})
    result = out["results"][0]
    ledger = result["extensions"]["assumption_ledger"]["assumptions"]
    ids = {str(entry["id"]) for entry in ledger}
    assert "outcome_error_variance_from_a_validation_study_on_y" in ids
    assert "outcome_error_variance_known_and_fixed_on_y" not in ids
    assert result["outcome_error"]["se_inflation_lower"] is not None


# --- what keeps it from drifting apart again ----------------------------------


def _settled_both_ways() -> tuple[str, ...]:
    """Every family the glossary words BOTH ways, read off the glossary.

    Read rather than listed, so the rule below covers a family the day it
    grows its second spelling and not the day somebody remembers to add it
    here. A family with one spelling is one that cannot yet be settled two
    ways — ``differential_coefficient`` is there now — and writing its id by
    hand states a fact rather than making a choice, so it is not in scope
    until the choice exists.
    """
    spelt = [
        {k[: -len(way)] for k in glossary.CLAIMS if k.endswith(way)}
        for way in (EXACT, STUDIED)
    ]
    return tuple(sorted(spelt[0] & spelt[1]))


def _written_by_hand(text: str) -> list[str]:
    """Which two-way premise ids this source spells out for itself."""
    return sorted(
        f"{family}{way}"
        for family in _settled_both_ways()
        for way in (EXACT, STUDIED)
        if f"{family}{way}" in text
    )


ESTIMATION = sorted(
    (pathlib.Path(themis.__file__).parent / "estimation").glob("*.py"))


def test_the_rule_has_something_to_be_about():
    """A scan whose table is empty passes on every source there is."""
    families = _settled_both_ways()
    assert "outcome_error_variance" in families
    assert "berkson_scatter_variance" in families


@pytest.mark.parametrize("path", ESTIMATION, ids=lambda p: p.name)
def test_no_estimator_spells_a_two_way_premise_itself(path):
    """The root, and the reason this is a rule rather than two edits.

    Which of the two spellings a run owes is not a fact about the estimator
    or about the column — it is a fact about the declaration, and the
    declaration is the only object that holds both the value and what
    measured it. An estimator that writes the id itself has taken that
    decision somewhere the declaration cannot reach, and the choice it makes
    there is always the same one: the exact-value premise, because that is
    what the id said before a study could be declared at all. Both channels
    failed exactly this way, silently, for as long as the interval beside
    them was right.
    """
    spelt = _written_by_hand(path.read_text(encoding="utf-8"))
    assert not spelt, (
        f"{path.name} writes {spelt} as a literal. Ask the declaration "
        f"instead — DeclaredVariance.premise(family, column) — so the "
        f"premise and the interval cannot disagree"
    )


def test_the_rule_would_catch_a_site_that_did():
    """The counterexample, so the sweep above is not passing on an empty
    reading of the sources."""
    assert _written_by_hand(
        'known = f"outcome_error_variance_known_and_fixed_on_{outcome}"'
    ) == ["outcome_error_variance_known_and_fixed_on_"]
    assert _written_by_hand(
        '        declared.premise("outcome_error_variance", outcome),'
    ) == []
