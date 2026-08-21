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

So ``VOCABULARIES`` names them, and this module checks four things: each
table's keys are exactly the kernel's vocabulary, each table's WORDS are
the kernel's own, every keyed table in the file has declared whether it is
one, and every entry has an anchor here. What none of it can see is a
vocabulary the browser states with no table at all — that hole is narrowed
by naming entries after vocabularies rather than after tables, and it is
why the ``ANCHORS`` map below is written from the kernel's side.

The second of those arrived late, and by the route the paragraph above
describes — one level down from where that paragraph was looking. Text was
pinned per table, in four places: two lists in this module, a function of
its own here, and a test in ``test_risk_provenance``. Between them they
covered eight of the eighteen tables that restate the kernel and said
nothing about the other ten, and two of the ten had drifted:
``identification_pattern.c_factor`` had lost 「分解」, and it and
``bounds_contrast_kind.ace`` had been retyped with half-width parentheses
where the kernel writes full-width ones. A fix that enumerates what it
covers leaves the level below it enumerated too, which is why the text
check is parametrized over ``ANCHORS`` exactly as the key check is, and why
the three lists are gone.

What it does NOT hold is the three tables that render a vocabulary in the
browser's own terms, and those are recognised by shape rather than named:
each holds a structure per language — a tier's label beside a
plain-language gloss, a status's label beside a blurb, a refusal's head,
lead and tail — where a restatement holds one string. An exemption written
as a list is a place to put a fourth entry, so which tables have a shape of
their own is itself pinned as an equality.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from themis import refusals
from themis.output import analysis_report
from themis.output.derivation_glossary import SAYS
from themis.risk_provenance import RiskProvenance
from themis.types import ResultStatus

from . import web_source
from .test_vocabulary_reach import VOCABULARIES, _word_for
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
    "result_status": {str(s.value) for s in ResultStatus},
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


#: Where the kernel's own word for a member lives, for the one vocabulary
#: the reach registry has no row for. ``step.rule`` is a free string in
#: derivation.schema.json, so no schema enum declares it and the closed set
#: is the glossary — which is the same reason ``ANCHORS`` above anchors it
#: on the module rather than on a schema site.
_GLOSSED_HERE = {"derivation_rule": "themis.output.derivation_glossary.SAYS"}

#: What the kernel deliberately has no word for, each said on its own row
#: in the reach registry: a gap carries its own ``description`` and its kind
#: is a key no reader meets; a query kind is glossed by a whole question
#: line rather than by a word. There is nothing to hold a copy against, so
#: nothing is — and the reason lives beside the vocabulary rather than here.
_KERNEL_SAYS_NOTHING = {"gap_kind", "query_kind"}

#: The tables that render a vocabulary in the browser's own terms. Measured
#: rather than declared: what puts a table here is holding a STRUCTURE per
#: language, and ``test_a_table_is_exempt_only_by_having_a_shape_of_its_own``
#: is what keeps this a record of that measurement instead of a way to be
#: excused from the check above it.
_ITS_OWN_RENDERING = {"answer_tier", "result_status", "refusal_kind"}


def _kernel_word(vocabulary: str, member: str, lang: str) -> str:
    """What the kernel hands a reader of ``lang`` for this member.

    Through the gloss the kernel's own surfaces call, not through the table
    behind it: what the browser has to match is what a reader is actually
    given, and a gloss that transforms its table on the way out would make
    those two different texts.
    """
    return _word_for(
        _GLOSSED_HERE.get(vocabulary) or VOCABULARIES[vocabulary].glossed_by,
        member, lang)


def _browser_word(entry: str, lang: str) -> tuple[str, bool]:
    """What one member says in one language, and whether it is structured.

    A restatement holds one string per language. A table that renders the
    vocabulary in its own terms holds an object instead, and its label is
    read out of it so that the SHAPE can be reported separately from the
    text — the caller needs the two apart, because the shape is what says
    the text is not supposed to match.
    """
    opened = re.search(rf"(?<![\w'\"]){lang}:\s*", entry)
    if not opened:
        return "", False
    rest = entry[opened.end():].lstrip()
    if rest.startswith("{"):
        found = re.search(r"label: '((?:[^'\\]|\\.)*)'",
                          web_source.balanced(rest, 0))
        return (web_source.unquoted(found.group(1)) if found else ""), True
    found = re.match(r"'((?:[^'\\]|\\.)*)'", rest)
    return (web_source.unquoted(found.group(1)) if found else ""), False


