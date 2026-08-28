// GENERATED FILE — DO NOT EDIT.
//
// Written by themis/output/reader_words.py from the kernel's own glosses.
// Regenerate with `python -m themis.output.reader_words`; the suite fails
// when this file and the kernel disagree, so a hand edit is reverted by the
// next regeneration rather than kept.
//
// What is here: every closed vocabulary the browser RESTATES — the same
// words the report gives a reader, in every language this build writes —
// and, at the end, the kernel's punctuation, which is not a vocabulary but
// is the same fact about the reader's language and is needed wherever this
// surface joins a list or two sentences. What is not: the tables that render
// a vocabulary in the browser's own terms (a tier's plain-language gloss, a
// status's blurb, a refusal's head/lead/tail) and the two the kernel
// deliberately has no word for (a gap carries its own description; a query
// kind is glossed by a whole question line).
import type { Words } from './language'

export const REGION_SHAPE_WORDS: Record<string, Words> = {
  bounded: {
    zh: '数据把整组系数都框住了（置信域有界）',
    en: 'the data pin the whole coefficient vector down (the region is bounded)',
  },
  empty: {
    zh: '没有任何一组系数能通过检验——在这个水平上，数据否掉了「这些工具有效 + 结果方程线性」这套假设本身',
    en: 'no coefficient vector survives the test — at this level the data refute the premise itself: these instruments being valid together with a linear outcome equation',
  },
  unbounded: {
    zh: '有方向是数据约束不了的（置信域无界）——这些工具变量在那个方向上说不出话，不是算错了',
    en: 'some direction is left unconstrained (the region is unbounded) — these instruments say nothing along it, which is a fact about them and not an error',
  },
  whole_space: {
    zh: '这些工具变量什么也没排除（置信域是整个空间）',
    en: 'nothing at all is ruled out (the region is the whole space)',
  },
}

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

