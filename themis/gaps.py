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

from collections.abc import Collection, Mapping, Sequence

from enum import unique

from . import language
from .types import (
    BoundsMethod,
    EnvelopeName,
    GapKind,
    GapRefKind,
    GapRoute,
    GapSentence,
    GapSeverity,
    InvestigationItem,
    MissingItem,
    MissingKind,
    Observable,
    Priority,
)


@unique
class QueryPart(language.Word, vocabulary="query_part",
                between=language.BETWEEN_ITEMS):
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
class Unnamed(language.Word, vocabulary="unnamed_thing",
              between=language.BETWEEN_ITEMS):
    """What stands in a sentence's slot where this occasion cannot name it.

    Five of these were templates rendered into the hole of another
    template, which is the shape (#410) named: a slot holds a value or a
    word, and a word rendered at the site is a word frozen into whichever
    language the site was passed. What goes in the hole here is not a
    value at all — the occasion HAS no value for it, and the placeholder
    is the sentence's own way of saying so.
    """

    POPULATION = ("population", {"zh": "<未命名>", "en": "<unnamed>"})
    SOURCE_POPULATION = ("source_population",
                         {"zh": "<源人群>", "en": "<source population>"})
    TARGET_POPULATION = ("target_population",
                         {"zh": "<目标人群>", "en": "<target population>"})
    INTERVENTION = ("intervention",
                    {"zh": "干预变量", "en": "the intervention variable"})
    OUTCOME = ("outcome", {"zh": "目标变量", "en": "the outcome variable"})


