"""
Process eval cases 14-20 through themis.run and write output JSON files.
Run from project root: python docs/eval_set/real_llm_run_v2/_process_cases_14_20.py
"""
import json, os, traceback, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import themis

OUT_DIR = os.path.join(os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Kernel ASTs (produced by A1 v2 agent reasoning — see agent_observations below)
# ---------------------------------------------------------------------------

CASES = []

# ── Case 14 ── F11 temporal compression ────────────────────────────────────
# "熬夜真的会让第二天没精神吗？"
# Intent: cause ("会让" pure cause phrasing; no intervention-action cue)
# §3a check: direct mechanistic link (sleep deprivation → fatigue), no obvious
#             unmeasured common cause needed; direct edge emitted.
# §5 temporal: NL encodes an explicit t→t+1 lag (tonight→next morning).
#              DAG is atemporal; must declare kind=temporal compression.
CASES.append({
    "case_id": "14_late_night_tired_temporal",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late", "domain": [True, False]},
            {"kind": "variable", "predicate": "feels_tired_next_morning", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "stays_up_late", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "feels_tired_next_morning", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "stays_up_late", "args": [{"type": "const", "name": "me"}]},
                    "to":   {"predicate": "feels_tired_next_morning", "args": [{"type": "const", "name": "me"}]}
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "temporal",
                    "chosen": "atemporal_dag_flattening",
                    "alternatives": ["time_series_model"],
                    "reason": "NL 显式编码了一个 t→t+1 的时间滞后（今晚熬夜 → 第二天上午没精神）。DAG 语义是无时序的，把它压缩为 stays_up_late→feels_tired_next_morning 丢失了'次日'这个滞后含义。已将 per-night lag 压缩进单条边以保持可运行性，但此处声明该压缩。",
                    "disambiguation_ask": "我把'第二天没精神'这个时间滞后压缩进了 DAG 的单条边里。如果你关心具体几小时后的效应，需要换时序模型——你需要这样吗？"
                }
            ]
        }
    },
    "agent_observations": (
        "F11 temporal compression: NL contains an explicit next-morning lag "
        "(熬夜→第二天). §3a check passed — sleep-deprivation→fatigue is a "
        "direct mechanistic link with no obvious unmeasured common cause, so "
        "direct edge emitted. Query intent 'cause' chosen (pure causal phrasing "
        "'会让', no do-style intervention cue). §5 temporal ambiguity declared: "
        "atemporal DAG flattens the t→t+1 lag; downstream user should know the "
        "per-night timing was compressed out."
    ),
    "extracted_for_scoring": {
        "variables": ["stays_up_late", "feels_tired_next_morning"],
        "directed_edges": [["stays_up_late", "feels_tired_next_morning"]],
        "bidirected_edges": [],
        "ambiguities_declared": ["temporal"]
    }
})

