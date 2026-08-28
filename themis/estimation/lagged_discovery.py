"""Learning the LAGGED graph from a time series — PCMCI's second stage, with
a condition-selection step whose output a second pass can check.

Themis could already REPRESENT a lagged graph (Phase 5 §T: an atom carries a
``time_index``, ``graph_projection`` unrolls it, the longitudinal estimators
run on it) and could already ESTIMATE through one. What it could not do was
read a time series and say which lagged links are in it — so a user with
panel data had to bring the lag structure with them, which is the one thing a
time series is best placed to answer.

Reference: Runge, Nowack, Kretschmer, Flaxman & Sejdinovic 2019, "Detecting
and quantifying causal associations in large nonlinear time series datasets",
*Science Advances* 5:eaau4996. Written from the paper. The reference
implementation (``tigramite``) is GPL and was not read or vendored.

What PCMCI is, and what is load-bearing in it
--------------------------------------------
Two stages. **Condition selection** finds, for each variable, a small set of
lagged parents. **MCI** — momentary conditional independence — then tests each
candidate link ``X^i_{t-τ} → X^j_t`` conditioning on *both* the target's
parents *and the driver's own parents shifted back by τ*. That second half is
the paper's contribution: with autocorrelated series, conditioning only on the
target's parents leaves the test statistic mis-calibrated, and the driver's
own past is what removes it. It is also where causal stationarity is spent —
the parents of ``X^i_t`` are taken to be the parents of ``X^i_{t-τ}`` shifted.

Where this deviates, and why
----------------------------
The paper's condition-selection step is PC₁, a deliberately cheap pruning
that removes a candidate as soon as SOME subset of the strongest others makes
it independent. That makes its output un-checkable: a candidate PC₁ dropped
need not be independent given the parent set it ended up with, so a second
pass has nothing to hold the result to except re-running the same search.

So condition selection here is the interleaved grow-shrink already in
:mod:`themis.estimation.discovery`, run to a fixpoint over the lagged
candidate pool. Its fixpoint IS a property of the output: nothing can be
added (every non-parent is independent of the target given the parents) and
nothing removed (every parent is dependent given the rest). Every candidate
is at a strictly earlier time than the target and therefore a non-descendant
of it, and a spouse needs a common child to be conditioned on — which is in
the future and never in the pool — so within a past-only pool that fixpoint
is the PARENT set rather than the Markov blanket. Under causal sufficiency
and faithfulness it is what a parent set means, and
:func:`themis.verify_lagged_discovery` holds the result to it. MCI is
unchanged.

The trade is stated rather than hidden: grow-shrink tests every candidate
against the current set on every round, so it costs more than PC₁ on very
many variables, and it buys an answer a reader can audit instead of repeat.

Scope (declared)
----------------
- **Lagged links only.** A contemporaneous link ``X^i_t → X^j_t`` is neither
  sought nor represented; PCMCI+ (Runge 2020) is the algorithm for that, and
  running this where contemporaneous causation exists can put a spurious
  lagged link in its place. Declared as an assumption, not silently assumed.
- **Causal stationarity** — the lagged structure does not change over t. MCI
  spends it, and so does pooling every t into one correlation matrix.
- **Causal sufficiency** — no unobserved confounder of two recorded series.
  PCMCI assumes it; LPCMCI is the relaxation and is not built.
- **Linear-Gaussian**, because the test is Fisher-Z partial correlation. That
  is what makes the correlation matrix a COMPLETE sufficient statistic and
  therefore what makes every recorded test re-derivable from the artifact.
  A nonlinear test (the paper's CMI / GPDC) would need its own statistic.
- **Integer time steps.** A lag is a number of steps, and only the caller
  knows what one step is, so a datetime column is converted upstream. Lags
  are taken by VALUE within a unit, so a gap in the series drops the rows
  that would have straddled it rather than silently lagging across it.

API::

    from themis.estimation.lagged_discovery import (
        discover_lagged_graph, lagged_discovery_to_dict,
    )
    result = discover_lagged_graph(frame, time="t", max_lag=2)
    themis.verify_lagged_discovery(lagged_discovery_to_dict(result))
"""
from __future__ import annotations

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

