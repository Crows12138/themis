"""The identification formula, said out loud.

``formula`` is a first-class field and 788 results in one suite run
carried one. Every one of them was told the same two things: the answer
line offered "估计式已生成，见文末审计", and the audit footer it pointed
at said "估计式已生成（机器可读，见 ``result.formula``）". Two pointers,
nothing at the end of either.

It is the residue of a section built one round too early: when the report
gained "怎么算出来的", ten renderers were bound to the ten identification
blocks in ``extensions``, and ``formula`` is a field rather than a block —
so the binding that catches a block nobody renders never looked at it.

The browser's ``lib/formula.ts`` existed all along and copying it would
have carried two defects across, both found by reading the schema instead
of that file: the grammar declares five node kinds and it handled four, so
a ``constant`` rendered as the word "constant"; and every bound value
printed as the letter ``z`` while the sum's subscript came from the atom,
so one formula named one variable two ways and nested sums (89 results in
that run, to depth 6) collapsed distinct bindings into one letter.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import themis
from themis.output import formula_text
from themis.output.analysis_report import build_analysis_report

from . import schema_walk


def _schema_node_kinds() -> set[str]:
    """The kinds the grammar admits, wherever each one is written down.

    Resolution is borrowed rather than done here: three of these branches name
    a shape that query_result.schema.json borrows from derivation.schema.json,
    and a reader that only splits the last path segment off a ``$ref`` finds
    nothing there and reports a smaller grammar than the one in force.
    """
    branches = schema_walk.RESULT.spec["$defs"]["formulaExpression"]["oneOf"]
    return {schema_walk.RESULT.resolve(branch)["properties"]["kind"]["const"]
            for branch in branches}


# --- the grammar is covered in both directions --------------------------------


def test_every_node_the_grammar_admits_has_a_renderer():
    """A kind with no renderer reaches the reader as its own name — which
    is what put the word "constant" on the browser's screen."""
    assert _schema_node_kinds() == set(formula_text.DECLARED)


def test_a_surface_that_misses_a_kind_is_refused_at_import():
    with pytest.raises(ValueError, match="no renderer for formula node kind"):
        formula_text.bind({k: str for k in formula_text.DECLARED
                           if k != formula_text.SUM})


def test_a_renderer_for_a_kind_the_grammar_forbids_is_refused():
    with pytest.raises(ValueError, match="does not admit"):
        formula_text.bind({**{k: str for k in formula_text.DECLARED},
                           "integral": str})


def test_an_undeclared_kind_is_loud_rather_than_named_back():
    with pytest.raises(formula_text.UnknownNodeKind):
        formula_text.render({"kind": "integral"})


# --- the notation ------------------------------------------------------------


def _atom(p, obj="me"):
    return {"predicate": p, "args": [{"type": "const", "name": obj}]}


def _p(target, given=(), value=True):
    return {
        "kind": "probability_ref",
        "target": {"atom": _atom(target), "value": value},
        "given": [{"atom": _atom(g), "value": v} for g, v in given],
    }


def test_a_true_value_is_the_bare_predicate_and_false_is_negated():
    assert formula_text.render(_p("y", [("x", True)])) == "P(y | x)"
    assert formula_text.render(_p("y", [("x", False)])) == "P(y | ¬x)"


def test_a_value_the_query_binds_from_outside_is_the_bare_predicate():
    """``valuedAtom.value`` may be absent — the enclosing query fixes it."""
    node = {"kind": "probability_ref",
            "target": {"atom": _atom("y")}, "given": []}
    assert formula_text.render(node) == "P(y)"


def test_a_summed_variable_is_the_atom_not_an_equation():
    """``P(z=z)`` is noise: the sum ranges over that very atom."""
    node = {
        "kind": "sum", "bind": {"name": "z_z_me"}, "over": _atom("z"),
        "body": {"kind": "probability_ref",
                 "target": {"atom": _atom("z"),
                            "value": {"kind": "var_ref", "name": "z_z_me"}},
                 "given": []},
    }
    assert formula_text.render(node) == "Σ_z [ P(z) ]"


def test_a_constant_says_its_value():
    assert formula_text.render({"kind": "constant", "value": 0.5}) == "0.5"


def test_nested_sums_keep_their_own_variables():
    """The letter-z bug, as a rule. Two bindings, two names."""
    inner = {
        "kind": "sum", "bind": {"name": "b2"}, "over": _atom("w"),
        "body": {"kind": "probability_ref",
                 "target": {"atom": _atom("w"),
                            "value": {"kind": "var_ref", "name": "b2"}},
                 "given": [{"atom": _atom("z"),
                            "value": {"kind": "var_ref", "name": "b1"}}]},
    }
    node = {"kind": "sum", "bind": {"name": "b1"}, "over": _atom("z"),
            "body": inner}
    assert formula_text.render(node) == "Σ_z [ Σ_w [ P(w | z) ] ]"


# --- and on real formulas -----------------------------------------------------


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_EFFECT = {"kind": "query", "id": "q", "query": {
    "kind": "effect",
    "target": {"atom": _atom("y"), "value": True},
    "intervention": {"atom": _atom("x"), "value": True},
    "given": [],
}}


def _program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [*statements, _EFFECT]}


_BACKDOOR = _program([_var("x"), _var("y"), _var("z"),
                      _cause("x", "y"), _cause("z", "x"), _cause("z", "y")])
_FRONTDOOR = _program([
    _var("x"), _var("m"), _var("y"), _cause("x", "m"), _cause("m", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
])


@pytest.mark.parametrize("program, expected", [
    (_BACKDOOR, "Σ_z [ P(y | x, z) · P(z) ]"),
    # The intervened treatment and the summation index are the same
    # variable held two ways, so the index is primed — otherwise one
    # letter means the intervention in one factor and the sum in the next.
    (_FRONTDOOR, "Σ_m [ P(m | x) · Σ_x' [ P(y | x', m) · P(x') ] ]"),
])
def test_a_real_estimand_reads_as_the_notation_it_is(program, expected):
    result = themis.run(program)["results"][0]
    assert formula_text.render(result["formula"]) == expected


def test_the_report_says_the_estimand_instead_of_naming_the_field():
    report = build_analysis_report(themis.run(_BACKDOOR)["results"][0],
                                   program=_BACKDOOR)
    assert "Σ_z [ P(y | x, z) · P(z) ]" in report
    assert "机器可读" not in report
    assert "result.formula" not in report
    # And it lands in the section about how the answer was arrived at.
    route = report.split("## 怎么算出来的", 1)[1].split("##", 1)[0]
    assert "估计式" in route


# --- the surface that cannot import the table ---------------------------------


WEB = (pathlib.Path(__file__).resolve().parent.parent / "themis" / "web"
       / "frontend" / "src" / "lib" / "formula.ts")


@pytest.mark.parametrize("kind", sorted(formula_text.DECLARED))
def test_the_browser_renders_every_kind_the_grammar_admits(kind):
    """The weaker of the two guarantees, and stated as such: ``bind``
    proves the report has a renderer, this proves only that the browser
    names the case. It is still the difference between a node rendering
    as its own kind name and rendering as itself."""
    source = WEB.read_text(encoding="utf-8")
    assert f"case '{kind}'" in source, (
        f"{WEB.name} has no case for formula node kind {kind}"
    )
