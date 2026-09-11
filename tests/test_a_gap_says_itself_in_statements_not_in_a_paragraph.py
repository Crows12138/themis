"""What a gap says about itself is a list of statements (#437, fourth cut).

``description`` was a field: a finished paragraph, in whichever language
whoever built the report happened to pass, written at 38 construction
sites — four of which assembled two to five optional pieces into one
string, and four of which filled one template's hole with ANOTHER
template's rendered text. A paragraph on the envelope is a rendering that
already happened, so the language was decided in the kernel and every
pass that needed to know WHICH gap this was had to read the prose back.

So a description is :class:`themis.gaps.Sentence` members, each with its
own occasion, and the paragraph is assembled where the reader's language
is known. Which statements a gap has is what this occasion knows — a
species per combination would be a vocabulary of products.

``summary`` went with it, and for the reason (324) gives rather than for
this one: every input to it was on the report beside it. It was the first
gap's description, framed by the answer tier — a rendering of a
rendering, and the second thing that could not be a list of statements
while it lived on the envelope.

Three things follow, and this module holds all three:

**Every statement must have text, in every language this build writes.**
A member with no row is a sentence that raises at the one site that names
it, which is a defect found by the reader rather than by the build.

**A hole is a promise the producer has to keep.** ``{collider}`` in a
sentence is a sentence that cannot be assembled without one, so the table
and the construction sites are held equal — statically, and over every
site rather than over the ones that name their statement with a literal:
a site that picks between two statements has to fill the holes of both,
and that is the site most likely to fill neither.

**The paragraph belongs to the reader's language, seam included.** The
join between two statements is the language's and not either statement's.
It was baked into the texts: one carried an English ``also`` clause, and
in Chinese it reached the reader mid-paragraph.
"""
from __future__ import annotations

import ast
import pathlib
import re
import string
from dataclasses import fields

import pytest

from . import web_source
from themis import gaps, language
from themis.output import reader_words
from themis.output.result_orchestrator import data_gap_to_dict
from themis.types import (
    DataGap,
    DataGapReport,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Where a statement is built. Both modules, for the reason the channel
#: one over gives: the second author is why this is a gate at all.
BUILDERS = ("themis/output/data_gap_report.py",
            "themis/estimation/dispatch.py")

#: How many statements those two build, and how many of them name their
#: species with a literal. The rest pick between two by a local name, or
#: read one out of a table — three shapes, and the pairing below has to
#: reach all three or it checks the easy sites and calls it coverage.
BUILT = 81
NAMED = 78

#: How many of the statements have a hole. Stated rather than derived, so
#: that a table that quietly loses its holes cannot make the pairing below
#: true by having nothing left to pair.
HOLED = 66

#: The door, by the name it has where it is declared. A call is one of
#: these because of what it resolves to and not because of what it is
#: spelled: two other modules have a ``sentence`` of their own — a refusal
#: has one too — and a scan that went by the bare name would report them
#: as builders that this gate does not cover.
DOOR = "sentence"


def _a_species_saying(*said) -> GapKind:
    """A species that makes all of these statements.

    What this file is about is the STATEMENT, and the species carrying it
    is scaffolding — but a gap may only say what its own species says
    (:data:`themis.gaps.SENTENCES_OF`), so the scaffolding is read off
    that table rather than picked. One fixed kind stood here and was right
    for whichever statement was written first.
    """
    wanted = set(said)
    for kind in sorted(gaps.SENTENCES_OF, key=lambda k: k.value):
        if wanted <= gaps.SENTENCES_OF[kind]:
            return kind
    raise AssertionError(
        f"no species says all of {sorted(str(one) for one in wanted)}; a "
        f"gap saying two species' statements is what this build refuses")


def _gap(**kw) -> DataGap:
    """A gap, saying only what its species leaves open.

    The severity and the blocks it used to type were the species', so
    overriding the kind and leaving them behind built a gap contradicting
    itself — which the constructor refuses. What a gap SAYS is the same
    kind of value: the two are one choice, and a caller fixes whichever of
    them the test is about while this derives the other. Fixing one and
    leaving the other behind is what every caller here used to do.
    """
    kind, describes = kw.pop("kind", None), kw.pop("describes", None)
    if describes is None:
        describes = (gaps.sentence(
            sorted(gaps.says_of(kind), key=str)[0]
            if kind is not None else gaps.Sentence.A_DISTRIBUTION_IS_MISSING,
            what="P(y|x)"),)
    if kind is None:
        kind = _a_species_saying(*(one.sentence for one in describes))
    fields_ = {
        "kind": kind,
        "describes": describes,
        "provenance": (GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK,
                                        ref_id="x"),),
    }
    fields_.update(kw)
    return DataGap(**fields_)      # type: ignore[arg-type]


