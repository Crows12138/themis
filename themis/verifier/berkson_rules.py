"""Independent audit of the Berkson-error assessment.

Like the outcome-error assessment it audits a block that changes no
number, and its whole content is a claim about what a declared variance
does and does not cost. Here the two halves are further apart than
anywhere else in the package, which is what makes the audit worth having:

**The point is claimed to need no correction at all.** That is the strong
half. Under Berkson error the truth scatters around the recorded nominal
value, ``E[X*|W,Z] = W``, and the ordinary back-door slope IS the causal
slope — so an answer that arrives beside this block has deliberately NOT
been de-attenuated. If the structure were classical instead, the same
number would be attenuated and the same block would be telling a reader
it is fine. No arithmetic can tell those apart: which structure holds is
a fact about how the measurement was made, and it reaches here as a
declaration. What this audit can do — and does — is refuse to let the
declaration go unstated: the premise has to be on the assumption ledger,
where a reader can disagree with it.

**The price is fully re-derivable**, and is checked as arithmetic:

    Var(Y|W,Z) = Var(Y) − 2 b'Cov(D,Y) + b'Σ_D b
    scattered  = β̂²·σ²_u
    signal     = residual − scattered
    inflation  = sqrt(residual / signal)

every term from the recorded moments alone. The one thing that makes this
different from the outcome-channel audit is that ``scattered`` is scaled
by the ANSWER, so a block whose β̂ does not match the estimate it rides
beside is priced against a number the reader was never given — and that
is checked too.

**Independence pin:** this module MUST NOT import from
``themis.estimation``. Everything it needs is on the envelope.
"""
from __future__ import annotations

import math
from typing import NoReturn

from .errors import VerificationError

_RULE = "berkson_error_check"
_TOL = 1e-6

#: The premises a Berkson block owes the reader, by the id each carries on
#: the assumption ledger. Restated rather than imported, for the reason in
#: the header: a ledger re-derived from the vocabulary its producer chose
#: is not an independent audit.
#:
#: Three rather than one, and the split is load-bearing. The STRUCTURE is
#: why no correction was applied; the LINEARITY is what carries E[X*|W,Z]=W
#: through to the coefficients, without which the structure alone does not
#: leave the point unbiased; the VARIANCE is why the price has the size it
#: has. A reader who doubts either of the first two should distrust the
#: point; a reader who doubts the third should distrust only the width.
_STRUCTURE = "berkson_error_on_"
_LINEARITY = "berkson_identity_rests_on_a_linear_outcome_in_the_true_values"
_VARIANCE = "berkson_scatter_variance_known_and_fixed_on_"


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(f"{what} must be a number; got {value!r}")
    return float(value)


def _agree(recomputed: float, recorded: float, what: str) -> None:
    if not math.isclose(recomputed, recorded, rel_tol=_TOL,
                        abs_tol=_TOL * max(abs(recomputed), 1.0)):
        _reject(f"{what}: recorded {recorded!r}, recomputed {recomputed!r}")


def _matrix(rows: object, n: int, what: str) -> list[list[float]]:
    if not isinstance(rows, list) or len(rows) != n:
        _reject(f"{what} must be a {n}x{n} matrix")
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) != n:
            _reject(f"{what} must be a {n}x{n} matrix")
        out.append([_number(v, f"{what} entry") for v in row])
    return out


def _vector(values: object, n: int, what: str) -> list[float]:
    if not isinstance(values, list) or len(values) != n:
        _reject(f"{what} must have {n} entries")
    return [_number(v, f"{what} entry") for v in values]


