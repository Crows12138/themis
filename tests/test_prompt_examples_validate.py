"""Meta-test: docs/prompts/examples/*.json kernel_ast examples must
parse and run without raising.

The A1 prompt (nl_to_kernel_ast.md) cites these as worked NL→kernel_ast
pairs. If kernel schema drifts (new required field, renamed key) and
the examples aren't updated, the prompt's worked examples become
silently invalid — a future LLM following them would emit broken AST.

This test loads every example with a `kernel_ast` key and asserts
themis.run accepts it. Only catches structural validity (parse + run
clean), not semantic correctness — that's what the example .md files
already cover when read by humans.

Examples without `kernel_ast` (narrative / edges / reply bundles) are
covered by their own dedicated tests in test_upstream/ and
test_workflow/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from themis import run


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "docs" / "prompts" / "examples"


def _kernel_ast_examples() -> list[Path]:
    out = []
    for f in sorted(EXAMPLES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if "kernel_ast" in d:
            out.append(f)
    return out


@pytest.mark.parametrize(
    "example_path",
    _kernel_ast_examples(),
    ids=lambda p: p.name,
)
def test_kernel_ast_example_parses_and_runs(example_path: Path):
    """Each kernel_ast example loads, parses, and runs without raising.
    Result envelope contract checked: results[0] exists with a status."""
    data = json.loads(example_path.read_text(encoding="utf-8"))
    program = data["kernel_ast"]
    out = run(program)
    assert "results" in out
    assert len(out["results"]) >= 1
    assert "status" in out["results"][0]


def test_at_least_five_kernel_ast_examples_present():
    """Sanity: examples directory has the expected number of full A1
    worked examples. If a prompt restructure renames or drops them
    silently this catches it."""
    examples = _kernel_ast_examples()
    assert len(examples) >= 5, (
        f"docs/prompts/examples/ should have >=5 files with kernel_ast key; "
        f"found {len(examples)}: {[p.name for p in examples]}"
    )


# Iter 99 audit: 4 known example shape groups
_KNOWN_EXAMPLE_SHAPES = {
    # A1 worked NL→kernel_ast (5 files)
    ("kernel_ast", "nl_input", "reasoning"),
    # A5 narrative→variables (3 files)
    ("narrative_input", "reasoning", "variables"),
    # A2 narrative→edges (3 files)
    ("edges", "narrative_ambiguities", "narrative_input", "reasoning",
     "refusals"),
    # Reply / patch bundles (3 files)
    ("filled_bundle", "input_bundle", "nl_reply", "reasoning"),
}


def test_example_files_match_known_shape():
    """Every docs/prompts/examples/*.json must match one of the known
    shape signatures (top-level key tuple).

    Iter 99 preventive pin. New example added with a typo or
    accidentally different key set silently joins as a "5th shape" —
    rather than being noticed and either consolidated to existing
    shapes or formally introducing a new shape category, the audit
    surface is preserved.
    """
    violations = []
    for f in sorted(EXAMPLES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        shape = tuple(sorted(d.keys()))
        if shape not in _KNOWN_EXAMPLE_SHAPES:
            violations.append(f"{f.name}: shape {shape} not in known set")
    assert not violations, "\n".join(violations)
