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
    """Extraction dict doesn't have ``{variables: [...]}`` / ``{edges: [...]}`` shape."""


class MergeConflictError(ValueError):
    """Two declarations of the same predicate / edge pair disagree.

    For variables: the same field is set to different concrete values.
    For edges: the same predicate pair is declared as different kinds
    (cause / bidirected / refusal) by different extractions.

    The message names the predicate or pair so the caller can surface
    the conflict back to the user / LLM for re-prompting.
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


# ====================================================== edge merge (Phase 4)
#
# A2 prompt (`narrative_to_edges.md`) emits this shape:
#
#   {
#     "edges": [
#       {"kind": "cause", "from": {"predicate": "X"}, "to": {"predicate": "Y"},
#        "annotations": {"source": "narrative_proposal", "evidence": "..."}},
#       {"kind": "bidirected", "left": {"predicate": "X"}, "right": {"predicate": "Y"},
#        "annotations": {...}},
#     ],
#     "refusals": [
#       {"kind": "refuse_direct_edge", "from": "X", "to": "Y",
#        "reason": "...", "suggested_confounder": "..."}
#     ],
#     "narrative_ambiguities": [...]
#   }
#
# Merge semantics:
# - cause / bidirected edges deduped by normalized predicate pair; evidence
#   strings concatenated unique
# - bidirected pair is unordered (X↔Y == Y↔X)
# - refusals deduped by (from, to) pair
# - narrative_ambiguities concatenated (each may originate from a different
#   paragraph; deduplication is the LLM's job upstream)
# - cross-kind conflict for the same pair (cause vs bidirected vs refusal)
#   raises MergeConflictError


def _require_edges_extraction(extraction: dict, what: str) -> dict:
    if not isinstance(extraction, dict):
        raise ExtractionShapeError(f"{what} must be a dict")
    if "edges" not in extraction:
        raise ExtractionShapeError(f"{what}.edges is required")
    if not isinstance(extraction["edges"], list):
        raise ExtractionShapeError(f"{what}.edges must be a list")
    for i, e in enumerate(extraction["edges"]):
        if not isinstance(e, dict):
            raise ExtractionShapeError(f"{what}.edges[{i}] must be a dict")
        kind = e.get("kind")
        if kind == "cause":
            for end in ("from", "to"):
                ref = e.get(end)
                if not isinstance(ref, dict) or not isinstance(ref.get("predicate"), str):
                    raise ExtractionShapeError(
                        f"{what}.edges[{i}].{end}.predicate must be a string"
                    )
        elif kind == "bidirected":
            for end in ("left", "right"):
                ref = e.get(end)
                if not isinstance(ref, dict) or not isinstance(ref.get("predicate"), str):
                    raise ExtractionShapeError(
                        f"{what}.edges[{i}].{end}.predicate must be a string"
                    )
        else:
            raise ExtractionShapeError(
                f"{what}.edges[{i}].kind must be 'cause' or 'bidirected'"
            )
    # refusals + narrative_ambiguities are optional; shape-validate softly
    for key in ("refusals", "narrative_ambiguities"):
        val = extraction.get(key)
        if val is not None and not isinstance(val, list):
            raise ExtractionShapeError(f"{what}.{key} must be a list when present")
    return extraction


def _edge_pair_key(edge: dict) -> tuple[str, tuple[str, ...]]:
    """Normalized dedup key. Bidirected pair is sorted; cause is ordered."""
    if edge["kind"] == "cause":
        return ("cause", (edge["from"]["predicate"], edge["to"]["predicate"]))
    # bidirected
    pair = tuple(sorted((edge["left"]["predicate"], edge["right"]["predicate"])))
    return ("bidirected", pair)


def _refusal_key(ref: dict) -> tuple[str, str]:
    return (ref.get("from", ""), ref.get("to", ""))


def _pair_for_conflict(edge_or_refusal: dict) -> tuple[str, str]:
    """Unordered predicate pair, used to detect cross-kind conflicts."""
    if "from" in edge_or_refusal and "to" in edge_or_refusal:
        a = edge_or_refusal["from"]
        b = edge_or_refusal["to"]
        a = a["predicate"] if isinstance(a, dict) else a
        b = b["predicate"] if isinstance(b, dict) else b
    else:
        a = edge_or_refusal["left"]["predicate"]
        b = edge_or_refusal["right"]["predicate"]
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _merge_two_edges(a: dict, b: dict) -> dict:
    """Combine two same-pair edges of the same kind; concat unique evidence."""
    out = deepcopy(a)
    a_anno = a.get("annotations") or {}
    b_anno = b.get("annotations") or {}

    # Source: prefer concrete citation over narrative_proposal; otherwise
    # take a's. We don't try to be clever about multiple citations.
    a_src = a_anno.get("source")
    b_src = b_anno.get("source")
    src = a_src if a_src and a_src != "narrative_proposal" else (b_src or a_src)

    # Evidence: concat unique non-empty strings, preserving order.
    evidences: list[str] = []
    for anno in (a_anno, b_anno):
        ev = anno.get("evidence")
        if isinstance(ev, str) and ev and ev not in evidences:
            evidences.append(ev)
        elif isinstance(ev, list):
            for item in ev:
                if isinstance(item, str) and item and item not in evidences:
                    evidences.append(item)

    annotations: dict = {}
    if src is not None:
        annotations["source"] = src
    if len(evidences) == 1:
        annotations["evidence"] = evidences[0]
    elif evidences:
        annotations["evidence"] = evidences
    # Preserve any other annotation fields from a (b's are dropped on collision)
    for k, v in a_anno.items():
        if k not in ("source", "evidence"):
            annotations.setdefault(k, v)
    for k, v in b_anno.items():
        if k not in ("source", "evidence"):
            annotations.setdefault(k, v)

    if annotations:
        out["annotations"] = annotations
    return out


def merge_edge_extractions(*extractions: dict) -> dict:
    """Merge multiple A2-shape ``{edges, refusals?, narrative_ambiguities?}``
    dicts into one.

    Behavior:
    - same-kind same-pair edges merge (evidence unioned)
    - cross-kind conflicts on the same predicate pair (e.g. cause vs
      bidirected, cause vs refusal) raise ``MergeConflictError``
    - refusals dedup by ``(from, to)``
    - ``narrative_ambiguities`` concatenated as-is (each may come from a
      different paragraph)

    Empty arg list returns ``{"edges": [], "refusals": [], "narrative_ambiguities": []}``.
    """
    edges_by_key: dict[tuple, dict] = {}
    edge_order: list[tuple] = []
    # Track set of kinds seen per unordered pair. cause + bidirected on the
    # same pair coexist (standard ADMG); refusal contradicts both.
    pair_kinds: dict[tuple[str, str], set[str]] = {}
    refusals_by_key: dict[tuple[str, str], dict] = {}
    refusal_order: list[tuple[str, str]] = []
    all_ambiguities: list[dict] = []

    def _check_conflict(pair: tuple[str, str], incoming: str) -> None:
        existing = pair_kinds.get(pair, set())
        if incoming == "refusal" and existing & {"cause", "bidirected"}:
            raise MergeConflictError(
                f"edge pair {pair}: refusal vs existing edge ({sorted(existing)})"
            )
        if incoming in ("cause", "bidirected") and "refusal" in existing:
            raise MergeConflictError(
                f"edge pair {pair}: {incoming} vs existing refusal"
            )
        # cause + bidirected on the same pair COEXIST — no conflict.

    for idx, extraction in enumerate(extractions):
        e = _require_edges_extraction(extraction, f"extractions[{idx}]")

        for edge in e["edges"]:
            key = _edge_pair_key(edge)
            unordered = _pair_for_conflict(edge)
            kind_tag = key[0]

            _check_conflict(unordered, kind_tag)
            pair_kinds.setdefault(unordered, set()).add(kind_tag)

            if key in edges_by_key:
                edges_by_key[key] = _merge_two_edges(edges_by_key[key], edge)
            else:
                edges_by_key[key] = deepcopy(edge)
                edge_order.append(key)

        for ref in e.get("refusals") or []:
            unordered = _pair_for_conflict(ref)
            _check_conflict(unordered, "refusal")
            pair_kinds.setdefault(unordered, set()).add("refusal")

            rkey = _refusal_key(ref)
            if rkey not in refusals_by_key:
                refusals_by_key[rkey] = deepcopy(ref)
                refusal_order.append(rkey)

        for amb in e.get("narrative_ambiguities") or []:
            all_ambiguities.append(deepcopy(amb))

    return {
        "edges": [edges_by_key[k] for k in edge_order],
        "refusals": [refusals_by_key[k] for k in refusal_order],
        "narrative_ambiguities": all_ambiguities,
    }


def _arg_const_me() -> list:
    return [{"type": "const", "name": "me"}]


def merge_edges_into_program(program_ast: dict, edge_extraction: dict) -> dict:
    """Fold A2 narrative-extracted edges into a kernel_ast program.

    Returns a new program dict — ``program_ast`` is not mutated.

    Behavior:
    - Each ``cause`` edge becomes a ``cause`` statement; each ``bidirected``
      edge becomes a ``bidirected`` statement. Atom args are filled with
      ``[{type: const, name: me}]`` per A2 prompt convention.
    - If the program already contains an edge for the same predicate pair
      (same kind), the duplicate is skipped (existing program wins on
      annotations, since it likely has hand-curated provenance).
    - Cross-kind conflict (existing cause edge vs incoming bidirected for
      the same pair, or vice versa) raises ``MergeConflictError``.
    - Refusals and narrative_ambiguities from the extraction are NOT
      merged into the program directly — refusals are advisory (they
      explain why the agent did NOT propose an edge), and ambiguities
      belong in ``extensions.ambiguities`` which is the orchestrator's
      job to populate.
    - New edges are inserted after the last existing statement of the
      same kind (cause → after last cause, bidirected → after last
      bidirected; falls back to end of statements list).
    """
    if not isinstance(program_ast, dict):
        raise ExtractionShapeError("program_ast must be a dict")
    if not isinstance(program_ast.get("statements"), list):
        raise ExtractionShapeError("program_ast.statements must be a list")

    e = _require_edges_extraction(edge_extraction, "edge_extraction")

    out = deepcopy(program_ast)
    statements: list = out["statements"]

    # Index existing edges by normalized pair. We allow cause AND bidirected
    # to coexist on the same pair (ADMG semantics: directed edge + latent
    # confounder), so track a set of kinds per pair, not a single kind.
    existing_by_pair: dict[tuple[str, str], set[str]] = {}
    last_cause_idx = -1
    last_bidirected_idx = -1
    for i, s in enumerate(statements):
        if not isinstance(s, dict):
            continue
        if s.get("kind") == "cause":
            last_cause_idx = i
            f = (s.get("from") or {}).get("predicate")
            t = (s.get("to") or {}).get("predicate")
            if isinstance(f, str) and isinstance(t, str):
                existing_by_pair.setdefault(tuple(sorted((f, t))), set()).add("cause")  # type: ignore[arg-type]
        elif s.get("kind") == "bidirected":
            last_bidirected_idx = i
            l = (s.get("left") or {}).get("predicate")
            r = (s.get("right") or {}).get("predicate")
            if isinstance(l, str) and isinstance(r, str):
                existing_by_pair.setdefault(tuple(sorted((l, r))), set()).add("bidirected")  # type: ignore[arg-type]

    # Insert new edges in two passes (cause first, then bidirected) to keep
    # ordering predictable.
    cause_insert_at = last_cause_idx + 1 if last_cause_idx >= 0 else len(statements)
    bidirected_insert_at = (
        last_bidirected_idx + 1 if last_bidirected_idx >= 0 else len(statements)
    )

    for edge in e["edges"]:
        if edge["kind"] == "cause":
            f = edge["from"]["predicate"]
            t = edge["to"]["predicate"]
            unordered = tuple(sorted((f, t)))
            existing = existing_by_pair.get(unordered, set())
            if "cause" in existing:
                continue  # already present; don't duplicate
            # cause + existing bidirected coexist (ADMG); no conflict raised.
            stmt = {
                "kind": "cause",
                "from": {"predicate": f, "args": _arg_const_me()},
                "to": {"predicate": t, "args": _arg_const_me()},
            }
            anno = edge.get("annotations")
            if isinstance(anno, dict) and anno:
                stmt["annotations"] = deepcopy(anno)
            statements.insert(cause_insert_at, stmt)
            cause_insert_at += 1
            if bidirected_insert_at > cause_insert_at - 1:
                # earlier insertions may have shifted the bidirected anchor
                pass
            else:
                bidirected_insert_at += 1
            existing_by_pair.setdefault(unordered, set()).add("cause")

        else:  # bidirected
            l = edge["left"]["predicate"]
            r = edge["right"]["predicate"]
            unordered = tuple(sorted((l, r)))
            existing = existing_by_pair.get(unordered, set())
            if "bidirected" in existing:
                continue
            # bidirected + existing cause coexist (ADMG); no conflict raised.
            stmt = {
                "kind": "bidirected",
                "left": {"predicate": l, "args": _arg_const_me()},
                "right": {"predicate": r, "args": _arg_const_me()},
            }
            anno = edge.get("annotations")
            if isinstance(anno, dict) and anno:
                stmt["annotations"] = deepcopy(anno)
            statements.insert(bidirected_insert_at, stmt)
            bidirected_insert_at += 1
            existing_by_pair.setdefault(unordered, set()).add("bidirected")

    return out


# ============================================== end-to-end orchestration


def compose_program(
    base_program: dict,
    variable_extraction: dict | None = None,
    edge_extraction: dict | None = None,
) -> dict:
    """Phase 4 end-to-end glue: fold A5 variables + A2 edges into a base program.

    The base program is typically the question-side kernel_ast that A1
    emits from the user's question (variables + query, possibly with
    common-knowledge cause edges). The narrative-side extractions
    (A5 variables, A2 edges) are folded in on top, with the same
    merge semantics as ``merge_into_program`` and
    ``merge_edges_into_program``.

    Either extraction may be ``None`` to skip that step.

    Order matters: variables are merged first so any predicate
    referenced by an incoming edge is already declared. The edge
    merger does not validate that referenced predicates exist —
    schema validation downstream will catch dangling references.

    Returns a new program dict — ``base_program`` is not mutated.
    Conflicts (variable framing disagreement, cross-kind edge clash)
    raise ``MergeConflictError`` with a message naming the predicate
    or pair.
    """
    out = deepcopy(base_program)
    if variable_extraction is not None:
        out = merge_into_program(out, variable_extraction)
    if edge_extraction is not None:
        out = merge_edges_into_program(out, edge_extraction)
    return out
