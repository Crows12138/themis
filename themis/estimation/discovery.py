"""Phase 8.1 — causal discovery wrapper around causal-learn.

Three algorithms:
- **PC** (Spirtes, Glymour 1991): assumes no latent confounders.
  Returns a CPDAG — directed edges where orientation is identified
  by colliders, undirected otherwise (Markov equivalence class).
- **FCI** (Spirtes 1997): allows latent confounders. Returns a PAG
  with three endpoint types: TAIL, ARROW, CIRCLE (ambiguous).
- **LiNGAM** (Shimizu et al. 2006): assumes linear non-Gaussian.
  Returns a fully directed DAG when assumptions hold.

The wrapper produces a uniform ``DiscoveryResult`` with three buckets:
- ``directed_edges``: confidently directed (X → Y)
- ``bidirected_edges``: ADMG-style (latent confounder, FCI only)
- ``ambiguous_edges``: undirected or partially-oriented (PC / FCI)

Users / agents take this as a **suggestion** — the kernel still
expects a deterministic kernel_ast input, so the agent must accept,
modify, or reject the suggestion before running identification.

5-rule API gate (causal-learn 0.1.4.5):
- ✅ deterministic with ``random_state`` and fixed alpha
- ⚠ track record: causal-learn ~4 years; activelyl maintained but
  shy of the 5-year threshold. Treat as production with caution;
  pin version, run parity tests on releases.
- ✅ pin version 0.1.4.5
- ✅ parity-testable against R pcalg
- ✅ output (edge lists) trivially fits in JSON

API:

    from themis.estimation.discovery import discover_graph
    result = discover_graph(data, algorithm="pc", alpha=0.05)
    for src, dst in result.directed_edges:
        print(f"{src} -> {dst}")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .contract import validate_data


AlgorithmName = Literal["pc", "fci", "lingam", "auto"]


@dataclass(frozen=True)
class DiscoveryResult:
    """Output of a causal-discovery run.

    - ``directed_edges``: tuple of (source_predicate, target_predicate)
      for confidently directed edges
    - ``bidirected_edges``: tuple of (a, b) frozen pairs for ADMG-style
      latent-confounder edges (only populated by FCI)
    - ``ambiguous_edges``: tuple of (a, b) for edges whose orientation
      is in the Markov equivalence class but not pinned (PC / FCI)
    - ``algorithm``: the algorithm actually run
    - ``alpha``: significance level used
    - ``data_hash``: SHA-256 of the data used (verifier reproducibility)
    - ``columns``: variable names in canonical order
    - ``note``: human-readable summary
    """

    directed_edges: tuple[tuple[str, str], ...]
    bidirected_edges: tuple[frozenset[str], ...]
    ambiguous_edges: tuple[frozenset[str], ...]
    algorithm: str
    alpha: float
    sample_size: int
    data_hash: str
    columns: tuple[str, ...]
    note: str
    assumption_violations: tuple[str, ...] = ()
    """Empirically detected violations of the algorithm's preconditions
    (e.g. Gaussian data on LiNGAM, sub-threshold sample size). Surfaces
    through ``extensions.discovery_metadata`` so the
    ``graph_learned_from_data`` caveat names *which* algorithm
    assumptions look unsafe on the actual data, not just which
    assumptions the algorithm requires in principle."""

    column_dtypes: tuple[tuple[str, str], ...] = ()
    """Per-column classification: ``"bool"`` (≤2 unique values),
    ``"discrete"`` (3-20 unique values), ``"continuous"`` (more, or
    non-integer). Used by ``discovery_to_kernel_ast`` to validate
    caller-supplied ``bool_predicates`` against the actual data shape
    — flagging a column as bool when it has 100 unique values produces
    a kernel_ast that's syntactically valid but semantically lying."""


