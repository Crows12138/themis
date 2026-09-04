"""The step named the counterfactual it ran, and the audit never looked.

``_rule_scm_abduction_action_prediction`` takes a parameter called
``inputs`` — what the step says it was GIVEN — and the body never opened
it. The audit re-ran Pearl's three steps from ``ctx.query`` and compared
one number, so the three entries that say WHICH counterfactual this is
were free to say anything and the check still agreed with itself.

Measured before this existed: on all 43 answers whose derivation carries
this step, the recorded target, the recorded intervention variable and the
recorded intervention value were each edited, and every edit passed both
public doors. A reader could be shown a step claiming it intervened on one
variable and asked about another, over a number computed for neither.

Nothing here is recomputed. ``abduct_act_predict`` already hands back the
whole world, and the value the world was computed at is the intervened
variable's own entry — do(X=v) puts v there — which is exactly how the
display copy beside this step is already read. Same re-run, asked for what
it had already worked out.

This is the third frontier in a row with that shape, so it is worth saying
plainly: the question to ask of a rule is not "what else should it check"
but "what did the re-run already have in its hands that nobody asked it
for".
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

RULE = "scm_abduction_action_prediction"

#: (answer name, index of the step) for every step of this rule.
STEPS = sorted(
    (name, i)
    for name, pair in SHAPES.items()
    for i, step in enumerate(
        ((pair["result"] or {}).get("derivation") or {}).get("steps") or [])
    if step.get("rule") == RULE
)

#: The three entries that say which counterfactual a step ran, and the
#: edit that makes each one a lie the rest of the envelope still fits.
LIES = (
    ("target", lambda s: s["inputs"]["target"].update({"predicate": "nobody"})),
    ("intervention_var",
     lambda s: s["inputs"]["intervention_var"].update({"predicate": "nobody"})),
    ("intervention_value",
     lambda s: s["inputs"].update(
         {"intervention_value": float(s["inputs"]["intervention_value"]) + 7.5})),
)


def test_the_steps_that_name_a_counterfactual():
    """The denominator, and that all three entries are really there.

    The producer writes exactly these three, so a step missing one is not
    a shape this rule has seen; asserting it here means a producer that
    stops recording which counterfactual it ran fails loudly rather than
    making the rule below vacuous.
    """
    assert len(STEPS) == 43, len(STEPS)
    for name, i in STEPS:
        inputs = SHAPES[name]["result"]["derivation"]["steps"][i]["inputs"]
        assert set(inputs) == {"target", "intervention_var",
                               "intervention_value"}, (name, sorted(inputs))


@pytest.mark.parametrize("name,i", STEPS)
def test_an_honest_step_is_accepted(name, i):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


@pytest.mark.parametrize("field,lie", LIES, ids=[f for f, _ in LIES])
def test_every_step_is_held_to_what_it_says_it_computed(field, lie):
    """One entry at a time, over every step, counted.

    One at a time because editing all three at once lets a single refusal
    stand for three separate checks — which is how a rule that reached one
    of them would look like a rule that reached them all.
    """
    refused = 0
    for name, i in STEPS:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        lie(forged["derivation"]["steps"][i])
        with pytest.raises(Exception):                          # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 43, refused


def test_the_two_atoms_are_told_apart_in_the_message():
    """Not a count: intervening on the wrong variable and answering about
    the wrong one are different mistakes, and a message covering both
    would leave a reader to work out which of the two happened."""
    name, i = STEPS[0]
    row = SHAPES[name]

    forged = copy.deepcopy(row["result"])
    forged["derivation"]["steps"][i]["inputs"]["target"]["predicate"] = "nobody"
    with pytest.raises(Exception, match="asked about"):          # noqa: B017
        the_door_for(row["result"])(row["program"], forged)

    forged = copy.deepcopy(row["result"])
    forged["derivation"]["steps"][i]["inputs"][
        "intervention_var"]["predicate"] = "nobody"
    with pytest.raises(Exception, match="intervened on"):        # noqa: B017
        the_door_for(row["result"])(row["program"], forged)


def test_the_step_and_the_block_describe_the_same_counterfactual():
    """The two places a reader is told which counterfactual this is.

    The step's inputs say it here; ``extensions.scm_counterfactual`` says
    it again for the reader, and #574 holds that block to the world the
    verifier re-derived. Chaining the two is what makes this rule's
    subject the same subject as that one — otherwise the envelope could
    carry a step about one counterfactual and a display copy about
    another, each held to something, neither held to the other.

    Asserted over the corpus rather than by rebuilding a context: the
    public doors normalise a program before any of this runs, and a
    hand-built context measures the un-normalised one instead.
    """
    checked = 0
    for name, i in STEPS:
        result = SHAPES[name]["result"]
        block = (result.get("extensions") or {}).get("scm_counterfactual")
        if not isinstance(block, dict):
            continue
        recorded = result["derivation"]["steps"][i]["inputs"]

        assert block["target"].startswith(recorded["target"]["predicate"]), (
            name, block["target"], recorded["target"])
        assert block["intervention"]["variable"].startswith(
            recorded["intervention_var"]["predicate"]), (
                name, block["intervention"]["variable"])
        assert block["intervention"]["value"] == pytest.approx(
            float(recorded["intervention_value"])), name
        checked += 1
    assert checked == 43, checked
