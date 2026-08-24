"""A refusal's slot can carry a WORD, and a word is not a value said back.

``details`` was designed to carry the occasion's NUMBERS — which stratum, how
many rows, what determinant — and a sentence's second need is a word: WHICH
matrix has no inverse, WHICH channel was mismeasured. On that channel the two
were indistinguishable, so ``_slot`` stringified, and a vocabulary member's
``str`` is its TOKEN — the spelling the envelope carries, which is in no
language and in this repository looks like English. A token dropped into a
Chinese sentence is the defect the sentence table exists to remove, one level
in.

The consequence was not cosmetic. Three species could not be folded at all:
each was one fact plus a word, so every raise site hard-coded its word into
prose of its own and thereby became another author of the species' sentence —
which is how one of them came to say "outcome" about the exposure.

What is checked here: that a word reaching a sentence reaches it as the
READER's word, and that no site hands a slot the token instead. What is not:
whether a given slot ought to hold a word. That is a reading of the sentence,
and the sentence is one author's.
"""
from __future__ import annotations

import ast
import collections
import enum
import importlib
import pathlib
import pkgutil
import string

import pytest

from themis import language, refusals

#: The calls that file a refusal. The same doors the author count uses — a
#: word reaches a reader the same way whichever one it came through — and
#: imported rather than typed again, because the set is not three names.
#: A subclass is a door too, and this copy had missed seventeen sites in
#: two families for as long as it was its own list.
from tests.test_a_refusal_says_one_thing_in_every_language import DOORS

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _vocabularies() -> dict[str, type[language.Word]]:
    """Every vocabulary in this build whose members are read inside a sentence.

    Walked from the base class rather than listed, so a new one is in the
    denominator the moment it is written — which is the only way a
    completeness check means anything.
    """
    import themis

    for mod in pkgutil.walk_packages(themis.__path__, "themis."):
        if "web.frontend" in mod.name:
            continue
        try:
            importlib.import_module(mod.name)
        except ImportError:
            continue

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return {f"{cls.__module__}.{cls.__qualname__}": cls
            for cls in walk(language.Word) if len(cls) > 0}


VOCABULARIES = _vocabularies()
MEMBERS = [(name, member)
           for name, cls in sorted(VOCABULARIES.items()) for member in cls]
TOKENS = {member.value for _name, member in MEMBERS}


def _dotted(node) -> str:
    """``refusals.QueryRole.EXPOSURE`` as text, for an attribute chain."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _fed(where: pathlib.Path) -> dict[str, dict[str, set]]:
    """What each slot of each refusal is handed, over the whole tree.

    ``{slot: {"word": {sites}, "token": {sites}}}`` — the two fillings that
    can be told apart by reading. A slot handed a name or a call is neither,
    and is not counted: this is a check on what a source says, and a source
    that says ``role=channel`` has said nothing about which it is. The
    denominator is therefore the literals, which is where a token could be
    written down in the first place.
    """
    seen: dict[str, dict[str, set]] = collections.defaultdict(
        lambda: {"word": set(), "token": set()})
    vocabulary_names = {name.rsplit(".", 1)[-1] for name in VOCABULARIES}
    for path in sorted(where.rglob("*.py")):
        module = path.relative_to(where.parent).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            door = (node.func.id if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", ""))
            if door not in DOORS:
                continue
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                site = f"{module}:{node.lineno} {kw.arg}"
                chain = _dotted(kw.value).split(".")
                if len(chain) >= 2 and chain[-2] in vocabulary_names:
                    seen[kw.arg]["word"].add(site)
                elif (isinstance(kw.value, ast.Constant)
                      and kw.value.value in TOKENS):
                    seen[kw.arg]["token"].add(site)
    return seen


def _spelled_out(where: pathlib.Path) -> dict[str, set]:
    """Sites that wrote a word's token where the word itself would go."""
    return {slot: got["token"] for slot, got in _fed(where).items()
            if got["token"]}


# --- the mechanism ---------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(language.written()))
@pytest.mark.parametrize("name,member", MEMBERS, ids=lambda x: getattr(x, "value", x))
def test_a_slot_renders_the_readers_word(name, member, lang):
    """What the slot gives the sentence is this language's word for it."""
    assert language.slot(member, lang) == member.words[lang], (name, member)


