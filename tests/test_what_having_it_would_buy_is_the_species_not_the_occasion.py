"""What filling a gap would buy is a fact about the species (#441).

``if_provided`` was a field: a finished sentence, in whichever language
whoever built the report happened to pass, written at 21 construction
sites from 17 templates. Measured against the kinds, it was never an
occasion's fact — every species either always carried one or never did,
and no two producers of a species disagreed about theirs. It was a table
the kernel already had, told one row at a time and then frozen into one
language on the way out.

So the table is stated as one (:data:`themis.gaps.IF_PROVIDED`), the gap
carries only what goes in its holes (``said`` / ``words``, the same two
halves a route and a shortfall carry), and each reader-facing surface
assembles the sentence where the reader's language is known.

Three things follow, and this module holds all three:

**The table must be total, and half a table reads like a whole one.** A
species with no row is indistinguishable from a species somebody stopped
short of answering for, so "nothing supplied changes this" is written
down too (:data:`themis.gaps.NOTHING_FILLS`) and the two must partition
the kinds.

**A hole is a promise the producer has to keep.** A sentence with
``{collider}`` in it is a sentence that cannot be assembled without one,
so the species that have holes and the sites that supply them are held
equal — statically, by reading every ``DataGap(...)`` in the kernel.

**Both surfaces must read the same template language.** The kernel's
renderer is ``str.format``'s and the browser's is a regex; a doubled
brace is a brace in the first and was a hole in the second, so three
sentences already on the envelope reached a browser reader with braces
the report does not show them. What is pinned is agreement over every
string the kernel hands the browser, with the browser's tokenizer read
out of its own source.
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
    BLOCKS_TURN_ON,
    SEVERITY_TURNS_ON,
    DataGap,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapSeverity,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The species whose sentence has a hole, and what goes in it. Written out
#: rather than derived, because the point of the pairing below is that two
#: independent things — a table of sentences and a set of construction
#: sites — say the same thing, and deriving one from the other would make
#: that agreement true by construction.
HOLED = {
    "collider_conditioning_opens_backdoor": {"collider"},
    "selection_on_collider_opens_path": {"collider", "value"},
    "ill_defined_intervention_versions": {"intervention"},
    "unattempted_layer_due_to_dispatch_conflict": {"won", "lost"},
    "missing_iv_candidate": {"treatment", "outcome"},
}

#: Where a gap is built. Both modules, because the second author is the
#: reason this is a gate: ``dispatch.py`` wrote its own sentence for a
#: species ``data_gap_report.py`` also produces.
BUILDERS = ("themis/output/data_gap_report.py",
            "themis/estimation/dispatch.py")

#: How many ``DataGap(...)`` calls those two hold, and how many of them
#: name their species with a literal. The one that does not is the
#: hydrator, which reads the kind off the envelope it is decoding.
BUILT = 47
NAMED = 46


def _a_statement_it_makes(kind: GapKind):
    """One statement this species makes about itself.

    The same reasoning as the severity and the blocks in :func:`_gap`:
    which statements a species makes is the species', and one literal
    stood here for all of them — a hedge Tian found, on every species this
    file walks. Lowest name first, so the fixture does not move when the
    table grows.
    """
    said = sorted(gaps.says_of(kind), key=str)
    if not said:
        raise AssertionError(
            f"{kind.value} declares no statement of its own; this fixture "
            f"cannot build a gap of a species nothing builds")
    return said[0]


def _gap(kind: GapKind, **kw) -> DataGap:
    """A gap of this species, saying only what the species leaves open.

    It used to type a severity and a blocks for every kind. Both belong to
    the species, so a fixture stating them was making up a value it does
    not own — and the two it happened to pick were wrong for most species
    it was called with. What is passed now is what the declaration says is
    an occasion's; everything else the species fills, the statement it
    makes included.
    """
    fields_ = {
        "kind": kind,
        "describes": (gaps.sentence(_a_statement_it_makes(kind)),),
        "provenance": (GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK,
                                        ref_id="x"),),
    }
    if kind in SEVERITY_TURNS_ON:
        fields_["severity"] = GapSeverity.BLOCKING
    if kind in BLOCKS_TURN_ON:
        fields_["blocks"] = GapBlocks.POINT_ESTIMATE
    fields_.update(kw)
    return DataGap(**fields_)      # type: ignore[arg-type]


def _occasion_for(species: str) -> dict:
    """An occasion that fills whatever holes this species' sentence has."""
    return gaps.occasion(**{hole: hole.upper()
                            for hole in HOLED.get(species, ())})


