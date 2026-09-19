"""The block that stands where a number would have been.

Every ``needs_investigation`` answer IS this block, and it is assembled by
one function. Measured before the rule: 273 of its leaves on the answer
shapes could be rewritten and both public doors said yes.

The relations it rests on are the producer's, and this file measures each
one on the corpus before the rule is allowed to lean on it — a relation
nobody measured is a false refusal waiting for the shape that disobeys it.

The one that had to be found by measuring rather than by reading: a
mapping's key order is not something an envelope fixes. A JSON object is
unordered by specification, and this repository's own corpus is written
through ``json.dumps(sort_keys=True)`` — which reorders the recorded half
while the rendered half keeps the order its producer wrote in. Comparing
the two as strings called one honest row a liar. So the order is taken
from the sentence and every value from the record, and the row that found
it is exercised below rather than described.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis import language, refusals
from themis.verifier.errors import VerificationError
from themis.verifier.estimator_failure_rules import (
    _as_written, _is_what_the_envelope_holds, verify_refusal_block)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every answer whose whole content is a refusal block.
REFUSALS = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair.get("result") or {}).get("estimator_failure"), dict))


def _block(name):
    return SHAPES[name]["result"]["estimator_failure"]


def _the_reordered_stratum():
    """The answer the two tests below are about, taken by what makes it one:
    a recorded stratum whose keys its own sentence lists in another order.

    It used to be named. A structural row's name is a digest of the leaf
    shapes it brings, so it changes the day another row starts bringing one
    of them — the name pinned something no claim here depends on, and a
    re-collection duly renamed it.
    """
    for name in REFUSALS:
        block = _block(name)
        cells = (block.get("details") or {}).get("cells")
        said = (block.get("said") or {}).get("cells")
        if not cells or not isinstance(said, str):
            continue
        keys = list(cells[0])
        spelled = [part.split("=")[0] for part in _parts(said)]
        if keys != spelled[:len(keys)]:
            return name
    return None


def _parts(rendered):
    """The ``key=value`` pieces of a rendered stratum, in sentence order."""
    return rendered.strip("[]").split(", ")


#: None when no answer renders one out of order, which the two tests below
#: say for themselves rather than dying on a missing key.
REORDERED_STRATUM = _the_reordered_stratum()


def _leaves(node, trail=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{trail}.{key}" if trail else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{trail}.{index}")
    else:
        yield trail, node


def _set_at(node, dotted, value):
    steps = dotted.split(".")
    for step in steps[:-1]:
        node = node[int(step)] if isinstance(node, list) else node[step]
    if isinstance(node, list):
        node[int(steps[-1])] = value
    else:
        node[steps[-1]] = value


def _bend(value):
    """One lie per leaf, of the kind that leaf can be told."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "_forged"
    if isinstance(value, list):
        return value[1:] if value else ["forged"]
    if isinstance(value, dict):
        return {**value, "forged": True}
    return "forged"


# ------------------------------------------------- the facts this rests on


def test_the_corpus_carries_refusals_to_ask_about():
    """Stated so a narrowing shows up as a failure, not as a quiet pass.

    Seven fewer than there were, and not by a narrowing: two refusals
    carried a copy of the identification layer's reason in ``recorded``,
    two leaves on one and five on the other, and the copy is gone."""
    assert len(REFUSALS) == 37, len(REFUSALS)
    assert sum(1 for name in REFUSALS for _ in _leaves(_block(name))) == 333


def test_the_recorded_facts_and_the_sentences_facts_are_one_mapping():
    """``block`` builds both halves from one dict, so their keys agree.

    Asserted rather than assumed: the rule refuses when they do not, and a
    relation that only held by luck would be refusing honest answers.
    """
    for name in REFUSALS:
        block = _block(name)
        spoken = set(block.get("said") or {}) | set(block.get("words") or {})
        assert spoken == set(block.get("details") or {}), name


def test_every_spoken_fact_is_the_recorded_one_rendered():
    """The said half, recomputed from the recorded half, all 70 of them."""
    checked = 0
    for name in REFUSALS:
        block = _block(name)
        details = block.get("details") or {}
        for key, spoken in (block.get("said") or {}).items():
            again = language.capped(
                language.symbols(_as_written(details[key], str(spoken))))
            assert again == spoken, (name, key, spoken, again)
            checked += 1
    assert checked == 73, checked


