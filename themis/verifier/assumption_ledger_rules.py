"""Independent audit of ``extensions.assumption_ledger``.

The ledger is the surface both ``output.analysis_report`` and the
``response_rendering.md`` bridge lead with — everything the answer takes on
faith, ranked by how it dies if it is false. Its failure mode is therefore
one-sided: an assumption that never reaches it is indistinguishable, to every
consumer, from an assumption nobody makes. This module re-derives what the
ledger owes from the channels that feed it and rejects UNDER-disclosure.

What it audits:

- **Completeness of the declaration channels.** An estimator declares what
  its answer rests on where it reports itself — ``numeric_estimate`` for a
  point, its own block for a region; an outcome measurement-error
  assessment and an identification route each declare their own premises
  beside it. The ledger must carry each of those declarations keyed by ``id``
  — either flat, or as the estimator's own structured ``identification`` entry
  naming the same id, which says the same thing in better words. Carrying
  neither is the defect.
- **Completeness of the other three channels, and what two of them say.**
  One entry per audited mechanism. A load-bearing proposal edge in the gap
  report and a prior the language model supplied are owed more than a
  count: each channel writes its line from one record on this answer and
  names no assumption, so the lines with no id are held, together, to be
  exactly the lines those records owe — one each, and word for word what
  the reader is told.
- **No fabrication.** Any entry attributed to the estimator whose ``id`` the
  estimate never declared is invented. This keys on the attribution and not on
  which of the two channels carried it, so it now covers the structured
  entries too — under the old key a fabricated structured entry was outside
  the question being asked. An entry with no ``id`` names no declaration and
  is not subject to it; it is held to the record it was written from
  instead, above.
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

- **What each named assumption IS.** A line says which layer it holds up,
  whether the data can answer it, and — for every layer but the functional
  form — who can overrule it. All three are facts about the assumption rather
  than about this run: the same id means the same three things in every
  answer, and the glossary says so of the third in as many words. They are
  read from the declaration and the line is held to it.

  This was once out of scope on the ground that the declaration lived in the
  output layer, so reading it would be reading a producer. It does not: what an
  assumption ID means is the same kind of fact as what a status word claims,
  and it now sits beside the vocabularies it classifies into, in
  ``themis.assumption_glossary``. Which is the difference between reading a
  declaration and transcribing a roster — and while it could be done neither
  way, ``testable`` was a field every reader acts on that no rule had ever
  asked about.

**Independence pin:** this module MUST NOT import from
``themis.output`` — the assembler under audit is
``themis.output.result_orchestrator``, and an audit that read it would be
agreeing with it by construction. Reading ``themis.assumption_glossary`` is
not that: it is the contract's statement of what a name means, the same
arrangement ``status_rules`` has with ``STATUS_CLAIMS``.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from typing import NoReturn

from .. import language
from ..assumption_glossary import answerable, declares
from ..gaps import DESCRIBED, Sentence
from .errors import VerificationError
from .mechanism_rules import (
    _HONOURS_A_WORD_BY_BEING_IT,
    shape_the_method_cannot_fit,
    word_that_could_not_have_asked_for,
)

#: What ``estimation_context.model_preference`` holds when the caller named
#: no shape. Spelled once here rather than read from
#: :mod:`themis.estimation.form`, which this side may not import — the value
#: is the envelope's, and a test drives a run that leaves the option alone to
#: pin the two.
_DECLINED_TO_CHOOSE = "auto"

#: The origin a shape carries when the caller's own lever settled it.
_THE_CALLER_S_OWN = "caller_asserted"


def _a_caller_settled_a_shape_here(mechanism: dict) -> bool:
    """Whether this block says a caller's lever settled a shape in it.

    THE PREMISE, stated because the block cannot state it: a
    ``caller_asserted`` here is read as the caller's ``model=``, and the
    block does not say which lever it was. It cannot — ``build_mechanism_audit``
    holds the form's origin and the other levers' origins as two arguments
    and merges them into one list. What makes the reading sound is not this
    module: no shape lever other than ``model=`` is a parameter of the public
    entry, so the others can only answer ``default`` on any envelope a
    verifier will ever see. That is asserted where it can be measured, in
    ``tests/test_the_word_on_the_context_and_the_form_on_the_block_are_one_fact.py``,
    and wiring one of those levers through fails there — which is the moment
    the block would have to say which lever it means, and this function would
    have to ask.
    """
    return any(
        isinstance(a, dict) and a.get("settled_by") == _THE_CALLER_S_OWN
        for a in (mechanism.get("assumptions") or ())
    )

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


#: The set an ESTIMATOR-DECLARED line states its sentence from. Not a
#: roster of every vocabulary a ledger may quote: that roster is not
#: knowable here. The tables live in ``themis.output``, which no verifier
#: module imports, so the only way to write one would be to infer it from
#: the answers this repository happens to produce — and an inference from
#: a sample is what this constant used to be. It listed the two
#: vocabularies the forty-four answer shapes contain and refused an honest
#: answer whose ledger quoted a third (``theta_prior_claim``), reached
#: only through an LLM-prior patch.
#:
#: What is knowable is narrower and has an anchor. An entry the estimator
#: declared is one this module already re-derives, and every one of the
#: 248 in the corpus says its sentence from the assumption glossary. The
#: other vocabularies belong to the two channels that declare no id —
#: proposal edges and theta priors — whose entries this rule cannot hold,
#: having no id to hold them to. The record each was written from can, and
#: :func:`_check_the_lines_that_name_no_assumption` asks it for the whole
#: claim, vocabulary included.
_ESTIMATOR_CLAIM_VOCABULARY = "assumption_claim"


def _check_the_claim_is_the_line_the_id_names(entries: list) -> None:
    """A ledger entry writes the same fact twice; hold the reader's copy.

    ``id`` is the machine's name for the assumption — the token with this
    occasion's values run together, ``propensity_clipped_to_floor_0.01_on_618``
    — and it is anchored: :func:`_check_estimator_channel` rejects a ledger
    that drops an id the estimator declared. ``claim`` is the same fact
    structured for a reader, ``(token, vocabulary, said)``, and it is what
    the sentence is built from. Nothing read it: on all forty-four answer
    shapes the token, the vocabulary and every value under ``said`` could
    each be rewritten and the door said yes, while ``id``, ``layer``,
    ``severity`` and ``provenance`` were all held.

    So this asks the two copies to agree, which needs no new authority and
    no table of legal tokens. It READS the id rather than rebuilding it:
    the format belongs to whoever writes it, and a verifier that
    reassembled ``token + values`` would turn a change of format into an
    apparent disagreement about the assumption. Measured across the
    corpus: 248 of 248 tokens are a prefix of their id (214 equal to it,
    34 a proper prefix) and 37 of 37 ``said`` values appear in what the id
    has left over, with no exceptions.

    Three entries carry no ``id`` at all — the load-bearing LLM-proposal
    edges, which state their sentence from the gap vocabulary. Nothing on
    the envelope is a second record of those, so they are not held here,
    and a test pins that it is exactly those three.
    """
    for i, e in enumerate(entries):
        ident = e.get("id")
        if not isinstance(ident, str) or not ident:
            # No second record to hold this against. Declared, not skipped:
            # the channels that reach here are named in the constant above
            # and pinned by test.
            continue
        for j, one in enumerate(e.get("claim") or []):
            vocabulary = one.get("vocabulary")
            if vocabulary != _ESTIMATOR_CLAIM_VOCABULARY:
                _reject(
                    f"assumptions[{i}] was declared by an estimator and "
                    f"tells a reader to look {one.get('token')!r} up in "
                    f"{vocabulary!r}; a declared assumption states its "
                    f"sentence from {_ESTIMATOR_CLAIM_VOCABULARY!r}, and a "
                    f"lookup in the wrong set falls through to printing the "
                    f"token"
                )
            token = str(one.get("token") or "")
            if not ident.startswith(token):
                _reject(
                    f"assumptions[{i}] is recorded as {ident!r} and tells a "
                    f"reader it is {token!r}; the sentence a reader gets and "
                    f"the assumption this answer declared are two copies of "
                    f"one fact, and these two are not the same fact"
                )
            left_over = ident[len(token):]
            for key, value in (one.get("said") or {}).items():
                # Emptiness is asked FIRST and on its own. "Appears in the
                # id" is a containment test, and every containment test
                # passes for the empty value — so a line that told a
                # reader nothing where a number goes would satisfy the
                # check below by saying nothing at all.
                if not str(value).strip():
                    _reject(
                        f"assumptions[{i}] names its {key} and puts nothing "
                        f"there; the sentence a reader is handed has a hole "
                        f"where the value goes, which is not the same as an "
                        f"assumption that carries no {key}"
                    )
                if str(value) not in left_over:
                    _reject(
                        f"assumptions[{i}] tells a reader its {key} is "
                        f"{value!r}, and the assumption it was recorded as "
                        f"({ident!r}) says otherwise"
                    )


#: The one layer whose provenance an id does not settle. Who fixed a shape is
#: a fact about the run — the same id is one family's definition and the next
#: family's resolved default — so the glossary refuses to answer for it, and
#: the line is held instead to the mechanism block that records the run's own
#: resolution, by :func:`_check_the_line_says_what_the_block_says`.
_SETTLED_BY_THE_RUN = "functional_form"


def _check_each_line_is_the_assumption_it_names(entries: list) -> None:
    """The facts an id already settles, held to what it settles them as.

    ``testable`` tells a reader whether there is anything they could go and
    do about this line, and ``layer`` says which part of the answer stops
    being true without it. Neither is a fact about this run: the same id
    means the same two things in every answer, which is why one table
    declares them for all of them.

    Nothing had ever asked. Measured over the corpus before this existed:
    507 entries name an id and every one of them agrees with the
    declaration, while every one of them could have been rewritten and the
    door said yes.

    ``provenance`` is the third, and the same table answers it — "who can
    overrule an assumption is a property of the assumption", in its own
    words — for every layer but the functional form. It was left to the
    checks that ask whether the answer records a caller's input, and those
    ask only of a line that CLAIMS one. A line relabelled ``inherent``
    claims nothing, so nothing asked: a premise the caller supplied could be
    told to the reader as one nobody can withdraw, and a lever taken away
    reads exactly like a lever that was never there. Measured before this
    read the third column: 430 named lines outside the functional form, and
    every one agrees with the declaration.

    Those checks stay, because they answer a different question — whether
    this answer carries the record a caller's input would leave — which no
    table keyed on a name can answer.

    An entry naming NO id is outside this, and the sentence is the whole
    reason rather than an apology: this table is keyed on the assumption's
    name, so an entry that names none is not one it can be right or wrong
    about. Those come from the two proposal channels — an unverified edge
    and a supplied prior — which state their line from the gap vocabulary
    instead. A test pins that it is exactly those.

    ``testable`` is the one field here the schema leaves optional, so a named
    line can be silent about it rather than wrong about it. This does not
    distinguish the two, deliberately: the declaration answers for every
    name, so a line that names an assumption and then says nothing about
    whether anyone could check it leaves the reader to guess at something
    the system knows.
    """
    for i, entry in enumerate(entries):
        assumption_id = entry.get("id")
        if not isinstance(assumption_id, str) or not assumption_id:
            continue
        layer, testable = declares(assumption_id)
        shown = entry.get("layer")
        if shown != str(layer):
            _reject(
                f"assumptions[{i}] is {assumption_id!r} and says it is a "
                f"{shown!r} assumption; that id holds up {str(layer)!r}, and "
                f"which part of an answer an assumption holds up is not the "
                f"run's to reassign — a line moved to a milder layer reads as "
                f"a milder assumption and is ranked as one"
            )
        if entry.get("testable") != testable:
            can = "the data can answer" if testable else "no data answers"
            _reject(
                f"assumptions[{i}] is {assumption_id!r} and tells a reader "
                f"its testability is {entry.get('testable')!r}; {can} that "
                f"assumption, whichever run it turns up in. A reader decides "
                f"from this field whether there is anything they could go and "
                f"do, so the wrong word here sends them after a check that "
                f"does not exist, or leaves one they could make unmade"
            )
        if str(layer) == _SETTLED_BY_THE_RUN:
            continue
        owed = str(answerable(assumption_id))
        if entry.get("provenance") != owed:
            _reject(
                f"assumptions[{i}] is {assumption_id!r} and says it came from "
                f"{entry.get('provenance')!r}; who can overrule that "
                f"assumption is {owed!r}, whichever run it turns up in. The "
                f"field tells a reader what they may do about the line — "
                f"withdraw it, choose again, or nothing — so the wrong word "
                f"here takes away a lever they have or hands them one they "
                f"do not"
            )


def verify_assumption_ledger(result: dict) -> None:
    """Audit one result's assumption ledger. No-op when the result has none
    AND owes none; raises :class:`VerificationError` otherwise."""
    extensions = result.get("extensions") or {}
    ledger = extensions.get("assumption_ledger")
    declared = _declaration_channels(result)

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
    _check_the_claim_is_the_line_the_id_names(entries)
    _check_each_line_is_the_assumption_it_names(entries)
    _check_verdicts(result, entries)
    _check_caller_assertions(result, entries)
    _check_caller_choices(result, entries)
    _check_estimator_defaults(result, entries)
    _check_the_lines_that_name_no_assumption(entries, owed_edges + owed_priors)
    _check_channel(entries, owed_forms, "functional_form", "audited mechanism")
    _check_the_line_says_what_the_block_says(entries, extensions)
    _check_one_run_settles_one_shape_per_lever(extensions)
    _check_every_shape_the_ledger_names_has_a_mechanism(entries, extensions)
    _check_the_block_describes_the_fit_that_ran(result, extensions)


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


def _declaration_channels(result: dict) -> tuple[str, ...]:
    """Every assumption someone declared, by id, whichever list holds it.

    Three do. The estimator's own is on whatever the run reported itself
    in, and every estimator populates it. It was read at
    ``numeric_estimate`` alone, while :func:`_where_the_run_reports_itself`
    already named the region block as the other such place — one fact in
    one module, read whole by the check on a mechanism and by half here.
    The second belongs to another author
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
    extensions = result.get("extensions") or {}
    ids = [str(a)
           for place in _where_the_run_reports_itself(result, extensions)
           for a in place.get("assumptions") or ()]
    block = result.get("outcome_error")
    if isinstance(block, dict):
        ids += [a for a in (block.get("assumptions") or ()) if isinstance(a, str)]
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


