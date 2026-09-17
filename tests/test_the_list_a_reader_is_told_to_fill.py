"""The one block that asks the reader for something, and the two rules
that only ever counted it.

``investigation_requests`` is the shopping list. Each item names a
``target``, carries a ``skeleton`` — the patch itself — and a ``said``
mapping whose contents are substituted into the sentence a reader gets.
The skeleton is not illustrative: ``apply_patch_and_run`` exists so that
an LLM copying one verbatim "should just work", which makes a rewritten
predicate a reader filling in a different variable.

Two rules touch the block and both use it as a DENOMINATOR. T10-1
collects every target into a set and resolves gap provenance against it;
T10-2 asks that each item be cited by some gap. Neither looks inside an
item — and a denominator can be shortened. It was shortened twice: the
framing group is exempt from T10-2 by name, thirty-seven of forty-three
requests, and what remained was reachable through ``if not target:
continue``. Measured before this: all 264 leaves the census asks about
could be rewritten and the door said yes.

Every anchor used here already existed. A framing item's target is a
``framing_notes[].predicate`` (75/75, and that side is held by T10-2's
third check); the predicate is written three times inside one item and
all three agree (75/75); the skeleton's empty fields are empty in the
program's own declaration and its ``existing`` entries equal it (48/48).
The last is the asked side, which an answer cannot edit.

One anchor was the wrong one. "The distribution is over predicates the
program declares" was read against the declaration table, and a program
whose variables all arrive through cause edges declares none of them — so
an honest ask for a distribution over one of them was refused, with the
reason that the door the patch goes back through would not know the name.
That door knows it: the same program with the probability supplied
validates and runs. Which predicates a program NAMES and which ones it
DECLARES are two rosters, and a membership question wanted the wider one.

The corpus has since widened to the answers that carry no number, and the
counts below moved with it. Two things it brought are not counts: a fourth
request group, and four carriers with no reasoning chain — so for one
frontier the block that asks a reader for something went unread on exactly
the answers whose whole content is an ask. Those four are now asked at the
door that holds what an answer says, which needs no chain.

The heading over the list came last and was declared unheld here with two
reasons beside it, both checkable and both wrong. That holding the target
means restating a format belonging to whoever writes it: the format is
written by two runtime functions out of one definition, which says in its
own docstring that it is stated once because it is applied twice. And that
group-to-action is a correspondence the corpus happens to show: it is a
table in the pusher, five pairs, plus the framing channel's. A reason
written beside a number reads exactly like a hole with a reason written
beside it, and this list has now produced five of the latter.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests import schema_walk
from tests.answer_corpus import the_door_for
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.types import GapKind
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import (
    _ACTION_FOR_GROUP, _FRAMING_PRIORITY, _SKELETON_KINDS, declarations_of,
    predicates_of, verify_investigation_items,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES if SHAPES[n]["result"].get("investigation_requests"))

#: Four carriers took no route and so carry no chain. The door that
#: re-runs a chain refuses those before reading a word — on them every
#: forgery would be refused for what the answer IS, and a rule scoring that
#: as a catch would be counting its own blindness as coverage. They are
#: asked at the door that holds what an answer SAYS, which is what
#: ``the_door_for`` returns, and which is the whole of their content.
CHAINLESS = sorted(name for name, pair in SHAPES.items()
                   if pair["result"].get("derivation") is None)

#: A shape whose framing request patches two variables, and one whose
#: structure items are the citable kind the coverage rule reads.
FRAMING = "backdoor_linear"
STRUCTURE = "iv_wald"
EDGES = "scm_counterfactual_linear_fit"


def _graph_only_program() -> dict:
    """A program that declares nothing and names everything.

    X → A → W ← B ← Y with X → Y, asked for the effect of X on Y given W.
    Every predicate arrives through a cause edge and there is not one
    ``variable`` statement — the shape the collider-gap tests are written
    in, so it is the system's own idiom rather than a case built to make
    a point.
    """
    def atom(name):
        return {"predicate": name, "args": [{"type": "const", "name": "me"}]}

    def edge(tail, head):
        return {"kind": "cause", "forall": ["I"],
                "from": {"predicate": tail,
                         "args": [{"type": "var", "name": "I"}]},
                "to": {"predicate": head,
                       "args": [{"type": "var", "name": "I"}]}}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            edge("x", "a"), edge("a", "w"), edge("y", "b"), edge("b", "w"),
            edge("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": atom("y"), "value": True},
                "intervention": {"atom": atom("x"), "value": True},
                "given": [{"atom": atom("w"), "value": True}],
            }},
        ],
    }


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _requests(result):
    return result.get("investigation_requests") or []


def _first_item(result, group):
    for request in _requests(result):
        if request.get("group") == group:
            for item in request.get("items") or []:
                return request, item
    raise AssertionError(f"no {group} item")


def _verify_with(method, mutate):
    program, result = _pair(method)
    mutate(result)
    themis.verify(program, result)


# ------------------------------------------------- the facts this rests on


def test_the_list_is_carried_by_almost_every_answer():
    """And which groups a request comes in, stated so that a fourth is a
    failure here rather than an item the rule reads by whichever branch it
    falls through — the mistake this module already made once."""
    assert len(CARRIERS) == 161
    groups = {r.get("group") for n in CARRIERS
              for r in _requests(SHAPES[n]["result"])}
    assert groups == {"framing", "assumption", "structure", "parameter"}


def test_a_framing_target_is_a_framing_note_predicate():
    """The link the exemption rests on, stated as a number.

    T10-2 lets a framing item go uncited because the note beside it is
    cited instead. That is only true while the two name the same thing,
    which nothing checked.

    Every count in this file moved together by eight when a targeted
    refresh of eight corpus rows picked up producer drift they predated:
    eight more framing notes, eight more gaps and eight more investigation
    items across six rows. More to link is not less linking, and the
    assertions here are equalities, so the two are told apart by whether
    the counts move together. They moved by one each again, and the patch
    fields by seven, when the joint general-ID row was refreshed the same
    way. The eight rows collected when the identifier began answering a
    query conditioning on a descendant of the treatment brought nine more
    framing items and 63 more patch fields.
    """
    linked = 0
    for name in CARRIERS:
        result = SHAPES[name]["result"]
        notes = {n.get("predicate") for n in result.get("framing_notes") or []}
        for request in _requests(result):
            if request.get("group") != "framing":
                continue
            for item in request.get("items") or []:
                assert item["target"] in notes
                linked += 1
    assert linked == 310


def test_the_patch_is_answerable_from_the_program_alone():
    """Every skeleton key is a field a variable declaration has, and the
    program agrees about which of them are set.

    Of the two kinds a skeleton can be, this is the fact about one of
    them. A parameter ask names a probability rather than a variable, so
    the program declares no such target and there is no field list to
    agree about; it is anchored on the two records it does have — the key
    its own sentence quotes, and the predicates its distribution is over —
    and the split is read off the skeleton's ``kind``, the way the rule
    itself reads it, rather than off which targets happen to resolve.
    """
    checked = parameters = 0
    for name in CARRIERS:
        program, result = _pair(name)
        declared = declarations_of(validate_program(program))
        for request in _requests(result):
            for item in request.get("items") or []:
                skeleton = item.get("skeleton") or {}
                if not skeleton:
                    continue
                if skeleton.get("kind") != "variable_patch":
                    parameters += 1
                    continue
                decl = declared[item["target"]]
                for key, value in (skeleton.get("fields") or {}).items():
                    assert hasattr(decl, key)
                    if value is None:
                        assert getattr(decl, key) is None
                        checked += 1
                for key, value in (skeleton.get("existing") or {}).items():
                    got = getattr(decl, key)
                    assert (list(got) if isinstance(got, tuple) else got) \
                        == value
                    checked += 1
    assert (checked, parameters) == (2185, 111), (checked, parameters)


# ------------------------------------------------------------- the gate


def test_the_kinds_a_skeleton_can_be_are_the_kinds_the_door_takes():
    """The one table this module restates, pinned to the table it copies.

    Written without it, the rule read "has a skeleton" as "is a framing
    patch" — which is what the forty-four answer shapes contain and not
    what the system has. A parameter ask carries a probability skeleton,
    and ten honest results were refused before this was a set rather than
    an assumption. Restated rather than imported, because a verifier that
    imports the producer's table agrees with it by construction; pinned,
    so a third kind is a red suite here rather than an item nothing reads.
    """
    from themis.kernel import _RECORD_KIND_TO_BUNDLE

    assert _SKELETON_KINDS == set(_RECORD_KIND_TO_BUNDLE)

    schema = json.loads(
        (pathlib.Path(themis.__file__).parent / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    defs = schema["$defs"]
    assert _SKELETON_KINDS == {
        defs[name]["properties"]["kind"]["const"]
        for name in ("parameterSkeleton", "variablePatch")
    }


def test_a_skeleton_of_a_kind_nothing_can_read():
    """Asked of the rule directly, because the schema gets there first.

    A third ``kind`` cannot reach ``verify`` — the envelope schema says
    so in as many words, "no third shape is accepted". That makes the
    branch below the second of two lines rather than the only one, and
    the reason to keep it is that it decides WHICH question an item is
    asked; deciding that by "whatever is left" is how the first version
    read a probability skeleton as a framing patch.
    """
    program, result = _pair(FRAMING)
    _first_item(result, "framing")[1]["skeleton"]["kind"] = "variable_patch_v2"
    with pytest.raises(VerificationError, match="an ask nobody can answer"):
        verify_investigation_items(result, validate_program(program))


def test_the_schema_refuses_a_third_kind_before_the_verifier_sees_one():
    from themis.input.syntactic_validator import SyntacticError

    program, result = _pair(FRAMING)
    _first_item(result, "framing")[1]["skeleton"]["kind"] = "variable_patch_v2"
    with pytest.raises(SyntacticError, match="skeleton"):
        themis.verify(program, result)


def test_a_patch_that_would_send_a_reader_to_another_variable():
    """The counter-example this exists for. The item still reads as a
    coherent ask; it just asks about something else."""
    def rename(result):
        _, item = _first_item(result, "framing")
        item["skeleton"]["predicate"] = "z"

    with pytest.raises(VerificationError, match="fills in the other one"):
        _verify_with(FRAMING, rename)


def test_a_patch_for_a_variable_this_program_never_declared():
    def stranger(result):
        request, item = _first_item(result, "framing")
        item["target"] = item["skeleton"]["predicate"] = "not_a_variable"
        item["said"]["predicate"] = "not_a_variable"
        # A note of the same shape as the real ones, so the item reaches
        # the declaration lookup rather than tripping the note check or
        # the schema on the way.
        note = copy.deepcopy(result["framing_notes"][0])
        note["predicate"] = "not_a_variable"
        result["framing_notes"].append(note)

    with pytest.raises(VerificationError, match="does not declare"):
        _verify_with(FRAMING, stranger)


def test_a_framing_item_with_no_note_beside_it():
    """Without the note the exemption in T10-2 has nothing behind it, so
    the item would be held by nothing at all."""
    def drop(result):
        _, item = _first_item(result, "framing")
        result["framing_notes"] = [
            n for n in result["framing_notes"]
            if n.get("predicate") != item["target"]
        ]

    with pytest.raises(VerificationError, match="framing_note says so"):
        _verify_with(FRAMING, drop)


def test_a_patch_that_asks_for_what_the_program_already_declared():
    """Moved out of ``existing``, which is where the program's answer is
    known to be non-empty — asking for a field this shape happens to
    leave unset would be an honest patch, not a forgery."""
    def already(result):
        for request in _requests(result):
            for item in request.get("items") or []:
                existing = (item.get("skeleton") or {}).get("existing") or {}
                if not existing:
                    continue
                key = sorted(existing)[0]
                existing.pop(key)
                item["skeleton"]["fields"][key] = None
                item["said"]["count"] = str(len(item["skeleton"]["fields"]))
                item["said"]["fields"] += f", {key}"
                return True
        return False

    tried = 0
    for name in CARRIERS:
        program, result = _pair(name)
        door = the_door_for(SHAPES[name]["result"])
        if not already(result):
            continue
        tried += 1
        with pytest.raises(VerificationError, match="already declares it"):
            door(program, result)
    assert tried == 121


def test_a_patch_that_misreports_what_the_program_fixed():
    def lie(result):
        _, item = _first_item(result, "framing")
        item["skeleton"]["existing"]["domain"] = ["yes", "no"]

    with pytest.raises(VerificationError, match="already fixed"):
        _verify_with(FRAMING, lie)


def test_a_sentence_whose_number_is_not_what_the_patch_leaves():
    def miscount(result):
        _, item = _first_item(result, "framing")
        item["said"]["count"] = "3"

    with pytest.raises(VerificationError, match="fields are unset"):
        _verify_with(FRAMING, miscount)


def test_a_sentence_naming_fields_the_patch_does_not_leave():
    def wrong(result):
        _, item = _first_item(result, "framing")
        item["said"]["fields"] = "time_window, unit"

    with pytest.raises(VerificationError, match="to fill"):
        _verify_with(FRAMING, wrong)


def test_the_number_and_the_list_may_not_be_left_blank():
    """Asked first and on its own, for the reason three frontiers running
    produced: the tests below a blank are equalities and memberships, and
    a blank is the value that reads as no claim while passing them."""
    for key in ("count", "fields"):
        with pytest.raises(VerificationError, match="puts nothing there|"
                                                   "names none"):
            _verify_with(FRAMING, lambda r, k=key: _first_item(r, "framing")[1]
                         ["said"].update({k: "  "}))


def test_an_item_may_not_name_nothing_at_all():
    with pytest.raises(VerificationError, match="nothing asked for"):
        _verify_with(FRAMING,
                     lambda r: _first_item(r, "framing")[1].update(target=""))


def test_an_emptied_target_no_longer_opts_an_item_out_of_coverage():
    """The other face of the same root cause, fixed where it lives.

    T10-2 demands that every non-framing item be cited by a gap and
    skipped any item whose target was falsy — so naming nothing bought
    the exemption that the framing group has by name. Measured before the
    fix: accepted on five of the six shapes carrying a citable item.

    Asked at the door that rule lives behind rather than through
    ``verify``, where the check above would reach the same envelope
    first. Two rules refusing one forgery is not one rule too many: this
    one is what the OTHER door has, and that door takes no program.
    """
    _, result = _pair(STRUCTURE)
    _first_item(result, "structure")[1]["target"] = ""
    with pytest.raises(VerificationError, match="cannot be cited"):
        themis.verify_data_gap_report(result)


def test_an_edge_the_item_spells_out_names_its_own_ends():
    for key in ("child", "parent"):
        with pytest.raises(VerificationError, match="edge it asks about"):
            _verify_with(EDGES, lambda r, k=key: _first_item(r, "structure")[1]
                         ["said"].update({k: "q(me)"}))
        with pytest.raises(VerificationError, match="puts nothing there"):
            _verify_with(EDGES, lambda r, k=key: _first_item(r, "structure")[1]
                         ["said"].update({k: " "}))


# ------------------------------------------- what the rule does not reach


def test_a_note_may_honestly_be_empty_and_is_not_read():
    """``causation_plugin`` ships ``said = {"note": ""}``, so a rule that
    refused blank ``said`` values everywhere would refuse an honest
    answer. Prose is declared, not asked — the same line drawn one
    frontier earlier for a gap's ``note``.

    Rewritten in both places the answer writes it. The request over this
    one ask carries the ask's species and occasion as its own note, and
    two copies that disagree are a different claim from what either says.
    """
    result = SHAPES["causation_plugin"]["result"]
    request, item = _first_item(result, "assumption")
    assert item["said"] == {"note": ""}
    assert request["note"]["said"] == {"note": ""}

    def rewrite(r):
        request, item = _first_item(r, "assumption")
        for said in (item["said"], request["note"]["said"]):
            said.update(note="anything at all")

    _verify_with("causation_plugin", rewrite)


#: The words each heading field may legally hold. Written out rather than
#: imported from the rule under test: a lie drawn from the rule's own
#: table is a lie the rule is guaranteed to recognise.
_ACTIONS = ("collect_observation", "run_experiment", "increase_sample",
            "validate_parameter", "define_assumption", "define_variable")
_PRIORITIES = ("low", "medium", "high")
_GROUPS = ("parameter", "observation", "sample", "structure", "assumption",
           "framing")


def _heading_lies(request):
    """Every lie worth telling about one heading.

    Members of the leaf's own vocabulary, not words outside it — the
    schema refuses those before a rule reads them, which is how two of
    these four fields came to read as held. A grouped target is lied
    about in both of the ways it can drift: the count no longer matching
    what is under it, and the channel it names being another one.
    """
    out = []
    target = request.get("target")
    if isinstance(target, str):
        out.append(("target", "NOPE_not_a_real_ask"))
        if target.strip():
            out.append(("target", ""))
        head, sep, rest = target.partition(":")
        digits = "".join(c for c in rest if c.isdigit())
        if sep and digits:
            out.append(("target", f"{head}:{int(digits) + 1}_items"))
            out.append(("target",
                        f"{next(g for g in _GROUPS if g != head)}:{rest}"))
    for field, vocabulary in (("action", _ACTIONS),
                              ("priority", _PRIORITIES),
                              ("group", _GROUPS)):
        was = request.get(field)
        if isinstance(was, str):
            out.append((field, next(w for w in vocabulary if w != was)))
    return out


def test_the_heading_over_the_list_is_held_to_the_list():
    """The four fields a reader reads before any item, and what holds them.

    They were held by nothing, and two of the four did not appear in the
    declared remainder either — an enum leaf could only be told a lie
    validation refuses, so the census scored it held without any rule
    having asked which member it is.

    Nothing new is recorded to close them. A heading is the items said
    shortly: ``push`` writes the action from the channel, the target from
    the one item or from how many there are, the priority from the
    strongest, and the group is what those items are rows of. Each field
    already had a second record on the envelope; what was missing is that
    the rule descended into ``items`` on its first line and read the one
    heading field it touched, ``group``, as the input to a branch.

    Asked at the strongest door that reads each row, and asked twice: the
    door refuses it, and this rule is the one that refuses it. The first
    is what a caller gets and the second is what this test is entitled to
    say.
    """
    assert len([n for n in CARRIERS if n in CHAINLESS]) == 69
    survived, by_this_rule = [], 0
    for name in CARRIERS:
        program, result = _pair(name)
        for ri, request in enumerate(result["investigation_requests"]):
            for path, value in _heading_lies(request):
                program, result = _pair(name)
                result["investigation_requests"][ri][path] = value
                try:
                    the_door_for(SHAPES[name]["result"])(program, result)
                except Exception:
                    with pytest.raises(VerificationError):
                        verify_investigation_items(result, program)
                    by_this_rule += 1
                    continue
                survived.append((name, ri, path))
    assert by_this_rule == 1407
    assert {p for _, _, p in survived} == {"priority"}
    assert len(survived) == 13


def test_the_thirteen_priorities_with_no_second_record():
    """What is left, and the fact that leaves it rather than a story.

    A group is as urgent as the most urgent thing in it, and how urgent
    each of those things is, is a row of ``missing_information``. Thirteen
    requests have no such rows: their items were pushed from missing items
    the envelope does not render. That is a fact about those envelopes,
    checkable here, and not a reason anybody wrote down — which is what
    the four reasons on this list that later turned out to be holes all
    had in common.

    Framing is not among them although it has no rows either: the priority
    it is filed at is a constant its own pass writes, so there IS a second
    copy to restate, the way a diagnostic band is restated.
    """
    without = []
    for name in CARRIERS:
        result = SHAPES[name]["result"]
        rows = {row.get("name")
                for row in result.get("missing_information") or ()}
        for ri, request in enumerate(result["investigation_requests"]):
            if request.get("group") == "framing":
                continue
            targets = {item.get("target")
                       for item in request.get("items") or ()}
            if not targets <= rows:
                without.append((name, ri))
    assert len(without) == 13, without


def _paired():
    """Every place one missing item is written on the envelope twice."""
    for name in CARRIERS:
        result = SHAPES[name]["result"]
        rows = {r.get("name"): i
                for i, r in enumerate(result.get("missing_information") or ())
                if isinstance(r, dict)}
        for ri, request in enumerate(result["investigation_requests"]):
            for ii, item in enumerate(request.get("items") or ()):
                idx = rows.get(item.get("target"))
                if idx is not None:
                    yield name, ri, ii, idx


def test_one_missing_item_written_twice_says_the_same_thing():
    """The two lists a reader reads, against each other.

    ``missing_information`` says what is short; ``investigation_requests``
    says what to go and do about it, and it is PUSHED from the very tuple
    the first list renders. So wherever a row and an item are the same
    item, the fields both carry are one fact written twice — and nothing
    had ever compared them. A reader could be told one species in the
    first list and another in the second.

    What is deliberately not compared is what only one of them carries:
    the row's ``observable`` and the item's ``skeleton``. Each surface
    carries what its own reader needs, and a field one side lacks is not
    a second record of anything.
    """
    pairs = list(_paired())
    assert len(pairs) == 147, len(pairs)
    refused = 0
    for name, ri, ii, idx in pairs:
        for field in ("gap", "need", "kind"):
            program, result = _pair(name)
            if result["missing_information"][idx].get(field) is None:
                continue
            result["missing_information"][idx][field] = "NOPE_forged"
            with pytest.raises(Exception):
                the_door_for(SHAPES[name]["result"])(program, result)
            with pytest.raises(VerificationError):
                verify_investigation_items(result, program)
            refused += 1
    assert refused == 441


def test_what_only_one_rendering_carries_is_not_compared():
    """Measured, so the exemption is a fact rather than a decision.

    Every pair has the row's ``observable`` and none has it on the item;
    every pair has the item's ``skeleton`` and none has it on the row. A
    rule comparing those would refuse every honest answer that has them.
    """
    one_sided = {"observable": 0, "skeleton": 0}
    for name, ri, ii, idx in _paired():
        result = SHAPES[name]["result"]
        row = result["missing_information"][idx]
        item = result["investigation_requests"][ri]["items"][ii]
        if ("observable" in row) != ("observable" in item):
            one_sided["observable"] += 1
        if ("skeleton" in row) != ("skeleton" in item):
            one_sided["skeleton"] += 1
    assert one_sided == {"observable": 111, "skeleton": 111}


def _asks():
    """Every item that names a gap, and whether a twin row names one too."""
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        rows = {r.get("name"): r
                for r in result.get("missing_information") or ()
                if isinstance(r, dict)}
        for ri, request in enumerate(
                result.get("investigation_requests") or ()):
            for ii, item in enumerate((request or {}).get("items") or ()):
                if not isinstance(item, dict) or item.get("gap") is None:
                    continue
                twin = rows.get(item.get("target"))
                yield name, ri, ii, (isinstance(twin, dict)
                                     and twin.get("gap") is not None)


#: The species an ASK may name, which is not every species there is. Read
#: off the contract rather than off ``GapKind``, because a forgery the
#: schema refuses is not a forgery this rule was ever asked about — the
#: lie has to be one the envelope is allowed to tell.
_ASK_MAY_NAME = frozenset(
    enum for path, sub, _c in schema_walk.RESULT.walk()
    if path[-1:] == ("gap",)
    for enum in schema_walk.RESULT.resolve(sub).get("enum") or ())


def test_the_species_an_ask_may_name_are_a_subset_of_the_species():
    """So the roster above is the contract's and stays a real subset."""
    assert _ASK_MAY_NAME and _ASK_MAY_NAME < {str(k) for k in GapKind}


