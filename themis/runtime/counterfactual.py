"""Twin-network projection + single-cell binary counterfactual solving.

``project_twin_network`` materializes the structural object: the base
graph duplicated into factual / counterfactual worlds, incoming edges
into the counterfactual intervention node cut, and bidirected coupling
extended across worlds so both copies share the same exogenous
background.

``counterfactual_cell_interval`` answers ``P(Y_{x'} = y* | X = x [, Y =
y])`` for binary X, Y from the observational joint plus the
interventional risk ``P(Y=1 | do(x'))``, with monotonicity — when
declared — as an optional extra constraint rather than a precondition.
Its docstring carries the single identity everything else follows from.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .. import refusals
from ..refusals import Refusal
from ..ledger import Monotonicity
from ..types import Atom, CounterfactualQuery, NumericInterval
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


class CounterfactualBoundsError(refusals.EstimatorFailure):
    """Raised when the narrow S.C.3 solver will not answer, and why.

    An :class:`~themis.refusals.EstimatorFailure` rather than a family of
    its own. Two layers catch this and both put it on an envelope — the
    data end in :mod:`themis.estimation.counterfactual_cell` and the θ end
    in :mod:`themis.runtime.scheduler` — so what they need from it is
    exactly what a refusal carries: the species, and the occasion's facts
    for the species' sentence to interpolate. Carrying a MESSAGE instead
    is what made this module the author of fourteen sentences, in one
    language, for a table that has a place for every one of them; the two
    handlers relayed that text with ``str(exc)`` and the count of authors
    never saw any of it, because it reads the name at the door and this
    name is not one of them.

    The species arrives at the raise site. A subclass fixes one because
    its whole reason for existing is that a caller catches it by name and
    acts on which failure it is; the base class does not, because ten of
    its sites say ten different things and one name over ten facts is the
    arrangement #405 spent five cuts removing.
    """

    #: A subclass' own. ``None`` on the base is what makes the raise site
    #: name one, rather than inheriting a name chosen for another failure.
    species: Refusal | None = None

    def __init__(self, species: Refusal | None = None, **occasion) -> None:
        # ``occasion`` is the base's own keyword surface — the sentence's
        # slots, plus ``recorded`` and ``remedies`` — forwarded whole so
        # this layer never has to be edited when that surface grows.
        chosen = species if species is not None else type(self).species
        if chosen is None:
            raise TypeError(
                f"{type(self).__name__} was raised without a species; name "
                f"the refusal in themis.refusals that describes this case"
            )
        super().__init__(chosen, **occasion)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "species" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} inherits its refusal species from "
                f"{cls.__mro__[1].__name__}; declare the one that describes "
                f"this case in themis.refusals and name it here"
            )


class InterventionalRiskRequired(CounterfactualBoundsError):
    """The requested counterfactual cell cannot be bounded from the
    observational joint alone — it needs ``P(Y=1 | do(X=x_cf))``.

    Carries the intervention arm that is needed so the caller can go and
    identify exactly that one (and only that one). Raised instead of
    returning a vacuous ``[0, 1]``: an uninformative interval that *looks*
    like an answer is worse than a gap that names its own remedy.
    """

    species = Refusal.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE

    @property
    def needed_x_value(self) -> bool:
        """The arm the caller has to go and identify.

        Read back out of the occasion rather than stored beside it: it is
        the sentence's one slot and the one thing a catcher wants, and a
        second copy of it under a second name is a second copy. Keeping it
        as an attribute would also mean the raise site naming the
        attribute instead of the slot, which is the shape that lets a
        sentence and its sites drift apart without a gate seeing it.
        """
        return self.details["intervention"]


class CounterfactualInfeasible(CounterfactualBoundsError):
    """The declared monotonicity is refuted by what was supplied.

    Distinct from a malformed input so callers can report "the assumption
    is refuted" instead of "this query is outside the language", and
    distinct from the sources contradicting each other, which is
    ``inputs_contradict_by_consistency`` and blames no assumption. Two
    resample counters catch this by name to count the draws a declared
    monotonicity cannot survive, which is why it stays a subclass.
    """

    species = Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE


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



_TOL = 1e-9


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def monotonicity_pins(query: CounterfactualQuery) -> dict[bool, float]:
    """Which counterfactual cells does monotonicity pin *deterministically*?

    A cell here is ``P(Y_{x'}=1 | X=x, Y=y)`` indexed by the factual ``y``;
    ``x'`` is the counterfactual intervention and ``x != x'``. Monotonicity
    plus consistency fixes exactly one of the two cells at 0 or 1, because
    consistency already tells us the unit's potential outcome under its OWN
    treatment, and the monotone order then forces the other one:

        non-decreasing (Y_{x=0} <= Y_{x=1}), observed x=1  ->  Y_1 = y
            y = 0 forces Y_0 = 0            -> cell(y=0) = 0
        non-decreasing, observed x=0        ->  Y_0 = y
            y = 1 forces Y_1 = 1            -> cell(y=1) = 1
        non-increasing (Y_{x=1} <= Y_{x=0}), observed x=1  ->  Y_1 = y
            y = 1 forces Y_0 = 1            -> cell(y=1) = 1
        non-increasing, observed x=0        ->  Y_0 = y
            y = 0 forces Y_1 = 0            -> cell(y=0) = 0

    The OTHER cell is exactly the one monotonicity says nothing about on its
    own — for (x=1, y=1) that cell is PN, for (x=0, y=0) it is PS. Those are
    the cells that need the interventional risk, and the linear consistency
    constraint in :func:`counterfactual_cell_interval` is what turns the pin
    on one cell into a point on the other (recovering Tian-Pearl's monotone
    point identification as a consequence rather than a second formula).

    Returns ``{}`` when the query declares no monotonicity.
    """
    if query.assumptions is None or query.assumptions.monotonicity is None:
        return {}
    x_obs = query.observed.value
    monotonicity = query.assumptions.monotonicity
    if monotonicity == Monotonicity.NON_DECREASING:
        return {False: 0.0} if x_obs else {True: 1.0}
    if monotonicity == Monotonicity.NON_INCREASING:
        return {True: 1.0} if x_obs else {False: 0.0}
    raise CounterfactualBoundsError(
        Refusal.INVALID_MONOTONICITY, declared=monotonicity,
    )


def _require_binary(value: object, role: str) -> bool:
    """Narrow one query value to the boolean the S.C.3 program is written in.

    ``factual_target_known`` is the single place where absence means
    something — the factual outcome is not part of the evidence — and the
    caller passes that one through before asking. Everywhere else a missing
    value is not a third case this solver could answer: it would reach a
    lookup in the binary joint, or a truth test that silently reads it as
    ``False`` and returns the complementary cell's number.
    """
    if not isinstance(value, bool):
        raise CounterfactualBoundsError(
            Refusal.COUNTERFACTUAL_CELL_NOT_BINARY, label=role, given=value,
        )
    return value


def _validate_cell_inputs(
    twin: TwinNetwork,
    query: CounterfactualQuery,
    observed_joint_xy: dict[tuple[bool, bool], float],
) -> tuple[bool, bool, bool, bool | None]:
    """Check twin/query/joint agree, and hand back the four cell values.

    Returning them is what makes the rest of the solver total: ``x``, ``x'``
    and ``y*`` are booleans from here on, and ``y`` is the only one that may
    be absent — which is exactly the shape every line below assumes.
    """
    # Not refusals, and this is the one place in this module that says so.
    # A twin network is projected FROM a query, and both callers project
    # the one they then pass; reaching here means a caller of this public
    # function paired two objects that were never about the same cell.
    # There is no sentence for a reader in that, because no reader can
    # cause it — filing it as a refusal would put a species on an envelope
    # to describe a bug in the code that built the envelope.
    for part, mine, theirs in (
        ("observed", twin.observed, query.observed),
        ("counterfactual_intervention",
         twin.counterfactual_intervention, query.counterfactual_intervention),
        ("counterfactual_target",
         twin.counterfactual_target, query.counterfactual_target),
    ):
        if mine.atom != theirs.atom:
            raise ValueError(
                f"twin network/query mismatch: the twin's {part} is "
                f"{mine.atom} and the query's is {theirs.atom}; the twin has "
                f"to be the one projected from this query"
            )

    x_obs = _require_binary(query.observed.value, "observed")
    x_cf = _require_binary(
        query.counterfactual_intervention.value, "counterfactual_intervention"
    )
    y_star = _require_binary(
        query.counterfactual_target.value, "counterfactual_target"
    )
    factual_y = (
        None if query.factual_target_known is None
        else _require_binary(
            query.factual_target_known, "factual_target_known"
        )
    )

    expected_keys = {
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    }
    if set(observed_joint_xy) != expected_keys:
        raise CounterfactualBoundsError(
            Refusal.MALFORMED_ARGUMENT,
            argument="observed_joint_xy",
            shape="{(X, Y): P} over the four (False/True) pairs",
            given=sorted(observed_joint_xy, key=str),
        )

    total = sum(observed_joint_xy.values())
    if abs(total - 1.0) > _TOL:
        raise CounterfactualBoundsError(
            Refusal.PROBABILITIES_DO_NOT_SUM,
            what="observed_joint_xy", given=total,
        )
    outside = [p for p in observed_joint_xy.values() if p < 0 or p > 1]
    if outside:
        raise CounterfactualBoundsError(
            Refusal.NOT_A_PROBABILITY,
            what="observed_joint_xy", given=outside,
        )

    return x_obs, x_cf, y_star, factual_y


def counterfactual_cell_interval(
    twin: TwinNetwork,
    query: CounterfactualQuery,
    observed_joint_xy: dict[tuple[bool, bool], float],
    *,
    p_y_do_x_cf: float | None = None,
) -> NumericInterval:
    """Bounds (or a point) for one binary counterfactual cell.

    The quantity is ``P(Y_{x'} = y* | X = x [, Y = y])`` where ``x`` is the
    observed factual treatment, ``x'`` the counterfactual intervention,
    ``y*`` the counterfactual target value, and ``y`` the optional factual
    outcome (``query.factual_target_known``).

    Everything below the ``x' == x`` shortcut rests on ONE identity. Write
    ``a = P(Y_{x'}=1 | X=x, Y=1)`` and ``b = P(Y_{x'}=1 | X=x, Y=0)``. Then

        a * P(x, Y=1) + b * P(x, Y=0)  =  P(Y=1 | do(x'))  -  P(x', Y=1)

    because the left-hand side is ``P(Y_{x'}=1 | X=x) * P(x)`` and, by
    consistency, ``P(Y_{x'}=1, X=x') = P(Y=1, X=x')`` carves the rest of
    ``P(Y_{x'}=1)`` off. So one linear equation ties the two cells together,
    each of them lives in ``[0, 1]``, and monotonicity — when declared —
    pins one of them outright (see :func:`monotonicity_pins`). Every answer
    this function gives is that little program solved for the cell asked for:

    - ``y`` unknown: the target IS the left-hand side over ``P(x)``, so it
      is point-identified outright (the ETT identity) — not bounded.
    - ``y`` known, other cell free: the box ``[0, 1]`` on the other cell
      maps through the equation to an interval. For (x=1, y=1, y*=0) this
      reproduces the Tian-Pearl PN bounds (eq. 25) term for term, and for
      (x=0, y=0, y*=1) the PS bounds (eq. 26).
    - ``y`` known, other cell pinned by monotonicity: the equation leaves a
      single value — Tian-Pearl's monotone point identification (eqs. 41-42)
      falls out, rather than being transcribed a second time.

    ``p_y_do_x_cf`` is ``P(Y=1 | do(X=x'))``, however the caller obtained it
    (identification from theta, or a randomized experiment). It may be
    omitted only when the answer does not depend on it — the ``x' == x``
    consistency case and a cell monotonicity pins directly. Otherwise
    :class:`InterventionalRiskRequired` names the arm that is needed.
    """
    x_obs, x_cf, y_star, factual_y = _validate_cell_inputs(
        twin, query, observed_joint_xy
    )

    p_x_obs = observed_joint_xy[(x_obs, False)] + observed_joint_xy[(x_obs, True)]
    if p_x_obs == 0:
        raise CounterfactualBoundsError(
            Refusal.UNDEFINED_CONDITIONING_EVENT,
            event=f"{query.observed.atom.predicate}={x_obs}",
        )

    # Same world on both sides: consistency answers it outright, and no
    # interventional information is involved.
    if x_cf == x_obs:
        if factual_y is not None:
            point = 1.0 if factual_y == y_star else 0.0
        else:
            p_y1 = observed_joint_xy[(x_obs, True)] / p_x_obs
            point = p_y1 if y_star else 1.0 - p_y1
        return NumericInterval(low=point, high=point)

    pins = monotonicity_pins(query)

    if p_y_do_x_cf is None:
        if factual_y is not None and factual_y in pins:
            pinned = pins[factual_y]
            value = pinned if y_star else 1.0 - pinned
            return NumericInterval(low=value, high=value)
        raise InterventionalRiskRequired(intervention=x_cf)

    if not (0.0 <= p_y_do_x_cf <= 1.0):
        raise CounterfactualBoundsError(
            Refusal.NOT_A_PROBABILITY,
            what=f"P(Y=1 | do(X={x_cf}))", given=p_y_do_x_cf,
        )

    # K = P(Y_{x'}=1 | X=x) * P(x), the right-hand side of the identity.
    k = p_y_do_x_cf - observed_joint_xy[(x_cf, True)]
    if not (-_TOL <= k <= p_x_obs + _TOL):
        # Not the subclass: nothing here is refuted, the two sources
        # disagree. Blaming the monotonicity would send a caller who
        # declared none looking for one to drop.
        raise CounterfactualBoundsError(
            Refusal.INPUTS_CONTRADICT_BY_CONSISTENCY,
            intervention=x_cf, given=p_y_do_x_cf,
            lower=observed_joint_xy[(x_cf, True)],
            upper=observed_joint_xy[(x_cf, True)] + p_x_obs,
        )

    if factual_y is None:
        point = _clamp01(k / p_x_obs)
        value = point if y_star else 1.0 - point
        return NumericInterval(low=value, high=value)

    w_target = observed_joint_xy[(x_obs, factual_y)]
    w_other = observed_joint_xy[(x_obs, not factual_y)]
    lo_other, hi_other = pins.get(not factual_y, 0.0), pins.get(not factual_y, 1.0)
    lo_target, hi_target = pins.get(factual_y, 0.0), pins.get(factual_y, 1.0)

    if w_target > 0.0:
        # target = (K - other * w_other) / w_target, decreasing in `other`.
        lo_target = max(lo_target, (k - hi_other * w_other) / w_target)
        hi_target = min(hi_target, (k - lo_other * w_other) / w_target)
    # w_target == 0 means the conditioning event {X=x, Y=y} has zero mass, so
    # the cell is undefined; the box (plus any pin) is all there is to say.

    # Emptiness is decided BEFORE clamping: clamping first would fold an
    # empty feasible set back onto the boundary and report a confident
    # 0 or 1 for a cell no distribution can produce. Without a pin the
    # intersection is provably non-empty, so reaching here means the
    # declared monotonicity is what the data refute.
    if lo_target > hi_target + _TOL:
        raise CounterfactualInfeasible(
            refuted_by=refusals.Refutation.CELL_FEASIBLE_SET,
            recorded={"interventional_risk": p_y_do_x_cf,
                      "intervention": x_cf},
        )
    lo_target, hi_target = _clamp01(lo_target), _clamp01(hi_target)
    hi_target = max(hi_target, lo_target)

    if y_star:
        return NumericInterval(low=lo_target, high=hi_target)
    return NumericInterval(low=1.0 - hi_target, high=1.0 - lo_target)
