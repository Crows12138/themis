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
the test. Three data types, three sufficient statistics:

- **continuous (``test="fisherz"``)** — the Fisher-Z partial-correlation test
  is a pure function of the correlation matrix, so that matrix is a complete
  sufficient statistic;
- **discrete (``test="chisq"``)** — the chi-square conditional-independence
  test is a pure function of the joint contingency counts, so the recorded
  sparse joint count table is a complete sufficient statistic (bounded by the
  number of distinct rows ≤ n, not the k^p dense table).
- **mixed (``test="cg_lrt"``)** — the homogeneous conditional-Gaussian
  likelihood ratio is a pure function of the per-configuration counts, sums
  and cross-products, and every set of columns it asks about is a marginal of
  those, so one sparse record serves the four fits each test compares.

Independence pin: ``_partial_corr`` / ``_fisher_z_pvalue`` / ``_chi_square`` /
``_cg_loglik`` here are a second, standalone transcription. They read only the
recorded sufficient statistic; a bug in the producer's search or CI test cannot
mask itself through them. On the third the transcription goes a visibly
different way: the producer assembles the pooled covariance by subtracting each
configuration's own mean from its own cross-products, and this one takes the
total scatter about the GRAND mean and subtracts the between-configuration
scatter — the analysis-of-variance identity W = T − B. Algebraically the same
matrix; no shared line; and its determinant is read off a Cholesky factor
rather than a general LU.

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


# Each guard below is ``_require(isinstance(v, T), message)`` that hands the
# checked value back, so the caller holds a ``T`` rather than the untyped
# ``dict.get`` result — same rejection, same message, one less unstated fact.
# (Same shape as ``_require_list`` in ``orientation_rules``.)
#
# Nothing the artifact supplies is used in a way that assumes its type until
# something — one of these, or an inline ``isinstance`` — has checked it. That
# is not tidiness: hashing a name into a dict, sorting two name sets against
# each other, taking ``len`` of a level list, and letting numpy coerce a matrix
# are all type assumptions, and an unchecked one leaves as a TypeError or a
# ValueError. That breaks this module's promise (and the one in
# ``themis.kernel.verify_markov_blanket``) that every structural inconsistency
# comes back as a VerificationError — and the promise is load-bearing, because
# both callers report ``type(exc).__name__`` to the reader, where "the artifact
# is malformed" and "the verifier is broken" then read as the same event.


def _require_list(value: object, message: str) -> list:
    if not isinstance(value, list):
        raise VerificationError(message)
    return value


def _require_non_empty_list(value: object, message: str) -> list:
    checked = _require_list(value, message)
    if not checked:
        raise VerificationError(message)
    return checked


def _require_dict(value: object, message: str) -> dict:
    if not isinstance(value, dict):
        raise VerificationError(message)
    return value