def _a_species_this_report_does_not_carry(result) -> str:
    present = {gap.get("kind")
               for gap in ((result.get("data_gap_report") or {})
                           .get("gaps") or ())
               if isinstance(gap, dict)}
    return next(k for k in sorted(_ASK_MAY_NAME) if k not in present)


def test_every_ask_names_a_gap_its_own_report_carries():
    """The denominator, and the invariant the rule is allowed to assume.

    Held on every ask this repository produces, so the rule refuses no
    honest answer — and the split says why it was worth writing at all.
    """
    asks = list(_asks())
    twinned = sum(1 for *_rest, twin in asks if twin)
    assert (len(asks), twinned) == (472, 147), (len(asks), twinned)
    for name, ri, ii, _twin in asks:
        result = SHAPES[name]["result"]
        named = result["investigation_requests"][ri]["items"][ii]["gap"]
        kinds = {gap.get("kind")
                 for gap in result["data_gap_report"]["gaps"]}
        assert named in kinds, (name, named, sorted(map(str, kinds)))


def test_an_ask_naming_a_gap_the_report_does_not_carry():
    """The counterexample, put to every ask ONE AT A TIME, at the door.

    One at a time and not all at once: forging every ask on an envelope
    lets one refusal stand for all of them, which counts a rule that
    reached one ask as a rule that reached every ask.

    The number beside it is why this is a rule of its own. The check next
    to it compares an item to the ``missing_information`` row for the same
    target, and 321 of these 468 asks have no such row — every framing ask
    and some of the rest. Two records agreeing is a check only where there
    are two records; a reference is checked against its referent, and there
    is always exactly one of those.
    """
    refused = lonely = 0
    for name, ri, ii, twinned in _asks():
        program, result = _pair(name)
        result["investigation_requests"][ri]["items"][ii]["gap"] = (
            _a_species_this_report_does_not_carry(result))
        with pytest.raises(VerificationError) as caught:
            the_door_for(SHAPES[name]["result"])(program, result)
        refused += 1
        if twinned:
            # Either rule may speak first for these, and the one beside
            # this one does: an ask with a twin row disagrees with it in
            # the same stroke. What that rule already reached is not this
            # one's to count.
            continue
        lonely += 1
        assert "never said it had" in str(caught.value), (name, caught.value)
    assert (refused, lonely) == (472, 325), (refused, lonely)


