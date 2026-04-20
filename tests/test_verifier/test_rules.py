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
