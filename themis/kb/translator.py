"""Phase 11.2 — pure translation between DataGap and KB layer.

Two functions:

- ``gap_to_kb_query``: build a structured KBQuery from a DataGap. The
  caller supplies the target / given atoms because DataGap carries
  P(...) only as a description string, while the LLM (which produced
  the kernel_ast) already knows the structured atoms.

- ``kb_result_to_skeleton`` / ``kb_results_to_bundle``: turn a KBResult
  (or several) into the parameter_fill_bundle shape that
  ``themis.apply_patch_and_run`` consumes. ``annotations.source`` is
  copied verbatim from ``provenance.citation`` so the verifier treats
  the value as sourced.

No IO, no kernel access — both functions are deterministic and
side-effect-free.
"""
from __future__ import annotations

from ..types import DataGap, GapKind
from ..workflow.parameter_fill import BUNDLE_KIND, BUNDLE_VERSION
from .schemas import KBQuery, KBQueryKind, KBResult


# Maps DataGap.kind → KBQueryKind. Three gap_kinds are intentionally
# absent: UNIDENTIFIABLE_NO_ADMISSIBLE_SET (no data fixes structure),
# MISSING_ASSUMPTION (user epistemological choice), and
# AMBIGUOUS_VARIABLE_DEFINITION (user reframing). For those,
# gap_to_kb_query returns None — the caller surfaces the gap to the
# user via ask-then-render, not via KB lookup.
_GAP_TO_QUERY_KIND: dict[GapKind, KBQueryKind] = {
    GapKind.MISSING_POPULATION_DISTRIBUTION: KBQueryKind.TARGET_POPULATION_MARGINAL,
    GapKind.MISSING_IV_CANDIDATE: KBQueryKind.IV_CANDIDATE,
    GapKind.MISSING_MEDIATOR_DATA: KBQueryKind.MEDIATOR_DISTRIBUTION,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: KBQueryKind.TARGET_POPULATION_MARGINAL,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: KBQueryKind.STRATIFIED_SUBGROUP,
}


# MISSING_DISTRIBUTION dispatches by signature — distinct query_kinds
# let adapters route to data sources of the matching shape.
_SIGNATURE_TO_QUERY_KIND: dict[str, KBQueryKind] = {
    "marginal": KBQueryKind.MARGINAL_DISTRIBUTION,
    "conditional": KBQueryKind.CONDITIONAL_DISTRIBUTION,
    "joint": KBQueryKind.JOINT_DISTRIBUTION,
}


# Default kb_name when the caller doesn't supply a kb_hint. websearch_proxy
# is the reference adapter (S.11.2.5); concrete KB adapters override at
# call site.
DEFAULT_KB_NAME = "websearch_proxy"


def gap_to_kb_query(
    gap: DataGap,
    *,
    target: dict,
    given: tuple[dict, ...] = (),
    kb_hint: str | None = None,
    constraints: dict | None = None,
    raw_string: str | None = None,
) -> KBQuery | None:
    """Build a structured KBQuery from a DataGap.

    `target` / `given` are atom dicts the caller (orchestrator LLM)
    extracted while parsing the kernel_ast. They are not parsed out of
    `gap.description` — that string is freeform Chinese / mixed and
    not reliably parseable.

    Returns None when the gap_kind has no KB-fixable mapping:
    UNIDENTIFIABLE_NO_ADMISSIBLE_SET (structural), MISSING_ASSUMPTION
    (user choice), AMBIGUOUS_VARIABLE_DEFINITION (user reframing).
    """
    query_kind = _resolve_query_kind(gap)
    if query_kind is None:
        return None

    population = None
    if gap.required_data is not None:
        population = gap.required_data.population

    return KBQuery(
        kb_name=kb_hint or DEFAULT_KB_NAME,
        query_kind=query_kind,
        target=target,
        given=given,
        population=population,
        constraints=constraints,
        raw_string=raw_string,
    )


def _resolve_query_kind(gap: DataGap) -> KBQueryKind | None:
    if gap.kind == GapKind.MISSING_DISTRIBUTION:
        if gap.signature is None:
            # Generator should always set signature on missing_distribution
            # gaps, but if it didn't, treat as conditional (the safer
            # default — a marginal can be derived from a conditional + a
            # marginal for the conditioning variable, but not vice versa).
            return KBQueryKind.CONDITIONAL_DISTRIBUTION
        return _SIGNATURE_TO_QUERY_KIND.get(gap.signature, KBQueryKind.CONDITIONAL_DISTRIBUTION)
    return _GAP_TO_QUERY_KIND.get(gap.kind)


# ---------------------------------------------------------------------------
# KBResult → parameter_fill_bundle
# ---------------------------------------------------------------------------


def kb_result_to_skeleton(result: KBResult) -> dict | None:
    """Turn one successful KBResult into a parameter_fill_bundle skeleton.

    Returns None when the result can't be converted into a probability
    skeleton (failure result / no value / wrong query_kind).

    The caller bundles one or more skeletons via ``kb_results_to_bundle``
    before calling ``themis.apply_patch_and_run``.
    """
    if not result.success or result.value is None:
        return None

    # IV_CANDIDATE results are not probability skeletons — they propose
    # a variable to add to the graph, not a value to fill in. Out of
    # scope for this translator.
    if result.query.query_kind == KBQueryKind.IV_CANDIDATE:
        return None

    target = _atom_with_value(result.query.target)
    given = [_atom_with_value(a) for a in result.query.given]

    skeleton: dict = {
        "kind": "probability",
        "target": target,
        "given": given,
        "value": result.value,
        "annotations": {"source": result.provenance.citation},
    }
    return skeleton


def _atom_with_value(atom: dict) -> dict:
    """Wrap a bare atom dict as the {atom: ..., value: ...} shape the
    parameter_fill skeleton uses. If atom already has a 'value' key at
    the top level, lift it out into the skeleton's value slot."""
    if "atom" in atom and "value" in atom:
        # Already in the {atom, value} shape
        return {"atom": atom["atom"], "value": atom["value"]}
    value = atom.get("value", True)
    inner = {k: v for k, v in atom.items() if k != "value"}
    return {"atom": inner, "value": value}


def kb_results_to_bundle(results: list[KBResult]) -> dict:
    """Bundle one or more KBResults into a parameter_fill_bundle dict
    ready for ``themis.apply_patch_and_run``.

    Skipped results (failure, no value, wrong kind) are silently
    dropped — the caller can compare ``len(results)`` vs
    ``len(bundle['skeletons'])`` to detect drops.
    """
    skeletons: list[dict] = []
    for r in results:
        sk = kb_result_to_skeleton(r)
        if sk is not None:
            skeletons.append(sk)
    return {
        "version": BUNDLE_VERSION,
        "kind": BUNDLE_KIND,
        "skeletons": skeletons,
    }
