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
- **Nothing handed to the caller that they never supplied.** Two attributions
  give the reader something to DO — ``caller_asserted``, where withdrawing it
  brings the answer back wider, and ``caller_chose``, where choosing again
  moves it — so both are re-derived rather than believed: the answer has to
  carry its own record of the input, and a pair of legitimate values is
  otherwise indistinguishable from a true one. They are checked separately
  because the records that back them are different records, and a pass
  accepting either for either would confirm each against the other's
  evidence.
- **Every verdict, re-derived from the numbers it was read off.** A line may
  say a check made on this run refuted it. That is the strongest sentence the
  ledger can carry and it is the one a producer could simply assert, so it is
  not believed: the outcome is re-read here out of the estimate's own record
  and the two must agree, including about WHICH check governs where a run made
  two of them. The under-disclosure side is checked in the same pass — an
  answer holding the record of a check, on a line the check adjudicates, that
  says nothing about it, is the defect this whole module is shaped around.
- **Internal coherence.** Entries sorted by severity, and a refuted line ahead
  of its unrefuted neighbours of the same grade; every entry's severity being
  the one its layer implies — identification failing means the number is not a
  causal effect at all, so an identification entry ranked anything milder is
  incoherent, and the same holds for the other four.

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

from collections.abc import Callable, Mapping
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


def _over_identification(result: dict) -> dict:
    block = (result.get("numeric_estimate") or {}).get("over_identification")
    return block if isinstance(block, dict) else {}


def _sargan_says_refuted(result: dict) -> bool | None:
    oid = _over_identification(result)
    return (bool(oid["rejected_at_0_05"]) if "rejected_at_0_05" in oid
            else None)


def _hansen_says_refuted(result: dict) -> bool | None:
    oid = _over_identification(result)
    return (bool(oid["hansen_rejected_at_0_05"])
            if "hansen_rejected_at_0_05" in oid else None)


def _margin_weights_say_refuted(result: dict) -> bool | None:
    block = (result.get("numeric_estimate") or {}).get("acr_decomposition")
    if not isinstance(block, dict) or "monotonicity_refuted" not in block:
        return None
    return bool(block["monotonicity_refuted"])


def _fitted_propensity_says_refuted(result: dict) -> bool | None:
    """Judged against the threshold the RECORD carries.

    Not one restated here: this pass and the producer would then hold two
    copies of a number the estimation layer chose, and the first retune of
    the band would put the ledger's verdict and the gap beside it on
    different sides of one frame.
    """
    block = (result.get("numeric_estimate") or {}).get("fitted_overlap")
    if not isinstance(block, dict):
        return None
    share, threshold = block.get("share_outside"), block.get("threshold")
    if not isinstance(share, (int, float)) or not isinstance(
            threshold, (int, float)):
        return None
    return float(share) > float(threshold)


def _arm_counts_say_refuted(result: dict) -> bool | None:
    block = (result.get("numeric_estimate") or {}).get("stratum_support")
    if not isinstance(block, dict):
        return None
    cells, supported = block.get("cells"), block.get("supported")
    if not isinstance(cells, int) or not isinstance(supported, int):
        return None
    return supported < cells


