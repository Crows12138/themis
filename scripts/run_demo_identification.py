"""Three clean identification demo cases — the spine of the Themis demo.

Walks the full identification spectrum on hand-built, fully-framed DAGs:

1. **Backdoor** — observed confounder. do(X)→Y is point-identified by
   adjusting for the measured confounder. Themis also flags that "every
   confounder is measured" is itself an assumption (no bidirected edge
   declared) and recommends an E-value sensitivity analysis.
2. **Front-door** — an *unobserved* X↔Y common cause, but a fully
   mediating M. do(X)→Y is still point-identified through the front-door
   functional, despite the latent — the case where naive adjustment is
   impossible yet identification succeeds.
3. **Bow arc** — X→Y with an unobserved X↔Y common cause and no mediator.
   do(X)→Y is genuinely *not* point-identified; Themis returns a definitive
   "unidentifiable" with a Tian hedge witness, and falls back to
   assumption-free Manski bounds.

Each case asks two queries:

- an ``identify`` query — exposes the *strategy* (pattern + adjustment /
  mediator set + estimand, or the hedge proof of non-identifiability);
- an ``effect`` query — exposes the *data gap* (which distribution you'd
  need to actually compute it, plus the model-free Manski interval).

Every positive identification is round-tripped through the independent
verifier (``themis.verify``) so the demo shows the reasoning chain is
auditable, not merely asserted.

Run::

    python scripts/run_demo_identification.py          # narrated
    python scripts/run_demo_identification.py --json    # machine-readable

Exit code is non-zero if any case stops producing its expected
identification verdict — these three are the ground truth the
identification engine must keep reproducing.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import themis


# --------------------------------------------------------------- AST builders

def _atom(pred: str, obj: str = "me") -> dict[str, Any]:
    return {"predicate": pred, "args": [{"type": "const", "name": obj}]}


def _binvar(pred: str, measurement: str) -> dict[str, Any]:
    """A fully-framed binary variable, so the advisory framing channel stays
    silent and the effect query's data-gap report shows the *substantive*
    statistical gap rather than operationalization nags."""
    return {
        "kind": "variable",
        "predicate": pred,
        "domain": [True, False],
        "time_window": "study window",
        "measurement": measurement,
        "observability": "observed",
        "direction": "up",
        "baseline": "pre-intervention",
        "state_vs_event": "event",
    }


def _cause(frm: str, to: str) -> dict[str, Any]:
    # Edges are domain-asserted (the causal model is given), not LLM-proposed,
    # so the edge-provenance channel stays out of the identification story.
    return {
        "kind": "cause",
        "from": _atom(frm),
        "to": _atom(to),
        "annotations": {"source": "common_knowledge"},
    }


def _bidirected(left: str, right: str) -> dict[str, Any]:
    return {
        "kind": "bidirected",
        "left": _atom(left),
        "right": _atom(right),
        "annotations": {"source": "common_knowledge"},
    }


def _identify_query(target: str, intervention: str) -> dict[str, Any]:
    return {
        "kind": "query", "id": "identify",
        "query": {
            "kind": "identify",
            "target": _atom(target),
            "intervention": {"atom": _atom(intervention), "value": True},
            "given": [],
        },
    }


def _effect_query(target: str, intervention: str) -> dict[str, Any]:
    return {
        "kind": "query", "id": "effect",
        "query": {
            "kind": "effect",
            "target": {"atom": _atom(target), "value": True},
            "intervention": {"atom": _atom(intervention), "value": True},
            "given": [],
        },
    }


def _program(statements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ------------------------------------------------------------------- the cases

@dataclass(frozen=True)
class DemoCase:
    name: str
    headline: str
    dag: tuple[str, ...]
    program: dict[str, Any]
    target: str
    intervention: str
    # expected identify verdict
    expect_identified: bool
    expect_pattern: str | None = None
    expect_set_label: str | None = None          # "adjustment_set" / "mediator_set"
    expect_set_predicates: frozenset[str] = field(default_factory=frozenset)
    expect_hedge: bool = False
    # expected effect data-gap kinds (subset that must be present)
    expect_effect_gap_kinds: frozenset[str] = field(default_factory=frozenset)


BACKDOOR = DemoCase(
    name="backdoor",
    headline="Backdoor adjustment — observed confounder",
    dag=(
        "disease_severity → medication",
        "disease_severity → recovery",
        "medication → recovery",
    ),
    program=_program([
        _binvar("medication", "prescribed (yes/no)"),
        _binvar("recovery", "recovered within window (yes/no)"),
        _binvar("disease_severity", "severe at baseline (yes/no)"),
        _cause("disease_severity", "medication"),
        _cause("disease_severity", "recovery"),
        _cause("medication", "recovery"),
        _identify_query("recovery", "medication"),
        _effect_query("recovery", "medication"),
    ]),
    target="recovery",
    intervention="medication",
    expect_identified=True,
    expect_pattern="backdoor",
    expect_set_label="adjustment_set",
    expect_set_predicates=frozenset({"disease_severity"}),
    expect_effect_gap_kinds=frozenset({
        "missing_distribution",
        "unmeasured_confounder_risk",
        "answer_is_bounds_not_point_estimate",
    }),
)

FRONT_DOOR = DemoCase(
    name="front_door",
    headline="Front-door — identified despite an unobserved confounder",
    dag=(
        "smoking → tar",
        "tar → cancer",
        "smoking ↔ cancer   (unobserved common cause)",
    ),
    program=_program([
        _binvar("smoking", "smoker (yes/no)"),
        _binvar("tar", "lung tar deposit above clinical cutoff (yes/no)"),
        _binvar("cancer", "diagnosed (yes/no)"),
        _cause("smoking", "tar"),
        _cause("tar", "cancer"),
        _bidirected("smoking", "cancer"),
        _identify_query("cancer", "smoking"),
        _effect_query("cancer", "smoking"),
    ]),
    target="cancer",
    intervention="smoking",
    expect_identified=True,
    expect_pattern="front_door",
    expect_set_label="mediator_set",
    expect_set_predicates=frozenset({"tar"}),
    expect_effect_gap_kinds=frozenset({
        "missing_distribution",
        "front_door_identification_assumption_required",
        "answer_is_bounds_not_point_estimate",
    }),
)

BOW_ARC = DemoCase(
    name="bow_arc",
    headline="Bow arc — genuinely unidentifiable (hedge witness)",
    dag=(
        "treatment → outcome",
        "treatment ↔ outcome   (unobserved common cause)",
    ),
    program=_program([
        _binvar("treatment", "received (yes/no)"),
        _binvar("outcome", "positive outcome (yes/no)"),
        _cause("treatment", "outcome"),
        _bidirected("treatment", "outcome"),
        _identify_query("outcome", "treatment"),
        _effect_query("outcome", "treatment"),
    ]),
    target="outcome",
    intervention="treatment",
    expect_identified=False,
    expect_hedge=True,
    expect_effect_gap_kinds=frozenset({
        "unidentifiable_no_admissible_set",
        "answer_is_bounds_not_point_estimate",
    }),
)

CASES: tuple[DemoCase, ...] = (BACKDOOR, FRONT_DOOR, BOW_ARC)


# --------------------------------------------------------------------- running

@dataclass
class CaseReport:
    name: str
    status: str                       # PASS / FAIL
    details: dict[str, Any]
    failures: list[str] = field(default_factory=list)


def _result_by_id(results: list[dict], qid: str) -> dict:
    return next(r for r in results if r["query_id"] == qid)


def _predicate_set(labels: list[str]) -> frozenset[str]:
    # identification sets render predicates as "disease_severity(me)".
    return frozenset(label.split("(", 1)[0] for label in labels)


def _gap_kinds(result: dict) -> list[str]:
    report = result.get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", [])]


def _hedge_step(result: dict) -> dict | None:
    deriv = result.get("derivation") or {}
    steps = deriv.get("steps", []) if isinstance(deriv, dict) else []
    return next((s for s in steps if s.get("rule") == "tian_hedge_witness"), None)


def _missing_distribution(result: dict) -> str | None:
    for g in (result.get("data_gap_report") or {}).get("gaps", []):
        if g["kind"] == "missing_distribution":
            return g["description"]
    return None


def run_case(case: DemoCase) -> CaseReport:
    failures: list[str] = []
    out = themis.run(case.program)
    results = out["results"]
    ident = _result_by_id(results, "identify")
    effect = _result_by_id(results, "effect")

    structural_value = (ident.get("structural_result") or {}).get("value")
    if structural_value is not case.expect_identified:
        failures.append(
            f"identify value {structural_value!r} != expected "
            f"{case.expect_identified!r}"
        )

    identification = (ident.get("extensions") or {}).get("identification") or {}
    actual_set: frozenset[str] = frozenset()
    if case.expect_identified:
        if identification.get("pattern") != case.expect_pattern:
            failures.append(
                f"pattern {identification.get('pattern')!r} != "
                f"{case.expect_pattern!r}"
            )
        actual_set = _predicate_set(identification.get(case.expect_set_label, []))
        if actual_set != case.expect_set_predicates:
            failures.append(
                f"{case.expect_set_label} {set(actual_set)} != "
                f"{set(case.expect_set_predicates)}"
            )

    hedge = _hedge_step(ident)
    if case.expect_hedge and hedge is None:
        failures.append("expected a tian_hedge_witness step, found none")

    # Independent verifier must accept the identify derivation.
    verify_ok = True
    try:
        themis.verify(case.program, ident)
    except Exception as exc:  # noqa: BLE001 — demo surfaces any failure
        verify_ok = False
        failures.append(f"verify(identify) rejected: {type(exc).__name__}: {exc}")

    effect_gaps = set(_gap_kinds(effect))
    missing_gaps = case.expect_effect_gap_kinds - effect_gaps
    if missing_gaps:
        failures.append(
            f"effect missing expected gap kinds: {sorted(missing_gaps)}"
        )

    rows = effect.get("bounds_results") or []
    bounds = next(
        (b for b in rows if b.get("method") == "manski_natural"), None)
    if bounds is None:
        failures.append("effect query produced no Manski fallback bounds")

    details = {
        "identify_value": structural_value,
        "identification": identification,
        "adjustment_or_mediator": sorted(actual_set),
        "hedge_witness": bool(hedge),
        "verify": "accepted" if verify_ok else "rejected",
        "effect_status": effect["status"],
        "effect_gap_kinds": sorted(effect_gaps),
        "missing_distribution": _missing_distribution(effect),
        "bounds_methods": [b.get("method") for b in rows],
        "bounds_interval": (
            f'[{(bounds or {}).get("lower_expression")}, '
            f'{(bounds or {}).get("upper_expression")}]'
            if bounds else None
        ),
    }
    return CaseReport(
        name=case.name,
        status="PASS" if not failures else "FAIL",
        details=details,
        failures=failures,
    )


# ------------------------------------------------------------------- rendering

def _print_narrated(case: DemoCase, report: CaseReport) -> None:
    d = report.details
    print("=" * 72)
    print(f"[{report.status}] {case.name} — {case.headline}")
    print("=" * 72)
    print("  DAG:")
    for edge in case.dag:
        print(f"    {edge}")
    print()
    print(f"  Q1  identify  do({case.intervention}) → {case.target} ?")
    if case.expect_identified:
        label = "adjustment set" if case.expect_set_label == "adjustment_set" else "mediator set"
        print(f"      ✓ IDENTIFIED via {d['identification'].get('pattern')} "
              f"— {label} {{{', '.join(d['adjustment_or_mediator'])}}}")
    else:
        print("      ✗ NOT IDENTIFIABLE — no admissible point estimand")
        if d["hedge_witness"]:
            print("        proof: Tian hedge witness (Shpitser–Pearl Line 5)")
    print(f"      verifier: {d['verify'].upper()} "
          f"(independent replay of the derivation)")
    print()
    print(f"  Q2  effect  P({case.target}=true | do({case.intervention}=true)) ?")
    print(f"      status: {d['effect_status']}")
    if d["missing_distribution"]:
        print(f"      data needed: {d['missing_distribution']}")
    if d["bounds_interval"]:
        print(f"      assumption-free fallback ({d['bounds_method']}):")
        print(f"        {d['bounds_interval']}")
    print(f"      data-gap kinds: {', '.join(d['effect_gap_kinds'])}")
    if report.failures:
        print()
        print("  FAILURES:")
        for f in report.failures:
            print(f"    - {f}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    reports = [run_case(case) for case in CASES]

    if args.json:
        print(json.dumps(
            [{"name": r.name, "status": r.status,
              "details": r.details, "failures": r.failures} for r in reports],
            indent=2, ensure_ascii=False,
        ))
    else:
        print("\nThemis — identification demo (backdoor / front-door / bow arc)\n")
        for case, report in zip(CASES, reports):
            _print_narrated(case, report)
        passed = sum(r.status == "PASS" for r in reports)
        print(f"{passed}/{len(reports)} cases reproduced their expected verdict.")

    return 1 if any(r.status == "FAIL" for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
