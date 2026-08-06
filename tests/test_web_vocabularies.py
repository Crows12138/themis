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
from themis.output import analysis_report, assumption_glossary
from themis.types import ResultStatus

REPO = pathlib.Path(__file__).resolve().parent.parent
WEB = REPO / "themis" / "web" / "frontend" / "src" / "lib" / "verdict.ts"
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json").read_text(
        encoding="utf-8")
)


# --- reading the .ts ---------------------------------------------------------
#
# A brace-matcher rather than a regex per table. Three test modules grew
# their own pattern for one object literal each, which is the convention
# that has to be rewritten at every use point — and the fourth would have
# been written the same way.

def _source() -> str:
    return WEB.read_text(encoding="utf-8")


def _literal(name: str, source: str) -> str:
    """The body of one top-level ``const NAME ... = { ... }``."""
    opened = re.search(rf"^(?:export )?const {name}\b[^=]*=\s*[{{\[]",
                       source, re.M)
    assert opened, f"verdict.ts declares no {name}"
    start = opened.end() - 1
    close = {"{": "}", "[": "]"}[source[start]]
    depth, i = 0, start
    while True:
        if source[i] in "{[":
            depth += 1
        elif source[i] in "}]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return source[start + 1:i]


def _top_level_keys(body: str) -> set[str]:
    keys, depth = set(), 0
    for line in body.splitlines():
        if depth == 0:
            found = re.match(r"\s*([A-Za-z_]\w*)\s*:", line)
            if found:
                keys.add(found.group(1))
        depth += (line.count("{") + line.count("[")
                  - line.count("}") - line.count("]"))
    return keys


def _keyed_tables(source: str) -> set[str]:
    """Every top-level ``const NAME: Record<...>`` in the file."""
    return set(re.findall(r"^(?:export )?const (\w+): Record<", source, re.M))


def _string_list(name: str, source: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", _literal(name, source)))


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
    "assumption_severity": set(assumption_glossary.SEVERITIES),
    "identification_pattern": _enum_at(
        "properties", "extensions", "properties", "identification",
        "properties", "pattern"),
    "interventional_risk_provenance": _enum_at(
        "properties", "extensions", "properties", "causation", "properties",
        "interventional_risk_provenance"),
    "refusal_kind": {str(k) for k in refusals.Kind},
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
    source = _source()
    body = _literal("REFUSAL_KIND_ZH", source)
    heads = re.findall(r"head: '([^']+)'", body)
    tails = re.findall(r"tail: '([^']+)'", body)
    assert len(heads) == len(tails) == len(ANCHORS["refusal_kind"])
    assert len(set(heads)) == len(heads), f"two kinds share a head: {heads}"
    assert len(set(tails)) == len(tails), f"two kinds share a tail: {tails}"


def _half_width(text: str) -> str:
    """Only the punctuation the two files spell differently."""
    for full, half in (("，", ","), ("；", ";"), ("（", "("), ("）", ")")):
        text = text.replace(full, half)
    return text


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
    """
    body = _literal("REFUSAL_KIND_ZH", _source())
    entry = re.search(rf"\n  {kind}: \{{(.*?)\n  \}}", body, re.S)
    assert entry, f"verdict.ts states no refusal kind {kind!r}"
    reported = _half_width(analysis_report._kind_zh(kind) or "")
    assert reported, f"the report has no sentence for kind {kind!r}"
    for field in ("lead", "head", "tail"):
        said = re.search(rf"{field}: '([^']+)'", entry.group(1)).group(1)
        assert _half_width(said) in reported, (
            f"the browser's {field} for a {kind} refusal is {said!r}, which "
            f"the report does not say: {reported!r}"
        )


def test_the_ledger_severity_words_are_the_reports_own():
    """Same vocabulary, same question, same answer.

    Unlike the refusal kinds, this one is a bare label with no layout around
    it, so there is no reason for the two surfaces to word it differently —
    and a reader moving between them would read a difference as a
    difference in what was found.
    """
    web = dict(re.findall(
        r"^\s*(\w+): '([^']+)',", _literal("ASSUMPTION_SEVERITY_ZH", _source()),
        re.M))
    assert web == assumption_glossary.SEVERITIES
