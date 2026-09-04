"""The first word an answer says about itself, against what it is showing.

``status`` is what a reader meets before anything else, and it decides
which audit runs: :func:`themis.verify` dispatches on it, and so does the
estimate half. A field that SELECTS the checks is a premise of the audit
until somebody holds it — the sentence #568 wrote about ``query_kind`` and
``answer_tier``, with this one named in the same breath and left.

Measured before it was written: of 1458 relabellings of the corpus's own
answers, 673 were accepted at both public doors. An answer that came back
``needs_investigation`` could call itself ``numerically_solved``,
``structurally_solved``, ``outside_language`` or ``counterfactual_solved``
and be believed.

What holds it is on the envelope beside it. Each word names a rung the run
reached — nothing, a structure, an interval, a number — and every rung has
a block that shows it. So the audit is in two halves with two authors, and
they have to agree: :data:`themis.types.STATUS_CLAIMS` says what each word
claims, declared beside the word because that is where this package puts
what a name means; this module says what an envelope SHOWS, read off the
blocks by a reader that knows nothing about which word it is checking.

The reading is deliberately coarse. WHERE a number lives is a fact about
the query kind — a joint contrast keeps it under ``joint_effect``, a dose
response under ``dose_response_curve``, causation under
``probabilities_of_causation``, and an Anderson-Rubin region is a number
the estimate blocks have no room for at all — and a status is not a claim
about that. It says whether the run got one. Fifteen honest answers were
refused by a first draft that asked for a POINT where the word only claims
a number, which is what a claim written from four examples looks like.

A second draft wrote that sentence and then read the estimate blocks
anyway, so thirteen honest region answers were refused by the paragraph
above being prose. The blocks a quantity can arrive in are not something
this module gets to guess: ``themis.blocks`` groups them by the reader's
question they answer, and ``Family.ANSWER`` is exactly "the quantity, on
the paths that put it beside the estimate rather than in it".
:data:`_ANSWER_BLOCKS` is that family, restated here for the reason every
table in this package is restated, and pinned to it by a test — so a new
place a number can live arrives as a red suite rather than as an honest
answer this rule refuses.

One envelope is then read TWICE, at two strictnesses, and the reason is
the whole design of this rule. A promise and a denial are wrong in
opposite directions. Reading too little makes a promise refuse an answer
that kept its number somewhere the reading missed; reading too much makes
a denial refuse an answer whose block is present and empty — and a region
that came back unbounded is exactly that, a block whose whole content is
that these data do not constrain the effect. Both refuse an honest answer,
which this rule may never do. So each half is read in the direction that
errs toward accepting: a denial is held only against what the envelope
CERTAINLY shows, and a promise is satisfied by anything the envelope MIGHT
be showing. Same principle, opposite polarity, and nothing in between
needs deciding.

The claims table denies nothing to ``numerically_solved`` or
``counterfactual_solved``, and that is not an omission: a number, an
interval and a structure can all be true of one answer at once, so for
those two words there is nothing on the envelope that contradicts them.
Their content is the positive half, and it is checked.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..types import STATUS_CLAIMS, ResultStatus, Shown
from .errors import VerificationError

_RULE = "answer_status_check"

#: The extension blocks that hold a quantity the estimate fields have no
#: room for. ``themis.blocks.declared_as(Family.ANSWER)``, restated rather
#: than imported: a verifier that reads the producer's own roster agrees
#: with it by construction. A test pins the two together.
_ANSWER_BLOCKS = frozenset({
    "anderson_rubin_region",
    "causation",
    "counterfactual_cell",
    "scm_counterfactual",
})


def _shown(result: Mapping) -> frozenset[Shown]:
    """What this envelope certainly shows, whatever it calls itself.

    Read from the blocks rather than from any field that summarises them,
    for the reason this module exists: a summary is the thing being
    audited. ``bounds_results`` counts as an interval because that is what
    a bound IS to a reader — a range the answer is inside — and it is
    where an answer that could not reach a point keeps what it did reach.

    Certainly: every rung here is a value sitting in a field, not a block
    that would hold one. This is the reading a denial is held against, and
    a denial is the half that must not see what is not there.
    """
    estimate = result.get("numeric_estimate")
    outcome = result.get("numeric_result")
    estimate = estimate if isinstance(estimate, Mapping) else None
    outcome = outcome if isinstance(outcome, Mapping) else None

    out: set[Shown] = set()
    if estimate is not None or outcome is not None:
        out.add(Shown.NUMBER)
    if (estimate is not None and estimate.get("point") is not None) or (
            outcome is not None and outcome.get("value") is not None):
        out.add(Shown.POINT)
    if (estimate is not None and estimate.get("ci_lower") is not None) or (
            outcome is not None and outcome.get("interval") is not None) or (
            result.get("bounds_results")):
        out.add(Shown.INTERVAL)
    if result.get("structural_result") is not None:
        out.add(Shown.STRUCTURE)
    if result.get("derivation") is not None:
        out.add(Shown.CHAIN)
    return frozenset(out)


def _might_be_showing(result: Mapping) -> frozenset[Shown]:
    """That, plus every block a quantity could be sitting inside.

    An answer block counts here and contributes a number and nothing
    finer. What shape the quantity took inside it is that block's own
    business — a region projects an interval per coefficient, a
    counterfactual cell is a point — and reading that far would put this
    function back to enumerating the answers its author had seen.

    This is the reading a promise is satisfied by, so what it costs when
    it is too generous is a lie left standing, and what it would cost if
    it were too strict is an honest answer refused.
    """
    extensions = result.get("extensions")
    extensions = extensions if isinstance(extensions, Mapping) else {}
    if _ANSWER_BLOCKS & extensions.keys():
        return _shown(result) | {Shown.NUMBER}
    return _shown(result)


#: How each rung is said in the refusal, so the sentence names what a
#: reader would have been looking at rather than an enum member.
_AS_WRITTEN: dict[Shown, str] = {
    Shown.POINT: "a point estimate",
    Shown.INTERVAL: "an interval",
    Shown.NUMBER: "a number",
    Shown.STRUCTURE: "a structural result",
    Shown.CHAIN: "a reasoning chain",
}


def _named(rungs) -> str:
    return ", ".join(_AS_WRITTEN[r] for r in sorted(rungs))


def verify_answer_status(result: Mapping) -> None:
    """Hold the word an answer leads with to what the answer is showing.

    A status this build does not carry is passed over: the schema's enum
    is where membership is asked, and a rule that answered it here would
    be a second, weaker enum check standing in front of the real one.
    """
    word = result.get("status")
    if not isinstance(word, str) or word not in set(ResultStatus):
        return
    status = ResultStatus(word)
    claim = STATUS_CLAIMS[status]
    said, shown = str(status), _shown(result)
    might = _might_be_showing(result)

    for wanted in claim.carries:
        if wanted & might:
            continue
        raise VerificationError(
            f"the answer says it is {said!r} and shows "
            f"{_named(might) or 'none of the things a status is about'}; "
            f"a reader is told that word before anything else, and it "
            f"claims {_named(wanted)}",
            rule=_RULE,
        )
    if denied := (claim.withholds & shown):
        raise VerificationError(
            f"the answer says it is {said!r} and shows {_named(denied)}; "
            f"that word says the run did not get there, so a reader who "
            f"reads it stops looking at what is sitting beside it",
            rule=_RULE,
        )
