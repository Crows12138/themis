"""Deterministic linear-SCM counterfactual — DATA end.

The structural path (:func:`themis.runtime.scheduler._dispatch_scm_counterfactual`)
computes a unit's counterfactual value by Pearl's abduction–action–prediction
(Primer §4.2) from the path coefficients **declared on the cause edges**. That
requires the user to know the structural mechanisms exactly.

This module estimates the SAME counterfactual when the coefficients are NOT
declared but a population DataFrame is available: each endogenous variable's
linear equation ``V = Σ α_p·p + U_V`` is FITTED by ordinary least squares of V
on its graph parents, and the queried unit's counterfactual is then computed by
the exact same three-step arithmetic
(:func:`themis.runtime.scm_counterfactual.linear_scm_counterfactual`).

Why the intercept needs no separate handling: OLS of ``V ~ parents`` yields
slopes α and an intercept β₀ absorbing ``E[U_V]``. Pearl's abduction recovers
the unit's exogenous term as ``U_V = v_obs − Σ α·parent_obs`` — which equals
``β₀ + ε_unit`` automatically (``v_obs = β₀ + Σ α·parent_obs + ε_unit``). The
prediction step ``v_cf = U_V + Σ α·parent_cf`` then carries β₀ forward exactly.
So fitting WITH an intercept and feeding only the SLOPES to
``linear_scm_counterfactual`` reproduces the intercept through abduction — no
change to the shared arithmetic.

Scope (declared):

- CONTINUOUS / real-valued linear SCM. The abduction–action–prediction point is
  exact only when every relevant mechanism is linear (the regime where the
  structural equations, not just the DAG, are the model). A misspecified
  (nonlinear) mechanism makes the fitted slopes and hence the point wrong; that
  is an untestable modelling assumption surfaced in the ledger, not caught here.
- The unit (Pearl's evidence E=e) is supplied as ObservationStatements, exactly
  as on the structural path — the DataFrame supplies the population to fit the
  mechanisms, the observations pin the specific unit whose counterfactual is
  asked. The DataFrame is NOT re-used as the unit.
- Point estimate + non-parametric percentile bootstrap CI (resample rows,
  REFIT every equation, recompute the unit's counterfactual). The unit is held
  fixed across replicates; only the fitted mechanisms vary.
- A rank-deficient design (collinear parents, a constant regressor) raises
  ``EstimatorFailure`` rather than returning a least-norm slope whose
  counterfactual is not identified.

Reference: Pearl, Glymour & Jewell (2016) Primer §4.2; the OLS structural-
equation fit is the textbook path-coefficient estimator for a recursive linear
SCM (Wright 1934; Bollen 1989).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from ..runtime.scm_counterfactual import linear_scm_counterfactual
from ..ledger import Provenance
from ..types import Atom
from .contract import validate_data
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class NodeFit:
    """The fitted equation of one endogenous node, plus the OLS moment
    matrices the verifier re-solves from.

    ``parents`` is the ordered parent list; ``coefficients`` are the fitted
    SLOPES (one per parent, intercept dropped). ``xtx`` / ``xty`` are the
    augmented normal-equation moments over the design ``[1, parents]`` — the
    sufficient statistics that let the verifier independently re-solve
    ``β = (XᵀX)⁻¹ Xᵀy`` and confirm the slopes."""

    node: str
    parents: tuple[str, ...]
    coefficients: tuple[float, ...]
    xtx: tuple[tuple[float, ...], ...]
    xty: tuple[float, ...]


@dataclass(frozen=True)
class SCMCounterfactualEstimate:
    """Result of a data-fitted linear-SCM counterfactual point."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "scm_counterfactual_linear_fit"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    target: str
    intervention_var: str
    intervention_value: float
    # The fitted mechanisms + their re-solve moments (verifier substrate).
    node_fits: tuple[NodeFit, ...]
    # The unit's factual values over the relevant set (abduction input).
    observed_unit: tuple[tuple[str, float], ...]
    # Abduction / prediction intermediates (rendering + audit trail).
    abducted_noise: tuple[tuple[str, float], ...] = ()
    counterfactual_values: tuple[tuple[str, float], ...] = ()
    form: str = "linear_structural_equations"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    cluster: str | None = None


def _relevant_set(graph: nx.DiGraph, x_atom: Atom, y_atom: Atom) -> set[Atom]:
    """Ancestors of Y on the MUTILATED graph (edges into X severed by do(X))
    plus Y itself — exactly the structural path's relevant set."""
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(graph.in_edges(x_atom)))
    return set(nx.ancestors(mutilated, y_atom)) | {y_atom}


def _fit_node(
    df: pd.DataFrame, node: Atom, parents: tuple[Atom, ...],
) -> tuple[tuple[float, ...], np.ndarray, np.ndarray]:
    """OLS of ``node ~ [1, parents]``; return (slopes, XtX, Xty).

    Raises ``EstimatorFailure`` if the augmented design is rank-deficient
    (collinear parents / a constant regressor) so the slopes are not
    uniquely determined."""
    n = len(df)
    design = np.empty((n, len(parents) + 1), dtype=float)
    design[:, 0] = 1.0
    for j, p in enumerate(parents):
        design[:, j + 1] = df[p.predicate].to_numpy(dtype=float)
    y = df[node.predicate].to_numpy(dtype=float)

    xtx = design.T @ design
    xty = design.T @ y
    # Rank check on the augmented design: a unique OLS solution needs full
    # column rank. A least-norm lstsq answer for a rank-deficient design is
    # not the identified structural coefficient — refuse.
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise EstimatorFailure(
            Refusal.RANK_DEFICIENT_DESIGN,
            node=node.predicate,
            parents=[p.predicate for p in parents],
        )
    beta = np.linalg.solve(xtx, xty)
    slopes = tuple(float(b) for b in beta[1:])   # drop intercept
    return slopes, xtx, xty


