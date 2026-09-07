"""How many draws an interval stands on, held to the number the run asked for.

``estimation_context`` records what a run was told and ``bootstrap`` records
what its loop drew, and until now nothing put the two side by side. Of the
five settings the run writes there, ``cluster``, ``ci_level`` and
``random_state`` each have a module holding them against something the
envelope says elsewhere; this one had none, and it is the largest family of
leaves the answer-shape census still reports as unwitnessed.

HOW MUCH OF THAT FAMILY THIS REACHES, said here rather than left to the
family's size. It is 120 rows and this closes 34. Of the rest, seventy-two
asked for no bootstrap and correctly carry no record, and twelve reported
an analytic interval and ran none — so those envelopes hold no second
record of the number at all, and by this repository's own rule a leaf with
no witness is an honest remainder rather than a hole. Refusing there would
invent an authority nothing on the envelope has. What this file is for is
the defect below, which was handing readers the wrong number; the count is
what came off with it.

WHAT THE MISSING HOLDER LET THROUGH. The count reaches an estimator by one
route: dispatch hands over the settings the caller gave, keyword by keyword,
under the name each parameter is spelled. A parameter spelled differently is
therefore not a wire that breaks loudly but one that was never drawn — the
call site simply has no such argument, the estimator's own default wins, and
the envelope goes on recording the caller's ask beside an interval built on
something else. Two mediation loops spelled it ``n_rep``, so every mediation
interval this system ever reported stood on two hundred draws: under a
caller who asked for five hundred, under one who asked for thirty, and under
one who asked for none at all, which ``kernel.estimate`` documents as the
way to skip the interval. Measured on the answer shapes, six of forty-six
resample counts were numbers nobody on their own envelope had decided, and
all six were that.

Nothing was inconsistent inside any of those blocks. Their losses added up,
their reasons were species, their intervals rested on more than one draw —
and the reader-facing sentence for them says "taken over N of M resamples",
so the number was being shown to people. What a block cannot check about
itself is whether the loop it describes was the one anybody ordered.

THE SAME CALL SITE dropped ``cluster`` on the joint route, one line below
the single-mediator route that passes it. A clustered run's joint mediation
therefore came back ``kind: iid`` — an anti-conservative interval on
dependent rows — and its own cluster audit accepted it, for a reason kept
open below.

So this file holds: the ceiling table is two statements and they agree; a
count outside what the run asked for is refused at the producer's door and
at the reader's; the block that legitimately draws fewer is accepted at its
ceiling and refused away from it; a fragment that is not a run is still
accepted; and the count the caller asks for is the count the intervals of
every mediation shape actually stand on.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import dispatch as producer
from themis.verifier.bootstrap_rules import (
    CEILING_BECAUSE,
    CEILINGS,
    _check_every_ceiling_says_why,
    verify_bootstrap_records,
)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


# ===================================================== the two declarations


def test_the_ceiling_is_declared_twice_and_the_two_agree():
    """Re-declared rather than imported, for the reason the module's
    independence pin gives: a ceiling read from the producer's own constant
    agrees with the producer by construction, so a build that quietly
    halved it would be agreed with rather than caught."""
    assert CEILINGS == {
        block: cap
        for block, (cap, _) in producer._LOOPS_UNDER_ITS_OWN_CEILING.items()
    }
    assert CEILINGS["four_way_ratio"] == producer._RATIO_BOOTSTRAP_CAP


def test_the_two_reasons_are_the_same_reason():
    """The producer states why a block departs and so does the reader's
    door, because each quotes it to whoever it refuses."""
    assert set(CEILING_BECAUSE) == set(CEILINGS)
    for block, (_, because) in producer._LOOPS_UNDER_ITS_OWN_CEILING.items():
        assert because == CEILING_BECAUSE[block]


def test_a_ceiling_with_no_reason_and_a_reason_with_no_ceiling_are_refused():
    """Both directions, as the import-time gate asks them. A number with no
    occasion beside it reads as arbitrary and gets moved; an occasion with
    no number is a sentence about a block that no longer departs."""
    kept = dict(CEILINGS), dict(CEILING_BECAUSE)
    try:
        CEILINGS["a_second_loop"] = 10
        with pytest.raises(RuntimeError, match="say"):
            _check_every_ceiling_says_why()
        del CEILINGS["a_second_loop"]

        CEILING_BECAUSE["a_block_that_left"] = "because"
        with pytest.raises(RuntimeError, match="no longer"):
            _check_every_ceiling_says_why()
    finally:
        CEILINGS.clear()
        CEILINGS.update(kept[0])
        CEILING_BECAUSE.clear()
        CEILING_BECAUSE.update(kept[1])
    _check_every_ceiling_says_why()


# ===================================================== the reader's door


def _run(asked: int, **blocks) -> dict:
    """One result: what the run was told, and what its loops report."""
    estimate = {"method": "backdoor_adjustment", "point": 0.3,
                "ci_lower": 0.1, "ci_upper": 0.5}
    estimate.update(blocks)
    return {"estimation_context": {"ci_bootstrap": asked, "ci_level": 0.95},
            "numeric_estimate": estimate}


def _drew(n: int) -> dict:
    return {"kind": "iid", "requested": n, "used": n}


def _refused(result: dict) -> str:
    with pytest.raises(VerificationError) as exc:
        verify_bootstrap_records(result)
    return str(exc.value)


def test_an_interval_on_the_draws_the_run_asked_for_is_accepted():
    """The gate discriminates: every rejection below differs from this by
    one fact, and this one passes."""
    verify_bootstrap_records(_run(500, bootstrap=_drew(500)))


def test_a_loop_nobody_ordered_is_refused():
    """The shape this system shipped. Two hundred honest draws, described
    to a reader as the resampling they asked for."""
    message = _refused(_run(500, bootstrap=_drew(200)))
    assert "200" in message and "500" in message
    assert "nobody ordered" in message


def test_a_run_that_asked_for_no_interval_and_got_one_is_refused():
    """``ci_bootstrap=0`` is this system's documented way to skip the
    interval, so a block standing there is not a smaller disagreement than
    the others — it is an interval the caller declined."""
    assert "0" in _refused(_run(0, bootstrap=_drew(200)))


def test_more_draws_than_the_run_asked_for_is_refused_too():
    """Asked both ways round. A loop that overshot is as much a loop
    nobody ordered as one that fell short, and costs the caller the time
    they were trying not to spend."""
    assert "900" in _refused(_run(500, bootstrap=_drew(900)))


def test_the_block_with_a_ceiling_is_accepted_at_it_and_nowhere_else():
    """A second double-model bootstrap beside the estimate's own. It is
    the one block that draws fewer on purpose, and the purpose is quoted
    to whoever it refuses."""
    cap = CEILINGS["four_way_ratio"]
    verify_bootstrap_records(_run(
        500, bootstrap=_drew(500),
        four_way_ratio={"cde": {"point": 0.2, "ci_lower": 0.1,
                                "ci_upper": 0.3},
                        "bootstrap": _drew(cap)}))

    message = _refused(_run(
        500, bootstrap=_drew(500),
        four_way_ratio={"cde": {"point": 0.2, "ci_lower": 0.1,
                                "ci_upper": 0.3},
                        "bootstrap": _drew(cap + 1)}))
    assert CEILING_BECAUSE["four_way_ratio"] in message


def test_a_ceiling_does_not_excuse_the_block_it_is_not_about():
    """The over-correction this gate came closest to. The ratio block's
    ceiling is two hundred and the wire that was cut also produced two
    hundred, so a rule offering the ceiling to every record would have
    accepted the exact defect it exists to refuse."""
    cap = CEILINGS["four_way_ratio"]
    assert "nobody ordered" in _refused(_run(500, bootstrap=_drew(cap)))


def test_the_ceiling_is_a_ceiling_and_not_a_second_number():
    """A run asking for fewer draws than the ceiling gets fewer, in the
    capped block too — the cap bounds the ask rather than replacing it."""
    cap = CEILINGS["four_way_ratio"]
    verify_bootstrap_records(_run(
        20, bootstrap=_drew(20),
        four_way_ratio={"cde": {"point": 0.2, "ci_lower": 0.1,
                                "ci_upper": 0.3},
                        "bootstrap": _drew(20)}))
    assert "nobody ordered" in _refused(_run(
        20, bootstrap=_drew(20),
        four_way_ratio={"cde": {"point": 0.2, "ci_lower": 0.1,
                                "ci_upper": 0.3},
                        "bootstrap": _drew(cap)}))


def test_every_loop_on_the_envelope_is_asked_and_not_only_the_estimate_s():
    """Written as a walk rather than a list of sites, so a block added
    after this is asked by being written."""
    for where, block in (
        ("acr_decomposition", {"margins": [{"step": "1", "weight": 0.5}],
                               "bootstrap": _drew(9)}),
        ("counterfactual_cell_curve", {"bootstrap": _drew(9)}),
    ):
        assert where in _refused(_run(500, bootstrap=_drew(500),
                                      **{where: block}))

    bounds = {"estimation_context": {"ci_bootstrap": 500},
              "bounds_results": [{"method": "manski_natural",
                                  "lower": 0.0, "upper": 1.0,
                                  "bootstrap": _drew(9)}]}
    assert "nobody ordered" in _refused(bounds)


def test_a_fragment_that_is_not_a_run_is_still_accepted():
    """The other side of the counterexample. A block audited on its own
    carries no account of a run, and refusing it would make this rule a
    statement about how a caller assembled their test."""
    verify_bootstrap_records({"numeric_estimate": {
        "method": "backdoor_adjustment", "point": 0.3,
        "ci_lower": 0.1, "ci_upper": 0.5, "bootstrap": _drew(200)}})
    verify_bootstrap_records(_run(None, bootstrap=_drew(200)))
    verify_bootstrap_records({"estimation_context": {"ci_bootstrap": "500"},
                              "numeric_estimate": {"bootstrap": _drew(200)}})


# ===================================================== the producer's door


def test_the_producer_refuses_a_count_its_own_run_did_not_decide():
    """Held on both sides of the door: the reader's door catches a
    tampered envelope, and this catches the build that would have shipped
    one — naming the two things it can be."""
    with pytest.raises(RuntimeError) as exc:
        producer._check_every_resample_count_is_the_runs(
            _run(500, bootstrap=_drew(200)))
    assert "never arrived under the name" in str(exc.value)
    assert "_LOOPS_UNDER_ITS_OWN_CEILING" in str(exc.value)

    producer._check_every_resample_count_is_the_runs(
        _run(500, bootstrap=_drew(500)))


# ===================================================== end to end


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _mediation_program(*mediators: str) -> dict:
    statements = [{"kind": "variable", "predicate": p}
                  for p in ("x", *mediators, "y")]
    for m in mediators:
        statements += [
            {"kind": "cause", "from": _atom("x"), "to": _atom(m)},
            {"kind": "cause", "from": _atom(m), "to": _atom("y")},
        ]
    statements += [
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
            **({"mediator": _atom(mediators[0])} if len(mediators) == 1
               else {"mediators": [_atom(m) for m in mediators]}),
        }},
    ]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


def _frame(n: int = 900, clustered: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    fam = np.repeat(np.arange(n // 6), 6)
    shift = rng.normal(0, 1.0, n // 6)[fam] if clustered else np.zeros(n)
    x = rng.integers(0, 2, n).astype(float)
    m1 = 0.8 * x + 0.4 * shift + rng.normal(size=n)
    m2 = 0.5 * x + 0.3 * shift + rng.normal(size=n)
    y = 1.1 * m1 + 0.7 * m2 + 0.4 * x + 0.3 * shift + rng.normal(size=n)
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "y": y, "fam": fam})


def _the_estimate(out: dict) -> dict:
    for result in out.get("results") or ():
        estimate = result.get("numeric_estimate")
        if isinstance(estimate, dict) and estimate.get("bootstrap"):
            return result
    raise AssertionError("no result carried a bootstrap block")


def _endpoints(node, path=()):
    """Every pair of interval endpoints on one estimate, wherever it sits.

    Walked rather than read off the two places a mediation answer is known
    to keep them: this block reports endpoints at four depths, and an
    interval nobody computed is only as visible as the reading that goes
    looking for it.
    """
    if isinstance(node, dict):
        if "ci_lower" in node or "ci_upper" in node:
            yield (".".join(map(str, path)) or "the estimate",
                   node.get("ci_lower"), node.get("ci_upper"))
        for key, value in node.items():
            yield from _endpoints(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _endpoints(value, path + (index,))


@pytest.mark.parametrize("mediators", [("m1",), ("m1", "m2")])
@pytest.mark.parametrize("asked", [17, 31])
def test_a_mediation_interval_stands_on_the_draws_the_caller_asked_for(
    mediators, asked,
):
    """Through the public door, on both mediation shapes and at two
    counts, because the number that was shipped happened to equal one
    estimator's default and a single value cannot tell the two apart."""
    result = _the_estimate(themis.estimate(
        _mediation_program(*mediators), _frame(), ci_bootstrap=asked))
    assert result["numeric_estimate"]["bootstrap"]["requested"] == asked
    assert result["estimation_context"]["ci_bootstrap"] == asked
    themis.verify_bootstrap_draws(result)


