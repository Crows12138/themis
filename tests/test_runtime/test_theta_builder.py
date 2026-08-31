"""Unit tests for theta_builder."""
from __future__ import annotations

import pytest

from themis import language
from themis.runtime.theta_builder import (
    ConflictingThetaEntry,
    NonLiteralProbabilityValue,
    build_theta,
)
from themis.runtime.theta_words import Half, Refuses
from themis.types import (
    Atom,
    ConstTerm,
    ProbabilityStatement,
    ValuedAtom,
    VarRef,
)


def atom(pred: str, obj: str = "alice") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def test_probability_statement_becomes_theta_entry():
    y, x = atom("y"), atom("x")
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.3,
    )
    theta = build_theta((stmt,))
    assert len(theta.entries) == 1
    key = next(iter(theta.entries))
    assert key.target_atom == y
    assert key.target_value is True
    assert key.given == frozenset({(x, True)})
    assert theta.entries[key] == 0.3


def test_empty_given_produces_unconditional_entry():
    z = atom("z")
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=z, value=False),
        given=(),
        value=0.6,
    )
    theta = build_theta((stmt,))
    (key,) = theta.entries
    assert key.given == frozenset()
    assert theta.entries[key] == 0.6


def test_non_probability_statements_are_skipped():
    from themis.types import CauseStatement, ObservationStatement

    stmts = (
        CauseStatement(from_atom=atom("a"), to_atom=atom("b")),
        ObservationStatement(atom=atom("c"), value=True),
    )
    theta = build_theta(stmts)
    assert theta.entries == {}


def test_multiple_distinct_statements_accumulate():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.7,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=False),),
        value=0.2,
    )
    theta = build_theta((s1, s2))
    assert len(theta.entries) == 2


def test_duplicate_key_with_different_value_raises():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.7,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.9,
    )
    with pytest.raises(ConflictingThetaEntry):
        build_theta((s1, s2))


def test_duplicate_key_with_same_value_is_idempotent():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.5,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.5,
    )
    theta = build_theta((s1, s2))
    assert len(theta.entries) == 1


# A probability statement's value has to be a concrete literal. ``ValuedAtom``
# is shared with the formula AST, where a value may be absent or bound by an
# enclosing sum, so both non-literal shapes can reach this builder.
NON_LITERALS = [
    pytest.param(None, id="unbound"),
    pytest.param(VarRef(name="v"), id="sum-bound"),
]


@pytest.mark.parametrize("non_literal", NON_LITERALS)
def test_a_non_literal_target_value_is_refused(non_literal):
    """This branch has no other way to be reached, which is exactly why
    it needs a test.

    The JSON door cannot get here — ``atom.schema.json`` §groundedAtom
    makes a probability statement's value required and literal — so the
    guard is live only for callers who build the dataclass directly, as
    the runtime and these tests do. To anyone reading the module cold it
    looks unreachable, and unreachable-looking guards get deleted.

    What it stops is not an exception, it is a key. The value goes
    straight into ``ProbabilityKey.target_value`` and into the atom's
    value domain, so an unbound one used to produce an entry keyed on
    ``None`` and a domain of ``(None,)``: a theta that looks well formed,
    that no lookup can ever hit, and that never says why.
    """
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=atom("x"), value=non_literal),
        given=(),
        value=0.3,
    )

    with pytest.raises(NonLiteralProbabilityValue) as caught:
        build_theta((stmt,))
    # Which HALF went wrong is the point of the message, and it is a word
    # rather than the site's spelling of one: searching the rendered
    # sentence for "target" could only ever succeed in one language.
    assert caught.value.species is Refuses.A_VALUE_IS_NOT_A_LITERAL
    assert caught.value.words["half"]["token"] == str(Half.TARGET)
    assert caught.value.said["predicate"] == "x"


@pytest.mark.parametrize("non_literal", NON_LITERALS)
def test_a_non_literal_given_value_is_refused(non_literal):
    """The conditioning side is the same contract and needs the same
    check, said separately so the message can name the side.

    A given atom's value is half of the frozenset that makes the key, so
    a non-literal there produces a key that is unmatchable in the same
    way while the target reads perfectly well — the harder half to spot
    by eye, and the one a check written only for ``stmt.target`` would
    let through.
    """
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=atom("y"), value=True),
        given=(ValuedAtom(atom=atom("x"), value=non_literal),),
        value=0.3,
    )

    with pytest.raises(NonLiteralProbabilityValue) as caught:
        build_theta((stmt,))
    assert caught.value.words["half"]["token"] == str(Half.GIVEN)
    assert caught.value.said["predicate"] == "x"
    # And the whole sentence really does reach two readers, which the
    # message it replaced could not: the half is a word inside it.
    zh, en = (language.assemble(
        Refuses.A_VALUE_IS_NOT_A_LITERAL.words,
        caught.value.said, caught.value.words, lang) for lang in ("zh", "en"))
    assert zh != en
    assert language.spoke(language.state(Half.GIVEN), "zh") in zh
    assert language.spoke(language.state(Half.GIVEN), "en") in en