#: How wide the lagged design may get before its correlation matrix stops
#: being a statistic that can travel with the answer. The artifact carries
#: ``width**2`` floats, and the whole point of recording the statistic is
#: that a second pass can redo every test from it — a matrix too large to
#: ship would make the audit trail the thing that had to be trusted. Refused
#: with both levers named rather than truncated.
_MAX_DESIGN_WIDTH = 200


class LaggedDiscoveryError(ValueError):
    """The lagged-discovery request cannot be served as posed — the time
    column is unusable, the series is too short for the lags asked for, the
    columns are not continuous, or the design would be too wide to record.
    Preferred over returning a lagged graph that cannot be verified."""


@dataclass(frozen=True)
class LaggedDiscoveryResult:
    """The lagged parents of each variable, and the audit trail for both
    stages.

    - ``variables``: the series, in the order the design matrix is indexed by
    - ``max_lag``: the deepest candidate lag τmax
    - ``depth``: the deepest lag the design HOLDS, ``2 * max_lag`` — MCI
      conditions on the driver's parents shifted back by τ, and τ + τ' can
      reach twice τmax, so the columns have to exist for the test to be the
      test the paper describes
    - ``columns``: the design's column names, ``var@t-lag``, in index order.
      Read rather than parsed: the layout is a function of ``variables`` and
      ``depth``, and both sides derive it
    - ``correlation``: Pearson correlation over ``columns`` — the complete
      sufficient statistic for every Fisher-Z test either stage runs
    - ``sample_size``: rows surviving alignment (every lag 0..depth present
      in the same unit), which is what every test's degrees of freedom use
    - ``parents``: per target variable, the fixpoint parent set as
      ``(driver, lag)`` pairs
    - ``parent_tests``: the fixpoint stated as tests — one per candidate per
      target, ``role="parent"`` (must be dependent given the rest) or
      ``role="not_a_parent"`` (must be independent given all of them)
    - ``links``: one MCI test per candidate link, with the conditioning set
      it was run on and whether it was detected at ``alpha``
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
    parents: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    parent_tests: tuple[dict, ...]
    links: tuple[dict, ...]
    note: str


def design_columns(variables, depth: int) -> tuple[str, ...]:
    """The design's column names, in the order its index formula puts them.

    Public and derived because BOTH sides need it and neither may be the
    other's source: the producer builds the matrix by this order and the
    verifier rebuilds the same list and holds the recorded one to it. A name
    is then a label a reader can follow rather than a thing to parse.
    """
    return tuple(
        f"{var}@t" if lag == 0 else f"{var}@t-{lag}"
        for var in variables
        for lag in range(depth + 1)
    )


def design_index(var_position: int, lag: int, depth: int) -> int:
    """Where ``variables[var_position]`` at ``lag`` sits in the design."""
    return var_position * (depth + 1) + lag


def discover_lagged_graph(
    data: pd.DataFrame,
    *,
    time: str,
    unit: str | None = None,
    columns: tuple[str, ...] | None = None,
    max_lag: int = 3,
    alpha: float = 0.05,
) -> LaggedDiscoveryResult:
    """Learn the lagged causal parents of every series in ``data``.

    ``time`` names the integer step column; ``unit`` optionally names the
    panel identifier, and lags never cross from one unit into another.
    ``columns`` restricts the series (defaults to every continuous column
    other than the time and unit ones).

    Raises ``LaggedDiscoveryError`` when the request cannot be served in a way
    the artifact can be audited: a time column that is not integer-valued or
    repeats within a unit, fewer than two series, a discrete column (the
    Fisher-Z sufficient statistic does not apply), a design too wide to
    record, or too few aligned rows to test at this depth.
    """
    if max_lag < 1:
        raise LaggedDiscoveryError(
            f"max_lag must be at least 1; got {max_lag}"
        )
    if not 0 < alpha < 1:
        raise LaggedDiscoveryError(f"alpha must be in (0, 1); got {alpha}")
    for name, role in ((time, "time"), *((unit, "unit"),) * (unit is not None)):
        if name not in data.columns:
            raise LaggedDiscoveryError(
                f"the {role} column {name!r} is not in the data"
            )

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
        raise LaggedDiscoveryError(
            "a lagged graph needs at least two series; found "
            f"{list(series)}. Name them with columns=(...) if the "
            "defaults picked the wrong ones."
        )

    # The unit id goes in as a PRESENCE column, the category a cluster id
    # uses: it must be there and be non-null, it is carried through
    # uncoerced so a string panel id survives, and it is excluded from
    # ``data_hash``. That last part is a real weakening and is stated rather
    # than absorbed — unlike a cluster id, the unit column CHANGES the
    # answer, because it decides which rows may be lagged onto which. So two
    # runs differing only in how rows are grouped into units share a digest,
    # and what tells them apart is the recorded correlation matrix, which is
    # what every claim in the artifact actually rests on. ``data_columns``
    # names the digest's denominator, so a reader can see the omission.
    contract = validate_data(
        data,
        required_columns=set(series) | {time},
        presence_columns=() if unit is None else (unit,),
    )
    frame = contract.data

    kinds = {c: _classify_column(frame[c]) for c in series}
    not_continuous = sorted(c for c in series if kinds[c] != "continuous")
    if not_continuous:
        raise LaggedDiscoveryError(
            f"columns {not_continuous} are not continuous, and the Fisher-Z "
            "partial-correlation test this records its statistic for applies "
            "to continuous series. A discrete lagged test needs contingency "
            "counts as its statistic and is not built."
        )

    depth = 2 * max_lag
    width = len(series) * (depth + 1)
    if width > _MAX_DESIGN_WIDTH:
        raise LaggedDiscoveryError(
            f"{len(series)} series at max_lag={max_lag} make a design "
            f"{width} columns wide, past the {_MAX_DESIGN_WIDTH} whose "
            "correlation matrix can travel with the answer. Lower max_lag "
            "or name fewer series — the statistic has to ship, because "
            "re-deriving every test from it is what the answer is worth."
        )

    aligned = _aligned_rows(frame, time=time, unit=unit, depth=depth)
    n = len(aligned)
    if n <= width + 3:
        raise LaggedDiscoveryError(
            f"only {n} rows have every lag up to {depth} present in the same "
            f"unit, which cannot support a test conditioning on up to "
            f"{width} columns. A longer series, fewer series, or a smaller "
            "max_lag."
        )

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

    # --- stage 1: the parent set of each series, to a fixpoint ----------------
    parents: dict[str, tuple[tuple[str, int], ...]] = {}
    parent_idx: dict[str, tuple[int, ...]] = {}
    pool = tuple(
        design_index(i, lag, depth)
        for i in range(len(series))
        for lag in range(1, max_lag + 1)
    )
    for j, target in enumerate(series):
        t_idx = design_index(j, 0, depth)
        try:
            found = _grow_shrink_mb(ci, t_idx, pool, alpha)
        except MarkovBlanketError as exc:
            raise LaggedDiscoveryError(
                f"condition selection for {target!r} did not settle: {exc}"
            ) from None
        parent_idx[target] = tuple(found)
        parents[target] = tuple(
            _as_link(idx, series, depth) for idx in found)

    parent_tests = tuple(
        entry
        for target in series
        for entry in _parent_tests(R, n, cols, series, depth, target,
                                   parent_idx[target], pool, alpha)
    )

    # --- stage 2: MCI ---------------------------------------------------------
    links: list[dict] = []
    for j, target in enumerate(series):
        t_idx = design_index(j, 0, depth)
        for i, driver in enumerate(series):
            for lag in range(1, max_lag + 1):
                d_idx = design_index(i, lag, depth)
                cond = _mci_conditions(
                    d_idx, t_idx, driver_lag=lag, driver=driver,
                    target=target, parent_idx=parent_idx, series=series,
                    depth=depth)
                p = ci(t_idx, d_idx, cond)
                links.append({
                    "driver": driver,
                    "lag": lag,
                    "target": target,
                    "conditioning_set": sorted(cols[x] for x in cond),
                    "partial_correlation": round(
                        _partial_corr(R, t_idx, d_idx, cond), 12),
                    "p_value": p,
                    "detected": p <= alpha,
                })

    detected = sum(1 for link in links if link["detected"])
    note = (
        f"PCMCI（Runge 等 2019）在 {len(series)} 条序列上找到 {detected} 条滞后"
        f"因果链接（候选 {len(links)} 条，τmax={max_lag}，α={alpha}）。"
        "第一阶段用 grow-shrink 跑到不动点来选条件集——它的输出本身是可核的："
        "任何非父节点在给定父集后都独立、任何父节点在给定其余父节点后都相依。"
        "第二阶段是 MCI：检验一条链接时，同时以目标的父集**和驱动变量自己的"
        "父集（按滞后平移）**为条件，这是自相关下 p 值能被信任的原因。"
        "**只找滞后链接**：同期因果既不寻找也不表示，若数据里有同期因果，"
        "它可能以一条虚假的滞后链接出现。"
    )

    return LaggedDiscoveryResult(
        variables=series,
        max_lag=max_lag,
        depth=depth,
        columns=cols,
        data_columns=contract.columns,
        time_column=time,
        unit_column=unit,
        method="pcmci_gs",
        test="fisherz",
        alpha=alpha,
        sample_size=n,
        data_hash=contract.data_hash,
        correlation=tuple(tuple(float(v) for v in row) for row in R),
        parents=tuple((target, parents[target]) for target in series),
        parent_tests=parent_tests,
        links=tuple(links),
        note=note,
    )


# --- internals ----------------------------------------------------------------


def _aligned_rows(frame, *, time, unit, depth) -> tuple[tuple[int, ...], ...]:
    """For each usable row, the row indices of its own lag 0..``depth``.

    Lags are taken by the VALUE of the time column within a unit, not by
    position. A series with a hole in it therefore loses the rows that would
    have straddled the hole, instead of quietly treating the row before the
    hole as the previous step — which is the same defect as lagging across
    the seam between two units, and the reason the unit column exists here.
    """
    times = frame[time].to_numpy()
    if not np.all(np.isfinite(times)):
        raise LaggedDiscoveryError(
            f"the time column {time!r} holds a missing or infinite value"
        )
    steps = np.rint(times).astype(np.int64)
    if not np.allclose(times, steps):
        raise LaggedDiscoveryError(
            f"the time column {time!r} is not integer-valued. A lag is a "
            "number of steps and only you know what one step is, so convert "
            "a date or a timestamp into a step index first."
        )
    units = (frame[unit].to_numpy() if unit is not None
             else np.zeros(len(frame), dtype=np.int64))

    where: dict[tuple, int] = {}
    for row, (u, t) in enumerate(zip(units, steps)):
        key = (u.item() if hasattr(u, "item") else u, int(t))
        if key in where:
            raise LaggedDiscoveryError(
                f"two rows share {time}={key[1]}"
                + (f" in {unit}={key[0]!r}" if unit is not None else "")
                + "; a step has to name one observation per series"
            )
        where[key] = row

    aligned: list[tuple[int, ...]] = []
    for row, (u, t) in enumerate(zip(units, steps)):
        key_u = u.item() if hasattr(u, "item") else u
        rows = []
        for lag in range(depth + 1):
            hit = where.get((key_u, int(t) - lag))
            if hit is None:
                break
            rows.append(hit)
        else:
            aligned.append(tuple(rows))
    return tuple(aligned)


def _as_link(index: int, series, depth: int) -> tuple[str, int]:
    """A design index read back as the ``(variable, lag)`` it stands for."""
    position, lag = divmod(index, depth + 1)
    return series[position], lag


def _parent_tests(R, n, cols, series, depth, target, found, pool, alpha):
    """The fixpoint of stage 1, stated as the tests that define it.

    One entry per candidate: a parent has to be dependent on the target given
    the OTHER parents, a non-parent independent given ALL of them. Recorded
    rather than derived at read time because they are what the verifier holds
    the search to — and unlike the search itself they are checkable from the
    correlation matrix alone.
    """
    t_idx = design_index(series.index(target), 0, depth)
    kept = set(found)
    for candidate in pool:
        if candidate in kept:
            role = "parent"
            cond = tuple(x for x in found if x != candidate)
            passes = lambda p: p <= alpha          # noqa: E731
        else:
            role = "not_a_parent"
            cond = tuple(found)
            passes = lambda p: p > alpha           # noqa: E731
        p = _fisher_z_pvalue(R, t_idx, candidate, cond, n)
        driver, lag = _as_link(candidate, series, depth)
        yield {
            "target": target,
            "driver": driver,
            "lag": lag,
            "role": role,
            "conditioning_set": sorted(cols[x] for x in cond),
            "partial_correlation": round(
                _partial_corr(R, t_idx, candidate, cond), 12),
            "p_value": p,
            "passed": bool(passes(p)),
        }


def _mci_conditions(
    d_idx: int, t_idx: int, *, driver_lag: int, driver: str, target: str,
    parent_idx, series, depth: int,
) -> tuple[int, ...]:
    """What an MCI test conditions on: the target's parents without the link
    being tested, plus the driver's own parents shifted back by the lag.

    The shift is where causal stationarity is spent — the parents of
    ``X^i_t`` are taken to be the parents of ``X^i_{t-τ}`` moved back with
    it — and it is why the design carries lags to twice τmax: a parent at
    τ' behind a driver at τ sits at τ + τ', and a conditioning variable the
    design does not hold is a test that was not the test.
    """
    cond = {x for x in parent_idx[target] if x != d_idx}
    for their_driver, their_lag in (
        _as_link(x, series, depth) for x in parent_idx[driver]
    ):
        shifted = their_lag + driver_lag
        if shifted <= depth:
            cond.add(design_index(series.index(their_driver), shifted, depth))
    cond.discard(t_idx)
    return tuple(sorted(cond))


def lagged_discovery_to_dict(result: LaggedDiscoveryResult) -> dict:
    """JSON-serialisable view — the artifact ``verify_lagged_discovery``
    consumes and the MCP tool returns."""
    d = {
        "kind": "lagged_discovery",
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
        "parents": [
            {"target": target,
             "parents": [{"driver": d_, "lag": lag} for d_, lag in ps]}
            for target, ps in result.parents
        ],
        "parent_tests": [dict(t) for t in result.parent_tests],
        "links": [dict(link) for link in result.links],
        "note": result.note,
    }
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact(d)


def lagged_discovery_to_kernel_ast(
    result: LaggedDiscoveryResult,
    *,
    domain_subjects: tuple[str, ...] = ("me",),
    query: dict | None = None,
) -> dict:
    """Convert a ``LaggedDiscoveryResult`` into a kernel_ast suggestion.

    Each detected link becomes a ``cause`` edge between time-indexed atoms —
    the representation Phase 5 §T already threads through projection,
    identification and the longitudinal estimators — carrying
    ``annotations.source = "discovery:pcmci_gs"`` so the provenance survives
    into the assumption ledger as a learned edge rather than a declared one.

    A suggestion, like every discovery output: the kernel still wants a
    deterministic program, so the agent or the user accepts, edits or rejects
    this before running identification.
    """
    args = [{"type": "const", "name": s} for s in domain_subjects]
    statements: list[dict] = [
        {"kind": "variable", "predicate": var} for var in result.variables
    ]
    for link in result.links:
        if not link["detected"]:
            continue
        statements.append({
            "kind": "cause",
            "from": {
                "predicate": link["driver"], "args": args,
                "time_index": {"kind": "relative", "value": -link["lag"]},
            },
            "to": {
                "predicate": link["target"], "args": args,
                "time_index": {"kind": "relative", "value": 0},
            },
            "annotations": {"source": f"discovery:{result.method}"},
        })
    if query is not None:
        statements.append(query)
    return {
        "version": "0.1",
        "domain": {
            "objects": [{"kind": "object", "name": s} for s in domain_subjects]
        },
        "statements": statements,
        "extensions": {
            "lagged_discovery_metadata": {
                "method": result.method,
                "max_lag": result.max_lag,
                "alpha": result.alpha,
                "sample_size": result.sample_size,
                "data_hash": result.data_hash,
                "data_columns": list(result.data_columns),
                "time_column": result.time_column,
                "unit_column": result.unit_column,
                "note": result.note,
            },
        },
    }
