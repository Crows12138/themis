"""What an interval's width is a fact about, and how tight it is.

Two numbers with a comma between them look the same however they were
arrived at, and on one envelope they are not the same kind of statement.
An ``iv_wald`` estimate reports ``[0.326, 0.426]`` and carries a
``precision_budget`` saying N≈16000 halves it; the Manski row beside it
reports ``[0.348, 0.852]``, and no amount of data narrows that at all —
its width is what the assumptions leave undetermined. The Balke-Pearl row
beside THAT reports ``[0.552, 0.759]``, and the 2.4× it gains over Manski
is bought entirely by declaring an instrument. Three intervals, one
result, and nothing a reader could ask to tell the three apart.

The fact was not missing everywhere. It was RECOVERED, separately, by
whoever needed it: the report's causation renderer probes ``point is not
None`` to decide between "CI" and "外带" and says so in a comment ("one
pair of CI keys, two meanings"); the explainer probes the same thing about
a counterfactual cell and calls the answer "区间自身的抽样带";
``verdict.ts`` derives it again for its own chip; ``types.ts`` states it a
fourth time in prose. Four workings-out, four namings, and no two of them
the same words. And ``numeric_result.interval`` — where a bounded
counterfactual's answer lands — carries ``{low, high}`` and nothing else,
so there is nothing to recover it from at all.

A missing FIELD, not a missing sentence, is what this is, and the proof is
that it is stopping code from being written today:
:func:`themis.estimation.bounds_numeric.evaluate_manski_tamer_bounds`
declines to report a contrast it could compute, because subtracting two
MTR intervals gives an outer bound rather than a sharp one and "the
envelope has no field saying which a row is". A valid-but-unsharp row
shipped unlabelled beside sharp ones would be this defect wearing its
other face.

So both facts are declared here, both are carried on the envelope, and
every surface reads them instead of deriving them:

- :class:`Width` — what this pair's width is a fact about. Three members,
  because a confidence statement about a POINT and a confidence statement
  about an identified SET are different objects that share one pair of key
  names, and the identified set itself is a third thing that is not a
  confidence statement at all.
- :class:`Tightness` — whether a narrower set is consistent with the same
  assumptions. Orthogonal to the above: an outer band around a non-sharp
  set is a perfectly ordinary thing to report, and saying only one of the
  two tells a reader the wrong half.

:data:`DECLARED` is the census: every pair of endpoints the envelope can
carry, and which of the three its width is. A test walks
``query_result.schema.json`` for endpoint pairs and holds the two equal in
both directions, the arrangement ``GapKind`` and ``answers.SHAPES_OF``
already use — so a pair added to the schema without an answer to "what is
this the width of" fails rather than joining the ones a reader has to
guess at.

Two of the twenty-six are settled by the run rather than by the slot, and
that is the whole shape of the defect at its sharpest: on a causation
quantity and on a counterfactual cell, ``ci_lower`` / ``ci_upper`` is the
point's bootstrap CI when monotonicity bought a point and the outer band
on ``[lower, upper]`` when it did not. Those two name the envelope field
that settles them (``settled_by``) rather than asserting a width, and the
producer that knows writes it.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import unique
from typing import Mapping, TypeVar

from .language import DEFAULT, Lang, Words, gloss
from .types import EnvelopeName

R = TypeVar("R")


@unique
class Width(EnvelopeName):
    """What this pair of endpoints' width is a fact about.

    The member a reader needs is the one that answers "what would make
    this narrower", and the three answers are different: more rows, a
    stronger assumption, and both. Rendering two numbers without it is
    what let an assumption-free floor and a bootstrap CI sit on one screen
    as though the second were simply the tighter of two estimates.
    """

    narrows_with: str
    """What actually shrinks this width, for whoever is deciding whether a
    candidate member belongs here. One language, like a docstring: it is
    written for the person adding a member, not for the reader."""

    words: Words
    """The reader's name for this kind of interval, by language."""

    advice: Words
    """What the reader can do about the width, by language. This is the
    half a bare pair of numbers cannot carry and the half that decides
    what someone does next."""

    def __new__(cls, value: str, narrows_with: str, words: Words,
                advice: Words):
        width = str.__new__(cls, value)
        width._value_ = value
        width.narrows_with = narrows_with
        width.words = words
        width.advice = advice
        return width

    SAMPLING = (
        "sampling",
        "more rows: the width is dominated by 1/sqrt(N) and goes to zero",
        {"zh": "置信区间", "en": "confidence interval"},
        {"zh": "再收数据会变窄——宽度是这批样本的事",
         "en": "more data narrows this — the width is a fact about this "
               "sample"},
    )
    IDENTIFICATION = (
        "identification",
        "a stronger assumption, and nothing else: this is the set the "
        "premises leave undetermined, and it is the same set at N=10^9",
        {"zh": "识别区间", "en": "identified interval"},
        {"zh": "再收数据不会变窄——宽度是这套假设的事，要窄得再加一条假设",
         "en": "more data does not narrow this — the width is a fact about "
               "the assumptions, and only a further assumption narrows it"},
    )
    OUTER_BAND = (
        "outer_band",
        "more rows, down to the identification width and no further: it is "
        "a confidence statement ABOUT the identified set, not about a point",
        {"zh": "识别区间的外带", "en": "outer band on the identified interval"},
        {"zh": "再收数据会收到识别区间那么窄为止，再窄要加假设",
         "en": "more data narrows this as far as the identified interval and "
               "no further; past that it takes a further assumption"},
    )


