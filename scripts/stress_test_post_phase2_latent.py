"""Post-Phase-2.latent stress test.

Run six hand-constructed (NL question, kernel_ast) pairs through
themis.run and collect structured findings. Each question targets a
dimension the first stress test (task #33, docs/trial_reports/
a1_to_40_stress_test.md) didn't cover:

    1. pure cause query (structural-only, no theta needed)
    2. categorical (non-bool) domain
    3. effect with non-empty given (conditional subpopulation)
    4. multi-hop chain (4 variables, 3 edges) — does front-door fire?
    5. ADMG hidden-confounder (post-Phase-2.latent, newly supported)
    6. ambiguous cause / assoc intent

This is not a real LLM-driven stress test (no API calls); the
author plays the role of a good A1 LLM and flags any place where
the constructed kernel_ast felt unnatural to produce from NL. The
findings get reported to docs/trial_reports/.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import themis


def _a(p: str, subj: str = "me") -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": subj}]}


@dataclass
class Case:
    id: str
    nl: str
    dimension: str
    ast: dict
    notes: str = ""


# =============================================================== cases

CASES: list[Case] = [
    Case(
        id="1_cause_structural",
        nl="吸烟会导致肺癌吗",
        dimension="cause query (structural only)",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
                {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
                {"kind": "cause", "from": _a("smoking"), "to": _a("lung_cancer"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "query", "id": "q",
                 "query": {"kind": "cause",
                           "from": _a("smoking"), "to": _a("lung_cancer")}},
            ],
        },
        notes="Pure structural. No theta, no framing fields, no CPT.",
    ),
    Case(
        id="2_categorical_domain",
        nl="血压水平（低/中/高）和运动量有关系吗",
        dimension="categorical (non-bool) domain + assoc",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "exercise_volume",
                 "domain": ["low", "medium", "high"]},
                {"kind": "variable", "predicate": "blood_pressure",
                 "domain": ["low", "medium", "high"]},
                {"kind": "cause", "from": _a("exercise_volume"), "to": _a("blood_pressure"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "query", "id": "q",
                 "query": {"kind": "assoc",
                           "left": _a("exercise_volume"),
                           "right": _a("blood_pressure"),
                           "given": []}},
            ],
        },
        notes="Categorical domain rather than bool. Stresses whether assoc on "
              "non-bool works end-to-end.",
    ),
    Case(
        id="3_conditional_effect",
        nl="对于糖尿病患者，减少糖分摄入能改善血糖吗",
        dimension="effect with non-empty given (subpopulation)",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "diabetic", "domain": [True, False]},
                {"kind": "variable", "predicate": "low_sugar_diet", "domain": [True, False]},
                {"kind": "variable", "predicate": "blood_sugar_improves", "domain": [True, False]},
                {"kind": "cause", "from": _a("diabetic"), "to": _a("low_sugar_diet"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _a("diabetic"), "to": _a("blood_sugar_improves"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _a("low_sugar_diet"), "to": _a("blood_sugar_improves"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "query", "id": "q",
                 "query": {
                     "kind": "effect",
                     "target": {"atom": _a("blood_sugar_improves"), "value": True},
                     "intervention": {"atom": _a("low_sugar_diet"), "value": True},
                     "given": [{"atom": _a("diabetic"), "value": True}],
                 }},
            ],
        },
        notes="Non-empty given. The A6 front-door currently only fires when "
              "given is empty; does this fall through gracefully?",
    ),
    Case(
        id="4_multi_hop_chain",
        nl="长期压力会通过暴饮暴食和肥胖导致糖尿病吗",
        dimension="4-variable chain (stress → overeating → obesity → diabetes)",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "chronic_stress", "domain": [True, False]},
                {"kind": "variable", "predicate": "overeating", "domain": [True, False]},
                {"kind": "variable", "predicate": "obesity", "domain": [True, False]},
                {"kind": "variable", "predicate": "diabetes", "domain": [True, False]},
                {"kind": "cause", "from": _a("chronic_stress"), "to": _a("overeating"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _a("overeating"), "to": _a("obesity"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _a("obesity"), "to": _a("diabetes"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "query", "id": "q",
                 "query": {
                     "kind": "effect",
                     "target": {"atom": _a("diabetes"), "value": True},
                     "intervention": {"atom": _a("chronic_stress"), "value": True},
                     "given": [],
                 }},
            ],
        },
        notes="3-edge chain. Does adjustment or front-door fire? Which mediator "
              "gets picked?",
    ),
    Case(
        id="5_admg_hidden_confounder",
        nl="喝咖啡能提神吗（基因型 U 未观测，既影响咖啡习惯也影响警觉性）",
        dimension="ADMG hidden confounder (post-Phase-2.latent)",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "drinks_coffee", "domain": [True, False]},
                {"kind": "variable", "predicate": "alertness", "domain": [True, False]},
                {"kind": "variable", "predicate": "stays_focused", "domain": [True, False]},
                {"kind": "cause", "from": _a("drinks_coffee"), "to": _a("alertness"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _a("alertness"), "to": _a("stays_focused"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "bidirected",
                 "left": _a("drinks_coffee"), "right": _a("stays_focused"),
                 "annotations": {"source": "llm_proposal",
                                 "confidence": 0.6}},
                {"kind": "query", "id": "q",
                 "query": {
                     "kind": "identify",
                     "target": _a("stays_focused"),
                     "intervention": {"atom": _a("drinks_coffee"), "value": True},
                     "given": [],
                 }},
            ],
        },
        notes="Hidden-U as bidirected. S3.a front-door should fire with "
              "alertness as mediator.",
    ),
    Case(
        id="6_ambiguous_cause_vs_assoc",
        nl="咖啡和失眠有关系吗",
        dimension="ambiguous intent — cause or assoc?",
        ast={
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "drinks_coffee", "domain": [True, False]},
                {"kind": "variable", "predicate": "has_insomnia", "domain": [True, False]},
                {"kind": "cause", "from": _a("drinks_coffee"), "to": _a("has_insomnia"),
                 "annotations": {"source": "llm_proposal"}},
                {"kind": "query", "id": "q",
                 "query": {"kind": "assoc",
                           "left": _a("drinks_coffee"),
                           "right": _a("has_insomnia"),
                           "given": []}},
            ],
        },
        notes="Chose assoc (user said '有关系'); but if user meant causation, "
              "A1 would pick cause. The prompt doesn't make this choice "
              "mechanically recoverable.",
    ),
]


# ================================================================ runner

def run_all() -> None:
    for case in CASES:
        print("=" * 72)
        print(f"[{case.id}] {case.nl}")
        print(f"dimension: {case.dimension}")
        print()
        try:
            out = themis.run(case.ast)
        except Exception as exc:
            print(f"!! RAISED {type(exc).__name__}: {exc}")
            print(f"note: {case.notes}")
            continue
        r = out["results"][0]
        print(f"status: {r['status']}")
        print(f"query_kind: {r['query_kind']}")
        if r.get("structural_result") is not None:
            print(f"structural_result.value: {r['structural_result']['value']}")
        if r.get("numeric_result") is not None:
            print(f"numeric_result: {r['numeric_result']}")
        if r.get("derivation") is not None:
            rules = [s["rule"] for s in r["derivation"]["steps"]]
            print(f"derivation rules: {rules}")
        mi = r.get("missing_information", [])
        if mi:
            print("missing_information:")
            for m in mi:
                print(f"  - [{m['priority']}] {m['kind']}:{m['name']}")
                if m.get("reason"):
                    print(f"      reason: {m['reason']}")
        ir = r.get("investigation_requests", [])
        if ir:
            print("investigation_requests:")
            for req in ir:
                print(f"  - {req['action']} / {req.get('group', '?')} ({req['priority']})")
                for it in req.get("items", []):
                    print(f"      target: {it['target']}")
        fn = r.get("framing_notes", [])
        if fn:
            print("framing_notes:")
            for note in fn:
                print(f"  - {note['predicate']}: missing={note['missing']}")
        print(f"note: {case.notes}")
        print()


if __name__ == "__main__":
    run_all()
