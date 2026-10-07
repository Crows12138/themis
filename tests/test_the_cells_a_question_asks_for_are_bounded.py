"""The cells a question asks for are bounded.

#819. A question short of a number is answered by naming what it is
short of, one cell at a time: a gap, an investigation request and a line
of the missing list each. x -> y with k yes-or-no common causes of both
is short of 2^k + k cells, and each one is built, glossed and held to the
envelope's schema on the way out — measured on the demo server, k = 10
takes 9 s for a 2.9 MB envelope and k = 12 takes 36 s for 13 MB, most of
it the schema check. The web's reverse proxy stops waiting at 120 s and
its one worker goes on computing for nobody, so one large graph was
every other visitor's wait. And a list of four thousand cells is not
what anybody fills in; data rows are, or a smaller graph.

So the kernel counts the cells where they are collected and, past a
fixed budget, refuses with a sentence saying the count and the two
things that do fill it, instead of building the envelope. The budget is
pinned to the measurement it was set from. The page, for its part, tells
a reader what a gateway status means instead of printing its number.
"""
from __future__ import annotations

import pytest

import themis
from themis.runtime import theta_builder
from themis.runtime.scheduler_words import Asks

from tests import web_source


def atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def va(p, v):
    return {"atom": atom(p), "value": v}


def program(k: int, query: dict) -> dict:
    """x -> y, and k common causes z1..zk of both, nothing supplied."""
    zs = [f"z{i}" for i in range(1, k + 1)]
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in ["x", "y", *zs]]
    statements.append({"kind": "cause", "from": atom("x"), "to": atom("y")})
    for z in zs:
        statements.append({"kind": "cause", "from": atom(z), "to": atom("x")})
        statements.append({"kind": "cause", "from": atom(z), "to": atom("y")})
    statements.append({"kind": "query", "id": "q", "query": query})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


EFFECT = {"kind": "effect", "intervention": va("x", True),
          "target": va("y", True), "given": []}
COUNTERFACTUAL = {"kind": "counterfactual", "observed": va("x", True),
                  "counterfactual_intervention": va("x", False),
                  "counterfactual_target": va("y", True),
                  "factual_target_known": False}


def test_the_budget_is_the_one_the_measurement_set():
    """k = 11 asks 2059 and takes about 18 s on the demo server for a 6 MB
    envelope; k = 12 asks 4108 and takes 36 s for 13 MB. The budget admits
    the first and refuses the second — and sits above the 2060 cells the
    counterfactual bound's ancestral factorisation asks at its own edge,
    which a budget of 2048 was found to refuse."""
    assert theta_builder.CELLS_ASKED_AT_MOST == 4096


@pytest.mark.parametrize("query", [EFFECT, COUNTERFACTUAL],
                         ids=["effect", "counterfactual"])
def test_a_question_short_of_more_cells_than_the_budget_is_refused(
        monkeypatch, query):
    """Held at a small budget so the graph can stay small: with four common
    causes an effect asks 2^4 + 4 cells, and the refusal says how many and
    what fills them."""
    monkeypatch.setattr(theta_builder, "CELLS_ASKED_AT_MOST", 8)
    with pytest.raises(theta_builder.TooManyCellsToAsk) as caught:
        themis.run(program(4, query))
    refused = caught.value
    assert refused.species is Asks.MORE_CELLS_THAN_ANYONE_FILLS_IN
    assert refused.details["budget"] == 8
    assert refused.details["cells"] > 8
    assert "数据行" in str(refused)


@pytest.mark.parametrize("query", [EFFECT, COUNTERFACTUAL],
                         ids=["effect", "counterfactual"])
def test_a_question_within_the_budget_is_asked_cell_by_cell(query):
    result = themis.run(program(4, query))["results"][0]
    assert result["status"] in ("needs_investigation", "counterfactual_bounded")
    assert len(result.get("missing_information") or ()) > 0


def test_the_count_refused_is_the_count_that_would_have_been_asked(monkeypatch):
    """The same list, counted before it is written out."""
    asked = len(themis.run(program(4, EFFECT))["results"][0]["missing_information"])
    monkeypatch.setattr(theta_builder, "CELLS_ASKED_AT_MOST", asked - 1)
    with pytest.raises(theta_builder.TooManyCellsToAsk) as caught:
        themis.run(program(4, EFFECT))
    assert caught.value.details["cells"] == asked
    monkeypatch.setattr(theta_builder, "CELLS_ASKED_AT_MOST", asked)
    themis.run(program(4, EFFECT))


# --------------------------------------------------------------- the page

def test_a_gateway_status_is_said_as_what_it_means():
    api = web_source.without_comments(
        web_source.read(web_source.SRC / "api.ts"))
    assert "const GATEWAY = new Set([502, 503, 504])" in api
    assert ("GATEWAY.has(res.status) ? SAYS.notAnswered : SAYS.requestFailed"
            ) in api
    assert "服务器没有在时限内回答（{status}）" in api


def test_the_font_server_does_not_hold_the_page():
    """A stylesheet for print does not block rendering; it becomes the
    screen's when it arrives. Where fonts.googleapis.com cannot be reached
    — which is where this demo's readers are — the page used to show after
    the request timed out."""
    html = (web_source.SRC.parent / "index.html").read_text(encoding="utf-8")
    link = html[html.index("fonts.googleapis.com/css2"):]
    link = link[:link.index("/>")]
    assert 'media="print"' in link
    assert "onload=\"this.media='all'\"" in link
