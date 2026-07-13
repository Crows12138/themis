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

from .errors import VerificationError

_ATOL = 1e-6
_SUM_ATOL = 1e-6


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(
            f"missing_data_recovery_numeric: {message}",
            step_index=None, rule="missing_data_recovery_numeric",
        )


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
    total = factor.get("marginal_total")
    _require(isinstance(total, int) and total > 0,
             f"{label}: marginal_total {total!r} must be a positive integer")
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


def verify_missing_data_numeric(result: dict) -> None:
    """Re-derive a ``missing_data_recovery_gformula`` numeric_estimate.

    Raises :class:`VerificationError` on any mismatch; returns ``None`` on a
    truthful block. A result that carries no such numeric_estimate is a no-op
    (nothing to audit).
    """
    ne = result.get("numeric_estimate")
    if (
        not isinstance(ne, dict)
        or ne.get("method") != "missing_data_recovery_gformula"
    ):
        return  # not a missing-data recovery numeric result — nothing to check

    ra = ne.get("recovered_ate")
    _require(isinstance(ra, dict),
             "numeric_estimate carries no recovered_ate detail block")
    suff = ra.get("sufficient_statistics")
    _require(isinstance(suff, dict),
             "recovered_ate block carries no sufficient_statistics")

    n_zvars = len(suff.get("adjustment_vars") or ())

    # --- 1. recovered ATE must match the reported point ---
    recovered = suff.get("recovered")
    _require(isinstance(recovered, dict),
             "sufficient_statistics missing the 'recovered' factor tables")
    ate_re = _gformula_from_stats(recovered, n_zvars, "recovered")

    point = ne.get("point")
    _require(point is not None, "numeric_estimate missing point")
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
    naive_reported = ra.get("naive_listwise_ate")
    if naive is not None:
        _require(isinstance(naive, dict),
                 "sufficient_statistics.naive is neither null nor a factor block")
        naive_re = _gformula_from_stats(naive, n_zvars, "naive")
        _require(naive_reported is not None,
                 "naive sufficient statistics recorded but naive_listwise_ate is null")
        _require(abs(naive_re - float(naive_reported)) <= _ATOL,
                 f"naive listwise ATE mismatch: re-derived {naive_re}, recorded "
                 f"{naive_reported}")
