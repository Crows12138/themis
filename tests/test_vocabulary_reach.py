"""Every closed vocabulary, where it is declared, and who turns it into words.

A vocabulary is written in one place and restated wherever it has to be
read: a JSON schema that admits the envelope, a prompt an LLM answers from,
a reference table a person opens, a mapping that gives a reader the word.
Nothing makes a restatement follow its declaration, so each restatement
needs a pin — and pinning some of them says nothing about the rest.

``tests/test_web_vocabularies.py`` solved that for the browser, and the
shape it used does not carry over. It can ask ``verdict.ts`` "is every
table in this file accounted for", because the file declares its tables as
``const NAME: Record<...>``. A prompt is prose; it has no declaration unit
to enumerate, so there is nothing to partition. That is why the browser
ended up guarded and the other surfaces did not — the boundary fell exactly
where a surface stopped being enumerable, not where anyone decided it
should.

So this module enumerates the OTHER side. Not "what does this surface
carry" but "what does the kernel declare, and where must each of them
land".

**The kernel declares through two doors, and this module used to watch
one.** It walked ``enum.Enum``'s subclasses and asked each whether the
envelope carried it. But a JSON schema is equally the kernel's
declaration, and 42 of the envelope's enum sites had no Python enum at
all — they were never asked anything. Whether a vocabulary got a Python
enum was decided by whether the kernel had to branch on it, which is
unrelated to whether a reader ever sees a member, so the question that
went unasked was exactly the one whose answer varies: a mediation
condition reached a Chinese sentence as ``M3``, a predicate's unset fields
as ``time_window, measurement, threshold``, a type mismatch as an English
paragraph in an otherwise Chinese report.

Both doors are walked below, and one row per vocabulary answers for both:
which Python enum states it, which schema sites state it, and who gives a
reader the word. A vocabulary arriving through either door with no row
fails here.

**A third door cannot be watched from this side.** A vocabulary whose only
declaration is the glossary that translates it — ``derivation_glossary``'s
rule names are the one live case — is invisible to both walks, because
there is nothing to walk. It is caught where it is rendered instead:
``tests/test_derivation_glossary.py`` and the browser's ``ANCHORS``. Naming
that here rather than leaving the gap silent is the point; a partition that
claims more than it can see is worth less than one that says where it ends.

The browser is not checked here. It has a stronger pin already, and a
weaker duplicate of a stronger check is worth less than nothing: it reads
as coverage while admitting what the real one rejects.
"""
from __future__ import annotations

import enum
import importlib
import json
import pathlib
import pkgutil
from dataclasses import dataclass, field

import pytest
from themis import language

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"

Site = tuple[str, ...]


# --- the two doors -----------------------------------------------------------

def _python_vocabularies() -> dict[str, type[enum.Enum]]:
    """Every closed vocabulary the package declares in Python.

    Found by importing the package and walking ``Enum``'s subclasses rather
    than by reading the source for a list of base names: the registries here
    inherit through ``EnvelopeName`` and a source scan for ``StrEnum``
    misses all of them, which is the failure this module exists to make
    impossible.

    Members-less classes are the marker bases themselves and are skipped;
    they declare no vocabulary, they declare how one behaves.
    """
    import themis

    for mod in pkgutil.walk_packages(themis.__path__, "themis."):
        if "web.frontend" in mod.name:
            continue
        try:
            importlib.import_module(mod.name)
        except ImportError:
            continue

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return {
        f"{cls.__module__}.{cls.__qualname__}": cls
        for cls in walk(enum.Enum)
        if cls.__module__.startswith("themis") and len(cls) > 0
    }


