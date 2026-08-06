"""Classification of the flat ``numeric_estimate.assumptions`` channel.

Every estimator declares what its number rests on as a flat list of snake_case
IDs (a few declare Chinese prose instead). That list is the oldest and the only
UNIVERSAL assumption channel — every numeric answer has one. The assumption
ledger aggregates the load-bearing assumptions into one severity-ranked view,
so it has to read this channel; to do that it needs, per ID, the two things the
flat list does not carry:

- **layer** — which part of the answer stops being true if it is false;
- **testable** — can the reader do something to check it.

**What belongs on this list at all.** A row is a claim about the world that
this answer needs: if it is false the answer is wrong. A sentence that,
being false, would leave the answer unchanged or better is not a member,
however true and however worth telling the reader — "monotonicity was not
assumed" is the shape, and it was here twice, ranked invalidating, counted
in the headline "N of these void the conclusion". What such a sentence is
really about is the answer (an interval instead of a point) or the line
next to it (an assumption nothing could refute), and both of those have
somewhere of their own to be said. Note that a negation in the NAME is no
signal either way: sixteen rows begin with ``no_`` and every one of them —
no unmeasured confounding, no intermediate confounder — is a claim about
the world that the answer rests on.

Severity used to be a third column here, on all 146 rows, and it never once
disagreed with the layer beside it — because it is that layer's grade and not
a judgement about the assumption. It is asked of :class:`themis.ledger.Layer`
now. ``testable`` is the contrast that makes the point: two identification
assumptions genuinely differ on it, so it stays.

The default matters more than the table. An ID nobody has classified is
presumed to be an *identification* assumption — invalidating, therefore — and
is surfaced with its raw text: on a disclosure surface the safe direction of
error is to over-report, never to drop. Adding an estimator therefore cannot
make an assumption disappear — at worst it appears untranslated.

Two shapes are matched: exact IDs, and prefixes for the IDs an estimator builds
with a runtime suffix (a cluster column name, a covariate name). Prefix entries
are explicit data, not keyword heuristics — an ID that merely *contains* a word
is not classified by it.

**Provenance is answered here too**, by :func:`answerable`, and for BOTH of the
channels that carry an estimator's assumptions — this flat list and the
structured identification specs. It lives here because who can overrule an
assumption is a property of the assumption, and this is the only table keyed on
the assumption. When each channel answered for itself, one ID could carry two
provenances at once; keying both on the ID makes "one assumption, one answer"
true by construction rather than by a guard.
"""
from __future__ import annotations

from ..ledger import Layer, Provenance

# layer / testable / Chinese claim
_Entry = tuple[Layer, bool, str]

# The two vocabularies this table classifies INTO are declared in
# :mod:`themis.ledger`, beside the third field of the same ledger line and
# beside the statement of which producer may write which. This module says
# which entry each ID gets; it does not get to say what the choices are.
_ID = Layer.IDENTIFICATION
_FORM = Layer.FUNCTIONAL_FORM
_CI = Layer.CONFIDENCE


# --- exact IDs ----------------------------------------------------------------

