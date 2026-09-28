"""A table is asked for as a baseline and a ratio per condition.

When the kernel is short of a conditional distribution with several causes,
"estimate the missing numbers" asked a model for every cell of it: 2^k
numbers, each estimated alone, with nothing to keep one cause's effect the
same from cell to cell. What a model — or a person — knows of such a table
is how common the outcome is and how much each cause moves it. So a
distribution that can be is asked for that way, and comes back as the
``probability_model`` the kernel expands (#790):

- a table is a two-valued target with two conditions or more, each with
  two values or more — declared, or where undeclared the ones the kernel
  asks the table at — none of whose cells the program states; anything
  else is asked for cell by cell;
- the model is shown the table, its baseline with every condition at its
  reference — a yes-or-no condition's is its absence — and one numbered
  ratio per other value, each against the reference;
- the reply becomes a model with every parameter's reason, which the
  kernel takes through the patch loop and the audit accepts;
- a baseline at 0 or 1, a ratio that is not a positive number, a missing
  ratio or one without a reason is refused, as a cell is;
- a merged program is held to every rule a program is, so a record no
  program could have been written with is refused rather than run.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import themis
from themis.input.semantic_validator import Malformed, SemanticError
from themis.web import llm_bridge
from themis.web.bridge_words import Bridge

EACH = llm_bridge._PRIOR_TOKENS_EACH
AROUND = llm_bridge._PRIOR_TOKENS_AROUND


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _cell(target, value, given):
    return {"kind": "probability",
            "target": {"atom": _atom(target), "value": value},
            "given": [{"atom": _atom(g), "value": v} for g, v in given],
            "value": None, "annotations": {}}


DOMAINS = {"x": [True, False], "y": [True, False], "z": [True, False],
           "a": ["low", "mid", "high"]}


def _program(*extra, domains=DOMAINS):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                *({"kind": "variable", "predicate": p, "domain": d}
                  for p, d in domains.items()),
                *extra]}


def _table_rows(conditions, target="y"):
    """The cells of P(target | conditions), one target value each, as the
    kernel lists them."""
    rows = [[]]
    for c in conditions:
        rows = [r + [(c, v)] for r in rows for v in DOMAINS[c]]
    return [_cell(target, True, r) for r in rows]


class _Model:
    """Answers a table with ``baseline`` and ``ratio`` for every ratio, and
    a probability with 0.5; keeps what it was sent."""

    def __init__(self, baseline=0.2, ratio=2.0, reply=None):
        self.sent: list[dict] = []
        self.baseline, self.ratio, self.reply = baseline, ratio, reply

    def create(self, **kwargs):
        self.sent.append(kwargs)
        asked = json.loads(kwargs["messages"][0]["content"].split(
            "leave none out:\n", 1)[1])
        priors = self.reply(asked) if self.reply else [
            {"index": a["index"],
             "baseline": {"value": self.baseline, "reason": "how common"},
             "odds_ratios": [{"ratio": r["ratio"], "value": self.ratio,
                              "reason": f"effect {r['condition']}"}
                             for r in a["ratios"]]}
            if "table" in a else
            {"index": a["index"], "value": 0.5, "reason": "a cell"}
            for a in asked]
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps({"priors": priors}))])

    def asked(self, n=0):
        return json.loads(self.sent[n]["messages"][0]["content"].split(
            "leave none out:\n", 1)[1])


@pytest.fixture
def model(monkeypatch):
    m = _Model()
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=m.create)))
    return m


# ================================================================ which rows


@pytest.mark.parametrize("program, rows, tabled", [
    (_program(), _table_rows(["x", "z"]), True),
    (_program(), _table_rows(["x"]), False),
    (_program(domains={**DOMAINS, "z": None}), _table_rows(["x", "z"]), True),
    (_program(domains={**DOMAINS, "z": None}),
     [r for r in _table_rows(["x", "z"]) if r["given"][1]["value"]], False),
    (_program(domains={**DOMAINS, "y": [0, 1, 2]}), _table_rows(["x", "z"]), False),
    (_program({"kind": "probability", "value": 0.4,
               "target": {"atom": _atom("y"), "value": True},
               "given": [{"atom": _atom("x"), "value": True},
                         {"atom": _atom("z"), "value": True}]}),
     _table_rows(["x", "z"])[1:], False),
], ids=["two declared conditions", "one condition",
        "an undeclared condition asked at both values",
        "an undeclared condition asked at one value",
        "a three-valued target", "a cell the program states"])
def test_a_table_is_what_can_be_asked_for_as_one(program, rows, tabled):
    """``None`` drops a declaration, and an undeclared condition's values
    are the ones the table is asked at; the last program states one cell
    of the table, and the kernel asks for the other three."""
    for s in program["statements"]:
        if s.get("domain") is None:
            s.pop("domain", None)
    tables = llm_bridge._tables(program, rows)
    assert bool(tables) is tabled
    if tabled:
        assert list(tables) == [0] and tables[0].rows == tuple(range(len(rows)))


def test_the_model_is_shown_the_table_its_baseline_and_each_ratio(model):
    """A three-valued condition has two ratios, each against its first
    value; a yes-or-no one has one, against its absence."""
    rows = _table_rows(["a", "x"])
    llm_bridge.propose_theta_priors(_program(), rows)
    assert model.asked() == [{
        "index": 0,
        "table": "P(y | a, x)",
        "baseline": "P(y=True | a=low, x=False)",
        "ratios": [
            {"ratio": 0, "condition": "a=mid", "against": "a=low"},
            {"ratio": 1, "condition": "a=high", "against": "a=low"},
            {"ratio": 2, "condition": "x=True", "against": "x=False"},
        ],
    }]
    # Budgeted for the four numbers asked, not the six cells they replace.
    assert model.sent[0]["max_tokens"] == AROUND + 4 * EACH


def test_a_table_comes_back_as_a_model_in_the_place_of_its_rows(model):
    """Cells before and after it stay cells, in order."""
    rows = [_cell("x", True, []), *_table_rows(["x", "z"]), _cell("z", True, [])]
    out = llm_bridge.propose_theta_priors(_program(), rows)
    assert [r["kind"] for r in out] == ["probability", "probability_model",
                                        "probability"]
    table = out[1]
    assert table["provenance"] == "llm_prior"
    assert table["given"] == [{"atom": _atom("x"), "value": False},
                              {"atom": _atom("z"), "value": False}]
    assert table["baseline"] == {"value": 0.2,
                                 "annotations": {"source": "how common"}}
    assert table["odds_ratios"] == [
        {"atom": _atom(c), "value": True, "odds_ratio": 2.0,
         "annotations": {"source": f"effect {c}=True"}} for c in ("x", "z")]


def _confounded():
    """x → y with a common cause z, and no numbers: the kernel asks for
    P(z), P(x | z) and the table P(y | x, z)."""
    return _program(
        {"kind": "cause", "from": _atom("z"), "to": _atom("x"),
         "annotations": {"source": "llm_proposal"}},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y"),
         "annotations": {"source": "llm_proposal"}},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
         "annotations": {"source": "llm_proposal"}},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "target": {"atom": _atom("y"), "value": True},
            "intervention": {"atom": _atom("x"), "value": True}, "given": []}},
        domains={p: DOMAINS[p] for p in "xyz"})


def test_the_kernel_answers_from_the_model_and_the_audit_accepts_it(model):
    from themis.web import app as web_app

    program = _confounded()
    rows = web_app._probability_skeletons(themis.run(program)["results"][0])
    filled = llm_bridge.propose_theta_priors(program, rows)
    out = themis.apply_patch_and_run(program, {
        "version": "0.1", "kind": "parameter_fill_bundle", "skeletons": filled})
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    # P(y=1 | do(x=1)) = Σ_z P(z) · odds→p(0.2/0.8 · 2 · (2 if z else 1)),
    # with P(z) = 0.5 from the cell the fake answers.
    def p(odds):
        return odds / (1 + odds)
    want = 0.5 * p(0.25 * 2 * 2) + 0.5 * p(0.25 * 2)
    assert result["numeric_result"]["value"] == pytest.approx(want, abs=1e-12)
    themis.verify(out["merged_program"], result)


# ============================================================ what is refused


@pytest.mark.parametrize("reply, species", [
    (lambda a: [{"index": 0, "baseline": {"value": 1.0, "reason": "r"},
                 "odds_ratios": [{"ratio": 0, "value": 2, "reason": "r"},
                                 {"ratio": 1, "value": 2, "reason": "r"}]}],
     Bridge.A_BASELINE_IS_AT_AN_END),
    (lambda a: [{"index": 0, "baseline": {"value": 0.2, "reason": "r"},
                 "odds_ratios": [{"ratio": 0, "value": 0, "reason": "r"},
                                 {"ratio": 1, "value": 2, "reason": "r"}]}],
     Bridge.AN_ODDS_RATIO_IS_NOT_POSITIVE),
    (lambda a: [{"index": 0, "baseline": {"value": 0.2, "reason": "r"},
                 "odds_ratios": [{"ratio": 0, "value": 2, "reason": "r"}]}],
     Bridge.A_PROBABILITY_GOT_NO_PRIOR),
    (lambda a: [{"index": 0, "baseline": {"value": 0.2, "reason": "r"},
                 "odds_ratios": [{"ratio": 0, "value": 2, "reason": "r"},
                                 {"ratio": 1, "value": 2, "reason": " "}]}],
     Bridge.A_PRIOR_CAME_WITH_NO_REASON),
    (lambda a: [{"index": 0, "value": 0.3, "reason": "a cell, not a table"}],
     Bridge.A_PROBABILITY_GOT_NO_PRIOR),
], ids=["a baseline of one", "a ratio of zero", "a ratio left out",
        "a ratio with no reason", "a number where a table was asked"])
def test_a_table_answered_wrongly_is_refused(monkeypatch, reply, species):
    m = _Model(reply=reply)
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=m.create)))
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.propose_theta_priors(_program(), _table_rows(["x", "z"]))
    assert caught.value.species is species


def test_a_merged_program_is_held_to_every_rule_a_program_is():
    """A record the bundle adds is a statement once merged. Here a model
    with a parameter whose reason is blank, which ``run`` refuses in a
    program and the patch loop used to run."""
    program = _confounded()
    table = {
        "kind": "probability_model", "form": "odds_ratios",
        "provenance": "llm_prior",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": False},
                  {"atom": _atom("z"), "value": False}],
        "baseline": {"value": 0.2, "annotations": {"source": "how common"}},
        "odds_ratios": [
            {"atom": _atom("x"), "value": True, "odds_ratio": 2.0,
             "annotations": {"source": "x"}},
            {"atom": _atom("z"), "value": True, "odds_ratio": 2.0,
             "annotations": {"source": " "}}],
    }
    with pytest.raises(SemanticError) as raised:
        themis.apply_patch_and_run(program, {
            "version": "0.1", "kind": "parameter_fill_bundle",
            "skeletons": [table]})
    assert raised.value.species is Malformed.LLM_PRIOR_PARAMETER_WITHOUT_SOURCE
