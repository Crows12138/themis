"""What a model is handed of a result has a ceiling; the record does not.

The first real question asked through MCP — would a run of slowing
search-ad revenue show that AI is eroding search — came back at 205,402
characters. Half of that was indentation; most of the rest was 42 cells of
one probability table, each listed three times. Claude Code moved it to a
file, and the agent read it only because it had a shell. Its two guides
were moved to files the same way.

The envelope's size is the question's, and it has no ceiling because an
audit needs all of it. So the ceiling is on what is handed over:
``themis.output.bounded_view`` folds whatever does not fit into markers,
and the server keeps the record and follows them. What is held here:

- a record that fits is handed over exactly as it is;
- a view never runs past its budget by more than the answer itself does;
- the answer is never folded;
- following every marker gives back the record, byte for byte — over the
  whole archive of answers, at budgets small enough to fold most of it;
- through the server: the attribution question from that test comes back
  within budget, with its audits run and its record whole behind the id,
  and the guides come back a section at a time, each within budget, the
  sections adding up to the document.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import themis
from themis.output import bounded_view
from themis.output.bounded_view import FOLD

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = json.loads(
    (REPO / "tests" / "fixtures" / "answer_shapes.json").read_text(encoding="utf-8"))

#: Small enough that most of the archive folds, large enough to hold an answer.
BUDGETS = (3_000, 9_000, bounded_view.DEFAULT_BUDGET)


def _records():
    for name, entry in sorted(ARCHIVE.items()):
        yield name, {"results": [entry["result"]], "program": entry["program"]}


def _follow(where: str, start: int, fetch) -> object:
    frame = fetch(where, start)
    value = frame["value"]
    if isinstance(value, str):
        pieces = [value]
        while "next" in frame:
            frame = fetch(where, frame["next"])
            pieces.append(frame["value"])
        return "".join(pieces)
    return _reassembled(value, fetch)


def _reassembled(value: object, fetch) -> object:
    """``value`` with every marker in it replaced by what it points at.

    In a list a marker is only ever the tail — the items from ``from`` on —
    because an item that must be opened is never folded whole, and any
    other list keeps its head whole.
    """
    if isinstance(value, dict):
        if set(value) == {FOLD}:
            said = value[FOLD]
            return _follow(said["pointer"], said.get("from", 0), fetch)
        return {k: _reassembled(v, fetch) for k, v in value.items()}
    if isinstance(value, list):
        out: list = []
        for item in value:
            if isinstance(item, dict) and set(item) == {FOLD}:
                said = item[FOLD]
                out.extend(_follow(said["pointer"], said.get("from", 0), fetch))  # type: ignore[arg-type]
            else:
                out.append(_reassembled(item, fetch))
        return out
    return value


def _markers(value: object) -> int:
    if isinstance(value, dict):
        if set(value) == {FOLD}:
            return 1
        return sum(_markers(v) for v in value.values())
    if isinstance(value, list):
        return sum(_markers(v) for v in value)
    return 0


# ------------------------------------------------------------------ the view


def test_a_record_that_fits_is_handed_over_as_it_is():
    fits = [(name, record) for name, record in _records()
            if bounded_view.size(record) <= bounded_view.DEFAULT_BUDGET]
    assert len(fits) > 200, "the archive stopped being mostly small; re-read this test"
    for name, record in fits:
        assert bounded_view.view(record) == record, name


@pytest.mark.parametrize("budget", BUDGETS)
def test_a_view_runs_past_its_budget_only_by_what_the_answer_needs(budget):
    """The floor is the most-folded view there is — every part folded that
    may be. A view larger than its budget is allowed only up to that."""
    for name, record in _records():
        floor = bounded_view.size(bounded_view.view(record, 0))
        got = bounded_view.size(bounded_view.view(record, budget))
        assert got <= max(budget, floor), (name, got, budget, floor)


@pytest.mark.parametrize("budget", BUDGETS)
def test_following_every_marker_gives_back_the_record(budget):
    folded = 0
    for name, record in _records():
        seen = bounded_view.view(record, budget)
        folded += _markers(seen) > 0

        def fetch(where, start, record=record):
            frame = bounded_view.part(record, where, start, budget)
            assert bounded_view.size(frame) <= max(
                budget, bounded_view.size(bounded_view.part(record, where, start, 0))), (name, where)
            return frame

        assert _reassembled(seen, fetch) == record, name
    assert folded, "nothing folded at this budget, so nothing was followed"


def test_the_answer_is_never_folded():
    """At a budget of nothing, every part that may fold has — and the
    answer is still there, as the record has it."""
    for name, record in _records():
        seen = bounded_view.view(record, 0)
        result, shown = record["results"][0], seen["results"][0]
        for key in ("status", "query_kind", "query_id", "numeric_result",
                    "structural_result"):
            assert shown.get(key) == result.get(key), (name, key)
        for block, key in (("data_gap_report", "answer_tier"),
                           ("extensions", "assumption_ledger")):
            if key in (result.get(block) or {}):
                assert shown[block][key] == result[block][key], (name, block)


def test_a_pointer_that_names_nothing_says_which_step_did_not_resolve():
    record = {"results": [{"status": "x"}]}
    with pytest.raises(KeyError, match="no item '3'"):
        bounded_view.part(record, "/results/3")
    with pytest.raises(KeyError, match="no key 'nope'"):
        bounded_view.part(record, "/results/0/nope")


# ------------------------------------------------------------------ the server


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "google"}]}


#: The shape of the question that came back at 205,402 characters: four
#: candidate causes of one outcome, asked as attribution, with no data.
CAUSES = ("ai_erodes_search", "ad_market_cyclical_weakness",
          "competition_from_other_ad_platforms", "high_base_deceleration")
EFFECT = "search_ad_revenue_growth_slows"
ATTRIBUTION = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "google"}]},
    "statements": [
        *({"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in (*CAUSES, EFFECT)),
        *({"kind": "cause", "from": _atom(c), "to": _atom(EFFECT),
           "annotations": {"source": "llm_proposal"}} for c in CAUSES),
        {"kind": "query", "id": "q", "query": {
            "kind": "causation", "cause": _atom(CAUSES[0]),
            "effect": _atom(EFFECT)}},
    ],
}


@pytest.fixture(scope="module")
def app():
    from themis.mcp import build_server
    return build_server()


def _text(app, name, args) -> str:
    blocks = asyncio.run(app.call_tool(name, args))
    texts = [b.text for b in blocks if getattr(b, "text", None)]
    assert len(texts) == 1, blocks
    return texts[0]


def test_the_question_that_overflowed_now_fits(app):
    record = themis.run(ATTRIBUTION)
    # 101,814 characters when this was written, 56,922 once the last value
    # of a variable under one condition stopped being asked for (#776).
    # What the test needs is only that one view cannot hold it.
    assert bounded_view.size(record) > bounded_view.DEFAULT_BUDGET, (
        "the record no longer overflows, so this no longer tests the fold")
    text = _text(app, "themis_run", {"program": ATTRIBUTION})
    assert len(text) <= bounded_view.DEFAULT_BUDGET
    handed = json.loads(text)
    assert handed["results"][0]["status"] == record["results"][0]["status"]
    assert all(row["audit"] and row["ok"] is not None
               for row in handed["audits"][0])

    def fetch(where, start):
        return json.loads(_text(app, "themis_result", {
            "result_id": handed["result_id"], "pointer": where,
            "start": start}))

    whole = _reassembled(handed, fetch)
    assert whole["results"] == record["results"]
    assert whole["program"] == record["program"]


def test_an_audit_by_id_is_the_audit_of_the_record(app):
    handed = json.loads(_text(app, "themis_run", {"program": ATTRIBUTION}))
    by_id = json.loads(_text(app, "themis_audit",
                             {"result_id": handed["result_id"]}))
    record = themis.run(ATTRIBUTION)
    assert by_id["audits"] == [themis.audit(record["program"], r)
                               for r in record["results"]]


def test_an_id_the_server_does_not_hold_is_refused_by_saying_so(app):
    from mcp.server.fastmcp.exceptions import ToolError
    with pytest.raises(ToolError, match="no result 'r999999'"):
        asyncio.run(app.call_tool("themis_result", {"result_id": "r999999"}))


def test_the_agent_is_told_how_before_its_first_call(app):
    said = app.instructions or ""
    for name in ("themis_guide", "themis_result", "result_id", "omitted"):
        assert name in said, name


def _guide(app, **args) -> dict:
    text = _text(app, "themis_guide", args)
    assert len(text) <= bounded_view.DEFAULT_BUDGET, (args, len(text))
    return json.loads(text)


def _section_text(app, doc: str, name: str) -> str:
    """A section's whole text, by following what the guide hands over."""
    got = _guide(app, doc=doc, section=name)
    pieces = [got["text"]]
    while "next" in got:
        got = _guide(app, doc=doc, section=name, start=got["next"])
        pieces.append(got["text"])
    for sub in got.get("subsections", []):
        pieces.append(_section_text(app, doc, sub))
    return "".join(pieces)


