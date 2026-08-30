"""Everything the front door refuses, it refuses to somebody.

``themis/upstream`` is the LLM-side layer: an agent hands it an extraction
dict and gets back a program, or gets back a refusal saying what was wrong
with what it handed in. Forty-nine of those refusals were f-strings at
their own raise sites, in English, and a raise site that writes its own
wording is the author of it.

The finding that made the cut small is that the OCCASION was already split
off. Every helper here takes a ``what`` — ``extraction.variables[3]`` —
and interpolates it, so the path had been a slot since the module was
written; only the sentence stayed welded to the site. Forty-nine sites are
sixteen species because what differed between them was almost always the
path, and the path was never the sentence.

Two vocabularies rather than one: seven species were "{where} must be a
dict / a list / a non-empty string / …", which is ONE sentence with a hole
for which shape. A hole a bare token cannot fill is exactly what
``language.Word`` exists for — stringifying ``dict`` into a Chinese
sentence puts an English token in it.
"""
from __future__ import annotations

import ast
import pathlib
import string

import pytest

from themis import language
from themis.upstream import (
    ExtractionError,
    ExtractionRefusal,
    ExtractionShapeError,
    MergeConflictError,
    PredicateLinkError,
    build_program_from_extraction,
    compose_program,
    diagnose_predicate_links,
    merge_edge_extractions,
    merge_variable_extractions,
)
from themis.upstream.extraction_words import Refuses, Shape, edge

UPSTREAM = pathlib.Path(
    __file__).resolve().parent.parent.parent / "themis" / "upstream"

MEMBERS = (*Refuses, *Shape)


# --------------------------------------------------------------------------
# the sets
# --------------------------------------------------------------------------


def _unwritten(members) -> list[tuple[object, str]]:
    """(member, language) for every text this build owes and does not have."""
    return [(m, tag) for m in members for tag in language.written()
            if not m.words.get(tag)]


def _disagreeing_holes(members) -> list[object]:
    """Members whose languages do not ask for the same facts."""
    out = []
    for m in members:
        holes = {
            frozenset(name for _t, name, _s, _c
                      in string.Formatter().parse(text) if name)
            for text in m.words.values()
        }
        if len(holes) > 1:
            out.append(m)
    return out


class _Stub:
    def __init__(self, words):
        self.words = words


def test_every_species_is_written_in_every_language_this_build_writes():
    assert not _unwritten(MEMBERS)


def test_the_two_languages_of_a_species_have_the_same_holes():
    assert not _disagreeing_holes(MEMBERS)


def test_the_completeness_gate_refuses_a_one_language_member():
    assert _unwritten([_Stub({"zh": "只有中文"})])
    assert _unwritten([_Stub({"zh": "有中文", "en": ""})])


def test_the_hole_gate_refuses_a_fact_only_one_reader_gets():
    assert _disagreeing_holes([_Stub({"zh": "{a} 和 {b}", "en": "only {a}"})])


def test_a_refusal_does_not_end_itself():
    """The opposite convention from an artifact's ``note``, and for a
    reason rather than by accident: this is rendered ALONE into
    ``str(exc)``, not joined into a paragraph, so there is no next
    sentence to be kept off. ``Malformed`` one layer down does the same.
    """
    ended = [m.value for m in MEMBERS
             for text in m.words.values() if text and text[-1] in "。."]
    assert not ended, ended


# --------------------------------------------------------------------------
# no site writes its own sentence any more
# --------------------------------------------------------------------------