#: Every check a run can make against a declaration on this ledger: which
#: declarations it adjudicates, whether passing it SETTLES them, and where in
#: the envelope this pass re-reads the outcome for itself.
#:
#: Restated and not imported, for the reason in this module's header, and the
#: reason bites harder here than anywhere else in the file: a verdict is the
#: one field a producer could fill with a sentence and no evidence, and
#: "refuted" is the sentence a reader acts on. Re-reading the estimate's own
#: numbers is what makes the field a disclosure instead of a claim. A test
#: pins the ids and the settles-it flags equal to ``themis.ledger``; the
#: readers above are this module's own, which is the part that must not be
#: shared.
#:
#: Ordered, and later rows win — weaker witness first, in both pairs. A run
#: holding both over-identification statistics is governed by the robust one,
#: so a line reporting the homoskedastic verdict where the robust one exists
#: is reporting the weaker test. A run that could count the cells of its
#: adjustment set is governed by the count rather than by the fitted
#: propensity, for the plainer reason that the count IS the condition and the
#: fit only estimates it. Both are disagreements worth raising rather than
#: formatting choices.
#:
#: ``a_pass_settles_it`` is the column that decides what a PASS is worth, and
#: the three refutation checks answer it differently from the count. Each of
#: them can only fail to fire, and a ledger saying "held" on that strength
#: would claim the data established a premise it merely did not manage to
#: disprove. The count is not a refutation check: every cell holding both arms
#: IS the condition, so a pass settles it.
_CHECKS: tuple[tuple[str, tuple[str, ...], bool,
                     Callable[[dict], bool | None]], ...] = (
    ("fitted_propensity_range", ("positivity_overlap_of_treatment_arms",),
     False, _fitted_propensity_says_refuted),
    ("stratum_arm_counts", ("positivity_overlap_of_treatment_arms",),
     True, _arm_counts_say_refuted),
    ("sargan",
     ("overidentifying_restrictions_testable_via_sargan_homoskedastic",
      "overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j"),
     False, _sargan_says_refuted),
    ("robust_hansen_j",
     ("overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j",),
     False, _hansen_says_refuted),
    ("acr_margin_weights",
     ("monotonicity_refutable_dose_response_same_direction_for_all_units",),
     False, _margin_weights_say_refuted),
)


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
    # ``parameter`` sits here and ``functional_form`` does not, and the
    # asymmetry is the point: a numeric input names its own author — there
    # is one id for "the caller supplied it" and another for "the estimator
    # fell back" — while a shape's id is the same string whoever settled it.
    # ``default`` rides in on the same reasoning, and only for ids that say
    # where "nobody chose this" is recorded; the checks below hold both
    # directions of that claim.
    "estimator_assumption": (
        ("identification", "confidence", "parameter"),
        ("inherent", "caller_asserted", "caller_chose", "default"),
    ),
    "identification_premise": (("identification",), ("inherent",)),
    "proposal_edge": (("structural_edge",), ("llm_proposal", "discovery")),
    "theta_prior": (("parameter",), ("llm_prior",)),
    # The shape choice, and the only producer of a functional_form line. Who
    # settled a form is a property of the RUN, so the id is not what answers:
    # the same one is the method's definition where nothing takes a ``model=``
    # and the estimator's resolved default where something does. Both caller
    # answers are legitimate too, and they differ in what a reader may do
    # next: a form the estimator could have resolved without them falls back
    # when withdrawn, and a form nothing but the caller can supply — where
    # the data cannot distinguish two estimands — leaves no answer here when
    # withdrawn rather than a wider one. All four are legitimate here and
    # nowhere else.
    "audited_mechanism": (
        ("functional_form",),
        ("inherent", "default", "caller_asserted", "caller_chose"),
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
        claim = e.get("claim")
        if not isinstance(claim, list) or not claim:
            _reject(f"assumptions[{i}] carries an empty claim")
        for j, one in enumerate(claim):
            # A statement with no token is a line with nothing to say, which
            # an empty string used to be. The vocabulary is checked too: a
            # token without one names a member of no particular set, and the
            # reader's lookup would fall through to printing the token.
            if not isinstance(one, Mapping) or not str(
                    one.get("token") or "").strip() or not str(
                    one.get("vocabulary") or "").strip():
                _reject(
                    f"assumptions[{i}].claim[{j}] is not a statement; a "
                    f"ledger line names which sentence it is and which set "
                    f"that sentence came from, so a reader in any language "
                    f"can be handed it"
                )

    # Severity first, then a refuted line ahead of its unrefuted neighbours of
    # the same grade. The second key is not a second grade: what a refuted
    # premise costs the answer is still whatever its layer costs. What it
    # changes is the order the reader meets them in, and the reader meets the
    # head of this list — so an answer standing on a premise its own data
    # refused, printed sixth, is the same burial one rung down.
    ranks = [(_RANK[e["severity"]],
              0 if str((e.get("checked") or {}).get("verdict")) == "refuted"
              else 1)
             for e in entries]
    if [r for r, _ in ranks] != sorted(r for r, _ in ranks):
        _reject(
            "assumption_ledger is not sorted by severity; the renderer leads "
            "with the first entries, so an invalidating assumption below a "
            "confidence-only one is buried"
        )
    if ranks != sorted(ranks):
        _reject(
            "assumption_ledger puts a refuted assumption below an unrefuted "
            "one of the same severity; a premise this run's own data refused "
            "is the first thing about the answer resting on it"
        )

    # Completeness first: a ledger that dropped an assumption also has a stale
    # count, and "you are missing this assumption" is the useful reject.
    _check_estimator_channel(entries, declared)
    _check_verdicts(result, entries)
    _check_caller_assertions(result, entries)
    _check_caller_choices(result, entries)
    _check_estimator_defaults(result, entries)
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


def _recorded_channels(result: dict) -> tuple[dict, ...]:
    """Every record on this answer that could witness a caller's choice.

    Two sources today and neither is privileged: the ``measurement_channel``
    the derivation carries, and the estimator block a family writes when its
    levers are not the channel's. What generalises is the SOURCE and not the
    predicates — each one already knows the shape of the record it reads, so
    a predicate written for a channel simply answers no to a block and the
    other way round. Loosening the predicates instead would have made every
    new line true on some older line's evidence, which is the failure this
    registry exists to prevent.

    The channels are read through the serializer rather than by hand, so
    this pass and the one that wrote the record agree about the format by
    construction. A payload that will not decode is the derivation rule's
    finding, not this one's — and it is not a record of a choice either, so
    it contributes nothing here.
    """
    from .serialization import derivation_from_dict

    records: list[dict] = []
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, dict):
        block = estimate.get("simex")
        if isinstance(block, dict):
            records.append(block)

    payload = result.get("derivation")
    if not isinstance(payload, dict):
        return tuple(records)
    try:
        steps = derivation_from_dict(payload)
    except Exception:
        return tuple(records)
    records.extend(
        step.inputs["measurement_channel"] for step in steps
        if isinstance(step.inputs.get("measurement_channel"), dict)
    )
    return tuple(records)


