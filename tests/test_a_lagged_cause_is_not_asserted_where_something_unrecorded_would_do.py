"""The assumption PCMCI makes, and what it costs when it is wrong.

``lagged_discovery`` declares causal sufficiency in its scope — no unobserved
confounder of two recorded series — and a declaration is not a defence. The
first test here is the measurement that made this module necessary: a latent
AR(1) drives two recorded series that have NO link of any kind between them,
and the sufficiency-assuming search returns two lagged CAUSES at p = 0. A
reader is shown a graph and a note about scope; nothing in either says those
two arrows were manufactured by the one variable they were not given.

What replaces the assumption is not a better test. It is a third answer. An
edge comes back as ``tail`` (a cause), ``arrow`` (the two share something
unrecorded, and the driver is not a cause) or ``circle`` — one of those, and
this data does not settle which. The circle is the finding, not a gap in it.

Three properties are pinned here, and the third is the one the audit exists
for:

- the honest circle, where PCMCI writes an arrow;
- the identified ``arrow``, which PCMCI structurally cannot produce and which
  needs a collider to reach — a positive claim of confounding rather than a
  refusal to claim causation;
- the ``tail`` that still comes back where the data does settle it, because a
  method that answered ``circle`` to everything would also pass the first two
  and be worth nothing.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import language
from themis.estimation.discovery_words import Confounded
from themis.estimation.lagged_discovery import discover_lagged_graph
from themis.estimation.latent_lagged_discovery import (
    discover_latent_lagged_graph,
    latent_lagged_discovery_to_dict,
    latent_lagged_discovery_to_kernel_ast,
)


def _latent_driver(n: int = 4000) -> pd.DataFrame:
    """``x`` measures a latent at t, ``y`` is driven by it at t-1.

    Nothing runs from x to y or from y to x. Every association between them
    is L's, and L is not in the frame. ``z -> w`` at lag one is a real link,
    kept in so the run is not all confounding.
    """
    rng = np.random.default_rng(7)
    lat = np.zeros(n)
    for t in range(1, n):
        lat[t] = 0.8 * lat[t - 1] + rng.normal(0, 1)
    x = lat + rng.normal(0, 0.3, n)
    y, z, w = (np.zeros(n) for _ in range(3))
    for t in range(1, n):
        y[t] = 1.0 * lat[t - 1] + rng.normal(0, 0.3)
        z[t] = 0.6 * z[t - 1] + rng.normal(0, 1)
        w[t] = 0.7 * z[t - 1] + rng.normal(0, 0.5)
    return pd.DataFrame({"t": np.arange(n), "x": x, "y": y, "z": z, "w": w})


def _collider_to_the_latent(n: int = 6000) -> pd.DataFrame:
    """A design where the confounding is IDENTIFIABLE, not merely possible.

    ``u`` is unrecorded white noise and ``w`` an exogenous recorded series::

        x_t = 0.8 w_{t-1} + u_t + e        w@t-2 -> x@t-1
        y_t = u_{t-1} + e                  x@t-1 <-> y@t, through u@t-1

    ``w@t-2`` and ``y@t`` are independent outright — the only path between
    them runs through the collider ``x@t-1`` — so the triple is unshielded
    and ``x@t-1`` is NOT in the set that separated its ends. That is what
    turns "could be confounded" into "is confounded".
    """
    rng = np.random.default_rng(11)
    u, w = rng.normal(0, 1, n), rng.normal(0, 1, n)
    x, y = np.zeros(n), np.zeros(n)
    for t in range(1, n):
        x[t] = 0.8 * w[t - 1] + 1.0 * u[t] + rng.normal(0, 0.2)
        y[t] = 1.0 * u[t - 1] + rng.normal(0, 0.2)
    return pd.DataFrame({"t": np.arange(n), "w": w, "x": x, "y": y})


@pytest.fixture(scope="module")
def under_a_latent():
    return discover_latent_lagged_graph(
        _latent_driver(), time="t", max_lag=2, alpha=0.01)


@pytest.fixture(scope="module")
def through_a_collider():
    return discover_latent_lagged_graph(
        _collider_to_the_latent(), time="t", max_lag=2, alpha=0.01)


def _mark(result, driver, lag, target) -> str | None:
    for edge in result.edges:
        if (edge["driver"], edge["lag"], edge["target"]) == (driver, lag,
                                                             target):
            return edge["driver_end"]
    return None


# --- what the assumption costs ------------------------------------------------


def test_assuming_every_common_cause_was_recorded_manufactures_two_causes():
    """The measurement, run here rather than quoted from a docstring.

    This is not a criticism of the sibling module — it is what its own
    declared scope says will happen, made visible. A reader is handed a
    graph, and the scope note is the only thing standing between them and
    two arrows the data never contained.
    """
    found = {
        (link["driver"], link["lag"], link["target"]): link["p_value"]
        for link in discover_lagged_graph(
            _latent_driver(), time="t", max_lag=2, alpha=0.01).links
        if link["detected"]
    }
    assert ("x", 1, "y") in found and found[("x", 1, "y")] < 1e-12
    assert ("x", 2, "y") in found and found[("x", 2, "y")] < 1e-12
    # And it finds the real ones too, which is what makes the two above
    # indistinguishable to a reader.
    assert ("z", 1, "w") in found


def test_the_same_pair_comes_back_unsettled_rather_than_causal(under_a_latent):
    """The circle IS the answer here. There is no set to separate x@t-1 from
    y@t — their common cause was never recorded — so the edge stays, and what
    changes is that nothing claims it runs from one to the other."""
    assert _mark(under_a_latent, "x", 1, "y") == "circle"
    assert _mark(under_a_latent, "x", 2, "y") == "circle"


def test_a_link_the_data_does_settle_is_still_settled(under_a_latent):
    """A method that answered `circle` to everything would pass the test
    above and be worth nothing. z@t-1 -> w@t is real and comes back as a
    tail, by the non-collider rule on z@t-2, z@t-1, w@t: z@t-2 is separated
    from w@t by a set containing z@t-1, so z@t-1 cannot be a collider, and
    the end pointing out of it must be a tail."""
    assert _mark(under_a_latent, "z", 1, "w") == "tail"
    assert _mark(under_a_latent, "z", 1, "z") == "tail"
    witness = next(o for o in under_a_latent.orientations
                   if (o["driver"], o["lag"], o["target"]) == ("z", 1, "w"))
    assert witness["rule"] == "non_collider"
    assert witness["between"] == ["z@t-2", "w@t"]
    assert witness["through"] == "z@t-1"
    assert "z@t-1" in witness["separating_set"]


def test_the_subset_search_drops_an_edge_the_screen_kept(under_a_latent):
    """The screen is not the answer, and this is where the difference shows.

    Grow-shrink conditions on everything it has, so z@t-2 stays in x@t's
    screen; a subset of it separates them, and the edge goes. Under causal
    sufficiency there would have been no reason to look — one conditioning
    set does for every candidate, and it is the whole parent set.
    """
    screened = {(m["driver"], m["lag"])
                for entry in under_a_latent.screen
                if entry["target"] == "x"
                for m in entry["members"]}
    assert ("z", 2) in screened
    assert _mark(under_a_latent, "z", 2, "x") is None
    verdict = next(t for t in under_a_latent.pair_tests
                   if (t["target"], t["driver"], t["lag"]) == ("x", "z", 2))
    assert verdict["verdict"] == "separated"
    assert len(verdict["conditioning_set"]) < len(screened)


# --- the answer the assumption cannot even express ----------------------------


def test_confounding_is_identified_and_not_merely_left_open(
        through_a_collider):
    """`arrow` is a positive claim: x@t-1 is NOT a cause of y@t, and the two
    share something that was never recorded. It needs the collider rule, and
    the collider rule needs the empty set to be a candidate separating set —
    w@t-2 and y@t are independent outright, and become dependent only once
    x@t-1 is conditioned on."""
    assert _mark(through_a_collider, "x", 1, "y") == "arrow"
    witness = next(o for o in through_a_collider.orientations
                   if (o["driver"], o["lag"], o["target"]) == ("x", 1, "y"))
    assert witness["rule"] == "collider"
    assert witness["between"] == ["w@t-2", "y@t"]
    assert witness["separating_set"] == []


def test_the_sufficiency_assuming_search_calls_the_same_pair_a_cause():
    """Two of its three links are wrong on this design, and the second is
    the sharper failure: w@t-2 -> y@t is not confounding read as causation,
    it is an association that exists ONLY because the conditioning set
    contains a collider."""
    found = {
        (link["driver"], link["lag"], link["target"])
        for link in discover_lagged_graph(
            _collider_to_the_latent(), time="t", max_lag=2, alpha=0.01).links
        if link["detected"]
    }
    assert ("x", 1, "y") in found
    assert ("w", 2, "y") in found


def test_the_edge_the_collider_invented_is_not_here(through_a_collider):
    assert _mark(through_a_collider, "w", 2, "y") is None


# --- the audit, and the thing it has to say no to -----------------------------


def test_the_audit_accepts_what_the_producer_emits(under_a_latent,
                                                   through_a_collider):
    for result in (under_a_latent, through_a_collider):
        themis.verify_latent_lagged_discovery(
            latent_lagged_discovery_to_dict(result))


def test_the_audit_refuses_a_tail_no_triple_reaches(under_a_latent):
    """The counterexample this whole module is for. A fabricated tail is a
    causal claim made out of nothing — which is exactly what the assumption
    being dropped here used to produce — so the audit re-derives every mark
    from the recorded adjacency and separating sets rather than reading it.
    """
    tampered = copy.deepcopy(latent_lagged_discovery_to_dict(under_a_latent))
    edge = next(e for e in tampered["edges"] if e["driver_end"] == "circle")
    edge["driver_end"] = "tail"
    with pytest.raises(Exception) as caught:
        themis.verify_latent_lagged_discovery(tampered)
    assert "orientation rules" in str(caught.value)


def test_the_audit_refuses_a_separating_set_that_was_not_the_one_found(
        under_a_latent):
    """Which set separated a pair is not decoration: the rules ask whether a
    vertex is IN it, so a different set reaches different marks from the
    same data."""
    tampered = copy.deepcopy(latent_lagged_discovery_to_dict(under_a_latent))
    entry = next(t for t in tampered["pair_tests"]
                 if t["verdict"] == "separated" and t["conditioning_set"])
    entry["conditioning_set"] = []
    with pytest.raises(Exception):
        themis.verify_latent_lagged_discovery(tampered)


def test_the_audit_refuses_an_edge_the_verdicts_do_not_support(
        under_a_latent):
    tampered = copy.deepcopy(latent_lagged_discovery_to_dict(under_a_latent))
    tampered["edges"] = [e for e in tampered["edges"]
                         if not (e["driver"] == "z" and e["target"] == "w")]
    with pytest.raises(Exception) as caught:
        themis.verify_latent_lagged_discovery(tampered)
    assert "adjacent verdicts" in str(caught.value)


def test_the_audit_refuses_a_screen_that_is_not_a_fixpoint(under_a_latent):
    """Checked even though the producer never calls the screen the answer,
    because the conditioning pool every verdict was reached inside is a
    function of it: a screen that is not a fixpoint is a pool nobody chose.
    """
    tampered = copy.deepcopy(latent_lagged_discovery_to_dict(under_a_latent))
    entry = next(s for s in tampered["screen"] if s["members"])
    entry["members"] = entry["members"][:-1]
    with pytest.raises(Exception) as caught:
        themis.verify_latent_lagged_discovery(tampered)
    assert "fixpoint" in str(caught.value)


# --- what leaves for the kernel, and what does not ----------------------------


def test_an_unsettled_edge_becomes_a_question_and_never_a_cause(
        under_a_latent):
    """Emitting the cause would be the fabrication this module removes, and
    emitting nothing would drop a found adjacency on the floor. It goes out
    as an ambiguity with the question attached."""
    ast = latent_lagged_discovery_to_kernel_ast(under_a_latent)
    causes = {(s["from"]["predicate"], s["to"]["predicate"])
              for s in ast["statements"] if s["kind"] == "cause"}
    assert ("x", "y") not in causes
    assert ("z", "w") in causes
    asked = ast["extensions"]["ambiguities"]
    assert {tuple(a["endpoints"]) for a in asked} >= {("x@t-1", "y@t")}
    assert all(a["kind"] == "latent_or_causal" for a in asked)


def test_identified_confounding_leaves_as_a_bidirected_statement(
        through_a_collider):
    ast = latent_lagged_discovery_to_kernel_ast(through_a_collider)
    pairs = {(s["left"]["predicate"], s["right"]["predicate"])
             for s in ast["statements"] if s["kind"] == "bidirected"}
    assert pairs == {("x", "y")}
    assert not [s for s in ast["statements"] if s["kind"] == "cause"]


def test_a_time_index_travels_with_every_edge(through_a_collider):
    """The lag is the whole content of a lagged edge, and the kernel has a
    representation for it — a bidirected statement between two atoms with no
    time index would say the two are confounded at the same instant."""
    ast = latent_lagged_discovery_to_kernel_ast(through_a_collider)
    statement = next(s for s in ast["statements"] if s["kind"] == "bidirected")
    assert statement["left"]["time_index"] == {"kind": "relative", "value": -1}
    assert statement["right"]["time_index"] == {"kind": "relative", "value": 0}


# --- what the run says about itself -------------------------------------------


def test_the_note_says_what_a_circle_means_in_both_languages(under_a_latent):
    """The sentence a reader needs most is the one about the mark that says
    nothing, and it is a statement rather than text so it can be said in
    whichever language they are reading."""
    tokens = {one["token"] for one in under_a_latent.note}
    assert str(Confounded.A_CIRCLE_IS_THE_ANSWER) in tokens
    assert str(Confounded.SOUND_BUT_NOT_MAXIMALLY_INFORMATIVE) in tokens
    said = {
        lang: language.spoke(
            next(one for one in under_a_latent.note
                 if one["token"] == str(Confounded.A_CIRCLE_IS_THE_ANSWER)),
            lang)
        for lang in ("zh", "en")
    }
    assert said["zh"] != said["en"]
    assert all(text.strip() for text in said.values())


def test_the_counts_add_up_to_the_edges(under_a_latent):
    summary = next(one for one in under_a_latent.note
                   if one["token"] == str(Confounded.FOUND_THIS_MANY_EDGES))
    said = summary["said"]
    assert int(said["edges"]) == len(under_a_latent.edges)
    assert (int(said["causal"]) + int(said["confounded"])
            + int(said["unresolved"])) == len(under_a_latent.edges)


def test_no_triple_disagreed_on_either_of_these(under_a_latent,
                                                through_a_collider):
    """Empty in the population. Not empty is the sample saying a premise did
    not hold, and on two designs built to satisfy the premises it should be
    empty here — which is what makes it a signal rather than noise."""
    assert under_a_latent.conflicts == ()
    assert through_a_collider.conflicts == ()
