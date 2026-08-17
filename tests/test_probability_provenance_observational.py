"""Observational provenance on ``probabilityStatement``, found by a
CLadder dry run (Q6772).

Before this iter: ``probabilityStatement.given`` had to be a subset of
the target's structural parent set (∪ ancestors ∪ bidirected
siblings). Useful for identification (backdoor / front-door /
ID need parent-aligned CPTs) but rejects CLadder-shape collider /
exp_away questions where the empirical data is conditional on
descendants of the target.

This iter: ``probabilityStatement.provenance`` distinguishes
``"structural"`` (default, current strict validation) from
``"observational"`` (relaxed — given can contain any atoms).

Safety analysis: observational entries don't break identification
because identification formulas request structural-parent-aligned
keys. Observational keys have different shapes (e.g. P(X | descendant)
vs structural P(X)), so identification naturally won't request them
and won't use them. Observational entries fire only on direct lookups
whose key matches exactly.

Pinned invariants:
- structural provenance (default) preserves strict validation
- observational provenance lets given contain descendants
- direct lookup of an observational-supplied conditional succeeds
- backward-compat: programs without provenance keep current behavior
- mixed structural + observational coexists without conflict
- Q6772 shape (collider conditioning) solves end-to-end
"""
import pytest

from themis import run
from themis.input.syntactic_validator import validate_ast
from themis.input.semantic_validator import (
    SemanticError,
    validate_program,
)


def _q6772_program(*, provenance=None):
    """Q6772 program — talent → accepted ← effort (V-collider).

    CLadder supplies P(effort | talent, accepted) for the 4 combos —
    these are observational conditionals because accepted is a
    descendant of effort in the DAG.
    """
    def _atom(pred, val=None):
        a = {"predicate": pred,
             "args": [{"type": "const", "name": "p"}]}
        if val is not None:
            return {"atom": a, "value": val}
        return a

    stmt = lambda target_val, talent_val, accepted_val, value: {
        "kind": "probability",
        **({"provenance": provenance} if provenance is not None else {}),
        "target": _atom("effort", target_val),
        "given": [_atom("talent", talent_val),
                  _atom("accepted", accepted_val)],
        "value": value,
    }

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "talent",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "effort",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "accepted",
             "domain": [True, False]},
            {"kind": "cause",
             "from": _atom("talent"), "to": _atom("accepted")},
            {"kind": "cause",
             "from": _atom("effort"), "to": _atom("accepted")},
            stmt(True, False, False, 1.00),
            stmt(True, False, True,  0.94),
            stmt(True, True,  False, 0.98),
            stmt(True, True,  True,  0.92),
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": _atom("effort", True),
                "given": [_atom("accepted", True),
                          _atom("talent", True)],
            }},
        ],
    }


def test_default_provenance_keeps_strict_validation():
    """When provenance is unset, behavior is unchanged from before
    this iter — observational-shape statements (given contains a
    descendant) are rejected by the parent-subset check. Backward
    compat: existing programs and existing tests keep their
    semantics. The check fires in ``validate_against_graph`` (called
    from dispatch_all), so we trigger it via themis.run."""
    program = _q6772_program(provenance=None)
    with pytest.raises(SemanticError) as excinfo:
        run(program)
    msg = str(excinfo.value)
    assert "not structural parents" in msg
    assert "effort" in msg


def test_explicit_structural_provenance_keeps_strict_validation():
    """Explicit ``provenance: "structural"`` is identical to omitting
    the field. The strict parent-subset check still fires."""
    program = _q6772_program(provenance="structural")
    with pytest.raises(SemanticError) as excinfo:
        run(program)
    assert "not structural parents" in str(excinfo.value)


def test_observational_provenance_allows_descendants():
    """``provenance: "observational"`` skips the parent-subset check.
    Given can contain descendants (or any non-parent atoms). The
    program runs end-to-end without SemanticError."""
    program = _q6772_program(provenance="observational")
    # themis.run must not raise (validation passes; query succeeds)
    out = run(program)
    assert out["results"][0]["status"] == "numerically_solved"


