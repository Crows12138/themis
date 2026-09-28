"""A table is asked for as a baseline and a ratio per condition.

When the kernel is short of a conditional distribution with several causes,
"estimate the missing numbers" asked a model for every cell of it: 2^k
numbers, each estimated alone, with nothing to keep one cause's effect the
same from cell to cell. What a model — or a person — knows of such a table
is how common the outcome is and how much each cause moves it. So a
distribution that can be is asked for that way, and comes back as the
``probability_model`` the kernel expands (#790):

- a table is the rows of one target value, or of a target with two, under
  two conditions or more, each with two values or more — declared; where
  undeclared, a yes-or-no's two if it is asked at true or false, as the
  kernel asks the condition a question sets; else the ones the kernel asks
  the table at — none of whose cells the program states; anything else is
  asked for cell by cell;
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
import math
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


def _table_rows(conditions, target="y", value=True):
    """The cells of P(target=value | conditions), as the kernel lists them."""
    rows = [[]]
    for c in conditions:
        rows = [r + [(c, v)] for r in rows for v in DOMAINS[c]]
    return [_cell(target, value, r) for r in rows]


THREE_LEVELS = {**DOMAINS, "y": ["low", "mid", "high"]}


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
     [r for r in _table_rows(["x", "z", "a"]) if r["given"][1]["value"]], True),
    (_program(domains={**DOMAINS, "z": None}),
     [_cell("y", True, [("x", x), ("z", "often"), ("a", a)])
      for x in DOMAINS["x"] for a in DOMAINS["a"]], False),
    (_program(domains=THREE_LEVELS), _table_rows(["x", "z"], value="high"), True),
    (_program(domains=THREE_LEVELS),
     _table_rows(["x", "z"], value="high") + _table_rows(["x", "z"], value="mid"),
     False),
    (_program(domains={**DOMAINS, "y": None}),
     _table_rows(["x", "z"], value="a") + _table_rows(["x", "z"], value="b"),
     False),
    (_program(), _table_rows(["x", "z"]) + _table_rows(["x", "z"], value=False),
     True),
    (_program(), _table_rows(["x", "z"])[:3], False),
    (_program({"kind": "probability", "value": 0.4,
               "target": {"atom": _atom("y"), "value": True},
               "given": [{"atom": _atom("x"), "value": True},
                         {"atom": _atom("z"), "value": True},
                         {"atom": _atom("a"), "value": "low"}]}),
     _table_rows(["x", "z", "a"])[1:], False),
], ids=["two declared conditions", "one condition",
        "an undeclared condition asked at both values",
        "an undeclared condition asked at one yes-or-no value",
        "an undeclared condition asked at one other value",
        "a three-valued target asked at one value",
        "a three-valued target asked at two values",
        "an undeclared target asked at two values that are not yes-or-no",
        "a two-valued target asked at both values",
        "as many numbers as the rows",
        "a cell the program states"])
def test_a_table_is_what_can_be_asked_for_as_one(program, rows, tabled):
    """``None`` drops a declaration. An undeclared condition asked at true
    or false is a yes-or-no, as an undeclared target is, and one asked at
    anything else takes the values it is asked at. A model states the
    target value it names and, where there is one other, that one; so rows
    of two target values are a table only where those are the target's
    two. Three rows of a table of two yes-or-no conditions are three
    numbers either way. The last program states one cell of the table, and
    the kernel asks for the other eleven."""
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
    assert table["llm_prior"] is True and "provenance" not in table
    assert table["given"] == [{"atom": _atom("x"), "value": False},
                              {"atom": _atom("z"), "value": False}]
    assert table["baseline"] == {"value": 0.2,
                                 "annotations": {"source": "how common"}}
    assert table["odds_ratios"] == [
        {"atom": _atom(c), "value": True, "odds_ratio": 2.0,
         "annotations": {"source": f"effect {c}=True"}} for c in ("x", "z")]


def _confounded(domains=None, outcome=True, confounders=("z",)):
    """x → y with common causes, and no numbers: the kernel asks for each
    cause's marginal and the table P(y=outcome | x, causes), at the value
    do(x) sets x to."""
    edges = [("x", "y"), *((c, t) for c in confounders for t in ("x", "y"))]
    return _program(
        *({"kind": "cause", "from": _atom(a), "to": _atom(b),
           "annotations": {"source": "llm_proposal"}} for a, b in edges),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "target": {"atom": _atom("y"), "value": outcome},
            "intervention": {"atom": _atom("x"), "value": True}, "given": []}},
        domains=domains or {p: DOMAINS[p] for p in "xyz"})


CAUSES = ("z", "w", "v")
YES_OR_NO = [True, False]


@pytest.mark.parametrize("domains, outcome", [
    ({p: YES_OR_NO for p in ("x", "y", *CAUSES)}, True),
    ({p: YES_OR_NO for p in ("y", *CAUSES)}, True),
    ({"y": ["low", "mid", "high"], **{p: YES_OR_NO for p in ("x", *CAUSES)}},
     "high"),
], ids=["declared", "an exposure declaring no values",
        "an outcome with three values"])
def test_the_kernel_answers_from_the_model_and_the_audit_accepts_it(
        model, domains, outcome):
    """The kernel asks the table at the one value do(x) sets x to: eight
    rows over three common causes, where the table is five numbers. An
    exposure that declares no values is a yes-or-no condition of it all the
    same; an outcome with three values is asked at the one the question
    names, and the model is the probability of that value."""
    from themis.web import app as web_app

    program = _confounded(domains, outcome, CAUSES)
    rows = web_app._probability_skeletons(themis.run(program)["results"][0])
    filled = llm_bridge.propose_theta_priors(program, rows)
    assert [r["kind"] for r in filled].count("probability_model") == 1
    out = themis.apply_patch_and_run(program, {
        "version": "0.1", "kind": "parameter_fill_bundle", "skeletons": filled})
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    # P(y | do(x)) = Σ_c P(c) · odds→p(0.2/0.8 · 2 · 2^(causes present)),
    # each cause present with the 0.5 the fake answers a cell with.
    def p(odds):
        return odds / (1 + odds)
    want = sum(p(0.25 * 2 * 2 ** k) * math.comb(3, k) / 8 for k in range(4))
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
        "llm_prior": True,
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
