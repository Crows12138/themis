"""What the browser's copy of the envelope says is THERE, against the schema.

``types.ts`` is a hand-written mirror of ``query_result.schema.json``, and the
module beside this one settles which top-level FIELDS it has. That is half of
what a type claims. The other half is which of them are guaranteed, and nothing
asked: a ``required`` dropped in the copying leaves the field there, with the
right type, merely optional — so the compiler asks the browser for a check the
envelope can never fail, and somebody writes a reader a line for a case that
does not exist. The other direction is worse. A field required here and not
guaranteed there is ``undefined`` wearing the type of a value, and the compiler
is on its side.

Both had happened. #497 fixed eight fields by hand, of which the compiler had
caught two — the two somebody had leaned on the guarantee for — and a probe
found the other six. Run against the file it was written for, this module found
116 more: 115 fields the schema guarantees and this one left optional, and
``LlmProposedReview.summary``, required here while no producer had ever written
it, no schema declared it, and nothing in ``src`` read it.

The reason nothing asked is that an interface and a schema shape had no way to
be the same thing. Matching them by name reaches 7 of 40 interfaces and gets
one of those wrong — ``CausationQuantity`` mirrors two shapes with different
guarantees — which is coverage's shape without coverage. So each interface now
NAMES the shape it copies, in ``MIRRORS``, and may name several: a field is
guaranteed only where every named shape requires it, so naming a second shape
can weaken a promise and never invent one.

What this reaches: the fields of a named interface. An inline object written in
a field's type has no name, so it cannot say what it mirrors; those fields are
counted here and the count is capped, which is the pressure to give the next
such shape a name rather than a place to put it.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from . import web_source

SCHEMAS = pathlib.Path(__file__).resolve().parent.parent / "themis" / "schemas"
HOME = "query_result.schema.json"

#: Slots typed with a shape that has no name, and so no row above. It can
#: shrink — by naming the shape — and cannot grow.
OUT_OF_REACH = 28


def _types() -> str:
    return web_source.read(web_source.TYPES)


def _mirrors(source: str) -> dict[str, list[str]]:
    return web_source.string_lists("MIRRORS", source)


def _written_off(source: str) -> dict[str, str]:
    return web_source.string_map("NOT_THE_ENVELOPE", source)


_files: dict[str, dict] = {}


def _schema(name: str) -> dict:
    if name not in _files:
        _files[name] = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return _files[name]


def _at(node, pointer: str, mirror: str):
    for step in pointer.split("/")[1:]:
        key = step.replace("~1", "/").replace("~0", "~")
        assert isinstance(node, dict) and key in node, (
            f"{mirror} points at nothing: no {key!r} there"
        )
        node = node[key]
    return node


def _shape(mirror: str) -> dict:
    """The object shape one mirror names.

    A ``$ref`` at the landing point is followed, because where a shape is
    WRITTEN is the schema's business and not this file's: ``derivation`` and
    the two halves of an occasion live in schema files of their own, and a
    reader that stopped at the reference would report them as shapeless.
    """
    file, _, pointer = mirror.partition("#")
    node = _at(_schema(file or HOME), pointer, mirror)
    for _ in range(10):
        if not (isinstance(node, dict) and "$ref" in node
                and "properties" not in node):
            return node
        target, _, sub = node["$ref"].partition("#")
        node = _at(_schema(target or file or HOME), sub, mirror)
    raise AssertionError(f"{mirror} chases references in a circle")


def _guarantees(mirror_list: list[str]) -> tuple[set[str], set[str]]:
    """(what every named shape requires, what any of them has room for)."""
    shapes = [_shape(m) for m in mirror_list]
    required = [set(s.get("required", ())) for s in shapes]
    present = [set(s.get("properties", {})) for s in shapes]
    return set.intersection(*required), set.union(*present)


def _disagreements(source: str) -> list[str]:
    """Every field whose promise here is not the promise there."""
    found = []
    for name, mirror_list in sorted(_mirrors(source).items()):
        guaranteed, anywhere = _guarantees(mirror_list)
        for field, declared in sorted(web_source.interface_fields(
                name, source).items()):
            if field not in anywhere:
                found.append(
                    f"{name}.{field} is declared here and no shape "
                    f"{name} mirrors has room for it"
                )
            elif field in guaranteed and declared.optional:
                found.append(
                    f"{name}.{field} is optional here and guaranteed by "
                    f"every shape {name} mirrors"
                )
            elif field not in guaranteed and not declared.optional:
                short = [m.rsplit("/", 1)[-1] for m in mirror_list
                         if field not in set(_shape(m).get("required", ()))]
                found.append(
                    f"{name}.{field} is promised here and not guaranteed by "
                    f"{short}"
                )
    return found


# --- the table itself ---------------------------------------------------------


def test_every_interface_says_which_shape_it_mirrors():
    """Exactly one answer per interface.

    None is the failure: a shape nobody related to the schema is a shape whose
    promises nothing reads. Two would be worse — an interface both mirroring
    and written off has said opposite things about itself in one file.
    """
    source = _types()
    for name in web_source.interface_names(source):
        holders = [table for table, members in
                   (("MIRRORS", _mirrors(source)),
                    ("NOT_THE_ENVELOPE", _written_off(source)))
                   if name in members]
        assert holders, (
            f"types.ts declares interface {name} and says nothing about what "
            f"it is a copy of: name the schema shape in MIRRORS, or say in "
            f"NOT_THE_ENVELOPE that the kernel has no such shape"
        )
        assert len(holders) == 1, f"{name} is in {holders}"


def test_neither_table_names_a_shape_this_file_does_not_declare():
    """The other direction: a row for an interface nobody wrote reads as
    coverage and is not."""
    source = _types()
    declared = set(web_source.interface_names(source))
    for table, members in (("MIRRORS", _mirrors(source)),
                           ("NOT_THE_ENVELOPE", _written_off(source))):
        stray = sorted(set(members) - declared)
        assert not stray, f"{table} names {stray}, which types.ts does not declare"


@pytest.mark.parametrize("name", sorted(_mirrors(_types())))
def test_every_named_shape_is_a_shape_with_fields(name):
    """A pointer that lands on a description, an enum or nothing would make
    every promise under it vacuously true — the failure this whole module is
    written against, one level up."""
    for mirror in _mirrors(_types())[name]:
        shape = _shape(mirror)
        assert isinstance(shape, dict) and shape.get("properties"), (
            f"MIRRORS[{name}] names {mirror}, which declares no properties"
        )


def test_every_row_of_the_written_off_table_gives_a_reason():
    """An empty string satisfies the partition and answers nothing."""
    for name, why in _written_off(_types()).items():
        assert why.strip(), f"NOT_THE_ENVELOPE[{name}] gives no reason"


def test_a_shape_written_off_is_not_reached_from_one_that_mirrors():
    """The only way out of the table is held to a claim it can fail.

    Otherwise the escape hatch is the place to put the next nested shape, and
    a shape the envelope really carries would sit under a row saying the
    kernel has no such thing.
    """
    source = _types()
    written_off = _written_off(source)
    for name in sorted(_mirrors(source)):
        for field, declared in web_source.interface_fields(name, source).items():
            named = set(re.findall(r"\b([A-Z]\w+)", declared.type))
            reached = sorted(named & set(written_off))
            assert not reached, (
                f"{name}.{field} is typed {declared.type!r}, which reaches "
                f"{reached} — NOT_THE_ENVELOPE says the kernel has no such "
                f"shape, and an interface that mirrors one carries it"
            )


# --- the promises -------------------------------------------------------------


def test_what_the_browser_promises_is_what_the_envelope_guarantees():
    source = _types()
    found = _disagreements(source)
    assert not found, "\n".join(found)


def test_the_slots_no_mirror_can_reach_are_counted():
    """A shape written inline in a type has no name, so it cannot say what it
    mirrors, and everything inside it is outside every rule above. Capped
    rather than ignored: the honest directions are down and unchanged."""
    source = _types()
    unnamed = sorted(
        f"{name}.{field}"
        for name in web_source.interface_names(source)
        for field, declared in web_source.interface_fields(name, source).items()
        if "{" in declared.type
    )
    assert len(unnamed) <= OUT_OF_REACH, (
        f"types.ts now points {len(unnamed)} slots at a shape with no name, "
        f"up from {OUT_OF_REACH}: {unnamed}. Give the shape a name and a row "
        f"in MIRRORS rather than adding to what nothing checks"
    )


# --- what each rule says no to ------------------------------------------------


def _edited(old: str, new: str) -> str:
    source = _types()
    assert old in source, f"the source no longer contains {old!r}"
    return source.replace(old, new, 1)


def test_a_dropped_guarantee_is_caught():
    """The failure that opened this: a `required` lost in the copying."""
    found = _disagreements(
        _edited("  sample_size: number", "  sample_size?: number"))
    assert any("NumericEstimate.sample_size is optional here" in line
               for line in found), found


def test_a_promise_the_envelope_does_not_make_is_caught():
    """The dangerous direction: `undefined` wearing the type of a value."""
    found = _disagreements(_edited("  form?: string", "  form: string"))
    assert any("Simex.form is promised here" in line for line in found), found


def test_a_field_no_shape_has_room_for_is_caught():
    """What `summary` was: declared, required, never sent, never read."""
    found = _disagreements(_edited("  form?: string", "  eta: number; form?: string"))
    assert any("Simex.eta is declared here" in line for line in found), found


def test_a_second_mirror_can_only_weaken_a_promise():
    """Naming another shape is how a promise is given up, and it cannot be
    how one is made: the intersection is over shapes, so a field guaranteed
    by the second and not the first stays optional."""
    both, _ = _guarantees(["#/$defs/causationQuantity", "#/$defs/causationEstimate"])
    alone, _ = _guarantees(["#/$defs/causationEstimate"])
    assert "ci_lower" in alone and "ci_lower" not in both
