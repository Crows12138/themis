"""The estimation cascade as a table rather than as control flow.

Three facts about the cascade used to live nowhere but in the shape of one
555-line ``if`` chain: which strategy outranks which (source line order),
what each guard actually tests, and what the number a strategy produces
MEANS. All three had drifted from the identification layer's separately
written copy of the same decisions — that drift is what the slice 0 audit
measured, and findings A and C were made of it.

A :class:`Strategy` states all three as data. Order is a number, so two
layers can be asserted to agree on it. The guard is a pure predicate over
:class:`EffectFacts`, so it cannot depend on how far the cascade has
already got. And ``produces`` names the estimand, so "this handler passed
the query on" can eventually be checked against "and the next one answered
the same question" — the invariant the claim protocol could state but not
enforce.

**Why the guard sees a separate object from the run.** The estimation
layer's longitudinal guard tested a METHOD NAME left behind by an earlier
pass: rename the method and routing changes silently. The fix is not a
convention against it — :class:`EffectFacts` simply has no ``result``
attribute, so a guard that reaches for this layer's own output raises
instead of branching on residue. Guards do see the *identification*
layer's conclusions, which is the layer boundary working as designed.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Any, Callable, Iterator

from .claim import Claim


class Role(str, Enum):
    """Whether a strategy competes for the query or comments beside it.

    The distinction is redundant with the :class:`~.claim.Claim` a handler
    returns — and that redundancy is the point. Declaring it in the table
    lets the driver reject the one mismatch that has actually bitten:
    an annotating handler quietly answering the query.
    """

    CLAIM = "claim"
    ANNOTATE = "annotate"


class Estimand(str, Enum):
    """What a strategy's number is an estimate OF.

    Two strategies in an escalation ladder may legitimately produce
    different estimands — the IV fall-back reports a complier contrast
    where the non-parametric route would have reported a population
    effect — but that substitution has to be visible. It is not visible
    while the estimand exists only in prose in each estimator's docstring.
    """

    QUERY_EFFECT = "query_effect"
    """The interventional contrast the query names, in its own population."""

    TRANSPORTED_EFFECT = "transported_effect"
    """The query's contrast carried to a declared target population."""

    DECOMPOSITION = "decomposition"
    """Natural direct / indirect effects through the named mediator(s)."""

    JOINT_CONTRAST = "joint_contrast"
    """The effect of intervening on a treatment SET at once."""

    DOSE_RESPONSE = "dose_response"
    """A curve over treatment levels, not a two-point contrast."""

    COMPLIER_EFFECT = "complier_effect"
    """A LATE — an effect among compliers, not in the whole population."""

    NONE = "none"
    """Annotating strategies, which produce no estimand at all."""


@dataclass(frozen=True)
class Strategy:
    """One row of the cascade.

    ``run`` is the only imperative part: it calls the existing estimator
    wiring unchanged and returns the handler's :class:`~.claim.Claim`.
    """

    id: str
    precedence: int
    applies_when: Callable[["EffectFacts"], Any]
    role: Role
    produces: Estimand
    run: Callable[["EffectFacts", dict, "EffectKnobs"], Claim]
    defers_to: frozenset[str] = frozenset()
    """Rows allowed to answer this one's query with a DIFFERENT estimand.

    Handing a query to a row that answers the same question needs no
    declaration — it is the same question. Handing it to a row that
    answers a different one is a substitution, and a substitution the
    reader cannot see is how a decomposition query comes back carrying a
    total effect. Two exist and both are deliberate: a query that fails
    non-parametric identification may be answered by the IV ladder under
    assumptions, and a query the identification layer routed elsewhere is
    answered there. Anything else raises.
    """

    def __post_init__(self) -> None:
        if (self.role is Role.ANNOTATE) != (self.produces is Estimand.NONE):
            raise ValueError(
                f"strategy {self.id!r}: an annotating strategy produces no "
                f"estimand and a claiming one must name the estimand it "
                f"produces; got role={self.role.value} "
                f"produces={self.produces.value}"
            )


@dataclass(frozen=True)
class EffectKnobs:
    """The caller's estimation settings — how to estimate, not whether to.

    Nothing here may appear in a guard: these choose an estimator or an
    inference procedure for a strategy already selected. ``ate_estimator``
    is the exception that proves it, and it is in :class:`EffectFacts`
    instead, because selecting IPW/AIPW/TMLE genuinely selects a different
    strategy rather than tuning one.
    """

    random_state: int
    ci_bootstrap: int
    model: str
    cluster: str | None
    reference_data: Any
    selection_values: Any
    program: Any