#: What a line naming no assumption is held to its record on, in the order
#: an owed line is written below. The severity is not among them: it is the
#: grade of the layer, held to that for every line above, and a line that
#: disagreed on it is refused there first.
_WRITTEN_FROM_THE_RECORD = ("claim", "layer", "provenance", "testable")


def _unnamed_line(claim: list, layer: str, provenance: str) -> tuple:
    """What a channel that names no assumption owes, as the four values a
    line is compared on — not as a ledger entry, which is assembled where
    the ledger is and nowhere else. Testable whichever channel: an edge
    and a number are both things data can speak to, which is what
    separates them from an identification premise."""
    return [dict(one) for one in claim], layer, provenance, True


def _owed_proposal_edges(result: dict) -> tuple[tuple, ...]:
    """The line each load-bearing proposal edge owes, as its gap owes it.

    One per gap: the gap report already did the load-bearing analysis, and
    a proposed-but-unused edge is not owed. Everything the line tells a
    reader is on the gap too — the statements it is made of, verbatim, and
    in the first of them who proposed the edge.

    This read ``description`` until it read the statements, and no gap has
    carried that field since descriptions became statements. Nothing
    noticed, because only the length of what came back was ever used.
    """
    report = result.get("data_gap_report") or {}
    owed = []
    for gap in report.get("gaps") or ():
        if not isinstance(gap, Mapping) or gap.get(
                "kind") != "unverified_proposal_edge_on_query_path":
            continue
        describes = [e for e in gap.get("describes") or ()
                     if isinstance(e, Mapping)]
        learned = bool(describes) and describes[0].get(
            "sentence") == Sentence.THE_EDGE_WAS_LEARNED_BY_DISCOVERY
        owed.append(_unnamed_line(
            [language.restate(e, DESCRIBED, "sentence") for e in describes],
            "structural_edge", "discovery" if learned else "llm_proposal"))
    return tuple(owed)