def test_every_word_is_the_recorded_one_the_envelope_could_hold():
    """The words half, which reduces to a token unless it has facts of its own.

    Both shapes occur — eight words travel as a bare token and two as a
    whole statement — and the rule accepts either rather than deciding
    which a word should have taken. That is the point: which shape a
    producer chose is not a claim, and a rule that read the count above as
    a rule would refuse the first producer to state a bare member as a
    statement.
    """
    tokens = whole = 0
    for name in REFUSALS:
        block = _block(name)
        details = block.get("details") or {}
        for key, spoken in (block.get("words") or {}).items():
            assert _is_what_the_envelope_holds(details[key], spoken), (name, key)
            if isinstance(spoken, dict) and "said" not in spoken:
                tokens += 1
            else:
                whole += 1
    assert (tokens, whole) == (8, 2), (tokens, whole)


def test_a_bare_member_stated_as_a_statement_is_not_a_lie():
    """The shape no producer writes today, which is a count and not a rule.

    Constructed, because the corpus cannot exhibit it: a word carrying no
    facts of its own may be written down whole or as its token, and both
    say the same thing to a reader.
    """
    spoken = {"token": "cell_feasible_set", "vocabulary": "x"}
    assert _is_what_the_envelope_holds("cell_feasible_set", spoken)
    assert _is_what_the_envelope_holds(dict(spoken), spoken)
    assert not _is_what_the_envelope_holds("something_else", spoken)


def test_the_kind_is_a_function_of_the_species():
    """Read off the registry, which is where the producer stamps it from."""
    for name in REFUSALS:
        block = _block(name)
        species = refusals.BY_NAME[str(block["failure_type"])]
        assert str(block["kind"]) == str(species.kind), name


# ------------------------------------------------------------------- teeth


def test_no_honest_answer_is_refused():
    """All 243, through the strongest door that reads each one."""
    for name, pair in SHAPES.items():
        the_door_for(pair["result"])(pair["program"], pair["result"])


def test_a_bent_leaf_is_refused():
    """Every leaf of every refusal block, bent one at a time.

    The number is what the rule catches on its own rather than what the
    door does, so a leaf another rule already holds counts as free here and
    is named below instead of inflating this. The seven leaves of the copied
    identification reason were all on the free side, and left with it.

    Thirty-seven moved from free to held when the estimator became a name
    this build has to have: one per refusal block, since every one of them
    carries the field and nothing had ever asked what it said.
    """
    held = free = 0
    for name in REFUSALS:
        result = SHAPES[name]["result"]
        for where, value in _leaves(result["estimator_failure"]):
            bad = copy.deepcopy(result)
            _set_at(bad["estimator_failure"], where, _bend(value))
            try:
                verify_refusal_block(bad)
            except VerificationError:
                held += 1
            else:
                free += 1
    assert (held, free) == (264, 69), (held, free)


def test_a_dropped_fact_is_refused():
    """The forgery no value edit reaches: a fact deleted from one half.

    A sentence with a fact removed still renders — the assembler drops what
    has no hole and states an absence for a hole with nothing in it — so
    this is the edit that leaves an answer looking whole.
    """
    held = free = 0
    for name in REFUSALS:
        result = SHAPES[name]["result"]
        for part in ("said", "words", "details"):
            for key in result["estimator_failure"].get(part) or {}:
                bad = copy.deepcopy(result)
                del bad["estimator_failure"][part][key]
                try:
                    verify_refusal_block(bad)
                except VerificationError:
                    held += 1
                else:
                    free += 1
    assert (held, free) == (166, 0), (held, free)


def test_a_kind_swapped_for_another_declared_one_is_refused():
    """The lie the vocabulary cannot catch, because both words are real."""
    refused = 0
    for name in REFUSALS:
        result = SHAPES[name]["result"]
        mine = str(result["estimator_failure"]["kind"])
        other = next(str(k) for k in refusals.Kind if str(k) != mine)
        bad = copy.deepcopy(result)
        bad["estimator_failure"]["kind"] = other
        with pytest.raises(VerificationError, match="registry declares"):
            verify_refusal_block(bad)
        refused += 1
    assert refused == 37, refused


def test_a_species_this_build_never_heard_of_says_nothing_about_its_kind():
    """The silence is the producer's, and it points the other way from routes.

    ``stamp`` closes what this build emits and says reading is deliberately
    not symmetric, because refusing an unregistered species would reject
    somebody else's honest refusal. Exercised on the check directly: through
    the door the vocabulary would speak for it and the silence would look
    held.
    """
    bad = copy.deepcopy(SHAPES[REFUSALS[0]]["result"])
    bad["estimator_failure"]["failure_type"] = "a_species_from_another_build"
    bad["estimator_failure"]["kind"] = "graph"
    verify_refusal_block(bad)