def _require_str(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise VerificationError(message)
    return value


def _require_int(value: object, message: str) -> int:
    if not isinstance(value, int):
        raise VerificationError(message)
    return value


def _require_number(value: object, message: str) -> float:
    if not isinstance(value, (int, float)):
        raise VerificationError(message)
    return value


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


def _fisher_z_pvalue(
    R: np.ndarray, i: int, j: int, cond: tuple[int, ...], n: int
) -> float:
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


def _chi_square(
    joint: list[tuple[tuple[int, ...], int]],
    cards: list[int],
    i: int,
    j: int,
    cond: tuple[int, ...],
) -> tuple[float, int, float]:
    from scipy.stats import chi2

    card_x, card_y = cards[i], cards[j]
    strata: dict[tuple[int, ...], np.ndarray] = {}
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


# --- conditional Gaussian (mixed) — independent reimplementation ---------------


def _cg_loglik(cells, n: int, d_keep: tuple[int, ...],
               c_keep: tuple[int, ...]) -> float:
    """The maximised log-likelihood of the homogeneous fit over one set of
    columns, from the recorded cells alone.

        l(V) = Σ_i n_i·log(n_i/n) − (n/2)·log det Σ̂ − (n·|C|/2)(1 + log 2π)

    The pooled Σ̂ is reached by W = T − B rather than by the producer's
    per-configuration subtraction: T is the scatter of everything about the
    grand mean, B the scatter of the configuration means about it weighted by
    their counts, and the two routes agree by the analysis-of-variance identity
    and not by sharing an expression.
    """
    import math

    merged: dict[tuple[int, ...], list] = {}
    width = len(c_keep)
    for config, count, total, cross in cells:
        key = tuple(config[i] for i in d_keep)
        got = merged.get(key)
        if got is None:
            got = merged[key] = [0, np.zeros(width), np.zeros((width, width))]
        got[0] += count
        if width:
            got[1] += np.asarray([total[i] for i in c_keep], dtype=float)
            got[2] += np.asarray(
                [[cross[i][j] for j in c_keep] for i in c_keep], dtype=float)
    out = sum(count * math.log(count / n)
              for count, _, _ in merged.values() if count)
    if not width:
        return out

    grand = np.zeros(width)
    crosses = np.zeros((width, width))
    for count, total, cross in merged.values():
        grand += total
        crosses += cross
    grand = grand / n
    between = np.zeros((width, width))
    for count, total, _ in merged.values():
        if not count:
            continue
        shift = total / count - grand
        between += count * np.outer(shift, shift)
    within = (crosses - n * np.outer(grand, grand)) - between
    try:
        factor = np.linalg.cholesky(within / n)
    except np.linalg.LinAlgError as exc:
        raise VerificationError(
            "the recorded cells leave a pooled covariance that is not "
            "positive definite, so the likelihood the test is a ratio of does "
            "not exist"
        ) from exc
    logdet = 2.0 * float(np.sum(np.log(np.diag(factor))))
    return out - 0.5 * n * logdet - 0.5 * n * width * (1.0 + math.log(2.0 * math.pi))


def _cg_dof(cards: list[int], d_keep: tuple[int, ...], width: int) -> int:
    configs = 1
    for i in d_keep:
        configs *= cards[i]
    return (configs - 1) + width * configs + width * (width + 1) // 2


def _cg_test(cells, cards: list[int], n: int, i: int, j: int,
             cond: tuple[int, ...], slot) -> tuple[float, int, float]:
    from scipy.stats import chi2

    statistic = 0.0
    dof = 0
    for names, sign in (((i, j, *cond), 1), (cond, 1),
                        ((i, *cond), -1), ((j, *cond), -1)):
        d_keep = tuple(sorted(slot[k][1] for k in names if slot[k][0]))
        c_keep = tuple(sorted(slot[k][1] for k in names if not slot[k][0]))
        statistic += sign * _cg_loglik(cells, n, d_keep, c_keep)
        dof += sign * _cg_dof(cards, d_keep, len(c_keep))
    statistic *= 2.0
    if dof <= 0:
        return statistic, 0, 1.0
    return statistic, dof, float(chi2.sf(max(statistic, 0.0), dof))


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

    # Variable names are the one thing this function hashes and sorts, so they
    # are the one thing whose type it cannot leave unstated. ``columns`` is the
    # anchor — nothing else establishes that a name is a string — so it is
    # checked element by element here; the target and the blanket members are
    # then pinned against it below.
    columns = [
        _require_str(c, f"column name {c!r} must be a string")
        for c in _require_non_empty_list(
            result.get("columns"), "columns must be a non-empty list"
        )
    ]
    blanket = _require_list(result.get("blanket"), "blanket must be a list")
    tests = _require_list(result.get("tests"), "tests must be a list")
    alpha = _require_number(result.get("alpha"), "alpha out of range")
    _require(0 < alpha < 1, "alpha out of range")
    n = _require_int(result.get("sample_size"), "sample_size must be an int > 3")
    _require(n > 3, "sample_size must be an int > 3")
    test = result.get("test") or (
        "cg_lrt" if "conditional_gaussian" in result
        else "chisq" if "contingency" in result
        else "fisherz")

    # "Not a column name" covers both ways a target can fail — wrong type, or
    # simply absent — so it is one rejection with one message. Stating the type
    # is what lets the index lookup below stop assuming it.
    raw_target = result.get("target")
    not_a_column = f"target {raw_target!r} not among columns"
    target = _require_str(raw_target, not_a_column)
    _require(target in columns, not_a_column)
    _require(len(set(columns)) == len(columns), "duplicate column names")
    _require(target not in blanket, f"target {target!r} appears in its own blanket")
    # Membership first, duplicates second: being a column name is what makes a
    # blanket member a string, and the duplicate check hashes it.
    for m in blanket:
        _require(m in columns, f"blanket member {m!r} not among columns")
    _require(len(set(blanket)) == len(blanket), "duplicate members in blanket")

    col_index = {c: i for i, c in enumerate(columns)}
    t_idx = col_index[target]
    mb_idx = [col_index[m] for m in blanket]
    mb_set = set(mb_idx)
    p = len(columns)
    cand_idx = [i for i in range(p) if i != t_idx]

    # --- build the test-specific ci closure + field checker -------------------
    if test == "fisherz":
        # ``asarray`` is where untyped JSON becomes numbers; a ragged or
        # non-numeric matrix makes it raise, and that raise is a structural
        # inconsistency like any other, so it is reported as one.
        try:
            R = np.asarray(result.get("correlation"), dtype=float)
        except (TypeError, ValueError) as exc:
            raise VerificationError(
                f"correlation must be a {p}x{p} matrix of numbers"
            ) from exc
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

        def ci(i: int, cond: tuple[int, ...]) -> float:
            return _fisher_z_pvalue(R, t_idx, i, cond, n)

        def check_fields(rec: dict, i: int, cond: tuple[int, ...], pv: float) -> None:
            rec_r = rec.get("partial_correlation")
            rc = _partial_corr(R, t_idx, i, cond)
            _require(
                isinstance(rec_r, (int, float)) and abs(float(rec_r) - rc) <= _R_ATOL,
                f"test for {columns[i]!r} partial correlation {rec_r!r} != "
                f"recomputed {rc:.6g}",
            )
    elif test == "chisq":
        cont = _require_dict(
            result.get("contingency"), "chisq result needs a contingency block"
        )
        levels = _require_list(
            cont.get("levels"), "contingency.levels must have one entry per column"
        )
        _require(
            len(levels) == p,
            "contingency.levels must have one entry per column",
        )
        cards = [
            len(_require_list(lv, "each contingency.levels entry must be a list"))
            for lv in levels
        ]
        _require(all(k >= 1 for k in cards), "every column needs at least one level")
        counts = _require_non_empty_list(
            cont.get("counts"), "contingency.counts must be non-empty"
        )
        joint: list[tuple[tuple[int, ...], int]] = []
        seen_configs: set[tuple[int, ...]] = set()
        total = 0
        for row in counts:
            pair = _require_list(row, "each count row must be [config, count]")
            _require(
                len(pair) == 2,
                "each count row must be [config, count]",
            )
            config, cnt = pair
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

        def ci(i: int, cond: tuple[int, ...]) -> float:
            return _chi_square(joint, cards, t_idx, i, cond)[2]

        def check_fields(rec: dict, i: int, cond: tuple[int, ...], pv: float) -> None:
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
    elif test == "cg_lrt":
        block = _require_dict(
            result.get("conditional_gaussian"),
            "cg_lrt result needs a conditional_gaussian block",
        )
        d_names = [
            _require_str(c, "conditional_gaussian.discrete must be column names")
            for c in _require_non_empty_list(
                block.get("discrete"),
                "conditional_gaussian.discrete must be a non-empty list")
        ]
        c_names = [
            _require_str(c, "conditional_gaussian.continuous must be column names")
            for c in _require_non_empty_list(
                block.get("continuous"),
                "conditional_gaussian.continuous must be a non-empty list")
        ]
        # Both non-empty and together exactly the search space: with either
        # side empty this would be one of the two tests above, and a partition
        # that is not one leaves some column with no place in the statistic
        # while every test still reports a number for it.
        _require(
            sorted(d_names + c_names) == sorted(columns),
            "conditional_gaussian.discrete + .continuous must partition "
            "columns exactly",
        )
        levels = _require_list(
            block.get("levels"),
            "conditional_gaussian.levels must have one entry per discrete column",
        )
        _require(
            len(levels) == len(d_names),
            "conditional_gaussian.levels must have one entry per discrete column",
        )
        cards = [
            len(_require_non_empty_list(
                lv, "each conditional_gaussian.levels entry must be a non-empty list"))
            for lv in levels
        ]
        width = len(c_names)
        rows = _require_non_empty_list(
            block.get("cells"), "conditional_gaussian.cells must be non-empty")
        cells: list[tuple[tuple[int, ...], int, list, list]] = []
        seen: set[tuple[int, ...]] = set()
        total_count = 0
        for row in rows:
            parts = _require_list(
                row, "each cell must be [config, count, sum, cross]")
            _require(len(parts) == 4,
                     "each cell must be [config, count, sum, cross]")
            config, count, totals, cross = parts
            _require(
                isinstance(config, list) and len(config) == len(d_names),
                "each cell config must have one code per discrete column",
            )
            _require(isinstance(count, int) and not isinstance(count, bool)
                     and count > 0, "each cell count must be a positive int")
            cfg = tuple(config)
            for c, code in enumerate(cfg):
                _require(
                    isinstance(code, int) and not isinstance(code, bool)
                    and 0 <= code < cards[c],
                    f"cell code {code!r} out of range for column {d_names[c]!r}",
                )
            _require(cfg not in seen, "duplicate configuration in cells")
            seen.add(cfg)
            sums = [
                _require_number(v, "each cell sum must be a list of numbers")
                for v in _require_list(
                    totals, "each cell sum must be a list of numbers")
            ]
            _require(len(sums) == width,
                     "each cell sum must have one entry per continuous column")
            square = [
                [_require_number(v, "each cell cross must be a square matrix")
                 for v in _require_list(
                     r, "each cell cross must be a square matrix")]
                for r in _require_list(
                    cross, "each cell cross must be a square matrix")
            ]
            _require(
                len(square) == width and all(len(r) == width for r in square),
                "each cell cross must be square with one row per continuous "
                "column",
            )
            # A sum of outer products is symmetric by construction, so an
            # asymmetric one is not a statistic of any sample — checked here
            # rather than left to fail as a strange determinant later.
            for a in range(width):
                for b in range(a + 1, width):
                    _require(
                        abs(square[a][b] - square[b][a]) <= _STAT_ATOL
                        * max(1.0, abs(square[a][b])),
                        "a cell's cross-product matrix is not symmetric",
                    )
            cells.append((cfg, count, sums, square))
            total_count += count
        _require(total_count == n,
                 f"conditional_gaussian cells sum to {total_count}, expected n={n}")

        d_at = {c: k for k, c in enumerate(d_names)}
        c_at = {c: k for k, c in enumerate(c_names)}
        slot = {
            i: (True, d_at[c]) if c in d_at else (False, c_at[c])
            for i, c in enumerate(columns)
        }

        def ci(i: int, cond: tuple[int, ...]) -> float:
            return _cg_test(cells, cards, n, t_idx, i, cond, slot)[2]

        def check_fields(rec: dict, i: int, cond: tuple[int, ...], pv: float) -> None:
            stat, dof, _ = _cg_test(cells, cards, n, t_idx, i, cond, slot)
            rec_s = rec.get("likelihood_ratio")
            rec_d = rec.get("dof")
            _require(
                isinstance(rec_s, (int, float))
                and abs(float(rec_s) - stat) <= _STAT_ATOL * max(1.0, abs(stat)),
                f"test for {columns[i]!r} likelihood ratio {rec_s!r} != "
                f"recomputed {stat:.6g}",
            )
            _require(
                rec_d == dof,
                f"test for {columns[i]!r} dof {rec_d!r} != recomputed {dof}",
            )
    else:
        raise VerificationError(f"unknown test type {test!r}")

    # --- recompute the definition + cross-check the recorded tests ------------
    # Keyed by the variable name each entry claims. Building this dict hashes
    # that name and the coverage check below sorts it against the column names,
    # so the name is type-checked on the way in — a non-string one has to be
    # rejected *here*, before it reaches a comparison that is not defined for
    # it, not diagnosed afterwards.
    recorded: dict[str, dict] = {}
    for entry in tests:
        if not isinstance(entry, dict):
            continue  # a non-dict entry is caught by the count check below
        name = entry.get("variable")
        recorded[_require_str(name, f"test variable {name!r} must be a string")] = entry
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
        # A conditioning set that is not a list of names cannot equal the one
        # recomputed here, so its shape is part of the same mismatch verdict
        # rather than a separate complaint — but it has to be established
        # before ``sorted`` assumes it.
        cond_msg = f"test for {var!r} has a mismatched conditioning set"
        rec_cond = [
            _require_str(c, cond_msg)
            for c in _require_list(rec.get("conditioning_set", []), cond_msg)
        ]
        _require(sorted(rec_cond) == sorted(columns[x] for x in cond), cond_msg)
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
