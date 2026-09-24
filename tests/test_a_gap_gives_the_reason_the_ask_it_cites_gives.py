"""A gap's reason and the ask it points at are one sentence.

A gap that came of an investigation request shows the reader a reason for
itself, and the request that asked for the same thing states that reason
too. One sentence, written into two documents by one run — and the two
documents spell its word differently, ``token`` on the gap and ``need`` on
the ask, which is the whole of why no reading of values ever paired them.

Nothing had asked. T10-1 resolves the ref, so which request a gap is about
was already held; T10-8 holds which sentences the gap's species may make.
What the sentence SAYS sat between them with one author, and on the stored
answers every hole of it could be moved with no door refusing: the level a
test was run at, the arm a stratum has none of, the bounds a quantity was
given.

The strictness follows the citation. An item's target names ONE statement,
so a gap citing it answers to that statement alone; a request's target
names the ask as a whole, so a gap citing it answers to carrying one of
the statements the ask is made of. Reading the first as the second was
measured and refuses two honest answers — a gap about one coefficient of a
five-coefficient ask, compared against four siblings that carry the same
need with other holes.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis.verifier import verify_a_gap_says_what_its_request_says as rule
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Answers whose gap report shows a reason for a gap that cites an ask.
#: Pinned because a rule's reach is the point: silence is what it looked
#: like before, and silence is what a rule that stops reaching looks like.
ANSWERS_EXERCISING_THIS = 35

#: Of those, the ones whose reason has holes to move. A reason with none
#: is held by its word alone, and the forgery below has nothing to do on
#: it — counted rather than skipped, so a drop in either number is seen.
ANSWERS_WHOSE_REASON_HAS_HOLES = 11


def _carriers() -> list:
    out = []
    for name, pair in SHAPES.items():
        report = pair["result"].get("data_gap_report") or {}
        requests = pair["result"].get("investigation_requests") or []
        targets = set()
        for request in requests:
            targets.add(request.get("target"))
            for item in request.get("items") or ():
                targets.add(item.get("target"))
        for gap in report.get("gaps") or ():
            cites = any(ref.get("ref_kind") == "investigation_request"
                        and ref.get("ref_id") in targets
                        for ref in gap.get("provenance") or ())
            shows = any(isinstance(d.get("words"), dict)
                        and isinstance(d["words"].get("why"), dict)
                        for d in gap.get("describes") or ())
            if cites and shows:
                out.append(name)
                break
    return sorted(out)


def _carriers_with_holes() -> list:
    return [name for name in _carriers()
            if _a_reason(SHAPES[name]["result"])[1].get("said")]


def _a_reason(result):
    """The first gap that shows a reason and cites an ask, and that reason."""
    for gap in (result.get("data_gap_report") or {}).get("gaps") or ():
        if not any(ref.get("ref_kind") == "investigation_request"
                   for ref in gap.get("provenance") or ()):
            continue
        for described in gap.get("describes") or ():
            words = described.get("words")
            if isinstance(words, dict) and isinstance(words.get("why"), dict):
                return gap, words["why"]
    raise AssertionError("no gap here shows a reason and cites an ask")


def test_the_corpus_exercises_this_rule():
    carriers = _carriers()
    assert len(carriers) == ANSWERS_EXERCISING_THIS, carriers
    with_holes = _carriers_with_holes()
    assert len(with_holes) == ANSWERS_WHOSE_REASON_HAS_HOLES, with_holes


def test_no_honest_answer_is_refused():
    """All of them, not only the carriers.

    A rule reading a block most answers do not carry has more quiet cases
    than loud ones, and a quiet case that raises is found last.
    """
    for _name, pair in SHAPES.items():
        rule(pair["result"])


@pytest.mark.parametrize("name", _carriers_with_holes())
def test_a_reason_whose_holes_were_moved_is_refused(name):
    """The forgery this exists for.

    The reason stays a sentence the species allows, filled in the way its
    own template asks, and says something the ask beside it does not.
    """
    result = copy.deepcopy(SHAPES[name]["result"])
    _gap, why = _a_reason(result)
    said = why["said"]
    key = sorted(said)[0]
    honest = said[key]
    said[key] = f"{honest}_forged" if isinstance(honest, str) else "forged"
    with pytest.raises(VerificationError, match="T10-9"):
        rule(result)


@pytest.mark.parametrize("name", _carriers())
def test_a_reason_that_is_not_the_asks_reason_is_refused(name):
    """A well-formed sentence about something nobody asked for."""
    result = copy.deepcopy(SHAPES[name]["result"])
    _gap, why = _a_reason(result)
    why["token"] = "a_need_no_ask_here_carries"
    with pytest.raises(VerificationError, match="no investigation request"):
        rule(result)


def test_what_a_reason_says_beneath_its_holes_is_part_of_it():
    """A detail under a reason has one author unless this reaches it.

    Measured: holding only the top holes leaves five leaves of the stored
    answers unheld, and they are the interval a quantity was bounded to.
    """
    name = next((n for n in _carriers()
                 if isinstance(_a_reason(SHAPES[n]["result"])[1].get("words"),
                               dict)), None)
    if name is None:
        pytest.skip("no stored reason carries a detail beneath it")
    result = copy.deepcopy(SHAPES[name]["result"])
    _gap, why = _a_reason(result)
    detail = json.dumps(why["words"])
    why["words"] = json.loads(detail.replace("0.", "9."))
    if why["words"] == json.loads(detail):
        pytest.skip("that detail carries no number to move")
    with pytest.raises(VerificationError, match="beneath it"):
        rule(result)


def test_a_gap_citing_one_item_is_not_held_to_its_siblings():
    """The precision of the question follows the precision of the citation.

    An ask can be one need filed for five things at once — five
    coefficients of one structural model — and a gap is about one of them.
    Comparing it with the other four refuses an honest answer, which is
    what reading an item's id as the whole ask's does.
    """
    request = {
        "target": "structure:2_items",
        "items": [
            {"target": "coefficient:a->b", "need": "path_coefficient",
             "said": {"parent": "a", "child": "b"}},
            {"target": "coefficient:c->b", "need": "path_coefficient",
             "said": {"parent": "c", "child": "b"}},
        ],
    }
    result = {
        "investigation_requests": [request],
        "data_gap_report": {"gaps": [{
            "kind": "missing_structural_input",
            "provenance": [{"ref_kind": "investigation_request",
                            "ref_id": "coefficient:c->b"}],
            "describes": [{"words": {"why": {
                "token": "path_coefficient",
                "said": {"parent": "c", "child": "b"}}}}],
        }]},
    }
    rule(result)

    # And the same gap citing that one item, saying the other's holes.
    other = copy.deepcopy(result)
    why = other["data_gap_report"]["gaps"][0]["describes"][0]["words"]["why"]
    why["said"] = {"parent": "a", "child": "b"}
    with pytest.raises(VerificationError, match="T10-9"):
        rule(other)


def test_an_ask_filed_under_another_species_the_report_also_carries():
    """The one thing this asks that membership cannot.

    The rule beside this one asks whether the species an ask names is one
    the report carries. Where BOTH species are carried, a swap passes it:
    the ask says it was filed for a variable-definition gap and the gap it
    points at is a structural-input one, and every word in the answer is a
    word the answer uses. What tells them apart is not membership but
    identity — this ask and this gap are one filing, or they are two.

    Written because the arm closes no leaf the gate asks about: the bends
    that gate makes never produce this, so without a case here the arm
    would be a branch with a reason and nothing to show for it.
    """
    result = {
        "investigation_requests": [{
            "target": "t1",
            "items": [{"target": "t1", "need": "n",
                       "gap": "ambiguous_variable_definition",
                       "said": {"a": "b"}}],
        }],
        "data_gap_report": {"gaps": [
            {"kind": "ambiguous_variable_definition", "provenance": [],
             "describes": []},
            {"kind": "missing_structural_input",
             "provenance": [{"ref_kind": "investigation_request",
                             "ref_id": "t1"}],
             "describes": [{"words": {"why": {
                 "token": "n", "said": {"a": "b"}}}}]},
        ]},
    }
    with pytest.raises(VerificationError, match="filed the same need as"):
        rule(result)

    # And the same answer with the two agreeing, which is the honest one.
    honest = copy.deepcopy(result)
    honest["investigation_requests"][0]["items"][0]["gap"] = (
        "missing_structural_input")
    rule(honest)


def test_a_gap_citing_the_whole_ask_carries_one_of_its_statements():
    """Where the id names the ask, any of the things it asks for will do."""
    result = {
        "investigation_requests": [{
            "target": "structure:2_items",
            "items": [
                {"target": "coefficient:a->b", "need": "path_coefficient",
                 "said": {"parent": "a", "child": "b"}},
                {"target": "coefficient:c->b", "need": "path_coefficient",
                 "said": {"parent": "c", "child": "b"}},
            ],
        }],
        "data_gap_report": {"gaps": [{
            "kind": "missing_structural_input",
            "provenance": [{"ref_kind": "investigation_request",
                            "ref_id": "structure:2_items"}],
            "describes": [{"words": {"why": {
                "token": "path_coefficient",
                "said": {"parent": "c", "child": "b"}}}}],
        }]},
    }
    rule(result)

    stranger = copy.deepcopy(result)
    shown = stranger["data_gap_report"]["gaps"][0]["describes"][0]
    why = shown["words"]["why"]
    why["said"] = {"parent": "nobody", "child": "asked"}
    with pytest.raises(VerificationError, match="T10-9"):
        rule(stranger)


def test_a_gap_citing_no_ask_is_not_this_rules_business():
    """Whether a gap OWES a citation is T10-2's question.

    Asserted rather than described: a second author for that decision is
    two answers that disagree the first time either moves.
    """
    result = {
        "investigation_requests": [{"target": "t", "items": [
            {"target": "t", "need": "n", "said": {}}]}],
        "data_gap_report": {"gaps": [{
            "kind": "missing_structural_input",
            "provenance": [{"ref_kind": "derivation_step", "ref_id": "s1"}],
            "describes": [{"words": {"why": {
                "token": "something_else_entirely", "said": {"a": "b"}}}}],
        }]},
    }
    rule(result)


def test_an_answer_with_no_report_is_nothing_to_check():
    rule({})
    rule({"investigation_requests": []})
    rule({"data_gap_report": {"gaps": []}})
