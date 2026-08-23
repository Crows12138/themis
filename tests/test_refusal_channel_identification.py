"""Identification refuses through the same channel an estimator does.

Why no number came out is a top-level field of the result — the schema
has carried ``estimator_failure`` all along, with a closed enum, a kind
stamped at the exit, a branch in the report and one in the browser.
``QueryResult`` did not carry it, so the identification layer, which
returns a result rather than raising for dispatch to catch, had nowhere
to put a reason and wrote prose into two ``extensions`` blocks instead.

Neither block reached a reader. ``causation_error`` was rendered by the
detachable explainer and by nothing on the main report; the reader of a
non-binary causation query was told only "该问题超出 Themis 可表达 / 可
识别的范围" while the kernel had written which variable and which states.
``counterfactual_error`` was read by nothing at all — two producers, no
consumer — and the explainer's own sentence for that status ("已进入语法
层，但当前仍未进入求解层") described a stage rather than the failure.

The species were not missing either. Both reasons already had one,
raised by the data end for the same causes: the counterfactual solver's
exception family had three of them written out at one handler, and
``cause_or_effect_not_binary`` says, in its own words, "probabilities of
causation are defined here for binary cause and effect".
"""
from __future__ import annotations

import pytest

import themis
from themis import blocks, language, refusals
from themis.refusals import Refusal
from themis.output.analysis_report import build_analysis_report
from themis.runtime import counterfactual as cf
from themis.types import AnswerTier, QueryResult


def _atom(p, obj="p"):
    return {"predicate": p, "args": [{"type": "const", "name": obj}]}


X, Y = _atom("x"), _atom("y")


def _program(query, *, x_domain=(True, False)):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": list(x_domain)},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": X, "to": Y},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}], "value": 0.2},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}], "value": 0.1},
            {"kind": "query", "id": "q1", "query": query},
        ],
    }


NON_BINARY_CAUSATION = _program(
    {"kind": "causation", "cause": X, "effect": Y},
    x_domain=("lo", "mid", "hi"),
)


# --- the species belongs to the failure, not to whoever caught it -------------


@pytest.mark.parametrize("exc_type", [
    cf.InterventionalRiskRequired,
    cf.CounterfactualInfeasible,
])
def test_every_named_solver_failure_names_a_registered_species(exc_type):
    assert isinstance(exc_type.species, Refusal)


def test_the_two_named_failures_are_two_species():
    """A shared species would make the field say less than the class
    hierarchy already knows — a needed experiment and a cell the data has
    ruled out are two different things to be told."""
    species = {
        cf.InterventionalRiskRequired.species,
        cf.CounterfactualInfeasible.species,
    }
    assert len(species) == 2


def test_the_head_of_the_family_names_none_and_is_told_one_each_time():
    """It named one until #433, and that one species answered for the ten
    sites that raise the base class directly — a wrong domain, a
    probability outside [0, 1], a conditioning event of measure zero. One
    name over ten facts is what the cuts before this one spent their time
    removing, so the head is now the family's door rather than a member of
    it, and a site with nothing to name cannot construct one at all."""
    assert cf.CounterfactualBoundsError.species is None
    with pytest.raises(TypeError, match="without a species"):
        cf.CounterfactualBoundsError()


def test_a_subclass_that_declares_no_species_is_refused_at_import():
    """Inheriting one means being described by a reason chosen for a
    different failure — the silent half of what this file is about."""
    with pytest.raises(TypeError, match="declare the one that describes"):
        type("NewCase", (cf.CounterfactualBoundsError,), {})


# --- the envelope -------------------------------------------------------------


def test_the_result_type_carries_the_field_the_schema_declares():
    assert "estimator_failure" in QueryResult.__dataclass_fields__


def test_a_refusal_block_from_identification_has_the_estimator_shape():
    b = refusals.block(
        estimator="causation_identification",
        failure_type=Refusal.CAUSE_OR_EFFECT_NOT_BINARY,
    )
    assert set(b) == {"estimator", "failure_type"}
    assert b["failure_type"] == "cause_or_effect_not_binary"
    # A hole this occasion carried nothing for is said by its own name
    # rather than thrown over: identification is the layer with no
    # exception to raise, and a reader here has already been told there is
    # no number.
    assert refusals.said(b) == refusals.sentence(
        Refusal.CAUSE_OR_EFFECT_NOT_BINARY,
        {"column": language.absent("no_fact_for_this_slot",
                                   name="column"),
         "values": language.absent("no_fact_for_this_slot",
                                   name="values")})


def test_an_unregistered_species_is_refused_where_there_is_no_constructor():
    """``EstimatorFailure`` validates at the raise site; identification
    has no raise site, so the assembler validates too."""
    with pytest.raises(ValueError, match="unregistered failure_type"):
        refusals.block(estimator="x", failure_type="not_a_species")


def test_a_refusal_from_identification_is_stamped_with_its_kind():
    """The stamp is what lets a consumer branch on five values instead of
    sixty-nine, and it runs at the kernel exit — which the identification
    path goes through as much as the estimation path does."""
    result = themis.run(NON_BINARY_CAUSATION)["results"][0]
    failure = result["estimator_failure"]
    assert failure["kind"] == refusals.BY_NAME[failure["failure_type"]].kind


def test_identification_reuses_the_species_the_data_end_raises():
    result = themis.run(NON_BINARY_CAUSATION)["results"][0]
    assert (result["estimator_failure"]["failure_type"]
            == Refusal.CAUSE_OR_EFFECT_NOT_BINARY)


def test_the_two_prose_blocks_are_gone():
    assert "causation_error" not in blocks.Block
    assert "counterfactual_error" not in blocks.Block
    assert all(f != "refusal" for f in blocks.Family)


# --- and it reaches the reader ------------------------------------------------


def test_the_report_says_which_variable_and_which_states():
    """The measured symptom: the kernel wrote the predicate and the
    domain, and the main surface said only that the question was out of
    range."""
    result = themis.run(NON_BINARY_CAUSATION)["results"][0]
    answer = build_analysis_report(result, program=NON_BINARY_CAUSATION)
    answer = answer.split("## 答案", 1)[1].split("##", 1)[0]
    assert "binary" in answer and "x" in answer
    assert "超出 Themis 可表达" not in answer


def test_a_refused_question_is_not_promised_an_interval():
    """``outside_language`` says the quantity is undefined as asked, not
    that data are short. The tier used to be read off the question's
    shape — causation falls back to Tian-Pearl bounds — and promised an
    interval that no amount of data produces, because bounds over a
    non-binary cause are undefined too."""
    result = themis.run(NON_BINARY_CAUSATION)["results"][0]
    tier = (result.get("data_gap_report") or {}).get("answer_tier")
    assert tier in (None, AnswerTier.NONE.value)
    assert "区间" not in build_analysis_report(
        result, program=NON_BINARY_CAUSATION
    ).split("## 数据缺口", 1)[1]
