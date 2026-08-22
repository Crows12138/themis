"""Classical measurement error on a CONTINUOUS OUTCOME — what it costs.

The third role a mismeasured variable can play, and the only one that costs no
bias. Where the exposure channel loses the effect to regression dilution and a
mismeasured covariate leaves residual confounding, a classical additive error on
the outcome — Y = Y* + V with E[V | D, Y*] = 0 — leaves **every conditional
mean unchanged**. Every estimand this package reports on a continuous outcome is
built from conditional means (a back-door contrast, a Wald ratio, a front-door
sum, a natural-effect decomposition), so none of them moves. There is nothing to
de-attenuate.

What it does cost is precision, and that cost is knowable rather than merely
lamentable, because σ²_v is supplied. The residual variance of the observed
outcome around its model splits exactly:

    Var(Y | D) = Var(Y* | D) + σ²_v

so the standard error of every least-squares functional of that design is
inflated by the fixed factor

    se_inflation = sqrt( Var(Y | D) / (Var(Y | D) − σ²_v) )

— the interval the study actually reports, divided by the interval the same
design would have reported had the outcome been measured without error. That is
the actionable answer to "should I collect more subjects or measure better".

**One arithmetic, three designs.** That formula is not the back-door's, and
generalising it is not a matter of writing it out again per route. Exactly three
things differ between designs: WHICH residual absorbs σ²_v, WHICH conditioning
set the classical premise has to hold on, and whether the reported factor is the
answer or a ceiling on it. Everything else — the split, the share, the square
root — is the same arithmetic on different moments.

- BACK_DOOR. The residual around the OLS projection on (exposure, *adjustment).
  Premise E[V | X, Z] = 0. The factor is EXACT for a homoskedastic
  linear-projection coefficient.

- INSTRUMENTAL_VARIABLE. The 2SLS sandwich has Ω = E[Z Z' e²] (Hansen,
  *Econometrics*, 2022, Theorem 12.2). With Y = Y* + V and E[ZV] = 0 that Ω
  becomes Ω* + σ²_v Q_ZZ and the sandwich COLLAPSES to an additive penalty
  V_β = V_β* + σ²_v (Q_XZ Q_ZZ⁻¹ Q_ZX)⁻¹; under homoskedastic e* that is the
  same scalar factor, and still exact. What differs is the residual — the
  STRUCTURAL one, Var(Y − βX − γ'W) taken around the IV coefficient rather than
  around an OLS projection — and the premise, which is different in KIND rather
  than merely wider. Hansen's Assumption 12.1.7 is E[Ze] = 0, so what must be
  mean-independent of the error is the INSTRUMENT; E[V | X, W] = 0 is neither
  necessary nor sufficient here. (Hausman, 2001, *JEP* 15(4) 57-67 is the
  canonical citation for the left-hand-side result itself but does not cover
  2SLS; Pierce & VanderWeele, 2012, *IJE* 41(5) 1383-1393 is the Mendelian-
  randomization corroboration — non-differential outcome error does not bias the
  estimate, and is the single largest source of power loss.)

- FRONT_DOOR. The efficient influence function has the outcome entering ONLY as
  w·{Y − μ(M, A, X)}, with w = f_M(M | a₀, X) / f_M(M | A, X) (Guo, Benkeser &
  Nabi, arXiv:2312.10234, Eq. 4). So the conditioning set carries the MEDIATOR
  and this design is a SUPERSET of the back-door one, and the asymptotic variance
  gains σ²_v·E[w²]. Two things follow that are reported rather than smoothed
  over. The scalar factor OVERSTATES the loss here, because that influence
  function has a second term carrying no outcome residual at all — so on this
  design the number is an UPPER BOUND, which is what
  ``OutcomeErrorDesign.exact`` says and why no field beside the factor repeats
  it. And the front-door graph posits an unmeasured X-Y confounder U: if V
  depends on U then E[V | A, M, X] ≠ 0 and THE POINT MOVES. The IV design has no
  such exposure — only E[ZV] = 0 is needed, and Z is independent of U by
  assumption — so the front-door premise is a claim about an UNOBSERVED
  variable, unfalsifiable from data, and it is disclosed on its own rather than
  folded into the classical one.

The split is also refutable, which is the point of computing it. σ²_v ≥
Var(Y | D) says the declared measurement noise does not fit underneath the
unexplained variation the data actually show. One of three things is then false
— the declared variance, the linearity of the outcome model, or the
independence of the error from the design — and the last of those is precisely
the premise under which the point estimate was safe. So the assessment refuses
rather than reporting a negative signal variance.

Deliberately out of scope, each refused by name rather than absorbed: a
DISCRETE outcome (that is misclassification, a different object with a different
correction — ``misclassification=``), and differential / Berkson error (the
spec has no way to declare either, so accepting one silently would be inventing
a premise the caller never made).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import unique

import numpy as np
import pandas as pd

from .contract import validate_data
from .declared import design_terms
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from ..types import EnvelopeName
# Shared with the front-door estimator on purpose: the level set a mediator is
# encoded over is ONE decision. The front-door outcome model is fitted on the
# span those indicators generate, so a residual taken around any other span is
# a residual around a model nobody fitted — and around a COARSER one it is
# larger, which understates the cost in the direction that matters.
from .frontdoor import _discrete_levels
# Shared with regression calibration on purpose: "how many distinct values before
# a column stops being a misclassification object" is one decision, and the two
# channels must route the same variable the same way.
from .regression_calibration import _MIN_CONTINUOUS_DISTINCT

# Signal variance at or below this share of the residual ⇒ the declared error
# swallows the model's unexplained variation ⇒ refuse rather than report a
# meaningless inflation factor.
_SIGNAL_FLOOR = 1e-9


@unique
class OutcomeErrorDesign(EnvelopeName):
    """Which design's residual a declared σ²_v is being priced against.

    A closed vocabulary rather than a free string, because every difference
    between the routes is a fact ABOUT the design and belongs beside its
    name: which extra arguments the design is even able to use, and whether
    the factor it reports is exact. Recorded here once, they cannot become a
    second record of themselves on the envelope — a field saying "this one
    is exact" would be free to disagree with the field saying which design
    it was.
    """

    exact: bool
    """Whether ``se_inflation`` is the factor, or a ceiling on it. A design
    whose influence function puts the whole outcome residual in one term
    gets the factor; one that splits it across terms gets an upper bound,
    because the split's other terms carry no σ²_v to inflate."""

    requires: frozenset[str]
    """The optional arguments this design cannot proceed without. Every
    argument NOT named here is refused for this design rather than ignored:
    an argument a design has no place for is a premise the caller believes
    they declared, and silently dropping it leaves them believing it."""

    says: str
    """What the design is, for whoever adds the next one beside it."""

    def __new__(
        cls, value: str, exact: bool, requires: tuple[str, ...], says: str,
    ) -> "OutcomeErrorDesign":
        design = str.__new__(cls, value)
        design._value_ = value
        design.exact = exact
        design.requires = frozenset(requires)
        design.says = says
        return design

    BACK_DOOR = (
        "back_door",
        True,
        (),
        "the residual around the OLS projection on (exposure, *adjustment); "
        "the premise is mean-independence of the error given that design",
    )
    INSTRUMENTAL_VARIABLE = (
        "instrumental_variable",
        True,
        ("instruments", "treatment_coefficient"),
        "the STRUCTURAL residual around a supplied IV coefficient; the 2SLS "
        "sandwich collapses to an additive σ²_v penalty, so the factor is the "
        "same one — but the premise is about the INSTRUMENT, not the design",
    )
    FRONT_DOOR = (
        "front_door",
        False,
        ("mediators",),
        "the residual around the outcome model on (exposure, *mediator "
        "indicators, *adjustment); the influence function splits the "
        "variance, so the factor is a ceiling and the latent confounder the "
        "graph posits can carry the error into the point",
    )


