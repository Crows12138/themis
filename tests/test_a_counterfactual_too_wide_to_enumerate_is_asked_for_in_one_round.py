"""A counterfactual too wide to enumerate is asked for in one round.

The ancestral recovery reads the joint over every ancestor of X and Y, one
row per assignment of them, through all of their tables, and where theta
lacks those tables every cell of them is an item the answer asks for. The
demo's translator drew "I majored in history; had I chosen computer science,
would I earn more?" with fourteen parents of income: 32,768 rows, a minute
and 300 MB to list what was missing and 800 MB to estimate it, past the
400 MB the demo gives a process.

Past 4,096 rows the route is not taken, and the joint is read off the chain
rule's two marginals. That route named one factor per round — ``P(X)``, and
only once it was in, ``P(Y | X)`` — and the door returned at the joint's
shortfall before asking for the risk's, which its sibling, the probabilities
of causation, stopped doing when it learned that returning at the first
shortfall hides the other. The history major took three rounds of answering
before it had a number.

Pinned here:

- the bound: at 4,096 rows the ancestral route is taken and one variable
  more it is not; the verifier's bound is the producer's;
- past it, the first run asks for everything the answer needs, the chain
  rule's factors and the risk's beside them, and answering that with one
  distribution's numbers gives that distribution's answer, which the
  verifier accepts — for a counterfactual cell and for the probabilities of
  causation;
- the risk is not asked for beside the joint where the cell does not
  depend on it (monotonicity pins it), and not where the joint's shortfall
  is the ancestors' tables, from which it follows;
- the fourteen-parent shape lists a few dozen items, not thousands.
"""
from __future__ import annotations

import copy
import random
from itertools import product

import pytest

import themis
from themis.runtime import scheduler
from themis.verifier import rules


def _a(name):
    return {"predicate": name, "args": []}


class _Model:
    """A binary model: ``k`` confounders of x and y, ``m`` roots into y
    alone, perhaps a mediator, CPTs drawn from ``seed``."""

    def __init__(self, m, k, seed, *, mediator=False):
        rng = random.Random(seed)
        self.roots = [f"r{i}" for i in range(m)]
        self.confounders = [f"c{i}" for i in range(k)]
        self.parents = {v: [] for v in self.roots + self.confounders}
        self.parents["x"] = list(self.confounders)
        if mediator:
            self.parents["w"] = ["x"]
            self.parents["y"] = ["w"] + self.confounders + self.roots
        else:
            self.parents["y"] = ["x"] + self.confounders + self.roots
        self.order = self.confounders + self.roots + ["x"] + (
            ["w"] if mediator else []) + ["y"]
        self.cpt = {v: {row: round(rng.uniform(0.15, 0.85), 3)
                        for row in product((True, False),
                                           repeat=len(self.parents[v]))}
                    for v in self.order}
        self._joint = self._rows()

    def _rows(self, fixed=None):
        out = {}
        for row in product((True, False), repeat=len(self.order)):
            a = dict(zip(self.order, row))
            if fixed and any(a[n] != v for n, v in fixed.items()):
                continue
            p = 1.0
            for v in self.order:
                if fixed and v in fixed:
                    continue
                q = self.cpt[v][tuple(a[u] for u in self.parents[v])]
                p *= q if a[v] else 1 - q
            out[row] = p
        return out

    def _p(self, rows, pairs):
        idx = [(self.order.index(n), v) for n, v in pairs]
        return sum(p for row, p in rows.items()
                   if all(row[i] == v for i, v in idx))

    def conditional(self, target, value, given):
        return (self._p(self._joint, list(given) + [(target, value)])
                / self._p(self._joint, given))

    def risk(self, x_value):
        return self._p(self._rows({"x": x_value}), [("y", True)])

    def edges(self):
        return [(u, v) for v in self.order for u in self.parents[v]]


def _program(model, query, *, bidirected=()):
    body = [{"kind": "variable", "predicate": v} for v in model.order]
    body += [{"kind": "cause", "from": _a(u), "to": _a(v)}
             for u, v in model.edges()]
    body += [{"kind": "bidirected", "left": _a(u), "right": _a(v)}
             for u, v in bidirected]
    body.append({"kind": "query", "id": "q", "query": query})
    return {"version": "0.1", "domain": {"objects": []}, "statements": body}


def _counterfactual(observed=True, intervention=False, *, factual=None,
                    monotonicity=None):
    query = {"kind": "counterfactual",
             "observed": {"atom": _a("x"), "value": observed},
             "counterfactual_intervention": {"atom": _a("x"),
                                             "value": intervention},
             "counterfactual_target": {"atom": _a("y"), "value": True}}
    if factual is not None:
        query["factual_target_known"] = factual
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    return query


CAUSATION = {"kind": "causation", "cause": _a("x"), "effect": _a("y"),
             "monotonic": False}


