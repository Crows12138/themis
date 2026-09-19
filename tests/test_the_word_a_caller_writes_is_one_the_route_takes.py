"""``model=`` is one option over five vocabularies, and it had no reader.

Which words a route accepts was decided in each estimator's own control
flow and written in each estimator's own ``ModelName``. Nothing connected
either to the caller, so one word had four fates, measured on live runs
before any of this was written:

    back-door   ``model='forest'``  a bare ValueError, out through the
                                    public entry and past the envelope
    front-door  ``model='forest'``  a structured refusal naming its words
    IV          ``model='forest'``  accepted, ignored, answered anyway
    mediation   ``model='forest'``  accepted, ignored, answered anyway

and the mirror, which is why forwarding the option to the two rows that
dropped it would not have been the fix: ``iv`` implements five words down
to the remedy it suggests when one answers the wrong question, and the
entry's vocabulary — hand-written as the union of the OTHER families —
shared exactly ``auto`` with it. Every word IV knew was refused at the
door by a message listing five alternatives that all ran the same
estimator; every word the door allowed reached IV and did nothing.

Both directions are pinned here because a table checked one way is a table
whose other side rots: a word a route declares must reach it and change
the answer, and a word it does not declare must come back as that route's
own refusal rather than as a silence, a crash, or somebody else's list.
"""
from __future__ import annotations

import typing

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import backdoor, frontdoor, iv, joint
from themis.estimation.claim import answered, passed
from themis.estimation.dispatch import _DECLARED_MODELS, _EFFECT_STRATEGIES
from themis.estimation.form import (
    AUTO,
    MODEL_WORDS_DOSE_RESPONSE,
    MODEL_WORDS_IV,
    MODEL_WORDS_NONE,
    MODEL_WORDS_OUTCOME,
    outcome_form,
)
from themis.estimation.strategy import (
    EffectKnobs, Estimand, Role, Strategy, check_table, run_cascade,
)
from themis import routing


# --- the programs, one per route ------------------------------------------


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
    """One frame every route above can answer on: an instrument, a
    confounder, a mediator and a binary outcome."""
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


def _run(program, word):
    """``(method, estimator_failure)`` for one program under one word."""
    out = themis.estimate(program, _frame(), model=word, ci_bootstrap=0)
    for result in out.get("results") or ():
        estimate = result.get("numeric_estimate")
        method = estimate.get("method") if isinstance(estimate, dict) else None
        if method or result.get("estimator_failure"):
            return method, result.get("estimator_failure")
    return None, None


# --- every row says which words it takes -----------------------------------


def test_every_row_of_the_cascade_declares_the_words_it_takes():
    """The measurement the field was added to end. Twenty-five rows, and
    before this five of them could hear the caller's word at all — the
    other twenty took it, recorded it on the envelope as the caller's
    preference, and answered through something else."""
    assert len(_EFFECT_STRATEGIES) == 25
    for strategy in _EFFECT_STRATEGIES:
        assert strategy.models, strategy.id
        assert AUTO in strategy.models, strategy.id


def test_a_row_may_not_declare_a_set_without_the_word_for_declining():
    """``auto`` is the caller not choosing, which every row serves. A set
    without it describes no run this build can make."""
    with pytest.raises(ValueError, match="declined to choose"):
        Strategy(
            route=routing.Route(id="r", precedence=10,
                                applies_when=lambda f: True,
                                ends=routing.ESTIMATES),
            role=Role.CLAIM, produces=Estimand.QUERY_EFFECT,
            models=frozenset({"linear"}),
            run=lambda f, r, k: answered(),
        )


def test_the_entry_accepts_every_word_some_row_takes_and_no_other():
    """Derived, not written twice. Hand-written it was the union of three
    families and not the fourth, so the four words IV implements were
    refused at the door — the one measurement that "each route asks its
    own question" could not explain, because the door never let them
    through for a route to ask about."""
    union = frozenset().union(*(s.models for s in _EFFECT_STRATEGIES))
    assert frozenset(_DECLARED_MODELS) == union
    assert MODEL_WORDS_IV <= union
    assert MODEL_WORDS_OUTCOME <= union
    assert MODEL_WORDS_DOSE_RESPONSE <= union


@pytest.mark.parametrize("module,declared", [
    (backdoor, MODEL_WORDS_OUTCOME),
    (frontdoor, MODEL_WORDS_OUTCOME),
    (joint, MODEL_WORDS_OUTCOME),
    (iv, MODEL_WORDS_IV),
])
def test_each_family_s_annotation_says_what_the_table_declares(
    module, declared,
):
    """Four modules define a type called ``ModelName`` and two of them mean
    different things by it; three are the same three words written out
    three times. Held equal to the declared set rather than merged into it,
    because the annotation is what a reader of that module sees and the set
    is what the driver enforces — the arrangement the verifier uses for the
    same reason."""
    assert frozenset(typing.get_args(module.ModelName)) == declared


