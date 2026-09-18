"""The numeric end of the cascade: what each strategy's number MEANS.

Which strategy outranks which, and when each applies, are not decided
here — :mod:`themis.routing` holds them, shared with the identification
layer, because they are facts about the question rather than about either
layer. What this module adds is the part only the numeric end knows:
whether a row competes for the query or comments beside it, what its
number is an estimate OF, and which substitutions it permits.

``produces`` is what turns "this handler passed the query on" into
something checkable against "and the next one answered the same question"
— the invariant the claim protocol could state but not enforce.

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
import copy
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from typing import Any, Callable, Iterator

from .. import refusals
from ..refusals import Refusal
from ..routing import End, Route, StructuralFacts, bind, displaced_by
from .claim import Claim
from .form import AUTO


#: The two error STRUCTURES a continuous ``measurement_error`` spec may
#: name on the exposure, and the reason the key exists at all: no property
#: of the recorded column tells them apart. ``W = X* + U`` with U
#: independent of the TRUTH attenuates the slope and wants correcting;
#: ``X* = W + U`` with U independent of the RECORDED value leaves the
#: back-door slope alone and wants pricing. Which one holds is a fact
#: about how the measurement was made, so it arrives as a declaration or
#: not at all — and the default is the one every correction here was
#: written for.
#:
#: They live beside the property that reads them rather than beside either
#: estimator, because the word is the caller's and the routing decision it
#: settles belongs to neither of the two rows it settles it between.
STRUCTURE_CLASSICAL = "classical"
STRUCTURE_BERKSON = "berkson"


class Role(StrEnum):
    """Whether a strategy competes for the query or comments beside it.

    The distinction is redundant with the :class:`~.claim.Claim` a handler
    returns — and that redundancy is the point. Declaring it in the table
    lets the driver reject the one mismatch that has actually bitten:
    an annotating handler quietly answering the query.
    """

    CLAIM = "claim"
    ANNOTATE = "annotate"


class Estimand(StrEnum):
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

    STRUCTURAL_COEFFICIENT = "structural_coefficient"
    """The coefficient of the treatment in the outcome's own equation.

    What an instrument recovers once a reciprocal loop has been declared
    between the two (#450). It is not the query's interventional contrast
    and not a complier effect: in a system where each variable moves the
    other, a one-unit change in the treatment does not settle at a
    one-unit change, and this number is the single equation's coefficient
    rather than the equilibrium the pair reaches. Its own member because
    the difference is exactly what a reader must not be left to infer.
    """

    NONE = "none"
    """Annotating strategies, which produce no estimand at all."""


@dataclass(frozen=True)
class Strategy:
    """One row of the cascade: a shared route plus this layer's end of it.

    ``route`` is the shared object, not a copy of its fields — ``id``,
    ``precedence`` and ``applies_when`` read straight through it. Two
    layers agreeing on an order is then identity rather than inspection,
    which is what the previous arrangement had and lost three times.

    ``run`` is the only imperative part: it calls the existing estimator
    wiring unchanged and returns the handler's :class:`~.claim.Claim`.
    """

    route: Route
    role: Role
    produces: Estimand
    models: frozenset[str]
    """Which words this row's ``model=`` knob accepts, ``auto`` included.

    The same sentence ``produces`` is here for, one knob over: which forms
    an estimator can fit was decided in each estimator's own control flow
    and written in each estimator's own ``ModelName``, so nothing connected
    the caller's word to the row that would answer under it. What that cost
    was measured before this field was written — one word, four fates. On a
    back-door query ``model='forest'`` left by the exception door as a bare
    ``ValueError``; on a front-door one it came back as a proper refusal
    naming the two words that route knows; on an IV or a mediation query it
    was accepted, ignored, and recorded on the envelope as the caller's
    preference beside a number fitted through something else.

    And the mirror, which is why forwarding the knob to the two rows that
    dropped it would not have been the fix: ``iv`` declares five words and
    implements all five, down to the remedy it suggests when one answers
    the wrong question — and the entry's vocabulary, hand-written as the
    union of the OTHER families, shares exactly ``auto`` with it. Every
    word IV knows was refused at the door; every word the door allowed ran
    the same estimator. A union cannot decide this, because the question is
    not "does some route take this word" but "does the row now running take
    it", and only here are both halves in one place.

    ``auto`` is in every set: it is the caller declining to choose, which
    every row accepts. A row whose method IS its shape declares
    :data:`~themis.estimation.form.MODEL_WORDS_NONE` — one word, not none,
    because a row that takes no choice still answers the question.

    :func:`run_cascade` refuses a word the ANSWERING row does not declare,
    and it refuses there rather than leaving it to the estimators because
    most of these rows have nothing of their own to refuse with: a family
    whose method is its shape never reads the option at all, so a caller
    who names a shape on such a query used to be answered as though they
    had said nothing. The other direction — a row that declares a word and
    then does not change its answer under it — is not decidable from here
    and is pinned per route, on live runs, in
    ``tests/test_the_word_a_caller_writes_is_one_the_route_takes.py``.
    """
    run: Callable[["EffectFacts", dict, "EffectKnobs"], Claim]
    defers_to: frozenset[str] = frozenset()
    """Rows allowed to answer this one's query with a DIFFERENT estimand.

    Handing a query to a row that answers the same question needs no
    declaration — it is the same question. Handing it to a row that
    answers a different one is a substitution, and a substitution the
    reader cannot see is how a decomposition query comes back carrying a
    total effect. One remains, and it is deliberate: a query that fails
    non-parametric identification may be answered by the IV ladder under
    assumptions. Anything else raises.

    Declaring the substitution rather than forbidding it is a measured
    choice and not a concession. The invariant was handed over stated
    literally — passing on is legitimate only when whoever answers next
    answers the same question — and instrumenting the whole suite showed
    the literal reading false: of 434 evaluations 92 were passed on, and
    the substitutions took exactly two shapes, this one firing 80 times.
    Every one of those hands the query to a ladder that answers with a
    complier contrast, which is a different quantity and is the escape
    working as designed. Forbidding what the sentence forbids would have
    broken 81 correct paths.

    There were two. The other existed only because the two layers ordered
    transport and mediation differently, so the estimation cascade could
    reach transport for a query naming both only by having mediation stand
    down first. One shared order removed the hand-off and the declaration
    with it.
    """

    @property
    def id(self) -> str:
        return self.route.id

    @property
    def precedence(self) -> int:
        return self.route.precedence

    @property
    def applies_when(self) -> Callable[["EffectFacts"], Any]:
        return self.route.applies_when

    def __post_init__(self) -> None:
        if (self.role is Role.ANNOTATE) != (self.produces is Estimand.NONE):
            raise ValueError(
                f"strategy {self.id!r}: an annotating strategy produces no "
                f"estimand and a claiming one must name the estimand it "
                f"produces; got role={self.role.value} "
                f"produces={self.produces.value}"
            )
        # The caller's do-nothing word, in every row. A set without it says
        # this row refuses a caller who declined to choose, which is the one
        # caller every row already serves; a set with nothing in it says the
        # knob cannot be written at all, and the knob has no such value.
        if AUTO not in self.models:
            raise ValueError(
                f"strategy {self.id!r} accepts {sorted(self.models)} for "
                f"model= and not {AUTO!r}; every row serves the caller who "
                f"declined to choose, so a set without it describes no run"
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


def _declared_tracking(spec: object, key: str) -> object | None:
    """What a measurement spec declared under ``key``, or ``None`` if nothing.

    Two questions used to be answered by one expression here, and merging them
    is what let a declaration disappear: WAS a differential error declared is
    the routing question, and IS the declared value usable is the estimator's.
    Answered together, the second one's ``no`` came back in the first one's
    words — an unusable δ read as no δ at all, the row that owns that case
    never ran, and the answer shipped under the very premise the caller had
    written down to withdraw. A declaration nobody can act on has to leave by
    the refusal door, which means the row that owns it has to be reached.

    So presence routes and the estimator judges: what comes back is whatever
    the caller wrote, unwrapped only far enough to see an exact zero — which
    IS the classical premise, and belongs to the row that prices it.
    """
    from collections.abc import Mapping

    from .resample import DeclaredTracking

    if not isinstance(spec, Mapping) or key not in spec:
        return None
    declared = DeclaredTracking.declared_value(spec[key])
    if (isinstance(declared, (int, float)) and not isinstance(declared, bool)
            and declared == 0):
        return None
    return spec[key]


class EffectFacts(StructuralFacts):
    """The numeric end's view: the structural facts plus the data.

    Deliberately narrow. There is no ``result`` here: a guard cannot branch
    on what this pass has already written, because the attribute does not
    exist to read. What guards do see is inputs (the query, the graph, the
    data, the caller's specs) and the identification layer's conclusions,
    captured before estimation starts.

    Everything structural comes from the shared base, so a guard shared
    with the identification layer means the same thing on both sides
    rather than being two solver calls that look alike.

    ``contract`` is the rows THIS QUESTION is about: a question
    conditioning on a stratum is about the people in it, and a strategy
    reading this reads them. ``whole`` is every row the caller handed in,
    and a route reads it only where its estimand is not the one this
    question conditions to — a second population to transport onto, a
    biased sample to recover from, a formula that conditions inside
    itself. The default is the narrower of the two on purpose: a route
    added later that says nothing is about the question as asked, and a
    route that needs the rest of the table says so where it asks for
    them. Where the question names no stratum the two are the same frame.
    """

    def __init__(
        self,
        *,
        q_stmt: Any,
        graph: Any,
        bidirected: Any,
        feedback: Any,
        prog: Any,
        contract: Any,
        ate_estimator: str,
        misclassification: dict | None,
        measurement_error: dict | None,
        selection_recovery: dict | None,
        dose_response_triggered: bool,
        whole: Any = None,
    ) -> None:
        super().__init__(
            q_stmt=q_stmt, graph=graph, bidirected=bidirected,
            feedback=feedback,
        )
        self.prog = prog
        self.contract = contract
        self.whole = contract if whole is None else whole
        self.ate_estimator = ate_estimator
        self.misclassification = misclassification or {}
        self.measurement_error = measurement_error or {}
        self.selection_recovery = selection_recovery
        self.dose_response_triggered = dose_response_triggered

    # --- the chosen adjustment set as data columns -----------------------

    @cached_property
    def adjustment_names(self) -> tuple[str, ...]:
        """The chosen set as column names, in topological order."""
        from .dispatch import _topo_order

        return tuple(
            a.predicate for a in _topo_order(self.graph, self.chosen_adjustment)
        )

    # --- data facts ------------------------------------------------------

    @cached_property
    def treatment_is_binary(self) -> bool:
        from .dispatch import _is_binary_treatment

        return _is_binary_treatment(self.contract.data, self.x_atom.predicate)

    # --- the program's declarations, resolved against THIS query's atoms --

    @cached_property
    def censored_outcome(self):
        """The outcome's follow-up-time declaration, or ``None``.

        Presence routes and the estimator judges, for the reason
        :func:`_declared_tracking` gives one field over: a declaration
        naming a column the data does not have, or a horizon past the end
        of follow-up, must leave by the refusal door — which means the row
        that owns it has to be reached first. So the only question asked
        here is whether the program said this column is a follow-up time.

        Read from the program rather than from a caller spec, because it
        is a fact about what the variable IS. A measurement error is
        something an analyst knows about their instrument and passes
        beside the data; that a column stops when follow-up does is part
        of the variable's definition, and belongs where its domain and its
        scale already are.
        """
        from ..types import VariableDeclaration

        for stmt in getattr(self.prog, "statements", ()) or ():
            if (isinstance(stmt, VariableDeclaration)
                    and stmt.predicate == self.y_atom.predicate
                    and stmt.censoring is not None):
                return stmt.censoring
        return None

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
    def exposure_error_structure(self) -> str:
        """Which error structure the caller declared on the exposure.

        Absence reads as :data:`STRUCTURE_CLASSICAL`, and that asymmetry is
        deliberate: every correction in this package was written for the
        classical structure, so the caller who says nothing gets what they
        would have got before the key existed.

        What it returns for a word nobody recognises is the word itself,
        not a fallback. A structure that cannot be identified is exactly
        the case where correcting is unsafe — the premise a correction
        rests on is the one in doubt — so an unknown word must not read as
        the structure the corrections assume. It routes with Berkson's,
        where a row that owns every non-classical declaration says so.
        """
        declared = (self.measurement_error_exposure or {}).get("structure")
        return declared if isinstance(declared, str) else STRUCTURE_CLASSICAL

    @cached_property
    def exposure_error_is_classical(self) -> bool:
        """The routing question the word above settles.

        Two readings of one fact rather than two facts: the guards in
        :mod:`themis.routing` need to know which side of the fork they are
        on, the refusal that names an unrecognised structure needs the word
        itself, and a route table spelling the word would be a second place
        it is written — which is how the two would come to disagree.
        """
        return self.exposure_error_structure == STRUCTURE_CLASSICAL

    @cached_property
    def exposure_error_differential(self) -> object | None:
        """δ — how much the exposure's error tracks the outcome, or ``None``.

        A declared zero reads as absent, and for the same reason a declared
        ``"linear"`` outcome model does above: δ = 0 says the error is
        non-differential, which is exactly the classical correction's case.
        Routing there rather than to an estimator that computes the same
        number by a longer road keeps one answer with one producer.

        Only a NUMBER declares it. The size is what enters the correction, so
        there is no way to say "differential, amount unknown" here and get a
        point — a caller who has only the direction has a sensitivity
        analysis to run, not a correction to apply.

        That number may arrive alone or inside the validation regression that
        measured it, and the coefficient is read out of either: which shape a
        caller used decides whether the interval carries that study, and it
        decides nothing about which route answers. Reading only the bare shape
        here would send a fully declared study to the classical correction,
        under a premise it never made.
        """
        return _declared_tracking(
            self.measurement_error_exposure, "differential_coefficient")

    @cached_property
    def outcome_error_differential(self) -> object | None:
        """δ — how much the OUTCOME's error tracks the exposure, or ``None``.

        The mirror of :meth:`exposure_error_differential`, and the reason it
        was missing is the reason it matters: the row that reads an
        outcome-error declaration reads ``error_variance`` and nothing else,
        so a caller could declare the one fact that makes the point wrong and
        have it dropped without a word. Absence of a reader is not a refusal;
        it is an answer computed under a premise the caller withdrew.

        A declared zero reads as absent, exactly as it does on the exposure
        side: δ = 0 IS the classical premise, and the row below prices it.
        """
        return _declared_tracking(
            self.measurement_error_outcome, "differential_coefficient")

    @cached_property
    def simex_outcome_model(self) -> str | None:
        """The nonlinear outcome model the caller declared the estimand
        lives in, or ``None`` — which is what routes between the two
        continuous-mismeasurement corrections.

        It has to be a declaration and cannot be read off the data. The
        moment correction and simulation-extrapolation do not compute the
        same number better and worse; they answer different questions
        about the same two columns. For a binary outcome the moment
        correction returns the de-attenuated LINEAR-PROBABILITY slope — a
        risk difference per unit of true exposure — and this returns the
        coefficient in a logistic model, a conditional log-odds ratio.
        Both are estimable from exactly the same columns, so nothing in
        the sample distinguishes which one was wanted.

        An explicit ``"linear"`` therefore routes to the moment
        correction rather than here: same estimand, and a closed form
        beats a seeded simulation of it every time.
        """
        model = (self.measurement_error_exposure or {}).get("outcome_model")
        return model if isinstance(model, str) and model != "linear" else None

    @cached_property
    def measurement_error_map(self) -> dict:
        """{design column → that column's whole declaration}.

        The outcome is absent by construction: a CLASSICAL additive error
        there costs precision, not bias, so it has nothing to correct. That
        word is load-bearing and was for a long time unchecked — an outcome
        error that tracks the exposure shifts the exposure's coefficient by
        δ, and the row that owns that case reads the declaration itself
        rather than this map.

        The SPEC and not the number, because the variance and how well the
        caller knows it are one declaration, and a map carrying only the
        number is how a column ends up corrected by a study whose own
        uncertainty nothing downstream can see.

        Untouched, though, and that is the other half. Facts describe a run;
        they do not adjudicate it. This property is read while a strategy's
        arguments are being built — before the handler that owns the refusal
        exists to catch anything — so a declaration judged here would leave
        by the exception door instead of reaching the reader as a refusal
        with the estimator's name on it.
        """
        error_map: dict = {}
        if self.measurement_error_exposure is not None:
            error_map[self.x_atom.predicate] = (
                self.measurement_error_exposure or {})
        for name, spec in self.measurement_error_covariates.items():
            error_map[name] = spec or {}
        return error_map


@dataclass(frozen=True)
class Evaluation:
    """What one pass of the cascade over one query decided.

    The fields are readings of a single evaluation, which is the whole
    reason the table exists: ``fired`` is the answer, ``declined`` is the
    gap report, ``annotated`` is what was recorded beside the answer, and
    ``considered`` explains reachability — why a strategy that exists never
    ran on this query.

    ``considered`` could only ever half-answer that on its own. It holds
    the rows whose guard was false, and the cascade stops at the winner, so
    a row BELOW the winner whose guard was true is in neither list — the
    one shape where "never ran" is a decision rather than a non-event.
    ``displaced`` is that shape, named by the route table (see
    :attr:`themis.routing.Route.displaces`) and evaluated where the winner
    is picked.
    """

    query_id: str
    fired: tuple[str, Estimand] | None = None
    annotated: tuple[str, ...] = ()
    declined: tuple[tuple[str, str | None], ...] = ()
    passed_by: tuple[tuple[str, Estimand, str | None], ...] = ()
    considered: tuple[str, ...] = ()
    displaced: tuple[str, ...] = ()

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
    previous = _recorder
    sink: list[Evaluation] = []
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
    displaced: tuple[str, ...] = ()

    for strategy in strategies:
        if strategy.route.after_the_answer:
            continue
        if not strategy.applies_when(facts):
            considered.append(strategy.id)
            continue
        # A row cannot honour a word it does not accept, and WHICH row was
        # asked to is settled only once one answers: a row that hands the
        # query on has not used the knob, and the row that takes it next
        # may take a word this one does not — the escape that fires 80
        # times in 434 measured evaluations. So the judgement waits for the
        # claim, which means the result has to survive until it comes. The
        # copy is kept only where it could be needed, and on the ordinary
        # path — every run that leaves ``model`` at ``auto`` — no row is
        # ever offered a word it does not take and nothing is copied.
        untouched = (None if knobs.model in strategy.models
                     else copy.deepcopy(result))
        claim = strategy.run(facts, result, knobs)
        if untouched is not None and claim.answered:
            # The number was produced with the caller's instruction
            # ignored, so it does not stand. Refused here and not in the
            # estimator because most of these rows have nothing of their
            # own to refuse WITH: a family whose method is its shape never
            # reads the option, so the caller who names a shape on such a
            # query was answered as though they had said nothing. The
            # driver is the only place that holds both the word and the
            # row it was aimed at.
            result.clear()
            result.update(untouched)
            result["estimator_failure"] = refusals.block(
                estimator=strategy.id,
                failure_type=Refusal.UNKNOWN_OPTION,
                details={"option": "model", "given": knobs.model,
                         "known": sorted(strategy.models)},
            )
            declined.append((strategy.id, "estimator_refused"))
            break
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
                displaced = displaced_by(strategy.route, facts)
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

    # The other half of the axis. These rows do not compete, so they are not
    # offered the query until the competition is over — and not at all when it
    # was refused, because a refusal has no answer to annotate and annotating
    # one is how a refusal comes to read as a result.
    if not declined:
        for strategy in strategies:
            if not strategy.route.after_the_answer:
                continue
            if not strategy.applies_when(facts):
                considered.append(strategy.id)
                continue
            claim = strategy.run(facts, result, knobs)
            if claim.answered or claim.stops_here:
                raise AssertionError(
                    f"strategy {strategy.id!r} runs after the answer and "
                    f"{'claimed' if claim.answered else 'stopped'} the query; "
                    f"there is nothing left to claim, and stopping here would "
                    f"mean withdrawing an answer already written — what such a "
                    f"row learns too late is a note beside the answer, not a "
                    f"veto over it"
                )
            annotated.append(strategy.id)

    evaluation = Evaluation(
        query_id=query_id,
        fired=fired,
        annotated=tuple(annotated),
        declined=tuple(declined),
        passed_by=tuple(passed_by),
        considered=tuple(considered),
        displaced=displaced,
    )
    if _recorder is not None:
        _recorder.append(evaluation)
    return evaluation


def check_table(
    strategies: tuple[Strategy, ...], *, covers: End | None = None,
) -> tuple[Strategy, ...]:
    """Reject a table that cannot express an order, and return it sorted.

    Duplicate precedence would put the tie back where it was before this
    module — decided by whichever row happened to be written first.

    ``covers`` binds the table to the shared route table: every route
    declaring that end must have a row here and vice versa, so a strategy
    the routing table promises cannot go quietly unimplemented. Tables
    built out of routes that are not in the shared one — the ones tests
    construct to exercise the driver — leave it unset.
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
        if s.route.after_the_answer and s.role is not Role.ANNOTATE:
            raise ValueError(
                f"{s.id!r} runs after the answer but is declared as "
                f"{s.role.name}; by the time it runs the query has been "
                f"answered, so a row that produces an estimand there would "
                f"be offering a second one for a question already settled"
            )
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
    if covers is not None:
        return tuple(s for _route, s in bind(covers, by_id))
    return tuple(sorted(strategies, key=lambda s: s.precedence))
