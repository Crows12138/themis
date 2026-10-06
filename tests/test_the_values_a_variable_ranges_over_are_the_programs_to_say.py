"""The values a variable ranges over are the program's to say.

#818. Every rule that re-derives a number sums over a variable's values,
and reads them from the parameter store the audit's context is rebuilt
with — by the same ``build_theta`` the kernel ran. On that one premise the
audit had nothing of its own, and #804 is what that cost: the builder read
a yes-or-no met at one of its values as a variable with ONE value, a sum
over it ran over a single term, the kernel reported a number, and the
audit, summing over the same single term, agreed.

``themis/verifier/domain_rules.py`` restates the reading from the program
and holds what the store answers to it. This file holds that the reading
agrees with the builder on honest programs of every shape, and that it
refuses each way a store can be wrong about a range — through forged
stores, because the builder put back the way it was before #804 is now
refused before any sum, by what follows.

Writing the reading down found a second hole in it, beside #804's. A
variable nothing declares ranges over the values met — and for a
yes-or-no that is both values, but for ``z`` met only at ``low`` it is
``{low}``. With P(z=low) = 0.4 written down, the sum over z ran over that
one value and the kernel reported 0.12 — 0.4 of an answer. The numbers
themselves refute the reading there: a variable met at every value its
range was read as having, with mass short of one, has values that were
never written. The builder now refuses that program and says which
declaration to complete; it used to skip the one-valued range as having
nothing to complete, which is where the axiom went unasked.
"""
from __future__ import annotations

import pathlib

import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime import theta_builder
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.numeric_estimator import RangeReadShort, Theta
from themis.runtime.theta_builder import ConflictingThetaEntry
from themis.runtime.theta_words import Refuses
from themis.verifier import VerificationError
from themis.verifier.domain_rules import verify_domains_are_the_programs

REPO = pathlib.Path(__file__).resolve().parent.parent


def atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def va(p, v):
    return {"atom": atom(p), "value": v}


def program(z_rows: dict, declare_z=None, declare_xy=True) -> dict:
    """x -> y with a common cause z; one row of numbers per value of z."""
    statements: list = []
    if declare_xy:
        statements += [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
        ]
    if declare_z is not None:
        statements.append(
            {"kind": "variable", "predicate": "z", "domain": declare_z})
    statements += [
        {"kind": "cause", "from": atom("x"), "to": atom("y")},
        {"kind": "cause", "from": atom("z"), "to": atom("x")},
        {"kind": "cause", "from": atom("z"), "to": atom("y")},
    ]
    for z, pz in z_rows.items():
        statements.append({"kind": "probability", "target": va("z", z),
                           "given": [], "value": pz})
        for x, py in ((True, 0.3), (False, 0.2)):
            statements.append({"kind": "probability", "target": va("y", True),
                               "given": [va("x", x), va("z", z)], "value": py})
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "intervention": va("x", True),
        "target": va("y", True), "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _premises(ast: dict):
    ground = instantiate(validate_program(validate_ast(ast)))
    return ground, project(ground), theta_builder.build_theta(ground)


HONEST = {
    "a yes-or-no met at one value": program({True: 0.4}),
    "a yes-or-no met at both": program({True: 0.4, False: 0.6}),
    "declared levels, one of them met": program(
        {"low": 0.4}, declare_z=["low", "mid", "high"]),
    "undeclared levels, as met": program({"low": 0.4, "high": 0.6}),
    "nothing declared at all": program({True: 0.4}, declare_xy=False),
}


@pytest.mark.parametrize("ast", list(HONEST.values()), ids=list(HONEST))
def test_the_reading_agrees_with_the_builder_on_an_honest_program(ast):
    ground, graph, theta = _premises(ast)
    verify_domains_are_the_programs(ground, graph.nodes, theta)


def _z(theta: Theta):
    return next(a for a in theta.domains if a.predicate == "z")


