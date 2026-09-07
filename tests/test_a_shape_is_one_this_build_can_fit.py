"""The one word saying what a number was fitted through, held to the method.

``extensions.mechanism_audit.mechanisms[]`` carries four fields and three
were held: ``method`` against the estimate's own account of the run, each
named assumption against the estimate's declaration, ``target`` against
the question. ``form`` — the shape word, the reason the block exists —
took any string at all, so on every answer shape it could be rewritten and
the public door said yes.

WHY NOTHING HELD IT. Which shapes a build can fit was decided everywhere
and written nowhere. The estimators do refuse outside their set — a model
nobody declared comes back as ``unknown model``, and ``iv`` even lists its
five in the refusal — but the decision lives in control flow and in a
sentence, so no reader downstream had anything to look a shape up in.
``form.py`` was right to refuse a GLOBAL table ("which forms an estimator
can fit is that estimator's question"); what never followed was the
per-estimator declaration that sentence implies.

WHERE THE ROWS CAME FROM, AND WHY NOT FROM THE CORPUS. The note this
closes said ``form`` is "a function of ``method`` across the corpus
(thirty-one methods, one form each)", and the qualifier was carrying the
sentence: ``tmle`` fits ``logistic`` for a bool outcome and ``linear``
otherwise, ``aipw`` likewise, and the two counterfactual plug-ins name the
route their borrowed risk came under. The corpus is a sample of what
somebody once ran — thirty-five methods where the build produces
forty-nine — so the rows were measured by watching the whole suite
produce them, and the constructed families are built the way the producer
builds them so a member nobody has exercised is covered rather than
refused.

So this file holds: the two tables are two statements and agree; a shape
outside its method is refused at the producer's door and at the reader's;
the census's three lies about a form are all refused; and the answers the
corpus does NOT contain are still accepted, because a gate that closed
this hole by refusing honest runs would be worse than the hole.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.estimation import form as producer
from themis.verifier import VerificationError
from themis.verifier.mechanism_rules import (
    FITS as VERIFIER_FITS, shape_the_method_cannot_fit,
)


# ===================================================== the two declarations


def test_the_two_tables_are_two_statements_and_agree():
    """Re-declared rather than imported, and pinned equal.

    The producer builds six families by spelling the form into the method
    name; a verifier sharing that construction would agree with the
    producer by running the producer's code, which is not a second look.
    """
    assert VERIFIER_FITS == producer.FITS


def test_no_row_is_empty_and_no_shape_is_blank():
    """A row with nothing in it refuses everything, including the truth;
    a row containing the empty string accepts the census's own blank."""
    for method, shapes in producer.FITS.items():
        assert shapes, method
        assert all(s and s.strip() for s in shapes), method


def test_every_method_that_fits_two_shapes_says_what_picks():
    """Both directions — the import-time gate, asked again from here so a
    reader of this file can see what it is."""
    for method, shapes in producer.FITS.items():
        if len(shapes) > 1:
            assert method in producer.FITS_TURNS_ON, method
    for method in producer.FITS_TURNS_ON:
        assert len(producer.FITS[method]) > 1, method


def test_what_picks_is_quoted_where_a_reader_of_the_refusal_meets_it():
    """A sentence in a table with no reader is a sentence nothing keeps
    true. This one is spent in the refusal, so an estimator naming the
    wrong shape is told which occasion it should have been reading."""
    with pytest.raises(ValueError) as caught:
        producer.fits("tmle", "forest")
    assert producer.FITS_TURNS_ON["tmle"] in str(caught.value)


def test_simex_declares_the_product_of_its_own_two_levers():
    """The one row assembled from another module's vocabularies, pinned to
    them rather than transcribed once and left."""
    from themis.estimation import simex

    expected = {f"simex_{fitter}_{extrapolant}"
                for fitter in simex._FITTERS
                for extrapolant in simex._NEEDS}
    assert producer.FITS["simex"] == expected


# ===================================================== the producer's door


def test_a_shape_its_method_cannot_fit_is_refused_at_the_door():
    with pytest.raises(ValueError, match="fits"):
        producer.fits("backdoor_linear", "logistic")


def test_a_method_with_no_row_is_refused_rather_than_waved_through():
    """The counterexample to a lookup with a fallback. Answering "no
    opinion" for an unknown method would be silent exactly where a new
    family arrives with nothing holding it — which is the state this
    closes."""
    with pytest.raises(ValueError, match="declares no shapes"):
        producer.fits("a_family_nobody_declared", "linear")


@pytest.mark.parametrize("method, shape", sorted(
    (m, s) for m, shapes in producer.FITS.items() for s in shapes))
def test_every_declared_pair_passes_its_own_door(method, shape):
    assert producer.fits(method, shape) == shape


