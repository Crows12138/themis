"""Independent audit of a Markov-blanket result (2026-07-11, borrow-list #4).

A Markov blanket MB(T) is defined by two properties that any *correct* blanket
must satisfy on the data, regardless of which search produced it:

- **completeness** — every non-member is conditionally independent of the
  target given the whole blanket: ``T ⊥ V | MB`` for all ``V ∉ MB∪{T}``;
- **minimality** — every member is conditionally dependent given the rest:
  ``T ⊥̸ M | MB\\{M}`` for all ``M ∈ MB``.

This verifier re-checks both directly on the returned set, WITHOUT re-running
the grow-shrink search. For continuous data the Fisher-Z conditional-
independence test is a pure function of the correlation matrix and the sample
size, so the recorded correlation matrix is a complete sufficient statistic:
we reconstruct it, reimplement Fisher-Z from scratch (no import of the
producer, no causal-learn), recompute every completeness / minimality test,
and reject a blanket that violates its own definition — or a result whose
recorded ``tests`` disagree with the independent recomputation.

Independence pin: ``_partial_corr`` / ``_fisher_z_pvalue`` here are a second,
standalone transcription of the Fisher-Z formula. They read only the recorded
``correlation`` + ``sample_size``; a bug in the producer's search or CI test
cannot mask itself through them.

Trust boundary (stated honestly): the correlation matrix itself is taken as
the sufficient statistic — it is pinned to the fitted data by ``data_hash``,
but this function does not re-read the raw data to recompute it. What it
guarantees is: *given the recorded correlation matrix*, the returned set
provably satisfies the Markov-blanket definition at the stated alpha and every
recorded test statistic is correct. That catches a search bug, a corrupted /
reordered result, and a fabricated or trimmed blanket.
"""
from __future__ import annotations

import numpy as np

from .errors import VerificationError

_P_ATOL = 1e-6
_R_ATOL = 1e-6


