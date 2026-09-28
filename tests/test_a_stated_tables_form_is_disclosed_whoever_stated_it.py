"""A stated table's form is disclosed whoever stated it.

A probability model states a table as a baseline and an odds ratio per
condition, and from two conditions on its form assumes the conditions do
not interact — a claim no cell of the table makes. The schema says the form
"is disclosed as one". It was, for a model a language model supplied: the
ledger read its line off the LLM review. A model the caller wrote — the
kernel takes one from anybody — composed its cells under the same
assumption and the ledger said nothing.

The form's assumption is the model's, not its author's. So every model the
program states is listed in ``extensions.probability_models`` with whether
a language model supplied it, the ledger writes the form's line from that
list, and who stated the model decides only whose line it is: one more of
the language model's priors, or the caller's choice of how to state the
table — withdrawn, the cells are unstated and there is no answer. The list
is held to the program, and the line to the list.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _model(conditions=("x", "z"), *, llm_prior=False):
    why = {"annotations": {"source": "a reason"}} if llm_prior else {}
    model = {
        "kind": "probability_model", "form": "odds_ratios",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom(c), "value": False} for c in conditions],
        "baseline": {"value": 0.2, **why},
        "odds_ratios": [{"atom": _atom(c), "value": True, "odds_ratio": 2.0, **why}
                        for c in conditions],
    }
    if llm_prior:
        model["llm_prior"] = True
    return model


def _program(model):
    """x → y confounded by z, P(z) stated, and y's table as ``model``."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in "xyz"),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "probability", "target": {"atom": _atom("z"), "value": True},
             "given": [], "value": 0.3},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True}, "given": []}},
            model,
        ],
    }


def _answer(model):
    program = _program(model)
    return program, themis.run(program)["results"][0]


def _form_lines(result):
    return [(claim.get("token"), entry.get("provenance"))
            for entry in result["extensions"]["assumption_ledger"]["assumptions"]
            for claim in entry.get("claim") or ()
            if claim.get("vocabulary") == "stated_form_claim"]


@pytest.mark.parametrize("llm_prior, owner", [
    (False, "caller_chose"), (True, "llm_prior"),
], ids=["the caller's table", "the language model's"])
def test_a_table_of_two_conditions_owes_the_form_s_line(llm_prior, owner):
    program, result = _answer(_model(llm_prior=llm_prior))
    assert result["status"] == "numerically_solved"
    assert result["extensions"]["probability_models"] == {"models": [{
        "distribution": "P(y | x, z)", "form": "odds_ratios",
        "conditions": ["x", "z"], "llm_prior": llm_prior}]}
    assert _form_lines(result) == [("no_interaction", owner)]
    themis.verify(program, result)


def test_the_review_lists_a_supplied_table_s_numbers_and_not_the_table():
    """What the language model supplied is its numbers, each a line of the
    review; which table they compose is said of every table alike."""
    _, result = _answer(_model(llm_prior=True))
    review = result["extensions"]["llm_proposed_review"]
    assert set(review) == {"edges", "probabilities"}
    assert len(review["probabilities"]) == 3


def test_a_table_of_one_condition_is_listed_and_owes_no_line():
    """With one condition the baseline and its ratio are the table itself:
    x's table over its one parent z, and y's cells stated one by one."""
    x_given_z = {**_model(("z",)), "target": {"atom": _atom("x"), "value": True}}
    program = _program(x_given_z)
    program["statements"] += [
        {"kind": "probability", "target": {"atom": _atom("y"), "value": True},
         "given": [{"atom": _atom("x"), "value": x}, {"atom": _atom("z"), "value": z}],
         "value": 0.2 + 0.3 * x + 0.2 * z}
        for x in (True, False) for z in (True, False)]
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["extensions"]["probability_models"] == {"models": [{
        "distribution": "P(x | z)", "form": "odds_ratios", "conditions": ["z"],
        "llm_prior": False}]}
    assert "assumption_ledger" not in result["extensions"] or not _form_lines(result)
    themis.verify(program, result)


def test_a_program_with_no_table_has_no_list():
    program, result = _answer({"kind": "probability", "given": [],
                               "target": {"atom": _atom("y"), "value": True},
                               "value": 0.5})
    assert "probability_models" not in (result.get("extensions") or {})


def _forged(result, forge):
    forged = copy.deepcopy(result)
    forge(forged["extensions"])
    return forged


def _hand_the_line_to_the_model(ext):
    for entry in ext["assumption_ledger"]["assumptions"]:
        if entry.get("provenance") == "caller_chose":
            entry["provenance"] = "llm_prior"


def _drop_the_line(ext):
    kept = [e for e in ext["assumption_ledger"]["assumptions"]
            if e.get("provenance") != "caller_chose"]
    if kept:
        ext["assumption_ledger"]["assumptions"] = kept
    else:
        del ext["assumption_ledger"]


# The list forged with the ledger agreeing with it, so that the list's own
# copy of the program is the one thing left to disagree.
def _mark_it_the_model_s(ext):
    ext["probability_models"]["models"][0]["llm_prior"] = True
    _hand_the_line_to_the_model(ext)


def _drop_it(ext):
    del ext["probability_models"]
    _drop_the_line(ext)


@pytest.mark.parametrize("token", ["x", "a_commonsense_prior"],
                         ids=["no word of any set", "a prior's word"])
def test_the_form_s_line_says_a_word_of_its_own_set(token):
    """No stored answer carries the line, so the membership gate has no row
    to forge on (``NO_ROW_TO_FORGE_ON``); this is the row."""
    program, result = _answer(_model())
    themis.verify(program, result)
    forged = copy.deepcopy(result)
    claim, = [c for e in forged["extensions"]["assumption_ledger"]["assumptions"]
              for c in e["claim"] if c["vocabulary"] == "stated_form_claim"]
    claim["token"] = token
    with pytest.raises(SyntacticError):
        themis.verify(program, forged)


@pytest.mark.parametrize("forge, rule", [
    (_mark_it_the_model_s, "probability_models_check"),
    (_drop_it, "probability_models_check"),
    (_hand_the_line_to_the_model, "assumption_ledger_check"),
    (_drop_the_line, "assumption_ledger_check"),
], ids=["the caller's table marked the model's", "the table left out",
        "the caller's line handed to the model", "the line left out"])
def test_the_list_is_held_to_the_program_and_the_line_to_the_list(forge, rule):
    program, result = _answer(_model())
    with pytest.raises(VerificationError) as refused:
        themis.verify(program, _forged(result, forge))
    assert refused.value.rule == rule
