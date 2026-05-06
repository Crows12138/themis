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
