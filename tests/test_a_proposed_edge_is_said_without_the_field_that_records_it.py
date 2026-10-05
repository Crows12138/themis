"""A proposed edge is said to the reader without the field that records it.

#814. The sentence that says an edge on the route to the answer is the
upstream model's hypothesis carried, in brackets, where the program keeps
that fact: ``annotations.source = llm_proposal``. That is an address in the
program, and the entry already carries it as its ``source_path``; the
sentence is what a reader reads, and to a reader it was noise in the middle
of the one clause that mattered.

Both spellings are pinned: the sentence for one edge, and the one that
leads a group of them (#812).
"""
from __future__ import annotations

import pytest

from themis import gaps, ledger

def _the_sentence_for_one_edge() -> dict:
    found = [
        value for value in vars(gaps).values()
        if isinstance(value, dict)
        and isinstance(value.get("the_edge_is_an_llm_proposal"), dict)
    ]
    assert len(found) == 1
    return found[0]["the_edge_is_an_llm_proposal"]


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_sentence_for_one_edge_names_no_field(lang):
    said = _the_sentence_for_one_edge()[lang]
    assert "annotations" not in said
    assert "llm_proposal" not in said
    assert "{edge}" in said


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_sentence_leading_several_names_no_field(lang):
    said = ledger.SEVERAL_LEAD["the_edge_is_an_llm_proposal"][lang]
    assert "annotations" not in said
    assert "llm_proposal" not in said
    assert "{n}" in said


def test_the_two_say_the_same_thing_in_the_singular_and_the_plural():
    one = _the_sentence_for_one_edge()
    several = ledger.SEVERAL_LEAD["the_edge_is_an_llm_proposal"]
    assert "是上游 LLM 提出的假设，不是经证据支持的边。" in one["zh"]
    assert "是上游 LLM 提出的假设，不是经证据支持的边。" in several["zh"]
    assert "the upstream LLM proposed, not an edge evidence supports." in (
        one["en"])
    assert "the upstream LLM proposed, not edges evidence supports." in (
        several["en"])
