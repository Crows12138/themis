"""Phase 2.latent S3/S4: ADMG-aware front-door + assoc m-separation.

S3.a widens dispatch to accept identify / effect queries on ADMG
programs via an ADMG-aware front-door check (FD2 / FD3 use
m-separation instead of plain d-separation). S4 adds verifier support
and admits assoc queries on ADMG programs through m-separation /
m-connection witnesses.

See PHASE_2_LATENT_CHARTER.md §7 S3.a for the slice threshold.
"""
from __future__ import annotations

import pytest

import themis
from themis import AdmgVerificationPending
from themis.input.semantic_validator import SemanticError


# =============================================================== helpers

def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _hidden_u_program(extra_statements=()) -> dict:
    """Classic front-door-with-hidden-U ADMG:

        X → M → Y,  X ↔ Y

    Front-door on the directed skeleton finds M as a mediator.
    FD2 / FD3 checks that use m-separation must also accept M
    because the bidirected X↔Y doesn't add back-door paths from
    X to M (X has no in-edges beyond the bidirected to Y, which
    doesn't reach M except via X→M going the wrong way), and the
    back-door from M to Y via X↔Y is blocked by {X}.
    """
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
            *extra_statements,
        ],
    }


def _identify_query(query_id: str = "q") -> dict:
    return {
        "kind": "query", "id": query_id,
        "query": {
            "kind": "identify",
            "target": _atom("y"),
            "intervention": {"atom": _atom("x"), "value": True},
            "given": [],
        },
    }


# ============================================== S3.a positive: front-door

def test_hidden_u_identify_succeeds_via_admg_front_door():
    """The classic front-door-with-hidden-U ADMG: X → M → Y with X ↔ Y.
    identify query P(Y | do(X)) must be structurally_solved with a
    front-door-shaped derivation."""
    ast = _hidden_u_program([_identify_query()])
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is True
    # The derivation reuses the existing identify_via_front_door rule
    # family (S3.a explicitly does not mint new theorem family names).
    # Concretely: the terminal step's rule is the same one A6 minted.
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_front_door" in rules


def test_hidden_u_effect_succeeds_and_reaches_front_door_formula():
    """Same ADMG, effect query. Reaches the front-door formula path and
    needs_investigation only because the CPT entries aren't filled in —
    the structural identification itself succeeds."""
    ast = _hidden_u_program([
        {
            "kind": "query", "id": "e",
            "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": [],
            },
        },
    ])
    out = themis.run(ast)
    r = out["results"][0]
    # With no theta data, numeric resolution falls short, but the
    # formula itself was built — that is the S3.a success signal.
    assert "formula" in r
    assert r["formula"] is not None


# ============================================== S3.a negative: FD2 violated

