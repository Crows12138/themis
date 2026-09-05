"""The variable is held; the VALUE beside it was not.

#580 made sure a skeleton sends a reader after a variable the problem
actually has. It says nothing about the literal written next to it:
``P(survival=42)`` names a real variable and asks for a number nobody can
come back with. Measured before this: 193 of 193 value sites accepted
``"not_a_value_anything_can_take"`` through both public doors.

TWO AUTHORITIES, AND NEITHER IS THE OTHER WRITTEN TWICE.

The DECLARED DOMAIN is outside the answer: the program says what levels
the variable has, and a value that is not one of them is unanswerable
whatever else the envelope says. It reaches 143 of the 193 sites, because
50 name a variable this problem declares no domain for — a graph written
entirely out of cause edges declares nothing while naming everything, and
there is then no authority to appeal to. That silence is stated and
exercised here rather than papered over: reading the missing domain off
the values the corpus happens to use would be taking the roster from the
answers it is meant to judge. Measured: 26 of those 50 ask for a value
the program has never written anywhere, so that roster would refuse
honest asks.

The ITEM'S OWN NAME is inside the answer and complete: ``parameter:P(y=
True|x=True,z=False)`` is the same ask as the skeleton beneath it,
rendered as the one string a reader looks it up by. It reproduces all 85
probability skeletons exactly, target pair and conditioning pairs both.

Each catches what the other cannot. Move a value alone and the name
refuses it; move the name with it and only the domain can still say the
level does not exist; swap the target with one of its own conditions and
only the name notices, because both variables are perfectly real and #580
is satisfied.
"""
from __future__ import annotations

import collections
import copy
import json
import pathlib
import re

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier.investigation_rules import (
    _check_the_values_it_asks_about_are_ones_the_variable_takes,
    _PAIRS_IN_A_KEY, _valued_atoms_of, declarations_of)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every place an item asks a reader to record one variable at one value:
#: (answer, request index, item index, "target" | "given", given index).
SITES = sorted(
    (name, ri, ii, which, gi)
    for name, pair in SHAPES.items()
    for ri, req in enumerate(
        (pair["result"] or {}).get("investigation_requests") or [])
    for ii, item in enumerate(req.get("items") or [])
    if isinstance(item.get("skeleton"), dict)
    for which, gi in (
        [("target", -1)]
        if isinstance(item["skeleton"].get("target"), dict)
        and "value" in item["skeleton"]["target"] else []
    ) + [
        ("given", g) for g, node in enumerate(item["skeleton"].get("given")
                                              or [])
        if isinstance(node, dict) and "value" in node
    ]
)

#: The parameter skeletons themselves, which is where the name is read.
SKELETONS = sorted(
    (name, ri, ii)
    for name, pair in SHAPES.items()
    for ri, req in enumerate(
        (pair["result"] or {}).get("investigation_requests") or [])
    for ii, item in enumerate(req.get("items") or [])
    if isinstance(item.get("skeleton"), dict)
    and item["skeleton"].get("kind") == "probability"
)


def _node(result, ri, ii, which, gi):
    skeleton = result["investigation_requests"][ri]["items"][ii]["skeleton"]
    return skeleton["target"] if which == "target" else skeleton["given"][gi]


def _declarations(name):
    _, program, _, _ = _premises_of(SHAPES[name]["program"],
                                    SHAPES[name]["result"])
    return declarations_of(program)


def _domain(name, ri, ii, which, gi):
    node = _node(SHAPES[name]["result"], ri, ii, which, gi)
    declaration = _declarations(name).get((node.get("atom") or {})
                                          .get("predicate"))
    return getattr(declaration, "domain", None) if declaration else None


def test_the_places_a_reader_is_asked_for_a_value():
    """The denominator, and the split that says where each rule speaks."""
    assert len(SITES) == 193, len(SITES)
    assert len(SKELETONS) == 85, len(SKELETONS)

    walked = sum(
        len(_valued_atoms_of(item["skeleton"], []))
        for pair in SHAPES.values()
        for req in (pair["result"] or {}).get("investigation_requests") or []
        for item in req.get("items") or []
        if isinstance(item.get("skeleton"), dict))
    assert walked == len(SITES), (walked, len(SITES))

    split: collections.Counter = collections.Counter()
    for name, ri, ii, which, gi in SITES:
        domain = _domain(name, ri, ii, which, gi)
        split["a domain to be held to" if domain else "no domain"] += 1
    assert split == {"a domain to be held to": 143, "no domain": 50}, split


