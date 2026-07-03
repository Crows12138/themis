"""Phase 9 §S9.1 — Bareinboim-Pearl recoverability from selection bias.

Unit tests for the pure structural core (themis/runtime/selection_recovery.py).
Every expected verdict below is hand-traced by d-separation on the small
canonical graph in the test's docstring — no oracle library is called.

Selection is modeled as conditioning on an observed node S (the sample is
restricted to S=selected); S is a real graph node with declared parents.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.types import Atom
from themis.runtime.selection_recovery import (
    SelectionRecoveryResult,
    recover_conditional,
    recover_effect,
    _z_recoverable_from_biased,
)


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


def _graph(edges: list[tuple[str, str]], nodes: list[str] | None = None) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in nodes or []:
        g.add_node(A(n))
    for u, v in edges:
        g.add_edge(A(u), A(v))
    return g


# ============================================================ conditional


def test_conditional_recoverable_selection_on_treatment_child():
    """X→Y, X→S. S is a child of X only ⇒ Y ⊥ S | X ⇒ P(y|x) recoverable
    directly as P(y|x,S)."""
    g = _graph([("x", "y"), ("x", "s")])
    r = recover_conditional(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is True
    assert r.criterion == "conditional_independence"
    assert r.formula_repr == "P(y | x) = P(y | x, S)"
    assert r.external_data_needed == ()


def test_conditional_unrecoverable_selection_directly_on_outcome():
    """X→Y, Y→S. S is a direct child of Y ⇒ the edge Y→S can never be
    blocked ⇒ P(y|x) is NOT s-recoverable (no Z helps)."""
    g = _graph([("x", "y"), ("y", "s")])
    r = recover_conditional(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is False
    assert r.criterion is None
    assert "not s-recoverable" in r.failure_reason


def test_conditional_recoverable_with_external_data():
    """X→Y, Z→Y, Z→S. Y and S share the common cause Z, so Y ⊥̸ S | X, but
    Y ⊥ S | X,Z. Recoverable only with external unbiased (X,Z)."""
    g = _graph([("x", "y"), ("z", "y"), ("z", "s")])
    r = recover_conditional(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is True
    assert r.criterion == "external_data"
    assert r.adjustment_set == (A("z"),)
    assert r.external_data_needed == ("unbiased P(x, z)",)
    assert "P(y | x, z, S)" in r.formula_repr


def test_conditional_no_selection_is_trivially_recoverable():
    g = _graph([("x", "y")])
    r = recover_conditional(g, A("x"), A("y"), ())
    assert r.recoverable is True
    assert r.criterion is None
    assert r.formula_repr == "P(y | x)"


# ============================================================ effect (SBD)


def test_effect_recoverable_no_confounding_no_external():
    """X→Y, X→S. Selection on a treatment-child; no confounding.
    Z=∅ is selection-backdoor admissible ⇒ P(y|do(x)) = P(y|x,S), no
    external data."""
    g = _graph([("x", "y"), ("x", "s")])
    r = recover_effect(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is True
    assert r.criterion == "selection_backdoor"
    assert r.adjustment_set == ()
    assert r.z_plus == () and r.z_minus == ()
    assert r.formula_repr == "P(y | do(x)) = P(y | x, S)"
    assert r.external_data_needed == ()


def test_effect_recoverable_with_confounder_needs_external():
    """Z→X, Z→Y, X→Y, X→S, Z→S. Confounder Z also drives selection.
    SBD admissible with Z⁺={z}: (1) S⊥Y|{X,Z}, (2) Z blocks the X←Z→Y
    back-door. Since Z→S, P(z) is NOT recoverable from the biased sample
    ⇒ external unbiased P(z) required."""
    g = _graph([("z", "x"), ("z", "y"), ("x", "y"), ("x", "s"), ("z", "s")])
    r = recover_effect(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is True
    assert r.criterion == "selection_backdoor"
    assert r.z_plus == (A("z"),)
    assert r.z_minus == ()
    assert r.external_data_needed == ("unbiased P(z)",)
    assert r.formula_repr == "P(y | do(x)) = Σ_{z} P(y | x, z, S) · P(z)"


def test_effect_sbd_uses_descendant_of_x_for_selection_control():
    """Z→X, Z→Y, X→M, M→Y, M→S. The mediator M (a DESCENDANT of X) must be
    adjusted to block the S–Y path, but must stay OUT of the back-door set
    (adjusting a mediator would block the causal path). This is the核心 SBD
    generalization: Z⁻={m} controls selection, Z⁺={z} controls confounding.
    """
    g = _graph([("z", "x"), ("z", "y"), ("x", "m"), ("m", "y"), ("m", "s")])
    r = recover_effect(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is True
    assert r.criterion == "selection_backdoor"
    assert r.z_plus == (A("z"),)
    assert r.z_minus == (A("m"),)
    # Z⁻ ≠ ∅ ⇒ general Theorem-3.5 formula with inner reweighting, and X
    # must join the external sample.
    assert r.external_data_needed == ("unbiased P(x, z, m)",)
    assert r.formula_repr == (
        "P(y | do(x)) = Σ_{z} [ Σ_{m} P(y | x, z, m, S) · P(m | x, z) ] · P(z)"
    )


def test_effect_recoverable_selection_collider_via_mediator_only_zminus():
    """X→Y, X→W, Y→M, M→W. W is a selection collider of X and Y (X→W direct,
    Y→M→W), so conditioning on W opens X→W←M←Y. Recovery needs only the
    descendant M (Z⁻={m}, Z⁺=∅): no back-door to block, but M must be
    adjusted to close the selection path, then reweighted by P(m|x)."""
    g = _graph([("x", "y"), ("x", "w"), ("y", "m"), ("m", "w")])
    r = recover_effect(g, A("x"), A("y"), (A("w"),))
    assert r.recoverable is True
    assert r.criterion == "selection_backdoor"
    assert r.z_plus == ()
    assert r.z_minus == (A("m"),)
    assert r.external_data_needed == ("unbiased P(x, m)",)
    assert r.formula_repr == (
        "P(y | do(x)) = Σ_{m} P(y | x, m, S) · P(m | x)"
    )


def test_effect_not_recoverable_selection_on_outcome():
    """X→Y, Y→S. Selection driven by the outcome ⇒ no SBD-admissible set;
    the negative verdict is explicitly 'not via selection-backdoor', not a
    proof of non-recoverability."""
    g = _graph([("x", "y"), ("y", "s")])
    r = recover_effect(g, A("x"), A("y"), (A("s"),))
    assert r.recoverable is False
    assert r.criterion is None
    assert "not a proof of non-recoverability" in r.failure_reason


def test_effect_no_selection_is_inert():
    g = _graph([("x", "y")])
    r = recover_effect(g, A("x"), A("y"), ())
    assert r.recoverable is True
    assert r.criterion is None
    assert r.failure_reason == "no selection nodes declared"


# ============================================================ helper


def test_z_recoverable_from_biased_true_when_s_dsep_z():
    """X→Y, X→S, Z→Y. S←X and Z→Y meet only at the collider Y ⇒ S ⊥ Z
    marginally ⇒ P(z) recoverable from biased data (no external)."""
    g = _graph([("x", "y"), ("x", "s"), ("z", "y")])
    assert _z_recoverable_from_biased(g, (A("s"),), (A("z"),)) is True


def test_z_recoverable_from_biased_false_when_s_descends_from_z():
    """Z→X→S ⇒ S ⊥̸ Z ⇒ P(z) not recoverable from the biased sample."""
    g = _graph([("z", "x"), ("x", "s")])
    assert _z_recoverable_from_biased(g, (A("s"),), (A("z"),)) is False


def test_z_recoverable_empty_z_is_trivially_true():
    g = _graph([("x", "y")])
    assert _z_recoverable_from_biased(g, (A("s"),), ()) is True


# ============================================================ guards / shape


def test_missing_treatment_returns_unrecoverable():
    g = _graph([("x", "y")])
    r = recover_effect(g, A("nope"), A("y"), (A("s"),))
    assert r.recoverable is False
    assert "absent from graph" in r.failure_reason


def test_result_is_frozen_dataclass():
    g = _graph([("x", "y"), ("x", "s")])
    r = recover_conditional(g, A("x"), A("y"), (A("s"),))
    assert isinstance(r, SelectionRecoveryResult)
    with pytest.raises(Exception):
        r.recoverable = False  # type: ignore[misc]


def test_effect_determinism_repeated_calls_identical():
    g = _graph([("z", "x"), ("z", "y"), ("x", "y"), ("x", "s"), ("z", "s")])
    r1 = recover_effect(g, A("x"), A("y"), (A("s"),))
    r2 = recover_effect(g, A("x"), A("y"), (A("s"),))
    assert r1 == r2


# ============================================================ end-to-end
#
# Full programs through themis.run: the selection_recovery extension block
# must appear (only) when the effect query's sample is restricted on a
# selection collider, carrying the constructive recoverability verdict.

from themis import run  # noqa: E402


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {
        "kind": "cause",
        "from": {"predicate": a, "args": [{"type": "const", "name": "p"}]},
        "to": {"predicate": b, "args": [{"type": "const", "name": "p"}]},
    }


def _obs(p, value=True):
    return {
        "kind": "observation",
        "atom": {"predicate": p, "args": [{"type": "const", "name": "p"}]},
        "value": value,
    }


def _effect_query(x="x", y="y"):
    return {
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "target": {
                "atom": {"predicate": y, "args": [{"type": "const", "name": "p"}]},
                "value": True,
            },
            "intervention": {
                "atom": {"predicate": x, "args": [{"type": "const", "name": "p"}]},
                "value": True,
            },
            "given": [],
        },
    }


def _program(statements):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": statements,
    }


def _recovery_block(out):
    return (out["results"][0].get("extensions") or {}).get("selection_recovery")


def test_e2e_recoverable_selection_collider_attaches_block():
    """X→Y, X→W, Y→M, M→W, restrict on W. Selection collider recoverable
    via Z⁻={m}."""
    prog = _program([
        _var("x"), _var("y"), _var("m"), _var("w"),
        _edge("x", "y"), _edge("x", "w"), _edge("y", "m"), _edge("m", "w"),
        _obs("w"), _effect_query(),
    ])
    block = _recovery_block(run(prog))
    assert block is not None
    assert block["kind"] == "selection_recovery"
    assert block["recoverable"] is True
    assert block["criterion"] == "selection_backdoor"
    assert block["z_minus"] == ["m"]
    assert block["z_plus"] == []
    assert block["external_data_needed"] == ["unbiased P(x, m)"]


def test_e2e_canonical_hernan_not_recoverable_via_sbd():
    """X→Y, X→W, Y→W (direct collider), restrict on W. The direct Y→W edge
    can't be blocked ⇒ not recoverable via SBD — the structural confirmation
    of Hernán 2004 §5 ('no covariate adjustment closes the path'). The block
    still attaches, alongside the selection_on_collider gap."""
    prog = _program([
        _var("x"), _var("y"), _var("w"),
        _edge("x", "y"), _edge("x", "w"), _edge("y", "w"),
        _obs("w"), _effect_query(),
    ])
    out = run(prog)
    block = _recovery_block(out)
    assert block is not None
    assert block["recoverable"] is False
    assert block["criterion"] is None
    assert "not a proof of non-recoverability" in block["failure_reason"]
    # The existing detector gap still fires — companion, not replacement.
    report = out["results"][0].get("data_gap_report") or {}
    kinds = [g["kind"] for g in report.get("gaps", [])]
    assert "selection_on_collider_opens_path" in kinds


def test_e2e_no_block_when_no_selection_restriction():
    """A free collider W (X→W, Y→W) with NO ObservationStatement ⇒ no sample
    restriction ⇒ no recoverability question ⇒ no block."""
    prog = _program([
        _var("x"), _var("y"), _var("w"),
        _edge("x", "y"), _edge("x", "w"), _edge("y", "w"),
        _effect_query(),
    ])
    assert _recovery_block(run(prog)) is None


def test_e2e_no_block_when_observation_not_a_collider():
    """Restrict on W where only X is an ancestor (X→W, no Y→…→W). W is not a
    selection collider of X and Y ⇒ no block (gate matches the detector)."""
    prog = _program([
        _var("x"), _var("y"), _var("w"),
        _edge("x", "y"), _edge("x", "w"),
        _obs("w"), _effect_query(),
    ])
    assert _recovery_block(run(prog)) is None


# ============================================================ verifier
#
# verify_selection_recovery re-derives the block INDEPENDENTLY against the
# graph (a second transcription; it does not call the producer). These test
# that it accepts a truthful block and rejects every tampering.

import copy  # noqa: E402

from themis.verifier import verify_selection_recovery  # noqa: E402
from themis.verifier.errors import VerificationError  # noqa: E402
from themis.runtime.scheduler import _serialize_selection_recovery  # noqa: E402


def _block_and_graph(edges, s="s"):
    g = _graph(edges)
    rec = recover_effect(g, A("x"), A("y"), (A(s),))
    return _serialize_selection_recovery(rec, A("x"), A("y")), g


_CONFOUNDED = [("z", "x"), ("z", "y"), ("x", "y"), ("x", "s"), ("z", "s")]
_HERNAN = [("x", "y"), ("x", "s"), ("y", "s")]


def test_verifier_accepts_truthful_recoverable_block():
    block, g = _block_and_graph(_CONFOUNDED)
    assert block["recoverable"] is True
    verify_selection_recovery(block, g)  # must not raise


def test_verifier_accepts_truthful_not_recoverable_block():
    block, g = _block_and_graph(_HERNAN)
    assert block["recoverable"] is False
    verify_selection_recovery(block, g)  # must not raise


def test_verifier_rejects_false_recoverable_claim():
    """Flip a genuinely non-recoverable verdict to recoverable."""
    block, g = _block_and_graph(_HERNAN)
    block["recoverable"] = True
    block["criterion"] = "selection_backdoor"
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_false_not_recoverable_claim():
    """Hide a valid recovery by claiming non-recoverability."""
    block, g = _block_and_graph(_CONFOUNDED)
    block["recoverable"] = False
    block["criterion"] = None
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_tampered_zplus_that_breaks_backdoor():
    """Drop the confounder from Z⁺ so the back-door is left open."""
    block, g = _block_and_graph(_CONFOUNDED)
    block["z_plus"] = []
    block["adjustment_set"] = []
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_tampered_external_ledger():
    block, g = _block_and_graph(_CONFOUNDED)
    assert block["external_data_needed"] == ["unbiased P(z)"]
    block["external_data_needed"] = []
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_tampered_formula():
    block, g = _block_and_graph(_CONFOUNDED)
    block["recovery_formula"] = "P(y | do(x)) = P(y | x)"
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_partition_violation():
    """Move a non-descendant of X into Z⁻."""
    block, g = _block_and_graph(_CONFOUNDED)
    block["z_plus"] = []
    block["z_minus"] = ["z"]  # z is a non-descendant of x → invalid Z⁻
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)


def test_verifier_rejects_unknown_predicate():
    block, g = _block_and_graph(_CONFOUNDED)
    block["treatment"] = "ghost"
    with pytest.raises(VerificationError):
        verify_selection_recovery(block, g)