_EXACT: dict[str, _Entry] = {
    # -- exchangeability / positivity / consistency (the back-door core) -------
    "conditional_exchangeability_given_adjustment_set": (
        _ID, False, "给定调整集后处理可视为随机分配（无未观测混杂）"),
    "unconditional_exchangeability_treatment_is_marginally_randomized": (
        _ID, False, "无条件可交换性：处理近似边际随机化（无需调整）"),
    "joint_conditional_exchangeability_given_adjustment_set": (
        _ID, False, "联合可交换性：给定调整集后整个处理向量可视为随机分配"),
    "unconditional_exchangeability_treatments_marginally_randomized": (
        _ID, False, "无条件可交换性：整个处理向量近似边际随机化"),
    "sequential_exchangeability_no_unmeasured_time_varying_confounding": (
        _ID, False, "顺序可交换性：不存在未观测的时变混杂"),
    "positivity_overlap_of_treatment_arms": (
        _ID, False, "重叠 / positivity：调整集每一层内两个处理臂都有样本"),
    "positivity_overlap_of_every_treatment_cell": (
        _ID, False, "重叠：处理向量的每个组合格子在每层内都有样本"),
    "positivity_every_conditioning_stratum_has_support": (
        _ID, False, "重叠：识别公式条件到的每一层在数据中都有样本"),
    "positivity_every_conditioning_stratum_of_the_estimand_has_support": (
        _ID, False, "重叠：估计量条件到的每一层在数据中都有样本"),
    "positivity_the_asked_arm_has_support_in_each_stratum": (
        _ID, False, "重叠：被问的那个处理臂在每一层内都有样本"),
    "positivity_every_treatment_arm_has_support_in_each_stratum": (
        _ID, False, "重叠：每一层内两个处理臂都有样本"),
    "positivity_every_contributing_stratum_has_support": (
        _ID, False, "重叠：每个进入求和的层在数据中都有样本"),
    "positivity_each_treatment_level_observed_within_history_strata": (
        _ID, False, "重叠：每个处理水平在每条历史分层内都被观测到"),
    "positivity_in_each_z_stratum_of_source": (
        _ID, False, "重叠：源人群的每个 Z 层内都有样本"),
    "positivity_both_instrument_arms_present_in_every_stratum": (
        _ID, False, "重叠：每一层内工具变量的两个取值都出现"),
    "consistency_of_potential_outcomes": (
        _ID, False, "一致性：观察到的 Y 等于该处理下的潜在结果"),
    "consistency_of_potential_outcomes_under_joint_intervention": (
        _ID, False, "一致性：联合干预下的潜在结果良定义"),
    "consistency_and_no_interference": (
        _ID, False, "一致性且无干扰：一个单位的处理不影响别人的结果"),
    "consistency_well_defined_sustained_treatment_strategy": (
        _ID, False, "一致性：所问的持续处理策略定义明确"),

    # -- instrumental variables ------------------------------------------------
    "iv1_relevance": (_ID, True, "IV 与处理相关（第一阶段非零）"),
    "iv1_relevance_instrument_affects_treatment": (
        _ID, True, "IV 与处理相关（第一阶段非零）"),
    "iv1_relevance_instruments_affect_treatment": (
        _ID, True, "各工具变量都与处理相关"),
    "iv2_exclusion_instrument_affects_outcome_only_via_treatment": (
        _ID, False, "排他性：IV 只通过处理影响结果"),
    "iv2_exclusion_instruments_affect_outcome_only_via_treatment": (
        _ID, False, "排他性：各工具变量都只通过处理影响结果"),
    "iv3_independence_instrument_independent_of_unmeasured_confounders": (
        _ID, False, "IV 与未观测混杂独立"),
    "iv3_independence_instrument_independent_of_latent_confounders": (
        _ID, False, "IV 与潜混杂独立"),
    "iv3_independence_instruments_independent_of_latent_confounders": (
        _ID, False, "各工具变量都与潜混杂独立"),
    "monotonicity_no_defiers": (
        _ID, False, "单调性：不存在 defier（处理方向对每个单位一致）"),
    "monotonicity_first_stage_effect_same_sign_for_all_units": (
        _ID, False, "单调性：第一阶段效应对所有单位同号"),
    "conditioning_set_blocks_instrument_outcome_backdoor_given_W": (
        _ID, False, "给定条件集 W 后 IV 到结果的后门已被阻断"),
    "estimand_is_LATE_on_compliers_not_population_ATE": (
        _ID, False, "估计量是 LATE（仅 complier 子人群），不是人群 ATE"),
    "strata_aggregated_by_complier_share_not_by_stratum_probability": (
        _ID, False,
        "各层按 complier 份额加权（不是按层概率）——得到的是 complier 平均因果效应"),
    "constant_treatment_effect_else_estimand_is_weighted_average": (
        _ID, False, "处理效应恒定；否则估计量是一个加权平均而非 ATE"),
    "overidentifying_restrictions_testable_via_sargan_homoskedastic": (
        _ID, True, "过度识别约束成立（可用同方差 Sargan 检验）"),
    "overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j": (
        _ID, True, "过度识别约束成立（可用 Sargan 与稳健 Hansen J 检验）"),

    # -- front door ------------------------------------------------------------
    "front_door_criterion_holds_on_graph": (
        _ID, False, "前门准则在因果图上成立"),
    "frontdoor_full_mediation": (
        _ID, False, "中介集拦截 X→Y 的所有有向路径"),
    "frontdoor_no_treatment_mediator_backdoor": (
        _ID, False, "X 到中介之间无未阻断的后门"),
    "frontdoor_mediator_outcome_backdoor_blocked_given_treatment": (
        _ID, False, "给定 X 后中介到 Y 的后门已被阻断"),
    "mediator_intercepts_all_directed_paths_from_treatment_to_outcome": (
        _ID, False, "中介拦截了 X→Y 的所有有向路径"),
    "no_unblocked_backdoor_from_treatment_to_mediator": (
        _ID, False, "X→M 段无未阻断的后门"),
    "backdoor_from_mediator_to_outcome_blocked_by_treatment": (
        _ID, False, "给定 X 后 M→Y 的后门已被阻断"),

    # -- mediation -------------------------------------------------------------
    "sequential_ignorability_treatment_and_mediator": (
        _ID, False, "顺序可忽略性：处理与中介都满足条件随机化（Imai 关键假设）"),
    "sequential_ignorability_treatment_and_mediator_set": (
        _ID, False, "顺序可忽略性：处理与整个中介集都满足条件随机化"),
    "no_intermediate_confounder_affected_by_treatment": (
        _ID, False, "不存在被处理影响的中间混杂（X 的后代同时影响 M 和 Y）"),
    "pearl_2001_four_conditions_hold_on_the_graph": (
        _ID, False, "Pearl 2001 中介分解四条件在因果图上成立"),
    "vanderweele_vansteelandt_2014_joint_natural_effect_conditions": (
        _ID, False, "VanderWeele-Vansteelandt 2014 联合自然效应条件成立"),
    "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment": (
        _ID, False, "给定 X 后调整集阻断 M→Y 的后门"),
    "adjustment_set_blocks_mediatorset_outcome_backdoor_given_treatment": (
        _ID, False, "给定 X 后调整集阻断整个中介集到 Y 的后门"),
    "adjustment_set_blocks_xy_and_my_backdoors": (
        _ID, False, "调整集同时阻断 X→Y 与 M→Y 的后门"),
    "adjustment_set_blocks_xy_and_my_chain_backdoors": (
        _ID, False, "调整集同时阻断 X→Y 与整条中介链到 Y 的后门"),
    "no_unmeasured_confounder_x_y_given_m_and_adjustment": (
        _ID, False, "给定中介与调整集后 X–Y 无未观测混杂"),
    "no_unmeasured_confounder_x_y_given_chain_and_adjustment": (
        _ID, False, "给定整条中介链与调整集后 X–Y 无未观测混杂"),
    "no_unmeasured_confounder_m_y_given_x_and_adjustment": (
        _ID, False, "给定 X 与调整集后 M–Y 无未观测混杂"),
    "no_unmeasured_confounder_between_successive_mediators": (
        _ID, False, "相邻中介之间无未观测混杂"),
    "no_confounder_of_mediatorset_outcome_affected_by_treatment_outside_the_set": (
        _ID, False, "中介集之外不存在被处理影响的中介–结局混杂"),
    "no_effect_of_exposure_that_confounds_mediator_outcome": (
        _ID, False, "暴露不产生任何混杂中介–结局关系的效应"),
    "no_unmeasured_confounder_exposure_outcome_given_adjustment": (
        _ID, False, "给定调整集后暴露–结局无未观测混杂"),
    "no_unmeasured_confounder_exposure_mediator_given_adjustment": (
        _ID, False, "给定调整集后暴露–中介无未观测混杂"),
    "no_unmeasured_confounder_mediator_outcome_given_exposure_and_adjustment": (
        _ID, False, "给定暴露与调整集后中介–结局无未观测混杂"),

    # -- ADMG / general ID / counterfactual ------------------------------------
    "admg_structure_correct_including_latent_confounders": (
        _ID, False, "ADMG 结构正确，包括潜混杂（双向边）的位置"),
    "conditional_effect_identified_via_idc_rule2_exchange": (
        _ID, False, "条件效应经 IDC 规则 2 交换后点识别"),
    "joint_effect_point_identified_by_set_id_no_adjustment_set_exists": (
        _ID, False, "联合效应由集合值 ID 点识别（不存在调整集）"),
    "binary_cause_and_effect": (_ID, False, "原因与结果都是二值的"),
    "binary_treatment_and_outcome": (_ID, False, "处理与结局都是二值的"),
    "exogeneity_no_backdoor_path_do_risk_equals_conditional": (
        _ID, False, "外生性：无后门路径，故 do-风险等于条件概率"),
    # Plural and singular are two ids because they are two claims: PN/PS/PNS
    # need BOTH arms licensed, a counterfactual cell needs only the one it
    # asks about. Both read "干预风险取自随机实验" until now, which dropped the
    # only thing the second id exists to carry.
    "interventional_risks_from_randomized_experiment": (
        _ID, False, "两臂干预风险 P(Y|do X) 与 P(Y|do ¬X) 都取自随机实验"),
    "interventional_risk_from_randomized_experiment": (
        _ID, False, "本格所需的那一臂干预风险取自随机实验"),
    "monotonicity_x_never_prevents_y_point_identification": (
        _ID, False, "单调性：X 从不阻止 Y —— 这条把区间收紧成点"),

    # -- proximal --------------------------------------------------------------
    "U_sufficient_confounder_and_proxies_satisfy_miao_model_f": (
        _ID, False, "U 是充分混杂，且两个 proxy 满足 Miao 的 model f"),
    "diagram_correct_including_unobserved_confounder_U_and_proxy_roles": (
        _ID, False, "因果图正确，包括未观测混杂 U 与两个 proxy 的角色"),
    "latent_cardinality_k_correct_and_proxies_have_exactly_k_levels": (
        _ID, False, "潜变量类别数 k 正确，且两个 proxy 各恰有 k 个水平"),
    "rank_condition_P(W|Z,x)_invertible_verified_on_data": (
        _ID, True, "秩条件：P(W|Z,x) 可逆（已在数据上核验）"),

    # -- structural SCM counterfactual -----------------------------------------
    "recursive_acyclic_scm_matching_the_declared_graph": (
        _ID, False, "SCM 是与所声明因果图一致的递归无环模型"),
    "correct_parent_set_per_node_no_unmeasured_common_cause_of_a_node_and_its_parents": (
        _ID, False, "每个节点的父集正确：节点与其父之间无未观测共同原因"),

    # -- measurement error -----------------------------------------------------
    "non_differential_misclassification_Y_indep_XZ_given_Ytrue": (
        _ID, False,
        "非差异误分类：给定真实结局后，记录到的结局与处理、协变量无关（同一张混淆矩阵适用于所有臂和层）"),
    "non_differential_misclassification_X_indep_YZ_given_Xtrue": (
        _ID, False,
        "非差异误分类：给定真实暴露后，记录到的暴露与结局、协变量无关"),
    "independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z": (
        _ID, False,
        "两条误差通道在真值下相互独立（同一份记录上暴露和结局不会被一起写错）——"
        "这是单通道校正不需要、双边校正才需要的额外前提"),
    "differential_misclassification_by_outcome_M_depends_on_Y": (
        _ID, False, "差异误分类：暴露的误分类率随真实结局而变（回忆偏倚）"),
    "differential_misclassification_by_exposure_arm_M_depends_on_X": (
        _ID, False, "差异误分类：结局的误分类率随处理臂而变（检出偏倚）"),
    "known_confusion_matrix_from_validation_study": (
        _ID, False, "混淆矩阵由验证研究给出且视为已知、无抽样误差"),
    "known_confusion_matrices_from_validation_studies": (
        _ID, False, "两条通道的混淆矩阵都由验证研究给出且视为已知"),
    "known_per_arm_confusion_matrices_from_validation_study": (
        _ID, False, "逐处理臂的混淆矩阵由验证研究给出且视为已知"),
    "known_per_outcome_confusion_matrices_from_validation_study": (
        _ID, False, "逐结局水平的混淆矩阵由验证研究给出且视为已知"),
    "known_per_covariate_stratum_confusion_matrices_from_validation_study": (
        _ID, False, "逐协变量分层的混淆矩阵由验证研究给出且视为已知"),
    "confusion_matrix_invertible": (
        _ID, True, "混淆矩阵可逆（|det| 已在估计时核验）"),
    "recovered_true_exposure_marginal_positive": (
        _ID, True, "求逆恢复出的真实暴露边际为正（否则条件风险无定义）"),

    # -- selection / missing data / transport ----------------------------------
    "selection_backdoor_admissible_set": (
        _ID, False, "选择后门可容许集成立"),
    "external_reference_sample_is_unbiased": (
        _ID, False, "外部参照样本本身无偏"),
    "adjustment_set_is_valid_backdoor_set": (
        _ID, False, "调整集是合法的后门集"),
    "estimand_recoverable_ordered_factorization_valid": (
        _ID, False, "估计量在该缺失图下可恢复：有序分解合法"),
    "s_admissibility_of_adjustment_set": (
        _ID, False, "调整集满足 S-可容许性（迁移到目标人群的关键条件）"),
    "no_treatment_effect_modification_outside_z_in_either_pop": (
        _ID, False, "两个人群中都不存在 Z 之外的效应修饰"),
    "no_directed_edge_between_treatments": (
        _ID, False, "两个处理之间没有有向边"),

    # -- functional form / estimator machinery ---------------------------------
    "linear_outcome_regression": (_FORM, True, "outcome 用线性回归建模"),
    "logit_outcome_regression": (_FORM, True, "outcome 用 logit 回归建模"),
    "logit_outcome_link": (_FORM, True, "outcome 用 logit 链接"),
    "linear_outcome_regression_with_saturated_treatment_interactions": (
        _FORM, True, "outcome 用带饱和处理交互的线性回归"),
    "logit_outcome_regression_with_saturated_treatment_interactions": (
        _FORM, True, "outcome 用带饱和处理交互的 logit 回归"),
    "linear_mediator_model_with_normal_residual_variance": (
        _FORM, True, "中介模型为线性且残差方差为正态"),
    "logit_mediator_model": (_FORM, True, "中介用 logit 模型"),
    "logit_outcome_model_with_exposure_mediator_interaction": (
        _FORM, True, "outcome 用带暴露×中介交互的 logit 模型"),
    "linearity_of_first_and_second_stage": (
        _FORM, True, "IV 的一、二阶段都设为线性"),
    "linear_structural_equations_every_relevant_mechanism": (
        _FORM, True, "每条相关机制都设为线性结构方程"),
    "additive_exogenous_noise_abducted_per_unit": (
        _FORM, True, "外生噪声可加，按单位 abduct 回来"),
    "mediators_drawn_jointly_via_gaussian_residual_copula": (
        _FORM, True, "多个中介按高斯残差 copula 联合抽样"),
    "no_mediator_mediator_interaction_in_outcome_model": (
        _FORM, True, "outcome 模型里中介之间没有交互项"),
    "outcome_model_correctly_specified_at_chain_fixed_values": (
        _FORM, True, "outcome 模型在链上固定值处设定正确"),
    "correct_specification_of_covariate_transition_and_outcome_models": (
        _FORM, True, "协变量转移模型与结局模型设定正确"),
    "correct_specification_of_treatment_propensity_models": (
        _FORM, True, "各期处理倾向模型设定正确"),
    "marginal_structural_model_additive_no_treatment_time_interaction": (
        _FORM, True, "边际结构模型是可加的（处理与时间无交互）"),
    "doubly_robust_outcome_OR_propensity_model_correct": (
        _FORM, True, "双稳健：结局回归或倾向模型任一设定正确即一致"),
    "correct_propensity_model_single_robust": (
        _FORM, True, "单稳健：一致性依赖倾向模型设定正确"),
    "tmle_targeted_substitution_estimator": (
        _FORM, True, "TMLE：对初始结局拟合做定标的代入估计"),
    "hajek_stabilized_weights": (
        _FORM, True, "IPW 用 Hájek 稳定化权重（组内归一，方差更小）"),
    "horvitz_thompson_weights": (
        _FORM, True, "IPW 用 Horvitz-Thompson 原始权重"),
    "discrete_variables_saturated_nonparametric_plug_in": (
        _FORM, True, "离散变量的饱和非参数代入估计（无函数形式假设）"),
    "discrete_adjustment_strata": (_FORM, True, "调整集按离散分层处理"),
    "chain_rule_factoring_of_joint_mediator_conditional": (
        _FORM, True, "联合中介的条件分布按链式法则分解"),
    "conditional_from_own_complete_cases_marginal_from_its_own": (
        _FORM, True, "条件分布取自其自身的完整病例、边际取自其自身"),
    "continuous_mediator_odds_ratio_approximation_rare_outcome": (
        _FORM, True, "连续中介的 OR 近似依赖罕见结局假设"),
    "decomposition_reported_at_sample_mean_covariate_value": (
        _FORM, True, "分解在协变量的样本均值处报告"),

    # -- dose-response --------------------------------------------------------
    "no_unmeasured_confounding_given_W": (
        _ID, False, "无未观测混杂（given W）"),
    "positivity_every_sampled_dose_has_support_on_W": (
        _ID, False, "重叠：每个采样剂量在所有 W 上都有支持"),

    # -- how the interval was computed -----------------------------------------
    "ci_via_analytic_influence_function": (
        _CI, True, "置信区间由影响函数解析求得（非 bootstrap）"),
    "ci_via_percentile_bootstrap": (
        _CI, True, "置信区间由百分位 bootstrap 求得"),
}


