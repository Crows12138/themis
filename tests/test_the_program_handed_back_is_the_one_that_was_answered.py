"""``apply_patch_and_run`` hands back a program, and it was a different one.

The second turn of the ordinary Themis loop returns ``merged_program``,
and the kernel's own docstring tells a caller to audit the answer against
it — "the exact program the kernel computed on, not the pre-patch input".
Writing that document is a second writer of a shape the parser owns, and a
second writer learns a field late or never. Six had never been written:
``mediator``, ``mediators`` and ``target_population`` on an effect
question, ``target_population`` on an identify one, and the two
experimental risks a counterfactual question may carry itself.

So a mediation question came back a total-effect question, and a
transported question came back a one-population question — measured over
the answer corpus, seven of forty-five programs came back changed. The
loop's own transport test caught it only when a new rule read the field
the caller had lost: verifying a transported estimand against the merged
program refused it, because that program no longer asked about a
population.

Every feature that added a field to a query has a wiring test for its own
field. The general question — does anything the parser reads go unwritten
— was asked by none of them, and is asked here twice: once of the writer's
own text, so a field added tomorrow is caught whether or not any program
uses it, and once of every program the corpus has, because being
mentioned is not the same as being written correctly.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import pathlib
import re

import pytest

import themis
from themis import kernel, types
from themis.input.semantic_validator import validate_program

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _query_writers() -> dict[str, str]:
    """``query class name -> the source of the branch that writes it``."""
    source = inspect.getsource(kernel._query_to_dict)
    parts = re.split(r"\n    if isinstance\(q, (\w+)\)", source)
    return dict(zip(parts[1::2], parts[2::2]))


def _unwritten(body: str, query_class: str) -> list[str]:
    """Fields of ``query_class`` that ``body`` never reads off the query.

    On a word boundary: ``q.mediator`` is a prefix of ``q.mediators``, and
    a check that reads one as the other passes on the very field it was
    written to catch.
    """
    fields = [f.name for f in dataclasses.fields(getattr(types, query_class))]
    return [name for name in fields if not re.search(rf"q\.{name}\b", body)]


# ------------------------------------------- what the writer knows about


def test_the_writer_has_a_branch_for_every_query_the_parser_builds():
    """Stated so the two sides cannot drift apart quietly."""
    written = set(_query_writers())
    built = {
        name for name in dir(types)
        if name.endswith("Query") and dataclasses.is_dataclass(
            getattr(types, name))
    }
    assert written == built, built ^ written


@pytest.mark.parametrize("query_class", sorted(_query_writers()))
def test_no_field_of_a_question_goes_unwritten(query_class):
    """Every field of every query dataclass is named by the branch that
    writes it. A field the writer never mentions is a field the caller
    never gets back, whatever the schema allows — and no program has to
    exercise it for this to be true."""
    unwritten = _unwritten(_query_writers()[query_class], query_class)
    assert unwritten == [], (query_class, unwritten)


def test_a_field_left_out_is_what_this_notices():
    """The shape the writer actually shipped, handed back to the check.

    A gate that has only ever been seen green says nothing about what it
    can see, so the six fields as they stood are put in front of it: the
    effect branch with its last three lines gone, and — because one name
    is a prefix of another — a branch that writes ``mediators`` alone.
    """
    branch = _query_writers()["EffectQuery"]
    assert _unwritten(branch, "EffectQuery") == []

    def without(*names):
        return "\n".join(
            row for row in branch.splitlines()
            if not any(re.search(rf"q\.{name}\b", row) for name in names))

    assert _unwritten(without("mediator", "mediators", "target_population"),
                      "EffectQuery") == [
        "mediator", "mediators", "target_population"]
    assert _unwritten(without("mediator"), "EffectQuery") == ["mediator"]


# -------------------------------------- and that it writes them correctly


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_program_written_back_parses_to_the_program_it_came_from(shape):
    """Being mentioned is not being written. Forty-four real programs,
    parsed, written back, and parsed again."""
    once = validate_program(SHAPES[shape]["program"])
    twice = validate_program(kernel._program_to_ast_dict(once))
    assert once.statements == twice.statements
    assert once.objects == twice.objects


def test_the_loop_hands_back_the_question_it_was_asked():
    """The end-to-end shape this was found in: a source-only transport
    program, an LLM-proposed target marginal, and a merged program a
    caller is told to audit against. It has to ask the same question — and
    the plainest way to say that is that running it again gives the same
    answer."""
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent / "test_runtime"))
    import test_llm_prior_transport_loop as loop

    program = loop._source_only_program()
    out = themis.apply_patch_and_run(program, [loop._llm_prior_patch_bundle()])
    merged, answer = out["merged_program"], out["results"][0]

    asked, = [s["query"] for s in merged["statements"]
              if s.get("kind") == "query"]
    assert asked["target_population"] == "rural_india"

    again = themis.run(merged)["results"][0]
    assert again["status"] == answer["status"] == "numerically_solved"
    assert again["numeric_result"] == answer["numeric_result"] == {
        "value": 0.505}
    themis.verify(merged, answer)