def test_an_answer_with_no_report_is_not_asked_this():
    """An answer that reported nothing is a different claim.

    Silent rather than refusing, because "this ask points at a species the
    report does not carry" and "this answer has no report at all" are two
    statements and the second is not this rule's to make. Asserted as the
    absence of THIS complaint rather than as acceptance, so that whatever
    else an answer with no report is told stays that rule's business.
    """
    name = CARRIERS[0]
    program, result = _pair(name)
    result.pop("data_gap_report", None)
    for request in result.get("investigation_requests") or ():
        for item in (request or {}).get("items") or ():
            if isinstance(item, dict) and item.get("gap") is not None:
                item["gap"] = "unmeasured_confounder_risk"
    try:
        verify_investigation_items(result, program)
    except VerificationError as exc:
        assert "never said it had" not in str(exc), exc


def test_the_channel_table_is_the_one_the_runtime_writes():
    """The verifier's copy against both producers of the original.

    Restated rather than imported, for the reason ``_SKELETON_KINDS`` is:
    a rule that imports the producer's table agrees with it by
    construction and would have nothing to say when the table changes.
    What makes a restatement safe is this — the two copies compared once,
    so a sixth channel arrives as a red suite rather than as a heading
    nothing reads.

    Two producers, because the framing channel is not pushed with the
    others: its request is built by hand in the scheduler, which is also
    why its heading is spelled with the action where every other is
    spelled with the group.
    """
    from themis.runtime.investigation_pusher import _ACTION_OF
    from themis.types import InvestigationAction, MissingKind

    pushed = {kind.value: action.value
              for kind, action in _ACTION_OF.items()}
    assert pushed == {k: v for k, v in _ACTION_FOR_GROUP.items()
                      if k != "framing"}
    assert set(pushed) == {k.value for k in MissingKind
                           if k is not MissingKind.FRAMING}
    assert (_ACTION_FOR_GROUP["framing"]
            == InvestigationAction.DEFINE_VARIABLE.value)

    framing = [request
               for name in CARRIERS
               for request in SHAPES[name]["result"]["investigation_requests"]
               if request.get("group") == "framing"]
    assert framing
    assert {r["action"] for r in framing} == {"define_variable"}
    assert {r["priority"] for r in framing} == {_FRAMING_PRIORITY}


