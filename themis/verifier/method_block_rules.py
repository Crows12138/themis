"""A block an estimate carries says which method wrote it.

``numeric_estimate.method`` is not only a word a reader is shown. It is
the SWITCH eleven rules in this package are written behind: each opens
with ``if estimate.get("method") != X: return``, so a forged method word
does not merely misreport the run -- it turns off the rule that owns the
block the run left behind. Measured: on three stored answers the word
could be rewritten to ``aipw`` and every public door said yes, two of
them with a whole derivation chain beside them.

Those gates are one-sided, and the side they watch is the one visible
from where they stand. :func:`post_stratification_rules
.verify_post_stratification` says so itself -- it refuses an answer OF
ITS METHOD that carries no strata, "because 'nothing to check' is the
state this rule exists to make impossible to be in silently". The other
way into that state is to leave the strata where they are and change the
word, and by then the rule has already returned.

So the question is asked once, from outside every gate: a block that is
HERE names the methods that write it, and the run's own word has to be
one of them. Asked of the blocks rather than of the word, because the
blocks are what the estimator actually left behind and the word is the
thing being checked.

WHY A TABLE AND NOT A LINE IN EACH GATE. ``measurement_correction`` is
written by three methods -- a treatment-side correction, an exposure-side
one, and the combined route -- and no gate knows the other two. A check
added at each gate would refuse the honest exposure answer in the name of
the treatment rule. The correspondence is many-to-one, so it is stated
where all of it can be seen.

WHAT IS RESTATED HERE, AND WHAT IS NOT. The table below is this package's
own eleven gates written out as one fact, not a new claim about what a
producer emits. Every row is a block some rule already declines to read
unless the method is one of these; nothing here decides which blocks an
estimator may write. A block no gate guards is not in the table and this
rule says nothing about it, which is the honest state for a block nobody
has claimed yet rather than a silence to be fixed by guessing.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "method_block_check"

#: Which methods each guarded block is read under.
#:
#: Read off the gates rather than off the corpus: the corpus says which
#: pairs have occurred, and a rule built from that would call any pair it
#: has not seen a lie. The gates say which pairs this package is prepared
#: to re-derive, which is the claim being made. A test holds the table to
#: the corpus in the one direction that is safe -- no stored answer
#: disagrees with it -- and names the gate each row comes from.
WRITTEN_BY: dict[str, frozenset[str]] = {
    "differential_error": frozenset({
        "differential_regression_calibration"}),
    "differential_outcome_error": frozenset({
        "differential_outcome_correction"}),
    "measurement_correction": frozenset({
        "measurement_error_correction",
        "exposure_measurement_error_correction",
        "combined_measurement_error_correction",
    }),
    "over_identification": frozenset({"iv_2sls_overid"}),
    "post_stratification": frozenset({"transport_post_stratification"}),
    "recovered_ate": frozenset({"missing_data_recovery_gformula"}),
    "regression_calibration": frozenset({"regression_calibration"}),
    "selection_recovery_numeric": frozenset({"selection_backdoor_recovery"}),
    "simex": frozenset({"simex"}),
}


def verify_a_block_names_the_method_that_wrote_it(result: dict) -> None:
    """The word against the work it left behind.

    Returns ``None`` on accept, including for an answer with no estimate,
    no method word, or no guarded block -- there is nothing to disagree
    with in any of those. Raises where a guarded block is present and the
    method is not one that writes it.

    The refusal names both sides and neither is assumed to be the forged
    one: a reader who gets this is told the block, the word, and the
    methods that would account for the block, because which of the two
    moved is not something this rule can know.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    method = estimate.get("method")
    if not isinstance(method, str):
        return
    for block in sorted(estimate):
        writers = WRITTEN_BY.get(block)
        if writers is None or method in writers:
            continue
        if estimate.get(block) is None:
            continue
        raise VerificationError(
            f"numeric_estimate.{block} is on this envelope and "
            f"numeric_estimate.method says {method!r}; that block is "
            f"written by {sorted(writers)}, and the rule that re-derives "
            f"it reads nothing unless the method is one of them. Whichever "
            f"of the two was moved, what a reader is shown is a number "
            f"from one estimator labelled as another, with the audit of "
            f"the block switched off",
            rule=_RULE,
        )
