"""Whether a number can be contradicted is not a fact about its road.

Two estimators reach a joint intervention's contrast and its K-way
interaction. The joint back-door g-formula standardizes a saturated outcome
model over the corners of the treatment box; the general-ID plug-in
identifies each corner's estimand and evaluates it. They differ in what has
to be true for the answer to mean anything, and in nothing else: same box,
same two finite differences, same block on the envelope.

They did not differ in the audit either — there was only one, and its
docstring described the block. What differed was the RECORD. The general-ID
route kept its per-corner risks; the back-door route computed every corner,
took its two differences and dropped them. So the audit that re-derives both
numbers from the corners had corners to read on one road and nothing on the
other, and the difference showed up as a class of forgery: on both back-door
methods the joint contrast could be replaced with any number at all, its
treated and control cells could be moved onto each other, and the
interaction's order could be told as a fraction — nine leaves, none of which
an estimator ever touches.

Naming that "the general-ID rule" is what let it stand. The rule was general
over the block from the day it was written; only its selector said
``joint_general_id_plugin``, and a selector that names a method answers "who
recorded a box" rather than "who has one to check". So the corners moved to
the module that already owns the enumeration, the sign rule and the cap; the
back-door route keeps them the same way the plug-in does; the rule is keyed
on the block; and naming a treatment vector at all now obliges the answer to
carry the record it would be re-derived from — one layer earlier, where a
missing block is a missing block rather than an audit that quietly does not
apply.

The last of those is the load-bearing one. A rule selected by a block is
only as wide as the schema makes that block: without the obligation, the
next joint route could escape the re-derivation the same way this one did,
by not writing anything down.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

import themis
from themis.estimation import general_id, joint, treatment_box
from themis.input.syntactic_validator import SyntacticError
from themis.kernel import _ESTIMATE_AUDITS
from themis.verifier import verify_treatment_box
from themis.verifier.errors import VerificationError
from themis.verifier.frame_rules import verify_frame

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every shape this system produces that answers a joint intervention. Read
#: off the snapshot rather than listed, so a third road arrives here.
JOINT = sorted(
    name for name, pair in SHAPES.items()
    if isinstance(pair["result"].get("numeric_estimate"), dict)
    and pair["result"]["numeric_estimate"].get("treatments") is not None
)


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _key(cell: dict, treatments: list) -> tuple:
    return tuple(cell[t] for t in treatments)


# ------------------------------------------------- both roads leave a record


def test_more_than_one_road_reaches_this_block():
    """The premise of everything below.

    If only one estimator ever emitted a treatment box, keying the audit on
    the block would be keying it on that estimator under another name, and
    every test here would pass while saying nothing.
    """
    assert len(JOINT) > 1
    methods = {SHAPES[n]["result"]["numeric_estimate"]["method"]
               for n in JOINT}
    assert len(methods) > 1, methods


@pytest.mark.parametrize("shape", JOINT)
def test_the_box_a_joint_answer_differenced_is_on_the_envelope(shape):
    """Every corner, named in the caller's own levels, and enough of them.

    Complete at 2^K exactly when an interaction is reported: the contrast
    needs two corners, the K-way finite difference needs all of them.
    """
    _, result = _pair(shape)
    ne = result["numeric_estimate"]
    treatments = ne["treatments"]
    recorded = ne["corner_risks"]
    keys = {_key(entry["cell"], treatments) for entry in recorded}
    assert len(keys) == len(recorded)
    if ne.get("interaction") is not None:
        assert len(keys) == 2 ** len(treatments)
    else:
        assert 2 <= len(keys) < 2 ** len(treatments)


@pytest.mark.parametrize("shape", JOINT)
def test_the_contrast_is_a_difference_of_two_corners_that_are_there(shape):
    """Recomputed here from the snapshot, in this test's own arithmetic.

    The point of the record is that a reader can do this. If the two cells
    the contrast names were spelled differently from the cells in the box —
    ``True`` against ``1``, say — the corners would be present and still
    unfindable, which is why one argument writes both.
    """
    _, result = _pair(shape)
    ne = result["numeric_estimate"]
    treatments = ne["treatments"]
    risks = {_key(e["cell"], treatments): e["risk"]
             for e in ne["corner_risks"]}
    joint_effect = ne["joint_effect"]
    hi = _key(joint_effect["treated"], treatments)
    lo = _key(joint_effect["control"], treatments)
    assert hi in risks and lo in risks
    assert joint_effect["point"] == pytest.approx(risks[hi] - risks[lo])


@pytest.mark.parametrize("shape", JOINT)
def test_the_interaction_is_the_alternating_sum_of_the_whole_box(shape):
    """Written from the definition rather than from the producer: a corner's
    sign is the parity of how many treatments sit at their CONTROL level."""
    _, result = _pair(shape)
    ne = result["numeric_estimate"]
    interaction = ne.get("interaction")
    if interaction is None:
        pytest.skip("this shape withholds the interaction")
    treatments = ne["treatments"]
    lo = _key(ne["joint_effect"]["control"], treatments)
    total = 0.0
    for entry in ne["corner_risks"]:
        key = _key(entry["cell"], treatments)
        at_lo = sum(1 for i, value in enumerate(key) if value == lo[i])
        total += (-1.0 if at_lo % 2 else 1.0) * entry["risk"]
    assert interaction["point"] == pytest.approx(total)
    assert interaction["order"] == len(treatments)


# ------------------------------------------- the forgeries the record refuses


@pytest.mark.parametrize("shape", JOINT)
@pytest.mark.parametrize("path,forged", [
    (("joint_effect", "point"), 2.4111784399084386),
    (("joint_effect", "treated", "a"), False),
    (("joint_effect", "control", "b"), True),
    (("interaction", "point"), 0.9301636921629234),
    (("interaction", "order"), 7),
])
def test_a_number_that_no_longer_follows_from_the_box_is_refused(
        shape, path, forged):
    """The nine leaves this frontier is about, asked of every road at once.

    Two of them move no arithmetic: the cells the contrast was taken
    between. Moving one onto the other makes the difference a difference of
    one corner from itself, which is zero and is not what the block reports
    — but nothing reads those cells until something re-derives the contrast
    FROM them.
    """
    program, result = _pair(shape)
    node = result["numeric_estimate"]
    for step in path[:-1]:
        if step not in node:
            # An answer may have no interaction to report, and one in the
            # corpus does. It is not passed over on that account: an
            # omitted block and a WITHHELD one are different claims, and
            # only the second means there is no number here to bend. So
            # the row must be saying the second, in the field that says
            # it, before this bend agrees there is nothing to forge.
            assert step == "interaction", (shape, path)
            assert "interaction_unavailable" in result["numeric_estimate"]
            return
        node = node[step]
    assert node[path[-1]] != forged
    node[path[-1]] = forged
    with pytest.raises(VerificationError):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", JOINT)
@pytest.mark.parametrize("dropped", ["corner_risks", "joint_effect"])
def test_naming_a_treatment_vector_obliges_the_record_and_the_contrast(
        shape, dropped):
    """Held by the schema, one layer before the rule.

    An audit selected by a block cannot ask about an answer that omits it —
    a missing block and a rule that does not apply are the same silence. So
    the obligation is stated where a shape is stated: name a treatment
    vector and you owe the contrast and the box it is a difference of.
    """
    program, result = _pair(shape)
    del result["numeric_estimate"][dropped]
    with pytest.raises(SyntacticError, match=dropped):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", JOINT)
def test_a_corner_the_contrast_rests_on_cannot_be_dropped(shape):
    """Short of 2^K is a claim, and the block beside it has to make it."""
    program, result = _pair(shape)
    ne = result["numeric_estimate"]
    treatments = ne["treatments"]
    hi = _key(ne["joint_effect"]["treated"], treatments)
    ne["corner_risks"] = [e for e in ne["corner_risks"]
                          if _key(e["cell"], treatments) != hi]
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_an_order_written_as_a_float_is_read_rather_than_skipped():
    """A wrong TYPE was the one way past a rule about a wrong VALUE.

    The frame rule that holds an interaction's order to the contrast beside
    it read anything that was not an ``int`` as nothing to say — and JSON's
    ``integer`` admits ``7.0``, so a wrong order in float clothing walked
    through the one rule written to catch it. Silence and refusal look the
    same in the code and mean the opposite.

    Asked at the rule, because a re-derivation reaches this edit first and
    refuses for its own reason, which is the arrangement working rather than
    this rule being unnecessary.
    """
    program, result = _pair("joint_backdoor_linear")
    result["numeric_estimate"]["interaction"]["order"] = 7.0
    with pytest.raises(VerificationError):
        themis.verify(program, result)
    with pytest.raises(VerificationError,
                       match="different number of treatments"):
        verify_frame(result, program, query_id=result.get("query_id"))


def test_an_order_that_is_not_a_whole_number_is_refused():
    """The other half of reading it: a fraction is not an order.

    Held by the schema at the public door, so the rule's own refusal is
    asked of the rule — an order arriving from anywhere else is still not a
    count of treatments.
    """
    program, result = _pair("joint_backdoor_linear")
    result["numeric_estimate"]["interaction"]["order"] = 2.5
    with pytest.raises(SyntacticError, match="order"):
        themis.verify(program, result)
    with pytest.raises(VerificationError, match="whole number of treatments"):
        verify_frame(result, program, query_id=result.get("query_id"))


# -------------------------------------------------- one definition, one place


def test_the_selector_names_the_block_and_no_method():
    """What the fix IS, stated where a test can hold it.

    A row that named a method would answer "who recorded a box" — the
    question whose wrong answer this frontier was.
    """
    rows = [r for r in _ESTIMATE_AUDITS if r.rule is verify_treatment_box]
    assert len(rows) == 1
    row, = rows
    assert row.blocks == frozenset({"corner_risks"})
    assert not row.methods and not row.method_prefixes


def test_both_roads_take_their_corners_from_the_module_that_defines_the_box():
    """The enumeration, the sign rule, the cap and now the record.

    A second definition of what a corner IS is how two roads drift apart
    while both look right.
    """
    assert treatment_box.CornerRisk.__module__ == treatment_box.__name__
    for producer in (joint, general_id):
        assert producer.CornerRisk is treatment_box.CornerRisk
    source = pathlib.Path(inspect.getsourcefile(treatment_box)).read_text(
        encoding="utf-8")
    defined = {node.name for node in ast.walk(ast.parse(source))
               if isinstance(node, ast.ClassDef)}
    assert "CornerRisk" in defined


def test_the_two_uses_of_a_corner_are_written_by_one_argument():
    """A route's own way of writing a corner, used for the contrast's cells
    and for the box, cannot be two ways.

    Asked at the source: the attachment takes ``cell`` once and every corner
    in its body is written by calling it — the contrast's two, and the box's.
    What must not differ is the two USES, not what either route chooses; one
    hands over ``dict``, the other coerces to ``bool``.
    """
    attach = __import__(
        "themis.estimation.dispatch", fromlist=["dispatch"]
    )._attach_treatment_box
    assert "cell" in inspect.signature(attach).parameters
    tree = ast.parse(inspect.getsource(attach).lstrip())
    calls = [node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert calls == ["cell"] * 3, calls


# ----------------------------------------------- what the record is held to


def test_a_corner_of_a_probability_answer_is_held_to_the_unit_interval():
    """Held where the envelope names the outcome level the risks are OF —
    the one statement on it that makes them probabilities."""
    program, result = _pair("joint_general_id_plugin")
    ne = result["numeric_estimate"]
    assert ne.get("outcome_high") is not None
    ne["corner_risks"][0]["risk"] = 1.7
    with pytest.raises(VerificationError, match="must be a probability"):
        themis.verify(program, result)


def test_a_corner_on_the_outcomes_own_scale_has_no_range_to_be_held_to():
    """The same bound applied unconditionally would refuse an honest answer:
    a linear joint standardizes to means, and this one's corners are
    outside [0, 1] on both sides."""
    program, result = _pair("joint_backdoor_linear")
    ne = result["numeric_estimate"]
    assert ne.get("outcome_high") is None
    risks = [entry["risk"] for entry in ne["corner_risks"]]
    assert any(r > 1.0 for r in risks) and any(r < 0.0 for r in risks)
    themis.verify(program, result)


def test_a_corner_that_is_not_a_number_is_refused_on_either_scale():
    """Asked at the rule: the schema types this leaf, so the public door
    refuses it one layer earlier and would never reach the sentence under
    test."""
    estimate = {
        "treatments": ["a", "b"],
        "joint_effect": {"point": 1.0,
                         "treated": {"a": True, "b": True},
                         "control": {"a": False, "b": False}},
        "corner_risks": [{"cell": {"a": True, "b": True}, "risk": "1.0"}],
    }
    with pytest.raises(VerificationError, match="must be a number"):
        verify_treatment_box(estimate)