#: The sentence a supplied prior's line is, spelled here rather than
#: imported: it is declared as ``Prior`` in the output layer, which this
#: module may not read. Both are members of sets the statement carrier
#: enumerates, and a spelling that drifted from the declaration would
#: refuse every honest answer carrying a prior rather than pass a
#: dishonest one.
_PRIOR_VOCABULARY = "theta_prior_claim"
_PRIOR_SENTENCE = "a_commonsense_prior"


def _owed_theta_priors(extensions: dict) -> tuple[tuple, ...]:
    """The line each prior the language model supplied owes: its key and
    its value, in the one sentence there is for them."""
    review = extensions.get("llm_proposed_review") or {}
    return tuple(
        _unnamed_line(
            [language.spelt(_PRIOR_VOCABULARY, _PRIOR_SENTENCE,
                            key=p.get("key"), value=p.get("value"))],
            "parameter", "llm_prior")
        for p in review.get("probabilities") or ()
        if isinstance(p, Mapping)
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

    Both questions used to wait for a declaration to be found, and what
    went unfound was a place rather than a declaration: they were read at
    the estimate alone, and an estimator answering with a region declares
    in its own block. On the two answers where that is the only
    estimator, 8 of 10 deletions of a named line passed every door, and a
    premise copied in from AIPW passed as well. With both places read, no
    ledger in the corpus carries a line attributed to an estimator under
    an id nobody declared, 14 of them declaring nothing at all — so
    finding no declaration is a claim this holds the ledger to, not a
    reason to stop asking.
    """
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


def _check_every_shape_the_ledger_names_has_a_mechanism(
    entries: list, extensions: dict,
) -> None:
    """The other direction, and why nothing could see it was missing.

    Both existing checks walk the BLOCK: one finds the ledger line for
    each id the block names, the other counts the lines the block says are
    owed. That makes the block the denominator, which is the one position
    in which a thing is never itself checked — emptying ``mechanisms`` did
    not merely skip its own audit, it also reduced what the ledger was
    said to owe. A measuring stick can be shortened.

    What anchors the other direction is that a shape assumption reaches
    the ledger because the ESTIMATE declared it, which the estimator
    channel above already holds. So every functional-form line is a shape
    some fit was settled under, and the reader is owed the block saying
    which fit. Asked over the lines rather than against a list of ids this
    module would have to keep: the ledger carries the layer, and the layer
    is already held to the severity beside it, so relabelling a line out
    of reach of this check is refused one rung up.
    """
    named = {
        str(a.get("id"))
        for m in ((extensions.get("mechanism_audit") or {})
                  .get("mechanisms") or ())
        for a in m.get("assumptions") or ()
        if isinstance(a, dict)
    }
    unclaimed = sorted(
        str(e.get("id")) for e in entries
        if e.get("layer") == "functional_form" and str(e.get("id")) not in named
    )
    if unclaimed:
        _reject(
            f"assumption_ledger files {unclaimed} under functional_form and no "
            "mechanism_audit entry says which fit was settled that way; the "
            "shape a number was computed under reaches a reader in that block "
            "and nowhere else"
        )


def _the_fit_this_run_reported(result: dict, extensions: dict) -> dict | None:
    """Where this run said what it fitted.

    One place per answer, and which place depends on what the answer IS: a
    point estimate reports its method and its declaration list on
    ``numeric_estimate``, and an answer that is a region rather than a
    point reports the same two on the region block. Both are the run's own
    account of itself, which is what makes either of them the thing a
    mechanism block is a view OF.

    Returning ``None`` where neither is present is deliberate and the
    caller refuses on it. A future answer shape that carries a mechanism
    block and reports its fit somewhere third belongs in
    :func:`_where_the_run_reports_itself`,
    and the way to be told is a suite that stops rather than a check that
    quietly skips.
    """
    return next(_where_the_run_reports_itself(result, extensions), None)


def _where_the_run_reports_itself(result: dict,
                                  extensions: dict) -> Iterator[dict]:
    """The blocks this run reported itself in: the estimate, then a region.

    Read first-found by :func:`_the_fit_this_run_reported`, which wants the
    one fit a mechanism block is a view of, and whole by
    :func:`_declaration_channels`, which wants every declaration the run
    made. One statement of where a run speaks for itself, so the two
    readers cannot come to disagree about the places — which is how the
    second came to know only the first of them.
    """
    for place in (result.get("numeric_estimate"),
                  extensions.get("anderson_rubin_region")):
        if isinstance(place, dict):
            yield place


def _check_the_block_describes_the_fit_that_ran(
    result: dict, extensions: dict,
) -> None:
    """The block is a view over one fit, so it names that fit's method and
    assumptions that fit declared.

    Nothing here re-runs the fit; that needs the data. What it does is deny
    the block a life of its own — three of its four fields have a second
    copy on the envelope, written by the same run for a different reader,
    and a view that disagrees with what it is a view OF is the one thing
    that cannot be true.

    ``method`` and ``assumptions`` are reported by every fit, so both are
    asked of every block. The other two fields are not checked, and
    what stops that being a shrug is that each has a reason a reader can
    weigh.

    A ``caller_asserted`` among the origins is asked against
    ``estimation_context.model_preference``, and until it was, that context
    field was witnessed by nothing on any answer this build gives: the word
    could be rewritten from ``auto`` to a shape the estimator chose for
    itself and every public door said yes. The two are one decision recorded
    twice — the context at the entry, before a route was chosen; the origin
    on the far side of the cascade, off the estimate that resolved a shape —
    so a route that drops the knob shows up here as a disagreement rather
    than as an envelope telling a reader they chose a shape they did not
    get. Held in BOTH directions, because a block claiming a caller the
    context has none of, and a context naming a word no block attributes to
    anybody, are the same lie told from the two ends. And in a third: which
    shape the word names, since the two ends can agree that the caller chose
    and still disagree about what.

    ``form`` reaches the envelope through this block alone — the estimate
    records which method ran, never the shape word — so it stands as the
    producer's statement, in the company of the other producer statements
    this repository declines to recompute rather than agree with by
    construction. A check invented for it (that the method spells the
    form, say) holds for the outcome models and fails on the honest
    ``logistic_propensity`` beside ``aipw``.

    ``target`` is asked, and not from here. This function is reached
    through ``verify_assumption_ledger(result)``, which has no program
    beside it, and a target names the thing the QUESTION is about — so
    the authority is one this door cannot see. What was tried instead was
    the nearest copy that IS in reach, ``numeric_estimate.outcome``; it
    refused seventeen honest results, and the note left here concluded
    that the field meant two things and had no witness. It has one:
    :func:`themis.verifier.verify_mechanism_target` asks the question
    rather than the answer's copy of it, and twenty-six of thirty-one
    targets are the question's outcome exactly. The five that are not
    are accounted for there.
    """
    mechanisms = ((extensions.get("mechanism_audit") or {})
                  .get("mechanisms") or ())
    if not mechanisms:
        return
    estimate = _the_fit_this_run_reported(result, extensions)
    if estimate is None:
        _reject(
            "mechanism_audit discloses the shape a number was fitted through "
            "and this result reports no fit — neither a numeric_estimate nor "
            "a region; a shape with no fit beside it describes a run this "
            "envelope has no record of"
        )
    declared = {str(a) for a in estimate.get("assumptions") or ()}
    asked_for = str((result.get("estimation_context") or {})
                    .get("model_preference") or _DECLINED_TO_CHOOSE)
    for m in mechanisms:
        if m.get("method") != estimate.get("method"):
            _reject(
                f"mechanism_audit says the fit was {m.get('method')!r} and "
                f"the estimate reports {estimate.get('method')!r}; a reader "
                "weighing the shape is weighing the wrong estimator"
            )
        # And the shape itself, against what that method can fit. The two
        # lines around this one held the other fields of the block from the
        # day it existed; the one word that says what the number was fitted
        # THROUGH took any string, so every form on every answer shape could
        # be rewritten and this door said yes. It is asked after the method
        # is held, so the set it is looked up in is not one an answer can
        # choose for itself.
        complaint = shape_the_method_cannot_fit(m.get("method"), m.get("form"))
        if complaint is not None:
            _reject(complaint)
        # WHICH shape the word names. The other direction of this pair — a
        # block attributing a shape to a caller who named none — is held
        # already, and not from here: :func:`_check_caller_assertions` reads
        # the same context field to decide whether any ``caller_asserted``
        # line may be handed to the reader at all. Adding a second gate for
        # it would be a rule whose counterexample another rule refuses
        # first, which reads as coverage and is not.
        if _a_caller_settled_a_shape_here(m) and (
            asked_for != _DECLINED_TO_CHOOSE
        ):
            complaint = word_that_could_not_have_asked_for(
                asked_for, m.get("form"))
            if complaint is not None:
                _reject(complaint)
        for named in m.get("assumptions") or ():
            if not isinstance(named, dict):
                continue
            if str(named.get("id")) not in declared:
                _reject(
                    f"mechanism_audit names shape assumption "
                    f"{str(named.get('id'))!r} and the estimate declares "
                    f"{sorted(declared)}; a mechanism points at assumptions "
                    "already declared and does not introduce one"
                )
    # The other end of the same pair. Asked once, of the blocks together,
    # because an answer may disclose several fits and the caller's word
    # settled the shape of one of them — a measurement route's own form is
    # not a shape any ``model=`` names, and requiring the claim of every
    # block would refuse an honest answer for carrying an extra one. What
    # cannot be honest is a word on the context that NO disclosed fit
    # attributes to the caller: the field would then be the only record of a
    # choice, which is what it was before this pair existed.
    #
    # Except where the row honoured the word by BEING it, which is a real
    # way to honour a request and not a loophole — see
    # :data:`~themis.verifier.mechanism_rules._HONOURS_A_WORD_BY_BEING_IT`.
    # An answer with no disclosed fit at all never reaches here, and that is
    # the same exemption one step earlier: three of IV's five words select
    # an estimator with no functional form to disclose, so there is no block
    # for the word to be attributed to.
    if (
        asked_for != _DECLINED_TO_CHOOSE
        and str(estimate.get("method")) not in _HONOURS_A_WORD_BY_BEING_IT
        and not any(_a_caller_settled_a_shape_here(m) for m in mechanisms)
    ):
        _reject(
            f"estimation_context records the caller asking for "
            f"{asked_for!r} and no disclosed mechanism says a caller's "
            f"model= settled its shape; the word would be the answer's only "
            f"record that anybody chose anything, and a record nothing "
            f"corroborates cannot tell a run that honoured the word from one "
            f"that dropped it"
        )


def _check_the_lines_that_name_no_assumption(entries: list,
                                             owed: tuple) -> None:
    """The lines with no id are the lines this answer's records owe, one each.

    Two channels write a line without naming an assumption: a load-bearing
    proposal edge, from its gap, and a prior the language model supplied,
    from the review. Having no id, such a line is outside everything keyed
    on one — what the declaration says the assumption is, the claim held to
    its id, the fabrication check — and it used to be counted instead: at
    least as many lines of its layer as records. A record reduced to its
    length checks nothing else. Measured, every field the reader is told
    could be rewritten and pass: who proposed an edge, in either direction;
    a supplied prior told as nobody's to overrule; which edge; whether the
    data can answer it. So could a line written twice, and a real line
    copied onto an answer that owed none, where the count had returned
    before looking.

    The line is a copy of its record and is held as one. Measured before
    this was enforced, over every answer shape: 22 such lines on 19 shapes,
    every one exactly its record's line and none left over. As a multiset
    rather than pairwise, because nothing on a line says which record it
    copies — and two records owing the same line owe it twice.
    """
    def as_written(values) -> str:
        return json.dumps(list(values), sort_keys=True, ensure_ascii=False,
                          default=repr)

    carried = Counter(as_written(e.get(k) for k in _WRITTEN_FROM_THE_RECORD)
                      for e in entries if not e.get("id"))
    owes = Counter(as_written(o) for o in owed)
    extra, missing = carried - owes, owes - carried
    if not extra and not missing:
        return
    _reject(
        f"assumption_ledger's lines that name no assumption are not the "
        f"lines this answer's records owe: {sum(extra.values())} carried "
        f"that no gap or supplied prior writes"
        + (f" (the first: {next(iter(extra))})" if extra else "")
        + f", {sum(missing.values())} owed and not carried"
        + (f" (the first: {next(iter(missing))})" if missing else "")
        + ". A line with no name is only as true as its copy of the record "
        "it stands for — which edge, whose proposal, whether the data can "
        "answer it — and a line nothing owes is a proposal nobody made"
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
