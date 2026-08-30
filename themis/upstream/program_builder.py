"""Slice W1: turn an extraction dict into a Themis ``Program``.

This module is an **LLM-side convenience**, not part of the kernel
contract. The kernel's authoritative entry point is ``themis.run``,
consuming the canonical ``kernel_ast.schema.json`` JSON shape. An
extraction dict is a simpler, LLM-friendlier intermediate that
trades expressivity for ease of reliable structured LLM output —
callers that can emit canonical kernel_ast JSON directly should skip
this module.

An extraction dict is produced by whatever front-end parsed the user's
natural-language question (Claude Code, an LLM with structured output,
or a test fixture). This module converts it into an internal
``Program`` object. It is pure data transformation — no LLM calls,
no I/O, no global state.

Extraction dict shape (W1 supports cause / assoc / effect query kinds;
identify and probability can be added when a real case requires)::

    {
      "query_kind": "effect",              # "cause" | "assoc" | "effect"
      "predicates": ["running", "belly_fat_loss"],
      "edges": [["running", "belly_fat_loss"]],
      "query_id": "q",                     # optional, defaults to "q"
      "query": {
        # shape depends on query_kind — see below
      }
    }

Per-kind ``query`` shapes::

    cause:  {"from": "running", "to": "belly_fat_loss"}
    assoc:  {"left": "a", "right": "b", "given": ["z"]}
    effect: {
              "target":       {"name": "belly_fat_loss", "value": true},
              "intervention": {"name": "running",        "value": true},
              "given":        [{"name": "z", "value": true}, ...]
            }

Design decisions in W1:

- **Bool-only domains.** Every predicate gets ``domain=(True, False)``.
  Categorical domains are in the type system but not reachable from
  NL yet; extend when a case needs it.
- **Single subject "me".** Every atom is ``Atom(predicate=P, args=(ConstTerm("me"),))``.
  Multi-subject questions (e.g. "tom vs alice") aren't in scope here.
- **Opt-in framing stubs.** Each declared predicate produces a
  ``VariableDeclaration`` with only ``domain`` set. The other framing
  fields stay None, which makes A0 / F1 flag them as gaps —
  exactly what this slice's real-case driver needs.

Validation raises ``ExtractionError`` with the species of the refusal and
the offending path in the dict. Callers are expected to surface this error
to the human parser rather than try to guess what they meant.
"""
from __future__ import annotations

from typing import Iterable

from .extraction_words import ExtractionRefusal, Refuses, Shape
from ..types import (
    AssocQuery,
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    Intervention,
    Program,
    QueryStatement,
    ValuedAtom,
    VariableDeclaration,
)

_VALID_QUERY_KINDS = frozenset({"cause", "assoc", "effect"})
_ME = ConstTerm(name="me")


class ExtractionError(ExtractionRefusal):
    """Extraction dict shape is invalid.

    Raised with the species of the refusal and the specific field or path
    that failed validation, so the caller can fix it (or the LLM output
    can be re-prompted) — and so that a surface which knows who is reading
    can say it to them. It carried a finished English sentence until #470.
    """


# ------------------------------------------------------------- helpers

def _require(d: dict, key: str, what: str):
    if key not in d:
        raise ExtractionError(Refuses.IS_REQUIRED, where=f"{what}.{key}")
    return d[key]


def _require_bool(value, what: str) -> bool:
    if not isinstance(value, bool):
        raise ExtractionError(Refuses.ONLY_BOOLEAN_VALUES_HERE, where=what,
                              got=type(value).__name__)
    return value


