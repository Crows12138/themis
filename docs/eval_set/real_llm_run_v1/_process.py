"""Process 10 eval cases with produced kernel_asts and run themis on each.

Run: PYTHONPATH=. python docs/eval_set/real_llm_run_v1/_process.py
"""
import json
import os
import sys
import traceback

import themis

OUT_DIR = "docs/eval_set/real_llm_run_v1"
os.makedirs(OUT_DIR, exist_ok=True)


def atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def var(pred, **framing):
    d = {"kind": "variable", "predicate": pred, "domain": [True, False]}
    d.update(framing)
    return d


def cause(frm, to):
    return {
        "kind": "cause",
        "from": atom(frm),
        "to": atom(to),
        "annotations": {"source": "llm_proposal"},
    }


def bidirected(a, b):
    return {
        "kind": "bidirected",
        "left": atom(a),
        "right": atom(b),
        "annotations": {"source": "llm_proposal"},
    }


def q_effect(target, intervention):
    return {
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "effect",
            "target": {"atom": atom(target), "value": True},
            "intervention": {"atom": atom(intervention), "value": True},
            "given": [],
        },
    }


def q_effect_val(target, tv, intervention, iv):
    return {
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "effect",
            "target": {"atom": atom(target), "value": tv},
            "intervention": {"atom": atom(intervention), "value": iv},
            "given": [],
        },
    }


def q_cause(frm, to):
    return {"kind": "query", "id": "q", "query": {"kind": "cause", "from": atom(frm), "to": atom(to)}}


def q_assoc(left, right):
    return {
        "kind": "query",
        "id": "q",
        "query": {"kind": "assoc", "left": atom(left), "right": atom(right), "given": []},
    }


def program(statements):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": statements,
    }


# ---- Case 01: narrative=null, "跑步能减肥吗" — effect (default tiebreak)
case01 = program([
    var("running"),
    var("weight_loss"),
    cause("running", "weight_loss"),
    q_effect("weight_loss", "running"),
])
obs01 = (
    "No explicit intervention marker in the question; applied A1 default tiebreaker "
    "(prefer effect for 'will doing X lead to Y' phrasing). All framing fields left blank "
    "since the question gave none."
)

# ---- Case 02: narrative about daily VitD past month, colds fewer past 2 months.
# A5 extracts vitamin_d_supplement (daily, past month, self-report) and
# cold_frequency_reduced (past 2 months, self-report count).
# Question "维生素 D 真的能减少感冒吗" — effect (will taking X reduce Y).
case02 = program([
    var(
        "vitamin_d_supplement",
        time_window="past 1 month",
        threshold="daily",
        measurement="self-report of supplementation",
        observability="self-report",
    ),
    var(
        "cold_frequency_reduced",
        time_window="past 2 months",
        measurement="self-report count of cold episodes",
        observability="self-report",
    ),
    cause("vitamin_d_supplement", "cold_frequency_reduced"),
    q_effect("cold_frequency_reduced", "vitamin_d_supplement"),
])
obs02 = (
    "A5 extracted two narrative variables with explicit time windows and self-report "
    "observability. Picked effect (question asks whether the intervention reduces colds). "
    "Did not merge narrative+question predicates — they already shared names."
)

# ---- Case 03: "咖啡和失眠有关系吗" — correlation phrasing -> assoc
case03 = program([
    var("drinking_coffee"),
    var("insomnia"),
    cause("drinking_coffee", "insomnia"),
    q_assoc("drinking_coffee", "insomnia"),
])
obs03 = (
    "'有关系吗' is the correlation-phrasing cue per A1 table -> assoc. Still emitted a "
    "plausible cause edge (coffee -> insomnia) as llm_proposal. Framing left blank."
)

