"""Phase 4 e2e regression: lock the blind-agent stress test outputs.

The 3 fixtures in ``docs/eval_set/phase4_e2e_run_v1/agent_outputs/``
are real outputs from blind sub-agents driving the full NL→JSON
pipeline (A1+A5+A2). Each was produced by an isolated agent reading
only the prompts and one case input — no gold leakage.

These tests pin the end-to-end behavior:
  ``compose_program(a1_base, a5_variables, a2_edges) → themis.run → status``

If any of A1 / A5 / A2 prompts, the merge layer, kernel V-set
construction, or query dispatch changes in a way that breaks one of
these pipelines, this test surfaces it.

See ``docs/trial_reports/phase4_e2e_stress_test.md`` for the
narrative behind each case.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis
from themis.upstream import compose_program


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "docs" / "eval_set" / "phase4_e2e_run_v1" / "agent_outputs"


def _load(case_id: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def _run(case_id: str) -> dict:
    """Compose + run for the given case; return the first result entry."""
    data = _load(case_id)
    program = compose_program(data["a1_base"], data["a5_variables"], data["a2_edges"])
    out = themis.run(program)
    return out["results"][0]


# ============================================ pinned end-states


def test_case_14_temporal_cause_resolves_to_true():
    """Case 14 (late-night → tired): A2 emits one cause edge with
    ``time_index`` on both atoms. After ``compose_program`` preserves
    time_index, the cause query resolves structurally to True."""
    result = _run("14")
    assert result["status"] == "structurally_solved"
    assert result["query_kind"] == "cause"
    assert result["structural_result"]["value"] is True


def test_case_16_selection_refusal_resolves_to_false():
    """Case 16 (hospitalized → diabetes): A2 declines the edge as
    selection bias / collider; only refusal entry, no cause edges.
    The kernel V-set relaxation admits the query atoms as isolated
    nodes (since their predicates are declared), and the cause query
    resolves to False (no path exists)."""
    result = _run("16")
    assert result["status"] == "structurally_solved"
    assert result["query_kind"] == "cause"
    assert result["structural_result"]["value"] is False


def test_case_21_iv_admg_reaches_needs_investigation():
    """Case 21 (Mendelian randomization): A2 emits cause + bidirected
    coexisting on the (cholesterol, heart_disease) pair. Without data,
    the IV-identified effect query resolves to needs_investigation."""
    result = _run("21")
    assert result["status"] == "needs_investigation"
    assert result["query_kind"] == "effect"


# ============================================ pipeline invariants


@pytest.mark.parametrize("case_id", ["14", "16", "21"])
def test_compose_program_does_not_raise(case_id):
    """All three fixtures must compose cleanly — no MergeConflictError,
    no schema validation surprises."""
    data = _load(case_id)
    program = compose_program(data["a1_base"], data["a5_variables"], data["a2_edges"])
    assert isinstance(program, dict)
    assert "statements" in program


@pytest.mark.parametrize("case_id", ["14", "16", "21"])
def test_themis_run_returns_well_formed_result(case_id):
    """Pipeline output must conform to query_result.schema.json
    minimums: status string + query_kind."""
    result = _run(case_id)
    assert isinstance(result.get("status"), str)
    assert isinstance(result.get("query_kind"), str)


def test_case_21_program_carries_both_cause_and_bidirected_for_same_pair():
    """ADMG semantics: case 21 has cause(cholesterol → heart_disease)
    AND bidirected(cholesterol ↔ heart_disease) for the same pair.
    Both must survive composition."""
    data = _load("21")
    program = compose_program(data["a1_base"], data["a5_variables"], data["a2_edges"])
    statements = program["statements"]

    cause_pairs = {
        tuple(sorted([s["from"]["predicate"], s["to"]["predicate"]]))
        for s in statements if s.get("kind") == "cause"
    }
    bidir_pairs = {
        tuple(sorted([s["left"]["predicate"], s["right"]["predicate"]]))
        for s in statements if s.get("kind") == "bidirected"
    }
    iv_pair = ("heart_disease_risk", "serum_cholesterol")
    assert iv_pair in cause_pairs
    assert iv_pair in bidir_pairs
