"""An atom the question names is not free wherever it appears.

``P(Y | do(X), Z)`` is identified as a ratio: ``ID(Y∪Z_rem, X')`` over
``ID(Z_rem, X')``. Y is what the question asks about, so in the NUMERATOR
its occurrences are the reader's — bound to the value the query names. In
the DENOMINATOR Y is not asked about at all; it is summed away, and the ID
recursion writes a ``Σ_y`` whose variable those same occurrences carry.

Two roles, one atom. A stamping pass that decides "free or not" by asking
which atom this is answers the numerator's question in the denominator: it
overwrites the sum's variable with the query's value, and what is left is a
sum whose body no longer mentions the thing it sums over. The denominator
becomes |dom(Y)| copies of the numerator and the whole ratio collapses to
1/|dom(Y)| — a confident number about nothing, on a graph where every
variable is observed.

What decides the question is not the atom but the position: an occurrence
is free when no enclosing sum holds its name. The graph below is the
smallest one where the two answers differ — conditioning on a collider W
that Y causes, so the denominator must genuinely marginalize Y — and its
truth is hand-computable from the truncated factorization.
"""
from __future__ import annotations

import itertools

import pytest

import themis
from themis.runtime.c_factor import _apply_idc_values
from themis.types import (
    Atom,
    BindDecl,
    ConstTerm,
    ProbabilityRefExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)

_B = (True, False)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


# ---------------------------------------------------------------------------
# Z→X, Z→Y, X→Y, X→W, Y→W.  Everything observed, so the observational
# conditionals ARE the mechanisms and P(z,y,w | do(x)) = P(z)P(y|z,x)P(w|x,y).
# ---------------------------------------------------------------------------

_pZ1 = 0.3


def _pY1(zv, xv):
    return 0.2 + 0.5 * xv + 0.2 * zv


def _pW1(xv, yv):
    return 0.1 + 0.4 * xv + 0.4 * yv


def _truth(wv: bool) -> float:
    """P(Y=1 | do(X=1), W=wv) by the truncated factorization."""
    def joint(zv, yv):
        pz = _pZ1 if zv else 1 - _pZ1
        py = _pY1(int(zv), 1)
        pw = _pW1(1, int(yv))
        return (pz * (py if yv else 1 - py) * (pw if wv else 1 - pw))

    num = sum(joint(zv, True) for zv in _B)
    den = sum(joint(zv, yv) for zv in _B for yv in _B)
    return num / den


def _prob(target, tv, given, value):
    return {"kind": "probability",
            "target": {"atom": _atom(target), "value": tv},
            "given": [{"atom": _atom(p), "value": v} for p, v in given],
            "value": value}


def _program(wv: bool) -> dict:
    statements = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("z", "x", "y", "w")
    ] + [
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("w")},
        {"kind": "cause", "from": _atom("y"), "to": _atom("w")},
    ]
    for zv in _B:
        statements.append(_prob("z", zv, [], _pZ1 if zv else 1 - _pZ1))
    for zv, xv, yv in itertools.product(_B, _B, _B):
        p1 = _pY1(int(zv), int(xv))
        statements.append(
            _prob("y", yv, [("z", zv), ("x", xv)], p1 if yv else 1 - p1))
    for xv, yv, wv_ in itertools.product(_B, _B, _B):
        p1 = _pW1(int(xv), int(yv))
        statements.append(
            _prob("w", wv_, [("x", xv), ("y", yv)], p1 if wv_ else 1 - p1))
    statements.append({
        "kind": "query", "id": "q",
        "query": {"kind": "effect",
                  "intervention": {"atom": _atom("x"), "value": True},
                  "target": {"atom": _atom("y"), "value": True},
                  "given": [{"atom": _atom("w"), "value": wv}]}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _answer(wv: bool):
    return themis.run(_program(wv))["results"][0]


def _sums(node):
    kind = node.get("kind")
    if kind == "sum":
        yield node
        yield from _sums(node["body"])
    elif kind == "product":
        for term in node["terms"]:
            yield from _sums(term)
    elif kind == "fraction":
        yield from _sums(node["numerator"])
        yield from _sums(node["denominator"])


def _bound_to(node, name):
    """The predicates this subtree gives the value ``VarRef(name)``."""
    kind = node.get("kind")
    out = set()
    if kind == "probability_ref":
        for valued in (node["target"],) + tuple(node.get("given") or ()):
            value = valued.get("value")
            if isinstance(value, dict) and value.get("name") == name:
                out.add(valued["atom"]["predicate"])
    elif kind == "product":
        for term in node["terms"]:
            out |= _bound_to(term, name)
    elif kind == "sum":
        out |= _bound_to(node["body"], name)
    elif kind == "fraction":
        out |= _bound_to(node["numerator"], name)
        out |= _bound_to(node["denominator"], name)
    return out


def test_the_conditional_on_a_collider_matches_the_truncated_factorization():
    """The number, against a truth computed outside this system."""
    for wv in _B:
        result = _answer(wv)
        assert result["status"] == "numerically_solved"
        assert result["numeric_result"]["value"] == pytest.approx(
            _truth(wv), abs=1e-12)


def test_neither_conditional_is_the_number_a_collapsed_ratio_returns():
    """Anti-silent-wrong. A denominator that stopped depending on Y is
    |dom(Y)| copies of its numerator, so the ratio is 1/2 for a binary Y —
    the same 1/2 whatever the mechanisms are, and the same for both values
    of the thing conditioned on. Truth does neither."""
    values = [_answer(wv)["numeric_result"]["value"] for wv in _B]
    assert all(abs(v - 0.5) > 0.1 for v in values)
    assert abs(values[0] - values[1]) > 0.4


def test_every_sum_in_the_shipped_estimand_binds_what_it_ranges_over():
    """The shape, not the number: a reader shown ``Σ_y`` is shown a
    denominator whose body says y."""
    for wv in _B:
        formula = _answer(wv)["formula"]
        totals = list(_sums(formula))
        assert totals, "the conditional estimand is a ratio of sums"
        for total in totals:
            assert _bound_to(total["body"], total["bind"]["name"]) == {
                total["over"]["predicate"]}


def test_a_sum_holds_its_variable_and_nothing_else_does():
    """The rule itself, both halves. The same atom, the same query, the
    same VarRef — the answer differs only by whether a sum encloses it."""
    y = _A("y")
    x = _A("x")
    marked = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=VarRef(name="t_y")), given=())

    held = _apply_idc_values(
        SumExpr(bind=BindDecl(name="t_y"), over=y, body=marked),
        x_atom=x, x_value=True, free_targets=frozenset({y}))
    assert held.body.target.value == VarRef(name="t_y")

    loose = _apply_idc_values(
        marked, x_atom=x, x_value=True, free_targets=frozenset({y}))
    assert loose.target.value is None

    other = _apply_idc_values(
        SumExpr(bind=BindDecl(name="t_z"), over=_A("z"), body=marked),
        x_atom=x, x_value=True, free_targets=frozenset({y}))
    assert other.body.target.value is None


def test_the_verifier_accepts_the_conditional_it_recomputes():
    for wv in _B:
        program = _program(wv)
        themis.verify(program, _answer(wv))
