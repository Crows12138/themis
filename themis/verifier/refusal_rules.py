"""A refusal is a claim about the program, and it needs a witness too.

When Themis cannot answer, what it hands back is not an absence. It is a
report: this estimand is not identified from this graph, that is what
blocks it, and here is what you would have to go and measure. A reader
acts on that — measures a confounder, hunts an instrument, runs a trial.
It is the most expensive advice the system gives.

And it was the one claim no door checked. ``verify`` requires a derivation
and refuses the whole class before reading a block; every other public
entry is result-only, and a result-only door cannot check a claim about a
program it was never handed. Measured: a refusal saying
``unidentifiable_no_admissible_set`` was moved, unchanged, onto a query
that the same system answers with a point estimate, and ``themis.audit``
returned verdicts identical to the honest one's, every row ok.

The principle is already the repo's own. The classifier that reads a
derivation was changed to fire on the SUCCEEDING ``tian_hedge_witness``
step precisely because a failed step "was only an assertion that something
had gone wrong", while the c-component decomposition is a proof the
verifier can replay. That was applied inside the chain and never at the
door — so the sibling classifier, which fires from a kernel investigation
item on the path where no chain exists at all, yields the same gap kind
carrying no witness whatever.

**This module is a falsifier, not a confirmer.** It refuses a refusal
when it can EXHIBIT what the refusal says does not exist. It never
certifies one as proven: proving non-identifiability is the producer's
work and the hedge witness is where that proof lives. Every bound in the
searches below therefore errs one way — toward finding nothing and
accepting — because a bound that erred the other way would call an honest
refusal a lie.

**What settles each claim.** A gap kind asserts something, and the
something has an owner: the program, or the data, or the caller's own
declaration. Only the first is this door's business, and the binding at
the bottom of this module is total over the vocabulary — a kind added
without a classification does not import. Of the program-settled kinds,
those that already have a witness search live in ``_REFUTERS``; the rest
are named by a test rather than by a comment, so they leave that list only
by being closed.

**Independence pin:** this module MUST NOT import from ``themis.output``
or ``themis.runtime``. It re-derives identification from the graph using
the verifier's own d- and m-separation, which is the whole point: a
witness found by the producer's own identifier would prove only that the
producer is consistent with itself.
"""
from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Mapping
from dataclasses import dataclass

import networkx as nx

from ..gaps import GapKind
from ..types import Atom, EffectQuery, Query
from .errors import VerificationError
from .rules import (
    _check_d_separation,
    _graph_minus_x_outgoing,
    _verifier_is_admg_backdoor_connected,
)

#: How far the front-door search looks. Unlike the adjustment search below
#: it is not complete, and it does not have to be: a mediator set this
#: misses is a witness not exhibited, which ends in accepting the refusal.
#: The bound that would need justifying is the one that could manufacture a
#: refusal, and there is none.
_FRONT_DOOR_MAX_SET = 2


@dataclass(frozen=True)
class RefusalFacts:
    """What re-deriving a refusal needs: the program's graph, and nothing
    the result said about itself.

    ``longitudinal`` is the program's ``options.longitudinal`` as written,
    or ``None``: a declaration outside the query that can change the
    estimand the query stands for, so it travels beside the query.
    """

    graph: nx.DiGraph
    bidirected: frozenset
    query: Query
    feedback: frozenset = frozenset()
    selection_nodes: tuple = ()
    longitudinal: Mapping | None = None


#: The fields of the query the searches below read. They express ONE
#: estimand: the total effect of one treatment on one outcome, in the
#: population the graph describes, from that population's own observational
#: distribution. Every other field on the query moves the estimand — a
#: second treatment, a mediator to decompose through, another population to
#: transport to — and a witness for the plain effect is then a witness for a
#: different question.
#:
#: Stated as the fields READ rather than as the fields that disqualify,
#: because the second list goes stale the day a field is added beside it.
#: Measured: twenty-eight honest transport refusals were called lies by a
#: guard that checked the query's TYPE, since a transport query is an
#: EffectQuery carrying a target population.
_ESTIMAND_FIELDS_READ = frozenset({"target", "intervention", "given"})


