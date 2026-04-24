"""
Process eval cases 21-22 through themis.run and write output JSON files.
Run from project root: python docs/eval_set/real_llm_run_v2/_process_cases_21_22.py
"""
import json, os, traceback, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import themis

OUT_DIR = os.path.join(os.path.dirname(__file__))


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


CASES = []

# ── Case 21 ── F19 IV identification (valid IV — Mendelian randomization) ────
# Narrative: "血清胆固醇和心脏病相关。肥胖/饮食等生活方式是未观测混杂。
#             特定基因变异影响肝脏合成胆固醇，只通过胆固醇影响心脏病，
#             不直接影响心脏病也不和生活方式相关。"
# Question: "血清胆固醇升高是否导致心脏病？能用基因变异作工具变量来识别吗？"
#
# Intent: §3b fires — narrative explicitly proposes gene_variant as IV candidate
#   ("只通过胆固醇影响心脏病"). Gold query kind is "identify".
# §3b extraction:
#   1. gene_variant → high_cholesterol  (IV1 relevance, narrative)
#   2. high_cholesterol → heart_disease (main path, common knowledge)
#   3. high_cholesterol ↔ heart_disease (bidirected: lifestyle is unobserved confounder)
#   4. NO gene_variant → heart_disease  (IV2 exclusion: narrative explicitly prohibits)
# Query: identify P(heart_disease | do(high_cholesterol=True))
# Extensions: iv_validity ambiguity with all three IV assumptions stated
#
# Expected themis.run: structurally_solved via iv_identification
#   (backdoor fails — latent confounder blocks it;
#    front-door fails — no observed mediator;
#    IV fires with gene_variant)
CASES.append({
    "case_id": "21_mendelian_randomization_iv",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "gene_variant", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_cholesterol", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_disease", "domain": [True, False]},
            # IV1: gene_variant → high_cholesterol (relevance — narrative states gene
            #      affects hepatic cholesterol synthesis)
            {
                "kind": "cause",
                "from": _atom("gene_variant"),
                "to": _atom("high_cholesterol"),
                "annotations": {"source": "narrative"}
            },
            # Main path: high_cholesterol → heart_disease
            {
                "kind": "cause",
                "from": _atom("high_cholesterol"),
                "to": _atom("heart_disease"),
                "annotations": {"source": "llm_proposal"}
            },
            # Unobserved confounder (lifestyle/obesity/diet): high_cholesterol ↔ heart_disease
            # Per §3b rule 4: emit bidirected edge for ADMG (not a U variable per §3a)
            {
                "kind": "bidirected",
                "left": _atom("high_cholesterol"),
                "right": _atom("heart_disease"),
                "annotations": {"source": "narrative"}
            },
            # NOTE: NO gene_variant → heart_disease edge (IV2 exclusion restriction)
            # Query: identify P(heart_disease | do(high_cholesterol=True))
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "identify",
                    "intervention": {"atom": _atom("high_cholesterol"), "value": True},
                    "target": _atom("heart_disease"),
                    "given": []
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "iv_validity",
                    "instrument": "gene_variant",
                    "assumptions": {
                        "IV1_relevance": "gene_variant affects high_cholesterol (narrative: 影响肝脏合成胆固醇)",
                        "IV2_exclusion": "gene_variant affects heart_disease ONLY via high_cholesterol — no direct path. Narrative explicitly states '只通过胆固醇影响心脏病，不直接影响心脏病'. No gene_variant→heart_disease edge emitted.",
                        "IV3_independence": "gene_variant is independent of the lifestyle confounder — narrative states '不和生活方式相关'. This is the Mendelian randomization assumption; challengeable if pleiotropy exists."
                    },
                    "notes": "All three IV assumptions are asserted by the narrative. Response layer should surface them explicitly so the user can challenge each assumption — especially IV3 (pleiotropic effects are a known threat to Mendelian randomization).",
                    "disambiguation_ask": "这个基因变异被假设满足三个工具变量条件：(IV1) 它影响胆固醇；(IV2) 它只通过胆固醇影响心脏病（无直接路径）；(IV3) 它与生活方式混杂因素无关。其中 IV3（独立性）在多效性（pleiotropy）存在时会被违反——这种情况在孟德尔随机化研究中是已知威胁。你同意这三个假设吗？"
                }
            ]
        }
    },
    "agent_observations": (
        "Case 21 (Mendelian randomization IV): §3b fires — narrative explicitly "
        "names gene_variant as IV candidate ('只通过胆固醇影响心脏病'). "
        "Extraction: gene_variant → high_cholesterol (IV1, source=narrative); "
        "high_cholesterol → heart_disease (main path, llm_proposal); "
        "high_cholesterol ↔ heart_disease (bidirected ADMG edge — lifestyle is "
        "unobserved confounder, per §3b rule 4: emit bidirected not a U variable). "
        "Critically: NO gene_variant → heart_disease edge emitted — IV2 exclusion "
        "requires this, and narrative explicitly states it. "
        "Query kind=identify (gold says 'identify'; IV dispatch requires identify "
        "query to route through backdoor→front-door→IV fallback chain). "
        "Expected: backdoor fails (latent confounder high_cholesterol↔heart_disease "
        "blocks all deconfounding sets); front-door fails (no observed mediator — "
        "high_cholesterol→heart_disease is direct); IV fires with gene_variant. "
        "Declared iv_validity with all three assumptions (IV1/IV2/IV3) so response "
        "layer can surface them. Prompt note: §3b explicitly says to emit "
        "extensions.ambiguities[kind=iv_validity] — rule is clear and followed."
    ),
    "extracted_for_scoring": {
        "variables": ["gene_variant", "high_cholesterol", "heart_disease"],
        "directed_edges": [
            ["gene_variant", "high_cholesterol"],
            ["high_cholesterol", "heart_disease"]
        ],
        "bidirected_edges": [["high_cholesterol", "heart_disease"]],
        "ambiguities_declared": ["iv_validity"]
    }
})

