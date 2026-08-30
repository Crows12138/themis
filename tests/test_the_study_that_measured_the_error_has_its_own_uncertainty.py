# -*- coding: utf-8 -*-
"""A correction rests on σ²_u, and somebody had to measure σ²_u too.

Every measurement-error correction in this package takes a variance from
outside the sample, because nothing inside the sample can estimate it. Where
that number came from a validation substudy it is an ESTIMATE, and an
interval computed with it held fixed prices the main sample's uncertainty and
nothing else. Measured at a true βx = 0.8, n = 800, σ²_u = 0.5 estimated on
24 degrees of freedom, over 120 samples in which the analyst is handed σ̂²
rather than σ²:

    σ²_u held fixed   coverage 0.525    median width 0.195
    σ²_u redrawn      coverage 0.958    median width 0.826

A nominal-95% interval covering half the time is the whole defect in one
number, and no amount of main-sample data fixes it — the missing variation is
in a study the main sample never saw.

**A missing slot, not a missing calculation.** ``error_variance`` was typed
``float``, and a float holds one point value, so "how well is this number
known" had nowhere to be said: no sibling key on the spec, no parameter on
the estimator, no distribution in the bootstrap, nothing for a verifier to
check. ``DeclaredVariance`` is the slot; the χ² redraw is what fills it.

The three groups below are the three claims: the interval carries the second
study, the declaration is judged rather than believed, and the artifact says
which of the two runs a reader is looking at.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.differential_error import estimate_differential_error
from themis.estimation.regression_calibration import (
    estimate_regression_calibration,
)
from themis.estimation.resample import DeclaredVariance
from themis.input.syntactic_validator import validate_result
from themis.output.assumption_glossary import (
    classify_assumption,
    is_classified,
)
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.differential_error_rules import (
    verify_differential_error_numeric,
)
from themis.verifier.errors import VerificationError

BETA = 0.8
SIGMA2 = 0.5
KNOWN = "design_error_variance_known_and_fixed_on_"
STUDIED = "design_error_variance_from_a_validation_study_on_"


# --- data ---------------------------------------------------------------------


def _frame(seed=11, n=4000, sigma2=SIGMA2):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + BETA * x + 0.4 * z + rng.normal(0, 1, n)
    return pd.DataFrame({"w": x + rng.normal(0, np.sqrt(sigma2), n),
                         "y": y, "z": z})


def _fit(declared, *, frame=None, bootstrap=200, seed=7):
    return estimate_regression_calibration(
        frame if frame is not None else _frame(),
        treatment="w", outcome="y", adjustment=("z",),
        error_variance={"w": declared},
        ci_bootstrap=bootstrap, random_state=seed)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    """W→Y + Z→W + Z→Y back door, exposure W measured with noise."""
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": [
                {"kind": "variable", "predicate": "w",
                 "measurement": "single-occasion continuous measurement"},
                {"kind": "variable", "predicate": "y"},
                {"kind": "variable", "predicate": "z"},
                {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("w")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("w"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}}]}


def _run(spec, *, frame=None, variable="w", bootstrap=60):
    return themis.estimate(
        _program(), frame if frame is not None else _frame(),
        ci_bootstrap=bootstrap, random_state=7,
        measurement_error={variable: spec})["results"][0]


def _refusal(result: dict) -> dict:
    block = result.get("estimator_failure")
    assert isinstance(block, dict), (
        f"expected a recorded refusal; the result carries {sorted(result)}")
    return block


# --- 1. the interval carries the second study ---------------------------------


def test_a_fixed_variance_undercovers_and_a_redrawn_one_does_not():
    """The defect and the fix, measured on the same 120 samples.

    The analyst is handed σ̂², a draw from the validation study — not σ². That
    is what makes the fixed-variance interval fail: it is centred on a number
    that is itself off, and its width knows nothing about how far off.
    """
    reps, df, n = 120, 24, 800
    caught = {"fixed": 0, "redrawn": 0}
    for label, wrap in (("fixed", lambda h: h),
                        ("redrawn", lambda h: DeclaredVariance(h, df))):
        for s in range(reps):
            rng = np.random.default_rng(1000 + s)
            z = rng.normal(0, 1, n)
            x = 0.6 * z + rng.normal(0, 1, n)
            y = 1.0 + BETA * x + 0.4 * z + rng.normal(0, 1, n)
            hat = SIGMA2 * rng.chisquare(df) / df
            frame = pd.DataFrame(
                {"w": x + rng.normal(0, np.sqrt(SIGMA2), n), "y": y, "z": z})
            est = _fit(wrap(hat), frame=frame, seed=1000 + s)
            if est.ci_lower is not None and est.ci_lower <= BETA <= est.ci_upper:
                caught[label] += 1

    assert caught["fixed"] / reps < 0.80, (
        "holding a validation-study variance fixed is supposed to undercover "
        f"badly at df={df}; it covered {caught['fixed']}/{reps}"
    )
    assert caught["redrawn"] / reps > 0.90, (
        "redrawing σ²_u from its own sampling distribution is supposed to "
        f"restore nominal coverage; it covered {caught['redrawn']}/{reps}"
    )


@pytest.mark.parametrize("df", [9, 24, 99])
def test_a_smaller_study_buys_a_wider_interval(df):
    """Monotone in the one thing the caller declares.

    A df is not a switch that widens by a fixed amount — it says how much the
    validation study left undetermined, so a smaller one has to cost more.
    """
    fixed = _fit(SIGMA2)
    studied = _fit(DeclaredVariance(SIGMA2, df))
    looser = _fit(DeclaredVariance(SIGMA2, df * 4))
    width = lambda e: e.ci_upper - e.ci_lower  # noqa: E731
    assert width(studied) > width(fixed)
    assert width(studied) > width(looser), (
        f"df={df} should cost more than df={df * 4}")


def test_the_declaration_moves_the_interval_and_not_the_point():
    """σ²_u enters the correction, so the point is a fact about the number
    itself; the df is a fact about how well the number is known, and a fact
    about knowledge cannot move an estimate."""
    fixed = _fit(SIGMA2)
    studied = _fit(DeclaredVariance(SIGMA2, 24))
    assert studied.point == fixed.point
    assert studied.naive_point == fixed.naive_point
    assert studied.reliability == fixed.reliability
    assert studied.ci_lower != fixed.ci_lower


def test_declaring_no_study_reproduces_the_old_run_exactly():
    """The rng stream, not just the answer.

    ``None`` degrees of freedom is the claim that there is no distribution
    here to draw from, and the draw answers it by consuming no randomness at
    all — so every run that declares nothing is the run it was before this
    class existed, to the last bit.
    """
    bare = _fit(SIGMA2)
    wrapped = _fit(DeclaredVariance(SIGMA2))
    assert (wrapped.ci_lower, wrapped.ci_upper) == (bare.ci_lower, bare.ci_upper)


def test_the_differential_correction_carries_it_too():
    """The second route that redraws, and δ deliberately does not.

    δ's own sampling distribution is not a χ² and nothing here says what it
    is, so it stays fixed while σ²_u is redrawn beside it — widening on a
    distribution nobody stated would be inventing precision, in the direction
    that looks like caution.
    """
    frame = _frame()
    common = dict(treatment="w", outcome="y", adjustment=("z",),
                  differential_by="y", differential_coefficient=0.3,
                  ci_bootstrap=200, random_state=7)
    fixed = estimate_differential_error(frame, error_variance=0.9, **common)
    studied = estimate_differential_error(
        frame, error_variance=DeclaredVariance(0.9, 24), **common)
    assert studied.point == fixed.point
    assert studied.differential_coefficient == fixed.differential_coefficient
    assert (studied.ci_upper - studied.ci_lower) > (
        fixed.ci_upper - fixed.ci_lower)


# --- 2. the declaration is judged, and by one author --------------------------


@pytest.mark.parametrize("given", [0, -1, 2.5, True, "24", float("nan")])
def test_a_df_that_is_not_a_df_is_refused(given):
    """Every shape that is not a positive whole number, including the two a
    permissive check would let through: ``True`` is an ``int`` and 2.5 is a
    ``float``, and neither names a χ² anybody could draw from."""
    with pytest.raises(EstimatorFailure) as exc:
        DeclaredVariance(SIGMA2, given)
    assert exc.value.failure_type == Refusal.NON_POSITIVE_VALIDATION_DF.value


def test_a_whole_number_written_as_a_float_is_a_df():
    """49 from a caller who wrote it in a file arrives as 49.0. Refusing that
    would make one declaration legal at one door and not the other, which is
    a fact about the parser rather than about the study."""
    assert DeclaredVariance(SIGMA2, 49.0).validation_df == 49


def test_the_whole_spec_is_read_for_both_keys_at_once():
    """The number and how well it is known arrive together or the second is
    lost — which is the defect this class exists to close."""
    one = DeclaredVariance.read({"error_variance": 0.5, "validation_df": 24})
    assert (one.value, one.validation_df) == (0.5, 24)
    assert DeclaredVariance.read(0.5).validation_df is None
    assert DeclaredVariance.declared_value({"error_variance": 0.5}) == 0.5
    assert DeclaredVariance.declared_value(DeclaredVariance(0.5)) == 0.5
    assert DeclaredVariance.declared_value(0.5) == 0.5


@pytest.mark.parametrize("given", [-1, 0, "lots", None])
def test_an_unusable_variance_still_leaves_in_the_estimators_own_words(given):
    """A normaliser, not a second adjudicator.

    Whether a declared variance is USABLE is the estimator's judgement, made
    naming the estimator's own variable, and this class must not take it
    over — so whatever shape the declaration arrives in, the refusal the
    caller meets is still the one about their variance, still quoting what
    they wrote. A check here would either duplicate that sentence or replace
    it with one about a shape.
    """
    spec = {"error_variance": given} if given is not None else {}
    block = _refusal(_run(spec))
    assert block["failure_type"] in (
        Refusal.NON_POSITIVE_ERROR_VARIANCE.value,
        Refusal.ARGUMENT_NOT_GIVEN.value,
    )
    if given is not None:
        assert block["details"]["given"] == given
        assert block["details"]["variable"] == "w"


def test_a_spec_that_is_not_one_carries_no_variance_at_all():
    """``None`` and not a guess, because a spec that is not a mapping declares
    nothing — and a default here would be a number the caller never wrote."""
    assert DeclaredVariance.from_spec(4) is None
    assert DeclaredVariance.from_spec(None) is None


def test_the_species_for_a_route_that_could_not_carry_it_is_gone():
    """It was minted here for three routes and outlived all three.

    Its whole content was "no construction here can carry a study", and the
    three that could not carry a DRAW each turned out to carry the study
    another way — SIMEX by reading its fitted curve somewhere else, the two
    pricing blocks by taking the quantiles of the factor they compute. A
    species with no citer is a word no reader can ever meet, so it is
    retired rather than kept against a route that might want it.
    """
    from themis import refusals as r

    assert not hasattr(Refusal, "VALIDATION_DF_NOT_CARRIED_HERE")
    assert "validation_df_not_carried_here" not in {str(s) for s in Refusal}
    assert "validation_df_not_carried_here" not in r.SAYS


def test_a_bad_df_reaches_the_reader_as_a_refusal_and_not_as_a_crash():
    """Where the check runs decides whether anyone can read it.

    The map of declarations is built while a strategy's ARGUMENTS are being
    assembled — before the handler that owns the refusal exists to catch
    anything. A declaration judged there leaves by the exception door, which
    no caller of ``themis.estimate`` reads. So facts describe and handlers
    adjudicate, and this is the counterexample that pins it.
    """
    block = _refusal(_run({"error_variance": 1.0, "validation_df": 0}))
    assert block["failure_type"] == Refusal.NON_POSITIVE_VALIDATION_DF.value
    assert block["estimator"] == "regression_calibration"
    assert block["details"] == {"given": 0}


@pytest.mark.parametrize("species", [Refusal.NON_POSITIVE_VALIDATION_DF])
def test_each_new_species_has_a_sentence_in_both_languages(species):
    from themis import refusals as r
    words = r.SAYS[species.value]
    assert set(words) >= {"zh", "en"}
    assert all(w.strip() for w in words.values())


# --- 3. the artifact says which of the two runs it was ------------------------


def test_the_premise_says_which_way_the_variance_was_declared():
    assert _fit(SIGMA2).assumptions.count(KNOWN + "w") == 1
    studied = _fit(DeclaredVariance(SIGMA2, 24)).assumptions
    assert studied.count(STUDIED + "w") == 1
    assert (KNOWN + "w") not in studied


def test_the_new_premise_is_classified_rather_than_falling_to_the_default():
    """An unclassified id is surfaced with its raw text, which is the
    untranslated identifier the glossary exists to keep off the page.

    ``is_classified`` first, because the default for an id nobody tabled IS
    identification — so comparing layers alone would pass on the day this row
    is deleted, for the reason it exists to prevent.
    """
    assert is_classified(STUDIED + "w")
    entry = classify_assumption(STUDIED + "w")
    known = classify_assumption(KNOWN + "w")
    assert entry["claim"] != known["claim"], (
        "the two are different claims and must reach the reader as different "
        "sentences; sharing one row would make the premise unrefutable "
        "without knowing which half of it applied"
    )
    assert entry["layer"] == known["layer"], (
        "σ²_u still enters the correction when a df is declared, so a wrong "
        "one still moves the point; filing this one under a milder layer "
        "would downgrade the premise for declaring more about it"
    )
    assert entry["testable"] == known["testable"]
    assert entry["claim"], "the premise reaches the reader as words"


def test_the_block_records_the_df_only_when_a_study_declared_one():
    studied = _run({"error_variance": SIGMA2, "validation_df": 24})
    block = studied["numeric_estimate"]["regression_calibration"]
    assert block["validation_df"] == {"w": 24}
    fixed = _run({"error_variance": SIGMA2})
    assert "validation_df" not in (
        fixed["numeric_estimate"]["regression_calibration"])


def test_both_shapes_round_trip_through_the_result_schema():
    for spec in ({"error_variance": SIGMA2},
                 {"error_variance": SIGMA2, "validation_df": 24}):
        validate_result(_run(spec))


def test_the_verifier_accepts_what_the_producer_ships():
    program = _program()
    for spec in ({"error_variance": SIGMA2},
                 {"error_variance": SIGMA2, "validation_df": 24}):
        themis.verify(program, _run(spec))


def _tampered(change):
    """One shipped artifact with one thing about it changed."""
    result = _run({"error_variance": SIGMA2, "validation_df": 24})
    result = copy.deepcopy(result)
    change(result["numeric_estimate"])
    return result


@pytest.mark.parametrize("name,change", [
    ("the df is dropped and the premise is not",
     lambda e: e["regression_calibration"].pop("validation_df")),
    ("the premise is downgraded and the df is not",
     lambda e: e["assumptions"].__setitem__(
         e["assumptions"].index(STUDIED + "w"), KNOWN + "w")),
    ("both premises are declared at once",
     lambda e: e["assumptions"].append(KNOWN + "w")),
    ("neither premise is declared",
     lambda e: e["assumptions"].remove(STUDIED + "w")),
    ("a df is recorded for a column with no variance",
     lambda e: e["regression_calibration"]["validation_df"].__setitem__(
         "z", 24)),
])
def test_a_premise_that_disagrees_with_the_block_is_rejected(name, change):
    """The two intervals are the same pair of numbers on the page.

    Nothing about an interval's appearance says whether a validation study
    was priced into it, so the premise is the reader's only handle — and a
    premise free to disagree with what was done is worse than none.
    """
    with pytest.raises(VerificationError):
        themis.verify(_program(), _tampered(change))


def test_the_honest_artifact_is_not_rejected_by_that_check():
    """The gate above proves it says no; this proves it can still say yes."""
    themis.verify(_program(), _tampered(lambda e: None))


def test_the_differential_audit_holds_the_same_pair_together():
    frame = _frame()
    est = estimate_differential_error(
        frame, treatment="w", outcome="y", adjustment=("z",),
        differential_by="y", differential_coefficient=0.3,
        error_variance=DeclaredVariance(0.9, 24),
        ci_bootstrap=0, random_state=7)
    from themis.estimation.dispatch import _differential_error_block
    envelope = {
        "point": est.point, "method": est.method,
        "assumptions": list(est.assumptions),
        "treatment": est.treatment, "outcome": est.outcome,
        "differential_error": _differential_error_block(est),
    }
    verify_differential_error_numeric(envelope)
    assert envelope["differential_error"]["validation_df"] == 24

    forged = copy.deepcopy(envelope)
    forged["differential_error"].pop("validation_df")
    with pytest.raises(VerificationError):
        verify_differential_error_numeric(forged)


def _blocks_named(node, name):
    """Every schema object declaring a property called ``name``."""
    if isinstance(node, dict):
        found = node.get("properties", {}).get(name)
        if isinstance(found, dict):
            yield found
        for child in node.values():
            yield from _blocks_named(child, name)
    elif isinstance(node, list):
        for child in node:
            yield from _blocks_named(child, name)


def test_the_schema_describes_both_places_the_df_is_recorded():
    """A field the schema does not carry is a field a consumer may not read,
    and both blocks that redraw record one. Found by walking rather than by a
    path, because a path written here is a second record of where the block
    lives and would go stale silently."""
    schema = json.loads(
        (pathlib.Path(themis.__file__).parent / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    for block, kind in (("regression_calibration", "object"),
                        ("differential_error", "integer")):
        homes = [b for b in _blocks_named(schema, block)
                 if "validation_df" in b.get("properties", {})]
        assert homes, f"{block} declares no validation_df"
        for home in homes:
            assert home["properties"]["validation_df"]["type"] == kind
