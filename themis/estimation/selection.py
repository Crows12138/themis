"""Selection-bias recovery numeric end — the SBD formula on data.

The structural layer (:func:`themis.runtime.selection_recovery.recover_effect`)
answers "is P(y | do(x)) recoverable from a sample restricted on a selection
collider, and with what formula?" — but it deliberately stops at the *formula*
(``recover_effect`` docstring: "No numeric estimation here"). This module is the
DATA counterpart: given the biased sample P(v | S) and the external unbiased
data the ledger demands, it evaluates the selection-backdoor formula
(Bareinboim & Pearl 2012, Theorem 3.5) into an actual ATE with a bootstrap CI.

Why an *external* sample is mandatory here — and there is no "from the biased
sample alone" path: for a genuine selection collider of X and Y, both X and Y
are ancestors of S, so every node that closes the opened X→…→S←…←Y path is an
ancestor of S and therefore d-connected to S. Hence the adjustment weights
P(z⁺) [and P(z⁻ | x, z⁺)] can *never* be read off the biased sample — they
always require the unbiased reference data of Assumption 3.4 condition (3). A
brute-force scan of every small selection-collider DAG confirms: 0 are
recoverable from the biased sample alone. So this estimator takes a
``reference`` DataFrame (the paper's unbiased sample T) for the weights and uses
the biased sample only for the S-conditioned risks P(y | x, z, S).

The Theorem-3.5 formula, in mean form (valid for numeric as well as binary Y):

    μ(x) = Σ_{z⁺} [ Σ_{z⁻} E_biased[Y | x, z⁺, z⁻, S] · P_ref(z⁻ | x, z⁺) ] · P_ref(z⁺)
    ATE  = μ(1) − μ(0)

- E_biased[Y | x, z⁺, z⁻, S]  — the stratum mean on the S-restricted biased
  sample. (Binary Y ⇒ this is P(Y=1 | …); numeric Y ⇒ the plain mean.)
- P_ref(z⁺), P_ref(z⁻ | x, z⁺)  — empirical weights from the unbiased reference.

Empty-set shapes fall out of the general formula: Z⁺=∅ ⇒ a single trivial z⁺
stratum with weight 1; Z⁻=∅ ⇒ the inner sum collapses to one trivial z⁻
stratum with weight 1 (so μ(x) = Σ_{z⁺} E_biased[Y | x, z⁺, S] · P_ref(z⁺)).

Scope (declared):

- BINARY treatment X (the ATE is a two-arm contrast); multi-value X is deferred.
- DISCRETE adjustment sets Z⁺, Z⁻ (the saturated stratified formula has no
  empirical stratum for a continuous covariate); a covariate with more than
  ``MAX_LEVELS`` distinct values is refused as continuous.
- Numeric OR binary outcome Y (stratum means).
- The reference sample must carry the weight columns: Z⁺ for P(z⁺), and
  X ∪ Z⁺ ∪ Z⁻ for the conditional P(z⁻ | x, z⁺) when Z⁻ ≠ ∅.
- A needed stratum with no support (in the biased sample for the risk, or the
  reference for a weight) is a positivity violation and refuses rather than
  fabricating a mean.

The sufficient statistics recorded on the estimate (per-stratum biased
``(n, y_sum)`` counts + the reference weight tables) are exactly what
``themis.verify_selection_recovery_numeric`` re-runs the formula on — it never
re-touches the raw data, and never imports this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from ..types import envelope_scalar
from ..ledger import Provenance
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices

# A covariate with more distinct values than this is treated as continuous and
# refused (no empirical stratum for the saturated formula).
# The cap lives beside the per-stratum count that reads it, so a fourth
# reading of "does this column have strata" cannot come out differently
# from the other three.
from .support import MAX_LEVELS
_TOL = 1e-9


@dataclass(frozen=True)
class SelectionRecoveryEstimate:
    """Data-based selection-backdoor recovered ATE with a bootstrap CI.

    ``point`` is μ(1) − μ(0) from the Theorem-3.5 formula. ``mu_treated`` /
    ``mu_control`` are the two arms (audit trail). ``sufficient_statistics``
    carries the per-stratum biased ``(n, y_sum)`` records and the reference
    weight tables — everything the numeric verifier re-derives the point from.
    """
    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int              # biased (S-restricted) sample size
    reference_sample_size: int
    data_hash: str                # biased sample hash
    data_columns: tuple[str, ...]
    reference_data_hash: str
    reference_data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    z_plus: tuple[str, ...]
    z_minus: tuple[str, ...]
    selected_values: dict         # {selection_node: value}
    mu_treated: float
    mu_control: float
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "selection_backdoor_theorem_3_5_plug_in"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT


# --- public entry -------------------------------------------------------------


def estimate_selection_recovery(
    biased: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    z_plus: tuple[str, ...],
    z_minus: tuple[str, ...],
    selection_nodes: tuple[str, ...],
    selected_values: dict | None = None,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> SelectionRecoveryEstimate:
    """Evaluate the selection-backdoor recovery formula on data.

    Parameters
    ----------
    biased: the sample restricted on the selection node(s) — P(v | S). Rows are
        filtered to ``selected_values`` on ``selection_nodes`` (a no-op if the
        sample is already restricted); the S-conditioned risks come from here.
    reference: the external unbiased sample T. The adjustment weights P(z⁺) and
        (when Z⁻ ≠ ∅) P(z⁻ | x, z⁺) come from here.
    treatment / outcome: binary X and numeric-or-binary Y column names.
    z_plus / z_minus: the SBD partition (non-descendants / descendants of X).
    selection_nodes / selected_values: the S node(s) and the value(s) that
        define "selected"; default value is ``True`` for any node not listed.
    ci_bootstrap / ci_level / random_state / cluster: percentile bootstrap
        controls; ``cluster`` names a cluster-id column in the biased sample.

    Raises
    ------
    EstimatorFailure: non-binary treatment; continuous adjustment covariate;
        a reference weight column absent; a positivity violation (a needed
        biased or reference stratum has no support).
    """
    # One statement about what this parameter is: a value per selection node,
    # ``True`` where the caller did not say, as the envelope can record it.
    # The envelope has to record it for the answer to be checkable, so a
    # value it cannot hold is this input being refused — and deciding that
    # at the exit lets the row filter speak first, which says the sample is
    # too small: the symptom, under the name of the cause.
    supplied = dict(selected_values or {})
    selected_values = {
        s: envelope_scalar(supplied.get(s, True)) for s in selection_nodes
    }

    zp_vars = tuple(sorted(z_plus))
    zm_vars = tuple(sorted(z_minus))

    # 1. Restrict the biased sample to S = selected (harmless if already so).
    biased_sel, restricted = _restrict_to_selected(
        biased, selection_nodes, selected_values,
    )

    # 2. Validate + hash both samples. The biased sample needs X, Y, Z⁺, Z⁻;
    #    the reference needs Z⁺ and (when Z⁻ ≠ ∅) X ∪ Z⁺ ∪ Z⁻.
    biased_required = {treatment, outcome, *zp_vars, *zm_vars}
    presence = (cluster,) if cluster is not None else ()
    b_contract = validate_data(
        biased_sel, required_columns=biased_required, presence_columns=presence,
        quantity_columns=(treatment, outcome),
    )
    bdf = b_contract.data

    ref_required = set(zp_vars)
    if zm_vars:
        ref_required |= {treatment, *zp_vars, *zm_vars}
    missing = ref_required - set(reference.columns)
    if missing:
        raise EstimatorFailure(
            Refusal.REFERENCE_MISSING_COLUMN, columns=sorted(missing),
        )
    r_contract = validate_data(
        reference, required_columns=ref_required or {treatment},
        quantity_columns=(treatment, outcome),
    )
    rdf = r_contract.data

    # 3. Binary treatment; discrete adjustment.
    _require_binary(bdf[treatment], treatment)
    for v in (*zp_vars, *zm_vars):
        _require_discrete(bdf[v], v)
        if v in rdf.columns:
            _require_discrete(rdf[v], v)

    groups = (
        cluster_labels(bdf, cluster, expected_n=len(bdf))
        if cluster is not None else None
    )

    # 4. Point estimate + sufficient statistics.
    y_biased = bdf[outcome].to_numpy().astype(float)
    x_biased = _as_binary(bdf[treatment])
    mu1, mu0, suff = _formula(
        x_biased, y_biased, bdf, rdf,
        treatment=treatment, zp_vars=zp_vars, zm_vars=zm_vars,
    )
    point = mu1 - mu0

    # 5. Percentile bootstrap: resample the biased rows (or clusters) and the
    #    reference rows independently, re-run the formula, collect the ATE.
    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap(
            bdf, rdf, treatment=treatment, outcome=outcome,
            zp_vars=zp_vars, zm_vars=zm_vars, groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state,
        )

    assumptions = _assumptions(zp_vars, zm_vars, cluster)
    return SelectionRecoveryEstimate(
        point=point,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="selection_backdoor_recovery",
        assumptions=assumptions,
        sample_size=b_contract.sample_size,
        reference_sample_size=r_contract.sample_size,
        data_hash=b_contract.data_hash,
        data_columns=b_contract.columns,
        reference_data_hash=r_contract.data_hash,
        reference_data_columns=r_contract.columns,
        treatment=treatment, outcome=outcome,
        z_plus=zp_vars, z_minus=zm_vars,
        selected_values=selected_values,
        mu_treated=mu1, mu_control=mu0,
        sufficient_statistics={
            **suff,
            "biased_restricted": bool(restricted),
        },
        cluster=cluster,
    )


# --- formula core -------------------------------------------------------------


def _formula(
    x: np.ndarray, y: np.ndarray, bdf: pd.DataFrame, rdf: pd.DataFrame,
    *, treatment: str, zp_vars: tuple[str, ...], zm_vars: tuple[str, ...],
) -> tuple[float, float, dict]:
    """Compute μ(1), μ(0) and the sufficient statistics via Theorem 3.5.

    All weights are read from the reference frame; all risks from the biased
    frame. Enumeration is driven by the reference support (the weights define
    which strata contribute); a contributing stratum with no biased support is
    a positivity violation.
    """
    # Reference weights.
    p_zplus = _marginal(rdf, zp_vars)                      # {zp_key: prob}
    # Biased per-(arm, zp, zm) risk records.
    risk: dict[tuple, tuple[float, int]] = {}             # key -> (y_sum, n)

    def biased_risk(arm: int, zp_key: tuple, zm_key: tuple) -> float:
        key = (arm, zp_key, zm_key)
        if key in risk:
            ysum, n = risk[key]
        else:
            mask = (x == bool(arm))
            mask &= _stratum_mask(bdf, zp_vars, zp_key)
            mask &= _stratum_mask(bdf, zm_vars, zm_key)
            n = int(mask.sum())
            ysum = float(y[mask].sum()) if n else 0.0
            risk[key] = (ysum, n)
        if n == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                f"biased stratum X={arm}, z⁺={zp_key}, z⁻={zm_key} has no rows "
                f"(positivity violation); E[Y|x,z,S] is not estimable.",
            )
        return ysum / n

    def mu(arm: int) -> float:
        total = 0.0
        for zp_key, p_zp in p_zplus.items():
            if p_zp <= 0:
                continue
            p_zminus = _conditional(rdf, treatment, arm, zp_vars, zp_key, zm_vars)
            inner = 0.0
            for zm_key, p_zm in p_zminus.items():
                if p_zm <= 0:
                    continue
                inner += biased_risk(arm, zp_key, zm_key) * p_zm
            total += inner * p_zp
        return total

    mu1, mu0 = mu(1), mu(0)

    suff = {
        "z_plus_vars": list(zp_vars),
        "z_minus_vars": list(zm_vars),
        "treatment": treatment,
        "ref_p_zplus": [
            {"z_plus": list(_json_key(k)), "p": p} for k, p in p_zplus.items()
        ],
        "ref_p_zminus_given": _conditional_table(
            rdf, treatment, zp_vars, zm_vars, p_zplus,
        ),
        "biased_strata": [
            {"arm": arm, "z_plus": list(_json_key(zp)), "z_minus": list(_json_key(zm)),
             "y_sum": ysum, "n": n}
            for (arm, zp, zm), (ysum, n) in sorted(risk.items(), key=_stratum_sort)
        ],
        "mu_treated": mu1,
        "mu_control": mu0,
    }
    return mu1, mu0, suff


def _marginal(df: pd.DataFrame, vars_: tuple[str, ...]) -> dict[tuple, float]:
    """Empirical P(vars_) as {value-tuple: prob}. Empty vars → {(): 1.0}."""
    n = len(df)
    if not vars_:
        return {(): 1.0}
    counts: dict[tuple, int] = {}
    sub = df[list(vars_)]
    for key, idx in sub.groupby(list(vars_), sort=True, observed=True).indices.items():
        counts[_as_tuple(key, len(vars_))] = len(idx)
    return {k: v / n for k, v in counts.items()}


def _conditional(
    df: pd.DataFrame, treatment: str, arm: int,
    zp_vars: tuple[str, ...], zp_key: tuple, zm_vars: tuple[str, ...],
) -> dict[tuple, float]:
    """Empirical P(z⁻ | X=arm, z⁺=zp_key) as {value-tuple: prob}.

    Empty Z⁻ → {(): 1.0}. The conditioning cell (X=arm, z⁺=zp_key) with no
    reference support is a positivity violation."""
    if not zm_vars:
        return {(): 1.0}
    mask = (_as_binary(df[treatment]) == bool(arm))
    mask &= _stratum_mask(df, zp_vars, zp_key)
    denom = int(mask.sum())
    if denom == 0:
        raise EstimatorFailure(
            Refusal.INSUFFICIENT_SUPPORT,
            f"reference cell X={arm}, z⁺={zp_key} has no rows; P(z⁻|x,z⁺) is "
            f"not estimable (positivity violation in the unbiased sample).",
        )
    sub = df.loc[mask, list(zm_vars)]
    out: dict[tuple, float] = {}
    for key, idx in sub.groupby(list(zm_vars), sort=True, observed=True).indices.items():
        out[_as_tuple(key, len(zm_vars))] = len(idx) / denom
    return out


def _conditional_table(
    df: pd.DataFrame, treatment: str,
    zp_vars: tuple[str, ...], zm_vars: tuple[str, ...],
    p_zplus: dict[tuple, float],
) -> list[dict]:
    """Flatten every P(z⁻ | X=arm, z⁺) weight into serializable records."""
    if not zm_vars:
        return []
    rows: list[dict] = []
    for arm in (1, 0):
        for zp_key, p_zp in p_zplus.items():
            if p_zp <= 0:
                continue
            cond = _conditional(df, treatment, arm, zp_vars, zp_key, zm_vars)
            for zm_key, p in cond.items():
                rows.append({
                    "arm": arm,
                    "z_plus": list(_json_key(zp_key)),
                    "z_minus": list(_json_key(zm_key)),
                    "p": p,
                })
    return rows


# --- bootstrap ----------------------------------------------------------------


def _bootstrap(
    bdf: pd.DataFrame, rdf: pd.DataFrame, *,
    treatment: str, outcome: str,
    zp_vars: tuple[str, ...], zm_vars: tuple[str, ...],
    groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the recovered ATE — resample the biased rows
    (or clusters) and the reference rows independently, re-run the formula,
    and collect μ(1)−μ(0). Draws that induce a positivity failure are skipped.
    """
    rng = np.random.default_rng(random_state)
    nb, nr = len(bdf), len(rdf)
    ates: list[float] = []
    for _ in range(ci_bootstrap):
        bi = resample_indices(nb, rng, groups=groups)
        ri = rng.integers(0, nr, size=nr)
        bsub = bdf.iloc[bi]
        rsub = rdf.iloc[ri]
        x = _as_binary(bsub[treatment])
        y = bsub[outcome].to_numpy().astype(float)
        try:
            mu1, mu0, _ = _formula(
                x, y, bsub, rsub,
                treatment=treatment, zp_vars=zp_vars, zm_vars=zm_vars,
            )
        except EstimatorFailure:
            continue
        ates.append(mu1 - mu0)
    if len(ates) < 2:
        return (None, None)
    arr = np.asarray(ates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


# --- guards / coercion --------------------------------------------------------


def _restrict_to_selected(
    df: pd.DataFrame, selection_nodes: tuple[str, ...], selected_values: dict,
) -> tuple[pd.DataFrame, bool]:
    """Filter to rows with S = selected on every selection node.

    Returns (restricted_frame, did_filter). ``did_filter`` is True only when
    rows were actually dropped — i.e. the caller passed an unrestricted sample.
    A selection column absent from the frame is left un-filtered (the frame is
    taken as already S-restricted on it)."""
    mask = pd.Series(True, index=df.index)
    for s in selection_nodes:
        if s not in df.columns:
            continue
        val = selected_values.get(s, True)
        col = df[s]
        try:
            mask &= (col == val) | (col.astype(bool) == bool(val))
        except (TypeError, ValueError):
            mask &= (col == val)
    if bool(mask.all()):
        return df, False
    return df.loc[mask].reset_index(drop=True), True


def _require_binary(col: pd.Series, name: str) -> None:
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            treatment=name, levels=sorted(vals, key=str),
        )