def test_fd2_violated_via_bidirected_is_correctly_rejected():
    """If a bidirected edge creates an open back-door X ↔ M, the
    directed skeleton still admits M as a mediator, but the ADMG-aware
    front-door must reject it (FD2 fails) and surface a needs_investigation.

    Graph: X → M → Y, X ↔ Y, **X ↔ M**. The extra X ↔ M is a direct
    back-door from X to M — front-door must not pick M."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("m")},
            _identify_query(),
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    # Phase 2.latent ext §S3.b.2: front-door correctly rejects M (FD2
    # violated by X↔M), and Tian's hedge witness then confirms the
    # ADMG is genuinely unidentifiable — bidirected {X,Y} ∪ {X,M}
    # transitively places X, M, Y in one c-component covering An(Y).
    # Pre-Tian this was needs_investigation; post-Tian it's the
    # definitive structurally_solved + value=False answer.
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is False
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "tian_hedge_witness" in rules


# =========================================== gate: cause / assoc / prob

def test_gate_still_rejects_cause_query_on_admg():
    ast = _hidden_u_program([
        {"kind": "query", "id": "c",
         "query": {"kind": "cause",
                   "from": _atom("x"), "to": _atom("y")}},
    ])
    with pytest.raises(SemanticError) as exc:
        themis.run(ast)
    assert "cause" in str(exc.value).lower()


def test_gate_allows_assoc_query_on_admg_with_m_witness():
    ast = _hidden_u_program([
        {"kind": "query", "id": "a",
         "query": {"kind": "assoc",
                   "left": _atom("x"), "right": _atom("y"),
                   "given": []}},
    ])
    out = themis.run(ast)
    result = out["results"][0]

    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    assert result["derivation"]["steps"][-1]["rule"] == "m_connection_witness"
    assert themis.verify(ast, result) is None


def test_gate_still_rejects_probability_query_on_admg():
    ast = _hidden_u_program([
        {"kind": "query", "id": "p",
         "query": {"kind": "probability",
                   "target": {"atom": _atom("y"), "value": True},
                   "given": []}},
    ])
    with pytest.raises(SemanticError) as exc:
        themis.run(ast)
    assert "probability" in str(exc.value).lower()


# =========================================== gate: identify / effect pass

def test_gate_allows_identify_and_effect_in_same_program():
    """Two queries (identify + effect), both supported kinds. Program
    must validate and run without SemanticError."""
    ast = _hidden_u_program([
        _identify_query("q_id"),
        {"kind": "query", "id": "q_eff",
         "query": {"kind": "effect",
                   "target": {"atom": _atom("y"), "value": True},
                   "intervention": {"atom": _atom("x"), "value": True},
                   "given": []}},
    ])
    out = themis.run(ast)
    assert len(out["results"]) == 2
    assert out["results"][0]["status"] == "structurally_solved"


# ============================================== verifier compat patch

def test_verify_accepts_hidden_u_after_s4():
    """Phase 2.latent S4 lifts the AdmgVerificationPending path —
    themis.verify on the classic hidden-U ADMG must now accept the
    S3.a front-door result (returns None). The criterion rule
    consults ctx.bidirected and the verifier independently recomputes
    m-separation to verify FD2/FD3."""
    ast = _hidden_u_program([_identify_query()])
    out = themis.run(ast)
    assert themis.verify(ast, out["results"][0]) is None


def test_admg_verification_pending_class_still_exported_for_compat():
    """AdmgVerificationPending is no longer raised by verify() (S4
    removed that code path) but the class symbol stays for any caller
    that still imports it. Acts as a documented historical exception."""
    from themis.verifier import VerificationError
    assert AdmgVerificationPending is not VerificationError
    assert issubclass(AdmgVerificationPending, ValueError)


# =================================================== regression: DAG paths

def test_directed_only_front_door_still_works_without_bidirected():
    """Charter §7 S3.a regression: programs with no bidirected edges
    must still flow through the original front-door path unchanged."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            _identify_query(),
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    # No bidirected: the pre-S3.a behavior — backdoor returns empty
    # adjustment set (X has no in-edges), so P(Y|do(X)) = P(Y|X) is
    # identifiable via backdoor-with-empty-adjustment.
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is True


def test_dag_program_verify_still_works_end_to_end():
    """Charter §7 S3.a regression: the verifier path on a DAG program
    with no bidirected edges is unchanged — themis.verify accepts."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            _identify_query(),
        ],
    }
    out = themis.run(ast)
    # verify() returns None on accept.
    assert themis.verify(ast, out["results"][0]) is None


# =================================================== instantiation round-trip

def test_bidirected_with_forall_instantiates_correctly():
    """Bidirected edge with forall over two subjects must expand to
    per-subject bidirected edges in ground statements, and the ADMG
    analysis must pick them up.

    Program: 2 subjects alice / bob; X(S) → M(S) → Y(S), X(S) ↔ Y(S).
    identify query P(Y(alice) | do(X(alice))) succeeds via front-door."""
    ast = {
        "version": "0.1",
        "domain": {
            "objects": [
                {"kind": "object", "name": "alice"},
                {"kind": "object", "name": "bob"},
            ]
        },
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["S"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "S"}]},
             "to":   {"predicate": "m", "args": [{"type": "var", "name": "S"}]}},
            {"kind": "cause", "forall": ["S"],
             "from": {"predicate": "m", "args": [{"type": "var", "name": "S"}]},
             "to":   {"predicate": "y", "args": [{"type": "var", "name": "S"}]}},
            {"kind": "bidirected", "forall": ["S"],
             "left":  {"predicate": "x", "args": [{"type": "var", "name": "S"}]},
             "right": {"predicate": "y", "args": [{"type": "var", "name": "S"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": {"predicate": "y",
                            "args": [{"type": "const", "name": "alice"}]},
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "alice"}]},
                     "value": True,
                 },
                 "given": [],
             }},
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is True