# --- every statement has text ------------------------------------------------


def test_the_statements_and_their_texts_are_the_same_set():
    """Both directions. A member with no row raises where it is built —
    which is to say, on the occasion that has it and not on the build; a
    row with no member is text nothing can reach, which is how a renamed
    statement leaves its wording behind."""
    assert set(gaps.DESCRIBES) == {str(one) for one in gaps.Sentence}


@pytest.mark.parametrize("statement", sorted(gaps.DESCRIBES))
def test_the_text_exists_in_every_language_this_build_writes(statement):
    """Not in every language it is ANSWERED in — a language being written
    is held to the same completeness, which is what makes it safe to offer
    on the day it is."""
    said = gaps.DESCRIBES[statement]
    assert set(said) == language.written(), statement
    assert all(text.strip() for text in said.values()), statement


@pytest.mark.parametrize("statement", sorted(gaps.DESCRIBES))
def test_the_languages_agree_about_where_the_holes_are(statement):
    """A hole one language has and another does not is a fact that reaches
    one reader and not the other, silently in the language with fewer."""
    per = {lang: frozenset(name for _, name, _, _
                           in string.Formatter().parse(text) if name)
           for lang, text in gaps.DESCRIBES[statement].items()}
    assert len(set(per.values())) == 1, per


@pytest.mark.parametrize("statement", sorted(gaps.DESCRIBES))
def test_a_statement_says_what_it_is_for_to_whoever_adds_the_next_one(
        statement):
    """The member's second half. It is not a reader's sentence — it is the
    one thing the next author needs and the wording cannot give them,
    which is when to reach for this statement rather than write a new
    one."""
    assert gaps.BY_SENTENCE[statement].says.strip()


# --- a hole is a promise -----------------------------------------------------


def _holes() -> dict[str, set[str]]:
    """The statements that have holes, and which. Derived here and pinned
    by count above: what the pairing compares is a table against a set of
    construction sites, two things written by different hands."""
    found = {name: language.holes(said)
             for name, said in gaps.DESCRIBES.items()}
    return {name: holes for name, holes in found.items() if holes}


def _own(scope: ast.AST) -> list[ast.AST]:
    """The nodes of one scope, not of a function nested inside it."""
    out: list[ast.AST] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda, ast.ClassDef)):
                continue
            out.append(child)
            walk(child)

    walk(scope)
    return out


def _bound(scope: ast.AST) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """What this scope binds: names to statements, names to dict keys.

    Both halves of what a site can say indirectly. A branch assigns one of
    two statements to a local; an occasion is built as a dict and splatted
    in. Neither is a literal at the call, and both are what a scan that
    read only literals would score as covered.
    """
    statements: dict[str, set[str]] = {}
    keys: dict[str, set[str]] = {}
    for node in _own(scope):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not names:
            continue
        named = {found.group(1) for sub in ast.walk(value)
                 if isinstance(sub, ast.Attribute)
                 for found in [re.fullmatch(r"Sentence\.(\w+)",
                                            ast.unparse(sub))]
                 if found}
        for name in names:
            if named:
                statements.setdefault(name, set()).update(
                    str(getattr(gaps.Sentence, one)) for one in named)
            if isinstance(value, ast.Dict):
                keys.setdefault(name, set()).update(
                    key.value for key in value.keys
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str))
    return statements, keys


