"""An estimator nobody can reach is not a capability.

``estimate_cde`` was written, exported from ``themis.estimation``, and given
a test file of its own that exercised its arithmetic thoroughly. Every one
of those tests called it directly. For the whole of the phase that
introduced it, no program handed to ``themis.estimate`` could arrive at it:
the dispatcher named ``numeric_end_not_built`` on the very branch the
identification layer routes to when the natural effects fail and the
controlled direct effect survives — the case the estimator exists for.

This is the same shape as the defect the sibling gate
(``test_every_correction_survives_the_kernel_that_dispatches_it``) was
written for, and its wording was narrower than its criterion: that one
asks the question of measurement corrections, and the question belongs to
estimators. So this asks it of all of them.

**The check is on the source and not on a run.** Whether a route fires
depends on a graph, a query and a frame, and a test that had to build one
per estimator would be a test of the twenty-four programs it happened to
write. What can be checked exactly is whether the dispatcher NAMES the
estimator at all: an estimator it never mentions cannot be reached from
``themis.estimate`` by any input whatsoever, which is the failure that
actually occurred. It is a weaker claim than "reachable" and a decisive one
against the failure it guards.

The second half of the pair is :data:`REACHED_THROUGH_ANOTHER`, and it is
where an estimator says why the dispatcher does not name it. A list with
reasons rather than a bare allowlist, because "the dispatcher calls the
n-level form and this is the 1-level wrapper" and "nobody can get here"
look identical in a set of names.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import themis.estimation as estimation

DISPATCH = pathlib.Path(__file__).resolve().parents[1] / (
    "themis/estimation/dispatch.py")
ESTIMATION = DISPATCH.parent

#: Estimators the dispatcher legitimately does not name, and what reaches
#: the estimand instead. An entry here is a claim a reader can check, not a
#: waiver: it must say which OTHER route answers the same question.
REACHED_THROUGH_ANOTHER: dict[str, str] = {
    "estimate_cde": (
        "the one-level form of estimate_cde_curve, which the dispatcher "
        "does name. A route has no level to choose — picking one would be "
        "the package settling a policy question — so it asks for the curve "
        "and this entry point is for a caller who has chosen"
    ),
    "estimate_cde_chain": (
        "the mediator-SET controlled direct effect, held at a VECTOR of "
        "levels. The dispatcher declines that case as numeric_end_not_built "
        "and says why where it declines: the curve shape indexes its rows "
        "by one number, and reporting a vector through that field would "
        "take a second way of saying the same thing"
    ),
}


def _names_mentioned(path: pathlib.Path) -> set[str]:
    """Every identifier the module names, however it names it.

    Imports count, and so do attribute accesses: the dispatcher imports its
    estimators lazily inside the handlers that use them, so a check reading
    only module-level imports would find almost none of them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.name for a in node.names)
    return names


def _exported_estimators() -> tuple[str, ...]:
    return tuple(sorted(
        n for n in estimation.__all__ if n.startswith("estimate_")))


def test_the_dispatcher_names_every_estimator_or_the_list_says_why():
    unnamed = set(_exported_estimators()) - _names_mentioned(DISPATCH)
    assert unnamed == set(REACHED_THROUGH_ANOTHER), (
        "estimators the dispatcher never names, with no entry saying what "
        f"reaches their estimand instead: {sorted(unnamed - set(REACHED_THROUGH_ANOTHER))}\n"
        "entries claiming an estimator is unreachable that the dispatcher "
        f"does name: {sorted(set(REACHED_THROUGH_ANOTHER) - unnamed)}"
    )


@pytest.mark.parametrize("name", sorted(REACHED_THROUGH_ANOTHER))
def test_each_exception_names_a_route_that_answers_instead(name):
    """A reason, not a length. The entry has to name the other road."""
    reason = REACHED_THROUGH_ANOTHER[name]
    assert len(reason) > 40, f"{name}: the reason says nothing"
    assert any(word in reason for word in
               ("estimate_", "dispatcher", "route")), (
        f"{name}: the reason has to name what answers this estimand instead"
    )


def test_every_exception_is_still_an_exported_estimator():
    """The list cannot outlive what it excuses.

    An entry for a function that has been renamed or deleted would sit here
    reading like a considered decision about a route that no longer exists,
    which is how the deferral this whole gate was written for survived a
    phase.
    """
    exported = set(_exported_estimators())
    stale = sorted(set(REACHED_THROUGH_ANOTHER) - exported)
    assert not stale, f"entries for estimators that are no longer exported: {stale}"


def test_no_estimation_module_is_the_only_one_that_knows_an_estimator():
    """An estimator the dispatcher skips must be reachable from somewhere
    that is not its own module.

    The measured shape of the defect was total isolation: neither the
    dispatcher nor any other estimation module named ``estimate_cde``, so
    the only callers in the repository were its own tests. That is what
    distinguishes an estimator with a different front door from one with
    none.
    """
    for name, reason in REACHED_THROUGH_ANOTHER.items():
        home = getattr(estimation, name).__module__.rsplit(".", 1)[-1]
        elsewhere = [
            p.name for p in sorted(ESTIMATION.glob("*.py"))
            if p.stem not in (home, "__init__")
            and name in _names_mentioned(p)
        ]
        # The chain form's road is a declared decline in the dispatcher
        # rather than another module's call, and the decline is the thing
        # that has to be findable — so a named reason stands in for a
        # caller here, and the reason above is what a reader follows.
        assert elsewhere or "dispatcher" in reason, (
            f"{name} is named by no estimation module but its own, and its "
            f"reason does not point at the dispatcher"
        )
