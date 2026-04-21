"""Slice A3: multi-turn closed loop via JSON boundary.

Pin ``themis.apply_patch_and_run``: turn 1 produces
``investigation_requests``; turn 2 applies the filled-in bundles and
re-runs through the same pipeline. These tests stay at the JSON
boundary — no typed Program crosses caller code — mirroring what an
external agent would actually do.
"""
from __future__ import annotations

import copy
import json

import pytest

import themis


# ------------------------------------------------- driving programs

def _underframed_effect_program() -> dict:
    """Two underframed predicates, one cause edge, one effect query.
    Turn 1 should yield both a define_variable request (framing gaps)
    and a validate_parameter request (Theta empty)."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "belly_fat_loss",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "intervention": {
                        "atom": {"predicate": "running",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }


def _framing_filled_bundle() -> dict:
    """A framing_skeleton_bundle with every gap field filled, ready
    to patch the underframed program."""
    filled = {
        "time_window": "12w",
        "measurement": "waist cm",
        "threshold": ">=3cm",
        "observability": "self-report",
    }
    return {
        "version": "0.1",
        "kind": "framing_skeleton_bundle",
        "patches": [
            {"kind": "variable_patch", "predicate": "running",
             "existing": {"domain": [True, False]}, "fields": dict(filled)},
            {"kind": "variable_patch", "predicate": "belly_fat_loss",
             "existing": {"domain": [True, False]}, "fields": dict(filled)},
        ],
    }


def _parameter_filled_bundle(value: float = 0.42) -> dict:
    """A parameter_fill_bundle carrying the conditional probability
    the underframed program asked for."""
    return {
        "version": "0.1",
        "kind": "parameter_fill_bundle",
        "skeletons": [
            {
                "kind": "probability",
                "target": {
                    "atom": {"predicate": "belly_fat_loss",
                             "args": [{"type": "const", "name": "me"}]},
                    "value": True,
                },
                "given": [
                    {
                        "atom": {"predicate": "running",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                ],
                "value": value,
                "annotations": {"source": "user_provided"},
            },
        ],
    }


# =================================================== framing round-trip

def test_framing_patch_closes_define_variable_request():
    """Turn 1: define_variable requests. Turn 2 after framing patch:
    define_variable cleared, status still needs_investigation (param
    still missing), but framing side is closed."""
    program = _underframed_effect_program()

    turn1 = themis.run(program)
    define_turn1 = [
        req for req in turn1["results"][0]["investigation_requests"]
        if req["action"] == "define_variable"
    ]
    assert define_turn1

    turn2 = themis.apply_patch_and_run(program, [_framing_filled_bundle()])
    r2 = turn2["results"][0]
    define_turn2 = [
        req for req in r2.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    assert define_turn2 == []
    assert r2.get("framing_notes", []) == []
    # Parameter still missing — framing is advisory, doesn't resolve numeric.
    assert r2["status"] == "needs_investigation"


# ================================================== parameter round-trip

def test_parameter_patch_drives_status_to_numerically_solved():
    """Turn 2 with just the parameter bundle filled: numeric layer
    resolves even if framing is still advisory."""
    program = _underframed_effect_program()
    out = themis.apply_patch_and_run(program, [_parameter_filled_bundle(0.42)])
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.42)
    # Framing advisory should still fire — parameter patch didn't fill
    # those gaps.
    define_reqs = [
        req for req in r.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    assert define_reqs, "framing advisory should survive parameter-only patch"


# ============================================= both bundles in one call

def test_applying_both_bundles_resolves_entire_investigation_set():
    program = _underframed_effect_program()
    out = themis.apply_patch_and_run(
        program,
        [_framing_filled_bundle(), _parameter_filled_bundle(0.42)],
    )
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.42)
    assert r.get("framing_notes", []) == []
    # All investigation channels cleared.
    assert r.get("investigation_requests", []) == []


# ============================================================= inputs

def test_single_patch_dict_is_accepted():
    """Callers can pass one bundle directly without wrapping in a list."""
    program = _underframed_effect_program()
    out = themis.apply_patch_and_run(program, _parameter_filled_bundle(0.1))
    assert out["results"][0]["status"] == "numerically_solved"


def test_empty_patch_list_is_identical_to_plain_run():
    """Zero patches must produce the same structured output as
    ``run(program)`` — an identity invariant for the JSON boundary."""
    program = _underframed_effect_program()
    plain = themis.run(program)
    zero_patch = themis.apply_patch_and_run(program, [])
    assert plain == zero_patch


# ============================================================ errors

def test_unknown_patch_kind_rejected_with_path_scoped_message():
    program = _underframed_effect_program()
    with pytest.raises(ValueError, match=r"patches\[0\]\.kind"):
        themis.apply_patch_and_run(
            program,
            [{"kind": "mystery_bundle", "stuff": []}],
        )


def test_non_dict_patch_is_rejected():
    program = _underframed_effect_program()
    with pytest.raises(TypeError, match=r"patches\[0\]"):
        themis.apply_patch_and_run(program, ["not a dict"])  # type: ignore[list-item]


def test_non_list_non_dict_patches_is_rejected():
    program = _underframed_effect_program()
    with pytest.raises(TypeError, match="patches must be"):
        themis.apply_patch_and_run(program, 123)  # type: ignore[arg-type]


def test_non_supported_program_type_is_rejected():
    with pytest.raises(TypeError, match="program must be"):
        themis.apply_patch_and_run(123, [])  # type: ignore[arg-type]


def test_unfilled_parameter_bundle_raises():
    """Bundle with a null value must raise so the user notices before
    the kernel silently ignores the gap."""
    from themis.workflow.parameter_fill import UnfilledSkeletonError
    program = _underframed_effect_program()
    unfilled = _parameter_filled_bundle()
    unfilled["skeletons"][0]["value"] = None
    with pytest.raises(UnfilledSkeletonError):
        themis.apply_patch_and_run(program, [unfilled])


# ======================================================== immutability

def test_caller_program_dict_not_mutated():
    program = _underframed_effect_program()
    snapshot = json.dumps(program, sort_keys=True)
    themis.apply_patch_and_run(program, [_framing_filled_bundle()])
    assert json.dumps(program, sort_keys=True) == snapshot


def test_caller_patches_dict_not_mutated():
    program = _underframed_effect_program()
    bundle = _framing_filled_bundle()
    snapshot = json.dumps(bundle, sort_keys=True)
    themis.apply_patch_and_run(program, [bundle])
    assert json.dumps(bundle, sort_keys=True) == snapshot


# ================================================ json round-trippable

def test_output_round_trips_through_json_dumps():
    program = _underframed_effect_program()
    out = themis.apply_patch_and_run(
        program,
        [_framing_filled_bundle(), _parameter_filled_bundle(0.42)],
    )
    reloaded = json.loads(json.dumps(out, ensure_ascii=False))
    assert reloaded == out
