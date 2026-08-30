"""Independent audit of a NOTEARS fit.

A local optimum found by L-BFGS-B cannot be replayed step for step, and this
verifier does not try. It does not have to: the objective and its gradient
depend on the data ONLY through the Gram matrix S = X'X / n, because

    ‖X − XW‖²_F / 2n = tr((I − W)' S (I − W)) / 2      ∇ = −S(I − W)

so a d×d matrix is a sufficient statistic for the entire problem. Every
number the artifact asserts about its own solution — the acyclicity
residual, the objective value, the first-order residual, the edges, and the
varsortability of the graph those edges make — is therefore recomputed here
from ``gram`` and ``weights`` alone, by something that never ran the solver.

**Independence pin.** ``_expm`` is a second, standalone transcription of the
matrix exponential: a truncated power series with scaling-and-squaring,
where the producer uses SciPy's Padé approximant. The series is a sum of
NON-NEGATIVE terms here — its argument is W∘W, an elementwise square — so
it carries no cancellation and a disagreement between the two routes is a
real disagreement rather than two different roundings of one.

**What is NOT certified, stated rather than implied.**

- *Global optimality.* The first-order residual says the returned point is
  (nearly) stationary. Nothing here says it is the best such point, and the
  problem is not convex, so nothing could.
- *The Gram matrix itself.* It is pinned to the fitted data by ``data_hash``
  but not recomputed from the raw rows. What this guarantees is: GIVEN the
  recorded statistic, every number the artifact reports about its solution
  is the number that solution has.
- *The standardised re-run.* ``edges_standardised`` and
  ``survives_standardising`` come from solving a second problem, which this
  audit does not re-solve. What it does check is that the surviving set is a
  subset of the edges actually reported and no larger than the count it
  claims to intersect — the two ways that record can contradict itself.
"""
from __future__ import annotations

import math

import numpy as np

from .errors import VerificationError

#: How closely two routes to the same number must agree. The absolute floor
#: is not a constant: it is derived per quantity from the magnitude that
#: quantity was computed FROM, because floating-point error is proportional
#: to the intermediates and not to the answer. The acyclicity residual is
#: what makes this matter — it is a difference of two numbers near d, so its
#: error floor is set by d and not by the near-zero result, and a flat
#: tolerance wide enough to hold that floor is wide enough to accept a
#: residual replaced outright by zero.
_RTOL = 1e-9
_FLOOR = 64.0 * float(np.finfo(float).eps)

#: Above this 1-norm the power series is applied to a halved argument and the
#: result squared back. Squaring preserves the non-negativity the series
#: relies on, so the pin survives the rescaling.
_SCALE_NORM = 1.0
_MAX_TERMS = 400


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _require_list(value: object, message: str) -> list:
    if not isinstance(value, list):
        raise VerificationError(message)
    return value


