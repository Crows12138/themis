"""Meta-tests: cross-file invariants + structural pins.

Originally seeded by iter 25 ('every GapKind has test reference') after
iter 5/19 added two new gap_kinds. The file accumulated additional
sync / preventive pins through iter 90 as drift categories were
caught:

GapKind sync (iter 25-26, 37):
- test_gap_kind_has_test_coverage — every enum value referenced
- test_gap_kind_enum_synced_with_schema — types ↔ JSON schema
- test_gap_kind_enum_synced_with_verifier_registry — types ↔ T10
- test_must_disclose_set_is_subset_of_gap_kinds — scheduler whitelist
- test_must_disclose_kinds_documented_in_response_rendering_prompt

Doc / count sync (iter 42, 45, 56, 58, 59, 60, 89):
- test_test_count_consistent_between_core_status_and_readme
- test_package_version_matches_roadmap_and_core_status
- test_failure_modes_header_count_matches_actual_entries
- test_eval_set_readme_counts_match_actual_files
- test_coverage_map_mcp_counts_match_actual_server
- test_mcp_readme_counts_match_actual_server (iter 104, symmetric with
  iter 59 COVERAGE_MAP pin)
- test_mcp_readme_catalog_tables_match_server (iter 105 — count pin
  alone missed the table contents drifting independently of the prose
  count: iter 103 fixed the prose count but tables still listed
  5 tools / 8 resources)
- test_mcp_server_docstring_lists_all_tools_and_resources (iter 105 —
  same drift class as the README tables, in the server.py module
  docstring; both surfaces need to stay synced with @app.tool() and
  @app.resource() registrations)
- test_readme_query_kind_list_matches_enum (iter 106 — README "当前能力"
  section listed 5 kinds while QueryKind enum has 6; counterfactual
  was added by Phase 5 §C but README claim never updated)
- test_coverage_map_gap_kind_count_matches_enum (iter 107 — COVERAGE_MAP
  元基础设施 row claimed "8 gap_kind" but GapKind grew to 22 via
  Phase 13 dose-response + iter 5/19 + later additions; same drift
  class as iter 105/106 — current-state inventory frozen at initial
  scope while the actual registry kept growing)
- test_kb_readme_gap_to_query_kind_table_matches_translator (iter 108 —
  themis/kb/README.md "Mapping gaps to query kinds" table missed
  missing_population_distribution + transport_source_conditional_unknown
  rows; drifted from _GAP_TO_QUERY_KIND in translator.py)
- test_kb_readme_confidence_grade_ladder_matches_enum (iter 109 — KB
  README claimed "five-level GRADE-style ladder" but KBConfidenceGrade
  enum has 6 values; ladder text also listed 6 entries while saying
  "five". Pin asserts the named values in the prose match the enum)
- test_bounds_method_producers_have_rendering_template (iter 110 —
  preventative: every BoundsMethod value actually produced by
  themis/output/bounds.py must have a matching '#### `method_name`'
  section in response_rendering.md. Locks the LLM-rendering coverage
  invariant for future bounds solvers — current state is in sync but
  adding a frontdoor_partial / manski_tamer producer without prompt
  template would silently downgrade rendering)
- test_numeric_estimate_method_enum_documented_in_prompt (iter 132 —
  parallel to iter 110 but for numeric_estimate.method enum: every
  value in query_result.schema.json's method enum must appear
  verbatim in response_rendering.md. iter 128 added
  transport_post_stratification + iter 124 extended sensitivity to
  continuous outcome but neither was prompt-documented for 4 iters
  — this pin catches that drift class going forward.)
- test_must_disclose_gap_kinds_documented_in_gap_to_action (iter 136
  — parallel to iter 132 but for gap_to_action.md: every must-disclose
  gap_kind + the iter 120/121/123 estimator-runtime gap_kinds must
  appear verbatim in the prompt's Q0 INFORMATIONAL list. iter 119-134
  added 4 new gap_kinds that drifted out of gap_to_action for ~16
  iters until iter 136 caught it.)
- test_every_gap_kind_documented_in_reference (iter 139 — every
  GapKind enum value must have a row in docs/GAP_KINDS_REFERENCE.md.
  Single-source human-readable table for the 26 gap_kinds; previously
  scattered across types.py docstrings, classifier descriptions in
  data_gap_report.py, gap_to_action.md, response_rendering.md.)
- test_precision_budget_field_documented_in_rendering_prompt (iter
  157 sync pin — iter 151-155 wired numeric_estimate.precision_budget
  into all 6 estimator paths; iter 156 added §Precision budget to
  response_rendering.md. Pin asserts the field name + section heading
  + 3 schema-shape tokens (decomposition / dose_response_curve /
  n_to_halve_ci) all appear in the prompt so the LLM knows what to
  surface. Catches future renames.)
- test_precision_budget_method_specific_caveats_documented (iter
  177 sync pin — iter 161 added §Method-specific caveats inside
  §Precision budget covering IV/mediation/frontdoor/transport/
  dose-response/backdoor; each method has different "more N means"
  semantics. Pin asserts each category's anchor keyword survives
  future prompt edits so LLMs don't naively render "recruit N more"
  without method-aware caveat.)
- test_identification_formula_witness_set_synced_with_scheduler
  (iter 183 sync pin — iter 182 hoisted IDENTIFICATION_FORMULA_RULES
  to module level after iter 181 discovered front-door variant was
  silently rejected by the verifier's hardcoded backdoor-only check.
  Pin asserts the set membership exactly so a future identification
  path that emits a symbolic formula must be added to BOTH the set
  and this pin's expected literal — preventing the iter 182 silent-
  rejection drift class.)
- test_precision_budget_in_query_result_schema (iter 157 sync pin —
  iter 152→154 had a 2-iter silent schema violation: precision_budget
  emitted but query_result.schema.json with additionalProperties=false
  rejected it through verify(). Pin asserts $defs/precisionBudget
  exists AND is referenced from ≥5 sites — top-level
  numeric_estimate, each of nde/nie/te/proportion_mediated under
  decomposition, plus dose_response_curve.items.)
- test_estimation_init_docstring_inventories_all_exports (iter 111 —
  themis/estimation/__init__.py docstring described "Phase 7.1 scope"
  while the package had grown to include Phase 8.1 / 8.2 / 14
  exports; pin asserts every __all__ name appears in the docstring
  body so future additions force docstring updates)
- test_subpackage_init_docstrings_inventory_all_exports (iter 112 —
  same drift class as iter 111, applied to themis.kb / themis.upstream
  / themis.verifier / themis.mcp: each had __all__ exporting 2-19
  names with most/all missing from the module docstring. mcp also said
  "four public ... entry points" which was stale (now seven). One pin
  parametrized over the four packages forces docstring sync going
  forward.)
- test_workflow_init_docstring_lists_all_submodules (iter 113 — for
  packages without __all__ that explicitly enumerate their submodules
  in the docstring (workflow listed only ``parameter_fill`` while
  ``variable_framing`` had been there for phases). Pin asserts every
  public .py module in themis/workflow/ is referenced in the
  __init__.py docstring. Web __init__ also had stale "no NL → JSON
  bridge yet" prose despite mode (a) Ask landing — fixed in same
  commit but not pinned because web docstring describes endpoints
  rather than modules; no clean enumeration to pin against.)
- test_prompt_header_word_counts_match_subsection_counts (iter 114 —
  gap_to_action.md "## Three questions per gap" had 4 ### subsections
  (Q0 pre-screen + Q1–Q3 walk) — header count drifted when Q0 was
  added later. Pin scans every "## <number-word> <noun>" header in
  docs/prompts/ and asserts the immediate ### subsection count
  matches the spelled-out number.)
- test_kernel_docstring_lists_all_public_entries (iter 115 —
  themis/kernel.py docstring described only run / apply_patch_and_run
  / verify (3 of 5 entries). estimate (Phase 7) and
  verify_data_gap_report (Phase 10) had been there for phases but the
  docstring was never updated. Pin asserts every name re-exported
  from themis.kernel into themis.__all__ appears in kernel.py's
  module docstring.)
- test_formula_ast_spec_node_count_matches_types (iter 116 —
  formula_ast_spec_v0_1.md version pointer header claimed "5 core
  nodes" listing Sum / Product / ProbabilityRef / BindDecl / VarRef
  while ConstantExpr was always a 6th node since v0.1. Pin asserts
  the 五/六/七 claim in the header matches the count of formula AST
  dataclass names actually present in themis/types.py.)
- test_eval_set_readme_gold_query_kind_matches_enum (iter 117 —
  docs/eval_set/README.md "Per-case JSON schema" example listed
  only 5 gold_query_kind values (cause / assoc / effect / identify
  / probability) while QueryKind enum has 6 (counterfactual added
  Phase 5 §C). Same drift class as iter 106 in a different doc.)
- test_data_gap_report_docstring_must_disclose_section_accurate
  (iter 118 — themis/output/data_gap_report.py module docstring
  categorized transport_source_conditional_unknown +
  dose_response_data_required under "must-disclose channel" but
  they are NOT in scheduler._MUST_DISCLOSE_GAP_KINDS — they're
  data needs that surface only via data_gap_report, not auto-
  mirrored to explanation. Restructured into a separate "data-need
  gap_kinds" section. Pin asserts the docstring's must-disclose
  list mirrors the actual scheduler set.)
- test_readme_subpackage_list_matches_actual
- test_status_docs_have_update_timestamp

Path / link integrity (iter 63-66, 84):
- test_no_windows_absolute_paths_in_committed_files
- test_markdown_cross_links_resolve
- test_markdown_backtick_path_refs_resolve

Structure / docstring (iter 34, 67, 72, 77, 79, 80, 90):
- test_no_orphan_test_files
- test_themis_init_all_matches_imports
- test_themis_init_docstring_exception_imports_resolve
- test_themis_py_files_have_module_docstrings
- test_scripts_py_files_have_module_docstrings
- test_tests_py_files_have_module_docstrings
- test_wall_md_has_required_structure
- test_every_phase_charter_declares_status (iter 55)

Hygiene (iter 62, 69, 76):
- test_readme_public_entry_imports_actually_resolve
- test_kernel_run_emits_no_deprecation_warnings
- test_all_committed_json_files_parse_cleanly

Eval set internal (iter 61):
- test_eval_set_cases_have_internally_consistent_edges — every
  gold_edges from/to predicate must appear in gold_variables

Self-meta (iter 94):
- test_meta_test_docstring_inventories_all_test_functions — every
  test_… function in this file must be mentioned in this docstring;
  catches 'added test, forgot to inventory' regression (iter 91→93
  was that exact pattern)

Each pin documents which iter found the original drift (if any) plus
the regression class it guards. Add new pins symmetric with existing
patterns when new drift classes surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.types import GapKind


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"


def _all_test_text() -> str:
    """Concatenate the bodies of every test file. Once. Cached because
    the corpus is small enough that re-reading per gap_kind is fine."""
    parts: list[str] = []
    for p in TESTS_DIR.rglob("test_*.py"):
        if p.name == Path(__file__).name:
            continue  # don't count this meta-file as coverage
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


_TEST_TEXT_CACHE: str | None = None


def _test_text() -> str:
    global _TEST_TEXT_CACHE
    if _TEST_TEXT_CACHE is None:
        _TEST_TEXT_CACHE = _all_test_text()
    return _TEST_TEXT_CACHE


@pytest.mark.parametrize(
    "kind", list(GapKind), ids=[k.value for k in GapKind]
)
def test_gap_kind_has_test_coverage(kind: GapKind):
    """Every GapKind enum value must appear in at least one test file —
    either as an assertion in must-have / must-not-have lists, or as a
    direct reference. Catches 'added enum, forgot test' regressions."""
    needle = kind.value
    text = _test_text()
    assert needle in text, (
        f"GapKind.{kind.name} (value={needle!r}) does not appear in any "
        f"test file under {TESTS_DIR}. Add at least one positive or "
        f"suppression assertion when introducing a new gap_kind."
    )


def test_gap_kind_enum_synced_with_schema():
    """The query_result.schema.json gap_kind enum and Python GapKind enum
    must list exactly the same values. Adding to one but forgetting the
    other (a real risk; iter 5/19 had to update both manually) breaks
    schema validation in opaque ways."""
    import json
    schema = json.loads(
        (REPO_ROOT / "themis" / "schemas" / "query_result.schema.json").read_text(encoding="utf-8")
    )
    schema_kinds = set(schema["$defs"]["dataGap"]["properties"]["kind"]["enum"])
    enum_kinds = {k.value for k in GapKind}
    only_in_schema = schema_kinds - enum_kinds
    only_in_enum = enum_kinds - schema_kinds
    assert not only_in_schema, (
        f"gap_kinds in schema but missing from GapKind enum: {only_in_schema}"
    )
    assert not only_in_enum, (
        f"gap_kinds in GapKind enum but missing from schema: {only_in_enum}. "
        f"Add to query_result.schema.json $defs.dataGap.properties.kind.enum."
    )


def test_gap_kind_enum_synced_with_verifier_registry():
    """The verifier's _KIND_ACCEPTS_REF must have an entry for
    every GapKind enum value. T10-3 raises VerificationError when a gap
    has an unregistered kind, so missing registrations cause silent
    test failures the moment the gap fires (caught by iter 5 hard way
    when test_t10_passes_on_real_dispatch_output failed before the
    verifier registration was added)."""
    from themis.verifier.data_gap_rules import _KIND_ACCEPTS_REF
    registry_kinds = set(_KIND_ACCEPTS_REF.keys())
    enum_kinds = {k.value for k in GapKind}
    only_in_registry = registry_kinds - enum_kinds
    only_in_enum = enum_kinds - registry_kinds
    assert not only_in_registry, (
        f"verifier registry has unknown gap_kinds: {only_in_registry}"
    )
    assert not only_in_enum, (
        f"GapKind values missing from verifier registry: {only_in_enum}. "
        f"Add to themis/verifier/data_gap_rules.py _KIND_ACCEPTS_REF."
    )


def test_must_disclose_set_is_subset_of_gap_kinds():
    """The scheduler's _MUST_DISCLOSE_GAP_KINDS whitelist must be a
    subset of GapKind values. A typo or rename would make the gap
    silently NOT auto-prepend to result.explanation."""
    from themis.runtime.scheduler import _MUST_DISCLOSE_GAP_KINDS
    enum_kinds = {k.value for k in GapKind}
    unknown = _MUST_DISCLOSE_GAP_KINDS - enum_kinds
    assert not unknown, (
        f"_MUST_DISCLOSE_GAP_KINDS has unknown values: {unknown}. "
        f"Either typo or stale enum reference."
    )


def test_must_disclose_kinds_documented_in_response_rendering_prompt():
    """Every gap_kind in scheduler._MUST_DISCLOSE_GAP_KINDS must appear
    in docs/prompts/response_rendering.md's mirrored-set table. The
    table is the contract the renderer LLM reads to know which gap_kinds
    are auto-prepended to result.explanation as ⚠ lines (so the
    renderer doesn't itemize them again).

    Adding a kind to _MUST_DISCLOSE_GAP_KINDS without updating the prompt
    breaks the contract silently — the LLM might double-render or fail
    to surface the caveat. Iter 9 (unmeasured_confounder_risk) and
    iter 19 (dispatch_conflict) both required this prompt update; this
    test catches the third or fourth time.
    """
    from themis.runtime.scheduler import _MUST_DISCLOSE_GAP_KINDS
    rendering_md = (
        REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
    ).read_text(encoding="utf-8")
    missing = []
    for kind in _MUST_DISCLOSE_GAP_KINDS:
        # Look for the kind name in a backtick-quoted form, which is
        # how the prompt's mirrored-set table cites it.
        if f"`{kind}`" not in rendering_md:
            missing.append(kind)
    assert not missing, (
        f"_MUST_DISCLOSE_GAP_KINDS members missing from "
        f"response_rendering.md prompt: {missing}. Add a row to the "
        f"mirrored-set table at docs/prompts/response_rendering.md."
    )


def test_precision_budget_field_documented_in_rendering_prompt():
    """Iter 156 sync pin: when dispatch emits ``precision_budget`` on
    numeric_estimate, response_rendering.md must document how the LLM
    should surface it. Otherwise downstream LLMs read raw JSON without
    knowing the field exists or when to mention it.

    iter 151 added the helper, 152-155 wired it into all 6 estimator
    paths, 156 documented it. This pin keeps the docs in lockstep:
    if a future iter renames or removes the field without updating the
    prompt, the test fails.
    """
    rendering_md = (
        REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
    ).read_text(encoding="utf-8")
    # The renderer prompt must mention the field name verbatim AND
    # the dedicated section heading (so the LLM finds it via TOC).
    assert "`precision_budget`" in rendering_md, (
        "response_rendering.md does not mention the `precision_budget` "
        "field. Add the field-table row + §Precision budget section "
        "(see iter 156)."
    )
    assert "Precision budget" in rendering_md, (
        "response_rendering.md is missing the §Precision budget section."
    )
    # The §Precision budget section must reference all three locations
    # — top-level (single-CI estimators), decomposition (mediation),
    # and dose_response_curve (per-curve-point).
    for token in ("decomposition", "dose_response_curve", "n_to_halve_ci"):
        assert token in rendering_md, (
            f"response_rendering.md §Precision budget missing reference "
            f"to '{token}'. The renderer needs to know about all 3 "
            f"locations the field appears in across estimator shapes."
        )


def test_identification_formula_witness_set_synced_with_scheduler():
    """Iter 183 sync pin: themis.verifier.verify.IDENTIFICATION_FORMULA_RULES
    must include every rule name the scheduler emits as a formula
    witness (consumed by formula_evaluation). Pre-iter-182 only
    backdoor was admitted; iter 182 added front-door after iter 181
    discovered the gap. If scheduler adds a new identification path
    that emits a symbolic formula (e.g. tian_c_formula), this pin
    fails so the verifier set is updated alongside.

    Today's emitters (verified via grep on themis/runtime/scheduler.py
    rule= sites that produce FormulaExpr-typed output):
    - backdoor_adjustment_formula
    - front_door_adjustment_formula
    - transport_formula_ast (Fix 3+4 §T9.2)

    transport_formula (string repr step, separate from
    transport_formula_ast) emits a STRING repr (not FormulaExpr) and
    stays excluded — it's the human-readable rendering witness, not
    the machine-evaluable one.
    """
    from themis.verifier.verify import IDENTIFICATION_FORMULA_RULES
    expected = frozenset({
        "backdoor_adjustment_formula",
        "front_door_adjustment_formula",
        "transport_formula_ast",
        # Fix 5 (v0.1.5, audit follow-up): Tian-in-effect bound
        # formula step. Parallel to transport_formula_ast.
        "tian_formula_ast",
    })
    assert IDENTIFICATION_FORMULA_RULES == expected, (
        f"IDENTIFICATION_FORMULA_RULES drift: got "
        f"{IDENTIFICATION_FORMULA_RULES}, expected {expected}. "
        f"If a new identification path emits a symbolic formula, "
        f"add it to the set in verify.py AND this pin's expected set."
    )


def test_precision_budget_method_specific_caveats_documented():
    """Iter 177 sync pin: iter 161 added method-specific caveats to
    response_rendering.md's §Precision budget for the 6 estimator
    paths. Each method has different "more N" semantics:
    - IV (wald/2sls): compliers, not all takers
    - mediation_*: joint M+Y rows
    - frontdoor_*: M+Y joint requirement
    - transport_post_stratification: weakest stratum N
    - dose_response_*: per-curve-point allocation
    - backdoor_*: straightforward joint (X,Y,Z)

    Without these caveats LLMs render "recruit N more" naively. Pin
    asserts each method category's keyword appears in the §Precision
    budget section; drift in the prompt fails the test before
    deployment.
    """
    rendering_md = (
        REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
    ).read_text(encoding="utf-8")
    # Anchor: §Method-specific caveats inside §Precision budget
    assert "Method-specific caveats" in rendering_md
    # Each method category must be referenced with its key term
    method_keywords = {
        "IV": ("iv_wald", "iv_2sls", "compliers"),
        "mediation": ("mediation_*", "joint M+Y", "M and Y"),
        "frontdoor": ("frontdoor_*", "M and Y on the same units",),
        "transport": ("transport_post_stratification", "weakest", "stratum"),
        "dose_response": ("dose_response_*", "per-curve-point", "per point"),
        "backdoor": ("backdoor_*",),
    }
    missing = []
    for category, keywords in method_keywords.items():
        present = [kw for kw in keywords if kw in rendering_md]
        if not present:
            missing.append(category)
    assert not missing, (
        f"§Method-specific caveats missing references for "
        f"{missing}. Iter 161 added them; future doc edits must "
        f"preserve at least one keyword per method category."
    )


def test_precision_budget_in_query_result_schema():
    """Iter 156 sync pin: query_result.schema.json must define
    precisionBudget under $defs and reference it from numeric_estimate
    + decomposition components + dose_response_curve. Drift here would
    cause themis.verify() to reject results carrying the field (the
    iter 152→154 silent-violation pattern)."""
    schema_text = (
        REPO_ROOT / "themis" / "schemas" / "query_result.schema.json"
    ).read_text(encoding="utf-8")
    assert '"precisionBudget"' in schema_text, (
        "query_result.schema.json missing $defs/precisionBudget. iter "
        "151+152 added the helper + dispatch wire; the schema needs "
        "to whitelist the field or themis.verify() will reject."
    )
    # Should be referenced at all three structural shapes
    assert schema_text.count("#/$defs/precisionBudget") >= 5, (
        "query_result.schema.json should reference precisionBudget "
        "from numeric_estimate top-level + each of nde/nie/te/"
        "proportion_mediated under decomposition + dose_response_curve "
        "items (iter 152-155 wires)."
    )


def test_package_version_matches_roadmap_and_core_status():
    """themis.__version__ in themis/__init__.py must match the version
    quoted in ROADMAP.md / CORE_STATUS.md / README.md. Iter 45 found
    this drift the hard way: __version__ was '0.14.0-dev' for an entire
    release cycle while doc files all said '0.15.0-dev'.

    The version string moves with each release boundary; pin sync so
    bumping one and forgetting another fails fast."""
    import themis
    pkg_version = themis.__version__

    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    core = (REPO_ROOT / "CORE_STATUS.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert pkg_version in roadmap, (
        f"themis.__version__ = {pkg_version!r} not found in ROADMAP.md "
        f"(expected the file to quote the same version somewhere)"
    )
    assert pkg_version in core, (
        f"themis.__version__ = {pkg_version!r} not found in CORE_STATUS.md"
    )
    assert pkg_version in readme, (
        f"themis.__version__ = {pkg_version!r} not found in README.md"
    )


def test_test_count_consistent_between_core_status_and_readme():
    """CORE_STATUS.md and README.md both quote 'N passed / M skipped' as
    the current full-suite baseline. They must agree — iter 5 onwards
    each test-adding commit updated both manually, easy to miss one.

    Pin: extract the count line from each file via regex, assert equal.
    Future test-count changes update both files (or this test catches
    the drift)."""
    import re
    pattern = re.compile(r"(\d+)\s*passed\s*/\s*(\d+)\s*skipped")
    core = (REPO_ROOT / "CORE_STATUS.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    core_match = pattern.search(core)
    readme_match = pattern.search(readme)
    assert core_match, "CORE_STATUS.md must list 'N passed / M skipped'"
    assert readme_match, "README.md must list 'N passed / M skipped'"
    assert core_match.groups() == readme_match.groups(), (
        f"CORE_STATUS.md says {core_match.group()} but README.md says "
        f"{readme_match.group()}. Both files quote the test baseline; "
        f"keep them in sync."
    )


def test_meta_test_docstring_inventories_all_test_functions():
    """Iter 91-93 self-meta find: this file's module docstring lists
    each pin by category. Iter 91 wrote it with 26 entries; iter 93
    audit found one missing (eval_set consistency from iter 61) and
    the docstring's category total was wrong by 1.

    Iter 94 pin: count test_… function definitions in this file,
    count test name mentions in the module docstring's bullet lines,
    assert every actual function name appears in docstring bullets.

    Catches the 'add new pin, forget docstring entry' regression.
    """
    import ast
    self_text = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(self_text)
    actual_test_funcs = sorted(
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )
    docstring = ast.get_docstring(tree) or ""
    missing = [
        name for name in actual_test_funcs if name not in docstring
    ]
    assert not missing, (
        f"Module docstring inventory missing test names: {missing}. "
        f"Add to the appropriate '<Category>:' section."
    )


def test_wall_md_has_required_structure():
    """wall.md is the autonomous-loop blocker log — central to the
    /loop's design. Iter 90 preventive pin: must exist + must have
    a `Format:` declaration line + at least one ## YYYY-MM-DD entry.

    Without these, the loop's "记在 wall.md" instruction has no
    parseable target. Catches accidental deletion / restructure that
    breaks the audit log's contract.
    """
    import re
    wall_path = REPO_ROOT / "wall.md"
    assert wall_path.exists(), "wall.md must exist (autonomous-loop blocker log)"
    text = wall_path.read_text(encoding="utf-8")
    assert re.search(r"^Format[：:]", text, re.MULTILINE), (
        "wall.md must have a 'Format:' declaration line at top describing "
        "entry shape"
    )
    entry_re = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}", re.MULTILINE)
    entries = entry_re.findall(text)
    assert entries, (
        "wall.md must have at least one '## YYYY-MM-DD …' entry. "
        "An empty wall.md means the loop has nothing to read on "
        "subsequent iters."
    )


def test_status_docs_have_update_timestamp():
    """CORE_STATUS.md and COVERAGE_MAP.md must declare a `更新时间`
    timestamp in their header. Iter 85-87 found three timestamp drifts
    where these fields existed but were stale; iter 89 pin guards
    against the field being silently removed (which would make future
    drift undetectable by audit).

    Field format: `> 更新时间：YYYY-MM-DD`. The audit only checks
    presence, not freshness — staleness depends on file content
    history which can't be reliably regex'd.
    """
    import re
    pattern = re.compile(r"^>\s*更新时间[：:]\s*\d{4}-\d{2}-\d{2}",
                          re.MULTILINE)
    for fname in ("CORE_STATUS.md", "COVERAGE_MAP.md"):
        text = (REPO_ROOT / fname).read_text(encoding="utf-8")
        assert pattern.search(text), (
            f"{fname} must declare '> 更新时间：YYYY-MM-DD' in header. "
            f"Without it, doc-content drift can't be flagged by audit."
        )


def test_failure_modes_header_count_matches_actual_entries():
    """docs/eval_set/failure_modes.md header quotes 'N codes' as the
    taxonomy size. Iter 56 found this stale: header said '22 codes'
    while file actually had 26 (F23-F26 added without updating count).

    Pin: regex extract header count + count actual `## F\\d+` entries;
    assert equal.
    """
    import re
    fm = (REPO_ROOT / "docs" / "eval_set" / "failure_modes.md").read_text(
        encoding="utf-8"
    )
    header_match = re.search(r"(\d+)\s+codes\.", fm)
    assert header_match, "failure_modes.md header must quote 'N codes.'"
    header_count = int(header_match.group(1))
    actual_codes = re.findall(r"^##\s+F\d+", fm, re.MULTILINE)
    assert header_count == len(actual_codes), (
        f"failure_modes.md header says {header_count} codes but file has "
        f"{len(actual_codes)}: {[c.strip() for c in actual_codes[:5]]}... "
        f"Update the 'N codes' line in the header."
    )


def test_readme_public_entry_imports_actually_resolve():
    """README.md '公开入口' code block shows `from themis import (...)`
    listing the public API. Iter 62 pin: extract those names + assert
    every one is actually importable + callable from `themis`. Catches
    a future README drift where someone removes a function from
    themis/__init__.py without updating the README example.

    Also catches the reverse drift: if a function is added to
    __init__.py but NOT mentioned in README example, the test fails
    only by the reverse direction (only enforces 'README names exist'
    not 'all exports are documented'); the doc-completeness side is
    judgement, not strict invariant."""
    import re
    import themis
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Match either `from themis import (a, b, c)` or `from themis import a, b, c`
    block_matches = re.findall(
        r"from\s+themis\s+import\s+(?:\(\s*([^)]+?)\s*\)|([^\n#]+))",
        readme,
    )
    assert block_matches, "README must contain 'from themis import …' block"
    names: list[str] = []
    for paren_form, line_form in block_matches:
        raw = paren_form or line_form
        for n in raw.split(","):
            n = n.strip()
            if n and not n.startswith("#"):
                names.append(n)
    missing = []
    for name in names:
        attr = getattr(themis, name, None)
        if attr is None or not callable(attr):
            missing.append(name)
    assert not missing, (
        f"README cites these names in 'from themis import (...)' but "
        f"they are not importable + callable from themis: {missing}"
    )


def test_kernel_run_emits_no_deprecation_warnings():
    """Importing `themis` and running a representative L3 case must not
    emit DeprecationWarning. Iter 68 silenced the pytest-asyncio config
    warning; iter 69 pins kernel-level cleanliness so a future
    DeprecationWarning leaking from themis or its deps would fail here.

    Doesn't substitute for the broader pytest filterwarnings in
    pytest.ini — those handle test-time noise from estimator deps.
    This test only enforces the import + symbolic-kernel path stays
    deprecation-clean (no estimation, no external libs)."""
    import json
    import warnings
    program = json.loads(
        (REPO_ROOT / "docs" / "l3_simulation"
         / "case_001_hrt_cvd.json").read_text(encoding="utf-8")
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        import themis
        out = themis.run(program)
    deprec = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert not deprec, (
        f"themis.run emitted DeprecationWarning(s): "
        f"{[(w.category.__name__, str(w.message)[:120]) for w in deprec]}"
    )
    assert "results" in out


def test_tests_py_files_have_module_docstrings():
    """Symmetric with iter 77 (themis) and iter 79 (scripts) docstring
    pins. Every .py file under tests/ must have a module docstring
    so a future contributor reading test_xxx.py knows what's being
    pressure-tested at a glance.

    Iter 80 found one missing (test_015_world_modeling_pressure.py)
    and added a docstring; this pin prevents regression.

    Skips empty __init__.py files (size < 50 bytes — sub-package
    marker files).
    """
    import ast
    violations = []
    for p in sorted((REPO_ROOT / "tests").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        if p.name == "__init__.py" and p.stat().st_size < 50:
            continue
        text = p.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if not ast.get_docstring(tree):
            violations.append(str(p.relative_to(REPO_ROOT)))
    assert not violations, (
        f"tests/ .py files missing module docstring: {violations}"
    )


def test_scripts_py_files_have_module_docstrings():
    """Symmetric with iter 77's themis docstring pin. Every .py file
    under scripts/ must have a module docstring.

    Iter 78 added the last missing docstring (run_trial_pack.py); this
    pin (iter 79) prevents regression. Scripts are typically run
    directly by users, so a no-docstring entry-point script is a real
    UX problem — running with --help / inspecting the file should give
    a quick overview.
    """
    import ast
    violations = []
    scripts_dir = REPO_ROOT / "scripts"
    if not scripts_dir.exists():
        pytest.skip("no scripts/ directory")
    for p in sorted(scripts_dir.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        if p.name == "__init__.py" and p.stat().st_size < 50:
            continue
        text = p.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if not ast.get_docstring(tree):
            violations.append(str(p.relative_to(REPO_ROOT)))
    assert not violations, (
        f"scripts/ .py files missing module docstring: {violations}"
    )


def test_themis_py_files_have_module_docstrings():
    """Every themis/**/*.py file must have a module-level docstring.

    Iter 77 preventive pin. Themis is intentionally well-documented
    at the module level (e.g. iter 36 / iter 39 fixed two stale
    docstrings; iter 71 added exception docs to __init__.py). A new
    .py file without a docstring would be a real onboarding cost for
    contributors trying to find what each module does.

    Skips empty __init__.py files (size < 50 bytes — a marker file
    not requiring narrative). Currently every non-empty file passes.
    """
    import ast
    violations = []
    for p in sorted((REPO_ROOT / "themis").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        if p.name == "__init__.py" and p.stat().st_size < 50:
            continue
        text = p.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if not ast.get_docstring(tree):
            violations.append(str(p.relative_to(REPO_ROOT)))
    assert not violations, (
        f"themis/ .py files missing module docstring: {violations}. "
        f"Add a top-level docstring describing the module's purpose."
    )


def test_all_committed_json_files_parse_cleanly():
    """Every .json file in the repo (excluding hidden / __pycache__ /
    node_modules) must be syntactically valid JSON.

    Iter 76 preventive pin. Catches typos, accidental save corruptions,
    incomplete edits where someone forgot a closing brace, etc.

    129 files currently audited. The repo has eval_set/cases JSONs,
    L3 simulation JSONs, schema files, prompt example JSONs, render
    runs, etc. — any malformed entry would break either the kernel or
    the regression test reading them, but only at point of use. This
    test catches them all upfront.
    """
    import json
    violations = []
    for p in sorted(REPO_ROOT.rglob("*.json")):
        if any(part.startswith(".") or part == "__pycache__"
               for part in p.parts):
            continue
        if "node_modules" in p.parts:
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            violations.append(f"{p.relative_to(REPO_ROOT)}: {e}")
    assert not violations, "Malformed JSON files: " + "\n".join(violations[:10])


def test_themis_init_docstring_exception_imports_resolve():
    """themis/__init__.py docstring (iter 71) lists 7 'common exceptions'
    with explicit `from themis.X.Y import Z` paths. If a future
    submodule rename / refactor breaks one of those import paths,
    users following the docstring would hit ImportError. Pin the
    paths so a rename forces an explicit doc update.

    Extracts every `from themis.… import …` line from the docstring
    and asserts each import works.
    """
    import re
    import importlib
    init_text = (REPO_ROOT / "themis" / "__init__.py").read_text(
        encoding="utf-8"
    )
    # Match exception imports inside the docstring (any `from themis…`
    # line — same regex as the smoke-test for any documented import)
    import_re = re.compile(
        r"from\s+(themis(?:\.\w+)*)\s+import\s+([\w_]+(?:\s*,\s*[\w_]+)*)"
    )
    failed = []
    for m in import_re.finditer(init_text):
        module = m.group(1)
        names = [n.strip() for n in m.group(2).split(",")]
        try:
            mod = importlib.import_module(module)
        except ImportError as e:
            failed.append(f"{module!r}: {e}")
            continue
        for name in names:
            if not hasattr(mod, name):
                failed.append(f"{module}.{name}: not found on module")
    assert not failed, (
        f"Docstring-cited imports broken: {failed}. "
        f"Update the docstring or fix the rename."
    )


def test_themis_init_all_matches_imports():
    """themis/__init__.py imports a tuple of names from .kernel and
    declares __all__. The two must agree:
    - Every imported name appears in __all__ (else `from themis import *`
      is asymmetric vs explicit imports)
    - Every __all__ entry is actually an attribute on the themis module
      (else IDE auto-import / type-checker reports a phantom)

    Iter 67 preventive pin (no current drift). Future regression: add a
    new public function, import it, but forget to add to __all__ →
    invisible to `from themis import *`.
    """
    import re
    import themis
    init_text = (REPO_ROOT / "themis" / "__init__.py").read_text(
        encoding="utf-8"
    )
    declared_all = set(themis.__all__)

    # Every __all__ name must be an attribute on the module
    missing_attrs = [n for n in declared_all if not hasattr(themis, n)]
    assert not missing_attrs, (
        f"__all__ lists names not actually on themis module: {missing_attrs}"
    )

    # Every name imported from .kernel must be in __all__
    # Handle both parens and bare-name forms; iter 82 generalizes the
    # iter 67 pin to be format-tolerant.
    m = re.search(
        r"from\s+\.kernel\s+import\s+(?:\(\s*([^)]+?)\s*\)|([^\n#]+))",
        init_text,
    )
    assert m, "themis/__init__.py must import names from .kernel"
    raw = m.group(1) or m.group(2)
    imported = {
        n.strip().rstrip(",")
        for n in raw.replace(",", " ").split()
        if n.strip().rstrip(",")
    }
    missing_from_all = imported - declared_all
    assert not missing_from_all, (
        f"Names imported from .kernel but missing from __all__: "
        f"{missing_from_all}. Public imports should appear in __all__ "
        f"so `from themis import *` matches explicit-name imports."
    )


def test_markdown_backtick_path_refs_resolve():
    """Plain-text references in markdown backticks to repo paths must
    point at existing files. Iter 66 covered `themis/*.py`; iter 84
    extends to `docs/.../*.{md,json,py}` references.

    Catches narrative prose like 'see `docs/prompts/response_rendering.md`'
    or 'inspect `themis/runtime/c_factor.py`' becoming dead links when
    files are renamed/moved without grep'ing for incoming references.

    Distinct from iter 65's link-form pin: this catches references
    that use only backtick syntax, no link wrapper.
    """
    import re
    # Match `themis/.../*.py` OR `docs/.../<file>.<ext>`
    ref_re = re.compile(
        r"`(themis/(?:[\w_]+/)*[\w_]+\.py"
        r"|docs/(?:[\w_]+/)*[\w_.\-]+\.(?:md|json|py))`"
    )
    violations = []
    for f in sorted(REPO_ROOT.rglob("*.md")):
        if any(part.startswith(".") for part in f.parts):
            continue
        text = f.read_text(encoding="utf-8")
        for m in ref_re.finditer(text):
            target = m.group(1)
            if not (REPO_ROOT / target).exists():
                line = text[:m.start()].count("\n") + 1
                violations.append(
                    f"{f.relative_to(REPO_ROOT)}:{line}: `{target}` "
                    f"-> NOT FOUND"
                )
    assert not violations, (
        f"Backtick path references not resolving: "
        f"{violations[:10]}{'...' if len(violations) > 10 else ''}"
    )


def test_markdown_cross_links_resolve():
    """Every relative .md cross-link in committed markdown must resolve
    to an existing file. Iter 63 stripped 28 abs paths to relative
    paths; if a target file was renamed/deleted, those relative links
    would now be broken — caught here.

    Iter 65 audit: all currently resolve. Pin the invariant for future
    drift (e.g., delete a charter file without grep'ing for incoming
    references).

    Skips http(s) / external links and anchor-only fragments.
    """
    import re
    link_re = re.compile(r"\[([^\]]+)\]\(([^)#]+\.md)(?:#[^)]*)?\)")
    violations = []
    for f in sorted(REPO_ROOT.rglob("*.md")):
        if any(part.startswith(".") for part in f.parts):
            continue
        text = f.read_text(encoding="utf-8")
        for m in link_re.finditer(text):
            target = m.group(2)
            if target.startswith(("http://", "https://")):
                continue
            target_path = (f.parent / target).resolve()
            if not target_path.exists():
                line = text[:m.start()].count("\n") + 1
                violations.append(
                    f"{f.relative_to(REPO_ROOT)}:{line}: "
                    f"link {target!r} -> NOT FOUND"
                )
    assert not violations, (
        f"Broken markdown cross-links: {violations[:10]}"
        f"{'...' if len(violations) > 10 else ''}"
    )


def test_no_windows_absolute_paths_in_committed_files():
    """Iter 63 audit found 28 hardcoded `C:\\Users\\12916\\...\\` paths
    across 7 .md files. Iter 64 extends this to .py files in
    themis/ / scripts/ / tests/ — code is clean today (Python uses
    Path/__file__ idioms naturally) but absolute paths could leak in
    via future copy-paste from a debugger or shell command.

    These break:
    - Anyone reading the docs on Linux / macOS
    - CI rendering of markdown
    - Anyone who clones the repo to a different path
    - Markdown link resolution from any repo browser
    - Code execution outside the original author's machine

    Pin: no committed .md or .py file (excluding hidden dirs) may
    contain 'C:\\Users\\…' or '/c/Users/…' user-specific paths.
    Test data exemption: this test file itself contains the patterns
    as regex data — accepted via path-based skip.
    """
    import re
    pattern = re.compile(r"C:[\\\\/]Users[\\\\/]12916|/c/Users/12916")
    violations = []
    for ext in ("*.md", "*.py"):
        for p in REPO_ROOT.rglob(ext):
            # Skip hidden dirs (e.g. .git, .venv) and this self-test
            if any(part.startswith(".") for part in p.parts):
                continue
            if p.resolve() == Path(__file__).resolve():
                continue
            text = p.read_text(encoding="utf-8")
            for m in pattern.finditer(text):
                line = text[:m.start()].count("\n") + 1
                violations.append(f"{p.relative_to(REPO_ROOT)}:{line}")
    assert not violations, (
        f"Files with hardcoded user-specific absolute paths: "
        f"{violations[:10]}{'...' if len(violations) > 10 else ''}. "
        f"Use relative paths or Path(__file__).parent / Path(__file__).resolve()."
    )


def test_eval_set_cases_have_internally_consistent_edges():
    """Each docs/eval_set/cases/*.json must have gold_edges whose from /
    to predicates all appear in gold_variables.

    Catches typos like 'gold_variables: [..., {predicate: smkoing}]' +
    'gold_edges: [{from: smoking, ...}]' — pytest doesn't run these
    JSON cases directly (the e2e tests build kernel_ast from gold);
    a typo would only surface at e2e test time with a confusing error.

    All 29 currently consistent (iter 61 audit).
    """
    import json
    cases_dir = REPO_ROOT / "docs" / "eval_set" / "cases"
    issues = []
    for f in sorted(cases_dir.glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        var_names = {v["predicate"] for v in case.get("gold_variables", [])}
        for e in case.get("gold_edges", []) or []:
            for endpoint in (e.get("from"), e.get("to")):
                if endpoint and endpoint not in var_names:
                    issues.append(
                        f"{f.name}: gold_edge endpoint {endpoint!r} not in "
                        f"gold_variables (got {sorted(var_names)})"
                    )
    assert not issues, "\n".join(issues)


def test_readme_subpackage_list_matches_actual():
    """README.md '主要目录' code block lists themis/<sub-package>/
    entries. Iter 60 found drift: README listed 10 sub-packages but
    actual themis/ has 11 (web/ was missing — added in this session
    via mode (a) LLM bridge + mode (b) paste-JSON commits).

    Pin: extract sub-package names from the code block, compare against
    actual directories under themis/."""
    import re
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Extract lines like '  upstream/   NL bridge helpers: ...' inside the
    # 主要目录 code block
    block_match = re.search(r"## 主要目录\s*\n+```text\n(.*?)\n```", readme,
                             re.DOTALL)
    assert block_match, "README must have '主要目录' code block"
    block = block_match.group(1)
    listed = set()
    for line in block.splitlines():
        m = re.match(r"\s+(\w+)/\s+", line)
        if m:
            listed.add(m.group(1))

    actual = {
        p.name for p in (REPO_ROOT / "themis").iterdir()
        if p.is_dir() and not p.name.startswith("_")
    }
    missing_from_readme = actual - listed
    extra_in_readme = listed - actual
    assert not missing_from_readme, (
        f"README '主要目录' missing actual sub-packages: {missing_from_readme}"
    )
    assert not extra_in_readme, (
        f"README '主要目录' lists non-existent sub-packages: {extra_in_readme}"
    )


def test_mcp_readme_counts_match_actual_server():
    """themis/mcp/README.md "Architecture" section quotes
    "current count: N tools + M resources". Iter 103 found this stale
    (said 4 tools / 8 resources but actual was 7 / 12). Iter 104 pin
    catches future regression where another tool/resource is added
    without updating the README quote.

    Symmetric with iter 59's COVERAGE_MAP MCP count pin — both files
    quote the same numbers, so they're independently checked against
    actual server output.
    """
    import asyncio
    import re
    from themis.mcp import build_server
    app = build_server()
    actual_tools = len(asyncio.run(app.list_tools()))
    actual_resources = len(list(asyncio.run(app.list_resources())))

    readme = (
        REPO_ROOT / "themis" / "mcp" / "README.md"
    ).read_text(encoding="utf-8")
    m = re.search(
        r"current count[：:]?\s*(\d+)\s+tools\s*\+\s*(\d+)\s+resources",
        readme,
        re.IGNORECASE,
    )
    assert m, (
        "themis/mcp/README.md must quote 'current count: N tools + M "
        "resources' for audit to detect drift"
    )
    quoted_tools = int(m.group(1))
    quoted_resources = int(m.group(2))
    assert quoted_tools == actual_tools, (
        f"MCP README says {quoted_tools} tools but server has "
        f"{actual_tools}. Update themis/mcp/README.md."
    )
    assert quoted_resources == actual_resources, (
        f"MCP README says {quoted_resources} resources but server has "
        f"{actual_resources}. Update themis/mcp/README.md."
    )


def test_mcp_readme_catalog_tables_match_server():
    """themis/mcp/README.md has two markdown tables — "Tool catalog" and
    "Resource catalog" — that list each tool name / resource URI as table
    rows. Iter 105 found these drifted independently of the count quote
    fixed by iter 103/104: the prose said "7 tools + 12 resources" but
    the tables still showed only 5 tools and 8 resources from before
    Phase 8.1 (themis_discover) / Phase 10 (themis_verify_data_gap_report)
    / Phase 11.1-11.2 (gap_to_action / kb_lookup / kb_query / kb_result)
    landed.

    Count pins catch "the number is wrong"; this catches "the list is
    wrong" — same drift root cause (new tool/resource added, README
    catalog not updated), different surface.
    """
    import asyncio
    import re
    from themis.mcp import build_server

    app = build_server()
    actual_tool_names = {t.name for t in asyncio.run(app.list_tools())}
    actual_resource_uris = {
        str(r.uri) for r in asyncio.run(app.list_resources())
    }

    readme = (
        REPO_ROOT / "themis" / "mcp" / "README.md"
    ).read_text(encoding="utf-8")

    # Tool catalog: rows look like "| `themis_X` | ... | ... |"
    tool_section = re.search(
        r"##\s*Tool catalog\s*\n(.*?)(?=\n##\s|\Z)",
        readme,
        re.DOTALL,
    )
    assert tool_section, "themis/mcp/README.md must have ## Tool catalog"
    listed_tools = set(re.findall(
        r"^\|\s*`(themis_\w+)`\s*\|", tool_section.group(1), re.MULTILINE
    ))
    assert listed_tools == actual_tool_names, (
        "themis/mcp/README.md Tool catalog drifted from server. "
        f"Missing from README: {sorted(actual_tool_names - listed_tools)}; "
        f"extra in README: {sorted(listed_tools - actual_tool_names)}"
    )

    # Resource catalog: rows look like "| `themis://...` | ... |"
    resource_section = re.search(
        r"##\s*Resource catalog\s*\n(.*?)(?=\n##\s|\Z)",
        readme,
        re.DOTALL,
    )
    assert resource_section, (
        "themis/mcp/README.md must have ## Resource catalog"
    )
    listed_resources = set(re.findall(
        r"^\|\s*`(themis://[^`]+)`\s*\|",
        resource_section.group(1),
        re.MULTILINE,
    ))
    assert listed_resources == actual_resource_uris, (
        "themis/mcp/README.md Resource catalog drifted from server. "
        f"Missing from README: "
        f"{sorted(actual_resource_uris - listed_resources)}; "
        f"extra in README: "
        f"{sorted(listed_resources - actual_resource_uris)}"
    )


def test_readme_query_kind_list_matches_enum():
    """README.md "当前能力" section claims "运行结构查询: cause / assoc /
    identify / effect / probability / counterfactual". Iter 106 caught
    that this list was stuck at 5 kinds — counterfactual landed via
    Phase 5 §C and `QueryKind.COUNTERFACTUAL` is a canonical
    dispatched kind, but the README never grew to mention it.

    Pre-Phase-5 historical lists in CORE_STATUS.md (v1.0 frozen surface,
    Phase 5 §T scope) intentionally retain the older 5-kind list and
    are NOT pinned by this test — README's "当前能力" section is the
    one that promises the present-tense capability.
    """
    import re

    from themis.types import QueryKind

    actual_kinds = {k.value for k in QueryKind}

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(
        r"运行结构查询[：:]\s*`([^`]+)`",
        readme,
    )
    assert m, (
        "README.md '当前能力' must quote 运行结构查询 list inline "
        "for audit to detect drift"
    )
    listed = {tok.strip() for tok in m.group(1).split("/")}
    assert listed == actual_kinds, (
        f"README query-kind list drifted from QueryKind enum. "
        f"Missing from README: {sorted(actual_kinds - listed)}; "
        f"extra in README: {sorted(listed - actual_kinds)}"
    )


def test_coverage_map_gap_kind_count_matches_enum():
    """COVERAGE_MAP.md 元基础设施 row quotes 'DataGapReport schema
    (N gap_kind / M severity / K ref_kind, ...)'. Iter 107 caught
    that this claimed N=8 (initial Phase 10 scope) while GapKind
    enum had grown to 22 via Phase 13 + iter 5/19 + later additions.

    Pin parses the row and asserts N == len(GapKind), M == len(GapSeverity),
    K == len(ref_kind enum from query_result.schema.json).

    CORE_STATUS.md / PHASE_10_DATA_GAP_REPORT_CHARTER.md retain '8'
    intentionally — those describe S.10.1 historical scope, not
    current state — so they're NOT pinned by this test.
    """
    import json
    import re

    from themis.types import GapKind
    from themis.output.data_gap_report import GapSeverity

    actual_gap_kinds = len(list(GapKind))
    actual_severities = len(list(GapSeverity))

    schema = json.loads(
        (REPO_ROOT / "themis" / "schemas" / "query_result.schema.json").read_text(encoding="utf-8")
    )

    def _find_ref_kind_enum(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "ref_kind" and isinstance(v, dict) and "enum" in v:
                    return v["enum"]
                hit = _find_ref_kind_enum(v)
                if hit is not None:
                    return hit
        elif isinstance(node, list):
            for item in node:
                hit = _find_ref_kind_enum(item)
                if hit is not None:
                    return hit
        return None

    ref_kind_enum = _find_ref_kind_enum(schema)
    assert ref_kind_enum is not None, (
        "query_result.schema.json must define a ref_kind enum"
    )
    actual_ref_kinds = len(ref_kind_enum)

    coverage = (
        REPO_ROOT / "COVERAGE_MAP.md"
    ).read_text(encoding="utf-8")
    m = re.search(
        r"DataGapReport schema\s*\(\s*(\d+)\s+gap_kind\s*/\s*(\d+)\s+severity\s*/\s*(\d+)\s+ref_kind",
        coverage,
    )
    assert m, (
        "COVERAGE_MAP.md must quote 'DataGapReport schema (N gap_kind / "
        "M severity / K ref_kind, ...)' for audit to detect drift"
    )
    quoted_kinds = int(m.group(1))
    quoted_severities = int(m.group(2))
    quoted_ref_kinds = int(m.group(3))
    assert quoted_kinds == actual_gap_kinds, (
        f"COVERAGE_MAP says {quoted_kinds} gap_kind but GapKind enum "
        f"has {actual_gap_kinds}. Update COVERAGE_MAP.md."
    )
    assert quoted_severities == actual_severities, (
        f"COVERAGE_MAP says {quoted_severities} severity but GapSeverity "
        f"enum has {actual_severities}. Update COVERAGE_MAP.md."
    )
    assert quoted_ref_kinds == actual_ref_kinds, (
        f"COVERAGE_MAP says {quoted_ref_kinds} ref_kind but schema enum "
        f"has {actual_ref_kinds}. Update COVERAGE_MAP.md."
    )


