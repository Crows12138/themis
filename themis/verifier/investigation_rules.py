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

So this module restates three things: the set of skeleton KINDS, because
it decides which question an item can be asked at all; the channel table,
because a request names its channel twice and the two names must be for
one channel; and the format of a grouped heading, because that format is
written by two runtime functions from one definition rather than being
any site's private spelling. Each is compared to its producer by a test.
Everything else is "do these two records of one fact agree", and the
record it asks of the program is the strongest, because the program is
not the answer's to write.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Iterable, Mapping, NoReturn

from ..types import VariableDeclaration
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


def _atoms_a_probability_names(skeleton: Mapping) -> Iterable[Mapping]:
    target = skeleton.get("target")
    if isinstance(target, Mapping):
        yield target
    for given in skeleton.get("given") or ():
        if isinstance(given, Mapping):
            yield given


def _check_a_parameter_the_reader_is_asked_for(
    where: str, skeleton: Mapping, said: Mapping, target: str,
    named: frozenset[str],
) -> None:
    """A probability skeleton, held to the two things beside it.

    The sentence quotes a ``key`` and the item's target ends with it, so
    the two are one record read twice rather than reassembled from a
    prefix this module would then own. And the distribution is over
    predicates, which the program is the authority on.

    The authority is which predicates the program NAMES, not which ones it
    declares. This asked the declaration table, and refused an ask for a
    distribution over a variable a graph introduces through a cause edge —
    a program with no ``variable`` statement at all declares nothing and
    names everything, and the door the patch goes back through takes such
    a patch without complaint. What is left to catch is the ask a reader
    cannot place at all: a name this program has never written down.
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
    for atom in _atoms_a_probability_names(skeleton):
        inner = atom.get("atom")
        predicate = inner.get("predicate") if isinstance(inner, Mapping) \
            else None
        if predicate is None:
            continue
        if predicate not in named:
            _reject(
                f"{where} asks a reader for a distribution over "
                f"{predicate!r}, which this program never names"
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
    many there are, the priority from the strongest — so each field has a
    second record already on the envelope and none of them needed a new
    one. What was missing is that anybody read them: the rule below this
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
            said = item.get("said")
            said = said if isinstance(said, Mapping) else {}
            skeleton = item.get("skeleton")
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
                    where, skeleton, said, target, named)
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
