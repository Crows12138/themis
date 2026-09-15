"""Which weights a number was taken over is recorded once.

That one bit used to be in an IPW envelope five times: ``method``, whose two
members ARE the two forms; the derivation step that produced the number; the
mechanism audit's record of the fit; the estimator's own
``hajek_stabilized_weights`` / ``horvitz_thompson_weights`` declaration, which
reaches a reader as a sentence; and a boolean ``stabilized`` beside them.

Measured with the leaf sweep's own door set — every public ``themis.verify*``
entry point rather than one of them: bending any of the first four is refused,
bending all of them together is still refused, and bending the boolean was
accepted by all thirteen doors that read that answer. It was written by the
layer that had just passed the lever in, a field copied off the estimate on the
way out, and nothing read it: no rule, no report, not the browser's own type
for that block. From a JSON program it could not be anything but ``true``,
because the weights lever is only reachable on the time-varying estimator.

So it is gone rather than held — the third answer to "nobody reads it", beside
rendering it and leaving it to a consumer who is not a reader. What is held
here is what that leaves: the records still in the envelope, the lies still
refused, the reader still shown which weights, a contract that refuses the
boolean if a producer writes it again, and the time-varying block's own
``stabilized``, which stays for the opposite reason — a reader is shown it and
a rule holds it to the program.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import kernel
from themis.estimation.aipw import estimate_ipw_ate
from themis.input.syntactic_validator import SyntacticError, validate_result
from themis.output.analysis_report import build_analysis_report
from themis.verifier import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))

ROW = SHAPES["ipw_stabilized"]
HAJEK = "hajek_stabilized_weights"
HORVITZ_THOMPSON = "horvitz_thompson_weights"


def _frame(rng, n=3000):
    """One confounder, both nuisances linear in it, true ATE = 2."""
    z = rng.normal(0, 1, n)
    a = rng.binomial(1, 1.0 / (1.0 + np.exp(-1.2 * z))).astype(float)
    y = 2.0 * a + 3.0 * z + rng.normal(0, 1, n)
    return pd.DataFrame({"A": a, "Y": y, "Z": z})


def _program():
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    Z = {"predicate": "Z", "args": [{"type": "const", "name": "u"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "variable", "predicate": "Z"},
            {"kind": "cause", "from": Z, "to": A},
            {"kind": "cause", "from": Z, "to": Y},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True}, "given": []}},
        ],
    }


def test_an_ipw_answer_says_which_weights_where_it_is_read():
    """The live producer, not the snapshot: the envelope carries the method
    and the declaration, and nothing beside them."""
    program = _program()
    result = kernel.estimate(program, _frame(np.random.default_rng(0)),
                             random_state=1, ate_estimator="ipw")["results"][0]
    estimate = result["numeric_estimate"]
    assert estimate["method"] == "ipw_stabilized"
    assert HAJEK in estimate["assumptions"]
    assert "stabilized" not in estimate, (
        "the weight form is in the envelope a second time, as a boolean no "
        "rule and no reader reads")
    validate_result(result)
    themis.verify(program, result)


@pytest.mark.parametrize("lever, method, token", [
    (None, "ipw_stabilized", HAJEK),
    (True, "ipw_stabilized", HAJEK),
    (False, "ipw_ht", HORVITZ_THOMPSON),
])
def test_the_estimate_keeps_one_record_of_the_lever_it_was_given(
        lever, method, token):
    """Including the position the caller cannot reach through a program: the
    estimate says which weights in the method's own name, and the boolean it
    used to say it in a second time is not a field."""
    keywords = {} if lever is None else {"stabilized": lever}
    estimate = estimate_ipw_ate(
        _frame(np.random.default_rng(1)), treatment="A", outcome="Y",
        adjustment=("Z",), ci_bootstrap=0, **keywords)
    assert estimate.method == method
    assert token in estimate.assumptions
    assert not hasattr(estimate, "stabilized")


def test_the_contract_refuses_the_boolean_if_a_producer_writes_it_again():
    """``numeric_estimate`` is closed, so the deletion is enforced by the
    document the door validates against rather than by memory."""
    forged = copy.deepcopy(ROW["result"])
    forged["numeric_estimate"]["stabilized"] = True
    with pytest.raises(SyntacticError) as refused:
        validate_result(forged)
    assert "stabilized" in str(refused.value)


def test_the_stored_ipw_answer_is_accepted_as_it_stands():
    themis.verify(ROW["program"], ROW["result"])


@pytest.mark.parametrize("bend", ["method", "declaration", "both together"])
def test_which_weights_is_still_refused_when_it_is_bent(bend):
    """What the boolean's four companions buy, which is what deleting it had
    to leave standing. The last case is the self-consistent forgery: every
    copy flipped at once, refused by the derivation step that produced the
    number and by the ledger the estimator declared into."""
    forged = copy.deepcopy(ROW["result"])
    estimate = forged["numeric_estimate"]
    if bend in ("method", "both together"):
        estimate["method"] = "ipw_ht"
    if bend in ("declaration", "both together"):
        assumptions = estimate["assumptions"]
        assumptions[assumptions.index(HAJEK)] = HORVITZ_THOMPSON
    with pytest.raises(VerificationError):
        themis.verify(ROW["program"], forged)


def test_the_reader_is_still_shown_which_weights():
    said = build_analysis_report(ROW["result"], program=ROW["program"])
    assert "Hájek 稳定化权重" in said
    assert "ipw_stabilized" in said


def test_the_time_varying_block_keeps_its_own_because_a_reader_reads_it():
    """One word, deleted in one place and required in another. The MSM block
    shows its weight form to a reader in a sentence and a rule holds it to
    ``options.longitudinal``; the top-level boolean did neither."""
    declared = SCHEMA["properties"]["numeric_estimate"]["properties"]
    assert "stabilized" not in declared
    msm = declared["longitudinal_ipw_msm"]
    assert "stabilized" in msm["properties"]
    assert "stabilized" in msm["required"]
    row = SHAPES["longitudinal_ipw_msm"]
    said = build_analysis_report(row["result"], program=row["program"])
    assert "稳定化权重" in said
