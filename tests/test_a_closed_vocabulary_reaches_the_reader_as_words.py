"""A member of a closed vocabulary reaches the reader through its gloss.

The registry in ``test_vocabulary_reach`` asks the other half of this: does
every member HAVE a word. It cannot ask whether a producer used it, and the
monotonicity direction is what that gap looked like. The direction had no
word at all, and the registry let it through on a written reason — that the
ledger line said the direction in words. The ledger line printed the token
(``单调性（non_decreasing）``), so the reason was simply false, and nothing
had ever asked it to be true.

Five producers had each answered the missing word for themselves: four
interpolated the token into a Chinese sentence, one hand-wrote a pair of
English clauses into a Chinese note. That is what a vocabulary with no
gloss looks like from the inside — not one omission but one per site, and
a sixth waiting for the next site.

So there are two rules here. The direction has words (the registry now
enforces that, because the row says ``glossed_by`` instead of a sentence),
and no producer writes its own: a value of a ledger vocabulary
interpolated into a Chinese sentence goes through that vocabulary's
gloss. The second rule's denominator is the glosses ``themis.ledger``
exports and every module under ``themis/`` — neither is a list anyone
maintains, which is the point, because the defect was five sites nobody
had listed.

**What that second rule does not cover, and why not a wider one.** The
registry holds more vocabularies than the ledger's, and the obvious
generalisation — no member's token inside a string literal written for a
reader — was tried and does not work. Members are ordinary technical
words that Chinese prose borrows on its own terms: ``bounds``,
``transport``, ``effect``, ``interpretation``, ``marginal``. Fifty-three
literals matched outside documentation and essentially all of them were
the English word rather than the vocabulary's member, which no reading of
the text can tell apart. The interpolation rule can, because there the
value comes from the vocabulary at run time rather than from someone's
sentence — so it is the rule, and it reaches as far as the naming
convention that pairs ``X`` with ``X_word`` does. Giving the other
glosses that convention would widen it; nothing here pretends it is
already wide.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from themis import language

import themis
import themis.ledger as ledger
from themis.output.assumption_glossary import classify_assumption
from themis.types import Monotonicity
from tests.bounds_rows import row


_PACKAGE = Path(__file__).parent.parent / "themis"

#: What ``themis.ledger`` hands a reader a word for. Derived from the
#: exports rather than named here: a fifth vocabulary added to the ledger
#: joins this rule by existing.
SUBJECTS = sorted(n[:-5] for n in dir(ledger) if n.endswith("_word"))
GLOSSES = {f"{s}_word" for s in SUBJECTS}


def test_the_ledger_has_glosses_to_check():
    """The denominator is discovered, so it has to be shown non-empty."""
    assert "monotonicity" in SUBJECTS
    assert len(SUBJECTS) >= 4


# ------------------------------------------------------- the direction has words


@pytest.mark.parametrize("direction", list(Monotonicity))
def test_the_direction_has_words_of_its_own(direction):
    words = ledger.monotonicity_word(direction)
    assert direction.value not in words
    # And they say what the assumption means, not only how it is written:
    # a reader who does not read Y(1) ≥ Y(0) is the reason this exists.
    assert "处理" in words and "结局" in words


def test_an_unknown_direction_renders_as_its_own_token():
    """The same fallback the other three glosses keep, and for the same
    reason: a name the reader has to look up beats a confident wrong one."""
    assert ledger.monotonicity_word("sideways") == language.absent(
        "no_word_for_this_token", token="sideways")


# ------------------------------------------------ what the reader is handed


@pytest.mark.parametrize("direction", list(Monotonicity))
def test_the_ledger_line_says_the_direction_in_words(direction):
    """The sentence the registry's old reason claimed was already true."""
    for assumption in (f"mtr_{direction.value}",
                       f"monotonicity_{direction.value}_in_treatment"):
        claim = classify_assumption(assumption)["claim"]
        assert direction.value not in claim, assumption
        assert ledger.monotonicity_word(direction) in claim, assumption


def _mtr_program(direction):
    """x → y with x ↔ y latent, and a monotone treatment response declared."""
    def atom(pred):
        return {"predicate": pred, "args": [{"type": "var", "name": "I"}]}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {"monotonicity": {
            "target": "y", "treatment": "x", "direction": direction.value}},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": atom("x"), "to": atom("y")},
            {"kind": "bidirected", "forall": ["I"],
             "left": atom("x"), "right": atom("y")},
            {"kind": "query", "id": "mtr",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


@pytest.mark.parametrize("direction", list(Monotonicity))
def test_the_bounds_note_says_the_direction_in_words(direction):
    """The note that used to hand a Chinese reader an English clause.

    ``non-decreasing (Y(1) ≥ Y(0))`` also survived the language gate,
    correctly: that gate tells prose from formula by function words, and
    this clause has none. A closed vocabulary is the registry's to answer,
    not the language gate's.
    """
    result = themis.run(_mtr_program(direction))["results"][0]
    note = row(result, "manski_tamer_monotonicity")["notes"]
    assert ledger.monotonicity_word(direction) in note
    assert direction.value not in note
    assert "non-decreasing" not in note and "non-increasing" not in note


def test_the_tightened_side_is_not_handed_over_in_english():
    """The second bare token in the same sentence, found beside the first."""
    result = themis.run(
        _mtr_program(Monotonicity.NON_DECREASING))["results"][0]
    note = row(result, "manski_tamer_monotonicity")["notes"]
    assert "下界" in note or "上界" in note
    assert "lower 这一侧" not in note and "upper 这一侧" not in note


# ------------------------------------------------- and no producer writes its own


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def _names_in(node: ast.AST) -> set[str]:
    """Every identifier or string key the interpolated expression mentions."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.add(sub.value)
    return out


def _calls_a_gloss(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = (func.id if isinstance(func, ast.Name)
                    else getattr(func, "attr", ""))
            if name in GLOSSES:
                return True
    return False


def _modules():
    return sorted(p for p in _PACKAGE.rglob("*.py")
                  if "frontend" not in p.parts)


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_sentence_interpolates_a_vocabulary_instead_of_its_gloss(path):
    """CJK in the literal is what makes it addressed to a reader.

    The same value interpolated into an identifier — ``mtr_{direction}``,
    an assumption id — is not a sentence and stays the token, which is
    what that id is for. The line between the two is the one the language
    gate already draws, read here on the one thing this rule is about.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    raw: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal = "".join(v.value for v in node.values
                          if isinstance(v, ast.Constant))
        if not _has_cjk(literal):
            continue
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            subjects = _names_in(part.value) & set(SUBJECTS)
            if subjects and not _calls_a_gloss(part.value):
                raw.append(
                    f"line {node.lineno}: {sorted(subjects)} in {literal!r}")

    assert not raw, (
        f"{path.name} hands a reader a ledger vocabulary without its gloss "
        f"— the member arrives as its own identifier inside a sentence "
        f"written for a person: " + "; ".join(raw)
    )
