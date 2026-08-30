"""Parameter fill-back workflow.

Three steps in the loop — each a pure function that can be composed
manually or via a wrapper script / CLI:

1. ``extract_skeleton_bundle(results)``: walk every result in a run
   and collect every unique parameter skeleton the investigation
   layer attached. The returned dict is JSON-serializable and meant
   to be written to disk for a user to edit.

2. ``merge_skeleton_bundle(program, filled_bundle)``: take the
   original program plus a user-edited bundle (with numeric
   ``value`` entries filled in) and return a new ``Program`` that
   appends the filled skeletons as ``probabilityStatement`` records.
   Unfilled (value=null) skeletons raise so the user notices.

3. ``diff_runs(before, after)``: classify each query_id into
   resolved / still_missing / changed / unchanged based on the
   before/after ``ResultStatus``. Numeric values on resolved
   transitions are surfaced so the caller can print a useful
   "x → 0.18" kind of summary.

The bundle is NOT a kernel_ast Program on its own; it's a purpose-
built shape for the fill loop. Merge is where it rejoins the main
language.
"""
from __future__ import annotations

from typing import Iterable

from .bundle import (
    VERSION as BUNDLE_VERSION,
    MalformedBundleError,
    Refuses,
    envelope,
)
from .. import language
from ..input.semantic_validator import _to_statement
from ..types import (
    Program,
    QueryResult,
    ResultStatus,
)


#: This bundle kind's name. The version beside it belongs to the
#: envelope rather than to either kind, and is imported from there.
BUNDLE_KIND = "parameter_fill_bundle"

#: The records live under this key — the other half of the pair
#: :func:`themis.workflow.bundle.envelope` is parameterised by.
BUNDLE_RECORDS = "skeletons"


class UnfilledSkeletonError(language.Voiced, ValueError):
    """Raised when ``merge_skeleton_bundle`` is handed a bundle whose
    skeletons still have ``value == null``. Carries ``unfilled`` — a
    list of skeleton indices that weren't filled — so a CLI can point
    the user at them.

    The list is an attribute as well as a fact of the sentence: a
    caller that means to point at those indices reads them, and
    reading them back out of a rendered sentence is not reading them.
    """

    def __init__(self, unfilled: list[int]) -> None:
        super().__init__(Refuses.SKELETONS_ARE_STILL_EMPTY,
                         count=len(unfilled), indices=list(unfilled))
        self.unfilled = unfilled


# ---------------------------------------------------------- extract

def _skeleton_signature(skeleton: dict) -> tuple:
    """Produce a hashable signature so duplicates across multiple
    query results collapse into one bundle entry. The signature is
    built from atom predicates + arg names + values; the TODO source
    annotation does not participate."""
    target = skeleton.get("target", {})
    target_sig = (
        target.get("atom", {}).get("predicate"),
        tuple(
            (a.get("type"), a.get("name"))
            for a in target.get("atom", {}).get("args", [])
        ),
        target.get("value"),
    )
    given_sigs = tuple(
        (
            g.get("atom", {}).get("predicate"),
            tuple(
                (a.get("type"), a.get("name"))
                for a in g.get("atom", {}).get("args", [])
            ),
            g.get("value"),
        )
        for g in skeleton.get("given", [])
    )
    return (target_sig, given_sigs)


def extract_skeleton_bundle(results: Iterable[QueryResult]) -> dict:
    """Collect every unique parameter skeleton across the given run
    results into a JSON-serializable bundle.

    Bundle shape:

        {
          "version": "0.1",
          "kind": "parameter_fill_bundle",
          "skeletons": [
            { kind: "probability", target: ..., given: ...,
              value: null, annotations: {...} },
            ...
          ]
        }

    Dedupe key = (target atom+value, given atoms+values). Items that
    don't carry a skeleton (non-parameter gaps) are skipped. Order is
    first-seen across the input results.
    """
    seen: set = set()
    skeletons: list[dict] = []
    for r in results:
        for req in r.investigation_requests:
            for item in req.items:
                if item.skeleton is None:
                    continue
                sig = _skeleton_signature(item.skeleton)
                if sig in seen:
                    continue
                seen.add(sig)
                skeletons.append(item.skeleton)
    return {
        "version": BUNDLE_VERSION,
        "kind": BUNDLE_KIND,
        BUNDLE_RECORDS: skeletons,
    }


