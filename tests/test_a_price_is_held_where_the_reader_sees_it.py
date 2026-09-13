"""A figure held where it was computed and free where it was shown.

``extensions.counterfactual_cell`` is the reader's copy of a block that
also sits under ``numeric_estimate``. Both carry the same budget, and the
figure in it is the most actionable thing this system prints: go and
recruit 160,000 more subjects. Set that number to anything at all in the
copy and every door that reads the envelope said yes — 0 of 12. Set it in
the original and two refused. Same number, same envelope, one key apart.

Neither the identity nor the copy-comparison was holding it. The copy
rule does not cover the pair, and the identity — the only check that
could be made from the envelope alone — never reached, because
``verify_envelope_arithmetic`` walked ``numeric_estimate`` and returned
when there was none.

The walk was carrying two claims that do not have the same scope:

    an identity  a budget's three figures equal what the interval and
                 the sample beside them give. Closed on the envelope's
                 own numbers, so it is true or false anywhere.

    an absence   an interval with no budget means an endpoint is missing
                 or the width is zero. Closed on nothing — it reads a
                 producer's promise, and reaches as far as that producer
                 writes.

Read off one traversal, the narrower claim's precondition became the
wider one's boundary. The producer had already written down the belief
the envelope was held under — "the verifier that prices these has walked
the whole envelope since it was written" — and the two sides had drifted
without either noticing, because nothing asked.

So each claim is asked at its own scope, and the scope of the narrow one
is written down with the promise it rests on. Both sides measured, and
the second is the one that decides: the identity from the root refuses
none of the 243 answer shapes; the absence question from the root refuses
20 of them, every one a derivation step's inputs or a bounds row — an
interval nobody promised to price. A rule that asked those would be worse
than the hole it closed.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier import verify_envelope_arithmetic
from themis.verifier.envelope_arithmetic_rules import _BUDGET_IS_PROMISED
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _budgets(node, path=()):
    """Every block carrying a budget, with the path that reached it."""
    if isinstance(node, dict):
        if isinstance(node.get("precision_budget"), dict):
            yield ".".join(path), node
        for key, value in node.items():
            yield from _budgets(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _budgets(value, path + (f"[{index}]",))


#: Shapes carrying a priced block OUTSIDE the promised subtree — the ones
#: the old walk could not see. Read off the snapshot, so the witnesses
#: below are about answers this system actually produces.
SHOWN_ELSEWHERE = sorted({
    name for name, pair in SHAPES.items()
    for where, _ in _budgets(pair["result"])
    if not where.startswith(_BUDGET_IS_PROMISED)
})


# ------------------------------------------------- the hole, and its absence


def test_there_is_a_priced_block_outside_the_promised_subtree():
    """The denominator. Every witness below is about a budget the narrow
    walk could not reach, so a corpus that stopped carrying one would make
    them pass by having nothing to ask."""
    assert SHOWN_ELSEWHERE, (
        "no answer shape carries a budget outside "
        f"{_BUDGET_IS_PROMISED}; the witnesses below would be vacuous")


@pytest.mark.parametrize("name", SHOWN_ELSEWHERE)
@pytest.mark.parametrize("leaf", ["current_ci_half_width", "n_to_halve_ci"])
def test_a_figure_a_reader_is_shown_cannot_be_moved(name, leaf):
    """The regression. Before the split every one of these was accepted."""
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    moved = 0
    for where, node in _budgets(result):
        if where.startswith(_BUDGET_IS_PROMISED) or leaf not in \
                node["precision_budget"]:
            continue
        node["precision_budget"][leaf] = 999950
        moved += 1
    if not moved:
        pytest.skip(f"no {leaf} outside {_BUDGET_IS_PROMISED} on this shape")
    with pytest.raises(VerificationError):
        the_door_for(result)(pair["program"], result)


@pytest.mark.parametrize("name", SHOWN_ELSEWHERE)
def test_the_answer_each_forgery_was_made_from_is_honest(name):
    """The other side of every row above: the figure as the producer wrote
    it is accepted, so what the forgery meets is the forgery."""
    pair = SHAPES[name]
    the_door_for(pair["result"])(pair["program"], pair["result"])


def test_the_identity_is_put_wherever_a_budget_is_found():
    """Not at a list of places: a block under a name nobody has written
    arrives on its own, wherever on the envelope it is put."""
    honest = {"ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5,
              "precision_budget": {"current_ci_half_width": 0.4,
                                   "relative_width": 0.8}}
    for where in ("extensions", "a_key_nobody_has_written_yet"):
        verify_envelope_arithmetic({
            "numeric_estimate": {"sample_size": 400},
            where: {"a_block": copy.deepcopy(honest)}})
        bent = copy.deepcopy(honest)
        bent["precision_budget"]["current_ci_half_width"] = 0.9
        with pytest.raises(VerificationError, match="producer's word twice"):
            verify_envelope_arithmetic({
                "numeric_estimate": {"sample_size": 400},
                where: {"a_block": bent}})


# ------------------------------------ and the absence stays where it is owed


@pytest.mark.parametrize("where,payload", [
    ("derivation",
     {"steps": [{"inputs": {"ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5}}]}),
    ("bounds_results", [{"ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5}]),
    ("extensions", {"a_block": {"ci_lower": 0.1, "ci_upper": 0.9,
                                "point": 0.5}}),
])
def test_an_unpriced_interval_outside_the_promise_is_not_asked_why(
        where, payload):
    """The false-positive side, and the reason the scope is not simply the
    whole envelope. A derivation step records what an estimator was handed
    and a bounds row states a range no sample narrows; neither was ever
    priced, and asking them would refuse twenty honest answers."""
    verify_envelope_arithmetic({
        "numeric_estimate": {"sample_size": 400}, where: payload})


def test_an_unpriced_interval_inside_the_promise_still_is():
    """And the side that would go quiet if the split were made by deleting
    the absence claim rather than by scoping it."""
    with pytest.raises(VerificationError, match="no precision_budget"):
        verify_envelope_arithmetic({"numeric_estimate": {
            "sample_size": 400,
            "a_block_nobody_has_written_yet": {
                "ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5}}})


# ------------------------------------------------- and the promise is pinned


def test_the_promised_subtree_is_the_one_the_producer_prices():
    """The two halves of one fact, in two modules that must not import each
    other. The verifier reads a missing budget as a statement only across
    the subtree the producer walks; if the producer's single call site
    starts reading a different key off the result, the belief the verifier
    holds the envelope under has changed and this is where it shows.
    """
    import themis.estimation.dispatch as dispatch

    tree = ast.parse(
        pathlib.Path(inspect.getsourcefile(dispatch)).read_text(
            encoding="utf-8"))
    # The one call site, which a sibling test pins to this function; read
    # inside it and not over the module, where eleven thousand lines assign
    # to the same short name for other reasons.
    door = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "_estimate_program")
    call = next(node for node in ast.walk(door)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_attach_precision_budget")
    # ``estimate = result.get("numeric_estimate")`` — the assignment that
    # feeds the call, found by the name the call is given.
    fed = call.args[0].id
    priced = {node.value.args[0].value
              for node in ast.walk(door)
              if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == fed
                      for t in node.targets)
              and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and node.value.func.attr == "get"
              and node.value.args
              and isinstance(node.value.args[0], ast.Constant)}
    assert priced == set(_BUDGET_IS_PROMISED), (
        f"the producer prices {sorted(priced)} and the verifier reads an "
        f"absence as a statement across {sorted(_BUDGET_IS_PROMISED)}")
