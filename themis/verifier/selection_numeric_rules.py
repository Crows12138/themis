"""Independent audit of a selection-backdoor recovered ATE (§S9.1 numeric end).

The producer (:func:`themis.estimation.selection.estimate_selection_recovery`)
evaluates the Bareinboim-Pearl selection-backdoor formula (Theorem 3.5) into a
number: μ(x) = Σ_{z⁺} [ Σ_{z⁻} E_biased[Y|x,z⁺,z⁻,S] · P_ref(z⁻|x,z⁺) ] · P_ref(z⁺),
ATE = μ(1) − μ(0). This verifier re-runs that formula from the recorded
sufficient statistics — a SECOND, standalone transcription of the sum — and
checks the returned point (and the two arms) match. It never imports the
producer's ``selection`` module and never re-touches the raw data.

Two families of recorded statistics drive the re-derivation:

- ``biased_strata`` — per-(arm, z⁺, z⁻) counts (``n``, ``y_sum``) on the
  S-restricted biased sample; the risk is ``y_sum / n``;
- ``ref_p_zplus`` / ``ref_p_zminus_given`` — the external unbiased weights
  P(z⁺) and P(z⁻|x,z⁺).

Trust boundary (stated honestly): the recorded statistics themselves are taken
as given — they are pinned to the two fitted samples by ``data_hash`` /
``reference_data_hash``, but this function does not re-read either sample to
recompute them. What it guarantees is: *given the recorded per-stratum counts
and weights*, the reported ATE is the correct evaluation of the Theorem-3.5
formula, the two arms are consistent with it, and the weight tables are proper
distributions (non-negative, summing to 1 over each conditioning cell). That
catches a formula bug, a corrupted/reordered result, and a forged point.
"""
from __future__ import annotations

from typing import NoReturn, TypeVar

from .errors import VerificationError

_ATOL = 1e-6
_SUM_ATOL = 1e-6

_T = TypeVar("_T")


def _fail(message: str) -> NoReturn:
    raise VerificationError(
        f"selection_recovery_numeric: {message}",
        step_index=None, rule="selection_recovery_numeric",
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


def _key(seq) -> tuple:
    """A stratum key as a hashable tuple of JSON scalars."""
    return tuple(seq)


def verify_selection_recovery_numeric(result: dict) -> None:
    """Re-derive a ``selection_backdoor_recovery`` numeric_estimate.

    Raises :class:`VerificationError` on any mismatch; returns ``None`` on a
    truthful block. A result that carries no such numeric_estimate is a no-op
    (nothing to audit).
    """
    ne = result.get("numeric_estimate")
    if not isinstance(ne, dict) or ne.get("method") != "selection_backdoor_recovery":
        return  # not a selection-recovery numeric result — nothing to check

    detail = _require_dict(
        ne.get("selection_recovery_numeric"),
        "numeric_estimate carries no selection_recovery_numeric detail block")
    suff = _require_dict(
        detail.get("sufficient_statistics"),
        "detail block carries no sufficient_statistics")

    zp_vars = tuple(suff.get("z_plus_vars") or ())
    zm_vars = tuple(suff.get("z_minus_vars") or ())

    # --- 1. rebuild the recorded tables into keyed lookups ---
    # P_ref(z⁺): marginal over z⁺.
    p_zplus: dict[tuple, float] = {}
    for rec in suff.get("ref_p_zplus", []):
        k = _key(rec["z_plus"])
        _require(len(k) == len(zp_vars),
                 f"ref_p_zplus key {k} arity != |z_plus_vars|={len(zp_vars)}")
        p = float(rec["p"])
        _require(-_ATOL <= p <= 1 + _ATOL, f"ref_p_zplus probability {p} out of [0,1]")
        p_zplus[k] = p
    _require(bool(p_zplus), "ref_p_zplus is empty")
    s = sum(p_zplus.values())
    _require(abs(s - 1.0) <= _SUM_ATOL, f"P(z⁺) sums to {s}, not 1")

    # P_ref(z⁻ | arm, z⁺): conditional. Empty z⁻ ⇒ trivial weight 1.
    p_zminus: dict[tuple, dict[tuple, float]] = {}
    for rec in suff.get("ref_p_zminus_given", []):
        cell = (int(rec["arm"]), _key(rec["z_plus"]))
        zm_key = _key(rec["z_minus"])
        _require(len(zm_key) == len(zm_vars),
                 f"ref_p_zminus_given key {zm_key} arity != |z_minus_vars|={len(zm_vars)}")
        p = float(rec["p"])
        _require(-_ATOL <= p <= 1 + _ATOL, f"P(z⁻|x,z⁺) probability {p} out of [0,1]")
        p_zminus.setdefault(cell, {})[zm_key] = p
    # Each conditioning cell's z⁻ weights must sum to 1 (proper conditional).
    for cell, tbl in p_zminus.items():
        cs = sum(tbl.values())
        _require(abs(cs - 1.0) <= _SUM_ATOL,
                 f"P(z⁻ | X={cell[0]}, z⁺={cell[1]}) sums to {cs}, not 1")

    # E_biased[Y | arm, z⁺, z⁻, S] = y_sum / n.
    risk: dict[tuple, float] = {}
    for rec in suff.get("biased_strata", []):
        key = (int(rec["arm"]), _key(rec["z_plus"]), _key(rec["z_minus"]))
        n = int(rec["n"])
        _require(n > 0, f"biased stratum {key} has n={n} (must be positive)")
        y_sum = float(rec["y_sum"])
        risk[key] = y_sum / n

    # --- 2. re-derive μ(arm) independently ---
    def zminus_weights(arm: int, zp_key: tuple) -> dict[tuple, float]:
        if not zm_vars:
            return {(): 1.0}
        return _require_present(
            p_zminus.get((arm, zp_key)),
            f"no recorded P(z⁻ | X={arm}, z⁺={zp_key}) for a contributing cell")

    def mu(arm: int) -> float:
        total = 0.0
        for zp_key, p_zp in p_zplus.items():
            if p_zp <= 0:
                continue
            inner = 0.0
            for zm_key, p_zm in zminus_weights(arm, zp_key).items():
                if p_zm <= 0:
                    continue
                rkey = (arm, zp_key, zm_key)
                _require(rkey in risk,
                         f"contributing stratum {rkey} has no recorded biased risk")
                inner += risk[rkey] * p_zm
            total += inner * p_zp
        return total

    mu1_re, mu0_re = mu(1), mu(0)

    # --- 3. check the recorded arms + point ---
    mu1_rec = _require_present(
        suff.get("mu_treated", detail.get("mu_treated")),
        "detail block missing mu_treated / mu_control")
    mu0_rec = _require_present(
        suff.get("mu_control", detail.get("mu_control")),
        "detail block missing mu_treated / mu_control")
    _require(abs(mu1_re - float(mu1_rec)) <= _ATOL,
             f"μ(1) mismatch: re-derived {mu1_re}, recorded {mu1_rec}")
    _require(abs(mu0_re - float(mu0_rec)) <= _ATOL,
             f"μ(0) mismatch: re-derived {mu0_re}, recorded {mu0_rec}")

    point = _require_present(ne.get("point"), "numeric_estimate missing point")
    ate_re = mu1_re - mu0_re
    _require(abs(ate_re - float(point)) <= _ATOL,
             f"ATE mismatch: re-derived μ(1)−μ(0)={ate_re}, recorded point={point}")