_BY_NAME = {str(design): design for design in OutcomeErrorDesign}


# Why each optional argument exists, in the words of the design that needs it.
# Keyed by the argument rather than by the design/argument pair: what the
# argument IS does not change with who asked for it, and the refusal a caller
# reads has to name the thing they left out, not the route they chose.
_WHAT_IT_IS = {
    "instruments": (
        "the premise this design rests on is E[V | Z] = 0, a claim about the "
        "INSTRUMENTS rather than about the design; without named instruments "
        "there is no variable to make that claim about, and the assessment "
        "would disclose a premise with a hole in it. Plural because an "
        "over-identified system rests on one such claim PER instrument, each "
        "separately able to be false — naming only one of them would put a "
        "premise on the ledger that understates what is being assumed"
    ),
    "treatment_coefficient": (
        "the residual here is the structural Var(Y − βX − γ'W) taken around "
        "the IV coefficient, not around an OLS projection of Y on the design; "
        "without β̂ there is nothing to take it around, and the OLS residual "
        "is a different, smaller number about a different model"
    ),
    "mediators": (
        "the front-door outcome model conditions on the mediator, which is "
        "what makes this design a superset of the back-door one; without a "
        "mediator the design IS the back-door design, and that one already "
        "has a name"
    ),
}


@dataclass(frozen=True)
class OutcomeErrorAssessment:
    """What a known classical outcome-error variance implies for one query.

    ``design_kind`` says which residual the split was taken around, and is
    what every other field has to be read against: ``residual_variance`` is
    Var(Y | D) — the unexplained variance of the OBSERVED outcome around the
    design D that ``design_vars`` names — ``signal_variance`` is what remains
    of it once the declared measurement noise is removed, ``noise_share`` the
    fraction of the unexplained variation that is pure measurement, and
    ``se_inflation`` the factor by which that noise widens every
    least-squares interval on this design (a ceiling on it where
    ``design_kind.exact`` is false). ``sufficient_statistics`` carries Σ_D,
    Cov(D, Y), Var(Y), the design coefficients, σ²_v and n — everything the
    verifier re-derives the split from without the data.
    """
    outcome: str
    treatment: str
    design_kind: OutcomeErrorDesign
    design_vars: tuple[str, ...]
    error_variance: float
    residual_variance: float
    signal_variance: float
    noise_share: float
    se_inflation: float
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    sufficient_statistics: dict = field(default_factory=dict)


