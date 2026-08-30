"""The block's record of how σ²_u was settled, against the premise it declared.

A measurement-error correction reads a variance the caller declared, and there
are two ways to declare one. Saying only the number means "this is exact" — a
dose fixed by protocol, a rounding width — and the interval then prices the
main sample alone. Saying the number AND the degrees of freedom of the study
that estimated it means the bootstrap redrew σ²_u every round as σ̂²·df/χ²_df,
and the interval carries that study's uncertainty too.

The block records which happened. The premise id says which happened. **They
are one fact written twice**, and the failure worth catching is the pair
disagreeing: a reader told the validation study was priced in, over an
interval that held σ²_u still, is reading protection the number does not have
— and it is the SAME two numbers on the page either way, so nothing about the
interval's appearance gives it away. The mirror case is no better and quieter:
an interval that did widen, under a premise saying it could not have.

One module for both corrections that redraw, because the fact is theirs
jointly and a rule written twice is two rules on the day one is edited. What
each caller supplies is its own block's shape; what is judged here is the
agreement, which has no shape.

**Independence pin:** this module MUST NOT import from ``themis.estimation``
or ``themis.output``. The premise stems below are restated rather than
imported, for the reason every verifier restates what it checks — an id read
from the producer's own table agrees with the producer by construction.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NoReturn

from .errors import VerificationError

#: The premise a column declares when its σ²_u is taken as exact, and the one
#: it declares when a validation study estimated it. Both end in the column's
#: own name, because each column's variance comes from its own study and each
#: can separately be wrong.
KNOWN_AND_FIXED = "design_error_variance_known_and_fixed_on_"
FROM_A_VALIDATION_STUDY = "design_error_variance_from_a_validation_study_on_"


def _reject(rule: str, message: str) -> NoReturn:
    raise VerificationError(f"{rule}: {message}", step_index=None, rule=rule)


def check_variance_premises(
    *,
    rule: str,
    declared: Iterable[str],
    mismeasured: Iterable[str],
    validation_df: Mapping[str, object],
) -> None:
    """Hold one estimate's variance premises to what its block records.

    ``rule`` names the caller in the rejection, so a reader learns which
    audit found it. ``declared`` is the estimate's own ``assumptions``.
    ``mismeasured`` is every column carrying a σ²_u. ``validation_df`` maps
    the subset of those whose σ²_u came from a study to that study's degrees
    of freedom — empty when none did.

    Raises :class:`VerificationError` on a df recorded for a column that
    declares no variance, and on any column whose premise names the wrong one
    of the two ways to declare.
    """
    said = {a for a in declared if isinstance(a, str)}
    columns = list(mismeasured)

    stray = [v for v in validation_df if v not in columns]
    if stray:
        _reject(
            rule,
            f"a validation study's degrees of freedom are recorded for "
            f"{stray!r}, which declares no measurement-error variance at "
            f"all. Degrees of freedom say how well a number is known, so "
            f"recorded against no number they qualify nothing — and the "
            f"columns that DO carry a variance are then left looking as "
            f"though theirs was taken as exact"
        )

    for column in columns:
        redrawn = column in validation_df
        owed = (FROM_A_VALIDATION_STUDY if redrawn else KNOWN_AND_FIXED) + column
        wrong = (KNOWN_AND_FIXED if redrawn else FROM_A_VALIDATION_STUDY) + column
        if owed in said:
            if wrong in said:
                _reject(
                    rule,
                    f"{column} declares both {owed!r} and {wrong!r}. They are "
                    f"the two answers to one question — was σ²_u taken as "
                    f"exact, or redrawn from the study that estimated it — "
                    f"and a reader handed both cannot tell which interval "
                    f"they are looking at"
                )
            continue
        if wrong in said:
            did, says = (
                ("redrew σ²_u each bootstrap round, so its interval carries "
                 "the validation study's uncertainty as well as the main "
                 "sample's", "the variance was taken as exact")
                if redrawn else
                ("held σ²_u still, so its interval prices the main sample "
                 "alone", "a validation study's uncertainty was carried into "
                 "the interval")
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
            f"{column} carries a measurement-error variance and declares "
            f"neither {owed!r} nor its counterpart. Which of the two the "
            f"correction rests on decides what a reader would have to check "
            f"to refute it, and a premise that reaches no ledger is one "
            f"nobody was asked to check"
        )
