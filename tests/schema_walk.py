"""Walking the contracts, for the gates that ask something of every key.

Two of them do. One asks whether the block a key belongs to says it out loud;
the other asks whether "there is none" has one spelling here or two. Both need
the same traversal — follow ``$ref`` while it stays inside the document, and
descend into array items — and the traversal is the part that is easy to get
subtly wrong: a walk that stops at a ``$ref`` drops a whole subtree out of the
denominator and reads exactly like a subtree with nothing to answer for. One
copy, because two would be a pair of tables that were once equal.

``allOf`` is deliberately not merged. Every one of them is an ``if``/``then``
pair, and a key a ``then`` requires is required only on that branch — folding
it into the unconditional ``required`` set would report a key that CAN be
absent as one that never is, which is the opposite of what both questions are
for.

**Which document is an argument, not this module's identity.** It used to be
a module constant read from ``query_result.schema.json``, with ``resolve``
closed over it, and that one line decided the denominator of every gate built
on the walk: one file out of thirteen. The absence rule then read as a rule
about one contract, which is not what it says — and nineteen key paths in
five other shipped documents sat in the shape it forbids, unasked (#429). The
fix is not a list of the other filenames. There was no list to add to: the
walk could not have followed a ``$ref`` in another document because it did
not know which document it was in.

So a document carries its own resolution, :func:`shipped` answers "which
documents" by globbing the directory — a glob cannot go stale the way a
transcribed list can — and the gates say which ones they mean.
"""
from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
from typing import Iterator

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"


@dataclasses.dataclass(frozen=True)
class Document:
    """One schema file, and the ``$ref`` resolution that belongs to it."""

    name: str
    spec: dict

    def resolve(self, spec: dict) -> dict:
        """Follow ``$ref`` while it stays inside THIS document.

        Both spellings appear: ``#/$defs/name`` and a JSON pointer into
        ``properties``. The joint mediation block reaches the single-mediator
        one that way. A reference out of the document — the atom shape lives
        in ``atom.schema.json`` — resolves to nothing on purpose: that
        document is another subject with its own readers, and pulling it in
        here would put one vocabulary's completeness under two files.
        """
        seen = 0
        while isinstance(spec, dict) and "$ref" in spec and seen < 20:
            ref = spec["$ref"]
            if not ref.startswith("#/"):
                return {}
            node: object = self.spec
            for step in ref[2:].split("/"):
                if not isinstance(node, dict) or step not in node:
                    return {}
                node = node[step]
            spec, seen = node if isinstance(node, dict) else {}, seen + 1
        return spec if isinstance(spec, dict) else {}

    def walk(self, spec: dict | None = None, path: tuple[str, ...] = (),
             depth: int = 0) -> Iterator[tuple[tuple[str, ...], dict, dict]]:
        """Every declared key below ``spec``, as ``(path, subschema, container)``.

        Defaults to the whole document. The container comes back resolved
        rather than pre-digested, because what each caller wants of it differs
        — one reads ``required``, the other reads ``dependentRequired`` and
        the sibling shapes — and a walk that answered both questions itself
        would have to be changed for the third.
        """
        if depth > 8:
            return
        spec = self.resolve(self.spec if spec is None else spec)
        for name, sub in (spec.get("properties") or {}).items():
            yield path + (name,), sub, spec
            yield from self.walk(sub, path + (name,), depth + 1)
        items = spec.get("items")
        if isinstance(items, dict):
            yield from self.walk(items, path + ("[]",), depth + 1)
        # A branch is still this path: the sufficient-statistics record is one
        # of two object shapes, and a walk that stopped at the choice would
        # leave every key inside both of them undeclared as far as any gate
        # can tell.
        for keyword in ("oneOf", "anyOf"):
            for branch in spec.get(keyword) or ():
                if isinstance(branch, dict):
                    yield from self.walk(branch, path, depth + 1)


@functools.lru_cache(maxsize=None)
def named(name: str) -> Document:
    """The shipped document called ``name``."""
    return Document(name, json.loads(
        (SCHEMAS / name).read_text(encoding="utf-8")))


def shipped() -> tuple[Document, ...]:
    """Every schema this package ships, by name.

    Globbed rather than transcribed. A list would have to be edited by whoever
    adds a document, which is the same as saying a new document joins the
    build unasked whenever they don't.
    """
    return tuple(named(p.name) for p in sorted(SCHEMAS.glob("*.schema.json")))


#: The result contract, for the gates whose question is about it in particular.
RESULT = named("query_result.schema.json")


def nullable(sub: dict) -> bool:
    """Whether ``null`` is one of the values this key may take.

    Two spellings, both in use: ``"type": [..., "null"]`` and a ``oneOf``
    branch that is nothing but ``{"type": "null"}``. Reading only the first
    reports a key that can be null as one that cannot, which is the shape of
    blindness the gate above exists to refuse.
    """
    if not isinstance(sub, dict):
        return False
    declared = sub.get("type")
    types = {declared} if isinstance(declared, str) else set(declared or ())
    if "null" in types:
        return True
    for keyword in ("oneOf", "anyOf"):
        for branch in sub.get(keyword) or ():
            if isinstance(branch, dict) and branch.get("type") == "null":
                return True
    return False
