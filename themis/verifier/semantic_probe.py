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
import numpy as np

from ..types import (
    Atom,
    AtomValue,
    FormulaExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from ..runtime.numeric_estimator import (
    VEIntractable as _VEIntractable,
    Theta,
    _ve_multiply,
    _ve_sum_out,
    enumerate_keys,
    referenced_keys,
    ve_estimate_formula,
)


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
      - ``"unfit"``       — the formula is not a formula about this graph:
        it names something the graph does not have, or refers to a
        variable nothing binds. A REJECTION, and separated from the one
        below because they used to be the same word: a formula naming a
        predicate that does not exist cannot be evaluated, so it arrived
        as "could not probe" — which the caller reads as no opinion, and
        which made renaming one predicate the cheapest way past this.
      - ``"inconclusive"`` — could not probe (state space too large, or
        the formula referenced a quantity the observational distribution
        could not supply). NOT a rejection — the caller falls back to
        structural checks.
    """
    status: str
    detail: str = ""


def _atoms_and_refs(expr, bound=(), atoms=None, unbound=None):
    """Every predicate the formula names, and every reference nothing binds.

    Written over the expression rather than over its JSON, because the JSON
    is one of two spellings of this shape and the question is about the
    formula.
    """
    atoms = set() if atoms is None else atoms
    unbound = set() if unbound is None else unbound
    if isinstance(expr, ProbabilityRefExpr):
        for valued in (expr.target,) + tuple(expr.given):
            atoms.add(valued.atom.predicate)
            value = valued.value
            if isinstance(value, VarRef) and value.name not in bound:
                unbound.add(value.name)
    elif isinstance(expr, ProductExpr):
        for term in expr.terms:
            _atoms_and_refs(term, bound, atoms, unbound)
    elif isinstance(expr, SumExpr):
        atoms.add(expr.over.predicate)
        _atoms_and_refs(expr.body, tuple(bound) + (expr.bind.name,),
                        atoms, unbound)
    elif isinstance(expr, FractionExpr):
        _atoms_and_refs(expr.numerator, bound, atoms, unbound)
        _atoms_and_refs(expr.denominator, bound, atoms, unbound)
    return atoms, unbound


def formula_fits(graph, formula, domains=()) -> ProbeResult | None:
    """Is this a formula about THIS problem? ``None`` when it is.

    Asked before any SCM is sampled, and answered from the formula's own
    text rather than from an exception raised while evaluating it: a
    verifier that read "could not evaluate" as a reason would be reading a
    message, and a message is the evaluator's to change.

    A problem's names come from two places and NEITHER is complete alone.
    An estimation route's graph carries every variable while its theta is
    empty; a probability query's theta carries the variable while its
    graph — built from the cause statements — has no nodes at all, because
    a variable that causes nothing is still a variable. Asking only the
    graph reads "took part in no edge" as "does not exist", which refuses
    an honest answer: the two are one word here for the same reason
    ``inconclusive`` was one word for two verdicts.
    """
    nodes = {node.predicate for node in graph.nodes}
    nodes |= {atom.predicate for atom in (domains or ())}
    named, unbound = _atoms_and_refs(formula)
    stray = sorted(named - nodes)
    if stray:
        return ProbeResult(
            "unfit",
            f"the formula names {stray}, which the problem it claims to "
            f"be about does not declare; its names are {sorted(nodes)}",
        )
    if unbound:
        return ProbeResult(
            "unfit",
            f"the formula refers to {sorted(unbound)}, and nothing in it "
            f"binds those — a sum's variable and the references to it are "
            f"one name, so one of them has been rewritten",
        )
    return None


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


# ============================================ variable elimination
#
# The probe's ground-truth quantity (_true_do) and the observational
# conditionals it needs (_theta_from_scm) are marginals of the sampled
# SCM's discrete factor graph. Brute-force enumeration over all 2^|V|
# joint assignments is exponential AND the site of a flaky native fault at
# |V|≳12 (the per-assignment object churn). Variable elimination computes
# the IDENTICAL marginals in time exponential only in the graph's
# TREEWIDTH — milliseconds for the sparse ADMGs nested-ID produces, with
# no giant enumeration to trip the fault. A factor is
# (vars: tuple, table: {value-tuple: prob}); VE equals enumeration EXACTLY
# (pinned by test). The enumeration forms below stay as the oracle.
#
# The generic factor primitives (_ve_multiply / _ve_sum_out, the VE_MAX_SCOPE
# guard and VEIntractable) live in runtime.numeric_estimator — shared with the
# formula-VE evaluator the plug-in numeric end also uses — and are imported
# above. The SCM-specific pieces (factor construction, min-degree ordering,
# marginals) stay here.


def _scm_factors(scm: _SCM, drop: "Atom | None" = None) -> list:
    """Factors of the SCM joint: one per latent, one per observed node's
    CPT. ``drop`` omits a node's CPT (do-operator severs its mechanism;
    the node survives only as a clamped parent of its children)."""
    factors: list = []
    for name in scm.latents:
        factors.append(((name,), {(v,): p for v, p in scm.latent_dist[name].items()}))
    for node in scm.observed:
        if node == drop:
            continue
        vars_ = scm.parents[node] + (node,)
        table: dict = {}
        for pv, dist in scm.cpt[node].items():
            for v, p in dist.items():
                table[pv + (v,)] = p
        factors.append((vars_, table))
    return factors


def _ve_restrict(factor, evidence):
    """Clamp a factor's evidence variables to their given values, dropping
    them from the scope."""
    vars_, table = factor
    if not any(v in evidence for v in vars_):
        return factor
    keep_i = [i for i, v in enumerate(vars_) if v not in evidence]
    keep_vars = tuple(vars_[i] for i in keep_i)
    ev_i = [(i, evidence[v]) for i, v in enumerate(vars_) if v in evidence]
    new: dict = {}
    for vals, p in table.items():
        if all(vals[i] == ev for i, ev in ev_i):
            key = tuple(vals[i] for i in keep_i)
            new[key] = new.get(key, 0.0) + p
    return (keep_vars, new)


def _ve_degree(factors, v) -> int:
    neigh: set = set()
    for vars_, _ in factors:
        if v in vars_:
            neigh.update(vars_)
    return len(neigh)


def _ve_eliminate(factors, v):
    containing = [f for f in factors if v in f[0]]
    rest = [f for f in factors if v not in f[0]]
    prod = containing[0]
    for f in containing[1:]:
        prod = _ve_multiply(prod, f)
    return rest + [_ve_sum_out(prod, v)]


def _ve_prob(factors, evidence) -> float:
    """P(evidence) under the factor product, via variable elimination
    (min-degree order): Σ over non-evidence vars of ∏ factors, evidence
    clamped."""
    fs = [_ve_restrict(f, evidence) for f in factors]
    while True:
        allv = set().union(*[set(f[0]) for f in fs]) if fs else set()
        if not allv:
            break
        v = min(allv, key=lambda v: _ve_degree(fs, v))
        fs = _ve_eliminate(fs, v)
    p = 1.0
    for _, table in fs:
        p *= table.get((), 0.0)
    return p


def _ve_marginal(factors, keep):
    """Joint marginal factor over ``keep`` (every other variable summed
    out); its table is the distribution P(keep) and sums to 1."""
    keepset = set(keep)
    fs = list(factors)
    while True:
        elim = (set().union(*[set(f[0]) for f in fs]) if fs else set()) - keepset
        if not elim:
            break
        v = min(elim, key=lambda v: _ve_degree(fs, v))
        fs = _ve_eliminate(fs, v)
    prod = ((), {(): 1.0})
    for f in fs:
        prod = _ve_multiply(prod, f)
    return prod


# ============================================ true quantities
#
# Enumeration forms — the readable definitions and the VE equivalence
# oracle. Production paths (_true_do, _theta_from_scm) use variable
# elimination above; their equality to these is pinned by test.


def _observational_cond(scm: _SCM, target: Atom, tv, given: dict[Atom, object]) -> float:
    """P(target=tv | given) under the SCM's observational distribution.

    Reference (per-key) form. ``_theta_from_scm`` computes the identical
    number for every key it needs in a single grouped pass; this stays as
    the readable definition and the equivalence oracle its test pins."""
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


def _true_do_enum(scm: _SCM, x: Atom, xv, y: Atom, yv, given: dict[Atom, object]) -> float:
    """True P(Y=yv | do(X=xv), given) by direct structural intervention,
    computed by brute-force enumeration. Reference oracle for ``_true_do``."""
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


def _true_do(scm: _SCM, x: Atom, xv, y: Atom, yv, given: dict[Atom, object]) -> float:
    """True P(Y=yv | do(X=xv), given), via variable elimination on the
    do-mutilated factor graph (X's CPT dropped, X clamped to xv). Equals
    ``_true_do_enum`` exactly (pinned by test) but costs ~2^treewidth, not
    2^|V|, and never enumerates — so it neither hangs nor trips the native
    fault on larger graphs. May raise ``_VEIntractable`` (→ inconclusive)
    on a high-treewidth graph."""
    factors = _scm_factors(scm, drop=x)
    den = _ve_prob(factors, {x: xv, **given})
    if den <= 0:
        return 0.0
    num = _ve_prob(factors, {x: xv, y: yv, **given})
    return num / den


# ============================================ formula evaluation


def _bind_holes(formula: FormulaExpr,
                bindings: dict[Atom, AtomValue]) -> FormulaExpr:
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


def _atom_sort_key(atom: Atom) -> tuple:
    """Deterministic ordering of atoms for building contingency-table keys."""
    return (atom.predicate, tuple(t.name for t in atom.args))


def _theta_from_scm(
    scm: _SCM, bound_formula: FormulaExpr,
    graph: nx.DiGraph, bidirected: frozenset,
) -> Theta:
    """Fill a Theta with exactly the conditionals ``bound_formula``
    references, computed from the SCM's observational distribution.

    The formula references 2^#sums keys but only |V|-order DISTINCT
    (target atom, conditioning atom-SET) groups (one per probability factor;
    the conditioning set of each is bounded). Collect the distinct referenced
    keys by a LINEAR per-factor walk (runtime :func:`referenced_keys` — never
    the 2^#sums :func:`enumerate_keys` list, which is itself exponential and a
    native-fault site), group them by (target atom, conditioning atom-SET), and
    answer each group from ONE variable-elimination marginal P(target,
    given-atoms): cost ~2^treewidth per group, never a 2^|V| enumeration. Every
    entry is the exact observational conditional (a key's value depends only on
    its target/given atoms and their values, not the population tag). The key
    set equals :func:`enumerate_keys`'s distinct output and each value equals
    :func:`_observational_cond` (both pinned by test); may raise
    ``_VEIntractable`` (→ inconclusive) on a high-treewidth graph."""
    th = Theta()
    keys = referenced_keys(bound_formula, scm.domains)

    # Group keys by (target atom, population, conditioning atom-SET). Keys in a
    # group differ only by the conditioning/target VALUES, all answered from
    # one shared marginal.
    members: dict = {}
    atom_order: dict = {}
    for key in keys:
        gid = (key.target_atom, key.population,
               frozenset(a for a, _ in key.given))
        if gid not in members:
            members[gid] = []
            atom_order[gid] = tuple(sorted(gid[2], key=_atom_sort_key))
        members[gid].append(key)

    factors = _scm_factors(scm)
    for gid, klist in members.items():
        target_atom = gid[0]
        atoms = atom_order[gid]
        m_vars, m_table = _ve_marginal(factors, (target_atom,) + atoms)
        ti = m_vars.index(target_atom)
        gi = [m_vars.index(a) for a in atoms]
        # cond[given-values][target-value] = P(target, given) mass
        cond: dict = {}
        for row, p in m_table.items():
            slot = cond.setdefault(tuple(row[j] for j in gi), {})
            tvv = row[ti]
            slot[tvv] = slot.get(tvv, 0.0) + p
        for key in klist:
            gmap = dict(key.given)
            cell = cond.get(tuple(gmap[a] for a in atoms))
            if not cell:
                th.entries[key] = 0.0
                continue
            den = sum(cell.values())
            th.entries[key] = (
                cell.get(key.target_value, 0.0) / den if den > 0 else 0.0
            )
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

    # Whether this is a formula ABOUT this graph is asked first, and
    # answered from the formula rather than from a failure to evaluate it.
    unfit = formula_fits(graph, formula, domains)
    if unfit is not None:
        return unfit

    # Probe needs a fully-instantiated ADMG over the formula's variables.
    if x not in graph or y not in graph:
        return ProbeResult("inconclusive", "x or y absent from graph")
    if any(g not in graph for g in given):
        return ProbeResult("inconclusive", "a conditioned Z is absent from graph")

    for i in range(k):
        rng = random.Random(seed + i)
        scm = _sample_scm(graph, bidirected, domains, rng)

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
                    got = ve_estimate_formula(bound, theta)
                    true = _true_do(scm, x, x_value, y, yv, given_map)
                except _VEIntractable:
                    return ProbeResult(
                        "inconclusive",
                        "variable elimination exceeded the probe cap (high treewidth)",
                    )
                except Exception as exc:  # noqa: BLE001 — probe is best-effort
                    return ProbeResult(
                        "inconclusive",
                        f"formula could not be evaluated against the probe SCM: {exc}",
                    )
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


# ============================================ counterfactual (ID*) backbone


# ---------------------------------------- vectorized counterfactual MC
#
# The true P(γ) / P(γ|δ) of a counterfactual conjunction is estimated by
# Monte-Carlo: unlike the formula-evaluation path there is NO exact factor
# reduction to fall back on — the exact counterfactual is a sum over a per-node
# RESPONSE FUNCTION whose state space is ∏ exponential (Fig-1 alone is ~2^19),
# so the truth stays Monte-Carlo. The earlier per-draw Python loop churned
# millions of small dict/tuple objects at 50k-120k replicates, and under a deep
# native callstack that was a flaky Windows heap-corruption / access-violation
# site (an innocent dict assignment raising a nonsense "tuple has no context
# manager" TypeError, or an outright segfault). This vectorized form removes
# the churn — draw all ``n`` replicates AT ONCE as integer arrays and propagate
# each world with a handful of numpy ops. Standard twin-network semantics: one
# exogenous background shared across worlds; a node's per-parent-combo response
# shared across worlds, independent across combos. Its equality to an EXACT
# enumeration of the whole exogenous space (the readable ground truth) is
# pinned by tests/test_counterfactual_mc_vectorized.py.

# A pathologically high-in-degree node would pre-draw a huge response table;
# decline (→ probe inconclusive) rather than allocate unboundedly.
_MC_MAX_COMBOS = 1 << 16


def _sample_categorical(pvec: np.ndarray, n: int, rng) -> np.ndarray:
    """``n`` i.i.d. draws from a categorical given as probability vector
    ``pvec`` (ordered by value index); returns an int8 array of value indices,
    by inverse-CDF via ``searchsorted``."""
    cum = np.cumsum(pvec)
    cum[-1] = 1.0                      # guard against fp drift below 1.0
    u = rng.random(n)
    return np.searchsorted(cum, u, side="right").astype(np.int8)


def _mc_world_values(scm: _SCM, worlds, topo, n: int, rng):
    """Sample ``n`` replicates of every ``(world, node)`` value as an int8
    array of value indices, by a fully vectorized forward pass.

    Shares one exogenous background across worlds (latents drawn once per
    replicate) and shares each node's per-parent-combo response across worlds
    while keeping different combos independent — the standard counterfactual
    twin-network semantics, with no per-draw allocation. Returns
    ``(world_values, value_to_index)`` where ``world_values[world][atom]`` is
    the length-``n`` index array and ``value_to_index[atom]`` maps a domain
    value to its index."""
    lat_dom = scm.latent_domain

    # exogenous background: one index array per latent, shared across worlds.
    U: dict = {}
    for name in scm.latents:
        pvec = np.array([scm.latent_dist[name][v] for v in lat_dom], dtype=np.float64)
        U[name] = _sample_categorical(pvec, n, rng)

    arange_n = np.arange(n)
    v2i: dict = {}
    radix: dict = {}          # node -> per-parent mixed-radix multiplier
    resp: dict = {}           # node -> (n_combos, n) int8 response table

    for node in topo:
        node_dom = scm.domains.get(node, _DEFAULT_DOMAIN)
        v2i[node] = {v: i for i, v in enumerate(node_dom)}
        pars = scm.parents[node]
        par_doms = [
            lat_dom if isinstance(p, str) else scm.domains.get(p, _DEFAULT_DOMAIN)
            for p in pars
        ]
        sizes = [len(d) for d in par_doms]
        # mixed-radix multipliers matching itertools.product order (first
        # parent most significant) — the order _sample_scm built cpt keys in.
        mult = [1] * len(sizes)
        acc = 1
        for k in range(len(sizes) - 1, -1, -1):
            mult[k] = acc
            acc *= sizes[k]
        radix[node] = mult
        n_combos = acc
        if n_combos > _MC_MAX_COMBOS:
            raise ValueError(
                f"node {node.predicate} has {n_combos} parent combinations — "
                "beyond the vectorized MC response-table cap"
            )
        stack = np.empty((n_combos, n), dtype=np.int8)
        combos = itertools.product(*par_doms) if par_doms else [()]
        for ci, combo in enumerate(combos):
            dist = scm.cpt[node][combo]
            pvec = np.array([dist[v] for v in node_dom], dtype=np.float64)
            stack[ci] = _sample_categorical(pvec, n, rng)
        resp[node] = stack

    world_values: dict = {}
    for world in worlds:
        wd = dict(world)
        vals: dict = {}
        for node in topo:
            if node in wd:                          # intervened in this world
                vals[node] = np.full(n, v2i[node][wd[node]], dtype=np.int8)
                continue
            pars = scm.parents[node]
            combo_idx = np.zeros(n, dtype=np.int64)
            for k, p in enumerate(pars):
                pidx = U[p] if isinstance(p, str) else vals[p]
                combo_idx += pidx.astype(np.int64) * radix[node][k]
            vals[node] = resp[node][combo_idx, arange_n]
        world_values[world] = vals
    return world_values, v2i


def _counterfactual_true_mc(
    scm: _SCM, gamma, topo, n_draws: int, rng,
) -> float:
    """Vectorized true ``P(γ)`` for a counterfactual conjunction ``gamma``.
    ``rng`` is a numpy ``Generator``. ``gamma`` is a tuple of objects with
    ``.variable`` (Atom), ``.subscript`` (frozenset of ``(Atom, value)``
    interventions = the world) and ``.value``."""
    worlds = {e.subscript for e in gamma}
    wv, v2i = _mc_world_values(scm, worlds, topo, n_draws, rng)
    mask = np.ones(n_draws, dtype=bool)
    for e in gamma:
        mask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    return float(np.count_nonzero(mask)) / n_draws


def _conditional_true_mc(
    scm: _SCM, gamma, delta, topo, n_draws: int, rng,
) -> tuple[float, int]:
    """Vectorized true ``P(γ | δ) = P(γ∧δ)/P(δ)``. Numerator and denominator
    share one background draw (parallel worlds), so the ratio is a genuine
    counterfactual conditional. Returns ``(estimate, denominator_count)``."""
    worlds = {e.subscript for e in (*gamma, *delta)}
    wv, v2i = _mc_world_values(scm, worlds, topo, n_draws, rng)
    dmask = np.ones(n_draws, dtype=bool)
    for e in delta:
        dmask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    nmask = dmask.copy()
    for e in gamma:
        nmask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    den = int(np.count_nonzero(dmask))
    return (float(np.count_nonzero(nmask)) / den if den else 0.0), den


def probe_counterfactual_formula(
    graph: nx.DiGraph,
    bidirected: frozenset,
    *,
    gamma,
    formula: FormulaExpr,
    domains: dict[Atom, tuple] | None = None,
    k: int = 2,
    n_draws: int = 50000,
    tol: float = 0.03,
    seed: int = 0x5CA1AB1E,
) -> ProbeResult:
    """Semantic backbone for ID*: does ``formula`` compute the true
    ``P(γ)`` in models consistent with the graph?

    Unlike :func:`probe_identify_formula` (exact enumeration, tol 1e-7),
    this is **Monte-Carlo**: an exact counterfactual evaluation requires
    enumerating a response function per node — exponential, and the Fig-1
    worked example alone is ~2^19 > the exact-enumeration cap. So the true
    ``P(γ)`` is estimated by sampling the shared exogenous background. The
    seed is fixed (reproducible) and the tolerance is generous — the MC
    standard error ≈ 1/(2√n_draws) ≈ 0.002 is far below ``tol`` — so a
    correct formula never trips and a wrong formula (typically off by
    ≥ 0.05) is caught. ``k`` independent SCMs make a false accept unlikely.

    Returns ``match`` / ``mismatch`` / ``inconclusive`` (parallel to
    ``probe_identify_formula``); ``inconclusive`` is NOT a rejection.
    """
    domains = dict(domains or {})

    atoms = {
        a
        for e in gamma
        for a in (e.variable, *(at for (at, _v) in e.subscript))
    }
    if any(a not in graph for a in atoms):
        return ProbeResult("inconclusive", "a γ atom is absent from the graph")

    # Forward-evaluation order for the (non-recursive) MC truth — parents
    # before children, over the observed nodes.
    topo = list(nx.topological_sort(graph))

    for i in range(k):
        rng = random.Random(seed + i)
        scm = _sample_scm(graph, bidirected, domains, rng)
        try:
            theta = _theta_from_scm(scm, formula, graph, bidirected)
            got = ve_estimate_formula(formula, theta)
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            return ProbeResult(
                "inconclusive",
                f"formula could not be evaluated against the probe SCM: {exc}",
            )
        mc_rng = np.random.default_rng(seed + 7919 + i)
        try:
            true = _counterfactual_true_mc(scm, gamma, topo, n_draws, mc_rng)
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            return ProbeResult(
                "inconclusive",
                f"counterfactual Monte-Carlo could not run: {exc}",
            )
        if abs(got - true) > tol:
            return ProbeResult(
                "mismatch",
                f"SCM #{i}: formula gives {got:.4f} for P(γ) but the "
                f"counterfactual Monte-Carlo truth is {true:.4f}",
            )

    return ProbeResult("match")


# ============================================ conditional (IDC*) backbone


def probe_conditional_counterfactual_formula(
    graph: nx.DiGraph,
    bidirected: frozenset,
    *,
    gamma,
    delta,
    formula: FormulaExpr,
    domains: dict[Atom, tuple] | None = None,
    k: int = 2,
    n_draws: int = 80000,
    tol: float = 0.04,
    min_den: int = 1000,
    seed: int = 0x5CA1AB1E,
) -> ProbeResult:
    """Semantic backbone for IDC*: does ``formula`` compute the true
    ``P(γ | δ)`` in models consistent with the graph?

    The conditional counterpart of :func:`probe_counterfactual_formula`.
    The truth is a ratio of two counterfactual Monte-Carlo counts sharing
    one background draw, so its variance is higher than the unconditional
    probe's — hence a larger ``n_draws`` and ``tol``, and a ``min_den``
    guard that declines (``inconclusive``, not a rejection) when the
    conditioning event ``δ`` is too rare in a sampled SCM to estimate the
    ratio reliably. Never calls the identification code.
    """
    domains = dict(domains or {})

    atoms = {
        a
        for e in (*gamma, *delta)
        for a in (e.variable, *(at for (at, _v) in e.subscript))
    }
    if any(a not in graph for a in atoms):
        return ProbeResult("inconclusive", "a γ/δ atom is absent from the graph")

    topo = list(nx.topological_sort(graph))

    for i in range(k):
        rng = random.Random(seed + i)
        scm = _sample_scm(graph, bidirected, domains, rng)
        try:
            theta = _theta_from_scm(scm, formula, graph, bidirected)
            got = ve_estimate_formula(formula, theta)
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            return ProbeResult(
                "inconclusive",
                f"formula could not be evaluated against the probe SCM: {exc}",
            )
        mc_rng = np.random.default_rng(seed + 7919 + i)
        try:
            true, den = _conditional_true_mc(scm, gamma, delta, topo, n_draws, mc_rng)
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            return ProbeResult(
                "inconclusive",
                f"counterfactual Monte-Carlo could not run: {exc}",
            )
        if den < min_den:
            return ProbeResult(
                "inconclusive",
                f"SCM #{i}: conditioning event too rare "
                f"({den}/{n_draws}) to estimate the ratio",
            )
        if abs(got - true) > tol:
            return ProbeResult(
                "mismatch",
                f"SCM #{i}: formula gives {got:.4f} for P(γ|δ) but the "
                f"counterfactual Monte-Carlo truth is {true:.4f}",
            )

    return ProbeResult("match")
