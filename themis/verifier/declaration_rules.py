"""A block's record of how a declared quantity was settled, against the
premise it declared.

A measurement-error block reads something the caller declared, and there
are two ways to declare one. Saying only the value means "this is exact" —
a dose fixed by protocol, a rounding width, a coding rule set by protocol —
and the interval then prices the main sample alone. Saying the value AND
what the study that measured it actually produced means that study's
uncertainty reaches the interval too.

**HOW it reaches the interval is not what is judged here**, and for a
while the wording assumed it was. Where a correction is resampled the
quantity is redrawn every bootstrap round; where a block prices somebody
ELSE's interval, nothing is redrawn and the widening factor's endpoints
are read as exact quantiles of the study's own χ². Rejections written
around the first of those could only be registered by families that
redraw, so the two families that price a factor stayed outside this module
and went on declaring the exact-value premise over intervals that carried
a study — which is this module's own failure mode, committed on the two
declarations it never saw. The clause naming what a run DID is therefore
carried by the family, and what is judged is the agreement, which has no
shape.

The block records which happened. The premise id says which happened.
**They are one fact written twice**, and the failure worth catching is the
pair disagreeing: a reader told the validation study was priced in, over an
interval that held the quantity still, is reading protection the number
does not have — and it is the SAME two numbers on the page either way, so
nothing about the interval's appearance gives it away. The mirror case is
no better and quieter: an interval that did widen, under a premise saying
it could not have.

One module for every declaration that can be settled either way, because
the fact is theirs jointly and a rule written twice is two rules on the day
one is edited. What differs between the families is a handful of nouns and
the two clauses above — what was declared, and what each of the two runs
did with it — and those are what :class:`Declaration` carries.

**Independence pin:** this module MUST NOT import from ``themis.estimation``
or ``themis.output``. The premise stems below are restated rather than
imported, for the reason every verifier restates what it checks — an id
read from the producer's own table agrees with the producer by
construction.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NoReturn

from .errors import VerificationError

#: The two answers to "how was this declaration settled", as they read in a
#: premise id. Restated here rather than imported; see the pin above.
KNOWN_AND_FIXED = "known_and_fixed_on_"
FROM_A_VALIDATION_STUDY = "from_a_validation_study_on_"


@dataclass(frozen=True)
class Declaration:
    """One family of declared quantity, in the words its rejections need.

    ``stem`` is what its premise ids begin with; the rest are nouns. They
    are here rather than inlined at the two call sites because a rejection
    a reader cannot place is a rejection they cannot act on — "the block
    says the correction redrew it" leaves them hunting for what "it" was.
    """

    stem: str
    #: What the caller declared, as a bare noun: "carries no ___ at all".
    noun: str
    #: The same thing named the way the arithmetic names it: "was ___
    #: taken as exact".
    short: str
    #: What a study hands over about it — degrees of freedom, a tally.
    record: str
    #: What a run whose interval carries the study did, as a whole clause.
    #: A whole clause rather than a slot in one written here, because the
    #: two ways a study reaches an interval have no sentence in common:
    #: "redrew it every round" and "read the factor's endpoints off it"
    #: share a subject and nothing else. A template with a hole in it would
    #: force the second family to describe itself in the first's words,
    #: which is the shape that kept them out of this module.
    priced: str
    #: ...and the mirror, for a run that took the declaration as exact.
    exact: str


#: A classical measurement-error variance on one column of the DESIGN.
VARIANCE = Declaration(
    stem="design_error_variance_",
    noun="measurement-error variance",
    short="σ²_u",
    record="a validation study's degrees of freedom",
    priced="redrew σ²_u every bootstrap round as σ̂²·df/χ²_df, so its "
           "interval carries the validation study's uncertainty as well as "
           "the main sample's",
    exact="held σ²_u still, so its interval prices the main sample alone",
)

#: A misclassification channel's confusion matrix on one column.
CONFUSION_MATRIX = Declaration(
    stem="confusion_matrix_",
    noun="confusion matrix",
    short="the matrix",
    record="a validation study's count table",
    priced="redrew the matrix every bootstrap round from each column's "
           "Dirichlet, so its interval carries the validation study's "
           "uncertainty as well as the main sample's",
    exact="held the matrix still, so its interval prices the main sample "
          "alone",
)

#: A classical measurement-error variance on the OUTCOME. The mirror of
#: :data:`VARIANCE` one channel over, and the mirror is not symmetric: σ²_v
#: never enters a correction, so nothing about it is resampled and the study
#: reaches the reader through the widening factor's own endpoints instead.
OUTCOME_ERROR_VARIANCE = Declaration(
    stem="outcome_error_variance_",
    noun="outcome measurement-error variance",
    short="σ²_v",
    record="a validation study's degrees of freedom",
    priced="read the widening factor's endpoints as exact quantiles of the "
           "study's own χ², so the factor it reports is an interval and "
           "carries that study's uncertainty",
    exact="reported the widening factor at the declared σ²_v as one number, "
          "with no interval around it",
)

#: The scatter of a true exposure around the nominal value that was recorded.
#: Priced exactly as the outcome channel is, on a share scaled by β̂².
BERKSON_SCATTER_VARIANCE = Declaration(
    stem="berkson_scatter_variance_",
    noun="Berkson scatter variance",
    short="σ²_u",
    record="a validation study's degrees of freedom",
    priced="read the widening factor's endpoints as exact quantiles of the "
           "study's own χ², so the factor it reports is an interval and "
           "carries that study's uncertainty",
    exact="reported the widening factor at the declared σ²_u as one number, "
          "with no interval around it",
)


def _reject(rule: str, message: str) -> NoReturn:
    raise VerificationError(f"{rule}: {message}", step_index=None, rule=rule)


def check_declaration_premises(
    family: Declaration,
    *,
    rule: str,
    declared: Iterable[str],
    measured: Iterable[str],
    carried: Mapping[str, object],
) -> None:
    """Hold one estimate's premises to what its block records.

    ``rule`` names the caller in the rejection, so a reader learns which
    audit found it. ``declared`` is the estimate's own ``assumptions``.
    ``measured`` is every column carrying a declaration of this family.
    ``carried`` maps the subset of those a study measured to whatever that
    study handed over — empty when none did.

    Raises :class:`VerificationError` on a study recorded against a column
    that declares nothing of this family, and on any column whose premise
    names the wrong one of the two ways to declare.
    """
    said = {a for a in declared if isinstance(a, str)}
    columns = list(measured)

    stray = [v for v in carried if v not in columns]
    if stray:
        _reject(
            rule,
            f"{family.record} is recorded for {stray!r}, which declares no "
            f"{family.noun} at all. What a study measured says how well a "
            f"number is known, so recorded against no number it qualifies "
            f"nothing — and the columns that DO carry one are then left "
            f"looking as though theirs was taken as exact"
        )

    for column in columns:
        studied = column in carried
        owed = family.stem + (
            FROM_A_VALIDATION_STUDY if studied else KNOWN_AND_FIXED) + column
        wrong = family.stem + (
            KNOWN_AND_FIXED if studied else FROM_A_VALIDATION_STUDY) + column
        if owed in said:
            if wrong in said:
                _reject(
                    rule,
                    f"{column} declares both {owed!r} and {wrong!r}. They are "
                    f"the two answers to one question — was {family.short} "
                    f"taken as exact, or did the study that measured it reach "
                    f"the interval — and a reader handed both cannot tell "
                    f"which interval they are looking at"
                )
            continue
        if wrong in said:
            did, says = (
                (family.priced, f"the {family.noun} was taken as exact")
                if studied else
                (family.exact,
                 "a validation study's uncertainty was carried into the "
                 "interval")
            )
            _reject(
                rule,
                f"the block records that on {column} the run {did}, and the "
                f"premise it declares ({wrong!r}) says {says}. The two "
                f"intervals are the same pair of numbers on the page, so a "
                f"reader has nothing but this premise to tell them apart"
            )
        _reject(
            rule,
            f"{column} carries a {family.noun} and declares neither "
            f"{owed!r} nor its counterpart. Which of the two the answer "
            f"rests on decides what a reader would have to check to refute "
            f"it, and a premise that reaches no ledger is one nobody was "
            f"asked to check"
        )
