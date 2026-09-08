"""T10-1 follows a gap's refs. Half of them pointed at the other document.

A gap's provenance says where what it says came from. T10-1 follows an
``envelope_path`` ref onto the answer and refuses one that lands on
nothing; a ``program_site`` ref makes the same claim about the PROBLEM,
and nothing followed it. The rule that reads a report is result-only by
contract — the audit exists so that a diagnosis carrying no derivation can
still be held — so the program a site would be found in is not there to
look in, and that was written down beside the ref as the reason rather
than as a place the check still had to go.

MEASURED FIRST. On three corpus rows, bending the cited site to
``program:confounder_pattern:_forged`` and to a variable the problem does
not declare passed ``verify``, ``verify_answer_claims`` and
``verify_data_gap_report``, in every direction tried. The census now
counts 88 slices of it, having counted ten while it asked one ref per row.

SEVEN SPELLINGS, THREE QUESTIONS. A site names an EDGE and the annotation
it carries, or a VARIABLE and a field of its declaration, or a place under
the program's own extensions. And two name no site at all but a SHAPE the
program is in — one saying it declares an unmeasured confounder and one
saying it declares none — which are two sides of a single question about
the same statements, answered by counting them. Measured on the corpus
before it was written that way: every ``front_door_pattern`` row declares
at least one bidirected edge and every ``no_bidirected`` row declares
none, in 78 occurrences with no exception.

AND AN UNKNOWN SPELLING IS REFUSED. A ref nothing can follow is the state
this rule exists to end, so letting one through in silence would rebuild
it one spelling at a time.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.data_gap_rules import (
    _NOT_A_PROGRAM_SITE_AT_ALL,
    _resolve_program_site,
    verify_gap_program_sites,
)
from themis.verifier.errors import VerificationError

CORPUS = pathlib.Path(__file__).resolve().parent / "fixtures" / (
    "answer_shapes.json")


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _results(envelope):
    return envelope.get("results") or [envelope]


def _gaps(result):
    return (result.get("data_gap_report") or {}).get("gaps") or []


def _sites(envelope):
    for result in _results(envelope):
        for gap_index, gap in enumerate(_gaps(result)):
            for ref_index, ref in enumerate(gap.get("provenance") or []):
                if ref.get("ref_kind") == "program_site":
                    yield result, gap_index, ref_index, ref.get("ref_id")


def _an_edge(kind, one, other, *, source=True):
    ends = ("from", "to") if kind == "cause" else ("left", "right")
    atom = lambda p: {"predicate": p, "args": [{"type": "const", "name": "u"}]}
    statement = {"kind": kind, ends[0]: atom(one), ends[1]: atom(other)}
    if source:
        statement["annotations"] = {"source": "llm_proposal"}
    return statement


def _program(*statements, extensions=None):
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            *statements,
        ],
    }
    if extensions is not None:
        program["extensions"] = extensions
    return program


# --- the honest side, on every ref the corpus actually carries -------------


def test_every_cited_site_in_the_corpus_is_a_site_its_problem_has(corpus):
    """The first thing a rule that refuses has to earn. 130 refs across the
    corpus, and a spelling this resolver cannot follow is a false refusal
    of an honest report — the one failure worse than the hole."""
    resolved, exempt, refused = 0, 0, []
    for name, row in sorted(corpus.items()):
        for _result, _gi, _ri, ref_id in _sites(row["result"]):
            if str(ref_id).startswith(_NOT_A_PROGRAM_SITE_AT_ALL):
                exempt += 1
                continue
            found, why = _resolve_program_site(row["program"], ref_id)
            if found:
                resolved += 1
            else:
                refused.append((name, ref_id, why))
    assert refused == []
    assert (resolved, exempt) == (130, 1)


def test_the_one_cited_place_that_is_not_a_place_is_named_and_explained():
    """The exemption, stated rather than left as a hole. A dispatch
    conflict names which layer answered and which was skipped, which is a
    fact about the run and not about the problem — following it into the
    program is impossible and refusing it would refuse an honest answer.
    What is wrong there is the ref's KIND, and a kind is contract."""
    assert _NOT_A_PROGRAM_SITE_AT_ALL == "query:"
    found, _ = _resolve_program_site(
        _program(), "query:dispatch_conflict:a_dispatched_b_skipped")
    assert not found


# --- the two sides of one question about the same statements --------------


def test_a_graph_said_to_have_no_unmeasured_confounder_may_not_have_one():
    clean = _program()
    assert _resolve_program_site(
        clean, "program:confounder_pattern:no_bidirected")[0]
    confounded = _program(_an_edge("bidirected", "x", "y"))
    found, why = _resolve_program_site(
        confounded, "program:confounder_pattern:no_bidirected")
    assert not found
    assert "bidirected" in why


def test_a_front_door_reading_needs_the_confounding_it_reads_around():
    confounded = _program(_an_edge("bidirected", "x", "y"))
    assert _resolve_program_site(confounded, "program:front_door_pattern")[0]
    found, why = _resolve_program_site(
        _program(), "program:front_door_pattern")
    assert not found
    assert "no bidirected edge" in why


