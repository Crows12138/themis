"""Independent audit of ``extensions.assumption_ledger``.

The ledger is the surface both ``output.analysis_report`` and the
``response_rendering.md`` bridge lead with — everything the answer takes on
faith, ranked by how it dies if it is false. Its failure mode is therefore
one-sided: an assumption that never reaches it is indistinguishable, to every
consumer, from an assumption nobody makes. This module re-derives what the
ledger owes from the channels that feed it and rejects UNDER-disclosure.

What it audits:

- **Completeness of the declaration channels.** ``numeric_estimate.assumptions``
  is the one channel every estimator populates; an outcome measurement-error
  assessment and an identification route each declare their own premises
  beside it. The ledger must carry each of those declarations keyed by ``id``
  — either flat, or as the estimator's own structured ``identification`` entry
  naming the same id, which says the same thing in better words. Carrying
  neither is the defect.
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
- **Internal coherence.** Entries sorted by severity; every entry's severity
  being the one its layer implies — identification failing means the number is
  not a causal effect at all, so an identification entry ranked anything milder
  is incoherent, and the same holds for the other four.

  There was a third: the ledger's one-line summary carried two counts of the
  entries beside it, and this file checked them by searching that line for
  ``依赖 {n} 条假设``. A rule that can only be written in one language is a
  rule about a field the kernel wrote in one language, and the check and the
  defect were the same fact — so the counts are not stored and there is
  nothing here to re-derive them from.

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

from typing import NoReturn

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
        ("identification", "confidence"),
        ("inherent", "caller_asserted"),
    ),
    "identification_premise": (("identification",), ("inherent",)),
    "proposal_edge": (("structural_edge",), ("llm_proposal", "discovery")),
    "theta_prior": (("parameter",), ("llm_prior",)),
    # The shape choice, and the only producer of a functional_form line. Who
    # settled a form is a property of the RUN, so the id is not what answers:
    # the same one is the method's definition where nothing takes a ``model=``
    # and the estimator's resolved default where something does. All three
    # answers are legitimate here and nowhere else.
    "audited_mechanism": (
        ("functional_form",),
        ("inherent", "default", "caller_asserted"),
    ),
}

_RULE = "assumption_ledger_check"


def _pair_is_writable(layer, provenance) -> bool:
    return any(
        layer in layers and provenance in provs
        for layers, provs in _ADMISSIBLE_PAIRS.values()
    )


def _reject(message: str) -> NoReturn:
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
        # An entry with no declared layer — or one that is not a string —
        # owes no particular severity: the table is keyed by the declared
        # layer names, and a lookup that misses said exactly that. The
        # ``layer`` field itself is checked below, against provenance.
        layer = e.get("layer")
        owed = _SEVERITY_OF_LAYER.get(layer) if isinstance(layer, str) else None
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
    _check_the_line_says_what_the_block_says(entries, extensions)
    _check_one_run_settles_one_shape_per_lever(extensions)


# --- the four channels the ledger owes ----------------------------------------


#: Where an identification ROUTE states what its own claim rests on, spelled
#: from the schema rather than imported: this file audits the ledger and a
#: list of sites shared with the producer would make the audit a restatement.
_ROUTE_PREMISE_SITES = (
    ("longitudinal_identification", "assumptions"),
    ("mediation_decomposition", "nde_nie", "assumptions"),
    ("mediation_decomposition", "cde", "assumptions"),
    ("mediation_joint_decomposition", "nde_nie", "assumptions"),
    ("mediation_joint_decomposition", "cde", "assumptions"),
)


def _declaration_channels(result: dict, estimate) -> tuple[str, ...]:
    """Every assumption someone declared, by id, whichever list holds it.

    Three do. ``numeric_estimate.assumptions`` is the estimator's own and
    every estimator populates it. The second belongs to another author
    entirely: an outcome measurement-error assessment states the premises
    under which its split of the residual variance means anything. The third
    is the identification layer speaking for itself — a mediation or
    longitudinal route lists the premises "identifiable" is conditional on —
    and it is the only one of the three that exists when no estimator ran,
    which is why its absence was invisible: on every path that produced a
    number the estimator declared the same ids flat, and on the paths that
    produced none the ledger was simply quieter than the envelope.

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
    extensions = result.get("extensions") or {}
    for site in _ROUTE_PREMISE_SITES:
        node = extensions
        for step in site:
            node = node.get(step) if isinstance(node, dict) else None
        if isinstance(node, list):
            ids += [a for a in node if isinstance(a, str)]
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
    bounds = result.get("bounds_results") or ()
    records = []
    for block, field in (
        (ext.get("causation"), "monotonic"),
        (estimate.get("probabilities_of_causation"), "monotonic"),
        (ext.get("counterfactual_cell"), "monotonicity"),
        (estimate.get("counterfactual_cell"), "monotonicity"),
    ):
        if isinstance(block, dict) and block.get(field):
            records.append(f"{field} on the answer it pinned")
    if any(
        isinstance(b, dict) and b.get("method") == "manski_tamer_monotonicity"
        for b in bounds
    ):
        records.append("a monotone-treatment-response bounds method")
    # The caller's own ``model=``. The envelope has recorded it all along and
    # nothing read it, because until a shape line could say ``caller_asserted``
    # there was nothing to trace: the ledger answered that question off the id
    # and the id never names a caller. Read from the context and NOT from the
    # mechanism block, which is the surface this audits — taking the block's
    # word for who settled the form would confirm it against itself.
    context = result.get("estimation_context") or {}
    preference = str(context.get("model_preference") or "auto")
    if preference != "auto":
        records.append(f"a model preference of {preference!r}")
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


