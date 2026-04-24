"""Phase 5 §C / S.C.2: twin-network projection primitive.

This module does **not** solve counterfactual queries yet. It only
materializes the structural object that later slices consume:

- duplicate the base graph into factual / counterfactual worlds
- cut incoming edges into the counterfactual intervention node
- extend bidirected coupling across worlds so both copies share the
  same exogenous background

The projection is intentionally narrow and self-contained. No scheduler
integration lands here; callers import ``project_twin_network`` directly
and pin its shape in tests.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from ..types import Atom, CounterfactualQuery, Monotonicity, NumericInterval
from .structural_solver import BidirectedEdgeSet


TwinWorld = str
FACTUAL_WORLD: TwinWorld = "factual"
COUNTERFACTUAL_WORLD: TwinWorld = "counterfactual"


@dataclass(frozen=True)
class TwinAtom:
    """One endogenous variable in one world of the twin network."""

    atom: Atom
    world: TwinWorld


TwinBidirectedEdgeSet = frozenset[frozenset[TwinAtom]]


@dataclass(frozen=True)
class TwinNetwork:
    """Structural object produced by S.C.2.

    ``graph`` carries only directed edges. ``bidirected`` carries the
    latent-coupling surface, parallel to how ADMG support is represented
    elsewhere in Themis.
    """

    graph: nx.DiGraph
    bidirected: TwinBidirectedEdgeSet
    observed: TwinAtom
    counterfactual_intervention: TwinAtom
    counterfactual_target: TwinAtom


class CounterfactualBoundsError(ValueError):
    """Raised when the narrow S.C.3 solver preconditions are not met."""


def project_twin_network(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    query: CounterfactualQuery,
) -> TwinNetwork:
    """Project a base graph + bidirected set into a twin network.

    Rules:
    - every base node appears once in the factual world and once in the
      counterfactual world
    - every directed edge is copied into both worlds
    - incoming edges into the counterfactual intervention node are cut
    - same-variable cross-world coupling is always present
    - every original bidirected pair {A, B} expands into a complete
      bidirected coupling among {A_f, A_cf, B_f, B_cf}
    """

    base_nodes: set[Atom] = set(graph.nodes())
    for pair in bidirected:
        base_nodes.update(pair)
    base_nodes.update(
        {
            query.observed.atom,
            query.counterfactual_intervention.atom,
            query.counterfactual_target.atom,
        }
    )

    twin_graph = nx.DiGraph()

    def twin(atom: Atom, world: TwinWorld) -> TwinAtom:
        return TwinAtom(atom=atom, world=world)

    for atom in base_nodes:
        twin_graph.add_node(twin(atom, FACTUAL_WORLD))
        twin_graph.add_node(twin(atom, COUNTERFACTUAL_WORLD))

    intervention_cf = twin(
        query.counterfactual_intervention.atom, COUNTERFACTUAL_WORLD
    )

    for src, dst in graph.edges():
        twin_graph.add_edge(
            twin(src, FACTUAL_WORLD),
            twin(dst, FACTUAL_WORLD),
        )
        if twin(dst, COUNTERFACTUAL_WORLD) != intervention_cf:
            twin_graph.add_edge(
                twin(src, COUNTERFACTUAL_WORLD),
                twin(dst, COUNTERFACTUAL_WORLD),
            )

    bidir_pairs: set[frozenset[TwinAtom]] = set()

    # Every variable shares its exogenous background across the two worlds.
    for atom in base_nodes:
        bidir_pairs.add(
            frozenset(
                {twin(atom, FACTUAL_WORLD), twin(atom, COUNTERFACTUAL_WORLD)}
            )
        )

    # An original A ↔ B means the same latent background touches both
    # variables in both worlds. Represent that by fully coupling the four
    # relevant copies.
    for pair in bidirected:
        members = [
            twin(atom, world)
            for atom in pair
            for world in (FACTUAL_WORLD, COUNTERFACTUAL_WORLD)
        ]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                bidir_pairs.add(frozenset({members[i], members[j]}))

    return TwinNetwork(
        graph=twin_graph,
        bidirected=frozenset(bidir_pairs),
        observed=twin(query.observed.atom, FACTUAL_WORLD),
        counterfactual_intervention=intervention_cf,
        counterfactual_target=twin(
            query.counterfactual_target.atom, COUNTERFACTUAL_WORLD
        ),
    )


def balke_pearl_bounds_binary_monotone(
    twin: TwinNetwork,
    query: CounterfactualQuery,
    observed_joint_xy: dict[tuple[bool, bool], float],
) -> NumericInterval:
    """Narrow S.C.3 primitive for binary monotone bounds.

    Scope:
    - binary observed/intervention/target values only
    - explicit monotonicity already present on the query
    - input observational data supplied as the factual joint table
      ``P(X=x, Y=y)``

    This is intentionally not scheduler-integrated yet. S.C.4 decides
    when a missing monotonicity assumption becomes
    ``needs_assumption``; S.C.5 wires the primitive into runtime
    results.
    """

    if twin.observed.atom != query.observed.atom:
        raise CounterfactualBoundsError(
            "twin network/query mismatch: observed atom differs"
        )
    if twin.counterfactual_intervention.atom != query.counterfactual_intervention.atom:
        raise CounterfactualBoundsError(
            "twin network/query mismatch: intervention atom differs"
        )
    if twin.counterfactual_target.atom != query.counterfactual_target.atom:
        raise CounterfactualBoundsError(
            "twin network/query mismatch: target atom differs"
        )

    if query.assumptions is None or query.assumptions.monotonicity is None:
        raise CounterfactualBoundsError(
            "balke_pearl_bounds_binary_monotone requires an explicit monotonicity assumption"
        )

    values = (
        query.observed.value,
        query.counterfactual_intervention.value,
        query.counterfactual_target.value,
        query.factual_target_known,
    )
    for value in values:
        if value is not None and not isinstance(value, bool):
            raise CounterfactualBoundsError(
                "S.C.3 only supports boolean observed/intervention/target values"
            )

    expected_keys = {
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    }
    if set(observed_joint_xy) != expected_keys:
        raise CounterfactualBoundsError(
            "observed_joint_xy must contain exactly the four binary cells"
        )

    total = sum(observed_joint_xy.values())
    if abs(total - 1.0) > 1e-9:
        raise CounterfactualBoundsError(
            f"observed_joint_xy must sum to 1, got {total}"
        )
    if any(p < 0 or p > 1 for p in observed_joint_xy.values()):
        raise CounterfactualBoundsError(
            "observed_joint_xy probabilities must all lie in [0, 1]"
        )

    x_obs = query.observed.value
    x_cf = query.counterfactual_intervention.value
    y_star = query.counterfactual_target.value
    factual_y = query.factual_target_known
    monotonicity = query.assumptions.monotonicity

    p_x_obs = observed_joint_xy[(x_obs, False)] + observed_joint_xy[(x_obs, True)]
    if p_x_obs == 0:
        raise CounterfactualBoundsError(
            f"observed_joint_xy assigns zero mass to X={x_obs}"
        )
    p_y1_given_xobs = observed_joint_xy[(x_obs, True)] / p_x_obs

    if x_cf == x_obs:
        if factual_y is not None:
            point = 1.0 if factual_y == y_star else 0.0
        else:
            point = p_y1_given_xobs if y_star else 1.0 - p_y1_given_xobs
        return NumericInterval(low=point, high=point)

    if monotonicity is Monotonicity.NON_DECREASING:
        low_true, high_true = _bounds_non_decreasing(
            x_obs=x_obs,
            p_y1_given_xobs=p_y1_given_xobs,
            factual_y=factual_y,
        )
    elif monotonicity is Monotonicity.NON_INCREASING:
        low_true, high_true = _bounds_non_increasing(
            x_obs=x_obs,
            p_y1_given_xobs=p_y1_given_xobs,
            factual_y=factual_y,
        )
    else:
        raise CounterfactualBoundsError(
            f"unsupported monotonicity assumption {monotonicity!r}"
        )

    if y_star:
        return NumericInterval(low=low_true, high=high_true)
    return NumericInterval(low=1.0 - high_true, high=1.0 - low_true)


def _bounds_non_decreasing(
    *,
    x_obs: bool,
    p_y1_given_xobs: float,
    factual_y: bool | None,
) -> tuple[float, float]:
    if not x_obs:
        if factual_y is True:
            return 1.0, 1.0
        if factual_y is False:
            return 0.0, 1.0
        return p_y1_given_xobs, 1.0

    if factual_y is True:
        return 0.0, 1.0
    if factual_y is False:
        return 0.0, 0.0
    return 0.0, p_y1_given_xobs


def _bounds_non_increasing(
    *,
    x_obs: bool,
    p_y1_given_xobs: float,
    factual_y: bool | None,
) -> tuple[float, float]:
    if not x_obs:
        if factual_y is True:
            return 0.0, 1.0
        if factual_y is False:
            return 0.0, 0.0
        return 0.0, p_y1_given_xobs

    if factual_y is True:
        return 1.0, 1.0
    if factual_y is False:
        return 0.0, 1.0
    return p_y1_given_xobs, 1.0
