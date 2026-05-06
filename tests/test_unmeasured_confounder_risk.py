"""Tests for unmeasured_confounder_risk gap_kind (iter 5 of L3 simulation).

Triggered by program-shape: declared Z->X & Z->Y (confounder) + no bidirected
edges + effect query + identification not in unidentifiable branch.
"""
from themis import run


def _base_program(*, with_confounder=True, with_bidirected=False):
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
    ]
    if with_confounder:
        statements.append(
            {"kind": "variable", "predicate": "z", "domain": [True, False]}
        )
    statements.append(
        {
            "kind": "cause",
            "from": {
                "predicate": "x",
                "args": [{"type": "const", "name": "p"}],
            },
            "to": {
                "predicate": "y",
                "args": [{"type": "const", "name": "p"}],
            },
        }
    )
    if with_confounder:
        statements.extend(
            [
                {
                    "kind": "cause",
                    "from": {
                        "predicate": "z",
                        "args": [{"type": "const", "name": "p"}],
                    },
                    "to": {
                        "predicate": "x",
                        "args": [{"type": "const", "name": "p"}],
                    },
                },
                {
                    "kind": "cause",
                    "from": {
                        "predicate": "z",
                        "args": [{"type": "const", "name": "p"}],
                    },
                    "to": {
                        "predicate": "y",
                        "args": [{"type": "const", "name": "p"}],
                    },
                },
            ]
        )
    if with_bidirected:
        statements.append(
            {
                "kind": "bidirected",
                "left": {
                    "predicate": "x",
                    "args": [{"type": "const", "name": "p"}],
                },
                "right": {
                    "predicate": "y",
                    "args": [{"type": "const", "name": "p"}],
                },
            }
        )
    statements.append(
        {
            "kind": "query",
            "id": "q",
            "query": {
                "kind": "effect",
                "target": {
                    "atom": {
                        "predicate": "y",
                        "args": [{"type": "const", "name": "p"}],
                    },
                    "value": True,
                },
                "intervention": {
                    "atom": {
                        "predicate": "x",
                        "args": [{"type": "const", "name": "p"}],
                    },
                    "value": True,
                },
                "given": [],
            },
        }
    )
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": statements,
    }


def _gap_kinds(out):
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", [])]


def test_fires_on_confounder_pattern_no_bidirected():
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    kinds = _gap_kinds(out)
    assert "unmeasured_confounder_risk" in kinds


def test_suppressed_when_bidirected_declared():
    out = run(_base_program(with_confounder=True, with_bidirected=True))
    kinds = _gap_kinds(out)
    assert "unmeasured_confounder_risk" not in kinds


def test_suppressed_on_two_variable_dag_no_confounder():
    out = run(_base_program(with_confounder=False, with_bidirected=False))
    kinds = _gap_kinds(out)
    assert "unmeasured_confounder_risk" not in kinds


def test_suppressed_on_cause_query():
    program = _base_program(with_confounder=True, with_bidirected=False)
    program["statements"][-1] = {
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "cause",
            "from": {
                "predicate": "x",
                "args": [{"type": "const", "name": "p"}],
            },
            "to": {
                "predicate": "y",
                "args": [{"type": "const", "name": "p"}],
            },
        },
    }
    out = run(program)
    kinds = _gap_kinds(out)
    assert "unmeasured_confounder_risk" not in kinds


def test_severity_is_informational():
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    report = out["results"][0]["data_gap_report"]
    matching = [
        g for g in report["gaps"] if g["kind"] == "unmeasured_confounder_risk"
    ]
    assert len(matching) == 1
    assert matching[0]["severity"] == "informational"


def test_provenance_is_verifier_check_program_shape():
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    report = out["results"][0]["data_gap_report"]
    [matching] = [
        g for g in report["gaps"] if g["kind"] == "unmeasured_confounder_risk"
    ]
    [prov] = matching["provenance"]
    assert prov["ref_kind"] == "verifier_check"
    assert "confounder_pattern" in prov["ref_id"]


def test_caveat_surfaced_in_result_explanation():
    """The gap is in the must-disclose channel — its description must
    appear as a ⚠ line in result.explanation (where the renderer is
    contractually required to quote it). Without this, the gap lives in
    data_gap_report.gaps only and a renderer might silently drop it."""
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    explanation = out["results"][0].get("explanation") or ""
    assert "⚠" in explanation
    assert "unmeasured confounder" in explanation.lower() or \
        "confounder" in explanation


def test_alternative_paths_mentions_evalue():
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    report = out["results"][0]["data_gap_report"]
    [matching] = [
        g for g in report["gaps"] if g["kind"] == "unmeasured_confounder_risk"
    ]
    paths_text = " ".join(matching.get("alternative_paths", []) or [])
    assert "E-value" in paths_text or "e-value" in paths_text.lower()
