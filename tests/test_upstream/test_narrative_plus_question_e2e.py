"""Slice #37.b: narrative + question end-to-end.

Closes the loop from both prompt-layer outputs (A5 narrative and A1
question) through the dict-level merge (slice #37.a) into
``themis.run``. Uses the existing prompt-example fixtures as real
driving inputs so the test breaks loudly if any of them drifts.

Scenario exercised: the W0 driving case — "我每天跑步，肚子上的肉会瘦
下来吗" — with a narrative paragraph about the running habit providing
operationalization for the shared ``running`` predicate, plus an
extra ``waist_reduced`` variable the narrative introduces that the
question alone did not declare.
"""
from __future__ import annotations

import json
from pathlib import Path

import themis
from themis.upstream import merge_into_program

EXAMPLES_DIR = (
    Path(__file__).resolve().parents[2]
    / "themis"
    / "prompts"
    / "examples"
)


def _load(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_narrative_framing_lands_on_shared_predicate():
    """Narrative supplies the framing fields the question left blank
    on the ``running`` predicate — after merge, ``running`` carries
    the narrative's metadata and the framing gap list shrinks."""
    question = _load("exercise_waist.json")["kernel_ast"]
    narrative = _load("narrative_running.json")

    # Baseline: before merge, ``running`` declaration is bare.
    pre_run = next(
        s for s in question["statements"]
        if s.get("kind") == "variable" and s["predicate"] == "running"
    )
    assert "time_window" not in pre_run
    assert "threshold" not in pre_run

    merged = merge_into_program(question, {"variables": narrative["variables"]})

    # After merge: ``running`` now carries narrative framing.
    post_run = next(
        s for s in merged["statements"]
        if s.get("kind") == "variable" and s["predicate"] == "running"
    )
    assert post_run["time_window"] == "past 3 months"
    assert post_run["threshold"] == ">=4 sessions/week, 30 min each"
    assert post_run["measurement"] == "self-report of sessions"
    assert post_run["observability"] == "self-report"

    # ``belly_fat_loss`` was not in the narrative — stays bare.
    post_belly = next(
        s for s in merged["statements"]
        if s.get("kind") == "variable" and s["predicate"] == "belly_fat_loss"
    )
    assert "time_window" not in post_belly


def test_narrative_only_predicate_lands_as_new_declaration():
    """``waist_reduced`` is in the narrative but not in the question.
    Merge adds it as a new declaration; the question's edges and query
    are unchanged."""
    question = _load("exercise_waist.json")["kernel_ast"]
    narrative = _load("narrative_running.json")

    merged = merge_into_program(question, {"variables": narrative["variables"]})

    decls = {s["predicate"] for s in merged["statements"]
             if s.get("kind") == "variable"}
    assert decls == {"running", "belly_fat_loss", "waist_reduced"}

    # Edge and query survive the merge unchanged.
    causes = [s for s in merged["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    assert causes[0]["from"]["predicate"] == "running"
    assert causes[0]["to"]["predicate"] == "belly_fat_loss"

    queries = [s for s in merged["statements"] if s.get("kind") == "query"]
    assert len(queries) == 1
    assert queries[0]["query"]["kind"] == "effect"


def test_merged_program_runs_and_gap_list_matches_merge():
    """e2e: merged program dispatches through themis.run. The framing
    gaps reported on ``running`` should equal the narrative's
    skipped_fields (not the question's bare-decl gap set), while
    ``belly_fat_loss`` should still surface the full gap list."""
    question = _load("exercise_waist.json")["kernel_ast"]
    narrative = _load("narrative_running.json")

    merged = merge_into_program(question, {"variables": narrative["variables"]})
    out = themis.run(merged)
    r = out["results"][0]

    # Effect query with no CPT — still needs_investigation.
    assert r["status"] == "needs_investigation"

    gaps = {n["predicate"]: set(n["missing"])
            for n in r.get("framing_notes", [])}

    # ``running`` narrative filled time_window / measurement /
    # threshold / observability, skipped direction / baseline /
    # state_vs_event. Those three should be the only remaining gaps.
    assert gaps.get("running") == {"direction", "baseline", "state_vs_event"}

    # ``belly_fat_loss`` stayed bare — all seven A0-reportable fields
    # surface as gaps.
    assert gaps.get("belly_fat_loss") == {
        "time_window", "measurement", "threshold", "observability",
        "direction", "baseline", "state_vs_event",
    }


def test_define_variable_request_drops_fully_framed_predicate():
    """F1 emits a define_variable investigation item per predicate with
    remaining gaps. After merge, ``running`` is not fully framed (3
    dims still missing) so it still appears — but its skeleton's
    nulls should be exactly those 3 fields, not all 7."""
    question = _load("exercise_waist.json")["kernel_ast"]
    narrative = _load("narrative_running.json")

    merged = merge_into_program(question, {"variables": narrative["variables"]})
    out = themis.run(merged)
    r = out["results"][0]

    framing_reqs = [
        req for req in r.get("investigation_requests", [])
        if req.get("action") == "define_variable"
    ]
    assert len(framing_reqs) == 1
    items_by_target = {it["target"]: it for it in framing_reqs[0]["items"]}

    assert "running" in items_by_target
    run_fields = items_by_target["running"]["skeleton"]["fields"]
    null_fields = {k for k, v in run_fields.items() if v is None}
    assert null_fields == {"direction", "baseline", "state_vs_event"}

    # ``belly_fat_loss`` all seven still null.
    belly_fields = items_by_target["belly_fat_loss"]["skeleton"]["fields"]
    belly_nulls = {k for k, v in belly_fields.items() if v is None}
    assert belly_nulls == {
        "time_window", "measurement", "threshold", "observability",
        "direction", "baseline", "state_vs_event",
    }
