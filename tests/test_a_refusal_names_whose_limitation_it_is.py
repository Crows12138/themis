"""A kind says which of four things stopped the answer. It can be wrong.

``Refusal`` carries its ``kind`` beside its name, and the reasoning for that
is sound as far as it goes: only the estimator knows whether it stopped at
the graph, at the data, at the caller's input or at the edge of what this
package implements, and declaring it once keeps every raise site and every
reader out of the decision.

What it assumes is that the species determines the answer. A species is a
name for a CONDITION; a kind is a claim about what that condition is evidence
OF. Where one condition can come about in more than one way, the name covers
occasions with different answers, and any constant the declaration picks is
wrong on the rest. Two were measured:

``convergence_failure`` — BACKEND, "a routine did not return an answer, so
nothing has been decided" — was raised by a pre-fit check that had just
measured the outcome column and found it constant. Nothing had been fitted.
The site's own message said 实为数据问题 and the species said the opposite,
and the treatment-side twin two functions below has answered
``overlap_insufficient`` since the day it was written.

``iv_model_refuted`` — GRAPH, "the observed table is incompatible with ANY IV
model" — was raised on ``not (lo.success and hi.success)``. ``success`` is a
two-valued shadow of a five-valued status, and only one of those values is a
statement about the model: HiGHS reports 2 when the constraints admit no
point. An iteration limit and a numerical breakdown are the solver saying it
stopped, and they were being reported to the reader as a refuted instrument —
a claim about their design, made because a program ran out of iterations, in
the direction where being wrong costs the most.

The first of the two generalises and is gated here: a BACKEND refusal is the
record of a routine that was asked and did not answer, so a site filing one
has such a record in hand — an ``except`` arm it is standing in, or a routine's
own verdict in the test above it. Run against the code as it was, the sweep
names ``dose_response.py:424`` and leaves the ``except`` arm forty lines up
alone.

The second does not generalise, and does not need to: ``linprog`` is called in
one place in this package, so the fact is pinned where it lives — which of the
five statuses licenses the conclusion, and what the other four do instead.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from themis import refusals
from themis.estimation.dose_response import _check_outcome_variance
from themis.refusals import EstimatorFailure, Kind, Refusal
from themis.response_polytope import _LP_INFEASIBLE, _not_infeasible

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The attributes on which a routine reports its own verdict.
#:
#: A BACKEND refusal is not a measurement, it is a quotation: the routine ran
#: and said it had no answer. Usually it says so by raising, and then the
#: quotation is the ``except`` arm. ``scipy.optimize`` says so by returning,
#: and these are the two names it says it on.
ROUTINE_VERDICTS = {"status", "success"}


class _Site:
    """One place a species is filed, with what stood above it."""

    def __init__(self, module: str, lineno: int, species: str,
                 caught: bool, tests: list[str]):
        self.module, self.lineno, self.species = module, lineno, species
        self.caught, self.tests = caught, tests

    def __repr__(self) -> str:
        return f"{self.module}:{self.lineno} files {self.species}"


def _named(call: ast.Call) -> str | None:
    named = next((kw.value for kw in call.keywords if kw.arg == "failure_type"),
                 None)
    first = named if named is not None else (call.args[0] if call.args else None)
    return first.attr if isinstance(first, ast.Attribute) else None


def _filed(node: ast.stmt) -> ast.Call | None:
    """The call in this simple statement that names a species.

    Simple statements only, so a ``try`` and the assignment inside it are not
    two sightings of one site.
    """
    if isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With,
                         ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = (sub.func.id if isinstance(sub.func, ast.Name)
                else getattr(sub.func, "attr", ""))
        if name in {"EstimatorFailure", "IdentificationFailure", "block"}:
            if _named(sub) is not None:
                return sub
    return None


def _sites(tree: ast.AST, module: str) -> list[_Site]:
    """Every filing site, carrying the guards it sits under."""
    found: list[_Site] = []

    def walk(node, caught: bool, tests: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt) and (call := _filed(child)):
                found.append(
                    _Site(module, child.lineno, _named(call), caught, tests))
            if isinstance(child, ast.ExceptHandler):
                walk(child, True, tests)
            elif isinstance(child, ast.If):
                said = tests + [ast.unparse(child.test)]
                for stmt in child.body:
                    walk_stmt(stmt, caught, said)
                for stmt in child.orelse:
                    walk_stmt(stmt, caught, said)
            else:
                walk(child, caught, tests)

    def walk_stmt(stmt, caught: bool, tests: list[str]) -> None:
        if (call := _filed(stmt)):
            found.append(_Site(module, stmt.lineno, _named(call), caught, tests))
        walk(stmt, caught, tests)

    walk(tree, False, [])
    return found


def _all_sites() -> list[_Site]:
    out: list[_Site] = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - none today
            continue
        out.extend(_sites(tree, path.relative_to(REPO).as_posix()))
    return out


def _unquoted(sites) -> list[_Site]:
    """Backend filings with no routine's report above them."""
    return [
        s for s in sites
        if getattr(Refusal, s.species, None) is not None
        and Refusal[s.species].kind is Kind.BACKEND
        and not s.caught
        and not any(
            isinstance(n, ast.Attribute) and n.attr in ROUTINE_VERDICTS
            for test in s.tests for n in ast.walk(ast.parse(test))
        )
    ]


