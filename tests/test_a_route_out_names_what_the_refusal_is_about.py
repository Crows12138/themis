"""A refusal's way out names the input the refusal is about.

A refusal that produces no number tells the reader what it was short of —
``error_variance=``, ``states=``, the column ``x`` — and then offers a route
out that names the same thing: pass it, change it, supply data in which it
varies. One name, written twice by the site that raised the refusal.

Nothing had compared them. The rule beside this one asks whether a route is
one this build declares and whether it names something at all; neither
question is about WHAT it names, and the object is the whole of what the
reader is sent after. A refusal saying it is short of ``error_variance=``
and sending the reader to pass ``differential_by`` passed every door.

The two are spelt differently, which is why no reading of values pairs
them: the refusal spells the argument as the argument it is, sign and all,
and the route spells it as the name a reader types. Measured over every
site in this build that offers a route — fourteen name an input the refusal
also names, and all fourteen drop the sign — so the spelling is part of the
claim rather than noise around it.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

from themis import refusals
from themis.verifier import estimator_failure_rules as module
from themis.verifier.errors import VerificationError
from themis.verifier.estimator_failure_rules import verify_refusal_block as rule

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
THEMIS = pathlib.Path(refusals.__file__).parent

#: Answers whose refusal both names an input and offers a route that names
#: one. Pinned because a rule's reach is the point: silence is what this
#: looked like before, and silence is what a rule that stops reaching looks
#: like.
ANSWERS_EXERCISING_THIS = 2


def _the_input(failure) -> str | None:
    details = failure.get("details") or {}
    return next((details[key] for key in module._SAYS_WHICH_INPUT
                 if isinstance(details.get(key), str)), None)


def _a_route(failure):
    """The first route of that refusal whose object is an input."""
    for row in failure.get("remedies") or ():
        if (refusals.REMEDY_BY_NAME.get(str(row.get("remedy")))
                in module._NAMES_AN_INPUT and "subject" in row):
            return row
    return None


def _carriers() -> list:
    out = []
    for name, pair in SHAPES.items():
        failure = pair["result"].get("estimator_failure")
        if not isinstance(failure, dict):
            continue
        if _the_input(failure) is not None and _a_route(failure) is not None:
            out.append(name)
    return sorted(out)


CARRIERS = _carriers()


def test_the_corpus_exercises_this_rule():
    assert len(CARRIERS) == ANSWERS_EXERCISING_THIS, CARRIERS


def test_no_honest_answer_is_refused():
    """All of them, not only the carriers.

    A rule reading a block most answers do not carry has more quiet cases
    than loud ones, and a quiet case that raises is found last.
    """
    for _name, pair in SHAPES.items():
        rule(pair["result"])


@pytest.mark.parametrize("name", CARRIERS)
def test_a_route_that_names_another_input_is_refused(name):
    """The forgery this exists for."""
    result = copy.deepcopy(SHAPES[name]["result"])
    route = _a_route(result["estimator_failure"])
    route["subject"] = "some_other_input"
    with pytest.raises(VerificationError, match="one name written twice"):
        rule(result)


@pytest.mark.parametrize("name", CARRIERS)
def test_the_sign_that_marks_an_argument_is_part_of_the_claim(name):
    """The refusal spells the argument, the route spells the name typed.

    Holding the two as equal strings would refuse every honest answer;
    holding them as equal up to the sign would let the route spell it
    either way, and every site in this build spells it one way.
    """
    result = copy.deepcopy(SHAPES[name]["result"])
    failure = result["estimator_failure"]
    named = _the_input(failure)
    route = _a_route(failure)
    assert route["subject"] == named.rstrip("="), (route, named)
    if not named.endswith("="):
        pytest.skip("this refusal names a column rather than an argument")
    route["subject"] = named
    with pytest.raises(VerificationError, match="one name written twice"):
        rule(result)


def _one(details, remedies):
    return {"estimator_failure": {
        "estimator": "backdoor", "failure_type": "argument_not_given",
        "kind": "request", "details": details, "remedies": remedies}}


def test_what_this_rule_does_not_answer():
    """Two silences, each of them another author's question.

    A refusal that names no input has nothing to be held to — the object
    can also be a parameter of the estimator that refused, which the
    refusal has no occasion to state. And a route whose object is not an
    input is not about the input either. A second author for either would
    be two answers that disagree the first time one of them moves.
    """
    module._check_each_route_names_what_the_refusal_is_about(
        _one({"outcome": "y"},
             [{"remedy": "supply_input", "subject": "misclassification="}])
        ["estimator_failure"])
    module._check_each_route_names_what_the_refusal_is_about(
        _one({"argument": "error_variance="},
             [{"remedy": "use_method", "subject": "regression_calibration"},
              {"remedy": "change_design"}])["estimator_failure"])


def test_a_route_whose_object_is_an_input_is_held_whichever_it_is():
    """All three of them, not the one the corpus happens to carry."""
    for member in sorted(module._NAMES_AN_INPUT, key=str):
        failure = _one({"argument": "error_variance="},
                       [{"remedy": str(member),
                         "subject": "error_variance"}])["estimator_failure"]
        module._check_each_route_names_what_the_refusal_is_about(failure)
        failure["remedies"][0]["subject"] = "something_else"
        with pytest.raises(VerificationError, match="one name written twice"):
            module._check_each_route_names_what_the_refusal_is_about(failure)


def test_every_route_is_either_read_here_or_said_why_not():
    """The drift guard.

    A route added to the contract is a new object a reader is sent after,
    and whether it is an input is a question somebody has to answer. The
    three left out are left out for reasons written beside the table: a
    stratum is a level rather than an input, a method is not an input, and
    the last names nothing at all.
    """
    left_out = {refusals.Remedy.SUPPLY_DATA_STRATUM,
                refusals.Remedy.USE_METHOD,
                refusals.Remedy.CHANGE_DESIGN}
    assert module._NAMES_AN_INPUT | left_out == set(refusals.Remedy)
    assert not (module._NAMES_AN_INPUT & left_out)
    assert all(member.takes_object for member in module._NAMES_AN_INPUT)
    assert not refusals.Remedy.CHANGE_DESIGN.takes_object


def _sites() -> list:
    """Every call in this build that offers a reader a route out."""
    out = []

    def word(node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for path in sorted(THEMIS.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - the build parses
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if "remedies" not in kw or not isinstance(kw["remedies"], ast.List):
                continue
            named = next(
                (word(kw[key]) for key in module._SAYS_WHICH_INPUT
                 if key in kw and isinstance(word(kw[key]), str)), None)
            for entry in kw["remedies"].elts:
                if not (isinstance(entry, ast.Tuple) and len(entry.elts) == 2):
                    continue
                member = word(entry.elts[0])
                subject = word(entry.elts[1])
                if member is None or subject is None:
                    continue
                out.append((f"{path.name}:{node.lineno}", member, subject,
                            named))
    return out


def test_every_site_in_this_build_writes_the_two_the_same_way():
    """The half the stored answers cannot reach.

    Two answers carry this pairing and fourteen sites write it. A site
    whose refusal names one input and whose route names another is the
    defect this rule exists for, and it would ship the day that site is
    reached — so it is asked of the sites too, where the corpus is silent.
    """
    sites = _sites()
    assert len(sites) >= 14, sites
    wrong = []
    signs = 0
    for where, member, subject, named in sites:
        if named is None:
            continue
        if getattr(refusals.Remedy, member.rsplit(".", 1)[-1], None) \
                not in module._NAMES_AN_INPUT:
            continue
        if subject != named.rstrip("="):
            wrong.append((where, named, subject))
        elif named.endswith("="):
            signs += 1
    assert not wrong, wrong
    assert signs >= 8, signs
