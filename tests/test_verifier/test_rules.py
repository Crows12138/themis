"""Unit tests for verifier rules R1..R5.

Each rule gets a positive test (a claim the rule accepts) and a
negative test (a tampered claim the rule rejects). All tests build
the graph, atoms, and derivation by hand — no dependency on any
e2e fixture, scheduler, or elaborator.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.types import (
    Atom,
    ConstTerm,
    DerivationStep,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ProbabilityRefExpr,
    StepRef,
    StructuralResult,
    SumExpr,
    ValuedAtom,
)
from themis.verifier import (
    RuleNotFoundError,
    StepRefError,
    VerificationContext,
    VerificationError,
    verify_identify,
    verify_numeric_estimate,
)
from themis.verifier.errors import RuleCheckFailed, UnknownRuleInputError


# --------------------------------------------------------- fixtures

def _atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _confounded_graph():
    """Classic confounded triangle: stress → smokes → cancer; stress → cancer.

    X = smokes, Y = cancer, backdoor adjustment set = {stress}.
    """
    stress = _atom("stress")
    smokes = _atom("smokes")
    cancer = _atom("cancer")
    g = nx.DiGraph()
    g.add_nodes_from([stress, smokes, cancer])
    g.add_edges_from([
        (stress, smokes),
        (stress, cancer),
        (smokes, cancer),
    ])
    return g, stress, smokes, cancer


def _identify_query(x: Atom, y: Atom, *, x_value=False) -> IdentifyQuery:
    return IdentifyQuery(
        target=y,
        intervention=Intervention(atom=x, value=x_value),
        given=(),
    )


def _ctx(g, x, y) -> VerificationContext:
    return VerificationContext(graph=g, query=_identify_query(x, y))


# =============================================================== R1

def test_r1_accepts_dag():
    g, _, x, y = _confounded_graph()
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": g},
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(VerificationError, match="last derivation step"):
        # last step output True != StructuralResult(True); we only
        # want to hit R1 and then fail at the result-match stage.
        verify_identify(deriv, _ctx(g, x, y), StructuralResult(value=True))


def test_r1_rejects_cycle():
    a = _atom("a")
    b = _atom("b")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, a)])
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": g},
            output=True,  # claim it's a DAG
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="graph_is_dag"):
        verify_identify(deriv, VerificationContext(
            graph=g,
            query=_identify_query(a, b),
        ), StructuralResult(value=True))


def test_r1_rejects_graph_mismatch_with_context():
    g_ctx, _, x, y = _confounded_graph()
    # A different graph — missing one edge.
    g_deriv = g_ctx.copy()
    g_deriv.remove_edge(*list(g_deriv.edges())[0])
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": g_deriv},
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="differs from context"):
        verify_identify(deriv, _ctx(g_ctx, x, y), StructuralResult(value=True))


# =============================================================== R2

def test_r2_accepts_true_d_separation():
    """In stress→smokes→cancer + stress→cancer, conditioning on {stress}
    d-separates the backdoor path between smokes and cancer via stress.
    But in the original graph (not mutated), a direct edge smokes→cancer
    remains, so they are NOT d-separated overall — test with a graph
    that actually produces a d-sep we can claim."""
    # Path: a → b → c, nothing else. Condition on b.
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])

    deriv = (
        DerivationStep(
            rule="d_separation_check",
            inputs={"graph": g, "x": a, "y": c, "z": frozenset({b})},
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(VerificationError, match="last derivation step"):
        verify_identify(deriv, VerificationContext(
            graph=g,
            query=_identify_query(a, c),
        ), StructuralResult(value=True))


def test_r2_rejects_false_claim_of_d_separation():
    """a → b → c with no conditioning: a and c are d-connected. Claiming
    d-separation must be rejected."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    deriv = (
        DerivationStep(
            rule="d_separation_check",
            inputs={"graph": g, "x": a, "y": c, "z": frozenset()},
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="d_separation_check"):
        verify_identify(deriv, VerificationContext(
            graph=g,
            query=_identify_query(a, c),
        ), StructuralResult(value=True))


# =============================================================== R3