def _calls_the_door(tree: ast.Module):
    """Whether a call in this module is a call to :func:`themis.gaps.sentence`.

    By what the name resolves to, through the module's own imports. Both
    spellings, because both are written: the builders import the function
    under an alias, and a test or a script reaches it through the module.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            here = (node.module or "").split(".")[-1]
            for alias in node.names:
                if here == "gaps" and alias.name == DOOR:
                    direct.add(alias.asname or alias.name)
                if alias.name == "gaps" and here in ("themis", ""):
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "themis.gaps":
                    modules.add(alias.asname or alias.name)

    def is_door(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        if isinstance(node.func, ast.Name):
            return node.func.id in direct
        return (isinstance(node.func, ast.Attribute)
                and node.func.attr == DOOR
                and ast.unparse(node.func.value) in modules)

    return is_door


def _declared_elsewhere(value: ast.AST) -> set[str] | None:
    """The statements in a table :mod:`themis.gaps` declares, or None.

    A site may read its statement out of a table in another module —
    ``gaps.DISPLACED_BECAUSE`` decides which reason a displaced pair is
    owed — and the scan saw only tables named locally. Resolving it means
    reading the real object rather than the name, which is available
    because the declaration is importable; a table that is not there is
    not a table this scan may guess at, so it says None and the caller
    raises.
    """
    if not (isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id in {"gaps", "_gaps"}):
        return None
    table = getattr(gaps, value.attr, None)
    if not isinstance(table, dict):
        return None
    return {str(one) for one in table.values()
            if isinstance(one, gaps.Sentence)} or None


def _sites(path: str) -> list[tuple[int, set[str], set[str], bool]]:
    """Every statement built in one module.

    ``(line, the statements it could be, the holes it fills, literal?)``.
    A first argument this cannot resolve is an assertion failure and not a
    skipped site: the whole value of the pairing is that its denominator
    is every site.
    """
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    is_door = _calls_the_door(tree)
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def scopes(node: ast.AST) -> list[ast.AST]:
        chain, cur = [], parent.get(node)
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Module)):
                chain.append(cur)
            cur = parent.get(cur)
        return chain + [tree]

    def lookup(node: ast.AST, name: str, half: int) -> set[str]:
        for scope in scopes(node):
            found = _bound(scope)[half].get(name)
            if found:
                return found
        return set()

    out = []
    for node in ast.walk(tree):
        if not is_door(node):
            continue
        assert node.args, f"{path}:{node.lineno} names no statement"
        first, literal = node.args[0], True
        if re.fullmatch(r"Sentence\.\w+", ast.unparse(first)):
            named = {str(getattr(gaps.Sentence,
                                 ast.unparse(first).split(".")[1]))}
        elif isinstance(first, ast.Name):
            named, literal = lookup(node, first.id, 0), False
        elif isinstance(first, ast.Subscript) and isinstance(
                first.value, ast.Name):
            named, literal = lookup(node, first.value.id, 0), False
        elif isinstance(first, ast.Subscript) and _declared_elsewhere(
                first.value) is not None:
            named, literal = _declared_elsewhere(first.value), False
        else:
            raise AssertionError(
                f"{path}:{node.lineno} builds a statement this scan cannot "
                f"resolve: {ast.unparse(first)}")
        assert named, f"{path}:{node.lineno} resolves to no statement"

        filled = set()
        for keyword in node.keywords:
            if keyword.arg is not None:
                filled.add(keyword.arg)
            elif isinstance(keyword.value, ast.Name):
                found = lookup(node, keyword.value.id, 1)
                assert found, (f"{path}:{node.lineno} splats a name this "
                               f"scan cannot resolve")
                filled |= found
            else:
                raise AssertionError(
                    f"{path}:{node.lineno} splats something this scan "
                    f"cannot resolve: {ast.unparse(keyword.value)}")
        out.append((node.lineno, named, filled, literal))
    return out


def test_the_scan_over_the_builders_reaches_what_it_claims_to():
    """A static scan that quietly matched nothing would pass every pairing
    below, so its own reach is stated first — including how much of it is
    the easy shape."""
    found = [site for path in BUILDERS for site in _sites(path)]
    assert len(found) == BUILT
    assert len([site for site in found if site[3]]) == NAMED
    assert len(_holes()) == HOLED


def test_nothing_outside_the_two_builders_says_a_gap_s_sentence():
    """What makes ``BUILDERS`` a denominator rather than a sample. A third
    module building one is not a defect — it is a module this gate does
    not cover, which is the same thing one commit later."""
    written = set()
    for path in sorted((ROOT / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        is_door = _calls_the_door(tree)
        if any(is_door(node) for node in ast.walk(tree)):
            written.add(path.relative_to(ROOT).as_posix())
    assert written == set(BUILDERS)


@pytest.mark.parametrize("path", BUILDERS)
def test_a_site_fills_exactly_the_holes_its_statement_has(path):
    """The pairing. A site that supplies nothing for a statement with a
    hole is a reader shown the hole's own name; one that supplies a fact
    for a statement with no hole is a fact that reaches nobody."""
    holes = _holes()
    for line, named, filled, _ in _sites(path):
        for one in named:
            assert filled == holes.get(one, set()), (path, line, one)


@pytest.mark.parametrize("path", BUILDERS)
def test_a_site_that_picks_between_two_can_fill_either(path):
    """The branch. Two statements reached from one call have to want the
    same facts — a site choosing between statements with different holes
    fills one of them and shows the other's hole to the reader, on
    whichever occasion takes the branch that was not measured."""
    holes = _holes()
    for line, named, _, _ in _sites(path):
        wanted = {frozenset(holes.get(one, set())) for one in named}
        assert len(wanted) == 1, (path, line, sorted(named))


def test_every_statement_is_one_some_site_can_reach():
    """The other direction of the pairing. A member nothing names is a
    sentence no reader can ever be shown, and it reads exactly like one
    that is simply rare."""
    reachable = {one for path in BUILDERS
                 for _, named, _, _ in _sites(path) for one in named}
    assert reachable == {str(one) for one in gaps.Sentence}


# --- the paragraph belongs to the reader -------------------------------------


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_seam_between_two_statements_is_the_language_s(lang):
    """Not either statement's. It was one statement's: a leading space so
    the English sentence before it would not run on, which in Chinese
    reached the reader as a gap mid-paragraph."""
    # Two statements of ONE species: a gap saying two species' statements
    # is what the constructor refuses, and the seam is the same seam.
    kind = max(gaps.SENTENCES_OF, key=lambda k: (len(gaps.SENTENCES_OF[k]),
                                                 k.value))
    first, second = sorted(gaps.SENTENCES_OF[kind], key=str)[:2]
    filling = _holes()

    def _said(one):
        return gaps.sentence(
            one, **{hole: hole.upper()
                    for hole in filling.get(str(one), ())})

    two = _gap(kind=kind, describes=(_said(first), _said(second)))
    seam = language.fill(language.BETWEEN_SENTENCES, lang)
    said = gaps.described(data_gap_to_dict(two), lang)
    assert said == seam.join(
        gaps.describe(one, lang) for one in two.describes)
    for one in two.describes:
        assert gaps.describe(one, lang) in said


def test_a_gap_with_nothing_to_say_says_nothing():
    """The empty case has one spelling, decided at the door. A join over
    no statements is the empty string and not a stray seam."""
    assert gaps.described(data_gap_to_dict(_gap(describes=()))) == ""


def test_a_statement_this_build_has_never_heard_of_reaches_the_reader():
    """Off an envelope some other build wrote. Its own name is a worse
    sentence than its text and a better one than nothing — the reader
    learns that something was said and that this build cannot say it."""
    said = gaps.describe({"sentence": "a_statement_from_the_future"})
    assert "a_statement_from_the_future" in said


def test_a_statement_round_trips_through_the_envelope():
    """Written, serialized, read back. The occasion has to survive both
    halves — a statement whose facts are dropped on the way out renders
    its holes' names to the reader."""
    one = gaps.sentence(gaps.Sentence.THE_EDGE_WAS_LEARNED_BY_DISCOVERY,
                        edge="a->b", algorithm="pc")
    back = gaps.sentence_entry(gaps.sentence_fields(one))
    assert back is not None
    assert back.sentence is one.sentence and back.said == one.said
    assert gaps.describe(back) == gaps.describe(one)


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_language_is_the_reader_s_and_not_the_builder_s(lang):
    """The whole point of the cut. The same gap, asked twice, answers in
    two languages — which a paragraph on the envelope cannot do."""
    # A statement with no holes, so the comparison is against the text
    # rather than against an assembly of it.
    one = gaps.Sentence.TIAN_FOUND_A_HEDGE
    said = gaps.described(
        data_gap_to_dict(_gap(describes=(gaps.sentence(one),))), lang)
    assert said == language.fill(gaps.DESCRIBES[str(one)], lang)


