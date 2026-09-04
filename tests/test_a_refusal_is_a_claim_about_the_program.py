"""A refusal says the program blocks something. Nobody asked the program.

When Themis cannot answer it hands back advice: this estimand is not
identified, go measure the confounder, go find an instrument, go run a
trial. Measured before this change: that report, unaltered, moved onto a
query the same system answers with a point estimate, and ``themis.audit``
returned verdicts identical to the honest one's — every row ok. ``verify``
refuses the whole class before reading a block, because a refusal carries
no derivation; every other public door is result-only, and a result-only
door cannot check a claim about a program it was never handed.

The door added here takes the program and tries to EXHIBIT what the
refusal says does not exist. It is a falsifier: accepting is not a
certificate, and the tests below are arranged so that the honest refusals
pass first, because a door that refused them would be worse than the hole
it closes — it would call an honest "I cannot answer this" a lie.

WHAT IS STILL TRUSTED. Ten of the eleven claims a gap can make about a
program have no witness search yet; they are named in ``UNWITNESSED`` and
pinned below, so one leaves that set only by being closed. Claims the data
settles are not this door's, and it says so rather than passing over them.
"""
from __future__ import annotations

import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest

import themis
from themis.gaps import GapKind
from themis.kernel import _refusal_facts as _facts
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import (
    _ESTIMAND_FIELDS_READ, SETTLED_BY, THE_PROGRAM, UNWITNESSED,
    _asks_what_the_search_can_answer, verify_refusal_claims,
)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "scale": "continuous"}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _bi(a, b):
    return {"kind": "bidirected", "left": _atom(a), "right": _atom(b)}


def _query(given=()):
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": 1.0},
        "target": {"atom": _atom("y"), "value": 1.0},
        "given": [{"atom": _atom(g), "value": 1.0} for g in given]}}


def _program(*statements, given=()):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [*statements, _query(given)]}


#: x -> y with unmeasured confounding and nothing else: no adjustment set
#: exists, no mediator intercepts the effect. The refusal is the truth.
BLOCKED = _program(_var("x"), _var("y"), _cause("x", "y"), _bi("x", "y"))

#: The same estimand with the confounder observed. Identified by adjustment.
OPEN = _program(_var("x"), _var("y"), _var("w"),
                _cause("w", "x"), _cause("w", "y"), _cause("x", "y"))

#: Unmeasured confounding again, but the effect runs entirely through m.
FRONTDOOR = _program(_var("x"), _var("m"), _var("y"),
                     _cause("x", "m"), _cause("m", "y"), _bi("x", "y"))


def _frame(n=2000, seed=5):
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(n)
    x = 0.7 * w + rng.standard_normal(n)
    y = 1.3 * x + 0.9 * w + rng.standard_normal(n)
    return pd.DataFrame({"w": w, "x": x, "y": y})


@pytest.fixture(scope="module")
def honest():
    return themis.run(BLOCKED)["results"][0]


@pytest.fixture(scope="module")
def answer():
    return themis.estimate(OPEN, _frame(), ci_bootstrap=0)["results"][0]


def _gap(kind, blocks):
    """A gap in the shape the schema requires — provenance is non-empty
    there, so a fabricated one has to cite something to get as far as the
    check this file is about."""
    return {"kind": kind.value, "severity": "blocking", "describes": [],
            "blocks": blocks,
            "provenance": [{"ref_kind": "investigation_request",
                            "ref_id": "query:effect_admg"}]}


def _forge(honest_refusal, query_id="q"):
    """The whole refusal, lifted intact. Nothing inside it is edited — the
    forgery is the pairing, which is exactly what no door was looking at."""
    forged = copy.deepcopy(honest_refusal)
    forged["query_id"] = query_id
    return forged


# ================================================================ honest first