# ---- Case 04: chain question, "... 导致 ... 这条链可信吗" — cause
# One query only per prompt; predicates are all four mentioned;
# direct edges are the three link steps.
case04 = program([
    var("chronic_stress"),
    var("overeating"),
    var("obesity"),
    var("diabetes"),
    cause("chronic_stress", "overeating"),
    cause("overeating", "obesity"),
    cause("obesity", "diabetes"),
    q_cause("chronic_stress", "diabetes"),
])
obs04 = (
    "Chain '压力 -> 暴饮暴食 -> 肥胖 -> 糖尿病'. Used cause intent ('导致'). Emitted the "
    "three chain edges as llm_proposal; did NOT add a direct chronic_stress->diabetes "
    "shortcut since the question specified the route via mediators."
)

# ---- Case 05: narrative about latent genetic caffeine sensitivity; question "喝咖啡能让人更专注吗".
# A5: narrative describes a mechanism (third-person / biological), not the user's own habit —
# per A5 rules I don't extract a genetic_caffeine_sensitivity variable (and the prompt says don't
# name unobservables as observed predicates). But 'drinks_coffee' and 'alertness' are mentioned as
# concepts in the narrative; however they're described abstractly, not framed as the user's habit.
# I'll leave A5 output empty and let A1 drive it.
# A1 on question: effect; predicates drinks_coffee, stays_focused. No mention of alertness in
# question, so I won't invent it (A1 says don't invent intermediates).
case05 = program([
    var("drinking_coffee"),
    var("stays_focused"),
    cause("drinking_coffee", "stays_focused"),
    q_effect("stays_focused", "drinking_coffee"),
])
obs05 = (
    "Question phrased as 'will doing X lead to Y' -> effect (default tiebreak). A1 prompt "
    "forbids inventing intermediates the user didn't mention, so alertness is excluded. "
    "A1 prompt also doesn't describe bidirected-edge emission, and A5 doesn't produce edges, "
    "so the narrative's latent-genetic hint is not captured in this strict-prompt run."
)

# ---- Case 06: narrative says 慢跑 (jogging) with clear cadence; question says 跑步 (running).
# A5 extracts jogging with framing. A1 extracts running, is_healthier.
# I keep them as distinct predicates (jogging vs running) — A5 naming rule didn't tell me to
# unify, and the A5 prompt emphasizes not hallucinating. Merge: three predicates.
case06 = program([
    var(
        "jogging",
        time_window="past 3 months",
        threshold=">=4 sessions/week, 30 min each",
        measurement="self-report of sessions",
        observability="self-report",
    ),
    var("running"),
    var("is_healthier"),
    cause("running", "is_healthier"),
    q_effect("is_healthier", "running"),
])
obs06 = (
    "Narrative predicate 'jogging' (慢跑) kept distinct from question predicate 'running' "
    "(跑步) because A5/A1 prompts don't describe alias merging. jogging retains framing "
    "from narrative; running/is_healthier have no framing (question gave none). Picked "
    "effect per default tiebreak."
)

# ---- Case 07: "不吃早餐会影响学习效率吗" — negation.
# Naive A1 reading: predicates 'not_eating_breakfast' and 'study_efficiency'.
# Pick effect (will doing X affect Y -> effect per default).
case07 = program([
    var("skipping_breakfast"),
    var("study_efficiency"),
    cause("skipping_breakfast", "study_efficiency"),
    q_effect("study_efficiency", "skipping_breakfast"),
])
obs07 = (
    "Extracted 'skipping_breakfast' as-is from '不吃早餐' (naive LLM would not collapse "
    "negation into eats_breakfast=False without explicit prompt guidance). Picked effect."
)

# ---- Case 08: narrative about ice cream sales and drowning in summer; question "吃冰激凌会导致溺水吗".
# A5: narrative is third-person statistical pattern, not user's habit -> return no variables.
# A1: cause intent (导致). Predicates ice_cream_consumption, drowning.
case08 = program([
    var("eating_ice_cream"),
    var("drowning"),
    cause("eating_ice_cream", "drowning"),
    q_cause("eating_ice_cream", "drowning"),
])
obs08 = (
    "A5 returned empty (narrative is a third-person statistical pattern, not a first-person "
    "habit). A1 picked cause ('导致'). Strict prompt gives no mechanism to refuse a causal edge "
    "for a classic confounded pair, so the naive direct edge is emitted as llm_proposal."
)

