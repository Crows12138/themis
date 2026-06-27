"""Phase 9 §T9.2 (iter 128) — transport-numeric ATE estimator.

Post-stratification estimator (Cole & Stuart 2010 §3): given source
data with treatment, outcome, and a single binary adjustment variable
Z, plus a target-population marginal P(Z=z), compute

    ATE_target = Σ_z P(Z=z | target) · ATE_source(z)

where ATE_source(z) = E[Y|X=1, Z=z] - E[Y|X=0, Z=z] is computed by
stratification on the observed source DataFrame.

Phase 9 §T9.1 (already landed) produces the structural identification
result with an `adjustment_set` and `formula_repr`. This module is
the numeric companion: same identification, plug-in numeric.

Scope (v1):
- Binary treatment, bool / continuous outcome
- Single adjustment variable Z (binary in source data)
- Target marginal supplied as ``program.extensions['target_marginal']``
  via the dispatch path; this module's standalone signature takes a
  Python dict
- Bootstrap percentile CI matching the backdoor estimator's pattern

Out of scope (follow-up §T9.3+):
- Multi-source transport (Bareinboim 2014 §5)
- Multi-variable Z marginals (joint table)
- Latent S (unobservable population indicator)
- IPSW reweighting of continuous covariates

References:
- Cole SR, Stuart EA. "Generalizing evidence from randomized clinical
  trials to target populations." Am J Epidemiol. 2010;172(1):107-115.
- Westreich D et al. "Transportability of trial results using
  inverse odds of sampling weights." Am J Epidemiol. 2017;186(8):
  1010-1014.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import validate_data
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class TransportEstimate:
    """Phase 9 §T9.2 numeric transport estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "transport_post_stratification"
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_marginal: dict             # what was supplied (audit trail)
    source_sample_size: int
    data_hash: str
    assumptions: tuple[str, ...]
    cluster: str | None = None


def estimate_transport(
    source_data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    target_marginal: dict,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> TransportEstimate:
    """Post-stratification transport-numeric ATE.

    ``target_marginal`` shape (single Z, v1):
        {"predicate": "z_pred", "marginal": {True: p1, False: p0}}

    The Z values in ``target_marginal["marginal"]`` are matched
    against the same column in ``source_data`` named by
    ``target_marginal["predicate"]``.

    Returns ``TransportEstimate`` with point + CI in the target
    population's effect-size scale (binary outcome → risk difference;
    continuous outcome → mean difference).

    Raises ``ValueError`` when:
    - target_marginal shape is malformed
    - Z's marginal probabilities don't sum to 1 within ε
    - any source stratum is empty (cannot compute ATE_source(z))
    - len(adjustment) > 1 (multi-Z is out of scope this slice)
    """
    if len(adjustment) != 1:
        raise NotImplementedError(
            "transport-numeric v1 supports only single-variable "
            "adjustment; got " + repr(adjustment)
        )

    z_pred = target_marginal.get("predicate")
    z_marg = target_marginal.get("marginal")
    if not isinstance(z_pred, str) or not isinstance(z_marg, dict):
        raise ValueError(
            "target_marginal must be {'predicate': str, "
            "'marginal': {z_value: probability}}"
        )
    if z_pred != adjustment[0]:
        raise ValueError(
            f"target_marginal.predicate {z_pred!r} doesn't match "
            f"the adjustment variable {adjustment[0]!r}"
        )

    total_p = sum(z_marg.values())
    if abs(total_p - 1.0) > 1e-6:
        raise ValueError(
            f"target_marginal.marginal probabilities must sum to 1; "
            f"got {total_p}"
        )

    required = {treatment, outcome, z_pred}
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(source_data, cluster, expected_n=len(source_data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        source_data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    def _ate_in_stratum(sample: pd.DataFrame, z_value) -> float:
        sub = sample[sample[z_pred] == z_value]
        if len(sub) == 0:
            raise ValueError(
                f"source data has no observations with {z_pred}={z_value}"
            )
        treated = sub[sub[treatment] == True]  # noqa: E712
        control = sub[sub[treatment] == False]  # noqa: E712
        if len(treated) == 0 or len(control) == 0:
            raise ValueError(
                f"stratum {z_pred}={z_value} lacks both treatment arms; "
                "cannot compute ATE_source(z)"
            )
        return float(treated[outcome].astype(float).mean()
                     - control[outcome].astype(float).mean())

    def _transport_point(sample: pd.DataFrame) -> float:
        ate = 0.0
        for z_value, p in z_marg.items():
            ate += float(p) * _ate_in_stratum(sample, z_value)
        return ate

    point = _transport_point(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            try:
                draws[i] = _transport_point(df.iloc[idx])
            except ValueError:
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    assumptions = (
        "s_admissibility_of_adjustment_set",
        "no_treatment_effect_modification_outside_z_in_either_pop",
        "consistency_of_potential_outcomes",
        "positivity_in_each_z_stratum_of_source",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return TransportEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method="transport_post_stratification",
        treatment=treatment,
        outcome=outcome,
        adjustment=tuple(adjustment),
        target_marginal=dict(target_marginal),
        source_sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        assumptions=assumptions,
        cluster=cluster,
    )
