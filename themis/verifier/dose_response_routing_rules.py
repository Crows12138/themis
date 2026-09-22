"""Where a dose-response request went, held to the program it went in.

A ``dose_response_query`` names the curve to draw and not the query to draw
it for, so the estimation layer picks one -- and where the pick was not the
obvious one it says so, in a statement on
``estimation_context.data_contract_warnings``. Five of that vocabulary's six
members are propositions about the PROGRAM: that it holds no effect query at
all, that every effect query it holds names a mediator, that an id it was
handed matches nothing, that the id it was handed names a mediation, and
that the first effect query was passed over for the first eligible one.

Nothing had read any of them. The SHAPE of each statement was held --
:mod:`themis.verifier.statement_rules` asks whether a token saying
``the_query_id_matches_nothing`` carries the id it is about -- and the shape
is the same whichever of these the producer says. So the two members that
share a hole are interchangeable: a run that skipped the curve because the
id it was handed pointed at a mediation could say instead that the id
matched nothing, and the reader would go hunting for a typo in a name that
is spelt right, in a program where the query it names is sitting.

Four of the five stop the estimator, so what the reader is told is why
there is no curve. A wrong one of those is not a wrong footnote beside an
answer; it is the whole of the answer to the question that was asked.

WHAT IS NOT RE-DERIVED. The routing PLAN. Which query a request resolves to
where several are eligible is a decision, and a second author for a
decision is two decisions that will disagree the first time either moves.
What is asked here is only whether what a statement says about the program
is so, which is a different question and the one a reader of the statement
is relying on. So this rule never says a warning is missing, and never says
which query the curve should have gone to.

THE SIXTH MEMBER is not about the program. ``the_treatment_is_binary`` is a
fact about a COLUMN, and no door here holds the data. Its subject is held --
that the name it calls the treatment is a treatment some query in this
program intervenes on -- and its predicate is not, and says so here rather
than passing as checked. It is also the one member written into two slots,
by three lines that write both or neither, and its producer's own docstring
calls that identity the point: "The two used to be two sentences saying the
same thing ... Now the identity is the statement."

That the WRITER writes both is already held, at the writer: a test walks
every assignment to ``estimator_fallback`` in the package, finds the one
site, and requires the warning to be appended beside it in the same
unbranched body. What is held here is a different claim about a different
object. That one says this build cannot produce an envelope with one slot
filled; this one says an envelope in hand does not have two slots that
disagree -- and an envelope is a document anyone can write, which is the
whole reason there is a verifier as well as a test suite. The contract
itself had already stated the identity, in the block's own description,
where it says the reason is "the SAME statement the data_contract_warnings
entry beside it carries, not a second sentence about the same fact". It
had been a description of an intention.

The block's other two fields say which estimator a reader is being shown
instead, and they are held as the constant pair they are -- see
:data:`THE_ONE_SUBSTITUTION`, which also records what is wrong with the
second of them and why it is not fixed here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NoReturn

from .errors import VerificationError

_RULE = "dose_response_routing_check"

#: The vocabulary this rule reads. Statements in any other vocabulary sit in
#: the same list and are about the data rather than the routing.
VOCABULARY = "dose_response_routing"

#: The request whose resolution these statements record.
_REQUEST = "dose_response_query"

#: The member that is about a column rather than about the program, and the
#: slot the producer writes it into a second time.
_BINARY = "the_treatment_is_binary"
_FALLBACK = "estimator_fallback"

#: The one substitution this build performs, as that block spells it.
#:
#: Restated rather than derived. There is a single site that writes the
#: block, and the test standing at that site asserts there is a single one,
#: so a second substitution fails THERE first and arrives here with a
#: pointer rather than as a puzzle. That is what makes a restatement
#: affordable here: its premise is already somebody's assertion.
#:
#: The two halves are not alike, and the difference is recorded rather than
#: fixed. ``from`` is a member of ``themis.estimation.strategy.Estimand``,
#: the vocabulary saying what a strategy's number is an estimate OF.
#: ``to`` is a word nothing in this build declares; the nearest true
#: Estimand for what answered instead is ``query_effect``. Making it one
#: changes what the envelope carries, and the stored answers would have to
#: be collected again for it to take effect, so it is written down here.
THE_ONE_SUBSTITUTION = ("dose_response", "binary_effect")


def _rows(value) -> list:
    """``value`` as a list of mappings, or empty where it is not a list."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _requests(program: Mapping) -> list:
    """The dose-response requests the program makes."""
    extensions = program.get("extensions")
    if not isinstance(extensions, Mapping):
        return []
    return [a for a in _rows(extensions.get("ambiguities"))
            if a.get("kind") == _REQUEST]


