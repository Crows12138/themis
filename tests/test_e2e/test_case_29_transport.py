"""S.T9.1.5 — eval case 29 regression test.

Builds the kernel_ast that case 29 (running → belly_fat_loss with
S_age, S_sex, S_bmi shifts between rct_meta_2022 and user) implies,
runs it through ``themis.run`` + ``themis.verify``, and confirms the
gold transport_identification extension matches.

This is the canonical Phase 9 §T9.1 e2e: cross-population effect
question, structural-only answer (no numeric — that's §T9.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = (
    REPO_ROOT / "docs" / "eval_set" / "cases"
    / "29_running_belly_fat_transport.json"
)


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _build_program_from_case(case: dict) -> dict:
    """Translate the case's gold structure into a kernel_ast program.
    Mirrors what an LLM should produce given the case narrative + question."""
    statements = []
    seen_predicates = set()
    for v in case["gold_variables"]:
        if v["predicate"] in seen_predicates:
            continue
        seen_predicates.add(v["predicate"])
        statements.append({
            "kind": "variable",
            "predicate": v["predicate"],
            "domain": [True, False],
        })
    for e in case["gold_edges"]:
        statements.append({
            "kind": "cause",
            "from": _atom(e["from"]),
            "to": _atom(e["to"]),
        })
    for s in case.get("gold_selection_nodes", []):
        statements.append({
            "kind": "selection_node",
            "id": s["id"],
            "affects": _atom(s["affects"]),
            "source_population": s["source_population"],
            "target_population": s["target_population"],
        })
    statements.append({
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("running"), "value": True},
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [],
            "target_population": "user",
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


@pytest.fixture
def case():
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def test_case_29_program_resolves_to_structurally_solved_transport(case):
    program = _build_program_from_case(case)
    out = themis.run(program)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["query_kind"] == "effect"
    assert result["structural_result"]["value"] is True


def test_case_29_transport_identification_extension_matches_gold(case):
    program = _build_program_from_case(case)
    out = themis.run(program)
    ext = out["results"][0]["extensions"]["transport_identification"]

    gold = case["gold_extensions"]["transport_identification"]
    assert ext["source_population"] == gold["source_population"]
    assert ext["target_population"] == gold["target_population"]

    # Adjustment set must include all three shifted variables
    actual_z = sorted(a["predicate"] for a in ext["adjustment_set"])
    assert actual_z == sorted(gold["adjustment_set"])

    # Formula repr must contain the expected substrings
    formula = ext["formula_repr"]
    assert "P*(belly_fat_loss | do(running))" in formula
    assert "Σ_{" in formula
    for shifted in ("age", "sex", "bmi"):
        assert shifted in formula


def test_case_29_round_trips_through_verifier(case):
    """End-to-end audit: run produces a derivation, verify accepts it."""
    program = _build_program_from_case(case)
    out = themis.run(program)
    themis.verify(program, out["results"][0])


def test_case_29_no_numeric_estimate_yet(case):
    """§T9.1 deliberately stops at structural identification —
    no numeric_result / numeric_estimate populated."""
    program = _build_program_from_case(case)
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("numeric_result") is None
    assert result.get("numeric_estimate") is None
    # gold field reflects the same expectation
    assert case["gold_numeric_estimate"] is None
