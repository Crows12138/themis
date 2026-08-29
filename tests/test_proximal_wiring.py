"""Pipeline wiring for the proximal_effect query kind.

``proximal_identify.identify_proximal`` / ``estimation.proximal.
estimate_proximal_ate`` were pure functions unreachable from the kernel's
public surface. This slice threads a new ``proximal_effect`` query kind through
the whole stack — schema, semantic validation, graph projection, scheduler
dispatch, kernel round-trip, explanation, estimation dispatch, and the
independent verifier — so a client can hand the kernel a proximal query as JSON
and get back an identifiability verdict (Miao model (f)) and, with data, an ATE
recovered under an unobserved confounder that a second, independent pass
re-checks.

The verifier mirror ``proximal_criterion`` RE-RUNS identify_proximal on the
context graph (never trusting the result), so a result claiming
identifiability is rejected when verified against a graph that actually breaks
the proxy structure — ``test_verify_criterion_reruns_identification_from_graph``
proves it has teeth.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.kernel import _program_to_ast_dict
from themis.types import (
    DiscreteChannel,
    ProximalEffectQuery,
    QueryStatement,
)
from themis.verifier import VerificationError


# ------------------------------------------------------------------ builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _prox_query(k=2):
    return {"kind": "proximal_effect",
            "treatment": _atom("x"), "outcome": _atom("y"),
            "latent": _atom("u"), "treatment_proxy": [_atom("z")],
            "outcome_proxy": [_atom("w")],
        "channel": {"kind": "discrete_channel",
                    "latent_cardinality": k}}


def _ast(extra=(), query=None):
    # Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y. U is declared but unobserved.
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x"), _var("y"), _var("u"), _var("z"), _var("w"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"), *extra,
            {"kind": "query", "id": "q", "query": query or _prox_query()},
        ],
    }


def _sample_scm(n: int, seed: int) -> pd.DataFrame:
    """Latent-U SCM (Miao model f), linear outcome so the true ATE = 0.35."""
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    z = rng.random(n) < np.where(u, 0.80, 0.20)
    w = rng.random(n) < np.where(u, 0.85, 0.25)
    x = rng.random(n) < np.where(u, np.where(z, 0.80, 0.55), np.where(z, 0.50, 0.20))
    y = rng.random(n) < (0.15 + 0.35 * x + 0.25 * u + 0.15 * w)
    return pd.DataFrame({"x": x, "y": y, "z": z, "w": w})


def _result(r):
    return r["results"][0] if "results" in r else r["queries"][0]


# ------------------------------------------------------------------ schema
def test_schema_accepts_proximal_query():
    assert isinstance(validate_ast(_ast()), dict)


def test_schema_rejects_missing_role():
    ast = _ast()
    del ast["statements"][-1]["query"]["latent"]
    with pytest.raises(SyntacticError):
        validate_ast(ast)


def test_schema_rejects_cardinality_below_two():
    with pytest.raises(SyntacticError):
        validate_ast(_ast(query=_prox_query(k=1)))


# ------------------------------------------------------------------ parse
def test_validate_program_parses_typed_query():
    prog = validate_program(validate_ast(_ast()), checks=frozenset())
    stmt = next(s for s in prog.statements if isinstance(s, QueryStatement))
    assert isinstance(stmt.query, ProximalEffectQuery)
    q = stmt.query
    assert q.treatment.predicate == "x" and q.outcome.predicate == "y"
    assert q.latent.predicate == "u"
    assert [a.predicate for a in q.treatment_proxy] == ["z"]
    assert [a.predicate for a in q.outcome_proxy] == ["w"]
    assert q.channel.latent_cardinality == 2


def test_kernel_roundtrip_preserves_query():
    prog = validate_program(validate_ast(_ast()), checks=frozenset())
    ast2 = _program_to_ast_dict(prog)
    q = next(s["query"] for s in ast2["statements"] if s.get("kind") == "query")
    assert q["kind"] == "proximal_effect"
    assert q["latent"]["predicate"] == "u"
    assert q["channel"]["latent_cardinality"] == 2


# ------------------------------------------------------------------ run
def test_run_identifiable_structurally_solved():
    res = _result(themis.run(_ast()))
    assert res["status"] == "structurally_solved"
    assert res["query_kind"] == "proximal_effect"
    assert res["extensions"]["proximal_estimand"]["method"] == "proximal_matrix"


def test_run_broken_proxy_needs_investigation():
    # Z→Y breaks Z ⊥ Y | (U,X): not proximal-identifiable.
    res = _result(themis.run(_ast(extra=(_cause("z", "y"),))))
    assert res["status"] == "needs_investigation"
    names = [m["name"] for m in res.get("missing_information", [])]
    assert "query:proximal_not_identifiable" in names


# ------------------------------------------------------------------ estimate
def test_estimate_attaches_numeric():
    df = _sample_scm(80_000, seed=1)
    res = _result(themis.estimate(_ast(), df))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert ne["method"] == "proximal_matrix"
    assert abs(ne["point"] - 0.35) < 0.03           # recovered under latent U
    assert ne["treatment_proxy"] == ["z"] and ne["outcome_proxy"] == ["w"]
    assert ne["ci_lower"] <= ne["point"] <= ne["ci_upper"]


def test_estimate_broken_proxy_stays_structural():
    # not identifiable → no numeric overlay, structural verdict preserved.
    df = _sample_scm(20_000, seed=2)
    res = _result(themis.estimate(_ast(extra=(_cause("z", "y"),)), df))
    assert res["status"] == "needs_investigation"
    assert "numeric_estimate" not in res


# ------------------------------------------------------------------ verify
def test_verify_accepts_structural():
    prog = _ast()
    themis.verify(prog, _result(themis.run(prog)))


def test_verify_accepts_numeric():
    prog = _ast()
    df = _sample_scm(60_000, seed=3)
    themis.verify(prog, _result(themis.estimate(prog, df)))


def test_verify_rejects_tampered_data_hash():
    prog = _ast()
    df = _sample_scm(40_000, seed=4)
    res = _result(themis.estimate(prog, df))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_proximal_estimate":
            st["inputs"]["data_hash"] = "deadbeef"       # not a 64-hex hash
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_criterion_flag():
    # Flip the proximal_criterion step's output True→False: the criterion rule
    # re-runs identify_proximal (which says identifiable=True) and rejects the
    # False claim.
    prog = _ast()
    df = _sample_scm(40_000, seed=5)
    res = _result(themis.estimate(prog, df))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "proximal_criterion":
            st["output"] = {"kind": "bool", "value": False} \
                if isinstance(st["output"], dict) else False
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_criterion_reruns_identification_from_graph():
    # A result claiming proximal-identifiable, verified against a program whose
    # graph actually breaks the proxy structure (Z→Y). proximal_criterion
    # re-runs identify_proximal on ctx.graph and must reject — it does not trust
    # the result's descriptor. This is the safety property of the mirror.
    res = _result(themis.run(_ast()))
    broken = _ast(extra=(_cause("z", "y"),))
    with pytest.raises(VerificationError):
        themis.verify(broken, res)


# ------------------------------------------------------------------ explain
def test_explain_identifiable_and_refused():
    from themis import language
    from themis.output.explainer import _explain_proximal_effect
    from themis.types import (
        Atom, QueryKind, QueryResult, ResultStatus, StructuralResult,
    )

    def A(p):
        return Atom(predicate=p, args=())

    q = ProximalEffectQuery(A("x"), A("y"), A("u"), (A("z"),), (A("w"),),
                            DiscreteChannel(latent_cardinality=2))
    stmt = QueryStatement(id="q", query=q)

    solved = QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.PROXIMAL_EFFECT, query_id="q",
        structural_result=StructuralResult(value=True),
    )
    text = _explain_proximal_effect(solved, stmt,
                                    lang=language.DEFAULT)
    assert "近端可识别" in text and "proxy" in text and "u" in text

    refused = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.PROXIMAL_EFFECT, query_id="q",
    )
    assert "不可识别" in _explain_proximal_effect(
        refused, stmt, lang=language.DEFAULT)