def test_r3_accepts_valid_backdoor_set():
    g, stress, smokes, cancer = _confounded_graph()
    deriv = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": g, "x": smokes, "y": cancer,
                "z": frozenset({stress}), "given": frozenset(),
            },
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(VerificationError, match="last derivation step"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=True))


def test_r3_rejects_descendant_in_adjustment_set():
    """cancer is a descendant of smokes, so it can't be in Z."""
    g, stress, smokes, cancer = _confounded_graph()
    deriv = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": g, "x": smokes, "y": cancer,
                "z": frozenset({cancer}),  # invalid: cancer ∈ descendants(smokes)
                "given": frozenset(),
            },
            output=True,
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="backdoor_criterion"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=True))


def test_r3_rejects_empty_set_when_confounder_exists():
    g, _stress, smokes, cancer = _confounded_graph()
    deriv = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": g, "x": smokes, "y": cancer,
                "z": frozenset(),
                "given": frozenset(),
            },
            output=True,  # claiming ∅ blocks — wrong
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="backdoor_criterion"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=True))


# =============================================================== R4

def test_r4_accepts_correct_backdoor_formula():
    g, stress, smokes, cancer = _confounded_graph()
    target = ValuedAtom(atom=cancer, value=None)
    intervention = ValuedAtom(atom=smokes, value=False)

    # Expected formula: Σ_{stress} P(cancer | smokes=False, stress) P(stress)
    from themis.verifier.rules import _build_expected_backdoor_formula
    expected = _build_expected_backdoor_formula(
        target=target, intervention=intervention,
        adjustment_set=(stress,), observed=(),
    )
    assert isinstance(expected, SumExpr)  # sanity: it's a single sum

    deriv = (
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={
                "target": target, "intervention": intervention,
                "z": (stress,), "given": (),
            },
            output=expected,
            step_id="s1",
        ),
    )
    with pytest.raises(VerificationError, match="last derivation step"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=True))


def test_r4_rejects_wrong_formula_shape():
    g, stress, smokes, cancer = _confounded_graph()
    target = ValuedAtom(atom=cancer, value=None)
    intervention = ValuedAtom(atom=smokes, value=False)

    # Hand in a naive P(cancer | smokes) — missing the sum over stress.
    wrong = ProbabilityRefExpr(target=target, given=(intervention,))
    deriv = (
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={
                "target": target, "intervention": intervention,
                "z": (stress,), "given": (),
            },
            output=wrong,
            step_id="s1",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="backdoor_adjustment_formula"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=True))


def test_r4_empty_adjustment_gives_direct_conditional():
    """Z = () ⇒ formula is P(target | intervention, observed) — no sum."""
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_edge(a, b)
    target = ValuedAtom(atom=b, value=None)
    intervention = ValuedAtom(atom=a, value=True)

    from themis.verifier.rules import _build_expected_backdoor_formula
    expected = _build_expected_backdoor_formula(
        target=target, intervention=intervention, adjustment_set=(), observed=()
    )
    assert isinstance(expected, ProbabilityRefExpr)
    assert expected.given == (intervention,)


# =============================================================== R5

def _full_confounded_derivation():
    g, stress, smokes, cancer = _confounded_graph()
    target = ValuedAtom(atom=cancer, value=None)
    intervention = ValuedAtom(atom=smokes, value=False)
    from themis.verifier.rules import _build_expected_backdoor_formula
    formula = _build_expected_backdoor_formula(
        target=target, intervention=intervention, adjustment_set=(stress,), observed=()
    )
    result = StructuralResult(value=True)
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": g}, output=True, step_id="s1",
        ),
        DerivationStep(
            rule="backdoor_criterion",
            inputs={"graph": g, "x": smokes, "y": cancer,
                    "z": frozenset({stress}), "given": frozenset()},
            output=True, step_id="s2",
        ),
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={"target": target, "intervention": intervention,
                    "z": (stress,), "given": ()},
            output=formula, step_id="s3",
        ),
        DerivationStep(
            rule="identify_via_backdoor",
            inputs={"criterion": StepRef("s2"), "formula": StepRef("s3")},
            output=result, step_id="s4",
        ),
    )
    return g, smokes, cancer, deriv, result


