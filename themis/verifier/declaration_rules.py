"""A block's record of how a declared quantity was settled, against the
premise it declared.

A measurement-error correction reads something the caller declared, and
there are two ways to declare one. Saying only the value means "this is
exact" — a dose fixed by protocol, a rounding width, a coding rule set by
protocol — and the interval then prices the main sample alone. Saying the
value AND what the study that measured it actually produced means the
bootstrap redrew it every round, and the interval carries that study's
uncertainty too.

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
one is edited. What differs between the families is a handful of nouns —
what was declared, and how a study's version of it gets redrawn — and those
are what :class:`Declaration` carries. What is judged is the agreement,
which has no shape.

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
    #: How a round redraws it once a study is declared.
    how: str


#: A classical measurement-error variance on one column.
VARIANCE = Declaration(
    stem="design_error_variance_",
    noun="measurement-error variance",
    short="σ²_u",
    record="a validation study's degrees of freedom",
    how="as σ̂²·df/χ²_df",
)

#: A misclassification channel's confusion matrix on one column.
CONFUSION_MATRIX = Declaration(
    stem="confusion_matrix_",
    noun="confusion matrix",
    short="the matrix",
    record="a validation study's count table",
    how="from each column's Dirichlet",
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
        redrawn = column in carried
        owed = family.stem + (
            FROM_A_VALIDATION_STUDY if redrawn else KNOWN_AND_FIXED) + column
        wrong = family.stem + (
            KNOWN_AND_FIXED if redrawn else FROM_A_VALIDATION_STUDY) + column
        if owed in said:
            if wrong in said:
                _reject(
                    rule,
                    f"{column} declares both {owed!r} and {wrong!r}. They are "
                    f"the two answers to one question — was {family.short} "
                    f"taken as exact, or redrawn from the study that measured "
                    f"it — and a reader handed both cannot tell which "
                    f"interval they are looking at"
                )
            continue
        if wrong in said:
            did, says = (
                (f"redrew {family.short} each bootstrap round {family.how}, "
                 f"so its interval carries the validation study's "
                 f"uncertainty as well as the main sample's",
                 f"the {family.noun} was taken as exact")
                if redrawn else
                (f"held {family.short} still, so its interval prices the "
                 f"main sample alone",
                 "a validation study's uncertainty was carried into the "
                 "interval")
            )
            _reject(
                rule,
                f"the block says the correction on {column} {did}, and the "
                f"premise it declares ({wrong!r}) says {says}. The two "
                f"intervals are the same pair of numbers on the page, so a "
                f"reader has nothing but this premise to tell them apart"
            )
        _reject(
            rule,
            f"{column} carries a {family.noun} and declares neither "
            f"{owed!r} nor its counterpart. Which of the two the correction "
            f"rests on decides what a reader would have to check to refute "
            f"it, and a premise that reaches no ledger is one nobody was "
            f"asked to check"
        )