class EffectFacts:
    """Everything a guard may look at — and nothing else.

    Deliberately narrow. There is no ``result`` here: a guard cannot branch
    on what this pass has already written, because the attribute does not
    exist to read. What guards do see is inputs (the query, the graph, the
    data, the caller's specs) and the identification layer's conclusions,
    captured before estimation starts.

    The structural facts are derived on first use rather than up front.
    That is not a speed concern: computing an adjustment set for a query
    the cascade answers long before it needs one would run solver code on
    query shapes it has never seen, and a table is supposed to change
    routing, not reachability.
    """

    def __init__(
        self,
        *,
        q_stmt: Any,
        graph: Any,
        bidirected: Any,
        prog: Any,
        contract: Any,
        ate_estimator: str,
        misclassification: dict | None,
        measurement_error: dict | None,
        selection_recovery: dict | None,
        dose_response_triggered: bool,
    ) -> None:
        self.q_stmt = q_stmt
        self.query = q_stmt.query
        self.graph = graph
        self.bidirected = bidirected
        self.prog = prog
        self.contract = contract
        self.ate_estimator = ate_estimator
        self.misclassification = misclassification or {}
        self.measurement_error = measurement_error or {}
        self.selection_recovery = selection_recovery
        self.dose_response_triggered = dose_response_triggered

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
        from ..runtime import structural_solver

        return structural_solver.minimal_adjustment_sets(
            self.graph, self.x_atom, self.y_atom,
            given=self.given_atoms,
            bidirected=self.bidirected or None,
        )

    @cached_property
    def front_door_sets(self) -> tuple:
        """Empty when the query conditions on anything.

        The front-door formula has no conditional form here, and the
        identification layer refuses the same combination. Folding that
        into the fact — rather than nesting the front-door branch under an
        ``if not given`` — is what lets the two layers' guards be compared
        side by side at all.
        """
        if self.given_atoms:
            return ()
        from ..runtime import structural_solver

        return structural_solver.front_door_sets(
            self.graph, self.x_atom, self.y_atom,
            bidirected=self.bidirected or None,
        )

    @cached_property
    def chosen_adjustment(self) -> tuple:
        """The smallest valid back-door set — the one the estimators use."""
        return min(self.adjustment_sets, key=len)

    @cached_property
    def adjustment_names(self) -> tuple[str, ...]:
        """The chosen set as column names, in topological order."""
        from .dispatch import _topo_order

        return tuple(
            a.predicate for a in _topo_order(self.graph, self.chosen_adjustment)
        )

    @cached_property
    def iv_candidates(self) -> tuple:
        """Empty when the query conditions on anything — as for front-door.

        A Wald ratio is an unconditional two-point contrast; there is no
        conditional form of it here, and the instrument's own conditioning
        set W is not the query's ``given`` (they coincide only by accident).
        Estimating one anyway answers a different question, which the
        identification layer refuses to do in as many words.

        That refusal used to live as the first line of the identification
        handler rather than in a guard, so it applied to exactly the one
        call site that happened to contain it: the estimation layer, whose
        guard was written separately, shipped a stratified Wald as the
        answer to ``P(Y|do(X), W=w)`` — the same number for w=True and
        w=False, so it could not have been an answer to either. Stating it
        as a fact is what makes it apply to every IV row rather than to a
        function body.
        """
        if self.given_atoms:
            return ()
        from ..runtime import structural_solver

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

    # --- data facts ------------------------------------------------------

    @cached_property
    def treatment_is_binary(self) -> bool:
        from .dispatch import _is_binary_treatment

        return _is_binary_treatment(self.contract.data, self.x_atom.predicate)

    # --- caller specs, resolved against THIS query's atoms ---------------

    @cached_property
    def misclassification_outcome(self) -> dict | None:
        return self.misclassification.get(self.y_atom.predicate)

    @cached_property
    def misclassification_exposure(self) -> dict | None:
        return self.misclassification.get(self.x_atom.predicate)

    @cached_property
    def measurement_error_outcome(self) -> dict | None:
        return self.measurement_error.get(self.y_atom.predicate)

    @cached_property
    def measurement_error_exposure(self) -> dict | None:
        return self.measurement_error.get(self.x_atom.predicate)

    @cached_property
    def measurement_error_covariates(self) -> dict:
        return {
            k: v for k, v in self.measurement_error.items()
            if k not in (self.x_atom.predicate, self.y_atom.predicate)
        }

    @cached_property
    def measurement_error_map(self) -> dict:
        """{design column → σ²_u} for the exposure and any named covariate.

        The outcome is absent by construction: a classical additive error
        there costs precision, not bias, so it has nothing to correct.
        """
        error_map: dict = {}
        if self.measurement_error_exposure is not None:
            error_map[self.x_atom.predicate] = (
                self.measurement_error_exposure or {}
            ).get("error_variance")
        for name, spec in self.measurement_error_covariates.items():
            error_map[name] = (spec or {}).get("error_variance")
        return error_map


