"""A verdict about the graph is the answer only where a graph was asked about.

``structural_result.value`` is one boolean field carrying ten different
propositions. Across one suite run 1397 results reached a reader and 271
were answered with it; 81 of those had asked for a number — 78 ``effect``
and 3 ``proximal_effect`` — so "结论：是" was the whole answer to "how large
is this effect". Thirty-four of the 78 carried a ``formula``, meaning the
sentence they needed sat one branch below the one that caught them.

:mod:`themis.questions` makes the proposition a fact instead of a guess.
These tests hold the vocabulary against the schema that defines it, hold
each surface to covering it, and hold the six measured cells to what a
reader should now get.
"""
import json
import pathlib
import re

import pytest

import themis
from themis import language
from themis import questions, registry
from tests import web_source
from themis.output.analysis_report import (
    _render_answer, _render_question, build_analysis_report,
)

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "themis" / "schemas"
          / "query_result.schema.json")
WEB_SURFACE = (pathlib.Path(__file__).resolve().parent.parent / "themis" / "web"
               / "frontend" / "src" / "lib" / "verdict.ts")


# --- the vocabulary ----------------------------------------------------------


def test_the_vocabulary_is_the_schemas_query_kind_enum():
    """Both directions. A kind in the schema with no reading is a question
    every surface answers by falling back; a reading for a kind the schema
    does not admit is a sentence no result can reach."""
    declared = json.loads(SCHEMA.read_text(encoding="utf-8"))
    enum = set(declared["properties"]["query_kind"]["enum"])
    assert {q.kind for q in questions.DECLARED} == enum


def test_query_kind_is_required_so_a_reading_is_always_resolvable():
    """Why this table needs no default — and why a default would be a
    regression rather than caution."""
    declared = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert "query_kind" in declared["required"]


def test_exactly_the_three_questions_about_the_graph_are_answered_by_a_verdict():
    """Pinned literally, because it is the fact every surface keys off and
    it is not guessable from the field: ``identify`` asks whether the
    estimand is identifiable, so the same proposition that is scaffolding
    for an effect query is the answer for this one."""
    answered = {q.kind for q in questions.DECLARED if q.verdict_is_the_answer}
    assert answered == {"cause", "assoc", "identify"}


def test_every_reading_states_a_proposition_for_both_values():
    """``settles`` / ``fails`` are propositions, not ways of saying yes and
    no; a blank one puts the bare boolean back on the surface."""
    for q in questions.DECLARED:
        assert q.asks and q.settles and q.fails, q.kind
        assert q.settles != q.fails, q.kind


def test_a_surface_that_misses_a_query_kind_is_refused():
    with pytest.raises(ValueError, match="no reading for query kind"):
        questions.bind({questions.CAUSE: "x"})


def test_a_surface_cannot_bind_a_kind_the_vocabulary_does_not_have():
    made_up = questions.Question("mediation_kind", asks="", settles="a",
                                 fails="b", verdict_is_the_answer=False,
                                 names_an_estimand=True,
                                 interval_fallback=None)
    with pytest.raises(ValueError, match="not a declared query"):
        questions.bind({q: "x" for q in questions.DECLARED} | {made_up: "x"})


def test_an_unknown_kind_raises_rather_than_defaulting():
    """The default is what this module removes; one here would restore it
    under a new name."""
    with pytest.raises(registry.NoRowDeclared) as caught:
        questions.reading_of("effekt")
    assert caught.value.args[0] == "themis.questions.BY_KIND"
    assert "effect" in caught.value.args[2]


def test_the_explainer_is_bound_rather_than_chained():
    """The one surface that was already complete: an ``if`` chain over all
    ten kinds whose fall-through raised. Its guarantee moves from "the
    eleventh branch raises once a result of a new kind arrives" to "a kind
    without an explainer fails at import"."""
    from themis.output import explainer
    assert set(explainer._EXPLAINERS) == set(questions.DECLARED)


# --- the six measured cells --------------------------------------------------


def _res(kind, value, **extra):
    return {"status": "structurally_solved", "query_kind": kind,
            "structural_result": {"value": value}, **extra}


def test_a_question_that_asked_for_a_number_is_not_answered_with_a_verdict():
    """32 results in one suite run: a mediation decomposition identified at
    the structural layer, no formula, no estimate. The whole answer section
    read ``结论：**是**``."""
    line = _render_answer(_res("effect", True), lang=language.DEFAULT)
    assert not line.startswith("结论")
    assert "可识别" in line and "没有给出数值" in line


def test_not_identifiable_is_stated_as_such_rather_than_as_no():
    """12 results: ``结论：**否**`` to "how large is the effect" — not a
    weak answer to that question but not a sentence about it."""
    line = _render_answer(_res("effect", False, status="needs_investigation"), lang=language.DEFAULT)
    assert not line.startswith("结论")
    assert "不可识别" in line


