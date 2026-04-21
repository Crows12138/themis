"""Slice #37 / A5b: merge narrative-extracted variable dicts.

Companion to ``docs/prompts/narrative_to_variables.md`` (A5). The A5
prompt extracts variable candidates with partial framing from one
paragraph of natural-language narrative. Real usage often needs to
combine:

- **multiple extractions** — e.g. a long narrative split into paragraphs
  and run through A5 separately, then recombined
- **narrative + question** — A5 extraction gives framed variable
  declarations; A1 (``nl_to_kernel_ast.md``) gives a full kernel_ast
  with edges and a query. The narrative declarations must be folded
  into the kernel_ast, with per-predicate union of framing fields.

Both operations are pure JSON-in / JSON-out dict transforms — no
typed Program objects, no LLM calls. This module is LLM-side
convenience (same status as ``program_builder.py``); the kernel
contract is still ``themis.run(kernel_ast)``.

Merge semantics for two declarations of the same predicate:

- ``domain`` — must agree if both set; otherwise take whichever is set
- each framing field (``time_window``, ``measurement``, ``threshold``,
  ``observability``, ``unit``, ``direction``, ``baseline``,
  ``state_vs_event``) — same rule: agree, or one set / one absent
- conflict (both set, values differ) raises ``MergeConflictError``
  with the predicate and field named; callers are expected to surface
  it to the user or the LLM for re-prompting rather than silently
  picking a winner

Synonym collapsing (e.g. ``running`` vs ``daily_running``) is
explicitly NOT in scope — predicates are matched by exact name. The
A5 prompt is responsible for stable naming across extractions; if it
drifts, the human orchestrator resolves it upstream.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Iterable


_FRAMING_FIELDS: tuple[str, ...] = (
    "time_window",
    "measurement",
    "threshold",
    "observability",
    "unit",
    "direction",
    "baseline",
    "state_vs_event",
)


class ExtractionShapeError(ValueError):
    """Extraction dict does not have the expected ``{variables: [...]}`` shape."""


class MergeConflictError(ValueError):
    """Two declarations of the same predicate disagree on a concrete field.

    The message names the predicate and field so the caller can
    surface the conflict back to the user / LLM for re-prompting.
    """


# -------------------------------------------------------------- helpers

def _require_variables_list(extraction: dict, what: str) -> list[dict]:
    if not isinstance(extraction, dict):
        raise ExtractionShapeError(f"{what} must be a dict")
    if "variables" not in extraction:
        raise ExtractionShapeError(f"{what}.variables is required")
    vs = extraction["variables"]
    if not isinstance(vs, list):
        raise ExtractionShapeError(f"{what}.variables must be a list")
    for i, v in enumerate(vs):
        if not isinstance(v, dict):
            raise ExtractionShapeError(
                f"{what}.variables[{i}] must be a dict"
            )
        if v.get("kind") != "variable":
            raise ExtractionShapeError(
                f"{what}.variables[{i}].kind must be 'variable'"
            )
        if not isinstance(v.get("predicate"), str) or not v["predicate"]:
            raise ExtractionShapeError(
                f"{what}.variables[{i}].predicate must be a non-empty string"
            )
    return vs


def _merge_two_decls(a: dict, b: dict, predicate: str) -> dict:
    """Field-by-field union of two variable declarations for the same predicate.

    Raises MergeConflictError when both sides set the same field to
    different concrete values.
    """
    out: dict = {"kind": "variable", "predicate": predicate}

    # domain — list equality
    a_dom = a.get("domain")
    b_dom = b.get("domain")
    if a_dom is not None and b_dom is not None:
        if list(a_dom) != list(b_dom):
            raise MergeConflictError(
                f"predicate {predicate!r}: domain conflict "
                f"({a_dom!r} vs {b_dom!r})"
            )
        out["domain"] = list(a_dom)
    elif a_dom is not None:
        out["domain"] = list(a_dom)
    elif b_dom is not None:
        out["domain"] = list(b_dom)

    for field in _FRAMING_FIELDS:
        a_val = a.get(field)
        b_val = b.get(field)
        if a_val is not None and b_val is not None:
            if a_val != b_val:
                raise MergeConflictError(
                    f"predicate {predicate!r}: {field} conflict "
                    f"({a_val!r} vs {b_val!r})"
                )
            out[field] = a_val
        elif a_val is not None:
            out[field] = a_val
        elif b_val is not None:
            out[field] = b_val

    return out


# ========================================================= public API

def merge_variable_extractions(*extractions: dict) -> dict:
    """Merge multiple A5-shape ``{variables: [...]}`` dicts into one.

    Predicates that appear in more than one extraction are unioned
    field-by-field; concrete disagreement raises
    ``MergeConflictError``. Predicate order follows first appearance.

    With zero arguments, returns ``{"variables": []}``.
    """
    by_pred: dict[str, dict] = {}
    order: list[str] = []

    for idx, extraction in enumerate(extractions):
        vs = _require_variables_list(extraction, f"extractions[{idx}]")
        for v in vs:
            pred = v["predicate"]
            v_copy = deepcopy(v)
            if pred in by_pred:
                by_pred[pred] = _merge_two_decls(by_pred[pred], v_copy, pred)
            else:
                by_pred[pred] = v_copy
                order.append(pred)

    return {"variables": [by_pred[p] for p in order]}


def merge_into_program(program_ast: dict, extraction: dict) -> dict:
    """Fold narrative-extracted variables into a kernel_ast program.

    Returns a new program dict — ``program_ast`` is not mutated.

    Behavior:

    - For each variable declaration in ``extraction.variables``:
      - if the program already declares that predicate, merge the two
        declarations field-by-field (same rules as
        ``merge_variable_extractions``)
      - otherwise, insert the new declaration after the last existing
        variable declaration (or at the front if there are none)
    - Cause statements, probability statements, observations, queries
      — all pass through unchanged

    Raises ``ExtractionShapeError`` or ``MergeConflictError`` on bad
    input or irreconcilable declarations.
    """
    if not isinstance(program_ast, dict):
        raise ExtractionShapeError("program_ast must be a dict")
    if not isinstance(program_ast.get("statements"), list):
        raise ExtractionShapeError("program_ast.statements must be a list")

    new_vars = _require_variables_list(extraction, "extraction")

    out = deepcopy(program_ast)
    statements: list = out["statements"]

    existing_idx: dict[str, int] = {}
    last_var_idx = -1
    for i, s in enumerate(statements):
        if isinstance(s, dict) and s.get("kind") == "variable":
            pred = s.get("predicate")
            if isinstance(pred, str):
                existing_idx[pred] = i
                last_var_idx = i

    insert_at = last_var_idx + 1

    for v in new_vars:
        pred = v["predicate"]
        v_copy = deepcopy(v)
        if pred in existing_idx:
            merged = _merge_two_decls(statements[existing_idx[pred]], v_copy, pred)
            statements[existing_idx[pred]] = merged
        else:
            statements.insert(insert_at, v_copy)
            existing_idx[pred] = insert_at
            insert_at += 1

    return out