# ----------------------------------------------------------- merge

def merge_skeleton_bundle(program: Program, filled_bundle: dict) -> Program:
    """Return a new ``Program`` with the filled skeletons appended as
    ``probabilityStatement`` records.

    Requirements on the bundle:
    - Shape matches what ``extract_skeleton_bundle`` emitted.
    - Every skeleton's ``value`` is a concrete number (null raises
      ``UnfilledSkeletonError``).
    - Each skeleton's other fields are left as produced; the caller
      may edit ``annotations`` (e.g. fill ``source``) but shouldn't
      reshape target / given.

    Does NOT re-validate the new program against the ast schema here —
    callers that want schema-level assurance should run
    ``syntactic_validator.validate_ast`` on a round-tripped dict.
    ``theta_builder`` will still catch conflicting entries downstream.
    """
    skeletons = envelope(filled_bundle, kind=BUNDLE_KIND,
                         key=BUNDLE_RECORDS)

    unfilled = [i for i, s in enumerate(skeletons) if s.get("value") is None]
    if unfilled:
        raise UnfilledSkeletonError(unfilled)

    new_statements = list(program.statements)
    for s in skeletons:
        new_statements.append(_to_statement(s))
    return Program(
        version=program.version,
        objects=program.objects,
        statements=tuple(new_statements),
        extensions=program.extensions,
    )


# ------------------------------------------------------------ diff

def _row(r: QueryResult) -> dict[str, object]:
    """A compact dict row describing a single QueryResult's status."""
    row: dict[str, object] = {"query_id": r.query_id, "status": r.status.value}
    if r.numeric_result is not None:
        row["value"] = r.numeric_result.value
    if r.missing_information:
        row["missing_count"] = len(r.missing_information)
    return row


def diff_runs(
    before: Iterable[QueryResult],
    after: Iterable[QueryResult],
) -> dict:
    """Categorise every query_id that appears in either run.

    Returns:

        {
          "resolved":      [<row>, ...],  # needs_investigation -> numerically_solved
          "still_missing": [<row>, ...],  # needs_investigation in both
          "changed":       [<row>, ...],  # any other status transition
          "unchanged":     [<row>, ...],  # same status in both
          "before_only":   [<row>, ...],  # present only in before
          "after_only":    [<row>, ...],  # present only in after
        }

    Each row carries query_id, status (post), numeric value when
    available, and missing_count. For "resolved" rows the status is
    the after status (numerically_solved) and the value is the newly
    computed one.
    """
    before_by_id = {r.query_id: r for r in before if r.query_id is not None}
    after_by_id = {r.query_id: r for r in after if r.query_id is not None}

    resolved: list[dict] = []
    still_missing: list[dict] = []
    changed: list[dict] = []
    unchanged: list[dict] = []
    before_only: list[dict] = []
    after_only: list[dict] = []

    for qid, b in before_by_id.items():
        if qid not in after_by_id:
            before_only.append(_row(b))
            continue
        a = after_by_id[qid]
        if (
            b.status is ResultStatus.NEEDS_INVESTIGATION
            and a.status is ResultStatus.NUMERICALLY_SOLVED
        ):
            resolved.append(_row(a))
        elif (
            b.status is ResultStatus.NEEDS_INVESTIGATION
            and a.status is ResultStatus.NEEDS_INVESTIGATION
        ):
            still_missing.append(_row(a))
        elif b.status is a.status:
            unchanged.append(_row(a))
        else:
            changed.append(
                {
                    "query_id": qid,
                    "from": b.status.value,
                    "to": a.status.value,
                }
            )

    for qid, a in after_by_id.items():
        if qid not in before_by_id:
            after_only.append(_row(a))

    return {
        "resolved":      resolved,
        "still_missing": still_missing,
        "changed":       changed,
        "unchanged":     unchanged,
        "before_only":   before_only,
        "after_only":    after_only,
    }