@pytest.mark.parametrize("mediators", [("m1",), ("m1", "m2")])
def test_a_caller_who_declined_the_interval_is_not_given_one(mediators):
    """``0 skips CI`` is what this system documents, and it was the one
    ask the broken wire answered most loudly: a two-hundred-draw interval
    for a caller who wanted none.

    Asked of every endpoint on the envelope, not of the bootstrap block
    alone. With the block gone, the decomposition went on reporting
    ``ci_lower == ci_upper == point`` at eleven places — which is not the
    absence of an interval but an interval of zero width: a claim of
    exactness, shaped on the envelope like a real interval and read as
    one by everything downstream. The endpoints could not answer "none"
    because the estimate class and the schema both declared them numbers,
    so the estimator gave the only answer it could express. This test's
    own name had promised the wider claim and asked the narrower one.
    """
    out = themis.estimate(
        _mediation_program(*mediators), _frame(), ci_bootstrap=0)
    for result in out.get("results") or ():
        estimate = result.get("numeric_estimate") or {}
        assert estimate.get("bootstrap") is None
        for where, lower, upper in _endpoints(estimate):
            assert lower is None and upper is None, (where, lower, upper)
        themis.verify_bootstrap_draws(result)


@pytest.mark.parametrize("mediators", [("m1",), ("m1", "m2")])
def test_the_endpoints_are_there_when_the_caller_does_ask(mediators):
    """The denominator for the test above, which a walk reaching nothing
    would satisfy in silence — and the other side of the refusal: what is
    withheld from a caller who declined the interval is owed to one who
    asked."""
    out = themis.estimate(
        _mediation_program(*mediators), _frame(), ci_bootstrap=25)
    for result in out.get("results") or ():
        estimate = result.get("numeric_estimate") or {}
        found = list(_endpoints(estimate))
        assert len(found) >= 6, len(found)
        for where, lower, upper in found:
            assert lower is not None and upper is not None, where
            assert lower < upper, (where, lower, upper)


