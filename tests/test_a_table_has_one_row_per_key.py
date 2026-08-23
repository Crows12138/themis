"""A table has one row per key, and neither notation can say otherwise.

Both notations this repository writes tables in — a Python mapping literal
and a JSON object — accept the same key twice and keep the last one. The
duplicate is an error at no layer: the parser allows it, the object that
comes out has already lost it, and every gate that reads the object sees a
table that is complete and self-consistent. A second row is therefore
invisible to everything except the source text.

That is what it did here. :data:`themis.refusals.SAYS` is maintained in
sections by family, and which section a species belongs to is a thing a
person remembers rather than a thing the file states. A cut that opened a
new section wrote ``no_first_stage`` into it, where the table already had a
row for that species three hundred lines up. The new row won silently, the
shadowed one carried the slot names an earlier arrangement of the raise
sites had used, and both gates over ``SAYS`` stayed green throughout —
because both ask whether a species HAS a sentence, and having two is having
one. The same shadow in the other direction is the one that costs a day:
the maintainer edits the row they found, the reader keeps getting the row
that won, and the edit has no effect anywhere.

So the rule is stated on the source, which is the only place the fact still
exists. It is not a rule about ``SAYS``: every table in these two trees is
maintained the same way and fails the same way, and a gate whose
denominator is the table that broke is a gate waiting for the next one.

Mappings and not set displays, and the difference is what the shadow costs.
A row in a mapping carries a value, and the value of the row that wins is
the one a reader gets while the row somebody edits sits there doing
nothing. A set element carries nothing, so an element written twice loses
nothing — and where this repository does write one, it is saying something:
``{0, 1, True, False, 0.0, 1.0}`` is the same two levels six ways, and the
six are there so a reader can see which spellings of a binary column are
accepted. A rule that called those shadowed rows would be a rule about a
different subject, and would be argued with until someone switched it off.

SCOPE is the package that faces a reader and the suite that holds it to
what it says. ``docs/`` and ``CORE_STATUS.md`` are outside, and not because
they matter less: they are records — a run captured verbatim, a decision
already logged — and a record is quoted rather than maintained.
"""
from __future__ import annotations

import ast
import collections
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The package that speaks to a reader, and the suite that pins it.
SURFACES = (REPO / "themis", REPO / "tests")

#: Trees the repository does not write. Named rather than filtered by
#: extension, because what disqualifies them is authorship, not language.
NOT_OURS = frozenset({"node_modules", "dist", "__pycache__", ".venv"})

#: Files with a ``.json`` suffix that are not JSON. TypeScript reads its
#: configuration in a dialect that admits comments, so ``json.loads``
#: refuses them and no part of this repository parses them as JSON. Named
#: one by one rather than pattern-matched: a new unparseable document is a
#: thing somebody has to classify, and failing here is how they find out.
NOT_JSON = frozenset({
    pathlib.Path("themis/web/frontend/tsconfig.app.json"),
    pathlib.Path("themis/web/frontend/tsconfig.node.json"),
})


def _key(node: ast.expr):
    """The value a key spells out, or ``None`` where it spells out none.

    Constants and tuples of constants, because those are the two shapes a
    row's name is written in. A key computed at run time is not a row
    somebody is maintaining, and two of them being equal is a fact about
    the values rather than about the table.

    ``None`` is also a legal constant key, so absence is reported by the
    caller's sentinel rather than by this returning ``None`` — hence the
    two-value return.
    """
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Tuple):
        parts = [_key(el) for el in node.elts]
        if all(found for found, _ in parts):
            return True, tuple(value for _, value in parts)
    return False, None


def _keys(node: ast.Dict) -> list:
    """The keys one mapping literal spells out, in source order."""
    out = []
    for element in node.keys:
        if element is None:              # ``{**other}`` has no key of its own
            continue
        was_literal, value = _key(element)
        if was_literal:
            out.append(value)
    return out


def _shadowed_in_python(text: str) -> list[tuple[int, object, int]]:
    """Every mapping literal in one module that names a key twice.

    Python's ``==`` is the right comparison and not an approximation of it:
    ``{1: ..., True: ...}`` really is one row, because that is what the
    dictionary will do with it.
    """
    return [
        (node.lineno, key, count)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Dict)
        for key, count in collections.Counter(_keys(node)).items()
        if count > 1
    ]


