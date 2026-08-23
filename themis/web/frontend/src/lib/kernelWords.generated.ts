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
