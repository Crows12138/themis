"""A mapping the chain recorded is a record of each field inside it.

``verify_numeric_display_agrees`` holds what a reader is shown to what the
derivation recorded, and below the envelope's outer keys it asks the record
for one spelling: the block's name joined to the leaf's, ``cde_status_cap``
for a ``cap`` inside a ``cde_status``. That spelling has been offered since
the deep spellings were worked out. Nothing on the record's side ever
carried such a name, because the chain's outputs were expanded exactly one
level: a mapping a step recorded sat there whole, and every joined spelling
walked past it.

So the two sides could not meet however deep either went. Measured before
this was written: forty-seven leaves of the stored answers have a joined
name the record answers to once its own mappings are expanded, and not one
of them disagreed -- among them why a controlled-effect grid was not
solved, recorded as one mapping and shown as three fields, of which the cap
it was compared against was held by nothing at all.

The other direction was measured too and is wrong. Offering the nested
block itself as a subject on the reader's side reaches the same leaves and
brings three collisions of the kind the walk is built to avoid -- a
decomposition's ``cde`` is a table of intervals where the step's ``cde`` is
the cell values it was summarised from -- and twenty-four comparisons
landing opposite a pointer to another step. A role inside a parent is not
the record's vocabulary; a prefixed name is.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

from themis.verifier import display_copy_rules as display
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The answer whose controlled-effect status is the leaf this was written
#: for, and the three fields that status holds.
CARRIER = "numerically_solved:effect:numeric_result#2c4d0f"
STATUS_AT = ("mediation_joint_decomposition", "numeric", "cde_status")
THE_FIELDS = ("cap", "reference_point_count", "status")

#: Comparisons that happen only because a recorded mapping is now a record
#: of its fields. Pinned because the rule's reach is the point: a number
#: that falls is leaves going quiet again, and a reading of values cannot
#: tell the difference between a leaf nobody compares and one that agrees.
NEWLY_COMPARED = 47


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _with_a_derivation():
    for name, pair in SHAPES.items():
        result = pair["result"]
        steps = (result.get("derivation") or {}).get("steps") or ()
        if steps:
            yield name, result


def _newly_compared(result) -> list:
    """Every (block, path, name) this change made comparable at all."""
    steps = result["derivation"]["steps"]
    plain = {}
    for index, step in enumerate(steps):
        named = {}
        if isinstance(step.get("inputs"), dict):
            named.update(step["inputs"])
        produced = step.get("output")
        if isinstance(produced, dict) and isinstance(produced.get("items"),
                                                     dict):
            named.update(produced["items"])
        for name, value in named.items():
            plain[name] = (index, display._plain(value))

    out = []
    full = display._chain_record(steps)
    for key, block in display._subjects(result):
        own = (display._unambiguous(block)
               - display._claimed_outright(result, block))
        for path, _shown in display._named_subjects(block):
            for name in display._spellings(path, own):
                if name in plain:
                    break
                if name in full:
                    out.append((key, path, name))
                    break
    return out


def test_the_corpus_exercises_this_rule():
    """How much this reaches, and that the answer it was written for is in it.

    Counted over the stored answers rather than asserted of the carrier
    alone: a rule that reaches one answer is a special case with a general
    name.
    """
    reached = [(name, hit)
               for name, result in _with_a_derivation()
               for hit in _newly_compared(result)]
    assert len(reached) == NEWLY_COMPARED, len(reached)
    here = {hit[1][-1] for name, hit in reached if name == CARRIER}
    assert here == set(THE_FIELDS), sorted(here)


def test_no_honest_answer_is_refused():
    """All of them, including the ones that carry no such mapping."""
    for _name, result in _with_a_derivation():
        display.verify_numeric_display_agrees(result, result["derivation"])


@pytest.mark.parametrize("field", THE_FIELDS)
def test_a_field_of_a_recorded_block_is_held(field):
    """The forgery this exists for: a field inside a block the step recorded.

    ``cap`` is the one that nothing else holds. The other two are held
    elsewhere as well -- one is recomputed from the grid it counts -- and
    they are here because a rule that reaches a block reaches its fields,
    and a reader cannot tell which of three neighbours has a second author.
    """
    _program, result = _pair(CARRIER)
    status = result["extensions"]
    for part in STATUS_AT:
        status = status[part]
    honest = status[field]
    status[field] = "forged" if isinstance(honest, str) else honest + 7
    with pytest.raises(VerificationError) as caught:
        display.verify_numeric_display_agrees(result, result["derivation"])
    assert field in str(caught.value), str(caught.value)


def test_a_name_the_chain_recorded_is_not_displaced_by_a_derived_one():
    """A real record outranks a name assembled out of two others.

    Without this the joining would let a mapping quietly answer for a name
    a step actually carries, which is the record being rewritten by the
    reading of it.
    """
    steps = [{"rule": "r", "inputs": {
        "cde": {"status": "real"},
        "cde_status": "the one the step recorded",
    }}]
    record = display._chain_record(steps)
    assert record["cde_status"][1] == "the one the step recorded"


def test_a_joined_name_two_mappings_both_produce_is_dropped():
    """An ambiguity is not a disagreement, which is the spelling side's rule.

    ``a`` holding ``b_c`` and ``a_b`` holding ``c`` both spell ``a_b_c``,
    and there is nothing to say which of them a reader means.
    """
    steps = [{"rule": "r", "inputs": {
        "a": {"b_c": 1},
        "a_b": {"c": 2},
    }}]
    record = display._chain_record(steps)
    assert "a_b_c" not in record, record.get("a_b_c")
    assert record["a_b"][1] == {"c": 2}


def test_a_typed_wrapper_names_none_of_its_own_keys():
    """``kind`` is not the name of anything a wrapper contains.

    The same reason the expansion above reads ``items`` and not whatever a
    mapping happens to hold: a reference to another step stands for
    nothing here, and ``step_ref`` is not a field of the thing pointed at.
    """
    steps = [{"rule": "r", "inputs": {
        "cde": {"kind": "step_ref", "step_id": "s2"},
    }}]
    record = display._chain_record(steps)
    assert "cde_kind" not in record
    assert "cde_step_id" not in record


def test_a_refusal_names_the_block_it_is_about():
    """Which block a reader should look in, and no block it should not.

    The message carried one subject's name hard-coded from before there
    was a second, so a disagreement inside the other one printed a path no
    answer has.
    """
    _program, result = _pair(CARRIER)
    status = result["extensions"]
    for part in STATUS_AT:
        status = status[part]
    status["cap"] = status["cap"] + 7
    with pytest.raises(VerificationError) as caught:
        display.verify_numeric_display_agrees(result, result["derivation"])
    said = str(caught.value)
    assert said.startswith("extensions."), said
    assert "numeric_estimate.extensions" not in said, said


def test_the_module_names_no_helper_it_does_not_have():
    """Prose that points at a check is a claim that the check is there.

    One paragraph here named a function that declines to compare a block
    with a pointer to one. No such function existed, and reading the
    sentence as a description of the code is how a reader concludes a case
    is handled that nothing handles.

    Asked of the package and not of this module: a rule may name a helper
    it borrows, and ``_atom_label_verifier`` -- which this module's prose
    names and does not import -- is one of them.
    """
    source = pathlib.Path(display.__file__).read_text(encoding="utf-8")
    named = set(re.findall(r"``(_[A-Za-z_][A-Za-z0-9_]*)``", source))
    here = pathlib.Path(display.__file__).parent
    everywhere: set = set()
    for module in sorted(here.glob("*.py")):
        text = module.read_text(encoding="utf-8")
        everywhere |= set(re.findall(
            r"^(?:def|class)\s+(_[A-Za-z0-9_]*)", text, re.MULTILINE))
        everywhere |= set(re.findall(
            r"^(_[A-Za-z0-9_]*)\s*(?::[^=]+)?=", text, re.MULTILINE))
    missing = sorted(name for name in named if name not in everywhere)
    assert not missing, missing