def test_an_identified_estimand_gets_the_line_that_was_already_written():
    """34 results carried a ``formula``, so the sentence they needed was
    one branch below the verdict that caught them. Nothing was added for
    this cell — the verdict simply stopped claiming it."""
    line = _render_answer(_res("effect", True, formula={"op": "sum"}), lang=language.DEFAULT)
    # The line points at the estimand, not at the verdict. Where it points
    # moved once the report learned to render the formula; that it points
    # away from 结论 is the fact this cell is about.
    assert "估计式" in line and "没有数据" in line
    assert "结论" not in line


def test_the_verdict_still_answers_the_questions_that_asked_one():
    line = _render_answer(_res("cause", True,
                               structural_result={"value": True,
                                                  "supporting_paths": [["x", "y"]]}), lang=language.DEFAULT)
    assert line.startswith("结论：**是**")
    # The proposition the verifier checked, which is reachability over the
    # edges the caller drew — not a sentence about the world.
    assert "有向路径" in line and "图里" in line
    assert "支持路径 1 条" in line


def test_a_false_verdict_on_a_graph_question_is_still_the_answer():
    line = _render_answer(_res("assoc", False), lang=language.DEFAULT)
    assert line.startswith("结论：**否**")
    assert "d-分离" in line


@pytest.mark.parametrize("kind", [q.kind for q in questions.DECLARED], ids=str)
def test_no_query_kind_falls_through_to_no_renderable_field(kind):
    """The fall-through the verdict used to hide. A result carrying an
    identifiability verdict and nothing else must say what it settled."""
    line = _render_answer(_res(kind, True), lang=language.DEFAULT)
    assert line != "（无可呈现的答案字段）"
    assert line.strip()


# --- the question line -------------------------------------------------------


AST_SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "themis" / "schemas"
              / "kernel_ast.schema.json")


def _query_schemas() -> dict[str, dict]:
    """Each query kind's own schema node, resolved through ``$defs.query``.

    Read rather than transcribed: the branch this file exists to fix asked
    an ``assoc`` query about ``from`` / ``to``, which are the *cause*
    query's fields, and the first version of this test agreed with it
    because the fixture had been copied from the renderer.
    """
    schema = json.loads(AST_SCHEMA.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    out = {}
    for ref in defs["query"]["oneOf"]:
        node = defs[ref["$ref"].rsplit("/", 1)[1]]
        out[node["properties"]["kind"]["const"]] = node
    return out


def _a(name):
    return {"predicate": name, "args": [{"type": "const", "name": "me"}]}


def _g(name, value=True):
    return {"atom": _a(name), "value": value}


# One query per kind, in the schema's own field names, and the predicates a
# reader must find in the question line.
QUERIES = {
    "cause": ({"from": _a("qa"), "to": _a("qb")}, ("qa", "qb")),
    "assoc": ({"left": _a("qa"), "right": _a("qb"), "given": [_a("qc")]},
              ("qa", "qb", "qc")),
    "effect": ({"target": _g("qb"), "intervention": {"atom": _a("qa"), "value": True},
                "given": [_g("qc")]}, ("qa", "qb", "qc")),
    "identify": ({"target": _a("qb"), "intervention": {"atom": _a("qa"), "value": True},
                  "given": []}, ("qa", "qb")),
    "probability": ({"target": _g("qb"), "given": [_g("qc")]}, ("qb", "qc")),
    "counterfactual": ({"observed": _g("qa", False),
                        "counterfactual_intervention": {"atom": _a("qa"), "value": True},
                        "counterfactual_target": _g("qb")}, ("qa", "qb")),
    "causation": ({"cause": _a("qa"), "effect": _a("qb")}, ("qa", "qb")),
    "scm_counterfactual": ({"intervention": {"atom": _a("qa"), "value": 1},
                            "target": _a("qb")}, ("qa", "qb")),
    "counterfactual_conjunction": ({"events": [{"variable": _a("qa"), "value": True}]},
                                   ("1",)),
    "proximal_effect": ({"treatment": _a("qa"), "outcome": _a("qb"), "latent": _a("qu"),
                         "treatment_proxy": [_a("qz")], "outcome_proxy": [_a("qw")],
                         "channel": {"kind": "discrete_channel",
                 "latent_cardinality": 2}},
     ("qa", "qb", "qu", "qz", "qw")),
}


def test_the_fixtures_are_built_from_the_schema_not_from_the_renderer():
    """What the first version of this file got wrong. A fixture that shares
    the renderer's mistaken field name agrees with it and proves nothing."""
    schemas = _query_schemas()
    assert set(QUERIES) == set(schemas)
    for kind, (query, _expected) in QUERIES.items():
        node = schemas[kind]
        allowed = set(node["properties"]) - {"kind"}
        assert set(query) <= allowed, (
            f"{kind} fixture uses {sorted(set(query) - allowed)}, which the "
            f"schema does not declare")
        required = set(node.get("required", ())) - {"kind"}
        assert required <= set(query), (
            f"{kind} fixture omits required {sorted(required - set(query))}")


@pytest.mark.parametrize("kind", sorted(QUERIES), ids=str)
def test_a_question_line_names_what_it_was_asked_about(kind):
    """Six kinds had no branch at all and rendered as ``（查询类型：`x`）``;
    ``assoc`` had one that could not fire and would have printed ``?`` for
    both variables if it had."""
    query, expected = QUERIES[kind]
    prog = {"version": "0.1", "domain": {"objects": []},
            "statements": [{"kind": "query", "id": "q",
                            "query": {"kind": kind, **query}}]}
    line = _render_question({"query_kind": kind}, prog, lang=language.DEFAULT)
    assert line != f"（查询类型：`{kind}`）", "the fallback shape survives"
    missing = [t for t in expected if t not in line]
    assert not missing, f"{kind} dropped {missing} from: {line!r}"
    assert "?" not in line, f"{kind} rendered an unresolved atom: {line!r}"


@pytest.mark.parametrize("kind", [q.kind for q in questions.DECLARED], ids=str)
def test_a_question_with_no_program_still_says_what_was_asked(kind):
    """``build_analysis_report`` is often called without the program. Every
    kind then states its question in prose rather than echoing its enum —
    checked as "the fallback shape is gone", not as "the token is absent":
    the ``identify`` line may name its enum after asking the question, and
    a token-presence rule cannot tell that apart from the token standing in
    for it.
    """
    line = _render_question({"query_kind": kind}, None, lang=language.DEFAULT)
    assert line != f"（查询类型：`{kind}`）", "the fallback shape survives"
    assert sum(1 for ch in line if "一" <= ch <= "鿿") >= 6, line


def test_each_result_is_asked_its_own_question():
    """One program, two queries. The question line used to take the FIRST
    query statement regardless of which result was being rendered, so the
    assoc report opened with "x 是否因果影响 y" — the cause query's
    question, about something that report does not answer. Every fixture
    in the suite carries one query, which is why it never showed.
    """
    prog = {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "query", "id": "c", "query": {
                    "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
                {"kind": "query", "id": "a", "query": {
                    "kind": "assoc", "left": _atom("x"), "right": _atom("y"),
                    "given": []}}]}
    lines = {r["query_kind"]: _render_question(r, prog, lang=language.DEFAULT)
             for r in themis.run(prog)["results"]}
    assert "因果影响" in lines["cause"]
    assert "相关联" in lines["assoc"]
    assert "因果影响" not in lines["assoc"]


def test_a_query_id_the_program_does_not_carry_falls_back_to_prose():
    """Rather than to some other query's atoms."""
    prog = {"version": "0.1", "domain": {"objects": []}, "statements": [
        {"kind": "query", "id": "c", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}}]}
    line = _render_question({"query_kind": "assoc", "query_id": "elsewhere"}, prog, lang=language.DEFAULT)
    assert "x" not in line and "y" not in line
    assert "相关联" in line


