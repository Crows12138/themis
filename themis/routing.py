"""Which strategy owns a query — decided once, read by both layers.

Whether a query belongs to transport or to mediation, and whether an
assumption-free estimand outranks an assumption-laden one, are facts about
the *question*. Neither is a fact about identification or about estimation,
and until this module existed each layer answered them separately:
identification as a chain of ``if`` statements inside ``_dispatch_effect``,
estimation as a table. Two copies of one decision drifted five times that
were measured — three on order (findings A and C among them), one on
reachability (D: a branch written inside the wrong copy, so conditional
identification was unreachable without latent confounding), and one on
coverage (E: a constraint written as the first line of one handler, so the
other layer answered a conditional query with an unconditional Wald).

Here the decision is data: an id, a precedence, a guard, and which *ends*
the strategy has. Each layer binds its own implementation to the ids, and
:func:`bind` refuses a binding set that does not cover exactly the routes
declaring that end — so a strategy added to the table without an
implementation fails at import rather than by going quietly unreachable.

**Guards are pure functions of facts, and the facts are what the layer can
see.** :class:`StructuralFacts` holds what both layers have: the query, the
graph, and what the solver makes of them. A guard for a route with only a
numeric end may name attributes that only the estimation layer's facts
carry; evaluating it anywhere else raises rather than silently reading a
default. That is the same discipline that keeps guards from reading their
own layer's output — the attribute is absent, so the mistake cannot compile
into a branch.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from typing import Any, Callable, Mapping, TypeVar


class End(StrEnum):
    """The two places a strategy can have an implementation.

    An identification end turns the query into an estimand — a formula and
    the assumptions it rests on. A numeric end turns data into a number for
    that estimand. Most strategies have both. Some genuinely have one:
    measurement-error correction is a numeric end with no identification
    counterpart (the identification layer never sees a DataFrame), and the
    longitudinal g-formula routes on ``options.longitudinal``, which does
    not reach the estimation layer at all.
    """

    IDENTIFICATION = "identification"
    ESTIMATION = "estimation"


BOTH = frozenset({End.IDENTIFICATION, End.ESTIMATION})
IDENTIFIES = frozenset({End.IDENTIFICATION})
ESTIMATES = frozenset({End.ESTIMATION})


@dataclass(frozen=True)
class Route:
    """One strategy's claim on a query: when it applies, and how early.

    ``precedence`` is a number rather than a source line so that "transport
    outranks mediation" is a statement two layers can be checked against
    instead of a coincidence between two files. ``ends`` is not a label —
    it is what :func:`bind` enforces.

    Precedence says who answers. It does not say that anyone LOST, and two
    guards can hold at once: a query naming both a mediator and a target
    population is claimed by both rows, and the dispatcher returns at the
    first one without ever evaluating the second. ``displaces`` is that
    missing half — the rows this one can take a query away from, each
    answering a question this one does not answer in passing. What made it
    necessary is that the fact was being rebuilt downstream instead:
    ``data_gap_report`` read back which extension came out non-empty to
    infer which layer had been skipped, so the disclosure depended on a
    layer failing to leave residue rather than on the dispatcher saying
    what it did. Only one of the pairs that can occur was covered that way,
    and two more had their scope written in a query field's docstring,
    which is prose.

    ``triggered_by`` names the declaration that makes this row claim a
    query. It is what lets the disclosure say which field to remove to get
    the other layer, and :func:`_check` requires it from both sides of any
    displacement — a displacement nobody could act on should not be
    declarable.
    """

    id: str
    precedence: int
    applies_when: Callable[[Any], Any]
    ends: frozenset[End]
    triggered_by: str = ""
    displaces: frozenset[str] = frozenset()
    after_the_answer: bool = False
    """Whether this row runs once the query has been answered rather than in
    the race to answer it.

    Precedence orders COMPETITORS, and a row that only annotates is not one —
    it is a disclosure ABOUT whichever estimand won. Most disclosures can be
    made early anyway, so the distinction stayed invisible until one could
    not: the precision cost of a mismeasured outcome is taken, on the
    instrumental-variable design, around β̂ itself, and no row that runs
    before the estimators can see β̂. Fixing that by recomputing β̂ early
    would put a second copy of the shipped number in the envelope, free to
    disagree with it the moment a different IV row answers.

    So the axis gets a second half rather than a workaround. A row here may
    not claim a query — there is nothing left to claim — and may not stop
    one, because stopping after the fact would mean withdrawing an answer
    already written; :func:`themis.estimation.strategy.check_table` enforces
    the first and the cascade the second."""


class StructuralFacts:
    """What a guard may look at in either layer.

    The query, the graph, and the solver's verdicts on them — no data, no
    theta, and above all no result. A guard branching on what the current
    pass has already produced is how the estimation layer came to route on
    a method NAME left behind by an earlier pass; there is no attribute
    here to make that mistake with.

    Everything structural is derived on first use. A query answered by the
    first route must not pay for an adjustment-set search, and more to the
    point must not be *broken* by one: running solver code on query shapes
    it has never been offered would make the table change reachability, and
    a table is supposed to change routing.
    """

    def __init__(self, *, q_stmt: Any, graph: Any, bidirected: Any) -> None:
        self.q_stmt = q_stmt
        self.query = q_stmt.query
        self.graph = graph
        self.bidirected = bidirected

    # --- the query's own atoms ------------------------------------------

    @cached_property
    def x_atom(self) -> Any:
        return self.query.intervention.atom

    @cached_property
    def y_atom(self) -> Any:
        return self.query.target.atom

    @cached_property
    def given_atoms(self) -> tuple:
        return tuple(g.atom for g in self.query.given)

    # --- structural facts, solved once ----------------------------------

    @cached_property
    def adjustment_sets(self) -> tuple:
        from .runtime import structural_solver

        return structural_solver.minimal_adjustment_sets(
            self.graph, self.x_atom, self.y_atom,
            given=self.given_atoms,
            bidirected=self.bidirected or None,
        )

    @cached_property
    def chosen_adjustment(self) -> tuple:
        """The smallest valid back-door set — the one both ends use."""
        return min(self.adjustment_sets, key=len)

    @cached_property
    def front_door_sets(self) -> tuple:
        """Empty when the query conditions on anything.

        The front-door formula has no conditional form here. Folding that
        into the fact — rather than nesting the branch under an ``if not
        given`` in each layer — is what lets the two layers share one
        guard instead of two that agree by inspection.
        """
        if self.given_atoms:
            return ()
        from .runtime import structural_solver

        return structural_solver.front_door_sets(
            self.graph, self.x_atom, self.y_atom,
            bidirected=self.bidirected or None,
        )

    @cached_property
    def iv_candidates(self) -> tuple:
        """Empty when the query conditions on anything — as for front-door.

        A Wald ratio is an unconditional two-point contrast; there is no
        conditional form of it here, and the instrument's own conditioning
        set W is not the query's ``given`` (they coincide only by
        accident). Estimating one anyway answers a different question.

        That refusal used to live as the first line of the identification
        handler rather than in a guard, so it applied to exactly the one
        call site that contained it: the estimation layer, whose guard was
        written separately, shipped a stratified Wald as the answer to
        ``P(Y|do(X), C=c)`` — the same number for c=True and c=False, so it
        could not have been an answer to either. Stated as a fact it binds
        every IV row in both layers.
        """
        if self.given_atoms:
            return ()
        from .runtime import structural_solver

        return structural_solver.iv_sets(
            self.graph, self.x_atom, self.y_atom,
            bidirected=self.bidirected or None,
        )

    @cached_property
    def overid_instruments(self) -> tuple:
        """Instruments valid under the SAME smallest conditioning set.

        Two or more of them form one over-identified system, whose Sargan
        test can refute the instruments jointly — falsification power that
        picking a single instrument throws away.
        """
        if not self.iv_candidates:
            return ()
        w0 = self.iv_candidates[0].conditioning
        return tuple(sorted(
            (c.instrument for c in self.iv_candidates if c.conditioning == w0),
            key=lambda a: a.predicate,
        ))


# ---------------------------------------------------------------------------
# The table.
#
# One precedence axis in three bands, and then a half. 10-50 route on the
# SHAPE of the question — what the query names, before any graph is
# consulted. 60-140 belong to the data: corrections and estimator choices the
# identification layer cannot see. 150-190 are the structural ladder, ordered
# so that an assumption-free estimand always outranks an assumption-laden one
# — the ordering finding C was made of, when declaring monotonicity replaced
# a population effect with a complier contrast.
#
# The bands interleave on one axis rather than living in three tables
# because the question "who answers this query" has one answer.
#
# 200 and up answer a different question: not who answers, but what is said
# ABOUT the answer once it exists (``Route.after_the_answer``). They are on
# the same axis because they are declared the same way and guarded the same
# way; they are past the ladder because nothing there is competing.
# ---------------------------------------------------------------------------

EFFECT_ROUTES: tuple[Route, ...] = (
    Route(
        # Phase 7.L: a time-varying treatment declared via
        # options.longitudinal, which the cross-sectional query grammar
        # cannot carry. Ranked first because the single-treatment back-door
        # path below would silently compute the biased static-adjustment
        # ATE — the very estimator the g-formula exists to replace.
        #
        # No numeric end here: the longitudinal estimate is attached by a
        # pass that runs before this cascade. The guard names a fact only
        # the identification layer's facts carry, so it cannot be evaluated
        # in the layer that has no implementation for it.
        #
        # It displaces every shape row below it. A time-varying treatment
        # is standardized sequentially along ONE treatment trajectory, in
        # the sample's own population, for the total effect: a joint
        # contrast over a treatment set, a carry to another population, and
        # a direct/indirect split (which would need sequential
        # ignorability for time-varying mediators) are each a different
        # quantity this row does not produce on the way past.
        id="longitudinal",
        precedence=10,
        applies_when=lambda f: f.declares_longitudinal,
        ends=IDENTIFIES,
        triggered_by="options.longitudinal",
        displaces=frozenset({
            "joint_intervention", "transport",
            "mediation_joint", "mediation_single",
        }),
    ),
    Route(
        # Joint interventions: do(A=a, B=b, ...) over a treatment SET — the
        # joint contrast plus its treatment×treatment interaction, which no
        # sequence of single-treatment estimates recovers.
        #
        # Its v1 scope — no mediator and no target population alongside the
        # joint — was written in ``extra_interventions``' own docstring,
        # where nothing could act on it. Declared here it becomes the
        # disclosure the reader gets.
        id="joint_intervention",
        precedence=20,
        applies_when=lambda f: bool(f.query.extra_interventions),
        ends=BOTH,
        triggered_by="extra_interventions",
        displaces=frozenset({
            "transport", "mediation_joint", "mediation_single",
        }),
    ),
    Route(
        # Phase 9 §T9.1.3: carry the effect to a declared target population
        # (Bareinboim 2014).
        #
        # Ranked ABOVE mediation, which is the identification layer's
        # long-standing order and now the only one. A query naming both a
        # mediator and a target population has one owner, and transport
        # says so out loud (unattempted_layer_due_to_dispatch_conflict)
        # rather than answering one layer and dropping the other in
        # silence. While the two layers disagreed here, the estimation
        # cascade reached transport only by having mediation stand down
        # first — a hand-off that had to be declared as a substitution
        # because the estimands differ. One number for the order removes
        # both the hand-off and the declaration.
        #
        # Mediation and transport are sequential operations (Cole & Stuart
        # 2010; VanderWeele 2016 §6.2) — decompose in the source
        # population, then carry each component — so one dispatch cannot be
        # both.
        id="transport",
        precedence=30,
        applies_when=lambda f: f.query.target_population is not None,
        ends=BOTH,
        triggered_by="target_population",
        displaces=frozenset({"mediation_joint", "mediation_single"}),
    ),
    Route(
        # The JOINT natural-effect decomposition through the mediator SET
        # as one block (VanderWeele-Vansteelandt 2014), ranked before the
        # single-mediator path: treating the set as a block is what makes
        # it identifiable without assuming an ordering among the mediators.
        #
        # The guard is "did this query name a set", not "how big is it".
        # A block of one is still a block — the estimator is byte-identical
        # at k=1 — and ``mediators`` and ``mediator`` are distinct fields,
        # so a size threshold would not divert k=1 to the single-mediator
        # row. It would drop the decomposition and answer the total effect
        # instead, beside an envelope still claiming the block. That was
        # finding A.
        #
        # A query naming the block AND a single mediator is claimed twice.
        # The block's joint NDE/NIE does not contain the path-specific
        # split through one of its members — that split is out of scope
        # here precisely because it needs assumptions the block does not —
        # so the singular field is not answered in passing.
        id="mediation_joint",
        precedence=40,
        applies_when=lambda f: bool(f.query.mediators),
        ends=BOTH,
        triggered_by="mediators",
        displaces=frozenset({"mediation_single"}),
    ),
    Route(
        # Phase 6.mediation: NDE / NIE / CDE through a single named
        # mediator, rather than the plain total effect.
        id="mediation_single",
        precedence=50,
        applies_when=lambda f: f.query.mediator is not None,
        ends=BOTH,
        triggered_by="mediator",
    ),
    Route(
        # §S9.1: the sample is restricted on a selection collider, so the
        # ordinary back-door number below would be silently biased — it
        # standardizes over a collider-conditioned sample. This row either
        # recovers the number from external reference data or refuses while
        # naming what it needs; either way the query never reaches
        # back-door. The guard reads the identification layer's conclusion,
        # which is the layer boundary working, not a result being sniffed.
        id="selection_recovery",
        precedence=60,
        applies_when=lambda f: f.selection_recovery is not None,
        ends=ESTIMATES,
    ),
    Route(
        # Frontier E, both channels: a validated confusion matrix for the
        # exposure AND the outcome. Invert both sides of the per-stratum
        # (X, Y) joint at once — correcting one and shipping the point
        # would leave the other channel's bias in the number.
        id="measurement_correction_both_channels",
        precedence=70,
        applies_when=lambda f: (
            f.misclassification_outcome is not None
            and f.misclassification_exposure is not None
        ),
        ends=ESTIMATES,
    ),
    Route(
        # Frontier E (outcome side): de-attenuate the misclassified binary
        # outcome by inverting the matrix per back-door stratum.
        id="measurement_correction_outcome",
        precedence=80,
        applies_when=lambda f: f.misclassification_outcome is not None,
        ends=ESTIMATES,
    ),
    Route(
        # Frontier E (exposure side): invert M on the X-margin per
        # back-door stratum instead of shipping the attenuated number.
        id="measurement_correction_exposure",
        precedence=90,
        applies_when=lambda f: f.misclassification_exposure is not None,
        ends=ESTIMATES,
    ),
    Route(
        # The outcome channel is the one that costs no bias: a classical
        # additive error leaves every conditional mean — and so every
        # estimand here — untouched. There is nothing to de-attenuate, so
        # this row comments rather than competing.
        #
        # Two questions were fused under that heading, and they sit on
        # opposite sides of the answer. Whether the DECLARATION can be true
        # of this sample has to be settled first, because its answer can stop
        # the query — a discrete outcome is misclassification, which does
        # attenuate, and a σ²_v that will not fit under the unexplained
        # variation puts in doubt the independence premise the point rested
        # on. That is this row.
        id="outcome_error_declaration",
        precedence=100,
        applies_when=lambda f: f.measurement_error_outcome is not None,
        ends=ESTIMATES,
    ),
    Route(
        # And what the noise COSTS cannot be settled until there is an
        # estimator to cost: on the instrumental-variable design the split is
        # taken around β̂. Same guard, same facts, the other side of the
        # answer — see ``Route.after_the_answer``.
        id="outcome_error_precision_cost",
        precedence=200,
        applies_when=lambda f: f.measurement_error_outcome is not None,
        ends=ESTIMATES,
        after_the_answer=True,
    ),
    Route(
        # Continuous mismeasurement (regression calibration): a known
        # classical additive error variance for the exposure (regression
        # dilution) and/or a back-door covariate (residual confounding).
        id="regression_calibration",
        precedence=110,
        applies_when=lambda f: (
            f.measurement_error_exposure is not None
            or bool(f.measurement_error_covariates)
        ),
        ends=ESTIMATES,
    ),
    Route(
        # A dose-response curve over a binary treatment would degenerate to
        # the two-point contrast the binary path already computes. Record
        # the fall-back and let that path answer.
        id="dose_response_binary_fallback",
        precedence=120,
        applies_when=lambda f: (
            f.dose_response_triggered and f.treatment_is_binary
        ),
        ends=ESTIMATES,
    ),
    Route(
        # Phase 14 slice a: a flagged dose-response query whose treatment is
        # not binary and whose identification clears via back-door gets the
        # curve estimator rather than the binary-effect ATE.
        id="dose_response_curve",
        precedence=130,
        applies_when=lambda f: (
            f.dose_response_triggered
            and not f.treatment_is_binary
            and bool(f.adjustment_sets)
        ),
        ends=ESTIMATES,
    ),
    Route(
        # Doubly-robust opt-in: the back-door-identified ATE estimated by
        # the propensity / augmented estimator instead of the g-formula
        # plug-in. Same identification, different estimator and inference —
        # which is why it has no identification end and why it sits
        # immediately above back-door rather than anywhere else.
        id="doubly_robust",
        precedence=140,
        applies_when=lambda f: (
            bool(f.adjustment_sets)
            and f.ate_estimator in ("ipw", "aipw", "tmle")
        ),
        ends=ESTIMATES,
    ),
    Route(
        # Phase 7.1: back-door adjustment over the smallest valid set.
        id="backdoor",
        precedence=150,
        applies_when=lambda f: bool(f.adjustment_sets),
        ends=BOTH,
    ),
    Route(
        # Phase 7.2: back-door failed — front-door, which the fact itself
        # restricts to unconditioned queries.
        id="frontdoor",
        precedence=160,
        applies_when=lambda f: (
            not f.adjustment_sets and bool(f.front_door_sets)
        ),
        ends=BOTH,
    ),
    Route(
        # Non-parametric point identification (Shpitser-Pearl ID for an
        # unconditional do(X), IDC for a conditional one). Ranked ABOVE the
        # IV rows and the order is load-bearing: a c-factor estimand is
        # assumption-free and answers the query's own estimand, whereas the
        # Wald LATE needs a declared monotonicity and reports a contrast
        # among compliers. With IV first, declaring an assumption REPLACED
        # an assumption-free population answer with an assumption-laden
        # subpopulation one — supplying more information degraded the
        # estimand. That was finding C.
        id="general_id",
        precedence=170,
        applies_when=lambda f: (
            not f.adjustment_sets and not f.front_door_sets
        ),
        ends=BOTH,
    ),
    Route(
        # Over-identification: every instrument valid under the SAME
        # smallest conditioning set forms one over-identified system. With
        # two or more, run over-identified 2SLS plus the Sargan test rather
        # than discarding the extra instruments and their falsification
        # power. No identification end — the just-identified escalation is
        # the only one the identify path builds.
        id="iv_overidentified",
        precedence=180,
        applies_when=lambda f: (
            not f.adjustment_sets and not f.front_door_sets
            and len(f.overid_instruments) >= 2
        ),
        ends=ESTIMATES,
    ),
    Route(
        # Phase 7.3: the just-identified Wald ratio, under the assumptions
        # general-ID did not need. What it reports is a complier contrast,
        # not the population effect the query names — which is why it ranks
        # last, and why the answer carries the LATE caveat.
        id="iv_wald",
        precedence=190,
        applies_when=lambda f: (
            not f.adjustment_sets and not f.front_door_sets
            and bool(f.iv_candidates)
        ),
        ends=BOTH,
    ),
)


def _check(routes: tuple[Route, ...]) -> tuple[Route, ...]:
    """Reject a table that cannot express an order, and return it sorted."""
    by_precedence: dict[int, str] = {}
    seen: set[str] = set()
    for r in routes:
        if r.id in seen:
            raise ValueError(f"duplicate route id {r.id!r}")
        seen.add(r.id)
        if not r.ends:
            raise ValueError(
                f"route {r.id!r} declares no ends; a strategy no layer "
                f"implements is a routing decision with nothing behind it"
            )
        if r.precedence in by_precedence:
            raise ValueError(
                f"routes {by_precedence[r.precedence]!r} and {r.id!r} share "
                f"precedence {r.precedence}; the tie would be broken by "
                f"declaration order, which is what precedence replaces"
            )
        by_precedence[r.precedence] = r.id
    by_id = {r.id: r for r in routes}
    for r in routes:
        for target in sorted(r.displaces):
            if target not in by_id:
                raise ValueError(
                    f"route {r.id!r} displaces unknown route {target!r}"
                )
            other = by_id[target]
            if other.precedence <= r.precedence:
                raise ValueError(
                    f"route {r.id!r} displaces {target!r}, which outranks it; "
                    f"a row can only take a query away from one the cascade "
                    f"would have offered it to later"
                )
            if other.ends != BOTH:
                raise ValueError(
                    f"route {r.id!r} displaces {target!r}, which declares only "
                    f"{sorted(e.value for e in other.ends)}; a displaced "
                    f"route's guard is evaluated by whichever layer answered, "
                    f"so a route only one layer can evaluate cannot be one"
                )
            for side in (r, other):
                if not side.triggered_by:
                    raise ValueError(
                        f"route {r.id!r} displaces {target!r} but {side.id!r} "
                        f"names no triggered_by; the disclosure has to say "
                        f"which declaration to remove to get the other layer, "
                        f"and cannot be written without it"
                    )
    return tuple(sorted(routes, key=lambda r: r.precedence))


EFFECT_ROUTES = _check(EFFECT_ROUTES)
_BY_ID = {r.id: r for r in EFFECT_ROUTES}


def route(route_id: str) -> Route:
    """The route with this id, or a loud failure."""
    try:
        return _BY_ID[route_id]
    except KeyError:
        raise KeyError(
            f"no effect route {route_id!r}; known routes are "
            f"{sorted(_BY_ID)}"
        ) from None


def displaced_by(winner: Route, facts: Any) -> tuple[str, ...]:
    """The rows this one took the query away from, on these facts.

    Computed where the decision is made and by the layer that made it.
    The alternative — and what this replaces — is to notice downstream
    that one of the extensions came back empty and infer from that which
    layer never ran, which is a guess dressed as a disclosure: it reads
    residue, so a layer that fills its extension and then fails is
    indistinguishable from one that was never offered the query.

    Only the winner's DECLARED rivals are evaluated, never the rest of the
    table. Guards below the shape band run the structural solver, and
    :class:`StructuralFacts` is built so a query answered by the first row
    never pays for an adjustment-set search — nor is broken by one on a
    query shape that search has never been offered.
    """
    if not winner.displaces:
        return ()
    return tuple(
        r.id for r in EFFECT_ROUTES
        if r.id in winner.displaces and r.applies_when(facts)
    )


T = TypeVar("T")


def bind(end: End, bindings: Mapping[str, T]) -> tuple[tuple[Route, T], ...]:
    """Pair every route declaring ``end`` with its implementation.

    Both directions are errors. A route that declares an end nobody bound
    is the shape finding D had — a strategy the table promises and the
    layer never runs. A binding for a route that does not declare this end
    is the other half: an implementation the table does not know about,
    which is where a second dispatcher starts.
    """
    expected = {r.id for r in EFFECT_ROUTES if end in r.ends}
    missing = sorted(expected - set(bindings))
    if missing:
        raise ValueError(
            f"{end.value} declares no implementation for {missing}; every "
            f"route naming this end must be bound here"
        )
    extra = sorted(set(bindings) - expected)
    if extra:
        raise ValueError(
            f"{end.value} binds {extra}, which the effect route table does "
            f"not route to this end; add the end to the route, or the "
            f"binding is a second dispatcher"
        )
    return tuple(
        (r, bindings[r.id]) for r in EFFECT_ROUTES if end in r.ends
    )
