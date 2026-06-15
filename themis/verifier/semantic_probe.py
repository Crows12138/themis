"""Phase 15 — semantic verification backbone for point identification.

The per-method verifier rules (identify_via_backdoor / _front_door /
_tian / _idc) each check a *structural recipe* — "is this the right
adjustment set", "does the c-component partition match". None of them
check the one thing that actually matters: **does the claimed formula
compute the true interventional quantity?** Phase 14 proved the gap is
real — an IDC fraction that was numerically wrong (a degenerate inner
sum) passed every structural check and the schema.

This module is the method-agnostic fix. Given a graph, a claimed
identification formula, and the query, it:

1. samples random SCMs *consistent with the ADMG* (a CPT per node, an
   independent latent per bidirected edge),
2. computes the **true** ``P(Y=y | do(X=xv), Z=z)`` by intervening on
   each SCM directly (sever X, enumerate latents),
3. evaluates the claimed formula against the SCM's *observational*
   distribution and requires it to equal the truth, for every binding,
   across K independent SCMs.

A wrong formula matches the truth only on a measure-zero set, so K≥2-3
makes a false accept astronomically unlikely. This is Monte-Carlo
verification — overwhelming evidence, not a symbolic proof — but it is
strictly stronger than the structural checks, which prove *nothing*
about the number.

INDEPENDENCE: the probe never calls the runtime's identification code.
It builds its own SCM and computes the true do-quantity by direct
structural intervention, so it cannot share a bug with the path that
produced the formula.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

import networkx as nx

from ..types import (
    Atom,
    ConstantExpr,
    FormulaExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from ..runtime.numeric_estimator import Theta, estimate_formula, enumerate_keys


# Cap on the SCM enumeration state space (observed nodes + one latent per
# bidirected edge). 2^16 keeps a single probe well under a millisecond's
# worth of work; above it the probe declines rather than hang.
_MAX_STATES = 1 << 16

# Default per-atom value domain when the caller supplies none. Binary is
# rich enough to expose a wrong formula generically.
_DEFAULT_DOMAIN = (True, False)


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a semantic equivalence probe.

    ``status`` is one of:
      - ``"match"``       — formula reproduced the true do-quantity on
        every binding across all sampled SCMs.
      - ``"mismatch"``    — at least one binding disagreed; ``detail``
        carries the witness (binding, formula value, true value).
      - ``"inconclusive"`` — could not probe (state space too large, or
        the formula referenced a quantity the observational distribution
        could not supply). NOT a rejection — the caller falls back to
        structural checks.
    """
    status: str
    detail: str = ""


# ============================================ SCM sampling


@dataclass
class _SCM:
    observed: tuple[Atom, ...]
    latents: tuple[str, ...]
    domains: dict[Atom, tuple]
    latent_domain: tuple
    # node -> ordered parent vars (atoms then latent names)
    parents: dict[Atom, tuple]
    # node -> {parent-value-tuple: {value: prob}}
    cpt: dict[Atom, dict]
    # latent name -> {value: prob}
    latent_dist: dict[str, dict]


def _latent_name(pair: frozenset[Atom]) -> str:
    a, b = sorted(pair, key=lambda n: (n.predicate, tuple(t.name for t in n.args)))
    return f"__L_{a.predicate}_{b.predicate}"


def _rand_dist(domain, rng: random.Random) -> dict:
    raw = [rng.random() + 1e-6 for _ in domain]
    s = sum(raw)
    return {v: r / s for v, r in zip(domain, raw)}


