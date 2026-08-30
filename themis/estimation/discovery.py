"""Phase 8.1 — causal discovery wrapper around causal-learn.

Six algorithms (one ``AlgorithmSpec`` registry entry each):
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
- **NOTEARS** (Zheng et al. 2018): the combinatorial acyclicity
  constraint written as one smooth equality, so the search becomes
  continuous optimisation. Returns a weighted DAG. Explicit only —
  see :mod:`themis.estimation.notears` for the certificate and the
  scale diagnostic that travel with it.

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
from typing import Callable, Literal, get_args

import numpy as np
import pandas as pd

from .contract import integer_valued, validate_data
from .discovery_words import Blanket, said
from .refusal_words import Refuses
from .notears import NotearsCertificate, ScaleDiagnostic, fit_notears
from .. import language
from ..language import Statement
from ..types import envelope_scalar


AlgorithmName = Literal[
    "pc", "fci", "lingam", "ges", "grasp", "notears", "auto",
]

# The same vocabulary as data. Derived from the type rather than written
# twice, so the runtime check and the declared contract cannot drift.
ALGORITHM_NAMES: tuple[AlgorithmName, ...] = get_args(AlgorithmName)


def as_algorithm_name(value: str) -> AlgorithmName:
    """Return ``value`` as an :data:`AlgorithmName`, or raise ``ValueError``.

    A text boundary — an MCP tool argument, a CLI flag — holds a free-form
    ``str``, while the algorithm registry is keyed by this closed
    vocabulary. This is where one becomes the other: an unrecognised name
    is refused here, naming the accepted ones, rather than travelling as
    an ordinary string until the dispatch in ``_run_resolved`` rejects it.
    """
    if value in ALGORITHM_NAMES:
        return value
    raise ValueError(
        f"unknown discovery algorithm {value!r}; expected one of "
        + ", ".join(ALGORITHM_NAMES)
    )

# Past this many distinct values a level-coded column stops being usable as a
# stratum set for a chi-square CI test and is treated as a measurement.
_MAX_DISCRETE_LEVELS = 20


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
    notes: tuple[Statement, ...] = ()
    """What the measurements say about themselves, as statements rather
    than as sentences: which one, plus this occasion's numbers."""


@dataclass(frozen=True)
class Selection:
    """The resolved algorithm plus the CI test / score function chosen
    for the data type, and why."""

    algorithm: str
    indep_test: str | None
    score_func: str | None
    rationale: tuple[Statement, ...]
    """Why this algorithm, and why this test — one statement each. Two
    facts, so two statements: the selector picks an algorithm and then
    picks a test for the data type, and a single string had to concatenate
    them with a separator chosen in whichever language it was written in."""


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
    kind: str  # constraint | score | permutation | fcm | continuous
    source: str = "causal-learn"
    """Who computed the graph. Five of the six are wrapped; the note said
    "causal-learn" for all of them, which stopped being provenance the
    moment one of them was written here."""
    uses_indep_test: bool = False
    score_continuous: str | None = None
    score_discrete: str | None = None
    note_clause: str = ""
    """Which sentence in :mod:`themis.estimation.discovery_words` says what
    this algorithm is. A TOKEN and not the sentence: an algorithm's row is
    the same in every language, and the row is not where a language gets
    decided."""
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
    - ``data_columns``: what that digest is OF
    - ``columns``: the order the algorithm indexed the variables in
    - ``note``: human-readable summary
    """

    directed_edges: tuple[tuple[str, str], ...]
    bidirected_edges: tuple[frozenset[str], ...]
    ambiguous_edges: tuple[frozenset[str], ...]
    algorithm: str
    alpha: float
    sample_size: int
    data_hash: str

    data_columns: tuple[str, ...]
    """The columns ``data_hash`` was taken over, in the order it
    walked them: sorted, because that is the order the contract
    subsets the frame into before hashing. Spelled the way every other
    digest spells its denominator, and it is the same fact — what the
    fingerprint is OF.

    The same members as ``columns`` in a different order, which is why
    they are two fields: a digest is reproduced by walking its own
    order, a matrix is read by walking the other one."""

    columns: tuple[str, ...]
    """The order the variables were handed to the algorithm, and
    therefore the order everything downstream is indexed by.

    Not canonical and not the digest's — the caller's order, or the
    frame's when the caller named none. It once said canonical,
    which is a third answer and was true of neither."""

    note: tuple[Statement, ...]
    """What the run says about itself, one statement per sentence. What
    goes between two of them is a fact about the language, so they are
    joined where the reader is rather than here."""

    assumption_violations: tuple[Statement, ...] = ()
    """Empirically detected violations of the algorithm's preconditions
    (e.g. Gaussian data on LiNGAM, sub-threshold sample size). Surfaces
    through ``extensions.discovery_metadata`` so the
    ``graph_learned_from_data`` caveat names *which* algorithm
    assumptions look unsafe on the actual data, not just which
    assumptions the algorithm requires in principle — and it names them
    as statements, so that caveat can put them inside its own sentence in
    the reader's language instead of pasting a rendered list into it."""

    column_dtypes: tuple[tuple[str, str], ...] = ()
    """Per-column classification: ``"bool"`` (≤2 unique values),
    ``"discrete"`` (3 to ``_MAX_DISCRETE_LEVELS`` integer-coded values),
    ``"continuous"`` (more, or non-integer). Used by
    ``discovery_to_kernel_ast`` to validate caller-supplied
    ``bool_predicates`` against the actual data shape — flagging a column
    as bool when it has 100 unique values produces a kernel_ast that's
    syntactically valid but semantically lying. Also read by the NL bridge,
    which asks the user to discretise a ``continuous`` column, so a
    misclassification here becomes a question about a column that already
    has levels."""

    data_diagnostics: "DataDiagnostics | None" = None
    """Measured data properties that drove the algorithm choice."""
    selection_rationale: tuple[Statement, ...] = ()
    """Why this algorithm, and why this test — one statement each."""
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

    notears_weights: tuple[tuple[float, ...], ...] = ()
    """The pre-threshold solution, indexed by ``columns`` both ways:
    ``[i][j]`` is the weight of ``columns[i] → columns[j]``. Empty unless
    the resolved algorithm was NOTEARS. The edges in ``directed_edges``
    are this matrix read at ``notears_certificate.threshold``, which is
    why the matrix and not a second thresholded copy is what is kept."""
    notears_certificate: NotearsCertificate | None = None
    """What can be re-derived about a solution nobody can replay: the
    acyclicity residual, the objective, and the first-order residual, all
    recomputable from the recorded Gram matrix alone."""
    notears_scale: ScaleDiagnostic | None = None
    """Whether this answer came from the structure or from the scales
    (Reisach et al. 2021), edge by edge."""


