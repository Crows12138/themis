"""The flag that decides whether a strategy contrast gets a number at all.

``extensions.longitudinal_identification.identified`` says the g-formula
point-identifies E[Y_ā=treated] − E[Y_ā=control]; false says an unblocked
back door remains at some treatment and the numeric layer refuses.
``verify_longitudinal_numeric`` audits the numbers under it and reads
``numeric_estimate`` — so it audits what this flag licensed and never the
flag. Nor the history the flag is a claim about: the treatments could be
reordered in time, a covariate block emptied, the outcome renamed to a
treatment, and the answer passed the public door.

Two things are checked and they differ in kind.

The block has to describe the strategy the PROGRAM declared. Treatments,
outcome and per-time covariate blocks all come from
``options.longitudinal``, and the order is part of the description, because
the history is built by walking it — H_k is every covariate block up to and
including k plus the treatments before k, so a swapped pair is a different
history at every later time.

And the criterion has to hold, per time: the ordinary back-door criterion
asked K times of a growing set. Both halves are exercised separately below,
because a check that only ever compared the block to the spec would pass
every graph.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.structural_solver import bidirected_from_ground
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_longitudinal_identification


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _graph_of(program):
    """The two premises the rule reads, built the way the door builds them.

    Reaching for the rule directly is not a shortcut around the door: it is
    the only way to hold a claim the door never sees, and the premises have
    to be the same premises or the test would be checking something else.
    """
    ground = instantiate(validate_program(validate_ast(copy.deepcopy(program))))
    return project(ground), bidirected_from_ground(ground)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "subj"}]}


def _program(extra=()):
    statements = [
        {"kind": "variable", "predicate": "L0"},
        {"kind": "variable", "predicate": "A0", "domain": [True, False]},
        {"kind": "variable", "predicate": "L1"},
        {"kind": "variable", "predicate": "A1", "domain": [True, False]},
        {"kind": "variable", "predicate": "Y"},
        {"kind": "cause", "from": _atom("A0"), "to": _atom("L1")},
        {"kind": "cause", "from": _atom("L1"), "to": _atom("A1")},
        {"kind": "cause", "from": _atom("L1"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("A0"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("A1"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("L0"), "to": _atom("A0")},
        {"kind": "cause", "from": _atom("L0"), "to": _atom("Y")},
        *extra,
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "target": {"atom": _atom("Y"), "value": True},
            "intervention": {"atom": _atom("A1"), "value": True},
            "given": []}},
    ]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "subj"}]},
            "options": {"longitudinal": {
                "estimator": "gformula", "treatments": ["A0", "A1"],
                "confounders_by_time": [["L0"], ["L1"]], "outcome": "Y",
                "strategy_treated": 1, "strategy_control": 0,
                "n_sim": 500, "ci_bootstrap": 0}},
            "statements": statements}


IDENTIFIED = _program()

#: An unmeasured common cause of the last treatment and the outcome. The
#: measured history cannot block it, so sequential exchangeability fails.
CONFOUNDED = _program(
    [{"kind": "bidirected", "left": _atom("A1"), "right": _atom("Y")}])


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(8)
    n = 1500
    L0 = rng.normal(0, 1, n)
    A0 = rng.random(n) < _expit(0.5 * L0)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.8 * L1 - 0.4)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + rng.normal(0, 1, n)
    return pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1, "Y": Y})


def _answer(program, frame):
    return themis.estimate(program, frame, ci_bootstrap=0)["results"][0]


def _block(result):
    return result["extensions"]["longitudinal_identification"]


def _refuses(program, result, fragment):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


def _tampered(program, frame, change):
    result = copy.deepcopy(_answer(program, frame))
    change(_block(result))
    return result


# ------------------------------------------------------------- denominators


def test_an_untouched_identified_answer_passes(frame):
    result = _answer(IDENTIFIED, frame)
    assert _block(result)["identified"] is True
    themis.verify(IDENTIFIED, result)


def test_an_honest_refusal_passes_too(frame):
    """The other side of the flag, held against the rule directly, and the
    reason is worth recording: a result whose identification failed carries
    no derivation, and ``themis.verify`` declines those before it reads any
    block. So this face of the flag reaches a reader through the report and
    the gap list and reaches the public door not at all — the same boundary
    #506 measured on the feedback-loop route, and a fact about where the
    audit begins rather than about this block."""
    result = _answer(CONFOUNDED, frame)
    assert _block(result)["identified"] is False
    assert result.get("derivation") is None, result.get("derivation")
    with pytest.raises(ValueError, match="requires a result with a "):
        themis.verify(CONFOUNDED, result)
    verify_longitudinal_identification(
        _block(result), CONFOUNDED["options"]["longitudinal"],
        *_graph_of(CONFOUNDED))


# ---------------------------------------------------- the criterion itself


def test_claiming_identification_where_a_back_door_remains_is_refused(frame):
    """The forgery that matters: it turns a refusal into a number, and the
    number is biased by exactly the path the history cannot block. Held
    against the rule for the reason above."""
    block = copy.deepcopy(_block(_answer(CONFOUNDED, frame)))
    block["identified"] = True
    with pytest.raises(VerificationError) as caught:
        verify_longitudinal_identification(
            block, CONFOUNDED["options"]["longitudinal"],
            *_graph_of(CONFOUNDED))
    assert "does not block every back-door path" in str(caught.value), \
        str(caught.value)


def test_denying_an_identification_the_history_supports_is_refused(frame):
    _refuses(IDENTIFIED, _tampered(
        IDENTIFIED, frame, lambda b: b.__setitem__("identified", False)),
        "while the measured history does block every back-door path")


def test_claiming_identification_with_no_premise_named_is_refused(frame):
    """Sequential exchangeability is untestable, so naming it is the whole
    disclosure; a claim without it is the claim with its price removed."""
    _refuses(IDENTIFIED, _tampered(
        IDENTIFIED, frame, lambda b: b.__setitem__("assumptions", [])),
        "names none of the untestable premises")


# ------------------------------------------------ the strategy as declared


def test_reordering_the_treatments_in_time_is_refused(frame):
    """H_k is built by walking this list, so a swapped pair is a different
    history at every later time — not a cosmetic reordering."""
    _refuses(IDENTIFIED, _tampered(IDENTIFIED, frame, lambda b: b.__setitem__(
        "treatments", ["A1(subj)", "A0(subj)"])),
        "records treatments=['A1', 'A0'] while the program declares")


def test_a_treatment_list_naming_a_confounder_is_refused(frame):
    _refuses(IDENTIFIED, _tampered(IDENTIFIED, frame, lambda b: b.__setitem__(
        "treatments", ["A0(subj)", "L1(subj)"])), "while the program declares")


def test_a_renamed_outcome_is_refused(frame):
    _refuses(IDENTIFIED, _tampered(IDENTIFIED, frame, lambda b: b.__setitem__(
        "outcome", "A1(subj)")), "records outcome='A1' while the program")


@pytest.mark.parametrize("blocks", [
    [["L0(subj)"], []],
    [["L0(subj)"], ["Y(subj)"]],
])
def test_a_rewritten_covariate_history_is_refused(frame, blocks):
    _refuses(IDENTIFIED, _tampered(IDENTIFIED, frame, lambda b: b.__setitem__(
        "confounders_by_time", blocks)),
        "records confounders_by_time=")


def test_a_history_with_fewer_blocks_than_treatments_is_refused(frame):
    """Walked together or not at all: a block list shorter than the
    treatment list has no k-th entry to add before the k-th treatment."""
    result = copy.deepcopy(_answer(IDENTIFIED, frame))
    block = _block(result)
    block["confounders_by_time"] = [["L0(subj)"]]
    with pytest.raises(VerificationError) as caught:
        themis.verify(IDENTIFIED, result)
    assert ("covariate block" in str(caught.value)
            or "while the program declares" in str(caught.value)), \
        str(caught.value)