@pytest.mark.parametrize("wrong, said", [
    ((True,), "a yes-or-no read as one value"),
    ((True, False, "maybe"), "a value the program never names"),
    ((True, True, False), "a value listed twice"),
    ((), "no values at all"),
], ids=lambda v: v if isinstance(v, str) else None)
def test_a_store_wrong_about_a_range_is_refused(wrong, said):
    ground, graph, theta = _premises(HONEST["a yes-or-no met at one value"])
    forged = Theta(entries=theta.entries,
                   domains={**theta.domains, _z(theta): wrong},
                   declared=theta.declared)
    with pytest.raises(VerificationError, match=r"^domain: .* ranges z over"):
        verify_domains_are_the_programs(ground, graph.nodes, forged)


def test_a_declared_range_is_held_too():
    ground, graph, theta = _premises(HONEST["declared levels, one of them met"])
    forged = Theta(entries=theta.entries,
                   domains={**theta.domains, _z(theta): ("low",)},
                   declared=theta.declared)
    with pytest.raises(VerificationError, match="its declaration lists them"):
        verify_domains_are_the_programs(ground, graph.nodes, forged)


def test_a_variable_nothing_mentions_is_held_through_what_the_store_answers():
    """The rules read ``domain_of``, which answers for a variable the store
    holds nothing about. So that answer is what is held, for every variable
    in the graph, and not only the store's own table."""
    ast = program({True: 0.4})
    # A cause of y no statement puts a number on, or a value to.
    ast["statements"].insert(0, {"kind": "cause", "from": atom("w"),
                                 "to": atom("y")})
    ground, graph, theta = _premises(ast)
    assert not any(a.predicate == "w" for a in theta.domains)
    verify_domains_are_the_programs(ground, graph.nodes, theta)
    forged = Theta(entries=theta.entries, domains=theta.domains,
                   declared={**theta.declared, "w": (True,)})
    with pytest.raises(VerificationError, match=r"ranges w over \{True\}"):
        verify_domains_are_the_programs(ground, graph.nodes, forged)


def test_true_and_one_are_told_apart():
    ground, graph, theta = _premises(HONEST["a yes-or-no met at one value"])
    forged = Theta(entries=theta.entries,
                   domains={**theta.domains, _z(theta): (1, False)},
                   declared=theta.declared)
    with pytest.raises(VerificationError, match="^domain: "):
        verify_domains_are_the_programs(ground, graph.nodes, forged)


# ----------------------------------------------- the failure this is for

def test_the_builder_as_it_was_before_804_is_refused_before_any_sum(
        monkeypatch):
    """#804, replayed. With the builder reading a yes-or-no met at one value
    as a variable with one value, the kernel summed over a single term and
    reported a number where it should have asked for the other value — and
    the audit, rebuilt by the same builder, summed over the same single
    term and accepted it.

    The replay no longer reaches a number: the second hole's check marks
    z's range as short (0.4 at True is not all of its mass), and the sum
    over z is refused when it asks for the values. So the audit's own
    reading is held through forged stores above, which is the only way
    left to hand it a wrong range."""
    ast = program({True: 0.4})

    honest = themis.run(ast)["results"][0]
    assert honest["status"] == "needs_investigation", (
        "half of z's distribution is missing; the honest answer asks for it")

    monkeypatch.setattr(theta_builder, "_values_met", theta_builder._sort_values)
    refused = _refused(ast)
    assert refused.species is Refuses.THE_VALUES_MET_DO_NOT_EXHAUST_THE_RANGE


def test_the_honest_answer_to_the_same_program_is_accepted():
    ast = program({True: 0.4, False: 0.6})
    result = themis.run(ast)["results"][0]
    assert result["status"] == "numerically_solved"
    themis.verify(ast, result)


# ------------------------------------------- the second hole, in the builder

def _refused(ast: dict, channel=RangeReadShort):
    with pytest.raises(channel) as caught:
        themis.run(ast)
    return caught.value


