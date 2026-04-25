"""
Phase 7+8 stress test — process eval cases 25-28 (data-bearing) through
themis.run / themis.estimate using sub-agent-produced kernel_ast.

Run from project root:
    python docs/eval_set/real_llm_run_v3/_process_cases_25_28.py
"""
import json, os, sys, traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import numpy as np
import pandas as pd
import themis

OUT_DIR = os.path.dirname(__file__)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# Sub-agent outputs (verbatim, with the ambiguity entries normalised to
# kernel_ast.schema.json's narrow shape — agents added rich nested fields
# that the schema rejects; we preserve agent intent in agent_observations).

CASES = []

# ---- Case 25 -----------------------------------------------------------------
CASES.append({
    "case_id": "25_medication_bp_backdoor_numeric",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "takes_medication", "domain": [True, False]},
            {"kind": "variable", "predicate": "systolic_bp", "domain": [True, False]},
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("takes_medication"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("age"), "to": _atom("systolic_bp"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("takes_medication"), "to": _atom("systolic_bp"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("takes_medication"), "value": True},
                "target": {"atom": _atom("systolic_bp"), "value": True},
                "given": [],
            }},
        ],
    },
    "data_fn": lambda seed=0, n=2000: (
        lambda rng: pd.DataFrame({
            "age": rng.uniform(40, 80, n),
            "takes_medication": rng.random(n) < (1 / (1 + np.exp(-0.1 * (rng.uniform(40, 80, n) - 60)))),
            "systolic_bp": 0.8 * rng.uniform(40, 80, n) + 80
                + (-10.0) * (rng.random(n) < 0.5).astype(float)
                + rng.standard_normal(n) * 5,
        })
    )(np.random.default_rng(seed)),
    "agent_observations": (
        "Case 25: agent correctly identified backdoor on age. KEY ISSUE: "
        "agent declared continuous outcome systolic_bp as bool per §2 default — "
        "this loses semantic meaning (mmHg ATE collapses to bool prob diff). "
        "Agent flagged this as 'categorical_compression' ambiguity but the "
        "prompt has no convenient way to encode 'this is continuous'. "
        "Real prompt gap: §2 default to bool is wrong for clearly continuous "
        "outcomes like mmHg / income / weight. Recommend prompt v2.6 add §2d "
        "for continuous detection cues (单位 / 数值范围)."
    ),
    "agent_prompt_gaps": [
        "§2 default-to-bool is wrong for continuous outcomes (mmHg / years / kg)",
        "No way to express 'leave dtype unspecified, infer from data column dtype'",
    ],
})

# ---- Case 26 -----------------------------------------------------------------
CASES.append({
    "case_id": "26_smoking_tar_cancer_frontdoor_numeric",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "tar_deposit", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("tar_deposit"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("tar_deposit"), "to": _atom("lung_cancer"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "bidirected", "left": _atom("smoking"), "right": _atom("lung_cancer"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("smoking"), "value": True},
                "target": {"atom": _atom("lung_cancer"), "value": True},
                "given": [],
            }},
        ],
    },
    "data_fn": lambda seed=0, n=3000: (
        lambda rng: (lambda u, smoke, tar: pd.DataFrame({
            "smoking": smoke, "tar_deposit": tar,
            "lung_cancer": rng.random(n) < (1 / (1 + np.exp(-(2 * tar.astype(float) + 2 * u - 2)))),
        }))(
            rng.standard_normal(n),
            (lambda u: rng.random(n) < (1 / (1 + np.exp(-u))))(rng.standard_normal(n)),
            None,  # placeholder — actual flow below
        )
    )(np.random.default_rng(seed)),
    "agent_observations": (
        "Case 26: agent emitted classic Pearl front-door structure "
        "(smoking→tar→cancer + smoking↔cancer bidirected). NO spurious "
        "smoking→cancer direct edge. Variable name divergence from gold "
        "(tar_deposit vs tar, lung_cancer vs cancer) — cosmetic. "
        "KEY OBSERVATION: agent correctly noted the prompt is silent on "
        "the front-door encoding choice (bidirected vs U variable) — "
        "they picked bidirected because §3b pattern matched. Prompt v2.7 "
        "should add explicit §3d 'front-door encoding choice'."
    ),
    "agent_prompt_gaps": [
        "§3 doesn't say bidirected vs U variable for front-door scenarios",
    ],
})

