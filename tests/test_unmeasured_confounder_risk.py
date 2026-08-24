"""Tests for the unmeasured_confounder_risk gap_kind.

Triggered by program-shape: declared Z->X & Z->Y (confounder) + no bidirected
edges + effect query + identification not in unidentifiable branch.
"""
from themis import run
from tests import caveats


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


def test_the_risk_is_a_caveat_the_reader_is_led_with():
    """The gap is in the must-disclose channel — its description must
    appear as a ⚠ line in result.explanation (where the renderer is
    contractually required to quote it). Without this, the gap lives in
    data_gap_report.gaps only and a renderer might silently drop it."""
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    explanation = caveats.text(out["results"][0])
    assert "⚠" in explanation
    assert "unmeasured confounder" in explanation.lower() or \
        "confounder" in explanation


def test_alternative_paths_mentions_evalue():
    out = run(_base_program(with_confounder=True, with_bidirected=False))
    report = out["results"][0]["data_gap_report"]
    [matching] = [
        g for g in report["gaps"] if g["kind"] == "unmeasured_confounder_risk"
    ]
    taken = [a["route"] for a in matching.get("alternative_paths") or ()]
    assert "run_an_e_value" in taken, taken


def test_unmeasured_confounder_risk_persists_through_apply_patch_and_run():
    """unmeasured_confounder_risk is a structural advisory
    (about DAG completeness, not data). It must persist when the user
    fills missing distributions via apply_patch_and_run — the DAG hasn't
    changed, so the advisory still applies even if status flips toward
    numerically_solved.

    Catches a class of regression where some dispatch path could
    accidentally elide structural advisories once theta is more filled."""
    from themis import apply_patch_and_run
    program = _base_program(with_confounder=True, with_bidirected=False)
    initial = run(program)
    initial_kinds = _gap_kinds(initial)
    assert "unmeasured_confounder_risk" in initial_kinds

    # Fill the missing parameter via the investigation_request skeleton
    investigation = initial["results"][0]["investigation_requests"][0]
    skeleton = dict(investigation["items"][0]["skeleton"])
    skeleton["value"] = 0.5
    skeleton["annotations"] = {"source": "test_fixture"}

    patched = apply_patch_and_run(program, [skeleton])
    patched_kinds = _gap_kinds(patched)
    assert "unmeasured_confounder_risk" in patched_kinds, (
        "Structural advisory should persist through apply_patch_and_run; "
        f"DAG unchanged but advisory elided. gap_kinds: {patched_kinds}"
    )


def test_transport_advisory_fires_on_structurally_solved():
    """Confirm the transport advisory fires correctly
    when transport identification succeeds. Transport queries return
    status=structurally_solved, extensions has transport_identification —
    same code path as mediation (extensions-driven, so no empty
    derivation for the signal to miss, which is the front-door
    failure below). Pins the contract."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "selection_node",
                "id": "S_z",
                "affects": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
                "source_population": "src",
                "target_population": "tgt",
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "intervention": {
                        "atom": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "given": [],
                    "target_population": "tgt",
                },
            },
        ],
    }
    out = run(program)
    result = out["results"][0]
    kinds = [g["kind"] for g in result.get("data_gap_report", {}).get("gaps", [])]
    assert "transport_identification_assumption_required" in kinds


def test_mediation_advisory_fires_on_structurally_solved():
    """Confirm the mediation advisory fires correctly
    when mediation identification succeeds. Mediation queries return
    status=structurally_solved (not needs_investigation), so derivation
    is populated and extensions has mediation_decomposition — a
    different code path from the front-door case below. This test pins
    the contract so a future refactor doesn't silently regress it."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "m", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "m", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "intervention": {
                        "atom": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "mediator": {"predicate": "m", "args": [{"type": "const", "name": "p"}]},
                    "given": [],
                },
            },
        ],
    }
    out = run(program)
    result = out["results"][0]
    kinds = [g["kind"] for g in result.get("data_gap_report", {}).get("gaps", [])]
    assert "mediation_identification_assumption_required" in kinds


def test_front_door_advisory_fires_via_program_shape_fallback():
    """Front-door identification with missing theta has
    empty derivation, so the original derivation-only signal in
    _classify_front_door_assumptions silently dropped the FD1/FD2/FD3
    advisory. Pearl's smoking->tar->cancer with smoking<->cancer is the
    canonical front-door case; verify the advisory fires via the new
    program-shape fallback even when status is needs_investigation."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "m", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "m", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "bidirected",
                "left":  {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "right": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
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
            },
        ],
    }
    out = run(program)
    result = out["results"][0]
    kinds = [g["kind"] for g in result.get("data_gap_report", {}).get("gaps", [])]
    assert "front_door_identification_assumption_required" in kinds
    explanation = caveats.text(result)
    assert "前门" in explanation or "front-door" in explanation.lower()