def test_a_grouped_heading_is_spelled_the_way_the_runtime_spells_it():
    """The format the rule restates, against the function that writes it.

    ``summarise`` says in its own docstring that it is stated once
    because it is applied twice, so this is a shared convention rather
    than one site's private spelling — which is what makes restating it
    the right move and pinning it here the price of that move.
    """
    from themis.runtime.investigation_pusher import summarise
    from themis.types import Priority

    for group, n in (("parameter", 2), ("structure", 4), ("assumption", 12)):
        target, _note, _priority = summarise(
            group, [(f"t{i}", None, Priority.LOW) for i in range(n)])
        assert target == f"{group}:{n}_items"

    single, _note, _priority = summarise(
        "parameter", [("just_this_one", None, Priority.HIGH)])
    assert single == "just_this_one"


def test_the_rule_is_silent_where_there_is_no_list_to_read():
    """Not a skip: an answer that asks for nothing makes no claim about
    what a reader should supply."""
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        assert not _requests(result)
        verify_investigation_items(result, object())


# ------------------------------------ which roster answers "is this a name"


def test_a_program_that_declares_nothing_still_names_its_variables():
    """The two rosters, told apart on the program that separates them.

    ``declarations_of`` answers what the program SAID ABOUT a variable and
    hands back the declaration, which is what a rule wanting a domain
    needs. ``predicates_of`` answers whether the program knows the name at
    all. On this program the first is empty and the second is everything.
    """
    parsed = validate_program(validate_ast(_graph_only_program()))
    assert declarations_of(parsed) == {}
    assert predicates_of(parsed) == frozenset({"x", "a", "w", "y", "b"})