def test_r5_accepts_full_chain():
    g, smokes, cancer, deriv, result = _full_confounded_derivation()
    verify_identify(deriv, _ctx(g, smokes, cancer), result)  # must not raise


def test_r5_rejects_when_criterion_step_claims_false():
    """If the backdoor_criterion step somehow claims False, R5's
    chain logic should refuse to close identify_via_backdoor."""
    g, smokes, cancer, deriv, result = _full_confounded_derivation()
    # Replace s2 with a step that claims False (and still recomputes False
    # honestly — pick a Z that doesn't work).
    new_s2 = DerivationStep(
        rule="backdoor_criterion",
        inputs={"graph": g, "x": smokes, "y": cancer,
                "z": frozenset(), "given": frozenset()},
        output=False, step_id="s2",
    )
    bad = (deriv[0], new_s2, deriv[2], deriv[3])
    with pytest.raises(RuleCheckFailed, match="criterion step did not prove True"):
        verify_identify(bad, _ctx(g, smokes, cancer), result)


def test_r5_rejects_step_ref_to_missing_id():
    g, smokes, cancer, deriv, result = _full_confounded_derivation()
    bad_s4 = DerivationStep(
        rule="identify_via_backdoor",
        inputs={"criterion": StepRef("nope"), "formula": StepRef("s3")},
        output=result, step_id="s4",
    )
    bad = (deriv[0], deriv[1], deriv[2], bad_s4)
    with pytest.raises(StepRefError, match="no earlier step"):
        verify_identify(bad, _ctx(g, smokes, cancer), result)


def test_r5_rejects_formula_ref_to_non_formula_rule():
    """R5 must point at a real backdoor_adjustment_formula witness,
    not just any earlier step."""
    g, smokes, cancer, deriv, result = _full_confounded_derivation()
    bad_s4 = DerivationStep(
        rule="identify_via_backdoor",
        inputs={"criterion": StepRef("s2"), "formula": StepRef("s1")},
        output=result,
        step_id="s4",
    )
    bad = (deriv[0], deriv[1], deriv[2], bad_s4)
    with pytest.raises(RuleCheckFailed, match="formula must reference a backdoor_adjustment_formula step"):
        verify_identify(bad, _ctx(g, smokes, cancer), result)


# =============================================================== verifier-level

def test_unknown_rule_is_rejected():
    g, _, x, y = _confounded_graph()
    deriv = (
        DerivationStep(rule="frobnicate", inputs={}, output=True, step_id="s1"),
    )
    with pytest.raises(RuleNotFoundError, match="frobnicate"):
        verify_identify(deriv, _ctx(g, x, y), StructuralResult(value=True))


def test_missing_required_input_is_rejected():
    g, _, x, y = _confounded_graph()
    deriv = (
        DerivationStep(
            rule="d_separation_check",
            inputs={"graph": g, "x": x, "y": y},  # missing "z"
            output=True, step_id="s1",
        ),
    )
    with pytest.raises(UnknownRuleInputError, match="z"):
        verify_identify(deriv, _ctx(g, x, y), StructuralResult(value=True))


def test_empty_derivation_is_rejected():
    g, _, x, y = _confounded_graph()
    with pytest.raises(VerificationError, match="empty"):
        verify_identify((), _ctx(g, x, y), StructuralResult(value=True))


def test_final_output_must_equal_claimed_result():
    """Even if every step passes, the last step's output must equal
    claimed_result. Otherwise the derivation is about a different
    question than the one being verified."""
    g, smokes, cancer, deriv, _ = _full_confounded_derivation()
    with pytest.raises(VerificationError, match="does not equal claimed"):
        verify_identify(deriv, _ctx(g, smokes, cancer), StructuralResult(value=False))


# ============================================ identify-shaped binding
#
# ``_assert_query_binding`` is installed by three entry points, and two of
# them (verify_numeric_estimate, verify_effect_structural) carry an
# EffectQuery rather than an IdentifyQuery. The two query types state the
# same target at different shapes — a bare ``Atom`` for identify, a
# ``ValuedAtom`` carrying the queried literal for effect — so a branch
# that unpacks the query itself binds correctly for one type and compares
# incommensurable shapes for the other. Comparing incommensurable shapes
# never raises an error saying so; it just rejects everything, including
# every honest derivation, under a message claiming a mismatch that is
# not one. The tests below fix what "the step names the active query"
# means on the effect side, in both directions.