# --- prefixes (IDs the estimator builds with a runtime suffix) -----------------

_PREFIX: tuple[tuple[str, _Entry], ...] = (
    ("ci_via_pairs_cluster_bootstrap_on_",
     (_CI, True, "置信区间由按 {} 重采样整簇的 pairs cluster bootstrap 求得")),
    ("ci_not_cluster_robust_econml_dml_interval_ignores_",
     (_CI, True, "置信区间不是簇稳健的：解析区间忽略了 {} 的簇内相关，可能偏窄")),
    ("cluster_robust_influence_variance_on_",
     (_CI, True, "影响函数方差按 {} 做了簇稳健修正")),
    ("propensity_clipped_to_floor_",
     (_FORM, True, "倾向得分被截断到下限（{}）")),
    ("differential_misclassification_by_covariate_",
     (_ID, False, "差异误分类：误分类率随协变量 {} 而变，逐层用本层矩阵求逆")),
    ("zminus_reweighting_from_unbiased_reference_",
     (_ID, False, "Z⁻ 的重加权取自无偏参照样本（{}）")),
    ("zplus_weights_from_unbiased_reference_",
     (_ID, False, "Z⁺ 的权重取自无偏参照样本（{}）")),
    ("backdoor_adjustment_set_",
     (_ID, False, "后门调整集充分：{} 阻断 X→Y 的所有后门路径")),
    ("backdoor_adjustment_",
     (_ID, False, "后门调整：{}")),
    # A mismeasured continuous outcome: the first premise is what makes the
    # point estimate immune to the noise, so its failure kills the answer; the
    # second only fixes how much precision the noise is said to cost.
    ("outcome_error_classical_non_differential_on_",
     (_ID, False,
      "结局 {} 的测量误差是经典可加且**非差异**的（与暴露、调整集、真实结局独立，"
      "均值 0）——正因如此点估计不受它影响；若误差随暴露臂或真实结局而变，点估计有偏")),
    ("outcome_error_variance_known_and_fixed_on_",
     (_CI, True,
      "结局 {} 的测量误差方差 σ²_v 已知且固定：区间的精度代价按它折算，"
      "但不传播验证研究自身对 σ²_v 的不确定性")),
    ("monotonicity_",
     (_ID, False, "单调性（{}）")),
    ("mtr_",
     (_ID, False, "单调处理响应（{}）：把无假设界的一侧收紧")),
    # regression calibration declares Chinese prose rather than IDs; the
    # sentence openings are stable and carry the same three-way distinction.
    ("聚类 bootstrap", (_CI, True, "")),
    ("经典加性测量误差", (_ID, False, "")),
    ("被经典加性误差污染的", (_ID, False, "")),
    ("后门可识别", (_ID, False, "")),
)