@pytest.mark.parametrize("rows", [
    {"low": 0.4},
    {"low": 0.4, "high": 0.3},
    {1: 0.4},
], ids=["one level, 0.4 of the mass", "two levels, 0.7", "a number, 0.4"])
def test_summing_over_values_met_in_full_at_less_than_the_whole_mass_is_refused(
        rows):
    """Undeclared, met at these values only, and the numbers over them fall
    short of one: the variable has values the program never wrote. The
    effect sums over z, and the reply says which declaration to complete
    rather than reporting 0.4 of an answer."""
    refused = _refused(program(rows))
    assert refused.species is Refuses.THE_VALUES_MET_DO_NOT_EXHAUST_THE_RANGE
    assert refused.details["variable"] == "z"
    assert "domain" in str(refused)


def test_a_short_range_that_is_only_ever_read_is_no_obstacle():
    """An outcome is read at the value asked about and never summed over.
    ``y`` undeclared and met only at ``high``, with P(y=high | x, z) that
    is nowhere near all of y's mass, is an ordinary way to state an
    outcome, and the number comes out."""
    ast = program({True: 0.4, False: 0.6})
    ast["statements"] = [s for s in ast["statements"]
                         if not (s["kind"] == "variable" and s["predicate"] == "y")]
    for s in ast["statements"]:
        if s["kind"] == "probability" and s["target"]["atom"]["predicate"] == "y":
            s["target"]["value"] = "high"
        if s["kind"] == "query":
            s["query"]["target"]["value"] = "high"
    result = themis.run(ast)["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["numeric_result"]["value"] == pytest.approx(0.3)
    themis.verify(ast, result)


def test_the_same_values_declared_are_held_to_the_axiom_instead():
    """A declaration is the program's word on the range. Declared low/high
    and met at both with 0.7 of the mass is numbers that cannot be true,
    not a range read short."""
    refused = _refused(program({"low": 0.4, "high": 0.3},
                               declare_z=["low", "high"]), ConflictingThetaEntry)
    assert refused.species is Refuses.A_FULL_DISTRIBUTION_DOES_NOT_SUM_TO_ONE


def test_the_store_says_which_ranges_are_short_and_the_audit_holds_it_to_that():
    ground, graph, theta = _premises(program({"low": 0.4}))
    assert {a.predicate for a in theta.short} == {"z"}
    verify_domains_are_the_programs(ground, graph.nodes, theta)
    silent = Theta(entries=theta.entries, domains=theta.domains,
                   declared=theta.declared, short={})
    with pytest.raises(VerificationError, match=r"known to be short"):
        verify_domains_are_the_programs(ground, graph.nodes, silent)
    ground, graph, theta = _premises(HONEST["a yes-or-no met at one value"])
    forged = Theta(entries=theta.entries, domains=theta.domains,
                   declared=theta.declared, short={_z(theta): ("P(z=*)", 0.4)})
    with pytest.raises(VerificationError, match=r"known to be short"):
        verify_domains_are_the_programs(ground, graph.nodes, forged)


def test_a_variable_met_at_one_value_with_all_the_mass_is_that_value():
    result = themis.run(program({"low": 1.0}))["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["numeric_result"]["value"] == pytest.approx(0.3)


def test_a_yes_or_no_met_at_one_value_is_still_asked_for_the_other():
    """#804's reading is unchanged: naming True is not saying False cannot
    happen, so 0.4 at True is not a short range but half of one."""
    result = themis.run(program({True: 0.4}))["results"][0]
    assert result["status"] == "needs_investigation"


# ------------------------------------------------------------ independence

def test_the_reading_borrows_nothing_from_the_side_being_checked():
    source = (REPO / "themis" / "verifier" / "domain_rules.py").read_text(
        encoding="utf-8")
    assert "runtime" not in source.split('"""', 2)[2]
    assert "theta_builder" not in source.split('"""', 2)[2]


def test_the_audit_runs_it_on_every_answer():
    kernel = (REPO / "themis" / "kernel.py").read_text(encoding="utf-8")
    premises = kernel[kernel.index("def _premises_of("):]
    premises = premises[:premises.index("\ndef ", 10)]
    assert "verify_domains_are_the_programs(ground, graph.nodes, theta)" in premises
