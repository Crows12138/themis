"""Phase 6.mediation S.M.1 — unit tests for structural_solver.mediation_sets.

Coverage matrix:

- Basic mediator (X → M → Y): both NDE/NIE and CDE succeed
- Observed X-Y confounder: both succeed with correct W
- Intermediate confounder (X-descendant affects M and Y): sinks BOTH,
  and both name the membership condition that refused the one set that
  would have worked
- M-Y confounder not reachable from X: both succeed if blockable by W
- Degenerate structures: no mediator path / X=Y / missing nodes
- ADMG (bidirected) cases: bidirected X ↔ Y blocks both

The failure labels are asserted exactly rather than as a disjunction. A
test that accepts "M3 or M4" passes whichever the code says, and that is
how "M4" stayed unreachable while a glossary sentence waited for it; the
containment between the two routes, and the reachability of every label,
are counted in ``test_which_gate_is_weaker_is_a_count.py``.

Reference: Pearl 2001 "Direct and indirect effects"; VanderWeele 2015.
"""
from __future__ import annotations

import networkx as nx

from themis.runtime.structural_solver import (
    MediationAttempt,
    MediationResult,
    mediation_sets,
)
from themis.types import Atom, ConstTerm


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


# ================================================= basic mediator cases


def test_bare_mediator_both_identifiable():
    """X → M → Y, nothing else. Both NDE/NIE and CDE succeed with empty W."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert result.nde_nie.identifiable
    assert result.nde_nie.adjustment == frozenset()
    assert result.nde_nie.failed_condition is None
    assert result.cde.identifiable
    assert result.cde.adjustment == frozenset()


def test_mediator_with_direct_edge_still_valid():
    """X → M → Y and X → Y direct. Both still identifiable; NDE captures
    the direct edge's contribution, NIE captures the mediator path."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y), (x, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert result.nde_nie.identifiable
    assert result.cde.identifiable


# ============================================ observed X-Y confounder (U)


def test_observed_xy_confounder_requires_adjustment():
    """U → X, U → Y, X → M → Y. U must be in W for NDE/NIE; else M1 fails."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, x), (u, y), (x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert result.nde_nie.identifiable
    assert u in result.nde_nie.adjustment
    assert result.cde.identifiable
    assert u in result.cde.adjustment


def test_observed_xm_confounder_requires_adjustment():
    """U → X, U → M, X → M → Y. U must be in W for NDE/NIE (M2 condition)."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, x), (u, m), (x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert result.nde_nie.identifiable
    assert u in result.nde_nie.adjustment


def test_observed_my_confounder_requires_adjustment():
    """U → M, U → Y, X → M → Y. U must be in W for NDE/NIE (M3 condition)
    and for CDE."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, m), (u, y), (x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert result.nde_nie.identifiable
    assert u in result.nde_nie.adjustment
    assert result.cde.identifiable
    assert u in result.cde.adjustment


# ================================== intermediate confounder (X descendant)


def test_intermediate_confounder_breaks_both():
    """X → W → M, X → W → Y (W is X-descendant affecting both M and Y).

    This is the canonical "intermediate confounder" (a.k.a. recanting
    witness) case. Neither NDE/NIE nor simple backdoor-CDE are
    identifiable here, and both say so with the membership condition:

    - NDE/NIE: {W} satisfies M1, M2 and M3 — it blocks the M-Y backdoor —
      and is refused by M4 for descending from X.
    - CDE (backdoor-based): {W} satisfies C1 for the same reason and is
      refused by C2.

    Naming the restriction rather than the open path is the point. "There
    is still a back-door" sends the reader looking for a variable; the
    variable is right there in their graph and the answer is that
    controlling it would block the effect being measured.

    More advanced methods (g-formula, sequential ignorability) can
    identify CDE here, but those are out of scope for the backdoor-based
    check this slice implements.
    """
    x, w, m, y = _atom("x"), _atom("w"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, w), (w, m), (w, y), (x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert result.mediator_valid
    assert not result.nde_nie.identifiable
    assert result.nde_nie.failed_condition == "M4"
    assert not result.cde.identifiable
    assert result.cde.failed_condition == "C2"


def test_intermediate_confounder_fails_m4_explicit():
    """Dedicated M4 failure check. X → Z, Z → M, Z → Y, X → M, M → Y.
    Z is structurally required to block the M-Y backdoor but Z is an
    X-descendant → M4 forbids it → NDE/NIE fails M4."""
    x, z, m, y = _atom("x"), _atom("z"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, z), (z, m), (z, y), (x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert not result.nde_nie.identifiable
    assert result.nde_nie.failed_condition == "M4"


# ================================== degenerate / structural prereqs


def test_no_mediator_path_reports_invalid():
    """X → Y direct, no M in the path between them. Mediator invalid."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y), (m, y)])  # X does not reach M

    result = mediation_sets(g, x, y, m)
    assert not result.mediator_valid
    assert not result.nde_nie.identifiable
    assert not result.cde.identifiable