def test_every_guide_comes_back_whole_a_section_at_a_time(app):
    docs = _guide(app)["documents"]
    prompts = [d["doc"] for d in docs if d["doc"].endswith(".md")]
    assert "nl_to_kernel_ast.md" in prompts and "response_rendering.md" in prompts
    for doc in prompts:
        text = (REPO / "themis" / "prompts" / doc).read_text(encoding="utf-8")
        contents = _guide(app, doc=doc)
        top = [s["section"] for s in contents["sections"] if " > " not in s["section"]]
        assert contents["sections"], doc
        # The text before the first heading, then each top-level section.
        first = text.index(next(line for line in text.splitlines(keepends=True)
                                if line.startswith("#")))
        rebuilt = text[:first] + "".join(_section_text(app, doc, s) for s in top)
        assert rebuilt == text, doc


def test_every_schema_definition_comes_back_within_budget(app):
    for doc in ("kernel_ast.schema.json", "query_result.schema.json"):
        schema = json.loads(
            (REPO / "themis" / "schemas" / doc).read_text(encoding="utf-8"))
        names = [s["section"] for s in _guide(app, doc=doc)["sections"]]
        assert set(names) - {"(root)"} == set(schema["$defs"]), doc
        for name in names:
            _guide(app, doc=doc, section=name)
