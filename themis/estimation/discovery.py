"""Phase 8.1 — causal discovery wrapper around causal-learn.

Five algorithms (one ``AlgorithmSpec`` registry entry each):
- **PC** (Spirtes, Glymour 1991): assumes no latent confounders.
  Returns a CPDAG — directed edges where orientation is identified
  by colliders, undirected otherwise (Markov equivalence class).
- **FCI** (Spirtes 1997): allows latent confounders. Returns a PAG
  with three endpoint types: TAIL, ARROW, CIRCLE (ambiguous).
- **GES** (Chickering 2002): score-based (BIC / BDeu). Greedy
  equivalence search; returns a CPDAG like PC.
- **GRaSP** (Lam, Andrews, Ramsey 2022): permutation/score-based;
  returns a CPDAG, often more accurate than PC/GES on the same data.
- **LiNGAM** (Shimizu et al. 2006): assumes linear non-Gaussian.
  Returns a fully directed DAG when assumptions hold.

``algorithm="auto"`` runs a deterministic, reproducible selector over
measured data properties (``_diagnose_data`` → ``_select_algorithm``):
continuous + non-Gaussian + adequate N → LiNGAM; all-categorical → PC
with a chi-square CI test; otherwise PC with Fisher-Z. The choice is a
pure function of the data — a verifier can recompute the diagnostics
and re-derive the same algorithm. The selector also picks the
discrete-appropriate CI test / score function, so PC / GES are never
run with a Gaussian test on categorical data.

Pass ``n_bootstrap > 0`` to attach a per-edge stability score in
``[0, 1]`` (the fraction of row-resamples in which the edge appears).
That is a data-refit quantity — reproducible under a fixed seed but not
independently re-derivable — so it is surfaced as
``annotations.confidence`` on the proposal, not as a verified claim.

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
from typing import Callable, Literal

import numpy as np
import pandas as pd

from .contract import validate_data


AlgorithmName = Literal["pc", "fci", "lingam", "ges", "grasp", "auto"]


@dataclass(frozen=True)
class DataDiagnostics:
    """Measured properties of the data that drive algorithm selection.
    Recomputable from the data — this is what makes ``auto`` selection
    reproducible and auditable rather than an opaque heuristic."""

    n_samples: int
    n_variables: int
    n_continuous: int
    n_discrete: int
    n_bool: int
    frac_non_gaussian: float
    """Fraction of continuous columns that fail a normality test
    (D'Agostino K² at α=0.05; ``|skew| > 0.5`` fallback when N < 20).
    ``-1.0`` when there are no continuous columns."""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    """The resolved algorithm plus the CI test / score function chosen
    for the data type, and a human-readable rationale."""

    algorithm: str
    indep_test: str | None
    score_func: str | None
    rationale: str


@dataclass(frozen=True)
class AlgorithmSpec:
    """Declarative profile of one discovery algorithm — the single place
    that knows how to run it, its note, its precondition check, and when
    ``auto`` should pick it. Adding an algorithm is one entry here (plus a
    runner), not edits scattered across the selector, the note, and the
    violation checks. Themis's deterministic take on Causal-Copilot's
    algorithm knowledge base: rules over measured data properties, no LLM.
    """

    name: str
    run: Callable
    kind: str  # constraint | score | permutation | fcm
    uses_indep_test: bool = False
    score_continuous: str | None = None
    score_discrete: str | None = None
    note_clause: str = ""
    violations: Callable | None = None
    auto: Callable | None = None
    """None → never auto-selected (explicit only). Otherwise a function of
    ``DataDiagnostics`` returning ``(eligible, priority, rationale)``; the
    highest-priority eligible spec wins under ``algorithm='auto'``."""


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

    data_diagnostics: "DataDiagnostics | None" = None
    """Measured data properties that drove the algorithm choice."""
    selection_rationale: str = ""
    """Why this algorithm / CI test was chosen (human-readable)."""
    indep_test: str | None = None
    """CI test used by PC / FCI (``"fisherz"`` / ``"chisq"``)."""
    score_func: str | None = None
    """Score used by GES (``"local_score_BIC"`` / ``"local_score_BDeu"``)."""
    n_bootstrap: int = 0
    n_bootstrap_ok: int = 0
    """Resamples that ran without error (stability denominator)."""
    edge_confidence: tuple[tuple[str, str, float], ...] = ()
    """Per directed edge ``(src, dst, stability)`` — fraction of
    bootstrap resamples in which the edge appeared with this
    orientation. Empty unless ``n_bootstrap > 0``."""
    skeleton_confidence: tuple[tuple[str, str, float], ...] = ()
    """Per unordered pair ``(a, b, stability)`` — fraction of resamples
    in which the two variables were adjacent in any orientation."""


def discover_graph(
    data: pd.DataFrame,
    *,
    algorithm: AlgorithmName = "auto",
    alpha: float = 0.05,
    columns: tuple[str, ...] | None = None,
    random_state: int = 42,
    n_bootstrap: int = 0,
) -> DiscoveryResult:
    """Run a causal-discovery algorithm on ``data`` and return a
    structured suggestion.

    ``columns`` selects which DataFrame columns to use; defaults to
    all numeric / bool columns. ``algorithm='auto'`` runs the
    deterministic diagnostics-driven selector (``_select_algorithm``)
    and also picks the discrete-appropriate CI test / score function.

    ``n_bootstrap > 0`` re-runs the resolved algorithm on that many
    row-resamples (seeded off ``random_state``) and attaches a per-edge
    stability score in ``[0, 1]``; ``0`` (the default) skips it.
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

    diagnostics = _diagnose_data(df, cols)
    selection = _select_algorithm(algorithm, df, cols, diagnostics)

    # Coerce to numpy float matrix; bool → 0/1
    matrix = df.to_numpy(dtype=float)

    directed, bidirected, ambiguous = _run_resolved(
        matrix, cols, selection.algorithm,
        alpha=alpha, indep_test=selection.indep_test,
        score_func=selection.score_func, random_state=random_state,
    )

    edge_conf: tuple[tuple[str, str, float], ...] = ()
    skeleton_conf: tuple[tuple[str, str, float], ...] = ()
    n_ok = 0
    if n_bootstrap and n_bootstrap > 0:
        edge_conf, skeleton_conf, n_ok = _bootstrap_edge_confidence(
            matrix, cols, selection.algorithm,
            alpha=alpha, indep_test=selection.indep_test,
            score_func=selection.score_func, random_state=random_state,
            n_bootstrap=n_bootstrap,
        )

    note = _format_note(
        selection.algorithm, len(directed), len(bidirected), len(ambiguous),
    )
    violations = _detect_assumption_violations(
        selection.algorithm, df, contract.sample_size,
    )
    column_dtypes = tuple(
        (col, _classify_column(df[col])) for col in cols
    )

    return DiscoveryResult(
        directed_edges=directed,
        bidirected_edges=bidirected,
        ambiguous_edges=ambiguous,
        algorithm=selection.algorithm,
        alpha=alpha,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        columns=cols,
        note=note,
        assumption_violations=violations,
        column_dtypes=column_dtypes,
        data_diagnostics=diagnostics,
        selection_rationale=selection.rationale,
        indep_test=selection.indep_test,
        score_func=selection.score_func,
        n_bootstrap=int(n_bootstrap or 0),
        n_bootstrap_ok=n_ok,
        edge_confidence=edge_conf,
        skeleton_confidence=skeleton_conf,
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
    Delegates to the resolved algorithm's own ``violations`` check in the
    registry so each algorithm's preconditions live in one place.
    """
    spec = _ALGORITHMS.get(algorithm)
    if spec is None or spec.violations is None:
        return ()
    return spec.violations(df, sample_size)


# --- internals ----------------------------------------------------------------


def _diagnose_data(df: pd.DataFrame, cols: tuple[str, ...]) -> DataDiagnostics:
    """Measure the data properties the selector keys on. Deterministic
    and recomputable — the auditability of ``auto`` selection rests on
    this being a pure function of the data."""
    from scipy import stats

    types = {c: _classify_column(df[c]) for c in cols}
    n = len(df)
    n_cont = sum(1 for c in cols if types[c] == "continuous")
    n_disc = sum(1 for c in cols if types[c] == "discrete")
    n_bool = sum(1 for c in cols if types[c] == "bool")

    non_gauss = 0
    tested = 0
    for c in cols:
        if types[c] != "continuous":
            continue
        tested += 1
        col = df[c].to_numpy(dtype=float)
        try:
            if n >= 20:
                _, p = stats.normaltest(col)
                if p < 0.05:
                    non_gauss += 1
            elif abs(float(pd.Series(col).skew())) > 0.5:
                non_gauss += 1
        except Exception:
            # Degenerate column (e.g. zero variance) — can't judge; treat
            # as Gaussian so it doesn't spuriously trigger LiNGAM.
            pass
    frac_ng = (non_gauss / tested) if tested else -1.0

    notes: list[str] = []
    if n < 200:
        notes.append(
            f"sample size {n} is small; conditional-independence tests are "
            "low-power and the proposal is correspondingly less reliable"
        )
    if n_cont == 0:
        notes.append(
            "no continuous columns — LiNGAM is not applicable; a chi-square "
            "CI test is preferred over Fisher-Z"
        )
    return DataDiagnostics(
        n_samples=n,
        n_variables=len(cols),
        n_continuous=n_cont,
        n_discrete=n_disc,
        n_bool=n_bool,
        frac_non_gaussian=frac_ng,
        notes=tuple(notes),
    )


def _select_algorithm(
    algorithm: str,
    df: pd.DataFrame,
    cols: tuple[str, ...],
    diag: DataDiagnostics,
) -> Selection:
    """Resolve ``algorithm`` (honouring an explicit choice, or picking one
    under ``"auto"``) and choose the CI test / score function that matches
    the data type. Returns the choice plus a human-readable rationale.

    ``auto`` is deterministic: among the auto-eligible algorithms in the
    registry whose applicability matches the measured diagnostics, the
    highest-priority one wins. PC (fewest assumptions) is always eligible
    at priority 1, so a stronger method only wins when the data clearly
    supports it.
    """
    all_categorical = diag.n_continuous == 0

    if algorithm == "auto":
        best: tuple[int, str, str] | None = None
        for spec in _ALGORITHMS.values():
            if spec.auto is None:
                continue
            eligible, priority, rationale = spec.auto(diag)
            if eligible and (best is None or priority > best[0]):
                best = (priority, spec.name, rationale)
        if best is None:  # unreachable (PC always eligible) — defensive
            algo, why = "pc", "auto→PC (fallback)"
        else:
            _, algo, why = best
    else:
        algo = algorithm
        why = f"user-selected {algorithm.upper()}"

    spec = _ALGORITHMS.get(algo)
    indep_test: str | None = None
    score_func: str | None = None
    if spec is not None:
        if spec.uses_indep_test:
            indep_test = "chisq" if all_categorical else "fisherz"
            if all_categorical:
                why += "; chi-square CI test chosen for categorical data"
        if spec.score_continuous is not None:
            score_func = (
                spec.score_discrete
                if all_categorical and spec.score_discrete
                else spec.score_continuous
            )
            if all_categorical and spec.score_discrete:
                why += "; BDeu score chosen for categorical data"

    return Selection(
        algorithm=algo,
        indep_test=indep_test,
        score_func=score_func,
        rationale=why,
    )


def _run_resolved(
    matrix, cols, resolved, *,
    alpha, indep_test, score_func, random_state,
):
    """Dispatch to the resolved algorithm's runner via the registry.
    Shared by the main run and each bootstrap resample so they use
    identical settings."""
    spec = _ALGORITHMS.get(resolved)
    if spec is None:
        raise ValueError(f"unknown algorithm {resolved!r}")
    return spec.run(
        matrix, cols,
        alpha=alpha, indep_test=indep_test,
        score_func=score_func, random_state=random_state,
    )


# All runners share one signature (matrix, cols, *, alpha, indep_test,
# score_func, random_state) and ignore what they don't need, so the
# registry can call any of them uniformly.


def _run_pc(matrix, cols, *, alpha=0.05, indep_test="fisherz", score_func=None, random_state=None):
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.graph.Endpoint import Endpoint

    result = pc(
        matrix, alpha=alpha, indep_test=indep_test or "fisherz",
        show_progress=False, node_names=list(cols),
    )
    return _extract_edges(result.G, cols, Endpoint)


def _run_fci(matrix, cols, *, alpha=0.05, indep_test="fisherz", score_func=None, random_state=None):
    from causallearn.search.ConstraintBased.FCI import fci
    from causallearn.graph.Endpoint import Endpoint

    g, edges = fci(
        matrix, independence_test_method=indep_test or "fisherz", alpha=alpha,
        verbose=False, show_progress=False, node_names=list(cols),
    )
    return _extract_edges(g, cols, Endpoint)


def _run_ges(matrix, cols, *, alpha=None, indep_test=None, score_func="local_score_BIC", random_state=None):
    from causallearn.search.ScoreBased.GES import ges
    from causallearn.graph.Endpoint import Endpoint

    record = ges(
        matrix, score_func=score_func or "local_score_BIC", node_names=list(cols),
    )
    return _extract_edges(record["G"], cols, Endpoint)


def _run_grasp(matrix, cols, *, alpha=None, indep_test=None, score_func="local_score_BIC_from_cov", random_state=None):
    from causallearn.search.PermutationBased.GRaSP import grasp
    from causallearn.graph.Endpoint import Endpoint

    g = grasp(
        matrix, score_func=score_func or "local_score_BIC_from_cov",
        depth=3, verbose=False, node_names=list(cols),
    )
    return _extract_edges(g, cols, Endpoint)


def _run_lingam(matrix, cols, *, alpha=None, indep_test=None, score_func=None, random_state=42):
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


# --- algorithm registry (the "knowledge base") --------------------------------


def _viol_citest_small_n(df, n):
    if n < 200:
        return (
            f"sample size {n} < 200 — conditional independence tests have "
            "low power; expect spurious edges and missed edges",
        )
    return ()


def _viol_score_small_n(df, n):
    if n < 200:
        return (
            f"sample size {n} < 200 — the BIC / BDeu score is unstable at "
            "small N; the returned graph is unreliable",
        )
    return ()


def _viol_lingam(df, n):
    numeric = df.select_dtypes(include=[np.number])
    if numeric.empty:
        return ()
    max_abs_skew = float(numeric.apply(lambda s: float(s.skew())).abs().max())
    if max_abs_skew < 0.5:
        return (
            f"data appears Gaussian (max |skew| = {max_abs_skew:.2f} < 0.5); "
            "LiNGAM identifiability requires non-Gaussian noise — "
            "edge directions on Gaussian data are essentially arbitrary",
        )
    return ()


def _auto_pc(diag: DataDiagnostics):
    """PC is always the fewest-assumption fallback (priority 1)."""
    if diag.n_continuous == 0:
        return (True, 1, (
            "auto→PC: all variables are categorical/discrete, so a "
            "chi-square conditional-independence test is used"
        ))
    return (True, 1, (
        "auto→PC: data is continuous and not clearly non-Gaussian (or N is "
        "below the LiNGAM threshold); PC with Fisher-Z makes the fewest "
        "parametric assumptions"
    ))


def _auto_lingam(diag: DataDiagnostics):
    """LiNGAM wins (priority 10) only when the data clearly supports it:
    continuous, non-Gaussian, and enough samples to orient edges."""
    mostly_continuous = diag.n_continuous >= max(1, diag.n_variables // 2 + 1)
    non_gaussian = diag.frac_non_gaussian >= 0.5
    if mostly_continuous and non_gaussian and diag.n_samples >= 500:
        return (True, 10, (
            f"auto→LiNGAM: {diag.frac_non_gaussian:.0%} of continuous "
            f"variables fail a normality test and N={diag.n_samples}≥500, "
            "so non-Gaussian noise can fully orient the edges"
        ))
    return (False, 0, "")


# One entry per algorithm; adding a new algorithm is a runner + one row.
_ALGORITHMS: dict[str, AlgorithmSpec] = {
    "pc": AlgorithmSpec(
        name="pc", run=_run_pc, kind="constraint",
        uses_indep_test=True,
        note_clause="PC assumes no latent confounders; consider FCI if that is wrong",
        violations=_viol_citest_small_n, auto=_auto_pc,
    ),
    "fci": AlgorithmSpec(
        name="fci", run=_run_fci, kind="constraint",
        uses_indep_test=True,
        note_clause="FCI allows latent confounders; CIRCLE endpoints denote ambiguous orientation",
        violations=_viol_citest_small_n, auto=None,
    ),
    "ges": AlgorithmSpec(
        name="ges", run=_run_ges, kind="score",
        score_continuous="local_score_BIC", score_discrete="local_score_BDeu",
        note_clause="GES is score-based (BIC/BDeu); returns a CPDAG — orientation only within the equivalence class",
        violations=_viol_score_small_n, auto=None,
    ),
    "grasp": AlgorithmSpec(
        name="grasp", run=_run_grasp, kind="permutation",
        score_continuous="local_score_BIC_from_cov", score_discrete="local_score_BDeu",
        note_clause="GRaSP is permutation-based (score-guided); returns a CPDAG, often more accurate than PC/GES on the same data",
        violations=_viol_score_small_n, auto=None,
    ),
    "lingam": AlgorithmSpec(
        name="lingam", run=_run_lingam, kind="fcm",
        note_clause="LiNGAM assumes linear non-Gaussian noise; weak signal under Gaussian data",
        violations=_viol_lingam, auto=_auto_lingam,
    ),
}


def _bootstrap_edge_confidence(
    matrix, cols, resolved, *,
    alpha, indep_test, score_func, random_state, n_bootstrap,
):
    """Re-run ``resolved`` on ``n_bootstrap`` row-resamples and tally how
    often each edge appears. Child seeds are drawn from one generator
    seeded by ``random_state``, so the stability scores are reproducible.
    Resamples that error out are skipped and excluded from the denominator.

    Returns ``(edge_confidence, skeleton_confidence, n_ok)`` — the two
    confidence tuples are sorted ``(a, b, fraction)`` triples: directed
    orientation frequency and undirected-adjacency frequency respectively.
    """
    rng = np.random.default_rng(random_state)
    n = matrix.shape[0]
    seeds = rng.integers(1, 2**31 - 1, size=n_bootstrap)
    directed_counts: dict[tuple[str, str], int] = {}
    adjacency_counts: dict[frozenset, int] = {}
    n_ok = 0
    for s in seeds:
        idx = np.random.default_rng(int(s)).integers(0, n, size=n)
        boot = matrix[idx]
        try:
            directed, bidirected, ambiguous = _run_resolved(
                boot, cols, resolved,
                alpha=alpha, indep_test=indep_test,
                score_func=score_func, random_state=random_state,
            )
        except Exception:
            continue
        n_ok += 1
        adjacent: set = set()
        for edge in directed:
            directed_counts[edge] = directed_counts.get(edge, 0) + 1
            adjacent.add(frozenset(edge))
        for pair in (*bidirected, *ambiguous):
            adjacent.add(pair)
        for pair in adjacent:
            adjacency_counts[pair] = adjacency_counts.get(pair, 0) + 1

    denom = n_ok or 1
    edge_conf = tuple(sorted(
        (src, dst, count / denom)
        for (src, dst), count in directed_counts.items()
    ))
    skeleton_conf = tuple(sorted(
        (min(pair), max(pair), count / denom)
        for pair, count in adjacency_counts.items()
    ))
    return edge_conf, skeleton_conf, n_ok


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

    # Bootstrap stability lookups (empty unless n_bootstrap was set)
    directed_conf = {(s, d): c for s, d, c in result.edge_confidence}
    skeleton_conf = {frozenset((a, b)): c for a, b, c in result.skeleton_confidence}

    def _edge_annotations(*, orientation_key, skeleton_key):
        ann = {"source": f"discovery:{result.algorithm}"}
        conf = directed_conf.get(orientation_key)
        if conf is None:
            conf = skeleton_conf.get(skeleton_key)
        if conf is not None:
            ann["confidence"] = round(float(conf), 4)
        return ann

    # 2. Directed cause edges
    args = [{"type": "const", "name": s} for s in domain_subjects]
    for src, dst in result.directed_edges:
        statements.append({
            "kind": "cause",
            "from": {"predicate": src, "args": args},
            "to": {"predicate": dst, "args": args},
            "annotations": _edge_annotations(
                orientation_key=(src, dst),
                skeleton_key=frozenset((src, dst)),
            ),
        })

    # 3. Bidirected (latent confounder) edges from FCI
    for pair in result.bidirected_edges:
        a, b = sorted(pair)
        statements.append({
            "kind": "bidirected",
            "left": {"predicate": a, "args": args},
            "right": {"predicate": b, "args": args},
            "annotations": _edge_annotations(
                orientation_key=(a, b),
                skeleton_key=frozenset((a, b)),
            ),
        })

    # 4. Optional query statement
    if query is not None:
        statements.append(query)

    # 5. Ambiguities for each undirected / partially-oriented edge
    ambiguities: list[dict] = []
    for pair in result.ambiguous_edges:
        entry = {
            "kind": "ambiguous_orientation",
            "endpoints": sorted(pair),
            "discovery_algorithm": result.algorithm,
            "disambiguation_ask": (
                f"算法 {result.algorithm.upper()} 找到 {sorted(pair)[0]} "
                f"和 {sorted(pair)[1]} 之间存在因果关联，但从数据无法判定"
                "方向。你能根据领域知识告诉我方向吗？"
            ),
        }
        conf = skeleton_conf.get(frozenset(pair))
        if conf is not None:
            entry["skeleton_confidence"] = round(float(conf), 4)
        ambiguities.append(entry)

    diagnostics_block = None
    if result.data_diagnostics is not None:
        d = result.data_diagnostics
        diagnostics_block = {
            "n_samples": d.n_samples,
            "n_variables": d.n_variables,
            "n_continuous": d.n_continuous,
            "n_discrete": d.n_discrete,
            "n_bool": d.n_bool,
            "frac_non_gaussian": d.frac_non_gaussian,
            "notes": list(d.notes),
        }

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
            "selection_rationale": result.selection_rationale,
            "indep_test": result.indep_test,
            "score_func": result.score_func,
            "n_bootstrap": result.n_bootstrap,
            "n_bootstrap_ok": result.n_bootstrap_ok,
            "diagnostics": diagnostics_block,
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
    spec = _ALGORITHMS.get(algorithm)
    if spec is not None and spec.note_clause:
        parts.append(spec.note_clause)
    if n_amb > 0 and algorithm != "lingam":
        parts.append(
            f"{n_amb} edges are not orientable from observational data alone "
            "— user / domain knowledge required to direct them"
        )
    return "; ".join(parts)
