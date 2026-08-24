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
    CounterfactualQuery,
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
    elif isinstance(q, CounterfactualQuery):
        atoms = (
            _as_atom(q.observed),
            q.counterfactual_intervention.atom,
            _as_atom(q.counterfactual_target),
        )
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


# `threshold` is a continuous-cutpoint field — operationalization-relevant
# only for a continuous / numeric variable (something a cutpoint could
# dichotomize), not for a genuinely binary / categorical predicate. Same
# conditional-applicability rationale that keeps ``unit`` out of the reportable
# set ("not all predicates have a physical unit"): not all predicates have a
# continuous cutpoint.
_CONTINUOUS_MEASUREMENT_CUES: tuple[str, ...] = (
    "mmhg", "kg", "cm", "mm", "mg", "ml", "mol", "bmi", "%", "score",
    "岁", "分", "毫米", "厘米", "千克", "浓度", "水平", "区间", "范围",
    "连续", "≥", "≤", ">", "<",
)


def _looks_continuous(decl: VariableDeclaration) -> bool:
    """Whether the variable is plausibly a continuous / numeric quantity, so a
    ``threshold`` (cutpoint) is meaningful.

    ``scale`` answers this outright and is asked first: it is a closed
    vocabulary the author declares, and a declaration beats a reading of
    the prose beside it. The cues below are the fallback for a declaration
    that has none — a physical ``unit``, or a ``measurement`` naming a
    numeric quantity (a digit, a common unit, a range or comparison). A
    genuinely binary event measured "是/否" has none of these, so we don't
    nag it for a cutpoint it can't have. The fallback reads whatever words
    the author wrote and so cannot be language-neutral; that is a property
    of free text, not something a second language would fix, and it is
    exactly why the positive declaration goes first.
    """
    if decl.scale is not None:
        return decl.scale == "continuous"
    if getattr(decl, "unit", None):
        return True
    m = (getattr(decl, "measurement", None) or "").lower()
    if not m:
        return False
    if any(ch.isdigit() for ch in m):
        return True
    return any(cue in m for cue in _CONTINUOUS_MEASUREMENT_CUES)


def _gaps(decl: VariableDeclaration) -> tuple[str, ...]:
    missing: list[str] = []
    continuous = _looks_continuous(decl)
    defaulted = frozenset(decl.defaulted)
    for field in _REPORTABLE_FIELDS:
        # threshold only applies to continuous variables (see above); skip it
        # for binary / categorical predicates so it isn't a phantom gap.
        if field == "threshold" and not continuous:
            continue
        # A field the author answered by taking the standard operationalisation
        # is answered. The question was put and something came back, which is
        # the whole of what this check asks — the fill loop used to make the
        # same answer out of a sentence written into the value, and the
        # sentence is what ``defaulted`` replaces.
        if field in defaulted:
            continue
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
    # Answered by taking the default is answered, so it belongs in the
    # read-only context beside the fields that carry a value — an author
    # looking at this skeleton is owed both halves of what has been settled.
    if decl.defaulted:
        existing["defaulted"] = list(decl.defaulted)

    return {
        "kind": _PATCH_KIND,
        "predicate": predicate,
        "existing": existing,
        "fields": {field: None for field in gap_fields},
    }
