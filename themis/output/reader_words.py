"""Every closed vocabulary a reader is handed words for, in one place.

The kernel emits tokens; a reader gets a word. Which accessor turns one into
the other was written down in the suite — a row per vocabulary in
``tests/test_vocabulary_reach.py``, and a second table in
``tests/test_web_vocabularies.py`` saying where the kernel declares each
member. That was the right place while the only consumer was a gate. It
stopped being the right place the moment something in the package needed to
ANSWER the question rather than check it: the browser cannot import Python,
so the twenty vocabularies it restates are generated from here, and a
generator that read its inputs out of the test suite would be a build step
that a `pytest` refactor could break.

So this module holds the answer and the suite holds its claims about it. A
row here says three things: which accessor hands a reader the word, where
the members are declared, and — for the twenty the browser restates — the
name its table takes in the generated TypeScript.

**Why the members are a path and not a list.** A vocabulary's members are
declared once, in a schema ``enum`` or a Python ``Enum``, and a row that
copied them would be a second declaration free to fall behind. What a row
carries is how to reach the first one. Where two containers carry the same
vocabulary and hold different subsets of it, the row says so by taking the
union: anchoring on either site alone passes while half the vocabulary goes
unstated, which is how a table came to be missing four licences a
counterfactual cell can carry.

**What the browser gets and why it is generated.** Twenty of these tables
were restated by hand in ``verdict.ts`` — 254 member-language pairs — and a
freshness gate held them equal to the kernel's. A gate makes the copy safe;
generating makes it zero, and the difference shows up on the day a third
language arrives: hand-written, it is 254 more strings on the second
surface. The three tables that render a vocabulary in the browser's OWN
terms are not here and must not be: a tier's plain-language gloss beside its
label, a status's blurb, a refusal's head/lead/tail are the browser's
sentences, not copies of the kernel's.
"""
from __future__ import annotations

import functools
import importlib
import json
import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .. import language

SCHEMAS = pathlib.Path(__file__).resolve().parent.parent / "schemas"

_QR = "query_result.schema.json"


