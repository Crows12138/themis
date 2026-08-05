"""The envelope's block registry, checked against the system that uses it.

A registry is worth exactly what checks it. Two directions can rot, and
they rot differently: a block can be written without ever being declared
(which is how eleven of them got past the result schema, whose extensions
map is open by design), and a block can be declared long after nothing
writes it any more. The kernel's two single exits close the first
direction on every run. The second is closed here.
"""
import ast
import json
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


def test_every_block_says_which_of_the_readers_questions_it_answers():
    """The registry grouped itself by producer from the day it was written.
    Grouped that way, a block nobody renders looks exactly like a block
    somebody does — which is how ten route blocks reached no reader at all
    while every other kind had both a table and a section."""
    for block in blocks.DECLARED:
        assert block.read_as in blocks.FAMILIES, (
            f"{block!r} is read as {block.read_as!r}, which is not a family"
        )


def test_the_families_partition_the_registry():
    covered = [b for f in blocks.FAMILIES for b in blocks.declared_as(f)]
    assert sorted(covered) == sorted(blocks.DECLARED)
    assert len(covered) == len(set(covered)), "a block in two families"


def test_declared_order_is_the_order_a_section_says_them_in():
    """A family's running order lives in the registry, because the second
    list is the one that goes stale. Pinned rather than described: the
    recognised pattern leads, the recoverability verdicts — which qualify
    whatever came before them — come last."""
    assert [str(b) for b in blocks.declared_as(blocks.ROUTE)] == [
        "identification",
        "iv_identification",
        "transport_identification",
        "joint_identification",
        "longitudinal_identification",
        "mediation_decomposition",
        "mediation_joint_decomposition",
        "proximal_estimand",
        "selection_recovery",
        "missing_data_recovery",
    ]


def test_a_surface_that_misses_a_block_of_its_family_is_refused_at_import():
    members = blocks.declared_as(blocks.ROUTE)
    with pytest.raises(ValueError, match="no renderer for route block"):
        blocks.bind(blocks.ROUTE, {b: str for b in members[1:]})


def test_a_surface_cannot_bind_a_block_from_another_family():
    """Its output would land in the wrong section, which reads as coverage
    and is not."""
    bound = {b: str for b in blocks.declared_as(blocks.ROUTE)}
    bound[blocks.ASSUMPTION_LEDGER] = str
    with pytest.raises(ValueError, match="which route does not contain"):
        blocks.bind(blocks.ROUTE, bound)


def test_a_block_cannot_be_declared_without_saying_how_it_is_read():
    with pytest.raises(TypeError):
        blocks.Block("invented", holds="nothing", carried_by=None)


def test_a_block_cannot_be_declared_without_saying_how_it_reaches_a_reader():
    with pytest.raises(TypeError):
        blocks.Block("invented", holds="nothing", read_as=blocks.GAP)


def test_a_block_claiming_a_renderer_has_one():
    """``carried_by=None`` is a claim about a surface; this asks the surface.

    The claim used to be a comment over a family heading, and what checked
    it asked whether any module *names* the block — which its writer
    satisfies. All eight blocks outside the one bound family passed it,
    and they were in three different states: the ledger, which the report
    did read; the five something else carries; and the two answered from
    theta, which reached nobody but a detachable scaffold. Naming is what
    all three states have in common, so the check could not tell them
    apart.

    ``bind`` records which surface bound what, and importing the report is
    what makes it bind, so the question can be put directly instead — of
    the report, by name. "Some surface renders it" is the weaker question
    the explainer already answered.
    """
    from themis.output import analysis_report  # noqa: F401  binds on import

    rendered_by_the_report = blocks.BOUND.get(analysis_report.__name__, set())
    unbound = sorted(
        str(b) for b in blocks.DECLARED
        if b.carried_by is None and str(b) not in rendered_by_the_report
    )
    assert not unbound, (
        f"{unbound} say a surface renders them and the report does not; "
        f"either bind a renderer there or say what carries them"
    )


def test_a_block_naming_a_carrier_names_something_that_exists():
    """The other half. A carrier is a member of a table, not a sentence.

    Either another block — which must reach a reader by its own route, so
    the chain ends — or a top-level field of the result, which the report
    already renders. Both are checked against the thing itself rather than
    against a list kept here.
    """
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json")
        .read_text(encoding="utf-8")
    )
    fields = set(schema["properties"])

    for block in blocks.DECLARED:
        # Walk to the end of the chain. It terminates at a field, or at a
        # block that renders itself — and the test above holds that one to
        # actually having a renderer, so a chain that ends is a chain that
        # arrives.
        seen: list[str] = [str(block)]
        target = block.carried_by
        while target is not None:
            name = str(target)
            assert name not in seen, f"carrier cycle: {seen + [name]}"
            seen.append(name)
            if name in fields:
                break
            assert name in blocks.BY_NAME, (
                f"{block!r} says {name!r} carries it, which is neither a "
                f"declared block nor a field of the result"
            )
            target = blocks.BY_NAME[name].carried_by


def test_the_record_says_which_surface_bound_it():
    """The distinction the guard above rests on.

    Binding from here must land under this module and not under the
    report's, or "the report renders it" would be satisfiable by any
    module that binds — which is the check that let a detachable
    scaffold stand in for a reader in the first place.
    """
    blocks.bind(
        blocks.ASSUMPTION,
        {b: str for b in blocks.rendered_in(blocks.ASSUMPTION)},
    )
    assert "assumption_ledger" in blocks.BOUND[__name__]
    assert "themis.output.analysis_report" != __name__


def test_a_surface_cannot_bind_a_block_something_else_carries():
    """Binding one is a second telling — and the first one is the one the
    reader gets, since the carrier is read before the report runs."""
    bound = {b: str for b in blocks.rendered_in(blocks.ASSUMPTION)}
    bound[blocks.MECHANISM_AUDIT] = str
    with pytest.raises(ValueError, match="something else carries it"):
        blocks.bind(blocks.ASSUMPTION, bound)


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