@pytest.mark.parametrize("name,member", MEMBERS, ids=lambda x: getattr(x, "value", x))
def test_the_token_is_the_same_in_every_language(name, member):
    """Which is why it cannot be what a sentence gets.

    The token is what the envelope carries and what a consumer branches on,
    so it must not move when a reader's preference does — and a thing that
    does not move cannot be a translation of anything.
    """
    assert str(member) == member.value, name
    assert {language.slot(member, lang) for lang in language.written()} != {
        member.value}, (
        f"{name}.{member.name} reads the same in every language, so this "
        f"member proves nothing about the mechanism; either it needs its "
        f"other language or it is not a word")


def test_a_stringifying_slot_puts_the_token_in_the_sentence():
    """The state this replaced, reconstructed rather than described.

    A gate whose failing case cannot be built is a gate nobody has seen say
    no. This builds it out of the same species and the same member, changing
    only the one thing that changed: whether the slot may hold a word.
    """
    words = refusals.SAYS["singular_confusion_matrix"]
    role = refusals.QueryRole.EXPOSURE
    facts = {"determinant": 0.0, "floor": 1e-6}

    stringified = words["zh"].format(role=str(role), **facts)
    assert role.value in stringified          # an English token, in Chinese
    assert role.words["zh"] not in stringified

    delegated = refusals.sentence("singular_confusion_matrix",
                                  {"role": role, **facts}, "zh")
    assert role.words["zh"] in delegated
    assert role.value not in delegated


# --- the sites -------------------------------------------------------------


def test_no_refusal_slot_is_handed_a_word_spelled_out():
    """A member's token written as a string literal is the member, retyped.

    Retyping it is not a smaller version of using it — it is the whole
    defect: the token is what the ENVELOPE carries, and a sentence built
    around it says the same English word to every reader. That this reads
    correctly in one language is why it survives; the language it reads
    correctly in is the one nobody was writing the table for.

    A literal at a raise site is always the author's word and never the
    caller's data — a column named "outcome" arrives as a value, not as
    something typed into the source — so a literal that spells a member is
    not a coincidence to be excused.
    """
    spelled = _spelled_out(ROOT / "themis")
    assert not spelled, {slot: sorted(got) for slot, got in spelled.items()}


def test_the_check_sees_a_site_that_wrote_the_token_instead(tmp_path):
    """Against a source built for it, not against the repository.

    The repository passing is what the check is for; a check verified only by
    the repository passing has been verified by the thing it is watching.
    """
    package = tmp_path / "themis"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    wrong = (
        "from ..refusals import EstimatorFailure, QueryRole, Refusal\n"
        "\n"
        "def a(det):\n"
        "    raise EstimatorFailure(\n"
        "        Refusal.SINGULAR_CONFUSION_MATRIX,\n"
        "        role=QueryRole.EXPOSURE, determinant=det, floor=1e-6)\n"
        "\n"
        "def b(det):\n"
        "    raise EstimatorFailure(\n"
        "        Refusal.SINGULAR_CONFUSION_MATRIX,\n"
        "        role='exposure', determinant=det, floor=1e-6)\n"
    )
    (package / "estimator.py").write_text(wrong, encoding="utf-8")

    spelled = _spelled_out(package)
    assert set(spelled) == {"role"}, spelled
    assert len(spelled["role"]) == 1

    right = wrong[:wrong.index("\n\ndef b(")] + "\n"
    (package / "estimator.py").write_text(right, encoding="utf-8")
    assert not _spelled_out(package)
    assert _fed(package)["role"]["word"], "the good arm has to be seen too"


def test_a_word_slot_is_watched_at_all():
    """The denominator, said out loud.

    A scan for "a slot handed both a word and a token" reads as a check on
    words and is a check on the slots that hold one — so if no site anywhere
    hands a word to anything, it passes by having nothing to look at. This is
    the same blindness the author count had while it could only see one of
    the two doors, and it is worth one assertion.
    """
    fed = _fed(ROOT / "themis")
    with_a_word = {slot for slot, got in fed.items() if got["word"]}
    assert with_a_word, "no refusal anywhere hands a slot a word"
    assert VOCABULARIES, "no vocabulary in this build is read inside a sentence"


# --- the fold this made possible -------------------------------------------


def _holes(text: str) -> set[str]:
    return {name for _t, name, _s, _c in string.Formatter().parse(text) if name}


@pytest.mark.parametrize("species,slot", [
    ("singular_design", "design"),
    ("singular_confusion_matrix", "role"),
    ("singular_confusion_matrix_in_stratum", "role"),
])
def test_the_species_that_needed_this_names_its_word(species, slot):
    """Each of these was one fact told at several sites in several sentences,
    and the one thing that differed between them was the word."""
    for lang in sorted(language.written()):
        holes = _holes(refusals.SAYS[species][lang])
        assert slot in holes, (species, lang, sorted(holes))


