// GENERATED FILE — DO NOT EDIT.
//
// Written by themis/output/reader_words.py from the kernel's own glosses.
// Regenerate with `python -m themis.output.reader_words`; the suite fails
// when this file and the kernel disagree, so a hand edit is reverted by the
// next regeneration rather than kept.
//
// What is here: every closed vocabulary the browser RESTATES — the same
// words the report gives a reader, in every language this build writes. What
// is not: the tables that render a vocabulary in the browser's own terms (a
// tier's plain-language gloss, a status's blurb, a refusal's head/lead/tail)
// and the two the kernel deliberately has no word for (a gap carries its own
// description; a query kind is glossed by a whole question line).
import type { Words } from './language'

export const AR_SET_KIND_WORDS: Record<string, Words> = {
  bounded: {
    zh: '有界区间',
    en: 'a bounded interval',
  },
  disconnected: {
    zh: '两条射线，中间一段被排除',
    en: 'two rays with a stretch between them ruled out',
  },
  empty: {
    zh: '空集 —— 没有哪个取值能同时满足所有工具的矩条件，数据在否定这组工具本身',
    en: 'empty — no value satisfies every instrument\'s moment condition at once, so the data are rejecting this set of instruments',
  },
  unbounded_above: {
    zh: '向上无界 —— 工具太弱，数据约束不住效应的上限（旁边那个 bootstrap 区间会把这件事掩盖掉）',
    en: 'unbounded above — the instrument is too weak for the data to constrain how large the effect could be (the bootstrap interval beside it hides exactly this)',
  },
  unbounded_below: {
    zh: '向下无界 —— 工具太弱，数据约束不住效应的下限（旁边那个 bootstrap 区间会把这件事掩盖掉）',
    en: 'unbounded below — the instrument is too weak for the data to constrain how small the effect could be (the bootstrap interval beside it hides exactly this)',
  },
  union: {
    zh: '多段（三段以上）',
    en: 'several pieces (three or more)',
  },
  whole_line: {
    zh: '整条实轴 —— 数据对这个效应没有任何约束力',
    en: 'the whole real line — the data constrain this effect not at all',
  },
}

export const LEDGER_LAYER_WORDS: Record<string, Words> = {
  confidence: {
    zh: '区间',
    en: 'the interval',
  },
  functional_form: {
    zh: '函数形式',
    en: 'functional form',
  },
  identification: {
    zh: '识别',
    en: 'identification',
  },
  parameter: {
    zh: '参数取值',
    en: 'a parameter value',
  },
  structural_edge: {
    zh: '图上的边',
    en: 'an edge in the graph',
  },
}

export const LEDGER_PROVENANCE_WORDS: Record<string, Words> = {
  caller_asserted: {
    zh: '你在问题里断言的',
    en: 'you asserted it in the question',
  },
  default: {
    zh: '估计器默认选择',
    en: 'the estimator\'s default choice',
  },
  discovery: {
    zh: '因果发现算法学出',
    en: 'learned by the causal-discovery algorithm',
  },
  inherent: {
    zh: '方法本身要求',
    en: 'required by the method itself',
  },
  llm_prior: {
    zh: 'LLM 常识 prior',
    en: 'an LLM\'s common-sense prior',
  },
  llm_proposal: {
    zh: '上游 LLM 提议',
    en: 'proposed by the upstream LLM',
  },
}

export const ASSUMPTION_SEVERITY_WORDS: Record<string, Words> = {
  confidence_only: {
    zh: '仅影响置信',
    en: 'affects the interval only',
  },
  distorting: {
    zh: '扭曲级',
    en: 'distorting',
  },
  invalidating: {
    zh: '作废级',
    en: 'invalidating',
  },
}

export const BOUNDS_CONTRAST_WORDS: Record<string, Words> = {
  ace: {
    zh: '平均因果效应（ACE）',
    en: 'the average causal effect (ACE)',
  },
}

export const BOUNDS_ESTIMAND_WORDS: Record<string, Words> = {
  arm_probability: {
    zh: '干预到所问的那一档之后，目标事件发生的概率',
    en: 'the probability of the target event after intervening to the arm you asked about',
  },
}

export const CDE_CONDITION_WORDS: Record<string, Words> = {
  C1: {
    zh: '把 M 固定住之后，X 到 Y 或 M 到 Y 仍有调整集挡不住的后门路径，而且图里没有任何变量能挡住它',
    en: 'with M held fixed there is still a back-door path from X to Y or from M to Y that the adjustment set does not block, and no variable in the graph can block it',
  },
  C2: {
    zh: '能挡住那条后门的变量是有的，但它是 X 或 M 的后代 —— 控制它会挡掉要测的那条路径',
    en: 'a variable that would block that back-door does exist, but it is a descendant of X or of M — controlling for it would block the very path being measured',
  },
}

export const DERIVATION_SAYS: Record<string, Words> = {
  backdoor_adjustment_formula: {
    zh: '写下后门调整公式：在调整集的每一层内算效应，再按各层占比加权',
    en: 'write down the back-door adjustment formula: compute the effect within each stratum of the adjustment set, then weight the strata by how common they are',
  },
  backdoor_criterion: {
    zh: '在图上验证调整集满足后门准则：阻断全部后门路径，且不含处理的后代',
    en: 'verify on the graph that the adjustment set satisfies the back-door criterion: it blocks every back-door path and contains no descendant of the treatment',
  },
  causation_probability_bounds: {
    zh: '从 θ 求 PN/PS/PNS：两个干预风险都拿得到时用 Tian-Pearl(2000) 公式，拿不到而图上有工具变量时改在响应函数多面体上求解',
    en: 'solve PN/PS/PNS from θ: the Tian-Pearl (2000) formulas where both interventional risks are available, and a solve over the response-function polytope where they are not and the graph carries an instrument',
  },
  cause_via_directed_path: {
    zh: '在图上找出一条从原因到结果的有向路径',
    en: 'find a directed path on the graph from cause to effect',
  },
  counterfactual_cell_bounds: {
    zh: '从 θ 解出这一格反事实的可识别区间：干预风险拿得到时用一条一致性恒等式，拿不到而图上有工具变量时改在响应函数多面体上求解',
    en: 'solve this counterfactual cell\'s identifiable interval from θ: a consistency identity where the interventional risk is available, and a solve over the response-function polytope where it is not and the graph carries an instrument',
  },
  ctf_conjunction_criterion: {
    zh: '用 ID*/IDC* 判定这个反事实合取在图上可点识别',
    en: 'use ID*/IDC* to decide whether this counterfactual conjunction is point-identifiable on the graph',
  },
  d_connected_via_open_path: {
    zh: '在图上找出一条打开的路径，两者因此相关',
    en: 'find an open path on the graph, which is why the two are associated',
  },
  d_separated: {
    zh: '在图上确认两者在给定条件集下 d-分离（无关联通路）',
    en: 'confirm on the graph that the two are d-separated given the conditioning set (no open path between them)',
  },
  formula_evaluation: {
    zh: '把 θ 代入识别公式求值',
    en: 'substitute θ into the identifying formula and evaluate it',
  },
  front_door_adjustment_formula: {
    zh: '写下前门调整公式：处理→中介与中介→结果两段相乘，再对处理求和',
    en: 'write down the front-door adjustment formula: multiply the treatment→mediator and mediator→outcome stages, then sum over the treatment',
  },
  front_door_criterion: {
    zh: '在图上验证中介集满足前门准则',
    en: 'verify on the graph that the mediator set satisfies the front-door criterion',
  },
  general_id_criterion: {
    zh: '用 general ID（Tian–Shpitser c-factor 分解）判定效应在 ADMG 上可点识别',
    en: 'use general ID (the Tian-Shpitser c-factor decomposition) to decide whether the effect is point-identifiable on the ADMG',
  },
  graph_is_dag: {
    zh: '确认因果图无环',
    en: 'confirm the causal graph is acyclic',
  },
  id_star_identification: {
    zh: '用 ID* 导出这个反事实量的识别式',
    en: 'use ID* to derive the identifying expression for this counterfactual quantity',
  },
  idc_formula_ast: {
    zh: '写下 IDC 导出的条件效应识别式',
    en: 'write down the identifying expression IDC produced for the conditional effect',
  },
  idc_rule2_exchange: {
    zh: '做 IDC 规则 2 的观测-干预交换，把条件项挪进 do 里',
    en: 'apply IDC rule 2\'s observation-intervention exchange, moving the conditioning term inside the do',
  },
  identify_via_backdoor: {
    zh: '据后门准则与相应公式，判定效应可识别',
    en: 'decide the effect is identifiable, by the back-door criterion and its formula',
  },
  identify_via_front_door: {
    zh: '据前门准则与相应公式，判定效应可识别',
    en: 'decide the effect is identifiable, by the front-door criterion and its formula',
  },
  identify_via_general_id: {
    zh: '据 general ID 的判定，效应可点识别',
    en: 'the effect is point-identifiable, by what general ID decided',
  },
  identify_via_gformula: {
    zh: '据顺序可交换性，判定时变策略对比可由 g-formula 识别',
    en: 'decide the time-varying strategy contrast is identifiable by the g-formula, from sequential exchangeability',
  },
  identify_via_idc: {
    zh: '独立重导条件效应 P(Y|do(X), Z) 的识别',
    en: 'independently re-derive the identification of the conditional effect P(Y|do(X), Z)',
  },
  identify_via_iv: {
    zh: '据 IV 准则，判定效应可由工具变量识别',
    en: 'decide the effect is identifiable from the instrument, by the IV criterion',
  },
  identify_via_joint_backdoor: {
    zh: '据联合后门准则，判定这一组处理的联合效应可识别',
    en: 'decide the joint effect of this group of treatments is identifiable, by the joint back-door criterion',
  },
  identify_via_mediation: {
    zh: '判定至少一种中介分解（NDE/NIE 或 CDE）可识别',
    en: 'decide at least one mediation decomposition (NDE/NIE or CDE) is identifiable',
  },
  identify_via_mediation_joint: {
    zh: '判定中介集的联合分解可识别',
    en: 'decide the joint decomposition over the mediator set is identifiable',
  },
  identify_via_tian: {
    zh: '重导 ADMG 的 c-分量，把目标写成 c-factor 乘积（Tian）',
    en: 're-derive the ADMG\'s c-components and write the target as a product of c-factors (Tian)',
  },
  identify_via_transport: {
    zh: '据 S-可容许性与迁移公式，判定结论可迁移到目标总体',
    en: 'decide the conclusion transports to the target population, by S-admissibility and the transport formula',
  },
  iv_criterion_check: {
    zh: '在图上验证所选工具变量满足 IV 准则',
    en: 'verify on the graph that the chosen instrument satisfies the IV criterion',
  },
  iv_wald_numeric_evaluate: {
    zh: '按工具变量的条件集分层，逐层求 Wald 比',
    en: 'stratify by the instrument\'s conditioning set and take the Wald ratio within each stratum',
  },
  joint_backdoor_criterion: {
    zh: '在图上验证这一组处理的联合调整集有效（广义调整准则）',
    en: 'verify on the graph that the joint adjustment set for this group of treatments is valid (the generalized adjustment criterion)',
  },
  longitudinal_sequential_exchangeability_check: {
    zh: '逐个时点重查顺序可交换性：每一步的处理在既往历史给定后可视为随机',
    en: 're-check sequential exchangeability time point by time point: at each step the treatment can be treated as random given the history so far',
  },
  mediation_cde_check: {
    zh: '验证受控直接效应 CDE(m) 的后门识别条件',
    en: 'verify the back-door identification conditions for the controlled direct effect CDE(m)',
  },
  mediation_cde_joint_check: {
    zh: '验证把整个中介块固定住的联合 CDE 识别条件',
    en: 'verify the joint CDE identification conditions with the whole mediator block held fixed',
  },
  mediation_nde_nie_check: {
    zh: '验证 Pearl 2001 的四个条件，自然直接/间接效应可识别',
    en: 'verify Pearl 2001\'s four conditions, so the natural direct and indirect effects are identifiable',
  },
  mediation_nde_nie_joint_check: {
    zh: '对整个中介集验证那四个条件（VanderWeele–Vansteelandt 2014 的向量版）',
    en: 'verify those four conditions for the whole mediator set (the vector version from VanderWeele-Vansteelandt 2014)',
  },
  mediation_numeric_evaluate: {
    zh: '求出各条中介分解量（NDE / NIE / CDE）',
    en: 'compute each mediation quantity (NDE / NIE / CDE)',
  },
  no_directed_path: {
    zh: '在图上确认不存在从原因到结果的有向路径',
    en: 'confirm on the graph that no directed path runs from cause to effect',
  },
  numeric_backdoor_estimate: {
    zh: '在数据上按后门公式求平均因果效应',
    en: 'estimate the average causal effect from the data by the back-door formula',
  },
  numeric_causation_estimate: {
    zh: '在数据上按 Tian-Pearl 公式求 PN/PS/PNS',
    en: 'compute PN/PS/PNS from the data by the Tian-Pearl formulas',
  },
  numeric_counterfactual_cell_estimate: {
    zh: '在数据上重算这一格反事实（并用自助法给出抽样区间）',
    en: 'recompute this counterfactual cell from the data (with a bootstrap sampling interval)',
  },
  numeric_ctf_conjunction_estimate: {
    zh: '在数据上按 ID*/IDC* 导出的式子求这个反事实合取',
    en: 'compute this counterfactual conjunction from the data by the expression ID*/IDC* derived',
  },
  numeric_frontdoor_estimate: {
    zh: '在数据上按前门公式求平均因果效应',
    en: 'estimate the average causal effect from the data by the front-door formula',
  },
  numeric_general_id_estimate: {
    zh: '在数据上按 general ID 导出的估计量逐层求值',
    en: 'evaluate the estimand general ID derived, stratum by stratum, on the data',
  },
  numeric_iv_estimate: {
    zh: '在数据上求工具变量估计（Wald 比 / 两阶段最小二乘）',
    en: 'compute the instrumental-variable estimate from the data (Wald ratio / two-stage least squares)',
  },
  numeric_iv_overid_estimate: {
    zh: '在数据上做过度识别的 2SLS 估计（工具多于内生变量）',
    en: 'compute the over-identified 2SLS estimate from the data (more instruments than endogenous variables)',
  },
  numeric_joint_backdoor_estimate: {
    zh: '在数据上求这一组处理的联合效应，以及它们之间的交互',
    en: 'estimate the joint effect of this group of treatments from the data, and the interaction between them',
  },
  numeric_measurement_correction_estimate: {
    zh: '先用混淆矩阵校正测量误差，再求效应',
    en: 'correct the measurement error with the confusion matrix first, then compute the effect',
  },
  numeric_proximal_estimate: {
    zh: '在数据上用近端矩阵求逆（Miao 2018）求效应',
    en: 'compute the effect from the data by proximal matrix inversion (Miao 2018)',
  },
  numeric_result: {
    zh: '把上一步算出的数收成本次查询的答案',
    en: 'collect the number the previous step produced as this query\'s answer',
  },
  numeric_scm_counterfactual_estimate: {
    zh: '结构方程的系数没有声明，改由每个节点的 OLS 从数据拟合，再做反推扰动-施加干预-沿方程重算',
    en: 'the structural coefficients were not declared, so each node is fitted from the data by OLS instead, and then abduction, action and prediction are run along the equations',
  },
  proximal_criterion: {
    zh: '在图上验证近端识别条件（Miao model f：两个 proxy 与未测混杂的关系）',
    en: 'verify the proximal identification conditions on the graph (Miao model f: how the two proxies relate to the unmeasured confounder)',
  },
  s_admissibility_check: {
    zh: '重导 S-可容许性（Bareinboim 定理 1）：选择节点在给定集合下与结果无关',
    en: 're-derive S-admissibility (Bareinboim Theorem 1): the selection node is independent of the outcome given the set',
  },
  scm_abduction_action_prediction: {
    zh: '按你声明的结构方程系数：从该个体的观测值反推它自己的外生扰动（abduction）、施加干预（action）、再沿方程重算目标（prediction）',
    en: 'using the structural coefficients you declared: recover this unit\'s own exogenous disturbance from its observations (abduction), apply the intervention (action), and recompute the target along the equations (prediction)',
  },
  tian_c_decomposition: {
    zh: '在图上做 c-分解，把联合分布拆成各 c-分量的乘积',
    en: 'run the c-decomposition on the graph, splitting the joint distribution into a product over c-components',
  },
  tian_formula_ast: {
    zh: '写下 Tian 分解导出的识别式',
    en: 'write down the identifying expression the Tian decomposition produced',
  },
  tian_hedge_witness: {
    zh: '在图上找到一个 hedge —— 该效应非参数不可点识别',
    en: 'find a hedge on the graph — the effect is not non-parametrically point-identifiable',
  },
  transport_formula: {
    zh: '写下 Bareinboim 迁移公式：源总体的条件效应，按目标总体的协变量分布重新加权',
    en: 'write down the Bareinboim transport formula: the source population\'s conditional effect, reweighted by the target population\'s covariate distribution',
  },
  transport_formula_ast: {
    zh: '写下迁移公式的具体表达式',
    en: 'write down the transport formula\'s concrete expression',
  },
}

