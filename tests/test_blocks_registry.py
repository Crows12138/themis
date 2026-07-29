"""The envelope's block registry, checked against the system that uses it.

A registry is worth exactly what checks it. Two directions can rot, and
they rot differently: a block can be written without ever being declared
(which is how eleven of them got past the result schema, whose extensions
map is open by design), and a block can be declared long after nothing
writes it any more. The kernel's two single exits close the first
direction on every run. The second is closed here.
"""
import ast
import pathlib

import pytest

import themis
from themis import blocks

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "themis"
REGISTRY = PACKAGE / "blocks.py"

# Where the registry deliberately does not reach. The verifier re-derives
# the envelope independently — sharing a symbol with whoever wrote the
# block would make it audit its own spelling — and the program carries its
# own extensions side-channel, which shares the word ``ambiguities`` and
# nothing else.
_NOT_THROUGH_THE_REGISTRY = ("themis/verifier/",)


def _sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        if path == REGISTRY or rel.startswith(_NOT_THROUGH_THE_REGISTRY):
            continue
        yield rel, path.read_text(encoding="utf-8")


def _registry_attributes() -> set[str]:
    """Every ``blocks.<NAME>`` mentioned anywhere outside the registry."""
    used: set[str] = set()
    for _rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "blocks"
            ):
                used.add(node.attr)
    return used


def test_the_registry_declares_what_it_says_it_declares():
    """``ALL`` is collected from the module, not listed again below it."""
    declared = {
        name for name, value in vars(blocks).items()
        if isinstance(value, blocks.Block)
    }
    assert {str(b) for b in blocks.ALL} == {
        str(getattr(blocks, name)) for name in declared
    }
    assert len(blocks.ALL) == len(declared), "two names for one block"


@pytest.mark.parametrize("block", sorted(blocks.ALL))
def test_every_registered_block_is_referred_to_by_something(block):
    """A registration nothing refers to is a block that has been deleted
    everywhere except here — the registry describing a system that no
    longer exists, which is worse than no registry."""
    constant = {
        name for name, value in vars(blocks).items()
        if isinstance(value, blocks.Block) and value == block
    }
    assert _registry_attributes() & constant, (
        f"{block!r} is registered but no module names blocks.{constant}"
    )


def test_a_block_is_the_plain_name_once_it_is_data():
    """The registry hands out ``str`` subclasses so a misspelling is an
    AttributeError at import. What lands in the envelope has to be the
    string it always was — a copy or a pickle that came back carrying
    registry metadata would make the envelope depend on this module."""
    import copy
    import json
    import pickle

    envelope = {blocks.CAUSATION: {"pn": 0.5}}
    assert json.loads(json.dumps(envelope)) == {"causation": {"pn": 0.5}}
    assert type(next(iter(copy.deepcopy(envelope)))) is str
    assert type(pickle.loads(pickle.dumps(blocks.CAUSATION))) is str


def test_an_unregistered_block_is_refused_at_the_exit():
    result = {"query_id": "q1", "extensions": {"iv_identification": {}}}
    blocks.check_registered(result)

    result["extensions"]["a_block_nobody_declared"] = {}
    with pytest.raises(ValueError, match="unregistered extension block"):
        blocks.check_registered(result)


def test_a_result_with_no_extensions_is_not_a_violation():
    blocks.check_registered({"query_id": "q1"})
    blocks.check_registered({"query_id": "q1", "extensions": None})


def test_the_schema_gives_shapes_only_to_registered_blocks():
    """The result schema carries a full sub-schema for some blocks. It
    predates this registry and is where the drift was first measurable,
    so it must not name a block the registry does not."""
    import json

    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    shaped = set(schema["properties"]["extensions"].get("properties") or {})
    assert shaped <= set(blocks.BY_NAME), sorted(shaped - set(blocks.BY_NAME))


def test_a_run_emits_only_registered_blocks():
    """The exit check, reached the way a caller reaches it."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause",
             "from": {"predicate": "x", "args": [{"type": "const", "name": "u"}]},
             "to": {"predicate": "y", "args": [{"type": "const", "name": "u"}]}},
            {"kind": "cause",
             "from": {"predicate": "z", "args": [{"type": "const", "name": "u"}]},
             "to": {"predicate": "x", "args": [{"type": "const", "name": "u"}]}},
            {"kind": "cause",
             "from": {"predicate": "z", "args": [{"type": "const", "name": "u"}]},
             "to": {"predicate": "y", "args": [{"type": "const", "name": "u"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "u"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "u"}]},
                     "value": True},
                 "given": []}},
        ],
    }
    out = themis.run(program)
    for result in out["results"]:
        for key in (result.get("extensions") or {}):
            assert key in blocks.BY_NAME