def verify_berkson_error(result: dict) -> None:
    """Re-derive a ``berkson_error`` block's price from its own moments.

    Takes the ``query_result`` envelope, because the two things this audit
    holds together live on opposite sides of it: the block's arithmetic,
    and the premises the assumption ledger owes the reader. Returns
    ``None`` when the result carries no such block. Raises
    ``VerificationError`` on a price that does not recompute, a price
    scaled by a coefficient the answer does not report, or a declaration
    that never reached the reader.
    """
    if not isinstance(result, dict):
        _reject("result must be a dict")
    block = result.get("berkson_error")
    if block is None:
        return
    if not isinstance(block, dict):
        _reject("berkson_error must be an object")

    stats = block.get("sufficient_statistics")
    if not isinstance(stats, dict):
        _reject("berkson_error.sufficient_statistics is missing")

    names = stats.get("design_vars")
    if not isinstance(names, list) or not names:
        _reject("berkson_error.sufficient_statistics.design_vars is missing")
    p = len(names)
    if list(block.get("design_vars") or ()) != list(names):
        _reject(
            "berkson_error.design_vars and its sufficient_statistics name "
            "different designs; the price would then be arithmetic about one "
            "model reported beside another"
        )

    sigma = _matrix(stats.get("cov_matrix"), p, "cov_matrix")
    cov_dy = _vector(stats.get("cov_design_y"), p, "cov_design_y")
    b = _vector(stats.get("design_coefficients"), p, "design_coefficients")
    var_y = _number(stats.get("var_y"), "var_y")
    sigma_u = _number(stats.get("error_variance"), "error_variance")
    if sigma_u <= 0:
        _reject(f"a Berkson variance of {sigma_u!r} is not one")

    # The coefficient the price is scaled by has to be the coefficient the
    # answer reports. Otherwise the block prices an effect the reader was
    # never given — which is the one forgery that leaves every scalar here
    # internally consistent.
    beta = _number(stats.get("treatment_coefficient"),
                   "treatment_coefficient")
    _agree(beta, _number(block.get("treatment_coefficient"),
                         "berkson_error.treatment_coefficient"),
           "the coefficient the price is scaled by")
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, dict) and estimate.get("point") is not None:
        _agree(beta, _number(estimate["point"], "numeric_estimate.point"),
               "the price's coefficient against the answer it rides beside")

    # The design's own coefficients must solve the normal equations. Under
    # Berkson error nothing is sourced from outside them — the whole claim
    # is that the ORDINARY back-door slope is already the causal one — so
    # every row is checked, the exposure's included.
    for i in range(p):
        lhs = sum(sigma[i][j] * b[j] for j in range(p))
        _agree(lhs, cov_dy[i],
               f"the normal equation for {names[i]!r}")

    # And the coefficient the block is ABOUT must be that same slope. The
    # two checks above pin it to the answer and pin the design to the data;
    # without this one a block could sit beside an answer that is not the
    # ordinary slope, and tell its reader the identity had left that number
    # alone. The exposure leads the design by construction, so its row is
    # the first — which the name check below states rather than assumes.
    if not names or str(names[0]) != str(block.get("exposure")):
        _reject(
            f"the design's first column is {names[0]!r} and the block is "
            f"about {block.get('exposure')!r}; the identity is about the "
            f"exposure's own slope, so a design that does not lead with it "
            f"prices a coefficient on some other column"
        )
    _agree(beta, b[0],
           "the priced coefficient against the design's own exposure slope")

    residual = var_y - 2.0 * sum(b[i] * cov_dy[i] for i in range(p)) + sum(
        b[i] * sigma[i][j] * b[j] for i in range(p) for j in range(p))
    _agree(residual, _number(block.get("residual_variance"),
                             "residual_variance"),
           "the residual variance around the observed design")

    scattered = beta * beta * sigma_u
    _agree(scattered, _number(block.get("scattered_variance"),
                              "scattered_variance"),
           "what the declared scatter contributes to the residual")

    signal = residual - scattered
    if signal <= 0:
        _reject(
            f"the declared scatter contributes {scattered!r} to a residual "
            f"of {residual!r}, so no signal is left under it — a block that "
            f"shipped a price here priced a split that does not exist"
        )
    _agree(signal, _number(block.get("signal_variance"), "signal_variance"),
           "the signal remaining under the scatter")
    _agree(scattered / residual,
           _number(block.get("noise_share"), "noise_share"),
           "the share of the unexplained variation that is scattered truth")
    _agree(math.sqrt(residual / signal),
           _number(block.get("se_inflation"), "se_inflation"),
           "the factor the scatter widens every interval by")

    _check_the_declaration_reached_the_reader(result, block)


def _check_the_declaration_reached_the_reader(result: dict,
                                              block: dict) -> None:
    """The structure is why no correction was applied, so it is owed.

    An assessment whose premises stop at its own block is
    indistinguishable, downstream, from an answer that assumed nothing —
    and here what would go unsaid is the reason a number nobody
    de-attenuated is nevertheless the right one. Silence is the defect.
    """
    exposure = block.get("exposure")
    if not isinstance(exposure, str) or not exposure:
        _reject("berkson_error.exposure must name the nominal column")
    ledger = (result.get("extensions") or {}).get("assumption_ledger") or {}
    declared = {
        str(e.get("id")) for e in (ledger.get("assumptions") or ())
        if isinstance(e, dict)
    }
    for owed, why in (
        (f"{_STRUCTURE}{exposure}",
         "why no correction was applied to the point at all"),
        (_LINEARITY,
         "what carries E[X*|W,Z]=W through to the coefficients, and so the "
         "other half of why the uncorrected point is the right one"),
        (f"{_VARIANCE}{exposure}",
         "why the price has the size it has"),
    ):
        if owed not in declared:
            _reject(
                f"the assumption ledger does not carry {owed!r}, which is "
                f"{why}; a premise that stops at this block reaches no "
                f"reader, and this one is not one they can infer from the "
                f"number"
            )
