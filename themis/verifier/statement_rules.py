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

A token this build does not carry is passed over rather than refused, and
that is :func:`themis.language.spelt`'s design rather than a hole here: the
door exists so a producer can name a member of somebody else's set — an
assumption id an estimator declared — and a reader meets an unknown token
as a stand-in they are told to look up. Which member a token is, where the
set is ours, is a schema enum and is asked by the census; this rule asks
the question that comes after it, and asks it of members and non-members
alike. The exception is a table that is partial ON PURPOSE, whose other
half this build writes down (:data:`_DECLARED_SILENT`): a token there has
no sentence by declaration, so its holes are none rather than unknown.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .. import language
from ..gaps import DESCRIBED, NEEDED, NOTHING_FILLS, PROVIDED, ROUTED
from ..refusals import REFUSED
from .errors import VerificationError

_RULE = "statement_facts_check"

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


def _facts(entry: Mapping) -> set[str]:
    """The slots this occasion filled, both halves together.

    Which half a fact travels in is decided by the fact's own type and not
    by the sentence, so the same statement legitimately arrives with a name
    in ``said`` on one occasion and in ``words`` on another. The union is
    what the assembler puts into the holes.
    """
    return {str(k) for half in ("said", "words")
            for k in (entry.get(half) or ())}


def _hold(where: str, vocabulary: str, token: str, entry: Mapping) -> None:
    """One statement against its template."""
    words = _template(vocabulary, token)
    if words is None:
        if token not in _DECLARED_SILENT.get(vocabulary, ()):
            return
        declared: set[str] = set()
    else:
        declared = language.holes(words)
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


def _walk(node, path: tuple[str, ...]) -> None:
    """Every statement under this node, wherever it is written.

    Descends through everything rather than through a list of blocks: a
    statement's facts may themselves be statements, so one arrives four
    levels inside another, and a walk that knew where to look would cover
    the places its author had thought of.
    """
    if isinstance(node, Mapping):
        where = ".".join(path)
        vocabulary = node.get("vocabulary")
        if isinstance(vocabulary, str) and "token" in node:
            _hold(where or "the result", vocabulary,
                  str(node.get("token") or ""), node)
        carrier = _CARRIERS.get(where)
        if carrier is not None:
            spelling, named = carrier
            token = node.get(spelling)
            if token:
                _hold(where, named, str(token), node)
        for key, value in node.items():
            _walk(value, (*path, str(key)))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for item in node:
            _walk(item, (*path, "[]"))


def verify_statements_carry_their_facts(result: Mapping) -> None:
    """Hold every statement on this envelope to the sentence it names.

    Total over the envelope, because which blocks carry a sentence is not
    something a reader chose and not something this rule should have to
    know. Nothing is re-derived: the claim being audited is the pairing,
    and the pairing is wrong or right on its own terms.
    """
    _walk(result, ())