# --- who can overrule it ------------------------------------------------------

# Listed by exception rather than as a fifth column on every row above,
# because the default is right for an estimator's assumptions as a class:
# an estimator declares what its own answer rests on. What breaks the class
# is the caller opting IN to something the method does not need — the
# answer runs without it and comes back wider — and that is a short list
# whose members would be invisible spread across a hundred identical
# entries.
#
# ``monotonicity_first_stage_effect_same_sign_for_all_units`` is deliberately
# NOT here: an IV point estimate is the LATE and there is no LATE without it,
# so the caller cannot withdraw it and keep an answer. Which is why this is
# keyed on whole IDs and one prefix, and not on the word "monotonicity".
_ANSWERABLE_EXACT: dict[str, Provenance] = {
    # PN / PS / PNS: without it the three are Tian-Pearl intervals.
    "monotonicity_x_never_prevents_y_point_identification":
        Provenance.CALLER_ASSERTED,
    # A counterfactual cell: without it the cell is its bounds. When no
    # do-risk was obtainable this same assertion does ALL the work with
    # nothing to check it against, which the producer says on this line's
    # own claim rather than as an entry beside it.
    "monotonicity_non_decreasing_in_treatment": Provenance.CALLER_ASSERTED,
    "monotonicity_non_increasing_in_treatment": Provenance.CALLER_ASSERTED,
}

