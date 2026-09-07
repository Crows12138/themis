"""One cascade row declares a vocabulary; three estimators answer under it.

``Strategy.models`` says which words a ROW's ``model=`` accepts, and
:func:`run_cascade` refuses a word the answering row does not declare. That
is the whole of #602's fix and it does not reach the ``doubly_robust`` row,
because the row is not what answers: ``ate_estimator`` picks between AIPW,
TMLE and IPW after the driver's gate has already run, so the vocabulary the
row declares is one estimator's wearing the other two's names. It was
AIPW's.

WHAT THAT COST, measured end to end before it was changed. ``model='linear'``
on a TMLE run came back a LOGISTIC fit, with ``estimation_context.
model_preference`` recording ``'linear'`` beside it; on an IPW run the word
was read by nothing at all, that estimator weighting by the propensity and
fitting no outcome model whatever. AIPW, the same word on the same row,
honoured it. One row, one word, three fates — which is the sentence #602
wrote about the entry's hand-written union, one level down.

The judgement therefore happens where both halves are in one place, which
is the argument #602 made for putting it in the driver: here that is
``_try_doubly_robust_estimate``, the first place holding the caller's word
and the estimator that will answer under it. The refusal is the same block
the driver writes, so a caller who names a shape on a TMLE query reads what
a caller who names one on a front-door query reads.

WHAT THIS IS NOT. TMLE has two arms — it fits the logit link for a bool
outcome and the line otherwise — so it could be given a lever instead of
being made to refuse. That is a capability this build does not have, with a
root cause of its own (an estimator with two arms and no way to ask for
one), and answering it here would be answering a different question with
this one's evidence. What is wrong today is a row promising a lever that
does not exist; that is what this closes.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.aipw import estimate_aipw_ate, estimate_ipw_ate
from themis.estimation.dispatch import (
    _ATE_ESTIMATORS,
    _WORDS_BY_DOUBLY_ROBUST_ESTIMATOR,
    _EFFECT_STRATEGIES,
)
from themis.estimation.form import MODEL_WORDS_NONE, MODEL_WORDS_OUTCOME
from themis.estimation.tmle import estimate_tmle_ate
from themis import routing


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_BACKDOOR = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "u"}]},
    "statements": [
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "variable", "predicate": "z"},
        _cause("x", "y"), _cause("z", "x"), _cause("z", "y"),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True}, "given": []}},
    ],
}


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    n = 1200
    z = rng.integers(0, 2, n)
    latent = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.2 + 0.25 * z + 0.15 * latent).astype(int)
    y = (rng.random(n) < np.clip(0.2 + 0.3 * x + 0.2 * latent, 0, 1)
         ).astype(int)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _run(frame, estimator, word):
    out = themis.estimate(_BACKDOOR, frame, ci_bootstrap=0,
                          ate_estimator=estimator, model=word)
    return out["results"][0]


#: The estimator that owns each row of the table, so the signature check
#: below reads the function rather than a name.
_FUNCTION = {
    "aipw": estimate_aipw_ate,
    "tmle": estimate_tmle_ate,
    "ipw": estimate_ipw_ate,
}

#: What an outcome-model lever is called where one exists. Two spellings
#: because two families named it, and the point of the check is presence.
_LEVER_NAMES = ("outcome_model", "model")


# --- the table is the estimators' own answer, not a copy of it -------------


def test_the_table_names_every_estimator_this_row_can_run_and_no_other():
    """Bound to the route guard rather than written beside it. A fourth
    doubly-robust estimator arrives at a KeyError today, which is loud, and
    at this line first, which says what to do about it."""
    guard = {e for e in _ATE_ESTIMATORS if e != "gformula"}
    assert set(_WORDS_BY_DOUBLY_ROBUST_ESTIMATOR) == guard
    row = next(s for s in _EFFECT_STRATEGIES if s.id == "doubly_robust")
    assert row.models == MODEL_WORDS_OUTCOME
    # And the row still declares the widest of the three, which is why the
    # judgement cannot be left to it: the gate it feeds lets every one of
    # those words through to all three estimators.
    assert all(words <= row.models
               for words in _WORDS_BY_DOUBLY_ROBUST_ESTIMATOR.values())


@pytest.mark.parametrize("estimator", sorted(_FUNCTION))
def test_a_row_takes_words_exactly_when_its_estimator_has_a_lever(estimator):
    """The binding, and the reason this table cannot go stale quietly: an
    estimator takes a word when it has a parameter to receive one, so the
    row is read off the signature rather than remembered."""
    params = inspect.signature(_FUNCTION[estimator]).parameters
    has_lever = any(name in params for name in _LEVER_NAMES)
    expected = MODEL_WORDS_OUTCOME if has_lever else MODEL_WORDS_NONE
    assert _WORDS_BY_DOUBLY_ROBUST_ESTIMATOR[estimator] == expected


def test_the_guard_and_the_table_are_two_statements_about_one_set():
    """The route decides whether this row runs at all, and it names the
    same three. Read from the routing table so that adding an estimator
    there without a row here is a red suite."""
    route = routing.route("doubly_robust")
    assert route.id == "doubly_robust"
    for estimator in _WORDS_BY_DOUBLY_ROBUST_ESTIMATOR:
        assert estimator in _ATE_ESTIMATORS


# --- the estimator that has the lever still honours it ---------------------


@pytest.mark.parametrize("word,form", [
    ("auto", "logistic"), ("linear", "linear"), ("logistic", "logistic"),
])
def test_aipw_still_answers_under_every_word_it_declares(frame, word, form):
    """The half that must not change. AIPW has the parameter, so its
    vocabulary is the row's, and the shape follows the word."""
    result = _run(frame, "aipw", word)
    assert result.get("estimator_failure") is None
    assert result["numeric_estimate"]["method"] == "aipw"
    mechanism = result["extensions"]["mechanism_audit"]["mechanisms"][0]
    assert mechanism["form"] == form


