"""An entry in a block the contract leaves open is addressed by position.

``extensions.ambiguities`` is the one block the envelope contract leaves
open on purpose: what it carries is authored upstream, and enumerating
the kinds would make the kernel the authority on which uncertainties a
caller is allowed to report. Two consequences of that openness had been
read as if the block were closed.

The first is the address. A gap raised from an entry cited it as
``extensions.ambiguities[kind]``, and ``kind`` is the only field the
block requires — so it is the one field two entries are most likely to
share. When two did, two entries differing in every other field became
two gaps differing in none, each citing a place with two occupants and
naming neither. Measured on the corpus: 11 refs pick a list member, 4 of
them land on more than one entry, in 2 rows.

The second is the reason. The producer looked for it under ``rationale``
and ``note``; upstream writes ``description``. 21 of the 24 entries in
the corpus carried a reason that was dropped, and the reader was told no
reason had been given — including one entry whose reason was a question
addressed to that reader. A field list at the reading site cannot be
right about an open block, so the list is declared instead, in
``gaps.WHY_AN_AMBIGUITY_GIVES`` and in the block's own contract, and
this file holds those two to each other.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from themis.gaps import WHY_AN_AMBIGUITY_GIVES, Sentence
from themis.output.data_gap_report import _classify_llm_ambiguities
from themis.verifier.data_gap_rules import _at_path

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (REPO_ROOT / "themis/schemas/query_result.schema.json")
    .read_text(encoding="utf-8"))
AMBIGUITIES = SCHEMA["properties"]["extensions"]["properties"]["ambiguities"]


def gaps_for(*entries) -> list:
    return list(_classify_llm_ambiguities({"ambiguities": list(entries)}))


def only_sentence(gap):
    return gap.describes[0].sentence


def said(gap) -> dict:
    return dict(gap.describes[0].said)


# ------------------------------------------------- 声明本身

def test_the_names_the_kernel_reads_are_declared_in_order():
    assert list(WHY_AN_AMBIGUITY_GIVES) == [
        "description", "rationale", "reason", "note"]


def test_every_declared_name_says_why_it_is_read():
    empty = [name for name, why in WHY_AN_AMBIGUITY_GIVES.items()
             if not why or not why.strip()]
    assert not empty, empty


def test_the_contract_names_the_same_fields():
    """The promise is made to the caller, so the caller's document says it."""
    prose = AMBIGUITIES["description"]
    missing = [f"`{name}`" for name in WHY_AN_AMBIGUITY_GIVES
               if f"`{name}`" not in prose]
    assert not missing, missing


def test_the_contract_promises_no_field_the_kernel_does_not_read():
    """The other side. A name in the document and not in the table is a
    promise nothing keeps, which is worse than one never made."""
    prose = AMBIGUITIES["description"]
    start = prose.index("the entry's")
    promised = {word.strip("`,. ") for word in prose[start:].split()
                if word.startswith("`") and word.strip("`,. ").isidentifier()}
    assert promised <= set(WHY_AN_AMBIGUITY_GIVES) | {"kind", "n"}, promised


def test_the_block_is_still_open():
    """Nothing here may close it — only `kind` is required, and no
    vocabulary is enumerated for it."""
    assert AMBIGUITIES["items"]["required"] == ["kind"]
    assert "enum" not in AMBIGUITIES["items"]["properties"]["kind"]


# ------------------------------------------------- 读哪个字段

def test_the_first_name_present_wins():
    gap, = gaps_for({"kind": "k", "description": "D", "rationale": "R"})
    assert said(gap)["rationale"] == "D"


def test_a_later_name_is_read_when_the_earlier_ones_are_absent():
    gap, = gaps_for({"kind": "k", "note": "N"})
    assert said(gap)["rationale"] == "N"


def test_an_entry_with_no_reason_is_reported_as_having_none():
    """The refusing side of the same rule: it must still be possible for
    a gap to say no reason was given, or the sentence that says so dies
    unused and every entry gets a reason invented for it."""
    gap, = gaps_for({"kind": "k"})
    assert only_sentence(gap) is Sentence.THE_CALLER_FLAGGED_AN_UNCERTAINTY
    assert "rationale" not in said(gap)


def test_an_empty_reason_is_no_reason():
    gap, = gaps_for({"kind": "k", "description": ""})
    assert only_sentence(gap) is Sentence.THE_CALLER_FLAGGED_AN_UNCERTAINTY


def test_a_name_outside_the_declaration_is_not_read():
    """Otherwise the table is decoration and the reading site is still
    the authority."""
    gap, = gaps_for({"kind": "k", "why": "not a declared name"})
    assert only_sentence(gap) is Sentence.THE_CALLER_FLAGGED_AN_UNCERTAINTY


# ------------------------------------------------- 按位置引用

def test_two_entries_of_one_kind_are_two_gaps_that_differ():
    first, second = gaps_for(
        {"kind": "selection_bias", "description": "collider"},
        {"kind": "selection_bias", "description": "Berkson"})
    assert first != second
    assert [ref.ref_id for ref in first.provenance] == [
        "extensions.ambiguities[#0]"]
    assert [ref.ref_id for ref in second.provenance] == [
        "extensions.ambiguities[#1]"]


def test_the_position_is_the_entry_s_own_even_when_one_is_skipped():
    """``dose_response_query`` has its own species and raises no gap here.
    The entries after it keep the positions they occupy, because the ref
    is an address into the caller's list and not a count of gaps."""
    gaps = gaps_for({"kind": "dose_response_query"},
                    {"kind": "selection_bias", "description": "x"})
    assert len(gaps) == 1
    assert gaps[0].provenance[0].ref_id == "extensions.ambiguities[#1]"


# ------------------------------------------------- 路径跟得到吗

ENVELOPE = {"extensions": {"ambiguities": [
    {"kind": "a"}, {"kind": "b"}, {"kind": "0"}]}}


def test_a_position_resolves():
    for at in range(3):
        found, why = _at_path(ENVELOPE, f"extensions.ambiguities[#{at}]")
        assert found, why


def test_a_position_past_the_end_does_not():
    found, why = _at_path(ENVELOPE, "extensions.ambiguities[#3]")
    assert not found
    assert "3 entries" in why


def test_picking_by_kind_still_works():
    found, _ = _at_path(ENVELOPE, "extensions.ambiguities[b]")
    assert found


def test_a_kind_that_looks_like_a_number_is_still_reachable_by_kind():
    """The collision this syntax was chosen to avoid. ``[0]`` is a kind
    and ``[#0]`` is a position, so a caller who names an ambiguity ``0``
    loses nothing."""
    found, _ = _at_path(ENVELOPE, "extensions.ambiguities[0]")
    assert found
    missing, _ = _at_path(ENVELOPE, "extensions.ambiguities[9]")
    assert not missing


@pytest.mark.parametrize("path", [
    "extensions.ambiguities[#]",
    "extensions.ambiguities[#x]",
    "extensions.ambiguities[# 0]",
])
def test_a_hash_that_is_not_a_position_is_read_as_a_kind(path):
    """And so refuses, there being no entry of that kind — rather than
    being read as position zero by a lenient parse."""
    found, why = _at_path(ENVELOPE, path)
    assert not found
    assert "kind" in why
