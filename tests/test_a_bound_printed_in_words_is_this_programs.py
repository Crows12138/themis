"""A bound printed in words is still this program's bound.

``bounds_results[].lower_expression`` holds two kinds of thing. For the
two methods with a closed form it holds a formula, and the verifier
rebuilds that formula out of the query and compares it character for
character. Balke-Pearl has no closed form to print -- the bound is the
optimum of a linear programme -- so that branch prints the programme in
words, and the audit held the words to naming what they render: the
target predicate appears, one ``do(X=`` appears, the instrument appears.
Wording was the producer's.

Which left one field with one treatment per method, and the difference
was not a property of the field. Everything the sentence renders is a
fact the rule holds anyway -- the arm and the observables from the query,
the instrument from its own field, and the size of the response-function
partition from the cardinalities the PROGRAM declares. So the sentence is
a rendering this program determines, and it is rebuilt here.

Three things a forged sentence could do, and nothing refused. It could
print a partition of a different size from the one the note beside it
carries. It could call a lower bound a maximum: the direction was left
unaudited on the argument that looking for the operator word refuses any
programme whose predicates contain it, and ``vitamin`` contains ``min``
-- which is true of looking for the word and not of building the sentence
that contains it. And it could gain a word, which is not idle: the
vocabulary a rendered claim elsewhere on the row may draw on is built out
of these two strings, BECAUSE they are re-derived, which was true of two
methods out of three.

The count is re-derived; the producer's ceiling is not. Whether a row is
OFFERED at all is a build's decision, and reading its constant back here
would be agreeing with it by construction. What stops the multiplication
instead is the length of the expression being audited: a count with more
digits than that sentence has characters is not the count that sentence
prints.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for, verify_honestly
from themis.input.semantic_validator import validate_program
from themis.runtime.scheduler import _declared_level_count
from themis.verifier import bounds_rules as _bounds_rules
from themis.verifier.bounds_account_rules import verify_bounds_account
from themis.verifier.bounds_rules import (
    _verifier_declared_level_count,
    _verifier_response_type_count,
    verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))

METHOD = "balke_pearl_iv"


def _query_of(pair):
    """The query this answer is about, the way the kernel locates it."""
    program = pair["program"]
    wanted = pair["result"].get("query_id")
    queries = [s for s in program["statements"] if s.get("kind") == "query"]
    for stmt in queries:
        if stmt.get("id") == wanted:
            return stmt["query"]
    return queries[0]["query"]


def _rows():
    for name in sorted(SHAPES):
        pair = SHAPES[name]
        for row in pair["result"].get("bounds_results") or ():
            if row.get("method") == METHOD:
                yield name, pair, row


ROWS = tuple(_rows())
CARRYING = tuple(sorted({name for name, _, _ in ROWS}))

#: Each lie, as a rewriting of one expression. The first two are the
#: sweep's own -- append and empty -- and the rest are the ones the old
#: mention-checks were shaped to let through.
LIES = {
    "a word appended": lambda s: s + " and pancreas",
    "nothing at all": lambda s: "",
    "a partition of another size": lambda s: s.replace(
        " response types", "00 response types"),
    "a lower bound called a maximum": lambda s: s.replace("min of", "max of"),
    "the instrument dropped": lambda s: s.split(" over ")[0],
}

#: Only the pairs where the lie is one. ``min of`` is not in the upper
#: expression and the count is not in it either, so applying those there
#: rewrites nothing -- and a case that bends nothing is not a bend the
#: total should count.
SWEEP = tuple(
    (name, key, lie)
    for name, _pair, row in ROWS
    for key in ("lower_expression", "upper_expression")
    for lie in LIES
    if LIES[lie](row[key]) != row[key]
)


# --------------------------------------------------------------- the census


def test_the_corpus_carries_what_this_file_is_about():
    """One field, three methods -- and the count of each, so that a row
    leaving the corpus is a failure here rather than a quiet thinning of
    what this file sweeps."""
    counts: dict[str, int] = {}
    for pair in SHAPES.values():
        for row in pair["result"].get("bounds_results") or ():
            counts[row.get("method")] = counts.get(row.get("method"), 0) + 1
    assert counts == {
        "manski_natural": 83,
        METHOD: 9,
        "manski_tamer_monotonicity": 6,
    }
    assert len(ROWS) == 9
    assert len(CARRYING) == 9
    for _name, _pair, row in ROWS:
        assert row.get("lower_expression")
        assert row.get("upper_expression")


def test_one_of_them_is_not_binary():
    """The rebuild is of the general partition, not of the 2x2x2 one.

    ``|X|^|Z| * |Y|^|X|`` is 16 wherever everything is binary, and 16 is
    also what several wrong readings of it give. One answer here declares
    a four-level treatment, so its 256 is a count only the right reading
    produces.
    """
    sizes = set()
    for _name, pair, row in ROWS:
        query = _query_of(pair)
        sizes.add((
            _verifier_declared_level_count(
                pair["program"], query["intervention"]["atom"]["predicate"],
                query["intervention"]["value"]),
            _verifier_declared_level_count(
                pair["program"], query["target"]["atom"]["predicate"],
                query["target"]["value"]),
            _verifier_declared_level_count(
                pair["program"], row["instrument"], None),
        ))
    assert (4, 2, 2) in sizes
    assert (2, 2, 2) in sizes


# ------------------------------------------------------- the honest direction


@pytest.mark.parametrize("name", CARRYING)
def test_every_stored_answer_still_passes(name):
    """Nine rows through the strongest door that reads them, unchanged.

    An equality refuses everything it does not predict, so the first
    thing it has to be is right about every answer this repository has
    collected.
    """
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


@pytest.mark.parametrize("name,key,lie", SWEEP,
                         ids=[f"{n}:{k[:5]}:{l}" for n, k, l in SWEEP])
def test_a_bent_expression_is_refused(name, key, lie):
    pair = SHAPES[name]
    forged = copy.deepcopy(pair["result"])
    bent = False
    for row in forged["bounds_results"]:
        if row.get("method") != METHOD:
            continue
        new = LIES[lie](row[key])
        if new != row[key]:
            row[key] = new
            bent = True
    assert bent, f"{lie} rewrote nothing on {name}.{key}"
    door = the_door_for(forged)
    with pytest.raises(Exception):
        door(pair["program"], forged)


# ------------------------------------------- what the rebuild replaced


def test_the_mention_checks_it_replaced_are_gone():
    """Two judgements on one question is one judgement and a decoration.

    Every sentence the mention-checks accepted that the equality refuses
    is a sentence the weaker one would have gone on accepting, since it
    ran first.
    """
    source = inspect.getsource(verify_balke_pearl_iv_bounds_result)
    for gone in ("expression must reference ",
                 "brackets a difference between arms",
                 "expression must name the "):
        assert gone not in source, gone
    assert "lower_expression mismatch" in source
    assert "upper_expression mismatch" in source


def test_the_count_is_derived_and_the_ceiling_is_not_read_back():
    """The producer's cap decides whether a row is OFFERED, which is a
    different question from what this row says, and it is a build's
    number with no second witness on the row."""
    source = inspect.getsource(_bounds_rules)
    assert "MAX_RESPONSE_TYPES" not in source
    assert "10_000" not in source and "10000" not in source


def test_what_stops_the_multiplication_is_the_sentence_being_audited():
    """A budget taken from the row, not a size this module chose.

    Small enough and the count is exact; past what the sentence could be
    printing and there is no count to compare, which is a refusal and not
    an accept.
    """
    assert _verifier_response_type_count(2, 2, 2, digits=8) == 16
    assert _verifier_response_type_count(4, 2, 2, digits=8) == 256
    # 16 is two digits, so two digits of budget still hold it and one
    # does not: the boundary is the number's own length.
    assert _verifier_response_type_count(2, 2, 2, digits=2) == 16
    assert _verifier_response_type_count(2, 2, 2, digits=1) is None
    assert _verifier_response_type_count(500, 500, 500, digits=120) is None


def test_the_second_reader_of_the_program_reads_what_the_first_read():
    """The cardinalities come from the program twice, by two readers.

    The producer counts them off the parsed statements; this module
    counts them off the same statements as JSON, because it may not
    import the producer. A rebuild whose count came from the producer
    would agree by construction, and one whose count disagreed would
    refuse honest rows -- so the identity is the pin.
    """
    seen = 0
    for text in {json.dumps(p["program"], sort_keys=True)
                 for p in SHAPES.values()}:
        raw = json.loads(text)
        parsed = validate_program(raw)
        for stmt in raw["statements"]:
            if stmt.get("kind") != "variable":
                continue
            predicate = stmt["predicate"]
            for value in (None, True):
                assert (_verifier_declared_level_count(raw, predicate, value)
                        == _declared_level_count(parsed, predicate, value)), (
                    predicate, value)
                seen += 1
    assert seen > 100


# ------------------------------------------ what the loose sentence licensed


def test_a_forged_sentence_no_longer_licenses_a_forged_data_request():
    """The consequence that was not on this row.

    :func:`themis.verifier.bounds_account_rules._words_this_row_already_uses`
    builds the vocabulary a rendered claim may draw on out of the two
    expressions, and says why: they "are themselves re-derived". That was
    true of two methods out of three, so a word appended to this one's
    sentence was a word a ``data_required`` entry could then send a reader
    to go and collect.
    """
    name = next(n for n, _pair, _row in ROWS
                if not SHAPES[n]["result"]["bounds_results"][0].get(
                    "numeric_data_columns"))
    pair = SHAPES[name]
    query = _query_of(pair)
    row = copy.deepcopy(next(r for r in pair["result"]["bounds_results"]
                             if r["method"] == METHOD))

    verify_bounds_account(row, program=pair["program"], query_dict=query)
    verify_balke_pearl_iv_bounds_result(
        row, program=pair["program"], query_dict=query)

    row["lower_expression"] = row["lower_expression"] + " and pancreas"
    said = row["data_required"][0]["said"]
    said["expression"] = said["expression"].replace("|", "| pancreas,")
    # The account door still accepts it -- the licence is real, and it is
    # the sentence that grants it.
    verify_bounds_account(row, program=pair["program"], query_dict=query)
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_balke_pearl_iv_bounds_result(
            row, program=pair["program"], query_dict=query)


def test_a_row_the_program_declares_no_domain_for_is_refused():
    """A row exists only where the producer read three cardinalities off
    the program, so one whose instrument has no domain is a row this
    program cannot have produced -- refused, rather than audited less."""
    name = CARRYING[0]
    pair = SHAPES[name]
    query = _query_of(pair)
    row = next(r for r in pair["result"]["bounds_results"]
               if r["method"] == METHOD)
    program = copy.deepcopy(pair["program"])
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" \
                and stmt.get("predicate") == row["instrument"]:
            stmt.pop("domain", None)
    with pytest.raises(VerificationError, match="no domain of at least two"):
        verify_balke_pearl_iv_bounds_result(
            row, program=program, query_dict=query)


def test_the_note_beside_it_and_the_sentence_now_say_one_number():
    """The size of the partition is on the row twice, and they agreed
    only because nobody had made them."""
    name, pair, row = next(
        (n, p, r) for n, p, r in ROWS if r.get("notes"))
    said = row["notes"][0]["said"]
    assert said["types"] in row["lower_expression"]
    forged = copy.deepcopy(row)
    forged["lower_expression"] = forged["lower_expression"].replace(
        f"{said['types']} response types", "3 response types")
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_balke_pearl_iv_bounds_result(
            forged, program=pair["program"], query_dict=_query_of(pair))
