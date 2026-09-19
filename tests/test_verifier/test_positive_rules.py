"""V4 unit tests: positive structural witness rules.

- cause_via_directed_path — claims StructuralResult(True) for cause
- d_connected_via_open_path — claims StructuralResult(True) for assoc

Each rule is exercised on hand-built graphs. No scheduler / fixture
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
    StructuralResult,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_assoc,
    verify_cause,
)
from themis.verifier.errors import RuleCheckFailed


def _atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _label(a: Atom) -> str:
    args = ",".join(t.name for t in a.args)
    return f"{a.predicate}({args})"


# =================================================== cause_via_directed_path

def test_cause_via_directed_path_accepts_one_witness():
    """a → b → c: witness path (a, b, c) proves cause."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = CauseQuery(from_atom=a, to_atom=c)
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": ((a, b, c),)},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_accepts_multiple_witnesses():
    """Two disjoint directed paths from a to c — rule validates both."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    d = _atom("d")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c), (a, d), (d, c)])
    query = CauseQuery(from_atom=a, to_atom=c)
    paths = ((a, b, c), (a, d, c))
    supporting = tuple(tuple(_label(x) for x in p) for p in paths)
    result = StructuralResult(value=True, supporting_paths=supporting)
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": paths},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_underreported_directed_path_set():
    """Positive cause proofs must justify the exact supporting path set,
    not merely one witness when two directed paths exist."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    d = _atom("d")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c), (a, d), (d, c)])
    query = CauseQuery(from_atom=a, to_atom=c)
    partial = ((a, b, c),)
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": partial},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="full directed-path set"):
        verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_missing_edge():
    """Witness path claims (a, b, c) but edge (b, c) isn't in graph."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b)])  # no (b, c)
    # c is a VARIABLE of this problem that happens to have no edge into it.
    # Leaving it out of the graph entirely would make this a different
    # question — "there is no c" rather than "the path claims an edge that
    # is not there" — and dispatch_rule now says so first, correctly.
    g.add_node(c)
    query = CauseQuery(from_atom=a, to_atom=c)
    # Output claims a valid StructuralResult, but the path is a lie.
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": ((a, b, c),)},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="missing a directed edge"):
        verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_reversed_edge():
    """Edge goes b → a, not a → b. The witness path (a, b) is invalid
    because (a, b) isn't a directed edge."""
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_edges_from([(b, a)])  # reversed
    query = CauseQuery(from_atom=a, to_atom=b)
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": b, "paths": ((a, b),)},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="missing a directed edge"):
        verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_path_not_starting_at_src():
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = CauseQuery(from_atom=a, to_atom=c)
    # Path starts at b, not a.
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": ((b, c),)},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="start at src"):
        verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_empty_paths():
    a, b = _atom("a"), _atom("b")
    g = nx.DiGraph()
    g.add_edge(a, b)
    query = CauseQuery(from_atom=a, to_atom=b)
    result = StructuralResult(value=True, supporting_paths=())
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": b, "paths": ()},
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="at least one witness"):
        verify_cause(deriv, ctx, result)


def test_cause_via_directed_path_rejects_supporting_paths_mismatch():
    """Witness path in inputs doesn't match the string-rendered
    supporting_paths in the claimed output."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = CauseQuery(from_atom=a, to_atom=c)
    # claim lists wrong path strings
    wrong_result = StructuralResult(
        value=True,
        supporting_paths=(("wrong", "path", "names"),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": ((a, b, c),)},
            output=wrong_result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="supporting_paths do not match"):
        verify_cause(deriv, ctx, wrong_result)


def test_verify_cause_rejects_witness_for_wrong_query():
    """Derivation's src/dst must match the context's cause query."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    # Context asks cause(a → b); derivation proves cause(a → c).
    query = CauseQuery(from_atom=a, to_atom=b)
    result_for_a_to_c = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="cause_via_directed_path",
            inputs={"graph": g, "src": a, "dst": c, "paths": ((a, b, c),)},
            output=result_for_a_to_c,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="cause_via_directed_path.dst"):
        verify_cause(deriv, ctx, result_for_a_to_c)


# =================================================== d_connected_via_open_path

def test_d_connected_accepts_chain_open_without_conditioning():
    """a → b → c; no conditioning ⇒ chain is open."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=c, given=())
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
                "paths": ((a, b, c),),
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_assoc(deriv, ctx, result)


def test_d_connected_rejects_blocked_chain_witness():
    """a → b → c with conditioning on {b}: the chain path (a, b, c) is
    blocked, so the witness is invalid."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=c, given=(b,))
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset({b}),
                "paths": ((a, b, c),),
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="blocked under conditioning"):
        verify_assoc(deriv, ctx, result)


def test_d_connected_accepts_collider_path_opened_by_conditioning():
    """a → b ← c; conditioning on collider {b} opens the path."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (c, b)])
    query = AssocQuery(left=a, right=c, given=(b,))
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset({b}),
                "paths": ((a, b, c),),
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    verify_assoc(deriv, ctx, result)


def test_d_connected_rejects_collider_path_not_opened():
    """a → b ← c with no conditioning on b (a collider): path is
    closed."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (c, b)])
    query = AssocQuery(left=a, right=c, given=())
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
                "paths": ((a, b, c),),
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="blocked under conditioning"):
        verify_assoc(deriv, ctx, result)


def test_d_connected_rejects_missing_edge_in_undirected_path():
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b)])  # no edge between b and c
    g.add_node(c)               # but c IS a variable here — see above
    query = AssocQuery(left=a, right=c, given=())
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
                "paths": ((a, b, c),),
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="missing an edge"):
        verify_assoc(deriv, ctx, result)


def test_verify_assoc_rejects_positive_witness_for_wrong_pair():
    """Witness is for (a, c); context asks about (a, b)."""
    a, b, c = _atom("a"), _atom("b"), _atom("c")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c)])
    query = AssocQuery(left=a, right=b, given=())
    result_for_ac = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
                "paths": ((a, b, c),),
            },
            output=result_for_ac,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(VerificationError, match="d_connected_via_open_path.y"):
        verify_assoc(deriv, ctx, result_for_ac)


def test_d_connected_rejects_underreported_open_path_set():
    """V4 positive assoc proofs must justify the exact supporting path
    set, not merely one witness. If two open paths exist, listing only
    one is an under-report and must be rejected."""
    a, b, c, d = _atom("a"), _atom("b"), _atom("c"), _atom("d")
    g = nx.DiGraph()
    g.add_edges_from([(a, b), (b, c), (a, d), (d, c)])
    query = AssocQuery(left=a, right=c, given=())
    partial = ((a, b, c),)
    result = StructuralResult(
        value=True,
        supporting_paths=((_label(a), _label(b), _label(c)),),
    )
    deriv = (
        DerivationStep(
            rule="d_connected_via_open_path",
            inputs={
                "graph": g, "x": a, "y": c,
                "conditioning": frozenset(),
                "paths": partial,
            },
            output=result,
            label="s1",
        ),
    )
    ctx = VerificationContext(graph=g, query=query)
    with pytest.raises(RuleCheckFailed, match="full open-path set"):
        verify_assoc(deriv, ctx, result)