# ── Case 15 ── F12 categorical-numeric ─────────────────────────────────────
# "如果我的血压现在是高…把每周运动量从「少」增加到「多」，血压能从高变到中或低吗？"
# Intent: effect — explicit intervention cue "从少增加到多" + "如果…能…吗"
# Problem: user specifies three-level categorical domains for both variables.
#          Kernel only supports bool domain → must collapse to bool.
#          Must NOT silently drop the level-pair framing; declare ambiguity.
# Edge: exercise_amount → blood_pressure_level (common knowledge, direct).
CASES.append({
    "case_id": "15_bp_exercise_categorical",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "exercises_regularly", "domain": [True, False]},
            {"kind": "variable", "predicate": "blood_pressure_controlled", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "exercises_regularly", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "blood_pressure_controlled", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "blood_pressure_controlled", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "intervention": {
                        "atom": {"predicate": "exercises_regularly", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "given": []
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "categorical_domain",
                    "chosen": "bool_collapse",
                    "alternatives": ["three_level_categorical"],
                    "reason": (
                        "用户明确指定了三档分类域（运动量：少/中/多；血压：低/中/高），"
                        "并提出从「少→多」的干预，目标是血压从「高→中或低」。"
                        "当前 kernel 只支持 bool 域，无法表达三档对比。"
                        "已将运动量折叠为 exercises_regularly=True（对应「多」档），"
                        "血压折叠为 blood_pressure_controlled=True（对应「中或低」档），"
                        "丢失了中间档的区分。"
                    ),
                    "disambiguation_ask": (
                        "你的问题涉及三档分类变量（少/中/多，低/中/高），"
                        "但我目前只能用 是/否 两档来近似。"
                        "这个近似对你够用吗？还是你需要精确的三档对比？"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "F12 categorical-numeric: user specifies three-level domains for both "
        "exercise_amount (少/中/多) and blood_pressure_level (低/中/高). The "
        "kernel only supports bool domain. Per A1 v2 rules, predicates must be "
        "bool; collapsed exercise_amount→exercises_regularly and "
        "blood_pressure_level→blood_pressure_controlled. This drops the explicit "
        "level-pair framing (少→多, 高→{中,低}). Declared ambiguity "
        "kind=categorical_domain in extensions. Prompt gap noted: no explicit §2 "
        "or §5 rule for categorical domains — improvised a 'categorical_domain' "
        "kind analogous to the existing structural ambiguity kinds."
    ),
    "extracted_for_scoring": {
        "variables": ["exercises_regularly", "blood_pressure_controlled"],
        "directed_edges": [["exercises_regularly", "blood_pressure_controlled"]],
        "bidirected_edges": [],
        "ambiguities_declared": ["categorical_domain"]
    }
})

# ── Case 16 ── F15 selection bias ───────────────────────────────────────────
# Narrative: "在住院病人中，糖尿病患者的比例明显高于一般人群。"
# Question:  "所以住院会增加得糖尿病的风险吗？"
# §3a trigger: "在住院病人中" = conditioning on a selection variable.
#   is_hospitalized is a COLLIDER (underlying_illness → hospitalized AND
#   underlying_illness → has_diabetes). Must NOT emit is_hospitalized → has_diabetes.
# Intent: cause ("会增加…的风险吗" — pure causal phrasing, no action/intervention).
# Proposed confounder: underlying_illness_severity → is_hospitalized
#                       underlying_illness_severity → has_diabetes
# Declare selection_bias ambiguity.
CASES.append({
    "case_id": "16_hospital_diabetes_selection_bias",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "is_hospitalized", "domain": [True, False]},
            {"kind": "variable", "predicate": "has_diabetes", "domain": [True, False]},
            {"kind": "variable", "predicate": "underlying_illness_severity", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "underlying_illness_severity", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "is_hospitalized", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "cause",
                "from": {"predicate": "underlying_illness_severity", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "has_diabetes", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "is_hospitalized", "args": [{"type": "const", "name": "me"}]},
                    "to":   {"predicate": "has_diabetes", "args": [{"type": "const", "name": "me"}]}
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "selection_bias",
                    "chosen": "confounder_structure_underlying_illness",
                    "alternatives": ["direct_edge_hospitalized_to_diabetes"],
                    "reason": (
                        "叙述在住院病人中观察到糖尿病比例高，但住院本身是一个"
                        "碰撞节点（collider）：潜在疾病严重程度同时导致住院和糖尿病。"
                        "在住院病人中观察（即条件化于 is_hospitalized=True）会打开"
                        "collider 路径，制造虚假的统计相关——这是经典的选择偏差，"
                        "不是因果效应。已拒绝直接边 is_hospitalized→has_diabetes，"
                        "改为提出共同原因结构：underlying_illness_severity→两者。"
                    ),
                    "disambiguation_ask": (
                        "住院病人里糖尿病比例高，很可能是因为病情较重的人同时更容易"
                        "住院也更容易有糖尿病（选择偏差），而不是住院本身导致糖尿病。"
                        "你是想探讨这个混淆结构，还是仍然坚持询问住院是否'直接'导致糖尿病？"
                    )
                },
                {
                    "kind": "confounder_refusal",
                    "chosen": "underlying_illness_severity_as_confounder",
                    "alternatives": ["is_hospitalized_directly_causes_has_diabetes"],
                    "reason": "§3a: clinical/ICU setting pattern — sicker patients are selected into hospital, making is_hospitalized a collider not a cause. Direct edge refused.",
                    "disambiguation_ask": "我没有画 is_hospitalized→has_diabetes 的直接边，因为住院是一个选择变量。你同意这个判断吗？"
                }
            ]
        }
    },
    "agent_observations": (
        "F15 selection bias: narrative conditions on hospitalization (在住院病人中), "
        "then question asks if hospitalization causes diabetes. §3a clinical-setting "
        "pattern fires: is_hospitalized is a collider (underlying_illness_severity "
        "causes both). Refused direct is_hospitalized→has_diabetes edge. Proposed "
        "confounder structure: underlying_illness_severity → is_hospitalized and "
        "underlying_illness_severity → has_diabetes. Query still asks cause(is_hospitalized, "
        "has_diabetes) so themis can run (both atoms enter V via the confounder edges). "
        "Declared both selection_bias and confounder_refusal in extensions.ambiguities. "
        "Prompt gap: §3a lists 'selection effect' as a trigger but doesn't name "
        "selection_bias as an explicit ambiguity kind — improvised by analogy with "
        "confounder_refusal."
    ),
    "extracted_for_scoring": {
        "variables": ["is_hospitalized", "has_diabetes", "underlying_illness_severity"],
        "directed_edges": [
            ["underlying_illness_severity", "is_hospitalized"],
            ["underlying_illness_severity", "has_diabetes"]
        ],
        "bidirected_edges": [],
        "ambiguities_declared": ["selection_bias", "confounder_refusal"]
    }
})