# Re-do case 26 data deterministically (the lambda above is broken; rewrite cleanly):
def _case_26_data(seed=0, n=3000):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    smoking = rng.random(n) < (1 / (1 + np.exp(-u)))
    tar = rng.random(n) < (1 / (1 + np.exp(-(2 * smoking.astype(float) - 1))))
    cancer = rng.random(n) < (1 / (1 + np.exp(-(2 * tar.astype(float) + 2 * u - 2))))
    return pd.DataFrame({"smoking": smoking, "tar_deposit": tar, "lung_cancer": cancer})
CASES[-1]["data_fn"] = lambda: _case_26_data()

# ---- Case 27 -----------------------------------------------------------------
CASES.append({
    "case_id": "27_gene_cholesterol_heart_iv_numeric",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "gene_variant", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_cholesterol", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_disease", "domain": [True, False]},
            {"kind": "cause", "from": _atom("gene_variant"), "to": _atom("high_cholesterol"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("high_cholesterol"), "to": _atom("heart_disease"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "bidirected", "left": _atom("high_cholesterol"), "right": _atom("heart_disease"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("high_cholesterol"), "value": True},
                "target": {"atom": _atom("heart_disease"), "value": True},
                "given": [],
            }},
        ],
    },
    "data_fn": None,
    "agent_observations": (
        "Case 27: textbook §3b application. Agent emitted IV1 edge (gene→chol), "
        "main path (chol→heart), bidirected (chol↔heart latent lifestyle). "
        "Critically: NO gene→heart direct edge (would violate IV2). "
        "Monotonicity correctly flagged in iv_validity ambiguity. "
        "Variable names match gold exactly. No prompt gaps."
    ),
    "agent_prompt_gaps": [],
})

def _case_27_data(seed=0, n=5000):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    gene = rng.random(n) < 0.5
    chol = rng.random(n) < (1 / (1 + np.exp(-(1.5 * gene.astype(float) - 0.5 + 0.5 * u))))
    heart = rng.random(n) < (1 / (1 + np.exp(-(1.0 * chol.astype(float) + 1.5 * u - 1))))
    return pd.DataFrame({
        "gene_variant": gene,
        "high_cholesterol": chol,
        "heart_disease": heart,
    })
CASES[-1]["data_fn"] = lambda: _case_27_data()