def _schema_sites() -> dict[Site, list]:
    """Every ``enum`` in every schema, keyed by the path that reaches it.

    Keyed by path and not by value-set, because two sites holding the same
    values are not thereby one vocabulary — ``binary``/``continuous`` names
    a mediator's scale in one place and which ATE-to-risk-ratio conversion
    ran in another, and a row covering both would say they move together.
    """
    def walk(node, path):
        if isinstance(node, dict):
            if isinstance(node.get("enum"), list):
                yield tuple(path), node["enum"]
            for k, v in node.items():
                yield from walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, path + [str(i)])

    out: dict[Site, list] = {}
    for f in sorted(SCHEMAS.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for path, values in walk(doc, [f.name]):
            out[path] = values
    return out


# --- one row per vocabulary --------------------------------------------------

@dataclass(frozen=True)
class Vocabulary:
    """Where one closed vocabulary is declared, and who reads it.

    ``glossed_by`` and ``no_gloss`` are exclusive and one is required: a
    vocabulary either hands a reader a word for every member or says why no
    reader needs one. The reason is a claim rather than an exemption — it
    has to name what the reader gets instead, which is the sentence somebody
    has to disagree with before a member reaches a report as its own
    identifier.

    ``sites`` and ``off_envelope`` are exclusive the same way: the union of
    the sites has to be exactly the members, and a vocabulary no schema
    states has to say why the envelope never carries it.
    """

    declares: str = ""
    """Dotted name of the Python enum that states it, if one does."""

    sites: tuple[Site, ...] = ()
    """Schema enum sites whose UNION is exactly the members.

    A tuple because one vocabulary can be carried by more than one
    container, each holding a different subset — the licences a
    counterfactual cell may declare are not the ones a causation block may,
    because the admissible set depends on the rule that wrote it. Equality
    against either site alone would pass while half the vocabulary went
    unstated.
    """

    off_envelope: str = ""
    """Why no schema states it — it reaches a reader some other way, or not
    at all, and saying which is the point."""

    glossed_by: str = ""
    """Dotted name of the mapping or callable that gives the reader's word.

    Asked once per member, so a mapping missing a key and a callable falling
    through to the identifier both fail here. That is the whole check: a
    gloss that answers with the token it was given has not glossed it.
    """

    no_gloss: str = ""
    """Why no reader needs a word for it."""

    partly_stated: str = ""
    """Why the sites state a PROPER subset of the members.

    Equality is the rule, and one direction of it is not negotiable: a
    value the schema admits and the kernel never emits is a case a reader
    believes was handled. The other direction has one honest cause — a
    member that classifies a SLOT reaches a reader through the slot and
    can never appear as a value on a row — and this is where that has to
    be said. A claim rather than an exemption: it names which members the
    envelope cannot carry and how they reach a reader instead, and it goes
    stale loudly, because a row whose sites have caught up fails here.
    """

    subset_of: str = ""
    """Set when the site is a constraint written in terms of another
    vocabulary rather than a vocabulary of its own — a schema ``if``/``not``
    naming two methods is a rule about ``numeric_method``, and giving it a
    row of its own would say the envelope carries a second method field."""

    members: frozenset[str] = field(default_factory=frozenset)
    """Only for a vocabulary neither door fully states — left empty
    otherwise, and derived from whichever door does."""


_QR = "query_result.schema.json"
_KA = "kernel_ast.schema.json"
_EXT = (_QR, "properties", "extensions", "properties")
_NE = (_QR, "properties", "numeric_estimate", "properties")
_DEFS = (_QR, "$defs")
_GLOSSARY = "themis.output.envelope_glossary"
_REPORT = "themis.output.analysis_report"

#: The five standalone artifacts (#387). Their vocabularies reach a machine —
#: a second implementation that re-derives the artifact — rather than a report
#: or a browser, and each row below has to say what its reader gets instead.
_MB = "markov_blanket.schema.json"
_OP = "orientation_propagation.schema.json"
_OQ = "orientation_question_set.schema.json"
_OS = "orientation_session.schema.json"
_OL = "orientation_ledger_export.schema.json"


#: One row per closed vocabulary. Adding an enum through either door fails
#: here until it says which readers it reaches and who gives them the word.
VOCABULARIES: dict[str, Vocabulary] = {
    # --- who is being answered, which is not something the answer says ---
    "reader_language": Vocabulary(
        declares="themis.language.Lang",
        off_envelope="A result is the same result whoever reads it, so the "
                     "language is chosen where the sentence is made and never "
                     "travels on the answer. It is a vocabulary anyway because "
                     "it is the denominator of every gloss below: what has to "
                     "exist is a word per member per member of THIS, and a set "
                     "with no name has no members to count.",
        no_gloss="Nobody is shown a language tag. What a reader sees is the "
                 "language itself, and a surface that offers the choice names "
                 "each option in its own spelling rather than in the reader's "
                 "current one.",
    ),
    # --- the assumption ledger: three vocabularies of one line ---------------
    "assumption_layer": Vocabulary(
        declares="themis.ledger.Layer",
        sites=((*_EXT, "assumption_ledger", "properties", "assumptions",
                "items", "properties", "layer"),),
        glossed_by="themis.ledger.layer_word",
    ),
    "assumption_severity": Vocabulary(
        declares="themis.ledger.Severity",
        sites=((*_EXT, "assumption_ledger", "properties", "assumptions",
                "items", "properties", "severity"),),
        glossed_by="themis.ledger.severity_word",
    ),
    "assumption_provenance": Vocabulary(
        # Two containers, and the second was undeclared: a mechanism audit's
        # provenance is the same vocabulary as a ledger line's, which is why
        # the audit's summary could hand-write a second translation of it.
        declares="themis.ledger.Provenance",
        sites=(
            (*_EXT, "assumption_ledger", "properties", "assumptions",
             "items", "properties", "provenance"),
            (*_EXT, "mechanism_audit", "properties", "mechanisms", "items",
             "properties", "assumptions", "items", "properties", "settled_by"),
        ),
        glossed_by="themis.ledger.provenance_word",
    ),
    "interventional_risk_provenance": Vocabulary(
        # Three containers holding three different subsets, because what a
        # cell may declare depends on the rule that wrote it.
        declares="themis.risk_provenance.RiskProvenance",
        sites=(
            (*_EXT, "causation", "properties",
             "interventional_risk_provenance"),
            (*_NE, "counterfactual_cell", "properties",
             "interventional_risk_provenance"),
            (*_NE, "probabilities_of_causation", "properties",
             "interventional_risk_provenance"),
        ),
        glossed_by="themis.risk_provenance.describe",
    ),

    # --- what the report leads with ------------------------------------------
    "result_status": Vocabulary(
        declares="themis.types.ResultStatus",
        sites=((_QR, "properties", "status"),),
        glossed_by=f"{_REPORT}._STATUS_BADGE",
    ),
    "answer_tier": Vocabulary(
        declares="themis.types.AnswerTier",
        sites=((*_DEFS, "dataGapReport", "properties", "answer_tier"),),
        glossed_by=f"{_REPORT}._TIER_WORDS",
    ),
    "gap_severity": Vocabulary(
        declares="themis.types.GapSeverity",
        sites=((*_DEFS, "dataGap", "properties", "severity"),),
        glossed_by=f"{_REPORT}._GAP_SEVERITY_WORDS",
    ),
    "identification_pattern": Vocabulary(
        sites=((*_EXT, "identification", "properties", "pattern"),),
        off_envelope="",
        glossed_by=f"{_REPORT}._PATTERN_WORDS",
    ),
    "bounds_estimand": Vocabulary(
        sites=((*_DEFS, "boundsResult", "properties", "estimand"),),
        glossed_by=f"{_REPORT}._BOUNDS_ESTIMAND_WORDS",
    ),
    "bounds_contrast_kind": Vocabulary(
        sites=((*_DEFS, "boundsResult", "properties", "contrast",
                "properties", "kind"),),
        glossed_by=f"{_REPORT}._BOUNDS_CONTRAST_WORDS",
    ),
    "missing_data_mechanism": Vocabulary(
        sites=((*_EXT, "missing_data_recovery", "properties", "mechanism"),),
        glossed_by=f"{_REPORT}._MECHANISM_WORDS",
    ),
    "refusal_kind": Vocabulary(
        declares="themis.refusals.Kind",
        sites=((_QR, "properties", "estimator_failure", "properties",
                "kind"),),
        glossed_by=f"{_REPORT}._kind_word",
    ),
    "outcome_error_design": Vocabulary(
        declares="themis.estimation.outcome_error.OutcomeErrorDesign",
        sites=((_QR, "properties", "outcome_error", "properties",
                "design_kind"),),
        glossed_by=f"{_REPORT}._OUTCOME_ERROR_DESIGN_WORDS",
    ),
    "investigation_action": Vocabulary(
        declares="themis.types.InvestigationAction",
        sites=((*_DEFS, "investigationRequest", "properties", "action"),),
        glossed_by="themis.output.explainer._ACTION_PHRASE",
    ),
    "priority": Vocabulary(
        declares="themis.types.Priority",
        sites=(
            (*_DEFS, "investigationRequest", "properties", "priority"),
            (*_DEFS, "missingItem", "properties", "priority"),
        ),
        glossed_by="themis.output.explainer._PRIORITY_PHRASE",
    ),

    # --- the vocabularies only the schema stated -----------------------------
    "nde_nie_failed_condition": Vocabulary(
        sites=((*_EXT, "mediation_decomposition", "properties", "nde_nie",
                "properties", "failed_condition"),),
        glossed_by=f"{_GLOSSARY}.nde_nie_condition_word",
    ),
    "cde_failed_condition": Vocabulary(
        sites=((*_EXT, "mediation_decomposition", "properties", "cde",
                "properties", "failed_condition"),),
        glossed_by=f"{_GLOSSARY}.cde_condition_word",
    ),
    "framing_field": Vocabulary(
        sites=((*_DEFS, "framingNote", "properties", "missing", "items"),),
        glossed_by=f"{_GLOSSARY}.framing_field_word",
    ),
    "measurement_scale": Vocabulary(
        # One vocabulary across three containers: what a variable declares,
        # and the two halves of the reconciliation that compares a
        # declaration with its column. A mismatch is read by putting the two
        # side by side, so they have to be in the same words.
        sites=(
            (_KA, "$defs", "variableDeclaration", "properties", "scale"),
            (*_EXT, "type_reconciliation", "properties", "checks", "items",
             "properties", "declared_scale"),
            (*_EXT, "type_reconciliation", "properties", "checks", "items",
             "properties", "observed_scale"),
        ),
        glossed_by=f"{_GLOSSARY}.scale_word",
    ),
    "dtype_kind": Vocabulary(
        sites=((*_EXT, "type_reconciliation", "properties", "checks",
                "items", "properties", "dtype_kind"),),
        no_gloss="The column's storage type, kept so the verifier can "
                 "re-derive the verdict. What the reader is told is the "
                 "check's own `detail`, which states the disagreement in "
                 "words — the scale it names is glossed, this is not.",
    ),
    "reconciliation_verdict": Vocabulary(
        sites=((*_EXT, "type_reconciliation", "properties", "checks",
                "items", "properties", "verdict"),),
        no_gloss="Which way the declaration and the data disagreed. The "
                 "`detail` beside it is that sentence; this is the key the "
                 "gap's severity and blocked output were chosen by.",
    ),

    # --- printed as a handle beside a caption that carries the meaning -------
    #
    # Not an exemption: each names the caption. A handle is legitimate when
    # the reader is meant to see the identifier — to quote it, to look it up,
    # to match it against a method they know — and the sentence beside it
    # says what it is. It stops being legitimate the moment the caption goes.
    "numeric_method": Vocabulary(
        sites=((*_NE, "method"),),
        no_gloss="Printed as `方法 \\`x\\`` under a Chinese caption that "
                 "states what was computed; the reader is meant to see the "
                 "identifier, because it is what names the estimator in the "
                 "literature and in the derivation chain beside it.",
    ),
    "bounds_method": Vocabulary(
        declares="themis.types.BoundsMethod",
        sites=((*_DEFS, "boundsResult", "properties", "method"),),
        no_gloss="Printed beside `靠的假设`, which states what the interval "
                 "rests on — the fact a reader choosing between rows needs. "
                 "The method name is the handle for the one they pick.",
    ),
    "refusal_species": Vocabulary(
        declares="themis.refusals.Refusal",
        sites=((_QR, "properties", "estimator_failure", "properties",
                "failure_type"),),
        no_gloss="Printed as `拒答类型 \\`x\\`` beside the sentence "
                 "``refusal_kind`` glosses, which says what the reader "
                 "should do about it. Sixty-nine species share five kinds, "
                 "and it is the kind that carries the action.",
    ),

    # --- never printed by name ------------------------------------------------
    "gap_kind": Vocabulary(
        declares="themis.types.GapKind",
        sites=((*_DEFS, "dataGap", "properties", "kind"),),
        no_gloss="Every gap carries its own Chinese `description`; the kind "
                 "is the key a reader never meets on this surface. The "
                 "browser titles it (`GAP_TITLE`, pinned) and "
                 "`docs/GAP_KINDS_REFERENCE.md` gives each a row, both "
                 "checked elsewhere.",
    ),
    "gap_blocks": Vocabulary(
        declares="themis.types.GapBlocks",
        sites=((*_DEFS, "dataGap", "properties", "blocks"),),
        no_gloss="Which downstream output a gap prevents. Read by the "
                 "answer-tier computation, never rendered: what the reader "
                 "is told is the tier it produced.",
    ),
    "gap_ref_kind": Vocabulary(
        declares="themis.types.GapRefKind",
        sites=((*_DEFS, "dataGap", "properties", "provenance", "items",
                "properties", "ref_kind"),),
        no_gloss="The audit trail — which channel found the gap. It is for "
                 "whoever re-derives the report, not for the reader of it.",
    ),
    "required_data_type": Vocabulary(
        declares="themis.types.RequiredDataType",
        sites=((*_DEFS, "dataGap", "properties", "required_data",
                "properties", "data_type"),),
        no_gloss="What kind of study would fill the gap. The gap's own "
                 "Chinese sentence says it in words; this is the machine "
                 "copy, and no surface prints it.",
    ),
    "missing_kind": Vocabulary(
        declares="themis.types.MissingKind",
        sites=((*_DEFS, "missingItem", "properties", "kind"),),
        no_gloss="Which channel repairs a missing item. Consumed by the "
                 "investigation-request builder; the reader gets the "
                 "request.",
    ),
    "missing_gap": Vocabulary(
        sites=(
            (*_DEFS, "missingItem", "properties", "gap"),
            (*_DEFS, "investigationItem", "properties", "gap"),
        ),
        no_gloss="The species key `_ITEM_SPECIES` binds one renderer to. "
                 "Every member selects a Chinese sentence, so a member with "
                 "no word is impossible by construction — `bind` refuses a "
                 "set that misses one.",
    ),
    "query_kind": Vocabulary(
        declares="themis.types.QueryKind",
        sites=((_QR, "properties", "query_kind"),),
        no_gloss="Glossed by a sentence rather than a word: `questions.bind` "
                 "fixes one question line and one verdict phrasing per kind "
                 "and refuses a set that misses one. The browser's "
                 "`QUESTION_READINGS` is pinned against the same enum.",
    ),
    "mediation_strategy": Vocabulary(
        sites=((*_EXT, "mediation_decomposition", "properties", "strategy"),),
        no_gloss="Which decomposition survived. The reader is shown the two "
                 "arms themselves — each identifiable or not, and on what — "
                 "so the summary of them is not restated.",
    ),
    "mediation_joint_strategy": Vocabulary(
        sites=((*_EXT, "mediation_joint_decomposition", "properties",
                "strategy"),),
        no_gloss="As `mediation_strategy`, for a mediator set. A separate "
                 "vocabulary because it has a member the single-mediator one "
                 "does not: `nde_nie+cde`, both arms at once.",
    ),
    "joint_identification_pattern": Vocabulary(
        sites=((*_EXT, "joint_identification", "properties", "pattern"),),
        no_gloss="The report names the joint route in its own sentence "
                 "rather than through this key; the key says which of two "
                 "solvers produced it.",
    ),
    "joint_interaction_scale": Vocabulary(
        sites=((*_EXT, "joint_identification", "properties", "interaction"),),
        no_gloss="One member. The scale is stated in the interaction line "
                 "itself (`差值尺度`), because a one-member vocabulary "
                 "printed as a key says nothing a sentence does not.",
    ),
    "selection_criterion": Vocabulary(
        sites=((*_EXT, "selection_recovery", "properties", "criterion"),),
        no_gloss="Which recovery criterion licensed the answer. The route "
                 "renderer states the licence in a sentence; this is the key "
                 "it branched on.",
    ),
    "selection_query_kind": Vocabulary(
        sites=((*_EXT, "selection_recovery", "properties", "query_kind"),),
        no_gloss="Whether the recovered target was a conditional or an "
                 "effect — restated from the query the reader asked, so it "
                 "is a machine cross-check rather than news.",
    ),
    "counterfactual_cell_monotonicity": Vocabulary(
        declares="themis.types.Monotonicity",
        sites=(
            (_KA, "$defs", "effectQuery", "properties", "assumptions",
             "properties", "monotonicity"),
            (_KA, "$defs", "counterfactualQuery", "properties", "assumptions",
             "properties", "monotonicity"),
            (*_NE, "counterfactual_cell", "properties", "monotonicity"),
            ("verification_context.schema.json", "$defs",
             "counterfactual_assumptions", "properties", "monotonicity"),
        ),
        # This row used to carry that sentence as a `no_gloss` reason, and
        # the sentence was false: the ledger line printed the token
        # (`单调性（non_decreasing）`). A reason naming a surface that says a
        # member "in words" is a claim that a per-member mapping exists
        # somewhere — which is what `glossed_by` is. Written as prose it was
        # nobody's to check, and five producers each answered the missing
        # mapping for themselves.
        glossed_by="themis.ledger.monotonicity_word",
    ),
    "estimation_model_preference": Vocabulary(
        sites=((_QR, "properties", "estimation_context", "properties",
                "model_preference"),),
        no_gloss="What the caller asked the estimator to fit. The form it "
                 "actually chose reaches the reader through the mechanism "
                 "audit, which is the load-bearing one.",
    ),
    "ci_method": Vocabulary(
        sites=((*_NE, "ci_method"),),
        no_gloss="How the interval was formed. The interval is rendered; "
                 "which of two routines produced it is not, and a reader who "
                 "wants it reads the derivation chain.",
    ),
    "bootstrap_kind": Vocabulary(
        sites=((*_NE, "bootstrap", "properties", "kind"),),
        no_gloss="Whether resampling was clustered. The cluster disclosure "
                 "is a gap with its own sentence; this is what that gap was "
                 "derived from.",
    ),
    "propensity_model": Vocabulary(
        sites=((*_NE, "propensity_summary", "properties", "model"),),
        no_gloss="Which propensity family was fitted — a diagnostic beside "
                 "the overlap numbers, read by whoever inspects them.",
    ),
    "interaction_scale": Vocabulary(
        sites=((*_NE, "interaction", "properties", "scale"),),
        no_gloss="One member, stated in the interaction line itself.",
    ),
    "measurement_correction_side": Vocabulary(
        sites=(
            (*_NE, "measurement_correction", "properties", "side"),
            (*_NE, "measurement_correction", "properties",
             "sufficient_statistics", "properties", "side"),
        ),
        glossed_by="themis.output.envelope_glossary.measurement_side_word",
    ),
    "four_way_mediator_scale": Vocabulary(
        sites=((*_NE, "four_way_ratio", "properties", "mediator_scale"),),
        glossed_by="themis.output.envelope_glossary.four_way_mediator_scale_word",
    ),
    "sensitivity_conversion_path": Vocabulary(
        sites=((*_NE, "sensitivity_analysis", "properties", "path"),),
        no_gloss="Which ATE-to-risk-ratio conversion ran. Same values as "
                 "`four_way_mediator_scale` and a different question, which "
                 "is why they are two rows.",
    ),
    "evalue_interpretation_band": Vocabulary(
        # The reading a person acts on, which was prose inside ``note`` until
        # nothing could re-derive it and the rule producing it turned out to
        # be keyed to the wrong number.
        sites=((*_NE, "sensitivity_analysis", "properties",
                "interpretation_band"),),
        glossed_by=f"{_GLOSSARY}.evalue_band_word",
    ),
    "evalue_band_basis": Vocabulary(
        # Two members, and registered for the reason a one-member vocabulary
        # is: this pair IS the distinction the defect erased, so a surface
        # that stops stating it stops saying which question was answered.
        sites=((*_NE, "sensitivity_analysis", "properties", "band_basis"),),
        glossed_by=f"{_GLOSSARY}.evalue_band_basis_word",
    ),
    "anderson_rubin_set_kind": Vocabulary(
        # Three containers; the robust one has a member the others cannot
        # produce, so the union is the vocabulary.
        sites=(
            (*_NE, "anderson_rubin_confidence_set", "properties", "kind"),
            (*_NE, "stratified_anderson_rubin_confidence_set", "properties",
             "kind"),
            (*_NE, "robust_anderson_rubin_confidence_set", "properties",
             "kind"),
        ),
        # Was `no_gloss` on the ground that no surface rendered the block at
        # all, which was true and is the reason a word would have been dead.
        # Both surfaces render it now, so the word is what a reader gets.
        glossed_by=f"{_GLOSSARY}.ar_set_kind_word",
    ),
    "gformula_stratum_arm": Vocabulary(
        sites=((*_DEFS, "gformulaFactorStats", "properties",
                "conditional_strata", "items", "properties", "arm"),),
        no_gloss="0 and 1, the two arms of the contrast, inside a "
                 "per-stratum diagnostic. They are the values themselves, "
                 "not names for anything.",
    ),

    # --- the other schemas ----------------------------------------------------
    "term_type": Vocabulary(
        sites=(
            ("derivation.schema.json", "$defs", "term", "properties", "type"),
            ("verification_context.schema.json", "$defs", "term",
             "properties", "type"),
        ),
        no_gloss="Whether a formula term is a constant or a variable. It is "
                 "structure inside a formula, and the formula reaches the "
                 "reader rendered, never as its parse tree.",
    ),
    "theta_provenance": Vocabulary(
        sites=((_KA, "$defs", "probabilityStatement", "properties",
                "provenance"),),
        no_gloss="Where a supplied probability came from, on the way IN. "
                 "What comes back out is the ledger line it produced, and "
                 "`assumption_provenance` is the vocabulary of that.",
    ),
    "ate_estimator_option": Vocabulary(
        sites=((_KA, "properties", "options", "properties", "ate_estimator"),),
        no_gloss="A knob the caller sets. What ran is reported as "
                 "`numeric_method`, which is where a reader looks.",
    ),
    "longitudinal_estimator_option": Vocabulary(
        sites=((_KA, "properties", "options", "properties", "longitudinal",
                "properties", "estimator"),),
        no_gloss="As `ate_estimator_option`, for the time-varying pass.",
    ),
    "kb_query_kind": Vocabulary(
        declares="themis.kb.schemas.KBQueryKind",
        sites=(
            ("kb_query.schema.json", "properties", "query_kind"),
            ("kb_result.schema.json", "$defs", "kbQuery", "properties",
             "query_kind"),
        ),
        no_gloss="What a knowledge-base adapter was asked for. The adapter "
                 "boundary is machine-to-machine; nothing on it reaches a "
                 "person without passing through a result envelope first.",
    ),
    "kb_confidence_grade": Vocabulary(
        declares="themis.kb.schemas.KBConfidenceGrade",
        sites=(("kb_result.schema.json", "$defs", "kbProvenance",
                "properties", "confidence_grade"),),
        no_gloss="How good the adapter thinks its own answer is. Same "
                 "boundary as `kb_query_kind`.",
    ),

    # --- a constraint written in another vocabulary's terms -------------------
    "numeric_method_requiring_a_point": Vocabulary(
        sites=((_QR, "properties", "numeric_estimate", "allOf", "2", "if",
                "properties", "method", "not"),),
        subset_of="numeric_method",
    ),

    # --- declared in Python, never on the envelope ----------------------------
    "extension_block": Vocabulary(
        declares="themis.blocks.Block",
        off_envelope="The one vocabulary the envelope states as KEYS rather "
                     "than as an enum: its members are exactly the property "
                     "names under extensions in query_result.schema.json. "
                     "There is no field to point a site at, and the equality "
                     "a site would assert is asserted directly instead — "
                     "tests/test_blocks_registry.py holds the registry and "
                     "that property set to each other in both directions, "
                     "and themis.blocks.check_registered refuses at the "
                     "kernel's exits to emit a key the registry does not "
                     "declare.",
        no_gloss="A block name is what a renderer is reached BY, not "
                 "something a reader is shown: what arrives is the section "
                 "its renderer writes, under that section's own Chinese "
                 "heading. Which is why the reachability question for these "
                 "is 'does a surface bind one' — asked by themis.blocks.bind "
                 "at import, and of the browser by the same test file.",
    ),
    "block_family": Vocabulary(
        declares="themis.blocks.Family",
        off_envelope="The axis the block registry is grouped ON — which of "
                     "the reader's questions a block answers. It exists so "
                     "that a block reaching nobody cannot look like a block "
                     "reaching somebody, and it is consumed entirely by "
                     "themis.blocks.bind and the surfaces that call it. No "
                     "result carries one.",
        no_gloss="A reader gets the family as the section it produces, not "
                 "as the word: the four `tells` sentences are written for "
                 "whoever adds the next family, and the heading a reader "
                 "sees is the surface's own.",
    ),
    "audit_artifact": Vocabulary(
        declares="themis.audits.Artifact",
        off_envelope="The vocabulary of what an audit is an audit OF, which "
                     "reaches a reader through `themis.audit`'s own output "
                     "rather than through a result envelope. Its members are "
                     "verbatim the `kind` their artifacts carry, and since "
                     "#387 each artifact's own schema states its member — as "
                     "a `const` rather than an `enum`, because a document "
                     "that admitted the whole vocabulary would be a document "
                     "that did not say which artifact it describes. No site "
                     "here for that reason, and none in "
                     "query_result.schema.json either, because an envelope "
                     "does not say what kind of dict it is.",
        no_gloss="An audit's own output names the artifact in its heading; "
                 "the member is the heading.",
    ),
    "strategy_estimand": Vocabulary(
        declares="themis.estimation.strategy.Estimand",
        off_envelope="What a strategy row's number is an estimate of, used "
                     "to decide whether one row may answer another's query. "
                     "It is a fact about the TABLE, not about any one "
                     "result: the envelope says which method ran and what it "
                     "produced, and a reader who wants the estimand reads "
                     "the method. Only `arm_probability` reaches the "
                     "envelope, as bounds_results[].estimand, which is a "
                     "one-member enum with its own anchor in the browser "
                     "pin.",
        no_gloss="Never leaves the cascade.",
    ),
    "strategy_role": Vocabulary(
        declares="themis.estimation.strategy.Role",
        off_envelope="Whether a strategy row claims the answer or annotates "
                     "someone else's. A property of the row, consumed "
                     "entirely inside the cascade; no reader is ever handed "
                     "one.",
        no_gloss="Never leaves the cascade.",
    ),
    "latent_exposure": Vocabulary(
        declares="themis.input.semantic_validator.LatentExposure",
        off_envelope="What an unobserved common cause can do to a query "
                     "kind's answer — the verdict the bidirected gate "
                     "reaches BEFORE anything runs. A program it refuses "
                     "produces a SemanticError and no envelope at all, and a "
                     "program it admits produces an envelope that carries "
                     "the answer rather than the reason it was allowed to be "
                     "computed. There is no field for it because there is no "
                     "result to put one on.",
        no_gloss="The reason travels as the refusal's own sentence, not as "
                 "the member's name: the gate interpolates the row's "
                 "explanation into the message, which is what a reader "
                 "needs. `absorbed` and `consulted` never reach anyone — "
                 "they are what the next person to add a query kind has to "
                 "choose between, and the sentences under them are written "
                 "for that person.",
    ),
    # --- what an interval's width is a fact about, and how tight it is ------
    "interval_width": Vocabulary(
        declares="themis.intervals.Width",
        sites=((*_DEFS, "causationEstimate", "properties", "ci_width_is"),
               (*_NE, "counterfactual_cell", "properties", "ci_width_is")),
        partly_stated="``identification`` classifies a SLOT and can never be "
                      "a value on a row: a ci pair is a confidence statement "
                      "by construction, and the identified interval it is a "
                      "statement ABOUT lives in the row's other pair. The two "
                      "sites here are the two pairs whose kind the RUN "
                      "settles, which is why they carry a field at all; the "
                      "other twenty-four are settled by which slot they are, "
                      "and themis.intervals.DECLARED is where that is "
                      "written. The member reaches a reader through the "
                      "bounds section, which asks the census what the slot "
                      "holds and renders its advice.",
        glossed_by="themis.intervals.width_word",
    ),
    "interval_tightness": Vocabulary(
        declares="themis.intervals.Tightness",
        sites=((*_DEFS, "boundsResult", "properties", "tightness"),
               (*_DEFS, "boundsResult", "properties", "contrast",
                "properties", "tightness")),
        glossed_by="themis.intervals.tightness_word",
    ),
    # --- the five standalone artifacts, whose reader is the auditor ---------
    # These eight were closed vocabularies in the producers all along. Nothing
    # asked them who reads them, because nothing declared the artifacts they
    # sit in — which is #387: being an artifact and having a declared shape
    # were two facts, and five of the six had only the first.
    "markov_blanket_method": Vocabulary(
        sites=((_MB, "properties", "method"),),
        no_gloss="Which search produced the blanket. Its reader is "
                 "`verify_markov_blanket`, which re-runs the search and has "
                 "to know which one it is re-running; a person gets the "
                 "artifact's `note`, which names the algorithm in words.",
    ),
    "markov_blanket_ci_test": Vocabulary(
        sites=((_MB, "properties", "test"),),
        no_gloss="Which conditional-independence test ran, chosen by the data "
                 "type rather than by the caller. It also decides which "
                 "sufficient statistic the artifact records, so its reader is "
                 "whoever redoes the tests from that record. The `note` gives "
                 "a person the test by its published name.",
    ),
    "markov_blanket_test_role": Vocabulary(
        sites=((_MB, "$defs", "fisherZTest", "properties", "role"),
               (_MB, "$defs", "chiSquareTest", "properties", "role"),),
        no_gloss="Which half of the definition a test entry is checking — "
                 "minimality for a member, completeness for a non-member. It "
                 "is also which DIRECTION `passed` compares in, which is why "
                 "it is on the row rather than left to be inferred. Two sites "
                 "because the two test shapes are declared separately so each "
                 "can close itself; one vocabulary, because it is the same "
                 "question either way.",
    ),
    "orientation_conflict_reason": Vocabulary(
        sites=((_OP, "$defs", "conflictReason"),),
        no_gloss="Why an asserted direction, adjacency or absence was refused "
                 "and the data's structure left intact. It reaches a person "
                 "through the question set, which turns each conflict into a "
                 "`prompt` written for whoever has to adjudicate it — the "
                 "member is what the compiler routes on, the prompt is what "
                 "the reader is asked.",
    ),
    "orientation_rule": Vocabulary(
        sites=((_OP, "$defs", "provenanceStep", "properties", "rule"),
               (_OL, "$defs", "ledgerEdge", "properties", "rule"),),
        no_gloss="What forced one orientation: the data, an applied "
                 "constraint, or one of Meek's four rules. Load-bearing "
                 "rather than decorative — the ledger derives an edge's "
                 "source from it, so `collider_input` is what makes an edge "
                 "the data's and everything else makes it somebody's. The "
                 "second site is that derivation echoing the first, and a "
                 "person meets the conclusion (`source`) rather than the rule.",
    ),
    "orientation_question_kind": Vocabulary(
        sites=((_OQ, "$defs", "question", "properties", "kind"),),
        no_gloss="Whether a question asks for a direction or for an "
                 "adjudication. It decides which `detail` shape travels with "
                 "the question and which fields mean anything, and what a "
                 "person is handed is the `prompt` the kind selected.",
    ),
    "orientation_answer_adjacency": Vocabulary(
        sites=((_OS, "$defs", "answer", "properties", "adjacency"),),
        no_gloss="What an answer claims about whether a pair is connected at "
                 "all, when it claims anything. Read by the session's replay "
                 "and never rendered: an answer is something a reader WROTE, "
                 "and what comes back to them is the conflict it raised or "
                 "the constraint it became.",
    ),
    "orientation_session_status": Vocabulary(
        sites=((_OS, "properties", "status"),),
        no_gloss="Whether the session is worth another turn. The distinction "
                 "it exists for is `blocked` against `open`: both leave edges "
                 "undetermined, and only one of them is fixed by asking "
                 "again. A person gets the session's `note`, which says the "
                 "counts and the status in a sentence.",
    ),
    "routing_end": Vocabulary(
        declares="themis.routing.End",
        off_envelope="Which of the two implementations a strategy has — "
                     "identification or numeric. Internal to routing; the "
                     "envelope reports what was derived and what was "
                     "computed, never which end of the table did it.",
        no_gloss="Never leaves the router.",
    ),
}


# --- resolving what a row names ----------------------------------------------

def _resolve(dotted: str):
    """Import ``a.b.c`` and return the attribute, module or not."""
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for attr in parts[cut:]:
            obj = getattr(obj, attr)
        return obj
    raise ImportError(dotted)


def _at(site: Site) -> set[str]:
    node = json.loads((SCHEMAS / site[0]).read_text(encoding="utf-8"))
    for step in site[1:]:
        node = node[int(step)] if isinstance(node, list) else node[step]
    # ``null`` is the absence of a value, not a member of the vocabulary:
    # a mediation arm with no failed condition is an identifiable one.
    return {str(v) for v in node["enum"] if v is not None}


def _members(name: str) -> set[str]:
    row = VOCABULARIES[name]
    if row.declares:
        return {str(m.value) for m in _python_vocabularies()[row.declares]}
    if row.subset_of:
        return set().union(*(_at(s) for s in row.sites))
    return set().union(*(_at(s) for s in row.sites))


#: A tag no build declares, used to ask a gloss what it says when it has
#: nothing to say.
NOTHING = "xx"


def _word_for(glossed_by: str, member: str, lang: str):
    """What a reader of ``lang`` is handed for this member.

    A gloss is either the words themselves — a mapping from member to
    the text in each language — or an accessor over one, and every
    accessor answers the same shape so that this can ask any of them
    the same way, once per language.

    The dotted name rather than the row it sits on, because the second
    caller has no row: ``test_web_vocabularies`` holds the browser's copy
    of each vocabulary to what the kernel hands a reader, and one of the
    vocabularies it asks about is declared by a glossary rather than by a
    schema enum, so it is not registered here at all."""
    gloss = _resolve(glossed_by)
    if isinstance(gloss, dict):
        return language.gloss(gloss, member, lang, unknown="")
    return gloss(member, lang)


# --- the checks ---------------------------------------------------------------

def _unaccounted(declared: set, stated: set, excused: set):
    """The three ways two tables and a package can disagree."""
    return (
        sorted(declared - (stated | excused)),   # said nothing about itself
        sorted((stated | excused) - declared),   # a row for something gone
        sorted(stated & excused),                # said both things
    )


def test_every_python_vocabulary_has_exactly_one_row():
    """Door one. Adding an ``Enum`` fails here until it says who reads it."""
    found = set(_python_vocabularies())
    claimed = [v.declares for v in VOCABULARIES.values() if v.declares]
    assert len(claimed) == len(set(claimed)), (
        f"two rows claim the same enum: "
        f"{sorted({c for c in claimed if claimed.count(c) > 1})}"
    )
    silent, stale, _ = _unaccounted(found, set(claimed), set())
    assert not silent, (
        f"{silent} are closed vocabularies with no row; add one saying which "
        f"schema sites state it and who gives the reader the word"
    )
    assert not stale, f"{stale} are named here and no longer declared"


def test_every_schema_enum_site_has_exactly_one_row():
    """Door two, and the one that was not watched.

    A schema is as much the kernel's declaration as a Python enum is, and
    42 of these sites had no enum behind them — so nothing ever asked them
    who reads them, and three answered "a Chinese sentence, in English".
    """
    found = set(_schema_sites())
    claimed = [s for v in VOCABULARIES.values() for s in v.sites]
    assert len(claimed) == len(set(claimed)), (
        f"two rows claim the same site: "
        f"{sorted({c for c in claimed if claimed.count(c) > 1})}"
    )
    silent, stale, _ = _unaccounted(found, set(claimed), set())
    assert not silent, (
        f"{silent} are enum sites with no row; add one saying which "
        f"vocabulary it states and who gives the reader the word"
    )
    assert not stale, f"{stale} are named here and no schema states them"


def test_a_vocabulary_that_says_nothing_about_itself_is_caught():
    """The counterexample. Without it either partition could hold
    vacuously — an ``accounted`` set built from ``declared`` would pass
    forever."""
    assert _unaccounted({"a", "b"}, {"a"}, set()) == (["b"], [], [])
    assert _unaccounted({"a"}, {"a"}, {"gone"}) == ([], ["gone"], [])
    assert _unaccounted({"a"}, {"a"}, {"a"}) == ([], [], ["a"])


@pytest.mark.parametrize("name", sorted(VOCABULARIES))
def test_every_row_says_both_things_about_itself(name):
    """A row is two answers: where it is declared, and who reads it."""
    row = VOCABULARIES[name]
    if row.subset_of:
        assert row.subset_of in VOCABULARIES, (
            f"{name} names {row.subset_of}, which is not a vocabulary")
        assert row.sites and not row.declares
        return
    assert row.declares or row.sites, (
        f"{name} is declared by neither door and cannot be discovered")
    assert bool(row.sites) != bool(row.off_envelope), (
        f"{name} must either name the schema sites that state it or say why "
        f"the envelope never carries it")
    assert bool(row.glossed_by) != bool(row.no_gloss), (
        f"{name} must either name what gives the reader the word or say why "
        f"no reader needs one")
    assert not row.partly_stated or (row.sites and row.declares), (
        f"{name} says why the sites state a proper subset, and a subset is "
        f"only sayable where both doors are named")


@pytest.mark.parametrize(
    "name", sorted(n for n, v in VOCABULARIES.items() if v.sites and v.declares))
def test_the_declared_sites_state_exactly_the_vocabulary(name):
    """Union over the sites, equal to the members.

    Equality rather than containment, because a value the schema admits and
    the kernel never emits is a case a reader believes was handled.
    """
    row = VOCABULARIES[name]
    stated: set[str] = set()
    for site in row.sites:
        stated |= _at(site)
    members = _members(name)
    assert not stated - members, (
        f"{name}: the schema states {sorted(stated - members)} which the "
        f"kernel does not emit"
    )
    if not row.partly_stated:
        assert stated == members, (
            f"{name}: the schema omits {sorted(members - stated)}; either a "
            f"site is missing or the row has to say why the envelope cannot "
            f"carry them"
        )
        return
    assert members - stated, (
        f"{name} says the sites state a proper subset and they now state all "
        f"of it; delete the sentence rather than leaving it to be believed"
    )


def test_a_partly_stated_row_is_watched_from_both_sides():
    """The relaxation above, shown refusing in both directions.

    A sentence excusing a gap is worth exactly what it costs to keep true,
    so it has to fail when the gap closes as loudly as the rule fails when
    the gap opens. Built out of the real row rather than a fixture: what is
    being checked is that the two branches disagree, and the members of the
    vocabulary are what makes them disagree.
    """
    row = VOCABULARIES["interval_width"]
    stated: set[str] = set()
    for site in row.sites:
        stated |= _at(site)
    members = _members("interval_width")
    assert row.partly_stated, "the row this is built from stopped being one"
    assert stated < members, "the sites caught up; delete the sentence"
    assert not stated - members, "a site admits what the kernel cannot emit"


@pytest.mark.parametrize("name", sorted(n for n, v in VOCABULARIES.items()
                                        if v.subset_of))
def test_a_constraint_site_stays_inside_the_vocabulary_it_constrains(name):
    """A rule written in another vocabulary's terms cannot invent a term."""
    row = VOCABULARIES[name]
    assert _members(name) <= _members(row.subset_of), (
        f"{name} names values {sorted(_members(name) - _members(row.subset_of))} "
        f"that are not in {row.subset_of}"
    )


@pytest.mark.parametrize("lang", sorted(language.written()))
@pytest.mark.parametrize("name", sorted(n for n, v in VOCABULARIES.items()
                                        if v.glossed_by))
def test_the_gloss_answers_for_every_member(name, lang):
    """The check the package did not have.

    Asked once per member, and an answer equal to what the gloss says with
    NO text is not an answer: ``_STATUS_BADGE.get(status, status)`` and the
    backtick fallback in :func:`themis.language.gloss` both hand the
    identifier back, which is what a reader was getting.

    Against the fallback rather than against the member, which is what the
    first version compared. The identifiers here are English words —
    ``blocking``, ``high``, ``continuous`` — so in English the word for a
    member IS its own token often enough that comparing the two would
    report a filled table as empty. The fallback is asked for directly:
    a gloss handed a language it has nothing in says what it says when it
    has nothing to say, and a real text is not that.

    **And once per language this build has words in.** The two are one
    question, because a member with no word in the reader's language and
    a member with no word at all arrive identically: as the identifier.
    The denominator is :func:`themis.language.written` rather than
    :class:`themis.language.Lang`, so a language starts being counted the
    moment somebody starts writing it — the holes are named while they are
    being filled rather than at the end, and nothing has to remember to
    look for them."""
    row = VOCABULARIES[name]
    wordless = []
    for member in sorted(_members(name)):
        word = _word_for(row.glossed_by, member, lang)
        if not word or word == _word_for(row.glossed_by, member, NOTHING):
            wordless.append(member)
    assert not wordless, (
        f"{row.glossed_by} gives {wordless} no {lang} word — a member with "
        f"no word reaches the reader as its own identifier"
    )


def test_a_gloss_missing_a_member_is_caught():
    """The counterexample for the check above, which would otherwise be
    vacuous on any vocabulary whose gloss happens to be total.

    Runs against a real row with a member removed from its mapping, so what
    is exercised is the lookup rather than a hand-written pair.
    """
    row = VOCABULARIES["result_status"]
    members = _members("result_status")
    table = dict(_resolve(row.glossed_by))
    assert all(table.get(m) for m in members)
    dropped = sorted(members)[0]
    table.pop(dropped)
    assert not table.get(dropped)


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_a_member_with_no_word_in_one_language_is_caught(lang):
    """The other half, which the check above cannot see.

    A member present in the table with a word in one language and none in
    another is what a half-finished translation looks like, and the reader
    of the other language gets the identifier. Same lookup, one language
    key removed from a real row.
    """
    row = VOCABULARIES["result_status"]
    member = sorted(_members("result_status"))[0]
    table = dict(_resolve(row.glossed_by))
    assert language.gloss(table, member, lang, unknown="")
    table[member] = {k: v for k, v in table[member].items() if k != lang}
    assert not language.gloss(table, member, lang, unknown="")


# --- the prose surfaces -------------------------------------------------------
#
# A prompt or a reference table has no structure to compare against, so what
# can be asked of it is that it names each member. Backticked, which is how
# all three cite one, and which is what separates naming the kind from
# happening to use the words in a sentence.

#: A derived set, not a whole vocabulary: what has to reach a surface is
#: sometimes a subset, and the subset has to be a declared one. A list
#: written out by hand in the test is drawn from what the surface already
#: says, so it holds the surface against itself — which is how the group
#: below lost two of its six members and nothing failed.
SUBSETS = {
    "themis.types.MIRRORED_INTO_EXPLANATION",
    "themis.types.REACHES_EXPLANATION",
}

#: (what must be named, why this surface needs it, the surfaces).
NAMED_IN_PROSE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "gap_kind",
        "every gap kind has a row a person can read",
        ("docs/GAP_KINDS_REFERENCE.md",),
    ),
    (
        "nde_nie_failed_condition",
        "the renderer is told to explain the condition and had no source "
        "for one, so it improvised — and the one gloss the prompt did "
        "carry named the wrong condition for the intermediate confounder",
        ("themis/prompts/response_rendering.md",),
    ),
    (
        "cde_failed_condition",
        "as its twin: a label the reader cannot act on until someone says "
        "which path it means",
        ("themis/prompts/response_rendering.md",),
    ),
    (
        "themis.types.MIRRORED_INTO_EXPLANATION",
        "the renderer has to know which caveats are already prepended to "
        "explanation, or it says them a second time",
        ("themis/prompts/response_rendering.md",),
    ),
    (
        "themis.types.REACHES_EXPLANATION",
        "the orchestrator pre-screens every kind that reaches explanation, "
        "and one with no rule is one it has to improvise about — mirrored "
        "or estimator-time makes no difference from there",
        ("themis/prompts/gap_to_action.md",),
    ),
)


def _prose_members(name: str) -> set[str]:
    if name in SUBSETS:
        import themis.types
        return {k.value for k in getattr(themis.types, name.rsplit(".", 1)[1])}
    return _members(name)


@pytest.mark.parametrize(
    "name,why,surface",
    [(n, w, s) for n, w, files in NAMED_IN_PROSE for s in files],
)
def test_the_prose_surface_names_every_member(name, why, surface):
    """Backticked containment — the whole of what prose admits being asked."""
    text = (REPO / surface).read_text(encoding="utf-8")
    missing = sorted(m for m in _prose_members(name) if f"`{m}`" not in text)
    assert not missing, f"{surface} does not name {missing} — {why}"


def test_a_vocabulary_the_schema_states_incompletely_is_caught():
    """The counterexample for the union check, without which it could be
    vacuous.

    Reads a real site and drops a member from the comparison, so what is
    exercised is the equality itself rather than a hand-written pair.
    """
    site = VOCABULARIES["gap_severity"].sites[0]
    stated = _at(site)
    assert stated == _members("gap_severity")
    assert (stated - {next(iter(stated))}) != _members("gap_severity")
