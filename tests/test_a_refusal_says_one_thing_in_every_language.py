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
#:
#: 39 → 15 with the measurement-error family, which held the largest
#: remaining concentration for a reason: its arguments are DECLARED rather
#: than read off the data, and a declaration can be wrong in more ways than
#: a column can. The names above those sites were sorted by which argument
#: went wrong and not by what went wrong with it, so four of the sentences
#: written here would have been false at one of the sites filing them.
#:
#: 15 → 0. The last fifteen were the opposite of that family: not one of
#: them is a caller's argument, and every one is a judgement about what
#: this graph, this sample or this solver can reach. What they had in
#: common is that the name above each was written for the FIRST site that
#: met it — so a door that ran three routes and a door that ran one filed
#: the same "not identifiable", and a refusal raised over a moment record
#: was asked to name columns the record deliberately does not carry.
#:
#: ZERO IS NOT THE SAME AS DONE, and what is left is the other half of
#: #411: ``reason`` is still a string this kernel writes, in one language,
#: at the moment of refusing. What this number reaching zero buys is that
#: there is now exactly one author to move — every site hands over a
#: species and its occasion, and the sentence is assembled in one place.
STILL_AUTHORED = 0

#: Sites that file a species they were handed rather than one they name.
#:
#: ``EstimatorFailure(exc.failure_type, ...)`` and ``block(failure_type=
#: exc.failure_type, ...)`` carry a refusal another site already decided,
#: so which species they file cannot be read here. They were counted
#: rather than judged, and the count said what it existed to say: all five
#: were composing a second sentence, not relaying the first. Four of them
#: handed over ``str(exc)`` from the counterfactual solver, whose fourteen
#: raise sites wrote English prose behind a name this scan could not see.
#:
#: One is left and it relays. Nothing here enforces that — a forwarder
#: that starts authoring shows up in :data:`STILL_AUTHORED`, which is the
#: gate that counts authors whatever door they use.
#:
#: The one that went was ``refusals.relayed``, and it went by ceasing to be
#: a caller: it assembles the envelope beside :func:`block` rather than
#: through it, because the split of an occasion into words and values is
#: made at the raise site and is gone by the time the exception carries it.
#: A forwarder is a site that files a species decided elsewhere, and that
#: site now files nothing — it IS the filing.
FORWARDED = 1

#: Species whose sites do not agree on who writes the sentence.
#:
#: One refusal reaching two readers as two sentences is the state SAYS
#: replaced, so this is a list of exceptions rather than a tolerance. It is
#: empty, and the entry it held is what emptied it: the row at
#: ``dispatch._try_outcome_error_declaration`` had a true thing to add that
#: ``no_identifying_design`` does not own — the split is taken AROUND a
#: design, and only the precision cost is missing, not the point. The note
#: was never an addition to that species' sentence. It was a different
#: species (``no_design_to_split_around``), which is why no slot for a
#: filing row's own note was the right thing not to build.
STILL_TWO_AUTHORS: set[str] = set()

#: Sentences in :data:`SAYS` that no site can currently produce.
#:
#: ``no_first_stage``'s contract question is answered and its entry is
#: gone. The moment record is sufficient for the NUMBER by design and not
#: for the sentence, so the two sites inside the solvers do not file a
#: species that promises column names — they file
#: ``joint_first_stage_degenerate``, which says what the record knows. A
#: name whose sentence a site cannot keep is a second name, not a contract
#: to renegotiate.
#:
#: ``rows_outside_the_strata``'s one site raises ``iv._NotStratifiable``,
#: an ``EstimatorFailure`` subclass, and the scan above read the CALL by
#: name — so that entry was the subclass blind spot rather than a sentence
#: nobody could reach. :func:`_doors` reads the class statements now and
#: the entry is gone, along with the seventeen sites the blind spot hid.
#:
#: Empty, and it is a stronger statement than it looks: every sentence in
#: the reader's table has a site that can produce it, so a sentence that
#: drifts from its sites drifts where a test is watching.
STILL_UNSPOKEN: set[str] = set()

#: The two doors a refusal reaches the envelope through, by the name a
#: raise site writes. Not the whole set: a SUBCLASS is the same door under
#: another name, and this scan reads the name at the call — so seventeen
#: sites in two families (``iv._NotStratifiable``, the counterfactual
#: solver's ``CounterfactualBoundsError``) were outside every count here,
#: and three species reached readers with no sentence in :data:`SAYS` at
#: all, kept alive by the messages those sites were writing.
#:
#: :func:`_doors` widens it by READING the class statements rather than by
#: listing the subclasses, because a list is the thing that goes stale on
#: the day somebody adds the next one.
NAMED_DOORS = {"EstimatorFailure", "IdentificationFailure", "block"}