class DiscoveryError(language.Voiced, ValueError):
    """The whole-graph search cannot be run as asked — no column is
    usable, the named algorithm is not one of the six, the artifact
    handed to a serialiser came from a different one.

    The third of this module's three searches to have a channel, and
    the last: the local one has :class:`MarkovBlanketError` and the
    lagged one :class:`LaggedDiscoveryError`, and the main one raised a
    bare ``ValueError`` with its sentence written in. That is the same
    root cause as the sentences — a carrier written out per package
    made a fourth exception class expensive, so the cheap thing was to
    reach for a builtin and put the wording at the site.

    ``ValueError`` as well, which is what these three raised before and
    so what a caller has been able to catch.
    """


def discover_graph(
    data: pd.DataFrame,
    *,
    algorithm: AlgorithmName = "auto",
    alpha: float = 0.05,
    columns: tuple[str, ...] | None = None,
    random_state: int = 42,
    n_bootstrap: int = 0,
    l1: float | None = None,
    threshold: float | None = None,
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

    ``l1`` and ``threshold`` are NOTEARS's two knobs, threaded the way
    ``alpha`` and ``score_func`` already are: every runner takes the whole
    settings vocabulary and ignores what its family has no use for. Left
    at ``None`` they are the paper's defaults.
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
        raise DiscoveryError(Refuses.NO_USABLE_COLUMNS)

    contract = validate_data(data, required_columns=set(cols))
    df = contract.data[list(cols)]

    diagnostics = _diagnose_data(df, cols)
    selection = _select_algorithm(algorithm, df, cols, diagnostics)

    # Coerce to numpy float matrix; bool → 0/1
    matrix = df.to_numpy(dtype=float)

    directed, bidirected, ambiguous, fit = _run_resolved(
        matrix, cols, selection.algorithm,
        alpha=alpha, indep_test=selection.indep_test,
        score_func=selection.score_func, random_state=random_state,
        l1=l1, threshold=threshold,
    )

    edge_conf: tuple[tuple[str, str, float], ...] = ()
    skeleton_conf: tuple[tuple[str, str, float], ...] = ()
    n_ok = 0
    if n_bootstrap and n_bootstrap > 0:
        edge_conf, skeleton_conf, n_ok = _bootstrap_edge_confidence(
            matrix, cols, selection.algorithm,
            alpha=alpha, indep_test=selection.indep_test,
            score_func=selection.score_func, random_state=random_state,
            n_bootstrap=n_bootstrap, l1=l1, threshold=threshold,
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
        data_columns=contract.columns,
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
        notears_weights=() if fit is None else fit.weights,
        notears_certificate=None if fit is None else fit.certificate,
        notears_scale=None if fit is None else fit.scale,
    )


def _classify_column(series: pd.Series) -> str:
    """Per-column classification driving the CI-test choice and, later, the
    validation of caller-supplied ``bool_predicates``. Two unique values is
    bool; up to ``_MAX_DISCRETE_LEVELS`` level-coded values is discrete;
    anything else is continuous.

    Level-codedness is read off the VALUES, never the dtype, and the
    reading is :func:`contract.integer_valued` — the contract widens every
    integer column to float64 before this sees it, so the fact belongs
    beside that cast and not in a copy here.
    """
    values = series.dropna()
    n_unique = int(values.nunique())
    if n_unique <= 2:
        return "bool"
    if n_unique > _MAX_DISCRETE_LEVELS:
        return "continuous"
    if not pd.api.types.is_numeric_dtype(values):
        return "discrete"  # labels are levels by construction
    return "discrete" if integer_valued(values) else "continuous"


def _detect_assumption_violations(
    algorithm: str,
    df: pd.DataFrame,
    sample_size: int,
) -> tuple[Statement, ...]:
    """Empirically check the data against the algorithm's preconditions.
    Returns one statement per violation — an empty tuple if none was
    detected.

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

    notes: list[Statement] = []
    if n < 200:
        notes.append(said("the_sample_is_small_for_a_test", n=n))
    if n_cont == 0:
        notes.append(said("no_column_is_continuous"))
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
        best: tuple[int, str, Statement] | None = None
        # ``candidate`` is one algorithm being scanned; ``spec`` below is
        # the one that won — two different things, so two names.
        for candidate in _ALGORITHMS.values():
            if candidate.auto is None:
                continue
            eligible, priority, rationale = candidate.auto(diag)
            if eligible and (best is None or priority > best[0]):
                best = (priority, candidate.name, rationale)
        if best is None:  # unreachable (PC always eligible) — defensive
            algo, why = "pc", said("auto_fell_back_to_pc")
        else:
            _, algo, why = best
    else:
        algo = algorithm
        why = said("you_chose_this_algorithm", algorithm=algorithm.upper())

    because: list[Statement] = [why]
    spec = _ALGORITHMS.get(algo)
    indep_test: str | None = None
    score_func: str | None = None
    if spec is not None:
        if spec.uses_indep_test:
            indep_test = "chisq" if all_categorical else "fisherz"
            if all_categorical:
                because.append(
                    said("chi_square_because_the_data_are_categorical"))
        if spec.score_continuous is not None:
            score_func = (
                spec.score_discrete
                if all_categorical and spec.score_discrete
                else spec.score_continuous
            )
            if all_categorical and spec.score_discrete:
                because.append(
                    said("bdeu_because_the_data_are_categorical"))

    return Selection(
        algorithm=algo,
        indep_test=indep_test,
        score_func=score_func,
        rationale=tuple(because),
    )


def _run_resolved(
    matrix, cols, resolved, *,
    alpha, indep_test, score_func, random_state, l1=None, threshold=None,
):
    """Dispatch to the resolved algorithm's runner via the registry.
    Shared by the main run and each bootstrap resample so they use
    identical settings."""
    spec = _ALGORITHMS.get(resolved)
    if spec is None:
        raise DiscoveryError(Refuses.METHOD_IS_LIMITED_TO,
                             given=resolved, offered=sorted(_ALGORITHMS))
    return spec.run(
        matrix, cols,
        alpha=alpha, indep_test=indep_test,
        score_func=score_func, random_state=random_state,
        l1=l1, threshold=threshold,
    )


# All runners share one signature (matrix, cols, *, alpha, indep_test,
# score_func, random_state, l1, threshold) and ignore what they don't need,
# so the registry can call any of them uniformly. They also share a return
# shape: (directed, bidirected, ambiguous, fit), where ``fit`` is whatever
# the algorithm can say about its own answer beyond the edge buckets and is
# ``None`` for the five that can say nothing.


def _run_pc(matrix, cols, *, alpha=0.05, indep_test="fisherz", score_func=None, random_state=None, l1=None, threshold=None):
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.graph.Endpoint import Endpoint

    result = pc(
        matrix, alpha=alpha, indep_test=indep_test or "fisherz",
        show_progress=False, node_names=list(cols),
    )
    return (*_extract_edges(result.G, cols, Endpoint), None)


def _run_fci(matrix, cols, *, alpha=0.05, indep_test="fisherz", score_func=None, random_state=None, l1=None, threshold=None):
    from causallearn.search.ConstraintBased.FCI import fci
    from causallearn.graph.Endpoint import Endpoint

    g, edges = fci(
        matrix, independence_test_method=indep_test or "fisherz", alpha=alpha,
        verbose=False, show_progress=False, node_names=list(cols),
    )
    return (*_extract_edges(g, cols, Endpoint), None)


def _run_ges(matrix, cols, *, alpha=None, indep_test=None, score_func="local_score_BIC", random_state=None, l1=None, threshold=None):
    from causallearn.search.ScoreBased.GES import ges
    from causallearn.graph.Endpoint import Endpoint

    record = ges(
        matrix, score_func=score_func or "local_score_BIC", node_names=list(cols),
    )
    return (*_extract_edges(record["G"], cols, Endpoint), None)


def _run_grasp(matrix, cols, *, alpha=None, indep_test=None, score_func="local_score_BIC_from_cov", random_state=None, l1=None, threshold=None):
    from causallearn.search.PermutationBased.GRaSP import grasp
    from causallearn.graph.Endpoint import Endpoint

    g = grasp(
        matrix, score_func=score_func or "local_score_BIC_from_cov",
        depth=3, verbose=False, node_names=list(cols),
    )
    return (*_extract_edges(g, cols, Endpoint), None)


def _run_lingam(matrix, cols, *, alpha=None, indep_test=None, score_func=None, random_state=42, l1=None, threshold=None):
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
    return tuple(directed), (), (), None


def _run_notears(matrix, cols, *, alpha=None, indep_test=None, score_func=None, random_state=None, l1=None, threshold=None):
    """The one runner written here rather than wrapped.

    NOTEARS has no ambiguous bucket and no bidirected one: it returns a
    weighted DAG, every edge oriented, because the acyclicity constraint is
    what it optimises rather than what it reads off a conditional
    independence. That is a stronger claim than PC's CPDAG, resting on a
    stronger assumption — a linear SCM — and the certificate travelling
    beside it is the price of making the claim.
    """
    fit = fit_notears(
        matrix, tuple(cols),
        **({} if l1 is None else {"l1": float(l1)}),
        **({} if threshold is None else {"threshold": float(threshold)}),
    )
    return fit.directed_edges, (), (), fit


# --- algorithm registry (the "knowledge base") --------------------------------


def _viol_citest_small_n(df, n):
    if n < 200:
        return (said("a_test_of_independence_needs_more_rows", n=n),)
    return ()


def _viol_score_small_n(df, n):
    if n < 200:
        return (said("a_score_needs_more_rows", n=n),)
    return ()


def _viol_lingam(df, n):
    """LiNGAM assumes a linear SEM over CONTINUOUS variables with
    non-Gaussian noise. Both halves are asked of the values: a dtype filter
    here would drop bool columns from the frame entirely — reporting no
    violation for the frame that violates the assumption most — and would
    call a widened integer code continuous."""
    level_coded = tuple(
        c for c in df.columns if _classify_column(df[c]) != "continuous"
    )
    if level_coded:
        return (said("lingam_was_given_level_codes",
                     columns=list(level_coded)),)
    max_abs_skew = float(df.apply(lambda s: float(s.skew())).abs().max())
    if max_abs_skew < 0.5:
        return (said("lingam_was_given_gaussian_data",
                     skew=round(max_abs_skew, 2)),)
    return ()


def _viol_notears(df, n):
    """NOTEARS fits a linear SCM by least squares, so its preconditions are
    asked of the values the same way LiNGAM's are — and one more besides.

    Reisach, Seiler & Weichwald (2021) showed the method exploits the
    marginal variances: when they happen to rise along the causal order,
    sorting by variance alone reproduces the graph, and the search gets
    credit for it. That is not detectable after the fact from a good-looking
    answer, so the spread is reported BEFORE the run as what it is — a
    reason the returned orientation may be about the units the columns were
    recorded in. The per-edge check in ``ScaleDiagnostic`` then says which
    edges survived removing them.
    """
    out: list[Statement] = []
    level_coded = tuple(
        c for c in df.columns if _classify_column(df[c]) != "continuous"
    )
    if level_coded:
        out.append(said("notears_was_given_level_codes",
                        columns=list(level_coded)))
    variances = df.var(axis=0)
    positive = variances[variances > 0]
    if len(positive) >= 2:
        spread = float(positive.max() / positive.min())
        if spread >= 10.0:
            out.append(said("notears_reads_the_variance_order",
                            spread=round(spread)))
    if n < 200:
        out.append(said("least_squares_needs_more_rows", n=n))
    return tuple(out)


def _auto_pc(diag: DataDiagnostics):
    """PC is always the fewest-assumption fallback (priority 1)."""
    if diag.n_continuous == 0:
        return (True, 1,
                said("auto_chose_pc_because_everything_is_categorical"))
    return (True, 1, said("auto_chose_pc_for_the_fewest_assumptions"))


def _auto_lingam(diag: DataDiagnostics):
    """LiNGAM wins (priority 10) only when the data clearly supports it:
    continuous, non-Gaussian, and enough samples to orient edges."""
    mostly_continuous = diag.n_continuous >= max(1, diag.n_variables // 2 + 1)
    non_gaussian = diag.frac_non_gaussian >= 0.5
    if mostly_continuous and non_gaussian and diag.n_samples >= 500:
        return (True, 10, said(
            "auto_chose_lingam",
            fraction=f"{diag.frac_non_gaussian:.0%}", n=diag.n_samples))
    return (False, 0, None)


# One entry per algorithm; adding a new algorithm is a runner + one row.
_ALGORITHMS: dict[str, AlgorithmSpec] = {
    "pc": AlgorithmSpec(
        name="pc", run=_run_pc, kind="constraint",
        uses_indep_test=True,
        note_clause="pc_assumes_no_latent_confounder",
        violations=_viol_citest_small_n, auto=_auto_pc,
    ),
    "fci": AlgorithmSpec(
        name="fci", run=_run_fci, kind="constraint",
        uses_indep_test=True,
        note_clause="fci_allows_latent_confounders",
        violations=_viol_citest_small_n, auto=None,
    ),
    "ges": AlgorithmSpec(
        name="ges", run=_run_ges, kind="score",
        score_continuous="local_score_BIC", score_discrete="local_score_BDeu",
        note_clause="ges_scores_an_equivalence_class",
        violations=_viol_score_small_n, auto=None,
    ),
    "grasp": AlgorithmSpec(
        name="grasp", run=_run_grasp, kind="permutation",
        score_continuous="local_score_BIC_from_cov", score_discrete="local_score_BDeu",
        note_clause="grasp_permutes_to_an_equivalence_class",
        violations=_viol_score_small_n, auto=None,
    ),
    "lingam": AlgorithmSpec(
        name="lingam", run=_run_lingam, kind="fcm",
        note_clause="lingam_orients_by_non_gaussian_noise",
        violations=_viol_lingam, auto=_auto_lingam,
    ),
    "notears": AlgorithmSpec(
        name="notears", run=_run_notears, kind="continuous", source="themis",
        note_clause="notears_optimises_a_smooth_constraint",
        violations=_viol_notears, auto=None,
    ),
}


def _bootstrap_edge_confidence(
    matrix, cols, resolved, *,
    alpha, indep_test, score_func, random_state, n_bootstrap,
    l1=None, threshold=None,
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
            directed, bidirected, ambiguous, _fit = _run_resolved(
                boot, cols, resolved,
                alpha=alpha, indep_test=indep_test,
                score_func=score_func, random_state=random_state,
                l1=l1, threshold=threshold,
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


class DomainMismatchError(language.Voiced, ValueError):
    """Caller declared a column as bool but the data has more than two
    unique values. Refusing to emit a syntactically-valid-but-lying
    kernel_ast is preferred over running structural reasoning over a
    domain that doesn't match the data.

    A :class:`themis.language.Voiced`: it carries the species and this
    occasion's facts, and the sentence is
    :class:`themis.estimation.refusal_words.Refuses`' rather than the
    raise site's. ``ValueError`` as well, because that is what a caller
    has always been able to catch.
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
        raise DomainMismatchError(
            Refuses.DECLARED_BOOL_HAS_MORE_LEVELS,
            columns=[f"{col} ({dtypes_lookup.get(col, '?')})"
                     for col in mismatched])

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
        entry: dict[str, object] = {
            "kind": "ambiguous_orientation",
            "endpoints": sorted(pair),
            "discovery_algorithm": result.algorithm,
            "disambiguation_ask": said(
                "which_way_between_these_two",
                algorithm=result.algorithm.upper(),
                one=sorted(pair)[0], other=sorted(pair)[1],
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
            "notes": [dict(note) for note in d.notes],
        }

    extensions: dict[str, object] = {
        "discovery_metadata": {
            "algorithm": result.algorithm,
            "alpha": result.alpha,
            "sample_size": result.sample_size,
            "data_hash": result.data_hash,
            "data_columns": list(result.data_columns),
            "columns": list(result.columns),
            "note": [dict(one) for one in result.note],
            "assumption_violations": [
                dict(one) for one in result.assumption_violations],
            "column_dtypes": {col: dt for col, dt in result.column_dtypes},
            "selection_rationale": [
                dict(one) for one in result.selection_rationale],
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


def notears_fit_to_dict(result: DiscoveryResult) -> dict:
    """The verifiable view of a NOTEARS run — the artifact
    :func:`themis.verify_notears_fit` consumes.

    Separate from :func:`discovery_to_kernel_ast` rather than folded into
    its ``discovery_metadata``, because the two answer different questions.
    The kernel_ast is a *suggestion*: these edges, from this algorithm, for
    a human to accept or reject. This is a *claim*: at these weights, with
    this Gram matrix, the acyclicity residual is that, the objective is
    that, and the first-order residual is that — every one of them
    recomputable by something that never ran the solver. Carrying the
    second inside the first would put a checkable claim inside a document
    whose whole point is that nothing in it is checkable yet.
    """
    if result.algorithm != "notears" or result.notears_certificate is None:
        raise DiscoveryError(Refuses.ARTIFACT_HAS_NO_CERTIFICATE,
                             algorithm=result.algorithm)
    cert = result.notears_certificate
    scale = result.notears_scale
    assert scale is not None  # produced together or not at all
    d = {
        "kind": "notears_fit",
        "columns": list(result.columns),
        "data_columns": list(result.data_columns),
        "sample_size": result.sample_size,
        "data_hash": result.data_hash,
        "weights": [list(row) for row in result.notears_weights],
        "gram": [list(row) for row in cert.gram],
        "l1_penalty": cert.l1_penalty,
        "threshold": cert.threshold,
        "multiplier": cert.multiplier,
        "rho": cert.rho,
        "iterations": cert.iterations,
        "acyclicity": cert.acyclicity,
        "objective": cert.objective,
        "stationarity": cert.stationarity,
        "directed_edges": [
            [src, dst] for src, dst in result.directed_edges],
        "varsortability": scale.varsortability,
        "n_paths": scale.n_paths,
        "edges_standardised": scale.edges_standardised,
        "survives_standardising": [
            [src, dst] for src, dst in scale.survives_standardising],
        "assumption_violations": [
            dict(one) for one in result.assumption_violations],
        "note": [dict(one) for one in result.note],
    }
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact(d)


def _format_note(algorithm: str, n_dir: int, n_bidir: int,
                 n_amb: int) -> tuple[Statement, ...]:
    """What the run says about itself: what it found, what the algorithm is,
    and — where any edge is left undirected — that somebody has to point it.

    A tuple rather than one joined string. What goes between two sentences
    is a fact about the language, so the joining belongs where the reader
    is; the separator here was an ASCII semicolon in front of Chinese."""
    spec = _ALGORITHMS.get(algorithm)
    parts = [said(
        "found_this_many_edges",
        source=spec.source if spec is not None else "causal-learn",
        algorithm=algorithm.upper(),
        directed=n_dir, bidirected=n_bidir, ambiguous=n_amb,
    )]
    if spec is not None and spec.note_clause:
        parts.append(said(spec.note_clause))
    if n_amb > 0 and algorithm != "lingam":
        parts.append(said("some_edges_have_no_direction", count=n_amb))
    return tuple(parts)


# ==============================================================================
# Markov blanket (2026-07-11, borrow-list #4).
#
# The Markov blanket MB(T) of a target T is the minimal set that shields T from
# every other variable: T ⊥ V | MB(T) for all V ∉ MB(T)∪{T} (completeness), and
# no proper subset does (minimality — every member is necessary). Structurally
# it is the parents, children, and children's other parents (spouses) of T.
#
# Unlike the five whole-graph learners above, MB is a *local, target-relative*
# primitive: given a target it screens dozens of variables down to the handful
# locally relevant to it — a dimension-reduction / pruning step for building a
# DAG. It does NOT hand you an adjustment set: the blanket includes children and
# spouses, which you must NOT condition on when estimating T's effect (that opens
# colliders). It tells you where the local structure lives; a human still directs.
#
# Why MB earns a verifier where the whole-graph learners don't: its defining
# property is checkable on the OUTPUT without re-running the search. For
# continuous (Gaussian) data the Fisher-Z conditional-independence test is a pure
# function of the correlation matrix + sample size, so the correlation matrix is
# a complete sufficient statistic. ``verify_markov_blanket`` recomputes every
# completeness / minimality test from that recorded matrix with an independent
# Fisher-Z reimplementation and rejects a returned blanket that violates the
# definition — the first per-number verification to reach the discovery layer.
#
# Scope (stated tradeoff): continuous data only. Discrete Markov blankets need a
# chi-square test whose sufficient statistic is the contingency tables, not the
# correlation matrix; that path is deliberately deferred, and mixed / discrete
# input raises an actionable error rather than silently emitting an
# un-verifiable blanket.
# ==============================================================================


class MarkovBlanketError(language.Voiced, ValueError):
    """The Markov-blanket request cannot be served as posed — the target is
    absent, there are too few candidates, or (the common case) the data is
    not continuous so the Fisher-Z sufficient-statistic path does not apply.
    Preferred over silently returning a blanket that cannot be verified.

    A :class:`themis.language.Voiced`: it carries the species and this
    occasion's facts, and the sentence is
    :class:`themis.estimation.refusal_words.Refuses`' rather than the
    raise site's. ``ValueError`` as well, because that is what a caller
    has always been able to catch.
    """


@dataclass(frozen=True)
class MarkovBlanketResult:
    """Output of a Markov-blanket screen for one ``target``.

    - ``target``: the variable whose blanket was found
    - ``blanket``: sorted tuple of member variable names (the shield)
    - ``columns``: all variables considered, in the order the
      sufficient statistic below is indexed by (target first)
    - ``data_columns``: what ``data_hash`` is OF
    - ``method``: the search method run (``"grow_shrink"``)
    - ``test``: the conditional-independence test used — ``"fisherz"`` for
      continuous data, ``"chisq"`` for discrete data. This selects which
      sufficient statistic is recorded and which the verifier recomputes.
    - ``alpha``: CI-test significance level
    - ``sample_size`` / ``data_hash``: provenance of the fitted data
    - ``correlation`` (fisherz only): the Pearson correlation matrix over
      ``columns`` — the complete sufficient statistic for Fisher-Z.
    - ``contingency`` (chisq only): ``{"levels": [...], "counts": [...]}`` —
      the per-column distinct values (defining the integer codes) and the
      sparse observed joint count table over all columns. From this the
      verifier reconstructs any stratified table and recomputes any
      chi-square test; it is a complete sufficient statistic bounded by the
      number of distinct rows (≤ n), not by the k^p dense table.
    - ``tests``: the completeness + minimality definition check — one entry
      per non-member (``role="shield"``, must be independent) and per member
      (``role="necessary"``, must be dependent); each carries the tested
      variable, the conditioning set, the test statistic (partial correlation
      for fisherz; chi-square statistic + dof for chisq), the p-value, and
      whether it passed. The verifier re-derives all of this from the recorded
      sufficient statistic and rejects a blanket that does not satisfy its own
      definition.
    - ``note``: what the run says about itself, one statement per sentence
      (:class:`~themis.estimation.discovery_words.Blanket`). The second of
      them is why this field is not just a summary: the blanket contains
      children and spouses, and conditioning on those is the one mistake a
      reader can make with it that nothing else here would warn them of.
    """

    target: str
    blanket: tuple[str, ...]

    columns: tuple[str, ...]
    """The target first, then the candidate pool in the order given.
    That is the order ``correlation`` and ``contingency`` are
    indexed by — a fact about how to read them rather than a
    spelling choice."""

    data_columns: tuple[str, ...]
    """The columns ``data_hash`` was taken over, in the order it
    walked them: sorted, because that is the order the contract
    subsets the frame into before hashing. Spelled the way every other
    digest spells its denominator, and it is the same fact — what the
    fingerprint is OF.

    The same members as ``columns`` in a different order, which is why
    they are two fields: a digest is reproduced by walking its own
    order, a matrix is read by walking the other one."""

    method: str
    test: str
    alpha: float
    sample_size: int
    data_hash: str
    tests: tuple[dict, ...]
    note: tuple[Statement, ...]
    correlation: tuple[tuple[float, ...], ...] = ()
    contingency: dict | None = None


def _corr_matrix(matrix: np.ndarray) -> np.ndarray:
    """Pearson correlation over columns (variables). This is the complete
    sufficient statistic for the Fisher-Z partial-correlation test."""
    return np.corrcoef(matrix, rowvar=False)


def _partial_corr(R: np.ndarray, i: int, j: int, cond: tuple[int, ...]) -> float:
    """Partial correlation of i and j given the conditioning set ``cond``,
    computed from the correlation matrix ``R`` by inverting the relevant
    submatrix (precision-matrix formula)."""
    if not cond:
        return float(R[i, j])
    idx = [i, j, *cond]
    sub = R[np.ix_(idx, idx)]
    try:
        P = np.linalg.inv(sub)
    except np.linalg.LinAlgError:
        P = np.linalg.pinv(sub)
    denom = np.sqrt(P[0, 0] * P[1, 1])
    if denom <= 0.0:
        return 0.0
    return float(-P[0, 1] / denom)


def _fisher_z_pvalue(
    R: np.ndarray, i: int, j: int, cond: tuple[int, ...], n: int,
) -> float:
    """Two-sided p-value of the Fisher-Z partial-correlation test for
    ``i ⊥ j | cond``. Large p → independent; small p → dependent."""
    from scipy import stats

    r = _partial_corr(R, i, j, cond)
    r = max(min(r, 0.999999999999), -0.999999999999)
    z = float(np.arctanh(r))
    dof = n - len(cond) - 3
    if dof <= 0:
        # Not enough samples to condition on this many variables — treat as
        # inconclusive/dependent (never drop an edge we cannot test).
        return 0.0
    stat = np.sqrt(dof) * abs(z)
    return float(2.0 * (1.0 - stats.norm.cdf(stat)))


# --- discrete: chi-square conditional independence from joint counts ----------
#
# Sufficient statistic = the sparse observed joint count table over all
# columns (bounded by the number of distinct rows ≤ n, NOT the k^p dense
# table). Every conditional test marginalises this table to per-stratum X×Y
# tables. Degrees of freedom follow causal-learn's convention: per stratum,
# (present-X-levels − 1)(present-Y-levels − 1), summed over strata with data.


def _level_label(v):
    """A distinct value of a discrete column, as the level it stands for.

    Two steps, and only the first is the envelope's. The contract casts
    every model column to float64, so an integer-coded column arrives here
    as ``0.0, 1.0, 2.0`` and its levels would be reported as the floats the
    cast made rather than the codes the data carries. Undoing that cast is
    a modelling decision about what a level IS on a discrete column, which
    is why it stays here and does not travel with ``envelope_scalar`` to
    the estimators, where an outcome level of exactly 2.0 is a measurement
    and not a code.
    """
    x = envelope_scalar(v)
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def _recode_discrete(frame: pd.DataFrame, cols: tuple[str, ...]):
    """Recode each column to integer codes 0..card-1 by sorted distinct value.
    Returns ``(int_matrix (n, p), levels, cards)`` where ``levels[c]`` is the
    sorted distinct values (the code = its index)."""
    levels: list[list] = []
    code_cols: list[np.ndarray] = []
    for c in cols:
        vals = frame[c].to_numpy()
        uniq = np.unique(vals)
        levels.append([_level_label(v) for v in uniq])
        code_cols.append(np.searchsorted(uniq, vals).astype(np.int64))
    int_matrix = np.column_stack(code_cols)
    cards = [len(u) for u in levels]
    return int_matrix, levels, cards


def _build_joint_counts(int_matrix: np.ndarray) -> list[tuple[tuple[int, ...], int]]:
    """Sparse joint counts over all columns: ``[(config_tuple, count), ...]``,
    bounded by the number of distinct rows (≤ n)."""
    uniq, counts = np.unique(int_matrix, axis=0, return_counts=True)
    return [
        (tuple(int(x) for x in row), int(cnt))
        for row, cnt in zip(uniq, counts)
    ]


def _chi_square_from_joint(joint, cards, i, j, cond) -> tuple[float, int, float]:
    """Conditional chi-square CI test for ``i ⊥ j | cond`` from the sparse
    joint count table. Returns ``(statistic, dof, p_value)`` — large p →
    independent. Matches causal-learn's chisq dof convention exactly."""
    from scipy.stats import chi2

    card_x, card_y = cards[i], cards[j]
    strata: dict[tuple, np.ndarray] = {}
    for config, cnt in joint:
        key = tuple(config[c] for c in cond)
        tbl = strata.get(key)
        if tbl is None:
            tbl = np.zeros((card_x, card_y), dtype=float)
            strata[key] = tbl
        tbl[config[i], config[j]] += cnt

    stat = 0.0
    dof = 0
    for tbl in strata.values():
        row = tbl.sum(axis=1)
        col = tbl.sum(axis=0)
        total = tbl.sum()
        if total <= 0:
            continue
        d = (int(np.count_nonzero(row)) - 1) * (int(np.count_nonzero(col)) - 1)
        if d <= 0:
            continue
        expected = np.outer(row, col) / total
        mask = expected > 0
        stat += float(np.sum(((tbl[mask] - expected[mask]) ** 2) / expected[mask]))
        dof += d
    if dof == 0:
        return stat, 0, 1.0
    return stat, dof, float(chi2.sf(stat, dof))


def _grow_shrink_mb(
    ci_pvalue, target: int, candidates: tuple[int, ...], alpha: float,
    *, max_rounds: int = 100,
) -> list[int]:
    """Interleaved grow-shrink Markov-blanket search to a fixpoint.

    ``ci_pvalue(i, j, cond)`` returns the conditional-independence p-value for
    ``i ⊥ j | cond`` (Fisher-Z for continuous data, chi-square for discrete) —
    the only test-specific dependency, so the search is shared across data
    types. Grow adds the most strongly associated candidate that is dependent
    on the target given the current blanket; shrink drops any member that has
    become independent given the rest. Iterating both to a fixpoint yields a
    set on which grow can add nothing (completeness) and shrink can remove
    nothing (minimality) — exactly the Markov-blanket definition at this alpha.
    Deterministic: grow breaks ties by smallest p-value then column order;
    shrink scans in column order.
    """
    mb: list[int] = []
    for _ in range(max_rounds):
        changed = False
        # Grow to local completeness
        while True:
            best: tuple[float, int] | None = None
            for c in candidates:
                if c == target or c in mb:
                    continue
                p = ci_pvalue(target, c, tuple(mb))
                if p < alpha and (best is None or p < best[0]):
                    best = (p, c)
            if best is None:
                break
            mb.append(best[1])
            changed = True
        # Shrink to minimality
        for c in list(mb):
            rest = tuple(x for x in mb if x != c)
            p = ci_pvalue(target, c, rest)
            if p > alpha:  # independent given the rest → not necessary
                mb.remove(c)
                changed = True
        if not changed:
            return sorted(mb)
    raise MarkovBlanketError(Refuses.THE_SEARCH_DID_NOT_SETTLE,
                             rounds=max_rounds)


def markov_blanket(
    data: pd.DataFrame,
    target: str,
    *,
    alpha: float = 0.05,
    columns: tuple[str, ...] | None = None,
    method: str = "grow_shrink",
) -> MarkovBlanketResult:
    """Find the Markov blanket of ``target`` in ``data``.

    Dispatches on the data type: all-continuous → Fisher-Z (correlation-matrix
    sufficient statistic); all-discrete (integer-coded / bool) → chi-square
    (joint-count sufficient statistic). ``columns`` restricts the candidate
    pool (defaults to every numeric / bool column other than the target).
    The returned blanket provably satisfies its own definition at ``alpha``
    given the recorded sufficient statistic — see ``verify_markov_blanket``.

    Raises ``MarkovBlanketError`` when the target is missing, there are no
    candidates, or the columns mix continuous and discrete types (a mixed CI
    test is deferred — split or discretise).
    """
    if method != "grow_shrink":
        raise MarkovBlanketError(Refuses.METHOD_IS_LIMITED_TO,
                                 given=method, offered=["grow_shrink"])
    if target not in data.columns:
        raise MarkovBlanketError(Refuses.NOT_A_COLUMN,
                                 where="target", name=target)

    if columns is None:
        pool = tuple(
            c for c in data.columns
            if c != target and (
                pd.api.types.is_numeric_dtype(data[c])
                or pd.api.types.is_bool_dtype(data[c])
            )
        )
    else:
        pool = tuple(c for c in columns if c != target)
    if not pool:
        raise MarkovBlanketError(Refuses.NO_CANDIDATE_COLUMNS)

    used = (target, *pool)
    contract = validate_data(data, required_columns=set(used))
    cols = tuple(used)  # target first, then pool in given order

    # Discrete path = every column integer-coded or bool; continuous path =
    # every column continuous; a mix is rejected. The coerced frame answers
    # this the same as the original one, because the classification is read
    # off the values rather than the dtype the contract rewrites.
    kinds = {c: _classify_column(contract.data[c]) for c in cols}
    discrete_cols = [c for c in cols if kinds[c] in ("bool", "discrete")]
    continuous_cols = [c for c in cols if kinds[c] == "continuous"]
    if discrete_cols and continuous_cols:
        raise MarkovBlanketError(Refuses.MIXED_TYPES_IN_ONE_TEST,
                                 discrete=sorted(discrete_cols),
                                 continuous=sorted(continuous_cols))

    n = contract.sample_size
    t_idx = 0
    cand_idx = tuple(range(1, len(cols)))

    if continuous_cols:  # ---- Fisher-Z path
        test = "fisherz"
        matrix = contract.data[list(cols)].to_numpy(dtype=float)
        R = _corr_matrix(matrix)

        def ci_pvalue(i, j, cond):
            return _fisher_z_pvalue(R, i, j, cond, n)

        def make_test(i, role, cond):
            return {
                "variable": cols[i], "role": role,
                "conditioning_set": sorted(cols[x] for x in cond),
                "partial_correlation": round(_partial_corr(R, t_idx, i, cond), 12),
                "p_value": ci_pvalue(t_idx, i, cond),
            }

        correlation = tuple(tuple(float(v) for v in row) for row in R)
        contingency = None
    else:  # ---- chi-square path
        test = "chisq"
        int_matrix, levels, cards = _recode_discrete(contract.data, cols)
        joint = _build_joint_counts(int_matrix)

        def ci_pvalue(i, j, cond):
            return _chi_square_from_joint(joint, cards, i, j, cond)[2]

        def make_test(i, role, cond):
            stat, dof, p = _chi_square_from_joint(joint, cards, t_idx, i, cond)
            return {
                "variable": cols[i], "role": role,
                "conditioning_set": sorted(cols[x] for x in cond),
                "statistic": round(stat, 10), "dof": dof, "p_value": p,
            }

        correlation = ()
        contingency = {
            "levels": [list(lv) for lv in levels],
            "counts": [[list(cfg), cnt] for cfg, cnt in joint],
        }

    mb_idx = _grow_shrink_mb(ci_pvalue, t_idx, cand_idx, alpha)
    mb_set = set(mb_idx)
    blanket = tuple(sorted(cols[i] for i in mb_idx))

    # Definition check — the sufficient audit trail. Completeness: every
    # non-member is independent of the target given the whole blanket.
    # Minimality: every member is dependent given the rest of the blanket.
    tests: list[dict] = []
    for i in cand_idx:
        if i in mb_set:
            entry = make_test(i, "necessary", tuple(x for x in mb_idx if x != i))
            entry["passed"] = entry["p_value"] <= alpha
        else:
            entry = make_test(i, "shield", tuple(mb_idx))
            entry["passed"] = entry["p_value"] > alpha
        tests.append(entry)

    # The published names of the search and the test, which is what
    # ``test_vocabulary_reach`` excuses those two enums from a gloss ON: a
    # published name reads the same to everyone, so it travels as a fact and
    # the sentence around it is what carries a language.
    note = (
        language.state(
            Blanket.FOUND_THIS_BLANKET,
            target=target,
            members=("{" + language.within(blanket) + "}") if blanket else "∅",
            pool=len(pool), size=len(blanket),
            search="grow-shrink",
            test="Fisher-Z" if test == "fisherz" else "chi-square",
            alpha=alpha,
        ),
        language.state(Blanket.A_SCREEN_AND_NOT_AN_ADJUSTMENT_SET),
    )

    return MarkovBlanketResult(
        target=target,
        blanket=blanket,
        columns=cols,
        data_columns=contract.columns,
        method=method,
        test=test,
        alpha=alpha,
        sample_size=n,
        data_hash=contract.data_hash,
        tests=tuple(tests),
        note=note,
        correlation=correlation,
        contingency=contingency,
    )


def markov_blanket_to_dict(result: MarkovBlanketResult) -> dict:
    """JSON-serialisable view of a ``MarkovBlanketResult`` — the artifact
    ``verify_markov_blanket`` consumes and the MCP tool returns."""
    d = {
        "kind": "markov_blanket",
        "target": result.target,
        "blanket": list(result.blanket),
        "columns": list(result.columns),
        "data_columns": list(result.data_columns),
        "method": result.method,
        "test": result.test,
        "alpha": result.alpha,
        "sample_size": result.sample_size,
        "data_hash": result.data_hash,
        "tests": [dict(t) for t in result.tests],
        "note": [dict(one) for one in result.note],
    }
    if result.test == "fisherz":
        d["correlation"] = [list(row) for row in result.correlation]
    else:
        d["contingency"] = result.contingency
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact(d)
