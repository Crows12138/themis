"""The first word an answer says about itself, against what can hold it.

Four things can. What the envelope is SHOWING, which is most of this
module; what the question ASKED, which separates two words that show the
same; where a question has more than one road to an answer, which ROAD
this one came by; and what the VERDICT beside it SAYS, where the answer
carries one. None subsumes another: an answer showing nothing cannot be
any of the solved words whatever was asked; an effect query's answer
cannot be a counterfactual point however many numbers are beside it; a
question about two worlds is answered either by computing from the model
the program declares or by estimating from data, where the word says
which and the envelope shows which; and a word that says the run has an
errand left is open to an answer whose structural question is still open,
not to one whose slot beside it says it is settled.


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
:data:`_THE_QUANTITY_IN` is that family, restated here for the reason
every table in this package is restated, and pinned to it by a test — so
a new place a number can live arrives as a red suite rather than as an
honest answer this rule refuses.

That roster was the names alone, and the reading under it was the KEY: a
block of the family is on the envelope, so a quantity might be. A key is
an address. Whether a number is at it is inside the block, and each of
these says so — a confidence region records whether it closed,
probabilities of causation record the point beside the bounds that stand
in where there is none. Two of the words differ over exactly that, and to
a reading of the key the two envelopes are one: a run that reached only
bounds could call itself solved, and a run that reached a region could
call itself needing investigation. So the family declares WHERE its
quantity arrives, this roster carries that column, and the reading moves
from the generous half to the certain one — a block is no longer a place a
number might be, it is a place that says.

One envelope is then read TWICE, at two strictnesses, and the reason is
the whole design of this rule. A promise and a denial are wrong in
opposite directions. Reading too little makes a promise refuse an answer
that kept its number somewhere the reading missed; reading too much makes
a denial refuse an answer whose block is present and holds nothing — and a
region that came back unbounded was exactly that, a block whose whole
content is that these data do not constrain the effect. Both refuse an
honest answer, which this rule may never do. So each half is read in the
direction that errs toward accepting: a denial is held only against what
the envelope CERTAINLY shows, and a promise is satisfied by anything the
envelope MIGHT be showing. Same principle, opposite polarity, and nothing
in between needs deciding.

What is left in the generous half is the ask, and that is the whole of it.
The unbounded region was the reason a block could not be read for a
denial, and the block answers it now, so where a quantity is stopped being
a guess and became the certain reading above.

The claims table denies nothing to ``numerically_solved`` or
``counterfactual_solved``, and that is not an omission: a number, an
interval and a structure can all be true of one answer at once, so for
those two words there is nothing on the envelope that contradicts them.
Their content is the positive half, and it is checked.

The rungs above are all one axis — how far the run got — and the two words
that say it did not get there are not claims on that axis. They are claims
about what is to be done instead, and until ``Shown`` had a member for it
neither could be held to anything: ``outside_language`` denied every rung
and so denied nothing an unfinished answer actually carries, and
``needs_investigation`` promised nothing whatever. An answer carrying a
settled structure and the chain that reached it could lead with the second
while naming no errand at all, and one naming a page of errands could lead
with the first. Both halves come out of the vocabulary gaining
:attr:`~themis.types.Shown.ASK` and neither needed a rule of its own.

The two readings differ over it, and here the generous one is generous for
a stated reason rather than by accident. A denial is held against what is
certainly there, which for an ask is the caller's side of the envelope:
the requests and the missing items, both fields whose whole content is
what somebody has to go and get. A promise is satisfied by anything that
might be one, and a recorded refusal is — :class:`themis.refusals.Kind` is
in its own words "what the reader should do about a refusal", so an
envelope carrying one has told the reader what to do even where no ask was
written out. The cost is declared: five stored answers identify cleanly and
then refuse at the estimator for want of data, and this rule does not stop
them calling that needing investigation, because on those five it would
not be a lie.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..types import STATUS_CLAIMS, MissingKind, ResultStatus, Shown
from .errors import VerificationError

_RULE = "answer_status_check"

#: A name of its own rather than a second use of the one above: the
#: rules refuse for different reasons — one because the envelope
#: contradicts the word, one because the question does, one because the
#: road the answer came by does — and a reader given one name for them
#: has to open the sentence to learn which.
_RULE_QUESTION = "answer_status_question_check"
_RULE_ROAD = "answer_status_road_check"

#: Where each block that holds a quantity the estimate fields have no room
#: for puts it. ``themis.blocks``' own ``arrives_at``, restated rather than
#: imported: a verifier that reads the producer's own roster agrees with it
#: by construction. A test pins the two together, this column included.
#:
#: Read for the value and not for the key, which is the difference between
#: a block that could be holding a number and one that is. The same
#: question the tier channel in :mod:`themis.verifier.data_gap_rules` asks
#: when it declines to call an open region an interval — asked here for the
#: other reader, and out of the declaration rather than inline, because
#: each block has its own way of saying it and a reader that spells one of
#: them knows about one block.
_THE_QUANTITY_IN: dict[str, tuple[tuple[str, ...], ...]] = {
    "anderson_rubin_region": (("region", "point"),),
    "causation": (("pn", "point"), ("ps", "point"), ("pns", "point")),
    "counterfactual_cell": (("point",),),
    "scm_counterfactual": (("target_value",),),
}


def _a_quantity_arrived_in(
    block: Mapping, slots: tuple[tuple[str, ...], ...],
) -> bool:
    """Whether any of one block's declared slots holds a value.

    Any, because a block may carry a quantity per estimand — three
    probabilities of causation are identified or bounded one at a time —
    and reaching one of them is reaching a quantity. ``None`` is the
    block's own word for "not this one": the slot is written on every
    answer of that shape and filled on the ones that got there.
    """
    for path in slots:
        node: object = block
        for step in path:
            if not isinstance(node, Mapping):
                node = None
                break
            node = node.get(step)
        if node is not None:
            return True
    return False


def _shown(result: Mapping) -> frozenset[Shown]:
    """What this envelope certainly shows, whatever it calls itself.

    Read from the blocks rather than from any field that summarises them,
    for the reason this module exists: a summary is the thing being
    audited. ``bounds_results`` counts as an interval because that is what
    a bound IS to a reader — a range the answer is inside — and it is
    where an answer that could not reach a point keeps what it did reach.
    Which is also why the rung it raises is no evidence that one arrived,
    and why the claims table asks the two words saying the run got there
    for a number rather than for any of the three
    (:data:`themis.types.A_QUANTITY`).

    Certainly: every rung here is a value sitting in a field, and the two
    places a quantity can sit are asked for the value rather than for
    themselves. A headline result has a point slot and a range slot and it
    says which one it filled; a block of the ANSWER family says the same
    thing at the slot :data:`_THE_QUANTITY_IN` names. Reading either one's
    presence tells a reader a number arrived on every envelope that wrote
    down that none did, which is the one thing two of the words differ
    over.

    The estimate field is the exception and is read for its presence,
    because there the presence IS the reading that is total: it is where an
    estimator that ran puts what it got, under whichever key its own shape
    decides, and no list of those keys is total over the shapes to come.

    This is the reading a denial is held against, and a denial is the half
    that must not see what is not there.
    """
    estimate = result.get("numeric_estimate")
    outcome = result.get("numeric_result")
    estimate = estimate if isinstance(estimate, Mapping) else None
    outcome = outcome if isinstance(outcome, Mapping) else None
    extensions = result.get("extensions")
    extensions = extensions if isinstance(extensions, Mapping) else {}

    out: set[Shown] = set()
    if estimate is not None or (
            outcome is not None and outcome.get("value") is not None):
        out.add(Shown.NUMBER)
    for name, slots in _THE_QUANTITY_IN.items():
        block = extensions.get(name)
        if isinstance(block, Mapping) and _a_quantity_arrived_in(block, slots):
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
    if result.get("investigation_requests") or result.get(
            "missing_information"):
        out.add(Shown.ASK)
    return frozenset(out)


def _might_be_showing(result: Mapping) -> frozenset[Shown]:
    """That, plus the refusal that is an ask with none written out.

    :class:`themis.refusals.Kind` is, in its own words, what the reader
    should do about a refusal — the graph has to change, or the data, or
    what was sent — so an envelope carrying one has said what is to be
    done whether or not an ask was also written out. Five stored answers
    are the difference: they identify, then refuse at the estimator for
    want of data, and calling that needing investigation is not a lie.

    The answer blocks were the other half of this and are not any more.
    "A block a quantity could be sitting inside" was a guess this function
    had to make, because the alternative was a list of keys that could
    only ever be the answers its author had seen. The family declares the
    slot now, so what a block shows is certain and is read above. What
    stays here is the one thing still inferred rather than read.

    This is the reading a promise is satisfied by, so what it costs when
    it is too generous is a lie left standing, and what it would cost if
    it were too strict is an honest answer refused.
    """
    out = set(_shown(result))
    if result.get("estimator_failure") is not None:
        out.add(Shown.ASK)
    return frozenset(out)


#: How each rung is said in the refusal, so the sentence names what a
#: reader would have been looking at rather than an enum member.
_AS_WRITTEN: dict[Shown, str] = {
    Shown.POINT: "a point estimate",
    Shown.INTERVAL: "an interval",
    Shown.NUMBER: "a number",
    Shown.STRUCTURE: "a structural result",
    Shown.CHAIN: "a reasoning chain",
    Shown.ASK: "something for the reader to go and find out",
}


def _named(rungs) -> str:
    return ", ".join(_AS_WRITTEN[r] for r in sorted(rungs))


#: The words a refusal leaves, and so the words open to every question.
#:
#: A refusal is about what this system could not do, not about what was
#: asked, so nothing about the question narrows them. Restated from
#: ``themis.refusals.Kind.outcome`` and pinned to it by a test, for the
#: reason every table in this package is restated.
_REFUSAL_WORDS = frozenset({"needs_investigation", "outside_language"})

#: Which words each question's ANSWER can lead with.
#:
#: ``themis.questions``' own ``answers_with``, restated and pinned. A word
#: absent from every roster is absent from this table too and is refused
#: everywhere, which is the honest reading of a status no producer emits:
#: the day one does, the question it is emitted for gains an entry.
_ANSWERS_WITH: dict[str, frozenset[str]] = {
    "cause": frozenset({"structurally_solved"}),
    "assoc": frozenset({"structurally_solved"}),
    "identify": frozenset({"structurally_solved"}),
    "effect": frozenset({"numerically_solved", "structurally_solved"}),
    "probability": frozenset({"numerically_solved"}),
    "counterfactual": frozenset({"counterfactual_bounded",
                                 "counterfactual_solved",
                                 "numerically_solved"}),
    "causation": frozenset({"counterfactual_bounded",
                            "counterfactual_solved",
                            "numerically_solved"}),
    "scm_counterfactual": frozenset({"counterfactual_solved",
                                     "numerically_solved"}),
    "counterfactual_conjunction": frozenset({"numerically_solved",
                                             "structurally_solved"}),
    "proximal_effect": frozenset({"numerically_solved",
                                  "structurally_solved"}),
}

#: The questions whose quantity is defined over more than one world.
#:
#: ``themis.questions``' own ``asks_across_worlds``, restated and pinned
#: for the reason the roster above is. A question that gains the property
#: and not an entry here leaves this rule silent on its answers, which is
#: a rule that stops refusing rather than one that starts refusing wrongly
#: — and the test pins the table in both directions anyway.
_ACROSS_WORLDS: frozenset[str] = frozenset({
    "causation",
    "counterfactual",
    "counterfactual_conjunction",
    "scm_counterfactual",
})

#: The word the estimating road ends in, and the one word an across-world
#: question shares with the questions that ask about a single world. Named
#: rather than written into the sentence below, because which word it is is
#: a fact about the roster above.
_THE_ESTIMATORS_WORD = "numerically_solved"


def verify_answer_status_fits_its_question(result: Mapping) -> None:
    """Hold the word an answer leads with to the question it answers.

    The rule above asks what the envelope shows, and there it stops: two
    words that both say a quantity arrived show the same thing, so nothing
    beside them tells one from the other. What tells them apart is the
    question. An effect query asks for an interventional contrast and a
    counterfactual point is not a sharper answer to it — it is an answer
    to something else, and a reader who takes the word at face value has
    been told the run answered a question nobody asked.

    Safe to read ``query_kind`` here, and only because it is held:
    ``verify_answer_names_its_kind`` puts it against the program, which an
    answer may not edit. Reading an unheld field would make this rule an
    argument between two things the same author wrote.

    A roster keyed on the question is only as fine as the question is.
    Where a question has one road to an answer, naming the question names
    the road; where it has two, the roster can do nothing but list both
    words, which is no hold at all on whichever family took the commoner
    road. Four questions are about more than one world, and a number for
    one of them arrives either from data, estimated, or from the structural
    model the program itself declares, computed. The estimating road ends
    in ``numerically_solved`` and the computing road in the counterfactual
    words, so on those four questions the estimator's word is asked for the
    estimate that earns it.

    The estimate block is the witness and the estimation context beside it
    is not, though the context is the broader mark of an estimator having
    run. Same sentence as above: what a rule leans on has to be held by
    somebody other than the author of the answer, and the context is the
    block whose own leaves this repository's sweep still lists as unheld.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    word, kind = result.get("status"), result.get("query_kind")
    if not isinstance(word, str) or word in _REFUSAL_WORDS:
        return
    if not isinstance(kind, str) or (allowed := _ANSWERS_WITH.get(kind)) is None:
        return
    if word not in allowed:
        raise VerificationError(
            f"the answer says it is {word!r} and the question asked was "
            f"{kind!r}, whose answer says one of {sorted(allowed)}; a reader "
            f"is told that word before anything else, and it says the run "
            f"answered a question that was not put to it",
            rule=_RULE_QUESTION,
        )
    if (kind in _ACROSS_WORLDS and word == _THE_ESTIMATORS_WORD
            and not result.get("numeric_estimate")):
        raise VerificationError(
            f"the answer says it is {word!r} and the question asked was "
            f"{kind!r}, which is about more than one world; a number for "
            f"such a question comes either from data, estimated, or from "
            f"the structural model this program declares, computed, and "
            f"that word is the estimating road's. No estimate is on this "
            f"envelope, so a reader is told the number came from data when "
            f"it came from what the program itself declares",
            rule=_RULE_ROAD,
        )


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


