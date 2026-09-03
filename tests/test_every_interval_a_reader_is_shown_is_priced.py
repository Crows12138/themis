"""Whether an interval could be re-derived was a fact about who wrote it.

A ``precision_budget`` is what makes an interval's endpoints checkable: the
half-width and the ratio to the point are arithmetic on the two endpoints,
so a rule can re-derive them and a lone edit to either endpoint stops
agreeing. The rule that does it has walked the whole envelope since it was
written — "wherever a budget appears, and not at a list of places it is
known to appear".

**The producer had not.** It priced intervals through four near-identical
functions — flat, curve, joint, decomposition — differing only in where they
looked and what the sibling estimate was called, and each route called
whichever one its author remembered. So a reader's interval was checkable
exactly when someone had thought of it. Measured end to end before this
file existed: ``decomposition.nde.ci_lower`` moved from 0.48 to 50.48 —
an interval running backwards, with its own point estimate outside it — and
``themis.verify`` accepted. The same for both four-way decompositions'
seven components each, both longitudinal blocks and every row of an
ordered dose's margin table. Where the same shape DID have a budget, the
same edit was refused, which is the asymmetry: not two kinds of interval,
two kinds of author.

A fifth variant would have been the fifth copy and the sixth hole. One walk
replaces them, and coverage becomes a fact about the envelope's shape on
both sides of the door.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests import partially_observed
from themis.estimation.dispatch import _ESTIMATE_NAMES as _PRODUCER_NAMES
from themis.verifier import verify_envelope_arithmetic
from themis.verifier.envelope_arithmetic_rules import (
    _ESTIMATE_NAMES as _VERIFIER_NAMES,
)
from themis.verifier.errors import VerificationError

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "themis" / "schemas" / "query_result.schema.json")
                    .read_text(encoding="utf-8"))
DEFS = SCHEMA.get("$defs", {})
SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))


def _intervals(node, path, seen):
    """Every object under ``numeric_estimate`` that declares an interval.

    Follows ``$ref`` once per definition: a shared component is one place
    in the schema and answering for it twice would say nothing new.
    """
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name not in seen:
            seen.add(name)
            yield from _intervals(DEFS.get(name, {}), path + [f"<{name}>"],
                                  seen)
        return
    props = node.get("properties")
    if isinstance(props, dict):
        if "ci_lower" in props and "ci_upper" in props:
            yield "/".join(path), props
        for key, value in props.items():
            yield from _intervals(value, path + [key], seen)
    for key in ("items", "then", "else"):
        if key in node:
            yield from _intervals(node[key], path, seen)
    for key in ("allOf", "anyOf", "oneOf"):
        for index, sub in enumerate(node.get(key, ())):
            yield from _intervals(sub, path + [f"{key}[{index}]"], seen)


DECLARED = list(_intervals(SCHEMA["properties"]["numeric_estimate"],
                           ["numeric_estimate"], set()))


# ============================================ the vocabulary, in two places


def test_the_two_vocabularies_are_one_vocabulary():
    """What a block calls the number its interval is around decides which
    sibling the producer prices against and which one the verifier re-derives
    the ratio from. The two must not import each other — that is what the
    verifier's independence means — so the list is restated, and pinned equal
    here. Measured when it was not: a margin priced against ``weight``
    reached a verifier that knew only ``point`` and ``effect``, and was
    refused as a share of nothing."""
    assert _PRODUCER_NAMES == _VERIFIER_NAMES


@pytest.mark.parametrize("where,props", DECLARED,
                         ids=[where for where, _ in DECLARED])
def test_no_interval_names_its_estimate_a_word_neither_side_knows(where,
                                                                 props):
    """The anti-drift half. A vocabulary of three words is safe only while
    nothing adds a fourth: a block whose estimate is called something else
    gets a budget priced against nothing, its ratio silently omitted, and
    its endpoints back to being held by no one. This fails on the day that
    word is added rather than on the day someone notices."""
    assert set(props) & set(_PRODUCER_NAMES), (
        f"{where} declares an interval and calls the number it is around "
        f"none of {_PRODUCER_NAMES}"
    )


@pytest.mark.parametrize("where,props", DECLARED,
                         ids=[where for where, _ in DECLARED])
def test_every_interval_the_schema_declares_has_a_slot_for_its_price(where,
                                                                     props):
    """The producer now prices by walking, so the set of places a budget can
    land is decided here rather than by a caller. A slot missing is a door
    that refuses an honest answer — which is how each of the ten added with
    this item was found."""
    assert "precision_budget" in props, (
        f"{where} declares an interval the producer will price and no slot "
        f"for the price"
    )


def test_the_schema_still_declares_intervals_to_ask_about():
    """A walk that finds nothing satisfies both parametrized tests in
    silence."""
    assert len(DECLARED) >= 15, len(DECLARED)


# ================================================ what a reader can rely on


@pytest.mark.parametrize("method,path", [
    ("mediation_joint_linear", ("decomposition", "nde")),
    ("mediation_joint_linear", ("decomposition", "te")),
    ("mediation_linear_imai", ("four_way_decomposition", "pie")),
    ("mediation_logit_imai", ("four_way_decomposition", "intmed")),
    ("longitudinal_gformula", ("longitudinal_gformula",)),
    ("longitudinal_ipw_msm", ("longitudinal_ipw_msm",)),
    ("iv_acr", ("acr_decomposition", "margins", 0)),
])
def test_an_interval_that_excludes_its_own_point_is_refused(method, path):
    """Every one of these was accepted. The edit is the same each time —
    push the lower endpoint past the upper — and what refuses it now is the
    half-width beside it, which no longer describes the interval it prices.
    """
    pair = SHAPES[method]
    bad = copy.deepcopy(pair["result"])
    node = bad["numeric_estimate"]
    for step in path:
        node = node[step]
    assert "precision_budget" in node, (
        f"{method}.{path} carries no budget, so this test would pass for "
        f"the wrong reason")
    node["ci_lower"] = node["ci_upper"] + 50.0
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], bad)


@pytest.mark.parametrize("method,path", [
    ("mediation_joint_linear", ("decomposition", "nie")),
    ("mediation_linear_imai", ("four_way_decomposition", "te")),
    ("longitudinal_gformula", ("longitudinal_gformula",)),
])
def test_widening_an_interval_is_refused_too(method, path):
    """The edit containment cannot see. An interval stretched outwards still
    holds its point and still runs the right way — measured across all
    forty-four shapes, ordering and containment are violated by none of them
    honestly and by this forgery either. The half-width is what notices."""
    pair = SHAPES[method]
    bad = copy.deepcopy(pair["result"])
    node = bad["numeric_estimate"]
    for step in path:
        node = node[step]
    node["ci_lower"] -= 10.0
    node["ci_upper"] += 10.0
    # Named at the rule, because the door may refuse a widened interval for
    # a second reason — the step that recorded the endpoints disagrees too —
    # and this item is about the first one existing at all.
    with pytest.raises(VerificationError, match="half_width"):
        verify_envelope_arithmetic(bad)
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], bad)


def test_a_route_that_declines_early_cannot_decline_the_price():
    """One walk is only one walk if every route reaches it.

    Replacing twenty-six per-route calls with a single pricing walk stopped
    coverage being a fact about which author was standing where. Written at
    the foot of a function with three exits, it became a fact about which
    route returned early instead: the missing-data recovery path returns
    above it — the columns it recovers from carry NaN, which the data
    contract forbids — so a recovered ATE reached a reader with two
    endpoints and no price. An unpriced interval is one whose endpoints
    nothing holds, and the corpus cannot notice because it carries no
    recovery row.

    So the routing is a function of its own and the walk is the epilogue an
    early return cannot reach past.
    """
    result = themis.estimate(partially_observed.program(),
                             partially_observed.frame())["results"][0]
    estimate = result["numeric_estimate"]
    assert estimate["ci_lower"] is not None
    assert "precision_budget" in estimate
    verify_envelope_arithmetic(result)

    widened = copy.deepcopy(result)
    node = widened["numeric_estimate"]
    node["ci_lower"] -= 10.0
    node["ci_upper"] += 10.0
    with pytest.raises(VerificationError, match="half_width"):
        verify_envelope_arithmetic(widened)


#: The shapes this file forges from — a reader's interval one level in, on
#: each of the four routes that had no budget beside it.
_FORGED_FROM = ("iv_acr", "longitudinal_gformula", "longitudinal_ipw_msm",
                "mediation_joint_linear", "mediation_linear_imai",
                "mediation_logit_imai")


@pytest.mark.parametrize("method", _FORGED_FROM)
def test_the_answer_each_forgery_was_made_from_is_honest(method):
    """First in intent even where it sits last. Asked of these six and not
    of all forty-four: the snapshot as a whole is
    :mod:`tests.test_every_answer_shape_is_asked_the_same_question`'s to
    answer for, and repeating that claim here would be a second copy of it
    rather than the local one these forgeries depend on."""
    themis.verify(SHAPES[method]["program"], SHAPES[method]["result"])