def assess_outcome_error(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    design_kind: OutcomeErrorDesign | str = OutcomeErrorDesign.BACK_DOOR,
    adjustment: Sequence[str] = (),
    mediators: Sequence[str] = (),
    instruments: Sequence[str] = (),
    # ``object``, not ``float``, for the same reason as ``error_variance``
    # below: whether what arrived is a usable coefficient is this entry
    # point's judgement, and the annotation must not claim it was settled
    # before the call.
    treatment_coefficient: object = None,
    error_variance: object,
) -> OutcomeErrorAssessment:
    """Split the observed outcome's residual variance into signal and declared
    measurement noise, and report what the noise costs in precision.

    Parameters
    ----------
    data: the sample carrying the observed (error-prone) outcome.
    treatment / outcome: this query's exposure and continuous outcome columns.
    design_kind: which design the split is taken around — see
        :class:`OutcomeErrorDesign`. It decides which of the arguments below
        are required and which are refused.
    adjustment: covariates the outcome model conditions on, on every design.
    mediators: FRONT_DOOR only — expanded into drop-first indicators over each
        mediator's sorted level set, which is the span the front-door outcome
        model is actually fitted on.
    instruments: INSTRUMENTAL_VARIABLE only. They are NOT part of the design;
        they name the variables the premise E[V | Z] = 0 is about — one such
        premise each, because an over-identified system rests on all of them
        and each can fail on its own.
    treatment_coefficient: INSTRUMENTAL_VARIABLE only — the IV coefficient β̂
        the structural residual is taken around.
    error_variance: the KNOWN classical additive error variance σ²_v of the
        outcome (validation study / repeat measurement).

    Raises
    ------
    EstimatorFailure: an unknown design; an argument the chosen design
        requires and did not get, or has no place for and did; a non-positive
        or non-finite σ²_v; a near-discrete outcome (a misclassification
        object, not a continuously-mismeasured one); a mediator the front-door
        outcome model could not encode; a singular design; or a σ²_v that
        meets or exceeds the observed residual variance.
    """
    design = _resolve_design(design_kind)
    mediators = tuple(mediators)
    adjustment = tuple(adjustment)
    instruments = tuple(instruments)
    _check_arguments(
        design,
        mediators=mediators or None,
        instruments=instruments or None,
        treatment_coefficient=treatment_coefficient,
    )

    sigma_v = _refuse_unusable_variance(error_variance, outcome)

    # The instrument is not in the design, but the premise named after it is a
    # claim about a column of THIS sample; requiring it here is what keeps a
    # mistyped instrument from reaching the ledger as a premise about a
    # variable nobody measured.
    contract = validate_data(
        data,
        required_columns={
            treatment, outcome, *adjustment, *mediators, *instruments,
        },
        quantity_columns=(treatment, outcome, *instruments),
    )
    df = contract.data

    _refuse_discrete_outcome(df, outcome)

    design_vars, D = _build_design(df, treatment, mediators, adjustment)
    Sigma, cov_Dy, var_y, n = _moments(D, df[outcome].to_numpy(dtype=float))

    b = _design_coefficients(Sigma, cov_Dy, treatment_coefficient)
    # Var(Y − b'D), the one form that covers every route. Where b is the OLS
    # solution the cross term absorbs the quadratic one and it reduces to
    # Var(Y) − Cov(D,Y)'Σ_D⁻¹Cov(D,Y); where b came from outside it does not,
    # and writing the reduced form there would silently price a model that was
    # never fitted.
    residual_variance = float(var_y - 2.0 * (b @ cov_Dy) + b @ Sigma @ b)

    signal_variance = _refuse_variance_that_does_not_fit(
        outcome, sigma_v, residual_variance,
    )

    noise_share = sigma_v / residual_variance
    se_inflation = float(np.sqrt(residual_variance / signal_variance))

    return OutcomeErrorAssessment(
        outcome=outcome,
        treatment=treatment,
        design_kind=design,
        design_vars=design_vars,
        error_variance=sigma_v,
        residual_variance=residual_variance,
        signal_variance=signal_variance,
        noise_share=noise_share,
        se_inflation=se_inflation,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        assumptions=_assumptions(outcome, design, instruments),
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "design_coefficients": [float(v) for v in b],
            "var_y": var_y,
            "error_variance": sigma_v,
            "n": int(n),
        },
    )