def test_the_two_patterns_are_one_question_asked_both_ways(corpus):
    """Why they are answered by counting rather than by two readings. On
    the corpus, every row citing the front-door pattern declares at least
    one bidirected edge and every row citing no-confounding declares
    none — 78 occurrences, no exception."""
    tally = {"program:front_door_pattern": [],
             "program:confounder_pattern:no_bidirected": []}
    for row in corpus.values():
        declared = sum(1 for s in row["program"].get("statements") or ()
                       if s.get("kind") == "bidirected")
        for _r, _gi, _ri, ref_id in _sites(row["result"]):
            if ref_id in tally:
                tally[ref_id].append(declared)
    assert len(tally["program:front_door_pattern"]) == 11
    assert all(n >= 1 for n in tally["program:front_door_pattern"])
    assert len(tally["program:confounder_pattern:no_bidirected"]) == 67
    assert set(tally["program:confounder_pattern:no_bidirected"]) == {0}


# --- an edge, and the annotation the ref says it carries ------------------


def test_an_edge_site_needs_the_edge_and_the_annotation_on_it():
    with_source = _program(_an_edge("cause", "x", "y"))
    ref = "program:cause:x->y:annotations.source"
    assert _resolve_program_site(with_source, ref)[0]

    without = _program(_an_edge("cause", "x", "y", source=False))
    found, why = _resolve_program_site(without, ref)
    assert not found and "annotations.source" in why

    elsewhere = _program(_an_edge("cause", "y", "x"))
    found, why = _resolve_program_site(elsewhere, ref)
    assert not found and "no cause edge" in why


def test_a_pair_is_the_same_pair_written_the_other_way_round():
    """The acceptance a direction-blind reading owes. A bidirected edge is
    a pair rather than an arrow, so a ref that spells its ends in the
    other order names the same statement; a DIRECTED edge does not get
    that, and the row above shows it refused."""
    program = _program(_an_edge("bidirected", "y", "x"))
    assert _resolve_program_site(
        program, "program:bidirected:x↔y:annotations.source")[0]
    found, _ = _resolve_program_site(
        program, "program:bidirected:x↔z:annotations.source")
    assert not found


# --- a variable, and a field of its declaration ---------------------------


def test_a_variable_site_reads_the_declaration_it_names():
    program = _program()
    program["statements"][0]["measurement"] = "self-report survey"
    ref = "program:variable:x:measurement:contains:self-report"
    assert _resolve_program_site(program, ref)[0]

    found, why = _resolve_program_site(
        program, "program:variable:x:measurement:contains:register")
    assert not found and "measurement" in why

    found, why = _resolve_program_site(
        program, "program:variable:nobody:measurement:contains:self-report")
    assert not found and "no variable" in why


def test_a_threshold_site_is_the_cut_the_declaration_states():
    program = _program()
    program["statements"][0]["threshold"] = ">=3cm"
    assert _resolve_program_site(
        program, "program:variable:x:threshold:>=3cm")[0]
    found, why = _resolve_program_site(
        program, "program:variable:x:threshold:>=4cm")
    assert not found and "threshold" in why


# --- a place under the program's own extensions ---------------------------


def test_an_extensions_site_follows_keys_and_then_a_members_kind():
    program = _program(extensions={
        "ambiguities": [{"kind": "dose_response_query", "description": "..."}],
        "discovery_metadata": {"algorithm": "pc"},
    })
    assert _resolve_program_site(
        program, "program:extensions.discovery_metadata")[0]
    assert _resolve_program_site(
        program, "program:extensions.ambiguities.dose_response_query")[0]

    found, why = _resolve_program_site(
        program, "program:extensions.ambiguities.transport_query")
    assert not found and "kind" in why
    found, why = _resolve_program_site(
        program, "program:extensions.nothing_here")
    assert not found


# --- and the spelling nobody declared -------------------------------------


def test_a_spelling_this_resolver_does_not_know_is_refused():
    """What closes the set. A ref nothing can follow is the state this
    rule exists to end, and a resolver that passed the ones it did not
    recognise would rebuild it one spelling at a time."""
    found, why = _resolve_program_site(
        _program(), "program:confounder_pattern:_forged")
    assert not found
    assert "spelled" in why


# --- reached through the doors a caller uses ------------------------------


def test_the_refusal_is_reached_through_the_doors_a_caller_uses(corpus):
    row = corpus["backdoor_linear"]
    forged = copy.deepcopy(row["result"])
    bent = False
    for result in _results(forged):
        for gap in _gaps(result):
            for ref in gap.get("provenance") or []:
                if ref.get("ref_kind") == "program_site":
                    ref["ref_id"] = "program:variable:nobody:threshold:>=1"
                    bent = True
    assert bent
    with pytest.raises(VerificationError) as caught:
        themis.verify(row["program"], forged)
    assert caught.value.rule == "data_gap_provenance_check"
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(row["program"], forged)
    themis.verify(row["program"], row["result"])


def test_a_program_this_rule_cannot_read_is_refused_not_skipped(corpus):
    """The first draft of this rule was wired to the typed program the
    kernel parses and returned quietly on it, so every forgery above
    passed while the rule looked wired. A rule that returns on an
    argument it does not recognise reads exactly like a rule that ran."""
    row = corpus["backdoor_linear"]
    with pytest.raises(TypeError):
        verify_gap_program_sites(row["result"], object())
