"""Every check about a resampling loop starts at the block it left behind.

``check_bootstrap_record`` holds a block to its own arithmetic,
``_check_every_count_is_the_runs`` holds its count to the run's ask,
``_check_the_losses_add_up`` to its own reasons, and the two
``_check_every_stamp_says_what_the_estimator_declared`` in
:mod:`themis.verifier.cluster_inference_rules` hold what a block says to
what the estimator declared. All five begin AT a block. **A loop that left
no block was therefore audited by nobody**: the count that is not there
adds up, the species that are not there are all registered, the floor that
is not there is cleared, and the interval printed beside them rests on
whatever number the reader supplies.

MEASURED END TO END BEFORE IT WAS WRITTEN. An ordinary backdoor run asked
for forty replicates, with the block deleted from the envelope and nothing
else touched, passed ``verify``, ``verify_answer_claims``,
``verify_assumption_ledger``, ``verify_bootstrap_draws`` AND
``verify_cluster_inference`` — five public doors, no refusal.

WHY IT IS ASKABLE, which is the part that was not obvious. The registered
version of this gap proposed a source-level assertion: that every attach
point in the dispatch layer calls ``_attach_bootstrap_meta``. That reads
the producer's call sites, so it counts by name and misses the two places
that write the block by hand — and any future third. The envelope answers
it without reading any source, because the sentence and the block are ONE
object's two statements: :meth:`Draws.declares` writes the sentence when
the loop drew enough replicates for an interval to be reportable at all,
:meth:`Draws.record` writes the block whenever a loop ran, and the first
condition implies the second. So a sentence with no block is a
contradiction inside one answer.

ONE DIRECTION ONLY, and the other side is witnessed below: a block with no
sentence is the honest shape of a loop that ran and lost too many draws to
let its estimator claim anything.
"""
from __future__ import annotations

import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.resample import Draws
from themis.verifier.bootstrap_rules import (
    _DECLARES_A_RESAMPLED_INTERVAL,
    verify_bootstrap_records,
)
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _atom(predicate):
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_BACKDOOR = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "u"}]},
    "statements": [
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "variable", "predicate": "z"},
        _cause("x", "y"), _cause("z", "x"), _cause("z", "y"),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True}, "given": []}},
    ],
}


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 600
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.25 + 0.4 * z).astype(int)
    y = (rng.random(n) < np.clip(0.2 + 0.3 * x + 0.2 * z, 0, 1)).astype(int)
    return pd.DataFrame({"x": x, "y": y, "z": z, "g": rng.integers(0, 30, n)})


def _run(frame, **options):
    out = themis.estimate(_BACKDOOR, frame, **options)
    return out["results"][0]


def _sentences(estimate) -> list[str]:
    return [str(item) for item in (estimate.get("assumptions") or ())
            if str(item).startswith("ci_via_")]


def _blocks(node, under="numeric_estimate"):
    """Every bootstrap block on an estimate, written here rather than
    imported so the test does not share the rule's blindness."""
    if isinstance(node, dict):
        if isinstance(node.get("bootstrap"), dict):
            yield under
        for key, value in node.items():
            if key != "bootstrap":
                yield from _blocks(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from _blocks(value, under)


def _strip_blocks(node) -> None:
    if isinstance(node, dict):
        node.pop("bootstrap", None)
        for value in node.values():
            _strip_blocks(value)
    elif isinstance(node, list):
        for value in node:
            _strip_blocks(value)


# --- the sentence the rule reads is the one the loop writes ---------------


def test_the_sentence_this_rule_reads_is_the_one_the_loop_writes():
    """The two copies, pinned to each other. The verifier restates the
    sentence rather than importing it — the package's independence pin —
    so what keeps the restatement true is this, read off the object that
    writes it."""
    draws = Draws(5)
    for _ in draws:
        draws.usable()
    assert draws.enough
    assert draws.declares(cluster=None) == (_DECLARES_A_RESAMPLED_INTERVAL,)
    assert draws.declares(cluster="g")[0] == _DECLARES_A_RESAMPLED_INTERVAL


def test_the_sentence_has_exactly_one_writer():
    """THE PREMISE, stated because the rule cannot state it: pairing the
    sentence with the block is sound only while the sentence has a single
    writer. A second producer spelling it beside a loop of its own — or
    without one — would make an answer carry it for a reason this rule
    does not know about, and the rule would be refusing honest work.

    Three holders, one role each: the loop that writes it, the glossary
    that translates it for a reader, and this verifier's restated copy.
    A fourth is not necessarily wrong, but it is the thing a person has to
    look at before this pairing keeps its meaning.
    """
    holders = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.joinpath("themis").rglob("*.py")
        if _DECLARES_A_RESAMPLED_INTERVAL in path.read_text(encoding="utf-8")
    )
    assert holders, "the scan found no copy at all; it is measuring nothing"
    assert holders == [
        "themis/assumption_glossary.py",       # translates it
        "themis/estimation/resample.py",       # writes it
        "themis/verifier/bootstrap_rules.py",  # restates it
    ]


def test_the_producer_writes_no_sentence_where_no_interval_is_reportable():
    """The condition that makes the implication run: the sentence appears
    only above the floor, and the block appears wherever a loop ran, so
    sentence implies block and not the other way round."""
    starved = Draws(3)
    for _ in starved:
        starved.unusable()
    assert not starved.enough
    assert starved.declares(cluster=None) == ()
    assert starved.record(cluster=None)["requested"] == 3


