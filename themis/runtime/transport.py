"""Phase 9 §T9.1: Bareinboim-Pearl single-source transportability.

Implements the structural identification side of cross-population
causal effect transport, per Bareinboim & Pearl 2014 "A General
Algorithm for Deciding Transportability of Experimental Results".

S.T9.1 scope (single source, observable S, structural identification
only — no numeric estimation):

- ``build_selection_diagram``: G(M) ∪ {S → affects edges} from
  ground statements + selection node statements
- ``s_admissibility_check``: given selection diagram D, treatment
  X, outcome Y, candidate adjustment Z; return True iff Z d-separates
  the S nodes from Y in the intervention graph D_{\\bar{X}} (X's
  incoming edges removed)
- ``find_s_admissible_set``: enumerate subsets of pretreatment
  observed variables and return the smallest S-admissible Z, or
  None if no such set exists in the diagram
- ``identify_via_transport``: orchestrator — given a transport-shaped
  EffectQuery and the program's selection nodes, return either
  (Z, transport_formula) for identifiable cases or None for
  unidentifiable

Out-of-scope here (deferred to §T9.2 / §T9.3):
- numeric estimation of P(y|do(x), z) and P*(z) from data
- multi-source transport (Bareinboim 2014 §5)
- latent S nodes (S nodes pointing to unobserved variables)
- counterfactual transport (Bareinboim & Pearl 2013)

The selection diagram is built fresh per transport query — we do
NOT mutate the working graph G(M) used by other dispatch paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import networkx as nx

from ..types import Atom, CauseStatement, SelectionNode, Statement


# =========================================================== diagram


# Sentinel atom used internally to represent S nodes inside the
# selection diagram. The ``predicate`` collides with no real predicate
# (forbidden by atom schema's identifier pattern). The ``args[0].name``
# carries the SelectionNode id for traceability in derivation.
_S_PREDICATE_PREFIX = "__S__"


def _s_node_atom(s_node: SelectionNode) -> Atom:
    from ..types import ConstTerm
    return Atom(
        predicate=f"{_S_PREDICATE_PREFIX}{s_node.id}",
        args=(ConstTerm(name=s_node.id),),
    )


def is_s_node(atom: Atom) -> bool:
    return atom.predicate.startswith(_S_PREDICATE_PREFIX)


def build_selection_diagram(
    ground_statements: Iterable[Statement],
    base_graph: nx.DiGraph,
) -> tuple[nx.DiGraph, tuple[Atom, ...]]:
    """Build D = G(M) ∪ {S → affects edges} from selection node statements.

    Returns ``(D, s_atoms)`` where ``s_atoms`` is the tuple of S-node
    atoms added (one per SelectionNode statement). The original
    ``base_graph`` is not mutated.
    """
    diagram = base_graph.copy()
    s_atoms: list[Atom] = []
    for stmt in ground_statements:
        if not isinstance(stmt, SelectionNode):
            continue
        s_atom = _s_node_atom(stmt)
        s_atoms.append(s_atom)
        diagram.add_node(s_atom, atom=s_atom, kind="selection_node")
        # The S node itself doesn't need to be in V (it's never queried);
        # the affects atom must be in V (it's a regular variable). If
        # affects is missing from base_graph, fall through — d-sep on
        # a missing endpoint just returns False.
        if stmt.affects in diagram:
            diagram.add_edge(s_atom, stmt.affects, source=stmt)
    return diagram, tuple(s_atoms)


def _mutilate_incoming(graph: nx.DiGraph, node: Atom) -> nx.DiGraph:
    """G_{\\overline{X}}: remove all edges pointing INTO ``node``.

    This is Pearl 2009's overbar mutilation, the intervention graph
    used by Bareinboim 2014 Theorem 1 for transport identification."""
    g = graph.copy()
    g.remove_edges_from(list(g.in_edges(node)))
    return g


# =========================================================== check


@dataclass(frozen=True)
class TransportIdentificationResult:
    """Outcome of identify_via_transport."""
    identifiable: bool
    adjustment_set: tuple[Atom, ...]   # the Z that satisfies S-admissibility
    s_atoms: tuple[Atom, ...]          # S nodes in the diagram
    formula_repr: str                  # symbolic transport formula
    failure_reason: str | None = None  # populated when identifiable=False


def s_admissibility_check(
    diagram: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    s_atoms: tuple[Atom, ...],
) -> bool:
    """Bareinboim 2014 sufficient condition (Theorem 1, simplified):

    Z is S-admissible iff every S node is d-separated from Y given Z
    in D_{\\overline{X}} (the intervention graph).

    Z must consist of observed (non-S) atoms; this function does not
    enforce that — it's the caller's job to pass a valid candidate Z.
    """
    if x not in diagram or y not in diagram:
        return False
    g_bar_x = _mutilate_incoming(diagram, x)

    # Lazy import to avoid circular dep at module load time.
    from .structural_solver import is_d_connected

    for s in s_atoms:
        if s not in g_bar_x:
            # S node didn't reach the diagram (affects atom missing) —
            # vacuously d-separated, but really a structural error
            # caller should catch upstream. Treat as separated.
            continue
        # d-connected = path open ⇒ NOT d-separated. We want all S to
        # be d-separated from Y.
        if is_d_connected(g_bar_x, s, y, z):
            return False
    return True


def _pretreatment_observed_atoms(
    diagram: nx.DiGraph, x: Atom, s_atoms: tuple[Atom, ...]
) -> tuple[Atom, ...]:
    """Atoms eligible for inclusion in Z.

    "Pretreatment" = not a descendant of X (per Bareinboim 2014).
    "Observed" = not an S node and not the treatment / outcome itself.
    """
    if x not in diagram:
        return ()
    descendants_of_x = nx.descendants(diagram, x)
    s_set = frozenset(s_atoms)
    candidates = [
        n for n in diagram.nodes
        if n != x
        and n not in descendants_of_x
        and n not in s_set
    ]
    return tuple(candidates)


def find_s_admissible_set(
    diagram: nx.DiGraph,
    x: Atom,
    y: Atom,
    s_atoms: tuple[Atom, ...],
    max_size: int = 5,
) -> tuple[Atom, ...] | None:
    """Search for the smallest S-admissible Z, up to ``max_size`` atoms.

    Returns the empty tuple if Z=∅ already satisfies S-admissibility
    (no transport adjustment needed). Returns None if no Z within the
    size budget works.
    """
    candidates = _pretreatment_observed_atoms(diagram, x, s_atoms)
    # Try empty set first — the cheapest case.
    if s_admissibility_check(diagram, x, y, (), s_atoms):
        return ()
    for size in range(1, min(len(candidates), max_size) + 1):
        for subset in combinations(candidates, size):
            if s_admissibility_check(diagram, x, y, subset, s_atoms):
                return subset
    return None


# =========================================================== orchestrator


def transport_formula_repr(
    target: Atom,
    intervention: Atom,
    z: tuple[Atom, ...],
) -> str:
    """Render the Bareinboim transport formula symbolically.

    P*(y | do(x)) = Σ_z P(y | do(x), z) · P*(z)
    """
    y = target.predicate
    x = intervention.predicate
    if not z:
        return f"P*({y} | do({x})) = P({y} | do({x}))"
    z_names = ", ".join(a.predicate for a in z)
    return (
        f"P*({y} | do({x})) = "
        f"Σ_{{{z_names}}} P({y} | do({x}), {z_names}) · P*({z_names})"
    )


def identify_via_transport(
    diagram: nx.DiGraph,
    s_atoms: tuple[Atom, ...],
    treatment: Atom,
    outcome: Atom,
) -> TransportIdentificationResult:
    """Run Bareinboim Theorem 1 sufficient-condition transport identification.

    Returns a TransportIdentificationResult; check ``.identifiable``
    before reading ``.adjustment_set`` / ``.formula_repr``.
    """
    if not s_atoms:
        # No S nodes declared → diagram is just G(M); transport is
        # trivially the same as the source effect (Z=∅, formula reduces
        # to identity). This is technically still "transportable", but
        # the user gets no value beyond a regular effect query.
        return TransportIdentificationResult(
            identifiable=True,
            adjustment_set=(),
            s_atoms=(),
            formula_repr=transport_formula_repr(outcome, treatment, ()),
            failure_reason=None,
        )

    if treatment not in diagram or outcome not in diagram:
        return TransportIdentificationResult(
            identifiable=False,
            adjustment_set=(),
            s_atoms=s_atoms,
            formula_repr="",
            failure_reason=(
                f"处理 {treatment.predicate} 或结局 "
                f"{outcome.predicate} 不在选择图中"
            ),
        )

    z = find_s_admissible_set(diagram, treatment, outcome, s_atoms)
    if z is None:
        return TransportIdentificationResult(
            identifiable=False,
            adjustment_set=(),
            s_atoms=s_atoms,
            formula_repr="",
            failure_reason=(
                "找不到 S-可容许的调整集 Z；在所声明的选择图下，"
                "源人群的效应无法迁移到目标人群"
                "（Bareinboim 2014 定理 1 的充分条件不成立）"
            ),
        )

    return TransportIdentificationResult(
        identifiable=True,
        adjustment_set=z,
        s_atoms=s_atoms,
        formula_repr=transport_formula_repr(outcome, treatment, z),
        failure_reason=None,
    )
