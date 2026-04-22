"""Phase 2.latent S4: narrow ADMG verifier.

S4 adds two new verifier rule families (``m_separation_witness`` and
``m_connection_witness``) with independent m-separation reimplementation
that does not import from ``structural_solver``, and makes the existing
``backdoor_criterion`` / ``front_door_criterion`` rules ADMG-aware when
the verification context carries a non-empty bidirected edge set. The
``AdmgVerificationPending`` path through ``themis.verify`` is removed.

Charter threshold (PHASE_2_LATENT_CHARTER.md §7 S4):
- independent m-sep implementation (not importing structural_solver)
- a tampered-m-sep derivation is rejected (dual-impl cross-check
  actually catches shared-bug classes)
- themis.verify accepts S3.a / S3.b.1 ADMG results end-to-end
- DAG paths bit-identical
"""
from __future__ import annotations

import pytest

import themis
from themis.types import Atom, ConstTerm, IdentifyQuery, Intervention
from themis.verifier import VerificationContext, VerificationError
from themis.verifier.rules import (
    _verifier_is_m_connected,
    _verifier_is_admg_backdoor_connected,
)


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _a(name: str) -> Atom:
    return Atom(predicate=name, args=(ConstTerm(name="me"),))


def _hidden_u_program() -> dict:
    """X → M → Y, X ↔ Y + identify query. The S3.a canonical case."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": _atom("y"),
                 "intervention": {"atom": _atom("x"), "value": True},
                 "given": [],
             }},
        ],
    }


def _backdoor_adjustment_program() -> dict:
    """Z→X→Y, W→Y, W↔Z. S3.b.1 case — backdoor on {W, Z} under ADMG."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("z")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": _atom("y"),
                 "intervention": {"atom": _atom("x"), "value": True},
                 "given": [],
             }},
        ],
    }


# ====================================== independence of verifier m-sep

def test_verifier_m_sep_does_not_import_from_runtime():
    """Charter-level invariant: the verifier's m-sep helpers must not
    call into ``structural_solver``. We scan the function's bytecode
    for any reference to the runtime module — comments in the docstring
    that merely mention the module are allowed, but real code references
    are not."""
    import dis
    import themis.verifier.rules as rules_mod
    for fn in (_verifier_is_m_connected, _verifier_is_admg_backdoor_connected):
        # Co_names captures every global / attribute name referenced in
        # the compiled code. structural_solver showing up here would
        # mean a real runtime call — not just a string in a docstring.
        code_names = set(fn.__code__.co_names)
        assert "structural_solver" not in code_names
        assert "is_m_connected" not in code_names  # would mean runtime call
    # Additionally: the verifier's rules module must not have
    # structural_solver imported at all.
    assert not hasattr(rules_mod, "structural_solver")


def test_verifier_m_sep_agrees_with_runtime_on_simple_admg():
    """Cross-check: on a well-known ADMG, the verifier's m-sep answer
    agrees with the runtime's on every (x, y, z) triple. The fact that
    they're independent implementations makes this a meaningful sanity
    pin — a real bug in either would show up here."""
    from itertools import combinations
    from themis.runtime import structural_solver as ss
    import networkx as nx

    g = nx.DiGraph()
    nodes = [_a(n) for n in ("x", "m", "y")]
    g.add_edge(_a("x"), _a("m"))
    g.add_edge(_a("m"), _a("y"))
    bidir = frozenset({frozenset({_a("x"), _a("y")})})
    for l, r in [(a, b) for a in nodes for b in nodes if a != b]:
        for k in range(3):
            for combo in combinations([n for n in nodes if n not in (l, r)], k):
                cond = frozenset(combo)
                assert (
                    _verifier_is_m_connected(g, bidir, l, r, cond)
                    == ss.is_m_connected(g, bidir, l, r, tuple(combo))
                ), (l, r, cond)


# ====================================== end-to-end: verify accepts ADMG

def test_verify_accepts_s3a_hidden_u_result():
    ast = _hidden_u_program()
    out = themis.run(ast)
    # The derivation carries identify_via_front_door; the extended
    # rule consults ctx.bidirected and independently rechecks FD2/FD3
    # via m-separation.
    assert themis.verify(ast, out["results"][0]) is None


def test_verify_accepts_s3b1_backdoor_result():
    ast = _backdoor_adjustment_program()
    out = themis.run(ast)
    assert themis.verify(ast, out["results"][0]) is None


# ==================================== adversarial: tampered derivation

def test_verify_rejects_bidirected_stripped_from_context():
    """Simulate a 'runtime lied about bidirected' scenario: build a
    VerificationContext where bidirected is silently dropped, then try
    to verify a derivation whose structural claim (front-door FD3) only
    holds under the full ADMG. The verifier's front_door_criterion
    rule, seeing ctx.bidirected=empty, will recheck on the directed
    skeleton alone — but for this graph the directed-only recheck also
    accepts (FD3 holds on the directed skeleton trivially here). So
    the adversarial test needs a case where directed-only and ADMG-aware
    answers *disagree*. We build one below."""
    # Graph: X → M → Y, X ↔ M (bidirected from X to M, NOT X to Y).
    # ADMG front-door should reject M as mediator (FD2 fails: X ↔ M is
    # an open back-door from X to M in ADMG).
    # Directed-only check accepts M (X has no in-edges, FD2 vacuous).
    # So runtime returns needs_investigation (S3.a correctly rejects),
    # and there's no "solved" derivation to tamper with. Build one
    # manually from scratch instead.
    import networkx as nx

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("m"))
    g.add_edge(_a("m"), _a("y"))
    bidir = frozenset({frozenset({_a("x"), _a("m")})})
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )

    # Check on ADMG context: front-door FD2 fails (X ↔ M is an open
    # back-door), so the rule must reject the claim that {M} is a
    # valid mediator set.
    ctx_admg = VerificationContext(
        graph=g, query=query, theta=None, bidirected=bidir,
    )
    from themis.verifier.rules import dispatch_rule
    with pytest.raises(VerificationError):
        dispatch_rule(
            "front_door_criterion",
            ctx_admg,
            inputs={
                "graph": g, "x": _a("x"), "y": _a("y"),
                "z": frozenset({_a("m")}),
            },
            claimed_output=True,
            step_index=0,
            step_by_id={},
            step_output_by_id={},
        )


