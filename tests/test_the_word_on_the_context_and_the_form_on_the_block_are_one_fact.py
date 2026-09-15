"""``model=`` is recorded twice, and until now only one copy was readable.

``estimation_context.model_preference`` is written at the entry, on every
result, before any route has been chosen. What became of that word is
written on the far side of the cascade, by the estimator that resolved a
shape, and reaches the envelope as ``extensions.mechanism_audit``. Two
records of one decision — which is the arrangement this repository uses
wherever a run's own input has to be deniable.

The second record was there and nobody read it. Measured, end to end: an
answer produced under ``auto``, whose block says the estimator settled the
shape, has its ``model_preference`` rewritten to ``'linear'`` and every
public door says yes. That leaf was declared unwitnessed on 120 of the
corpus's rows, and this is what was under it.

THE PREMISE THIS RESTS ON, and why it is a test rather than a comment.
``build_mechanism_audit`` holds the form's origin and the origins of the
levers that are NOT ``model=`` as two separate arguments and merges them
into one ``settled_by`` list, so a ``caller_asserted`` there does not say
WHICH lever the caller pulled. Reading it as ``model=`` is sound only
because no other shape lever is a parameter of the public entry — a
propensity floor and a weighting flag are levers of the estimators and of
nothing a caller can reach, so :func:`~themis.estimation.form.pulled_by`
can only answer ``default`` on any envelope a verifier will ever see. That
is measured below rather than asserted here, and wiring one of them
through turns this file red, which is the moment the block would have to
say which lever it means.

The alternative was a field on the block saying exactly that, and it was
built and withdrawn: the schema requires what a block carries, so every
stored answer-shape needed re-collecting, and a full re-collection re-keys
the corpus — 44 of 75 changed rows came back as a different RUN, other
sample sizes and other data. That would have moved the declared remainder
for two reasons at once and made this repair unmeasurable. A premise that
fails loudly is cheaper than a measurement that can no longer be read.

WHAT THIS FILE DOES NOT CLAIM. A named word on an answer that discloses no
mechanism at all is not checked HERE, and cannot be: three of IV's five
words select an estimator with no functional-form assumption to disclose,
so there is no block to attribute anything to, and requiring one would
refuse those three honest answers. They are held by something else, in
``test_the_word_a_caller_wrote_is_held_by_whatever_honours_it.py``: their
word names a ROW rather than a shape, and the row that ran is the record
of what became of the request. The limit is pinned below rather than left
to be discovered — a coverage claim is a fact about the question that was
asked.
"""
from __future__ import annotations

import ast
import copy
import inspect
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _EFFECT_STRATEGIES, estimate_program
from themis.estimation.form import (
    AUTO,
    MODEL_WORDS_DOSE_RESPONSE,
    MODEL_WORDS_IV,
    MODEL_WORDS_NONE,
    MODEL_WORDS_OUTCOME,
    outcome_form,
)
from themis.verifier.assumption_ledger_rules import (
    _DECLINED_TO_CHOOSE,
    _THE_ROWS_A_WORD_NAMES,
)
from themis.verifier.mechanism_rules import (
    _ONE_ARM_TWO_SPELLINGS,
    word_that_could_not_have_asked_for,
)


ROOT = pathlib.Path(__file__).resolve().parent.parent


# --- the programs, one per route -------------------------------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


_EFFECT_QUERY = {"kind": "query", "id": "q", "query": {
    "kind": "effect", "intervention": {"atom": _atom("x"), "value": True},
    "target": {"atom": _atom("y"), "value": True}, "given": []}}

_BACKDOOR = _program([
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "y"},
    {"kind": "variable", "predicate": "z"},
    _cause("x", "y"), _cause("z", "x"), _cause("z", "y"), _EFFECT_QUERY,
])

_FRONTDOOR = _program([
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "m"},
    {"kind": "variable", "predicate": "y"},
    _cause("x", "m"), _cause("m", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _EFFECT_QUERY,
])

_IV = _program([
    {"kind": "variable", "predicate": "z"},
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "y"},
    _cause("z", "x"), _cause("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _EFFECT_QUERY,
])

_OVERID = _program([
    {"kind": "variable", "predicate": "z"},
    {"kind": "variable", "predicate": "z2"},
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "y"},
    _cause("z", "x"), _cause("z2", "x"), _cause("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _EFFECT_QUERY,
])

