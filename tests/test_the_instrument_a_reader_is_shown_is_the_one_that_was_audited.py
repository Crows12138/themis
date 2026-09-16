"""The instrument a reader is shown is the one the criterion was checked on.

An IV answer states one sentence — use Z as an instrument, valid given W,
and you still owe monotonicity or linearity — and states it in two places:
``extensions.identification``, the human surface, and
``extensions.iv_identification``, which the report routes for this strategy.
The derivation behind them states it a third time, in its own inputs.

Only the third was audited. ``verify_identification_pattern`` returned
immediately on ``pattern == "instrumental_variable"``, saying beside itself
that these were "premises the iv_criterion derivation rule already
re-derives" — a true sentence about the derivation and an empty one about
the block, because the derivation carries its OWN copy of the instrument and
nothing related the two. Measured against the public door rather than
against the source: an envelope naming the OUTCOME as its instrument passed
``themis.verify``, while the identical edit to the derivation was refused
with "x, y, and instrument must be distinct".

What is pinned here:

- every field of both blocks is re-derived from the graph, not read;
- each block is re-derived on ITS OWN fields, so neither is audited only
  through the other;
- and then the two are held equal, because passing is not agreeing — a
  graph with two valid instruments lets both blocks pass alone while the
  reader is shown one and the number came from the other;
- a genuinely different valid instrument, named consistently in both, is a
  different honest answer and is accepted. The rule is about divergence,
  not about which instrument the producer prefers.

WHAT IS NOT RE-DERIVED, and why. ``alternatives_count`` says how many other
valid (Z, W) pairs the structural search found, and the search that produces
it caps |W| at three and keeps only subset-minimal W per instrument. Those
are the producer's search parameters, not a theorem, so a verifier that
recounted would either transcribe them — agreeing by construction, which is
what an independent re-derivation is defined against — or pick its own and
refuse honest answers. The count stays the producer's word; the instrument
it counts alternatives to does not.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.kernel import _premises_of
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_iv_surfaces


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program(nodes, edges, latent=()):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in nodes]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "identify",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _atom("y"),
        "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


#: One instrument. The latent edge is what takes the back door away and
#: sends the route to IV in the first place.
ONE_INSTRUMENT = _program(
    ["z", "x", "y"], [("z", "x"), ("x", "y")], latent=[("x", "y")])

#: Two instruments, both valid. The graph where satisfying the criterion
#: and agreeing come apart.
TWO_INSTRUMENTS = _program(
    ["z1", "z2", "x", "y"], [("z1", "x"), ("z2", "x"), ("x", "y")],
    latent=[("x", "y")])

#: ``w`` moves the treatment and also reaches the outcome directly, so it
#: passes relevance and fails exclusion. ``iso`` reaches the treatment only
#: through the outcome, which is a collider on that path, so it fails both.
#: The two halves of the criterion, separated.
LEAKY = _program(
    ["z", "w", "iso", "x", "y"],
    [("z", "x"), ("w", "x"), ("w", "y"), ("iso", "y"), ("x", "y")],
    latent=[("x", "y")])


def _run(program):
    result = themis.run(program)["results"][0]
    extensions = result.get("extensions") or {}
    assert "identification" in extensions, extensions
    assert "iv_identification" in extensions, extensions
    return result


def _refuses(program, result, fragment):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


# ---------------------------------------------------------------- the honest
# answer, which every case below is an edit of


def test_an_untouched_iv_answer_passes():
    themis.verify(ONE_INSTRUMENT, _run(ONE_INSTRUMENT))


def test_both_blocks_carry_the_same_sentence():
    extensions = _run(ONE_INSTRUMENT)["extensions"]
    surface, source = (extensions["identification"],
                       extensions["iv_identification"])
    assert surface["pattern"] == "instrumental_variable"
    assert source["strategy"] == "iv"
    for field in ("instrument", "conditioning", "required_assumption"):
        assert surface[field] == source[field]


# --------------------------------------------- re-derived, block by block


@pytest.mark.parametrize("block", ["identification", "iv_identification"])
def test_naming_the_outcome_as_the_instrument_is_refused(block):
    """The edit the derivation rule already refused, made where a reader
    reads. Both blocks, because auditing one and trusting the other to
    match leaves the second reachable and re-derived by nobody."""
    result = _run(ONE_INSTRUMENT)
    result["extensions"][block]["instrument"] = "y(u)"
    _refuses(ONE_INSTRUMENT, result, "which is the outcome")


@pytest.mark.parametrize("block", ["identification", "iv_identification"])
def test_naming_the_treatment_as_the_instrument_is_refused(block):
    result = _run(ONE_INSTRUMENT)
    result["extensions"][block]["instrument"] = "x(u)"
    _refuses(ONE_INSTRUMENT, result, "which is the treatment")


@pytest.mark.parametrize("block", ["identification", "iv_identification"])
def test_conditioning_on_the_outcome_is_refused(block):
    """W is the set the instrument is valid GIVEN. A set holding the
    outcome is not a set anything is valid given."""
    result = _run(ONE_INSTRUMENT)
    result["extensions"][block]["conditioning"] = ["y(u)"]
    _refuses(ONE_INSTRUMENT, result, "disjoint from the treatment")


@pytest.mark.parametrize("name,failing", [
    ("w(u)", "IV2+IV3 exclusion=False"),
    ("iso(u)", "IV1 relevance=False"),
])
def test_an_instrument_the_criterion_rejects_is_refused(name, failing):
    """Which half failed is in the message, because the two are different
    complaints: a relevance failure names something that moves nothing, an
    exclusion failure names something with its own road to the outcome."""
    result = _run(LEAKY)
    for key in ("identification", "iv_identification"):
        result["extensions"][key]["instrument"] = name
    _refuses(LEAKY, result, failing)


def test_an_instrument_that_is_not_in_the_graph_is_refused():
    """A block may name only nodes."""
    result = _run(ONE_INSTRUMENT)
    for key in ("identification", "iv_identification"):
        result["extensions"][key]["instrument"] = "not_a_node(u)"
    _refuses(ONE_INSTRUMENT, result, "not a node in the graph")


def test_a_surface_that_names_no_instrument_at_all_is_refused():
    result = _run(ONE_INSTRUMENT)
    del result["extensions"]["identification"]["instrument"]
    _refuses(ONE_INSTRUMENT, result, "names no instrument")


# ------------------------------------------------ and then held together


def test_the_surface_swapped_to_the_other_valid_instrument_is_refused():
    """The case a criterion re-derivation alone cannot catch: both blocks
    satisfy it, and they disagree."""
    result = _run(TWO_INSTRUMENTS)
    shown = result["extensions"]["identification"]["instrument"]
    other = "z2(u)" if shown == "z1(u)" else "z1(u)"
    result["extensions"]["identification"]["instrument"] = other
    _refuses(TWO_INSTRUMENTS, result, "while the block it copies holds")


def test_the_same_swap_made_in_both_blocks_is_a_different_honest_answer():
    """Not a tamper. ``z2`` is a valid instrument, and an answer that
    names it in both places is one this graph supports. A rule that
    refused here would be pinning the producer's preference, not the
    reader's sentence."""
    result = _run(TWO_INSTRUMENTS)
    shown = result["extensions"]["identification"]["instrument"]
    other = "z2(u)" if shown == "z1(u)" else "z1(u)"
    for key in ("identification", "iv_identification"):
        result["extensions"][key]["instrument"] = other
    themis.verify(TWO_INSTRUMENTS, result)


