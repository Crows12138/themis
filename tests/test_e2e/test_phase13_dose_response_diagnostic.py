"""Phase 13 — dose-response data-spec diagnostic.

When the user (via NL→AST) flags `dose_response_query` in
`program.extensions.ambiguities`, the kernel emits a
`dose_response_data_required` gap whose `required_data` block fully
specifies what's needed to fit the curve in EconML / DoubleML / GAM
externally. Themis itself does NOT compute the curve — that's the
Phase 14 estimator territory.
"""
from __future__ import annotations

import themis
from themis.types import GapKind


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dose_response_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {
                    "kind": "dose_response_query",
                    "description": "用户问加薪和敬业度的关系图",
                },
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "cause",
             "from": _atom("raise_amount"), "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {"atom": _atom("raise_amount"),
                                  "value": True},
                 "target": {"atom": _atom("engagement"), "value": 4},
                 "given": []}},
        ],
    }


def test_dose_response_query_ambiguity_triggers_gap():
    out = themis.run(_dose_response_program())
    gaps = out["results"][0]["data_gap_report"]["gaps"]
    kinds = [g["kind"] for g in gaps]
    assert "dose_response_data_required" in kinds


def test_dose_response_gap_is_blocking_point_estimate():
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "point_estimate"


def test_dose_response_required_data_carries_full_spec():
    """The whole point of this gap_kind: fully-spec'd data sheet so
    user can take it elsewhere and fit the curve."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    rd = gap["required_data"]
    # Sampling points: ≥4 per Hill-Tukey for non-linearity detection
    assert rd["sampling_point_count"] >= 4
    # Total sample size: K × per-point n (Cohen's d power calc)
    assert rd["min_sample_size"] >= rd["sampling_point_count"] * 50
    # Cohen's d cited in precision_target
    assert "Cohen" in rd["precision_target"]
    assert "d=" in rd["precision_target"]
    # Time window present
    assert rd.get("time_window")
    # SUTVA concerns enumerated
    assert rd.get("sutva_concerns")
    assert len(rd["sutva_concerns"]) >= 1


def test_dose_response_description_names_external_tools():
    """Headline must say Themis isn't the right tool — point at EconML
    / DoubleML / GAM so the user knows where to go next."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    desc = gap["description"]
    assert "Themis 不算曲线" in desc or "不画曲线" in desc.replace(
        "不算", "不画"
    )
    assert "EconML" in desc or "DoubleML" in desc or "GAM" in desc


def test_dose_response_alt_path_offers_binary_fallback():
    """If the user can't collect dose-response data, Themis offers a
    binary contrast as fallback (which it CAN handle)."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    alts = gap["alternative_paths"]
    assert any("二元对比" in a or "binary" in a.lower() for a in alts)


def test_no_ambiguity_no_dose_response_gap():
    """Without the `dose_response_query` ambiguity flag, the kernel
    must NOT emit this gap — the trigger is intentional, not heuristic."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "cause",
             "from": _atom("raise_amount"), "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {"atom": _atom("raise_amount"),
                                  "value": True},
                 "target": {"atom": _atom("engagement"), "value": 4},
                 "given": []}},
        ],
    }
    out = themis.run(program)
    gaps = out["results"][0].get("data_gap_report", {}).get("gaps", [])
    kinds = [g["kind"] for g in gaps]
    assert "dose_response_data_required" not in kinds


def test_gap_kind_enum_includes_dose_response():
    assert GapKind.DOSE_RESPONSE_DATA_REQUIRED.value == (
        "dose_response_data_required"
    )