export const EVALUE_BAND_BASIS_WORDS: Record<string, Words> = {
  ci_bound: {
    zh: '按置信区间靠近零的那一端判的——这一端问的是「结论还在不在」',
    en: 'read off the end of the interval nearer the null — that end asks whether the finding survives',
  },
  point: {
    zh: '按点估计判的——这次没有可用的区间端点',
    en: 'read off the point estimate — no interval bound was available this time',
  },
}

export const EVALUE_BAND_WORDS: Record<string, Words> = {
  fragile: {
    zh: '很脆弱——很小的未测混杂就足以解释掉这个结果',
    en: 'fragile — a small amount of unmeasured confounding is already enough to explain this result away',
  },
  moderate: {
    zh: '中等强度——一个强度一般的混杂就足以解释掉这个结果',
    en: 'moderate — a confounder of ordinary strength is enough to explain this result away',
  },
  substantial: {
    zh: '比较稳健——混杂要相当大才解释得掉',
    en: 'substantial — the confounding would have to be sizeable to explain this result away',
  },
  very_robust: {
    zh: '非常稳健——需要一个强到不合常理的混杂才解释得掉',
    en: 'very robust — it would take a confounder strong enough to be implausible',
  },
}

export const FOUR_WAY_MEDIATOR_SCALE_WORDS: Record<string, Words> = {
  binary: {
    zh: '中介是二值 —— 走 eAppendix §3.4 的闭式',
    en: 'the mediator is binary — the eAppendix §3.4 closed form',
  },
  continuous: {
    zh: '中介是连续 —— 走 eAppendix §3.3 的闭式，多出一个中介残差方差项',
    en: 'the mediator is continuous — the eAppendix §3.3 closed form, which carries one extra mediator-residual variance term',
  },
}

export const GAP_IF_PROVIDED: Record<string, Words> = {
  ambiguous_variable_definition: {
    zh: '变量框架化后，下游结果（点估计 / bounds）的语义才确定 —— 用户能判断 \'P(Y|X)\' 到底说的是哪段时间窗 / 哪种测量',
    en: 'once the variable is framed, what the downstream result (a point, an interval) means is settled — the reader can tell which time window and which measurement \'P(Y|X)\' is about',
  },
  collider_conditioning_opens_backdoor: {
    zh: '从 `given` 移除 `{collider}` —— 如果你真的想问 "在 `{collider}` 子群上的效应"，需要单独的 transport / stratified analysis（先分层再估计），不能直接做条件查询',
    en: 'drop `{collider}` from `given` — if the effect within the `{collider}` subgroup is really the question, it needs a transport or a stratified analysis of its own (stratify first, estimate second) rather than a conditional query',
  },
  dichotomized_continuous_measure: {
    zh: '若能拿到未二分的连续原始测量，可改走 dose-response 估计（LinearDML / DRLearner，Themis Phase 13/14），保留剂量-反应曲线并避免任意切点',
    en: 'given the original continuous measurement before it was cut, the dose-response route is available instead (LinearDML / DRLearner, Themis Phase 13/14), which keeps the dose-response curve and needs no arbitrary cutpoint',
  },
  dose_response_data_required: {
    zh: '数据齐了之后，去 EconML / DoubleML / GAM 拟合曲线 —— Themis 不在 estimator 这一步参与',
    en: 'once the data is complete, fit the curve in EconML / DoubleML / GAM — Themis takes no part in that step',
  },
  graph_theta_independence_mismatch: {
    zh: '可给点估计（在解决图与 CPT 矛盾后）',
    en: 'a point estimate, once the graph and the CPTs stop contradicting each other',
  },
  ill_defined_intervention_versions: {
    zh: '在 `{intervention}` 的 VariableDeclaration 上加 `time_window`（说明 "持续多长时间 / 在哪个时点被视为该状态"），并在 program.extensions.ambiguities 里加 `ill_defined_intervention` 条目，说明你打算把哪一种具体的 manipulation（如生活方式 / 用药 / 手术 / RCT 随机化）作为 do(.) 的 well-defined intervention 等价物',
    en: 'add a `time_window` to `{intervention}`\'s VariableDeclaration (saying "for how long / at which point it counts as being in that state"), and add an `ill_defined_intervention` entry under program.extensions.ambiguities naming which concrete manipulation (lifestyle / medication / surgery / RCT randomization) you mean to stand in for do(.) as the well-defined intervention',
  },
  iv_estimand_fallback_to_linear: {
    zh: '分层 Wald 就能跑起来，报出来的量会变成顺从者中的效应，也就是这个工具真正识别的那个估计量',
    en: 'the stratified Wald becomes available, and what gets reported turns into the effect among compliers — the estimand this instrument actually identifies',
  },
  measurement_error_concern: {
    zh: '若拿到 (a) 被误分类离散结局或二值暴露的验证过混淆矩阵（Se/Sp 或整张 confusion matrix），可经 estimate(misclassification=...) 逐后门层矩阵求逆去衰减；或 (b) 连续暴露或连续混杂的已知经典加性误差方差 σ²_u（重复测量 test-retest / 验证子样本），可经 estimate(measurement_error={{<暴露或混杂名>: {{error_variance}}}}) 用 regression calibration 去偏（误测混杂纠正残差混淆；非线性结局的 SIMEX 仍推迟）；连续结局的 σ²_v 同一入口给出的是精度代价而非校正，因为它本就不偏；或 (c) gold-standard 亚样本（如 BP 用 ABPM、sodium 用 24h 尿钠）做校准',
    en: 'given (a) a validated confusion matrix for the misclassified discrete outcome or binary exposure (Se/Sp, or the whole matrix), the attenuation can be undone through estimate(misclassification=...), inverting within each back-door stratum; or (b) a known classical additive error variance σ²_u for a continuous exposure or continuous confounder (test-retest repeats, a validation subsample), which debiases through estimate(measurement_error={{<exposure or confounder>: {{error_variance}}}}) with regression calibration (a mismeasured confounder has its residual confounding corrected; SIMEX for non-linear outcomes is still deferred) — for a continuous outcome the same entry point gives the precision cost rather than a correction, because there is no bias to correct; or (c) a gold-standard subsample to calibrate against (ABPM for blood pressure, 24-hour urinary sodium for salt)',
  },
  missing_assumption: {
    zh: '该识别路径可继续走到点估计',
    en: 'this identification route can carry on to a point estimate',
  },
  missing_distribution: {
    zh: '可给点估计',
    en: 'a point estimate',
  },
  missing_mediator_data: {
    zh: '可给 NDE / NIE / TE 数值分解',
    en: 'a numeric NDE / NIE / TE decomposition',
  },
  missing_structural_input: {
    zh: '该查询可继续走到点估计',
    en: 'this query can carry on to a point estimate',
  },
  missing_unit_observation: {
    zh: '该查询可继续走到点估计',
    en: 'this query can carry on to a point estimate',
  },
  selection_on_collider_opens_path: {
    zh: '补充未被 `{collider}` 限制的对照样本（覆盖 {collider}=¬{value} 的受试者），把全样本作为分析对象 —— 而不是只用 `{collider}={value}` 子样本',
    en: 'add the controls that `{collider}` excluded (subjects with {collider}=¬{value}) and analyse the whole sample rather than the `{collider}={value}` subsample alone',
  },
  transport_source_conditional_unknown: {
    zh: '可给目标人群的 transport-adjusted ATE 点估计',
    en: 'a transport-adjusted ATE point estimate for the target population',
  },
  transport_target_distribution_unknown: {
    zh: '可给目标人群的 transport-adjusted ATE 点估计',
    en: 'a transport-adjusted ATE point estimate for the target population',
  },
  unattempted_layer_due_to_dispatch_conflict: {
    zh: '拆成两个 query，各自只声明一层：一个带 {won}，一个带 {lost}',
    en: 'split it into two queries, each declaring one layer: one with {won}, one with {lost}',
  },
  unidentifiable_no_admissible_set: {
    zh: '可给出识别公式 + 后续点估计',
    en: 'an identification formula, and a point estimate after it',
  },
  unmeasured_confounder_risk: {
    zh: '若怀疑某 latent 共因，添加 bidirected 边；Themis 会改走 ADMG-aware（Tian / front-door / IV）识别策略并报对应的 structural gap',
    en: 'if you suspect a latent common cause, add a bidirected edge; Themis will switch to an ADMG-aware identification strategy (Tian / front-door / IV) and report the structural gap that goes with it',
  },
  unverified_proposal_edge_on_query_path: {
    zh: '可换成证据支持的边或外部文献的引用',
    en: 'replace it with an edge evidence supports, or with a citation to the literature',
  },
}

