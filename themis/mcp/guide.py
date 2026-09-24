"""The agent's documents, a section at a time.

The documents that teach an agent to drive Themis are written as complete
references — the rendering guide alone is about 160,000 characters — and
a resource is read whole. In the first real test through MCP, Claude Code
moved both documents the agent opened to files because they were too
large to hand over, and a client without file access would have had
neither. So they are also served by section: a table of contents, then
whichever section the agent needs, each under the same budget as a result.

A markdown section too large for the budget is handed over as its own
opening text and the names of its subsections; a section with no
subsections that is still too large comes in consecutive slices, each
saying where the next begins. A schema is served by definition, and
anything in a definition too large to hand over is folded the way a
result is (:mod:`themis.output.bounded_view`), with a JSON Pointer that
this same call accepts as the section. Following every entry gives back
the document exactly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from themis.output import bounded_view

#: A heading line, outside fenced code.
_HEADING = re.compile(r"^(#{1,6}) +(.+?) *#* *$")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")

#: What joins a heading to the one it sits under, in a section's name.
_JOIN = " > "


@dataclass
class _Section:
    name: str          # the path of titles, joined — unique within a document
    level: int
    start: int         # where its heading line begins
    body: int          # where the text under the heading begins
    end: int = 0
    children: list["_Section"] = field(default_factory=list)


def _outline(text: str) -> _Section:
    """The heading tree of a markdown document; the root is the text before
    the first heading, named ``""``."""
    root = _Section("", 0, 0, 0, len(text))
    stack = [root]
    fenced = False
    at = 0
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            fenced = not fenced
        m = None if fenced else _HEADING.match(line.rstrip("\r\n"))
        if m:
            level = len(m.group(1))
            while stack[-1].level >= level:
                stack.pop().end = at
            parent = stack[-1]
            title = m.group(2).strip()
            name = title if parent is root else parent.name + _JOIN + title
            here = _Section(name, level, at, at + len(line))
            parent.children.append(here)
            stack.append(here)
        at += len(line)
    while len(stack) > 1:
        stack.pop().end = len(text)
    root.end = len(text)
    return root


def _walk(section: _Section):
    for child in section.children:
        yield child
        yield from _walk(child)


class Guide:
    """The documents under ``prompts`` and ``schemas``, by file name."""

    def __init__(self, prompts: dict[str, Path], schemas: dict[str, Path],
                 budget: int = bounded_view.DEFAULT_BUDGET) -> None:
        self._prompts = {k: v for k, v in prompts.items() if v.is_file()}
        self._schemas = {k: v for k, v in schemas.items() if v.is_file()}
        self._budget = budget

    # ------------------------------------------------------------ listing

    def documents(self) -> dict:
        docs = []
        for name, path in self._prompts.items():
            text = path.read_text(encoding="utf-8")
            first = next((line.lstrip("# ").strip() for line in text.splitlines()
                          if line.startswith("# ")), name)
            docs.append({"doc": name, "chars": len(text), "title": first})
        for name, path in self._schemas.items():
            schema = json.loads(path.read_text(encoding="utf-8"))
            docs.append({"doc": name, "chars": bounded_view.size(schema),
                         "title": schema.get("title", name)})
        return {"documents": docs}

    def contents(self, doc: str) -> dict:
        if doc in self._prompts:
            text = self._text(doc)
            root = _outline(text)
            return {"doc": doc, "chars": len(text), "sections": [
                {"section": s.name, "chars": s.end - s.start}
                for s in _walk(root)]}
        schema = self._schema(doc)
        sections = [{"section": "(root)",
                     "chars": bounded_view.size(_without_defs(schema))}]
        sections += [{"section": name, "chars": bounded_view.size(value)}
                     for name, value in (schema.get("$defs") or {}).items()]
        return {"doc": doc, "chars": bounded_view.size(schema),
                "sections": sections}

    # ------------------------------------------------------------ reading

    def section(self, doc: str, name: str, start: int = 0) -> dict:
        if doc in self._prompts:
            return self._markdown_section(doc, name, start)
        schema = self._schema(doc)
        if name.startswith("/"):
            return {"doc": doc, **bounded_view.part(schema, name, start,
                                                    self._budget)}
        if name == "(root)":
            return {"doc": doc, "section": name,
                    "value": bounded_view.view(_without_defs(schema),
                                               self._budget)}
        if name not in (schema.get("$defs") or {}):
            raise KeyError(f"{doc} has no definition {name!r}; "
                           f"themis_guide(doc={doc!r}) lists them")
        where = "/$defs/" + name.replace("~", "~0").replace("/", "~1")
        return {"doc": doc, "section": name,
                **bounded_view.part(schema, where, start, self._budget)}

    def _markdown_section(self, doc: str, name: str, start: int) -> dict:
        text = self._text(doc)
        root = _outline(text)
        if name == "":
            found = root
        else:
            named = [s for s in _walk(root) if s.name == name]
            if not named:
                # A bare title is accepted when it names one section only.
                named = [s for s in _walk(root)
                         if s.name.rsplit(_JOIN, 1)[-1] == name]
            if len(named) != 1:
                raise KeyError(
                    f"{doc} has {'no' if not named else len(named)} section "
                    f"called {name!r}; themis_guide(doc={doc!r}) lists them "
                    f"by the name to pass")
            found = named[0]
        said: dict = {"doc": doc, "section": found.name}
        room = self._budget - bounded_view.size(said) - 120
        whole = text[found.start:found.end]
        if start == 0 and bounded_view.size(whole) <= room and found is not root:
            said["text"] = whole
            return said
        # Too large whole: its own text up to its first subsection, and the
        # subsections by name. A leaf that is still too large, in slices.
        own_end = found.children[0].start if found.children else found.end
        own = text[found.start:own_end]
        subsections = [s.name for s in found.children]
        room -= bounded_view.size(subsections)
        piece = own[start:]
        cut = _longest_prefix(piece, room)
        said["text"] = piece[:cut]
        if start + cut < len(own):
            said["next"] = start + cut
        if subsections:
            said["subsections"] = subsections
        return said

    # ------------------------------------------------------------ files

    def _text(self, doc: str) -> str:
        return self._prompts[doc].read_text(encoding="utf-8")

    def _schema(self, doc: str) -> dict:
        if doc not in self._schemas:
            raise KeyError(f"no document {doc!r}; themis_guide() lists them")
        return json.loads(self._schemas[doc].read_text(encoding="utf-8"))


def _without_defs(schema: dict) -> dict:
    return {k: v for k, v in schema.items() if k != "$defs"}


def _longest_prefix(text: str, room: int) -> int:
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if bounded_view.size(text[:mid]) <= room:
            lo = mid
        else:
            hi = mid - 1
    return lo