export const ASSUMPTION_CLAIM_WORDS: Record<string, Words> = {
  U_sufficient_confounder_and_proxies_satisfy_miao_model_f: {
    zh: 'U 是充分混杂，且两个 proxy 满足 Miao 的 model f',
    en: 'U is a sufficient confounder and the two proxies satisfy Miao\'s model f',
  },
  additive_exogenous_noise_abducted_per_unit: {
    zh: '外生噪声可加，按单位 abduct 回来',
    en: 'the exogenous noise is additive and abducted per unit',
  },
  adjustment_set_blocks_mediator_outcome_backdoor_given_treatment: {
    zh: '给定 X 后调整集阻断 M→Y 的后门',
    en: 'given X, the adjustment set blocks the back-door from M to Y',
  },
  adjustment_set_blocks_mediatorset_outcome_backdoor_given_treatment: {
    zh: '给定 X 后调整集阻断整个中介集到 Y 的后门',
    en: 'given X, the adjustment set blocks the back-door from the whole mediator set to Y',
  },
  adjustment_set_blocks_xy_and_my_backdoors: {
    zh: '调整集同时阻断 X→Y 与 M→Y 的后门',
    en: 'the adjustment set blocks both the X→Y and the M→Y back-doors',
  },
  adjustment_set_blocks_xy_and_my_chain_backdoors: {
    zh: '调整集同时阻断 X→Y 与整条中介链到 Y 的后门',
    en: 'the adjustment set blocks both the X→Y back-door and the back-doors from the whole mediator chain to Y',
  },
  adjustment_set_is_valid_backdoor_set: {
    zh: '调整集是合法的后门集',
    en: 'the adjustment set is a valid back-door set',
  },
  admg_structure_correct_including_latent_confounders: {
    zh: 'ADMG 结构正确，包括潜混杂（双向边）的位置',
    en: 'the ADMG structure is correct, including where the latent confounders (bidirected edges) sit',
  },
  backdoor_adjustment_: {
    zh: '后门调整：{suffix}',
    en: 'back-door adjustment: {suffix}',
  },
  backdoor_adjustment_set_sufficient_: {
    zh: '后门调整集充分：{suffix} 阻断 X→Y 的所有后门路径',
    en: 'the back-door adjustment set is sufficient: {suffix} blocks every back-door path from X to Y',
  },
  backdoor_from_mediator_to_outcome_blocked_by_treatment: {
    zh: '给定 X 后 M→Y 的后门已被阻断',
    en: 'given X, the back-door from M to Y is blocked',
  },
  binary_cause_and_effect: {
    zh: '原因与结果都是二值的',
    en: 'both the cause and the effect are binary',
  },
  binary_treatment_and_outcome: {
    zh: '处理与结局都是二值的',
    en: 'both the treatment and the outcome are binary',
  },
  chain_rule_factoring_of_joint_mediator_conditional: {
    zh: '联合中介的条件分布按链式法则分解',
    en: 'the joint mediator conditional is factored by the chain rule',
  },
  ci_not_cluster_robust_econml_dml_interval_ignores_: {
    zh: '置信区间不是簇稳健的：解析区间忽略了 {suffix} 的簇内相关，可能偏窄',
    en: 'the confidence interval is not cluster-robust: the analytic interval ignores within-cluster correlation on {suffix} and may be too narrow',
  },
  ci_via_analytic_influence_function: {
    zh: '置信区间由影响函数解析求得（非 bootstrap）',
    en: 'the confidence interval is analytic, from the influence function (not bootstrap)',
  },
  ci_via_pairs_cluster_bootstrap_on_: {
    zh: '置信区间由按 {suffix} 重采样整簇的 pairs cluster bootstrap 求得',
    en: 'the confidence interval comes from a pairs cluster bootstrap resampling whole clusters by {suffix}',
  },
  ci_via_percentile_bootstrap: {
    zh: '置信区间由百分位 bootstrap 求得',
    en: 'the confidence interval comes from a percentile bootstrap',
  },
  cluster_robust_influence_variance_on_: {
    zh: '影响函数方差按 {suffix} 做了簇稳健修正',
    en: 'the influence-function variance is cluster-robust on {suffix}',
  },
  conditional_effect_identified_via_idc_rule2_exchange: {
    zh: '条件效应经 IDC 规则 2 交换后点识别',
    en: 'the conditional effect is point-identified after the IDC rule-2 exchange',
  },
  conditional_exchangeability_given_adjustment_set: {
    zh: '给定调整集后处理可视为随机分配（无未观测混杂）',
    en: 'given the adjustment set, treatment can be taken as randomly assigned (no unmeasured confounding)',
  },
  conditional_from_own_complete_cases_marginal_from_its_own: {
    zh: '条件分布取自其自身的完整病例、边际取自其自身',
    en: 'the conditional comes from its own complete cases and the marginal from its own',
  },
  conditioning_set_blocks_instrument_outcome_backdoor_given_W: {
    zh: '给定条件集 W 后 IV 到结果的后门已被阻断',
    en: 'given the conditioning set W, the back-door from the instrument to the outcome is blocked',
  },
  confusion_matrix_invertible: {
    zh: '混淆矩阵可逆（|det| 已在估计时核验）',
    en: 'the confusion matrix is invertible (|det| checked at estimation time)',
  },
  consistency_and_no_interference: {
    zh: '一致性且无干扰：一个单位的处理不影响别人的结果',
    en: 'consistency and no interference: one unit\'s treatment does not affect another unit\'s outcome',
  },
  consistency_of_potential_outcomes: {
    zh: '一致性：观察到的 Y 等于该处理下的潜在结果',
    en: 'consistency: the observed Y equals the potential outcome under the treatment received',
  },
  consistency_of_potential_outcomes_under_joint_intervention: {
    zh: '一致性：联合干预下的潜在结果良定义',
    en: 'consistency: the potential outcome under the joint intervention is well defined',
  },
  consistency_well_defined_sustained_treatment_strategy: {
    zh: '一致性：所问的持续处理策略定义明确',
    en: 'consistency: the sustained treatment strategy being asked about is well defined',
  },
  constant_treatment_effect_else_estimand_is_weighted_average: {
    zh: '处理效应恒定；否则估计量是一个加权平均而非 ATE',
    en: 'the treatment effect is constant; otherwise the estimand is a weighted average rather than the ATE',
  },
  continuous_mediator_odds_ratio_approximation_rare_outcome: {
    zh: '连续中介的 OR 近似依赖罕见结局假设',
    en: 'the odds-ratio approximation for a continuous mediator rests on the rare-outcome assumption',
  },
  correct_parent_set_per_node_no_unmeasured_common_cause_of_a_node_and_its_parents: {
    zh: '每个节点的父集正确：节点与其父之间无未观测共同原因',
    en: 'each node\'s parent set is correct: no unmeasured common cause of a node and its parents',
  },
  correct_propensity_model_single_robust: {
    zh: '单稳健：一致性依赖倾向模型设定正确',
    en: 'singly robust: consistency rests on the propensity model being correctly specified',
  },
  correct_specification_of_covariate_transition_and_outcome_models: {
    zh: '协变量转移模型与结局模型设定正确',
    en: 'the covariate-transition and outcome models are correctly specified',
  },
  correct_specification_of_treatment_propensity_models: {
    zh: '各期处理倾向模型设定正确',
    en: 'the per-period treatment propensity models are correctly specified',
  },
  decomposition_reported_at_sample_mean_covariate_value: {
    zh: '分解在协变量的样本均值处报告',
    en: 'the decomposition is reported at the sample mean of the covariates',
  },
  design_error_classical_additive_on_: {
    zh: '连续设计列 {suffix} 上的测量误差是经典加性的：W=真值+U，U 均值 0，且与其余设计列、与给定真值的 Y 都独立',
    en: 'the measurement error on the continuous design column {suffix} is classical and additive: W=true+U, with U of mean 0 and independent both of the other design columns and of Y given the true values',
  },
  design_error_variance_known_and_fixed_on_: {
    zh: '设计列 {suffix} 的误差方差 σ²_u 已知且固定（来自验证研究或重复测量）——它进入校正本身，所以它错了错的是点估计，不只是区间宽度',
    en: 'the error variance σ²_u on design column {suffix} is known and fixed (from a validation study or repeated measures) — it enters the correction itself, so if it is wrong the point estimate is wrong, not only the width of the interval',
  },
  diagram_correct_including_unobserved_confounder_U_and_proxy_roles: {
    zh: '因果图正确，包括未观测混杂 U 与两个 proxy 的角色',
    en: 'the causal graph is correct, including the unobserved confounder U and the roles of the two proxies',
  },
  differential_misclassification_by_covariate_: {
    zh: '差异误分类：误分类率随协变量 {suffix} 而变，逐层用本层矩阵求逆',
    en: 'differential misclassification: the rates vary with covariate {suffix}, and each stratum is inverted with its own matrix',
  },
  differential_misclassification_by_exposure_arm_M_depends_on_X: {
    zh: '差异误分类：结局的误分类率随处理臂而变（检出偏倚）',
    en: 'differential misclassification: the outcome\'s misclassification rates vary with the treatment arm (detection bias)',
  },
  differential_misclassification_by_outcome_M_depends_on_Y: {
    zh: '差异误分类：暴露的误分类率随真实结局而变（回忆偏倚）',
    en: 'differential misclassification: the exposure\'s misclassification rates vary with the true outcome (recall bias)',
  },
  discrete_adjustment_strata: {
    zh: '调整集按离散分层处理',
    en: 'the adjustment set is handled as discrete strata',
  },
  discrete_variables_saturated_nonparametric_plug_in: {
    zh: '离散变量的饱和非参数代入估计（无函数形式假设）',
    en: 'a saturated non-parametric plug-in over discrete variables (no functional-form assumption)',
  },
  dose_binned_and_effects_estimated_per_bin: {
    zh: '剂量按相邻采样点的中点切成若干档，同一档内的剂量被当作可互换。档内的剂量差异因此被抹平，而档与档之间的非线性能保留下来——曲线的分辨率就是采样点的疏密',
    en: 'the dose is cut into bins at the midpoints between adjacent sampling points, and doses inside one bin are treated as INTERCHANGEABLE. Variation within a bin is flattened while non-linearity between bins survives — the curve\'s resolution is however finely the sampling points were spaced',
  },
  doubly_robust_outcome_OR_propensity_model_correct: {
    zh: '双稳健：结局回归或倾向模型任一设定正确即一致',
    en: 'doubly robust: consistent if either the outcome regression or the propensity model is correctly specified',
  },
  estimand_is_LATE_on_compliers_not_population_ATE: {
    zh: '估计量是 LATE（仅 complier 子人群），不是人群 ATE',
    en: 'the estimand is the LATE (compliers only), not the population ATE',
  },
  estimand_recoverable_ordered_factorization_valid: {
    zh: '估计量在该缺失图下可恢复：有序分解合法',
    en: 'the estimand is recoverable under this missingness graph: the ordered factorization is valid',
  },
  exogeneity_no_backdoor_path_do_risk_equals_conditional: {
    zh: '外生性：无后门路径，故 do-风险等于条件概率',
    en: 'exogeneity: there is no back-door path, so the do-risk equals the conditional probability',
  },
  external_reference_sample_is_unbiased: {
    zh: '外部参照样本本身无偏',
    en: 'the external reference sample is itself unbiased',
  },
  front_door_criterion_holds_on_graph: {
    zh: '前门准则在因果图上成立',
    en: 'the front-door criterion holds on the causal graph',
  },
  frontdoor_full_mediation: {
    zh: '中介集拦截 X→Y 的所有有向路径',
    en: 'the mediator set intercepts every directed path from X to Y',
  },
  frontdoor_mediator_outcome_backdoor_blocked_given_treatment: {
    zh: '给定 X 后中介到 Y 的后门已被阻断',
    en: 'given X, the back-door from the mediator to Y is blocked',
  },
  frontdoor_no_treatment_mediator_backdoor: {
    zh: 'X 到中介之间无未阻断的后门',
    en: 'there is no unblocked back-door between X and the mediator',
  },
  hajek_stabilized_weights: {
    zh: 'IPW 用 Hájek 稳定化权重（组内归一，方差更小）',
    en: 'IPW uses Hájek stabilized weights (normalized within group, lower variance)',
  },
  homoskedastic_errors_for_the_anderson_rubin_f_critical_value: {
    zh: '误差同方差——置信域的临界值按 F 分布取，异方差下该换成稳健形式',
    en: 'the errors are homoskedastic, which is what makes the region\'s F critical value the right one; under heteroskedasticity the robust form is needed',
  },
  horvitz_thompson_weights: {
    zh: 'IPW 用 Horvitz-Thompson 原始权重',
    en: 'IPW uses raw Horvitz-Thompson weights',
  },
  independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z: {
    zh: '两条误差通道在真值下相互独立（同一份记录上暴露和结局不会被一起写错）——这是单通道校正不需要、双边校正才需要的额外前提',
    en: 'the two error channels are independent given the truth (exposure and outcome are not mis-recorded together on the same record) — an extra premise the two-sided correction needs and the single-channel one does not',
  },
  interventional_risk_from_randomized_experiment: {
    zh: '本格所需的那一臂干预风险取自随机实验',
    en: 'the one interventional risk this cell needs comes from a randomized experiment',
  },
  interventional_risks_from_randomized_experiment: {
    zh: '两臂干预风险 P(Y|do X) 与 P(Y|do ¬X) 都取自随机实验',
    en: 'both interventional risks, P(Y|do X) and P(Y|do ¬X), come from a randomized experiment',
  },
  iv1_relevance: {
    zh: 'IV 与处理相关（第一阶段非零）',
    en: 'the instrument is relevant to treatment (non-zero first stage)',
  },
  iv1_relevance_instrument_affects_treatment: {
    zh: 'IV 与处理相关（第一阶段非零）',
    en: 'the instrument is relevant to treatment (non-zero first stage)',
  },
  iv1_relevance_instruments_affect_treatment: {
    zh: '各工具变量都与处理相关',
    en: 'every instrument is relevant to treatment',
  },
  iv2_exclusion_instrument_affects_outcome_only_via_treatment: {
    zh: '排他性：IV 只通过处理影响结果',
    en: 'exclusion: the instrument affects the outcome only through treatment',
  },
  iv2_exclusion_instruments_affect_outcome_only_via_treatment: {
    zh: '排他性：各工具变量都只通过处理影响结果',
    en: 'exclusion: every instrument affects the outcome only through treatment',
  },
  iv2_exclusion_instruments_affect_outcome_only_via_treatment_vector: {
    zh: '排他性：各工具变量只通过这一组处理影响结果',
    en: 'exclusion: every instrument affects the outcome only through the treatments being intervened on',
  },
  iv3_independence_instrument_independent_of_latent_confounders: {
    zh: 'IV 与潜混杂独立',
    en: 'the instrument is independent of the latent confounders',
  },
  iv3_independence_instrument_independent_of_unmeasured_confounders: {
    zh: 'IV 与未观测混杂独立',
    en: 'the instrument is independent of the unmeasured confounders',
  },
  iv3_independence_instruments_independent_of_latent_confounders: {
    zh: '各工具变量都与潜混杂独立',
    en: 'every instrument is independent of the latent confounders',
  },
  joint_conditional_exchangeability_given_adjustment_set: {
    zh: '联合可交换性：给定调整集后整个处理向量可视为随机分配',
    en: 'joint exchangeability: given the adjustment set, the whole treatment vector can be taken as randomly assigned',
  },
  joint_effect_point_identified_by_set_id_no_adjustment_set_exists: {
    zh: '联合效应由集合值 ID 点识别（不存在调整集）',
    en: 'the joint effect is point-identified by set-valued ID (no adjustment set exists)',
  },
  known_confusion_matrices_from_validation_studies: {
    zh: '两条通道的混淆矩阵都由验证研究给出且视为已知',
    en: 'both channels\' confusion matrices come from validation studies and are taken as known',
  },
  known_confusion_matrix_from_validation_study: {
    zh: '混淆矩阵由验证研究给出且视为已知、无抽样误差',
    en: 'the confusion matrix comes from a validation study and is taken as known and free of sampling error',
  },
  known_per_arm_confusion_matrices_from_validation_study: {
    zh: '逐处理臂的混淆矩阵由验证研究给出且视为已知',
    en: 'the per-arm confusion matrices come from a validation study and are taken as known',
  },
  known_per_covariate_stratum_confusion_matrices_from_validation_study: {
    zh: '逐协变量分层的混淆矩阵由验证研究给出且视为已知',
    en: 'the per-covariate-stratum confusion matrices come from a validation study and are taken as known',
  },
  known_per_outcome_confusion_matrices_from_validation_study: {
    zh: '逐结局水平的混淆矩阵由验证研究给出且视为已知',
    en: 'the per-outcome-level confusion matrices come from a validation study and are taken as known',
  },
  latent_cardinality_k_correct_and_proxies_have_exactly_k_levels: {
    zh: '潜变量类别数 k 正确，且两个 proxy 各恰有 k 个水平',
    en: 'the latent cardinality k is correct and each proxy has exactly k levels',
  },
  latent_cardinality_k_correct_and_the_declared_coarsening_folds_each_proxy_to_k_levels: {
    zh: '潜变量类别数 k 正确，且你声明的粗化把两个 proxy 各折成 k 组——哪些层级代表 U 的同一个状态是你的判断，数据不作答；换一个分组就是另一个数',
    en: 'the latent cardinality k is correct, and the coarsening you declared folds each proxy into k groups — which levels stand for the same state of U is your judgement and the data does not answer it; a different grouping is a different number',
  },
  linear_in_treatment_partially_linear_dml: {
    zh: '剂量-反应曲线在处理上是直线：Y = θ·T + g(W) + ε，其中 g 不受形状约束而 T 只以一次项进入。真实剂量效应若是弯的，拟合出来的是它的最佳直线近似——曲线的形状是假设的，不是量出来的',
    en: 'the dose-response curve is a STRAIGHT LINE in the treatment: Y = θ·T + g(W) + ε, with g unconstrained in shape and T entering only linearly. A dose effect that truly bends is fitted as its best straight-line approximation — the curve\'s shape is assumed here, not measured',
  },
  linear_in_treatment_with_nonparametric_nuisance: {
    zh: '剂量-反应曲线在处理上仍是直线，但两个 nuisance 拟合（Y~W、T~W）不必是——森林放开的是对协变量的形状约束，没有放开对剂量的那一条',
    en: 'the dose-response curve is still a STRAIGHT LINE in the treatment, though the two nuisance fits (Y~W and T~W) need not be — the forest relaxes the shape constraint on the covariates and NOT the one on the dose',
  },
  linear_mediator_model_with_normal_residual_variance: {
    zh: '中介模型为线性且残差方差为正态',
    en: 'the mediator model is linear with normal residual variance',
  },
  linear_outcome_regression: {
    zh: 'outcome 用线性回归建模',
    en: 'the outcome is modelled by linear regression',
  },
  linear_outcome_regression_with_saturated_treatment_interactions: {
    zh: 'outcome 用带饱和处理交互的线性回归',
    en: 'the outcome is modelled by linear regression with saturated treatment interactions',
  },
  linear_structural_equations_every_relevant_mechanism: {
    zh: '每条相关机制都设为线性结构方程',
    en: 'every relevant mechanism is taken to be a linear structural equation',
  },
  linear_structural_outcome_model_in_the_true_values: {
    zh: '真实结局模型对未观测的真值是线性的：Y=β0+βx·X*+βz\'·Z+ε——正是这条线性使矩量校正精确而非近似',
    en: 'the true outcome model is linear in the unobserved true values, Y=β0+βx·X*+βz\'·Z+ε — which is exactly what makes the moment correction exact rather than approximate',
  },
  linearity_of_first_and_second_stage: {
    zh: 'IV 的一、二阶段都设为线性',
    en: 'both IV stages are taken to be linear',
  },
  linearity_of_the_outcome_equation_in_the_treatment_vector: {
    zh: '结果方程对这一组处理设为线性',
    en: 'the outcome equation is taken to be linear in the treatments being intervened on',
  },
  logit_mediator_model: {
    zh: '中介用 logit 模型',
    en: 'the mediator is modelled by logit',
  },
  logit_outcome_link: {
    zh: 'outcome 用 logit 链接',
    en: 'the outcome uses a logit link',
  },
  logit_outcome_model_with_exposure_mediator_interaction: {
    zh: 'outcome 用带暴露×中介交互的 logit 模型',
    en: 'the outcome is modelled by logit with an exposure×mediator interaction',
  },
  logit_outcome_regression: {
    zh: 'outcome 用 logit 回归建模',
    en: 'the outcome is modelled by logit regression',
  },
  logit_outcome_regression_with_saturated_treatment_interactions: {
    zh: 'outcome 用带饱和处理交互的 logit 回归',
    en: 'the outcome is modelled by logit regression with saturated treatment interactions',
  },
  marginal_structural_model_additive_no_treatment_time_interaction: {
    zh: '边际结构模型是可加的（处理与时间无交互）',
    en: 'the marginal structural model is additive (no treatment-by-time interaction)',
  },
  mediator_intercepts_all_directed_paths_from_treatment_to_outcome: {
    zh: '中介拦截了 X→Y 的所有有向路径',
    en: 'the mediator intercepts every directed path from X to Y',
  },
  mediators_drawn_jointly_via_gaussian_residual_copula: {
    zh: '多个中介按高斯残差 copula 联合抽样',
    en: 'the mediators are drawn jointly through a Gaussian residual copula',
  },
  monotonicity_: {
    zh: '单调性：{direction}',
    en: 'monotonicity: {direction}',
  },
  monotonicity_assumed_: {
    zh: '单调性：{direction}——总体中没有结局与处理反向的单位；这条路线上没有可以反驳它的东西',
    en: 'monotonicity: {direction} — no unit in the population moves against the treatment, and nothing on this route could answer back',
  },
  monotonicity_assumed_x_never_prevents_y: {
    zh: '单调性：X 从不阻止 Y——这条把区间收紧成点，而这条路线上没有任何东西能反驳它',
    en: 'monotonicity: X never prevents Y — this is what tightens the interval to a point, and nothing on this route could answer back',
  },
  monotonicity_first_stage_effect_same_sign_for_all_units: {
    zh: '单调性：第一阶段效应对所有单位同号',
    en: 'monotonicity: the first-stage effect has the same sign for every unit',
  },
  monotonicity_no_defiers: {
    zh: '单调性：不存在 defier（处理方向对每个单位一致）',
    en: 'monotonicity: there are no defiers (treatment moves in one direction for every unit)',
  },
  monotonicity_refutable_: {
    zh: '单调性：{direction}——总体中没有结局与处理反向的单位；它作为模型限制进入响应型多面体，程序不可行就是数据在反驳它',
    en: 'monotonicity: {direction} — no unit in the population moves against the treatment; it enters the response-type polytope as a restriction, so an infeasible program is the data contradicting it',
  },
  monotonicity_refutable_x_never_prevents_y: {
    zh: '单调性：X 从不阻止 Y——它作为模型限制进入响应型多面体，不加它可行、加了不可行，就是数据在反驳这个方向',
    en: 'monotonicity: X never prevents Y — it enters the response-type polytope as a restriction of the model, so a program that is feasible without it and infeasible with it is the data contradicting the declared direction',
  },
  mtr_: {
    zh: '单调处理响应：{direction}——把无假设界的一侧收紧',
    en: 'monotone treatment response: {direction} — this tightens one side of the assumption-free bounds',
  },
  multi_level_covariates_entered_as_ordered_numbers: {
    zh: '调整集里有超过两档的列，它是以一个有序的数进模型的：第三档到第一档的距离，被当成第二档的两倍。如果这一列是渠道、科室、地区这类没有大小之分的分类，这个形式就不成立，调整不干净，效应会带偏。这一行出现，是因为没有人说过这列没有大小：把它声明为 `scale: "nominal"`，每一档就各占一项进模型，这条假设随之消失',
    en: 'an adjustment column with more than two levels entered the model as ONE ORDERED NUMBER: level three was taken to sit twice as far from level one as level two does. If the column names channels, departments or regions, which have no greater and lesser, the form does not hold, the adjustment is incomplete and the effect carries the difference. This row is here because nothing said the column has no order: declare it `scale: "nominal"` and each level enters as its own term, and the assumption goes away with it',
  },
  no_confounder_of_mediatorset_outcome_affected_by_treatment_outside_the_set: {
    zh: '中介集之外不存在被处理影响的中介–结局混杂',
    en: 'no mediator-outcome confounder affected by treatment sits outside the mediator set',
  },
  no_directed_edge_between_treatments: {
    zh: '两个处理之间没有有向边',
    en: 'there is no directed edge between the two treatments',
  },
  no_effect_of_exposure_that_confounds_mediator_outcome: {
    zh: '暴露不产生任何混杂中介–结局关系的效应',
    en: 'the exposure has no effect that confounds the mediator-outcome relation',
  },
  no_intermediate_confounder_affected_by_treatment: {
    zh: '不存在被处理影响的中间混杂（X 的后代同时影响 M 和 Y）',
    en: 'there is no intermediate confounder affected by treatment (a descendant of X that affects both M and Y)',
  },
  no_mediator_mediator_interaction_in_outcome_model: {
    zh: 'outcome 模型里中介之间没有交互项',
    en: 'the outcome model has no mediator-by-mediator interaction',
  },
  no_treatment_effect_modification_outside_z_in_either_pop: {
    zh: '两个人群中都不存在 Z 之外的效应修饰',
    en: 'neither population has effect modification outside Z',
  },
  no_unblocked_backdoor_from_treatment_to_mediator: {
    zh: 'X→M 段无未阻断的后门',
    en: 'the X→M leg has no unblocked back-door',
  },
  no_unmeasured_confounder_between_successive_mediators: {
    zh: '相邻中介之间无未观测混杂',
    en: 'successive mediators have no unmeasured confounder between them',
  },
  no_unmeasured_confounder_exposure_mediator_given_adjustment: {
    zh: '给定调整集后暴露–中介无未观测混杂',
    en: 'given the adjustment set, exposure–mediator has no unmeasured confounder',
  },
  no_unmeasured_confounder_exposure_outcome_given_adjustment: {
    zh: '给定调整集后暴露–结局无未观测混杂',
    en: 'given the adjustment set, exposure–outcome has no unmeasured confounder',
  },
  no_unmeasured_confounder_m_y_given_x_and_adjustment: {
    zh: '给定 X 与调整集后 M–Y 无未观测混杂',
    en: 'given X and the adjustment set, M–Y has no unmeasured confounder',
  },
  no_unmeasured_confounder_mediator_outcome_given_exposure_and_adjustment: {
    zh: '给定暴露与调整集后中介–结局无未观测混杂',
    en: 'given exposure and the adjustment set, mediator–outcome has no unmeasured confounder',
  },
  no_unmeasured_confounder_x_y_given_chain_and_adjustment: {
    zh: '给定整条中介链与调整集后 X–Y 无未观测混杂',
    en: 'given the whole mediator chain and the adjustment set, X–Y has no unmeasured confounder',
  },
  no_unmeasured_confounder_x_y_given_m_and_adjustment: {
    zh: '给定中介与调整集后 X–Y 无未观测混杂',
    en: 'given the mediator and the adjustment set, X–Y has no unmeasured confounder',
  },
  no_unmeasured_confounding_given_W: {
    zh: '无未观测混杂（given W）',
    en: 'no unmeasured confounding (given W)',
  },
  non_differential_misclassification_X_indep_YZ_given_Xtrue: {
    zh: '非差异误分类：给定真实暴露后，记录到的暴露与结局、协变量无关',
    en: 'non-differential misclassification: given the true exposure, the recorded exposure is independent of outcome and covariates',
  },
  non_differential_misclassification_Y_indep_XZ_given_Ytrue: {
    zh: '非差异误分类：给定真实结局后，记录到的结局与处理、协变量无关（同一张混淆矩阵适用于所有臂和层）',
    en: 'non-differential misclassification: given the true outcome, the recorded outcome is independent of treatment and covariates (one confusion matrix applies to every arm and stratum)',
  },
  outcome_error_classical_non_differential_on_: {
    zh: '结局 {suffix} 的测量误差是经典可加且非差异的（与暴露、调整集、真实结局独立，均值 0）——正因如此点估计不受它影响；若误差随暴露臂或真实结局而变，点估计有偏',
    en: 'the measurement error on outcome {suffix} is classical, additive and non-differential (independent of exposure, of the adjustment set and of the true outcome, with mean 0) — which is exactly why the point estimate is unaffected by it; if the error varied with the exposure arm or with the true outcome, the point estimate would be biased',
  },
  outcome_error_independent_of_the_front_door_latent_confounder_on_: {
    zh: '结局 {suffix} 的测量误差与前门图假定的那个未观测混杂无关。那个混杂按定义就没被测到，所以这一条没法用数据检验——不是「暂时没检验」，是这批数据里根本没有能检验它的东西；它若不成立，误差动的是点估计本身，不只是区间宽度',
    en: 'the measurement error on outcome {suffix} is unrelated to the unobserved confounder the front-door graph assumes. That confounder is by definition unmeasured, so this claim cannot be checked against the data — not "not checked yet", but nothing in this dataset could check it; if it fails, the error moves the point estimate itself and not only the width of the interval',
  },
  outcome_error_mean_independent_of_instrument_: {
    zh: '结局 {outcome} 的测量误差与工具变量 {instrument} 均值无关（E[V | {instrument}] = 0）—— IV 点估计不受这个误差影响，靠的正是这一条。它不是经典前提的放宽版：经典前提要求误差与暴露和调整集无关，这一条要求的是与工具无关，两者互不蕴含，检验了一个不等于检验了另一个',
    en: 'the measurement error on outcome {outcome} is mean-independent of the instrument {instrument} (E[V | {instrument}] = 0) — which is exactly what leaves the IV point estimate unaffected by that error. It is not a relaxed version of the classical premise: that one asks the error to be independent of the exposure and the adjustment set, this one asks it to be independent of the instrument, and neither implies the other, so having checked one is not having checked the other',
  },
  outcome_error_mean_independent_of_instrument_unsplit: {
    zh: '结局的测量误差与工具变量均值无关（{suffix}）',
    en: 'the outcome\'s measurement error is mean-independent of the instrument ({suffix})',
  },
  outcome_error_variance_known_and_fixed_on_: {
    zh: '结局 {suffix} 的测量误差方差 σ²_v 已知且固定：区间的精度代价按它折算，但不传播验证研究自身对 σ²_v 的不确定性',
    en: 'the measurement-error variance σ²_v on outcome {suffix} is known and fixed: the interval\'s precision cost is computed from it, but the validation study\'s own uncertainty about σ²_v is not propagated',
  },
  outcome_model_correctly_specified_at_chain_fixed_values: {
    zh: 'outcome 模型在链上固定值处设定正确',
    en: 'the outcome model is correctly specified at the values the chain is fixed to',
  },
  overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j: {
    zh: '过度识别约束成立（可用 Sargan 与稳健 Hansen J 检验）',
    en: 'the overidentifying restrictions hold (testable by Sargan and by the robust Hansen J test)',
  },
  overidentifying_restrictions_testable_via_sargan_homoskedastic: {
    zh: '过度识别约束成立（可用同方差 Sargan 检验）',
    en: 'the overidentifying restrictions hold (testable by the homoskedastic Sargan test)',
  },
  pearl_2001_four_conditions_hold_on_the_graph: {
    zh: 'Pearl 2001 中介分解四条件在因果图上成立',
    en: 'Pearl\'s 2001 four conditions for mediation decomposition hold on the causal graph',
  },
  positivity_both_instrument_arms_present_in_every_stratum: {
    zh: '重叠：每一层内工具变量的两个取值都出现',
    en: 'overlap: both values of the instrument appear in every stratum',
  },
  positivity_each_treatment_level_observed_within_history_strata: {
    zh: '重叠：每个处理水平在每条历史分层内都被观测到',
    en: 'overlap: every treatment level is observed within every history stratum',
  },
  positivity_every_conditioning_stratum_has_support: {
    zh: '重叠：识别公式条件到的每一层在数据中都有样本',
    en: 'overlap: every stratum the identification formula conditions on has units in the data',
  },
  positivity_every_conditioning_stratum_of_the_estimand_has_support: {
    zh: '重叠：估计量条件到的每一层在数据中都有样本',
    en: 'overlap: every stratum the estimand conditions on has units in the data',
  },
  positivity_every_contributing_stratum_has_support: {
    zh: '重叠：每个进入求和的层在数据中都有样本',
    en: 'overlap: every stratum entering the sum has units in the data',
  },
  positivity_every_sampled_dose_has_support_on_W: {
    zh: '重叠：每个采样剂量在所有 W 上都有支持',
    en: 'overlap: every sampled dose has support across W',
  },
  positivity_every_treatment_arm_has_support_in_each_stratum: {
    zh: '重叠：每一层内两个处理臂都有样本',
    en: 'overlap: both treatment arms have units in every stratum',
  },
  positivity_in_each_z_stratum_of_source: {
    zh: '重叠：源人群的每个 Z 层内都有样本',
    en: 'overlap: every Z stratum of the source population has units',
  },
  positivity_overlap_of_every_treatment_cell: {
    zh: '重叠：处理向量的每个组合格子在每层内都有样本',
    en: 'overlap: every cell of the treatment vector has units in every stratum',
  },
  positivity_overlap_of_treatment_arms: {
    zh: '重叠 / positivity：调整集每一层内两个处理臂都有样本',
    en: 'overlap / positivity: both treatment arms have units in every stratum of the adjustment set',
  },
  positivity_the_asked_arm_has_support_in_each_stratum: {
    zh: '重叠：被问的那个处理臂在每一层内都有样本',
    en: 'overlap: the arm being asked about has units in every stratum',
  },
  positivity_violated_some_strata_hold_one_arm: {
    zh: '重叠 / positivity 不成立（已逐层核对）：调整集里有层只含一个处理臂，那些层里缺的那一臂由结局模型外推补出，不是数据里的对比',
    en: 'overlap / positivity does NOT hold (checked cell by cell): strata of the adjustment set hold a single treatment arm, and the missing arm there is the outcome model\'s extrapolation rather than a comparison in the data',
  },
  propensity_clipped_to_floor_: {
    zh: '倾向得分被截断到下限 {floor}，有 {n} 个单位受此影响',
    en: 'the propensity score is clipped to a floor of {floor}, which affects {n} units',
  },
  propensity_clipped_unsplit: {
    zh: '倾向得分被截断（{suffix}）',
    en: 'the propensity score is clipped ({suffix})',
  },
  'rank_condition_P(W|Z,x)_invertible_verified_on_data': {
    zh: '秩条件：P(W|Z,x) 可逆（已在数据上核验）',
    en: 'rank condition: P(W|Z,x) is invertible (verified on the data)',
  },
  recovered_true_exposure_marginal_positive: {
    zh: '求逆恢复出的真实暴露边际为正（否则条件风险无定义）',
    en: 'the true-exposure marginal recovered by inversion is positive (otherwise the conditional risk is undefined)',
  },
  recursive_acyclic_scm_matching_the_declared_graph: {
    zh: 'SCM 是与所声明因果图一致的递归无环模型',
    en: 'the SCM is recursive and acyclic, and matches the declared causal graph',
  },
  s_admissibility_of_adjustment_set: {
    zh: '调整集满足 S-可容许性（迁移到目标人群的关键条件）',
    en: 'the adjustment set is S-admissible (the key condition for transporting to the target population)',
  },
  selection_backdoor_admissible_set: {
    zh: '选择后门可容许集成立',
    en: 'the selection back-door admissible set holds',
  },
  sequential_exchangeability_no_unmeasured_time_varying_confounding: {
    zh: '顺序可交换性：不存在未观测的时变混杂',
    en: 'sequential exchangeability: there is no unmeasured time-varying confounding',
  },
  sequential_ignorability_treatment_and_mediator: {
    zh: '顺序可忽略性：处理与中介都满足条件随机化（Imai 关键假设）',
    en: 'sequential ignorability: both treatment and mediator are conditionally randomized (Imai\'s key assumption)',
  },
  sequential_ignorability_treatment_and_mediator_set: {
    zh: '顺序可忽略性：处理与整个中介集都满足条件随机化',
    en: 'sequential ignorability: treatment and the whole mediator set are conditionally randomized',
  },
  strata_aggregated_by_complier_share_not_by_stratum_probability: {
    zh: '各层按 complier 份额加权（不是按层概率）——得到的是 complier 平均因果效应',
    en: 'strata are weighted by complier share rather than by stratum probability — what comes out is the complier average causal effect',
  },
  tmle_targeted_substitution_estimator: {
    zh: 'TMLE：对初始结局拟合做定标的代入估计',
    en: 'TMLE: a substitution estimator targeted on the initial outcome fit',
  },
  unconditional_exchangeability_treatment_is_marginally_randomized: {
    zh: '无条件可交换性：处理近似边际随机化（无需调整）',
    en: 'unconditional exchangeability: treatment is approximately marginally randomized (no adjustment needed)',
  },
  unconditional_exchangeability_treatments_marginally_randomized: {
    zh: '无条件可交换性：整个处理向量近似边际随机化',
    en: 'unconditional exchangeability: the whole treatment vector is approximately marginally randomized',
  },
  vanderweele_vansteelandt_2014_joint_natural_effect_conditions: {
    zh: 'VanderWeele-Vansteelandt 2014 联合自然效应条件成立',
    en: 'the VanderWeele-Vansteelandt 2014 conditions for joint natural effects hold',
  },
  zminus_reweighting_from_unbiased_reference_: {
    zh: 'Z⁻ 的重加权取自无偏参照样本（{suffix}）',
    en: 'the Z⁻ reweighting comes from an unbiased reference sample ({suffix})',
  },
  zplus_weights_from_unbiased_reference_: {
    zh: 'Z⁺ 的权重取自无偏参照样本（{suffix}）',
    en: 'the Z⁺ weights come from an unbiased reference sample ({suffix})',
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
  caller_chose: {
    zh: '你在问题里做的选择（方法必须有人选，它自己选不了）',
    en: 'your choice in the question — the method needs one and cannot make it',
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

export const BOUND_SIDE_WORDS: Record<string, Words> = {
  lower: {
    zh: '下界',
    en: 'lower',
  },
  upper: {
    zh: '上界',
    en: 'upper',
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

export const BOUNDS_NOTE_WORDS: Record<string, Words> = {
  a_sharper_method_was_declined_for_scale: {
    zh: '图里有工具 {instrument}，本来能给出这一臂上的 Balke-Pearl 锐界，但在 {treatment_levels}×{outcome_levels}×{instrument_levels} 个水平下它的响应函数划分有 {types} 种类型，超过本实现能解的 {cap} 种。这里给的是不加假设的下限区间 —— 报它是因为更紧的方法按规模被放弃了，不是因为没有更紧的方法。把某个变量的水平合并粗一些，锐界就又够得着了。',
    en: 'the graph has an instrument {instrument}, so a Balke-Pearl sharp bound on this arm was available, but at {treatment_levels}×{outcome_levels}×{instrument_levels} levels its response-function partition has {types} types, past the {cap} this implementation can solve. What is reported here is the assumption-free floor — reported because the sharper method was declined on size, not because there is no sharper method. Coarsen one variable\'s levels and the sharp bound is reachable again.',
  },
  one_side_tightened: {
    zh: '假设{direction}。相对 Manski 自然界，{side}这一侧收紧到 {to}，另一侧不变，结果含在自然界的区间里。',
    en: 'assuming {direction}. Against the Manski natural interval the {side} end tightens to {to} and the other is unchanged, so the result is contained in it.',
  },
  the_partition_has_this_many_types: {
    zh: '响应函数划分在处理 {treatment_levels} 个水平 × 结局 {outcome_levels} 个水平 × 工具 {instrument_levels} 个水平下有 {types} 种响应型，而用到的只有可观测的分布。',
    en: 'the response-function partition has {types} types at {treatment_levels} treatment levels × {outcome_levels} outcome levels × {instrument_levels} instrument levels, and nothing but observable distributions goes into it.',
  },
  width_is_the_off_arm_mass: {
    zh: '区间宽度 = {mass} —— 另一臂的人越少，界越紧；这个处理水平一个人都没有时，界退化成没有信息的 [0,1]。',
    en: 'the interval is {mass} wide — the fewer units sit at the other treatment levels, the tighter it gets, and with nobody at this one it degenerates to the uninformative [0,1].',
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
  numeric_anderson_rubin_region: {
    zh: '在数据上反演 Anderson-Rubin 检验，得到这一组系数的置信域',
    en: 'invert the Anderson-Rubin test on the data to get the confidence region for this group of coefficients',
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
  numeric_joint_general_id_estimate: {
    zh: '在数据上逐个取值组合求这一组处理的联合效应，以及它们之间的交互',
    en: 'estimate the joint effect of this group of treatments from the data one treatment combination at a time, and the interaction between them',
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
  vector_iv_criterion_check: {
    zh: '在图上验证这个工具变量对整组被干预的处理都有效（排他性与外生性）',
    en: 'verify on the graph that this instrument is valid for the whole group of treatments being intervened on (exclusion and exogeneity)',
  },
}

export const E_VALUE_UNDEFINED_WORDS: Record<string, Words> = {
  ate_not_finite: {
    zh: 'ATE={ate} 不是有限数；E 值无定义，连续结局这条路线需要一个有限的点估计',
    en: 'ATE={ate} is not a finite number; there is no E-value, and this route needs a finite point estimate',
  },
  baseline_on_boundary: {
    zh: '基线结局发生率 {rate} 正落在 [0,1] 的边界上，构不成风险比；这个估计的 E 值无定义',
    en: 'the baseline outcome rate {rate} sits on the boundary of [0,1], and that is not a risk ratio; this estimate has no E-value',
  },
  outcome_sd_not_usable: {
    zh: '结局标准差 {sd} 非正或非有限；Chinn 2000 的 SMD→RR 换算需要一个有意义的结局尺度，E 值无定义',
    en: 'the outcome standard deviation {sd} is not positive and finite; the Chinn 2000 SMD→RR conversion needs a meaningful outcome scale, so there is no E-value',
  },
  treated_rate_out_of_range: {
    zh: '推出来的处理组发生率 {rate} 落在 [0,1] 之外——线性 ATE 假设在这里已经不成立；风险比尺度上的 E 值没有意义，建议改用 logistic 结局模型重估',
    en: 'the implied treated rate {rate} falls outside [0,1] — the linear-ATE assumption has already failed here; an E-value on the risk-ratio scale means nothing, and a logistic outcome model is what would give one',
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

export const GAP_DESCRIBES: Record<string, Words> = {
  a_block_decomposition_does_not_split_a_path: {
    zh: '`mediators` 把这些中介当作一个块做联合 NDE/NIE；穿过其中单个中介的路径特定拆分不含在块的分解里 —— 它需要块本身不需要的额外条件，本仓明确列为作用域之外。',
    en: '`mediators` decomposes these into a joint NDE/NIE as one block; the path-specific split through a single mediator inside it is not part of the block\'s decomposition — it needs conditions the block itself does not, and this repository puts it explicitly out of scope.',
  },
  a_continuous_measure_was_cut_in_two: {
    zh: '二分化（dichotomization）：识别路径上有连续测量被在某个 cutpoint 切成二值 — {variables}。把连续量在阈值处二分会（1）丢失 dose-response 信息、降低统计效率（Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127 “Dichotomizing continuous predictors in multiple regression: a bad idea”）；（2）结果对切点敏感，数据驱动的“最优切点”搜索还会抬高假阳性（Altman et al 1994 *JNCI* 86:829）；（3）若被二分的是 confounder，类内残余混杂使调整不充分（Becher 1992 *Stat Med* 11:1747）。Themis 支持把变量保留为连续并做 dose-response 估计（Phase 13/14）。',
    en: 'dichotomization: a continuous measurement on the identification route was cut into two at some cutpoint — {variables}. Splitting a continuous quantity at a threshold (1) throws away the dose-response information and costs statistical efficiency (Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127 “Dichotomizing continuous predictors in multiple regression: a bad idea”); (2) makes the result sensitive to the cutpoint, and a data-driven search for the “optimal” one inflates false positives on top of that (Altman et al 1994 *JNCI* 86:829); (3) leaves within-category residual confounding, so the adjustment is incomplete, when what was dichotomized is a confounder (Becher 1992 *Stat Med* 11:1747). Themis can keep the variable continuous and estimate the dose-response instead (Phase 13/14).',
  },
  a_distribution_is_missing: {
    zh: '缺概率分布 {what}',
    en: 'the distribution {what} is missing',
  },
  a_joint_intervention_does_not_decompose: {
    zh: '联合干预给的是处理集合的总对比（含处理×处理交互），不做直接/间接分解；该路径的 v1 作用域明确不与中介声明组合。',
    en: 'a joint intervention gives the total contrast over a set of treatments (with treatment-by-treatment interaction) and does no direct/indirect decomposition; the v1 scope of that route explicitly does not compose with a mediator declaration.',
  },
  a_joint_intervention_does_not_transport: {
    zh: '联合对比是在主样本自己的总体里算的；联合干预路径的 v1 作用域明确不与 `target_population` 组合。',
    en: 'the joint contrast is computed within the main sample\'s own population; the v1 scope of the joint-intervention route explicitly does not compose with `target_population`.',
  },
  a_learned_graph_inherits_the_algorithms_assumptions: {
    zh: '结果继承算法的核心假设：PC 需要忠实性 (faithfulness) + 因果充足性 (causal sufficiency)；FCI 放宽因果充足性但仍需忠实性；LiNGAM 需要线性 + 非高斯噪声。',
    en: 'the result inherits the algorithm\'s core assumptions: PC needs faithfulness and causal sufficiency; FCI relaxes causal sufficiency but still needs faithfulness; LiNGAM needs linearity and non-Gaussian noise.',
  },
  a_longitudinal_route_does_not_do_a_joint_intervention: {
    zh: '纵向 g-formula 沿时间序对一条处理轨迹做序贯标准化；对处理集合的联合干预（含处理×处理交互）不是它算出来的那个量。',
    en: 'the longitudinal g-formula standardizes sequentially along time over one treatment trajectory; a joint intervention on a set of treatments (with treatment-by-treatment interaction) is not the quantity it computes.',
  },
  a_longitudinal_route_does_not_transport: {
    zh: '纵向 g-formula 在主样本自己的总体里标准化；把结果搬到目标总体是另一次识别（选择图 + s-可容许集），它不顺带做。',
    en: 'the longitudinal g-formula standardizes within the main sample\'s own population; carrying the result to a target population is a second identification (selection diagram + s-admissible set), and it does not come along for free.',
  },
  a_longitudinal_route_gives_the_total_effect_only: {
    zh: '时变处理的直接/间接效应分解要的是时变中介的序贯可忽略性，与总效应的 g-formula 不是同一组条件；这条路线只给总效应。',
    en: 'decomposing a time-varying treatment into direct and indirect effects needs sequential ignorability for the time-varying mediator, which is not the set of conditions the total-effect g-formula rests on; this route gives the total effect only.',
  },
  a_structural_input_is_missing: {
    zh: '缺结构输入：{why}',
    en: 'a structural input is missing: {why}',
  },
  a_variable_declares_a_noisy_measurement: {
    zh: '测量误差风险：识别路径上有变量声明了高噪声测量方式 — {variables}。 经典文献：MacMahon 1990 Lancet 单次门诊 BP 测量因 within-person 变异导致 BP→CHD 斜率被 regression dilution 向 0 衰减约 60%；Hernán & Robins What If §9 自报告 / 问卷暴露的 non-differential mis-classification 同样使 估计值低估真效应；Fuller 1987 Measurement Error Models 给出 attenuation theorem 的形式定义。结构层只做识别 + 缺口诊断；但若被误分类的离散结局或二值暴露有验证研究给出的混淆矩阵，数值层可做去衰减校正（estimate(..., misclassification={{<结局或暴露变量名>: {{confusion_matrix, states}}}})），逐后门层做矩阵求逆——结局侧 p_true=M⁻¹p_obs（二值即 Rogan-Gladen 1978），暴露侧用矩阵法沿暴露轴对 (X,Y) 联合逐结局列求逆（Barron 1977 / Greenland 1988 / Marshall 1990）。误分类可为非差异（单一矩阵），也可为差异性（differential=True + 每个条件层一个矩阵，differential_by 指定差异轴：结局侧按暴露臂=detection bias 或按协变量分层（differential_by=<协变量>），暴露侧按结局层=recall bias 或按协变量分层（differential_by=<协变量>，误分类率随测量地点/年龄而异）；差异误分类可朝远离零方向偏，故须逐层求逆，池化单矩阵会做错）；两种都由 verify_measurement_correction_numeric / verify_exposure_measurement_correction_numeric 独立重算校正值。若被误测的是连续暴露或连续混杂且有已知的经典加性误差方差 σ²_u（验证研究 / 重复测量），数值层可经 estimate(..., measurement_error={{<变量名>: {{error_variance}}}}) 用 regression calibration 的矩量校正 β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive 去偏（Carroll 2006；误测暴露=回归稀释向零衰减，单暴露即 βx=b_naive/λ，λ=1−σ²_u/Var(W|Z) 是连续版 det(M)；误测混杂=对噪声代理调整留下的残差混淆偏倚，可朝任意方向，由整条矩阵求逆去偏无标量捷径），由 verify_regression_calibration_numeric 独立重导。被误测的若是连续结局则另当别论：经典加性误差 Y=Y*+V 不改变任何条件均值，点估计无偏、无可校正；同一入口 measurement_error={{<结局名>: {{error_variance}}}} 给出的是代价——残差方差按 Var(Y|D)=Var(Y*|D)+σ²_v 分解，区间比结局测准时宽 √(Var(Y|D)/Var(Y*|D)) 倍，这部分靠加样本量消不掉、只能靠把结局测准（由 verify_outcome_error 独立重导）。',
    en: 'measurement-error risk: a variable on the identification route declares a noisy way of measuring it — {variables}. The classical references: MacMahon 1990 Lancet, where a single clinic BP reading attenuates the BP→CHD slope toward 0 by about 60% through within-person variation (regression dilution); Hernán & Robins *What If* §9, where non-differential misclassification of a self-reported or questionnaire exposure likewise pulls the estimate below the true effect; Fuller 1987 *Measurement Error Models* for the formal attenuation theorem. The structural layer only identifies and diagnoses gaps — but where a misclassified discrete outcome or binary exposure has a confusion matrix from a validation study, the numeric layer can undo the attenuation (estimate(..., misclassification={{<outcome or exposure name>: {{confusion_matrix, states}}}})), inverting the matrix within each back-door stratum — on the outcome side p_true=M⁻¹p_obs (Rogan-Gladen 1978 in the binary case), on the exposure side by the matrix method, inverting the joint (X,Y) along the exposure axis one outcome column at a time (Barron 1977 / Greenland 1988 / Marshall 1990). Misclassification may be non-differential (one matrix) or differential (differential=True plus one matrix per stratum, with differential_by naming the axis: on the outcome side by exposure arm = detection bias, or by covariate stratum (differential_by=<covariate>); on the exposure side by outcome level = recall bias, or by covariate stratum (differential_by=<covariate>, where the rates vary with site or age). Differential misclassification can bias away from the null, which is why each stratum has to be inverted on its own and pooling into one matrix gets it wrong.) Either way, verify_measurement_correction_numeric / verify_exposure_measurement_correction_numeric recompute the correction independently. Where what is mismeasured is a continuous exposure or continuous confounder with a known classical additive error variance σ²_u (validation study, repeat measurements), the numeric layer can debias through estimate(..., measurement_error={{<variable>: {{error_variance}}}}) with regression calibration\'s method of moments, β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive (Carroll 2006; a mismeasured exposure attenuates toward zero, and with a single exposure that is βx=b_naive/λ, where λ=1−σ²_u/Var(W|Z) is the continuous counterpart of det(M); a mismeasured confounder leaves residual confounding after adjusting on the noisy proxy, which can go either way and has no scalar shortcut — the whole matrix inversion is what debiases it), and verify_regression_calibration_numeric re-derives it. A mismeasured continuous outcome is a different case: classical additive error Y=Y*+V moves no conditional mean, so the point estimate is unbiased and there is nothing to correct; what the same entry point measurement_error={{<outcome>: {{error_variance}}}} gives is the cost — the residual variance splits as Var(Y|D)=Var(Y*|D)+σ²_v, and the interval is √(Var(Y|D)/Var(Y*|D)) times wider than it would be with the outcome measured correctly. That part cannot be bought back with sample size; only measuring the outcome better removes it (verify_outcome_error re-derives this).',
  },
  an_identification_premise_is_missing: {
    zh: '识别前提待补充或修正：{why}',
    en: 'an identification premise has to be supplied or corrected: {why}',
  },
  and_that_interval_is_uninformative: {
    zh: '这一条是非信息性的 [0,1] / [-1,1]，没有实际辨别力。',
    en: 'that one is the uninformative [0,1] / [-1,1], which tells nothing apart.',
  },
  choose_by_which_assumptions_you_accept: {
    zh: '读者按自己接受哪组假设来选，不要取交：两条都成立时交集确实含真值，但它不是二者合取下的锐界（那要数值端在响应型多面体上另解一次），而一个不带标签的区间会把各自靠什么抹掉。',
    en: 'Choose by which set of assumptions you accept, and do not intersect them: where both hold the intersection does contain the true value, but it is not the sharp bound under their conjunction (that would take the numeric side solving once more over the response-type polytope), and an interval with no label on it erases what each one stood on.',
  },
  declared_binary_but_the_column_has_more_levels: {
    zh: '变量 `{variable}` 声明为二值（两档），但这一列有 {count} 个不同取值——g-formula 会把它当多档 / 连续暴露处理，而不是两臂对比。',
    en: 'the variable `{variable}` is declared binary (two levels), but the column holds {count} distinct values — the g-formula will treat it as a multi-level or continuous exposure rather than as a two-arm contrast.',
  },
  declared_continuous_but_the_column_is_discrete: {
    zh: '变量 `{variable}` 声明为连续，但这一列只有 {count} 个不同取值（{values}）——任何剂量-反应估计量都会塌成离散的两档对比，给不出一条曲线。',
    en: 'the variable `{variable}` is declared continuous, but the column holds only {count} distinct values ({values}) — any dose-response estimand collapses to a discrete two-level contrast and yields no curve.',
  },
  declared_discrete_but_the_values_form_a_continuum: {
    zh: '变量 `{variable}` 声明为离散，但这一列的 {count} 个取值构成连续尺度。',
    en: 'the variable `{variable}` is declared discrete, but its {count} values form a continuous scale.',
  },
  discovery_ran_on_this_many_rows: {
    zh: '样本量 N = {n}。',
    en: 'sample size N = {n}.',
  },
  discovery_used_this_significance_threshold: {
    zh: '显著性阈值 α = {alpha}。',
    en: 'significance threshold α = {alpha}.',
  },
  every_stratum_should_have_both_arms_and_some_do_not: {
    zh: '调整集 {adjustment} 在这份样本里划出 {cells} 个层，其中 {bad} 个只含一个处理臂，占样本 {share}：{strata}。positivity（Hernan & Robins ch.3）要求每一层内两个臂都有个体；这些层里缺的那一臂，是结局模型拿别的层的斜率外推出来的——答案的那一部分不是数据里的对比。',
    en: 'the adjustment set {adjustment} cuts this sample into {cells} strata, and {bad} of them hold a single treatment arm, carrying {share} of the sample: {strata}. Positivity (Hernan & Robins ch.3) asks for units in both arms inside every stratum; where one is absent the outcome model supplies it from the slope it learned in the other strata, and that part of the answer is not a comparison the data made.',
  },
  front_door_rests_on_four_premises: {
    zh: '前门识别（Pearl front-door criterion）的有效性以下列假设为前提：(1) 中介集 M 阻断 X→Y 的所有有向路径；(2) 不存在未阻断的 X→M 后门路径；(3) 所有 M→Y 后门路径已被 X 阻断；(4) consistency of potential outcomes。若任一假设不成立，前门估计失效。',
    en: 'front-door identification (Pearl\'s front-door criterion) is valid only under these assumptions: (1) the mediator set M intercepts every directed path from X to Y; (2) there is no unblocked back-door path from X to M; (3) every back-door path from M to Y is blocked by X; (4) consistency of potential outcomes. If any one of them fails, the front-door estimate fails with it.',
  },
  iv_rests_on_this_assumption: {
    zh: 'IV 识别（工具变量 `{instrument}`）的有效性以下列假设为前提：{assumption}。读 IV 估计前应明确这条假设是否在你的场景下成立。',
    en: 'IV identification (through the instrument `{instrument}`) is valid only under this assumption: {assumption}. Settle whether it holds in your setting before reading the IV estimate.',
  },
  mediation_and_transport_are_sequential: {
    zh: 'Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × transport 是 sequential operations（先在 source population 做 mediation, 再 transport 各 component 到 target），不能在一个 query 里同时 dispatch。',
    en: 'Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × transport are sequential operations (mediation first in the source population, then each component transported to the target); they cannot be dispatched together in one query.',
  },
  mediation_is_identifiable_for_a_mediator: {
    zh: '中介分解 {branch} 标识为可识别，前提是以下假设成立：{assumptions}。（中介 {subject}）',
    en: 'the {branch} mediation decomposition is marked identifiable, on the premise that these assumptions hold: {assumptions}. (mediator {subject})',
  },
  mediation_is_identifiable_for_a_mediator_block: {
    zh: '中介分解 {branch} 标识为可识别，前提是以下假设成立：{assumptions}。（中介组 {subject}，作为一整组分解，不拆到单条路径）',
    en: 'the {branch} mediation decomposition is marked identifiable, on the premise that these assumptions hold: {assumptions}. (the mediator block {subject}, decomposed as one whole and not split into single paths)',
  },
  one_interval_and_what_it_rests_on: {
    zh: '一条来自 `{method}`，假设 {assumptions}。',
    en: 'one comes from `{method}`, assuming {assumptions}.',
  },
  one_interval_that_rests_on_nothing: {
    zh: '一条来自 `{method}`，不需要额外假设。',
    en: 'one comes from `{method}` and needs no further assumption.',
  },
  only_one_declared_layer_was_run: {
    zh: 'Query 同时声明了 {won} 和 {lost}；当前 dispatch 只跑了 {winner}，{skipped} 被静默跳过。',
    en: 'the query declares both {won} and {lost}; this dispatch ran {winner} only, and {skipped} was skipped in silence. ',
  },
  several_intervals_bound_the_same_quantity: {
    zh: '共 {count} 条，界定的是同一个量，各自靠不同的假设。',
    en: '{count} of them bound the same quantity, each resting on different assumptions.',
  },
  the_algorithms_assumptions_were_violated_on_this_data: {
    zh: '检测到当前数据上算法假设的具体违反：{violations}。',
    en: 'specific violations of the algorithm\'s assumptions were detected on this data: {violations}.',
  },
  the_anderson_rubin_set_is_this: {
    zh: 'Anderson-Rubin {level}% 弱工具稳健置信集（不管工具多强都有效）是 {interval}。',
    en: 'the Anderson-Rubin {level}% weak-instrument-robust confidence set (valid whatever the instrument\'s strength) is {interval}.',
  },
  the_answer_is_an_interval_not_a_point: {
    zh: '答案是符号区间，不是点估计。渲染时必须明示这是 bounds 而非具体数值。',
    en: 'the answer is a symbolic interval, not a point estimate. Whatever renders it has to say so rather than let it read as a number.',
  },
  the_caller_flagged_an_uncertainty: {
    zh: '上游 LLM 标记了不确定性 `{kind}`。答案的解读应将其考虑在内。',
    en: 'the upstream LLM flagged an uncertainty, `{kind}`. Read the answer with that in view.',
  },
  the_caller_flagged_an_uncertainty_and_said_why: {
    zh: '上游 LLM 标记了不确定性 `{kind}`：{rationale}。答案的解读应将其考虑在内。',
    en: 'the upstream LLM flagged an uncertainty, `{kind}`: {rationale}. Read the answer with that in view.',
  },
  the_column_holds_values_the_declaration_does_not_list: {
    zh: '变量 `{variable}` 这一列出现了声明取值范围 {domain} 之外的值：{extra}。',
    en: 'the column for `{variable}` holds values outside the declared domain {domain}: {extra}.',
  },
  the_composite_confidence_is_below_the_threshold: {
    zh: '答案的复合可信度为 {confidence}（< {threshold}）— 至少有一项输入语句的置信度较低，结果应视为不确定的。具体的薄弱环节见 `confidence_sources` 中标记 is_weakest=true 的条目。',
    en: 'the answer\'s composite confidence is {confidence} (< {threshold}) — at least one input statement carries substantial uncertainty, and the result should be read as uncertain. The weak links themselves are the entries marked is_weakest=true in `confidence_sources`.',
  },
  the_conditioning_node_is_a_collider: {
    zh: '`given` 中的条件节点 `{collider}` 是 collider —— 在 `{intervention}` 与 `{target}` 之间存在一条以 `{collider}` 为对撞点的路径（两条臂可经潜在/双向边，即 M-bias）。Pearl d-separation：在 collider（或其后代）上做条件会打开这条非因果路径而不是阻断它，给最终估计引入 collider-induced bias / selection bias。当前返回的不是 "在 `{collider}` 子群上的因果效应"，而是被打开的非因果路径污染过的混合量。',
    en: 'the conditioning node `{collider}` in `given` is a collider — between `{intervention}` and `{target}` there is a path that collides at `{collider}` (either arm may run through a latent or bidirected edge, which is M-bias). Pearl\'s d-separation: conditioning on a collider (or on its descendant) opens that non-causal path rather than blocking it, and puts collider-induced bias / selection bias into the estimate. What comes back is not "the causal effect within the `{collider}` subgroup" but a mixture contaminated by the path that was opened.',
  },
  the_counterfactual_rests_on_cross_world_premises: {
    zh: '反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的潜在结果）+ composition 公理为前提，这两条无法从数据本身验证；跨世界的格子还要靠某一条路线把两个世界连起来，那条路线自己的前提也一并被继承——具体是哪条、可不可检验，看答案上的 interventional_risk_provenance 与假设台账逐条列出的那几行；单调性若声明，是收紧这一格的额外前提，不是回答的前提。',
    en: 'counterfactual reasoning is valid only under consistency (an observed value = the potential outcome under do(the value it actually took)) and the composition axiom, neither of which the data can check; a cross-world cell needs some route to join the two worlds besides, and that route\'s own premises are inherited with it — which route, and whether it can be tested, is on the answer\'s interventional_risk_provenance and in the rows the assumption ledger lists one by one. Monotonicity, where it is declared, is a further premise that tightens this cell rather than a premise of the answer.',
  },
  the_dag_declares_no_confounder_for_the_curve: {
    zh: '（注：你的 DAG 仅声明了 intervention + target 两个节点，没有任何 confounder。观察性剂量响应分析典型需要在 DAG 里至少声明 baseline outcome 与关键 demographic covariates；若你确实想保持 minimal DAG（如随机化 RCT 设计），可以忽略此提示。）',
    en: '(Note: your DAG declares only the intervention and the target, with no confounder at all. An observational dose-response analysis usually needs at least the baseline outcome and the key demographic covariates declared in the DAG; if you do mean to keep the DAG minimal — a randomized design, say — you can ignore this.)',
  },
  the_dag_declares_no_latent_common_cause: {
    zh: 'Backdoor 识别假设你列出的 confounder 已经测全 —— DAG 里没有声明任何 bidirected / latent-common-cause 边。这是 measured-covariate 调整后仍残留 unmeasured confounder 的典型场景。多个域有 well-documented RCT-vs-observational（或实验-vs-观察）反转：医学（HRT-CVD WHI 2002、vitamin D-CVD VITAL 2018）、劳动经济学（Card 1995 schooling-earnings 中的 ability bias）、教育评估（charter schools CREDO 2013 中的 parental motivation）。机制各域不同（healthy-user bias / ability bias / selection effects），但结构教训一致——measured 调整不够。拿到数据后跑 sensitivity analysis（E-value）量化对 unmeasured confounder 的稳健性，或在 DAG 里把怀疑的 latent 显式声明为 bidirected。',
    en: 'back-door identification assumes the confounders you listed are all of them — the DAG declares no bidirected / latent-common-cause edge at all. This is the standard setting for an unmeasured confounder surviving adjustment on the measured covariates. Several fields have well-documented RCT-vs-observational (or experiment-vs-observation) reversals: medicine (HRT-CVD, WHI 2002; vitamin D-CVD, VITAL 2018), labour economics (ability bias in Card 1995\'s schooling-earnings estimates), education evaluation (parental motivation in CREDO 2013\'s charter schools). The mechanism differs by field (healthy-user bias / ability bias / selection effects), but the structural lesson is the same — adjusting on the measured ones is not enough. Once the data is in hand, run a sensitivity analysis (E-value) to quantify how robust this is to an unmeasured confounder, or declare the latent you suspect as a bidirected edge in the DAG.',
  },
  the_decomposition_needs_the_mediators_distributions: {
    zh: '中介分解需要 {mediator} 相关分布：{target}',
    en: 'the mediation decomposition needs {mediator}\'s distributions: {target}',
  },
  the_edge_is_an_llm_proposal: {
    zh: '结构性回答途径上的边 `{edge}` 是上游 LLM 提出的假设（annotations.source = llm_proposal），不是经证据支持的边。当前回答相当于复述这条假设，而非独立验证。',
    en: 'the edge `{edge}` on the route to the structural answer is a hypothesis the upstream LLM proposed (annotations.source = llm_proposal), not an edge evidence supports. The answer as it stands restates that hypothesis rather than verifying it.',
  },
  the_edge_survived_this_share_of_resamples: {
    zh: '自助法稳定度 {confidence}（该边在此比例的数据重采样中重现；越低越可能是采样噪声，越应复核）。',
    en: 'bootstrap stability {confidence} (the share of resamples the edge reappears in; the lower it is the more likely it is sampling noise, and the more it wants checking).',
  },
  the_edge_was_learned_by_discovery: {
    zh: '结构性回答途径上的边 `{edge}` 是因果发现算法 `{algorithm}` 从数据中学出的，结果以算法假设（如 PC: 忠实性 + 因果充足性；LiNGAM: 线性 + 非高斯）为前提。',
    en: 'the edge `{edge}` on the route to the structural answer was learned from the data by the causal-discovery algorithm `{algorithm}`, so the result rests on that algorithm\'s assumptions (PC: faithfulness and causal sufficiency; LiNGAM: linearity and non-Gaussian noise).',
  },
  the_first_stage_is_weak: {
    zh: '工具 `{instrument}` 的第一阶段 F = {f}，低于 Stock-Yogo (2005) 的阈值 {threshold}。IV 估计朝 OLS 偏的幅度按 1/F 放大，第一阶段弱的时候 2SLS / Wald 的 bootstrap 置信区间也不可靠。把这个点估计当成粗略参考，不要当成一次紧致的识别。',
    en: 'the first stage of the instrument `{instrument}` is F = {f}, below Stock-Yogo\'s (2005) threshold of {threshold}. The IV estimate\'s bias toward OLS scales as 1/F, and with a weak first stage the bootstrap CI on 2SLS / Wald is unreliable too. Read the point estimate as a rough bearing, not as a tight identification.',
  },
  the_fitted_propensity_leaves_part_of_the_sample_unsupported: {
    zh: '估计出的倾向性 P({treatment}=1 | {adjustment}) 有 {outside}/{total} 个观测落在 [{lower}, {upper}] 之外（{share}；最小 {low}，最大 {high}）。Hernan & Robins ch.3 \'positivity\'：每个混杂分层里都该同时有受处理和未受处理的个体。后门 / g-formula 的估计会把结局回归外推到没有支撑的那片区域——答案的那一部分不是真正的因果估计，只是模型假设。',
    en: 'the fitted propensity P({treatment}=1 | {adjustment}) puts {outside}/{total} observations outside [{lower}, {upper}] ({share}; min {low}, max {high}). Hernán & Robins ch.3, \'positivity\': every confounder stratum should hold both treated and untreated units. A back-door / g-formula estimate extrapolates the outcome regression into the region with no support — and that part of the answer is a model assumption rather than a causal estimate.',
  },
  the_graph_and_the_cpts_disagree: {
    zh: '声明的图与提供的 CPT 不一致：缺 {what}，但 theta 中存在的边缘量被 d-separation 拒绝（图蕴含的独立性不成立）',
    en: 'the declared graph and the CPTs supplied disagree: {what} is missing, and a marginal that theta does carry is refused by d-separation (an independence the graph implies does not hold)',
  },
  the_graph_was_learned_by_an_algorithm: {
    zh: 'DAG 是由因果发现算法 `{algorithm}` 从数据中学出的，不是用领域知识手工声明的。',
    en: 'the DAG was learned from the data by the causal-discovery algorithm `{algorithm}` rather than declared by hand from domain knowledge.',
  },
  the_heteroskedasticity_robust_anderson_rubin_set_is_this: {
    zh: '异方差稳健的 Anderson-Rubin {level}% 集（在弱工具「且」异方差下都有效）是 {interval}。',
    en: 'the heteroskedasticity-robust Anderson-Rubin {level}% set (valid under weak instruments *and* heteroskedasticity) is {interval}.',
  },
  the_homoskedastic_sargan_says_the_same: {
    zh: '同方差 Sargan 检验给的是 J = {j}，p = {p}。',
    en: 'the homoskedastic Sargan gives J = {j}, p = {p}.',
  },
  the_identification_route_failed: {
    zh: '识别路径失败：{why}',
    en: 'the identification route failed: {why}',
  },
  the_intervention_is_a_state_with_no_time_window: {
    zh: 'intervention 是状态不是事件、且没有指定时间窗：变量 `{intervention}` 声明了 `state_vs_event="state"`（持久性属性，不是离散事件），但同一变量没有声明 `time_window`。这是 Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 "Does obesity shorten life? The importance of well-defined interventions to answer causal questions" 的经典 ill-defined intervention 结构 —— 同一个 `{intervention}` 状态值可以由多种结构上不同的操纵方式达到，而这些不同的操纵会带来不同的反事实结果，因此 do({intervention}=state) 没有唯一定义；consistency assumption（Hernán & Robins *What If* §3.4）被沉默地违反，返回的 "effect" 实际上是多个估计量的混合。Themis 仅surface 此问题，无法替你选具体的干预定义。',
    en: 'the intervention is a state rather than an event and no time window was given: the variable `{intervention}` declares `state_vs_event="state"` (a lasting attribute, not a discrete event) and declares no `time_window`. This is the classic ill-defined-intervention structure of Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 "Does obesity shorten life? The importance of well-defined interventions to answer causal questions" — one `{intervention}` state value is reachable by structurally different manipulations, those manipulations carry different counterfactuals, and so do({intervention}=state) has no single definition; the consistency assumption (Hernán & Robins *What If* §3.4) is violated silently, and the "effect" that comes back is a mixture of several estimands. Themis only surfaces this; it cannot pick the intervention\'s definition for you.',
  },
  the_intervention_says_neither_state_nor_event: {
    zh: '`{intervention}` 出现在 do(.) 位置，但没声明它是离散事件还是持续状态（`state_vs_event`），也没给 `time_window` —— 所以这里还无法判断这个干预定义得够不够清楚（缺信息 ≠ 定义不清）。先确认一句：`{intervention}` 是一个明确的动作 / 事件（如一次性给药、参加某项目），还是一个属性 / 持续状态（如肥胖、长期保持某行为）？若是前者，干预本就定义清楚，声明 `state_vs_event="event"` 即可消除本提示。若是后者，则会落入 Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 "Does obesity shorten life?"（该文以肥胖为例）的 ill-defined intervention 情形：同一状态值可由多种操纵方式达到、各自反事实不同，do({intervention}=该状态) 没有唯一定义，consistency 假设（Hernán & Robins *What If* §3.4）会被违反 —— 这时请加 `time_window`，或在 extensions.ambiguities opt-in `ill_defined_intervention`。',
    en: '`{intervention}` appears in a do(.) position, but nothing says whether it is a discrete event or a sustained state (`state_vs_event`), and no `time_window` was given — so this cannot yet be judged one way or the other (missing information is not the same as an ill-defined intervention). One question settles it: is `{intervention}` a definite action or event (a single dose, enrolling in a programme), or an attribute or sustained state (obesity, keeping up a behaviour)? If the former, the intervention is already well defined and declaring `state_vs_event="event"` clears this notice. If the latter, it falls into the ill-defined-intervention case of Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 "Does obesity shorten life?" (which uses obesity as its example): one state value is reachable by several manipulations, each with its own counterfactual, so do({intervention}=that state) has no single definition and the consistency assumption (Hernán & Robins *What If* §3.4) is violated — add a `time_window`, or opt in to `ill_defined_intervention` under extensions.ambiguities.',
  },
  the_joint_first_stage_is_weak: {
    zh: '工具组 {instruments} 的联合第一阶段 F = {f}，低于 Stock-Yogo (2005) 的阈值 {threshold}。过度识别的 2SLS 估计会朝 OLS 偏，而且这组工具联合起来弱的时候，bootstrap 置信区间也不可靠。',
    en: 'the joint first stage of the instrument set {instruments} is F = {f}, below Stock-Yogo\'s (2005) threshold of {threshold}. An overidentified 2SLS estimate is biased toward OLS, and when the set is jointly weak the bootstrap CI is unreliable too.',
  },
  the_multi_instrument_anderson_rubin_set_is_this: {
    zh: '多工具 Anderson-Rubin {level}% 弱工具稳健置信集（不管这组工具联合起来多强都有效）是 {interval}。',
    en: 'the multi-instrument Anderson-Rubin {level}% weak-instrument-robust confidence set (valid however strong the set is jointly) is {interval}.',
  },
  the_number_answers_a_different_estimand_than_declared: {
    zh: '数还是照着强制转换后的数据算出来了，但它回答的估计量和声明承诺的不是同一个——把声明的尺度 / 取值范围和数据对齐之后，这个数才能当成声明的那个量来读。',
    en: 'the number was still computed off the coerced data, but the estimand it answers is not the one the declaration promised — align the declared scale or domain with the data and only then does the number read as the quantity that was declared.',
  },
  the_outcome_model_is_quasi_separated: {
    zh: 'Backdoor 后门 logistic 模型 P({outcome}=1 | {features}) 的训练集预测概率在 {outside}/{total}（{share}）个观测上落在 [{lower}, {upper}] 之外（min={low}, max={high}）。这是 quasi-separation 信号——结果在某些 (treatment, confounder) 子层近乎确定，logistic 系数已饱和。点估计仍能算出但 CI 偏窄、对极端结局的偏差放大。这是 outcome 模型的失败模式，与 `propensity_overlap_violation` 检查的 treatment assignment 模型互补。',
    en: 'the back-door logistic model P({outcome}=1 | {features}) puts {outside}/{total} ({share}) of its training-set fitted probabilities outside [{lower}, {upper}] (min={low}, max={high}). That is quasi-separation — the outcome is nearly certain within some (treatment, confounder) strata and the logistic coefficients have saturated. A point estimate still comes out, but the CI is too narrow and the bias on extreme outcomes is magnified. This is the outcome model\'s failure mode, the counterpart of the treatment-assignment model that `propensity_overlap_violation` checks.',
  },
  the_overidentification_test_refuted_the_instruments: {
    zh: '{test} 过度识别检验「否决」了工具组 {instruments} 的联合有效性（J = {j}，df = {df}，p = {p}）。至少有一条排他性限制与数据里的其他限制互相矛盾——IV 点估计所依赖的这组工具，被数据反驳了。这是一次证伪，不是数据量不够的缺口：再多同样的数据也不会让它消失。',
    en: 'the {test} overidentification test rejected the joint validity of the instrument set {instruments} (J = {j}, df = {df}, p = {p}). At least one exclusion restriction contradicts the others in the data — the set the IV point estimate rests on has been refuted by it. This is a falsification and not a shortfall of data: more of the same refutes it again.',
  },
  the_proxies_are_finer_than_the_declared_cardinality: {
    zh: 'Miao 公式 (5) 靠反演两个代理之间的 `{k}`×`{k}` 测量通道来恢复效应，所以每个代理都要恰好呈现 `{k}` 个层级——也就是这个查询为未观测混杂 `{latent}` 假定的类别数。`{z}` 有 {z_levels} 个，`{w}` 有 {w_levels} 个，要反演的那个通道还不存在。',
    en: 'Miao\'s formula (5) recovers the effect by inverting a `{k}`x`{k}` measurement channel between the two proxies, so each of them has to present exactly `{k}` levels — the cardinality the query posits for the unobserved confounder `{latent}`. `{z}` presents {z_levels} and `{w}` presents {w_levels}, so the channel this estimate would invert does not exist yet.',
  },
  the_question_asks_for_a_dose_response_curve: {
    zh: '用户问的是 {intervention} 与 {target} 之间的剂量响应关系（曲线 / 关系图）。Themis 不算曲线（请用 EconML / DoubleML / GAM）—— 但下面是你做这件事所需的数据规格。',
    en: 'the question asks for the dose-response relationship between {intervention} and {target} (a curve, a plot). Themis does not fit curves — use EconML / DoubleML / GAM — but here is the data specification doing so would take.',
  },
  the_result_reflects_one_layer_only: {
    zh: '当前 result 只反映 {winner} 这一层；{skipped} 分析需要单独 query。',
    en: 'The result reflects the {winner} layer alone; a {skipped} analysis takes a query of its own.',
  },
  the_sample_could_not_be_cut_into_the_strata_the_wald_needs: {
    zh: '工具 `{instrument}` 只在给定 {{{conditioning}}} 时才有效，那对应的是分层 Wald——顺从者中的效应。这份样本没法这样切分：{reason}。所以报出来的数是 2SLS 系数，它给每一层的效应加的权，是工具在那一层把处理推动得有多强，而不是那一层顺从者的占比。两者只有在第一阶段每层一样强时才重合；否则它们是两个不同的量，而不是同一个量的两种估计。',
    en: 'the instrument `{instrument}` is valid only given {{{conditioning}}}, and what that identifies is the stratified Wald — the effect among compliers. This sample cannot be cut that way: {reason}. So the number reported is the 2SLS coefficient, which weights each stratum\'s effect by how hard the instrument moves treatment there rather than by that stratum\'s share of compliers. The two coincide only when the first stage is equally strong in every stratum; otherwise they are two different quantities, not two estimates of one.',
  },
  the_sample_is_restricted_on_a_collider: {
    zh: '样本被结构性限制为 `{collider}={value}` 的受试者（program 里有 ObservationStatement 编码了这个限制），但声明的 DAG 里 `{intervention}` 和 `{target}` 都是 `{collider}` 的祖先 —— `{collider}` 是 collider。Pearl d-separation：用『仅 {collider}={value} 的子样本』估计 P({target} | do({intervention})) 等于在 collider 上做条件，会打开 `{intervention}→...→{collider}←...←{target}` 这条非因果路径，给估计引入 selection-induced bias。Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615 "A Structural Approach to Selection Bias" 的标准结构。',
    en: 'the sample is structurally restricted to subjects with `{collider}={value}` (an ObservationStatement in the program encodes that restriction), and in the declared DAG both `{intervention}` and `{target}` are ancestors of `{collider}` — so `{collider}` is a collider. Pearl\'s d-separation: estimating P({target} | do({intervention})) from the {collider}={value} subsample alone is conditioning on a collider, and it opens the non-causal path `{intervention}→...→{collider}←...←{target}`, putting selection-induced bias into the estimate. This is the standard structure of Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615 "A Structural Approach to Selection Bias".',
  },
  the_source_domains_contradict_each_other: {
    zh: '多源迁移互相矛盾：{why}',
    en: 'the source domains contradict each other: {why}',
  },
  the_source_populations_stratified_conditional_is_missing: {
    zh: '转移公式还需要源人群 {population} 的分层条件分布 {formula}（meta-analysis 通常只汇总成一个数，不给分层）',
    en: 'the transport formula also needs the stratified conditional {formula} on the source population {population} (a meta-analysis usually pools to one number and publishes no strata)',
  },
  the_target_populations_covariate_distribution_is_missing: {
    zh: '转移公式已识别，但目标人群 {population} 在 {{{variables}}} 上的分布 P*(Z) 未提供',
    en: 'the transport formula is identified, but the distribution P*(Z) of the target population {population} over {{{variables}}} was not supplied',
  },
  the_variable_has_no_operational_definition: {
    zh: '变量 `{variable}` 缺操作化定义：{missing}',
    en: 'the variable `{variable}` has no operational definition: {missing}',
  },
  this_column_is_not_in_this_estimand: {
    zh: '这一列不在本查询的估计量里，所以它不改变这里的数。它说的是程序的声明与数据不符——任何用到 `{variable}` 的查询都会被它影响，这一份不会。',
    en: 'this column is not in this query\'s estimand, so it changes no number here. What it reports is that the program\'s declaration and the data disagree — any query that does use `{variable}` is affected by it; this one is not.',
  },
  this_units_observations_are_missing: {
    zh: '缺该单位的观测值：{why}',
    en: 'this unit\'s observed values are missing: {why}',
  },
  tian_found_a_hedge: {
    zh: '识别失败：Tian 算法在 An(Y) 子图上找到 c-component hedge —— X 与 Y 处于同一 c-component，说明它们之间存在未被任何观测变量遮断的潜在共同原因 / 双向耦合，P(Y | do(X)) 在该 ADMG 下不可从观测分布识别',
    en: 'identification failed: Tian\'s algorithm found a c-component hedge on the An(Y) subgraph — X and Y sit in the same c-component, which says there is a latent common cause (or bidirected coupling) between them that no observed variable screens off, so P(Y | do(X)) is not identifiable from the observational distribution on this ADMG',
  },
  transport_rests_on_s_admissibility: {
    zh: '将估计从 {source} 转移到 {target} 的有效性以 S-admissibility 为前提：声明的 selection_nodes 必须正确捕获两人群间分布差异。',
    en: 'carrying the estimate from {source} to {target} is valid only under S-admissibility: the selection_nodes declared have to capture the distributional differences between the two populations correctly.',
  },
  which_levels_are_one_state_is_not_in_the_data: {
    zh: '更细的代理可以折到 `{k}` 组——条件独立性在变量的任何函数下都保持，所以折过的代理仍满足 model (f) 的判据，而且在总体上任何折出满秩通道的分组都识别同一个效应。有限样本里则不然：换一个分组就是另一个矩阵、另一个数。没有任何观测能说 `{z}` 的两个层级是那个谁也没测过的变量的同一个状态，所以估计器不替你挑分组——你声明它，它就作为你的选择被记录下来。',
    en: 'A finer proxy CAN be folded down to `{k}` groups — a conditional independence survives any function of the variable it holds for, so a grouped proxy still satisfies the model-(f) criteria, and in the population every grouping whose folded channel keeps full rank identifies the same effect. In a finite sample they do not: a different grouping is a different matrix and a different number. Nothing observed says that two levels of `{z}` are the same state of a variable nobody measured, so the estimator will not pick a grouping on your behalf — declare it and it is recorded as your choice.',
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
  proxy_coarsening_undeclared: {
    zh: '公式 (5) 要反演的那个 k×k 通道就存在了，近端 ATE 能算出来；分组会作为你的选择进假设台账，因为换一个分组就是另一个数',
    en: 'the k×k channel formula (5) inverts exists, so the proximal ATE can be computed; the grouping goes into the assumption ledger as your choice, because a different grouping is a different number',
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
  declare_a_proxy_coarsening: {
    zh: '若 U 确实只有 {k} 个状态，就在 query 的 `proxy_coarsening` 里把 `{z}` 与 `{w}` 的层级各分成 {k} 组，说明哪些层级代表 U 的同一个状态',
    en: 'if U really has just {k} states, group the levels of `{z}` and `{w}` into {k} groups each on the query\'s `proxy_coarsening`, saying which levels stand for the same state of U',
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
  reconsider_the_latent_cardinality: {
    zh: '若两个代理显示的状态数才是 U 真实的状态数，那要改的是 `latent_cardinality`——U 从未被观测，k 一直是个假设',
    en: 'if the states the proxies show are the states U really has, then what has to move is `latent_cardinality` — U is never observed, so k was always an assumption',
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
    zh: '源人群 `{detail}` 找不到 S-可容许的调整集——在它自己声明的那张选择图下，它的效应无法迁移到目标人群。每个源各自卡在哪里，写在迁移块上。',
    en: 'source population `{detail}` has no S-admissible adjustment set: under its own declared selection diagram its effect cannot be transported to the target population. Where each source got stuck is on the transport block.',
  },
  transport_sources_disagree: {
    zh: '两个源人群把同一个目标效应迁出了不同的数，相差 {detail}。θ 是给定的、不是估出来的，所以这不是抽样噪声：你给的分布否掉了至少一张选择图。这里不报数——报其中任何一个，都是替你选了信哪一张。',
    en: 'two source populations transport the same target effect to different numbers, differing by {detail}. Theta is declared rather than estimated, so this is not sampling noise: the distributions supplied refute at least one declared selection diagram. No number is reported, because reporting either one would be choosing which diagram to believe on your behalf.',
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
  proxy_coarsening_undeclared: {
    zh: '把每个代理的层级分成 k 组的方案，写在 query 的 proxy_coarsening 上',
    en: 'a grouping of each proxy\'s levels into the k groups, on the query\'s proxy_coarsening',
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
  transport_sources_disagree: {
    zh: '一个说法：哪张选择图是错的，或者哪个源的分布报错了',
    en: 'a decision on which selection diagram is wrong, or which source\'s distributions were misreported',
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

export const INTERACTION_UNAVAILABLE_WORDS: Record<string, Words> = {
  corner_unsupported: {
    zh: '这个有限差分要在处理的每一个取值组合上都站得住，而 {cells} 上没有任何一行数据。上面那个对比不受影响——它取在全处理格与全对照格之间，两者都有观测——但交互项没法与在空格子上凭空补出来的东西分开。',
    en: 'the finite difference has to stand on every combination of treatment levels, and {cells} has no rows at all. The contrast above is unaffected — it is taken between the all-treated and all-control cells, both of them observed — but the interaction cannot be told apart from what gets made up on an empty cell.',
  },
  order_above_cap: {
    zh: '这个有限差分要走遍处理的每一个取值组合，而处理超过 {cap} 个时不做这趟枚举，所以没有走。上面那个对比不受影响——它只要两个格子。数据也许撑得住每一个组合，只是没有人去看。',
    en: 'the finite difference walks every combination of treatment levels, and past {cap} treatments that walk is not taken — so it was not. The contrast above is unaffected: it needs two cells. The data may well support every combination; nobody looked.',
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

export const MEASUREMENT_NOTE_WORDS: Record<string, Words> = {
  a_field_names_a_known_noise: {
    zh: '{variable}〔{role}〕({field}: 含 “{phrase}”)',
    en: '{variable} [{role}] ({field}: contains “{phrase}”)',
  },
  a_threshold_cut_it_in_two: {
    zh: '{variable}（切点：“{cut}”）',
    en: '{variable} (threshold: “{cut}”)',
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

export const MISSING_DATA_SHORTFALL_WORDS: Record<string, Words> = {
  a_product_is_blocked_by_its_factors: {
    zh: '{factors}。干预估计量是这些因子的乘积，任何一个不行都会卡住它',
    en: '{factors}. The interventional estimand is the product of these factors, so any one of them blocks it',
  },
  no_recoverable_ordered_factorization: {
    zh: '在每一种可用的条件方式下，都有某个因子的目标仍与相关的缺失指示变量 d-连通（例如一条自遮蔽的 V→R_V 边），所以没有可恢复的有序因子分解',
    en: 'under every available way of conditioning, some factor\'s target stays d-connected to a missingness indicator that matters to it (a self-masking V→R_V edge, say), so no ordered factorization recovers the target',
  },
  the_adjusted_conditional: {
    zh: '调整后的条件分布 {target} 不可恢复',
    en: 'the adjusted conditional {target} is not recoverable',
  },
  the_covariate_marginal: {
    zh: '协变量边缘分布 {target} 不可恢复（例如一个自遮蔽的混杂 Z→R_Z）',
    en: 'the covariate marginal {target} is not recoverable (a self-masking confounder Z→R_Z, say)',
  },
}

export const MONOTONICITY_WORDS: Record<string, Words> = {
  non_decreasing: {
    zh: '处理只会让结局不变或变大（Y(1) ≥ Y(0)）',
    en: 'treatment can only leave the outcome unchanged or raise it (Y(1) ≥ Y(0))',
  },
  non_increasing: {
    zh: '处理只会让结局不变或变小（Y(1) ≤ Y(0)）',
    en: 'treatment can only leave the outcome unchanged or lower it (Y(1) ≤ Y(0))',
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

export const OBSERVABLE_REQUIRED_WORDS: Record<string, Words> = {
  a_full_table_of_cells: {
    zh: '{expression} 的完整分布，共 {cells} 个概率',
    en: 'the full distribution {expression} — {cells} probabilities',
  },
  a_joint_distribution: {
    zh: '{expression} 的联合观测',
    en: 'the joint distribution {expression}',
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

export const PRECISION_TARGET_WORDS: Record<string, Words> = {
  detect_a_binary_effect: {
    zh: '检出 Cohen\'s h={h}（二值结局的中小效应），α=0.05 双侧、power=0.80；两臂等分配',
    en: 'detect Cohen\'s h={h} (a small-to-medium binary effect) at α=0.05 two-sided and power 0.80, allocated equally to two arms',
  },
  detect_a_continuous_effect: {
    zh: '检出 Cohen\'s d={d}（连续结局的中等效应），α=0.05 双侧、power=0.80；两臂等分配',
    en: 'detect Cohen\'s d={d} (a medium continuous effect) at α=0.05 two-sided and power 0.80, allocated equally to two arms',
  },
  detect_both_mediation_paths: {
    zh: '同时检出 NDE 与 NIE，每条路径上按 Cohen\'s h={h}（α=0.05、power=0.80）；这是个经验值 = 简单 ATE 所需 n 的 {times} 倍，依据 VanderWeele 2015 §4',
    en: 'detect the NDE and the NIE together, at Cohen\'s h={h} on each path (α=0.05, power 0.80). A rule of thumb rather than a power calculation: {times}× the n a simple ATE needs, after VanderWeele 2015 §4',
  },
  detect_the_effect_in_every_stratum: {
    zh: '每一层里检出 transport 校正后的 ATE（Cohen\'s h={h}），共 {strata} 层；α=0.05 双侧、power=0.80',
    en: 'detect the transport-corrected ATE inside each stratum (Cohen\'s h={h}) across all {strata} of them, at α=0.05 two-sided and power 0.80',
  },
  pin_one_proportion: {
    zh: '让这个边际概率的 95% 置信区间半宽 ≤{precision}（按 p={p} 的最坏方差算）',
    en: 'hold this marginal probability\'s 95% CI to a half-width of {precision} or less, at the worst-case variance for p={p}',
  },
  pin_the_target_distribution: {
    zh: '把目标人群的 P*(Z) 估到每层 ±{precision} 以内，共 {strata} 层（按最坏情况 p={p} 算）',
    en: 'pin the target population\'s P*(Z) to within ±{precision} in each of {strata} strata, computed at the worst case p={p}',
  },
  trace_a_dose_response_curve: {
    zh: 'K={points} 个 X 采样点 × n={per_point}/点 (Cohen\'s d=0.5, α=0.05, power=0.80)',
    en: 'K={points} sampling points in X × n={per_point} each (Cohen\'s d=0.5, α=0.05, power=0.80)',
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

export const RECOVERY_FACTOR_WORDS: Record<string, Words> = {
  adjusted_conditional: {
    zh: '调整后的条件分布 {target}',
    en: 'the adjusted conditional {target}',
  },
  covariate_marginal: {
    zh: '协变量边缘分布 {target}',
    en: 'the covariate marginal {target}',
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
  coarsening_does_not_partition_the_proxy: {
    zh: '`{proxy}` 上声明的粗化与这一列实际持有的层级对不上：声明覆盖 {declared}，列里是 {observed}。每个观测到的层级要落在且只落在一个组里，每个组要指到确实存在的层级——否则折出来的通道就不是这一列的重新编码',
    en: 'the coarsening declared for `{proxy}` does not line up with the levels that column holds: the declaration covers {declared}, the column has {observed}. Every observed level has to fall in exactly one group and every group has to name levels that are there, or the folded channel is not a recoding of this column',
  },
  coarsening_group_count_is_not_k: {
    zh: '`{proxy}` 上声明的粗化分成了 {groups} 组，而 query 里 U 的类别数是 k={k}。这些组就是 U 的那 k 个状态，所以组数不是自由的：要么改分组，要么改 latent_cardinality',
    en: 'the coarsening declared for `{proxy}` makes {groups} groups while the query posits k={k} states for U. The groups ARE those k states, so their count is not free: either regroup or change latent_cardinality',
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
    zh: '近端公式 (5) 要求每个代理都恰好呈现 k={k} 个层级；实际 |Z|={z}、|W|={w}。要用更细的代理，就在 query 的 proxy_coarsening 里说明每个代理的哪些层级并作 k 组中的一组——哪些层级代表 U 的同一个状态，数据本身答不了',
    en: 'proximal formula (5) needs each proxy to present exactly k={k} levels; observed |Z|={z}, |W|={w}. To use a finer proxy, say on the query\'s proxy_coarsening which of its levels make up each of the k groups — which levels stand for the same state of U is not something the data answers',
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

export const SELECTION_SHORTFALL_WORDS: Record<string, Words> = {
  no_admissible_selection_backdoor_set: {
    zh: '没有一组已观测的变量同时满足选择-后门的两个条件',
    en: 'no observed set satisfies both selection-backdoor conditions',
  },
  outcome_not_separable_from_selection: {
    zh: '给定 {treatment} 时，{outcome} 与选择节点不可 d-分离（再加上任何一组已观测的变量也不行）',
    en: 'given {treatment}, {outcome} cannot be d-separated from the selection nodes — nor by adding any observed set to the conditioning',
  },
  treatment_or_outcome_not_in_graph: {
    zh: '处理或结局不在图中',
    en: 'the treatment or the outcome is not in the graph',
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

export const SUTVA_CONCERN_WORDS: Record<string, Words> = {
  spillover_must_be_recorded: {
    zh: '若有溢出 / 同侪效应，需登记并在分析中纳入',
    en: 'where spillover or peer effects exist, record them and carry them into the analysis',
  },
  units_must_not_coordinate: {
    zh: '受试者之间不能讨论 / 协调干预（违反 SUTVA）',
    en: 'subjects must not discuss or coordinate the intervention between themselves (that violates SUTVA)',
  },
}

export const THETA_PRIOR_CLAIM_WORDS: Record<string, Words> = {
  a_commonsense_prior: {
    zh: '{key} = {value}（LLM 常识 prior）',
    en: '{key} = {value} (a commonsense prior from the language model)',
  },
}

export const TIME_WINDOW_WORDS: Record<string, Words> = {
  baseline_and_two_follow_ups: {
    zh: '建议 baseline + 4w + 12w（视实际研究问题调整）',
    en: 'baseline + 4w + 12w is a reasonable start (adjust to the actual research question)',
  },
}

export const TRANSPORT_BLOCKED_WORDS: Record<string, Words> = {
  no_s_admissible_set: {
    zh: '搬不过来——没有哪个调整集能抹平它与目标总体的差别',
    en: 'does not carry over — no adjustment set evens out its difference from the target population',
  },
  treatment_or_outcome_off_diagram: {
    zh: '搬不过来——处理或结局根本不在这个源总体的选择图上',
    en: 'does not carry over — the treatment or the outcome is not on this source domain\'s selection diagram at all',
  },
}

export const UNBIASED_DISTRIBUTION_WORDS: Record<string, Words> = {
  the_weights: {
    zh: '来自未受选择影响样本的调整权重',
    en: 'adjustment weights from a sample selection did not touch',
  },
  unbiased: {
    zh: '来自未受选择影响样本的 {expression}',
    en: '{expression} from a sample selection did not touch',
  },
}

export const UNNAMED_WORDS: Record<string, Words> = {
  intervention: {
    zh: '干预变量',
    en: 'the intervention variable',
  },
  outcome: {
    zh: '目标变量',
    en: 'the outcome variable',
  },
  population: {
    zh: '<未命名>',
    en: '<unnamed>',
  },
  source_population: {
    zh: '<源人群>',
    en: '<source population>',
  },
  target_population: {
    zh: '<目标人群>',
    en: '<target population>',
  },
}

export const BETWEEN_CLAUSES: Words = {
  zh: '，',
  en: ', ',
}

export const BETWEEN_ITEMS: Words = {
  zh: '、',
  en: ', ',
}

export const BETWEEN_SENTENCES: Words = {
  zh: '',
  en: ' ',
}

export const BETWEEN_STATEMENTS: Words = {
  zh: '；',
  en: '; ',
}

export const ENDONYM: Words = {
  zh: '中文',
  en: 'English',
}