@unique
class Tightness(EnvelopeName):
    """Whether a narrower set is consistent with the same assumptions.

    A separate question from :class:`Width`, and one a reader cannot infer
    from the method's reputation: the same procedure is sharp on one
    estimand and an outer bound on another. Manski-Tamer bounds an ARM
    sharply and its arms are tied together at the unit level, so the
    difference of the two intervals is wider than the interval of the
    difference.
    """

    words: Words
    """The reader's word, by language."""

    advice: Words
    """Whether a better procedure could narrow this without a new
    assumption — which is a different offer from the one ``Width`` makes,
    and the one a reader would otherwise never be made."""

    def __new__(cls, value: str, words: Words, advice: Words):
        tight = str.__new__(cls, value)
        tight._value_ = value
        tight.words = words
        tight.advice = advice
        return tight

    SHARP = (
        "sharp",
        {"zh": "紧的", "en": "sharp"},
        {"zh": "这已经是这套假设下最窄的区间了——没有更好的算法能收得更紧",
         "en": "this is the narrowest interval these assumptions allow — no "
               "better procedure tightens it"},
    )
    OUTER = (
        "outer",
        {"zh": "外界（不一定最紧）", "en": "an outer bound (not necessarily "
                                          "the tightest)"},
        {"zh": "真实的识别区间可能比这窄——这里报的是一个有效上界，"
               "不加假设也可能还有收紧的余地",
         "en": "the identified interval may be narrower than this — what is "
               "reported is a valid outer bound, and there may be room to "
               "tighten it without any further assumption"},
    )


@dataclass(frozen=True)
class Endpoints:
    """One pair of endpoints the envelope can carry, and what it is.

    ``container`` is the dotted path in ``query_result.schema.json`` — a
    ``$defs`` name where the shape is shared and reached through a
    ``$ref``, since that is the one place the pair is declared and
    therefore the one place a new one can be added.

    ``width`` is None exactly where the slot does not settle the question
    and the run does; then ``settled_by`` names the envelope field the
    producer writes it into. Neither may be given without the other, and
    a pair with neither would be a pair whose reader is back to guessing.
    """

    container: str
    lower: str
    upper: str
    width: Width | None
    settled_by: str | None
    #: Why this pair is what it is, for whoever adds the next one. One
    #: language, and keyword-only: it is a note with no reader, and giving
    #: it a name is what lets the language gate say so about this slot
    #: rather than about "the sixth argument".
    because: str = dataclasses.field(kw_only=True)

    def __post_init__(self) -> None:
        if (self.width is None) == (self.settled_by is None):
            raise ValueError(
                f"{self.container}.({self.lower}, {self.upper}) must either "
                f"declare a width or name the field that settles it, and "
                f"exactly one of the two"
            )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.container}.({self.lower}, {self.upper})"


#: The field a run-decided pair's producer writes its width into. One name
#: for both such pairs: they are the same question about the same pair of
#: keys, and two names would be two vocabularies for one fact.
CI_WIDTH_FIELD = "ci_width_is"

#: The field a bounds row states its tightness in.
TIGHTNESS_FIELD = "tightness"


# --- the identified sets ------------------------------------------------------
# The answer itself where a point is out of reach. Not a confidence
# statement about anything: at any sample size these are the endpoints the
# premises leave, and the bootstrap band beside them is the separate thing.

