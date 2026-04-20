from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.output.explainer import explain
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import QueryStatement
DEFAULT_FIXTURES = [
    ROOT / "tests" / "test_e2e" / "fixtures" / "numeric_backdoor.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "numeric_backdoor_missing_parameter.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "probability_no_graph.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "identify_two_var.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "numeric_backdoor_confidence_mixed.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "tutoring_exam_complete.json",
    ROOT / "tests" / "test_e2e" / "fixtures" / "sleep_focus_complete.json",
]


def _short_formula(payload: dict) -> str:
    formula = payload.get("formula")
    if not formula:
        return "-"
    kind = formula.get("kind")
    if kind == "sum":
        return "sum(...)"
    if kind == "probability_ref":
        return "probability_ref(...)"
    if kind == "product":
        return "product(...)"
    return str(kind)


def _print_investigation(payload: dict) -> None:
    requests = payload.get("investigation_requests") or []
    if not requests:
        return
    print("  investigation:")
    for req in requests:
        print(
            f"    - action={req['action']} group={req.get('group')} "
            f"target={req['target']}"
        )
        for item in req.get("items", []):
            print(f"      item: {item['target']}")
            if "reason" in item:
                print(f"        reason: {item['reason']}")
            if "skeleton" in item:
                skeleton = item["skeleton"]
                sk_target = skeleton.get("target", {}).get("atom", {}).get("predicate")
                sk_given = [
                    g.get("atom", {}).get("predicate")
                    for g in skeleton.get("given", [])
                ]
                print(
                    "        skeleton: "
                    f"kind={skeleton.get('kind')} "
                    f"target={sk_target} given={sk_given}"
                )


def run_fixture(path: Path) -> None:
    ast = parse_json(path.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    ground = instantiate(program)
    graph = project(ground)
    stmt_by_id = {
        stmt.id: stmt for stmt in program.statements if isinstance(stmt, QueryStatement)
    }
    results = dispatch_all(program, graph)

    print(f"\n=== {path.name} ===")
    print(f"graph: nodes={graph.number_of_nodes()} edges={graph.number_of_edges()}")

    for result in results:
        payload = to_dict(result)
        stmt = stmt_by_id.get(result.query_id)
        print(
            f"- {result.query_id}: status={payload['status']} "
            f"kind={payload['query_kind']} "
            f"numeric={payload.get('numeric_result', {}).get('value')} "
            f"confidence={payload.get('confidence')} "
            f"formula={_short_formula(payload)}"
        )
        try:
            text = explain(result, stmt=stmt)
        except Exception as exc:  # pragma: no cover - manual tool
            text = f"<explainer failed: {type(exc).__name__}: {exc}>"
        print(f"  explain: {text}")

        if payload.get("missing_information"):
            print("  missing:")
            for m in payload["missing_information"]:
                print(f"    - {m['kind']} {m['name']}")
                if "reason" in m:
                    print(f"      reason: {m['reason']}")
        _print_investigation(payload)


def main(argv: list[str]) -> int:
    fixtures = [Path(arg).resolve() for arg in argv] if argv else DEFAULT_FIXTURES
    for path in fixtures:
        if not path.exists():
            print(f"[missing] {path}", file=sys.stderr)
            return 2
        run_fixture(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
