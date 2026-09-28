"""A long list of priors is asked for in parts, each part budgeted for itself.

"Estimate the missing numbers" asks a model for a prior for each
probability the kernel is short of, and it asked in one call with a fixed
budget of 2000 output tokens. On deepseek-v4-pro a prior and its reason
take about 35 (52 came back in 1826), so the call ran out at about 55 —
and a graph drawn with every common cause of its outcome needs that many
at five common causes of an attribution question, or six of an effect
question, because what the kernel asks for doubles with each (#783).

What is held:

- a call's budget is sized to the rows it carries;
- a long list goes out in parts, and the rows one distribution is made of
  — the values of one variable under one condition, which must sum to
  one — are never split between two of them;
- every row is asked for once and filled from the reply to the call that
  asked for it, so an index a reply strays onto does not stand in for a
  row another call was asked;
- a list that would take more calls than the bridge makes at once is
  refused before any model is asked, with the count, in the reader's
  words;
- a real attribution question with five common causes, 101 rows, is
  filled end to end through ``/api/assume`` and answered — asked for, now
  that its two large distributions are tables (#791), as 18 numbers in one
  call.

The long lists below are the marginals of as many variables, each a
distribution of one row with no condition, so none is a table: every row
is a cell, and the packing is what is under test.
"""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import themis
from themis.web import app as web_app
from themis.web import llm_bridge
from themis.web.bridge_words import Bridge

EACH = llm_bridge._PRIOR_TOKENS_EACH
AROUND = llm_bridge._PRIOR_TOKENS_AROUND
PER_CALL = llm_bridge._PRIORS_PER_CALL
AT_MOST = llm_bridge._PRIOR_CALLS_AT_MOST


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _row(target, value, given):
    return {"kind": "probability",
            "target": {"atom": _atom(target), "value": value},
            "given": [{"atom": _atom(g), "value": v} for g, v in given],
            "value": None, "annotations": {}}


def _cells(n):
    """``n`` one-row distributions: P(v<i>=True)."""
    return [_row(f"v{i}", True, []) for i in range(n)]


def _rows_in(kwargs):
    content = kwargs["messages"][0]["content"]
    return [r["index"] for r in json.loads(content.split("leave none out:\n", 1)[1])]


class _Model:
    """A model that answers each row it is asked for with ``index / 10000``,
    and keeps what every call was sent. Each reply also carries the rows of
    ``stray`` it was NOT asked for."""

    def __init__(self, stray=()):
        self.sent: list[dict] = []
        self.lock = threading.Lock()
        self.stray = list(stray)

    def create(self, **kwargs):
        with self.lock:
            self.sent.append(kwargs)
        rows = _rows_in(kwargs)
        priors = [{"index": i, "value": i / 10000, "reason": f"r{i}"}
                  for i in rows] + [p for p in self.stray if p["index"] not in rows]
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps({"priors": priors}))])


@pytest.fixture
def model(monkeypatch):
    m = _Model()
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=m.create)))
    return m


def test_a_call_s_budget_is_sized_to_the_rows_it_carries(model):
    llm_bridge.propose_theta_priors({"version": "0.1"}, _cells(3))
    llm_bridge.propose_theta_priors({"version": "0.1"}, _cells(PER_CALL))
    budgets = [kw["max_tokens"] for kw in model.sent]
    assert budgets == [AROUND + 3 * EACH, AROUND + PER_CALL * EACH]
    # The fixed budget this replaces ran out at about 55 rows.
    assert budgets[1] > 2000


def test_a_long_list_is_asked_for_in_parts_and_filled_from_each(model):
    """As few parts as the list needs, about even — the calls run side by
    side, so the reader waits for the largest."""
    n = 2 * PER_CALL + 7
    out = llm_bridge.propose_theta_priors({"version": "0.1"}, _cells(n))
    asked = [_rows_in(kw) for kw in model.sent]
    sizes = [len(rows) for rows in asked]
    assert len(sizes) == 3 and max(sizes) - min(sizes) <= 1
    assert sorted(i for rows in asked for i in rows) == list(range(n))
    assert [s["value"] for s in out] == [i / 10000 for i in range(n)]
    assert all(s["provenance"] == "llm_prior" for s in out)


