"""Independent audit of ``extensions.assumption_ledger``.

The ledger is the surface both ``output.analysis_report`` and the
``response_rendering.md`` bridge lead with — everything the answer takes on
faith, ranked by how it dies if it is false. Its failure mode is therefore
one-sided: an assumption that never reaches it is indistinguishable, to every
consumer, from an assumption nobody makes. This module re-derives what the
ledger owes from the channels that feed it and rejects UNDER-disclosure.

What it audits:

- **Completeness of the estimator channel.** ``numeric_estimate.assumptions``
  is the one channel every estimator populates. The ledger must either carry
  each of those declarations (``provenance: estimator_declared``, keyed by
  ``id``) or carry the estimator's own structured ``identification`` entries,
  which say the same thing in better words. Carrying neither is the defect.
- **Completeness of the other three channels** — one entry per load-bearing
  proposal edge in the gap report, per LLM theta prior, per audited mechanism.
- **No fabrication.** An ``estimator_declared`` entry whose ``id`` the estimate
  never declared is invented.
- **Internal coherence.** Entries sorted by severity; the summary's counts
  matching the entries; an ``identification``-layer entry ranked
  ``invalidating`` (the ledger's own semantics: identification failing means
  the number is not a causal effect at all).

What it deliberately does NOT audit: which severity a particular assumption ID
deserves. That is a curation judgement recorded in
``output.assumption_glossary``, not a fact derivable from the envelope;
re-stating the table here would be transcription, not verification.

**Independence pin:** this module MUST NOT import from
``themis.output.result_orchestrator`` or ``themis.output.assumption_glossary``.
"""
from __future__ import annotations

from .errors import VerificationError

_SEVERITIES = ("invalidating", "distorting", "confidence_only")
_RANK = {s: i for i, s in enumerate(_SEVERITIES)}

_RULE = "assumption_ledger_check"


def _reject(message: str) -> None:
    raise VerificationError(message, rule=_RULE)


def verify_assumption_ledger(result: dict) -> None:
    """Audit one result's assumption ledger. No-op when the result has none
    AND owes none; raises :class:`VerificationError` otherwise."""
    extensions = result.get("extensions") or {}
    ledger = extensions.get("assumption_ledger")
    estimate = result.get("numeric_estimate")
    declared = tuple((estimate or {}).get("assumptions") or ())

    owed_edges = _owed_proposal_edges(result)
    owed_priors = _owed_theta_priors(extensions)
    owed_forms = _owed_mechanisms(extensions)

    if ledger is None:
        if declared or owed_edges or owed_priors or owed_forms:
            _reject(
                "assumption_ledger missing while the result declares "
                f"{len(declared)} estimator assumption(s), {len(owed_edges)} "
                f"load-bearing proposal edge(s), {len(owed_priors)} theta "
                f"prior(s) and {len(owed_forms)} audited mechanism(s); an "
                "absent ledger reads as 'nothing is assumed'."
            )
        return

    if not isinstance(ledger, dict):
        _reject(f"assumption_ledger must be an object; got {type(ledger).__name__}")
    entries = ledger.get("assumptions")
    if not isinstance(entries, list) or not entries:
        _reject("assumption_ledger carries no assumptions[]")

    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            _reject(f"assumptions[{i}] must be an object")
        if e.get("severity") not in _RANK:
            _reject(
                f"assumptions[{i}] severity {e.get('severity')!r} is not one of "
                f"{list(_SEVERITIES)}"
            )
        if e.get("layer") == "identification" and e["severity"] != "invalidating":
            _reject(
                f"assumptions[{i}] is an identification assumption ranked "
                f"{e['severity']!r}; identification failing means the number is "
                "not a causal effect at all, which is 'invalidating' by "
                "definition"
            )
        if not str(e.get("claim") or "").strip():
            _reject(f"assumptions[{i}] carries an empty claim")

    ranks = [_RANK[e["severity"]] for e in entries]
    if ranks != sorted(ranks):
        _reject(
            "assumption_ledger is not sorted by severity; the renderer leads "
            "with the first entries, so an invalidating assumption below a "
            "confidence-only one is buried"
        )

    # Completeness first: a ledger that dropped an assumption also has a stale
    # count, and "you are missing this assumption" is the useful reject.
    _check_estimator_channel(entries, declared)
    _check_channel(entries, owed_edges, "structural_edge", "proposal edge")
    _check_channel(entries, owed_priors, "parameter", "LLM theta prior")
    _check_channel(entries, owed_forms, "functional_form", "audited mechanism")
    _check_summary(ledger, entries)