# ---- Case 09: "吸烟会导致肺癌吗" — cause. smoking -> lung_cancer.
case09 = program([
    var("smoking"),
    var("lung_cancer"),
    cause("smoking", "lung_cancer"),
    q_cause("smoking", "lung_cancer"),
])
obs09 = (
    "'导致' -> cause intent. Emitted smoking -> lung_cancer as llm_proposal. "
    "No framing because the question gave none."
)

# ---- Case 10: narrative '进入冬天后办公室里感冒的人变多'; question '冷天会让人更容易生病吗'.
# A5: narrative again is third-person observation not first-person habit -> no variables.
# (Could arguably frame 'cold_weather' with time_window 'winter', but narrative doesn't say the
#  user's own state; keep empty to be conservative per A5's 'don't hallucinate framing' rule.)
# A1: 'X 会让人 Y 吗' — default tiebreak -> effect. Predicates cold_weather, gets_sick.
case10 = program([
    var("cold_weather"),
    var("gets_sick"),
    cause("cold_weather", "gets_sick"),
    q_effect("gets_sick", "cold_weather"),
])
obs10 = (
    "A5 returned empty (narrative describes an observed office-wide pattern, not the user's "
    "own state). A1 picked effect per default tiebreak ('会让人 Y 吗'). Did not capture "
    "population-scope mismatch — strict A1 prompt has no such mechanism."
)


CASES = [
    ("01_running_weight_loss_underframed", case01, obs01),
    ("02_vitamin_d_narrative_edge", case02, obs02),
    ("03_coffee_insomnia_ambiguous", case03, obs03),
    ("04_stress_chain_diabetes", case04, obs04),
    ("05_coffee_alertness_admg", case05, obs05),
    ("06_running_jogging_alias", case06, obs06),
    ("07_skip_breakfast_negation", case07, obs07),
    ("08_ice_cream_drowning_confounded", case08, obs08),
    ("09_smoking_lung_cancer_structural", case09, obs09),
    ("10_cold_weather_sick_directional", case10, obs10),
]


def extract_for_scoring(ast):
    vars_ = []
    directed = []
    bidir = []
    for s in ast["statements"]:
        k = s["kind"]
        if k == "variable":
            vars_.append(s["predicate"])
        elif k == "cause":
            directed.append([s["from"]["predicate"], s["to"]["predicate"]])
        elif k == "bidirected":
            bidir.append([s["left"]["predicate"], s["right"]["predicate"]])
    return {"variables": vars_, "directed_edges": directed, "bidirected_edges": bidir}


summary_lines = []
succ = 0
err = 0

for cid, ast, obs in CASES:
    run_out = None
    run_err = None
    try:
        res = themis.run(ast)
        # normalize serializable
        res_json = json.loads(json.dumps(res, default=str))
        run_out = res_json.get("results", [None])[0]
        succ += 1
    except Exception as e:
        run_err = f"{type(e).__name__}: {e}"
        err += 1

    out_obj = {
        "case_id": cid,
        "produced_kernel_ast": ast,
        "themis_run_output": run_out,
        "themis_error": run_err,
        "agent_observations": obs,
        "extracted_for_scoring": extract_for_scoring(ast),
    }
    out_path = os.path.join(OUT_DIR, f"{cid}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)
    status = "ok" if run_err is None else f"ERR({run_err[:60]})"
    qk = ast["statements"][-1]["query"]["kind"]
    summary_lines.append(f"{cid}: {status} / {qk}")

print(f"OK={succ} ERR={err}")
for ln in summary_lines:
    print(ln)