def test_a_route_this_build_never_heard_of_is_refused():
    """And this silence does not exist, for the reason ``route`` gives.

    A species whose sentence is unwritten is said by its token and a reader
    loses nothing; a route CARRIES the sentence, so one this build has never
    heard of cannot be said at all.
    """
    name = next(n for n in REFUSALS if _block(n).get("remedies"))
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["estimator_failure"]["remedies"][0]["remedy"] = "walk_it_off"
    with pytest.raises(VerificationError, match="not a route this build"):
        verify_refusal_block(bad)


def test_a_route_is_held_to_naming_what_it_names():
    """Whether a route takes an object belongs to the route.

    Both directions, because both reach a reader as damage: a route that
    names nothing given a subject sends them after something the sentence
    has no room for, and one that names something with the subject removed
    reaches them with an empty hole in it.
    """
    added = removed = 0
    for name in REFUSALS:
        result = SHAPES[name]["result"]
        for index, row in enumerate(result["estimator_failure"].get("remedies")
                                    or ()):
            member = refusals.REMEDY_BY_NAME[str(row["remedy"])]
            bad = copy.deepcopy(result)
            mine = bad["estimator_failure"]["remedies"][index]
            if member.takes_object:
                del mine["subject"]
                removed += 1
            else:
                mine["subject"] = "somewhere"
                added += 1
            with pytest.raises(VerificationError, match="belongs to the route"):
                verify_refusal_block(bad)
    assert (added, removed) == (2, 7), (added, removed)


def test_which_route_an_occasion_offers_is_not_held():
    """The silence stated as a number, so a later rule can see what it buys.

    A route swapped for another of the same arity passes: what is declared
    about a route is its sentence and whether it names something, and which
    one THIS occasion offers is the raise site's. The arity half does work
    — every swap across it is refused — and this pins both halves so that
    closing either shows up here.
    """
    accepted = refused = 0
    for name in REFUSALS:
        result = SHAPES[name]["result"]
        for index, row in enumerate(result["estimator_failure"].get("remedies")
                                    or ()):
            for other in refusals.Remedy:
                if str(other) == str(row["remedy"]):
                    continue
                bad = copy.deepcopy(result)
                bad["estimator_failure"]["remedies"][index]["remedy"] = str(
                    other)
                try:
                    verify_refusal_block(bad)
                except VerificationError:
                    refused += 1
                else:
                    accepted += 1
    assert (accepted, refused) == (28, 17), (accepted, refused)


def test_a_fact_no_second_run_could_reproduce_is_refused():
    """The one value whose two renderings are not one function.

    ``occasion`` orders a set on its way onto the envelope and ``symbols``
    does not on its way into the sentence, so the sentence carries Python
    set syntax in a hash-dependent order. This rule refuses that rather
    than allowing for it, and the reason is in the module docstring: text
    its own producer cannot reproduce is not something two records can be
    said to agree about. Constructed, since nothing emits one — which is
    what the clean corpus above says.
    """
    # Set syntax, and no promise about the order inside it. Pinning one of
    # the two spellings made this test depend on the very thing it exists
    # to record: Python randomises string hashing per process, so the same
    # call renders {'a', 'b'} in one run and {'b', 'a'} in the next, and
    # the failure arrives looking like somebody else's change broke it.
    # What is claimed is that the braces are there and the ordering is not.
    rendered = language.symbols({"a", "b"})
    assert rendered.startswith("{") and rendered.endswith("}"), rendered
    assert sorted(rendered[1:-1].split(", ")) == ["'a'", "'b'"], rendered
    assert language.symbols(language.occasion({"a", "b"})) == "['a', 'b']"

    result = {"estimator_failure": {
        "estimator": "backdoor", "failure_type": "not_identified",
        "kind": "graph", "details": {"columns": ["a", "b"]},
        "said": {"columns": "{'a', 'b'}"}}}
    with pytest.raises(VerificationError, match="shown different facts"):
        verify_refusal_block(result)


# --------------------------------------------------- what is not a claim


def test_a_reordered_mapping_is_not_a_lie():
    """The row that found this, exercised rather than described.

    One corpus answer renders a stratum as ``[z=…, x=…]`` while its
    recorded twin, having been through a sorting serializer, holds the
    keys the other way round. Both tell the fact correctly. Comparing the
    renderings as strings called it a forgery, so the order is taken from
    the sentence and every value from the record.
    """
    name = REORDERED_STRATUM
    assert name, "no corpus answer renders a stratum out of key order"
    block = _block(name)
    keys = list(block["details"]["cells"][0])
    assert [part.split("=")[0] for part in _parts(block["said"]["cells"])] \
        != keys
    verify_refusal_block(SHAPES[name]["result"])

    # The same facts written the other way round, taken from the sentence
    # the answer itself carries rather than typed out beside it.
    bad = copy.deepcopy(SHAPES[name]["result"])
    parts = _parts(bad["estimator_failure"]["said"]["cells"])
    bad["estimator_failure"]["said"]["cells"] = (
        f"[{', '.join(reversed(parts))}]")
    verify_refusal_block(bad)