def test_the_vocabularies_are_the_ones_the_reach_table_watches():
    """A word vocabulary is a vocabulary, so #362's row is owed for it too.

    Stated here as well because the two checks fail differently: the reach
    table says a vocabulary has no declared reader, and this says which
    vocabularies exist to have one.
    """
    from tests.test_vocabulary_reach import VOCABULARIES as ROWS

    declared = {row.declares for row in ROWS.values() if row.declares}
    assert set(VOCABULARIES) <= declared, sorted(set(VOCABULARIES) - declared)


def test_enum_is_still_the_base():
    """``Word`` is an ``Enum``, so everything that walks enums finds these too.

    Written down because it is what makes the sentence above true, and it is
    a property of a base class three files away — the kind that gets changed
    by someone who never reads this one.
    """
    for name, cls in VOCABULARIES.items():
        assert issubclass(cls, enum.Enum), name
        assert issubclass(cls, str), name


# --- and the same answer one level down ---------------------------------------
#
# A hole holds a word. The next thing a hole is asked to hold is a whole
# SENTENCE — one variable and what its declaration says about how it was
# measured — and, where there are several, all of them. Until it could, the
# only way to put a sentence inside a sentence was to assemble the inner one
# where it was built, which is the kernel choosing a language for a reader it
# cannot see; both sites that needed it did exactly that, and one of them
# joined its list with the comma of the language its author was thinking in.
#
# The shape needs no new half: a statement is a word whose text has holes, so
# it travels in the half that already carries words.


def _dichotomized(**thresholds):
    """A result whose gap report names one variable per declared cutpoint."""
    from themis import run
    from tests.test_dichotomized_continuous_measure import _make_program

    out = run(_make_program(thresholds=thresholds, confounder=len(thresholds) > 1))
    result = out["results"][0]
    for gap in (result.get("data_gap_report") or {}).get("gaps", []):
        if gap["kind"] == "dichotomized_continuous_measure":
            return result, gap
    raise AssertionError("no dichotomization gap; the producer moved")


def test_a_hole_holds_the_sentence_and_not_its_text():
    """What crosses is the inner sentence's word and its facts."""
    _result, gap = _dichotomized(x=">=3cm")
    said = gap["describes"][0]
    assert "variables" not in (said.get("said") or {}), (
        "the inner sentence was rendered before it left"
    )
    inner = said["words"]["variables"]
    assert [one["vocabulary"] for one in inner] == ["measurement_note"]
    assert inner[0]["said"] == {"variable": "x", "cut": ">=3cm"}


def test_the_seam_between_several_is_the_readers_punctuation():
    """The defect the list had, and the one thing a list cannot be joined by
    where it is built: Chinese separates items with ``、`` and English with a
    comma, and neither is the other's."""
    _result, gap = _dichotomized(x=">=3cm", z=">=50")
    from themis import gaps as gap_channel

    seen = {lang: gap_channel.describe(gap["describes"][0], lang)
            for lang in ("zh", "en")}
    assert "x（切点：“>=3cm”）、z（切点：“>=50”）" in seen["zh"]
    assert 'x (threshold: “>=3cm”), z (threshold: “>=50”)' in seen["en"]


@pytest.mark.parametrize("instead", [
    "x（切点：“>=3cm”）、z（切点：“>=50”）",
    [{"vocabulary": "measurement_note", "token": "a_threshold_cut_it_in_two"},
     "z（切点：“>=50”）"],
    [{"vocabulary": "measurement_note", "said": {"variable": "x"}}],
], ids=["assembled", "one_of_them_assembled", "no_token"])
def test_the_envelope_refuses_a_hole_that_holds_text(instead):
    """The counterexample the contract has to say no to.

    A hole that holds a rendered sentence is the shape this replaced, and it
    is indistinguishable from the new one to everything except the contract —
    both are "something in the words half". So the contract is where it has
    to be refused, and a list is refused for one bad member rather than for
    all of them, since one is all it takes to make the seam somebody else's.
    """
    import copy

    from themis.input.syntactic_validator import SyntacticError, validate_result

    result, gap = _dichotomized(x=">=3cm")
    validate_result(result)                    # the good arm, seen first

    tampered = copy.deepcopy(result)
    for one in (tampered.get("data_gap_report") or {}).get("gaps", []):
        if one["kind"] == gap["kind"]:
            one["describes"][0]["words"]["variables"] = instead
    with pytest.raises(SyntacticError):
        validate_result(tampered)
