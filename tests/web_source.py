"""Reading the browser's source from the kernel's test suite.

The browser cannot import Python, so everything the kernel holds it to is
checked by parsing its TypeScript. Three test modules once grew a regex
each for one object literal apiece, which is the convention that gets
rewritten at every use point and missed at one of them; they were folded
into a single brace matcher when the fourth table arrived. This module is
where that matcher lives, because the fifth reader is a different test
file and would otherwise have written a fifth.

Nothing here knows what any particular table means. The questions — is
this a vocabulary, does the envelope declare this field — belong to the
modules that ask them.
"""
from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "themis" / "web" / \
    "frontend" / "src"
VERDICT = SRC / "lib" / "verdict.ts"
TYPES = SRC / "types.ts"
COMPONENT = SRC / "components" / "Verdict.tsx"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def literal(name: str, source: str) -> str:
    """The body of one top-level ``const NAME ... = { ... }``."""
    opened = re.search(rf"^(?:export )?const {name}\b[^=]*=\s*[{{\[]",
                       source, re.M)
    assert opened, f"the source declares no {name}"
    start = opened.end() - 1
    close = {"{": "}", "[": "]"}[source[start]]
    depth, i = 0, start
    while True:
        if source[i] in "{[":
            depth += 1
        elif source[i] in "}]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return source[start + 1:i]


def interface_body(name: str, source: str) -> str:
    """The body of one ``export interface NAME { ... }``.

    Same matcher as ``literal`` and deliberately not shared with it: an
    interface opens on ``{`` only, and merging the two would mean a
    parameter whose only job is to say which of two spellings to expect.
    """
    opened = re.search(rf"^(?:export )?interface {name}\b[^{{]*\{{",
                       source, re.M)
    assert opened, f"the source declares no interface {name}"
    start = opened.end() - 1
    depth, i = 0, start
    while True:
        if source[i] in "{[":
            depth += 1
        elif source[i] in "}]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return source[start + 1:i]


def top_level_keys(body: str) -> set[str]:
    """The keys of a literal or the fields of an interface, depth 0 only.

    Quoted as well as bare, because a key that is a path — the detail table is
    keyed by ``extensions.iv_identification.numeric`` — cannot be written bare
    in TypeScript. A matcher that only saw bare keys would report such a table
    as empty, which reads exactly like a table nobody filled in.
    """
    keys, depth = set(), 0
    for line in body.splitlines():
        if depth == 0:
            found = re.match(r"\s*'([^']+)'\s*:", line) or re.match(
                r"\s*([A-Za-z_]\w*)\??\s*:", line)
            if found:
                keys.add(found.group(1))
        depth += (line.count("{") + line.count("[")
                  - line.count("}") - line.count("]"))
    return keys


def string_list(name: str, source: str) -> set[str]:
    """Every quoted string in a top-level array literal.

    Whole-line comments are dropped first. An apostrophe in English prose —
    "the schema's own names" — otherwise opens a quote that closes on the
    next entry, so the list silently loses members and gains a fragment of
    itself. A line that begins with ``//`` is never content, and a string
    containing ``//`` begins with a quote, so the two cannot be confused.
    """
    body = "\n".join(
        line for line in literal(name, source).splitlines()
        if not line.lstrip().startswith("//")
    )
    return set(re.findall(r"'([^']+)'", body))


def string_map(name: str, source: str) -> dict[str, str]:
    """A top-level ``Record<string, string>``, as Python."""
    return dict(re.findall(r"^\s*(\w+): '([^']*)',", literal(name, source),
                           re.M))


_DECL = re.compile(
    r"^(?:export )?(?:async )?(?:function|const|type|interface|class) (\w+)",
    re.M)


def chunks(text: str) -> dict[str, str]:
    """Top-level declared name -> its text, up to the next declaration.

    Everything in these files is declared at column 0, so no brace matching
    is needed — and brace matching would be wrong here: on
    ``function f(x): T { ... }`` it closes at the parameter list, which
    made the first version of this scan report that nothing reads anything.
    """
    marks = [(m.start(), m.group(1)) for m in _DECL.finditer(text)]
    out = {}
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[name] = text[pos:end]
    return out


def sources_that_could_read(exclude: pathlib.Path | None = None) -> str:
    """Every ``.ts``/``.tsx`` under ``src``, import lines stripped.

    An import is not a use: a component that stops rendering something
    keeps importing it, and a haystack that counts the import line calls
    that component a reader.
    """
    out = []
    for path in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx")):
        if exclude is not None and path == exclude:
            continue
        out.extend(
            line for line in read(path).splitlines()
            if not line.lstrip().startswith("import ")
        )
    return "\n".join(out)