#: A third name, for the third reason a word can be wrong beside what it
#: stands next to.
_RULE_ERRAND = "answer_status_errand_check"

#: The rung an errand asks for, where it asks for one.
#:
#: Two closed vocabularies meet here and neither is about the other.
#: :class:`themis.types.Shown` says how far a run got;
#: :class:`themis.types.MissingKind` says what it needed and did not have.
#: Exactly one kind names a rung: an answer asking for STRUCTURE is asking
#: for the thing ``structurally_solved`` promises, and the two sentences
#: are then a contradiction a reader has to resolve by guessing which one
#: to believe.
#:
#: Written as a join rather than as another column of ``STATUS_CLAIMS``,
#: for the reason ``QUERY_KIND_OF`` gives about itself: the two sets are
#: declared and the join belongs beside them rather than inside either.
#: What follows from it is read OFF ``STATUS_CLAIMS`` and names no word,
#: so a status added later that promises a structural result is covered
#: without being mentioned.
_THE_RUNG_AN_ERRAND_ASKS_FOR: dict[str, Shown] = {
    str(MissingKind.STRUCTURE): Shown.STRUCTURE,
}

#: And the kinds that ask for an INPUT or a PREMISE, neither of which is a
#: rung. Named rather than left as the absence of the five above, so that
#: a seventh kind has to be classified instead of joining nothing quietly
#: — the shape ``_every_status_says_what_it_claims`` uses on the table
#: this one reads.
_ASKS_FOR_NO_RUNG: frozenset[str] = frozenset({
    str(MissingKind.PARAMETER), str(MissingKind.OBSERVATION),
    str(MissingKind.SAMPLE), str(MissingKind.ASSUMPTION),
    str(MissingKind.FRAMING),
})