export const GAP_ROUTES: Record<string, Words> = {
  accept_the_interval: {
    zh: '接受 {fallback} 给区间答案',
    en: 'accept {fallback} and take the interval answer',
  },
  accept_the_mixed_estimand: {
    zh: '在 extensions.ambiguities 里以 `ill_defined_intervention` kind 显式声明本题接受多 intervention 的混合估计量 —— Themis 会停发本警告并在渲染时把 caveat 显式化',
    en: 'declare under extensions.ambiguities, with the kind `ill_defined_intervention`, that this question accepts an estimand mixed over several interventions — Themis stops issuing this warning and makes the caveat explicit when it renders',
  },
  accept_the_source_ate: {
    zh: '接受源人群 ATE 作为粗略估计（外推有效性弱）',
    en: 'take the source population\'s ATE as a rough estimate (the extrapolation rests on little)',
  },
  accept_the_variance_weighted_2sls: {
    zh: '就按原样报 2SLS 系数，同时说明它是各层效应的方差加权平均，而不是顺从者中的效应',
    en: 'report the 2SLS coefficient as it stands, saying that it is a variance-weighted average of the stratum effects rather than the effect among compliers',
  },
  ar_set_for_the_joint_stage: {
    zh: '报 Anderson-Rubin 置信集——它反转的那个检验，不管联合第一阶段多强都有正确的水平',
    en: 'report an Anderson-Rubin confidence set — the test it inverts has the right level whatever the joint first stage is',
  },
  ar_set_not_constructible: {
    zh: '拿到一个对弱识别稳健的区间（Anderson-Rubin），它不管第一阶段多强都有正确的水平；这份样本不足以构造出来，所以这意味着要更多数据或换一个设计，而不是从这个结果里读出来',
    en: 'get an interval robust to weak identification (Anderson-Rubin), which has the right level whatever the first stage is — this sample was not enough to construct one, so that means more data or a different design rather than something to read off this result',
  },
  ask_conditionally: {
    zh: '改为询问\'若该边成立则…\'的条件性问题',
    en: 'ask the conditional question instead — \'if this edge holds, then …\'',
  },
  ask_the_marginal_effect: {
    zh: '不做这个条件，问 marginal 效应 P({target} | do({intervention}))',
    en: 'drop the condition and ask for the marginal effect P({target} | do({intervention}))',
  },
  bound_the_unsupported_region: {
    zh: '对没有支撑的那片区域，只给出界的答案',
    en: 'give a bounds answer over the region that has no support',
  },
  bounds_already_computed: {
    zh: '已经算出区间了（method={methods}）',
    en: 'the interval has already been computed (method={methods})',
  },
  coarsen_the_conditioning_set: {
    zh: '把条件集变粗（更少或更宽的类别），让每一格都同时带上两条工具臂——但前提是变粗之后仍然挡得住工具到结局的后门',
    en: 'coarsen the conditioning set (fewer or wider categories) so that every cell carries both instrument arms — provided the coarser set still blocks the back door from the instrument to the outcome',
  },
  collect_in_the_one_armed_strata: {
    zh: '在缺工具臂的那些分层里补收观测，这能直接把 LATE 救回来',
    en: 'collect observations in the strata that are missing an instrument arm — that recovers the LATE directly',
  },
  collect_in_the_saturated_strata: {
    zh: '在饱和的那些子层补样本（多收 rare-outcome 的观测）——Hosmer-Lemeshow 的经验法则是每个参数至少 10 个事件',
    en: 'collect more observations in the saturated strata (more rare-outcome events) — the Hosmer-Lemeshow rule of thumb is at least 10 events per parameter',
  },
  collect_it_no_interval_fallback: {
    zh: '直接收集 {what} 的数据 —— 该问法没有区间退路，拿不到点估计就没有数',
    en: 'collect data for {what} directly — this question has no interval to fall back on, so without the point estimate there is no number at all',
  },
  cross_check_an_experiment: {
    zh: '有随机对照 / 准实验数据时，拿它和这个观察性估计相互印证',
    en: 'where randomized or quasi-experimental data exists, check it against this observational estimate',
  },
  declare_it_a_selection_node: {
    zh: '用 `selection_node` (Phase 9 §T9.1) 把 `{collider}` 声明为 transport 选择节点而不是观察节点，并通过 transport identification 路径处理跨人群泛化',
    en: 'declare `{collider}` a transport selection node rather than an observation node with `selection_node` (Phase 9 §T9.1), and generalize across populations through the transport identification route',
  },
  declare_the_intervention_an_event: {
    zh: '把 `{intervention}` 重新声明为一个具体的事件类变量（state_vs_event="event"）—— 一个有明确操纵动作的一次性事件，这样 do(.) 有明确目标',
    en: 'redeclare `{intervention}` as a concrete event variable (state_vs_event="event") — a one-off event with a definite manipulation behind it, so do(.) has something definite to act on',
  },
  drop_the_contradicting_edge: {
    zh: '删除引发独立性矛盾的边（改图，承认现有 CPT 已是真分布）',
    en: 'drop the edge that causes the contradiction (change the graph, and take the CPTs as the true distribution)',
  },
  drop_the_other_layer: {
    zh: '如果只想要 {wanted} 结果，删除 {drop} 使 dispatch 唯一',
    en: 'if the {wanted} result is the one you want, drop {drop} so the dispatch is unambiguous',
  },
  drop_the_suspect_instrument: {
    zh: '去掉排他性可疑的那个（些）工具再跑一次（某个子集可能就通过了）',
    en: 'drop the instrument(s) whose exclusion is in doubt and run again — some subset of them may pass',
  },
  emulate_a_target_trial: {
    zh: '按 Hernán-Robins 的目标试验模拟（target trial emulation）重新设计：明确入组条件，做 per-protocol 分析',
    en: 'redesign it as a Hernán-Robins target trial emulation: state the eligibility criteria, and do a per-protocol analysis',
  },
  fall_back_to_a_binary_contrast: {
    zh: '退一步只看二元对比 (X=high vs X=low)：Themis 能给区间答案',
    en: 'step back to the binary contrast (X=high vs X=low), which Themis can answer with an interval',
  },
  fall_back_to_bounds_without_exclusion: {
    zh: '退回到不假设排他性的、只给界的答案（Manski 自然界）',
    en: 'fall back to a bounds answer that assumes no exclusion restriction (Manski\'s natural bounds)',
  },
  fall_back_to_cde: {
    zh: '回退到 CDE（控制中介，给条件直接效应）',
    en: 'fall back to the CDE (hold the mediator fixed, and take the controlled direct effect)',
  },
  fall_back_to_iv_bounds: {
    zh: '退回到只给界的答案（Manski 自然界 / Balke-Pearl IV 界对弱工具都是稳健的）',
    en: 'fall back to a bounds answer — Manski\'s natural bounds and the Balke-Pearl IV bounds are both robust to a weak instrument',
  },
  fall_back_to_the_total_effect: {
    zh: '退回 total effect，不分解',
    en: 'fall back to the total effect, undecomposed',
  },
  find_a_matched_rct: {
    zh: '退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价',
    en: 'failing that: find the one small RCT closest to your subgroup, and pay for it in sample size',
  },
  find_a_stronger_instrument: {
    zh: '找一个更强的工具（条件之后，与处理的第一阶段偏相关更高的那种）',
    en: 'find a stronger instrument — one whose first-stage partial correlation with the treatment, after conditioning, is higher',
  },
  find_a_subgroup_analysis: {
    zh: '找 meta-analysis 的 subgroup analysis（按 age / sex / BMI 分层）',
    en: 'find the meta-analysis\'s subgroup analysis (stratified by age / sex / BMI)',
  },
  find_an_instrument: {
    zh: '找一个满足 IV 条件的工具变量',
    en: 'find an instrument that satisfies the IV conditions',
  },
  find_stronger_instruments_jointly: {
    zh: '找更强的工具（与处理的联合第一阶段偏相关更高的那种）',
    en: 'find stronger instruments — ones whose joint first-stage partial correlation with the treatment is higher',
  },
  find_the_rct_ipd: {
    zh: '找原始 RCT IPD（联系作者 / 看附件 supplementary table）',
    en: 'find the original RCT\'s individual participant data (write to the authors, or check the supplementary tables)',
  },
  fix_the_data_to_match_the_declaration: {
    zh: '若 `{variable}` 确实是{scale}的，那就是数据这一列有问题（供给的值与声明不符），改数据',
    en: 'if `{variable}` really is {scale}, then it is this column of the data that is wrong — the values supplied do not match the declaration — so fix the data',
  },
  fix_the_declaration_to_match_the_data: {
    zh: '若数据是对的，那就改声明（尺度 / 取值范围），让估计量对上你真正能测到的量',
    en: 'if the data is right, then fix the declaration (the scale, the range) so that the estimand matches the quantity you can actually measure',
  },
  go_bayesian_with_a_weak_prior: {
    zh: '处理×混杂的格子稀疏到这个程度时，考虑贝叶斯拟合配弱信息先验，而不是频率派估计',
    en: 'where the treatment x confounder cells are this sparse, consider a Bayesian fit with a weakly informative prior rather than a frequentist estimate',
  },
  keep_the_measure_continuous: {
    zh: '保留连续变量，用 dose-response 估计代替二分（Themis Phase 13/14）',
    en: 'keep the variable continuous and estimate the dose-response instead of dichotomizing (Themis Phase 13/14)',
  },
  know_the_bootstrap_is_also_strained: {
    zh: '用 bootstrap 置信区间而不是 plug-in 区间（这里已经是这样了，但 bootstrap 本身在饱和下也不稳，可能抽出 NaN）',
    en: 'use the bootstrap interval rather than the plug-in one (already the case here, though the bootstrap is itself unsteady under saturation and can draw NaNs)',
  },
  loosen_the_adjustment_set: {
    zh: '放宽调整集，让没有支撑的那一层不再是同一层——但前提是确实存在一个站得住脚的 Z 可以换过去',
    en: 'loosen the adjustment set so the unsupported stratum is no longer one stratum — but only if there is a defensible Z to move to',
  },
  maybe_it_is_not_a_collider: {
    zh: '如果 `{collider}` 不是真 collider（即只有 X 或只有 Y 是祖先），更新 DAG 把缺失的因果方向加进去 — 当前结构性结论会变',
    en: 'if `{collider}` is not really a collider (only X or only Y is an ancestor), update the DAG with the causal direction that is missing — the structural conclusion will change',
  },
  maybe_it_is_not_a_common_effect: {
    zh: '如果 `{collider}` 实际并非由 `{intervention}` 和 `{target}` 共同决定，更新 DAG 删除其中一条祖先边 —— 当前结构性结论会随之改变',
    en: 'if `{collider}` is not in fact determined by both `{intervention}` and `{target}`, update the DAG and remove one of those ancestor edges — the structural conclusion moves with it',
  },
  measure_the_confounder_and_reidentify: {
    zh: '测量并加入 unmeasured confounder Z，重新识别',
    en: 'measure the unmeasured confounder Z, add it, and identify again',
  },
  measure_the_confounder_to_break_the_hedge: {
    zh: '测量并加入 unmeasured confounder Z，打破 hedge',
    en: 'measure the unmeasured confounder Z, add it, and break the hedge',
  },
  reexamine_the_graph_for_a_direct_path: {
    zh: '重新审视因果图——过度识别检验被否决，往往意味着一条本以为只走 Z→X 的路径其实直接到达了 Y',
    en: 're-examine the causal graph — a rejected over-identification test usually means a path believed to run only Z->X in fact reaches Y directly',
  },
  report_attenuation_range: {
    zh: '在敏感性分析中报告 attenuation factor 范围（Rosner et al 1989 regression calibration upper bound）',
    en: 'report a range for the attenuation factor in the sensitivity analysis (the regression-calibration upper bound of Rosner et al 1989)',
  },
  report_cutpoint_sensitivity: {
    zh: '若必须二分，报告对 cutpoint 的敏感性分析（多个切点下结论是否稳定）',
    en: 'if it has to be dichotomized, report a sensitivity analysis over the cutpoint (does the conclusion hold at several of them)',
  },
  retest_reliability: {
    zh: '对涉及变量做 reliability 重测，按 Carroll et al 2006 *Measurement Error in Nonlinear Models* 校准',
    en: 'run a reliability retest on the variables involved and calibrate as in Carroll et al 2006 *Measurement Error in Nonlinear Models*',
  },
  reweight_for_selection: {
    zh: '用 inverse-probability-of-selection weighting (Hernán et al 2004 §5)：对每个保留样本按 1/P({collider}={value} | X, Y) 加权重抽以近似全样本',
    en: 'use inverse-probability-of-selection weighting (Hernán et al 2004 §5): weight each retained subject by 1/P({collider}={value} | X, Y) to approximate the whole sample',
  },
  run_an_e_value: {
    zh: '数据到位后跑 E-value 敏感性分析（Phase 8.2，对二值结局自动附）',
    en: 'run an E-value sensitivity analysis once the data is in hand (Phase 8.2, attached automatically for a binary outcome)',
  },
  run_an_rct_past_the_backdoor: {
    zh: '在 X 上做 RCT (如可行)，旁路 backdoor',
    en: 'randomize X if that is feasible, and bypass the back-door',
  },
  run_an_rct_past_the_hedge: {
    zh: '在 X 上做 RCT (如可行)，旁路 hedge',
    en: 'randomize X if that is feasible, and bypass the hedge',
  },
  split_the_intervention_in_two: {
    zh: '把 `{intervention}` 拆成两个变量：一个事件类的intervention（具体的操纵动作）+ 一个由它导致的中间状态，用 mediation 路径处理',
    en: 'split `{intervention}` into two variables: an event-shaped intervention (the concrete manipulation) and the intermediate state it causes, and handle it through the mediation route',
  },
  stratify_more_finely: {
    zh: '对被二分的 confounder，改用更细分层或样条以减少类内残余混杂（Becher 1992）',
    en: 'for a dichotomized confounder, use finer strata or a spline to cut the within-category residual confounding (Becher 1992)',
  },
  supply_a_source_for_the_edge: {
    zh: '提供支持这条边的研究 / 数据来源',
    en: 'give the study or the data this edge rests on',
  },
  supply_the_conditional: {
    zh: '补充所缺的条件量 {what}（接受图）',
    en: 'supply the conditional {what} that is missing (and keep the graph)',
  },
  tighten_the_iv_interval: {
    zh: '工具变量已声明并已用于给出区间；要把区间收紧成点估计，需补一个额外假设：monotonicity（→ LATE/Wald）或 linearity（→ 2SLS/ATE）',
    en: 'an instrument is declared and the interval already uses it; tightening that interval to a point needs one further assumption — monotonicity (→ LATE/Wald) or linearity (→ 2SLS/ATE)',
  },
  treat_the_collider_as_a_target_population: {
    zh: '用 transport identification 路径处理 "target population restricted by {collider}" 而不是用 `given` 字段',
    en: 'handle "target population restricted by {collider}" through the transport identification route rather than through the `given` field',
  },
  trim_to_the_overlap_region: {
    zh: '把样本裁到重叠区域（例如丢掉倾向性落在 [0.05, 0.95] 之外的观测）再估一次——这样得到的答案是重叠子集上的 ATE，不是全人群的',
    en: 'trim the sample to the overlap region (dropping observations whose propensity falls outside [0.05, 0.95], say) and estimate again — the answer is then the ATE on the overlapping subset, not on the whole population',
  },
  use_a_separation_robust_fit: {
    zh: '改用 Firth 惩罚 logistic 或精确 logistic 回归（不是 sklearn 默认的 L2）——它们对 separation 稳健',
    en: 'fit a Firth penalised logistic or an exact logistic regression instead (not sklearn\'s default L2) — both are robust to separation',
  },
  use_an_overlap_robust_method: {
    zh: '换一个对重叠不足更稳健的方法（带卡钳的匹配、用加权 ATT 代替 ATE、按倾向性分层的估计量）',
    en: 'switch to a method more robust to thin overlap: caliper matching, a weighted ATT in place of the ATE, or a propensity-stratified estimator',
  },
  use_experimental_data_for_the_versions: {
    zh: '用 RCT / 实验性数据替代观察性主样本 —— 实验里 do(.) 的"compared with what" 由随机化协议明确定义',
    en: 'replace the observational main sample with RCT or experimental data — in an experiment the randomization protocol defines what do(.) is "compared with what"',
  },
  use_experimental_data_instead_of_self_report: {
    zh: '用 RCT / 实验性分配数据（消除自报告偏差）替代观察性主样本',
    en: 'replace the observational main sample with randomized or experimentally assigned data, which removes the self-report bias',
  },
  use_the_ar_set: {
    zh: '改用 Anderson-Rubin {level}% 弱工具稳健集 {interval}（已经算好了；在弱工具下依然有效），不要用 bootstrap 置信区间',
    en: 'use the Anderson-Rubin {level}% weak-instrument-robust set {interval} instead of the bootstrap interval — it is already computed and stays valid under a weak instrument',
  },
  use_the_robust_ar_set: {
    zh: '改用异方差稳健的 Anderson-Rubin {level}% 集 {interval}（在弱工具和异方差下都有效），不要用 bootstrap 置信区间',
    en: 'use the heteroskedasticity-robust Anderson-Rubin {level}% set {interval} instead of the bootstrap interval — it is valid under both a weak instrument and heteroskedasticity',
  },
}

