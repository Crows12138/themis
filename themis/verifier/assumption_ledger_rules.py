"""Independent audit of ``extensions.assumption_ledger``.

The ledger is the surface both ``output.analysis_report`` and the
``response_rendering.md`` bridge lead with — everything the answer takes on
faith, ranked by how it dies if it is false. Its failure mode is therefore
one-sided: an assumption that never reaches it is indistinguishable, to every
consumer, from an assumption nobody makes. This module re-derives what the
ledger owes from the channels that feed it and rejects UNDER-disclosure.

What it audits:

- **Completeness of the estimator channel.** ``numeric_estimate.assumptions``
  is the one channel every estimator populates. The ledger must carry each of
  those declarations keyed by ``id`` — either flat, or as the estimator's own
  structured ``identification`` entry naming the same id, which says the same
  thing in better words. Carrying neither is the defect.
- **Completeness of the other three channels** — one entry per load-bearing
  proposal edge in the gap report, per LLM theta prior, per audited mechanism.
- **No fabrication.** Any entry attributed to the estimator whose ``id`` the
  estimate never declared is invented. This keys on the attribution and not on
  which of the two channels carried it, so it now covers the structured
  entries too — under the old key a fabricated structured entry was outside
  the question being asked. An entry with no ``id`` names no declaration and
  is not subject to it.
- **Nothing handed to the caller that they never supplied.** ``caller_asserted``
  is the one attribution that gives the reader something to DO — withdraw it
  and the answer comes back wider — so it is re-derived rather than believed:
  the answer has to carry its own record of the input, and a pair of legitimate
  values is otherwise indistinguishable from a true one.
- **Internal coherence.** Entries sorted by severity; the summary's counts
  matching the entries; every entry's severity being the one its layer implies
  — identification failing means the number is not a causal effect at all, so
  an identification entry ranked anything milder is incoherent, and the same
  holds for the other four.

The severity was once out of scope here, on the reading that which severity an
assumption ID deserves is curation and not derivable from the envelope. It is
derivable: it is the grade of the layer sitting next to it in the same entry,
and it agreed with that layer on all 3252 entries of one suite run before
anything enforced it. What is curation is the LAYER — which part of the answer
a given assumption holds up — and that is still not second-guessed here.

What it deliberately does NOT audit: which layer a particular assumption ID
belongs to. That judgement is recorded in ``output.assumption_glossary``;
re-stating the table here would be transcription, not verification.

**Independence pin:** this module MUST NOT import from
``themis.output.result_orchestrator`` or ``themis.output.assumption_glossary``.
"""
from __future__ import annotations

from .errors import VerificationError

_SEVERITIES = ("invalidating", "distorting", "confidence_only")
_RANK = {s: i for i, s in enumerate(_SEVERITIES)}

#: How badly each layer's failure kills the conclusion, restated here from
#: what the layer MEANS rather than read off the entry.
#:
#: A layer already says which part of the answer stops being true, and a
#: severity grades how badly that kills it — so the second follows from the
#: first and disagreeing is incoherent, not a curation choice. Only the
#: identification row was stated before, which left a functional-form
#: assumption free to be ranked invalidating and an identification one free
#: to be relabelled a shape concern the average survives; the relabelled
#: entry keeps a legal severity and reads as a milder assumption than it is.
#: Measured over one suite run, all 3252 entries agree with these five.
#:
#: The producer now derives the severity from the layer instead of writing
#: it, which does not make this redundant: a build that lost the derivation,
#: or an envelope from elsewhere, is exactly what an independent audit is
#: for, and the two tables are pinned equal by a test rather than shared.
_SEVERITY_OF_LAYER = {
    "identification": "invalidating",
    "structural_edge": "invalidating",
    "functional_form": "distorting",
    "parameter": "distorting",
    "confidence": "confidence_only",
}

