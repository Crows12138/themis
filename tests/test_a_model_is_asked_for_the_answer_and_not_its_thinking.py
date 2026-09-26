"""A model is asked for the answer, and not for its thinking first.

Every call the bridge makes budgets ``max_tokens`` for the answer and reads
only its text blocks. DeepSeek's model thinks unless told not to, and its
thinking counts against the same budget: on the demo server two of the five
worked examples came back with no JSON, and two more with an empty reading,
each call stopping at its budget with the answer unwritten. With thinking
off the same five all came back whole (#779).

The provider's default is not this module's to rely on, so the one place
the bridge speaks to a model says it.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from themis.web import llm_bridge

NO_THINKING = {"type": "disabled"}


def _message(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _Recording:
    """A client whose ``messages.create`` keeps what each call was sent."""

    def __init__(self, reply: str):
        self.sent: list[dict] = []
        self.base_url = "http://stub.invalid"

        def create(**kwargs):
            self.sent.append(kwargs)
            return _message(reply)

        self.messages = SimpleNamespace(create=create)


def test_the_one_call_says_no_thinking():
    client = _Recording("x")
    llm_bridge._ask_model(client, model="m", max_tokens=10, messages=[])
    assert client.sent == [
        {"thinking": NO_THINKING, "model": "m", "max_tokens": 10,
         "messages": []}]


def test_a_caller_cannot_ask_for_thinking_past_it():
    """Saying it once means no call site says otherwise."""
    with pytest.raises(TypeError):
        llm_bridge._ask_model(_Recording("x"), model="m",
                              thinking={"type": "enabled"})


def _translate(client):
    llm_bridge.nl_to_kernel_ast("x 会导致 y 吗")


def _read_back(client):
    llm_bridge.render_reply({"program": {}, "results": []}, nl="x")


def _propose(client):
    llm_bridge.propose_theta_priors(
        {"version": "0.1"},
        [{"kind": "probability",
          "target": {"atom": {"predicate": "y", "args": []}, "value": True},
          "given": [], "value": None, "annotations": {}}])


REPLIES = {
    _translate: json.dumps({"version": "0.1", "domain": {"objects": []},
                            "statements": []}),
    _read_back: "a reading",
    _propose: json.dumps({"priors": [
        {"index": 0, "value": 0.5, "reason": "r"}]}),
}


@pytest.mark.parametrize("door", list(REPLIES), ids=lambda d: d.__name__)
def test_each_surface_that_calls_a_model_arrives_without_thinking(
        monkeypatch, door):
    client = _Recording(REPLIES[door])
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: client)
    door(client)
    assert client.sent, "the surface never called the model"
    assert all(kw["thinking"] == NO_THINKING for kw in client.sent)
