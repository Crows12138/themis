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
