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

from ..types import Atom, BridgeFunction, DiscreteChannel, ProximalChannel
from .structural_solver import BidirectedEdgeSet, backdoor_paths, m_separated

#: What the graph leaves for the data, per regime — the rank of a finite
#: channel, or the completeness of an integral operator. Two sentences and
#: not one because they are not the same condition weakened: a rank
#: condition is checkable on the sample and is checked, while completeness
#: is not testable from data at all (Canay, Santos & Shaikh 2013), so what
#: stands in for it numerically is the conditioning of the sieve's own
#: cross-moment matrix — a necessary consequence, never the condition.
_RANK_CONDITION = (
    "秩条件：P(W|Z,x) 对每个 x 都可逆（两个代理各自至少有 k 个取值，"
    "且都与 U 相关）",
)
_COMPLETENESS_CONDITION = (
    "完备性：E[·|Z,X=x] 作为算子对 bridge 所在的函数类完备（连续版本的秩条件，"
    "且它在数据上原则上不可检验）",
    "bridge 落在声明的基函数张成的空间里——基函数族和维数是断言，不是设置",
)


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
    treatment_proxy: Atom    # Z — treatment-inducing proxy (Miao) / neg-control exposure
    outcome_proxy: Atom      # W — outcome-inducing proxy (Miao) / neg-control outcome
    #: Which algebra the caller asked the proxies to be read by. The graph
    #: decision above is the same either way — model (f) is model (f) — and
    #: this is what the numeric layer is then obliged to run and what the two
    #: fields below are read off.
    channel: "ProximalChannel"
    method: str = "proximal_matrix"
    # Assumptions the GRAPH cannot discharge — the numeric layer must check them
    # against the data (never assume them silently).
    data_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProximalNotIdentified:
    """Structural refusal: the declared ``(U, Z, W)`` do not form Miao model (f).

    ``failed_criterion`` is a stable machine tag; ``reason`` is the human-facing
    diagnosis (which independence / structural precondition broke). Returning a
    *reason* rather than a bare sentinel is deliberate — the point of proximal
    inference is to tell the analyst precisely why their proxies are inadequate.
    """

    failed_criterion: str
    reason: str


