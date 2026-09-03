"""A walk over a formula, and the line by which it claims to be total.

``themis.verify`` raised ``TypeError: unknown FormulaExpr node:
FractionExpr`` on Pearl's napkin — a graph this repository identifies
through a c-factor, which is a ratio, on an answer its own suite produces.
Not a refusal, a traceback: the strongest public door could not reach a
verdict at all about an honest answer.

The branch was missing from ``_verifier_bind_target_value``, which says in
its own docstring that it is a verifier-side INDEPENDENT re-implementation
of ``formula_builder.bind_target_value``. The producer walks five node
kinds and that copy walked four. Its sibling twelve lines below,
``_verifier_bind_idc_values``, walks all five and says so in its docstring
— so this was never a gap in what anybody knew. Verifier duplication is
deliberate here, which makes a twin drifting from its original a KNOWN
cost of the design, and a known cost is answered with a gate rather than
with vigilance.

The gate is available because both halves are already written down. The
kinds live in one place, ``types.FormulaExpr``, read here off the type
rather than listed. And a walker declares itself total by ending in
``raise ...("unknown ... node")`` — that line is the claim, so the
functions carrying it are exactly the ones this holds to the list.
Fifteen of them; fourteen were already complete.

WHAT THIS DOES NOT CHECK: that a walker's branch is CORRECT, only that it
exists. A branch that returns the wrong tree is each rule's own business
and is checked where that rule is.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import typing

import pytest

import themis
from themis import types
# One writer for the napkin-with-theta fixture, and it is there. The
# regression below needs a chain, a chain needs numbers, and a second
# hand-built joint distribution would be a second thing to keep true.
from tests.test_runtime.test_iv_effect_dispatch import _napkin_with_theta

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: How a walker says it has handled every kind there is.
CLAIM = re.compile(r"unknown\s+.*node", re.IGNORECASE)

#: The kinds, read off the union rather than transcribed. A node kind
#: added to the type is a node kind every claimant below must handle.
NODE_KINDS = frozenset(
    node.__name__ for node in typing.get_args(types.FormulaExpr))


def _message(node: ast.AST) -> str:
    """Every string literal inside a raise, f-string parts included."""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return " ".join(out)


def _isinstance_names(func: ast.AST) -> set[str]:
    """Every type name this function tests membership of."""
    names: set[str] = set()
    for sub in ast.walk(func):
        if not (isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "isinstance"
                and len(sub.args) == 2):
            continue
        second = sub.args[1]
        for item in (second.elts if isinstance(second, ast.Tuple)
                     else [second]):
            if isinstance(item, ast.Name):
                names.add(item.id)
            elif isinstance(item, ast.Attribute):
                names.add(item.attr)
    return names


def _claimants(source: str, where: str) -> list[tuple[str, int, set[str]]]:
    """``(name, line, kinds it does not test for)`` per claiming walker."""
    found = []
    for func in ast.walk(ast.parse(source)):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        claims = any(isinstance(stmt, ast.Raise) and CLAIM.search(_message(stmt))
                     for stmt in ast.walk(func))
        if not claims:
            continue
        found.append((f"{where}:{func.lineno} {func.name}", func.lineno,
                      NODE_KINDS - _isinstance_names(func)))
    return found


def _every_claimant() -> list[tuple[str, int, set[str]]]:
    found = []
    for path in sorted(ROOT.joinpath("themis").rglob("*.py")):
        found.extend(_claimants(path.read_text(encoding="utf-8"),
                                path.relative_to(ROOT).as_posix()))
    return found


# ------------------------------------------------------------- the two halves


def test_the_kinds_come_from_the_type_and_not_from_this_file():
    """Read off ``types.FormulaExpr``, and pinned so that adding a kind is
    a visible change here rather than a silent widening of the gate."""
    assert NODE_KINDS == {
        "ConstantExpr", "ProbabilityRefExpr", "ProductExpr", "SumExpr",
        "FractionExpr",
    }, sorted(NODE_KINDS)


def test_every_walker_that_claims_the_whole_tree_has_walked_it():
    """The gate. A walker that raises on an unknown node is claiming there
    are none it does not know."""
    incomplete = {name: sorted(missing)
                  for name, _line, missing in _every_claimant() if missing}
    assert not incomplete, (
        "walkers that raise on an unknown formula node while never testing "
        f"for one: {json.dumps(incomplete, ensure_ascii=False, indent=1)}")


def test_the_claimants_are_the_ones_this_expects():
    """The denominator, so that a walker which stops making the claim — by
    losing its raise, or by being deleted — is noticed rather than
    silently leaving the gate's scope."""
    names = sorted(name.split()[-1] for name, _l, _m in _every_claimant())
    assert len(names) == 15, names
    assert "_verifier_bind_target_value" in names
    assert "bind_target_value" in names


def test_the_scan_says_so_when_a_branch_is_missing():
    """Teeth. The gate above passes; a gate that cannot fail is a
    decoration, so it is shown the shape it exists to refuse."""
    short = '''
def walk(formula):
    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return formula
    if isinstance(formula, ProductExpr):
        return formula
    if isinstance(formula, SumExpr):
        return formula
    raise TypeError(f"unknown FormulaExpr node: {type(formula).__name__}")
'''
    found = _claimants(short, "<synthetic>")
    assert len(found) == 1, found
    assert found[0][2] == {"FractionExpr"}, found

    whole = short.replace(
        "    raise TypeError",
        "    if isinstance(formula, FractionExpr):\n        return formula\n"
        "    raise TypeError")
    assert _claimants(whole, "<synthetic>")[0][2] == set()


# ----------------------------------------------------- and the answer itself


def test_a_ratio_reaches_a_verdict_rather_than_a_traceback():
    """The napkin, end to end, through the door that raised on it.

    Asserted about the CHAIN and not only about the door, because a door
    that accepts an answer carrying no ratio would pass this while the
    branch was still missing.
    """
    program = _napkin_with_theta(None)
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved", result["status"]
    assert '"fraction"' in json.dumps(result["derivation"])

    themis.verify(program, result)
    themis.verify_answer_claims(program, result)


def test_the_bind_itself_carries_a_ratio_through():
    """The unit under the answer above, so a failure says which of the two
    it is: the walker, or the route that reaches it."""
    from themis.types import (
        Atom, ConstantExpr, FractionExpr, ProbabilityRefExpr, ValuedAtom,
    )
    from themis.verifier.rules import _verifier_bind_target_value

    y = Atom(predicate="y", args=())
    hole = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=None), given=())
    ratio = FractionExpr(numerator=hole, denominator=ConstantExpr(value=2.0))

    bound = _verifier_bind_target_value(ratio, y, True)
    assert isinstance(bound, FractionExpr)
    assert bound.numerator.target.value is True
    assert bound.denominator == ConstantExpr(value=2.0)


def test_an_unknown_node_is_still_refused():
    """The raise is not removed by making the walk total: something that
    is not a formula node at all still says so."""
    from themis.types import Atom
    from themis.verifier.rules import _verifier_bind_target_value

    with pytest.raises(TypeError, match="unknown FormulaExpr node"):
        _verifier_bind_target_value(
            "not a formula", Atom(predicate="y", args=()), True)
