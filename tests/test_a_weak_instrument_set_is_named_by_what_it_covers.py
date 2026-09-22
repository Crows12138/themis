"""The robust Anderson-Rubin set names its own cover, and the region names its roles.

Two sibling checks sit thirty lines apart in one function. The
homoskedastic AR set re-solves the quadratic, compares the kind and
compares the 2SLS point. The heteroskedasticity-robust set -- written
afterwards for the same family, and the one a reader of a weak-instrument
answer actually gets -- rebuilt the cover from the crossings and the
asymptote, ran a dense-grid membership scan, and never named it. The
comment above it said it matched the kind. Ten declared leaves.

What that buys a forger is the whole point of the set. An AR set says how
much the data can rule out when the instruments are weak, and `empty`
means nothing was ruled out at this level -- the honest signal a bootstrap
interval can never give. Relabel it `bounded` and a reader is told the
effect is pinned down; the crossings, the segments and the grid scan all
still agree, because none of them is the word.

The region half is the same shape one block along. Its treatments were
held to the order of the moment tables and the other two names beside
them were not, though a region is a statement about WHICH instruments
bracketed WHICH outcome, and the moment tables count both.

`cluster_robust` is left open on purpose and this file says why, because
a silence nobody wrote down reads like one nobody noticed.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))

ROBUST = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair["result"].get("numeric_estimate") or {})
                  .get("robust_anderson_rubin_confidence_set"), dict))
REGION = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair["result"].get("extensions") or {})
                  .get("anderson_rubin_region"), dict))

ROBUST_ROSTER = 2
REGION_ROSTER = 2

#: The words the estimator's module declares for a cover, with what each
#: one is a cover OF. Transcribed from ``themis.estimation.iv``'s module
#: docstring, which is where the vocabulary is stated.
THE_WORDS = {
    "empty": "nothing",
    "bounded": "one finite interval",
    "unbounded_below": "one ray running down",
    "unbounded_above": "one ray running up",
    "whole_line": "everything",
    "disconnected": "two rays",
    "union": "more than two pieces",
}


def test_the_rosters_are_the_size_this_file_was_written_against():
    assert len(ROBUST) == ROBUST_ROSTER, ROBUST
    assert len(REGION) == REGION_ROSTER, REGION


def test_the_vocabulary_is_the_one_the_contract_declares():
    """A word this file does not know is a cover nothing here names."""
    schema = json.loads(
        (pathlib.Path(__file__).parent.parent / "themis" / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    enum = set(schema["properties"]["numeric_estimate"]["properties"]
               ["robust_anderson_rubin_confidence_set"]["properties"]
               ["kind"]["enum"])
    assert enum == set(THE_WORDS), enum ^ set(THE_WORDS)


# ------------------------------------------------------------- the cover's name


@pytest.mark.parametrize("shape", ROBUST)
def test_the_set_is_named_by_what_it_covers(shape):
    """Every other word, not one: the forgery that matters is whichever
    word flatters the finding, and which one that is depends on the row."""
    pair = SHAPES[shape]
    honest = (pair["result"]["numeric_estimate"]
              ["robust_anderson_rubin_confidence_set"]["kind"])
    assert honest in THE_WORDS, honest
    for word in THE_WORDS:
        if word == honest:
            continue
        result = copy.deepcopy(pair["result"])
        (result["numeric_estimate"]
         ["robust_anderson_rubin_confidence_set"])["kind"] = word
        with pytest.raises(VerificationError, match="kind mismatch"):
            themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("shape", ROBUST)
def test_an_empty_set_cannot_be_shown_as_a_finding(shape):
    """The reading this exists for, stated on its own.

    ``empty`` is the answer that says the data ruled nothing out at this
    level. It is the one a bootstrap interval cannot produce and the one a
    forger would most want gone.
    """
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["numeric_estimate"]["robust_anderson_rubin_confidence_set"]
    block["kind"] = "bounded" if block["kind"] == "empty" else "empty"
    with pytest.raises(VerificationError, match="kind mismatch"):
        themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("shape", ROBUST)
def test_the_set_keeps_the_same_point_the_answer_does(shape):
    pair = SHAPES[shape]
    ne = pair["result"]["numeric_estimate"]
    assert (ne["robust_anderson_rubin_confidence_set"]["point"]
            == ne["point"]), shape
    result = copy.deepcopy(pair["result"])
    (result["numeric_estimate"]
     ["robust_anderson_rubin_confidence_set"])["point"] += 0.5
    with pytest.raises(VerificationError, match="point mismatch"):
        themis.verify_answer_claims(pair["program"], result)


# ------------------------------------------------------- the region's own roles


@pytest.mark.parametrize("shape", REGION)
def test_an_instrument_is_a_column_this_region_read(shape):
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["extensions"]["anderson_rubin_region"]
    block["instruments"] = ["a_column_no_document_names"] * len(
        block["instruments"])
    with pytest.raises(VerificationError, match="did not read"):
        themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("shape", REGION)
def test_the_instruments_are_the_ones_the_moments_were_built_on(shape):
    """The count is not decoration: the moment tables are q x q."""
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["extensions"]["anderson_rubin_region"]
    block["instruments"] = block["instruments"] + block["data_columns"][:1]
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("shape", REGION)
def test_an_instrument_is_not_also_a_treatment(shape):
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["extensions"]["anderson_rubin_region"]
    block["instruments"] = list(block["treatments"][:len(block["instruments"])])
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("shape", REGION)
def test_the_outcome_is_a_column_and_is_not_one_of_the_other_roles(shape):
    pair = SHAPES[shape]
    for forged, why in (("a_column_no_document_names", "did not read"),
                        (None, None)):
        result = copy.deepcopy(pair["result"])
        block = result["extensions"]["anderson_rubin_region"]
        if forged is None:
            block["outcome"] = block["treatments"][0]
            why = "is also"
        else:
            block["outcome"] = forged
        with pytest.raises(VerificationError, match=why):
            themis.verify_answer_claims(pair["program"], result)


# --------------------------------------------------------- the declared silence


def test_cluster_robust_is_left_open_and_this_is_the_reason():
    """It restates ``cluster is not None`` and the envelope writes the word
    once, in that key.

    Measured, not assumed: on every answer carrying the block the string
    ``cluster`` appears exactly once in the whole result. A comparison
    would be the boolean against itself, which is the third copy
    ``dispatch`` deleted for this reason. The two directions the fact IS
    audited from are the run context and the estimator's own assumption
    sentence, which ``verifier.cluster_inference_rules`` reads.
    """
    for shape in ROBUST:
        blob = json.dumps(SHAPES[shape]["result"], ensure_ascii=False)
        assert blob.count("cluster") == 1, (shape, blob.count("cluster"))
        leaves = set(UNWITNESSED.get(shape, ()))
        assert ("numeric_estimate.robust_anderson_rubin_confidence_set"
                ".cluster_robust") in leaves, shape


def test_everything_else_under_both_blocks_is_held():
    """The other half: nothing this frontier claimed is still declared."""
    still = {
        leaf
        for shape in ROBUST + REGION
        for leaf in UNWITNESSED.get(shape, ())
        if "anderson_rubin" in leaf
    }
    assert still == {
        "numeric_estimate.robust_anderson_rubin_confidence_set.cluster_robust",
    }, still


# --------------------------------------------------------- nothing else moved


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_is_refused(shape):
    themis.verify_answer_claims(
        SHAPES[shape]["program"], SHAPES[shape]["result"])
