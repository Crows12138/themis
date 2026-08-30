"""Structure learning as continuous optimisation — NOTEARS (Zheng, Aragam,
Ravikumar & Xing, NeurIPS 2018), with the two things this repo needs before
it will ship a search it cannot replay.

The method fits a linear SCM ``X = XW + noise`` by minimising

    (1/2n)·‖X − XW‖²_F + λ‖W‖₁    subject to    h(W) = tr(e^{W∘W}) − d = 0

where h(W) = 0 exactly when W is acyclic, so the combinatorial constraint
that makes structure learning hard becomes one smooth equality. The
augmented Lagrangian below is the paper's; the two additions are not.

**The certificate.** The repo's standing rule is that every number it ships
can be re-derived by something that did not produce it, and a local optimum
found by L-BFGS-B cannot be replayed step for step. But it does not have to
be. The objective and its gradient depend on the data ONLY through the Gram
matrix S = X'X/n:

    ‖X − XW‖²_F / 2n = tr((I − W)' S (I − W)) / 2
    ∇ = −S(I − W)

so a d×d matrix is a sufficient statistic for the whole problem. Everything
the certificate asserts — the acyclicity residual, the objective value, and
the first-order (KKT) residual against the multipliers the run exited with —
is therefore recomputable from S alone by a verifier that never sees the
data and never runs the solver. What cannot be certified is global
optimality, and the envelope says so rather than implying otherwise.

**The scale diagnostic.** Reisach, Seiler & Weichwald (NeurIPS 2021) showed
that on the simulated data this family is usually benchmarked on, the
marginal variances alone very nearly sort the graph — a property they name
varsortability — and that continuous-optimisation methods exploit it, so
that a trivial variance-ordering baseline matches them. Standardising the
data destroys the property and the performance with it. That makes "did
scale carry this result" a question about every individual answer, not just
about benchmarks, and it is answerable: measure the varsortability of the
graph this run returned, and re-run on standardised data to see whether the
answer survives. Both travel with the result.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.linalg
import scipy.optimize


@dataclass(frozen=True)
class NotearsCertificate:
    """What can be re-derived about a solution that cannot be replayed.

    Every field is a function of the Gram matrix, the returned weights and
    the multipliers — so a verifier with those and nothing else recomputes
    all of them. ``stationarity`` is the max over entries of the KKT
    residual of the L1-regularised augmented-Lagrangian subproblem at exit:
    zero would mean an exact first-order stationary point, and the number
    is reported rather than asserted against a threshold, because how close
    is close enough is the reader's judgement and not the solver's.
    """

    acyclicity: float
    objective: float
    stationarity: float
    multiplier: float
    """The Lagrange multiplier estimate the run exited with. ONE number
    and not the (α, ρ) pair, because the augmented Lagrangian's
    subproblem gradient uses α + ρ·h and the constrained problem's KKT
    condition uses the updated multiplier, and those are the same
    quantity — carrying both invites adding it in twice."""
    rho: float
    l1_penalty: float
    threshold: float
    iterations: int
    #: S = X'X / n, the sufficient statistic for the objective and its
    #: gradient. Small — d×d — so unlike the moment matrices elsewhere in
    #: the repo it fits on the envelope and the re-derivation is complete.
    gram: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class ScaleDiagnostic:
    """Whether this answer came from the structure or from the scales.

    ``varsortability`` is the share of directed paths in the returned graph
    that run from a lower-variance variable to a higher-variance one, ties
    counted as half (Reisach et al. 2021). At 1.0 the marginal variances
    alone would have ordered the graph; at 0.5 they say nothing.

    The scale check runs the same fit on the same data standardised column
    by column. Standardising cannot change a causal structure, so an edge
    that survives it is one the scales did not put there, and an edge that
    does not is one they did. That verdict is PER EDGE and not a flag on
    the whole answer: the method's L1 penalty and threshold are not
    scale-equivariant, so *some* movement is certain, and a boolean saying
    so on every result would carry no information while the per-edge
    split says exactly which part of the graph to believe.
    """

    varsortability: float
    n_paths: int
    edges_standardised: int
    #: The edges present in BOTH fits, which is the part of the answer the
    #: scales did not decide.
    survives_standardising: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NotearsFit:
    columns: tuple[str, ...]
    weights: tuple[tuple[float, ...], ...]
    """The solution BEFORE thresholding — what the certificate is about, and
    the only copy of it. The thresholded matrix is this one read at
    ``certificate.threshold``, so it is derived where it is needed rather
    than carried as a second matrix that could disagree with the first."""
    directed_edges: tuple[tuple[str, str], ...]
    """Read off ``weights`` at ``certificate.threshold`` — a claim a
    verifier re-derives, which is why it is stated rather than left implied."""
    certificate: NotearsCertificate
    scale: ScaleDiagnostic


_H_TOL = 1e-8
_RHO_MAX = 1e16


def _acyclicity(w_mat: np.ndarray) -> tuple[float, np.ndarray]:
    """h(W) = tr(e^{W∘W}) − d, and its gradient.

    Zero exactly when W is acyclic, positive otherwise, and smooth
    everywhere — which is the whole trick.
    """
    d = w_mat.shape[0]
    expm = scipy.linalg.expm(w_mat * w_mat)
    return float(np.trace(expm) - d), expm.T * w_mat * 2


def _loss(w_mat: np.ndarray, gram: np.ndarray) -> tuple[float, np.ndarray]:
    """Least squares and its gradient, through the Gram matrix alone."""
    resid = np.eye(w_mat.shape[0]) - w_mat
    return (
        float(np.trace(resid.T @ gram @ resid) / 2.0),
        -gram @ resid,
    )


def _split(vec: np.ndarray, d: int) -> np.ndarray:
    """[w⁺, w⁻] ≥ 0 back to W, the standard L1 reformulation: an
    absolute value is not differentiable and a difference of two
    non-negative blocks is, so L-BFGS-B can carry the penalty in its
    bounds instead of in its objective."""
    return (vec[:d * d] - vec[d * d:]).reshape(d, d)


def _objective(vec, gram, l1, alpha, rho, d):
    w_mat = _split(vec, d)
    loss, g_loss = _loss(w_mat, gram)
    h_val, g_h = _acyclicity(w_mat)
    obj = (loss + 0.5 * rho * h_val * h_val + alpha * h_val
           + l1 * float(vec.sum()))
    g_smooth = g_loss + (rho * h_val + alpha) * g_h
    grad = np.concatenate(
        ((g_smooth + l1).ravel(), (-g_smooth + l1).ravel()))
    return obj, grad


def stationarity(w_mat: np.ndarray, gram: np.ndarray, l1: float,
                 multiplier: float) -> float:
    """The KKT residual of the constrained problem at ``w_mat``.

    Where an entry is non-zero the smooth gradient must cancel the L1
    penalty's slope exactly; where it is zero the gradient must merely be
    inside the penalty's slope. The max violation of the two is the number.

    The diagonal is excluded, and not as a tolerance. W_ii is not a variable
    the solver chose — the model forbids self-loops, so it is pinned at zero
    by a bound, and a pinned variable's first-order condition carries a bound
    multiplier that absorbs whatever gradient sits there. Asking it to lie
    inside the L1 subdifferential asks the optimum for something the problem
    never imposed, and what comes back is ``|∂loss/∂W_ii| − λ``, which is the
    residual variance of column i: a fact about how much of the column went
    unexplained, carrying no information about optimality at all.

    Public because it is the certificate's one non-trivial claim, and a
    verifier that re-derives it from the Gram matrix must be able to say
    what it is re-deriving.
    """
    _loss_val, g_loss = _loss(w_mat, gram)
    _h_val, g_h = _acyclicity(w_mat)
    g_smooth = g_loss + multiplier * g_h
    active = w_mat != 0
    residual = np.where(
        active,
        np.abs(g_smooth + l1 * np.sign(w_mat)),
        np.maximum(0.0, np.abs(g_smooth) - l1),
    )
    free = ~np.eye(w_mat.shape[0], dtype=bool)
    return float(residual[free].max()) if residual[free].size else 0.0


def _solve(gram: np.ndarray, *, l1: float, threshold: float,
           max_iter: int) -> tuple[np.ndarray, NotearsCertificate]:
    """The augmented-Lagrangian loop, and the certificate it exits with."""
    d = gram.shape[0]
    vec = np.zeros(2 * d * d)
    bounds = [(0.0, 0.0) if i == j else (0.0, None)
              for _ in range(2) for i in range(d) for j in range(d)]
    rho, alpha, h_val = 1.0, 0.0, np.inf
    used = 0
    for used in range(1, max_iter + 1):
        new_vec, new_h = vec, h_val
        while rho < _RHO_MAX:
            solution = scipy.optimize.minimize(
                _objective, vec, method="L-BFGS-B", jac=True, bounds=bounds,
                args=(gram, l1, alpha, rho, d),
            )
            new_vec = solution.x
            new_h, _grad = _acyclicity(_split(new_vec, d))
            if new_h > 0.25 * h_val:
                rho *= 10
            else:
                break
        vec, h_val = new_vec, new_h
        # The subproblem just solved used the coefficient α + ρ·h on ∇h,
        # and that IS the constrained problem's multiplier estimate — the
        # update below is the same number, not a further one.
        alpha = alpha + rho * h_val
        if h_val <= _H_TOL or rho >= _RHO_MAX:
            break

    w_mat = _split(vec, d)
    loss, _g = _loss(w_mat, gram)
    certificate = NotearsCertificate(
        acyclicity=h_val,
        objective=loss + l1 * float(np.abs(w_mat).sum()),
        stationarity=stationarity(w_mat, gram, l1, alpha),
        multiplier=alpha, rho=rho, l1_penalty=l1, threshold=threshold,
        iterations=used,
        gram=tuple(tuple(float(v) for v in row) for row in gram),
    )
    return w_mat, certificate


def _varsortability(w_mat: np.ndarray, variances: np.ndarray,
                    tol: float = 1e-9) -> tuple[float, int]:
    """The share of directed paths running low-variance → high-variance.

    Paths of every length are counted, with multiplicity: a pair joined by
    three paths contributes three times, which is Reisach et al.'s
    definition. A tie counts as half, so a graph whose variances say
    nothing scores 0.5 rather than 0 or 1.
    """
    edges = (w_mat != 0).astype(float)
    reach = edges.copy()
    var = variances.reshape(1, -1)
    ratio = np.divide(var, var.T, out=np.ones_like(edges),
                      where=var.T != 0)
    n_paths = 0.0
    ordered = 0.0
    for _ in range(max(1, w_mat.shape[0] - 1)):
        n_paths += float(reach.sum())
        ordered += float((reach * (ratio > 1 + tol)).sum())
        ordered += 0.5 * float(
            (reach * (ratio <= 1 + tol) * (ratio >= 1 - tol)).sum())
        reach = reach @ edges
    if n_paths == 0:
        return 0.5, 0
    return ordered / n_paths, int(round(n_paths))


def _edge_set(w_mat: np.ndarray) -> set[tuple[int, int]]:
    return {(int(i), int(j)) for i, j in zip(*np.nonzero(w_mat))}


def fit_notears(
    matrix: np.ndarray,
    columns: tuple[str, ...],
    *,
    l1: float = 0.1,
    threshold: float = 0.3,
    max_iter: int = 100,
) -> NotearsFit:
    """Learn a weighted DAG, and say what it rests on.

    ``matrix`` is centred first: the model has no intercept, and an
    uncentred column would put its mean into the regression.
    """
    data = np.asarray(matrix, dtype=float)
    data = data - data.mean(axis=0, keepdims=True)
    n_rows, d = data.shape
    if d != len(columns):
        raise ValueError(
            f"notears: {d} columns of data against {len(columns)} names")

    gram = data.T @ data / n_rows
    w_mat, certificate = _solve(
        gram, l1=l1, threshold=threshold, max_iter=max_iter)
    pruned = np.where(np.abs(w_mat) >= threshold, w_mat, 0.0)

    # The same question asked of the same data with the scales removed.
    # Standardising cannot change a causal structure, so whatever changes
    # came from the scales.
    scale = data.std(axis=0, ddof=0)
    scale = np.where(scale > 0, scale, 1.0)
    standardised = data / scale
    std_gram = standardised.T @ standardised / n_rows
    std_w, _std_cert = _solve(
        std_gram, l1=l1, threshold=threshold, max_iter=max_iter)
    std_pruned = np.where(np.abs(std_w) >= threshold, std_w, 0.0)

    here, there = _edge_set(pruned), _edge_set(std_pruned)
    varsort, n_paths = _varsortability(pruned, data.var(axis=0))

    def _named(pairs) -> tuple[tuple[str, str], ...]:
        return tuple(
            (columns[i], columns[j])
            for i, j in sorted(pairs, key=lambda p: (p[1], p[0]))
        )

    diagnostic = ScaleDiagnostic(
        varsortability=varsort,
        n_paths=n_paths,
        edges_standardised=len(there),
        survives_standardising=_named(here & there),
    )
    return NotearsFit(
        columns=tuple(columns),
        weights=tuple(tuple(float(v) for v in row) for row in w_mat),
        directed_edges=_named(here),
        certificate=certificate,
        scale=diagnostic,
    )
