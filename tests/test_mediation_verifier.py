"""Phase 6.mediation S.M.3: verifier rules for mediation identification.

Tests:
- Accept valid NDE/NIE and CDE witnesses (empty W + non-empty W)
- Reject tampered witnesses (wrong output, illegal conditioning)
- Accept ADMG (bidirected) cases
- End-to-end: themis.verify succeeds on mediation effect results
- Byte-code independence: verifier rules don't call structural_solver
"""
from __future__ import annotations

import pytest

import themis
from themis.types import (
    Atom,
    ConstTerm,
    EffectQuery,
    Intervention,
    ValuedAtom,
    StepRef,
    StructuralResult,
)
from themis.verifier import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.rules import (
    _rule_mediation_nde_nie_check,
    _rule_mediation_cde_check,
    _rule_identify_via_mediation,
)

import networkx as nx


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _ctx(graph, bidirected=frozenset()):
    """Minimal VerificationContext using a trivial EffectQuery; rules
    we test here don't read the query shape beyond binding atoms."""
    x = _atom("x")
    y = _atom("y")
    q = EffectQuery(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=x, value=True),
        given=(),
        mediator=_atom("m"),
    )
    return VerificationContext(graph=graph, query=q, bidirected=bidirected)


# ======================================= mediation_nde_nie_check acceptance


def test_nde_nie_accepts_bare_mediator_empty_adjustment():
    """X → M → Y. All four conditions hold with W=∅."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])

    ctx = _ctx(g)
    _rule_mediation_nde_nie_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "mediator": m, "adjustment": frozenset(),
        },
        claimed_output=True,
        step_index=0,
    )


def test_nde_nie_accepts_when_adjustment_blocks_m_y_confounder():
    """U → M, U → Y, X → M → Y. W = {U} makes all four conditions hold."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, m), (u, y), (x, m), (m, y)])

    ctx = _ctx(g)
    _rule_mediation_nde_nie_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "mediator": m, "adjustment": frozenset({u}),
        },
        claimed_output=True,
        step_index=0,
    )


def test_nde_nie_rejects_wrong_output_claim():
    """W=∅ doesn't satisfy M3 (U is an open M-Y backdoor). Claiming True
    is wrong."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, m), (u, y), (x, m), (m, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_mediation_nde_nie_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "mediator": m, "adjustment": frozenset(),
            },
            claimed_output=True,  # Wrong — should be False
            step_index=0,
        )


def test_nde_nie_rejects_x_descendant_adjustment():
    """X → W → M, X → W → Y. W is X-descendant; M4 forbids. Claiming True
    with W={W} must be rejected."""
    x, w_node, m, y = _atom("x"), _atom("w"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, w_node), (w_node, m), (w_node, y), (x, m), (m, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_mediation_nde_nie_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "mediator": m, "adjustment": frozenset({w_node}),
            },
            claimed_output=True,  # Wrong: M4 violated
            step_index=0,
        )


def test_nde_nie_rejects_conditioning_on_treatment():
    """Illegal to put X, Y, or M in adjustment set."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_mediation_nde_nie_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "mediator": m, "adjustment": frozenset({x}),  # illegal
            },
            claimed_output=True,
            step_index=0,
        )


# ======================================= mediation_cde_check acceptance


