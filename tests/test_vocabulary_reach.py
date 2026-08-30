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

import dataclasses
import enum
import importlib
import json
import pathlib
import pkgutil
from dataclasses import dataclass, field

import pytest
from themis import language
from themis.output import reader_words

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

    tabled: str = ""
    """Dotted name of the token-to-words table that states it, if one does.

    The third door, and the one a vocabulary uses when its tokens are not
    this codebase's names: the assumption ids estimators declare are already
    named, so a member per row would be a second spelling of each of them
    that nothing would reference. The table is then the declaration, and
    the words are on it rather than beside it — which is the same rule
    :class:`themis.language.Word` follows, with the mapping in the other
    place.
    """

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

    Filled in from :data:`themis.output.reader_words.GLOSSED` rather than
    written on the row: which accessor hands a reader a word is the
    package's answer, not this module's claim about it, and the browser's
    tables are generated from that same registry. A row states the claim —
    that some reader gets a word at all — by having an entry there.

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
_LD = "lagged_discovery.schema.json"
_OP = "orientation_propagation.schema.json"
_OQ = "orientation_question_set.schema.json"
_OS = "orientation_session.schema.json"
_OL = "orientation_ledger_export.schema.json"


#: One row per closed vocabulary. Adding an enum through either door fails
#: here until it says which readers it reaches and who gives them the word.
_ROWS: dict[str, Vocabulary] = {
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
    ),
    "assumption_severity": Vocabulary(
        declares="themis.ledger.Severity",
        sites=((*_EXT, "assumption_ledger", "properties", "assumptions",
                "items", "properties", "severity"),),
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
    ),

    # --- what the report leads with ------------------------------------------
    "result_status": Vocabulary(
        declares="themis.types.ResultStatus",
        sites=((_QR, "properties", "status"),),
    ),
    "answer_tier": Vocabulary(
        declares="themis.types.AnswerTier",
        sites=((*_DEFS, "dataGapReport", "properties", "answer_tier"),),
    ),
    "gap_severity": Vocabulary(
        declares="themis.types.GapSeverity",
        sites=((*_DEFS, "dataGap", "properties", "severity"),),
    ),
    "identification_pattern": Vocabulary(
        sites=((*_EXT, "identification", "properties", "pattern"),),
        off_envelope="",
    ),
    "feedback_reduction": Vocabulary(
        sites=((*_EXT, "feedback_loop", "properties", "reduction"),),
        no_gloss="Which algebra rescued a declared loop, and there is only "
                 "one: two simultaneous equations reduce to a Wald ratio "
                 "when the loop is exactly between the treatment and the "
                 "outcome. The token reaches no reader because its two "
                 "states are not two words but two situations — present, "
                 "and the route block says the adjustment set was withdrawn "
                 "and an instrument used in its place; absent, and there is "
                 "no answer to caption at all, only the gap saying the loop "
                 "reaches this estimand from somewhere the two-equation "
                 "algebra does not reach.",
    ),
    "malformed_program": Vocabulary(
        declares="themis.input.semantic_validator.Malformed",
        off_envelope="Why a program cannot be run at all. The one "
                     "vocabulary here that no result contract states, and "
                     "for the strongest reason any of them has: a program "
                     "refused at this door produces a SemanticError and no "
                     "envelope at all. Its reader is the failure body the "
                     "web returns, whose `words` carry the species' "
                     "sentence and whose `slots` carry the occasion — the "
                     "same shape an estimator's refusal takes one layer "
                     "down, where there IS a result to put it on.",
    ),
    "proximal_criterion_failure": Vocabulary(
        declares="themis.runtime.proximal_identify.Criterion",
        off_envelope="Which precondition of Miao model (f) the declared "
                     "variables broke, and the sentence that says so. It "
                     "reaches the envelope as a STATEMENT rather than as a "
                     "value on a row — inside `missing_information[].words."
                     "detail` when identification refused, and inside "
                     "`estimator_failure.words.detail` when the estimator "
                     "did — so there is no slot for a schema to state it "
                     "at. The two frames around it are the two channels' "
                     "own, and the diagnosis is the same statement in both.",
    ),
    "proximal_role": Vocabulary(
        declares="themis.runtime.proximal_identify.Role",
        off_envelope="Which of the five parts of model (f) a variable was "
                     "declared to play. One rung further in than the row "
                     "above: it fills a hole in that sentence, so it "
                     "travels inside a statement that is itself inside a "
                     "hole. While it was the key of the dict the message "
                     "read, a reader met `treatment_proxy` mid-clause.",
    ),
    "proximal_data_condition": Vocabulary(
        # Stated by the schema, unlike its two siblings above: this one IS
        # a value on a row — the estimand block lists which conditions the
        # graph left for the data — and a list of tokens is a slot a
        # contract can name.
        sites=((*_EXT, "proximal_estimand", "properties", "data_conditions",
                "items"),),
        declares="themis.runtime.proximal_identify.DataCondition",
    ),
    "proximal_channel_kind": Vocabulary(
        sites=((*_EXT, "proximal_estimand", "properties", "channel_kind"),),
        no_gloss="Which of the two proximal regimes ran. No word, because "
                 "the two members are not two labels for one slot: each "
                 "selects a different sentence about a different object — "
                 "how many states the unmeasured confounder was assumed to "
                 "have, or what function class the bridge was assumed to "
                 "lie in and who chose the penalty that made it solvable. A "
                 "reader who saw the token instead would be handed the name "
                 "of a branch in place of what the branch says.",
    ),
    "basis_family": Vocabulary(
        # Two containers holding the same members, which is the shape a
        # caller's declaration takes when it is echoed back: the query
        # states the family and the estimand block restates what ran. Both
        # sit one level deeper than they used to — a family belongs to a
        # FACTOR now, because a design over several variables has one for
        # each and a family named beside the design belongs to none of them.
        declares="themis.types.BasisFamily",
        sites=((_KA, "$defs", "sieveTerms", "items", "properties", "factors",
                "items", "properties", "basis"),
               (*_DEFS, "sieveDesign", "items", "items", "properties",
                "basis")),
    ),
    "proximal_estimator": Vocabulary(
        # Which of the three answers two bridges support is the answer. The
        # reader's word for it is a SENTENCE and not a noun, because the
        # members differ in what has to be true rather than in what ran, and
        # a reader handed "doubly robust" has been handed the name of a
        # theorem they were not told the content of.
        declares="themis.types.ProximalEstimator",
        sites=((_KA, "$defs", "bridgeChannel", "properties", "estimator"),
               (*_EXT, "proximal_estimand", "properties", "estimator")),
        glossed_by=f"{_REPORT}._ESTIMATOR_WORDS",
    ),
    "bounds_estimand": Vocabulary(
        sites=((*_DEFS, "boundsResult", "properties", "estimand"),),
    ),
    "bounds_contrast_kind": Vocabulary(
        sites=((*_DEFS, "boundsResult", "properties", "contrast",
                "properties", "kind"),),
    ),
    "missing_data_mechanism": Vocabulary(
        sites=((*_EXT, "missing_data_recovery", "properties", "mechanism"),),
    ),
    "refusal_kind": Vocabulary(
        declares="themis.refusals.Kind",
        sites=((_QR, "properties", "estimator_failure", "properties",
                "kind"),),
    ),
    "outcome_error_design": Vocabulary(
        declares="themis.estimation.outcome_error.OutcomeErrorDesign",
        sites=((_QR, "properties", "outcome_error", "properties",
                "design_kind"),),
    ),
    "investigation_action": Vocabulary(
        declares="themis.types.InvestigationAction",
        sites=((*_DEFS, "investigationRequest", "properties", "action"),),
    ),
    "priority": Vocabulary(
        declares="themis.types.Priority",
        sites=(
            (*_DEFS, "investigationRequest", "properties", "priority"),
            (*_DEFS, "missingItem", "properties", "priority"),
        ),
    ),

    # --- the vocabularies only the schema stated -----------------------------
    "nde_nie_failed_condition": Vocabulary(
        sites=((*_EXT, "mediation_decomposition", "properties", "nde_nie",
                "properties", "failed_condition"),),
    ),
    "cde_failed_condition": Vocabulary(
        sites=((*_EXT, "mediation_decomposition", "properties", "cde",
                "properties", "failed_condition"),),
    ),
    "framing_field": Vocabulary(
        # One vocabulary across two containers, and the two halves of one
        # question: which of a variable's framing fields nobody has answered,
        # and which of them were answered by taking the standard reading.
        # A reader comparing the two lists is comparing the same names.
        sites=(
            (*_DEFS, "framingNote", "properties", "missing", "items"),
            (_KA, "$defs", "variableDeclaration", "properties", "defaulted",
             "items"),
        ),
    ),
    "measurement_scale": Vocabulary(
        # Declared in Python since #438, because the scale is also read
        # INSIDE a sentence — the route that says which of the declaration
        # and the column to fix names it mid-clause — and a hole that can
        # only carry a rendered value puts one language's adjective into the
        # other language's sentence.
        declares="themis.output.envelope_glossary.Scale",
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

    "need": Vocabulary(
        declares="themis.gaps.Need",
        sites=((*_DEFS, "need"),),
        no_gloss="The other channel's species, and the same arrangement: "
                 "the token is the developer's handle and what a reader "
                 "gets is the sentence beside it in `themis.gaps.SAYS`, "
                 "assembled where the reader's language is known. One site "
                 "because the four places that carry a shortfall — a "
                 "missing item, an investigation item, a request's note, a "
                 "mediation arm's status — all point at the one definition "
                 "rather than restating the enum.",
    ),
    "text": Vocabulary(
        declares="themis.language.Text",
        off_envelope="Whose words a slot holds — which is a fact about the "
                     "SLOT and not about any one answer, so it is written "
                     "into the schemas beside the slot (`x-text`) rather "
                     "than into a result. It is the only vocabulary here "
                     "whose sites are schema keywords instead of schema "
                     "enums, which is why neither door below reaches it: "
                     "an `enum` says what a value may be, and this says "
                     "what the slot IS.",
        no_gloss="Nobody is ever handed a member. What it decides is "
                 "whether the text in that slot is translated at all, "
                 "and a reader who sees the outcome of that decision "
                 "does not see the decision.",
    ),
    "gap_describes": Vocabulary(
        declares="themis.gaps.Sentence",
        sites=((*_DEFS, "sentence"),),
        # Glossed for the same reason `gap_route` is, one channel further
        # in: what a gap says about itself IS the sentence in
        # `themis.gaps.DESCRIBES`, and the token settles which statement
        # this is — the question two passes used to answer by searching the
        # assembled paragraph for a substring, and one of them in the
        # browser, where the substring was Chinese.
    ),
    "unnamed_thing": Vocabulary(
        declares="themis.gaps.Unnamed",
        off_envelope="What stands in a statement's slot where the occasion "
                     "has no name for the thing. It rides on a statement's "
                     "`words`, as the set and the token, for the reason "
                     "`query_part` rides on a shortfall's: the occasion has "
                     "no VALUE for that hole, and the placeholder is the "
                     "sentence's own way of saying so — which makes it a "
                     "word and not a value.",
    ),
    "gap_route": Vocabulary(
        declares="themis.gaps.Route",
        sites=((*_DEFS, "route"),),
        # Glossed, and for the reason `gap_sentence` is: the browser does
        # not print the token beside anything, it assembles the sentence out
        # of `themis.gaps.ROUTES`. What the token settles is WHICH way past
        # a gap this is — the question three kernel passes used to answer by
        # searching the rendered sentence for three substrings (#438).
    ),
    "query_part": Vocabulary(
        declares="themis.gaps.QueryPart",
        off_envelope="Which part of a program named an atom the graph does "
                     "not have. It rides on `missing_information[].words`, "
                     "as the set and the token, for the reason `query_role` "
                     "rides on a refusal's — a slot inside a sentence is "
                     "not a field, and the surface that knows who is "
                     "reading looks it up.",
    ),

    # --- never printed by name ------------------------------------------------
    "gap_kind": Vocabulary(
        declares="themis.types.GapKind",
        sites=((*_DEFS, "dataGap", "properties", "kind"),),
        no_gloss="Every gap carries the statements it is made of, each "
                 "glossed from `gap_describes`; the kind is the key a "
                 "reader never meets on this surface. The "
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
    "sample_size_family": Vocabulary(
        declares="themis.output.sample_size.Measured",
        off_envelope="Which family of sample-size formula a missing "
                     "distribution falls to, decided from the statement the "
                     "ask filed with the gap. What the envelope carries is "
                     "the answer — `min_sample_size` and the "
                     "`precision_target` that names the assumptions behind "
                     "it — never which branch produced it. It is a "
                     "vocabulary rather than a pair of booleans because the "
                     "third case is real: a value that is neither a truth "
                     "value nor a number is one nothing here sizes, and two "
                     "flags would let a caller say it is both.",
        no_gloss="Nobody is shown it. It is also deliberately not spelled "
                 "in `measurement_scale`'s words: a five-point rating "
                 "answers a mean formula while being discrete, so borrowing "
                 "that vocabulary would put a false word about the variable "
                 "next to a right answer about the arithmetic.",
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
    "monotonicity": Vocabulary(
        declares="themis.ledger.Monotonicity",
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
    # One site, because the block became one shape the moment a second
    # place carried it — the margin table's own loop, the ratio split's,
    # a bounds row's outer band — and a vocabulary listing four copies of
    # a $ref would be describing the reference rather than the shape.
    "bootstrap_kind": Vocabulary(
        sites=(("query_result.schema.json", "$defs", "bootstrapDraws",
                "properties", "kind"),),
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
    "interaction_unavailable_kind": Vocabulary(
        # Which way the K-way interaction went missing, on a slot the
        # contrast beside it survives. Two members and a word for each,
        # because they differ in what a reader can DO: a corner with no rows
        # is a fact about this dataset, and an order past the enumeration
        # cap is a fact about this program.
        sites=((*_NE, "interaction_unavailable", "properties", "kind"),),
    ),
    "transport_blocked_kind": Vocabulary(
        # Why this one source domain's effect does not reach the target,
        # on a block whose other domains may be transporting fine. Two
        # members and a word for each, because they differ in what a reader
        # can do: a diagram missing the treatment or the outcome is a fact
        # about how that domain was declared, and no S-admissible set is a
        # fact about what it would take to even the two populations out.
        sites=((*_EXT, "transport_identification", "properties", "sources",
                "items", "properties", "blocked_by"),),
    ),
    "measurement_correction_side": Vocabulary(
        sites=(
            (*_NE, "measurement_correction", "properties", "side"),
            (*_NE, "measurement_correction", "properties",
             "sufficient_statistics", "properties", "side"),
        ),
    ),
    "four_way_mediator_scale": Vocabulary(
        sites=((*_NE, "four_way_ratio", "properties", "mediator_scale"),),
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
    ),
    "evalue_band_basis": Vocabulary(
        # Two members, and registered for the reason a one-member vocabulary
        # is: this pair IS the distinction the defect erased, so a surface
        # that stops stating it stops saying which question was answered.
        sites=((*_NE, "sensitivity_analysis", "properties", "band_basis"),),
    ),
    "anderson_rubin_set_kind": Vocabulary(
        # Four containers; the robust one has a member the others cannot
        # produce, so the union is the vocabulary. The fourth is a COORDINATE
        # of a k-dimensional region: projecting the region onto one
        # coefficient gives a set on a line, and a set on a line has these
        # six shapes whichever solver produced it.
        sites=(
            (*_NE, "anderson_rubin_confidence_set", "properties", "kind"),
            (*_NE, "stratified_anderson_rubin_confidence_set", "properties",
             "kind"),
            (*_NE, "robust_anderson_rubin_confidence_set", "properties",
             "kind"),
            (*_EXT, "anderson_rubin_region", "properties", "region",
             "properties", "projections", "items", "properties", "kind"),
        ),
        # Was `no_gloss` on the ground that no surface rendered the block at
        # all, which was true and is the reason a word would have been dead.
        # Both surfaces render it now, so the word is what a reader gets.
    ),
    "anderson_rubin_region_shape": Vocabulary(
        # And what the region says about the vector as a WHOLE, which the six
        # above cannot say: a region can be unbounded along one direction
        # while each coordinate projects onto something finite along another,
        # so "bounded" is a different claim here and gets a vocabulary of its
        # own rather than a fifth site on the row above.
        sites=((*_EXT, "anderson_rubin_region", "properties", "region",
                "properties", "shape"),),
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
        # One site: a verification context borrows the term shape rather than
        # restating it, so there is one place this vocabulary is declared.
        sites=(("derivation.schema.json", "$defs", "term", "properties",
                "type"),),
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
        # One site, because there is one record of the query shape: a result
        # references kb_query.schema.json rather than restating it. The second
        # site this used to name was the copy that had already drifted.
        sites=(("kb_query.schema.json", "properties", "query_kind"),),
        no_gloss="What a knowledge-base adapter was asked for. The adapter "
                 "boundary is machine-to-machine; nothing on it reaches a "
                 "person without passing through a result envelope first.",
    ),
    "remedy": Vocabulary(
        # The gloss names the route with its object left open, because that
        # is what the member means on its own; the occasion's own sentence
        # is `themis.refusals.route`, which needs the occasion to make one.
        declares="themis.refusals.Remedy",
        sites=((_QR, "$defs", "remedy", "properties", "remedy"),),
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
    ),
    "interval_tightness": Vocabulary(
        declares="themis.intervals.Tightness",
        sites=((*_DEFS, "boundsResult", "properties", "tightness"),
               (*_DEFS, "boundsResult", "properties", "contrast",
                "properties", "tightness")),
    ),
    # --- a vocabulary that is read INSIDE a sentence ------------------------
    "singular_matrix": Vocabulary(
        declares="themis.refusals.Design",
        off_envelope="Which matrix a fit could not invert. It travels on "
                     "`estimator_failure.details`, which the schema types "
                     "`object` and names no key of — the occasion's own "
                     "facts, whose shape is the raise site's. So no enum "
                     "site states it, and the reason is the same one that "
                     "keeps `details` open: a species' facts are not a "
                     "vocabulary the envelope closes.",
    ),
    "bridge_side": Vocabulary(
        declares="themis.refusals.BridgeSide",
        off_envelope="Which of a bridge's two declared designs a refusal is "
                     "about — the span the bridge is searched for in, or the "
                     "moments it is asked to hold along. It rides on "
                     "`estimator_failure.details` beside `singular_matrix` "
                     "and for the same reason: the occasion's facts are the "
                     "raise site's shape, and the schema types `details` "
                     "`object` and names no key of it. The reader gets the "
                     "word through the refusal's own sentence, which cannot "
                     "be acted on without it — the two sides are written in "
                     "different fields of the query, so 'the design does not "
                     "mention the treatment' names no field until this does.",
    ),
    "outcome_error_premise": Vocabulary(
        declares="themis.estimation.outcome_error.Premise",
        off_envelope="Why one optional argument of an outcome-error design "
                     "exists — the premise the design would rest on if it "
                     "were given. It rides on `estimator_failure.details` "
                     "like `query_role` does, and for the same reason: the "
                     "refusal that names the missing argument has to say "
                     "what the caller would be assuming, and `details` is "
                     "typed as an open object with no named key.",
    ),
    "e_value_undefined": Vocabulary(
        declares="themis.estimation.sensitivity.Undefined",
        off_envelope="Why no E-value came out. The token DOES reach the "
                     "envelope — `sensitivity_analysis.undefined_because` — "
                     "but through the generic statement carrier, which types "
                     "its `token` as a string because the carrier is one "
                     "shape over every vocabulary and a schema cannot enumerate "
                     "a set it does not know. What closes the set is the "
                     "`vocabulary` beside it, which names this one, and this "
                     "row is what holds the two ends together.",
    ),
    "precision_target": Vocabulary(
        declares="themis.output.sample_size.Precision",
        off_envelope="What a sample of `required_data.min_sample_size` "
                     "would buy. The token reaches the envelope through the "
                     "statement carrier, whose `token` the schema types as "
                     "a string because the carrier is one shape over every "
                     "vocabulary; the `vocabulary` beside it closes the set "
                     "and this row holds the two ends together.",
    ),
    "time_window": Vocabulary(
        declares="themis.output.data_gap_report.Window",
        off_envelope="When the measurements a gap asks for would have to be "
                     "taken. Through the carrier, like the row above. Not "
                     "to be confused with the FRAMING field of the same "
                     "name on a variable declaration, which is the caller's "
                     "own text and is not a vocabulary at all.",
    ),
    "sutva_concern": Vocabulary(
        declares="themis.output.data_gap_report.Sutva",
        off_envelope="How a study design could break SUTVA. Through the "
                     "carrier, and as a LIST of them, since a design breaks "
                     "it in more than one way at once.",
    ),
    # The line a ledger entry shows, from the three channels that write it.
    # The glossary's table is the odd one: its tokens are the assumption ids
    # estimators declare, so there is no Python enum to declare them and the
    # table itself is the declaration.
    "assumption_claim": Vocabulary(
        tabled="themis.output.assumption_glossary.CLAIMS",
        off_envelope="What a ledger line says the answer rests on. Through "
                     "the statement carrier, and the one vocabulary here "
                     "with no Python enum to declare it: its tokens are the "
                     "assumption ids estimators write, so a member per row "
                     "would be a second spelling of each id that nothing "
                     "would reference. The table is the declaration.",
    ),
    # The three a simulation-extrapolation estimate puts in front of a
    # reader. Anchored on the schema rather than on their tables, which is
    # the opposite of the two rows below and for the reason the rule gives:
    # these ARE enum sites, so the envelope is what a browser is handed.
    "simex_outcome_model": Vocabulary(
        sites=((*_NE, "simex", "properties", "outcome_model"),),
    ),
    "simex_extrapolant": Vocabulary(
        sites=((*_NE, "simex", "properties", "extrapolant"),),
    ),
    "simex_no_interval": Vocabulary(
        sites=((*_NE, "simex", "properties", "no_interval_because"),),
    ),
    "discovery_note": Vocabulary(
        tabled="themis.estimation.discovery_words.NOTES",
        off_envelope="What a discovery run says about itself — what it "
                     "found, what the algorithm is, which precondition the "
                     "data broke, why the selector chose what it chose. "
                     "Through the statement carrier, on a kernel_ast's "
                     "`discovery_metadata` and on a `notears_fit` artifact, "
                     "neither of which enumerates the tokens: a statement's "
                     "token is a free string for the reason the assumption "
                     "ids above are. The second vocabulary with no Python "
                     "enum, and here the reason is not that the tokens are "
                     "somebody else's but that they are sentences — a "
                     "member per sentence would be a name nothing but the "
                     "table would ever reference.",
    ),
    "theta_prior_claim": Vocabulary(
        declares="themis.output.result_orchestrator.Prior",
        off_envelope="A number the language model supplied, as the ledger "
                     "line it becomes. Through the carrier, into the same "
                     "field as the row above — which is what a statement "
                     "carrying its own vocabulary is for: one field, three "
                     "authors, and no author having to know the others.",
    ),
    "bounds_note": Vocabulary(
        declares="themis.output.bounds.Note",
        off_envelope="What is true of a symbolic interval that no other "
                     "field on its row carries — its width, the size of the "
                     "response-function partition, which end an assumption "
                     "moved, or that a sharper method existed and was "
                     "declined on size. Through the statement carrier, and "
                     "as a LIST: a fourth author appends to it rather than "
                     "gluing a second sentence onto the first.",
    ),
    "observable_required": Vocabulary(
        declares="themis.output.bounds.Observable",
        off_envelope="One distribution a client must supply to evaluate the "
                     "expressions, and how many cells its table has. Through "
                     "the carrier, like the row above; the second half used "
                     "to be glued onto the formula with a `#`.",
    ),
    "selection_recovery_shortfall": Vocabulary(
        declares="themis.runtime.selection_recovery.Shortfall",
        off_envelope="Which condition a selection-recovery verdict came "
                     "back empty on. Its counterpart on the same row is "
                     "`criterion`, which names the theorem that carried a "
                     "POSITIVE verdict and is null on every negative — so "
                     "the row could say what worked and not what did not, "
                     "and the whole of a negative was one free-text field.",
    ),
    "unbiased_distribution": Vocabulary(
        declares="themis.runtime.selection_recovery.External",
        off_envelope="What a sample selection did not touch would have to "
                     "carry. The expression beside it is symbolic and reads "
                     "the same to everyone; the role in front of it is the "
                     "reader's, and the two used to be one string with the "
                     "English glued on the front.",
    ),
    "missing_data_shortfall": Vocabulary(
        declares="themis.runtime.missing_data.Shortfall",
        off_envelope="Which factor a missing-data verdict came back not "
                     "recoverable on. Twin of the selection one; the "
                     "estimand's member holds a LIST of the others in one "
                     "hole, because a product is blocked by whichever of "
                     "its factors failed and the seam between them belongs "
                     "to whoever is reading.",
    ),
    "recovery_factor": Vocabulary(
        declares="themis.runtime.missing_data.Factor",
        off_envelope="Which factor of the interventional estimand this is, "
                     "around the target carried on the row it came from. "
                     "Two hardcoded strings used to say it, with a literal "
                     "`P(Y|X,Z)` in them rather than those targets — a "
                     "second record that had already drifted from the first.",
    ),
    "bound_side": Vocabulary(
        declares="themis.output.bounds.Side",
        off_envelope="Which end of an interval an assumption moved. One "
                     "level further in than the two above: it sits in a HOLE "
                     "of a bounds note, and a hole is typed as the statement "
                     "shape rather than as any one vocabulary, because a "
                     "hole is free to name any set and the `vocabulary` "
                     "beside the token is what closes it.",
    ),
    "measurement_note": Vocabulary(
        declares="themis.output.data_gap_report.Measurement",
        off_envelope="What one variable's declaration says about how it was "
                     "measured. The token reaches the envelope one level "
                     "further in than the carrier above: it sits in a HOLE of "
                     "a gap's own sentence, and a hole is typed as the "
                     "statement shape rather than as any one vocabulary, for "
                     "the same reason — a hole is free to name any set, and "
                     "the `vocabulary` beside the token is what closes it.",
    ),
    "query_role": Vocabulary(
        declares="themis.refusals.QueryRole",
        off_envelope="Which variable of the query a sentence is about. It "
                     "rides on `estimator_failure.details` for the same "
                     "reason `singular_matrix` does, and reaches a second "
                     "reader through the gap report's own prose, which is "
                     "rendered text and not an envelope path either.",
    ),
    "recovery_mechanism": Vocabulary(
        declares="themis.refusals.Recovery",
        off_envelope="Which mechanism an estimand was asked to be recovered "
                     "from — a declared missingness pattern or a declared "
                     "selection. It rides on `estimator_failure.details` for "
                     "the same reason the two above it do. The mechanism IS "
                     "stated on the envelope elsewhere, on each recovery "
                     "block's own `mechanism` field; this vocabulary is the "
                     "word a sentence about the refusal needs, and a member "
                     "names the criterion beside the mechanism, which no "
                     "block field does.",
    ),
    "monotonicity_refutation": Vocabulary(
        declares="themis.refusals.Refutation",
        off_envelope="Which evidence refuted a declared monotonicity. Two "
                     "routes reach the same finding — a response-type "
                     "polytope over an instrument's table, and a "
                     "counterfactual cell whose feasible set the joint and "
                     "the do-risk empty out — and they differ in the "
                     "evidence rather than in the conclusion or what to do "
                     "about it, so the word is a slot of one species' "
                     "sentence rather than a second species. It rides on "
                     "`estimator_failure.details`, like the two above it, "
                     "and for the same reason: a reader told an assumption "
                     "is refuted and not told what refuted it cannot check "
                     "the decision.",
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
    "lagged_discovery_method": Vocabulary(
        sites=((_LD, "properties", "method"),),
        no_gloss="Which two-stage procedure produced the lagged graph. Its "
                 "reader is `verify_lagged_discovery`, which holds the result "
                 "to the property the condition-selection step is supposed to "
                 "reach — and PC1 and a grow-shrink fixpoint reach different "
                 "ones, so an audit that did not know which it was auditing "
                 "would be checking the wrong claim. A person gets the "
                 "artifact's `note`, which names the method and its paper.",
    ),
    "lagged_discovery_ci_test": Vocabulary(
        sites=((_LD, "properties", "test"),),
        no_gloss="Which conditional-independence test ran, and therefore "
                 "which sufficient statistic the artifact records — one "
                 "decision, so one word. Its reader is whoever redoes the "
                 "tests from that record; the `note` gives a person the test "
                 "by its published name.",
    ),
    "lagged_discovery_parent_role": Vocabulary(
        sites=((_LD, "$defs", "parentTest", "properties", "role"),),
        no_gloss="Which half of the fixpoint a test entry is checking — a "
                 "parent must be dependent given the OTHER parents, a "
                 "non-parent independent given ALL of them. It is also which "
                 "direction `passed` compares in, which is why it is on the "
                 "row rather than left to be inferred.",
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
                 "person is handed is the sentence `asks` names.",
    ),
    "orientation_asks": Vocabulary(
        declares="themis.estimation.orientation_questions.Asks",
        off_envelope="What the session is putting to a person. It rides on "
                     "`questions[].asks` as the set and the token, which is "
                     "what a statement is — the artifact carries which "
                     "question and this occasion's names for its holes, and "
                     "the surface that knows who is reading makes the "
                     "sentence. It carried the assembled sentence before "
                     "#467, in one language, because the field was typed "
                     "`string` and a string has nowhere to put a second.",
    ),
    "orientation_question_set_says": Vocabulary(
        declares="themis.estimation.orientation_questions.Says",
        off_envelope="What the compiled set says about itself, on `says`, "
                     "the same way and for the same reason. One member: the "
                     "counts and the top leverage, which the fields beside "
                     "it already carry — so what this adds is a sentence "
                     "about them rather than a fact, and it is here rather "
                     "than written at the producer because the producer "
                     "does not know who is reading.",
    ),
    "orientation_propagation_says": Vocabulary(
        declares="themis.estimation.orientation.Says",
        off_envelope="What a Meek closure says about itself, on `note`. One "
                     "member for what it directed and one per kind of input "
                     "it refused — separate members and not one sentence "
                     "with a clause bolted on, because the bolt was where "
                     "the language went: the summary was written where the "
                     "counts were and the clause where the conflicts were, "
                     "and the reader got the two joined by a full-width "
                     "semicolon in whichever languages the two authors had "
                     "been thinking in (#469).",
    ),
    "orientation_session_says": Vocabulary(
        declares="themis.estimation.orientation_session.Says",
        off_envelope="What a turn of the session says about itself, on "
                     "`note`: the counts, then what the status MEANS. The "
                     "second is what `orientation_session_status` below is "
                     "excused from a gloss ON — `blocked` and `open` both "
                     "leave edges undetermined and only one is fixed by "
                     "asking again, which is a difference in what to do "
                     "next rather than a word.",
    ),
    "markov_blanket_says": Vocabulary(
        declares="themis.estimation.discovery_words.Blanket",
        off_envelope="What a blanket run says about itself, on `note`. Two "
                     "members, and only the first is a summary: the second "
                     "says the blanket is a SCREEN and not an adjustment "
                     "set, which nothing else on the artifact records and "
                     "which is the one mistake a reader can act on — the "
                     "blanket holds children and spouses, and conditioning "
                     "on those opens a collider path.",
    ),
    "lagged_discovery_says": Vocabulary(
        declares="themis.estimation.discovery_words.Lagged",
        off_envelope="What a lagged run says about itself, on `note`: the "
                     "counts, what makes stage one checkable, what MCI "
                     "conditions on, and what was not looked for at all. "
                     "The last is load-bearing — a contemporaneous cause is "
                     "not representable here and can surface as a spurious "
                     "lagged link, so a reader who does not know the scope "
                     "can read a finding out of a shape the method cannot "
                     "express.",
    ),
    "extraction_shape": Vocabulary(
        declares="themis.upstream.extraction_words.Shape",
        off_envelope="What a field of an extraction was supposed to be. It "
                     "goes in a HOLE of the refusal below rather than on an "
                     "envelope — seven of the sixteen species were '{where} "
                     "must be a dict / a list / a non-empty string / …', "
                     "which is one sentence with a hole for which shape, and "
                     "a hole a bare token cannot fill is what `Word` exists "
                     "for. Written as seven sentences it would be seven near "
                     "-identical ones, and an eighth on the day an eighth "
                     "shape is checked.",
    ),
    "extraction_refusal": Vocabulary(
        declares="themis.upstream.extraction_words.Refuses",
        off_envelope="Why the LLM-side front door refused what it was "
                     "handed. It reaches a reader through the exception "
                     "rather than through a result — `themis/upstream` has "
                     "no consumer inside this repository, so the caller IS "
                     "the reader — and each was an f-string at its own raise "
                     "site until #470, forty-nine of them, in English. The "
                     "path was already a slot at every one of those sites, "
                     "which is why forty-nine of them are sixteen species.",
    ),
    "estimation_refusal": Vocabulary(
        declares="themis.estimation.refusal_words.Refuses",
        off_envelope="Why the estimation layer refused a REQUEST — a frame, "
                     "a stated graph, an answer to a question it asked, a "
                     "panel with a time column. It reaches the reader as an "
                     "exception for the reason the one above does, and one "
                     "more: a request that cannot be served produces no "
                     "result to carry an envelope. One table for five catch "
                     "channels, because 'this name is not a column in the "
                     "data' is one sentence whether a blanket or a panel met "
                     "it, and which module caught it is the slot rather than "
                     "the species.",
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


#: The rows above, each with its accessor filled in from the kernel.
#:
#: ``glossed_by`` used to be written on the row, which made this module the
#: place the package's own answer to "how does a reader get this word" was
#: kept — fine while a gate was the only thing that asked, and wrong the
#: moment the browser's tables started being generated from it. The accessor
#: lives in :data:`themis.output.reader_words.GLOSSED` now and the row takes
#: it from there, so the two cannot say different things.
VOCABULARIES: dict[str, Vocabulary] = {
    name: (dataclasses.replace(row, glossed_by=reader_words.GLOSSED[name].gloss)
           if name in reader_words.GLOSSED else row)
    for name, row in _ROWS.items()
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
    if row.tabled:
        return set(reader_words._resolve(row.tabled))
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
    assert row.declares or row.sites or row.tabled, (
        f"{name} is declared by no door and cannot be discovered")
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
    "themis.types.QUALIFIES_THE_ANSWER",
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
        # One row where there were two. They named two sets — the caveats
        # the kernel rendered into a string, and every kind that string
        # could reach — and the difference between them was which author
        # had typed the sentence. Nothing types it now, so there is one
        # set and both surfaces need all of it.
        "themis.types.QUALIFIES_THE_ANSWER",
        "a surface that leads with the caveats has to know which gaps are "
        "caveats, and one it has no row for is one it improvises about",
        ("themis/prompts/response_rendering.md",
         "themis/prompts/gap_to_action.md"),
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
