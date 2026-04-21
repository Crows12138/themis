"""Slice #36: strict framing gate.

When ``program.options.strict_framing == true``, effect / probability
queries whose referenced predicates still have A0 framing gaps flip
to ``needs_investigation`` before numeric evaluation — even if Theta
has every conditional they need. The F1 DEFINE_VARIABLE channel
still fires so the fill-back loop is unchanged; only the numeric
path is gated.

These tests pin the full matrix:

- Default (option off / absent): behavior unchanged, numeric flows
- Strict on + fully framed predicates: numeric flows
- Strict on + declared-but-partial predicate: numeric blocked
- Strict on + completely undeclared predicate: numeric still flows
  (opt-in per predicate — framing is silent for undeclared)
- The gate injects a MissingKind.FRAMING item naming each gap but
  does NOT produce a duplicate DEFINE_VARIABLE request — framing is
  already in its own channel
- apply_patch_and_run with a filled framing bundle can clear the gate
"""
from __future__ import annotations

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _base_effect_program(
    strict_framing: bool,
    declare_running: bool = True,
    fully_frame_running: bool = False,
    declare_belly: bool = True,
    fully_frame_belly: bool = False,
    with_theta: bool = True,
) -> dict:
    """Build a running → belly_fat_loss effect query program with
    knobs for which predicates get declared vs fully framed, and
    whether options.strict_framing is on."""
    statements: list[dict] = []

    def framing_kwargs(full: bool) -> dict:
        if not full:
            return {}
        return {
            "time_window": "12w",
            "measurement": "self-report",
            "threshold": ">=3 sessions/week",
            "observability": "self-report",
            "direction": "up",
            "baseline": "prior week",
            "state_vs_event": "state",
        }

    if declare_running:
        statements.append({
            "kind": "variable", "predicate": "running",
            "domain": [True, False],
            **framing_kwargs(fully_frame_running),
        })
    if declare_belly:
        belly_framing = framing_kwargs(fully_frame_belly)
        # belly_fat_loss is a "down" direction outcome
        if belly_framing:
            belly_framing["direction"] = "down"
            belly_framing["measurement"] = "waist cm"
            belly_framing["threshold"] = ">=3 cm"
        statements.append({
            "kind": "variable", "predicate": "belly_fat_loss",
            "domain": [True, False],
            **belly_framing,
        })

    statements.append({
        "kind": "cause",
        "from": _atom("running"), "to": _atom("belly_fat_loss"),
        "annotations": {"source": "llm_proposal"},
    })

    if with_theta:
        # P(belly_fat_loss=True | running=True) = 0.5 — backdoor set is
        # empty (no confounders), so this is directly the conditional
        # the backdoor formula needs.
        statements.append({
            "kind": "probability",
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [{"atom": _atom("running"), "value": True}],
            "value": 0.5,
        })

    statements.append({
        "kind": "query", "id": "q",
        "query": {"kind": "effect",
                  "target": {"atom": _atom("belly_fat_loss"), "value": True},
                  "intervention": {"atom": _atom("running"), "value": True},
                  "given": []},
    })

    program: dict = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }
    if strict_framing:
        program["options"] = {"strict_framing": True}
    return program


# ============================================= default behavior preserved

def test_default_no_options_behaves_as_before_strict():
    """A program with no options field behaves exactly as it did
    pre-#36: framing is advisory, numeric flows."""
    out = themis.run(_base_effect_program(strict_framing=False))
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    # framing_notes and DEFINE_VARIABLE still fire advisorily.
    assert r.get("framing_notes", [])


def test_explicit_strict_false_same_as_default():
    """options.strict_framing: false is a sibling of absent — numeric
    still flows even when predicates are underframed."""
    program = _base_effect_program(strict_framing=False)
    program["options"] = {"strict_framing": False}
    out = themis.run(program)
    assert out["results"][0]["status"] == "numerically_solved"


# ============================================= gate fires when declared-partial

def test_strict_on_with_underframed_predicate_flips_to_needs_investigation():
    out = themis.run(_base_effect_program(strict_framing=True))
    r = out["results"][0]
    assert r["status"] == "needs_investigation"
    # numeric_result was not computed
    assert "numeric_result" not in r


def test_strict_on_populates_framing_kind_missing_items():
    out = themis.run(_base_effect_program(strict_framing=True))
    r = out["results"][0]
    framing_items = [
        m for m in r.get("missing_information", [])
        if m["kind"] == "framing"
    ]
    # Both running and belly_fat_loss are declared-but-partial.
    assert len(framing_items) == 2
    names = sorted(m["name"] for m in framing_items)
    assert names == ["framing:belly_fat_loss", "framing:running"]
    # Reasons carry the unfilled field list
    for m in framing_items:
        assert "strict_framing" in m["reason"]
        assert "time_window" in m["reason"]


def test_strict_on_still_surfaces_define_variable_request_no_duplicates():
    """The F1 channel must run as usual; the strict gate must NOT
    cause a duplicate DEFINE_VARIABLE request from the FRAMING
    MissingItems."""
    out = themis.run(_base_effect_program(strict_framing=True))
    r = out["results"][0]
    define_reqs = [
        req for req in r.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    # Exactly one DEFINE_VARIABLE request (from _attach_framing),
    # not a second one pushed by investigation_pusher.
    assert len(define_reqs) == 1
    # Its items still carry real variable_patch skeletons.
    for item in define_reqs[0]["items"]:
        assert item["skeleton"]["kind"] == "variable_patch"
        assert "fields" in item["skeleton"]


# ============================================= gate skips when fully framed

def test_strict_on_with_fully_framed_predicates_allows_numeric():
    out = themis.run(_base_effect_program(
        strict_framing=True,
        fully_frame_running=True,
        fully_frame_belly=True,
    ))
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.5)


