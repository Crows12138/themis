"""The precondition that stood in front of the wrong half.

``verify`` requires a derivation, and the reason is sound and is written
into the message it raises: re-running a conclusion means re-running the
reasoning that reached it, and an answer that shows none cannot be audited
that way. What was wrong is where the sentence stood. Every audit in that
function that is a fact about the ANSWER rather than about the route — the
estimand a reader is shown, each route block, the gap report's contents,
the list a reader is told to fill, the mechanism's target, the refusal
claims, the caller's own words copied back — was written BELOW it.

So the one answer whose whole content is those claims was the one answer
none of them was ever asked about. A data-gap diagnosis takes no route; it
has no chain; the report IS the answer. Measured on the corpus: six such
answers, carrying forty ``said`` leaves — eleven of them the variable a
gap says it is about — one estimand, and four entire investigation lists,
none of it read by any public door.

That the classification was already known is what makes this a structural
defect rather than an oversight. Four of those call sites say in their own
comments that they are facts about the answer and not about the route.
The distinction existed in the prose and not in the code.

The line the split is drawn on is checkable and is checked below: an audit
belongs to the answer half exactly when it needs no derivation to run.
Measured before the split, by running the whole first half of ``verify``
against every answer in the corpus with the chain withheld: nothing
refused. The premises the two halves share come from the program and from
the question, and a derivation is not among them.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib
import textwrap

import pytest

import themis
from tests import partially_observed
from tests.answer_corpus import renaming_refusal
from themis import audits, kernel
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CHAINLESS = sorted(name for name, pair in SHAPES.items()
                   if pair["result"].get("derivation") is None)


def _pair(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


# ------------------------------------------------- the fact this rests on


def test_the_answers_that_took_no_route_are_the_ones_this_is_for():
    """Which answers have no chain, and that they are not a rare shape.

    Three statuses reach a reader without one. Two were expected: an
    answer that came back needing investigation, whose data-gap report is
    its entire content, and a question this language cannot express, whose
    refusal is.

    The third was not, and it is the interesting one. Three answers are
    SOLVED — they carry a number, the estimand it came from and the
    mechanism that fitted it — and still record no chain. The door that
    re-runs reasoning refuses them for having none, so the arithmetic a
    reader is shown on them is never re-run by anything; only what they
    SAY is held. That is a fact about two recovery routes rather than
    about this gate, so it is named here rather than counted, and it is
    its own frontier.
    """
    assert len(CHAINLESS) == 71, len(CHAINLESS)
    statuses = {SHAPES[name]["result"].get("status") for name in CHAINLESS}
    assert statuses == {"needs_investigation", "outside_language",
                        "numerically_solved"}
    solved = sorted(n for n in CHAINLESS
                    if SHAPES[n]["result"].get("status") == "numerically_solved")
    assert solved == ["numerically_solved:effect:none",
                      "numerically_solved:effect:none#6587a8",
                      "numerically_solved:effect:none#859dfc"], solved
    assert {(SHAPES[n]["result"].get("numeric_estimate") or {}).get("method")
            for n in solved} == {"selection_backdoor_recovery",
                                 "missing_data_recovery_gformula"}
    # Whatever the status, every chainless answer says why it is one.
    for name in CHAINLESS:
        assert SHAPES[name]["result"].get("data_gap_report")


def test_the_split_is_drawn_where_the_chain_is_needed():
    """Not a taste: the premises of the answer half are read off the
    program and the question, and a derivation is not among them.

    Stated against the CODE — the docstrings say the word freely, and
    saying it is how they say it is absent — so that threading the chain
    into the shared premises fails here rather than making the second door
    quietly need what it exists not to need.
    """
    for function in (kernel._premises_of, kernel._hold_what_the_answer_says):
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        body = tree.body[0].body
        if (isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]
        code = "\n".join(ast.unparse(node) for node in body)
        assert "derivation" not in code, (function.__name__, code)


#: Names that can only have come from the derivation. A call handed one of
#: these is asking about the chain; a call handed none of them is asking
#: about the answer, and an answer may arrive without a chain.
_FROM_THE_CHAIN = frozenset({
    "derivation", "derivation_json", "claimed", "claimed_numeric",
    "num_est", "steps", "step",
})


def _calls_in(function):
    """Every plain-name call in this function, with the names it is handed."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            handed = set()
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                handed |= {n.id for n in ast.walk(arg)
                           if isinstance(n, ast.Name)}
            yield node.func.id, handed