_SETS = (
    Endpoints(
        "$defs.boundsResult", "lower_value", "upper_value",
        Width.IDENTIFICATION, None,
        because="the partial-identification layer's answer for the arm the query "
        "named; every row on one result brackets the same estimand and "
        "they differ by what each row assumes",
    ),
    Endpoints(
        "$defs.boundsResult.contrast", "lower_value", "upper_value",
        Width.IDENTIFICATION, None,
        because="the same, for the contrast an effect query actually asked about",
    ),
    Endpoints(
        "$defs.causationEstimate", "lower", "upper",
        Width.IDENTIFICATION, None,
        because="Tian-Pearl bounds on one probability of causation, from data; "
        "assumption-free, so monotonicity does not move them",
    ),
    Endpoints(
        "$defs.causationQuantity", "lower", "upper",
        Width.IDENTIFICATION, None,
        because="the same quantity on the theta path, where there is no sample to "
        "have uncertainty about",
    ),
    Endpoints(
        "numeric_estimate.counterfactual_cell", "lower", "upper",
        Width.IDENTIFICATION, None,
        because="the response-function polytope's bounds on one counterfactual cell",
    ),
    Endpoints(
        "numeric_result.interval", "low", "high",
        Width.IDENTIFICATION, None,
        because="the generic answer slot, reached when the answer IS an interval — "
        "a bounded counterfactual, a bounded probability of causation. It "
        "carries no point, no method and no ci_level, so it was the one "
        "pair with nothing at all to recover this from",
    ),
)


# --- confidence statements about a set ----------------------------------------

_BANDS = (
    Endpoints(
        "$defs.boundsResult", "ci_lower", "ci_upper",
        Width.OUTER_BAND, None,
        because="a percentile-bootstrap OUTER band for the identified set: the "
        "lower-alpha/2 quantile of the bootstrapped lower endpoint and the "
        "upper-alpha/2 quantile of the upper. It covers the SET with "
        "probability >= 1-alpha, which is a different target from the "
        "Imbens-Manski interval for the point and is wider. A bounds row "
        "carries no point, so this pair is never the other thing",
    ),
)


# --- settled by the run, not by the slot --------------------------------------
# One pair of keys, two objects, and which one came out is a fact about the
# run: monotonicity buys a point on some data and not on other data.

_BIMODAL = (
    Endpoints(
        "$defs.causationEstimate", "ci_lower", "ci_upper",
        None, CI_WIDTH_FIELD,
        because="the point's bootstrap CI when monotonicity identified PN/PS/PNS, "
        "and the outer band on [lower, upper] when it did not",
    ),
    Endpoints(
        "numeric_estimate.counterfactual_cell", "ci_lower", "ci_upper",
        None, CI_WIDTH_FIELD,
        because="the same two objects in one pair of keys, one cell down",
    ),
)


# --- confidence intervals for a point -----------------------------------------
# The ordinary case, and the majority. Named here rather than left to the
# ``ci_`` prefix, because the prefix is exactly what the three above share
# with them.

def _point_ci(container: str, *, because: str) -> Endpoints:
    return Endpoints(container, "ci_lower", "ci_upper",
                     Width.SAMPLING, None, because=because)


_POINT_CIS = (
    _point_ci("numeric_estimate",
              because="the headline estimate's interval, and what precision_budget "
              "budgets against"),
    _point_ci("numeric_estimate.decomposition.te", because="mediation: total effect"),
    _point_ci("numeric_estimate.decomposition.nde",
              because="mediation: natural direct effect"),
    _point_ci("numeric_estimate.decomposition.nie",
              because="mediation: natural indirect effect"),
    _point_ci("numeric_estimate.decomposition.proportion_mediated",
              because="mediation: the share running through the mediator"),
    _point_ci("$defs.cdeReferenceEstimate",
              because="the controlled direct effect at each level M was fixed to"),
    _point_ci("$defs.componentEstimate",
              because="one term of VanderWeele's four-way decomposition"),
    _point_ci("$defs.ratioComponentEstimate",
              because="the same decomposition on the ratio scale"),
    _point_ci("numeric_estimate.dose_response_curve[]",
              because="the effect at one sampled dose against the reference dose"),
    _point_ci("numeric_estimate.interaction",
              because="the highest-order interaction among joint treatments"),
    _point_ci("numeric_estimate.joint_effect",
              because="the contrast between two joint treatment corners"),
    _point_ci("numeric_estimate.longitudinal_gformula",
              because="the g-formula's strategy contrast"),
    _point_ci("numeric_estimate.longitudinal_ipw_msm",
              because="the marginal structural model's strategy contrast"),
    _point_ci("numeric_estimate.recovered_ate",
              because="the ATE recovered from incomplete data"),
)


