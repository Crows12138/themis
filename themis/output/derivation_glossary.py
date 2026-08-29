"""What each derivation step did, in the reader's words.

Every answered result carries a derivation: an ordered list of steps, each
naming the rule that produced it, each independently re-checkable. That
list is the complete answer to "how was this arrived at" — it is the only
channel that has one for every path, and until now no surface read it.

The report's 「怎么算出来的」 section was bound to the ROUTE block family,
and a route is written as a block only by the identification patterns that
produce one. Everything else — a d-separation verdict, the Tian-Pearl
formulas, abduction-action-prediction — records what it did in
``step.rule`` and nowhere else, so for six query kinds the section that
exists to say how the answer was reached said nothing at all. The
verification section made it plainer: it told the reader the derivation has
N steps and never said what they were.

This is the sibling of :mod:`themis.output.assumption_glossary`, and it is
here for the same reason and with the same shape: the kernel emits
snake_case ids, the reader needs sentences, and the translation is data
rather than a chain of ``if``\\ s. It has the same default too — a rule
nobody has glossed surfaces as its own name rather than vanishing, because
on a surface whose whole job is disclosure the safe direction of error is
to over-report.

The entries say what the step DID, not what the verifier re-checks about
it: the reader is following a recipe, not auditing an audit. Where a step
touched the data rather than only the graph or θ, the sentence says so —
that distinction is load-bearing and no other line of the report carries
it. The linear-SCM pair is the clearest case: one path uses coefficients
the caller declared and the other fits them by per-node OLS, and which one
happened was previously recorded only in an ``estimated_from_data`` flag
that nothing read.

A test holds this table equal to the rules producers actually write, found
by walking every ``DerivationStep(rule=...)`` in the package — so a new
step cannot be added without saying what it does.
"""
from __future__ import annotations

from .. import language

