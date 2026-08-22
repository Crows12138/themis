"""A vocabulary's member printed as where it is declared, not as what it says.

#386. ``class X(str, Enum)`` makes a member equal to its value and comparable
to it, and then ``str(member)``, ``f"{member}"`` and ``"%s" % member`` all
hand back ``"X.MEMBER"`` — the address of the declaration, which is the one
thing a reader holding the value does not need. #380 measured five defects of
exactly that shape on ``Monotonicity``; #382 moved it to a base that fixes it.
Eighteen vocabularies were still the old shape.

**What was and was not measured.** The registered item left one question
open: does an address actually reach a reader today? Asked over the corpus
``test_no_sentence_reaches_the_reader_in_the_wrong_language`` already
builds — every string the kernel emits across the L3 cases — the answer is
**no**, 0 of 4072, before the migration as well as after. So this is a latent
defect made unrepresentable rather than a live one repaired: the construct
that produces it is a variable interpolation, which no static scan can see,
and the only thing that ever kept these eighteen quiet was that nobody had
interpolated one yet.

**And the design question it forced.** ``EnvelopeName`` is not "the base for
a vocabulary that reaches the envelope". It gives up member identity so a
copy or a pickle hands back a plain string, and that is only owed where a
LIVE member is placed into the envelope structure. Measured on produced
envelopes: exactly four do — ``Block`` as a key, ``Layer`` / ``Provenance`` /
``Severity`` as values — and all four already had it. The other eighteen
needed the smaller thing, ``StrEnum``, which changes what a member PRINTS as
and nothing else: identity survives, ``json.dumps`` is byte-identical, and
the suite did not move.
"""
from __future__ import annotations

import copy
import enum
import json
import re

import numpy as np
import pandas as pd
import pytest

import themis
from themis.types import EnvelopeName
from tests.test_vocabulary_reach import _python_vocabularies
from tests.test_no_sentence_reaches_the_reader_in_the_wrong_language import (
    _sweep,
)

VOCABULARIES = _python_vocabularies()


def _words(cls) -> list:
    return [m for m in cls if isinstance(m.value, str)]


# --- the rule -----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(VOCABULARIES))
def test_a_member_prints_as_its_value_however_it_is_printed(name):
    """Three spellings of the same mistake, because a producer reaches for
    whichever is nearest: ``str()`` in a join, ``{x}`` in an f-string, ``%s``
    in a log line. A base that fixes one and not the others would be a rule
    that holds until someone reaches for a different one."""
    cls = VOCABULARIES[name]
    for member in _words(cls):
        assert str(member) == member.value, name
        assert f"{member}" == member.value, name
        assert "%s" % member == member.value, name


def test_the_rule_has_a_denominator():
    """A rule over zero vocabularies passes by saying nothing. The walk is
    the package's own — ``Enum.__subclasses__`` rather than a list of base
    names, so a nineteenth declared tomorrow is inside the question."""
    assert len(VOCABULARIES) >= 30, sorted(VOCABULARIES)
    assert sum(len(_words(c)) for c in VOCABULARIES.values()) >= 200


def test_the_rule_says_no_to_the_shape_it_replaced():
    """The construct itself, so the criterion is shown discriminating rather
    than asserted to."""
    class Stale(str, enum.Enum):
        LOUD = "loud"

    assert Stale.LOUD == "loud"                 # equal, and still
    assert str(Stale.LOUD) == "Stale.LOUD"      # printing its own address
    assert f"{Stale.LOUD}" == "Stale.LOUD"


# --- what the migration deliberately did NOT change ---------------------------


@pytest.mark.parametrize("name", sorted(VOCABULARIES))
def test_a_member_that_is_not_an_envelope_name_keeps_its_identity(name):
    """``StrEnum`` and ``EnvelopeName`` answer different questions, and this
    is the one the smaller base does not touch. Giving up ``is`` is the price
    of leaving the process as data; a vocabulary that never does should not
    be paying it, and 155 ``is`` comparisons across the package and its tests
    rest on that."""
    cls = VOCABULARIES[name]
    if issubclass(cls, EnvelopeName):
        pytest.skip("gives up identity on purpose — #382 checks that")
    for member in _words(cls):
        assert copy.deepcopy(member) is member, name
        assert member is cls(member.value), name


