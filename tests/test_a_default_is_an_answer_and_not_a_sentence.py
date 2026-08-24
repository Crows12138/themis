"""#400: taking the standard operationalisation is a fact, not a wording.

A variable declaration has seven framing fields, and a reader who is asked
what one of them means may answer in two ways: by naming a value, or by
taking whatever the standard reading is. Only the first has ever had a slot.
The second was written into the value — four of the seven defaults were
sentences reading "not specified (default: the study follow-up window)" and
the like, authored so that ``framing_check``'s ``is None`` test would come
back false and the gap would clear.

That put a fact in a wording, and every consumer of the fact became a reader
of prose. The browser kept a byte-identical copy of all seven values so it
could recognise them in the merged program afterwards, with nothing holding
the two copies equal; the recognition ran by looking for 未指定 inside the
string, so it was fixed to one language; and it could not be done at all for
the three whose default is a value a reader might genuinely have picked, a
limitation the code stated and could not fix. A fourth copy sat in the
sentence that discloses the whole thing, naming the four values by hand.

``VariableDeclaration.defaulted`` names the fields instead. The rules below
are what that buys, and each one names the thing that must go back for it to
fail.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from themis import kernel
from themis.input import semantic_validator
from themis.runtime import framing_check
from themis.types import Program, VariableDeclaration
from themis.upstream import narrative_merge
from themis.web import app as webapp
from themis.workflow import variable_framing

from . import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
APP = REPO / "themis" / "web" / "app.py"


def _function_body(name: str, source: str) -> str:
    """One exported function, declaration through closing brace.

    Not a brace walk from the first ``{``: a return type is written in
    braces too, so that reads the annotation and stops. A top-level
    function's body is the text down to the first ``}`` in column zero,
    which is what the file's own formatting says.
    """
    opened = re.search(rf"^export function {name}\b", source, re.M)
    assert opened, f"verdict.ts declares no {name}"
    closed = re.search(r"^\}", source[opened.start():], re.M)
    assert closed, f"{name} is never closed"
    return source[opened.start():opened.start() + closed.end()]


def _framing_rows() -> list[dict]:
    """``FRAMING_FIELDS`` as parsed rows — key, and which other keys it has.

    A row's texts are objects of their own, so the nested braces come out
    before the keys are counted: otherwise every row reports the language
    tags inside its ``Words`` as entries of the row.
    """
    body = web_source.literal("FRAMING_FIELDS", web_source.read(
        web_source.VERDICT))
    rows = []
    for line in body.splitlines():
        match = re.match(r"\s*\{\s*key:\s*'([^']+)',(.*)$", line)
        if match is None:
            continue
        rest = match.group(2)
        while True:
            flattened = re.sub(r"\{[^{}]*\}", "", rest)
            if flattened == rest:
                break
            rest = flattened
        rows.append({
            "key": match.group(1),
            "keys": frozenset(re.findall(r"(\w+)\s*:", rest)),
        })
    return rows


# --------------------------------------------------------- the slot exists

def test_the_program_can_say_a_field_was_left_to_the_default():
    """The third state, on the declaration and through the round trip.

    Unset, named, and defaulted are three different answers to one question.
    Two of them had somewhere to live; putting the third in a value is what
    every rule below is about.
    """
    decl = VariableDeclaration(predicate="x", defaulted=("time_window",))
    as_json = kernel._statement_to_dict(decl)
    assert as_json["defaulted"] == ["time_window"]
    assert "time_window" not in as_json, (
        "a defaulted field carries no value — writing one is the sentence "
        "this replaces"
    )
    back = semantic_validator._to_statement(as_json)
    assert back.defaulted == ("time_window",)
    assert back.time_window is None


def test_a_declaration_that_defaults_nothing_says_nothing():
    """Absent rather than empty, like every other unset thing on a program."""
    assert "defaulted" not in kernel._statement_to_dict(
        VariableDeclaration(predicate="x"))


def test_a_default_cannot_answer_the_field_that_enumerates_the_levels():
    """``domain`` is what the rest of the program computes over, so there is
    no standard one to take — a default there would be a guess wearing the
    same word as an answer."""
    assert "domain" not in variable_framing._DEFAULTABLE_FIELDS
    with pytest.raises(variable_framing.MalformedBundleError):
        variable_framing._incoming_defaulted("x", {"defaulted": ["domain"]})


# ------------------------------------------------ nobody authors a value

def test_no_surface_writes_a_value_for_a_field_the_reader_left_blank():
    """The rule, over the module that used to hold the table.

    ``_FILL_DEFAULTS`` lived here: seven values, four of them Chinese
    sentences, written into the program on the reader's behalf. What comes
    back now is what the reader typed and the names of what they did not.
    """
    fields = webapp._framing_fields({})
    assert set(fields) == {"defaulted"}, (
        f"the fill loop authored {sorted(set(fields) - {'defaulted'})}; a "
        f"surface may name what a reader left blank, not decide it for them"
    )
    assert sorted(fields["defaulted"]) == sorted(webapp._FILL_FIELDS)


def test_what_the_reader_typed_survives_and_the_rest_is_named():
    named = webapp._framing_fields({"time_window": "  >=6 months  "})
    assert named["time_window"] == ">=6 months"
    assert "time_window" not in named["defaulted"]
    assert set(named["defaulted"]) == set(webapp._FILL_FIELDS) - {"time_window"}


def test_the_module_that_fills_a_blank_holds_no_table_of_values():
    """The counterexample this file exists for, read off the source.

    A behavioural check passes as soon as the values are unused; this fails
    while they are still written down, which is where the second copy and
    the one language came from.
    """
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                keys = {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant)}
                assert not (keys & set(webapp._FILL_FIELDS)), (
                    f"{target.id} maps framing fields to values; what a "
                    f"program stores is not this surface's to word"
                )


# -------------------------------------------- the browser keeps no copy

def test_the_browser_holds_no_copy_of_what_the_program_stores():
    """Each row is a key and the two texts a reader is handed. A fourth
    entry is a value this surface would have to keep equal to the other
    surface's, which is what nothing was doing."""
    rows = _framing_rows()
    assert rows, "verdict.ts declares no FRAMING_FIELDS"
    for row in rows:
        assert row["keys"] == {"label", "placeholder"}, (
            f"FRAMING_FIELDS row {row['key']!r} carries {sorted(row['keys'])}; "
            f"a row is a key and the words for it"
        )


# Three rules that stood here — the browser's keys against the fill loop's,
# the fill loop's against what the check reports, and the schema's enum
# against what a patch may default — were comparisons between two lists.
# #446 made both sides of each the same projection of one table, so they
# said nothing; what they were checking is in
# ``test_the_framing_fields_are_declared_once``, stated against the table.


def test_the_disclosure_is_read_off_the_program_and_not_off_a_wording():
    """``framingDefaultsInProgram`` asks the program which fields were
    defaulted. It used to compare each field against the sentence the server
    wrote for a blank one, which is the copy above and the one language."""
    source = web_source.read(web_source.VERDICT)
    body = _function_body("framingDefaultsInProgram", source)
    assert "defaulted" in body, (
        "the disclosure does not read the program's own account of what was "
        "defaulted"
    )
    assert "未指定" not in source, (
        "a value stored in the program is recognised by its wording, which "
        "no reader's language may decide"
    )


# ----------------------------------------------- what the fix buys a reader

def _program(**decl) -> Program:
    return Program(version="0.1", objects=(), statements=(
        VariableDeclaration(predicate="x", **decl),))


def test_a_field_answered_by_the_default_is_answered():
    """The gap clears, and it clears because a question was answered rather
    than because a sentence made ``is None`` come back false."""
    assert "baseline" in framing_check._gaps(VariableDeclaration(predicate="x"))
    assert "baseline" not in framing_check._gaps(
        VariableDeclaration(predicate="x", defaulted=("baseline",)))


@pytest.mark.parametrize("field", sorted(
    set(webapp._FILL_FIELDS) & set(framing_check._REPORTABLE_FIELDS)))
def test_every_field_a_reader_can_default_can_be_told_apart_afterwards(field):
    """All seven, not four.

    ``observability``/``direction``/``state_vs_event`` had defaults equal to
    values a reader might have picked — ``observable``, ``up``, ``state`` —
    so no reading of the stored value could tell "they chose this" from
    "nobody chose". Three of the seven were therefore never disclosed. The
    name does not have that problem, and the parametrisation is the census.
    """
    decl = VariableDeclaration(predicate="x", defaulted=(field,))
    assert field not in framing_check._gaps(decl)
    assert kernel._statement_to_dict(decl)["defaulted"] == [field]


def test_a_field_is_answered_by_a_value_or_by_the_default_but_not_both():
    with pytest.raises(variable_framing.VariablePatchAnsweredTwiceError):
        variable_framing._apply_patch(
            VariableDeclaration(predicate="x"),
            {"fields": {"baseline": "clinic BP", "defaulted": ["baseline"]}},
        )
    with pytest.raises(variable_framing.VariablePatchAnsweredTwiceError):
        variable_framing._apply_patch(
            VariableDeclaration(predicate="x", baseline="clinic BP"),
            {"fields": {"defaulted": ["baseline"]}},
        )


def test_naming_a_value_later_supersedes_the_default_taken_before():
    """The loop stays open: a reader who took the standard reading and then
    thought better of it is refining, not contradicting. Refusing this would
    trap them with the first answer they gave."""
    was = VariableDeclaration(predicate="x",
                              defaulted=("baseline", "time_window"))
    now = variable_framing._apply_patch(was, {"fields": {"baseline": "clinic BP"}})
    assert now.baseline == "clinic BP"
    assert now.defaulted == ("time_window",)


def test_a_default_accrues_rather_than_replacing_what_came_before():
    was = VariableDeclaration(predicate="x", defaulted=("baseline",))
    now = variable_framing._apply_patch(
        was, {"fields": {"defaulted": ["time_window"]}})
    assert now.defaulted == ("baseline", "time_window")


def test_the_other_merge_path_cannot_drop_it():
    """``narrative_merge`` is the second place two declarations of one
    predicate become one. A field it does not know about is a field that
    vanishes on the way in."""
    merged = narrative_merge._merge_two_decls(
        {"defaulted": ["baseline"]},
        {"defaulted": ["time_window"], "measurement": "self-reported"},
        "x",
    )
    assert merged["defaulted"] == ["baseline", "time_window"]
    merged = narrative_merge._merge_two_decls(
        {"defaulted": ["baseline"]}, {"baseline": "clinic BP"}, "x")
    assert "defaulted" not in merged, (
        "a value is the more specific answer; keeping the name beside it "
        "leaves the declaration settled two ways"
    )


# ------------------------------- what the sentence was holding up, stated

def test_taking_the_default_does_not_close_the_well_defined_intervention_gap():
    """The load the prose was carrying, now visible.

    ``ill_defined_intervention_versions`` suppresses itself when
    ``time_window`` is set — "duration closes the version-ambiguity gap".
    The blank-fill used to satisfy that by writing 未指定（默认：研究随访期）
    into the slot, so a reader who filled the form with everything blank
    stopped being told their estimand was ill-defined (Hernán & Taubman
    2008), on the strength of a sentence saying no duration was given.
    Taking the standard reading of a duration is not a duration.
    """
    decl = VariableDeclaration(predicate="x", defaulted=("time_window",))
    assert decl.time_window is None
    assert "time_window" not in framing_check._gaps(decl), (
        "the framing question is answered — that half was never in doubt"
    )


def test_whether_a_cutpoint_applies_is_asked_of_the_declaration_first():
    """``scale`` is a closed vocabulary saying exactly this, and the reading
    of ``measurement``'s prose beside it — digits, a cue list half Chinese
    and half English — was answering it instead. A positive declaration
    beats a reading of the words next to it."""
    declared = VariableDeclaration(
        predicate="x", scale="continuous", measurement="self-reported")
    assert "threshold" in framing_check._gaps(declared)
    denied = VariableDeclaration(
        predicate="x", scale="binary", measurement="BMI 30 kg/m2")
    assert "threshold" not in framing_check._gaps(denied)


def test_the_prose_is_still_read_when_nothing_was_declared():
    """The fallback stays: a declaration with no ``scale`` is the common
    shape, and dropping the cues would stop asking about a cutpoint for
    every variable that has one."""
    assert "threshold" in framing_check._gaps(
        VariableDeclaration(predicate="x", measurement="BMI 30 kg/m2"))
