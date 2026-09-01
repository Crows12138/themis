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

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from .contract import validate_data
from .resample import Draws, cluster_labels, resample_indices
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
    #: One entry per target-marginal cell: the weight it carries and, for
    #: the source stratum it names, each arm's size and outcome total. What
    #: the answer is a sum OVER, in the form somebody can add up again.
    #:
    #: This route appends no derivation step — the chain it rides on ends
    #: at ``identify_via_transport`` — so until these existed the number
    #: was recorded nowhere and no rule could re-derive it. Measured: the
    #: transported effect could be set to any value at all and pass the
    #: public door.
    strata: tuple[Mapping[str, object], ...] = ()
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    cluster: str | None = None
    #: Transport reweights the source strata by the target's covariate
    #: distribution and reads the answer off them; there is no model to
    #: pick, so nothing was chosen. Carried even though this family
    #: declares no functional-form assumption, because the disclosure
    #: point asks every estimate the same question.
    form: str = "transport_reweighted_strata_plug_in"
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


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

    Malformed shapes raise ``EstimatorFailure(malformed_argument)`` — the
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
                Refusal.MALFORMED_ARGUMENT,
                argument="target_marginal",
                shape="{'predicates': [str, ...], 'cells': [{'values': "
                      "{pred: value}, 'probability': p}, ...]}",
                given=target_marginal,
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
                    Refusal.MALFORMED_ARGUMENT,
                    argument="a target_marginal cell",
                    shape="{'values': {pred: value}, 'probability': number}",
                    given=c,
                )
            if set(values.keys()) != set(z_preds):
                raise EstimatorFailure(
                    Refusal.INPUTS_DISAGREE,
                    one="a target_marginal cell's values",
                    one_is=sorted(values.keys()),
                    other="the declared predicates",
                    other_is=sorted(z_preds),
                )
            cells.append((dict(values), float(prob)))
        return z_preds, cells

    z_pred = target_marginal.get("predicate")
    z_marg = target_marginal.get("marginal")
    if not isinstance(z_pred, str) or not isinstance(z_marg, dict):
        raise EstimatorFailure(
            Refusal.MALFORMED_ARGUMENT,
            argument="target_marginal",
            # Notation, not prose: this is spliced into whichever language
            # the reader asked for, so an English connector between the two
            # forms would reach half of them mid-sentence. ``|`` is the
            # union the two shapes already are.
            shape="{'predicate': str, 'marginal': {z_value: probability}} | "
                  "{'predicates': [str], 'cells': [({z: value}, probability)]}",
            given=target_marginal,
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

    Raises ``EstimatorFailure``, and the species says which of two things
    is the caller's to fix, because one who is told only that something
    went wrong cannot tell them apart:

    the request is malformed — ``malformed_argument`` for the
        target_marginal's shape, ``probabilities_do_not_sum`` for weights
        that miss 1 by more than ε, ``inputs_disagree`` for target Z
        variables that are not the ``adjustment`` set, ``too_few_inputs``
        for an empty one.
    ``overlap_insufficient`` — the request is well formed and the source
        data does not reach: a joint stratum the target marginal weights
        has no source rows, or holds only one treatment arm. ``details``
        carries the stratum and its arm counts.
    """
    if not adjustment:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="adjustment", needed=1, given=len(adjustment),
        )

    z_preds, cells = _canonical_target_marginal(target_marginal, adjustment)
    if set(z_preds) != set(adjustment):
        raise EstimatorFailure(
            Refusal.INPUTS_DISAGREE,
            one="the target_marginal variables", one_is=sorted(z_preds),
            other="the adjustment set", other_is=sorted(adjustment),
        )

    total_p = sum(p for _, p in cells)
    if abs(total_p - 1.0) > 1e-6:
        raise EstimatorFailure(
            Refusal.PROBABILITIES_DO_NOT_SUM,
            what="target_marginal", given=total_p,
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

    def _ate_in_stratum(sample: pd.DataFrame, assignment: dict,
                        record: list | None = None) -> float:
        sub = sample
        for pred, value in assignment.items():
            sub = sub[sub[pred] == value]
        if len(sub) == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                cells=[dict(assignment)],
                quantity=(
                    f"E[{outcome} | {treatment}=1, " + ", ".join(z_preds)
                    + f"] − E[{outcome} | {treatment}=0, "
                    + ", ".join(z_preds) + "]"
                ),
                recorded={"stratum": dict(assignment)},
            )
        treated = sub[sub[treatment] == True]  # noqa: E712
        control = sub[sub[treatment] == False]  # noqa: E712
        if len(treated) == 0 or len(control) == 0:
            raise EstimatorFailure(
                Refusal.NO_WITHIN_STRATUM_CONTRAST,
                column=treatment,
                strata=[dict(assignment)],
                recorded={"n_treated": len(treated),
                          "n_control": len(control)},
            )
        y_treated = treated[outcome].astype(float)
        y_control = control[outcome].astype(float)
        if record is not None:
            # Sums and counts, not the two means. A reader's auditor divides
            # for itself, so a mean copied here would be one more figure
            # taken on the producer's word — and the arm sizes are what say
            # whether a stratum's contrast rests on eleven units or eleven
            # hundred.
            record.append({
                "values": dict(assignment),
                "n_treated": int(len(treated)),
                "n_control": int(len(control)),
                "sum_treated": float(y_treated.sum()),
                "sum_control": float(y_control.sum()),
            })
        return float(y_treated.mean() - y_control.mean())

    def _transport_point(sample: pd.DataFrame,
                         record: list | None = None) -> float:
        ate = 0.0
        for assignment, p in cells:
            ate += float(p) * _ate_in_stratum(sample, assignment, record)
        return ate

    #: What the answer is a sum over. Recorded on the full sample only: the
    #: resamples below build the interval, and an interval is not what this
    #: re-derives.
    stratum_statistics: list[dict] = []
    point = _transport_point(df, stratum_statistics)
    for row, (_, p) in zip(stratum_statistics, cells):
        row["probability"] = float(p)

    ci_lower: float | None = None
    ci_upper: float | None = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        rng = np.random.default_rng(random_state)
        n = len(df)
        values: list[float] = []
        for _ in draws:
            idx = resample_indices(n, rng, groups=groups)
            try:
                value = _transport_point(df.iloc[idx])
            except EstimatorFailure as exc:
                # A resample that lost a stratum, or an arm within one. The
                # point estimate above established the source has both, so
                # this is a resampling artifact: the draw leaves the
                # interval and the rest of them build it — and says on the
                # way out which refusal took it, because a source that
                # loses strata on a tenth of its resamples is telling the
                # reader something about the strata.
                draws.unusable(exc.failure_type)
                continue
            values.append(value)
            draws.usable()
        if draws.enough:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(values, alpha))
            ci_upper = float(np.quantile(values, 1 - alpha))

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
        strata=tuple(stratum_statistics),
        draws=draws,
        cluster=cluster,
    )
