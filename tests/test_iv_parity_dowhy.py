"""Phase 6.iv S.IV.7: parity test — Themis iv_sets vs DoWhy get_instruments.

DoWhy is a **dev-only dependency** used here strictly as a correctness
calibrator. It is NOT a production backend. These tests confirm our
iv_sets agrees with DoWhy's get_instruments on simple DAGs (where
both implementations should match).

Known semantic differences (documented, not bugs):

1. **Graph mutilation direction**:
   - DoWhy cuts X's INCOMING edges (intervention graph `G_bar{X}`)
   - Themis cuts X's OUTGOING edges (Brito-Pearl 2002 `G_under{X}`)
   Both are correct for DAGs and give equivalent answers on pure-DAG
   inputs; the formulations diverge when ADMG bidirected edges are
   present (DoWhy has no ADMG IV support).

2. **Candidate pool**:
   - DoWhy restricts candidates to parents of X (via
     `parents_treatment` set)
   - Themis considers all non-X/non-Y nodes
   On DAGs this is equivalent because IV1 (directed path Z → X)
   naturally filters to X's ancestors anyway.

3. **Conditional IV**:
   - DoWhy does NOT support conditional IV (no W parameter)
   - Themis supports conditional IV up to max_conditioning_size
   So we restrict our comparison to BASIC IV (W = ∅) for parity.

If a future DoWhy version gains ADMG / conditional IV support, these
tests may need updating. If the tests fail for a "should-agree" case,
investigate: it indicates a real semantic divergence worth understanding.
"""
from __future__ import annotations

import pytest

try:
    from dowhy.graph import get_instruments
    _DOWHY_AVAILABLE = True
except ImportError:
    _DOWHY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DOWHY_AVAILABLE,
    reason="dowhy not installed (dev-only parity dependency)",
)

import networkx as nx
from themis.runtime import structural_solver
from themis.types import Atom, ConstTerm


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _themis_basic_iv_instruments(graph, x, y) -> set:
    """Wrap Themis iv_sets to return a set of basic-IV instrument names
    (conditioning = empty), comparable to DoWhy's get_instruments output."""
    result = structural_solver.iv_sets(graph, x, y)
    return {
        c.instrument.predicate
        for c in result
        if not c.conditioning  # only basic IV
    }


def _dowhy_instruments(graph_themis, x_pred, y_pred) -> set:
    """Build a DoWhy-compatible string-node graph and call get_instruments."""
    # DoWhy's graph uses string node labels. Themis uses Atom objects.
    # Build a parallel string graph preserving the same structure.
    g_str = nx.DiGraph()
    for node in graph_themis.nodes:
        g_str.add_node(node.predicate)
    for src, dst in graph_themis.edges:
        g_str.add_edge(src.predicate, dst.predicate)
    instruments = get_instruments(g_str, [x_pred], [y_pred])
    return set(instruments)


# ==================================================== parity cases


def test_parity_minimal_iv():
    """Z → X → Y. Both should identify Z as an IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == {"z"}


def test_parity_multiple_valid_instruments():
    """Z1 → X, Z2 → X, X → Y. Both should find both."""
    z1, z2, x, y = _atom("z1"), _atom("z2"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z1, x), (z2, x), (x, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == {"z1", "z2"}


def test_parity_z_to_y_direct_rejects_iv():
    """Z → X → Y + Z → Y direct. IV2 violated. Both should reject Z."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y), (z, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == set()


def test_parity_z_disconnected():
    """Z isolated from X/Y. Neither should find any IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y)])
    g.add_node(z)

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == set()


def test_parity_z_descendant_of_y():
    """Z is a descendant of Y (no Z → X path). Both reject."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y), (y, z)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == set()


def test_parity_with_mediator():
    """Z → X → M → Y. Z can reach Y only via X→M→Y path; IV valid."""
    z, x, m, y = _atom("z"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, m), (m, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    assert themis_ivs == dowhy_ivs == {"z"}


def test_parity_with_common_confounder_of_x_y():
    """Z → X → Y, plus U → X, U → Y (observed confounder). Classic
    IV setup in DAG form. Note U is OBSERVED here; in ADMG you'd
    use a bidirected edge, but DoWhy doesn't handle that."""
    u, z, x, y = _atom("u"), _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (u, x), (u, y), (x, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    # Both should find Z as IV (U is observed so backdoor could also
    # work, but get_instruments doesn't know that — it still reports Z)
    assert themis_ivs == dowhy_ivs == {"z"}


def test_parity_z_indirect_via_another_instrument():
    """Z1 → Z2 → X → Y. Z1 is an indirect IV (valid per Pearl)."""
    z1, z2, x, y = _atom("z1"), _atom("z2"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z1, z2), (z2, x), (x, y)])

    themis_ivs = _themis_basic_iv_instruments(g, x, y)
    dowhy_ivs = _dowhy_instruments(g, "x", "y")

    # Both implementations may differ here: DoWhy restricts candidates
    # to PARENTS of X (z2 only, not z1). Themis considers all nodes
    # (z1 qualifies via directed path). Document the divergence.
    assert "z2" in themis_ivs
    assert "z2" in dowhy_ivs
    # Themis finds z1 (transitive ancestor); DoWhy doesn't (restricted
    # to direct parents). This is a known semantic difference, not
    # a bug in either — both are valid IV definitions.
    assert "z1" in themis_ivs
    # DoWhy may or may not include z1 depending on implementation
    # details; we don't assert equality here.


# ==================================================== documented divergence


def test_divergence_on_admg_case_themis_stricter():
    """ADMG case where Z ↔ Y bidirected should reject Z as IV.

    DoWhy has no bidirected edge support, so this test exercises only
    Themis. The purpose is to document that Themis provides an
    identification capability DoWhy does not.
    """
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bidir = frozenset([frozenset({z, y})])

    # Themis with ADMG awareness rejects Z (IV3 violated)
    themis_admg = structural_solver.iv_sets(g, x, y, bidirected=bidir)
    assert themis_admg == ()

    # DoWhy with just the DAG (no bidirected info) would accept Z
    # because it can't see the latent shared cause.
    dowhy_ivs = _dowhy_instruments(g, "x", "y")
    assert dowhy_ivs == {"z"}  # DoWhy's answer for just-the-DAG view

    # This divergence is not a bug — it reflects Themis' strictly
    # larger modeling language (ADMG ⊃ DAG).