def test_a_program_that_identifies_nothing_keeps_its_refusal(honest):
    """First, or every refusal below proves nothing. No adjustment set and
    no front-door route exist here, so the door finds no witness and says
    so by returning."""
    assert honest["status"] == "needs_investigation"
    assert honest.get("derivation") is None
    kinds = {g["kind"] for g in honest["data_gap_report"]["gaps"]}
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET.value in kinds
    themis.verify_refusal(BLOCKED, honest)


def test_an_answer_still_passes_the_door_it_always_had(answer):
    """The pass now runs inside ``verify`` too, so the answered path is
    the other half of the denominator."""
    assert answer["status"] == "numerically_solved"
    themis.verify(OPEN, answer)


def test_variables_that_do_not_help_are_not_a_witness():
    """The false alarm worth guarding: a graph with plenty of observed
    variables, none of which closes the backdoor. A search that returned
    the first set it could build would refuse this honest refusal."""
    prog = _program(_var("x"), _var("y"), _var("v"), _var("u"),
                    _cause("x", "y"), _cause("v", "u"), _bi("x", "y"))
    res = themis.run(prog)["results"][0]
    themis.verify_refusal(prog, res)


def test_a_descendant_of_the_treatment_is_not_a_witness():
    """A node that would close the path but sits downstream of the
    treatment is forbidden, not merely unhelpful — conditioning on it
    removes part of the effect being asked about."""
    prog = _program(_var("x"), _var("y"), _var("d"),
                    _cause("x", "y"), _cause("x", "d"), _cause("d", "y"),
                    _bi("x", "y"))
    res = themis.run(prog)["results"][0]
    themis.verify_refusal(prog, res)


def test_a_refusal_about_missing_data_is_left_alone():
    """The front-door program with no data attached refuses for want of
    distributions, which is a claim about the frame. The door has no
    frame, says nothing about it, and must not read the graph's route as
    an answer to a question about data."""
    res = themis.run(FRONTDOOR)["results"][0]
    kinds = {g["kind"] for g in res["data_gap_report"]["gaps"]}
    assert GapKind.MISSING_DISTRIBUTION.value in kinds
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET.value not in kinds
    themis.verify_refusal(FRONTDOOR, res)


#: The effect of x on y in a population the data do not come from, where
#: the outcome's own mechanism is what differs. In the source graph the
#: estimand needs no adjustment at all — the empty set is admissible, and
#: it is not a witness against "this does not transport".
TRANSPORT = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        {"kind": "variable", "predicate": p, "scale": "binary"}
        for p in ("x", "y")
    ] + [
        _cause("x", "y"),
        {"kind": "selection_node", "id": "S", "affects": _atom("y"),
         "source_population": "trial", "target_population": "real_world"},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [], "target_population": "real_world"}},
    ],
}


def test_an_effect_asked_of_another_population_is_a_different_estimand():
    """The class the whole suite had to be run to find. Twenty-eight honest
    transport refusals were called lies, because a transport query is an
    EffectQuery carrying a target population rather than a type of its
    own — so a guard on the query's TYPE let them through to a search that
    identifies the effect HERE. Here that search succeeds immediately, on
    the empty set, and what it found is not a witness against "this does
    not transport"."""
    res = themis.run(TRANSPORT)["results"][0]
    kinds = {g["kind"] for g in res["data_gap_report"]["gaps"]}
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET.value in kinds
    assert _facts(TRANSPORT, "q").selection_nodes
    themis.verify_refusal(TRANSPORT, res)


@pytest.mark.parametrize("field,value", [
    ("target_population", "elsewhere"),
    ("mediator", object()),
    ("extra_interventions", ("another treatment",)),
])
def test_anything_that_moves_the_estimand_puts_it_out_of_reach(field, value):
    """Stated as the fields the search READS, so a field added to the query
    beside these takes it out of reach on its own. The opposite list — the
    fields that disqualify — goes stale the day somebody adds one."""
    facts = _facts(OPEN, "q")
    moved = dataclasses.replace(facts.query, **{field: value})
    assert _asks_what_the_search_can_answer(
        dataclasses.replace(facts, query=moved)) is False
    assert _asks_what_the_search_can_answer(facts) is True