export const GAP_SAYS: Record<string, Words> = {
  admg_effect_not_identifiable: {
    zh: '这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都到不了。若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7。',
    en: 'this ADMG effect query is out of reach of ADMG back-door, front-door and Tian / Shpitser ID alike. For the Line-7 case see PHASE_2_LATENT_CHARTER.md §7.',
  },
  admg_effect_reachable_only_by_instrument: {
    zh: '这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都到不了。工具变量升级路线确实到得了它，但那条路线是带假设的。若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7。',
    en: 'this ADMG effect query is out of reach of ADMG back-door, front-door and Tian / Shpitser ID alike. The instrument upgrade route does reach it, but that route carries assumptions. For the Line-7 case see PHASE_2_LATENT_CHARTER.md §7.',
  },
  atom_not_in_graph: {
    zh: '{part}指到了 `{atom}`，而它不在实例化变量集 V 中',
    en: '{part} names `{atom}`, which is not in the instantiated variable set V',
  },
  conditional_admg_not_identifiable: {
    zh: '条件 general-ID（IDC）效应：条件量 P(Y|do(X), given) 在这个 ADMG 上不可识别（Rule-2 交换加 ID 递归在条件估计量上撞到了 hedge）。也不会拿边缘量顶替它。',
    en: 'conditional general-ID (IDC) effect: P(Y|do(X), given) is not identifiable on this ADMG (Rule-2 exchange plus the ID recursion hit a hedge on the conditional estimand). The marginal is not substituted for it either.',
  },
  conditioning_event_has_probability_zero: {
    zh: 'P(γ|δ) 无定义：在每一个与该图相容的模型里，条件合取 δ 的概率都是 0（有效性违反，或两个世界互相矛盾），所以这个条件概率根本不存在。',
    en: 'P(γ|δ) is undefined: in every model the graph admits, the conditioning conjunction δ has probability 0 (a validity violation, or two worlds that contradict each other), so this conditional does not exist.',
  },
  counterfactual_bound_needs_entry: {
    zh: '反事实界需要 {key}',
    en: 'the counterfactual bound needs {key}',
  },
  counterfactual_not_identifiable: {
    zh: 'P(γ|δ) 经 ID*/IDC* 算法判定不可识别——存在 w-图 / 下标冲突见证（例如 PNS 的 P(y_x, y\'_{{x\'}}) 配一条 X→Y 直接边，或一条后门挡住了每一次条件移动）。不存在任何观测估计量。',
    en: 'ID*/IDC* found P(γ|δ) unidentifiable — there is a w-graph or subscript-conflict witness (PNS\'s P(y_x, y\'_{{x\'}}) beside a direct X→Y edge, say, or a back-door that blocks every conditioning move). No observational estimand exists.',
  },
  duplicate_treatment_atom: {
    zh: '联合处理向量里有重复的原子',
    en: 'the joint treatment vector repeats an atom',
  },
  framing_fields_unfilled: {
    zh: '变量 `{predicate}` 已声明，但缺 {count} 个操作化字段：{fields}',
    en: 'variable `{predicate}` is declared but is missing {count} operationalisation field(s): {fields}',
  },
  given_violates_backdoor: {
    zh: 'identify.given 违反了后门前置条件（含 X、Y，或 X 的某个后代）：{atoms}',
    en: 'identify.given breaks the back-door precondition (it holds X, Y, or a descendant of X): {atoms}',
  },
  graph_contradicts_supplied_marginal: {
    zh: 'Theta 中缺条目 {key}；theta 里有 {have}，但声明的图蕴含 {variable} ⊥ {{{extras}}} | {{{conditioning}}} 不成立，故不能用边缘量替代条件量。要么补上被要求的那个条件量，要么改图——「多给点 theta」是另一个问题的答案。',
    en: 'Theta has no entry for {key}; theta does hold {have}, but the declared graph does not imply {variable} ⊥ {{{extras}}} | {{{conditioning}}}, so the marginal cannot stand in for the conditional. Supply the conditional that was demanded, or change the graph — "more theta" answers a different question.',
  },
  interventional_risk_needs_distributions: {
    zh: 'P(Y=1|do(X)) 可识别，但算不出数——它需要的分布列在旁边。请把它们补上；或者直接给出来自随机实验的 experimental_risk_treated / experimental_risk_control，跳过它们。{note}',
    en: 'P(Y=1|do(X)) is identifiable but not computable — the distributions it needs are listed beside this. Supply them; or give experimental_risk_treated / experimental_risk_control from a randomised experiment and skip them.{note}',
  },
  interventional_risk_not_identifiable: {
    zh: 'P(Y=1|do(X)) 在这张图上不可识别，再多观测数据也换不出它。请提供来自随机实验的 experimental_risk_treated / experimental_risk_control，或者修改因果图。{note}',
    en: 'P(Y=1|do(X)) is not identifiable on this graph, and no amount of observational data buys it. Supply experimental_risk_treated / experimental_risk_control from a randomised experiment, or change the graph.{note}',
  },
  interventional_risk_unavailable_for_cell: {
    zh: 'P(Y=1|do(X={arm})) 推不出来（该效应从所给数据不可识别），少了它这个反事实单格就定不下来。请提供来自随机实验的 experimental_risk_treated / experimental_risk_control，或补上识别该效应所需的数据。{note}',
    en: 'P(Y=1|do(X={arm})) cannot be derived (that effect is not identifiable from the data given), and without it this counterfactual cell is not pinned down. Supply experimental_risk_treated / experimental_risk_control from a randomised experiment, or supply the data that identifies the effect.{note}',
  },
  interventional_risks_contradict_the_joint: {
    zh: '给出的干预风险与观测联合分布互相矛盾（一致性约束），没有任何 SCM 能同时产生两者——PN/PS/PNS 无定义。{detail}',
    en: 'the interventional risks given contradict the observed joint (the consistency constraint): no SCM produces both, so PN/PS/PNS are undefined. {detail}',
  },
  iv_first_stage_degenerate: {
    zh: '工具 {instrument} 推不动处理（加权后的第一阶段 ≈ 0），所以 Wald 比值无定义——没有顺从者子总体可供平均。换一个、或更强的工具，才是补上这一条的办法。',
    en: 'instrument {instrument} does not move the treatment (the weighted first stage is ≈ 0), so the Wald ratio is undefined — there is no complier subpopulation to average over. A different, or stronger, instrument is what fills this.',
  },
  iv_monotonicity_undeclared: {
    zh: '有 {count} 个有效工具能到达这个效应——{candidate}——但光有工具并不能定下用哪个估计量。声明 assumptions.monotonicity 可以得到顺从者中的 Wald LATE；内核不会替你在 Wald、2SLS 和界之间做选择。',
    en: '{count} valid instrument(s) reach this effect — {candidate} — but having an instrument does not settle which estimator to use. Declaring assumptions.monotonicity buys the Wald LATE among compliers; the kernel will not choose between Wald, 2SLS and bounds on your behalf.',
  },
  iv_stratum_weights_not_normalized: {
    zh: '给出的工具条件分层概率之和是 {total}，不是 1。LATE 比值对尺度不敏感，数照样算得出来，但报告里的处理变动是一个「顺从者占比」，对着一组根本不成其为分布的权重毫无意义。',
    en: 'the instrument\'s conditional stratum probabilities sum to {total}, not 1. The LATE ratio is scale-free so a number still comes out, but the treatment shift the report gives is a complier share, and that is meaningless against weights that are not a distribution.',
  },
  iv_wald_late_needs_entry: {
    zh: '工具变量 Wald LATE 需要它（工具 {instrument}）',
    en: 'the instrumental-variable Wald LATE needs it (instrument {instrument})',
  },
  iv_wald_late_needs_entry_in_stratum: {
    zh: '工具变量 Wald LATE 需要它（工具 {instrument}，给定 {given}）',
    en: 'the instrumental-variable Wald LATE needs it (instrument {instrument}, given {given})',
  },
  joint_effect_not_identifiable: {
    zh: '没有哪个有效的联合（处理集）后门调整集能挡住从处理向量到目标的所有真非因果路径，集合值 ID 也没能把联合效应点识别出来',
    en: 'no valid joint (treatment-set) back-door adjustment blocks every genuinely non-causal path from the treatment vector to the target, and set-valued ID did not point-identify the joint effect either',
  },
  joint_with_mediation_or_transport: {
    zh: 'v1 里，联合多处理干预不能和中介 / 迁移组合使用；后两者分解的是单处理效应，而联合分解是另一种操作',
    en: 'in v1 a joint multi-treatment intervention cannot be combined with mediation or transport; those two decompose a single-treatment effect, and the joint decomposition is a different operation',
  },
  mediator_off_the_directed_paths: {
    zh: '这个中介不落在任何一条有向路径 X → … → M → … → Y 上；请检查中介的声明或图上的边',
    en: 'this mediator lies on no directed path X → … → M → … → Y; check the mediator declaration or the edges in the graph',
  },
  mediator_set_off_the_directed_paths: {
    zh: '至少有一个中介不落在有向路径 X → … → M → … → Y 上（或者这个集合是空的 / 含 X 或 Y）；请检查中介的声明或图上的边',
    en: 'at least one mediator lies off the directed paths X → … → M → … → Y (or the set is empty, or holds X or Y); check the mediator declaration or the edges in the graph',
  },
  no_backdoor_or_frontdoor: {
    zh: '不存在有效的后门或前门调整',
    en: 'no valid back-door or front-door adjustment exists',
  },
  no_c_factor_witness: {
    zh: '完备的 ID/IDC 算法判定不可识别（找不到 c-factor 见证），也没有可用的工具变量升级路线。',
    en: 'the complete ID/IDC algorithm found it unidentifiable (no c-factor witness), and no instrument route is available either.',
  },
  path_coefficient_undeclared: {
    zh: '线性 SCM 反事实需要这条边上的通径系数：{parent} -> {child}',
    en: 'a linear SCM counterfactual needs this edge\'s path coefficient: {parent} -> {child}',
  },
  proximal_not_identifiable: {
    zh: 'P(Y|do(X)) 不可经近端识别（{criterion}）：{detail}',
    en: 'P(Y|do(X)) is not proximally identifiable ({criterion}): {detail}',
  },
  query_bound_atom_unresolved: {
    zh: '公式里有一个查询绑定的原子没有具体取值；数值层没有外部提供的代入就解不开它',
    en: 'the formula holds a query-bound atom with no concrete value; the numeric layer cannot resolve it without an externally supplied substitution',
  },
  sequential_exchangeability_fails: {
    zh: '处理 {treatment}（时刻 {time}）到 {outcome} 有一条后门路径是开的，测得的历史挡不住它——序贯可交换性不成立，g-formula 会给出一个有偏的数。请测量该混杂变量，或修改因果图。',
    en: 'a back-door path from treatment {treatment} (time {time}) to {outcome} is open and the measured history does not block it — sequential exchangeability fails and the g-formula would return a biased number. Measure that confounder, or change the graph.',
  },
  theta_entry_missing: {
    zh: 'Theta 中缺条目 {key}',
    en: 'Theta has no entry for {key}',
  },
  transport_not_identifiable: {
    zh: '找不到 S-可容许的调整集；在所声明的选择图下，源人群的效应无法迁移到目标人群：{detail}',
    en: 'no S-admissible adjustment set was found; under the declared selection diagram the source effect does not transport to the target population: {detail}',
  },
  unit_observation_missing: {
    zh: '确定性反事实需要这个变量在该个体上的观测值，归因这一步才能还原它的外生项',
    en: 'a deterministic counterfactual needs this unit\'s measured value for the variable, so that abduction can recover its exogenous term',
  },
}

export const SEVERITY_LABEL: Record<string, Words> = {
  blocking: {
    zh: '阻断',
    en: 'blocking',
  },
  important: {
    zh: '重要',
    en: 'important',
  },
  informational: {
    zh: '提示',
    en: 'for information',
  },
}

