"""Phase 6.iv S.IV.1: iv_sets primitive.

Tests Pearl IV identification on the graph / ADMG structure:
- IV1 (relevance): Z has an open path to X given W in G
- IV2 + IV3 (exogeneity + exclusion): in G with X's outgoing edges
  removed, Z is m-separated from Y given W

See PHASE_6_IV_CHARTER.md §3 for the formal definitions.
"""
from __future__ import annotations

import networkx as nx

from themis.runtime import structural_solver
from themis.runtime.structural_solver import IVCandidate
from themis.types import Atom, ConstTerm


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


# ================================================== basic IV cases


def test_iv_sets_minimal_valid_iv():
    """Z -> X -> Y, no other edges. Z is a valid basic IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    assert result == (IVCandidate(instrument=z, conditioning=frozenset()),)


def test_iv_sets_multiple_instruments():
    """Two separate IVs Z1 -> X and Z2 -> X, both valid."""
    z1, z2, x, y = _atom("z1"), _atom("z2"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z1, x), (z2, x), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    instruments = {c.instrument for c in result}
    assert instruments == {z1, z2}
    # All are basic IVs (W empty)
    for c in result:
        assert c.conditioning == frozenset()


def test_iv_sets_rejects_direct_z_to_y():
    """Z -> X -> Y, Z -> Y direct. IV2 violated — Z reaches Y without
    going through X→Y (via Z→Y direct edge)."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y), (z, y)])

    result = structural_solver.iv_sets(g, x, y)
    assert result == ()


def test_iv_sets_rejects_z_disconnected_from_x():
    """Z is isolated or has no path to X — IV1 fails."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y)])
    g.add_node(z)

    result = structural_solver.iv_sets(g, x, y)
    assert result == ()


def test_iv_sets_rejects_z_descendant_of_y():
    """Z is descendant of Y — no directed path Z→X, IV1 fails."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y), (y, z)])

    result = structural_solver.iv_sets(g, x, y)
    assert result == ()


# ================================================== conditional IV cases


def test_iv_sets_conditional_iv_when_w_blocks_backdoor():
    """W -> Z and W -> Y creates a Z <- W -> Y back-door in the
    mutilated graph. Basic IV fails (Z connected to Y via W).
    But given W, Z is d-separated from Y in G[\\bar{X}]. Note: W
    is not a descendant of X, so it is allowed in the conditioning
    pool."""
    w, z, x, y = _atom("w"), _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(w, z), (w, y), (z, x), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    # Expect: given W, Z becomes a valid IV
    assert any(
        c.instrument == z and c.conditioning == frozenset({w}) for c in result
    )


def test_iv_sets_excludes_descendants_of_x_from_w_pool():
    """Descendants of X should not be proposed as conditioning vars
    (would condition on a mediator). Construct a graph where the
    only variable that could block is a descendant of X — result
    should be empty (no valid IV, rather than silently conditioning
    on the mediator)."""
    z, x, m, y = _atom("z"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    # Z -> X -> M -> Y, and Z -> Y via Z -> M -> Y direct? No — let's
    # use: Z -> X, X -> Y direct, plus Z -> M where M is a descendant
    # of X. The natural IV uses no conditioning, so this is mainly
    # a guard test that M is not proposed as W.
    g.add_edges_from([(z, x), (x, m), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    # Z alone is a valid basic IV
    assert IVCandidate(instrument=z, conditioning=frozenset()) in result
    # M should never appear in any W because M is a descendant of X
    for c in result:
        assert m not in c.conditioning


# ================================================== ADMG cases


def test_iv_sets_rejects_when_z_y_share_bidirected():
    """Z ↔ Y bidirected means Z shares latent common cause with Y.
    IV3 (exogeneity) fails — in G[\\bar{X}] there's still a Z ↔ Y
    m-path."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bidir = frozenset([frozenset({z, y})])

    result = structural_solver.iv_sets(g, x, y, bidirected=bidir)
    assert result == ()


def test_iv_sets_allows_bidirected_between_x_and_y():
    """X ↔ Y bidirected (unobserved X-Y confounder) — this is
    exactly the scenario IV solves. Z → X → Y with X ↔ Y latent
    should still admit Z as valid IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bidir = frozenset([frozenset({x, y})])

    result = structural_solver.iv_sets(g, x, y, bidirected=bidir)
    assert IVCandidate(instrument=z, conditioning=frozenset()) in result


# ================================================== guards / edge cases


def test_iv_sets_empty_graph():
    x, y = _atom("x"), _atom("y")
    g = nx.DiGraph()
    result = structural_solver.iv_sets(g, x, y)
    assert result == ()


def test_iv_sets_x_equals_y():
    x = _atom("x")
    g = nx.DiGraph()
    g.add_node(x)
    result = structural_solver.iv_sets(g, x, x)
    assert result == ()


def test_iv_sets_nodes_not_in_graph():
    x, y, z = _atom("x"), _atom("y"), _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    missing = _atom("missing")
    # Missing X
    assert structural_solver.iv_sets(g, missing, y) == ()
    # Missing Y
    assert structural_solver.iv_sets(g, x, missing) == ()


def test_iv_sets_respects_max_conditioning_size():
    """When max_conditioning_size=0, conditional IVs are excluded even
    if they would otherwise be valid."""
    w, z, x, y = _atom("w"), _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(w, z), (w, y), (z, x), (x, y)])

    # With max=0, only basic IVs allowed; none exist here
    result_basic = structural_solver.iv_sets(g, x, y, max_conditioning_size=0)
    assert result_basic == ()

    # With max=1, conditional IV with |W|=1 is found
    result_cond = structural_solver.iv_sets(g, x, y, max_conditioning_size=1)
    assert any(c.conditioning == frozenset({w}) for c in result_cond)


def test_iv_sets_subset_minimal_w():
    """If both W={} and W={w} are valid for the same Z, only W={} is
    kept (subset-minimal). Most easily tested with a graph where
    basic IV works AND adding conditioning doesn't break it — the
    subset dedup should keep only the basic version."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    # Only one candidate: basic IV with empty W
    assert result == (IVCandidate(instrument=z, conditioning=frozenset()),)


# ================================================== ordering stability


def test_iv_sets_sorted_basic_before_conditional():
    """Returned candidates sorted: basic IV (|W|=0) before conditional
    (|W|≥1), then by instrument predicate."""
    z1, z2, w, x, y = (
        _atom("z1"), _atom("z2"), _atom("w"), _atom("x"), _atom("y"),
    )
    g = nx.DiGraph()
    # z1 -> x -> y (basic IV)
    # z2 -> x, with W -> z2, W -> y (z2 is conditional IV given W)
    g.add_edges_from([(z1, x), (z2, x), (w, z2), (w, y), (x, y)])

    result = structural_solver.iv_sets(g, x, y)
    # First candidate should be basic IV
    assert result[0].conditioning == frozenset()
    # Among basic, z1 comes before (alphabetical)
    basic = [c for c in result if c.conditioning == frozenset()]
    assert basic[0].instrument == z1