# --- the honest answers, both ways ----------------------------------------


@pytest.mark.parametrize("cluster", [None, "g"])
def test_a_run_that_resampled_says_so_and_shows_the_block(frame, cluster):
    """The shape this rule is about, before anything is bent: the sentence
    and the block arrive together on every ordinary run."""
    result = _run(frame, ci_bootstrap=40, cluster=cluster)
    estimate = result["numeric_estimate"]
    assert _DECLARES_A_RESAMPLED_INTERVAL in _sentences(estimate)
    assert sorted(set(_blocks(estimate))) == ["numeric_estimate"]
    themis.verify_bootstrap_draws(result)
    themis.verify(_BACKDOOR, result)


def test_a_run_asked_for_no_interval_says_nothing_and_owes_nothing(frame):
    """The first of the two acceptances that keep this from being a rule
    that refuses ordinary work. No loop ran, so there is no sentence and
    nothing is owed."""
    result = _run(frame, ci_bootstrap=0)
    estimate = result["numeric_estimate"]
    assert _sentences(estimate) == []
    assert list(_blocks(estimate)) == []
    themis.verify_bootstrap_draws(result)
    themis.verify(_BACKDOOR, result)


def test_a_block_with_no_sentence_is_a_loop_that_lost_too_many(frame):
    """The second, and the reason this rule holds one direction only. A
    loop that ran and did not clear the floor writes the block and says
    nothing, and refusing that would refuse the honest report of a
    resample that could not support an interval."""
    result = _run(frame, ci_bootstrap=40)
    starved = copy.deepcopy(result)
    estimate = starved["numeric_estimate"]
    estimate["assumptions"] = [
        item for item in estimate["assumptions"]
        if not str(item).startswith("ci_via_")
    ]
    assert list(_blocks(estimate)) == ["numeric_estimate"]
    themis.verify_bootstrap_draws(starved)


# --- and the answer that says it resampled and shows nothing --------------


def test_a_sentence_with_no_block_is_refused(frame):
    """The hole, at the size it was measured. Nothing else about the
    envelope is touched: the interval, the point, the ledger and the
    sentence all stay exactly as the run wrote them."""
    result = _run(frame, ci_bootstrap=40)
    forged = copy.deepcopy(result)
    _strip_blocks(forged["numeric_estimate"])
    assert _DECLARES_A_RESAMPLED_INTERVAL in _sentences(
        forged["numeric_estimate"])
    assert list(_blocks(forged["numeric_estimate"])) == []
    assert forged["numeric_estimate"]["ci_lower"] is not None

    with pytest.raises(VerificationError) as caught:
        themis.verify_bootstrap_draws(forged)
    assert caught.value.rule == "bootstrap_draws_check"
    assert _DECLARES_A_RESAMPLED_INTERVAL in str(caught.value)


def test_the_refusal_is_reached_through_the_door_a_caller_uses(frame):
    """A rule in this package that only the package's own entry point
    reaches would hold nothing a caller does."""
    forged = copy.deepcopy(_run(frame, ci_bootstrap=40))
    _strip_blocks(forged["numeric_estimate"])
    with pytest.raises(VerificationError):
        themis.verify(_BACKDOOR, forged)
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(_BACKDOOR, forged)


def test_the_cluster_pairing_still_declines_this_one(frame):
    """Which rule refuses it, asked rather than assumed. The pairing one
    module over compares a block to the sentence and is silent where there
    is no block — deliberately, and it says so — so leaving it silent here
    is what makes this a new hold rather than a second spelling of one
    that already exists."""
    forged = copy.deepcopy(_run(frame, ci_bootstrap=40, cluster="g"))
    _strip_blocks(forged["numeric_estimate"])
    themis.verify_cluster_inference(forged)
    themis.verify_assumption_ledger(forged)
    with pytest.raises(VerificationError):
        themis.verify_bootstrap_draws(forged)


def test_a_block_one_level_down_is_a_block():
    """The reach, on a shape this build does not currently produce. Two
    families put a second loop under a block of its own and stamp both
    levels; none stamps only the lower one. Read at every depth anyway,
    because the sentence is one flat list describing however many loops
    ran, so 'a block' is the most this pairing can ask for and it has to
    find one wherever the answer keeps it.

    Built here rather than run, the way this module's other depth
    witnesses are: what is under test is where the rule looks, and a
    fabricated estimate says that in four lines."""
    verify_bootstrap_records({"numeric_estimate": {
        "method": "mediation_logit_imai", "point": 0.3,
        "assumptions": [_DECLARES_A_RESAMPLED_INTERVAL],
        "four_way_ratio": {
            "cde": {"point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3},
            "bootstrap": {"kind": "iid", "requested": 50, "used": 50}}}})


def test_the_same_estimate_with_that_block_removed_is_refused():
    """The other side of the line above, one field apart: the same
    fabricated answer with nothing left to describe its loop."""
    with pytest.raises(VerificationError):
        verify_bootstrap_records({"numeric_estimate": {
            "method": "mediation_logit_imai", "point": 0.3,
            "assumptions": [_DECLARES_A_RESAMPLED_INTERVAL],
            "four_way_ratio": {
                "cde": {"point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3}}}})
