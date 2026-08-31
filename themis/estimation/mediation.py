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
from ..refusals import Refusal, Remedy
from ..refusals import EstimatorFailure
from .contract import validate_data
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES, outcome_form, shapes_settled
from .declared import ORDERED_ENTRY_SHAPE, design_block, ordered_entry
from .four_way import four_way_decomposition
from .resample import Draws, cluster_labels, resample_indices


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
            recorded={"diagnostic": str(exc)},
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
    #: The replicates every interval above was taken over, and what became
    #: of the rest — see :class:`themis.estimation.resample.Draws`. This
    #: class used to carry ``n_rep``, the number ASKED for, which a refit
    #: that fails on a resample makes into a different number from the one
    #: the intervals rest on. ``None`` when no bootstrap ran.
    draws: "Draws | None"
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
            Refusal.UNKNOWN_OPTION,
            option="model", given=model, known=["logit", "linear"],
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
    draws = Draws(n_rep) if n_rep > 0 else None
    if draws is not None:
        for _ in draws:
            idx = resample_indices(n_rows, rng, groups=groups)
            bframe = fit_df.iloc[idx].reset_index(drop=True)
            try:
                om_b, mm_b = _fit(bframe)
                nb, ib = _nde_nie(om_b, mm_b, bframe)
                fwb = (
                    four_way_decomposition(**_four_way_inputs(om_b, mm_b, bframe))
                    if four_way_valid else None
                )
            except EstimatorFailure as exc:
                draws.unusable(exc.failure_type)
                continue
            except Exception:
                draws.unusable()
                continue
            draws.usable()
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
                    (fwb.intmed + fwb.pie) / fwb.te
                    if fwb.te != 0 else float("nan")
                )
                fw_pi_s.append(
                    (fwb.intref + fwb.intmed) / fwb.te
                    if fwb.te != 0 else float("nan")
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
        draws=draws,
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
    #: The replicates every interval above was taken over, and what became
    #: of the rest — see :class:`themis.estimation.resample.Draws`, and the
    #: single-mediator class for why it is not ``n_rep``.
    draws: "Draws | None"
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
            Refusal.TOO_FEW_INPUTS,
            what="mediators=", needed=1, given=len(mediators),
        )
    if len(set(mediators)) != len(mediators):
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="mediators=", given=list(mediators),
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
            Refusal.UNKNOWN_OPTION,
            option="model", given=model, known=["logit", "linear"],
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
    draws = Draws(n_rep) if n_rep > 0 else None
    if draws is not None:
        for _ in draws:
            idx = resample_indices(n_rows, rng, groups=groups)
            bframe = fit_df.iloc[idx].reset_index(drop=True)
            try:
                om_b, mms_b = _fit(bframe)
                nb, ib = _nde_nie(om_b, mms_b, bframe)
                c0b = _cde_at(om_b, bframe, 0.0)
                c1b = _cde_at(om_b, bframe, 1.0)
            except EstimatorFailure as exc:
                draws.unusable(exc.failure_type)
                continue
            except Exception:
                draws.unusable()
                continue
            draws.usable()
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
        draws=draws,
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
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
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


@dataclass(frozen=True)
class CDELevel:
    """The controlled direct effect at one level of the mediator.

    ``mediator_level`` is a float and not the caller's own value: it is
    where the design matrix was evaluated, and a level that arrived as a
    bool or a numpy scalar entered the plug-in through ``float()``. What
    the caller passed is kept once, on the curve, so the two can be
    compared rather than one of them silently standing for the other.
    """

    mediator_level: float
    point: float
    ci_lower: float | None
    ci_upper: float | None
    #: The two standardized quantities the contrast is a difference of —
    #: E[Y | do(X=high), do(M=level)] and the same at ``low``. Carried
    #: because a number that is only ever compared against itself cannot be
    #: audited: with its two parts recorded, altering the contrast makes it
    #: disagree with what it was made from.
    risk_treated: float = 0.0
    risk_control: float = 0.0