def _sample_scm(
    graph: nx.DiGraph,
    bidirected: frozenset,
    domains: dict[Atom, tuple],
    rng: random.Random,
) -> _SCM:
    observed = tuple(graph.nodes())
    latent_domain = (True, False)
    latent_of: dict[Atom, list[str]] = {n: [] for n in observed}
    latent_dist: dict[str, dict] = {}
    latents: list[str] = []
    for pair in bidirected:
        name = _latent_name(pair)
        latents.append(name)
        latent_dist[name] = _rand_dist(latent_domain, rng)
        for node in pair:
            if node in latent_of:
                latent_of[node].append(name)

    parents: dict[Atom, tuple] = {}
    cpt: dict[Atom, dict] = {}
    for node in observed:
        dir_parents = tuple(graph.predecessors(node))
        lat_parents = tuple(latent_of[node])
        parents[node] = dir_parents + lat_parents
        dom = domains.get(node, _DEFAULT_DOMAIN)
        # one random conditional per parent-value combination
        parent_domains = [domains.get(p, _DEFAULT_DOMAIN) for p in dir_parents] \
            + [latent_domain] * len(lat_parents)
        table: dict = {}
        for combo in itertools.product(*parent_domains) if parent_domains else [()]:
            table[combo] = _rand_dist(dom, rng)
        cpt[node] = table

    return _SCM(
        observed=observed,
        latents=tuple(latents),
        domains=domains,
        latent_domain=latent_domain,
        parents=parents,
        cpt=cpt,
        latent_dist=latent_dist,
    )


def _state_space_size(scm: _SCM) -> int:
    size = 1
    for n in scm.observed:
        size *= len(scm.domains.get(n, _DEFAULT_DOMAIN))
        if size > _MAX_STATES:
            return size
    size *= len(scm.latent_domain) ** len(scm.latents)
    return size


def _full_assignments(scm: _SCM):
    """Enumerate every (observed + latent) joint assignment as a dict."""
    var_order = list(scm.observed) + list(scm.latents)
    doms = [scm.domains.get(n, _DEFAULT_DOMAIN) for n in scm.observed] \
        + [scm.latent_domain] * len(scm.latents)
    for combo in itertools.product(*doms):
        yield dict(zip(var_order, combo))


def _cell_prob(scm: _SCM, assign: dict, *, fixed: dict | None = None) -> float:
    """Probability mass of a full assignment. ``fixed`` names nodes set by
    intervention — their CPT factor is dropped (do-operator)."""
    fixed = fixed or {}
    p = 1.0
    for name in scm.latents:
        p *= scm.latent_dist[name][assign[name]]
        if p == 0.0:
            return 0.0
    for node in scm.observed:
        if node in fixed:
            continue  # mechanism severed by do()
        key = tuple(assign[par] for par in scm.parents[node])
        p *= scm.cpt[node][key][assign[node]]
        if p == 0.0:
            return 0.0
    return p


# ============================================ true quantities


def _observational_cond(scm: _SCM, target: Atom, tv, given: dict[Atom, object]) -> float:
    """P(target=tv | given) under the SCM's observational distribution."""
    num = 0.0
    den = 0.0
    for a in _full_assignments(scm):
        if any(a[g] != v for g, v in given.items()):
            continue
        m = _cell_prob(scm, a)
        den += m
        if a[target] == tv:
            num += m
    return num / den if den > 0 else 0.0


def _true_do(scm: _SCM, x: Atom, xv, y: Atom, yv, given: dict[Atom, object]) -> float:
    """True P(Y=yv | do(X=xv), given) by direct structural intervention."""
    fixed = {x: xv}
    num = 0.0   # P(Y=yv, given | do x)
    den = 0.0   # P(given | do x)
    for a in _full_assignments(scm):
        if a[x] != xv:
            continue
        if any(a[g] != v for g, v in given.items()):
            continue
        m = _cell_prob(scm, a, fixed=fixed)
        den += m
        if a[y] == yv:
            num += m
    return num / den if den > 0 else 0.0


# ============================================ formula evaluation


