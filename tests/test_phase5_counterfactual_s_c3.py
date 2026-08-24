"""The binary counterfactual-cell primitive.

Everything here exercises the single identity the solver rests on:

    a * P(x, Y=1) + b * P(x, Y=0) = P(Y=1 | do(x')) - P(x', Y=1)

with a = P(Y_{x'}=1 | X=x, Y=1) and b = P(Y_{x'}=1 | X=x, Y=0). The
observational joint used throughout is

    P(X=0, Y=0) = 0.3   P(X=0, Y=1) = 0.2
    P(X=1, Y=0) = 0.1   P(X=1, Y=1) = 0.4

so P(X=0) = P(X=1) = 0.5 and P(Y=1) = 0.6. Consistency confines
P(Y=1|do(X=1)) to [0.4, 0.9] and P(Y=1|do(X=0)) to [0.2, 0.7].
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis import refusals
from themis.refusals import Refusal
from themis.runtime.counterfactual import (
    CounterfactualBoundsError,
    CounterfactualInfeasible,
    InterventionalRiskRequired,
    counterfactual_cell_interval,
    monotonicity_pins,
    project_twin_network,
)
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.ledger import Monotonicity
from themis.types import (
    Atom,
    CauseStatement,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    Intervention,
    NumericInterval,
    ProbabilityStatement,
    Program,
    QueryStatement,
    ResultStatus,
    ValuedAtom,
    VariableDeclaration,
)


JOINT = {
    (False, False): 0.3,
    (False, True): 0.2,
    (True, False): 0.1,
    (True, True): 0.4,
}


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _base_query(
    *,
    monotonicity: Monotonicity | None = Monotonicity.NON_DECREASING,
    x_obs: bool = False,
    x_cf: bool = True,
    y_cf: bool = True,
    factual_y: bool | None = None,
) -> CounterfactualQuery:
    x = _atom("treat")
    y = _atom("recover")
    return CounterfactualQuery(
        observed=ValuedAtom(atom=x, value=x_obs),
        counterfactual_intervention=Intervention(atom=x, value=x_cf),
        counterfactual_target=ValuedAtom(atom=y, value=y_cf),
        assumptions=(
            None
            if monotonicity is None
            else CounterfactualAssumptions(monotonicity=monotonicity)
        ),
        factual_target_known=factual_y,
    )


def _twin(query: CounterfactualQuery):
    x = query.observed.atom
    y = query.counterfactual_target.atom
    g = nx.DiGraph()
    g.add_edge(x, y)
    return project_twin_network(g, frozenset(), query)


def _cell(query, joint=None, risk=None):
    return counterfactual_cell_interval(
        _twin(query), query, joint or JOINT, p_y_do_x_cf=risk,
    )


def _approx(interval, low, high, tol=1e-9):
    return abs(interval.low - low) <= tol and abs(interval.high - high) <= tol


# --------------------------------------------------------------- same world

def test_returns_point_by_consistency_when_worlds_match():
    query = _base_query(x_obs=False, x_cf=False, y_cf=True)

    assert _cell(query) == NumericInterval(low=0.4, high=0.4)


def test_returns_point_from_known_factual_target_when_worlds_match():
    query = _base_query(x_obs=False, x_cf=False, y_cf=True, factual_y=True)

    assert _cell(query) == NumericInterval(low=1.0, high=1.0)


def test_same_world_needs_no_interventional_risk():
    """Consistency alone answers it, so the solver must not ask for a risk."""
    query = _base_query(monotonicity=None, x_obs=True, x_cf=True, y_cf=False)

    assert _approx(_cell(query), 0.2, 0.2)


# ------------------------------------------------------- the ETT identity

def test_no_factual_outcome_is_point_identified_not_bounded():
    """P(Y_{x'}=1 | X=x) is exact once the interventional risk is known.

    K = 0.7 - P(X=1, Y=1) = 0.3, divided by P(X=0) = 0.5.
    """
    query = _base_query(monotonicity=None, x_obs=False, x_cf=True, y_cf=True)

    assert _approx(_cell(query, risk=0.7), 0.6, 0.6)


def test_no_factual_outcome_point_is_unchanged_by_monotonicity():
    """Monotonicity constrains the cells, not their observational average."""
    free = _cell(_base_query(monotonicity=None), risk=0.7)
    mono = _cell(_base_query(monotonicity=Monotonicity.NON_DECREASING), risk=0.7)

    assert free == mono


def test_no_factual_outcome_complements_for_y_false():
    query = _base_query(monotonicity=None, x_obs=False, x_cf=True, y_cf=False)

    assert _approx(_cell(query, risk=0.7), 0.4, 0.4)


# ------------------------------------------------ assumption-free bounds

def test_ps_cell_reproduces_the_tian_pearl_bounds():
    """PS = P(Y_{x=1}=1 | X=0, Y=0) with no assumptions.

    Lower (eq 26) = (0.7 - 0.6) / 0.3, upper = min(1, (0.7 - 0.4) / 0.3).
    """
    query = _base_query(
        monotonicity=None, x_obs=False, x_cf=True, y_cf=True, factual_y=False,
    )

    assert _approx(_cell(query, risk=0.7), 1.0 / 3.0, 1.0)


def test_pn_cell_reproduces_the_tian_pearl_bounds():
    """PN = P(Y_{x=0}=0 | X=1, Y=1) with no assumptions.

    Lower (eq 25) = (P(Y=1) - P(y|do(x=0))) / P(X=1,Y=1) = (0.6 - 0.5) / 0.4.
    Upper = (P(X=1) - 0.5 + P(X=0,Y=1)) / 0.4 = (0.5 - 0.5 + 0.2) / 0.4.
    """
    query = _base_query(
        monotonicity=None, x_obs=True, x_cf=False, y_cf=False, factual_y=True,
    )

    assert _approx(_cell(query, risk=0.5), 0.25, 0.5)


def test_bounds_are_informative_where_the_old_monotone_only_path_was_vacuous():
    """The PN cell used to come back [0, 1] under monotonicity alone."""
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=True, x_cf=False, y_cf=False, factual_y=True,
    )
    with pytest.raises(InterventionalRiskRequired):
        _cell(query)

    got = _cell(query, risk=0.5)

    assert got.low > 0.0 and got.high < 1.0


# --------------------------------------------- monotonicity as a constraint

def test_monotonicity_pins_exactly_one_cell():
    non_dec_x1 = _base_query(x_obs=True, x_cf=False)
    non_dec_x0 = _base_query(x_obs=False, x_cf=True)
    non_inc_x1 = _base_query(
        monotonicity=Monotonicity.NON_INCREASING, x_obs=True, x_cf=False,
    )
    non_inc_x0 = _base_query(
        monotonicity=Monotonicity.NON_INCREASING, x_obs=False, x_cf=True,
    )

    assert monotonicity_pins(non_dec_x1) == {False: 0.0}
    assert monotonicity_pins(non_dec_x0) == {True: 1.0}
    assert monotonicity_pins(non_inc_x1) == {True: 1.0}
    assert monotonicity_pins(non_inc_x0) == {False: 0.0}
    assert monotonicity_pins(_base_query(monotonicity=None)) == {}


def test_pinned_cell_is_answered_without_any_interventional_risk():
    """Non-decreasing + X=0 factual + Y=1 factual forces Y_{x=1} = 1."""
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=False, x_cf=True, y_cf=True, factual_y=True,
    )

    assert _cell(query) == NumericInterval(low=1.0, high=1.0)


def test_pinning_the_other_cell_collapses_the_bounds_to_the_monotone_point():
    """Tian-Pearl's monotone PS point (eq 42) falls out of the constraint.

    Non-decreasing pins P(Y_1=1 | X=0, Y=1) = 1, and the identity then
    leaves PS = (0.3 - 1 * 0.2) / 0.3 = (P(y|do(x)) - P(y)) / P(x', y').
    """
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=False, x_cf=True, y_cf=True, factual_y=False,
    )

    assert _approx(_cell(query, risk=0.7), 1.0 / 3.0, 1.0 / 3.0)


def test_non_increasing_pins_the_mirror_cell():
    """Non-increasing + X=1 factual + Y=1 factual forces Y_{x=0} = 1."""
    query = _base_query(
        monotonicity=Monotonicity.NON_INCREASING,
        x_obs=True, x_cf=False, y_cf=True, factual_y=True,
    )

    assert _cell(query) == NumericInterval(low=1.0, high=1.0)


# ------------------------------------------------------------ refutations

def test_missing_monotonicity_is_no_longer_a_precondition():
    query = _base_query(monotonicity=None, factual_y=False)

    assert _approx(_cell(query, risk=0.7), 1.0 / 3.0, 1.0)


def test_names_the_arm_it_needs_instead_of_returning_a_vacuous_interval():
    query = _base_query(monotonicity=None, x_obs=True, x_cf=False, factual_y=True)

    with pytest.raises(InterventionalRiskRequired) as excinfo:
        _cell(query)

    assert excinfo.value.needed_x_value is False


def test_rejects_an_interventional_risk_the_joint_forbids():
    """P(Y=1|do(X=1)) must lie in [P(X=1,Y=1), P(X=1,Y=1) + P(X=0)].

    NOT the "infeasible" subclass, and the query here says why: it
    declares no monotonicity, so there is no assumption for the data to
    refute. What contradicts is the caller's own two sources.
    """
    query = _base_query(monotonicity=None, factual_y=False)

    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(query, risk=0.95)
    assert excinfo.value.failure_type is Refusal.INPUTS_CONTRADICT_BY_CONSISTENCY
    assert not isinstance(excinfo.value, CounterfactualInfeasible)
    assert excinfo.value.details == {
        "intervention": True, "given": 0.95, "lower": 0.4, "upper": 0.9,
    }


def test_reports_monotonicity_refuted_rather_than_clamping_to_a_boundary():
    """Non-decreasing pins the other cell at 1, which needs K >= 0.2.

    P(Y=1|do(X=1)) = 0.5 is perfectly feasible on its own (K = 0.1) but
    leaves the PS cell at -1/3. Clamping would report a confident 0.
    """
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=False, x_cf=True, y_cf=True, factual_y=False,
    )

    with pytest.raises(CounterfactualInfeasible) as excinfo:
        _cell(query, risk=0.5)
    assert excinfo.value.failure_type is Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE
    # Which evidence refuted it is the occasion's, and travels as a word:
    # the same species is filed by the response polytope off a different
    # table entirely.
    assert excinfo.value.details == {
        "refuted_by": refusals.Refutation.CELL_FEASIBLE_SET,
    }

    # ... and without the monotonicity claim the very same inputs are fine.
    free = _base_query(
        monotonicity=None, x_obs=False, x_cf=True, y_cf=True, factual_y=False,
    )
    assert _cell(free, risk=0.5).low >= 0.0


def test_rejects_a_risk_outside_zero_one():
    query = _base_query(monotonicity=None, factual_y=False)

    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(query, risk=1.4)
    assert excinfo.value.failure_type is Refusal.NOT_A_PROBABILITY
    assert excinfo.value.details["given"] == 1.4


# ------------------------------------------------------------- validation

def test_rejects_incomplete_joint_table():
    query = _base_query()
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, True): 0.5,
    }

    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(query, joint=joint)
    assert excinfo.value.failure_type is Refusal.MALFORMED_ARGUMENT
    assert excinfo.value.details["argument"] == "observed_joint_xy"


def test_rejects_joint_table_that_does_not_sum_to_one():
    query = _base_query()
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.5,
    }

    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(query, joint=joint)
    assert excinfo.value.failure_type is Refusal.PROBABILITIES_DO_NOT_SUM
    assert excinfo.value.details["given"] == pytest.approx(1.1)


def test_rejects_zero_mass_on_the_observed_treatment():
    query = _base_query(x_obs=True, x_cf=False)
    joint = {
        (False, False): 0.4,
        (False, True): 0.6,
        (True, False): 0.0,
        (True, True): 0.0,
    }

    # The same species the ID*/IDC* evaluator files when P(δ)=0: what is
    # conditioned on has no mass, so the cell is undefined rather than
    # unknown. The event travels as a slot so both sites can name theirs.
    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(query, joint=joint)
    assert excinfo.value.failure_type is Refusal.UNDEFINED_CONDITIONING_EVENT
    assert excinfo.value.details == {"event": "treat=True"}


def test_undefined_cell_with_zero_conditioning_mass_stays_uninformative():
    """P(X=0, Y=1) = 0 makes that cell undefined; the box is all there is."""
    query = _base_query(
        monotonicity=None, x_obs=False, x_cf=True, y_cf=True, factual_y=True,
    )
    joint = {
        (False, False): 0.5,
        (False, True): 0.0,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    assert _cell(query, joint=joint, risk=0.7) == NumericInterval(low=0.0, high=1.0)


# ------------------------------------------- values the solver cannot read

@pytest.mark.parametrize(
    "role, kwargs",
    [
        ("observed", {"x_obs": None}),
        ("counterfactual_intervention", {"x_cf": None}),
        ("counterfactual_target", {"y_cf": None}),
    ],
)
def test_an_absent_query_value_is_refused_and_named(role, kwargs):
    """Absence is not a third case this solver can answer, and it has to
    say which value went missing rather than improvise past it.

    Each of these three steers something: two of them index the binary
    joint, the third picks which cell is being asked for. A missing one
    does not degrade — it either fell off the end of the table as a bare
    ``KeyError`` or was read as merely falsy, both covered just below.
    The role travels as a SLOT of the species' sentence, because that
    sentence ends up in the refusal a reader holds, and "one of your
    values is wrong" is not something a reader can act on.
    """
    with pytest.raises(CounterfactualBoundsError) as excinfo:
        _cell(_base_query(**kwargs), risk=0.7)
    assert excinfo.value.failure_type is Refusal.COUNTERFACTUAL_CELL_NOT_BINARY
    assert excinfo.value.details == {"label": role, "given": None}


def test_an_absent_counterfactual_target_is_not_read_as_false():
    """The failure being refused here used to be silent, which is the
    whole reason it is worth a test of its own.

    ``counterfactual_target=None`` flowed into ``p_y1 if y_star else
    1.0 - p_y1``, where ``None`` is merely falsy: the solver answered
    the *complementary* question and returned it as a point, with no
    interval, no caveat and no refusal. So this does not only check that
    something is raised — it names the number that used to come back.
    Asking for ``Y=True`` on this joint is 0.6 and asking for ``Y=False``
    is 0.4, and 0.4 is exactly what a missing target used to produce.
    """
    assert _approx(_cell(_base_query(monotonicity=None), risk=0.7), 0.6, 0.6)
    assert _approx(
        _cell(_base_query(monotonicity=None, y_cf=False), risk=0.7), 0.4, 0.4
    )

    with pytest.raises(CounterfactualBoundsError):
        _cell(_base_query(monotonicity=None, y_cf=None), risk=0.7)


def test_an_absent_factual_outcome_still_means_it_is_not_evidence():
    """``factual_target_known`` is the one value whose absence is itself
    a statement, so the check above has to carve it out.

    Absent, the query is P(Y_{x'}=1 | X=x) and the interventional risk
    identifies it as a point; present, it is P(Y_{x'}=1 | X=x, Y=y),
    a strictly harder question that generally only bounds. A carve-out
    with nothing exercising it is a carve-out the next reader tidies
    away for consistency, so both sides are pinned: absent stays
    accepted, and it stays a different question from known.
    """
    absent = _cell(_base_query(monotonicity=None, factual_y=None), risk=0.7)
    known_false = _cell(
        _base_query(monotonicity=None, factual_y=False), risk=0.7
    )

    assert _approx(absent, 0.6, 0.6)
    assert _approx(known_false, 1 / 3, 1.0)


# ------------------------------------------ the refusal reaches the reader

def _program_for(query: CounterfactualQuery) -> Program:
    """The JOINT above, spelled as a program the scheduler can dispatch."""
    x, y = _atom("treat"), _atom("recover")
    p_x = {xv: JOINT[(xv, False)] + JOINT[(xv, True)] for xv in (False, True)}
    statements: list = [
        CauseStatement(from_atom=x, to_atom=y),
        VariableDeclaration(predicate="treat", domain=(True, False)),
        VariableDeclaration(predicate="recover", domain=(True, False)),
    ]
    for xv in (False, True):
        statements.append(
            ProbabilityStatement(
                target=ValuedAtom(atom=x, value=xv), given=(), value=p_x[xv],
            )
        )
        for yv in (False, True):
            statements.append(
                ProbabilityStatement(
                    target=ValuedAtom(atom=y, value=yv),
                    given=(ValuedAtom(atom=x, value=xv),),
                    value=JOINT[(xv, yv)] / p_x[xv],
                )
            )
    statements.append(QueryStatement(id="q_cf", query=query))
    return Program(version="0.1", objects=(), statements=tuple(statements))


def _dispatch(query: CounterfactualQuery):
    program = _program_for(query)
    (result,) = dispatch_all(program, project(instantiate(program)))
    return result


def test_a_value_the_solver_cannot_read_comes_back_as_a_refusal():
    """Raising the declared exception type is only half of the fix; this
    is the half that checks somebody catches it.

    ``themis.estimation.counterfactual_cell`` and
    ``themis.runtime.scheduler`` each catch this family, so the bare
    ``KeyError`` the cell solver used to raise walked past both handlers
    and left ``themis.run`` as a traceback — a kernel crash where the
    contract says a refusal. What a reader ends up holding is asserted
    here, sentence included, not just what the primitive throws.

    The species used to be ``counterfactual_cell_out_of_scope``, which
    said "one of ten things this solver will not do" and could carry no
    sentence at all; the sentence a reader got was the solver's own, in
    English, relayed by ``str(exc)``.
    """
    solved = _dispatch(_base_query())
    assert solved.status is ResultStatus.COUNTERFACTUAL_SOLVED

    refused = _dispatch(_base_query(x_obs=None))
    assert refused.status is ResultStatus.OUTSIDE_LANGUAGE
    assert refused.numeric_result is None
    failure = refused.estimator_failure
    assert failure["failure_type"] == "counterfactual_cell_not_binary"
    assert failure["details"] == {"label": "observed", "given": None}
    assert refusals.said(failure) == refusals.sentence(
        Refusal.COUNTERFACTUAL_CELL_NOT_BINARY,
        {"label": "observed", "given": None})


def test_an_unreadable_target_is_refused_rather_than_answered():
    """A wrong number wearing a success status is worse than a crash,
    because nothing downstream has any reason to doubt it.

    With ``counterfactual_target=None`` the whole pipeline used to return
    ``COUNTERFACTUAL_SOLVED`` carrying the point value for ``Y=False``
    — 0.2 where the reader's own question, ``Y=True``, answers 0.8 —
    and every surface downstream printed it as the answer.
    """
    asked = _dispatch(_base_query(y_cf=True))
    assert asked.status is ResultStatus.COUNTERFACTUAL_SOLVED
    assert asked.numeric_result.value == pytest.approx(0.8)

    complement = _dispatch(_base_query(y_cf=False))
    assert complement.numeric_result.value == pytest.approx(0.2)

    refused = _dispatch(_base_query(y_cf=None))
    assert refused.status is ResultStatus.OUTSIDE_LANGUAGE
    assert refused.numeric_result is None
