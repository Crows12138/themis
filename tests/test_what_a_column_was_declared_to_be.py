"""What a column was declared to be, and who says so.

The pre-flight diagnostic reconciles a variable's declared measurement type
against the column that arrived, and records the evidence so the verdict can
be re-derived without the data. The re-derivation has been there since the
block was: it recomputes the observed scale from the cardinality and the
dtype, recomputes the verdict from that, and matches the gaps against it.

Everything it recomputes, it recomputes FROM the declared scale and the
declared domain. Those two fields are therefore premises of the audit and
not results of it — a verdict re-derived from a rewritten declaration
agrees with the rewritten declaration, exactly as it agreed with the real
one. Measured before this file: 219 of the leaves under the block could be
rewritten and the rule said yes, and the declaration was 105 of them.

The declaration is the program's. ``verify_declared_types`` asks it there,
which is the one side an answer cannot edit, and the two fields stop being
premises. What the rule cannot ask of the program it asks of the envelope:
the sentence the block carries about a column is a rendering, and its
producer says in as many words which entry it is a rendering of; a column
cannot hold more distinct values than the run held rows; and the recorded
value set is a set, in the order it was sorted into, of the type its own
dtype family reads out as.

Two fields stay open and are named here rather than left to be discovered.
``dtype_kind`` is an observation with no second record anywhere on the
envelope and no authority off it — the program declares what a variable
means, never how pandas stored it — and every bend of it the sweep makes is
to another member of its own vocabulary. A value inside ``observed_values``
swapped for another value of the same type is the same case one level down:
the column's contents are recorded once. Both are the honest shape of "not
knowable here", and a rule that refused them would be inventing an
authority rather than reading one.

The relations are measured here before the rule leans on them, since a
relation nobody measured is a false refusal waiting for the shape that
disobeys it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import gaps as _gaps
from themis.kernel import _premises_of
from themis.verifier.errors import VerificationError
from themis.verifier.type_reconciliation_rules import (
    _DISCRETE_DTYPES, _DTYPE_FIXES_NOTHING, _VALUE_TYPE_BY_DTYPE,
    verify_declared_types, verify_type_reconciliation)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[1] / "themis" / "schemas"
     / "query_result.schema.json").read_text(encoding="utf-8"))

#: Every answer shape carrying a reconciliation block, with the program it
#: was produced from.
BLOCKS = [
    (name, pair, _premises_of(pair["program"], pair["result"])[1])
    for name, pair in sorted(SHAPES.items())
    if ((pair["result"].get("extensions") or {}).get("type_reconciliation"))
]

#: (answer, program, check) for each column reconciled.
CHECKS = [
    (name, program, check)
    for name, pair, program in BLOCKS
    for check in pair["result"]["extensions"]["type_reconciliation"]["checks"]
]


def _declared(program) -> dict:
    from themis.verifier.investigation_rules import declarations_of
    return declarations_of(program)


def _of(name: str) -> dict:
    return copy.deepcopy(dict(SHAPES[name]["result"]))


def _checks_of(result: dict) -> list:
    return result["extensions"]["type_reconciliation"]["checks"]


def _both_doors(result: dict, program) -> None:
    verify_type_reconciliation(result)
    verify_declared_types(result, program)


# ------------------------------------------------- the facts this rests on


def test_the_corpus_reconciles_columns():
    """Stated so a narrowing shows up as a failure, not as a quiet pass."""
    assert (len(BLOCKS), len(CHECKS)) == (21, 36), (len(BLOCKS), len(CHECKS))


def test_every_reconciled_column_is_one_the_program_declares():
    for name, program, check in CHECKS:
        assert check["predicate"] in _declared(program), (name, check)


def test_the_recorded_domain_is_the_declaration_word_for_word():
    present = absent = 0
    for name, program, check in CHECKS:
        statement = _declared(program)[check["predicate"]]
        if statement.domain is None:
            assert check["declared_domain"] is None, (name, check)
            absent += 1
        else:
            assert check["declared_domain"] == list(statement.domain), name
            present += 1
    assert (present, absent) == (34, 2), (present, absent)


def test_the_recorded_scale_is_what_the_declaration_resolves_to():
    """Two ways a declaration reaches a positive type, and both are here.

    A ``scale`` said outright wins; otherwise the enumerated levels imply
    binary or discrete by their number. Both arms are exercised, which is
    what makes the second transcription worth having — a rule tested only
    on the arm that copies a field would not notice the other.
    """
    spoken = implied = 0
    for name, program, check in CHECKS:
        statement = _declared(program)[check["predicate"]]
        if statement.scale in ("binary", "discrete", "continuous", "nominal"):
            assert check["declared_scale"] == statement.scale, name
            spoken += 1
        else:
            assert statement.domain is not None, name
            assert check["declared_scale"] == (
                "binary" if len(statement.domain) <= 2 else "discrete"), name
            implied += 1
    assert (spoken, implied) == (4, 32), (spoken, implied)


def test_the_sentence_is_the_statement_on_the_gap_beside_it():
    checked = 0
    for name, pair, _program in BLOCKS:
        result = pair["result"]
        gaps = {
            reference["ref_id"]: gap
            for gap in (result.get("data_gap_report") or {}).get("gaps") or ()
            for reference in gap.get("provenance") or ()
            if str(reference.get("ref_id", "")).startswith(
                "type_reconciliation:")
        }
        for check in _checks_of(result):
            gap = gaps[f"type_reconciliation:{check['predicate']}"]
            assert check["detail"] == _gaps.describe(gap["describes"][0]), name
            checked += 1
    assert checked == 36, checked


def test_a_column_holds_no_more_values_than_the_run_held_rows():
    """And how many have no room at all, which is where the bend bites."""
    tight = 0
    for name, pair, _program in BLOCKS:
        rows = pair["result"]["estimation_context"]["sample_size"]
        for check in _checks_of(pair["result"]):
            assert check["n_unique"] <= rows, (name, check)
            tight += check["n_unique"] == rows
    assert tight == 31, tight


def test_the_recorded_values_are_a_sorted_set_of_their_own_type():
    lists = values = 0
    for name, _program, check in CHECKS:
        recorded = check["observed_values"]
        if recorded is None:
            continue
        lists += 1
        assert sorted(recorded) == recorded, (name, recorded)
        assert len({(type(v).__name__, v) for v in recorded}) == len(recorded)
        wanted = _VALUE_TYPE_BY_DTYPE[check["dtype_kind"]]
        for value in recorded:
            assert type(value) is wanted, (name, value, check["dtype_kind"])
            values += 1
    assert (lists, values) == (5, 13), (lists, values)


# ------------------------------------------- the table against its own space


def test_what_a_dtype_family_reads_out_as_covers_the_vocabulary():
    """Both directions, so an omission cannot be silent.

    A partial map goes wrong by never matching, which looks exactly like a
    deliberate silence. The families that fix a type and the families that
    fix nothing are therefore written down separately and both held here
    against the closed vocabulary the envelope schema declares — the same
    arrangement ``answers.SHAPES_OF`` and ``blocks`` already use. A family
    added to the schema fails this test rather than quietly joining the
    ones this rule says nothing about.
    """
    declared = set(
        SCHEMA["properties"]["extensions"]["properties"]["type_reconciliation"]
        ["properties"]["checks"]["items"]["properties"]["dtype_kind"]["enum"])
    assert set(_VALUE_TYPE_BY_DTYPE) | _DTYPE_FIXES_NOTHING == declared
    assert not (set(_VALUE_TYPE_BY_DTYPE) & _DTYPE_FIXES_NOTHING)
    assert _DISCRETE_DTYPES <= declared


# --------------------------------------------------------- honest and silent


BLOCKS_BY_NAME = {name: program for name, _pair, program in BLOCKS}


@pytest.mark.parametrize("name", sorted(BLOCKS_BY_NAME))
def test_every_honest_answer_goes_through(name):
    _both_doors(_of(name), BLOCKS_BY_NAME[name])


def test_an_answer_without_the_block_is_not_this_rules_business():
    name, _pair, program = BLOCKS[0]
    result = _of(name)
    del result["extensions"]["type_reconciliation"]
    _both_doors(result, program)
    verify_declared_types({}, program)


# -------------------------------------------------------------------- teeth


def test_a_domain_the_program_did_not_declare_is_refused():
    refused = 0
    for name, program, check in CHECKS:
        if check["declared_domain"] is None:
            continue
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["declared_domain"] = list(check["declared_domain"]) \
                    + ["invented"]
        with pytest.raises(VerificationError):
            verify_declared_types(result, program)
        refused += 1
    assert refused == 34, refused


def test_a_scale_the_program_did_not_declare_is_refused():
    refused = 0
    for name, program, check in CHECKS:
        other = "continuous" if check["declared_scale"] != "continuous" \
            else "binary"
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["declared_scale"] = other
        with pytest.raises(VerificationError):
            verify_declared_types(result, program)
        refused += 1
    assert refused == 36, refused


def test_a_column_the_program_never_heard_of_is_refused():
    refused = 0
    for name, program, check in CHECKS:
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["predicate"] = "a_column_nobody_declared"
        with pytest.raises(VerificationError):
            verify_declared_types(result, program)
        refused += 1
    assert refused == 36, refused


def test_a_sentence_that_is_not_the_statement_beside_it_is_refused():
    refused = 0
    for name, _program, check in CHECKS:
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["detail"] = recorded["detail"] + "，而且更严重"
        with pytest.raises(VerificationError):
            verify_type_reconciliation(result)
        refused += 1
    assert refused == 36, refused


def test_more_distinct_values_than_rows_is_refused():
    """And on the checks where nothing else would have noticed.

    A cardinality raised far enough changes what the column classifies as,
    and the classification is re-derived already — so counting refusals
    would count the old rule's. What is new is a count raised by one, which
    every other check agrees with and no frame can hold.
    """
    refused = by_the_count = 0
    for name, _program, check in CHECKS:
        result = _of(name)
        rows = result["estimation_context"]["sample_size"]
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["n_unique"] = rows + 1
        with pytest.raises(VerificationError) as caught:
            verify_type_reconciliation(result)
        refused += 1
        by_the_count += "rows" in str(caught.value)
    assert (refused, by_the_count) == (36, 31), (refused, by_the_count)


def test_a_repeated_value_in_the_distinct_values_is_refused():
    refused = 0
    for name, _program, check in CHECKS:
        if not check["observed_values"]:
            continue
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                values = list(recorded["observed_values"])
                values[-1] = values[0]
                recorded["observed_values"] = values
        with pytest.raises(VerificationError):
            verify_type_reconciliation(result)
        refused += 1
    assert refused == 5, refused


def test_a_value_set_out_of_order_is_refused():
    refused = 0
    for name, _program, check in CHECKS:
        if not check["observed_values"]:
            continue
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                recorded["observed_values"] = list(
                    reversed(recorded["observed_values"]))
        with pytest.raises(VerificationError):
            verify_type_reconciliation(result)
        refused += 1
    assert refused == 5, refused


def test_a_value_of_a_type_the_column_cannot_hold_is_refused():
    refused = 0
    for name, _program, check in CHECKS:
        if not check["observed_values"]:
            continue
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                values = list(recorded["observed_values"])
                values[0] = "a label"
                recorded["observed_values"] = values
        with pytest.raises(VerificationError):
            verify_type_reconciliation(result)
        refused += 1
    assert refused == 5, refused


# --------------------------------------------------- and what stays open


def test_the_dtype_family_has_no_second_record_and_is_not_pretended_to():
    """The sweep's own bends of it, accepted, on the checks where they are
    consistent with everything else the block records.

    Accepting is the pin. What decides a column's dtype is neither on the
    envelope twice nor declared by the program, so the alternative to
    accepting is a rule with an invented authority — and a false refusal is
    worse than the hole it closes. Where the block records the VALUES, the
    family does have a second record and a bend of it is refused; this is
    the complement of that.
    """
    accepted = 0
    for name, program, check in CHECKS:
        if check["observed_values"] is not None:
            continue
        if check["n_unique"] <= 20:
            continue  # the classification would notice
        for family in ("integer", "bool", "categorical"):
            if family == check["dtype_kind"]:
                continue
            result = _of(name)
            for recorded in _checks_of(result):
                if recorded["predicate"] == check["predicate"]:
                    recorded["dtype_kind"] = family
            _both_doors(result, program)
            accepted += 1
    assert accepted == 93, accepted


def test_a_value_swapped_for_another_of_its_type_is_accepted():
    """The same shape one level down, and stated for the same reason."""
    accepted = 0
    for name, program, check in CHECKS:
        recorded_values = check["observed_values"]
        if not recorded_values or check["dtype_kind"] == "bool":
            continue
        result = _of(name)
        for recorded in _checks_of(result):
            if recorded["predicate"] == check["predicate"]:
                values = list(recorded["observed_values"])
                values[-1] = type(values[-1])(97)
                recorded["observed_values"] = values
        _both_doors(result, program)
        accepted += 1
    assert accepted == 4, accepted
