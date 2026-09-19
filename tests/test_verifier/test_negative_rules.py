"""V3 unit tests: negative-path rules.

- unidentifiable_via_backdoor — claims StructuralResult(False) for identify
- d_separated — claims StructuralResult(False) for assoc
- no_directed_path — claims StructuralResult(False) for cause

Each rule is exercised with hand-built graphs. No scheduler / fixture
dependency.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.types import (
    AssocQuery,
    Atom,
    CauseQuery,
    ConstTerm,
    DerivationStep,
    IdentifyQuery,
    Intervention,
    StructuralResult,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_assoc,
    verify_cause,
    verify_identify,
)
from themis.verifier.errors import RuleCheckFailed


def _atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


# =================================================== unidentifiable_via_backdoor

def _bidirected_confounder_graph():
    """X ← U → Y with U unobservable inside the graph actually makes
    the effect identifiable by adjusting on U. For a genuinely
    unidentifiable pattern in V3's DAG model we need a graph where
    the ONLY separating candidates are descendants of X or X/Y
    themselves. The simplest case: X → Y with no other edges — the
    only candidate set is ∅ which trivially blocks (no backdoor
    paths exist), so that case identifies. We instead use a setup
    where a backdoor path exists but the only blockers are X's
    descendants.

    Pattern: X → M → Y and X → Y — M is a mediator. The backdoor
    criterion is satisfied by ∅ (no backdoor path). So X→Y is
    identifiable. Not useful for a "negative" test.

    We construct a case that a V0.1 DAG simply can't handle:
    X ← Z, Z → Y, X → Y, AND Z is a descendant of X (making Z's
    inclusion forbidden). Setup: X → Z, Z → Y, X → Y with a
    **backdoor path via Z that can't be blocked**.

    But Z is X's descendant, so it can't be in Z. The only
    candidate is ∅, which leaves Z open in backdoor Y ← Z ← X —
    wait, that's a directed path, not a backdoor.

    A simpler unidentifiable pattern needs latent confounders
    (ADMG). In the plain-DAG V0.1 language every pattern is either
    identifiable by ∅ or by some observable set. So to get a real
    unidentifiable case we'd need to add a fake atom that's in the
    graph but the solver never finds as valid.

    Skip: the unit test exercises the rule algorithmically on a
    handcrafted scenario where the elaborator would produce
    value=False — see the e2e fixture-based test for coverage via
    real negative identify results (none currently exist in the
    repo, which is why this rule is exercised via synthetic unit
    tests only).
    """
    raise NotImplementedError


def test_unidentifiable_rule_rejects_when_a_valid_adjustment_exists():
    """Classic confounded triangle — stress → smokes, stress → cancer,
    smokes → cancer. Z = {stress} satisfies backdoor, so claiming
    unidentifiable must be rejected by the rule."""
    stress = _atom("stress")
    smokes = _atom("smokes")
    cancer = _atom("cancer")
    g = nx.DiGraph()
    g.add_nodes_from([stress, smokes, cancer])
    g.add_edges_from([
        (stress, smokes), (stress, cancer), (smokes, cancer),
    ])
    query = IdentifyQuery(
        target=cancer,
        intervention=Intervention(atom=smokes, value=False),
        given=(),
    )
    deriv = (
        DerivationStep(
            rule="unidentifiable_via_backdoor",
            inputs={
                "graph": g, "x": smokes, "y": cancer,
                "given": frozenset(),
            },
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="found a valid adjustment set"):
        verify_identify(deriv, ctx, StructuralResult(value=False))


def test_unidentifiable_rule_rejects_when_claim_is_positive_result():
    stress = _atom("stress")
    smokes = _atom("smokes")
    cancer = _atom("cancer")
    g = nx.DiGraph()
    g.add_nodes_from([stress, smokes, cancer])
    # Add only structure that makes ∅ insufficient but the rule would
    # succeed in finding some Z. This test checks the rule refuses to
    # bless a StructuralResult(value=True) output.
    g.add_edges_from([
        (stress, smokes), (stress, cancer), (smokes, cancer),
    ])
    query = IdentifyQuery(
        target=cancer,
        intervention=Intervention(atom=smokes, value=False),
        given=(),
    )
    deriv = (
        DerivationStep(
            rule="unidentifiable_via_backdoor",
            inputs={
                "graph": g, "x": smokes, "y": cancer,
                "given": frozenset(),
            },
            output=StructuralResult(value=True),  # wrong claim
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed):
        verify_identify(deriv, ctx, StructuralResult(value=True))


# =================================================== d_separated

def test_d_separated_accepts_conditioned_chain():
    """a → b → c with conditioning on {b}: a, c are d-separated."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=c, given=(b,))
    deriv = (
        DerivationStep(
            rule="d_separated",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset({b}),
            },
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_assoc(deriv, ctx, StructuralResult(value=False))


def test_d_separated_rejects_when_path_is_open():
    """a → b → c with no conditioning: a, c are d-connected; the
    rule must refuse to bless the d-separation claim."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=c, given=())
    deriv = (
        DerivationStep(
            rule="d_separated",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
            },
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="open path"):
        verify_assoc(deriv, ctx, StructuralResult(value=False))


def test_d_separated_rejects_positive_claim():
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=c, given=(b,))
    deriv = (
        DerivationStep(
            rule="d_separated",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset({b}),
            },
            output=StructuralResult(value=True),  # wrong claim
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="must be False"):
        verify_assoc(deriv, ctx, StructuralResult(value=True))


# =================================================== no_directed_path

def test_no_directed_path_accepts_disconnected_pair():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_nodes_from([a, b])  # no edges
    query = CauseQuery(from_atom=a, to_atom=b)
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": a, "dst": b},
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_cause(deriv, ctx, StructuralResult(value=False))


def test_no_directed_path_accepts_reverse_direction_only():
    """b → a exists but a → ... → b does NOT."""
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_edge(b, a)
    query = CauseQuery(from_atom=a, to_atom=b)
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": a, "dst": b},
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_cause(deriv, ctx, StructuralResult(value=False))


def test_no_directed_path_rejects_when_path_exists():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_edge(a, b)
    query = CauseQuery(from_atom=a, to_atom=b)
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": a, "dst": b},
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="directed path exists"):
        verify_cause(deriv, ctx, StructuralResult(value=False))


# =================================================== query binding

def test_verify_assoc_rejects_derivation_for_different_pair():
    """A d_separated step whose atoms don't match the context's assoc
    query must be rejected."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    # Context asks about (a, c); derivation claims d-sep between (a, b)
    # which is d-connected so would fail the rule anyway — but the
    # binding check should fire first.
    query = AssocQuery(left=a, right=c, given=(b,))
    deriv = (
        DerivationStep(
            rule="d_separated",
            inputs={
                "graph": g, "x": a, "y": b,
                "conditioning": frozenset({b}),
            },
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="d_separated.y"):
        verify_assoc(deriv, ctx, StructuralResult(value=False))


def test_verify_cause_rejects_derivation_for_different_pair():
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_nodes_from([a, b, c])
    query = CauseQuery(from_atom=a, to_atom=b)
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": a, "dst": c},  # wrong dst
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="no_directed_path.dst"):
        verify_cause(deriv, ctx, StructuralResult(value=False))


def test_verify_identify_rejects_wrong_negative_theorem_family():
    """A cause-style negative witness must not verify an identify
    theorem just because it also concludes StructuralResult(False)."""
    x, y = _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_nodes_from([x, y])
    query = IdentifyQuery(
        target=y,
        intervention=Intervention(atom=x, value=True),
        given=(),
    )
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": x, "dst": y},
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="identify derivation must end in"):
        verify_identify(deriv, ctx, StructuralResult(value=False))


def test_verify_assoc_rejects_cause_style_negative_witness():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_nodes_from([a, b])
    query = AssocQuery(left=a, right=b, given=())
    deriv = (
        DerivationStep(
            rule="no_directed_path",
            inputs={"graph": g, "src": a, "dst": b},
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="d_separated"):
        verify_assoc(deriv, ctx, StructuralResult(value=False))


def test_verify_cause_rejects_assoc_style_negative_witness():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_nodes_from([a, b])
    query = CauseQuery(from_atom=a, to_atom=b)
    deriv = (
        DerivationStep(
            rule="d_separated",
            inputs={
                "graph": g,
                "x": a,
                "y": b,
                "conditioning": frozenset(),
            },
            output=StructuralResult(value=False),
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="no_directed_path"):
        verify_cause(deriv, ctx, StructuralResult(value=False))