def test_q6772_observational_query_returns_supplied_value():
    """End-to-end: with observational provenance, the kernel returns
    the supplied P(effort=true | accepted=true, talent=true) = 0.92
    directly via theta lookup. No identification, no inference —
    just the right value for the right query."""
    program = _q6772_program(provenance="observational")
    out = run(program)
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    # Pull the final numeric value from the derivation
    final_output = None
    for step in result.get("derivation", {}).get("steps", []) or []:
        if step.get("rule") == "numeric_result":
            out_field = step.get("output")
            if isinstance(out_field, dict) and "value" in out_field:
                final_output = out_field["value"]
            else:
                final_output = out_field
    assert final_output == pytest.approx(0.92, abs=1e-6)


def test_observational_does_not_pollute_backdoor_identification():
    """Safety property: observational entries with descendant
    conditioning don't fool backdoor identification. The backdoor
    formula requests structural keys (parent-aligned). Observational
    keys have different shapes — identification asks for P(Y|X,Z)
    aligned with parents, not P(X|descendant). So adding observational
    entries is safe — they sit in theta but identification doesn't
    use them.

    Program: X → Y (simple chain). Theta has an observational entry
    P(X | Y) (descendant-conditioned) plus the structural
    P(Y | X). Effect query asks P(Y | do(X=True)).
    - Without the safety property: kernel might pick up the
      observational entry → wrong identification.
    - With safety property: backdoor formula needs P(Y | X), finds
      it, ignores observational P(X | Y). Result correct.
    """
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "y",
             "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x",
                      "args": [{"type": "const", "name": "p"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "const", "name": "p"}]}},
            # Structural CPT: P(Y | X) parent-aligned
            {"kind": "probability",
             "target": {"atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": True},
             "given": [{"atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": True}],
             "value": 0.8},
            {"kind": "probability",
             "target": {"atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": True},
             "given": [{"atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": False}],
             "value": 0.2},
            # Observational: P(X | Y) — descendant conditioning.
            # Identification must NOT use this for do(X) computation.
            {"kind": "probability",
             "provenance": "observational",
             "target": {"atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": True},
             "given": [{"atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "p"}]},
                        "value": True}],
             "value": 0.9},
            # Effect query: P(Y=true | do(X=true))
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": {"predicate": "y",
                                    "args": [{"type": "const", "name": "p"}]},
                           "value": True},
                "intervention": {"atom": {"predicate": "x",
                                          "args": [{"type": "const", "name": "p"}]},
                                 "value": True},
                "given": [],
            }},
        ],
    }
    out = run(program)
    result = out["results"][0]
    # Backdoor adjustment with empty Z (X has no parents) gives
    # P(Y|do(X=T)) = P(Y|X=T) = 0.8 (structural CPT, NOT 0.9 from
    # the observational P(X|Y) entry).
    final_output = None
    for step in result.get("derivation", {}).get("steps", []) or []:
        if step.get("rule") == "numeric_result":
            out_field = step.get("output")
            if isinstance(out_field, dict) and "value" in out_field:
                final_output = out_field["value"]
            else:
                final_output = out_field
    assert final_output == pytest.approx(0.8, abs=1e-6)


def test_mixed_structural_and_observational_coexist():
    """A program with both structural and observational probability
    statements validates and runs. They don't conflict because they
    have different (target, given) key shapes."""
    def _atom(pred, val=None):
        a = {"predicate": pred,
             "args": [{"type": "const", "name": "p"}]}
        if val is not None:
            return {"atom": a, "value": val}
        return a

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "y",
             "domain": [True, False]},
            {"kind": "cause",
             "from": _atom("x"), "to": _atom("y")},
            # Structural P(Y|X) — parent-aligned
            {"kind": "probability",
             "target": _atom("y", True),
             "given": [_atom("x", True)],
             "value": 0.7},
            # Observational P(X|Y) — descendant-conditioned
            {"kind": "probability",
             "provenance": "observational",
             "target": _atom("x", True),
             "given": [_atom("y", True)],
             "value": 0.4},
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": _atom("y", True),
                "given": [_atom("x", True)],
            }},
        ],
    }
    out = run(program)
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
