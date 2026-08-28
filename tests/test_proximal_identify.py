"""Structural identification for proximal causal inference (Miao-Geng-Tchetgen
2018 model (f); Kuroki-Pearl 2014 independent source).

D1 validation is two-pronged:

1. Worked examples transcribed edge-for-edge from Miao Fig. 1(d)/(e)/(f) and
   Kuroki-Pearl Fig. 1(b), asserting the model-(f) criteria admit them and the
   named refusals reject the broken variants.
2. An INDEPENDENT separation oracle: ``themis.runtime.structural_solver`` decides
   the criteria with its own hand-rolled m-path traversal; here we recompute the
   very same identifiability verdict with networkx's unrelated d-separation
   implementation and cross-check. The two engines must agree on every diagram.
   (Proximal diagrams are plain DAGs with a named — if unobserved — U, so
   d-separation is a valid oracle; no bidirected edges are involved.)
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.proximal_identify import (
    ProximalEstimand,
    ProximalNotIdentified,
    identify_proximal,
)
from themis.types import Atom, DiscreteChannel

NO_BIDIR = frozenset()


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, Y, U, Z, W, V = (A("x"), A("y"), A("u"), A("z"), A("w"), A("v"))


def _graph(edges) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from([X, Y, U, Z, W])
    g.add_edges_from(edges)
    return g


# --------------------------------------------------------------------------- #
# Independent d-separation oracle (networkx), recomputing the model-(f) verdict
# --------------------------------------------------------------------------- #
def _dsep(g, a, b, cond) -> bool:
    return nx.is_d_separator(g, {a}, {b}, set(cond))


def _oracle_identifiable(g) -> bool:
    """Model-(f) identifiability decided purely with networkx d-separation:
    {U} blocks every back-door path (checked on G with X's out-edges removed),
    W ⊥ Z | U, W ⊥ X | U, and Z ⊥ Y | {U, X}."""
    g_bar_x = g.copy()
    g_bar_x.remove_edges_from(list(g.out_edges(X)))
    return (
        _dsep(g_bar_x, X, Y, (U,))
        and _dsep(g, W, Z, (U,))
        and _dsep(g, W, X, (U,))
        and _dsep(g, Y, Z, (U, X))
    )


def _id(g, k=2):
    return identify_proximal(
        g, NO_BIDIR, treatment=X, outcome=Y, latent=U,
        treatment_proxy=Z, outcome_proxy=W,
        channel=DiscreteChannel(latent_cardinality=k),
    )


# --------------------------------------------------------------------------- #
# Worked examples — Miao Fig. 1(d)/(e)/(f), all special cases of model (f)
# --------------------------------------------------------------------------- #
# (d) both proxies are pure indicators of U: U→{X,Y,Z,W}, X→Y.
FIG_D = [(U, X), (U, Y), (U, Z), (U, W), (X, Y)]
# (e) Z is treatment-inducing (Z→X); W still pure: + Z→X.
FIG_E = [(U, X), (U, Y), (U, Z), (U, W), (Z, X), (X, Y)]
# (f) the general one: Z→X and W→Y both allowed.
FIG_F = [(U, X), (U, Y), (U, Z), (U, W), (Z, X), (W, Y), (X, Y)]


@pytest.mark.parametrize("edges", [FIG_D, FIG_E, FIG_F], ids=["fig_d", "fig_e", "fig_f"])
def test_worked_examples_identify(edges):
    g = _graph(edges)
    est = _id(g)
    assert isinstance(est, ProximalEstimand)
    assert est.treatment == X and est.outcome == Y and est.latent == U
    assert est.treatment_proxy == Z and est.outcome_proxy == W
    assert est.method == "proximal_matrix"
    assert est.channel.latent_cardinality == 2
    # the rank/relevance condition is deferred to the data, and disclosed
    assert any("秩条件" in c for c in est.data_conditions)
    # D1: the independent d-separation oracle agrees it is identifiable
    assert _oracle_identifiable(g) is True


def test_kuroki_pearl_fig1b_identifies():
    # Kuroki-Pearl Fig. 1(b): two conditionally-independent proxies of U, neither
    # touching X or Y directly — their model (d). Identifiable under model (f).
    g = _graph([(U, X), (U, Y), (U, Z), (U, W), (X, Y)])
    assert isinstance(_id(g), ProximalEstimand)
    assert _oracle_identifiable(g) is True


# --------------------------------------------------------------------------- #
# Structural refusals — each breaks exactly one model-(f) criterion
# --------------------------------------------------------------------------- #
def test_reject_dependent_proxies():
    # W → Z opens a W–Z path outside U: W ⊥ Z | U fails.
    g = _graph(FIG_F + [(W, Z)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "outcome_proxy_leaks_to_treatment_proxy"
    assert _oracle_identifiable(g) is False


def test_reject_outcome_proxy_causes_treatment():
    # W → X: W ⊥ X | U fails (W leaks to the treatment side).
    g = _graph(FIG_F + [(W, X)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "outcome_proxy_leaks_to_treatment"
    assert _oracle_identifiable(g) is False


def test_reject_treatment_proxy_causes_outcome():
    # Z → Y: Z ⊥ Y | (U, X) fails (Z leaks to the outcome side).
    g = _graph(FIG_F + [(Z, Y)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "treatment_proxy_leaks_to_outcome"
    assert _oracle_identifiable(g) is False


def test_reject_residual_confounding():
    # A second unobserved confounder V→X, V→Y that {U} cannot block: U is not a
    # sufficient confounder, so a single proxy pair cannot restore the effect.
    # Built on FIG_D (pure proxies, no Z→X) so the proxy criteria all hold and
    # the failure lands cleanly on the back-door check — NOT on Z⊥Y|{U,X}. (With
    # Z→X present, conditioning on X would open the collider path Z→X←V→Y and the
    # diagnosis would instead — correctly — flag the treatment proxy; that is a
    # genuine subtlety of proximal attribution, exercised separately below.)
    g = _graph(FIG_D)
    g.add_node(V)
    g.add_edges_from([(V, X), (V, Y)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "latent_not_sufficient"
    assert _oracle_identifiable(g) is False


def test_residual_confounder_with_collider_proxy_flags_treatment_proxy():
    # FIG_F (Z→X present) + second confounder V→X, V→Y. Conditioning on X to
    # test Z⊥Y|{U,X} opens the collider Z→X←V→Y, so the treatment-proxy leak
    # fires first. Documents that proximal attribution is path-dependent: the
    # SAME residual confounder surfaces under a different criterion depending on
    # whether the treatment proxy causes X.
    g = _graph(FIG_F)
    g.add_node(V)
    g.add_edges_from([(V, X), (V, Y)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "treatment_proxy_leaks_to_outcome"
    assert _oracle_identifiable(g) is False


def test_reject_latent_is_descendant_of_treatment():
    # X → U makes U a descendant of X — illegitimate as a back-door adjustment.
    g = _graph([(X, U), (U, Y), (U, Z), (U, W), (X, Y)])
    r = _id(g)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "latent_is_descendant"


def test_reject_degenerate_latent_cardinality():
    g = _graph(FIG_F)
    r = _id(g, k=1)
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "degenerate_latent"


def test_reject_missing_node():
    g = _graph(FIG_F)
    q = A("q")
    r = identify_proximal(
        g, NO_BIDIR, treatment=X, outcome=Y, latent=U,
        treatment_proxy=q, outcome_proxy=W,
        channel=DiscreteChannel(latent_cardinality=2),
    )
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "missing_node"


def test_reject_roles_not_distinct():
    g = _graph(FIG_F)
    r = identify_proximal(
        g, NO_BIDIR, treatment=X, outcome=Y, latent=U,
        treatment_proxy=Z, outcome_proxy=Z,
        channel=DiscreteChannel(latent_cardinality=2),
    )
    assert isinstance(r, ProximalNotIdentified)
    assert r.failed_criterion == "roles_not_distinct"


# --------------------------------------------------------------------------- #
# D1 exhaustive cross-check: Themis m-separation vs networkx d-separation must
# return the SAME identifiability verdict on every diagram above.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "edges,extra",
    [
        (FIG_D, []), (FIG_E, []), (FIG_F, []),
        (FIG_F, [(W, Z)]), (FIG_F, [(W, X)]), (FIG_F, [(Z, Y)]),
    ],
)
def test_engines_agree(edges, extra):
    g = _graph(edges + extra)
    themis_says = isinstance(_id(g), ProximalEstimand)
    assert themis_says is _oracle_identifiable(g)