def _require_str(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise VerificationError(message)
    return value


def _require_number(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VerificationError(message)
    return float(value)


def _require_int(value: object, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VerificationError(message)
    return value


def _square_matrix(value: object, size: int, what: str) -> np.ndarray:
    rows = _require_list(value, f"{what} must be a list of rows")
    _require(len(rows) == size, f"{what} must be {size}×{size}")
    out = np.zeros((size, size), dtype=float)
    for i, row in enumerate(rows):
        cells = _require_list(row, f"{what} row {i} must be a list")
        _require(len(cells) == size, f"{what} must be {size}×{size}")
        for j, cell in enumerate(cells):
            out[i, j] = _require_number(cell, f"{what}[{i}][{j}] must be a number")
    _require(bool(np.isfinite(out).all()), f"{what} holds a non-finite entry")
    return out


def _expm(a: np.ndarray) -> np.ndarray:
    """e^A by truncated power series with scaling-and-squaring.

    The second transcription. Callers pass an elementwise square, so every
    term is non-negative and the series adds rather than cancels; the
    truncation stops when a term can no longer move the sum.
    """
    norm = float(np.abs(a).sum(axis=0).max()) if a.size else 0.0
    squarings = 0
    scaled = a
    while norm > _SCALE_NORM:
        scaled = scaled / 2.0
        norm /= 2.0
        squarings += 1

    total = np.eye(a.shape[0])
    term = np.eye(a.shape[0])
    for k in range(1, _MAX_TERMS + 1):
        term = term @ scaled / k
        total = total + term
        if float(np.abs(term).max()) <= 1e-18 * max(
            1.0, float(np.abs(total).max())
        ):
            break
    else:
        raise VerificationError(
            "weights are too large for the matrix exponential to be "
            "re-derived by series; this fit cannot be audited"
        )

    for _ in range(squarings):
        total = total @ total
    return total


def _agree(recomputed: float, recorded: float, what: str, scale: float) -> None:
    """``scale`` is the largest magnitude the recomputation passed through,
    which is what the absolute floor is a fraction of."""
    if not math.isclose(
        float(recomputed), recorded,
        rel_tol=_RTOL, abs_tol=_FLOOR * max(abs(scale), 1.0),
    ):
        raise VerificationError(
            f"{what}: recorded {recorded!r}, recomputed {float(recomputed)!r}"
        )


def _edge_pairs(value: object, columns: list[str], what: str) -> set:
    known = set(columns)
    out = set()
    for entry in _require_list(value, f"{what} must be a list"):
        pair = _require_list(entry, f"{what} holds a non-pair entry")
        _require(len(pair) == 2, f"{what} holds an entry that is not a pair")
        src = _require_str(pair[0], f"{what}: the tail must be a string")
        dst = _require_str(pair[1], f"{what}: the head must be a string")
        _require(src in known, f"{what} names unknown column {src!r}")
        _require(dst in known, f"{what} names unknown column {dst!r}")
        _require(src != dst, f"{what} holds a self-loop on {src!r}")
        _require((src, dst) not in out, f"{what} holds {src!r}→{dst!r} twice")
        out.add((src, dst))
    return out


def _varsortability(w_mat: np.ndarray, variances: np.ndarray) -> tuple[float, int]:
    """Share of directed paths running low-variance → high-variance, ties half.

    Independently transcribed from the definition (Reisach, Seiler &
    Weichwald 2021): paths of every length, counted with multiplicity, so a
    pair joined three ways contributes three times.
    """
    tol = 1e-9
    edges = (w_mat != 0).astype(float)
    reach = edges.copy()
    n_paths = 0.0
    ordered = 0.0
    for _ in range(max(1, w_mat.shape[0] - 1)):
        for i in range(w_mat.shape[0]):
            for j in range(w_mat.shape[0]):
                count = reach[i, j]
                if count == 0.0:
                    continue
                n_paths += count
                lo, hi = variances[i], variances[j]
                if hi > lo * (1 + tol):
                    ordered += count
                elif hi >= lo * (1 - tol):
                    ordered += 0.5 * count
        reach = reach @ edges
    if n_paths == 0:
        return 0.5, 0
    return float(ordered / n_paths), int(round(n_paths))


def verify_notears_fit(result: dict) -> None:
    """Independently audit a NOTEARS fit artifact (the dict from
    ``notears_fit_to_dict`` / ``themis_discover_graph`` with
    ``algorithm="notears"``).

    Returns ``None`` on accept; raises ``VerificationError`` on any
    structural inconsistency, or on a recorded number that disagrees with
    the recomputation from ``gram`` and ``weights``.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(
        result.get("kind") == "notears_fit",
        f"not a notears_fit result (kind={result.get('kind')!r})",
    )

    columns = [
        _require_str(c, f"column name {c!r} must be a string")
        for c in _require_list(result.get("columns"), "columns must be a list")
    ]
    _require(bool(columns), "columns must be a non-empty list")
    _require(len(set(columns)) == len(columns), "columns holds a repeated name")
    d = len(columns)

    weights = _square_matrix(result.get("weights"), d, "weights")
    gram = _square_matrix(result.get("gram"), d, "gram")
    _require(
        bool(np.allclose(gram, gram.T, atol=1e-9)),
        "gram is not symmetric, so it is not X'X/n over these columns",
    )
    _require(
        bool((np.diag(gram) >= -1e-12).all()),
        "gram has a negative variance on its diagonal",
    )
    _require(
        bool((np.abs(np.diag(weights)) == 0).all()),
        "weights has a non-zero diagonal, which is a self-loop",
    )

    l1 = _require_number(result.get("l1_penalty"), "l1_penalty must be a number")
    _require(l1 >= 0, "l1_penalty must not be negative")
    threshold = _require_number(result.get("threshold"), "threshold must be a number")
    _require(threshold >= 0, "threshold must not be negative")
    multiplier = _require_number(result.get("multiplier"), "multiplier must be a number")
    rho = _require_number(result.get("rho"), "rho must be a number")
    _require(rho > 0, "rho must be positive")
    iterations = _require_int(result.get("iterations"), "iterations must be an integer")
    _require(iterations >= 1, "iterations must be at least 1")

    # --- the three claims about the solution, from the sufficient statistic ---
    expm = _expm(weights * weights)
    trace = float(np.trace(expm))
    _agree(
        trace - d,
        _require_number(result.get("acyclicity"), "acyclicity must be a number"),
        "acyclicity",
        # What the subtraction cancelled, not what it left. h is near zero
        # precisely when the two sides are near d, so the digits that
        # survive are set by the exponential's own entries — which grow
        # with the weights and are not bounded by d — summed d times.
        float(np.abs(expm).max()) * d,
    )

    resid = np.eye(d) - weights
    loss = float(np.trace(resid.T @ gram @ resid) / 2.0)
    penalty = l1 * float(np.abs(weights).sum())
    _agree(
        loss + penalty,
        _require_number(result.get("objective"), "objective must be a number"),
        "objective",
        abs(loss) + abs(penalty),
    )

    g_smooth = -gram @ resid + multiplier * (expm.T * weights * 2.0)
    active = weights != 0
    residual = np.where(
        active,
        np.abs(g_smooth + l1 * np.sign(weights)),
        np.maximum(0.0, np.abs(g_smooth) - l1),
    )
    free = ~np.eye(d, dtype=bool)
    _agree(
        float(residual[free].max()) if d > 1 else 0.0,
        _require_number(result.get("stationarity"), "stationarity must be a number"),
        "stationarity",
        float(np.abs(g_smooth).max()) + l1,
    )

    # --- the edges, re-read off the weights at the declared threshold --------
    pruned = np.where(np.abs(weights) >= threshold, weights, 0.0)
    np.fill_diagonal(pruned, 0.0)
    expected = {
        (columns[i], columns[j])
        for i, j in zip(*np.nonzero(pruned))
    }
    reported = _edge_pairs(result.get("directed_edges"), columns, "directed_edges")
    if reported != expected:
        missing = sorted(expected - reported)
        extra = sorted(reported - expected)
        raise VerificationError(
            "directed_edges is not what these weights say at threshold "
            f"{threshold}: missing {missing}, unsupported {extra}"
        )

    # --- the scale diagnostic ------------------------------------------------
    varsort, n_paths = _varsortability(pruned, np.diag(gram))
    _agree(
        varsort,
        _require_number(result.get("varsortability"), "varsortability must be a number"),
        "varsortability",
        1.0,
    )
    _require(
        _require_int(result.get("n_paths"), "n_paths must be an integer") == n_paths,
        f"n_paths: recorded {result.get('n_paths')!r}, recomputed {n_paths}",
    )

    n_std = _require_int(
        result.get("edges_standardised"), "edges_standardised must be an integer"
    )
    _require(n_std >= 0, "edges_standardised must not be negative")
    survives = _edge_pairs(
        result.get("survives_standardising"), columns, "survives_standardising"
    )
    _require(
        survives <= reported,
        "survives_standardising names an edge this fit did not report: "
        f"{sorted(survives - reported)}",
    )
    _require(
        len(survives) <= n_std,
        f"survives_standardising has {len(survives)} edges, more than the "
        f"{n_std} the standardised run is said to have found",
    )
