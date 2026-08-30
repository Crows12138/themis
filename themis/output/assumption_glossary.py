"""Classification of the flat ``numeric_estimate.assumptions`` channel.

Every estimator declares what its number rests on as a flat list of snake_case
IDs. That list is the oldest and the only
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

from collections.abc import Callable

from .. import language
from ..estimation.declared import ORDERED_COVARIATE_ASSUMPTION
from ..ledger import Layer, Monotonicity, Provenance

# layer / testable / what the reader is told.
#
# One shape for both tables below, which they did not have while a prefix row
# could hold a RULE where its words go. The rule is not a kind of wording —
# it says how an id is read, and the sentence it lands on is a row like any
# other — so it lives in :data:`_RULES`, keyed by the prefix whose tail it
# knows how to split.
_Row = tuple[Layer, bool, language.Words]

#: What one occasion puts in a sentence's holes.
#:
#: Not ``str``: a value renders the same for every reader and travels
#: rendered, and a WORD does not — it travels as its vocabulary and its
#: token, and is met by the reader's own word for it.
_Slots = dict[str, object]

#: How an id whose tail is not one name is read: which row the reader is
#: handed, and what this occasion puts in its holes.
#:
#: A rule rather than a template exists because a runtime suffix is not
#: always ONE name: an id that pins a premise to two of the caller's
#: variables carries both, and a single hole cannot place them. Filling one
#: hole with the pair would put `z_on_y` in front of the reader, which is the
#: untranslated identifier this table exists to keep off the page.
#:
#: A rule ends at a TOKEN and this occasion's facts rather than at text.
#: Returning text would mean writing that text in every language at the
#: rule's own point of use, and a sentence written where it is used is a
#: sentence with no template for its translation to sit beside. It is handed
#: the prefix as well as the tail because the prefix is the token of the row
#: it matched, and a rule that named its own row would be that prefix written
#: down a second time.
_Fills = Callable[[str, str], tuple[str, _Slots]]

# The two vocabularies this table classifies INTO are declared in
# :mod:`themis.ledger`, beside the third field of the same ledger line and
# beside the statement of which producer may write which. This module says
# which entry each ID gets; it does not get to say what the choices are.
_ID = Layer.IDENTIFICATION
_FORM = Layer.FUNCTIONAL_FORM
_CI = Layer.CONFIDENCE
#: One numeric input supplied rather than measured. Distinct from ``_FORM``
#: in a way that is load-bearing here and not merely tidy: a form line's
#: provenance is read off the estimate's own ``form_provenance`` rather than
#: off this module's table, because who settled a SHAPE is a fact about the
#: run. A penalty is not a shape — it is a number added to make an ill-posed
#: solve have an answer — so it keeps its provenance where it is declared.
_PARAM = Layer.PARAMETER


# --- exact IDs ----------------------------------------------------------------

_EXACT: dict[str, _Row] = {
    # -- exchangeability / positivity / consistency (the back-door core) -------
    "conditional_exchangeability_given_adjustment_set": (
        _ID, False, {"zh": "给定调整集后处理可视为随机分配（无未观测混杂）",
                     "en": "given the adjustment set, treatment can be taken "
                           "as randomly assigned (no unmeasured confounding)"}),
    "unconditional_exchangeability_treatment_is_marginally_randomized": (
        _ID, False, {"zh": "无条件可交换性：处理近似边际随机化（无需调整）",
                     "en": "unconditional exchangeability: treatment is "
                           "approximately marginally randomized (no "
                           "adjustment needed)"}),
    "joint_conditional_exchangeability_given_adjustment_set": (
        _ID, False, {"zh": "联合可交换性：给定调整集后整个处理向量可视为随机"
                           "分配",
                     "en": "joint exchangeability: given the adjustment set, "
                           "the whole treatment vector can be taken as "
                           "randomly assigned"}),
    "unconditional_exchangeability_treatments_marginally_randomized": (
        _ID, False, {"zh": "无条件可交换性：整个处理向量近似边际随机化",
                     "en": "unconditional exchangeability: the whole "
                           "treatment vector is approximately marginally "
                           "randomized"}),
    "sequential_exchangeability_no_unmeasured_time_varying_confounding": (
        _ID, False, {"zh": "顺序可交换性：不存在未观测的时变混杂",
                     "en": "sequential exchangeability: there is no "
                           "unmeasured time-varying confounding"}),
    # Every row below says the same kind of thing — some stratum, arm or
    # cell has units in the data — and every one of them is a question the
    # DATA answers. Which is why they are the identification rows marked
    # testable: exchangeability asks about a world nobody observed, and
    # positivity asks whether a count is zero. The eleven were marked
    # untestable together, which is what a field filled by the layer beside
    # it rather than by the assumption looks like — and eleven of the
    # structured specs said True at the same time, disagreeing with this
    # table about what the reader could go and do.
    "positivity_overlap_of_treatment_arms": (
        _ID, True, {"zh": "重叠 / positivity：调整集每一层内两个处理臂都有"
                           "样本",
                     "en": "overlap / positivity: both treatment arms have "
                           "units in every stratum of the adjustment set"}),
    # The row above is a CLAIM, and where the adjustment set has strata the
    # count can contradict it. This is the same identification assumption
    # reported as what it was found to be — same layer, so the same grade:
    # the reader is not told less loudly because the answer came back.
    "positivity_violated_some_strata_hold_one_arm": (
        _ID, True, {"zh": "重叠 / positivity 不成立（已逐层核对）：调整集里"
                          "有层只含一个处理臂，那些层里缺的那一臂由结局模型"
                          "外推补出，不是数据里的对比",
                     "en": "overlap / positivity does NOT hold (checked cell "
                           "by cell): strata of the adjustment set hold a "
                           "single treatment arm, and the missing arm there "
                           "is the outcome model's extrapolation rather than "
                           "a comparison in the data"}),
    "positivity_overlap_of_every_treatment_cell": (
        _ID, True, {"zh": "重叠：处理向量的每个组合格子在每层内都有样本",
                     "en": "overlap: every cell of the treatment vector has "
                           "units in every stratum"}),
    "positivity_every_conditioning_stratum_has_support": (
        _ID, True, {"zh": "重叠：识别公式条件到的每一层在数据中都有样本",
                     "en": "overlap: every stratum the identification "
                           "formula conditions on has units in the data"}),
    "positivity_every_conditioning_stratum_of_the_estimand_has_support": (
        _ID, True, {"zh": "重叠：估计量条件到的每一层在数据中都有样本",
                     "en": "overlap: every stratum the estimand conditions "
                           "on has units in the data"}),
    "positivity_the_asked_arm_has_support_in_each_stratum": (
        _ID, True, {"zh": "重叠：被问的那个处理臂在每一层内都有样本",
                     "en": "overlap: the arm being asked about has units in "
                           "every stratum"}),
    "positivity_every_treatment_arm_has_support_in_each_stratum": (
        _ID, True, {"zh": "重叠：每一层内两个处理臂都有样本",
                     "en": "overlap: both treatment arms have units in every "
                           "stratum"}),
    "positivity_every_contributing_stratum_has_support": (
        _ID, True, {"zh": "重叠：每个进入求和的层在数据中都有样本",
                     "en": "overlap: every stratum entering the sum has "
                           "units in the data"}),
    "positivity_each_treatment_level_observed_within_history_strata": (
        _ID, True, {"zh": "重叠：每个处理水平在每条历史分层内都被观测到",
                     "en": "overlap: every treatment level is observed "
                           "within every history stratum"}),
    "positivity_in_each_z_stratum_of_source": (
        _ID, True, {"zh": "重叠：源人群的每个 Z 层内都有样本",
                     "en": "overlap: every Z stratum of the source "
                           "population has units"}),
    "positivity_both_instrument_arms_present_in_every_stratum": (
        _ID, True, {"zh": "重叠：每一层内工具变量的两个取值都出现",
                     "en": "overlap: both values of the instrument appear in "
                           "every stratum"}),
    "consistency_of_potential_outcomes": (
        _ID, False, {"zh": "一致性：观察到的 Y 等于该处理下的潜在结果",
                     "en": "consistency: the observed Y equals the potential "
                           "outcome under the treatment received"}),
    "consistency_of_potential_outcomes_under_joint_intervention": (
        _ID, False, {"zh": "一致性：联合干预下的潜在结果良定义",
                     "en": "consistency: the potential outcome under the "
                           "joint intervention is well defined"}),
    "consistency_and_no_interference": (
        _ID, False, {"zh": "一致性且无干扰：一个单位的处理不影响别人的结果",
                     "en": "consistency and no interference: one unit's "
                           "treatment does not affect another unit's outcome"}),
    "consistency_well_defined_sustained_treatment_strategy": (
        _ID, False, {"zh": "一致性：所问的持续处理策略定义明确",
                     "en": "consistency: the sustained treatment strategy "
                           "being asked about is well defined"}),

    # -- instrumental variables ------------------------------------------------
    "iv1_relevance": (_ID, True, {"zh": "IV 与处理相关（第一阶段非零）",
                                  "en": "the instrument is relevant to "
                                        "treatment (non-zero first stage)"}),
    "iv1_relevance_instrument_affects_treatment": (
        _ID, True, {"zh": "IV 与处理相关（第一阶段非零）",
                    "en": "the instrument is relevant to treatment (non-zero "
                          "first stage)"}),
    "iv1_relevance_instruments_affect_treatment": (
        _ID, True, {"zh": "各工具变量都与处理相关",
                    "en": "every instrument is relevant to treatment"}),
    "iv2_exclusion_instrument_affects_outcome_only_via_treatment": (
        _ID, False, {"zh": "排他性：IV 只通过处理影响结果",
                     "en": "exclusion: the instrument affects the outcome "
                           "only through treatment"}),
    "iv2_exclusion_instruments_affect_outcome_only_via_treatment": (
        _ID, False, {"zh": "排他性：各工具变量都只通过处理影响结果",
                     "en": "exclusion: every instrument affects the outcome "
                           "only through treatment"}),
    # Exclusion for a treatment VECTOR is a different claim from exclusion for
    # one treatment: an instrument may reach the outcome through ANOTHER of the
    # treatments and still satisfy it, because that path is inside the vector
    # being intervened on. Two ids, because a reader told the singular sentence
    # would be told something the method does not require.
    "iv2_exclusion_instruments_affect_outcome_only_via_treatment_vector": (
        _ID, False, {"zh": "排他性：各工具变量只通过这一组处理影响结果",
                     "en": "exclusion: every instrument affects the outcome "
                           "only through the treatments being intervened on"}),
    "iv3_independence_instrument_independent_of_unmeasured_confounders": (
        _ID, False, {"zh": "IV 与未观测混杂独立",
                     "en": "the instrument is independent of the unmeasured "
                           "confounders"}),
    "iv3_independence_instrument_independent_of_latent_confounders": (
        _ID, False, {"zh": "IV 与潜混杂独立",
                     "en": "the instrument is independent of the latent "
                           "confounders"}),
    "iv3_independence_instruments_independent_of_latent_confounders": (
        _ID, False, {"zh": "各工具变量都与潜混杂独立",
                     "en": "every instrument is independent of the latent "
                           "confounders"}),
    "monotonicity_no_defiers": (
        _ID, False, {"zh": "单调性：不存在 defier（处理方向对每个单位一致）",
                     "en": "monotonicity: there are no defiers (treatment "
                           "moves in one direction for every unit)"}),
    "monotonicity_first_stage_effect_same_sign_for_all_units": (
        _ID, False, {"zh": "单调性：第一阶段效应对所有单位同号",
                     "en": "monotonicity: the first-stage effect has the "
                           "same sign for every unit"}),
    "monotonicity_refutable_dose_response_same_direction_for_all_units": (
        _ID, True,
        {"zh": "单调性：工具把每个单位的剂量都往同一个方向推（没有人被它推低）"
               "——**这条在这里是可反驳的**：它成立时每一档的权重都与总体一阶段同号，"
               "所以任何一档出现负权重就是数据在反驳它",
         "en": "monotonicity: the instrument moves every unit's dose the same "
               "way (nobody is pushed down by it) — **and here it is "
               "refutable**: under it every step's weight shares the sign of "
               "the aggregate first stage, so a negative weight on any step "
               "**is the data contradicting it**"}),
    "conditioning_set_blocks_instrument_outcome_backdoor_given_W": (
        _ID, False, {"zh": "给定条件集 W 后 IV 到结果的后门已被阻断",
                     "en": "given the conditioning set W, the back-door from "
                           "the instrument to the outcome is blocked"}),
    "estimand_is_LATE_on_compliers_not_population_ATE": (
        _ID, False, {"zh": "估计量是 LATE（仅 complier 子人群），不是人群 "
                           "ATE",
                     "en": "the estimand is the LATE (compliers only), not "
                           "the population ATE"}),
    "estimand_is_ACR_a_weighted_average_of_per_step_responses": (
        _ID, False,
        {"zh": "估计量是 ACR：把剂量每一档上的单位效应按各自权重平均起来的那个数，"
               "不是任何单独一档的效应，也不是人群 ATE",
         "en": "the estimand is the ACR: the weighted average of the per-unit "
               "response at each step of the dose, which is neither any one "
               "step's effect nor the population ATE"}),
    "strata_aggregated_by_complier_share_not_by_stratum_probability": (
        _ID, False,
        {"zh": "各层按 complier 份额加权（不是按层概率）——得到的是 complier "
               "平均因果效应",
         "en": "strata are weighted by complier share rather than by stratum "
               "probability — what comes out is the complier average causal "
               "effect"}),
    "constant_treatment_effect_else_estimand_is_weighted_average": (
        _ID, False, {"zh": "处理效应恒定；否则估计量是一个加权平均而非 ATE",
                     "en": "the treatment effect is constant; otherwise the "
                           "estimand is a weighted average rather than the "
                           "ATE"}),
    # The F critical value the region is cut at. Confidence layer, because it
    # moves the region's boundary and nothing else — there is no point estimate
    # underneath for it to move.
    "homoskedastic_errors_for_the_anderson_rubin_f_critical_value": (
        _CI, True, {"zh": "误差同方差——置信域的临界值按 F 分布取，异方差下"
                          "该换成稳健形式",
                    "en": "the errors are homoskedastic, which is what makes "
                          "the region's F critical value the right one; under "
                          "heteroskedasticity the robust form is needed"}),
    "overidentifying_restrictions_testable_via_sargan_homoskedastic": (
        _ID, True, {"zh": "过度识别约束成立（可用同方差 Sargan 检验）",
                    "en": "the overidentifying restrictions hold (testable "
                          "by the homoskedastic Sargan test)"}),
    "overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j": (
        _ID, True, {"zh": "过度识别约束成立（可用 Sargan 与稳健 Hansen J 检"
                          "验）",
                    "en": "the overidentifying restrictions hold (testable "
                          "by Sargan and by the robust Hansen J test)"}),

    # -- front door ------------------------------------------------------------
    "front_door_criterion_holds_on_graph": (
        _ID, False, {"zh": "前门准则在因果图上成立",
                     "en": "the front-door criterion holds on the causal "
                           "graph"}),
    "frontdoor_full_mediation": (
        _ID, False, {"zh": "中介集拦截 X→Y 的所有有向路径",
                     "en": "the mediator set intercepts every directed path "
                           "from X to Y"}),
    "frontdoor_no_treatment_mediator_backdoor": (
        _ID, False, {"zh": "X 到中介之间无未阻断的后门",
                     "en": "there is no unblocked back-door between X and "
                           "the mediator"}),
    "frontdoor_mediator_outcome_backdoor_blocked_given_treatment": (
        _ID, False, {"zh": "给定 X 后中介到 Y 的后门已被阻断",
                     "en": "given X, the back-door from the mediator to Y is "
                           "blocked"}),
    "mediator_intercepts_all_directed_paths_from_treatment_to_outcome": (
        _ID, False, {"zh": "中介拦截了 X→Y 的所有有向路径",
                     "en": "the mediator intercepts every directed path from "
                           "X to Y"}),
    "no_unblocked_backdoor_from_treatment_to_mediator": (
        _ID, False, {"zh": "X→M 段无未阻断的后门",
                     "en": "the X→M leg has no unblocked back-door"}),
    "backdoor_from_mediator_to_outcome_blocked_by_treatment": (
        _ID, False, {"zh": "给定 X 后 M→Y 的后门已被阻断",
                     "en": "given X, the back-door from M to Y is blocked"}),

    # -- mediation -------------------------------------------------------------
    "sequential_ignorability_treatment_and_mediator": (
        _ID, False, {"zh": "顺序可忽略性：处理与中介都满足条件随机化（Imai "
                           "关键假设）",
                     "en": "sequential ignorability: both treatment and "
                           "mediator are conditionally randomized (Imai's "
                           "key assumption)"}),
    "sequential_ignorability_treatment_and_mediator_set": (
        _ID, False, {"zh": "顺序可忽略性：处理与整个中介集都满足条件随机化",
                     "en": "sequential ignorability: treatment and the whole "
                           "mediator set are conditionally randomized"}),
    "no_intermediate_confounder_affected_by_treatment": (
        _ID, False, {"zh": "不存在被处理影响的中间混杂（X 的后代同时影响 M "
                           "和 Y）",
                     "en": "there is no intermediate confounder affected by "
                           "treatment (a descendant of X that affects both M "
                           "and Y)"}),
    "pearl_2001_four_conditions_hold_on_the_graph": (
        _ID, False, {"zh": "Pearl 2001 中介分解四条件在因果图上成立",
                     "en": "Pearl's 2001 four conditions for mediation "
                           "decomposition hold on the causal graph"}),
    "vanderweele_vansteelandt_2014_joint_natural_effect_conditions": (
        _ID, False, {"zh": "VanderWeele-Vansteelandt 2014 联合自然效应条件成"
                           "立",
                     "en": "the VanderWeele-Vansteelandt 2014 conditions for "
                           "joint natural effects hold"}),
    "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment": (
        _ID, False, {"zh": "给定 X 后调整集阻断 M→Y 的后门",
                     "en": "given X, the adjustment set blocks the back-door "
                           "from M to Y"}),
    "adjustment_set_blocks_mediatorset_outcome_backdoor_given_treatment": (
        _ID, False, {"zh": "给定 X 后调整集阻断整个中介集到 Y 的后门",
                     "en": "given X, the adjustment set blocks the back-door "
                           "from the whole mediator set to Y"}),
    "adjustment_set_blocks_xy_and_my_backdoors": (
        _ID, False, {"zh": "调整集同时阻断 X→Y 与 M→Y 的后门",
                     "en": "the adjustment set blocks both the X→Y and the "
                           "M→Y back-doors"}),
    "adjustment_set_blocks_xy_and_my_chain_backdoors": (
        _ID, False, {"zh": "调整集同时阻断 X→Y 与整条中介链到 Y 的后门",
                     "en": "the adjustment set blocks both the X→Y back-door "
                           "and the back-doors from the whole mediator chain "
                           "to Y"}),
    "no_unmeasured_confounder_x_y_given_m_and_adjustment": (
        _ID, False, {"zh": "给定中介与调整集后 X–Y 无未观测混杂",
                     "en": "given the mediator and the adjustment set, X–Y "
                           "has no unmeasured confounder"}),
    "no_unmeasured_confounder_x_y_given_chain_and_adjustment": (
        _ID, False, {"zh": "给定整条中介链与调整集后 X–Y 无未观测混杂",
                     "en": "given the whole mediator chain and the "
                           "adjustment set, X–Y has no unmeasured confounder"}),
    "no_unmeasured_confounder_m_y_given_x_and_adjustment": (
        _ID, False, {"zh": "给定 X 与调整集后 M–Y 无未观测混杂",
                     "en": "given X and the adjustment set, M–Y has no "
                           "unmeasured confounder"}),
    "no_unmeasured_confounder_between_successive_mediators": (
        _ID, False, {"zh": "相邻中介之间无未观测混杂",
                     "en": "successive mediators have no unmeasured "
                           "confounder between them"}),
    "no_confounder_of_mediatorset_outcome_affected_by_treatment_outside_the_set": (
        _ID, False, {"zh": "中介集之外不存在被处理影响的中介–结局混杂",
                     "en": "no mediator-outcome confounder affected by "
                           "treatment sits outside the mediator set"}),
    "no_effect_of_exposure_that_confounds_mediator_outcome": (
        _ID, False, {"zh": "暴露不产生任何混杂中介–结局关系的效应",
                     "en": "the exposure has no effect that confounds the "
                           "mediator-outcome relation"}),
    "no_unmeasured_confounder_exposure_outcome_given_adjustment": (
        _ID, False, {"zh": "给定调整集后暴露–结局无未观测混杂",
                     "en": "given the adjustment set, exposure–outcome has "
                           "no unmeasured confounder"}),
    "no_unmeasured_confounder_exposure_mediator_given_adjustment": (
        _ID, False, {"zh": "给定调整集后暴露–中介无未观测混杂",
                     "en": "given the adjustment set, exposure–mediator has "
                           "no unmeasured confounder"}),
    "no_unmeasured_confounder_mediator_outcome_given_exposure_and_adjustment": (
        _ID, False, {"zh": "给定暴露与调整集后中介–结局无未观测混杂",
                     "en": "given exposure and the adjustment set, "
                           "mediator–outcome has no unmeasured confounder"}),

    # -- ADMG / general ID / counterfactual ------------------------------------
    "admg_structure_correct_including_latent_confounders": (
        _ID, False, {"zh": "ADMG 结构正确，包括潜混杂（双向边）的位置",
                     "en": "the ADMG structure is correct, including where "
                           "the latent confounders (bidirected edges) sit"}),
    "conditional_effect_identified_via_idc_rule2_exchange": (
        _ID, False, {"zh": "条件效应经 IDC 规则 2 交换后点识别",
                     "en": "the conditional effect is point-identified after "
                           "the IDC rule-2 exchange"}),
    "joint_effect_point_identified_by_set_id_no_adjustment_set_exists": (
        _ID, False, {"zh": "联合效应由集合值 ID 点识别（不存在调整集）",
                     "en": "the joint effect is point-identified by "
                           "set-valued ID (no adjustment set exists)"}),
    "binary_cause_and_effect": (_ID, False, {"zh": "原因与结果都是二值的",
                                             "en": "both the cause and the effect "
                                                   "are binary"}),
    "binary_treatment_and_outcome": (_ID, False, {"zh": "处理与结局都是二值的",
                                                  "en": "both the treatment and the "
                                                        "outcome are binary"}),
    "exogeneity_no_backdoor_path_do_risk_equals_conditional": (
        _ID, False, {"zh": "外生性：无后门路径，故 do-风险等于条件概率",
                     "en": "exogeneity: there is no back-door path, so the "
                           "do-risk equals the conditional probability"}),
    # Plural and singular are two ids because they are two claims: PN/PS/PNS
    # need BOTH arms licensed, a counterfactual cell needs only the one it
    # asks about. Both read "干预风险取自随机实验" until now, which dropped the
    # only thing the second id exists to carry.
    "interventional_risks_from_randomized_experiment": (
        _ID, False, {"zh": "两臂干预风险 P(Y|do X) 与 P(Y|do ¬X) 都取自随机"
                           "实验",
                     "en": "both interventional risks, P(Y|do X) and P(Y|do "
                           "¬X), come from a randomized experiment"}),
    "interventional_risk_from_randomized_experiment": (
        _ID, False, {"zh": "本格所需的那一臂干预风险取自随机实验",
                     "en": "the one interventional risk this cell needs "
                           "comes from a randomized experiment"}),
    # One premise about the world, two ids, because what the ROUTE can do
    # about it differs and ``testable`` is a column of this table. The name
    # says which: assumed, or put up against something that could answer
    # back. :attr:`themis.risk_provenance.RiskProvenance.can_refute_a_premise`
    # is the route half, and folding it into the id is what lets one table
    # answer instead of two.
    "monotonicity_assumed_x_never_prevents_y": (
        _ID, False, {"zh": "单调性：X 从不阻止 Y——这条把区间收紧成点，"
                           "而这条路线上没有任何东西能反驳它",
                     "en": "monotonicity: X never prevents Y — this is what "
                           "tightens the interval to a point, and nothing on "
                           "this route could answer back"}),
    "monotonicity_refutable_x_never_prevents_y": (
        _ID, True, {"zh": "单调性：X 从不阻止 Y——它作为模型限制进入响应型"
                          "多面体，**不加它可行、加了不可行，就是数据在反驳"
                          "这个方向**",
                    "en": "monotonicity: X never prevents Y — it enters the "
                          "response-type polytope as a restriction of the "
                          "model, so a program that is feasible without it "
                          "and infeasible with it **is the data contradicting "
                          "the declared direction**"}),

    # -- proximal --------------------------------------------------------------
    "U_sufficient_confounder_and_proxies_satisfy_miao_model_f": (
        _ID, False, {"zh": "U 是充分混杂，且两个 proxy 满足 Miao 的 model f",
                     "en": "U is a sufficient confounder and the two proxies "
                           "satisfy Miao's model f"}),
    "diagram_correct_including_unobserved_confounder_U_and_proxy_roles": (
        _ID, False, {"zh": "因果图正确，包括未观测混杂 U 与两个 proxy 的角色",
                     "en": "the causal graph is correct, including the "
                           "unobserved confounder U and the roles of the two "
                           "proxies"}),
    "latent_cardinality_k_correct_and_proxies_have_exactly_k_levels": (
        _ID, False, {"zh": "潜变量类别数 k 正确，且两个 proxy 各恰有 k 个水"
                           "平",
                     "en": "the latent cardinality k is correct and each "
                           "proxy has exactly k levels"}),
    # The same premise where the proxies are finer and the caller said how to
    # fold them. It REPLACES the one above rather than joining it, because
    # the one above states as a fact the thing this run is not doing.
    "latent_cardinality_k_correct_and_the_declared_coarsening_folds_each_proxy_to_k_levels": (
        _ID, False,
        {"zh": "潜变量类别数 k 正确，且你声明的粗化把两个 proxy 各折成 k 组"
               "——哪些层级代表 U 的同一个状态是你的判断，数据不作答；换一"
               "个分组就是另一个数",
         "en": "the latent cardinality k is correct, and the coarsening you "
               "declared folds each proxy into k groups — which levels stand "
               "for the same state of U is your judgement and the data does "
               "not answer it; a different grouping is a different number"}),
    "rank_condition_P(W|Z,x)_invertible_verified_on_data": (
        _ID, True, {"zh": "秩条件：P(W|Z,x) 可逆（已在数据上核验）",
                    "en": "rank condition: P(W|Z,x) is invertible (verified "
                          "on the data)"}),
    # -- proximal, testing the null instead of estimating ----------------------
    # The three the causal-null test carries and formula (5) does not. The
    # first two REPLACE their point-estimate counterparts rather than joining
    # them, because each states something weaker: only W is folded, and only
    # the stacked channel is asked to have full row rank.
    "latent_cardinality_k_correct_and_the_outcome_proxy_folds_to_k_levels": (
        _ID, False,
        {"zh": "潜变量类别数 k 正确，且结局侧 proxy 恰好折成 k 组。这里只对"
               "结局侧 proxy 提这个要求：γ 的长度就是 U 的状态数，而处理侧 "
               "proxy 的层级在检验里是当矩条件用的，有几个用几个",
         "en": "the latent cardinality k is correct and the outcome-side "
               "proxy folds to exactly k groups. Only the outcome-side proxy "
               "is held to this: γ has one coefficient per state of U, while "
               "the treatment-side proxy's levels are spent as moments and "
               "the test takes as many as there are"}),
    "stacked_channel_Q_has_full_row_rank_verified_on_data": (
        _ID, True,
        {"zh": "把各处理层级的 P(W|Z,x) 叠成的那个矩阵行满秩（已在数据上核"
               "验）。这比公式 (5) 要的可逆性弱：单个 x 上的通道可以是奇异"
               "的，叠起来仍然满秩——这正是能检验、却给不出数的那个区间",
         "en": "the matrix that stacks P(W|Z,x) across the treatment's levels "
               "has full row rank (verified on the data). Weaker than the "
               "invertibility formula (5) needs: the channel at a single x "
               "may be singular while the stack still has full rank — which "
               "is exactly the regime where the null can be tested and no "
               "number can be given"}),
    "chi_square_reference_distribution_is_a_large_sample_approximation": (
        _ID, False,
        {"zh": "p 值来自卡方分布，而这个分布是大样本近似——每个 (x, z) 格"
               "子里的均值和比例要接近正态，检验统计量才服从卡方。格子越"
               "薄，这个近似越差，p 值也越不可信",
         "en": "the p-value comes from a chi-square distribution, and that "
               "distribution is a large-sample approximation — the cell "
               "means and proportions have to be near-normal for the "
               "statistic to follow it. The thinner the cells, the worse the "
               "approximation and the less the p-value is worth"}),
    # -- proximal, the continuous regime ---------------------------------------
    # Marked UNCHECKED, and that is the fact rather than an omission: the
    # completeness of a conditional operator is not testable from data at all
    # (Canay-Santos-Shaikh 2013). The condition number the estimator does
    # check is a necessary consequence of it and never the condition, so
    # writing this line as checked would be reporting a proof of something
    # weaker under the name of the thing itself.
    "completeness_of_the_conditional_operator_E[.|Z,X=x]": (
        _ID, False,
        {"zh": "完备性：E[·|Z,X=x] 作为算子对 bridge 所在的函数类完备——这是"
               "秩条件的连续版本，而它**在数据上原则上不可检验**"
               "（Canay-Santos-Shaikh 2013）；估计时核过的条件数只是它的必要"
               "推论，不是它本身",
         "en": "completeness: the operator E[·|Z,X=x] is complete for the "
               "class the bridge lies in — the continuous form of the rank "
               "condition, and one that is **not testable from data at all** "
               "(Canay-Santos-Shaikh 2013); the condition number checked at "
               "estimation time is a consequence of it and not the thing"}),
    "completeness_of_the_conditional_operator_E[.|W,A=a,X]": (
        _ID, False,
        {"zh": "完备性：E[·|W,A=a,X] 作为算子对处理桥 q 所在的函数类完备。"
               "这是上一条在另一个方向上的镜像——那一条让结局桥 h 被 Z 的矩"
               "定下来，这一条让 q 被 W 的矩定下来——同样**在数据上原则上"
               "不可检验**",
         "en": "completeness: the operator E[·|W,A=a,X] is complete for the "
               "class the treatment bridge q lies in. The mirror of the line "
               "above in the other direction — that one pins h down by "
               "moments of Z, this one pins q down by moments of W — and "
               "equally **not testable from data**"}),
    "the_outcome_bridge_lies_in_the_span_of_the_declared_sieve": (
        _ID, False,
        {"zh": "结局桥 h 落在你为它声明的基函数张成的空间里——基函数族和维数"
               "是断言不是设置：span 里没有这个 h，再多数据也逼近不到它",
         "en": "the outcome bridge h lies in the span of the basis you "
               "declared for it — the family and the dimension are an "
               "assertion and not a setting: if h is not in the span, more "
               "data does not approach it"}),
    "the_treatment_bridge_lies_in_the_span_of_the_declared_sieve": (
        _ID, False,
        {"zh": "处理桥 q 落在你为它声明的基函数张成的空间里。q 是倒数倾向"
               "得分那一侧的桥，本该处处为正，而对参数线性的 sieve 不保证"
               "这一点——真出现负值时会有单独一条 gap 说出来",
         "en": "the treatment bridge q lies in the span of the basis you "
               "declared for it. q sits on the reciprocal-propensity side and "
               "ought to be positive everywhere, which a sieve linear in its "
               "parameters does not guarantee — where it comes out negative a "
               "gap of its own says so"}),
    "the_bridge_varies_with_the_treatment_as_the_declared_basis_does": (
        _ID, False,
        {"zh": "曲线在两个水平之间的形状，是你给处理声明的那组基函数的形状，"
               "不是数据挑出来的。落在水平上的点由数据定，水平之间怎么连"
               "由声明定——处理上只给了一次多项式，真值是弯的，画出来也是"
               "直的，而且不会报告有偏差",
         "en": "the shape of the curve BETWEEN levels is the shape of the "
               "basis you declared on the treatment, not one the data chose. "
               "The data pin the points at the levels; the declaration says "
               "how they join up — a first-degree basis on the dose draws a "
               "straight line through a curved truth and reports no misfit"}),
    "at_least_one_of_the_two_bridges_lies_in_its_declared_span": (
        _ID, False,
        {"zh": "两座桥里**至少有一座**落在它声明的 span 里——哪一座都行，"
               "不需要知道是哪一座。这就是双稳健买到的东西（Cui et al. 2024 "
               "定理 3.2 的并模型），也是它的边界：两座都错时答案照样错，"
               "而这个估计量不会告诉你两座都错了",
         "en": "**at least one** of the two bridges lies in its declared span "
               "— either one, and you do not have to know which. That is what "
               "double robustness buys (Cui et al. 2024, Theorem 3.2's union "
               "model) and also its edge: where BOTH spans are wrong the "
               "answer is wrong too, and this estimator does not announce it"}),
    # Not identification and not functional form: the span above is the form,
    # and this is what was ADDED to solve for a coefficient inside it. A
    # heavier penalty shrinks the answer toward zero, so what it costs is the
    # value of the point — reported rather than assumed away, which is why it
    # is the one line here marked checked.
    #
    # Per BRIDGE, because each is its own ill-posed solve with its own scale
    # and the caller may have named one λ and left the other to the estimator.
    # One pair of lines covering both would have had to call that case either
    # chosen or defaulted, and it is neither.
    "treatment_bridge_regularisation_lambda_chosen_by_the_caller": (
        _PARAM, True,
        {"zh": "处理桥 q 的正则化强度 λ 是你在问题里选的。它和结局桥那一个是"
               "两个数：两条方程正则化的是两个不同的算子，各有各的尺度",
         "en": "the treatment bridge's regularisation λ is the one you chose. "
               "It is a different number from the outcome bridge's: the two "
               "equations regularise two different operators, each with its "
               "own scale"}),
    "treatment_bridge_regularisation_lambda_defaulted_by_the_estimator": (
        _PARAM, True,
        {"zh": "处理桥 q 的正则化强度 λ **没有人选**——估计器按这条方程自身的"
               "尺度取了一个稳定化的小值，规则和结局桥那一条相同，取到的数"
               "不同",
         "en": "**nobody chose** the treatment bridge's regularisation λ — the "
               "estimator took a small value scaled to that equation's own "
               "magnitude, by the same rule as the outcome bridge's and "
               "arriving at a different number"}),
    "regularisation_lambda_chosen_by_the_caller": (
        _PARAM, True,
        {"zh": "正则化强度 λ 是你在问题里选的。bridge 方程是不适定反问题，"
               "没有正则化就没有数值解；λ 越大，报出来的数越被拉向零。答案"
               "对它的敏感度已经算出来，随答案一起报",
         "en": "the regularisation λ is the one you chose in the question. "
               "The bridge equation is an ill-posed inverse problem and has "
               "no numeric solution without one; a larger λ pulls the "
               "reported number toward zero. How much the answer moves under "
               "it has been computed and travels beside it"}),
    "regularisation_lambda_defaulted_by_the_estimator": (
        _PARAM, True,
        {"zh": "正则化强度 λ **没有人选**——估计器按问题自身的尺度取了一个"
               "稳定化的小值。它稳定求解，不声称最优；换一个 λ 这个数就变，"
               "所以答案对它的敏感度随答案一起报",
         "en": "**nobody chose** the regularisation λ — the estimator took a "
               "small value scaled to the problem's own magnitude. It "
               "stabilises the solve and claims nothing about being optimal; "
               "a different λ is a different number, which is why how much "
               "the answer moves under it travels beside it"}),

    # -- structural SCM counterfactual -----------------------------------------
    "recursive_acyclic_scm_matching_the_declared_graph": (
        _ID, False, {"zh": "SCM 是与所声明因果图一致的递归无环模型",
                     "en": "the SCM is recursive and acyclic, and matches "
                           "the declared causal graph"}),
    "correct_parent_set_per_node_no_unmeasured_common_cause_of_a_node_and_its_parents": (
        _ID, False, {"zh": "每个节点的父集正确：节点与其父之间无未观测共同原"
                           "因",
                     "en": "each node's parent set is correct: no unmeasured "
                           "common cause of a node and its parents"}),

    # -- measurement error -----------------------------------------------------
    "non_differential_misclassification_Y_indep_XZ_given_Ytrue": (
        _ID, False,
        {"zh": "非差异误分类：给定真实结局后，记录到的结局与处理、协变量无关"
               "（同一张混淆矩阵适用于所有臂和层）",
         "en": "non-differential misclassification: given the true outcome, "
               "the recorded outcome is independent of treatment and "
               "covariates (one confusion matrix applies to every arm and "
               "stratum)"}),
    "non_differential_misclassification_X_indep_YZ_given_Xtrue": (
        _ID, False,
        {"zh": "非差异误分类：给定真实暴露后，记录到的暴露与结局、协变量无关",
         "en": "non-differential misclassification: given the true exposure, "
               "the recorded exposure is independent of outcome and "
               "covariates"}),
    "independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z": (
        _ID, False,
        {"zh": "两条误差通道在真值下相互独立（同一份记录上暴露和结局不会被一"
               "起写错）——这是单通道校正不需要、双边校正才需要的额外前提",
         "en": "the two error channels are independent given the truth "
               "(exposure and outcome are not mis-recorded together on the "
               "same record) — an extra premise the two-sided correction "
               "needs and the single-channel one does not"}),
    "differential_misclassification_by_outcome_M_depends_on_Y": (
        _ID, False, {"zh": "差异误分类：暴露的误分类率随真实结局而变（回忆偏"
                           "倚）",
                     "en": "differential misclassification: the exposure's "
                           "misclassification rates vary with the true "
                           "outcome (recall bias)"}),
    "differential_misclassification_by_exposure_arm_M_depends_on_X": (
        _ID, False, {"zh": "差异误分类：结局的误分类率随处理臂而变（检出偏倚）",
                     "en": "differential misclassification: the outcome's "
                           "misclassification rates vary with the treatment "
                           "arm (detection bias)"}),
    "known_confusion_matrix_from_validation_study": (
        _ID, False, {"zh": "混淆矩阵由验证研究给出且视为已知、无抽样误差",
                     "en": "the confusion matrix comes from a validation "
                           "study and is taken as known and free of sampling "
                           "error"}),
    "known_confusion_matrices_from_validation_studies": (
        _ID, False, {"zh": "两条通道的混淆矩阵都由验证研究给出且视为已知",
                     "en": "both channels' confusion matrices come from "
                           "validation studies and are taken as known"}),
    "known_per_arm_confusion_matrices_from_validation_study": (
        _ID, False, {"zh": "逐处理臂的混淆矩阵由验证研究给出且视为已知",
                     "en": "the per-arm confusion matrices come from a "
                           "validation study and are taken as known"}),
    "known_per_outcome_confusion_matrices_from_validation_study": (
        _ID, False, {"zh": "逐结局水平的混淆矩阵由验证研究给出且视为已知",
                     "en": "the per-outcome-level confusion matrices come "
                           "from a validation study and are taken as known"}),
    "known_per_covariate_stratum_confusion_matrices_from_validation_study": (
        _ID, False, {"zh": "逐协变量分层的混淆矩阵由验证研究给出且视为已知",
                     "en": "the per-covariate-stratum confusion matrices "
                           "come from a validation study and are taken as "
                           "known"}),
    "confusion_matrix_invertible": (
        _ID, True, {"zh": "混淆矩阵可逆（|det| 已在估计时核验）",
                    "en": "the confusion matrix is invertible (|det| checked "
                          "at estimation time)"}),
    "recovered_true_exposure_marginal_positive": (
        _ID, True, {"zh": "求逆恢复出的真实暴露边际为正（否则条件风险无定义）",
                    "en": "the true-exposure marginal recovered by inversion "
                          "is positive (otherwise the conditional risk is "
                          "undefined)"}),

    # -- selection / missing data / transport ----------------------------------
    "selection_backdoor_admissible_set": (
        _ID, False, {"zh": "选择后门可容许集成立",
                     "en": "the selection back-door admissible set holds"}),
    "external_reference_sample_is_unbiased": (
        _ID, False, {"zh": "外部参照样本本身无偏",
                     "en": "the external reference sample is itself unbiased"}),
    "adjustment_set_is_valid_backdoor_set": (
        _ID, False, {"zh": "调整集是合法的后门集",
                     "en": "the adjustment set is a valid back-door set"}),
    "estimand_recoverable_ordered_factorization_valid": (
        _ID, False, {"zh": "估计量在该缺失图下可恢复：有序分解合法",
                     "en": "the estimand is recoverable under this "
                           "missingness graph: the ordered factorization is "
                           "valid"}),
    "s_admissibility_of_adjustment_set": (
        _ID, False, {"zh": "调整集满足 S-可容许性（迁移到目标人群的关键条件）",
                     "en": "the adjustment set is S-admissible (the key "
                           "condition for transporting to the target "
                           "population)"}),
    "no_treatment_effect_modification_outside_z_in_either_pop": (
        _ID, False, {"zh": "两个人群中都不存在 Z 之外的效应修饰",
                     "en": "neither population has effect modification "
                           "outside Z"}),
    "no_directed_edge_between_treatments": (
        _ID, False, {"zh": "两个处理之间没有有向边",
                     "en": "there is no directed edge between the two "
                           "treatments"}),

    # -- functional form / estimator machinery ---------------------------------
    "linear_outcome_regression": (_FORM, True, {"zh": "outcome 用线性回归建模",
                                                "en": "the outcome is modelled by "
                                                      "linear regression"}),
    # Not the row above, which is how the answer was FITTED — a modelling
    # choice, and the reader can look at its residuals. This one is a claim
    # about the world: the true model is linear in values nobody measured,
    # and it is that linearity which makes the moment correction exact
    # rather than approximate. There are no residuals to look at on the axis
    # it is about, which is why it is the one of the pair marked untestable.
    # The same proposition as the row below, in the other relationship a
    # family can have to it. There an estimator FITS a linear model, so it is
    # a shape choice: disclosed through the mechanism audit, graded
    # distorting. Here nothing is fitted — the identity that leaves the point
    # alone rests on the shape being TRUE, and under a nonlinear outcome
    # Berkson error biases rather than merely bends. Two ids because a layer
    # is a fact about use, and one id cannot carry two uses; the pair cannot
    # meet on one ledger, because the routing that reaches one excludes the
    # other.
    "berkson_identity_rests_on_a_linear_outcome_in_the_true_values": (
        _ID, False,
        {"zh": "真实结局模型对未观测的真值是线性的："
               "Y=β0+βx·X*+βz'·Z+ε。Berkson 恒等式靠的就是这条：E[X*|W,Z]=W "
               "只有穿过一个线性的条件均值，才会把系数原样带到名义值那边。"
               "结局模型非线性时，Berkson 误差是会致偏的——那时不校正就不再"
               "是对的做法，而这份数据没法反驳它，因为真值一次都没被观测到",
         "en": "the true outcome model is linear in the unobserved true "
               "values, Y=β0+βx·X*+βz'·Z+ε. The Berkson identity rests on "
               "exactly this: E[X*|W,Z]=W carries the coefficients over to "
               "the nominal value only through a conditional mean that is "
               "linear. Under a nonlinear outcome model Berkson error DOES "
               "bias, and leaving the point uncorrected stops being the "
               "right thing to do. These data cannot refute it — the true "
               "values were never observed once"}),
    "linear_structural_outcome_model_in_the_true_values": (
        _FORM, False,
        {"zh": "真实结局模型对未观测的真值是线性的："
               "Y=β0+βx·X*+βz'·Z+ε——正是这条线性使矩量校正精确"
               "而非近似",
         "en": "the true outcome model is linear in the unobserved true "
               "values, Y=β0+βx·X*+βz'·Z+ε — which is exactly what makes "
               "the moment correction exact rather than approximate"}),
    "logit_outcome_regression": (_FORM, True, {"zh": "outcome 用 logit 回归建模",
                                               "en": "the outcome is modelled by "
                                                     "logit regression"}),
    # Which model the wanted coefficient lives in. Not a preference between
    # two roads to one number: on a binary outcome the moment correction
    # de-attenuates the linear-probability slope and simulation-extrapolation
    # de-attenuates the log-odds ratio, both from the same two columns, so
    # nothing in the data can say which was meant. The caller says, and this
    # is the line where they said it.
    "simex_estimand_is_the_exposure_coefficient_in_a_logistic": (
        _FORM, True,
        {"zh": "要校正的量是 logistic 结局模型里暴露的系数——也就是真实暴露"
               "每增加一个单位的条件对数优势比，不是风险差",
         "en": "the quantity being corrected is the exposure's coefficient "
               "in a logistic outcome model — a conditional log-odds ratio "
               "per unit of the TRUE exposure, not a risk difference"}),
    "simex_estimand_is_the_exposure_coefficient_in_a_linear": (
        _FORM, True,
        {"zh": "要校正的量是线性结局模型里暴露的系数——真实暴露每增加一个"
               "单位的条件斜率",
         "en": "the quantity being corrected is the exposure's coefficient "
               "in a linear outcome model — a conditional slope per unit of "
               "the TRUE exposure"}),
    # The extrapolant is the one premise here that the data cannot speak to.
    # Its residuals over the simulated rungs say how well it fits where the
    # measurement got WORSE; the answer is read where it got perfect, which
    # is outside every rung. So all three are marked untestable, and which
    # family was declared is on the line rather than behind it.
    "simex_extrapolant_declared_rational": (
        _FORM, False,
        {"zh": "外推用的是有理式 θ(λ)=γ0+γ1/(γ2+λ)。它在 λ=−1 处的取值"
               "无法用数据检验——每一档模拟都在测量更差的方向上，而答案"
               "读在测量完美的那一点",
         "en": "the extrapolation is the rational family "
               "θ(λ)=γ0+γ1/(γ2+λ). Its value at λ=−1 is not checkable "
               "against the data: every simulated rung lies in the "
               "direction of WORSE measurement, and the answer is read "
               "where the measurement would be perfect"}),
    "simex_extrapolant_declared_quadratic": (
        _FORM, False,
        {"zh": "外推用的是二次式 θ(λ)=γ0+γ1λ+γ2λ²。它在 λ=−1 处的取值"
               "无法用数据检验——每一档模拟都在测量更差的方向上，而答案"
               "读在测量完美的那一点",
         "en": "the extrapolation is the quadratic family "
               "θ(λ)=γ0+γ1λ+γ2λ². Its value at λ=−1 is not checkable "
               "against the data: every simulated rung lies in the "
               "direction of WORSE measurement, and the answer is read "
               "where the measurement would be perfect"}),
    "simex_extrapolant_declared_linear": (
        _FORM, False,
        {"zh": "外推用的是直线 θ(λ)=γ0+γ1λ。它在 λ=−1 处的取值无法用数据"
               "检验——每一档模拟都在测量更差的方向上，而答案读在测量完美"
               "的那一点；直线也是三族里衰减刻画得最保守的一族",
         "en": "the extrapolation is the straight line θ(λ)=γ0+γ1λ. Its "
               "value at λ=−1 is not checkable against the data: every "
               "simulated rung lies in the direction of WORSE measurement, "
               "and the answer is read where the measurement would be "
               "perfect — and of the three families the line is the one "
               "that describes the decay most conservatively"}),
    "logit_outcome_link": (_FORM, True, {"zh": "outcome 用 logit 链接",
                                         "en": "the outcome uses a logit link"}),
    # Not a claim about the world and not a fitting preference either: it is
    # what a design matrix built by column DID to a covariate whose levels
    # are not two. The program CAN deny it — ``scale: "nominal"`` says the
    # levels carry no order, and the design build then gives that column one
    # indicator per level, so this row is absent. Which is why the claim
    # names the declaration that removes it: an assumption a reader cannot
    # act on reads as a disclaimer, and this one is a question with an answer.
    "multi_level_covariates_entered_as_ordered_numbers": (
        _FORM, True,
        {"zh": "调整集里有超过两档的列，它是以**一个有序的数**进模型的："
               "第三档到第一档的距离，被当成第二档的两倍。如果这一列是"
               "渠道、科室、地区这类**没有大小之分**的分类，这个形式就"
               "不成立，调整不干净，效应会带偏。"
               "这一行出现，是因为没有人说过这列没有大小："
               "把它声明为 `scale: \"nominal\"`，每一档就各占一项进模型，"
               "这条假设随之消失",
         "en": "an adjustment column with more than two levels entered the "
               "model as ONE ORDERED NUMBER: level three was taken to sit "
               "twice as far from level one as level two does. If the column "
               "names channels, departments or regions, which have no "
               "greater and lesser, the form does not hold, the adjustment "
               "is incomplete and the effect carries the difference. This "
               "row is here because nothing said the column has no order: "
               "declare it `scale: \"nominal\"` and each level enters as its "
               "own term, and the assumption goes away with it"}),
    # The three dose-response backends' shape choices. They arrived here as
    # sentences the estimator wrote and put in its own ``assumptions`` tuple,
    # where a sentence is not an id: the glossary could not recognise it, so
    # it reached the reader as an INVALIDATING identification premise, while
    # the same sentence came down the mechanism channel as a DISTORTING
    # functional form. One fact, two rows, two layers, two severities. What
    # each says is what a reader must decide about — the shape assumed and
    # what assuming it costs — rather than which library was called.
    "linear_in_treatment_partially_linear_dml": (
        _FORM, True,
        {"zh": "剂量-反应曲线在处理上是**直线**：Y = θ·T + g(W) + ε，其中 g "
               "不受形状约束而 T 只以一次项进入。真实剂量效应若是弯的，"
               "拟合出来的是它的最佳直线近似——曲线的形状是假设的，不是量出来的",
         "en": "the dose-response curve is a STRAIGHT LINE in the treatment: "
               "Y = θ·T + g(W) + ε, with g unconstrained in shape and T "
               "entering only linearly. A dose effect that truly bends is "
               "fitted as its best straight-line approximation — the curve's "
               "shape is assumed here, not measured"}),
    "linear_in_treatment_with_nonparametric_nuisance": (
        _FORM, True,
        {"zh": "剂量-反应曲线在处理上仍是**直线**，但两个 nuisance 拟合"
               "（Y~W、T~W）不必是——森林放开的是对协变量的形状约束，"
               "**没有**放开对剂量的那一条",
         "en": "the dose-response curve is still a STRAIGHT LINE in the "
               "treatment, though the two nuisance fits (Y~W and T~W) need "
               "not be — the forest relaxes the shape constraint on the "
               "covariates and NOT the one on the dose"}),
    "dose_binned_and_effects_estimated_per_bin": (
        _FORM, True,
        {"zh": "剂量按相邻采样点的中点切成若干档，同一档内的剂量被当作**可互换**。"
               "档内的剂量差异因此被抹平，而档与档之间的非线性能保留下来——"
               "曲线的分辨率就是采样点的疏密",
         "en": "the dose is cut into bins at the midpoints between adjacent "
               "sampling points, and doses inside one bin are treated as "
               "INTERCHANGEABLE. Variation within a bin is flattened while "
               "non-linearity between bins survives — the curve's resolution "
               "is however finely the sampling points were spaced"}),
    "linear_outcome_regression_with_saturated_treatment_interactions": (
        _FORM, True, {"zh": "outcome 用带饱和处理交互的线性回归",
                      "en": "the outcome is modelled by linear regression "
                            "with saturated treatment interactions"}),
    "logit_outcome_regression_with_saturated_treatment_interactions": (
        _FORM, True, {"zh": "outcome 用带饱和处理交互的 logit 回归",
                      "en": "the outcome is modelled by logit regression "
                            "with saturated treatment interactions"}),
    "linear_mediator_model_with_normal_residual_variance": (
        _FORM, True, {"zh": "中介模型为线性且残差方差为正态",
                      "en": "the mediator model is linear with normal "
                            "residual variance"}),
    "logit_mediator_model": (_FORM, True, {"zh": "中介用 logit 模型",
                                           "en": "the mediator is modelled by "
                                                 "logit"}),
    "logit_outcome_model_with_exposure_mediator_interaction": (
        _FORM, True, {"zh": "outcome 用带暴露×中介交互的 logit 模型",
                      "en": "the outcome is modelled by logit with an "
                            "exposure×mediator interaction"}),
    "linearity_of_first_and_second_stage": (
        _FORM, True, {"zh": "IV 的一、二阶段都设为线性",
                      "en": "both IV stages are taken to be linear"}),
    # Only the OUTCOME equation: the Anderson-Rubin region inverts a test of
    # it and never fits a first stage, so a line about the first stage's shape
    # would describe a step this method does not take.
    "linearity_of_the_outcome_equation_in_the_treatment_vector": (
        _FORM, True, {"zh": "结果方程对这一组处理设为线性",
                      "en": "the outcome equation is taken to be linear in "
                            "the treatments being intervened on"}),
    "linear_structural_equations_every_relevant_mechanism": (
        _FORM, True, {"zh": "每条相关机制都设为线性结构方程",
                      "en": "every relevant mechanism is taken to be a "
                            "linear structural equation"}),
    "additive_exogenous_noise_abducted_per_unit": (
        _FORM, True, {"zh": "外生噪声可加，按单位 abduct 回来",
                      "en": "the exogenous noise is additive and abducted "
                            "per unit"}),
    "mediators_drawn_jointly_via_gaussian_residual_copula": (
        _FORM, True, {"zh": "多个中介按高斯残差 copula 联合抽样",
                      "en": "the mediators are drawn jointly through a "
                            "Gaussian residual copula"}),
    "no_mediator_mediator_interaction_in_outcome_model": (
        _FORM, True, {"zh": "outcome 模型里中介之间没有交互项",
                      "en": "the outcome model has no mediator-by-mediator "
                            "interaction"}),
    "outcome_model_correctly_specified_at_chain_fixed_values": (
        _FORM, True, {"zh": "outcome 模型在链上固定值处设定正确",
                      "en": "the outcome model is correctly specified at the "
                            "values the chain is fixed to"}),
    "correct_specification_of_covariate_transition_and_outcome_models": (
        _FORM, True, {"zh": "协变量转移模型与结局模型设定正确",
                      "en": "the covariate-transition and outcome models are "
                            "correctly specified"}),
    "correct_specification_of_treatment_propensity_models": (
        _FORM, True, {"zh": "各期处理倾向模型设定正确",
                      "en": "the per-period treatment propensity models are "
                            "correctly specified"}),
    "marginal_structural_model_additive_no_treatment_time_interaction": (
        _FORM, True, {"zh": "边际结构模型是可加的（处理与时间无交互）",
                      "en": "the marginal structural model is additive (no "
                            "treatment-by-time interaction)"}),
    "doubly_robust_outcome_OR_propensity_model_correct": (
        _FORM, True, {"zh": "双稳健：结局回归或倾向模型任一设定正确即一致",
                      "en": "doubly robust: consistent if either the outcome "
                            "regression or the propensity model is correctly "
                            "specified"}),
    "correct_propensity_model_single_robust": (
        _FORM, True, {"zh": "单稳健：一致性依赖倾向模型设定正确",
                      "en": "singly robust: consistency rests on the "
                            "propensity model being correctly specified"}),
    "tmle_targeted_substitution_estimator": (
        _FORM, True, {"zh": "TMLE：对初始结局拟合做定标的代入估计",
                      "en": "TMLE: a substitution estimator targeted on the "
                            "initial outcome fit"}),
    "hajek_stabilized_weights": (
        _FORM, True, {"zh": "IPW 用 Hájek 稳定化权重（组内归一，方差更小）",
                      "en": "IPW uses Hájek stabilized weights (normalized "
                            "within group, lower variance)"}),
    "horvitz_thompson_weights": (
        _FORM, True, {"zh": "IPW 用 Horvitz-Thompson 原始权重",
                      "en": "IPW uses raw Horvitz-Thompson weights"}),
    "discrete_variables_saturated_nonparametric_plug_in": (
        _FORM, True, {"zh": "离散变量的饱和非参数代入估计（无函数形式假设）",
                      "en": "a saturated non-parametric plug-in over "
                            "discrete variables (no functional-form "
                            "assumption)"}),
    "discrete_adjustment_strata": (_FORM, True, {"zh": "调整集按离散分层处理",
                                                 "en": "the adjustment set is handled "
                                                       "as discrete strata"}),
    "chain_rule_factoring_of_joint_mediator_conditional": (
        _FORM, True, {"zh": "联合中介的条件分布按链式法则分解",
                      "en": "the joint mediator conditional is factored by "
                            "the chain rule"}),
    "conditional_from_own_complete_cases_marginal_from_its_own": (
        _FORM, True, {"zh": "条件分布取自其自身的完整病例、边际取自其自身",
                      "en": "the conditional comes from its own complete "
                            "cases and the marginal from its own"}),
    "continuous_mediator_odds_ratio_approximation_rare_outcome": (
        _FORM, True, {"zh": "连续中介的 OR 近似依赖罕见结局假设",
                      "en": "the odds-ratio approximation for a continuous "
                            "mediator rests on the rare-outcome assumption"}),
    "decomposition_reported_at_sample_mean_covariate_value": (
        _FORM, True, {"zh": "分解在协变量的样本均值处报告",
                      "en": "the decomposition is reported at the sample "
                            "mean of the covariates"}),

    # -- dose-response --------------------------------------------------------
    "no_unmeasured_confounding_given_W": (
        _ID, False, {"zh": "无未观测混杂（given W）",
                     "en": "no unmeasured confounding (given W)"}),
    "positivity_every_sampled_dose_has_support_on_W": (
        _ID, True, {"zh": "重叠：每个采样剂量在所有 W 上都有支持",
                     "en": "overlap: every sampled dose has support across W"}),

    # -- how the interval was computed -----------------------------------------
    "ci_via_analytic_influence_function": (
        _CI, True, {"zh": "置信区间由影响函数解析求得（非 bootstrap）",
                    "en": "the confidence interval is analytic, from the "
                          "influence function (not bootstrap)"}),
    "ci_via_percentile_bootstrap": (
        _CI, True, {"zh": "置信区间由百分位 bootstrap 求得",
                    "en": "the confidence interval comes from a percentile "
                          "bootstrap"}),
    # A width and a bias are different objects, and no width contains one.
    # Marked untestable for the reason the extrapolant rows above are: what
    # this row says is missing lives at λ=−1, where nothing was simulated.
    # A reader comparing this interval to a bootstrap one is comparing two
    # different things, and this line is where they find that out.
    "simex_interval_covers_sampling_not_extrapolation_error": (
        _CI, False,
        {"zh": "区间覆盖的是抽样波动和模拟本身的噪声，不覆盖外推式的近似"
               "误差——那是偏倚，任何方差都装不下偏倚。误差方差越大，外推"
               "残留的偏倚越可能把真值推到区间之外",
         "en": "the interval covers sampling variability and the "
               "simulation's own noise, and not the extrapolant's "
               "approximation error — that is a bias, and no variance "
               "contains a bias. The larger the error variance, the more "
               "readily the residual extrapolation bias carries the truth "
               "outside this interval"}),
}


# --- prefixes (IDs the estimator builds with a runtime suffix) -----------------

#: The instrumental-variable route's premise, once the two names are known.
#:
#: It has to say what this premise is NOT. Read as a wider version of the
#: classical one, it invites a reader to check the error against the exposure
#: and conclude they have checked this; the two conditions do not imply each
#: other in either direction.
_ERROR_AND_INSTRUMENT: language.Words = {
    "zh": "结局 {outcome} 的测量误差与工具变量 {instrument} 均值无关"
          "（E[V | {instrument}] = 0）—— IV 点估计不受这个误差影响，靠的正是"
          "这一条。它不是经典前提的放宽版：经典前提要求误差与**暴露和调整集**"
          "无关，这一条要求的是与**工具**无关，两者互不蕴含，检验了一个不等于"
          "检验了另一个",
    "en": "the measurement error on outcome {outcome} is mean-independent of "
          "the instrument {instrument} (E[V | {instrument}] = 0) — which is "
          "exactly what leaves the IV point estimate unaffected by that "
          "error. It is not a relaxed version of the classical premise: that "
          "one asks the error to be independent of the **exposure and the "
          "adjustment set**, this one asks it to be independent of the "
          "**instrument**, and neither implies the other, so having checked "
          "one is not having checked the other",
}

#: The same premise when the id cannot be split, so neither name is known.
#:
#: A token of its own, because a sentence no id names still has to be one a
#: reader can be handed — and every row of :data:`CLAIMS` is reached by a
#: token. The prefix names the row above; this names the row a rule falls
#: back to when the tail it was told to read does not read.
_UNSPLIT_INSTRUMENT = "outcome_error_mean_independent_of_instrument_unsplit"
_ERROR_AND_INSTRUMENT_UNSPLIT: language.Words = {
    "zh": "结局的测量误差与工具变量均值无关（{suffix}）",
    "en": "the outcome's measurement error is mean-independent of the "
          "instrument ({suffix})",
}


#: A monotonicity declared on the query, and the same one used as a bound.
#: The direction is the hole, and it is a vocabulary member's word rather
#: than a name the caller supplied — which is what the language is for.
_MONOTONE: language.Words = {"zh": "单调性：{direction}",
                             "en": "monotonicity: {direction}"}
#: The same, and what the route can do about it — see the pair of exact ids
#: above for why that belongs in the name rather than beside it.
_MONOTONE_ASSUMED: language.Words = {
    "zh": "单调性：{direction}——总体中没有结局与处理反向的单位；"
          "这条路线上没有可以反驳它的东西",
    "en": "monotonicity: {direction} — no unit in the population moves "
          "against the treatment, and nothing on this route could answer "
          "back",
}
_MONOTONE_REFUTABLE: language.Words = {
    "zh": "单调性：{direction}——总体中没有结局与处理反向的单位；它作为模型"
          "限制进入响应型多面体，**程序不可行就是数据在反驳它**",
    "en": "monotonicity: {direction} — no unit in the population moves "
          "against the treatment; it enters the response-type polytope as a "
          "restriction, so an infeasible program **is the data contradicting "
          "it**",
}
_MONOTONE_RESPONSE: language.Words = {
    "zh": "单调处理响应：{direction}——把无假设界的一侧收紧",
    "en": "monotone treatment response: {direction} — this tightens one side "
          "of the assumption-free bounds",
}


def _mean_independent_of_instrument(prefix: str, suffix: str
                                   ) -> tuple[str, _Slots]:
    """Which of the two above, and the names that go in it.

    Split at the first ``_on_``, the same literal every sibling id's prefix
    absorbs: the field it closes is the instrument the prefix just opened.
    The id is not uniquely parseable if either name contains that literal
    itself, which is a property of the id and not of this rule — so the
    fallback is the whole suffix rather than a confident mis-split.
    """
    instrument, sep, outcome = suffix.partition("_on_")
    if not sep:
        return _UNSPLIT_INSTRUMENT, {"suffix": suffix}
    return prefix, {"instrument": instrument, "outcome": outcome}


#: The propensity floor, and how many units it touched.
#:
#: Two of the caller's numbers rather than one of their names, which is what
#: the rule shape is for. Under the plain template this id's whole tail went
#: into the single hole and the reader was shown ``0.01_on_37_units`` —
#: this codebase's own words, in the middle of a sentence written for them.
_CLIPPED_PROPENSITY: language.Words = {
    "zh": "倾向得分被截断到下限 {floor}，有 {n} 个单位受此影响",
    "en": "the propensity score is clipped to a floor of {floor}, which "
          "affects {n} units",
}

#: The same premise when the id cannot be split, so neither number is known.
_UNSPLIT_CLIP = "propensity_clipped_unsplit"
_CLIPPED_PROPENSITY_UNSPLIT: language.Words = {
    "zh": "倾向得分被截断（{suffix}）",
    "en": "the propensity score is clipped ({suffix})",
}


def _clipped_propensity(prefix: str, suffix: str) -> tuple[str, _Slots]:
    """The floor and the count, split at the ``_on_`` the prefix opened."""
    floor, sep, trimmed = suffix.partition("_on_")
    if not sep:
        return _UNSPLIT_CLIP, {"suffix": suffix}
    return prefix, {"floor": floor, "n": trimmed}


def _direction(prefix: str, suffix: str) -> tuple[str, _Slots]:
    """Which way, for the four ids that end in a direction.

    ``_in_treatment`` is the id saying the assumption is monotone in the
    TREATMENT; what is left of the tail is the direction, and the direction
    is a closed vocabulary with words of its own.

    It goes into the hole as a WORD rather than as a lookup done here, which
    is also what keeps a tail naming no member from being an error:
    :func:`~themis.language.spelt` states a token whether or not the set
    carries it, and a reader handed one it does not carry is told so. Which
    is the answer this had before, from the machinery that already gives it.
    """
    return prefix, {"direction": language.spelt(
        Monotonicity.vocabulary, suffix.removesuffix("_in_treatment"))}


_PREFIX: tuple[tuple[str, _Row], ...] = (
    ("ci_via_pairs_cluster_bootstrap_on_",
     (_CI, True, {"zh": "置信区间由按 {suffix} 重采样整簇的 pairs cluster "
                        "bootstrap 求得",
                  "en": "the confidence interval comes from a pairs cluster "
                        "bootstrap resampling whole clusters by {suffix}"})),
    ("ci_not_cluster_robust_econml_dml_interval_ignores_",
     (_CI, True, {"zh": "置信区间不是簇稳健的：解析区间忽略了 {suffix} 的簇"
                        "内相关，可能偏窄",
                  "en": "the confidence interval is not cluster-robust: the "
                        "analytic interval ignores within-cluster "
                        "correlation on {suffix} and may be too narrow"})),
    ("cluster_robust_influence_variance_on_",
     (_CI, True, {"zh": "影响函数方差按 {suffix} 做了簇稳健修正",
                  "en": "the influence-function variance is cluster-robust "
                        "on {suffix}"})),
    ("propensity_clipped_to_floor_", (_FORM, True, _CLIPPED_PROPENSITY)),
    ("differential_misclassification_by_covariate_",
     (_ID, False, {"zh": "差异误分类：误分类率随协变量 {suffix} 而变，逐层用"
                         "本层矩阵求逆",
                   "en": "differential misclassification: the rates vary "
                         "with covariate {suffix}, and each stratum is "
                         "inverted with its own matrix"})),
    ("zminus_reweighting_from_unbiased_reference_",
     (_ID, False, {"zh": "Z⁻ 的重加权取自无偏参照样本（{suffix}）",
                   "en": "the Z⁻ reweighting comes from an unbiased "
                         "reference sample ({suffix})"})),
    ("zplus_weights_from_unbiased_reference_",
     (_ID, False, {"zh": "Z⁺ 的权重取自无偏参照样本（{suffix}）",
                   "en": "the Z⁺ weights come from an unbiased reference "
                         "sample ({suffix})"})),
    ("backdoor_adjustment_set_sufficient_",
     (_ID, False, {"zh": "后门调整集充分：{suffix} 阻断 X→Y 的所有后门路径",
                   "en": "the back-door adjustment set is sufficient: "
                         "{suffix} blocks every back-door path from X to Y"})),
    ("backdoor_adjustment_",
     (_ID, False, {"zh": "后门调整：{suffix}",
                   "en": "back-door adjustment: {suffix}"})),
    # A mismeasured continuous outcome. Which premises appear depends on the
    # design the error was priced against, and they are not one premise in
    # three widths: what has to be mean-independent of the error is the
    # DESIGN on the back-door route, the INSTRUMENT on the IV route, and on
    # the front-door route there is a third premise about a variable nobody
    # measured. Whichever ones appear, only the variance one is about the
    # interval; the rest decide whether the point survives at all.
    ("outcome_error_classical_non_differential_on_",
     (_ID, False,
      {"zh": "结局 {suffix} 的测量误差是经典可加且**非差异**的（与暴露、调整"
             "集、真实结局独立，均值 0）——正因如此点估计不受它影响；若误差随"
             "暴露臂或真实结局而变，点估计有偏",
       "en": "the measurement error on outcome {suffix} is classical, "
             "additive and **non-differential** (independent of exposure, of "
             "the adjustment set and of the true outcome, with mean 0) — "
             "which is exactly why the point estimate is unaffected by it; "
             "if the error varied with the exposure arm or with the true "
             "outcome, the point estimate would be biased"})),
    ("outcome_error_mean_independent_of_instrument_",
     (_ID, False, _ERROR_AND_INSTRUMENT)),
    # Unfalsifiable by construction, which is why `testable` is False here on
    # the same grounds as the classical premise and for a stronger reason:
    # the classical one is at least about variables in the data.
    ("outcome_error_independent_of_the_front_door_latent_confounder_on_",
     (_ID, False,
      {"zh": "结局 {suffix} 的测量误差与前门图假定的那个**未观测**混杂无关。"
             "那个混杂按定义就没被测到，所以这一条**没法用数据检验**——不是「"
             "暂时没检验」，是这批数据里根本没有能检验它的东西；它若不成立，"
             "误差动的是点估计本身，不只是区间宽度",
       "en": "the measurement error on outcome {suffix} is unrelated to the "
             "**unobserved** confounder the front-door graph assumes. That "
             "confounder is by definition unmeasured, so this claim **cannot "
             "be checked against the data** — not \"not checked yet\", but "
             "nothing in this dataset could check it; if it fails, the error "
             "moves the point estimate itself and not only the width of the "
             "interval"})),
    ("outcome_error_variance_known_and_fixed_on_",
     (_CI, True,
      {"zh": "结局 {suffix} 的测量误差方差 σ²_v 已知且固定：区间的精度代价按"
             "它折算，但不传播验证研究自身对 σ²_v 的不确定性——这一条给的是"
             "别人那个区间的标价，不是自己重抽出来的区间，所以没有哪一轮"
             "可以顺便重抽 σ²_v（设计侧那条会重抽的路见"
             "`design_error_variance_from_a_validation_study_on_`）",
       "en": "the measurement-error variance σ²_v on outcome {suffix} is "
             "known and fixed: the interval's precision cost is computed "
             "from it, but the validation study's own uncertainty about σ²_v "
             "is not propagated — this row prices somebody else's interval "
             "rather than resampling one of its own, so there is no round in "
             "which σ²_v could be redrawn (the design side's route that does "
             "is `design_error_variance_from_a_validation_study_on_`)"})),
    # The tail of these four is a direction rather than a name, which is
    # what :func:`_direction` reads — see :data:`_RULES` below.
    ("monotonicity_assumed_", (_ID, False, _MONOTONE_ASSUMED)),
    ("monotonicity_refutable_", (_ID, True, _MONOTONE_REFUTABLE)),
    ("monotonicity_", (_ID, False, _MONOTONE)),
    ("mtr_", (_ID, False, _MONOTONE_RESPONSE)),
    # A mismeasured continuous column of the DESIGN — the exposure, a
    # confounder, or several of each. The mirror of the outcome_error family
    # above, and the mirror is not symmetric: on the outcome side σ²_v only
    # prices the interval, while here σ²_u enters the correction itself
    # (β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive), so a wrong variance moves the
    # point. Which is why the variance row below is an identification premise
    # here and a confidence one there — the same sentence about the same
    # quantity, sitting in a different layer because of where it is used.
    ("design_error_classical_additive_on_",
     (_ID, False,
      {"zh": "连续设计列 {suffix} 上的测量误差是经典加性的：W=真值+U，U "
             "均值 0，且与其余设计列、与给定真值的 Y 都独立",
       "en": "the measurement error on the continuous design column "
             "{suffix} is classical and additive: W=true+U, with U of mean "
             "0 and independent both of the other design columns and of Y "
             "given the true values"})),
    ("design_error_variance_known_and_fixed_on_",
     (_ID, True,
      {"zh": "设计列 {suffix} 的误差方差 σ²_u 已知且固定（来自验证研究"
             "或重复测量）——它进入校正本身，所以它错了错的是点估计，"
             "不只是区间宽度",
       "en": "the error variance σ²_u on design column {suffix} is known "
             "and fixed (from a validation study or repeated measures) — it "
             "enters the correction itself, so if it is wrong the point "
             "estimate is wrong, not only the width of the interval"})),
    # The same quantity declared the other way — with the size of the study
    # that measured it — and so a different premise, because what is taken on
    # trust changes. A second row rather than a clause on the one above,
    # because a reader who is told both would have to work out which half of
    # the sentence this run made; and an identification premise still,
    # despite being about the interval, for the reason the comment above
    # gives: on this side σ²_u enters the correction, so it is still the
    # point estimate that a wrong one moves.
    ("design_error_variance_from_a_validation_study_on_",
     (_ID, True,
      {"zh": "设计列 {suffix} 的误差方差 σ²_u 由一个验证研究估出，自由度已"
             "声明——bootstrap 每一轮按 σ̂²·df/χ²_df 重抽它，所以区间同时"
             "携带主样本与那个验证研究两份不确定性。被信的不再是「σ²_u "
             "是对的」，而是「那个自由度是对的、重复测量的误差是正态的」；"
             "σ²_u 仍进入校正本身，所以它错了点估计仍然错",
       "en": "the error variance σ²_u on design column {suffix} was "
             "estimated by a validation study whose degrees of freedom are "
             "declared — each bootstrap round redraws it as σ̂²·df/χ²_df, so "
             "the interval carries that study's uncertainty as well as the "
             "main sample's. What is trusted is no longer that σ²_u is right "
             "but that the declared degrees of freedom are and that the "
             "replicate errors are normal; σ²_u still enters the correction "
             "itself, so if it is wrong the point estimate is still wrong"})),
    # The classical premise's other half withdrawn. The pair above says the
    # error is independent of everything; this says it is independent of
    # everything BUT the outcome, and carries the size of that dependence as
    # its own row — two facts arriving where one used to, and separately
    # refutable. Both are identification premises: get either wrong and the
    # correction lands somewhere else, in either direction.
    ("design_error_tracks_the_outcome_on_",
     (_ID, False,
      {"zh": "{suffix} 上的测量误差**不是**非差异的：它含有一份随结局走的分量，"
             "W=真值+U，U=δ·（结局对调整集的残差）+f，其中 f 与真值、与结局都"
             "独立。这条不可检验——δ 和真实斜率进入观测协方差的方式完全一样，"
             "样本分不出哪一份是效应、哪一份是误差，所以 δ 只能从外部来",
       "en": "the measurement error on {suffix} is NOT non-differential: it "
             "carries a component that tracks the outcome, W=true+U with "
             "U=δ·(the outcome's residual on the adjustment set)+f, where f "
             "is independent of both the truth and the outcome. Untestable — "
             "a δ and a true slope enter the observed covariance in exactly "
             "the same way, so the sample cannot say which part is effect "
             "and which is error, and δ has to come from outside it"})),
    ("differential_coefficient_known_and_fixed_on_",
     (_ID, True,
      {"zh": "{suffix} 的差异系数 δ 已知且固定（来自同时握有真值、观测值、结局"
             "的验证子研究）。它进入校正本身——观测协方差要先减掉 δ·Var(Y|Z) "
             "再去衰减——所以它错了错的是点估计，不只是区间宽度。这份数据能"
             "单向反驳它：δ 太大时误差的经典部分方差为负、或真实暴露没有方差"
             "剩下",
       "en": "the differential coefficient δ on {suffix} is known and fixed "
             "(from a validation substudy holding the truth, the recorded "
             "value and the outcome together). It enters the correction "
             "itself — the observed covariance has δ·Var(Y|Z) removed before "
             "anything is de-attenuated — so if it is wrong the point "
             "estimate is wrong, not only the width of the interval. These "
             "data can refute it one-sidedly: too large a δ leaves the "
             "error's classical part a negative variance, or the true "
             "exposure none at all"})),
    # The OTHER structure the same two facts can have, and the pair splits
    # across two layers where the pair above sits in one. Under Berkson
    # error the truth scatters around the recorded nominal value, so the
    # uncorrected slope is already the causal one: the STRUCTURE is an
    # identification premise — get it wrong and a correct number is
    # de-attenuated into a wrong one — while the VARIANCE never touches the
    # point at all and buys only the width, which is the confidence layer.
    # A reader who doubts the first should distrust the answer; a reader who
    # doubts the second should distrust only the price beside it.
    ("berkson_error_on_",
     (_ID, False,
      {"zh": "{suffix} 上的测量误差是 Berkson 型的：记录下来的是名义值 W，"
             "真值围绕它散布（X*=W+U，U 与 W 独立、均值 0）。于是 "
             "E[X*|W,Z]=W；再配上旁边那条线性性，普通的后门斜率本身就是"
             "因果斜率——不做校正才是对的。这条不可检验：同一列数据在经典"
             "误差下和在 Berkson 误差下长得一模一样，哪一种成立是关于"
             "「这个数是怎么测出来的」的事实",
       "en": "the measurement error on {suffix} is of the BERKSON kind: "
             "what was recorded is the nominal value W and the truth "
             "scatters around it (X*=W+U, with U independent of W and of "
             "mean 0). E[X*|W,Z]=W then holds exactly, and together with "
             "the linearity stated beside it the ordinary back-door slope "
             "already IS the causal slope, so applying no correction is "
             "the right thing to do. Untestable: a column under classical "
             "error and the same column under Berkson error look "
             "identical, and which one holds is a fact about how the "
             "measurement was made"})),
    ("berkson_scatter_variance_known_and_fixed_on_",
     (_CI, True,
      {"zh": "{suffix} 的散布方差 σ²_u=Var(X*−W) 已知且固定（来自验证研究"
             "或名义值是怎么分配的）。它不进入点估计，只进入代价：真值的"
             "散布按 β²σ²_u 落进残差，把这条设计上的每个区间按固定倍数"
             "撑宽。这份数据能反驳它——β²σ²_u 装不进未被解释的变异时就装"
             "不进",
       "en": "the scatter variance σ²_u = Var(X* − W) on {suffix} is known "
             "and fixed (from a validation study, or from how the nominal "
             "value was assigned). It does not enter the point estimate at "
             "all, only the price: the truth's scatter falls into the "
             "residual as β²σ²_u and widens every interval on this design "
             "by a fixed factor. These data can refute it — β²σ²_u either "
             "fits under the unexplained variation or it does not"})),
)


#: The prefixes whose tail is not one name, and how it is read.
#:
#: Keyed on the prefix rather than sitting in the row, so that a row is one
#: shape whether or not a rule reads its tail: what the sentence IS belongs
#: to the row, and how the id is read belongs here. It used to sit in the
#: row, in the slot the words go in — one slot holding two things, and the
#: union type that allowed it is what kept the two tables from being one
#: shape.
_RULES: dict[str, _Fills] = {
    "propensity_clipped_to_floor_": _clipped_propensity,
    "outcome_error_mean_independent_of_instrument_":
        _mean_independent_of_instrument,
    "monotonicity_assumed_": _direction,
    "monotonicity_refutable_": _direction,
    "monotonicity_": _direction,
    "mtr_": _direction,
}


#: The name this table's sentences answer to on an envelope.
CLAIM = "assumption_claim"

#: Every sentence this table can hand a reader, by the token it travels as.
#:
#: Derived rather than authored, so that each sentence stays beside the layer
#: and the testability it is a row with. What makes this a VOCABULARY and not
#: a third lookup is the registration below: a statement carries a name and a
#: token, and every surface that shows one — this package's renderer, the
#: browser, a model asked to write the answer up — meets the sentence through
#: the table registered under that name. While there was no such name, the
#: only way to get one of these to a reader was to render it here, which is
#: the kernel deciding who is reading.
#:
#: An exact row is keyed by its id and a prefix row by its prefix, because
#: the prefix is what that row IS — the tail is the occasion's fact and goes
#: in a hole. An id no row matches is its own token and is carried by none of
#: these, which is what the reader's side already knows how to say.
CLAIMS: dict[str, language.Words] = {
    **{i: words for i, (_layer, _testable, words) in _EXACT.items()},
    **{p: words for p, (_layer, _testable, words) in _PREFIX},
    _UNSPLIT_INSTRUMENT: _ERROR_AND_INSTRUMENT_UNSPLIT,
    _UNSPLIT_CLIP: _CLIPPED_PROPENSITY_UNSPLIT,
}
language.declare(CLAIM, CLAIMS)


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
    "monotonicity_assumed_x_never_prevents_y": Provenance.CALLER_ASSERTED,
    "monotonicity_refutable_x_never_prevents_y": Provenance.CALLER_ASSERTED,
    # A counterfactual cell: without it the cell is its bounds. When no
    # do-risk was obtainable this same assertion does ALL the work with
    # nothing to check it against, which the producer says on this line's
    # own claim rather than as an entry beside it.
    "monotonicity_assumed_non_decreasing_in_treatment":
        Provenance.CALLER_ASSERTED,
    "monotonicity_assumed_non_increasing_in_treatment":
        Provenance.CALLER_ASSERTED,
    "monotonicity_refutable_non_decreasing_in_treatment":
        Provenance.CALLER_ASSERTED,
    "monotonicity_refutable_non_increasing_in_treatment":
        Provenance.CALLER_ASSERTED,
    # A CHOICE and not an assertion, which is a different member: the
    # proximal matrix needs a k x k channel and cannot be run without SOME
    # grouping of a finer proxy, so withdrawing this one leaves no answer
    # rather than a wider one — the test CALLER_ASSERTED's own text states.
    # What the caller can do is group differently, and the answer is
    # recomputed from that.
    "latent_cardinality_k_correct_and_the_declared_coarsening_folds_each_proxy_to_k_levels":
        Provenance.CALLER_CHOSE,
    # The sieve's two halves, and the pair that makes the distinction between
    # these two members legible: WHERE the bridge is assumed to live is a
    # choice the method cannot make and the answer is recomputed from, while
    # HOW MUCH penalty was added is the same kind of choice except that on
    # one of these two lines nobody made it. Both change the number, and a
    # reader deciding whether to argue needs to know which door to knock on.
    "the_outcome_bridge_lies_in_the_span_of_the_declared_sieve":
        Provenance.CALLER_CHOSE,
    "the_treatment_bridge_lies_in_the_span_of_the_declared_sieve":
        Provenance.CALLER_CHOSE,
    "the_bridge_varies_with_the_treatment_as_the_declared_basis_does":
        Provenance.CALLER_CHOSE,
    # The union model is the caller's too, and by the same act: it is what
    # the two spans they declared amount to together, and the estimator did
    # not weaken either of them into it.
    "at_least_one_of_the_two_bridges_lies_in_its_declared_span":
        Provenance.CALLER_CHOSE,
    "regularisation_lambda_chosen_by_the_caller": Provenance.CALLER_CHOSE,
    "regularisation_lambda_defaulted_by_the_estimator": Provenance.DEFAULT,
    "treatment_bridge_regularisation_lambda_chosen_by_the_caller":
        Provenance.CALLER_CHOSE,
    "treatment_bridge_regularisation_lambda_defaulted_by_the_estimator":
        Provenance.DEFAULT,
}

_ANSWERABLE_PREFIX: tuple[tuple[str, Provenance], ...] = (
    # Monotone treatment response, declared on the query and used to tighten
    # one side of the assumption-free bounds.
    ("mtr_", Provenance.CALLER_ASSERTED),
    # An outcome measurement-error assessment runs only because the caller
    # attached the model, and every premise it declares is about the caller's
    # own measurement process. Drop the model and the point estimate stands —
    # what is lost is the accounting of what the noise costs the interval.
    # One prefix rather than one per id, because that argument is about the
    # channel and not about any particular premise on it: which premises the
    # block declares depends on the design, and a list per id would have gone
    # stale the moment a second design was added — as it did.
    ("outcome_error_", Provenance.CALLER_ASSERTED),
)


def answerable(assumption_id: str) -> Provenance:
    """Who can overrule this assumption, for either channel that carries one.

    The structured identification specs ask this too, keyed on the same id,
    so a spec and the flat declaration it restates cannot disagree about
    what the reader may do with the line.

    A functional-form id is REFUSED rather than answered. The same
    ``logit_outcome_regression`` is TMLE's definition — it takes no ``model=``
    and the caller has no lever — and back-door's resolved default one family
    over, and the caller's own assertion the moment they pass it. No value
    keyed on that id is true of all three, so the estimate carries the ones
    that are.
    """
    text = str(assumption_id)
    hit = _ANSWERABLE_EXACT.get(text)
    if hit is not None:
        return hit
    for prefix, provenance in _ANSWERABLE_PREFIX:
        if text.startswith(prefix):
            return provenance
    if layer_of(text) == _FORM:
        # A builtin, and deliberately: nothing catches this and no reader is
        # ever handed it. It fires when kernel code asks this table a
        # question it does not answer, which is a wiring mistake — the same
        # kind of thing as an index out of range, and not a refusal.
        raise ValueError(
            f"themis: {text!r} is a functional-form assumption, and who "
            f"settled a form is a fact about the RUN rather than about the "
            f"id — build the mechanism block from the estimate's own "
            f"``form_provenance`` and ``shape_provenance``"
        )
    return Provenance.INHERENT


def _row(text: str) -> tuple[Layer, bool, str, _Slots]:
    """The row this id falls on: its layer, whether the data can answer it,
    which sentence a reader is handed, and what this occasion puts in that
    sentence's holes.

    Split out so the layer can be asked for on its own, which is what
    :func:`layer_of` wants. Nothing is worded either way now — a token and
    some facts is what both callers get — so the split is a convenience
    rather than the guard against a stray translation it used to be.

    An id no row matches keeps ITSELF as the token. Nothing here words it,
    and a token the vocabulary does not carry is what the reader's side
    already knows how to say, so an unclassified declaration reaches the
    page as its own name — the disclosure rule this module opens with, said
    by the machinery every other unknown token is said by.
    """
    entry = _EXACT.get(text)
    if entry is not None:
        layer, testable, _words = entry
        return layer, testable, text, {}
    for prefix, (layer, testable, _words) in _PREFIX:
        if text.startswith(prefix):
            rule = _RULES.get(prefix)
            if rule is None:
                return layer, testable, prefix, {"suffix": text[len(prefix):]}
            spelling, slots = rule(prefix, text[len(prefix):])
            return layer, testable, spelling, slots
    return _ID, False, text, {}


def layer_of(assumption_id: str) -> Layer:
    """Which part of the answer this assumption holds up.

    The layer alone, for the callers that select on it. An unrecognised id is
    an identification assumption here for the same reason it is one in
    :func:`classify_assumption`: a disclosure surface must not drop something
    because nobody classified it, and identification is the grade that gets
    it looked at.
    """
    return _row(str(assumption_id))[0]


def classify_assumption(assumption: str) -> dict:
    """Classify one flat assumption declaration.

    Returns ``{"id", "claim", "layer", "testable"}`` — what this table knows —
    plus ``provenance`` for every layer but one. The severity is not among
    them: it is the layer's grade, and it reaches the entry when the caller
    stamps it, from the one place that says which grade each layer falls into.

    ``provenance`` is ABSENT on a functional-form entry rather than filled
    with a plausible constant, because who settled a form is a fact about the
    run and this table sees only the id. Absent
    rather than ``None``: a consumer that needs it and forgets gets a
    ``KeyError`` naming the id, and a consumer that only wants the layer never
    asks. The channel holding the run's answer supplies it —
    :func:`~themis.output.result_orchestrator.build_mechanism_audit`.

    **No language arrives here, and that is the whole of what changed.** The
    claim is a STATEMENT — which row of :data:`CLAIMS`, and what this
    occasion puts in its holes — so all four fields are facts about the
    assumption, the same for every reader, and the sentence is met where the
    reader is. A ``lang`` used to arrive for this one field of the four.

    A LIST of statements rather than one, because the field takes them from
    channels this table is not the only one of: the line for an unverified
    edge is made of however many statements that gap is made of. One is the
    common case, not the contract.

    An unrecognised declaration is surfaced as an identification assumption —
    invalidating, therefore — under its own id as the token: a disclosure
    surface must never drop something because nobody classified it, and a
    token this vocabulary does not carry is what the reader's side already
    knows how to say.
    """
    text = str(assumption)
    layer, testable, spelling, slots = _row(text)
    entry: dict = {"id": text,
                   "claim": [language.spelt(CLAIM, spelling, **slots)],
                   "layer": layer, "testable": testable}
    if layer != _FORM:
        entry["provenance"] = answerable(text)
    return entry


def is_classified(assumption: str) -> bool:
    """Whether the glossary recognises this declaration (exact or prefix).

    Used by the parity test that keeps the table in step with what the
    estimators emit; an unrecognised ID still reaches the ledger, so this is a
    quality check, not a correctness gate.
    """
    text = str(assumption)
    return text in _EXACT or any(text.startswith(p) for p, _ in _PREFIX)
