"""What a query is short of, and what the reader is told about it.

``themis.refusals`` answers "why is there no number". This answers the
other half — "what would give you one" — and it is the same shape, which
is the finding this module was built on. A refusal carries a species, a
kind read off the species, and the occasion's facts; ``MissingItem``
carried a :class:`~themis.types.GapKind` and a SENTENCE, rendered at the
site in one language out of that kind and this occasion's values.

Measured before it was built, at the kernel exit, over a full suite run:
``missing_information[].reason`` and ``investigation_requests[].items[]
.reason`` carry the same set of strings (the second is a projection of the
first, one line in ``investigation_pusher``), and between them about 15,700
sentences. They fall into roughly thirty shapes, and the shapes do not line
up with the kinds: ``unidentifiable_no_admissible_set`` covers ten distinct
findings, ``missing_assumption`` eleven, ``missing_structural_input`` nine.

So the kind was doing two jobs. It is the coarse one — which channel
repairs this — and there was no name for the fine one, which is why the
fine one lived in prose. :class:`Need` is that name. The kind is read off
it, exactly as a refusal's is read off its species, so the two can no
longer disagree.

The sentences live beside the species, in every language this build
writes, for the reason :data:`themis.refusals.SAYS` gives: one author sees
both languages of a sentence at once, and no site can drift from it
because no site writes one.
"""
from __future__ import annotations

from collections.abc import Mapping

from enum import unique

from . import language
from .types import (
    EnvelopeName,
    GapKind,
    GapRefKind,
    GapRoute,
    GapSeverity,
    InvestigationItem,
    MissingItem,
    MissingKind,
    Observable,
    Priority,
)


@unique
class QueryPart(language.Word, vocabulary="query_part"):
    """Which part of a program named an atom the graph does not have.

    Six sites said this in six hand-written sentences that differed only
    here, and the wording had already drifted: five said "实例化变量集 V"
    and one said "变量集 V". A word is what they were spelling out.
    """

    QUERY = ("query", {"zh": "查询", "en": "the query"})
    CAUSATION_QUERY = ("causation_query",
                       {"zh": "causation 查询", "en": "the causation query"})
    SCM_COUNTERFACTUAL_QUERY = (
        "scm_counterfactual_query",
        {"zh": "scm_counterfactual 查询", "en": "the scm_counterfactual query"})
    COUNTERFACTUAL_EVENT = (
        "counterfactual_event",
        {"zh": "反事实事件", "en": "the counterfactual event"})
    PROXIMAL_ROLE = ("proximal_role",
                     {"zh": "proximal 查询的角色", "en": "a proximal role"})
    LONGITUDINAL_SPEC = ("longitudinal_spec",
                         {"zh": "纵向 spec", "en": "the longitudinal spec"})