# --- the one line the reader is led with -------------------------------------


def test_the_summary_is_the_first_gap_s_own_paragraph():
    """Why it left the envelope. Its head was never anything but this, and
    a rendering of a rendering is what kept the description a string."""
    filed = [data_gap_to_dict(_gap()),
             data_gap_to_dict(_gap(kind=GapKind.
                                   COLLIDER_CONDITIONING_OPENS_BACKDOOR))]
    assert gaps.summary(filed) == gaps.described(filed[0])


def test_a_second_blocking_gap_is_counted_and_not_described():
    """The one thing the line adds to the paragraph it leads with: that
    the reader is looking at the first of several, which the paragraph
    cannot say about itself."""
    one = [data_gap_to_dict(_gap())]
    # A species the count actually counts: what makes this second gap
    # blocking is what it IS, and the fixture that used to type the word
    # was filing a collider gap — which is important, not blocking.
    two = one + [data_gap_to_dict(_gap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET))]
    assert gaps.summary(one) == gaps.described(one[0])
    assert gaps.summary(two).startswith(gaps.described(one[0]))
    assert gaps.summary(two) != gaps.summary(one)
    assert gaps.described(two[1]) not in gaps.summary(two)


def test_the_frame_around_it_is_what_the_answer_has():
    """Leading with the top gap says "no answer" on a query that has an
    interval in hand, so the tier frames the line rather than following
    it."""
    filed = [data_gap_to_dict(_gap())]
    assert gaps.summary(filed, "interval").endswith(gaps.described(filed[0]))
    assert gaps.summary(filed, "interval") != gaps.summary(filed, "none")
    assert gaps.summary(filed, "point") == gaps.described(filed[0])


