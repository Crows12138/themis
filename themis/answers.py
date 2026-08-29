"""What shape of answer an estimate carries — declared once, bound per surface.

An estimate answers in whatever shape its estimand has: a point, a curve over
doses, a decomposition into direct and indirect parts, a contrast with the
interaction that rides on it, an interval where monotonicity was not available
to sharpen it into a point. Which shape a given estimate carries is a fact its
estimator knows. Until this module existed no estimate said so, and every
surface that renders an answer recovered it by probing field names in an
ordered chain.

A probe that finds nothing does not fail. It falls to the next branch, and the
last branch in that chain is the structural verdict — which always has a value.
So across one full suite run, 84 estimates reached the reader as ``结论：是``, a
claim about the graph standing in for the number that was asked for, while the
numbers sat in the same block under ``dose_response_curve`` (29),
``decomposition`` (29), ``joint_effect`` (17) and ``counterfactual_cell`` (11).
The one shape that did render was the one somebody had already been bitten by
and patched a branch for.

Shapes are declared here; each method declares which of them it can produce;
each surface binds its own renderer to the same vocabulary — the arrangement
:mod:`themis.routing` uses for strategies. :func:`bind` refuses a renderer set
that does not cover the vocabulary exactly, so a shape added here without a way
to say it fails at import rather than by rendering some other shape's answer.

**A method declares every shape it can produce, not the one it usually does.**
Two are genuinely bimodal: probabilities of causation and a counterfactual cell
are point-identified under monotonicity and bounded without it, and which came
out is a property of the run. Their entries name both, in the order tried, so
the sharper answer wins when it is available.

Declaring a shape is not the same as declaring the right one, and the check
this module performs cannot tell them apart: it asks whether every method has
a shape and every shape has a renderer, which a wrong shape satisfies. The
causation pair named ``point`` for its sharper half, and ``point`` carries a
single number for THE estimand while a causation query asks for three — so the
answer monotonicity buys arrived as a bare headline, less named than the
bounds it was meant to sharpen. The probe for that is not coverage but
arithmetic: how many quantities did the reader ask about, and how many does
this shape carry.

The keys of :data:`SHAPES_OF` are the closed ``numeric_estimate.method``
vocabulary of ``query_result.schema.json``; a test pins the two together in
both directions, the arrangement ``GapKind`` already uses. Two entries are
declared from their sibling's measured behaviour rather than from an observed
run — ``ipw_ht`` and ``joint_backdoor_logistic`` are reachable but the suite
never triggers them — and are marked below rather than folded in silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, TypeVar

R = TypeVar("R")

Estimate = Mapping[str, Any]


@dataclass(frozen=True)
class Shape:
    """One way an answer can be shaped, and where that answer lives.

    ``lives_in`` names the key on the estimate block carrying this shape's
    answer. It is a field rather than a closure detail because it is what a
    surface must read to render the shape, and therefore what a test can
    check a surface against — the web renders from TypeScript and cannot
    import this table, so the vocabulary has to be inspectable, not merely
    callable.

    ``detect`` says whether THIS estimate came out in this shape, which is
    not the same question as whether its method can produce it — that one
    :data:`SHAPES_OF` answers. Keeping them apart is what lets a bimodal
    method declare both of its shapes honestly instead of each surface
    guessing from whichever field it happened to probe first.
    """

    name: str
    carries: str
    lives_in: str
    # Defaults to "the key is there and non-empty", which is right for every
    # shape whose answer is a sub-object; only ``point`` needs its own, and
    # says why where it is declared.
    detect: Callable[[Estimate], bool] | None = field(compare=False,
                                                      default=None)

    def __post_init__(self) -> None:
        if self.detect is None:
            key = self.lives_in
            object.__setattr__(
                self, "detect", lambda estimate: bool(estimate.get(key)),
            )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


POINT = Shape(
    "point",
    carries="a single number for the estimand, with its interval",
    lives_in="point",
    # Not truthiness: a null effect is an answer, and ``0.0`` is one.
    detect=lambda estimate: estimate.get("point") is not None,
)
DOSE_RESPONSE_CURVE = Shape(
    "dose_response_curve",
    carries="an effect at each sampled dose, against a reference dose",
    lives_in="dose_response_curve",
)
MEDIATION_DECOMPOSITION = Shape(
    "mediation_decomposition",
    carries="the total effect split into what runs through the mediator "
            "and what does not",
    lives_in="decomposition",
)
JOINT_CONTRAST = Shape(
    "joint_contrast",
    carries="the contrast between two joint treatment corners, and the "
            "highest-order interaction among them",
    lives_in="joint_effect",
)
COUNTERFACTUAL_CELL_BOUNDS = Shape(
    "counterfactual_cell_bounds",
    carries="bounds on one cell of the counterfactual joint distribution, "
            "which monotonicity would have sharpened to a point",
    lives_in="counterfactual_cell",
)
NO_EFFECT_TEST = Shape(
    "no_effect_test",
    carries="whether the treatment affects the outcome at all, with no "
            "statement of by how much",
    lives_in="no_effect_test",
)
CAUSATION_POINTS = Shape(
    "causation_points",
    carries="the probabilities of necessity, sufficiency and both, as "
            "three named points — what monotonicity buys",
    lives_in="probabilities_of_causation",
    # The block is present either way; what monotonicity buys sits INSIDE
    # each quantity, so the point is what tells the two modes apart. PN is
    # asked of all three together: they are identified or bounded as one.
    detect=lambda estimate: (
        ((estimate.get("probabilities_of_causation") or {}).get("pn") or {})
        .get("point") is not None
    ),
)
CAUSATION_BOUNDS = Shape(
    "causation_bounds",
    carries="bounds on the probabilities of necessity and sufficiency, "
            "which monotonicity would have sharpened to points",
    lives_in="probabilities_of_causation",
)

ALL: tuple[Shape, ...] = (
    POINT,
    DOSE_RESPONSE_CURVE,
    MEDIATION_DECOMPOSITION,
    JOINT_CONTRAST,
    NO_EFFECT_TEST,
    COUNTERFACTUAL_CELL_BOUNDS,
    CAUSATION_POINTS,
    CAUSATION_BOUNDS,
)


# The bimodal pairs. Sharper first: monotonicity was available, and what it
# buys is the sharper answer to the same question.
#
# The two are not symmetric, and the asymmetry is the whole point. A
# counterfactual cell IS one number, so POINT describes it. Probabilities of
# causation are three, so POINT never described them: it says "a single
# number for the estimand", and the one it rendered was the PN headline,
# printed with no name under a question line asking for all three by name.
_MONOTONE_OR_BOUNDED_CAUSATION = (CAUSATION_POINTS, CAUSATION_BOUNDS)
_MONOTONE_OR_BOUNDED_CELL = (POINT, COUNTERFACTUAL_CELL_BOUNDS)

SHAPES_OF: dict[str, tuple[Shape, ...]] = {
    # --- one number for one estimand ---------------------------------------
    "backdoor_linear": (POINT,),
    "backdoor_logistic": (POINT,),
    "aipw": (POINT,),
    "tmle": (POINT,),
    "ipw_stabilized": (POINT,),
    "ipw_ht": (POINT,),  # declared from ipw_stabilized; suite never triggers
    "frontdoor_linear": (POINT,),
    "frontdoor_logistic": (POINT,),
    "iv_wald": (POINT,),
    "iv_stratified_wald": (POINT,),
    "iv_2sls": (POINT,),
    "iv_acr": (POINT,),
    "iv_2sls_overid": (POINT,),
    "transport_post_stratification": (POINT,),
    "longitudinal_gformula": (POINT,),
    "longitudinal_ipw_msm": (POINT,),
    "missing_data_recovery_gformula": (POINT,),
    "general_id_plugin": (POINT,),
    "general_id_idc_plugin": (POINT,),
    "ctf_conjunction_plugin": (POINT,),
    "proximal_matrix": (POINT,),
    # A DIFFERENT method and not a second shape of ``proximal_matrix``,
    # because it is a different computation answering a different question:
    # formula (5) inverts a channel to get a number, and this stacks the
    # channel across levels to test whether one is needed at all. A run
    # arrives here only where the first refused, so the two never coexist —
    # but a reader handed the answer must be able to see WHICH was run, and
    # a method that could mean either would not tell them.
    "proximal_null_test": (NO_EFFECT_TEST,),
    # Bimodal, and on the treatment's own cardinality rather than on an
    # assumption: two levels are a contrast, more are a curve. Both shapes
    # come out of the same theorem — (4) identifies E[Y(a)] one level at a
    # time — so this is one method with two answer shapes and not two
    # methods, and ``detect`` tells a surface which one it is holding.
    "proximal_bridge": (POINT, DOSE_RESPONSE_CURVE),
    "scm_counterfactual_linear_fit": (POINT,),
    "selection_backdoor_recovery": (POINT,),
    "measurement_error_correction": (POINT,),
    # Bimodal on the exposure's cardinality, the way ``proximal_bridge`` is:
    # a binary exposure has one contrast and reports it as a point, while a
    # polytomous one has no single difference and answers with the curve — plus
    # the point at the level the query named, when it named one.
    "exposure_measurement_error_correction": (POINT, DOSE_RESPONSE_CURVE),
    "combined_measurement_error_correction": (POINT, DOSE_RESPONSE_CURVE),
    "regression_calibration": (POINT,),
    # --- shapes a point cannot hold ----------------------------------------
    "mediation_linear_imai": (MEDIATION_DECOMPOSITION,),
    "mediation_logit_imai": (MEDIATION_DECOMPOSITION,),
    "mediation_joint_linear": (MEDIATION_DECOMPOSITION,),
    "mediation_joint_logit": (MEDIATION_DECOMPOSITION,),
    "joint_backdoor_linear": (JOINT_CONTRAST,),
    # declared from joint_backdoor_linear; suite never triggers it
    "joint_backdoor_logistic": (JOINT_CONTRAST,),
    # The same shape by the other road: where adjustment fails and the set-
    # valued ID still identifies the joint effect, the answer is still a
    # contrast between two corners of the treatment box with the K-way
    # interaction beside it. It reported a bare POINT while the intervention
    # was a set plus one shared level, which could only name the two uniform
    # corners; the mixed ones the interaction is built from were unsayable.
    "joint_general_id_plugin": (JOINT_CONTRAST,),
    "dose_response_linear_dml": (DOSE_RESPONSE_CURVE,),
    "dose_response_causal_forest_dml": (DOSE_RESPONSE_CURVE,),
    "dose_response_linear_drlearner": (DOSE_RESPONSE_CURVE,),
    # --- sharper when monotonicity holds, bounded when it does not ---------
    "causation_plugin": _MONOTONE_OR_BOUNDED_CAUSATION,
    "counterfactual_cell_plugin": _MONOTONE_OR_BOUNDED_CELL,
}


class UnknownMethod(KeyError):
    """An estimate names a method no shape has been declared for.

    Reachable only past the schema, whose ``method`` enum this table covers
    exactly. Raised rather than defaulted because the default that was there
    before — try every probe, fall through to whatever is left — is what put
    a structural verdict in the answer slot.
    """


def shape_of(estimate: Estimate) -> Shape | None:
    """Which shape this estimate came out in, or ``None`` if it carries none.

    ``None`` is not a fall-through licence. It says the estimator produced a
    block with no answer in it, which every caller should say out loud rather
    than quietly render something else.
    """
    method = estimate.get("method")
    try:
        candidates = SHAPES_OF[method]  # type: ignore[index]  # a block
        # naming no method must miss too, and say so the same way
    except KeyError:
        raise UnknownMethod(
            f"no answer shape declared for method {method!r}; add it to "
            f"themis.answers.SHAPES_OF beside the estimator that emits it"
        ) from None
    for shape in candidates:
        if shape.detect(estimate):  # type: ignore[misc]  # never None past
            # __post_init__, which fills in the default detector
            return shape
    return None


def bind(renderers: Mapping[Shape, R]) -> dict[Shape, R]:
    """One surface's renderers, checked against the vocabulary both ways.

    An unbound shape is an answer that reaches this surface and produces
    nothing — the silence this module exists to remove. A bound shape outside
    the vocabulary is a renderer no estimate can reach: dead copy that reads
    like coverage.
    """
    missing = sorted(s.name for s in ALL if s not in renderers)
    if missing:
        raise ValueError(
            f"no renderer for answer shape {missing}; an estimate in that "
            f"shape would reach this surface and say nothing"
        )
    extra = sorted(str(s) for s in renderers if s not in ALL)
    if extra:
        raise ValueError(
            f"renderer bound for {extra}, which is not a declared answer "
            f"shape (themis.answers.ALL)"
        )
    return dict(renderers)
