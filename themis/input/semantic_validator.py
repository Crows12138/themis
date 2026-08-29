"""Semantic validation of a syntactically-valid AST.

This layer enforces rules that cannot be expressed in the JSON Schema.
Two entry points exist, distinguished by what they need:

``validate_program(ast, checks=...)`` — dict-level checks that do not
require the compiled working graph. These run before instantiation.

``validate_against_graph(ground_statements, graph, checks=...)`` —
post-instantiation checks that reference ``G(M)``. These run after
``instantiation.instantiate`` + ``graph_projection.project``.

Program-level (pre-graph) checks:

- ``objects``:            every constant in an atom is declared in D.
- ``forall_usage``:       every forall variable is actually used in
                          the statement's atoms.
- ``bound_variables``:    every VarTerm in cause / probability
                          statements is declared in forall.
- ``ground_observations``: observation atoms contain no VarTerm.
- ``ground_queries``:     query atoms contain no VarTerm (v0.1 only
                          answers ground queries; patterned queries
                          are out-of-language for now).

Graph-level (post-projection) checks:

- ``probability_parents``: probability.given ⊆ parents(target) in
                          G(M). Prevents probability statements whose
                          conditioning set is incompatible with the
                          declared causal structure from silently
                          feeding Theta and corrupting identification.
- ``query_atoms_in_V``:    every atom referenced by a cause / assoc /
                          identify / effect query is a node in G(M).
                          Probability queries are intentionally exempt
                          — they are pure distributional lookups and
                          may reference atoms that live only in Theta.

Reserved for later slices:

- ``formula_wellformed``:  no free value variables, sum.over ground
  (already callable as ``validate_formula``)

On success ``validate_program`` returns a typed ``Program`` object;
``validate_against_graph`` returns nothing.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Callable, NamedTuple

from .. import language
from ..ledger import Monotonicity
from ..types import (
    Annotation,
    AssocQuery,
    Atom,
    BidirectedStatement,
    FeedbackLoop,
    SelectionNode,
    MissingnessIndicator,
    CausationQuery,
    CounterfactualAssumptions,
    CounterfactualConjunctionQuery,
    ProximalEffectQuery,
    CounterfactualEvent,
    CounterfactualQuery,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    EffectQueryAssumptions,
    IdentifyQuery,
    Intervention,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    QueryKind,
    QUERY_KIND_OF,
    RelativeTimeIndex,
    SIEVE_MINIMUM_DIMENSION,
    SieveTerm,
    QueryStatement,
    SCMCounterfactualQuery,
    Term,
    ValuedAtom,
    VariableDeclaration,
    VarTerm,
)

SLICE_1_CHECKS: frozenset[str] = frozenset(
    {
        "objects",
        "forall_usage",
        "bound_variables",
        "feedback_loops",
        "ground_observations",
        "ground_queries",
        "unique_variable_declarations",
        "bidirected_runtime_gate",
        "transport_runtime_gate",
        "temporal_monotonicity",
        # Fix 3+4 (v0.1.5): llm_prior provenance demands a non-empty
        # annotations.source so the audit-trail review surface
        # (extensions.llm_proposed_review) has a reason string per
        # entry. Empty / null source on llm_prior would let LLM
        # silently launder fabricated numbers without disclosure.
        "llm_prior_requires_source",
        # A proximal sieve design against the roles the same query gave the
        # same variables. Every one of these is two declarations of one
        # program disagreeing, so none of it needs data — and left to the
        # estimator each would surface as a missing column or a singular
        # matrix, in a vocabulary about matrices rather than the question.
        "proximal_sieve_design",
    }
)


class Malformed(language.Word, vocabulary="malformed_program"):
    """Why a program cannot be run at all, as the sentence that says so.

    Every member here is addressed to whoever wrote the program, and until
    this vocabulary existed each was an f-string at its own raise site —
    which made the checker the author of the wording and therefore the
    chooser of its language. Twenty of them reached a person that way,
    through ``/api/*``'s ``diagnostic`` field, in English, underneath a
    stage sentence the browser had already been given in both.

    A ``Word`` rather than a table because the tokens are ours and a raise
    site names one, the discipline :class:`themis.refusals.Refusal` is held
    to for the refusals one layer down. The two channels are the same shape
    for the same reason: this one refuses a PROGRAM and that one refuses to
    put a number on a well-formed program, and a reader meets both as "here
    is why you did not get an answer".

    **What is not here is as decided as what is.** A citation of this
    repository's own charters — ``Phase 5 §T / T1``, ``wall.md iter 150``
    — was inside four of these messages, and a document the reader cannot
    open is not part of the reason they were refused; it is a note to
    whoever maintains the check, and the member's own name is where that
    now points. Nor are the invariants here: a dispatch table that meets a
    kind it has no branch for is asserting, not refusing, and those raise a
    builtin now — the syntax this package already uses to tell the two
    apart.
    """

    # --- the query asks for something this build cannot pose --------------
    BRIDGE_UNDER_DETERMINED = ("bridge_under_determined", {
        "zh": "近端 {bridge}：矩条件只有 {moments} 个，未知数有 {unknowns} 个。"
              "方程比未知数少，那不是病态求解，是欠定——加惩罚项也只是从"
              "无穷多个解里挑一个出来，而不是把它定下来",
        "en": "proximal {bridge}: {moments} moments against {unknowns} "
              "unknowns. Fewer equations than unknowns is not an "
              "ill-conditioned solve but an under-determined one — a penalty "
              "would pick one of infinitely many solutions rather than pin "
              "the solution down",
    })
    TREATMENT_BRIDGE_NOT_DECLARED = ("treatment_bridge_not_declared", {
        "zh": "estimator 选的是 {estimator}，它要读处理桥 q，而这个查询只声明了"
              "结局桥。q 活在 (Z, C) 的函数里、在 (W, C) 的矩上被检验，"
              "正好和 h 反过来；没有它，能算的只有 outcome_regression",
        "en": "the estimator asked for is {estimator}, which reads the "
              "treatment bridge q, and this query declares only the outcome "
              "bridge. q spans (Z, C) and is tested at moments of (W, C) — "
              "the mirror of h — and without it the only answer available is "
              "outcome_regression",
    })
    TREATMENT_BRIDGE_UNUSED = ("treatment_bridge_unused", {
        "zh": "查询声明了处理桥 q，而 estimator 是 outcome_regression，"
              "它一眼都不会看 q。声明一座不进算式的桥，"
              "读的人会以为答案受它保护——要么换 estimator，要么别声明它",
        "en": "the query declares a treatment bridge and the estimator is "
              "outcome_regression, which never consults it. A bridge that "
              "does not enter the arithmetic reads as protection the answer "
              "does not have — either change the estimator or drop it",
    })
    BRIDGES_ARE_EACH_OTHERS_MIRROR = ("bridges_are_each_others_mirror", {
        "zh": "处理桥的 span 正好是结局桥取矩的那组设计，矩那一侧又正好是"
              "结局桥的 span。加上「矩不少于未知数」这条规则，两个方程组就都"
              "被逼成方阵，而由同一对设计造出来的两个方阵解出同一个数——"
              "三个估计量恒等，双稳健买到的保额是零。"
              "把任一侧加宽，两座桥才是两座桥",
        "en": "the treatment bridge spans exactly what the outcome bridge "
              "takes moments along, and takes moments along exactly the "
              "outcome bridge's span. With the rule that each bridge have at "
              "least as many moments as unknowns, that forces both systems "
              "square, and two square systems built from one pair of designs "
              "solve to the same number — the three estimators are "
              "identical and the union model insures nothing. Widen either "
              "side and the two bridges are two bridges",
    })

    # --- names that do not resolve ----------------------------------------
    # --- a sieve design the query's own roles contradict ---------------------
    # Keyed on the ROLE a side may read and not on the side's name, because
    # there are two bridges and they read the roles in opposite orders: the
    # outcome bridge spans W and takes moments of Z, the treatment bridge
    # spans Z and takes moments of W. A species per side-name would have had
    # to say "the outcome side" of a bridge whose outcome side reads Z.
    # ``{bridge}`` is the field the offending design sits in — a token from
    # the program, like ``{variable}``, and not a word this file would have
    # had to write in two languages.
    SIEVE_TERM_NAMES_A_STRANGER_TO_OUTCOME_PROXY = (
        "sieve_term_names_a_stranger_to_outcome_proxy", {
            "zh": "{bridge} 里有一项用到了 {variable}，而它既不是这个查询声明的"
                  "结局侧代理 W，也不是它的协变量 C。近端的每条等式都把 W 和 Z "
                  "放在两边——结局桥 h 是 (W, X, C) 的函数，处理桥 q 在 "
                  "(W, C) 的矩上被检验——这一侧读的是 W，处理侧代理 Z 属于另一边",
            "en": "a term in {bridge} uses {variable}, which is neither an "
                  "outcome-side proxy W this query declares nor one of its "
                  "covariates C. Every proximal equation puts W and Z on "
                  "opposite sides — h is a function of (W, X, C), q is "
                  "tested at moments of (W, C) — and this side reads W, so a "
                  "treatment-side proxy Z belongs to the other one",
        })
    SIEVE_TERM_NAMES_A_STRANGER_TO_TREATMENT_PROXY = (
        "sieve_term_names_a_stranger_to_treatment_proxy", {
            "zh": "{bridge} 里有一项用到了 {variable}，而它既不是这个查询声明的"
                  "处理侧代理 Z，也不是它的协变量 C。近端的每条等式都把 W 和 Z "
                  "放在两边——结局桥 h 在 (Z, X, C) 的矩上被检验，处理桥 q 是 "
                  "(Z, C) 的函数——这一侧读的是 Z，结局侧代理 W 属于另一边",
            "en": "a term in {bridge} uses {variable}, which is neither a "
                  "treatment-side proxy Z this query declares nor one of its "
                  "covariates C. Every proximal equation puts W and Z on "
                  "opposite sides — h is tested at moments of (Z, X, C), q is "
                  "a function of (Z, C) — and this side reads Z, so an "
                  "outcome-side proxy W belongs to the other one",
        })
    SIEVE_BASIS_TOO_NARROW = ("sieve_basis_too_narrow", {
        "zh": "{variable} 上声明了 {dimension} 个 {basis} 基函数，"
              "而这一族至少要 {minimum} 个才成立——三次样条在少于四个基函数时"
              "根本还不是三次的，钳位节点向量里放不下这个次数",
        "en": "{dimension} {basis} basis functions are declared on "
              "{variable}, and this family needs at least {minimum} to "
              "exist — a cubic spline is not cubic below four of them, "
              "because the clamped knot vector has no room for the degree",
    })
    SIEVE_LEAVES_A_PROXY_UNUSED = ("sieve_leaves_a_proxy_unused", {
        "zh": "查询声明了代理 {variables}，而 bridge 的设计里没有任何一项"
              "用到它们。一个不进设计矩阵的代理对这个数没有贡献，"
              "但识别的说法仍然把它算在内——要么给它一项，要么别声明它",
        "en": "the query declares the proxies {variables} and no term of the "
              "bridge design uses them. A proxy that does not enter the "
              "design matrix contributes nothing to the number while the "
              "identification claim still counts it — give it a term, or do "
              "not declare it",
    })
    COVARIATE_NOT_ON_BOTH_SIDES = ("covariate_not_on_both_sides", {
        "zh": "协变量 {variable} 在 {bridge} 的 span 里占了 {span_width} 列，"
              "而在它取矩的那一侧只有 {moment_width} 列。"
              "桥的等式是在给定 C 之下成立的——桥随 C 变多少，"
              "矩就得在多少个 C 的方向上取；矩这一侧张不出同样的 C，"
              "这座桥就不被这组矩条件识别",
        "en": "the covariate {variable} takes {span_width} columns in "
              "{bridge}'s span and {moment_width} on the side it is tested "
              "at. A bridge equation holds GIVEN C, so the moments have to "
              "be taken along as many directions of C as the bridge varies "
              "in; where the moment side does not span the same functions of "
              "C, this bridge is not identified by these moments",
    })
    DISCRETE_CHANNEL_TAKES_ONE_PROXY_EACH = (
        "discrete_channel_takes_one_proxy_each", {
            "zh": "离散通道求逆的是一个 k×k 的测量矩阵，两侧各要一个代理；"
                  "这个查询给了 {treatment_proxies} 个处理侧、"
                  "{outcome_proxies} 个结局侧。想同时用上多个代理，"
                  "就把 channel 换成 bridge_channel——那一侧的设计矩阵"
                  "由若干项相加而成，代理有几个都放得下",
            "en": "the discrete channel inverts one k×k measurement matrix "
                  "and takes one proxy on each side; this query gives "
                  "{treatment_proxies} on the treatment side and "
                  "{outcome_proxies} on the outcome side. To use several at "
                  "once, ask for a bridge_channel instead — that channel's "
                  "design matrix is a sum of terms and holds as many proxies "
                  "as there are",
        })
    DISCRETE_CHANNEL_TAKES_NO_COVARIATES = (
        "discrete_channel_takes_no_covariates", {
            "zh": "这个查询声明了协变量 {variables}，而离散通道的公式 (5) "
                  "里没有条件在它们之上的位置——那需要在每个 C 的层内各求逆"
                  "一次再平均，Themis 还没有实现。要在给定 C 之下作答，"
                  "请改用 bridge_channel",
            "en": "this query declares the covariates {variables}, and the "
                  "discrete channel's formula (5) has no place to condition "
                  "on them — that would mean one inversion within each level "
                  "of C and an average over them, which Themis does not "
                  "implement. To be answered given C, ask for a "
                  "bridge_channel instead",
        })
    CONST_NOT_IN_DOMAIN = ("const_not_in_domain", {
        "zh": "statements[{index}]：谓词 {predicate} 里用到的常量 {const} "
              "没有在 domain.objects 里声明",
        "en": "statements[{index}]: the constant {const} used in predicate "
              "{predicate} is not declared in domain.objects",
    })
    FORALL_VARIABLE_UNUSED = ("forall_variable_unused", {
        "zh": "statements[{index}]：forall 声明了变量 {variables}，"
              "但原子里没有用到它们",
        "en": "statements[{index}]: the forall declares variables "
              "{variables} and no atom uses them",
    })
    VARIABLE_NOT_IN_FORALL = ("variable_not_in_forall", {
        "zh": "statements[{index}]：谓词 {predicate} 里用到了变量 "
              "{variables}，而 forall 没有声明它们",
        "en": "statements[{index}]: predicate {predicate} uses the variables "
              "{variables} and the forall does not declare them",
    })
    OBSERVATION_NOT_GROUND = ("observation_not_ground", {
        "zh": "statements[{index}]：观测的原子必须是基原子，"
              "这里还带着自由变量 {variables}",
        "en": "statements[{index}]: an observation's atom has to be ground "
              "and this one still carries the free variables {variables}",
    })
    QUERY_NOT_GROUND = ("query_not_ground", {
        "zh": "statements[{index}]（{query}）：查询原子 {predicate} 在 v0.1 "
              "必须是基原子，这里还带着自由变量 {variables}",
        "en": "statements[{index}] ({query}): the query atom {predicate} has "
              "to be ground in v0.1 and still carries the free variables "
              "{variables}",
    })
    QUERY_ATOM_NOT_IN_GRAPH = ("query_atom_not_in_graph", {
        "zh": "ground_statements[{index}]（{query}）：查询用到的原子 {atoms} "
              "不在实例化出来的变量集 V 里——没有任何 cause 边引入它们",
        "en": "ground_statements[{index}] ({query}): the query references "
              "the atoms {atoms}, which are not in the instantiated variable "
              "set V — no cause edge introduces them",
    })
    QUERY_ATOM_ONLY_BIDIRECTED = ("query_atom_only_bidirected", {
        "zh": "ground_statements[{index}]（{query}）：查询用到的原子 {atoms} "
              "只出现在双向（潜混杂）边上，所以不在变量集 V 里——"
              "双向边的端点没有有向的因果角色。条件在一个纯粹被潜混杂连起来的"
              "节点上（M-bias 那个结构）不在支持范围内；如果它确实有可观测的"
              "因果角色，给它一条有向的 cause 边",
        "en": "ground_statements[{index}] ({query}): the query references the "
              "atoms {atoms}, which appear only in bidirected "
              "(latent-confounding) edges and so are not in the variable set "
              "V — a bidirected endpoint has no directed causal role. "
              "Conditioning on a purely latent-confounded node (the M-bias "
              "structure) is not supported; give the node a directed cause "
              "edge if it has an observed causal role",
    })
    FREE_VARIABLE_IN_FORMULA = ("free_variable_in_formula", {
        "zh": "公式里的 VarRef {variable} 是自由的；没有任何外层的 sum "
              "绑定这个名字",
        "en": "the VarRef {variable} in this formula is free; no enclosing "
              "sum binds the name",
    })
    SUM_OVER_NOT_GROUND = ("sum_over_not_ground", {
        "zh": "sum.over 必须是基原子；谓词 {predicate} 里拿到的是变量 "
              "{variable}",
        "en": "sum.over has to be ground; predicate {predicate} carries the "
              "variable {variable}",
    })

    # --- one thing declared twice, or declared against itself --------------
    PREDICATE_DECLARED_TWICE = ("predicate_declared_twice", {
        "zh": "statements[{index}]：谓词 {predicate} 在 statements[{first}] "
              "已经声明过了；一个谓词至多只能有一条 variableDeclaration",
        "en": "statements[{index}]: predicate {predicate} is already declared "
              "at statements[{first}]; a predicate may have at most one "
              "variableDeclaration",
    })
    LOOP_HAS_ONE_END = ("loop_has_one_end", {
        "zh": "statements[{index}]：一个反馈环需要两个原子，"
              "而两端都叫 {predicate}",
        "en": "statements[{index}]: a feedback loop needs two atoms and both "
              "ends name {predicate}",
    })
    LOOP_ACROSS_TIME_STEPS = ("loop_across_time_steps", {
        "zh": "statements[{index}]：这个反馈环的两端在不同的时间步上，"
              "那不是环——{left} 在一步、{right} 在另一步，这是两个时间片之间"
              "普通的 cause 边，而且这样写的效应不需要工具变量就可识别。"
              "'feedback' 只用于同时性的环，也就是你说不出谁先谁后的那种",
        "en": "statements[{index}]: the two ends of this feedback loop are at "
              "different time steps, which is not a cycle — {left} at one "
              "step and {right} at another are ordinary cause edges between "
              "time slices, and written that way the effect is identifiable "
              "without an instrument. Use 'feedback' only for an "
              "instantaneous loop, where you cannot say which came first",
    })
    CAUSE_RUNS_BACKWARDS = ("cause_runs_backwards", {
        "zh": "statements[{index}]：这条 cause 的方向违反时间单调性——"
              "源 {source} 在 t={source_time}，比目的 {destination} 的 "
              "t={destination_time} 更晚。原因不能倒着走",
        "en": "statements[{index}]: this cause runs against time — the "
              "source {source} at t={source_time} is later than the "
              "destination {destination} at t={destination_time}. Causes "
              "cannot run backwards in time",
    })

    # --- a declaration the rest of the program contradicts ------------------
    # The third way out names a real hole — a hand-rolled Tian/ADMG c-factor
    # product conditions on topological predecessors, and the kernel does not
    # run one end to end. That hole is written up in wall.md iter 150, and
    # the citation stays here rather than in the sentence: the reader of the
    # sentence has themis.estimate and does not have the repository.
    GIVEN_NOT_PARENTS = ("given_not_parents", {
        "zh": "ground_statements[{index}]：probability.given 里有 {extra}，"
              "而它们不是 {target} 的结构父节点（父节点是 {parents}）。"
              "given 必须是 parents(target) 的子集。三条出路："
              "(1) 如果 {extra} 确实是 {target} 的原因，补上缺的 cause 语句，"
              "它们就成了结构父节点；(2) 把 {extra} 从 given 里去掉，"
              "改为提供边缘化之后的 P({target}|{parents})；"
              "(3) 如果你是在手写 Tian/ADMG 的 c-factor 乘积"
              "（它条件在完整的拓扑前驱上，而不只是结构父节点），"
              "kernel 还不支持端到端跑它——请改用 themis.estimate(...) 加原始数据",
        "en": "ground_statements[{index}]: probability.given includes "
              "{extra}, which are not structural parents of {target} "
              "(parents={parents}). given has to be a subset of "
              "parents(target). Three ways out: (1) if {extra} really are "
              "causes of {target}, add the missing cause statements so they "
              "become structural parents; (2) drop {extra} from given and "
              "supply the marginalized P({target}|{parents}) instead; (3) if "
              "you are hand-rolling a Tian/ADMG c-factor product (which "
              "conditions on full topological predecessors rather than "
              "structural parents), the kernel does not yet run that "
              "end to end — use themis.estimate(...) with raw data",
    })
    LLM_PRIOR_WITHOUT_SOURCE = ("llm_prior_without_source", {
        "zh": "statements[{index}]：provenance='llm_prior' 的 "
              "probabilityStatement 必须带一个非空的 annotations.source"
              "（一句话的理由，它会出现在 extensions.llm_proposed_review 里"
              "供终端用户审计）。没有说明理由的 LLM 先验就是无声的编造，"
              "Themis 拒绝让它从审计通道洗过去",
        "en": "statements[{index}]: a probabilityStatement with "
              "provenance='llm_prior' has to carry a non-empty "
              "annotations.source — a one-sentence reason, which appears in "
              "extensions.llm_proposed_review for the end user to audit. An "
              "LLM-proposed prior with no stated reason is silent "
              "fabrication, and Themis will not launder one through the "
              "audit channel",
    })
    LATENT_UNREAD_BY_THIS_QUERY = ("latent_unread_by_this_query", {
        "zh": "statements[{index}]（{query}）：这份程序声明了潜在共因，"
              "而 `{kind}` 查询只会照有向边作答，读不到它",
        "en": "statements[{index}] ({query}): this program declares a latent "
              "common cause, and a `{kind}` query would be answered off the "
              "directed edges alone",
    })

    # --- transport: which population the question is about ------------------
    SELECTION_NODES_DISAGREE_ON_TARGET = (
        "selection_nodes_disagree_on_target", {
            "zh": "选择节点对 target_population 说法不一（{targets}）："
                  "一个迁移问题只有一个目标人群，多个源域是靠不同的 "
                  "source_population 区分的，不是靠不同的 target",
            "en": "the selection nodes disagree on target_population "
                  "({targets}): a transport question has one target "
                  "population, and several source domains are declared by "
                  "differing source_population, not by differing target",
        })
    IDENTIFY_QUERY_CANNOT_TRANSPORT = ("identify_query_cannot_transport", {
        "zh": "statements[{index}]（{query}）：带 target_population="
              "{population} 的 identify 查询还不支持——目前只有 effect "
              "查询能做迁移",
        "en": "statements[{index}] ({query}): an identify query with "
              "target_population={population} is not supported yet — only "
              "effect queries transport today",
    })
    NO_DIAGRAM_FOR_THIS_TARGET = ("no_diagram_for_this_target", {
        "zh": "statements[{index}]（{query}）：这个查询问的是 "
              "target_population={population}，而声明的每个选择节点说的都是 "
              "{declared}；这些图描述的不是这个问题所问的那个人群",
        "en": "statements[{index}] ({query}): the query asks about "
              "target_population={population} and every declared selection "
              "node is about {declared}; the diagrams do not describe the "
              "population the question is about",
    })


class SemanticError(Exception):
    """Raised when the AST violates a semantic rule.

    Carries the species and this occasion's facts, and builds its own
    message from them — so ``str(exc)`` is still what a traceback shows,
    while :attr:`said` and :attr:`words` are what a surface that knows the
    reader's language assembles the sentence from. ``themis.web.failure``
    already does exactly that for the estimator's refusals; this is the
    same door for the checker's.
    """

    def __init__(self, species: Malformed, **details) -> None:
        # Before ``language.occasion`` flattens them: a word is a member
        # here and a bare token afterwards, and which set it came from is
        # what the flattening loses.
        self.said, self.words = language.halve(details)
        self.species = species
        self.details = {k: language.occasion(v) for k, v in details.items()}
        super().__init__(language.capped(
            language.assemble(species.words, self.said, self.words)))


# ---------------------------------------------------------------------------
# dict -> typed object conversion
# ---------------------------------------------------------------------------

def _to_term(d: dict) -> Term:
    if d["type"] == "const":
        return ConstTerm(name=d["name"])
    return VarTerm(name=d["name"])


def _to_atom(d: dict) -> Atom:
    ti = d.get("time_index")
    time_index = None
    if ti is not None:
        time_index = RelativeTimeIndex(value=ti["value"])
    return Atom(
        predicate=d["predicate"],
        args=tuple(_to_term(t) for t in d["args"]),
        time_index=time_index,
    )


def _to_atoms(raw) -> tuple[Atom, ...]:
    """A list of atoms, in the order the program wrote them.

    Order is kept rather than sorted because it is the order of the columns
    a design matrix is built from, and a record of those columns that a
    verifier re-derives has to agree with the one the estimator built.
    """
    return tuple(_to_atom(d) for d in raw)


def _to_annotation(d: dict | None) -> Annotation | None:
    if d is None:
        return None
    return Annotation(confidence=d.get("confidence"), source=d.get("source"))


def _to_intervention(d: dict) -> Intervention:
    return Intervention(atom=_to_atom(d["atom"]), value=d["value"])


def _to_grounded(d: dict) -> ValuedAtom:
    """Parse a groundedAtom ({atom, value}) from the schema into a
    ValuedAtom. The schema guarantees ``value`` is a concrete literal
    here (no VarRef, no None); ValuedAtom's broader type accommodates
    this without extra runtime checks."""
    return ValuedAtom(atom=_to_atom(d["atom"]), value=d["value"])


def _to_query(d: dict):
    k = d["kind"]
    if k == "cause":
        return CauseQuery(from_atom=_to_atom(d["from"]), to_atom=_to_atom(d["to"]))
    if k == "assoc":
        return AssocQuery(
            left=_to_atom(d["left"]),
            right=_to_atom(d["right"]),
            given=tuple(_to_atom(a) for a in d["given"]),
        )
    if k == "effect":
        mediator_raw = d.get("mediator")
        # Parse the first-class assumptions field on EffectQuery
        # (parallel to CounterfactualQuery.assumptions). Backwards-
        # compat: scheduler still falls back to program.extensions
        # when this is absent.
        eq_assumptions_raw = d.get("assumptions")
        eq_assumptions = None
        if eq_assumptions_raw is not None:
            mono = eq_assumptions_raw.get("monotonicity")
            eq_assumptions = EffectQueryAssumptions(
                monotonicity=Monotonicity.named(mono) if mono else None,
            )
        extra_raw = d.get("extra_interventions") or ()
        mediators_raw = d.get("mediators") or ()
        return EffectQuery(
            target=_to_grounded(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            extra_interventions=tuple(_to_intervention(iv) for iv in extra_raw),
            given=tuple(_to_grounded(a) for a in d["given"]),
            mediator=_to_atom(mediator_raw) if mediator_raw is not None else None,
            mediators=tuple(_to_atom(a) for a in mediators_raw),
            target_population=d.get("target_population"),
            assumptions=eq_assumptions,
        )
    if k == "identify":
        return IdentifyQuery(
            target=_to_atom(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            given=tuple(_to_atom(a) for a in d["given"]),
            target_population=d.get("target_population"),
        )
    if k == "probability":
        return ProbabilityQuery(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
        )
    if k == "counterfactual":
        assumptions_raw = d.get("assumptions")
        assumptions = None
        if assumptions_raw is not None:
            assumptions = CounterfactualAssumptions(
                monotonicity=(
                    Monotonicity.named(assumptions_raw["monotonicity"])
                    if assumptions_raw.get("monotonicity") is not None
                    else None
                )
            )
        return CounterfactualQuery(
            observed=_to_grounded(d["observed"]),
            counterfactual_intervention=_to_intervention(
                d["counterfactual_intervention"]
            ),
            counterfactual_target=_to_grounded(d["counterfactual_target"]),
            assumptions=assumptions,
            factual_target_known=d.get("factual_target_known"),
            experimental_risk_treated=d.get("experimental_risk_treated"),
            experimental_risk_control=d.get("experimental_risk_control"),
        )
    if k == "causation":
        return CausationQuery(
            cause=_to_atom(d["cause"]),
            effect=_to_atom(d["effect"]),
            monotonic=bool(d.get("monotonic", False)),
            experimental_risk_treated=d.get("experimental_risk_treated"),
            experimental_risk_control=d.get("experimental_risk_control"),
        )
    if k == "scm_counterfactual":
        return SCMCounterfactualQuery(
            intervention=_to_intervention(d["intervention"]),
            target=_to_atom(d["target"]),
        )
    if k == "counterfactual_conjunction":
        def _to_ctf_events(raw):
            return tuple(
                CounterfactualEvent(
                    variable=_to_atom(e["variable"]),
                    subscript=tuple(
                        _to_grounded(s) for s in e.get("subscript", ())
                    ),
                    value=e["value"],
                )
                for e in raw
            )
        return CounterfactualConjunctionQuery(
            events=_to_ctf_events(d["events"]),
            condition=_to_ctf_events(d.get("condition", ())),
        )
    if k == "proximal_effect":
        return ProximalEffectQuery(
            treatment=_to_atom(d["treatment"]),
            outcome=_to_atom(d["outcome"]),
            latent=_to_atom(d["latent"]),
            treatment_proxy=_to_atoms(d["treatment_proxy"]),
            outcome_proxy=_to_atoms(d["outcome_proxy"]),
            covariates=_to_atoms(d.get("covariates", ())),
            channel=_to_proximal_channel(d["channel"]),
        )
    raise TypeError(f"unknown query kind: {k}")


def _to_proximal_channel(raw: dict):
    """Which algebra the query asks the proxies to be read by.

    A conversion, like everything else here. What is checked at this door is
    only what makes the object ill-formed rather than wrong — a bridge with
    fewer moments than unknowns describes a system that was never posed,
    which is not an estimate that comes out badly. Everything a reader could
    be told about instead lives in the estimator, where the language is
    theirs.

    Both widths are COUNTED from the declared terms rather than read from
    the query. They used to be two integers the caller supplied beside a
    design they also supplied, which made the under-determination rule a
    check on what the caller said about their design rather than on the
    design; the two could disagree, and only one of them built the matrix.
    """
    from ..types import (
        BridgeChannel, DiscreteChannel, ProximalEstimator,
    )

    kind = raw.get("kind")
    if kind == "discrete_channel":
        return DiscreteChannel(
            latent_cardinality=int(raw["latent_cardinality"]),
            proxy_coarsening=_to_proxy_coarsening(raw.get("proxy_coarsening")),
        )
    if kind == "bridge_channel":
        treatment = raw.get("treatment_bridge")
        estimator = ProximalEstimator(
            raw.get("estimator", str(ProximalEstimator.OUTCOME_REGRESSION)))
        wants_q = estimator != ProximalEstimator.OUTCOME_REGRESSION
        # Declared and unread, or read and undeclared: one gate, both
        # directions. A caller who names an estimator that divides by q and
        # gives no q has asked for an answer this program cannot reach, and
        # one who gives a q nothing reads has bought insurance the arithmetic
        # never collects on. Neither is an estimate that comes out badly.
        if wants_q and treatment is None:
            raise SemanticError(Malformed.TREATMENT_BRIDGE_NOT_DECLARED,
                                estimator=str(estimator))
        if treatment is not None and not wants_q:
            raise SemanticError(Malformed.TREATMENT_BRIDGE_UNUSED)
        outcome_bridge = _to_bridge(raw["outcome_bridge"], "outcome_bridge")
        if treatment is None:
            return BridgeChannel(outcome_bridge=outcome_bridge,
                                 estimator=estimator)
        treatment_bridge = _to_bridge(treatment, "treatment_bridge")
        if (treatment_bridge.span_terms == outcome_bridge.moment_terms
                and treatment_bridge.moment_terms == outcome_bridge.span_terms):
            raise SemanticError(Malformed.BRIDGES_ARE_EACH_OTHERS_MIRROR)
        return BridgeChannel(outcome_bridge=outcome_bridge,
                             treatment_bridge=treatment_bridge,
                             estimator=estimator)
    raise TypeError(f"unknown proximal channel kind: {kind}")


def _to_bridge(raw: dict, field: str):
    """One bridge, and the one rule that makes a bridge posable at all.

    Written once and called for each, which is the point of the two having
    one type: "at least as many moments as unknowns" is a property of a
    solve, and a solve does not know which of its variables are proxies of
    what. While the fields carried the roles this rule could only be spelt
    for the outcome bridge, and the treatment bridge would have needed it
    spelt again against different names.
    """
    from ..types import BridgeFunction, width_of

    span_terms = _to_sieve_terms(raw["span_terms"])
    moment_terms = _to_sieve_terms(raw["moment_terms"])
    unknowns = width_of(span_terms)
    moments = width_of(moment_terms)
    if moments < unknowns:
        raise SemanticError(Malformed.BRIDGE_UNDER_DETERMINED, bridge=field,
                            moments=moments, unknowns=unknowns)
    ridge = raw.get("ridge")
    return BridgeFunction(
        span_terms=span_terms,
        moment_terms=moment_terms,
        ridge=None if ridge is None else float(ridge),
    )


def _to_sieve_terms(raw) -> "tuple[SieveTerm, ...]":
    """One side of a sieve design, as the terms it is the sum of."""
    from ..types import BasisFamily, SieveFactor, SieveTerm

    return tuple(
        SieveTerm(factors=tuple(
            SieveFactor(
                variable=_to_atom(f["variable"]),
                basis=BasisFamily(f["basis"]),
                dimension=int(f["dimension"]),
            )
            for f in term["factors"]
        ))
        for term in raw
    )


def _to_proxy_coarsening(raw):
    """The declared grouping of each proxy's levels, as the query holds it.

    A conversion and nothing more. The shape — arrays of arrays, no group
    empty, no level named twice inside one — is the schema's; that there are
    as many groups as the query posits states of the latent, and that they
    cover the levels the column actually holds, are the estimator's, and
    they are refusals rather than parse errors so that a reader meets them
    in their own language. The cost is that a coarsening whose group count
    is wrong is not caught until data arrives — which is also the first
    moment it could change an answer, since identification does not read it.
    """
    if raw is None:
        return None
    from ..types import ProxyCoarsening

    return ProxyCoarsening(**{
        side: tuple(tuple(group) for group in raw[side])
        for side in ("treatment_proxy", "outcome_proxy")
    })


def _to_statement(d: dict):
    k = d["kind"]
    if k == "cause":
        return CauseStatement(
            from_atom=_to_atom(d["from"]),
            to_atom=_to_atom(d["to"]),
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
            coefficient=d.get("coefficient"),
        )
    if k == "bidirected":
        return BidirectedStatement(
            left=_to_atom(d["left"]),
            right=_to_atom(d["right"]),
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "feedback":
        return FeedbackLoop(
            left=_to_atom(d["left"]),
            right=_to_atom(d["right"]),
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "selection_node":
        return SelectionNode(
            id=d["id"],
            affects=_to_atom(d["affects"]),
            source_population=d["source_population"],
            target_population=d["target_population"],
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "missingness_indicator":
        return MissingnessIndicator(
            id=d["id"],
            missing_var=_to_atom(d["missing_var"]),
            caused_by=tuple(_to_atom(a) for a in d.get("caused_by", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "probability":
        return ProbabilityStatement(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
            value=d["value"],
            forall=tuple(d.get("forall", ())),
            population=d.get("population"),
            provenance=d.get("provenance", "structural"),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "observation":
        return ObservationStatement(
            atom=_to_atom(d["atom"]),
            value=d["value"],
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "query":
        return QueryStatement(id=d["id"], query=_to_query(d["query"]))
    if k == "variable":
        domain = d.get("domain")
        defaulted = d.get("defaulted")
        return VariableDeclaration(
            predicate=d["predicate"],
            domain=tuple(domain) if domain is not None else None,
            defaulted=tuple(defaulted) if defaulted is not None else (),
            time_window=d.get("time_window"),
            measurement=d.get("measurement"),
            threshold=d.get("threshold"),
            observability=d.get("observability"),
            unit=d.get("unit"),
            direction=d.get("direction"),
            baseline=d.get("baseline"),
            state_vs_event=d.get("state_vs_event"),
            scale=d.get("scale"),
        )
    raise TypeError(f"unknown statement kind: {k}")


# ---------------------------------------------------------------------------
# semantic checks
# ---------------------------------------------------------------------------

def _as_atom(x) -> Atom:
    """Return the bare Atom from either an Atom or a ValuedAtom."""
    return x.atom if isinstance(x, ValuedAtom) else x


def _atoms_in_statement(stmt) -> tuple[Atom, ...]:
    if isinstance(stmt, CauseStatement):
        return (stmt.from_atom, stmt.to_atom)
    if isinstance(stmt, (BidirectedStatement, FeedbackLoop)):
        return (stmt.left, stmt.right)
    if isinstance(stmt, SelectionNode):
        return (stmt.affects,)
    if isinstance(stmt, MissingnessIndicator):
        return (stmt.missing_var, *stmt.caused_by)
    if isinstance(stmt, ProbabilityStatement):
        return (_as_atom(stmt.target), *(_as_atom(g) for g in stmt.given))
    if isinstance(stmt, ObservationStatement):
        return (stmt.atom,)
    if isinstance(stmt, QueryStatement):
        q = stmt.query
        if isinstance(q, CauseQuery):
            return (q.from_atom, q.to_atom)
        if isinstance(q, AssocQuery):
            return (q.left, q.right, *q.given)
        if isinstance(q, EffectQuery):
            return (
                _as_atom(q.target),
                q.intervention.atom,
                *(iv.atom for iv in q.extra_interventions),
                *(_as_atom(g) for g in q.given),
            )
        if isinstance(q, IdentifyQuery):
            return (q.target, q.intervention.atom, *q.given)
        if isinstance(q, ProbabilityQuery):
            return (_as_atom(q.target), *(_as_atom(g) for g in q.given))
        if isinstance(q, CounterfactualQuery):
            return (
                _as_atom(q.observed),
                q.counterfactual_intervention.atom,
                _as_atom(q.counterfactual_target),
            )
        if isinstance(q, CausationQuery):
            return (q.cause, q.effect)
        if isinstance(q, SCMCounterfactualQuery):
            return (q.intervention.atom, q.target)
        if isinstance(q, CounterfactualConjunctionQuery):
            return tuple(
                a
                for e in (*q.events, *q.condition)
                for a in (e.variable, *(s.atom for s in e.subscript))
            )
        if isinstance(q, ProximalEffectQuery):
            return (
                q.treatment, q.outcome, q.latent,
                *q.treatment_proxy, *q.outcome_proxy, *q.covariates,
            )
    return ()


def _check_objects(program: Program) -> None:
    declared = set(program.objects)
    for idx, stmt in enumerate(program.statements):
        for atom in _atoms_in_statement(stmt):
            for arg in atom.args:
                if isinstance(arg, ConstTerm) and arg.name not in declared:
                    raise SemanticError(Malformed.CONST_NOT_IN_DOMAIN,
                                        index=idx, const=arg.name,
                                        predicate=atom.predicate)


def _check_forall_usage(program: Program) -> None:
    for idx, stmt in enumerate(program.statements):
        forall = getattr(stmt, "forall", ())
        if not forall:
            continue
        used: set[str] = set()
        for atom in _atoms_in_statement(stmt):
            for arg in atom.args:
                if isinstance(arg, VarTerm):
                    used.add(arg.name)
        missing = set(forall) - used
        if missing:
            raise SemanticError(Malformed.FORALL_VARIABLE_UNUSED,
                                index=idx, variables=sorted(missing))


def _var_names(atom: Atom) -> set[str]:
    return {a.name for a in atom.args if isinstance(a, VarTerm)}


def _check_bound_variables(program: Program) -> None:
    """Every VarTerm in cause / probability statements must be declared
    in the statement's forall list.

    Without this check, a stray ``{"type": "var", "name": "X"}`` slips
    through and becomes a permanent ghost node in the working graph.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, (CauseStatement, BidirectedStatement,
                                 FeedbackLoop, ProbabilityStatement)):
            continue
        declared = set(stmt.forall)
        for atom in _atoms_in_statement(stmt):
            free = _var_names(atom) - declared
            if free:
                raise SemanticError(Malformed.VARIABLE_NOT_IN_FORALL,
                                    index=idx, variables=sorted(free),
                                    predicate=atom.predicate)


def _check_feedback_loops(program: Program) -> None:
    """A declared loop has to be a loop, and has to be instantaneous.

    Two refusals, and the second is the one worth having.

    A loop between two atoms that carry different time indices is not a
    cycle at all — ``a`` at t moving ``b`` at t+1 moving ``a`` at t+2 is
    three ordinary edges in an acyclic graph, and writing it here instead
    throws away the very resolution that makes the effect identifiable
    without an instrument. A reader who has the time index has the
    stronger model and does not know it, so this refusal hands it back
    rather than quietly accepting the weaker claim.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, FeedbackLoop):
            continue
        if stmt.left == stmt.right:
            raise SemanticError(Malformed.LOOP_HAS_ONE_END,
                                index=idx, predicate=stmt.left.predicate)
        left_t, right_t = stmt.left.time_index, stmt.right.time_index
        if left_t != right_t:
            raise SemanticError(Malformed.LOOP_ACROSS_TIME_STEPS,
                                index=idx, left=stmt.left.predicate,
                                right=stmt.right.predicate)


def _check_ground_observations(program: Program) -> None:
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, ObservationStatement):
            continue
        vars_used = _var_names(stmt.atom)
        if vars_used:
            raise SemanticError(Malformed.OBSERVATION_NOT_GROUND,
                                index=idx, variables=sorted(vars_used))


def _check_ground_queries(program: Program) -> None:
    """Queries must be ground in v0.1.

    A patterned query like ``cause(smokes(X), cancer(X))`` is rejected
    here rather than silently returning False because no graph node
    matches the variable-bearing atom.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        for atom in _atoms_in_statement(stmt):
            vars_used = _var_names(atom)
            if vars_used:
                raise SemanticError(Malformed.QUERY_NOT_GROUND,
                                    index=idx, query=stmt.id,
                                    predicate=atom.predicate,
                                    variables=sorted(vars_used))


def _check_unique_variable_declarations(program: Program) -> None:
    """Slice A0 follow-up: a predicate may have at most one
    ``variableDeclaration``. Duplicate declarations used to silently
    overwrite each other in ``framing_check._declarations_by_predicate``,
    so framing would depend on statement order rather than on a stable
    predicate definition.

    Authors who want to change a predicate's metadata should edit the
    one declaration, not stack a second one on top.
    """
    seen: dict[str, int] = {}
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, VariableDeclaration):
            continue
        if stmt.predicate in seen:
            first = seen[stmt.predicate]
            raise SemanticError(Malformed.PREDICATE_DECLARED_TWICE,
                                index=idx, predicate=stmt.predicate,
                                first=first)
        seen[stmt.predicate] = idx


class LatentExposure(StrEnum):
    """What an unobserved common cause can do to a query kind's answer.

    A bidirected edge asks each dispatch path one question, and it is not
    "does this path take a ``bidirected`` argument" — that is a fact about
    a signature. It is whether a latent common cause can move the answer,
    and if it can, whether the path is looking.

    The two verdicts that let a query through are not the same verdict,
    and holding them apart is what this enum is for. A path that is right
    because the latent is irrelevant to what it computes stays right
    however the edge set is threaded; a path that is right because it
    consults the edge set stops being right the moment it stops
    consulting, and stays quiet while it does. Collapsing the two into
    "the path reads the edge set" is what left this gate refusing two
    kinds that were already answering correctly while admitting one that
    the same sentence would have refused.
    """

    ABSORBED = "absorbed"
    """A latent common cause cannot move this answer."""

    CONSULTED = "consulted"
    """It can, and the dispatch path is handed the bidirected edge set."""

    UNREAD = "unread"
    """It can, and the dispatch path is not handed it — so the query is
    refused rather than answered off the directed edges alone."""


class Exposure(NamedTuple):
    """One query kind's verdict, and the evidence it was reached on.

    Two fields rather than a pair, because they have two audiences and the
    pair could not say so. ``verdict`` decides whether a program is refused;
    ``evidence`` is why that decision is right, written for whoever changes
    it. While they were positions in a tuple, the refusal spliced position
    one into the reader's sentence — so an English note recording a
    measurement would have arrived in the middle of a Chinese refusal, and
    the only reason it never did is that no kind is ``UNREAD`` today.

    The reader's half of an ``UNREAD`` verdict is
    :attr:`Malformed.LATENT_UNREAD_BY_THIS_QUERY`, which is bilingual and
    names the query and the kind — both of which are the reader's own.
    """

    verdict: "LatentExposure"
    evidence: str


_LATENT_EXPOSURE: dict[QueryKind, Exposure] = {
    QueryKind.CAUSE: Exposure(
        verdict=LatentExposure.ABSORBED,
        evidence="it asks about directed paths, and a latent common cause draws no "
        "arrow: the projected G(M) carries the atoms of a bidirected "
        "statement as isolated nodes and never as an edge, so reachability "
        "cannot see them and has nothing to see. Measured — on x<->y alone "
        "the answer is False, and on x->m->y with x<->y it is True with "
        "the one supporting path x,m,y",
    ),
    QueryKind.SCM_COUNTERFACTUAL: Exposure(
        verdict=LatentExposure.ABSORBED,
        evidence="abduction is unit-level: whatever the latent did to this unit's "
        "outcome is already inside the exogenous term the factual "
        "observation pins down, and do() leaves that term alone. Measured "
        "against the closed-form unit counterfactual — 40 units in the test "
        "that pins this and 200 while establishing it — the worst error is "
        "2e-15, and it is identical whether or not the edge is declared",
    ),
    QueryKind.PROBABILITY: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="an observational conditional is whatever theta says, until theta "
        "lacks the exact entry and a coarser one is considered in its "
        "place; standing one in asserts an independence, and a latent "
        "common cause is exactly what makes that assertion false. "
        "Measured — with only the marginal P(y)=0.18 declared and x<->y, "
        "withholding the edge set from the guard hands back 0.18 as though "
        "it were P(y|x), and supplying it refuses",
    ),
    QueryKind.ASSOC: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="association travels a latent common cause as readily as an arrow, "
        "so whether two atoms are separated is a question about the ADMG "
        "rather than about its directed edges",
    ),
    QueryKind.IDENTIFY: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="identifiability is a property of the ADMG: the same directed "
        "edges are identifiable with one latent common cause and hedged "
        "with another",
    ),
    QueryKind.EFFECT: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="it identifies before it estimates, so it inherits identify's "
        "exposure, and the estimand it hands downstream moves with it",
    ),
    QueryKind.COUNTERFACTUAL: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="a latent common cause is shared between the factual and the "
        "counterfactual world rather than drawn twice, which is what makes "
        "a cross-world quantity depend on it",
    ),
    QueryKind.CAUSATION: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="the interventional risks the probabilities of causation are taken "
        "from are point-identified on some ADMGs and only bounded on "
        "others",
    ),
    QueryKind.COUNTERFACTUAL_CONJUNCTION: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="same exposure as a single counterfactual, and the recursion it "
        "uses factors by c-component — which is a set the bidirected edges "
        "define",
    ),
    QueryKind.PROXIMAL_EFFECT: Exposure(
        verdict=LatentExposure.CONSULTED,
        evidence="an unmeasured confounder with two proxies is its premise, so a "
        "latent common cause is the input rather than a complication",
    ),
}


def _bind_latent_exposure(
    table: "dict[QueryKind, Exposure]",
) -> None:
    """Every query kind says what a latent common cause does to it.

    Called at import, so a kind nobody has classified cannot reach a user
    at all — which is the direction that matters. The gate this feeds used
    to name the kinds it refused and let every other kind through, and by
    the time five more kinds existed nobody had been asked the question
    about any of them.
    """
    undeclared = sorted(k.value for k in set(QueryKind) - set(table))
    stale = sorted(getattr(k, "value", k) for k in set(table) - set(QueryKind))
    if undeclared or stale:
        raise AssertionError(
            "themis/input/semantic_validator.py: every query kind must "
            "declare what an unobserved common cause can do to its answer "
            "before the bidirected gate can decide whether to let it "
            f"through; undeclared: {undeclared}, no longer a kind: {stale}"
        )


_bind_latent_exposure(_LATENT_EXPOSURE)


def _check_bidirected_runtime_gate(program: Program) -> None:
    """A query on an ADMG is refused when a latent common cause can move
    its answer and its dispatch path is not handed the edge set.

    The gate used to name the two kinds it refused, under a stated lift
    condition: once every dispatch path reads the bidirected edge set.
    That sentence is a proxy for the one that matters, and it is wrong in
    both directions. ``cause`` will never read the edge set, because a
    latent common cause is not causation — under the stated condition it
    stays refused forever while answering correctly. ``scm_counterfactual``
    is not handed the edge set either and was never refused, because the
    gate did not apply its own condition: it applied a hand-written pair
    of ``isinstance`` checks, written before five of the ten kinds
    existed, whose default for an unlisted kind was to allow.

    So the verdict comes from :data:`_LATENT_EXPOSURE` instead, where the
    default for a kind nobody has classified is that the module does not
    import.
    """
    if not any(
        isinstance(s, BidirectedStatement) for s in program.statements
    ):
        return

    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        kind = QUERY_KIND_OF[type(stmt.query)]
        if _LATENT_EXPOSURE[kind].verdict is not LatentExposure.UNREAD:
            continue
        # The evidence beside the verdict is NOT spliced in here. It is the
        # maintainer's — measurements taken while classifying the kind — and
        # it was reaching a reader as the second half of their refusal, in
        # whichever language it happened to be written in. What the reader
        # needs is which query and which kind, both of which are theirs.
        raise SemanticError(Malformed.LATENT_UNREAD_BY_THIS_QUERY,
                            index=idx, query=stmt.id, kind=kind.value)


def _check_transport_runtime_gate(program: Program) -> None:
    """Phase 9 §T9.1.2 → S.T9.1.3 lifted (kept as a no-op stub).

    Pre-S.T9.1.3 this check raised SemanticError on any query with
    ``target_population`` set, because the dispatch path didn't exist.
    S.T9.1.3 added ``transport.identify_via_transport`` and the
    EffectQuery dispatch branch to handle it. The gate is now a no-op,
    retained in the registry for symmetry with the bidirected gate
    (so future versions can re-narrow it if needed without renaming).

    Identify queries with ``target_population`` are still gated below
    until §T9.2 lands their dispatch path.

    The two populations a selection node names are not symmetric. Its
    ``source_population`` is that node's own — Bareinboim & Pearl's object
    is a SET of selection diagrams over one shared graph, one per source
    domain, and nodes disagreeing there is exactly the multi-source case.
    Its ``target_population`` is the question's, and there is one question:
    nodes that disagree about where the answer is FOR, or a node that
    disagrees with the query, are not several diagrams but one program
    asserting two incompatible things. No route through it is more right
    than the other, so it is refused rather than resolved.
    """
    declared_targets = {
        s.target_population for s in program.statements
        if isinstance(s, SelectionNode)
    }
    if len(declared_targets) > 1:
        raise SemanticError(Malformed.SELECTION_NODES_DISAGREE_ON_TARGET,
                            targets=sorted(declared_targets))
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        target = getattr(stmt.query, "target_population", None)
        if isinstance(stmt.query, IdentifyQuery) and target is not None:
            raise SemanticError(Malformed.IDENTIFY_QUERY_CANNOT_TRANSPORT,
                                index=idx, query=stmt.id,
                                population=stmt.query.target_population)
        if (target is not None and declared_targets
                and target not in declared_targets):
            raise SemanticError(Malformed.NO_DIAGRAM_FOR_THIS_TARGET,
                                index=idx, query=stmt.id, population=target,
                                declared=sorted(declared_targets))


def _check_temporal_monotonicity(program: Program) -> None:
    """Phase 5 §T / T1 enforcement: a `cause` whose source carries a
    later time_index than its destination is rejected — there is no
    coherent "tomorrow's X causes today's Y" semantics.

    Rules:
    - If both endpoints carry a time_index, src.value <= dst.value.
    - If only one endpoint carries a time_index, no constraint
      (atemporal endpoint sits on the virtual atemporal index, ordering
      with a temporal endpoint is undefined and out-of-scope).
    - Bidirected statements: same rule applies symmetrically because
      bidirected coupling implies a shared latent that exists across
      both endpoints' time slices — but in this slice we only enforce
      directed-cause ordering. Bidirected ordering (if any future case
      drives it) lands in a separate check.

    The verifier already has T1_time_monotonicity as a primitive but
    runtime never wired it in — this semantic check is the runtime-side
    enforcement that mirrors the verifier rule.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, CauseStatement):
            continue
        src_ti = stmt.from_atom.time_index
        dst_ti = stmt.to_atom.time_index
        if src_ti is None or dst_ti is None:
            continue
        if src_ti.value > dst_ti.value:
            raise SemanticError(Malformed.CAUSE_RUNS_BACKWARDS,
                                index=idx,
                                source=stmt.from_atom.predicate,
                                source_time=src_ti.value,
                                destination=stmt.to_atom.predicate,
                                destination_time=dst_ti.value)


def _check_llm_prior_requires_source(program: Program) -> None:
    """Fix 3+4 §3.1 (v0.1.5): every probability statement tagged
    ``provenance == "llm_prior"`` must carry a non-empty
    ``annotations.source`` string. The source field is the audit-trail
    reason that surfaces in ``extensions.llm_proposed_review``; if it's
    empty / null / whitespace, the end user has no way to evaluate
    whether the LLM-proposed number is reasonable. Empty source on
    llm_prior would let the LLM silently launder fabricated values
    without disclosure — a direct violation of Themis's "kernel
    doesn't fabricate" contract.

    Charter requires the source to be a one-sentence reason; we
    enforce non-empty here (semantic minimum), the Skill enforces
    "useful sentence" (prompt minimum).
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, ProbabilityStatement):
            continue
        if stmt.provenance != "llm_prior":
            continue
        ann = stmt.annotations
        source = ann.source if ann is not None else None
        if source is None or not source.strip():
            raise SemanticError(Malformed.LLM_PRIOR_WITHOUT_SOURCE, index=idx)


#: Every side of every sieve design: which bridge holds it, which of that
#: bridge's two fields it is, which proxy role it may draw on, and which
#: species refuses a variable that is neither that role nor a covariate.
#:
#: Read as data because the sides differ in exactly those four things — and
#: because written out, the table SHOWS the swap that is the whole reason
#: there are two bridges: the outcome bridge spans W and takes moments of Z,
#: the treatment bridge does the opposite, and each species appears twice
#: because what a side may name follows from the role it reads and not from
#: which bridge it belongs to.
_SIEVE_SIDES = (
    ("outcome_bridge", "span_terms", "outcome_proxy",
     Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_OUTCOME_PROXY),
    ("outcome_bridge", "moment_terms", "treatment_proxy",
     Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_TREATMENT_PROXY),
    ("treatment_bridge", "span_terms", "treatment_proxy",
     Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_TREATMENT_PROXY),
    ("treatment_bridge", "moment_terms", "outcome_proxy",
     Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_OUTCOME_PROXY),
)


def _covariate_width(terms, atom) -> int:
    """How many columns of a side vary with this covariate.

    Summed over the terms that name it, each contributing its whole width:
    a term is a tensor product, so every one of its columns moves when this
    factor does, and counting the factor's own dimension instead would say
    an interaction resolves C no better than an additive term does.
    """
    return sum(term.width for term in terms
               if any(f.variable == atom for f in term.factors))


def _check_proximal_sieve_design(program: Program) -> None:
    """A sieve design has to be buildable from the roles the query declared.

    Every check here compares two declarations of the SAME program against
    each other — which variables have which role, and which variables the
    design is built from. None of it needs data, and all of it would
    otherwise surface as a missing column or a singular matrix, one layer
    down and in a vocabulary about matrices rather than about the question.
    """
    from ..types import BridgeChannel, DiscreteChannel

    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        q = stmt.query
        if not isinstance(q, ProximalEffectQuery):
            continue
        if isinstance(q.channel, DiscreteChannel):
            if len(q.treatment_proxy) != 1 or len(q.outcome_proxy) != 1:
                raise SemanticError(
                    Malformed.DISCRETE_CHANNEL_TAKES_ONE_PROXY_EACH,
                    index=idx, query=stmt.id,
                    treatment_proxies=len(q.treatment_proxy),
                    outcome_proxies=len(q.outcome_proxy))
            if q.covariates:
                raise SemanticError(
                    Malformed.DISCRETE_CHANNEL_TAKES_NO_COVARIATES,
                    index=idx, query=stmt.id,
                    variables=[a.predicate for a in q.covariates])
            continue
        if not isinstance(q.channel, BridgeChannel):
            raise TypeError(f"unknown proximal channel: {q.channel!r}")

        for bridge_field, side, role, stranger_species in _SIEVE_SIDES:
            bridge = getattr(q.channel, bridge_field)
            if bridge is None:
                continue
            terms = getattr(bridge, side)
            for factor in (f for term in terms for f in term.factors):
                minimum = SIEVE_MINIMUM_DIMENSION[factor.basis]
                if factor.dimension < minimum:
                    raise SemanticError(
                        Malformed.SIEVE_BASIS_TOO_NARROW,
                        index=idx, query=stmt.id,
                        variable=factor.variable.predicate,
                        basis=str(factor.basis),
                        dimension=factor.dimension, minimum=minimum)
            allowed = frozenset((*getattr(q, role), *q.covariates))
            used = {f.variable for term in terms for f in term.factors}
            for stranger in sorted(used - allowed, key=lambda a: a.predicate):
                raise SemanticError(stranger_species, index=idx,
                                    query=stmt.id, bridge=bridge_field,
                                    variable=stranger.predicate)
            unused = [a for a in getattr(q, role) if a not in used]
            if unused:
                raise SemanticError(
                    Malformed.SIEVE_LEAVES_A_PROXY_UNUSED,
                    index=idx, query=stmt.id,
                    variables=[a.predicate for a in unused])

        # Read per BRIDGE and not per query: the rule is that a bridge's
        # moments resolve C as finely as the bridge varies in it, and each
        # bridge answers for its own two sides. One rule, twice.
        for bridge_field in ("outcome_bridge", "treatment_bridge"):
            bridge = getattr(q.channel, bridge_field)
            if bridge is None:
                continue
            for atom in q.covariates:
                span_width = _covariate_width(bridge.span_terms, atom)
                moment_width = _covariate_width(bridge.moment_terms, atom)
                if span_width > moment_width:
                    raise SemanticError(
                        Malformed.COVARIATE_NOT_ON_BOTH_SIDES,
                        index=idx, query=stmt.id, variable=atom.predicate,
                        bridge=bridge_field, span_width=span_width,
                        moment_width=moment_width)


_CHECK_FUNCS = {
    "objects": _check_objects,
    "proximal_sieve_design": _check_proximal_sieve_design,
    "forall_usage": _check_forall_usage,
    "bound_variables": _check_bound_variables,
    "feedback_loops": _check_feedback_loops,
    "ground_observations": _check_ground_observations,
    "ground_queries": _check_ground_queries,
    "unique_variable_declarations": _check_unique_variable_declarations,
    "bidirected_runtime_gate": _check_bidirected_runtime_gate,
    "transport_runtime_gate": _check_transport_runtime_gate,
    "temporal_monotonicity": _check_temporal_monotonicity,
    "llm_prior_requires_source": _check_llm_prior_requires_source,
}


# ---------------------------------------------------------------------------
# graph-level checks (run post-instantiation)
# ---------------------------------------------------------------------------

GRAPH_LEVEL_CHECKS: frozenset[str] = frozenset(
    {"probability_parents", "query_atoms_in_V"}
)


def _check_probability_parents(
    ground_statements, graph, *, bidirected: "frozenset[frozenset]" = frozenset(),
) -> None:
    """Every ground probability statement's ``given`` set must be a
    subset of the target atom's structural parents in ``G(M)`` —
    OR any atom that reaches target via a directed or
    bidirected path (admissible Tian c-factor topo-predecessors).

    A model parameter is a conditional on the target's parent set (or
    a marginal over a subset of them). Allowing arbitrary conditionals
    into Theta silently admits statements that are not CPT entries and
    whose values cannot be consumed by identification formulas without
    contradiction.

    A narrower bidirected-sibling-only loosening does not cover it:
    the disjoint-Y case revealed Tian's c-factor product needs the
    full topo-predecessor closure (Y's V_{<Y} = {X, Z1, Z2} where X
    X is a grandparent through Z1↔Z2. This is the closure
    via directed-or-bidirected reachability — atoms with any path to
    target may appear in ``given``.
    """
    import networkx as nx
    for idx, stmt in enumerate(ground_statements):
        if not isinstance(stmt, ProbabilityStatement):
            continue
        # CLadder Q6772, collider conditioning:
        # observational provenance means this entry is an empirical /
        # joint-derived conditional, not a structural CPT. Skip the
        # parent-subset enforcement — given can contain descendants
        # or other non-parent atoms. Safe because identification
        # algorithms (backdoor, front-door, ID) request structural-
        # parent-aligned keys; observational keys won't match those
        # shapes, so identification naturally won't use them. Direct
        # lookups in associational / probability queries will find
        # observational entries via exact (target, given) match.
        if stmt.provenance == "observational":
            continue
        target_atom = stmt.target.atom
        if target_atom in graph:
            parents = set(graph.predecessors(target_atom))
            ancestors = set(nx.ancestors(graph, target_atom))
        else:
            parents = set()
            ancestors = set()
        # admissible = parents ∪ directed-ancestors ∪
        # bidirected-siblings. Tian's c-factor product factors over
        # topo predecessors (which may include directed ancestors
        # like X → Z1 → Y for P(Y|X,Z1) when iterating chain rule
        # within a c-component) AND bidirected siblings (because
        # topo within a c-component puts them in arbitrary order;
        # validator can't know which order Tian will pick).
        bidir_siblings: set = set()
        for pair in bidirected:
            if target_atom in pair:
                bidir_siblings.update(a for a in pair if a != target_atom)
        admissible = parents | ancestors | bidir_siblings
        given_atoms = {va.atom for va in stmt.given}
        extra = given_atoms - admissible
        if extra:
            extra_names = sorted(a.predicate for a in extra)
            parent_names = sorted(a.predicate for a in parents)
            raise SemanticError(Malformed.GIVEN_NOT_PARENTS,
                                index=idx, extra=extra_names,
                                target=target_atom.predicate,
                                parents=parent_names)


def _query_structural_atoms(q) -> tuple[Atom, ...]:
    """Return the atoms a structural query references.

    Probability queries are intentionally excluded: they are
    distributional lookups that may reference atoms living only in
    Theta, not in the causal DAG.
    """
    if isinstance(q, CauseQuery):
        return (q.from_atom, q.to_atom)
    if isinstance(q, AssocQuery):
        return (q.left, q.right, *q.given)
    if isinstance(q, IdentifyQuery):
        return (q.target, q.intervention.atom, *q.given)
    if isinstance(q, EffectQuery):
        return (
            q.target.atom,
            q.intervention.atom,
            *(iv.atom for iv in q.extra_interventions),
            *(g.atom for g in q.given),
        )
    if isinstance(q, CounterfactualQuery):
        return (
            q.observed.atom,
            q.counterfactual_intervention.atom,
            q.counterfactual_target.atom,
        )
    if isinstance(q, CausationQuery):
        return (q.cause, q.effect)
    if isinstance(q, SCMCounterfactualQuery):
        return (q.intervention.atom, q.target)
    if isinstance(q, CounterfactualConjunctionQuery):
        return tuple(
            a
            for e in (*q.events, *q.condition)
            for a in (e.variable, *(s.atom for s in e.subscript))
        )
    if isinstance(q, ProximalEffectQuery):
        return (
            q.treatment, q.outcome, q.latent,
            *q.treatment_proxy, *q.outcome_proxy, *q.covariates,
        )
    return ()


def _check_query_atoms_in_V(ground_statements, graph) -> None:
    """Every atom referenced by a cause / assoc / identify / effect
    query must be a node in the instantiated working graph G(M).

    Silent False for undeclared query atoms is the same class of bug
    as patterned-query-answered-False caught by ``ground_queries`` in
    slice 2; catching it at validation time keeps the four-state
    contract honest.
    """
    for idx, stmt in enumerate(ground_statements):
        if not isinstance(stmt, QueryStatement):
            continue
        atoms = _query_structural_atoms(stmt.query)
        if not atoms:
            continue
        missing = [a for a in atoms if a not in graph]
        if missing:
            names = sorted({a.predicate for a in missing})
            # A missing atom that DOES appear in a bidirected edge is a
            # different, more confusing situation than a truly undeclared
            # one: the user declared it, but only as a latent-confounding
            # endpoint with no directed causal role, so it never entered
            # the variable set V (built from cause edges). Name that
            # precisely — the canonical case is conditioning on an M-bias
            # collider — instead of the misleading "no cause edge
            # introduces them", which reads as "you forgot to declare it".
            bidir_atoms = {
                a
                for s in ground_statements
                if isinstance(s, BidirectedStatement)
                for a in (s.left, s.right)
            }
            bidir_only = sorted({
                a.predicate for a in missing if a in bidir_atoms
            })
            if bidir_only:
                raise SemanticError(Malformed.QUERY_ATOM_ONLY_BIDIRECTED,
                                    index=idx, query=stmt.id,
                                    atoms=bidir_only)
            raise SemanticError(Malformed.QUERY_ATOM_NOT_IN_GRAPH,
                                index=idx, query=stmt.id, atoms=names)


# Keyed dispatch, not a set of interchangeable checks: the calling convention
# differs per entry because ``bidirected`` is part of the ADMG that the
# ``graph`` argument does not carry, so only the check that needs it is
# handed it. ``...`` is the honest parameter list for that.
_GRAPH_CHECK_FUNCS: dict[str, Callable[..., None]] = {
    "probability_parents": _check_probability_parents,
    "query_atoms_in_V": _check_query_atoms_in_V,
}


def validate_against_graph(
    ground_statements,
    graph,
    checks: frozenset[str] | None = None,
    *,
    bidirected: "frozenset[frozenset]" = frozenset(),
) -> None:
    """Run post-instantiation semantic checks that need the working graph.

    Call this after ``instantiation.instantiate`` +
    ``graph_projection.project``. ``checks`` defaults to
    ``GRAPH_LEVEL_CHECKS``. Raises SemanticError on violation.

    ``bidirected``: the ADMG's bidirected edge set. When
    provided, the probability_parents check loosens its
    ``given ⊆ structural_parents`` rule to also accept bidirected
    siblings of the target — needed for Tian's c-factor product
    Q[S] = ∏ P(V_i | V_{<i}) which factors over topo predecessors
    that may include latent-confounder-linked variables (see wall.md,
    entries iter 150 and iter 165, for the xfail-strict tracker).
    """
    checks = checks if checks is not None else GRAPH_LEVEL_CHECKS
    for name in checks:
        func = _GRAPH_CHECK_FUNCS.get(name)
        if func is None:
            raise KeyError(f"unknown graph-level check: {name}")
        if name == "probability_parents":
            func(ground_statements, graph, bidirected=bidirected)
        else:
            func(ground_statements, graph)


# ---------------------------------------------------------------------------
# public entry
# ---------------------------------------------------------------------------

def validate_program(ast: dict, checks: frozenset[str] | None = None) -> Program:
    """Turn a syntactically-valid AST dict into a typed Program.

    ``checks`` selects which semantic rules to run. Defaults to
    SLICE_1_CHECKS. Later slices pass a larger set.

    Raises SemanticError on any violation.
    """
    checks = checks if checks is not None else SLICE_1_CHECKS

    program = Program(
        version=ast["version"],
        objects=tuple(o["name"] for o in ast["domain"]["objects"]),
        statements=tuple(_to_statement(s) for s in ast["statements"]),
        extensions=ast.get("extensions"),
        options=ast.get("options"),
    )

    for name in checks:
        func = _CHECK_FUNCS.get(name)
        if func is None:
            # Unknown check name is a programmer error, not user input.
            raise KeyError(f"unknown semantic check: {name}")
        func(program)

    return program


def validate_formula(formula) -> None:
    """Check that a formula AST is well-formed.

    Rules enforced:
    - Every VarRef's name is bound by an enclosing SumExpr.
    - Every SumExpr.over is a ground atom (no VarTerm in args).

    Query-context ValuedAtoms (value is None) are accepted without
    binding — per formula_ast_spec_v0_1.md §3.3, their value is
    resolved externally.
    """
    from ..types import (
        ConstantExpr,
        FractionExpr,
        ProbabilityRefExpr,
        ProductExpr,
        SumExpr,
        ValuedAtom,
        VarRef,
    )

    def check(node, bound: frozenset[str]) -> None:
        if isinstance(node, ConstantExpr):
            return
        if isinstance(node, ProbabilityRefExpr):
            _check_valued_atom(node.target, bound)
            for g in node.given:
                _check_valued_atom(g, bound)
            return
        if isinstance(node, ProductExpr):
            for t in node.terms:
                check(t, bound)
            return
        if isinstance(node, FractionExpr):
            # Numerator and denominator are independent sub-formulas; a
            # sum binder on one side does NOT scope into the other, so
            # each is checked under the SAME inherited `bound` (IDC never
            # binds a name spanning the ratio bar).
            check(node.numerator, bound)
            check(node.denominator, bound)
            return
        if isinstance(node, SumExpr):
            for arg in node.over.args:
                if isinstance(arg, VarTerm):
                    raise SemanticError(Malformed.SUM_OVER_NOT_GROUND,
                                        variable=arg.name,
                                        predicate=node.over.predicate)
            check(node.body, bound | {node.bind.name})
            return
        # An invariant, not a refusal: every node the formula AST can hold
        # has a branch above, so reaching this line means this build built
        # something it cannot read. Raised as a builtin, which is how this
        # package says "a developer reads this" — and it matters here more
        # than most, because the one caller that catches SemanticError
        # around this function treats it as "the formula is malformed" and
        # would have turned the bug into a quiet False.
        raise TypeError(f"unknown formula node type: {type(node).__name__}")

    def _check_valued_atom(va: ValuedAtom, bound: frozenset[str]) -> None:
        if va.value is None:
            return  # query-bound, exempt from free-variable check
        if isinstance(va.value, VarRef):
            if va.value.name not in bound:
                raise SemanticError(Malformed.FREE_VARIABLE_IN_FORMULA,
                                    variable=va.value.name)

    check(formula, frozenset())
