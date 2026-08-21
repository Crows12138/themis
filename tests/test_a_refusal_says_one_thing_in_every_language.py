"""A species' sentence has one author, and that author writes every language.

``estimator_failure.reason`` is the field a refusal reaches a reader
through, and until now it was written at the raise site: 171 sites across
25 modules, each composing its own sentence with an f-string. Two things
follow from that arrangement and both were measured on it. The sentence
was not the species' — seven sites raised ``TREATMENT_NOT_BINARY`` and
wrote six different sentences for it. And the sentence could not be
translated at all — an f-string interpolates where it is written, so 149
of the 171 were values rather than templates, and the six that had been
written in Chinese stayed Chinese for an English reader while the other
157 stayed English for a Chinese one.

:data:`themis.refusals.SAYS` is the other arrangement: the sentence lives
beside the species, in every language, with named slots the occasion fills
from ``details``. These gates are what keep the two from becoming three.

What they do not reach: whether a sentence is any GOOD, whether its two
languages say the same thing, and whether the species is the right one for
the branch that raised it. The first two are a reader's judgement and the
third is the estimator's.
"""
from __future__ import annotations

import ast
import collections
import pathlib
import string

import pytest

from themis import language, refusals

ROOT = pathlib.Path(__file__).resolve().parent.parent


#: Raise sites that still compose their own sentence.
#:
#: Only ever smaller. It is not zero because the species below it disagree
#: with themselves — seven sites, six sentences — and reconciling a species
#: is a reading of what its estimators meant, not a mechanical move. What
#: the number does is keep the two mechanisms from settling in: a new raise
#: site that writes its own sentence has to come here and say so.
STILL_AUTHORED = 105


def _slots(template: str) -> frozenset[str]:
    """The named holes in a sentence."""
    return frozenset(
        name for _lit, name, _spec, _conv in string.Formatter().parse(template)
        if name
    )


def _raise_sites() -> dict[str, list[tuple[str, int, bool, frozenset[str]]]]:
    """Every ``EstimatorFailure(...)`` in the package, by species name.

    Read out of the source rather than out of a run: the branch that raises
    a refusal is the branch no happy path takes, so a scan of what executed
    would be a scan of the refusals nobody hits.
    """
    found: dict[str, list] = collections.defaultdict(list)
    for path in sorted((ROOT / "themis").rglob("*.py")):
        module = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if name != "EstimatorFailure":
                continue
            species = node.args[0]
            key = (species.attr if isinstance(species, ast.Attribute)
                   else "<computed>")
            found[key].append((
                module, node.lineno, len(node.args) >= 2,
                frozenset(k.arg for k in node.keywords if k.arg),
            ))
    return found


def test_a_sentence_exists_in_every_language_this_build_writes():
    """Not "in Chinese and English" — in whatever :func:`written` counts.

    A gate naming the languages would be a third place they are declared,
    and it would stop meaning anything on the day a fourth is added: it
    would keep passing while the new language had no sentence at all.
    """
    for name, words in refusals.SAYS.items():
        assert set(words) == set(language.written()), name


def test_the_two_languages_of_one_sentence_fill_the_same_holes():
    """The facts a sentence turns on cannot depend on who is reading it.

    Where they differ, one language is quietly saying less — and it is the
    kind of difference nothing else would catch, because each language
    renders fine on its own.
    """
    for name, words in refusals.SAYS.items():
        holes = {lang: _slots(text) for lang, text in words.items()}
        assert len(set(holes.values())) == 1, (name, holes)


@pytest.mark.parametrize("name", sorted(refusals.SAYS))
def test_a_sentence_renders_in_every_language(name):
    """With the slots filled by nothing in particular, which is the point:
    what is being checked is that the template is a template."""
    filling = {hole: 0 for hole in _slots(refusals.SAYS[name]["zh"])}
    for lang in sorted(language.written()):
        text = refusals.sentence(name, filling, lang)
        assert text and "{" not in text, (name, lang, text)


def test_every_delegating_raise_site_supplies_the_slots_its_species_names():
    """A raise site that gives no message is naming the slots instead.

    Missing one raises ``KeyError`` from inside ``str.format`` — at the
    moment the refusal is being written down, which is the moment least
    able to absorb a second failure. Nothing runs these branches, so the
    check is here.
    """
    sites = _raise_sites()
    for name, template in refusals.SAYS.items():
        holes = _slots(template["zh"])
        for module, line, authored, given in sites[name.upper()]:
            if authored:
                continue
            assert holes <= given, (f"{module}:{line}", name,
                                    sorted(holes - given))


def test_no_species_is_raised_both_ways():
    """The two mechanisms coexist while :data:`STILL_AUTHORED` is nonzero,
    and a species in both is where they would disagree — the same refusal
    reaching two readers as two different sentences, which is the state
    this replaced."""
    both = [
        name for name, sites in _raise_sites().items()
        if {authored for _m, _l, authored, _k in sites} == {True, False}
    ]
    assert both == []


def test_the_raise_sites_that_still_write_their_own_sentence_are_counted():
    sites = _raise_sites()
    authored = sum(1 for got in sites.values()
                   for _m, _l, is_authored, _k in got if is_authored)
    assert authored == STILL_AUTHORED, (
        f"{authored} raise sites author their own sentence, not "
        f"{STILL_AUTHORED}. Lower the number when one moves into "
        f"themis.refusals.SAYS; raise it only with a reason."
    )


def test_a_species_with_no_sentence_and_no_message_is_refused():
    """The counterexample for the mechanism: silence is not a sentence."""
    assert "overlap_insufficient" not in refusals.SAYS
    with pytest.raises(ValueError, match="has no sentence"):
        refusals.EstimatorFailure(refusals.Refusal.OVERLAP_INSUFFICIENT)


def test_a_slot_the_raise_site_forgot_is_refused():
    """The counterexample for the gate above: a hole with nothing in it is
    caught by ``format`` rather than rendered as the word ``{column}``."""
    with pytest.raises(KeyError):
        refusals.EstimatorFailure(refusals.Refusal.SAMPLE_TOO_SMALL, n=40)


def test_the_occasion_reaches_the_envelope_as_the_envelope_can_hold_it():
    """``details`` is on an envelope path, so it answers to the same rule
    the rest of that path does."""
    np = pytest.importorskip("numpy")
    exc = refusals.EstimatorFailure(
        refusals.Refusal.SAMPLE_TOO_SMALL,
        n=np.int64(40), minimum=np.int64(100),
        levels=[np.str_("a"), np.float64(1.5)],
    )
    assert exc.details == {"n": 40, "minimum": 100, "levels": ["a", 1.5]}
    assert all(type(v) is int for v in (exc.details["n"],
                                        exc.details["minimum"]))


def test_a_structure_the_envelope_can_hold_survives_as_a_structure():
    """The counterexample the suite found: a stratum is ``{column: level}``,
    which JSON writes down and a scalar coercion does not recognise. Left
    to the fallback it arrives as the string ``"{'w': True}"`` — a reader
    can still read it and nothing downstream can index it."""
    np = pytest.importorskip("numpy")
    exc = refusals.EstimatorFailure(
        refusals.Refusal.OVERLAP_INSUFFICIENT, "a stratum was empty",
        stratum={"w": np.True_}, cells=[{"a": np.int64(0)}],
    )
    assert exc.details == {"stratum": {"w": True}, "cells": [{"a": 0}]}