def test_kb_readme_gap_to_query_kind_table_matches_translator():
    """themis/kb/README.md has a "Mapping gaps to query kinds" table that
    documents which gap_kinds the translator can route to a KB. Iter 108
    found this table missing missing_population_distribution and
    transport_source_conditional_unknown rows that were already in
    `_GAP_TO_QUERY_KIND` in translator.py.

    Pin extracts gap_kind names from the README table and compares to
    the actual translator dict + the MISSING_DISTRIBUTION special case.
    """
    import re

    from themis.kb.translator import _GAP_TO_QUERY_KIND
    from themis.types import GapKind

    actual_mapped_kinds = set(_GAP_TO_QUERY_KIND.keys())
    actual_mapped_kinds.add(GapKind.MISSING_DISTRIBUTION)
    actual_mapped_names = {k.value for k in actual_mapped_kinds}

    readme = (
        REPO_ROOT / "themis" / "kb" / "README.md"
    ).read_text(encoding="utf-8")
    section = re.search(
        r"##\s*Mapping gaps to query kinds\s*\n(.*?)(?=\n##\s|\Z)",
        readme,
        re.DOTALL,
    )
    assert section, (
        "themis/kb/README.md must have ## Mapping gaps to query kinds"
    )
    listed = set(re.findall(
        r"^\|\s*`([a-z_]+)`",
        section.group(1),
        re.MULTILINE,
    ))

    assert listed == actual_mapped_names, (
        "themis/kb/README.md gap mapping table drifted from "
        "_GAP_TO_QUERY_KIND. Missing from README: "
        f"{sorted(actual_mapped_names - listed)}; extra in README: "
        f"{sorted(listed - actual_mapped_names)}"
    )


