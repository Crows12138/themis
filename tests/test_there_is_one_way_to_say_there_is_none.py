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

THE DENOMINATOR WAS ONE FILE OUT OF THIRTEEN, AND NOT ON PURPOSE. Everything
above is a statement about contracts; what ran was a statement about
``query_result.schema.json``, because the walk it is built on held its
document in a module constant. Nineteen key paths in five other shipped
documents sat in the forbidden shape, unasked (#429) — the kb query and result
(twelve, though nine of them are three keys reached by three ``$ref`` routes),
a derivation step's id, the observed factual target in two documents, and the
verification context's theta.

What the widening cost, per key, was reading its producer. Eleven write under
``if x is not None``, so the null branch was never produced and comes off the
type. One — ``theta`` — is always written and carries null when there is none,
so it becomes required. Both are the same edit in opposite directions: say the
spelling the producer already uses. That is why a rule about declarations can
be widened without touching a line of behaviour, and also why it was worth
widening: what was unchecked was not the code, it was whether the code and the
contract still agree.
"""
from __future__ import annotations

import json

import pytest

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
    # absent: the discrete regime ran, and there is no equation to penalise
    # null:   the bridge regime ran and NOBODY named the penalty — which the
    #         reader is owed, because it is the difference between a lever
    #         they moved and one they did not know they had.
    #         The bridge's own span is the anchor because it is the field
    #         that says this bridge was declared at all, and the pair is
    #         mutual: a penalty with no sieve penalises nothing. One line per
    #         bridge, because each carries its own λ over its own operator
    #         and a run may have a caller's number on one and nobody's on the
    #         other.
    "extensions.proximal_estimand.outcome_bridge_ridge":
        "outcome_bridge_span_terms",
    "extensions.proximal_estimand.treatment_bridge_ridge":
        "treatment_bridge_span_terms",
}

#: The size of the walk, per document. A walk that quietly stops early — at a
#: ``$ref``, at the depth cap — passes every question below vacuously, and a
#: gate that cannot fail reads exactly like a clean one.
#:
#: Per document rather than one total, because a total is a floor two
#: documents can hold up for each other: one subtree collapsing while another
#: grows leaves the sum alone. And every shipped document has a row, so a new
#: schema cannot join the build without someone entering it here — the glob
#: SEES it, this table is what makes it be ANSWERED for.
#:
#: Four of these rose when the walk began following references out of the
#: document (#431). Nothing was added to those contracts: the keys were always
#: theirs, behind a reference the walk used to treat as the end of the
#: subject, so this rule had been answering for less of them than it read as
#: answering for. verification_context is the control — it lands on exactly
#: the number it held before three of its shapes moved to one record, which
#: is what says that move took nothing out of the contract.
REACHED: dict[str, int] = {
    "atom.schema.json": 0,  # a bare $defs library; nothing declares a key
    "derivation.schema.json": 256,
    "kb_query.schema.json": 13,
    "kb_result.schema.json": 41,
    "kernel_ast.schema.json": 399,
    "lagged_discovery.schema.json": 37,
    "markov_blanket.schema.json": 29,
    "notears_fit.schema.json": 26,
    "orientation_common.schema.json": 0,  # shared $defs, same as atom
    "orientation_ledger_export.schema.json": 105,
    "orientation_propagation.schema.json": 24,
    "orientation_question_set.schema.json": 28,
    "orientation_session.schema.json": 81,
    "query_result.schema.json": 2146,
    "verification_context.schema.json": 232,
}


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


def test_every_shipped_document_is_answered_for():
    """The glob finds the documents; this table says they were looked at.

    Two halves of one question, and the reason they are separate: a glob that
    finds a new file puts it in the denominator silently, which is how a
    document joins a rule while nobody decides that it should.
    """
    assert {d.name for d in schema_walk.shipped()} == set(REACHED), (
        "a shipped schema has no row here — the walk sees it, and nobody has "
        "said what it should reach"
    )


@pytest.mark.parametrize("doc", schema_walk.shipped(), ids=lambda d: d.name)
def test_the_walk_still_reaches_the_whole_contract(doc):
    reached = sum(1 for _ in doc.walk())
    assert reached >= REACHED[doc.name], (
        f"{doc.name}: the walk reaches {reached} declared keys, was "
        f"{REACHED[doc.name]}; a walk that shrank is a denominator that shrank"
    )


def test_a_key_that_keeps_both_spellings_has_a_sibling_that_tells_them_apart():
    found: dict[str, str] = {}
    for doc in schema_walk.shipped():
        for path, sub, container in doc.walk():
            name = path[-1]
            if name in (container.get("required") or ()):
                continue
            if not schema_walk.nullable(sub):
                continue
            anchors = _anchors_of(name, container)
            assert anchors, (
                f"{doc.name}: {'.'.join(path)} can be omitted AND set to null, "
                f"which are two ways to say the same nothing unless a "
                f"non-nullable sibling says which is which"
            )
            found[".".join(path)] = anchors[0]
    assert found == ANCHORED


def test_the_rule_sees_a_key_in_the_forbidden_shape_in_any_document():
    """The counterexample, in the document that used to be out of reach.

    Built on a copy of a shipped schema that is NOT the result contract,
    because "the rule runs" and "the rule runs here" are different claims and
    the second is the one #429 was about: for as long as the walk held one
    document, the check below passed on every schema by never reading it.
    """
    doc = schema_walk.named("orientation_propagation.schema.json")
    clean = dict(doc.spec)
    assert not _ambiguous(schema_walk.Document(doc.name, clean))

    spoiled = json.loads(json.dumps(clean))
    spoiled["properties"]["note"] = {"type": ["string", "null"]}
    spoiled["required"] = [r for r in spoiled.get("required", ()) if r != "note"]
    assert _ambiguous(schema_walk.Document(doc.name, spoiled)) == ["note"]


def _ambiguous(doc) -> list[str]:
    return [".".join(path) for path, sub, container in doc.walk()
            if path[-1] not in (container.get("required") or ())
            and schema_walk.nullable(sub)
            and not _anchors_of(path[-1], container)]
