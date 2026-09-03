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

So the one table this module restates is the set of skeleton KINDS, and
it restates it because that set decides which question an item can be
asked at all. Everything else is "do these two records of one fact
agree", and the record it asks of the program is the strongest, because
the program is not the answer's to write.
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
    declared = declarations_of(program)
    named = predicates_of(program)
    for ri, request in enumerate(requests):
        if not isinstance(request, Mapping):
            continue
        group = request.get("group")
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
