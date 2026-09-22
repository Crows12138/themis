"""What a gap says about a learned graph is what the run recorded.

A graph that was discovered rather than declared comes with a disclosure:
which algorithm learned it, at which significance threshold, on how many
rows, and which of that algorithm's assumptions the run itself found broken
on this data. Every one of those is a printing of a value the caller's own
document declares under ``extensions.discovery_metadata``.

Nothing had read that record. ``discovery_metadata`` occurred nowhere in
the verifier: such a gap cites the site in its provenance and T10-1 asks
whether the site is THERE and stops, so the four printings had one author
between them — a disclosure could name an algorithm the run never ran, an α
it never used, a sample it never saw.

Held at the site rather than through the citation. The two coincide exactly
on the stored answers, so the ref picks out nothing the fixed path does not,
and wanting it would let a forgery drop the ref and then say what it liked.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

from themis import gaps
from themis.verifier import data_gap_rules as module
from themis.verifier import verify_a_gap_says_what_the_run_recorded as rule
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The sentences that print the record, by what each one prints.
READS = dict(module._WHAT_THE_RUN_RECORDED)
VIOLATED = module._THE_ASSUMPTIONS_IT_BROKE

#: Named rather than taken in some order, so a case below exercises the
#: sentence it says it does: a silence reached because the hole under test
#: belongs to another sentence reads exactly like the rule being silent.
ALGORITHM = gaps.Sentence.THE_GRAPH_WAS_LEARNED_BY_AN_ALGORITHM.value
ALPHA = gaps.Sentence.DISCOVERY_USED_THIS_SIGNIFICANCE_THRESHOLD.value
ROWS = gaps.Sentence.DISCOVERY_RAN_ON_THIS_MANY_ROWS.value

#: Answers whose gap report discloses a learned graph. Pinned because a
#: rule's reach is the point: silence is what this looked like before, and
#: silence is what a rule that stops reaching looks like.
ANSWERS_EXERCISING_THIS = 2


def _recorded(pair) -> dict | None:
    extensions = pair["program"].get("extensions") or {}
    recorded = extensions.get("discovery_metadata")
    return recorded if isinstance(recorded, dict) else None


def _carriers() -> list:
    out = []
    for name, pair in SHAPES.items():
        if _recorded(pair) is None:
            continue
        for gap in ((pair["result"].get("data_gap_report") or {})
                    .get("gaps") or ()):
            if any(d.get("sentence") in READS
                   for d in gap.get("describes") or ()):
                out.append(name)
                break
    return sorted(out)


def _a_sentence(result, sentence):
    """The first description of that sentence, to move in place."""
    for gap in (result.get("data_gap_report") or {}).get("gaps") or ():
        for described in gap.get("describes") or ():
            if described.get("sentence") == sentence:
                return described
    raise AssertionError(f"no gap here says {sentence!r}")


def _the_learned_graph_group() -> set:
    """The sentences ``themis.gaps`` files under the learned-graph heading.

    Read from the source rather than listed here, so a sentence added to
    that group arrives in this test instead of passing unseen.
    """
    source = pathlib.Path(gaps.__file__).read_text(encoding="utf-8")
    start = source.index("# --- the graph was learned rather than declared")
    end = source.index("# --- what the graph does not say", start)
    names = re.findall(r"^    ([A-Z][A-Z0-9_]*) = \($",
                       source[start:end], re.MULTILINE)
    assert names, "the learned-graph heading names no sentence"
    return {getattr(gaps.Sentence, name).value for name in names}


CARRIERS = _carriers()


def test_the_corpus_exercises_this_rule():
    assert len(CARRIERS) == ANSWERS_EXERCISING_THIS, CARRIERS
    for name in CARRIERS:
        recorded = _recorded(SHAPES[name])
        for _hole, field in READS.values():
            assert field in recorded, (name, field)


def test_no_honest_answer_is_refused():
    """All of them, not only the carriers.

    A rule reading a block most answers do not carry has more quiet cases
    than loud ones, and a quiet case that raises is found last.
    """
    for _name, pair in SHAPES.items():
        rule(pair["result"], pair["program"])


@pytest.mark.parametrize("name", CARRIERS)
@pytest.mark.parametrize("sentence", sorted(READS))
def test_a_printing_that_is_not_the_records_is_refused(name, sentence):
    """The forgery this exists for: a disclosure of a run that never was."""
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    described = _a_sentence(result, sentence)
    hole, field = READS[sentence]
    honest = described["said"][hole]
    described["said"][hole] = f"{honest}_forged"
    with pytest.raises(VerificationError, match=f"T10-10.*{field}"):
        rule(result, pair["program"])


@pytest.mark.parametrize("name", CARRIERS)
def test_a_disclosure_answers_for_the_run_without_citing_it(name):
    """The citation is not what finds the record.

    One program records one run, at one path. A gap that drops the ref and
    keeps the sentence is the forgery that reading the record THROUGH the
    provenance would have let pass.
    """
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    described = _a_sentence(result, ALGORITHM)
    described["said"][READS[ALGORITHM][0]] = "a_run_that_never_happened"
    for gap in result["data_gap_report"]["gaps"]:
        gap["provenance"] = []
    with pytest.raises(VerificationError, match="T10-10"):
        rule(result, pair["program"])


def test_what_the_run_found_broken_is_shown_rather_than_composed():
    """The one hole that is not a word but the statements the run filed."""
    name = next((n for n in CARRIERS
                 if any(d.get("sentence") == VIOLATED
                        for gap in ((SHAPES[n]["result"]
                                     .get("data_gap_report") or {})
                                    .get("gaps") or ())
                        for d in gap.get("describes") or ())), None)
    assert name is not None, "no stored answer shows the violations sentence"
    pair = SHAPES[name]
    honest = copy.deepcopy(pair["result"])
    rule(honest, pair["program"])

    result = copy.deepcopy(pair["result"])
    described = _a_sentence(result, VIOLATED)
    shown = described["words"]["violations"]
    assert shown, "that sentence shows no violation to move"
    described["words"]["violations"] = shown[:-1]
    with pytest.raises(VerificationError, match="what the run found broken"):
        rule(result, pair["program"])


def _one(said, recorded, sentence=ALGORITHM):
    """A program and a result carrying one disclosure, to hold as a pair."""
    program = {"extensions": {"discovery_metadata": recorded}}
    result = {"data_gap_report": {"gaps": [{
        "kind": "graph_learned_from_data",
        "provenance": [{"ref_kind": "program_site",
                        "ref_id": "program:extensions.discovery_metadata"}],
        "describes": [{"sentence": sentence, "said": said}],
    }]}}
    return result, program


def test_a_reader_is_told_the_word_and_not_its_case():
    """A sentence prints the algorithm in a reader's letters.

    The record keeps the token's, so the two differ by case on every stored
    answer and holding the spelling would refuse all of them.
    """
    rule(*_one({"algorithm": "LiNGAM"}, {"algorithm": "lingam"}))
    with pytest.raises(VerificationError, match="T10-10"):
        rule(*_one({"algorithm": "PC"}, {"algorithm": "lingam"}))


def test_a_count_recorded_as_a_number_is_printed_as_text():
    """A hole is filled with text and the record keeps a number."""
    rule(*_one({"n": "1000"}, {"sample_size": 1000}, ROWS))
    rule(*_one({"n": "1000"}, {"sample_size": 1000.0}, ROWS))
    with pytest.raises(VerificationError, match="sample_size"):
        rule(*_one({"n": "1000"}, {"sample_size": 999}, ROWS))
    rule(*_one({"alpha": "0.05"}, {"alpha": 0.05}, ALPHA))
    with pytest.raises(VerificationError, match="alpha"):
        rule(*_one({"alpha": "0.01"}, {"alpha": 0.05}, ALPHA))


def test_what_this_rule_does_not_answer():
    """Three silences, each of them another author's question.

    Whether the cited site is there is T10-1's; whether a sentence filled
    its holes belongs to whoever writes the sentences; and a field the
    record does not carry is nothing to compare against. A second author
    for any of them would be two answers that disagree the first time one
    of them moves.
    """
    rule({"data_gap_report": {"gaps": [{
        "describes": [{"sentence": ALGORITHM,
                       "said": {"algorithm": "PC"}}]}]}},
         {"extensions": {}})
    rule(*_one({}, {"algorithm": "lingam"}))
    rule(*_one({"algorithm": "PC"}, {"alpha": 0.05}))


def test_the_program_itself_is_required():
    """A rule handed something it does not recognise refuses rather than
    returns: a rule that returns quietly reads as a rule that ran."""
    with pytest.raises(TypeError, match="program document itself"):
        rule({"data_gap_report": {"gaps": []}}, object())


def test_every_sentence_about_the_run_that_prints_something_is_read():
    """The drift guard.

    A sentence added to the learned-graph group with a hole in it is a new
    printing of that record, and a new printing with one author is exactly
    what this rule was written for. The group is read from the source, so
    an addition fails here rather than passing unseen; the one sentence
    this rule does not read is the one whose text has nothing to print.
    """
    group = _the_learned_graph_group()
    holes = {}
    for sentence in group:
        words = gaps.DESCRIBES[sentence]
        holes[sentence] = set(re.findall(r"\{(\w+)\}", words["en"]))
        assert holes[sentence] == set(re.findall(r"\{(\w+)\}", words["zh"])), (
            f"{sentence} prints different holes in its two languages")
    prints = {sentence for sentence, hole in holes.items() if hole}
    assert prints == set(READS) | {VIOLATED}, sorted(prints)
    silent = group - prints
    assert silent == {
        gaps.Sentence.A_LEARNED_GRAPH_INHERITS_THE_ALGORITHMS_ASSUMPTIONS
        .value}, sorted(silent)


def test_the_hole_each_sentence_prints_is_the_hole_the_rule_reads():
    """The table says which hole a sentence fills; its template says so too,
    and a rule reading the wrong one compares nothing."""
    for sentence, (hole, _field) in READS.items():
        text = gaps.DESCRIBES[sentence]["en"]
        assert set(re.findall(r"\{(\w+)\}", text)) == {hole}, sentence
    assert set(re.findall(r"\{(\w+)\}",
                          gaps.DESCRIBES[VIOLATED]["en"])) == {"violations"}


def test_the_rule_is_on_the_run_path():
    """Wired, not merely importable — the failure this cannot see is the
    one where the rule is perfect and nothing calls it."""
    kernel = (pathlib.Path(gaps.__file__).parent / "kernel.py").read_text(
        encoding="utf-8")
    assert "verify_a_gap_says_what_the_run_recorded(result, ast)" in kernel
