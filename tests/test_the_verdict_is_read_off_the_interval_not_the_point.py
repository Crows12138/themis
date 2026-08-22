"""Which of the two E-values the reader's verdict is taken from.

One estimate yields two E-values and they answer different questions. The
one on the point estimate asks how strong a confounder would have to be to
move the ESTIMATE to the null. The one on the confidence bound nearer the
null asks how strong a one would have to be to take the FINDING away. "Is
this robust" means the second, and the module read the first.

Two things made that reading unreachable rather than merely wrong. The
bound was computed and printed and then not used: four ``if e_point <``
branches, written twice — once per conversion route, with different wording
for the same four bands. And ``_closer_to_null`` returned ``None`` for any
interval spanning the null, so on exactly the results that are not
significant there was no bound to fall back FROM, and the reading was taken
off a point estimate the interval had already failed to separate from zero.

The two compound. A 90-row campaign frame below estimates +0.087 with a
95% interval of [-0.014, +0.202] — an interval that includes no effect at
all — and the E-value on that point is 4.10, which the module read as
"比较稳健：混杂要相当大才解释得掉". The bound's E-value is exactly 1: the
confounder that explains this away is the trivial one.

So the band is a field with a gloss rather than a clause of a Chinese
sentence, and beside it is the number it was read off. A verdict inside
prose is a verdict no verifier re-derives and no second language reaches,
and both of those are what let this one stand.
"""
from __future__ import annotations

import ast as pyast
import inspect
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import sensitivity
from themis.estimation.dispatch import _closer_to_null
from themis.estimation.sensitivity import (BAND_BASES, BANDS, band_for,
                                           e_value_from_ate_binary,
                                           e_value_from_ate_continuous)
from themis.output import analysis_report, envelope_glossary

SCHEMA = json.loads(
    (pathlib.Path(__file__).resolve().parent.parent / "themis" / "schemas"
     / "query_result.schema.json").read_text(encoding="utf-8"))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _ast():
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
                "given": []}},
        ],
    }


def _campaign(seed: int, n: int = 90) -> pd.DataFrame:
    """A rare outcome and few rows: a sizeable RR with a wide interval.

    The combination is what separates the two E-values. A low baseline makes
    the point estimate's risk ratio large — and therefore its E-value large
    — while ninety rows leave the interval unable to exclude no effect at
    all. Neither number is wrong; they answer different questions.
    """
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    x = rng.random(n) < np.where(z, 0.6, 0.4)
    p = np.clip(0.05 + 0.04 * z + 0.10 * x, 0.01, 0.99)
    return pd.DataFrame({"x": x, "z": z, "y": rng.random(n) < p})


def _block(seed: int) -> tuple[dict, dict]:
    out = themis.estimate(_ast(), _campaign(seed), ci_bootstrap=400)
    ne = out["results"][0]["numeric_estimate"]
    return ne, ne["sensitivity_analysis"]


# --- the reading follows the bound -------------------------------------------


def test_a_result_the_interval_cannot_separate_from_zero_is_not_robust():
    """The headline case, end to end.

    The interval contains no-effect, so nothing here has been shown at all
    — and the E-value on the point estimate is 4.10, which the module read
    as "比较稳健". What the bound says is 1: the trivial confounder already
    explains it. A reading that gets louder as the evidence gets weaker is
    not a cautious reading, it is an inverted one.
    """
    ne, sa = _block(5)
    assert ne["ci_lower"] < 0 < ne["ci_upper"]        # excludes nothing

    assert sa["e_value"] == pytest.approx(4.10, abs=0.01)
    assert band_for(sa["e_value"], None) == ("substantial", "point")

    assert sa["e_value_ci_bound"] == 1.0
    assert (sa["interpretation_band"], sa["band_basis"]) == (
        "fragile", "ci_bound")


def test_an_interval_that_does_exclude_zero_still_moves_the_reading():
    """Not only a significance test wearing a band's name.

    This interval is [+0.060, +0.267] and excludes the null, so nothing is
    being clamped to 1. The point's E-value is 8.23 and the bound's is 4.00,
    which is two bands apart — the distinction is about how much of the
    estimate the interval leaves standing, and it is live wherever an
    interval is wide.
    """
    ne, sa = _block(11)
    assert ne["ci_lower"] > 0

    assert band_for(sa["e_value"], None) == ("very_robust", "point")
    assert (sa["interpretation_band"], sa["band_basis"]) == (
        "substantial", "ci_bound")


def test_the_point_is_the_fallback_and_the_result_says_so():
    """No interval, so the point is the only number there is — which is a
    different situation from the one above and is reported as one."""
    result = e_value_from_ate_binary(ate=0.7, baseline_rate=0.05)
    assert result.e_value_ci_bound is None
    assert (result.interpretation_band, result.band_basis) == (
        "very_robust", "point")


# --- what the interval's near end is -----------------------------------------


def test_an_interval_spanning_the_null_reaches_the_null():
    """The second half of the defect, on its own.

    ``None`` here says "there is no bound", and a reading that falls back to
    the point on that answer is loudest exactly where the evidence is
    weakest. The interval's nearest approach to zero is zero, the E-value
    there is 1, and that is a fact about the estimate.
    """
    assert _closer_to_null(-0.05, 0.20) == 0.0
    assert _closer_to_null(-0.20, 0.05) == 0.0
    assert _closer_to_null(0.0, 0.20) == 0.0

    at_null = e_value_from_ate_binary(ate=0.09, baseline_rate=0.05,
                                      ci_bound=0.0)
    assert at_null.e_value_ci_bound == 1.0
    assert at_null.interpretation_band == "fragile"