def _point_from_fit(
    equations: dict[Atom, tuple[tuple[Atom, float], ...]],
    observed: dict[Atom, float],
    x_atom: Atom,
    intervention_value: float,
    y_atom: Atom,
    topo: tuple[Atom, ...],
) -> tuple[float, dict[Atom, float], dict[Atom, float]]:
    res = linear_scm_counterfactual(
        equations=equations,
        observed=observed,
        intervention_var=x_atom,
        intervention_value=float(intervention_value),
        target=y_atom,
        topo_order=topo,
    )
    return res.target_value, res.noise, res.cf_values


def estimate_scm_counterfactual_point(
    data: pd.DataFrame,
    *,
    graph: nx.DiGraph,
    observed_unit: dict[Atom, float],
    intervention_atom: Atom,
    intervention_value: float,
    target_atom: Atom,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> SCMCounterfactualEstimate:
    """Fit a recursive linear SCM from ``data`` and compute the queried
    unit's counterfactual value under ``do(intervention)``.

    ``observed_unit`` is the unit's factual value for every relevant variable
    (Pearl's E=e). Raises ``EstimatorFailure`` if the query atoms are missing,
    a relevant variable is unobserved for the unit, or a fitted design is
    rank-deficient. Raises ``DataContractError`` (ValueError) on missing
    columns / NaN / too-small sample.
    """
    if intervention_atom not in graph or target_atom not in graph:
        raise EstimatorFailure(Refusal.ATOM_NOT_IN_GRAPH)
    if intervention_atom == target_atom:
        raise EstimatorFailure(Refusal.INTERVENTION_IS_TARGET)

    relevant = _relevant_set(graph, intervention_atom, target_atom)
    # Endogenous nodes we fit: every relevant node except the intervened one
    # (its equation is replaced by the do-constant, never fitted or abducted).
    fit_nodes = [v for v in relevant if v != intervention_atom]

    # Every relevant variable must be observed for the unit (abduction) and
    # present as a data column (fit). The unit uses the intervened variable's
    # factual value too — abduction of the OTHER nodes references it as a
    # parent.
    for v in relevant:
        if v not in observed_unit:
            raise EstimatorFailure(
                Refusal.UNIT_UNDEROBSERVED, variable=v.predicate,
            )

    required = {v.predicate for v in relevant}
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    topo = tuple(n for n in nx.topological_sort(graph) if n in relevant)
    parents_of = {
        v: tuple(p for p in graph.predecessors(v)) for v in fit_nodes
    }

    def _fit_all(frame: pd.DataFrame):
        eqs: dict[Atom, tuple[tuple[Atom, float], ...]] = {}
        fits: list[NodeFit] = []
        for v in fit_nodes:
            parents = parents_of[v]
            slopes, xtx, xty = _fit_node(frame, v, parents)
            eqs[v] = tuple(zip(parents, slopes))
            fits.append(NodeFit(
                node=v.predicate,
                parents=tuple(p.predicate for p in parents),
                coefficients=slopes,
                xtx=tuple(tuple(float(c) for c in row) for row in xtx),
                xty=tuple(float(c) for c in xty),
            ))
        return eqs, fits

    equations, node_fits = _fit_all(df)
    observed = {v: float(observed_unit[v]) for v in relevant}
    point, noise, cf_values = _point_from_fit(
        equations, observed, intervention_atom, intervention_value,
        target_atom, topo,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        n = len(df)
        rng = np.random.default_rng(random_state)
        reps: list[float] = []
        for _ in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            boot = df.iloc[idx]
            try:
                eqs_b, _ = _fit_all(boot)
            except EstimatorFailure:
                # A degenerate resample (e.g. a collinear draw) is dropped
                # rather than poisoning the interval.
                continue
            pt_b, _, _ = _point_from_fit(
                eqs_b, observed, intervention_atom, intervention_value,
                target_atom, topo,
            )
            reps.append(pt_b)
        if reps:
            lo_q = (1.0 - ci_level) / 2.0
            hi_q = 1.0 - lo_q
            ci_lower = float(np.quantile(reps, lo_q))
            ci_upper = float(np.quantile(reps, hi_q))

    assumptions: tuple[str, ...] = (
        "linear_structural_equations_every_relevant_mechanism",
        "recursive_acyclic_scm_matching_the_declared_graph",
        "additive_exogenous_noise_abducted_per_unit",
        "correct_parent_set_per_node_no_unmeasured_common_cause_of_a_node_and_its_parents",
    )
    if cluster is not None:
        assumptions = assumptions + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)


    return SCMCounterfactualEstimate(
        point=float(point),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method="scm_counterfactual_linear_fit",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        target=target_atom.predicate,
        intervention_var=intervention_atom.predicate,
        intervention_value=float(intervention_value),
        node_fits=tuple(node_fits),
        observed_unit=tuple(
            (v.predicate, float(observed_unit[v])) for v in topo
        ),
        abducted_noise=tuple((a.predicate, v) for a, v in noise.items()),
        counterfactual_values=tuple((a.predicate, v) for a, v in cf_values.items()),
        form="linear_structural_equations",
        cluster=cluster,
    )
