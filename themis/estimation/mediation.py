"""Phase 7.4 + 7.5 — mediation numeric estimators.

S.MN.1 (Phase 7.4): NDE / NIE / TE via statsmodels' Mediation class
(Imai, Keele, Tingley 2010 algorithms 1 & 2). See ``estimate_mediation``.

S.CDE (Phase 7.5): Controlled Direct Effect at a fixed
mediator value m* via plug-in g-formula on a fitted outcome model
``Y ~ X + M + Z``. See ``estimate_cde``. Implementation is sklearn-
based (not statsmodels) because choosing a reference m* and computing
``E[Y|do(X=x), do(M=m*)]`` requires a custom plug-in that the
statsmodels Mediation API doesn't expose. Bootstrap CI matches the
backdoor estimator's percentile pattern.

Scope (current):
- Single mediator (bool or continuous)
- Binary treatment
- Bool or continuous outcome (logit / OLS)
- Adjustment set ``adjustment`` threaded into both outcome and
  mediator models as linear features
- CDE: requires the user to pass ``mediator_value=m*`` (no implicit
  reference choice — Themis does not invent which level is the
  "control" for the mediator)

Uses statsmodels as a production backend (not dev-only parity) per
the 5-rule API gate:
- deterministic given a seed
- statsmodels 15+ year track record
- version pinned in environment
- parity-testable against DoWhy's mediation estimator
- all outputs (3 point estimates + 3 CIs) fit in derivation JSON

CDE path uses sklearn linear / logistic regression for the outcome
model, same backend as ``themis/estimation/backdoor.py``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import SupportsFloat

import numpy as np
import pandas as pd

import statsmodels.api as sm

from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .contract import validate_data
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES, outcome_form, shapes_settled
from .declared import ORDERED_ENTRY_SHAPE, design_block, ordered_entry
from .four_way import four_way_decomposition
from .resample import cluster_labels, resample_indices


def _fit_or_refuse(fit, what: refusals.Design):
    """Run the point fit, and let a singular design say so.

    The bootstrap already tolerates a resample it cannot fit — a degenerate
    draw is expected and the interval is built from the rest. The point fit
    has no such loop: when the design is collinear, ``statsmodels`` raises
    the solver's own ``LinAlgError``, which is a ``ValueError`` subclass and
    was therefore caught by dispatch's generic guard and discarded. The
    caller was told nothing, having asked about data that cannot support
    the estimator at all.
    """
    try:
        return fit()
    except np.linalg.LinAlgError as exc:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=what,
            diagnostic=str(exc),
        ) from exc


@dataclass(frozen=True)
class ComponentEstimate:
    """A single decomposition component: point estimate + percentile CI."""

    point: float
    ci_lower: float
    ci_upper: float


@dataclass(frozen=True)
class FourWayDecomposition:
    """VanderWeele 2014 four-way decomposition of the total effect into
    CDE + INTref + INTmed + PIE (unification of mediation and interaction).

    Each component carries a bootstrap percentile CI. ``prop_mediated``
    = (INTmed+PIE)/TE and ``prop_interaction`` = (INTref+INTmed)/TE are
    the two headline attribution proportions (Ch. 14.2). ``scale`` is
    the risk-difference scale; ``cde_mediator_reference`` records that
    the controlled direct effect fixes M at 0 and the mediator contrast
    is the M=0→1 unit change (exact for binary M; the M=0/1 evaluation
    linearizes the mediator effect for a continuous M under a nonlinear
    outcome model).
    """

    cde: ComponentEstimate
    intref: ComponentEstimate
    intmed: ComponentEstimate
    pie: ComponentEstimate
    te: ComponentEstimate
    prop_mediated: ComponentEstimate
    prop_interaction: ComponentEstimate
    additive_interaction_point: float
    ci_level: float
    scale: str
    cde_mediator_reference: object
    # The six standardized quantities the split was built from:
    # p00/p01/p10/p11 = E[Y|A,M] and q0/q1 = E[M|A], g-formula standardized
    # over the sample covariates. Recorded as the difference-scale sufficient
    # statistics so the verifier can re-derive every component from them (the
    # analog of four_way_ratio recording the fitted coefficients) — turning
    # the block from invariant-only into a strong re-derivation.
    cell_means: dict[str, float]


@dataclass(frozen=True)
class MediationEstimate:
    """Numeric mediation decomposition.

    - ``nde`` / ``nie`` / ``te`` are point + CI for the natural direct,
      natural indirect, and total effects.
    - ``method`` distinguishes the outcome-model family.
    """

    nde_point: float
    nde_ci_lower: float
    nde_ci_upper: float
    nie_point: float
    nie_ci_lower: float
    nie_ci_upper: float
    te_point: float
    te_ci_lower: float
    te_ci_upper: float
    # Proportion of total effect mediated through M = NIE / TE.
    # The user's "X 占多少比例" question — surfaced explicitly so the
    # renderer doesn't have to compute it from {nie, te} (and lose the
    # CI by doing the division naively).
    proportion_mediated_point: float
    proportion_mediated_ci_lower: float
    proportion_mediated_ci_upper: float
    ci_level: float
    method: str                   # "mediation_linear_imai" | "mediation_logit_imai"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    n_rep: int
    # VanderWeele 2014 four-way split of the same total effect. Computed
    # from the same fitted (interaction-aware) models. None when the
    # difference-scale decomposition is INVALID for this data shape — a
    # continuous mediator under a nonlinear (logit) outcome, where the
    # m∈{0,1} plug-in extrapolates and the components no longer sum to the
    # total effect. ``four_way_unavailable_reason`` says why when None.
    four_way: "FourWayDecomposition | None" = None
    four_way_unavailable_reason: str | None = None
    # Variance concern, not a model node: when set, the bootstrap
    # resampled whole clusters (pairs cluster bootstrap) instead of
    # i.i.d. rows. None → ordinary i.i.d. bootstrap.
    cluster: str | None = None
    #: The outcome model's shape, and who settled it — see
    #: :mod:`themis.estimation.form`. Both empty until the caller's
    #: ``model=`` has been read.
    form: str = ""
    form_provenance: str = ""
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def estimate_mediation(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    adjustment: tuple[str, ...] = (),
    model: str = "auto",
    n_rep: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> MediationEstimate:
    """Compute NDE / NIE / TE via the Imai et al. 2010 algorithm as
    implemented in statsmodels. See module docstring for scope.

    ``cluster`` (optional column name) switches the bootstrap from
    i.i.d. rows to a pairs cluster bootstrap (whole clusters resampled
    with replacement) — the right variance under within-cluster
    dependence. ``None`` reproduces the i.i.d. CI byte-for-byte. The
    cluster column is NOT part of the causal model. The four-way
    components share the same resampled frames, so they inherit the
    cluster-robust CI automatically.
    """
    required = {treatment, outcome, mediator, *adjustment}
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
        quantity_columns=(treatment, outcome, mediator),
    )
    df = contract.data

    resolved, form_provenance = outcome_form(model, df[outcome], logistic="logit")

    # Coerce to float for statsmodels formula API
    fit_df = df.copy()
    bool_cols = [c for c in fit_df.columns if fit_df[c].dtype == bool]
    for c in bool_cols:
        fit_df[c] = fit_df[c].astype(float)

    adj_term = " + ".join(adjustment) if adjustment else ""
    sep = " + " if adj_term else ""

    # Outcome model: Y ~ X + M + X:M [+ adjustment]. The exposure-mediator
    # interaction is INCLUDED so the natural-effect decomposition is correct
    # under interaction. Omitting it silently collapses NDE/NIE to the
    # Baron-Kenny estimates (θ1, θ2·β1), which VanderWeele (2015, §2.2) shows
    # are biased whenever an interaction is present. statsmodels' Mediation does
    # NOT propagate an interaction term to the counterfactual exposure (it sets
    # the X column but leaves the stale X:M product), so we compute the natural
    # effects ourselves with a g-formula that re-predicts the outcome on rebuilt
    # design rows — patsy then recomputes X:M at the counterfactual exposure.
    interaction = f"{treatment}:{mediator}"
    outcome_formula = (
        f"{outcome} ~ {treatment} + {mediator} + {interaction}{sep}{adj_term}"
    )
    if resolved == "logit":
        is_logit = True
        method = "mediation_logit_imai"
    elif resolved == "linear":
        is_logit = False
        method = "mediation_linear_imai"
    else:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"unknown model {model!r}; mediation fits 'logit' or 'linear'",
            model=model,
        )

    # Mediator model: M ~ X [+ adjustment]. Always OLS; for a bool mediator this
    # is a linear-probability first stage (a standard Imai-framework
    # approximation when the treatment effect on M is away from the [0,1] edge).
    mediator_formula = f"{mediator} ~ {treatment}{sep}{adj_term}"

    rng = np.random.default_rng(random_state)
    n_sim = 100  # Monte-Carlo mediator draws for the nonlinear (logit) g-formula

    def _fit(frame: pd.DataFrame):
        if is_logit:
            om = sm.Logit.from_formula(outcome_formula, data=frame).fit(disp=0)
        else:
            om = sm.OLS.from_formula(outcome_formula, data=frame).fit()
        mm = sm.OLS.from_formula(mediator_formula, data=frame).fit()
        return om, mm

    def _nde_nie(om, mm, frame: pd.DataFrame) -> tuple[float, float]:
        # NDE = E[Y_{1,M0} - Y_{0,M0}], NIE = E[Y_{1,M1} - Y_{1,M0}], where
        # M_x ~ (mediator model | X = x). The outcome is predicted on rebuilt
        # rows so the X:M interaction is re-evaluated at the counterfactual X.
        def _mean_M(xval: float):
            d = frame.copy()
            d[treatment] = xval
            return np.asarray(mm.predict(d))

        def _EY(xval: float, m_values, base: pd.DataFrame):
            d = base.copy()
            d[treatment] = xval
            d[mediator] = m_values
            return np.asarray(om.predict(d))

        if is_logit:
            # Nonlinear outcome: integrate over M's distribution by Monte Carlo.
            sd = float(np.std(np.asarray(mm.resid), ddof=1))
            mu0, mu1 = _mean_M(0.0), _mean_M(1.0)
            k = len(frame)
            big = pd.concat([frame] * n_sim, ignore_index=True)
            m0 = np.tile(mu0, n_sim) + rng.standard_normal(n_sim * k) * sd
            m1 = np.tile(mu1, n_sim) + rng.standard_normal(n_sim * k) * sd
            nde = float(np.mean(_EY(1.0, m0, big) - _EY(0.0, m0, big)))
            nie = float(np.mean(_EY(1.0, m1, big) - _EY(1.0, m0, big)))
            return nde, nie
        # Linear outcome: E[Y|X,M] is linear in M, so plugging in E[M|X] is exact.
        m0, m1 = _mean_M(0.0), _mean_M(1.0)
        nde = float(np.mean(_EY(1.0, m0, frame) - _EY(0.0, m0, frame)))
        nie = float(np.mean(_EY(1.0, m1, frame) - _EY(1.0, m0, frame)))
        return nde, nie

    def _four_way_inputs(om, mm, frame: pd.DataFrame) -> dict[str, float]:
        # Standardized conditional outcome means p_am = E[Y|A=a,M=m] and
        # mediator means q_a = E[M|A=a], averaged over the sample's
        # covariates (g-formula standardization). For a linear outcome
        # these reproduce VanderWeele's regression form (14.4) exactly;
        # for binary M they are the empirical 14.1b quantities.
        def _ey(a: float, m: float) -> float:
            d = frame.copy()
            d[treatment] = a
            d[mediator] = m
            return float(np.mean(np.asarray(om.predict(d))))

        def _em(a: float) -> float:
            d = frame.copy()
            d[treatment] = a
            return float(np.mean(np.asarray(mm.predict(d))))

        return dict(
            p00=_ey(0.0, 0.0), p01=_ey(0.0, 1.0),
            p10=_ey(1.0, 0.0), p11=_ey(1.0, 1.0),
            q0=_em(0.0), q1=_em(1.0),
        )

    # The difference-scale four-way decomposition evaluates the outcome
    # model at the mediator grid m∈{0,1}. That is exact for a BINARY
    # mediator (any outcome) and for a LINEAR outcome (any mediator, the
    # m=0/1 slope is the true per-unit effect), but for a CONTINUOUS
    # mediator under a NONLINEAR (logit) outcome it extrapolates off the
    # mediator's support — the components no longer sum to the total
    # effect (VanderWeele's ratio-scale decomposition, 14.5, is the right
    # tool there and is deferred). Gate it rather than emit wrong numbers.
    mediator_is_binary = set(
        np.unique(fit_df[mediator].to_numpy())
    ) <= {0.0, 1.0}
    four_way_valid = mediator_is_binary or resolved == "linear"
    four_way_unavailable_reason = None if four_way_valid else (
        "差值尺度的四分解已跳过：非线性（logit）结局下的连续中介，"
        "会把 m∈{0,1} 的代入外推到中介取值范围之外。"
        "调度改为挂上比值尺度（超额相对风险）的 four_way_ratio 块——"
        "VanderWeele 2014 eAppendix §3.3，那才是「连续中介 + 二值结局」"
        "该用的工具"
    )

    om_point, mm_point = _fit_or_refuse(
        lambda: _fit(fit_df), refusals.Design.OUTCOME_AND_MEDIATOR_FIT)
    nde_p, nie_p = _nde_nie(om_point, mm_point, fit_df)
    te_p = nde_p + nie_p
    pm_p = nie_p / te_p if te_p != 0 else float("nan")

    # The cell means ARE the four-way block: the components are a pure
    # function of them, so this one binding decides whether there is a
    # four-way split at all — the point components are derived from it
    # below, next to the bootstrap samples they get their CI from.
    fw_inputs = (
        _four_way_inputs(om_point, mm_point, fit_df) if four_way_valid else None
    )

    # Bootstrap CIs: resample rows with replacement, refit both models,
    # recompute the natural effects.
    n_rows = len(fit_df)
    nde_s: list[float] = []
    nie_s: list[float] = []
    te_s: list[float] = []
    pm_s: list[float] = []
    cde_s: list[float] = []
    intref_s: list[float] = []
    intmed_s: list[float] = []
    pie_s: list[float] = []
    fwte_s: list[float] = []
    fw_pm_s: list[float] = []
    fw_pi_s: list[float] = []
    for _ in range(n_rep):
        idx = resample_indices(n_rows, rng, groups=groups)
        bframe = fit_df.iloc[idx].reset_index(drop=True)
        try:
            om_b, mm_b = _fit(bframe)
            nb, ib = _nde_nie(om_b, mm_b, bframe)
            fwb = (
                four_way_decomposition(**_four_way_inputs(om_b, mm_b, bframe))
                if four_way_valid else None
            )
        except Exception:
            continue
        tb = nb + ib
        nde_s.append(nb)
        nie_s.append(ib)
        te_s.append(tb)
        pm_s.append(ib / tb if tb != 0 else float("nan"))
        if fwb is not None:
            cde_s.append(fwb.cde)
            intref_s.append(fwb.intref)
            intmed_s.append(fwb.intmed)
            pie_s.append(fwb.pie)
            fwte_s.append(fwb.te)
            fw_pm_s.append(
                (fwb.intmed + fwb.pie) / fwb.te if fwb.te != 0 else float("nan")
            )
            fw_pi_s.append(
                (fwb.intref + fwb.intmed) / fwb.te if fwb.te != 0 else float("nan")
            )

    half = (1.0 - ci_level) / 2.0

    def _ci(samples: list[float], point: float) -> tuple[float, float]:
        arr = np.array([s for s in samples if np.isfinite(s)], dtype=float)
        if arr.size < 2:
            return point, point
        lo = float(np.quantile(arr, half))
        hi = float(np.quantile(arr, 1.0 - half))
        # Guarantee the interval brackets the point estimate.
        return min(lo, point), max(hi, point)

    nde_lo, nde_hi = _ci(nde_s, nde_p)
    nie_lo, nie_hi = _ci(nie_s, nie_p)
    te_lo, te_hi = _ci(te_s, te_p)
    pm_lo, pm_hi = _ci(pm_s, pm_p)

    def _comp(samples: list[float], point: float) -> ComponentEstimate:
        lo, hi = _ci(samples, point)
        return ComponentEstimate(point=point, ci_lower=lo, ci_upper=hi)

    four_way: FourWayDecomposition | None = None
    if fw_inputs is not None:
        fw_point = four_way_decomposition(**fw_inputs)
        fw_pm_p = (
            (fw_point.intmed + fw_point.pie) / fw_point.te
            if fw_point.te != 0 else float("nan")
        )
        fw_pi_p = (
            (fw_point.intref + fw_point.intmed) / fw_point.te
            if fw_point.te != 0 else float("nan")
        )
        four_way = FourWayDecomposition(
            cde=_comp(cde_s, fw_point.cde),
            intref=_comp(intref_s, fw_point.intref),
            intmed=_comp(intmed_s, fw_point.intmed),
            pie=_comp(pie_s, fw_point.pie),
            te=_comp(fwte_s, fw_point.te),
            prop_mediated=_comp(fw_pm_s, fw_pm_p),
            prop_interaction=_comp(fw_pi_s, fw_pi_p),
            additive_interaction_point=fw_point.additive_interaction,
            ci_level=ci_level,
            scale="risk_difference",
            cde_mediator_reference=0,
            cell_means={k: float(v) for k, v in fw_inputs.items()},
        )

    # ``ordered_entry``: the design took each adjustment column as ONE
    # term, so a column with more than two levels was read as a number.
    # Nothing in the program claimed that ordering and ``scale`` has no
    # member that could deny it, so the fit says what it assumed.
    assumptions = (
        _assumptions_for(resolved, len(adjustment))
        + ordered_entry(df, adjustment) + (
            (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
            if cluster is not None else ()
        )
    )
    return MediationEstimate(
        nde_point=nde_p, nde_ci_lower=nde_lo, nde_ci_upper=nde_hi,
        nie_point=nie_p, nie_ci_lower=nie_lo, nie_ci_upper=nie_hi,
        te_point=te_p, te_ci_lower=te_lo, te_ci_upper=te_hi,
        proportion_mediated_point=pm_p,
        proportion_mediated_ci_lower=pm_lo,
        proportion_mediated_ci_upper=pm_hi,
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        n_rep=n_rep,
        four_way=four_way,
        four_way_unavailable_reason=four_way_unavailable_reason,
        cluster=cluster,
        form=resolved,
        form_provenance=form_provenance,
        # The design matrix's own decision, which no ``model=`` names.
        shape_provenance=shapes_settled(assumptions, ORDERED_ENTRY_SHAPE),
    )


@dataclass(frozen=True)
class MediationJointEstimate:
    """VanderWeele-Vansteelandt 2014 joint natural-effect decomposition
    through a SET of mediators M = {M_1, ..., M_k} treated as one block.

    Answers "how much of X's effect on Y flows through the mediators
    {M_1, ..., M_k} TAKEN TOGETHER" — the joint NDE, joint NIE, total
    effect, and proportion mediated. Treating the mediators as one block
    is exactly what makes the decomposition identifiable WITHOUT knowing
    (or assuming) the causal ordering AMONG the mediators: a "recanting
    witness" inside the set (a mediator that also confounds another
    mediator's effect) does not break the JOINT split — only a
    path-SPECIFIC split through one individual mediator would, and that
    is deliberately out of scope (it hits genuine non-identifiability).

    Scope (v1):
    - k >= 1 mediators. k == 1 is a valid degenerate that reproduces
      ``estimate_mediation``'s point on the linear path (both plug in the
      marginal mediator mean); dispatch routes k == 1 through the single-
      mediator estimator and only k >= 2 here.
    - Binary treatment; bool or continuous outcome (logit / OLS).
    - Outcome model ``Y ~ X + sum(M_j) + sum(X:M_j) [+ Z]``: the exposure
      × each-mediator interactions are INCLUDED (so the joint natural
      effects are correct under X-M interaction). Mediator × mediator
      interactions are NOT modelled — declared v1 scope. Under a LINEAR
      outcome this makes the joint NDE/NIE depend only on the marginal
      mediator means E[M_j|X] (the cross-mediator correlation drops out),
      so the plug-in is exact. Under a LOGIT outcome the nonlinearity
      makes the correlation matter, so the mediators are drawn JOINTLY
      (Gaussian residual copula on the k mediator models) to preserve it.
    - No four-way (CDE/INTref/INTmed/PIE) split: that construction is
      single-mediator-specific and does not generalize to a set.
    """

    nde_point: float
    nde_ci_lower: float
    nde_ci_upper: float
    nie_point: float
    nie_ci_lower: float
    nie_ci_upper: float
    te_point: float
    te_ci_lower: float
    te_ci_upper: float
    proportion_mediated_point: float
    proportion_mediated_ci_lower: float
    proportion_mediated_ci_upper: float
    ci_level: float
    method: str            # "mediation_joint_linear" | "mediation_joint_logit"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    mediators: tuple[str, ...]
    treatment: str
    outcome: str
    n_rep: int
    # Sufficient statistics for the verifier's STRONG re-derivation on the
    # LINEAR path: the outcome-model coefficients (beta_x; per-mediator main
    # beta_j and interaction gamma_j) plus each mediator's standardized means
    # q_j0 = E[M_j|X=0], q_j1 = E[M_j|X=1]. From these the verifier re-derives
    #   NDE = beta_x + sum_j gamma_j * q_j0
    #   NIE = sum_j (beta_j + gamma_j) * (q_j1 - q_j0)
    # independently (the joint analog of four_way_ratio recording its
    # coefficients). On the logit path these still record the fit, but the
    # reported NDE/NIE come from a Monte-Carlo joint integration over M, so
    # only the construction identities (TE = NDE+NIE, prop = NIE/TE) are
    # re-checkable there — the honest ceiling, same as the single-mediator
    # logit path.
    sufficient_statistics: dict
    # Controlled direct effect for the mediator SET held fixed at a reference
    # level (the VanderWeele CDE generalized to the whole block). Reported at
    # the two binary corner references m*=0 (all mediators at control) and
    # m*=1 (all at treated):
    #   {"reference_control": {"mediator_level": 0.0, "point", "ci_lower",
    #    "ci_upper"}, "reference_treated": {"mediator_level": 1.0, ...}}
    # On the LINEAR path CDE(m*) = beta_x + sum_j gamma_j * m* is an exact
    # functional of the recorded outcome coefficients (m*=0 -> beta_x), which
    # verify_mediation_numeric re-derives independently; on the LOGIT path it
    # is a Monte-Carlo plug-in over the sample covariates (construction
    # ceiling). Arbitrary / observed-grid reference values are a follow-on.
    cde: dict = field(default_factory=dict)
    cluster: str | None = None
    #: The outcome model's shape, and who settled it — see
    #: :mod:`themis.estimation.form`. Both empty until the caller's
    #: ``model=`` has been read.
    form: str = ""
    form_provenance: str = ""
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def _joint_mediation_assumptions(
    model: str, n_adj: int, is_logit: bool, cluster: str | None,
) -> tuple[str, ...]:
    a: tuple[str, ...] = (
        "sequential_ignorability_treatment_and_mediator_set",
        "no_confounder_of_mediatorset_outcome_affected_by_treatment_outside_the_set",
        "vanderweele_vansteelandt_2014_joint_natural_effect_conditions",
        "no_mediator_mediator_interaction_in_outcome_model",
    )
    if model == "linear":
        a = a + ("linear_outcome_regression",)
    elif model == "logit":
        a = a + ("logit_outcome_regression",)
    if is_logit:
        a = a + ("mediators_drawn_jointly_via_gaussian_residual_copula",)
    if n_adj > 0:
        a = a + (
            "adjustment_set_blocks_mediatorset_outcome_backdoor_given_treatment",
        )
    if cluster is not None:
        a = a + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return a


def estimate_mediation_joint(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    adjustment: tuple[str, ...] = (),
    model: str = "auto",
    n_rep: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> MediationJointEstimate:
    """Joint natural-effect decomposition through a mediator SET.

    See ``MediationJointEstimate`` for scope. The estimator mirrors
    ``estimate_mediation`` but with M a vector:

    - Outcome model ``Y ~ X + sum(M_j) + sum(X:M_j) [+ Z]``.
    - One mediator model ``M_j ~ X [+ Z]`` per mediator.
    - g-formula natural effects: NDE = E[Y_{1,M0} - Y_{0,M0}],
      NIE = E[Y_{1,M1} - Y_{1,M0}] with M_x drawn from P(M | X=x). On a
      LINEAR outcome the marginal means E[M_j|X] are plugged in (exact,
      correlation-free). On a LOGIT outcome the k mediators are drawn
      JOINTLY from a Gaussian residual copula (mean = fitted E[M_j|X],
      covariance = the k×k residual covariance of the mediator models),
      preserving their conditional correlation through the nonlinearity.
    - Percentile bootstrap CIs (optionally cluster bootstrap).

    Raises ``ValueError`` on an empty mediator set or a duplicate.
    """
    mediators = tuple(mediators)
    if len(mediators) == 0:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            "estimate_mediation_joint requires at least one mediator",
        )
    if len(set(mediators)) != len(mediators):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"duplicate mediator in {mediators!r}",
            mediators=list(mediators),
        )

    required = {treatment, outcome, *mediators, *adjustment}
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
        quantity_columns=(treatment, outcome, *mediators),
    )
    df = contract.data

    resolved, form_provenance = outcome_form(model, df[outcome], logistic="logit")

    fit_df = df.copy()
    for c in [c for c in fit_df.columns if fit_df[c].dtype == bool]:
        fit_df[c] = fit_df[c].astype(float)

    adj_term = " + ".join(adjustment) if adjustment else ""
    sep = " + " if adj_term else ""

    med_main = " + ".join(mediators)
    med_inter = " + ".join(f"{treatment}:{m}" for m in mediators)
    outcome_formula = (
        f"{outcome} ~ {treatment} + {med_main} + {med_inter}{sep}{adj_term}"
    )
    if resolved == "logit":
        is_logit = True
        method = "mediation_joint_logit"
    elif resolved == "linear":
        is_logit = False
        method = "mediation_joint_linear"
    else:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"unknown model {model!r}; joint mediation fits 'logit' or "
            f"'linear'",
            model=model,
        )

    mediator_formulas = [f"{m} ~ {treatment}{sep}{adj_term}" for m in mediators]

    rng = np.random.default_rng(random_state)
    n_sim = 100

    def _fit(frame: pd.DataFrame):
        if is_logit:
            om = sm.Logit.from_formula(outcome_formula, data=frame).fit(disp=0)
        else:
            om = sm.OLS.from_formula(outcome_formula, data=frame).fit()
        mms = [
            sm.OLS.from_formula(f, data=frame).fit() for f in mediator_formulas
        ]
        return om, mms

    def _mu(mm, frame: pd.DataFrame, xval: float):
        d = frame.copy()
        d[treatment] = xval
        return np.asarray(mm.predict(d))

    def _nde_nie(om, mms, frame: pd.DataFrame) -> tuple[float, float]:
        def _EY(xval: float, m_vecs, base: pd.DataFrame):
            d = base.copy()
            d[treatment] = xval
            for name, vals in zip(mediators, m_vecs):
                d[name] = vals
            return np.asarray(om.predict(d))

        if is_logit:
            mu0 = [_mu(mm, frame, 0.0) for mm in mms]
            mu1 = [_mu(mm, frame, 1.0) for mm in mms]
            # Joint residual covariance across the k mediator models — the
            # cross-mediator dependence the nonlinear outcome is sensitive to.
            resid = np.column_stack([np.asarray(mm.resid) for mm in mms])
            sigma = np.atleast_2d(np.cov(resid, rowvar=False, ddof=1))
            k = len(frame)
            zeros = np.zeros(len(mediators))
            big = pd.concat([frame] * n_sim, ignore_index=True)
            d0 = rng.multivariate_normal(zeros, sigma, size=n_sim * k)
            d1 = rng.multivariate_normal(zeros, sigma, size=n_sim * k)
            m0 = [np.tile(mu0[i], n_sim) + d0[:, i] for i in range(len(mediators))]
            m1 = [np.tile(mu1[i], n_sim) + d1[:, i] for i in range(len(mediators))]
            nde = float(np.mean(_EY(1.0, m0, big) - _EY(0.0, m0, big)))
            nie = float(np.mean(_EY(1.0, m1, big) - _EY(1.0, m0, big)))
            return nde, nie
        # Linear outcome: E[Y|X,M] linear in each M_j and no M_j:M_l term,
        # so plugging in the marginal means E[M_j|X] is exact (the
        # cross-mediator correlation cancels in the expectation).
        m0 = [_mu(mm, frame, 0.0) for mm in mms]
        m1 = [_mu(mm, frame, 1.0) for mm in mms]
        nde = float(np.mean(_EY(1.0, m0, frame) - _EY(0.0, m0, frame)))
        nie = float(np.mean(_EY(1.0, m1, frame) - _EY(1.0, m0, frame)))
        return nde, nie

    def _cde_at(om, frame: pd.DataFrame, mstar: float) -> float:
        """CDE-for-the-set holding EVERY mediator fixed at ``mstar``:
        E[Y | do(X=1, M=m*)] - E[Y | do(X=0, M=m*)], g-formula plug-in
        over the sample covariates. Linear outcome collapses to the exact
        beta_x + sum_j gamma_j * m* (Z cancels); logit is the MC-free
        analytic plug-in over the empirical Z (the covariate integration is
        the sample mean of predicted probabilities), no mediator draw needed
        because the mediators are HELD at m* rather than integrated out.
        """
        d1 = frame.copy()
        d0 = frame.copy()
        d1[treatment] = 1.0
        d0[treatment] = 0.0
        for name in mediators:
            d1[name] = mstar
            d0[name] = mstar
        return float(np.mean(np.asarray(om.predict(d1)) - np.asarray(om.predict(d0))))

    def _coef(params, *cands) -> float:
        for c in cands:
            if c in params.index:
                return float(params[c])
        raise KeyError(f"none of {cands} in fitted outcome coefficients")

    om_point, mms_point = _fit_or_refuse(
        lambda: _fit(fit_df), refusals.Design.OUTCOME_AND_MEDIATOR_FIT)
    nde_p, nie_p = _nde_nie(om_point, mms_point, fit_df)
    te_p = nde_p + nie_p
    pm_p = nie_p / te_p if te_p != 0 else float("nan")
    cde0_p = _cde_at(om_point, fit_df, 0.0)
    cde1_p = _cde_at(om_point, fit_df, 1.0)

    # Sufficient statistics for the linear-path strong re-derivation.
    params = om_point.params
    suff = {
        "outcome_coefficients": {
            "treatment": _coef(params, treatment),
            "mediators": {
                m: _coef(params, m) for m in mediators
            },
            "interactions": {
                m: _coef(params, f"{treatment}:{m}", f"{m}:{treatment}")
                for m in mediators
            },
        },
        "mediator_means": {
            m: {
                "m0": float(np.mean(_mu(mm, fit_df, 0.0))),
                "m1": float(np.mean(_mu(mm, fit_df, 1.0))),
            }
            for m, mm in zip(mediators, mms_point)
        },
    }

    n_rows = len(fit_df)
    nde_s: list[float] = []
    nie_s: list[float] = []
    te_s: list[float] = []
    pm_s: list[float] = []
    cde0_s: list[float] = []
    cde1_s: list[float] = []
    for _ in range(n_rep):
        idx = resample_indices(n_rows, rng, groups=groups)
        bframe = fit_df.iloc[idx].reset_index(drop=True)
        try:
            om_b, mms_b = _fit(bframe)
            nb, ib = _nde_nie(om_b, mms_b, bframe)
            c0b = _cde_at(om_b, bframe, 0.0)
            c1b = _cde_at(om_b, bframe, 1.0)
        except Exception:
            continue
        tb = nb + ib
        nde_s.append(nb)
        nie_s.append(ib)
        te_s.append(tb)
        pm_s.append(ib / tb if tb != 0 else float("nan"))
        cde0_s.append(c0b)
        cde1_s.append(c1b)

    half = (1.0 - ci_level) / 2.0

    def _ci(samples: list[float], point: float) -> tuple[float, float]:
        arr = np.array([s for s in samples if np.isfinite(s)], dtype=float)
        if arr.size < 2:
            return point, point
        lo = float(np.quantile(arr, half))
        hi = float(np.quantile(arr, 1.0 - half))
        return min(lo, point), max(hi, point)

    nde_lo, nde_hi = _ci(nde_s, nde_p)
    nie_lo, nie_hi = _ci(nie_s, nie_p)
    te_lo, te_hi = _ci(te_s, te_p)
    pm_lo, pm_hi = _ci(pm_s, pm_p)
    cde0_lo, cde0_hi = _ci(cde0_s, cde0_p)
    cde1_lo, cde1_hi = _ci(cde1_s, cde1_p)
    cde = {
        "reference_control": {
            "mediator_level": 0.0,
            "point": cde0_p, "ci_lower": cde0_lo, "ci_upper": cde0_hi,
        },
        "reference_treated": {
            "mediator_level": 1.0,
            "point": cde1_p, "ci_lower": cde1_lo, "ci_upper": cde1_hi,
        },
    }

    assumptions = _joint_mediation_assumptions(
        resolved, len(adjustment), is_logit, cluster,
    )
    return MediationJointEstimate(
        nde_point=nde_p, nde_ci_lower=nde_lo, nde_ci_upper=nde_hi,
        nie_point=nie_p, nie_ci_lower=nie_lo, nie_ci_upper=nie_hi,
        te_point=te_p, te_ci_lower=te_lo, te_ci_upper=te_hi,
        proportion_mediated_point=pm_p,
        proportion_mediated_ci_lower=pm_lo,
        proportion_mediated_ci_upper=pm_hi,
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        mediators=tuple(mediators),
        treatment=treatment,
        outcome=outcome,
        n_rep=n_rep,
        sufficient_statistics=suff,
        cde=cde,
        cluster=cluster,
        form=resolved,
        form_provenance=form_provenance,
        # Two shapes the link did not settle: the copula is how the mediators
        # are DRAWN under the link the caller picked, and no value of
        # ``model=`` names one; the no-interaction restriction is declared
        # whatever shape the outcome model ended up with.
        shape_provenance=shapes_settled(
            assumptions,
            ("mediators_drawn_jointly_via_gaussian_residual_copula",
             Provenance.DEFAULT),
            ("no_mediator_mediator_interaction_in_outcome_model",
             Provenance.INHERENT),
        ),
    )


@dataclass(frozen=True)
class CDEEstimate:
    """Phase 7.5 — Controlled Direct Effect at fixed M=m*.

    CDE(x, x', m*) = E[Y | do(X=x), do(M=m*)] - E[Y | do(X=x'), do(M=m*)]

    Differences from NDE/NIE:
    - CDE fixes M at a chosen level m* (the "control" for the
      mediator); NDE/NIE take expectations over M's natural distribution.
    - CDE only requires the X→Y identification given M (one-step
      no-unmeasured-confounders), not Pearl's full sequential
      ignorability — a strictly weaker assumption set.
    - Per VanderWeele 2015 ch.2.3.3, CDE is the policy-relevant
      direct effect when M is itself an intervention target (e.g.
      "what would the effect of X on Y look like if we forced
      everyone's M to m*?").
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                   # "cde_linear" | "cde_logit"
    # The three levels the plug-in is evaluated at. They are numeric
    # levels of numeric columns: the treatment and the mediator enter the
    # design as themselves and every level is pushed in through
    # ``float()`` — so ``SupportsFloat`` is what this estimator actually
    # accepts (bool / int / float / numpy scalar), recorded verbatim. The
    # adjustment columns are a separate half of the design and are not
    # under this constraint; an unordered covariate is usable here, an
    # unordered MEDIATOR is not, because there is no m* to set it to.
    mediator_value: SupportsFloat        # the m* the CDE was computed at
    treatment_low: SupportsFloat         # the x' (control treatment level)
    treatment_high: SupportsFloat        # the x (treated level)
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]
    # Variance concern, not a model node: when set, the bootstrap CI was
    # computed by resampling whole clusters (pairs cluster bootstrap)
    # rather than i.i.d. rows. None → ordinary i.i.d. bootstrap.
    cluster: str | None = None
    #: The outcome model's shape, and who settled it — see
    #: :mod:`themis.estimation.form`. Both empty until the caller's
    #: ``model=`` has been read.
    form: str = ""
    form_provenance: str = ""
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def estimate_cde(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    mediator_value: SupportsFloat,
    adjustment: tuple[str, ...] = (),
    treatment_low: SupportsFloat = False,
    treatment_high: SupportsFloat = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CDEEstimate:
    """Plug-in g-formula CDE at fixed ``M = mediator_value``.

    Steps:
    1. Fit ``E[Y | X, M, Z]`` with sklearn (linear if Y continuous,
       logistic if Y bool).
    2. For each row i, predict at ``(X=high, M=m*, Z=Z_i)`` and
       ``(X=low, M=m*, Z=Z_i)``; the CDE is the sample-mean difference.
    3. Percentile bootstrap CI (same pattern as backdoor.py).

    ``cluster`` (optional column name) switches the bootstrap from
    i.i.d. rows to a pairs cluster bootstrap (whole clusters resampled
    with replacement) — the right variance under within-cluster
    dependence (families / repeated measures / schools). ``None``
    reproduces the i.i.d. bootstrap byte-for-byte. The cluster column
    is a variance concern, NOT part of the causal model: it never
    enters the outcome regression or the data hash.

    Returns ``CDEEstimate``. Does NOT require statsmodels — purely
    sklearn — because the statsmodels Mediation API doesn't expose
    do(M=m*) plug-in directly.
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    required = {treatment, outcome, mediator, *adjustment}
    # Pull cluster labels from the raw frame (uncoerced) before the
    # contract subsets to model columns; positionally aligned with df.
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
        quantity_columns=(treatment, outcome, mediator),
    )
    df = contract.data

    resolved, form_provenance = outcome_form(model, df[outcome], logistic="logit")

    # Two halves, and they answer different questions. The treatment and
    # the mediator are read as numbers on purpose: the CDE is DEFINED by
    # setting them, and the levels arrive as ``float(mediator_value)``.
    # What the adjustment columns are is not this estimator's to decide —
    # ``design_block`` reads it off the frame, so a covariate whose levels
    # carry no order enters as one indicator per level. Keeping the halves
    # apart is also what keeps indices 0 and 1 meaning what the
    # substitutions below say they mean when a covariate widens.
    set_cols = [treatment, mediator]

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        X_full = np.hstack([
            sample[set_cols].to_numpy(dtype=float),
            design_block(sample, adjustment),
        ])
        y = sample[outcome].to_numpy()
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            X_high = X_full.copy()
            X_low = X_full.copy()
            # Replace the treatment column (index 0) and mediator (index 1)
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            X_high = X_full.copy()
            X_low = X_full.copy()
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            try:
                draws[i] = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    method = f"cde_{resolved}"
    assumptions: tuple[str, ...] = (
        "no_unmeasured_confounder_x_y_given_m_and_adjustment",
        "no_unmeasured_confounder_m_y_given_x_and_adjustment",
        "consistency_of_potential_outcomes",
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_backdoors",
        )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return CDEEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method=method,
        mediator_value=mediator_value,
        treatment_low=treatment_low,
        treatment_high=treatment_high,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        assumptions=assumptions,
        cluster=cluster,
        form=resolved,
        form_provenance=form_provenance,
    )


@dataclass(frozen=True)
class CDEChainEstimate:
    """Phase 7.5+ — Controlled Direct Effect for a chain of
    N mediators X → M_1 → M_2 → ... → M_n → Y, fixing each M_i at
    a chosen reference value m_i*.

    CDE_chain(x, x', m1*, m2*, ..., mn*) =
        E[Y | do(X=x), do(M_1=m1*), do(M_2=m2*), ..., do(M_n=mn*)]
      - E[Y | do(X=x'), do(M_1=m1*), ..., do(M_n=mn*)]

    Differences from single-M ``CDEEstimate``:
    - ``mediators`` is a tuple of predicate names (chain order)
    - ``mediator_values`` is a parallel tuple of reference values
      (m_i* for each M_i)
    - method is "cde_chain_linear" / "cde_chain_logit"

    Same identification footing as single-M CDE per VanderWeele 2015
    ch.5 chain extension: fits a single outcome model
    ``Y ~ X + M_1 + ... + M_n + Z`` and plug-in evaluates at the
    chain-fixed mediator values.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                         # "cde_chain_linear" | "cde_chain_logit"
    mediators: tuple[str, ...]          # chain order
    # Same numeric-level contract as ``CDEEstimate``: every value here is
    # pushed into a float design matrix through ``float()``.
    mediator_values: tuple[SupportsFloat, ...]   # parallel to mediators
    treatment_low: SupportsFloat
    treatment_high: SupportsFloat
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]
    # Variance concern, not a model node: when set, the bootstrap CI was
    # computed by resampling whole clusters (pairs cluster bootstrap)
    # rather than i.i.d. rows. None → ordinary i.i.d. bootstrap.
    cluster: str | None = None
    #: The outcome model's shape, and who settled it — see
    #: :mod:`themis.estimation.form`. Both empty until the caller's
    #: ``model=`` has been read.
    form: str = ""
    form_provenance: str = ""
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def estimate_cde_chain(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    mediator_values: tuple[SupportsFloat, ...],
    adjustment: tuple[str, ...] = (),
    treatment_low: SupportsFloat = False,
    treatment_high: SupportsFloat = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CDEChainEstimate:
    """Plug-in g-formula CDE for a chain of N mediators, each fixed
    at a chosen value.

    Steps:
    1. Fit ``E[Y | X, M_1, ..., M_n, Z]`` with sklearn.
    2. For each row i, predict at
       (X=high, M_i=m_i* for each i, Z=Z_i) vs
       (X=low, M_i=m_i* for each i, Z=Z_i).
       Sample-mean difference is the CDE_chain.
    3. Percentile bootstrap CI.

    For N=1 this is exactly equivalent to ``estimate_cde``; the
    separate function exists so callers signal chain semantics
    explicitly and the audit trail records the chain-CDE assumption
    set (which adds "no unmeasured confounder between successive
    mediators given X and Z").

    ``cluster`` (optional column name) switches the bootstrap from
    i.i.d. rows to a pairs cluster bootstrap (whole clusters resampled
    with replacement) — the right variance under within-cluster
    dependence. ``None`` reproduces the i.i.d. bootstrap byte-for-byte.
    The cluster column is a variance concern, NOT part of the causal
    model: it never enters the outcome regression or the data hash.

    Raises ``ValueError`` when:
    - ``mediators`` and ``mediator_values`` have different length
    - ``mediators`` is empty (use ``estimate_backdoor_ate`` for the
      no-mediator case)
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    if len(mediators) != len(mediator_values):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"mediators ({len(mediators)}) and mediator_values "
            f"({len(mediator_values)}) length mismatch",
            n_mediators=len(mediators), n_values=len(mediator_values),
        )
    if len(mediators) == 0:
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            "estimate_cde_chain requires at least one mediator; use "
            "estimate_backdoor_ate for the no-mediator case",
        )

    required = {treatment, outcome, *mediators, *adjustment}
    # Pull cluster labels from the raw frame (uncoerced) before the
    # contract subsets to model columns; positionally aligned with df.
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
        quantity_columns=(treatment, outcome, *mediators),
    )
    df = contract.data

    resolved, form_provenance = outcome_form(model, df[outcome], logistic="logit")

    # See the single-mediator estimator above: the columns the plug-in
    # SETS are read as numbers, the columns it adjusts for are read as
    # whatever they are, and the split is what keeps the indices below
    # pointing at the treatment and the mediators.
    set_cols = [treatment, *mediators]

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        X_full = np.hstack([
            sample[set_cols].to_numpy(dtype=float),
            design_block(sample, adjustment),
        ])
        y = sample[outcome].to_numpy()
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            X_high = X_full.copy()
            X_low = X_full.copy()
            # Substitute treatment column (index 0) and each mediator
            # column (indices 1..len(mediators)).
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            for i, mv in enumerate(mediator_values):
                X_high[:, 1 + i] = float(mv)
                X_low[:, 1 + i] = float(mv)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            X_high = X_full.copy()
            X_low = X_full.copy()
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            for i, mv in enumerate(mediator_values):
                X_high[:, 1 + i] = float(mv)
                X_low[:, 1 + i] = float(mv)
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            try:
                draws[i] = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    method = f"cde_chain_{resolved}"
    assumptions: tuple[str, ...] = (
        "no_unmeasured_confounder_x_y_given_chain_and_adjustment",
        "no_unmeasured_confounder_between_successive_mediators",
        "consistency_of_potential_outcomes",
        "outcome_model_correctly_specified_at_chain_fixed_values",
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_chain_backdoors",
        )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return CDEChainEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method=method,
        mediators=tuple(mediators),
        mediator_values=tuple(mediator_values),
        treatment_low=treatment_low,
        treatment_high=treatment_high,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        assumptions=assumptions,
        cluster=cluster,
        form=resolved,
        form_provenance=form_provenance,
        # Declared beside the rest of what the chain decomposition is derived
        # under, whatever shape the outcome model ended up with.
        shape_provenance=shapes_settled(
            assumptions,
            ("outcome_model_correctly_specified_at_chain_fixed_values",
             Provenance.INHERENT),
        ),
    )


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    common: tuple[str, ...] = (
        "sequential_ignorability_treatment_and_mediator",
        "no_intermediate_confounder_affected_by_treatment",
        "pearl_2001_four_conditions_hold_on_the_graph",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logit":
        common = common + ("logit_outcome_regression",)
    if n_adj > 0:
        common = common + (
            "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment",
        )
    return common
