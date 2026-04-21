"""Slice A0: advisory framing check.

Reads VariableDeclaration statements out of a Program and, for each
query, reports which framing-metadata fields are unset on predicates
the query references. The output is purely advisory — it never shifts
a result's status or changes any numeric value.

Design contract:

- **Opt-in per predicate.** A predicate with no VariableDeclaration at
  all produces no framing_note. This keeps every pre-Slice-A0 fixture
  (which declares nothing) silent, so adopting the feature is an
  additive author action.
- **Gap list enumerates only unset fields.** A predicate declared with
  only ``domain`` emits a note listing the other four optional fields
  (``time_window``, ``measurement``, ``threshold``, ``observability``)
  as missing. ``unit`` is also optional but omitted from the default
  gap list because it's not always meaningful (e.g. boolean outcomes
  have no unit) — callers can read it off the declaration directly.
- **One note per referenced predicate.** Deduplicated even when the
  same predicate appears in both target and given.
"""
from __future__ import annotations

from typing import Iterable

from ..types import (
    AssocQuery,
    Atom,
    CauseQuery,
    EffectQuery,
    FramingNote,
    IdentifyQuery,
    ProbabilityQuery,
    Program,
    QueryStatement,
    ValuedAtom,
    VariableDeclaration,
)


_REPORTABLE_FIELDS: tuple[str, ...] = (
    "domain",
    "time_window",
    "measurement",
    "threshold",
    "observability",
    # Slice #41 additions — direction / baseline / state_vs_event
    # join the gap list so A0 surfaces them the same way it does the
    # original four. ``unit`` stays out (optional, not all predicates
    # have a physical unit).
    "direction",
    "baseline",
    "state_vs_event",
)


# Slice F1: shape of the variable_patch dict emitted as
# InvestigationItem.skeleton for DEFINE_VARIABLE items. Must stay in
# sync with ``themis.workflow.variable_framing.PATCH_KIND`` /
# ``_PATCHABLE_FIELDS`` — any shape change needs coordinated edits in
# both modules and in the existing extract / merge tests.
_PATCH_KIND = "variable_patch"
_PATCH_DISPLAY_FIELDS: tuple[str, ...] = (
    "domain",
    "time_window",
    "measurement",
    "threshold",
    "observability",
    "unit",
    # Slice #41
    "direction",
    "baseline",
    "state_vs_event",
)


def _as_atom(x) -> Atom:
    return x.atom if isinstance(x, ValuedAtom) else x


def _predicates_in_query(stmt: QueryStatement) -> tuple[str, ...]:
    q = stmt.query
    atoms: Iterable[Atom]
    if isinstance(q, CauseQuery):
        atoms = (q.from_atom, q.to_atom)
    elif isinstance(q, AssocQuery):
        atoms = (q.left, q.right, *q.given)
    elif isinstance(q, EffectQuery):
        atoms = (
            _as_atom(q.target),
            q.intervention.atom,
            *(_as_atom(g) for g in q.given),
        )
    elif isinstance(q, IdentifyQuery):
        atoms = (q.target, q.intervention.atom, *q.given)
    elif isinstance(q, ProbabilityQuery):
        atoms = (_as_atom(q.target), *(_as_atom(g) for g in q.given))
    else:
        return ()

    seen: dict[str, None] = {}
    for a in atoms:
        seen.setdefault(a.predicate)
    return tuple(seen.keys())


def _declarations_by_predicate(
    program: Program,
) -> dict[str, VariableDeclaration]:
    """Index declarations by predicate.

    The ``unique_variable_declarations`` semantic check already rejects
    duplicates, so the input program has at most one declaration per
    predicate by the time it reaches here. Framing is a read-only
    consumer of that invariant.
    """
    idx: dict[str, VariableDeclaration] = {}
    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration):
            idx[stmt.predicate] = stmt
    return idx


def _gaps(decl: VariableDeclaration) -> tuple[str, ...]:
    missing: list[str] = []
    for field in _REPORTABLE_FIELDS:
        if getattr(decl, field) is None:
            missing.append(field)
    return tuple(missing)


def check_framing(
    program: Program,
    stmt: QueryStatement,
) -> tuple[FramingNote, ...]:
    """Return framing notes for every declared predicate the query
    references that still has unset metadata fields.

    Predicates without any VariableDeclaration are silently skipped —
    framing is opt-in.
    """
    decls = _declarations_by_predicate(program)
    notes: list[FramingNote] = []
    for pred in _predicates_in_query(stmt):
        decl = decls.get(pred)
        if decl is None:
            continue
        gaps = _gaps(decl)
        if gaps:
            notes.append(FramingNote(predicate=pred, missing=gaps))
    return tuple(notes)


def build_define_variable_skeleton(
    program: Program,
    predicate: str,
    gap_fields: tuple[str, ...],
) -> dict:
    """Slice F1: build a variable_patch dict that can be dropped
    straight into a ``framing_skeleton_bundle`` and fed through
    ``merge_variable_declaration``.

    ``existing`` surfaces the predicate's already-set metadata as
    read-only context; ``fields`` carries each gap field as ``None``
    for the author to fill.

    Only callable for a predicate that has a VariableDeclaration;
    undeclared predicates produce no framing note and therefore no
    skeleton. Raises KeyError otherwise.
    """
    decls = _declarations_by_predicate(program)
    decl = decls[predicate]

    existing: dict = {}
    for field in _PATCH_DISPLAY_FIELDS:
        value = getattr(decl, field)
        if value is None:
            continue
        if field == "domain":
            existing[field] = list(value)
        else:
            existing[field] = value

    return {
        "kind": _PATCH_KIND,
        "predicate": predicate,
        "existing": existing,
        "fields": {field: None for field in gap_fields},
    }