def check_outcome_error_declaration(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: Sequence[str] = (),
    mediators: Sequence[str] = (),
    error_variance: object,
) -> None:
    """Whether what the caller declared about their outcome can be true of this
    sample at all — the half of the assessment that has to be settled BEFORE
    an estimator runs.

    Two questions were fused here, and they sit on opposite sides of the
    answer. "Can this declaration be true?" has to be settled first, because
    its answer can stop the query: a discrete outcome is misclassification,
    which DOES attenuate, and a σ²_v that will not fit under the unexplained
    variation puts in doubt the independence premise that made the point safe.
    "What does the noise cost this estimator?" cannot be settled until there
    IS an estimator — on the instrumental-variable design the split is taken
    around β̂, which is the answer itself. Fused, the pair could only sit on
    one side, and it sat on the early one, so the design whose cost needs the
    answer could never be priced.

    The residual here is the ORDINARY least-squares one on every design, and
    that is not an approximation standing in for the structural residual the
    IV route prices against. Var(Y | D) = Var(Y* | D) + σ²_v is a statement
    about the conditional variance, which under linearity IS the least-squares
    residual, and least squares minimises it — so σ²_v ≤ Var(Y | D) is a
    NECESSARY condition whatever design goes on to answer, and taking it
    around any other coefficient would only make the check looser than the
    data warrant. Measured: on a just-identified IV setup the structural
    residual runs 4.99 against the least-squares 2.52, so pricing the refusal
    around β̂ would admit declarations the sample rules out.

    Raises the same refusals :func:`assess_outcome_error` raises, from the
    same three judgements — this is the earlier half of one assessment, not a
    second opinion about it.
    """
    sigma_v = _refuse_unusable_variance(error_variance, outcome)
    mediators, adjustment = tuple(mediators), tuple(adjustment)
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment, *mediators},
        quantity_columns=(treatment, outcome),
    )
    df = contract.data
    _refuse_discrete_outcome(df, outcome)
    _, D = _build_design(df, treatment, mediators, adjustment)
    Sigma, cov_Dy, var_y, _ = _moments(D, df[outcome].to_numpy(dtype=float))
    b = _design_coefficients(Sigma, cov_Dy, None)
    _refuse_variance_that_does_not_fit(
        outcome, sigma_v, float(var_y - 2.0 * (b @ cov_Dy) + b @ Sigma @ b),
    )


# --- the judgements, shared by both halves -------------------------------------


