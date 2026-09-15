"""The word a caller wrote is held by whatever honoured it.

``estimation_context.model_preference`` is the run's record of what was asked
for. Two kinds of word can stand there and they are honoured by two different
things. A shape word — ``linear``, ``logistic``, ``forest``, ``drlearner`` —
asks for a functional form, and the record of what became of it is the
mechanism block that discloses a fitted shape and says who settled it. A row
word — IV's four — asks for an ESTIMATOR, and the record is ``method``: that
option picks which row runs, so the row that ran is the answer to what happened
to the request.

Only the first half was read. The check that read it lived inside the check on
the block, behind that function's opening line — no disclosed mechanism,
nothing to check, return — so the direction that reads the CONTEXT could not
fire on the answers it was written for. A word no disclosed fit attributes to
anybody is most completely unwitnessed exactly when there is no fit to
attribute it to. Measured with the leaf sweep's own door set: 29 answers record
``auto`` beside a route that has no shape lever at all — proximal,
measurement-error, transport, RMST, the three IV rows that fit nothing, the
counterfactual plug-ins — and on every one of them the field could be rewritten
to say the caller had asked for 2SLS, or for a link function, and all of the
public doors said yes.

THE PRODUCER'S HALF ALREADY EXISTS, which is what makes this a check rather
than a new restriction. ``run_cascade`` will not answer a query with a word the
answering row does not accept: it rolls the result back and records the refusal,
naming the words that row knows. So no honest envelope carries a concrete word
beside a method whose row never offered it — and that is driven below, because
a rule that refuses what the producer can emit is a rule that refuses honest
answers.

WHAT THIS REPLACED, AND WHY THE BLOCK HALF IS ONE BICONDITIONAL. The old
arrangement needed an exemption: one row honours ``2sls`` by BEING the
two-stage fit, has no parameter to receive the word, and therefore discloses a
block saying the caller settled nothing. Asked that SOME block claim the
caller, that answer was refused, so it was exempted — and the note beside the
exemption conceded that the word on those rows stayed corroborated by nothing.
The rule now says, of every disclosed block, that the caller settled its shape
if and only if the word names its form: the exempted row fits
``two_stage_least_squares``, which no word names, so the biconditional holds on
the false side and there is nothing to exempt. Both halves are needed and both
are driven below — holding a row word to its method alone was measured to free
a forgery in the other direction, on an answer whose word DID settle its form.

THE DECLARED CEILING. An answer that reports no fit at all is left alone. There
is no second record for the word to disagree with — nothing was honoured and
nothing was dropped — and 33 corpus rows are still declared unwitnessed for
that reason. Beyond it, on the one row that honours a word by being it, ``auto``
and ``2sls`` remain interchangeable: the row ignores the lever, so the two
produce the same run down to the byte, and no record can tell which was written.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.form import AUTO, MODEL_WORDS_IV
from themis.verifier import assumption_ledger_rules as ledger_rules
from themis.verifier.assumption_ledger_rules import _THE_ROWS_A_WORD_NAMES


# --- the two designs, the one frame ----------------------------------------


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

#: One instrument: the row that reads ``model=`` as which estimator to run.
_IV = _program([
    {"kind": "variable", "predicate": "z"},
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "y"},
    _cause("z", "x"), _cause("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _EFFECT_QUERY,
])

#: Two instruments: the row that honours ``2sls`` by being it.
_OVERID = _program([
    {"kind": "variable", "predicate": "z"},
    {"kind": "variable", "predicate": "z2"},
    {"kind": "variable", "predicate": "x"},
    {"kind": "variable", "predicate": "y"},
    _cause("z", "x"), _cause("z2", "x"), _cause("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _EFFECT_QUERY,
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


def _under(result, word) -> str | None:
    """What the door says when the recorded word is rewritten to ``word``."""
    bent = copy.deepcopy(result)
    bent["estimation_context"]["model_preference"] = word
    return _refuses(bent)


#: Which row each word names, and where to drive it — the measurement the
#: table under test is a transcription of. Written out here rather than read
#: from that table: a test that asks the table which run to make cannot
#: disagree with it.
_WORD_RUNS = [
    (_IV, "wald", "iv_wald"),
    (_IV, "stratified_wald", "iv_stratified_wald"),
    (_IV, "2sls", "iv_2sls"),
    (_IV, "acr", "iv_acr"),
    (_OVERID, "2sls", "iv_2sls_overid"),
]


# --- the table is the producer's vocabulary, measured ----------------------


def test_the_table_names_exactly_the_words_that_pick_a_row():
    """Which words belong in it is not this side's opinion.

    ``iv`` is the one family whose ``model=`` selects an estimator instead of
    a link function, and its vocabulary says which words those are. A word
    added to that family and not to the table would be read as a shape word
    and asked for a block it has none of; a shape word listed here would
    stop being asked for its block at all.
    """
    assert set(_THE_ROWS_A_WORD_NAMES) == set(MODEL_WORDS_IV) - {AUTO}
    assert AUTO not in _THE_ROWS_A_WORD_NAMES


@pytest.mark.parametrize("program,word,method", _WORD_RUNS)
def test_each_word_is_honoured_by_the_row_the_table_names(program, word,
                                                          method):
    """Driven end to end, because the claim is about what RAN under the word.

    A unit assertion on the table would restate the table. What is being
    measured is that writing the word at the public entry produces the row
    the table says it names — and that the answer it produces is not refused,
    which is the honest side of every check below.
    """
    result = _answer(program, word)
    assert result["estimation_context"]["model_preference"] == word
    assert result["numeric_estimate"]["method"] == method
    assert method in _THE_ROWS_A_WORD_NAMES[word]
    assert _refuses(result) is None


def test_the_table_names_no_row_this_build_never_runs():
    """The other direction, so the table cannot grow a member by guess.

    Every method it names is reached by one of the runs above. A row listed
    here that nothing produces would be a word honoured by an answer this
    build cannot give, which reads as coverage and is not.
    """
    named = set().union(*_THE_ROWS_A_WORD_NAMES.values())
    assert named == {method for _, _, method in _WORD_RUNS}


# --- a row word, held to the row that ran ---------------------------------


@pytest.mark.parametrize("word", ["acr", "2sls", "stratified_wald"])
def test_a_word_naming_a_row_that_did_not_run_is_refused(word):
    """The Wald answer, told it was asked for something else.

    This is the bend the corpus reports as free on 29 rows, and the reason it
    was free is that none of them discloses a fitted shape: the only check
    that read this field returned before looking whenever that was so.
    """
    result = _answer(_IV, "wald")
    assert result["numeric_estimate"]["method"] == "iv_wald"
    complaint = _under(result, word)
    assert complaint is not None
    assert "is honoured by that row running" in complaint
    assert "iv_wald" in complaint


def test_a_word_naming_a_shape_where_no_shape_was_fitted_is_refused():
    """The same field on the same answer, forged the other way.

    ``iv_wald`` fits no functional form, so it discloses no mechanism. A
    shape word there is corroborated by nothing on the envelope — which used
    to be the reason it was not asked about, and is the reason it must be.
    """
    result = _answer(_IV, AUTO)
    assert _blocks(result) == []
    for word in ("logistic", "drlearner"):
        complaint = _under(result, word)
        assert complaint is not None
        assert "no disclosed mechanism" in complaint


def test_the_row_that_honours_a_word_by_being_it_needs_no_exemption():
    """What the old arrangement paid for this row, and does not any more.

    ``iv_overidentified`` has no ``model=`` parameter: the row IS the
    two-stage fit, so a caller who writes ``2sls`` gets what they named and
    the block correctly says they settled nothing. Asked for a block, that
    honest answer was refused, so the row was exempted from the only check
    that read the field — and being exempted, every other word passed there
    too. Held against the method instead, the honest word passes and the
    others do not.
    """
    result = _answer(_OVERID, "2sls")
    assert result["numeric_estimate"]["method"] == "iv_2sls_overid"
    assert _refuses(result) is None
    for word in ("wald", "acr"):
        assert "is honoured by that row running" in str(_under(result, word))
    assert "no disclosed mechanism" in str(_under(result, "logistic"))
    # And the residual, stated where it can be read: the row ignores the
    # lever, so the do-nothing word and the word it honours produce the same
    # run, and no record distinguishes them.
    assert _under(result, AUTO) is None


def test_a_block_that_fitted_what_was_asked_for_must_say_the_caller_asked():
    """The block half, and the measurement that made it a biconditional.

    ``iv_2sls`` under ``2sls`` discloses a block whose form IS the word, so
    that block's origin and the context's word are one decision recorded
    twice. Rewriting the origin alone is refused by the pairing that holds it
    equal to its ledger line; rewriting both copies says the estimator chose
    2SLS for itself beside a context saying the caller asked for it. Held to
    its method and nothing else — the shape of this rule before the block
    half was asked of every block — that forgery passed every door.
    """
    result = _answer(_IV, "2sls")
    block = _blocks(result)[0]
    assert block["form"] == "2sls"
    shapes = {a["id"] for a in block["assumptions"]}

    one_copy = copy.deepcopy(result)
    for entry in (one_copy["extensions"]["mechanism_audit"]["mechanisms"][0]
                  ["assumptions"]):
        entry["settled_by"] = "default"
    assert _refuses(one_copy) is not None

    both = copy.deepcopy(one_copy)
    for line in both["extensions"]["assumption_ledger"]["assumptions"]:
        if line.get("id") in shapes:
            line["provenance"] = "default"
    complaint = _refuses(both)
    assert complaint is not None
    assert "says no caller settled it" in complaint


def test_the_row_that_is_the_word_is_the_same_rule_on_its_other_side():
    """And the honest answer that half must not refuse.

    ``iv_2sls_overid`` fits ``two_stage_least_squares``, which no caller's
    word names, so its block says the shape was inherent to the route. The
    biconditional holds on the false side, which is the whole of why the
    exemption list is gone rather than merely shortened.
    """
    result = _answer(_OVERID, "2sls")
    block = _blocks(result)[0]
    assert block["form"] == "two_stage_least_squares"
    assert not any(a["settled_by"] == "caller_asserted"
                   for a in block["assumptions"])
    assert _refuses(result) is None


def test_an_answer_that_reports_no_fit_is_the_declared_ceiling():
    """The limit, asked of the check directly rather than of a run.

    Nothing this file can drive produces a ledger with no fit beside it: a
    word the answering row refuses leaves no ledger either, as the next test
    measures. The rows that do are in the corpus, and the declaration file
    still lists this leaf on 33 of them. So the ceiling is asked where it
    lives — with no fit reported there is no second record for the word to
    disagree with, and a check that refused here would be refusing an answer
    for having nothing to say.
    """
    ledger_rules._check_the_word_the_caller_pointed_at(
        {"estimation_context": {"model_preference": "linear"}}, {})


def test_the_producer_already_refuses_what_this_rule_calls_impossible():
    """THE PREMISE, measured — without it the rule above refuses honest work.

    The rule says a concrete word beside a method whose row never offered it
    cannot be honest. What makes that true is not the verifier: the driver
    holds both the word and the row it was aimed at, and where the row that
    answered does not accept the word it withdraws the number and records
    the refusal instead. Wire a route to answer under a word it ignores and
    this turns red, which is the moment the rule above would start refusing
    answers that happened.
    """
    out = themis.estimate(_IV, _frame(), model="drlearner", ci_bootstrap=0)
    results = out.get("results") or ()
    assert results
    for result in results:
        assert result.get("numeric_estimate") is None
        assert result["estimation_context"]["model_preference"] == "drlearner"
        failure = result.get("estimator_failure") or {}
        assert failure.get("failure_type") == "unknown_option"
        assert failure["details"]["given"] == "drlearner"
        assert "drlearner" not in failure["details"]["known"]