_MEDIATION = _program([
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "m"},
    {"kind": "variable", "predicate": "y"},
    _cause("x", "m"), _cause("m", "y"), _cause("x", "y"),
    {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True}, "given": [],
        "mediator": _atom("m")}},
])


def _frame(n: int = 1200, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    latent = rng.integers(0, 2, n)
    z2 = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.2 + 0.25 * z + 0.2 * z2 + 0.15 * latent
         ).astype(int)
    m = (rng.random(n) < 0.2 + 0.5 * x).astype(int)
    y = (rng.random(n) < np.clip(0.2 + 0.3 * x + 0.3 * m + 0.2 * latent,
                                 0, 1)).astype(int)
    return pd.DataFrame({"x": x, "y": y, "z": z, "z2": z2, "m": m})


def _answer(program, word) -> dict:
    """The one result of ``program`` under ``word`` that carries a fit."""
    out = themis.estimate(program, _frame(), model=word, ci_bootstrap=0)
    for result in out.get("results") or ():
        if isinstance(result.get("numeric_estimate"), dict):
            return result
    raise AssertionError(f"no numeric answer for {word!r}")


def _blocks(result) -> list:
    return list(((result.get("extensions") or {})
                 .get("mechanism_audit") or {}).get("mechanisms") or ())


def _refuses(result) -> str | None:
    try:
        themis.verify_assumption_ledger(result)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None


# --- the witness itself, both values, on every family that has one ---------


def _a_caller_settled_a_shape(block) -> bool:
    """Written out here rather than imported from the rule it defends.

    The rule and its test sharing one predicate is how a test and the check
    it guards go blind together — this repository has already paid for that
    once, one block over.
    """
    return any(a.get("settled_by") == "caller_asserted"
               for a in block.get("assumptions") or ())


@pytest.mark.parametrize("program,word,form,named", [
    (_BACKDOOR, "auto", "logistic", False),
    (_BACKDOOR, "linear", "linear", True),
    (_BACKDOOR, "logistic", "logistic", True),
    (_FRONTDOOR, "auto", "logistic", False),
    (_FRONTDOOR, "linear", "linear", True),
    (_FRONTDOOR, "logistic", "logistic", True),
    # The family that spells the arm its own way, which is why the word and
    # the form are not compared as strings.
    (_MEDIATION, "auto", "logit", False),
    (_MEDIATION, "linear", "linear", True),
    (_MEDIATION, "logistic", "logit", True),
    # IV reads the option as which ESTIMATOR to run; the one of its words
    # that carries a functional-form assumption discloses a block.
    (_IV, "2sls", "2sls", True),
])
def test_the_block_says_whether_a_caller_settled_the_form_beside_it(
    program, word, form, named,
):
    """Driven end to end, because what is being checked is that the word
    survived the journey from the entry to the estimator that resolved a
    shape. A unit call on the builder would state that the builder copies
    its argument."""
    result = _answer(program, word)
    blocks = _blocks(result)
    assert len(blocks) == 1
    assert blocks[0]["form"] == form
    assert _a_caller_settled_a_shape(blocks[0]) is named
    assert _refuses(result) is None


# --- and the two ends are held to each other -------------------------------


def test_a_context_naming_a_word_no_block_attributes_to_the_caller():
    """The bend the census asks about, and the one that was passing.

    An answer produced under ``auto``: the block says the estimator settled
    the shape, and the context is rewritten to say the caller chose it. The
    field would then be the answer's only record that anybody chose
    anything.
    """
    result = _answer(_BACKDOOR, AUTO)
    assert _a_caller_settled_a_shape(_blocks(result)[0]) is False
    bent = copy.deepcopy(result)
    bent["estimation_context"]["model_preference"] = "linear"
    complaint = _refuses(bent)
    assert complaint is not None
    assert "no disclosed mechanism" in complaint