#: The shapes that are alternative POSITIONS OF ONE LEVER, by lever.
#:
#: Restated and not imported, for the reason in this module's header. What it
#: restates is no longer a list of which ids stand outside the run's
#: resolution — #426 moved that to the estimator, the only thing that knows
#: its own levers — but the fact that list was standing in for: a lever has
#: one position, so a block naming two of its values is describing a fit that
#: was both.
_ONE_PER_LEVER: tuple[tuple[str, ...], ...] = (
    ("linear_outcome_regression", "logit_outcome_regression"),
    ("linear_outcome_regression_with_saturated_treatment_interactions",
     "logit_outcome_regression_with_saturated_treatment_interactions"),
    ("hajek_stabilized_weights", "horvitz_thompson_weights"),
    ("logit_mediator_model",
     "linear_mediator_model_with_normal_residual_variance"),
    ("linear_in_treatment_partially_linear_dml",
     "linear_in_treatment_with_nonparametric_nuisance",
     "dose_binned_and_effects_estimated_per_bin"),
)


# --- checks -------------------------------------------------------------------


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


def _check_the_line_says_what_the_block_says(entries: list,
                                            extensions: dict) -> None:
    """A shape assumption's ledger line and its block entry answer the same
    question, so the one thing that cannot be true is that they differ.

    No table of this module's own is needed to ask it, which is what makes it
    an audit rather than a restatement: the block says who settled the shape
    for whoever re-derives the answer, the line beside it says the same thing
    in the reader's words, and both are written by the same producer for two
    different readers. It is also exactly the failure it exists for — the line
    read "required by the method itself" about a form the caller had named in
    the call.
    """
    mech = extensions.get("mechanism_audit") or {}
    by_id = {str(e.get("id")): e for e in entries if e.get("id")}
    for m in mech.get("mechanisms") or ():
        for named in m.get("assumptions") or ():
            if not isinstance(named, dict):
                _reject(
                    f"mechanism_audit names shape assumption {named!r} as a "
                    f"bare {type(named).__name__}; an id on its own cannot "
                    "say who settled the shape, which is what the block is "
                    "for"
                )
            text = str(named.get("id"))
            line = by_id.get(text)
            if line is None:
                _reject(
                    f"mechanism_audit discloses shape assumption {text!r} and "
                    "the assumption_ledger has no line for it"
                )
            if line.get("provenance") != named.get("settled_by"):
                _reject(
                    f"assumption_ledger says {text!r} came from "
                    f"{line.get('provenance')!r} and the mechanism_audit "
                    f"beside it says {named.get('settled_by')!r}; both reach "
                    "the reader, and they answer the same question"
                )


def _check_one_run_settles_one_shape_per_lever(extensions: dict) -> None:
    """One lever has one position, so a block names one of its values.

    What this catches that the check above cannot: the two surfaces agreeing
    with each other on an answer no run could have produced. A block naming
    the linear outcome model beside the logit one is describing a single fit
    that was both, and it is describing it consistently everywhere — the
    per-id origins can be whatever they like and the pair is still impossible.

    It replaces a check that asked the ids to AGREE about who settled them,
    which held only while a run had one answer to give. #426 gave each lever
    its own, so a propensity floor the caller named now stands, rightly,
    beside a link nobody did — and the old check would have refused that,
    while passing a linear-and-logit block whose two ids agreed.
    """
    mech = extensions.get("mechanism_audit") or {}
    for m in mech.get("mechanisms") or ():
        named = {str(a.get("id")) for a in m.get("assumptions") or ()
                 if isinstance(a, dict)}
        for lever in _ONE_PER_LEVER:
            both = sorted(named.intersection(lever))
            if len(both) > 1:
                _reject(
                    f"mechanism_audit says the shape of "
                    f"{str(m.get('form'))!r} is {both} at once; those are "
                    "positions of ONE lever, and one run sets it once"
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