def test_the_fields_the_search_reads_are_declared():
    """Widening what the searches answer for should be a deliberate act,
    so the three fields they read are written down and every other field
    of the query is required to be at its default."""
    assert _ESTIMAND_FIELDS_READ == {"target", "intervention", "given"}


# ============================================================== the forgery


def test_a_refusal_lifted_onto_a_query_the_graph_answers_is_refused(honest):
    """The measured hole. Not one byte of the report is edited; the
    forgery is which program it is handed back for."""
    with pytest.raises(VerificationError, match="adjusting for"):
        themis.verify_refusal(OPEN, _forge(honest))


def test_the_witness_is_named(honest):
    """A refusal that cannot say what it found leaves the reader where it
    found them. The variable to adjust for is the answer to "so what
    should I have done", and it is in the message."""
    with pytest.raises(VerificationError, match=r"\{w\}"):
        themis.verify_refusal(OPEN, _forge(honest))


def test_a_front_door_route_is_a_witness_too(honest):
    """Adjustment is not the only way an estimand is identified, and a
    door that only searched for adjustment sets would wave through the
    classic case where no adjustment set exists at all."""
    with pytest.raises(VerificationError, match=r"front-door.*\{m\}"):
        themis.verify_refusal(FRONTDOOR, _forge(honest))


def test_latent_confounding_elsewhere_does_not_hide_the_witness(honest):
    """Any bidirected edge moves the search onto m-separation, so a graph
    with latent confounding somewhere harmless is its own case — the
    estimand is still closed by w and the refusal is still false."""
    prog = _program(_var("x"), _var("y"), _var("w"), _var("v"),
                    _cause("w", "x"), _cause("w", "y"), _cause("x", "y"),
                    _cause("v", "x"), _bi("v", "w"))
    with pytest.raises(VerificationError, match=r"adjusting for.*w"):
        themis.verify_refusal(prog, _forge(honest))


def test_the_witness_can_be_the_empty_set(honest):
    """M-bias: two latent common causes meeting at z, and the effect of x
    on y is identified by adjusting for NOTHING — while conditioning on
    the one variable available would open the path. A search that reported
    whatever set it could assemble would find the wrong thing here, and a
    search that only ever proposed a non-empty set would find nothing."""
    prog = _program(_var("x"), _var("y"), _var("z"),
                    _cause("x", "y"), _bi("x", "z"), _bi("z", "y"))
    with pytest.raises(VerificationError, match=r"adjusting for \{\}"):
        themis.verify_refusal(prog, _forge(honest))


def _conditioned(*, given):
    """One graph, two estimands: w closes the backdoor, s is downstream of
    the treatment and a collider on x -> s <- y."""
    return _program(_var("x"), _var("y"), _var("w"), _var("s"),
                    _cause("w", "x"), _cause("w", "y"), _cause("x", "y"),
                    _cause("x", "s"), _cause("y", "s"), given=given)


def test_a_witness_has_to_be_admissible_beside_what_was_asked(honest):
    """The estimand includes the subgroup the reader asked about, so the
    witness has to hold alongside it rather than instead of it. Here it
    does: w is pre-treatment and adjusting for it closes the only
    backdoor, so the refusal is refuted."""
    with pytest.raises(VerificationError, match="adjusting for"):
        themis.verify_refusal(_conditioned(given=()), _forge(honest))


def test_conditioning_the_reader_asked_for_can_be_what_blocks_it(honest):
    """The same graph, asked about the subgroup s — which is downstream of
    the treatment and a collider. No set is admissible beside that, so this
    refusal stands and the door says nothing. The pair is the point: the
    witness is a fact about the estimand, not about the graph alone."""
    themis.verify_refusal(_conditioned(given=("s",)), _forge(honest))