def _require_str(value, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExtractionError(Refuses.IS_NOT, where=what,
                              shape=Shape.NON_EMPTY_STRING)
    return value


def _atom(name: str) -> Atom:
    return Atom(predicate=name, args=(_ME,))


def _valued_atom(obj: dict, what: str, known_predicates: set[str]) -> ValuedAtom:
    if not isinstance(obj, dict):
        raise ExtractionError(Refuses.IS_NOT, where=what,
                              shape=Shape.NAME_AND_VALUE)
    name = _require_str(_require(obj, "name", what), f"{what}.name")
    if name not in known_predicates:
        raise ExtractionError(Refuses.NOT_A_DECLARED_PREDICATE,
                              where=f"{what}.name", name=name)
    value = _require_bool(_require(obj, "value", what), f"{what}.value")
    return ValuedAtom(atom=_atom(name), value=value)


def _predicate_ref(obj, what: str, known_predicates: set[str]) -> Atom:
    name = _require_str(obj, what)
    if name not in known_predicates:
        raise ExtractionError(Refuses.NOT_A_DECLARED_PREDICATE, where=what,
                              name=name)
    return _atom(name)


# ----------------------------------------------------- per-kind decoders

def _build_cause_query(q: dict, known: set[str]) -> CauseQuery:
    return CauseQuery(
        from_atom=_predicate_ref(_require(q, "from", "query"), "query.from", known),
        to_atom=_predicate_ref(_require(q, "to", "query"), "query.to", known),
    )


def _build_assoc_query(q: dict, known: set[str]) -> AssocQuery:
    given_raw = q.get("given", [])
    if not isinstance(given_raw, list):
        raise ExtractionError(Refuses.IS_NOT, where="query.given",
                              shape=Shape.LIST)
    return AssocQuery(
        left=_predicate_ref(_require(q, "left", "query"), "query.left", known),
        right=_predicate_ref(_require(q, "right", "query"), "query.right", known),
        given=tuple(
            _predicate_ref(g, f"query.given[{i}]", known)
            for i, g in enumerate(given_raw)
        ),
    )


def _build_effect_query(q: dict, known: set[str]) -> EffectQuery:
    given_raw = q.get("given", [])
    if not isinstance(given_raw, list):
        raise ExtractionError(Refuses.IS_NOT, where="query.given",
                              shape=Shape.LIST)
    target = _valued_atom(_require(q, "target", "query"), "query.target", known)
    inter_raw = _require(q, "intervention", "query")
    if not isinstance(inter_raw, dict):
        raise ExtractionError(Refuses.IS_NOT, where="query.intervention",
                              shape=Shape.DICT)
    inter_name = _require_str(
        _require(inter_raw, "name", "query.intervention"), "query.intervention.name"
    )
    if inter_name not in known:
        raise ExtractionError(Refuses.NOT_A_DECLARED_PREDICATE,
                              where="query.intervention.name",
                              name=inter_name)
    inter_value = _require_bool(
        _require(inter_raw, "value", "query.intervention"),
        "query.intervention.value",
    )
    given = tuple(
        _valued_atom(g, f"query.given[{i}]", known)
        for i, g in enumerate(given_raw)
    )
    return EffectQuery(
        target=target,
        intervention=Intervention(atom=_atom(inter_name), value=inter_value),
        given=given,
    )


# ---------------------------------------------------------------- main

def build_program_from_extraction(extraction: dict) -> Program:
    """Convert an extraction dict into a ``Program``.

    The returned Program declares every predicate as a bool variable
    with no framing metadata set, which is exactly what drives the A0
    / F1 channel to report time_window / measurement / threshold /
    observability as missing on every mentioned predicate.

    Raises ``ExtractionError`` on any shape / reference / type
    violation.
    """
    if not isinstance(extraction, dict):
        raise ExtractionError(Refuses.IS_NOT, where="extraction",
                              shape=Shape.DICT)

    # ---- query_kind
    query_kind = _require_str(
        _require(extraction, "query_kind", "extraction"), "extraction.query_kind"
    )
    if query_kind not in _VALID_QUERY_KINDS:
        raise ExtractionError(Refuses.QUERY_KIND_NOT_SUPPORTED,
                              kind=query_kind,
                              accepted=sorted(_VALID_QUERY_KINDS))

    # ---- predicates
    pred_raw = _require(extraction, "predicates", "extraction")
    if not isinstance(pred_raw, list) or not pred_raw:
        raise ExtractionError(Refuses.IS_NOT, where="extraction.predicates",
                              shape=Shape.NON_EMPTY_LIST_OF_NAMES)
    predicates: list[str] = []
    seen: set[str] = set()
    for i, p in enumerate(pred_raw):
        name = _require_str(p, f"extraction.predicates[{i}]")
        if name in seen:
            raise ExtractionError(Refuses.PREDICATE_DECLARED_TWICE,
                                  where="extraction.predicates", name=name)
        seen.add(name)
        predicates.append(name)
    known = set(predicates)

    # ---- edges
    edges_raw = extraction.get("edges", [])
    if not isinstance(edges_raw, list):
        raise ExtractionError(Refuses.IS_NOT, where="extraction.edges",
                              shape=Shape.LIST)
    edges: list[tuple[str, str]] = []
    for i, edge in enumerate(edges_raw):
        where = f"extraction.edges[{i}]"
        if (not isinstance(edge, (list, tuple))) or len(edge) != 2:
            raise ExtractionError(Refuses.IS_NOT, where=where,
                                  shape=Shape.FROM_TO_PAIR)
        src = _require_str(edge[0], f"{where}[0]")
        dst = _require_str(edge[1], f"{where}[1]")
        if src == dst:
            raise ExtractionError(Refuses.SELF_LOOP, where=where, name=src)
        if src not in known or dst not in known:
            raise ExtractionError(Refuses.AN_EDGE_NAMES_SOMETHING_UNDECLARED,
                                  where=where, tail=src, head=dst)
        edges.append((src, dst))

    # ---- query
    query_obj = _require(extraction, "query", "extraction")
    if not isinstance(query_obj, dict):
        raise ExtractionError(Refuses.IS_NOT, where="extraction.query",
                              shape=Shape.DICT)
    # The three kinds W1 supports; the variable holds whichever the
    # dispatch below built, so it is annotated with all three rather
    # than inferred from the first branch.
    query: CauseQuery | AssocQuery | EffectQuery
    if query_kind == "cause":
        query = _build_cause_query(query_obj, known)
    elif query_kind == "assoc":
        query = _build_assoc_query(query_obj, known)
    else:  # effect — validated above
        query = _build_effect_query(query_obj, known)

    # ---- query_id (optional)
    query_id = extraction.get("query_id", "q")
    if not isinstance(query_id, str) or not query_id:
        raise ExtractionError(Refuses.IS_NOT, where="extraction.query_id",
                              shape=Shape.NON_EMPTY_STRING)

    # ---- assemble
    statements: list = []
    for name in predicates:
        statements.append(
            VariableDeclaration(predicate=name, domain=(True, False)),
        )
    for src, dst in edges:
        statements.append(
            CauseStatement(from_atom=_atom(src), to_atom=_atom(dst)),
        )
    statements.append(QueryStatement(id=query_id, query=query))

    return Program(
        version="0.1",
        objects=("me",),
        statements=tuple(statements),
    )
