"""A variable is shown by the name a reader would call it.

#815. A program's predicates are identifiers — ASCII, one token each, the
thing every formula, key and data column is written in — and that is what
the page showed a reader: ``quantitative_ability`` on the graph and in every
sentence about it, to somebody who asked in Chinese. The canvas asked the
same of whoever drew a graph, by turning every character that was not ASCII
into an underscore as it was typed.

A variable declaration now carries ``name``: what a reader calls the
variable, by language tag. Three things are held here.

**The kernel carries it and reads nothing from it.** It is parsed, it
survives being written back (the merged program a fill returns is written
by the kernel's second writer, which has dropped a new field before), and
two programs that differ only in it get the same answer.

**The model is told to write it**, in the language of the question.

**The page shows it.** The graph's nodes, every hole a sentence is filled
through, and the places that print an identifier-bearing string directly.
The browser cannot be imported, so what is pinned there is its source; the
behaviour was exercised on a real page when this landed.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.kernel import _program_to_ast_dict
from themis.types import VariableDeclaration
from themis.upstream import narrative_merge

from tests import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "themis" / "prompts" / "examples"
PROMPT = REPO / "themis" / "prompts" / "nl_to_kernel_ast.md"
SRC = web_source.SRC


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            *[{"kind": "cause",
               "from": {"predicate": a, "args": [{"type": "const", "name": "me"}]},
               "to": {"predicate": b, "args": [{"type": "const", "name": "me"}]}}
              for a, b in (("x", "y"), ("z", "x"), ("z", "y"))],
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": {"predicate": "x", "args": [
                    {"type": "const", "name": "me"}]}, "value": True},
                "target": {"atom": {"predicate": "y", "args": [
                    {"type": "const", "name": "me"}]}, "value": True},
                "given": []}},
        ],
    }


NAMES = {"x": {"zh": "每天运动"}, "y": {"zh": "体重下降", "en": "weight loss"},
         "z": {"zh": "年龄"}}


def _named() -> dict:
    program = _program()
    for s in program["statements"]:
        if s["kind"] == "variable":
            s["name"] = dict(NAMES[s["predicate"]])
    return program


def _declarations(program) -> dict:
    return {s.predicate: s for s in program.statements
            if isinstance(s, VariableDeclaration)}


# ------------------------------------------------------- the kernel carries it

def test_a_name_is_parsed_by_language_in_tag_order():
    program = validate_program(validate_ast(_named()), checks=frozenset())
    decls = _declarations(program)
    assert decls["x"].name == (("zh", "每天运动"),)
    assert decls["y"].name == (("en", "weight loss"), ("zh", "体重下降"))


def test_a_declaration_without_one_has_none():
    program = validate_program(validate_ast(_program()), checks=frozenset())
    assert all(d.name == () for d in _declarations(program).values())


def test_it_survives_being_written_back():
    """``_program_to_ast_dict`` is the program's second writer — the merged
    program every fill returns is its output — and a field it does not know
    is a field that disappears between two steps of one conversation."""
    program = validate_program(validate_ast(_named()), checks=frozenset())
    emitted = _program_to_ast_dict(program)
    said = {s["predicate"]: s.get("name") for s in emitted["statements"]
            if s["kind"] == "variable"}
    assert said == NAMES
    assert validate_program(validate_ast(emitted), checks=frozenset()) == program
    plain = _program_to_ast_dict(
        validate_program(validate_ast(_program()), checks=frozenset()))
    assert all("name" not in s for s in plain["statements"])


def test_nothing_is_computed_from_it():
    """Two programs that differ only in what their variables are called are
    the same program to the kernel: the same envelope, to the byte."""
    with_names = themis.run(_named())
    without = themis.run(_program())
    assert json.dumps(with_names["results"], sort_keys=True) == json.dumps(
        without["results"], sort_keys=True)


#: The worked examples that are whole programs (the others in the folder
#: are narrative extractions and fill replies, which are not run).
WORKED = {
    path.stem: json.loads(path.read_text(encoding="utf-8"))["kernel_ast"]
    for path in sorted(EXAMPLES.glob("*.json"))
    if "kernel_ast" in json.loads(path.read_text(encoding="utf-8"))
}


def test_the_worked_examples_are_the_five_this_file_was_written_against():
    """The roster is read off a folder, and a roster that came back empty
    would collect no case and report green."""
    assert len(WORKED) == 5
    assert all(any(s.get("kind") == "variable" for s in program["statements"])
               for program in WORKED.values())


@pytest.mark.parametrize("program", list(WORKED.values()), ids=list(WORKED))
def test_nothing_is_computed_from_it_on_a_worked_example(program):
    named = copy.deepcopy(program)
    declared = [s for s in named["statements"] if s.get("kind") == "variable"]
    for i, s in enumerate(declared):
        s["name"] = {"zh": f"变量{i}"}
    assert json.dumps(themis.run(named)["results"], sort_keys=True) == json.dumps(
        themis.run(program)["results"], sort_keys=True)


@pytest.mark.parametrize("name", [
    {},                      # says nothing
    {"zh": ""},              # an empty name
    {"zh": "   "},           # a blank one
    {"Chinese": "运动"},      # not a language tag
    {"zh": 3},               # not text
    "运动",                   # no language
], ids=["empty", "empty text", "blank text", "not a tag", "not text",
        "no language"])
def test_a_name_that_names_nothing_is_refused(name):
    program = _program()
    program["statements"][0]["name"] = name
    with pytest.raises(SyntacticError):
        validate_ast(program)


def test_two_documents_wording_one_variable_differently_do_not_conflict():
    """A name is how a variable is said, not a claim about it. Each language
    keeps the first wording it was given, and a language only one side has
    comes along."""
    a = {"kind": "variable", "predicate": "x", "name": {"zh": "运动"}}
    b = {"kind": "variable", "predicate": "x",
         "name": {"zh": "锻炼", "en": "exercise"}}
    merged = narrative_merge._merge_two_decls(a, b, "x")
    assert merged["name"] == {"en": "exercise", "zh": "运动"}
    assert "name" not in narrative_merge._merge_two_decls(
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "x"}, "x")


# ---------------------------------------------------- the model is told to

def test_the_translation_prompt_asks_for_it_in_the_questions_language():
    prompt = PROMPT.read_text(encoding="utf-8")
    section = prompt[prompt.index("### 2. Predicates"):]
    section = section[:section.index("When to omit `domain`")]
    assert "`name`" in section
    assert "language their question is written in" in " ".join(section.split())
    # The format anchor shows where it goes, and says the key is the
    # question's language rather than the skeleton's.
    assert '"name": {"en": "some cause"}' in prompt
    assert "keyed by the language of the question" in " ".join(prompt.split())


# ------------------------------------------------------------ the page shows it

def _code(*parts: str) -> str:
    return web_source.without_comments(
        web_source.read(SRC.joinpath(*parts)))


def test_a_hole_is_filled_with_the_names_in_force():
    fill = web_source.chunks(_code("lib", "language.ts"))["fill"]
    assert "typeof value === 'string' ? named(value) : String(value)" in fill


def test_a_name_replaces_an_identifier_only_where_it_stands_whole():
    names = _code("lib", "names.ts")
    assert "const IDENTIFIER = /[A-Za-z_][A-Za-z0-9_]*/g" in names
    assert "const said = names.get(token)" in names
    # No name in the reader's language is no name: the identifier shows,
    # and a name in another language does not stand in for it.
    assert "(s.name as Record<string, unknown> | undefined)?.[lang]" in names


def test_the_result_says_whose_names_are_in_force_as_it_renders():
    view = _code("components", "ResultView.tsx")
    assert "namesOf(program, lang)" in view
    assert "showNames(names, lang)" in view
    assert "() => showNames(null)" in view
    assert "named(fill(question, lang))" in view


@pytest.mark.parametrize("component, printed", [
    ("GapReport.tsx", "named(row.distribution)"),
    ("FramingFill.tsx", "nameOf(v)"),
    ("ProposedReview.tsx", "named(p.key)"),
    ("ProposedReview.tsx", "{named(e.from)} → {named(e.to)}"),
    ("SupplyNumbers.tsx", "named(label)"),
    ("SupplyNumbers.tsx", "named(a.table)"),
    ("Verdict.tsx", "named(r.value)"),
    ("Verdict.tsx", "named(cleanPathNode(node))"),
    ("Verdict.tsx", "named(formula)"),
    ("Recheck.tsx", "named(row.refusal)"),
    ("ResultView.tsx", "nameOf(d.predicate)"),
])
def test_what_is_printed_outside_a_sentence_is_said_by_name_too(
        component, printed):
    assert printed in _code("components", component)


def test_a_node_is_drawn_with_its_name_and_remembers_its_identifier():
    flow = web_source.chunks(_code("lib", "graph.ts"))["programToFlow"]
    assert "saidBy.get(v)?.[lang]?.trim() || v" in flow
    assert ("data: { label: shown(v), predicate: v, said: saidBy.get(v), "
            "shownAs: shown(v), role: roleMap.get(v) }") in flow


def test_the_canvas_takes_whatever_a_reader_types():
    canvas = _code("components", "CausalCanvas.tsx")
    assert "data.rename?.(id, e.target.value)" in canvas
    assert "replace(/[^a-zA-Z0-9_]/g" not in canvas


def test_which_identifier_a_node_is_written_as_is_read_off_its_text():
    written = web_source.chunks(_code("lib", "graph.ts"))["written"]
    # Untouched: the variable it came from, names and all.
    assert ("d.predicate && (text === '' || text === (d.shownAs ?? "
            "d.predicate))) as = { predicate: d.predicate, name: d.said }"
            ) in written
    # Typed as an identifier: that identifier, as it always was.
    assert "isIdentifier(text)) as = { predicate: text }" in written
    # Typed as anything else: the identifier stays and the text is its name.
    assert ("as = { predicate: d.predicate, name: { ...d.said, [lang]: text } }"
            ) in written
    # A new variable with such a text is given an identifier past any in use.
    assert "do { predicate = `v${++k}` } while (taken.has(predicate))" in written
    assert "out.set(u.id, { predicate, name: { [lang]: u.text } })" in written


def test_both_ways_back_to_a_program_read_it_that_way():
    to_program = web_source.chunks(_code("lib", "graph.ts"))["graphToProgram"]
    assert "written(nodes, lang)" in to_program
    builder = _code("components", "DagBuilder.tsx")
    assert "written(ns, lang)" in builder
    # The query's ends are picked by node, so retyping a name or switching
    # language does not unpick them.
    assert "<option key={o.id} value={o.id}>{o.label}</option>" in builder


def test_a_seeded_nodes_text_follows_the_language_until_it_is_retyped():
    canvas = _code("components", "CausalCanvas.tsx")
    assert "d.label !== (d.shownAs ?? d.predicate)) return n" in canvas
    assert "d.said?.[lang]?.trim() || d.predicate" in canvas
    # And seeding does not depend on the language, or switching it would
    # re-seed the canvas over the reader's edits.
    assert "programToFlow(prog, langNow.current)" in canvas


def test_a_column_headed_by_a_name_is_that_variables_column():
    assert "rowsAsWritten(data.rows, program)" in _code(
        "components", "EstimateWorkspace.tsx")
    rows = web_source.chunks(_code("lib", "names.ts"))["rowsAsWritten"]
    # The identifier's own column wins, and a name two variables share says
    # nothing about which.
    assert "headed.has(s.predicate)" in rows
    assert "by.size === 1" in rows
