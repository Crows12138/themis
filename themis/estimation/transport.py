"""Phase 9 §T9.2 — transport-numeric ATE estimator.

Post-stratification estimator (Cole & Stuart 2010 §3): given source
data with treatment, outcome, and a single binary adjustment variable
Z, plus a target-population marginal P(Z=z), compute

    ATE_target = Σ_z P(Z=z | target) · ATE_source(z)

where ATE_source(z) = E[Y|X=1, Z=z] - E[Y|X=0, Z=z] is computed by
stratification on the observed source DataFrame.

Phase 9 §T9.1 (already landed) produces the structural identification
result with an `adjustment_set` and `formula_repr`. This module is
the numeric companion: same identification, plug-in numeric.

Scope:
- Binary treatment, bool / continuous outcome
- One OR MORE adjustment variables Z. Multi-variable Z generalises the
  post-stratification sum to the JOINT strata of the Z set:

      ATE_target = Σ_{z1,...,zk} P*(Z1=z1,...,Zk=zk) · ATE_source(z1,...,zk)

  where each ``ATE_source`` is a difference-in-means inside the joint
  source stratum. Single-Z is the k=1 special case (identical arithmetic).
- Target marginal supplied as ``program.extensions['target_marginal']``
  via the dispatch path; this module's standalone signature takes a
  Python dict (single-Z ``{'predicate','marginal'}`` OR multi-Z
  ``{'predicates','cells'}`` joint form — see ``_canonical_target_marginal``)
- Bootstrap percentile CI matching the backdoor estimator's pattern

Out of scope (follow-up §T9.3+):
- Multi-source transport (Bareinboim 2014 §5) — needs the mz-transport
  structural identification first; not a numeric-only catch-up
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
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure


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
    data_columns: tuple[str, ...]
    assumptions: tuple[str, ...]
    cluster: str | None = None


def _canonical_target_marginal(
    target_marginal: dict, adjustment: tuple[str, ...],
) -> tuple[tuple[str, ...], list[tuple[dict, float]]]:
    """Normalise a target marginal to ``(z_predicates, cells)``.

    ``cells`` is a list of ``(assignment, probability)`` where
    ``assignment`` maps every Z predicate to a concrete value. Two input
    shapes are accepted:

    - multi-Z joint form (any k >= 1)::

          {"predicates": ["z1", "z2"],
           "cells": [{"values": {"z1": True, "z2": False},
                      "probability": 0.1}, ...]}

    - single-Z form (k == 1, back-compatible)::

          {"predicate": "z", "marginal": {True: 0.7, False: 0.3}}

    Malformed shapes raise ``EstimatorFailure(invalid_input)`` — the
    caller's own words are wrong, which is a different thing from the data
    not reaching far enough, and the species is what says so.
    """
    if "predicates" in target_marginal or "cells" in target_marginal:
        preds = target_marginal.get("predicates")
        raw_cells = target_marginal.get("cells")
        if (
            not isinstance(preds, (list, tuple))
            or not preds
            or not all(isinstance(p, str) for p in preds)
            or not isinstance(raw_cells, list)
            or not raw_cells
        ):
            raise EstimatorFailure(
                Refusal.INVALID_INPUT,
                "multi-Z target_marginal must be {'predicates': [str, ...], "
                "'cells': [{'values': {pred: value}, 'probability': p}, ...]}",
            )
        z_preds = tuple(preds)
        cells: list[tuple[dict, float]] = []
        for c in raw_cells:
            values = c.get("values") if isinstance(c, dict) else None
            prob = c.get("probability") if isinstance(c, dict) else None
            if (
                not isinstance(values, dict)
                or not isinstance(prob, (int, float))
                or isinstance(prob, bool)
            ):
                raise EstimatorFailure(
                    Refusal.INVALID_INPUT,
                    "each target_marginal cell must be {'values': "
                    "{pred: value}, 'probability': number}",
                )
            if set(values.keys()) != set(z_preds):
                raise EstimatorFailure(
                    Refusal.INVALID_INPUT,
                    f"cell values keys {refusals.describe(sorted(values.keys()))} must equal "
                    f"the declared predicates {refusals.describe(sorted(z_preds))}",
                )
            cells.append((dict(values), float(prob)))
        return z_preds, cells

    z_pred = target_marginal.get("predicate")
    z_marg = target_marginal.get("marginal")
    if not isinstance(z_pred, str) or not isinstance(z_marg, dict):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            "target_marginal must be {'predicate': str, "
            "'marginal': {z_value: probability}} or the multi-Z "
            "{'predicates': [...], 'cells': [...]} form",
        )
    return (z_pred,), [({z_pred: v}, float(p)) for v, p in z_marg.items()]


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
    """Post-stratification transport-numeric ATE (single- OR multi-Z).

    ``target_marginal`` — two accepted shapes (see
    ``_canonical_target_marginal``):
      single-Z: {"predicate": "z", "marginal": {True: p1, False: p0}}
      multi-Z : {"predicates": ["z1", "z2"],
                 "cells": [{"values": {"z1": True, "z2": False},
                            "probability": p}, ...]}

    The Z assignment in each cell is matched against the same columns
    in ``source_data``; the target's JOINT distribution P*(Z1,...,Zk)
    reweights each source joint-stratum effect.

    Returns ``TransportEstimate`` with point + CI in the target
    population's effect-size scale (binary outcome → risk difference;
    continuous outcome → mean difference).

    Raises ``EstimatorFailure``, in one of two species, because a caller
    who is told only that something went wrong cannot tell which of these
    is their problem to fix:

    ``invalid_input`` — the request is malformed: the target_marginal
        shape, Z probabilities that don't sum to 1 within ε, or target Z
        variables that don't match ``adjustment``.
    ``overlap_insufficient`` — the request is well formed and the source
        data does not reach: a joint stratum the target marginal weights
        has no source rows, or holds only one treatment arm. ``details``
        carries the stratum and its arm counts.
    """
    if not adjustment:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            "estimate_transport requires >=1 adjustment variable",
        )

    z_preds, cells = _canonical_target_marginal(target_marginal, adjustment)
    if set(z_preds) != set(adjustment):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"target_marginal variables {refusals.describe(sorted(z_preds))} doesn't match "
            f"the adjustment set {refusals.describe(sorted(adjustment))}",
        )

    total_p = sum(p for _, p in cells)
    if abs(total_p - 1.0) > 1e-6:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"target_marginal probabilities must sum to 1; got {total_p}",
        )

    required = {treatment, outcome, *z_preds}
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

    def _ate_in_stratum(sample: pd.DataFrame, assignment: dict) -> float:
        sub = sample
        for pred, value in assignment.items():
            sub = sub[sub[pred] == value]
        if len(sub) == 0:
            raise EstimatorFailure(
                Refusal.OVERLAP_INSUFFICIENT,
                f"source data has no observations with stratum {assignment}, "
                f"which the target marginal weights; transporting to a "
                f"population the source never covered would be extrapolation",
                stratum=dict(assignment),
            )
        treated = sub[sub[treatment] == True]  # noqa: E712
        control = sub[sub[treatment] == False]  # noqa: E712
        if len(treated) == 0 or len(control) == 0:
            raise EstimatorFailure(
                Refusal.OVERLAP_INSUFFICIENT,
                f"stratum {assignment} holds only one treatment arm "
                f"({len(treated)} treated, {len(control)} control), so the "
                f"source has no contrast to transport from it",
                stratum=dict(assignment),
                n_treated=len(treated), n_control=len(control),
            )
        return float(treated[outcome].astype(float).mean()
                     - control[outcome].astype(float).mean())

    def _transport_point(sample: pd.DataFrame) -> float:
        ate = 0.0
        for assignment, p in cells:
            ate += float(p) * _ate_in_stratum(sample, assignment)
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
            except EstimatorFailure:
                # A resample that lost a stratum, or an arm within one. The
                # point estimate above established the source has both, so
                # this is a resampling artifact: the draw leaves the
                # interval and the rest of them build it.
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    assumptions: tuple[str, ...] = (
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
        data_columns=contract.columns,
        assumptions=assumptions,
        cluster=cluster,
    )