# --- a word a route takes reaches it and changes the answer ----------------


@pytest.mark.parametrize("program,word,method", [
    (_BACKDOOR, "auto", "backdoor_logistic"),
    (_BACKDOOR, "linear", "backdoor_linear"),
    (_BACKDOOR, "logistic", "backdoor_logistic"),
    (_FRONTDOOR, "auto", "frontdoor_logistic"),
    (_FRONTDOOR, "linear", "frontdoor_linear"),
    (_FRONTDOOR, "logistic", "frontdoor_logistic"),
    # The two that used to be answered through something else. ``linear``
    # came back as ``mediation_logit_imai`` while the envelope recorded the
    # caller's ``'linear'`` beside it.
    (_MEDIATION, "auto", "mediation_logit_imai"),
    (_MEDIATION, "linear", "mediation_linear_imai"),
    (_MEDIATION, "logistic", "mediation_logit_imai"),
    # IV's own vocabulary, which the entry used to refuse outright.
    (_IV, "auto", "iv_wald"),
    (_IV, "wald", "iv_wald"),
    (_IV, "2sls", "iv_2sls"),
    (_IV, "acr", "iv_acr"),
    (_IV, "stratified_wald", "iv_stratified_wald"),
])
def test_a_word_the_route_declares_is_the_one_that_runs(
    program, word, method,
):
    ran, failure = _run(program, word)
    assert failure is None, failure
    assert ran == method


# --- and a word it does not take comes back as that route's refusal --------


@pytest.mark.parametrize("program,word,known", [
    (_BACKDOOR, "forest", sorted(MODEL_WORDS_OUTCOME)),
    (_BACKDOOR, "drlearner", sorted(MODEL_WORDS_OUTCOME)),
    (_FRONTDOOR, "forest", sorted(MODEL_WORDS_OUTCOME)),
    (_MEDIATION, "forest", sorted(MODEL_WORDS_OUTCOME)),
    (_MEDIATION, "drlearner", sorted(MODEL_WORDS_OUTCOME)),
    # The other direction on the same query: IV's words are not the
    # outcome-model families' words either.
    (_IV, "linear", None),
    (_IV, "logistic", None),
    (_IV, "forest", None),
])
def test_a_word_the_route_does_not_declare_is_refused_by_that_route(
    program, word, known,
):
    """A refusal and not a silence, and not an exception either: the bare
    ``ValueError`` back-door used to raise left through the public entry,
    so the caller got a traceback where the same mistake one route over
    got a block they could read."""
    ran, failure = _run(program, word)
    assert ran is None
    assert failure is not None
    assert failure["failure_type"] == "unknown_option"
    assert failure["details"]["option"] == "model"
    assert failure["details"]["given"] == word
    if known is not None:
        assert failure["details"]["known"] == known


def test_a_row_that_is_an_estimator_takes_the_word_that_names_it():
    """``iv_overidentified`` has no ``model`` parameter and needs none: the
    row IS the two-stage fit, several instruments and the Sargan test
    beside it. Declaring only ``auto`` there would have refused a caller
    for writing the right word — honouring a request by being what it asks
    for is honouring it."""
    ran, failure = _run(_OVERID, "2sls")
    assert failure is None, failure
    assert ran == "iv_2sls_overid"
    assert _run(_OVERID, "auto")[0] == "iv_2sls_overid"


def test_that_row_still_refuses_the_words_it_is_not():
    """The other side. Its set is one word wider than ``auto``, not open."""
    ran, failure = _run(_OVERID, "logistic")
    assert ran is None
    assert failure["estimator"] == "iv_overidentified"
    assert failure["details"]["known"] == ["2sls", "auto"]


def test_a_word_outside_every_vocabulary_is_still_the_caller_s_typo():
    """The entry keeps the one judgement it can make. A word no row takes
    is a mistake at the call, and naming it there is what stopped a typo
    from riding to whichever estimator happened to read the option."""
    with pytest.raises(ValueError, match="unknown model"):
        themis.estimate(_BACKDOOR, _frame(), model="lienar", ci_bootstrap=0)


# --- the arm the caller names is the arm the system would have picked ------


