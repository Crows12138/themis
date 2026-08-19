"""How a key says "there is none", and why it may only say it one way.

The contract says what values a key may take. It never said how ABSENCE is
spelled, so each producer chose per site, and a key that is both optional and
nullable ends up with two spellings for one fact.
``extensions.causation.pn.point`` is where that showed: the structural route
omitted it when monotonicity was not assumed — its docstring said the absence
was itself the information — and the data route wrote ``null`` into the same
field of the same block for the same reason. One path, two producers, two
conventions, and nothing that could report the disagreement, because both were
legal. Seventy-six declared keys were in that shape.

What it cost was two of everything downstream. The kernel cross-checks the
causation display copy against its derivation twice, and the structural check
asked whether the two sides agree on the key being THERE while the numeric one
asked whether the two values agree — one question, two conventions, two
checks. The schema needed an ``allOf`` to put ``required`` back on the
container where the key is always written. None of that was doing work that
one spelling would not have done for free.

So the rule goes on the contract rather than on the checks (#363:
unrepresentable beats detected). Three shapes each say "there is none" exactly
once:

  required + non-null      there is no such state; the key is always a value
  required + nullable      the state is said out loud, as null
  optional + non-null      the state is said by omission

The fourth is what this file forbids — with one exception, which measurement
forced and which is the interesting part. In ``numeric_estimate`` the absences
of ``point`` and of ``ci_lower`` turned out to be the SAME sixty results,
method for method: causation bounds, a counterfactual cell, a dose-response
curve, a joint contrast, a mediation decomposition — every method whose answer
is not a top-level point at all. There ``absent`` and ``null`` are not two
spellings of one fact, they are two facts: "this answer has no headline
number" and "it has one, and no interval around it". A key may keep both,
then, but only where the schema makes the two TELLABLE APART: it must sit in a
``dependentRequired`` cycle with a non-nullable sibling, whose presence answers
the first question while its own value answers the second. Without such an
anchor there is nothing to read the difference off, and then it is not a
difference.

WHY NOTHING ON THE READER SIDE CHANGED, AND WHY THAT IS THE POINT. Every
reader of these keys already asks ``.get(key)`` or ``!= null``, which answers
the same for both spellings. That is how the disagreement survived: it never
rendered anything wrong. What it cost was that the contract could not be
checked — and a producer that quietly stops writing a key looks, to a reader
defended against both, exactly like a route with nothing to say.

For the same reason the browser's ``types.ts`` is not held to this rule. It
declares a READ-side view, where ``field?: T | null`` says "I may not be given
this, and it may be null" — a defence, not a choice between two ways of
writing one fact. The rule binds producers, and the browser produces nothing.

WHAT THIS IS WORTH. The rule is checked on the declaration, not on the
traffic, so it is exactly as strong as the declaration is enforced: ``run()``
does not validate its own output, and a producer meets the schema only where
something calls ``verify()`` — the audit path, the web endpoint, and the test
modules that validate. A producer that starts writing null where the contract
says omit is caught wherever a result is audited, and nowhere else.
"""
from __future__ import annotations

from . import schema_walk

#: Every key that keeps both spellings, and the sibling that tells them apart.
#: A table rather than a derivation, so that adding a ``dependentRequired``
#: pair to quiet this gate has to be argued for in review instead of merely
#: passing.
ANCHORED: dict[str, str] = {
    # absent: this method's answer is not a top-level point at all
    # null:   it is, and no interval was computed
    "numeric_estimate.ci_lower": "point",
    "numeric_estimate.ci_upper": "point",
    # absent: not a doubly-robust estimator
    # null:   it is, and the analytic CI was skipped
    "numeric_estimate.std_error": "doubly_robust",
    # absent: the symbolic bounds were never numerically evaluated
    # null:   they were, and no outer band was computed
    "bounds_results.[].ci_lower": "lower_value",
    "bounds_results.[].ci_upper": "lower_value",
}

#: The size of the walk when this file was written. A walk that quietly stops
#: early — at a ``$ref``, at the depth cap — passes every question below
#: vacuously, and a gate that cannot fail reads exactly like a clean one.
REACHED = 1775


def _anchors_of(name: str, container: dict) -> list[str]:
    """Non-nullable siblings this key and its container require of each other.

    Mutual on purpose: ``a requires b`` alone would let the anchor go missing
    while the nullable key stays, and then its absence answers nothing.
    """
    dependent = container.get("dependentRequired") or {}
    props = container.get("properties") or {}
    return [
        sibling for sibling in dependent.get(name) or ()
        if not schema_walk.nullable(props.get(sibling) or {})
        and name in (dependent.get(sibling) or ())
    ]


def test_null_is_recognised_in_both_spellings_the_document_uses():
    """The predicate the gate rests on, on a shape rather than on traffic.

    ``null`` is written two ways here — inside ``type`` and as a ``oneOf``
    branch of its own — and reading only the first reports a key that CAN be
    null as one that cannot, which passes this file's questions by not seeing
    them. Nothing in the document is currently in the second shape AND
    optional, so no live key would notice the predicate losing that arm.
    """
    assert schema_walk.nullable({"type": ["number", "null"]})
    assert schema_walk.nullable(
        {"oneOf": [{"$ref": "#/$defs/dataGapReport"}, {"type": "null"}]})
    assert not schema_walk.nullable({"type": "number"})
    assert not schema_walk.nullable({"oneOf": [{"type": "number"}]})


def test_the_walk_still_reaches_the_whole_contract():
    reached = sum(1 for _ in schema_walk.walk(schema_walk.SCHEMA))
    assert reached >= REACHED, (
        f"the walk reaches {reached} declared keys, was {REACHED}; a walk that "
        f"shrank is a denominator that shrank"
    )


def test_a_key_that_keeps_both_spellings_has_a_sibling_that_tells_them_apart():
    found: dict[str, str] = {}
    for path, sub, container in schema_walk.walk(schema_walk.SCHEMA):
        name = path[-1]
        if name in (container.get("required") or ()):
            continue
        if not schema_walk.nullable(sub):
            continue
        anchors = _anchors_of(name, container)
        assert anchors, (
            f"{'.'.join(path)} can be omitted AND set to null, which are two "
            f"ways to say the same nothing unless a non-nullable sibling says "
            f"which is which"
        )
        found[".".join(path)] = anchors[0]
    assert found == ANCHORED
