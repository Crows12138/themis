"""Independent audit of a Markov-blanket result (2026-07-11, borrow-list #4).

A Markov blanket MB(T) is defined by two properties that any *correct* blanket
must satisfy on the data, regardless of which search produced it:

- **completeness** — every non-member is conditionally independent of the
  target given the whole blanket: ``T ⊥ V | MB`` for all ``V ∉ MB∪{T}``;
- **minimality** — every member is conditionally dependent given the rest:
  ``T ⊥̸ M | MB\\{M}`` for all ``M ∈ MB``.

This verifier re-checks both directly on the returned set, WITHOUT re-running
the grow-shrink search, by recomputing every conditional-independence test
from the recorded sufficient statistic with an independent reimplementation of
the test. Two data types, two sufficient statistics:

- **continuous (``test="fisherz"``)** — the Fisher-Z partial-correlation test
  is a pure function of the correlation matrix, so that matrix is a complete
  sufficient statistic;
- **discrete (``test="chisq"``)** — the chi-square conditional-independence
  test is a pure function of the joint contingency counts, so the recorded
  sparse joint count table is a complete sufficient statistic (bounded by the
  number of distinct rows ≤ n, not the k^p dense table).

Independence pin: ``_partial_corr`` / ``_fisher_z_pvalue`` / ``_chi_square``
here are a second, standalone transcription. They read only the recorded
sufficient statistic; a bug in the producer's search or CI test cannot mask
itself through them.

Trust boundary (stated honestly): the recorded sufficient statistic itself
(correlation matrix / joint counts) is taken as given — it is pinned to the
fitted data by ``data_hash``, but this function does not re-read the raw data
to recompute it. What it guarantees is: *given the recorded statistic*, the
returned set provably satisfies the Markov-blanket definition at the stated
alpha and every recorded test statistic is correct. That catches a search bug,
a corrupted / reordered result, and a fabricated or trimmed blanket.
"""
from __future__ import annotations

import numpy as np

from .errors import VerificationError

_P_ATOL = 1e-6
_R_ATOL = 1e-6
_STAT_ATOL = 1e-6


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


# --- Fisher-Z (continuous) — independent reimplementation ---------------------


def _partial_corr(R: np.ndarray, i: int, j: int, cond: tuple[int, ...]) -> float:
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


def _fisher_z_pvalue(R, i, j, cond, n) -> float:
    from scipy import stats

    r = _partial_corr(R, i, j, cond)
    r = max(min(r, 0.999999999999), -0.999999999999)
    z = float(np.arctanh(r))
    dof = n - len(cond) - 3
    if dof <= 0:
        return 0.0
    stat = np.sqrt(dof) * abs(z)
    return float(2.0 * (1.0 - stats.norm.cdf(stat)))


# --- chi-square (discrete) — independent reimplementation ---------------------


def _chi_square(joint, cards, i, j, cond) -> tuple[float, int, float]:
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


# --- entry --------------------------------------------------------------------


def verify_markov_blanket(result: dict) -> None:
    """Independently audit a Markov-blanket result dict (the artifact from
    ``markov_blanket_to_dict`` / ``themis_markov_blanket``).

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, an ill-formed sufficient statistic, a recorded test that
    disagrees with the independent recomputation, or a blanket that does not
    satisfy the Markov-blanket definition at its alpha.
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
    tests = result.get("tests")
    test = result.get("test") or ("chisq" if "contingency" in result else "fisherz")

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

    col_index = {c: i for i, c in enumerate(columns)}
    t_idx = col_index[target]
    mb_idx = [col_index[m] for m in blanket]
    mb_set = set(mb_idx)
    p = len(columns)
    cand_idx = [i for i in range(p) if i != t_idx]

    # --- build the test-specific ci closure + field checker -------------------
    if test == "fisherz":
        R = np.asarray(result.get("correlation"), dtype=float)
        _require(R.shape == (p, p), f"correlation shape {R.shape} != ({p}, {p})")
        _require(np.allclose(R, R.T, atol=1e-8), "correlation matrix is not symmetric")
        _require(np.allclose(np.diag(R), 1.0, atol=1e-6), "correlation diagonal is not 1")
        _require(
            float(np.max(np.abs(R))) <= 1.0 + 1e-6,
            "correlation matrix has an entry outside [-1, 1]",
        )
        _require(
            float(np.min(np.linalg.eigvalsh(R))) >= -1e-6,
            "correlation matrix is not positive semi-definite",
        )

        def ci(i, cond):
            return _fisher_z_pvalue(R, t_idx, i, cond, n)

        def check_fields(rec, i, cond, pv):
            rec_r = rec.get("partial_correlation")
            rc = _partial_corr(R, t_idx, i, cond)
            _require(
                isinstance(rec_r, (int, float)) and abs(float(rec_r) - rc) <= _R_ATOL,
                f"test for {columns[i]!r} partial correlation {rec_r!r} != "
                f"recomputed {rc:.6g}",
            )
    elif test == "chisq":
        cont = result.get("contingency")
        _require(isinstance(cont, dict), "chisq result needs a contingency block")
        levels = cont.get("levels")
        counts = cont.get("counts")
        _require(
            isinstance(levels, list) and len(levels) == p,
            "contingency.levels must have one entry per column",
        )
        cards = [len(lv) for lv in levels]
        _require(all(k >= 1 for k in cards), "every column needs at least one level")
        _require(isinstance(counts, list) and counts, "contingency.counts must be non-empty")
        joint = []
        seen_configs = set()
        total = 0
        for row in counts:
            _require(
                isinstance(row, list) and len(row) == 2,
                "each count row must be [config, count]",
            )
            config, cnt = row
            _require(
                isinstance(config, list) and len(config) == p,
                "each config must have one code per column",
            )
            _require(isinstance(cnt, int) and cnt > 0, "each count must be a positive int")
            cfg = tuple(config)
            for c, code in enumerate(cfg):
                _require(
                    isinstance(code, int) and 0 <= code < cards[c],
                    f"config code {code!r} out of range for column {columns[c]!r}",
                )
            _require(cfg not in seen_configs, "duplicate configuration in counts")
            seen_configs.add(cfg)
            joint.append((cfg, cnt))
            total += cnt
        _require(total == n, f"contingency counts sum to {total}, expected n={n}")

        def ci(i, cond):
            return _chi_square(joint, cards, t_idx, i, cond)[2]

        def check_fields(rec, i, cond, pv):
            stat, dof, _ = _chi_square(joint, cards, t_idx, i, cond)
            rec_s = rec.get("statistic")
            rec_d = rec.get("dof")
            _require(
                isinstance(rec_s, (int, float)) and abs(float(rec_s) - stat) <= _STAT_ATOL,
                f"test for {columns[i]!r} statistic {rec_s!r} != recomputed {stat:.6g}",
            )
            _require(
                rec_d == dof,
                f"test for {columns[i]!r} dof {rec_d!r} != recomputed {dof}",
            )
    else:
        raise VerificationError(f"unknown test type {test!r}")

    # --- recompute the definition + cross-check the recorded tests ------------
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
            pv = ci(i, cond)
            passed = pv <= alpha
        else:
            role, ok_expr = "shield", "independent (p > alpha)"
            cond = tuple(mb_idx)
            pv = ci(i, cond)
            passed = pv > alpha

        # (1) the returned set must satisfy the definition
        _require(
            passed,
            f"Markov-blanket definition violated: {var!r} is a "
            f"{'member' if i in mb_set else 'non-member'} but not {ok_expr} "
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
        check_fields(rec, i, cond, pv)