def test_naming_the_arm_resolves_like_declining_to_choose_does():
    """``logistic=`` says what THIS family calls the non-linear arm, and
    translating only the system's choice left the same arm coming back
    under two words: a bool outcome under ``auto`` resolved to ``'logit'``
    and ran, and the caller who named that very arm got ``'logistic'`` —
    refused, by a list containing ``'logit'``, which the entry's option has
    never carried."""
    y = pd.Series([True, False, True, False])
    assert outcome_form(AUTO, y, logistic="logit")[0] == "logit"
    assert outcome_form("logistic", y, logistic="logit")[0] == "logit"
    # And the families that spell it the ordinary way are untouched.
    assert outcome_form("logistic", y)[0] == "logistic"
    assert outcome_form(AUTO, y)[0] == "logistic"
    # A word nobody resolves still passes through, for the estimator that
    # owns the question to refuse by name.
    assert outcome_form("forest", y, logistic="logit")[0] == "forest"


# --- the producer gate, both sides ----------------------------------------


def _writes_an_answer(f, r, k):
    """A row that mutates the result on its way to claiming, as every real
    one does — otherwise "the answer does not stand" is asserted about a
    result nothing ever wrote to."""
    r["numeric_estimate"] = {"method": "made_up", "point": 1.0}
    r["derivation"] = {"steps": []}
    r["status"] = "numerically_solved"
    return answered()


def _table(models):
    return check_table((
        Strategy(
            route=routing.Route(id="backdoor", precedence=10,
                                applies_when=lambda f: True,
                                ends=routing.ESTIMATES),
            role=Role.CLAIM, produces=Estimand.QUERY_EFFECT,
            models=models,
            run=_writes_an_answer,
        ),
    ))


def _knobs(word):
    return EffectKnobs(
        random_state=42, ci_bootstrap=0, model=word, cluster=None,
        reference_data=None, selection_values=None, program=None,
    )


def test_a_row_that_answers_under_a_word_it_did_not_declare_is_refused():
    """And the answer it produced does not stand. Sixteen of the
    twenty-five rows fit one shape because their method IS that shape, so
    they never read the option and have nothing of their own to refuse
    with — the caller who named a shape on such a query was answered as
    though they had said nothing. The driver is the only place holding
    both the word and the row it was aimed at."""
    result: dict = {"query_id": "q1", "status": "structurally_solved"}
    evaluation = run_cascade(_table(MODEL_WORDS_NONE), None, result,
                             _knobs("linear"), query_id="q1")
    assert evaluation.fired is None
    assert evaluation.declined == (("backdoor", "estimator_refused"),)
    failure = result["estimator_failure"]
    assert failure["estimator"] == "backdoor"
    assert failure["failure_type"] == "unknown_option"
    assert failure["details"] == {
        "option": "model", "given": "linear", "known": ["auto"],
    }
    # What the row wrote on the way is gone with it: a number produced
    # with the caller's instruction ignored is the silence this field
    # exists to end, not a result to ship beside the refusal.
    assert "numeric_estimate" not in result
    assert "derivation" not in result
    assert result["status"] == "structurally_solved"


def test_a_row_that_answers_under_a_word_it_declared_is_left_alone():
    """The other side of the same gate. Without this the rule would be
    satisfied by a table where every row declares every word, which says
    nothing about any run."""
    evaluation = run_cascade(
        _table(MODEL_WORDS_OUTCOME), None, {}, _knobs("linear"),
        query_id="q1",
    )
    assert evaluation.fired == ("backdoor", Estimand.QUERY_EFFECT)


def test_a_row_that_passes_under_a_word_it_did_not_declare_is_left_alone():
    """The case that decides where the check goes. A row that hands the
    query on has not used the knob, and the row that answers next may take
    a word this one does not — which is the IV escape, 80 of 434 measured
    evaluations. Checking before the offer would refuse there and take an
    answer away that the caller's word was aimed at."""
    table = check_table((
        Strategy(
            route=routing.Route(id="first", precedence=10,
                                applies_when=lambda f: True,
                                ends=routing.ESTIMATES),
            role=Role.CLAIM, produces=Estimand.QUERY_EFFECT,
            models=MODEL_WORDS_NONE,
            run=lambda f, r, k: passed("not_identified"),
        ),
        Strategy(
            route=routing.Route(id="second", precedence=20,
                                applies_when=lambda f: True,
                                ends=routing.ESTIMATES),
            role=Role.CLAIM, produces=Estimand.QUERY_EFFECT,
            models=MODEL_WORDS_OUTCOME,
            run=_writes_an_answer,
        ),
    ))
    evaluation = run_cascade(table, None, {}, _knobs("linear"),
                             query_id="q1")
    assert evaluation.fired == ("second", Estimand.QUERY_EFFECT)