# ── Case 22 ── F19 IV identification (INVALID IV — IV2 violation) ─────────────
# Narrative: "想估教育对收入的因果效应。家庭背景是未观测混杂。
#             有人提议用'离学校远近'作为工具变量——距离远→上学难度大→教育少。
#             但是：距离远的地方往往是偏远农村，社区经济水平本身就低，
#             这可能通过非教育路径（如就业机会）影响收入。"
# Question: "'距离学校远近'作为教育→收入因果效应的工具变量，能成立吗？"
#
# Intent: §3b fires — distance_to_school is proposed as IV candidate
# §3b extraction:
#   1. distance_to_school → high_education  (IV1 relevance candidate, narrative)
#   2. high_education → high_income         (main path, common knowledge)
#   3. high_education ↔ high_income         (bidirected: family background unobserved)
#   4. community_economic_level → distance_to_school  (narrative: 偏远农村经济水平低)
#   5. community_economic_level → high_income          (narrative: 非教育路径影响收入)
#
# The community_economic_level variable creates an ALTERNATIVE PATH from
# distance_to_school to high_income:
#   distance_to_school ← community_economic_level → high_income
# This violates IV2 (exclusion restriction): distance affects income via
# community_economic_level, not only via education.
#
# Expected themis.run: IV should FAIL (distance_to_school is not a valid IV)
#   because there is a backdoor path through community_economic_level from
#   distance_to_school to high_income. Result should be needs_investigation
#   (not structurally_solved via iv_identification).
CASES.append({
    "case_id": "22_distance_school_iv_violation",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "distance_to_school", "domain": [True, False]},
            {"kind": "variable", "predicate": "community_economic_level", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_education", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_income", "domain": [True, False]},
            # distance_to_school → high_education (IV1 candidate: narrative)
            {
                "kind": "cause",
                "from": _atom("distance_to_school"),
                "to": _atom("high_education"),
                "annotations": {"source": "narrative"}
            },
            # high_education → high_income (main path: common knowledge)
            {
                "kind": "cause",
                "from": _atom("high_education"),
                "to": _atom("high_income"),
                "annotations": {"source": "llm_proposal"}
            },
            # high_education ↔ high_income (bidirected: family background unobserved)
            {
                "kind": "bidirected",
                "left": _atom("high_education"),
                "right": _atom("high_income"),
                "annotations": {"source": "narrative"}
            },
            # community_economic_level → distance_to_school
            # (narrative: 偏远农村经济水平低 → 距离远)
            # This edge is the IV2 violation setup: community_level causes distance
            {
                "kind": "cause",
                "from": _atom("community_economic_level"),
                "to": _atom("distance_to_school"),
                "annotations": {"source": "narrative"}
            },
            # community_economic_level → high_income
            # (narrative: 通过非教育路径（如就业机会）影响收入)
            # This is the IV2 violation: alternative path distance←community→income
            {
                "kind": "cause",
                "from": _atom("community_economic_level"),
                "to": _atom("high_income"),
                "annotations": {"source": "narrative"}
            },
            # Query: identify P(high_income | do(high_education=True))
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "identify",
                    "intervention": {"atom": _atom("high_education"), "value": True},
                    "target": _atom("high_income"),
                    "given": []
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "iv_validity",
                    "instrument": "distance_to_school",
                    "iv2_violation": True,
                    "iv2_violation_path": "distance_to_school ← community_economic_level → high_income",
                    "notes": (
                        "IV2 exclusion restriction is VIOLATED. The narrative explicitly states "
                        "that community_economic_level (偏远农村经济水平) causes both "
                        "distance_to_school (偏远 → 距离远) and high_income (通过就业机会). "
                        "This creates an alternative path from the proposed instrument "
                        "(distance_to_school) to the outcome (high_income) that bypasses "
                        "the treatment (high_education). Therefore distance_to_school does "
                        "NOT satisfy IV2, and IV identification must be refused."
                    ),
                    "disambiguation_ask": (
                        "'距离学校远近'作为工具变量不成立：社区经济水平同时影响'距离远近'和'收入'，"
                        "形成了工具变量→结果的替代路径（distance_to_school←community_economic_level→high_income），"
                        "违反了 IV2 排他性限制。如果你能控制/测量社区经济水平，"
                        "距离可能在条件化后成为有效工具变量——但需要对 community_economic_level 进行测量和调整。"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "Case 22 (Distance-to-school IV violation): §3b fires — distance_to_school "
        "is proposed as IV for high_education → high_income. "
        "Following the task instruction: DO NOT hide community_economic_level. "
        "Extraction: distance_to_school → high_education (IV1 candidate); "
        "high_education → high_income (main path); "
        "high_education ↔ high_income (bidirected — family background unobserved); "
        "community_economic_level → distance_to_school (narrative: 偏远农村经济水平低); "
        "community_economic_level → high_income (narrative: 非教育路径影响收入). "
        "The community_economic_level variable exposes IV2 violation: there is an "
        "alternative path distance_to_school ← community_economic_level → high_income "
        "that connects the proposed instrument to the outcome bypassing education. "
        "In the IV validity check, distance_to_school is NOT independent of high_income's "
        "determinants — community_economic_level is an observed common cause. "
        "Expected: IV dispatch tries distance_to_school as instrument; finds that "
        "community_economic_level → distance_to_school means distance is not "
        "independent of high_income (via community path) → IV3/IV2 violation → "
        "IV identification must fail → needs_investigation returned. "
        "Declared iv_validity with iv2_violation=True and the exact violation path. "
        "Prompt gap note: §3b says 'do NOT emit Z→Y edge to be safe' and focuses "
        "on the case where IV is valid. For the invalid-IV case, the correct action "
        "is to expose the IV2-violating structure (community_economic_level edges) "
        "rather than silently omitting it — this is consistent with §3b's emphasis "
        "on not hiding information, and with the task instruction to expose the violation."
    ),
    "extracted_for_scoring": {
        "variables": ["distance_to_school", "community_economic_level", "high_education", "high_income"],
        "directed_edges": [
            ["distance_to_school", "high_education"],
            ["high_education", "high_income"],
            ["community_economic_level", "distance_to_school"],
            ["community_economic_level", "high_income"]
        ],
        "bidirected_edges": [["high_education", "high_income"]],
        "ambiguities_declared": ["iv_validity"]
    }
})

# ---------------------------------------------------------------------------
# Run all cases through themis.run and write output files
# ---------------------------------------------------------------------------

for case in CASES:
    case_id = case["case_id"]
    ast = case["produced_kernel_ast"]
    themis_output = None
    themis_error = None

    try:
        result = themis.run(ast)
        themis_output = result
    except Exception as e:
        themis_error = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        print(f"[ERROR] {case_id}: {themis_error}", file=sys.stderr)

    out = {
        "case_id": case_id,
        "produced_kernel_ast": ast,
        "themis_run_output": themis_output,
        "themis_error": themis_error,
        "agent_observations": case["agent_observations"],
        "extracted_for_scoring": case["extracted_for_scoring"]
    }

    out_path = os.path.join(OUT_DIR, f"{case_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] wrote {out_path}")
