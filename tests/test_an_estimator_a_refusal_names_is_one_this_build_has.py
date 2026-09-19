"""An estimator a refusal names is one this build has.

The block that stands where a number would have been opens with two
fields: which species refused, and which estimator was running. The
species has been checked against a registry at three separate doors for
several frontiers. The estimator was checked nowhere, and the two are
assembled on the same line of the same function.

WHY THERE WAS NOTHING TO CHECK IT AGAINST, which is the part worth
keeping. The name was spelled at some seventy call sites and the contract
types it ``string`` where it gives the species a full enum, so holding it
looked like it would mean this package restating seventy literals -- the
table a verifier must not become. But fifteen of the twenty-nine spellings
are already declared elsewhere: seven are route ids, five are method
names, three are both. What the others needed was a home, not a copy.

AND ONE OF THEM WAS NOT A SPELLING AT ALL. The dose-response catch site
built its name out of the caller's model word --
``f"dose_response_{model}_dml"`` -- and the three backends call themselves
``dose_response_linear_dml``, ``dose_response_causal_forest_dml`` and
``dose_response_linear_drlearner``. Of the four words that site can be
handed, one produces the estimator's own name and three produce something
no estimator here answers to. Nor could a deeper name be honest there:
``_check_overlap`` runs before ``_resolve_model_choice``, so on that path
the refusal happens before a backend has been chosen. A format string
cannot be checked against anything, which is why the field had no roster
rather than merely no rule.

The stored corpus carried the proof: one answer named
``dose_response_drlearner_dml``, and no version of this source has ever
contained that string.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis import answers, refusals, routing
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

LEAF = "estimator_failure.estimator"

ROSTER = refusals.the_estimators_this_build_has()
METHODS = frozenset(answers.SHAPES_OF)
ROUTES = frozenset(route.id for route in routing.EFFECT_ROUTES)
FAMILIES = refusals.FAMILIES

CARRYING = sorted(
    name for name, shape in SHAPES.items()
    if isinstance(shape["result"].get("estimator_failure"), dict))


def _named(name: str) -> str:
    return SHAPES[name]["result"]["estimator_failure"].get("estimator")


# ------------------------------------------------- three sources, one roster

def test_the_roster_is_the_size_it_was_measured_at():
    assert (len(ROSTER), len(METHODS), len(ROUTES), len(FAMILIES)) == (
        88, 49, 26, 16)


def test_the_callers_own_words_for_an_estimator_are_nameable():
    """Two of the sixteen families are written twice, and this is the
    second writing's relationship to the first.

    ``dispatch`` declares the words a caller may name an ATE estimator
    by. Two of its four are method names as well and two are families,
    which is the same accident the dose-response site turned on: a word
    that happens to coincide with a name is not the same thing as a name.
    The read cannot go from ``refusals`` to ``dispatch`` -- that module
    imports this one -- so the two words are written again beside the
    families, and held to the original here rather than left to agree by
    habit.
    """
    from themis.estimation.dispatch import _ATE_ESTIMATORS

    assert _ATE_ESTIMATORS <= ROSTER
    assert _ATE_ESTIMATORS - METHODS == {"gformula", "ipw"}
    assert _ATE_ESTIMATORS - METHODS <= FAMILIES


def test_the_roster_is_those_three_and_nothing_else():
    assert ROSTER == METHODS | ROUTES | FAMILIES


def test_a_family_is_a_name_nothing_else_declares():
    """What the new list is FOR. A family is what a refusal can say when
    no route and no method had been chosen, and the two tables that
    declare those do not declare it -- which is the only reason a third
    source exists."""
    assert FAMILIES & (METHODS | ROUTES) == frozenset()


def test_a_method_and_a_route_may_be_the_same_name():
    """And three of them are. The sources overlap because a row of the
    cascade and the method it runs sometimes share a name; the roster is
    a union and says nothing about which source a name came from."""
    assert len(METHODS & ROUTES) == 3


def test_the_roster_is_read_rather_than_kept(monkeypatch):
    """The defect this closes was a second author for a name. A roster
    kept here would be a third."""
    monkeypatch.setitem(answers.SHAPES_OF, "a_method_added_today",
                        answers.SHAPES_OF["backdoor_linear"])
    assert "a_method_added_today" in refusals.the_estimators_this_build_has()


def test_the_three_dose_response_backends_are_nameable():
    """The names the estimator gives itself, all declared."""
    for method in ("dose_response_linear_dml",
                   "dose_response_causal_forest_dml",
                   "dose_response_linear_drlearner"):
        assert method in ROSTER


def test_the_spellings_the_catch_site_used_to_build_are_not_names():
    """Three of the four, which is the measurement the frontier turned
    on. ``dose_response_linear_dml`` is the fourth and is a real method,
    which is how the arrangement went unnoticed."""
    for built in ("dose_response_drlearner_dml", "dose_response_forest_dml",
                  "dose_response_dml"):
        assert built not in ROSTER
    assert "dose_response_linear_dml" in ROSTER


def test_the_row_that_refuses_before_a_backend_is_chosen_is_nameable():
    """What that site says now: the route it was running."""
    assert "dose_response_curve" in ROUTES


# ------------------------------------------------------------- the producer

def test_the_assembler_refuses_a_name_this_build_does_not_have():
    with pytest.raises(ValueError, match="unregistered estimator"):
        refusals.block(estimator="no_such_estimator",
                       failure_type=refusals.Refusal.UNKNOWN)


def test_the_assembler_says_where_to_declare_one():
    with pytest.raises(ValueError, match="SHAPES_OF"):
        refusals.block(estimator="no_such_estimator",
                       failure_type=refusals.Refusal.UNKNOWN)


def test_the_assembler_accepts_each_of_the_three_sources():
    for name in ("backdoor_linear", "dose_response_curve", "proximal"):
        built = refusals.block(estimator=name,
                               failure_type=refusals.Refusal.UNKNOWN)
        assert built["estimator"] == name


def test_the_species_is_still_asked_first():
    """Order, so that a caller with two things wrong is told about the
    one it was already told about."""
    with pytest.raises(ValueError, match="unregistered failure_type"):
        refusals.block(estimator="no_such_estimator",
                       failure_type="not_a_species")


def test_a_relayed_refusal_passes_the_same_door():
    """Three ways in and one assembly point, so one check covers them."""
    exc = refusals.EstimatorFailure(
        failure_type=refusals.Refusal.UNKNOWN)
    with pytest.raises(ValueError, match="unregistered estimator"):
        refusals.relayed(estimator="no_such_estimator", exc=exc)


def test_a_recorded_refusal_passes_the_same_door():
    exc = refusals.EstimatorFailure(
        failure_type=refusals.Refusal.UNKNOWN)
    with pytest.raises(ValueError, match="unregistered estimator"):
        refusals.record({}, estimator="no_such_estimator", exc=exc)


# --------------------------------------------------------- the stored corpus

def test_every_stored_refusal_names_something_this_build_has():
    assert len(CARRYING) == 37
    outside = sorted({_named(name) for name in CARRYING} - ROSTER)
    assert outside == []


def test_the_stored_names_come_from_all_three_sources():
    """Measured, because a roster exercised from one source would pass
    while the other two were never asked."""
    counted = {"method": 0, "route": 0, "family": 0}
    for name in CARRYING:
        value = _named(name)
        if value in METHODS:
            counted["method"] += 1
        elif value in ROUTES:
            counted["route"] += 1
        else:
            counted["family"] += 1
    assert counted == {"method": 13, "route": 4, "family": 20}


@pytest.mark.parametrize("name", CARRYING)
def test_a_stored_answer_that_names_an_estimator_is_accepted(name):
    verify_honestly(SHAPES[name]["program"],
                    copy.deepcopy(SHAPES[name]["result"]))


@pytest.mark.parametrize("name", CARRYING)
def test_a_name_this_build_does_not_have_is_refused_at_the_door(name):
    program = SHAPES[name]["program"]
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["estimator_failure"]["estimator"] = "an_estimator_nobody_has"
    with pytest.raises(Exception):
        the_door_for(bad)(program, bad)


@pytest.mark.parametrize("name", CARRYING[:8])
def test_an_estimator_with_a_suffix_is_a_different_estimator(name):
    program = SHAPES[name]["program"]
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["estimator_failure"]["estimator"] = _named(name) + "_forged"
    with pytest.raises(VerificationError, match="no estimator by that name"):
        the_door_for(bad)(program, bad)


def test_an_empty_name_is_not_a_name():
    name = CARRYING[0]
    program = SHAPES[name]["program"]
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["estimator_failure"]["estimator"] = ""
    with pytest.raises(Exception):
        the_door_for(bad)(program, bad)


# -------------------------------------------------------- what is not claimed

def test_whether_the_field_is_there_at_all_is_not_asked_here():
    """A claim about the record's SHAPE, which the schema makes."""
    from themis.verifier.estimator_failure_rules import verify_refusal_block
    verify_refusal_block({"estimator_failure": {"failure_type": "unknown",
                                                "kind": "backend"}})
