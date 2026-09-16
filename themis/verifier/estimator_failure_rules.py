"""The block that stands where a number would have been.

An answer that could not produce a number says why in one shape, and that
shape is assembled by one function: :func:`themis.refusals.block`. It is
the most-read block this system emits — every ``needs_investigation``
answer IS this block — and, measured across the answer shapes, 273 of its
leaves could be rewritten and both public doors said yes.

The rules beside it read the block without holding it. The statement
carrier asks whether the SLOTS of a refusal's sentence match the holes its
species declares, which is a fact about the template. The status rules ask
what the answer's leading word claims, and a refusal's outcome is read off
its ``kind`` rather than compared with it. So which species refused, what
it said about the occasion, and what a reader is told to do about it were
all standing on the producer's word.

WHAT MAKES THIS BLOCK HOLDABLE is that its producer already declares every
relation in it, and this module restates none of them:

The KIND is the species'. :func:`themis.refusals.stamp` writes it at the
exit from the registry, because no raise site knows anything about the
kind the species does not already say. So the field is a function of
``failure_type`` and the registry is where that function lives.

The SENTENCE'S FACTS are the occasion's. ``block`` builds ``details`` and
``said``/``words`` from ONE mapping — ``details`` is every fact as the
envelope can hold it, and :func:`themis.language.halve` splits the same
facts into the ones that render alike in every language and the ones whose
text IS the language. Two halves of one mapping have the same keys as the
mapping, and a key on one side and not the other is a fact added to the
sentence or dropped out of it.

Each FACT IS ITS OWN SECOND RENDERING. ``details[k]`` and ``said[k]``
come from one value by two functions, so the second is recomputable from
the first. Nothing here re-implements either: the rendering is imported
from where the producer calls it.

There is one value for which those two functions do not agree, and this
rule refuses it rather than allowing for it. A SET is ordered on its way
onto the envelope and is not ordered on its way into the sentence, so a
reader is handed Python's own set syntax in an ordering that depends on
the hash seed — text no second run reproduces, this rule included, and no
translation can carry. Refusing there reports that rather than failing to
allow for it: what cannot be reproduced by its own producer is not a fact
two records can be said to agree about. Nothing passes a set today.

Each ROUTE is one this build declares, and whether it names something is
the route's to decide rather than the raise site's — an invariant
:func:`themis.refusals._routes` states and enforces where the refusal is
raised, which is exactly the point at which an envelope edited afterwards
has already gone by.

TWO SILENCES, AND NEITHER IS THIS MODULE'S JUDGEMENT. Both producers say
which way to read an unknown token, and they say opposite things. An
unregistered SPECIES is accepted: ``stamp`` closes what this build emits
and deliberately does not close what it reads, because refusing there
would reject somebody else's honest refusal. An unregistered ROUTE is
refused: :func:`themis.refusals.route` says a route this build has never
heard of is one it cannot describe, and a bare token in a reader's
sentence is worse than the field being absent.

WHAT STAYS OPEN, measured rather than deferred. The ``estimator`` is 36 of
the 273 and has no second record anywhere — 31 of its 36 appear nowhere
else on the envelope, and these answers carry no estimate and often no
chain for one to appear in. Nor is there a roster: it is written as a
string literal at some forty raise sites, and the contract types it
``string`` where it gives ``failure_type`` a full enum. Holding it would
mean this package restating those forty literals, which is the table a
verifier must not become — and the honest frontier there is the one
``failure_type`` already had, a name declared once rather than spelled at
each site. ``recorded`` stays open for a reason its own producer states:
it is the occasion's half that was measured and NOT said, so there is no
second rendering of it to compare with. Nor a second record: what it
holds is what the estimator measured, and a verdict another layer reached
stays on that layer's block, where it is held.

WHICH route a refusal offers is open for the same reason, and the reason
is the route's whole point. A species is raised at several sites and the
way past it differs by site, so no per-species answer can carry it and the
registry does not try to: what is declared about a route is its sentence
and whether it names something, and both are held here. Which of them this
occasion offers is the raise site's, and it appears nowhere else on the
envelope. Measured: of 45 swaps between declared routes, 28 are accepted —
every one that keeps the arity. A rule wanting more would need the route
declared per species, which is the arrangement this one exists to replace.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NoReturn

from .. import language, refusals
from .errors import VerificationError

_RULE = "refusal_block_check"


def _reject(says: str) -> NoReturn:
    raise VerificationError(says, step_index=None, rule=_RULE)


def _half(failure: Mapping, name: str) -> Mapping:
    """One part of the block, or an empty one.

    An absent part and an empty part are the same thing here, which is the
    rule the assembler follows on the way out: "there is nothing here" has
    one spelling.
    """
    part = failure.get(name)
    return part if isinstance(part, Mapping) else {}


def _where_a_key_stands(rendered: str, key: str) -> int:
    """Where a mapping's key stands in a rendering, or -1 for nowhere.

    Only at a fragment boundary — the start of the string, just after a
    bracket, or just after the ``", "`` that joins two fragments — because
    that is where the rendering puts a key, while a VALUE is free to spell
    one anywhere. Without the boundary an honest stratum whose first value
    reads ``c=1`` puts ``c`` ahead of ``b``, and the two renderings then
    disagree about a fact both of them state correctly.
    """
    at = rendered.find(f"{key}=")
    while at > 0 and not (rendered[at - 1] == "["
                          or rendered[at - 2:at] == ", "):
        at = rendered.find(f"{key}=", at + 1)
    return at


def _as_written(fact, rendered: str):
    """The recorded fact, with each mapping's keys in the sentence's order.

    The rendering is one function of the value, so the two halves would
    compare as strings — except that the order of a MAPPING's keys is not
    something an envelope fixes. A JSON object is unordered by
    specification, and this repository's own answer corpus is written
    through ``json.dumps(sort_keys=True)``, which reorders the recorded
    half while the rendered half keeps the order its producer wrote in.
    Both are then telling the fact correctly and the strings differ.

    So the order is taken from the SENTENCE and every value from the
    RECORD. A key the sentence does not mention sorts last, which leaves
    the strings unequal, as a dropped fact should. Nothing about what is
    claimed comes from the sentence: which order a mapping's keys are in
    is not a claim anybody makes, so it is not one a reader can be lied
    to about. A LIST's order is left alone — that one IS a claim.
    """
    if isinstance(fact, Mapping):
        seen = {key: _where_a_key_stands(rendered, key) for key in fact}
        order = sorted(fact, key=lambda key: (seen[key] < 0, seen[key], key))
        return {key: _as_written(fact[key], rendered) for key in order}
    if isinstance(fact, list):
        return [_as_written(item, rendered) for item in fact]
    return fact


def _is_what_the_envelope_holds(recorded, spoken) -> bool:
    """Whether the recorded half is what this word travels as.

    ``halve`` sends a word out as the statement a reading surface fills
    in, and ``occasion`` writes down what the envelope is able to hold of
    the same value. Two shapes reach it: a word with facts of its own is
    written down whole, and a bare one reduces to its token. BOTH are
    accepted rather than told apart, because which shape a word takes is
    the producer's and is not a claim anybody can be misled by — and a
    rule that told them apart by whether the statement carries facts
    would refuse a producer that stated a bare member as a statement.
    Nothing does that today, which is a count rather than a declaration,
    and this rule rests only on declarations.
    """
    if isinstance(spoken, list):
        return (isinstance(recorded, list) and len(recorded) == len(spoken)
                and all(_is_what_the_envelope_holds(one, other)
                        for one, other in zip(recorded, spoken)))
    if recorded == spoken:
        return True
    return isinstance(spoken, Mapping) and recorded == spoken.get("token")


def _check_the_kind_is_the_one_the_species_declares(failure: Mapping) -> None:
    """Silent on a species this build has never heard of, deliberately.

    ``stamp`` closes what this build EMITS and says in as many words that
    reading is not symmetric: an envelope carrying an unregistered species
    is somebody else's honest refusal, and refusing it here would reject
    an answer for having been produced elsewhere. The word is held by the
    statement carrier either way, against the vocabulary this build
    declares — which is the check that belongs to a name.
    """
    species = refusals.BY_NAME.get(str(failure.get("failure_type")))
    if species is None or str(failure.get("kind")) == str(species.kind):
        return
    _reject(
        f"this answer refuses with {str(failure.get('failure_type'))!r} and "
        f"tells a reader that is a {str(failure.get('kind'))!r} problem; the "
        f"registry declares that species a {str(species.kind)!r} one. The "
        f"kind is what a reader is told to do next, and it is stamped from "
        f"the species rather than written at the refusing site, so the two "
        f"cannot honestly differ"
    )


def _check_the_sentence_carries_the_occasions_facts(failure: Mapping) -> None:
    spoken = set(_half(failure, "said")) | set(_half(failure, "words"))
    recorded = set(_half(failure, "details"))
    if spoken == recorded:
        return
    says = []
    if spoken - recorded:
        says.append(f"{sorted(spoken - recorded)} reach a reader with "
                    f"nothing behind them")
    if recorded - spoken:
        says.append(f"{sorted(recorded - spoken)} were recorded and say "
                    f"nothing")
    _reject(
        f"a refusal's facts and the sentence's facts are two halves of one "
        f"mapping, and here they are not: {'; '.join(says)}. A fact "
        f"appearing on one side alone was added to the sentence or dropped "
        f"out of it after the refusal was assembled"
    )


def _check_each_fact_is_written_twice_and_agrees(failure: Mapping) -> None:
    details = failure.get("details")
    if not isinstance(details, Mapping):
        return
    said = failure.get("said")
    for key, spoken in (said if isinstance(said, Mapping) else {}).items():
        if key not in details:
            continue
        again = language.capped(
            language.symbols(_as_written(details[key], str(spoken))))
        if str(spoken) == again:
            continue
        _reject(
            f"a refusal tells a reader {key} is {str(spoken)!r} and records "
            f"it as {again!r}. The two are one value written twice by the "
            f"block that assembled them, so a reader and an auditor of the "
            f"same answer are being shown different facts"
        )
    words = failure.get("words")
    for key, spoken in (words if isinstance(words, Mapping) else {}).items():
        if key not in details:
            continue
        if _is_what_the_envelope_holds(details[key], spoken):
            continue
        _reject(
            f"a refusal says {key} with the word {spoken!r} and records it "
            f"as {details[key]!r}. A word travels as the token a reading "
            f"surface looks up and as what the envelope can hold of it, "
            f"and those are the same fact"
        )


def _check_each_route_is_one_this_build_declares(failure: Mapping) -> None:
    """Refusing an unknown route, which is the opposite of the line above.

    Both silences are the producers' own. A species whose sentence is
    still unwritten is said by its token and a reader loses nothing; a
    route carries the sentence itself, so one this build has never heard
    of cannot be said at all — and a bare token where a reader expects
    what to do next is worse than the field being absent.
    """
    for row in failure.get("remedies") or ():
        if not isinstance(row, Mapping):
            continue
        member = refusals.REMEDY_BY_NAME.get(str(row.get("remedy")))
        if member is None:
            _reject(
                f"a refusal sends a reader out by {str(row.get('remedy'))!r}, "
                f"which is not a route this build declares. Every way past a "
                f"refusal carries its own sentence, so one that is not "
                f"declared cannot be said to anybody"
            )
        if member.takes_object != ("subject" in row):
            _reject(
                f"the route {str(member)!r} "
                f"{'names something' if member.takes_object else 'names nothing'}"
                f", and this one "
                f"{'names ' + repr(row.get('subject')) if 'subject' in row else 'names nothing'}"
                f". Which it is belongs to the route rather than to the "
                f"occasion, so a reader is either sent after nothing or "
                f"handed a sentence with an empty hole in it"
            )


def verify_refusal_block(result: Mapping) -> None:
    """Hold a refusal to what the one function that assembles it declares."""
    failure = result.get("estimator_failure")
    if not isinstance(failure, Mapping):
        return
    _check_the_kind_is_the_one_the_species_declares(failure)
    _check_the_sentence_carries_the_occasions_facts(failure)
    _check_each_fact_is_written_twice_and_agrees(failure)
    _check_each_route_is_one_this_build_declares(failure)