def test_the_full_door_runs_the_same_pass(answer):
    """#512's rule, applied to a claim both doors can reach: an answered
    result carrying a gap that says its own graph identifies nothing is
    refused by ``verify``, not only by the narrow door. The chain in this
    result identified the estimand; the gap says no set does.

    The tier moves with the gap. A gap saying no set identifies the
    estimand is also a gap saying the point this report still promises is
    out of reach, and the newer rule about that word speaks first — on a
    forgery that leaves it in place this test would pass on somebody
    else's refusal.
    """
    bad = copy.deepcopy(answer)
    bad["data_gap_report"]["gaps"].append(
        _gap(GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET, "identification"))
    bad["data_gap_report"]["answer_tier"] = "none"
    with pytest.raises(VerificationError, match="adjusting for"):
        themis.verify(OPEN, bad)


def test_the_audit_surface_tells_the_two_apart(honest):
    """What a caller reads. Before this change both columns were ok."""
    honest_rows = {r["audit"]: r["ok"] for r in themis.audit(BLOCKED, honest)}
    forged_rows = {r["audit"]: r["ok"]
                   for r in themis.audit(OPEN, _forge(honest))}
    assert honest_rows["verify_refusal"] is True
    assert forged_rows["verify_refusal"] is False
    assert forged_rows["verify_data_gap_report"] is True, (
        "the neighbour is not the check that catches this, and a test that "
        "let it look like one would hide which door does the work")


# ======================================================== the door's edges


def test_a_result_making_no_claim_is_a_caller_error(answer):
    """Not a verdict about the artifact: a caller asking this door about a
    result that says nothing about what it could not answer."""
    bare = copy.deepcopy(answer)
    bare.pop("data_gap_report", None)
    with pytest.raises(ValueError, match="requires result.data_gap_report"):
        themis.verify_refusal(OPEN, bare)


def test_a_query_the_program_does_not_have_is_a_caller_error(honest):
    with pytest.raises(ValueError, match="no query with id"):
        themis.verify_refusal(OPEN, _forge(honest, query_id="not_a_query"))


def test_a_gap_kind_outside_the_vocabulary_is_refused():
    """A kind nobody classified is a claim nobody decided about, and the
    door cannot know whether it was its business. Called on the rule
    directly: the schema's enum answers first at the public door, and a
    test that went through it would be a test of the schema."""
    with pytest.raises(VerificationError, match="not in the gap vocabulary"):
        verify_refusal_claims({"gaps": [{"kind": "unidentifiable_probably"}]},
                              _facts(BLOCKED, "q"))


def test_a_claim_the_data_settles_is_not_answered_from_the_graph(honest):
    """The other denominator. A door that refused everything it could not
    confirm would refuse the forgeries too and mean nothing by it — so a
    gap about a distribution passes here even when the graph is fine,
    because the graph was never what that gap was about."""
    bad = copy.deepcopy(honest)
    bad["query_id"] = "q"
    bad["data_gap_report"]["gaps"] = [
        _gap(GapKind.MISSING_DISTRIBUTION, "point_estimate")]
    themis.verify_refusal(OPEN, bad)


# ============================================================== the binding


def test_every_gap_kind_says_what_settles_it():
    """The vocabulary is closed, so coverage of it is a fact rather than a
    habit. The module refuses to import when it is not, and this states the
    property that refusal exists for."""
    assert set(SETTLED_BY) == set(GapKind)


def test_what_the_program_settles_and_has_no_witness_yet():
    """Named rather than described, so one leaves this list only by being
    closed. Each is a claim about the graph, the query or a declaration —
    checkable from what this door already holds, and not yet checked."""
    assert {k.value for k in UNWITNESSED} == {
        "ambiguous_variable_definition",
        "collider_conditioning_opens_backdoor",
        "dichotomized_continuous_measure",
        "feedback_loop_reaches_the_estimand",
        "graph_theta_independence_mismatch",
        "ill_defined_intervention_versions",
        "missing_iv_candidate",
        "selection_on_collider_opens_path",
        "unmeasured_confounder_risk",
        "unverified_proposal_edge_on_query_path",
    }
    assert all(SETTLED_BY[k] is THE_PROGRAM for k in UNWITNESSED)