def test_verify_rejects_tampered_m_separation_witness():
    """Create an m_separation_witness step claiming X ⊥_m Y | ∅ on a
    graph where they're clearly m-connected. Verifier rule must reject."""
    import networkx as nx
    from themis.verifier.rules import dispatch_rule

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("y"))
    bidir = frozenset({frozenset({_a("x"), _a("y")})})
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )
    ctx = VerificationContext(
        graph=g, query=query, theta=None, bidirected=bidir,
    )

    # X → Y directly + X ↔ Y — clearly m-connected.
    with pytest.raises(VerificationError):
        dispatch_rule(
            "m_separation_witness",
            ctx,
            inputs={
                "graph": g,
                "bidirected": bidir,
                "x": _a("x"),
                "y": _a("y"),
                "z": frozenset(),
            },
            claimed_output=True,  # claims separated — false
            step_index=0,
            step_by_id={},
            step_output_by_id={},
        )


def test_verify_accepts_correct_m_separation_witness():
    """Positive: verifier accepts a correct m_separation_witness claim."""
    import networkx as nx
    from themis.verifier.rules import dispatch_rule

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("m"))
    g.add_edge(_a("m"), _a("y"))
    bidir = frozenset()  # empty — falls back to pure d-sep
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )
    ctx = VerificationContext(graph=g, query=query, theta=None, bidirected=bidir)

    # X → M → Y: conditioning on M m-separates X and Y.
    dispatch_rule(
        "m_separation_witness",
        ctx,
        inputs={
            "graph": g, "bidirected": bidir,
            "x": _a("x"), "y": _a("y"),
            "z": frozenset({_a("m")}),
        },
        claimed_output=True,
        step_index=0,
        step_by_id={},
        step_output_by_id={},
    )


def test_bidirected_context_mismatch_is_rejected():
    """If the inputs' bidirected doesn't match ctx.bidirected, reject —
    prevents a derivation from smuggling in a different graph."""
    import networkx as nx
    from themis.verifier.rules import dispatch_rule

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("y"))
    ctx_bidir = frozenset({frozenset({_a("x"), _a("y")})})
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )
    ctx = VerificationContext(
        graph=g, query=query, theta=None, bidirected=ctx_bidir,
    )

    with pytest.raises(VerificationError):
        dispatch_rule(
            "m_separation_witness",
            ctx,
            inputs={
                "graph": g,
                "bidirected": frozenset(),  # LIE: empty
                "x": _a("x"),
                "y": _a("y"),
                "z": frozenset(),
            },
            claimed_output=True,
            step_index=0,
            step_by_id={},
            step_output_by_id={},
        )


# ==================================== regression: DAG paths unchanged

def test_dag_program_verify_end_to_end():
    """Pure-DAG programs must continue to verify cleanly — the S4
    changes are strictly additive when ctx.bidirected is empty."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("w"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": _atom("y"),
                 "intervention": {"atom": _atom("x"), "value": True},
                 "given": [],
             }},
        ],
    }
    out = themis.run(ast)
    assert themis.verify(ast, out["results"][0]) is None


# ====================================== connection witness rule

def test_m_connection_witness_accepts_open_path():
    import networkx as nx
    from themis.verifier.rules import dispatch_rule

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("y"))
    bidir = frozenset({frozenset({_a("x"), _a("y")})})
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )
    ctx = VerificationContext(graph=g, query=query, theta=None, bidirected=bidir)

    dispatch_rule(
        "m_connection_witness",
        ctx,
        inputs={
            "graph": g, "bidirected": bidir,
            "x": _a("x"), "y": _a("y"),
            "z": frozenset(),
        },
        claimed_output=True,  # X and Y are clearly m-connected here
        step_index=0,
        step_by_id={},
        step_output_by_id={},
    )


def test_m_connection_witness_rejects_wrong_claim():
    import networkx as nx
    from themis.verifier.rules import dispatch_rule

    g = nx.DiGraph()
    g.add_edge(_a("x"), _a("m"))
    g.add_edge(_a("m"), _a("y"))
    query = IdentifyQuery(
        target=_a("y"),
        intervention=Intervention(atom=_a("x"), value=True),
        given=(),
    )
    ctx = VerificationContext(
        graph=g, query=query, theta=None, bidirected=frozenset(),
    )

    # X and Y with M in cond: m-separated, not connected.
    with pytest.raises(VerificationError):
        dispatch_rule(
            "m_connection_witness",
            ctx,
            inputs={
                "graph": g, "bidirected": frozenset(),
                "x": _a("x"), "y": _a("y"),
                "z": frozenset({_a("m")}),
            },
            claimed_output=True,  # LIE
            step_index=0,
            step_by_id={},
            step_output_by_id={},
        )