def test_an_ask_about_a_variable_a_cause_edge_introduced_is_answerable():
    """The refusal this closed, and why the reason it gave was wrong.

    The rule refused a parameter ask for naming a predicate the program
    "does not declare", and gave as its reason that the patch would go
    back through a door that would not know the name. The door knows it —
    asserted here rather than argued, by handing that very probability
    back to the program and running it.
    """
    program = _graph_only_program()
    result = themis.run(program)["results"][0]
    asked = [item["skeleton"]["target"]["atom"]["predicate"]
             for request in _requests(result)
             for item in request["items"]
             if (item.get("skeleton") or {}).get("kind") == "probability"]
    assert "a" in asked, asked

    the_door_for(result)(program, result)

    answered = copy.deepcopy(program)
    answered["statements"].insert(0, {
        "kind": "probability", "provenance": "observational",
        "target": {"atom": {"predicate": "a",
                            "args": [{"type": "const", "name": "me"}]},
                   "value": True},
        "given": [{"atom": {"predicate": "x",
                            "args": [{"type": "const", "name": "me"}]},
                   "value": True}],
        "value": 0.5,
    })
    validate_program(validate_ast(answered))
    themis.run(answered)


def test_an_ask_about_a_name_the_program_never_writes_is_still_refused():
    """What the check is for, kept. Widening a roster is only safe if the
    thing it was catching is still caught: an ask a reader cannot place,
    because nothing in the program has ever written that name down."""
    program = _graph_only_program()
    result = themis.run(program)["results"][0]
    item = next(i for request in _requests(result)
                for i in request["items"]
                if (i.get("skeleton") or {}).get("kind") == "probability")
    item["skeleton"]["target"]["atom"]["predicate"] = "unheard_of"
    # The refusal moved one level finer and one step earlier: the whole
    # atom is now held against the problem's grounded variables, which
    # refuses every name this used to refuse and the wrong-unit case with
    # it. What is asserted here is unchanged — the ask is still refused.
    with pytest.raises(VerificationError, match="no such variable"):
        the_door_for(result)(program, result)


def test_the_declaration_table_still_answers_the_question_it_is_for():
    """Scope, stated where it can be argued with.

    Only the membership question moved. The variable-patch path still asks
    the declaration table, because a patch for a variable is answerable
    against what was declared about it — and no honest answer this suite
    produces exercises that path on a predicate the program names without
    declaring, so widening it too would be a change with no evidence
    behind it.
    """
    program, result = _pair(FRAMING)
    item = next(i for request in _requests(result)
                for i in request["items"]
                if (i.get("skeleton") or {}).get("kind") == "variable_patch")
    was, now = item["target"], "a_name_the_program_does_not_declare"
    # The framing note beside it is renamed too: a framing item without a
    # note is refused for THAT, one check earlier, and this is about the
    # check after it.
    for note in result.get("framing_notes") or ():
        if note.get("predicate") == was:
            note["predicate"] = now
    item["target"] = now
    item["skeleton"]["predicate"] = now
    item["said"]["predicate"] = now
    with pytest.raises(VerificationError, match="does not declare"):
        the_door_for(result)(program, result)