_FAKE_DATA_HASH = "a" * 64


def _effect_query(x: Atom, y: Atom, *, x_value=True, y_value=True, given=()):
    return EffectQuery(
        target=ValuedAtom(atom=y, value=y_value),
        intervention=Intervention(atom=x, value=x_value),
        given=given,
    )


def _two_outcome_graph():
    """The confounded triangle plus a second outcome sharing both the
    treatment and the confounder: stress → {smokes, cancer, cough},
    smokes → {cancer, cough}.

    The second outcome is what makes the replay tests below sharp. Pointed
    at ``cough``, the back-door formula over {stress} is still a perfectly
    well-formed formula — every rule handler accepts it on its own terms —
    so the only thing that can refuse it is the query binding.
    """
    stress, smokes = _atom("stress"), _atom("smokes")
    cancer, cough = _atom("cancer"), _atom("cough")
    g = nx.DiGraph()
    g.add_nodes_from([stress, smokes, cancer, cough])
    g.add_edges_from([
        (stress, smokes), (stress, cancer), (smokes, cancer),
        (stress, cough), (smokes, cough),
    ])
    return g, stress, smokes, cancer, cough


def _effect_backdoor_estimate(pick_formula_target=None):
    """A data-based backdoor estimate that also ships the identification
    formula it estimated, under an EffectQuery for P(cancer=1 | do(smokes=1)).

    ``pick_formula_target(stress, smokes, cancer, cough)`` re-points the
    formula step's target — the one input the binding asserter reads there.
    Left None the step names the query's own target.
    """
    from themis.verifier.rules import _build_expected_backdoor_formula

    g, stress, smokes, cancer, cough = _two_outcome_graph()
    intervention = ValuedAtom(atom=smokes, value=True)
    target = (
        ValuedAtom(atom=cancer, value=True) if pick_formula_target is None
        else pick_formula_target(stress, smokes, cancer, cough)
    )
    formula = _build_expected_backdoor_formula(
        target=target, intervention=intervention,
        adjustment_set=(stress,), observed=(),
    )
    deriv = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={"graph": g, "x": smokes, "y": cancer,
                    "z": frozenset({stress}), "given": frozenset()},
            output=True, step_id="s1",
        ),
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={"target": target, "intervention": intervention,
                    "z": (stress,), "given": ()},
            output=formula, step_id="s2",
        ),
        DerivationStep(
            rule="numeric_backdoor_estimate",
            inputs={
                "criterion": StepRef("s1"),
                "treatment": smokes, "outcome": cancer,
                "adjustment": frozenset({stress}),
                "method": "backdoor_linear",
                "data_hash": _FAKE_DATA_HASH,
                "sample_size": 500,
                "point": 0.3, "ci_lower": 0.1, "ci_upper": 0.5,
                "ci_level": 0.95,
            },
            output=StructuralResult(value=True), step_id="s3",
        ),
    )
    ctx = VerificationContext(graph=g, query=_effect_query(smokes, cancer))
    return ctx, deriv


def test_effect_derivation_may_carry_the_backdoor_formula_it_estimated():
    """Guards the shared binding asserter against degenerating into an
    unconditional reject on the effect path.

    ``backdoor_adjustment_formula`` names its target as a ``ValuedAtom``.
    An IdentifyQuery has to have that shape built for it — its own target
    is a bare atom and its estimand leaves the literal open, so the valued
    shape is ``ValuedAtom(atom, None)``. An EffectQuery already IS that
    shape. Building it unconditionally wraps the effect target a second
    time, and nothing a producer can construct ever equals
    ``ValuedAtom(atom=ValuedAtom(...))`` — so every effect derivation
    carrying this witness gets rejected for a target mismatch that does
    not exist. This derivation is honest end to end: the formula step
    names the exact literal the context asks about. Accepting it is the
    behaviour, not an accident of which shape the code happened to build.
    """
    ctx, deriv = _effect_backdoor_estimate()
    verify_numeric_estimate(deriv, ctx, StructuralResult(value=True))


