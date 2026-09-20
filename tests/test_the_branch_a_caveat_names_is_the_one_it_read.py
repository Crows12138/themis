"""The branch a caveat names is the one its premises came from.

A mediation answer that identifies a decomposition carries a caveat per
branch, so a reader cannot take ``identifiable: true`` for unconditional.
Each spells the premises it rests on and puts a word over them saying
which quantity they are the premises OF -- ``CDE`` or ``NDE/NIE``.

The word was unheld, on a reason written into the roster that holds the
rest: "a coined label (``CDE``) is not a copy of anything at all". Half of
that is true. No record on the envelope holds the STRING ``CDE``. But the
word is not a copy, it is a NAME, and what it names is on the envelope
twice over: the branch key the gap's own provenance cites, and the list of
premises in the same breath, which is one branch's and -- measured over
every answer here -- never the other's.

So the roster was asking after a record of the VALUE where the record that
exists is a record of what the value MEANS. A second roster puts that
question, and is handed the ``said`` the word sits in, which the walk had
been carrying all along and saying so.

Holding it by membership in the two words there are would have moved the
same count. It refuses a forgery and takes the SWAP -- the one lie this
word can tell that reads as honest, and so the only one worth a rule. On
twenty-two of these twenty-four caveats both branches are identifiable,
so either word is one this answer did write; the swap puts it over the
other branch's premises and nothing about it looks wrong. Those two tests
are here.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.output import data_gap_report as _producer
from themis.verifier import gap_claim_rules as _rules

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))

OTHER = {"CDE": "NDE/NIE", "NDE/NIE": "CDE"}


def _caveats():
    """Every stored caveat carrying a branch word, and where it sits."""
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        report = result.get("data_gap_report") or {}
        for gi, gap in enumerate(report.get("gaps") or ()):
            for ci, claim in enumerate(gap.get("describes") or ()):
                said = claim.get("said")
                if isinstance(said, dict) and "branch" in said:
                    yield name, gi, ci, claim


CAVEATS = tuple(_caveats())
CARRYING = tuple(sorted({name for name, _, _, _ in CAVEATS}))
IDS = tuple(f"{name}[{gi}.{ci}]" for name, gi, ci, _ in CAVEATS)


def _branches_of(result, block=None):
    """Every (word, branch record) this answer files, for either key."""
    extensions = result.get("extensions") or {}
    for key in _rules._DECOMPOSITIONS:
        if block is not None and key != block:
            continue
        found = extensions.get(key)
        if not isinstance(found, dict):
            continue
        for word, inner in _rules._BRANCH_KEYS.items():
            branch = found.get(inner)
            if isinstance(branch, dict):
                yield word, branch


def _premises(branch):
    return ", ".join(str(one) for one in branch.get("assumptions") or ())


def _bend(name, gi, ci, key, value):
    """A copy of one stored answer with one leaf of one caveat bent."""
    result = copy.deepcopy(SHAPES[name]["result"])
    result["data_gap_report"]["gaps"][gi]["describes"][ci]["said"][key] = value
    return result


def _refusal(name, result):
    """What the strongest door that reads this answer says about it."""
    door = the_door_for(result)
    with pytest.raises(Exception) as caught:
        door(SHAPES[name]["program"], result)
    return str(caught.value)


# --------------------------------------------------------------- the corpus

def test_the_caveats_that_carry_a_branch():
    """The census this file is about, so a corpus that stops carrying
    them says so here rather than by every test below passing vacuously."""
    assert len(CAVEATS) == 24
    assert len(CARRYING) == 13
    words = sorted(claim["said"]["branch"] for _, _, _, claim in CAVEATS)
    assert words.count("CDE") == 13
    assert words.count("NDE/NIE") == 11
    assert {claim.get("sentence") for _, _, _, claim in CAVEATS} == {
        "mediation_is_identifiable_for_a_mediator",
        "mediation_is_identifiable_for_a_mediator_block",
    }
    assert {frozenset(claim["said"]) for _, _, _, claim in CAVEATS} == {
        frozenset({"branch", "subject", "assumptions"})
    }


def test_the_two_words_are_the_producers_own():
    """The one transcription this fix costs, held to the original.

    A verifier may not import the producer, so the pair is written out
    twice. This is the only thing keeping the two copies one fact: a third
    branch, or a branch respelt, fails here rather than going quietly
    unasked in the roster that has to know which key a word picks out.
    """
    assert dict(_producer._BRANCHES) == _rules._BRANCH_KEYS


def test_every_key_a_decomposition_is_filed_under_is_read():
    """The other half of the same transcription: which extension keys
    hold a decomposition. Read off the corpus, so a third shape of
    mediation answer is noticed here."""
    filed = set()
    for name in sorted(SHAPES):
        for key in (SHAPES[name]["result"].get("extensions") or {}):
            if "mediation" in key and key.endswith("decomposition"):
                filed.add(key)
    assert filed == set(_rules._DECOMPOSITIONS)


def test_the_two_branches_never_record_the_same_premises():
    """The fact the rule leans on, measured rather than assumed.

    The word is held by the premises beside it, which can only pick a
    branch out where the two branches' premises differ. They do, on every
    answer here. Where they did not the reader returns both words and the
    rule accepts either, which is the honest answer to a question the
    envelope does not settle -- but it is not the situation, and a corpus
    that drifted into it would weaken this file silently.
    """
    for name in CARRYING:
        for key in _rules._DECOMPOSITIONS:
            recorded = {word: _premises(branch)
                        for word, branch in _branches_of(
                            SHAPES[name]["result"], key)}
            listed = [text for text in recorded.values() if text]
            assert len(listed) == len(set(listed)), name


def test_the_branch_never_travels_as_a_word():
    """Why the rule reads one half and not both.

    What a locator picks out is the envelope's own spelling of a key; the
    other half is where a fact goes to be said in the reader's language,
    and a translated word would not equal the record's spelling. That is a
    choice about where this fact travels, and it holds here.
    """
    for name in sorted(SHAPES):
        report = SHAPES[name]["result"].get("data_gap_report")
        if not isinstance(report, dict):
            continue
        for _where, _statement, words, _said in _rules.every_word_mapping(
                report):
            assert "branch" not in words, name


# ------------------------------------------------------------ honest first

@pytest.mark.parametrize("name", CARRYING)
def test_an_honest_caveat_is_still_accepted(name):
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


# ------------------------------------------------------------------- bends

@pytest.mark.parametrize("name,gi,ci,claim", CAVEATS, ids=IDS)
def test_a_forged_branch_is_refused(name, gi, ci, claim):
    word = claim["said"]["branch"]
    said = _refusal(name, _bend(name, gi, ci, "branch", word + "_forged"))
    assert "where it names the branch whose assumptions it lists" in said


@pytest.mark.parametrize("name,gi,ci,claim", CAVEATS, ids=IDS)
def test_a_branch_left_blank_is_refused(name, gi, ci, claim):
    said = _refusal(name, _bend(name, gi, ci, "branch", ""))
    assert "where it names the branch whose assumptions it lists" in said


@pytest.mark.parametrize("name,gi,ci,claim", CAVEATS, ids=IDS)
def test_the_other_branchs_name_over_these_premises_is_refused(
        name, gi, ci, claim):
    """The swap: the lie a vocabulary would have taken.

    A reader granting these premises is granting them for the quantity the
    word says, and the word is the only part of the caveat that says which.
    """
    word = claim["said"]["branch"]
    said = _refusal(name, _bend(name, gi, ci, "branch", OTHER[word]))
    assert f"a gap says {OTHER[word]!r}" in said
    assert f"is [{word!r}]'s" in said


def test_the_swap_is_a_word_this_answer_could_honestly_have_written():
    """Why membership in the vocabulary would not have held this leaf.

    On all but two of these caveats the answer identifies BOTH branches
    and writes a caveat for each, so both words are words it honestly
    wrote -- one of them over the other branch's premises. A rule asking
    only whether the word is one this answer reports takes the swap on
    every one of those, which is the whole of what the word can get wrong.
    """
    both = 0
    for name, _gi, _ci, claim in CAVEATS:
        reported = {word for word, _b in _branches_of(SHAPES[name]["result"])
                    if any(c["said"]["branch"] == word
                           for _n, _g, _c, c in CAVEATS if _n == name)}
        if OTHER[claim["said"]["branch"]] in reported:
            both += 1
    assert both == 22


def _premise_swaps():
    """Each caveat paired with the other branch's premises, where the
    other branch has any.

    Built here rather than skipped inside the test. A run-time skip is a
    decision about the corpus wearing the shape of an absence, and this
    one is a fact worth stating: two of these twenty-four answers identify
    one branch only, so there is no other list to put under the word.
    """
    for name, gi, ci, claim in CAVEATS:
        word = claim["said"]["branch"]
        theirs = {w: _premises(b)
                  for w, b in _branches_of(SHAPES[name]["result"])}
        other = theirs.get(OTHER[word], "")
        if other and other != claim["said"]["assumptions"]:
            yield name, gi, ci, word, other


SWAPS = tuple(_premise_swaps())


def test_two_of_these_answers_identify_one_branch_only():
    assert len(SWAPS) == len(CAVEATS) - 2 == 22


@pytest.mark.parametrize("name,gi,ci,word,other", SWAPS,
                         ids=[f"{n}[{g}.{c}]" for n, g, c, _w, _o in SWAPS])
def test_the_premises_beside_it_are_now_one_branchs(name, gi, ci, word, other):
    """The second hole this closes.

    ``said.assumptions`` was held by membership in every assumption id the
    answer records ANYWHERE, and both branches' are recorded. So a caveat
    could list the other branch's premises under its own word and pass.
    Read as the record the word names, it cannot.
    """
    said = _refusal(name, _bend(name, gi, ci, "assumptions", other))
    assert f"a gap says {word!r}" in said


# --------------------------------------------------------- the reader alone

def test_the_reader_names_the_branch_whose_premises_these_are():
    """Read directly, over every stored caveat: exactly one word, and it
    is the one the caveat carries."""
    for name, _gi, _ci, claim in CAVEATS:
        picked = _rules._the_branch_whose_assumptions_these_are(
            SHAPES[name]["result"], claim["said"])
        assert picked == {claim["said"]["branch"]}, name


def test_the_reader_is_silent_where_the_record_is_not_there():
    """The discipline the rule beside it keeps, kept here too.

    A caveat listing premises no branch on this envelope records is not a
    caveat this rule can judge -- inventing the roster out of the thing
    being judged is what the module exists not to do. Empty, and the rule
    says nothing.
    """
    result = SHAPES[CARRYING[0]]["result"]
    assert _rules._the_branch_whose_assumptions_these_are(
        result, {"assumptions": "no_such_premise"}) == set()
    assert _rules._the_branch_whose_assumptions_these_are(
        result, {"assumptions": ""}) == set()
    assert _rules._the_branch_whose_assumptions_these_are(
        result, {}) == set()
    assert _rules._the_branch_whose_assumptions_these_are(
        {}, {"assumptions": "x"}) == set()


def test_the_roster_is_asked_by_the_rule_that_walks_the_report():
    """One walk, two questions. A second walk would be a second place for
    the silence discipline to be got right, which is how the two copies of
    a rule drift apart."""
    tree = ast.parse(inspect.getsource(_rules.verify_gap_quotes))
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert {"_locates", "_copied_from"} <= called


def test_the_sentence_that_called_the_word_uncopyable_is_gone():
    """The claim this fix disproves, removed rather than left beside its
    disproof."""
    source = pathlib.Path(_rules.__file__).read_text("utf-8")
    assert "not a copy of anything at all" not in source
    assert "_LOCATES" in source