def test_an_audit_that_never_reads_the_chain_does_not_stand_behind_it():
    """The rule that decides which door an audit belongs to, applied
    instead of remembered.

    This frontier moved the audits it could NAME. The ones it could not
    stayed in :func:`verify`'s tail, and counted by what each call is
    handed there were ten of them — among them the rule that refuses an
    interval whose run states no level, standing on the chain side of the
    one path that ships intervals with no chain.

    So the partition is asserted rather than curated: inside ``verify``,
    every call to a verifier is handed something that came from the
    derivation. Anything else is a question about the answer, and belongs
    in one of the two phases both doors run.
    """
    stranded = sorted(
        name for name, handed in _calls_in(kernel.verify)
        if (name.startswith(("verify", "_verify", "_audit"))
            and not handed & _FROM_THE_CHAIN))
    assert stranded == [], stranded

    # And the phases themselves are reachable from the door that has no
    # chain, which is what makes moving an audit into them mean anything.
    called = {name for name, _ in _calls_in(kernel.verify_answer_claims)}
    assert {"_hold_what_the_answer_says",
            "_hold_what_the_estimate_calls_for"} <= called


def test_the_door_with_no_chain_holds_the_number_it_is_shown():
    """An answer with no chain is not an answer with no number.

    The missing-data recovery path attaches a point, an interval, the level
    its run states its confidence at and the price of narrowing it, and
    returns without a derivation. Behind this door every one of those went
    unread — not refused on the merits, never asked. Each rule below
    existed and would have refused; none of them had ever been put to an
    answer of this shape.
    """
    program = partially_observed.program()
    result = themis.estimate(program, partially_observed.frame())["results"][0]
    assert "derivation" not in result
    assert result["numeric_estimate"]["point"] is not None
    themis.verify_answer_claims(program, result)

    levelless = copy.deepcopy(result)
    del levelless["estimation_context"]["ci_level"]
    with pytest.raises(VerificationError, match="what level this run"):
        themis.verify_answer_claims(program, levelless)

    widened = copy.deepcopy(result)
    widened["numeric_estimate"]["ci_upper"] += 10.0
    with pytest.raises(VerificationError, match="half_width"):
        themis.verify_answer_claims(program, widened)


def test_both_doors_are_declared_and_only_one_asks_for_a_chain():
    """The table that says what each public entry re-derives has a row for
    this one, and the two rows differ in exactly the field the split is
    about.

    Both recompute the answer, and only one of them is gated on the thing
    it recomputes. That is why this row's claim is read through the
    envelope: an answer with no chain may be an answer with no number, and
    then there is nothing here to recompute.
    """
    rows = {row.name: row for row in audits.AUDITS}
    assert rows["verify"].needs_field == "derivation"
    assert rows["verify_answer_claims"].needs_field is None
    assert rows["verify_answer_claims"].re_derives_answer is True
    assert rows["verify_answer_claims"].re_derives_the_answer_of({}) is False
    assert rows["verify_answer_claims"].re_derives_the_answer_of(
        {"numeric_estimate": {"point": 0.4}}) is True
    assert rows["verify_answer_claims"].needs_program is True
    assert "verify_answer_claims" in themis.__all__


# ------------------------------------------------------------- the gate


@pytest.mark.parametrize("shape", CHAINLESS)
def test_an_answer_with_no_chain_is_read_rather_than_refused(shape):
    """Honest first, at the door this frontier opened."""
    themis.verify_answer_claims(*_pair(shape))


@pytest.mark.parametrize("shape", CHAINLESS)
def test_the_chain_door_still_asks_for_a_chain(shape):
    """The precondition is not weakened — it is only no longer standing in
    front of the half that does not need it. And the refusal now says
    where else to go, because a reader who cannot audit an answer at all
    and a reader holding the wrong door are different people.
    """
    program, result = _pair(shape)
    with pytest.raises(ValueError, match="requires a result with a") as caught:
        themis.verify(program, result)
    assert "verify_answer_claims" in str(caught.value)