@dataclass(frozen=True)
class CDECurveEstimate:
    """The controlled direct effect as what it is — a function of the
    level the mediator is held at.

    One outcome model, one bootstrap, and one entry per level. The levels
    are ordered as the caller gave them, so a curve read at quantiles
    arrives in increasing order and one read at a column's own values
    arrives in the order that column enumerates.
    """

    levels: tuple[CDELevel, ...]
    #: What the auditor re-derives from. On the LINEAR path the covariate
    #: terms cancel out of the treated-minus-control difference, so
    #: CDE(m*) = θ_x + θ_xm·m* and these coefficients close the loop for
    #: every level at once. On the logit path the standardization is not
    #: collapsible and the risks on each level are the ceiling — the same
    #: honest ceiling this file's natural-effect half declares for its own
    #: Monte-Carlo integration.
    sufficient_statistics: dict
    #: Whether the sample HOLDS every level the curve was read at. False
    #: says the levels are quantiles of a continuum, so each number is the
    #: outcome model's answer at a place no row sits exactly on. Both are
    #: legitimate and they are not the same claim.
    levels_observed: bool
    ci_level: float
    method: str                   # "cde_linear" | "cde_logit"
    #: The levels as the caller named them, before ``float()``. See
    #: :class:`CDELevel`.
    given_levels: tuple[SupportsFloat, ...]
    treatment_low: SupportsFloat
    treatment_high: SupportsFloat
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]
    cluster: str | None = None
    draws: "Draws | None" = None
    form: str = ""
    form_provenance: str = ""
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES

    @property
    def varies(self) -> bool:
        """Whether the direct effect changes across the levels at all.

        The question a reader has as soon as they are handed more than one
        number, and the one the exposure-mediator interaction decides. A
        flat curve is an answer — it says holding the mediator anywhere
        gives the same direct effect — and it is not the same answer as a
        curve that crosses zero.
        """
        pts = [level.point for level in self.levels]
        return len(pts) > 1 and max(pts) != min(pts)


