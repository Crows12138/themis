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
