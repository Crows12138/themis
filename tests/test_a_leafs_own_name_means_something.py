"""Whether a leaf's name means anything is not a fact about how deep it sits.

``verify_numeric_display_agrees`` holds what a reader is shown to what the
derivation recorded, by the one question that needs no estimator: a name on
both sides names the same thing. Below the envelope's outermost keys it
asked for ONE spelling, the block's name joined to the leaf's, on the
observation that most of what an answer reports about itself is vocabulary
relative to whichever answer carries it — ``ps.ci_lower`` is the probability
of sufficiency's interval and the step's ``ci_lower`` is the run's.

That observation is right. Reading it as a rule about DEPTH is what cost.
Measured end to end before this was written: on the two attribution blocks —
the highest rung of the hierarchy, where an answer says what a particular
person's outcome would have been — thirteen forgeries were accepted and not
one of them touched an estimator. The observational joint the bounds came
from, both interventional risks, the monotonicity flag that decides WHICH
bound formula applies, the adjustment set, and, for the counterfactual cell,
``lower`` and ``upper`` themselves — the whole answer, replaceable. Every one
of them is recorded flat in the step, and every one sat behind a spelling no
step would ever carry.

Relative or absolute is a question about the envelope, and the envelope
answers it: three blocks say ``ci_lower`` and one says ``p_y_do_x0``. So the
leaf's own name is offered as a fallback exactly where nothing else on this
envelope answers to it.

Four leaves are not in any step at all — which arm was observed, what was
intervened to, which outcome the probability is of, what the factual outcome
was. Those are the question, not the record, and they are held to the query
that asked it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier import display_copy_rules as display
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


# ---------------------------------- the evidence a bound was computed from


@pytest.mark.parametrize("shape,block,path,forged", [
    ("causation_plugin", "probabilities_of_causation", ("p_y_do_x0",), 0.9),
    ("causation_plugin", "probabilities_of_causation", ("p_y_do_x1",), 0.1),
    ("causation_plugin", "probabilities_of_causation",
     ("observational_joint", "p_x1_y1"), 0.9),
    ("causation_plugin", "probabilities_of_causation",
     ("observational_joint", "p_x0_y0"), 0.9),
    ("causation_plugin", "probabilities_of_causation", ("monotonic",), True),
    ("causation_plugin", "probabilities_of_causation", ("adjustment",),
     ["nonexistent_column"]),
    ("counterfactual_cell_plugin", "counterfactual_cell", ("p_y_do_x_cf",),
     0.9),
    ("counterfactual_cell_plugin", "counterfactual_cell",
     ("observational_joint", "p_x1_y1"), 0.9),
    ("counterfactual_cell_plugin", "counterfactual_cell", ("adjustment",),
     ["nonexistent_column"]),
])
def test_the_evidence_shown_is_the_evidence_recorded(
        shape, block, path, forged):
    """None of these moves a bound. That is the point: the numbers the
    bounds are a closed form OF are what a reader checks the reasoning
    with, and they were free."""
    program, result = _pair(shape)
    node = result["numeric_estimate"][block]
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = forged
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(program, result)


@pytest.mark.parametrize("field,forged", [("lower", 0.4), ("upper", 0.6)])
def test_a_counterfactual_cell_cannot_be_given_a_different_answer(
        field, forged):
    """The bounds ARE the answer here, and the block that holds them is one
    level in — which is the only reason they were reachable."""
    program, result = _pair("counterfactual_cell_plugin")
    result["numeric_estimate"]["counterfactual_cell"][field] = forged
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(program, result)


def test_a_word_with_two_owners_is_still_not_asked():
    """The false positive this fallback could have been.

    ``pn``, ``ps`` and ``pns`` each carry ``ci_lower``, and the step's
    ``ci_lower`` is the run's. The rule must stay silent there, and the way
    it stays silent has to be the ambiguity rather than a name written down
    somewhere.
    """
    estimate = SHAPES["causation_plugin"]["result"]["numeric_estimate"]
    unambiguous = display._unambiguous(estimate)
    assert "ci_lower" not in unambiguous
    assert "p_y_do_x0" in unambiguous

    claimed = [".".join(path) for path, _ in display._named_subjects(estimate)
               if path[-1] == "ci_lower"]
    assert len(claimed) > 1, claimed


def test_a_nested_sequence_of_recorded_things_is_unwrapped():
    """A confounder set recorded one list per time step.

    ``_plain`` stopped at the outer container while its docstring said it
    did not, so the names a reader is shown were compared against serialised
    atoms and the two were called different runs.
    """
    recorded = {"kind": "atom_paths", "items": [
        [{"kind": "atom", "predicate": "L0", "args": []}],
        [{"kind": "atom", "predicate": "L1", "args": []}],
    ]}
    assert display._plain(recorded) == [["L0"], ["L1"]]


@pytest.mark.parametrize("shape", ["longitudinal_gformula",
                                   "longitudinal_ipw_msm"])
def test_a_confounder_set_is_held_to_the_one_recorded(shape):
    program, result = _pair(shape)
    result["numeric_estimate"][shape]["confounders_by_time"] = [["L0"], ["L0"]]
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(program, result)


# ------------------------------------ the four values nothing else records


@pytest.mark.parametrize("field,forged", [
    ("observed_x", False),
    ("counterfactual_x", True),
    ("target_y", False),
    ("factual_y", True),
])
def test_a_cell_cannot_say_it_is_a_different_cell(field, forged):
    """Which of the four cells this is, held to the question.

    No step records them, so no re-derivation can find them wrong: the
    plug-in reads them as the INPUTS that decide which quantity to compute.
    Change one and the arithmetic re-derives a bound that agrees with
    itself everywhere — an answer about a counterfactual nobody asked for.
    """
    program, result = _pair("counterfactual_cell_plugin")
    result["numeric_estimate"]["counterfactual_cell"][field] = forged
    with pytest.raises(VerificationError, match="the query asked about"):
        themis.verify(program, result)


def test_a_cell_that_forgets_it_had_a_factual_outcome_is_a_different_quantity():
    """Absence is an answer here, so it is compared and not skipped: with no
    factual outcome in the evidence the cell is the ETT identity, which is
    point-identified rather than bounded."""
    program, result = _pair("counterfactual_cell_plugin")
    result["numeric_estimate"]["counterfactual_cell"]["factual_y"] = None
    with pytest.raises(VerificationError, match="the query asked about"):
        themis.verify(program, result)


# ------------------------------------------------- one fact, one shape

def test_an_adjustment_set_travels_as_the_names_it_is():
    """What blocked the fallback, and why it is the encoding that moved.

    These two routes standardize over data columns, so what travels is
    names — and they used to travel comma-joined into one string, from a
    time when the serializer took no sequence of strings. It has taken one
    for a while. A joined string cannot tell a set of two apart from a
    column whose name holds a comma, and the reader's copy beside it is a
    list, so the two could not be compared at all.
    """
    for shape in ("causation_plugin", "counterfactual_cell_plugin"):
        steps = SHAPES[shape]["result"]["derivation"]["steps"]
        recorded = steps[-1]["inputs"]["adjustment"]
        assert isinstance(recorded, dict), recorded
        assert isinstance(recorded.get("items"), list), recorded
        assert display._plain(recorded) == ["z"]
