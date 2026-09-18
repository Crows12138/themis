"""One table, one row count — asked wherever the envelope writes it.

The digest rules beside this one say WHICH table an answer stands on.
This says how big it was. The run records that once, before any estimator
runs, and the point estimate, each bounds row, the outcome-error block
and every derivation step's inputs then carry their own copy.

Two rules already stated the relation, each for the one block its author
happened to be walking — ``bounds_rules`` on a Manski row and
``frame_rules`` on a fitted block, both saying "should be the row count"
in as many words. Neither can see ``estimation_context``, so the run's own
record — the number a reader is likeliest to quote a precision off — was
the copy nothing compared to anything.

Asked of the name the contract gives the whole, so that the counts spelled
one level down (``strata[].n``, a measurement channel's treated and
control halves) are never mistaken for it: those are parts of the table
rather than the table, and a walk that took every count would have to
guess which it had.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis import audits
from themis.verifier.errors import VerificationError
from themis.verifier.fingerprint_rules import _row_counts, verify_one_row_count

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES
    if (SHAPES[n]["result"].get("estimation_context") or {}).get("sample_size")
    is not None)


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


# ------------------------------------------------- the fact this rests on


def test_every_copy_of_the_count_already_agrees():
    """The measurement the rule rests on, kept where it can go stale."""
    agree = total = 0
    for name in CARRIERS:
        counts = _row_counts(SHAPES[name]["result"])
        run_wide = (SHAPES[name]["result"]["estimation_context"]
                    ["sample_size"])
        total += len(counts)
        agree += sum(1 for _, v in counts if v == run_wide)
    # 4 fewer copies: four refreshed answers no longer carry a numeric
    # Balke-Pearl interval around a node that is not an instrument with
    # nothing conditioned, and each such row wrote its own.
    assert (agree, total) == (340, 340)


def test_the_count_is_written_in_more_than_one_block():
    """A rule comparing copies is worth nothing if there is only one.

    Six blocks now, and the sixth arrived without the walk being touched:
    a confidence region under ``extensions`` records the table it was
    inverted from, and the rule finds it because it asks for the name the
    contract gives the whole rather than for a list of places.
    """
    blocks = {
        path.split("/")[1]
        for name in CARRIERS
        for path, _ in _row_counts(SHAPES[name]["result"])
    }
    assert blocks == {
        "estimation_context", "numeric_estimate", "derivation",
        "bounds_results", "outcome_error", "extensions",
    }, sorted(blocks)


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        verify_honestly(*_pair(name))


# ------------------------------------------------------------- the gate


@pytest.mark.parametrize("bend", [lambda v: v + 7, lambda v: 0,
                                  lambda v: v * 2 + 1])
def test_a_run_that_misreports_how_many_rows_arrived(bend):
    """The leaf this frontier was opened on: the run's own record.

    A negative count is not among these because the contract already
    refuses one (``minimum: 0``) before any rule is reached — a bend that
    never gets here is not a bend this gate has to answer for.
    """
    program, result = _pair("backdoor_linear")
    context = result["estimation_context"]
    context["sample_size"] = bend(context["sample_size"])
    with pytest.raises(VerificationError, match="rows"):
        themis.verify(program, result)


def test_a_negative_count_is_refused_before_any_rule_sees_it():
    """Stated so that removing the bound from the contract is a failure
    here rather than a hole this rule silently inherits."""
    from themis.input.syntactic_validator import SyntacticError

    program, result = _pair("backdoor_linear")
    result["estimation_context"]["sample_size"] = -1
    with pytest.raises(SyntacticError, match="minimum"):
        themis.verify(program, result)


def test_a_block_that_reports_a_different_table_s_size():
    """The other direction: a copy edited away from the run's record.

    Through this rule's own door, because the full door refuses it one
    rule earlier — ``verify_numeric_display_agrees`` compares the point
    estimate with the derivation's terminal step, which is why this leaf
    was already held and the run's own record was not.
    """
    _, result = _pair("backdoor_linear")
    result["numeric_estimate"]["sample_size"] += 7
    with pytest.raises(VerificationError, match="rows"):
        verify_one_row_count(result)


def test_the_public_door_asks_the_same_question():
    """A surface audited only by the door that names it is one a caller
    has to know to ask for; ``bind_rerun`` exists to make that impossible,
    and this is the half of it a test can see."""
    program, result = _pair("backdoor_linear")
    themis.verify_one_row_count(result)
    result["estimation_context"]["sample_size"] += 7
    with pytest.raises(VerificationError, match="rows"):
        themis.verify_one_row_count(result)
    del program


def test_the_audit_says_what_it_is_an_audit_of():
    _, result = _pair("backdoor_linear")
    named = {row.name for row in audits.applicable(result)}
    assert "verify_one_row_count" in named
    rows = audits.audit(SHAPES["backdoor_linear"]["program"], result)
    assert {r["audit"]: r["ok"] for r in rows}["verify_one_row_count"]


# ------------------------------------------- what the rule does not reach


def test_a_part_of_the_table_is_not_the_table():
    """Every honest partition, left alone.

    A stratum's rows and a channel's treated half are counts of the same
    table and are not its size. They are spelled ``n``; only the whole
    wears the contract's name for it, which is why this rule never has to
    tell one from the other.
    """
    parts = 0
    for name in CARRIERS:
        run_wide = (SHAPES[name]["result"]["estimation_context"]
                    ["sample_size"])
        stats = ((SHAPES[name]["result"].get("numeric_estimate") or {})
                 .get("measurement_correction") or {}
                 ).get("sufficient_statistics") or {}
        for stratum in stats.get("strata") or []:
            if "n" not in stratum:
                continue
            assert stratum["n"] != run_wide
            parts += 1
    assert parts == 12
    _, result = _pair("measurement_error_correction")
    verify_one_row_count(result)          # and it is not refused


def test_a_second_table_is_not_this_one():
    """``reference_sample_size`` is the other frame a selection recovery
    reads, so the walk asks for the name exactly rather than by suffix —
    the one place where matching the way the digests are matched would
    have equated two tables."""
    _, result = _pair("backdoor_linear")
    result["numeric_estimate"]["reference_sample_size"] = 1
    verify_one_row_count(result)
    assert not any(p.endswith("reference_sample_size")
                   for p, _ in _row_counts(result))


def test_an_envelope_with_one_record_or_none_is_left_alone():
    verify_one_row_count({})
    verify_one_row_count({"estimation_context": {"sample_size": 400}})