def test_a_backend_refusal_quotes_a_routine_that_already_answered():
    """Nothing files BACKEND off a measurement of the data.

    BACKEND is the kind that decides nothing — not about the question, not
    about the graph, not about the data. A site that has just measured the
    data and found it wanting has decided about the data, and saying
    otherwise leaves the reader with a refusal that names no next move while
    the data it measured is sitting right there.
    """
    offenders = _unquoted(_all_sites())
    assert not offenders, (
        f"{offenders} file a BACKEND species with no routine's report in "
        f"hand — neither inside an except arm nor under a test of "
        f"{sorted(ROUTINE_VERDICTS)}; whatever they measured, they decided it"
    )


def test_the_check_sees_a_backend_refusal_measured_off_the_data(tmp_path):
    """The counterexample, spelled the way the dose-response check was."""
    doctored = tmp_path / "doctored.py"
    doctored.write_text(
        "def _check_outcome_variance(y):\n"
        "    if float(y.std()) < 1e-8:\n"
        "        raise EstimatorFailure(\n"
        "            failure_type=Refusal.CONVERGENCE_FAILURE, message='x')\n"
        "    try:\n"
        "        fit(y)\n"
        "    except ValueError as exc:\n"
        "        raise EstimatorFailure(Refusal.CONVERGENCE_FAILURE, str(exc))\n",
        encoding="utf-8")
    sites = _sites(ast.parse(doctored.read_text(encoding="utf-8")), "doctored")
    assert len(sites) == 2, sites
    assert [s.lineno for s in _unquoted(sites)] == [3]


# --- the second one, at its own seam ------------------------------------------

class _Program:
    """What ``linprog`` hands back, down to what is read off it."""

    def __init__(self, status: int, message: str = "said so"):
        self.status, self.message = status, message
        self.success = status == 0


@pytest.mark.parametrize("status", [1, 3, 4])
def test_a_solver_that_did_not_finish_is_not_a_refuted_model(status):
    """An iteration limit, an unbounded objective, a numerical breakdown.

    All three are ``success is False``, and none of them is evidence about
    the reader's instrument.
    """
    stalled = _not_infeasible(_Program(status), _Program(_LP_INFEASIBLE))
    assert stalled is not None and stalled.status == status
    assert _not_infeasible(_Program(_LP_INFEASIBLE), _Program(status)) is not None


def test_an_infeasible_pair_is_still_a_refutation():
    """Both programs prove the constraints admit nothing, which is the claim."""
    assert _not_infeasible(_Program(_LP_INFEASIBLE),
                           _Program(_LP_INFEASIBLE)) is None


def test_two_programs_disagreeing_about_feasibility_decide_nothing():
    """They share their constraints, so a disagreement is the solver's."""
    assert _not_infeasible(_Program(0), _Program(_LP_INFEASIBLE)) is not None


def test_the_stalled_solver_decides_nothing_and_quotes_what_stalled():
    """The two answers a failed program can have are two species, two kinds.

    And the stalled one hands over the solver's own words rather than a
    conclusion of its own: what a reader can act on here is the diagnostic,
    because the question is still open.
    """
    assert Refusal.LINEAR_PROGRAM_FAILED.kind is Kind.BACKEND
    assert Refusal.IV_MODEL_REFUTED.kind is Kind.GRAPH
    for lang in sorted(refusals.language.written()):
        said = refusals.sentence(
            Refusal.LINEAR_PROGRAM_FAILED,
            {"statuses": [1, 1], "diagnostic": "iteration limit"}, lang)
        assert said and "iteration limit" in said


# --- the first one, at its own seam -------------------------------------------

def test_the_outcome_check_measures_the_data_and_says_so():
    """It runs before any fit, so what it found is about the data."""
    with pytest.raises(EstimatorFailure) as caught:
        _check_outcome_variance(y=np.full(64, 4.0), outcome="engagement")
    assert caught.value.failure_type is Refusal.OUTCOME_DOES_NOT_VARY
    assert Refusal.OUTCOME_DOES_NOT_VARY.kind is Kind.DATA
    assert "engagement" in str(caught.value)


def test_a_varying_outcome_passes():
    """The counterexample: the check has to be able to say yes."""
    _check_outcome_variance(y=np.arange(64.0), outcome="engagement")
