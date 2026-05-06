"""L3 simulation corpus regression test.

Iter 1-16 mined 8 L3 cases from authoritative sources to pressure-test
the data_gap_report. This test pins the corpus contract: each case's
expected gap_kinds must remain in the report. A code change that
silently drops one of these gaps fails here.

Each case is encoded in docs/l3_simulation/case_NNN_*.json with a
matching .md describing the authoritative source + expected behavior.
This test loads the JSON, runs themis.run, and asserts the expected
gap_kinds are present.

Cases:
- 001/002 backdoor (medicine) — measured confounders + no bidirected
- 003 IV via Balke-Pearl bounds (econ) — Card 1995 schooling-earnings
- 004 front-door (medicine) — Pearl smoking->tar->cancer
- 005 dose-response (medicine) — Whelton 2002 exercise-BP
- 006 mediation (epi) — Cnattingius 2004 smoking-birthweight
- 007 transport (medicine) — USPSTF 2022 statin to 75+
- 008 counterfactual (Layer 3) — Pearl 2009 monotone bounds

L3 simulation methodology + per-case authoritative sources:
docs/l3_simulation/README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from themis import run


REPO_ROOT = Path(__file__).resolve().parents[1]
L3_DIR = REPO_ROOT / "docs" / "l3_simulation"


def _load(name: str) -> dict:
    return json.loads((L3_DIR / name).read_text(encoding="utf-8"))


def _gap_kinds(out: dict) -> list[str]:
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", [])]


# Each entry: (case file, must-have gap_kinds, must-NOT-have gap_kinds)
CASES = [
    (
        "case_001_hrt_cvd.json",
        # measured confounders + no bidirected → unmeasured_confounder_risk fires
        ["missing_distribution", "answer_is_bounds_not_point_estimate",
         "unmeasured_confounder_risk"],
        ["front_door_identification_assumption_required",
         "transport_identification_assumption_required"],
    ),
    (
        "case_002_vitamin_d_cvd.json",
        ["missing_distribution", "answer_is_bounds_not_point_estimate",
         "unmeasured_confounder_risk"],
        ["front_door_identification_assumption_required"],
    ),
    (
        "case_003_card_schooling_earnings.json",
        # IV-shape detected → Balke-Pearl IV bounds + unmeasured_confounder_risk
        # (ability is a confounder + no bidirected, so risk fires)
        ["missing_distribution", "answer_is_bounds_not_point_estimate",
         "unmeasured_confounder_risk"],
        [],
    ),
    (
        "case_004_pearl_smoking_tar_cancer.json",
        # bidirected declared → unmeasured_confounder_risk SUPPRESSED
        # front-door pattern → front_door_identification_assumption_required fires
        # (iter 10 fix)
        ["missing_distribution", "answer_is_bounds_not_point_estimate",
         "front_door_identification_assumption_required"],
        ["unmeasured_confounder_risk"],
    ),
    (
        "case_005_exercise_bp_dose_response.json",
        # extensions.ambiguities[kind=dose_response_query] → dose-response gap
        ["dose_response_data_required", "missing_distribution",
         "answer_is_bounds_not_point_estimate"],
        [],
    ),
    (
        "case_006_smoking_birthweight_mediation.json",
        # mediation query → mediation_identification_assumption_required (×2)
        # ses_low confounder + no bidirected → unmeasured_confounder_risk
        ["mediation_identification_assumption_required",
         "unmeasured_confounder_risk"],
        ["front_door_identification_assumption_required"],
    ),
    (
        "case_007_statin_transport.json",
        # selection_node + target_population → transport identification
        # 4-layer advisory: structure / assumption / data×2 / DAG completeness
        ["transport_identification_assumption_required",
         "transport_target_distribution_unknown",
         "transport_source_conditional_unknown",
         "unmeasured_confounder_risk"],
        ["front_door_identification_assumption_required"],
    ),
    (
        "case_008_pearl_monotone_counterfactual.json",
        # counterfactual query → counterfactual advisory + 6 missing_distribution
        # 2-var DAG → unmeasured_confounder_risk SUPPRESSED (var_count < 3)
        ["counterfactual_identification_assumption_required",
         "missing_distribution"],
        ["unmeasured_confounder_risk",
         "front_door_identification_assumption_required"],
    ),
    (
        "case_009_mediation_x_transport.json",
        # query has BOTH mediator + target_population; iter 19 fix:
        # unattempted_layer_due_to_dispatch_conflict surfaces silent skip
        ["unattempted_layer_due_to_dispatch_conflict",
         "transport_identification_assumption_required",
         "unmeasured_confounder_risk"],
        ["mediation_identification_assumption_required"],
    ),
    (
        "case_010_co2_temperature_ipcc.json",
        # cause query (boolean) — minimal gaps, no must-disclose. cause
        # queries don't need data; query_kind != EFFECT so
        # unmeasured_confounder_risk correctly suppressed.
        ["ambiguous_variable_definition"],
        ["unmeasured_confounder_risk",
         "missing_distribution",
         "front_door_identification_assumption_required",
         "unattempted_layer_due_to_dispatch_conflict"],
    ),
]


@pytest.mark.parametrize("case_file,must_have,must_not_have", CASES,
                         ids=[c[0] for c in CASES])
def test_l3_case_emits_expected_gap_kinds(case_file, must_have, must_not_have):
    program = _load(case_file)
    out = run(program)
    kinds = _gap_kinds(out)
    for k in must_have:
        assert k in kinds, (
            f"L3 corpus regression: {case_file} should emit gap_kind "
            f"{k!r} but did not. Got: {kinds}"
        )
    for k in must_not_have:
        assert k not in kinds, (
            f"L3 corpus regression: {case_file} should NOT emit gap_kind "
            f"{k!r} but did. Got: {kinds}"
        )


def test_every_l3_case_json_has_matching_markdown():
    """Each case_NNN_*.json must have a sibling case_NNN_*.md describing
    the authoritative source, encoded DAG, expected behavior, and
    assessment. The .md is the L3 audit trail — without it a future
    contributor reading the .json has no idea what's being tested
    against what ground truth.

    iter 40 audit pin: 10 cases all have matching markdown today; this
    pins the invariant so adding a .json without a .md fails fast.
    """
    json_files = sorted(L3_DIR.glob("case_*.json"))
    md_files = {f.stem for f in L3_DIR.glob("case_*.md")}
    missing = []
    for jf in json_files:
        if jf.stem not in md_files:
            missing.append(jf.name)
    assert not missing, (
        f"L3 case JSON without matching markdown audit trail: {missing}. "
        f"Add case_NNN_*.md describing the authoritative source + "
        f"expected behavior + assessment per docs/l3_simulation/README.md "
        f"case format."
    )


def test_l3_readme_case_index_matches_actual_files():
    """docs/l3_simulation/README.md has a 'case index' listing all
    cases as `- [Case NNN — title](case_NNN_*.md)` entries. Each line
    must match an actual case_NNN_*.md file in the directory.

    Iter 73 preventive pin (no current drift). Catches future
    regression where case 011 is added without README index update,
    or a .md is renamed without reflecting in README.
    """
    import re
    readme = (L3_DIR / "README.md").read_text(encoding="utf-8")
    entry_re = re.compile(r"\[Case\s+(\d+)\s+—[^\]]+\]\(([^)]+\.md)\)")
    indexed = {int(m.group(1)) for m in entry_re.finditer(readme)}

    actual = set()
    for f in L3_DIR.glob("case_*.md"):
        m = re.match(r"case_(\d+)_", f.name)
        if m:
            actual.add(int(m.group(1)))

    missing = actual - indexed
    extra = indexed - actual
    assert not missing, (
        f"L3 README case index missing actual cases: {sorted(missing)}. "
        f"Add entries for these to docs/l3_simulation/README.md."
    )
    assert not extra, (
        f"L3 README case index references non-existent cases: "
        f"{sorted(extra)}"
    )


def test_l3_corpus_count_at_plateau():
    """Sanity: corpus has reached plateau (≥10 cases). If a case is
    accidentally deleted this catches it."""
    case_files = list(L3_DIR.glob("case_*.json"))
    assert len(case_files) >= 10, (
        f"L3 corpus expected ≥10 cases at plateau, found {len(case_files)}. "
        f"Files: {[f.name for f in case_files]}"
    )


def test_dispatch_conflict_fires_on_mediator_plus_target_pop():
    """iter 19 finding-fix: when query has both mediator and target_population
    set, but only one of mediation_decomposition / transport_identification
    extension is populated, the kernel must surface
    unattempted_layer_due_to_dispatch_conflict to disclose the silent skip."""
    program = _load("case_009_mediation_x_transport.json")
    out = run(program)
    kinds = _gap_kinds(out)
    assert "unattempted_layer_due_to_dispatch_conflict" in kinds
    matching = [
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "unattempted_layer_due_to_dispatch_conflict"
    ]
    assert len(matching) == 1
    gap = matching[0]
    assert gap["severity"] == "important"
    # Description names what was attempted and what was skipped
    assert "transport" in gap["description"]
    assert "mediation" in gap["description"]


def test_dispatch_conflict_suppressed_when_only_mediator():
    """Symmetric: pure mediation query (no target_population) should NOT
    fire the conflict gap — there's no conflict, only one layer was asked
    for."""
    program = _load("case_006_smoking_birthweight_mediation.json")
    out = run(program)
    kinds = _gap_kinds(out)
    assert "unattempted_layer_due_to_dispatch_conflict" not in kinds


def test_dispatch_conflict_suppressed_when_only_target_pop():
    """Symmetric: pure transport query (no mediator) should NOT fire the
    conflict gap."""
    program = _load("case_007_statin_transport.json")
    out = run(program)
    kinds = _gap_kinds(out)
    assert "unattempted_layer_due_to_dispatch_conflict" not in kinds


def test_l3_corpus_runtime_regression():
    """iter 33 perf pin. Each L3 case currently runs in 2-5 ms, total
    ~36 ms (measured on local machine, no concurrency). Conservative
    threshold of 200 ms per case + 1 s total catches a true 10-50x
    regression without flaking under CI variance.

    Skipped if any case file is somehow unreadable — perf test is a
    diagnostic safety net, not a build gate."""
    import time
    cases = sorted(L3_DIR.glob("case_*.json"))
    assert len(cases) >= 10  # plateau guarantee

    # Warm up to get past first-import overhead
    run(_load(cases[0].name))

    total = 0.0
    for case_file in cases:
        program = _load(case_file.name)
        t0 = time.perf_counter()
        run(program)
        t = time.perf_counter() - t0
        assert t < 0.200, (
            f"{case_file.name}: themis.run took {t*1000:.0f} ms, "
            f"exceeding 200 ms regression threshold (typical 2-5 ms). "
            f"A perf regression of this magnitude probably indicates a "
            f"missed optimization or accidental quadratic walk."
        )
        total += t
    assert total < 1.0, (
        f"Total L3 corpus runtime {total*1000:.0f} ms exceeds 1000 ms "
        f"regression threshold (typical ~36 ms)."
    )


def test_dispatch_conflict_persists_through_apply_patch_and_run():
    """iter 31 audit, symmetric with iter 30's unmeasured_confounder_risk
    test. unattempted_layer_due_to_dispatch_conflict triggers on the
    query shape (mediator + target_population both set). The query
    doesn't change across apply_patch_and_run rounds — only data does
    — so the advisory must persist. Pins 'data filling cannot elide
    a query-construction advisory.'"""
    from themis import apply_patch_and_run
    program = _load("case_009_mediation_x_transport.json")
    initial = run(program)
    initial_kinds = _gap_kinds(initial)
    assert "unattempted_layer_due_to_dispatch_conflict" in initial_kinds

    # Build a small framing patch (case 009 has 2 ambiguous_variable_definition
    # gaps that come with skeletons we can fill quickly)
    framing_ir = next(
        (
            ir for ir in initial["results"][0]["investigation_requests"]
            if ir["group"] == "framing"
        ),
        None,
    )
    if framing_ir is None:
        # No framing patch available — apply empty bundle just to round-trip
        patches: list[dict] = []
    else:
        patches = []
        for item in framing_ir["items"]:
            patch = dict(item["skeleton"])
            patch["fields"] = {
                "time_window": "12 weeks",
                "measurement": "test fixture",
                "threshold": "binary",
                "observability": "fully observable",
                "direction": "increasing",
                "baseline": "untreated",
                "state_vs_event": "event",
            }
            patches.append(patch)

    if patches:
        patched = apply_patch_and_run(program, patches)
        patched_kinds = _gap_kinds(patched)
        assert "unattempted_layer_due_to_dispatch_conflict" in patched_kinds, (
            "dispatch_conflict should persist through apply_patch_and_run; "
            f"query unchanged but advisory elided. gap_kinds: {patched_kinds}"
        )
