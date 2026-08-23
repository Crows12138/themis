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

A refusal reaches the envelope through TWO doors — raised as an
``EstimatorFailure`` (176 sites) or written straight onto the result by
``refusals.block`` (14) — and these gates watched only the first. Both of
the species that ended up with two voices got there through the unwatched
one, and one of them was written while the gates were green. A gate whose
denominator is one door measures the door, not the rule.

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


#: Filing sites that still compose their own sentence.
#:
#: Only ever smaller. It is not zero because the species below it disagree
#: with themselves — seven sites, six sentences — and reconciling a species
#: is a reading of what its estimators meant, not a mechanical move. What
#: the number does is keep the two mechanisms from settling in: a new site
#: that writes its own sentence has to come here and say so.
#:
#: IT WENT UP ONCE, AND THAT IS WHAT IT MEASURES. This counter finds a site
#: by looking for a call to one of :data:`DOORS`, so the seven refusal blocks
#: that dispatch assembled as dict literals were not sites it could see —
#: every one of them wrote its own ``reason``, so the true figure was 116
#: while this said 109. Closing that door (there are none left, and
#: ``test_a_refusal_reaches_the_envelope_one_way`` now says so absolutely)
#: brought them into view, and five of the seven handed their sentence to
#: their species on the way in: 116 → 111, measured the same way at both
#: ends. A counter whose denominator is "the sites a door can see" reads as
#: a count of authors and is a count of authors THROUGH THAT DOOR.
#:
#: 111 → 99 when a slot learned to carry a word. Twelve of these sites were
#: one fact plus a name — WHICH matrix has no inverse, WHICH channel was
#: mismeasured, WHICH fit has nothing left to explain — and a channel that
#: carried only numbers left each of them to write the name into prose of
#: its own. They delegate now.
#:
#: 65 → 39 when the support boundary's two species were given sentences.
#: They already said the right fact — a cell with no rows, a column with no
#: variation — and had no entry here at all, so twenty-six sites wrote the
#: fact again in order to get the occasion's cell or column into it (#405).
STILL_AUTHORED = 39

#: Sites that file a species they were handed rather than one they name.
#:
#: ``EstimatorFailure(exc.species, ...)`` and ``block(failure_type=exc.
#: failure_type, ...)`` carry a refusal another site already decided, so
#: which species they file cannot be read here. They are counted rather
#: than judged: whether such a site RELAYS the first author's sentence or
#: composes a second one is a question the count exists to keep visible.
FORWARDED = 5

#: Species whose sites do not agree on who writes the sentence.
#:
#: One refusal reaching two readers as two sentences is the state SAYS
#: replaced, so this is a list of exceptions rather than a tolerance. Its
#: one entry: the row at ``dispatch._try_outcome_error_declaration`` has a
#: true thing to add that the species does not own — the point estimate
#: stands, and only the precision cost is missing — and there is no slot
#: for a filing row's own note on top of the species' sentence. Making one
#: is the fix; borrowing the species' voice to say it is not.
STILL_TWO_AUTHORS = {"NO_IDENTIFYING_DESIGN"}

#: Sentences in :data:`SAYS` that no site can currently produce.
#:
#: ``no_first_stage``'s six sites all author. Five of them are one fact —
#: the instrument does not move the treatment — witnessed by five different
#: statistics, and two of those five are inside the moments solvers, whose
#: record is a NUMERIC sufficient statistic the verifier recomputes from.
#: Putting column names in it would be a second copy of names the envelope
#: already carries elsewhere; leaving them out costs the other three sites
#: the names their sentences have today. That is a contract question, and
#: until it is answered the sentence stays here where it can be seen.
#:
#: ``rows_outside_the_strata``'s one site raises ``iv._NotStratifiable``,
#: an ``EstimatorFailure`` subclass, and the scan above reads the CALL by
#: name — so this entry is the subclass blind spot rather than a sentence
#: nobody can reach. Widening the scan to subclasses is the fix; guessing
#: which local names are species is not.
STILL_UNSPOKEN = {"no_first_stage", "rows_outside_the_strata"}

