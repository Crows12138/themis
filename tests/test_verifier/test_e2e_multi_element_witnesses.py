"""Witness collections with more than one element, end to end.

``test_e2e_structural_witnesses`` exists because #348 could not show itself
until a graph had two directed paths: the rule rebuilt an ordered witness from
a third traversal order and demanded positional equality, every e2e case had
exactly one path, and rule-level coverage was green throughout.

Instrumenting ``dispatch_rule`` over the 84 test modules that drive
``themis.verify`` says which other witness collections are in that state. Two
came back never once holding more than a single element, on either side:

- ``backdoor_criterion.z`` / ``backdoor_adjustment_formula.z`` — the chain-rule
  product over Z and the nested sums over it exist only at |Z| >= 2, and two
  confounders is the most ordinary graph there is.
- ``iv_wald_numeric_evaluate.instrument_conditioning`` — at |W| = 1 the
  chain-rule expansion of P(W=w) degenerates (the ``w_pairs[:i]`` prefix is
  always empty) and the Cartesian product over the strata has one factor.

Both turned out to be correct when finally asked, so these are regression pins,
not a bug fix. As in the module above, only the program is hand-written: the
result and the derivation come from ``themis.run`` and go to ``themis.verify``.
"""
from __future__ import annotations

import itertools

import pytest

import themis

OBJ = "alice"


def _var(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "var", "name": "X"}]}


def _const(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": OBJ}]}


def _cause(a: str, b: str) -> dict:
    return {"kind": "cause", "forall": ["X"], "from": _var(a), "to": _var(b)}


def _prob(target: str, value: bool, given, p: float) -> dict:
    return {
        "kind": "probability", "forall": ["X"],
        "target": {"atom": _var(target), "value": value},
        "given": [{"atom": _var(g), "value": v} for g, v in given],
        "value": p,
    }


# --------------------------------------------------------------- back-door

CONFOUNDERS = ["stress", "genetics", "diet"]


def _backdoor_program(n: int) -> dict:
    """X <- Zi -> Y for each of n confounders, plus X -> Y.

    Every confounder is a parent of both, so the adjustment set the solver
    finds has exactly n members and P(Z) factorises into n marginals.
    """
    zs = CONFOUNDERS[:n]
    stmts: list[dict] = []
    for c in zs:
        stmts += [_cause(c, "smokes"), _cause(c, "cancer")]
    stmts.append(_cause("smokes", "cancer"))
    for i, combo in enumerate(itertools.product([True, False], repeat=n)):
        stmts.append(_prob(
            "cancer", True,
            [("smokes", False)] + list(zip(zs, combo)), 0.1 + 0.1 * i,
        ))
    for c in zs:
        stmts.append(_prob(c, True, [], 0.4))
        stmts.append(_prob(c, False, [], 0.6))
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "target": {"atom": _const("cancer"), "value": True},
        "intervention": {"atom": _const("smokes"), "value": False},
        "given": [],
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": OBJ}]},
            "statements": stmts}


def _steps(result: dict) -> list[dict]:
    derivation = result.get("derivation") or {}
    return [s for s in (derivation.get("steps") or []) if isinstance(s, dict)]


def _step(result: dict, rule: str) -> dict:
    for step in _steps(result):
        if step.get("rule") == rule:
            return step
    raise AssertionError(
        f"没有 {rule} 步骤，实际链条：{[s.get('rule') for s in _steps(result)]}"
    )


def _adjustment_size(result: dict) -> int:
    return len(_step(result, "backdoor_criterion")["inputs"]["z"]["items"])


@pytest.mark.parametrize("n", [1, 2, 3])
def test_the_verifier_accepts_a_backdoor_adjustment_of_n_confounders(n):
    program = _backdoor_program(n)
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved", result.get("status")
    themis.verify(program, result)


@pytest.mark.parametrize("n,expected", [(1, 0.16), (2, 0.28), (3, 0.52)])
def test_the_adjusted_value_is_the_one_worked_out_by_hand(n, expected):
    """A sweep that only checks ``verify`` does not notice a formula that is
    self-consistently wrong on both sides."""
    result = themis.run(_backdoor_program(n))["results"][0]
    assert result["numeric_result"]["value"] == pytest.approx(expected)


def test_the_battery_reaches_a_multi_variable_adjustment_set():
    """A sweep whose adjustment set is always a singleton never touches the
    chain-rule product this module exists for, and is green either way."""
    sizes = [_adjustment_size(themis.run(_backdoor_program(n))["results"][0])
             for n in (1, 2, 3)]
    assert sizes == [1, 2, 3], f"调整集大小是 {sizes}，多变量分支没被走到"


