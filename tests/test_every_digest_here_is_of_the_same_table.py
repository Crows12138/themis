"""Four fingerprints ride on one answer, and nothing compared them.

The run's data contract, the estimator's own, the bound's, and the one in
the derivation step the verifier walks. Fifteen rules read a ``data_hash``
and each checks that it is sixty-four lowercase hex characters; none of
them looks at a second one. So an envelope whose bound was computed on one
frame and whose point came from another passed every check there was.

The relation was unwritable before #381, because **agreement is not
equality**: a Manski bound covers the exposure and the outcome where the
estimator whose point it brackets also covered the adjustment set, so the
two digests SHOULD differ. What has to hold is that the digest is a
function of the columns it covers — same list, same digest; different
list, different digest — plus that no answer stands on a column the run
never received, and that the chain's digest is of a table this answer
names.

Each of those was measured across every envelope the suite produces (312
carrying a digest, in 13 distinct fingerprint shapes) before being written
down as a rule; all five held with no exceptions. So the tests below are
the other half: each way of breaking one, and the rule saying no.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _frame(n=600, seed=1):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


@pytest.fixture(scope="module")
def answered():
    env = themis.estimate(_program(), _frame(), ci_bootstrap=0)
    return env["results"][0]


def _digests(result):
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.endswith("data_hash") \
                        and isinstance(value, str):
                    found.append(f"{path}/{key}")
                else:
                    walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}/{i}")

    walk(result, "")
    return found


# --- there is something here to disagree --------------------------------

def test_one_answer_really_does_carry_several_digests(answered):
    """A rule about agreement over one digest would be saying nothing."""
    paths = _digests(answered)
    assert len(paths) >= 3, paths
    assert "/estimation_context/data_hash" in paths
    assert "/numeric_estimate/data_hash" in paths
    assert any(p.startswith("/bounds_results/") for p in paths)
    assert any(p.startswith("/derivation/") for p in paths)


def test_agreement_is_not_equality(answered):
    """The bound's digest differs from the point's, and that is correct."""
    point = answered["numeric_estimate"]["data_hash"]
    bound = answered["bounds_results"][0]["numeric_data_hash"]
    assert point != bound
    assert (set(answered["bounds_results"][0]["numeric_data_columns"])
            < set(answered["numeric_estimate"]["data_columns"]))
    themis.verify_fingerprints_agree(answered)


def test_an_answer_with_no_data_behind_it_has_nothing_to_check():
    """Identification only: no digest, so no disagreement and no verdict."""
    result = themis.run(_program())["results"][0]
    assert not _digests(result)
    themis.verify_fingerprints_agree(result)


# --- each way of breaking it --------------------------------------------

def test_an_empty_denominator_is_refused(answered):
    tampered = copy.deepcopy(answered)
    tampered["numeric_estimate"]["data_columns"] = []
    with pytest.raises(VerificationError, match="digest of nothing"):
        themis.verify_fingerprints_agree(tampered)


def test_a_repeated_column_in_a_denominator_is_refused(answered):
    tampered = copy.deepcopy(answered)
    tampered["numeric_estimate"]["data_columns"] = ["x", "y", "y"]
    with pytest.raises(VerificationError, match="repeated column"):
        themis.verify_fingerprints_agree(tampered)


def test_two_digests_over_one_column_list_must_be_one_digest(answered):
    """The run's contract and the estimator's cover the same columns here,
    so a divergence between them is two runs reported as one."""
    tampered = copy.deepcopy(answered)
    assert (tampered["estimation_context"]["data_columns"]
            == tampered["numeric_estimate"]["data_columns"])
    tampered["numeric_estimate"]["data_hash"] = "0" * 64
    with pytest.raises(VerificationError, match="same columns"):
        themis.verify_fingerprints_agree(tampered)


def test_one_digest_over_two_column_lists_is_refused(answered):
    """A digest mixes each column's NAME before its values, so this pair
    cannot be equal — a producer that reports it copied it."""
    tampered = copy.deepcopy(answered)
    tampered["bounds_results"][0]["numeric_data_hash"] = (
        tampered["numeric_estimate"]["data_hash"]
    )
    with pytest.raises(VerificationError, match="copied rather than computed"):
        themis.verify_fingerprints_agree(tampered)


def test_an_answer_cannot_stand_on_a_column_that_never_arrived(answered):
    tampered = copy.deepcopy(answered)
    tampered["numeric_estimate"]["data_columns"] = ["x", "y", "z", "ghost"]
    tampered["numeric_estimate"]["data_hash"] = "a" * 64
    with pytest.raises(VerificationError, match="does not record as having"):
        themis.verify_fingerprints_agree(tampered)


def test_a_chain_about_another_table_is_refused(answered):
    """The derivation step carries a digest and no denominator, so this is
    the only thing that can notice it drifting."""
    tampered = copy.deepcopy(answered)
    step = tampered["derivation"]["steps"][1]
    assert "data_hash" in step["inputs"]
    assert "data_columns" not in step["inputs"]
    step["inputs"]["data_hash"] = "b" * 64
    with pytest.raises(VerificationError, match="chain is about a table"):
        themis.verify_fingerprints_agree(tampered)


# --- and it is reachable the way every audit is --------------------------

def test_the_audit_table_lists_it(answered):
    rows = themis.audit(_program(), answered)
    named = {row["audit"]: row for row in rows}
    assert "verify_fingerprints_agree" in named
    assert named["verify_fingerprints_agree"]["ok"]


def test_the_main_audit_runs_it_too(answered):
    """``verify`` bundles the checks that are about the envelope rather
    than about one block, and this is one of them."""
    tampered = copy.deepcopy(answered)
    tampered["bounds_results"][0]["numeric_data_hash"] = (
        tampered["numeric_estimate"]["data_hash"]
    )
    with pytest.raises(VerificationError, match="copied rather than computed"):
        themis.verify(_program(), tampered)