#: Rule id → what that step did. Ordered roughly as a derivation runs:
#: graph checks, identification terminals, symbolic formulas, then the
#: numeric evaluations that touch data.
SAYS: dict[str, language.Words] = {
    # --- reading the graph ----------------------------------------------------
    "graph_is_dag": {"zh": "确认因果图无环",
                     "en": "confirm the causal graph is acyclic"},
    "d_separated": {"zh": "在图上确认两者在给定条件集下 d-分离（无关联通路）",
                    "en": "confirm on the graph that the two are d-separated "
                          "given the conditioning set (no open path between "
                          "them)"},
    "d_connected_via_open_path": {"zh": "在图上找出一条打开的路径，两者因此相关",
                                  "en": "find an open path on the graph, which "
                                        "is why the two are associated"},
    "cause_via_directed_path": {"zh": "在图上找出一条从原因到结果的有向路径",
                                "en": "find a directed path on the graph from "
                                      "cause to effect"},
    "no_directed_path": {"zh": "在图上确认不存在从原因到结果的有向路径",
                         "en": "confirm on the graph that no directed path "
                               "runs from cause to effect"},

    # --- recognising a pattern ------------------------------------------------
    "backdoor_criterion": {"zh": "在图上验证调整集满足后门准则：阻断全部后门路径，且不含处理的后代",
                           "en": "verify on the graph that the adjustment set "
                                 "satisfies the back-door criterion: it blocks "
                                 "every back-door path and contains no "
                                 "descendant of the treatment"},
    "joint_backdoor_criterion": {"zh": "在图上验证这一组处理的联合调整集有效（广义调整准则）",
                                 "en": "verify on the graph that the joint "
                                       "adjustment set for this group of "
                                       "treatments is valid (the generalized "
                                       "adjustment criterion)"},
    "front_door_criterion": {"zh": "在图上验证中介集满足前门准则",
                             "en": "verify on the graph that the mediator set "
                                   "satisfies the front-door criterion"},
    "iv_criterion_check": {"zh": "在图上验证所选工具变量满足 IV 准则",
                           "en": "verify on the graph that the chosen "
                                 "instrument satisfies the IV criterion"},
    "vector_iv_criterion_check": {"zh": "在图上验证这个工具变量对整组被干预的处理都有效（排他性与外生性）",
                                  "en": "verify on the graph that this "
                                        "instrument is valid for the whole "
                                        "group of treatments being intervened "
                                        "on (exclusion and exogeneity)"},
    "proximal_criterion": {"zh": "在图上验证近端识别条件（Miao model f：两个 proxy 与未测混杂的关系）",
                           "en": "verify the proximal identification "
                                 "conditions on the graph (Miao model f: how "
                                 "the two proxies relate to the unmeasured "
                                 "confounder)"},
    "general_id_criterion": {"zh": "用 general ID（Tian–Shpitser c-factor 分解）判定效应在 ADMG 上可点识别",
                             "en": "use general ID (the Tian-Shpitser c-factor "
                                   "decomposition) to decide whether the "
                                   "effect is point-identifiable on the ADMG"},
    "ctf_conjunction_criterion": {"zh": "用 ID*/IDC* 判定这个反事实合取在图上可点识别",
                                  "en": "use ID*/IDC* to decide whether this "
                                        "counterfactual conjunction is "
                                        "point-identifiable on the graph"},
    "s_admissibility_check": {"zh": "重导 S-可容许性（Bareinboim 定理 1）：选择节点在给定集合下与结果无关",
                              "en": "re-derive S-admissibility (Bareinboim "
                                    "Theorem 1): the selection node is "
                                    "independent of the outcome given the set"},
    "longitudinal_sequential_exchangeability_check":
        {"zh": "逐个时点重查顺序可交换性：每一步的处理在既往历史给定后可视为随机",
         "en": "re-check sequential exchangeability time point by time point: "
               "at each step the treatment can be treated as random given the "
               "history so far"},
    "mediation_nde_nie_check": {"zh": "验证 Pearl 2001 的四个条件，自然直接/间接效应可识别",
                                "en": "verify Pearl 2001's four conditions, so "
                                      "the natural direct and indirect effects "
                                      "are identifiable"},
    "mediation_nde_nie_joint_check":
        {"zh": "对整个中介集验证那四个条件（VanderWeele–Vansteelandt 2014 的向量版）",
         "en": "verify those four conditions for the whole mediator set (the "
               "vector version from VanderWeele-Vansteelandt 2014)"},
    "mediation_cde_check": {"zh": "验证受控直接效应 CDE(m) 的后门识别条件",
                            "en": "verify the back-door identification "
                                  "conditions for the controlled direct effect "
                                  "CDE(m)"},
    "mediation_cde_joint_check": {"zh": "验证把整个中介块固定住的联合 CDE 识别条件",
                                  "en": "verify the joint CDE identification "
                                        "conditions with the whole mediator "
                                        "block held fixed"},
    "tian_c_decomposition": {"zh": "在图上做 c-分解，把联合分布拆成各 c-分量的乘积",
                             "en": "run the c-decomposition on the graph, "
                                   "splitting the joint distribution into a "
                                   "product over c-components"},
    "tian_hedge_witness": {"zh": "在图上找到一个 hedge —— 该效应非参数不可点识别",
                           "en": "find a hedge on the graph — the effect is "
                                 "not non-parametrically point-identifiable"},
    "idc_rule2_exchange": {"zh": "做 IDC 规则 2 的观测-干预交换，把条件项挪进 do 里",
                           "en": "apply IDC rule 2's observation-intervention "
                                 "exchange, moving the conditioning term "
                                 "inside the do"},

    # --- concluding identification --------------------------------------------
    "identify_via_backdoor": {"zh": "据后门准则与相应公式，判定效应可识别",
                              "en": "decide the effect is identifiable, by the "
                                    "back-door criterion and its formula"},
    "identify_via_joint_backdoor": {"zh": "据联合后门准则，判定这一组处理的联合效应可识别",
                                    "en": "decide the joint effect of this "
                                          "group of treatments is "
                                          "identifiable, by the joint "
                                          "back-door criterion"},
    "identify_via_front_door": {"zh": "据前门准则与相应公式，判定效应可识别",
                                "en": "decide the effect is identifiable, by "
                                      "the front-door criterion and its "
                                      "formula"},
    "feedback_loop_withdraws_adjustment": {
        "zh": "确认程序声明的那个互为因果的环确实会影响本问题，"
              "因此调整类的识别路线在这里都不成立",
        "en": "confirm the declared reciprocal loop really does reach this "
              "question, so the adjustment routes do not hold here"},
    "identify_via_iv": {"zh": "据 IV 准则，判定效应可由工具变量识别",
                        "en": "decide the effect is identifiable from the "
                              "instrument, by the IV criterion"},
    "identify_via_general_id": {"zh": "据 general ID 的判定，效应可点识别",
                                "en": "the effect is point-identifiable, by "
                                      "what general ID decided"},
    "identify_via_tian": {"zh": "重导 ADMG 的 c-分量，把目标写成 c-factor 乘积（Tian）",
                          "en": "re-derive the ADMG's c-components and write "
                                "the target as a product of c-factors (Tian)"},
    "identify_via_idc": {"zh": "独立重导条件效应 P(Y|do(X), Z) 的识别",
                         "en": "independently re-derive the identification of "
                               "the conditional effect P(Y|do(X), Z)"},
    "identify_via_gformula": {"zh": "据顺序可交换性，判定时变策略对比可由 g-formula 识别",
                              "en": "decide the time-varying strategy contrast "
                                    "is identifiable by the g-formula, from "
                                    "sequential exchangeability"},
    "identify_via_mediation": {"zh": "判定至少一种中介分解（NDE/NIE 或 CDE）可识别",
                               "en": "decide at least one mediation "
                                     "decomposition (NDE/NIE or CDE) is "
                                     "identifiable"},
    "identify_via_mediation_joint": {"zh": "判定中介集的联合分解可识别",
                                     "en": "decide the joint decomposition "
                                           "over the mediator set is "
                                           "identifiable"},
    "identify_via_transport": {"zh": "据 S-可容许性与迁移公式，判定结论可迁移到目标总体",
                               "en": "decide the conclusion transports to the "
                                     "target population, by S-admissibility "
                                     "and the transport formula"},
    "id_star_identification": {"zh": "用 ID* 导出这个反事实量的识别式",
                               "en": "use ID* to derive the identifying "
                                     "expression for this counterfactual "
                                     "quantity"},

    # --- writing the estimand down --------------------------------------------
    "backdoor_adjustment_formula": {"zh": "写下后门调整公式：在调整集的每一层内算效应，再按各层占比加权",
                                    "en": "write down the back-door adjustment "
                                          "formula: compute the effect within "
                                          "each stratum of the adjustment set, "
                                          "then weight the strata by how "
                                          "common they are"},
    "front_door_adjustment_formula": {"zh": "写下前门调整公式：处理→中介与中介→结果两段相乘，再对处理求和",
                                      "en": "write down the front-door "
                                            "adjustment formula: multiply the "
                                            "treatment→mediator and "
                                            "mediator→outcome stages, then sum "
                                            "over the treatment"},
    "tian_formula_ast": {"zh": "写下 Tian 分解导出的识别式",
                         "en": "write down the identifying expression the Tian "
                               "decomposition produced"},
    "idc_formula_ast": {"zh": "写下 IDC 导出的条件效应识别式",
                        "en": "write down the identifying expression IDC "
                              "produced for the conditional effect"},
    "transport_formula": {"zh": "写下 Bareinboim 迁移公式：源总体的条件效应，按目标总体的协变量分布重新加权",
                          "en": "write down the Bareinboim transport formula: "
                                "the source population's conditional effect, "
                                "reweighted by the target population's "
                                "covariate distribution"},
    "transport_formula_ast": {"zh": "写下迁移公式的具体表达式",
                              "en": "write down the transport formula's "
                                    "concrete expression"},

    # --- putting numbers in ---------------------------------------------------
    "formula_evaluation": {"zh": "把 θ 代入识别公式求值",
                           "en": "substitute θ into the identifying formula "
                                 "and evaluate it"},
    "causation_probability_bounds":
        {"zh": "从 θ 求 PN/PS/PNS：两个干预风险都拿得到时用 Tian-Pearl(2000) 公式，"
        "拿不到而图上有工具变量时改在响应函数多面体上求解",
         "en": "solve PN/PS/PNS from θ: the Tian-Pearl (2000) formulas where "
               "both interventional risks are available, and a solve over the "
               "response-function polytope where they are not and the graph "
               "carries an instrument"},
    "counterfactual_cell_bounds":
        {"zh": "从 θ 解出这一格反事实的可识别区间：干预风险拿得到时用一条一致性恒等式，"
        "拿不到而图上有工具变量时改在响应函数多面体上求解",
         "en": "solve this counterfactual cell's identifiable interval from θ: "
               "a consistency identity where the interventional risk is "
               "available, and a solve over the response-function polytope "
               "where it is not and the graph carries an instrument"},
    "scm_abduction_action_prediction":
        {"zh": "按你声明的结构方程系数：从该个体的观测值反推它自己的外生扰动（abduction）、"
        "施加干预（action）、再沿方程重算目标（prediction）",
         "en": "using the structural coefficients you declared: recover this "
               "unit's own exogenous disturbance from its observations "
               "(abduction), apply the intervention (action), and recompute "
               "the target along the equations (prediction)"},
    "iv_wald_numeric_evaluate": {"zh": "按工具变量的条件集分层，逐层求 Wald 比",
                                 "en": "stratify by the instrument's "
                                       "conditioning set and take the Wald "
                                       "ratio within each stratum"},
    "mediation_numeric_evaluate": {"zh": "求出各条中介分解量（NDE / NIE / CDE）",
                                   "en": "compute each mediation quantity (NDE "
                                         "/ NIE / CDE)"},
    "numeric_result": {"zh": "把上一步算出的数收成本次查询的答案",
                       "en": "collect the number the previous step produced as "
                             "this query's answer"},

    # --- estimating from data -------------------------------------------------
    "numeric_backdoor_estimate": {"zh": "在数据上按后门公式求平均因果效应",
                                  "en": "estimate the average causal effect "
                                        "from the data by the back-door "
                                        "formula"},
    "numeric_joint_backdoor_estimate": {"zh": "在数据上求这一组处理的联合效应，以及它们之间的交互",
                                        "en": "estimate the joint effect of "
                                              "this group of treatments from "
                                              "the data, and the interaction "
                                              "between them"},
    "numeric_joint_general_id_estimate": {
        "zh": "在数据上逐个取值组合求这一组处理的联合效应，以及它们之间的交互",
        "en": "estimate the joint effect of this group of treatments from "
              "the data one treatment combination at a time, and the "
              "interaction between them"},
    "numeric_frontdoor_estimate": {"zh": "在数据上按前门公式求平均因果效应",
                                   "en": "estimate the average causal effect "
                                         "from the data by the front-door "
                                         "formula"},
    "numeric_iv_estimate": {"zh": "在数据上求工具变量估计（Wald 比 / 两阶段最小二乘）",
                            "en": "compute the instrumental-variable estimate "
                                  "from the data (Wald ratio / two-stage least "
                                  "squares)"},
    "numeric_iv_overid_estimate": {"zh": "在数据上做过度识别的 2SLS 估计（工具多于内生变量）",
                                   "en": "compute the over-identified 2SLS "
                                         "estimate from the data (more "
                                         "instruments than endogenous "
                                         "variables)"},
    "numeric_anderson_rubin_region": {"zh": "在数据上反演 Anderson-Rubin 检验，得到这一组系数的置信域",
                                      "en": "invert the Anderson-Rubin test on "
                                            "the data to get the confidence "
                                            "region for this group of "
                                            "coefficients"},
    "numeric_general_id_estimate": {"zh": "在数据上按 general ID 导出的估计量逐层求值",
                                    "en": "evaluate the estimand general ID "
                                          "derived, stratum by stratum, on the "
                                          "data"},
    "numeric_proximal_bridge_estimate": {
        "zh": "在数据上解 bridge function（Miao 2018 §3）求效应——这是个不适定"
              "反问题，所以带一个正则化项，报出来的数附带它对这一项的敏感度",
        "en": "solve the outcome bridge on the data (Miao 2018 §3) for the "
              "effect — an ill-posed inverse problem, so it carries a "
              "regularisation term, and the number travels with how much it "
              "moves under one",
    },
    "numeric_proximal_estimate": {"zh": "在数据上用近端矩阵求逆（Miao 2018）求效应",
                                  "en": "compute the effect from the data by "
                                        "proximal matrix inversion (Miao 2018)"},
    "numeric_proximal_null_test": {
        "zh": "通道反演不了，改为检验「有没有效应」（Miao 2018 §4）：把各处理"
              "层级的代理通道叠起来，看结局均值是否落在 U 的状态张成的那个"
              "低维空间里——落不进去，就是有效应",
        "en": "the channel would not invert, so test whether there is an "
              "effect at all (Miao 2018 §4): stack the proxy channel across "
              "the treatment's levels and ask whether the outcome means lie "
              "in the low-dimensional space U's states span — if they do "
              "not, there is an effect",
    },
    "numeric_measurement_correction_estimate": {"zh": "先用混淆矩阵校正测量误差，再求效应",
                                                "en": "correct the measurement "
                                                      "error with the "
                                                      "confusion matrix first, "
                                                      "then compute the effect"},
    "numeric_causation_estimate": {"zh": "在数据上按 Tian-Pearl 公式求 PN/PS/PNS",
                                   "en": "compute PN/PS/PNS from the data by "
                                         "the Tian-Pearl formulas"},
    # Two solvers stand behind this one rule — the consistency identity, and
    # the response-function program when an instrument is all there is — so
    # the sentence names what the rule does and leaves which route to the
    # licence that exists to say it.
    "numeric_counterfactual_cell_estimate":
        {"zh": "在数据上重算这一格反事实（并用自助法给出抽样区间）",
         "en": "recompute this counterfactual cell from the data (with a "
               "bootstrap sampling interval)"},
    "numeric_ctf_conjunction_estimate": {"zh": "在数据上按 ID*/IDC* 导出的式子求这个反事实合取",
                                         "en": "compute this counterfactual "
                                               "conjunction from the data by "
                                               "the expression ID*/IDC* "
                                               "derived"},
    "numeric_scm_counterfactual_estimate":
        {"zh": "结构方程的系数没有声明，改由每个节点的 OLS 从数据拟合，再做"
        "反推扰动-施加干预-沿方程重算",
         "en": "the structural coefficients were not declared, so each node is "
               "fitted from the data by OLS instead, and then abduction, "
               "action and prediction are run along the equations"},
}


def describe(rule, lang: language.Lang | str = language.DEFAULT) -> str:
    """What that step did, or the rule's own name.

    An unglossed rule surfaces as its id rather than as silence: this is a
    disclosure surface, and dropping a step the answer actually rests on is
    worse than printing a name the reader has to look up. The default is a
    safety net for a rule added after this file, not a place to leave one —
    a test refuses a producer-written rule that has no sentence here.

    A rule with no sentence in the READER's language surfaces the same way,
    and for the opposite reason: it is a hole this repository keeps empty
    rather than a rule from the future. Both hand back the identifier
    because a reader can act on neither, and neither is answered in some
    other language — half a chain in a language nobody asked for would be
    worse than the id.
    """
    return language.gloss(SAYS, rule, lang)