def _effect_queries(program: Mapping) -> list[tuple[str, bool, object]]:
    """(id, whether it names a mediator, what it intervenes on), in order.

    In order, because two of the members below are about which effect query
    comes FIRST and a set would answer a different question.
    """
    out: list[tuple[str, bool, object]] = []
    for statement in _rows(program.get("statements")):
        if statement.get("kind") != "query":
            continue
        query = statement.get("query")
        if not isinstance(query, Mapping) or query.get("kind") != "effect":
            continue
        name = statement.get("id")
        if not isinstance(name, str):
            continue
        intervention = query.get("intervention")
        atom = (intervention.get("atom")
                if isinstance(intervention, Mapping) else None)
        on = atom.get("predicate") if isinstance(atom, Mapping) else None
        out.append((name, query.get("mediator") is not None, on))
    return out


def verify_where_a_dose_response_request_went(
    result: object, program: object,
) -> None:
    """Each routing statement's proposition, asked of the program.

    Returns ``None`` on accept, including for an answer carrying no such
    statement. Raises :class:`~themis.verifier.errors.VerificationError`
    where a statement says something about the program that the program
    does not bear out, or where the one member written twice is not the
    same statement in both slots.
    """
    if not isinstance(result, Mapping) or not isinstance(program, Mapping):
        return
    context = result.get("estimation_context")
    context = context if isinstance(context, Mapping) else {}
    said = [s for s in _rows(context.get("data_contract_warnings"))
            if s.get("vocabulary") == VOCABULARY]

    fallback = result.get(_FALLBACK)
    fallback = fallback if isinstance(fallback, Mapping) else None
    reason = fallback.get("reason") if fallback else None
    reason = reason if isinstance(reason, Mapping) else None

    def _refuse(why: str) -> NoReturn:
        raise VerificationError(why, rule=_RULE)

    if fallback is not None:
        went = (fallback.get("from"), fallback.get("to"))
        if went != THE_ONE_SUBSTITUTION:
            _refuse(
                f"{_FALLBACK} says the run went from {went[0]!r} to "
                f"{went[1]!r}; the one substitution this build performs is "
                f"{THE_ONE_SUBSTITUTION[0]!r} to "
                f"{THE_ONE_SUBSTITUTION[1]!r}. Both words say which "
                f"estimator a reader is actually being shown, and a reader "
                f"who is told the wrong one has no other field to notice it "
                f"against")
        # And the reason, which is not a second sentence about the same
        # fact. The contract says so in its own description; until now
        # nothing had asked whether the two slots still agree.
        if reason is None or not any(s == reason for s in said):
            _refuse(
                f"{_FALLBACK} gives a reason that "
                f"estimation_context.data_contract_warnings carries no "
                f"statement equal to. The producer writes one statement "
                f"into both slots in three lines that write both or "
                f"neither, so a reader who reads either is reading the "
                f"other; two that differ mean one of them was edited")
        # WHICH statement it is, and not merely that it is one of them.
        # This build leaves the curve for one reason -- the column it was
        # asked to draw one over takes two values -- and the single site
        # that writes this block writes that note with it. So naming the
        # note here costs nothing and refuses a fallback that blames a
        # different note for a substitution that note does not explain.
        # Asked OF the token rather than gated ON it: a producer moving
        # the word off this one is the thing being looked for, and a
        # check that only runs when the word is already right would be
        # looking away at exactly that moment.
        if reason.get("token") != _BINARY:
            _refuse(
                f"{_FALLBACK} gives as its reason the statement "
                f"{reason.get('token')!r}. This build substitutes "
                f"{THE_ONE_SUBSTITUTION[1]!r} for one reason, {_BINARY!r}, "
                f"and a reader told the curve was dropped for some other "
                f"reason is being told about a fallback that does not "
                f"happen here")
    if not said:
        return

    requests = _requests(program)
    if not requests:
        _refuse(
            f"the answer carries {len(said)} statement(s) about where a "
            f"dose-response request went and the program makes no such "
            f"request; each is an account of a decision never taken")

    queries = _effect_queries(program)
    ids = [name for name, _mediates, _on in queries]
    # Keyed on ``object`` rather than ``str``: what gets looked up here is a
    # name read off the other document, and a document may spell one any way
    # it likes. A lookup that has to be narrowed before it is made is a
    # lookup that answers a question about the narrowing.
    mediates: dict[object, bool] = {name: m for name, m, _on in queries}
    eligible = [name for name, m, _on in queries if not m]
    intervened_on = {on for _name, _m, on in queries if isinstance(on, str)}
    # Only the requests that name one. A request that names no id is not a
    # request for an id spelt ``None``, and reading it as one lets a
    # statement with no ``named`` at all match it.
    asked_for = [r.get("query_id") for r in requests
                 if isinstance(r.get("query_id"), str)]

    for statement in said:
        token = statement.get("token")
        facts = statement.get("said")
        facts = facts if isinstance(facts, Mapping) else {}
        opens = f"the answer says {token!r}, and"

        if token == "no_effect_query_to_attach_to":
            if ids:
                _refuse(
                    f"{opens} the program holds {len(ids)} effect "
                    f"query(s), {ids}. The curve is reported skipped for "
                    f"want of anywhere to attach it, and there was "
                    f"somewhere")

        elif token == "every_effect_query_is_a_mediation":
            if not ids:
                _refuse(
                    f"{opens} the program holds no effect query at all, "
                    f"which this vocabulary has its own word for; a reader "
                    f"told every query names a mediator is told there are "
                    f"queries")
            elif eligible:
                _refuse(
                    f"{opens} the effect query {eligible[0]!r} names no "
                    f"mediator. A curve could have been drawn for it")

        elif token in ("the_query_id_matches_nothing",
                       "the_query_id_names_a_mediation"):
            named = facts.get("named")
            if not isinstance(named, str) or named not in asked_for:
                _refuse(
                    f"{opens} it is about the id {named!r}, which no "
                    f"dose-response request in the program asks for; the "
                    f"ids they ask for are {asked_for}")
            if token == "the_query_id_matches_nothing":
                if named in ids:
                    _refuse(
                        f"{opens} {named!r} is an effect query of this "
                        f"program. A reader is sent looking for a "
                        f"misspelling in a name that is spelt right")
            elif named not in ids:
                _refuse(
                    f"{opens} no effect query of this program is called "
                    f"{named!r}; the ones there are, are {ids}")
            elif not mediates[named]:
                _refuse(
                    f"{opens} the effect query {named!r} names no "
                    f"mediator. That is the one thing about it that would "
                    f"have stopped the curve")

        elif token == "no_query_id_so_the_first_eligible_won":
            if all(r.get("query_id") is not None for r in requests):
                _refuse(
                    f"{opens} every dose-response request in the program "
                    f"names an id, so nothing was chosen for want of one")
            first = ids[0] if ids else None
            first_eligible = eligible[0] if eligible else None
            passed_over = facts.get("passed_over")
            chosen = facts.get("chosen")
            if passed_over != first:
                _refuse(
                    f"{opens} it says {passed_over!r} was passed over; the "
                    f"effect query that comes first in this program is "
                    f"{first!r}")
            if chosen != first_eligible:
                _refuse(
                    f"{opens} it says the curve went to {chosen!r}; the "
                    f"first effect query naming no mediator is "
                    f"{first_eligible!r}")
            if not mediates.get(passed_over, False):
                _refuse(
                    f"{opens} the query {passed_over!r} it says was passed "
                    f"over names no mediator, so nothing passed it over")

        elif token == _BINARY:
            treatment = facts.get("treatment")
            if treatment not in intervened_on:
                _refuse(
                    f"{opens} it calls {treatment!r} the treatment; no "
                    f"effect query of this program intervenes on that. The "
                    f"ones intervened on are {sorted(intervened_on)}. "
                    f"Whether the column is binary is a fact about the "
                    f"data and is not asked here")
            if fallback is None or reason != statement:
                _refuse(
                    f"{opens} {_FALLBACK} does not carry that same "
                    f"statement as the reason it fell back from the curve. "
                    f"One statement goes into both slots, so two readers "
                    f"reading different slots are entitled to read one "
                    f"thing")
