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
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import (
    _SKELETON_KINDS, declarations_of, verify_investigation_items,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES if SHAPES[n]["result"].get("investigation_requests"))

#: A shape whose framing request patches two variables, and one whose
#: structure items are the citable kind the coverage rule reads.
FRAMING = "backdoor_linear"
STRUCTURE = "iv_wald"
EDGES = "scm_counterfactual_linear_fit"


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
    assert len(CARRIERS) == 39
    groups = {r.get("group") for n in CARRIERS
              for r in _requests(SHAPES[n]["result"])}
    assert groups == {"framing", "assumption", "structure"}


def test_a_framing_target_is_a_framing_note_predicate():
    """The link the exemption rests on, stated as a number.

    T10-2 lets a framing item go uncited because the note beside it is
    cited instead. That is only true while the two name the same thing,
    which nothing checked.
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
    assert linked == 75


def test_the_patch_is_answerable_from_the_program_alone():
    """Every skeleton key is a field a variable declaration has, and the
    program agrees about which of them are set."""
    checked = 0
    for name in CARRIERS:
        program, result = _pair(name)
        declared = declarations_of(validate_program(program))
        for request in _requests(result):
            for item in request.get("items") or []:
                skeleton = item.get("skeleton") or {}
                if not skeleton:
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
    assert checked == 529


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
        if not already(result):
            continue
        tried += 1
        with pytest.raises(VerificationError, match="already declares it"):
            themis.verify(program, result)
    assert tried == 28


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
    """
    result = SHAPES["causation_plugin"]["result"]
    _, item = _first_item(result, "assumption")
    assert item["said"] == {"note": ""}
    _verify_with("causation_plugin",
                 lambda r: _first_item(r, "assumption")[1]["said"]
                 .update(note="anything at all"))


def test_the_request_level_target_and_group_are_declared_not_held():
    """Counted, so that "we closed the list" cannot be said.

    A request's own ``target`` is a derived label — ``define_variable:
    2_items`` on thirty-eight of forty-three — and holding it means
    restating the producer's format, which #527 put out of bounds: the
    spelling belongs to whoever writes it. ``group`` pairs one-to-one
    with ``action`` across the corpus, and a table built from what the
    corpus happens to contain is the exact shape that produced a false
    refusal one frontier earlier.
    """
    survived = []
    for name in CARRIERS:
        for path in ("target", "group"):
            for bend in ("_forged", "", "x"):
                program, result = _pair(name)
                was = result["investigation_requests"][0].get(path)
                if was is None:
                    continue
                result["investigation_requests"][0][path] = (
                    str(was) + bend if bend == "_forged" else bend)
                try:
                    themis.verify(program, result)
                except Exception:
                    continue
                survived.append((name, path))
                break
    assert len(survived) == 45
    assert {p for _, p in survived} == {"target", "group"}


def test_the_rule_is_silent_where_there_is_no_list_to_read():
    """Not a skip: an answer that asks for nothing makes no claim about
    what a reader should supply."""
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        assert not _requests(result)
        verify_investigation_items(result, object())