def test_a_clustered_joint_mediation_resamples_clusters():
    """The other knob the same call site dropped. Whole clusters, because
    an interval computed on rows that are not independent is narrower than
    the evidence supports and looks identical on the page."""
    result = _the_estimate(themis.estimate(
        _mediation_program("m1", "m2"), _frame(clustered=True),
        cluster="fam", ci_bootstrap=21))
    block = result["numeric_estimate"]["bootstrap"]
    assert block["kind"] == "cluster"
    assert block["cluster_column"] == "fam"
    assert block["requested"] == 21


# ===================================================== the whole corpus


def test_no_answer_this_repository_produces_stands_on_a_count_nobody_asked():
    """The census's question, asked of every shape at once. Six rows of the
    corpus failed this before the wire was drawn, and they were the only
    six — which is what makes the gate a measurement rather than a hope."""
    seen = 0
    for name, row in SHAPES.items():
        envelope = row.get("result") or row
        for result in (envelope.get("results") or [envelope]):
            if not isinstance(result, dict):
                continue
            seen += 1
            try:
                verify_bootstrap_records(result)
            except VerificationError as exc:  # pragma: no cover - the report
                raise AssertionError(f"{name}: {exc}") from exc
    assert seen >= 40


def test_the_corpus_is_where_a_bent_count_is_caught():
    """A gate nobody has seen refuse anything on the real corpus is a gate
    whose reach is unmeasured. Every row carrying a block is bent."""
    bent = 0
    for name, row in SHAPES.items():
        envelope = row.get("result") or row
        for result in (envelope.get("results") or [envelope]):
            if not isinstance(result, dict):
                continue
            estimate = result.get("numeric_estimate")
            if not isinstance(estimate, dict):
                continue
            block = estimate.get("bootstrap")
            if not isinstance(block, dict):
                continue
            forged = copy.deepcopy(result)
            forged["numeric_estimate"]["bootstrap"]["requested"] += 7
            forged["numeric_estimate"]["bootstrap"]["used"] += 7
            with pytest.raises(VerificationError):
                verify_bootstrap_records(forged)
            bent += 1
    assert bent >= 25
