"""A reader supplies the numbers a model would be asked for.

When the kernel is short of probabilities the page offered one way to fill
them: have a model guess. A reader who has the numbers — from data, a paper,
published statistics — had nowhere to put them but the program's JSON, one
cell at a time under the kernel's key spelled exactly, and a table of four
causes is sixteen of those where the model is asked for five numbers.

So the reader is asked what the model is asked, and the reader's answers
become the records the model's would, except that they are the reader's:

- ``/api/asks`` lists the requests the model is shown, and with each table
  its own cells, for a reader who has it cell by cell;
- ``/api/supply`` fills what is answered — a table as a baseline and
  ratios, a table cell by cell, a cell — and runs again; each record keeps
  the kind of conditional the kernel asked for, none is marked a guess, and
  each carries the reader's source where they gave one;
- a table the reader states as a baseline and ratios is their line of the
  assumption ledger, and one given cell by cell owes none;
- a request left blank is left asked, and asked again;
- nothing to fill, nothing filled, and an answer that is not to this
  program's requests are each refused, under a stage of their own.
"""
from __future__ import annotations

import json
from itertools import product
from types import SimpleNamespace

import pytest

import themis

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from themis.web import app as web_app  # noqa: E402
from themis.web import llm_bridge  # noqa: E402

client = TestClient(web_app.app)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(confounders):
    """x → y, each confounder a cause of both and c a cause of every
    confounder; no numbers. Two confounders are asked for cell by cell,
    three as two tables — one of them the observational factor P(v | z, w)
    the back-door adjustment names."""
    edges = [("x", "y"), *(("c", z) for z in confounders),
             *((z, t) for z in confounders for t in ("x", "y"))]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in ("c", "x", "y", *confounders)),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)}
              for a, b in edges),
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }


def _nothing_missing():
    """Whether x causes y: a structural question, short of no number."""
    program = _program(())
    program["statements"][-1]["query"] = {
        "kind": "cause", "from": _atom("x"), "to": _atom("y")}
    return program


def _cell(label):
    """The number for a cell, distinct per cell so an adjustment's weights
    show: 0.2 and 0.2 more for each condition at true."""
    return 0.2 + 0.2 * label.partition(" | ")[2].count("=True")


def _p(odds):
    return odds / (1 + odds)


def _three():
    """Σ P(z) P(w|z) P(v|z,w) P(y|x,z,w,v): z's and w's factors cells, v's
    and y's tables of baseline 0.2 and odds doubled by each condition
    present — x among them, set by do(x)."""
    def at(p, holds):
        return p if holds else 1 - p
    return sum(at(0.2, z) * at(0.2 + 0.2 * z, w)
               * at(_p(0.25 * 2 ** (z + w)), v) * _p(0.25 * 2 ** (1 + z + w + v))
               for z, w, v in product((1, 0), repeat=3))


def _asks(program):
    r = client.post("/api/asks", json={"program": program})
    assert r.status_code == 200, r.text
    return r.json()["requests"]


def _answer(asked):
    """What the model's stand-in answers below, as a reader would type it."""
    if "table" in asked:
        return {"index": asked["index"], "baseline": 0.2,
                "odds_ratios": [2.0] * len(asked["ratios"])}
    return {"index": asked["index"], "value": _cell(asked["probability"])}


def _by_cells(asked):
    if "table" not in asked:
        return _answer(asked)
    return {"index": asked["index"],
            "cells": [{"cell": c["cell"], "value": _cell(c["probability"])}
                      for c in asked["cells"]]}


def _supply(program, answers, **extra):
    r = client.post("/api/supply",
                    json={"program": program, "answers": answers, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _supplied(out, program):
    """The statements the merge added, which are what the reader supplied."""
    return out["merged_program"]["statements"][len(program["statements"]):]


def _form_lines(result):
    return [(claim.get("token"), entry.get("provenance"))
            for entry in ((result.get("extensions") or {})
                          .get("assumption_ledger") or {}).get("assumptions", ())
            for claim in entry.get("claim") or ()
            if claim.get("vocabulary") == "stated_form_claim"]


# ================================================================ what is asked


def test_a_reader_is_asked_what_a_model_is_asked(monkeypatch):
    """The same requests under the same indices, each labelled the same way.
    A reader is shown two things more: each ratio written out whole, and the
    cells a table stands for."""
    program = _program(("z", "w", "v"))
    sent = []

    def create(**kwargs):
        asked = json.loads(kwargs["messages"][0]["content"].split(
            "leave none out:\n", 1)[1])
        sent.extend(asked)
        priors = [
            {"index": a["index"], "baseline": {"value": 0.2, "reason": "r"},
             "odds_ratios": [{"ratio": r["ratio"], "value": 2.0, "reason": "r"}
                             for r in a["ratios"]]}
            if "table" in a else {"index": a["index"], "value": 0.5, "reason": "r"}
            for a in asked]
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps({"priors": priors}))])

    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=create)))
    rows = web_app._probability_skeletons(themis.run(program)["results"][0])
    llm_bridge.propose_theta_priors(program, rows)

    asked = _asks(program)
    assert sum("table" in a for a in asked) == 2
    shown_to_both = [
        {k: ([{f: r[f] for f in r if f != "label"} for r in v] if k == "ratios" else v)
         for k, v in a.items() if k != "cells"}
        for a in asked]
    assert shown_to_both == sorted(sent, key=lambda a: a["index"])
    y_table = next(a for a in asked if a["table"].startswith("P(y"))
    assert sorted(r["label"] for r in y_table["ratios"]) == [
        f"OR(y=True | {c}=True/False)" for c in "vwxz"]
    assert len(y_table["cells"]) == 8  # at the one value do(x) sets x to