@unique
class Population(language.Word, vocabulary="described_population",
                 between=language.BETWEEN_ITEMS):
    """A population a gap can characterise where nobody has named it.

    Beside :class:`Unnamed` rather than inside it, and the line between
    them is whether the occasion HAS a value. A placeholder stands where
    it does not; these are a value — a subset the kernel picked out and
    can say exactly which one, for which no name exists to be supplied.

    ``required_data.population`` holds a NAME (the caller's, for a source
    or target population). A producer holding a characterisation instead
    of a name has nowhere to put it, so it writes prose into the name's
    slot — which is a value's slot answering a question the value cannot
    be asked, and prose is what that produces.
    """

    THE_STRATA_WITH_ONE_INSTRUMENT_ARM = (
        "the_strata_with_one_instrument_arm", {
            "zh": "条件集里目前只带一条工具臂（或一条都没有）的那些分层",
            "en": "the strata that currently carry only one arm of the "
                  "instrument, or none at all"})


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
    FEEDBACK_LOOP_NEEDS_AN_INSTRUMENT = (
        "feedback_loop_needs_an_instrument", GapKind.MISSING_IV_CANDIDATE,
        "the treatment and the outcome were declared to cause each other, "
        "which makes the treatment endogenous by construction; adjustment "
        "cannot reach it and an instrument is the route that can")
    FEEDBACK_LOOP_OUTSIDE_THE_SIMULTANEOUS_CASE = (
        "feedback_loop_outside_the_simultaneous_case",
        GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND,
        "a declared loop still reaches the outcome after the intervention, "
        "and it is not the two-equation system whose reduction has a "
        "remedy — so what fails is not the search for an estimand but the "
        "premise that the model is a DAG")
    THE_PENALTY_IS_DOING_THE_WORK = (
        "the_penalty_is_doing_the_work",
        GapKind.REGULARISATION_IS_MOVING_THE_ANSWER,
        "the bridge equation is ill-posed, so a penalty had to be added to "
        "solve it at all, and on this sample that penalty moves the answer "
        "further than sampling noise does — the number is substantially the "
        "penalty's rather than the data's")
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
        "no S-admissible adjustment set transports the effect from this "
        "source domain")
    #: The over-identified transport, refuted. Two source domains carrying
    #: the same target effect to two numbers is a falsification of at least
    #: one declared selection diagram, in the same way the Sargan test
    #: falsifies an instrument set — which is why it is not filed under a
    #: missing distribution: nothing supplied fixes a contradiction.
    TRANSPORT_SOURCES_DISAGREE = (
        "transport_sources_disagree",
        GapKind.TRANSPORT_SOURCES_DISAGREE,
        "two source domains transport the same effect to different numbers, "
        "so at least one declared selection diagram is refuted")

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
              "根本不存在",
        "en": "P(γ|δ) is undefined: in every model the graph admits, the "
              "conditioning conjunction δ has probability 0 (a validity "
              "violation, or two worlds that contradict each other), so this "
              "conditional does not exist",
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
              "可用的工具变量升级路线",
        "en": "the complete ID/IDC algorithm found it unidentifiable (no "
              "c-factor witness), and no instrument route is available "
              "either",
    },
    "no_backdoor_or_frontdoor": {
        "zh": "不存在有效的后门或前门调整",
        "en": "no valid back-door or front-door adjustment exists",
    },
    "counterfactual_not_identifiable": {
        "zh": "P(γ|δ) 经 ID*/IDC* 算法判定不可识别——存在 w-图 / 下标冲突见证"
              "（例如 PNS 的 P(y_x, y'_{{x'}}) 配一条 X→Y 直接边，或一条后门"
              "挡住了每一次条件移动）。不存在任何观测估计量",
        "en": "ID*/IDC* found P(γ|δ) unidentifiable — there is a w-graph or "
              "subscript-conflict witness (PNS's P(y_x, y'_{{x'}}) beside a "
              "direct X→Y edge, say, or a back-door that blocks every "
              "conditioning move). No observational estimand exists",
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
              "给出一个有偏的数。请测量该混杂变量，或修改因果图",
        "en": "a back-door path from treatment {treatment} (time {time}) to "
              "{outcome} is open and the measured history does not block "
              "it — sequential exchangeability fails and the g-formula would "
              "return a biased number. Measure that confounder, or change "
              "the graph",
    },
    "conditional_admg_not_identifiable": {
        "zh": "条件 general-ID（IDC）效应：条件量 P(Y|do(X), given) 在这个 "
              "ADMG 上不可识别（Rule-2 交换加 ID 递归在条件估计量上撞到了 "
              "hedge）。也不会拿边缘量顶替它",
        "en": "conditional general-ID (IDC) effect: P(Y|do(X), given) is not "
              "identifiable on this ADMG (Rule-2 exchange plus the ID "
              "recursion hit a hedge on the conditional estimand). The "
              "marginal is not substituted for it either",
    },
    "feedback_loop_needs_an_instrument": {
        "zh": "程序声明了 `{left}` 与 `{right}` 互为因果，所以 "
              "`{treatment}` 按构造就不是外生的——任何调整集都补不上，"
              "而图里也没有能推动 `{treatment}`、且只通过它影响 "
              "`{outcome}` 的变量",
        "en": "the program declares that `{left}` and `{right}` cause each "
              "other, so `{treatment}` is not exogenous by construction — "
              "no adjustment set closes that — and the graph holds nothing "
              "that moves `{treatment}` while reaching `{outcome}` only "
              "through it",
    },
    "feedback_loop_outside_the_simultaneous_case": {
        "zh": "程序声明的环 `{left}` ⇄ `{right}` 在干预 `{treatment}` "
              "之后仍能影响 `{outcome}`，而它不在处理与结果之间——两方程"
              "联立系统那条化简在这个形状上不成立，有环模型也未必定义得出"
              "这个量",
        "en": "the declared loop `{left}` <-> `{right}` can still influence "
              "`{outcome}` after `{treatment}` is set, and it is not "
              "between the treatment and the outcome — the two-equation "
              "reduction does not hold for this shape, and a cyclic model "
              "need not define this quantity at all",
    },
    "the_penalty_is_doing_the_work": {
        "zh": "bridge 方程是不适定反问题，必须加一个正则化项才解得出来；在这"
              "份数据上，这一项把答案挪动的幅度**超过了抽样噪声**——你看到的"
              "这个数，相当程度上是这个正则化项的，不是数据的",
        "en": "the bridge equation is ill-posed and needs a penalty added to "
              "be solvable at all; on this sample that penalty moves the "
              "answer **further than sampling noise does** — the number you "
              "are looking at is substantially the penalty's rather than the "
              "data's",
    },
    "admg_effect_not_identifiable": {
        "zh": "这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都"
              "到不了。若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7",
        "en": "this ADMG effect query is out of reach of ADMG back-door, "
              "front-door and Tian / Shpitser ID alike. For the Line-7 case "
              "see PHASE_2_LATENT_CHARTER.md §7",
    },
    "admg_effect_reachable_only_by_instrument": {
        "zh": "这个 ADMG 效应查询，ADMG 版后门、前门、Tian / Shpitser ID 都"
              "到不了。工具变量升级路线确实到得了它，但那条路线是带假设的。"
              "若涉及 Line-7 情形，见 PHASE_2_LATENT_CHARTER.md §7",
        "en": "this ADMG effect query is out of reach of ADMG back-door, "
              "front-door and Tian / Shpitser ID alike. The instrument "
              "upgrade route does reach it, but that route carries "
              "assumptions. For the Line-7 case see "
              "PHASE_2_LATENT_CHARTER.md §7",
    },
    # ``{detail}`` is a whole statement — the criterion that broke, said in
    # this reader's language with its own occasion's facts in it. It used to
    # be a rendered Chinese sentence beside a ``{criterion}`` hole holding
    # the machine tag, so an English reader got this frame in English, a
    # snake_case token in the parentheses, and the diagnosis in Chinese. The
    # token is still on the envelope, one level down, as the statement's own.
    "proximal_not_identifiable": {
        "zh": "P(Y|do(X)) 不可经近端识别：{detail}",
        "en": "P(Y|do(X)) is not proximally identifiable: {detail}",
    },
    "transport_not_identifiable": {
        "zh": "源人群 `{detail}` 找不到 S-可容许的调整集——在它自己声明的那张"
              "选择图下，它的效应无法迁移到目标人群。每个源各自卡在哪里，写在"
              "迁移块上",
        "en": "source population `{detail}` has no S-admissible adjustment "
              "set: under its own declared selection diagram its effect "
              "cannot be transported to the target population. Where each "
              "source got stuck is on the transport block",
    },
    "transport_sources_disagree": {
        "zh": "两个源人群把同一个目标效应迁出了不同的数，相差 {detail}。θ 是"
              "给定的、不是估出来的，所以这不是抽样噪声：你给的分布否掉了至少"
              "一张选择图。这里不报数——报其中任何一个，都是替你选了信哪一张",
        "en": "two source populations transport the same target effect to "
              "different numbers, differing by {detail}. Theta is declared "
              "rather than estimated, so this is not sampling noise: the "
              "distributions supplied refute at least one declared selection "
              "diagram. No number is reported, because reporting either one "
              "would be choosing which diagram to believe on your behalf",
    },
    "interventional_risk_not_identifiable": {
        "zh": "P(Y=1|do(X)) 在这张图上不可识别，再多观测数据也换不出它。请提供"
              "来自随机实验的 experimental_risk_treated / "
              "experimental_risk_control，或者修改因果图。{note}",
        "en": "P(Y=1|do(X)) is not identifiable on this graph, and no amount "
              "of observational data buys it. Supply "
              "experimental_risk_treated / experimental_risk_control from a "
              "randomised experiment, or change the graph. {note}",
    },
    "interventional_risk_needs_distributions": {
        "zh": "P(Y=1|do(X)) 可识别，但算不出数——它需要的分布列在旁边。请把"
              "它们补上；或者直接给出来自随机实验的 experimental_risk_treated "
              "/ experimental_risk_control，跳过它们。{note}",
        "en": "P(Y=1|do(X)) is identifiable but not computable — the "
              "distributions it needs are listed beside this. Supply them; "
              "or give experimental_risk_treated / experimental_risk_control "
              "from a randomised experiment and skip them. {note}",
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
              "effect. {note}",
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
              "对着一组根本不成其为分布的权重毫无意义",
        "en": "the instrument's conditional stratum probabilities sum to "
              "{total}, not 1. The LATE ratio is scale-free so a number still "
              "comes out, but the treatment shift the report gives is a "
              "complier share, and that is meaningless against weights that "
              "are not a distribution",
    },
    "iv_first_stage_degenerate": {
        "zh": "工具 {instrument} 推不动处理（加权后的第一阶段 ≈ 0），所以 Wald "
              "比值无定义——没有顺从者子总体可供平均。换一个、或更强的工具，"
              "才是补上这一条的办法",
        "en": "instrument {instrument} does not move the treatment (the "
              "weighted first stage is ≈ 0), so the Wald ratio is undefined — "
              "there is no complier subpopulation to average over. A "
              "different, or stronger, instrument is what fills this",
    },
    "iv_monotonicity_undeclared": {
        "zh": "有 {count} 个有效工具能到达这个效应——{candidate}——但光有工具"
              "并不能定下用哪个估计量。声明 assumptions.monotonicity 可以得到"
              "顺从者中的 Wald LATE；内核不会替你在 Wald、2SLS 和界之间做选择",
        "en": "{count} valid instrument(s) reach this effect — {candidate} — "
              "but having an instrument does not settle which estimator to "
              "use. Declaring assumptions.monotonicity buys the Wald LATE "
              "among compliers; the kernel will not choose between Wald, "
              "2SLS and bounds on your behalf",
    },
    "theta_entry_missing": {
        "zh": "Theta 中缺条目 {key}",
        "en": "Theta has no entry for {key}",
    },
    "graph_contradicts_supplied_marginal": {
        "zh": "Theta 中缺条目 {key}；theta 里有 {have}，但声明的图蕴含 "
              "{variable} ⊥ {{{extras}}} | {{{conditioning}}} 不成立，故不能用"
              "边缘量替代条件量。要么补上被要求的那个条件量，要么改图——"
              "「多给点 theta」是另一个问题的答案",
        "en": "Theta has no entry for {key}; theta does hold {have}, but the "
              "declared graph does not imply {variable} ⊥ {{{extras}}} | "
              "{{{conditioning}}}, so the marginal cannot stand in for the "
              "conditional. Supply the conditional that was demanded, or "
              "change the graph — \"more theta\" answers a different "
              "question",
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

Two slots are not values but another layer's sentence: ``proximal_not_
identifiable{detail}`` (one of seven criteria, each with its wording in
``proximal_identify``) and ``transport_not_identifiable{detail}``. Both
arrive as STATEMENTS now, which is a sentence inside a sentence and the
only shape in which the outer one stays the reader's; they used to arrive
already rendered, in whichever language their producer was thinking in,
and this paragraph counted five of them so the count would be a
measurement rather than an impression. Two of the five closed in the
place that produced them and the ``{note}`` on the three interventional-
risk species closed here.

That last one is the instrument route saying why IT could not reach the
quantity either, and one of its three forms CITES A REFUSAL. Not quotes:
a refusal already carries the species and the occasion's facts, so it is
restated as a statement rather than rendered — the same two halves one
level further down. Which is also why the separator before ``{note}``
lives in the template: what goes between two sentences is a fact about
the language, and the site that filled the hole knew one language's
answer. English wants a space there and Chinese does not.
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
    "transport_sources_disagree": {
        "zh": "一个说法：哪张选择图是错的，或者哪个源的分布报错了",
        "en": "a decision on which selection diagram is wrong, or which "
              "source's distributions were misreported",
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
    "proxy_coarsening_undeclared": {
        "zh": "把每个代理的层级分成 k 组的方案，写在 query 的 proxy_coarsening 上",
        "en": "a grouping of each proxy's levels into the k groups, on the "
              "query's proxy_coarsening",
    },
    "answer_is_a_test_not_an_effect_size": {
        "zh": "一个能把潜变量各状态分辨开的代理变量——更细的测量，或多测一"
              "个负对照",
        "en": "a proxy that separates the latent's states — a finer "
              "measurement, or one more negative control recorded beside it",
    },
    "feedback_loop_reaches_the_estimand": {
        "zh": "一个说得清这两个变量怎么互相影响的模型——按时间拆开，或者撤回这个环",
        "en": "a model that says how the two variables move each other — "
              "resolved in time, or with the loop withdrawn",
    },
    "regularisation_is_moving_the_answer": {
        "zh": "一个轻到答案不再跟着它走的正则化——或者一个小到轻正则化也解得动的基",
        "en": "a penalty light enough that the answer stops moving with it — "
              "or a basis small enough that a light one solves",
    },
    "treatment_bridge_leaves_its_range": {
        "zh": "一个装得下「处处 ≥ 1 的函数」的处理桥空间——"
              "或者那个不单靠它做除法的答案",
        "en": "a treatment-bridge span that can hold a function bounded below "
              "by one — or the answer that does not divide by it alone",
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
    # A name arrives as a name, and a characterisation as a STATEMENT —
    # the field holds either, because a producer that picked out a subset
    # rather than being handed a name has something to say and no name to
    # say it with. Said here, where the reader's language is known.
    population = _read(required, "population")
    return {
        "variables": language.listing(variables, lang),
        "population": (language.spoke(population, lang)
                       if isinstance(population, Mapping)
                       else population or language.fill(default, lang)),
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
            return language.fill(named, lang, **slots)
    return language.fill(template, lang)


#: What a route that offers an interval instead of a point accepts in
#: place of itself. Empty is "this route is not about this question's
#: interval at all" — the reading the old boolean had, kept exactly.
_NOT_A_BOUNDS_ROUTE: frozenset[BoundsMethod] = frozenset()
#: Any interval this kernel can compute for the estimand answers it.
_ANY_BOUND: frozenset[BoundsMethod] = frozenset(BoundsMethod)
#: Every bound except the one that assumes the instrument affects the
#: outcome only through the treatment. A difference rather than a list so
#: that it reads as the one exclusion it is — but the default it implies
#: is the UNSAFE direction, since a method added later joins this set
#: whatever it assumes. What makes that safe is not the spelling: a gate
#: holds this set to the assumptions the builders actually attach, so a
#: new bound that assumes exclusion turns red here rather than quietly
#: becoming an answer to the route that exists to get away from it.
_BOUNDS_THAT_DO_NOT_ASSUME_EXCLUSION: frozenset[BoundsMethod] = (
    _ANY_BOUND - {BoundsMethod.BALKE_PEARL_IV})


@unique
class Route(EnvelopeName):
    """One way past a gap, by name.

    A member is ``(token, answered_by, what it means to whoever adds the
    next one)``. These were finished sentences on the envelope, and
    :class:`themis.types.GapRoute` says what that cost; this is the name
    they were being spelled out as.

    ``answered_by`` names the bounds methods whose computed interval takes
    this route's place, and it is declared here rather than at the site for
    the reason :class:`Need`'s kind is: the scheduler asked it by searching
    the rendered sentence for ``"bounds"``, ``"Manski"`` and ``"Balke-Pearl
    bounds"``, so a route's answer depended on its wording and on the
    language it was rendered in.

    It is a SET rather than a flag because substituting an interval for a
    route is only sound when the interval does not rest on what the route
    exists to get away from. One route here is offered because the data
    refuted the exclusion restriction, and Balke-Pearl bounds assume it: a
    flag cannot hold that difference, so the pass that reads it would send
    the reader to an interval standing on the assumption just refuted. The
    flag was narrow in the other direction too, and two members said so in
    prose — a route offering an interval on a DIFFERENT question (binarise
    the dose, then Themis can bracket it) is not made redundant by bounds
    on this one. Empty means exactly that, so those notes are the type now.
    """

    answered_by: frozenset[BoundsMethod]
    says: str

    def __new__(cls, value: str, answered_by: frozenset[BoundsMethod],
                says: str) -> "Route":
        member = str.__new__(cls, value)
        member._value_ = value
        member.answered_by = answered_by
        member.says = says
        return member

    # --- take the interval this question does have ------------------------

    ACCEPT_THE_INTERVAL = (
        "accept_the_interval", _ANY_BOUND,
        "the point is out of reach; take the interval this question's "
        "fallback method brackets it with")
    BOUNDS_ALREADY_COMPUTED = (
        "bounds_already_computed", _ANY_BOUND,
        "the interval is in hand — the scheduler replaces the offer above "
        "with this once the methods have run")

    # --- change the graph, or what was measured ---------------------------

    MEASURE_THE_CONFOUNDER_TO_BREAK_THE_HEDGE = (
        "measure_the_confounder_to_break_the_hedge", _NOT_A_BOUNDS_ROUTE,
        "measure the unmeasured common cause, and the hedge that blocked "
        "identification is gone")
    MEASURE_THE_CONFOUNDER_AND_REIDENTIFY = (
        "measure_the_confounder_and_reidentify", _NOT_A_BOUNDS_ROUTE,
        "the same move where what failed was the back-door search rather "
        "than a hedge")
    RUN_AN_RCT_PAST_THE_HEDGE = (
        "run_an_rct_past_the_hedge", _NOT_A_BOUNDS_ROUTE,
        "randomise the treatment and the hedge stops mattering")
    RUN_AN_RCT_PAST_THE_BACKDOOR = (
        "run_an_rct_past_the_backdoor", _NOT_A_BOUNDS_ROUTE,
        "randomise the treatment and there is no back-door path left")
    FIND_AN_INSTRUMENT = (
        "find_an_instrument", _NOT_A_BOUNDS_ROUTE,
        "an instrument satisfying the IV conditions identifies what no "
        "adjustment set can")
    TIGHTEN_THE_IV_INTERVAL = (
        "tighten_the_iv_interval", _NOT_A_BOUNDS_ROUTE,
        "an instrument is already in hand and already gave the interval; "
        "the POINT needs one further assumption on top of it")
    TAKE_THE_INSTRUMENT_ROUTE_THE_GRAPH_OFFERS = (
        "take_the_instrument_route_the_graph_offers", _NOT_A_BOUNDS_ROUTE,
        "the distinction FIND_AN_INSTRUMENT cannot make: the graph ALREADY "
        "holds a variable that qualifies, so there is nothing to go and "
        "find and the errand is to accept what that route assumes")
    MEASURE_THE_TIME_VARYING_CONFOUNDER = (
        "measure_the_time_varying_confounder", _NOT_A_BOUNDS_ROUTE,
        "the longitudinal form of measuring the confounder, and not the "
        "same errand: what is open is a back door at ONE time point given "
        "the history, so what has to be recorded is that period's covariate "
        "and not a variable the study lacks altogether")
    FIND_A_VALID_PROXY_PAIR = (
        "find_a_valid_proxy_pair", _NOT_A_BOUNDS_ROUTE,
        "what proximal identification is short of when the model (f) "
        "criterion fails — a treatment-side and an outcome-side proxy that "
        "between them separate the states of U. An instrument is not a "
        "smaller version of this and does not stand in for it")
    MEASURE_WHAT_DIFFERS_BETWEEN_THE_POPULATIONS = (
        "measure_what_differs_between_the_populations", _NOT_A_BOUNDS_ROUTE,
        "the transport twin of measuring a confounder, and a different "
        "errand: nothing here is unmeasured in the source, and what is "
        "wanted is the covariate that makes the selection node S-admissible "
        "— recorded in BOTH populations, since one alone cannot show a "
        "difference")
    RUN_THE_STUDY_IN_THE_TARGET_POPULATION = (
        "run_the_study_in_the_target_population", _NOT_A_BOUNDS_ROUTE,
        "the transport twin of running an RCT, and the reason the generic "
        "one is wrong here: randomising in the SOURCE reproduces exactly "
        "the effect that was already refused, so where the trial is run is "
        "the whole of the remedy")

    # --- accept a different quantity --------------------------------------

    FALL_BACK_TO_CDE = (
        "fall_back_to_cde", _NOT_A_BOUNDS_ROUTE,
        "the decomposition is out of reach; the controlled direct effect "
        "is not")
    FALL_BACK_TO_THE_TOTAL_EFFECT = (
        "fall_back_to_the_total_effect", _NOT_A_BOUNDS_ROUTE,
        "ask for the total effect and do not decompose it")
    FALL_BACK_TO_A_BINARY_CONTRAST = (
        "fall_back_to_a_binary_contrast", _NOT_A_BOUNDS_ROUTE,
        "the dose-response curve is out of scope; a high-vs-low contrast "
        "is a question this kernel brackets. Offers an interval, and is "
        "answered by none of them: it is an interval on a different "
        "question, so a computed one here does not make it redundant")
    ASK_THE_MARGINAL_EFFECT = (
        "ask_the_marginal_effect", _NOT_A_BOUNDS_ROUTE,
        "drop the conditioning that opened the collider path and ask the "
        "marginal effect instead")
    ACCEPT_THE_SOURCE_ATE = (
        "accept_the_source_ate", _NOT_A_BOUNDS_ROUTE,
        "take the source population's effect as a rough transfer, knowing "
        "the extrapolation is weak")
    ASK_ONE_TREATMENT_AT_A_TIME = (
        "ask_one_treatment_at_a_time", _NOT_A_BOUNDS_ROUTE,
        "a joint intervention that is not identified says nothing about "
        "its parts: each single-treatment effect is a separate estimand "
        "with its own back door, and asking for them one at a time is the "
        "question this graph may well answer")
    ASK_THE_EFFECT_INSTEAD_OF_THE_COUNTERFACTUAL = (
        "ask_the_effect_instead_of_the_counterfactual", _NOT_A_BOUNDS_ROUTE,
        "the cross-world quantity is what failed, and no experiment "
        "supplies one — two worlds are never observed together. The "
        "interventional contrast underneath it is a different question on "
        "the same graph, and frequently identified where this is not")
    ASK_THE_UNCONDITIONAL_EFFECT = (
        "ask_the_unconditional_effect", _NOT_A_BOUNDS_ROUTE,
        "the detail-free twin of asking for the marginal effect, for the "
        "channel that knows the estimand failed but not what its atoms are "
        "called. The marginal is NOT substituted for the conditional here, "
        "which is why this is offered as a question to ask rather than "
        "taken silently")

    # --- say more about the model ------------------------------------------

    SUPPLY_A_SOURCE_FOR_THE_EDGE = (
        "supply_a_source_for_the_edge", _NOT_A_BOUNDS_ROUTE,
        "the edge is a proposal; a study or a data source turns it into "
        "evidence")
    ASK_CONDITIONALLY = (
        "ask_conditionally", _NOT_A_BOUNDS_ROUTE,
        "ask what follows IF the proposed edge holds, which is a question "
        "the proposal can answer")
    SUPPLY_THE_CONDITIONAL = (
        "supply_the_conditional", _NOT_A_BOUNDS_ROUTE,
        "the graph is accepted and the missing conditional is what stands "
        "in the way")
    DROP_THE_CONTRADICTING_EDGE = (
        "drop_the_contradicting_edge", _NOT_A_BOUNDS_ROUTE,
        "the other side of the same disagreement: keep the CPTs and take "
        "out the edge they refute")
    MAYBE_IT_IS_NOT_A_COLLIDER = (
        "maybe_it_is_not_a_collider", _NOT_A_BOUNDS_ROUTE,
        "the conditioning variable is a collider only if both are its "
        "ancestors; if one is not, the graph is what is wrong")
    MAYBE_IT_IS_NOT_A_COMMON_EFFECT = (
        "maybe_it_is_not_a_common_effect", _NOT_A_BOUNDS_ROUTE,
        "the same doubt for the selection variable")
    DECLARE_IT_A_SELECTION_NODE = (
        "declare_it_a_selection_node", _NOT_A_BOUNDS_ROUTE,
        "say the variable selects the population rather than being "
        "observed in it, and the transport route handles it")
    TREAT_THE_COLLIDER_AS_A_TARGET_POPULATION = (
        "treat_the_collider_as_a_target_population", _NOT_A_BOUNDS_ROUTE,
        "the same move for a collider in the conditioning set")
    DECLARE_THE_INTERVENTION_AN_EVENT = (
        "declare_the_intervention_an_event", _NOT_A_BOUNDS_ROUTE,
        "a one-off act with a manipulation behind it, so do(.) has "
        "something to point at")
    SPLIT_THE_INTERVENTION_IN_TWO = (
        "split_the_intervention_in_two", _NOT_A_BOUNDS_ROUTE,
        "an event that can be acted on, plus the state it leads to, "
        "handled as mediation")
    ACCEPT_THE_MIXED_ESTIMAND = (
        "accept_the_mixed_estimand", _NOT_A_BOUNDS_ROUTE,
        "declare that this question accepts an estimator mixing several "
        "versions of the intervention, and the warning is withdrawn")
    DROP_THE_OTHER_LAYER = (
        "drop_the_other_layer", _NOT_A_BOUNDS_ROUTE,
        "two identification layers were asked for and one was dispatched; "
        "asking for one at a time makes the dispatch unambiguous")

    # --- get different data -------------------------------------------------

    COLLECT_IT_NO_INTERVAL_FALLBACK = (
        "collect_it_no_interval_fallback", _NOT_A_BOUNDS_ROUTE,
        "this question has no interval to fall back on, so the data are "
        "the only way to a number")
    USE_EXPERIMENTAL_DATA_FOR_THE_VERSIONS = (
        "use_experimental_data_for_the_versions", _NOT_A_BOUNDS_ROUTE,
        "a randomisation protocol defines what the intervention was "
        "compared with, which is what the observational sample cannot say")
    USE_EXPERIMENTAL_DATA_INSTEAD_OF_SELF_REPORT = (
        "use_experimental_data_instead_of_self_report", _NOT_A_BOUNDS_ROUTE,
        "experimental assignment is not self-reported, so the measurement "
        "error goes with it")
    CROSS_CHECK_AN_EXPERIMENT = (
        "cross_check_an_experiment", _NOT_A_BOUNDS_ROUTE,
        "a randomised or quasi-experimental estimate of the same quantity "
        "is a check on this one")
    EMULATE_A_TARGET_TRIAL = (
        "emulate_a_target_trial", _NOT_A_BOUNDS_ROUTE,
        "Hernán-Robins: state the trial this analysis is imitating, then "
        "imitate it — eligibility, assignment, per-protocol analysis")
    RUN_AN_E_VALUE = (
        "run_an_e_value", _NOT_A_BOUNDS_ROUTE,
        "how strong an unmeasured confounder would have to be to explain "
        "the estimate away")
    RETEST_RELIABILITY = (
        "retest_reliability", _NOT_A_BOUNDS_ROUTE,
        "a reliability coefficient is what a measurement-error correction "
        "needs")
    REPORT_ATTENUATION_RANGE = (
        "report_attenuation_range", _NOT_A_BOUNDS_ROUTE,
        "without the coefficient, a range for it still bounds the "
        "attenuation")
    REWEIGHT_FOR_SELECTION = (
        "reweight_for_selection", _NOT_A_BOUNDS_ROUTE,
        "inverse-probability-of-selection weights rebuild the sample the "
        "selection removed")
    FIND_THE_RCT_IPD = (
        "find_the_rct_ipd", _NOT_A_BOUNDS_ROUTE,
        "individual participant data from the source trial carries the "
        "stratified conditional a published marginal does not")
    FIND_A_SUBGROUP_ANALYSIS = (
        "find_a_subgroup_analysis", _NOT_A_BOUNDS_ROUTE,
        "a meta-analysis' subgroup tables are a coarse version of the "
        "same thing")
    FIND_A_MATCHED_RCT = (
        "find_a_matched_rct", _NOT_A_BOUNDS_ROUTE,
        "one small trial on a population close to the target, paying for "
        "the match in sample size")

    # --- keep the measurement you had ---------------------------------------

    KEEP_THE_MEASURE_CONTINUOUS = (
        "keep_the_measure_continuous", _NOT_A_BOUNDS_ROUTE,
        "do not dichotomise; estimate the dose-response instead")
    REPORT_CUTPOINT_SENSITIVITY = (
        "report_cutpoint_sensitivity", _NOT_A_BOUNDS_ROUTE,
        "if it must be dichotomised, show whether the conclusion survives "
        "moving the cut")
    STRATIFY_MORE_FINELY = (
        "stratify_more_finely", _NOT_A_BOUNDS_ROUTE,
        "a dichotomised confounder leaves residual confounding inside each "
        "half; finer strata or a spline reduce it")

    # --- the fit itself, where the estimator strained on this sample --------

    COLLECT_IN_THE_SATURATED_STRATA = (
        "collect_in_the_saturated_strata", _NOT_A_BOUNDS_ROUTE,
        "the logistic saturated because those cells are thin; events in "
        "them is what un-saturates it")
    USE_A_SEPARATION_ROBUST_FIT = (
        "use_a_separation_robust_fit", _NOT_A_BOUNDS_ROUTE,
        "keep the data and change the estimator to one that has a finite "
        "solution under separation")
    KNOW_THE_BOOTSTRAP_IS_ALSO_STRAINED = (
        "know_the_bootstrap_is_also_strained", _NOT_A_BOUNDS_ROUTE,
        "the interval already on this result is the better of the two, and "
        "this says how far that goes")
    GO_BAYESIAN_WITH_A_WEAK_PRIOR = (
        "go_bayesian_with_a_weak_prior", _NOT_A_BOUNDS_ROUTE,
        "a prior is what carries cells the likelihood alone cannot")

    # --- where the arms do not overlap --------------------------------------

    TRIM_TO_THE_OVERLAP_REGION = (
        "trim_to_the_overlap_region", _NOT_A_BOUNDS_ROUTE,
        "change the population to the one the data supports, and say that "
        "is what the number is now about")
    USE_AN_OVERLAP_ROBUST_METHOD = (
        "use_an_overlap_robust_method", _NOT_A_BOUNDS_ROUTE,
        "keep the population and change the estimator to one that does not "
        "need support everywhere")
    LOOSEN_THE_ADJUSTMENT_SET = (
        "loosen_the_adjustment_set", _NOT_A_BOUNDS_ROUTE,
        "the unsupported stratum stops being one stratum under a coarser "
        "set — if a defensible one exists")
    BOUND_THE_UNSUPPORTED_REGION = (
        "bound_the_unsupported_region", _NOT_A_BOUNDS_ROUTE,
        "bracket the region with no support rather than extrapolating "
        "into it. Answered by no bound: this is an interval over a REGION, "
        "not the fallback interval for the estimand, and the computed "
        "bounds are not it")

    # --- where the instrument is weak, or refuted ---------------------------

    COLLECT_IN_THE_ONE_ARMED_STRATA = (
        "collect_in_the_one_armed_strata", _NOT_A_BOUNDS_ROUTE,
        "the strata missing an instrument arm are what the stratified Wald "
        "cannot use; observations there recover the LATE directly")
    COARSEN_THE_CONDITIONING_SET = (
        "coarsen_the_conditioning_set", _NOT_A_BOUNDS_ROUTE,
        "wider cells carry both arms — as long as the coarser set still "
        "blocks the back door from the instrument")
    ACCEPT_THE_VARIANCE_WEIGHTED_2SLS = (
        "accept_the_variance_weighted_2sls", _NOT_A_BOUNDS_ROUTE,
        "report the coefficient for what it is rather than for the LATE it "
        "is not")
    FIND_A_STRONGER_INSTRUMENT = (
        "find_a_stronger_instrument", _NOT_A_BOUNDS_ROUTE,
        "the bias is 1/F, so a higher first-stage partial correlation is "
        "the whole of the remedy")
    FIND_STRONGER_INSTRUMENTS_JOINTLY = (
        "find_stronger_instruments_jointly", _NOT_A_BOUNDS_ROUTE,
        "the over-identified twin of the one above: what is weak is the "
        "JOINT first stage, so no single instrument is the answer")
    FALL_BACK_TO_IV_BOUNDS = (
        "fall_back_to_iv_bounds", _ANY_BOUND,
        "the bounds hold whatever the first stage is, so a weak instrument "
        "costs width rather than validity")
    FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION = (
        "fall_back_to_bounds_without_exclusion", _BOUNDS_THAT_DO_NOT_ASSUME_EXCLUSION,
        "the twin for a REFUTED exclusion rather than a weak one: only the "
        "bounds that never assumed exclusion survive it, which is what "
        "its ``answered_by`` leaves out and no flag could have said")
    AR_SET_NOT_CONSTRUCTIBLE = (
        "ar_set_not_constructible", _NOT_A_BOUNDS_ROUTE,
        "the weak-identification-robust interval is the right answer here "
        "and this sample could not form one — so it is data to collect, "
        "not a block to read off this result")
    USE_THE_AR_SET = (
        "use_the_ar_set", _NOT_A_BOUNDS_ROUTE,
        "it is already computed and on this envelope; the bootstrap "
        "interval beside it is the one that is not valid")
    AR_SET_FOR_THE_JOINT_STAGE = (
        "ar_set_for_the_joint_stage", _NOT_A_BOUNDS_ROUTE,
        "the same offer where the weakness is joint and no set was computed")
    USE_THE_ROBUST_AR_SET = (
        "use_the_robust_ar_set", _NOT_A_BOUNDS_ROUTE,
        "the Stock-Wright S form, valid under weak identification AND "
        "heteroskedasticity — strictly the stronger of the two to report")
    DROP_THE_SUSPECT_INSTRUMENT = (
        "drop_the_suspect_instrument", _NOT_A_BOUNDS_ROUTE,
        "over-identification rejects the SET; a subset may still pass")
    REEXAMINE_THE_GRAPH_FOR_A_DIRECT_PATH = (
        "reexamine_the_graph_for_a_direct_path", _NOT_A_BOUNDS_ROUTE,
        "a rejected over-identification test is usually the graph being "
        "wrong rather than the sample being small")

    # --- where the declaration and the column disagree ----------------------

    FIX_THE_DATA_TO_MATCH_THE_DECLARATION = (
        "fix_the_data_to_match_the_declaration", _NOT_A_BOUNDS_ROUTE,
        "one of the two is wrong and only the reader knows which; this is "
        "the branch where the declaration was right")
    FIX_THE_DECLARATION_TO_MATCH_THE_DATA = (
        "fix_the_declaration_to_match_the_data", _NOT_A_BOUNDS_ROUTE,
        "the other branch, where what has to move is the estimand rather "
        "than the column")

    # --- where the proxy is finer than the latent it stands for -------------

    DECLARE_A_PROXY_COARSENING = (
        "declare_a_proxy_coarsening", _NOT_A_BOUNDS_ROUTE,
        "the branch where k is right and the proxy is simply finer than U; "
        "what the caller supplies is the grouping, which is a claim about "
        "the measurement and not a thing the data holds")
    RECONSIDER_THE_LATENT_CARDINALITY = (
        "reconsider_the_latent_cardinality", _NOT_A_BOUNDS_ROUTE,
        "the other branch, where the proxies showing more states than k is "
        "the evidence that k was posited too small — U is never observed, "
        "so its cardinality was always an assumption")

    # --- where only the null could be tested ---------------------------------

    ENRICH_A_PROXY_TO_GET_A_NUMBER = (
        "enrich_a_proxy_to_get_a_number", _NOT_A_BOUNDS_ROUTE,
        "what turns the test back into an estimate, and the reason it is a "
        "measurement errand and not a modelling one: the channel needs a "
        "proxy that separates the states of U, and no rearrangement of what "
        "is already recorded produces one")
    USE_A_BRIDGE_CHANNEL_FOR_MORE_THAN_TWO_ARMS = (
        "use_a_bridge_channel_for_more_than_two_arms", _NOT_A_BOUNDS_ROUTE,
        "the route that exists because the sieve regime was built: a "
        "treatment with more than two levels has no contrast for formula (5) "
        "to form, and the bridge channel answers it as a curve. Offered only "
        "where the arms are what blocked the number, since it repairs "
        "nothing about a channel that will not invert")

    # --- where the two variables were declared to move each other -----------

    NAME_AN_INSTRUMENT_FOR_THE_TREATMENT = (
        "name_an_instrument_for_the_treatment", _NOT_A_BOUNDS_ROUTE,
        "the branch the loop leaves open. A two-equation system is still "
        "identified through something that moves the treatment and reaches "
        "the outcome only through it, which is what the caller is asked "
        "for — a variable in their setting, not a distribution")
    RESOLVE_THE_LOOP_IN_TIME = (
        "resolve_the_loop_in_time", _NOT_A_BOUNDS_ROUTE,
        "the branch where the loop was never instantaneous. Once each "
        "variable carries the step it is measured at, 'they affect each "
        "other' is a set of ordinary edges between time slices and no "
        "cycle is left — which is a stronger position than any escape "
        "from one, because the effect becomes identifiable without an "
        "instrument")
    WITHDRAW_THE_DECLARED_LOOP = (
        "withdraw_the_declared_loop", _NOT_A_BOUNDS_ROUTE,
        "the branch where the loop was a hedge rather than a claim. Saying "
        "one direction dominates is a premise the reader can weigh; it is "
        "offered as a route so that it is taken deliberately, which is "
        "exactly what happened silently before this gap existed")
    NAME_A_LIGHTER_PENALTY = (
        "name_a_lighter_penalty", _NOT_A_BOUNDS_ROUTE,
        "the direct lever: λ is a field on the query, and the ladder beside "
        "the answer already says what a lighter one gives. Offered first "
        "because it is the one that costs nothing to try, and last in "
        "usefulness for the same reason — a penalty that cannot be lowered "
        "without the solve failing is the problem announcing itself")
    THIN_THE_SIEVE = (
        "thin_the_sieve", _NOT_A_BOUNDS_ROUTE,
        "the structural lever, and the one that changes what is being "
        "assumed: fewer basis functions is a smaller class for the bridge to "
        "lie in, which is both a stronger assumption and a better-posed "
        "problem. That trade is the caller's to make and cannot be made for "
        "them, since nothing in the data says which class holds the bridge")
    READ_THE_PENALTY_LADDER_AS_THE_ANSWER = (
        "read_the_penalty_ladder_as_the_answer", _NOT_A_BOUNDS_ROUTE,
        "the branch where neither lever is available and the honest answer "
        "is a range: the rungs the estimate carries ARE what this sample "
        "supports, and reporting the point alone would give a precision the "
        "problem does not have")
    WIDEN_THE_TREATMENT_BRIDGE = (
        "widen_the_treatment_bridge", _NOT_A_BOUNDS_ROUTE,
        "the structural lever for a bridge that left its own range: a "
        "reciprocal probability is at least one everywhere, and a span that "
        "cannot hold such a function will fit one that dips below zero. More "
        "columns, or a family whose shape suits a ratio, is what changes "
        "that — and more ROWS is not, which is why this is a route and not a "
        "request for data")
    READ_THE_DOUBLY_ROBUST_ANSWER_INSTEAD = (
        "read_the_doubly_robust_answer_instead", _NOT_A_BOUNDS_ROUTE,
        "the branch that costs nothing, because the number is already on the "
        "envelope: the augmented estimator does not divide by this bridge "
        "alone, so where the outcome bridge's span holds it survives a "
        "treatment bridge that has gone out of range — which is the whole "
        "reason there are two")


INSTRUMENT_CHANNEL: frozenset[Route] = frozenset({
    Route.FIND_AN_INSTRUMENT,
    Route.TAKE_THE_INSTRUMENT_ROUTE_THE_GRAPH_OFFERS,
})
"""Routes whose answer is "your way past this is an instrument".

Two of them, because whether the caller has to go and find one is a fact
about the SPECIES and the next move once an interval has actually come
out of an instrument is a fact about the RUN. A pass that knows the
second should not have to know which name the first chose — it read for
``find_an_instrument`` alone, so a species offering the other name kept a
"go and get one" reading past the point where one was in hand.
"""


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
    "take_the_instrument_route_the_graph_offers": {
        "zh": "图里已经有一个满足工具变量条件的变量——不用再去找。要做的是"
              "接受那条路自带的假设（排他性、与混杂独立），按工具变量识别",
        "en": "the graph already holds a variable meeting the IV conditions — "
              "there is nothing to go and find. What this asks for is "
              "accepting what that route assumes (exclusion, independence of "
              "the confounder) and identifying through it",
    },
    "measure_the_time_varying_confounder": {
        "zh": "有一个时点的后门在给定已测历史后仍然开着：把那一期的协变量测"
              "下来——不是整段研究缺一个变量，是缺那一期的一次记录",
        "en": "one time point's back door is still open given the measured "
              "history: record that period's covariate — not a variable the "
              "study lacks altogether, but one period's reading of it",
    },
    "find_a_valid_proxy_pair": {
        "zh": "近端识别缺的是一对代理：一个在处理侧、一个在结局侧，合起来把 U "
              "的状态分开。工具变量不是它的简化版，替不了",
        "en": "proximal identification is short of a PAIR of proxies — one on "
              "the treatment side, one on the outcome side, which between "
              "them separate U's states. An instrument is not a smaller "
              "version of this and does not stand in for it",
    },
    "measure_what_differs_between_the_populations": {
        "zh": "把让选择节点变成 S-可容许的那个协变量测下来，而且两个人群都要"
              "测——只测一边看不出差异",
        "en": "record the covariate that makes the selection node "
              "S-admissible, and record it in BOTH populations — one alone "
              "cannot show a difference",
    },
    "run_the_study_in_the_target_population": {
        "zh": "在目标人群里做这个研究。在源人群里随机化，拿到的还是刚被拒的"
              "那个效应——差别全在做在哪儿",
        "en": "run the study in the target population. Randomising in the "
              "source reproduces exactly the effect just refused — where it "
              "is run is the whole of the difference",
    },
    "ask_one_treatment_at_a_time": {
        "zh": "联合干预不可识别，不等于它的每一部分都不可识别：一次问一个处理"
              "的效应，各自有各自的后门",
        "en": "a joint intervention that is not identified says nothing about "
              "its parts: ask for one treatment's effect at a time, each with "
              "its own back door",
    },
    "ask_the_effect_instead_of_the_counterfactual": {
        "zh": "失败的是跨世界的那个量，实验也给不出来——两个世界从来不会被同时"
              "观测到。改问它底下的干预对比，那是同一张图上的另一个问题，常常"
              "是可识别的",
        "en": "what failed is the cross-world quantity, and no experiment "
              "supplies one — two worlds are never observed together. Ask "
              "instead for the interventional contrast underneath it: a "
              "different question on the same graph, and frequently "
              "identified where this is not",
    },
    "ask_the_unconditional_effect": {
        "zh": "去掉条件，问不带条件的那个效应。Themis 不会拿边缘效应替你顶上"
              "条件效应，所以这是一个要你改问法的选项，不是它替你做的事",
        "en": "drop the condition and ask for the unconditional effect. "
              "Themis does not substitute the marginal for the conditional, "
              "so this is a question to ask rather than something taken on "
              "your behalf",
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

    # --- the proxy is finer than the latent ----------------------------------
    "declare_a_proxy_coarsening": {
        "zh": "若 U 确实只有 {k} 个状态，就在 query 的 `proxy_coarsening` 里"
              "把 `{z}` 与 `{w}` 的层级各分成 {k} 组，说明哪些层级代表 U 的"
              "同一个状态",
        "en": "if U really has just {k} states, group the levels of `{z}` "
              "and `{w}` into {k} groups each on the query's "
              "`proxy_coarsening`, saying which levels stand for the same "
              "state of U"},
    "reconsider_the_latent_cardinality": {
        "zh": "若两个代理显示的状态数才是 U 真实的状态数，那要改的是 "
              "`latent_cardinality`——U 从未被观测，k 一直是个假设",
        "en": "if the states the proxies show are the states U really has, "
              "then what has to move is `latent_cardinality` — U is never "
              "observed, so k was always an assumption"},

    # --- only the null could be tested ---------------------------------------
    "enrich_a_proxy_to_get_a_number": {
        "zh": "要拿到数，需要一个能把 U 的 {k} 个状态分开的代理：给 `{z}` 换"
              "一个更细的测量，或再测一个负对照。这是去补一次测量，不是换个"
              "算法——现有的列怎么重排都变不出通道里缺的那部分信息",
        "en": "a number needs a proxy that separates U's {k} states: a finer "
              "measurement in place of `{z}`, or one more negative control "
              "recorded beside it. A measurement to go and make, not a "
              "method to switch to — no rearrangement of the columns you "
              "have holds what the channel is missing"},
    "use_a_bridge_channel_for_more_than_two_arms": {
        "zh": "`{treatment}` 有 {levels} 个层级，公式 (5) 的对比只对两臂有"
              "定义。改用 `bridge` 通道，它会把每个层级各算一次，给出一条"
              "剂量-反应曲线而不是一个对比",
        "en": "`{treatment}` has {levels} levels and formula (5)'s contrast "
              "is defined for two arms only. Ask for the `bridge` channel "
              "instead: it solves at each level and answers with a "
              "dose-response curve rather than a contrast"},

    # --- the two variables were declared to move each other -------------------
    "name_an_instrument_for_the_treatment": {
        "zh": "找一个能推动 `{treatment}`、并且只通过 `{treatment}` 影响 "
              "`{outcome}` 的变量，作为 `cause` 边加进图里——它就是这个"
              "联立系统还留着的那条路",
        "en": "find something that moves `{treatment}` and reaches "
              "`{outcome}` only through it, and add it to the graph as a "
              "`cause` edge — that is the route this simultaneous system "
              "still leaves open"},
    "resolve_the_loop_in_time": {
        "zh": "若 `{treatment}` 与 `{outcome}` 其实是一前一后地互相影响，"
              "就给两边写上时间下标、把环拆成时间片之间的普通 `cause` 边——"
              "那样它根本不是环，也就不需要工具变量",
        "en": "if `{treatment}` and `{outcome}` in fact move each other one "
              "step apart, put a time index on both and write the loop as "
              "ordinary `cause` edges between time slices — then it is not "
              "a cycle at all, and needs no instrument"},
    "withdraw_the_declared_loop": {
        "zh": "若其中一个方向其实可以忽略，就删掉这条 `feedback` 语句——"
              "这是在明说「我按单向来算」，而不是让它默默发生",
        "en": "if one direction is in fact negligible, remove the "
              "`feedback` statement — which is saying out loud that the "
              "answer is computed one-way, rather than letting that happen "
              "unsaid"},
    "name_a_lighter_penalty": {
        "zh": "在这座桥的 `ridge` 字段上给一个更小的 λ，再看这个数还动不动"
              "——答案旁边那把「正则化梯子」已经把几个 λ 下的结果都算给你了",
        "en": "name a smaller λ in this bridge's `ridge` field and see whether "
              "the number still moves — the penalty ladder beside the answer "
              "has already computed it at several"},
    "thin_the_sieve": {
        "zh": "把这座桥 `span_terms` 里的基函数个数调小：函数少一些，问题就没"
              "那么病态，代价是「bridge 落在这个空间里」这条假设变强了——"
              "这是个取舍，而数据不替你做这个取舍",
        "en": "declare fewer basis functions in this bridge's `span_terms`: a "
              "narrower span makes the problem better posed, at the cost of a "
              "stronger assumption about where the bridge lies — a trade the "
              "data does not make for you"},
    "read_the_penalty_ladder_as_the_answer": {
        "zh": "两个杠杆都动不了的时候，就把梯子上那几个数当成答案的区间来读"
              "——这份数据支持的就是这么宽，只报那个点是给了它没有的精度",
        "en": "where neither lever moves, read the ladder's rungs as the "
              "answer's range — that is what this sample supports, and the "
              "point alone would claim a precision it does not have"},
    "widen_the_treatment_bridge": {
        "zh": "把 `treatment_bridge.span_terms` 加宽，或者换一个形状更配"
              "「比值」的基函数族——倒数倾向得分处处 ≥ 1，一个装不下这种函数的"
              "空间，拟合出来就会掉到零以下。加数据不解决这个",
        "en": "widen `treatment_bridge.span_terms`, or declare a family whose "
              "shape suits a ratio — a reciprocal propensity is at least one "
              "everywhere, and a span that cannot hold such a function fits "
              "one that dips below zero. More rows do not change that"},
    "read_the_doubly_robust_answer_instead": {
        "zh": "改用 `doubly_robust`——它不单靠这座桥做除法，只要结局桥落在它"
              "声明的空间里就还站得住。那个数已经算好在信封上了，不用重跑",
        "en": "ask for `doubly_robust` instead — it does not divide by this "
              "bridge alone and survives where the outcome bridge's span "
              "holds. That number is already on the envelope; nothing has to "
              "be re-run"},
}
"""What each route says to a reader, in every language this build writes.

Beside the species for the reason :data:`SAYS` gives. The slots are this
occasion's facts and travel as :func:`themis.language.halve` splits them,
so a route naming a variable is the same route wherever it is named.
"""


ESCAPES: dict[Need, tuple[Route, ...]] = {
    # --- no estimand exists over the observed distribution ----------------
    #
    # Ten species, and until this table they shared one hard-coded trio,
    # because the routes hung on the KIND. The kind is the coarse name by
    # construction — this module's own opening paragraph says so — so
    # hanging the advice there guaranteed it could not tell a transport
    # failure from a bow arc. What made it visible is that the species
    # already knew: the same gap carrying ``transport_not_identifiable``
    # offered "find an instrument", which does not transport anything.
    Need.NO_C_FACTOR_WITNESS: (
        # Not FIND_AN_INSTRUMENT, and this species is the one that proves
        # the table is needed rather than tidier: its own sentence ends
        # "and no instrument route is available either", so the trio put
        # a gap in contradiction with itself in two adjacent fields.
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
    ),
    Need.NO_BACKDOOR_OR_FRONTDOOR: (
        # The species the old trio was written for, unchanged. A table
        # that moved every species would be a rewrite; this one is a
        # claim that the OTHER nine were being told this one's answer.
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
        Route.FIND_AN_INSTRUMENT,
    ),
    Need.COUNTERFACTUAL_NOT_IDENTIFIABLE: (
        Route.ASK_THE_EFFECT_INSTEAD_OF_THE_COUNTERFACTUAL,
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
    ),
    Need.JOINT_EFFECT_NOT_IDENTIFIABLE: (
        Route.ASK_ONE_TREATMENT_AT_A_TIME,
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
    ),
    Need.SEQUENTIAL_EXCHANGEABILITY_FAILS: (
        Route.MEASURE_THE_TIME_VARYING_CONFOUNDER,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
    ),
    Need.CONDITIONAL_ADMG_NOT_IDENTIFIABLE: (
        Route.ASK_THE_UNCONDITIONAL_EFFECT,
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
    ),
    Need.ADMG_EFFECT_NOT_IDENTIFIABLE: (
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
        Route.FIND_AN_INSTRUMENT,
    ),
    Need.ADMG_EFFECT_REACHABLE_ONLY_BY_INSTRUMENT: (
        Route.TAKE_THE_INSTRUMENT_ROUTE_THE_GRAPH_OFFERS,
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
    ),
    Need.PROXIMAL_NOT_IDENTIFIABLE: (
        Route.FIND_A_VALID_PROXY_PAIR,
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
    ),
    Need.TRANSPORT_NOT_IDENTIFIABLE: (
        Route.MEASURE_WHAT_DIFFERS_BETWEEN_THE_POPULATIONS,
        Route.RUN_THE_STUDY_IN_THE_TARGET_POPULATION,
        Route.ACCEPT_THE_SOURCE_ATE,
    ),

    # --- the structure the query names and the graph does not have --------
    #
    # Eight species whose renderer offered nothing, on a reason its own
    # docstring gave: "these range too widely for one line of advice to fit
    # them all". True of the KIND and false of every species under it —
    # which is the same finding as the trio above, arriving as silence
    # instead of as wrong advice. Three of the eight have a route that was
    # already written and simply unreachable from here.
    Need.MEDIATOR_OFF_THE_DIRECTED_PATHS: (
        Route.FALL_BACK_TO_THE_TOTAL_EFFECT,
    ),
    Need.MEDIATOR_SET_OFF_THE_DIRECTED_PATHS: (
        Route.FALL_BACK_TO_THE_TOTAL_EFFECT,
    ),
    Need.JOINT_WITH_MEDIATION_OR_TRANSPORT: (
        Route.DROP_THE_OTHER_LAYER,
    ),

    # --- an identification premise the kernel will not choose -------------
    #
    # Same shape again, same suppressed advice, same docstring reason: "one
    # sentence of generic advice would be wrong for most of them". Two of
    # these are declarations contradicting a sample, which is the pair of
    # branches FIX_THE_* was written as, and one is a first stage that does
    # not move — the one thing FIND_A_STRONGER_INSTRUMENT is about.
    Need.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE: (
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
    ),
    Need.INTERVENTIONAL_RISK_UNAVAILABLE_FOR_CELL: (
        Route.MEASURE_THE_CONFOUNDER_AND_REIDENTIFY,
        Route.RUN_AN_RCT_PAST_THE_BACKDOOR,
    ),
    Need.INTERVENTIONAL_RISKS_CONTRADICT_THE_JOINT: (
        Route.FIX_THE_DATA_TO_MATCH_THE_DECLARATION,
        Route.FIX_THE_DECLARATION_TO_MATCH_THE_DATA,
    ),
    Need.IV_STRATUM_WEIGHTS_NOT_NORMALIZED: (
        Route.FIX_THE_DATA_TO_MATCH_THE_DECLARATION,
        Route.FIX_THE_DECLARATION_TO_MATCH_THE_DATA,
    ),
    Need.IV_FIRST_STAGE_DEGENERATE: (
        Route.FIND_A_STRONGER_INSTRUMENT,
    ),
}
"""The ways past a gap that follow from the SPECIES, and nothing else.

The kind says which channel repairs a shortfall; the species says what
the shortfall was. Which route helps is a fact about the second, and it
lived against the first — so ten identification failures shared one trio
of routes written for one of them, and a reader whose effect would not
TRANSPORT was told to go and find an instrument.

What belongs here is a route the reason alone settles. A route naming
this occasion's variables is built where those names are known and is
declared in :data:`NO_SPECIES_ESCAPE` instead: the split is the one
:data:`SAYS` already draws between a sentence and its slots, and keeping
it means an entry here can be read as a claim about the species rather
than about one program.
"""


NO_SPECIES_ESCAPE: dict[Need, str] = {
    # --- the ask and the repair are the same sentence ---------------------
    #
    # A route here would restate what the species already said, and a
    # reader who has read one line does not need it back under a second
    # heading. Note what separates these from the eight above: a mediator
    # off the directed paths leaves ANOTHER question standing, and a
    # treatment vector that repeats an atom leaves the same question with
    # one character removed.
    Need.ATOM_NOT_IN_GRAPH: (
        "the sentence names the atom and the instantiated set it is absent "
        "from; adding it or correcting the query is the whole repair, and "
        "a route would be that sentence twice"
    ),
    Need.GIVEN_VIOLATES_BACKDOOR: (
        "the sentence lists the offending atoms, and taking them out of "
        "identify.given is the repair it already describes"
    ),
    Need.PATH_COEFFICIENT_UNDECLARED: (
        "the ask IS the repair — this edge's coefficient, declared. There "
        "is no second way past it and no different quantity to accept"
    ),
    Need.DUPLICATE_TREATMENT_ATOM: (
        "a repeated atom in the treatment vector is a defect in the "
        "program, not a shortfall in the data; the sentence names it and "
        "removing it restores the same question"
    ),
    Need.CONDITIONING_EVENT_HAS_PROBABILITY_ZERO: (
        "no data repairs it: the graph admits no model in which the "
        "conjunction occurs, so what has to move is the question, and "
        "which part of it is not something the kernel can choose"
    ),
    Need.INTERVENTIONAL_RISK_NEEDS_DISTRIBUTIONS: (
        "the sentence already carries both branches — supply the "
        "distributions the formula is computed from, or an experimental "
        "risk that skips them"
    ),
    Need.UNIT_OBSERVATION_MISSING: (
        "the sentence says what abduction needs and why a distribution "
        "over units does not stand in; there is no route past a reading "
        "this unit does not have"
    ),

    # --- naming one would be the kernel choosing after saying it would not
    Need.IV_MONOTONICITY_UNDECLARED: (
        "the species exists to say that Wald, 2SLS and bounds are the "
        "caller's choice among three. Offering one of them as THE route "
        "would make the choice the sentence declines to make"
    ),
    Need.TRANSPORT_SOURCES_DISAGREE: (
        "a falsification rather than a shortfall: the reader supplied too "
        "much, one declared selection diagram has to be withdrawn, and "
        "which one is not a thing the kernel is in a position to decide"
    ),

    # --- the routes exist and name this occasion's variables --------------
    #
    # Not an absence. These species have routes and the routes carry the
    # program's own names, so they are built where those names are known —
    # the split this table's docstring draws, and the same one SAYS draws
    # between a sentence and its slots.
    Need.THETA_ENTRY_MISSING: (
        "the choice between an interval offer and collecting the "
        "distribution is made by QUERY KIND, not by species, and the "
        "surviving route names the distribution asked for"
    ),
    Need.QUERY_BOUND_ATOM_UNRESOLVED: (
        "same channel as theta_entry_missing: an occasion fact chooses "
        "the route and the route names the ask"
    ),
    Need.COUNTERFACTUAL_BOUND_NEEDS_ENTRY: (
        "same channel as theta_entry_missing"
    ),
    Need.IV_WALD_LATE_NEEDS_ENTRY: (
        "same channel as theta_entry_missing"
    ),
    Need.IV_WALD_LATE_NEEDS_ENTRY_IN_STRATUM: (
        "same channel as theta_entry_missing"
    ),
    Need.GRAPH_CONTRADICTS_SUPPLIED_MARGINAL: (
        "its two routes are the two sides of one disagreement and each "
        "names the edge or the conditional at issue"
    ),
    Need.FEEDBACK_LOOP_NEEDS_AN_INSTRUMENT: (
        "its three routes name the loop's two variables, which the site "
        "reads off the item and this table cannot"
    ),
    Need.FEEDBACK_LOOP_OUTSIDE_THE_SIMULTANEOUS_CASE: (
        "the same two of those three, named the same way"
    ),

    # --- raised on another channel altogether -----------------------------
    Need.FRAMING_FIELDS_UNFILLED: (
        "framing notes fire on query kinds that raise no investigation "
        "item at all, so the note rather than the item is the one source "
        "that sees every case — the reason its renderer is _RaisedElsewhere"
    ),
    Need.THE_PENALTY_IS_DOING_THE_WORK: (
        "not an item species: it is raised beside a number, and its routes "
        "are built where the penalty ladder is"
    ),
}
"""Species that declare no route here, and why each does not.

Declared rather than omitted, for the reason
:data:`themis.output.data_gap_report.GAP_KINDS_WITH_NO_PRODUCER` is: an
entry saying "not here, and here is why" is checkable, and a missing one
cannot be told from an oversight. Two different sentences appear —
nothing repairs this reason, and the routes for it name variables only
the site knows — and they are different claims, so each entry says which
it is making.
"""


def _bind_escapes() -> None:
    """Every species is on exactly one of the two tables.

    Both directions are defects. A species on neither is one whose reader
    gets whatever advice the renderer happens to hold, which is the state
    this table was built to end. A species on both is two authors for one
    answer, and the one that wins depends on a lookup order.
    """
    unplaced = sorted(
        str(n) for n in Need
        if n not in ESCAPES and n not in NO_SPECIES_ESCAPE
    )
    if unplaced:
        raise ValueError(
            f"no escape declared for {unplaced}; a species names what a "
            f"query is short of, so what would repair it is settled beside "
            f"the species or declared absent in gaps.NO_SPECIES_ESCAPE"
        )
    both = sorted(str(n) for n in ESCAPES if n in NO_SPECIES_ESCAPE)
    if both:
        raise ValueError(
            f"{both} declare both routes and a reason for having none; "
            f"which the reader sees would depend on lookup order"
        )
    empty = sorted(str(n) for n, r in ESCAPES.items() if not r)
    if empty:
        raise ValueError(
            f"{empty} declare an empty route tuple; an absence that says "
            f"nothing is the one gaps.NO_SPECIES_ESCAPE exists to name"
        )


_bind_escapes()


def escapes(need) -> tuple[GapRoute, ...]:
    """The routes this species settles, ready for a gap's field.

    Empty where :data:`NO_SPECIES_ESCAPE` accounts for the species, so a
    caller adding its own occasion-named routes can concatenate without
    asking which table the species is on.
    """
    member = BY_NAME.get(str(need))
    if member is None:
        raise ValueError(
            f"{need!r} is not a species in themis.gaps.Need; what a query "
            f"is short of is named there before it is answered"
        )
    return tuple(route(r) for r in ESCAPES.get(member, ()))


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


def past_the_bounds_in_hand(
    offered: "Sequence[GapRoute]",
    computed: "Collection[BoundsMethod]",
    *,
    delivered_nothing: bool = False,
    blocking: bool = False,
) -> "tuple[GapRoute, ...] | None":
    """The ways past a gap, once you know which intervals actually came out.

    ``None`` where nothing changes, so a caller can keep what it has.

    A route that points at an interval is a promise, and a promise has
    three fates. One of the intervals in hand is one this route ACCEPTS →
    the promise is already kept, and the route becomes a pointer naming
    exactly those. Intervals came out and this route accepts none of them
    → the promise is still open, and it stays: replacing it would answer
    the reader with a bound resting on the very assumption the route was
    handed out to escape. Nothing came out at all → what happens depends
    on whether anyone tried, which is ``delivered_nothing``; a promise
    nothing delivered is withdrawn, a promise nobody tested is left alone.

    Two doors add ways past a gap — the pass that revises a report after
    identification, and the estimation layer filing what it found in the
    data — and only one of them used to make this judgement. It is not a
    judgement about either door: it needs which methods a route accepts
    (:attr:`Route.answered_by`) and which methods produced an interval,
    and both are facts about the answer rather than about the shape the
    report is being carried in at the time. So it lives beside the routes,
    and each door hands it what it holds.

    ``blocking`` is the one asymmetry, and it is about the READER: a gap
    that stops the answer, offering no interval of its own, gets the
    generic pointer put FIRST, because a surface showing one route should
    show the fallback that already exists ahead of "run a trial".
    """
    taken = tuple(computed)

    def _in_hand(which: "Route") -> "GapRoute | None":
        accepted = [str(m) for m in taken if m in which.answered_by]
        if not accepted:
            return None
        return route(Route.BOUNDS_ALREADY_COMPUTED,
                     methods=", ".join(accepted))

    rewritten: list = []
    changed = False
    promised = False
    for alt in offered:
        if not alt.route.answered_by:
            rewritten.append(alt)
            continue
        promised = True
        kept = _in_hand(alt.route)
        if kept is not None:
            if kept not in rewritten:
                rewritten.append(kept)
            changed = True
        elif taken or not delivered_nothing:
            rewritten.append(alt)
        else:
            changed = True

    if blocking and taken and not promised:
        pointer = _in_hand(Route.BOUNDS_ALREADY_COMPUTED)
        if pointer is not None and pointer not in rewritten:
            rewritten.insert(0, pointer)
            changed = True

    return tuple(rewritten) if changed else None


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


IF_PROVIDED: dict[str, language.Words] = {
    "missing_distribution": {"zh": "可给点估计", "en": "a point estimate"},
    # One sentence for the species, so it has to hold for both of its
    # occasions: a richer proxy buys a contrast and the bridge channel buys a
    # curve, and what those have in common is a SIZE where there was only a
    # yes/no.
    "answer_is_a_test_not_an_effect_size": {
        "zh": "可给出效应有多大，而不只是有没有",
        "en": "a size for the effect, rather than only whether there is one"},
    "missing_structural_input": {
        "zh": "该查询可继续走到点估计",
        "en": "this query can carry on to a point estimate"},
    "missing_unit_observation": {
        "zh": "该查询可继续走到点估计",
        "en": "this query can carry on to a point estimate"},
    "missing_assumption": {
        "zh": "该识别路径可继续走到点估计",
        "en": "this identification route can carry on to a point estimate"},
    "unidentifiable_no_admissible_set": {
        "zh": "可给出识别公式 + 后续点估计",
        "en": "an identification formula, and a point estimate after it"},
    "graph_theta_independence_mismatch": {
        "zh": "可给点估计（在解决图与 CPT 矛盾后）",
        "en": "a point estimate, once the graph and the CPTs stop "
              "contradicting each other"},
    "missing_mediator_data": {
        "zh": "可给 NDE / NIE / TE 数值分解",
        "en": "a numeric NDE / NIE / TE decomposition"},
    "transport_target_distribution_unknown": {
        "zh": "可给目标人群的 transport-adjusted ATE 点估计",
        "en": "a transport-adjusted ATE point estimate for the target "
              "population"},
    "transport_source_conditional_unknown": {
        "zh": "可给目标人群的 transport-adjusted ATE 点估计",
        "en": "a transport-adjusted ATE point estimate for the target "
              "population"},
    "unmeasured_confounder_risk": {
        "zh": "若怀疑某 latent 共因，添加 bidirected 边；Themis 会改走 "
              "ADMG-aware（Tian / front-door / IV）识别策略并报对应的 "
              "structural gap",
        "en": "if you suspect a latent common cause, add a bidirected edge; "
              "Themis will switch to an ADMG-aware identification strategy "
              "(Tian / front-door / IV) and report the structural gap that "
              "goes with it"},
    "unverified_proposal_edge_on_query_path": {
        "zh": "可换成证据支持的边或外部文献的引用",
        "en": "replace it with an edge evidence supports, or with a citation "
              "to the literature"},
    "ambiguous_variable_definition": {
        "zh": "变量框架化后，下游结果（点估计 / bounds）的语义才确定 —— 用户能"
              "判断 'P(Y|X)' 到底说的是哪段时间窗 / 哪种测量",
        "en": "once the variable is framed, what the downstream result (a "
              "point, an interval) means is settled — the reader can tell "
              "which time window and which measurement 'P(Y|X)' is about"},
    "dichotomized_continuous_measure": {
        "zh": "若能拿到未二分的连续原始测量，可改走 dose-response 估计"
              "（LinearDML / DRLearner，Themis Phase 13/14），保留剂量-反应"
              "曲线并避免任意切点",
        "en": "given the original continuous measurement before it was cut, "
              "the dose-response route is available instead (LinearDML / "
              "DRLearner, Themis Phase 13/14), which keeps the "
              "dose-response curve and needs no arbitrary cutpoint"},
    "dose_response_data_required": {
        "zh": "数据齐了之后，去 EconML / DoubleML / GAM 拟合曲线 —— Themis "
              "不在 estimator 这一步参与",
        "en": "once the data is complete, fit the curve in EconML / "
              "DoubleML / GAM — Themis takes no part in that step"},
    "measurement_error_concern": {
        "zh": "若拿到 (a) 被误分类离散结局**或二值暴露**的**验证过混淆矩阵**"
              "（Se/Sp 或整张 confusion matrix），可经 "
              "estimate(misclassification=...) 逐后门层矩阵求逆去衰减；或 (b) "
              "连续暴露**或连续混杂**的已知经典加性误差方差 σ²_u（重复测量 "
              "test-retest / 验证子样本），可经 "
              "estimate(measurement_error={{<暴露或混杂名>: "
              "{{error_variance}}}}) 用 regression calibration 去偏（误测混杂"
              "纠正残差混淆）——误差结构若不是经典型就要说出来，structure: "
              "berkson 要到的是精度代价，而不是一条会把本来就对的数改错的校正；"
              "要的系数若在 logistic 这类非线性结局模型里，"
              "同一入口加一句 outcome_model 就改走 SIMEX 模拟外推，因为矩量"
              "校正是关于线性结局的恒等式，在二值结局上它去衰减的是线性概率"
              "斜率而 SIMEX 去衰减的是对数优势比，是两个量不是一个量的两种"
              "算法；连续结局的 σ²_v 同一入口给出的是精度代价而非校正，"
              "因为它本就不偏；或 (c) "
              "gold-standard 亚样本（如 BP 用 ABPM、sodium 用 24h 尿钠）做校准",
        "en": "given (a) a **validated confusion matrix** for the "
              "misclassified discrete outcome **or binary exposure** (Se/Sp, "
              "or the whole matrix), the attenuation can be undone through "
              "estimate(misclassification=...), inverting within each "
              "back-door stratum; or (b) a known classical additive error "
              "variance σ²_u for a continuous exposure **or continuous "
              "confounder** (test-retest repeats, a validation subsample), "
              "which debiases through "
              "estimate(measurement_error={{<exposure or confounder>: "
              "{{error_variance}}}}) with regression calibration (a "
              "mismeasured confounder has its residual confounding "
              "corrected) — say which STRUCTURE the error has if it is not "
              "the classical one, because structure: berkson asks for the "
              "precision cost instead of a correction that would move a "
              "number already right; and if the wanted coefficient lives in a "
              "nonlinear outcome model, one more key on the same entry "
              "point, outcome_model, routes to SIMEX instead: the moment "
              "correction is an identity about a LINEAR outcome, so on a "
              "binary one it de-attenuates the linear-probability slope "
              "while SIMEX de-attenuates the log-odds ratio, which are two "
              "quantities rather than two computations of one "
              "— for a continuous outcome the same entry point gives the "
              "precision cost rather than a correction, because there is no "
              "bias to correct; or (c) a gold-standard subsample to "
              "calibrate against (ABPM for blood pressure, 24-hour urinary "
              "sodium for salt)"},
    "collider_conditioning_opens_backdoor": {
        "zh": "从 `given` 移除 `{collider}` —— 如果你真的想问 \"在 "
              "`{collider}` 子群上的效应\"，需要单独的 transport / "
              "stratified analysis（先分层再估计），不能直接做条件查询",
        "en": "drop `{collider}` from `given` — if the effect **within the "
              "`{collider}` subgroup** is really the question, it needs a "
              "transport or a stratified analysis of its own (stratify "
              "first, estimate second) rather than a conditional query"},
    "selection_on_collider_opens_path": {
        "zh": "补充未被 `{collider}` 限制的对照样本（覆盖 "
              "{collider}=¬{value} 的受试者），把全样本作为分析对象 —— 而不是"
              "只用 `{collider}={value}` 子样本",
        "en": "add the controls that `{collider}` excluded (subjects with "
              "{collider}=¬{value}) and analyse the whole sample rather than "
              "the `{collider}={value}` subsample alone"},
    "ill_defined_intervention_versions": {
        "zh": "在 `{intervention}` 的 VariableDeclaration 上加 `time_window`"
              "（说明 \"持续多长时间 / 在哪个时点被视为该状态\"），并在 "
              "program.extensions.ambiguities 里加 "
              "`ill_defined_intervention` 条目，说明你打算把哪一种具体的 "
              "manipulation（如生活方式 / 用药 / 手术 / RCT 随机化）作为 "
              "do(.) 的 well-defined intervention 等价物",
        "en": "add a `time_window` to `{intervention}`'s "
              "VariableDeclaration (saying \"for how long / at which point "
              "it counts as being in that state\"), and add an "
              "`ill_defined_intervention` entry under "
              "program.extensions.ambiguities naming which concrete "
              "manipulation (lifestyle / medication / surgery / RCT "
              "randomization) you mean to stand in for do(.) as the "
              "well-defined intervention"},
    "unattempted_layer_due_to_dispatch_conflict": {
        "zh": "拆成两个 query，各自只声明一层：一个带 {won}，一个带 {lost}",
        "en": "split it into two queries, each declaring one layer: one with "
              "{won}, one with {lost}"},
    "iv_estimand_fallback_to_linear": {
        "zh": "分层 Wald 就能跑起来，报出来的量会变成顺从者中的效应，"
              "也就是这个工具真正识别的那个估计量",
        "en": "the stratified Wald becomes available, and what gets reported "
              "turns into the effect among compliers — the estimand this "
              "instrument actually identifies"},
    "proxy_coarsening_undeclared": {
        "zh": "公式 (5) 要反演的那个 k×k 通道就存在了，近端 ATE 能算出来；"
              "分组会作为**你的选择**进假设台账，因为换一个分组就是另一个数",
        "en": "the k×k channel formula (5) inverts exists, so the proximal "
              "ATE can be computed; the grouping goes into the assumption "
              "ledger as **your** choice, because a different grouping is a "
              "different number"},
    "missing_iv_candidate": {
        "zh": "工具变量把联立系统重新变成可识别的：报出来的是 `{outcome}` "
              "那条方程里 `{treatment}` 的结构系数——不是均衡下的总效应，"
              "而且它靠的是线性假设，这条会进假设台账",
        "en": "an instrument makes the simultaneous system identified "
              "again: what gets reported is the structural coefficient of "
              "`{treatment}` in the `{outcome}` equation — not an "
              "equilibrium total effect — and it rests on linearity, which "
              "goes into the assumption ledger"},
    "feedback_loop_reaches_the_estimand": {
        "zh": "把这两个变量之间的关系说清楚之后，这个问题才有一个确定的量"
              "可问：拆成时间片就回到普通的 DAG，撤回这个环就是明说按单向算",
        "en": "once the relation between the two variables is settled there "
              "is a definite quantity to ask about: resolved in time it is "
              "an ordinary DAG again, and withdrawn it is a one-way answer "
              "computed on purpose"},
}
"""What having the missing thing would buy, by species.

The sentence ``if_provided`` used to carry, in the language whoever built
the report happened to pass. It was never an occasion's fact: 21 producers
wrote it from 17 templates, and every species either always carried one or
never did, with no producer disagreeing — so it was a table the kernel
already had, told one row at a time.

Partial on purpose, and :data:`NOTHING_FILLS` is the other half: a species
absent from BOTH is a species somebody stopped short of answering for, and
the two together are what makes that visible.
"""


NOTHING_FILLS: dict[str, str] = {
    "answer_is_bounds_not_point_estimate":
        "the interval IS the answer; there is no thing to supply that turns "
        "it into a point",
    "graph_learned_from_data":
        "a provenance note about the graph in hand, not a shortfall — what "
        "would change it is a different graph, not more of this one",
    "low_confidence_input_data":
        "the same, one layer down: it says how much to trust what was "
        "supplied, and supplying more of it does not raise that",
    "llm_declared_ambiguity":
        "the caller said the question is ambiguous; only the caller can "
        "un-say it, and no data does",
    "front_door_identification_assumption_required":
        "an assumption the reader accepts or does not — data cannot settle "
        "it, which is the whole reason it is stated rather than checked",
    "iv_identification_assumption_required":
        "the same, for the IV conditions",
    "mediation_identification_assumption_required":
        "the same, for sequential ignorability",
    "transport_identification_assumption_required":
        "the same, for the transportability conditions",
    "counterfactual_identification_assumption_required":
        "the same, for the counterfactual's cross-world premises",
    "declared_type_data_mismatch":
        "the declaration and the column disagree, so what closes it is "
        "changing one of the two — the routes say which, and neither is a "
        "thing to go and collect",
    "regularisation_is_moving_the_answer":
        "an ill-posed problem is not short of data — it is one where the "
        "inverse amplifies whatever data there is; what changes this line is "
        "a lighter penalty, a smaller sieve, or reading the ladder as the "
        "answer, and none of the three is a thing to go and collect",
    "treatment_bridge_leaves_its_range":
        "a declared span that cannot hold a function bounded below by one "
        "will not come to hold one with more rows in it; what changes this "
        "line is a different span or a different estimator, and neither is a "
        "thing to go and collect",
    "propensity_overlap_violation":
        "no amount of the SAME data adds support where there is none; the "
        "routes are a different population, a different estimator, or an "
        "interval",
    "outcome_model_quasi_separation":
        "the twin on the outcome side. More rows in the thin cells is one "
        "of the routes, not a thing this gap is waiting on",
    "weak_iv_instrument":
        "more of this instrument does not make it stronger; a stronger one "
        "is a different instrument, which is a route",
    "overidentification_rejected":
        "a falsification. The data refuted the instrument set, and more of "
        "the same data refutes it again",
    "transport_sources_disagree":
        "a falsification too, and of declarations rather than of data: the "
        "same distributions carried through two selection diagrams give two "
        "answers to one question, and supplying them again gives the same "
        "two",
    "missing_population_distribution":
        "the same",
}
"""Why nothing supplied would change these species, for whoever adds the next.

Half a table reads exactly like a whole one — that is (325), and it is why
this exists rather than :data:`IF_PROVIDED` simply not having the row. A
species that belongs in neither is one nobody has answered the question
for, and the gate can see that only if "nothing does" is something you
have to write down.

Not a reader's sentence, and never rendered: the reader's fact is that the
gap has no such line, which they learn by not being told one.
"""


@unique
class Sentence(EnvelopeName):
    """One statement a gap's description is made of, by name.

    A member is ``(token, what it means to whoever adds the next one)``.
    These were prose on the envelope — 40 places wrote one, four of them
    assembling a paragraph out of two to five optional pieces — and
    :class:`themis.types.DataGap` says what that cost.

    **Why a gap has a LIST of these and a refusal has one.** A refusal is
    one sentence about one thing that failed. A gap's description is a
    paragraph: which pieces it has depends on what this occasion knows —
    whether the discovery run recorded an α, how many methods bracketed
    the answer, whether the second overidentification test was computed.
    A species per combination would be a vocabulary of products; a list of
    species is the same statement, said once each.

    **And why the pieces are species rather than a rendered string.** Four
    sentences here used to be built by filling one template's hole with
    ANOTHER template's rendered text — a mediator clause, a caller's
    rationale, a displacement reason, a confidence set. A slot holds a
    value or a word (#410); a sentence in one is a rendering that had to
    happen in the kernel, in whichever language the builder was passed.
    """

    says: str

    def __new__(cls, value: str, says: str) -> "Sentence":
        member = str.__new__(cls, value)
        member._value_ = value
        member.says = says
        return member


    # --- an edge on the route was never verified -------------------------

    THE_EDGE_WAS_LEARNED_BY_DISCOVERY = (
        "the_edge_was_learned_by_discovery",
        "an edge on the route came out of a discovery algorithm, so the "
        "answer rests on that algorithm's assumptions")
    THE_EDGE_IS_AN_LLM_PROPOSAL = (
        "the_edge_is_an_llm_proposal",
        "the other way an edge arrives unverified: a caller's model proposed "
        "it, so answering restates the hypothesis rather than checking it")
    THE_EDGE_SURVIVED_THIS_SHARE_OF_RESAMPLES = (
        "the_edge_survived_this_share_of_resamples",
        "how stable the learned edge was. Its own statement rather than a "
        "clause glued to the one above, because it is there only when the "
        "discovery run recorded a stability")

    # --- premises the reader accepts or does not — no data settles them ---

    IV_RESTS_ON_THIS_ASSUMPTION = (
        "iv_rests_on_this_assumption",
        "the instrument's premises")
    FRONT_DOOR_RESTS_ON_FOUR_PREMISES = (
        "front_door_rests_on_four_premises",
        "the same, for Pearl's front-door criterion")
    THE_COUNTERFACTUAL_RESTS_ON_CROSS_WORLD_PREMISES = (
        "the_counterfactual_rests_on_cross_world_premises",
        "the same, one rung up, where the premises join two worlds")
    TRANSPORT_RESTS_ON_S_ADMISSIBILITY = (
        "transport_rests_on_s_admissibility",
        "the same, for carrying an estimate to another population")
    MEDIATION_IS_IDENTIFIABLE_FOR_A_MEDIATOR = (
        "mediation_is_identifiable_for_a_mediator",
        "sequential ignorability, for a decomposition through one mediator. "
        "Two members rather than one with a hole, because what went in that "
        "hole was another sentence — a slot holds a value or a word, and a "
        "sentence in one is a rendering the kernel had to do first")
    MEDIATION_IS_IDENTIFIABLE_FOR_A_MEDIATOR_BLOCK = (
        "mediation_is_identifiable_for_a_mediator_block",
        "and the same where the mediators are decomposed as one whole")

    # --- what the caller said about their own question -------------------

    THE_CALLER_FLAGGED_AN_UNCERTAINTY = (
        "the_caller_flagged_an_uncertainty",
        "the caller's model said the question is ambiguous and left it there")
    THE_CALLER_FLAGGED_AN_UNCERTAINTY_AND_SAID_WHY = (
        "the_caller_flagged_an_uncertainty_and_said_why",
        "and the same with the caller's own reason in the hole. Their words, "
        "not the kernel's, which is why it is a slot and not part of the "
        "text")
    THE_COMPOSITE_CONFIDENCE_IS_BELOW_THE_THRESHOLD = (
        "the_composite_confidence_is_below_the_threshold",
        "how far the inputs are trusted, where that is not far")
    THE_VARIABLE_HAS_NO_OPERATIONAL_DEFINITION = (
        "the_variable_has_no_operational_definition",
        "a predicate nobody has said how to measure")

    # --- the answer is an interval, and which intervals they are ---------

    THE_ANSWER_IS_AN_INTERVAL_NOT_A_POINT = (
        "the_answer_is_an_interval_not_a_point",
        "the headline of the disclosure a bounds answer carries")
    SEVERAL_INTERVALS_BOUND_THE_SAME_QUANTITY = (
        "several_intervals_bound_the_same_quantity",
        "how many there are, where more than one method bracketed it. The "
        "rows used to be rendered into a hole in this sentence, one text "
        "built out of N others; they are their own statements now")
    ONE_INTERVAL_AND_WHAT_IT_RESTS_ON = (
        "one_interval_and_what_it_rests_on",
        "one bracketing method and its assumptions — one statement per row, "
        "whether there is one row or five")
    ONE_INTERVAL_THAT_RESTS_ON_NOTHING = (
        "one_interval_that_rests_on_nothing",
        "and the same for a method that assumes nothing beyond the data")
    AND_THAT_INTERVAL_IS_UNINFORMATIVE = (
        "and_that_interval_is_uninformative",
        "the row above brackets the whole range, which is a real answer and "
        "not a failure — it says the assumptions rule nothing out")
    CHOOSE_BY_WHICH_ASSUMPTIONS_YOU_ACCEPT = (
        "choose_by_which_assumptions_you_accept",
        "why several intervals are not to be intersected — the tail of the "
        "several-rows disclosure")

    # --- the graph was learned rather than declared ----------------------

    THE_GRAPH_WAS_LEARNED_BY_AN_ALGORITHM = (
        "the_graph_was_learned_by_an_algorithm",
        "the disclosure a discovered DAG carries")
    DISCOVERY_USED_THIS_SIGNIFICANCE_THRESHOLD = (
        "discovery_used_this_significance_threshold",
        "the α the run used, where the metadata recorded one")
    DISCOVERY_RAN_ON_THIS_MANY_ROWS = (
        "discovery_ran_on_this_many_rows",
        "and how many rows it had")
    A_LEARNED_GRAPH_INHERITS_THE_ALGORITHMS_ASSUMPTIONS = (
        "a_learned_graph_inherits_the_algorithms_assumptions",
        "which assumptions come with which algorithm")
    THE_ALGORITHMS_ASSUMPTIONS_WERE_VIOLATED_ON_THIS_DATA = (
        "the_algorithms_assumptions_were_violated_on_this_data",
        "and where the run itself found them broken. The leading space this "
        "text used to carry was the seam between two statements, which is "
        "the reader's to supply and not the sentence's")

    # --- what the graph does not say -------------------------------------

    THE_DAG_DECLARES_NO_LATENT_COMMON_CAUSE = (
        "the_dag_declares_no_latent_common_cause",
        "back-door adjustment assumes the listed confounders are all of them")
    TIAN_FOUND_A_HEDGE = (
        "tian_found_a_hedge",
        "identification failed on a c-component hedge — a latent common "
        "cause no observed variable screens off")
    THE_IDENTIFICATION_ROUTE_FAILED = (
        "the_identification_route_failed",
        "and the general form, where the reason comes from the request that "
        "raised it")
    THE_GRAPH_AND_THE_CPTS_DISAGREE = (
        "the_graph_and_the_cpts_disagree",
        "the two things the caller supplied contradict each other, which no "
        "amount of further data settles")
    THE_SOURCE_DOMAINS_CONTRADICT_EACH_OTHER = (
        "the_source_domains_contradict_each_other",
        "the same shape one level up: two declared selection diagrams carry "
        "one target quantity to two numbers, so the declarations are what "
        "the data refuted")

    # --- what was not measured, or was measured badly --------------------

    A_VARIABLE_DECLARES_A_NOISY_MEASUREMENT = (
        "a_variable_declares_a_noisy_measurement",
        "the longest sentence here, and the one a reader most needs: what "
        "the numeric layer can and cannot undo about measurement error")
    A_CONTINUOUS_MEASURE_WAS_CUT_IN_TWO = (
        "a_continuous_measure_was_cut_in_two",
        "a continuous quantity dichotomized at a cutpoint, and what that "
        "costs")
    A_STRUCTURAL_INPUT_IS_MISSING = (
        "a_structural_input_is_missing",
        "the estimator asked for something the program does not carry")
    THIS_UNITS_OBSERVATIONS_ARE_MISSING = (
        "this_units_observations_are_missing",
        "the same, for one unit's observed values")
    A_DISTRIBUTION_IS_MISSING = (
        "a_distribution_is_missing",
        "the same, for a probability the evaluator looked for in theta")
    AN_IDENTIFICATION_PREMISE_IS_MISSING = (
        "an_identification_premise_is_missing",
        "the same, for a premise the identification route needs stated")
    THE_DECOMPOSITION_NEEDS_THE_MEDIATORS_DISTRIBUTIONS = (
        "the_decomposition_needs_the_mediators_distributions",
        "what a mediation decomposition is short of")
    THE_TARGET_POPULATIONS_COVARIATE_DISTRIBUTION_IS_MISSING = (
        "the_target_populations_covariate_distribution_is_missing",
        "the transport formula is identified and its target-side input is "
        "not in hand")
    THE_SOURCE_POPULATIONS_STRATIFIED_CONDITIONAL_IS_MISSING = (
        "the_source_populations_stratified_conditional_is_missing",
        "and the source-side input, which a meta-analysis usually pools away")

    # --- the question asks for a curve -----------------------------------

    THE_QUESTION_ASKS_FOR_A_DOSE_RESPONSE_CURVE = (
        "the_question_asks_for_a_dose_response_curve",
        "Themis identifies and diagnoses; fitting the curve is somebody "
        "else's step, and this says what data that step takes")
    THE_DAG_DECLARES_NO_CONFOUNDER_FOR_THE_CURVE = (
        "the_dag_declares_no_confounder_for_the_curve",
        "and the note that a two-node DAG is unusual for an observational "
        "curve — present only when there is no confounder at all")

    # --- conditioning, or selecting, on a collider -----------------------

    THE_CONDITIONING_NODE_IS_A_COLLIDER = (
        "the_conditioning_node_is_a_collider",
        "the query asked to condition on it, and doing so opens the path")
    THE_SAMPLE_IS_RESTRICTED_ON_A_COLLIDER = (
        "the_sample_is_restricted_on_a_collider",
        "and the same damage done by how the sample was drawn rather than by "
        "the query")

    # --- the intervention is not well defined ----------------------------

    THE_INTERVENTION_IS_A_STATE_WITH_NO_TIME_WINDOW = (
        "the_intervention_is_a_state_with_no_time_window",
        "the caller declared a lasting state and no window, which is the "
        "classic ill-defined intervention")
    THE_INTERVENTION_SAYS_NEITHER_STATE_NOR_EVENT = (
        "the_intervention_says_neither_state_nor_event",
        "and the case that cannot yet be judged, which is a different thing "
        "to tell the reader — missing information is not an ill-defined "
        "intervention. Two members because the renderer used to tell these "
        "apart by the prose, or by a prefix on the provenance id")

    # --- only one of the declared layers ran -----------------------------

    ONLY_ONE_DECLARED_LAYER_WAS_RUN = (
        "only_one_declared_layer_was_run",
        "which layer the dispatcher ran and which it skipped")
    THE_RESULT_REFLECTS_ONE_LAYER_ONLY = (
        "the_result_reflects_one_layer_only",
        "and what that leaves the reader holding")
    A_LONGITUDINAL_ROUTE_DOES_NOT_DO_A_JOINT_INTERVENTION = (
        "a_longitudinal_route_does_not_do_a_joint_intervention",
        "why the two cannot be dispatched together. These were a table keyed "
        "by the pair, rendered into a hole in the sentence above")
    A_LONGITUDINAL_ROUTE_DOES_NOT_TRANSPORT = (
        "a_longitudinal_route_does_not_transport",
        "the same, for the target population")
    A_LONGITUDINAL_ROUTE_GIVES_THE_TOTAL_EFFECT_ONLY = (
        "a_longitudinal_route_gives_the_total_effect_only",
        "the same, for a decomposition of a time-varying treatment")
    A_JOINT_INTERVENTION_DOES_NOT_TRANSPORT = (
        "a_joint_intervention_does_not_transport",
        "the same, one route over")
    A_JOINT_INTERVENTION_DOES_NOT_DECOMPOSE = (
        "a_joint_intervention_does_not_decompose",
        "and the same for a mediator declaration beside a joint intervention")
    MEDIATION_AND_TRANSPORT_ARE_SEQUENTIAL = (
        "mediation_and_transport_are_sequential",
        "these two compose, but in sequence and not in one query")
    A_BLOCK_DECOMPOSITION_DOES_NOT_SPLIT_A_PATH = (
        "a_block_decomposition_does_not_split_a_path",
        "a joint block and a path-specific split are different quantities")

    # --- where the estimator strained on this sample ---------------------

    THE_OUTCOME_MODEL_IS_QUASI_SEPARATED = (
        "the_outcome_model_is_quasi_separated",
        "the outcome side of the support question: fitted probabilities "
        "pinned at the ends, which is a saturated logistic")
    EVERY_STRATUM_SHOULD_HAVE_BOTH_ARMS_AND_SOME_DO_NOT = (
        "every_stratum_should_have_both_arms_and_some_do_not",
        "the support question answered by counting cells, which is what the "
        "kind's own definition asks")
    THE_FITTED_PROPENSITY_LEAVES_PART_OF_THE_SAMPLE_UNSUPPORTED = (
        "the_fitted_propensity_leaves_part_of_the_sample_unsupported",
        "and the same question answered by a fitted score, which is the only "
        "witness there is when the adjustment set is continuous")
    THE_SAMPLE_COULD_NOT_BE_CUT_INTO_THE_STRATA_THE_WALD_NEEDS = (
        "the_sample_could_not_be_cut_into_the_strata_the_wald_needs",
        "the instrument is conditionally valid, the strata it needs are not "
        "in this sample, and so the reported quantity changed")
    THE_FIRST_STAGE_IS_WEAK = (
        "the_first_stage_is_weak",
        "one instrument, and the first stage below Stock-Yogo")
    THE_JOINT_FIRST_STAGE_IS_WEAK = (
        "the_joint_first_stage_is_weak",
        "and the same for a set of instruments taken together")
    THE_ANDERSON_RUBIN_SET_IS_THIS = (
        "the_anderson_rubin_set_is_this",
        "the interval that stays valid however weak the instrument is — "
        "offered here because a weak first stage is exactly when it is "
        "needed")
    THE_MULTI_INSTRUMENT_ANDERSON_RUBIN_SET_IS_THIS = (
        "the_multi_instrument_anderson_rubin_set_is_this",
        "the same for a set of instruments")
    THE_HETEROSKEDASTICITY_ROBUST_ANDERSON_RUBIN_SET_IS_THIS = (
        "the_heteroskedasticity_robust_anderson_rubin_set_is_this",
        "and the strongest of the three, valid under weak identification AND "
        "heteroskedasticity")
    THE_SET_CONSTRAINS_NOTHING = (
        "the_set_constrains_nothing",
        "what an unbounded set MEANS, said beside the three above rather "
        "than glued onto the notation inside one of them. `(−∞, +∞)` is "
        "the same for every reader and the reading of it is not, so a "
        "renderer that appends the reading writes one language into a hole")
    THE_OVERIDENTIFICATION_TEST_REFUTED_THE_INSTRUMENTS = (
        "the_overidentification_test_refuted_the_instruments",
        "a falsification rather than a shortfall: the data contradicted the "
        "instrument set, and more of the same data contradicts it again")
    THE_HOMOSKEDASTIC_SARGAN_SAYS_THE_SAME = (
        "the_homoskedastic_sargan_says_the_same",
        "the second test's numbers, where both were computed. This clause "
        "was written twice at its site — once for the gap and once for the "
        "headline — and the gap's copy was in English inside a Chinese "
        "sentence, which is what two copies of one fact come to")

    # --- the declaration and the column disagree -------------------------

    DECLARED_CONTINUOUS_BUT_THE_COLUMN_IS_DISCRETE = (
        "declared_continuous_but_the_column_is_discrete",
        "the reconciliation verdicts were a sentence built beside the check "
        "rather than beside the other descriptions, and were the one gap "
        "description in the package written in a single language")
    DECLARED_BINARY_BUT_THE_COLUMN_HAS_MORE_LEVELS = (
        "declared_binary_but_the_column_has_more_levels",
        "the same disagreement, the other way round")
    DECLARED_DISCRETE_BUT_THE_VALUES_FORM_A_CONTINUUM = (
        "declared_discrete_but_the_values_form_a_continuum",
        "and the third verdict")
    THE_COLUMN_HOLDS_VALUES_THE_DECLARATION_DOES_NOT_LIST = (
        "the_column_holds_values_the_declaration_does_not_list",
        "the domain verdict, which is the same question ``conform`` asks "
        "before it can code a labelled column")
    THE_NUMBER_ANSWERS_A_DIFFERENT_ESTIMAND_THAN_DECLARED = (
        "the_number_answers_a_different_estimand_than_declared",
        "what the disagreement costs when this query's estimand stands on "
        "that column")
    THIS_COLUMN_IS_NOT_IN_THIS_ESTIMAND = (
        "this_column_is_not_in_this_estimand",
        "and what it costs when the column is not in this query's estimand, "
        "which is nothing here and something for the next query")

    # --- the proxy is finer than the latent it stands for ----------------

    THE_PROXIES_ARE_FINER_THAN_THE_DECLARED_CARDINALITY = (
        "the_proxies_are_finer_than_the_declared_cardinality",
        "the measurable half: how many levels each proxy presents and how "
        "many states the query says U has, which is why the k x k channel "
        "formula (5) inverts does not exist")
    THE_PROXIES_SHOW_FEWER_STATES_THAN_THE_LATENT_HAS = (
        "the_proxies_show_fewer_states_than_the_latent_has",
        "why there is no number, where the channel is not square: a proxy "
        "with fewer levels than U has states cannot distinguish them, so "
        "there is no matrix to invert. The mirror of "
        "``the_proxies_are_finer_than_the_declared_cardinality`` and not a "
        "slot in it, because being too coarse and being too fine are "
        "answered by opposite errands — one needs a better instrument and "
        "the other needs a declaration")
    THE_PROXY_CHANNEL_IS_SINGULAR = (
        "the_proxy_channel_is_singular",
        "why there is no number, where the channel is square and still will "
        "not invert: the proxy has the levels it needs and they carry the "
        "same information about U twice, so the matrix has no independent "
        "row for one of the states. What a reader takes from it is that the "
        "shortfall is in what the proxy DISTINGUISHES rather than in how "
        "many values it takes")
    THE_DISCRETE_CONTRAST_NEEDS_TWO_ARMS = (
        "the_discrete_contrast_needs_two_arms",
        "why there is no number, on the branch where the channel is fine "
        "and the TREATMENT is what does not fit: a contrast is between two "
        "things, and this treatment has more than two. Kept apart from the "
        "channel branch because the reader's next move differs — this one is "
        "answered by a channel Themis already has, and that one is answered "
        "by going back to the field")
    A_TEST_OF_THE_NULL_IS_WHAT_IS_LEFT = (
        "a_test_of_the_null_is_what_is_left",
        "what the answer they are holding does and does not say, stated "
        "wherever the shape changed under them. A reader who asked how much "
        "and is handed whether will otherwise read the p-value as a small "
        "effect size, which is the one misreading this shape invites")
    WHICH_LEVELS_ARE_ONE_STATE_IS_NOT_IN_THE_DATA = (
        "which_levels_are_one_state_is_not_in_the_data",
        "and why the estimator stops here rather than folding the proxy "
        "itself — the grouping changes the number and nothing observed "
        "settles it, so it is a declaration and not an inference")

    # --- the two variables were declared to move each other --------------

    THE_TREATMENT_IS_INSIDE_A_DECLARED_LOOP = (
        "the_treatment_is_inside_a_declared_loop",
        "the structural half: which loop was declared, and that the "
        "intervention does not cut it — this is what makes the treatment "
        "endogenous rather than merely confounded")
    ADJUSTMENT_CANNOT_REMOVE_A_FEEDBACK = (
        "adjustment_cannot_remove_a_feedback",
        "and why the ordinary routes are gone rather than approximate: a "
        "covariate blocks a path, and a feedback the treatment is part of "
        "is not a path to block. States the front-door half too, which is "
        "the one a reader is most likely to reach for: every mediator on "
        "an X-to-Y path is inside the loop")
    THE_NUMBER_IS_A_SINGLE_EQUATIONS_COEFFICIENT = (
        "the_number_is_a_single_equations_coefficient",
        "what the answer beside a declared loop is an estimate OF, which "
        "is not what the query asked for and not a complier contrast "
        "either — the substitution is the reader's to know about, and it "
        "is invisible from the number")
    THE_LOOP_HAS_TO_BE_SETTLED_BEFORE_ANY_OF_THESE = (
        "the_loop_has_to_be_settled_before_any_of_these",
        "why a declared loop displaces the layers that carry, decompose or "
        "jointly intervene on an effect — each of them operates ON a DAG "
        "estimand, and there is not one to operate on until the loop is "
        "settled, so the displacement is an ordering and not a preference")
    THE_BRIDGE_EQUATION_HAS_NO_SOLUTION_WITHOUT_A_PENALTY = (
        "the_bridge_equation_has_no_solution_without_a_penalty",
        "what an ill-posed inverse problem is, said once where the reader "
        "meets its consequence: the equation smooths in one direction, so "
        "inverting it amplifies, and a penalty is what makes it solvable at "
        "all rather than a knob somebody left turned")
    THE_PENALTY_MOVED_IT_FURTHER_THAN_NOISE_DID = (
        "the_penalty_moved_it_further_than_noise_did",
        "the measurement, and the reason this is a gap on THIS answer rather "
        "than a note about the method: how far the penalty in force moved "
        "the number, held against how far sampling moves it, both computed "
        "on this sample")
    A_LIGHTER_PENALTY_HAS_NO_SOLUTION_HERE = (
        "a_lighter_penalty_has_no_solution_here",
        "the other door to the same finding, and the stronger one: where a "
        "smaller penalty leaves the system unsolvable, the number exists "
        "BECAUSE of the penalty rather than in spite of it, and no "
        "comparison against noise is needed to say so")
    THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE = (
        "the_fitted_treatment_bridge_went_negative",
        "the measurement, and what makes this a fact about THIS answer "
        "rather than a caveat about the method: what share of rows the "
        "fitted bridge came out below zero on, in each arm, counted on this "
        "sample")
    THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE_AT_A_LEVEL = (
        "the_fitted_treatment_bridge_went_negative_at_a_level",
        "the same measurement where the answer is a CURVE. Its own statement "
        "and not a slot in the one above, because what differs is how the "
        "arms are NAMED: a contrast has two and a reader knows them as "
        "treated and control, and a curve has one per level and knows them "
        "by their dose. The worst level is the one said, with how many there "
        "were, since a reader deciding whether to trust the curve needs to "
        "know it is one level's problem rather than the whole curve's")
    A_RECIPROCAL_PROBABILITY_CANNOT_BE_NEGATIVE = (
        "a_reciprocal_probability_cannot_be_negative",
        "why that share matters, said once where the reader meets its "
        "consequence: q is defined as one over a probability, so it is at "
        "least one everywhere, and a row where the fit says otherwise "
        "contributes a NEGATIVE weight to an average of the outcome — which "
        "is no longer an average of anything")
    A_CYCLIC_MODEL_NEED_NOT_HAVE_THIS_QUANTITY = (
        "a_cyclic_model_need_not_have_this_quantity",
        "the stronger statement, for the shapes the two-equation reduction "
        "does not reach: not that the search for an estimand came back "
        "empty, but that a cyclic model need not define one — which is why "
        "the route is to say how the two variables relate rather than to "
        "collect anything")


BY_SENTENCE: dict[str, Sentence] = {str(s): s for s in Sentence}
"""Every statement by the name an envelope carries it under."""


DESCRIBES: dict[str, language.Words] = {
    "the_edge_was_learned_by_discovery": {
        "en": "the edge `{edge}` on the route to the structural answer was "
              "learned from the data by the causal-discovery algorithm "
              "`{algorithm}`, so the result rests on that algorithm's "
              "assumptions (PC: faithfulness and causal sufficiency; LiNGAM: "
              "linearity and non-Gaussian noise).",
        "zh": "结构性回答途径上的边 `{edge}` 是因果发现算法 `{algorithm}` 从数据中学出的，结果以算法假设（如 "
              "PC: 忠实性 + 因果充足性；LiNGAM: 线性 + 非高斯）为前提。"},
    "the_edge_is_an_llm_proposal": {
        "en": "the edge `{edge}` on the route to the structural answer is a "
              "hypothesis the upstream LLM proposed (annotations.source = "
              "llm_proposal), not an edge evidence supports. The answer as it "
              "stands restates that hypothesis rather than verifying it.",
        "zh": "结构性回答途径上的边 `{edge}` 是上游 LLM 提出的假设（annotations.source = "
              "llm_proposal），不是经证据支持的边。当前回答相当于复述这条假设，而非独立验证。"},
    "the_edge_survived_this_share_of_resamples": {
        "en": "bootstrap stability {confidence} (the share of resamples the "
              "edge reappears in; the lower it is the more likely it is "
              "sampling noise, and the more it wants checking).",
        "zh": "自助法稳定度 {confidence}（该边在此比例的数据重采样中重现；越低越可能是采样噪声，越应复核）。"},
    "iv_rests_on_this_assumption": {
        "en": "IV identification (through the instrument `{instrument}`) is "
              "valid only under this assumption: {assumption}. Settle whether "
              "it holds in your setting before reading the IV estimate.",
        "zh": "IV 识别（工具变量 `{instrument}`）的有效性以下列假设为前提：{assumption}。读 IV 估计前应明"
              "确这条假设是否在你的场景下成立。"},
    "front_door_rests_on_four_premises": {
        "en": "front-door identification (Pearl's front-door criterion) is "
              "valid only under these assumptions: (1) the mediator set M "
              "intercepts every directed path from X to Y; (2) there is no "
              "unblocked back-door path from X to M; (3) every back-door path "
              "from M to Y is blocked by X; (4) consistency of potential "
              "outcomes. If any one of them fails, the front-door estimate "
              "fails with it.",
        "zh": "前门识别（Pearl front-door criterion）的有效性以下列假设为前提：(1) 中介集 M 阻断 X→Y "
              "的所有有向路径；(2) 不存在未阻断的 X→M 后门路径；(3) 所有 M→Y 后门路径已被 X 阻断；(4) "
              "consistency of potential outcomes。若任一假设不成立，前门估计失效。"},
    "the_counterfactual_rests_on_cross_world_premises": {
        "en": "counterfactual reasoning is valid only under consistency (an "
              "observed value = the potential outcome under do(the value it "
              "actually took)) and the composition axiom, neither of which "
              "the data can check; a cross-world cell needs some route to "
              "join the two worlds besides, and that route's own premises are "
              "inherited with it — which route, and whether it can be tested, "
              "is on the answer's interventional_risk_provenance and in the "
              "rows the assumption ledger lists one by one. Monotonicity, "
              "where it is declared, is a further premise that tightens this "
              "cell rather than a premise of the answer.",
        "zh": "反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的潜在结果）+ composition 公理为"
              "前提，这两条无法从数据本身验证；跨世界的格子还要靠某一条路线把两个世界连起来，那条路线自己的前提也一并被继承——具体是哪条、"
              "可不可检验，看答案上的 interventional_risk_provenance 与假设台账逐条列出的那几行；单调性若声"
              "明，是收紧这一格的额外前提，不是回答的前提。"},
    "transport_rests_on_s_admissibility": {
        "en": "carrying the estimate from {source} to {target} is valid only "
              "under S-admissibility: the selection_nodes declared have to "
              "capture the distributional differences between the two "
              "populations correctly.",
        "zh": "将估计从 {source} 转移到 {target} 的有效性以 S-admissibility 为前提：声明的 "
              "selection_nodes 必须正确捕获两人群间分布差异。"},
    "mediation_is_identifiable_for_a_mediator": {
        "en": "the {branch} mediation decomposition is marked identifiable, "
              "on the premise that these assumptions hold: {assumptions} "
              "(mediator {subject}).",
        "zh": "中介分解 {branch} 标识为可识别，前提是以下假设成立：{assumptions}（中介 {subject}）。"},
    "mediation_is_identifiable_for_a_mediator_block": {
        "en": "the {branch} mediation decomposition is marked identifiable, "
              "on the premise that these assumptions hold: {assumptions} "
              "(the mediator block {subject}, decomposed as one whole and not "
              "split into single paths).",
        "zh": "中介分解 {branch} 标识为可识别，前提是以下假设成立：{assumptions}（中介组 {subject}，作为"
              "一整组分解，不拆到单条路径）。"},
    "the_caller_flagged_an_uncertainty": {
        "en": "the upstream LLM flagged an uncertainty, `{kind}`. Read the "
              "answer with that in view.",
        "zh": "上游 LLM 标记了不确定性 `{kind}`。答案的解读应将其考虑在内。"},
    "the_caller_flagged_an_uncertainty_and_said_why": {
        "en": "the upstream LLM flagged an uncertainty, `{kind}`: "
              "{rationale}. Read the answer with that in view.",
        "zh": "上游 LLM 标记了不确定性 `{kind}`：{rationale}。答案的解读应将其考虑在内。"},
    "the_composite_confidence_is_below_the_threshold": {
        "en": "the answer's composite confidence is {confidence} (< "
              "{threshold}) — at least one input statement carries "
              "substantial uncertainty, and the result should be read as "
              "uncertain. The weak links themselves are the entries marked "
              "is_weakest=true in `confidence_sources`.",
        "zh": "答案的复合可信度为 {confidence}（< {threshold}）— 至少有一项输入语句的置信度较低，结果应视为不确"
              "定的。具体的薄弱环节见 `confidence_sources` 中标记 is_weakest=true 的条目。"},
    "the_variable_has_no_operational_definition": {
        "en": "the variable `{variable}` has no operational definition: "
              "{missing}.",
        "zh": "变量 `{variable}` 缺操作化定义：{missing}。"},
    "the_answer_is_an_interval_not_a_point": {
        "en": "the answer is a symbolic interval, not a point estimate. "
              "Whatever renders it has to say so rather than let it read as a "
              "number.",
        "zh": "答案是符号区间，不是点估计。渲染时必须明示这是 bounds 而非具体数值。"},
    "several_intervals_bound_the_same_quantity": {
        "en": "{count} of them bound the same quantity, each resting on "
              "different assumptions.",
        "zh": "共 {count} 条，界定的是同一个量，各自靠不同的假设。"},
    "one_interval_and_what_it_rests_on": {
        "en": "one comes from `{method}`, assuming {assumptions}.",
        "zh": "一条来自 `{method}`，假设 {assumptions}。"},
    "one_interval_that_rests_on_nothing": {
        "en": "one comes from `{method}` and needs no further assumption.",
        "zh": "一条来自 `{method}`，不需要额外假设。"},
    "and_that_interval_is_uninformative": {
        "en": "that one is the uninformative [0,1] / [-1,1], which tells "
              "nothing apart.",
        "zh": "这一条是非信息性的 [0,1] / [-1,1]，没有实际辨别力。"},
    "choose_by_which_assumptions_you_accept": {
        "en": "Choose by which set of assumptions you accept, and **do not "
              "intersect them**: where both hold the intersection does "
              "contain the true value, but it is not the sharp bound under "
              "their conjunction (that would take the numeric side solving "
              "once more over the response-type polytope), and an interval "
              "with no label on it erases what each one stood on.",
        "zh": "读者按自己接受哪组假设来选，**不要取交**：两条都成立时交集确实含真值，但它不是二者合取下的锐界（那要数值端在响应型多面体"
              "上另解一次），而一个不带标签的区间会把各自靠什么抹掉。"},
    "the_graph_was_learned_by_an_algorithm": {
        "en": "the DAG was learned from the data by the causal-discovery "
              "algorithm `{algorithm}` rather than declared by hand from "
              "domain knowledge.",
        "zh": "DAG 是由因果发现算法 `{algorithm}` 从数据中学出的，不是用领域知识手工声明的。"},
    "discovery_used_this_significance_threshold": {
        "en": "significance threshold α = {alpha}.",
        "zh": "显著性阈值 α = {alpha}。"},
    "discovery_ran_on_this_many_rows": {
        "en": "sample size N = {n}.",
        "zh": "样本量 N = {n}。"},
    "a_learned_graph_inherits_the_algorithms_assumptions": {
        "en":
              "the result inherits the algorithm's core assumptions: PC needs "
              "faithfulness and causal sufficiency; FCI relaxes causal "
              "sufficiency but still needs faithfulness; LiNGAM needs "
              "linearity and non-Gaussian noise.",
        "zh": "结果继承算法的核心假设：PC 需要忠实性 (faithfulness) + 因果充足性 (causal "
              "sufficiency)；FCI 放宽因果充足性但仍需忠实性；LiNGAM 需要线性 + 非高斯噪声。"},
    "the_algorithms_assumptions_were_violated_on_this_data": {
        "en": "specific violations of the algorithm's assumptions were "
              "detected on this data: {violations}.",
        "zh": "检测到当前数据上算法假设的具体违反：{violations}。"},
    "the_dag_declares_no_latent_common_cause": {
        "en": "back-door identification assumes the confounders you listed "
              "are all of them — the DAG declares no bidirected / "
              "latent-common-cause edge at all. This is the standard setting "
              "for an unmeasured confounder surviving adjustment on the "
              "measured covariates. Several fields have well-documented "
              "RCT-vs-observational (or experiment-vs-observation) reversals: "
              "medicine (HRT-CVD, WHI 2002; vitamin D-CVD, VITAL 2018), "
              "labour economics (ability bias in Card 1995's "
              "schooling-earnings estimates), education evaluation (parental "
              "motivation in CREDO 2013's charter schools). The mechanism "
              "differs by field (healthy-user bias / ability bias / selection "
              "effects), but **the structural lesson is the same** — "
              "adjusting on the measured ones is not enough. Once the data is "
              "in hand, run a sensitivity analysis (E-value) to quantify how "
              "robust this is to an unmeasured confounder, or declare the "
              "latent you suspect as a bidirected edge in the DAG.",
        "zh": "Backdoor 识别假设你列出的 confounder 已经测全 —— DAG 里没有声明任何 bidirected / "
              "latent-common-cause 边。这是 measured-covariate 调整后仍残留 unmeasured "
              "confounder 的典型场景。多个域有 well-documented RCT-vs-observational（或实验"
              "-vs-观察）反转：医学（HRT-CVD WHI 2002、vitamin D-CVD VITAL 2018）、劳动经济学（"
              "Card 1995 schooling-earnings 中的 ability bias）、教育评估（charter "
              "schools CREDO 2013 中的 parental motivation）。机制各域不同（healthy-user "
              "bias / ability bias / selection effects），但**结构教训一致**——measured "
              "调整不够。拿到数据后跑 sensitivity analysis（E-value）量化对 unmeasured "
              "confounder 的稳健性，或在 DAG 里把怀疑的 latent 显式声明为 bidirected。"},
    "tian_found_a_hedge": {
        "en": "identification failed: Tian's algorithm found a c-component "
              "hedge on the An(Y) subgraph — X and Y sit in the same "
              "c-component, which says there is a latent common cause (or "
              "bidirected coupling) between them that no observed variable "
              "screens off, so P(Y | do(X)) is not identifiable from the "
              "observational distribution on this ADMG.",
        "zh": "识别失败：Tian 算法在 An(Y) 子图上找到 c-component hedge —— X 与 Y 处于同一 "
              "c-component，说明它们之间存在未被任何观测变量遮断的潜在共同原因 / 双向耦合，P(Y | do(X)) 在该 "
              "ADMG 下不可从观测分布识别。"},
    "the_identification_route_failed": {
        "en": "the identification route failed: {why}.",
        "zh": "识别路径失败：{why}。"},
    "the_source_domains_contradict_each_other": {
        "en": "the source domains contradict each other: {why}.",
        "zh": "多源迁移互相矛盾：{why}。"},
    "the_graph_and_the_cpts_disagree": {
        "en": "the declared graph and the CPTs supplied disagree: {what} is "
              "missing, and a marginal that theta does carry is refused by "
              "d-separation (an independence the graph implies does not "
              "hold).",
        "zh": "声明的图与提供的 CPT 不一致：缺 {what}，但 theta 中存在的边缘量被 d-separation 拒绝（图蕴含"
              "的独立性不成立）。"},
    "a_variable_declares_a_noisy_measurement": {
        "en":
              "measurement-error risk: a variable on the identification route "
              "declares a noisy way of measuring it — {variables}. The "
              "classical references: MacMahon 1990 Lancet, where a single "
              "clinic BP reading attenuates the BP→CHD slope toward 0 by "
              "about 60% through within-person variation (regression "
              "dilution); Hernán & Robins *What If* §9, where "
              "non-differential misclassification of a self-reported or "
              "questionnaire exposure likewise pulls the estimate below the "
              "true effect; Fuller 1987 *Measurement Error Models* for the "
              "formal attenuation theorem. The structural layer only "
              "identifies and diagnoses gaps — but where a misclassified "
              "**discrete outcome** or **binary exposure** has a confusion "
              "matrix from a validation study, the numeric layer can undo the "
              "attenuation (estimate(..., misclassification={{<outcome or "
              "exposure name>: {{confusion_matrix, states}}}})), inverting "
              "the matrix within each back-door stratum — on the outcome side "
              "p_true=M⁻¹p_obs (Rogan-Gladen 1978 in the binary case), on the "
              "exposure side by the matrix method, inverting the joint (X,Y) "
              "along the exposure axis one outcome column at a time (Barron "
              "1977 / Greenland 1988 / Marshall 1990). Misclassification may "
              "be non-differential (one matrix) or **differential** "
              "(differential=True plus one matrix per stratum, with "
              "differential_by naming the axis: on the outcome side by "
              "exposure arm = detection bias, or **by covariate stratum** "
              "(differential_by=<covariate>); on the exposure side by outcome "
              "level = recall bias, or **by covariate stratum** "
              "(differential_by=<covariate>, where the rates vary with site "
              "or age). Differential misclassification can bias away from the "
              "null, which is why each stratum has to be inverted on its own "
              "and pooling into one matrix gets it wrong.) Where the "
              "validation study's own count table is to hand, declare it "
              "instead of the matrix ({{validation_counts: [[...]]}}): the "
              "matrix is its column-normalisation and the interval then "
              "redraws it every bootstrap round from each column's "
              "Dirichlet, so it carries that study's uncertainty as well as "
              "the sample's — a matrix from fifty subjects and one fixed by "
              "protocol are different claims and stop reading identically. "
              "Either way, "
              "verify_measurement_correction_numeric / "
              "verify_exposure_measurement_correction_numeric recompute the "
              "correction independently. Where what is mismeasured is a "
              "**continuous exposure or continuous confounder** with a known "
              "classical additive error variance σ²_u (validation study, "
              "repeat measurements), the numeric layer can debias through "
              "estimate(..., measurement_error={{<variable>: "
              "{{error_variance}}}}) with regression calibration's method of "
              "moments, β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive (Carroll 2006; a "
              "mismeasured exposure attenuates toward zero, and with a single "
              "exposure that is βx=b_naive/λ, where λ=1−σ²_u/Var(W|Z) is the "
              "continuous counterpart of det(M); a mismeasured confounder "
              "leaves residual confounding after adjusting on the noisy "
              "proxy, which can go either way and has no scalar shortcut — "
              "the whole matrix inversion is what debiases it), and "
              "verify_regression_calibration_numeric re-derives it. That "
              "correction is for CLASSICAL error, W=X*+U with U independent "
              "of the truth. The other structure, **Berkson** error "
              "(X*=W+U, U independent of the RECORDED nominal value — an "
              "assigned dose, one station's reading applied to a district, a "
              "prescribed rather than absorbed amount), is not a weaker case "
              "of it but the opposite one: E[X*|W,Z]=W there, so the naive "
              "back-door slope is already unbiased and correcting is what "
              "introduces the error. Nothing in the column separates the "
              "two, so it is declared — measurement_error={{<exposure>: "
              "{{structure: berkson, error_variance}}}} — and what comes "
              "back is the price rather than a correction: the scatter "
              "enters the residual as β²σ²_u and widens every interval on "
              "the design by a fixed factor (verify_berkson_error re-derives "
              "it). A third reading of the same declaration is that the error "
              "is DIFFERENTIAL — that it carries a component tracking the "
              "outcome, as a self-report shaded by how ill the respondent "
              "already is does. That inflates the observed exposure-outcome "
              "covariance as well as the exposure's variance, so the ordinary "
              "correction moves one of the two things that moved and can land "
              "further from the truth than doing nothing. A caller who has δ "
              "from a validation substudy declares it "
              "(differential_by=<outcome>, differential_coefficient=δ) and a "
              "closed form takes the covariance's inflation off first; at δ=0 "
              "it reduces to the ordinary correction exactly. A mismeasured "
              "**continuous outcome** is a different case: "
              "classical additive error Y=Y*+V moves no conditional mean, so "
              "the point estimate is unbiased and there is nothing to "
              "correct; what the same entry point "
              "measurement_error={{<outcome>: {{error_variance}}}} gives is "
              "the cost — the residual variance splits as "
              "Var(Y|D)=Var(Y*|D)+σ²_v, and the interval is "
              "√(Var(Y|D)/Var(Y*|D)) times wider than it would be with the "
              "outcome measured correctly. That part cannot be bought back "
              "with sample size; only measuring the outcome better removes it "
              "(verify_outcome_error re-derives this).",
        "zh": "测量误差风险：识别路径上有变量声明了高噪声测量方式 — {variables}。 经典文献：MacMahon 1990 "
              "Lancet 单次门诊 BP 测量因 within-person 变异导致 BP→CHD 斜率被 regression "
              "dilution 向 0 衰减约 60%；Hernán & Robins What If §9 自报告 / 问卷暴露的 "
              "non-differential mis-classification 同样使 估计值低估真效应；Fuller 1987 "
              "Measurement Error Models 给出 attenuation theorem 的形式定义。结构层只做识别 "
              "+ "
              "缺口诊断；但若被误分类的**离散结局**或**二值暴露**有验证研究给出的混淆矩阵，数值层可做去衰减校正（estimate("
              "..., misclassification={{<结局或暴露变量名>: {{confusion_matrix, "
              "states}}}})），逐后门层做矩阵求逆——结局侧 p_true=M⁻¹p_obs（二值即 Rogan-Gladen "
              "1978），暴露侧用矩阵法沿暴露轴对 (X,Y) 联合逐结局列求逆（Barron 1977 / Greenland 1988 "
              "/ Marshall 1990）。误分类可为非差异（单一矩阵），也可为**差异性**（differential=True + "
              "每个条件层一个矩阵，differential_by 指定差异轴：结局侧按暴露臂=detection bias 或按**协变量"
              "分层**（differential_by=<协变量>），暴露侧按结局层=recall bias "
              "或按**协变量分层**（differential_by=<协变量>，误分类率随测量地点/年龄而异）；差异误分类可朝远离零方向"
              "偏，故须逐层求逆，池化单矩阵会做错）。若手上有验证研究**原始的计数表**，就把它"
              "而不是矩阵声明进来（{{validation_counts: [[...]]}}）：矩阵是这张表的按列归一，"
              "区间会在每一轮 bootstrap 里按每一列的 Dirichlet 重抽它，于是同时带上主样本和"
              "那次计数两份不确定性——「五十个受试者数出来的矩阵」和「协议规定死的矩阵」是两"
              "句不同的话，不该在页面上读起来一模一样。两种都由 "
              "verify_measurement_correction_numeric "
              "/ verify_exposure_measurement_correction_numeric 独立重算校正值。若被误测的"
              "是**连续暴露或连续混杂**且有已知的经典加性误差方差 σ²_u（验证研究 / 重复测量），数值层可经 "
              "estimate(..., measurement_error={{<变量名>: {{error_variance}}}}) "
              "用 regression calibration 的矩量校正 β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive "
              "去偏（Carroll 2006；误测暴露=回归稀释向零衰减，单暴露即 "
              "βx=b_naive/λ，λ=1−σ²_u/Var(W|Z) 是连续版 det(M)；误测混杂=对噪声代理调整留下的残差混淆"
              "偏倚，可朝任意方向，由整条矩阵求逆去偏无标量捷径），由 "
              "verify_regression_calibration_numeric 独立重导。这条校正针对的是**经典**"
              "误差 W=X*+U（U 与真值独立）。另一种结构 **Berkson 误差**（X*=W+U，U 与**记录"
              "下来的名义值**独立——分配的剂量、拿一个监测站的读数当整个区的值、开出的而非吸收的"
              "量）不是它的弱化版而是反过来：那时 E[X*|W,Z]=W，朴素的后门斜率本来就无偏，做校正"
              "才会把对的数改错。列本身分不出这两种，所以要声明——measurement_error={{<暴露名>: "
              "{{structure: berkson, error_variance}}}}——回来的不是校正而是代价：真值散布按 "
              "β²σ²_u 落进残差，把这条设计上的每个区间按固定倍数撑宽（由 verify_berkson_error "
              "独立重导）。同一份声明还有第三种读法：误差是**差异性**的——含一份"
              "随结局走的分量（自报告被「我已经病成这样」染色就是这种）。它把观测"
              "到的暴露-结局协方差和暴露方差一起抬高，于是普通那条校正只挪了两处"
              "变动里的一处，结果可能比不校正离真值更远。手里有验证子研究给出的 δ "
              "就声明出来（differential_by=<结局名>, differential_coefficient=δ），"
              "闭式会先把协方差里那份误差减掉；δ=0 时它精确退回普通校正。"
              "被误测的若是**连续结局**则另当别"
              "论：经典加性误差 Y=Y*+V 不改变任何条件均值，点估计无偏、无可校正；同一入口 "
              "measurement_error={{<结局名>: {{error_variance}}}} 给出的是代价——残差方差按 "
              "Var(Y|D)=Var(Y*|D)+σ²_v 分解，区间比结局测准时宽 √(Var(Y|D)/Var(Y*|D)) 倍，这"
              "部分靠加样本量消不掉、只能靠把结局测准（由 verify_outcome_error 独立重导）。"},
    "a_continuous_measure_was_cut_in_two": {
        "en": "dichotomization: a continuous measurement on the "
              "identification route was cut into two at some cutpoint — "
              "{variables}. Splitting a continuous quantity at a threshold "
              "(1) throws away the dose-response information and costs "
              "statistical efficiency (Royston, Altman & Sauerbrei 2006 *Stat "
              "Med* 25:127 “Dichotomizing continuous predictors in multiple "
              "regression: a bad idea”); (2) makes the result sensitive to "
              "the cutpoint, and a data-driven search for the “optimal” one "
              "inflates false positives on top of that (Altman et al 1994 "
              "*JNCI* 86:829); (3) leaves within-category residual "
              "confounding, so the adjustment is incomplete, when what was "
              "dichotomized is a confounder (Becher 1992 *Stat Med* 11:1747). "
              "Themis can keep the variable continuous and estimate the "
              "dose-response instead (Phase 13/14).",
        "zh": "二分化（dichotomization）：识别路径上有连续测量被在某个 cutpoint 切成二值 — "
              "{variables}。把连续量在阈值处二分会（1）丢失 dose-response 信息、降低统计效率（Royston, "
              "Altman & Sauerbrei 2006 *Stat Med* 25:127 “Dichotomizing "
              "continuous predictors in multiple regression: a bad idea”）；（2）"
              "结果对切点敏感，数据驱动的“最优切点”搜索还会抬高假阳性（Altman et al 1994 *JNCI* 86:829）；"
              "（3）若被二分的是 confounder，类内残余混杂使调整不充分（Becher 1992 *Stat Med* "
              "11:1747）。Themis 支持把变量保留为连续并做 dose-response 估计（Phase 13/14）。"},
    "a_structural_input_is_missing": {
        "en": "a structural input is missing: {why}.",
        "zh": "缺结构输入：{why}。"},
    "this_units_observations_are_missing": {
        "en": "this unit's observed values are missing: {why}.",
        "zh": "缺该单位的观测值：{why}。"},
    "a_distribution_is_missing": {
        "en": "the distribution {what} is missing.",
        "zh": "缺概率分布 {what}。"},
    "an_identification_premise_is_missing": {
        "en": "an identification premise has to be supplied or corrected: "
              "{why}.",
        "zh": "识别前提待补充或修正：{why}。"},
    "the_decomposition_needs_the_mediators_distributions": {
        "en": "the mediation decomposition needs {mediator}'s distributions: "
              "{target}.",
        "zh": "中介分解需要 {mediator} 相关分布：{target}。"},
    "the_target_populations_covariate_distribution_is_missing": {
        "en": "the transport formula is identified, but the distribution "
              "P*(Z) of the target population {population} over "
              "{{{variables}}} was not supplied.",
        "zh": "转移公式已识别，但目标人群 {population} 在 {{{variables}}} 上的分布 P*(Z) 未提供。"},
    "the_source_populations_stratified_conditional_is_missing": {
        "en": "the transport formula also needs the stratified conditional "
              "{formula} on the source population {population} (a "
              "meta-analysis usually pools to one number and publishes no "
              "strata).",
        "zh": "转移公式还需要源人群 {population} 的分层条件分布 {formula}（meta-analysis 通常只汇总成"
              "一个数，不给分层）。"},
    "the_question_asks_for_a_dose_response_curve": {
        "en": "the question asks for the dose-response relationship between "
              "{intervention} and {target} (a curve, a plot). Themis does not "
              "fit curves — use EconML / DoubleML / GAM — but here is the "
              "data specification doing so would take.",
        "zh": "用户问的是 {intervention} 与 {target} 之间的剂量响应关系（曲线 / 关系图）。Themis 不算曲"
              "线（请用 EconML / DoubleML / GAM）—— 但下面是你做这件事所需的数据规格。"},
    "the_dag_declares_no_confounder_for_the_curve": {
        "en":
              "(Note: your DAG declares only the intervention and the target, "
              "with no confounder at all. An observational dose-response "
              "analysis usually needs at least the baseline outcome and the "
              "key demographic covariates declared in the DAG; if you do mean "
              "to keep the DAG minimal — a randomized design, say — you can "
              "ignore this.)",
        "zh": "（注：你的 DAG 仅声明了 intervention + target 两个节点，没有任何 confounder。观察性剂"
              "量响应分析典型需要在 DAG 里至少声明 baseline outcome 与关键 demographic "
              "covariates；若你确实想保持 minimal DAG（如随机化 RCT 设计），可以忽略此提示。）"},
    "the_conditioning_node_is_a_collider": {
        "en": "the conditioning node `{collider}` in `given` is a collider — "
              "between `{intervention}` and `{target}` there is a path that "
              "collides at `{collider}` (either arm may run through a latent "
              "or bidirected edge, which is M-bias). Pearl's d-separation: "
              "conditioning on a collider (or on its descendant) **opens** "
              "that non-causal path rather than blocking it, and puts "
              "collider-induced bias / selection bias into the estimate. What "
              "comes back is not \"the causal effect within the `{collider}` "
              "subgroup\" but a mixture contaminated by the path that was "
              "opened.",
        "zh": "`given` 中的条件节点 `{collider}` 是 collider —— 在 `{intervention}` 与"
              " `{target}` 之间存在一条以 `{collider}` 为对撞点的路径（两条臂可经潜在/双向边，即 M-bia"
              "s）。Pearl d-separation：在 collider（或其后代）上做条件会**打开**这条非因果路径而不是阻断"
              "它，给最终估计引入 collider-induced bias / selection bias。当前返回的不是 \"在 "
              "`{collider}` 子群上的因果效应\"，而是被打开的非因果路径污染过的混合量。"},
    "the_sample_is_restricted_on_a_collider": {
        "en": "the sample is structurally restricted to subjects with "
              "`{collider}={value}` (an ObservationStatement in the program "
              "encodes that restriction), and in the declared DAG both "
              "`{intervention}` and `{target}` are ancestors of `{collider}` "
              "— so `{collider}` is a collider. Pearl's d-separation: "
              "estimating P({target} | do({intervention})) from the "
              "{collider}={value} subsample alone is conditioning on a "
              "collider, and it **opens** the non-causal path "
              "`{intervention}→...→{collider}←...←{target}`, putting "
              "selection-induced bias into the estimate. This is the standard "
              "structure of Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* "
              "15:615 \"A Structural Approach to Selection Bias\".",
        "zh": "样本被结构性限制为 `{collider}={value}` 的受试者（program 里有 "
              "ObservationStatement 编码了这个限制），但声明的 DAG 里 `{intervention}` 和 "
              "`{target}` 都是 `{collider}` 的祖先 —— `{collider}` 是 "
              "collider。Pearl d-separation：用『仅 {collider}={value} 的子样本』估计 "
              "P({target} | do({intervention})) 等于在 collider 上做条件，会**打开** "
              "`{intervention}→...→{collider}←...←{target}` 这条非因果路径，给估计引入 "
              "selection-induced bias。Hernán-Hernández-Díaz-Robins 2004 "
              "*Epidemiology* 15:615 \"A Structural Approach to Selection "
              "Bias\" 的标准结构。"},
    "the_intervention_is_a_state_with_no_time_window": {
        "en": "the intervention is a state rather than an event and no time "
              "window was given: the variable `{intervention}` declares "
              "`state_vs_event=\"state\"` (a lasting attribute, not a discrete "
              "event) and declares no `time_window`. This is the classic "
              "ill-defined-intervention structure of Hernán & Taubman 2008 "
              "*IJO* 32(S3):S8-S14 \"Does obesity shorten life? The importance "
              "of well-defined interventions to answer causal questions\" — "
              "one `{intervention}` state value is reachable by structurally "
              "different manipulations, those manipulations carry "
              "**different** counterfactuals, and so do({intervention}=state) "
              "has no single definition; the consistency assumption (Hernán & "
              "Robins *What If* §3.4) is violated silently, and the \"effect\" "
              "that comes back is a mixture of several estimands. Themis only "
              "surfaces this; it cannot pick the intervention's definition "
              "for you.",
        "zh": "intervention 是状态不是事件、且没有指定时间窗：变量 `{intervention}` 声明了 "
              "`state_vs_event=\"state\"`（持久性属性，不是离散事件），但同一变量没有声明 `time_window"
              "`。这是 Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 \"Does obesity "
              "shorten life? The importance of well-defined interventions to "
              "answer causal questions\" 的经典 ill-defined intervention 结构 —— 同一"
              "个 `{intervention}` 状态值可以由多种结构上不同的操纵方式达到，而这些不同的操纵会带来**不同**的反事实结"
              "果，因此 do({intervention}=state) 没有唯一定义；consistency "
              "assumption（Hernán & Robins *What If* §3.4）被沉默地违反，返回的 \"effect\" "
              "实际上是多个估计量的混合。Themis 仅surface 此问题，无法替你选具体的干预定义。"},
    "the_intervention_says_neither_state_nor_event": {
        "en":
              "`{intervention}` appears in a do(.) position, but nothing says "
              "whether it is a **discrete event** or a **sustained state** "
              "(`state_vs_event`), and no `time_window` was given — so **this "
              "cannot yet be judged** one way or the other (missing "
              "information is not the same as an ill-defined intervention). "
              "One question settles it: is `{intervention}` a **definite "
              "action or event** (a single dose, enrolling in a programme), "
              "or an **attribute or sustained state** (obesity, keeping up a "
              "behaviour)? If the former, the intervention is already well "
              "defined and declaring `state_vs_event=\"event\"` clears this "
              "notice. If the latter, it falls into the "
              "ill-defined-intervention case of Hernán & Taubman 2008 *IJO* "
              "32(S3):S8-S14 \"Does obesity shorten life?\" (which uses obesity "
              "as its example): one state value is reachable by several "
              "manipulations, each with its own counterfactual, so "
              "do({intervention}=that state) has no single definition and the "
              "consistency assumption (Hernán & Robins *What If* §3.4) is "
              "violated — add a `time_window`, or opt in to "
              "`ill_defined_intervention` under extensions.ambiguities.",
        "zh": "`{intervention}` 出现在 do(.) "
              "位置，但没声明它是**离散事件**还是**持续状态**（`state_vs_event`），也没给 "
              "`time_window` —— 所以这里**还无法判断**这个干预定义得够不够清楚（缺信息 ≠ "
              "定义不清）。先确认一句：`{intervention}` 是一个**明确的动作 / 事件**（如一次性给药、参加某项目），还"
              "是一个**属性 / 持续状态**（如肥胖、长期保持某行为）？若是前者，干预本就定义清楚，声明 "
              "`state_vs_event=\"event\"` 即可消除本提示。若是后者，则会落入 Hernán & Taubman "
              "2008 *IJO* 32(S3):S8-S14 \"Does obesity shorten life?\"（该文以肥胖为例）"
              "的 ill-defined intervention "
              "情形：同一状态值可由多种操纵方式达到、各自反事实不同，do({intervention}=该状态) "
              "没有唯一定义，consistency 假设（Hernán & Robins *What If* §3.4）会被违反 —— 这"
              "时请加 `time_window`，或在 extensions.ambiguities opt-in "
              "`ill_defined_intervention`。"},
    "only_one_declared_layer_was_run": {
        "en": "the query declares both {won} and {lost}; this dispatch ran "
              "**{winner}** only, and **{skipped}** was skipped in silence. ",
        "zh": "Query 同时声明了 {won} 和 {lost}；当前 dispatch 只跑了 "
              "**{winner}**，**{skipped}** 被静默跳过。"},
    "the_result_reflects_one_layer_only": {
        "en": "The result reflects the {winner} layer alone; a {skipped} "
              "analysis takes a query of its own.",
        "zh": "当前 result 只反映 {winner} 这一层；{skipped} 分析需要单独 query。"},
    "a_longitudinal_route_does_not_do_a_joint_intervention": {
        "en": "the longitudinal g-formula standardizes sequentially along "
              "time over **one** treatment trajectory; a joint intervention "
              "on a set of treatments (with treatment-by-treatment "
              "interaction) is not the quantity it computes.",
        "zh": "纵向 g-formula 沿时间序对**一条**处理轨迹做序贯标准化；对处理集合的联合干预（含处理×处理交互）不是它算出来的"
              "那个量。"},
    "a_longitudinal_route_does_not_transport": {
        "en": "the longitudinal g-formula standardizes within the main "
              "sample's own population; carrying the result to a target "
              "population is a second identification (selection diagram + "
              "s-admissible set), and it does not come along for free.",
        "zh": "纵向 g-formula 在主样本自己的总体里标准化；把结果搬到目标总体是另一次识别（选择图 + s-可容许集），它不顺带"
              "做。"},
    "a_longitudinal_route_gives_the_total_effect_only": {
        "en": "decomposing a time-varying treatment into direct and indirect "
              "effects needs sequential ignorability for the time-varying "
              "mediator, which is not the set of conditions the total-effect "
              "g-formula rests on; this route gives the total effect only.",
        "zh": "时变处理的直接/间接效应分解要的是时变中介的序贯可忽略性，与总效应的 g-formula 不是同一组条件；这条路线只给总效"
              "应。"},
    "a_joint_intervention_does_not_transport": {
        "en": "the joint contrast is computed within the main sample's own "
              "population; the v1 scope of the joint-intervention route "
              "explicitly does not compose with `target_population`.",
        "zh": "联合对比是在主样本自己的总体里算的；联合干预路径的 v1 作用域明确不与 `target_population` 组合。"},
    "a_joint_intervention_does_not_decompose": {
        "en": "a joint intervention gives the total contrast over a set of "
              "treatments (with treatment-by-treatment interaction) and does "
              "no direct/indirect decomposition; the v1 scope of that route "
              "explicitly does not compose with a mediator declaration.",
        "zh": "联合干预给的是处理集合的总对比（含处理×处理交互），不做直接/间接分解；该路径的 v1 作用域明确不与中介声明组合。"},
    "mediation_and_transport_are_sequential": {
        "en": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport are sequential operations (mediation first in the "
              "source population, then each component transported to the "
              "target); they cannot be dispatched together in one query.",
        "zh": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport 是 sequential operations（先在 source population 做 "
              "mediation, 再 transport 各 component 到 target），不能在一个 query 里同时 "
              "dispatch。"},
    "a_block_decomposition_does_not_split_a_path": {
        "en": "`mediators` decomposes these into a joint NDE/NIE as **one "
              "block**; the path-specific split through a single mediator "
              "inside it is not part of the block's decomposition — it needs "
              "conditions the block itself does not, and this repository puts "
              "it explicitly out of scope.",
        "zh": "`mediators` 把这些中介当作**一个块**做联合 NDE/NIE；穿过其中单个中介的路径特定拆分不含在块的分解里 "
              "—— 它需要块本身不需要的额外条件，本仓明确列为作用域之外。"},
    "the_outcome_model_is_quasi_separated": {
        "en": "the back-door logistic model P({outcome}=1 | {features}) puts "
              "{outside}/{total} ({share}) of its training-set fitted "
              "probabilities outside [{lower}, {upper}] (min={low}, "
              "max={high}). That is quasi-separation — the outcome is nearly "
              "certain within some (treatment, confounder) strata and the "
              "logistic coefficients have saturated. A point estimate still "
              "comes out, but the CI is too narrow and the bias on extreme "
              "outcomes is magnified. This is the outcome model's failure "
              "mode, the counterpart of the treatment-assignment model that "
              "`propensity_overlap_violation` checks.",
        "zh": "Backdoor 后门 logistic 模型 P({outcome}=1 | {features}) 的训练集预测概率在 "
              "{outside}/{total}（{share}）个观测上落在 [{lower}, {upper}] "
              "之外（min={low}, max={high}）。这是 quasi-separation 信号——结果在某些 "
              "(treatment, confounder) 子层近乎确定，logistic 系数已饱和。点估计仍能算出但 CI 偏窄、对"
              "极端结局的偏差放大。这是 outcome 模型的失败模式，与 `propensity_overlap_violation` "
              "检查的 treatment assignment 模型互补。"},
    "every_stratum_should_have_both_arms_and_some_do_not": {
        "en": "the adjustment set {adjustment} cuts this sample into {cells} "
              "strata, and {bad} of them hold a single treatment arm, "
              "carrying {share} of the sample: {strata}. Positivity (Hernan & "
              "Robins ch.3) asks for units in both arms inside every stratum; "
              "where one is absent the outcome model supplies it from the "
              "slope it learned in the other strata, and that part of the "
              "answer is not a comparison the data made.",
        "zh": "调整集 {adjustment} 在这份样本里划出 {cells} 个层，其中 {bad} 个只含一个处理臂，占样本 "
              "{share}：{strata}。positivity（Hernan & Robins ch.3）要求每一层内两个臂都有个"
              "体；这些层里缺的那一臂，是结局模型拿别的层的斜率外推出来的——答案的那一部分不是数据里的对比。"},
    "the_fitted_propensity_leaves_part_of_the_sample_unsupported": {
        "en": "the fitted propensity P({treatment}=1 | {adjustment}) puts "
              "{outside}/{total} observations outside [{lower}, {upper}] "
              "({share}; min {low}, max {high}). Hernán & Robins ch.3, "
              "'positivity': every confounder stratum should hold both "
              "treated and untreated units. A back-door / g-formula estimate "
              "extrapolates the outcome regression into the region with no "
              "support — and that part of the answer is a model assumption "
              "rather than a causal estimate.",
        "zh": "估计出的倾向性 P({treatment}=1 | {adjustment}) 有 {outside}/{total} 个观"
              "测落在 [{lower}, {upper}] 之外（{share}；最小 {low}，最大 {high}）。Hernan & "
              "Robins ch.3 'positivity'：每个混杂分层里都该同时有受处理和未受处理的个体。后门 / "
              "g-formula 的估计会把结局回归外推到没有支撑的那片区域——答案的那一部分不是真正的因果估计，只是模型假设。"},
    "the_sample_could_not_be_cut_into_the_strata_the_wald_needs": {
        "en": "the instrument `{instrument}` is valid only given "
              "{{{conditioning}}}, and what that identifies is the stratified "
              "Wald — the effect among compliers. This sample cannot be cut "
              "that way: {reason}. So the number reported is the 2SLS "
              "coefficient, which weights each stratum's effect by how hard "
              "the instrument moves treatment there rather than by that "
              "stratum's share of compliers. The two coincide only when the "
              "first stage is equally strong in every stratum; otherwise they "
              "are two different quantities, not two estimates of one.",
        "zh": "工具 `{instrument}` 只在给定 {{{conditioning}}} 时才有效，那对应的是分层 Wald——顺"
              "从者中的效应。这份样本没法这样切分：{reason}。所以报出来的数是 2SLS 系数，它给每一层的效应加的权，是工具在那一"
              "层把处理推动得有多强，而不是那一层顺从者的占比。两者只有在第一阶段每层一样强时才重合；否则它们是两个不同的量，而不是同一个量"
              "的两种估计。"},
    "the_first_stage_is_weak": {
        "en": "the first stage of the instrument `{instrument}` is F = {f}, "
              "below Stock-Yogo's (2005) threshold of {threshold}. The IV "
              "estimate's bias toward OLS scales as 1/F, and with a weak "
              "first stage the bootstrap CI on 2SLS / Wald is unreliable too. "
              "Read the point estimate as a rough bearing, not as a tight "
              "identification.",
        "zh": "工具 `{instrument}` 的第一阶段 F = {f}，低于 Stock-Yogo (2005) 的阈值 "
              "{threshold}。IV 估计朝 OLS 偏的幅度按 1/F 放大，第一阶段弱的时候 2SLS / Wald 的 "
              "bootstrap 置信区间也不可靠。把这个点估计当成粗略参考，不要当成一次紧致的识别。"},
    "the_joint_first_stage_is_weak": {
        "en":
              "the joint first stage of the instrument set {instruments} is F "
              "= {f}, below Stock-Yogo's (2005) threshold of {threshold}. An "
              "overidentified 2SLS estimate is biased toward OLS, and when "
              "the set is jointly weak the bootstrap CI is unreliable too.",
        "zh": "工具组 {instruments} 的联合第一阶段 F = {f}，低于 Stock-Yogo (2005) 的阈值 "
              "{threshold}。过度识别的 2SLS 估计会朝 OLS 偏，而且这组工具联合起来弱的时候，bootstrap 置信区"
              "间也不可靠。"},
    "the_anderson_rubin_set_is_this": {
        "en": "the Anderson-Rubin {level}% weak-instrument-robust confidence "
              "set (valid whatever the instrument's strength) is {interval}.",
        "zh": "Anderson-Rubin {level}% 弱工具稳健置信集（不管工具多强都有效）是 {interval}。"},
    "the_multi_instrument_anderson_rubin_set_is_this": {
        "en": "the multi-instrument Anderson-Rubin {level}% "
              "weak-instrument-robust confidence set (valid however strong "
              "the set is jointly) is {interval}.",
        "zh": "多工具 Anderson-Rubin {level}% 弱工具稳健置信集（不管这组工具联合起来多强都有效）是 "
              "{interval}。"},
    "the_heteroskedasticity_robust_anderson_rubin_set_is_this": {
        "en": "the heteroskedasticity-robust Anderson-Rubin {level}% set "
              "(valid under weak instruments *and* heteroskedasticity) is "
              "{interval}.",
        "zh": "异方差稳健的 Anderson-Rubin {level}% 集（在弱工具「且」异方差下都有效）是 {interval}。"},
    "the_set_constrains_nothing": {
        "en": "that set is the whole real line: at this level every value "
              "of the effect is consistent with these data, so the "
              "instrument constrains nothing here. An unbounded set is a "
              "finding rather than a missing number — it is exactly what a "
              "bootstrap CI conceals when the first stage is weak.",
        "zh": "这个集合是整条实线：在这个水平上，效应的每一个取值都与这批数据相容，"
              "所以工具在这里什么也约束不住。无界是结论，不是缺数——第一阶段弱的时候，"
              "bootstrap 置信区间掩盖的正是这件事。"},
    "the_overidentification_test_refuted_the_instruments": {
        "en":
              "the {test} overidentification test rejected the joint validity "
              "of the instrument set {instruments} (J = {j}, df = {df}, p = "
              "{p}). At least one exclusion restriction contradicts the "
              "others in the data — the set the IV point estimate rests on "
              "has been refuted by it. This is a falsification and not a "
              "shortfall of data: more of the same refutes it again.",
        "zh":
              "{test} 过度识别检验「否决」了工具组 {instruments} 的联合有效性（J = {j}，df = {df}，p "
              "= {p}）。至少有一条排他性限制与数据里的其他限制互相矛盾——IV 点估计所依赖的这组工具，被数据反驳了。这是一次证伪，不"
              "是数据量不够的缺口：再多同样的数据也不会让它消失。"},
    "the_homoskedastic_sargan_says_the_same": {
        "en": "the homoskedastic Sargan gives J = {j}, p = {p}.",
        "zh": "同方差 Sargan 检验给的是 J = {j}，p = {p}。"},
    "declared_continuous_but_the_column_is_discrete": {
        "en": "the variable `{variable}` is declared continuous, but the "
              "column holds only {count} distinct values ({values}) — any "
              "dose-response estimand collapses to a discrete two-level "
              "contrast and yields no curve.",
        "zh": "变量 `{variable}` 声明为连续，但这一列只有 {count} 个不同取值（{values}）——任何剂量-反应估"
              "计量都会塌成离散的两档对比，给不出一条曲线。"},
    "declared_binary_but_the_column_has_more_levels": {
        "en":
              "the variable `{variable}` is declared binary (two levels), but "
              "the column holds {count} distinct values — the g-formula will "
              "treat it as a multi-level or continuous exposure rather than "
              "as a two-arm contrast.",
        "zh": "变量 `{variable}` 声明为二值（两档），但这一列有 {count} 个不同取值——g-formula 会把它当多"
              "档 / 连续暴露处理，而不是两臂对比。"},
    "declared_discrete_but_the_values_form_a_continuum": {
        "en": "the variable `{variable}` is declared discrete, but its "
              "{count} values form a continuous scale.",
        "zh": "变量 `{variable}` 声明为离散，但这一列的 {count} 个取值构成连续尺度。"},
    "the_column_holds_values_the_declaration_does_not_list": {
        "en": "the column for `{variable}` holds values outside the declared "
              "domain {domain}: {extra}.",
        "zh": "变量 `{variable}` 这一列出现了声明取值范围 {domain} 之外的值：{extra}。"},
    "the_number_answers_a_different_estimand_than_declared": {
        "en": "the number was still computed off the coerced data, but the "
              "estimand it answers is not the one the declaration promised — "
              "align the declared scale or domain with the data and only then "
              "does the number read as the quantity that was declared.",
        "zh": "数还是照着强制转换后的数据算出来了，但它回答的估计量和声明承诺的不是同一个——把声明的尺度 / 取值范围和数据对齐之后，这个"
              "数才能当成声明的那个量来读。"},
    "this_column_is_not_in_this_estimand": {
        "en": "this column is not in this query's estimand, so it changes no "
              "number here. What it reports is that **the program's "
              "declaration** and the data disagree — any query that does use "
              "`{variable}` is affected by it; this one is not.",
        "zh":
              "这一列不在本查询的估计量里，所以它不改变这里的数。它说的是**程序的声明**与数据不符——任何用到 `{variable}` "
              "的查询都会被它影响，这一份不会。"},
    "the_proxies_are_finer_than_the_declared_cardinality": {
        "en": "Miao's formula (5) recovers the effect by inverting a "
              "`{k}`x`{k}` measurement channel between the two proxies, so "
              "each of them has to present exactly `{k}` levels — the "
              "cardinality the query posits for the unobserved confounder "
              "`{latent}`. `{z}` presents {z_levels} and `{w}` presents "
              "{w_levels}, so the channel this estimate would invert does "
              "not exist yet.",
        "zh": "Miao 公式 (5) 靠反演两个代理之间的 `{k}`×`{k}` 测量通道来恢复"
              "效应，所以每个代理都要恰好呈现 `{k}` 个层级——也就是这个查询"
              "为未观测混杂 `{latent}` 假定的类别数。`{z}` 有 {z_levels} 个，"
              "`{w}` 有 {w_levels} 个，要反演的那个通道还不存在。"},
    "the_proxies_show_fewer_states_than_the_latent_has": {
        "en": "Recovering a number for `{treatment}` on `{outcome}` means "
              "inverting the measurement channel between `{z}` and `{w}` — "
              "that inversion is what stands in for the confounder "
              "`{latent}`, which nobody measured. The query posits {k} "
              "states for `{latent}`, and `{z}` takes {z_levels} value(s): a "
              "proxy with fewer levels than U has states cannot tell them "
              "apart, so there is no channel to invert. More rows do not "
              "repair this — it is a limit of what was measured, not of how "
              "much of it there is.",
        "zh": "要得到 `{treatment}` 对 `{outcome}` 的一个数，就得反演 `{z}` "
              "与 `{w}` 之间的测量通道——正是这次反演替代了没人测到的混杂 "
              "`{latent}`。查询假定 `{latent}` 有 {k} 个状态，而 `{z}` 只取 "
              "{z_levels} 个值：层级数比 U 的状态数还少的代理分辨不开这些状"
              "态，也就没有通道可反演。加数据没有用——这是「测了什么」的限"
              "制，不是「测了多少」的限制。"},
    "the_proxy_channel_is_singular": {
        "en": "The channel between `{z}` and `{w}` has the {k} levels it "
              "needs and still will not invert: on this sample the levels "
              "carry the same information about `{latent}` more than once, "
              "so one of its {k} states has no independent row of its own. "
              "What is short is what `{z}` DISTINGUISHES, not how many "
              "values it takes.",
        "zh": "`{z}` 与 `{w}` 之间的通道层级数够了（{k} 个），却仍然反演不"
              "了：在这份数据上，这些层级关于 `{latent}` 的信息是重复的，于"
              "是 {k} 个状态里有一个没有属于自己的独立一行。缺的是 `{z}` 能"
              "「分辨」什么，而不是它能取多少个值。"},
    "the_discrete_contrast_needs_two_arms": {
        "en": "Formula (5)'s answer is a contrast — what `{outcome}` would "
              "be under one level of `{treatment}` minus what it would be "
              "under another — and `{treatment}` has {levels} levels here, "
              "so there is no one pair for it to be the contrast between. "
              "The channel itself is sound; what does not fit is the shape "
              "of the answer.",
        "zh": "公式 (5) 给出的是一个对比——`{outcome}` 在 `{treatment}` 的某"
              "一层级下会是多少，减去在另一层级下会是多少——而这里 "
              "`{treatment}` 有 {levels} 个层级，没有哪一对能充当这个对比的"
              "两端。通道本身没问题，不合的是答案的形状。"},
    "a_test_of_the_null_is_what_is_left": {
        "en": "What ran instead tests one thing: whether `{treatment}` "
              "affects `{outcome}` at all, at any state of `{latent}`. A "
              "small p-value is evidence that it does — and says nothing "
              "about how much, in which direction, or for whom. A large one "
              "is not evidence that the effect is zero; it is the absence of "
              "evidence that it is not. Read it as a yes/no about existence, "
              "never as an effect size that came out small.",
        "zh": "实际跑的是另一件事：检验 `{treatment}` 对 `{outcome}` 到底有"
              "没有影响——在 `{latent}` 的任何状态下。p 值小，是「有影响」的"
              "证据，但完全不说明影响有多大、朝哪个方向、对谁而言。p 值大，"
              "并不是「影响为零」的证据，只是没有证据说它不为零。请把它当成"
              "关于「有没有」的是非题，而不是一个算出来很小的效应量。"},
    "which_levels_are_one_state_is_not_in_the_data": {
        "en": "A finer proxy CAN be folded down to `{k}` groups — a "
              "conditional independence survives any function of the "
              "variable it holds for, so a grouped proxy still satisfies "
              "the model-(f) criteria, and in the population every grouping "
              "whose folded channel keeps full rank identifies the same "
              "effect. In a finite sample they do not: a different grouping "
              "is a different matrix and a different number. Nothing "
              "observed says that two levels of `{z}` are the same state of "
              "a variable nobody measured, so the estimator will not pick a "
              "grouping on your behalf — declare it and it is recorded as "
              "your choice.",
        "zh": "更细的代理**可以**折到 `{k}` 组——条件独立性在变量的任何函数"
              "下都保持，所以折过的代理仍满足 model (f) 的判据，而且在总体上"
              "任何折出满秩通道的分组都识别同一个效应。有限样本里则不然：换"
              "一个分组就是另一个矩阵、另一个数。没有任何观测能说 `{z}` 的"
              "两个层级是那个谁也没测过的变量的同一个状态，所以估计器不替你"
              "挑分组——你声明它，它就作为你的选择被记录下来。"},
    "the_treatment_is_inside_a_declared_loop": {
        "en": "the program declares that `{left}` and `{right}` cause each "
              "other, and setting `{treatment}` does not cut that loop — "
              "`{outcome}` is still downstream of it afterwards. So "
              "`{treatment}` is not exogenous here by construction, and "
              "that is a different problem from confounding: a confounder "
              "is a variable you could have measured, and this is a second "
              "equation.",
        "zh": "程序里声明了 `{left}` 与 `{right}` 互为因果，而把 "
              "`{treatment}` 设定住并不能切断这个环——干预之后 "
              "`{outcome}` 仍在它的下游。所以 `{treatment}` 在这里"
              "**按构造**就不是外生的，这跟混杂是两回事：混杂是一个你本"
              "可以测到的变量，而这是第二个方程。"},
    "adjustment_cannot_remove_a_feedback": {
        "en": "No adjustment set closes this. Controlling for a covariate "
              "blocks a path, and a feedback the treatment is part of is "
              "not a path to block — the back-door number would still be "
              "an answer to a different question. The front-door escape is "
              "gone for the same reason one step down: every mediator on a "
              "path from `{treatment}` to `{outcome}` sits inside the loop.",
        "zh": "没有任何调整集能补上这一点。控制一个协变量是**堵住一条路**，"
              "而处理变量自己参与其中的反馈不是一条可以堵的路——照 backdoor "
              "算出来的数依然是在回答另一个问题。前门那条逃生路也因为同一个"
              "原因不成立：从 `{treatment}` 到 `{outcome}` 的路径上的每一个"
              "中介，都在这个环里面。"},
    "the_number_is_a_single_equations_coefficient": {
        "en": "`{left}` and `{right}` were declared to cause each other, so "
              "the number beside this is the structural coefficient of "
              "`{treatment}` in the `{outcome}` equation — recovered "
              "through `{instrument}` — and NOT the equilibrium the pair "
              "settles at when "
              "`{treatment}` is moved and `{outcome}` moves it back. It "
              "rests on the system being linear: without that a cyclic "
              "model need not even have a unique interventional "
              "distribution.",
        "zh": "`{left}` 与 `{right}` 被声明为互为因果，所以旁边这个数是 "
              "`{outcome}` 那条方程里 `{treatment}` 的**结构系数**（通过 "
              "`{instrument}` 恢复出来），**不是**推动 `{treatment}`、"
              "`{outcome}` 再反推回来之后这一对最终停在的那个均衡值。它靠的"
              "是这个系统是线性的：没有线性，有环模型连唯一的干预分布都未必"
              "存在。"},
    "the_loop_has_to_be_settled_before_any_of_these": {
        "en": "this layer works ON an effect the DAG identifies — carrying "
              "it to another population, splitting it through a mediator, "
              "intervening on several treatments at once — and the declared "
              "loop means there is no such effect yet to work on. Settle "
              "the loop and this layer becomes available again on whatever "
              "the answer then is.",
        "zh": "这一层做的是**拿一个 DAG 已经识别出来的效应**再往下加工——迁到"
              "另一个总体、按中介拆开、同时干预好几个处理——而声明的这个环"
              "意味着现在还没有那个效应可加工。把环处理掉之后，这一层对新的"
              "答案又可用了。"},
    "the_bridge_equation_has_no_solution_without_a_penalty": {
        "en": "With continuous proxies the effect comes from solving "
              "`E[h(W, X) | Z, X] = E[Y | Z, X]` for the bridge `h`. That is "
              "an integral equation of the first kind: the left side smooths, "
              "so inverting it amplifies, and two datasets that differ by "
              "almost nothing can have bridges that differ by a lot. It has "
              "no numeric solution at all without a regularisation term — the "
              "penalty is not a knob somebody left turned, it is what makes "
              "the problem solvable.",
        "zh": "代理是连续变量时，效应是通过解 "
              "`E[h(W, X) | Z, X] = E[Y | Z, X]` 里的 bridge 函数 `h` 得到"
              "的。这是第一类积分方程：左边是平滑算子，求逆就会放大，两份差"
              "别极小的数据可以对应差别很大的 `h`。不加正则化项它根本没有数"
              "值解——这一项不是谁忘了关的旋钮，它是让问题可解的东西。"},
    "the_penalty_moved_it_further_than_noise_did": {
        "en": "At the penalty in force the answer sits {bend} away from the "
              "least-penalised solve available, while sampling moves it about "
              "{noise}. The first number being the larger is what makes this "
              "a fact about `{treatment}` and `{outcome}` on this sample "
              "rather than a general remark about the method.",
        "zh": "在当前这个正则化强度下，答案离「penalty 最轻的那次求解」相差 "
              "{bend}，而抽样本身带来的波动大约是 {noise}。前者比后者大，才"
              "使得这条不是关于方法的一般性提醒，而是关于这份数据上 "
              "`{treatment}` 与 `{outcome}` 的一个事实。"},
    "a_lighter_penalty_has_no_solution_here": {
        "en": "A lighter penalty leaves the system with no solution this "
              "estimator will take — so the number exists BECAUSE of the "
              "penalty rather than in spite of it, which says the same thing "
              "as the comparison above and says it more strongly.",
        "zh": "更轻的正则化会让这个系统落到估计器不肯求解的病态程度——也就是"
              "说，这个数是**因为**有正则化才存在的，不是顶着它存在的。这和"
              "上面那条比较说的是同一件事，只是说得更重。"},
    "a_reciprocal_probability_cannot_be_negative": {
        "en": "The treatment bridge `q` is defined as one over a "
              "probability, so it is at least one wherever it is defined. "
              "The sieve solving for it is linear in its parameters and "
              "knows nothing of that, so where the declared span cannot hold "
              "a function of the right shape the fit dips below zero — and a "
              "row with a negative `q` contributes a negative weight to an "
              "average of the outcome, which is not an average of anything.",
        "zh": "处理桥 `q` 的定义是「一除以一个概率」，所以它处处 ≥ 1。求解它"
              "的 sieve 对参数是线性的，并不知道这件事；当声明的那个空间装不"
              "下这种形状的函数时，拟合出来就会掉到零以下——而一行上的 `q` "
              "为负，意味着它在对结局求平均时贡献一个**负权重**，那就不再是"
              "任何东西的平均了。"},
    "the_fitted_treatment_bridge_went_negative": {
        "en": "On this sample the fitted `q` came out below zero on {treated} "
              "of the treated rows and {control} of the control rows. That "
              "share is what makes this a fact about `{treatment}` and "
              "`{outcome}` here rather than a general remark about linear "
              "sieves.",
        "zh": "在这份数据上，拟合出来的 `q` 在处理组有 {treated}、对照组有 "
              "{control} 的行落到了零以下。正是这个比例使得这条不是关于线性 "
              "sieve 的一般性提醒，而是关于这里 `{treatment}` 与 "
              "`{outcome}` 的一个事实。"},
    "the_fitted_treatment_bridge_went_negative_at_a_level": {
        "en": "On this sample the fitted `q` came out below zero on {share} "
              "of the rows at dose {level} — the worst of the {levels} doses "
              "the curve is drawn at. That share is what makes this a fact "
              "about `{treatment}` and `{outcome}` here rather than a "
              "general remark about linear sieves, and the level is what "
              "says whether one point of the curve is affected or all of "
              "them.",
        "zh": "在这份数据上，拟合出来的 `q` 在剂量 {level} 那一档有 {share} "
              "的行落到了零以下——这是曲线上 {levels} 个剂量里最差的一档。"
              "正是这个比例使得这条不是关于线性 sieve 的一般性提醒，而是关于"
              "这里 `{treatment}` 与 `{outcome}` 的一个事实；而说出是哪一档，"
              "是为了让你知道受影响的是曲线上的一个点还是整条曲线。"},
    "a_cyclic_model_need_not_have_this_quantity": {
        "en": "The loop is not between `{treatment}` and `{outcome}` "
              "themselves, so the two-equation reduction that an instrument "
              "rescues does not apply here — that result is about a system "
              "of two equations, and borrowing it for this shape would be "
              "inventing one. Nor is this the usual 'no adjustment set was "
              "found': a cyclic model need not have a solution at all, and "
              "when it does the interventional distribution need not be "
              "unique, so the quantity a DAG would identify may not exist "
              "here to be identified.",
        "zh": "这个环并不在 `{treatment}` 和 `{outcome}` 之间，所以工具变量"
              "能救回来的那个两方程化简在这里不适用——那个结论讲的是**两个"
              "方程**的系统，套到这个形状上就是编。这也不是通常那种「找不到"
              "调整集」：有环的模型可能根本没有解，即使有，干预分布也未必唯"
              "一，所以 DAG 会识别的那个量在这里可能压根不存在。"},
}
"""What each statement says, in every language this build writes.

Total over :class:`Sentence` by construction — a species with no text is a
statement nothing can say, and the gate holds the two equal. The prose is
the prose the builders wrote; what changed is who owns it and when it is
rendered.
"""



def occasion(**details) -> dict:
    """What this gap is about, as the two keys a gap carries it in.

    The writer's door. Splatted into :class:`themis.types.DataGap` rather
    than handed over as two arguments, because the pair is one fact and a
    caller free to pass one half is a caller who will.
    """
    said, words = language.halve(details)
    return {"said": said, "words": words}


def occasion_fields(gap) -> dict:
    """A gap's occasion as the keys it takes on an envelope — the
    serializer's half, stating "there is nothing here" once for both."""
    out: dict = {}
    said, words = _read(gap, "said"), _read(gap, "words")
    if said:
        out["said"] = dict(said)
    if words:
        out["words"] = dict(words)
    return out


def if_provided(gap, lang: language.Lang | str = language.DEFAULT) -> str:
    """What having the missing thing would buy this reader, or "".

    Empty for a species :data:`NOTHING_FILLS` answers for, and for one this
    build has never heard of — the reader's fact is the same either way
    (there is no such line), and inventing one would promise that
    something they could go and get changes this.
    """
    kind = language.token(_read(gap, "kind"))
    words = IF_PROVIDED.get(str(kind))
    if words is None:
        return ""
    return language.assemble(
        words, _read(gap, "said"), _read(gap, "words"), lang)


def sentence(name, **details) -> GapSentence:
    """One statement of a gap's description, in the one shape it takes.

    The writer's door. A description is a LIST of these because which
    statements it has is what this occasion knows — see :class:`Sentence`.
    """
    member = BY_SENTENCE.get(str(name))
    if member is None:
        raise ValueError(
            f"{name!r} is not a statement in themis.gaps.Sentence; what a "
            f"gap says about itself is named there before it is said, so "
            f"that a surface can assemble it in the reader's language"
        )
    if str(member) not in DESCRIBES:
        raise ValueError(
            f"{member} has no text in themis.gaps.DESCRIBES; declare it "
            f"there, beside the statement, so the wording has one author"
        )
    said, words = language.halve(details)
    return GapSentence(sentence=member, said=said, words=words)


def sentence_fields(entry) -> dict:
    """One statement as the keys it takes on an envelope."""
    out: dict = {"sentence": str(entry.sentence)}
    if entry.said:
        out["said"] = dict(entry.said)
    if entry.words:
        out["words"] = dict(entry.words)
    return out


#: The name a gap's statements answer to on an envelope.
#:
#: :data:`DESCRIBES` was already a token-to-words table; what it lacked was
#: a name, so a statement built out of it could be resolved by this module
#: and by nothing else. That is fine while these only ever travel inside a
#: gap, whose own shape says which table to read — and it stops being fine
#: the moment one has to go somewhere a gap's shape does not reach. The
#: ledger line for an unverified edge IS these sentences, and it used to
#: reach the envelope as a paragraph rendered here.
DESCRIBED = "gap_describes"
language.declare(DESCRIBED, DESCRIBES, language.BETWEEN_SENTENCES)

#: The name a shortfall's own sentence answers to on an envelope.
#:
#: Its twin above got one first because something needed it first. This one
#: is what a gap's sentence puts in a hole: five of them say "the route
#: failed: {why}", and the why IS a shortfall. Without a name the only thing
#: that could go in that hole was :func:`said`'s output — the sentence,
#: rendered, in whichever language the producer had been handed.
NEEDED = "gap_says"
language.declare(NEEDED, SAYS, language.BETWEEN_STATEMENTS)


def shortfall(item) -> "language.Statement | str":
    """One shortfall as another sentence's hole holds it.

    :func:`said` is the same fact rendered, and rendering it was what a
    caller had to do: a hole holds a value or a WORD, and a word is a
    vocabulary and a token — which this table had no name to be.

    Both kinds come back from here, because both are what the hole can
    hold. An item with a species is the statement; one without is the name
    it was filed under, which is the caller's own and reads the same to
    every reader. Reading either shape for the same reason :func:`said`
    does: which side of the serialization boundary a caller is on is not
    its question.
    """
    if isinstance(item, Mapping):
        tok, values, words = (item.get("need"), item.get("said"),
                              item.get("words"))
        target = item.get("target")
    else:
        tok, values, words = item.need, item.said, item.words
        # The name is the INVESTIGATION item's; a missing item always has a
        # species, so the fallback is only reachable on the channel that
        # can be short of one.
        target = getattr(item, "target", None)
    if not tok:
        return str(target or "")
    return language.restate(
        {"need": tok, "said": values, "words": words}, NEEDED, "need")


def sentence_entry(entry: Mapping) -> "GapSentence | None":
    """One statement read back off an envelope."""
    member = stated(entry)
    if member is None:
        return None
    return GapSentence(
        sentence=member,
        said=dict(entry.get("said") or {}),
        words=dict(entry.get("words") or {}),
    )


def stated(entry) -> "Sentence | None":
    """Which statement this entry is, off either shape."""
    tok = entry.get("sentence") if isinstance(entry, Mapping) else getattr(
        entry, "sentence", None)
    return BY_SENTENCE.get(str(tok)) if tok else None


def describe(entry, lang: language.Lang | str = language.DEFAULT) -> str:
    """One statement, as the sentence this reader gets."""
    member = stated(entry)
    if member is None:
        tok = entry.get("sentence") if isinstance(entry, Mapping) else getattr(
            entry, "sentence", "")
        return language.gloss({}, str(tok or ""), lang)
    if isinstance(entry, Mapping):
        values, words = entry.get("said"), entry.get("words")
    else:
        values, words = entry.said, entry.words
    return language.assemble(DESCRIBES[str(member)], values, words, lang)


def described(gap, lang: language.Lang | str = language.DEFAULT) -> str:
    """What a gap says about itself, as one paragraph for this reader.

    The seam between two statements belongs to the language and not to
    either statement — which is why it is here and not baked into the
    texts. It was baked into them: one carried a leading space so that the
    English sentence before it would not run on, and in Chinese that space
    reached the reader as a gap mid-paragraph.
    """
    return language.sentences(
        *(describe(entry, lang) for entry in _read(gap, "describes") or ()),
        lang=lang)


#: The one-line summary a reader is led with, and the two frames around it.
#:
#: These were a field on the report, and every input to that field was on
#: the report beside it: the gaps, sorted, and the answer tier. The head of
#: the summary WAS the first gap's description — a rendering of a rendering,
#: and the second reason a description could not be a list of statements
#: while it lived on the envelope.
SUMMARY_WITH_BLOCKING: language.Words = {
    "zh": "{head}（共 {blocking} 个 blocking 缺口）",
    "en": "{head} ({blocking} blocking gaps in all)",
}
SUMMARY_INTERVAL_AVAILABLE: language.Words = {
    "zh": "可得区间估计（点识别被阻断，但有信息性 bounds）：{base}",
    "en": "an interval is available (point identification is blocked, but "
          "the bounds are informative): {base}",
}
SUMMARY_NEITHER: language.Words = {
    "zh": "图+数据无法给出点或区间估计（需补假设或更强数据）：{base}",
    "en": "the graph and the data give neither a point nor an interval "
          "(this needs a further assumption, or stronger data): {base}",
}


def summary(gaps, answer_tier=None,
            lang: language.Lang | str = language.DEFAULT) -> str:
    """The one line a reader is led with, assembled where they are.

    Leads with what the answer HAS, because a blocking gap read on its own
    says "no answer" when an interval is in hand.
    """
    gaps = list(gaps or ())
    if not gaps:
        return ""
    base = described(gaps[0], lang)
    blocking = sum(1 for gap in gaps
                   if _read(gap, "severity") == GapSeverity.BLOCKING)
    if blocking > 1:
        base = language.fill(SUMMARY_WITH_BLOCKING, lang,
                             head=base, blocking=blocking)
    tier = language.token(answer_tier) if answer_tier is not None else ""
    if tier == "interval":
        return language.fill(SUMMARY_INTERVAL_AVAILABLE, lang, base=base)
    if tier == "none":
        return language.fill(SUMMARY_NEITHER, lang, base=base)
    return base


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
        and language.token(_read(gap, "kind")) in IF_PROVIDED
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
            skeleton: dict | None = None,
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
        skeleton=skeleton,
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