def test_estimation_init_docstring_inventories_all_exports():
    """themis/estimation/__init__.py docstring should reference every
    name in __all__. Iter 111 caught the docstring describing only
    "Phase 7.1 scope" (data contract + backdoor) while __all__ also
    exported Phase 8.1 discovery, Phase 8.2 sensitivity, and Phase 14
    dose-response APIs.

    Pin asserts every __all__ name (or its base form for *Result
    dataclasses paired with verb functions) appears in the docstring,
    so adding a new estimator forces a docstring update.
    """
    from themis import estimation

    docstring = estimation.__doc__ or ""
    missing = []
    for name in estimation.__all__:
        if name not in docstring:
            missing.append(name)
    assert not missing, (
        f"themis/estimation/__init__.py docstring missing names from "
        f"__all__: {missing}. Update the docstring to inventory new "
        "exports."
    )


def test_data_gap_report_docstring_must_disclose_section_accurate():
    """themis/output/data_gap_report.py module docstring inventories
    gap_kinds by category. Iter 118 caught the "Phase 11+ structural
    caveats (must-disclose channel)" section listing
    transport_source_conditional_unknown and dose_response_data_required
    while neither is actually in scheduler._MUST_DISCLOSE_GAP_KINDS —
    they're data needs that surface only via data_gap_report.

    Pin asserts every gap_kind named under the "must-disclose channel"
    paragraph is actually in scheduler._MUST_DISCLOSE_GAP_KINDS, and
    every must-disclose value appears somewhere in the docstring.
    """
    import re

    from themis.runtime.scheduler import _MUST_DISCLOSE_GAP_KINDS
    from themis.output import data_gap_report as dgr_mod

    docstring = dgr_mod.__doc__ or ""

    # Extract the "must-disclose channel" paragraph: header sentence
    # mentioning must-disclose channel + 0..N prose continuation lines
    # ending with the colon, followed by a contiguous run of bullets.
    section = re.search(
        r"must-disclose channel[^\n]*"
        r"(?:\n(?!- )[^\n]*)*"  # prose continuation lines (no bullet)
        r"\n((?:- [^\n]+\n(?:  [^\n]+\n)*)+)",  # bullet block
        docstring,
    )
    assert section, (
        "data_gap_report module docstring must have a "
        "'must-disclose channel' section enumerated as bullet list"
    )
    paragraph = section.group(1)
    listed = set(re.findall(r"^- (\w+)", paragraph, re.MULTILINE))

    # Every name listed in the must-disclose paragraph must actually
    # be in the scheduler's whitelist.
    not_actually_must_disclose = listed - _MUST_DISCLOSE_GAP_KINDS
    assert not not_actually_must_disclose, (
        f"data_gap_report docstring's 'must-disclose channel' section "
        f"lists gap_kinds that are NOT in scheduler._MUST_DISCLOSE_GAP_KINDS: "
        f"{sorted(not_actually_must_disclose)}. Move them to a "
        "different section."
    )

    # Every must-disclose value must appear somewhere in the full
    # docstring (in any section). The L3 section covers the iter 5/19
    # additions; this is just total-coverage hygiene.
    not_documented = _MUST_DISCLOSE_GAP_KINDS - {
        line for line in re.findall(r"\b([a-z_]+)\b", docstring)
    }
    assert not not_documented, (
        f"_MUST_DISCLOSE_GAP_KINDS values missing from "
        f"data_gap_report docstring: {sorted(not_documented)}"
    )


