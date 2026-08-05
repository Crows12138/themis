"""The half of a vocabulary table that ``bind`` cannot check.

A table in this codebase declares a closed set and some surface has to
cover it. ``bind`` states one half of that at import: *this dict's keys
are exactly the set*. The other half is a claim about branches — *this
match handles every member* — and no dict can hold it, because there is
no dict.

``typing.assert_never`` states it, and states it to a type checker: the
call is reached only if some member fell through, and a checker that has
narrowed the subject to ``Never`` by then is the thing that knows. Which
means the statement is worth exactly what reads it. Unread, it is a
comment that happens to be executable.

So this module checks the checker: that the package passes, that a
missing branch is caught, that a misspelt member is caught, and — the one
that decays silently — that no file writing ``assert_never`` sits in the
list of modules whose findings are ignored.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import tomllib

import pytest

mypy_api = pytest.importorskip(
    "mypy.api", reason="mypy is a dev dependency; install with .[dev]")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO / "pyproject.toml"


@contextlib.contextmanager
def _themis_on_the_search_path():
    """``MYPYPATH``, because a probe module lives outside the repo.

    The checks below write a module to a temp directory and ask mypy about
    it; from there ``themis`` is not resolvable the way it is from the
    repo root, and mypy would silently type its members as ``Any`` — which
    is the one outcome that would make a check about names pass for the
    wrong reason.
    """
    before = os.environ.get("MYPYPATH")
    os.environ["MYPYPATH"] = str(REPO)
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("MYPYPATH", None)
        else:
            os.environ["MYPYPATH"] = before


def _run_mypy(*paths: str) -> str:
    """mypy's findings, under the repository's own configuration.

    The config is named rather than discovered, so a probe written to a
    temp directory is judged by the same rules as the package.
    """
    with _themis_on_the_search_path():
        stdout, stderr, _status = mypy_api.run(
            ["--config-file", str(CONFIG), *paths])
    assert "Traceback" not in stderr, stderr
    assert "usage: mypy" not in stderr, stderr
    return stdout


def _suppressed_modules() -> list[str]:
    """The modules whose findings are ignored, read out of the config.

    A list that can only shrink: the package is checked, and this names
    what has not been read yet.
    """
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    suppressed: list[str] = []
    for override in config["tool"]["mypy"].get("overrides", ()):
        if override.get("ignore_errors"):
            suppressed.extend(override["module"])
    return suppressed


def _module_of(path: pathlib.Path) -> str:
    """The dotted name a config override would have to spell to reach it."""
    rel = path.resolve().relative_to(REPO).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def test_the_package_has_no_findings_outside_the_suppressed_list():
    """Run the way a developer runs it: no paths, the config decides.

    A finding here is a module that stopped being clean — the ones that
    were never read are named in the config and say so.
    """
    out = _run_mypy()
    assert "Success" in out, out


def test_a_match_missing_one_member_is_caught(tmp_path):
    """The guarantee itself. Four of the five kinds handled, and the fifth
    reaches ``assert_never`` — which is a type error precisely because the
    subject has not been narrowed to ``Never``."""
    src = tmp_path / "missing_branch.py"
    src.write_text(
        "from typing import assert_never\n"
        "from themis.refusals import Kind\n"
        "def words(k: Kind) -> str:\n"
        "    match k:\n"
        "        case Kind.GRAPH: return 'a'\n"
        "        case Kind.DATA: return 'b'\n"
        "        case Kind.UNBUILT: return 'c'\n"
        "        case Kind.REQUEST: return 'd'\n"
        "    assert_never(k)\n",
        encoding="utf-8")
    out = _run_mypy(str(src))
    assert "Success" not in out, out
    assert "assert_never" in out or "Never" in out, out


def test_a_misspelt_species_is_caught(tmp_path):
    """The case a registry cannot reach from inside. The name is evaluated
    only when its line runs, and the line that names a refusal is the
    branch no test took — which is why eight of them sit unexercised in
    iv.py alone."""
    src = tmp_path / "misspelt.py"
    src.write_text(
        "from themis.refusals import Refusal\n"
        "def why() -> Refusal:\n"
        "    return Refusal.NOT_IDENTIFED\n",
        encoding="utf-8")
    out = _run_mypy(str(src))
    assert "Success" not in out, out
    assert "NOT_IDENTIFED" in out, out


def test_no_file_that_says_assert_never_has_its_findings_ignored():
    """The decay this module exists for.

    ``assert_never`` in a module whose findings are ignored states
    nothing: it runs only when the fall-through already happened, and
    reports it as an ``AssertionError`` from a line whose whole purpose
    was to make that impossible. Writing one in a suppressed module is the
    same move as binding a renderer nothing calls.
    """
    suppressed = set(_suppressed_modules())
    writing = {
        _module_of(p) for p in (REPO / "themis").rglob("*.py")
        if "assert_never(" in p.read_text(encoding="utf-8")
    }
    unread = sorted(writing & suppressed)
    assert not unread, (
        f"{unread} state exhaustiveness with assert_never but their "
        f"findings are ignored, so nothing reads the statement"
    )
