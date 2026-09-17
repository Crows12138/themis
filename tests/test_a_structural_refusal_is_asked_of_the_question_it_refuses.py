"""A structural refusal says a question cannot be run, and the question is what it is asked of.

``missing_structural_input`` is the program's to settle, and it is witnessed
species by species. Two species carry the whole of their claim in their own
facts -- a name, the part that writes it, the nodes it is -- and had a
witness. The other seven say something about the question and the graph: a
condition holds the question's own treatment or outcome, a mediator is off the
paths from the treatment to the outcome, the abduction needs a coefficient
nobody declared,
a condition has probability zero in every model, a joint question also asks
for mediation or transport, a joint treatment repeats. At most they carry a
detail of that. They had no witness, so the copies of one were held to each
other and to nothing else.

Measured before the witnesses, on answers made beyond the corpus as well as
on it: bent together at every copy, 25 forgeries were accepted -- the
conditioned atoms a refusal names rewritten, the edge whose coefficient is missing
turned round, the declaration a joint question must drop renamed, and each
honest answer put beside a program where its claim is false. Bent at one copy
and asked at the door that reads only what the program settles, 100 more. Put
beside such a program at that door, 22, among them the two mediator species,
which only the mediation block's own rule had been holding and only at the
door that reads the block.

Every witness errs toward accepting. A detail is asked as a set, so a
reordering is the same claim; a joint question declaring two other layers
may be told to drop either; a condition is refuted only by a model in which
it happens.
"""
from __future__ import annotations

import copy

import pytest

import themis
from tests.answer_corpus import verify_honestly
from tests.test_ctf_conjunction_wiring import _ast_cond, _cause, _ev, _var
from themis import routing
from themis.verifier import semantic_probe
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import _ASKED_BESIDE_A_JOINT_EFFECT