# ---- Case 28 -----------------------------------------------------------------
# Agent introduced an explicit `unobserved_health_behavior` variable —
# this is semantically problematic because U is supposed to be unobserved
# (no data column). For dispatch, we'd hit a DataContractError. Save
# both the as-produced ast (for documentation) AND a normalised version
# without U (gold-aligned) to actually run.
CASES.append({
    "case_id": "28_aspirin_heart_e_value_sensitivity",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "takes_aspirin_daily", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_attack", "domain": [True, False]},
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "variable", "predicate": "unobserved_health_behavior", "domain": [True, False]},
            {"kind": "cause", "from": _atom("takes_aspirin_daily"), "to": _atom("heart_attack"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("age"), "to": _atom("takes_aspirin_daily"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("age"), "to": _atom("heart_attack"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("unobserved_health_behavior"), "to": _atom("takes_aspirin_daily"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("unobserved_health_behavior"), "to": _atom("heart_attack"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("takes_aspirin_daily"), "value": True},
                "target": {"atom": _atom("heart_attack"), "value": True},
                "given": [],
            }},
        ],
    },
    "data_fn": None,  # set below — has age, takes_aspirin_daily, heart_attack only
    "agent_observations": (
        "Case 28: TWO PROMPT GAPS exposed by sub-agent. (1) Agent introduced "
        "unobserved_health_behavior as a regular variable + emitted U→X, U→Y "
        "edges. This is wrong: §3a's 'introduce U' pattern is for cases where "
        "U is hypothetical, not when the user has data and U is genuinely "
        "missing. Better encoding would be bidirected X↔Y (ADMG) like §3b "
        "uses for IV scenarios. Result: themis.estimate will fail "
        "DataContractError because unobserved_health_behavior column is "
        "absent from data. (2) Agent correctly identified that there's no "
        "kernel_ast surface for 'compute E-value sensitivity' — invented a "
        "robustness_request ambiguity. The kernel actually does this "
        "automatically (Phase 8.2 auto-attaches E-value to all binary-outcome "
        "estimates), but the AGENT doesn't know this. Prompt v2.7 §3e should "
        "tell the agent 'when user worries about unmeasured confounders, "
        "DON'T introduce U — the kernel will surface E-value automatically'."
    ),
    "agent_prompt_gaps": [
        "§3a 'introduce U' rule misfires when U has no data column",
        "No prompt section telling agent that E-value is auto-attached",
    ],
    "normalised_ast": {
        # Agent-intent-preserving fix: drop unobserved_health_behavior
        # variable + edges; the kernel's E-value auto-attach will surface
        # robustness without the agent needing to encode it.
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "takes_aspirin_daily", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_attack", "domain": [True, False]},
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("takes_aspirin_daily"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("age"), "to": _atom("heart_attack"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("takes_aspirin_daily"), "to": _atom("heart_attack"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("takes_aspirin_daily"), "value": True},
                "target": {"atom": _atom("heart_attack"), "value": True},
                "given": [],
            }},
        ],
    },
})

def _case_28_data(seed=0, n=2000):
    rng = np.random.default_rng(seed)
    age = rng.uniform(40, 80, size=n)
    aspirin = rng.random(n) < (1 / (1 + np.exp(-0.05 * (age - 60))))
    p_heart = 1 / (1 + np.exp(-(0.04 * (age - 60) - 0.5 * aspirin.astype(float) - 1.5)))
    heart = rng.random(n) < p_heart
    return pd.DataFrame({"age": age, "takes_aspirin_daily": aspirin, "heart_attack": heart})
CASES[-1]["data_fn"] = lambda: _case_28_data()


# Helper for case 25 data (the lambda above is broken)
def _case_25_data(seed=0, n=2000):
    rng = np.random.default_rng(seed)
    age = rng.uniform(40, 80, size=n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    medication = rng.random(n) < p_med
    bp = 0.8 * age + 80 - 10.0 * medication.astype(float) + rng.standard_normal(n) * 5
    # Note: column named to match agent's variables, not gold
    return pd.DataFrame({
        "age": age, "takes_medication": medication, "systolic_bp": bp,
    })
CASES[0]["data_fn"] = lambda: _case_25_data()


# Run
for case in CASES:
    case_id = case["case_id"]
    ast = case.get("normalised_ast", case["produced_kernel_ast"])

    themis_output = None
    themis_error = None
    try:
        if case["data_fn"] is not None:
            df = case["data_fn"]()
            themis_output = themis.estimate(ast, df)
        else:
            themis_output = themis.run(ast)
    except Exception as e:
        themis_error = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)

    out = {
        "case_id": case_id,
        "produced_kernel_ast": case["produced_kernel_ast"],
        "normalised_ast": case.get("normalised_ast"),
        "themis_run_output": themis_output,
        "themis_error": themis_error,
        "agent_observations": case["agent_observations"],
        "agent_prompt_gaps": case["agent_prompt_gaps"],
    }
    out_path = os.path.join(OUT_DIR, f"{case_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"[{'OK' if themis_error is None else 'ERR'}] wrote {out_path}")