def _a_grouping_was_declared(channel: dict) -> bool:
    """A coarsening in force is a grouping with more than one level in it.

    The identity grouping is the ABSENCE of a choice rather than a choice of
    identity, which is why this asks about the group sizes and not about
    whether the field is there: every discrete run carries one.
    """
    return any(
        isinstance(groups, tuple)
        and any(isinstance(g, tuple) and len(g) > 1 for g in groups)
        for groups in (channel.get("z_groups"), channel.get("w_groups"))
    )


def _design_was_declared(design) -> bool:
    """A basis family at a dimension for every variable this design expands.

    Where a bridge is assumed to live has no defensible default — unlike the
    penalty beside it — so a run that has one is a run where somebody named
    it. Read over every factor of every term rather than off the side as a
    whole: a design is several declarations, and one of them being present
    says nothing about the rest.
    """
    if not isinstance(design, (tuple, list)) or not design:
        return False
    return all(
        isinstance(term, (tuple, list)) and term
        and all(isinstance(f, dict) and bool(f.get("family")) for f in term)
        for term in design
    )


def _an_outcome_sieve_was_declared(channel: dict) -> bool:
    return _design_was_declared(channel.get("w_basis"))


def _a_treatment_sieve_was_declared(channel: dict) -> bool:
    block = channel.get("treatment_bridge")
    return isinstance(block, dict) and _design_was_declared(
        block.get("span_basis"))


def _a_treatment_bridge_was_solved(channel: dict) -> bool:
    """The declaration AND the arms it was solved over.

    Two halves because a curve can carry the first without the second: the
    treatment bridge is identified level by level through an indicator, so
    a route that declared one and had no rows to weight would have a span
    on the record and no answer resting on it.
    """
    block = channel.get("treatment_bridge") or {}
    return (_a_treatment_sieve_was_declared(channel)
            and bool(block.get("arms") or block.get("treated")))


def _the_span_varies_with_the_treatment(channel: dict) -> bool:
    """A curve was solved, and its span is a function of the level.

    Both halves, because either alone attributes the wrong thing. The
    levels without the span naming them would be a curve whose shape
    nobody declared — nothing for the caller to have chosen. The span
    naming them without a curve would be a contrast, where how the bridge
    varies with the treatment is not a lever anyone was offered.
    """
    variable = channel.get("level_variable")
    if not channel.get("levels") or not isinstance(variable, str):
        return False
    design = channel.get("w_basis")
    if not isinstance(design, (list, tuple)):
        return False
    return any(isinstance(factor, dict)
               and factor.get("variable") == variable
               for term in design if isinstance(term, (list, tuple))
               for factor in term)


def _both_sieves_were_declared(channel: dict) -> bool:
    """The union line's evidence is BOTH spans, and that is not redundant.

    "At least one of these is right" is a claim the caller can only have made
    by naming two, and a ledger line offering it on the strength of one would
    be attributing to them a choice they were never given.
    """
    return (_an_outcome_sieve_was_declared(channel)
            and _a_treatment_bridge_was_solved(channel))


