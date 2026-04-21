"""Slice A5: pin that each narrative→variables prompt example is valid.

Narrative examples (unlike A1's question examples) emit only a list of
VariableDeclaration statements. To verify they're well-formed, wrap
each example's ``variables`` in a minimal runnable program (add a
provisional cause edge + a cause query between the first two
variables) and run through ``themis.run``. If the variable
declarations are schema-valid and semantically consistent, the wrapped
program dispatches cleanly.

We also verify that framing fields the prompt claims to have filled
really land on the typed VariableDeclaration, and that fields the
prompt left blank really do surface as A0/F1 gaps.
"""
from __future__ import annotations

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


def _load_narrative_examples():
    files = sorted(EXAMPLES_DIR.glob("narrative_*.json"))
    assert files, f"no narrative examples under {EXAMPLES_DIR}"
    return [pytest.param(path, id=path.stem) for path in files]


def _wrap_as_minimal_program(variables: list[dict]) -> dict:
    """Given a narrative example's variables list, build a minimal
    runnable program: add a trivial cause edge between the first two
    variables and a cause query asking about it. This keeps the wrapper
    honest — it exercises project/instantiate/dispatch without
    depending on matching framing content."""
    assert len(variables) >= 2, "need at least 2 variables to wrap"
    p0, p1 = variables[0]["predicate"], variables[1]["predicate"]

    def atom(pred: str) -> dict:
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *variables,
            {
                "kind": "cause",
                "from": atom(p0),
                "to": atom(p1),
                "annotations": {"source": "test_wrapper"},
            },
            {
                "kind": "query", "id": "q",
                "query": {"kind": "cause", "from": atom(p0), "to": atom(p1)},
            },
        ],
    }


@pytest.mark.parametrize("example_path", _load_narrative_examples())
def test_narrative_example_runs_through_kernel(example_path):
    payload = json.loads(example_path.read_text(encoding="utf-8"))

    assert payload.get("narrative_input"), (
        f"{example_path.name}: missing narrative_input"
    )
    assert "variables" in payload, (
        f"{example_path.name}: missing variables list"
    )
    variables = payload["variables"]
    assert isinstance(variables, list) and variables, (
        f"{example_path.name}: variables must be a non-empty list"
    )

    program = _wrap_as_minimal_program(variables)
    out = themis.run(program)
    assert out["results"][0]["status"] == "structurally_solved"


@pytest.mark.parametrize("example_path", _load_narrative_examples())
def test_narrative_reasoning_matches_filled_framing_fields(example_path):
    """If the reasoning block says a predicate's time_window is filled,
    the actual VariableDeclaration must have a non-null time_window —
    and vice-versa for skipped fields. This pins that the prompt's
    self-declared structure actually matches its output."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    reasoning = payload.get("reasoning", {})
    variables_by_pred = {v["predicate"]: v for v in payload["variables"]}

    for item in reasoning.get("identified_variables", []):
        pred = item["predicate"]
        assert pred in variables_by_pred, (
            f"{example_path.name}: reasoning references {pred!r} but no "
            f"such variable declared"
        )
        decl = variables_by_pred[pred]
        for field in item.get("filled_fields", []):
            assert field in decl, (
                f"{example_path.name}: reasoning claims {pred}.{field} "
                f"is filled but declaration omits it"
            )
        for field in item.get("skipped_fields", []):
            assert field not in decl, (
                f"{example_path.name}: reasoning claims {pred}.{field} "
                f"is skipped but declaration includes it"
            )


@pytest.mark.parametrize("example_path", _load_narrative_examples())
def test_narrative_example_surfaces_blank_fields_as_framing_gaps(example_path):
    """Fields that the narrative didn't fill in (skipped_fields in the
    reasoning block) must appear in the framing_notes gap list when
    the program is dispatched. This confirms A0/F1 really picks up
    what the prompt deliberately left blank."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    reasoning = payload.get("reasoning", {})
    program = _wrap_as_minimal_program(payload["variables"])
    out = themis.run(program)
    r = out["results"][0]

    gaps_by_pred = {
        note["predicate"]: set(note["missing"])
        for note in r.get("framing_notes", [])
    }

    reportable = {"time_window", "measurement", "threshold", "observability"}
    for item in reasoning.get("identified_variables", []):
        pred = item["predicate"]
        skipped = set(item.get("skipped_fields", []))
        expected_gaps = skipped & reportable
        if not expected_gaps:
            # Fully framed — predicate should not appear (or appear
            # only with an empty gap list, but A0 doesn't emit empty
            # notes).
            continue
        actual = gaps_by_pred.get(pred, set())
        missing_from_gap_list = expected_gaps - actual
        assert not missing_from_gap_list, (
            f"{example_path.name}: {pred} reasoning claims "
            f"{sorted(expected_gaps)} are blank but gap list surfaces "
            f"{sorted(actual)}"
        )