def test_the_attach_point_is_where_a_form_reaches_an_envelope(monkeypatch):
    """Asked of the attach point itself, not only of ``fits``.

    Twenty-nine call sites reach ``_attach_mechanism_audit`` and nothing
    else builds the block, so this is the door — and a door nobody knocks
    on in a test is a door that can be removed without a red suite.
    """
    from themis.estimation import dispatch
    from themis.output import result_orchestrator

    def forged(**kwargs):
        return {"mechanisms": [_mechanism("backdoor_linear", "forest")]}

    monkeypatch.setattr(result_orchestrator, "build_mechanism_audit", forged)
    with pytest.raises(ValueError, match="fits"):
        dispatch._attach_mechanism_audit(
            {}, _FakeEstimate(), target="y")


class _FakeEstimate:
    """Only the four fields the attach point reads off an estimate."""
    form = "forest"
    method = "backdoor_linear"
    assumptions = ("linear_outcome_regression",)
    form_provenance = "default"
    shape_provenance: dict = {}


# ===================================================== the reader's door


def _mechanism(method: str, form: str) -> dict:
    return {"target": "y", "form": form, "method": method,
            "assumptions": [{"id": "linear_outcome_regression",
                             "settled_by": "default"}]}


def test_the_verifier_refuses_a_shape_outside_the_method():
    assert shape_the_method_cannot_fit("backdoor_linear", "logistic")
    assert shape_the_method_cannot_fit("a_family_nobody_declared", "linear")
    assert shape_the_method_cannot_fit("tmle", "linear") is None
    assert shape_the_method_cannot_fit("tmle", "logistic") is None


@pytest.mark.parametrize("bend", ["_forged", "", "x"])
def test_the_three_lies_the_census_tells_about_a_form_are_refused(bend):
    """A leaf is held only when EVERY kind of lie about it is refused, and
    those are the census's three: the value with something appended, the
    blank, and a short arbitrary string."""
    forged = "linear" + bend if bend == "_forged" else bend
    assert shape_the_method_cannot_fit("backdoor_linear", forged)


# ============================== the answers the corpus does not contain


@pytest.mark.parametrize("method, shape", [
    # tmle fits the line whenever the outcome is not a bool. The corpus
    # holds only tmle -> logistic, and a table assembled from it would
    # refuse this — an honest run, red.
    ("tmle", "linear"),
    ("aipw", "linear"),
    # Built the way the producer builds the method name, so a member
    # nobody has exercised is covered rather than refused.
    ("cde_logit", "logit"),
    ("cde_chain_linear", "linear"),
    ("cde_chain_logit", "logit"),
    ("frontdoor_empirical_logistic", "logistic"),
    ("iv_wald", "wald"),
    ("iv_stratified_wald", "stratified_wald"),
    ("iv_acr", "acr"),
    ("simex", "simex_linear_quadratic"),
])
def test_a_run_the_corpus_never_saw_is_still_accepted(method, shape):
    assert shape_the_method_cannot_fit(method, shape) is None
    assert producer.fits(method, shape) == shape


# ===================================================== end to end


def _atom(p):
    return {"predicate": p, "args": []}


def _confounded_program():
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
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


def _estimated():
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(11)
    n = 4000
    z = rng.random(n) < 0.5
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    df = pd.DataFrame({"x": x, "z": z,
                       "y": rng.random(n) < (0.1 + 0.3 * x + 0.4 * z)})
    envelope = themis.estimate(_confounded_program(), df, random_state=1)
    return envelope["results"][0]


def test_an_honest_answer_passes_the_public_door():
    result = _estimated()
    audit = (result.get("extensions") or {}).get("mechanism_audit")
    assert audit, "this program is meant to disclose a mechanism"
    themis.verify_assumption_ledger(result)


@pytest.mark.parametrize("bend", ["_forged", "", "x"])
def test_a_rewritten_form_is_refused_by_the_public_door(bend):
    """The claim, at the door a reader can reach. Every form on every
    answer shape used to survive this."""
    result = _estimated()
    tampered = copy.deepcopy(result)
    mechanisms = tampered["extensions"]["mechanism_audit"]["mechanisms"]
    original = mechanisms[0]["form"]
    mechanisms[0]["form"] = original + bend if bend == "_forged" else bend
    with pytest.raises(VerificationError):
        themis.verify_assumption_ledger(tampered)


def test_a_form_from_another_method_is_refused_by_the_public_door():
    """Not only nonsense: a shape this build really does fit, claimed by a
    method that does not fit it. The blank and the appended suffix are
    refused by anything; this one needs the table."""
    result = _estimated()
    tampered = copy.deepcopy(result)
    mechanisms = tampered["extensions"]["mechanism_audit"]["mechanisms"]
    method = mechanisms[0]["method"]
    elsewhere = next(
        s for m, shapes in producer.FITS.items() if m != method
        for s in shapes if s not in producer.FITS[method])
    mechanisms[0]["form"] = elsewhere
    with pytest.raises(VerificationError):
        themis.verify_assumption_ledger(tampered)