def discover_graph(
    data: pd.DataFrame,
    *,
    algorithm: AlgorithmName = "auto",
    alpha: float = 0.05,
    columns: tuple[str, ...] | None = None,
    random_state: int = 42,
) -> DiscoveryResult:
    """Run a causal-discovery algorithm on ``data`` and return a
    structured suggestion.

    ``columns`` selects which DataFrame columns to use; defaults to
    all numeric / bool columns. ``algorithm='auto'`` heuristically
    picks LiNGAM for continuous non-Gaussian data, else PC.
    """
    if columns is None:
        # Default: all numeric / bool columns the contract validator accepts
        cols = tuple(
            c for c in data.columns
            if pd.api.types.is_numeric_dtype(data[c])
            or pd.api.types.is_bool_dtype(data[c])
        )
    else:
        cols = tuple(columns)

    if not cols:
        raise ValueError("discover_graph: no usable columns in data")

    contract = validate_data(data, required_columns=set(cols))
    df = contract.data[list(cols)]

    resolved = _resolve_algorithm(algorithm, df)

    # Coerce to numpy float matrix; bool → 0/1
    matrix = df.to_numpy(dtype=float)

    if resolved == "pc":
        directed, bidirected, ambiguous = _run_pc(
            matrix, cols, alpha=alpha,
        )
    elif resolved == "fci":
        directed, bidirected, ambiguous = _run_fci(
            matrix, cols, alpha=alpha,
        )
    elif resolved == "lingam":
        directed, bidirected, ambiguous = _run_lingam(
            matrix, cols, random_state=random_state,
        )
    else:
        raise ValueError(f"unknown algorithm {algorithm!r}")

    note = _format_note(resolved, len(directed), len(bidirected), len(ambiguous))
    violations = _detect_assumption_violations(resolved, df, contract.sample_size)
    column_dtypes = tuple(
        (col, _classify_column(df[col])) for col in cols
    )

    return DiscoveryResult(
        directed_edges=directed,
        bidirected_edges=bidirected,
        ambiguous_edges=ambiguous,
        algorithm=resolved,
        alpha=alpha,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        columns=cols,
        note=note,
        assumption_violations=violations,
        column_dtypes=column_dtypes,
    )


def _classify_column(series: pd.Series) -> str:
    """Per-column dtype classification used to validate caller-supplied
    ``bool_predicates`` later. Two unique values is bool; up to 20
    distinct integer / categorical values is discrete; otherwise
    continuous."""
    n_unique = series.nunique(dropna=True)
    if n_unique <= 2:
        return "bool"
    if n_unique <= 20 and (
        pd.api.types.is_integer_dtype(series)
        or pd.api.types.is_object_dtype(series)
        or pd.api.types.is_categorical_dtype(series)
    ):
        return "discrete"
    return "continuous"


def _detect_assumption_violations(
    algorithm: str,
    df: pd.DataFrame,
    sample_size: int,
) -> tuple[str, ...]:
    """Empirically check the data against the algorithm's preconditions.
    Returns a tuple of human-readable violation messages — empty tuple
    if no violations detected.

    Detection is intentionally conservative: only flag clear violations
    (Gaussian data on LiNGAM, sample size below standard thresholds).
    Borderline cases pass silently to avoid false-alarming on every run.
    """
    violations: list[str] = []
    numeric = df.select_dtypes(include=[np.number])

    if algorithm == "lingam" and not numeric.empty:
        max_abs_skew = float(numeric.apply(lambda s: float(s.skew())).abs().max())
        if max_abs_skew < 0.5:
            violations.append(
                f"data appears Gaussian (max |skew| = {max_abs_skew:.2f} < 0.5); "
                "LiNGAM identifiability requires non-Gaussian noise — "
                "edge directions on Gaussian data are essentially arbitrary"
            )

    if algorithm in ("pc", "fci") and sample_size < 200:
        violations.append(
            f"sample size {sample_size} < 200 — conditional independence "
            "tests have low power; expect spurious edges and missed edges"
        )

    return tuple(violations)


# --- internals ----------------------------------------------------------------


def _resolve_algorithm(algorithm: str, df: pd.DataFrame) -> str:
    if algorithm != "auto":
        return algorithm
    # Heuristic: if any column has clearly non-Gaussian skew, prefer
    # LiNGAM (it can fully direct edges under non-Gaussianity).
    # Otherwise default to PC (cheapest, broadest assumptions).
    numeric_only = df.select_dtypes(include=[np.number])
    if numeric_only.empty:
        return "pc"
    # Skewness magnitude > 0.5 on any column → suspect non-Gaussian
    skew = numeric_only.apply(lambda s: float(s.skew())).abs()
    if skew.max() > 0.5:
        return "lingam"
    return "pc"


def _run_pc(matrix, cols, *, alpha):
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.graph.Endpoint import Endpoint

    result = pc(
        matrix, alpha=alpha, show_progress=False,
        node_names=list(cols),
    )
    return _extract_edges(result.G, cols, Endpoint)


