"""A reply cut off at its budget says so.

Every call to a model carries a budget, ``max_tokens``, and a reply that
reaches it is cut off there, mid-sentence or mid-program. The bridge read
such a reply like any other: a program cut off is JSON whose braces never
close, taken for a slip and asked for again within the same budget. On the
demo's model one everyday question's program came back cut off at 4,000
tokens nine times running, three writes of three attempts each, and the
person waiting was told the model's JSON never closed.

The budget a program was given dated from graphs of three or four
variables. A graph drawn from the list of variables to consider carries
fifteen to twenty, and its program measured up to 3,905 tokens there.

So a reply cut off at its budget is raised where replies come back, as what
it is and with the budget it ran past, and is not read as JSON; and a
program is given a budget sized for the graphs it is now asked to draw.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from themis.web import llm_bridge
from themis.web.bridge_words import Bridge

QUESTION = "吸烟会导致肺癌吗"
CUT = '{"version": "0.1", "statements": [{"kind": "variable", "predicate": "x'


def _reply(text: str, stop_reason: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                           stop_reason=stop_reason)


class _Model:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list[dict] = []
        self.base_url = "http://stub.invalid"
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


@pytest.fixture
def model(monkeypatch):
    def install(reply):
        stub = _Model(reply)
        monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
        return stub
    return install


def test_a_program_cut_off_at_its_budget_is_said_to_be_and_not_read(model):
    stub = model(_reply(CUT, "max_tokens"))
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.nl_to_kernel_ast(QUESTION)
    assert caught.value.species is Bridge.THE_REPLY_RAN_PAST_ITS_BUDGET
    [call] = stub.calls
    assert caught.value.said["budget"] == str(call["max_tokens"])


def test_json_that_never_closes_before_the_budget_is_still_a_slip(model):
    """A reply that ended of its own accord is read as it was: its braces
    not closing is the model's slip, and a fresh one is asked for."""
    stub = model(_reply(CUT, "end_turn"))
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.nl_to_kernel_ast(QUESTION, max_attempts=3)
    assert caught.value.species is Bridge.THE_JSON_NEVER_CLOSES
    assert len(stub.calls) == 3


def _listing():
    return llm_bridge.variables_to_consider(QUESTION)


def _reply_to_a_run():
    return llm_bridge.render_reply({"results": []}, nl=QUESTION)


@pytest.mark.parametrize("ask", [_listing, _reply_to_a_run])
def test_every_call_that_reaches_its_budget_says_so(model, ask):
    """The listing and the written reply as much as the program: a reply
    cut off at its budget is not shown or read as if it were whole."""
    model(_reply("被截断的", "max_tokens"))
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        ask()
    assert caught.value.species is Bridge.THE_REPLY_RAN_PAST_ITS_BUDGET


def test_a_program_is_given_room_for_the_graphs_it_is_asked_to_draw(model):
    """Fifteen to twenty variables, up to 3,905 tokens measured."""
    stub = model(_reply(json.dumps({"version": "0.1", "statements": []}), "end_turn"))
    llm_bridge.nl_to_kernel_ast(QUESTION)
    assert stub.calls[0]["max_tokens"] >= 4 * 3_905