@pytest.mark.parametrize("before", range(0, 2 * PER_CALL, 7))
def test_one_distribution_is_never_split_between_two_calls(before):
    """Three levels of one variable under one condition sum to one, so the
    reply that writes one of them writes all three — wherever in the list
    they fall."""
    levels = [_row("mood", level, [("x", True)]) for level in ("低", "中", "高")]
    skeletons = _cells(before) + levels + _cells(2 * PER_CALL - before)
    calls = llm_bridge._prior_calls(skeletons)
    level_rows = {before, before + 1, before + 2}
    assert sum(1 for rows in calls if level_rows & set(rows)) == 1
    assert all(len(rows) <= PER_CALL for rows in calls)
    assert sorted(i for rows in calls for i in rows) == list(range(len(skeletons)))


def test_an_index_a_reply_strays_onto_does_not_fill_another_call_s_row(
        monkeypatch):
    """Each part's reply also offers a value for the other part's row, and
    arrives in whichever order the calls finish."""
    stray = [{"index": i, "value": 0.99, "reason": "not asked here"}
             for i in (0, PER_CALL)]
    m = _Model(stray=stray)
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=m.create)))
    out = llm_bridge.propose_theta_priors({"version": "0.1"}, _cells(PER_CALL + 1))
    assert len(m.sent) == 2
    for i in (0, PER_CALL):
        assert out[i]["value"] == i / 10000
        assert out[i]["annotations"]["source"] == f"r{i}"


def test_more_than_the_bridge_asks_for_at_once_is_refused_before_asking(model):
    needed = PER_CALL * AT_MOST + 1
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.propose_theta_priors({"version": "0.1"}, _cells(needed))
    assert caught.value.species is Bridge.TOO_MANY_PRIORS_TO_ASK_FOR
    assert caught.value.said["needed"] == str(needed)
    assert caught.value.said["most"] == str(PER_CALL * AT_MOST)
    assert model.sent == []


def _attribution_with_common_causes(k):
    names = [f"c{i}" for i in range(k)]
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in ["x", "y", *names]]
    edges = [("x", "y"), *((c, t) for c in names for t in ("x", "y"))]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b),
                    "annotations": {"source": "llm_proposal"}} for a, b in edges]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "causation", "cause": _atom("x"), "effect": _atom("y")}})
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def test_an_attribution_question_with_five_common_causes_is_answered(model):
    """101 rows, where one call ran out. Two distributions hold 96 of them —
    y under x and the five causes, x under the five — and each is asked for
    as a baseline and a ratio per cause, so the model is asked for 18
    numbers in one call, and the kernel answers."""
    program = _attribution_with_common_causes(5)
    rows = web_app._probability_skeletons(themis.run(program)["results"][0])
    assert len(rows) == 101

    # A value the kernel can use in every row: the fake's index / 10000 would
    # leave some P(y | ...) at zero, which is a legal but degenerate answer.
    def create(**kwargs):
        with model.lock:
            model.sent.append(kwargs)
        content = kwargs["messages"][0]["content"]
        asked = json.loads(content.split("leave none out:\n", 1)[1])
        priors = [
            {"index": r["index"],
             "baseline": {"value": 0.2, "reason": f"b{r['index']}"},
             "odds_ratios": [{"ratio": x["ratio"], "value": 1.5,
                              "reason": f"or{x['ratio']}"} for x in r["ratios"]]}
            if "table" in r else
            {"index": r["index"], "value": 0.3 + (r["index"] % 5) / 10,
             "reason": f"r{r['index']}"}
            for r in asked]
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps({"priors": priors}))])

    model.create = create
    r = TestClient(web_app.app).post("/api/assume", json={"program": program})
    assert r.status_code == 200, r.text
    assert len(model.sent) == 1
    assert model.sent[0]["max_tokens"] == AROUND + 18 * EACH
    result = r.json()["results"][0]
    assert result["status"] == "counterfactual_bounded"
    review = result["extensions"]["llm_proposed_review"]
    assert len(review["probabilities"]) == 18
    assert sorted(m["distribution"] for m in review["models"]) == [
        "P(x | c0, c1, c2, c3, c4)", "P(y | c0, c1, c2, c3, c4, x)"]