def _a(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _binary(*names):
    return [{"kind": "variable", "predicate": n, "domain": [True, False]}
            for n in names]


def _program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _cause_me(x, y, **extra):
    return {"kind": "cause", "from": _a(x), "to": _a(y), **extra}


def _query(**query):
    return {"kind": "query", "id": "q", "query": query}


def _effect(**extra):
    return _query(kind="effect", intervention={"atom": _a("x"), "value": True},
                  target={"atom": _a("y"), "value": True}, given=[], **extra)


def _identify(*given):
    return _query(kind="identify", target=_a("y"),
                  intervention={"atom": _a("x"), "value": True},
                  given=[_a(g) for g in given])


def _joint(first, *others):
    return _query(kind="effect", intervention={"atom": _a(first), "value": True},
                  extra_interventions=[{"atom": _a(o), "value": False}
                                       for o in others],
                  target={"atom": _a("y"), "value": True}, given=[])


_BACKDOOR = _binary("x", "y", "d", "z") + [
    _cause_me("x", "y"), _cause_me("x", "d"), _cause_me("z", "y")]
_MEDIATOR = _binary("x", "m", "y", "extra")
_BLOCK = _binary("x", "m1", "m2", "y") + [
    _cause_me("x", "m1"), _cause_me("m1", "y"), _cause_me("x", "y")]
_SCM = [{"kind": "variable", "predicate": n} for n in ("x", "m", "y", "w")] + [
    {"kind": "observation", "atom": _a(n), "value": v}
    for n, v in (("x", 1.0), ("m", 0.5), ("y", 2.0), ("w", 1.0))]
_SCM_QUERY = _query(kind="scm_counterfactual",
                    intervention={"atom": _a("x"), "value": 0.0}, target=_a("y"))
_XY = [_var("x"), _var("y"), _cause("x", "y")]
_JOINT = _binary("x", "b", "m", "y") + [
    _cause_me("x", "m"), _cause_me("m", "y"), _cause_me("b", "y")]
_B = [{"atom": _a("b"), "value": True}]
_REPEATS = _binary("a", "b", "y") + [_cause_me("a", "y"), _cause_me("b", "y")]


def _scm(*coefficients):
    edges = (("x", "m"), ("m", "y"), ("w", "x"))
    return _program(_SCM + [
        _cause_me(p, c, **({"coefficient": k} if k is not None else {}))
        for (p, c), k in zip(edges, coefficients)] + [_SCM_QUERY])


def _conditioned(*condition):
    return _ast_cond(_XY, events=[_ev("y", [("x", True)], True)],
                     condition=list(condition))


_ENDS = "given_holds_the_treatment_or_outcome"

#: Honest answers, and the species each is.
HONEST = {
    "the treatment conditioned on": (
        _program(_BACKDOOR + [_identify("z", "x")]), _ENDS),
    "the outcome conditioned on, beside a descendant": (
        _program(_BACKDOOR + [_identify("d", "y")]), _ENDS),
    "the treatment and the outcome conditioned on": (
        _program(_BACKDOOR + [_identify("y", "x")]), _ENDS),
    "the outcome conditioned on, asked as an effect": (
        _program(_BACKDOOR + [_query(
            kind="effect", intervention={"atom": _a("x"), "value": True},
            target={"atom": _a("y"), "value": True},
            given=[{"atom": _a("y"), "value": True}])]), _ENDS),
    "a mediator the treatment never reaches": (
        _program(_MEDIATOR + [_cause_me("x", "y"), _cause_me("m", "extra"),
                              _effect(mediator=_a("m"))]),
        "mediator_off_the_directed_paths"),
    "a mediator downstream of the outcome": (
        _program(_MEDIATOR + [_cause_me("x", "y"), _cause_me("y", "m"),
                              _effect(mediator=_a("m"))]),
        "mediator_off_the_directed_paths"),
    "a block with a member off the paths": (
        _program(_BLOCK + [_cause_me("m2", "y"),
                           _effect(mediators=[_a("m1"), _a("m2")])]),
        "mediator_set_off_the_directed_paths"),
    "a block holding the outcome": (
        _program(_BLOCK + [_effect(mediators=[_a("m1"), _a("y")])]),
        "mediator_set_off_the_directed_paths"),
    "a coefficient missing on the path": (
        _scm(0.7, None, 1.0), "path_coefficient_undeclared"),
    "a condition forced one way and seen the other": (
        _conditioned(_ev("x", [("x", False)], True)),
        "conditioning_event_has_probability_zero"),
    "a condition that contradicts itself": (
        _conditioned(_ev("y", [], True), _ev("y", [], False)),
        "conditioning_event_has_probability_zero"),
    "a joint question with a mediator": (
        _program(_JOINT + [_effect(extra_interventions=_B, mediator=_a("m"))]),
        "joint_with_mediation_or_transport"),
    "a joint question with a mediator block": (
        _program(_JOINT + [_effect(extra_interventions=_B,
                                   mediators=[_a("m")])]),
        "joint_with_mediation_or_transport"),
    "a joint question naming a treatment twice": (
        _program(_REPEATS + [_joint("a", "b", "b")]),
        "duplicate_treatment_atom"),
}

#: The honest answer beside a program where what it says is false.
ELSEWHERE = {
    "nothing conditioned on is an end of the question": (
        "the treatment conditioned on",
        _program(_BACKDOOR + [_identify("z")])),
    "a descendant of the treatment conditioned on is the identifier's": (
        "the treatment conditioned on",
        _program(_BACKDOOR + [_identify("z", "d")])),
    "asked as an effect, nothing conditioned on is an end": (
        "the outcome conditioned on, asked as an effect",
        _program(_BACKDOOR + [_effect()])),
    "the mediator is on a path": (
        "a mediator the treatment never reaches",
        _program(_MEDIATOR + [_cause_me("x", "m"), _cause_me("m", "y"),
                              _effect(mediator=_a("m"))])),
    "every member of the block is on a path": (
        "a block with a member off the paths",
        _program(_BLOCK + [_cause_me("m2", "y"), _cause_me("x", "m2"),
                           _effect(mediators=[_a("m1"), _a("m2")])])),
    "the coefficient is declared": (
        "a coefficient missing on the path", _scm(0.7, 0.2, 1.0)),
    "the condition is consistent": (
        "a condition forced one way and seen the other",
        _conditioned(_ev("x", [("x", False)], False))),
    "the condition is an observation": (
        "a condition forced one way and seen the other",
        _conditioned(_ev("x", [], True))),
    "the two events are in different worlds": (
        "a condition that contradicts itself",
        _conditioned(_ev("y", [], True), _ev("y", [("x", True)], False))),
    "the question is not joint": (
        "a joint question with a mediator",
        _program(_JOINT + [_effect(mediator=_a("m"))])),
    "the joint question asks nothing else": (
        "a joint question with a mediator",
        _program(_JOINT + [_effect(extra_interventions=_B)])),
    "the treatments are distinct": (
        "a joint question naming a treatment twice",
        _program(_REPEATS + [_joint("a", "b")])),
}

#: A detail bent, and whether what it then says is still true.
BENT = {
    "the outcome said for the treatment": (
        "the treatment conditioned on", {"atoms": "y(me)"}, False),
    "a conditioned atom that is no end": (
        "the treatment conditioned on", {"atoms": "z(me)"}, False),
    "a descendant said beside the outcome": (
        "the outcome conditioned on, beside a descendant",
        {"atoms": "y(me), d(me)"}, False),
    "the two ends, the other way round": (
        "the treatment and the outcome conditioned on",
        {"atoms": "y(me), x(me)"}, True),
    "the edge into the treatment": (
        "a coefficient missing on the path",
        {"parent": "w(me)", "child": "x(me)"}, False),
    "the edge turned round": (
        "a coefficient missing on the path",
        {"parent": "y(me)", "child": "m(me)"}, False),
    "a layer the question does not declare": (
        "a joint question with a mediator", {"drop": "`mediators`"}, False),
    "the joint intervention itself": (
        "a joint question with a mediator",
        {"drop": "`extra_interventions`"}, False),
}


def _run(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


@pytest.fixture(scope="module")
def answers():
    return {name: _run(program) for name, (program, _) in HONEST.items()}


def _copies(node, species):
    if isinstance(node, dict):
        if node.get("need") == species or (
                node.get("token") == species
                and node.get("vocabulary") == "gap_says"):
            yield node
        for value in node.values():
            yield from _copies(value, species)
    elif isinstance(node, list):
        for item in node:
            yield from _copies(item, species)


def _detailed(result, species):
    """The copies that carry the detail: a statement's facts, or an ask's."""
    return [holder for holder in _copies(result, species)
            if isinstance(holder.get("said"), dict)]


def _bend(result, species, facts, only=None):
    forged = copy.deepcopy(result)
    for index, holder in enumerate(_detailed(forged, species)):
        if only is None or index == only:
            holder["said"].update(facts)
    return forged


@pytest.mark.parametrize("name", sorted(HONEST))
def test_an_honest_structural_refusal_is_accepted(name, answers):
    program, species = HONEST[name]
    result = answers[name]
    assert len(list(_copies(result, species))) >= 4
    verify_honestly(program, result)
    themis.verify_refusal(program, result)


@pytest.mark.parametrize("name", sorted(ELSEWHERE))
def test_beside_a_program_where_it_is_false_it_is_refused(name, answers):
    """At the door that reads only what the program settles, where no other
    rule stands in front of the species', and at the door that reads all of
    it."""
    honest, program = ELSEWHERE[name]
    species = HONEST[honest][1]
    with pytest.raises(VerificationError, match=f"says '{species}'"):
        themis.verify_refusal(program, answers[honest])
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(program, answers[honest])


@pytest.mark.parametrize("name", sorted(BENT))
def test_a_detail_is_held_at_every_copy_and_at_each_one(name, answers):
    honest, facts, true = BENT[name]
    program, species = HONEST[honest]
    result = answers[honest]
    if true:
        verify_honestly(program, _bend(result, species, facts))
        return
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(program, _bend(result, species, facts))
    detailed = len(_detailed(result, species))
    assert detailed >= 4
    for index in range(detailed):
        with pytest.raises(VerificationError, match=f"says '{species}'"):
            themis.verify_refusal(
                program, _bend(result, species, facts, only=index))


def test_a_question_declaring_two_other_layers_may_be_told_to_drop_either():
    program = _program(_JOINT + [_effect(extra_interventions=_B,
                                         mediators=[_a("m")],
                                         mediator=_a("m"))])
    result = _run(program)
    species = "joint_with_mediation_or_transport"
    for other in ("`mediator`", "`mediators`"):
        themis.verify_refusal(program, _bend(result, species, {"drop": other}))


def test_a_condition_too_big_to_enumerate_is_sampled(answers, monkeypatch):
    """The same verdicts when every model is past the enumeration cap."""
    monkeypatch.setattr(semantic_probe, "_EXACT_BACKGROUND_CAP", 0)
    honest = "a condition forced one way and seen the other"
    program, _species = HONEST[honest]
    themis.verify_refusal(program, answers[honest])
    with pytest.raises(VerificationError, match="probability"):
        themis.verify_refusal(ELSEWHERE["the condition is consistent"][1],
                              answers[honest])


def test_the_layers_a_joint_question_cannot_also_ask_are_the_routing_table_s():
    """Restated in the verifier, which reads no producer table, and held
    here to the declarations that trigger the rows the joint route
    displaces."""
    joint = routing.route("joint_intervention")
    assert set(_ASKED_BESIDE_A_JOINT_EFFECT) == {
        routing.route(row).triggered_by for row in joint.displaces}