# --- the table is total ------------------------------------------------------


def test_every_species_says_either_what_it_buys_or_that_nothing_does():
    """The partition. A species in neither is one nobody has answered the
    question for, and it is only visible because "nothing does" had to be
    written down rather than left as an absent row."""
    kinds = {str(kind) for kind in GapKind}
    assert set(gaps.IF_PROVIDED) | set(gaps.NOTHING_FILLS) == kinds
    assert not set(gaps.IF_PROVIDED) & set(gaps.NOTHING_FILLS)


def test_neither_table_names_something_that_is_not_a_species():
    """The other direction: a key no kind matches is a row nothing reaches,
    which is how a renamed member leaves its sentence behind."""
    kinds = {str(kind) for kind in GapKind}
    assert set(gaps.IF_PROVIDED) <= kinds
    assert set(gaps.NOTHING_FILLS) <= kinds


@pytest.mark.parametrize("species", sorted(gaps.IF_PROVIDED))
def test_the_sentence_exists_in_every_language_this_build_writes(species):
    """Not in every language it is ANSWERED in — a language being written
    is held to the same completeness, which is what makes it safe to
    offer on the day it is."""
    said = gaps.IF_PROVIDED[species]
    assert set(said) == language.written(), species
    assert all(text.strip() for text in said.values()), species


@pytest.mark.parametrize("species", sorted(gaps.NOTHING_FILLS))
def test_why_nothing_fills_it_is_a_note_and_not_a_reader_s_sentence(species):
    """One string, not a ``Words``. The reader's fact is that there is no
    such line, which they learn by not being told one; this is for whoever
    adds the next species and has to decide which table it belongs in."""
    assert isinstance(gaps.NOTHING_FILLS[species], str)
    assert gaps.NOTHING_FILLS[species].strip()


# --- a hole is a promise ------------------------------------------------------


@pytest.mark.parametrize("species", sorted(gaps.IF_PROVIDED))
def test_the_languages_agree_about_where_the_holes_are(species):
    """A hole one language has and another does not is a fact that reaches
    one reader and not the other. The union is what gets filled, so the
    disagreement is silent in the language that has fewer."""
    said = gaps.IF_PROVIDED[species]
    per = {lang: {name for _, name, _, _
                  in string.Formatter().parse(text) if name}
           for lang, text in said.items()}
    assert len(set(map(frozenset, per.values()))) == 1, per


def test_the_species_with_holes_are_the_ones_written_down():
    """The denominator for everything below."""
    assert {species: holes
            for species in gaps.IF_PROVIDED
            for holes in [language.holes(gaps.IF_PROVIDED[species])]
            if holes} == HOLED


