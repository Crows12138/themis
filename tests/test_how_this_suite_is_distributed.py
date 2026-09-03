"""The arrangement that decides what a full run costs.

A distribution rule is invisible when it is right and invisible when it
is wrong: a module split across workers that should not have been rebuilds
something expensive per worker and only shows up as time, and a module
kept together that need not be is a worker doing everything while five
wait. Neither is a failing test unless something asks.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from tests import conftest

TESTS = pathlib.Path(__file__).resolve().parent


class _Module:
    def __init__(self, name, spread=False):
        self.__name__ = name
        if spread:
            self.SPREAD_ACROSS_WORKERS = True


class _Item:
    def __init__(self, module):
        self.module = module
        self.nodeid = f"{module.__name__}::t"
        self.marks = []

    def add_marker(self, mark):
        self.marks.append(mark)


def _groups(item) -> list[str]:
    return [m.mark.args[0] if hasattr(m, "mark") else m.args[0]
            for m in item.marks]


def test_a_module_is_kept_together_unless_it_says_otherwise():
    """The hook, put to both cases it decides between."""
    together = _Item(_Module("tests.test_something"))
    apart = _Item(_Module("tests.test_census", spread=True))
    conftest.pytest_collection_modifyitems(None, None, [together, apart])

    assert _groups(together) == ["tests.test_something"]
    assert _groups(apart) == [], (
        "a module that declared it may spread was pinned to one worker")


def test_the_opt_out_is_declared_and_not_widespread():
    """The denominator. Spreading is the exception, and an exception that
    quietly becomes the rule takes the reason for grouping with it."""
    declaring = sorted(
        path.name for path in TESTS.rglob("test_*.py")
        if any(isinstance(node, ast.Assign)
               and any(getattr(t, "id", None) == "SPREAD_ACROSS_WORKERS"
                       for t in node.targets)
               for node in ast.parse(
                   path.read_text(encoding="utf-8")).body))
    assert declaring == [
        "test_every_answer_shape_is_asked_the_same_question.py"], declaring


def test_the_census_walks_are_one_test_per_row():
    """What the opt-out is for. A single function looping over the corpus
    cannot be spread by any distribution rule, so the loop is the shape of
    the cost and parametrisation is the fix.

    Asked of the values a test is parametrised over rather than of the
    parameter's name: the two sweeps call a row a ``method`` and a ``name``
    respectively, and neither spelling is the thing being checked. Both are
    named here so that collapsing either one back into a loop fails, which
    would otherwise leave this file passing and the arrangement pointless.
    """
    from tests import test_every_answer_shape_is_asked_the_same_question as m

    rows = sorted(m.SHAPES)
    per_row = sorted(
        name for name in dir(m) if name.startswith("test_")
        for mark in getattr(getattr(m, name), "pytestmark", ())
        if mark.name == "parametrize" and list(mark.args[1]) == rows)
    assert per_row == [
        "test_no_leaf_a_reader_is_shown_goes_unasked",
        "test_the_snapshot_is_of_answers_this_build_still_gives",
    ], per_row
    assert len(rows) > 1