_ANSWERABLE_PREFIX: tuple[tuple[str, Provenance], ...] = (
    # Monotone treatment response, declared on the query and used to tighten
    # one side of the assumption-free bounds.
    ("mtr_", Provenance.CALLER_ASSERTED),
    # An outcome measurement-error assessment runs only because the caller
    # attached the model, and both premises are about the caller's own
    # measurement process. Drop the model and the point estimate stands —
    # what is lost is the accounting of what the noise costs the interval.
    ("outcome_error_classical_non_differential_on_", Provenance.CALLER_ASSERTED),
    ("outcome_error_variance_known_and_fixed_on_", Provenance.CALLER_ASSERTED),
)


def answerable(assumption_id: str) -> Provenance:
    """Who can overrule this assumption, for either channel that carries one.

    The structured identification specs ask this too, keyed on the same id,
    so a spec and the flat declaration it restates cannot disagree about
    what the reader may do with the line.
    """
    text = str(assumption_id)
    hit = _ANSWERABLE_EXACT.get(text)
    if hit is not None:
        return hit
    for prefix, provenance in _ANSWERABLE_PREFIX:
        if text.startswith(prefix):
            return provenance
    return Provenance.INHERENT


def classify_assumption(assumption: str) -> dict:
    """Classify one flat assumption declaration.

    Returns ``{"id", "claim", "layer", "testable", "provenance"}`` — what this
    table knows. The severity is not among them: it is the layer's grade, and
    it reaches the entry when the caller stamps it, from the one place that
    says which grade each layer falls into.

    An unrecognised declaration is surfaced as an identification assumption —
    invalidating, therefore — with its raw text as the claim: a disclosure
    surface must never drop something because nobody classified it.
    """
    text = str(assumption)
    common = {"id": text, "provenance": answerable(text)}
    entry = _EXACT.get(text)
    if entry is not None:
        layer, testable, zh = entry
        return {**common, "claim": zh, "layer": layer, "testable": testable}
    for prefix, (layer, testable, template) in _PREFIX:
        if text.startswith(prefix):
            suffix = text[len(prefix):]
            claim = template.format(suffix) if template else text
            return {**common, "claim": claim, "layer": layer,
                    "testable": testable}
    return {**common, "claim": text, "layer": _ID, "testable": False}


def is_classified(assumption: str) -> bool:
    """Whether the glossary recognises this declaration (exact or prefix).

    Used by the parity test that keeps the table in step with what the
    estimators emit; an unrecognised ID still reaches the ledger, so this is a
    quality check, not a correctness gate.
    """
    text = str(assumption)
    return text in _EXACT or any(text.startswith(p) for p, _ in _PREFIX)