export const GAP_WANTED: Record<string, Words> = {
  ambiguous_variable_definition: {
    zh: '变量的操作化定义',
    en: 'an operational definition for the variable',
  },
  answer_is_bounds_not_point_estimate: {
    zh: '能把区间收成一个点的额外假设',
    en: 'an extra assumption that would narrow the interval to a point',
  },
  collider_conditioning_opens_backdoor: {
    zh: '一个不含对撞点的条件集',
    en: 'a conditioning set that does not hold the collider',
  },
  counterfactual_identification_assumption_required: {
    zh: '对一致性与组合公理的确认（走界的话，还要二值 + 单调）',
    en: 'confirmation of consistency and composition (and, for the bounds, binary + monotonicity)',
  },
  declared_type_data_mismatch: {
    zh: '让声明和数据对上——改声明，或换数据',
    en: 'a declaration and a column that agree — fix one or the other',
  },
  dichotomized_continuous_measure: {
    zh: '二分之前的那份连续测量',
    en: 'the continuous measurement, before it was dichotomized',
  },
  dose_response_data_required: {
    zh: '拟合剂量-响应曲线要的数据：X 的采样点、每点的样本量、要控制的混杂',
    en: 'the data a dose-response curve needs: sampling points for X, the sample size at each, and the confounders to control',
  },
  front_door_identification_assumption_required: {
    zh: '对前门那三条图形前提的确认',
    en: 'confirmation of the three front-door premises',
  },
  graph_learned_from_data: {
    zh: '对这张学出来的图的领域确认',
    en: 'domain confirmation of the graph that was learned',
  },
  graph_theta_independence_mismatch: {
    zh: '图与 CPT 的不一致——改图，或补上被要的那个条件量',
    en: 'the disagreement between the graph and the CPTs — fix the graph, or supply the conditional it asked for',
  },
  ill_defined_intervention_versions: {
    zh: '干预到底指哪个版本',
    en: 'which version of the intervention is meant',
  },
  iv_estimand_fallback_to_linear: {
    zh: '分得开那些层的样本——否则要接受 2SLS 答的是另一个量',
    en: 'a sample that can be cut into those strata — otherwise, accepting that 2SLS targets a different quantity',
  },
  iv_identification_assumption_required: {
    zh: '对工具变量所依赖的那条假设（单调性，或线性）的确认',
    en: 'confirmation of the assumption the instrument rests on (monotonicity, or linearity)',
  },
  llm_declared_ambiguity: {
    zh: '对上游声明的那处歧义的裁定',
    en: 'a decision on the ambiguity the upstream program declared',
  },
  low_confidence_input_data: {
    zh: '置信度更高的输入陈述',
    en: 'a higher-confidence input statement',
  },
  measurement_error_concern: {
    zh: '测量误差的信度参数，或一份验证子样本',
    en: 'a reliability coefficient for the measurement, or a validation subsample',
  },
  mediation_identification_assumption_required: {
    zh: '对中介识别假设的确认：跨世界可忽略性、无中间混杂',
    en: 'confirmation of the mediation assumptions: cross-world ignorability, and no intermediate confounder',
  },
  missing_assumption: {
    zh: '识别前提',
    en: 'an identification premise',
  },
  missing_distribution: {
    zh: '缺的那个分布',
    en: 'the distribution this is short of',
  },
  missing_iv_candidate: {
    zh: '有效的工具变量',
    en: 'a valid instrument',
  },
  missing_mediator_data: {
    zh: '中介的相关分布',
    en: 'the mediator\'s distributions',
  },
  missing_population_distribution: {
    zh: '目标人群的分布',
    en: 'the target population\'s distribution',
  },
  missing_structural_input: {
    zh: '结构输入',
    en: 'a structural input',
  },
  missing_unit_observation: {
    zh: '该单位的观测值',
    en: 'this unit\'s observed values',
  },
  outcome_model_quasi_separation: {
    zh: '结局不近乎确定的样本，或一个不会饱和的结局模型',
    en: 'a sample where the outcome is not near-deterministic, or an outcome model that does not saturate',
  },
  overidentification_rejected: {
    zh: '一组能通过过度识别检验的工具变量',
    en: 'instruments that survive the over-identification test',
  },
  propensity_overlap_violation: {
    zh: '在没有观测的那一臂上的样本',
    en: 'units in the arm that has none',
  },
  selection_on_collider_opens_path: {
    zh: '选择是怎么发生的，或一条不经过它的路径',
    en: 'how the selection happened, or a route that does not pass through it',
  },
  transport_identification_assumption_required: {
    zh: '对 S-可容许性与选择节点设定的确认',
    en: 'confirmation of S-admissibility and of the selection-node specification',
  },
  transport_source_conditional_unknown: {
    zh: '源人群上的分层条件分布 P(Y|do(X), Z)',
    en: 'the stratified conditional P(Y|do(X), Z) on the source population',
  },
  transport_target_distribution_unknown: {
    zh: '目标人群上的 P*(Z)',
    en: 'P*(Z) on the target population',
  },
  unattempted_layer_due_to_dispatch_conflict: {
    zh: '把没被处理的那一层单独发一次查询',
    en: 'a separate query for the layer that was not dispatched',
  },
  unidentifiable_no_admissible_set: {
    zh: '可识别的调整集，或另一条识别路径',
    en: 'an identifiable adjustment set, or another route to identification',
  },
  unmeasured_confounder_risk: {
    zh: '未测混杂的敏感性分析，或一个不靠「混杂都测到了」的设计',
    en: 'a sensitivity analysis for unmeasured confounding, or a design that does not assume every confounder was measured',
  },
  unverified_proposal_edge_on_query_path: {
    zh: '支持这条边的证据——现在它只是上游 LLM 的提议',
    en: 'evidence for that edge — right now it is only the upstream LLM\'s proposal',
  },
  weak_iv_instrument: {
    zh: '更强的工具变量，或一个对弱工具稳健的区间',
    en: 'a stronger instrument, or a weak-instrument-robust interval',
  },
}

export const PATTERN_WORDS: Record<string, Words> = {
  backdoor: {
    zh: '后门调整',
    en: 'back-door adjustment',
  },
  c_factor: {
    zh: 'ID 算法的一般解（c-factor 分解）',
    en: 'the ID algorithm\'s general solution (c-factor decomposition)',
  },
  front_door: {
    zh: '前门调整',
    en: 'front-door adjustment',
  },
  instrumental_variable: {
    zh: '工具变量',
    en: 'an instrumental variable',
  },
}

export const TIGHTNESS_WORDS: Record<string, Words> = {
  outer: {
    zh: '外界（不一定最紧）',
    en: 'an outer bound (not necessarily the tightest)',
  },
  sharp: {
    zh: '紧的',
    en: 'sharp',
  },
}

export const INTERVAL_WIDTH_WORDS: Record<string, Words> = {
  identification: {
    zh: '识别区间',
    en: 'identified interval',
  },
  outer_band: {
    zh: '识别区间的外带',
    en: 'outer band on the identified interval',
  },
  sampling: {
    zh: '置信区间',
    en: 'confidence interval',
  },
}

export const RISK_PROVENANCE_WORDS: Record<string, Words> = {
  backdoor_adjustment: {
    zh: '干预风险经后门标准化（g-formula）识别',
    en: 'the interventional risk is identified by back-door standardization (the g-formula)',
  },
  derived_identification: {
    zh: '干预风险由识别层从图上导出',
    en: 'the interventional risk was derived from the graph by the identification layer',
  },
  exogenous: {
    zh: '原因到结果没有后门路径，干预风险即条件概率',
    en: 'there is no back-door path from cause to effect, so the interventional risk is the conditional probability',
  },
  general_id_plug_in: {
    zh: '没有可用的调整集，干预风险由 general ID 识别出的估计量求值',
    en: 'no adjustment set is available, so the interventional risk is evaluated from the estimand general ID identified',
  },
  instrument_response_polytope: {
    zh: '干预风险无法点识别，本格改由工具变量的响应函数多面体直接框住',
    en: 'the interventional risk is not point-identified, so this cell is bracketed directly by the instrument\'s response-function polytope',
  },
  not_required: {
    zh: '两个世界重合，一致性直接给出答案，没有用到任何干预风险',
    en: 'the two worlds coincide, so consistency answers the cell outright and no interventional risk was used',
  },
  pinned_by_monotonicity: {
    zh: '干预风险无从获得，本格完全由所声明的单调性钉死',
    en: 'no interventional risk is available, so this cell is pinned entirely by the monotonicity that was declared',
  },
  user_experimental: {
    zh: '干预风险来自调用方提供的随机实验数据',
    en: 'the interventional risk comes from randomized experimental data the caller supplied',
  },
}

export const MEASUREMENT_SIDE_WORDS: Record<string, Words> = {
  combined: {
    zh: '暴露与结局都被误分类，两个通道各自求逆',
    en: 'both the exposure and the outcome are misclassified, and each channel is inverted on its own',
  },
  exposure: {
    zh: '暴露被误分类（结局当作测准了）',
    en: 'the exposure is misclassified (the outcome is taken as measured correctly)',
  },
  outcome: {
    zh: '结局被误分类（暴露当作测准了）',
    en: 'the outcome is misclassified (the exposure is taken as measured correctly)',
  },
}

export const MEASUREMENT_SCALE_WORDS: Record<string, Words> = {
  binary: {
    zh: '二值',
    en: 'binary',
  },
  continuous: {
    zh: '连续',
    en: 'continuous',
  },
  discrete: {
    zh: '离散',
    en: 'discrete',
  },
  nominal: {
    zh: '名义（档之间无大小）',
    en: 'nominal (levels with no order)',
  },
}

export const REFUTATION_WORDS: Record<string, Words> = {
  cell_feasible_set: {
    zh: '观测联合分布与给定的 P(Y=1|do(X)) 一起，把这一格的可行集压成了空集——没有单调性时这个交集必非空',
    en: 'the observational joint and the supplied P(Y=1|do(X)) leave this cell\'s feasible set empty — without the monotonicity that intersection is provably non-empty',
  },
  response_type_polytope: {
    zh: '把结局与处理反向的那些单位剔除之后，没有任何响应型分布能重现 P(X, Y | Z)——工具变量与这张表本身是相容的',
    en: 'no distribution over response types reproduces P(X, Y | Z) once the units whose outcome moves against the treatment are removed — the instrument and the table are compatible on their own',
  },
}

export const NDE_NIE_CONDITION_WORDS: Record<string, Words> = {
  M1: {
    zh: 'X 到 Y 还有调整集挡不住的后门路径',
    en: 'there is still a back-door path from X to Y that the adjustment set does not block',
  },
  M2: {
    zh: 'X 到中介 M 还有调整集挡不住的后门路径',
    en: 'there is still a back-door path from X to the mediator M that the adjustment set does not block',
  },
  M3: {
    zh: '中介 M 到 Y 还有后门路径 —— 控制了 X 和调整集也挡不住，而且图里没有任何变量能挡住它',
    en: 'there is a back-door path from the mediator M to Y — controlling for X and the adjustment set does not block it, and no variable in the graph can',
  },
  M4: {
    zh: '能挡住那条后门的变量是有的，但它是 X 的后代 —— 控制它会连要测的那条因果路径一起挡掉（典型是「中间混杂器」：既被 X 影响、又同时影响 M 和 Y 的变量）',
    en: 'a variable that would block that back-door does exist, but it is a descendant of X — controlling for it would block the causal path being measured along with it (typically an intermediate confounder: a variable X affects that in turn affects both M and Y)',
  },
}

export const OUTCOME_ERROR_DESIGN_WORDS: Record<string, Words> = {
  back_door: {
    zh: '区间比结局测准时宽 {factor} 倍 —— 后门调整设计：残差取自 Y 对（暴露＋调整集）的最小二乘投影，这个倍数就是精度代价本身；点估计不受影响',
    en: 'the interval is {factor} times wider than it would be with the outcome measured correctly — a back-door design: the residual comes from the least-squares projection of Y on (exposure + adjustment set), and that factor is the precision cost itself; the point estimate is unaffected',
  },
  front_door: {
    zh: '区间比结局测准时至多宽 {factor} 倍 —— 前门设计：残差取自 Y 对（暴露＋中介＋调整集）的结局模型；前门的方差里还有一项完全不含结局残差，σ²_v 折不进去，所以这个倍数是精度代价的上界而不是代价本身（本仓自己的前门估计量上实测：报 1.25 倍，真实区间只宽 1.09 倍）。而且这条路线上点估计未必不受影响：前门图假定了一个未观测的混杂，测量误差只要与它有关，动的就是点估计本身，而不只是区间',
    en: 'the interval is at most {factor} times wider than it would be with the outcome measured correctly — a front-door design: the residual comes from the outcome model of Y on (exposure + mediator + adjustment set); the front-door variance also carries a term with no outcome residual in it at all, into which σ²_v does not fold, so this factor is an upper bound on the precision cost rather than the cost itself (measured on this repository\'s own front-door estimator: it reports 1.25×, and the interval is only 1.09× wider). And on this route the point estimate is not necessarily unaffected: the front-door graph assumes an unobserved confounder, and measurement error related to it moves the point estimate itself rather than only the interval',
  },
  instrumental_variable: {
    zh: '区间比结局测准时宽 {factor} 倍 —— 工具变量设计：残差是围绕 IV 系数的结构残差，不是最小二乘残差；2SLS 的夹心方差此时正好多出 σ²_v 一项，所以这个倍数同样是精度代价本身；点估计不受影响，它要的是误差与工具无关，而不是与暴露、调整集无关',
    en: 'the interval is {factor} times wider than it would be with the outcome measured correctly — an instrumental-variable design: the residual is the structural residual around the IV coefficient rather than a least-squares one, and the 2SLS sandwich variance gains exactly one σ²_v term here, so the factor is again the precision cost itself; the point estimate is unaffected, since what it needs is error independent of the instrument, not of the exposure and adjustment set',
  },
}

export const OUTCOME_ERROR_PREMISE_WORDS: Record<string, Words> = {
  instruments: {
    zh: '这个设计立在 E[V | Z] = 0 上，而这是一句关于「工具变量」的断言，不是关于设计的；没有具名的工具，就没有变量可以让这句话去谈，评估会披露一条带窟窿的前提。用复数是因为过度识别的系统对每一个工具各立一条这样的断言、每条都能单独为假——只写其中一个，会把一条低估了实际假设的前提记进台账',
    en: 'the premise this design rests on is E[V | Z] = 0, a claim about the INSTRUMENTS rather than about the design; without named instruments there is no variable to make that claim about, and the assessment would disclose a premise with a hole in it. Plural because an over-identified system rests on one such claim PER instrument, each separately able to be false — naming only one of them would put a premise on the ledger that understates what is being assumed',
  },
  mediators: {
    zh: '前门结局模型要在中介上取条件，这正是这个设计比后门设计更大的原因；没有中介，这个设计就「是」后门设计，而那个已经有名字了',
    en: 'the front-door outcome model conditions on the mediator, which is what makes this design a superset of the back-door one; without a mediator the design IS the back-door design, and that one already has a name',
  },
  treatment_coefficient: {
    zh: '这里的残差是结构残差 Var(Y − βX − γ\'W)，围绕工具变量系数取，而不是围绕 Y 对设计的最小二乘投影取；没有 β̂ 就没有东西可以围绕，而最小二乘残差是关于另一个模型的、另一个更小的数',
    en: 'the residual here is the structural Var(Y − βX − γ\'W) taken around the IV coefficient, not around an OLS projection of Y on the design; without β̂ there is nothing to take it around, and the OLS residual is a different, smaller number about a different model',
  },
}

export const QUERY_PART_WORDS: Record<string, Words> = {
  causation_query: {
    zh: 'causation 查询',
    en: 'the causation query',
  },
  counterfactual_event: {
    zh: '反事实事件',
    en: 'the counterfactual event',
  },
  longitudinal_spec: {
    zh: '纵向 spec',
    en: 'the longitudinal spec',
  },
  proximal_role: {
    zh: 'proximal 查询的角色',
    en: 'a proximal role',
  },
  query: {
    zh: '查询',
    en: 'the query',
  },
  scm_counterfactual_query: {
    zh: 'scm_counterfactual 查询',
    en: 'the scm_counterfactual query',
  },
}