# --- and the two without one refuse, rather than answering as if silent ----


@pytest.mark.parametrize("estimator", ["tmle", "ipw"])
@pytest.mark.parametrize("word", ["linear", "logistic"])
def test_an_estimator_with_no_lever_refuses_the_word(frame, estimator, word):
    """WHAT WAS WITHDRAWN, stated rather than slipped in: these four
    combinations produced numbers before this and now refuse. The numbers
    were the estimator's own choice of shape reported beside the caller's
    different word, which is the one thing the pair of records cannot
    both be."""
    result = _run(frame, estimator, word)
    assert result.get("numeric_estimate") is None
    failure = result["estimator_failure"]
    assert failure["failure_type"] == "unknown_option"
    assert failure["estimator"] == estimator
    assert failure["details"]["option"] == "model"
    assert failure["details"]["given"] == word
    assert failure["details"]["known"] == ["auto"]


@pytest.mark.parametrize("estimator", sorted(_FUNCTION))
def test_declining_to_choose_still_answers_on_all_three(frame, estimator):
    """The other side of every refusal above. ``auto`` is the word every
    row serves, and a gate that closed this by refusing the ordinary run
    would be worse than the hole."""
    result = _run(frame, estimator, "auto")
    assert result.get("estimator_failure") is None
    assert result["numeric_estimate"]["point"] is not None


def test_the_refusal_leaves_no_answer_claiming_the_word_beside_it(frame):
    """Why this is the same repair as the pair one module over.

    The envelope used to carry ``model_preference: 'linear'`` beside a
    logistic fit, and that is exactly what the mechanism-audit pair now
    refuses to let stand. Withdrawing the answer is what makes the two
    records agree: there is a word on the context and no fit attributing
    anything to anybody, because there is no fit.
    """
    result = _run(frame, "tmle", "linear")
    assert result["estimation_context"]["model_preference"] == "linear"
    assert "mechanism_audit" not in (result.get("extensions") or {})
    themis.verify_assumption_ledger(result)