def test_eval_set_readme_gold_query_kind_matches_enum():
    """docs/eval_set/README.md "Per-case JSON schema" example shows
    a `gold_query_kind` value pipe-list. Iter 117 caught this listed
    only 5 kinds (cause | assoc | effect | identify | probability)
    while QueryKind enum has 6 — counterfactual landed via Phase 5
    §C but the eval_set README never grew. Same drift class as
    iter 106 (root README query-kind list) in a different doc.
    """
    import re

    from themis.types import QueryKind

    actual_kinds = {k.value for k in QueryKind}

    readme = (
        REPO_ROOT / "docs" / "eval_set" / "README.md"
    ).read_text(encoding="utf-8")
    m = re.search(
        r'"gold_query_kind"\s*:\s*"([^"]+)"',
        readme,
    )
    assert m, (
        "docs/eval_set/README.md must show 'gold_query_kind: \"...\"' "
        "in its Per-case JSON schema example for audit to detect drift"
    )
    listed = {tok.strip() for tok in m.group(1).split("|")}
    assert listed == actual_kinds, (
        f"docs/eval_set/README.md gold_query_kind list drifted from "
        f"QueryKind enum. Missing from README: "
        f"{sorted(actual_kinds - listed)}; extra in README: "
        f"{sorted(listed - actual_kinds)}"
    )


