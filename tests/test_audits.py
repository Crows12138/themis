"""An audit that was never about your artifact is not an audit you failed.

Thirteen public ``verify_*`` entry points share a parameter name and a
prefix and audit two different things. Handed one ordinary ``query_result``
each, over 139 of them: ``verify_markov_blanket`` and the four
``verify_orientation_*`` raised ``VerificationError`` every single time,
because the artifact was not theirs — the same exception they raise for an
artifact that failed. ``verify_outcome_error`` returned quietly all 139
times, none of which carried an ``outcome_error``. Four surfaces each
hand-rolled a subset of the thirteen; the two largest overlapped in three.

These tests hold the table to both halves: what it excludes, it excludes
because of what the audit is an audit of, and what it includes really does
apply.
"""
from __future__ import annotations

import pytest

import themis
from themis.audits import AUDITS, Artifact, applicable, artifact_of, bind

STANDALONE = [a for a in Artifact if a is not Artifact.QUERY_RESULT]

# Named here rather than read off the table, because the table is what is
# under test: asking it which audits are not about an envelope and then
# checking it excludes those would agree with itself however it was written.
# These five say so in their own docstrings.
AUDITS_OF_ANOTHER_ARTIFACT = (
    "verify_markov_blanket",
    "verify_orientation_propagation",
    "verify_orientation_questions",
    "verify_orientation_session",
    "verify_orientation_ledger_export",
)


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _solved() -> tuple[dict, dict]:
    """A real envelope, from the kernel — not a hand-built stand-in."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "X", "domain": [True, False]},
            {"kind": "variable", "predicate": "M", "domain": [True, False]},
            {"kind": "variable", "predicate": "Y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("X"), "to": _atom("M")},
            {"kind": "cause", "from": _atom("M"), "to": _atom("Y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("X"), "to": _atom("Y")}},
        ],
    }
    return program, themis.run(program)["results"][0]


# ------------------------------------------------------------------ the table

def test_every_public_verifier_says_what_it_audits():
    """Import-time already; here to say what breaks if it stops holding."""
    bind(themis.__all__)


def test_a_verifier_that_declares_nothing_is_an_error():
    with pytest.raises(RuntimeError, match="undeclared"):
        bind([*themis.__all__, "verify_something_new"])


def test_a_row_for_an_entry_point_that_is_not_public_is_an_error():
    with pytest.raises(RuntimeError, match="not public"):
        bind([n for n in themis.__all__ if n != "verify"])


def test_every_row_says_what_it_re_derives():
    """The reader's sentence is the point of the row; a row without one
    would still select correctly and still tell them nothing."""
    for row in AUDITS:
        assert row.zh.strip(), row.name


def test_an_envelope_is_the_artifact_anything_unnamed_resolves_to():
    _, result = _solved()
    assert artifact_of(result) is Artifact.QUERY_RESULT
    assert artifact_of({}) is Artifact.QUERY_RESULT


# ------------------------------------- what it excludes, and why it excludes it

@pytest.mark.parametrize("name", AUDITS_OF_ANOTHER_ARTIFACT)
def test_an_audit_of_another_artifact_is_not_offered_for_an_envelope(name):
    """Each of these once refused every envelope it was ever shown, in the
    same words it uses for one that failed."""
    _, result = _solved()
    assert name not in [row.name for row in applicable(result)]


def test_the_table_agrees_about_which_audits_are_not_about_an_envelope():
    """The list above is the test's own claim; this is where the two meet.

    Splitting them is what lets the exclusion test stay independent of the
    table — and it is this one that goes red when a row is filed under the
    wrong artifact.
    """
    declared = {row.name for row in AUDITS
                if row.artifact is not Artifact.QUERY_RESULT}
    assert declared == set(AUDITS_OF_ANOTHER_ARTIFACT)


@pytest.mark.parametrize("kind", STANDALONE, ids=[str(a) for a in STANDALONE])
def test_a_standalone_artifact_selects_exactly_its_own_audit(kind):
    chosen = applicable({"kind": str(kind)})
    assert [row.artifact for row in chosen] == [kind]


@pytest.mark.parametrize("kind", STANDALONE, ids=[str(a) for a in STANDALONE])
def test_the_kind_a_standalone_auditor_demands_is_the_one_declared_here(kind):
    """Read from the auditor's side, which keeps its own literal.

    Selecting an audit out of a table the audit itself wrote would make the
    selection self-certifying. So ask the auditor: handed the declared kind
    it must get past its own gate and fail on the artifact's contents, and
    handed another it must refuse at the gate.
    """
    row = next(r for r in AUDITS if r.artifact is kind)
    fn = getattr(themis, row.name)

    with pytest.raises(Exception) as accepted:
        fn({"kind": str(kind)})
    assert "not a" not in str(accepted.value), \
        f"{row.name} 不认它自己声明的 kind={kind}"

    with pytest.raises(Exception) as refused:
        fn({"kind": "something_else_entirely"})
    assert "not a" in str(refused.value)


def test_a_field_the_result_does_not_carry_is_not_something_it_passed():
    """verify_outcome_error used to return quietly on a result with no
    outcome_error, and quiet is what passing looks like."""
    _, result = _solved()
    assert "outcome_error" not in result
    assert "verify_outcome_error" not in [row.name for row in applicable(result)]


# ------------------------------------------------------------------- running it

def test_a_solved_result_is_re_derived_by_every_check_that_applies():
    program, result = _solved()
    rows = themis.audit(program, result)
    assert len(rows) >= 3
    assert all(row["ok"] for row in rows), [r for r in rows if not r["ok"]]
    assert "verify" in [row["audit"] for row in rows]


def test_a_tampered_answer_is_reported_rather_than_raised():
    program, result = _solved()
    result["structural_result"] = {"value": False, "supporting_paths": []}
    rows = themis.audit(program, result)
    failed = [row for row in rows if not row["ok"]]
    assert failed, "改坏了答案，复核却全过"
    assert all(row["refusal"] for row in failed)


def test_an_audit_that_needs_the_program_says_so_rather_than_guessing():
    _, result = _solved()
    with pytest.raises(ValueError, match="verify"):
        themis.audit(None, result)


def test_a_standalone_artifact_needs_no_program():
    rows = themis.audit(None, {"kind": "markov_blanket"})
    assert [row["audit"] for row in rows] == ["verify_markov_blanket"]
    assert rows[0]["ok"] is False
