"""Phase 9 §S9.2 — Mohan-Pearl-Tian recoverability from missing data.

Unit tests for the pure structural core (themis/runtime/missing_data.py).
Every expected verdict is hand-traced by d-separation on the small m-graph
in the test's docstring — no oracle library is called.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.types import Atom, MissingnessIndicator, ConstTerm
from themis.runtime.missing_data import (
    MissingDataRecoveryResult,
    analyze_missing_data,
    build_m_graph,
    classify_missingness,
    is_r_node,
    recover_query,
)


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


def _graph(edges, nodes=None) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in nodes or []:
        g.add_node(A(n))
    for u, v in edges:
        g.add_edge(A(u), A(v))
    return g


def _mi(var: str, caused_by=()):
    return MissingnessIndicator(
        id=f"R_{var}", missing_var=A(var),
        caused_by=tuple(A(c) for c in caused_by),
    )


# ============================================================ build_m_graph


def test_build_m_graph_adds_r_nodes_and_edges():
    g = _graph([("x", "y")])
    m, r_of_var = build_m_graph(g, [_mi("y", caused_by=("x",))])
    r_y = r_of_var[A("y")]
    assert is_r_node(r_y)
    assert m.has_edge(A("x"), r_y)          # x → R_y
    assert not g.has_node(r_y)              # base graph not mutated
    assert set(r_of_var) == {A("y")}


def test_build_m_graph_self_masking_edge():
    g = _graph([("x", "y")])
    m, r_of_var = build_m_graph(g, [_mi("y", caused_by=("y",))])
    assert m.has_edge(A("y"), r_of_var[A("y")])  # self-masking y → R_y


# ============================================================ classify


def test_classify_mcar_isolated_indicator():
    """X→Y, R_y with no parents ⇒ R ⊥ everything ⇒ MCAR."""
    g = _graph([("x", "y")])
    m, r = build_m_graph(g, [_mi("y")])
    assert classify_missingness(m, r, list(g.nodes)) == "MCAR"


def test_classify_mar_missingness_depends_on_observed():
    """X→Y, Z→Y, Z→R_y. Missingness of Y depends only on the fully-observed
    Z ⇒ Y ⊥ R_y | {X,Z} ⇒ MAR (but not MCAR: R_y depends on substantive Z)."""
    g = _graph([("x", "y"), ("z", "y")])
    m, r = build_m_graph(g, [_mi("y", caused_by=("z",))])
    assert classify_missingness(m, r, list(g.nodes)) == "MAR"


def test_classify_mnar_self_masking():
    """R_y ← Y ⇒ missingness depends on the (missing) value of Y ⇒ MNAR."""
    g = _graph([("x", "y")])
    m, r = build_m_graph(g, [_mi("y", caused_by=("y",))])
    assert classify_missingness(m, r, list(g.nodes)) == "MNAR"


def test_classify_none_without_indicators():
    g = _graph([("x", "y")])
    m, r = build_m_graph(g, [])
    assert classify_missingness(m, r, list(g.nodes)) == "none"


# ============================================================ recover


def test_recover_mcar_conditional():
    """MCAR: P(y|x) recoverable directly from complete cases."""
    g = _graph([("x", "y")])
    r = analyze_missing_data(g, [_mi("y")], [A("y")], [A("x")])
    assert r.mechanism == "MCAR"
    assert r.recoverable is True
    assert r.formula_repr == "P(y | x) = P(y | x, R_y=0)"


def test_recover_mar_needs_the_missingness_driver():
    """X→Y, Z→Y, Z→R_y. P(y|x) is NOT recoverable via factorization on
    {x,y} alone — the driver Z of Y's missingness is out of scope, and
    complete-case P(y|x) selects on Z through Y. Bringing Z in
    (P(y|x,z)) recovers it. This is the crux: MAR ≠ 'any conditional
    is a complete-case estimate'."""
    g = _graph([("x", "y"), ("z", "y")])
    ind = [_mi("y", caused_by=("z",))]
    r_bare = analyze_missing_data(g, ind, [A("y")], [A("x")])
    assert r_bare.mechanism == "MAR"
    assert r_bare.recoverable is False

    r_full = analyze_missing_data(g, ind, [A("y")], [A("x"), A("z")])
    assert r_full.recoverable is True
    assert r_full.formula_repr == "P(y | x, z) = P(y | x, z, R_y=0)"


