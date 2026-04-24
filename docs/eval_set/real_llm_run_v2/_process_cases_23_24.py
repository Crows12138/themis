"""
Process eval cases 23-24 (Phase 6.mediation) through themis.run and write
output JSON files, recording what a blind sub-agent produced from A1 v2.3
§3c given only the NL + prompt (no gold access).

Run from project root:
    python docs/eval_set/real_llm_run_v2/_process_cases_23_24.py
"""
import json, os, sys, traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import themis

OUT_DIR = os.path.dirname(__file__)


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


CASES = []

# ── Case 23 ── F20 mediation decomposition (clean NDE/NIE) ───────────────────
# NL narrative: "每天跑步会减肥——一部分是直接消耗热量的作用，另一部分是跑步
#                改善了基础代谢，代谢改善再帮助减肥。没有其他影响代谢和体重
#                的变量被遗漏。"
# NL question: "跑步对减肥的效应里，有多少是通过代谢改善这条路径来的？
#               直接消耗热量的那部分有多大？"
#
# Sub-agent decision log (per §3c):
#   - Trigger = "X 的直接效应和间接效应各占多少" match → effect query with mediator
#   - Variables: running / metabolism_improved / weight_loss (§2 snake_case / me / bool)
#   - Edges: running→metabolism, metabolism→weight_loss, running→weight_loss
#     (direct calorie-burn + mediated path both named in narrative)
#   - No confounders (narrative explicitly rules out — "没有其他影响...的变量
#     被遗漏")
#   - mediator = metabolism_improved in query
#   - No ambiguities (matches §3c canonical example exactly)
#
# Expected themis.run: structurally_solved with strategy=nde_nie
CASES.append({
    "case_id": "23_running_metabolism_mediation",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "running", "domain": [True, False]},
            {"kind": "variable", "predicate": "metabolism_improved", "domain": [True, False]},
            {"kind": "variable", "predicate": "weight_loss", "domain": [True, False]},
            {"kind": "cause", "from": _atom("running"), "to": _atom("metabolism_improved"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("metabolism_improved"), "to": _atom("weight_loss"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("running"), "to": _atom("weight_loss"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("running"), "value": True},
                "target": {"atom": _atom("weight_loss"), "value": True},
                "given": [],
                "mediator": _atom("metabolism_improved"),
            }},
        ],
    },
    "agent_observations": (
        "Case 23 (clean mediation): §3c canonical example match almost verbatim. "
        "Trigger pattern '直接效应和间接效应各占多少' fires the mediator-based "
        "effect query. Extracted running / metabolism_improved / weight_loss as "
        "three variables. Emitted direct edge running→weight_loss (calorie burn) "
        "plus mediated path running→metabolism→weight_loss. No confounder refusal "
        "needed because narrative explicitly rules out additional variables. "
        "mediator field set on query. No §5 ambiguity — prompt says 'clean "
        "mediation structure' cases need no ambiguities. Expected kernel output: "
        "structurally_solved with strategy=nde_nie."
    ),
    "extracted_for_scoring": {
        "variables": ["running", "metabolism_improved", "weight_loss"],
        "directed_edges": [
            ["running", "metabolism_improved"],
            ["metabolism_improved", "weight_loss"],
            ["running", "weight_loss"],
        ],
        "mediator": "metabolism_improved",
        "ambiguities_declared": [],
    },
})


