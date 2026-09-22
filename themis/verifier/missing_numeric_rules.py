"""Independent audit of a recovered-from-missing-data ATE (§S9.2 numeric end).

The producer (:func:`themis.estimation.missing_recovery.estimate_recovered_ate`)
applies the Mohan-Pearl-Tian ordered-factorization recovery, summing the
g-formula

    E[Y|do(1)] − E[Y|do(0)] = Σ_z (E[Y|1,z] − E[Y|0,z]) · P(z)

where — the whole point of the multi-factor combination — the conditional
E[Y|X,z] is estimated from rows with {Y,X,Z} observed and the covariate
marginal P(z) from rows with {Z} observed (a larger set). This verifier
re-runs that sum from the recorded per-stratum sufficient statistics — a
SECOND, standalone transcription — and checks the reported ``point`` matches.
When the naive listwise foil is recorded it re-derives that too. It never
imports the producer's ``missing_recovery`` module and never re-touches the
raw data.

Trust boundary (stated honestly): the recorded per-stratum counts / sums are
taken as given — they are pinned to the fitted sample by ``data_hash`` but this
function does not re-read the data to recompute them. What it guarantees is:
*given the recorded per-stratum {n, y_sum} conditionals and {z, count} marginal
tables*, the reported recovered (and naive) ATE is the correct evaluation of
the g-formula, and each marginal table is a proper distribution (non-negative
counts summing to its total). That catches a formula bug, a corrupted /
reordered result, a dropped stratum, and a forged point.
"""
from __future__ import annotations

from typing import NoReturn, TypeVar

from .errors import VerificationError

_ATOL = 1e-6
_SUM_ATOL = 1e-6

_T = TypeVar("_T")