def test_formula_ast_spec_node_count_matches_types():
    """formula_ast_spec_v0_1.md version-pointer header quotes a count
    of formula AST node types. Iter 116 caught it claiming "5 core
    nodes" (Sum / Product / ProbabilityRef / BindDecl / VarRef) while
    ConstantExpr had always been a 6th node since v0.1.

    Pin asserts the spelled-out Chinese number in the header
    (五/六/七/八) equals the count of formula AST node dataclasses
    actually present in themis/types.py: ConstantExpr / SumExpr /
    ProductExpr / ProbabilityRefExpr / BindDecl / VarRef.
    """
    import re

    header = (REPO_ROOT / "formula_ast_spec_v0_1.md").read_text(
        encoding="utf-8"
    )

    # Find the quoted Chinese count.
    chinese_to_int = {
        "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    m = re.search(r"共\s*\*?\*?\s*([三四五六七八九])\s*个\s*AST\s*节点", header)
    assert m, (
        "formula_ast_spec_v0_1.md must quote a count of AST node types "
        "in the header in '共 N 个 AST 节点' form for audit to detect drift"
    )
    claimed = chinese_to_int[m.group(1)]

    # Count actual formula AST node dataclasses in types.py.
    expected_names = {
        "ConstantExpr",
        "SumExpr",
        "ProductExpr",
        "ProbabilityRefExpr",
        "BindDecl",
        "VarRef",
    }
    types_text = (REPO_ROOT / "themis" / "types.py").read_text(
        encoding="utf-8"
    )
    found = {n for n in expected_names if f"class {n}" in types_text}
    actual = len(found)

    assert claimed == actual, (
        f"formula_ast_spec_v0_1.md header claims {claimed} AST node "
        f"types but themis/types.py defines {actual} of the expected "
        f"set: {sorted(found)}. Update the header or the type set."
    )


def test_kernel_docstring_lists_all_public_entries():
    """themis/kernel.py module docstring should mention every public
    entry function it defines (the ones re-exported via themis.__all__).
    Iter 115 caught the docstring naming only ``run`` /
    ``apply_patch_and_run`` / ``verify`` while ``estimate`` (Phase 7)
    and ``verify_data_gap_report`` (Phase 10) had landed without
    docstring updates.

    Pin asserts every callable name in themis/__init__.py's __all__
    that comes from .kernel appears in kernel.py's module docstring.
    Excludes AdmgVerificationPending — it's an exception class, not
    an entry function, and the docstring is structured around
    pipeline behavior rather than exception inventory.
    """
    from themis import kernel as kernel_mod

    docstring = kernel_mod.__doc__ or ""
    # The 5 callables exposed via themis.run / etc.
    expected = {
        "run",
        "apply_patch_and_run",
        "estimate",
        "verify",
        "verify_data_gap_report",
    }
    missing = sorted(name for name in expected if name not in docstring)
    assert not missing, (
        f"themis/kernel.py module docstring missing public entries: "
        f"{missing}. Update the docstring."
    )


def test_prompt_header_word_counts_match_subsection_counts():
    """Iter 114 — drift class: prompt section header claims a count
    in spelled-out form (e.g. "## Three questions per gap") but the
    actual ### subsection count under it diverges. gap_to_action.md
    said "Three" while having Q0 + Q1 + Q2 + Q3 = 4 subsections after
    Q0 pre-screen was added later.

    Scans every "## <number-word> <noun>" header in docs/prompts/
    and asserts the immediate ### subsection count (until the next ##
    or EOF) equals the spelled-out number. Headers without a leading
    number-word are ignored.
    """
    import re

    word_to_int = {
        "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    }

    issues = []
    for prompt_path in (REPO_ROOT / "themis" / "prompts").glob("*.md"):
        text = prompt_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(
                r"^##\s+(?:The\s+)?(one|two|three|four|five|six|seven|eight|nine)\b",
                line,
                re.IGNORECASE,
            )
            if not m:
                continue
            claimed = word_to_int[m.group(1).lower()]
            # Count ### subsections until the next ## (non-###) or EOF.
            sub_count = 0
            for j in range(i + 1, len(lines)):
                nl = lines[j]
                if re.match(r"^##\s+", nl) and not re.match(r"^###", nl):
                    break
                if re.match(r"^###\s+", nl):
                    sub_count += 1
            # Only assert when subsections exist; some headers describe
            # things other than enumerated subsections.
            if sub_count and sub_count != claimed:
                issues.append(
                    f"{prompt_path.name}: '{line.strip()}' claims "
                    f"{claimed} but has {sub_count} ### subsections"
                )

    assert not issues, (
        "Prompt header counts drifted from subsection counts:\n"
        + "\n".join(f"  - {issue}" for issue in issues)
    )


def test_workflow_init_docstring_lists_all_submodules():
    """themis/workflow/__init__.py docstring explicitly enumerates its
    submodules (the "Modules:" bullet list). Iter 113 caught it
    listing only ``parameter_fill`` while ``variable_framing`` had
    been there for several phases.

    Pin asserts every public .py module in themis/workflow/ (excluding
    __init__.py and any _private.py) is referenced by basename in the
    __init__.py docstring. If a new workflow module lands, the docstring
    must grow to mention it.
    """
    pkg_dir = REPO_ROOT / "themis" / "workflow"
    init_text = (pkg_dir / "__init__.py").read_text(encoding="utf-8")

    submodules = []
    for p in pkg_dir.glob("*.py"):
        if p.name == "__init__.py" or p.name.startswith("_"):
            continue
        submodules.append(p.stem)

    missing = [m for m in submodules if m not in init_text]
    assert not missing, (
        f"themis/workflow/__init__.py docstring missing module names: "
        f"{missing}. Update the 'Modules:' list."
    )


@pytest.mark.parametrize("pkg_name", ["kb", "upstream", "verifier", "mcp"])
def test_subpackage_init_docstrings_inventory_all_exports(pkg_name):
    """Iter 112 — same pin as iter 111's estimation pin, applied to the
    other subpackages with __all__: kb (19 exports) / upstream (16) /
    verifier (17) / mcp (2). Each had docstring drift where most
    exports were not named — mcp's also said "four public entry
    points" while the actual count was seven.

    Pinning each forces future additions to either appear in the
    docstring or be left out of __all__ deliberately. Skips packages
    where __init__.py has no __all__ (web / runtime / output / workflow
    / oracle / input — these don't claim a curated re-export surface).
    """
    import importlib

    pkg = importlib.import_module(f"themis.{pkg_name}")
    assert hasattr(pkg, "__all__"), (
        f"themis.{pkg_name} no longer has __all__; remove from this "
        "parametrize list or restore __all__"
    )
    docstring = pkg.__doc__ or ""
    missing = [name for name in pkg.__all__ if name not in docstring]
    assert not missing, (
        f"themis/{pkg_name}/__init__.py docstring missing names from "
        f"__all__: {missing}. Update the docstring."
    )


def test_every_gap_kind_documented_in_reference():
    """Iter 139 — docs/GAP_KINDS_REFERENCE.md is the single-source
    human-readable table for the 26 gap_kinds. Previously this
    information was scattered across types.py docstrings, the
    classifier descriptions in data_gap_report.py, gap_to_action.md
    Q0 list, and response_rendering.md mirrored-set table. Pin
    asserts every GapKind enum value appears verbatim as a table
    row in the reference doc.
    """
    from themis.types import GapKind

    reference = (
        REPO_ROOT / "docs" / "GAP_KINDS_REFERENCE.md"
    ).read_text(encoding="utf-8")

    missing = sorted(
        k.value for k in GapKind
        if f"`{k.value}`" not in reference
    )
    assert not missing, (
        f"docs/GAP_KINDS_REFERENCE.md missing GapKind values: "
        f"{missing}. Add a row to the table."
    )


def test_must_disclose_gap_kinds_documented_in_gap_to_action():
    """Iter 136 — parallel to iter 132's response_rendering pin but
    for gap_to_action.md: every must-disclose gap_kind PLUS the iter
    120/121/123 estimator-runtime gap_kinds (which auto-mirror to
    explanation but live outside _MUST_DISCLOSE_GAP_KINDS) must
    appear verbatim in gap_to_action.md so the orchestrator agent
    has explicit Q0-pre-screen guidance for each.

    iter 119-134 added 4 new gap_kinds (collider, weak_iv,
    propensity_overlap, outcome_separation) that drifted out of
    gap_to_action for ~16 iters until this pin caught it.
    """
    from themis.runtime.scheduler import _MUST_DISCLOSE_GAP_KINDS

    estimator_runtime_kinds = {
        "weak_iv_instrument",            # iter 120
        "propensity_overlap_violation",  # iter 121
        "outcome_model_quasi_separation",  # iter 123
    }
    expected = set(_MUST_DISCLOSE_GAP_KINDS) | estimator_runtime_kinds

    prompt = (
        REPO_ROOT / "themis" / "prompts" / "gap_to_action.md"
    ).read_text(encoding="utf-8")

    missing = sorted(k for k in expected if k not in prompt)
    assert not missing, (
        f"gap_to_action.md missing gap_kinds: {missing}. "
        "Every must-disclose + estimator-runtime gap_kind needs Q0 "
        "pre-screen guidance — agents using this prompt have no "
        "fallback rules for unmentioned kinds."
    )


def test_numeric_estimate_method_enum_documented_in_prompt():
    """Iter 132 — parallel to iter 110's BoundsMethod producer pin
    but for numeric_estimate.method values. Every method enum value
    in query_result.schema.json must appear verbatim somewhere in
    docs/prompts/response_rendering.md so the LLM consumer has
    rendering guidance for that method.

    Iter 124 extended sensitivity to continuous outcome and iter 128
    added transport_post_stratification — both went 4 iterations
    without prompt-side rendering guidance until iter 132 caught it.
    This pin locks the "method ↔ prompt section" invariant going
    forward.
    """
    import json

    schema = json.loads(
        (REPO_ROOT / "themis" / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8"
        )
    )

    # Find the method enum within numeric_estimate's properties.
    def _find_method_enum(node, depth=0):
        """Walk schema looking for any 'method' property whose value
        matches the numeric-estimate-style enum (contains
        backdoor_linear / backdoor_logistic — distinguishes from
        bounds.method which lists manski_natural etc.)."""
        if isinstance(node, dict):
            if (
                node.get("type") == "object"
                and isinstance(node.get("properties"), dict)
            ):
                method_def = node["properties"].get("method")
                if (
                    isinstance(method_def, dict)
                    and isinstance(method_def.get("enum"), list)
                    and "backdoor_linear" in method_def["enum"]
                ):
                    return method_def["enum"]
            for v in node.values():
                hit = _find_method_enum(v, depth + 1)
                if hit is not None:
                    return hit
        elif isinstance(node, list):
            for item in node:
                hit = _find_method_enum(item, depth + 1)
                if hit is not None:
                    return hit
        return None

    method_enum = _find_method_enum(schema)
    assert method_enum is not None, (
        "Could not locate numeric_estimate.method enum in "
        "query_result.schema.json"
    )

    prompt = (
        REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
    ).read_text(encoding="utf-8")

    missing = [m for m in method_enum if m not in prompt]
    assert not missing, (
        f"numeric_estimate.method enum values not documented in "
        f"response_rendering.md: {missing}. Add a section / mention "
        "for each."
    )


def test_bounds_method_producers_have_rendering_template():
    r"""Every BoundsMethod value actually produced by themis/output/
    bounds.py must have a matching ``#### `method_name``` section in
    docs/prompts/response_rendering.md. Iter 110 added this
    preventatively — current state is in sync (manski_natural +
    balke_pearl_iv produced + rendered; frontdoor_partial +
    manski_tamer_monotonicity declared in enum but not yet produced
    so prompt correctly omits them). Pin catches future drift where a
    new bounds solver lands without a rendering template.

    The check uses 'producer' set (what bounds.py emits) rather than
    'enum' set (what BoundsMethod declares) because aspirational enum
    values shouldn't force premature prompt expansion.
    """
    import re

    bounds_src = (
        REPO_ROOT / "themis" / "output" / "bounds.py"
    ).read_text(encoding="utf-8")
    produced = set(re.findall(
        r"method=BoundsMethod\.([A-Z_]+)", bounds_src
    ))
    assert produced, (
        "Could not find any BoundsMethod producers in "
        "themis/output/bounds.py — pin assumption violated"
    )

    # Map enum NAMES (e.g. MANSKI_NATURAL) to their .value strings.
    from themis.types import BoundsMethod
    name_to_value = {bm.name: bm.value for bm in BoundsMethod}
    produced_values = {name_to_value[n] for n in produced}

    prompt = (
        REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
    ).read_text(encoding="utf-8")

    # "#### `<method_value>`" anchored at line start.
    rendered = set(re.findall(
        r"^####\s+`([a-z_]+)`", prompt, re.MULTILINE
    ))

    missing = produced_values - rendered
    assert not missing, (
        f"BoundsMethod values produced by bounds.py have no rendering "
        f"template in response_rendering.md: {sorted(missing)}. "
        "Add a '#### `<value>`' section with the per-method shape."
    )


def test_kb_readme_confidence_grade_ladder_matches_enum():
    """themis/kb/README.md prose describes KBConfidenceGrade as a
    GRADE-style ladder. Iter 109 caught it saying "five-level" while
    listing 6 entries (5 graded + unknown sentinel). Pin asserts every
    enum value appears in the prose ladder, and that the digit-word
    matches the enum count.
    """
    import re

    from themis.kb.schemas import KBConfidenceGrade

    actual_values = {v.value for v in KBConfidenceGrade}
    actual_count = len(actual_values)

    readme = (
        REPO_ROOT / "themis" / "kb" / "README.md"
    ).read_text(encoding="utf-8")

    # The "Confidence grading" section describes the ladder. Limit search
    # to that section so unrelated mentions don't confuse the pin.
    section = re.search(
        r"##\s*Confidence grading\s*\n(.*?)(?=\n##\s|\Z)",
        readme,
        re.DOTALL,
    )
    assert section, (
        "themis/kb/README.md must have ## Confidence grading"
    )
    body = section.group(1)

    # Each value must be named verbatim somewhere in the section.
    missing = sorted(v for v in actual_values if v not in body)
    assert not missing, (
        "themis/kb/README.md Confidence grading section missing "
        f"enum values: {missing}"
    )

    # The "N-level" claim must match enum count - 1 (graded levels;
    # unknown is the sentinel) OR equal enum count if the prose includes
    # unknown explicitly.
    word_to_int = {
        "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8,
    }
    m = re.search(
        r"(two|three|four|five|six|seven|eight)-level",
        body,
        re.IGNORECASE,
    )
    if m:
        claimed = word_to_int[m.group(1).lower()]
        assert claimed in (actual_count, actual_count - 1), (
            f"KB README claims '{m.group(0)}' but KBConfidenceGrade "
            f"has {actual_count} values "
            f"({actual_count - 1} graded + 1 unknown sentinel). "
            "Update the prose."
        )


def test_mcp_server_docstring_lists_all_tools_and_resources():
    """themis/mcp/server.py module docstring has parallel inventories
    to themis/mcp/README.md catalog tables — same drift class. Iter 105
    found server.py docstring listed 6 tools (missing themis_discover)
    and 9 resources (missing kb_lookup.md / kb_query.schema.json /
    kb_result.schema.json) while the README count quote already said
    "7 tools + 12 resources" post-iter-103.
    """
    import asyncio
    import re

    from themis.mcp import build_server, server as server_mod

    app = build_server()
    actual_tool_names = {t.name for t in asyncio.run(app.list_tools())}
    actual_resource_uris = {
        str(r.uri) for r in asyncio.run(app.list_resources())
    }

    docstring = server_mod.__doc__ or ""
    listed_tools = set(re.findall(r"``(themis_\w+)\(", docstring))
    listed_resources = set(re.findall(
        r"``(themis://[^`]+)``", docstring
    ))

    assert listed_tools == actual_tool_names, (
        "themis/mcp/server.py docstring tool inventory drifted. "
        f"Missing from docstring: {sorted(actual_tool_names - listed_tools)}; "
        f"extra in docstring: {sorted(listed_tools - actual_tool_names)}"
    )
    assert listed_resources == actual_resource_uris, (
        "themis/mcp/server.py docstring resource inventory drifted. "
        "Missing from docstring: "
        f"{sorted(actual_resource_uris - listed_resources)}; "
        "extra in docstring: "
        f"{sorted(listed_resources - actual_resource_uris)}"
    )


def test_coverage_map_mcp_counts_match_actual_server():
    """COVERAGE_MAP.md quotes 'N tools + M resources' for the MCP server.
    Iter 59 found drift: said '6 tools' while actual is 7
    (themis_apply_patch_and_run / discover / estimate / list_resources /
    run / verify / verify_data_gap_report). Pin actual server output."""
    import asyncio
    import re
    from themis.mcp import build_server
    app = build_server()
    actual_tools = len(asyncio.run(app.list_tools()))
    actual_resources = len(list(asyncio.run(app.list_resources())))

    cov = (REPO_ROOT / "COVERAGE_MAP.md").read_text(encoding="utf-8")
    # Handle both ASCII () and full-width （）parentheses around the count
    m = re.search(
        r"MCP server[^|]*[\(（](\d+)\s+tools\s*\+\s*(\d+)\s+resources",
        cov,
    )
    assert m, "COVERAGE_MAP.md must quote 'MCP server ...(N tools + M resources...'"
    quoted_tools = int(m.group(1))
    quoted_resources = int(m.group(2))
    assert quoted_tools == actual_tools, (
        f"COVERAGE_MAP says {quoted_tools} MCP tools but server has "
        f"{actual_tools}. Update the table row in COVERAGE_MAP.md."
    )
    assert quoted_resources == actual_resources, (
        f"COVERAGE_MAP says {quoted_resources} MCP resources but server has "
        f"{actual_resources}. Update the table row in COVERAGE_MAP.md."
    )


def test_eval_set_readme_counts_match_actual_files():
    """docs/eval_set/README.md header quotes 'N cases across M failure
    modes (F1-FM)'. Iter 57 audit found this stale: header said
    '28 cases / 24 failure modes' while actual was 29 cases + 26 codes.

    Pin both counts:
    - 'N cases' must match docs/eval_set/cases/*.json count
    - 'M failure modes (F1-FM)' must match the F-code count in
      failure_modes.md

    Same drift class as iter 56 failure_modes header pin.
    """
    import re
    eval_readme = (
        REPO_ROOT / "docs" / "eval_set" / "README.md"
    ).read_text(encoding="utf-8")

    # Count actual case JSON files
    case_files = list((REPO_ROOT / "docs" / "eval_set" / "cases").glob("*.json"))
    actual_cases = len(case_files)

    # Header quote: 'N cases'
    cases_match = re.search(r"\*\*(\d+)\s+cases\s+across\s+(\d+)\s+failure\s+modes",
                            eval_readme)
    assert cases_match, (
        "docs/eval_set/README.md header must quote '**N cases across "
        "M failure modes**'"
    )
    header_cases = int(cases_match.group(1))
    header_modes = int(cases_match.group(2))

    assert header_cases == actual_cases, (
        f"eval_set README header says {header_cases} cases but "
        f"docs/eval_set/cases/ has {actual_cases} JSON files. "
        f"Update the 'N cases' quote in the header."
    )

    # Failure mode count via failure_modes.md
    fm = (REPO_ROOT / "docs" / "eval_set" / "failure_modes.md").read_text(
        encoding="utf-8"
    )
    actual_modes = len(re.findall(r"^##\s+F\d+", fm, re.MULTILINE))
    assert header_modes == actual_modes, (
        f"eval_set README header says {header_modes} failure modes but "
        f"failure_modes.md has {actual_modes} F-codes. "
        f"Update the 'M failure modes' quote in the header."
    )


def test_every_phase_charter_declares_status():
    """Every PHASE_*_CHARTER.md must declare a status line (> 状态：…).

    Iter 52-54 audit revealed 6 charters with stale status lines that
    had drifted from CORE_STATUS truth — but the deeper invariant is
    that EVERY charter MUST have a parseable status line, otherwise
    audit can't even spot drift. Catches:

    - New charter created without status line at all
    - Status line accidentally deleted in a refactor
    - Status moved to a non-blockquote line and missed by audit pattern
    """
    import re
    status_re = re.compile(r"^>\s*状态[：:]", re.MULTILINE)
    charters = list(REPO_ROOT.glob("PHASE_*_CHARTER.md"))
    assert len(charters) >= 5, (
        f"Expected ≥5 PHASE_*_CHARTER.md files, found {len(charters)}"
    )
    missing = []
    for p in charters:
        text = p.read_text(encoding="utf-8")
        if not status_re.search(text):
            missing.append(p.name)
    assert not missing, (
        f"Charters without parseable '> 状态：' line: {missing}. "
        f"Add a status line in the charter header blockquote so audit "
        f"can detect drift against CORE_STATUS."
    )


def test_no_orphan_test_files():
    """Every tests/test_*.py file must contain at least one test
    function (def test_… or async def test_…). Pytest silently skips
    files with zero test funcs — a typo'd helper-only file named
    test_foo.py would never run, leaving the contract un-checked.

    This guard catches the typical 'I renamed a test func and broke
    the prefix' regression.
    """
    import re
    test_func_re = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.MULTILINE)
    orphans = []
    for p in TESTS_DIR.rglob("test_*.py"):
        if test_func_re.search(p.read_text(encoding="utf-8")):
            continue
        orphans.append(p.relative_to(REPO_ROOT))
    assert not orphans, (
        f"test_*.py files without any test function: {orphans}. "
        f"Pytest silently skips these — rename to non-test_ prefix or "
        f"add at least one test_xxx() function."
    )