def test_cde_accepts_bare_mediator_empty_adjustment():
    """X → M → Y. CDE identifiable with W=∅."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])

    ctx = _ctx(g)
    _rule_mediation_cde_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "mediator": m, "adjustment": frozenset(),
        },
        claimed_output=True,
        step_index=0,
    )


def test_cde_rejects_wrong_output_on_m_y_confounder():
    """U → M, U → Y, X → M → Y. With W=∅, Y-M backdoor via U remains
    open → C1 fails. Claiming True is wrong."""
    u, x, m, y = _atom("u"), _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(u, m), (u, y), (x, m), (m, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_mediation_cde_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "mediator": m, "adjustment": frozenset(),
            },
            claimed_output=True,
            step_index=0,
        )


# ======================================= ADMG cases


def test_nde_nie_rejects_with_bidirected_xy():
    """X ↔ Y latent confounder. M1 fails even with W=∅."""
    x, m, y = _atom("x"), _atom("m"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bidir = frozenset([frozenset({x, y})])

    ctx = _ctx(g, bidirected=bidir)
    # W=∅ claims False — accepted.
    _rule_mediation_nde_nie_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "mediator": m, "adjustment": frozenset(),
        },
        claimed_output=False,
        step_index=0,
    )
    # Claimed True must be rejected.
    with pytest.raises(VerificationError):
        _rule_mediation_nde_nie_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "mediator": m, "adjustment": frozenset(),
            },
            claimed_output=True,
            step_index=0,
        )


# ======================================= identify_via_mediation


def test_identify_via_mediation_accepts_any_branch_true():
    """When either nde_nie or cde check returned True, aggregator
    StructuralResult(value=True) must be accepted."""
    from themis.types import DerivationStep

    nde_step = DerivationStep(
        rule="mediation_nde_nie_check",
        inputs={}, output=True, label="s1",
    )
    cde_step = DerivationStep(
        rule="mediation_cde_check",
        inputs={}, output=False, label="s2",
    )
    step_by_id = {"s1": nde_step, "s2": cde_step}
    step_output_by_id = {"s1": True, "s2": False}

    ctx = _ctx(nx.DiGraph())
    _rule_identify_via_mediation(
        ctx=ctx,
        inputs={
            "nde_nie": StepRef(label="s1"),
            "cde": StepRef(label="s2"),
        },
        claimed_output=StructuralResult(value=True),
        step_index=2,
        step_by_id=step_by_id,
        step_output_by_id=step_output_by_id,
    )


def test_identify_via_mediation_rejects_mismatched_aggregation():
    """Both checks False must aggregate to value=False; claiming True
    is wrong."""
    from themis.types import DerivationStep

    nde_step = DerivationStep(
        rule="mediation_nde_nie_check",
        inputs={}, output=False, label="s1",
    )
    cde_step = DerivationStep(
        rule="mediation_cde_check",
        inputs={}, output=False, label="s2",
    )
    step_by_id = {"s1": nde_step, "s2": cde_step}
    step_output_by_id = {"s1": False, "s2": False}

    ctx = _ctx(nx.DiGraph())
    with pytest.raises(VerificationError):
        _rule_identify_via_mediation(
            ctx=ctx,
            inputs={
                "nde_nie": StepRef(label="s1"),
                "cde": StepRef(label="s2"),
            },
            claimed_output=StructuralResult(value=True),  # Wrong
            step_index=2,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )


def test_identify_via_mediation_rejects_wrong_step_rules():
    """If the referenced steps aren't the right rules, reject."""
    from themis.types import DerivationStep

    bad_step = DerivationStep(
        rule="graph_is_dag",  # wrong
        inputs={}, output=True, label="s1",
    )
    ok_step = DerivationStep(
        rule="mediation_cde_check",
        inputs={}, output=True, label="s2",
    )
    step_by_id = {"s1": bad_step, "s2": ok_step}
    step_output_by_id = {"s1": True, "s2": True}

    ctx = _ctx(nx.DiGraph())
    with pytest.raises(VerificationError):
        _rule_identify_via_mediation(
            ctx=ctx,
            inputs={
                "nde_nie": StepRef(label="s1"),
                "cde": StepRef(label="s2"),
            },
            claimed_output=StructuralResult(value=True),
            step_index=2,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )


# ================================= end-to-end themis.verify on mediation


def _e2e_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x", "args": [{"type": "const", "name": "me"}]},
             "to": {"predicate": "m", "args": [{"type": "const", "name": "me"}]}},
            {"kind": "cause",
             "from": {"predicate": "m", "args": [{"type": "const", "name": "me"}]},
             "to": {"predicate": "y", "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {
                    "atom": {"predicate": "x", "args": [{"type": "const", "name": "me"}]},
                    "value": True,
                },
                "target": {
                    "atom": {"predicate": "y", "args": [{"type": "const", "name": "me"}]},
                    "value": True,
                },
                "given": [],
                "mediator": {"predicate": "m", "args": [{"type": "const", "name": "me"}]},
            }},
        ],
    }


def test_themis_verify_accepts_mediation_result():
    """Full round-trip: run → verify on a mediation query."""
    ast = _e2e_program()
    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    # Must not raise
    themis.verify(ast, result)


# ===================================== byte-code independence pin


def test_verifier_rules_do_not_reference_structural_solver():
    """V-verifier invariant: the mediation verifier rules must not call
    into themis.runtime.structural_solver. Byte-code scan via co_names
    catches accidental re-use."""
    forbidden = {
        "structural_solver",
        "mediation_sets",
        "MediationResult",
        "MediationAttempt",
    }
    for fn in (
        _rule_mediation_nde_nie_check,
        _rule_mediation_cde_check,
        _rule_identify_via_mediation,
    ):
        names = set(fn.__code__.co_names)
        assert not (names & forbidden), (
            f"{fn.__name__} references forbidden symbol: "
            f"{names & forbidden}"
        )