@dataclass(frozen=True)
class Evaluation:
    """What one pass of the cascade over one query decided.

    The four fields are four readings of a single evaluation, which is the
    whole reason the table exists: ``fired`` is the answer, ``declined``
    is the gap report, ``annotated`` is what was recorded beside the
    answer, and ``considered`` explains reachability — why a strategy that
    exists never ran on this query.
    """

    query_id: str
    fired: tuple[str, Estimand] | None = None
    annotated: tuple[str, ...] = ()
    declined: tuple[tuple[str, str | None], ...] = ()
    passed_by: tuple[tuple[str, Estimand, str | None], ...] = ()
    considered: tuple[str, ...] = ()

    @property
    def answered(self) -> bool:
        return self.fired is not None

    @property
    def substitutions(self) -> tuple[tuple[str, str, Estimand, Estimand], ...]:
        """Every ``passed`` whose query was then answered by a DIFFERENT
        estimand — the shape the claim protocol can name but not yet reject.

        A ladder is allowed to substitute (the IV fall-back does), but the
        substitution has to be declared somewhere a reader can find it.
        Surfacing the pairs is what makes the rule decidable from data
        rather than from each estimator's prose.
        """
        if self.fired is None:
            return ()
        answerer, produced = self.fired
        return tuple(
            (passer, answerer, produces, produced)
            for passer, produces, _reason in self.passed_by
            if produces is not produced
        )


_recorder: list[Evaluation] | None = None


@contextlib.contextmanager
def recording() -> Iterator[list[Evaluation]]:
    """Collect every cascade evaluation made inside this block.

    The seam the derived surfaces need: turning ``declined`` into data
    gaps, and asserting that two entrances to the same estimand give the
    same number, both require watching evaluations from outside the
    envelope they are eventually written into.
    """
    global _recorder
    previous, sink = _recorder, []
    _recorder = sink
    try:
        yield sink
    finally:
        _recorder = previous


def run_cascade(
    strategies: tuple[Strategy, ...],
    facts: EffectFacts,
    result: dict,
    knobs: EffectKnobs,
    *,
    query_id: str,
) -> Evaluation:
    """Offer one query to each strategy in precedence order.

    First claim wins, exactly as the hand-written chain did — the
    difference is that "first" now means the smallest ``precedence``
    rather than the earliest line, and that everything the pass rejected
    on the way is retained instead of being discarded as control flow.
    """
    fired: tuple[str, Estimand] | None = None
    fired_by: Strategy | None = None
    annotated: list[str] = []
    declined: list[tuple[str, str | None]] = []
    passers: list[Strategy] = []
    passed_by: list[tuple[str, Estimand, str | None]] = []
    considered: list[str] = []

    for strategy in strategies:
        if not strategy.applies_when(facts):
            considered.append(strategy.id)
            continue
        claim = strategy.run(facts, result, knobs)
        if strategy.role is Role.ANNOTATE and claim.answered:
            raise AssertionError(
                f"strategy {strategy.id!r} is declared as annotating but "
                f"answered the query; an annotation that claims a query is "
                f"how a number for one estimand ends up standing in for "
                f"another"
            )
        if claim.stops_here:
            if claim.answered:
                fired, fired_by = (strategy.id, strategy.produces), strategy
            else:
                declined.append((strategy.id, claim.reason))
            break
        if strategy.role is Role.ANNOTATE:
            annotated.append(strategy.id)
        else:
            passers.append(strategy)
            passed_by.append((strategy.id, strategy.produces, claim.reason))

    if fired_by is not None:
        for passer in passers:
            if (
                passer.produces is not fired_by.produces
                and fired_by.id not in passer.defers_to
            ):
                raise AssertionError(
                    f"{passer.id!r} passed this query on and {fired_by.id!r} "
                    f"answered it with a different estimand "
                    f"({passer.produces.value} -> {fired_by.produces.value}); "
                    f"passing on is only legitimate when whoever answers next "
                    f"answers the same question, so a substitution has to be "
                    f"declared in {passer.id!r}'s defers_to"
                )

    evaluation = Evaluation(
        query_id=query_id,
        fired=fired,
        annotated=tuple(annotated),
        declined=tuple(declined),
        passed_by=tuple(passed_by),
        considered=tuple(considered),
    )
    if _recorder is not None:
        _recorder.append(evaluation)
    return evaluation


def check_table(strategies: tuple[Strategy, ...]) -> tuple[Strategy, ...]:
    """Reject a table that cannot express an order, and return it sorted.

    Duplicate precedence would put the tie back where it was before this
    module — decided by whichever row happened to be written first.
    """
    seen_ids: set[str] = set()
    seen_precedence: dict[int, str] = {}
    for s in strategies:
        if s.id in seen_ids:
            raise ValueError(f"duplicate strategy id {s.id!r}")
        seen_ids.add(s.id)
        if s.precedence in seen_precedence:
            raise ValueError(
                f"strategies {seen_precedence[s.precedence]!r} and {s.id!r} "
                f"share precedence {s.precedence}; the tie would be broken "
                f"by declaration order, which is the thing precedence exists "
                f"to replace"
            )
        seen_precedence[s.precedence] = s.id
    by_id = {s.id: s for s in strategies}
    for s in strategies:
        for target in s.defers_to:
            if target not in by_id:
                raise ValueError(
                    f"{s.id!r} defers to unknown strategy {target!r}"
                )
            if by_id[target].precedence <= s.precedence:
                raise ValueError(
                    f"{s.id!r} defers to {target!r}, which outranks it; a row "
                    f"can only hand a query to one the cascade has not yet "
                    f"offered it to"
                )
    return tuple(sorted(strategies, key=lambda s: s.precedence))
