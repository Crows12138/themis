"""``EnvelopeName`` gives up singleton identity on purpose. Nothing may ask.

The base rewrites ``__reduce_ex__``, ``__copy__`` and ``__deepcopy__`` so a
copied or pickled member comes back as a plain ``str``: the envelope is
data, and whoever serialises it must not receive the registry along with
it. Identity is precisely the property that buys — and thirty-five
comparisons in the package were spending it.

None of them was wrong on the day it was written, because no path copies
these values yet. That is what makes the shape dangerous rather than
broken: the failure arrives with a future copy, in a comparison nobody
revisits, and it is silent. One of the thirty-five decided which side of a
Manski interval to tighten, so a copied value there would have produced a
wrong answer rather than an exception.

The rule draws its line at the base class, not at "enums in general".
A plain ``Enum`` keeps its members singletons and ``is`` against one is
correct; ``ResultStatus``, ``Role``, ``AnswerTier`` and the rest are
compared that way in about thirty places and stay that way. What the line
buys is the migration: the day a vocabulary inherits ``EnvelopeName``,
every comparison that was fine becomes a defect, and this is what says so
instead of somebody remembering.

Scanned over ``themis/`` and not over the tests: a test that compares a
copied member with ``is`` fails loudly, and loud is not the problem.
"""
from __future__ import annotations

import ast
import copy
import enum
import importlib
import pathlib
import pkgutil
import textwrap

import pytest

import themis
from themis.types import EnvelopeName

REPO = pathlib.Path(__file__).resolve().parent.parent


def _import_everything() -> None:
    for mod in pkgutil.walk_packages(themis.__path__, "themis."):
        if "web.frontend" in mod.name:
            continue
        try:
            importlib.import_module(mod.name)
        except ImportError:
            continue


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def _vocabularies() -> dict[str, type[enum.Enum]]:
    """Every vocabulary that has given up identity.

    Found by importing the package and walking subclasses, not by reading a
    list: a vocabulary added tomorrow is inside the rule the day it is
    added, and a vocabulary that MOVES onto the base is what this exists to
    catch. Member-less classes are marker bases and declare no vocabulary.
    """
    _import_everything()
    return {c.__name__: c for c in _subclasses(EnvelopeName) if len(c) > 0}


def _modules() -> list[pathlib.Path]:
    return sorted(p for p in (REPO / "themis").rglob("*.py")
                  if "frontend" not in p.parts)


def _identity_comparisons(source: str, names: set[str]) -> list[str]:
    """Every ``x is <Vocabulary>.MEMBER`` in ``source``, either order."""
    def member(node) -> bool:
        return (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in names
                and node.attr.isupper())

    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        for op, right in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Is, ast.IsNot)) and (
                    member(node.left) or member(right)):
                found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return found


# --- the property the base actually gives up ---------------------------------

@pytest.mark.parametrize("name", sorted(_vocabularies()))
def test_a_copied_member_is_no_longer_the_member(name):
    """Not a style preference: the copy is a different object, and equal."""
    member = next(iter(_vocabularies()[name]))
    for copied in (copy.copy(member), copy.deepcopy(member)):
        assert copied is not member
        assert copied == member
        assert type(copied) is str


# --- the rule ----------------------------------------------------------------

@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_module_asks_an_envelope_vocabulary_for_its_identity(path):
    names = set(_vocabularies())
    found = _identity_comparisons(path.read_text(encoding="utf-8"), names)
    assert not found, f"{path.relative_to(REPO).as_posix()}: {found}"


def test_the_rule_has_a_denominator():
    """A rule over zero vocabularies passes by saying nothing."""
    assert len(_vocabularies()) >= 9, sorted(_vocabularies())


# --- what it says no to, and what it deliberately does not --------------------

_ASKS = """
    from themis.refusals import Refusal
    def f(x):
        return x is Refusal.CONTINUOUS_MEDIATOR
"""

_ASKS_REVERSED = """
    from themis.refusals import Refusal
    def f(x):
        return Refusal.CONTINUOUS_MEDIATOR is not x
"""

_ASKS_MID_CHAIN = """
    from themis.refusals import Refusal
    def f(a, x):
        return a == x is Refusal.CONTINUOUS_MEDIATOR
"""


@pytest.mark.parametrize(
    "source", [_ASKS, _ASKS_REVERSED, _ASKS_MID_CHAIN],
    ids=["plain", "reversed", "mid-chain"],
)
def test_the_rule_says_no(source):
    found = _identity_comparisons(textwrap.dedent(source), set(_vocabularies()))
    assert found, "an identity comparison went unnoticed"


def test_the_rule_leaves_a_plain_enum_alone():
    """A plain Enum keeps its singletons, so ``is`` against one is correct.

    The line is drawn at the base class rather than at the word ``is``,
    and this is where that shows.
    """
    source = textwrap.dedent("""
        from themis.types import ResultStatus
        def f(r):
            return r.status is ResultStatus.OUTSIDE_LANGUAGE
    """)
    assert not _identity_comparisons(source, set(_vocabularies()))


def test_equality_is_what_survives_the_copy():
    """The replacement has to hold for the member AND for what it becomes."""
    member = next(iter(_vocabularies()["Refusal"]))
    assert copy.deepcopy(member) == member
    assert str(member) == member
