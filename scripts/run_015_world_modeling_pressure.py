"""0.15 world-modeling pressure harness — fix Phase 4 / Phase 15
upstream-modeling pressure cases as repeatable end-to-end runs.

No new kernel semantics, no LLM. Threads existing A1/A2/A5 prompt
examples + ``themis.upstream.compose_program(...)`` +
``themis.run(...)`` + ``verify`` / ``verify_data_gap_report`` into
five pinned cases that historically surfaced upstream-layer pain:

1. **exercise_waist_variable_merge** — narrative framing shrinks
   `running` gap but `belly_fat_loss` stays under-framed
2. **late_sleep_predicate_drift** — question and narrative use
   different predicate names; tests predicate-link diagnostic
3. **late_sleep_predicate_links_rewrite_edges** — confirmed link
   bundle rewrites both narrative variables and A2 edge endpoints
4. **coffee_latent_edge_assoc** — A2-extracted bidirected latent edge
   makes ADMG assoc query return structural answer via
   `m_connection_witness`
5. **ice_cream_refusal_filters_edge** — A2 refusal filters A1
   question-side naive edge; final cause query returns ``False``

Run with::

    python scripts/run_015_world_modeling_pressure.py

Each case prints `[PASS] <name>` with key fields. Loses the diagnostic
value if any pressure_signal stops triggering — these are the ground
truth that 0.15 upstream layer must keep producing as it evolves.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import themis
from themis.upstream import (
    apply_predicate_links,
    compose_program,
    diagnose_edge_predicate_links,
    diagnose_predicate_links,
)


EXAMPLES_DIR = ROOT / "themis" / "prompts" / "examples"

FRAMING_FIELDS = (
    "time_window",
    "measurement",
    "threshold",
    "observability",
    "direction",
    "baseline",
    "state_vs_event",
)


@dataclass(frozen=True)
class PressureResult:
    name: str
    status: str
    details: dict[str, Any]
    error: str | None = None


def _load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _atom(predicate: str) -> dict[str, Any]:
    return {
        "predicate": predicate,
        "args": [{"type": "const", "name": "me"}],
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _declared_predicates(program: dict[str, Any]) -> set[str]:
    return {
        statement["predicate"]
        for statement in program.get("statements", [])
        if isinstance(statement, dict)
        and statement.get("kind") == "variable"
        and isinstance(statement.get("predicate"), str)
    }


def _framing_gaps(result: dict[str, Any]) -> dict[str, list[str]]:
    return {
        note["predicate"]: list(note.get("missing", []))
        for note in result.get("framing_notes", [])
    }


def _data_gap_kinds(result: dict[str, Any]) -> list[str]:
    report = result.get("data_gap_report") or {}
    return [gap["kind"] for gap in report.get("gaps", [])]


def _investigation_actions(result: dict[str, Any]) -> list[str]:
    return [
        request["action"]
        for request in result.get("investigation_requests", [])
        if isinstance(request, dict) and "action" in request
    ]


def _edge_kinds(program: dict[str, Any]) -> list[str]:
    return [
        statement["kind"]
        for statement in program.get("statements", [])
        if isinstance(statement, dict) and statement.get("kind") in {"cause", "bidirected"}
    ]


def _edge_pairs(program: dict[str, Any]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for statement in program.get("statements", []):
        if not isinstance(statement, dict):
            continue
        if statement.get("kind") == "cause":
            pairs.append([
                statement["from"]["predicate"],
                statement["to"]["predicate"],
            ])
        elif statement.get("kind") == "bidirected":
            pairs.append([
                statement["left"]["predicate"],
                statement["right"]["predicate"],
            ])
    return pairs


def pressure_exercise_waist_variable_merge() -> PressureResult:
    question = _load_example("exercise_waist.json")["kernel_ast"]
    narrative = _load_example("narrative_running.json")

    before_predicates = _declared_predicates(question)
    link_diagnostic = diagnose_predicate_links(
        question,
        {"variables": narrative["variables"]},
    )
    program = compose_program(
        question,
        variable_extraction={"variables": narrative["variables"]},
    )
    result = themis.run(program)["results"][0]
    themis.verify_data_gap_report(result)

    confirmed_links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "waist_reduced",
                "target_predicate": "belly_fat_loss",
            },
        ],
    }
    linked_extraction = apply_predicate_links(
        {"variables": narrative["variables"]},
        confirmed_links,
    )
    linked_program = compose_program(
        question,
        variable_extraction=linked_extraction,
    )
    linked_result = themis.run(linked_program)["results"][0]
    themis.verify_data_gap_report(linked_result)

    gaps = _framing_gaps(result)
    linked_gaps = _framing_gaps(linked_result)
    _require(result["status"] == "needs_investigation", "exercise case should need data")
    _require(
        set(gaps["running"]) == {"direction", "baseline", "state_vs_event"},
        "narrative should shrink running framing gaps to the three #41 fields",
    )
    _require(
        set(gaps["belly_fat_loss"]) == set(FRAMING_FIELDS),
        "belly_fat_loss should remain fully underframed",
    )
    _require(
        "missing_distribution" in _data_gap_kinds(result),
        "effect case should surface missing_distribution",
    )
    by_source = {
        item["source_predicate"]: item
        for item in link_diagnostic["unmatched"]
    }
    _require(
        set(by_source) == {"waist_reduced"},
        "exercise link diagnostic should report the narrative-only waist predicate",
    )
    _require(
        by_source["waist_reduced"]["candidates"][0]["target_predicate"]
        == "belly_fat_loss",
        "exercise link diagnostic should rank the query target first",
    )
    _require(
        by_source["waist_reduced"]["candidates"][0]["score"] < 0.5,
        "waist_reduced -> belly_fat_loss must stay explicit-confirmation only",
    )
    _require(
        _declared_predicates(linked_program) == before_predicates,
        "confirmed exercise target link should not add new declarations",
    )
    _require(
        set(linked_gaps["belly_fat_loss"])
        == {"direction", "baseline", "state_vs_event"},
        "confirmed waist target link should transfer measurement framing",
    )
    _require(
        "missing_distribution" in _data_gap_kinds(linked_result),
        "confirmed target framing still leaves the statistical data gap",
    )

    return PressureResult(
        name="exercise_waist_variable_merge",
        status="PASS",
        details={
            "result_status": result["status"],
            "introduced_predicates": sorted(_declared_predicates(program) - before_predicates),
            "link_diagnostic": link_diagnostic,
            "framing_gaps": gaps,
            "after_confirmed_links": {
                "introduced_predicates": sorted(
                    _declared_predicates(linked_program) - before_predicates
                ),
                "framing_gaps": linked_gaps,
                "data_gap_kinds": _data_gap_kinds(linked_result),
                "data_gap_verify": "accepted",
            },
            "investigation_actions": _investigation_actions(result),
            "data_gap_kinds": _data_gap_kinds(result),
            "data_gap_verify": "accepted",
            "pressure_signal": "variable_framing_merge_works_but_target_still_underframed",
        },
    )


def pressure_late_sleep_predicate_drift() -> PressureResult:
    question = _load_example("late_night_tired_temporal.json")["kernel_ast"]
    narrative = _load_example("narrative_late_sleep.json")

    before_predicates = _declared_predicates(question)
    link_diagnostic = diagnose_predicate_links(
        question,
        {"variables": narrative["variables"]},
    )
    program = compose_program(
        question,
        variable_extraction={"variables": narrative["variables"]},
    )
    result = themis.run(program)["results"][0]
    themis.verify(program, result)
    themis.verify_data_gap_report(result)

    confirmed_links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "staying_up_late",
                "target_predicate": "stays_up_late",
            },
            {
                "source_predicate": "cognitive_slowness",
                "target_predicate": "feels_tired_next_morning",
            },
        ],
    }
    linked_extraction = apply_predicate_links(
        {"variables": narrative["variables"]},
        confirmed_links,
    )
    linked_program = compose_program(
        question,
        variable_extraction=linked_extraction,
    )
    linked_result = themis.run(linked_program)["results"][0]
    themis.verify(linked_program, linked_result)
    themis.verify_data_gap_report(linked_result)

    introduced = sorted(_declared_predicates(program) - before_predicates)
    gaps = _framing_gaps(result)
    _require(result["status"] == "structurally_solved", "temporal cause should solve structurally")
    _require(
        introduced == ["cognitive_slowness", "staying_up_late"],
        "narrative predicates should land as unmatched declarations",
    )
    by_source = {
        item["source_predicate"]: item
        for item in link_diagnostic["unmatched"]
    }
    _require(
        set(by_source) == {"cognitive_slowness", "staying_up_late"},
        "link diagnostic should report both drifted narrative predicates",
    )
    _require(
        by_source["staying_up_late"]["candidates"][0]["target_predicate"]
        == "stays_up_late",
        "link diagnostic should rank the morphological late-sleep match first",
    )
    _require(
        set(gaps["stays_up_late"]) == set(FRAMING_FIELDS),
        "question-side stays_up_late should remain unframed because the narrative used staying_up_late",
    )
    _require(
        set(gaps["feels_tired_next_morning"]) == set(FRAMING_FIELDS),
        "question-side outcome should remain unframed because the narrative used cognitive_slowness",
    )
    linked_gaps = _framing_gaps(linked_result)
    _require(
        _declared_predicates(linked_program) == before_predicates,
        "confirmed predicate links should not add new declarations",
    )
    _require(
        set(linked_gaps["stays_up_late"])
        == {"measurement", "direction", "baseline", "state_vs_event"},
        "confirmed link should transfer late-sleep framing onto query predicate",
    )
    _require(
        set(linked_gaps["feels_tired_next_morning"])
        == {
            "time_window",
            "measurement",
            "threshold",
            "direction",
            "baseline",
            "state_vs_event",
        },
        "confirmed link should transfer outcome observability onto query predicate",
    )

    return PressureResult(
        name="late_sleep_predicate_drift",
        status="PASS",
        details={
            "result_status": result["status"],
            "introduced_predicates": introduced,
            "link_diagnostic": link_diagnostic,
            "query_predicate_gaps": gaps,
            "after_confirmed_links": {
                "introduced_predicates": sorted(
                    _declared_predicates(linked_program) - before_predicates
                ),
                "query_predicate_gaps": linked_gaps,
                "verify": "accepted",
                "data_gap_verify": "accepted",
            },
            "verify": "accepted",
            "data_gap_verify": "accepted",
            "pressure_signal": "predicate_name_drift_blocks_narrative_framing_reuse",
        },
    )


def _late_sleep_edge_link_base_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late", "domain": [True, False]},
            {"kind": "variable", "predicate": "feels_tired_next_morning", "domain": [True, False]},
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("stays_up_late"),
                    "to": _atom("feels_tired_next_morning"),
                },
            },
        ],
    }


def pressure_late_sleep_predicate_links_rewrite_edges() -> PressureResult:
    drifted_edge_extraction = {
        "edges": [
            {
                "kind": "cause",
                "from": {"predicate": "staying_up_late"},
                "to": {"predicate": "cognitive_slowness"},
                "annotations": {
                    "source": "narrative_proposal",
                    "evidence": "最近连续一周熬夜到凌晨两点，第二天上午总是没精神",
                },
            },
        ],
        "refusals": [],
        "narrative_ambiguities": [
            {
                "kind": "alias",
                "description": "narrative edge predicates use the unconfirmed A5 names",
            },
        ],
    }
    confirmed_links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "staying_up_late",
                "target_predicate": "stays_up_late",
            },
            {
                "source_predicate": "cognitive_slowness",
                "target_predicate": "feels_tired_next_morning",
            },
        ],
    }
    link_diagnostic = diagnose_edge_predicate_links(
        _late_sleep_edge_link_base_program(),
        drifted_edge_extraction,
    )

    program = compose_program(
        _late_sleep_edge_link_base_program(),
        edge_extraction=drifted_edge_extraction,
        predicate_links=confirmed_links,
    )
    result = themis.run(program)["results"][0]
    themis.verify(program, result)
    themis.verify_data_gap_report(result)

    pairs = _edge_pairs(program)
    ambiguity_kinds = [
        ambiguity.get("kind")
        for ambiguity in program.get("extensions", {}).get("ambiguities", [])
    ]
    by_source = {
        item["source_predicate"]: item
        for item in link_diagnostic["unmatched"]
    }
    _require(
        set(by_source) == {"cognitive_slowness", "staying_up_late"},
        "edge predicate diagnostic should report both drifted endpoints",
    )
    _require(
        by_source["staying_up_late"]["candidates"][0]["target_predicate"]
        == "stays_up_late",
        "edge predicate diagnostic should rank the morphological match first",
    )
    _require(
        pairs == [["stays_up_late", "feels_tired_next_morning"]],
        "confirmed predicate links should rewrite narrative edge endpoints",
    )
    _require(
        result["structural_result"]["value"] is True,
        "rewritten narrative edge should support the cause query",
    )
    _require(
        "alias" in ambiguity_kinds,
        "edge-level alias decision should remain auditable",
    )

    return PressureResult(
        name="late_sleep_predicate_links_rewrite_edges",
        status="PASS",
        details={
            "link_diagnostic": link_diagnostic,
            "edge_pairs": pairs,
            "ambiguity_kinds": ambiguity_kinds,
            "result_status": result["status"],
            "structural_value": result["structural_result"]["value"],
            "verify": "accepted",
            "data_gap_verify": "accepted",
            "pressure_signal": "confirmed_predicate_links_rewrite_edge_endpoints",
        },
    )


def _coffee_assoc_base_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "drinks_coffee", "domain": [True, False]},
            {"kind": "variable", "predicate": "alertness", "domain": [True, False]},
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "assoc",
                    "left": _atom("drinks_coffee"),
                    "right": _atom("alertness"),
                    "given": [],
                },
            },
        ],
    }


def pressure_coffee_latent_edge_assoc() -> PressureResult:
    edge_extraction = _load_example("narrative_edges_coffee_alertness.json")
    program = compose_program(
        _coffee_assoc_base_program(),
        edge_extraction=edge_extraction,
    )

    kinds = _edge_kinds(program)
    _require("bidirected" in kinds, "narrative edge extraction should inject a bidirected edge")
    ambiguity_kinds = [
        ambiguity.get("kind")
        for ambiguity in program.get("extensions", {}).get("ambiguities", [])
    ]
    _require(
        "admg_unobserved_common_cause" in ambiguity_kinds,
        "narrative ADMG ambiguity should stay on the final program boundary",
    )
    result = themis.run(program)["results"][0]
    themis.verify(program, result)
    themis.verify_data_gap_report(result)

    _require(
        result["status"] == "structurally_solved",
        "ADMG assoc query should solve structurally after S4 gate lift",
    )
    _require(
        result["structural_result"]["value"] is True,
        "coffee latent edge should make the two variables m-connected",
    )
    rule = result["derivation"]["steps"][-1]["rule"]
    _require(rule == "m_connection_witness", "expected m-connection witness")

    return PressureResult(
        name="coffee_latent_edge_assoc",
        status="PASS",
        details={
            "edge_kinds": kinds,
            "ambiguity_kinds": ambiguity_kinds,
            "result_status": result["status"],
            "structural_value": result["structural_result"]["value"],
            "witness_rule": rule,
            "verify": "accepted",
            "data_gap_verify": "accepted",
            "pressure_signal": "admg_assoc_query_now_uses_m_connection_witness",
        },
    )


def _ice_cream_refusal_base_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "eating_ice_cream", "domain": [True, False]},
            {"kind": "variable", "predicate": "drowning", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom("eating_ice_cream"),
                "to": _atom("drowning"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("eating_ice_cream"),
                    "to": _atom("drowning"),
                },
            },
        ],
    }


def pressure_ice_cream_refusal_filters_edge() -> PressureResult:
    edge_extraction = _load_example("narrative_edges_ice_cream_drowning.json")
    program = compose_program(
        _ice_cream_refusal_base_program(),
        edge_extraction=edge_extraction,
    )
    result = themis.run(program)["results"][0]
    themis.verify(program, result)
    themis.verify_data_gap_report(result)

    edge_kinds = _edge_kinds(program)
    ambiguity_kinds = [
        ambiguity.get("kind")
        for ambiguity in program.get("extensions", {}).get("ambiguities", [])
    ]
    _require(edge_kinds == [], "narrative refusal should remove the naive direct edge")
    _require(
        "confounder_refusal" in ambiguity_kinds,
        "refusal should remain visible as an ambiguity record",
    )
    _require(
        result["structural_result"]["value"] is False,
        "after refusal filtering, cause query should be structurally false",
    )

    return PressureResult(
        name="ice_cream_refusal_filters_edge",
        status="PASS",
        details={
            "edge_kinds_after_refusal": edge_kinds,
            "ambiguity_kinds": ambiguity_kinds,
            "result_status": result["status"],
            "structural_value": result["structural_result"]["value"],
            "verify": "accepted",
            "data_gap_verify": "accepted",
            "pressure_signal": "narrative_refusal_filters_question_side_naive_edge",
        },
    )


PRESSURES: tuple[Callable[[], PressureResult], ...] = (
    pressure_exercise_waist_variable_merge,
    pressure_late_sleep_predicate_drift,
    pressure_late_sleep_predicate_links_rewrite_edges,
    pressure_coffee_latent_edge_assoc,
    pressure_ice_cream_refusal_filters_edge,
)


def run_all() -> list[PressureResult]:
    results: list[PressureResult] = []
    for pressure in PRESSURES:
        try:
            results.append(pressure())
        except Exception as exc:
            results.append(
                PressureResult(
                    name=pressure.__name__.removeprefix("pressure_"),
                    status="FAIL",
                    details={},
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def _print_text(results: list[PressureResult]) -> None:
    print("Themis 0.15 world-modeling pressure")
    for result in results:
        suffix = f" - {result.error}" if result.error and result.status == "FAIL" else ""
        print(f"[{result.status}] {result.name}{suffix}")
        for key, value in result.details.items():
            print(f"  {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    results = run_all()
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False))
    else:
        _print_text(results)
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