def _built(path: str) -> list[tuple[int, str | None, list[str] | None]]:
    """Every ``DataGap(...)`` in one module: its line, the species it names
    if it names one literally, and the occasion it splats in if it does."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "DataGap"):
            continue
        species, occasion = None, None
        for keyword in node.keywords:
            if keyword.arg == "kind":
                named = re.fullmatch(r"GapKind\.(\w+)",
                                     ast.unparse(keyword.value))
                if named:
                    species = str(getattr(GapKind, named.group(1)))
            elif (keyword.arg is None
                  and isinstance(keyword.value, ast.Call)
                  and ast.unparse(keyword.value.func).endswith("occasion")):
                occasion = sorted(k.arg for k in keyword.value.keywords
                                  if k.arg)
        out.append((node.lineno, species, occasion))
    return out


def test_the_scan_over_the_builders_reaches_what_it_claims_to():
    """A static scan that quietly matched nothing would pass every pairing
    below, so its own reach is stated first."""
    found = [site for path in BUILDERS for site in _built(path)]
    assert len(found) == BUILT
    assert len([s for s in found if s[1] is not None]) == NAMED


@pytest.mark.parametrize("path", BUILDERS)
def test_a_site_supplies_exactly_the_holes_its_species_has(path):
    """The pairing. A producer that supplies nothing for a species whose
    sentence has a hole is a reader shown the hole's own name; one that
    supplies a fact for a species whose sentence has no hole is a fact
    that reaches nobody."""
    for line, species, occasion in _built(path):
        if species is None:
            continue
        wanted = HOLED.get(species, set())
        assert set(occasion or ()) == wanted, (path, line, species)


# --- the sentence is assembled where the reader is ----------------------------


@pytest.mark.parametrize("species", sorted(gaps.IF_PROVIDED))
@pytest.mark.parametrize("lang", sorted(language.written()))
def test_a_species_with_a_row_assembles_a_full_sentence(species, lang):
    """Filled from the occasion, with nothing left standing as its own
    name — which is what an unfilled hole renders as."""
    said = gaps.if_provided(
        _gap(GapKind(species), **_occasion_for(species)), lang)
    assert said.strip()
    for hole in HOLED.get(species, ()):
        assert f"`{hole}`" not in said, (species, hole)
        assert hole.upper() in said, (species, hole)


@pytest.mark.parametrize("species", sorted(gaps.NOTHING_FILLS))
def test_a_species_nothing_fills_says_nothing_rather_than_something(species):
    """The counterexample the table exists for. Empty is the ANSWER here:
    inventing a line would promise the reader that something they could go
    and get changes this gap.

    Asked of the ENVELOPE rather than of a built gap. What
    :func:`~themis.gaps.if_provided` reads is the kind, which the envelope
    carries either way — and one of these species is one nothing in this
    kernel builds (``GAP_KINDS_WITH_NO_PRODUCER``), so a constructed gap
    cannot be had for it at all. The test below asks the same question of
    a species from another build entirely, and for the same reason.
    """
    assert gaps.if_provided({"kind": species}) == ""


def test_a_species_this_build_has_never_heard_of_says_nothing_either():
    """Reachable from an envelope some other build wrote. The reader's
    fact is the same as above, so the answer is."""
    assert gaps.if_provided({"kind": "a_species_from_the_future"}) == ""


def test_the_tail_is_the_same_predicate_the_sentence_is():
    """A next-steps line is offered where there is something to go and
    get. Both conditions read off the gap: not informational, and a
    species the table answers for."""
    entries = [
        {"kind": str(GapKind.MISSING_DISTRIBUTION),
         "severity": str(GapSeverity.BLOCKING)},
        {"kind": str(GapKind.PROPENSITY_OVERLAP_VIOLATION),
         "severity": str(GapSeverity.BLOCKING)},
    ]
    assert gaps.next_steps(entries, "en") == [
        "supply the distribution this is short of"]


# --- what the envelope carries ------------------------------------------------


def test_the_gap_carries_the_occasion_and_not_the_sentence():
    """The dataclass. ``if_provided`` is gone from it, and the two halves
    an occasion travels in are there in its place — the same pair a route
    and a shortfall carry, one channel over."""
    names = {field.name for field in fields(DataGap)}
    assert "if_provided" not in names
    assert {"said", "words"} <= names


def test_the_two_halves_are_written_only_where_there_is_something():
    """"Nothing here" has one spelling, decided at the door rather than at
    each writer — the same rule the other optional fields follow."""
    bare = data_gap_to_dict(_gap(GapKind.MISSING_DISTRIBUTION))
    assert "said" not in bare and "words" not in bare
    assert "if_provided" not in bare

    carried = data_gap_to_dict(_gap(
        GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR,
        **_occasion_for("collider_conditioning_opens_backdoor")))
    assert carried["said"] == {"collider": "COLLIDER"}
    assert "words" not in carried


def test_the_envelope_declares_the_occasion_by_the_same_reference():
    """One declaration of each half, shared with the channel that already
    carried them: a second spelling of ``said`` is a second thing to keep
    equal."""
    schema = reader_words._document("query_result.schema.json")
    gap = schema["$defs"]["dataGap"]["properties"]
    assert "if_provided" not in gap
    assert gap["said"] == {"$ref": "#/$defs/said"}
    assert gap["words"] == {"$ref": "#/$defs/words"}
    route = schema["$defs"]["gapRoute"]["properties"]
    assert gap["said"] == route["said"] and gap["words"] == route["words"]


def test_the_browser_is_handed_the_table_and_not_the_sentence():
    """It assembles this one where it knows the reader, exactly as it does
    a route's and a shortfall's."""
    generated = web_source.read(web_source.GENERATED)
    assert set(web_source.words_map("GAP_IF_PROVIDED", generated)) == set(
        gaps.IF_PROVIDED)
    assert "if_provided" not in web_source.read(web_source.TYPES)


# --- both surfaces read the same template language ----------------------------


def _tokenizer() -> re.Pattern[str]:
    """The browser's own tokenizer, read out of the browser's source.

    Not a copy of it: a copy would be a third statement of the rule and
    would agree with itself. What this cannot see is a renderer that stops
    using it — which is why the pin below counts the tokenizers in the
    tree.
    """
    source = web_source.read(web_source.SRC / "lib" / "language.ts")
    found = re.search(r"^const TOKEN = /(.+)/g$", source, re.M)
    assert found, "language.ts declares no TOKEN"
    return re.compile(found.group(1))


def test_the_browser_has_exactly_one_tokenizer():
    """Two would be two answers to "what is a hole", and the second one is
    how the surface that COLLECTS the holes came to disagree with the one
    that fills them."""
    written = "\n".join(
        path.read_text(encoding="utf-8")
        for kind in ("*.ts", "*.tsx")
        for path in sorted(web_source.SRC.rglob(kind))
    )
    assert len(re.findall(r"/(?:[^/\n]*\\\{)[^/\n]*/g", written)) == 1
    assert "text.replace(TOKEN," in web_source.read(
        web_source.SRC / "lib" / "language.ts")


def _as_the_browser_renders(text: str, slots: dict) -> str:
    """The substitution the browser's ``fill`` performs, driven by its own
    tokenizer: a doubled brace collapses to one, a named hole takes its
    slot."""
    return _tokenizer().sub(
        lambda m: m.group(0)[0] if m.group(1) is None else slots[m.group(1)],
        text,
    )


@pytest.mark.parametrize("table", sorted(reader_words.tables()))
def test_the_two_renderers_agree_on_every_string_the_browser_is_handed(table):
    """Over the whole corpus, not over the templates one channel happens
    to use. Three sentences here carry a brace a reader is meant to see —
    a Python call with a dict in it, a counterfactual's subscript — and
    they are written the way ``str.format`` escapes one; a renderer that
    read the escape as a hole showed those readers a doubled brace and a
    hole's name where the report shows them the call.
    """
    for member, said in reader_words.tables()[table].items():
        for lang, text in said.items():
            slots = {name: f"<{name}>" for _, name, _, _
                     in string.Formatter().parse(text) if name}
            assert text.format(**slots) == _as_the_browser_renders(
                text, slots), (table, member, lang)
