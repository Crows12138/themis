"""A column's measurement scale is declared; it was being guessed from storage.

``{"kind": "variable", "predicate": "channel", "domain": [...]}`` says how
many levels a variable has, and ``dispatch._declared_scale`` has read that
since the type-reconciliation diagnostic was written. Nothing that DECIDED
anything read it. Two decisions came off the column's dtype instead, and
both are wrong the same way.

The first is admissibility. ``contract.validate_data`` took a bool or
numeric column and refused everything else, so three advertising channels
stored as text — the commonest shape business data arrives in — ended
``themis.estimate`` in ``DataContractError``, while the same variable coded
0/1/2 was accepted. The second is what the accepted column then is: a term
in a design matrix, so the three channels became the numbers 0, 1 and 2 and
the fit was asked to believe 社交 sits halfway between 搜索 and 邮件.

Together they let the ENCODING decide. Re-typing one column as labels turned
an estimate into a traceback, and neither outcome was a statement about the
data. The first test below is the whole ticket: the two frames are the same
data and now get the same answer, down to the fingerprint.

What is NOT fixed, and is disclosed instead: the ordered entry itself. A
one-hot design is the right answer for a NOMINAL covariate and the wrong one
for a count, and ``scale`` admits binary / discrete / continuous with no
member for "levels without an order" — so a three-channel campaign and a
0..10 visit count declare identically. Guessing between them would replace
one silent misspecification with another. The estimate stays biased and the
reader is now told so.
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
import pandas as pd
import pytest

import themis
from themis import language
from themis.estimation import declared
from themis.estimation.contract import DataContractError
from themis import assumption_glossary

ROW = declared.ORDERED_COVARIATE_ASSUMPTION

#: Per-channel truth. The third channel's effect REVERSES, which is what a
#: single ordered term cannot represent and what makes the bias visible
#: rather than a rounding difference.
SHARE = (1 / 3, 1 / 3, 1 / 3)
BASE = (0.30, 0.30, 0.55)
EFFECT = (0.20, 0.20, -0.35)
TRUE_ATE = sum(w * e for w, e in zip(SHARE, EFFECT))          # +0.01667

LABELS = ["搜索", "社交", "邮件"]


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program(domain):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "ad", "domain": [True, False]},
            {"kind": "variable", "predicate": "bought", "domain": [True, False]},
            {"kind": "variable", "predicate": "channel", "domain": list(domain)}
            if domain is not None else
            {"kind": "variable", "predicate": "channel"},
            {"kind": "cause", "from": _atom("ad"), "to": _atom("bought")},
            {"kind": "cause", "from": _atom("channel"), "to": _atom("ad")},
            {"kind": "cause", "from": _atom("channel"), "to": _atom("bought")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("bought"), "value": True},
                "intervention": {"atom": _atom("ad"), "value": True},
                "given": []}},
        ],
    }


def _campaign(levels, n: int = 1200, seed: int = 3) -> pd.DataFrame:
    """The same 1200 rows, written with whichever spelling of the levels."""
    rng = np.random.default_rng(seed)
    k = len(levels)
    idx = rng.integers(0, k, n)
    ad = rng.random(n) < np.take([0.55, 0.45, 0.30][:k], idx)
    bought = rng.random(n) < np.clip(
        np.take(BASE[:k], idx) + np.take(EFFECT[:k], idx) * ad, 0, 1)
    return pd.DataFrame({"ad": ad, "bought": bought,
                         "channel": [levels[i] for i in idx]})


def _estimate(levels, *, domain=None, **kw):
    out = themis.estimate(_program(LABELS if domain is None else domain),
                          _campaign(levels), ci_bootstrap=0, **kw)
    return out["results"][0]


# --- the ticket ---------------------------------------------------------------


def test_the_same_data_gets_the_same_answer_however_the_levels_were_spelled():
    """The whole of it, in one comparison.

    Labels and codes are the same 1200 rows under the same declaration, and
    the run now agrees — down to ``data_hash``, because the frame the
    contract fingerprints is the frame the PROGRAM declared rather than the
    one the user happened to type. Before, one of these was an estimate and
    the other was a traceback.
    """
    text = _estimate(LABELS)["numeric_estimate"]
    coded = _estimate([0, 1, 2], domain=[0, 1, 2])["numeric_estimate"]

    assert text["point"] == coded["point"]
    assert text["data_hash"] == coded["data_hash"]
    assert text["method"] == coded["method"] == "backdoor_logistic"


def test_the_declared_order_is_the_programs_own_and_not_this_modules():
    """Nothing here invents an order for a set of labels.

    Declaring the same three channels in a different order codes them
    differently, which is what makes the coding the program's statement
    rather than a convention buried in a helper — and what makes it
    reproducible for anyone reading the program.
    """
    forward = _campaign(LABELS)
    codes = declared.conform(_program(LABELS), forward)["channel"]
    reversed_codes = declared.conform(
        _program(list(reversed(LABELS))), forward)["channel"]

    assert list(codes[:5]) == [2 - v for v in reversed_codes[:5]]


def test_a_numeric_frame_is_returned_untouched():
    """The route is added, not swapped. A program that arrives already coded
    goes through the contract it always did, on the object it always did."""
    df = _campaign([0, 1, 2])
    assert declared.conform(_program([0, 1, 2]), df) is df


# --- where a label still cannot be placed ------------------------------------


def test_a_labelled_column_with_no_declared_domain_says_what_to_declare():
    """The counterexample the admissibility change has to answer.

    Nothing licenses an order for these three words, so nothing invents one
    — the run still ends here, which is ``estimate``'s documented behaviour
    for a frame that fails validation. What changed is the sentence: it used
    to name the dtype, which sends a reader to ``astype`` and produces a
    number resting on alphabetical order.
    """
    with pytest.raises(DataContractError) as exc:
        themis.estimate(_program(None), _campaign(LABELS), ci_bootstrap=0)
    said = str(exc.value)
    assert "domain" in said
    assert "dtype" not in said


def test_a_value_the_declaration_does_not_list_is_refused_naming_it():
    """A fourth channel nobody declared cannot be placed on three levels,
    and the refusal says which value rather than that something is wrong."""
    df = _campaign(LABELS)
    df.loc[df.index[:20], "channel"] = "线下"
    with pytest.raises(DataContractError, match="线下"):
        themis.estimate(_program(LABELS), df, ci_bootstrap=0)


def test_the_diagnostic_and_the_coding_ask_one_question():
    """Which values the declaration cannot place is asked once.

    The type-reconciliation diagnostic reports them and ``conform`` cannot
    code a column while any are present. Two answers to that could disagree
    about a frame, and the disagreement would read as the diagnostic passing
    something the step beside it refused.
    """
    values = ["搜索", "线下", "邮件"]
    assert declared.outside_domain(values, LABELS) == ["线下"]
    assert declared.outside_domain(LABELS, LABELS) == []


# --- what the fit then says about what it did --------------------------------


def test_the_fit_says_it_read_three_channels_as_one_number():
    for levels, domain in ((LABELS, None), ([0, 1, 2], [0, 1, 2])):
        result = _estimate(levels, domain=domain)
        assert ROW in result["numeric_estimate"]["assumptions"]


def test_and_the_estimate_really_is_off_by_the_amount_that_row_warns_about():
    """The disclosure is not a fix and this is what says so.

    The third channel's effect reverses, which one ordered term cannot
    represent, so the adjustment is incomplete and the point comes back at
    roughly three times the truth. The row is what a reader has to act on;
    it is not the row being cautious about a number that is fine.
    """
    point = _estimate(LABELS)["numeric_estimate"]["point"]
    assert TRUE_ATE == pytest.approx(0.0167, abs=0.001)
    assert point > 3 * TRUE_ATE


@pytest.mark.parametrize("estimator", ["ipw", "aipw", "tmle"])
def test_the_propensity_estimators_declare_it_too(estimator):
    result = _estimate(LABELS, ate_estimator=estimator)
    assert ROW in result["numeric_estimate"]["assumptions"]


def test_two_levels_carry_no_such_assumption():
    """The boundary, and the reason it is where it is: an indicator is an
    indicator whichever two labels built it, so there is no order to assume."""
    two = ["搜索", "社交"]
    result = themis.estimate(_program(two), _campaign(two), ci_bootstrap=0)
    assert ROW not in result["results"][0]["numeric_estimate"]["assumptions"]


def test_a_continuous_covariate_is_not_this_finding():
    """The other boundary, and the one that would have made the row noise.

    A quantity entering as one term is what ``linear_outcome_regression``
    already says, and a quantity's order and spacing are its own. Reporting
    it here would bury the case that matters under one the envelope carries.
    """
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"t": rng.random(400) < 0.5,
                       "z": rng.normal(size=400)})
    assert declared.ordered_covariates(df, ("z",)) == ()


def test_a_short_frame_of_distinct_values_has_no_levels_to_count():
    """Twelve distinct floats in twelve rows sit under the cap and are not
    levels — the judgement :mod:`themis.estimation.support` settled, asked
    here because it is the same question about the same columns."""
    df = pd.DataFrame({"z": [0.1, -0.4, 0.9, 0.3, -0.2, 0.7,
                             0.5, -0.7, 0.2, 0.8, -0.3, 0.6]})
    assert declared.ordered_covariates(df, ("z",)) == ()


# --- the row itself -----------------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_row_reaches_a_reader_in_either_language(lang):
    """Classified rather than passed through, and worded in both.

    An unrecognised declaration reaches the ledger as its own identifier, so
    a row nobody glossed still gets to a reader — as
    ``multi_level_covariates_entered_as_ordered_numbers``, which is not a
    sentence anybody can act on.
    """
    entry = assumption_glossary.classify_assumption(ROW)
    assert assumption_glossary.is_classified(ROW)
    assert language.spoken(entry["claim"], lang) != ROW
    assert entry["layer"] == assumption_glossary.Layer.FUNCTIONAL_FORM


def test_every_estimator_that_builds_a_design_by_column_declares_it():
    """The census, so a ninth estimator cannot arrive silent.

    Read off the source rather than listed here: a module that takes a
    covariate set straight to ``to_numpy(dtype=float)`` is one that made
    this assumption, and the two exemptions are named with why they are not
    estimates — one fits a propensity only to DIAGNOSE overlap, and the
    other is structure search, which states no effect at all.
    """
    root = pathlib.Path(themis.__file__).resolve().parent / "estimation"
    exempt = {
        "dispatch.py": "fits a propensity to diagnose overlap, and reports "
                       "no estimand of its own",
        "discovery.py": "searches for structure; it states no effect for an "
                        "assumption to qualify",
    }
    silent = []
    for path in sorted(root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not re.search(r"df\[list\(\w+\)\]\.to_numpy\(dtype=float\)|"
                         r"\[list\(adjustment\)\]\.to_numpy", source):
            continue
        if path.name in exempt or "ordered_entry" in source:
            continue
        silent.append(path.name)
    assert not silent, (
        f"{silent} build a design matrix from a covariate set by column and "
        f"do not declare what that does to a multi-level column"
    )
