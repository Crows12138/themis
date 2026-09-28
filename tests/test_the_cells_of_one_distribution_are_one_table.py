"""The cells of one missing distribution are shown as one table.

Every cell the evaluator looks for and theta does not hold is filed as a gap
of its own, and since graphs are drawn with every common cause of their
outcome (#783) a question with k binary common causes files 2^k cells of one
conditional distribution. The page listed each as a row — "a probability
distribution is missing: P(y=True|c1=True,c2=False,…)" twenty times over —
and ended on twenty identical steps, "supply the distribution this is short
of". A reader supplies a table, not twenty unrelated numbers.

Nothing on the gap said which table a cell was in. It carried the rendered
key, which is the reader's copy and is spelled more than one way (a source
population's is ``P_trial(…)``), so a surface grouping by it would be parsing
wording. The gap now carries the distribution's name, read off the statement
it cites, as the ``signature`` beside it is.

What is held:

- each missing cell names the distribution it is a cell of, the conditional
  cells of one outcome share one name and a marginal is named alone, and a
  source population's distribution keeps its population;
- the verifier reads the name off the cited statement and refuses a gap that
  names another one or none;
- the page groups by that name and says a table's step once.
"""
from __future__ import annotations

import collections
import copy
import json
import re
from pathlib import Path

import pytest

import themis
from themis.verifier.errors import VerificationError

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "themis" / "web" / "frontend" / "src"
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text(encoding="utf-8"))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b),
            "annotations": {"source": "llm_proposal"}}


CAUSES = ("c1", "c2", "c3")
PROGRAM = {
    "version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        _var("x"), _var("y"), *(_var(c) for c in CAUSES), _edge("x", "y"),
        *(e for c in CAUSES for e in (_edge(c, "x"), _edge(c, "y"))),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "target": {"atom": _atom("y"), "value": True},
            "intervention": {"atom": _atom("x"), "value": True}, "given": []}},
    ],
}


def _cells(result):
    gaps = (result.get("data_gap_report") or {}).get("gaps") or []
    return [g for g in gaps if g["kind"] == "missing_distribution"]


def test_the_cells_of_one_outcome_share_one_name():
    named = collections.Counter(g.get("distribution") for g in _cells(themis.run(PROGRAM)["results"][0]))
    assert named == {"P(y | c1, c2, c3, x)": 8, "P(c1)": 1, "P(c2)": 1, "P(c3)": 1}


def test_a_source_population_keeps_its_population():
    """Every archived cell names its table, and a transported question's
    tables are named by the population they are taken in, as its keys are."""
    cells = [g for row in SHAPES.values() for g in _cells(row["result"])]
    assert cells and all(g.get("distribution") for g in cells)
    for g in cells:
        key = g["describes"][0]["said"]["what"]
        head = key[:key.index("(")]
        assert g["distribution"].startswith(head + "("), (key, g["distribution"])
    assert any(g["distribution"].startswith("P_") for g in cells)


@pytest.mark.parametrize("bend, says", [
    (lambda g: g.update(distribution="P(somewhere_else)"), "files its cell under 'P(somewhere_else)'"),
    (lambda g: g.pop("distribution"), "files its cell under None"),
], ids=["another name", "no name"])
def test_the_verifier_reads_the_name_off_the_statement(bend, says):
    result = themis.run(PROGRAM)["results"][0]
    themis.verify_answer_claims(PROGRAM, result)
    bent = copy.deepcopy(result)
    bend(_cells(bent)[0])
    with pytest.raises(VerificationError, match=re.escape(says)):
        themis.verify_answer_claims(PROGRAM, bent)


def test_the_page_shows_a_table_once():
    page = (FRONTEND / "components" / "GapReport.tsx").read_text(encoding="utf-8")
    # Grouped by the name the gap carries, never by its rendered key.
    assert "g.kind === 'missing_distribution' ? g.distribution : undefined" in page
    assert "said.what" not in page
    # A table is one step, named by its distribution.
    assert "fill(SAYS.supplyTable, lang, { name: row.distribution, n: row.gaps.length })" in page
    types = (FRONTEND / "types.ts").read_text(encoding="utf-8")
    assert "distribution?: string" in types