# --- weak-instrument-robust confidence sets -----------------------------------
# A confidence statement about the point, arrived at by inverting a test
# rather than by a standard error, which is why it is spelled with the
# identified-set key names and is not one. An unbounded set is not a wide
# interval: it is the statement that these data do not constrain the
# effect, and ``kind`` is where that is said.

def _ar_set(container: str, *, because: str) -> Endpoints:
    return Endpoints(container, "lower", "upper", Width.SAMPLING, None,
                     because=because)


_AR_SETS = (
    _ar_set("numeric_estimate.anderson_rubin_confidence_set",
            because="Anderson-Rubin: the beta values the moment condition does not "
            "reject at this level, whatever the instrument's strength"),
    _ar_set("numeric_estimate.stratified_anderson_rubin_confidence_set",
            because="the same inversion, within a stratum"),
    _ar_set("numeric_estimate.robust_anderson_rubin_confidence_set.segments[]",
            because="one piece of a heteroskedasticity-robust set, which is the only "
            "producer that can return more than two"),
)


DECLARED: tuple[Endpoints, ...] = (
    *_SETS, *_BANDS, *_BIMODAL, *_POINT_CIS, *_AR_SETS,
)

BY_PAIR: dict[tuple[str, str, str], Endpoints] = {
    (e.container, e.lower, e.upper): e for e in DECLARED
}


class UnknownEndpoints(KeyError):
    """The envelope carries a pair of endpoints nothing has classified.

    Raised rather than defaulted to ``SAMPLING``: the default is what the
    ``ci_`` prefix already was, and it is wrong on three of the pairs that
    wear it.
    """


class WidthNotStated(ValueError):
    """A run-decided pair reached a reader with nothing saying which it is.

    The producer that knows — the one that saw whether a point came out —
    did not write ``ci_width_is``. Recovering it here from ``point is not
    None`` is exactly what this module exists to stop: that recovery is
    correct today and is a second record of the same fact.
    """


def pair_at(container: str, lower: str, upper: str) -> Endpoints:
    """What the endpoints at this slot are, or a refusal naming the slot."""
    try:
        return BY_PAIR[(container, lower, upper)]
    except KeyError:
        raise UnknownEndpoints(
            f"no width declared for {container}.({lower}, {upper}); add it "
            f"to themis.intervals.DECLARED beside the producer that writes it"
        ) from None


def width_of(pair: Endpoints, row: Mapping[str, object]) -> Width:
    """Which of the three this pair's width is, on THIS row.

    Fixed for twenty-four of the twenty-six; for the other two the row
    carries the answer, and a row that does not is refused rather than
    read as the common case.
    """
    if pair.width is not None:
        return pair.width
    said = row.get(pair.settled_by)  # type: ignore[arg-type]  # never None
    # here: __post_init__ admits only one of the two being absent
    if said is None:
        raise WidthNotStated(
            f"{pair} is settled by the run, and this row carries no "
            f"{pair.settled_by!r}; the estimator that knows whether a point "
            f"came out has to write it"
        )
    return width_named(str(said))


_WIDTHS = {str(w): w for w in Width}
_TIGHTNESSES = {str(x): x for x in Tightness}
#: Derived from the members rather than written again: the words a reader
#: gets are the ones on the vocabulary, and a second table of them would be
#: the duplication this module was built to remove.
_WIDTH_WORDS: dict[str, Words] = {k: v.words for k, v in _WIDTHS.items()}
_TIGHTNESS_WORDS: dict[str, Words] = {
    k: v.words for k, v in _TIGHTNESSES.items()
}


def width_word(value: object, lang: Lang | str = DEFAULT) -> str:
    """What this interval's width is a fact about, for the reader."""
    return gloss(_WIDTH_WORDS, value, lang)


def tightness_word(value: object, lang: Lang | str = DEFAULT) -> str:
    """Whether a narrower set is consistent with the same assumptions, for
    the reader."""
    return gloss(_TIGHTNESS_WORDS, value, lang)


UNSTATED: Words = {
    "zh": "宽度未声明的区间",
    "en": "interval of unstated width",
}
"""What a row from before the field existed is called.

Not a fourth member: it is the absence of an answer, and a surface that
picked one of the three for it would be doing the deriving this module
exists to stop. Here rather than on each surface because two of them ask
the same question about the same pair, and a word invented twice is a
word that differs twice.
"""