def _run_fci(matrix, cols, *, alpha):
    from causallearn.search.ConstraintBased.FCI import fci
    from causallearn.graph.Endpoint import Endpoint

    g, edges = fci(
        matrix, alpha=alpha, verbose=False,
        node_names=list(cols),
    )
    return _extract_edges(g, cols, Endpoint)


def _run_lingam(matrix, cols, *, random_state):
    from causallearn.search.FCMBased.lingam import DirectLiNGAM

    model = DirectLiNGAM()
    model.fit(matrix)
    # adjacency_matrix_[i, j] != 0 means j → i (note column-row convention)
    adj = np.asarray(model.adjacency_matrix_)
    n_cols = len(cols)
    directed: list[tuple[str, str]] = []
    for i in range(n_cols):
        for j in range(n_cols):
            if i == j:
                continue
            if abs(adj[i, j]) > 1e-9:
                # j → i in causal-learn's convention
                directed.append((cols[j], cols[i]))
    return tuple(directed), (), ()


def _extract_edges(graph, cols, Endpoint):
    """Walk a causal-learn GeneralGraph and bucket its edges into
    directed / bidirected / ambiguous.

    Endpoint semantics:
    - TAIL on side A + ARROW on side B: directed A → B
    - ARROW on both sides: bidirected (latent confounder)
    - any CIRCLE: ambiguous orientation (PAG)
    - TAIL on both sides: undirected (CPDAG / PAG)
    """
    directed: list[tuple[str, str]] = []
    bidirected: list[frozenset[str]] = []
    ambiguous: list[frozenset[str]] = []

    for edge in graph.get_graph_edges():
        n1 = edge.get_node1().get_name()
        n2 = edge.get_node2().get_name()
        e1 = edge.get_endpoint1()
        e2 = edge.get_endpoint2()

        # Check for CIRCLE (PAG ambiguity) first
        if e1 == Endpoint.CIRCLE or e2 == Endpoint.CIRCLE:
            ambiguous.append(frozenset({n1, n2}))
            continue

        if e1 == Endpoint.ARROW and e2 == Endpoint.ARROW:
            bidirected.append(frozenset({n1, n2}))
        elif e1 == Endpoint.TAIL and e2 == Endpoint.ARROW:
            # TAIL at n1, ARROW at n2 → n1 → n2
            directed.append((n1, n2))
        elif e1 == Endpoint.ARROW and e2 == Endpoint.TAIL:
            # ARROW at n1, TAIL at n2 → n2 → n1
            directed.append((n2, n1))
        else:
            # TAIL-TAIL = undirected
            ambiguous.append(frozenset({n1, n2}))

    return tuple(directed), tuple(bidirected), tuple(ambiguous)


class DomainMismatchError(ValueError):
    """Caller declared a column as bool but the data has more than two
    unique values. Refusing to emit a syntactically-valid-but-lying
    kernel_ast is preferred over running structural reasoning over a
    domain that doesn't match the data.
    """


