"""The list a reader is told to go and fill, read rather than counted.

``investigation_requests`` is the one block that asks the reader for
something. Each item names a ``target``, carries a ``skeleton`` — the
patch itself — and a ``said`` mapping whose contents are substituted into
the sentence the reader gets. The skeleton is not illustrative: the
second turn takes it verbatim (``kernel.apply_patch_and_run`` exists so
that an LLM copying one "should just work"), which makes a rewritten
predicate a reader filling in a different variable.

WHY NOTHING READ IT. Two rules touch the block and both use it as a
DENOMINATOR. T10-1 collects every target into a set and resolves gap
provenance against it; T10-2 asks the other direction, that each item be
cited by some gap. Neither ever looks inside an item, and a denominator
can be shortened. It is shortened twice here: the framing group is exempt
from T10-2 by name, which is thirty-seven of forty-three requests, and
what remained was reachable through ``if not target: continue`` — empty
the target and the rule that exists to demand coverage skips it. An
exemption and a skip are the same move with different spellings, which is
why the second is fixed where it lives rather than worked around here.

WHAT ANCHORS IT, ALL OF IT ALREADY ON THE ENVELOPE OR IN THE PROGRAM.
A framing item's target is a ``framing_notes[].predicate``, seventy-five
of seventy-five, and that side is held: T10-2's third check requires
every note to be cited by a gap. Inside an item the predicate is written
three times — ``target``, ``skeleton.predicate``, ``said.predicate`` —
and all three agree on all seventy-five. The skeleton's empty fields are
empty in the program's OWN variable declaration and its ``existing``
entries equal that declaration exactly, forty-eight of forty-eight; that
is the asked side, which an answer cannot edit. And ``said.count`` and
``said.fields`` are determined by the skeleton lying beside them.

A parameter ask carries the other kind of skeleton, a probability rather
than a framing patch, and it is anchored the same way twice over: the
sentence quotes a ``key`` that the item's target ends with, and the
distribution is over predicates the program NAMES. Names, not declares —
those are two rosters and this is the wider one. A program introduces a
predicate through a ``variable`` statement or through an atom in any
statement about the world, and a graph written entirely out of cause
edges declares nothing while naming everything. Answering the membership
question out of the declaration table refused a reader an ask that
``apply_patch_and_run`` accepts, which is the test that settles which
roster this rule wanted.

THE HEADING OVER THE LIST, which the above left for later by descending
into ``items`` on its first line. A request is four fields and then the
items: an action, a target, a priority, a group. Every one of them is
written out of the items — the action from the channel, the group from
what those items are rows of, the target from the single item or from how
many there are, the priority from the strongest among them — so the
second record was on the envelope the whole time. The one heading field
this module did read, ``group``, it read as the input to a branch, and a
label read as an input cannot be wrong. Two of the four did not even
reach the declared remainder: they are enums, the only lie the census
could tell an enum was one validation refuses, and a leaf that scores
held is a leaf nobody looks at again.

What that leaves unheld is thirteen requests' priority, and the reason is
a fact rather than a story: their items are not rows of
``missing_information``, so nothing on the envelope says what they are
worth. Framing is not among them — it has no rows either, but the
priority it is filed at is a constant its own pass writes, and a constant
with no second copy is restated and pinned, as a diagnostic band is.

ONE FIELD IS NOT A COPY, and treating it as one left it half held. An
item's ``gap`` names a species in the report on the same envelope, and it
was being compared to the ``missing_information`` row for the same target
— a second RENDERING of it. Two records agreeing is only a check where
both records are there, and this one is not: an item that block has no row
for got nothing asked of it, which is 107 of 158 answers accepting an ask
whose species the report never carried. A reference does not need a second
record, because what it names is either on the envelope or it is not. So
that field is asked of the report's own list, and the pattern this module
is built on is stated with its own boundary: two copies check each other
where there are two, and a reference is checked against its referent.

AND ONE RECORD HAS TWO DIRECTIONS, which is where the last unheld field
of a parameter ask was. A skeleton is the reader's copy of a patch: it
leaves on the envelope and comes back through ``apply_patch_and_run``
verbatim. The inbound half is held where it matters most — semantic
validation refuses an LLM-PROPOSED statement whose source is empty,
because a number somebody guessed and nobody sourced is one no reader can
weigh. A stub merged back carries ``provenance="structural"`` unless the
caller says otherwise, so that guard covers the fabrication case rather
than every return, which is worth saying exactly: the inbound rule is
narrower than this one. The outbound half was read for what it says and
never for what it must not say, and the two halves want opposite things
in the same two fields. Going out, this system is ASKING:
the slots a reader fills are the slots it cannot fill, so they leave
empty. A value already written in one is this system's own figure coming
back as somebody's measurement, and a source already written beside it is
a provenance nobody can have for a number nobody has taken. What the
filled form looks like is written down elsewhere in this repository —
``themis.kb.translator`` puts a value and a citation in exactly these two
slots — which is the same record with the reader's half supplied.

So this module restates four things: the set of skeleton KINDS, because
it decides which question an item can be asked at all; the channel table,
because a request names its channel twice and the two names must be for
one channel; the format of a grouped heading, because that format is
written by two runtime functions from one definition rather than being
any site's private spelling; and the word a source carries until somebody
measures the number, because that word is the whole of what says the form
is still blank. Each is compared to its producer by a test.
Everything else is "do these two records of one fact agree", and the
record it asks of the program is the strongest, because the program is
not the answer's to write.
"""
from __future__ import annotations

import collections
import dataclasses
import itertools
import re
from typing import Any, Iterable, Mapping, NoReturn

from .. import gaps as _gaps
from ..types import Atom, ConstTerm, VariableDeclaration
from .errors import VerificationError

_RULE = "investigation_item_check"

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: What a skeleton can BE. A patch goes back through
#: ``apply_patch_and_run``, which accepts exactly these two record kinds,
#: and they are answerable against different things: one is a framing
#: patch for a declared variable, the other a probability the reader is
#: asked to supply.
#:
#: Restated rather than imported — a verifier that imports the producer's
#: table agrees with it by construction — and pinned to that table by a
#: test, so a third kind arrives as a red suite rather than as an item
#: nothing reads. Written before the pin existed, this rule took "has a
#: skeleton" to mean the first kind, which is what the forty-four answer
#: shapes contain and not what the system has; ten honest results said
#: otherwise.
_VARIABLE_PATCH = "variable_patch"
_PROBABILITY = "probability"
_SKELETON_KINDS: frozenset[str] = frozenset({_VARIABLE_PATCH, _PROBABILITY})

