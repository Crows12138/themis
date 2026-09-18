"""An input a step records and nobody reads is not a record of anything.

``UnknownRuleInputError`` has always said a rule input dict may be
"missing a required key, OR HAVE AN UNEXPECTED KEY". Nothing implemented
the second half, so a step could write anything at all beside what its
rule reads and the writing was a claim no reader was ever offered —
measured, the criterion step of a proximal answer recorded a fifteen-field
descriptor its rule never opened, and 53 declared leaves sat under it.

Two things account for an input now. The atom gate at the top of
``dispatch_rule`` reads every atom a step names and holds it to the
graph's roster, which is why most inputs are held whatever their rule does
with them: a forged variable is not a node. The rule accounts for the rest
by asking for them. Anything else has to be named in
``_RECORDED_FOR_A_READER_ELSEWHERE`` before it may exist.

What this does NOT claim: that an input a rule reads is an input a rule
CHECKS. A rule can read a value and compare it with nothing — the transport
steps do, and their leaves are still in the remainder. The line held here
is the weaker one, and it is the one that makes the next silent record
impossible rather than merely absent today.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import Atom, ConstTerm
from themis.verifier.errors import RuleCheckFailed, UnknownRuleInputError
from themis.verifier.rules import (
    _RECORDED_FOR_A_READER_ELSEWHERE,
    _WhatTheRuleAskedFor,
    _the_proximal_descriptor,
    _what_was_written,
    dispatch_rule,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _steps(result: dict) -> tuple:
    return tuple((result.get("derivation") or {}).get("steps") or ())


def _criterion(result: dict) -> dict | None:
    for step in _steps(result):
        if step.get("rule") == "proximal_criterion" and "estimand" in (
                step.get("inputs") or {}):
            return step
    return None


#: Every stored answer whose criterion step records the descriptor it was
#: handed. Derived rather than listed: a roster typed out by hand is a
#: roster that stops being true.
CRITERION_ROWS = sorted(
    name for name, pair in SHAPES.items()
    if _criterion(pair["result"]) is not None)

#: Every stored answer with a criterion step that records NO descriptor.
#: The rule is emitted twice — once by the structural path with the
#: descriptor, once on the way to a numeric answer with the graph alone —
#: and this half is the narrowing recorded at the bottom of this file.
BARE_CRITERION_ROWS = sorted(
    name for name, pair in SHAPES.items()
    if _criterion(pair["result"]) is None
    and any(step.get("rule") == "proximal_criterion"
            for step in _steps(pair["result"])))


def test_the_rosters_are_the_size_they_were_measured_at():
    """Pinned so that a corpus change shows up here rather than as a
    silently narrower sweep somewhere below."""
    assert (len(CRITERION_ROWS), len(BARE_CRITERION_ROWS)) == (5, 9)


# ------------------------------------------------------------------ the record

def _recorded(name: str, field: str):
    """What the stored step actually writes for a field, read off the
    envelope rather than guessed."""
    step = _criterion(SHAPES[name]["result"])
    estimand = step["inputs"]["estimand"]
    return estimand.get("items", estimand)[field]


def _the_decoded_criterion(result: dict):
    """The step as the verifier sees it, not as the file spells it: the
    stored shape wraps every record in an envelope naming its kind, and
    what a rule is handed is the envelope opened."""
    from themis.verifier.serialization import derivation_from_dict

    for step in derivation_from_dict(result.get("derivation") or {}):
        if step.rule == "proximal_criterion" and "estimand" in step.inputs:
            return step
    raise AssertionError("no criterion step records a descriptor")


def _premises(name: str):
    from themis.kernel import _premises_of

    pair = SHAPES[name]
    _ast, program, query_stmt, ctx = _premises_of(pair["program"],
                                                  pair["result"])
    return pair, program, query_stmt, ctx


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_the_recorded_descriptor_is_the_one_the_question_asks_for(name):
    """Honest side, stated as an equality rather than an acceptance: the
    step's copy and the rebuild agree field for field."""
    pair, _program, query_stmt, _ctx = _premises(name)
    step = _the_decoded_criterion(pair["result"])
    recorded = _what_was_written(step.inputs["estimand"])
    asked = _what_was_written(_the_proximal_descriptor(query_stmt.query))
    for field in ("treatment_proxy", "outcome_proxy", "covariates"):
        if isinstance(recorded.get(field), list):
            recorded[field] = sorted(recorded[field])
    assert recorded == asked