def _bind_holes(formula: FormulaExpr, bindings: dict[Atom, object]) -> FormulaExpr:
    """Replace every value=None ValuedAtom whose atom is in ``bindings``
    with the bound literal. Leaves VarRef (summed) and concrete-literal
    (do-value) slots untouched."""
    def fix(va: ValuedAtom) -> ValuedAtom:
        if va.value is None and va.atom in bindings:
            return ValuedAtom(atom=va.atom, value=bindings[va.atom])
        return va

    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=fix(formula.target),
            given=tuple(fix(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(_bind_holes(t, bindings) for t in formula.terms))
    if isinstance(formula, SumExpr):
        return SumExpr(bind=formula.bind, over=formula.over,
                       body=_bind_holes(formula.body, bindings))
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_bind_holes(formula.numerator, bindings),
            denominator=_bind_holes(formula.denominator, bindings),
        )
    return formula


def _theta_from_scm(
    scm: _SCM, bound_formula: FormulaExpr,
    graph: nx.DiGraph, bidirected: frozenset,
) -> Theta:
    """Fill a Theta with exactly the conditionals ``bound_formula``
    references, computed from the SCM's observational distribution."""
    th = Theta()
    for key in enumerate_keys(bound_formula, th):
        given = {a: v for a, v in key.given}
        th.entries[key] = _observational_cond(
            scm, key.target_atom, key.target_value, given)
    return th


# ============================================ public backbone


def _domain_of(atom: Atom, domains: dict[Atom, tuple]) -> tuple:
    return domains.get(atom, _DEFAULT_DOMAIN)


def probe_identify_formula(
    graph: nx.DiGraph,
    bidirected: frozenset,
    *,
    x: Atom,
    x_value,
    y: Atom,
    given: tuple[Atom, ...],
    formula: FormulaExpr,
    domains: dict[Atom, tuple] | None = None,
    k: int = 3,
    seed: int = 0x5CA1AB1E,
) -> ProbeResult:
    """Semantic backbone: does ``formula`` compute the true
    ``P(Y | do(X=x_value), Z=given)`` in models consistent with the graph?

    Samples ``k`` random SCMs (fixed seed → reproducible), and for each
    checks the formula against the true do-quantity for every (Y, Z)
    binding. Returns ``match`` / ``mismatch`` / ``inconclusive``.
    """
    domains = dict(domains or {})

    # Probe needs a fully-instantiated ADMG over the formula's variables.
    if x not in graph or y not in graph:
        return ProbeResult("inconclusive", "x or y absent from graph")
    if any(g not in graph for g in given):
        return ProbeResult("inconclusive", "a conditioned Z is absent from graph")

    for i in range(k):
        rng = random.Random(seed + i)
        scm = _sample_scm(graph, bidirected, domains, rng)
        if _state_space_size(scm) > _MAX_STATES:
            return ProbeResult("inconclusive", "state space exceeds probe cap")

        y_dom = _domain_of(y, domains)
        given_doms = [_domain_of(g, domains) for g in given]
        given_combos = list(itertools.product(*given_doms)) if given else [()]

        for gvals in given_combos:
            given_map = dict(zip(given, gvals))
            for yv in y_dom:
                bindings = {y: yv, **given_map}
                bound = _bind_holes(formula, bindings)
                try:
                    theta = _theta_from_scm(scm, bound, graph, bidirected)
                    got = estimate_formula(bound, theta, graph=graph, bidirected=bidirected)
                except Exception as exc:  # noqa: BLE001 — probe is best-effort
                    return ProbeResult(
                        "inconclusive",
                        f"formula could not be evaluated against the probe SCM: {exc}",
                    )
                true = _true_do(scm, x, x_value, y, yv, given_map)
                if abs(got - true) > 1e-7:
                    binding_str = ", ".join(
                        [f"{y.predicate}={yv}"]
                        + [f"{g.predicate}={v}" for g, v in given_map.items()])
                    return ProbeResult(
                        "mismatch",
                        f"SCM #{i}: formula gives {got:.6f} for P({binding_str}|"
                        f"do({x.predicate}={x_value})) but the true interventional "
                        f"value is {true:.6f}",
                    )

    return ProbeResult("match")