def test_effect_derivation_rejects_a_backdoor_formula_for_another_literal():
    """Keeps the acceptance above from being a hole rather than a binding.

    On the effect path the queried literal is part of the question:
    P(cancer=1 | do(smokes=1)) and P(cancer=0 | do(smokes=1)) are two
    different quantities with two different answers. So the binding has to
    compare the whole ``ValuedAtom``, not just its atom — a witness built
    for the complementary literal must be refused even though it names the
    right outcome variable, the right treatment and the right adjustment
    set.
    """
    ctx, deriv = _effect_backdoor_estimate(
        lambda stress, smokes, cancer, cough: ValuedAtom(atom=cancer, value=False)
    )
    with pytest.raises(
        VerificationError,
        match="backdoor_adjustment_formula.target does not match",
    ):
        verify_numeric_estimate(deriv, ctx, StructuralResult(value=True))


def test_effect_derivation_rejects_a_backdoor_formula_for_another_outcome():
    """The replay this asserter exists to stop, in its plainest form.

    A back-door formula for cough over the same adjustment set is a valid
    proof — of another query. Nothing about the formula itself is wrong, so
    no rule handler can object to it; only the binding to the context knows
    that the question asked was about cancer.
    """
    ctx, deriv = _effect_backdoor_estimate(
        lambda stress, smokes, cancer, cough: ValuedAtom(atom=cough, value=True)
    )
    with pytest.raises(
        VerificationError,
        match="backdoor_adjustment_formula.target does not match",
    ):
        verify_numeric_estimate(deriv, ctx, StructuralResult(value=True))


def _frontdoor_graph():
    """X → M → Y with no other edge: M satisfies the front-door criterion."""
    x, m, y = _atom("smokes"), _atom("tar"), _atom("cancer")
    g = nx.DiGraph()
    g.add_nodes_from([x, m, y])
    g.add_edges_from([(x, m), (m, y)])
    return g, x, m, y


def _effect_frontdoor_estimate(pick_formula_target=None):
    """The front-door twin of ``_effect_backdoor_estimate``: a data-based
    front-door estimate that also ships the formula it estimated."""
    from themis.verifier.rules import _build_expected_front_door_formula

    g, x, m, y = _frontdoor_graph()
    intervention = ValuedAtom(atom=x, value=True)
    target = (
        ValuedAtom(atom=y, value=True) if pick_formula_target is None
        else pick_formula_target(x, m, y)
    )
    formula = _build_expected_front_door_formula(target, intervention, (m,))
    deriv = (
        DerivationStep(
            rule="front_door_criterion",
            inputs={"graph": g, "x": x, "y": y, "z": frozenset({m})},
            output=True, step_id="s1",
        ),
        DerivationStep(
            rule="front_door_adjustment_formula",
            inputs={"target": target, "intervention": intervention, "z": (m,)},
            output=formula, step_id="s2",
        ),
        DerivationStep(
            rule="numeric_frontdoor_estimate",
            inputs={
                "criterion": StepRef("s1"),
                "treatment": x, "outcome": y,
                "mediators": frozenset({m}),
                "method": "frontdoor_linear",
                "data_hash": _FAKE_DATA_HASH,
                "sample_size": 500,
                "point": 0.3, "ci_lower": 0.1, "ci_upper": 0.5,
                "ci_level": 0.95,
            },
            output=StructuralResult(value=True), step_id="s3",
        ),
    )
    ctx = VerificationContext(graph=g, query=_effect_query(x, y))
    return ctx, deriv


def test_effect_derivation_may_carry_the_front_door_formula_it_estimated():
    """The front-door branch of the same asserter reads the query the same
    way the back-door branch does.

    Front-door and back-door are two identification routes to one kind of
    answer, and both formula rules name their target as a ``ValuedAtom``.
    A reader who fixes one branch and not its twin leaves the verifier
    accepting an honest back-door effect derivation while rejecting the
    identical front-door one — a difference in what the verifier will
    believe that has nothing to do with either method's validity.
    """
    ctx, deriv = _effect_frontdoor_estimate()
    verify_numeric_estimate(deriv, ctx, StructuralResult(value=True))