def verify_no_status_promises_a_rung_an_errand_asks_for(
    result: Mapping,
) -> None:
    """The word an answer leads with, against what it is asking for.

    The rule above reads what the envelope SHOWS, and deliberately coarsely
    — where a number lives is the query kind's fact and a status is not a
    claim about that. That coarseness is why ``ASK`` says only that there
    is an errand: a promise may only be read off a total reading, and
    "some errand is written here" is total where "an errand of this shape"
    would be a list of the ones its author had seen.

    The errand's own ``kind`` is not that. It is a closed vocabulary
    declared beside the rungs, so asking which rung an errand is for is
    reading a second declaration rather than guessing at a shape. Two
    stored answers are what it costs not to: they settle nothing
    structurally, ask for structure, and could lead with the word that
    says the structural question was answered.

    Not the same complaint as a word that withholds a rung the envelope
    shows. That one is about a run having got somewhere its word denies.
    This is about a word promising the very thing the answer is sending
    the reader away to go and get, which is a contradiction in one
    direction only: an answer may be structurally solved and still ask for
    the DATA to evaluate it, and thirteen stored answers are.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    word = result.get("status")
    if not isinstance(word, str) or word not in set(ResultStatus):
        return
    promised: set[Shown] = set()
    for wanted in STATUS_CLAIMS[ResultStatus(word)].carries:
        promised |= set(wanted)
    if not promised:
        return
    for item in result.get("missing_information") or ():
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        rung = (_THE_RUNG_AN_ERRAND_ASKS_FOR.get(kind)
                if isinstance(kind, str) else None)
        if rung is None or rung not in promised:
            continue
        raise VerificationError(
            f"the answer says it is {word!r}, which claims {_AS_WRITTEN[rung]}, "
            f"and asks the reader for {_AS_WRITTEN[rung]}; a reader is told "
            f"that word before anything else, and an answer cannot both have "
            f"reached a thing and be sending somebody to go and get it",
            rule=_RULE_ERRAND,
        )


#: A fourth name, for the word that stands beside a verdict instead of
#: being about it.
_RULE_VERDICT = "answer_status_verdict_check"


def verify_no_refusing_word_stands_beside_a_settled_verdict(
    result: Mapping,
) -> None:
    """The word an answer leads with, against the verdict beside it.

    :class:`themis.refusals.Kind` gives each kind the status a result
    takes "when this refusal is all the result contains", and says in the
    same breath what a result carrying more than that does: one that also
    carries an identification answer has a status about THAT — the data
    end's refusals ride results whose status says the structural question
    was answered, or that a gap in it remains. So the two words a refusal
    leaves are open to an answer carrying a verdict on the second of those
    readings only. Where the verdict is that there is no gap, a reader is
    sent away to go and find something out, past the slot beside it saying
    the structural question is done.

    Not the first rule of this module with the verdict added. That one
    reads what the envelope SHOWS and reads a verdict for its PRESENCE,
    because a denial held against a short reading cannot invent a lie, and
    a verdict of either polarity is a verdict shown. What is read here is
    what the verdict SAYS, which is the one fact about it that tells the
    answer whose structural question is settled from the answer whose
    remaining gap IS the structural one — and the two stored answers that
    lead with a refusing word beside a verdict are the second kind.

    Safe to read the verdict, and only because it is held:
    :func:`themis.verifier.verdict_rules.verify_structural_verdict` puts
    it against the three places one answer commits to identification, none
    of which needs a route. A forgery that flips the verdict AND this word
    is refused there wherever one of those three is written, and where
    none is, it is a forgery neither rule can see.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    word = result.get("status")
    if not isinstance(word, str) or word not in _REFUSAL_WORDS:
        return
    verdict = result.get("structural_result")
    if not isinstance(verdict, Mapping) or verdict.get("value") is not True:
        return
    raise VerificationError(
        f"the answer leads with {word!r} and the structural verdict beside "
        f"it says the proposition its question names holds; that word is "
        f"what a result takes when a refusal is the whole of it, and this "
        f"one carries the structural answer as well, so a reader is told "
        f"there is a structural question still to settle while the slot "
        f"under the word says it is settled",
        rule=_RULE_VERDICT,
    )