def _fail(message: str) -> NoReturn:
    raise VerificationError(
        f"missing_data_recovery_numeric: {message}",
        step_index=None, rule="missing_data_recovery_numeric",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _require_dict(value: object, message: str) -> dict:
    """A check that hands back what it checked.

    ``_require(isinstance(v, dict), ...)`` leaves ``v`` exactly as unknown as
    it was: the assertion and the value are two separate things and only the
    reader connects them. This returns the value AS a dict, so the connection
    is in the code (the shape ``rules._require_atom`` already uses).
    """
    if not isinstance(value, dict):
        _fail(message)
    return value


def _require_present(value: _T | None, message: str) -> _T:
    """Same, for a recorded key whose absence is itself the failure."""
    if value is None:
        _fail(message)
    return value


def _require_positive_int(value: object, label: str, what: str) -> int:
    """Same, for a recorded count that has to be a positive integer."""
    if not isinstance(value, int) or value <= 0:
        _fail(f"{label}: {what} {value!r} must be a positive integer")
    return value


def _key(seq) -> tuple:
    """A stratum key as a hashable tuple of float scalars (0 == 0.0)."""
    return tuple(float(v) for v in seq)


def _gformula_from_stats(factor: dict, n_zvars: int, label: str) -> float:
    """Re-derive Σ_z (E[Y|1,z] − E[Y|0,z])·P(z) from one factor's recorded
    conditional_strata + marginal tables. An independent transcription of
    ``missing_recovery._gformula_ate`` that reads only the recorded counts."""
    # --- conditional risks E[Y|arm,z] = y_sum / n ---
    risk: dict[tuple, float] = {}
    for rec in factor.get("conditional_strata", []):
        z = _key(rec["z"])
        _require(len(z) == n_zvars,
                 f"{label}: conditional stratum key {z} arity != "
                 f"|adjustment_vars|={n_zvars}")
        arm = int(rec["arm"])
        _require(arm in (0, 1), f"{label}: conditional stratum arm {arm} not 0/1")
        n = int(rec["n"])
        _require(n > 0, f"{label}: conditional stratum {(arm, z)} has n={n}")
        risk[(arm, z)] = float(rec["y_sum"]) / n

    # --- marginal P(z) = count / total ---
    total = _require_positive_int(
        factor.get("marginal_total"), label, "marginal_total")
    p_z: dict[tuple, float] = {}
    csum = 0
    for rec in factor.get("marginal_counts", []):
        z = _key(rec["z"])
        _require(len(z) == n_zvars,
                 f"{label}: marginal key {z} arity != |adjustment_vars|={n_zvars}")
        count = int(rec["count"])
        _require(count >= 0, f"{label}: marginal count {count} for z={z} is negative")
        _require(z not in p_z, f"{label}: duplicate marginal stratum z={z}")
        p_z[z] = count / total
        csum += count
    _require(bool(p_z), f"{label}: marginal_counts is empty")
    _require(csum == total,
             f"{label}: marginal counts sum to {csum}, not marginal_total {total} "
             f"(a stratum was dropped or double-counted)")

    # --- sum the g-formula over the marginal strata ---
    ate = 0.0
    for z, pz in p_z.items():
        _require((1, z) in risk and (0, z) in risk,
                 f"{label}: stratum z={z} has P(z)={pz} but is missing a "
                 f"conditional arm — the recovered E[Y|X,z] is undefined there")
        ate += (risk[(1, z)] - risk[(0, z)]) * pz
    return ate


#: The one field this rule reads rather than derives: the per-stratum
#: record the g-formula sum was built from. Everything in the set below is
#: a function of it.
_RECOVERED_ATE_READ = frozenset({"sufficient_statistics"})

#: What this rule holds against that record. The two sums were here from
#: the start; the rest is what a reader is shown BESIDE them and what
#: nothing looked at -- the covariate list written twice over, the columns
#: the recovery was needed for, and the five counts that say how much data
#: the answer stands on.
_RECOVERED_ATE_HELD = frozenset({
    "point", "naive_listwise_ate", "adjustment", "missing_columns",
    "n_total", "n_marginal_rows", "n_conditional_rows",
    "n_complete_case", "n_strata"})

#: Not this rule's, and named so the three sets are a PARTITION of the
#: contract rather than a selection from it. Which rule holds them is not
#: asserted here: the test beside this module checks that none of them
#: sits in the declared remainder, which is the same claim without a
#: second author for it.
_RECOVERED_ATE_ELSEWHERE = frozenset({
    "ci_lower", "ci_upper", "precision_budget"})


def verify_missing_data_numeric(result: dict) -> None:
    """Re-derive a ``missing_data_recovery_gformula`` numeric_estimate.

    Raises :class:`VerificationError` on any mismatch; returns ``None`` on a
    truthful block. A result that carries no such numeric_estimate is a no-op
    (nothing to audit).

    THAT SENTENCE SAID THE ESTIMATE AND THE CODE RE-DERIVED TWO SUMS. The
    sufficient statistics are load-bearing -- the point is rebuilt from
    them and the marginal counts are already held to summing to their own
    total -- so every count printed beside the point had a witness sitting
    next to it that nothing was reading. Fourteen declared leaves, and the
    two a reader acts on hardest: ``n_total`` against ``n_complete_case``
    is how much of the sample went missing, and a recovery standing on
    three fifths of its rows reads exactly like one standing on all of
    them once those two numbers are free.

    Each count answers to the factor it was computed on, which is the
    whole of what the recoverability argument says: the conditional table
    is estimated where the outcome was observed and the marginal table on
    every row, so ``n_conditional_rows`` and ``n_marginal_rows`` differ on
    an honest block and differ by exactly what went missing.
    ``n_complete_case`` belongs to the naive factor and is asked only when
    that factor is recorded, the way this package holds anything present
    on one side and not the other.
    """
    ne = result.get("numeric_estimate")
    if (
        not isinstance(ne, dict)
        or ne.get("method") != "missing_data_recovery_gformula"
    ):
        return  # not a missing-data recovery numeric result — nothing to check

    ra = _require_dict(
        ne.get("recovered_ate"),
        "numeric_estimate carries no recovered_ate detail block")
    suff = _require_dict(
        ra.get("sufficient_statistics"),
        "recovered_ate block carries no sufficient_statistics")

    n_zvars = len(suff.get("adjustment_vars") or ())

    # --- 1. recovered ATE must match the reported point ---
    recovered = _require_dict(
        suff.get("recovered"),
        "sufficient_statistics missing the 'recovered' factor tables")
    ate_re = _gformula_from_stats(recovered, n_zvars, "recovered")

    point = _require_present(ne.get("point"), "numeric_estimate missing point")
    _require(abs(ate_re - float(point)) <= _ATOL,
             f"recovered ATE mismatch: re-derived {ate_re}, recorded point={point}")
    # The recovered_ate sub-block echoes the same point to the consumer.
    ra_point = ra.get("point")
    if ra_point is not None:
        _require(abs(ate_re - float(ra_point)) <= _ATOL,
                 f"recovered_ate.point {ra_point} disagrees with the re-derived "
                 f"ATE {ate_re}")

    # --- 2. naive listwise foil, when recorded, must match too ---
    naive = suff.get("naive")
    if naive is not None:
        naive_re = _gformula_from_stats(
            _require_dict(
                naive,
                "sufficient_statistics.naive is neither null nor a factor block"),
            n_zvars, "naive")
        naive_reported = _require_present(
            ra.get("naive_listwise_ate"),
            "naive sufficient statistics recorded but naive_listwise_ate is null")
        _require(abs(naive_re - float(naive_reported)) <= _ATOL,
                 f"naive listwise ATE mismatch: re-derived {naive_re}, recorded "
                 f"{naive_reported}")

    # --- 3. the covariate list, written on both sides of one block ---
    if "adjustment" in ra:
        declared = list(ra.get("adjustment") or ())
        used = list(suff.get("adjustment_vars") or ())
        _require(declared == used,
                 f"recovered_ate.adjustment {declared} is not the "
                 f"adjustment_vars {used} the strata were cut on; the two are "
                 f"one list and a reader is shown the first")

    # --- 4. the counts, each against the factor it was computed on ---
    def _count(field: str, expected: int, how: str) -> None:
        if field not in ra:
            return
        got = ra.get(field)
        _require(isinstance(got, int) and not isinstance(got, bool)
                 and got == expected,
                 f"recovered_ate.{field} is {got!r}; {how} gives {expected}")

    rows_marginal = int(recovered["marginal_total"])
    rows_conditional = sum(int(s["n"])
                           for s in recovered.get("conditional_strata", ()))
    _count("n_total", rows_marginal, "the recovered marginal total")
    _count("n_marginal_rows", rows_marginal, "the recovered marginal total")
    _count("n_conditional_rows", rows_conditional,
           "the recovered conditional strata summed")
    _count("n_strata", len(recovered.get("marginal_counts") or ()),
           "the recovered marginal strata counted")
    if naive is not None:
        _count("n_complete_case", int(naive["marginal_total"]),
               "the naive marginal total")

    # --- 5. a column can only go missing from the table it is in ---
    columns = ne.get("data_columns")
    if isinstance(columns, list) and "missing_columns" in ra:
        missing = list(ra.get("missing_columns") or ())
        stray = [c for c in missing if c not in columns]
        _require(not stray,
                 f"recovered_ate.missing_columns names {stray}, which this "
                 f"estimate did not read; a column absent from the table is "
                 f"not a column the recovery was needed for")
        _require(len(set(missing)) == len(missing),
                 f"recovered_ate.missing_columns is {missing}, and a column "
                 f"listed twice is one column counted twice")