def test_a_query_of_another_kind_is_not_handed_to_this_kinds_renderer():
    """A result naming no ``query_id`` beside a program leading with a
    different question. Both of today's question-line bugs were a renderer
    reading fields that belong to another kind, so the mismatch is dropped
    rather than rendered as a row of ``?``."""
    prog = {"version": "0.1", "domain": {"objects": []}, "statements": [
        {"kind": "query", "id": "c", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}}]}
    line = _render_question({"query_kind": "causation"}, prog, lang=language.DEFAULT)
    assert "?" not in line
    assert "归因概率" in line


# --- the surface that cannot import the table --------------------------------


def _web_readings() -> dict[str, bool]:
    """The flag each reading carries, read off the browser's source.

    Through :mod:`tests.web_source` rather than a regex of this file's own,
    which is what a table growing a language axis breaks: the flag stopped
    sharing a line with the member's opening brace and the regex went
    quietly empty rather than failing.
    """
    entries = web_source.members(
        "QUESTION_READINGS", web_source.read(web_source.VERDICT))
    assert entries, "verdict.ts declares no QUESTION_READINGS"
    return {name: re.search(r"answersIt:\s*(true|false)", said).group(1) == "true"
            for name, said in entries.items()}


def test_the_web_reads_the_same_verdicts_the_same_way():
    """The browser renders from TypeScript and cannot import the table, so
    its copy is parsed and held equal — including the flag, which is the
    fact rather than the wording."""
    assert _web_readings() == {q.kind: q.verdict_is_the_answer
                               for q in questions.DECLARED}


def test_the_web_has_no_fallback_reading_left():
    """The 成立 / 不成立 default was the shape of "this kind has no
    reading", and a fallback reads exactly like coverage."""
    source = WEB_SURFACE.read_text(encoding="utf-8")
    assert "成立'" not in source.split("QUESTION_READINGS")[0]
    assert "label: '成立'" not in source


# --- end to end --------------------------------------------------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def test_a_real_mediation_run_no_longer_answers_a_number_with_a_verdict():
    """The reproduction the measurement started from: x → m → y, asked for
    the effect of x on y through m. Structurally identified, no data."""
    prog = {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "m", "domain": [True, False]},
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
                {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                    "mediator": _atom("m")}}]}
    result = themis.run(prog)["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    report = build_analysis_report(result, program=prog)
    answer = report.split("## 答案", 1)[1].split("##")[0]
    assert "结论" not in answer, answer
    assert "可识别" in answer and "没有给出数值" in answer
