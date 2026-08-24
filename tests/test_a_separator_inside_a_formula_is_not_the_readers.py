"""#447 — a list a reader reads and a list inside a formula are two things.

One door served both. ``listing`` joins with the reader's punctuation, which
is right for "x, y and z" and wrong for the conditioning set in
``P(y | x, z)``: that comma is part of the mathematics, for the reason
:attr:`themis.language.Text.FORMULA` already gives about a Σ.

What it cost is visible without reading any code — one Chinese report showed
the same conditioning set two ways on adjacent lines, ``P(y | x、z)`` from
the factorization a reader assembled and ``P(y | x, z)`` from the formula the
kernel wrote. The browser had the same expression with a Chinese comma
spelled in by hand, which is the registered symptom of this: a separator
with no name gets picked locally, differently, by whoever needs one.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from themis import build_analysis_report, language
from themis.output.result_orchestrator import to_dict
from themis.types import QueryKind, QueryResult, ResultStatus

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERDICT = ROOT / "themis/web/frontend/src/lib/verdict.ts"

#: One block whose factorization and whose formula name the same set, which
#: is what makes the two renderings comparable at all.
BLOCK = {
    "kind": "missing_data_recovery", "target": "P(y | x, z)",
    "mechanism": "MAR", "recoverable": True, "partially_observed": ["z"],
    "factorization": [{"factor": "y", "conditioned_on": ["x", "z"]},
                      {"factor": "z", "conditioned_on": []}],
    "recovery_formula": "P(y | x, z) · P(z)",
    "failure_reason": None, "complete_criterion": False,
    "reference": "Mohan, Pearl & Tian 2013", "search_budget": 3,
    "adjustment_set": ["z"], "covariate_recovery": None,
    "estimand": {"target": "P(y | do(x))", "recoverable": True,
                 "recovery_formula": "Σ_z P(y | x, z) · P(z)",
                 "requires": [], "failure_reason": None},
}


def _report(lang: str) -> str:
    doc = to_dict(QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION, query_kind=QueryKind.EFFECT,
        extensions={"missing_data_recovery": dict(BLOCK)}))
    return build_analysis_report(doc, lang=lang)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_one_expression_reads_one_way_in_one_report(lang):
    """The failure this replaced, as the reader met it.

    Two lines of the same section, the same conditioning set, and — before
    this — two separators, because one line was assembled by the reader and
    the other written by the kernel.
    """
    conditioned = {line.strip() for line in _report(lang).splitlines()
                   if "P(y |" in line}
    assert conditioned, lang
    for line in conditioned:
        assert "P(y | x, z)" in line, (lang, line)
        assert "、" not in line, (lang, line)


def test_the_expression_is_the_same_in_both_languages():
    """It is mathematics, so there is nothing in it to say twice."""
    def spelling(text: str) -> set[str]:
        return set(re.findall(r"P\(y \| [^)]*\)", text))

    assert spelling(_report("zh")) == spelling(_report("en"))


@pytest.mark.parametrize("items,said", [
    (("x", "z"), "x, z"),
    ((), ""),
    (("x",), "x"),
])
def test_the_door_takes_no_language(items, said):
    """And that is the whole statement it makes.

    A signature is where this is enforceable: a reader's punctuation cannot
    reach a formula through a door that was never handed a reader.
    """
    assert language.within(items) == said
    tree = ast.parse((ROOT / "themis/language.py").read_text(encoding="utf-8"))
    door, = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "within"]
    assert not [a.arg for a in [*door.args.args, *door.args.kwonlyargs]
                if a.arg == "lang"]


def test_the_browser_picks_no_punctuation_of_its_own():
    """Its twin, and the registered symptom.

    Every one of these was a list — six a reader's, one a formula's — and
    each had the Chinese comma written in, so the English surface read every
    one of them wrong.
    """
    source = VERDICT.read_text(encoding="utf-8")
    # The denominator: this surface does join lists, through the two doors
    # that know which kind each is.
    assert source.count("listing(") > 8, source.count("listing(")
    assert "within(" in source
    for spelled in ("join('、')", 'join("、")'):
        assert spelled not in source, spelled


def test_both_surfaces_write_the_formula_the_same_way():
    """The browser's factorization mirrors the report's, so it has to.

    A mirror nobody holds equal is a mirror that drifts, and this one had:
    the report borrowed the reader's comma and the browser spelled the
    Chinese one in, which agreed by accident in Chinese and in no other
    language.
    """
    source = VERDICT.read_text(encoding="utf-8")
    assert "` | ${within(f.conditioned_on)}`" in source
