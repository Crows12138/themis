"""Who settled a functional form is a property of the run, not of the id.

#423. The ledger line beside a shape assumption asked ``answerable(id)``, a
table keyed on the assumption — and for every one of the 33 form ids it fell
through to ``inherent``: "required by the method itself, and nothing you can
do about it". Measured on back-door: with ``model='linear'`` passed in the
call, the block said ``caller_asserted`` and the line beside it said
``inherent``, so the reader holding the argument that changes the shape was
told the shape was not theirs to change.

That answer cannot be keyed on the id, and no filling-in of the table would
have fixed it. ``logit_outcome_regression`` is TMLE's definition — TMLE takes
no ``model=`` and there is no lever — and back-door's resolved default the
next family over, and the caller's own assertion the moment they pass one.
Three answers, one id.

So the glossary REFUSES the question for a form id, and the block answers it
per assumption from the resolution the estimate carries. Per assumption
because one field was one answer for however many shape decisions a family
made: a back-door run with a caller's ``model=`` and a multi-level covariate
declares the resolved link, which the caller owns, beside the design matrix's
own decision to enter that column as a number, which nobody offered them.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis import blocks, ledger
from themis.output.assumption_glossary import (
    answerable,
    classify_assumption,
    layer_of,
    settled_form,
    _FORM_NOT_RESOLVED,
)
from themis.output.result_orchestrator import (
    augment_assumption_ledger,
    build_mechanism_audit,
)
from themis.input.syntactic_validator import SyntacticError
from themis.verifier.assumption_ledger_rules import (
    verify_assumption_ledger as _rule_verify,
)
from themis.verifier.errors import VerificationError

from tests.test_the_encoding_does_not_decide_the_answer import (
    LABELS, _campaign, _program,
)

_LINK = "logit_outcome_regression"
_ORDERED = "multi_level_covariates_entered_as_ordered_numbers"


@pytest.fixture(scope="module")
def program() -> dict:
    return _program(LABELS)


@pytest.fixture(scope="module")
def frame():
    return _campaign(LABELS)


def _run(program, frame, **kw) -> dict:
    return themis.estimate(program, frame, ci_bootstrap=0, **kw)["results"][0]


def _block(result: dict) -> dict:
    return (result["extensions"][blocks.Block.MECHANISM_AUDIT]
            ["mechanisms"][0])


def _settled(result: dict) -> dict[str, str]:
    return {str(a["id"]): str(a["settled_by"])
            for a in _block(result)["assumptions"]}


def _lines(result: dict) -> dict[str, str]:
    return {
        str(e["id"]): str(e["provenance"])
        for e in result["extensions"][blocks.Block.ASSUMPTION_LEDGER]
                       ["assumptions"]
        if e.get("id") and e["layer"] == "functional_form"
    }


# --- the defect, in the two shapes it was measured in -------------------------


def test_the_same_shape_reads_differently_depending_on_who_settled_it(
        program, frame):
    """The run is the difference, and the run is what is asked.

    Same data, same resolved form, same number — and one of the two runs was
    told the shape and the other worked it out. A table keyed on the id sees
    one string, ``"logistic"``, in both.
    """
    auto = _run(program, frame)
    told = _run(program, frame, model="logistic")

    assert _block(auto)["form"] == _block(told)["form"] == "logistic"
    assert _settled(auto)[_LINK] == "default"
    assert _settled(told)[_LINK] == "caller_asserted"


def test_the_line_the_reader_sees_says_what_the_block_says(program, frame):
    """The defect itself: the two surfaces answering the same question.

    The block was right about this before #423 and the line was not, which is
    the shape that makes it a disclosure bug rather than a missing feature —
    the answer was on the envelope and the sentence beside it contradicted it.
    """
    for kw in ({}, {"model": "logistic"}):
        result = _run(program, frame, **kw)
        assert _lines(result) == _settled(result)


def test_one_block_holds_two_shape_decisions_of_different_origin(
        program, frame):
    """One field for N facts, measured. The caller named the link; nobody
    named the design matrix, and no value of ``model=`` names one."""
    told = _run(program, frame, model="logistic")
    assert _settled(told) == {
        _LINK: "caller_asserted",
        _ORDERED: "default",
    }


def test_a_caller_asserted_shape_traces_to_something_the_envelope_records(
        program, frame):
    """The verifier refuses a line handed to a caller who supplied nothing,
    and it is right to: an action the reader cannot take is worse than no
    line. What it reads is ``estimation_context.model_preference``, which the
    envelope has recorded all along with nothing asking for it — because
    until a shape line could say ``caller_asserted`` there was nothing to
    trace.
    """
    told = _run(program, frame, model="logistic")
    assert told["estimation_context"]["model_preference"] == "logistic"
    themis.verify(_program(LABELS), told)


# --- what the glossary may and may not answer ---------------------------------


def test_the_glossary_refuses_the_question_it_cannot_answer():
    """Refused rather than defaulted. The fallback was one line and it was
    wrong 33 times, silently, because a plausible constant reads exactly like
    a considered answer."""
    with pytest.raises(ValueError, match="fact about the RUN"):
        answerable(_LINK)
    # And still answers for every layer that IS a property of the id.
    assert answerable("consistency_of_potential_outcomes") == (
        ledger.Provenance.INHERENT)
    assert answerable("mtr_non_decreasing_in_t") == (
        ledger.Provenance.CALLER_ASSERTED)


def test_a_form_entry_carries_no_provenance_and_every_other_one_does():
    """Absent, not ``None``: a consumer that needs it and forgets gets a
    ``KeyError`` naming the id, and one that only wants the layer never
    asks."""
    shape = classify_assumption(_LINK)
    assert shape["layer"] == ledger.Layer.FUNCTIONAL_FORM
    assert "provenance" not in shape
    assert shape["claim"]

    premise = classify_assumption("consistency_of_potential_outcomes")
    assert premise["provenance"] == ledger.Provenance.INHERENT


def test_the_run_answers_except_where_the_id_really_is_the_question():
    """The exception table, from both sides."""
    assert settled_form(_LINK, ledger.Provenance.CALLER_ASSERTED) == (
        ledger.Provenance.CALLER_ASSERTED)
    assert settled_form(_LINK, "inherent") == ledger.Provenance.INHERENT
    # The design matrix's own decision does not move with the run's.
    for resolution in ("inherent", "default", "caller_asserted"):
        assert settled_form(_ORDERED, resolution) == ledger.Provenance.DEFAULT


def test_every_exception_is_a_shape_and_a_word_the_channel_may_write():
    """An exception listed for an id that is not a form assumption is an
    exception nothing reaches — it reads in the source exactly like a
    considered decision and excuses nothing."""
    _, admissible = ledger.ADMISSIBLE["audited_mechanism"]
    for text, provenance in _FORM_NOT_RESOLVED.items():
        assert layer_of(text) == ledger.Layer.FUNCTIONAL_FORM, text
        assert provenance in admissible, text


def test_a_resolution_outside_the_vocabulary_is_refused():
    with pytest.raises(ValueError, match="not an assumption provenance"):
        settled_form(_LINK, "estimator_default")


# --- the whitelist narrowed, and shown refusing --------------------------------


def test_the_flat_channel_may_no_longer_write_a_shape_line():
    """The narrowing is the structural part: the channel that carries an id
    and nothing else cannot say who settled a shape, so it is no longer
    allowed to try."""
    with pytest.raises(ValueError, match="may not write layer"):
        ledger.stamp("estimator_assumption", ledger.Layer.FUNCTIONAL_FORM,
                     ledger.Provenance.INHERENT)
    # The channel that holds the run's answer may write all three.
    for provenance in ("inherent", "default", "caller_asserted"):
        ledger.stamp("audited_mechanism", ledger.Layer.FUNCTIONAL_FORM,
                     provenance)


def test_a_shape_with_no_block_to_answer_for_it_is_refused():
    """Reachable only by building the block from a different list than the
    estimate declared, which is why it names that as the cause."""
    result = {
        "numeric_estimate": {
            "method": "backdoor_linear",
            "assumptions": ["consistency_of_potential_outcomes", _LINK],
        },
        "extensions": {
            blocks.Block.MECHANISM_AUDIT: {
                "mechanisms": [{
                    "target": "y", "form": "linear", "method": "backdoor_linear",
                    "assumptions": [{"id": "linear_outcome_regression",
                                     "settled_by": "default"}],
                }],
                "summary": "…",
            },
        },
    }
    with pytest.raises(ValueError, match="no mechanism_audit entry says who"):
        augment_assumption_ledger(result)


def test_the_builder_still_refuses_an_estimate_that_cannot_say():
    with pytest.raises(ValueError, match="not an assumption provenance"):
        build_mechanism_audit(target="y", form="linear", method="m",
                              assumptions=("linear_outcome_regression",),
                              form_provenance="")


# --- the two independent re-derivations, each shown saying no ------------------


def _tampered(result: dict, mutate) -> dict:
    copied = copy.deepcopy(result)
    mutate(copied["extensions"])
    return copied


def test_the_verifier_refuses_a_line_that_disagrees_with_its_block(
        program, frame):
    """The check that needs no table of its own: two surfaces, one question.

    This is the artefact the defect produced, reconstructed — the block right,
    the line beside it saying the method required a form the caller named.
    """
    told = _run(program, frame, model="logistic")

    def _revert_the_line(ext):
        for e in ext[blocks.Block.ASSUMPTION_LEDGER]["assumptions"]:
            if e.get("id") == _LINK:
                e["provenance"] = "inherent"

    with pytest.raises(VerificationError,
                       match="they answer the same question"):
        themis.verify_assumption_ledger(_tampered(told, _revert_the_line))


def test_the_verifier_refuses_a_shape_the_block_names_and_nothing_declared(
        program, frame):
    told = _run(program, frame, model="logistic")

    def _invent(ext):
        ext[blocks.Block.MECHANISM_AUDIT]["mechanisms"][0]["assumptions"].append(
            {"id": "linear_mediator_model_with_normal_residual_variance",
             "settled_by": "caller_asserted"})

    with pytest.raises(VerificationError, match="has no line for it"):
        themis.verify_assumption_ledger(_tampered(told, _invent))


def test_a_block_that_names_a_bare_id_is_refused_at_both_doors(program, frame):
    """The pre-#423 shape of the field, offered back.

    The contract is the door that closes it, and the rule says no as well
    rather than trusting that: it reads the block off an envelope where
    anything could have written it, and an id with no origin beside it is the
    one shape it must not read as "the method required it".
    """
    told = _run(program, frame, model="logistic")

    def _flatten(ext):
        mech = ext[blocks.Block.MECHANISM_AUDIT]["mechanisms"][0]
        mech["assumptions"] = [a["id"] for a in mech["assumptions"]]

    flattened = _tampered(told, _flatten)
    with pytest.raises(SyntacticError, match="is not of type 'object'"):
        themis.verify_assumption_ledger(flattened)
    with pytest.raises(VerificationError, match="as a bare str"):
        _rule_verify(flattened)


def test_the_verifier_refuses_one_run_that_resolved_two_ways(program, frame):
    """What the agreement check above cannot see: both surfaces agreeing on an
    answer no run could have produced.

    Consistent on every line, and still impossible — the same ``model=`` was
    both named and left unspecified. The design-matrix row is excluded from
    the comparison, which is why the forgery has to use a second id that the
    resolution really does settle.
    """
    told = _run(program, frame, model="logistic")
    second = "linear_outcome_regression"

    def _two_resolutions(ext):
        ext[blocks.Block.MECHANISM_AUDIT]["mechanisms"][0]["assumptions"].append(
            {"id": second, "settled_by": "default"})
        ext[blocks.Block.ASSUMPTION_LEDGER]["assumptions"].append({
            "id": second, "claim": "outcome 用线性回归建模",
            "layer": "functional_form", "severity": "distorting",
            "provenance": "default", "testable": True,
        })

    with pytest.raises(VerificationError, match="at once; one run resolves"):
        themis.verify_assumption_ledger(_tampered(told, _two_resolutions))


def test_the_untampered_answer_passes_every_one_of_them(program, frame):
    """A check that says no to everything says nothing."""
    for kw in ({}, {"model": "logistic"}):
        themis.verify_assumption_ledger(_run(program, frame, **kw))
