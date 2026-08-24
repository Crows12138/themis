"""#446: the nine framing fields, and every listing of them as a projection.

Five parts of the system ask a question about a variable declaration's
framing fields, and each of them used to answer by listing all nine names
again. Ten such lists existed. Nothing derived any of them from any other,
and nothing held any two equal — one of them said so in prose instead:
``_PATCH_DISPLAY_FIELDS`` carried "must stay in sync with
``_PATCHABLE_FIELDS`` — any shape change needs coordinated edits in both
modules", which was the whole enforcement, and which had already stopped
being true. A list that has to agree with another list is a derivation
written as a copy.

:mod:`themis.framing` is the declaration. The six Python listings are
projections of it, so nothing below has to check those against each other
— they are the same object. What is left to check is the boundary: the
three listings that cannot import Python (the dataclass's own field set,
the AST schema, the browser) and the census that says a new field cannot
be added without deciding what it is.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re

import pytest

from themis import framing
from themis.runtime import framing_check
from themis.types import VariableDeclaration
from themis.upstream import narrative_merge
from themis.web import app as webapp
from themis.workflow import variable_framing

from . import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = REPO / "themis" / "schemas" / "kernel_ast.schema.json"

#: The fields on the declaration that are not framing fields, each with the
#: reason it is not one. Named rather than subtracted, so that adding a
#: field to the declaration is a decision somebody records here or in the
#: table, and never a silent third category.
NOT_FRAMING = {
    "predicate": "identifies the variable rather than saying what it means",
    "scale": "a claim about what the DATA holds, reconciled against a column",
    "defaulted": "names members of the table rather than being one",
}


def _declaration() -> dict:
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return doc["$defs"]["variableDeclaration"]


# ------------------------------------------------------- the table itself

def test_both_halves_of_what_the_form_asks_are_doing_work():
    """``asked`` is a conjunction, and a conjunction whose second half
    never excludes anything is a longer way of writing the first. One
    field is left out for each reason — ``unit`` because its absence is
    not reported, ``domain`` because a default cannot answer it — so the
    derivation is not two names for one projection."""
    assert set(framing.reported()) - set(framing.asked()) == {"domain"}
    assert set(framing.defaultable()) - set(framing.asked()) == {"unit"}


def test_the_one_field_that_is_not_a_single_value_is_the_one_with_branches():
    """Every walk over these fields has a branch for a sequence. ``scalar``
    is what those branches are reading, so exactly one row may deny it —
    a second would mean a branch somewhere handles only the first."""
    assert [f.name for f in framing.FIELDS if not f.scalar] == ["domain"]


def test_the_projections_are_projections():
    """The six Python listings ARE these calls, so this states what each
    one means rather than comparing two lists — the comparison the old
    arrangement needed is what stopped existing."""
    assert framing_check._REPORTABLE_FIELDS == framing.reported()
    assert variable_framing._DEFAULTABLE_FIELDS == frozenset(
        framing.defaultable())
    assert narrative_merge._FRAMING_FIELDS == framing.scalar()
    assert webapp._FILL_FIELDS == framing.asked()
    assert variable_framing._PATCHABLE_FIELDS == framing.names() + (
        framing.NAMES_THE_DEFAULTED,)


def test_the_view_of_a_settled_declaration_has_one_author():
    """Two modules had grown this walk, agreeing on every declaration
    anyone tried. They are one function; a second would be a second
    reading of the same table."""
    assert variable_framing._existing_view is framing.settled


# --------------------------------------------- the boundary, in both ways

def test_every_field_on_the_declaration_is_accounted_for():
    """The census. A field added to ``VariableDeclaration`` is either a
    framing field — in which case its three answers are decisions somebody
    made — or it is one of the named exceptions. There is no third place
    for it to be, which is what stops the table from silently covering
    less than it claims."""
    declared = {f.name for f in dataclasses.fields(VariableDeclaration)}
    assert declared == set(framing.names()) | set(NOT_FRAMING), (
        f"undecided: {sorted(declared - set(framing.names()) - set(NOT_FRAMING))}; "
        f"stale: {sorted((set(framing.names()) | set(NOT_FRAMING)) - declared)}"
    )


def test_the_ast_schema_declares_the_same_fields():
    """The schema cannot import the table, so it is held to it. A property
    there that the table does not carry is a field the kernel accepts and
    nothing asks a question about."""
    properties = set(_declaration()["properties"]) - {"kind"}
    assert properties == set(framing.names()) | set(NOT_FRAMING)


def test_the_schema_says_which_fields_a_default_can_answer():
    assert (_declaration()["properties"]["defaulted"]["items"]["enum"]
            == list(framing.defaultable()))


def test_the_browser_offers_the_fields_the_table_says_to_ask_about():
    """The third listing that cannot import Python. #400 held it level with
    ``_FILL_FIELDS``; both are this call now, so the browser is held to the
    table directly."""
    body = web_source.literal("FRAMING_FIELDS", web_source.read(
        web_source.VERDICT))
    assert tuple(re.findall(r"\{ key: '([^']+)'", body)) == framing.asked()


# ------------------------------------------- what each answer buys, stated

def test_a_field_no_variable_need_have_is_not_a_gap():
    """``unit``'s row is the only one that denies ``reported``, and this is
    what denying it does: a boolean outcome is not nagged for a physical
    unit it cannot have."""
    assert "unit" not in framing.reported()
    assert "unit" not in framing_check._gaps(VariableDeclaration(predicate="x"))


def test_the_levels_a_variable_ranges_over_have_no_standard_to_take():
    assert "domain" not in framing.defaultable()
    with pytest.raises(variable_framing.MalformedBundleError):
        variable_framing._incoming_defaulted("x", {"defaulted": ["domain"]})


def test_the_form_offers_no_blank_that_would_clear_nothing():
    """Two ways to get this wrong, and the derivation forecloses both: a
    blank for a field the check does not report clears nothing when filled,
    and one for a field a default cannot answer is unanswerable when left
    blank."""
    for name in webapp._FILL_FIELDS:
        assert name in framing.reported()
        assert name in framing.defaultable()


@pytest.mark.parametrize("field", framing.FIELDS, ids=lambda f: f.name)
def test_a_settled_field_reaches_the_view_in_the_shape_its_row_declares(field):
    """The census over the walk: a sequence is listed, a value is stored as
    it stands, and which of the two is read off the row rather than off the
    field's name."""
    value = ("a", "b") if not field.scalar else "settled"
    decl = VariableDeclaration(predicate="x", **{field.name: value})
    view = framing.settled(decl)
    assert view[field.name] == (value if field.scalar else list(value))