# ── Case 17 ── F16 counterfactual ───────────────────────────────────────────
# "如果当初我选的是计算机专业，现在收入会更高吗？"
# Intent: effect ("如果…会更高吗" — intervention cue, maps to do(chose_cs=True)).
#         But "如果当初" signals unit-level counterfactual (Layer 3, not Layer 2).
# §3a: direct knowledge-based edge chose_cs_major → higher_current_income (plausible).
#      No obvious confounding pattern to reject here.
# Declare counterfactual_query: kernel only supports Layer 2 interventional effect,
#   not individual-level counterfactual.
CASES.append({
    "case_id": "17_career_choice_counterfactual",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_current_income", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "chose_cs_major", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "higher_current_income", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "higher_current_income", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "intervention": {
                        "atom": {"predicate": "chose_cs_major", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "given": []
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "counterfactual_query",
                    "chosen": "interventional_effect_proxy",
                    "alternatives": ["unit_level_counterfactual"],
                    "reason": (
                        "'如果当初我选的是…' 是 Pearl 第三层（反事实/孪生网络）问题："
                        "在已知我实际选了历史专业的情况下，假设我当时选了计算机，"
                        "现在的收入会如何？这是个体层面的反事实，不等于总体层面的"
                        "干预效应 P(higher_income|do(cs_major=True))。"
                        "当前 kernel 只支持第二层（干预效应），已用干预查询作为代理。"
                    ),
                    "disambiguation_ask": (
                        "你的问题是'如果当初我选了 CS，我现在会怎样'——这是一个"
                        "个体反事实问题，而我能给出的最好答案是：'在一般人群中，"
                        "选 CS 专业的人收入更高的概率是多少'（总体干预效应）。"
                        "这个代理答案对你够用吗？"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "F16 counterfactual: '如果当初我选的是计算机专业' is a unit-level "
        "counterfactual (Pearl Layer 3), not a population interventional effect "
        "(Layer 2). A1 v2 prompt has no explicit rule for this pattern. "
        "Improvised: emit effect query as the closest supported proxy "
        "(do(chose_cs_major=True) interventional effect), and declare "
        "kind=counterfactual_query explaining the semantic gap. Direct edge "
        "chose_cs_major→higher_current_income emitted (common knowledge, plausible). "
        "No confounder refusal needed — no §3a pattern triggered."
    ),
    "extracted_for_scoring": {
        "variables": ["chose_cs_major", "higher_current_income"],
        "directed_edges": [["chose_cs_major", "higher_current_income"]],
        "bidirected_edges": [],
        "ambiguities_declared": ["counterfactual_query"]
    }
})

# ── Case 18 ── F17 mechanism vs existence ──────────────────────────────────
# "吸烟为什么会导致肺癌？"
# Intent: cause — "为什么会导致" presupposes the causal link exists and asks
#         for the mechanism. Conservative default: cause query (existence-of-path).
# §3a: smoking→lung cancer is the canonical "confident direct edge" example
#      explicitly given in §3a text: "如果你确信因果关系直接且不可混淆
#      （例如吸烟→肺癌）". Emit direct edge.
# Declare mechanism_vs_existence: "为什么" asks for mediator chain,
#   kernel only answers existence-of-path.
CASES.append({
    "case_id": "18_smoking_mechanism_vs_existence",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "smokes", "domain": [True, False]},
            {"kind": "variable", "predicate": "has_lung_cancer", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "smokes", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "has_lung_cancer", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "smokes", "args": [{"type": "const", "name": "me"}]},
                    "to":   {"predicate": "has_lung_cancer", "args": [{"type": "const", "name": "me"}]}
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "mechanism_vs_existence",
                    "chosen": "existence_of_causal_path",
                    "alternatives": ["mechanism_mediator_chain"],
                    "reason": (
                        "'为什么' 问的是机制（中介链：吸烟→焦油→DNA 损伤→基因突变→肺癌），"
                        "不是因果路径是否存在（后者已被预设为真）。"
                        "当前 kernel 的 cause 查询只回答因果路径是否存在（第一层/第二层），"
                        "无法枚举生物机制中介链。已用存在性查询作为代理。"
                    ),
                    "disambiguation_ask": (
                        "你问的是'为什么'，是想了解吸烟导致肺癌的生物机制（如焦油、"
                        "DNA 损伤等中间步骤），还是确认这条因果关系存在？"
                        "如果是前者，我需要在图里显式加入中介变量，但这超出当前分析范围。"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "F17 mechanism vs existence: '为什么会导致' presupposes the causal link "
        "and asks for the mechanism. A1 v2 prompt §3a explicitly cites "
        "smoking→lung cancer as the canonical confident-direct-edge example, so "
        "direct edge emitted without confounder refusal. Query kind=cause (conservative "
        "default: existence-of-path as proxy for mechanism). Declared "
        "kind=mechanism_vs_existence: kernel answers existence, not mediator-chain "
        "enumeration. Prompt gap: no explicit §5 signal word for '为什么'; improvised "
        "by treating it as a structural out-of-scope query."
    ),
    "extracted_for_scoring": {
        "variables": ["smokes", "has_lung_cancer"],
        "directed_edges": [["smokes", "has_lung_cancer"]],
        "bidirected_edges": [],
        "ambiguities_declared": ["mechanism_vs_existence"]
    }
})

