"""A time-varying strategy is asked as a plain effect, and was refused as one.

A program declares a strategy in ``options.longitudinal`` -- its treatments
in time order, the covariates measured before each, the outcome -- and asks
it as the effect of one of those treatments on that outcome, because the
query grammar cannot carry the order. Where the declared history leaves a
back door open at some treatment, the answer says so with a gap of the kind
"no admissible set".

The refusal door read that gap as a claim about the plain effect of the one
treatment the query names. It searched the whole graph for an adjustment
set, found one made of variables the declaration says nobody measured, and
refused the honest answer as a lie. Measured: a history that leaves out the
covariate measured between the two treatments, and a confounder of the
first treatment that the history never names, were both refused.

The estimand the query stands in for is the strategy over the declared
history, and so is the witness: the history itself, holding at every
treatment.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.kernel import _refusal_facts as _facts
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import (
    _asks_what_the_search_can_answer, verify_refusal_claims,
)

_SUBJECT = [{"type": "const", "name": "subj"}]


def _atom(predicate, time=None):
    atom = {"predicate": predicate, "args": _SUBJECT}
    if time is not None:
        atom["time_index"] = {"kind": "relative", "value": time}
    return atom


def _untimed(pairs):
    return [(_atom(a), _atom(b)) for a, b in pairs]


def _program(edges, declared, *, ask=(_atom("A1"), _atom("Y")), bidirected=()):
    predicates = sorted({atom["predicate"]
                         for pair in [*edges, *bidirected] for atom in pair})
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in predicates]
    statements += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    statements += [{"kind": "bidirected", "left": a, "right": b}
                   for a, b in bidirected]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": ask[0], "value": True},
        "target": {"atom": ask[1], "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "subj"}]},
            "options": {"longitudinal": dict(
                declared, strategy_treated=1, strategy_control=0)},
            "statements": statements}


#: Two treatments, a covariate measured before each, the outcome after both.
_TWO_STEPS = [("L0", "A0"), ("L0", "Y"), ("A0", "L1"), ("A0", "Y"),
              ("L1", "A1"), ("L1", "Y"), ("A1", "Y")]
_DECLARED = {"treatments": ["A0", "A1"],
             "confounders_by_time": [["L0"], ["L1"]], "outcome": "Y"}

#: The declared history blocks every back door, at both treatments.
IDENTIFIED = _program(_untimed(_TWO_STEPS), _DECLARED)

#: Each leaves a back door open at some treatment given the declared
#: history, while the plain effect of A1 on Y has an adjustment set in the
#: graph -- except the last, where nothing does, which is the case the door
#: already took.
HONEST = {
    "the_history_leaves_out_the_covariate_between_the_treatments": _program(
        _untimed(_TWO_STEPS), dict(_DECLARED, confounders_by_time=[["L0"], []])),
    "a_confounder_of_the_first_treatment_is_outside_the_history": _program(
        _untimed(_TWO_STEPS + [("C", "A0"), ("C", "Y")]), _DECLARED),
    "the_last_treatment_shares_a_latent_cause_with_the_outcome": _program(
        _untimed(_TWO_STEPS), _DECLARED, bidirected=[(_atom("A1"), _atom("Y"))]),
}

#: The same strategy unrolled in time: one column per variable, a node per
#: step. The declaration names ``A`` and ``L`` and the graph holds two of
#: each.
UNROLLED = _program(
    [(_atom("L", -1), _atom("A", -1)), (_atom("L", -1), _atom("Y", 0)),
     (_atom("A", -1), _atom("L", 0)), (_atom("A", -1), _atom("Y", 0)),
     (_atom("L", 0), _atom("A", 0)), (_atom("L", 0), _atom("Y", 0)),
     (_atom("A", 0), _atom("Y", 0))],
    {"treatments": ["A"], "confounders_by_time": [["L"]], "outcome": "Y"},
    ask=(_atom("A", 0), _atom("Y", 0)))


def _run(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _gap():
    return {"kind": "unidentifiable_no_admissible_set", "severity": "blocking",
            "describes": [], "blocks": "identification",
            "provenance": [{"ref_kind": "investigation_request",
                            "ref_id": "query:effect_admg"}]}


# ================================================================ honest first


@pytest.mark.parametrize("name", sorted(HONEST))
def test_an_honest_refusal_of_a_strategy_passes_both_doors(name):
    program = HONEST[name]
    result = _run(program)
    assert result["status"] == "needs_investigation"
    assert result["extensions"]["longitudinal_identification"]["identified"] is False
    kinds = {g["kind"] for g in result["data_gap_report"]["gaps"]}
    assert "unidentifiable_no_admissible_set" in kinds
    themis.verify_refusal(program, result)
    themis.verify_answer_claims(program, result)


def test_a_strategy_its_history_identifies_is_still_answered():
    result = _run(IDENTIFIED)
    assert result["status"] == "structurally_solved"
    themis.verify(IDENTIFIED, result)


# ============================================================== the forgery


def test_a_refusal_lifted_onto_a_strategy_its_history_identifies_is_refused():
    honest = _run(HONEST[
        "the_history_leaves_out_the_covariate_between_the_treatments"])
    with pytest.raises(VerificationError,
                       match="history the program declares measured"):
        themis.verify_refusal(IDENTIFIED, copy.deepcopy(honest))


def test_the_witness_names_the_treatments_in_their_order():
    honest = _run(HONEST[
        "the_history_leaves_out_the_covariate_between_the_treatments"])
    with pytest.raises(VerificationError, match=r"to Y from each of A0, A1"):
        themis.verify_refusal(IDENTIFIED, copy.deepcopy(honest))


def test_the_full_door_is_handed_the_declaration_too():
    """An answered strategy carrying a gap that says nothing identifies it.
    The tier moves with the gap, as in the plain case, so the rule about
    the tier does not speak first."""
    bad = copy.deepcopy(_run(IDENTIFIED))
    bad["data_gap_report"]["gaps"].append(_gap())
    bad["data_gap_report"]["answer_tier"] = "none"
    with pytest.raises(VerificationError,
                       match="history the program declares measured"):
        themis.verify(IDENTIFIED, bad)


# ======================================================== what it stands for


def test_the_query_stands_in_for_the_strategy_only_when_it_asks_about_its_ends():
    """Asked about a declared treatment and the declared outcome, the query
    is the strategy's; asked about anything else, it is the plain effect it
    says it is, and the plain search answers it."""
    assert _facts(IDENTIFIED, "q").longitudinal == IDENTIFIED["options"]["longitudinal"]
    assert _asks_what_the_search_can_answer(_facts(IDENTIFIED, "q")) is False
    elsewhere = _program(_untimed(_TWO_STEPS), _DECLARED,
                         ask=(_atom("L1"), _atom("Y")))
    assert _asks_what_the_search_can_answer(_facts(elsewhere, "q")) is True


def test_a_name_the_graph_holds_at_several_times_is_not_a_witness():
    """Which step the declaration meant is written nowhere, so neither the
    history nor a set drawn from the graph is a witness, and the gap
    stands. The plain search found one here: the adjustment set for the
    current treatment, which is not the estimand."""
    facts = _facts(UNROLLED, "q")
    assert _asks_what_the_search_can_answer(facts) is False
    verify_refusal_claims({"gaps": [_gap()]}, facts)