def _partial_corr(R: np.ndarray, i: int, j: int, cond: tuple[int, ...]) -> float:
    """Partial correlation of i, j given ``cond`` from the correlation matrix
    (precision-matrix formula). Independent reimplementation."""
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
    """Two-sided Fisher-Z p-value for ``i ⊥ j | cond``. Independent
    reimplementation reading only ``R`` and ``n``."""
    from scipy import stats

    r = _partial_corr(R, i, j, cond)
    r = max(min(r, 0.999999999999), -0.999999999999)
    z = float(np.arctanh(r))
    dof = n - len(cond) - 3
    if dof <= 0:
        return 0.0
    stat = np.sqrt(dof) * abs(z)
    return float(2.0 * (1.0 - stats.norm.cdf(stat)))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def verify_markov_blanket(result: dict) -> None:
    """Independently audit a Markov-blanket result dict (the artifact from
    ``markov_blanket_to_dict`` / ``themis_markov_blanket``).

    Returns ``None`` on accept; raises ``VerificationError`` on any
    structural inconsistency, a correlation matrix that is not well-formed,
    a recorded test that disagrees with the independent recomputation, or a
    blanket that does not satisfy the Markov-blanket definition at its alpha.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(
        result.get("kind") == "markov_blanket",
        f"not a markov_blanket result (kind={result.get('kind')!r})",
    )

    target = result.get("target")
    blanket = result.get("blanket")
    columns = result.get("columns")
    alpha = result.get("alpha")
    n = result.get("sample_size")
    corr = result.get("correlation")
    tests = result.get("tests")

    _require(isinstance(columns, list) and columns, "columns must be a non-empty list")
    _require(isinstance(blanket, list), "blanket must be a list")
    _require(isinstance(tests, list), "tests must be a list")
    _require(isinstance(alpha, (int, float)) and 0 < alpha < 1, "alpha out of range")
    _require(isinstance(n, int) and n > 3, "sample_size must be an int > 3")
    _require(target in columns, f"target {target!r} not among columns")
    _require(len(set(columns)) == len(columns), "duplicate column names")
    _require(target not in blanket, f"target {target!r} appears in its own blanket")
    _require(len(set(blanket)) == len(blanket), "duplicate members in blanket")
    for m in blanket:
        _require(m in columns, f"blanket member {m!r} not among columns")

    # --- reconstruct and validate the sufficient statistic ---------------
    R = np.asarray(corr, dtype=float)
    p = len(columns)
    _require(R.shape == (p, p), f"correlation matrix shape {R.shape} != ({p}, {p})")
    _require(np.allclose(R, R.T, atol=1e-8), "correlation matrix is not symmetric")
    _require(np.allclose(np.diag(R), 1.0, atol=1e-6), "correlation diagonal is not 1")
    _require(
        float(np.max(np.abs(R))) <= 1.0 + 1e-6,
        "correlation matrix has an entry outside [-1, 1]",
    )
    # Must be a valid (PSD) correlation matrix — a fabricated matrix that is
    # symmetric with unit diagonal but not PSD is not a correlation matrix.
    eigmin = float(np.min(np.linalg.eigvalsh(R)))
    _require(eigmin >= -1e-6, "correlation matrix is not positive semi-definite")

    col_index = {c: i for i, c in enumerate(columns)}
    t_idx = col_index[target]
    mb_idx = [col_index[m] for m in blanket]
    mb_set = set(mb_idx)
    cand_idx = [i for i in range(p) if i != t_idx]

    # --- independently recompute the definition + cross-check the tests ---
    recorded = {t.get("variable"): t for t in tests if isinstance(t, dict)}
    _require(
        len(recorded) == len(tests),
        "tests contain a non-dict entry or duplicate variable",
    )
    expected_vars = {columns[i] for i in cand_idx}
    _require(
        set(recorded) == expected_vars,
        f"tests must cover exactly the non-target variables; "
        f"missing {sorted(expected_vars - set(recorded))}, "
        f"extra {sorted(set(recorded) - expected_vars)}",
    )

    for i in cand_idx:
        var = columns[i]
        rec = recorded[var]
        if i in mb_set:
            role, ok_expr = "necessary", "dependent (p <= alpha)"
            cond = tuple(x for x in mb_idx if x != i)
            pv = _fisher_z_pvalue(R, t_idx, i, cond, n)
            passed = pv <= alpha
        else:
            role, ok_expr = "shield", "independent (p > alpha)"
            cond = tuple(mb_idx)
            pv = _fisher_z_pvalue(R, t_idx, i, cond, n)
            passed = pv > alpha

        # (1) the returned set must satisfy the definition
        _require(
            passed,
            f"Markov-blanket definition violated: {var!r} is a "
            f"{'member but not ' + ok_expr if i in mb_set else 'non-member but not ' + ok_expr} "
            f"given {sorted(columns[x] for x in cond)} (p={pv:.4g}, alpha={alpha})",
        )
        # (2) the recorded test must match the independent recomputation
        _require(
            rec.get("role") == role,
            f"test for {var!r} claims role {rec.get('role')!r}, recomputed {role!r}",
        )
        _require(
            sorted(rec.get("conditioning_set", [])) == sorted(columns[x] for x in cond),
            f"test for {var!r} has a mismatched conditioning set",
        )
        _require(
            bool(rec.get("passed")) is passed,
            f"test for {var!r} claims passed={rec.get('passed')!r}, recomputed {passed}",
        )
        rec_p = rec.get("p_value")
        _require(
            isinstance(rec_p, (int, float)) and abs(float(rec_p) - pv) <= _P_ATOL,
            f"test for {var!r} p-value {rec_p!r} != recomputed {pv:.6g}",
        )
        rec_r = rec.get("partial_correlation")
        rc = _partial_corr(R, t_idx, i, cond)
        _require(
            isinstance(rec_r, (int, float)) and abs(float(rec_r) - rc) <= _R_ATOL,
            f"test for {var!r} partial correlation {rec_r!r} != recomputed {rc:.6g}",
        )