_WHY_THAT_SEVERITY = {
    "identification": "identification failing means the number is not a causal "
                      "effect at all",
    "structural_edge": "an edge the answer path runs through being unestablished "
                       "means the path may not exist",
    "functional_form": "a wrong fitted shape moves magnitude and curvature while "
                       "the estimand stays right",
    "parameter": "a supplied number moves the answer with it, and no further",
    "confidence": "the interval is the only thing computed from it, so being "
                  "wrong here is a wrong width around an untouched point",
}

#: Which ``(layer, provenance)`` pairs each producer of a ledger entry may
#: write, restated here rather than imported.
#:
#: The rows are producers because a producer is what fixes the pair, and
#: the pair is the checkable part: every value of both vocabularies is
#: legitimate somewhere, so membership alone cannot tell a back-door
#: assumption relabelled as an LLM prior from an LLM prior. Asking instead
#: "could anything have written this pair" catches that, and catches the
#: values no vocabulary holds at all — an empty ``layer`` among them.
#:
#: Restated and not imported for the reason in this module's header: a
#: ledger re-derived from the vocabulary its producer chose is not an
#: independent audit. A test pins these rows equal to ``themis.ledger``.
_ADMISSIBLE_PAIRS = {
    "estimator_assumption": (
        ("identification", "functional_form", "confidence"),
        ("inherent", "caller_asserted"),
    ),
    "proposal_edge": (("structural_edge",), ("llm_proposal", "discovery")),
    "theta_prior": (("parameter",), ("llm_prior",)),
    "audited_mechanism": (("functional_form",), ("default",)),
}

_RULE = "assumption_ledger_check"


def _pair_is_writable(layer, provenance) -> bool:
    return any(
        layer in layers and provenance in provs
        for layers, provs in _ADMISSIBLE_PAIRS.values()
    )


def _reject(message: str) -> None:
    raise VerificationError(message, rule=_RULE)


