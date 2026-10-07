"""A variable's declared domain names at least two values.

The runtime reads a declared domain as the values a variable takes, and sums
over it wherever a formula sums over the variable. The schema asked only for
a list. The demo's model, told to omit ``domain`` for quantities such as age
and income, wrote ``"domain": []`` for three confounders of "does staying up
late often make you duller?", and the back-door sum over them ran over
nothing: the answer came back ``numerically_solved`` with an effect of 0.0
from a program holding no number at all, and the reply explained the zero
as what an empty formula multiplies out to. A list of one value is the same
defect by a smaller margin — it leaves every other value's share out of the
sum — and a list naming one value twice is a list of one.

Pinned here:

- a declared domain of none, one or a repeated value is refused, and the
  refusal says which statement's ``domain`` and why;
- the shape that raised it is refused rather than answered, and the same
  program with the field omitted runs;
- at the door, a program written with an empty domain goes back to the model
  with that refusal, and the mended program answers.
"""
from __future__ import annotations

import json

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError
from themis.web import llm_bridge

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from themis.web import app as app_module  # noqa: E402
from tests.test_a_program_the_kernel_refuses_is_handed_back_with_the_refusal import (  # noqa: E402
    _Model, _refused_turn)


def _a(name):
    return {"predicate": name, "args": [{"type": "const", "name": "me"}]}


def _program(z_domain=None):
    """z confounds x and y; no numbers anywhere."""
    z = {"kind": "variable", "predicate": "z", "name": {"zh": "丙"}}
    if z_domain is not None:
        z["domain"] = z_domain
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "x", "domain": [True, False],
                 "name": {"zh": "甲"}},
                {"kind": "variable", "predicate": "y", "domain": [True, False],
                 "name": {"zh": "乙"}},
                z,
                {"kind": "cause", "from": _a("z"), "to": _a("x")},
                {"kind": "cause", "from": _a("z"), "to": _a("y")},
                {"kind": "cause", "from": _a("x"), "to": _a("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect", "given": [],
                    "intervention": {"atom": _a("x"), "value": True},
                    "target": {"atom": _a("y"), "value": True}}},
            ]}


@pytest.mark.parametrize("domain, why", [
    ([], "is too short"),
    ([True], "is too short"),
    (["low"], "is too short"),
    ([True, True], "has non-unique elements"),
])
def test_a_domain_of_fewer_than_two_values_is_refused(domain, why):
    with pytest.raises(SyntacticError) as caught:
        themis.run(_program(domain))
    assert f"statements/2/domain: {domain!r} {why}" in str(caught.value)


def test_an_empty_confounder_is_refused_rather_than_answered_as_zero():
    """What it answered before: numerically_solved, 0.0, no number given."""
    with pytest.raises(SyntacticError):
        themis.run(_program([]))
    result = themis.run(_program())["results"][0]
    assert result["status"] == "needs_investigation"
    assert result.get("numeric_result") is None


@pytest.mark.parametrize("domain", [[True, False], ["low", "mid", "high"], [0, 1]])
def test_two_values_or_more_are_a_domain(domain):
    assert themis.run(_program(domain))["results"][0]["status"] == "needs_investigation"


def test_at_the_door_the_empty_domain_goes_back_and_the_mended_program_answers(monkeypatch):
    stub = _Model(json.dumps(_program([])), json.dumps(_program()), "回答")
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
    r = TestClient(app_module.app).post("/api/ask", json={"nl": "经常熬夜会变笨吗", "lang": "zh"})
    assert r.status_code == 200, r.text
    assert r.json()["kernel_ast"] == _program()
    assert "statements/2/domain: [] is too short" in _refused_turn(stub.sent[1])