#: What each ``caller_chose`` line's evidence looks like on this answer.
#:
#: A registry and not a single predicate, because the attribution promises
#: something specific — "this one is yours, choose again and the number
#: moves" — and what backs it differs per line. It was one predicate while
#: there was one such line, and generalising it by loosening the predicate
#: would have made every new line true on the first line's evidence.
#:
#: An id absent from here is REFUSED rather than waved through: a line
#: offering the reader a lever whose record nobody has named is exactly the
#: shape this pass exists to catch.
_CHOICE_IS_RECORDED_BY = {
    "latent_cardinality_k_correct_and_the_declared_coarsening_folds_each_"
    "proxy_to_k_levels": _a_grouping_was_declared,
    "the_outcome_bridge_lies_in_the_span_of_the_declared_sieve":
        _an_outcome_sieve_was_declared,
    "the_treatment_bridge_lies_in_the_span_of_the_declared_sieve":
        _a_treatment_sieve_was_declared,
    "at_least_one_of_the_two_bridges_lies_in_its_declared_span":
        _both_sieves_were_declared,
    "the_bridge_varies_with_the_treatment_as_the_declared_basis_does":
        _the_span_varies_with_the_treatment,
    "regularisation_lambda_chosen_by_the_caller":
        lambda channel: channel.get("ridge_was_declared") is True,
    "treatment_bridge_regularisation_lambda_chosen_by_the_caller":
        lambda channel: (channel.get("treatment_bridge") or {}).get(
            "ridge_was_declared") is True,
    # The two levers a simulation-extrapolation run has, and each line names
    # the position as well as the lever — so the record has to agree about
    # both. A block recording a named `rational` does not back a line
    # claiming the caller chose `quadratic`.
    **{
        f"simex_estimand_is_the_exposure_coefficient_in_a_{model}":
            (lambda model: lambda block: (
                block.get("outcome_model") == model
                and block.get("outcome_model_was_declared") is True))(model)
        for model in ("linear", "logistic")
    },
    **{
        f"simex_extrapolant_declared_{family}":
            (lambda family: lambda block: (
                block.get("extrapolant") == family
                and block.get("extrapolant_was_declared") is True))(family)
        for family in ("linear", "quadratic", "rational")
    },
}


#: What each ``default`` line's evidence looks like, in the same shape and
#: for the same reason as the table above.
#:
#: "Nobody chose this" is a claim about the caller as much as
#: ``caller_chose`` is, and it is the one that goes unnoticed when wrong: a
#: run that laundered a caller's own number into the estimator's default
#: would tell the reader there is nothing here to argue with. So it is
#: checked from the other side, against the same record.
_DEFAULT_IS_RECORDED_BY = {
    "regularisation_lambda_defaulted_by_the_estimator":
        lambda channel: channel.get("ridge_was_declared") is False,
    "treatment_bridge_regularisation_lambda_defaulted_by_the_estimator":
        lambda channel: (channel.get("treatment_bridge") or {}).get(
            "ridge_was_declared") is False,
    # The mirrors of the two simulation-extrapolation levers above. Same
    # ids, other side: one id can legitimately arrive under either
    # attribution, and which one is true is a fact about the run that the
    # block records separately from its reading of it.
    **{
        f"simex_estimand_is_the_exposure_coefficient_in_a_{model}":
            (lambda model: lambda block: (
                block.get("outcome_model") == model
                and block.get("outcome_model_was_declared") is False))(model)
        for model in ("linear", "logistic")
    },
    **{
        f"simex_extrapolant_declared_{family}":
            (lambda family: lambda block: (
                block.get("extrapolant") == family
                and block.get("extrapolant_was_declared") is False))(family)
        for family in ("linear", "quadratic", "rational")
    },
}


def _check_estimator_defaults(result: dict, entries: list) -> None:
    """No line may say nobody chose it without the answer showing that.

    Every line whose id names a record is asked, and the table above is
    what decides which those are. A mechanism audit's ``default`` used to
    be outside the question on the grounds that it carries only its own
    resolution — a form's provenance read back from the field that IS that
    provenance confirms nothing. That is a property of a family rather than
    of the channel, and it stops being true the moment a family records
    which lever the caller pulled as a fact beside what the lever settled
    at: there is then a second record, and asking the claim against it is
    the same check the estimator-channel rows get.
    """
    claimed = [
        e for e in entries
        if e.get("provenance") == "default"
        and str(e.get("id") or "") in _DEFAULT_IS_RECORDED_BY
    ]
    if not claimed:
        return
    channels = _recorded_channels(result)
    for entry in claimed:
        line = str(entry.get("id") or "")
        if not any(_DEFAULT_IS_RECORDED_BY[line](c) for c in channels):
            _reject(
                f"assumption_ledger says nobody chose {line!r}, but this "
                f"answer's own record shows the choice being made — a line "
                f"attributed to the estimator that the caller in fact "
                f"supplied is a lever the reader is told they do not have"
            )
            return


