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
    """The body of one top-level ``const NAME ... = { ... }``.

    The annotation between the name and the ``=`` may contain an ``=`` of its
    own: a renderer table is typed ``Record<string, (b) => Section>``, and a
    matcher that stopped at the first equals sign reported that the source
    declared no such table — which reads exactly like a table nobody wrote.
    Only ``=`` immediately followed by an opening brace opens a body, so
    scanning past the arrows costs nothing.
    """
    opened = re.search(rf"^(?:export )?const {name}\b[^\n]*?=\s*[{{\[]",
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


def entry(body: str, key: str) -> str:
    """The balanced body of ``key: { ... }`` INSIDE an object literal.

    The same matcher as :func:`literal`, one level down. Two levels are what
    a table holds now — a member, and that member's text per language — and
    a reader that could only reach the outer one would have to find the
    inner by counting braces at its own use point, which is how the three
    regexes this module replaced came about.

    A key is a key wherever it sits: the entry may share a line with what
    precedes it, so this is anchored on the key not being part of a longer
    word rather than on the start of a line.
    """
    opened = re.search(rf"(?<![\w'\"]){key}:\s*\{{", body)
    assert opened, f"no {key} in this literal"
    start = opened.end() - 1
    depth, i = 0, start
    while True:
        if body[i] in "{[":
            depth += 1
        elif body[i] in "}]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return body[start + 1:i]


def members(name: str, source: str) -> dict[str, str]:
    """A top-level table, as member -> that member's whole entry.

    What a caller does with the entry is its own question: whether some
    language is present in it, whether two members say the same thing.
    """
    body = literal(name, source)
    return {key: entry(body, key) for key in top_level_keys(body)}


def unquoted(literal_text: str) -> str:
    """What a single-quoted TypeScript string SAYS, not how it is spelled.

    An English sentence brings apostrophes with it — "the instrument's
    conditioning set" — and inside a single-quoted string those are written
    ``\\'``. A reader that handed the escape back would report a copy held
    equal to the kernel's as different from it, in the one direction that
    looks like drift and is not.
    """
    return re.sub(r"\\(.)", r"\1", literal_text)


def words_map(name: str, source: str) -> dict[str, dict[str, str]]:
    """A top-level ``Record<string, Words>``, as member -> language -> text.

    For the tables whose entry is one string per language. A table holding
    something structured per language — a refusal is three sentences — is
    read through :func:`members` and :func:`entry` instead, because what
    "the text" means there is the caller's question.
    """
    return {
        member: {tag: unquoted(text) for tag, text
                 in re.findall(r"(\w+): '((?:[^'\\]|\\.)*)'", said)}
        for member, said in members(name, source).items()
    }


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