export const QUERY_ROLE_WORDS: Record<string, Words> = {
  exposure: {
    zh: '暴露',
    en: 'exposure',
  },
  instrument: {
    zh: '工具变量',
    en: 'instrument',
  },
  on_path_covariate: {
    zh: '路径上协变量',
    en: 'on-path covariate',
  },
  outcome: {
    zh: '结局',
    en: 'outcome',
  },
}

export const RECOVERY_WORDS: Record<string, Words> = {
  from_missingness: {
    zh: '所声明的缺失机制（判据是 Mohan-Pearl-Tian 的有序因子分解）',
    en: 'the declared missingness mechanism (judged by Mohan-Pearl-Tian\'s ordered factorisation)',
  },
  from_selection: {
    zh: '所声明的选择机制（判据是 Bareinboim-Pearl 的选择后门）',
    en: 'the declared selection mechanism (judged by Bareinboim-Pearl\'s selection back-door criterion)',
  },
}

export const REFUSAL_SAYS: Record<string, Words> = {
  adjustment_all_missing: {
    zh: '调整集里的 {column} 从未被观测到，它的边际 P({column}) 无法恢复',
    en: 'the adjustment column {column} is never observed, so its marginal P({column}) cannot be recovered',
  },
  adjustment_not_discrete: {
    zh: '调整集里的 {column} 有 {levels} 个观测层级、或取值不是整数；恢复估计要在后门集上分层，所以每个调整变量都必须离散（至多 {cap} 个整数层级）。连续混杂需要一个 P(Z) 的模型，不在范围内',
    en: 'the adjustment column {column} has {levels} observed levels or non-integer values; the recovery estimator stratifies on the back-door set, so every adjustment variable must be discrete (at most {cap} integer levels). A continuous confounder needs a model for P(Z) and is out of scope',
  },
  argument_foreign_to_design: {
    zh: '{design} 这个设计没有 {argument} 的位置——它属于 {owners}：{premise}',
    en: 'the {design} design has no place for {argument}; it belongs to {owners}: {premise}',
  },
  argument_missing_for_design: {
    zh: '{design} 这个设计要有 {argument}：{premise}',
    en: 'the {design} design needs {argument}: {premise}',
  },
  argument_not_a_number: {
    zh: '{argument} 必须是一个有限的数，收到的是 {given}',
    en: '{argument} has to be a finite number, and it was given {given}',
  },
  argument_not_given: {
    zh: '{argument} 没有给。这不是「给的值不对」——它根本没有出现，所以下面的每一条判据都没有可判的东西',
    en: '{argument} was not given. This is not a value that failed a test — nothing arrived, so there was nothing for any of the tests below it to judge',
  },
  arm_order_unreadable: {
    zh: '{what} 给的是 {given} 这一对：两个状态是有了，而没有东西说出哪个是对照臂。这一对要写成 [对照, 处理]，对照取假值、处理取真值（比如 [0, 1] 或 [False, True]）——混淆矩阵的哪一列对哪一臂，就是这么读出来的',
    en: '{what} was given the pair {given}: two states, and nothing in them says which is the control arm. The pair has to read as [control, treated] with a falsy control and a truthy treated (e.g. [0, 1] or [False, True]) — that is how the correction tells which column of the matrix belongs to which arm',
  },
  atom_not_in_graph: {
    zh: '干预或目标原子不在这个 SCM 的变量集里',
    en: 'the intervention or target atom is not in the SCM\'s variable set',
  },
  cause_or_effect_not_binary: {
    zh: '这个量要求 {column} 是二值列；实际取值是 {values}',
    en: 'this quantity requires a binary column {column}; got values {values}',
  },
  conditioning_too_fine: {
    zh: '条件列 {column} 取 {distinct_values} 个不同的值，超过这一版每列枚举的 {cap} 档；每层大约还有 {rows_per_level} 行，所以卡住的是这一版的枚举上限，不是样本',
    en: 'the conditioning column {column} takes {distinct_values} distinct values, past the {cap} per column this build enumerates; its strata would still hold about {rows_per_level} rows each, so the limit is this build\'s and not the sample\'s',
  },
  continuous_adjustment: {
    zh: '调整协变量 {column} 有 {levels} 个不同取值（超过 {cap}）；这个饱和分层公式在离散的层上求和，连续协变量没有层可分',
    en: 'the adjustment covariate {column} has {levels} distinct values (over {cap}); this saturated stratified formula sums over discrete strata, and a continuous covariate has none',
  },
  continuous_mediator: {
    zh: '中介 {mediator} 在这份数据上有 {levels} 个不同取值（超过 {cap}）；前门插值要在中介的每一层上精确求和，层数到这个量级就不是可承受的枚举了。连续中介要的是密度估计，暂未建',
    en: 'the mediator {mediator} takes {levels} distinct values here (over {cap}); the front-door plug-in sums exactly over every mediator stratum, and at this many the enumeration is not affordable. A continuous mediator needs density estimation and is deferred',
  },
  continuous_outcome: {
    zh: '结局 {outcome} 有 {states} 个取值（超过 {cap}）；混淆矩阵校正要对每个结局取值命名，需要一个离散结局',
    en: 'the outcome {outcome} has {states} values (over {cap}); a confusion-matrix correction names every outcome value and so needs a discrete outcome',
  },
  convergence_failure: {
    zh: '{backend} 这个后端在拟合中抛了错，而不是收敛到一个解；这一步没有产出数',
    en: 'the {backend} backend raised during the fit rather than converging on a solution; no number came out of this step',
  },
  corrected_design_not_positive_definite: {
    zh: '校正后的设计矩阵 Σ_obs − E 不是正定的。单看每一列，可靠度都还是正的；几列同时被声明有误差时，逐列判据是必要而不充分的——这组误差方差合起来超过了数据里的联合变异，校正无从定义',
    en: 'the corrected design matrix Σ_obs − E is not positive definite. Column by column every reliability is still positive; with several columns declared mismeasured the per-column test is necessary and not sufficient — these error variances taken together exceed the joint variation in the data, and the correction is undefined',
  },
  counterfactual_cell_cross_variable: {
    zh: '反事实单格估计干预的变量与它条件其上的变量是同一个：得到 do({intervened})，而观测的是 {observed}',
    en: 'the counterfactual cell estimator intervenes on the SAME variable it conditions on; got do({intervened}) with {observed} observed',
  },
  counterfactual_cell_not_binary: {
    zh: '反事实单格估计只处理布尔量；{label} 上得到的是 {given}',
    en: 'the counterfactual cell estimator is boolean-only; {label} is {given}',
  },
  counterfactual_inputs_infeasible: {
    zh: '声明的单调性被数据推翻了：{refuted_by}。要改的是这条假设，不是数据',
    en: 'the declared monotonicity is refuted by the data: {refuted_by}. What has to change is the assumption, not the data',
  },
  degenerate_recovered_exposure: {
    zh: '分层 z={stratum} 恢复出的真实暴露边际非正（P(X*=1|z)={p_treated}，P(X*=0|z)={p_control}）；条件风险因此无定义——混淆矩阵在这一层里信息太弱，识别不了效应',
    en: 'the stratum z={stratum} recovers a non-positive true exposure marginal (P(X*=1|z)={p_treated}, P(X*=0|z)={p_control}), so the conditional risk is undefined — the confusion matrix is too weakly informative to identify the effect in that stratum',
  },
  degenerate_reliability: {
    zh: '声明给 {variable} 的测量误差方差是 {error_variance}，而 {variable} 在其余设计变量之下的方差只有 {residual_variance}，可靠度 λ = {reliability} ≤ 0。这等于说这一列里没有一点真实变异——校正要除以 λ，声明和数据在这一列上是矛盾的',
    en: 'the measurement-error variance declared for {variable} is {error_variance}, and {variable}\'s variance given the rest of the design is only {residual_variance}, so the reliability λ = {reliability} ≤ 0. That says the column holds no true variation at all — the correction divides by λ, and the declaration contradicts the data in that column',
  },
  differential_by_the_mismeasured_variable: {
    zh: 'differential_by={axis} 正是这条通道在误测的那个变量（{role}）；它的混淆矩阵本来就是按真实{role}状态索引的，再按它分一次说不出新东西。这条通道可以按 {alternatives} 差异化',
    en: 'differential_by={axis} is the very variable this channel mismeasures (the {role}); its confusion matrix is already indexed by the true {role} state, so differing by it again says nothing new. This channel may differ by {alternatives}',
  },
  differential_by_unknown: {
    zh: 'differential_by={axis} 既不是 {home}，也不在这次校正条件化的协变量 {adjustment} 里。差异轴必须是校正本来就在其上分层的变量，否则「这一行该用哪个矩阵」没有可查的答案',
    en: 'differential_by={axis} is neither {home} nor one of the covariates this correction conditions on ({adjustment}). The differential axis has to be a variable the correction already stratifies on, or there is nothing to look up which matrix a row belongs to',
  },
  differential_combined_misclassification_deferred: {
    zh: '暴露 {exposure} 和结局 {outcome} 都给了混淆矩阵，而其中至少一个是 differential 的。联合校正把观测表分解成 M_x · P_true · M_yᵀ，这只在两个矩阵都恒定时成立；differential 的矩阵由另一条通道正在误测的那个层级选出，于是这个分解——以及建立在它上面的校正——不成立',
    en: 'a confusion matrix was supplied for both the exposure {exposure} and the outcome {outcome}, and at least one of them is differential. The combined correction factorises the observed table as M_x · P_true · M_yᵀ, which holds only while each matrix is constant; a differential matrix is selected by a level the other channel mismeasures, so the factorisation — and the correction built on it — does not apply',
  },
  differential_level_uncovered: {
    zh: '{axis}={level} 这一层没有提供混淆矩阵；差异性矩阵集必须覆盖差异轴上每一个观测到的层',
    en: 'no confusion matrix was supplied for {axis}={level}; the differential matrix set must cover every observed level of the differential axis',
  },
  differential_levels_mismatch: {
    zh: '差异性校正要给 {axis} 的每一层各配一个混淆矩阵，而这次给了 {matrices} 个矩阵、{levels} 个层级；两者必须一一对上，否则「哪个矩阵管哪一层」是按位置猜出来的',
    en: 'a differential correction gives every level of {axis} its own confusion matrix, and this call supplied {matrices} matrices for {levels} levels; the two have to line up one for one, or which matrix applies where is a guess made by position',
  },
  differential_levels_not_the_axis_levels: {
    zh: '差异性矩阵是按 {axis} 的层级索引的，而 {axis} 在这里取到的是 {expected}，这次给的层级是 {given}。这两组必须是同一组——多出来的层级没有数据，少掉的层级没有矩阵',
    en: 'the differential matrices are indexed by the levels of {axis}, which here takes {expected}, and the levels supplied are {given}. The two have to be the same set — a level too many has no data and a level too few has no matrix',
  },
  differential_spec_incomplete: {
    zh: '差异性误分类要 confusion_matrices= 和 differential_levels= 成对给出（每一层一个矩阵），这次没给的是 {missing}；缺了任何一半，「哪个矩阵管哪一层」就无从说起',
    en: 'differential misclassification needs confusion_matrices= and differential_levels= together, one matrix per level, and {missing} was not given; without either half there is no saying which matrix applies where',
  },
  do_risk_not_identifiable: {
    zh: '在这张图上，P({outcome}=1|do({exposure})) 没有可用的后门调整集，所以从观测分布里点识别不出来——最常见的原因是有一个没测到的混杂同时影响 {exposure} 和 {outcome}',
    en: 'on this graph P({outcome}=1|do({exposure})) has no admissible back-door adjustment set, so it is not point-identified from the observational distribution — most often because some unmeasured confounder affects both {exposure} and {outcome}',
  },
  do_risk_not_identifiable_by_any_route: {
    zh: 'P({outcome}=1|do({exposure})) 这个估计量跑过的三条路都到不了：没有可用的后门调整集（多半是未测混杂），两个臂都没有 ID 算法给出的估计量，图上也没有单个工具变量。不是某一条路没走通，是全部',
    en: 'P({outcome}=1|do({exposure})) is out of reach on all three routes this estimator runs: no admissible back-door adjustment set (most often an unmeasured confounder), no ID-algorithm estimand for either arm, and no single instrument on the graph. Not one route failing — all of them',
  },
  duplicate_input: {
    zh: '{what} 里同一样东西出现了两次（{given}）；它的每一项要指向不同的东西',
    en: '{what} names the same thing twice ({given}); its entries have to be distinct',
  },
  empty_outcome: {
    zh: '结局列 {outcome} 没有任何观测值',
    en: 'the outcome column {outcome} has no observed values',
  },
  exposure_not_binary: {
    zh: '暴露误分类校正建的是二值暴露：混淆矩阵是 2×2 的，两列分别属于「真实未暴露」和「真实已暴露」。这次声明的暴露状态是 {states}；多值暴露要的是一个更大的矩阵，暂未建',
    en: 'the exposure-misclassification correction is built for a binary exposure: the confusion matrix is 2×2, one column for truly-unexposed and one for truly-exposed. The exposure states declared here are {states}; a multi-level exposure needs a larger matrix and is deferred',
  },
  exposure_not_continuous: {
    zh: '回归校准建的是连续暴露上的经典可加误差，而暴露 {column} 在这份数据上只取到 {levels} 个不同值（低于 {floor}）。离散或二值的暴露不是「测量偏了一点」，是「被归错了类」，走混淆矩阵那条路',
    en: 'regression calibration is built for classical additive error on a continuous exposure, and the exposure {column} takes only {levels} distinct values here (below {floor}). A discrete or binary exposure is not measured with a small offset but classified into the wrong category, which is what the confusion-matrix correction is for',
  },
  external_data_required: {
    zh: '{exposure} 对 {outcome} 的效应在这种选择偏倚下，只有拿到外部无偏数据才恢复得出来（{needed}）。在对撞限制过的样本上算普通后门估计会有偏，所以不产出',
    en: 'the effect of {exposure} on {outcome} is recoverable from this selection bias only with external unbiased data ({needed}). The ordinary back-door estimate on the collider-restricted sample would be biased and is withheld',
  },
  inputs_contradict_by_consistency: {
    zh: 'P(Y=1|do(X={intervention}))={given} 与观测联合分布对不上：一致性把它锁在 [{lower}, {upper}] 里。两个数据来源互相矛盾，这里没有哪条假设需要改',
    en: 'P(Y=1|do(X={intervention}))={given} cannot hold with this observational joint: consistency confines it to [{lower}, {upper}]. The two sources contradict each other, and no assumption here is at fault',
  },
  inputs_disagree: {
    zh: '{one} 是 {one_is}，{other} 是 {other_is}；这两者必须一一对上',
    en: '{one} is {one_is} and {other} is {other_is}; the two have to line up one for one',
  },
  instrument_absorbed_by_conditioning: {
    zh: '把 {conditioning} 从 {instrument} 里投影掉之后，{instrument} 就不剩变异了（残差平方和 {residual_sum_of_squares}）。两阶段最小二乘照样会给出一个数，而那个数与 {instrument} 毫无关系——这跟「工具太弱」不是一回事',
    en: 'once {conditioning} is partialled out of {instrument} there is no variation left in it (residual sum of squares {residual_sum_of_squares}). Two-stage least squares would still return a number and that number would not depend on {instrument} at all — which is not the same thing as a weak instrument',
  },
  insufficient_support: {
    zh: '识别公式要在 {cells} 这一格上取 {quantity}，而数据里这一格没有行；那一项没有可估的东西，模型在那里给出的数只会是外推',
    en: 'the identifying formula needs {quantity} in the cell {cells}, and the data has no rows there; the term has nothing to be estimated from, and a model\'s number in it would be extrapolation',
  },
  intervention_is_target: {
    zh: '干预和目标必须是两个不同的变量',
    en: 'the intervention and the target must be distinct variables',
  },
  interventional_risk_not_identifiable: {
    zh: '要给出这一格，还需要 P(Y=1 | do(X={intervention}))：它在这张图上识别不出来，调用也没有给；只有观测联合分布的话，这一格就只能落在 [0, 1] 里',
    en: 'this cell needs P(Y=1 | do(X={intervention})), which is not identified on this graph and was not supplied; with the observational joint alone the cell sits anywhere in [0, 1]',
  },
  intractable_estimand: {
    zh: '识别出来的估计量树宽过大，变量消元算不动（{limit}）；在这张 ADMG 上它超出了数值 plug-in 的能力',
    en: 'the identified estimand has too high a treewidth to evaluate by variable elimination ({limit}); it is beyond the numeric plug-in\'s reach on this ADMG',
  },
  invalid_monotonicity: {
    zh: '单调性只能是 \'non_decreasing\' 或 \'non_increasing\'；得到的是 {declared}',
    en: 'monotonicity must be \'non_decreasing\' or \'non_increasing\'; got {declared}',
  },
  iv_model_infeasible: {
    zh: '在 {nx}×{ny}×{nz} 个层级上，没有任何一个响应型上的分布能在工具独立性 + 排他性之下重现观测到的 P(X,Y|Z) 表——线性规划无可行解。工具变量不等式在这个基数下不一定充分，所以指不出是哪一条不等式；小样本时这也可能是模型边界附近的抽样噪声',
    en: 'at {nx}×{ny}×{nz} levels no distribution over response types reproduces the observed P(X,Y|Z) table under instrument independence and exclusion — the linear program is infeasible. The instrumental inequality is not known here to be sufficient at this cardinality, so no single inequality can be pointed at; on a small sample this may also be sampling noise near the model boundary',
  },
  iv_model_refuted: {
    zh: '观测到的 P(X,Y|Z) 表违反了工具变量不等式：在处理的第 {level_index} 档上 Σ_y max_z P(Y=y, X=x | Z=z) = {statistic} > 1（Pearl 1995；二值情形即 Balke-Pearl 1997 式(6)）。这个不等式只用到独立性和排他性，所以违反它就是数据在说：这个工具变量本身的假设不成立',
    en: 'the observed P(X,Y|Z) table violates the instrumental inequality: at treatment level index {level_index}, Σ_y max_z P(Y=y, X=x | Z=z) = {statistic} > 1 (Pearl 1995; Balke-Pearl 1997 eq 6 in the binary case). That inequality uses only independence and exclusion, so violating it is the data saying the instrument\'s own assumptions do not hold',
  },
  joint_first_stage_degenerate: {
    zh: '{n_instruments} 个工具变量合起来也解释不了处理的任何变异（联合第一阶段统计量是 {statistic}）；它们定义的矩条件里没有可解的斜率',
    en: 'the {n_instruments} instruments together explain no variation in the treatment (the joint first-stage statistic is {statistic}); the moment condition they define has no slope to solve for',
  },
  linear_program_failed: {
    zh: '界的两个线性规划没有一致地给出不可行证书（求解器状态 {statuses}：{diagnostic}）；只有当两支都证明约束无解时，数据才算否证了这个模型，所以这一次没有对模型下任何结论。',
    en: 'the two bounds programs did not both certify infeasibility (solver statuses {statuses}: {diagnostic}); the data refutes the model only when both prove the constraints admit nothing, so nothing has been concluded about the model here.',
  },
  malformed_argument: {
    zh: '{argument} 读的是 {shape} 这个结构，收到的是 {given}',
    en: '{argument} is read as {shape}, and it was given {given}',
  },
  matrix_not_column_stochastic: {
    zh: '{what} 的每一列是一个真实状态在观测状态上的分布，各自应当加起来等于 1；实际的列和是 {sums}',
    en: 'each column of {what} is one true state\'s distribution over the observed states and has to sum to 1; the column sums are {sums}',
  },
  matrix_not_finite: {
    zh: '{what} 里有不是有限数的元素',
    en: '{what} holds entries that are not finite numbers',
  },
  matrix_not_numeric: {
    zh: '{what} 不是一个数值数组',
    en: '{what} is not a numeric array',
  },
  matrix_not_probabilities: {
    zh: '{what} 的元素要落在 [0, 1] 里才是概率',
    en: '{what} holds entries outside [0, 1], so they are not probabilities',
  },
  matrix_wrong_shape: {
    zh: '{what} 要是 {expected} 才配得上它连接的那些状态，收到的是 {given}',
    en: '{what} has to be {expected} to match the states it maps between; it is {given}',
  },
  mediator_not_discrete: {
    zh: '中介 {mediator} 的取值不落在整数上（例如 {values}）。前门插值要在它的每一层上精确求和，而分数取值给不出层——这跟层太多不是一回事，取值再少也一样',
    en: 'the mediator {mediator} does not take integer values (for instance {values}). The front-door plug-in sums exactly over its strata, and fractional values do not give any — which is not the same as having too many, and does not improve with fewer',
  },
  mediator_strata_intractable: {
    zh: '前门分层的交叉积是 {combinations}，超过了 {cap} 组合的上限；中介取值组合太多，无法精确枚举',
    en: 'the front-door stratum cross-product is {combinations}, over the {cap}-combination cap; there are too many mediator level combinations to enumerate exactly',
  },
  mismeasured_covariate_not_continuous: {
    zh: '被声明有测量误差的协变量 {column} 只取到 {levels} 个不同值（低于 {floor}）；协变量这一侧只建了连续变量的校正，离散协变量的误分类校正暂未建',
    en: 'the covariate {column}, declared mismeasured, takes only {levels} distinct values (below {floor}); on the covariate side only the continuous correction is built, and misclassification of a discrete covariate is deferred',
  },
  mismeasured_covariate_not_in_adjustment: {
    zh: '给 {variable} 提供了测量误差方差，而它既不是暴露、也不在后门调整集 {adjustment} 里；一个混杂要先被调整，才谈得上被校正',
    en: 'a measurement-error variance was supplied for {variable}, which is neither the exposure nor a covariate in the back-door adjustment set {adjustment}; a confounder must be adjusted for to be corrected',
  },
  mismeasured_variable_not_in_design: {
    zh: '为 {variable} 提供了测量误差，但它不在设计变量 {design} 里（设计变量 = 暴露及其后门调整集）。一个混杂只有被调整了才谈得上被校正',
    en: 'measurement error was supplied for {variable}, which is not among the design variables {design} (the exposure and its back-door adjustment set). A confounder has to be adjusted for to be corrected',
  },
  missing_column: {
    zh: '数据里没有 {columns} 这些列，而查询点了它们的名字',
    en: 'the data has no column(s) {columns}, which the query names',
  },
  model_fit_failed: {
    zh: '结局或中介模型在全样本上拟合失败：{detail}',
    en: 'the outcome or mediator model failed to fit on the full sample: {detail}',
  },
  model_needs_binary: {
    zh: '{model} 只对二值列有定义，而 {columns} 不是二值的',
    en: '{model} is defined for binary columns, and {columns} are not',
  },
  no_complete_case_rows: {
    zh: '{cells} 这一格里没有一行是完整的——行是有的，而每一行都在恢复公式要读的列上缺值',
    en: 'no row in the cell {cells} is complete — the rows are there and every one of them is missing a value in a column the recovery formula reads',
  },
  no_design_to_split_around: {
    zh: '量化结局误测要把残差方差拆开，而这个拆分是围绕识别效应的那条设计取的；P({outcome}|do({exposure})) 在这张图上既不是后门识别、也不是前门识别，还没有工具变量，于是没有设计可以围绕。结局上的经典可加误差不改变任何条件均值——缺席的是精度代价，不是点估计',
    en: 'quantifying a mismeasured outcome means splitting the residual variance, and that split is taken around the design that identifies the effect; P({outcome}|do({exposure})) is here neither back-door nor front-door identified and has no instrument, so there is no design to take it around. A classical additive error on the outcome leaves every conditional mean unchanged — what is missing is the precision cost, not the point',
  },
  no_first_stage: {
    zh: '{instrument} 在这份样本里推不动 {treatment}（第一阶段统计量是 {statistic}）。工具带来的对比要除以这个数才能变成效应，而它是零——图上那条相关箭头在数据里看不见',
    en: '{instrument} does not move {treatment} in this sample (the first-stage statistic is {statistic}). The contrast the instrument induces has to be divided by that number to become an effect, and it is zero — the graph\'s relevance arrow is not visible in the data',
  },
  no_identifying_design: {
    zh: '{exposure} 对 {outcome} 的效应在这张图上没有任何一条本包认识的识别路径：没有 back-door 调整集，没有 front-door 集，也没有工具变量。',
    en: 'the effect of {exposure} on {outcome} has no identifying design this package names on this graph: no back-door adjustment set, no front-door set, and no instrument.',
  },
  no_residual_variation: {
    zh: '结构残差平方和 û\'û 是 {sum_of_squares}：在这份样本上结局是处理的精确线性函数，于是 Sargan 统计量 n·û\'P_Z û / û\'û 是 0/0，过度识别检验无从谈起',
    en: 'the structural residual sum of squares û\'û is {sum_of_squares}: the outcome is an exact linear function of the treatment on this sample, so the Sargan statistic n·û\'P_Z û / û\'û is 0/0 and the over-identification test cannot be formed',
  },
  no_usable_resample: {
    zh: '{model} 估计量的 {resamples} 次 bootstrap 重抽样全部退化，区间没有可以取分位数的抽样',
    en: 'all {resamples} bootstrap resamples were degenerate for the {model} estimator, so there are no draws to take an interval from',
  },
  no_within_stratum_contrast: {
    zh: '{column} 只取到一个值的层：{strata}——层里有行，而两个臂之间的对比不在里面；这个估计量要在每一层内比较这两个臂，缺的那一臂只能由模型外推补上',
    en: 'strata in which {column} takes a single value: {strata} — the rows are there and the contrast between the arms is not among them; this estimator compares the two arms within each stratum, and the missing arm can only be supplied by a model\'s extrapolation',
  },
  non_positive_error_variance: {
    zh: '{variable} 的经典测量误差方差必须是一个正的有限数，收到的是 {given}。校正的每一步都要减去它或除以它，非正的值让整条式子没有定义',
    en: 'the classical measurement-error variance declared for {variable} has to be a positive finite number, and it was given {given}. Every step of the correction subtracts it or divides by it, and a non-positive value leaves the formula undefined',
  },
  not_a_joint_intervention: {
    zh: '联合干预至少需要两个处理，这次给的是 {count} 个（{treatments}）；单处理的效应走的是另一条路。',
    en: 'a joint intervention needs at least two treatments and this call named {count} ({treatments}); the single-treatment effect is answered by another route.',
  },
  not_a_probability: {
    zh: '{what} 要落在 [0, 1] 里才是概率；收到的是 {given}',
    en: '{what} has to lie in [0, 1] to be a probability; got {given}',
  },
  not_identifiable_by_general_id: {
    zh: '在这张 ADMG 上，{treatment} 对 {outcome} 的效应无法被 ID 算法点识别——没有可求值的 c-factor 估计量',
    en: 'the effect of {treatment} on {outcome} is not point-identified by the ID algorithm on this ADMG — there is no c-factor estimand to evaluate',
  },
  not_identifiable_by_idc: {
    zh: '在这张 ADMG 上，给定 {given} 时 {treatment} 对 {outcome} 的条件效应无法被 IDC 点识别——没有可求值的 c-factor 估计量',
    en: 'the conditional effect of {treatment} on {outcome} given {given} is not point-identified by IDC on this ADMG — there is no c-factor estimand to evaluate',
  },
  not_identifiable_counterfactual: {
    zh: '在这张 ADMG 上，P(γ|δ) 无法被 ID*/IDC* 算法识别——没有可求值的观测量',
    en: 'P(γ|δ) is not identifiable by the ID*/IDC* algorithm on this ADMG — there is no observational estimand to evaluate',
  },
  not_identifiable_proximal: {
    zh: '近端识别在 {criterion} 这一条上拒答：{detail}',
    en: 'proximal identification refused at {criterion}: {detail}',
  },
  not_identified: {
    zh: '时变策略效应在这张图上不可识别：序贯可交换性不成立——在已测历史之下，仍有某个处理到结局之间存在一条未阻断的后门。不产出数字，因为沿这条路算出来的数会有偏',
    en: 'the time-varying strategy effect is not identified on this graph: sequential exchangeability fails — given the measured history, some treatment still has an unblocked back-door to the outcome. No number is produced, because one computed on this route would be biased',
  },
  not_recoverable: {
    zh: '{estimand} 在{mechanism}之下恢复不出来：没有一条只由可观测量写成的分解能还原它。不产出数字，因为照现有数据直接算出来的那个数会有偏',
    en: '{estimand} is not recoverable under {mechanism}: no factorisation written only in observable quantities restores it. No number is produced, because one computed from the data as it stands would be biased',
  },
  option_answers_another_question: {
    zh: '{option} 算的是另一个估计量——它把 {ignored} 边际掉了，而这个查询要在它之下作比较',
    en: '{option} computes a different estimand: it marginalises over {ignored}, and this query compares within it',
  },
  outcome_does_not_vary: {
    zh: '结局列 {outcome} 在这份数据里几乎不变（标准差 {std}，极差 {spread}）；对它的任何拟合都会给出一条零效应曲线和零宽区间，而那是这份数据的形状，不是估计出来的答案。',
    en: 'the outcome column {outcome} barely varies in this data (std {std}, range {spread}); any fit of it returns a flat zero-effect curve with zero-width intervals, and that is the shape of this data rather than an estimated answer.',
  },
  outcome_error_exceeds_residual_variance: {
    zh: '声明的结局误差方差 σ²_v = {declared} 达到或超过了观测到的残差方差 Var({outcome}|D) = {residual}。这份噪声塞不进数据未能解释的那部分变异里，所以「声明的方差」「结局模型是线性的」「误差与设计独立」三条里至少有一条是假的——而最后那条正是点估计不受这个误差影响的原因。因此不出具评估',
    en: 'the declared outcome error variance σ²_v = {declared} meets or exceeds the observed residual variance Var({outcome}|D) = {residual}. The noise does not fit underneath the variation the data leave unexplained, so at least one of the declared variance, the linearity of the outcome model, and the independence of the error from the design is false — and that last one is what makes the point estimate immune to the error. No assessment is issued',
  },
  outcome_not_binary: {
    zh: '{outcome} 在数据里的取值是 {levels}；这个估计量只做二值结局',
    en: 'the observed values of {outcome} are {levels}; this estimator takes a binary outcome only',
  },
  outcome_not_continuous: {
    zh: '结局 {outcome} 只有 {distinct} 个不同取值；可加误差方差描述的是「连续」测量。离散结局属于误分类，它的误差确实会衰减效应，只是一个可加方差校正不了这种衰减',
    en: 'the outcome {outcome} has only {distinct} distinct values; an additive error variance describes a CONTINUOUS measurement. A discrete outcome is a misclassification object, and its error does attenuate the effect — but an additive variance is not what corrects that attenuation',
  },
  overlap_insufficient: {
    zh: '{column} 这一列（{role}）在整份样本里只取到 {levels}；对比要从它的取值差异里来，而这份数据里没有差异',
    en: 'the column {column} (the {role}) takes only {levels} in this whole sample; the contrast has to come from its variation, and this data has none',
  },
  probabilities_do_not_sum: {
    zh: '{what} 里的概率加起来是 {given}，不是 1',
    en: 'the probabilities in {what} sum to {given} rather than to 1',
  },
  proxy_cardinality_mismatch: {
    zh: '近端公式 (5) 要求每个代理都恰好呈现 k={k} 个层级；实际 |Z|={z}、|W|={w}。把更细的代理粗化到 k 层还没有支持',
    en: 'proximal formula (5) needs each proxy to present exactly k={k} levels; observed |Z|={z}, |W|={w}. Coarsening a finer proxy to k levels is not yet supported',
  },
  rank_condition_violated: {
    zh: 'P(W|Z,x) 奇异或病态：两个代理对未观测混杂的联合相关性不足以把测量通道求逆。在这份数据上这个效应不是近端可恢复的',
    en: 'P(W|Z,x) is singular or ill-conditioned: the proxies are not jointly relevant enough to the unobserved confounder to invert the measurement channel. The effect is not proximal-recoverable on this data',
  },
  rank_deficient_design: {
    zh: '节点 {node} 对父节点 {parents} 的 OLS 设计矩阵秩亏（存在共线回归元或常数列）；结构系数不唯一',
    en: 'the OLS design for node {node} on parents {parents} is rank-deficient (a collinear regressor or a constant column); the structural coefficients are not uniquely determined',
  },
  reference_missing_column: {
    zh: '外部无偏参照样本缺少 {columns} 这些列，而调整权重 P(z⁺)/P(z⁻|x,z⁺) 需要它们',
    en: 'the unbiased reference sample is missing the column(s) {columns} needed for the adjustment weights P(z⁺)/P(z⁻|x,z⁺)',
  },
  requires_a_point_estimate: {
    zh: '{exposure} 对 {outcome} 的效应在这里是靠工具变量识别的，而这条设计的拆分是围绕结构残差 Var(Y − βX − γ\'W)——也就是围绕 β̂ 本身——取的。这次查询没有产出点估计，也就没有 β̂ 可以围绕，因此不出评估',
    en: 'the effect of {exposure} on {outcome} is identified here through an instrument, and that design\'s split is taken around the structural residual Var(Y − βX − γ\'W) — around β̂ itself. No point estimate was produced for this query, so there is no β̂ to take it around; no assessment is issued',
  },
  requires_backdoor_identification: {
    zh: '{exposure} 对 {outcome} 的效应在这里是可识别的，但不是通过 back-door 调整；而这项校正只接在 back-door 调整之上，所以没有给出校正后的结果。',
    en: 'the effect of {exposure} on {outcome} is identified here, but not through back-door adjustment, and this correction composes with back-door adjustment only, so no corrected result is produced.',
  },
  response_model_too_large: {
    zh: '处理／结局／工具在这份数据上有 {nx}×{ny}×{nz} 个观测层级，响应函数划分因此有 {nx}^{nz}·{ny}^{nx} 个响应型，超过本包求解的 {cap} 个。锐界是存在的，被拒绝的是那个线性规划——它要在每个 bootstrap 重抽样上重解一次。层级这么多的列通常是连续的，而响应函数模型描述不了连续变量；把它粗化，方法就回到可及范围里',
    en: 'treatment, outcome and instrument have {nx}×{ny}×{nz} observed levels here, so the response-function partition has {nx}^{nz}·{ny}^{nx} types — above the {cap} this package solves. The sharp interval exists; what is declined is the LP, re-solved once per bootstrap replicate. A column with this many levels is usually a continuous one that no response-function model describes, and coarsening it brings the method back in reach',
  },
  rows_outside_the_strata: {
    zh: '按 {columns} 切出来的层只放下了 {rows} 行里的 {covered} 行；其余的行带着这个切法安置不了的取值，把权重在这些层上归一，描述的就是另一个人群',
    en: 'the strata cut by {columns} hold {covered} of {rows} rows; the rest carry values the cut cannot place, and weights normalised over these strata describe a different population',
  },
  sample_too_small: {
    zh: '样本量 {n} 低于估计所需的下限（{minimum}）',
    en: 'the sample size {n} is below the minimum ({minimum}) for estimation',
  },
  singular_confusion_matrix: {
    zh: '{role}的混淆矩阵不可逆（|det| = {determinant}，低于阈值 {floor}）：作为测量模型它对真实的{role}没有携带可用信息，校正无从定义——它没区分开的东西，再多数据也换不回来',
    en: 'the {role} confusion matrix is not invertible (|det| = {determinant}, below the floor of {floor}): as a measurement model it carries no usable information about the true {role}, so the correction is undefined — and no quantity of data recovers what it does not distinguish',
  },
  singular_confusion_matrix_in_stratum: {
    zh: '{axis}={level} 这一层的{role}混淆矩阵不可逆（|det| = {determinant}，低于阈值 {floor}）：差异性校正给每一层各配一个矩阵，别的层替不了它——各层不同正是这个模型的主张——所以校正在这一层无从定义',
    en: 'the {role} confusion matrix for {axis}={level} is not invertible (|det| = {determinant}, below the floor of {floor}): a differential correction gives every level its own matrix and no other level\'s can stand in — that they differ is what the model claims — so the correction is undefined in that level',
  },
  singular_design: {
    zh: '{design}在这份样本上是奇异的——它的那些列共线——于是需要它的那个拟合没有唯一解；最小范数解只是众多选择里的一个，所以不产出数字',
    en: '{design} is singular on this sample — its columns are collinear — so the fit that needs it has no unique solution; a minimum-norm answer would be one choice among many, and no number is produced',
  },
  states_incomplete: {
    zh: '{column} 观测到的取值 {values} 不在声明的混淆矩阵状态 {states} 里；矩阵必须覆盖每一个观测到的取值',
    en: 'the observed values {values} of {column} are not among the declared confusion-matrix states {states}; the matrix must cover every observed value',
  },
  strata_would_be_too_thin: {
    zh: '条件列 {column} 在 {rows} 行上取 {distinct_values} 个不同的值，切出来每层平均只有 {rows_per_level} 行——达不到一个层里每个工具臂所需的 {minimum_per_arm} 行。这是样本的限制，不是这一版的',
    en: 'the conditioning column {column} takes {distinct_values} distinct values over {rows} rows, so its strata would hold about {rows_per_level} rows each — short of the {minimum_per_arm} per instrument arm a stratum needs. The limit is the sample\'s, not this build\'s',
  },
  target_value_absent: {
    zh: '查询问的是 {column}（{role}）取 {value} 的那一档，而这一列在这里只有 {observed} 这些取值；没有这一档，也就没有可以报的数',
    en: 'the query asks about {column} (the {role}) at {value}, and here that column takes only {observed}; with no such level there is no number to report',
  },
  too_few_inputs: {
    zh: '{what} 至少要 {needed} 个，只收到 {given} 个',
    en: '{what} needs at least {needed}, and {given} were given',
  },
  too_many_joint_treatments: {
    zh: '联合效应最多支持 {cap} 个处理（饱和基是 2^K − 1 列，交互项是 2^K 个角点的有限差分）；实际是 {count} 个（{treatments}）',
    en: 'the joint effect caps at {cap} treatments (the saturated basis is 2^K − 1 columns and the interaction is a 2^K-corner finite difference); got {count} ({treatments})',
  },
  too_many_strata: {
    zh: '条件集 {conditioning} 把样本切成 {strata} 层，超过这一版枚举的 {cap} 层；没有哪一列单独过界，是它们的乘积过了',
    en: 'the conditioning set {conditioning} cuts the sample into {strata} strata, past the {cap} this build enumerates; no one column is over on its own — their product is',
  },
  too_sparse_to_estimate: {
    zh: '{where} 上的行数是 {given}，低于这个估计量在那里报一个数所要求的 {needed}；行是有的，只是不够',
    en: 'the number of rows at {where} is {given}, below the {needed} this estimator requires before it will report a number there; the rows are present and there are not enough of them',
  },
  treatment_levels_differ: {
    zh: '联合干预的角点是所有处理同时取同一对取值，而 {treatments} 的取值集是 {level_sets}——不是同一对，这个角点没有定义',
    en: 'a joint intervention\'s corner puts every treatment at one shared pair of values, and the level sets of {treatments} are {level_sets} — not one pair, so the corner is undefined',
  },
  treatment_not_binary: {
    zh: '{treatment} 在数据里的取值是 {levels}；这个估计量做的是两个取值之间的对比，只接受二值处理',
    en: 'the observed values of {treatment} are {levels}; this estimator contrasts two levels and takes a binary treatment only',
  },
  undefined_conditioning_event: {
    zh: '被条件的事件 {event} 概率为 0，所以这个条件概率无定义；给不出数',
    en: 'the conditioning event {event} has probability 0, so the conditional is undefined; no number can be produced',
  },
  unit_underobserved: {
    zh: '这个单位缺少 {variable} 的事实取值；abduction 无法恢复它的外生项',
    en: 'the unit is missing a factual value for {variable}; abduction cannot recover its exogenous term',
  },
  unknown: {
    zh: '它抛出的错误在本版本里没有对应的名字，所以这里说不出更具体的原因。',
    en: 'the error it raised has no name in this build, so nothing more specific can be said here.',
  },
  unknown_option: {
    zh: '{option} 只认这几个取值：{known}；收到的是 {given}',
    en: '{option} takes one of {known}; it was given {given}',
  },
}