def test_only_an_absent_interval_is_absent():
    assert _closer_to_null(None, 0.2) is None
    assert _closer_to_null(0.1, None) is None


def test_an_interval_clear_of_the_null_keeps_its_near_end():
    assert _closer_to_null(0.1, 0.3) == 0.1
    assert _closer_to_null(-0.3, -0.1) == -0.1


def test_the_verifier_transcribes_the_same_rule():
    """Two independent transcriptions of one rule, held together by a run.

    The verifier writes its own copy on purpose — an audit that imports the
    producer audits nothing — so what keeps the two from drifting is a
    result that distinguishes them. This one does: its interval straddles
    the null, so a verifier still answering ``None`` there would recompute
    no bound E-value at all and reject the 1.0 the producer recorded.

    A round trip rather than a comparison of two functions, because the
    second is not reachable from here — it is a closure, which is what
    makes it independent.
    """
    ast = _ast()
    out = themis.estimate(ast, _campaign(5), ci_bootstrap=400)
    result = out["results"][0]
    ne = result["numeric_estimate"]
    assert ne["ci_lower"] < 0 < ne["ci_upper"]
    assert ne["sensitivity_analysis"]["e_value_ci_bound"] == 1.0

    themis.verify(ast, result)          # no raise


# --- one authority for the cut-points ----------------------------------------


def test_the_cut_points_are_written_once():
    """What the two four-branch chains cost.

    Each route banded the number itself, and the two worded the same four
    bands differently — one in "interpretation: very weak / 很脆弱", the
    other in "解读：很脆弱——很小的未测混杂就足以解释掉这个结果". Two copies
    of a rule are two rules, and a fix applied to one of them is the shape
    this defect would have come back in.
    """
    tree = pyast.parse(pathlib.Path(inspect.getfile(sensitivity)).read_text(
        encoding="utf-8"))
    written = [node.value for node in pyast.walk(tree)
               if isinstance(node, pyast.Constant)
               and isinstance(node.value, float)]
    for cut in (1.5, 2.5, 5.0):
        assert written.count(cut) == 1, (
            f"{cut} is a literal in {written.count(cut)} places")


@pytest.mark.parametrize("band", BANDS)
def test_every_band_is_reachable(band):
    """A band nothing produces is a word nobody reads, and a band the gloss
    has no word for is an identifier a reader has to look up."""
    reached = {band_for(e, None)[0] for e in (1.1, 2.0, 3.0, 9.0)}
    assert band in reached
    for lang in ("zh", "en"):
        assert envelope_glossary.evalue_band_word(band, lang)


@pytest.mark.parametrize("basis", BAND_BASES)
def test_every_basis_has_a_word(basis):
    for lang in ("zh", "en"):
        assert envelope_glossary.evalue_band_basis_word(basis, lang)


def test_the_envelope_admits_exactly_these():
    """The schema's enum and the module's tuple, held equal.

    ``BANDS`` is derived from the cut-points, so a fourth cut-point adds a
    band to the producer; this is what stops it from being a band the
    contract rejects and the browser has no table row for.
    """
    props = SCHEMA["properties"]["numeric_estimate"]["properties"][
        "sensitivity_analysis"]["properties"]
    assert set(props["interpretation_band"]["enum"]) == set(BANDS) | {None}
    assert set(props["band_basis"]["enum"]) == set(BAND_BASES) | {None}


def test_both_routes_read_one_authority():
    """The same two numbers, banded the same way whichever conversion
    produced them. It is not a property either formatter can have on its
    own — it is what having one ``band_for`` means."""
    binary = e_value_from_ate_binary(ate=0.09, baseline_rate=0.05,
                                     ci_bound=0.01)
    continuous = e_value_from_ate_continuous(
        ate=0.5, outcome_sd=1.0, ci_bound=0.05)
    for result in (binary, continuous):
        assert result.interpretation_band == band_for(
            result.e_value, result.e_value_ci_bound)[0]
        assert result.band_basis == "ci_bound"


# --- what a reader is handed --------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_report_states_the_reading_and_which_number_it_came_off(lang):
    """Both languages, which is the other half of moving it out of prose.

    ``note`` is produced in the kernel, before anyone knows who is reading,
    so it is written in one language and will be until the words leave the
    kernel entirely. The reading is a field, so it is not — and the reading
    is the part a person acts on.
    """
    ne, sa = _block(5)
    lines = "\n".join(analysis_report._estimate_meta(ne, lang=lang))
    assert envelope_glossary.evalue_band_word("fragile", lang) in lines
    assert envelope_glossary.evalue_band_basis_word("ci_bound", lang) in lines


def test_a_block_with_no_e_value_states_no_reading():
    """Undefined is not a band. The row falls back to the note's reason
    rather than banding a number that does not exist."""
    result = e_value_from_ate_binary(ate=0.5, baseline_rate=0.7)
    assert result.e_value is None
    assert (result.interpretation_band, result.band_basis) == (None, None)

    ne = {"sensitivity_analysis": {
        "e_value": None, "interpretation_band": None, "band_basis": None,
        "note": result.note}}
    lines = "\n".join(analysis_report._estimate_meta(ne, lang="zh"))
    assert result.note in lines