#: What stands in a parameter ask's source until the reader writes one.
#: The scheduler builds the stub for a missing CPT entry with its value
#: unset and this word beside it, and those two are the whole of what a
#: reader supplies — which is why an ask carrying anything else in either
#: is answering the question it was raised to ask.
#:
#: Restated rather than imported, for the reason above ``_SKELETON_KINDS``,
#: and pinned to the producer by a test: it is that function's single
#: literal, and a verifier reading it from there would agree with a
#: producer that started pre-filling the field.
_A_SOURCE_NOBODY_HAS_YET = "TODO"

#: Which repair channel each action belongs to. One request is one
#: channel, and the row names that channel twice — once as the group it
#: was pushed under, once as the action a reader is told to take — so
#: each is the other's second record and neither can move alone.
#:
#: Restated for the reason above ``_SKELETON_KINDS``, and pinned to both
#: producers by a test: five pairs come from the pusher's own table, the
#: sixth from the framing channel the scheduler attaches separately.
_ACTION_FOR_GROUP: dict[str, str] = {
    "parameter":   "validate_parameter",
    "observation": "collect_observation",
    "sample":      "increase_sample",
    "structure":   "run_experiment",
    "assumption":  "define_assumption",
    "framing":     "define_variable",
}

#: What the framing channel puts in a heading it writes by hand. Every
#: other channel's priority is the strongest among its items, and those
#: items are rows of ``missing_information``; framing items are not, so
#: this constant is the answer's only record of it. A constant a reader is
#: shown with no second copy is restated and pinned, as a diagnostic band
#: is.
_FRAMING_GROUP = "framing"
_FRAMING_PRIORITY = "medium"

#: Strongest last. A group speaks with the loudest voice among its items.
_PRIORITY_ORDER: tuple[str, ...] = ("low", "medium", "high")


