"""Proximal causal inference — identification (Miao-Geng-Tchetgen 2018,
Biometrika 105(4); Kuroki-Pearl 2014, Biometrika 101(2) as independent source).

The kernel's back-door / front-door / general-ID engines all assume the
confounders on the relevant back-door paths are **observed**. Proximal
inference is the escape hatch one rung further out: the sufficient confounder
``U`` is *unobserved*, and identification is bought instead with two observed
**proxies** of ``U`` — a treatment-inducing proxy ``Z`` and an outcome-inducing
proxy ``W`` (in the negative-control vocabulary: a negative-control exposure and
a negative-control outcome).

This module decides the *structural* half of proximal identifiability: given a
causal diagram in which ``U`` is a named-but-unobserved node, does the pair
``(Z, W)`` satisfy Miao et al.'s **model (f)** proxy structure, so that the
average causal effect ``P(y | do(x))`` is (nonparametrically, in the discrete
regime) a matrix functional of the observed law? The numeric half — building the
Z×W contingency matrices and solving the linear system of Miao's identifying
formula (5) — lives in ``themis.estimation.proximal``; this file only produces /
refuses the estimand descriptor.

Model (f) (Miao-Geng-Tchetgen 2018, Table 1 (f) + Fig. 1(f)), the *weakest* of
the paper's proxy diagrams and the one that subsumes (a)-(e):

    W ⊥ (Z, X) | U          (W is a proxy that may cause Y directly)
    Z ⊥ Y | (U, X)          (Z is a proxy that may be caused-by / cause X)

together with ``U`` a **sufficient confounder** for ``(X, Y)`` (i.e. {U}
satisfies the back-door criterion). Under these, Miao's identifying formula

    P(y | do(x)) = P(y | Z, x) · P(W | Z, x)^{-1} · P(W)                    (5)

holds *without* identifying the measurement-error mechanism P(W | U) — the
crucial generalisation over Kuroki-Pearl, whose recovery of P(W | U) additionally
requires W ⊥ Y | U (Miao's models (d)/(e), the special case W has no direct
effect on Y).

Point identification additionally needs the **rank condition** — P(W | Z, x)
invertible for every x, equivalently the discrete proxies each have at least as
many levels as ``U`` and are genuinely relevant to it. That condition is a
property of the *data*, not the graph; it is recorded here as an assumption the
numeric layer must check and reported to the caller, never silently assumed.

The counterfactual graph engines (``ctf_identify``) and this module share the
same discipline: a self-contained structural primitive, no scheduler / kernel
wiring here — the estimation dispatch and the query surface consume it next.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .. import language
from ..types import Atom, BridgeFunction, DiscreteChannel, ProximalChannel
from .structural_solver import BidirectedEdgeSet, backdoor_paths, m_separated


class Role(language.Word, vocabulary="proximal_role"):
    """Which part of Miao model (f) a variable was declared to play.

    Interpolated rather than carried: a refusal below says WHICH of the five
    roles names a node the graph does not have, and the role goes inside that
    sentence. While the five were the keys of a dict the message read, the
    reader was handed ``treatment_proxy`` mid-clause — the kernel's own field
    name, in no language, inside a sentence written in one.
    """

    TREATMENT = ("treatment", {"zh": "处理", "en": "the treatment"})
    OUTCOME = ("outcome", {"zh": "结局", "en": "the outcome"})
    LATENT = ("latent", {
        "zh": "未观测混杂 U", "en": "the unobserved confounder U"})
    TREATMENT_PROXY = ("treatment_proxy", {
        "zh": "处理侧代理 Z", "en": "the treatment-side proxy Z"})
    OUTCOME_PROXY = ("outcome_proxy", {
        "zh": "结局侧代理 W", "en": "the outcome-side proxy W"})
    COVARIATE = ("covariate", {
        "zh": "协变量 C", "en": "a covariate C"})


class Criterion(language.Word, vocabulary="proximal_criterion_failure"):
    """Which precondition of model (f) the declared variables broke.

    A ``Word`` and not a table, because the token is ours and a raise site
    names one: a member is a name a typo cannot survive, which is the
    discipline :class:`themis.refusals.Refusal` is held to one layer down.

    The text on each member is the WHOLE sentence rather than a noun phrase
    naming the criterion, and that is what this vocabulary is for. The
    sentence used to be written at the return site as an f-string, so the
    module that decides identifiability was also the author of the reader's
    wording — and, being one module, it wrote it in one language. Both
    surfaces that show it (the gap list and the refusal note) then framed a
    Chinese payload in an English template for an English reader, because
    :func:`themis.language.halve` routes a bare string to the half that
    "renders the same in every language" and a rendered sentence is not that.

    A member's holes are this occasion's facts — which node, which role —
    and they travel beside the token, so the sentence is put together where
    the reader's language is known and nowhere earlier.
    """

    MISSING_NODE = ("missing_node", {
        "zh": "声明为{role}的 {node} 不是这张图上的节点",
        "en": "{node}, declared as {role}, is not a node of this graph",
    })
    ROLES_NOT_DISTINCT = ("roles_not_distinct", {
        "zh": "处理、结局、未观测混杂 U、每一个处理侧代理 Z、每一个结局侧"
              "代理 W、每一个协变量 C，必须两两不同——一个变量同时担两个角色，"
              "model (f) 的条件里就会同时出现在等号两边",
        "en": "the treatment, the outcome, the unobserved confounder U, each "
              "treatment-side proxy Z, each outcome-side proxy W and each "
              "covariate C have to be distinct from one another — a variable "
              "in two roles stands on both sides of a model (f) condition at "
              "once",
    })
    COVARIATE_IS_DESCENDANT = ("covariate_is_descendant", {
        "zh": "协变量 {covariate} 是处理 {treatment} 的后代，不能被条件在"
              "上面——那会挡掉正被问的那部分效应，或者打开一条对撞路径。"
              "要分层，就分在处理之前就定下来的变量上",
        "en": "the covariate {covariate} is a descendant of the treatment "
              "{treatment} and cannot be conditioned on — doing so blocks "
              "part of the very effect being asked for, or opens a collider "
              "path. Stratify on variables settled before the treatment was",
    })
    DEGENERATE_LATENT = ("degenerate_latent", {
        "zh": "未观测混杂至少要有 2 个类别（声明的是 k={cardinality}）；"
              "只有 1 个类别的 U 不构成混杂",
        "en": "the unobserved confounder needs at least 2 categories and "
              "k={cardinality} was declared; a U with one category confounds "
              "nothing",
    })
    LATENT_IS_DESCENDANT = ("latent_is_descendant", {
        "zh": "未观测混杂 {latent} 是处理 {treatment} 的后代；"
              "它不能充当后门调整",
        "en": "the unobserved confounder {latent} is a descendant of the "
              "treatment {treatment}, so it cannot serve as a back-door "
              "adjustment",
    })
    OUTCOME_PROXY_LEAKS_TO_TREATMENT_PROXY = (
        "outcome_proxy_leaks_to_treatment_proxy", {
            "zh": "结局侧代理 {outcome_proxy} 在给定 U 后与处理侧代理 "
                  "{treatment_proxy} 并不独立——model (f) 要求 W ⊥ (Z, X) | U；"
                  "两个代理之间还有一条绕开 U 的通路",
            "en": "the outcome-side proxy {outcome_proxy} is not independent "
                  "of the treatment-side proxy {treatment_proxy} given U, and "
                  "model (f) requires W ⊥ (Z, X) | U; there is a path between "
                  "the two proxies that goes around U",
        })
    OUTCOME_PROXY_LEAKS_TO_TREATMENT = ("outcome_proxy_leaks_to_treatment", {
        "zh": "结局侧代理 {outcome_proxy} 在给定 U 后与处理 {treatment} "
              "并不独立——model (f) 要求 W ⊥ (Z, X) | U；W 只能影响结局这一侧",
        "en": "the outcome-side proxy {outcome_proxy} is not independent of "
              "the treatment {treatment} given U, and model (f) requires "
              "W ⊥ (Z, X) | U; W may touch the outcome side only",
    })
    TREATMENT_PROXY_LEAKS_TO_OUTCOME = ("treatment_proxy_leaks_to_outcome", {
        "zh": "处理侧代理 {treatment_proxy} 在给定 (U, X) 后与结局 {outcome} "
              "并不独立——model (f) 要求 Z ⊥ Y | (U, X)；Z 只能影响处理这一侧",
        "en": "the treatment-side proxy {treatment_proxy} is not independent "
              "of the outcome {outcome} given (U, X), and model (f) requires "
              "Z ⊥ Y | (U, X); Z may touch the treatment side only",
    })
    LATENT_NOT_SUFFICIENT = ("latent_not_sufficient", {
        "zh": "条件在未观测的 {latent} 上，并挡不住 {treatment} 与 {outcome} "
              "之间的每一条后门路径；还剩下 {latent} 吸收不了的混杂，"
              "所以单独一对代理救不回这个效应",
        "en": "conditioning on the unobserved {latent} does not block every "
              "back-door path between {treatment} and {outcome}; confounding "
              "{latent} cannot absorb is left over, so a single pair of "
              "proxies does not recover this effect",
    })


class DataCondition(language.Word, vocabulary="proximal_data_condition"):
    """What the graph leaves for the data to discharge, per regime.

    Members rather than one sentence per regime, because the reader is
    handed them as a LIST and the continuous regime owes two: what makes
    the operator invertible, and what the bridge was assumed to be. Joined
    where the reader is, in that language's punctuation.

    The rank condition and completeness are not the same condition
    weakened. A rank condition is checkable on the sample and is checked;
    completeness is not testable from data at all (Canay, Santos & Shaikh
    2013), so what stands in for it numerically is the conditioning of the
    sieve's own cross-moment matrix — a necessary consequence, never the
    condition.
    """

    RANK = ("rank", {
        "zh": "秩条件：P(W|Z,x) 对每个 x 都可逆（两个代理各自至少有 k 个"
              "取值，且都与 U 相关）",
        "en": "the rank condition: P(W|Z,x) is invertible for every x — each "
              "proxy takes at least k values and both are genuinely related "
              "to U",
    })
    COMPLETENESS = ("completeness", {
        "zh": "完备性：E[·|Z,X=x] 作为算子对 bridge 所在的函数类完备"
              "（连续版本的秩条件，且它在数据上原则上不可检验）",
        "en": "completeness: the operator E[·|Z,X=x] is complete for the "
              "class the bridge lies in — the continuous counterpart of the "
              "rank condition, and one no data can check even in principle",
    })
    BRIDGE_IN_SPAN = ("bridge_in_span", {
        "zh": "bridge 落在声明的基函数张成的空间里——基函数族和维数是断言，"
              "不是设置",
        "en": "the bridge lies in the span of the declared basis — the family "
              "and the dimension are an assertion, not a setting",
    })


_RANK_CONDITION = (DataCondition.RANK,)
_COMPLETENESS_CONDITION = (DataCondition.COMPLETENESS,
                           DataCondition.BRIDGE_IN_SPAN)


@dataclass(frozen=True)
class ProximalEstimand:
    """A proximal-identifiable average causal effect ``P(Y | do(X))``.

    Carries the resolved variable roles the numeric layer needs to build Miao's
    formula (5) and the structured record of what was verified vs. what the data
    must still discharge (the rank / relevance condition on the proxies).
    """

    treatment: Atom          # X
    outcome: Atom            # Y
    latent: Atom             # U — a named but unobserved node of the diagram
    #: Z — treatment-inducing proxies (Miao) / negative-control exposures.
    treatment_proxy: tuple[Atom, ...]
    #: W — outcome-inducing proxies (Miao) / negative-control outcomes.
    outcome_proxy: tuple[Atom, ...]
    #: Which algebra the caller asked the proxies to be read by. The graph
    #: decision above is the same either way — model (f) is model (f) — and
    #: this is what the numeric layer is then obliged to run and what the two
    #: fields below are read off.
    channel: "ProximalChannel"
    #: C — the observed variables every condition above was read within, and
    #: the effect is averaged over at the end.
    covariates: tuple[Atom, ...] = ()
    method: str = "proximal_matrix"
    # Assumptions the GRAPH cannot discharge — the numeric layer must check them
    # against the data (never assume them silently). Members rather than
    # sentences: the envelope carries the tokens and the reader's surface
    # joins their text, which is the rule the envelope is held to everywhere
    # else and the one this field was the last proximal holdout from.
    data_conditions: tuple[DataCondition, ...] = ()


@dataclass(frozen=True)
class ProximalNotIdentified:
    """Structural refusal: the declared ``(U, Z, W)`` do not form Miao model (f).

    Carries the STATEMENT rather than a rendered sentence: which criterion
    broke, and this occasion's facts for the holes in that criterion's text.
    Saying precisely why the proxies are inadequate is the whole point of a
    proximal refusal — and saying it as prose made this module the author of
    the wording, which is the same as making it the chooser of the language.

    :attr:`failed_criterion` is the machine tag it always was, read off the
    statement rather than stored beside it: two records of one fact are free
    to disagree, and the tag IS the statement's token.
    """

    statement: language.Statement

    @property
    def failed_criterion(self) -> str:
        return str(self.statement.get("token") or "")


def _refuse(criterion: Criterion, **facts) -> ProximalNotIdentified:
    """One refusal, as the sentence it is and the facts it has for it."""
    return ProximalNotIdentified(language.state(criterion, **facts))


def identify_proximal(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    *,
    treatment: Atom,
    outcome: Atom,
    latent: Atom,
    treatment_proxy: tuple[Atom, ...],
    outcome_proxy: tuple[Atom, ...],
    covariates: tuple[Atom, ...] = (),
    channel: ProximalChannel,
) -> ProximalEstimand | ProximalNotIdentified:
    """Decide whether ``P(outcome | do(treatment))`` is proximal-identifiable
    via the declared unobserved confounder ``latent`` and proxies
    ``treatment_proxy`` (Z) / ``outcome_proxy`` (W), per Miao model (f), read
    within the observed ``covariates`` (C).

    Returns a :class:`ProximalEstimand` on success, or a
    :class:`ProximalNotIdentified` naming the criterion that failed. This is a
    pure graph decision; the rank / relevance condition on the proxies is a
    data property and is recorded on the estimand, not decided here.

    Both proxy roles are SETS, and model (f) does not change for that. Its
    conditions are d-separations, and a d-separation of two SETS given a
    fixed conditioning set holds exactly when it holds for every pair drawn
    from them — every path from the one set to the other is a path from some
    member to some member. So this reads the same criteria over more pairs
    rather than a second criterion for the plural case, and the sentence a
    reader gets still names the two variables whose path is open.

    ``covariates`` join the conditioning set of every one of those
    separations and of the back-door check: the whole argument is then made
    WITHIN a level of C, which is what makes a stratified proximal question
    a proximal question rather than a different method.
    """
    x, y, u = treatment, outcome, latent
    zs, ws, cs = treatment_proxy, outcome_proxy, covariates

    # --- structural preconditions ------------------------------------------
    roles: tuple[tuple[Role, Atom], ...] = (
        (Role.TREATMENT, x), (Role.OUTCOME, y), (Role.LATENT, u),
        *((Role.TREATMENT_PROXY, a) for a in zs),
        *((Role.OUTCOME_PROXY, a) for a in ws),
        *((Role.COVARIATE, a) for a in cs),
    )
    for role, node in roles:
        if node not in graph:
            return _refuse(Criterion.MISSING_NODE,
                           role=role, node=node.predicate)
    if len({node for _, node in roles}) != len(roles):
        return _refuse(Criterion.ROLES_NOT_DISTINCT)
    # A covariate that X causes is not a thing to hold fixed — conditioning
    # on it blocks part of the very effect being asked for, or opens a
    # collider path. This is back-door condition (i) again, applied to the
    # set the caller added rather than to U, and it has to be checked here
    # because C is the caller's and U is only ever declared.
    for c in cs:
        if c in nx.descendants(graph, x):
            return _refuse(Criterion.COVARIATE_IS_DESCENDANT,
                           covariate=c.predicate, treatment=x.predicate)
    # Regime-specific, and the ONLY thing about the channel this layer reads:
    # a latent with one state is not a confounder, which is a statement about
    # the declared k and has no counterpart where no k is declared.
    if isinstance(channel, DiscreteChannel) and channel.latent_cardinality < 2:
        return _refuse(Criterion.DEGENERATE_LATENT,
                       cardinality=channel.latent_cardinality)

    # U must be a legitimate adjustment variable: not a descendant of the
    # treatment (back-door criterion condition (i)).
    if u in nx.descendants(graph, x):
        return _refuse(Criterion.LATENT_IS_DESCENDANT,
                       latent=u.predicate, treatment=x.predicate)

    # --- Miao model (f) proxy criteria (checked first) ---------------------
    # A broken proxy structure typically ALSO makes {U} look insufficient (a
    # leaking proxy opens an X…Y path {U} cannot block), so the precise
    # proxy diagnosis must win over the generic "U not sufficient" one; the
    # residual-confounding check below is then reserved for the case where the
    # proxies are sound but a confounder OTHER than U is left unblocked.
    #
    # W ⊥ (Z, X) | (U, C)  ≡  W ⊥ Z | (U, C)  and  W ⊥ X | (U, C), and each of
    # those over every (w, z) pair (graph separation of a set equals separation
    # of each member for a fixed conditioning set).
    given = (u, *cs)
    for w in ws:
        for z in zs:
            if not m_separated(graph, bidirected, w, z, given):
                return _refuse(Criterion.OUTCOME_PROXY_LEAKS_TO_TREATMENT_PROXY,
                               outcome_proxy=w.predicate,
                               treatment_proxy=z.predicate)
        if not m_separated(graph, bidirected, w, x, given):
            return _refuse(Criterion.OUTCOME_PROXY_LEAKS_TO_TREATMENT,
                           outcome_proxy=w.predicate, treatment=x.predicate)
    # Z ⊥ Y | (U, X, C): the treatment proxy reaches the outcome only through U
    # and the treatment itself (it may cause X, but must not touch Y otherwise).
    for z in zs:
        if not m_separated(graph, bidirected, z, y, (u, x, *cs)):
            return _refuse(Criterion.TREATMENT_PROXY_LEAKS_TO_OUTCOME,
                           treatment_proxy=z.predicate, outcome=y.predicate)

    # --- U is a sufficient confounder: {U, C} blocks every back-door path --
    # Back-door criterion (ii): {U, C} m-separates X from Y in G with X's
    # outgoing edges deleted. With the proxies verified sound above, a failure
    # here means a DISTINCT unblocked confounder (not U, not a leaking proxy) —
    # more proxies of the same U cannot restore the effect, which is why this
    # refusal does not become gentler for being given several.
    g_bar_x = graph.copy()
    g_bar_x.remove_edges_from(list(graph.out_edges(x)))
    if not m_separated(g_bar_x, bidirected, x, y, given):
        return _refuse(Criterion.LATENT_NOT_SUFFICIENT,
                       latent=u.predicate, treatment=x.predicate,
                       outcome=y.predicate)

    bridge = isinstance(channel, BridgeFunction)
    return ProximalEstimand(
        treatment=x,
        outcome=y,
        latent=u,
        treatment_proxy=zs,
        outcome_proxy=ws,
        covariates=cs,
        channel=channel,
        method="proximal_bridge" if bridge else "proximal_matrix",
        data_conditions=(
            _COMPLETENESS_CONDITION if bridge else _RANK_CONDITION),
    )