@pytest.mark.parametrize("name", sorted(VOCABULARIES))
def test_what_json_writes_did_not_move(name):
    """The envelope is where these end up and the migration must be invisible
    there — a ``str`` subclass has always serialised as its value, which is
    also why nothing downstream noticed the defect."""
    for member in _words(VOCABULARIES[name]):
        assert json.dumps(member) == json.dumps(member.value), name


# --- and the question that decides which base a vocabulary owes ---------------


def _envelopes() -> list[tuple[str, dict]]:
    rng = np.random.default_rng(4)
    n = 2000
    z = rng.normal(size=n)
    x = rng.random(n) < 1 / (1 + np.exp(-3.2 * z))
    y = rng.random(n) < np.clip(0.2 + 0.3 * x + 0.25 * (z > 0), 0, 1)
    frame = pd.DataFrame({"x": x, "y": y, "z": z})

    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "u"}]}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "scale": "continuous"},
            {"kind": "cause", "from": atom("z"), "to": atom("x")},
            {"kind": "cause", "from": atom("z"), "to": atom("y")},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": []}},
        ],
    }
    return [(est, themis.estimate(program, frame, ci_bootstrap=0,
                                  ate_estimator=est))
            for est in ("gformula", "ipw", "aipw", "tmle")]


def _live_members(node, path=()) -> list[tuple[str, enum.Enum]]:
    out: list[tuple[str, enum.Enum]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, enum.Enum):
                out.append((".".join(map(str, path)) + " <key>", k))
            out += _live_members(v, path + (str(k),))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            out += _live_members(v, path + (str(i),))
    elif isinstance(node, enum.Enum):
        out.append((".".join(map(str, path)), node))
    return out


def test_a_live_member_left_in_an_envelope_is_an_envelope_name():
    """The rule, stated where it can fire.

    A member that reaches the envelope AS A MEMBER hands whoever copies or
    pickles that envelope a live registry object. ``EnvelopeName`` is the
    undertaking that it will not — and it is owed exactly here, not by every
    vocabulary a schema happens to name.
    """
    seen: dict[str, set[str]] = {}
    for label, out in _envelopes():
        for where, member in _live_members(out, (label,)):
            seen.setdefault(type(member).__name__, set()).add(where)
            assert isinstance(member, EnvelopeName), (
                f"{type(member).__name__} member sits in the envelope at "
                f"{where} as a live member, so a consumer that deepcopies "
                f"the answer receives the registry with it")
    # Not vacuous, and the four are named so a fifth is a visible change.
    assert set(seen) == {"Block", "Layer", "Provenance", "Severity"}, seen


def test_the_envelope_walk_would_see_a_member_that_should_not_be_there():
    """The criterion discriminates: a vocabulary that has NOT given up
    identity, placed where those four sit, is found by the same walk."""
    from themis.types import QueryKind

    planted = {"results": [{"status": QueryKind.EFFECT}]}
    found = _live_members(planted)
    assert [w for w, _ in found] == ["results.0.status"]
    assert not isinstance(found[0][1], EnvelopeName)


# --- and what a reader was actually handed ------------------------------------


_ADDRESS = re.compile(
    r"\b(" + "|".join(sorted({c.__name__ for c in VOCABULARIES.values()}))
    + r")\.[A-Z][A-Z0-9_]*\b")


def test_no_string_the_kernel_emits_carries_a_vocabulary_address():
    """The reader-facing half, over the corpus that already exists for the
    language rule. It was 0 of 4072 before this too — the eighteen were
    loaded rather than fired — which is why this is written as the gate that
    keeps it 0 rather than as the repair of something measured broken."""
    rows = _sweep()
    assert len(rows) >= 3000, len(rows)
    carried = [(src, path, text) for src, path, text in rows
               if _ADDRESS.search(text)]
    assert not carried, carried[:5]


def test_the_address_pattern_recognises_one():
    """Otherwise the check above passes by matching nothing."""
    assert _ADDRESS.search("方法 ResultStatus.NUMERICALLY_SOLVED 已解出")
    assert _ADDRESS.search("QueryKind.EFFECT")
    assert not _ADDRESS.search("numerically_solved")
    assert not _ADDRESS.search("ResultStatus")