def _refuse_unusable_variance(error_variance: object, outcome: str) -> float:
    """σ²_v as a number, or the refusal that says it is not one.

    Returns what it judged rather than merely approving it: an entry point
    takes ``object`` because deciding this IS its job, and a caller that had
    to convert the value again afterwards would be the second half of one
    judgement, written somewhere the first half cannot see.
    """
    if (
        not isinstance(error_variance, (int, float))
        or isinstance(error_variance, bool)
        or not np.isfinite(error_variance)
        or error_variance <= 0
    ):
        raise EstimatorFailure(
            Refusal.NON_POSITIVE_ERROR_VARIANCE,
            f"the classical measurement-error variance σ²_v for the outcome "
            f"{outcome!r} must be a positive finite number; got "
            f"{refusals.describe(error_variance)}.",
        )
    return float(error_variance)


def _refuse_discrete_outcome(df: pd.DataFrame, outcome: str) -> None:
    n_distinct = int(df[outcome].dropna().nunique())
    if n_distinct < _MIN_CONTINUOUS_DISTINCT:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_CONTINUOUS,
            outcome=outcome, distinct=n_distinct,
        )


def _refuse_variance_that_does_not_fit(
    outcome: str, sigma_v: float, residual_variance: float,
) -> float:
    """The signal that remains, or the refusal that says none does."""
    signal_variance = residual_variance - sigma_v
    if signal_variance <= _SIGNAL_FLOOR * max(residual_variance, 1.0):
        raise EstimatorFailure(
            Refusal.OUTCOME_ERROR_EXCEEDS_RESIDUAL_VARIANCE,
            declared=sigma_v, outcome=outcome, residual=residual_variance,
        )
    return signal_variance


def _moments(
    D: np.ndarray, y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    """Σ_D, Cov(D, Y), Var(Y), n — centred, and the only place they are formed.

    Both halves take their residual from these, so forming them twice would be
    two records of one sample rather than one read of it.
    """
    n = len(y)
    Dc, yc = D - D.mean(axis=0), y - y.mean()
    return (
        (Dc.T @ Dc) / (n - 1),
        (Dc.T @ yc) / (n - 1),
        float(yc @ yc / (n - 1)),
        n,
    )


# --- the call ------------------------------------------------------------------


def _resolve_design(design_kind) -> OutcomeErrorDesign:
    """The named design, or a refusal that lists the ones that exist.

    By name rather than through the enum's own call, so that a member and the
    plain string it becomes on the envelope are one input here — the round
    trip out and back is the normal case, not the exceptional one.
    """
    design = _BY_NAME.get(str(design_kind))
    if design is None:
        known = ", ".join(_BY_NAME)
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"design_kind={refusals.describe(design_kind)} is not a design "
            f"this assessment knows how to take a residual around; the "
            f"vocabulary is closed and holds {known}.",
        )
    return design


def _check_arguments(design: OutcomeErrorDesign, **supplied) -> None:
    """Each design gets the arguments it names and no others.

    Absence is ``None`` throughout, so "not passed" and "passed empty" are one
    state — a caller who passes ``mediators=()`` to the front-door design has
    supplied no mediator, and telling them their argument arrived would be
    true and useless.
    """
    for name, value in supplied.items():
        needed = name in design.requires
        if needed and value is None:
            raise EstimatorFailure(
                Refusal.INVALID_INPUT,
                f"design_kind={design!s} requires {name}=: "
                f"{_WHAT_IT_IS[name]}.",
            )
        if not needed and value is not None:
            owners = ", ".join(
                str(d) for d in OutcomeErrorDesign if name in d.requires
            ) or "no design here"
            raise EstimatorFailure(
                Refusal.INVALID_INPUT,
                f"design_kind={design!s} has no place for {name}= — that "
                f"argument belongs to {owners}. Ignoring it would leave the "
                f"caller holding a premise they think they declared: "
                f"{_WHAT_IT_IS[name]}.",
            )
    beta = supplied.get("treatment_coefficient")
    if beta is not None and (
        not isinstance(beta, (int, float))
        or isinstance(beta, bool)
        or not np.isfinite(beta)
    ):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"treatment_coefficient must be a finite number — the structural "
            f"residual is taken around it; got {refusals.describe(beta)}.",
        )


# --- the design ----------------------------------------------------------------