def _shadowed_in_json(text: str) -> list[tuple[object, int]]:
    """Every object in one document that names a member twice.

    ``object_pairs_hook`` is the only way to see it: the default decoder
    builds a dict, which is the step that loses the duplicate.
    """
    found: list[tuple[object, int]] = []

    def watch(pairs):
        found.extend((key, count) for key, count
                     in collections.Counter(k for k, _ in pairs).items()
                     if count > 1)
        return dict(pairs)

    json.loads(text, object_pairs_hook=watch)
    return found


def _sources(suffix: str) -> list[tuple[pathlib.Path, str]]:
    out = []
    for root in SURFACES:
        for path in sorted(root.rglob(f"*{suffix}")):
            if not path.is_file() or NOT_OURS & set(path.parts):
                continue
            out.append((path, path.read_text(encoding="utf-8")))
    return out


def _at(path: pathlib.Path) -> str:
    return path.relative_to(REPO).as_posix()


def test_no_python_table_names_a_key_twice():
    """The message names the line and the key, because the fix is to read
    the two rows and decide which one the table meant."""
    found = []
    for path, text in _sources(".py"):
        for line, key, count in _shadowed_in_python(text):
            found.append(f"{_at(path)}:{line}  {key!r} appears {count} times")
    assert not found, (
        f"{len(found)} literal(s) with a shadowed key:\n  " + "\n  ".join(found)
    )


def test_no_json_document_names_a_member_twice():
    found = []
    for path, text in _sources(".json"):
        if path.relative_to(REPO) in NOT_JSON:
            continue
        for key, count in _shadowed_in_json(text):
            found.append(f"{_at(path)}  {key!r} appears {count} times")
    assert not found, (
        f"{len(found)} object(s) with a shadowed member:\n  " + "\n  ".join(found)
    )


def test_every_json_document_in_scope_is_json():
    """The exception list is a list and not a filter.

    A ``.json`` that does not parse is skipped by the check above, so the
    set of skipped documents has to be one somebody wrote down. This fails
    when a new dialect arrives, which is the moment to classify it.
    """
    unparseable = set()
    for path, text in _sources(".json"):
        try:
            json.loads(text)
        except json.JSONDecodeError:
            unparseable.add(path.relative_to(REPO))
    assert unparseable == NOT_JSON, (
        f"unparseable: {sorted(map(str, unparseable))}, "
        f"declared: {sorted(map(str, NOT_JSON))}"
    )


def test_the_sweep_reads_the_repository():
    """A walk that stops finding tables passes both checks in silence.

    The floors are far under what the repository carries and neither is a
    target: what they say is that a scan reading nothing fails here rather
    than reporting a clean sweep.
    """
    modules = _sources(".py")
    assert len(modules) > 300, f"the walk found {len(modules)} modules"
    rows = sum(
        len(_keys(node))
        for _, text in modules
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Dict)
    )
    assert rows > 3_000, f"the walk found {rows} literal keys"
    assert len(_sources(".json")) > 20


def test_a_shadowed_key_is_caught():
    """The rule's teeth, in both notations and at both depths.

    The last mapping is the one a reader would not predict and the
    dictionary would: ``True`` and ``1`` are one row.
    """
    assert _shadowed_in_python('T = {"a": 1, "b": 2, "a": 3}')
    assert _shadowed_in_python('T = {("x", 0): 1, ("x", 0): 2}')
    assert _shadowed_in_python("T = {1: 'one', True: 'also one'}")
    assert _shadowed_in_json('{"a": 1, "a": 2}')
    assert _shadowed_in_json('{"outer": {"a": 1, "a": 2}}')


def test_a_key_the_rule_does_not_claim():
    """Where a repeated literal is not a shadowed row.

    Two rows named by the same expression are not two rows named by the
    same key — what those expressions hold at run time is the values'
    business, and nobody is maintaining a table by writing them. And a set
    display has no rows at all: the six spellings below are this
    repository's way of saying which encodings of a binary column it takes.
    """
    assert not _shadowed_in_python("T = {name: 1, other: 2}")
    assert not _shadowed_in_python("T = {**base, **extra}")
    assert not _shadowed_in_python('T = {"a": 1, "b": 2}')
    assert not _shadowed_in_python("ALLOWED = {0, 1, True, False, 0.0, 1.0}")
