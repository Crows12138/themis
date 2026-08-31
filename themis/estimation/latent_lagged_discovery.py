"""Learning the lagged graph WITHOUT assuming every common cause was recorded.

:mod:`themis.estimation.lagged_discovery` learns lagged links under causal
sufficiency — no unobserved confounder of two recorded series. That
assumption is declared there and is not free. Measured, 4000 steps, α=0.01:
a latent AR(1) ``L`` with ``x`` measuring ``L`` at t and ``y`` driven by
``L`` at t−1, and no link of any kind between ``x`` and ``y`` — PCMCI
returns ``x@t-1 → y`` at p = 0 and ``x@t-2 → y`` at p = 1.3e-15. Two
confident lagged causes, both fabricated by the one thing the reader was
not shown. This module is the same question asked without that assumption.

Reference: Malinsky & Spirtes 2018, "Causal Structure Learning from
Multivariate Time Series in Settings with Unmeasured Confounding"
(*Proceedings of the 2018 ACM SIGKDD Workshop on Causal Discovery*), which
is FCI (Spirtes, Meek & Richardson 1995) run on the time-lagged design with
the time order as background knowledge; and Zhang 2008, "On the completeness
of orientation rules for causal discovery in the presence of latent
confounders and selection bias", for the rules. Written from the papers.
``tigramite`` — which implements LPCMCI, the recall-oriented member of this
family — is GPL and was neither read nor vendored, and no permissively
licensed implementation of any of them exists: ``causal-learn``, which this
package already uses for the cross-sectional algorithms, has no time-series
FCI at all.

What the relaxation costs and what it buys
------------------------------------------
It buys the distinction between "X causes Y" and "X and Y share something
you did not record", which under causal sufficiency cannot be drawn because
the second is assumed away. It costs the right to condition on everything
available: with a latent confounder in the picture, conditioning on a
COLLIDER creates dependence where there was none, so a separating set has
to be SEARCHED for among subsets rather than taken to be the whole parent
set. That single change is why this is a different module and not a flag.

What comes out
--------------
A partially oriented graph over the lagged design. Time order settles more
of it than it would in a cross-sectional PAG: no later variable is an
ancestor of an earlier one, so **every edge already carries an arrowhead at
its later endpoint**, and the only open question per edge is the mark at the
EARLIER one:

- ``tail`` — ``X@t-τ → Y@t``: X is a cause of Y.
- ``arrow`` — ``X@t-τ ↔ Y@t``: they share an unrecorded cause, and X is not
  a cause of Y.
- ``circle`` — ``X@t-τ o→ Y@t``: one of the two, and this data cannot say
  which. Not a defect in the answer; it is the answer.

There is no ``o-o`` edge and no edge pointing backwards in time, both for
the same reason, and the notation is smaller than a general PAG's because of
it.

How an orientation is justified
-------------------------------
Every mark other than ``circle`` is set by a rule on ONE triple, and the
triple is recorded beside it, so a reader checks an orientation by looking at
three edges rather than by re-running a search. Three rules, and the first
two are the same triple read two ways —  ``W@t-τw``, ``X@t-τx``, ``Y@t`` with
τw > τx ≥ 1, W adjacent to X, X adjacent to Y, and W NOT adjacent to Y:

- **collider** (Spirtes' R0): X is not in the set that separated W from Y.
  Conditioning on X would then have opened the path, so X is a collider —
  which puts an arrowhead at X, and X's edge to Y is ``↔``.
- **non-collider** (Zhang's R1): X IS in that set. Then X cannot be a
  collider, and since the W–X edge already points into X, the X end of X–Y
  must be a tail: ``X → Y``.
- **ancestry** (Zhang's R8): ``A → B``, ``B → C`` and ``A o→ C`` make A an
  ancestor of C, so that circle is a tail too.

Zhang's R2–R4 and R9–R10 are NOT applied. R2's conclusion is an arrowhead at
the LATER endpoint of an edge, which the time order has already written down,
so it can add nothing here. R3, R4, R9 and R10 can add orientations and are
not built: each rests on a path rather than on a triple, so its witness is a
search result rather than three edges a reader can look at. The output is
therefore SOUND — every mark it writes is correct — without being maximally
informative: some circle here would be a tail or an arrowhead under the
complete rule set. Stated rather than absorbed, because "we could not tell"
and "we did not look" read identically to a reader and are not the same
claim.

Scope (declared), inherited from the module this relaxes
--------------------------------------------------------
- **Lagged links only.** A contemporaneous link ``X^i_t → X^j_t`` is neither
  sought nor represented. This is also what makes every edge time-ordered
  and therefore what the orientation above rests on.
- **Causal stationarity** — the lagged structure does not change over t. It
  is what lets one test per ``(driver, lag, target)`` stand for the whole
  unrolled window, and it is spent again when a triple is read at one shift
  and its conclusion applied at every other.
- **Linear-Gaussian**, because the test is Fisher-Z partial correlation, and
  because that is what makes the correlation matrix a COMPLETE sufficient
  statistic — every test either stage ran is re-derivable from the artifact
  by a second pass that never sees the data.
- **Integer time steps**, lags taken by value within a unit.

The recall question, and why it is a separate one
-------------------------------------------------
LPCMCI (Gerhardus & Runge 2020) targets the same graph with the same
soundness guarantee and recovers more of it under strong autocorrelation, by
refining ancestor sets across iterations instead of testing each pair once.
It is a POWER improvement, not a correctness one, and it is not built here.
The choice between them is not "how correct is the answer" but "how much of
the answer is left as a circle", which is the axis this package already ranks
second: a circle says the data did not settle it, and the failure this module
exists to remove is a fabricated arrow.

API::

    from themis.estimation.latent_lagged_discovery import (
        discover_latent_lagged_graph, latent_lagged_discovery_to_dict,
    )
    result = discover_latent_lagged_graph(frame, time="t", max_lag=2)
    themis.verify_latent_lagged_discovery(
        latent_lagged_discovery_to_dict(result))
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import validate_data
from .discovery import (
    _classify_column,
    _corr_matrix,
    _fisher_z_pvalue,
    _grow_shrink_mb,
    _partial_corr,
    MarkovBlanketError,
)
from .discovery_words import Confounded
from .lagged_discovery import (
    LaggedDiscoveryError,
    _aligned_rows,
    _as_link,
    design_columns,
    design_index,
    _MAX_DESIGN_WIDTH,
)
from .refusal_words import Refuses
from .. import language
from ..language import Statement

#: How large a separating set the refinement will look for. A pair that no
#: set of this size separates keeps its edge, which is the safe direction:
#: an edge that should have gone becomes a ``circle`` rather than a wrong
#: orientation. Three because the search is over SUBSETS — the whole point of
#: the relaxation — and the subset count is what grows, not the test.
_MAX_SEPARATING_SET = 3

#: The endpoint marks, as the artifact writes them. Notation rather than
#: prose: ``→``, ``↔`` and ``o→`` read the same to every reader, and what
#: they MEAN is a statement in :class:`themis.estimation.discovery_words`.
TAIL, ARROW, CIRCLE = "tail", "arrow", "circle"


class LatentLaggedDiscoveryError(LaggedDiscoveryError):
    """The request cannot be served in a way the artifact can be audited.

    The same channel as the module this relaxes, and deliberately the same
    class rather than a sibling: every reason either of them refuses is a
    reason about the DESIGN — an unusable time column, a series that is not
    continuous, too few aligned rows, a matrix too wide to travel — and a
    caller who has handled one has handled the other. The species carries
    which reason, as it does everywhere else.
    """


@dataclass(frozen=True)
class LatentLaggedDiscoveryResult:
    """The lagged graph, its marks, and the trail both stages leave.

    - ``variables`` / ``max_lag`` / ``depth`` / ``columns`` — the design, laid
      out exactly as :mod:`themis.estimation.lagged_discovery` lays it out, so
      the two are comparable run against run
    - ``correlation`` — Pearson correlation over ``columns``, the complete
      sufficient statistic for every Fisher-Z test recorded below
    - ``edges`` — the surviving adjacencies, one per ``(driver, lag, target)``,
      each carrying the mark at the driver end
    - ``screen`` — per target, the grow-shrink fixpoint the subset search ran
      inside. Recorded because the conditioning pool is a function of it, so
      a second pass cannot re-derive a verdict without it
    - ``pair_tests`` — one verdict per candidate pair in the screen, with the
      subset behind it: the set that separated them, or the set that came
      closest and did not. The separated ones are what the orientation rules
      read, so they are data rather than a by-product
    - ``orientations`` — one entry per mark written, in the order written
    - ``conflicts`` — a triple that asked for the other mark on an endpoint
      already written. Empty in the population; not empty is the sample
      saying an assumption of this module did not hold
    """

    variables: tuple[str, ...]
    max_lag: int
    depth: int
    columns: tuple[str, ...]
    data_columns: tuple[str, ...]
    time_column: str
    unit_column: str | None
    method: str
    test: str
    alpha: float
    sample_size: int
    data_hash: str
    correlation: tuple[tuple[float, ...], ...]
    edges: tuple[dict, ...]
    conflicts: tuple[dict, ...]
    screen: tuple[dict, ...]
    pair_tests: tuple[dict, ...]
    orientations: tuple[dict, ...]
    note: tuple[Statement, ...]


def discover_latent_lagged_graph(
    data: pd.DataFrame,
    *,
    time: str,
    unit: str | None = None,
    columns: tuple[str, ...] | None = None,
    max_lag: int = 3,
    alpha: float = 0.05,
) -> LatentLaggedDiscoveryResult:
    """Learn the lagged graph of ``data`` without assuming causal sufficiency.

    ``time`` names the integer step column; ``unit`` optionally names the
    panel identifier, and lags never cross from one unit into another.
    ``columns`` restricts the series (defaults to every continuous column
    other than the time and unit ones).

    Raises :class:`LatentLaggedDiscoveryError` on a request whose artifact
    could not be audited, for the reasons its parent class lists.
    """
    if max_lag < 1:
        raise LatentLaggedDiscoveryError(Refuses.BELOW_THE_MINIMUM,
                                         where="max_lag", minimum=1,
                                         got=max_lag)
    if not 0 < alpha < 1:
        raise LatentLaggedDiscoveryError(Refuses.OUTSIDE_THE_RANGE,
                                         where="alpha", range="(0, 1)",
                                         got=alpha)
    for name, role in ((time, "time"), *((unit, "unit"),) * (unit is not None)):
        if name not in data.columns:
            raise LatentLaggedDiscoveryError(Refuses.NOT_A_COLUMN,
                                             where=role, name=name)

    reserved = {time} | ({unit} if unit is not None else set())
    if columns is None:
        series = tuple(
            c for c in data.columns
            if c not in reserved and pd.api.types.is_numeric_dtype(data[c])
            and not pd.api.types.is_bool_dtype(data[c])
        )
    else:
        series = tuple(c for c in columns if c not in reserved)
    if len(series) < 2:
        raise LatentLaggedDiscoveryError(Refuses.TOO_FEW_SERIES,
                                         found=list(series))

    contract = validate_data(
        data,
        required_columns=set(series) | {time},
        presence_columns=() if unit is None else (unit,),
    )
    frame = contract.data

    kinds = {c: _classify_column(frame[c]) for c in series}
    not_continuous = sorted(c for c in series if kinds[c] != "continuous")
    if not_continuous:
        raise LatentLaggedDiscoveryError(Refuses.SERIES_ARE_NOT_CONTINUOUS,
                                         columns=not_continuous)

    # Twice τmax, the depth its sibling uses and for a reason that survives
    # the relaxation: a conditioning variable is looked for among the
    # DRIVER's own past shifted by the lag, so τ + τ' reaches 2·τmax and a
    # column the design does not hold is a test that was not run.
    depth = 2 * max_lag
    width = len(series) * (depth + 1)
    if width > _MAX_DESIGN_WIDTH:
        raise LatentLaggedDiscoveryError(Refuses.THE_DESIGN_IS_TOO_WIDE,
                                         series=len(series), max_lag=max_lag,
                                         width=width, cap=_MAX_DESIGN_WIDTH)

    aligned = _aligned_rows(frame, time=time, unit=unit, depth=depth)
    n = len(aligned)
    if n <= width + 3:
        raise LatentLaggedDiscoveryError(Refuses.TOO_FEW_ALIGNED_ROWS,
                                         rows=n, depth=depth, width=width)

    values = frame[list(series)].to_numpy(dtype=float)
    matrix = np.empty((n, width))
    for k, rows in enumerate(aligned):
        for i in range(len(series)):
            for lag in range(depth + 1):
                matrix[k, design_index(i, lag, depth)] = values[rows[lag], i]
    R = _corr_matrix(matrix)
    cols = design_columns(series, depth)

    def ci(i: int, j: int, cond: tuple[int, ...]) -> float:
        return _fisher_z_pvalue(R, i, j, cond, n)

    at = {var: pos for pos, var in enumerate(series)}

    def idx(link: tuple[str, int]) -> int:
        return design_index(at[link[0]], link[1], depth)

    # --- stage 1: the screen ---------------------------------------------------
    #
    # Grow-shrink to a fixpoint over the lagged pool, exactly as its sibling
    # runs it — and NOT the answer here, which is the whole difference. Under
    # causal sufficiency that fixpoint is the parent set, because a spouse
    # needs a common child and every child is in the future. Drop the
    # assumption and a spouse arrives through a LATENT child: if W causes X
    # and something unrecorded drives both X and Y, then conditioning on X
    # makes W and Y dependent, so W joins Y's fixpoint without being adjacent
    # to it. So this is a screen — a superset the search below is run inside
    # of — and it is recorded because the pool below is a function of it.
    pool = tuple(
        design_index(i, lag, depth)
        for i in range(len(series))
        for lag in range(1, max_lag + 1)
    )
    screen: dict[str, tuple[tuple[str, int], ...]] = {}
    for j, target in enumerate(series):
        t_idx = design_index(j, 0, depth)
        try:
            found = _grow_shrink_mb(ci, t_idx, pool, alpha)
        except MarkovBlanketError:
            raise LatentLaggedDiscoveryError(
                Refuses.CONDITION_SELECTION_DID_NOT_SETTLE,
                target=target) from None
        screen[target] = tuple(_as_link(x, series, depth) for x in found)

    # --- stage 2: one verdict per candidate pair, by searching subsets --------
    #
    # Under causal sufficiency one conditioning set will do — the parents —
    # so the sibling tests each candidate once against the whole of it. Here a
    # larger set can be a WORSE test, because conditioning on a collider opens
    # the path through it. A pair is separated when SOME subset separates it,
    # the empty set included, and the subsets are drawn from both endpoints'
    # screens with the driver's shifted the way MCI shifts them.
    #
    # Every candidate pair gets a verdict, not only the ones the screen kept.
    # The screen decides what may be CONDITIONED ON; which pairs are asked
    # about is the whole pool, because a separating set is what the
    # orientation rules read and the pairs they read it for are exactly the
    # non-adjacent ones. Recording a verdict only where an edge survived
    # would leave every rule with nothing to consult.
    adjacency: dict[str, list[tuple[str, int]]] = {t: [] for t in series}
    pair_tests: list[dict] = []
    for target in series:
        t_idx = design_index(at[target], 0, depth)
        for link in sorted(_as_link(x, series, depth) for x in pool):
            candidates = [idx(c) for c in
                          _condition_pool(link, target, screen, depth)]
            verdict, chosen, p = _search_subsets(
                ci, t_idx, idx(link), candidates, alpha)
            if verdict == "adjacent":
                adjacency[target].append(link)
            pair_tests.append({
                "target": target,
                "driver": link[0],
                "lag": link[1],
                "verdict": verdict,
                # For a separated pair this is the set that separated them,
                # and the orientation rules read it back. For an adjacent one
                # it is the subset that came CLOSEST to separating them,
                # which is the evidence for the edge: no subset did.
                "conditioning_set": sorted(cols[x] for x in chosen),
                "partial_correlation": round(
                    _partial_corr(R, t_idx, idx(link), chosen), 12),
                "p_value": p,
            })

    # --- stage 3: the marks, each with the triple that wrote it ---------------
    marks, orientations, conflicts = _orient(
        series, adjacency, pair_tests, max_lag, depth)

    edges = tuple(
        {
            "driver": driver,
            "lag": lag,
            "target": target,
            "driver_end": marks[(driver, lag, target)],
            # Written down rather than left to be inferred. It is the same
            # on every edge, and that sameness is a claim about the graph —
            # nothing later causes anything earlier — rather than a fact
            # about this run.
            "target_end": ARROW,
        }
        for target in series
        for driver, lag in sorted(adjacency[target])
    )

    causal = sum(1 for e in edges if e["driver_end"] == TAIL)
    confounded = sum(1 for e in edges if e["driver_end"] == ARROW)
    note = (
        language.state(
            Confounded.FOUND_THIS_MANY_EDGES,
            series=len(series), edges=len(edges), causal=causal,
            confounded=confounded, unresolved=len(edges) - causal - confounded,
            max_lag=max_lag, alpha=alpha,
        ),
        language.state(Confounded.A_CIRCLE_IS_THE_ANSWER),
        language.state(Confounded.SUBSETS_RATHER_THAN_THE_WHOLE_SET),
        language.state(Confounded.EVERY_MARK_CARRIES_ITS_TRIPLE),
        language.state(Confounded.SOUND_BUT_NOT_MAXIMALLY_INFORMATIVE),
        language.state(Confounded.ONLY_LAGGED_LINKS),
    ) + (
        (language.state(Confounded.THE_TRIPLES_DID_NOT_AGREE,
                        count=len(conflicts)),) if conflicts else ()
    )

    return LatentLaggedDiscoveryResult(
        variables=series,
        max_lag=max_lag,
        depth=depth,
        columns=cols,
        data_columns=contract.columns,
        time_column=time,
        unit_column=unit,
        method="tsfci_gs",
        test="fisherz",
        alpha=alpha,
        sample_size=n,
        data_hash=contract.data_hash,
        correlation=tuple(tuple(float(v) for v in row) for row in R),
        edges=edges,
        conflicts=tuple(conflicts),
        screen=tuple(
            {"target": target,
             "members": [{"driver": d, "lag": lag}
                         for d, lag in sorted(screen[target])]}
            for target in series
        ),
        pair_tests=tuple(pair_tests),
        orientations=tuple(orientations),
        note=note,
    )


# --- internals ----------------------------------------------------------------


def _condition_pool(link, target, adjacency, depth):
    """What a subset may be drawn from, for the edge ``link → target@t``.

    Both endpoints' neighbourhoods, because a separating set for a pair
    lives in one or the other — the driver's shifted back by the lag, which
    is where causal stationarity is spent for the second time and the reason
    the design carries twice τmax.
    """
    driver, lag = link
    out = {c for c in adjacency[target] if c != link}
    for their_driver, their_lag in adjacency.get(driver, ()):
        shifted = their_lag + lag
        if shifted <= depth:
            out.add((their_driver, shifted))
    out.discard((target, 0))
    out.discard(link)
    return sorted(out)


def _search_subsets(ci, t_idx, d_idx, candidates, alpha):
    """``(verdict, subset, p)`` for one candidate pair.

    Smallest first, and the first separating subset wins: a smaller set is a
    stronger claim about the pair and a shorter thing to check, and the
    orientation rules turn on whether a given vertex is IN the set, so which
    separating set is recorded changes what they conclude.

    **The empty set is a subset.** Skipping it would lose exactly the case
    the relaxation is for: a pair that is independent outright and dependent
    only once a collider between them has been conditioned on. The screen
    conditions on everything, so it is the screen that puts such a pair
    together, and it is size zero that takes it apart again.

    The whole pool is tried last, after every subset up to the cap has
    failed. Without it a pair the SCREEN separated could come back adjacent
    here — the screen conditions on a set that is often larger than the cap,
    so it is not among the subsets — and an edge this module resurrected
    while its sibling had dropped it would be a worse answer from the
    weaker assumption, which is the wrong way round.

    When nothing separates them the pair is adjacent, and what comes back is
    the subset that came CLOSEST — the largest p-value seen. That is the
    evidence for an edge stated positively: not "we found nothing" but "the
    best any set could do was this, and it was not enough".
    """
    ordered = sorted(candidates)
    best: tuple[tuple[int, ...], float] = ((), 0.0)
    sizes = [s for s in range(0, _MAX_SEPARATING_SET + 1) if s <= len(ordered)]
    for size in sizes:
        for subset in itertools.combinations(ordered, size):
            p = ci(t_idx, d_idx, subset)
            if p > alpha:
                return "separated", subset, p
            if p >= best[1]:
                best = (subset, p)
    if len(ordered) > _MAX_SEPARATING_SET:
        whole = tuple(ordered)
        p = ci(t_idx, d_idx, whole)
        if p > alpha:
            return "separated", whole, p
        if p >= best[1]:
            best = (whole, p)
    return "adjacent", best[0], best[1]


def _orient(series, adjacency, pair_tests, max_lag, depth):
    """Every endpoint mark, and the triple that wrote each one.

    ``adjacency`` is keyed by the lag-0 target, and causal stationarity is
    what lets that stand for the whole unrolled window: a triple read at one
    shift is the same triple at every other, so a conclusion is written once
    against ``(driver, lag, target)`` rather than once per position.
    """
    marks = {(driver, lag, target): CIRCLE
             for target in series
             for driver, lag in adjacency[target]}
    orientations: list[dict] = []
    conflicts: list[dict] = []

    sepsets = {
        (entry["driver"], entry["lag"], entry["target"]):
            frozenset(entry["conditioning_set"])
        for entry in pair_tests if entry["verdict"] == "separated"
    }

    def adjacent(driver, lag, target):
        return (driver, lag) in adjacency.get(target, ())

    def name(driver, lag):
        return f"{driver}@t" if lag == 0 else f"{driver}@t-{lag}"

    def write(key, mark, rule, *, between, through, separating_set=None):
        """One mark and the triple that wrote it.

        ``between`` is the pair the rule read and ``through`` the vertex it
        read them through — the same two fields for every rule, so a reader
        looking at two orientations is looking at one shape. Only the two
        triple rules turn on a separating set, and only they carry one: an
        empty list beside the ancestry rule would say the set was empty
        rather than that the rule never asked.

        A second triple asking for the OTHER mark on an endpoint already
        written is recorded rather than dropped. In the population the rules
        cannot disagree; on a finite sample they can, and a disagreement is
        the data saying one of this module's own assumptions did not hold.
        First-written wins so the answer stays deterministic, and the loser
        is carried so the reader is not told a settled thing was settled.
        """
        if marks.get(key) is None:
            return
        if marks[key] != CIRCLE:
            if marks[key] != mark:
                conflicts.append({
                    "driver": key[0], "lag": key[1], "target": key[2],
                    "kept": marks[key], "refused": mark, "rule": rule,
                    "between": list(between), "through": through,
                })
            return
        marks[key] = mark
        entry = {
            "rule": rule, "driver": key[0], "lag": key[1], "target": key[2],
            "driver_end": mark, "between": list(between), "through": through,
        }
        if separating_set is not None:
            entry["separating_set"] = sorted(separating_set)
        orientations.append(entry)

    # The two readings of one triple: W ... X ... Y, W and Y non-adjacent,
    # and the whole question is whether X was in the set that separated them.
    triples = [
        (w, tw, x, tx, y)
        for y in series
        for x, tx in sorted(adjacency[y])
        for w in series
        for tw in range(tx + 1, max_lag + 1)
        if adjacent(w, tw - tx, x) and not adjacent(w, tw, y)
    ]
    for w, tw, x, tx, y in triples:
        sep = sepsets.get((w, tw, y))
        if sep is None:
            # Non-adjacent with nothing recorded to say why cannot be read
            # either way: the rules turn on membership of a SET, and an
            # absent set is not an empty one.
            continue
        rule = "non_collider" if name(x, tx) in sep else "collider"
        write((x, tx, y), TAIL if rule == "non_collider" else ARROW, rule,
              between=[name(w, tw), name(y, 0)], through=name(x, tx),
              separating_set=sep)

    # Ancestry: a tail into a tail is a tail, wherever the circle was.
    for _ in range(len(series) * max_lag + 1):
        wrote = len(orientations)
        for c in series:
            for a, ta in sorted(adjacency[c]):
                if marks[(a, ta, c)] != CIRCLE:
                    continue
                for b, tb in sorted(adjacency[c]):
                    if not 1 <= tb < ta:
                        continue
                    if marks[(b, tb, c)] != TAIL:
                        continue
                    if marks.get((a, ta - tb, b)) != TAIL:
                        continue
                    write((a, ta, c), TAIL, "ancestry",
                          between=[name(a, ta), name(c, 0)],
                          through=name(b, tb))
                    break
        if len(orientations) == wrote:
            break

    return marks, orientations, conflicts


def latent_lagged_discovery_to_dict(
        result: LatentLaggedDiscoveryResult) -> dict:
    """JSON-serialisable view — the artifact
    ``verify_latent_lagged_discovery`` consumes and the MCP tool returns."""
    d = {
        "kind": "latent_lagged_discovery",
        "variables": list(result.variables),
        "max_lag": result.max_lag,
        "depth": result.depth,
        "columns": list(result.columns),
        "data_columns": list(result.data_columns),
        "time_column": result.time_column,
        "unit_column": result.unit_column,
        "method": result.method,
        "test": result.test,
        "alpha": result.alpha,
        "sample_size": result.sample_size,
        "data_hash": result.data_hash,
        "correlation": [list(row) for row in result.correlation],
        "edges": [dict(e) for e in result.edges],
        "conflicts": [dict(c) for c in result.conflicts],
        "screen": [dict(s) for s in result.screen],
        "pair_tests": [dict(t) for t in result.pair_tests],
        "orientations": [dict(o) for o in result.orientations],
        "note": [dict(one) for one in result.note],
    }
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact(d)


def latent_lagged_discovery_to_kernel_ast(
    result: LatentLaggedDiscoveryResult,
    *,
    domain_subjects: tuple[str, ...] = ("me",),
    query: dict | None = None,
) -> dict:
    """Convert the result into a kernel_ast suggestion.

    A ``tail`` becomes a ``cause`` edge between time-indexed atoms and an
    ``arrow`` a ``bidirected`` one — the two things this package can already
    say. A ``circle`` is neither, and it is the reason this conversion is
    not the whole artifact: it becomes an ambiguity the reader is asked
    about, because emitting the cause would be the fabrication this module
    was built to remove and emitting nothing would drop a found adjacency on
    the floor.
    """
    args = [{"type": "const", "name": s} for s in domain_subjects]
    statements: list[dict] = [
        {"kind": "variable", "predicate": var} for var in result.variables
    ]

    def atom(predicate, lag):
        return {"predicate": predicate, "args": args,
                "time_index": {"kind": "relative", "value": -lag}}

    source = {"source": f"discovery:{result.method}"}
    ambiguities: list[dict] = []
    for edge in result.edges:
        driver, lag, target = edge["driver"], edge["lag"], edge["target"]
        if edge["driver_end"] == TAIL:
            statements.append({
                "kind": "cause", "from": atom(driver, lag),
                "to": atom(target, 0), "annotations": dict(source),
            })
        elif edge["driver_end"] == ARROW:
            statements.append({
                "kind": "bidirected", "left": atom(driver, lag),
                "right": atom(target, 0), "annotations": dict(source),
            })
        else:
            ambiguities.append({
                "kind": "latent_or_causal",
                "endpoints": [f"{driver}@t-{lag}", f"{target}@t"],
                "discovery_algorithm": result.method,
                "disambiguation_ask": language.state(
                    Confounded.WHICH_OF_THE_TWO_IS_IT,
                    driver=f"{driver}@t-{lag}", target=f"{target}@t"),
            })
    if query is not None:
        statements.append(query)

    extensions: dict = {
        "latent_lagged_discovery_metadata": {
            "method": result.method,
            "max_lag": result.max_lag,
            "alpha": result.alpha,
            "sample_size": result.sample_size,
            "data_hash": result.data_hash,
            "data_columns": list(result.data_columns),
            "time_column": result.time_column,
            "unit_column": result.unit_column,
            "note": [dict(one) for one in result.note],
        },
    }
    if ambiguities:
        extensions["ambiguities"] = ambiguities
    return {
        "version": "0.1",
        "domain": {
            "objects": [{"kind": "object", "name": s} for s in domain_subjects]
        },
        "statements": statements,
        "extensions": extensions,
    }