def identify_proximal(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    *,
    treatment: Atom,
    outcome: Atom,
    latent: Atom,
    treatment_proxy: Atom,
    outcome_proxy: Atom,
    channel: ProximalChannel,
) -> ProximalEstimand | ProximalNotIdentified:
    """Decide whether ``P(outcome | do(treatment))`` is proximal-identifiable
    via the declared unobserved confounder ``latent`` and proxies
    ``treatment_proxy`` (Z) / ``outcome_proxy`` (W), per Miao model (f).

    Returns a :class:`ProximalEstimand` on success, or a
    :class:`ProximalNotIdentified` naming the criterion that failed. This is a
    pure graph decision; the rank / relevance condition on the proxies is a
    data property and is recorded on the estimand, not decided here.
    """
    x, y, u, z, w = treatment, outcome, latent, treatment_proxy, outcome_proxy

    # --- structural preconditions ------------------------------------------
    roles = {"treatment": x, "outcome": y, "latent": u,
             "treatment_proxy": z, "outcome_proxy": w}
    for name, node in roles.items():
        if node not in graph:
            return ProximalNotIdentified(
                "missing_node",
                f"声明的{name} {node.predicate!r} "
                f"不是这张图上的节点",
            )
    if len({x, y, u, z, w}) != 5:
        return ProximalNotIdentified(
            "roles_not_distinct",
            "处理、结局、潜混杂 U、处理侧代理 Z、结局侧代理 W "
            "必须是五个互不相同的变量",
        )
    # Regime-specific, and the ONLY thing about the channel this layer reads:
    # a latent with one state is not a confounder, which is a statement about
    # the declared k and has no counterpart where no k is declared.
    if isinstance(channel, DiscreteChannel) and channel.latent_cardinality < 2:
        return ProximalNotIdentified(
            "degenerate_latent",
            f"未观测混杂至少要有 2 个类别"
            f"（声明的是 k={channel.latent_cardinality}）；"
            f"只有 1 个类别的 U 不构成混杂",
        )

    # U must be a legitimate adjustment variable: not a descendant of the
    # treatment (back-door criterion condition (i)).
    if u in nx.descendants(graph, x):
        return ProximalNotIdentified(
            "latent_is_descendant",
            f"未观测混杂 {u.predicate!r} 是处理 {x.predicate!r} 的后代；"
            f"它不能充当后门调整",
        )

    # --- Miao model (f) proxy criteria (checked first) ---------------------
    # A broken proxy structure typically ALSO makes {U} look insufficient (a
    # leaking proxy opens an X…Y path {U} cannot block), so the precise
    # proxy diagnosis must win over the generic "U not sufficient" one; the
    # residual-confounding check below is then reserved for the case where the
    # proxies are sound but a confounder OTHER than U is left unblocked.
    #
    # W ⊥ (Z, X) | U  ≡  W ⊥ Z | U  and  W ⊥ X | U  (graph separation of a set
    # equals separation of each member for a fixed conditioning set).
    if not m_separated(graph, bidirected, w, z, (u,)):
        return ProximalNotIdentified(
            "outcome_proxy_leaks_to_treatment_proxy",
            f"结局侧代理 {w.predicate!r} 在给定 U 后与处理侧代理 "
            f"{z.predicate!r} 并不独立——model (f) 要求 "
            f"W ⊥ (Z, X) | U；两个代理之间还有一条绕开 U 的通路",
        )
    if not m_separated(graph, bidirected, w, x, (u,)):
        return ProximalNotIdentified(
            "outcome_proxy_leaks_to_treatment",
            f"结局侧代理 {w.predicate!r} 在给定 U 后与处理 "
            f"{x.predicate!r} 并不独立——model (f) 要求 "
            f"W ⊥ (Z, X) | U；W 只能影响结局这一侧",
        )
    # Z ⊥ Y | (U, X): the treatment proxy reaches the outcome only through U
    # and the treatment itself (it may cause X, but must not touch Y otherwise).
    if not m_separated(graph, bidirected, z, y, (u, x)):
        return ProximalNotIdentified(
            "treatment_proxy_leaks_to_outcome",
            f"处理侧代理 {z.predicate!r} 在给定 (U, X) 后与结局 "
            f"{y.predicate!r} 并不独立——model (f) 要求 "
            f"Z ⊥ Y | (U, X)；Z 只能影响处理这一侧",
        )

    # --- U is a sufficient confounder: {U} blocks every back-door path -----
    # Back-door criterion (ii): {U} m-separates X from Y in G with X's outgoing
    # edges deleted. With the proxies verified sound above, a failure here means
    # a DISTINCT unblocked confounder (not U, not a leaking proxy) — a single
    # proxy pair cannot restore the effect.
    g_bar_x = graph.copy()
    g_bar_x.remove_edges_from(list(graph.out_edges(x)))
    if not m_separated(g_bar_x, bidirected, x, y, (u,)):
        return ProximalNotIdentified(
            "latent_not_sufficient",
            f"条件在未观测的 {u.predicate!r} 上，并挡不住 {x.predicate!r} 与 "
            f"{y.predicate!r} 之间的每一条后门路径；还剩下 {u.predicate!r} "
            f"吸收不了的混杂，所以单独一对代理救不回这个效应",
        )

    bridge = isinstance(channel, BridgeFunction)
    return ProximalEstimand(
        treatment=x,
        outcome=y,
        latent=u,
        treatment_proxy=z,
        outcome_proxy=w,
        channel=channel,
        method="proximal_bridge" if bridge else "proximal_matrix",
        data_conditions=(
            _COMPLETENESS_CONDITION if bridge else _RANK_CONDITION),
    )