#: The keyword or position at which a site takes the sentence into its own
#: hands. ``block`` calls the field ``reason`` and the exception ``message``.
AUTHORS = {"message", "reason"}


def _doors(where: pathlib.Path | None = None) -> dict[str, list[str]]:
    """Every name a refusal can be filed under, and the species it fixes.

    Read out of the ``class`` statements, by name and transitively: a
    subclass of a door is a door, and it does not stop being one for being
    declared in the module that raises it. Names rather than types because
    the sites are read as source and never imported — a scan that had to
    import every module to find its doors would be a scan that a syntax
    error somewhere unrelated turns green.

    The value is the species the class pins in its own body, because that
    is where a subclass says which refusal it IS: its raise sites name no
    species, and a scan reading only the call would file every one of them
    as a forwarder — a site whose species cannot be read.
    """
    where = where or (ROOT / "themis")
    bases: dict[str, list[str]] = {}
    fixes: dict[str, list[str]] = {}
    for path in sorted(where.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            bases[node.name] = [
                b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
                for b in node.bases
            ]
            fixes[node.name] = [
                name for stmt in node.body
                if isinstance(stmt, (ast.Assign, ast.AnnAssign))
                and "species" in ast.dump(stmt.targets[0]
                                          if isinstance(stmt, ast.Assign)
                                          else stmt.target)
                for name in _species_in(stmt.value or ast.Constant(None))
            ]
    doors = dict.fromkeys(NAMED_DOORS, [])
    while True:
        found = {name: fixes[name] for name, mine in bases.items()
                 if name not in doors and set(doors) & set(mine)}
        if not found:
            return doors
        doors |= found


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


#: Every name a refusal is filed under in this build, computed once.
#:
#: Two other modules ask the same question — which calls file a refusal —
#: and one of them had typed the three seed names a second time. Reading
#: it from here is what makes "a subclass is a door" true for all three at
#: once, rather than true wherever somebody remembered to widen it.
DOORS = frozenset(_doors())


def _filing_sites(where: pathlib.Path | None = None
                  ) -> tuple[dict[str, list], list[tuple[str, int, bool]]]:
    """Every site that files a refusal, by species, and the forwarders.

    Read out of the source rather than out of a run: the branch that files
    a refusal is the branch no happy path takes, so a scan of what executed
    would be a scan of the refusals nobody hits.
    """
    where = where or (ROOT / "themis")
    doors = _doors(where)
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
            if door not in doors:
                continue
            named = next((kw.value for kw in node.keywords
                          if kw.arg == "failure_type"), None)
            first = named if named is not None else (
                node.args[0] if node.args else None)
            species = _species_in(first) if first is not None else []
            if not species and isinstance(first, ast.Name):
                species = bound.get(first.id, [])
            if not species:
                # A subclass that pins one says so in its class body, and
                # its sites name nothing because there is nothing left to
                # name — reading only the call reports the site as a
                # forwarder and the species as one nobody files.
                species = doors[door]
            if not species and first is None:
                continue
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


def test_a_species_with_no_sentence_and_no_message_is_refused(monkeypatch):
    """The counterexample for the mechanism: silence is not a sentence.

    The list this used to search ran dry, which is the outcome it was
    written to expect: every species has a sentence now, so the state
    being refused no longer occurs anywhere in the registry and has to be
    made. Taking one sentence away is the whole of it — the species is
    still declared, still filed by its sites, and the door still refuses
    to write down a refusal it cannot say.

    Both doors, because the constructor and ``block`` each check this and
    a fix applied to one of them would leave the other silent.
    """
    monkeypatch.delitem(refusals.SAYS, "sample_too_small")

    with pytest.raises(ValueError, match="has no sentence"):
        refusals.EstimatorFailure(refusals.Refusal.SAMPLE_TOO_SMALL)
    with pytest.raises(ValueError, match="has no sentence"):
        refusals.block(estimator="e",
                       failure_type=refusals.Refusal.SAMPLE_TOO_SMALL)


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
        refusals.Refusal.DEGENERATE_RECOVERED_EXPOSURE,
        stratum={"w": np.True_},
        p_treated=np.float64(0.0), p_control=np.float64(1.0),
    )
    assert exc.details["stratum"] == {"w": True}

    # And one level in, which is where coercing only the scalars would
    # leave a Python repr standing where the structure was.
    nested = refusals.EstimatorFailure(
        refusals.Refusal.INSUFFICIENT_SUPPORT,
        cells=[{"a": np.int64(0)}], quantity="P(Y=1 | a, w)",
    )
    assert nested.details["cells"] == [{"a": 0}]


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
