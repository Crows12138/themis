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
        ),
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
    "outcome_error_premise": Glossed(
        gloss="themis.estimation.outcome_error.Premise.said",
        browser_table="OUTCOME_ERROR_PREMISE_WORDS",
        members=lambda: _stated("themis.estimation.outcome_error.Premise"),
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
    "counterfactual_cell_monotonicity": Glossed(
        gloss="themis.ledger.monotonicity_word"),
    "framing_field": Glossed(
        gloss="themis.output.envelope_glossary.framing_field_word"),
    "investigation_action": Glossed(
        gloss="themis.output.explainer._ACTION_PHRASE"),
    "measurement_scale": Glossed(
        gloss="themis.output.envelope_glossary.scale_word"),
    "missing_data_mechanism": Glossed(
        gloss="themis.output.analysis_report._MECHANISM_WORDS"),
    "priority": Glossed(
        gloss="themis.output.explainer._PRIORITY_PHRASE"),
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


def restated() -> dict[str, Glossed]:
    """The vocabularies the browser holds a copy of, generated from here."""
    return {name: row for name, row in GLOSSED.items() if row.browser_table}


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
// words the report gives a reader, in every language this build writes. What
// is not: the tables that render a vocabulary in the browser's own terms (a
// tier's plain-language gloss, a status's blurb, a refusal's head/lead/tail)
// and the two the kernel deliberately has no word for (a gap carries its own
// description; a query kind is glossed by a whole question line).
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
    return "".join(out)


def write() -> pathlib.Path:
    """Regenerate the browser's copy in place."""
    GENERATED.write_text(typescript(), encoding="utf-8", newline="\n")
    return GENERATED


if __name__ == "__main__":  # pragma: no cover - a build step, not a path
    print(write())
