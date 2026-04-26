"""S.11.2.1 — schemas + JSON schema validation.

Covers KBQuery / KBResult / KBProvenance dataclass round-trips and
JSON-schema conformance.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from themis.kb.schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBQueryKind,
    KBResult,
    kb_provenance_from_dict,
    kb_provenance_to_dict,
    kb_query_from_dict,
    kb_query_to_dict,
    kb_result_from_dict,
    kb_result_to_dict,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
KB_QUERY_SCHEMA = json.loads((REPO_ROOT / "kb_query.schema.json").read_text("utf-8"))
KB_RESULT_SCHEMA = json.loads((REPO_ROOT / "kb_result.schema.json").read_text("utf-8"))


def _result_validator():
    resolver = jsonschema.RefResolver.from_schema(KB_RESULT_SCHEMA)
    return jsonschema.Draft202012Validator(KB_RESULT_SCHEMA, resolver=resolver)


# ----------------------------------------------------------- KBQuery

def _sample_query() -> KBQuery:
    return KBQuery(
        kb_name="primekg",
        query_kind=KBQueryKind.CONDITIONAL_DISTRIBUTION,
        target={"predicate": "lung_cancer", "args": [{"type": "const", "name": "me"}], "value": True},
        given=({"predicate": "smoking", "args": [{"type": "const", "name": "me"}], "value": True},),
        population="adult_us",
        constraints={"age_range": [40, 70], "sex": "any"},
    )


def test_kbquery_round_trip():
    q = _sample_query()
    d = kb_query_to_dict(q)
    q2 = kb_query_from_dict(d)
    assert q == q2


def test_kbquery_minimal():
    q = KBQuery(
        kb_name="websearch_proxy",
        query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
        target={"predicate": "exercise"},
    )
    d = kb_query_to_dict(q)
    assert d == {
        "kb_name": "websearch_proxy",
        "query_kind": "marginal_distribution",
        "target": {"predicate": "exercise"},
        "given": [],
    }
    assert kb_query_from_dict(d) == q


def test_kbquery_all_kinds_serializable():
    for kind in KBQueryKind:
        q = KBQuery(kb_name="x", query_kind=kind, target={"predicate": "y"})
        d = kb_query_to_dict(q)
        assert d["query_kind"] == kind.value
        assert kb_query_from_dict(d).query_kind == kind


def test_kbquery_json_schema_valid():
    d = kb_query_to_dict(_sample_query())
    jsonschema.validate(instance=d, schema=KB_QUERY_SCHEMA)


def test_kbquery_json_schema_rejects_unknown_kind():
    bad = kb_query_to_dict(_sample_query())
    bad["query_kind"] = "fabricated_kind"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=KB_QUERY_SCHEMA)


def test_kbquery_json_schema_rejects_missing_target():
    bad = kb_query_to_dict(_sample_query())
    del bad["target"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=KB_QUERY_SCHEMA)


def test_kbquery_json_schema_rejects_extra_top_level():
    bad = kb_query_to_dict(_sample_query())
    bad["unauthorized_field"] = "should reject"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=KB_QUERY_SCHEMA)


def test_kbquery_target_predicate_required_by_schema():
    bad = {"kb_name": "x", "query_kind": "marginal_distribution",
           "target": {"args": []}}  # missing predicate
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=KB_QUERY_SCHEMA)


# ------------------------------------------------------ KBProvenance

def _sample_provenance(query: KBQuery | None = None) -> KBProvenance:
    return KBProvenance(
        source_kb="primekg",
        query_used=query if query is not None else _sample_query(),
        retrieved_at="2026-04-27T10:30:00Z",
        raw_response_hash="sha256:abc123",
        citation="PMID:12345678",
        confidence_grade=KBConfidenceGrade.RCT_META_ANALYSIS,
        notes="extracted via SPARQL endpoint",
    )


def test_kbprovenance_round_trip():
    p = _sample_provenance()
    d = kb_provenance_to_dict(p)
    p2 = kb_provenance_from_dict(d)
    assert p == p2


def test_kbprovenance_default_confidence_unknown():
    p = KBProvenance(
        source_kb="x",
        query_used=KBQuery(kb_name="x", query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
                          target={"predicate": "y"}),
        retrieved_at="2026-04-27",
        raw_response_hash="h",
        citation="c",
    )
    assert p.confidence_grade == KBConfidenceGrade.UNKNOWN


def test_kbprovenance_all_grades_serializable():
    for grade in KBConfidenceGrade:
        p = _sample_provenance()
        p_with = KBProvenance(**{**p.__dict__, "confidence_grade": grade})
        d = kb_provenance_to_dict(p_with)
        assert d["confidence_grade"] == grade.value


# ---------------------------------------------------------- KBResult

def _sample_result_success() -> KBResult:
    q = _sample_query()
    return KBResult(
        query=q,
        success=True,
        provenance=_sample_provenance(q),
        value=0.18,
        interval=(0.12, 0.24),
        sample_size=2847,
        population_in_source="rct_meta_2023_adult_us",
    )


def _sample_result_failure() -> KBResult:
    q = _sample_query()
    return KBResult(
        query=q,
        success=False,
        provenance=_sample_provenance(q),
        failure_reason="no_matching_record",
    )


def test_kbresult_success_round_trip():
    r = _sample_result_success()
    d = kb_result_to_dict(r)
    assert kb_result_from_dict(d) == r


def test_kbresult_failure_round_trip():
    r = _sample_result_failure()
    d = kb_result_to_dict(r)
    r2 = kb_result_from_dict(d)
    assert r2 == r
    assert r2.value is None
    assert r2.interval is None


def test_kbresult_failure_omits_value_in_dict():
    d = kb_result_to_dict(_sample_result_failure())
    assert "value" not in d
    assert "interval" not in d
    assert "sample_size" not in d
    assert d["failure_reason"] == "no_matching_record"


def test_kbresult_json_schema_valid_success():
    d = kb_result_to_dict(_sample_result_success())
    _result_validator().validate(d)


def test_kbresult_json_schema_valid_failure():
    d = kb_result_to_dict(_sample_result_failure())
    _result_validator().validate(d)


def test_kbresult_json_schema_rejects_missing_query():
    bad = kb_result_to_dict(_sample_result_success())
    del bad["query"]
    with pytest.raises(jsonschema.ValidationError):
        _result_validator().validate(bad)


def test_kbresult_json_schema_rejects_missing_provenance():
    bad = kb_result_to_dict(_sample_result_success())
    del bad["provenance"]
    with pytest.raises(jsonschema.ValidationError):
        _result_validator().validate(bad)


def test_kbresult_json_schema_rejects_short_interval():
    bad = kb_result_to_dict(_sample_result_success())
    bad["interval"] = [0.1]  # only one element
    with pytest.raises(jsonschema.ValidationError):
        _result_validator().validate(bad)


def test_kbresult_immutable():
    """Frozen dataclasses — assignments should raise."""
    r = _sample_result_success()
    with pytest.raises(Exception):  # FrozenInstanceError
        r.success = False  # type: ignore


def test_kbquery_immutable():
    q = _sample_query()
    with pytest.raises(Exception):
        q.kb_name = "other"  # type: ignore


def test_kbquery_json_stable():
    """Two equal queries serialize to identical JSON — cache will use
    sha256 of the JSON dump as its key (KBQuery contains dicts so
    Python hash() doesn't apply, but JSON form is stable)."""
    import json as _json
    q1 = _sample_query()
    q2 = _sample_query()
    assert q1 == q2
    assert _json.dumps(kb_query_to_dict(q1), sort_keys=True) == _json.dumps(
        kb_query_to_dict(q2), sort_keys=True
    )
