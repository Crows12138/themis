"""What the reader is actually handed, once each vocabulary has a word.

``tests/test_vocabulary_reach.py`` asks whether every vocabulary has a
gloss. That is coverage, and coverage can be complete while nothing calls
it: a table with every key is worth nothing if the renderer interpolates
the field instead of asking. So these pin the rendered surface — the value
a reader sees for a member, not the mapping that could have produced it.

The last one is a different shape and covers what a per-vocabulary check
cannot: a producer writing a whole sentence in the wrong language. Two did
— the type-reconciliation gap and two of the three alternatives under
``unmeasured_confounder_risk`` — and no vocabulary was involved, so nothing
keyed on one could have seen them.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

import themis
from themis.output.analysis_report import build_analysis_report
from themis.types import ResultStatus

REPO = pathlib.Path(__file__).resolve().parent.parent
L3 = REPO / "docs" / "l3_simulation"
CJK = re.compile(r"[一-鿿]")


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# --- the mediation conditions ------------------------------------------------

def _unidentifiable_mediation() -> dict:
    """X→M→Y with a variable that X causes and that confounds M and Y.

    The textbook M3 violation: an intermediate confounder leaves a
    back-door from M to Y open that conditioning on X cannot close.
    """
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in ("x", "m", "y", "w")
        ] + [
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("w")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                    "mediator": _atom("m"),
                },
            },
        ],
    }


def test_a_failed_mediation_condition_says_which_path_is_open():
    """``M3`` names the theorem line; the reader needs the graph."""
    out = themis.run(_unidentifiable_mediation())
    res = out["results"][0]
    block = res["extensions"]["mediation_decomposition"]
    assert block["nde_nie"]["failed_condition"], (
        "fixture no longer produces an unidentifiable natural decomposition")
    md = build_analysis_report(res, program=out["program"])
    assert "后门路径" in md, md


# --- the framing fields ------------------------------------------------------

def test_an_unset_declaration_field_says_what_it_would_have_pinned_down():
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.output.explainer import explain
    from themis.runtime.graph_projection import project
    from themis.runtime.instantiation import instantiate
    from themis.runtime.scheduler import dispatch_all
    from themis.types import QueryStatement

    validate_ast(program)
    prog = validate_program(program)
    results = dispatch_all(prog, project(instantiate(prog)))
    by_id = {
        s.id: s for s in prog.statements if isinstance(s, QueryStatement)
    }
    res = results[0]
    assert res.framing_notes, "fixture no longer under-frames anything"
    text = explain(res, stmt=by_id[res.query_id])
    assert "时间窗" in text, text
    assert "time_window" not in text


# --- every status has a badge ------------------------------------------------

@pytest.mark.parametrize("status", sorted(s.value for s in ResultStatus))
def test_no_status_is_headed_by_its_own_identifier(status):
    """``_STATUS_BADGE.get(status, status)`` hands the identifier back.

    Parametrised over the vocabulary rather than over the corpus: the L3
    corpus reaches two of the seven statuses, so a corpus sweep would have
    passed on the day the two counterfactual ones had no badge — which is
    the day they did not have one.
    """
    out = themis.run(json.loads(
        (L3 / "case_001_hrt_cvd.json").read_text(encoding="utf-8")))
    res = dict(out["results"][0], status=status)
    head = build_analysis_report(res, program=out["program"]).split("\n\n")[1]
    assert status not in head, head


# --- no producer writes the reader a sentence in another language ------------

def _every_gap_string(res: dict):
    for gap in (res.get("data_gap_report") or {}).get("gaps") or []:
        yield gap["kind"], "description", gap.get("description") or ""
        yield gap["kind"], "if_provided", gap.get("if_provided") or ""
        for i, path in enumerate(gap.get("alternative_paths") or []):
            yield gap["kind"], f"alternative_paths[{i}]", path


@pytest.mark.parametrize("case", sorted(L3.glob("case_*.json")))
def test_every_gap_sentence_is_in_the_report_s_language(case):
    """The check no per-vocabulary gate could make.

    A gap kind's sentences are written once, at the producer, and nothing
    downstream re-reads them — so a producer that writes them in English
    ships English to a Chinese report and every other check still passes.
    Two did: 46 of the 48 non-Chinese alternatives one suite run produced
    came from a single kind.
    """
    out = themis.run(json.loads(case.read_text(encoding="utf-8")))
    wrong = [
        (kind, where, text)
        for res in out["results"]
        for kind, where, text in _every_gap_string(res)
        if text and not CJK.search(text)
    ]
    assert not wrong, wrong
