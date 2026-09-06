"""S.11.2.3 — translator: gap_to_kb_query + kb_result_to_skeleton +
kb_results_to_bundle."""
from __future__ import annotations

import pytest

from themis.kb.schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBQueryKind,
    KBResult,
)
from themis.kb.translator import (
    DEFAULT_KB_NAME,
    gap_to_kb_query,
    kb_result_to_skeleton,
    kb_results_to_bundle,
)
from themis.gaps import Sentence, sentence
from themis.types import (
    BLOCKS_TURN_ON,
    SEVERITY_TURNS_ON,
    DataGap,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    RequiredDataType,
)


def _gap(
    kind: GapKind = GapKind.MISSING_DISTRIBUTION,
    *,
    signature: str | None = "conditional",
    population: str | None = "adult_us",
) -> DataGap:
    """A gap of this species. Severity and blocks are the species' own —
    stated here only for the kinds whose declaration says the value is an
    occasion's, since the rest fill themselves and refuse a fixture's
    guess."""
    occasion = {}
    if kind in SEVERITY_TURNS_ON:
        occasion["severity"] = GapSeverity.BLOCKING
    if kind in BLOCKS_TURN_ON:
        occasion["blocks"] = GapBlocks.POINT_ESTIMATE
    return DataGap(
        kind=kind,
        **occasion,
        describes=(sentence(Sentence.A_DISTRIBUTION_IS_MISSING,
                            what="P(y | x)"),),
        provenance=(GapProvenanceRef(GapRefKind.INVESTIGATION_REQUEST, "P(y|x)"),),
        signature=signature,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population=population,
            variables=("x", "y"),
        ),
    )


_TARGET = {"predicate": "y", "args": [{"type": "const", "name": "me"}], "value": True}
_GIVEN = ({"predicate": "x", "args": [{"type": "const", "name": "me"}], "value": True},)


# ---------------------------------------------------------- gap_to_kb_query

def test_missing_distribution_conditional_signature():
    q = gap_to_kb_query(_gap(signature="conditional"), target=_TARGET, given=_GIVEN)
    assert q is not None
    assert q.query_kind == KBQueryKind.CONDITIONAL_DISTRIBUTION
    assert q.target == _TARGET
    assert q.given == _GIVEN
    assert q.population == "adult_us"


def test_missing_distribution_marginal_signature():
    q = gap_to_kb_query(_gap(signature="marginal"), target=_TARGET)
    assert q.query_kind == KBQueryKind.MARGINAL_DISTRIBUTION


def test_missing_distribution_joint_signature():
    q = gap_to_kb_query(_gap(signature="joint"), target=_TARGET)
    assert q.query_kind == KBQueryKind.JOINT_DISTRIBUTION


def test_missing_distribution_unknown_signature_defaults_conditional():
    q = gap_to_kb_query(_gap(signature="unrecognized"), target=_TARGET)
    assert q.query_kind == KBQueryKind.CONDITIONAL_DISTRIBUTION


def test_missing_distribution_no_signature_defaults_conditional():
    q = gap_to_kb_query(_gap(signature=None), target=_TARGET)
    assert q.query_kind == KBQueryKind.CONDITIONAL_DISTRIBUTION


def test_transport_target_distribution_unknown_maps_to_target_marginal():
    q = gap_to_kb_query(
        _gap(GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN, signature=None),
        target=_TARGET,
    )
    assert q.query_kind == KBQueryKind.TARGET_POPULATION_MARGINAL


def test_transport_source_conditional_unknown_maps_to_stratified():
    q = gap_to_kb_query(
        _gap(GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN, signature=None),
        target=_TARGET,
    )
    assert q.query_kind == KBQueryKind.STRATIFIED_SUBGROUP


def test_missing_iv_candidate_maps_to_iv_candidate():
    q = gap_to_kb_query(
        _gap(GapKind.MISSING_IV_CANDIDATE, signature=None),
        target=_TARGET,
    )
    assert q.query_kind == KBQueryKind.IV_CANDIDATE


def test_missing_mediator_data_maps_to_mediator_distribution():
    q = gap_to_kb_query(
        _gap(GapKind.MISSING_MEDIATOR_DATA, signature=None),
        target=_TARGET,
    )
    assert q.query_kind == KBQueryKind.MEDIATOR_DISTRIBUTION


def test_missing_population_distribution_maps_to_target_marginal():
    q = gap_to_kb_query(
        _gap(GapKind.MISSING_POPULATION_DISTRIBUTION, signature=None),
        target=_TARGET,
    )
    assert q.query_kind == KBQueryKind.TARGET_POPULATION_MARGINAL


def test_unidentifiable_returns_none():
    """Structural unidentifiability has no data fix; translator must
    refuse so caller doesn't waste a KB call."""
    assert gap_to_kb_query(
        _gap(GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET, signature=None),
        target=_TARGET,
    ) is None


def test_missing_assumption_returns_none():
    """Assumption acceptance is a user epistemological choice — never
    farmed out to KB."""
    assert gap_to_kb_query(
        _gap(GapKind.MISSING_ASSUMPTION, signature=None),
        target=_TARGET,
    ) is None


def test_ambiguous_variable_definition_returns_none():
    """User reframing — never KB."""
    assert gap_to_kb_query(
        _gap(GapKind.AMBIGUOUS_VARIABLE_DEFINITION, signature=None),
        target=_TARGET,
    ) is None