def _check_caller_choices(result: dict, entries: list) -> None:
    """No line may be handed to the caller as their CHOICE without the
    answer recording the choice that line names.

    Split from :func:`_check_caller_assertions` rather than folded into it
    because the two attributions promise a reader different things — one
    says withdrawing widens the answer, the other says choosing again moves
    it — and the records that would back them are different records. A pass
    that accepted either record for either attribution would confirm each
    against the other's evidence. The same argument runs one level down and
    is why the evidence is per-id: a run that declared a basis has not
    thereby declared a penalty, and a pass that took either for both would
    launder one choice into two.
    """
    claimed = [e for e in entries if e.get("provenance") == "caller_chose"]
    if not claimed:
        return
    channels = _recorded_channels(result)
    for entry in claimed:
        line = str(entry.get("id") or entry.get("claim") or "")
        backs = _CHOICE_IS_RECORDED_BY.get(line)
        if backs is None:
            _reject(
                f"assumption_ledger hands {line!r} to the caller as their "
                f"choice, and nothing declares what would record that choice "
                f"on an answer — an attribution no pass can check is one a "
                f"reader has to take on trust"
            )
            return
        if not any(backs(channel) for channel in channels):
            _reject(
                f"assumption_ledger hands {line!r} to the caller as their "
                f"choice, but nothing in this answer records that choice "
                f"being made — a line offered as theirs to change is a lever "
                f"the reader cannot find"
            )
            return


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
        if e.get("id") and e.get("provenance") in (
            "inherent", "caller_asserted", "caller_chose")
    } - {str(a) for a in declared}
    if invented:
        _reject(
            "assumption_ledger attributes to the estimator assumption(s) it "
            f"never declared: {sorted(invented)!r}"
        )


def _verdicts_this_answer_carries(result: dict) -> dict[str, tuple[str, str]]:
    """Declaration id to the ``(check, verdict)`` this envelope's own numbers
    imply, re-read here rather than taken off the ledger."""
    found: dict[str, tuple[str, str]] = {}
    for name, ids, settles, read in _CHECKS:
        refuted = read(result)
        if refuted is None:
            continue
        verdict = ("refuted" if refuted
                   else ("held" if settles else "not_refuted"))
        for declaration in ids:
            found[declaration] = (name, verdict)
    return found


def _check_verdicts(result: dict, entries: list) -> None:
    """Every verdict on the ledger is the one the numbers give, and every
    verdict the numbers give is on the ledger.

    Both directions, because the field fails in both and they are different
    failures. Overstating is a producer writing a sentence nothing backs —
    the reason the outcome is re-read here instead of believed. Understating
    is the one this module exists for: a run that tested a premise, watched
    this data refuse it, and handed the reader a line reading exactly like
    one nobody has ever looked at.

    A verdict also has to sit on a line the check adjudicates and on one the
    ledger already calls testable. Neither is pedantry about fields: a
    verdict stamped on a neighbouring assumption tells the reader this data
    settled something it never addressed, and a line saying at once that
    nobody could check this and that somebody did is two answers to one
    question.
    """
    owed = _verdicts_this_answer_carries(result)
    for i, e in enumerate(entries):
        line = str(e.get("id") or "")
        stated = e.get("checked")
        if stated is None:
            if line in owed:
                check, verdict = owed[line]
                _reject(
                    f"assumptions[{i}] is {line!r} and this answer carries "
                    f"the outcome of {check!r} against it ({verdict!r}), and "
                    f"the line says nothing about it; a premise this run "
                    f"tested reads on the page as one nobody has looked at"
                )
            continue
        if not isinstance(stated, Mapping):
            _reject(
                f"assumptions[{i}].checked must be an object saying which "
                f"check was run and what it concluded; got "
                f"{type(stated).__name__}"
            )
        if line not in owed:
            names = repr(line) if line else "an assumption naming no id"
            _reject(
                f"assumptions[{i}] reports a check concluding "
                f"{str(stated.get('verdict'))!r} about {names}, and this "
                f"answer holds no record of any check against it — a verdict "
                f"the reader cannot go and look at is not a disclosure"
            )
        check, verdict = owed[line]
        if str(stated.get("by")) != check:
            _reject(
                f"assumptions[{i}] attributes its verdict to "
                f"{str(stated.get('by'))!r} while this answer's own numbers "
                f"make {check!r} the check that governs {line!r}"
            )
        if str(stated.get("verdict")) != verdict:
            _reject(
                f"assumptions[{i}] says {check!r} concluded "
                f"{str(stated.get('verdict'))!r} about {line!r}; re-read from "
                f"the estimate's own record, it concluded {verdict!r}"
            )
        if not e.get("testable"):
            _reject(
                f"assumptions[{i}] carries the verdict of {check!r} and is "
                f"marked untestable; one line cannot both say nobody could "
                f"check this and report what happened when somebody did"
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
