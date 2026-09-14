"""Phase 9 §S9.2: Mohan-Pearl-Tian recoverability from missing data.

Sits beside ``selection_recovery.py`` (§S9.1). Both ask "can the
unbiased quantity be recovered from data corrupted by a selection/
response process?" — but the theories are distinct. Selection bias
conditions on ONE selection event S=1; missing data conditions on a
SET of response events R=0 (one per partially-observed variable), and
the workhorse is not a single adjustment but an *ordered factorization*
that recovers a query factor by factor.

An **m-graph** (Mohan, Pearl & Tian 2013, "Graphical Models for
Inference with Missing Data", NeurIPS) is the causal DAG G(M) over the
substantive variables V = V_o (fully observed) ∪ V_m (partially
observed), augmented with a missingness indicator R_i for each
V_i ∈ V_m. R_i's parents are the mechanism that decides whether V_i is
recorded (R_i=0 ⇒ recorded, R_i=1 ⇒ missing). The manifest data is
P(V_o, V*_m, R); complete-case analysis conditions on R=0.

Two textbook results are implemented:

- **Mechanism classification** (graphical, complete):
  * **MCAR**  — R ⊥ (V_o ∪ V_m): missingness independent of everything.
  * **MAR**   — V_m ⊥ R | V_o: missingness independent of the missing
    values given the observed ones (Rubin's MAR, graphically).
  * **MNAR**  — neither holds.

- **Recoverability of a query** P(Y | X) via the **ordered
  factorization** sufficient condition (Mohan-Pearl-Tian 2013). Order
  Y = Y₁ < … < Y_k and write P(Y|X) = ∏ᵢ P(Yᵢ | Xᵢ) with Xᵢ ⊆
  ({Y_{i+1},…,Y_k} ∪ X) a set for which Yᵢ ⊥ (({Y_{i+1..k}}∪X) ∖ Xᵢ) | Xᵢ
  (so the factorization is valid). The query is recoverable if some
  ordering makes **every** factor satisfy Yᵢ ⊥ R_{Wᵢ} | Xᵢ, where
  Wᵢ = {Yᵢ} ∪ Xᵢ and R_{Wᵢ} are the indicators of the partially-observed
  variables in Wᵢ. Each such factor then equals P(Yᵢ | Xᵢ, R_{Wᵢ}=0) and
  is estimable from complete cases.

  The marginal P(X) is the one-factor special case: recoverable iff
  X ⊥ R_X, so a **self-masking** mechanism X → R_X makes it
  unrecoverable — the canonical MNAR obstruction.

Scope (structural identification only, mirroring §S9.1 / transport §T9.1):
- The ordered factorization is a SUFFICIENT condition. A negative
  verdict says "not recoverable via ordered factorization", NOT a proof
  of non-recoverability — the complete characterization is deferred.
- No numeric estimation: this returns the recovery formula (which
  complete-case factors to combine), not a number.
- No latent (bidirected) edges in the m-graph and no causal-query-under-
  missingness (do-recovery) in v1 — deferred, as ADMG m-graphs and the
  do-calculus-for-missingness are follow-ups.

The base graph G(M) is never mutated; the m-graph is built fresh and all
tests are read-only d-separation queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import unique
from itertools import combinations, permutations

import networkx as nx

from .. import language
from ..types import Atom, MissingnessIndicator


# ============================================================= words


@unique
class Shortfall(language.Word, vocabulary="missing_data_shortfall",
                between=language.BETWEEN_STATEMENTS):
    """Which factor came back not recoverable, when this is a negative.

    Its twin is
    :class:`themis.runtime.selection_recovery.Shortfall`, and it is here
    for the same reason: a row could name the factorization that worked
    and had nothing to name what did not, so a negative went into one
    free-text field along with everything else it knew.

    Neither of the two clauses these sentences used to end with is here.
    "Not a proof of non-recoverability" is a property of the criterion and
    is now :attr:`MissingDataRecoveryResult.complete_criterion`; how far
    the search went is ``search_budget``. What is left is only which
    factor came back empty.
    """

    NO_RECOVERABLE_ORDERED_FACTORIZATION = (
        "no_recoverable_ordered_factorization", {
            "zh": "在每一种可用的条件方式下，都有某个因子的目标仍与相关的"
                  "缺失指示变量 d-连通（例如一条自遮蔽的 V→R_V 边），"
                  "所以没有可恢复的有序因子分解",
            "en": "under every available way of conditioning, some factor's "
                  "target stays d-connected to a missingness indicator that "
                  "matters to it (a self-masking V→R_V edge, say), so no "
                  "ordered factorization recovers the target",
        })
    A_PRODUCT_IS_BLOCKED_BY_ITS_FACTORS = (
        "a_product_is_blocked_by_its_factors", {
            "zh": "{factors}。干预估计量是这些因子的乘积，任何一个不行都会"
                  "卡住它",
            "en": "{factors}. The interventional estimand is the product of "
                  "these factors, so any one of them blocks it",
        })
    THE_ADJUSTED_CONDITIONAL = ("the_adjusted_conditional", {
        "zh": "调整后的条件分布 {target} 不可恢复",
        "en": "the adjusted conditional {target} is not recoverable",
    })
    THE_COVARIATE_MARGINAL = ("the_covariate_marginal", {
        "zh": "协变量边缘分布 {target} 不可恢复（例如一个自遮蔽的混杂 "
              "Z→R_Z）",
        "en": "the covariate marginal {target} is not recoverable (a "
              "self-masking confounder Z→R_Z, say)",
    })


@unique
class Factor(language.Word, vocabulary="recovery_factor",
             between=language.BETWEEN_ITEMS):
    """Which factor of the estimand this is — the role, not the expression.

    The expression beside it is symbolic and reads the same to everyone.
    The two used to be one string with the role glued on the front in
    English, and the expression in it was a literal ``P(Y|X,Z)`` rather
    than this program's own predicates — a second record of the target,
    already disagreeing with the first.
    """

    ADJUSTED_CONDITIONAL = ("adjusted_conditional", {
        "zh": "调整后的条件分布 {target}",
        "en": "the adjusted conditional {target}",
    })
    COVARIATE_MARGINAL = ("covariate_marginal", {
        "zh": "协变量边缘分布 {target}",
        "en": "the covariate marginal {target}",
    })


# Reserved predicate prefix for R nodes inside the m-graph. Collides with
# no real predicate (the atom schema forbids leading underscores), so an
# R node can never be mistaken for a substantive variable.
_R_PREDICATE_PREFIX = "__R__"


# ============================================================= m-graph


def _r_node_atom(missing_var: Atom) -> Atom:
    """The indicator of one node: that node's arguments and time, under
    the reserved predicate.

    Named by the predicate alone, two partially observed nodes of one
    variable -- ``y`` now and ``y`` a step back, or ``y`` of two people --
    were one indicator, and every separation read off it was about both.
    """
    return Atom(
        predicate=f"{_R_PREDICATE_PREFIX}{missing_var.predicate}",
        args=missing_var.args,
        time_index=missing_var.time_index,
    )


def is_r_node(atom: Atom) -> bool:
    return atom.predicate.startswith(_R_PREDICATE_PREFIX)


def build_m_graph(
    base_graph: nx.DiGraph,
    indicators,
) -> tuple[nx.DiGraph, dict]:
    """Build the m-graph = G(M) ∪ {parent → R_i} from the declared
    MissingnessIndicator statements.

    Returns ``(m_graph, r_of_var)`` where ``r_of_var`` maps each
    partially-observed variable's graph node to its R-node atom. The
    original ``base_graph`` is not mutated.

    Every atom an indicator names is a node of ``base_graph``: the
    graph-level check ``missingness_atoms_in_V`` refuses a program where
    one is not, so one arriving here is a broken invariant and raises.
    It used to be skipped, which answers for a program with that edge,
    or that indicator, taken out.

    An indicator's atoms are nodes of the graph as they stand, and are
    used as such. They used to be looked up by predicate, which keeps one
    node per predicate: on a program unrolled in time, or about several
    people, the indicator landed on whichever node of the variable the
    graph happened to list last.
    """
    m_graph = base_graph.copy()
    r_of_var: dict = {}
    for mi in indicators:
        if not isinstance(mi, MissingnessIndicator):
            continue
        stray = [a for a in (mi.missing_var, *mi.caused_by)
                 if a not in base_graph]
        if stray:
            raise ValueError(
                f"missingness indicator {mi.id} names {stray}, which are "
                f"not nodes of the graph"
            )
        var_node = mi.missing_var
        r_atom = _r_node_atom(var_node)
        m_graph.add_node(r_atom, kind="missingness_indicator")
        r_of_var[var_node] = r_atom
        for parent in mi.caused_by:
            m_graph.add_edge(parent, r_atom)
    return m_graph, r_of_var


# ============================================================= helpers


def _dsep(graph: nx.DiGraph, a: Atom, b: Atom, conditioning) -> bool:
    from .structural_solver import is_d_connected
    return not is_d_connected(graph, a, b, tuple(conditioning))


def _sorted_atoms(atoms) -> tuple[Atom, ...]:
    return tuple(sorted(atoms, key=lambda a: a.predicate))


def _names(atoms) -> str:
    return ", ".join(a.predicate for a in atoms)


# ============================================================= classify


def classify_missingness(
    m_graph: nx.DiGraph,
    r_of_var: dict,
    substantive_nodes,
) -> str:
    """Classify the missingness mechanism graphically (Mohan-Pearl-Tian).

    Returns ``"MCAR"`` / ``"MAR"`` / ``"MNAR"`` / ``"none"`` (no declared
    indicators). MCAR is tested first (it is the strongest); a graph that
    passes MCAR also passes MAR, so the returned label is the strongest
    that holds.
    """
    r_atoms = list(r_of_var.values())
    if not r_atoms:
        return "none"
    vm = set(r_of_var.keys())
    vo = [n for n in substantive_nodes if n not in vm]

    # MCAR: every R d-separated from every substantive variable (∅ cond).
    if all(_dsep(m_graph, r, v, ()) for r in r_atoms for v in substantive_nodes):
        return "MCAR"
    # MAR: every R d-separated from every partially-observed V given V_o.
    if all(_dsep(m_graph, r, vmi, vo) for r in r_atoms for vmi in vm):
        return "MAR"
    return "MNAR"


# ============================================================= recover


@dataclass(frozen=True)
class MissingDataRecoveryResult:
    """Verdict of a missing-data recoverability analysis.

    ``mechanism`` is the MCAR/MAR/MNAR label; ``recoverable`` says whether
    the target P(Y|X) admits a recovering ordered factorization;
    ``factorization`` lists the (Yᵢ, Xᵢ) factors in order; ``formula_repr``
    is the complete-case recovery expression.
    """
    target_repr: str
    mechanism: str
    recoverable: bool
    factorization: tuple[tuple[Atom, tuple[Atom, ...]], ...]
    formula_repr: str
    partially_observed: tuple[Atom, ...]
    failure_reason: language.Statement | None = None
    #: Whether the test behind this verdict is necessary as well as
    #: sufficient. Ordered factorization is sufficient only, so a negative
    #: from it means "not by this criterion" rather than "provably not
    #: recoverable". Its twin sits on the selection block; both used to be
    #: a clause inside the sentence, restated in each branch that
    #: remembered to.
    complete_criterion: bool = False
    #: The largest conditioning set Xᵢ the factorization search looked at.
    #: A negative verdict is a claim about that range and not about every
    #: factorization there is, so a reader told "not recoverable" is owed
    #: the quantifier, and a verifier re-deriving the verdict has to
    #: re-derive the same claim rather than one that happens to share a
    #: constant with it. Recorded on every verdict, including the ones the
    #: search never ran for, because what it states is how this analysis
    #: was configured. Its twin is
    #: :attr:`themis.runtime.selection_recovery.SelectionRecoveryResult.search_budget`.
    search_budget: int = 0


def _pick_xi(
    m_graph: nx.DiGraph,
    yi: Atom,
    later,
    r_of_var: dict,
    vm: set,
    max_cond: int,
):
    """Smallest Xᵢ ⊆ ``later`` that both validates the factorization
    (Yᵢ ⊥ later\\Xᵢ | Xᵢ) and recovers the factor (Yᵢ ⊥ R_{Wᵢ} | Xᵢ).

    Returns the chosen Xᵢ (sorted) or None if no subset within
    ``max_cond`` works.
    """
    later_list = list(later)
    later_set = set(later_list)
    budget = min(len(later_list), max_cond)
    for size in range(0, budget + 1):
        for xi in combinations(later_list, size):
            xi_set = set(xi)
            rest = later_set - xi_set
            # (a) factorization validity: Yᵢ ⊥ (later \ Xᵢ) | Xᵢ
            if any(not _dsep(m_graph, yi, v, xi) for v in rest):
                continue
            # (b) recoverability: Yᵢ ⊥ R_{Wᵢ} | Xᵢ, Wᵢ = {Yᵢ} ∪ Xᵢ
            w_i = [yi, *xi]
            r_wi = [r_of_var[v] for v in w_i if v in vm]
            if all(_dsep(m_graph, yi, r, xi) for r in r_wi):
                return _sorted_atoms(xi)
    return None


def _find_factorization(
    m_graph: nx.DiGraph,
    y_list,
    x_list,
    r_of_var: dict,
    vm: set,
    max_cond: int,
):
    """Search orderings of Y for a recovering ordered factorization.

    Returns the list of (Yᵢ, Xᵢ) factors, or None if no ordering works.
    """
    for order in permutations(y_list):
        factors: list[tuple[Atom, tuple[Atom, ...]]] = []
        ok = True
        for i, yi in enumerate(order):
            later = list(order[i + 1:]) + list(x_list)
            xi = _pick_xi(m_graph, yi, later, r_of_var, vm, max_cond)
            if xi is None:
                ok = False
                break
            factors.append((yi, xi))
        if ok:
            return factors
    return None


def _factor_repr(yi: Atom, xi, r_of_var: dict, vm: set) -> str:
    w_i = [yi, *xi]
    r_names = ", ".join(
        f"R_{v.predicate}=0" for v in w_i if v in vm
    )
    cond = ", ".join(a.predicate for a in xi)
    inside = yi.predicate
    if cond and r_names:
        return f"P({inside} | {cond}, {r_names})"
    if cond:
        return f"P({inside} | {cond})"
    if r_names:
        return f"P({inside} | {r_names})"
    return f"P({inside})"


def _target_repr(y_list, x_list) -> str:
    y = _names(y_list)
    if x_list:
        return f"P({y} | {_names(x_list)})"
    return f"P({y})"


def recover_query(
    m_graph: nx.DiGraph,
    y_list,
    x_list,
    r_of_var: dict,
    mechanism: str,
    max_cond: int = 4,
) -> MissingDataRecoveryResult:
    """Recoverability of P(Y | X) from an m-graph via ordered factorization.

    ``y_list`` / ``x_list`` are the target and conditioning variable nodes
    (graph atoms). Returns a MissingDataRecoveryResult; a negative verdict
    means "not recoverable via ordered factorization", not a proof of
    non-recoverability.
    """
    vm = set(r_of_var.keys())
    target = _target_repr(y_list, x_list)
    partial = _sorted_atoms(vm)

    if not r_of_var:
        # No missingness declared — the query is trivially "recoverable"
        # (complete data). Callers surface this only when indicators exist.
        return MissingDataRecoveryResult(
            target_repr=target, mechanism="none", recoverable=True,
            factorization=(), formula_repr=target,
            # No shortfall: this row is not a failure. The sentence that
            # used to sit here had no reader — both surfaces read this
            # field only when ``recoverable`` is false — and ``mechanism``
            # already says which row this is.
            partially_observed=(), failure_reason=None,
            search_budget=max_cond, complete_criterion=True,
        )

    factors = _find_factorization(m_graph, y_list, x_list, r_of_var, vm, max_cond)
    if factors is None:
        return MissingDataRecoveryResult(
            target_repr=target, mechanism=mechanism, recoverable=False,
            factorization=(), formula_repr="",
            partially_observed=partial,
            failure_reason=language.state(
                Shortfall.NO_RECOVERABLE_ORDERED_FACTORIZATION),
            search_budget=max_cond,
        )

    factor_strs = [_factor_repr(yi, xi, r_of_var, vm) for yi, xi in factors]
    if len(factor_strs) == 1 and not x_list and len(y_list) == 1:
        formula = f"{target} = {factor_strs[0]}"
    else:
        formula = f"{target} = " + " · ".join(factor_strs)

    return MissingDataRecoveryResult(
        target_repr=target, mechanism=mechanism, recoverable=True,
        factorization=tuple((yi, tuple(xi)) for yi, xi in factors),
        formula_repr=formula,
        partially_observed=partial,
        failure_reason=None,
        search_budget=max_cond,
    )


# ============================================================= orchestrator


def analyze_missing_data(
    base_graph: nx.DiGraph,
    indicators,
    y_list,
    x_list,
    max_cond: int = 4,
) -> MissingDataRecoveryResult:
    """Build the m-graph, classify the mechanism, and decide recoverability
    of P(Y | X). The single entry point the scheduler calls."""
    m_graph, r_of_var = build_m_graph(base_graph, indicators)
    mechanism = classify_missingness(m_graph, r_of_var, list(base_graph.nodes))
    return recover_query(m_graph, y_list, x_list, r_of_var, mechanism, max_cond)


# ================================================= full-estimand combination


@dataclass(frozen=True)
class EstimandRecoveryResult:
    """Recoverability of the full back-door g-formula estimand

        P(Y | do(X)[, C]) = Σ_z P(Y | X, C, Z=z) · P(Z=z | C)

    from missing data. The interventional distribution is a PRODUCT of two
    manifest factors — the adjusted conditional and the covariate marginal —
    so by the factor-by-factor logic of Mohan-Pearl-Tian (2013 §4) it is
    recoverable iff BOTH factors are recoverable. The scheduler already
    recovered the conditional; this adds the marginal P(Z | C) that the
    original slice flagged as the missing piece: a self-masking confounder
    (Z → R_Z) leaves the conditional P(Y|X,Z) recoverable yet makes P(Z)
    — and therefore the whole estimand — unrecoverable.

    ``covariate`` is None when the adjustment set Z is empty (no marginal to
    recover — the estimand collapses to the bare conditional).
    """
    estimand_repr: str
    mechanism: str
    recoverable: bool
    conditional: MissingDataRecoveryResult
    covariate: MissingDataRecoveryResult | None
    adjustment_set: tuple[Atom, ...]
    formula_repr: str
    failure_reason: language.Statement | None = None
    #: The factors this estimand is a product of, each as the role it
    #: plays and the target it stands for. Two hardcoded strings used to
    #: say this, with a literal ``P(Y|X,Z)`` in them rather than the
    #: targets on the rows one field over.
    requires: tuple[language.Statement, ...] = ()


def _estimand_repr(y: Atom, x: Atom, given) -> str:
    given = list(given)
    if given:
        return f"P({y.predicate} | do({x.predicate}), {_names(given)})"
    return f"P({y.predicate} | do({x.predicate}))"


def _rhs(formula_repr: str) -> str:
    """The right-hand side of a ``TARGET = RHS`` recovery formula."""
    return formula_repr.split(" = ", 1)[1] if " = " in formula_repr else formula_repr


def analyze_missing_data_estimand(
    base_graph: nx.DiGraph,
    indicators,
    y: Atom,
    x: Atom,
    given=(),
    z=(),
    max_cond: int = 4,
) -> EstimandRecoveryResult:
    """Recover the full back-door g-formula estimand P(Y | do(X)[, C]) from
    missing data by combining the two manifest factors.

    ``y``/``x`` are single atoms; ``given`` (C) the query conditioning; ``z``
    the already-chosen back-door adjustment set (graph atoms). Builds the
    m-graph once, classifies the mechanism, then recovers via ordered
    factorization (a) the adjusted conditional P(Y | X, C, Z) and (b) the
    covariate marginal P(Z | C). The estimand is recoverable iff both are;
    ``covariate`` is None (and ignored) when Z is empty.
    """
    m_graph, r_of_var = build_m_graph(base_graph, indicators)
    mechanism = classify_missingness(m_graph, r_of_var, list(base_graph.nodes))

    given_list = list(given)
    z_list = list(z)

    conditional = recover_query(
        m_graph, [y], [x, *given_list, *z_list], r_of_var, mechanism, max_cond,
    )
    covariate: MissingDataRecoveryResult | None = None
    if z_list:
        covariate = recover_query(
            m_graph, z_list, given_list, r_of_var, mechanism, max_cond,
        )

    cov_ok = covariate is None or covariate.recoverable
    recoverable = conditional.recoverable and cov_ok
    estimand = _estimand_repr(y, x, given_list)

    if recoverable:
        if covariate is None:
            formula = f"{estimand} = {_rhs(conditional.formula_repr)}"
        else:
            zsub = _names(z_list)
            formula = (
                f"{estimand} = Σ_{{{zsub}}} "
                f"{_rhs(conditional.formula_repr)} · {_rhs(covariate.formula_repr)}"
            )
        failure = None
    else:
        formula = ""
        # Which factors came back empty, as a list in one hole rather than
        # a string this module joined with a separator of its own choosing.
        # The seam between them belongs to whoever is reading.
        blocked = []
        if not conditional.recoverable:
            blocked.append(language.state(
                Shortfall.THE_ADJUSTED_CONDITIONAL,
                target=conditional.target_repr))
        if covariate is not None and not covariate.recoverable:
            blocked.append(language.state(
                Shortfall.THE_COVARIATE_MARGINAL,
                target=covariate.target_repr))
        failure = language.state(
            Shortfall.A_PRODUCT_IS_BLOCKED_BY_ITS_FACTORS,
            factors=tuple(blocked))

    return EstimandRecoveryResult(
        estimand_repr=estimand,
        mechanism=mechanism,
        recoverable=recoverable,
        conditional=conditional,
        covariate=covariate,
        adjustment_set=_sorted_atoms(z_list),
        formula_repr=formula,
        failure_reason=failure,
        requires=(
            (language.state(Factor.ADJUSTED_CONDITIONAL,
                            target=conditional.target_repr),)
            + ((language.state(Factor.COVARIATE_MARGINAL,
                               target=covariate.target_repr),)
               if covariate is not None else ())
        ),
    )