def test_a_program_short_of_nothing_asks_nothing():
    assert _asks(_nothing_missing()) == []


# ======================================================== what an answer becomes


def test_the_reader_s_numbers_answer_as_the_model_s_would_and_are_the_reader_s():
    program = _program(("z", "w", "v"))
    out = _supply(program, [_answer(a) for a in _asks(program)])
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["numeric_result"]["value"] == pytest.approx(_three(), abs=1e-12)
    supplied = _supplied(out, program)
    assert not any("llm_prior" in s or "annotations" in s for s in supplied)
    assert ("probability_model", "observational") in {
        (s["kind"], s.get("provenance")) for s in supplied}
    assert "llm_proposed_review" not in result.get("extensions", {})
    assert _form_lines(result) == [("no_interaction", "caller_chose")] * 2
    themis.verify(out["merged_program"], result)


def test_a_table_given_cell_by_cell_owes_no_form_line():
    program = _program(("z", "w", "v"))
    out = _supply(program, [_by_cells(a) for a in _asks(program)])
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    supplied = _supplied(out, program)
    assert {s["kind"] for s in supplied} == {"probability"}
    assert "observational" in {s.get("provenance") for s in supplied}
    assert _form_lines(result) == []
    themis.verify(out["merged_program"], result)


@pytest.mark.parametrize("answer", [_answer, _by_cells],
                         ids=["tables as ratios", "tables cell by cell"])
def test_the_reader_s_source_goes_with_every_number(answer):
    program = _program(("z", "w", "v"))
    out = _supply(program, [answer(a) for a in _asks(program)],
                  source=" a 2021 cohort ")
    for s in _supplied(out, program):
        parts = ([s["baseline"], *s["odds_ratios"]]
                 if s["kind"] == "probability_model" else [s])
        assert [p["annotations"] for p in parts] == [
            {"source": "a 2021 cohort"}] * len(parts)


def test_a_request_left_blank_is_left_asked():
    """The cells answered and the tables not: the tables are what is left,
    and they are asked for as tables again."""
    program = _program(("z", "w", "v"))
    asked = _asks(program)
    out = _supply(program, [_answer(a) for a in asked if "table" not in a])
    assert out["results"][0]["status"] == "needs_investigation"
    assert [a.get("table") for a in _asks(out["merged_program"])] == [
        a["table"] for a in asked if "table" in a]


# ================================================================ what is refused


def _a_table(program, **answer):
    """An answer to the first table asked, ``answer`` overriding a whole
    one: its baseline, and a ratio for each of its ratios."""
    table = next(a for a in _asks(program) if "table" in a)
    return [{**_answer(table), **answer}]


@pytest.mark.parametrize("program, answers, stage", [
    (_program(("z", "w")), lambda p: [], "no_number_supplied"),
    (_nothing_missing(), lambda p: [{"index": 0, "value": 0.5}], "nothing_to_supply"),
    (_program(("z", "w")), lambda p: [{"index": 99, "value": 0.5}], "supply"),
    (_program(("z", "w")),
     lambda p: [{"index": 0, "value": 0.5}, {"index": 0, "value": 0.4}], "supply"),
    (_program(("z", "w")),
     lambda p: [{"index": 0, "baseline": 0.2, "odds_ratios": [2.0]}], "supply"),
    (_program(("z", "w")), lambda p: [{"index": 0, "value": True}], "supply"),
    (_program(("z", "w")), lambda p: [{"index": 0, "value": 1.5}], "supply"),
    (_program(("z", "w", "v")), lambda p: _a_table(p, odds_ratios=[]), "supply"),
    (_program(("z", "w", "v")), lambda p: _a_table(p, baseline=1.0), "supply"),
    (_program(("z", "w", "v")),
     lambda p: [{"index": _a_table(p)[0]["index"],
                 "cells": [{"cell": 99, "value": 0.5}]}], "supply"),
], ids=["nothing filled", "nothing to fill", "no such request",
        "one request answered twice", "a cell answered as a table",
        "a yes for a number", "a probability above one",
        "a table short of its ratios", "a baseline of one", "no such cell"])
def test_what_is_not_an_answer_is_refused_under_its_stage(program, answers, stage):
    r = client.post("/api/supply", json={"program": program,
                                         "answers": answers(program)})
    assert r.status_code == 400, r.text
    assert r.json()["stage"] == stage