def width_or_unstated(pair: Endpoints,
                      row: Mapping[str, object]) -> tuple[Width | None, Words]:
    """This pair's width and the reader's name for it, or neither.

    The refusal is a species of its own so that a renderer can tell "nobody
    said" — which degrades to a word, the way an unrecognised gloss does
    everywhere — from "that is not one of the three", which is a producer
    writing a spelling that does not exist and should not be smoothed over.
    """
    try:
        width = width_of(pair, row)
    except WidthNotStated:
        return None, UNSTATED
    return width, width.words


def width_named(value: object) -> Width:
    """That word as the member it names, or a refusal that lists the words.

    A lookup rather than ``Width(value)``, for the reason
    :func:`themis.ledger.provenance_named` is one: an enum that hangs facts
    off its members through ``__new__`` reads to a type checker as a
    constructor wanting three more arguments, and calling it by value is
    also silent about what the alternatives were.
    """
    member = _WIDTHS.get(str(value))
    if member is None:
        raise ValueError(
            f"intervals: {str(value)!r} is not what an interval's width can "
            f"be a fact about; they are {sorted(_WIDTHS)}"
        )
    return member


def tightness_named(value: object) -> Tightness:
    """The same, one axis over."""
    member = _TIGHTNESSES.get(str(value))
    if member is None:
        raise ValueError(
            f"intervals: {str(value)!r} is not a declared tightness; "
            f"they are {sorted(_TIGHTNESSES)}"
        )
    return member


#: How tight each bounds method's interval is, per pair, because the two
#: are not the same question: Balke-Pearl runs a SECOND optimisation over
#: the same polytope for the contrast, since a response-type model
#: constrains the two arms together; Manski natural assumes nothing, so
#: the two arms' unobserved masses are disjoint sub-populations and the
#: difference of the intervals IS the interval of the difference.
#:
#: ``None`` says this repository has no producer for that row, so there is
#: nothing to be tight or loose. A test holds those entries equal to the
#: methods the kernel's bounds verifier refuses, which is the other place
#: the same fact is written.
TIGHTNESS_OF: dict[tuple[str, str], Tightness | None] = {
    ("manski_natural", "arm"): Tightness.SHARP,
    ("manski_natural", "contrast"): Tightness.SHARP,
    ("balke_pearl_iv", "arm"): Tightness.SHARP,
    ("balke_pearl_iv", "contrast"): Tightness.SHARP,
    ("manski_tamer_monotonicity", "arm"): Tightness.SHARP,
    # Sharp, and the reasoning that expected an outer bound here is worth
    # keeping because it was so nearly right: MTR does tie Y(1) and Y(0)
    # together at the unit level. What it does not do is tie the two ARMS
    # together — the other arm's units' Y(x) and this arm's units' Y(x')
    # are disjoint sub-populations, each confined only by its own unit's
    # observation — so every pair of points in the two intervals is jointly
    # attainable and the difference of the intervals is the interval of the
    # difference. Enumerating the response types MTR permits gives the same
    # endpoints term for term.
    ("manski_tamer_monotonicity", "contrast"): Tightness.SHARP,
    ("frontdoor_partial", "arm"): None,
    ("frontdoor_partial", "contrast"): None,
}


def tightness_of(method: str, pair: str = "arm") -> Tightness:
    """How tight this method's interval for this pair is."""
    try:
        said = TIGHTNESS_OF[(method, pair)]
    except KeyError:
        raise UnknownEndpoints(
            f"no tightness declared for bounds method {method!r} ({pair}); "
            f"add it to themis.intervals.TIGHTNESS_OF beside the procedure"
        ) from None
    if said is None:
        raise UnknownEndpoints(
            f"bounds method {method!r} reports no {pair}, so there is "
            f"nothing to call sharp or loose"
        )
    return said


def bind(readings: Mapping[Width, R]) -> dict[Width, R]:
    """One surface's renderings, checked against the vocabulary both ways.

    An unbound member is a width this surface renders by falling back, and
    a fallback reads exactly like coverage — which is how one pair of keys
    carried two meanings on three surfaces at once.
    """
    missing = sorted(str(w) for w in Width if w not in readings)
    if missing:
        raise ValueError(
            f"no rendering for interval width {missing}; an interval of "
            f"that kind would reach this surface and be described as some "
            f"other kind"
        )
    extra = sorted(str(w) for w in readings if not isinstance(w, Width))
    if extra:
        raise ValueError(
            f"rendering bound for {extra}, which is not a declared interval "
            f"width (themis.intervals.Width)"
        )
    return dict(readings)
