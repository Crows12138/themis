"""Phase 6.iv S.IV.3: verifier rules for IV identification.

Tests the verifier rules `iv_criterion_check` and `identify_via_iv`:
- Accept valid IV witnesses (basic + conditional, DAG + ADMG)
- Reject tampered witnesses (wrong criterion, wrong conditioning,
  wrong graph)
- Reject malformed identify_via_iv references
- End-to-end: themis.verify succeeds on IV identify results
- Byte-code independence: verifier rules don't call structural_solver
"""
from __future__ import annotations

import pytest

import themis
from themis.types import (
    Atom,
    ConstTerm,
    DerivationStep,
    IdentifyQuery,
    Intervention,
    StepRef,
    StructuralResult,
)
from themis.verifier import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.rules import (
    _rule_iv_criterion_check,
    _rule_identify_via_iv,
)

import networkx as nx


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _ctx(graph, bidirected=frozenset()):
    """Build a VerificationContext with a minimal IdentifyQuery for tests
    that only exercise the IV criterion rule (which doesn't read the query)."""
    x = _atom("x")
    y = _atom("y")
    q = IdentifyQuery(
        target=y,
        intervention=Intervention(atom=x, value=True),
        given=(),
    )
    return VerificationContext(graph=graph, query=q, bidirected=bidirected)


# ==================================================== basic IV rule acceptance


def test_iv_criterion_accepts_valid_basic_iv():
    """Z -> X -> Y with Z ⊥ Y in G[\\bar{X}] — valid basic IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    ctx = _ctx(g)
    # Must not raise — correct witness
    _rule_iv_criterion_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "instrument": z, "conditioning": frozenset(),
        },
        claimed_output=True,
        step_index=0,
    )


def test_iv_criterion_rejects_direct_z_to_y():
    """Z -> X -> Y, Z -> Y direct. IV2 violated. Claimed True is wrong."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y), (z, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_iv_criterion_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "instrument": z, "conditioning": frozenset(),
            },
            claimed_output=True,  # wrong — should be False
            step_index=0,
        )


def test_iv_criterion_accepts_correct_rejection():
    """Same as above, but claimed False — should pass."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y), (z, y)])

    ctx = _ctx(g)
    _rule_iv_criterion_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "instrument": z, "conditioning": frozenset(),
        },
        claimed_output=False,  # correctly rejects Z as IV
        step_index=0,
    )


def test_iv_criterion_rejects_when_z_y_share_bidirected():
    """ADMG: Z ↔ Y violates IV3. Claimed True should fail."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bidir = frozenset([frozenset({z, y})])

    ctx = _ctx(g, bidir)
    with pytest.raises(VerificationError):
        _rule_iv_criterion_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "instrument": z, "conditioning": frozenset(),
            },
            claimed_output=True,
            step_index=0,
        )


def test_iv_criterion_accepts_x_y_bidirected_classic_scenario():
    """Classic IV use case: X ↔ Y latent, Z → X. Z is valid IV."""
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bidir = frozenset([frozenset({x, y})])

    ctx = _ctx(g, bidir)
    _rule_iv_criterion_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "instrument": z, "conditioning": frozenset(),
        },
        claimed_output=True,
        step_index=0,
    )


def test_iv_criterion_accepts_conditional_iv():
    """Conditional IV: W -> Z, W -> Y. Basic IV fails, but given W, Z is valid."""
    w, z, x, y = _atom("w"), _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(w, z), (w, y), (z, x), (x, y)])

    ctx = _ctx(g)
    # Basic IV should fail
    _rule_iv_criterion_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "instrument": z, "conditioning": frozenset(),
        },
        claimed_output=False,
        step_index=0,
    )
    # Conditional IV given W should succeed
    _rule_iv_criterion_check(
        ctx=ctx,
        inputs={
            "graph": g, "x": x, "y": y,
            "instrument": z, "conditioning": frozenset({w}),
        },
        claimed_output=True,
        step_index=0,
    )


# ==================================================== malformed inputs


def test_iv_criterion_rejects_z_equal_x():
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_iv_criterion_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "instrument": x,  # same as x — invalid
                "conditioning": frozenset(),
            },
            claimed_output=True,
            step_index=0,
        )


