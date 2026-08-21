"""Every kernel vocabulary the browser states, held equal to the kernel's.

The browser is the second reader-facing surface, and it cannot import
Python: every closed vocabulary the envelope carries has to be mirrored in
``verdict.ts`` by hand. Eight such tables existed before this module; three
were pinned, each by its own hand-rolled regex in its own test file, and of
the five that were not, TWO had already drifted:

- ``STATUS_LABEL`` held ``unidentifiable``, which no dispatcher emits, and
  not ``outside_language``, which six results in one suite run carried — so
  the browser's status chip printed the identifier to the reader.
- ``GAP_TITLE`` glossed 28 of the 36 declared gap kinds; the other eight
  appeared 93 times across 57 results, rendered as their own ids with the
  underscores swapped for spaces.

Neither is a mistake anybody made twice. Both are what "a discipline
enforced where somebody thought of it" looks like from inside: having a
table and having every table pinned are indistinguishable in the source,
which is the shape ``RENDERED_BLOCKS`` was introduced to fix for blocks.

So ``VOCABULARIES`` names them, and this module checks three things: each
table's keys are exactly the kernel's vocabulary, every keyed table in the
file has declared whether it is one, and every entry has an anchor here.
What none of it can see is a vocabulary the browser states with no table at
all — that hole is narrowed by naming entries after vocabularies rather
than after tables, and it is why the ``ANCHORS`` map below is written from
the kernel's side.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from themis import refusals
from themis import ledger
from themis.output import analysis_report
from themis.output import envelope_glossary
from themis.output.derivation_glossary import SAYS
from themis.risk_provenance import RiskProvenance
from themis.types import ResultStatus

from . import web_source
from themis import language

REPO = pathlib.Path(__file__).resolve().parent.parent
WEB = web_source.VERDICT
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json").read_text(
        encoding="utf-8")
)


# --- reading the .ts ---------------------------------------------------------
#
# The matcher lives in :mod:`tests.web_source`: three test modules grew a
# regex each for one object literal apiece before it existed, and a fourth
# reader of the browser's source is exactly how a fifth regex gets written.

def _source() -> str:
    return web_source.read(WEB)


_literal = web_source.literal
_top_level_keys = web_source.top_level_keys
_chunks = web_source.chunks


def _keyed_tables(source: str) -> set[str]:
    """Every top-level ``const NAME: Record<...>`` in the file."""
    return set(re.findall(r"^(?:export )?const (\w+): Record<", source, re.M))


def _string_list(name: str, source: str) -> set[str]:
    return web_source.string_list(name, source)


def _phrase(field: str, block: str) -> str:
    """One field of a structured entry, as the reader gets it.

    Escape-aware and unescaped, because an English sentence brings
    apostrophes and a single-quoted TypeScript string spells those ``\\'``.
    A reader that stopped at the backslash would cut the sentence in half
    and report the surfaces as disagreeing.
    """
    found = re.search(rf"{field}: '((?:[^'\\]|\\.)*)'", block)
    assert found, f"no {field} in this entry"
    return web_source.unquoted(found.group(1))


# --- the kernel side ---------------------------------------------------------

def _enum_at(*path: str) -> set[str]:
    node = SCHEMA
    for step in path:
        node = node[step]
    return set(node["enum"])


#: Vocabulary name in ``VOCABULARIES`` -> the kernel's own declaration of it.
#: Written from the kernel's side on purpose: an entry here with no table in
#: the browser is the failure this module exists to catch, and it can only be
#: seen from the end that knows the vocabulary exists.
ANCHORS: dict[str, set[str]] = {
    "status": {str(s.value) for s in ResultStatus},
    "answer_tier": _enum_at("$defs", "dataGapReport", "properties",
                            "answer_tier"),
    "query_kind": _enum_at("properties", "query_kind"),
    "gap_kind": _enum_at("$defs", "dataGap", "properties", "kind"),
    "gap_severity": _enum_at("$defs", "dataGap", "properties", "severity"),
    # The three vocabularies of one ledger line. Anchored on the schema and
    # not on ``themis.ledger`` so that the browser is held to the contract
    # both surfaces read, rather than to the module one of them imports.
    "assumption_severity": _enum_at(
        "properties", "extensions", "properties", "assumption_ledger",
        "properties", "assumptions", "items", "properties", "severity"),
    "assumption_layer": _enum_at(
        "properties", "extensions", "properties", "assumption_ledger",
        "properties", "assumptions", "items", "properties", "layer"),
    "assumption_provenance": _enum_at(
        "properties", "extensions", "properties", "assumption_ledger",
        "properties", "assumptions", "items", "properties", "provenance"),
    "identification_pattern": _enum_at(
        "properties", "extensions", "properties", "identification",
        "properties", "pattern"),
    # Anchored on the module, not on either schema enum. Two containers carry
    # this vocabulary — the causation block and the counterfactual cell — and
    # they hold DIFFERENT subsets of it, because the admissible set depends on
    # the derivation rule that wrote it. Pinned against the causation block's
    # projection, this check passed while four of the licences the cell can
    # carry had no translation at all.
    "interventional_risk_provenance": {str(p) for p in RiskProvenance},
    # What a partial-identification interval brackets, and the second
    # quantity the same identified set is read through. Both are one-member
    # enums today; they are anchored anyway, because a one-member vocabulary
    # is exactly the one nobody notices growing.
    "bounds_estimand": _enum_at("$defs", "boundsResult", "properties",
                                "estimand"),
    "bounds_contrast_kind": _enum_at("$defs", "boundsResult", "properties",
                                     "contrast", "properties", "kind"),
    # Which theorem the decomposition failed on. ``null`` is dropped from
    # both: it is the absence of a failure, not a member — the arm renders
    # "可识别" and never asks the table.
    "nde_nie_failed_condition": _enum_at(
        "properties", "extensions", "properties", "mediation_decomposition",
        "properties", "nde_nie", "properties", "failed_condition") - {None},
    "cde_failed_condition": _enum_at(
        "properties", "extensions", "properties", "mediation_decomposition",
        "properties", "cde", "properties", "failed_condition") - {None},
    # Three producers state this, and the robust one can return a shape the
    # other two cannot, so the union is the vocabulary — anchoring on either
    # of the smaller two would let the browser drop the shape only the
    # polynomial inversion produces and still pass.
    "anderson_rubin_set_kind": (
        _enum_at("properties", "numeric_estimate", "properties",
                 "anderson_rubin_confidence_set", "properties", "kind")
        | _enum_at("properties", "numeric_estimate", "properties",
                   "stratified_anderson_rubin_confidence_set", "properties",
                   "kind")
        | _enum_at("properties", "numeric_estimate", "properties",
                   "robust_anderson_rubin_confidence_set", "properties",
                   "kind")
    ),
    # Which margin a misclassification correction inverted. Two sites hold it
    # — the block and the sufficient statistics the verifier re-derives from —
    # and the union is the vocabulary for the same reason it is above.
    "measurement_correction_side": (
        _enum_at("properties", "numeric_estimate", "properties",
                 "measurement_correction", "properties", "side")
        | _enum_at("properties", "numeric_estimate", "properties",
                   "measurement_correction", "properties",
                   "sufficient_statistics", "properties", "side")
    ),
    # Which VanderWeele closed form the ratio-scale split used. The same two
    # tokens name a column's measurement scale elsewhere and that is a
    # different vocabulary, so this is anchored on its own site.
    "four_way_mediator_scale": _enum_at(
        "properties", "numeric_estimate", "properties", "four_way_ratio",
        "properties", "mediator_scale"),
    # Which residual a declared outcome error was priced against. Anchored on
    # the schema site, like the rest: the browser gets the block off the
    # envelope, so what it has to state is what the envelope may carry —
    # anchoring on the Python enum instead would pin the table to a set the
    # browser never sees, and the two could then agree while the schema
    # admitted a third thing.
    "outcome_error_design": _enum_at(
        "properties", "outcome_error", "properties", "design_kind"),
    "refusal_kind": {str(k) for k in refusals.Kind},
    # The one anchor whose vocabulary no schema enum states at all:
    # ``step.rule`` is a free string in derivation.schema.json, and the closed
    # set is the glossary, which is also what the report renders. Anchoring on the
    # module is what ``refusal_kind`` already does for the same reason.
    "derivation_rule": set(SAYS),
}


def _declared() -> dict[str, str]:
    """``VOCABULARIES``, as vocabulary name -> table name."""
    body = _literal("VOCABULARIES", _source())
    return dict(re.findall(r"^\s*(\w+):\s*(\w+),?\s*$", body, re.M))


# --- the checks --------------------------------------------------------------

@pytest.mark.parametrize("vocabulary", sorted(ANCHORS))
def test_the_browser_states_every_value_of_the_vocabulary(vocabulary):
    """One table per vocabulary, and it holds all of it.

    Both directions. A missing key is a value that reaches the reader as its
    own identifier; an extra key is a translation for something the kernel
    does not emit, which reads as coverage and is not — the status table
    carried both at once.
    """
    source = _source()
    declared = _declared()
    assert vocabulary in declared, (
        f"the kernel declares the {vocabulary} vocabulary and verdict.ts's "
        f"VOCABULARIES does not name a table for it"
    )
    keys = _top_level_keys(_literal(declared[vocabulary], source))
    kernel = ANCHORS[vocabulary]
    assert keys == kernel, (
        f"{declared[vocabulary]} does not state the {vocabulary} vocabulary: "
        f"missing {sorted(kernel - keys)}, not in the kernel "
        f"{sorted(keys - kernel)}"
    )


def test_every_declared_vocabulary_has_a_kernel_anchor():
    """A table can be pinned only against something. An entry added to
    VOCABULARIES with no row here would be a table that names a vocabulary
    and is checked against nothing."""
    declared = set(_declared())
    assert declared == set(ANCHORS), (
        f"VOCABULARIES and this module's ANCHORS disagree: "
        f"unanchored {sorted(declared - set(ANCHORS))}, "
        f"no table {sorted(set(ANCHORS) - declared)}"
    )


def test_every_keyed_table_says_whether_it_is_a_vocabulary():
    """The half a pin cannot buy on its own.

    Pinning nine tables says nothing about a tenth, and a tenth is exactly
    how the five unpinned ones arrived. So every ``Record``-typed table in
    the file is either in VOCABULARIES or in NOT_VOCABULARIES, and adding
    one without deciding fails here rather than at a reader.
    """
    source = _source()
    tables = _keyed_tables(source)
    accounted = set(_declared().values()) | _string_list(
        "NOT_VOCABULARIES", source)
    assert tables <= accounted, (
        f"verdict.ts declares keyed table(s) {sorted(tables - accounted)} "
        f"that are in neither VOCABULARIES nor NOT_VOCABULARIES; a table "
        f"keyed by a kernel vocabulary has to say whether it states it"
    )
    assert accounted <= tables, (
        f"VOCABULARIES / NOT_VOCABULARIES name {sorted(accounted - tables)}, "
        f"which verdict.ts does not declare"
    )
    both = set(_declared().values()) & _string_list("NOT_VOCABULARIES", source)
    assert not both, (
        f"{sorted(both)} is in both VOCABULARIES and NOT_VOCABULARIES; the "
        f"two lists partition this file's keyed tables, and a table in both "
        f"has said opposite things about itself in the same file"
    )


def test_the_two_severity_vocabularies_stay_apart():
    """They share a field name and nothing else.

    A gap's severity grades how much a missing input blocks an answer; an
    assumption's grades how the conclusion dies if it is false. One Python
    dict held both, which is not wrong to read and does say severity is one
    vocabulary — and the browser copied that reading and took three of the
    six, so the ledger's three reached 688 results untranslated.
    """
    gaps = ANCHORS["gap_severity"]
    assumptions = ANCHORS["assumption_severity"]
    assert not (gaps & assumptions), (
        f"the two severity vocabularies now overlap on "
        f"{sorted(gaps & assumptions)}; one table could then answer both, "
        f"and the reader would get the other question's word"
    )


def test_the_refusal_kinds_each_say_something_different():
    """The vocabulary is pinned above; what it is FOR is checked here.

    Five identical sentences would satisfy key equality and leave the reader
    exactly where the raw identifier did: unable to tell "go get different
    data" from "change one input".
    """
    said = web_source.members("REFUSAL_KIND_WORDS", _source())
    assert set(said) == ANCHORS["refusal_kind"]
    for lang in language.written():
        for field in ("head", "tail"):
            found = [_phrase(field, web_source.entry(entry, lang))
                     for entry in said.values()]
            assert len(set(found)) == len(found), (
                f"two kinds share a {lang} {field}: {found}")


@pytest.mark.parametrize("kind", sorted(ANCHORS["refusal_kind"]))
def test_the_browser_tells_the_reader_what_the_report_tells_them(kind):
    """Same refusal, two surfaces, one instruction.

    Not the whole sentence: the report wraps its head in markdown and puts
    the occasion between head and tail, and one of the five says 没有算出
    where the others say 没有给出 — a difference that is about that kind and
    not about the reader's next move. What has to be the same is the move,
    and that is the tail. Two surfaces free to word it separately would be
    free to disagree about it, which is the drift this module exists for
    one level down.

    Substring, and otherwise byte for byte: both sides used to be run
    through a punctuation-width substitution, which is a list of ways the
    two copies were allowed to disagree, assembled from the ways they
    already did. ``tests/test_a_sentence_has_one_spelling.py`` says how the
    repository spells a Chinese sentence, which leaves the allowance with
    nothing to allow.
    """
    said = web_source.members("REFUSAL_KIND_WORDS", _source())
    assert kind in said, f"verdict.ts states no refusal kind {kind!r}"
    words = analysis_report._kind_words(kind) or {}
    for lang in language.written():
        reported = words.get(lang, "")
        assert reported, f"the report has no {lang} sentence for kind {kind!r}"
        block = web_source.entry(said[kind], lang)
        for field in ("lead", "head", "tail"):
            phrase = _phrase(field, block)
            assert phrase in reported, (
                f"the browser's {lang} {field} for a {kind} refusal is "
                f"{phrase!r}, which the report does not say: {reported!r}"
            )


#: The three vocabularies of one ledger line: browser table -> kernel enum.
#: Parametrized rather than written three times because they are one
#: discipline applied three times, and a rule stated per member is a rule
#: that holds until someone adds a fourth.
_LEDGER_TABLES = {
    "ASSUMPTION_SEVERITY_WORDS": ledger.Severity,
    "LEDGER_LAYER_WORDS": ledger.Layer,
    "LEDGER_PROVENANCE_WORDS": ledger.Provenance,
}


@pytest.mark.parametrize("table,vocabulary", sorted(
    _LEDGER_TABLES.items(), key=lambda kv: kv[0]))
def test_the_ledger_words_are_the_reports_own(table, vocabulary):
    """Same vocabulary, same question, same answer.

    Unlike the refusal kinds, these are bare labels with no layout around
    them, so there is no reason for the two surfaces to word them
    differently — and a reader moving between them would read a difference
    as a difference in what was found.

    Every language at once, not the default one. A pin on one language is
    what lets the second arrive reworded: the equality that costs nothing
    while the copy is exact costs nothing per language too.
    """
    assert web_source.words_map(table, _source()) == {
        str(m): dict(m.words) for m in vocabulary}


#: The envelope glossaries both surfaces state: browser table -> kernel table.
#: ``test_the_browser_states_every_value_of_the_vocabulary`` above compares key
#: sets, which is the right check for a table whose words are laid out
#: differently on each surface. These are not those. Each is one phrase per
#: member answering one question, printed with nothing around it, so the two
#: copies have no reason to differ and a difference reads to a reader who
#: moves between the surfaces as a difference in what was found.
_GLOSSARY_TABLES = {
    "AR_SET_KIND_WORDS": envelope_glossary.AR_SET_KIND,
    "MEASUREMENT_SIDE_WORDS": envelope_glossary.MEASUREMENT_SIDE,
    "FOUR_WAY_MEDIATOR_SCALE_WORDS": envelope_glossary.FOUR_WAY_MEDIATOR_SCALE,
}


@pytest.mark.parametrize("table,kernel", sorted(
    _GLOSSARY_TABLES.items(), key=lambda kv: kv[0]))
def test_the_glossary_words_are_the_kernels_own(table, kernel):
    """Same member, same question, same sentence — checked as text.

    The strongest available pin, and it costs nothing when the copy is exact.
    What it buys is the case key equality cannot see: both surfaces know all
    seven shapes an AR set comes in, and one of them says the unbounded case
    means the instrument cannot bound the effect while the other says only
    that the set is unbounded.
    """
    assert web_source.words_map(table, _source()) == {
        member: dict(words) for member, words in kernel.items()}


def test_the_chain_reads_the_same_on_both_surfaces():
    """Fifty-eight sentences, mirrored rather than reworded.

    The refusal kinds are held loosely — the report wraps its head in
    markdown and puts the occasion between head and tail, so only the
    instruction has to survive. Nothing wraps these: both surfaces print
    one sentence per step, in the same order, answering the same question,
    so the strongest available pin is plain equality and it costs nothing
    when the copy is exact. A reader comparing the two should find them
    the same text, not two accounts of one step.
    """
    web = web_source.words_map("DERIVATION_SAYS", _source())
    assert web == {rule: dict(words) for rule, words in SAYS.items()}


# --- a table nobody reads ----------------------------------------------------

SRC = web_source.SRC


def test_every_vocabulary_table_has_a_reader():
    """A table declared and never read renders nothing.

    ``VOCABULARIES`` says this surface states a vocabulary; it cannot say
    the words leave the module, and a translation nobody calls looks in the
    source exactly like one every reader sees. What this proves is only
    that a call site exists — not that the reader's eye reaches it — but
    the failure it does catch is the one that happened: the ledger's layer
    and provenance had no table here at all, and the fix would have been
    just as silent if the table had been added without the component.

    Reachability is transitive inside ``verdict.ts`` and then has to leave
    it: two tables are read by a renderer map, which is read by an exported
    function, which the component imports.
    """
    source = _source()
    bodies = _chunks(source)
    # Imports stripped: an import is not a use, and a component that stops
    # rendering a label keeps importing it — which is exactly what the
    # counterexample for this check does, and what it did until the import
    # lines came out of the haystack.
    elsewhere = "\n".join(
        re.sub(r"^import\b[^;\n]*(?:from\s+'[^']+')?;?\s*$", "",
               p.read_text(encoding="utf-8"), flags=re.M)
        for p in sorted(SRC.rglob("*.ts*")) if p != WEB)

    def reaches(table: str) -> bool:
        seen, frontier = {table}, [table]
        while frontier:
            name = frontier.pop()
            if name != table and re.search(rf"\b{name}\b", elsewhere):
                return True
            for other, body in bodies.items():
                if other in seen or other == "VOCABULARIES":
                    continue
                if re.search(rf"\b{name}\b", body):
                    seen.add(other)
                    frontier.append(other)
        return bool(re.search(rf"\b{table}\b", elsewhere))

    unread = sorted(t for t in _declared().values() if not reaches(t))
    assert not unread, (
        f"{unread} are declared as vocabularies this surface states, but "
        f"nothing outside verdict.ts reaches them — the words do not leave "
        f"the module"
    )
