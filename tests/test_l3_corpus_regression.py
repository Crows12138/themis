"""L3 simulation corpus regression + structural pins.

Each case is a published study rendered as a program, kept so that the
kernel's answer to it stays the answer. Four of them were mined as
deliberate stress probes after the corpus had stopped finding anything,
and two of those four found real bugs.

Cases corpus (14):
- 001/002 backdoor (medicine) — measured confounders + no bidirected
- 003 IV via Balke-Pearl bounds (econ) — Card 1995 schooling-earnings
- 004 front-door (medicine) — Pearl smoking->tar->cancer
- 005 dose-response (medicine) — Whelton 2002 exercise-BP
- 006 mediation (epi) — Cnattingius 2004 smoking-birthweight
- 007 transport (medicine) — USPSTF 2022 statin to 75+
- 008 counterfactual (Layer 3) — Pearl 2009 monotone bounds
- 009 mediation × transport — the case that exposed a silent dispatch
  skip when a query names both
- 010 cause query (climate) — IPCC AR6 attribution
- 011 continuous treatment + measurement error (DASH-Sodium /
  INTERSALT). An anti-finding: it walks the extensions.ambiguities
  escape-hatch path and the kernel was right to stay quiet.
- 012 chain DAG × marginal-only theta probability query (Pearl
  1995/2009). A real bug: the d-sep guard was not engaged on the
  probability dispatch path because ``bidirected`` was dropped at that
  call site, so P(C|S,T) came back as the marginal instead of refusing.
- 013 single-occasion BP → CHD (MacMahon 1990 Lancet). A real finding:
  ``variable.measurement`` structurally signals regression dilution, and
  nothing read it — the origin of measurement_error_concern.
- 014 selection bias / loss to follow-up via implicit sample restriction
  (Hernán-Hernández-Díaz-Robins 2004 Epidemiology 15:615, "A Structural
  Approach to Selection Bias"). ObservationStatement(W, value) where W
  is a collider on X→Y triggers selection_on_collider_opens_path —
  distinct from collider_conditioning_opens_backdoor, which fires on
  EffectQuery.given.

Pins:
- test_l3_case_emits_expected_gap_kinds — parametrised per case, over
  its must-have and must-not-have gap_kind lists
- test_l3_corpus_count_at_plateau — the corpus does not shrink
- test_dispatch_conflict_fires_on_mediator_plus_target_pop
- test_dispatch_conflict_suppressed_when_only_mediator
- test_dispatch_conflict_suppressed_when_only_target_pop
- test_dispatch_conflict_persists_through_apply_patch_and_run
- test_l3_corpus_runtime_regression — 200 ms/case + 1 s total; the
  corpus currently runs ~6 ms at its slowest case
- test_every_l3_case_json_has_matching_markdown
- test_l3_readme_case_index_matches_actual_files
- test_every_l3_case_file_has_regression_test_entry
- test_every_l3_case_md_has_required_sections
- test_l3_corpus_docstring_inventories_all_test_functions — every test
  above is named here, the same self-pin
  ``tests/test_gap_kind_coverage_meta.py`` carries

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
        # query has BOTH mediator + target_population, so
        # unattempted_layer_due_to_dispatch_conflict surfaces the skip
        # the dispatcher would otherwise take silently
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
    (
        "case_011_salt_blood_pressure.json",
        # An anti-finding: this continuous-treatment + measurement-error
        # case is already covered by the existing gap_kinds. Effect
        # query with multiple confounders (overall_diet_quality,
        # physical_activity); unmeasured_confounder_risk fires
        # (no bidirected); llm_declared_ambiguity catches my
        # measurement_quality declaration; bounds layer attaches
        # manski_natural since theta absent.
        ["missing_distribution",
         "ambiguous_variable_definition",
         "answer_is_bounds_not_point_estimate",
         "llm_declared_ambiguity",
         "unmeasured_confounder_risk"],
        ["unattempted_layer_due_to_dispatch_conflict",
         "iv_identification_assumption_required",
         "front_door_identification_assumption_required"],
    ),
    (
        "case_012_pearl_chain_dsep_refusal.json",
        # Pearl's smoking-tar-cancer chain (S→T→C) with marginal-only
        # theta P(C|S) and a probability query asking P(C|S,T). If
        # _dispatch_probability stops threading bidirected into
        # _try_numeric, the d-sep guard goes dormant across the whole
        # probability dispatch path and Themis silently returns 0.18 —
        # the marginal — instead of refusing. What this case pins:
        #   - graph_theta_independence_mismatch fires
        #   - status = needs_investigation, no numeric value
        #   - the substituted-marginal route stays closed for prob queries
        # NOT missing_distribution: the d-sep refusal signature routes to
        # the dedicated kind, because the repair is a different one.
        ["graph_theta_independence_mismatch",
         "ambiguous_variable_definition"],
        ["missing_distribution",
         "unmeasured_confounder_risk",
         "front_door_identification_assumption_required"],
    ),
    (
        "case_013_macmahon_bp_chd_regression_dilution.json",
        # A real finding: MacMahon 1990 Lancet 335:765 BP-CHD
        # meta-analysis. Variable bp_diastolic_high.measurement names
        # 'single-occasion office sphygmomanometer' — a documented
        # regression-dilution source attenuating the BP-CHD slope ~60%.
        # Without a classifier reading it, Themis returns a full envelope
        # carrying no measurement-error signal at all.
        # measurement_error_concern fires from program shape
        # (variable.measurement contains
        # 'single-occasion'), severity IMPORTANT, with provenance ref
        # naming the offending (variable, field, pattern). NOT suppressed
        # because extensions.ambiguities is empty (case 011 escape-hatch
        # path is the suppression branch).
        ["measurement_error_concern",
         "missing_distribution",
         "ambiguous_variable_definition",
         "unmeasured_confounder_risk"],
        ["graph_theta_independence_mismatch",
         "weak_iv_instrument",
         "front_door_identification_assumption_required",
         "unattempted_layer_due_to_dispatch_conflict"],
    ),
    (
        "case_014_hernan_2004_selection_bias.json",
        # A real finding: Hernán-Hernández-Díaz-Robins 2004
        # Epidemiology 15:615 "A Structural Approach to Selection Bias"
        # — HIV/AZT → AIDS-death cohort with loss-to-follow-up indicator
        # `selected` caused by both AZT (treatment-driven retention) and
        # AIDS-death (terminal-event-driven sample loss). The program
        # encodes implicit sample restriction via
        # ObservationStatement(selected, True). Covered by
        # collider_conditioning_opens_backdoor alone, this case gets no
        # selection-bias signal: that kind fires on EffectQuery.given
        # (explicit conditioning) and not on ObservationStatement
        # (implicit sample restriction), so the envelope comes back
        # complete and silent. selection_on_collider_opens_path fires
        # from program shape instead — an ObservationStatement on a node
        # that has both intervention and target as ancestors — at
        # severity IMPORTANT. The negative assertion below pins the two
        # apart, so merging both paths into one kind fails here.
        ["selection_on_collider_opens_path",
         "missing_distribution",
         "ambiguous_variable_definition"],
        ["collider_conditioning_opens_backdoor",
         "graph_theta_independence_mismatch",
         "weak_iv_instrument",
         "transport_target_distribution_unknown",
         "unattempted_layer_due_to_dispatch_conflict"],
    ),
    (
        "case_015_hernan_taubman_2008_obesity_well_defined.json",
        # A real finding: Hernán-Taubman 2008 IJO 32(S3):S8
        # "Does obesity shorten life? The importance of well-defined
        # interventions to answer causal questions" — obesity → 5yr
        # mortality with state_vs_event="state" declared on the obese
        # predicate but no time_window, plus the 'compound treatment'
        # methodology critique that the same obese state value can be
        # reached by structurally-different manipulations (gastric
        # surgery / diet / GLP-1 / metabolic disease) which entail
        # DIFFERENT counterfactual outcomes. The state_vs_event schema
        # field admitted "state" / "event" for a long time with no
        # classifier reading the VALUE — the third field of that shape,
        # after variable.measurement and the ObservationStatement.
        # ill_defined_intervention_versions
        # fires on the state-without-time_window shape with Hernán &
        # Taubman 2008 anchor + four named repair options (event-
        # encoding / mediation split / RCT / opt-in mixed estimand).
        # 2026-05 retest extended trigger to also fire when both
        # state_vs_event and time_window are absent (inferred state-
        # like shape — the most common LLM-emitted form).
        ["ill_defined_intervention_versions",
         "missing_distribution",
         "ambiguous_variable_definition",
         "unmeasured_confounder_risk"],
        ["collider_conditioning_opens_backdoor",
         "selection_on_collider_opens_path",
         "graph_theta_independence_mismatch",
         "weak_iv_instrument",
         "transport_target_distribution_unknown",
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

    Adding a .json without its .md fails here rather than leaving a case
    in the corpus that nobody can read the provenance of.
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

    Catches the
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


def test_every_l3_case_md_has_required_sections():
    """Every case_NNN_*.md must include the standard L3 audit sections:
    - `## NL question` — what the user actually asked
    - `## Authoritative source` — external ground truth
    - `## 历史` — iter-by-iter assessment trail

    The L3 audit methodology relies on every
    case .md describing (a) the user-facing question, (b) the external
    authority being checked against, and (c) the assessment evolution.
    A case without these sections breaks the corpus comparability.

    All 10 currently consistent. Pin holds."""
    required = ["## NL question", "## Authoritative source", "## 历史"]
    violations = []
    for f in sorted(L3_DIR.glob("case_*.md")):
        text = f.read_text(encoding="utf-8")
        missing = [s for s in required if s not in text]
        if missing:
            violations.append(f"{f.name}: missing {missing}")
    assert not violations, "\n".join(violations)


def test_every_l3_case_file_has_regression_test_entry():
    """Every case_NNN_*.json under docs/l3_simulation/ must have a
    matching entry in this file's CASES list (the parametrized
    regression test source of truth).

    Without this, a contributor adds
    case 011 + .md + index entry but forgets to add to CASES — the
    new case has no regression test until manually noticed.

    Comparison is by case file name, not number, since CASES holds
    the file path as the first tuple element."""
    cased_files = {entry[0] for entry in CASES}
    actual_files = {f.name for f in L3_DIR.glob("case_*.json")}
    missing = actual_files - cased_files
    extra = cased_files - actual_files
    assert not missing, (
        f"L3 case files without regression test entry in CASES list: "
        f"{sorted(missing)}. Add tuples to test_l3_corpus_regression.py "
        f"CASES with (file, must_have, must_not_have)."
    )
    assert not extra, (
        f"CASES list references non-existent case files: {sorted(extra)}"
    )


def test_l3_corpus_docstring_inventories_all_test_functions():
    """The self-pin, symmetric with
    test_meta_test_docstring_inventories_all_test_functions in
    test_gap_kind_coverage_meta.py.

    Every test_… function in this file must appear BY NAME in the module
    docstring's inventory. Naming matters: a summary line like "+ 2
    suppression tests" satisfies a reader and hides which two, so the
    check is on names rather than on counts.
    """
    import ast
    self_text = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(self_text)
    actual = sorted(
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    )
    docstring = ast.get_docstring(tree) or ""
    missing = [name for name in actual if name not in docstring]
    assert not missing, (
        f"Module docstring inventory missing test names: {missing}. "
        f"Add to the appropriate section in the docstring."
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
    """When a query has both mediator and target_population
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
    """A performance pin. Each L3 case currently runs in 2-6 ms, total
    ~36 ms (measured on this machine, re-checked three times for
    flake). A conservative threshold of 200 ms per case + 1 s total
    catches a true 10-50x regression without flaking under CI variance.

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
    """Symmetric with the unmeasured_confounder_risk version of the same
    check. unattempted_layer_due_to_dispatch_conflict triggers on the
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