def discovery_to_kernel_ast(
    result: DiscoveryResult,
    *,
    domain_subjects: tuple[str, ...] = ("me",),
    bool_predicates: tuple[str, ...] = (),
    query: dict | None = None,
) -> dict:
    """Convert a ``DiscoveryResult`` into a kernel_ast suggestion dict.

    The output is a complete kernel_ast that ``themis.run`` will accept
    — but agents / users SHOULD review and edit it before running:
    ambiguous edges become ``extensions.ambiguities`` entries, and
    each emitted ``cause`` edge carries an ``annotations.source =
    "discovery"`` flag so downstream provenance is auditable.

    Parameters
    ----------
    result: DiscoveryResult from ``discover_graph``.
    domain_subjects: tuple of object names for the domain block.
        Defaults to ``("me",)`` matching the rest of the kernel.
    bool_predicates: tuple of column names to declare as bool domain.
        Anything not in this list is left without an explicit domain
        (the schema validator will reject; the agent must fill these).
    query: optional pre-built query statement to append. Useful when
        the discovery is being run inside an end-to-end pipeline that
        already knows the question.

    Returns
    -------
    dict — a kernel_ast suggestion. Always contains:
        - version, domain, statements (variable + cause + bidirected)
        - extensions.discovery_metadata: provenance + algorithm + alpha
        - extensions.ambiguities: one entry per ambiguous edge

    Caller is responsible for:
        - filling variable domains for non-bool predicates
        - resolving each ``ambiguous_orientation`` ambiguity by
          deciding direction (or leaving both alternatives)
        - appending a query statement if not provided

    Raises ``DomainMismatchError`` when a column listed in
    ``bool_predicates`` has more than two unique values in the
    underlying data — emitting a ``[True, False]`` domain on a
    continuous column would let structural reasoning run over a
    schema-valid but semantically lying kernel_ast.
    """
    dtypes_lookup = dict(result.column_dtypes)
    mismatched = [
        col for col in bool_predicates
        if dtypes_lookup.get(col, "bool") != "bool"
    ]
    if mismatched:
        details = ", ".join(
            f"{col} ({dtypes_lookup.get(col, '?')})" for col in mismatched
        )
        raise DomainMismatchError(
            f"bool_predicates declared {details} as bool but the data has "
            f"more than two unique values for these columns. Discretize "
            f"explicitly (median split / threshold) before calling discover, "
            f"or drop them from bool_predicates and supply an explicit "
            f"multi-level domain to the resulting kernel_ast."
        )

    statements: list[dict] = []

    # 1. Variable declarations — one per column
    for col in result.columns:
        if col in bool_predicates:
            statements.append({
                "kind": "variable",
                "predicate": col,
                "domain": [True, False],
            })
        else:
            statements.append({
                "kind": "variable",
                "predicate": col,
            })

    # 2. Directed cause edges
    args = [{"type": "const", "name": s} for s in domain_subjects]
    for src, dst in result.directed_edges:
        statements.append({
            "kind": "cause",
            "from": {"predicate": src, "args": args},
            "to": {"predicate": dst, "args": args},
            "annotations": {
                "source": f"discovery:{result.algorithm}",
            },
        })

    # 3. Bidirected (latent confounder) edges from FCI
    for pair in result.bidirected_edges:
        a, b = sorted(pair)
        statements.append({
            "kind": "bidirected",
            "left": {"predicate": a, "args": args},
            "right": {"predicate": b, "args": args},
            "annotations": {
                "source": f"discovery:{result.algorithm}",
            },
        })

    # 4. Optional query statement
    if query is not None:
        statements.append(query)

    # 5. Ambiguities for each undirected / partially-oriented edge
    ambiguities: list[dict] = [
        {
            "kind": "ambiguous_orientation",
            "endpoints": sorted(pair),
            "discovery_algorithm": result.algorithm,
            "disambiguation_ask": (
                f"算法 {result.algorithm.upper()} 找到 {sorted(pair)[0]} "
                f"和 {sorted(pair)[1]} 之间存在因果关联，但从数据无法判定"
                "方向。你能根据领域知识告诉我方向吗？"
            ),
        }
        for pair in result.ambiguous_edges
    ]

    extensions = {
        "discovery_metadata": {
            "algorithm": result.algorithm,
            "alpha": result.alpha,
            "sample_size": result.sample_size,
            "data_hash": result.data_hash,
            "columns": list(result.columns),
            "note": result.note,
            "assumption_violations": list(result.assumption_violations),
            "column_dtypes": {col: dt for col, dt in result.column_dtypes},
        },
    }
    if ambiguities:
        extensions["ambiguities"] = ambiguities

    return {
        "version": "0.1",
        "domain": {
            "objects": [
                {"kind": "object", "name": s} for s in domain_subjects
            ],
        },
        "statements": statements,
        "extensions": extensions,
    }


def _format_note(algorithm: str, n_dir: int, n_bidir: int, n_amb: int) -> str:
    parts = [
        f"causal-learn {algorithm.upper()} found "
        f"{n_dir} directed, {n_bidir} bidirected, {n_amb} ambiguous edges"
    ]
    if algorithm == "pc":
        parts.append("PC assumes no latent confounders; consider FCI if that is wrong")
    elif algorithm == "fci":
        parts.append("FCI allows latent confounders; CIRCLE endpoints denote ambiguous orientation")
    elif algorithm == "lingam":
        parts.append("LiNGAM assumes linear non-Gaussian noise; weak signal under Gaussian data")
    if n_amb > 0 and algorithm != "lingam":
        parts.append(
            f"{n_amb} edges are not orientable from observational data alone "
            "— user / domain knowledge required to direct them"
        )
    return "; ".join(parts)