# ── Case 19 ── F18 individual vs population ────────────────────────────────
# Narrative: "这种降压药在临床试验里平均降压 10 mmHg。"
# Question:  "这药对我有效吗？"
# Intent: effect — "对我有效吗" + "这药" is intervention-style.
# §3a: takes_drug → blood_pressure_drops is direct (narrative confirms it).
# Declare individual_vs_population: narrative gives population average E[Y(1)-Y(0)];
#   question asks individual Y_i(1)-Y_i(0).
CASES.append({
    "case_id": "19_drug_individual_vs_population",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "takes_drug", "domain": [True, False]},
            {"kind": "variable", "predicate": "blood_pressure_drops", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "takes_drug", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "blood_pressure_drops", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "narrative"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "blood_pressure_drops", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "intervention": {
                        "atom": {"predicate": "takes_drug", "args": [{"type": "const", "name": "me"}]},
                        "value": True
                    },
                    "given": []
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "individual_vs_population",
                    "chosen": "population_average_effect_proxy",
                    "alternatives": ["individual_level_effect"],
                    "reason": (
                        "叙述提供了人群平均效应（临床试验平均降压 10 mmHg），"
                        "但问题问的是个体层面效应（'对我有效吗'）。"
                        "E[Y(1)-Y(0)]（人群平均）≠ Y_i(1)-Y_i(0)（个体）。"
                        "个体效应还依赖年龄、合并症、基因等在叙述中未提供的调节变量。"
                        "已用人群效应作为代理答案，但此处声明这一语义差距。"
                    ),
                    "disambiguation_ask": (
                        "临床试验结果是人群平均效应（平均降压 10 mmHg），"
                        "不能直接等同于'这药一定对你有效'。"
                        "你的具体情况（年龄、合并症、用药史等）会影响个体疗效。"
                        "你是想了解人群平均效应，还是想评估你个人的情况？"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "F18 individual vs population: narrative supplies population-average effect "
        "(临床试验平均降压 10 mmHg); question asks individual-level efficacy (对我有效吗). "
        "Edge source set to 'narrative' since the narrative explicitly states a causal "
        "effect. Effect query emitted (intervention cue '这药'). Declared "
        "kind=individual_vs_population: kernel returns population-average proxy; "
        "individual-level prediction requires moderator variables not supplied. "
        "Prompt gap: no explicit A1 v2 rule for individual vs population — improvised "
        "by analogy with scope ambiguity (§5)."
    ),
    "extracted_for_scoring": {
        "variables": ["takes_drug", "blood_pressure_drops"],
        "directed_edges": [["takes_drug", "blood_pressure_drops"]],
        "bidirected_edges": [],
        "ambiguities_declared": ["individual_vs_population"]
    }
})

