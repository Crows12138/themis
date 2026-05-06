"""Meta-test: every GapKind enum value has at least one test that
asserts it can fire.

When a new gap_kind is added (like iter 5's unmeasured_confounder_risk
or iter 19's unattempted_layer_due_to_dispatch_conflict), it's easy
to forget the corresponding test. This meta-test scans the test
directory for assertions that mention each gap_kind and fails fast
when one is unattended.

Detection is text-based (grep for the kind value in test files). False
positives are possible (a kind merely mentioned in a test doc string
counts), but it's a coarse safety net that catches the typical 'I
added the enum but forgot to write a test' regression.
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
        (REPO_ROOT / "query_result.schema.json").read_text(encoding="utf-8")
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
        REPO_ROOT / "docs" / "prompts" / "response_rendering.md"
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
    m = re.search(r"from\s+\.kernel\s+import\s+\(([^)]+)\)", init_text)
    assert m, "themis/__init__.py must import from .kernel via parens form"
    imported = {
        n.strip().rstrip(",")
        for n in m.group(1).split()
        if n.strip().rstrip(",")
    }
    missing_from_all = imported - declared_all
    assert not missing_from_all, (
        f"Names imported from .kernel but missing from __all__: "
        f"{missing_from_all}. Public imports should appear in __all__ "
        f"so `from themis import *` matches explicit-name imports."
    )


def test_markdown_backtick_py_refs_resolve():
    """Plain-text references like `themis/runtime/c_factor.py` in
    markdown backticks must point at existing files. Iter 66
    preventive pin (no current drift). Catches future regressions
    where a .py is renamed/moved without grep'ing for incoming
    references in narrative prose.

    Distinct from iter 65's link-form pin: this catches references
    in prose like 'see `themis/runtime/c_factor.py` for details',
    which doesn't use markdown link syntax but is just as fragile.
    """
    import re
    ref_re = re.compile(r"`(themis/(?:[\w_]+/)*[\w_]+\.py)`")
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
        f"Backtick `themis/*.py` references not resolving: "
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