def test_a_block_claiming_a_caller_who_named_nothing_was_already_held():
    """The other end of the pair, and this file adds NO rule for it.

    Two gates already stand between that lie and a reader, and both were
    found by trying to write a third. Moving the block's origin alone is
    refused by the pairing that holds it equal to the ledger line beside
    it; moving both is refused by the check that will not hand a
    ``caller_asserted`` line to a reader when nothing on the answer records
    the caller supplying anything — which reads THIS context field, and is
    the reason the field had a reader at all before today.

    Written down because a rule whose counterexample another rule refuses
    first reads as coverage and is not: it would have passed its own test
    on the strength of somebody else's work, and gone on passing it if it
    were deleted.
    """
    result = _answer(_BACKDOOR, AUTO)
    shapes = {a["id"] for a in _blocks(result)[0]["assumptions"]}

    one_copy = copy.deepcopy(result)
    for entry in (one_copy["extensions"]["mechanism_audit"]["mechanisms"][0]
                  ["assumptions"]):
        entry["settled_by"] = "caller_asserted"
    complaint = _refuses(one_copy)
    assert complaint is not None
    assert "the mechanism_audit beside it says" in complaint

    both_copies = copy.deepcopy(one_copy)
    for line in both_copies["extensions"]["assumption_ledger"]["assumptions"]:
        if line.get("id") in shapes:
            line["provenance"] = "caller_asserted"
    complaint = _refuses(both_copies)
    assert complaint is not None
    assert "nothing in this answer records the caller supplying" in complaint


def test_a_context_word_that_could_not_have_asked_for_this_shape():
    """Neither end withdrawn — both say the caller chose — and they name
    two different shapes. This is the bend the presence of the field alone
    would not have caught, and it is the one that reads worst: the envelope
    tells a reader they asked for the non-linear arm beside a number fitted
    through a line."""
    result = _answer(_BACKDOOR, "linear")
    assert _blocks(result)[0]["form"] == "linear"
    bent = copy.deepcopy(result)
    bent["estimation_context"]["model_preference"] = "logistic"
    complaint = _refuses(bent)
    assert complaint is not None
    assert "two records of the same decision" in complaint


# --- the other side: what a correct gate must NOT refuse -------------------


def test_one_arm_under_two_spellings_is_not_a_disagreement():
    """``logistic`` is what a caller may write and ``logit`` is what the
    mediation family reports; a rule comparing the two as strings would
    refuse an honest answer on every mediation run that names the arm."""
    result = _answer(_MEDIATION, "logistic")
    assert result["estimation_context"]["model_preference"] == "logistic"
    assert _blocks(result)[0]["form"] == "logit"
    assert _a_caller_settled_a_shape(_blocks(result)[0]) is True
    assert _refuses(result) is None


@pytest.mark.parametrize("word", ["wald", "acr", "stratified_wald"])
def test_a_named_word_whose_route_discloses_no_shape_is_left_alone(word):
    """THE LIMIT OF THE PAIR THIS FILE IS ABOUT, pinned rather than
    described.

    These three answer with no functional-form assumption at all, so there
    is no mechanism block to attribute the caller's word to. The check that
    reads a block is scoped to answers that disclose a shape, and these
    are why: a rule asking every named word for a block would refuse all
    three, and a refusal of an honest answer is worse than the hole it
    closes. It costs nothing in corroboration, which is what it used to
    cost: the word on these rows names the row that ran, and the ``method``
    it names is what holds it.
    """
    result = _answer(_IV, word)
    assert result["estimation_context"]["model_preference"] == word
    assert _blocks(result) == []
    assert _refuses(result) is None


def test_a_row_that_honours_a_word_by_being_it_is_left_alone():
    """The false positive this gate had, found by construction rather than
    by the corpus — which carries no answer under this word at all.

    ``iv_overidentified`` accepts ``2sls`` because the row IS the two-stage
    fit, so nothing received the word as an argument and the block says the
    caller settled nothing. That is the honest block: withdraw the word and
    the same row answers, so the shape is not theirs to change. A check
    asking every named word for a block would refuse this honest answer.

    Left alone by the check on the block, and no longer left alone: the
    word on this row is read against the row that ran, which is why the
    exemption this test used to pin is gone.
    """
    result = _answer(_OVERID, "2sls")
    assert result["numeric_estimate"]["method"] == "iv_2sls_overid"
    assert result["estimation_context"]["model_preference"] == "2sls"
    assert _a_caller_settled_a_shape(_blocks(result)[0]) is False
    assert _refuses(result) is None
    # And the same row under the word for declining to choose, which is what
    # makes the sentence above true rather than a courtesy.
    assert _answer(_OVERID, AUTO)["numeric_estimate"]["method"] == (
        "iv_2sls_overid")