def _require_discrete(col: pd.Series, name: str) -> None:
    k = col.nunique(dropna=True)
    if k > MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_ADJUSTMENT,
            column=name, levels=k, cap=MAX_LEVELS,
        )


def _as_binary(col: pd.Series) -> np.ndarray:
    return col.to_numpy().astype(bool)


def _stratum_mask(df: pd.DataFrame, vars_: tuple[str, ...], key: tuple) -> np.ndarray:
    """Boolean row mask for df[vars_] == key (all-True for empty vars_)."""
    if not vars_:
        return np.ones(len(df), dtype=bool)
    mask = np.ones(len(df), dtype=bool)
    for v, val in zip(vars_, key):
        mask &= (df[v].to_numpy() == val)
    return mask


def _as_tuple(key, arity: int) -> tuple:
    """A groupby key is a scalar for arity 1 and a tuple otherwise."""
    if arity == 1:
        return (key,)
    return tuple(key)


def _json_key(key: tuple) -> tuple:
    return tuple(envelope_scalar(v) for v in key)


def _stratum_sort(item):
    (arm, zp, zm), _ = item
    return (arm, [str(x) for x in zp], [str(x) for x in zm])


def _assumptions(
    zp_vars: tuple[str, ...], zm_vars: tuple[str, ...], cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "selection_backdoor_admissible_set",
        "consistency_of_potential_outcomes",
        "external_reference_sample_is_unbiased",
        "positivity_every_contributing_stratum_has_support",
    ]
    if zp_vars:
        out.append("zplus_weights_from_unbiased_reference_{" + ",".join(zp_vars) + "}")
    if zm_vars:
        out.append("zminus_reweighting_from_unbiased_reference_{" + ",".join(zm_vars) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