def _raises_with_a_literal(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every ``raise X("...")`` in one module — a site writing its own
    wording, which is the shape this item removed."""
    out = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(
                node.exc, ast.Call) or not node.exc.args:
            continue
        first = node.exc.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out.append((node.lineno, first.value))
        elif isinstance(first, ast.JoinedStr):
            out.append((node.lineno, "<f-string>"))
    return out


@pytest.mark.parametrize("module", ["narrative_merge.py", "program_builder.py"])
def test_no_raise_site_writes_its_own_sentence(module):
    """The rule, on the source rather than on what a test happens to reach.

    A branch no case exercises is checked here exactly like one every case
    exercises, which is the one thing running the module cannot do.
    """
    assert not _raises_with_a_literal(UPSTREAM / module)


def test_the_rule_would_catch_a_site_that_did():
    """The counterexample, through the same function. A gate only ever run
    against material that passes it is a gate nobody has seen say no."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "m.py"
        p.write_text('def f(x):\n    raise ValueError(f"{x} must be a dict")\n',
                     encoding="utf-8")
        assert _raises_with_a_literal(p)
        p.write_text('def f(x):\n    raise ValueError(Species.IS_NOT, where=x)\n',
                     encoding="utf-8")
        assert not _raises_with_a_literal(p)


# --------------------------------------------------------------------------
# what a caller gets
# --------------------------------------------------------------------------


def _refused(fn, *args) -> ExtractionRefusal:
    with pytest.raises(ExtractionRefusal) as raised:
        fn(*args)
    return raised.value


def test_both_readers_get_the_whole_refusal():
    exc = _refused(build_program_from_extraction, [])
    for lang in sorted(language.written()):
        said = language.assemble(exc.species.words, exc.said, exc.words, lang)
        assert said and exc.species.value not in said
        # The shape is a WORD in the hole, so it arrives as the reader's
        # word rather than as the token `dict`.
        assert "Shape." not in said


def test_the_path_reads_the_same_to_everyone():
    """A path is a symbol. It is the half that always worked, and keeping
    it a fact rather than folding it into the sentence is what let sixteen
    species cover forty-nine sites."""
    exc = _refused(build_program_from_extraction, {
        "query_kind": "cause", "predicates": ["a", "b"], "edges": [],
        "query": {"from": "a", "to": "c"}})
    assert exc.said["where"] == "query.to"
    rendered = {language.assemble(exc.species.words, exc.said, exc.words, lg)
                for lg in language.written()}
    assert len(rendered) == len(language.written())
    assert all("query.to" in one for one in rendered)


def test_the_shape_is_a_word_and_not_seven_sentences():
    """The seven "must be a X" refusals are one species. If they were
    seven, an eighth shape would be an eighth sentence in two languages
    rather than one member in two."""
    seen = set()
    for bad, where in (
        ([], "extraction"),
        ({"query_kind": "cause", "predicates": ["a"], "edges": {},
          "query": {"from": "a", "to": "a"}}, "extraction.edges"),
        ({"query_kind": "cause", "predicates": ["a", "b"], "edges": [["a"]],
          "query": {"from": "a", "to": "b"}}, "extraction.edges[0]"),
    ):
        exc = _refused(build_program_from_extraction, bad)
        assert exc.species is Refuses.IS_NOT
        assert exc.said["where"] == where
        seen.add(exc.words["shape"]["token"])
    assert seen == {"dict", "list", "from_to_pair"}


@pytest.mark.parametrize("cls, species", [
    (ExtractionError, Refuses.QUERY_KIND_NOT_SUPPORTED),
    (ExtractionShapeError, Refuses.IS_NOT),
    (MergeConflictError, Refuses.TWO_VALUES_FOR_ONE_FIELD),
    (PredicateLinkError, Refuses.IS_NOT),
])
def test_the_channel_and_the_species_are_two_questions(cls, species):
    """The exception class says which door to catch at; the species says
    what went wrong. They were one string before, so a caller that wanted
    the second had to read the first."""
    assert issubclass(cls, ExtractionRefusal)
    assert species in set(Refuses)


def test_a_merge_conflict_names_the_field_and_both_values():
    exc = _refused(
        merge_variable_extractions,
        {"variables": [{"kind": "variable", "predicate": "x",
                        "threshold": "> 5"}]},
        {"variables": [{"kind": "variable", "predicate": "x",
                        "threshold": "> 9"}]})
    assert exc.species is Refuses.TWO_VALUES_FOR_ONE_FIELD
    assert exc.said == {"predicate": "x", "field": "threshold",
                        "first": "> 5", "second": "> 9"}


def test_an_edge_pair_travels_as_an_expression():
    """``x–y`` is written the same way for every reader, which is what
    ``language.within`` says about a conditioning set. It used to arrive
    as a Python tuple repr inside an English clause."""
    exc = _refused(
        merge_edge_extractions,
        {"edges": [{"kind": "cause", "from": {"predicate": "x"},
                    "to": {"predicate": "y"}}]},
        {"edges": [], "refusals": [{"kind": "refuse_direct_edge",
                                    "from": "x", "to": "y"}]})
    assert exc.species is Refuses.A_REFUSAL_MEETS_AN_EDGE
    assert exc.said["pair"] == edge("x", "y") == "x–y"


def test_a_link_bundle_that_rewrites_onto_nothing_says_which_targets():
    exc = _refused(
        compose_program,
        {"version": "0.1", "statements": [
            {"kind": "variable", "predicate": "running"}]},
        {"variables": [{"kind": "variable", "predicate": "runing_typo"}]},
        None,
        [{"source_predicate": "runing_typo", "target_predicate": "jogging"}])
    assert exc.species is Refuses.TARGET_IS_NOT_IN_THE_BASE
    assert "jogging" in exc.said["targets"]


def test_an_argument_out_of_range_is_a_refusal_and_not_an_assertion():
    """A caller can fix ``max_candidates=0``; it is not a bug in this
    package. Two sites raised a bare ``ValueError`` with an English
    sentence, and the LANGUAGE DEBT never counted either of them — which
    is why the gate above reads the source rather than the debt table."""
    with pytest.raises(ExtractionRefusal) as raised:
        diagnose_predicate_links({"version": "0.1", "statements": []},
                                 {"variables": []}, max_candidates=0)
    exc = raised.value
    assert exc.species is Refuses.BELOW_THE_MINIMUM
    assert exc.said == {"where": "max_candidates", "minimum": "1", "got": "0"}