def test_the_row_that_honours_a_word_by_being_it_is_named_by_that_word():
    """Read off the strategy table, not off its own name.

    A row is one of these exactly when its vocabulary is neither the
    do-nothing word alone nor one of the three families' — it declares a
    word and has no parameter to receive it. This used to pin an exemption
    list, and there is no list any more: such a row is held to its word
    like every other, so what has to be true is that the word it declares
    names it. Reading the row off the table is what makes a second such
    row a red suite instead of a quiet second.
    """
    families = (MODEL_WORDS_NONE, MODEL_WORDS_OUTCOME, MODEL_WORDS_IV,
                MODEL_WORDS_DOSE_RESPONSE)
    odd = {s.id for s in _EFFECT_STRATEGIES if s.models not in families}
    assert odd == {"iv_overidentified"}
    word, = set(next(s for s in _EFFECT_STRATEGIES
                     if s.id == "iv_overidentified").models) - {AUTO}
    assert _answer(_OVERID, word)["numeric_estimate"]["method"] in (
        _THE_ROWS_A_WORD_NAMES[word])


def test_the_only_shape_lever_a_caller_can_reach_is_the_model_word():
    """THE PREMISE, measured — the one thing this repair rests on.

    The block merges the form's origin with the origins of levers that no
    ``model=`` names, so a ``caller_asserted`` there is read as the caller's
    word. That reading is sound exactly while no other shape lever can be
    written at the public entry: :func:`pulled_by` answers ``caller_asserted``
    for any lever left at something other than :data:`UNSET`, and a lever
    nobody can set is left at ``UNSET`` on every call.

    Read off the source rather than off a list here — the levers are
    whatever ``pulled_by`` is asked about — so a lever added tomorrow is
    counted, and one wired to the entry turns this red. The scan is held to
    finding some, because a scan that finds nothing passes this vacuously.
    """
    levers: set[str] = set()
    for path in sorted((ROOT / "themis" / "estimation").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "pulled_by"
                    and node.args
                    and isinstance(node.args[0], ast.Name)):
                levers.add(node.args[0].id)
    assert levers, "no shape lever found; this scan is measuring nothing"
    reachable = set(inspect.signature(estimate_program).parameters)
    assert levers & reachable == set(), (
        f"{sorted(levers & reachable)} is a shape lever a caller can now "
        f"write, so a caller_asserted origin in a mechanism block no longer "
        f"means the model word — the block has to say which lever it is, "
        f"and the rule reading it has to ask")
    assert "model" in reachable


# --- the two things this side declares, held to the producer ---------------


def test_the_two_spellings_are_one_arm_in_the_producer_too():
    """The alias is the verifier's own copy of the ``logistic=`` argument
    the mediation family names at its call sites, so it is pinned by
    driving that argument rather than by reading the set back."""
    y = pd.Series([True, False, True, False])
    assert outcome_form("logistic", y, logistic="logit")[0] == "logit"
    assert outcome_form("logistic", y)[0] == "logistic"
    assert {"logistic", "logit"} == set(_ONE_ARM_TWO_SPELLINGS)


def test_the_word_for_declining_to_choose_is_the_one_the_envelope_records():
    """This side spells ``auto`` itself rather than importing it. A run that
    leaves the option alone is what pins the two equal."""
    result = _answer(_BACKDOOR, AUTO)
    assert (result["estimation_context"]["model_preference"]
            == _DECLINED_TO_CHOOSE)


def test_the_helper_answers_both_ways_about_a_word_and_a_shape():
    """The predicate on its own, so that a gate reading it cannot be the
    only thing that says what it means."""
    assert word_that_could_not_have_asked_for("linear", "linear") is None
    assert word_that_could_not_have_asked_for("logistic", "logit") is None
    assert word_that_could_not_have_asked_for("logit", "logistic") is None
    assert word_that_could_not_have_asked_for("2sls", "2sls") is None
    assert word_that_could_not_have_asked_for("linear", "logistic") is not None
    assert word_that_could_not_have_asked_for("logistic", "linear") is not None
    assert word_that_could_not_have_asked_for("2sls", "acr") is not None