def _reworded(vocabulary: str, body: str) -> list[str]:
    """Every member of one table whose text is not the kernel's own.

    A member with no text in some language is passed over rather than
    reported: that is a hole, not a rewording, and
    ``test_the_browser_has_a_word_for_every_member_in_every_language``
    is where the denominator for it is kept.
    """
    out = []
    for member in sorted(_top_level_keys(body)):
        entry = web_source.entry(body, member)
        for lang in sorted(language.written()):
            theirs, structured = _browser_word(entry, lang)
            if structured or not theirs:
                continue
            ours = _kernel_word(vocabulary, member, lang)
            if not ours:
                out.append(f"{vocabulary}.{member} [{lang}]: the browser says "
                           f"{theirs!r} and the kernel has no word at all")
            elif ours.replace("**", "") != theirs:
                out.append(f"{vocabulary}.{member} [{lang}]: the kernel says "
                           f"{ours!r} and the browser says {theirs!r}")
    return out


@pytest.mark.parametrize("vocabulary", sorted(ANCHORS))
def test_the_browser_says_what_the_kernel_says(vocabulary):
    """The same words, and not only the same keys.

    Holding the KEYS equal is what let two entries drift while passing, and
    of the 220 member-language pairs across the fifteen tables that restate
    the kernel those two were the only ones that differed at all — which is
    what makes plain equality the right pin here. It costs nothing while
    the copy is exact, and a reader moving between the two surfaces reads
    any difference as a difference in what was found.

    Every language this build has words in, not the one it answers in.
    English is the language most able to drift unnoticed precisely because
    no reader can be answered in it yet: nobody is looking at it, and it is
    already written on both surfaces.

    ``**`` is normalised away rather than pinned. Emphasis is a decision
    each surface makes about its own layout — the report writes markdown
    and the browser's chip does not render it — and four long sentences in
    ``outcome_error_design`` differ by exactly that and by nothing else.
    """
    if vocabulary in _KERNEL_SAYS_NOTHING:
        pytest.skip("the kernel deliberately has no word for this vocabulary")
    if vocabulary in _ITS_OWN_RENDERING:
        pytest.skip("this table renders the vocabulary in its own terms")
    assert not _reworded(
        vocabulary, _literal(_declared()[vocabulary], _source()))


def test_a_table_is_exempt_only_by_having_a_shape_of_its_own():
    """What keeps the exemption above a measurement rather than a list.

    Three tables say more about a member than the kernel does — a tier's
    label beside a plain-language gloss, a status's label beside a blurb, a
    refusal's head, lead and tail — and each announces it by holding a
    structure per language where a restatement holds a string. Naming them
    in a list and stopping there would make the list the place a fourth
    table goes to stop being checked, which is how the ten unpinned tables
    came about one level up. So the list is held to what the source shows.
    """
    source, declared, structured = _source(), _declared(), set()
    for vocabulary in set(ANCHORS) - _KERNEL_SAYS_NOTHING:
        body = _literal(declared[vocabulary], source)
        for member in _top_level_keys(body):
            entry = web_source.entry(body, member)
            if any(_browser_word(entry, lang)[1]
                   for lang in language.written()):
                structured.add(vocabulary)
    assert structured == _ITS_OWN_RENDERING, (
        f"the tables holding a structure per language are now "
        f"{sorted(structured)}; a table that has stopped restating the "
        f"kernel has to say what it says instead, and one that has started "
        f"restating it is checked from now on"
    )


def test_the_check_sees_a_parenthesis_retyped():
    """The counterexample, doctored the way the two real ones were.

    Both drifted by being retyped rather than rewritten, and a half-width
    parenthesis came with the retyping. A gate nobody has watched say no is
    a statement about the corpus that happened to be there, and this one
    would pass on any repository whose copies were already exact.
    """
    vocabulary = "identification_pattern"
    body = _literal(_declared()[vocabulary], _source())
    doctored = body.replace("（", "(", 1).replace("）", ")", 1)
    assert doctored != body, "no full-width parenthesis left to retype"
    assert not _reworded(vocabulary, body)
    assert len(_reworded(vocabulary, doctored)) == 1


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