def _build_design(
    df: pd.DataFrame,
    treatment: str,
    mediators: tuple[str, ...],
    adjustment: tuple[str, ...],
) -> tuple[tuple[str, ...], np.ndarray]:
    """(exposure, *mediator indicators, *adjustment), as columns and as names.

    Built here rather than accepted from the caller, because the residual has
    to be taken around the span the outcome model was fitted on and only this
    module knows what that span is. A mediator arrives as one column and
    enters as drop-first indicators over its levels; a binary one yields
    exactly its own column, which is why the difference is invisible on the
    common case and material on every other.
    """
    columns: list[tuple[str, np.ndarray]] = [
        (treatment, df[treatment].to_numpy(dtype=float)),
    ]
    for m in mediators:
        columns.extend(_mediator_indicators(df[m], m))
    # An adjustment column is whatever the program declared it to be, and one
    # declared to have no order expands here for the same reason a mediator
    # does: the span the residual is taken around has to be the span the
    # outcome model was fitted on, and that model does not read a channel as
    # a number either.
    columns.extend(design_terms(df, adjustment))
    return (
        tuple(name for name, _ in columns),
        np.column_stack([column for _, column in columns]),
    )


def _mediator_indicators(
    series: pd.Series, name: str,
) -> list[tuple[str, np.ndarray]]:
    """Drop-first indicators over the mediator's sorted level set.

    The first level is the reference the intercept already carries; the rest
    span the same space the front-door outcome model's encoding does, which is
    the whole reason to expand at all.
    """
    levels = _discrete_levels(series, name)
    values = series.to_numpy()
    return [
        (f"{name}={level}", (values == level).astype(float))
        for level in levels[1:]
    ]


def _design_coefficients(
    Sigma: np.ndarray, cov_Dy: np.ndarray, treatment_coefficient,
) -> np.ndarray:
    """The vector the residual is taken around.

    With no coefficient supplied that is the OLS projection of Y on the whole
    design. With one supplied it is that coefficient on the exposure — which
    heads the design — and the OLS projection of the remainder Y − βX on
    everything else: the same nuisance-minimising fit the structural residual
    is defined by, with the one coefficient that did not come from OLS held
    where the caller put it.
    """
    if treatment_coefficient is None:
        return _solve(Sigma, cov_Dy, "the design covariance Σ_D")
    beta = float(treatment_coefficient)
    if Sigma.shape[0] == 1:
        return np.array([beta])
    rest = _solve(
        Sigma[1:, 1:],
        cov_Dy[1:] - beta * Sigma[1:, 0],
        "the covariance of the design's non-exposure columns",
    )
    return np.concatenate([[beta], rest])


def _solve(a: np.ndarray, b: np.ndarray, what: str) -> np.ndarray:
    try:
        return np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            f"{what} is singular (collinear covariates); the outcome's "
            f"residual variance is undefined.",
        ) from None


# --- disclosure ----------------------------------------------------------------


def _assumptions(
    outcome: str, design: OutcomeErrorDesign, instruments: tuple[str, ...],
) -> tuple[str, ...]:
    """The premises, and only the premises.

    What the split *implies* — that the point needs no correction, that the
    interval carries a fixed amount of measurement — is a consequence, and
    consequences belong in the block's numbers and in what the renderer says
    about them, not in a list of things that could be false. Mixing the two
    would put a derived quantity on the disclosure surface at the severity
    reserved for a premise whose failure kills the answer.

    Which premises they are is a fact about the design, not a wider or
    narrower version of one premise. The instrumental-variable route needs
    mean-independence of the INSTRUMENT and nothing about the design; the
    front-door route needs the classical premise AND one more that no data
    can refute, because the confounder it is about is the unmeasured one the
    graph posits.

    One entry per instrument, because an over-identified system assumes each
    of them separately and each can separately be false. A ledger that named
    one of several would report less than is being assumed, and a ledger that
    joined them into one name would offer the reader a premise they cannot
    refute one piece at a time — which is the only way this one ever fails.
    """
    known = f"outcome_error_variance_known_and_fixed_on_{outcome}"
    if design == OutcomeErrorDesign.INSTRUMENTAL_VARIABLE:
        return (
            *(
                f"outcome_error_mean_independent_of_instrument_{z}_on_{outcome}"
                for z in instruments
            ),
            known,
        )
    classical = f"outcome_error_classical_non_differential_on_{outcome}"
    if design == OutcomeErrorDesign.FRONT_DOOR:
        return (
            classical,
            known,
            f"outcome_error_independent_of_the_front_door_latent_confounder_"
            f"on_{outcome}",
        )
    return (classical, known)