@pytest.mark.parametrize("name", sorted({n for n, _, _, _, _ in SITES}))
def test_an_honest_ask_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_value_a_variable_cannot_take_is_refused():
    """The teeth, counted rather than sampled, over all 193 sites."""
    refused = 0
    for name, ri, ii, which, gi in SITES:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        _node(forged, ri, ii, which, gi)["value"] = \
            "not_a_value_anything_can_take"
        with pytest.raises(Exception):                          # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 193, refused


def _rewrite_every_rendering(node, was: str, now: str) -> None:
    """Move one ``predicate=value`` pair everywhere a string spells it."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                node[key] = value.replace(was, now)
            else:
                _rewrite_every_rendering(value, was, now)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, str):
                node[index] = value.replace(was, now)
            else:
                _rewrite_every_rendering(value, was, now)


def test_the_domain_is_what_speaks_when_both_renderings_move_together():
    """The lie only an outside authority can see.

    Moving the skeleton's value and the name it is filed under in one
    stroke leaves the answer agreeing with itself perfectly. What is left
    to appeal to is the program's own declaration of what levels the
    variable has.

    The forgery has to be complete for that to be what is tested, and one
    parameter is spelt in more places than this file first knew: a gap's
    sentence quotes the same ask, and the rule holding a quote to the
    shortfall it copies refuses a report left behind — earlier, and for a
    reason that is not the one under test. So every string in the report
    moves with the rest. A partial forgery is caught by an inside
    authority and never reaches the outside one.

    What moves is the WHOLE parameter and not the pair inside it. One
    level of one variable is a substring of every ask that conditions on
    it differently, so moving the pair rewrites quotes belonging to asks
    this forgery leaves alone, and the rule refuses those instead — a
    forgery too wide is caught as surely as one too narrow, and neither
    reaches the domain.
    """
    refused = 0
    for name, ri, ii in SKELETONS:
        row = SHAPES[name]
        item = row["result"]["investigation_requests"][ri]["items"][ii]
        node = item["skeleton"]["target"]
        predicate = (node.get("atom") or {}).get("predicate")
        declaration = _declarations(name).get(predicate)
        if not getattr(declaration, "domain", None):
            continue
        was = f"{predicate}={node['value']}"
        now = f"{predicate}=unreachable_level"
        forged = copy.deepcopy(row["result"])
        request = forged["investigation_requests"][ri]
        forged_item = request["items"][ii]
        forged_item["skeleton"]["target"]["value"] = "unreachable_level"
        forged_item["target"] = str(forged_item["target"]).replace(was, now)
        if isinstance(request.get("target"), str):
            request["target"] = request["target"].replace(was, now)
        said = forged_item.get("said")
        if isinstance(said, dict) and isinstance(said.get("key"), str):
            said["key"] = said["key"].replace(was, now)
        for entry in forged.get("missing_information") or []:
            if isinstance(entry, dict) and entry.get("name") == item["target"]:
                entry["name"] = forged_item["target"]
                theirs = entry.get("said")
                if isinstance(theirs, dict) and isinstance(theirs.get("key"),
                                                           str):
                    theirs["key"] = theirs["key"].replace(was, now)
        _rewrite_every_rendering(
            forged.get("data_gap_report"),
            str(item["target"]).split(":", 1)[-1],
            str(forged_item["target"]).split(":", 1)[-1])
        with pytest.raises(Exception, match="to take one of"):   # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 65, refused


def test_where_no_domain_is_declared_that_rule_says_nothing():
    """The silence, exercised on its own rather than described.

    Asked of the check directly, because through the door the name would
    speak for it and a silent rule would look held.
    """
    silent = [site for site in SITES if not _domain(*site)]
    assert len(silent) == 50, len(silent)
    name, ri, ii, which, gi = silent[0]
    skeleton = copy.deepcopy(
        SHAPES[name]["result"]["investigation_requests"][ri]["items"][ii]
        ["skeleton"])
    node = skeleton["target"] if which == "target" else skeleton["given"][gi]
    node["value"] = "not_a_value_anything_can_take"
    _check_the_values_it_asks_about_are_ones_the_variable_takes(
        "here", skeleton, _declarations(name))


def test_a_variable_patch_carries_no_value_and_is_never_asked():
    """The silence that is by construction, not by exception."""
    patches = [
        item["skeleton"]
        for pair in SHAPES.values()
        for req in (pair["result"] or {}).get("investigation_requests") or []
        for item in req.get("items") or []
        if isinstance(item.get("skeleton"), dict)
        and item["skeleton"].get("kind") == "variable_patch"
    ]
    assert len(patches) == 288, len(patches)
    assert all(_valued_atoms_of(patch, []) == [] for patch in patches)


def test_the_name_reproduces_every_skeleton_it_stands_for():
    """The grammar, pinned rather than assumed.

    A rule that reads a name is worth exactly as much as the reading, so
    every corpus skeleton is rebuilt from its own name here. A key whose
    grammar moves fails this loudly instead of being under-read into
    silence.
    """
    for name, ri, ii in SKELETONS:
        item = SHAPES[name]["result"]["investigation_requests"][ri]["items"][ii]
        head, bar, tail = str(item["target"]).partition("|")
        skeleton = item["skeleton"]
        target = skeleton["target"]
        mine = ((target.get("atom") or {}).get("predicate"),
                str(target.get("value")))
        assert [tuple(p) for p in _PAIRS_IN_A_KEY.findall(head)] == [mine], \
            item["target"]
        theirs = collections.Counter(_PAIRS_IN_A_KEY.findall(tail) if bar
                                     else [])
        ours = collections.Counter(
            ((g.get("atom") or {}).get("predicate"), str(g.get("value")))
            for g in skeleton.get("given") or [])
        assert theirs == ours, item["target"]


def test_a_target_swapped_with_its_own_condition_is_refused():
    """The lie #580's roster cannot see, which is why this is a second rule.

    Both variables are real, both are grounded, both are graph nodes. What
    has changed is which number the reader is sent to measure.
    """
    refused = 0
    for name, ri, ii in SKELETONS:
        row = SHAPES[name]
        if not (row["result"]["investigation_requests"][ri]["items"][ii]
                ["skeleton"].get("given") or []):
            continue
        forged = copy.deepcopy(row["result"])
        skeleton = forged["investigation_requests"][ri]["items"][ii]["skeleton"]
        skeleton["target"], skeleton["given"][0] = (skeleton["given"][0],
                                                    skeleton["target"])
        with pytest.raises(Exception, match="is a stub for"):    # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 66, refused


def test_dropping_a_condition_is_refused():
    """A number measured under fewer conditions is a different number."""
    refused = 0
    for name, ri, ii in SKELETONS:
        row = SHAPES[name]
        if not (row["result"]["investigation_requests"][ri]["items"][ii]
                ["skeleton"].get("given") or []):
            continue
        forged = copy.deepcopy(row["result"])
        forged["investigation_requests"][ri]["items"][ii]["skeleton"][
            "given"].pop(0)
        with pytest.raises(Exception, match="conditions on"):    # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 66, refused


def test_the_conditions_written_in_another_order_are_the_same_ask():
    """The rewrite that must NOT be refused.

    What a parameter is conditioned on is a set. An answer that writes it
    in another order says the same thing, and a rule that refused it would
    be pinning a rendering rather than an invariant.
    """
    checked = 0
    for name, ri, ii in SKELETONS:
        row = SHAPES[name]
        if len(row["result"]["investigation_requests"][ri]["items"][ii]
               ["skeleton"].get("given") or []) < 2:
            continue
        forged = copy.deepcopy(row["result"])
        forged["investigation_requests"][ri]["items"][ii]["skeleton"][
            "given"].reverse()
        the_door_for(row["result"])(row["program"], forged)
        checked += 1
    assert checked == 36, checked


def test_a_name_that_spells_no_parameter_is_refused():
    """The branch the corpus cannot reach on its own.

    The schema gives a parameter skeleton exactly one ``target``, so its
    name spells exactly one parameter before the conditioning bar. A name
    that spells none leaves a reader with no handle on which number this
    is, and going silent there would let a forger switch the rule off by
    rewriting the string it reads.
    """
    name, ri, ii = SKELETONS[0]
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    item = forged["investigation_requests"][ri]["items"][ii]
    item["target"] = "parameter:nothing"
    said = item.get("said")
    if isinstance(said, dict) and "key" in said:
        said["key"] = "nothing"
    with pytest.raises(Exception, match="spells no single parameter"):
        the_door_for(row["result"])(row["program"], forged)


def test_the_two_rosters_over_a_key_are_read_for_two_questions():
    """``_PAIRS_IN_A_KEY`` beside the names roster it sits next to.

    They are two expressions of one grammar rather than one derived from
    the other, and this is the shape that separates them: a key ending in
    a bare ``name=`` mentions a name and spells no value.
    """
    assert _PAIRS_IN_A_KEY.findall("P(y=True|x=)") == [("y", "True")]
    assert re.findall(r"([A-Za-z_][A-Za-z_0-9]*)\s*=", "P(y=True|x=)") == \
        ["y", "x"]