# ------------------------------------------------- conditional instrument

def _iv_atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _iv_prob(target: str, value: bool, given, p: float) -> dict:
    return {
        "kind": "probability",
        "target": {"atom": _iv_atom(target), "value": value},
        "given": [{"atom": _iv_atom(g), "value": v} for g, v in given],
        "value": p,
    }


def _conditional_iv_program(n: int) -> dict:
    """W1..Wn -> Z and -> Y, Z -> X -> Y, X <-> Y.

    No adjustment set exists (the X <-> Y arc), and Z is an instrument only
    once every Wi is conditioned on, so the answer must come through the
    stratified Wald. The Wi are chained W1 -> W2 -> ... so that the chain-rule
    factors P(Wi | W_<i) the producer asks for are CPTs the semantic validator
    accepts — ``given`` has to be a subset of the target's structural parents.
    """
    ws = [f"w{i + 1}" for i in range(n)]
    stmts: list[dict] = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("x", "y", "z", *ws)
    ]
    for i, w in enumerate(ws):
        stmts += [{"kind": "cause", "from": _iv_atom(w), "to": _iv_atom("z")},
                  {"kind": "cause", "from": _iv_atom(w), "to": _iv_atom("y")}]
        if i:
            stmts.append({"kind": "cause",
                          "from": _iv_atom(ws[i - 1]), "to": _iv_atom(w)})
    stmts += [
        {"kind": "cause", "from": _iv_atom("z"), "to": _iv_atom("x")},
        {"kind": "cause", "from": _iv_atom("x"), "to": _iv_atom("y")},
        {"kind": "bidirected", "left": _iv_atom("x"), "right": _iv_atom("y")},
    ]
    for i, w in enumerate(ws):
        prior = ws[i - 1:i]
        for combo in itertools.product([True, False], repeat=len(prior)):
            given = list(zip(prior, combo))
            stmts.append(_iv_prob(w, True, given, 0.4))
            stmts.append(_iv_prob(w, False, given, 0.6))
    for k, combo in enumerate(itertools.product([True, False], repeat=n)):
        stratum = list(zip(ws, combo))
        drift = 0.05 * k
        stmts += [
            _iv_prob("x", True, [("z", True)] + stratum, 0.8 - drift),
            _iv_prob("x", True, [("z", False)] + stratum, 0.3 - drift),
            _iv_prob("y", True, [("z", True)] + stratum, 0.7 - drift),
            _iv_prob("y", True, [("z", False)] + stratum, 0.4 - drift),
        ]
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _iv_atom("x"), "value": True},
        "target": {"atom": _iv_atom("y"), "value": True},
        "given": [],
        "assumptions": {"monotonicity": "non_decreasing"},
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _conditioning_size(result: dict) -> int:
    step = _step(result, "iv_wald_numeric_evaluate")
    return len(step["inputs"]["instrument_conditioning"]["items"])


def _strata(result: dict) -> list[dict]:
    output = _step(result, "iv_wald_numeric_evaluate")["output"]
    return output["items"]["strata"]["items"]


@pytest.mark.parametrize("n", [1, 2])
def test_the_verifier_accepts_a_conditional_instrument_with_n_covariates(n):
    program = _conditional_iv_program(n)
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved", (
        f"条件工具没给出数：{[m.get('name') for m in (result.get('missing_information') or [])][:6]}"
    )
    themis.verify(program, result)


def test_the_battery_reaches_a_two_variable_stratification():
    """|W| = 1 leaves the chain-rule prefix empty at every step and the
    Cartesian product with a single factor — the arithmetic the producer and
    the verifier each build independently is only put to the test at |W| >= 2.
    """
    sizes, counts, widths = [], [], []
    for n in (1, 2):
        result = themis.run(_conditional_iv_program(n))["results"][0]
        sizes.append(_conditioning_size(result))
        strata = _strata(result)
        counts.append(len(strata))
        widths.append(
            {len(s["items"]["values"]["items"]) for s in strata}
        )
    assert sizes == [1, 2], f"条件集大小是 {sizes}"
    assert counts == [2, 4], f"分层数是 {counts}，笛卡尔积没展开"
    # Each stratum is indexed by a coordinate per conditioning variable; a
    # width of 1 throughout is the degenerate shape this pin exists to exclude.
    assert widths == [{1}, {2}], f"分层坐标宽度是 {widths}"