def _asked(result):
    return [item["skeleton"]
            for request in result.get("investigation_requests") or ()
            for item in request.get("items") or ()
            if (item.get("skeleton") or {}).get("kind") == "probability"]


def _conditions(stub):
    return {g["atom"]["predicate"] for g in stub["given"]}


def _answered(program, model, asked):
    program = copy.deepcopy(program)
    for stub in asked:
        filled = copy.deepcopy(stub)
        filled["value"] = model.conditional(
            stub["target"]["atom"]["predicate"], stub["target"]["value"],
            [(g["atom"]["predicate"], g["value"]) for g in stub["given"]])
        filled["annotations"] = {"source": "a study"}
        program["statements"].insert(-1, filled)
    return program


def _run(program):
    return themis.run(copy.deepcopy(program))["results"][0]


# --- the bound ---------------------------------------------------------------

def test_the_verifier_s_bound_is_the_producer_s():
    assert (rules._ANCESTRAL_ROWS_AT_MOST_FOR_VERIFIER
            == scheduler._ANCESTRAL_ROWS_AT_MOST == 4096)


@pytest.mark.parametrize("m, ancestral", [(9, True), (10, False)])
def test_at_the_bound_the_ancestors_are_read_and_past_it_they_are_not(
        m, ancestral):
    """x, y, one confounder and ``m`` roots: 2**(m + 3) rows."""
    model = _Model(m, 1, seed=m)
    asked = _asked(_run(_program(model, _counterfactual())))
    reads_a_root = any(_conditions(s) & set(model.roots) for s in asked)
    assert reads_a_root is ancestral, [s["target"] for s in asked]


# --- one round ---------------------------------------------------------------

@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("k, mediator", [(0, False), (1, False), (2, False),
                                         (2, True)])
def test_past_the_bound_one_round_of_answers_reaches_the_cell(k, mediator,
                                                                  seed):
    model = _Model(11 - k, k, seed=100 * k + seed, mediator=mediator)
    observed = seed % 2 == 0
    program = _program(model, _counterfactual(observed, not observed))
    first = _run(program)
    asked = _asked(first)
    assert asked and not any(_conditions(s) & set(model.roots)
                             for s in asked)
    program = _answered(program, model, asked)
    result = _run(program)
    assert not _asked(result), [s["target"] for s in _asked(result)]
    assert result["status"] == "counterfactual_solved", result["status"]
    risk = model.risk(not observed)
    joint = model.conditional("y", True, [("x", not observed)]) * \
        model.conditional("x", not observed, [])
    p_x = model.conditional("x", observed, [])
    assert result["numeric_result"]["value"] == pytest.approx(
        (risk - joint) / p_x, abs=1e-9)
    themis.verify(copy.deepcopy(program), result)


@pytest.mark.parametrize("seed", range(3))
def test_past_the_bound_the_probabilities_of_causation_take_one_round(seed):
    model = _Model(9, 2, seed=seed)
    program = _program(model, CAUSATION)
    program = _answered(program, model, _asked(_run(program)))
    result = _run(program)
    assert not _asked(result)
    assert result["status"] == "counterfactual_bounded", result["status"]
    themis.verify(copy.deepcopy(program), result)


# --- where the risk is not asked for beside the joint ----------------------

def test_a_cell_monotonicity_pins_asks_only_for_the_joint():
    """x=1 observed with y=0 under a non-decreasing effect forces Y_0 = 0:
    the cell is answered without the risk, so its tables are not asked."""
    model = _Model(9, 2, seed=7)
    program = _program(model, _counterfactual(
        True, False, factual=False, monotonicity="non_decreasing"))
    asked = _asked(_run(program))
    assert {s["target"]["atom"]["predicate"] for s in asked} <= {"x", "y"}
    assert all(_conditions(s) <= {"x"} for s in asked), asked


def test_within_the_bound_the_risk_follows_from_the_ancestors_tables():
    """The ancestors' tables are the graph's own account, and the risk is
    read off them once they are in; asking for a coarser table of y beside
    y's own would be two numbers for one quantity."""
    model = _Model(3, 2, seed=11)
    asked = _asked(_run(_program(model, _counterfactual())))
    into_y = {frozenset(_conditions(s)) for s in asked
              if s["target"]["atom"]["predicate"] == "y"}
    assert into_y == {frozenset(model.parents["y"])}, into_y


# --- the shape that raised it ------------------------------------------------

def test_fourteen_parents_of_the_outcome_list_a_few_dozen_items():
    """Five confounders, eight roots and x: the ancestral recovery would
    list every cell of a table over fourteen parents."""
    model = _Model(8, 5, seed=3)
    asked = _asked(_run(_program(model, _counterfactual(False, True))))
    assert 0 < len(asked) <= 2 ** 5 + 5 + 3, len(asked)
