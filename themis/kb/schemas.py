"""Phase 11.2 KB Adapter — query / result / provenance schemas.

These dataclasses define the contract any KB adapter (PrimeKG, SciGraph,
SemMedDB, WebSearch wrapper, ...) speaks back to Themis. Themis itself
performs no IO — adapters live in client code or sibling packages, fetch
data, and return KBResult instances that the translator turns into
parameter_fill_bundle patches.

JSON schema mirrors live in `kb_query.schema.json` and
`kb_result.schema.json` at project root.

Frozen dataclasses for hashability + structural equality (consistent
with themis/types.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class KBQueryKind(str, Enum):
    """What the gap is asking the KB for. Maps from data_gap_report.kind
    via translator.gap_to_kb_query()."""

    MARGINAL_DISTRIBUTION = "marginal_distribution"
    CONDITIONAL_DISTRIBUTION = "conditional_distribution"
    JOINT_DISTRIBUTION = "joint_distribution"
    STRATIFIED_SUBGROUP = "stratified_subgroup"
    IV_CANDIDATE = "iv_candidate"
    MEDIATOR_DISTRIBUTION = "mediator_distribution"
    TARGET_POPULATION_MARGINAL = "target_population_marginal"


class KBConfidenceGrade(str, Enum):
    """Evidence grade self-reported by the source KB. Loosely modeled on
    GRADE / ACCP. Used by future S.11.7 conflict resolution to weight
    competing answers."""

    RCT_META_ANALYSIS = "rct_meta_analysis"
    SINGLE_RCT = "single_rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    EXPERT_OPINION = "expert_opinion"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class KBQuery:
    """A structured ask for one piece of evidence.

    `target` and `given` use JSON-shaped atom dicts (not strongly typed
    Atom) so third-party adapters don't need to import themis types:

        {"predicate": "y", "args": [{"type": "const", "name": "me"}],
         "value": true}

    `population` matches the population label used in transport queries
    (same string the kernel_ast `target_population` field carries).

    `constraints` carries optional refinements (age range, sex, time
    window) that adapters may use to narrow the lookup. Free-form dict
    so adapters can interpret per their own capabilities.

    `raw_string` is the fallback free-form query the LLM would have run
    via WebSearch — adapters that can't parse the structured shape can
    fall back to it.
    """

    kb_name: str
    query_kind: KBQueryKind
    target: dict
    given: tuple[dict, ...] = ()
    population: str | None = None
    constraints: dict | None = None
    raw_string: str | None = None


@dataclass(frozen=True)
class KBProvenance:
    """Audit trail attached to every KBResult. The translator copies
    `citation` into the patch's `annotations.source` so the verifier
    treats the value as sourced (confidence > 0)."""

    source_kb: str
    query_used: KBQuery
    retrieved_at: str
    raw_response_hash: str
    citation: str
    confidence_grade: KBConfidenceGrade = KBConfidenceGrade.UNKNOWN
    notes: str | None = None


@dataclass(frozen=True)
class KBResult:
    """Outcome of a KB lookup.

    Success path: `success=True`, `value` (and optionally `interval`,
    `sample_size`) populated, `provenance` complete.

    Failure path: `success=False`, `failure_reason` describes why
    (no_match / parse_error / dtype_mismatch / unauthorized / ...).
    Provenance is still attached even on failure so the audit trail
    captures *what was tried*.
    """

    query: KBQuery
    success: bool
    provenance: KBProvenance
    value: float | None = None
    interval: tuple[float, float] | None = None
    sample_size: int | None = None
    population_in_source: str | None = None
    failure_reason: str | None = None


# ---------------------------------------------------------------------------
# JSON serialization helpers
#
# Adapters and clients exchange these as JSON over MCP / HTTP / disk. Round-
# trip helpers keep the encoding stable so cache hashes stay deterministic.
# ---------------------------------------------------------------------------


def kb_query_to_dict(q: KBQuery) -> dict:
    """Pure dict representation; matches kb_query.schema.json."""
    out: dict = {
        "kb_name": q.kb_name,
        "query_kind": q.query_kind.value,
        "target": q.target,
        "given": list(q.given),
    }
    if q.population is not None:
        out["population"] = q.population
    if q.constraints is not None:
        out["constraints"] = q.constraints
    if q.raw_string is not None:
        out["raw_string"] = q.raw_string
    return out


def kb_query_from_dict(d: dict) -> KBQuery:
    return KBQuery(
        kb_name=d["kb_name"],
        query_kind=KBQueryKind(d["query_kind"]),
        target=d["target"],
        given=tuple(d.get("given", ())),
        population=d.get("population"),
        constraints=d.get("constraints"),
        raw_string=d.get("raw_string"),
    )


def kb_provenance_to_dict(p: KBProvenance) -> dict:
    out: dict = {
        "source_kb": p.source_kb,
        "query_used": kb_query_to_dict(p.query_used),
        "retrieved_at": p.retrieved_at,
        "raw_response_hash": p.raw_response_hash,
        "citation": p.citation,
        "confidence_grade": p.confidence_grade.value,
    }
    if p.notes is not None:
        out["notes"] = p.notes
    return out


def kb_provenance_from_dict(d: dict) -> KBProvenance:
    return KBProvenance(
        source_kb=d["source_kb"],
        query_used=kb_query_from_dict(d["query_used"]),
        retrieved_at=d["retrieved_at"],
        raw_response_hash=d["raw_response_hash"],
        citation=d["citation"],
        confidence_grade=KBConfidenceGrade(d.get("confidence_grade", "unknown")),
        notes=d.get("notes"),
    )


def kb_result_to_dict(r: KBResult) -> dict:
    out: dict = {
        "query": kb_query_to_dict(r.query),
        "success": r.success,
        "provenance": kb_provenance_to_dict(r.provenance),
    }
    if r.value is not None:
        out["value"] = r.value
    if r.interval is not None:
        out["interval"] = list(r.interval)
    if r.sample_size is not None:
        out["sample_size"] = r.sample_size
    if r.population_in_source is not None:
        out["population_in_source"] = r.population_in_source
    if r.failure_reason is not None:
        out["failure_reason"] = r.failure_reason
    return out


def kb_result_from_dict(d: dict) -> KBResult:
    interval = d.get("interval")
    return KBResult(
        query=kb_query_from_dict(d["query"]),
        success=d["success"],
        provenance=kb_provenance_from_dict(d["provenance"]),
        value=d.get("value"),
        interval=tuple(interval) if interval is not None else None,
        sample_size=d.get("sample_size"),
        population_in_source=d.get("population_in_source"),
        failure_reason=d.get("failure_reason"),
    )
