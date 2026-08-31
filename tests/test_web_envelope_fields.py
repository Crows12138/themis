"""Every field the envelope can carry, and what the browser does with it.

``blocks.py`` asks each block how it reaches a reader and holds the answer
to a surface. It stops at ``extensions`` and says why: the typed fields of
``QueryResult`` are declared once and a misspelling is an ``AttributeError``,
while an ``extensions`` key is a string literal and a misspelling there is
silence. That boundary is about SPELLING. The register then grew ``read_as``
and ``carried_by``, which are about REACHING — a question that holds exactly
as well for a field — and the boundary stayed where the older reason had put
it.

So the browser's mirror of the envelope was never asked. Measured before
this module existed: of twenty-one top-level fields the schema declares,
``types.ts`` named thirteen, three of those were read by nothing anywhere in
``src`` — an interface entry is a claim about use and nothing checked it —
and eight were absent. Ten reached a reader.

``derivation`` was one of the eight, which is what makes it the case worth
naming: 570 of 1627 envelopes in one suite run carry a chain, across ten
query kinds, and it is the only answer to "how was this arrived at" that
every answered result has — a route is written as a block only when an
identification pattern was recognised. The report was given the chain when
the same defect was found on that surface; nothing noticed that the claim
was still false here, because nothing had ever read this file.

What is checked: the three lists in ``types.ts`` partition the schema's
top-level fields against the interface, a carrier is a field this surface
really shows, a declared field is read by something outside the type, and
the one list that admits work remains cannot grow.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from . import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json").read_text(
        encoding="utf-8")
)
ENVELOPE_FIELDS = set(SCHEMA["properties"])

#: The size of ``NOT_YET_SAID_HERE`` when it was written. A cap rather than a
#: baseline file: the list names things this surface owes a reader, and the
#: only honest directions are down and unchanged. Lower this when one goes.
#: It started at 3 and is 0: two of the three were the estimate metadata this
#: surface now states, and the third was never missing — 94% of its lines were
#: a gap description this surface already renders, and the rest were withdrawn
#: or belonged to an estimator gap of their own.
STILL_OWED = 0


def _types() -> str:
    return web_source.read(web_source.TYPES)


def _declared() -> set[str]:
    return web_source.top_level_keys(
        web_source.interface_body("QueryResult", _types()))


def _list(name: str) -> dict[str, str]:
    return web_source.string_map(name, _types())


def _accounts() -> dict[str, set[str]]:
    return {
        "declared in QueryResult": _declared(),
        "CARRIED_BY": set(_list("CARRIED_BY")),
        "NOT_FOR_A_READER": set(_list("NOT_FOR_A_READER")),
        "NOT_YET_SAID_HERE": set(_list("NOT_YET_SAID_HERE")),
    }


@pytest.mark.parametrize("field", sorted(ENVELOPE_FIELDS))
def test_the_browser_says_what_it_does_with_every_field(field):
    """Exactly one answer per field.

    None is the failure this module is for: an omission and a decision to
    omit are the same absence in a type. Two would be worse than none — a
    field both declared and written off has said opposite things about
    itself in one file.
    """
    holders = [name for name, members in _accounts().items()
               if field in members]
    assert holders, (
        f"the envelope can carry {field!r} and types.ts says nothing about "
        f"it: declare it in QueryResult, or name what carries it, or say "
        f"why nothing here shows it"
    )
    assert len(holders) == 1, f"{field!r} is in {holders}"


def test_every_written_off_field_names_one_of_the_declared_audiences():
    """The value answers WHO, and who is a closed set.

    It was a sentence per field, which made four unrelated notes out of one
    fact with three values — and a sentence can be written for anything,
    while picking one of three is a claim that can be wrong. The union is
    read out of the same file, so the file stays the source of both halves
    rather than this module holding a second copy of the set.
    """
    source = _types()
    declared = re.search(r"export type Audience\s*=\s*([^\n]+)", source)
    assert declared, "types.ts declares no Audience union to check against"
    audiences = set(re.findall(r"'([^']+)'", declared.group(1)))
    assert len(audiences) >= 2, "a one-member set is not a classification"
    said = _list("NOT_FOR_A_READER")
    assert said, "the table is empty; there is nothing to classify"
    stray = sorted(set(said.values()) - audiences)
    assert not stray, (
        f"NOT_FOR_A_READER names {stray}, which Audience does not declare"
    )


def test_the_accounting_claims_nothing_the_envelope_cannot_carry():
    """The other direction. A row for a field the schema dropped reads as
    coverage and is not — the same both-ways check the vocabulary tables
    get, one level up."""
    for name, members in _accounts().items():
        if name == "declared in QueryResult":
            # The interface also declares shapes the envelope nests rather
            # than tops (`derivation` vs `DerivationStep`); only the field
            # names are the schema's business.
            continue
        stray = sorted(members - ENVELOPE_FIELDS)
        assert not stray, (
            f"{name} names {stray}, which query_result.schema.json does not "
            f"declare at the top level"
        )
    assert _declared() <= ENVELOPE_FIELDS, sorted(_declared() - ENVELOPE_FIELDS)


@pytest.mark.parametrize("field", sorted(_declared()))
def test_a_field_this_surface_declares_is_read_by_something_there(field):
    """A type entry is a claim about use, and this asks whether anything
    keeps it.

    Three fields failed this when it was written — ``query_id``,
    ``explanation`` and ``investigation_requests`` — and a declared field
    nothing reads is worse than an absent one: it is the omission wearing
    the shape of coverage. Import lines are stripped from the haystack for
    the reason the vocabulary check strips them: a component that stops
    rendering something keeps importing it.

    A property access by name, not a type-aware read: what it proves is
    that a call site exists, which is the weaker half of ㊷ and the half
    that catches the failure that actually happened here.
    """
    elsewhere = web_source.sources_that_could_read(exclude=web_source.TYPES)
    assert re.search(rf"\.{field}\b", elsewhere), (
        f"types.ts declares {field} and nothing in src reads it; either read "
        f"it or move it to one of the three lists"
    )


def test_a_carrier_is_a_field_this_surface_really_shows():
    """``carried_by`` names a member of an existing table for this reason:
    a carrier nobody renders carries nothing, and the claim is then a
    second way of saying the field is dropped."""
    declared = _declared()
    for field, carrier in _list("CARRIED_BY").items():
        assert carrier in declared, (
            f"types.ts says {field} is carried by {carrier}, which this "
            f"surface does not declare"
        )


def test_every_row_of_the_two_prose_lists_gives_a_reason():
    """An empty string satisfies the partition and answers nothing."""
    for name in ("NOT_FOR_A_READER", "NOT_YET_SAID_HERE"):
        for field, why in _list(name).items():
            assert why.strip(), f"{name}[{field}] gives no reason"


def test_the_list_that_admits_work_remains_cannot_grow():
    """The list is honest only while it shrinks.

    Without a cap it is a place to put the next field instead of deciding
    about it, which is what "the rest is passthrough" was.
    """
    owed = _list("NOT_YET_SAID_HERE")
    assert len(owed) <= STILL_OWED, (
        f"NOT_YET_SAID_HERE has grown to {sorted(owed)}; a field this "
        f"surface owes a reader is a defect to fix, not an entry to add"
    )


# --- the chain, which is what all of this was found by ------------------------


def test_the_chain_is_one_of_the_fields_this_surface_reads():
    """Named rather than left to the sweep above.

    The sweep says every declared field is read; this says which field the
    module was written for, so that removing the section fails with the
    reason rather than as one anonymous parametrized case.
    """
    assert "derivation" in _declared()
    component = web_source.read(web_source.COMPONENT)
    # The argument list stops at the field: whether the chain is READ is not
    # a fact about what else the call takes, and pinning the whole call made
    # this fail when the renderer started being told the reader's language.
    assert re.search(r"derivationRows\(\s*result\.derivation\b", component), (
        "Verdict.tsx no longer asks for the derivation chain; the foldout "
        "is named for how the answer was computed, and the chain is the only "
        "answer to that question every answered result carries"
    )


def test_the_chain_is_stated_after_the_pattern_and_the_expression():
    """Order is a claim about what the reader wants first, and the two
    surfaces make the same one: which pattern on which set, then the
    expression, then the skeleton. A reader comparing them should not have
    to reconcile two orders.

    Located by where each section RENDERS, not by its words. This test used
    to find the middle section by the Chinese text in it, which stopped
    meaning "where it renders" the moment the reader-facing text moved into
    a table at the top of the file — the language layer's whole shape. A
    section's rendering point is a name, and a name is what an order is
    about.
    """
    component = web_source.read(web_source.COMPONENT)
    routes_at = component.index("routes.map(")
    formula_at = component.index("SAYS.idFormula")
    chain_at = component.index("chain.rows.map(")
    assert routes_at < formula_at < chain_at
