"""A loop resampled one thing, and this envelope says what twice.

``numeric_estimate.bootstrap`` is written by the dispatch layer from the
estimator's ``cluster`` attribute; ``numeric_estimate.assumptions`` carries
the estimator's own ``ci_via_pairs_cluster_bootstrap_on_<column>``. Two
records of one loop, a call site apart — the arrangement
:mod:`themis.verifier.cluster_inference_rules` exists to exploit, because
neither hand can corroborate itself.

It held them in one direction only. Every check that module had begins at
the stamp: the block claims a cluster bootstrap, so does the run agree, does
the column match, does the estimator's declaration corroborate it. Nothing
asked the question the other way round, and a stamp that says LESS than the
estimator declared is corroborated by nobody and was therefore refused by
nobody. Measured through the public door on a run that really did resample
clusters: rewriting ``kind`` to ``iid`` was accepted by every door, and so
was a block left saying ``iid`` while still naming the column it had
supposedly ignored.

What that ships is the failure the module's own opening paragraph names —
an interval computed on dependent rows, labelled as resting on independent
ones, identical on the page and narrower than the evidence supports. It is
also how the missing direction was found: #600 measured a route that
dropped the cluster column entirely, and the answer that came back said
``iid`` and was accepted by its own cluster audit.

TWO THINGS THIS FILE HOLDS APART FROM EACH OTHER. Asking whether a
declaration MENTIONS a column is wording-agnostic on purpose — estimators
say it in several registers and pinning one spelling would make the audit a
transcription of the producer's string format. Asking which register a
declaration is IN cannot be: "I resampled the clusters" and "I ignored them
and say so" both name the column, and a reading that cannot tell them apart
cannot ask this question. So the one register that asserts a loop is named,
once, and pinned to the glossary that registers it and to what the
estimators actually emit.

WHERE THIS RULE IS SILENT, asserted rather than left to be discovered. It
says nothing when there is no stamp at all, because a run told to cluster
and asked for no replicates draws nothing and declares the cluster
bootstrap anyway — measured on every family. That is a defect of its own,
in the declaration rather than in the stamp, and it is what makes the
silence necessary here: refusing it would refuse every honest clustered
answer that carries no interval.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.assumption_glossary import is_classified
from themis.estimation.dispatch import (
    _RESAMPLED_WHOLE_CLUSTERS as _PRODUCER_SAYS,
)
from themis.verifier.cluster_inference_rules import (
    _RESAMPLED_WHOLE_CLUSTERS as _READER_SAYS,
    verify_cluster_inference,
)
from themis.verifier.errors import VerificationError

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

_CLUSTERED = {"kind": "cluster", "cluster_column": "clinic",
              "requested": 40, "used": 40}
_IID = {"kind": "iid", "requested": 40, "used": 40}


def _result(*, run_cluster="clinic", assumptions=(), bootstrap=None,
            extra=None) -> dict:
    estimate: dict = {"method": "backdoor_linear",
                      "assumptions": list(assumptions),
                      "point": 0.5, "ci_lower": 0.1, "ci_upper": 0.9}
    if bootstrap is not None:
        estimate["bootstrap"] = copy.deepcopy(bootstrap)
    estimate.update(extra or {})
    context = {} if run_cluster is None else {"cluster": run_cluster}
    return {"estimation_context": context, "numeric_estimate": estimate}


# ================================================ the word, in two places


def test_the_two_copies_of_the_register_are_one_register():
    """The verifier may not import the estimation layer, so the producer's
    door and the reader's each name it, and drift between them is what this
    pins. A stamp checked against a prefix nobody emits is a check that
    never speaks."""
    assert _PRODUCER_SAYS == _READER_SAYS


def test_the_register_is_one_the_glossary_registers():
    """Not a string invented in a verifier: the glossary carries it, which
    is what keeps the parity test that follows the estimators reaching it
    too."""
    assert is_classified(_READER_SAYS + "clinic")


# ===================================================== the missing direction


def test_a_clustered_run_that_says_so_is_accepted():
    """First in intent even where it sits here: the honest shape."""
    verify_cluster_inference(_result(
        assumptions=[_READER_SAYS + "clinic"], bootstrap=_CLUSTERED))


def test_a_stamp_that_says_iid_after_the_estimator_declared_clusters():
    """The forgery every door accepted."""
    with pytest.raises(VerificationError, match="resampled whole clusters"):
        verify_cluster_inference(_result(
            assumptions=[_READER_SAYS + "clinic"], bootstrap=_IID))


def test_a_stamp_that_contradicts_itself_is_refused_too():
    """``iid`` beside the very column it claims to have ignored. Two halves
    of one block disagreeing is not a lesser version of the forgery above —
    it is the same interval mislabelled, with a leftover that makes it look
    checked."""
    with pytest.raises(VerificationError, match="resampled whole clusters"):
        verify_cluster_inference(_result(
            assumptions=[_READER_SAYS + "clinic"],
            bootstrap={"kind": "iid", "cluster_column": "clinic",
                       "requested": 40, "used": 40}))


def test_a_nested_stamp_is_asked_the_same_question():
    """A decomposition puts a second loop under a block of its own, and the
    declarations are a flat list belonging to the estimate — so a stamp one
    level down is not exempt from a claim made about the answer. Measured
    on a clustered binary-outcome mediation: both stamps say cluster
    today, which is why requiring it refuses nothing honest."""
    with pytest.raises(VerificationError, match="four_way_ratio"):
        verify_cluster_inference(_result(
            assumptions=[_READER_SAYS + "clinic"], bootstrap=_CLUSTERED,
            extra={"four_way_ratio": {"bootstrap": dict(_IID)}}))


def test_a_stamp_naming_a_different_column_than_the_declaration():
    """One loop ran, so one column was resampled. A reader deciding whether
    the interval covers their unit of independence reads whichever of the
    two they happened to find."""
    with pytest.raises(VerificationError, match="resampled 'ward'"):
        verify_cluster_inference(_result(
            assumptions=[_READER_SAYS + "clinic"],
            bootstrap={"kind": "cluster", "cluster_column": "ward",
                       "requested": 40, "used": 40}))


# ===================================================== the other side


def test_an_estimator_that_declares_it_did_not_cluster_is_still_accepted():
    """The over-correction this rule is one bad reading away from. Both
    registers name the column; only one of them claims a loop. A check that
    keyed on the column would refuse the honest answer whose whole content
    is that it could not cluster and said so."""
    verify_cluster_inference(_result(
        assumptions=["ci_not_cluster_robust_analytic_interval_ignores_"
                     "clinic"],
        bootstrap=_IID))


def test_a_cluster_robust_variance_owes_no_bootstrap_stamp():
    """The third register: cluster-robust by a route that is not a
    resample. There is no loop, so there is no stamp to agree with."""
    verify_cluster_inference(_result(
        assumptions=["cluster_robust_influence_variance_on_clinic"],
        bootstrap=None))


def test_a_run_that_named_no_cluster_is_untouched():
    verify_cluster_inference(_result(run_cluster=None, bootstrap=_IID))


def test_a_declaration_with_no_stamp_at_all_is_accepted():
    """The silence, asserted so that closing it is a visible decision.

    A run told to cluster and asked for no replicates draws nothing and
    declares the cluster bootstrap regardless — measured below on every
    family. So an absent block is the ordinary shape of a clustered answer
    with no interval, and refusing it here would refuse honest answers.
    The declaration written whether or not the loop ran is a defect of its
    own, and it belongs where the declaration is written."""
    verify_cluster_inference(_result(
        assumptions=[_READER_SAYS + "clinic"], bootstrap=None))


# ===================================================== through the door


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }


@pytest.fixture(scope="module")
def clustered_frame():
    rng = np.random.default_rng(7)
    groups, per = 40, 15
    n = groups * per
    clinic = np.repeat(np.arange(groups), per)
    shift = rng.normal(0, 1.2, groups)[clinic]
    z = rng.normal(0, 1, n) + 0.5 * shift
    x = (rng.random(n) < 1 / (1 + np.exp(-(0.7 * z)))).astype(float)
    y = 0.9 * x + 0.8 * z + shift + rng.normal(0, 1, n)
    return pd.DataFrame({"z": z, "x": x, "y": y, "clinic": clinic})


@pytest.fixture(scope="module")
def clustered_answer(clustered_frame):
    out = themis.estimate(_program(), clustered_frame,
                          cluster="clinic", ci_bootstrap=40)
    return out["results"][0]


def test_a_real_clustered_run_says_the_same_thing_twice(clustered_answer):
    """The denominator for everything above: a hand-built dict cannot show
    that the two records are both really written."""
    estimate = clustered_answer["numeric_estimate"]
    assert estimate["bootstrap"]["kind"] == "cluster"
    assert estimate["bootstrap"]["cluster_column"] == "clinic"
    assert _READER_SAYS + "clinic" in estimate["assumptions"]


def test_the_public_door_refuses_the_bent_stamp(clustered_answer):
    """Through ``themis.verify``, because a rule reachable only by calling
    its own module is a rule most callers do not have."""
    bad = copy.deepcopy(clustered_answer)
    bad["numeric_estimate"]["bootstrap"]["kind"] = "iid"
    bad["numeric_estimate"]["bootstrap"].pop("cluster_column", None)
    with pytest.raises(VerificationError):
        themis.verify(_program(), bad)


def test_the_producer_refuses_rather_than_shipping(clustered_answer):
    """The other door. A route that drops the column produces the mislabel
    itself, and a caller who never runs the verifier would ship it."""
    from themis.estimation.dispatch import (
        _check_every_stamp_says_what_the_estimator_declared as _producer,
    )
    _producer(clustered_answer)                 # the honest one passes
    bad = copy.deepcopy(clustered_answer)
    bad["numeric_estimate"]["bootstrap"]["kind"] = "iid"
    with pytest.raises(RuntimeError, match="resampled whole clusters"):
        _producer(bad)


@pytest.mark.parametrize("asked", [0, 20])
def test_every_family_declares_the_bootstrap_whether_or_not_it_ran(
        clustered_frame, asked):
    """The measurement the silence above rests on, kept where it can go
    stale: the declaration does not depend on a loop having run, so an
    absent stamp cannot be read as a dropped column."""
    out = themis.estimate(_program(), clustered_frame,
                          cluster="clinic", ci_bootstrap=asked)
    estimate = out["results"][0]["numeric_estimate"]
    assert _READER_SAYS + "clinic" in estimate["assumptions"]
    assert (estimate.get("bootstrap") is not None) == (asked > 0)


# ===================================================== the whole corpus


def test_no_answer_this_repository_produces_is_refused_by_this_rule():
    """The false-refusal side at the scale the corpus offers. A rule that
    reads a declaration one way and a stamp another would show up here
    before it showed up in a run."""
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        for one in (result.get("results") or [result]):
            if isinstance(one, dict):
                verify_cluster_inference(one)