@functools.cache
def _document(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _enum_at(*path: str) -> frozenset[str]:
    """The members of one schema ``enum``, by the path that reaches it."""
    node: object = _document(_QR)
    for step in path:
        node = node[step]              # type: ignore[index]
    return frozenset(node["enum"])     # type: ignore[index]


def load() -> None:
    """Make every vocabulary this build declares known to a reader.

    :data:`themis.language.VOCABULARIES` is filled when a vocabulary's class
    body runs, so which sets a reader can state depended on which producers
    some caller happened to import — 42 of the 59 below were unknown after a
    bare ``import themis``. That is invisible while the kernel runs first,
    because running a query imports the producer on the way; it shows on the
    path where a stored envelope is rendered on its own, and there the
    reader falls back to handing over the token.

    Which sets can reach a reader is not a per-call question, and the list
    was already here: this is the module that answers it. Resolving a row's
    ``gloss`` imports whatever declares it, which is all this has to do.
    """
    for row in GLOSSED.values():
        _resolve(row.gloss)


def _stated(dotted: str) -> frozenset[str]:
    """The members of one Python vocabulary, by its dotted name."""
    return frozenset(str(member) for member in _resolve(dotted))


def _resolve(dotted: str):
    """A dotted name, imported as deep as it goes.

    Attributes rather than a second import for each level, because the
    accessors below are module-level names and some of them are methods on
    a vocabulary — ``Recovery.said`` is reached by attribute twice.
    """
    module, _, rest = dotted.partition(":")
    if not rest:
        parts = dotted.split(".")
        for cut in range(len(parts), 0, -1):
            try:
                module_obj = importlib.import_module(".".join(parts[:cut]))
            except ImportError:
                continue
            found: object = module_obj
            for attr in parts[cut:]:
                found = getattr(found, attr)
            return found
        raise ImportError(dotted)
    found = importlib.import_module(module)
    for attr in rest.split("."):
        found = getattr(found, attr)
    return found


@dataclass(frozen=True)
class Glossed:
    """One vocabulary, and how a reader is handed its words."""

    gloss: str
    """Dotted name of the mapping or accessor that gives the word.

    Either the words themselves — member to the text in each language — or a
    callable over one. Both answer the same shape, so a caller asks any of
    them the same way, once per language.
    """

    members: Callable[[], frozenset[str]] = field(
        default_factory=lambda: (lambda: frozenset()))
    """How to reach the declaration of the members, not a copy of them.

    Empty for a vocabulary this module does not have to enumerate — the
    reach registry in the suite already holds its sites, and only the
    generated tables need the set here.
    """

    browser_table: str = ""
    """The name this vocabulary's table takes in the generated TypeScript,
    or empty where the browser does not restate it."""


#: Schema paths that several rows below share.
_EXT = ("properties", "extensions", "properties")
_NE = ("properties", "numeric_estimate", "properties")
_DEFS = ("$defs",)

#: One row per vocabulary the kernel hands a reader words for.
#:
#: Where a row anchors its members is a decision, and each of the unobvious
#: ones says why beside itself. The rule the decisions come from: anchor on
#: what the READER's surface is handed. A browser reads a value off the
#: envelope, so what it has to state is what the envelope may carry — a
#: Python enum with a member no schema admits would pin the table to a set
#: the browser never sees, and the two could then agree while the schema
#: admitted a third thing. Where no schema states the vocabulary at all, the
#: module is the only declaration and the row says so.
GLOSSED: dict[str, Glossed] = {
    # --- the twenty the browser restates -------------------------------------
    "assumption_severity": Glossed(
        gloss="themis.ledger.severity_word",
        browser_table="ASSUMPTION_SEVERITY_WORDS",
        members=lambda: _enum_at(*_EXT, "assumption_ledger", "properties",
                                 "assumptions", "items", "properties",
                                 "severity"),
    ),
    "assumption_layer": Glossed(
        gloss="themis.ledger.layer_word",
        browser_table="LEDGER_LAYER_WORDS",
        members=lambda: _enum_at(*_EXT, "assumption_ledger", "properties",
                                 "assumptions", "items", "properties",
                                 "layer"),
    ),
    "assumption_provenance": Glossed(
        gloss="themis.ledger.provenance_word",
        browser_table="LEDGER_PROVENANCE_WORDS",
        members=lambda: _enum_at(*_EXT, "assumption_ledger", "properties",
                                 "assumptions", "items", "properties",
                                 "provenance"),
    ),
    "gap_severity": Glossed(
        gloss="themis.output.analysis_report._GAP_SEVERITY_WORDS",
        browser_table="SEVERITY_LABEL",
        members=lambda: _enum_at(*_DEFS, "dataGap", "properties", "severity"),
    ),
    "identification_pattern": Glossed(
        gloss="themis.output.analysis_report._PATTERN_WORDS",
        browser_table="PATTERN_WORDS",
        members=lambda: _enum_at(*_EXT, "identification", "properties",
                                 "pattern"),
    ),
    # Which family of functions a continuous-proxy bridge was assumed to lie
    # in. The word goes INSIDE the sentence that states the span, so a member
    # with no translation is not an identifier beside a value but a gap in the
    # middle of a clause — the sharper half of the reason every table here is
    # generated rather than written twice.
    "basis_family": Glossed(
        gloss="themis.output.analysis_report._BASIS_WORDS",
        browser_table="BASIS_WORDS",
        # One level down from where this used to point. A family belongs to
        # a FACTOR of a term, because a design over several variables has
        # one family per variable and a family named beside the design
        # belongs to none of them.
        members=lambda: _enum_at(*_DEFS, "sieveDesign", "items", "items",
                                 "properties", "basis"),
    ),
    # Anchored on the module, not on either schema enum. Two containers carry
    # this vocabulary — the causation block and the counterfactual cell — and
    # they hold DIFFERENT subsets of it, because the admissible set depends on
    # the derivation rule that wrote it. Pinned against the causation block's
    # projection, the browser's copy passed while four of the licences the
    # cell can carry had no translation at all.
    "interventional_risk_provenance": Glossed(
        gloss="themis.risk_provenance.describe",
        browser_table="RISK_PROVENANCE_WORDS",
        members=lambda: _stated("themis.risk_provenance.RiskProvenance"),
    ),
    # What a partial-identification interval brackets, and the second
    # quantity the same identified set is read through. Both are one-member
    # enums today; they are anchored anyway, because a one-member vocabulary
    # is exactly the one nobody notices growing.
    "bounds_estimand": Glossed(
        gloss="themis.output.analysis_report._BOUNDS_ESTIMAND_WORDS",
        browser_table="BOUNDS_ESTIMAND_WORDS",
        members=lambda: _enum_at(*_DEFS, "boundsResult", "properties",
                                 "estimand"),
    ),
    "bounds_contrast_kind": Glossed(
        gloss="themis.output.analysis_report._BOUNDS_CONTRAST_WORDS",
        browser_table="BOUNDS_CONTRAST_WORDS",
        members=lambda: _enum_at(*_DEFS, "boundsResult", "properties",
                                 "contrast", "properties", "kind"),
    ),
    # Which theorem the decomposition failed on. ``null`` is dropped from
    # both: it is the absence of a failure, not a member — the arm renders
    # "可识别" and never asks the table.
    "nde_nie_failed_condition": Glossed(
        gloss="themis.output.envelope_glossary.nde_nie_condition_word",
        browser_table="NDE_NIE_CONDITION_WORDS",
        members=lambda: _enum_at(*_EXT, "mediation_decomposition",
                                 "properties", "nde_nie", "properties",
                                 "failed_condition") - {None},
    ),
    "cde_failed_condition": Glossed(
        gloss="themis.output.envelope_glossary.cde_condition_word",
        browser_table="CDE_CONDITION_WORDS",
        members=lambda: _enum_at(*_EXT, "mediation_decomposition",
                                 "properties", "cde", "properties",
                                 "failed_condition") - {None},
    ),
    # Three producers state this, and the robust one can return a shape the
    # other two cannot, so the union is the vocabulary — anchoring on either
    # of the smaller two would let the browser drop the shape only the
    # polynomial inversion produces and still pass.
    "anderson_rubin_set_kind": Glossed(
        gloss="themis.output.envelope_glossary.ar_set_kind_word",
        browser_table="AR_SET_KIND_WORDS",
        members=lambda: (
            _enum_at(*_NE, "anderson_rubin_confidence_set", "properties",
                     "kind")
            | _enum_at(*_NE, "stratified_anderson_rubin_confidence_set",
                       "properties", "kind")
            | _enum_at(*_NE, "robust_anderson_rubin_confidence_set",
                       "properties", "kind")
            | _enum_at(*_EXT, "anderson_rubin_region", "properties", "region",
                       "properties", "projections", "items", "properties",
                       "kind")
        ),
    ),
    # What the k-dimensional region says about the vector as a WHOLE, which
    # the vocabulary above cannot say: those six classify a set on a line,
    # and a region can be unbounded in one direction while every coordinate
    # projects onto something finite in another. One vocabulary per question,
    # so a reader is never handed "bounded" for two different questions.
    # Which way a K-way interaction went missing. Both members leave the
    # joint contrast standing, so neither is a refusal — but one asks the
    # reader for a cell the data does not have and the other for a shorter
    # treatment vector, and a reader who cannot tell them apart cannot act
    # on either.
    "interaction_unavailable_kind": Glossed(
        gloss="themis.output.analysis_report._INTERACTION_UNAVAILABLE_WORDS",
        browser_table="INTERACTION_UNAVAILABLE_WORDS",
        members=lambda: _enum_at(*_NE, "interaction_unavailable",
                                 "properties", "kind"),
    ),
    # Why one source domain's effect does not reach the target. The two
    # members differ in whose fact they are: one says the diagram never had
    # the treatment or the outcome on it, the other says it did and no
    # adjustment set evens the two populations out. A reader deciding which
    # domain to go and measure needs the difference, and the sibling domains
    # on the same block may well be transporting fine.
    "transport_blocked_kind": Glossed(
        gloss="themis.output.analysis_report._TRANSPORT_BLOCKED_WORDS",
        browser_table="TRANSPORT_BLOCKED_WORDS",
        members=lambda: _enum_at(*_EXT, "transport_identification",
                                 "properties", "sources", "items",
                                 "properties", "blocked_by"),
    ),
    "anderson_rubin_region_shape": Glossed(
        gloss="themis.output.analysis_report._REGION_SHAPE_WORDS",
        browser_table="REGION_SHAPE_WORDS",
        members=lambda: _enum_at(*_EXT, "anderson_rubin_region", "properties",
                                 "region", "properties", "shape"),
    ),
    # Which margin a misclassification correction inverted. Two sites hold it
    # — the block and the sufficient statistics the verifier re-derives from —
    # and the union is the vocabulary for the same reason it is above.
    "measurement_correction_side": Glossed(
        gloss="themis.output.envelope_glossary.measurement_side_word",
        browser_table="MEASUREMENT_SIDE_WORDS",
        members=lambda: (
            _enum_at(*_NE, "measurement_correction", "properties", "side")
            | _enum_at(*_NE, "measurement_correction", "properties",
                       "sufficient_statistics", "properties", "side")
        ),
    ),
    # Which VanderWeele closed form the ratio-scale split used. The same two
    # tokens name a column's measurement scale elsewhere and that is a
    # different vocabulary, so this is anchored on its own site.
    "four_way_mediator_scale": Glossed(
        gloss="themis.output.envelope_glossary.four_way_mediator_scale_word",
        browser_table="FOUR_WAY_MEDIATOR_SCALE_WORDS",
        members=lambda: _enum_at(*_NE, "four_way_ratio", "properties",
                                 "mediator_scale"),
    ),
    "outcome_error_design": Glossed(
        gloss="themis.output.analysis_report._OUTCOME_ERROR_DESIGN_WORDS",
        browser_table="OUTCOME_ERROR_DESIGN_WORDS",
        members=lambda: _enum_at("properties", "outcome_error", "properties",
                                 "design_kind"),
    ),
    # The E-value's reading and which of the two E-values it was read off.
    # ``null`` drops from both: it is the absence of a reading, not a member
    # — a block with no E-value has nothing to band, and the browser renders
    # no line rather than asking the table.
    "evalue_interpretation_band": Glossed(
        gloss="themis.output.envelope_glossary.evalue_band_word",
        browser_table="EVALUE_BAND_WORDS",
        members=lambda: _enum_at(*_NE, "sensitivity_analysis", "properties",
                                 "interpretation_band") - {None},
    ),
    "evalue_band_basis": Glossed(
        gloss="themis.output.envelope_glossary.evalue_band_basis_word",
        browser_table="EVALUE_BAND_BASIS_WORDS",
        members=lambda: _enum_at(*_NE, "sensitivity_analysis", "properties",
                                 "band_basis") - {None},
    ),
    # What an interval's width is a fact about. Anchored on the module and
    # not on either schema site, for the reason the licences above are: the
    # two sites hold the two members a RUN can settle, and the third
    # classifies a slot and never travels as a value. A browser holding two
    # of the three would pass against either site and answer the bounds
    # section with a word about sampling.
    "interval_width": Glossed(
        gloss="themis.intervals.width_word",
        browser_table="INTERVAL_WIDTH_WORDS",
        members=lambda: _stated("themis.intervals.Width"),
    ),
    "interval_tightness": Glossed(
        gloss="themis.intervals.tightness_word",
        browser_table="TIGHTNESS_WORDS",
        members=lambda: _enum_at(*_DEFS, "boundsResult", "properties",
                                 "tightness"),
    ),
    # The way past one refusal, as opposed to the kind that classifies it.
    # Anchored on the schema site rather than on ``refusals.Remedy`` for the
    # reason ``outcome_error_design`` is: the browser reads the routes off
    # the envelope, so what it has to state is what the envelope may carry.
    "remedy": Glossed(
        gloss="themis.refusals.remedy_word",
        browser_table="REMEDY_WORDS",
        members=lambda: _enum_at(*_DEFS, "remedy", "properties", "remedy"),
    ),
    # The one vocabulary here that no schema enum states at all: ``step.rule``
    # is a free string in derivation.schema.json, and the closed set is the
    # glossary — which is also what the report renders.
    "derivation_rule": Glossed(
        gloss="themis.output.derivation_glossary.SAYS",
        browser_table="DERIVATION_SAYS",
        members=lambda: frozenset(
            _resolve("themis.output.derivation_glossary.SAYS")),
    ),
    # --- and the six a refusal's sentence is made of --------------------------
    #
    # These are not glosses a surface shows beside a value; they are what a
    # surface ASSEMBLES with. A refusal leaves the kernel as a species, its
    # rendered value slots and its word slots (#411), so every surface that
    # shows one holds the species' templates and the sets those word slots
    # are drawn from. The browser holds them for the same reason it holds
    # the twenty above and by the same route.
    #
    # The template table's members are the schema's enum rather than
    # ``refusals.SAYS`` itself: what the browser has to be able to say is
    # every species an envelope may carry, and a table pinned against its
    # own keys would agree with itself while the enum admitted a species it
    # had no sentence for.
    "refusal_sentence": Glossed(
        gloss="themis.refusals.SAYS",
        browser_table="REFUSAL_SAYS",
        members=lambda: _enum_at("properties", "estimator_failure",
                                 "properties", "failure_type"),
    ),
    "query_role": Glossed(
        gloss="themis.refusals.QueryRole.said",
        browser_table="QUERY_ROLE_WORDS",
        members=lambda: _stated("themis.refusals.QueryRole"),
    ),
    "monotonicity_refutation": Glossed(
        gloss="themis.refusals.Refutation.said",
        browser_table="REFUTATION_WORDS",
        members=lambda: _stated("themis.refusals.Refutation"),
    ),
    "recovery_mechanism": Glossed(
        gloss="themis.refusals.Recovery.said",
        browser_table="RECOVERY_WORDS",
        members=lambda: _stated("themis.refusals.Recovery"),
    ),
    "singular_matrix": Glossed(
        gloss="themis.refusals.Design.said",
        browser_table="SINGULAR_MATRIX_WORDS",
        members=lambda: _stated("themis.refusals.Design"),
    ),
    "bridge_side": Glossed(
        gloss="themis.refusals.BridgeSide.said",
        browser_table="BRIDGE_SIDE_WORDS",
        members=lambda: _stated("themis.refusals.BridgeSide"),
    ),
    # Why a program cannot be run at all. The one vocabulary here that
    # never reaches a query RESULT: a program refused at the door produces
    # no envelope, so its reader is the failure body ``/api/*`` returns and
    # the browser's own error line. Restated there like everything else,
    # because that surface cannot import this one either.
    "malformed_program": Glossed(
        gloss="themis.input.semantic_validator.Malformed.said",
        browser_table="MALFORMED_WORDS",
        members=lambda: _stated(
            "themis.input.semantic_validator.Malformed"),
    ),
    # The three a proximal refusal is made of. The criterion carries a whole
    # SENTENCE rather than a noun phrase — which is what the identification
    # layer had been writing at the return site, one language at a time —
    # and the role goes into one of that sentence's holes. Both are read
    # inside another sentence again, because the frame around them belongs
    # to whichever channel relayed the refusal: the gap list has one and the
    # estimator's failure note has another.
    "proximal_criterion_failure": Glossed(
        gloss="themis.runtime.proximal_identify.Criterion.said",
        browser_table="PROXIMAL_CRITERION_WORDS",
        members=lambda: _stated("themis.runtime.proximal_identify.Criterion"),
    ),
    "proximal_role": Glossed(
        gloss="themis.runtime.proximal_identify.Role.said",
        browser_table="PROXIMAL_ROLE_WORDS",
        members=lambda: _stated("themis.runtime.proximal_identify.Role"),
    ),
    # And what the graph left for the data. Carried as a LIST of tokens, so
    # the surface looks each one up and joins them in its own punctuation.
    "proximal_data_condition": Glossed(
        gloss="themis.runtime.proximal_identify.DataCondition.said",
        browser_table="PROXIMAL_DATA_CONDITION_WORDS",
        members=lambda: _stated(
            "themis.runtime.proximal_identify.DataCondition"),
    ),
    "outcome_error_premise": Glossed(
        gloss="themis.estimation.outcome_error.Premise.said",
        browser_table="OUTCOME_ERROR_PREMISE_WORDS",
        members=lambda: _stated("themis.estimation.outcome_error.Premise"),
    ),
    # Why an E-value did not come out. Reached through the generic carrier
    # rather than a channel of its own — the block names the vocabulary and
    # the token, so a surface looks the sentence up here the same way it
    # looks up a word inside one.
    "e_value_undefined": Glossed(
        gloss="themis.estimation.sensitivity.Undefined.said",
        browser_table="E_VALUE_UNDEFINED_WORDS",
        members=lambda: _stated("themis.estimation.sensitivity.Undefined"),
    ),
    # What one variable's declaration says about how it was measured. Reached
    # through the carrier too, but one level further in: a gap's own sentence
    # holds a LIST of these in a single slot, so what a surface looks up here
    # is a sentence that goes inside another sentence.
    "measurement_note": Glossed(
        gloss="themis.output.data_gap_report.Measurement.said",
        browser_table="MEASUREMENT_NOTE_WORDS",
        members=lambda: _stated("themis.output.data_gap_report.Measurement"),
    ),
    # The three a gap's `required_data` states rather than values: what a
    # sample of the size beside it would buy, when the measurements would
    # have to be taken, and how the design could break SUTVA. Reached
    # through the carrier, like the two above.
    "precision_target": Glossed(
        gloss="themis.output.sample_size.Precision.said",
        browser_table="PRECISION_TARGET_WORDS",
        members=lambda: _stated("themis.output.sample_size.Precision"),
    ),
    "time_window": Glossed(
        gloss="themis.output.data_gap_report.Window.said",
        browser_table="TIME_WINDOW_WORDS",
        members=lambda: _stated("themis.output.data_gap_report.Window"),
    ),
    "sutva_concern": Glossed(
        gloss="themis.output.data_gap_report.Sutva.said",
        browser_table="SUTVA_CONCERN_WORDS",
        members=lambda: _stated("themis.output.data_gap_report.Sutva"),
    ),
    # And the three a symbolic bound states rather than values: what is true
    # of the interval that no other field on its row carries, which
    # distribution a client must supply and how big its table is, and which
    # end of an interval an assumption moved. The last goes inside the
    # first, which is why it is a vocabulary of its own rather than two
    # sentences that differ by a word.
    # Which way the treatment may move the outcome. Named for what it says
    # rather than for the first container it was seen in — it reached the
    # envelope through a counterfactual cell and an assumption id, and it
    # reaches it through a bounds note as well.
    "monotonicity": Glossed(
        gloss="themis.ledger.Monotonicity.said",
        browser_table="MONOTONICITY_WORDS",
        members=lambda: _stated("themis.ledger.Monotonicity"),
    ),
    "bounds_note": Glossed(
        gloss="themis.output.bounds.Note.said",
        browser_table="BOUNDS_NOTE_WORDS",
        members=lambda: _stated("themis.output.bounds.Note"),
    ),
    "observable_required": Glossed(
        gloss="themis.output.bounds.Observable.said",
        browser_table="OBSERVABLE_REQUIRED_WORDS",
        members=lambda: _stated("themis.output.bounds.Observable"),
    ),
    "bound_side": Glossed(
        gloss="themis.output.bounds.Side.said",
        browser_table="BOUND_SIDE_WORDS",
        members=lambda: _stated("themis.output.bounds.Side"),
    ),
    # What a ledger line says the answer rests on. The largest table here by
    # a long way, and the one that shows what a vocabulary is when its
    # tokens are not ours: the keys are the assumption ids estimators
    # declare, so there are no member names to write and nothing would
    # reference them if there were. Anchored on the table itself, which is
    # the only declaration — the schema types the id as a free string,
    # because an estimator adding one is not a change to the envelope.
    "assumption_claim": Glossed(
        gloss="themis.output.assumption_glossary.CLAIMS",
        browser_table="ASSUMPTION_CLAIM_WORDS",
        members=lambda: frozenset(
            _resolve("themis.output.assumption_glossary.CLAIMS")),
    ),
    # What a discovery run says about itself, and the second table here
    # whose tokens are its own rather than somebody else's — an algorithm's
    # note, a precondition the data broke, why the selector chose what it
    # chose. Anchored on the table, because no schema enumerates the tokens:
    # they ride on the statement carrier, whose token field is a free string
    # for the same reason the assumption ids above are.
    "discovery_note": Glossed(
        gloss="themis.estimation.discovery_words.NOTES",
        browser_table="DISCOVERY_NOTE_WORDS",
        members=lambda: frozenset(
            _resolve("themis.estimation.discovery_words.NOTES")),
    ),
    # The three tokens a simulation-extrapolation estimate puts in front of
    # a reader. Anchored on the schema rather than on the tables, because
    # the envelope is what the browser reads and these ARE enum sites —
    # unlike the two rows above, whose tokens ride on a free string.
    "simex_outcome_model": Glossed(
        gloss="themis.estimation.simex_words.OUTCOME_MODELS",
        browser_table="SIMEX_OUTCOME_MODEL_WORDS",
        members=lambda: _enum_at(*_NE, "simex", "properties",
                                 "outcome_model"),
    ),
    "simex_extrapolant": Glossed(
        gloss="themis.estimation.simex_words.EXTRAPOLANTS",
        browser_table="SIMEX_EXTRAPOLANT_WORDS",
        members=lambda: _enum_at(*_NE, "simex", "properties", "extrapolant"),
    ),
    "simex_no_interval": Glossed(
        gloss="themis.estimation.simex_words.NO_INTERVAL",
        browser_table="SIMEX_NO_INTERVAL_WORDS",
        # ``null`` is on that enum because the field is always written and is
        # null when an interval DID ship. It is the absence of a reason, not
        # a reason, so it is not a member here — the same reading the
        # vocabulary registry takes of every nullable enum.
        members=lambda: _enum_at(*_NE, "simex", "properties",
                                 "no_interval_because") - {None},
    ),
    # And the same field's other two channels. A number the model supplied
    # is one sentence; a gap's own statements are however many that gap has,
    # and they are the table two rows down under a name of their own — the
    # ledger reaches them through the carrier rather than through the gap.
    "theta_prior_claim": Glossed(
        gloss="themis.output.result_orchestrator.Prior.said",
        browser_table="THETA_PRIOR_CLAIM_WORDS",
        members=lambda: _stated("themis.output.result_orchestrator.Prior"),
    ),

    # --- and the four the two recovery verdicts are made of -----------------
    #
    # Each block can name the theorem that carried a POSITIVE verdict and
    # had nothing to name what a negative came back empty on, so the whole
    # of a negative was one sentence. These are the halves that sentence
    # was hiding: which condition (the two shortfalls), and what an
    # unbiased sample or a product's factor has to be (the two labels,
    # which used to be an English role word glued onto a symbolic
    # expression).
    "selection_recovery_shortfall": Glossed(
        gloss="themis.runtime.selection_recovery.Shortfall.said",
        browser_table="SELECTION_SHORTFALL_WORDS",
        members=lambda: _stated(
            "themis.runtime.selection_recovery.Shortfall"),
    ),
    "unbiased_distribution": Glossed(
        gloss="themis.runtime.selection_recovery.External.said",
        browser_table="UNBIASED_DISTRIBUTION_WORDS",
        members=lambda: _stated("themis.runtime.selection_recovery.External"),
    ),
    "missing_data_shortfall": Glossed(
        gloss="themis.runtime.missing_data.Shortfall.said",
        browser_table="MISSING_DATA_SHORTFALL_WORDS",
        members=lambda: _stated("themis.runtime.missing_data.Shortfall"),
    ),
    "recovery_factor": Glossed(
        gloss="themis.runtime.missing_data.Factor.said",
        browser_table="RECOVERY_FACTOR_WORDS",
        members=lambda: _stated("themis.runtime.missing_data.Factor"),
    ),

    # --- and the two a shortfall's sentence is made of ------------------------
    #
    # The same arrangement one channel over. A missing item, an
    # investigation item and a request's note all leave the kernel as a
    # species and the two halves of an occasion, exactly as a refusal
    # does, so the surfaces that show one assemble it from the same two
    # kinds of table. Members from the schema enum for the reason stated
    # just above.
    "gap_says": Glossed(
        gloss="themis.gaps.SAYS",
        browser_table="GAP_SAYS",
        members=lambda: _enum_at(*_DEFS, "need"),
    ),
    # What stands where the occasion has no name for it. Read inside a
    # statement's hole rather than carried on its own, for the reason
    # ``measurement_scale`` is restated: the surface assembles the sentence,
    # so it needs the placeholder and not the token.
    "unnamed_thing": Glossed(
        gloss="themis.gaps.Unnamed.said",
        browser_table="UNNAMED_WORDS",
        members=lambda: _stated("themis.gaps.Unnamed"),
    ),
    "query_part": Glossed(
        gloss="themis.gaps.QueryPart.said",
        browser_table="QUERY_PART_WORDS",
        members=lambda: _stated("themis.gaps.QueryPart"),
    ),
    # Restated because it is read inside a route's sentence rather than
    # carried on its own: the browser assembles that sentence, so it needs
    # the adjective and not the token.
    "measurement_scale": Glossed(
        gloss="themis.output.envelope_glossary.Scale.said",
        browser_table="MEASUREMENT_SCALE_WORDS",
        members=lambda: _stated("themis.output.envelope_glossary.Scale"),
    ),

    # What would close a gap, which is the other question a reader shown one
    # asks. Restated because both surfaces build a next-steps line out of it
    # — the line used to arrive finished, in one language, on the envelope.
    #
    # ``themis.gaps.WANTED_NAMED`` is deliberately NOT here. It is the same
    # phrase for the occasions that can name the variables it wants, and
    # reaching it means knowing which provenance channel carries the name
    # for which kind — logic, not words, and a second copy of it in
    # TypeScript is what this module exists to avoid. The browser prints
    # ``required_data.variables`` on the gap itself, so the names are on the
    # surface either way; the report's line is the richer of the two.
    "gap_wanted": Glossed(
        gloss="themis.gaps.WANTED",
        browser_table="GAP_WANTED",
        members=lambda: _enum_at(*_DEFS, "dataGap", "properties", "kind"),
    ),

    # What the gap says about itself. One row per statement rather than
    # per kind: the same statement is said by more than one kind (the
    # displaced-layer pair, the two type-mismatch consequences), and a kind
    # says more than one of them whenever a branch adds a fact. Members
    # from the schema enum for the reason stated above.
    "gap_describes": Glossed(
        gloss="themis.gaps.DESCRIBES",
        browser_table="GAP_DESCRIBES",
        members=lambda: _enum_at(*_DEFS, "sentence"),
    ),

    # The ways past a gap. Templates rather than finished words, for the
    # reason ``refusal_sentence`` is: the route leaves the kernel as a
    # token plus this occasion's facts, so every surface that shows one
    # fills the same sentence.
    "gap_route": Glossed(
        gloss="themis.gaps.ROUTES",
        browser_table="GAP_ROUTES",
        members=lambda: _enum_at(*_DEFS, "route"),
    ),

    # And what having the missing thing would buy — the third sentence a
    # gap is made of, and the only one of the three that is PARTIAL. The
    # species a reader gets no such line for are named in
    # ``themis.gaps.NOTHING_FILLS``, so the members here are every kind an
    # envelope may carry minus those: anchoring on this table's own keys
    # would let it agree with itself while a new species had no sentence
    # and no reason for not having one, which is the shape (325) names.
    "gap_if_provided": Glossed(
        gloss="themis.gaps.IF_PROVIDED",
        browser_table="GAP_IF_PROVIDED",
        members=lambda: (_enum_at(*_DEFS, "dataGap", "properties", "kind")
                         - frozenset(_resolve("themis.gaps.NOTHING_FILLS"))),
    ),

    # --- glossed, and the browser does not restate them -----------------------
    #
    # Three of these it renders in its own terms instead (a tier's label
    # beside a plain-language gloss, a status's label beside a blurb, a
    # refusal's head/lead/tail); the rest reach a reader through the report
    # or the explainer only. Either way the accessor belongs here, because
    # what a row states is how a reader gets the word — not who asks.
    "answer_tier": Glossed(
        gloss="themis.output.analysis_report._TIER_WORDS"),
    "result_status": Glossed(
        gloss="themis.output.analysis_report._STATUS_BADGE"),
    "refusal_kind": Glossed(
        gloss="themis.output.analysis_report._kind_word"),
    "framing_field": Glossed(
        gloss="themis.output.envelope_glossary.framing_field_word"),
    "investigation_action": Glossed(
        gloss="themis.output.explainer._ACTION_PHRASE"),
    "missing_data_mechanism": Glossed(
        gloss="themis.output.analysis_report._MECHANISM_WORDS"),
    "priority": Glossed(
        gloss="themis.output.explainer._PRIORITY_PHRASE"),

    # The interactive orientation session, whose reader is whoever is being
    # asked. No browser table: the four orientation artifacts are a Python
    # and MCP surface and the browser does not show them, which is a
    # statement about where they are read rather than an omission — the
    # words are here so that the surface which DOES read them has both
    # languages to choose from, which is the whole of what #467 moved.
    "orientation_asks": Glossed(
        gloss="themis.estimation.orientation_questions.Asks.said"),
    "orientation_question_set_says": Glossed(
        gloss="themis.estimation.orientation_questions.Says.said"),
    # And what each standalone artifact says about ITSELF, on its `note`.
    # #467 opened the door and took the question through it; these four are
    # the rest of the population it was owed to. No browser table for the
    # same reason as the two above — the discovery and orientation artifacts
    # are a Python and MCP surface.
    "orientation_propagation_says": Glossed(
        gloss="themis.estimation.orientation.Says.said"),
    "orientation_session_says": Glossed(
        gloss="themis.estimation.orientation_session.Says.said"),
    "markov_blanket_says": Glossed(
        gloss="themis.estimation.discovery_words.Blanket.said"),
    "lagged_discovery_says": Glossed(
        gloss="themis.estimation.discovery_words.Lagged.said"),
    # And why the LLM-side front door refused what it was handed. Its
    # reader is whoever produced the extraction — an LLM asked for
    # structured output, or the agent driving it — and it is not a
    # browser surface either: `themis/upstream` has no consumer inside
    # this repository, which is what makes the caller the reader.
    "extraction_shape": Glossed(
        gloss="themis.upstream.extraction_words.Shape.said"),
    "extraction_refusal": Glossed(
        gloss="themis.upstream.extraction_words.Refuses.said"),
}


def word(vocabulary: str, member: str, lang: language.Lang | str) -> str:
    """What a reader of ``lang`` is handed for one member.

    Through the accessor the kernel's own surfaces call, not through the
    table behind it: what a second surface has to match is what a reader is
    actually given, and a gloss that transforms its table on the way out
    would make those two different texts.
    """
    gloss = _resolve(GLOSSED[vocabulary].gloss)
    if isinstance(gloss, dict):
        return language.gloss(gloss, member, lang, unknown="")
    return gloss(member, lang)


#: The kernel's punctuation, by the name both surfaces know it under.
#:
#: Plain :data:`Words` the browser also holds — no token, no member, no
#: holes, and therefore not vocabularies.
#:
#: They are here for the reason every table here is: two records of one
#: fact drift. A separator is the easiest of all of them to drift, and a
#: language's own name is the one string that must not be written in
#: anybody else's — telling an English reader "Chinese" is telling them in
#: the language they were asking not to read — so a chooser needs the
#: endonyms and a second copy of them is a second place to get one wrong.
PLAIN: dict[str, str] = {
    name: f"themis.language.{name}"
    for name in ("BETWEEN_ITEMS", "BETWEEN_SENTENCES",
                 "BETWEEN_CLAUSES", "BETWEEN_STATEMENTS", "ENDONYM")
}


def restated() -> dict[str, Glossed]:
    """The vocabularies the browser holds a copy of, generated from here."""
    return {name: row for name, row in GLOSSED.items() if row.browser_table}


def plain() -> dict[str, dict[str, str]]:
    """``name -> language -> the text``, for every plain table above."""
    return {
        name: {lang: language.fill(_resolve(dotted), lang)
               for lang in _language_order()}
        for name, dotted in PLAIN.items()
    }


def _language_order() -> list[str]:
    """The languages, in the order the generated file writes them.

    Answered-in first, in the order they are declared, then the ones whose
    words are being written. Any total order would do for a machine; this
    one is for the person reading the diff, and it puts the language a
    reader can actually be answered in on the first line of every entry.
    """
    answered = [str(lang) for lang in language.Lang]
    return answered + sorted(language.written() - set(answered))


def _without_emphasis(text: str) -> str:
    """One word, for a surface that renders no markdown.

    The report writes markdown and puts ``**`` around the clause a reader
    must not skim past; the browser's chips and rows render text, so the
    same markers would reach a reader as four asterisks. Which surface
    renders what is known here and nowhere else on the way, so the choice
    is made here — the alternative is a markdown stripper in TypeScript,
    which is a second place to decide the same thing.
    """
    return text.replace("**", "")


def tables() -> dict[str, dict[str, dict[str, str]]]:
    """``table name -> member -> language -> word``, for every restated one.

    Every language this build writes, not the one it answers in. A language
    with no reader yet is the one most able to drift unnoticed, and it is
    already written on both surfaces.
    """
    return {
        row.browser_table: {
            member: {lang: _without_emphasis(word(name, member, lang))
                     for lang in _language_order()}
            for member in sorted(row.members())
        }
        for name, row in restated().items()
    }


# --- the browser's copy -------------------------------------------------------

#: Where the generated module is written. Checked in rather than built,
#: because the browser's build must not need a Python interpreter and a
#: reader of the source must be able to see what it says.
GENERATED = (pathlib.Path(__file__).resolve().parent.parent
             / "web" / "frontend" / "src" / "lib" / "kernelWords.generated.ts")

_HEADER = """\
// GENERATED FILE — DO NOT EDIT.
//
// Written by themis/output/reader_words.py from the kernel's own glosses.
// Regenerate with `python -m themis.output.reader_words`; the suite fails
// when this file and the kernel disagree, so a hand edit is reverted by the
// next regeneration rather than kept.
//
// What is here: every closed vocabulary the browser RESTATES — the same
// words the report gives a reader, in every language this build writes —
// and, at the end, the kernel's punctuation, which is not a vocabulary but
// is the same fact about the reader's language and is needed wherever this
// surface joins a list or two sentences. What is not: the tables that render
// a vocabulary in the browser's own terms (a tier's plain-language gloss, a
// status's blurb, a refusal's head/lead/tail) and the two the kernel
// deliberately has no word for (a gap carries its own description; a query
// kind is glossed by a whole question line).
import type { Words } from './language'
"""

#: A key that needs no quotes in an object literal. Quoting every key would
#: read as a machine's output where the hand-written tables read as source,
#: and this file is meant to be read.
_BARE = re.compile(r"[A-Za-z_$][\w$]*\Z")


def _quoted(text: str) -> str:
    """One word as a TypeScript single-quoted string."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _key(member: str) -> str:
    return member if _BARE.match(member) else _quoted(member)


def typescript() -> str:
    """The generated module, as source.

    One table per vocabulary and one line per member-language pair, so that
    a diff on this file reads as the words that changed.
    """
    built = tables()
    out = [_HEADER]
    for name, row in sorted(restated().items()):
        out.append(f"\nexport const {row.browser_table}: "
                   f"Record<string, Words> = {{\n")
        for member, said in built[row.browser_table].items():
            out.append(f"  {_key(member)}: {{\n")
            for lang, text in said.items():
                out.append(f"    {lang}: {_quoted(text)},\n")
            out.append("  },\n")
        out.append("}\n")
    for name, said in sorted(plain().items()):
        out.append(f"\nexport const {name}: Words = {{\n")
        for lang, text in said.items():
            out.append(f"  {lang}: {_quoted(text)},\n")
        out.append("}\n")
    return "".join(out)


def write() -> pathlib.Path:
    """Regenerate the browser's copy in place."""
    GENERATED.write_text(typescript(), encoding="utf-8", newline="\n")
    return GENERATED


if __name__ == "__main__":  # pragma: no cover - a build step, not a path
    print(write())