# ── Case 20 ── F3 + F8 + F15 compound ──────────────────────────────────────
# Narrative: "最近十年某地区的移民数量增加了，同时本地失业率也在上升。"
# Question:  "所以移民多了会导致本地人失业吗？"
# §3a trigger: "最近十年…同时…上升" = temporal co-occurrence / group-level correlation.
#              Likely common cause: economic_conditions (recession, policy change,
#              industry shifts) → both high_immigration AND high_local_unemployment.
#              Refuse direct edge per §3a.
# Intent: "会导致…吗" — could be cause (is there a causal link) or effect
#         (quantify the impact). Conservative default: cause.
# §5 declarations: confounder_refusal + intent ambiguity.
CASES.append({
    "case_id": "20_immigration_unemployment_compound",
    "produced_kernel_ast": {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "options": {"strict_framing": False},
        "statements": [
            {"kind": "variable", "predicate": "high_immigration", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_local_unemployment", "domain": [True, False]},
            {"kind": "variable", "predicate": "adverse_economic_conditions", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "adverse_economic_conditions", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "high_immigration", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "cause",
                "from": {"predicate": "adverse_economic_conditions", "args": [{"type": "const", "name": "me"}]},
                "to":   {"predicate": "high_local_unemployment", "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"}
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "high_immigration", "args": [{"type": "const", "name": "me"}]},
                    "to":   {"predicate": "high_local_unemployment", "args": [{"type": "const", "name": "me"}]}
                }
            }
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "confounder_refusal",
                    "chosen": "adverse_economic_conditions_as_confounder",
                    "alternatives": ["high_immigration_directly_causes_high_local_unemployment"],
                    "reason": (
                        "§3a 触发：叙述描述了十年间两个时间趋势的共同变动，"
                        "这是典型的'时间滞后而无机制'模式（时序共现）。"
                        "经济周期、政策变化、产业结构变化等共同原因可以同时解释"
                        "移民增加和失业率上升，无需直接因果边。"
                        "已拒绝直接边 high_immigration→high_local_unemployment，"
                        "改为提出 adverse_economic_conditions 作为共同原因。"
                    ),
                    "disambiguation_ask": (
                        "我没有直接画移民→失业的边，因为这两个趋势很可能都被"
                        "经济环境（如经济下行、政策变化）驱动，而不是移民直接导致失业。"
                        "你同意这个判断吗？还是你有证据表明存在直接因果关系？"
                    )
                },
                {
                    "kind": "intent",
                    "chosen": "cause",
                    "alternatives": ["effect"],
                    "reason": (
                        "'会导致…吗' 既可读为因果存在性查询（cause）——移民是否是失业的原因，"
                        "也可读为干预效应查询（effect）——移民增加会使失业率上升多少。"
                        "保守默认选 cause。"
                    ),
                    "disambiguation_ask": (
                        "你是想问移民是否会'导致'失业（因果存在性），"
                        "还是想问移民增加'会使'失业率上升多少（干预效应量）？"
                    )
                }
            ]
        }
    },
    "agent_observations": (
        "F3+F8+F15 compound: §3a group-level/temporal-co-occurrence pattern fires "
        "(十年间两个趋势同时上升 → typical confounded correlation). Refused direct "
        "high_immigration→high_local_unemployment edge; emitted confounder structure "
        "adverse_economic_conditions → both. §5 intent ambiguity: '会导致…吗' admits "
        "cause (existence) vs effect (quantity) readings; picked cause as conservative "
        "default. Both confounder_refusal and intent ambiguities declared. Note: "
        "query still asks cause(high_immigration, high_local_unemployment) so "
        "themis can run; both atoms enter V via the confounder edges. subject is "
        "region-level not person-level, but kernel requires 'me' object — kept as-is "
        "since the prompt doesn't provide a region-scope object kind."
    ),
    "extracted_for_scoring": {
        "variables": ["high_immigration", "high_local_unemployment", "adverse_economic_conditions"],
        "directed_edges": [
            ["adverse_economic_conditions", "high_immigration"],
            ["adverse_economic_conditions", "high_local_unemployment"]
        ],
        "bidirected_edges": [],
        "ambiguities_declared": ["confounder_refusal", "intent"]
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
