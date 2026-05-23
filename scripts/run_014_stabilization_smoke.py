"""0.14 stabilization smoke — fast end-to-end check of the five paths
that are easiest to break with a careless refactor:

1. dose-response NL question → `data_gap_report` with
   `dose_response_data_required` (Phase 13)
2. transport `themis.run` → `themis.verify` round-trip (Phase 9 §T9.1)
3. dose-response `themis.estimate(...)` → `numeric_estimate` + verify
   (Phase 14)
4. transport gap → mock KB adapter → `parameter_fill_bundle` →
   `apply_patch_and_run`
5. MCP wrapper → tool catalog + `themis_run` + `themis_verify` +
   `themis_verify_data_gap_report` + `themis_estimate` + resources

No LLM, no network. Run with::

    python scripts/run_014_stabilization_smoke.py

Each path prints a `[PASS] <name>` line with the key fields it
verified, or fails fast with a traceback. The pytest suite covers the
same surface with finer granularity; this script is a one-shot
sanity check for releases / demos.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import themis


@dataclass(frozen=True)
class SmokeResult:
    name: str
    status: str
    details: dict[str, Any]
    error: str | None = None


def _atom(predicate: str) -> dict[str, Any]:
    return {
        "predicate": predicate,
        "args": [{"type": "const", "name": "me"}],
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _call_mcp_tool(app: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    blocks = asyncio.run(app.call_tool(name, args))
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no text content returned by MCP tool {name!r}")


def _verify_state(program: dict[str, Any], result: dict[str, Any]) -> str:
    if not result.get("derivation"):
        return "not_applicable:no_derivation"
    themis.verify(program, result)
    return "accepted"


def _verify_data_gap_state(result: dict[str, Any]) -> str:
    report = result.get("data_gap_report")
    if report is None:
        return "not_applicable:no_data_gap_report"

    from themis.verifier.data_gap_rules import verify_data_gap_report

    verify_data_gap_report(
        report,
        derivation=result.get("derivation"),
        investigation_requests=result.get("investigation_requests", []),
        framing_notes=result.get("framing_notes", []),
    )
    return "accepted"


def _dose_response_diagnostic_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {
                    "kind": "dose_response_query",
                    "description": "user asks for raise_amount vs engagement curve",
                },
            ],
        },
        "statements": [
            {
                "kind": "variable",
                "predicate": "engagement",
                "domain": [1, 2, 3, 4, 5],
            },
            {"kind": "variable", "predicate": "raise_amount"},
            {
                "kind": "cause",
                "from": _atom("raise_amount"),
                "to": _atom("engagement"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": _atom("raise_amount"),
                        "value": True,
                    },
                    "target": {"atom": _atom("engagement"), "value": 4},
                    "given": [],
                },
            },
        ],
    }


def smoke_dose_response_diagnostic() -> SmokeResult:
    program = _dose_response_diagnostic_program()
    result = themis.run(program)["results"][0]
    gaps = result.get("data_gap_report", {}).get("gaps", [])
    gap_kinds = [gap["kind"] for gap in gaps]

    _require(result["status"] == "needs_investigation", "expected diagnostic gap")
    _require(
        "dose_response_data_required" in gap_kinds,
        "missing dose_response_data_required gap",
    )

    dose_gap = next(gap for gap in gaps if gap["kind"] == "dose_response_data_required")
    required_data = dose_gap["required_data"]
    _require(
        "confounders_required" in required_data,
        "confounders_required must be present, even when empty",
    )
    _require(
        required_data["sampling_point_count"] >= 4,
        "dose-response diagnostic should request at least 4 sampling points",
    )

    return SmokeResult(
        name="dose_response_diagnostic",
        status="PASS",
        details={
            "kernel_status": result["status"],
            "gap_kinds": gap_kinds,
            "sampling_point_count": required_data["sampling_point_count"],
            "query_verify": _verify_state(program, result),
            "data_gap_verify": _verify_data_gap_state(result),
        },
    )


def _transport_program_from_case_29() -> dict[str, Any]:
    case_path = ROOT / "docs" / "eval_set" / "cases" / "29_running_belly_fat_transport.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))

    statements: list[dict[str, Any]] = []
    seen_predicates: set[str] = set()
    for variable in case["gold_variables"]:
        predicate = variable["predicate"]
        if predicate in seen_predicates:
            continue
        seen_predicates.add(predicate)
        statements.append({
            "kind": "variable",
            "predicate": predicate,
            "domain": [True, False],
        })
    for edge in case["gold_edges"]:
        statements.append({
            "kind": "cause",
            "from": _atom(edge["from"]),
            "to": _atom(edge["to"]),
        })
    for selection in case.get("gold_selection_nodes", []):
        statements.append({
            "kind": "selection_node",
            "id": selection["id"],
            "affects": _atom(selection["affects"]),
            "source_population": selection["source_population"],
            "target_population": selection["target_population"],
        })
    statements.append({
        "kind": "query",
        "id": "q",
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


def smoke_transport_verify() -> SmokeResult:
    program = _transport_program_from_case_29()
    result = themis.run(program)["results"][0]
    extension = result.get("extensions", {}).get("transport_identification")
    gaps = result.get("data_gap_report", {}).get("gaps", [])
    gap_kinds = [gap["kind"] for gap in gaps]

    _require(result["status"] == "structurally_solved", "transport should solve structurally")
    _require(extension is not None, "missing transport_identification extension")
    _require(result.get("numeric_estimate") is None, "transport T9.1 should not estimate")
    _require(
        any(kind.startswith("transport_") for kind in gap_kinds),
        "transport result should surface transport data gaps",
    )

    verify = _verify_state(program, result)
    _require(verify == "accepted", "transport derivation should verify")
    return SmokeResult(
        name="transport_verify_and_gap",
        status="PASS",
        details={
            "kernel_status": result["status"],
            "query_verify": verify,
            "data_gap_verify": _verify_data_gap_state(result),
            "gap_kinds": gap_kinds,
            "adjustment_set": [
                atom["predicate"] for atom in extension.get("adjustment_set", [])
            ],
        },
    )


def _dose_response_estimator_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {
                    "kind": "dose_response_query",
                    "description": "raise_amount vs engagement curve",
                },
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "variable", "predicate": "engagement"},
            {
                "kind": "cause",
                "from": _atom("raise_amount"),
                "to": _atom("engagement"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": _atom("raise_amount"),
                        "value": True,
                    },
                    "target": {"atom": _atom("engagement"), "value": 4},
                    "given": [],
                },
            },
        ],
    }


def _linear_dose_response_data(n: int = 240):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(17)
    treatment = rng.uniform(0.0, 10.0, size=n)
    outcome = 1.0 + 0.5 * treatment + rng.normal(0.0, 1.0, size=n)
    return pd.DataFrame({
        "raise_amount": treatment,
        "engagement": outcome,
    })


def smoke_dose_response_estimate() -> SmokeResult:
    try:
        import econml  # noqa: F401
    except ImportError as exc:
        return SmokeResult(
            name="dose_response_estimate_verify",
            status="SKIP",
            details={"reason": "econml not installed"},
            error=str(exc),
        )

    program = _dose_response_estimator_program()
    result = themis.estimate(
        program,
        _linear_dose_response_data(),
        model="linear",
    )["results"][0]
    numeric_estimate = result.get("numeric_estimate") or {}
    curve = numeric_estimate.get("dose_response_curve") or []

    _require(result["status"] == "numerically_solved", "estimate should solve numerically")
    _require(
        numeric_estimate.get("method") == "dose_response_linear_dml",
        "unexpected dose-response estimator method",
    )
    _require(len(curve) >= 2, "dose-response curve should have at least two points")

    verify = _verify_state(program, result)
    _require(verify == "accepted", "dose-response estimate should verify")
    return SmokeResult(
        name="dose_response_estimate_verify",
        status="PASS",
        details={
            "kernel_status": result["status"],
            "query_verify": verify,
            "data_gap_verify": _verify_data_gap_state(result),
            "method": numeric_estimate["method"],
            "curve_points": len(curve),
            "first_x": curve[0]["x"],
            "last_x": curve[-1]["x"],
        },
    )


def _kb_transport_program() -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "aspirin", "domain": [True, False]},
            {
                "kind": "variable",
                "predicate": "heart_attack",
                "domain": [True, False],
            },
            {"kind": "variable", "predicate": "age"},
            {
                "kind": "cause",
                "from": _atom("aspirin"),
                "to": _atom("heart_attack"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "cause",
                "from": _atom("age"),
                "to": _atom("heart_attack"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "selection_node",
                "id": "S_age",
                "affects": _atom("age"),
                "source_population": "rct_aspirin_2020",
                "target_population": "user",
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("aspirin"), "value": True},
                    "target": {"atom": _atom("heart_attack"), "value": True},
                    "given": [],
                    "target_population": "user",
                },
            },
        ],
    }


def _typed_gap_from_json(gap: dict[str, Any]):
    from themis.types import (
        DataGap,
        GapBlocks,
        GapKind,
        GapProvenanceRef,
        GapRefKind,
        GapRequiredData,
        GapSeverity,
        RequiredDataType,
    )

    required_data = gap.get("required_data") or {}
    return DataGap(
        kind=GapKind(gap["kind"]),
        severity=GapSeverity(gap["severity"]),
        description=gap.get("description", ""),
        blocks=GapBlocks(gap.get("blocks", "point_estimate")),
        provenance=tuple(
            GapProvenanceRef(GapRefKind(ref["ref_kind"]), ref["ref_id"])
            for ref in gap.get("provenance", [])
        ),
        required_data=GapRequiredData(
            data_type=(
                RequiredDataType(required_data["data_type"])
                if required_data.get("data_type")
                else None
            ),
            population=required_data.get("population"),
            variables=tuple(required_data.get("variables", ())),
        ) if required_data else None,
    )


def smoke_kb_patch_loop() -> SmokeResult:
    from themis.kb import KBQueryKind, KBRegistry, gap_to_kb_query, kb_results_to_bundle
    from themis.kb.adapters.websearch_proxy import (
        ParsedSearchResult,
        WebSearchProxyAdapter,
        static_table_search,
    )

    program = _kb_transport_program()
    result = themis.run(program)["results"][0]
    gaps = result.get("data_gap_report", {}).get("gaps", [])
    transport_gap = next(
        gap for gap in gaps
        if gap["kind"] in (
            "transport_target_distribution_unknown",
            "transport_source_conditional_unknown",
        )
    )
    query = gap_to_kb_query(
        _typed_gap_from_json(transport_gap),
        target={
            "predicate": "heart_attack",
            "args": [{"type": "const", "name": "me"}],
            "value": True,
        },
        given=(
            {
                "predicate": "aspirin",
                "args": [{"type": "const", "name": "me"}],
                "value": True,
            },
        ),
        kb_hint="websearch_proxy",
    )
    _require(query is not None, "transport gap should translate to KBQuery")
    _require(
        query.query_kind in (
            KBQueryKind.STRATIFIED_SUBGROUP,
            KBQueryKind.TARGET_POPULATION_MARGINAL,
        ),
        "unexpected KB query kind",
    )

    adapter = WebSearchProxyAdapter(static_table_search({
        ("websearch_proxy", "heart_attack"): ParsedSearchResult(
            value=0.018,
            interval=(0.012, 0.026),
            sample_size=15000,
            citation="PMID:30146931",
            raw_response="Cochrane meta-analysis 2018...",
            confidence_grade="rct_meta_analysis",
        ),
    }))
    registry = KBRegistry()
    registry.register(adapter)
    found = registry.find(query)
    _require(found is adapter, "KB adapter was not registered")
    kb_result = found.query(query)
    _require(kb_result.success, "mock KB lookup failed")

    bundle = kb_results_to_bundle([kb_result])
    refreshed = themis.apply_patch_and_run(program, [bundle])
    refreshed_result = refreshed["results"][0]

    return SmokeResult(
        name="kb_patch_loop",
        status="PASS",
        details={
            "initial_status": result["status"],
            "gap_kind": transport_gap["kind"],
            "kb_query_kind": query.query_kind.value,
            "bundle_kind": bundle["kind"],
            "refreshed_status": refreshed_result["status"],
        },
    )


def smoke_mcp_wrapper() -> SmokeResult:
    from themis.mcp import build_server

    app = build_server()
    tool_names = {tool.name for tool in asyncio.run(app.list_tools())}
    resource_uris = {str(resource.uri) for resource in asyncio.run(app.list_resources())}

    expected_tools = {
        "themis_run",
        "themis_apply_patch_and_run",
        "themis_verify",
        "themis_verify_data_gap_report",
        "themis_verify_bounds_result",  # iter 133
        "themis_estimate",
        "themis_discover",
        "themis_submit_verdict",  # v0.1.5 Fix 2A
        "themis_list_resources",
    }
    _require(tool_names == expected_tools, "MCP tool catalog drifted")
    _require(
        "themis://prompts/response_rendering.md" in resource_uris,
        "missing response_rendering prompt resource",
    )
    _require(
        "themis://schemas/kb_result.schema.json" in resource_uris,
        "missing KB result schema resource",
    )

    fixture = ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json"
    program = json.loads(fixture.read_text(encoding="utf-8"))
    run_out = _call_mcp_tool(app, "themis_run", {"program": program})
    _require(run_out.get("results"), "MCP themis_run returned no results")

    verify_out = _call_mcp_tool(
        app,
        "themis_verify",
        {"program": program, "result": run_out["results"][0]},
    )
    _require(verify_out == {"ok": True}, "MCP themis_verify did not accept result")

    catalog = _call_mcp_tool(app, "themis_list_resources", {})
    _require(
        "themis://prompts/response_rendering.md" in catalog.get("prompts", []),
        "MCP resource catalog omitted response_rendering prompt",
    )

    diagnostic_result = themis.run(_dose_response_diagnostic_program())["results"][0]
    gap_verify = _call_mcp_tool(
        app,
        "themis_verify_data_gap_report",
        {"result": diagnostic_result},
    )
    _require(
        gap_verify == {"ok": True},
        "MCP data-gap verifier did not accept diagnostic result",
    )

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "dose_response.csv"
        _linear_dose_response_data().to_csv(csv_path, index=False)
        estimate_out = _call_mcp_tool(
            app,
            "themis_estimate",
            {
                "program": _dose_response_estimator_program(),
                "csv_path": str(csv_path),
                "options": {"model": "linear"},
            },
        )
    estimate_result = estimate_out["results"][0]
    numeric_estimate = estimate_result.get("numeric_estimate") or {}
    _require(
        estimate_result["status"] == "numerically_solved",
        "MCP themis_estimate did not solve numerically",
    )
    _require(
        numeric_estimate.get("method") == "dose_response_linear_dml",
        "MCP themis_estimate did not forward model='linear'",
    )

    return SmokeResult(
        name="mcp_wrapper",
        status="PASS",
        details={
            "tools": sorted(tool_names),
            "resources": len(resource_uris),
            "run_status": run_out["results"][0]["status"],
            "verify": "accepted",
            "data_gap_verify": "accepted",
            "estimate_method": numeric_estimate["method"],
        },
    )


SMOKES: tuple[Callable[[], SmokeResult], ...] = (
    smoke_dose_response_diagnostic,
    smoke_transport_verify,
    smoke_dose_response_estimate,
    smoke_kb_patch_loop,
    smoke_mcp_wrapper,
)


def run_all() -> list[SmokeResult]:
    results: list[SmokeResult] = []
    for smoke in SMOKES:
        try:
            results.append(smoke())
        except Exception as exc:
            results.append(SmokeResult(
                name=smoke.__name__.removeprefix("smoke_"),
                status="FAIL",
                details={},
                error=f"{type(exc).__name__}: {exc}",
            ))
    return results


def _print_text(results: list[SmokeResult]) -> None:
    print("Themis 0.14 stabilization smoke")
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