def estimate_cde_curve(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    mediator_values: tuple[SupportsFloat, ...],
    adjustment: tuple[str, ...] = (),
    treatment_low: SupportsFloat = False,
    treatment_high: SupportsFloat = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
    levels_observed: bool = True,
) -> CDECurveEstimate:
    """Plug-in g-formula CDE at each level the mediator is held at.

    Steps:
    1. Fit ``E[Y | X, M, X·M, Z]`` with sklearn (linear if Y continuous,
       logistic if Y bool).
    2. For each row i and each level m*, predict at
       ``(X=high, M=m*, Z=Z_i)`` and ``(X=low, M=m*, Z=Z_i)``; the CDE at
       that level is the sample-mean difference.
    3. Percentile bootstrap CI (same pattern as backdoor.py), one
       resample serving every level.

    **The curve rather than a point is the estimand's own shape.** A
    controlled direct effect is indexed by the level the mediator is held
    at, and under an exposure-mediator interaction it varies with that
    level — can change sign across it. A route that reported one number
    would have to pick the level, and picking it is the caller's decision
    about a policy, not the estimator's about a default.
    ``estimate_cde`` is this function at one level, for a caller who has
    made that decision.

    ``levels_observed`` records whether every level asked for is one the
    sample holds. It is carried rather than inferred, because at the
    quantiles of a continuum the answer is a model's, and a reader is
    entitled to be told which of the two they are looking at.

    ``cluster`` (optional column name) switches the bootstrap from
    i.i.d. rows to a pairs cluster bootstrap (whole clusters resampled
    with replacement) — the right variance under within-cluster
    dependence (families / repeated measures / schools). ``None``
    reproduces the i.i.d. bootstrap byte-for-byte. The cluster column
    is a variance concern, NOT part of the causal model: it never
    enters the outcome regression or the data hash.

    Does NOT require statsmodels — purely sklearn — because the
    statsmodels Mediation API doesn't expose the do(M=m*) plug-in.
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
    # carry no order enters as one indicator per level.
    def _design(x: np.ndarray, m: np.ndarray, block: np.ndarray) -> np.ndarray:
        """Treatment, mediator, their product, then the covariates.

        One construction serves the fit and both counterfactual rebuilds,
        which is what keeps the product from being left at a level the two
        columns it is a product OF have moved off. That staleness is not a
        hypothetical: it is the defect this file's natural-effect half
        re-predicts on rebuilt rows to avoid, named where it does so.

        The product is here at all because ``mediator_value`` is a
        parameter of this function. Without it the fitted CDE cannot depend
        on the level the mediator is held at, while the estimand it names
        does whenever exposure and mediator interact — so the argument
        would be inert, and measurably was: on a frame with a true
        CDE(m*) = 1 + 2m* this returned one number for every m* asked of it.
        """
        return np.column_stack([x, m, x * m, block])

    # Every level the caller asked for, off ONE fit and through ONE
    # bootstrap. A CDE is a function of the level the mediator is held at,
    # so a caller reading it at five levels is asking one question five
    # times, not five questions — and refitting per level would spend five
    # bootstraps to answer it, then report intervals whose disagreement is
    # partly resampling noise between them rather than curvature.
    levels = tuple(float(m) for m in mediator_values)

    def _fit(sample: pd.DataFrame) -> tuple[np.ndarray, list[float],
                                            list[float], list[float]]:
        """One fit, and everything read off it: the per-level contrast, the
        two standardized risks each contrast is a difference of, and the
        coefficients the linear path's contrast is a closed form of.

        The risks and the coefficients exist for the auditor. A contrast on
        its own can only be re-checked against itself; with the two risks it
        was made from, a tamper of the reported number stops agreeing with
        its own parts, and on the linear path the coefficients close the
        loop entirely — the covariate terms cancel out of the difference, so
        CDE(m*) = θ_x + θ_xm·m* re-derives every level from two numbers.
        """
        block = design_block(sample, adjustment)
        x_obs = sample[treatment].to_numpy(dtype=float)
        m_obs = sample[mediator].to_numpy(dtype=float)
        X_full = _design(x_obs, m_obs, block)
        y = sample[outcome].to_numpy()
        ones = np.ones(len(sample))
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            model_fit = LogisticRegression(max_iter=1000, solver="lbfgs")
            model_fit.fit(X_full, y_int)
            coefs = [float(c) for c in np.ravel(model_fit.coef_)]

            def _at(design: np.ndarray) -> np.ndarray:
                return model_fit.predict_proba(design)[:, 1]
        elif resolved == "linear":
            model_fit = LinearRegression()
            model_fit.fit(X_full, y.astype(float))
            coefs = [float(c) for c in np.ravel(model_fit.coef_)]

            def _at(design: np.ndarray) -> np.ndarray:
                return np.asarray(model_fit.predict(design))
        else:
            raise ValueError(f"unknown model {model!r}")
        diffs, highs, lows = [], [], []
        for level in levels:
            held = ones * level
            hi = float(np.mean(
                _at(_design(ones * float(treatment_high), held, block))))
            lo = float(np.mean(
                _at(_design(ones * float(treatment_low), held, block))))
            highs.append(hi)
            lows.append(lo)
            diffs.append(hi - lo)
        return np.asarray(diffs, dtype=float), highs, lows, coefs

    def _fit_predict_diff(sample: pd.DataFrame) -> np.ndarray:
        return _fit(sample)[0]

    points, risks_treated, risks_control, coefficients = _fit(df)

    lowers: list[float | None] = [None] * len(levels)
    uppers: list[float | None] = [None] * len(levels)
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        rng = np.random.default_rng(random_state)
        n = len(df)
        values: list[np.ndarray] = []
        for _ in draws:
            idx = resample_indices(n, rng, groups=groups)
            try:
                value = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws.unusable()
                continue
            if not np.all(np.isfinite(value)):
                # One unusable level makes the whole replicate unusable, so
                # every level's interval stands on the same draws. Keeping a
                # partial replicate would give the levels different effective
                # sample sizes and nothing on the block would say which.
                draws.unusable()
                continue
            values.append(value)
            draws.usable()
        if draws.enough:
            alpha = (1 - ci_level) / 2
            arr = np.vstack(values)
            lowers = [float(q) for q in np.quantile(arr, alpha, axis=0)]
            uppers = [float(q) for q in np.quantile(arr, 1 - alpha, axis=0)]

    method = f"cde_{resolved}"
    assumptions: tuple[str, ...] = (
        "no_unmeasured_confounder_x_y_given_m_and_adjustment",
        "no_unmeasured_confounder_m_y_given_x_and_adjustment",
        "consistency_of_potential_outcomes",
    )
    # Which regression the plug-in was evaluated on. The sibling estimator
    # in this file has always declared this and the CDE never did, so a
    # reader comparing the two ledgers was shown a model shape for the
    # natural effects and none for the controlled one — from the same run,
    # on the same frame.
    assumptions = assumptions + (
        ("linear_outcome_regression",) if resolved == "linear"
        else ("logit_outcome_regression",)
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_backdoors",
        ) + ordered_entry(df, adjustment)
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )
    if not levels_observed:
        assumptions = assumptions + (
            "mediator_levels_read_at_quantiles_of_a_continuum",
        )

    return CDECurveEstimate(
        levels=tuple(
            CDELevel(
                mediator_level=level,
                point=float(pt),
                ci_lower=lo,
                ci_upper=hi,
                risk_treated=rt,
                risk_control=rc,
            )
            for level, pt, lo, hi, rt, rc in zip(
                levels, points, lowers, uppers,
                risks_treated, risks_control)
        ),
        # The design's coefficients, in its own column order: treatment,
        # mediator, their product, then whatever ``design_block`` made of
        # the covariates. Recorded so the linear path's curve can be
        # re-derived rather than merely re-checked against itself.
        sufficient_statistics={
            "outcome_coefficients": list(coefficients),
            "design_columns": ["treatment", "mediator",
                               "treatment_x_mediator"],
        },
        levels_observed=levels_observed,
        ci_level=ci_level,
        method=method,
        given_levels=tuple(mediator_values),
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
        draws=draws,
        form=resolved,
        form_provenance=form_provenance,
        shape_provenance=shapes_settled(assumptions, ORDERED_ENTRY_SHAPE),
    )


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
    """The controlled direct effect at ONE level, for a caller who has
    chosen it — :func:`estimate_cde_curve` at ``n = 1``.

    Two entry points and one plug-in. Which of them a caller wants is not
    a matter of convenience: a policy question names the level the
    mediator would be held at and wants the number there, while a reader
    asking what the direct effect IS has no such level and is owed the
    curve. Answering the first with a curve makes them find their level in
    it; answering the second with a point makes the estimator pick one.
    """
    curve = estimate_cde_curve(
        data, treatment=treatment, outcome=outcome, mediator=mediator,
        mediator_values=(mediator_value,), adjustment=adjustment,
        treatment_low=treatment_low, treatment_high=treatment_high,
        model=model, ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, cluster=cluster,
    )
    only = curve.levels[0]
    return CDEEstimate(
        point=only.point,
        ci_lower=only.ci_lower,
        ci_upper=only.ci_upper,
        ci_level=curve.ci_level,
        method=curve.method,
        mediator_value=mediator_value,
        treatment_low=curve.treatment_low,
        treatment_high=curve.treatment_high,
        sample_size=curve.sample_size,
        data_hash=curve.data_hash,
        data_columns=curve.data_columns,
        adjustment=curve.adjustment,
        mediator=curve.mediator,
        treatment=curve.treatment,
        outcome=curve.outcome,
        assumptions=curve.assumptions,
        cluster=curve.cluster,
        draws=curve.draws,
        form=curve.form,
        form_provenance=curve.form_provenance,
        shape_provenance=curve.shape_provenance,
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
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
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
            Refusal.INPUTS_DISAGREE,
            one="mediators=", one_is=list(mediators),
            other="mediator_values=", other_is=list(mediator_values),
        )
    if len(mediators) == 0:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="mediators=", needed=1, given=len(mediators),
            remedies=[(Remedy.USE_METHOD, "estimate_backdoor_ate")],
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
    # whatever they are, and one construction builds the fitted design and
    # both counterfactual ones so no product can be left stale.
    def _design(
        x: np.ndarray, ms: list[np.ndarray], block: np.ndarray,
    ) -> np.ndarray:
        """X, each M_j, each X·M_j, then the covariates.

        One exposure-mediator product per mediator, for the reason the
        single-mediator estimator carries one: the chain CDE is read AT the
        levels ``mediator_values`` names, and a model with no such term
        answers the same number wherever they are set. Mediator-mediator
        products are NOT here — the joint natural-effect estimator declares
        their absence as ``no_mediator_mediator_interaction_in_outcome_model``
        and this route declares the same restriction below.
        """
        return np.column_stack([x, *ms, *[x * m for m in ms], block])

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        block = design_block(sample, adjustment)
        x_obs = sample[treatment].to_numpy(dtype=float)
        m_obs = [sample[m].to_numpy(dtype=float) for m in mediators]
        X_full = _design(x_obs, m_obs, block)
        y = sample[outcome].to_numpy()
        ones = np.ones(len(sample))
        held = [ones * float(mv) for mv in mediator_values]
        X_high = _design(ones * float(treatment_high), held, block)
        X_low = _design(ones * float(treatment_low), held, block)
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

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
                value = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws.unusable()
                continue
            if not np.isfinite(value):
                draws.unusable()
                continue
            values.append(value)
            draws.usable()
        if draws.enough:
            alpha = (1 - ci_level) / 2
            arr = np.asarray(values, dtype=float)
            ci_lower = float(np.quantile(arr, alpha))
            ci_upper = float(np.quantile(arr, 1 - alpha))

    method = f"cde_chain_{resolved}"
    assumptions: tuple[str, ...] = (
        "no_unmeasured_confounder_x_y_given_chain_and_adjustment",
        "no_unmeasured_confounder_between_successive_mediators",
        "consistency_of_potential_outcomes",
        "outcome_model_correctly_specified_at_chain_fixed_values",
        # The design carries X·M_j for every j and no M_j·M_k. That is the
        # same restriction the joint natural-effect estimator declares, and
        # a reader deciding whether the chain's number can be read at these
        # levels needs the two halves of the design's shape, not one.
        "no_mediator_mediator_interaction_in_outcome_model",
    )
    assumptions = assumptions + (
        ("linear_outcome_regression",) if resolved == "linear"
        else ("logit_outcome_regression",)
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_chain_backdoors",
        ) + ordered_entry(df, adjustment)
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
        draws=draws,
        form=resolved,
        form_provenance=form_provenance,
        # Declared beside the rest of what the chain decomposition is derived
        # under, whatever shape the outcome model ended up with.
        shape_provenance=shapes_settled(
            assumptions,
            ORDERED_ENTRY_SHAPE,
            ("outcome_model_correctly_specified_at_chain_fixed_values",
             Provenance.INHERENT),
            ("no_mediator_mediator_interaction_in_outcome_model",
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