def _stands_in_for_a_strategy(facts: RefusalFacts) -> bool:
    """True when the program declares a time-varying strategy and this
    query is how it asks it.

    The query grammar cannot carry the order of treatments in time, so a
    program declares the strategy in ``options.longitudinal`` and asks it
    as the effect of one of the declared treatments on the declared
    outcome, with nothing else on the query. Asked that way the estimand is
    no longer the total effect of that one treatment. It is the strategy
    contrast, standardized over the history the program declares measured,
    and an adjustment set drawn from the whole graph is made of variables
    that declaration says nobody measured.

    Read by predicate, because the declaration names columns.
    """
    spec = facts.longitudinal
    q = facts.query
    if not isinstance(spec, Mapping) or not isinstance(q, EffectQuery):
        return False
    return (_nothing_else_is_asked(q)
            and q.target.atom.predicate == spec.get("outcome")
            and q.intervention.atom.predicate in (spec.get("treatments") or ()))


def _asks_what_the_search_can_answer(facts: RefusalFacts) -> bool:
    """True when the estimand is the one the witness searches express.

    A selection node disqualifies for the same reason a target population
    does: what the data are a sample OF is no longer the distribution the
    searches identify from. A declared strategy the query stands in for
    disqualifies for the reason :func:`_stands_in_for_a_strategy` gives.
    """
    q = facts.query
    if not isinstance(q, EffectQuery):
        return False
    if facts.selection_nodes:
        return False
    if _stands_in_for_a_strategy(facts):
        return False
    return _nothing_else_is_asked(q)


def _nothing_else_is_asked(q: Query) -> bool:
    """True when every field of the query past the ones the searches read
    is at its default."""
    for field in dataclasses.fields(q):
        if field.name in _ESTIMAND_FIELDS_READ:
            continue
        if field.default is not dataclasses.MISSING:
            default = field.default
        elif field.default_factory is not dataclasses.MISSING:
            default = field.default_factory()
        else:
            return False
        if getattr(q, field.name) != default:
            return False
    return True


# ===================================================== the adjustment witness


def _descendants(graph: nx.DiGraph, x: Atom) -> set[Atom]:
    return set(nx.descendants(graph, x)) | {x}


def _ancestors_of(graph: nx.DiGraph, nodes: set[Atom]) -> set[Atom]:
    out: set[Atom] = set()
    for n in nodes:
        if n in graph:
            out |= set(nx.ancestors(graph, n)) | {n}
    return out