class _Absent:
    """A declaration field that does not exist, told apart from one that
    exists and is unset. They are the same value under ``getattr`` with a
    default of ``None``, and they mean opposite things: no place for this
    field at all, versus a place a reader is rightly asked to fill."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<absent>"


_ABSENT = _Absent()


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, step_index=None, rule=_RULE)


def declarations_of(program: Any) -> dict[str, VariableDeclaration]:
    """The variable declarations the PROGRAM makes, by predicate."""
    out: dict[str, VariableDeclaration] = {}
    for statement in getattr(program, "statements", ()) or ():
        if isinstance(statement, VariableDeclaration):
            out[statement.predicate] = statement
    return out


def predicates_of(program: Any) -> frozenset[str]:
    """Every predicate the PROGRAM names, whichever way it names it.

    Two rosters answering two questions. ``declarations_of`` above answers
    "what did the program SAY ABOUT this variable" and hands back the
    declaration, which is what a rule wanting a domain or a field list
    needs. This answers "does this program know this name at all" — and a
    program introduces a predicate either by declaring a variable or by
    naming an atom in a statement about the world, so a graph written
    entirely out of cause edges declares nothing while naming everything.

    Reaching for the first roster to answer the second question is how a
    reader came to be refused an honest ask: a distribution over a
    variable the program introduces through a cause edge, which the door
    the patch goes back through accepts perfectly well.

    Walked generically over the frozen records rather than by listing the
    statement kinds that carry atoms. A list of kinds would be a third
    roster, and a roster needing an edit whenever a statement kind is
    added is the shape of the defect this exists to close.
    """
    found: set[str] = set()
    seen: set[int] = set()
    stack: list[Any] = list(getattr(program, "statements", ()) or ())
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        predicate = getattr(node, "predicate", None)
        if isinstance(predicate, str):
            found.add(predicate)
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            stack.extend(getattr(node, field.name, None)
                         for field in dataclasses.fields(node))
        elif isinstance(node, (tuple, list, set, frozenset)):
            stack.extend(node)
        elif isinstance(node, Mapping):
            stack.extend(node.values())
    return frozenset(found)


def atoms_of(program: Any) -> frozenset:
    """Every whole ATOM the program names, arguments included.

    The third roster, and it answers a third question.
    :func:`predicates_of` answers "does this program know this name",
    which is about ``survival``; this answers "does this program know
    this variable", which is about ``survival(patient)``. They differ by
    exactly the part a reader acts on — the unit whose data somebody is
    being sent to collect — so asking the predicate roster whether an
    atom is real accepts ``survival(nobody)`` for as long as any
    ``survival`` is mentioned anywhere.

    Not the graph, either. A program can name variables while declaring
    no edges at all — a bare probability question does — and its graph is
    then empty while its statements name everything. Held to the graph,
    such an answer's honest skeleton is refused for naming a variable
    that "is not there", when there is simply no graph for it to be in.

    Same generic walk as the roster above, for the same reason: a list of
    the statement kinds that carry atoms would need editing whenever a
    kind is added, which is the shape of defect these rosters exist to
    close.
    """
    found: set = set()
    seen: set[int] = set()
    stack: list[Any] = list(getattr(program, "statements", ()) or ())
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, Atom):
            found.add(node)
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            stack.extend(getattr(node, field.name, None)
                         for field in dataclasses.fields(node))
        elif isinstance(node, (tuple, list, set, frozenset)):
            stack.extend(node)
        elif isinstance(node, Mapping):
            stack.extend(node.values())
    return frozenset(found)


def variables_named_by(program: Any) -> frozenset[tuple[str, tuple[str, ...]]]:
    """The GROUNDED variables of a problem: ``z(me)``, not ``z(I)``.

    A statement may be written for all units — ``forall I: z(I) → y(I)`` —
    and what a reader is later told to measure is one unit's variable,
    ``z(me)``. Neither roster above answers that. :func:`atoms_of` hands
    back ``z(I)``, which matches nothing an envelope spells; the graph
    holds the grounded form but is built downstream of here.

    So the quantified positions are instantiated at the constants this
    same problem names, which is the grounding the graph performs. Two
    things follow, and both are the point: ``z(me)`` is admitted for a
    program that only ever wrote ``z(I)``, and ``z(nobody)`` is not,
    because ``nobody`` is a unit this problem never mentions.
    """
    atoms = atoms_of(program)
    constants = tuple(sorted({
        t.name for a in atoms for t in a.args if isinstance(t, ConstTerm)}))
    found: set[tuple[str, tuple[str, ...]]] = set()
    for atom in atoms:
        choices = [
            (t.name,) if isinstance(t, ConstTerm) else constants
            for t in atom.args
        ]
        if any(not c for c in choices):
            continue          # a variable with no constant to stand for
        for names in itertools.product(*choices):
            found.add((atom.predicate, names))
    return frozenset(found)


def _agree(declared: Any, shown: Any) -> bool:
    """Whether a declaration's value and the envelope's copy of it match.

    A domain is a tuple in the program and a list once it has been
    through JSON; nothing else needs the widening, and widening further
    would start accepting values that are merely similar.
    """
    if isinstance(declared, tuple):
        return list(declared) == shown
    return bool(declared == shown)


def _check_the_predicate_is_written_once(where: str, item: Mapping,
                                         said: Mapping, target: str) -> None:
    for label, shown in (("skeleton.predicate",
                          (item.get("skeleton") or {}).get("predicate")),
                         ("said.predicate", said.get("predicate"))):
        if shown is None:
            continue
        if shown != target:
            _reject(
                f"{where} tells a reader to patch {target!r} and its "
                f"{label} says {shown!r}; one item asks about one "
                f"variable, and a reader following this fills in the "
                f"other one"
            )


def _unfilled_fields(where: str, skeleton: Mapping,
                     declaration: VariableDeclaration) -> list[str]:
    """Which fields this patch leaves for the reader, checked against the
    program rather than against a list of what framing means here."""
    fields = skeleton.get("fields")
    if not isinstance(fields, Mapping):
        _reject(
            f"{where} hands a reader a patch with no fields to fill; the "
            f"item exists because something is unset, and the patch is "
            f"where that something is named"
        )
    unfilled: list[str] = []
    for key, value in fields.items():
        declared = getattr(declaration, str(key), _ABSENT)
        if declared is _ABSENT:
            _reject(
                f"{where} asks a reader to supply {key!r}, which a "
                f"variable declaration has no place for; the patch would "
                f"be rejected by the door it is written for"
            )
        if value is None:
            if declared is not None:
                _reject(
                    f"{where} asks a reader to supply {key!r} for "
                    f"{skeleton.get('predicate')!r} and the program "
                    f"already declares it as {declared!r}"
                )
            unfilled.append(str(key))
    return unfilled


def _check_what_the_patch_says_is_already_known(
    where: str, skeleton: Mapping, declaration: VariableDeclaration,
) -> None:
    existing = skeleton.get("existing")
    if not isinstance(existing, Mapping):
        return
    for key, value in existing.items():
        declared = getattr(declaration, str(key), _ABSENT)
        if declared is _ABSENT:
            _reject(
                f"{where} tells a reader the program already fixed "
                f"{key!r}, which is not something a variable declaration "
                f"says"
            )
        if not _agree(declared, value):
            _reject(
                f"{where} tells a reader the program already fixed "
                f"{key!r} at {value!r}; the program says {declared!r}, "
                f"and a reader who trusts the patch will not supply what "
                f"is actually missing"
            )


def _check_the_sentence_counts_what_the_patch_leaves(
    where: str, said: Mapping, unfilled: Iterable[str],
) -> None:
    """The number and the list a reader is shown, against the patch.

    Read off the skeleton rather than reassembled: which fields are
    unfilled is the patch's own fact, and the sentence quoting it is a
    second record of that fact. Identifier tokens rather than a split on
    the separator, so the sentence keeps the right to be spelled
    differently.
    """
    owed = set(unfilled)
    for key in ("count", "fields"):
        if key not in said and owed:
            _reject(
                f"{where} leaves {sorted(owed)} for a reader to fill and "
                f"its sentence says no {key}; the sentence is assembled "
                f"from these and would reach the reader with a hole"
            )
    count = said.get("count")
    if count is not None:
        # Emptiness first, and on its own. Every test below it is an
        # equality or a membership, and a blank passes membership
        # vacuously while reading, to a person, as no claim at all.
        if not str(count).strip():
            _reject(
                f"{where} tells a reader how many fields are unset and "
                f"puts nothing there"
            )
        if str(count) != str(len(owed)):
            _reject(
                f"{where} tells a reader {str(count)!r} fields are unset "
                f"and the patch beside it leaves {len(owed)}"
            )
    spelled = said.get("fields")
    if spelled is not None:
        if not str(spelled).strip():
            _reject(
                f"{where} tells a reader which fields are unset and "
                f"names none"
            )
        tokens = set(_IDENT.findall(str(spelled)))
        if tokens != owed:
            _reject(
                f"{where} tells a reader to fill {sorted(tokens)} and the "
                f"patch beside it leaves {sorted(owed)}"
            )


#: The name-and-value pairs a parameter key spells, and the sibling of
#: ``_NAMES_IN_A_KEY`` below: that one reads what stands before an "=",
#: this one reads what stands after it as well. Two expressions of one
#: grammar rather than one of them derived from the other, because they
#: are read for two different rules and a key ending in a bare "name="
#: mentions a name while spelling no value.
_PAIRS_IN_A_KEY = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([^,;|)\s]+)")


def _check_a_parameter_the_reader_is_asked_for(
    where: str, skeleton: Mapping, said: Mapping, target: str,
) -> None:
    """A probability skeleton, held to the sentence beside it.

    The sentence quotes a ``key`` and the item's target ends with it, so
    the two are one record read twice rather than reassembled from a
    prefix this module would then own.

    The name is also a rendering of the patch under it. ``P(y=True|x=
    True)`` says which parameter is short in the one string a reader looks
    the ask up by, and the skeleton says the same thing as a record —
    which variable, at which value, conditioned on which others at which
    values. So the pairs the name spells are the pairs the skeleton
    states, and an item whose two halves disagree hands a reader a stub
    for one number under the heading of another.

    Held as the target pair and the given pairs, and the given ones as a
    multiset: what is conditioned on is a set, so an answer that writes it
    in another order says the same thing and must not be refused for it.
    Arguments are not in this comparison because the name does not carry
    them — the atoms' units are held one rule earlier, against the
    problem's own grounded variables.

    It also used to ask whether the program names the predicates the
    distribution is over. That question is now put one level finer and one
    step earlier — the whole atom, arguments included, against the
    problem's grounded variables — which refuses every name this refused
    and the wrong-unit case besides. The roster it consulted has gone with
    it: a parameter of a check is only worth passing while something reads
    it.
    """
    key = said.get("key")
    if key is not None:
        if not str(key).strip():
            _reject(
                f"{where} tells a reader which parameter is missing and "
                f"names none"
            )
        if not target.endswith(str(key)):
            _reject(
                f"{where} asks a reader for {str(key)!r} and is recorded "
                f"as {target!r}; a reader looking the ask up by the name "
                f"they were given finds a different one"
            )
    head, bar, tail = str(target).partition("|")
    spelt_target = _PAIRS_IN_A_KEY.findall(head)
    node = skeleton.get("target")
    node = node if isinstance(node, Mapping) else {}
    mine_target = ((node.get("atom") or {}).get("predicate"),
                   str(node.get("value")))
    if len(spelt_target) != 1:
        _reject(
            f"{where} hands a reader a stub for one number and is filed "
            f"under {target!r}, which spells no single parameter before "
            f"its conditioning bar; the name is the only handle a reader "
            f"has on which number this is"
        )
    if tuple(spelt_target[0]) != mine_target:
        _reject(
            f"{where} is filed under {target!r} and the patch beneath it "
            f"is a stub for {mine_target[0]}={mine_target[1]}; a reader "
            f"who goes and measures what the patch says fills in a "
            f"different number from the one this ask is short of"
        )
    spelt_given = collections.Counter(_PAIRS_IN_A_KEY.findall(tail) if bar
                                      else [])
    mine_given = collections.Counter(
        ((g.get("atom") or {}).get("predicate"), str(g.get("value")))
        for g in skeleton.get("given") or () if isinstance(g, Mapping))
    if spelt_given != mine_given:
        conditions = sorted(f"{p}={v}" for p, v in mine_given.elements())
        _reject(
            f"{where} is filed under {target!r} and the patch beneath it "
            f"conditions on {conditions or 'nothing'}; the parameter a "
            f"reader is sent to measure is only that number under the "
            f"conditions written beside it"
        )


def _check_the_slots_a_reader_fills_leave_here_empty(
    where: str, skeleton: Mapping,
) -> None:
    """The part of a parameter ask that is not a statement but a blank.

    The rule above reads WHICH parameter the ask is about, which is every
    field of the stub except the two the ask exists for. Those two are
    read here, and they are read for being empty: this system raised the
    ask because it does not have the number, and it cannot have a source
    for a number nobody has taken.

    Both fields are spoken for in the other direction, where the patch
    comes back. That is what makes the silence here a half rather than an
    omission — one record, two directions, a rule on one of them. An ask
    that leaves with a value in it hands a reader a form they return
    unchanged, and this system's own figure arrives back as their
    measurement; an ask that leaves with a source in it puts a provenance
    under that figure that nobody wrote.

    The source is asked once, not twice. Bent, blanked or replaced by a
    sentence that reads like a real citation are one thing to this rule —
    not the word that says the field is still blank — and the return
    door's own rule about the source is narrower than that: it refuses an
    empty one only where the value is declared an LLM prior. So the
    sentence a refusal gives is about the ask, which is what this side
    knows.

    Only the two fields are read, and only for what is in them. Whether
    the value field is THERE is the contract's question and the contract
    answers it — the stub's schema requires it — so asking again here
    would be a branch no door can reach. The source field is the other
    way round: the schema types the annotations free-form and requires
    nothing inside them, which is why an absent source is refused here
    and an absent value is not.
    """
    value = skeleton.get("value")
    if value is not None:
        _reject(
            f"{where} hands a reader a stub with {value!r} "
            f"already written in as the value; this ask exists because "
            f"nobody has that number, and the stub goes back through the "
            f"patch door verbatim, so a reader who returns it unchanged "
            f"returns this system's own figure as their measurement"
        )
    annotations = skeleton.get("annotations")
    source = (annotations.get("source")
              if isinstance(annotations, Mapping) else None)
    if source != _A_SOURCE_NOBODY_HAS_YET:
        _reject(
            f"{where} hands a reader a stub whose source reads {source!r}; "
            f"this system is asking for the number rather than reporting "
            f"it, so the one thing it can write there is the word saying "
            f"the field is still blank. The stub goes back through the "
            f"patch door verbatim, so anything else is a provenance the "
            f"reader did not write, filed under a figure they supplied"
        )


def _check_an_edge_the_item_spells_out(where: str, said: Mapping,
                                       target: str) -> None:
    """An item with no patch may still name the two ends of an edge.

    Its target spells the edge out, so the ends are readable from it.
    Emptiness is asked first for the reason above: ``"" in anything``.
    """
    for key in ("child", "parent"):
        value = said.get(key)
        if value is None:
            continue
        if not str(value).strip():
            _reject(
                f"{where} names the {key} of the edge it asks about and "
                f"puts nothing there"
            )
        if str(value) not in target:
            _reject(
                f"{where} says the {key} of the edge it asks about is "
                f"{value!r}, and the edge it asks about is {target!r}"
            )


def _check_the_heading_describes_the_items(
    where: str, request: Mapping, items: list, missing: Mapping,
) -> None:
    """A request's own four fields, against the items under them.

    The heading is not a fifth thing a reader is told; it is the items
    said shortly. ``push`` writes every field of it out of them — the
    action from the channel, the target from the one item or from how
    many there are, the note from what they share, the priority from the
    strongest — so each field has a second record already on the envelope
    and none of them needed a new one. What was missing is that anybody read them: the rule below this
    one descends into ``items`` on its first line, and the single heading
    field it does touch, ``group``, it reads as the input to a branch.
    A label read as an input cannot be wrong.
    """
    action, group = request.get("action"), request.get("group")
    rows = [missing.get(item.get("target")) for item in items
            if isinstance(item, Mapping)]
    theirs = [row for row in rows if isinstance(row, Mapping)]
    if isinstance(group, str) and items and len(theirs) == len(items):
        kinds = {row.get("kind") for row in theirs}
        if kinds != {group}:
            _reject(
                f"{where} is filed under {group!r} and what it holds is "
                f"{sorted(k for k in kinds if k)}; a request is one "
                f"channel, and a reader repairs it through the wrong one"
            )
    if isinstance(group, str):
        wanted = _ACTION_FOR_GROUP.get(group)
        if wanted is None:
            _reject(
                f"{where} files a reader's ask under {group!r}, which is "
                f"not one of the repair channels; a reader sorting by "
                f"channel never sees this ask"
            )
        if action != wanted:
            _reject(
                f"{where} is a {group!r} ask and tells a reader to "
                f"{action!r}; that channel is repaired by {wanted!r}, and "
                f"the two names on this row are for one channel"
            )

    target = request.get("target")
    if isinstance(target, str) and items:
        if not target.strip():
            _reject(
                f"{where} heads a reader's list with nothing; the heading "
                f"is how the list is found and referred to"
            )
        if len(items) == 1:
            only = items[0].get("target") if isinstance(items[0], Mapping) \
                else None
            if isinstance(only, str) and target != only:
                _reject(
                    f"{where} is one ask, recorded as {target!r}, and the "
                    f"ask under it is for {only!r}; a reader looking it up "
                    f"by the name they were given finds a different one"
                )
        else:
            # Restated whole, not read for its count. A sentence a reader
            # is shown keeps the right to be spelled differently, and the
            # rule above about a patch's fields is written that way for
            # that reason; this is not one. It is a summary two functions
            # in the runtime write to one format, and a third site writing
            # it by hand is how the same request comes to have two names
            # depending on which pass touched it. Pinned to that format by
            # a test, so a producer changing it arrives as a red suite.
            #
            # Two spellings of the prefix, because the row names its
            # channel twice and the framing pass uses the other name. That
            # is not laxity: which two words those are is fixed by the
            # action-to-group table checked above, so this says "the
            # heading names THIS channel" and nothing wider.
            spellings = {f"{name}:{len(items)}_items"
                         for name in (group, action) if isinstance(name, str)}
            if spellings and target not in spellings:
                _reject(
                    f"{where} heads a reader's list with {target!r}; the "
                    f"list under it is {len(items)} asks in the {group!r} "
                    f"channel, which is written {sorted(spellings)}"
                )

    priority = request.get("priority")
    if not isinstance(priority, str):
        return
    if group == _FRAMING_GROUP:
        if priority != _FRAMING_PRIORITY:
            _reject(
                f"{where} is a framing ask filed as {priority!r}; framing "
                f"asks are filed at {_FRAMING_PRIORITY!r}, and a reader "
                f"working down by priority meets this one out of turn"
            )
        return
    graded = [rank for row in theirs
              if isinstance(rank := row.get("priority"), str)
              and rank in _PRIORITY_ORDER]
    if not graded or len(graded) != len(items):
        return          # no second record of what these items are worth
    strongest = max(graded, key=_PRIORITY_ORDER.index)
    if priority != strongest:
        _reject(
            f"{where} is filed at {priority!r} and the asks under it are "
            f"{sorted(set(graded))}; a group is as urgent as the most "
            f"urgent thing in it"
        )


def _check_the_note_is_what_the_items_share(
    where: str, request: Mapping, items: list,
) -> None:
    """The heading field that says what the asks under it have in common.

    ``summarise`` writes it out of the items as it writes the other
    fields: one ask's species and occasion when there is one ask; when
    there are several, the one mapping every ask carrying a species
    shares, and nothing when they differ. Nothing read it. A request
    could say its asks needed one thing over asks needing another, and
    on an answer whose ``missing_information`` the number path removed,
    the note was a record of the need that nothing was compared with.

    Restated rather than imported, for the reason the channel table is.
    """
    carried = [_gaps.carried(item) for item in items]
    if not carried:
        return
    if len(carried) == 1:
        owed = carried[0]
    else:
        distinct: list = []
        for one in carried:
            if one and one not in distinct:
                distinct.append(one)
        owed = distinct[0] if len(distinct) == 1 else None
    note = request.get("note")
    if note != owed:
        _reject(
            f"{where} sums up the asks under it as {note!r}, and what "
            f"those asks carry comes to {owed!r}; a heading is its items "
            f"said shortly, so this one tells a reader they need "
            f"something none of them says"
        )


#: What both renderings of one missing item carry. ``observable`` and
#: ``skeleton`` are deliberately not here: each surface carries what its
#: own reader needs, and a field only one of them has is not a second
#: record of anything. These five are on both, so each is the other's.
_BOTH_RENDERINGS_CARRY = ("gap", "need", "said", "words",
                          "superseded_by_estimation")


def _check_the_two_renderings_agree(
    where: str, item: Mapping, row: Mapping, group: Any,
) -> None:
    """One missing item, written on the envelope twice.

    ``missing_information`` and ``investigation_requests`` are two
    renderings of the same tuple — the requests are pushed from the very
    items the first block lists — so wherever a row and an item are the
    same item, the fields both carry are one fact written twice. Nothing
    had ever compared them, which is what let a reader be told one species
    in the list of what is missing and another in the list of what to go
    and do about it.

    The row's ``kind`` is the channel, and the request that holds this
    item names that channel too.
    """
    for field in _BOTH_RENDERINGS_CARRY:
        mine, theirs = item.get(field), row.get(field)
        if mine is None or theirs is None:
            continue
        if mine != theirs:
            _reject(
                f"{where} says its {field} is {mine!r} and the same ask "
                f"listed under missing_information says {theirs!r}; a "
                f"reader meets one of these in the list of what is short "
                f"and the other in the list of what to do about it"
            )
    kind = row.get("kind")
    if isinstance(kind, str) and isinstance(group, str) and kind != group:
        _reject(
            f"{where} is filed in the {group!r} channel and the ask it "
            f"stands for is listed as a {kind!r} one; the two lists send a "
            f"reader down different routes for one missing thing"
        )


def _check_the_gap_it_names_is_in_the_report(
    where: str, item: Mapping, kinds: frozenset[str],
) -> None:
    """The one field on an item that is a REFERENCE rather than a copy.

    Everything else this module holds is two records of one fact agreeing,
    and that only works where both records are there: the check above is
    silent for an item ``missing_information`` has no row for, which is
    every framing ask and some of the rest. ``gap`` does not need a second
    record. It names a species in the report on the same envelope, and
    whether that species is there is not an opinion.

    Asked of the report's own list rather than of the roster of species
    that exist, because the claim is not "this is a gap kind" — the schema
    settles that — but "this is one of the gaps THIS answer found". An ask
    naming a species the report does not carry sends a reader to supply
    something for a problem this answer never reported having, and the gap
    it really came from goes unattributed in the same stroke.
    """
    named = item.get("gap")
    if not isinstance(named, str) or named in kinds:
        return
    _reject(
        f"{where} tells a reader to go and supply something to close a "
        f"{named!r} gap, and this answer's report does not carry one — it "
        f"reports {sorted(kinds) or 'no gaps at all'}. The reader is sent "
        f"after a problem the answer never said it had, and whatever gap "
        f"the ask really came from is left with nothing pointing at it"
    )


def _check_it_names_the_species_its_need_raises(where: str, item: Mapping
                                                ) -> None:
    """And WHICH species, which the ask's own need already settles.

    The check above asks whether the named species is one this answer
    reported, and that is all a reference to a list can be asked on its
    own: an ask pointed at another gap the report really does carry sends
    a reader to collect something for a problem that is on the envelope,
    and no reading of the report alone can tell that from the truth.

    It is not on its own. An item says what was NEEDED, and a need
    declares the channel that repairs it — ``Need.gap``, on the member
    rather than at the sites that raise it, so that a site cannot file a
    need under a kind that contradicts it. That constrains the producer
    and nothing was holding the envelope to it, so the relation the
    contract states was a relation no answer had to honour.

    Read off the contract's own member rather than gathered from the
    corpus: a need this build has never raised is held to the same
    sentence as the ones it raises daily.
    """
    named, need = item.get("gap"), item.get("need")
    if not isinstance(named, str) or not isinstance(need, str):
        return
    declared = _gaps.BY_NAME.get(need)
    if declared is None:
        # A word outside the vocabulary is refused by the schema the door
        # validates against, before any rule here reads it.
        return
    if named == declared.gap.value:
        return
    _reject(
        f"{where} says what it needed is {need!r} and points a reader at a "
        f"{named!r} gap, and a {need!r} is repaired through a "
        f"{declared.gap.value!r} one. The species is the CHANNEL that "
        f"closes the need, so an ask pointed at another gap on the same "
        f"report sends a reader to collect something that would not close "
        f"this one — and the gap it really came from is left with nothing "
        f"pointing at it"
    )


#: The names a parameter key mentions: whatever stands immediately before
#: an "=" inside it. A narrow reading of one grammar, stated rather than
#: inferred, and pinned by a test that reproduces every corpus row's
#: ``observable.variables`` from its own key — so a key whose grammar
#: moved fails loudly instead of being under-read into silence.
_NAMES_IN_A_KEY = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\s*=")


def _check_the_row_says_one_thing_three_times(where: str, row: Mapping) -> None:
    """One missing parameter, rendered three ways on its own row.

    A row that names a parameter carries the same fact in three places: the
    key itself, the ``name`` this row is filed under, and the variables an
    analyst has to observe to supply it. They are one fact, so they agree
    or one of them is wrong, and a reader who acts on the wrong one goes
    and collects the wrong table.

    ``name`` is also the KEY this block is indexed by:
    :func:`verify_investigation_items` resolves each ask's ``target``
    against it, and that resolution is silent when it misses. So a moved
    name is not only unnoticed on its own account — it quietly switches off
    the agreement check for the ask pointing at it. Holding the name to the
    key beside it is what stops one edit from disabling another rule.

    Silent where there is no key: not every channel files one, and a row
    without one is not a row that disagrees with itself.
    """
    said = row.get("said")
    key = said.get("key") if isinstance(said, Mapping) else None
    if not isinstance(key, str) or not key:
        return

    name = row.get("name")
    if isinstance(name, str) and not name.endswith(f":{key}"):
        _reject(
            f"{where} is filed under the name {name!r} and the parameter it "
            f"is short of is {key!r}; the name is what an ask's target "
            f"resolves against, so the two disagreeing sends a reader to "
            f"collect one table under the heading of another"
        )

    observable = row.get("observable")
    shown = observable.get("variables") if isinstance(observable, Mapping) else None
    if not isinstance(shown, list):
        return
    mentioned = set(_NAMES_IN_A_KEY.findall(key))
    if not mentioned:
        return
    if set(shown) != mentioned:
        _reject(
            f"{where} says a reader must observe {sorted(shown)} to supply "
            f"{key!r}, and that parameter is over {sorted(mentioned)}; the "
            f"list of what to go and measure is the one thing on this row a "
            f"reader acts on directly"
        )


def _check_the_name_this_row_is_filed_under(
    where: str, row: Mapping,
) -> None:
    """The heading a shortfall is filed under, and what it says there.

    A name is a pair: the channel that repairs the shortfall, and what in
    particular is short. Which half the species settles and which the
    occasion does is declared beside the species in ``themis.gaps``, and
    the channel is recomputed from there rather than read off the row —
    because a channel the row carries for itself can disagree with the
    species in the field beside it, and one species was filed under two
    channels across seven sites without a stored answer able to show it.

    The subject half is the occasion's, so there is nothing here to
    rebuild it from. What holds that half is
    :func:`_check_every_row_is_named_by_an_ask`, below and last, because
    it is a fact about both lists rather than about this row.

    Silent where the row names no species: what a row with no species is
    filed under is not a question this declaration answers.
    """
    need = row.get("need")
    if not isinstance(need, str):
        return
    species = _gaps.BY_NAME.get(need)
    if species is None:
        # As for an ask's species: a word outside the vocabulary is
        # refused by the schema the door validates against, before this.
        return
    name = row.get("name")
    if not isinstance(name, str) or not name:
        _reject(
            f"{where} is a shortfall filed under {name!r}; the name is the "
            f"key this row is indexed by and the target an ask resolves "
            f"against, so a row without one is a row nothing on the "
            f"reader's list can be pointed at"
        )
    if species in _gaps.FILES_NO_ROW:
        _reject(
            f"{where} files a {need!r} shortfall and that species files "
            f"none: {_gaps.FILES_NO_ROW[species]}"
        )
    head, colon, subject = name.partition(":")
    whole = _gaps.FILED_WHOLE.get(species)
    if whole is not None and name != whole:
        _reject(
            f"{where} files a {need!r} shortfall under {name!r}, and that "
            f"species is filed whole under {whole!r}; it carries nothing "
            f"of the occasion that raised it, so every raising is the same "
            f"row and there is no second name for one of them to be under"
        )
    channel = _gaps.FILED_UNDER.get(species)
    if channel is not None and (head != channel or not subject):
        _reject(
            f"{where} files a {need!r} shortfall under {name!r}; that "
            f"species is repaired through the {channel!r} channel, and "
            f"what follows it is what in particular is short. A name "
            f"shaped otherwise files this row under a heading nothing "
            f"else on the envelope uses, and the ask pointing at it "
            f"resolves against nothing"
        )
    about = _gaps.FILED_ABOUT.get(species)
    if about is not None and (not head or not colon or subject != about):
        _reject(
            f"{where} files a {need!r} shortfall under {name!r}; the "
            f"caller names the channel for this species and what it is "
            f"about is the species' own, {about!r}. A subject that is not "
            f"that one is this row claiming to be about something the "
            f"species it names cannot be about"
        )


def _check_every_row_is_named_by_an_ask(
    result: Mapping, asked: frozenset,
) -> None:
    """The two lists a reader is handed, against each other.

    ``missing_information`` says what is short and
    ``investigation_requests`` says what to go and do about it, and the
    second is pushed from the first: an ask carries the row's name over as
    its target. So every row is named by an ask, and one that is not is a
    row the reader's list does not reach — a name that moved after the ask
    was built, which also switches off the checks on that ask, or a
    shortfall nobody is ever told about. That second failure is the one
    :func:`_check_the_row_says_one_thing_three_times` describes in its own
    docstring and could only see where a parameter key stood beside it.

    Last, after every rule that reads a single ask. Those say what one
    item is wrong about; this can only say the two lists no longer line
    up, and a reader shown the narrower sentence does not have to work out
    which of the two moved.

    Two spellings answer, because two producers write asks: the pusher
    carries the whole name, and the framing channel writes its item
    directly and puts the subject there without the channel. Narrowing
    that to one would be a decision about what a framing ask's target is,
    which is the ask's field and not the row's.
    """
    for mi, row in enumerate(result.get("missing_information") or ()):
        if not isinstance(row, Mapping):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        if name in asked or name.partition(":")[2] in asked:
            continue
        _reject(
            f"missing_information[{mi}] is filed under {name!r} and no ask "
            f"on this envelope names it; every row is pushed into an ask "
            f"that carries this name over as its target, so a row no ask "
            f"reaches is either a name that moved after the ask was built "
            f"— which silently switches off the checks on that ask — or a "
            f"shortfall the reader is never told about"
        )


def _skeleton_atoms(node: Any, out: list) -> list:
    """Every atom in a skeleton, as the envelope spells them.

    A skeleton's atoms carry no ``kind`` marker — they are bare
    ``{predicate, args}`` objects — so a walk keying on ``kind == "atom"``
    finds none of them and reports perfect coverage of an empty set.
    """
    if isinstance(node, Mapping):
        if isinstance(node.get("predicate"), str) and "args" in node:
            args = node.get("args")
            out.append((node["predicate"], tuple(
                a.get("name") for a in args if isinstance(a, Mapping))
                if isinstance(args, list) else ()))
            return out
        for value in node.values():
            _skeleton_atoms(value, out)
    elif isinstance(node, list):
        for value in node:
            _skeleton_atoms(value, out)
    return out


def _check_the_skeleton_names_variables_that_exist(
    where: str, skeleton: Any, named: frozenset,
) -> None:
    """The variables a reader is sent to go and measure.

    This is the most literally actionable thing on the envelope: somebody
    reads it and collects data. A skeleton naming ``survival(nobody)``
    sends them after a unit the problem never had.

    An atom is its arguments as much as its predicate, which is why the
    roster is atoms and not names — asking a predicate roster accepts any
    argument at all for as long as the predicate is mentioned somewhere,
    and the argument is the whole of what makes it a unit.

    Silent on a skeleton that names a predicate WITHOUT arguments: a
    variable patch's whole purpose is to introduce a variable the program
    does not have yet, and refusing that would refuse the one ask that
    exists to widen the problem.
    """
    if not isinstance(skeleton, Mapping) or not skeleton:
        return
    for key in _skeleton_atoms(skeleton, []):
        if key in named:
            continue
        spelt = f"{key[0]}({','.join(str(a) for a in key[1])})"
        _reject(
            f"{where} tells a reader to go and measure {spelt}, and this "
            f"problem names no such variable; the skeleton is the part of "
            f"an ask somebody actually collects data against, so a unit "
            f"that is not there sends them after nothing"
        )


def _valued_atoms_of(node: Any, out: list) -> list:
    """Every ``{atom, value}`` pair a skeleton states, at any depth.

    The pair and not the two halves: which variable is being asked about
    and which of its values is the same statement, and a value is only
    judgeable next to the variable it belongs to.
    """
    if isinstance(node, Mapping):
        inner = node.get("atom")
        if isinstance(inner, Mapping) and "value" in node \
                and isinstance(inner.get("predicate"), str):
            out.append((inner["predicate"], node["value"]))
            return out
        for value in node.values():
            _valued_atoms_of(value, out)
    elif isinstance(node, list):
        for value in node:
            _valued_atoms_of(value, out)
    return out


def _check_the_values_it_asks_about_are_ones_the_variable_takes(
    where: str, skeleton: Any, declared: Mapping,
) -> None:
    """The literal beside the variable, held to that variable's domain.

    The check above says the reader is being sent after a variable that
    exists. This says they are being asked for a value it can actually
    take. ``P(survival=42)`` names a real variable and asks a question
    nobody can answer, and somebody would go and look for it.

    Silent where the variable declares no domain — a problem written
    entirely out of cause edges declares nothing while naming everything,
    and there is then no authority here to appeal to. That is a genuine
    limit rather than a convenience: 143 of the corpus's 193 value sites
    have a domain to be held to and 50 do not, and inventing one from the
    values the corpus happens to use would be reading the roster off the
    answers it is meant to judge.
    """
    if not isinstance(skeleton, Mapping) or not skeleton:
        return
    for predicate, value in _valued_atoms_of(skeleton, []):
        declaration = declared.get(predicate)
        domain = getattr(declaration, "domain", None) if declaration else None
        if not domain:
            continue
        if any(member == value for member in domain):
            continue
        _reject(
            f"{where} asks a reader to record {predicate} = {value!r}, and "
            f"this problem declares {predicate} to take one of "
            f"{list(domain)}; nobody can come back with a value the "
            f"variable does not have"
        )


def verify_investigation_items(result: Mapping, program: Any) -> None:
    """Hold each item on the reader's list to the records beside it.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` when an item would
    send a reader to supply something other than what is missing.
    """
    requests = result.get("investigation_requests") or ()
    if not requests:
        return
    notes = {
        note.get("predicate")
        for note in result.get("framing_notes") or ()
        if isinstance(note, Mapping)
    }
    #: The same MissingItem tuple these requests were pushed from, as the
    #: envelope renders it. Not every request has rows here — a framing
    #: ask never does, and some channels file one without — so it answers
    #: where it answers and the heading rule is silent where it does not.
    missing = {
        row.get("name"): row
        for row in result.get("missing_information") or ()
        if isinstance(row, Mapping)
    }
    #: What the asks name. A row's name is the key those asks resolve
    #: against, so this is the other side of the dict above: the one that
    #: says whether anything on the reader's list reaches a given row.
    asked = frozenset(
        target
        for request in requests if isinstance(request, Mapping)
        for item in request.get("items") or ()
        if isinstance(item, Mapping)
        and isinstance(target := item.get("target"), str)
    )
    for mi, row in enumerate(result.get("missing_information") or ()):
        if isinstance(row, Mapping):
            # The narrower one first. Both hold the name, and where a
            # parameter key stands beside it that rule can name the
            # record the name disagrees with; this one can only say the
            # heading is wrong. A reader who is told which parameter is
            # under which heading does not have to go and diff the row.
            _check_the_row_says_one_thing_three_times(
                f"missing_information[{mi}]", row)
            _check_the_name_this_row_is_filed_under(
                f"missing_information[{mi}]", row)
    #: The species this answer's own report says it found. ``None`` where
    #: there is no report to ask — an answer that reported nothing is not
    #: an answer whose asks point at the wrong thing, and telling those two
    #: apart is what the block above this one is for.
    report = result.get("data_gap_report")
    kinds: frozenset[str] | None = None
    if isinstance(report, Mapping) and isinstance(report.get("gaps"), list):
        kinds = frozenset(
            kind for gap in report["gaps"] if isinstance(gap, Mapping)
            and isinstance(kind := gap.get("kind"), str))
    declared = declarations_of(program)
    named = predicates_of(program)
    #: The same question one level finer, for the skeletons below: which
    #: VARIABLES this problem names, arguments and all. The predicate
    #: roster cannot tell x(u) from x(nobody), and the difference is the
    #: unit somebody is being sent to collect data on.
    variables = variables_named_by(program)
    for ri, request in enumerate(requests):
        if not isinstance(request, Mapping):
            continue
        group = request.get("group")
        _check_the_heading_describes_the_items(
            f"investigation_requests[{ri}]", request,
            [i for i in request.get("items") or () if isinstance(i, Mapping)],
            missing)
        for ii, item in enumerate(request.get("items") or ()):
            if not isinstance(item, Mapping):
                continue
            where = f"investigation_requests[{ri}].items[{ii}]"
            target = item.get("target")
            if not isinstance(target, str) or not target.strip():
                _reject(
                    f"{where} tells a reader to go and supply something "
                    f"and names it {target!r}; an item with no target is "
                    f"an ask with nothing asked for"
                )
            # Before any branch below, because the two renderings agree or
            # they do not whatever kind of patch this ask carries — and
            # every branch below this line ends in a ``continue``.
            row = missing.get(target)
            if isinstance(row, Mapping):
                _check_the_two_renderings_agree(where, item, row, group)
            if kinds is not None:
                _check_the_gap_it_names_is_in_the_report(where, item, kinds)
            # Whether or not the report is here to be read: which species
            # an ask points at is settled by the ask's own need, and that
            # is a question about the item alone.
            _check_it_names_the_species_its_need_raises(where, item)
            said = item.get("said")
            said = said if isinstance(said, Mapping) else {}
            skeleton = item.get("skeleton")
            # Before the branch on kind, because a skeleton naming a
            # variable nobody has is wrong whichever kind it is, and every
            # branch below this line ends in a ``continue``.
            _check_the_skeleton_names_variables_that_exist(
                where, skeleton, variables)
            _check_the_values_it_asks_about_are_ones_the_variable_takes(
                where, skeleton, declared)
            if not isinstance(skeleton, Mapping) or not skeleton:
                _check_an_edge_the_item_spells_out(where, said, target)
                continue
            kind = skeleton.get("kind")
            if kind not in _SKELETON_KINDS:
                _reject(
                    f"{where} hands a reader a patch of kind {kind!r}; "
                    f"the door it goes back through takes "
                    f"{sorted(_SKELETON_KINDS)}, and a patch that door "
                    f"cannot read is an ask nobody can answer"
                )
            if kind == _PROBABILITY:
                _check_a_parameter_the_reader_is_asked_for(
                    where, skeleton, said, target)
                _check_the_slots_a_reader_fills_leave_here_empty(
                    where, skeleton)
                continue
            _check_the_predicate_is_written_once(where, item, said, target)
            if group == "framing" and target not in notes:
                _reject(
                    f"{where} is a framing ask about {target!r} and no "
                    f"framing_note says so; that note is the only reason "
                    f"a framing item is exempt from having to be cited "
                    f"by a gap, so without it the item is held by nothing"
                )
            declaration = declared.get(target)
            if declaration is None:
                _reject(
                    f"{where} hands a reader a patch for {target!r}, "
                    f"which this program does not declare; the patch goes "
                    f"back through a door that would not know the name"
                )
            unfilled = _unfilled_fields(where, skeleton, declaration)
            _check_what_the_patch_says_is_already_known(
                where, skeleton, declaration)
            _check_the_sentence_counts_what_the_patch_leaves(
                where, said, unfilled)
        # After the asks, not with the rest of the heading: a note copies
        # what its asks carry, so a lie told on an ask makes the note
        # disagree too, and the reader should be told about the ask.
        _check_the_note_is_what_the_items_share(
            f"investigation_requests[{ri}]", request,
            [i for i in request.get("items") or () if isinstance(i, Mapping)])
    # After every ask has been read, for the reason that rule gives: it is
    # the widest thing that can be wrong here, and standing in front of the
    # narrower ones it would answer a question nobody asked.
    _check_every_row_is_named_by_an_ask(result, asked)