@unique
class Need(EnvelopeName):
    """One thing the kernel needed and did not have, by name.

    A member is ``(token, kind, what it means to whoever adds the next
    one)``. The kind is the channel that repairs it and is declared here
    rather than at the site, so a site cannot file a need under a kind
    that contradicts it — the arrangement :class:`themis.refusals.Refusal`
    already uses for the same reason.

    ``says`` is the maintainer's. The reader's sentence is in
    :data:`SAYS`, and the two stay separate because they answer different
    people.
    """

    gap: GapKind
    says: str

    def __new__(cls, value: str, gap: GapKind, says: str) -> "Need":
        member = str.__new__(cls, value)
        member._value_ = value
        member.gap = gap
        member.says = says
        return member

    # --- the structure the query names and the graph does not have --------

    ATOM_NOT_IN_GRAPH = (
        "atom_not_in_graph", GapKind.MISSING_STRUCTURAL_INPUT,
        "a query named a variable that is not in the instantiated set V")
    GIVEN_VIOLATES_BACKDOOR = (
        "given_violates_backdoor", GapKind.MISSING_STRUCTURAL_INPUT,
        "identify.given holds X, Y, or a descendant of X")
    MEDIATOR_OFF_THE_DIRECTED_PATHS = (
        "mediator_off_the_directed_paths", GapKind.MISSING_STRUCTURAL_INPUT,
        "the declared mediator lies on no directed path from X to Y")
    MEDIATOR_SET_OFF_THE_DIRECTED_PATHS = (
        "mediator_set_off_the_directed_paths",
        GapKind.MISSING_STRUCTURAL_INPUT,
        "one of the declared mediators lies off the directed paths, or the "
        "set is empty or holds X or Y")
    PATH_COEFFICIENT_UNDECLARED = (
        "path_coefficient_undeclared", GapKind.MISSING_STRUCTURAL_INPUT,
        "a linear SCM counterfactual needs this edge's path coefficient")
    CONDITIONING_EVENT_HAS_PROBABILITY_ZERO = (
        "conditioning_event_has_probability_zero",
        GapKind.MISSING_STRUCTURAL_INPUT,
        "the conditioning conjunction has probability zero in every model "
        "the graph admits, so the conditional does not exist")
    JOINT_WITH_MEDIATION_OR_TRANSPORT = (
        "joint_with_mediation_or_transport",
        GapKind.MISSING_STRUCTURAL_INPUT,
        "a joint multi-treatment intervention combined with mediation or "
        "transport, which decompose a single-treatment effect")
    DUPLICATE_TREATMENT_ATOM = (
        "duplicate_treatment_atom", GapKind.MISSING_STRUCTURAL_INPUT,
        "the joint treatment vector repeats an atom")

    # --- no estimand exists over the observed distribution ----------------

    NO_C_FACTOR_WITNESS = (
        "no_c_factor_witness", GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "the complete ID/IDC algorithm found no c-factor witness, and no "
        "instrument route is available either")
    NO_BACKDOOR_OR_FRONTDOOR = (
        "no_backdoor_or_frontdoor", GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "no valid back-door or front-door adjustment exists")
    COUNTERFACTUAL_NOT_IDENTIFIABLE = (
        "counterfactual_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "ID*/IDC* found a w-graph or subscript-conflict witness")
    JOINT_EFFECT_NOT_IDENTIFIABLE = (
        "joint_effect_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "no joint back-door set blocks every non-causal path from the "
        "treatment vector, and set-valued ID did not point-identify it")
    SEQUENTIAL_EXCHANGEABILITY_FAILS = (
        "sequential_exchangeability_fails",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "a back-door path from one time point's treatment to the outcome is "
        "open given the measured history")
    CONDITIONAL_ADMG_NOT_IDENTIFIABLE = (
        "conditional_admg_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "IDC hit a hedge on the conditional estimand; the marginal is not "
        "substituted for it")
    ADMG_EFFECT_NOT_IDENTIFIABLE = (
        "admg_effect_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "ADMG back-door, front-door and Tian/Shpitser ID all fail")
    ADMG_EFFECT_REACHABLE_ONLY_BY_INSTRUMENT = (
        "admg_effect_reachable_only_by_instrument",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "the same as above, and an instrument route does reach it — which "
        "is a different thing to be told, because that route is one the "
        "caller can take and it carries assumptions")
    PROXIMAL_NOT_IDENTIFIABLE = (
        "proximal_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "a Miao model (f) criterion failed")
    TRANSPORT_NOT_IDENTIFIABLE = (
        "transport_not_identifiable",
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        "no S-admissible adjustment set transports the effect")

    # --- an assumption or an experiment, not more of the same data --------

    INTERVENTIONAL_RISK_NOT_IDENTIFIABLE = (
        "interventional_risk_not_identifiable", GapKind.MISSING_ASSUMPTION,
        "P(Y=1|do(X)) is not identifiable on this graph, so no amount of "
        "observational data yields it")
    INTERVENTIONAL_RISK_NEEDS_DISTRIBUTIONS = (
        "interventional_risk_needs_distributions", GapKind.MISSING_ASSUMPTION,
        "P(Y=1|do(X)) is identifiable and the distributions it is computed "
        "from are the gap; an experimental risk skips them")
    INTERVENTIONAL_RISK_UNAVAILABLE_FOR_CELL = (
        "interventional_risk_unavailable_for_cell",
        GapKind.MISSING_ASSUMPTION,
        "the counterfactual cell rests on one interventional risk and that "
        "risk is not identifiable from the data given")
    INTERVENTIONAL_RISKS_CONTRADICT_THE_JOINT = (
        "interventional_risks_contradict_the_joint",
        GapKind.MISSING_ASSUMPTION,
        "the supplied interventional risks and the observed joint cannot "
        "come from one SCM, so PN/PS/PNS are undefined")
    IV_STRATUM_WEIGHTS_NOT_NORMALIZED = (
        "iv_stratum_weights_not_normalized", GapKind.MISSING_ASSUMPTION,
        "the instrument's stratum probabilities do not sum to one, so the "
        "reported compliance share is weighted by a non-distribution")
    IV_FIRST_STAGE_DEGENERATE = (
        "iv_first_stage_degenerate", GapKind.MISSING_ASSUMPTION,
        "the instrument does not move the treatment, so the Wald ratio has "
        "no complier subpopulation to average over")
    IV_MONOTONICITY_UNDECLARED = (
        "iv_monotonicity_undeclared", GapKind.MISSING_ASSUMPTION,
        "valid instruments reach the effect and the kernel will not choose "
        "between Wald, 2SLS and bounds on the caller's behalf")

    # --- the probability itself is not in theta ---------------------------

    THETA_ENTRY_MISSING = (
        "theta_entry_missing", GapKind.MISSING_DISTRIBUTION,
        "the formula evaluator asked theta for a conditional it does not "
        "hold, and no derivation reaches it either")
    GRAPH_CONTRADICTS_SUPPLIED_MARGINAL = (
        "graph_contradicts_supplied_marginal",
        GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH,
        "theta does hold a marginal that would stand in, and the declared "
        "graph forbids the substitution — so this is not the same ask as "
        "the one above, and 'supply more theta' is advice for it")
    QUERY_BOUND_ATOM_UNRESOLVED = (
        "query_bound_atom_unresolved", GapKind.MISSING_DISTRIBUTION,
        "the formula holds a query-bound atom with no concrete value, which "
        "only an externally supplied substitution settles")
    COUNTERFACTUAL_BOUND_NEEDS_ENTRY = (
        "counterfactual_bound_needs_entry", GapKind.MISSING_DISTRIBUTION,
        "the response-type polytope the counterfactual bound is taken over "
        "is built from observational cells, and this cell is not in theta")
    IV_WALD_LATE_NEEDS_ENTRY = (
        "iv_wald_late_needs_entry", GapKind.MISSING_DISTRIBUTION,
        "the marginal Wald LATE needs this conditional and theta does not "
        "hold it")
    IV_WALD_LATE_NEEDS_ENTRY_IN_STRATUM = (
        "iv_wald_late_needs_entry_in_stratum", GapKind.MISSING_DISTRIBUTION,
        "the same, for a stratified instrument — a separate species and not "
        "a slot on the one above, because the connective that would join the "
        "stratum to that sentence is itself a word")

    # --- one unit's reading, which no population substitutes for ----------

    UNIT_OBSERVATION_MISSING = (
        "unit_observation_missing", GapKind.MISSING_UNIT_OBSERVATION,
        "abduction recovers this unit's exogenous term from its own "
        "measured values, so a distribution over units does not stand in")

    # --- the variable is declared and not yet defined ---------------------

    FRAMING_FIELDS_UNFILLED = (
        "framing_fields_unfilled", GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
        "a declared predicate is missing operationalisation fields, so what "
        "a do(.) on it means is not settled")


BY_NAME: dict[str, Need] = {str(need): need for need in Need}
"""The need going by that envelope name, or nothing.

``Need(name)`` is the same lookup and is the one to use where an unknown
name is an error. This is for the places where it is a question, for the
reason :data:`themis.refusals.BY_NAME` gives.
"""


SAYS: dict[str, language.Words] = {
    "atom_not_in_graph": {
        "zh": "{part}指到了 `{atom}`，而它不在实例化变量集 V 中",
        "en": "{part} names `{atom}`, which is not in the instantiated "
              "variable set V",
    },
    "given_violates_backdoor": {
        "zh": "identify.given 违反了后门前置条件（含 X、Y，或 X 的某个"
              "后代）：{atoms}",
        "en": "identify.given breaks the back-door precondition (it holds X, "
              "Y, or a descendant of X): {atoms}",
    },
    "mediator_off_the_directed_paths": {
        "zh": "这个中介不落在任何一条有向路径 X → … → M → … → Y 上；"
              "请检查中介的声明或图上的边",
        "en": "this mediator lies on no directed path X → … → M → … → Y; "
              "check the mediator declaration or the edges in the graph",
    },
    "mediator_set_off_the_directed_paths": {
        "zh": "至少有一个中介不落在有向路径 X → … → M → … → Y 上（或者这个"
              "集合是空的 / 含 X 或 Y）；请检查中介的声明或图上的边",
        "en": "at least one mediator lies off the directed paths "
              "X → … → M → … → Y (or the set is empty, or holds X or Y); "
              "check the mediator declaration or the edges in the graph",
    },
    "path_coefficient_undeclared": {
        "zh": "线性 SCM 反事实需要这条边上的通径系数：{parent} -> {child}",
        "en": "a linear SCM counterfactual needs this edge's path "
              "coefficient: {parent} -> {child}",
    },
    "conditioning_event_has_probability_zero": {
        "zh": "P(γ|δ) 无定义：在每一个与该图相容的模型里，条件合取 δ 的概率"
              "都是 0（有效性违反，或两个世界互相矛盾），所以这个条件概率"
              "根本不存在。",
        "en": "P(γ|δ) is undefined: in every model the graph admits, the "
              "conditioning conjunction δ has probability 0 (a validity "
              "violation, or two worlds that contradict each other), so this "
              "conditional does not exist.",
    },
    "joint_with_mediation_or_transport": {
        "zh": "v1 里，联合多处理干预不能和中介 / 迁移组合使用；后两者分解的是"
              "单处理效应，而联合分解是另一种操作",
        "en": "in v1 a joint multi-treatment intervention cannot be combined "
              "with mediation or transport; those two decompose a "
              "single-treatment effect, and the joint decomposition is a "
              "different operation",
    },
    "duplicate_treatment_atom": {
        "zh": "联合处理向量里有重复的原子",
        "en": "the joint treatment vector repeats an atom",
    },
    "no_c_factor_witness": {
        "zh": "完备的 ID/IDC 算法判定不可识别（找不到 c-factor 见证），也没有"
              "可用的工具变量升级路线。",
        "en": "the complete ID/IDC algorithm found it unidentifiable (no "
              "c-factor witness), and no instrument route is available "
              "either.",
    },
    "no_backdoor_or_frontdoor": {
        "zh": "不存在有效的后门或前门调整",
        "en": "no valid back-door or front-door adjustment exists",
    },
    "counterfactual_not_identifiable": {
        "zh": "P(γ|δ) 经 ID*/IDC* 算法判定不可识别——存在 w-图 / 下标冲突见证"
              "（例如 PNS 的 P(y_x, y'_{{x'}}) 配一条 X→Y 直接边，或一条后门"
              "挡住了每一次条件移动）。不存在任何观测估计量。",
        "en": "ID*/IDC* found P(γ|δ) unidentifiable — there is a w-graph or "
              "subscript-conflict witness (PNS's P(y_x, y'_{{x'}}) beside a "
              "direct X→Y edge, say, or a back-door that blocks every "
              "conditioning move). No observational estimand exists.",
    },
    "joint_effect_not_identifiable": {
        "zh": "没有哪个有效的联合（处理集）后门调整集能挡住从处理向量到目标的"
              "所有真非因果路径，集合值 ID 也没能把联合效应点识别出来",
        "en": "no valid joint (treatment-set) back-door adjustment blocks "
              "every genuinely non-causal path from the treatment vector to "
              "the target, and set-valued ID did not point-identify the "
              "joint effect either",
    },
    "sequential_exchangeability_fails": {
        "zh": "处理 {treatment}（时刻 {time}）到 {outcome} 有一条后门路径是"
              "开的，测得的历史挡不住它——序贯可交换性不成立，g-formula 会"
              "给出一个有偏的数。请测量该混杂变量，或修改因果图。",
        "en": "a back-door path from treatment {treatment} (time {time}) to "
              "{outcome} is open and the measured history does not block "
              "it — sequential exchangeability fails and the g-formula would "
              "return a biased number. Measure that confounder, or change "
              "the graph.",
    },
    "conditional_admg_not_identifiable": {
        "zh": "条件 general-ID（IDC）效应：条件量 P(Y|do(X), given) 在这个 "
              "ADMG 上不可识别（Rule-2 交换加 ID 递归在条件估计量上撞到了 "
              "hedge）。也不会拿边缘量顶替它。",
        "en": "conditional general-ID (IDC) effect: P(Y|do(X), given) is not "
              "identifiable on this ADMG (Rule-2 exchange plus the ID "
              "recursion hit a hedge on the conditional estimand). The "
              "marginal is not substituted for it either.",
    },
    "admg_effect_not_identifiable": {
        "zh": "这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都"
              "到不了。若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7。",
        "en": "this ADMG effect query is out of reach of ADMG back-door, "
              "front-door and Tian / Shpitser ID alike. For the Line-7 case "
              "see PHASE_2_LATENT_CHARTER.md §7.",
    },
    "admg_effect_reachable_only_by_instrument": {
        "zh": "这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都"
              "到不了。工具变量升级路线确实到得了它，但那条路线是带假设的。"
              "若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7。",
        "en": "this ADMG effect query is out of reach of ADMG back-door, "
              "front-door and Tian / Shpitser ID alike. The instrument "
              "upgrade route does reach it, but that route carries "
              "assumptions. For the Line-7 case see "
              "PHASE_2_LATENT_CHARTER.md §7.",
    },
    "proximal_not_identifiable": {
        "zh": "P(Y|do(X)) 不可经近端识别（{criterion}）：{detail}",
        "en": "P(Y|do(X)) is not proximally identifiable ({criterion}): "
              "{detail}",
    },
    "transport_not_identifiable": {
        "zh": "找不到 S-可容许的调整集；在所声明的选择图下，源人群的效应无法"
              "迁移到目标人群：{detail}",
        "en": "no S-admissible adjustment set was found; under the declared "
              "selection diagram the source effect does not transport to the "
              "target population: {detail}",
    },
    "interventional_risk_not_identifiable": {
        "zh": "P(Y=1|do(X)) 在这张图上不可识别，再多观测数据也换不出它。请提供"
              "来自随机实验的 experimental_risk_treated / "
              "experimental_risk_control，或者修改因果图。{note}",
        "en": "P(Y=1|do(X)) is not identifiable on this graph, and no amount "
              "of observational data buys it. Supply "
              "experimental_risk_treated / experimental_risk_control from a "
              "randomised experiment, or change the graph.{note}",
    },
    "interventional_risk_needs_distributions": {
        "zh": "P(Y=1|do(X)) 可识别，但算不出数——它需要的分布列在旁边。请把"
              "它们补上；或者直接给出来自随机实验的 experimental_risk_treated "
              "/ experimental_risk_control，跳过它们。{note}",
        "en": "P(Y=1|do(X)) is identifiable but not computable — the "
              "distributions it needs are listed beside this. Supply them; "
              "or give experimental_risk_treated / experimental_risk_control "
              "from a randomised experiment and skip them.{note}",
    },
    "interventional_risk_unavailable_for_cell": {
        "zh": "P(Y=1|do(X={arm})) 推不出来（该效应从所给数据不可识别），少了它"
              "这个反事实单格就定不下来。请提供来自随机实验的 "
              "experimental_risk_treated / experimental_risk_control，或补上"
              "识别该效应所需的数据。{note}",
        "en": "P(Y=1|do(X={arm})) cannot be derived (that effect is not "
              "identifiable from the data given), and without it this "
              "counterfactual cell is not pinned down. Supply "
              "experimental_risk_treated / experimental_risk_control from a "
              "randomised experiment, or supply the data that identifies the "
              "effect.{note}",
    },
    "interventional_risks_contradict_the_joint": {
        "zh": "给出的干预风险与观测联合分布互相矛盾（一致性约束），没有任何 "
              "SCM 能同时产生两者——PN/PS/PNS 无定义。{detail}",
        "en": "the interventional risks given contradict the observed joint "
              "(the consistency constraint): no SCM produces both, so "
              "PN/PS/PNS are undefined. {detail}",
    },
    "iv_stratum_weights_not_normalized": {
        "zh": "给出的工具条件分层概率之和是 {total}，不是 1。LATE 比值对尺度"
              "不敏感，数照样算得出来，但报告里的处理变动是一个「顺从者占比」，"
              "对着一组根本不成其为分布的权重毫无意义。",
        "en": "the instrument's conditional stratum probabilities sum to "
              "{total}, not 1. The LATE ratio is scale-free so a number still "
              "comes out, but the treatment shift the report gives is a "
              "complier share, and that is meaningless against weights that "
              "are not a distribution.",
    },
    "iv_first_stage_degenerate": {
        "zh": "工具 {instrument} 推不动处理（加权后的第一阶段 ≈ 0），所以 Wald "
              "比值无定义——没有顺从者子总体可供平均。换一个、或更强的工具，"
              "才是补上这一条的办法。",
        "en": "instrument {instrument} does not move the treatment (the "
              "weighted first stage is ≈ 0), so the Wald ratio is undefined — "
              "there is no complier subpopulation to average over. A "
              "different, or stronger, instrument is what fills this.",
    },
    "iv_monotonicity_undeclared": {
        "zh": "有 {count} 个有效工具能到达这个效应——{candidate}——但光有工具"
              "并不能定下用哪个估计量。声明 assumptions.monotonicity 可以得到"
              "顺从者中的 Wald LATE；内核不会替你在 Wald、2SLS 和界之间做选择。",
        "en": "{count} valid instrument(s) reach this effect — {candidate} — "
              "but having an instrument does not settle which estimator to "
              "use. Declaring assumptions.monotonicity buys the Wald LATE "
              "among compliers; the kernel will not choose between Wald, "
              "2SLS and bounds on your behalf.",
    },
    "theta_entry_missing": {
        "zh": "Theta 中缺条目 {key}",
        "en": "Theta has no entry for {key}",
    },
    "graph_contradicts_supplied_marginal": {
        "zh": "Theta 中缺条目 {key}；theta 里有 {have}，但声明的图蕴含 "
              "{variable} ⊥ {{{extras}}} | {{{conditioning}}} 不成立，故不能用"
              "边缘量替代条件量。要么补上被要求的那个条件量，要么改图——"
              "「多给点 theta」是另一个问题的答案。",
        "en": "Theta has no entry for {key}; theta does hold {have}, but the "
              "declared graph does not imply {variable} ⊥ {{{extras}}} | "
              "{{{conditioning}}}, so the marginal cannot stand in for the "
              "conditional. Supply the conditional that was demanded, or "
              "change the graph — \"more theta\" answers a different "
              "question.",
    },
    "query_bound_atom_unresolved": {
        "zh": "公式里有一个查询绑定的原子没有具体取值；数值层没有外部提供的"
              "代入就解不开它",
        "en": "the formula holds a query-bound atom with no concrete value; "
              "the numeric layer cannot resolve it without an externally "
              "supplied substitution",
    },
    "counterfactual_bound_needs_entry": {
        "zh": "反事实界需要 {key}",
        "en": "the counterfactual bound needs {key}",
    },
    "iv_wald_late_needs_entry": {
        "zh": "工具变量 Wald LATE 需要它（工具 {instrument}）",
        "en": "the instrumental-variable Wald LATE needs it (instrument "
              "{instrument})",
    },
    "iv_wald_late_needs_entry_in_stratum": {
        "zh": "工具变量 Wald LATE 需要它（工具 {instrument}，给定 {given}）",
        "en": "the instrumental-variable Wald LATE needs it (instrument "
              "{instrument}, given {given})",
    },
    "unit_observation_missing": {
        "zh": "确定性反事实需要这个变量在该个体上的观测值，归因这一步才能还原"
              "它的外生项",
        "en": "a deterministic counterfactual needs this unit's measured "
              "value for the variable, so that abduction can recover its "
              "exogenous term",
    },
    "framing_fields_unfilled": {
        "zh": "变量 `{predicate}` 已声明，但缺 {count} 个操作化字段：{fields}",
        "en": "variable `{predicate}` is declared but is missing {count} "
              "operationalisation field(s): {fields}",
    },
}
"""The reader's sentence for a need, in every language this build writes.

The field names inside them stay as they are: they are what a caller types
back into a declaration, so translating them would name something that does
not exist. The sentence around them is the reader's.

Five slots are not values but another layer's sentence, arriving already
rendered: ``proximal_not_identifiable{detail}`` (one of seven criteria,
each with its wording in ``proximal_identify``), ``transport_not_
identifiable{detail}``, ``interventional_risks_contradict_the_joint
{detail}``, and the ``{note}`` on the three interventional-risk species,
which is the instrument route saying why IT could not reach the quantity
either — one of its three forms quotes a refusal. Each needs its own
species where it is produced, and the last needs a way for a shortfall to
cite a refusal rather than quote one. Named here so the count is a
measurement rather than an impression.
"""


#: What each population is called where the occasion did not name it.
_TARGET_POPULATION: language.Words = {"zh": "目标人群",
                                      "en": "the target population"}
_SOURCE_POPULATION: language.Words = {"zh": "源人群",
                                      "en": "the source population"}


WANTED: dict[str, language.Words] = {
    "unidentifiable_no_admissible_set": {
        "zh": "可识别的调整集，或另一条识别路径",
        "en": "an identifiable adjustment set, or another route to "
              "identification",
    },
    "missing_distribution": {
        "zh": "缺的那个分布", "en": "the distribution this is short of",
    },
    "missing_population_distribution": {
        "zh": "目标人群的分布", "en": "the target population's distribution",
    },
    "missing_assumption": {
        # Not always an assumption to declare — the same channel carries
        # experimental inputs and contradictory declarations, so this names
        # the premise rather than the repair.
        "zh": "识别前提", "en": "an identification premise",
    },
    "missing_unit_observation": {
        "zh": "该单位的观测值", "en": "this unit's observed values",
    },
    "missing_structural_input": {
        "zh": "结构输入", "en": "a structural input",
    },
    "missing_iv_candidate": {
        "zh": "有效的工具变量", "en": "a valid instrument",
    },
    "missing_mediator_data": {
        "zh": "中介的相关分布", "en": "the mediator's distributions",
    },
    "transport_target_distribution_unknown": {
        "zh": "目标人群上的 P*(Z)",
        "en": "P*(Z) on the target population",
    },
    "transport_source_conditional_unknown": {
        "zh": "源人群上的分层条件分布 P(Y|do(X), Z)",
        "en": "the stratified conditional P(Y|do(X), Z) on the source "
              "population",
    },
    "ambiguous_variable_definition": {
        "zh": "变量的操作化定义",
        "en": "an operational definition for the variable",
    },
    "dose_response_data_required": {
        "zh": "拟合剂量-响应曲线要的数据：X 的采样点、每点的样本量、要控制"
              "的混杂",
        "en": "the data a dose-response curve needs: sampling points for X, "
              "the sample size at each, and the confounders to control",
    },
    "unverified_proposal_edge_on_query_path": {
        "zh": "支持这条边的证据——现在它只是上游 LLM 的提议",
        "en": "evidence for that edge — right now it is only the upstream "
              "LLM's proposal",
    },
    "iv_identification_assumption_required": {
        "zh": "对工具变量所依赖的那条假设（单调性，或线性）的确认",
        "en": "confirmation of the assumption the instrument rests on "
              "(monotonicity, or linearity)",
    },
    "mediation_identification_assumption_required": {
        "zh": "对中介识别假设的确认：跨世界可忽略性、无中间混杂",
        "en": "confirmation of the mediation assumptions: cross-world "
              "ignorability, and no intermediate confounder",
    },
    "transport_identification_assumption_required": {
        "zh": "对 S-可容许性与选择节点设定的确认",
        "en": "confirmation of S-admissibility and of the selection-node "
              "specification",
    },
    "llm_declared_ambiguity": {
        "zh": "对上游声明的那处歧义的裁定",
        "en": "a decision on the ambiguity the upstream program declared",
    },
    "answer_is_bounds_not_point_estimate": {
        "zh": "能把区间收成一个点的额外假设",
        "en": "an extra assumption that would narrow the interval to a point",
    },
    "low_confidence_input_data": {
        "zh": "置信度更高的输入陈述",
        "en": "a higher-confidence input statement",
    },
    "front_door_identification_assumption_required": {
        "zh": "对前门那三条图形前提的确认",
        "en": "confirmation of the three front-door premises",
    },
    "counterfactual_identification_assumption_required": {
        "zh": "对一致性与组合公理的确认（走界的话，还要二值 + 单调）",
        "en": "confirmation of consistency and composition (and, for the "
              "bounds, binary + monotonicity)",
    },
    "graph_learned_from_data": {
        "zh": "对这张学出来的图的领域确认",
        "en": "domain confirmation of the graph that was learned",
    },
    "unmeasured_confounder_risk": {
        "zh": "未测混杂的敏感性分析，或一个不靠「混杂都测到了」的设计",
        "en": "a sensitivity analysis for unmeasured confounding, or a design "
              "that does not assume every confounder was measured",
    },
    "unattempted_layer_due_to_dispatch_conflict": {
        "zh": "把没被处理的那一层单独发一次查询",
        "en": "a separate query for the layer that was not dispatched",
    },
    "weak_iv_instrument": {
        "zh": "更强的工具变量，或一个对弱工具稳健的区间",
        "en": "a stronger instrument, or a weak-instrument-robust interval",
    },
    "overidentification_rejected": {
        "zh": "一组能通过过度识别检验的工具变量",
        "en": "instruments that survive the over-identification test",
    },
    "iv_estimand_fallback_to_linear": {
        "zh": "分得开那些层的样本——否则要接受 2SLS 答的是另一个量",
        "en": "a sample that can be cut into those strata — otherwise, "
              "accepting that 2SLS targets a different quantity",
    },
    "propensity_overlap_violation": {
        "zh": "在没有观测的那一臂上的样本",
        "en": "units in the arm that has none",
    },
    "collider_conditioning_opens_backdoor": {
        "zh": "一个不含对撞点的条件集",
        "en": "a conditioning set that does not hold the collider",
    },
    "outcome_model_quasi_separation": {
        "zh": "结局不近乎确定的样本，或一个不会饱和的结局模型",
        "en": "a sample where the outcome is not near-deterministic, or an "
              "outcome model that does not saturate",
    },
    "graph_theta_independence_mismatch": {
        # The repair is structural, so this names the choice rather than the
        # symptom: the two inputs disagree and one of them has to move.
        "zh": "图与 CPT 的不一致——改图，或补上被要的那个条件量",
        "en": "the disagreement between the graph and the CPTs — fix the "
              "graph, or supply the conditional it asked for",
    },
    "measurement_error_concern": {
        "zh": "测量误差的信度参数，或一份验证子样本",
        "en": "a reliability coefficient for the measurement, or a validation "
              "subsample",
    },
    "selection_on_collider_opens_path": {
        "zh": "选择是怎么发生的，或一条不经过它的路径",
        "en": "how the selection happened, or a route that does not pass "
              "through it",
    },
    "ill_defined_intervention_versions": {
        "zh": "干预到底指哪个版本",
        "en": "which version of the intervention is meant",
    },
    "dichotomized_continuous_measure": {
        "zh": "二分之前的那份连续测量",
        "en": "the continuous measurement, before it was dichotomized",
    },
    "declared_type_data_mismatch": {
        "zh": "让声明和数据对上——改声明，或换数据",
        "en": "a declaration and a column that agree — fix one or the other",
    },
}
"""What would close a gap of this kind, as the noun phrase it is asked for by.

A reader who has been told what is missing is owed "so supply THIS", and
what fills that hole is a NAME, not a sentence: it is read inside "supply
{}", and a description is a complete statement that turns that line into a
wall of text. The line was assembled in ``data_gap_report`` out of a chain
over twelve of the thirty-six kinds, and the other twenty-four fell through
to the description — which is how a function whose own docstring says it
exists to prevent a wall of text came to produce one, seventeen times on the
corpus, once out of a description with a median length of 1518 characters.

Total over :class:`~themis.types.GapKind` rather than a chain with a
fallback, because a fallback is what let those twenty-four be silent. A kind
added upstream now costs a phrase here instead of costing the reader a page.
"""


WANTED_NAMED: dict[str, language.Words] = {
    "missing_distribution": {"zh": "{name}", "en": "{name}"},
    "missing_mediator_data": {
        "zh": "中介 {mediator} 的相关分布",
        "en": "the distributions belonging to mediator {mediator}",
    },
    # ``{population}`` is a name the program chose, so the particles go
    # around it rather than butting against it: the phrase has to read
    # whether what lands there is Latin or Chinese, and only the template
    # can put a space there.
    "transport_target_distribution_unknown": {
        "zh": "P*({variables}) 在 {population} 上",
        "en": "P*({variables}) on {population}",
    },
    "transport_source_conditional_unknown": {
        "zh": "P(Y|do(X), {variables}) 在 {population} 上的分层条件分布",
        "en": "the stratified conditional P(Y|do(X), {variables}) on "
              "{population}",
    },
    "ambiguous_variable_definition": {
        "zh": "`{variable}` 的操作化定义",
        "en": "an operational definition for `{variable}`",
    },
}
"""The same thing, for the occasions that can name it.

A phrase naming the variables it wants is worth more than one naming their
role, and the gap does not always carry them — so this is a refinement on
:data:`WANTED` rather than a replacement, and every key here is a key there.
"""


def _read(entry, key: str):
    """One field off a gap, on either side of the serialization boundary.

    The reason :func:`said` gives, one level down: a report is read as the
    dataclass in-process and as the dict it becomes on the envelope, and a
    reader should not have to know which it is holding.
    """
    if entry is None:
        return None
    if isinstance(entry, Mapping):
        return entry.get(key)
    return getattr(entry, key, None)


def _occasion(gap, kind: str, lang: language.Lang | str) -> "dict | None":
    """This gap's facts for the slots :data:`WANTED_NAMED` has, or nothing.

    ``None`` where the occasion does not name them, which is what selects
    the plain phrase — rather than :func:`themis.language.assemble`'s
    fallback of saying the hole by its own name, which would put
    ``P*(`variables`)`` in front of a reader.
    """
    if kind == GapKind.MISSING_DISTRIBUTION:
        # The distribution's own name, off the provenance the species
        # wrote. The channel prefix is the pusher's and not the reader's.
        ref = _cited(gap, GapRefKind.INVESTIGATION_REQUEST)
        prefix = "parameter:"
        if ref is None:
            return None
        return {"name": ref[len(prefix):] if ref.startswith(prefix) else ref}
    if kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION:
        ref = _cited(gap, GapRefKind.FRAMING_NOTE)
        return None if ref is None else {"variable": ref}
    required = _read(gap, "required_data")
    variables = list(_read(required, "variables") or ())
    if not variables:
        return None
    if kind == GapKind.MISSING_MEDIATOR_DATA:
        return {"mediator": variables[0]}
    default = (_TARGET_POPULATION
               if kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN
               else _SOURCE_POPULATION)
    return {
        "variables": language.fill(language.BETWEEN_ITEMS,
                                   lang).join(variables),
        "population": (_read(required, "population")
                       or language.fill(default, lang)),
    }


def _cited(gap, ref_kind: GapRefKind) -> "str | None":
    """The first thing this gap cites through that channel, by id."""
    for prov in _read(gap, "provenance") or ():
        if str(_read(prov, "ref_kind") or "") == ref_kind:
            ref = _read(prov, "ref_id")
            if ref:
                return str(ref)
    return None


def wanted(gap, lang: language.Lang | str = language.DEFAULT) -> str:
    """A gap, as the thing this reader is being asked to supply.

    The reader's half of :data:`WANTED`, and the reason the report no
    longer carries a next-steps list: every input to that list — which gaps
    block, which have somewhere to go, and what each is short of — is
    already on the envelope, so the list was a rendering the kernel had
    grown, in one language its own schema named.

    A kind this build has never heard of is said by its token, for the
    reason :func:`themis.language.gloss` gives, and only reachable from an
    envelope another build wrote.
    """
    kind = language.token(_read(gap, "kind"))
    template = WANTED.get(kind)
    if template is None:
        return language.gloss({}, kind, lang)
    named = WANTED_NAMED.get(kind)
    if named is not None:
        slots = _occasion(gap, kind, lang)
        if slots is not None:
            return language.capped(language.fill(named, lang, **slots))
    return language.fill(template, lang)


@unique
class Route(EnvelopeName):
    """One way past a gap, by name.

    A member is ``(token, points_at_bounds, what it means to whoever adds
    the next one)``. These were finished sentences on the envelope, and
    :class:`themis.types.GapRoute` says what that cost; this is the name
    they were being spelled out as.

    ``points_at_bounds`` is the one property a pass has to ask about a
    route, and it is declared here rather than at the site for the reason
    :class:`Need`'s kind is: the scheduler asked it by searching the
    rendered sentence for ``"bounds"``, ``"Manski"`` and ``"Balke-Pearl
    bounds"``, so a route's answer depended on its wording and on the
    language it was rendered in. It is true of exactly the two routes that
    offer an interval INSTEAD of this point — the ones a computed interval
    makes redundant. A route that offers an interval to a DIFFERENT
    question (binarise the dose, then Themis can bracket it) is not one of
    them, and could not say so while the test was a substring.
    """

    points_at_bounds: bool
    says: str

    def __new__(cls, value: str, points_at_bounds: bool,
                says: str) -> "Route":
        member = str.__new__(cls, value)
        member._value_ = value
        member.points_at_bounds = points_at_bounds
        member.says = says
        return member

    # --- take the interval this question does have ------------------------

    ACCEPT_THE_INTERVAL = (
        "accept_the_interval", True,
        "the point is out of reach; take the interval this question's "
        "fallback method brackets it with")
    BOUNDS_ALREADY_COMPUTED = (
        "bounds_already_computed", True,
        "the interval is in hand — the scheduler replaces the offer above "
        "with this once the methods have run")

    # --- change the graph, or what was measured ---------------------------

    MEASURE_THE_CONFOUNDER_TO_BREAK_THE_HEDGE = (
        "measure_the_confounder_to_break_the_hedge", False,
        "measure the unmeasured common cause, and the hedge that blocked "
        "identification is gone")
    MEASURE_THE_CONFOUNDER_AND_REIDENTIFY = (
        "measure_the_confounder_and_reidentify", False,
        "the same move where what failed was the back-door search rather "
        "than a hedge")
    RUN_AN_RCT_PAST_THE_HEDGE = (
        "run_an_rct_past_the_hedge", False,
        "randomise the treatment and the hedge stops mattering")
    RUN_AN_RCT_PAST_THE_BACKDOOR = (
        "run_an_rct_past_the_backdoor", False,
        "randomise the treatment and there is no back-door path left")
    FIND_AN_INSTRUMENT = (
        "find_an_instrument", False,
        "an instrument satisfying the IV conditions identifies what no "
        "adjustment set can")
    TIGHTEN_THE_IV_INTERVAL = (
        "tighten_the_iv_interval", False,
        "an instrument is already in hand and already gave the interval; "
        "the POINT needs one further assumption on top of it")

    # --- accept a different quantity --------------------------------------

    FALL_BACK_TO_CDE = (
        "fall_back_to_cde", False,
        "the decomposition is out of reach; the controlled direct effect "
        "is not")
    FALL_BACK_TO_THE_TOTAL_EFFECT = (
        "fall_back_to_the_total_effect", False,
        "ask for the total effect and do not decompose it")
    FALL_BACK_TO_A_BINARY_CONTRAST = (
        "fall_back_to_a_binary_contrast", False,
        "the dose-response curve is out of scope; a high-vs-low contrast "
        "is a question this kernel brackets. Offers an interval, and is "
        "NOT points_at_bounds: it is an interval on a different question, "
        "so a computed one here does not make it redundant")
    ASK_THE_MARGINAL_EFFECT = (
        "ask_the_marginal_effect", False,
        "drop the conditioning that opened the collider path and ask the "
        "marginal effect instead")
    ACCEPT_THE_SOURCE_ATE = (
        "accept_the_source_ate", False,
        "take the source population's effect as a rough transfer, knowing "
        "the extrapolation is weak")

    # --- say more about the model ------------------------------------------

    SUPPLY_A_SOURCE_FOR_THE_EDGE = (
        "supply_a_source_for_the_edge", False,
        "the edge is a proposal; a study or a data source turns it into "
        "evidence")
    ASK_CONDITIONALLY = (
        "ask_conditionally", False,
        "ask what follows IF the proposed edge holds, which is a question "
        "the proposal can answer")
    SUPPLY_THE_CONDITIONAL = (
        "supply_the_conditional", False,
        "the graph is accepted and the missing conditional is what stands "
        "in the way")
    DROP_THE_CONTRADICTING_EDGE = (
        "drop_the_contradicting_edge", False,
        "the other side of the same disagreement: keep the CPTs and take "
        "out the edge they refute")
    MAYBE_IT_IS_NOT_A_COLLIDER = (
        "maybe_it_is_not_a_collider", False,
        "the conditioning variable is a collider only if both are its "
        "ancestors; if one is not, the graph is what is wrong")
    MAYBE_IT_IS_NOT_A_COMMON_EFFECT = (
        "maybe_it_is_not_a_common_effect", False,
        "the same doubt for the selection variable")
    DECLARE_IT_A_SELECTION_NODE = (
        "declare_it_a_selection_node", False,
        "say the variable selects the population rather than being "
        "observed in it, and the transport route handles it")
    TREAT_THE_COLLIDER_AS_A_TARGET_POPULATION = (
        "treat_the_collider_as_a_target_population", False,
        "the same move for a collider in the conditioning set")
    DECLARE_THE_INTERVENTION_AN_EVENT = (
        "declare_the_intervention_an_event", False,
        "a one-off act with a manipulation behind it, so do(.) has "
        "something to point at")
    SPLIT_THE_INTERVENTION_IN_TWO = (
        "split_the_intervention_in_two", False,
        "an event that can be acted on, plus the state it leads to, "
        "handled as mediation")
    ACCEPT_THE_MIXED_ESTIMAND = (
        "accept_the_mixed_estimand", False,
        "declare that this question accepts an estimator mixing several "
        "versions of the intervention, and the warning is withdrawn")
    DROP_THE_OTHER_LAYER = (
        "drop_the_other_layer", False,
        "two identification layers were asked for and one was dispatched; "
        "asking for one at a time makes the dispatch unambiguous")

    # --- get different data -------------------------------------------------

    COLLECT_IT_NO_INTERVAL_FALLBACK = (
        "collect_it_no_interval_fallback", False,
        "this question has no interval to fall back on, so the data are "
        "the only way to a number")
    USE_EXPERIMENTAL_DATA_FOR_THE_VERSIONS = (
        "use_experimental_data_for_the_versions", False,
        "a randomisation protocol defines what the intervention was "
        "compared with, which is what the observational sample cannot say")
    USE_EXPERIMENTAL_DATA_INSTEAD_OF_SELF_REPORT = (
        "use_experimental_data_instead_of_self_report", False,
        "experimental assignment is not self-reported, so the measurement "
        "error goes with it")
    CROSS_CHECK_AN_EXPERIMENT = (
        "cross_check_an_experiment", False,
        "a randomised or quasi-experimental estimate of the same quantity "
        "is a check on this one")
    EMULATE_A_TARGET_TRIAL = (
        "emulate_a_target_trial", False,
        "Hernán-Robins: state the trial this analysis is imitating, then "
        "imitate it — eligibility, assignment, per-protocol analysis")
    RUN_AN_E_VALUE = (
        "run_an_e_value", False,
        "how strong an unmeasured confounder would have to be to explain "
        "the estimate away")
    RETEST_RELIABILITY = (
        "retest_reliability", False,
        "a reliability coefficient is what a measurement-error correction "
        "needs")
    REPORT_ATTENUATION_RANGE = (
        "report_attenuation_range", False,
        "without the coefficient, a range for it still bounds the "
        "attenuation")
    REWEIGHT_FOR_SELECTION = (
        "reweight_for_selection", False,
        "inverse-probability-of-selection weights rebuild the sample the "
        "selection removed")
    FIND_THE_RCT_IPD = (
        "find_the_rct_ipd", False,
        "individual participant data from the source trial carries the "
        "stratified conditional a published marginal does not")
    FIND_A_SUBGROUP_ANALYSIS = (
        "find_a_subgroup_analysis", False,
        "a meta-analysis' subgroup tables are a coarse version of the "
        "same thing")
    FIND_A_MATCHED_RCT = (
        "find_a_matched_rct", False,
        "one small trial on a population close to the target, paying for "
        "the match in sample size")

    # --- keep the measurement you had ---------------------------------------

    KEEP_THE_MEASURE_CONTINUOUS = (
        "keep_the_measure_continuous", False,
        "do not dichotomise; estimate the dose-response instead")
    REPORT_CUTPOINT_SENSITIVITY = (
        "report_cutpoint_sensitivity", False,
        "if it must be dichotomised, show whether the conclusion survives "
        "moving the cut")
    STRATIFY_MORE_FINELY = (
        "stratify_more_finely", False,
        "a dichotomised confounder leaves residual confounding inside each "
        "half; finer strata or a spline reduce it")

    # --- the fit itself, where the estimator strained on this sample --------

    COLLECT_IN_THE_SATURATED_STRATA = (
        "collect_in_the_saturated_strata", False,
        "the logistic saturated because those cells are thin; events in "
        "them is what un-saturates it")
    USE_A_SEPARATION_ROBUST_FIT = (
        "use_a_separation_robust_fit", False,
        "keep the data and change the estimator to one that has a finite "
        "solution under separation")
    KNOW_THE_BOOTSTRAP_IS_ALSO_STRAINED = (
        "know_the_bootstrap_is_also_strained", False,
        "the interval already on this result is the better of the two, and "
        "this says how far that goes")
    GO_BAYESIAN_WITH_A_WEAK_PRIOR = (
        "go_bayesian_with_a_weak_prior", False,
        "a prior is what carries cells the likelihood alone cannot")

    # --- where the arms do not overlap --------------------------------------

    TRIM_TO_THE_OVERLAP_REGION = (
        "trim_to_the_overlap_region", False,
        "change the population to the one the data supports, and say that "
        "is what the number is now about")
    USE_AN_OVERLAP_ROBUST_METHOD = (
        "use_an_overlap_robust_method", False,
        "keep the population and change the estimator to one that does not "
        "need support everywhere")
    LOOSEN_THE_ADJUSTMENT_SET = (
        "loosen_the_adjustment_set", False,
        "the unsupported stratum stops being one stratum under a coarser "
        "set — if a defensible one exists")
    BOUND_THE_UNSUPPORTED_REGION = (
        "bound_the_unsupported_region", False,
        "bracket the region with no support rather than extrapolating "
        "into it. Not :attr:`points_at_bounds`: this is an interval over a "
        "REGION, not the fallback interval for the estimand, and the "
        "computed bounds are not it")

    # --- where the instrument is weak, or refuted ---------------------------

    COLLECT_IN_THE_ONE_ARMED_STRATA = (
        "collect_in_the_one_armed_strata", False,
        "the strata missing an instrument arm are what the stratified Wald "
        "cannot use; observations there recover the LATE directly")
    COARSEN_THE_CONDITIONING_SET = (
        "coarsen_the_conditioning_set", False,
        "wider cells carry both arms — as long as the coarser set still "
        "blocks the back door from the instrument")
    ACCEPT_THE_VARIANCE_WEIGHTED_2SLS = (
        "accept_the_variance_weighted_2sls", False,
        "report the coefficient for what it is rather than for the LATE it "
        "is not")
    FIND_A_STRONGER_INSTRUMENT = (
        "find_a_stronger_instrument", False,
        "the bias is 1/F, so a higher first-stage partial correlation is "
        "the whole of the remedy")
    FIND_STRONGER_INSTRUMENTS_JOINTLY = (
        "find_stronger_instruments_jointly", False,
        "the over-identified twin of the one above: what is weak is the "
        "JOINT first stage, so no single instrument is the answer")
    FALL_BACK_TO_IV_BOUNDS = (
        "fall_back_to_iv_bounds", True,
        "the bounds hold whatever the first stage is, so a weak instrument "
        "costs width rather than validity")
    FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION = (
        "fall_back_to_bounds_without_exclusion", True,
        "the twin for a REFUTED exclusion rather than a weak one: only the "
        "bounds that never assumed exclusion survive it")
    AR_SET_NOT_CONSTRUCTIBLE = (
        "ar_set_not_constructible", False,
        "the weak-identification-robust interval is the right answer here "
        "and this sample could not form one — so it is data to collect, "
        "not a block to read off this result")
    USE_THE_AR_SET = (
        "use_the_ar_set", False,
        "it is already computed and on this envelope; the bootstrap "
        "interval beside it is the one that is not valid")
    AR_SET_FOR_THE_JOINT_STAGE = (
        "ar_set_for_the_joint_stage", False,
        "the same offer where the weakness is joint and no set was computed")
    USE_THE_ROBUST_AR_SET = (
        "use_the_robust_ar_set", False,
        "the Stock-Wright S form, valid under weak identification AND "
        "heteroskedasticity — strictly the stronger of the two to report")
    DROP_THE_SUSPECT_INSTRUMENT = (
        "drop_the_suspect_instrument", False,
        "over-identification rejects the SET; a subset may still pass")
    REEXAMINE_THE_GRAPH_FOR_A_DIRECT_PATH = (
        "reexamine_the_graph_for_a_direct_path", False,
        "a rejected over-identification test is usually the graph being "
        "wrong rather than the sample being small")

    # --- where the declaration and the column disagree ----------------------

    FIX_THE_DATA_TO_MATCH_THE_DECLARATION = (
        "fix_the_data_to_match_the_declaration", False,
        "one of the two is wrong and only the reader knows which; this is "
        "the branch where the declaration was right")
    FIX_THE_DECLARATION_TO_MATCH_THE_DATA = (
        "fix_the_declaration_to_match_the_data", False,
        "the other branch, where what has to move is the estimand rather "
        "than the column")


BY_ROUTE: dict[str, Route] = {str(r): r for r in Route}
"""The route going by that envelope name, or nothing.

For the read direction, where an unknown name is a question rather than an
error — the reason :data:`BY_NAME` gives, and here it is load-bearing:
:func:`taken` answers it for passes that are deciding what to withdraw.
"""


ROUTES: dict[str, language.Words] = {
    # The route the scheduler substitutes for the offer above once the
    # methods have run. It lived in ``runtime.scheduler`` as an f-string in
    # one language, naming an envelope key at a reader ("见 bounds_results")
    # — the only sentence on this field with no second language at all.
    "bounds_already_computed": {
        "zh": "已经算出区间了（method={methods}）",
        "en": "the interval has already been computed (method={methods})",
    },
    "accept_the_interval": {
        "zh": "接受 {fallback} 给区间答案",
        "en": "accept {fallback} and take the interval answer",
    },
    "accept_the_mixed_estimand": {
        "zh": "在 extensions.ambiguities 里以 `ill_defined_intervention` kind 显式"
              "声明本题接受多 intervention 的混合估计量 —— Themis 会停发本警告并在渲"
              "染时把 caveat 显式化",
        "en": "declare under extensions.ambiguities, with the kind "
              "`ill_defined_intervention`, that this question accepts an estimand "
              "mixed over several interventions — Themis stops issuing this "
              "warning and makes the caveat explicit when it renders",
    },
    "accept_the_source_ate": {
        "zh": "接受源人群 ATE 作为粗略估计（外推有效性弱）",
        "en": "take the source population's ATE as a rough estimate (the "
              "extrapolation rests on little)",
    },
    "ask_conditionally": {
        "zh": "改为询问'若该边成立则…'的条件性问题",
        "en": "ask the conditional question instead — 'if this edge holds, then "
              "…'",
    },
    "ask_the_marginal_effect": {
        "zh": "不做这个条件，问 marginal 效应 P({target} | do({intervention}))",
        "en": "drop the condition and ask for the marginal effect P({target} | "
              "do({intervention}))",
    },
    "collect_it_no_interval_fallback": {
        "zh": "直接收集 {what} 的数据 —— 该问法没有区间退路，拿不到点估计就没有数",
        "en": "collect data for {what} directly — this question has no interval "
              "to fall back on, so without the point estimate there is no number "
              "at all",
    },
    "cross_check_an_experiment": {
        "zh": "有随机对照 / 准实验数据时，拿它和这个观察性估计相互印证",
        "en": "where randomized or quasi-experimental data exists, check it "
              "against this observational estimate",
    },
    "declare_it_a_selection_node": {
        "zh": "用 `selection_node` (Phase 9 §T9.1) 把 `{collider}` 声明为 transport "
              "选择节点而不是观察节点，并通过 transport identification 路径处理跨人群"
              "泛化",
        "en": "declare `{collider}` a transport selection node rather than an "
              "observation node with `selection_node` (Phase 9 §T9.1), and "
              "generalize across populations through the transport identification "
              "route",
    },
    "declare_the_intervention_an_event": {
        "zh": "把 `{intervention}` 重新声明为一个具体的事件类变量"
              "（state_vs_event=\"event\"）—— 一个有明确操纵动作的一次性事件，这样 "
              "do(.) 有明确目标",
        "en": "redeclare `{intervention}` as a concrete event variable "
              "(state_vs_event=\"event\") — a one-off event with a definite "
              "manipulation behind it, so do(.) has something definite to act on",
    },
    "drop_the_contradicting_edge": {
        "zh": "删除引发独立性矛盾的边（改图，承认现有 CPT 已是真分布）",
        "en": "drop the edge that causes the contradiction (change the graph, "
              "and take the CPTs as the true distribution)",
    },
    "drop_the_other_layer": {
        "zh": "如果只想要 {wanted} 结果，删除 {drop} 使 dispatch 唯一",
        "en": "if the {wanted} result is the one you want, drop {drop} so the "
              "dispatch is unambiguous",
    },
    "emulate_a_target_trial": {
        "zh": "按 Hernán-Robins 的目标试验模拟（target trial emulation）重新设计：明"
              "确入组条件，做 per-protocol 分析",
        "en": "redesign it as a Hernán-Robins target trial emulation: state the "
              "eligibility criteria, and do a per-protocol analysis",
    },
    "fall_back_to_a_binary_contrast": {
        "zh": "退一步只看二元对比 (X=high vs X=low)：Themis 能给区间答案",
        "en": "step back to the binary contrast (X=high vs X=low), which Themis "
              "can answer with an interval",
    },
    "fall_back_to_cde": {
        "zh": "回退到 CDE（控制中介，给条件直接效应）",
        "en": "fall back to the CDE (hold the mediator fixed, and take the "
              "controlled direct effect)",
    },
    "fall_back_to_the_total_effect": {
        "zh": "退回 total effect，不分解",
        "en": "fall back to the total effect, undecomposed",
    },
    "find_a_matched_rct": {
        "zh": "退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价",
        "en": "failing that: find the one small RCT closest to your subgroup, and "
              "pay for it in sample size",
    },
    "find_a_subgroup_analysis": {
        "zh": "找 meta-analysis 的 subgroup analysis（按 age / sex / BMI 分层）",
        "en": "find the meta-analysis's subgroup analysis (stratified by age / "
              "sex / BMI)",
    },
    "find_an_instrument": {
        "zh": "找一个满足 IV 条件的工具变量",
        "en": "find an instrument that satisfies the IV conditions",
    },
    "find_the_rct_ipd": {
        "zh": "找原始 RCT IPD（联系作者 / 看附件 supplementary table）",
        "en": "find the original RCT's individual participant data (write to the "
              "authors, or check the supplementary tables)",
    },
    "keep_the_measure_continuous": {
        "zh": "保留连续变量，用 dose-response 估计代替二分（Themis Phase 13/14）",
        "en": "keep the variable continuous and estimate the dose-response "
              "instead of dichotomizing (Themis Phase 13/14)",
    },
    "maybe_it_is_not_a_collider": {
        "zh": "如果 `{collider}` 不是真 collider（即只有 X 或只有 Y 是祖先），更新 "
              "DAG 把缺失的因果方向加进去 — 当前结构性结论会变",
        "en": "if `{collider}` is not really a collider (only X or only Y is an "
              "ancestor), update the DAG with the causal direction that is "
              "missing — the structural conclusion will change",
    },
    "maybe_it_is_not_a_common_effect": {
        "zh": "如果 `{collider}` 实际并非由 `{intervention}` 和 `{target}` 共同决"
              "定，更新 DAG 删除其中一条祖先边 —— 当前结构性结论会随之改变",
        "en": "if `{collider}` is not in fact determined by both `{intervention}` "
              "and `{target}`, update the DAG and remove one of those ancestor "
              "edges — the structural conclusion moves with it",
    },
    "measure_the_confounder_and_reidentify": {
        "zh": "测量并加入 unmeasured confounder Z，重新识别",
        "en": "measure the unmeasured confounder Z, add it, and identify again",
    },
    "measure_the_confounder_to_break_the_hedge": {
        "zh": "测量并加入 unmeasured confounder Z，打破 hedge",
        "en": "measure the unmeasured confounder Z, add it, and break the hedge",
    },
    "report_attenuation_range": {
        "zh": "在敏感性分析中报告 attenuation factor 范围（Rosner et al 1989 "
              "regression calibration upper bound）",
        "en": "report a range for the attenuation factor in the sensitivity "
              "analysis (the regression-calibration upper bound of Rosner et al "
              "1989)",
    },
    "report_cutpoint_sensitivity": {
        "zh": "若必须二分，报告对 cutpoint 的敏感性分析（多个切点下结论是否稳定）",
        "en": "if it has to be dichotomized, report a sensitivity analysis over "
              "the cutpoint (does the conclusion hold at several of them)",
    },
    "retest_reliability": {
        "zh": "对涉及变量做 reliability 重测，按 Carroll et al 2006 *Measurement "
              "Error in Nonlinear Models* 校准",
        "en": "run a reliability retest on the variables involved and calibrate "
              "as in Carroll et al 2006 *Measurement Error in Nonlinear Models*",
    },
    "reweight_for_selection": {
        "zh": "用 inverse-probability-of-selection weighting (Hernán et al 2004 "
              "§5)：对每个保留样本按 1/P({collider}={value} | X, Y) 加权重抽以近似全"
              "样本",
        "en": "use inverse-probability-of-selection weighting (Hernán et al 2004 "
              "§5): weight each retained subject by 1/P({collider}={value} | X, "
              "Y) to approximate the whole sample",
    },
    "run_an_e_value": {
        "zh": "数据到位后跑 E-value 敏感性分析（Phase 8.2，对二值结局自动附）",
        "en": "run an E-value sensitivity analysis once the data is in hand "
              "(Phase 8.2, attached automatically for a binary outcome)",
    },
    "run_an_rct_past_the_backdoor": {
        "zh": "在 X 上做 RCT (如可行)，旁路 backdoor",
        "en": "randomize X if that is feasible, and bypass the back-door",
    },
    "run_an_rct_past_the_hedge": {
        "zh": "在 X 上做 RCT (如可行)，旁路 hedge",
        "en": "randomize X if that is feasible, and bypass the hedge",
    },
    "split_the_intervention_in_two": {
        "zh": "把 `{intervention}` 拆成两个变量：一个事件类的intervention（具体的操"
              "纵动作）+ 一个由它导致的中间状态，用 mediation 路径处理",
        "en": "split `{intervention}` into two variables: an event-shaped "
              "intervention (the concrete manipulation) and the intermediate "
              "state it causes, and handle it through the mediation route",
    },
    "stratify_more_finely": {
        "zh": "对被二分的 confounder，改用更细分层或样条以减少类内残余混杂（Becher "
              "1992）",
        "en": "for a dichotomized confounder, use finer strata or a spline to cut "
              "the within-category residual confounding (Becher 1992)",
    },
    "supply_a_source_for_the_edge": {
        "zh": "提供支持这条边的研究 / 数据来源",
        "en": "give the study or the data this edge rests on",
    },
    "supply_the_conditional": {
        "zh": "补充所缺的条件量 {what}（接受图）",
        "en": "supply the conditional {what} that is missing (and keep the graph)",
    },
    "tighten_the_iv_interval": {
        "zh": "工具变量已声明并已用于给出区间；要把区间收紧成点估计，需补一个额外假"
              "设：monotonicity（→ LATE/Wald）或 linearity（→ 2SLS/ATE）",
        "en": "an instrument is declared and the interval already uses it; "
              "tightening that interval to a point needs one further assumption "
              "— monotonicity (→ LATE/Wald) or linearity (→ 2SLS/ATE)",
    },
    "treat_the_collider_as_a_target_population": {
        "zh": "用 transport identification 路径处理 \"target population "
              "restricted by {collider}\" 而不是用 `given` 字段",
        "en": "handle \"target population restricted by {collider}\" through "
              "the transport identification route rather than through the "
              "`given` field",
    },
    "use_experimental_data_for_the_versions": {
        "zh": "用 RCT / 实验性数据替代观察性主样本 —— 实验里 do(.) 的\"compared "
              "with what\" 由随机化协议明确定义",
        "en": "replace the observational main sample with RCT or experimental "
              "data — in an experiment the randomization protocol defines what "
              "do(.) is \"compared with what\"",
    },
    "use_experimental_data_instead_of_self_report": {
        "zh": "用 RCT / 实验性分配数据（消除自报告偏差）替代观察性主样本",
        "en": "replace the observational main sample with randomized or "
              "experimentally assigned data, which removes the self-report bias",
    },

    # --- the fit itself ------------------------------------------------------
    "collect_in_the_saturated_strata": {
        "zh": "在饱和的那些子层补样本（多收 rare-outcome 的观测）——"
              "Hosmer-Lemeshow 的经验法则是每个参数至少 10 个事件",
        "en": "collect more observations in the saturated strata (more "
              "rare-outcome events) — the Hosmer-Lemeshow rule of thumb is "
              "at least 10 events per parameter"},
    "use_a_separation_robust_fit": {
        "zh": "改用 Firth 惩罚 logistic 或精确 logistic 回归"
              "（不是 sklearn 默认的 L2）——它们对 separation 稳健",
        "en": "fit a Firth penalised logistic or an exact logistic "
              "regression instead (not sklearn's default L2) — both are "
              "robust to separation"},
    "know_the_bootstrap_is_also_strained": {
        "zh": "用 bootstrap 置信区间而不是 plug-in 区间（这里已经是这样了，"
              "但 bootstrap 本身在饱和下也不稳，可能抽出 NaN）",
        "en": "use the bootstrap interval rather than the plug-in one "
              "(already the case here, though the bootstrap is itself "
              "unsteady under saturation and can draw NaNs)"},
    "go_bayesian_with_a_weak_prior": {
        "zh": "处理×混杂的格子稀疏到这个程度时，"
              "考虑贝叶斯拟合配弱信息先验，而不是频率派估计",
        "en": "where the treatment x confounder cells are this sparse, "
              "consider a Bayesian fit with a weakly informative prior "
              "rather than a frequentist estimate"},

    # --- overlap -------------------------------------------------------------
    "trim_to_the_overlap_region": {
        "zh": "把样本裁到重叠区域（例如丢掉倾向性落在 [0.05, 0.95] 之外的"
              "观测）再估一次——这样得到的答案是重叠子集上的 ATE，"
              "不是全人群的",
        "en": "trim the sample to the overlap region (dropping observations "
              "whose propensity falls outside [0.05, 0.95], say) and "
              "estimate again — the answer is then the ATE on the "
              "overlapping subset, not on the whole population"},
    "use_an_overlap_robust_method": {
        "zh": "换一个对重叠不足更稳健的方法（带卡钳的匹配、"
              "用加权 ATT 代替 ATE、按倾向性分层的估计量）",
        "en": "switch to a method more robust to thin overlap: caliper "
              "matching, a weighted ATT in place of the ATE, or a "
              "propensity-stratified estimator"},
    "loosen_the_adjustment_set": {
        "zh": "放宽调整集，让没有支撑的那一层不再是同一层"
              "——但前提是确实存在一个站得住脚的 Z 可以换过去",
        "en": "loosen the adjustment set so the unsupported stratum is no "
              "longer one stratum — but only if there is a defensible Z to "
              "move to"},
    "bound_the_unsupported_region": {
        "zh": "对没有支撑的那片区域，只给出界的答案",
        "en": "give a bounds answer over the region that has no support"},

    # --- the instrument ------------------------------------------------------
    "collect_in_the_one_armed_strata": {
        "zh": "在缺工具臂的那些分层里补收观测，这能直接把 LATE 救回来",
        "en": "collect observations in the strata that are missing an "
              "instrument arm — that recovers the LATE directly"},
    "coarsen_the_conditioning_set": {
        "zh": "把条件集变粗（更少或更宽的类别），让每一格都同时带上两条"
              "工具臂——但前提是变粗之后仍然挡得住工具到结局的后门",
        "en": "coarsen the conditioning set (fewer or wider categories) so "
              "that every cell carries both instrument arms — provided the "
              "coarser set still blocks the back door from the instrument "
              "to the outcome"},
    "accept_the_variance_weighted_2sls": {
        "zh": "就按原样报 2SLS 系数，同时说明它是各层效应的方差加权平均，"
              "而不是顺从者中的效应",
        "en": "report the 2SLS coefficient as it stands, saying that it is "
              "a variance-weighted average of the stratum effects rather "
              "than the effect among compliers"},
    "find_a_stronger_instrument": {
        "zh": "找一个更强的工具（条件之后，与处理的第一阶段偏相关"
              "更高的那种）",
        "en": "find a stronger instrument — one whose first-stage partial "
              "correlation with the treatment, after conditioning, is "
              "higher"},
    "find_stronger_instruments_jointly": {
        "zh": "找更强的工具（与处理的联合第一阶段偏相关更高的那种）",
        "en": "find stronger instruments — ones whose joint first-stage "
              "partial correlation with the treatment is higher"},
    "fall_back_to_iv_bounds": {
        "zh": "退回到只给界的答案（Manski 自然界 / Balke-Pearl IV 界"
              "对弱工具都是稳健的）",
        "en": "fall back to a bounds answer — Manski's natural bounds and "
              "the Balke-Pearl IV bounds are both robust to a weak "
              "instrument"},
    "fall_back_to_bounds_without_exclusion": {
        "zh": "退回到不假设排他性的、只给界的答案（Manski 自然界）",
        "en": "fall back to a bounds answer that assumes no exclusion "
              "restriction (Manski's natural bounds)"},
    "ar_set_not_constructible": {
        "zh": "拿到一个对弱识别稳健的区间（Anderson-Rubin），"
              "它不管第一阶段多强都有正确的水平；这份样本不足以构造出来，"
              "所以这意味着要更多数据或换一个设计，"
              "而不是从这个结果里读出来",
        "en": "get an interval robust to weak identification "
              "(Anderson-Rubin), which has the right level whatever the "
              "first stage is — this sample was not enough to construct "
              "one, so that means more data or a different design rather "
              "than something to read off this result"},
    "use_the_ar_set": {
        "zh": "改用 Anderson-Rubin {level}% 弱工具稳健集 {interval}"
              "（已经算好了；在弱工具下依然有效），不要用 bootstrap "
              "置信区间",
        "en": "use the Anderson-Rubin {level}% weak-instrument-robust set "
              "{interval} instead of the bootstrap interval — it is "
              "already computed and stays valid under a weak instrument"},
    "ar_set_for_the_joint_stage": {
        "zh": "报 Anderson-Rubin 置信集——它反转的那个检验，"
              "不管联合第一阶段多强都有正确的水平",
        "en": "report an Anderson-Rubin confidence set — the test it "
              "inverts has the right level whatever the joint first stage "
              "is"},
    "use_the_robust_ar_set": {
        "zh": "改用异方差稳健的 Anderson-Rubin {level}% 集 {interval}"
              "（在弱工具和异方差下都有效），不要用 bootstrap 置信区间",
        "en": "use the heteroskedasticity-robust Anderson-Rubin {level}% "
              "set {interval} instead of the bootstrap interval — it is "
              "valid under both a weak instrument and heteroskedasticity"},
    "drop_the_suspect_instrument": {
        "zh": "去掉排他性可疑的那个（些）工具再跑一次"
              "（某个子集可能就通过了）",
        "en": "drop the instrument(s) whose exclusion is in doubt and run "
              "again — some subset of them may pass"},
    "reexamine_the_graph_for_a_direct_path": {
        "zh": "重新审视因果图——过度识别检验被否决，往往意味着"
              "一条本以为只走 Z→X 的路径其实直接到达了 Y",
        "en": "re-examine the causal graph — a rejected over-identification "
              "test usually means a path believed to run only Z->X in fact "
              "reaches Y directly"},

    # --- the declaration and the column --------------------------------------
    "fix_the_data_to_match_the_declaration": {
        "zh": "若 `{variable}` 确实是{scale}的，"
              "那就是数据这一列有问题（供给的值与声明不符），改数据",
        "en": "if `{variable}` really is {scale}, then it is this column of "
              "the data that is wrong — the values supplied do not match "
              "the declaration — so fix the data"},
    "fix_the_declaration_to_match_the_data": {
        "zh": "若数据是对的，那就改声明（尺度 / 取值范围），"
              "让估计量对上你真正能测到的量",
        "en": "if the data is right, then fix the declaration (the scale, "
              "the range) so that the estimand matches the quantity you "
              "can actually measure"},
}
"""What each route says to a reader, in every language this build writes.

Beside the species for the reason :data:`SAYS` gives. The slots are this
occasion's facts and travel as :func:`themis.language.halve` splits them,
so a route naming a variable is the same route wherever it is named.
"""


def route(name, **details) -> GapRoute:
    """One way past a gap, in the one shape it takes.

    The writer's door, and the reason the field is not a list of sentences:
    :class:`themis.types.GapRoute` says what identifying a route by its
    rendering cost.
    """
    member = BY_ROUTE.get(str(name))
    if member is None:
        raise ValueError(
            f"{name!r} is not a route in themis.gaps.Route; a way past a "
            f"gap is named there before it is offered, so that the passes "
            f"which withdraw or replace one can say which they mean"
        )
    if str(member) not in ROUTES:
        raise ValueError(
            f"{member} has no sentence in themis.gaps.ROUTES; declare it "
            f"there, beside the route, so the reader's wording has one "
            f"author"
        )
    said, words = language.halve(details)
    return GapRoute(route=member, said=said, words=words)


def route_fields(entry) -> dict:
    """A route as the keys it takes on an envelope.

    The serializer's half of :func:`route`, stated here rather than there
    for the reason :func:`fields` gives: "there is nothing here" has one
    spelling, and it is not each writer's to choose.
    """
    out: dict = {"route": str(entry.route)}
    if entry.said:
        out["said"] = dict(entry.said)
    if entry.words:
        out["words"] = dict(entry.words)
    return out


def route_entry(entry: Mapping) -> "GapRoute | None":
    """A route read back off an envelope — the reading half of
    :func:`route_fields`.

    Nothing, rather than a raw token, where this build cannot name the
    route: :class:`themis.types.GapRoute` holds a :class:`Route` because
    the identity is the point of the field, and a schema whose ``route``
    is a closed enum is what makes the case unreachable for an envelope
    that validates.
    """
    member = taken(entry)
    if member is None:
        return None
    return GapRoute(
        route=member,
        said=dict(entry.get("said") or {}),
        words=dict(entry.get("words") or {}),
    )


def taken(entry) -> "Route | None":
    """Which route this entry is, off either shape.

    The identity three passes need and used to recover from the rendered
    text — by rebuilding the string to compare it, by searching it for
    three substrings, and, on the third, by wording a sentence so those
    substrings would not appear in it.

    A route from a build this one has never heard of is not one of ours to
    act on, so it answers ``None`` rather than raising: the passes that ask
    are deciding whether to WITHDRAW something, and withdrawing what you
    cannot name is worse than leaving it.
    """
    tok = entry.get("route") if isinstance(entry, Mapping) else getattr(
        entry, "route", None)
    return BY_ROUTE.get(str(tok)) if tok else None


def went(entry, lang: language.Lang | str = language.DEFAULT) -> str:
    """A way past this gap, as the sentence this reader gets."""
    member = taken(entry)
    if member is None:
        tok = entry.get("route") if isinstance(entry, Mapping) else getattr(
            entry, "route", "")
        return language.gloss({}, str(tok or ""), lang)
    if isinstance(entry, Mapping):
        values, words = entry.get("said"), entry.get("words")
    else:
        values, words = entry.said, entry.words
    return language.assemble(ROUTES[str(member)], values, words, lang)


SUPPLY: language.Words = {"zh": "补 {wanted}", "en": "supply {wanted}"}
"""The imperative a gap turns into once it is named rather than described."""


def next_steps(gaps, lang: language.Lang | str = language.DEFAULT) -> list[str]:
    """The short imperative tail, for the reader who is about to show it.

    One line per gap worth acting on, naming what would close it. This was
    a field on the report and is derived here instead, for the reason
    :class:`themis.types.DataGapReport` gives.

    It used to carry a second line per gap — "or: <the first alternative
    path>" — and that line was a copy. The alternatives belong to the gap
    and are shown with it, so a tail repeating the first one said the same
    thing twice on the surface that showed both; and on the surface that
    showed only the tail, the OTHER alternatives were unreachable. The one
    place it was not a copy is the one place it was suppressed, by a
    substring test for ``bounds_result`` that the scheduler ran to stop a
    computed interval being offered as a route to itself.
    """
    return [
        language.fill(SUPPLY, lang, wanted=wanted(gap, lang))
        for gap in gaps or ()
        if _read(gap, "severity") != GapSeverity.INFORMATIONAL
        and _read(gap, "if_provided")
    ]


def registered(need) -> Need:
    """The need by that name, or a refusal to proceed without one.

    ``Need(name)`` is the same lookup, and is not what callers use: the
    enum's ``__new__`` takes the kind and the maintainer's line as well,
    so a one-argument call is a type error before it is a lookup.
    """
    found = BY_NAME.get(str(need))
    if found is None:
        raise ValueError(
            f"unregistered need {str(need)!r}; declare it in themis.gaps "
            f"beside the others, with the kind that says which channel "
            f"repairs it and the sentence the reader is given"
        )
    return found


def missing(*, kind: MissingKind, name: str, priority: Priority, need: Need,
            observable: Observable | None = None,
            superseded_by_estimation: bool = False,
            **details) -> MissingItem:
    """One shortfall, in the one shape it takes on the envelope.

    The door. A site hands over a species and this occasion's facts and
    writes no sentence, which is what makes the sentence one author's; the
    ``gap`` is read off the species here rather than passed, so the two
    cannot contradict each other.

    The split into value slots and word slots happens now, before the
    facts are flattened for the envelope: after that a word is a bare
    token and which set it came from is exactly what the flattening loses.
    """
    species = registered(need)
    if str(species) not in SAYS:
        raise ValueError(
            f"{species} has no sentence in themis.gaps.SAYS; declare it "
            f"there, beside the species, so the reader's wording has one "
            f"author"
        )
    said, words = language.halve(details)
    return MissingItem(
        kind=kind,
        name=name,
        priority=priority,
        gap=species.gap,
        need=species,
        said=said,
        words=words,
        observable=observable,
        superseded_by_estimation=superseded_by_estimation,
    )


def item(*, target: str, need: Need, skeleton: dict | None = None,
         superseded_by_estimation: bool = False, **details
         ) -> InvestigationItem:
    """The same, for the channel that has no ``MissingItem`` to project.

    ``investigation_pusher`` builds its items from missing ones and copies
    the species across; the framing channel builds them directly. It wrote
    its own sentence for a situation ``_check_strict_framing`` also files —
    the same fact, in Chinese here and in English there, and a comment
    claiming both matched a third wording in the gap report.
    """
    species = registered(need)
    said, words = language.halve(details)
    return InvestigationItem(
        target=target,
        gap=species.gap,
        need=species,
        said=said,
        words=words,
        skeleton=skeleton,
        superseded_by_estimation=superseded_by_estimation,
    )


def fields(need, **details) -> dict:
    """A shortfall as the three keys it takes on an envelope.

    :func:`missing` and :func:`item` are the two typed doors; this is the
    same handover for the places that write a bare dict — the mediation
    arms' status blocks, and the serializer turning either dataclass back
    into JSON. Stated once because the alternative is each writer
    deciding for itself whether an absent word is a missing key or an
    empty one, and "there is nothing here" has one spelling.
    """
    said, words = language.halve(details)
    out: dict = {"need": str(registered(need))}
    if said:
        out["said"] = said
    if words:
        out["words"] = words
    return out


def carried(entry) -> "dict | None":
    """The three fields off an entry, in the shape :func:`fields` writes.

    The read direction, and the reason it exists is that two facts are
    "the same" when these three are equal — which is what a request
    grouping several asks has to decide, on either side of the
    serialization boundary. Deciding it on two rendered sentences instead
    would make it depend on the language they were rendered in.

    ``None`` when the entry carries no species, so that "nothing to say"
    and "says this" stay two answers rather than one empty one.
    """
    if isinstance(entry, Mapping):
        tok, values, words = (entry.get("need"), entry.get("said"),
                              entry.get("words"))
    else:
        tok, values, words = entry.need, entry.said, entry.words
    if not tok:
        return None
    out: dict = {"need": str(tok)}
    if values:
        out["said"] = dict(values)
    if words:
        out["words"] = dict(words)
    return out


def said(entry, lang: language.Lang | str = language.DEFAULT) -> str:
    """A shortfall, as the sentence this reader gets.

    The reader's half of :func:`missing`. Every surface that shows a gap
    calls this — or, in the browser, the twin generated from the same
    table — and none of them writes a word of it.

    Takes the item either as the dataclass or as the dict it becomes on
    the envelope: the three fields are the same three, and a reader on
    one side of the serialization boundary should not have to know which
    side it is on. An entry carrying no species at all says nothing,
    which is what lets a caller fall back on the item's name.

    A need this build has never heard of is said by its token, for the
    reason :func:`themis.language.gloss` gives, and only reachable from an
    envelope another build wrote.
    """
    if isinstance(entry, Mapping):
        tok, values, words = (entry.get("need"), entry.get("said"),
                              entry.get("words"))
    else:
        tok, values, words = entry.need, entry.said, entry.words
    if not tok:
        return ""
    template = SAYS.get(str(tok))
    if template is None:
        return language.gloss({}, str(tok), lang)
    return language.assemble(template, values, words, lang)
