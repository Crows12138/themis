"""Confidence source provenance tracking.

Adds ``QueryResult.confidence_sources`` — one entry per slot that
fed the composite ``min`` aggregation. Each record carries the
annotation source, the slot's confidence value, and an
``is_weakest`` flag marking sources whose confidence equals the
composite minimum.

Before this slice: a caller saw a single aggregated confidence
number and had no way to tell which source drove it down. Now the
JSON envelope exposes the audit trail so downstream agents can
cite the binding constraint explicitly.
"""
from __future__ import annotations

import json

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# ======================================================= program factory

def _program_with_mixed_confidences(
    *,
    p_running: float,
    src_running: str | None = None,
    p_given: float | None = None,
    src_given: str | None = None,
) -> dict:
    """effect(belly_fat_loss=True | do(running=True), age_over_40=True)
    with a single CPT entry carrying a confidence annotation, plus
    (optionally) an observation slot on ``age_over_40`` to exercise
    the §3.2 observation path with a non-intervention atom."""
    def anns(conf, src):
        out = {"confidence": conf}
        if src is not None:
            out["source"] = src
        return out

    statements = [
        {"kind": "variable", "predicate": "running", "domain": [True, False]},
        {"kind": "variable", "predicate": "belly_fat_loss", "domain": [True, False]},
        {"kind": "variable", "predicate": "age_over_40", "domain": [True, False]},
        {"kind": "cause", "from": _atom("age_over_40"), "to": _atom("running")},
        {"kind": "cause", "from": _atom("age_over_40"), "to": _atom("belly_fat_loss")},
        {"kind": "cause", "from": _atom("running"), "to": _atom("belly_fat_loss")},
        # P(belly_fat_loss=True | running=True, age_over_40=True)
        {
            "kind": "probability",
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [
                {"atom": _atom("running"), "value": True},
                {"atom": _atom("age_over_40"), "value": True},
            ],
            "value": 0.5,
            "annotations": anns(p_running, src_running),
        },
    ]

    query_given: list[dict] = [{"atom": _atom("age_over_40"), "value": True}]
    if p_given is not None:
        statements.append({
            "kind": "observation",
            "atom": _atom("age_over_40"),
            "value": True,
            "annotations": anns(p_given, src_given),
        })

    statements.append({
        "kind": "query", "id": "q",
        "query": {"kind": "effect",
                  "target": {"atom": _atom("belly_fat_loss"), "value": True},
                  "intervention": {"atom": _atom("running"), "value": True},
                  "given": query_given},
    })

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ======================================================= basic presence

def test_confidence_sources_populated_when_annotations_present():
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.8, src_running="PubMed:12345",
    ))
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["confidence"] == pytest.approx(0.8)
    assert "confidence_sources" in r
    assert len(r["confidence_sources"]) == 1
    s = r["confidence_sources"][0]
    assert s["source"] == "PubMed:12345"
    assert s["confidence"] == pytest.approx(0.8)
    assert s["is_weakest"] is True


def test_confidence_sources_absent_when_no_annotations():
    """No annotations.confidence anywhere → composite is None and
    confidence_sources is empty (absent from JSON)."""
    program = _program_with_mixed_confidences(p_running=0.8)
    # Strip annotations.confidence by deleting the entire annotations block
    for s in program["statements"]:
        if s["kind"] == "probability":
            del s["annotations"]
    out = themis.run(program)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert "confidence" not in r
    assert "confidence_sources" not in r


# ======================================================= min marking

def test_is_weakest_marks_source_equal_to_composite_min():
    """Two contributing slots (parameter + observation) with different
    confidences. composite = min. is_weakest marks only the slot whose
    confidence == composite."""
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.9, src_running="strong_source",
        p_given=0.3,   src_given="weak_source",
    ))
    r = out["results"][0]
    assert r["confidence"] == pytest.approx(0.3)
    by_source = {s["source"]: s for s in r["confidence_sources"]}
    assert by_source["strong_source"]["is_weakest"] is False
    assert by_source["weak_source"]["is_weakest"] is True


def test_ties_are_all_marked_weakest():
    """Two sources with identical confidence values — both tied with
    the composite min. Both must be marked is_weakest=True."""
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.4, src_running="a",
        p_given=0.4,   src_given="b",
    ))
    r = out["results"][0]
    assert r["confidence"] == pytest.approx(0.4)
    by_source = {s["source"]: s for s in r["confidence_sources"]}
    assert by_source["a"]["is_weakest"] is True
    assert by_source["b"]["is_weakest"] is True


# ======================================================= missing source field

def test_source_absent_when_annotation_lacks_source_field():
    """annotations.confidence set but annotations.source unset →
    confidence_sources entry has no 'source' key (schema allows it as
    optional) but still carries confidence + is_weakest."""
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.6, src_running=None,
    ))
    r = out["results"][0]
    assert len(r["confidence_sources"]) == 1
    s = r["confidence_sources"][0]
    assert "source" not in s
    assert s["confidence"] == pytest.approx(0.6)
    assert s["is_weakest"] is True


# ======================================================= slot labeling

def test_slot_label_for_parameter_includes_probability_key():
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.7, src_running="src",
    ))
    r = out["results"][0]
    assert len(r["confidence_sources"]) == 1
    label = r["confidence_sources"][0]["slot_label"]
    assert label.startswith("parameter:")
    assert "belly_fat_loss" in label
    assert "running" in label


def test_slot_label_for_observation_uses_atom_equals_value():
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.9, src_running="a",
        p_given=0.5, src_given="b",
    ))
    r = out["results"][0]
    # The observation source's slot label begins with "observation:"
    obs_sources = [s for s in r["confidence_sources"]
                   if s["slot_label"].startswith("observation:")]
    assert len(obs_sources) == 1
    assert "age_over_40" in obs_sources[0]["slot_label"]


# ======================================================= structural silence

def test_structural_query_has_no_confidence_sources():
    """cause / assoc / identify don't route through the numeric-slot
    confidence path. confidence_sources stays empty / absent."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }
    r = themis.run(program)["results"][0]
    assert r["status"] == "structurally_solved"
    assert "confidence_sources" not in r
    assert "confidence" not in r


# ======================================================= JSON contract

def test_confidence_sources_output_schema_validates():
    from themis.input.syntactic_validator import validate_result
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.8, src_running="PubMed:12345",
    ))
    validate_result(out["results"][0])


def test_schema_rejects_out_of_range_confidence():
    """Regression guard on the new $def: confidence must be in [0, 1]."""
    from themis.input.syntactic_validator import (
        SyntacticError, validate_result,
    )
    import copy
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.8, src_running="x",
    ))
    tampered = copy.deepcopy(out["results"][0])
    tampered["confidence_sources"][0]["confidence"] = 1.5
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_non_bool_is_weakest():
    from themis.input.syntactic_validator import (
        SyntacticError, validate_result,
    )
    import copy
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.8, src_running="x",
    ))
    tampered = copy.deepcopy(out["results"][0])
    tampered["confidence_sources"][0]["is_weakest"] = "true"
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_confidence_sources_json_round_trip():
    out = themis.run(_program_with_mixed_confidences(
        p_running=0.7, src_running="a",
        p_given=0.3, src_given="b",
    ))
    text = json.dumps(out, ensure_ascii=False)
    assert json.loads(text) == out