# ── Case 24 ── F20 mediation (intermediate confounder / recanting witness) ───
# NL narrative: "某降压药 → 降低血压 → 降低心脏病风险，但这个药同时也会引起
#                身体炎症反应，炎症水平本身既被药影响、又会推高血压、而且独立
#                影响心脏病风险。"
# NL question: "这个药对心脏病的直接作用（不通过血压）和通过血压的间接作用
#               各占多少？"
#
# Sub-agent decision log (per §3c "Intermediate-confounder hazard"):
#   - Trigger = "直接作用...和...间接作用各占多少" → effect with mediator
#   - Mediator = blood_pressure_elevated (explicit: 不通过血压 = direct)
#   - Variables: takes_antihypertensive_drug / blood_pressure_elevated /
#     inflammation_elevated / heart_disease
#   - Inflammation EXTRACTED (not silently omitted) — narrative names all three
#     of its causal roles, and §3c says "emit the structure faithfully and
#     flag" when intermediate confounder is present
#   - Edges: drug→bp, bp→heart (main path); drug→inflammation, inflammation→bp,
#     inflammation→heart (intermediate confounder structure)
#   - ambiguity: mediation_intermediate_confounder, variable=inflammation_elevated
#
# Expected themis.run: structurally_solved with strategy=none
#   (NDE/NIE fails M3 or M4; CDE fails C1 or C2 — agent note:
#    "inflammation sits on a drug→inflammation→heart path that cannot be
#    blocked without also blocking part of the mediated effect")
#
# Note: sub-agent chose "blood_pressure_elevated" as the variable name whereas
# the gold file uses "blood_pressure_lowered". This is a cosmetic framing
# divergence — the graph structure and kernel behavior are identical. Either
# direction name is defensible when a `direction` framing field is absent.
CASES.append({
    "case_id": "24_drug_inflammation_mediation_violation",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "takes_antihypertensive_drug", "domain": [True, False]},
            {"kind": "variable", "predicate": "blood_pressure_elevated", "domain": [True, False]},
            {"kind": "variable", "predicate": "inflammation_elevated", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_disease", "domain": [True, False]},
            {"kind": "cause", "from": _atom("takes_antihypertensive_drug"),
             "to": _atom("blood_pressure_elevated"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("blood_pressure_elevated"),
             "to": _atom("heart_disease"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("takes_antihypertensive_drug"),
             "to": _atom("inflammation_elevated"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("inflammation_elevated"),
             "to": _atom("blood_pressure_elevated"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("inflammation_elevated"),
             "to": _atom("heart_disease"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("takes_antihypertensive_drug"), "value": True},
                "target": {"atom": _atom("heart_disease"), "value": True},
                "given": [],
                "mediator": _atom("blood_pressure_elevated"),
            }},
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "mediation_intermediate_confounder",
                    "variable": "inflammation_elevated",
                    "notes": (
                        "炎症 is a drug-descendant that also affects both the "
                        "mediator (blood pressure) and the outcome (heart disease) "
                        "— the canonical recanting-witness pattern. NDE/NIE are "
                        "not identified under Pearl 2001's four conditions (M4 "
                        "violated), and simple backdoor-based CDE also fails. "
                        "Advanced methods (g-formula) may identify CDE in Phase 7+."
                    ),
                }
            ]
        },
    },
    "agent_observations": (
        "Case 24 (intermediate-confounder case): §3c 'Intermediate-confounder "
        "hazard' rule fires cleanly. Recognized inflammation as a drug-descendant "
        "that also affects both the mediator (blood pressure) and the outcome. "
        "Faithfully encoded the full five-edge structure rather than silently "
        "dropping inflammation. Declared mediation_intermediate_confounder "
        "ambiguity citing the recanting-witness pattern. Variable naming diverges "
        "from gold: sub-agent used 'blood_pressure_elevated' + "
        "'takes_antihypertensive_drug' where gold uses 'blood_pressure_lowered' + "
        "'drug'. Structural content identical. "
        "Expected kernel output: structurally_solved with strategy=none, "
        "nde_nie.failed_condition in {M3, M4}, cde.failed_condition in {C1, C2}."
    ),
    "extracted_for_scoring": {
        "variables": [
            "takes_antihypertensive_drug", "blood_pressure_elevated",
            "inflammation_elevated", "heart_disease",
        ],
        "directed_edges": [
            ["takes_antihypertensive_drug", "blood_pressure_elevated"],
            ["blood_pressure_elevated", "heart_disease"],
            ["takes_antihypertensive_drug", "inflammation_elevated"],
            ["inflammation_elevated", "blood_pressure_elevated"],
            ["inflammation_elevated", "heart_disease"],
        ],
        "mediator": "blood_pressure_elevated",
        "ambiguities_declared": ["mediation_intermediate_confounder"],
    },
})


# --- Run all and write outputs -------------------------------------------------

for case in CASES:
    case_id = case["case_id"]
    ast = case["produced_kernel_ast"]
    themis_output = None
    themis_error = None

    try:
        themis_output = themis.run(ast)
    except Exception as e:
        themis_error = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)

    out = {
        "case_id": case_id,
        "produced_kernel_ast": ast,
        "themis_run_output": themis_output,
        "themis_error": themis_error,
        "agent_observations": case["agent_observations"],
        "extracted_for_scoring": case["extracted_for_scoring"],
    }
    path = os.path.join(OUT_DIR, f"{case_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] wrote {path}")