def test_a_gap_that_names_a_variable_this_problem_lacks_is_refused():
    """The counter-example the door exists to say no to.

    Every name in the forged report is a name; only the one this gap is
    about has moved. Before the split this envelope reached no rule at
    all, so it was accepted by the only door that took it — by being
    turned away at it.
    """
    from themis.verifier.gap_claim_rules import _NAMES, every_said

    for name in CHAINLESS:
        program, result = _pair(name)
        found = next(
            ((w, v) for w, k, v in every_said(result["data_gap_report"])
             if k in _NAMES), None)
        if found is None:
            continue
        where, value = found
        node, steps = result["data_gap_report"], where.split(".")
        for step in steps[:-1]:
            node = node[int(step)] if isinstance(node, list) else node[step]
        node[steps[-1]] = str(value) + "_forged"
        with pytest.raises(VerificationError, match="does not name"):
            themis.verify_answer_claims(program, result)
        return
    raise AssertionError("no chainless answer names a variable in a gap")


def test_an_estimand_on_a_chainless_answer_is_refused():
    """A formula reaches a reader whether or not a route was taken, and a
    gap diagnosis may still show one: this is the question the reader was
    told could not be answered YET, written out."""
    carriers = [n for n in CHAINLESS if "formula" in SHAPES[n]["result"]]
    assert len(carriers) == 40, len(carriers)

    # Asked of every one of them, not of the first. This was one row when
    # it was written, and a loop over one row and a lookup of one row read
    # the same — until the corpus brought thirty-nine more and only one of
    # them would have been asked anything.
    for name in carriers:
        program, result = _pair(name)
        target = result["formula"].get("target")
        if not isinstance(target, dict) or "atom" not in target:
            # Not every estimand is a reference with a target to rename;
            # the ones that are not are held by the shape tests above.
            continue
        target["atom"]["predicate"] += "_forged"
        with pytest.raises(VerificationError,
                           match=renaming_refusal(program)):
            themis.verify_answer_claims(program, result)


def test_a_reader_may_not_be_sent_to_fill_in_another_variable():
    """The whole investigation list sits on these answers, and it is what
    the second turn takes verbatim as a patch."""
    carriers = [n for n in CHAINLESS
                if SHAPES[n]["result"].get("investigation_requests")]
    assert len(carriers) == 67, len(carriers)

    for name in carriers:
        program, result = _pair(name)
        for request in result["investigation_requests"]:
            for item in request.get("items") or []:
                skeleton = item.get("skeleton") or {}
                if skeleton.get("kind") != "variable_patch":
                    continue
                skeleton["predicate"] = str(skeleton["predicate"]) + "_forged"
                with pytest.raises(VerificationError,
                                   match="fills in the other one"):
                    themis.verify_answer_claims(program, result)
                return
    raise AssertionError("no chainless answer hands a reader a variable patch")


# ------------------------------------- and the strong door is still strong


def test_the_chain_door_runs_everything_the_other_one_does():
    """The failure this arrangement must not have.

    Two doors over one envelope is how the full door comes to be the
    weaker: a rule added to the narrow one does not grow the copy inside
    the full one, and the divergence runs the way nobody notices. So there
    is no copy — ``verify`` calls the same function, and that is asserted
    against its source rather than trusted.
    """
    source = inspect.getsource(kernel.verify)
    assert "_hold_what_the_answer_says(result, ast, prog, ctx)" in source
    assert source.index("_hold_what_the_answer_says") < source.index(
        "requires a result with a derivation")


@pytest.mark.parametrize("shape", CHAINLESS)
def test_the_reader_of_the_audit_trail_is_told_this_was_re_checked(shape):
    """Where the closure has to end.

    ``themis.audit`` is what a caller asks when the question is "was this
    independently re-checked", and its answer is a row per audit that
    APPLIES. On an answer with no chain the chain audit does not apply and
    said so, correctly — and there was nothing else, so the honest answer
    to that question was a list with nothing in it about the report the
    reader is holding. Now the row is there and says what it re-derived.
    """
    program, result = _pair(shape)
    rows = themis.audit(program, result)
    named = {row["audit"] for row in rows}
    assert "verify" not in named, named
    assert "verify_answer_claims" in named, named
    assert all(row["ok"] for row in rows), rows


def test_every_answer_in_the_corpus_passes_both_doors():
    """The two halves over the whole corpus, so that a rule which moved
    across the split and started needing the chain is caught here."""
    for name in sorted(SHAPES):
        program, result = _pair(name)
        themis.verify_answer_claims(program, result)
        if result.get("derivation") is not None:
            themis.verify(program, result)
