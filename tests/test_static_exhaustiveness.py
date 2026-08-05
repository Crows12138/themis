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

So this module checks the checker: that the listed modules pass, that a
missing branch is caught, that a misspelt member is caught, and — the
one that decays silently — that every file writing ``assert_never`` is on
the list mypy actually reads.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import re

import pytest

mypy_api = pytest.importorskip(
    "mypy.api", reason="mypy is a dev dependency; install with .[dev]")

REPO = pathlib.Path(__file__).resolve().parent.parent


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


def _check(*paths: str) -> str:
    """mypy's findings for these paths, as it would report them."""
    with _themis_on_the_search_path():
        stdout, stderr, _status = mypy_api.run([
            "--follow-imports=silent",
            "--ignore-missing-imports",
            "--warn-unused-ignores",
            "--python-version=3.11",
            *paths,
        ])
    assert "Traceback" not in stderr, stderr
    assert "usage: mypy" not in stderr, stderr
    return stdout


def _checked_modules() -> list[str]:
    """The ``files`` list from the mypy config, read as data."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[tool.mypy]", 1)[1].split("files = [", 1)[1]
    return re.findall(r'"([^"]+)"', block.split("]", 1)[0])


def test_the_configured_modules_have_no_findings():
    """What is on the list has been read and cleaned. A finding here is a
    module that stopped being clean, not a module that was never typed."""
    out = _check(*(str(REPO / m) for m in _checked_modules()))
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
    out = _check(str(src))
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
    out = _check(str(src))
    assert "Success" not in out, out
    assert "NOT_IDENTIFED" in out, out


def test_every_file_that_says_assert_never_is_one_mypy_reads():
    """The decay this module exists for.

    ``assert_never`` in an unchecked file states nothing: it runs only
    when the fall-through already happened, and reports it as an
    ``AssertionError`` from a line whose whole purpose was to make that
    impossible. Adding one to a module nobody checks is the same move as
    binding a renderer nothing calls.
    """
    checked = {(REPO / m).resolve() for m in _checked_modules()}
    writing = {
        p.resolve() for p in (REPO / "themis").rglob("*.py")
        if "assert_never(" in p.read_text(encoding="utf-8")
    }
    unread = sorted(str(p.relative_to(REPO)) for p in writing - checked)
    assert not unread, (
        f"{unread} state exhaustiveness with assert_never but are not in "
        f"the mypy files list, so nothing reads the statement"
    )