def test_default_kb_name_used_when_no_hint():
    q = gap_to_kb_query(_gap(), target=_TARGET)
    assert q.kb_name == DEFAULT_KB_NAME


def test_kb_hint_overrides_default():
    q = gap_to_kb_query(_gap(), target=_TARGET, kb_hint="primekg")
    assert q.kb_name == "primekg"


def test_population_pulled_from_required_data():
    q = gap_to_kb_query(_gap(population="cn_adult"), target=_TARGET)
    assert q.population == "cn_adult"


def test_population_none_when_required_data_absent():
    g = _gap()
    g_no_required = DataGap(**{**g.__dict__, "required_data": None})
    q = gap_to_kb_query(g_no_required, target=_TARGET)
    assert q.population is None


def test_constraints_passed_through():
    q = gap_to_kb_query(_gap(), target=_TARGET,
                        constraints={"age_range": [40, 70]})
    assert q.constraints == {"age_range": [40, 70]}


def test_raw_string_passed_through():
    q = gap_to_kb_query(_gap(), target=_TARGET,
                        raw_string="aspirin heart attack RCT meta-analysis")
    assert q.raw_string == "aspirin heart attack RCT meta-analysis"


# ------------------------------------------------------ KBResult → skeleton

def _success_result(value: float = 0.18) -> KBResult:
    q = KBQuery(
        kb_name="primekg",
        query_kind=KBQueryKind.CONDITIONAL_DISTRIBUTION,
        target=_TARGET,
        given=_GIVEN,
    )
    return KBResult(
        query=q,
        success=True,
        provenance=KBProvenance(
            source_kb="primekg",
            query_used=q,
            retrieved_at="2026-04-27T10:30:00Z",
            raw_response_hash="sha256:abc",
            citation="PMID:12345678",
            confidence_grade=KBConfidenceGrade.RCT_META_ANALYSIS,
        ),
        value=value,
        sample_size=2847,
    )


def test_skeleton_from_success():
    sk = kb_result_to_skeleton(_success_result(0.18))
    assert sk is not None
    assert sk["kind"] == "probability"
    assert sk["value"] == 0.18
    assert sk["annotations"]["source"] == "PMID:12345678"
    assert sk["target"]["value"] is True
    assert sk["target"]["atom"]["predicate"] == "y"
    assert len(sk["given"]) == 1
    assert sk["given"][0]["atom"]["predicate"] == "x"


def test_skeleton_returns_none_on_failure():
    failed = KBResult(
        query=_success_result().query,
        success=False,
        provenance=_success_result().provenance,
        failure_reason="no_match",
    )
    assert kb_result_to_skeleton(failed) is None


def test_skeleton_returns_none_on_missing_value():
    no_value = KBResult(
        query=_success_result().query,
        success=True,
        provenance=_success_result().provenance,
        value=None,
    )
    assert kb_result_to_skeleton(no_value) is None


def test_skeleton_returns_none_on_iv_candidate():
    """IV_CANDIDATE proposes a variable to add, not a probability."""
    q = KBQuery(
        kb_name="x",
        query_kind=KBQueryKind.IV_CANDIDATE,
        target={"predicate": "z"},
    )
    r = KBResult(
        query=q,
        success=True,
        provenance=KBProvenance(
            source_kb="x", query_used=q,
            retrieved_at="2026-04-27", raw_response_hash="h",
            citation="textbook",
        ),
        value=1.0,
    )
    assert kb_result_to_skeleton(r) is None


def test_skeleton_already_wrapped_atom_passthrough():
    """If the caller passed atoms in the {atom: ..., value: ...} shape
    already, the skeleton should preserve that shape."""
    q = KBQuery(
        kb_name="x",
        query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
        target={"atom": {"predicate": "y"}, "value": False},
    )
    r = KBResult(
        query=q, success=True,
        provenance=KBProvenance(
            source_kb="x", query_used=q,
            retrieved_at="2026-04-27", raw_response_hash="h",
            citation="src",
        ),
        value=0.3,
    )
    sk = kb_result_to_skeleton(r)
    assert sk["target"] == {"atom": {"predicate": "y"}, "value": False}


# ----------------------------------------------- KBResults → bundle

def test_bundle_shape():
    bundle = kb_results_to_bundle([_success_result(0.1), _success_result(0.2)])
    assert bundle["version"] == "0.1"
    assert bundle["kind"] == "parameter_fill_bundle"
    assert len(bundle["skeletons"]) == 2
    assert bundle["skeletons"][0]["value"] == 0.1
    assert bundle["skeletons"][1]["value"] == 0.2


def test_bundle_drops_failures_silently():
    failed = KBResult(
        query=_success_result().query,
        success=False,
        provenance=_success_result().provenance,
        failure_reason="no_match",
    )
    bundle = kb_results_to_bundle([_success_result(), failed, _success_result(0.3)])
    assert len(bundle["skeletons"]) == 2  # failure dropped


def test_bundle_empty_when_all_fail():
    failed = KBResult(
        query=_success_result().query,
        success=False,
        provenance=_success_result().provenance,
        failure_reason="x",
    )
    bundle = kb_results_to_bundle([failed, failed])
    assert bundle["skeletons"] == []
    assert bundle["kind"] == "parameter_fill_bundle"


def test_bundle_empty_input():
    bundle = kb_results_to_bundle([])
    assert bundle["skeletons"] == []
