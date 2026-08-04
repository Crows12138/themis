"""A module defines each of its top-level names once.

Python does not object to a second ``def`` of a name already defined:
the later one silently wins, and the earlier one becomes code that reads
like it runs. Nothing about the file says which is which — the reader
has to notice the repetition, and the repetition is usually thousands of
lines apart, which is exactly how it survives review.

``dispatch`` carried two ``_collect_required_columns`` and two
``_ensure_dict``. The dead ``_collect_required_columns`` was the older,
narrower one: it had no notion of a proximal latent, so a reader who
found it first would conclude that the data contract demands a column
for a node that is unobserved by construction. It was never called.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "themis"


def test_no_module_defines_the_same_name_twice() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        defined = collections.Counter(
            node.name
            for node in module.body
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
        )
        offenders += [
            f"{path.relative_to(PACKAGE.parent)}: {name} defined {count}×"
            for name, count in sorted(defined.items())
            if count > 1
        ]
    assert not offenders, (
        "a later definition silently replaces an earlier one, leaving code "
        "that reads as if it runs:\n  " + "\n  ".join(offenders)
    )