#: The two doors a refusal reaches the envelope through.
DOORS = {"EstimatorFailure", "IdentificationFailure", "block"}

#: The keyword or position at which a site takes the sentence into its own
#: hands. ``block`` calls the field ``reason`` and the exception ``message``.
AUTHORS = {"message", "reason"}


def _slots(template: str) -> frozenset[str]:
    """The named holes in a sentence."""
    return frozenset(
        name for _lit, name, _spec, _conv in string.Formatter().parse(template)
        if name
    )


def _species_in(node: ast.AST) -> list[str]:
    """Every species named in an expression — a conditional names two."""
    return [n.attr for n in ast.walk(node)
            if isinstance(n, ast.Attribute)
            and getattr(n.value, "id", None) == "Refusal"]


def _bound_to_a_species(tree: ast.AST) -> dict[str, list[str]]:
    """Locals holding a species, for the sites that choose one before they
    file it. Reading only the call would see a bare name and no species."""
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and (species := _species_in(node.value)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).extend(species)
    return found


def _filing_sites(where: pathlib.Path | None = None
                  ) -> tuple[dict[str, list], list[tuple[str, int, bool]]]:
    """Every site that files a refusal, by species, and the forwarders.

    Read out of the source rather than out of a run: the branch that files
    a refusal is the branch no happy path takes, so a scan of what executed
    would be a scan of the refusals nobody hits.
    """
    where = where or (ROOT / "themis")
    found: dict[str, list] = collections.defaultdict(list)
    forwarded: list[tuple[str, int, bool]] = []
    for path in sorted(where.rglob("*.py")):
        module = path.relative_to(where.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound = _bound_to_a_species(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            door = (node.func.id if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", ""))
            if door not in DOORS:
                continue
            named = next((kw.value for kw in node.keywords
                          if kw.arg == "failure_type"), None)
            first = named if named is not None else (
                node.args[0] if node.args else None)
            if first is None:
                continue
            species = _species_in(first)
            if not species and isinstance(first, ast.Name):
                species = bound.get(first.id, [])
            authored = (len(node.args) >= 2
                        or any(kw.arg in AUTHORS for kw in node.keywords))
            if not species:
                forwarded.append((module, node.lineno, authored))
                continue
            given = frozenset(k.arg for k in node.keywords if k.arg)
            if (details := next((kw.value for kw in node.keywords
                                 if kw.arg == "details"), None)) is not None:
                given |= frozenset(
                    k.value for k in getattr(details, "keys", [])
                    if isinstance(k, ast.Constant) and isinstance(k.value, str))
            for name in species:
                found[name].append((module, node.lineno, authored, given))
    return found, forwarded


def _raise_sites() -> dict[str, list]:
    return _filing_sites()[0]


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


#: Keywords the DOOR takes, which are not the occasion's facts.
PLUMBING = frozenset({"failure_type", "estimator", "details", "reason",
                      "message", "recorded", "remedies"})


def test_every_delegating_raise_site_names_its_species_slots_and_only_those():
    """A raise site that gives no message is naming the slots instead.

    Both directions, and the second one is the half that was missing. A hole
    with nothing in it raises ``KeyError`` from inside ``str.format`` — at
    the moment the refusal is being written down, which is the moment least
    able to absorb a second failure — so that direction announces itself.
    A KEYWORD WITH NO HOLE is dropped without a word, and thirty-three raise
    sites were doing it (#430): the exception's own text, the size each of
    three producers happened to measure, which channel a missing column came
    through. Some of those were deliberate and some were not, and nothing
    could tell them apart, because ``details`` named a container rather than
    an audience.

    It has two names now. ``details`` is what the sentence says, checked here
    as an equality; ``recorded`` is what it does not, and a fact moving
    between them is a decision someone makes in the open.
    """
    sites = _raise_sites()
    for name, template in refusals.SAYS.items():
        holes = _slots(template["zh"])
        for module, line, authored, given in sites[name.upper()]:
            if authored:
                continue
            named = frozenset(given) - PLUMBING
            assert holes <= named, (f"{module}:{line}", name,
                                    "unfilled", sorted(holes - named))
            assert named <= holes, (
                f"{module}:{line}", name, "named but never said",
                sorted(named - holes),
                "put it in recorded= if the sentence should not carry it")


def test_no_species_is_filed_both_ways():
    """The two mechanisms coexist while :data:`STILL_AUTHORED` is nonzero,
    and a species in both is where they would disagree — the same refusal
    reaching two readers as two different sentences, which is the state
    this replaced. Both doors, because a species does not care which one
    its sites went through and neither does the reader."""
    both = {
        name for name, sites in _raise_sites().items()
        if {authored for _m, _l, authored, _k in sites} == {True, False}
    }
    assert both == STILL_TWO_AUTHORS, {
        name: [f"{m}:{line} {'authors' if a else 'delegates'}"
               for m, line, a, _k in _raise_sites()[name]]
        for name in both ^ STILL_TWO_AUTHORS
    }


def test_every_sentence_has_a_site_that_can_speak_it():
    """A species' sentence is written for the sites that file it, and a
    species every one of whose sites authors will never reach it.

    Such a sentence is not inert. It is in the reader's table, it passes
    every gate about languages and slots, and nothing renders it — so it
    drifts from the sites that were supposed to converge on it, and the
    drift shows up on the day one of them finally delegates.
    """
    sites = _raise_sites()
    unspoken = {
        name for name in refusals.SAYS
        if not any(not authored
                   for _m, _l, authored, _k in sites[name.upper()])
    }
    assert unspoken == STILL_UNSPOKEN, {
        name: [f"{m}:{line}" for m, line, _a, _k in sites[name.upper()]]
        for name in unspoken ^ STILL_UNSPOKEN
    }


def test_the_filing_sites_that_still_write_their_own_sentence_are_counted():
    sites = _raise_sites()
    authored = sum(1 for got in sites.values()
                   for _m, _l, is_authored, _k in got if is_authored)
    assert authored == STILL_AUTHORED, (
        f"{authored} filing sites author their own sentence, not "
        f"{STILL_AUTHORED}. Lower the number when one moves into "
        f"themis.refusals.SAYS; raise it only with a reason."
    )


def _module(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    (tmp_path / "filed.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_the_check_sees_a_species_going_through_the_second_door(tmp_path):
    """The counterexample the gate was written for: one species, one site
    per door, and only the door that raises used to be looked at."""
    filed, _ = _filing_sites(_module(tmp_path, (
        "raise EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, n=1, minimum=2)\n"
        "result['x'] = block(failure_type=Refusal.SAMPLE_TOO_SMALL,\n"
        "                    reason='a second wording')\n"
    )))
    assert {a for _m, _l, a, _k in filed["SAMPLE_TOO_SMALL"]} == {True, False}


def test_the_check_sees_a_species_chosen_before_it_is_filed(tmp_path):
    """A site may pick its species into a local first. Reading only the
    call would find a bare name, file nothing, and pass."""
    filed, forwarded = _filing_sites(_module(tmp_path, (
        "kind = Refusal.MISSING_COLUMN if absent else Refusal.SAMPLE_TOO_SMALL\n"
        "raise EstimatorFailure(kind, 'a sentence of its own')\n"
    )))
    assert forwarded == []
    assert sorted(filed) == ["MISSING_COLUMN", "SAMPLE_TOO_SMALL"]


def test_the_check_sees_a_sentence_no_site_can_reach(tmp_path):
    """A species every one of whose sites authors leaves its sentence with
    no occasion — which is what the gate above measures."""
    filed, _ = _filing_sites(_module(tmp_path, (
        "raise EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, 'its own words')\n"
    )))
    spoken = [a for _m, _l, a, _k in filed["SAMPLE_TOO_SMALL"] if not a]
    assert spoken == []


def test_the_sites_that_file_a_species_they_were_handed_are_counted():
    """What a forwarder files is decided elsewhere, so no gate above can
    read it. The count is what keeps that blind spot a known size."""
    forwarded = _filing_sites()[1]
    assert len(forwarded) == FORWARDED, [
        f"{m}:{line} {'authors' if a else 'relays'}" for m, line, a in forwarded
    ]


def test_a_species_with_no_sentence_and_no_message_is_refused():
    """The counterexample for the mechanism: silence is not a sentence.

    The species is found rather than named, because naming one makes this
    test a hostage of whichever species gets its sentence next — which it
    twice was. When the list runs dry every species has a sentence, and the
    counterexample has to be built here instead of borrowed from the enum.
    """
    speechless = [s for s in refusals.Refusal if str(s) not in refusals.SAYS]
    assert speechless, (
        "every species now has a sentence — build the counterexample here "
        "rather than borrowing one from the registry"
    )
    with pytest.raises(ValueError, match="has no sentence"):
        refusals.EstimatorFailure(speechless[0])


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


def test_a_fact_the_sentence_does_not_say_survives_as_a_recorded_one():
    """The other half of the occasion, end to end.

    ``str.format`` drops a keyword its template has no hole for, so before
    there was a second name this fact reached the envelope as nothing at all
    — and looked, from outside, exactly like a fact deliberately withheld.
    """
    np = pytest.importorskip("numpy")
    exc = refusals.EstimatorFailure(
        refusals.Refusal.SAMPLE_TOO_SMALL, n=40, minimum=100,
        recorded={"treatment": "t", "rows_seen": np.int64(40)},
    )
    assert exc.details == {"n": 40, "minimum": 100}
    assert exc.recorded == {"treatment": "t", "rows_seen": 40}
    assert type(exc.recorded["rows_seen"]) is int, (
        "recorded is on the same envelope path as details and answers to the "
        "same rule about what JSON can hold")
    assert "treatment" not in str(exc) and "40" in str(exc), (
        "the sentence says what it says; recording a fact does not add it")

    result: dict = {}
    refusals.record(result, estimator="e", exc=exc)
    block = result["estimator_failure"]
    assert block["details"] == {"n": 40, "minimum": 100}
    assert block["recorded"] == {"treatment": "t", "rows_seen": 40}


def test_a_refusal_with_nothing_unsaid_carries_no_recorded_key():
    """The absence has one spelling here too (#371): the key is omitted
    rather than written as an empty object."""
    exc = refusals.EstimatorFailure(
        refusals.Refusal.SAMPLE_TOO_SMALL, n=40, minimum=100)
    result: dict = {}
    refusals.record(result, estimator="e", exc=exc)
    assert "recorded" not in result["estimator_failure"]


def test_the_check_sees_a_site_that_names_a_fact_its_sentence_never_says(tmp_path):
    """The counterexample for the direction that was missing.

    Written against a module on disk rather than by breaking a real raise
    site, and it is worth saying what this one costs to get wrong: the gate's
    first refusal was not to this file, it was to thirty-three raise sites on
    HEAD. A gate whose only red is its author's counterexample has not been
    shown to be about anything.
    """
    filed, _ = _filing_sites(_module(tmp_path, (
        "raise EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, n=1, minimum=2,\n"
        "                       treatment='t')\n"
    )))
    holes = _slots(refusals.SAYS["sample_too_small"]["zh"])
    (_m, _l, authored, given), = filed["SAMPLE_TOO_SMALL"]
    assert not authored
    named = frozenset(given) - PLUMBING
    assert holes <= named, "the slots it does fill are not the question"
    assert named - holes == {"treatment"}

    filed, _ = _filing_sites(_module(tmp_path, (
        "raise EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, n=1, minimum=2,\n"
        "                       recorded={'treatment': 't'})\n"
    )))
    (_m, _l, _a, given), = filed["SAMPLE_TOO_SMALL"]
    assert frozenset(given) - PLUMBING == holes, (
        "the repaired form must pass, or the gate is refusing the fix too")
