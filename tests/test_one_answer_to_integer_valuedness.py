"""Whether a column is whole numbers is answered once, beside the cast.

``validate_data`` widens every numeric model column to float64. After that
the dtype no longer separates an integer-coded category from a
measurement, and three estimators each needed the fact the widening
destroyed. Each derived it for itself, and independent derivations of the
same predicate disagree exactly where nothing compares them:

  empty column   ``_classify_column`` said whole numbers (nothing in it is
                 not one), ``_discrete_levels`` said not, and refused it as
                 a continuous mediator — a sentence about a column with
                 nothing in it. Unreachable: the contract wants ten rows
                 and refuses a NaN in a model column, which is why the
                 disagreement survived.
  an infinity    ``np.round(inf)`` is ``inf``, so a bare comparison against
                 the rounded value calls it a whole number.
                 ``_check_discrete`` made that comparison by itself and
                 took an infinite stratum level. Reachable.

The denominator of the source rule below is every comparison against a
rounded value in ``themis/``, read off the source, so a fourth derivation
written next year is checked like the three that exist. Rounding for some
other purpose is not a derivation of this and is not what the rule looks
for — it looks for a rounded value being COMPARED to the value it came
from, which is only ever this question being asked.

The level label in ``discovery`` is not in this family and stays out of
it: collapsing an integral float to an int is a statement about what a
level IS on a discrete column, pinned separately in
``test_a_value_reaches_the_envelope_as_json_or_not_at_all``.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd
import pytest

from themis.estimation.contract import integer_valued

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The one function allowed to compare a value against its rounding.
HOME = ("themis/estimation/contract.py", "integer_valued")


def _round_comparisons(source: str) -> list[tuple[str, int]]:
    """(enclosing function, line) for every ``x == round(x)``-shaped test.

    Either side may be the rounded one and the operator may be ``==`` or
    ``!=``; both spellings appeared among the three derivations.
    """
    tree = ast.parse(source)
    found: list[tuple[str, int]] = []

    def is_round(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("round", "rint", "floor", "ceil")
        )

    def walk(node: ast.AST, enclosing: str) -> None:
        for child in ast.iter_child_nodes(node):
            here = enclosing
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                here = child.name
            if isinstance(child, ast.Compare) and any(
                isinstance(op, (ast.Eq, ast.NotEq)) for op in child.ops
            ):
                sides = [child.left, *child.comparators]
                if any(is_round(side) for side in sides):
                    found.append((here, child.lineno))
            walk(child, here)

    walk(tree, "<module>")
    return found


def test_the_question_is_asked_in_one_place():
    elsewhere: list[str] = []
    for path in sorted((REPO_ROOT / "themis").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for where, line in _round_comparisons(path.read_text(encoding="utf-8")):
            if (rel, where) != HOME:
                elsewhere.append(f"{rel}:{line} in {where}")
    assert not elsewhere, (
        "integer-valuedness is derived again outside "
        f"{HOME[0]}::{HOME[1]}: {elsewhere}. Three derivations of it "
        "disagreed on an empty column and on an infinity."
    )


def test_the_rule_refuses_a_derivation_written_anywhere_else():
    source = "\n".join([
        "def _some_new_estimator(vals):",
        "    return bool(np.all(vals == np.round(vals)))",
    ])
    assert _round_comparisons(source) == [("_some_new_estimator", 2)]


def test_the_rule_reads_the_other_spelling_too():
    source = "\n".join([
        "def _another(levels):",
        "    if np.any(levels != np.round(levels)):",
        "        raise ValueError",
    ])
    assert _round_comparisons(source) == [("_another", 2)]


def test_rounding_for_some_other_purpose_is_not_this_question():
    source = "\n".join([
        "def _render(value):",
        "    return f'{np.round(value, 3)}'",
    ])
    assert _round_comparisons(source) == []


# ------------------------------------------- what the three disagreed about


def test_an_infinity_is_not_a_whole_number():
    """``np.round(inf)`` is ``inf``; the comparison alone says otherwise."""
    assert np.round(np.inf) == np.inf          # the trap, stated
    assert not integer_valued(pd.Series([1.0, 2.0, np.inf]))
    assert not integer_valued(pd.Series([1.0, -np.inf]))


def test_nothing_is_vacuously_whole_numbers():
    """There is no value in an empty column that is not a whole number.

    A caller that cannot work with no values asks that question itself.
    """
    assert integer_valued(pd.Series([], dtype=float))
    assert integer_valued(np.array([], dtype=float))


def test_a_widened_integer_column_is_still_integer_valued():
    """The case the widening was destroying: 0/1/2 arriving as floats."""
    assert integer_valued(pd.Series([0.0, 1.0, 2.0]))
    assert not integer_valued(pd.Series([0.0, 1.5]))


def test_missing_values_are_not_the_question():
    assert integer_valued(pd.Series([1.0, np.nan, 2.0]))


def test_the_recovery_path_no_longer_takes_an_infinite_level():
    """The reachable half of the disagreement, pinned at the site that had it.

    The derivation this call site used to carry is written out here on
    purpose — it is the counterexample, and the sentence it says about
    this column is the reason the reading moved.
    """
    from themis.estimation import missing_recovery
    from themis.refusals import EstimatorFailure

    frame = pd.DataFrame({"z": [1.0, 2.0, np.inf, 1.0, 2.0]})
    levels = np.unique(frame["z"].to_numpy())
    assert not np.any(levels != np.round(levels))  # "whole numbers", it said
    with pytest.raises(EstimatorFailure):
        missing_recovery._check_discrete(frame, "z", "x")


@pytest.mark.parametrize("values", [
    pd.Series([True, False]),
    np.array([1, 2, 3]),
    pd.Series([0.0, 1.0]),
])
def test_every_shape_the_contract_leaves_behind_is_accepted(values):
    """bool and float are the contract's two arms; ndarray is how the
    recovery path holds a level set."""
    assert integer_valued(values)
