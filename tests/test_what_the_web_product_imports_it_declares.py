"""What the web product imports, its install declares.

The model client was imported by ``themis/web/llm_bridge.py`` and declared
nowhere: the ``web`` extra listed the server and nothing else. Every machine
this was developed on had the client for other reasons, so the gap showed
only where the product was installed as declared — the demo server, where
all three model surfaces answered that the client was missing (#778).

What is declared is read from ``pyproject.toml``; what is imported is read
from the source. Neither is a list kept here.
"""
from __future__ import annotations

import ast
import importlib.metadata
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "themis" / "web"


def _name(requirement: str) -> str:
    """A requirement's distribution name, in the form PEP 503 compares."""
    head = re.split(r"[\s<>=!~;\[(]", requirement, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", head).lower()


def _declared() -> frozenset[str]:
    project = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return frozenset(_name(r) for r in (
        project["dependencies"] + project["optional-dependencies"]["web"]))


def _imported() -> dict[str, list[str]]:
    """Each third-party top-level module the web package imports, with the
    files that import it."""
    seen: dict[str, set[str]] = {}
    for path in sorted(WEB.rglob("*.py")):
        if "node_modules" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif (isinstance(node, ast.ImportFrom) and node.level == 0
                  and node.module):
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if (top in sys.stdlib_module_names
                        or top in ("themis", "__future__")):
                    continue
                seen.setdefault(top, set()).add(
                    path.relative_to(ROOT).as_posix())
    return {top: sorted(files) for top, files in seen.items()}


IMPORTED = _imported()


def test_the_walk_finds_what_the_web_product_imports():
    """The denominator: a walk that found nothing would pass the test
    below. The server, the client, and what the core already declares."""
    assert sorted(IMPORTED) == [
        "anthropic", "fastapi", "pandas", "pydantic", "uvicorn"], IMPORTED


def test_every_third_party_import_is_declared_by_the_core_or_the_web_extra():
    distributions = importlib.metadata.packages_distributions()
    declared = _declared()
    undeclared = {
        top: files for top, files in IMPORTED.items()
        if not {_name(d) for d in distributions.get(top, [top])} & declared}
    assert not undeclared, (
        f"imported under themis/web/ but declared neither in [project] "
        f"dependencies nor in the web extra: {undeclared}")
