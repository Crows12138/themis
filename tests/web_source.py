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
#: The tables the kernel writes for the browser. Checked in beside the
#: hand-written source and read the same way — what makes it different is
#: who edits it, which is a fact about the file rather than about how it
#: parses.
GENERATED = SRC / "lib" / "kernelWords.generated.ts"
TYPES = SRC / "types.ts"
COMPONENT = SRC / "components" / "Verdict.tsx"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def vocabularies() -> str:
    """Every table the browser answers a reader out of, as one text.

    Two files hold them: the one somebody writes and the one the kernel
    writes for it. Which of the two a table sits in is a real question and
    the module that asks it reads the files apart; everything else asks
    about a TABLE, and a caller that had to know where each one lives would
    be a caller that goes stale when one moves.
    """
    return read(VERDICT) + "\n" + read(GENERATED)


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
    return balanced(source, opened.end() - 1)


def balanced(text: str, start: int) -> str:
    """What sits between the bracket at ``start`` and the one that closes it.

    Written once and used four times. It counts brackets and does not read
    strings, which is right for the three callers that open on a declared
    name: a brace inside a quoted string would have to be inside a table
    this repository does not write. :func:`words_literals` needs more than
    that and says so where it needs it.
    """
    depth, i = 0, start
    while True:
        if text[i] in "{[":
            depth += 1
        elif text[i] in "}]":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1


def interface_body(name: str, source: str) -> str:
    """The body of one ``export interface NAME { ... }``.

    Same matcher as ``literal`` and deliberately not shared with it: an
    interface opens on ``{`` only, and merging the two would mean a
    parameter whose only job is to say which of two spellings to expect.
    """
    opened = re.search(rf"^(?:export )?interface {name}\b[^{{]*\{{",
                       source, re.M)
    assert opened, f"the source declares no interface {name}"
    return balanced(source, opened.end() - 1)


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
    return balanced(body, opened.end() - 1)


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


#: An object literal whose first key is a bare word — the shape a ``Words``
#: opens with. Whether it IS one is decided by its keys, which is the same
#: reading the kernel's own scan makes, and the reason nothing here looks
#: for a table name: a ``Words`` written inline in a component is as much
#: one as a ``Words`` in a named table, and the inline ones are exactly
#: what a name-driven scan would never see.
_OPENS_WITH_KEY = re.compile(r"\{\s*(\w+)\s*:")
#: A string in any of the three spellings TypeScript has for one. All three
#: rather than the one this repository writes today, because a scan that
#: reads only the current spelling reports a sentence written in another as
#: no sentence — and the pin on this scan's reach counts the KEY, which a
#: template literal would still have.
_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'"
                     r"|\"((?:[^\"\\]|\\.)*)\""
                     r"|`((?:[^`\\]|\\.)*)`")


def _past_string(text: str, i: int) -> int:
    """The index just after the quoted string that starts at ``i``."""
    quote, i = text[i], i + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return i


def calls(name: str, text: str) -> list[tuple[int, list[str]]]:
    """``(line, [argument source, ...])`` for every call of ``name``.

    For rules about what is passed rather than about what is declared. It
    reads strings for the same reason :func:`_fields` does — an argument
    can be an English sentence, and a comma inside one is not a comma
    between arguments — and it refuses a name reached through a dot,
    because ``obj.say(...)`` is not the ``say`` a rule about this
    package's own door is written about.
    """
    out: list[tuple[int, list[str]]] = []
    for m in re.finditer(rf"(?<![\w.]){re.escape(name)}\(", text):
        depth, i, pieces, last = 0, m.end() - 1, [], m.end()
        while i < len(text):
            char = text[i]
            if char in "'\"`":
                i = _past_string(text, i)
                continue
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
                if depth == 0:
                    pieces.append(text[last:i])
                    out.append((text[:m.start()].count("\n") + 1, pieces))
                    break
            elif char == "," and depth == 1:
                pieces.append(text[last:i])
                last = i + 1
            i += 1
    return out


def _fields(body: str) -> dict[str, str]:
    """``key -> value source`` for one object literal, its own level only.

    This one reads strings as well as counting brackets, which the three
    callers above can do without and it cannot: an English sentence carries
    commas, and a split that did not know it was inside a string would end
    the entry in the middle of the text it came for.
    """
    out: dict[str, str] = {}
    depth, key, start, i = 0, None, 0, 0
    while i < len(body):
        char = body[i]
        if char in "'\"`":
            i = _past_string(body, i)
            continue
        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        elif depth == 0 and char == ":" and key is None:
            key, start = body[start:i].strip().strip("'\""), i + 1
        elif depth == 0 and char == "," and key is not None:
            out[key], key, start = body[start:i], None, i + 1
        i += 1
    if key is not None:
        out[key] = body[start:]
    return out


def words_literals(text: str, tags) -> list[tuple[int, dict[str, str]]]:
    """(line, language -> what it says) for every ``Words`` written in it.

    Both shapes a ``Words`` is written in: one string per language, and one
    structure per language (a tier's label and gloss, a status's label and
    blurb). For the second, the language's text is every string inside it
    run together — a caller asking which holes a sentence has gets the same
    answer either way, and which field a hole sits in is a question about
    the structure rather than about the language.

    That there turned out to be two shapes is why the reach of this scan is
    pinned rather than trusted: a third one would otherwise read as nothing.
    """
    tags, found = set(tags), []
    for match in _OPENS_WITH_KEY.finditer(text):
        if match.group(1) not in tags:
            continue
        fields = _fields(balanced(text, match.start()))
        if not fields or not set(fields) <= tags:
            continue
        found.append((text.count("\n", 0, match.start()) + 1,
                      {tag: " ".join(unquoted(s) for found_in in
                                     _QUOTED.findall(v) for s in found_in if s)
                       for tag, v in fields.items()}))
    return found


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