def test_recover_mnar_conditional_recoverable_but_marginal_not():
    """X→Y, R_x←X (self-mask X), R_y←X; both X,Y partially observed. MNAR.
    P(y|x) IS recoverable — conditioning on X blocks Y from both R's
    (X→R_x, X→R_y) — the striking MPT result that MNAR data can still
    yield a recoverable conditional. But the marginal P(x) is NOT
    recoverable: the self-masking edge X→R_x can't be blocked."""
    g = _graph([("x", "y")])
    ind = [_mi("x", caused_by=("x",)), _mi("y", caused_by=("x",))]

    cond = analyze_missing_data(g, ind, [A("y")], [A("x")])
    assert cond.mechanism == "MNAR"
    assert cond.recoverable is True
    assert "R_x=0" in cond.formula_repr and "R_y=0" in cond.formula_repr

    marg = analyze_missing_data(g, ind, [A("x")], [])
    assert marg.mechanism == "MNAR"
    assert marg.recoverable is False
    assert "自遮蔽" in marg.failure_reason


def test_recover_mnar_self_masking_outcome_unrecoverable():
    """R_y ← Y: complete-case P(y|x) selects on Y itself ⇒ not recoverable."""
    g = _graph([("x", "y")])
    r = analyze_missing_data(g, [_mi("y", caused_by=("y",))], [A("y")], [A("x")])
    assert r.mechanism == "MNAR"
    assert r.recoverable is False


def test_recover_joint_under_mcar():
    """Joint P(x,y) with only Y missing (MCAR) is recoverable."""
    g = _graph([("x", "y")])
    r = analyze_missing_data(g, [_mi("y")], [A("x"), A("y")], [])
    assert r.recoverable is True


# ============================================================ shape


def test_result_is_frozen():
    g = _graph([("x", "y")])
    r = analyze_missing_data(g, [_mi("y")], [A("y")], [A("x")])
    assert isinstance(r, MissingDataRecoveryResult)
    with pytest.raises(Exception):
        r.recoverable = False  # type: ignore[misc]


def test_determinism():
    g = _graph([("x", "y"), ("z", "y")])
    ind = [_mi("y", caused_by=("z",))]
    a = analyze_missing_data(g, ind, [A("y")], [A("x"), A("z")])
    b = analyze_missing_data(g, ind, [A("y")], [A("x"), A("z")])
    assert a == b


# ============================================================ end-to-end
#
# Full programs through themis.run: the missing_data_recovery block must
# appear when the program declares a MissingnessIndicator, analyzing the
# g-formula conditional P(Y | X, given, Z) with Z the back-door set.

from themis import run  # noqa: E402


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {
        "kind": "cause",
        "from": {"predicate": a, "args": [{"type": "const", "name": "p"}]},
        "to": {"predicate": b, "args": [{"type": "const", "name": "p"}]},
    }