def test_no_gaps_is_no_line():
    """The counterexample. A clean bill of health has nothing to lead
    with, and inventing a line for it would say something no gap said."""
    assert gaps.summary([]) == ""
    assert gaps.summary(None) == ""


# --- what the envelope carries -----------------------------------------------


def test_the_gap_carries_the_statements_and_not_the_paragraph():
    """The dataclass. ``description`` is gone from it, and the list is
    required rather than defaulted — a gap that says nothing about itself
    is a gap the reader is shown an empty space for, and it has to be a
    decision somebody made at the site."""
    names = {field.name for field in fields(DataGap)}
    assert "description" not in names
    assert "describes" in names
    with pytest.raises(TypeError):
        DataGap(                                  # type: ignore[call-arg]
            kind=GapKind.MISSING_DISTRIBUTION,
            provenance=(),
        )


def test_the_report_does_not_carry_the_line_it_can_derive():
    """(324), in the one place it cost a rendering in the kernel."""
    assert "summary" not in {field.name for field in fields(DataGapReport)}


def test_the_envelope_declares_the_statement_by_one_reference():
    """One declaration of the shape, shared with the two channels that
    already carry an occasion: a second spelling of ``said`` is a second
    thing to keep equal."""
    schema = reader_words._document("query_result.schema.json")
    gap = schema["$defs"]["dataGap"]
    assert "description" not in gap["properties"]
    assert gap["properties"]["describes"]["items"] == {
        "$ref": "#/$defs/gapSentence"}
    assert "describes" in gap["required"]
    entry = schema["$defs"]["gapSentence"]["properties"]
    route = schema["$defs"]["gapRoute"]["properties"]
    assert entry["said"] == route["said"] and entry["words"] == route["words"]
    assert set(schema["$defs"]["sentence"]["enum"]) == set(gaps.DESCRIBES)
    assert "summary" not in schema["$defs"]["dataGapReport"]["properties"]