def _backdoor_holds(
    graph: nx.DiGraph,
    bidirected: frozenset,
    x: Atom,
    y: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """The verifier's own backdoor criterion, both legs, ADMG-aware.

    The same two legs the chain rule checks, asked of a set nobody
    proposed — which is the only difference between checking a witness and
    finding one.
    """
    if x not in graph or y not in graph:
        return False
    if not conditioning.isdisjoint(_descendants(graph, x) | {y}):
        return False
    if bidirected:
        return not _verifier_is_admg_backdoor_connected(
            graph, bidirected, x, y, conditioning)
    return _check_d_separation(
        _graph_minus_x_outgoing(graph, x), x, y, conditioning)


def _canonical_adjustment_set(
    graph: nx.DiGraph, x: Atom, y: Atom, given: frozenset[Atom],
) -> frozenset[Atom]:
    """The one set worth testing.

    The canonical adjustment set: the ancestors of the endpoints, less the
    treatment's descendants. The standard result is that if any set
    satisfies the criterion then this one does, which is why there is no
    subset search here and so no cap on one either.

    Soundness does not rest on that result and neither does this module.
    What is returned is handed to the criterion and re-checked there, so
    what comes back is a witness whether or not the completeness claim is
    remembered correctly; getting it wrong costs a witness not found,
    which ends in accepting the refusal.
    """
    forbidden = _descendants(graph, x) | {y}
    return frozenset(
        _ancestors_of(graph, {x, y} | set(given)) - forbidden)


def _adjustment_witness(facts: RefusalFacts) -> frozenset[Atom] | None:
    q = facts.query
    if not isinstance(q, EffectQuery):
        return None
    x, y = q.intervention.atom, q.target.atom
    given = frozenset(v.atom for v in getattr(q, "given", ()) or ())
    graph = facts.graph
    if x not in graph or y not in graph or x == y:
        return None
    for candidate in (
        _canonical_adjustment_set(graph, x, y, given),
        frozenset(),
    ):
        if _backdoor_holds(graph, facts.bidirected, x, y, candidate | given):
            return candidate
    return None


# ===================================================== the front-door witness


def _front_door_holds(
    graph: nx.DiGraph,
    bidirected: frozenset,
    x: Atom,
    y: Atom,
    m: frozenset[Atom],
) -> bool:
    """Pearl's three conditions, re-derived rather than looked up.

    (i) M intercepts every directed path from X to Y;
    (ii) no unblocked backdoor path from X to M;
    (iii) every backdoor path from M to Y is blocked by X.
    """
    if not m or x in m or y in m:
        return False
    for raw in nx.all_simple_paths(graph, x, y):
        if not (set(raw[1:-1]) & m):
            return False
    cut = _graph_minus_x_outgoing(graph, x)
    for node in m:
        if bidirected:
            if _verifier_is_admg_backdoor_connected(
                    graph, bidirected, x, node, frozenset()):
                return False
        elif not _check_d_separation(cut, x, node, frozenset()):
            return False
    for node in m:
        if bidirected:
            if _verifier_is_admg_backdoor_connected(
                    graph, bidirected, node, y, frozenset({x}) | (m - {node})):
                return False
        elif not _check_d_separation(
                _graph_minus_x_outgoing(graph, node), node, y,
                frozenset({x}) | (m - {node})):
            return False
    return True


def _front_door_witness(facts: RefusalFacts) -> frozenset[Atom] | None:
    q = facts.query
    if not isinstance(q, EffectQuery):
        return None
    x, y = q.intervention.atom, q.target.atom
    graph = facts.graph
    if x not in graph or y not in graph or x == y:
        return None
    mediators = sorted(
        (n for n in graph.nodes
         if n != x and n != y
         and nx.has_path(graph, x, n) and nx.has_path(graph, n, y)),
        key=lambda a: a.predicate)
    for size in range(1, _FRONT_DOOR_MAX_SET + 1):
        for combo in itertools.combinations(mediators, size):
            if _front_door_holds(
                    graph, facts.bidirected, x, y, frozenset(combo)):
                return frozenset(combo)
    return None


# ===================================================== the strategy witness


def _the_declared_history_holds(
    facts: RefusalFacts,
) -> tuple[tuple[Atom, ...], Atom] | None:
    """The treatments and the outcome, where the declared history holds.

    The sequential back door asked of the history the program declares
    rather than of a set anybody searched for. At each treatment A_k, in
    its declared order, the history is every covariate block up to and
    including k and every earlier treatment, and the back-door criterion
    has to hold for A_k's effect on the outcome given it: the two legs of
    :func:`_backdoor_holds`, asked once per treatment of a growing set.

    Every way of being unable to ask ends in ``None``, and so in accepting
    the refusal: blocks and treatments of different lengths; a feedback
    loop, whose route outranks this one wherever it reaches the estimand; a
    selection node; and a name the graph holds no node of, or several. On a
    program unrolled in time a column's variable has a node at every step,
    and which step the declaration meant is written nowhere.
    """
    spec = facts.longitudinal
    if (not isinstance(spec, Mapping) or facts.feedback
            or facts.selection_nodes):
        return None
    names = list(spec.get("treatments") or ())
    blocks = [list(block) for block in (spec.get("confounders_by_time") or ())]
    if not names or len(blocks) != len(names):
        return None
    by_predicate: dict[str, list[Atom]] = {}
    for node in facts.graph.nodes:
        by_predicate.setdefault(node.predicate, []).append(node)

    def _the_node(name: object) -> Atom | None:
        found = by_predicate.get(name) if isinstance(name, str) else None
        return found[0] if found and len(found) == 1 else None

    outcome = _the_node(spec.get("outcome"))
    if outcome is None:
        return None
    treatments: list[Atom] = []
    for name in names:
        node = _the_node(name)
        if node is None or node == outcome:
            return None
        treatments.append(node)
    history: list[Atom] = []
    for a_k, block in zip(treatments, blocks):
        for name in block:
            node = _the_node(name)
            if node is None:
                return None
            history.append(node)
        if not _backdoor_holds(facts.graph, facts.bidirected, a_k, outcome,
                               frozenset(history)):
            return None
        history.append(a_k)
    return tuple(treatments), outcome


# ===================================================== the refuters


def _names(atoms) -> str:
    return "{" + ", ".join(sorted(a.predicate for a in atoms)) + "}"


def _refute_unidentifiable(gap: dict, facts: RefusalFacts) -> str | None:
    """"No admissible set exists" — refuted by producing one.

    Only where the estimand is one a search here expresses. The kind is
    raised for every route that failed, transport's and a mediation
    decomposition's included, and an adjustment set for the plain total
    effect says nothing about either. Those reach here and leave
    unrefuted, which is the falsifier declining a question rather than a
    case being skipped.

    A declared strategy is the one estimand beside the plain effect that
    has a search of its own, and its witness is the declaration itself:
    the history it names, holding at every treatment.
    """
    if _stands_in_for_a_strategy(facts):
        held = _the_declared_history_holds(facts)
        if held is None:
            return None
        treatments, outcome = held
        return (f"the history the program declares measured blocks every "
                f"back-door path to {outcome.predicate} from each of "
                f"{', '.join(a.predicate for a in treatments)} in turn")
    if not _asks_what_the_search_can_answer(facts):
        return None
    z = _adjustment_witness(facts)
    if z is not None:
        return (f"adjusting for {_names(z)} satisfies the backdoor criterion "
                f"for this estimand in this graph")
    m = _front_door_witness(facts)
    if m is not None:
        return (f"the front-door criterion holds through {_names(m)} in this "
                f"graph")
    return None


_REFUTERS = {
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: _refute_unidentifiable,
}


# ===================================================== what settles a claim


@dataclass(frozen=True)
class Settles:
    """Who owns the fact a gap asserts.

    Not a measure of importance and not a to-do list: a statement about
    what would have to be in hand to check the claim. This door is handed
    a program and a result, so only the first is answerable here, and
    calling a data claim unaudited would be as wrong as calling it audited.

    Three module constants rather than a vocabulary, because nothing here
    reaches a reader. A closed vocabulary in this repo is a set of words
    somebody is shown and a schema states; this is a set of decisions the
    binding below enforces, and registering it as the former would claim a
    schema site it does not have.
    """

    owner: str


THE_PROGRAM = Settles("the graph, the query or a declaration in the program")
THE_DATA_OR_THE_RUN = Settles("the frame, the fitted numbers, or the chain")
A_DECLARATION_REPEATED = Settles("something the caller declared, restated")

_P = THE_PROGRAM
_D = THE_DATA_OR_THE_RUN
_R = A_DECLARATION_REPEATED

SETTLED_BY: dict[GapKind, Settles] = {
    # --- claims about the graph or the query ---------------------------------
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: _P,
    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR: _P,
    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH: _P,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND: _P,
    GapKind.MISSING_IV_CANDIDATE: _P,
    GapKind.UNMEASURED_CONFOUNDER_RISK: _P,
    GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH: _P,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: _P,
    GapKind.ILL_DEFINED_INTERVENTION_VERSIONS: _P,
    GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE: _P,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH: _P,
    # --- claims the frame or the run settles ---------------------------------
    GapKind.MISSING_DISTRIBUTION: _D,
    GapKind.MISSING_POPULATION_DISTRIBUTION: _D,
    GapKind.MISSING_ASSUMPTION: _D,
    GapKind.MISSING_UNIT_OBSERVATION: _D,
    GapKind.MISSING_STRUCTURAL_INPUT: _D,
    GapKind.MISSING_MEDIATOR_DATA: _D,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: _D,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: _D,
    GapKind.TRANSPORT_SOURCES_DISAGREE: _D,
    GapKind.DOSE_RESPONSE_DATA_REQUIRED: _D,
    GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE: _D,
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE: _D,
    GapKind.LOW_CONFIDENCE_INPUT_DATA: _D,
    GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT: _D,
    GapKind.WEAK_IV_INSTRUMENT: _D,
    GapKind.OVERIDENTIFICATION_REJECTED: _D,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR: _D,
    GapKind.PROPENSITY_OVERLAP_VIOLATION: _D,
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION: _D,
    GapKind.DECLARED_TYPE_DATA_MISMATCH: _D,
    GapKind.PROXY_COARSENING_UNDECLARED: _D,
    GapKind.REGULARISATION_IS_MOVING_THE_ANSWER: _D,
    GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE: _D,
    # --- the caller's own words, handed back ---------------------------------
    GapKind.LLM_DECLARED_AMBIGUITY: _R,
    GapKind.MEASUREMENT_ERROR_CONCERN: _R,
    GapKind.GRAPH_LEARNED_FROM_DATA: _R,
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED: _R,
    GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED: _R,
    GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED: _R,
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED: _R,
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED: _R,
}


def _bind() -> None:
    """The vocabulary is closed, so coverage of it can be a fact.

    A gap kind that reaches a reader without a line here is one nobody
    decided about, and an undecided claim is indistinguishable from an
    audited one at the door.
    """
    unclassified = sorted(k.value for k in GapKind if k not in SETTLED_BY)
    if unclassified:
        raise RuntimeError(
            f"gap kind(s) {unclassified} reach a reader with no statement of "
            f"what settles their claim; a refusal nobody classified is a "
            f"refusal nobody can be said to have checked")
    misfiled = sorted(k.value for k in _REFUTERS
                      if SETTLED_BY.get(k) is not THE_PROGRAM)
    if misfiled:
        raise RuntimeError(
            f"witness search bound for {misfiled}, whose claim is not the "
            f"program's to settle; a search over the graph cannot refute a "
            f"claim about the data")


_bind()


#: Program-settled kinds this door cannot yet exhibit a witness against.
#: Computed rather than listed, so the day one is closed the set changes on
#: its own and the test that pins it says which.
UNWITNESSED: frozenset[GapKind] = frozenset(
    k for k, s in SETTLED_BY.items()
    if s is THE_PROGRAM and k not in _REFUTERS)


# ===================================================== the pass


def verify_refusal_claims(report: dict, facts: RefusalFacts) -> None:
    """Refuse a gap report that says the program blocks what it does not.

    Raises :class:`VerificationError` naming the witness. Returns ``None``
    when no gap could be refuted, which is not the same as every gap being
    confirmed and does not claim to be.
    """
    if not isinstance(report, dict):
        return
    for position, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, dict):
            continue
        try:
            kind = GapKind(str(gap.get("kind")))
        except ValueError:
            raise VerificationError(
                f"gap {position} declares kind {gap.get('kind')!r}, which is "
                f"not in the gap vocabulary") from None
        refuter = _REFUTERS.get(kind)
        if refuter is None:
            continue
        witness = refuter(gap, facts)
        if witness is not None:
            raise VerificationError(
                f"gap {position} says {kind.value}, and the program says "
                f"otherwise: {witness}. A reader is being sent to collect "
                f"data for an estimand this graph already identifies")