def _bend_the_recorded_estimand(result: dict, field: str, value) -> None:
    for step in _steps(result):
        inputs = step.get("inputs") or {}
        if step.get("rule") != "proximal_criterion" or "estimand" not in inputs:
            continue
        estimand = inputs["estimand"]
        # The stored shape wraps every record in an envelope that names its
        # kind; the field sits under ``items``.
        body = estimand.get("items", estimand)
        body[field] = value


def _the_other(value, pair_of):
    """A forgery has to say something the record did not. A constant
    written here says the same thing as half the corpus and measures
    nothing on those rows, which is the same mistake as bending a value
    outside its own contract."""
    first, second = pair_of
    assert value in pair_of, value
    return second if value == first else first


def _refused(name: str, field: str, value, fragment: str) -> None:
    pair = SHAPES[name]
    result = json.loads(json.dumps(pair["result"]))
    _bend_the_recorded_estimand(result, field, value)
    door = the_door_for(result)
    with pytest.raises(Exception) as caught:
        door(pair["program"], result)
    assert fragment in str(caught.value), str(caught.value)


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_a_forged_latent_in_the_record_is_refused(name):
    """The confounder the whole design exists to see around. An atom, so
    the gate above would refuse a name the graph does not have — this
    bends it to ANOTHER NODE OF THE SAME GRAPH, which the gate accepts and
    only the question can tell apart."""
    _, program, _q, _ctx = _premises(name)
    _refused(name, "latent", "y()", "estimand")


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_a_forged_method_in_the_record_is_refused(name):
    """``method`` is ``channel_kind`` said in the vocabulary a reader
    reads, and neither is an atom, so nothing above this rule looks at
    it. The other member of the pair, not a constant: this corpus holds
    answers of both channels and a constant is a no-op on half of them."""
    _refused(name, "method", _the_other(_recorded(name, "method"),
                                        ("proximal_bridge", "proximal_matrix")),
             "estimand")


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_a_forged_channel_kind_in_the_record_is_refused(name):
    _refused(name, "channel_kind",
             _the_other(_recorded(name, "channel_kind"),
                        ("bridge_channel", "discrete_channel")),
             "estimand")


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_a_dropped_field_in_the_record_is_refused(name):
    """A record that leaves a field out describes a different study, and
    the comparison is of the whole descriptor for exactly that reason."""
    pair = SHAPES[name]
    result = json.loads(json.dumps(pair["result"]))
    for step in _steps(result):
        inputs = step.get("inputs") or {}
        if step.get("rule") == "proximal_criterion" and "estimand" in inputs:
            body = inputs["estimand"].get("items", inputs["estimand"])
            body.pop("method")
    door = the_door_for(result)
    with pytest.raises(Exception) as caught:
        door(pair["program"], result)
    assert "estimand" in str(caught.value), str(caught.value)


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_a_field_the_question_never_asked_for_is_refused(name):
    """The state the twelve bridge fields arrived in, one level down."""
    _refused(name, "outcome_bridge_curvature", 3, "estimand")


@pytest.mark.parametrize("name", CRITERION_ROWS)
def test_the_honest_record_still_passes(name):
    """Said once per row, because a rule that refuses everything refuses
    the forgeries too and would look identical above."""
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


# ------------------------------------------------- an input nobody reads

def _a_real_step(name: str):
    """A context and one step, taken from a stored answer rather than
    built here: the question is what ``dispatch_rule`` does with a real
    step, and a hand-built one would answer about the fixture."""
    from themis.kernel import _premises_of
    from themis.verifier.serialization import derivation_from_dict

    pair = SHAPES[name]
    _ast, _program, _query_stmt, ctx = _premises_of(pair["program"],
                                                    pair["result"])
    steps = derivation_from_dict(pair["result"].get("derivation") or {})
    return ctx, steps[0]


def _dispatch(ctx, step, inputs: dict) -> None:
    dispatch_rule(
        rule_name=step.rule,
        ctx=ctx,
        inputs=inputs,
        claimed_output=step.output,
        step_index=0,
        step_by_id={},
        step_output_by_id={},
    )


def test_an_input_the_rule_never_reads_is_refused():
    """The defect this frontier is about, asked directly: a step that
    writes something down which neither names a variable nor reaches its
    rule is writing a claim nobody can be wrong about."""
    ctx, step = _a_real_step(CRITERION_ROWS[0])
    inputs = dict(step.inputs)
    inputs["how_confident_the_analyst_felt"] = "very"
    with pytest.raises(UnknownRuleInputError,
                       match="how_confident_the_analyst_felt"):
        _dispatch(ctx, step, inputs)