export const REMEDY_WORDS: Record<string, Words> = {
  change_design: {
    zh: '这批数据本身给不出这个对比，要一个能制造它的设计——随机化实验，或图里一个工具变量',
    en: 'these data cannot produce the contrast; it takes a design that creates one — a randomised experiment, or an instrument on the graph',
  },
  change_input: {
    zh: '改一下传给 {subject} 的值',
    en: 'change what you passed for {subject}',
  },
  supply_data_stratum: {
    zh: '需要覆盖 {subject} 这一层的数据',
    en: 'supply data covering the stratum {subject}',
  },
  supply_data_variation: {
    zh: '需要 {subject} 在数据里取到不止一个值',
    en: 'supply data in which {subject} takes more than one value',
  },
  supply_input: {
    zh: '把 {subject} 作为参数传进来',
    en: 'pass {subject}',
  },
  use_method: {
    zh: '改用 {subject}',
    en: 'use {subject} instead',
  },
}

export const SINGULAR_MATRIX_WORDS: Record<string, Words> = {
  design_covariance: {
    zh: '设计矩阵的协方差 Σ',
    en: 'the design covariance Σ',
  },
  instrument_gram: {
    zh: '工具变量的 Gram 矩阵 Z\'Z',
    en: 'the instruments\' Gram matrix Z\'Z',
  },
  non_exposure_design_covariance: {
    zh: '设计矩阵里非暴露那几列的协方差',
    en: 'the covariance of the design\'s non-exposure columns',
  },
  outcome_and_mediator_fit: {
    zh: '结局模型与中介模型共用的设计矩阵',
    en: 'the design matrix the outcome and mediator models share',
  },
  robust_weight_matrix: {
    zh: '有效 GMM 那一步用来加权的稳健权重矩阵 Ŝ',
    en: 'the robust weight matrix Ŝ that the efficient GMM step weights with',
  },
  saturated_joint_design: {
    zh: '2^K 个角点的饱和联合设计矩阵',
    en: 'the saturated joint design matrix over the 2^K corners',
  },
}