def verify_assumption_ledger(result: dict) -> None:
    """Audit one result's assumption ledger. No-op when the result has none
    AND owes none; raises :class:`VerificationError` otherwise."""
    extensions = result.get("extensions") or {}
    ledger = extensions.get("assumption_ledger")
    estimate = result.get("numeric_estimate")
    declared = _declaration_channels(result, estimate)

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
        owed = _SEVERITY_OF_LAYER.get(e.get("layer"))
        if owed is not None and e["severity"] != owed:
            _reject(
                f"assumptions[{i}] is a {e.get('layer')} assumption ranked "
                f"{e['severity']!r}; {_WHY_THAT_SEVERITY[e['layer']]}, which is "
                f"{owed!r} by definition"
            )
        if not _pair_is_writable(e.get("layer"), e.get("provenance")):
            _reject(
                f"assumptions[{i}] is layer {e.get('layer')!r} from "
                f"{e.get('provenance')!r}, which no producer of a ledger "
                f"entry writes; both fields reach the reader, so a pair "
                f"nothing could have assembled is a claim about where this "
                f"assumption came from that is not true of any channel"
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
    _check_caller_assertions(result, entries)
    _check_channel(entries, owed_edges, "structural_edge", "proposal edge")
    _check_channel(entries, owed_priors, "parameter", "LLM theta prior")
    _check_channel(entries, owed_forms, "functional_form", "audited mechanism")
    _check_summary(ledger, entries)


# --- the four channels the ledger owes ----------------------------------------


def _declaration_channels(result: dict, estimate) -> tuple[str, ...]:
    """Every assumption someone declared, by id, whichever list holds it.

    Two do. ``numeric_estimate.assumptions`` is the estimator's own and every
    estimator populates it. The second belongs to another author entirely: an
    outcome measurement-error assessment states the premises under which its
    split of the residual variance means anything, and the ledger folds those
    in unconditionally.

    They are unioned rather than checked apart because the question here is
    "did anyone declare this", and asking instead which list it came from is
    what let the second one go unchecked in both directions — nothing verified
    that its premises reached the ledger, and nothing verified that a premise
    on the ledger came from it.
    """
    ids = list((estimate or {}).get("assumptions") or ())
    block = result.get("outcome_error")
    if isinstance(block, dict):
        ids += [a for a in (block.get("assumptions") or ()) if isinstance(a, str)]
    return tuple(ids)


def _caller_supplied(result: dict) -> tuple[str, ...]:
    """Which caller inputs THIS envelope records, re-derived from it.

    ``caller_asserted`` is the strongest actionable thing a ledger line can
    say — this one is yours, withdraw it and the answer comes back wider
    rather than gone — so it is the attribution worth re-deriving, and the
    only one whose failure hands the reader an action that is not theirs to
    take. Every such line has to trace to something the caller actually put
    on the query, and each field below is the answer's own record that they
    did: an assumption pinning a point out of its bounds leaves that mark on
    the block it pinned.
    """
    ext = result.get("extensions") or {}
    estimate = result.get("numeric_estimate") or {}
    bounds = result.get("bounds_result") or {}
    records = []
    for block, field in (
        (ext.get("causation"), "monotonic"),
        (estimate.get("probabilities_of_causation"), "monotonic"),
        (ext.get("counterfactual_cell"), "monotonicity"),
        (estimate.get("counterfactual_cell"), "monotonicity"),
    ):
        if isinstance(block, dict) and block.get(field):
            records.append(f"{field} on the answer it pinned")
    if isinstance(bounds, dict) and bounds.get("method") == "manski_tamer_monotonicity":
        records.append("a monotone-treatment-response bounds method")
    return tuple(records)


def _check_caller_assertions(result: dict, entries: list) -> None:
    """No line may be handed to the caller that the caller never supplied."""
    claimed = [e for e in entries if e.get("provenance") == "caller_asserted"]
    if not claimed:
        return
    block = result.get("outcome_error")
    measured = {
        str(a) for a in ((block.get("assumptions") or ())
                         if isinstance(block, dict) else ())
    }
    records = _caller_supplied(result)
    for e in claimed:
        # A measurement-error premise is about the model the caller attached,
        # and that block lists its own premises by id — so it is its own
        # record and needs no other.
        if str(e.get("id") or "") in measured:
            continue
        if not records:
            _reject(
                f"assumption_ledger hands {str(e.get('id') or e.get('claim'))!r} "
                "to the caller, but nothing in this answer records the caller "
                "supplying anything — a line marked as theirs to withdraw is an "
                "action the reader cannot actually take"
            )


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
    """Every declaration the estimate made is on the ledger under its own id.

    Which channel carried it is not part of the test. A declaration may reach
    the ledger flat or as the structured identification entry that names it —
    what must not happen is that it reaches neither.

    This used to accept any ledger carrying an identification entry, on the
    reasoning that structured entries restate the flat list. They restate
    PART of it: nineteen families also declare which weights, which
    interval, which substitution estimator, and those were dropped. The
    escape hatch is gone because the producer now says which flat
    declaration each structured entry stands for, so the question is
    decidable from the envelope instead of being assumed.
    """
    if not declared:
        return
    on_ledger = {str(e["id"]) for e in entries if e.get("id")}
    missing = [str(a) for a in declared if str(a) not in on_ledger]
    if missing:
        _reject(
            "assumption_ledger drops estimator-declared assumption(s) "
            f"{missing!r}"
        )
    # Attributed to the estimator — both provenances a ledger may carry for
    # one, since a structured spec and the flat declaration it restates are
    # the same assumption and the reader is told the same thing about both.
    # Keying on the attribution rather than on the channel is what lets this
    # see a fabricated STRUCTURED entry, which the channel key could not:
    # measured over one suite run, all 700 structured entries name a
    # declaration the estimate made, so a spec naming one it did not make is
    # the anomaly this is for. A spec with no flat twin says so by omitting
    # the id.
    invented = {
        str(e.get("id")) for e in entries
        if e.get("id") and e.get("provenance") in ("inherent", "caller_asserted")
    } - {str(a) for a in declared}
    if invented:
        _reject(
            "assumption_ledger attributes to the estimator assumption(s) it "
            f"never declared: {sorted(invented)!r}"
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