def _indicator(var, caused_by=()):
    return {
        "kind": "missingness_indicator",
        "id": f"R_{var}",
        "missing_var": {"predicate": var, "args": [{"type": "const", "name": "p"}]},
        "caused_by": [
            {"predicate": c, "args": [{"type": "const", "name": "p"}]}
            for c in caused_by
        ],
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


def _md_block(out):
    return (out["results"][0].get("extensions") or {}).get("missing_data_recovery")


def test_e2e_confounder_drives_missingness_recoverable_via_backdoor():
    """X→Y, Z→X, Z→Y, Z→R_y. The confounder Z also drives Y's missingness.
    The effect needs the back-door set {z}; conditioning on z ALSO blocks
    Y from R_y ⇒ the g-formula conditional P(y|x,z) is recoverable (MAR).
    This is why the block analyzes P(Y|X,Z), not bare P(Y|X)."""
    prog = _program([
        _var("x"), _var("y"), _var("z"),
        _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
        _indicator("y", caused_by=("z",)),
        _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block is not None
    assert block["kind"] == "missing_data_recovery"
    assert block["mechanism"] == "MAR"
    assert block["recoverable"] is True
    assert block["target"] == "P(y | x, z)"
    assert block["recovery_formula"] == "P(y | x, z) = P(y | x, z, R_y=0)"


def test_e2e_self_masking_outcome_not_recoverable():
    """X→Y, R_y←Y. Self-masking on the outcome ⇒ MNAR, not recoverable."""
    prog = _program([
        _var("x"), _var("y"),
        _edge("x", "y"),
        _indicator("y", caused_by=("y",)),
        _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block is not None
    assert block["mechanism"] == "MNAR"
    assert block["recoverable"] is False


def test_e2e_mcar_recoverable():
    prog = _program([
        _var("x"), _var("y"),
        _edge("x", "y"),
        _indicator("y"),
        _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block is not None
    assert block["mechanism"] == "MCAR"
    assert block["recoverable"] is True


def test_e2e_no_block_without_indicators():
    prog = _program([
        _var("x"), _var("y"),
        _edge("x", "y"),
        _effect_query(),
    ])
    assert _md_block(run(prog)) is None


# ============================================================ verifier
#
# verify_missing_data_recovery re-derives the block INDEPENDENTLY (rebuild
# m-graph, reclassify, re-search factorization; no import of the producer).

from types import SimpleNamespace as _NS  # noqa: E402

from themis.verifier import verify_missing_data_recovery  # noqa: E402
from themis.verifier.errors import VerificationError  # noqa: E402
from themis.runtime.scheduler import (  # noqa: E402
    _serialize_missing_data_recovery,
)


def _query(x="x", y="y", given=()):
    return _NS(
        intervention=_NS(atom=A(x)),
        target=_NS(atom=A(y)),
        given=tuple(_NS(atom=A(g)) for g in given),
    )


def _block_for(g, indicators, y=("y",), x=("x",)):
    rec = analyze_missing_data(g, indicators, [A(v) for v in y], [A(v) for v in x])
    return _serialize_missing_data_recovery(rec)


def test_verifier_accepts_truthful_mcar_block():
    g = _graph([("x", "y")])
    ind = [_mi("y")]
    block = _block_for(g, ind)
    verify_missing_data_recovery(block, g, ind, _query())  # no raise


def test_verifier_accepts_truthful_mnar_unrecoverable_block():
    g = _graph([("x", "y")])
    ind = [_mi("y", caused_by=("y",))]
    block = _block_for(g, ind)
    assert block["recoverable"] is False
    verify_missing_data_recovery(block, g, ind, _query())  # no raise


def test_verifier_rejects_tampered_mechanism():
    g = _graph([("x", "y")])
    ind = [_mi("y")]
    block = _block_for(g, ind)
    block["mechanism"] = "MNAR"
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, ind, _query())


def test_verifier_rejects_false_recoverable_claim():
    """Self-masking outcome is unrecoverable; flip it to recoverable."""
    g = _graph([("x", "y")])
    ind = [_mi("y", caused_by=("y",))]
    block = _block_for(g, ind)
    block["recoverable"] = True
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, ind, _query())


def test_verifier_rejects_false_not_recoverable_claim():
    g = _graph([("x", "y")])
    ind = [_mi("y")]
    block = _block_for(g, ind)
    block["recoverable"] = False
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, ind, _query())


def test_verifier_rejects_tampered_formula():
    g = _graph([("x", "y")])
    ind = [_mi("y")]
    block = _block_for(g, ind)
    block["recovery_formula"] = "P(y | x) = P(y | x)"
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, ind, _query())


# ==================================================== full-estimand (P(Z))
#
# analyze_missing_data_estimand combines the adjusted conditional
# P(Y|X,Z) with the covariate marginal P(Z): the interventional estimand
# P(Y|do(X)) = Σ_z P(Y|X,Z)·P(Z) is a product of two manifest factors, so
# it is recoverable iff BOTH are. The crux is the self-masking confounder:
# the conditional stays recoverable while P(Z) does not.

from themis.runtime.missing_data import (  # noqa: E402
    EstimandRecoveryResult,
    analyze_missing_data_estimand,
)


def test_estimand_confounder_drives_missingness_recoverable():
    """Z→X, Z→Y, X→Y, Z→R_y. Z is fully observed; the conditional and the
    marginal P(Z) are both recoverable ⇒ the full estimand is."""
    g = _graph([("z", "x"), ("z", "y"), ("x", "y")])
    ind = [_mi("y", caused_by=("z",))]
    est = analyze_missing_data_estimand(g, ind, A("y"), A("x"), given=(), z=(A("z"),))
    assert isinstance(est, EstimandRecoveryResult)
    assert est.mechanism == "MAR"
    assert est.conditional.recoverable is True
    assert est.covariate is not None and est.covariate.recoverable is True
    assert est.recoverable is True
    assert est.failure_reason is None
    assert est.formula_repr == (
        "P(y | do(x)) = Σ_{z} P(y | x, z, R_y=0) · P(z)"
    )


def test_estimand_self_masking_confounder_conditional_ok_marginal_not():
    """Z→X, Z→Y, X→Y with a SELF-MASKING confounder Z→R_z. Conditioning on
    Z blocks the conditional's target from R_z ⇒ P(Y|X,Z) IS recoverable,
    but P(Z) is not (self-masking) ⇒ the full estimand is NOT. This is the
    whole reason to check P(Z) separately."""
    g = _graph([("z", "x"), ("z", "y"), ("x", "y")])
    ind = [_mi("z", caused_by=("z",))]
    est = analyze_missing_data_estimand(g, ind, A("y"), A("x"), given=(), z=(A("z"),))
    assert est.conditional.recoverable is True
    assert est.covariate is not None and est.covariate.recoverable is False
    assert est.recoverable is False
    assert "P(Z)" in est.failure_reason
    assert est.formula_repr == ""


def test_estimand_no_adjustment_covariate_none():
    """No back-door adjustment needed ⇒ the estimand collapses to the bare
    conditional; there is no marginal to recover."""
    g = _graph([("x", "y")])
    est = analyze_missing_data_estimand(g, [_mi("y")], A("y"), A("x"), given=(), z=())
    assert est.covariate is None
    assert est.recoverable is True
    assert est.formula_repr == "P(y | do(x)) = P(y | x, R_y=0)"


def test_estimand_result_frozen():
    g = _graph([("z", "x"), ("z", "y"), ("x", "y")])
    est = analyze_missing_data_estimand(
        g, [_mi("y", caused_by=("z",))], A("y"), A("x"), given=(), z=(A("z"),)
    )
    with pytest.raises(Exception):
        est.recoverable = False  # type: ignore[misc]


# ---- end-to-end: the run() block carries the estimand sub-blocks ----


def test_e2e_estimand_block_recoverable_via_backdoor_marginal():
    prog = _program([
        _var("x"), _var("y"), _var("z"),
        _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
        _indicator("y", caused_by=("z",)),
        _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block["adjustment_set"] == ["z"]
    assert block["covariate_recovery"] is not None
    assert block["covariate_recovery"]["recoverable"] is True
    assert block["estimand"]["recoverable"] is True
    assert block["estimand"]["target"] == "P(y | do(x))"
    assert block["estimand"]["requires"] == [
        "conditional P(Y|X,Z)", "covariate P(Z)",
    ]


def test_e2e_self_masking_confounder_estimand_not_recoverable():
    prog = _program([
        _var("x"), _var("y"), _var("z"),
        _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
        _indicator("z", caused_by=("z",)),
        _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block["recoverable"] is True                       # conditional
    assert block["covariate_recovery"]["recoverable"] is False
    assert block["estimand"]["recoverable"] is False
    assert block["estimand"]["failure_reason"] is not None


def test_e2e_mcar_estimand_covariate_null():
    prog = _program([
        _var("x"), _var("y"), _edge("x", "y"), _indicator("y"), _effect_query(),
    ])
    block = _md_block(run(prog))
    assert block["adjustment_set"] == []
    assert block["covariate_recovery"] is None
    assert block["estimand"]["recoverable"] is True


# ---- verifier independently re-derives the estimand combination ----

from themis.kernel import _to_ast, validate_ast, validate_program  # noqa: E402
from themis.runtime.instantiation import instantiate  # noqa: E402
from themis.runtime.graph_projection import project  # noqa: E402
from themis.types import QueryStatement as _QueryStatement  # noqa: E402


def _rich_block_and_ctx(prog):
    """Real run() block + reconstructed (graph, indicators, query) for the
    independent verifier — mirrors the kernel.verify wiring."""
    out = run(prog)
    p = validate_program(validate_ast(_to_ast(prog)))
    graph = project(instantiate(p))
    inds = [s for s in p.statements if isinstance(s, MissingnessIndicator)]
    qstmt = [s for s in p.statements if isinstance(s, _QueryStatement)][0]
    block = out["results"][0]["extensions"]["missing_data_recovery"]
    return block, graph, inds, qstmt.query


_CONFOUNDER_PROG = _program([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
    _indicator("y", caused_by=("z",)),
    _effect_query(),
])
_SELFMASK_PROG = _program([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
    _indicator("z", caused_by=("z",)),
    _effect_query(),
])


def test_verifier_accepts_truthful_estimand_block():
    block, g, inds, q = _rich_block_and_ctx(_CONFOUNDER_PROG)
    verify_missing_data_recovery(block, g, inds, q)  # no raise


def test_verifier_accepts_truthful_unrecoverable_estimand_block():
    block, g, inds, q = _rich_block_and_ctx(_SELFMASK_PROG)
    assert block["estimand"]["recoverable"] is False
    verify_missing_data_recovery(block, g, inds, q)  # no raise


def test_verifier_rejects_false_estimand_recoverable_claim():
    block, g, inds, q = _rich_block_and_ctx(_SELFMASK_PROG)
    block["estimand"]["recoverable"] = True
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, inds, q)


def test_verifier_rejects_tampered_covariate_recoverable():
    block, g, inds, q = _rich_block_and_ctx(_CONFOUNDER_PROG)
    block["covariate_recovery"]["recoverable"] = False
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, inds, q)


def test_verifier_rejects_tampered_estimand_formula():
    block, g, inds, q = _rich_block_and_ctx(_CONFOUNDER_PROG)
    block["estimand"]["recovery_formula"] = "P(y | do(x)) = 42"
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(block, g, inds, q)