def test_iv_criterion_rejects_conditioning_contains_z():
    z, x, y = _atom("z"), _atom("x"), _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    ctx = _ctx(g)
    with pytest.raises(VerificationError):
        _rule_iv_criterion_check(
            ctx=ctx,
            inputs={
                "graph": g, "x": x, "y": y,
                "instrument": z,
                "conditioning": frozenset({z}),  # z can't condition on itself
            },
            claimed_output=True,
            step_index=0,
        )


# ==================================================== identify_via_iv rule


def test_identify_via_iv_accepts_valid_chain():
    """criterion step output True + correct StructuralResult → OK."""
    # Fake step_by_id/step_output_by_id to simulate the criterion step
    criterion_step = DerivationStep(
        rule="iv_criterion_check",
        inputs={},
        output=True,
        step_id="s1",
    )
    step_by_id = {"s1": criterion_step}
    step_output_by_id = {"s1": True}

    _rule_identify_via_iv(
        ctx=None,  # unused
        inputs={"criterion": StepRef(step_id="s1")},
        claimed_output=StructuralResult(value=True),
        step_index=1,
        step_by_id=step_by_id,
        step_output_by_id=step_output_by_id,
    )


def test_identify_via_iv_rejects_criterion_is_not_iv_check():
    """criterion ref must point to an iv_criterion_check step."""
    wrong_step = DerivationStep(
        rule="front_door_criterion",  # wrong rule
        inputs={}, output=True, step_id="s1",
    )
    step_by_id = {"s1": wrong_step}
    step_output_by_id = {"s1": True}

    with pytest.raises(VerificationError):
        _rule_identify_via_iv(
            ctx=None,
            inputs={"criterion": StepRef(step_id="s1")},
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )


def test_identify_via_iv_rejects_criterion_output_false():
    """If criterion step output is False, conclusion can't be True."""
    criterion_step = DerivationStep(
        rule="iv_criterion_check",
        inputs={}, output=False, step_id="s1",
    )
    step_by_id = {"s1": criterion_step}
    step_output_by_id = {"s1": False}

    with pytest.raises(VerificationError):
        _rule_identify_via_iv(
            ctx=None,
            inputs={"criterion": StepRef(step_id="s1")},
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )


def test_identify_via_iv_rejects_wrong_output_type():
    criterion_step = DerivationStep(
        rule="iv_criterion_check",
        inputs={}, output=True, step_id="s1",
    )
    step_by_id = {"s1": criterion_step}
    step_output_by_id = {"s1": True}

    with pytest.raises(VerificationError):
        _rule_identify_via_iv(
            ctx=None,
            inputs={"criterion": StepRef(step_id="s1")},
            claimed_output="not_a_structural_result",
            step_index=1,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )


# ==================================================== end-to-end via themis.verify


def _atom_dict(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def test_themis_verify_accepts_iv_identify_result():
    """End-to-end: run a classic IV program, then call themis.verify
    on the returned result — must pass."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("z"), "to": _atom_dict("x")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("y")},
            {"kind": "bidirected",
             "left": _atom_dict("x"), "right": _atom_dict("y")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": _atom_dict("y"),
                 "intervention": {"atom": _atom_dict("x"), "value": True},
                 "given": [],
             }},
        ],
    }
    out = themis.run(ast)
    # Result must be IV identifiable
    assert "iv_identification" in out["results"][0]["extensions"]

    # verify_identify must accept the derivation
    themis.verify(ast, out["results"][0])


# ==================================================== byte-code independence


def test_iv_verifier_rules_do_not_import_structural_solver():
    """Charter invariant: verifier rules for IV must not call into
    ``structural_solver`` — they're independent re-implementations.
    Byte-code scan (co_names) catches real calls; docstring mentions
    are OK."""
    for fn in (_rule_iv_criterion_check, _rule_identify_via_iv):
        code_names = set(fn.__code__.co_names)
        # These names would indicate a runtime-side call
        assert "structural_solver" not in code_names
        assert "iv_sets" not in code_names
        assert "IVCandidate" not in code_names
