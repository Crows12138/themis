"""Every sentence on the envelope, against the holes its own token declares.

A sentence does not travel as text. What crosses is a TOKEN naming a
template in one of this build's word tables, and the occasion's facts for
that template's holes — split into ``said`` for a value that reads the same
in every language and ``words`` for one that is itself a token. A surface
that knows the reader's language puts them back together.

Which makes the pair one claim in two halves, and nothing had ever asked
whether the halves agree. The consequence is not a crash, because the
assembler is built not to crash: a hole with no fact is rendered as a
stated absence, and a fact with no hole is dropped without a word. Both
were reachable through both doors. A description could be relabelled from
``the_variable_has_no_operational_definition`` to
``the_edge_was_learned_by_discovery`` and keep the facts it had, and the
reader would be told that an edge nobody can name was learned by an
algorithm nobody can name, on a gap that was about an undefined variable —
the two facts it did carry silently gone, the two it now claims silently
absent.

The tables are read rather than restated. What the other audits restate is
a producer's DECISION, and restating it is how the audit gets a second
author; a sentence's holes are not a decision but the sentence itself, and
a second transcription of 55 templates would be a second author for the
wording, which is the one thing this language layer exists to prevent.
What is independent here is the claim, not the vocabulary: the envelope
says which sentence and which facts, and the table says what that sentence
needs. Nothing on the envelope is compared against itself.

Two shapes carry a statement and both are asked. The generic one names its
own vocabulary, so the walk reads it off the entry. Twelve sites predate
that carrier and spell the token under a field of their own — a
description calls it ``sentence``, a route ``route``, a shortfall
``need``, a refusal ``failure_type``, and a gap's occasion is a statement
whose token is its ``kind`` — so those are named by the path they sit at,
and a test holds that table to every property in the contract whose
declared DOMAIN is one of these vocabularies, so which sites are covered
is measured rather than remembered.

That measurement was itself a function of this table for a while, and the
two sites it could not see are the reason to say so. The gate matched a
property's enum against the vocabularies and then kept only the hits whose
vocabulary this table already named — so it could find a new SITE of a
known set and never a new SET. A refusal's species and a variable's
declared scale are both members of declared vocabularies, both carry their
occasion's facts beside them, and neither was asked anything, because the
instrument that decides what is covered had its range fixed by what was
already covered.

A token this build does not carry is not a word from nowhere where the set
is somebody else's, and that is :func:`themis.language.spelt`'s design
rather than a hole: the door exists so a producer can name an id another
layer coined — an assumption an estimator declared — and a reader meets it
as a stand-in they are told to look up. Where the set is OURS the same
token is a word from nowhere, and this rule refuses it.

A borrowed set is not an unheld one, though, and passing its tokens over
left the LABEL free. The layer that coins them files its own record of
what it coined, beside the statement, and that record is what holds one
(:data:`_RECORDED_BESIDE`). Until it was read here, relabelling any
statement at all to the one borrowed set and keeping its token passed
every door — 414 leaves on 140 answers, one lie told over and over — and
a reader got the sentence replaced by the bare token, this build saying
it has no wording for a word it holds the wording for.

It passed over both, on the grounds that which member a token is, where
the set is ours, is a schema enum asked by the census. The census asks a
leaf by its PATH, and a word slot's set is named BESIDE the token — the
carrier is built on that, because a token alone does not say which set it
came from and two sets are free to spell a member the same way. So the
enumerations sit on the fields a set was first written at and reach no
other position the same set turns up in: across 243 answers there are
1096 word slots on 61 leaves, and the census had a domain for none of
them. On five of those leaves the token could be rewritten to any word
at all, and the largest of the five is the reason a gap gives for
itself, which 42 answers carry — a reason that is not a label beside
the sentence. For those gaps it IS the sentence.

The SET is carried for the same reason and asked here for it. The
contract enumerates the declared sets wherever the shared statement def
reaches, and two sites on the envelope are typed as open objects, where
the set name could be rewritten to any string and a reader sent to a
table no surface holds.

A LIST of statements makes a claim of its own, and being total over
the envelope is what lets this rule ask it: these are the sentences a
reader gets HERE, and they are different sentences. Every audit above
is about one statement — the sentence it names, the set it is from,
the record its coiner filed — and none of them is about the list,
because being one of several is not a property any of them has. So a
way past that names two of a design's SUTVA concerns could name the
first of them twice: the reader is told to watch one thing twice and
never told about the other, and no rule was looking at the pair.

The same TOKEN twice is not the question, and asking it would refuse
honest answers — four lists on this corpus say a sentence twice with
different facts, one risk outside its bound and then another. The
same STATEMENT twice is: two occasions that are the same occasion,
which is one occasion said twice with something else gone.

Membership is read, not restated: :data:`themis.language.TOKENS_ARE_OURS`
is where a set says whose its tokens are, and the words the producer wrote
are the member list. The exception is a table that is partial ON PURPOSE,
whose other half this build writes down (:data:`_DECLARED_SILENT`): a
token there is a member with no sentence by declaration, so its holes are
none rather than unknown, and it is not a stranger.

Some words on the envelope are decided by a record the sentence does
not carry. A QUESTION spells which way a monotonicity assumption runs;
the DERIVATION says which estimator ran, and so which premise an
instrument's answer rests on. Every sentence repeating such a word is
repeating that one word, and it is held here rather than in the block
audits for the reason the walk is total: the blocks that carry it are
not a list anyone chose. The one rule that read the question read it
for the row it was verifying and handed the word to that row's own
account, and the one that read the premise held two of its copies to
each other and to nothing else. A second record that reaches one of
the places its fact is written is not a second record of the others.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from .. import language
from ..assumption_glossary import CLAIM
from ..gaps import DESCRIBED, NEEDED, NOTHING_FILLS, PROVIDED, ROUTED
from ..refusals import REFUSED
from ..runtime.iv_words import Premise
from .errors import VerificationError
from .program_copy_rules import query_of

_RULE = "statement_facts_check"
_DECIDED = "statement_repeats_its_record"

#: The sites that spell a statement's token under a field of their own.
#:
#: Keyed by the path the entry sits at, because a field NAME does not say
#: which set it is from — three unrelated blocks spell something ``kind``
#: — and the path is what the schema knows. Restated here rather than read
#: off the producers for the reason every verifier table is: the producer
#: choosing where a statement goes must not also be the one saying where to
#: look for it.
#:
#: Which is also why it is not left as a restatement. A hand-written list of
#: sites is a list of the sites its author had in mind, and the first draft
#: of this one held five while the contract declares ten — the four
#: mediation statuses and a request's own note going unasked, every one of
#: them carrying facts on every occurrence in the corpus. So a gate reads
#: the contract for every property whose declared domain IS one of these
#: vocabularies and holds this table equal to what it finds.
#: ``measurement_scale`` is spelt rather than imported: its words live on
#: a class in the output layer, which no verifier may reach, and the
#: vocabulary gate below holds the spelling to what this build registers.
_MEASUREMENT_SCALE = "measurement_scale"

_CARRIERS: dict[str, tuple[str, str]] = {
    "data_gap_report.gaps.[]": ("kind", PROVIDED),
    "data_gap_report.gaps.[].describes.[]": ("sentence", DESCRIBED),
    "data_gap_report.gaps.[].alternative_paths.[]": ("route", ROUTED),
    "missing_information.[]": ("need", NEEDED),
    "investigation_requests.[].items.[]": ("need", NEEDED),
    "investigation_requests.[].note": ("need", NEEDED),
    "extensions.mediation_decomposition.numeric.cde_status": ("need", NEEDED),
    "extensions.mediation_decomposition.numeric.nde_nie_status":
        ("need", NEEDED),
    "extensions.mediation_joint_decomposition.numeric.cde_status":
        ("need", NEEDED),
    "extensions.mediation_joint_decomposition.numeric.nde_nie_status":
        ("need", NEEDED),
    "estimator_failure": ("failure_type", REFUSED),
    "extensions.type_reconciliation.checks.[]":
        ("declared_scale", _MEASUREMENT_SCALE),
}


#: Where a partial table's other half is written down.
#:
#: A table with no row for a token usually means this build has never heard
#: of it, and that is the case passed over below. A table that is partial
#: ON PURPOSE is a different thing, and this build says so where it is:
#: ``IF_PROVIDED`` answers what having the missing thing would buy and
#: ``NOTHING_FILLS`` names the species nothing buys anything for, the two
#: partitioning the kinds exactly, gated where they are declared. A token
#: on the second half has no sentence BY DECLARATION, so its hole set is
#: empty rather than unknown, and a fact beside it is a fact with nowhere
#: to go.
_DECLARED_SILENT: dict[str, frozenset[str]] = {
    PROVIDED: frozenset(NOTHING_FILLS),
}


#: Where the layer that coined a token filed its own record of it.
#:
#: A set whose tokens are not this build's own
#: (:data:`themis.language.TOKENS_ARE_OURS`) is not a set nothing
#: holds. The coiner writes what it coined down a second time, beside
#: the statement, and that second record is the authority this build
#: does not have: an estimator's assumption is assembled in one place
#: as ``{"id": ..., "claim": [statement]}``, so the id and the
#: sentence are minted together and never travel apart. The token is
#: the HEAD of the id rather than equal to it, the id running this
#: occasion's values together after the name.
#:
#: Keyed by vocabulary and naming a field on the record the statement
#: BELONGS TO, which is the shape the fact has: which sets are
#: borrowed is a fact about a set, and a borrowed token's record is
#: beside the statement rather than at a path — the same reason the
#: set itself travels beside the token. A gate holds every set that
#: says its tokens are not ours to having a row here, so a second
#: borrowed set cannot be declared into silence.
_RECORDED_BESIDE: dict[str, str] = {
    CLAIM: "id",
}


def _template(vocabulary: str, token: str) -> language.Words | None:
    """The sentence this token names, or None if this build has no such row.

    Both registries answer here. A vocabulary whose words live in a table
    is a mapping from token to words; one whose words live on an enum is a
    class whose members carry theirs. Which of the two a set is depends on
    where its words were written and is not a fact about the statement.
    """
    owner = language.VOCABULARIES.get(vocabulary)
    if owner is None:
        return None
    if isinstance(owner, Mapping):
        words = owner.get(token)
    else:
        words = next((getattr(m, "words", None) for m in owner
                      if str(m) == token), None)
    return words if isinstance(words, Mapping) and words else None


def _held_by_its_coiner(where: str, vocabulary: str, token: str,
                        record: Mapping | None) -> None:
    """A borrowed token, against the record its coiner filed beside it.

    Asked of every statement from such a set rather than only of the
    ones this build has no wording for: whether a glossary here
    happens to carry a row for an id is a fact about this build, and
    whether anything coined that id is a fact about the answer.

    EXISTENCE, and not agreement. Whether the two copies say the same
    thing — the token being the head of the id, the values under
    ``said`` appearing in what the id has left over — is a fact about
    that record's format, and the rule that audits the record asks it
    there. Asking it here as well would put one predicate in two
    places and, running first, leave the other unreachable: a 92-case
    end-to-end pin on that rule's wording stopped testing it. There is
    no population for it here either — every record on the corpus that
    carries such a field and holds a statement is one of those.
    """
    field = _RECORDED_BESIDE.get(vocabulary)
    if field is None:
        raise VerificationError(
            f"{where} tells a reader to look {token!r} up in "
            f"{vocabulary!r}, whose words this build declares to be "
            f"another layer's, and names nothing on an envelope that "
            f"records one; a word with no holder here and none there "
            f"reaches a reader with nothing behind it at all",
            rule=_RULE,
        )
    ident = record.get(field) if isinstance(record, Mapping) else None
    if not isinstance(ident, str) or not ident:
        raise VerificationError(
            f"{where} tells a reader to look {token!r} up in "
            f"{vocabulary!r}, whose words are ids another layer coins, "
            f"and nothing beside it is that layer's record of one; "
            f"such a token is held by the {field!r} its coiner "
            f"declared, and with none here the only thing behind the "
            f"word is the label on it, so the reader's surface finds "
            f"no row and hands the token back as a word to go and "
            f"learn",
            rule=_RULE,
        )

def _facts(entry: Mapping) -> set[str]:
    """The slots this occasion filled, both halves together.

    Which half a fact travels in is decided by the fact's own type and not
    by the sentence, so the same statement legitimately arrives with a name
    in ``said`` on one occasion and in ``words`` on another. The union is
    what the assembler puts into the holes.
    """
    return {str(k) for half in ("said", "words")
            for k in (entry.get(half) or ())}


def _hold(where: str, vocabulary: str, token: str, entry: Mapping,
          record: Mapping | None) -> None:
    """One statement against its template, and its pair against its set.

    Both halves the statement carries are asked, because both travel with
    it and neither is fixed by where it sits. The contract refuses an
    undeclared SET wherever the shared statement def reaches, and two
    sites are typed loosely enough that it does not reach them — a
    refusal's recorded reason and the factors under it, where the set
    name could be rewritten to any string at all. A rule that walks the
    whole envelope does not have to know which sites those are.

    Then the token, against that set. One lookup answers it and the holes
    both: a token with no row in the set it names has no holes to be held
    to, and whether that is a hole in this build or a token this build was
    never going to carry is the set's own answer.
    """
    if vocabulary not in language.VOCABULARIES:
        raise VerificationError(
            f"{where} sends a reader to {vocabulary!r} for the word "
            f"{token!r}, and this build declares no such set; the surface "
            f"that turns a word into text holds one table per set and "
            f"would have none for this one, so the reader is handed the "
            f"token back with nowhere to look it up",
            rule=_RULE,
        )
    ours = language.TOKENS_ARE_OURS.get(vocabulary, True)
    if not ours:
        _held_by_its_coiner(where, vocabulary, token, record)
    words = _template(vocabulary, token)
    if words is not None:
        declared = language.holes(words)
    elif token in _DECLARED_SILENT.get(vocabulary, ()):
        declared = set()
    elif ours:
        raise VerificationError(
            f"{where} tells a reader to look {token!r} up in "
            f"{vocabulary!r}, and that set has no such word; the "
            f"reader's surface hands a token it cannot find back "
            f"as a stand-in to go and look up, so a word from "
            f"nowhere arrives where the sentence was promised and "
            f"says it is one this reader has yet to learn",
            rule=_RULE,
        )
    else:
        return
    carried = _facts(entry)
    if extra := sorted(carried - declared):
        raise VerificationError(
            f"{where} carries {extra} beside {token!r}, and "
            + ("that sentence has no hole for any of them"
               if words is not None else
               f"{token!r} is declared to have no sentence at all")
            + "; a fact with nowhere to go is dropped where the sentence "
              "is assembled, so the reader is never shown it and never "
              "told it was there",
            rule=_RULE,
        )
    if unfilled := sorted(declared - carried):
        raise VerificationError(
            f"the sentence {token!r} at {where} has a hole for each of "
            f"{unfilled} and this occasion supplied none of them; the hole "
            f"is rendered as a stated absence, so the reader is handed a "
            f"sentence that promises a fact and does not name it",
            rule=_RULE,
        )


def _once_each(where: str, items: Sequence) -> None:
    """A list of statements, against itself.

    Compared whole rather than by token: which facts an occasion
    carried are what make it that occasion, and two sentences from one
    template about two different things are two sentences. What this
    refuses is the pair that is one — rendered, a reader is handed the
    same words twice, and whatever the duplicate displaced is not on
    the envelope to be missed.
    """
    seen: list = []
    for item in items:
        if not (isinstance(item, Mapping)
                and isinstance(item.get("vocabulary"), str)
                and "token" in item):
            return
        if any(item == earlier for earlier in seen):
            raise VerificationError(
                f"{where} hands a reader the sentence "
                f"{str(item.get('token') or '')!r} twice, with the "
                f"same facts both times; the list is what a reader is "
                f"shown, so one of its places is saying nothing new "
                f"and whatever belonged there is not here to be "
                f"missed",
                rule=_RULE,
            )
        seen.append(item)


def _walk(node, path: tuple[str, ...],
          record: Mapping | None = None) -> None:
    """Every statement under this node, wherever it is written.

    Descends through everything rather than through a list of blocks: a
    statement's facts may themselves be statements, so one arrives four
    levels inside another, and a walk that knew where to look would cover
    the places its author had thought of.

    ``record`` is the record the statement belongs to, which a list is
    transparent to: an assumption writes its claim as a LIST because
    one occasion turns out to have however many sentences it has, and
    every one of them is that assumption's.
    """
    if isinstance(node, Mapping):
        where = ".".join(path)
        vocabulary = node.get("vocabulary")
        if isinstance(vocabulary, str) and "token" in node:
            _hold(where or "the result", vocabulary,
                  str(node.get("token") or ""), node, record)
        carrier = _CARRIERS.get(where)
        if carrier is not None:
            spelling, named = carrier
            token = node.get(spelling)
            if token:
                _hold(where, named, str(token), node, record)
        for key, value in node.items():
            _walk(value, (*path, str(key)), node)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        if node:
            _once_each(".".join(path) or "the result", node)
        for item in node:
            _walk(item, (*path, "[]"), record)


def verify_statements_carry_their_facts(result: Mapping) -> None:
    """Hold every statement on this envelope to the sentence it names.

    Total over the envelope, because which blocks carry a sentence is not
    something a reader chose and not something this rule should have to
    know. Nothing is re-derived: the claim being audited is the pairing,
    and the pairing is wrong or right on its own terms.
    """
    _walk(result, ())


def _the_question_spells(result: Mapping,
                        program: Mapping) -> dict[str, str]:
    """Every word this answer's own question spells, by the set it is from.

    A program spells words from this build's sets in two shapes, and the
    contract says which: a word about a NAMED THING — the scale a column
    is declared at — and a word about the QUESTION, which is what
    ``query.assumptions`` holds. The first is keyed on the name and the
    audit that reads it is keyed on the name too; the second has no name
    to key on, being one word for the whole answer.

    Read rather than tabulated: an assumption a question declares is
    named after the SET its value comes from, so the pairing is the
    contract's and a table here would be a second copy of it going
    stale. A key naming no set this build declares, or a value that is
    not one of its members, is passed over — an assumption is free to be
    a number or a flag, and this rule has nothing to say about those.

    The answer's OWN question, not the program's first: a program
    carries as many statements as the caller wrote, and a word read off
    one this answer is not for would hold its sentences to a
    declaration nobody made about them. Where ``query_id`` names no
    statement this says nothing — that an answer names its question is
    another rule's claim, and guessing here would be answering a
    question this cannot identify.
    """
    query = query_of(program, result.get("query_id"))
    assumptions = query.get("assumptions") if isinstance(
        query, Mapping) else None
    if not isinstance(assumptions, Mapping):
        return {}
    spelt: dict[str, str] = {}
    for name, value in assumptions.items():
        owner = language.VOCABULARIES.get(str(name))
        if owner is None or not isinstance(value, str):
            continue
        if any(str(member) == value for member in owner):
            spelt[str(name)] = value
    return spelt


#: Which premise an instrument's answer rests on, by the step that settled it.
#:
#: The set's own words name the estimator along with the premise — a reader
#: told "monotonicity" without being told it buys a LATE has been told half
#: of it — so which member is true is a question about which estimator ran,
#: and the derivation is the record of that the kernel replays step by step.
#: A feedback loop reduced to simultaneous equations makes the number one
#: equation's coefficient; the Wald evaluation makes it a LATE under the
#: declared direction. Restated here rather than read off the producers for
#: the reason every verifier table is, and held by a gate to naming steps
#: the verifier really replays, so a misspelt row cannot sit here unread.
_PREMISE_SETTLED_BY: dict[str, str] = {
    "feedback_loop_withdraws_adjustment":
        str(Premise.LINEAR_SIMULTANEOUS_SYSTEM),
    "iv_wald_numeric_evaluate": str(Premise.MONOTONICITY_AS_DECLARED),
}

#: The step that identified through an instrument at all. A chain with it and
#: with neither settling step has chosen no estimator yet, and the member
#: saying so is a claim about THAT answer — so it is owed only where this
#: step ran, not assumed of every answer that happens to carry the word.
_THROUGH_AN_INSTRUMENT = "identify_via_iv"


def _the_premise_the_derivation_ran(result: Mapping,
                                    program: Mapping) -> dict[str, str]:
    """Which premise the estimator this answer ran rests on, by its set.

    Silent where the chain settles nothing about an instrument, and silent
    where it names two estimators: which of them this answer's premise
    belongs to is not something the chain says, and picking one would be
    refusing an answer on a guess.
    """
    derivation = result.get("derivation")
    steps = derivation.get("steps") if isinstance(
        derivation, Mapping) else None
    ran = {str(step.get("rule")) for step in steps or ()
           if isinstance(step, Mapping)}
    settled = {_PREMISE_SETTLED_BY[rule] for rule in ran
               if rule in _PREMISE_SETTLED_BY}
    if not settled and _THROUGH_AN_INSTRUMENT in ran:
        settled = {str(Premise.MONOTONICITY_OR_LINEARITY)}
    if len(settled) != 1:
        return {}
    return {Premise.vocabulary: next(iter(settled))}


#: Every record that decides a word on the envelope, and how a reader is told
#: whose word it was.
#:
#: Each reader answers for one envelope with the word its record decides for
#: each set it speaks for, and nothing for a set its record is silent about.
#: The sets they speak for do not overlap, which a gate holds: two records
#: deciding one set would make which of them a sentence answers to a fact
#: about the order of this tuple.
_DECIDERS: tuple[tuple[Callable[[Mapping, Mapping], dict[str, str]], str],
                 ...] = (
    (_the_question_spells, "the question it answers declares"),
    (_the_premise_the_derivation_ran, "the derivation it ran settles"),
)


def _repeat(node, path: tuple[str, ...],
            decided: Mapping[str, tuple[str, str]]) -> None:
    """Every statement under this node, against the word it must repeat.

    Its own descent rather than :func:`_walk`'s: what that walk carries
    down is the record a statement belongs to, which this question has
    no use for, and what this one needs is the statements that carry
    their set beside them. A decided word can reach no other shape — a
    carrier site spells its token under a field of its own and its set
    is fixed by :data:`_CARRIERS`, none of which is a set a record here
    decides, which a gate holds rather than this asserts.
    """
    if isinstance(node, Mapping):
        vocabulary = node.get("vocabulary")
        entry = (decided.get(vocabulary)
                 if isinstance(vocabulary, str) else None)
        if entry is not None and "token" in node:
            token = str(node.get("token") or "")
            word, whose = entry
            if token != word:
                raise VerificationError(
                    f"{'.'.join(path) or 'the result'} tells a reader "
                    f"the {vocabulary} this answer rests on is "
                    f"{token!r}; {whose} {word!r}, and a reader "
                    f"weighing the assumption is weighing one this "
                    f"answer does not rest on",
                    rule=_DECIDED,
                )
        for key, value in node.items():
            _repeat(value, (*path, str(key)), decided)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for item in node:
            _repeat(item, (*path, "[]"), decided)


def verify_statements_repeat_what_decided_them(result: Mapping,
                                               program: Mapping) -> None:
    """Hold every sentence repeating a decided word to what decided it.

    The rule above asks whether a statement's facts fit the sentence it
    names, which is a question the envelope answers on its own. This one
    is a copy check against a record the sentence does not carry, and it
    is the sharper of the two: which way a monotonicity assumption runs
    decides which side of an interval tightens, and which premise an
    instrument rests on decides whether the number is a LATE or one
    equation's coefficient — so a sentence naming the other word hands a
    reader the opposite conclusion in words that are all real. Each such
    word is written in several blocks, and a rule holding it at the block
    it was first computed in held none of the others.

    What this is general about, and where that generality ends: what a
    record decides is the word THIS answer rests on. Should a producer
    ever need to say some other assumption's direction or premise in the
    same words, it would be spelling a second fact, and the record is not
    one of that — such a sentence needs its own set or its own second
    record, and would be refused here until it has one. Said rather than
    guarded against: a guard would be a list of the positions this rule
    may speak at, which is the thing it exists to do without.

    Returns ``None`` on accept, including when no record decides a word
    this envelope carries.
    """
    decided: dict[str, tuple[str, str]] = {}
    for read, whose in _DECIDERS:
        for vocabulary, word in read(result, program).items():
            decided[vocabulary] = (word, whose)
    if decided:
        _repeat(result, (), decided)