# --- the four channels the ledger owes ----------------------------------------


def _owed_proposal_edges(result: dict) -> tuple[str, ...]:
    """One entry per load-bearing proposal edge. The gap report already did the
    load-bearing analysis; a proposed-but-unused edge is not owed."""
    report = result.get("data_gap_report") or {}
    return tuple(
        g.get("description", "")
        for g in report.get("gaps") or ()
        if g.get("kind") == "unverified_proposal_edge_on_query_path"
    )


def _owed_theta_priors(extensions: dict) -> tuple[str, ...]:
    review = extensions.get("llm_proposed_review") or {}
    return tuple(
        str(p.get("key")) for p in review.get("probabilities") or ()
    )


def _owed_mechanisms(extensions: dict) -> tuple[str, ...]:
    mech = extensions.get("mechanism_audit") or {}
    return tuple(str(m.get("form")) for m in mech.get("mechanisms") or ())


# --- checks -------------------------------------------------------------------


def _check_summary(ledger: dict, entries: list) -> None:
    summary = str(ledger.get("summary") or "")
    if not summary:
        _reject("assumption_ledger carries no summary")
    n_inval = sum(1 for e in entries if e["severity"] == "invalidating")
    n_other = len(entries) - n_inval
    if f"依赖 {len(entries)} 条假设" not in summary:
        _reject(
            f"assumption_ledger summary does not state the {len(entries)} "
            f"entries it carries: {summary!r}"
        )
    if n_inval and f"{n_inval} 条一旦不成立" not in summary:
        _reject(
            f"assumption_ledger summary undercounts the {n_inval} invalidating "
            f"entries: {summary!r}"
        )
    if n_other and f"{n_other} 条影响形状" not in summary:
        _reject(
            f"assumption_ledger summary undercounts the {n_other} non-"
            f"invalidating entries: {summary!r}"
        )


def _check_estimator_channel(entries: list, declared: tuple) -> None:
    if not declared:
        return
    from_estimator = {
        str(e.get("id")) for e in entries
        if e.get("provenance") == "estimator_declared"
    }
    if not from_estimator:
        # The estimator may instead have declared structured identification
        # assumptions, which are the same statements in better words.
        if any(e.get("layer") == "identification" for e in entries):
            return
        _reject(
            f"the estimate declares {len(declared)} assumption(s) and the "
            "assumption_ledger carries neither them nor any structured "
            "identification entry; they are absent from the surface the "
            "renderer leads with"
        )
    missing = [str(a) for a in declared if str(a) not in from_estimator]
    if missing:
        _reject(
            "assumption_ledger drops estimator-declared assumption(s) "
            f"{missing!r}"
        )
    invented = from_estimator - {str(a) for a in declared}
    if invented:
        _reject(
            "assumption_ledger carries estimator_declared entrie(s) the "
            f"estimate never declared: {sorted(invented)!r}"
        )


def _check_channel(entries: list, owed: tuple, layer: str, what: str) -> None:
    if not owed:
        return
    got = sum(1 for e in entries if e.get("layer") == layer)
    if got < len(owed):
        _reject(
            f"assumption_ledger carries {got} {layer} entrie(s) for "
            f"{len(owed)} {what}(s); the difference is silently undisclosed"
        )