def test_a_premise_swapped_on_one_surface_only_is_refused():
    """``required_assumption`` is the one field of the three no GRAPH can
    settle. Which premise a route owes is a fact about which estimator it
    ran, and the derivation records that — so through the whole door the
    swapped copy is refused as naming a premise the chain did not settle,
    which is the sentence a reader gets, and every other copy on the
    envelope is held the same way.

    What this module adds is that the two copies are one statement, and
    that is asked of it on its own: the chain answers first through the
    door, and the copy check is what still holds the two together where a
    chain settles nothing about an instrument.

    The swap is to another PREMISE, not to an invented word. Since #544 the
    contract enumerates this set, so an invented one is refused a rule
    earlier and would leave the two copies untested — and a real premise on
    one surface only is the sharper forgery anyway.
    """
    result = _run(ONE_INSTRUMENT)
    surface = result["extensions"]["identification"]["required_assumption"]
    other = next(p for p in ("linear_simultaneous_system",
                             "monotonicity_as_declared",
                             "monotonicity_or_linearity")
                 if p != surface["token"])
    result["extensions"]["identification"]["required_assumption"] = dict(
        surface, token=other)
    _refuses(ONE_INSTRUMENT, result, "the derivation it ran settles")

    _ast, _prog, _query, context = _premises_of(ONE_INSTRUMENT, result)
    with pytest.raises(VerificationError, match="required_assumption="):
        verify_iv_surfaces(
            result["extensions"]["identification"],
            result["extensions"]["iv_identification"],
            context.graph, context.bidirected, context.query)


def test_deleting_the_block_the_surface_copies_is_refused():
    """Silence on the source is not agreement. The producer writes both
    together, so a surface with nothing behind it is a divergence in the
    one direction an equality check would otherwise miss."""
    result = _run(ONE_INSTRUMENT)
    del result["extensions"]["iv_identification"]
    _refuses(ONE_INSTRUMENT, result, "the block it is copied from is absent")


# ------------------------------------------------------ the other patterns


def test_a_back_door_answer_still_verifies():
    """The IV branch was moved to where the graph is already decoded, so
    the three patterns that were always re-derived are exercised here."""
    program = _program(["z", "x", "y"],
                       [("z", "x"), ("z", "y"), ("x", "y")])
    result = themis.run(program)["results"][0]
    block = (result.get("extensions") or {}).get("identification")
    assert block and block["pattern"] == "backdoor", block
    themis.verify(program, result)
    result["extensions"]["identification"]["adjustment_set"] = []
    _refuses(program, result, "does not satisfy the back-door criterion")
