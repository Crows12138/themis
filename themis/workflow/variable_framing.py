"""Variable framing fill-back workflow (slice A1).

Symmetric counterpart of ``parameter_fill`` but operating on advisory
``framing_notes`` instead of ``missing_information``:

1. ``extract_framing_skeleton(program, results)`` — collect one patch
   per predicate that carries unset framing fields. Reads ``results``
   for the gap list and ``program`` for the predicate's already-set
   fields, so each patch exposes existing metadata as read-only
   context alongside the null-valued fill surface.

2. ``merge_variable_declaration(program, filled_bundle)`` — update
   each referenced predicate's existing ``VariableDeclaration`` in
   place. Patches never create a second declaration (the
   ``unique_variable_declarations`` semantic check would reject that
   anyway) and never overwrite a field that was already set — if the
   patch supplies a value that conflicts with the program's existing
   value, merge raises ``VariablePatchConflictError``.

3. ``diff_framing_runs(before, after)`` — confirm each predicate's
   gap set either strictly shrank or vanished, and simultaneously
   assert that framing is still advisory: ``status`` / numeric value
   / confidence of every query must be unchanged across the run.

Bundle shape (emitted by ``extract_framing_skeleton``):

    {
      "version": "0.1",
      "kind": "framing_skeleton_bundle",
      "patches": [
        {
          "kind": "variable_patch",
          "predicate": "waist_reduced",
          "existing": { "domain": [true, false] },
          "fields": {
            "time_window": null,
            "measurement": null,
            "threshold": null,
            "observability": null
          }
        },
        ...
      ]
    }

``existing`` is display-only; merge never reads it. Fills happen in
``fields`` — any ``null`` remaining after editing is simply ignored
(partial fills are allowed and show up as surviving notes in the
next run).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Iterable

from .bundle import (
    VERSION as BUNDLE_VERSION,
    MalformedBundleError,
    Refuses,
    envelope,
)
from .. import framing
from .. import language
from ..shape_words import Shape
from ..types import (
    FramingNote,
    InvestigationAction,
    Program,
    QueryResult,
    Statement,
    VariableDeclaration,
)

#: This bundle kind's name, the key its records live under, and the
#: kind each record carries. The version beside them belongs to the
#: envelope rather than to either kind, and is imported from there.
BUNDLE_KIND = "framing_skeleton_bundle"
BUNDLE_RECORDS = "patches"
PATCH_KIND = "variable_patch"

# Fields a variable_patch may legally carry: every framing field, plus the
# one that names them rather than carrying a value of its own — which is
# how a surface says "the author left these blank and took the standard
# operationalisation" without inventing a value to write in their name.
# Its fill rule is a union rather than a write, which is why it is spelled
# out here rather than folded into the table.
#
# That "plus one" is the whole of the difference between this list and the
# fields a skeleton displays, and the two used to be separate tuples with a
# note asking a person to keep them level. Written as an expression, the
# difference is the thing that varies and nothing else can drift.
_PATCHABLE_FIELDS: tuple[str, ...] = framing.names() + (
    framing.NAMES_THE_DEFAULTED,)

#: The framing fields ``defaulted`` may name.
_DEFAULTABLE_FIELDS: frozenset[str] = frozenset(framing.defaultable())


# ---------------------------------------------------------- errors

class UnknownPredicateError(language.Voiced, ValueError):
    """Patch targets a predicate without an existing VariableDeclaration.

    A patch is a *patch*, not a declaration — authors who want to
    introduce a new predicate should write a ``variableDeclaration``
    directly rather than route it through the framing loop.
    """

    def __init__(self, predicate: str) -> None:
        super().__init__(Refuses.NO_DECLARATION_TO_PATCH,
                         predicate=predicate)
        self.predicate = predicate


class VariablePatchConflictError(language.Voiced, ValueError):
    """Patch tries to set a field that is already set in the program
    to a *different* value. Framing is meant to *fill* gaps, not to
    rewrite existing metadata — overwrite must be explicit (edit the
    declaration directly)."""

    def __init__(self, predicate: str, field: str, existing,
                 incoming) -> None:
        super().__init__(Refuses.FIELD_IS_ALREADY_SET_DIFFERENTLY,
                         predicate=predicate, field=field,
                         existing=existing, incoming=incoming)
        self.predicate = predicate
        self.field = field
        self.existing = existing
        self.incoming = incoming


class VariablePatchAnsweredTwiceError(language.Voiced, ValueError):
    """A patch both names a field's value and lists it as defaulted.

    Those are two different answers to one question — "here is what it
    means" and "whatever the standard one is" — and a declaration that
    carried both would leave every reader of it to pick. Rejected at the
    channel rather than resolved by precedence, because which of the two
    the author meant is not something this layer can know.
    """

    def __init__(self, predicate: str, field: str) -> None:
        super().__init__(Refuses.FIELD_IS_ANSWERED_TWICE,
                         predicate=predicate, field=field)
        self.predicate = predicate
        self.field = field


# --------------------------------------------------------- helpers

def _declarations_by_predicate(program: Program) -> dict[str, VariableDeclaration]:
    idx: dict[str, VariableDeclaration] = {}
    for s in program.statements:
        if isinstance(s, VariableDeclaration):
            idx[s.predicate] = s
    return idx


#: JSON-ish view of what the author has already settled, shown as
#: read-only context on each patch. One function rather than this
#: module's own: ``framing_check`` had grown the same walk for the same
#: purpose, and the two agreed on every declaration anyone tried, which
#: is what a copied list does to the loop that reads it.
_existing_view = framing.settled


# ---------------------------------------------------------- extract

def extract_framing_skeleton(
    program: Program,
    results: Iterable[QueryResult],
) -> dict:
    """Build a patch bundle from all framing gaps across ``results``.

    Dedupe is by predicate — even if several queries reference the
    same underspecified predicate, the bundle carries one patch. The
    patch's ``fields`` dict lists only the gap fields (each ``null``)
    so the author can fill them; ``existing`` shows already-set
    metadata as read-only context.

    Predicates without a ``VariableDeclaration`` in the program never
    appear (framing is opt-in per predicate — they produced no note
    to begin with).
    """
    decls = _declarations_by_predicate(program)

    seen: dict[str, list[str]] = {}  # predicate -> gap field list
    for r in results:
        for note in r.framing_notes:
            if note.predicate in seen:
                continue
            seen[note.predicate] = list(note.missing)

    patches: list[dict] = []
    for predicate, gaps in seen.items():
        decl = decls.get(predicate)
        # Should never happen: framing_notes only fire for declared
        # predicates. Skip defensively rather than raise.
        if decl is None:
            continue
        patches.append({
            "kind": PATCH_KIND,
            "predicate": predicate,
            "existing": _existing_view(decl),
            "fields": {field: None for field in gaps},
        })

    return {
        "version": BUNDLE_VERSION,
        "kind": BUNDLE_KIND,
        BUNDLE_RECORDS: patches,
    }


# ----------------------------------------------------------- extract (F1)

def extract_definition_skeleton(
    results: Iterable[QueryResult],
) -> dict:
    """Slice F1: build a framing_skeleton_bundle from
    ``DEFINE_VARIABLE`` investigation_requests on ``results``.

    Counterpart to ``extract_framing_skeleton`` that takes only results
    (no program). Each DEFINE_VARIABLE item's ``skeleton`` is already a
    complete variable_patch dict (built by the scheduler with access
    to the program at dispatch time), so this function is essentially
    a dedupe-by-predicate collector.

    The emitted bundle is shape-identical to
    ``extract_framing_skeleton``'s output, so the same
    ``merge_variable_declaration`` consumes either one unchanged.
    """
    seen: dict[str, dict] = {}
    for r in results:
        for request in r.investigation_requests:
            if request.action is not InvestigationAction.DEFINE_VARIABLE:
                continue
            for item in request.items:
                if item.skeleton is None:
                    continue
                predicate = item.skeleton.get("predicate")
                if not isinstance(predicate, str) or predicate in seen:
                    continue
                # Return an editable workflow artifact, not a live alias
                # into the original QueryResult tree.
                seen[predicate] = deepcopy(item.skeleton)

    return {
        "version": BUNDLE_VERSION,
        "kind": BUNDLE_KIND,
        BUNDLE_RECORDS: list(seen.values()),
    }


# ----------------------------------------------------------- merge

def _validate_bundle_shape(bundle: dict) -> list[dict]:
    """The envelope, then each patch in it.

    Only the second half is here: what a patch may say is this
    module's vocabulary and nothing else reads it, while the envelope
    around it is the same envelope the other bundle kind arrives in.
    """
    patches = envelope(bundle, kind=BUNDLE_KIND, key=BUNDLE_RECORDS)
    for i, p in enumerate(patches):
        at = f"{BUNDLE_RECORDS}[{i}]"
        if not isinstance(p, dict):
            raise MalformedBundleError(Refuses.IS_NOT, where=at,
                                       shape=Shape.DICT)
        if p.get("kind") != PATCH_KIND:
            raise MalformedBundleError(
                Refuses.KIND_IS_LIMITED_TO, where=at,
                kinds=[PATCH_KIND], got=p.get("kind"))
        if not isinstance(p.get("predicate"), str) or not p["predicate"]:
            raise MalformedBundleError(
                Refuses.IS_NOT, where=f"{at}.predicate",
                shape=Shape.NON_EMPTY_STRING)
        fields = p.get("fields", {})
        if not isinstance(fields, dict):
            raise MalformedBundleError(Refuses.IS_NOT,
                                       where=f"{at}.fields",
                                       shape=Shape.DICT)
        for key in fields:
            if key not in _PATCHABLE_FIELDS:
                raise MalformedBundleError(
                    Refuses.FIELD_IS_NOT_PATCHABLE,
                    where=f"{at}.fields", field=key,
                    legal=list(_PATCHABLE_FIELDS))
    return patches


def _apply_patch(
    decl: VariableDeclaration,
    patch: dict,
) -> VariableDeclaration:
    updates: dict = {}
    fields = patch.get("fields", {})
    for field, incoming in fields.items():
        if incoming is None:
            continue  # unfilled → leave gap for next iteration
        if field == "defaulted":
            continue  # a union over the whole patch, taken below
        existing = getattr(decl, field)
        if field == "domain" and isinstance(incoming, list):
            incoming = tuple(incoming)
        if existing is not None and existing != incoming:
            raise VariablePatchConflictError(
                predicate=decl.predicate,
                field=field,
                existing=existing,
                incoming=incoming,
            )
        # Either existing was None, or it matches — write the value.
        updates[field] = incoming

    # ``defaulted`` names fields instead of carrying a value, so it accrues
    # rather than being written: a later patch that defaults one more field
    # must not un-default the ones before it.
    named = _incoming_defaulted(decl.predicate, fields)
    for field in sorted(named):
        # Two answers to one question, arriving together or one on top of a
        # value already declared. Which was meant is not knowable here.
        if updates.get(field) is not None or getattr(decl, field) is not None:
            raise VariablePatchAnsweredTwiceError(decl.predicate, field)
    # Naming a value for a field defaulted earlier is the reader refining
    # what they took the standard reading of, which is the whole point of
    # the loop staying open — the value answers it now, so the name goes.
    merged = (named | frozenset(decl.defaulted)) - set(updates)
    if merged != frozenset(decl.defaulted):
        updates["defaulted"] = tuple(sorted(merged))

    if not updates:
        return decl
    return replace(decl, **updates)


def _incoming_defaulted(predicate: str, fields: dict) -> frozenset[str]:
    """The fields a patch declares answered by the standard operationalisation.

    Shape is checked here rather than in :func:`_validate_bundle_shape`
    because what is legal to name depends on the vocabulary of patchable
    fields, which is this module's own.
    """
    named = fields.get("defaulted")
    if named is None:
        return frozenset()
    at = f"{PATCH_KIND}[{predicate}].fields.defaulted"
    if not isinstance(named, (list, tuple)):
        raise MalformedBundleError(Refuses.IS_NOT, where=at,
                                   shape=Shape.LIST_OF_FIELD_NAMES)
    unknown = sorted(set(named) - _DEFAULTABLE_FIELDS)
    if unknown:
        raise MalformedBundleError(
            Refuses.NO_STANDARD_TO_TAKE, where=at, named=unknown,
            legal=sorted(_DEFAULTABLE_FIELDS))
    return frozenset(named)


def merge_variable_declaration(
    program: Program,
    filled_bundle: dict,
) -> Program:
    """Return a new Program with each patch applied to the matching
    existing ``VariableDeclaration``. Fills are strictly additive: a
    field that is already set cannot be changed through this channel.

    Unknown predicates raise ``UnknownPredicateError``. Conflicting
    fills raise ``VariablePatchConflictError``. A bundle with every
    patch completely unfilled returns the program unchanged — that's
    a valid no-op (the author opted to defer).
    """
    patches = _validate_bundle_shape(filled_bundle)
    decls = _declarations_by_predicate(program)

    # Plan replacements keyed by predicate first; apply after. This
    # keeps the statement-index walk linear and avoids the surprise
    # of having two patches for one predicate (bundle shouldn't but
    # we dedupe defensively).
    new_decls: dict[str, VariableDeclaration] = {}
    for patch in patches:
        predicate = patch["predicate"]
        decl = new_decls.get(predicate, decls.get(predicate))
        if decl is None:
            raise UnknownPredicateError(predicate)
        new_decls[predicate] = _apply_patch(decl, patch)

    if not new_decls:
        return program

    new_statements: list[Statement] = []
    for s in program.statements:
        if isinstance(s, VariableDeclaration) and s.predicate in new_decls:
            new_statements.append(new_decls[s.predicate])
        else:
            new_statements.append(s)
    return Program(
        version=program.version,
        objects=program.objects,
        statements=tuple(new_statements),
        extensions=program.extensions,
    )


# ------------------------------------------------------------ diff

def _gaps_by_predicate(results: Iterable[QueryResult]) -> dict[str, set[str]]:
    """Union the framing gaps across every result, keyed by predicate.
    Same predicate appearing in multiple queries collapses to one
    entry; gap fields merge by set union."""
    gaps: dict[str, set[str]] = {}
    for r in results:
        for note in r.framing_notes:
            gaps.setdefault(note.predicate, set()).update(note.missing)
    return gaps


def _query_row(r: QueryResult) -> dict[str, object]:
    row: dict[str, object] = {"query_id": r.query_id, "status": r.status.value}
    if r.numeric_result is not None:
        row["value"] = r.numeric_result.value
    if r.confidence is not None:
        row["confidence"] = r.confidence
    return row


def diff_framing_runs(
    before: Iterable[QueryResult],
    after: Iterable[QueryResult],
) -> dict:
    """Compare two runs and classify each predicate's framing gap
    transition, plus flag any query whose status / numeric value /
    confidence changed — those would violate the advisory contract.

    Returned shape:

        {
          "framing": {
            "resolved":   [{predicate, gaps_before}, ...],
            "shrunk":     [{predicate, gaps_before, gaps_after}, ...],
            "unchanged":  [{predicate, gaps}, ...],
            "grew":       [{predicate, gaps_before, gaps_after}, ...],
            "new":        [{predicate, gaps}, ...],
          },
          "value_drift": [
            {query_id, before: {...}, after: {...}},
            ...
          ],
        }

    ``value_drift`` should be empty in every well-behaved A0 run — if
    anything shows up there, framing leaked into the numeric layer.
    """
    before_list = list(before)
    after_list = list(after)

    before_gaps = _gaps_by_predicate(before_list)
    after_gaps = _gaps_by_predicate(after_list)

    resolved: list[dict] = []
    shrunk: list[dict] = []
    unchanged: list[dict] = []
    grew: list[dict] = []
    new: list[dict] = []

    for predicate, before_set in before_gaps.items():
        after_set = after_gaps.get(predicate, set())
        if not after_set:
            resolved.append({
                "predicate": predicate,
                "gaps_before": sorted(before_set),
            })
        elif after_set < before_set:
            shrunk.append({
                "predicate": predicate,
                "gaps_before": sorted(before_set),
                "gaps_after": sorted(after_set),
            })
        elif after_set == before_set:
            unchanged.append({
                "predicate": predicate,
                "gaps": sorted(after_set),
            })
        else:
            grew.append({
                "predicate": predicate,
                "gaps_before": sorted(before_set),
                "gaps_after": sorted(after_set),
            })

    for predicate, after_set in after_gaps.items():
        if predicate not in before_gaps and after_set:
            new.append({
                "predicate": predicate,
                "gaps": sorted(after_set),
            })

    before_by_id = {r.query_id: r for r in before_list if r.query_id is not None}
    after_by_id = {r.query_id: r for r in after_list if r.query_id is not None}
    value_drift: list[dict] = []
    for qid, b in before_by_id.items():
        a = after_by_id.get(qid)
        if a is None:
            continue
        b_value = b.numeric_result.value if b.numeric_result is not None else None
        a_value = a.numeric_result.value if a.numeric_result is not None else None
        if (
            b.status is not a.status
            or b_value != a_value
            or b.confidence != a.confidence
        ):
            value_drift.append({
                "query_id": qid,
                "before": _query_row(b),
                "after":  _query_row(a),
            })

    return {
        "framing": {
            "resolved":  resolved,
            "shrunk":    shrunk,
            "unchanged": unchanged,
            "grew":      grew,
            "new":       new,
        },
        "value_drift": value_drift,
    }