def test_the_browser_is_handed_the_table_and_not_the_paragraph():
    """It assembles the paragraph where it knows the reader, exactly as it
    does a route's and a shortfall's."""
    generated = web_source.read(web_source.GENERATED)
    assert set(web_source.words_map("GAP_DESCRIBES", generated)) == set(
        gaps.DESCRIBES)
    declared = web_source.read(web_source.TYPES)
    assert "describes: GapSentence[]" in declared
    assert "description" not in web_source.interface_body("DataGap", declared)
    assert "summary" not in web_source.interface_body(
        "DataGapReport", declared)


# --- #395 seventh cut: the hole that held another sentence -------------------
#
# Five of these statements say that something failed and name a shortfall as
# the why. A shortfall IS a statement, and what went in the hole was that
# statement rendered — because the table its sentences come from had no name
# on an envelope, so nothing but this module could have resolved one.
#
# The parameter that rendering needed is the finding: a reader's language
# reached thirty-five signatures of the gap report for those five holes, and
# no caller ever passed one, so every one of them said DEFAULT whoever was
# reading.


def test_a_shortfall_in_a_hole_travels_as_a_statement():
    """Which sentence and this occasion's facts, not the sentence."""
    item = gaps.missing(
        kind=gaps.MissingKind.STRUCTURE, name="x",
        priority=gaps.Priority.HIGH, need=gaps.Need.ATOM_NOT_IN_GRAPH,
        part=gaps.QueryPart.QUERY, atom="x")
    one = gaps.shortfall(item)
    assert isinstance(one, language.Statement)
    assert one["vocabulary"] == gaps.NEEDED
    assert one["token"] == "atom_not_in_graph"
    # And its own hole holds a word, which is this three levels deep: a gap's
    # sentence, the shortfall in its hole, the query part in that one's.
    assert one["words"]["part"]["vocabulary"] == "query_part"
    for lang in sorted(language.written()):
        said = language.spoke(one, lang)
        assert said and one["token"] not in said, (lang, said)


def test_an_item_with_no_species_hands_over_the_name_it_was_filed_under():
    """A hole holds a value or a word, and both are what this can be.

    The name is the caller's own and reads the same to every reader, so it
    goes back as itself rather than as a statement with nothing to say.
    """
    assert gaps.shortfall({"target": "parameter:p_y"}) == "parameter:p_y"


def test_the_gap_report_is_never_handed_a_reader():
    """The module's own claim, and the one this cut turned true.

    What this module writes is statements — which sentence plus this
    occasion's facts — so there is nothing in it to say in one language
    rather than another. A ``lang`` argument anywhere here means some
    producer went back to rendering, which is the thing that cannot be
    seen by reading the envelope afterwards: it comes out in the reader's
    language either way, as long as there is only one reader.
    """
    tree = ast.parse((ROOT / "themis/output/data_gap_report.py").read_text(
        encoding="utf-8"))
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # The denominator, so a walk that found nothing does not read as a
    # module that hands nobody a language.
    assert len(functions) > 60, len(functions)
    handed = sorted(
        node.name for node in functions
        if any(a.arg == "lang"
               for a in [*node.args.args, *node.args.kwonlyargs]))
    assert handed == [], handed


def test_no_producer_renders_a_shortfall_on_its_way_into_a_hole():
    """The shape this replaced, in the two modules that build a statement."""
    reached = 0
    for path in BUILDERS:
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "gaps.said(" not in source, path
        reached += source.count("gaps.shortfall(")
    assert reached == 5, reached