def test_mediator_not_reaching_y_reports_invalid():
    """X → M but M does not reach Y. Mediator invalid."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (x, y)])  # M is a dead-end

    result = mediation_sets(g, x, y, m)
    assert not result.mediator_valid


def test_x_equals_y_reports_invalid():
    x = _atom("x")
    m = _atom("m")
    g = nx.DiGraph()
    g.add_edges_from([(x, m)])

    result = mediation_sets(g, x, x, m)
    assert not result.mediator_valid


def test_missing_nodes_reports_invalid():
    """Atoms not present in graph → mediator_valid False."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_node(x)
    g.add_node(y)
    # m absent

    result = mediation_sets(g, x, y, m)
    assert not result.mediator_valid


# ======================================= ADMG (bidirected) cases


def test_bidirected_xy_blocks_both():
    """X ↔ Y (latent unobserved confounder). Neither NDE/NIE nor CDE
    can identify the effect without an IV or something stronger.
    Expected: both fail (M1 for NDE/NIE, C1 for CDE)."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bidir = frozenset([frozenset({x, y})])

    result = mediation_sets(g, x, y, m, bidirected=bidir)
    assert result.mediator_valid
    assert not result.nde_nie.identifiable
    assert result.nde_nie.failed_condition == "M1"
    assert not result.cde.identifiable
    assert result.cde.failed_condition == "C1"


def test_bidirected_xm_blocks_nde_nie():
    """X ↔ M (latent confounder between X and M). NDE/NIE fails — the
    latent X↔M creates an X↔M→Y backdoor path that can't be blocked
    without observing the confounder. Reports M1 (X-Y) before M2
    because checks run in order and the X↔M→Y path is also an X→Y
    backdoor."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bidir = frozenset([frozenset({x, m})])

    result = mediation_sets(g, x, y, m, bidirected=bidir)
    assert not result.nde_nie.identifiable
    # X↔M→Y opens an X-Y backdoor (M1) before the X-M one (M2) is checked
    assert result.nde_nie.failed_condition in ("M1", "M2")


def test_bidirected_my_blocks_nde_nie_and_cde():
    """M ↔ Y (latent confounder between M and Y). NDE/NIE fails M3;
    CDE fails C1."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bidir = frozenset([frozenset({m, y})])

    result = mediation_sets(g, x, y, m, bidirected=bidir)
    assert not result.nde_nie.identifiable
    assert result.nde_nie.failed_condition == "M3"
    assert not result.cde.identifiable


# ================================================= max_adjustment_size


def test_max_adjustment_size_limits_search():
    """If a valid W requires size > max_adjustment_size, don't find it."""
    # Graph where only 2-element W works: two independent confounders
    u1, u2, x, m, y = _atom("u1"), _atom("u2"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([
        (u1, x), (u1, y),
        (u2, x), (u2, m),
        (x, m), (m, y),
    ])

    # With default max=3, finds {u1, u2}
    result = mediation_sets(g, x, y, m)
    assert result.nde_nie.identifiable
    assert {u1, u2}.issubset(result.nde_nie.adjustment)

    # With max=0, cannot find it
    result_capped = mediation_sets(g, x, y, m, max_adjustment_size=0)
    assert not result_capped.nde_nie.identifiable


# ================================================= result shape


def test_result_is_named_tuple_with_correct_fields():
    """Sanity: MediationResult structure is as documented."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])

    result = mediation_sets(g, x, y, m)
    assert isinstance(result, MediationResult)
    assert isinstance(result.nde_nie, MediationAttempt)
    assert isinstance(result.cde, MediationAttempt)
    assert result.mediator == m
