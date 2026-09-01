"""Every block that says where a number came from is re-derived by something.

:mod:`themis.blocks` already names the class: ``Family.ROUTE`` is "how the
estimand was identified", and ``analysis_report`` binds every member of it
to a renderer, so a route block that would reach a reader and render
nothing cannot be added. The other half had no binding at all, and the
measurement is why this file exists — of thirteen ROUTE blocks, six were
handed to a verifier at the public door and seven were not, and every one
of the seven let a tampered envelope through: an instrument named as the
outcome, a joint adjustment set replaced, a mediator's arm flipped from
identifiable to not, a proxy role reversed, the switch that decides whether
a time-varying strategy gets a number at all simply turned on.

``bind_audit`` is the sibling of ``bind`` and the denominator is the whole
of the difference. ``bind`` asks over ``rendered_in``, because a block
another surface carries has already been said. This asks over the WHOLE
family, because ``carried_by`` is a fact about how a block reaches a reader
and says nothing about whether anyone recomputed it — a number restated by
a carrier is the producer's word arriving twice. The two denominators are
equal on ROUTE today and differ on three other families, so the
distinction is pinned against one of those rather than against a
hypothetical.

WHAT THIS FILE DOES NOT CHECK. That an audit re-derives the block rather
than reading it back. No static check can, and the six files that closed
these blocks each construct the tampered envelope their block must be
refused for. What is checked here is the one thing those cannot: that the
list is complete, and that the table is the path that actually runs.
"""
from __future__ import annotations

import pytest

from themis import blocks, kernel


def _nothing(facts):
    return None


ROUTE = blocks.declared_as(blocks.Family.ROUTE)


def test_every_route_block_is_bound_to_an_audit():
    """The list, stated once here so a reader of this file can see it
    without reading the kernel's table."""
    assert set(kernel._ROUTE_AUDITS) == set(ROUTE), (
        sorted(str(b) for b in set(ROUTE) - set(kernel._ROUTE_AUDITS)),
        sorted(str(b) for b in set(kernel._ROUTE_AUDITS) - set(ROUTE)),
    )
    assert len(ROUTE) == 13, sorted(str(b) for b in ROUTE)


def test_a_route_block_with_no_audit_is_refused():
    """The counterexample the gate exists for. A block that reaches a
    reader on the producer's word is the thing this repository claims to
    be the opposite of."""
    table = {b: _nothing for b in ROUTE}
    table.pop(blocks.Block.PROXIMAL_ESTIMAND)
    with pytest.raises(ValueError, match="nothing re-derives"):
        blocks.bind_audit(blocks.Family.ROUTE, table)


def test_an_audit_for_a_block_of_another_family_is_refused():
    """The other half. An audit bound from outside reads as coverage of
    something this family does not contain."""
    table = {b: _nothing for b in ROUTE}
    table[blocks.Block.ASSUMPTION_LEDGER] = _nothing
    with pytest.raises(ValueError, match="which route does not contain"):
        blocks.bind_audit(blocks.Family.ROUTE, table)


def test_a_complete_table_is_accepted():
    """The denominator. A gate that refused everything would refuse both
    forgeries above and mean nothing by it."""
    assert blocks.bind_audit(
        blocks.Family.ROUTE, {b: _nothing for b in ROUTE})


@pytest.mark.parametrize("family", [
    blocks.Family.ANSWER, blocks.Family.ASSUMPTION, blocks.Family.GAP])
def test_being_carried_by_another_surface_does_not_excuse_a_block(family):
    """Where the two denominators come apart, and why this one is right.

    ``bind`` lets a carried block go unbound because it has already been
    said. ``bind_audit`` does not, because saying a number twice is not
    checking it once — ``counterfactual_cell`` is carried by
    ``numeric_estimate`` and is cross-checked against it in the kernel for
    exactly that reason: a tamper of the display copy alone must not pass.
    """
    declared = set(blocks.declared_as(family))
    rendered = set(blocks.rendered_in(family))
    assert rendered < declared, (family, sorted(map(str, declared)))
    with pytest.raises(ValueError, match="nothing re-derives"):
        blocks.bind_audit(family, {b: _nothing for b in rendered})


def test_the_table_is_the_path_that_runs():
    """A table nobody calls is the coverage-by-declaration this repository
    keeps having to replace. The kernel iterates the DISTINCT audits, so
    every function in it has to be reachable that way — two blocks sharing
    one audit is how the mediation twins and the two IV surfaces are held
    together, and it is the case a naive per-block loop would run twice.
    """
    distinct = dict.fromkeys(kernel._ROUTE_AUDITS.values())
    assert set(distinct) == set(kernel._ROUTE_AUDITS.values())
    shared = [audit for audit in distinct
              if sum(1 for a in kernel._ROUTE_AUDITS.values() if a is audit) > 1]
    assert len(shared) == 2, [a.__name__ for a in shared]
    assert {a.__name__ for a in shared} == {
        "_audit_identification", "_audit_mediation"}
