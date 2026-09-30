"""The tier of a causation answer reads all three of its quantities.

A causation question asks for the probabilities of necessity, of sufficiency,
and of both, and the answer prints all three. Its ``numeric_result`` carries
one of them — PN, the headline — and that was what the report's tier read: a
PN spanning [0, 1] made the report tell the reader no answer was available,
and withdraw its offer of an interval, beside a PS and a PNS that excluded
most of the line. The verifier read the other way and no more closely: a
causation block on the envelope counted as an interval in hand whatever its
bounds said. The two disagreed on exactly the answers where the headline is
vacuous, and the verifier refused them.

Both now read the block's three quantities, each for itself: an interval is
in hand where any of them rules part of [0, 1] out, and not where all three
span it.
"""
from __future__ import annotations

import copy

import pytest

from themis import kernel
from themis.output.data_gap_report import _compute_answer_tier
from themis.types import (
    AnswerTier, NumericInterval, NumericResult, QueryKind, ResultStatus,
)
from themis.verifier.data_gap_rules import _an_interval_is_in_hand
from themis.verifier.errors import VerificationError

X = {"predicate": "drug", "args": [{"type": "const", "name": "p"}]}
Y = {"predicate": "death", "args": [{"type": "const", "name": "p"}]}


def _program():
    """P(x) = 0.5 and P(y | x) = P(y | x') = 0.3, with the two risks measured
    in a trial at 0.3 and 0.4. PN's bounds are then [0, 1] exactly — its
    lower bound (P(y) − P(y | do(x'))) / P(x, y) is negative and its upper
    (P(y' | do(x')) − P(x', y')) / P(x, y) is above one — while PS lies in
    [0, 3/7] and PNS in [0, 0.3]."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": X, "to": Y},
            {"kind": "bidirected", "left": X, "right": Y},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}], "value": 0.3},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}], "value": 0.3},
            {"kind": "query", "id": "q1", "query": {
                "kind": "causation", "cause": X, "effect": Y,
                "experimental_risk_treated": 0.3,
                "experimental_risk_control": 0.4}},
        ],
    }


def _answer():
    program = _program()
    (result,) = kernel.run(copy.deepcopy(program))["results"]
    return program, result


def test_a_vacuous_headline_beside_an_informative_ps_is_an_interval():
    program, result = _answer()
    assert result["status"] == "counterfactual_bounded", result["status"]
    causation = result["extensions"]["causation"]
    assert (causation["pn"]["lower"], causation["pn"]["upper"]) == (0.0, 1.0)
    assert causation["ps"]["upper"] == pytest.approx(3 / 7)
    assert causation["pns"]["upper"] == pytest.approx(0.3)
    assert result["numeric_result"]["interval"] == {"low": 0.0, "high": 1.0}
    assert result["data_gap_report"]["answer_tier"] == "interval"
    kernel.verify(copy.deepcopy(program), result)


def test_calling_it_no_answer_is_refused():
    program, result = _answer()
    forged = copy.deepcopy(result)
    forged["data_gap_report"]["answer_tier"] = "none"
    with pytest.raises(VerificationError, match="no answer is available"):
        kernel.verify(copy.deepcopy(program), forged)


# --- the two readings agree, block by block ----------------------------------

_WHOLE_LINE = {"lower": 0.0, "upper": 1.0, "point": None}


def _block(**quantities):
    return {name: quantities.get(name, _WHOLE_LINE)
            for name in ("pn", "ps", "pns")}


@pytest.mark.parametrize("block, tier", [
    (_block(), AnswerTier.NONE),
    (_block(pn={"lower": 0.2, "upper": 1.0, "point": None}),
     AnswerTier.INTERVAL),
    (_block(ps={"lower": 0.0, "upper": 0.43, "point": None}),
     AnswerTier.INTERVAL),
    (_block(pns={"lower": 0.0, "upper": 0.3, "point": None}),
     AnswerTier.INTERVAL),
], ids=["all three span the line", "pn rules some out",
        "ps rules some out", "pns rules some out"])
def test_producer_and_verifier_read_the_same_block_the_same_way(block, tier):
    """The headline spans the line in every case, so the headline alone
    would say NONE to all four."""
    produced = _compute_answer_tier(
        QueryKind.CAUSATION, [], (), ResultStatus.COUNTERFACTUAL_BOUNDED,
        NumericResult(value=None,
                      interval=NumericInterval(low=0.0, high=1.0)),
        None, {"causation": block})
    assert produced is tier
    envelope = {"numeric_result": {"value": None,
                                   "interval": {"low": 0.0, "high": 1.0}},
                "extensions": {"causation": block}}
    assert _an_interval_is_in_hand(envelope) is (tier is AnswerTier.INTERVAL)
