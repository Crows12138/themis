"""Slice #40: pin that each reply-to-framing-patch example actually
closes the framing loop correctly when fed through
``themis.apply_patch_and_run``.

Each example carries:

- ``nl_reply`` — the Chinese user answer (for prompt context)
- ``input_bundle`` — the skeleton that surfaced last turn (all nulls)
- ``filled_bundle`` — the expected agent output after parsing the
  reply
- ``reasoning`` — which phrases mapped to which fields

These tests feed each example's filled_bundle into
``apply_patch_and_run`` on top of a canonical underframed program and
verify that the framing gaps shrink exactly as the example's
``reasoning`` predicts — and that the numeric path stays untouched
(framing remains advisory).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import themis

EXAMPLES_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "prompts"
    / "examples"
)


def _load_reply_examples():
    files = sorted(EXAMPLES_DIR.glob("reply_*.json"))
    assert files, f"no reply examples under {EXAMPLES_DIR}"
    return [pytest.param(path, id=path.stem) for path in files]


def _underframed_program() -> dict:
    """The canonical two-variable underframed program matching the
    running / belly_fat_loss skeleton shape in the examples."""
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running", "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss", "domain": [True, False]},
            {"kind": "cause",
             "from": atom("running"),
             "to": atom("belly_fat_loss"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": atom("belly_fat_loss"), "value": True},
                       "intervention": {"atom": atom("running"), "value": True},
                       "given": []}},
        ],
    }


@pytest.mark.parametrize("example_path", _load_reply_examples())
def test_reply_example_structure(example_path):
    """Every reply example must carry the four fields in the shape
    the prompt promises."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    assert payload.get("nl_reply"), f"{example_path.name}: nl_reply required"
    for key in ("input_bundle", "filled_bundle"):
        assert key in payload, f"{example_path.name}: {key} required"
        bundle = payload[key]
        assert bundle["kind"] == "framing_skeleton_bundle"
        assert bundle["version"] == "0.1"
        assert "patches" in bundle and bundle["patches"]
        for patch in bundle["patches"]:
            assert patch["kind"] == "variable_patch"
            assert patch["predicate"]
            assert "fields" in patch


@pytest.mark.parametrize("example_path", _load_reply_examples())
def test_reply_example_preserves_existing_and_structure(example_path):
    """Filled bundle must not touch ``existing`` or rewrite the patch
    shape — the agent fills nulls only."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    inp = payload["input_bundle"]
    out = payload["filled_bundle"]

    assert len(inp["patches"]) == len(out["patches"])
    in_by_pred = {p["predicate"]: p for p in inp["patches"]}
    out_by_pred = {p["predicate"]: p for p in out["patches"]}
    assert set(in_by_pred) == set(out_by_pred)

    for pred, in_patch in in_by_pred.items():
        out_patch = out_by_pred[pred]
        assert out_patch["existing"] == in_patch["existing"], (
            f"{example_path.name}: existing changed for {pred}"
        )
        assert set(out_patch["fields"].keys()) == set(in_patch["fields"].keys()), (
            f"{example_path.name}: fields keys changed for {pred}"
        )


@pytest.mark.parametrize("example_path", _load_reply_examples())
def test_reply_example_fills_only_null_slots(example_path):
    """An agent must only fill nulls — if a field had a value in the
    input (rare for fresh skeletons), it must not be overwritten.
    For these examples all inputs are nulls, so any non-null output
    is a legitimate fill."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    in_by_pred = {p["predicate"]: p for p in payload["input_bundle"]["patches"]}
    out_by_pred = {p["predicate"]: p for p in payload["filled_bundle"]["patches"]}
    for pred, in_patch in in_by_pred.items():
        for field, in_val in in_patch["fields"].items():
            out_val = out_by_pred[pred]["fields"][field]
            if in_val is not None:
                assert out_val == in_val, (
                    f"{example_path.name}: {pred}.{field} was already set to "
                    f"{in_val!r} in the input — filled bundle overwrote it"
                )


@pytest.mark.parametrize("example_path", _load_reply_examples())
def test_reply_example_closes_expected_gaps(example_path):
    """End-to-end: feed the filled bundle into apply_patch_and_run on
    the canonical underframed program. For each (predicate, field)
    pair the example filled, the corresponding A0/F1 gap must
    disappear. For each field left null, the gap must still be
    reported."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    program = _underframed_program()

    out = themis.apply_patch_and_run(program, [payload["filled_bundle"]])
    r = out["results"][0]

    gaps_by_pred = {
        note["predicate"]: set(note["missing"])
        for note in r.get("framing_notes", [])
    }

    reportable = {
        "time_window", "measurement", "threshold", "observability",
        "direction", "baseline", "state_vs_event",
    }
    for patch in payload["filled_bundle"]["patches"]:
        pred = patch["predicate"]
        filled_here = {
            k for k, v in patch["fields"].items()
            if v is not None and k in reportable
        }
        still_null_here = {
            k for k, v in patch["fields"].items()
            if v is None and k in reportable
        }
        actual_gaps = gaps_by_pred.get(pred, set())
        # Every filled field must be absent from the gap list.
        leaked = filled_here & actual_gaps
        assert not leaked, (
            f"{example_path.name}: {pred} filled {filled_here} but A0/F1 "
            f"still flags {sorted(leaked)} as gaps"
        )
        # Every still-null reportable field must remain in the gap list.
        missing_from_gaps = still_null_here - actual_gaps
        assert not missing_from_gaps, (
            f"{example_path.name}: {pred} left {sorted(still_null_here)} "
            f"null but A0/F1 didn't surface {sorted(missing_from_gaps)}"
        )


@pytest.mark.parametrize("example_path", _load_reply_examples())
def test_reply_example_does_not_change_numeric_path(example_path):
    """Advisory contract: whether 0 or all 8 fields got filled, the
    numeric / parameter investigation side of the result must be
    untouched (still a missing CPT, same parameter target)."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    program = _underframed_program()

    before = themis.run(program)["results"][0]
    after = themis.apply_patch_and_run(
        program, [payload["filled_bundle"]]
    )["results"][0]

    # Neither turn has numeric data to resolve — both must stay
    # needs_investigation.
    assert before["status"] == after["status"] == "needs_investigation"

    # The parameter investigation's target must match before vs after.
    def _param_targets(result):
        out = []
        for req in result.get("investigation_requests", []):
            if req["action"] == "validate_parameter":
                for item in req.get("items", []):
                    out.append(item["target"])
        return sorted(out)

    assert _param_targets(before) == _param_targets(after), (
        f"{example_path.name}: parameter-side requests drifted, violating "
        f"framing advisory semantics"
    )
