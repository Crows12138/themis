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
from themis.input.semantic_validator import SemanticError
from themis.upstream import (
    apply_predicate_links,
    compose_program,
    diagnose_predicate_links,
)


EXAMPLES_DIR = ROOT / "docs" / "prompts" / "examples"

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


def pressure_exercise_waist_variable_merge() -> PressureResult:
    question = _load_example("exercise_waist.json")["kernel_ast"]
    narrative = _load_example("narrative_running.json")

    before_predicates = _declared_predicates(question)
    program = compose_program(
        question,
        variable_extraction={"variables": narrative["variables"]},
    )
    result = themis.run(program)["results"][0]
    themis.verify_data_gap_report(result)

    gaps = _framing_gaps(result)
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

    return PressureResult(
        name="exercise_waist_variable_merge",
        status="PASS",
        details={
            "result_status": result["status"],
            "introduced_predicates": sorted(_declared_predicates(program) - before_predicates),
            "framing_gaps": gaps,
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


def pressure_coffee_latent_edge_gate() -> PressureResult:
    edge_extraction = _load_example("narrative_edges_coffee_alertness.json")
    program = compose_program(
        _coffee_assoc_base_program(),
        edge_extraction=edge_extraction,
    )

    kinds = _edge_kinds(program)
    _require("bidirected" in kinds, "narrative edge extraction should inject a bidirected edge")

    try:
        themis.run(program)
    except SemanticError as exc:
        message = str(exc)
        _require(
            "assoc query on a program containing bidirected edges is not yet supported" in message,
            "unexpected semantic gate message",
        )
        return PressureResult(
            name="coffee_latent_edge_gate",
            status="PASS",
            details={
                "edge_kinds": kinds,
                "blocked_by": type(exc).__name__,
                "message": message,
                "pressure_signal": "admg_assoc_query_needs_scheduler_and_verifier_exposure",
            },
        )

    raise AssertionError("expected SemanticError for ADMG assoc query")


PRESSURES: tuple[Callable[[], PressureResult], ...] = (
    pressure_exercise_waist_variable_merge,
    pressure_late_sleep_predicate_drift,
    pressure_coffee_latent_edge_gate,
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