def test_an_input_that_names_a_variable_is_accounted_for_by_the_gate():
    """Most inputs are held without their rule reading them, and this is
    why: the roster check above the dispatch reads every atom a step
    names. An extra atom-valued key is therefore NOT an unread record —
    it was read, by the one reader every step has."""
    ctx, step = _a_real_step(CRITERION_ROWS[0])
    node = next(iter(ctx.graph))
    inputs = dict(step.inputs)
    inputs["some_variable_this_rule_ignores"] = node
    _dispatch(ctx, step, inputs)


def test_an_atom_the_graph_does_not_have_is_still_refused_by_key():
    """And the gate now says which input it found the stranger in."""
    ctx, step = _a_real_step(CRITERION_ROWS[0])
    inputs = dict(step.inputs)
    inputs["some_variable_this_rule_ignores"] = Atom(
        predicate="nowhere", args=(ConstTerm(name="u"),))
    with pytest.raises(RuleCheckFailed, match="some_variable_this_rule_ignores"):
        _dispatch(ctx, step, inputs)


def test_a_name_on_the_list_is_allowed_to_go_unread():
    """The list is the whole of the excuse, so a name on it is the whole
    of what it buys."""
    ctx, step = _a_real_step(CRITERION_ROWS[0])
    inputs = dict(step.inputs)
    inputs["ci_level"] = 0.95
    _dispatch(ctx, step, inputs)


def test_the_list_is_short_and_says_what_is_on_it():
    """Pinned. The list is where this check stops holding, so it growing
    is the thing worth seeing in a diff."""
    assert _RECORDED_FOR_A_READER_ELSEWHERE == frozenset({
        "ar_point", "ci_level", "ci_width_is", "instrument",
        "instrument_levels", "intervention_value", "monotonicity",
        "p_xyz", "p_z", "risk_formula", "risk_formula_control",
        "risk_formula_treated",
    })


def test_every_name_on_the_list_is_one_the_corpus_actually_records():
    """A name nothing writes is a name excusing nothing, and it would sit
    there looking like coverage."""
    written = set()
    for pair in SHAPES.values():
        for step in _steps(pair["result"]):
            written.update(step.get("inputs") or ())
    assert _RECORDED_FOR_A_READER_ELSEWHERE <= written


# ---------------------------------------------------- what asking means

def test_iterating_the_keys_is_not_asking():
    """A rule that walks the key names has not taken any value into
    account, and counting that as reading would excuse exactly the record
    this check exists to find."""
    asked = _WhatTheRuleAskedFor({"a": 1, "b": 2})
    assert sorted(asked) == ["a", "b"]
    assert len(asked) == 2
    assert asked.asked == set()


def test_reading_a_value_or_testing_for_one_is_asking():
    asked = _WhatTheRuleAskedFor({"a": 1, "b": 2, "c": 3})
    assert asked["a"] == 1
    assert "b" in asked
    assert asked.get("c") == 3
    assert asked.asked == {"a", "b", "c"}


def test_the_record_cannot_be_edited_by_the_rule_that_reads_it():
    """Read-only on purpose: a rule that could write here would be editing
    the record it is checking."""
    asked = _WhatTheRuleAskedFor({"a": 1})
    with pytest.raises(TypeError):
        asked["a"] = 2


def test_content_is_compared_and_not_the_container():
    """The block arrives as JSON and a step's inputs arrive through the
    derivation serializer, which spells every sequence as a tuple."""
    assert _what_was_written({"k": ({"n": (1, 2)},)}) == {"k": [{"n": [1, 2]}]}
    assert _what_was_written("xy") == "xy"


# ------------------------------------------------- the narrowing, recorded

@pytest.mark.parametrize("name", BARE_CRITERION_ROWS)
def test_a_criterion_step_may_still_record_no_descriptor(name):
    """Recorded rather than fixed. The numeric path emits this rule with
    the graph alone, so a producer that simply stops recording the
    descriptor is not caught here. Requiring it would refuse these nine
    stored answers, which is a worse trade than saying so: what is held is
    that a descriptor which IS written down is the question's.
    """
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])
    assert _criterion(pair["result"]) is None