def test_a_reordering_that_changes_a_value_is_still_refused():
    """The order is all the sentence is trusted for."""
    name = REORDERED_STRATUM
    assert name, "no corpus answer renders a stratum out of key order"
    bad = copy.deepcopy(SHAPES[name]["result"])
    parts = _parts(bad["estimator_failure"]["said"]["cells"])
    at = next(i for i, part in enumerate(parts)
              if part.endswith(("=True", "=False")))
    parts[at] = (parts[at][:-len("True")] + "False"
                 if parts[at].endswith("=True")
                 else parts[at][:-len("False")] + "True")
    bad["estimator_failure"]["said"]["cells"] = (
        f"[{', '.join(reversed(parts))}]")
    with pytest.raises(VerificationError, match="shown different facts"):
        verify_refusal_block(bad)


def test_a_value_that_spells_another_key_is_not_a_lie():
    """The false refusal that reading a key ANYWHERE in the sentence causes.

    The order is taken from the sentence, so where a key stands has to be
    read off it — and a key stands where the rendering puts one, which is
    the start, just after a bracket, or just after the ``", "`` joining two
    fragments. A VALUE may spell ``c=1`` wherever it likes. Read without
    the boundary, this honest stratum orders ``c`` ahead of ``b`` and the
    two renderings disagree about a fact both state correctly.

    Constructed rather than found: no corpus row spells a sibling key
    inside a value, and a gate is only verified once the case it must say
    no to — and the case it must not — have both been built.
    """
    raw = {"a": "c=1", "b": 2, "c": 3}
    rendered = language.capped(language.symbols(raw))
    assert rendered == "a='c=1', b=2, c=3", rendered

    result = {"estimator_failure": {
        "estimator": "backdoor", "failure_type": "not_identified",
        "kind": "graph", "details": {"stratum": raw},
        "said": {"stratum": rendered}}}
    verify_refusal_block(result)

    # And the same fact after a sorting serializer, which is the case the
    # order-from-the-sentence reading exists for.
    result["estimator_failure"]["details"]["stratum"] = {
        key: raw[key] for key in sorted(raw)}
    verify_refusal_block(result)

    # A value moved inside that same stratum is still refused.
    result["estimator_failure"]["said"]["stratum"] = "a='c=1', b=9, c=3"
    with pytest.raises(VerificationError, match="shown different facts"):
        verify_refusal_block(result)


# ------------------------------------------------- what stays open, measured


def test_the_estimator_has_no_second_record_to_be_held_to():
    """Why 36 leaves stay open, measured rather than deferred.

    A refusal names the estimator that declined, and the name appears
    nowhere else on 31 of the 36 answers — these carry no estimate, often
    no chain, and the five hits are the query kind or the program saying
    the same word for its own reasons. Nor is there a roster: the contract
    types the field a string where it gives ``failure_type`` a full enum,
    and the word is written as a literal at some forty raise sites. Holding
    it would mean restating those forty here, which is the table a verifier
    must not become.
    """
    def _strings(node, out):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                _strings(value, out)
        elif isinstance(node, list):
            for value in node:
                _strings(value, out)
        return out

    alone = 0
    for name in REFUSALS:
        pair = SHAPES[name]
        rest = {k: v for k, v in pair["result"].items()
                if k != "estimator_failure"}
        word = _block(name)["estimator"]
        if word not in _strings(rest, []) + _strings(pair["program"], []):
            alone += 1
    assert alone == 32, alone

    schema = json.loads(
        (pathlib.Path(__file__).parents[1] / "themis" / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    field = (schema["properties"]["estimator_failure"]["properties"])
    assert field["estimator"] == {"type": "string"}
    assert len(field["failure_type"]["enum"]) > 60


def test_what_was_measured_and_not_said_has_no_second_rendering():
    """Why ``recorded`` stays open, in its own producer's words.

    ``block`` names the two halves separately so that one bag with two
    audiences cannot be checked; ``recorded`` is the half that was measured
    and NOT said, so there is no sentence to compare it with. A rule
    reaching for one would be inventing the second copy it claims to be
    checking.
    """
    carried = 0
    for name in REFUSALS:
        block = _block(name)
        recorded = block.get("recorded") or {}
        assert not (set(recorded) & set(block.get("said") or {})), name
        carried += len(recorded)
    assert carried == 16, carried