def test_effect_derivation_rejects_a_front_door_formula_for_another_literal():
    """The front-door twin of the literal-replay refusal above."""
    ctx, deriv = _effect_frontdoor_estimate(
        lambda x, m, y: ValuedAtom(atom=y, value=False)
    )
    with pytest.raises(
        VerificationError,
        match="front_door_adjustment_formula.target does not match",
    ):
        verify_numeric_estimate(deriv, ctx, StructuralResult(value=True))


def _bind_unidentifiable_step(*, ctx_query, step_y, step_given):
    """Run just the binding asserter over an ``unidentifiable_via_backdoor``
    step. No entry point emits this rule under an EffectQuery today, so the
    contract is pinned where it lives rather than through a producer that
    would have to be invented for the test."""
    from themis.verifier.verify import _assert_query_binding

    g, stress, smokes, cancer = _confounded_graph()
    step = DerivationStep(
        rule="unidentifiable_via_backdoor",
        inputs={"graph": g, "x": smokes, "y": step_y(stress, smokes, cancer),
                "given": frozenset(step_given)},
        output=False, step_id="s1",
    )
    ctx = VerificationContext(graph=g, query=ctx_query(smokes, cancer))
    _assert_query_binding(step, ctx, 0, {}, {})


def test_unidentifiable_via_backdoor_binds_to_an_effect_query_bare_atoms():
    """``unidentifiable_via_backdoor`` names bare atoms, so under an effect
    context it must be compared against the query's target ATOM.

    Its inputs are structural — x, y and a conditioning set of plain
    ``Atom``s — because non-identifiability is a property of the graph, not
    of any literal. Comparing them against an EffectQuery's ``ValuedAtom``
    target instead is a shape mismatch that can never hold, which turns the
    branch into a reject of every well-formed step and hides the real
    binding it is supposed to enforce.
    """
    _bind_unidentifiable_step(
        ctx_query=lambda x, y: _effect_query(x, y),
        step_y=lambda stress, smokes, cancer: cancer,
        step_given=(),
    )


def test_unidentifiable_via_backdoor_rejects_another_outcome_under_effect():
    """And the binding still bites: a non-identifiability claim about some
    other outcome on the same graph is not an answer to this query."""
    with pytest.raises(
        VerificationError,
        match="unidentifiable_via_backdoor.y does not match",
    ):
        _bind_unidentifiable_step(
            ctx_query=lambda x, y: _effect_query(x, y),
            step_y=lambda stress, smokes, cancer: stress,
            step_given=(),
        )


def test_unidentifiable_via_backdoor_binds_the_effect_query_given_as_atoms():
    """Same shape question one axis over: the step's ``given`` is a set of
    bare atoms while an EffectQuery's ``given`` carries literals, so the
    comparison has to be made atom-to-atom.

    A step conditioning on a different variable than the query does must
    still be refused — that is the part a shape mismatch would have thrown
    away along with the false rejections.
    """
    g, stress, smokes, cancer = _confounded_graph()
    conditioned = _effect_query(
        smokes, cancer, given=(ValuedAtom(atom=stress, value=True),)
    )
    from themis.verifier.verify import _assert_query_binding

    ok = DerivationStep(
        rule="unidentifiable_via_backdoor",
        inputs={"graph": g, "x": smokes, "y": cancer,
                "given": frozenset({stress})},
        output=False, step_id="s1",
    )
    _assert_query_binding(
        ok, VerificationContext(graph=g, query=conditioned), 0, {}, {},
    )

    unconditioned = DerivationStep(
        rule="unidentifiable_via_backdoor",
        inputs={"graph": g, "x": smokes, "y": cancer, "given": frozenset()},
        output=False, step_id="s1",
    )
    with pytest.raises(
        VerificationError,
        match="unidentifiable_via_backdoor.given does not match",
    ):
        _assert_query_binding(
            unconditioned,
            VerificationContext(graph=g, query=conditioned), 0, {}, {},
        )
