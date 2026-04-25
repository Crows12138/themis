"""Phase 9 §T9.1.4: independent verifier audit for transport identification.

T9-1 (s_admissibility_check) and T9-2 (transport_formula) and the
final identify_via_transport rule must:
- accept correct programs
- reject claims that don't match a fresh re-derivation
- not import themis.runtime.transport (independence pin)
"""
from __future__ import annotations

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _transport_program(extra_edges=()) -> dict:
    statements = [
        {"kind": "variable", "predicate": "running", "domain": [True, False]},
        {"kind": "variable", "predicate": "belly_fat_loss", "domain": [True, False]},
        {"kind": "variable", "predicate": "age", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("age"),
         "to": _atom("belly_fat_loss")},
        {"kind": "cause",
         "from": _atom("running"),
         "to": _atom("belly_fat_loss")},
    ]
    statements.extend(extra_edges)
    statements.append({
        "kind": "selection_node",
        "id": "S_age",
        "affects": _atom("age"),
        "source_population": "rct_2022",
        "target_population": "user",
    })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("running"), "value": True},
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [],
            "target_population": "user",
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ============================================ happy path


def test_transport_run_then_verify_round_trip():
    """The simplest end-to-end: run the kernel, then verify the result.
    All three rules (s_admissibility_check, transport_formula,
    identify_via_transport) get exercised."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"

    # Round-trip: pass program + result through the independent verifier
    themis.verify(prog, result)


# ============================================ rejection: T9-1


def test_verifier_rejects_false_s_admissibility_claim():
    """Mutate the s_admissibility_check claimed output to False; the
    verifier must reject."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]

    # Find the s_admissibility_check step and flip its output
    for step in result["derivation"]["steps"]:
        if step["rule"] == "s_admissibility_check":
            step["output"] = False
            break

    from themis.verifier.errors import VerificationError
    with pytest.raises(VerificationError):
        themis.verify(prog, result)


def test_verifier_rejects_wrong_adjustment_set():
    """Replace the adjustment_set with an empty list; T9-1 should
    independently re-derive that S-admissibility fails (S_age → age → y
    is open without conditioning on age)."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]

    for step in result["derivation"]["steps"]:
        if step["rule"] == "s_admissibility_check":
            # Empty the adjustment_set in inputs but keep claimed True
            step["inputs"]["adjustment_set"] = {"kind": "atom_set", "items": []}
            break

    from themis.verifier.errors import VerificationError
    with pytest.raises(VerificationError):
        themis.verify(prog, result)


# ============================================ rejection: T9-2


def test_verifier_rejects_malformed_transport_formula():
    """If the transport_formula step output doesn't match the required
    P*(...) shape, T9-2 must reject."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]

    for step in result["derivation"]["steps"]:
        if step["rule"] == "transport_formula":
            # Strip the leading P* — clearly wrong
            step["output"] = "wrong shape no P-star here"
            break

    from themis.verifier.errors import VerificationError
    with pytest.raises(VerificationError, match=r"P\*"):
        themis.verify(prog, result)


def test_verifier_rejects_formula_missing_summation_when_z_nonempty():
    """Z is non-empty in this case (age) — formula must contain Σ_{...}.
    Strip it out and the verifier should reject."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]

    for step in result["derivation"]["steps"]:
        if step["rule"] == "transport_formula":
            # Replace formula with one that has P* and predicates but no Σ
            step["output"] = "P*(belly_fat_loss | do(running)) = P(belly_fat_loss | do(running), age)"
            break

    from themis.verifier.errors import VerificationError
    with pytest.raises(VerificationError, match=r"Σ"):
        themis.verify(prog, result)


# ============================================ rejection: identify_via_transport


def test_verifier_rejects_identify_via_transport_with_wrong_step_refs():
    """Mutate the identify_via_transport criterion ref to point at a
    non-s_admissibility_check step; the rule must reject."""
    prog = _transport_program()
    out = themis.run(prog)
    result = out["results"][0]

    for step in result["derivation"]["steps"]:
        if step["rule"] == "identify_via_transport":
            step["inputs"]["criterion"] = {"kind": "step_ref", "step_id": "s_t9_2"}  # wrong: points at formula
            break

    from themis.verifier.errors import VerificationError
    with pytest.raises(VerificationError, match=r"s_admissibility_check"):
        themis.verify(prog, result)


# ============================================ independence pin


def test_verifier_does_not_import_runtime_transport():
    """The byte-code independence rule: themis.verifier.rules must not
    import themis.runtime.transport (the module it audits).

    Line-level check that ignores comments/docstrings — only flags
    actual ``import`` / ``from ... import`` statements."""
    import themis.verifier.rules as rules_mod

    forbidden_starts = (
        "from themis.runtime.transport",
        "from ..runtime.transport",
        "import themis.runtime.transport",
    )
    with open(rules_mod.__file__, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            # Skip comments — they may legitimately mention these names
            if stripped.startswith("#"):
                continue
            for forbidden in forbidden_starts:
                if stripped.startswith(forbidden):
                    raise AssertionError(
                        f"line {lineno}: verifier rules.py contains "
                        f"forbidden import statement: {stripped!r} — "
                        "T9-1/T9-2 audit must be independent of the runtime impl"
                    )