def test_strict_on_blocks_even_if_only_one_predicate_is_underframed():
    """Asymmetric case: running is fully framed, belly_fat_loss is
    declared-but-partial. Gate fires because framing_check reports a
    gap on belly_fat_loss."""
    out = themis.run(_base_effect_program(
        strict_framing=True,
        fully_frame_running=True,
        fully_frame_belly=False,
    ))
    r = out["results"][0]
    assert r["status"] == "needs_investigation"
    names = sorted(
        m["name"] for m in r.get("missing_information", [])
        if m["kind"] == "framing"
    )
    assert names == ["framing:belly_fat_loss"]


# ============================================= opt-in preserved

def test_strict_on_with_undeclared_predicates_does_not_block():
    """Opt-in per predicate: a predicate with no VariableDeclaration
    at all produces no framing_note, so the gate sees zero gaps and
    numeric flows. This is the pre-A0 baseline — strict mode cannot
    override it without explicit declarations."""
    out = themis.run(_base_effect_program(
        strict_framing=True,
        declare_running=False,
        declare_belly=False,
    ))
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r.get("framing_notes", []) == []


def test_strict_on_mixed_declared_and_undeclared():
    """running declared (partial) + belly_fat_loss undeclared:
    gate fires only for running."""
    out = themis.run(_base_effect_program(
        strict_framing=True,
        declare_running=True,
        fully_frame_running=False,
        declare_belly=False,
    ))
    r = out["results"][0]
    assert r["status"] == "needs_investigation"
    names = sorted(
        m["name"] for m in r.get("missing_information", [])
        if m["kind"] == "framing"
    )
    assert names == ["framing:running"]


# ============================================= fill-back through the gate

def test_apply_patch_and_run_clears_strict_gate_and_reaches_numeric():
    program = _base_effect_program(strict_framing=True)
    bundle = {
        "version": "0.1", "kind": "framing_skeleton_bundle",
        "patches": [
            {"kind": "variable_patch", "predicate": "running",
             "existing": {"domain": [True, False]},
             "fields": {
                 "time_window": "12w", "measurement": "log",
                 "threshold": ">=3/week", "observability": "self",
                 "direction": "up", "baseline": "prior", "state_vs_event": "state"}},
            {"kind": "variable_patch", "predicate": "belly_fat_loss",
             "existing": {"domain": [True, False]},
             "fields": {
                 "time_window": "12w", "measurement": "cm",
                 "threshold": ">=3", "observability": "self",
                 "direction": "down", "baseline": "prior", "state_vs_event": "state"}},
        ],
    }
    out = themis.apply_patch_and_run(program, [bundle])
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.5)


# ============================================= probability query too

def test_strict_gate_also_applies_to_probability_query():
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": True},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "probability",
             "target": {"atom": atom("y"), "value": True},
             "given": [], "value": 0.3},
            {"kind": "query", "id": "q",
             "query": {"kind": "probability",
                       "target": {"atom": atom("y"), "value": True},
                       "given": []}},
        ],
    }
    r = themis.run(program)["results"][0]
    assert r["status"] == "needs_investigation"
    assert any(
        m["kind"] == "framing" for m in r.get("missing_information", [])
    )


# ============================================= does not gate cause/assoc/identify

def test_strict_gate_does_not_apply_to_cause_query():
    """Structural queries have no numeric path, so strict_framing
    has nothing to gate on them."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": True},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": atom("x"), "to": atom("y")}},
        ],
    }
    r = themis.run(program)["results"][0]
    # cause query still resolves structurally even with underframed
    # predicates and strict_framing=True.
    assert r["status"] == "structurally_solved"


# ============================================= verify round-trip

def test_verify_round_trip_on_strict_blocked_result():
    """A strict-framing-blocked result carries no derivation (nothing
    was computed). themis.verify must handle this gracefully — the
    contract requires a derivation, so it raises ValueError, not a
    silent accept."""
    out = themis.run(_base_effect_program(strict_framing=True))
    r = out["results"][0]
    assert "derivation" not in r
    with pytest.raises(ValueError, match="derivation"):
        themis.verify(_base_effect_program(strict_framing=True), r)


# ============================================= schema validation

def test_schema_rejects_unknown_option_key():
    from themis.input.syntactic_validator import SyntacticError
    from themis.input.syntactic_validator import validate_ast
    program = _base_effect_program(strict_framing=False)
    program["options"] = {"strict_framing": True, "unknown_option": True}
    with pytest.raises(SyntacticError):
        validate_ast(program)


def test_schema_rejects_non_bool_strict_framing():
    from themis.input.syntactic_validator import SyntacticError
    from themis.input.syntactic_validator import validate_ast
    program = _base_effect_program(strict_framing=False)
    program["options"] = {"strict_framing": "yes"}
    with pytest.raises(SyntacticError):
        validate_ast(program)
