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
import re

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
    """Every ``blocks.Block.<NAME>`` mentioned anywhere outside the
    registry."""
    used: set[str] = set()
    for _rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            inner = node.value if isinstance(node, ast.Attribute) else None
            if (
                isinstance(inner, ast.Attribute)
                and inner.attr == "Block"
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "blocks"
            ):
                used.add(node.attr)
    return used


# "``ALL`` is collected from the module, not listed again below it" was a
# test here, and "two names for one block" beside it. The class is the
# registry now, so the first is not a statement that can be false, and
# ``@unique`` refuses the second at import. Neither is checked here any
# more because neither is reachable from here.


@pytest.mark.parametrize("block", sorted(blocks.Block))
def test_every_registered_block_is_referred_to_by_something(block):
    """A registration nothing refers to is a block that has been deleted
    everywhere except here — the registry describing a system that no
    longer exists, which is worse than no registry."""
    assert block.name in _registry_attributes(), (
        f"{block!r} is registered but no module names blocks.Block.{block.name}"
    )


def test_every_block_says_which_of_the_readers_questions_it_answers():
    """The registry grouped itself by producer from the day it was written.
    Grouped that way, a block nobody renders looks exactly like a block
    somebody does — which is how ten route blocks reached no reader at all
    while every other kind had both a table and a section.

    ``isinstance`` and not ``in``: a family is a ``str``, so the bare name
    of one would pass a membership test while carrying no ``tells``."""
    for block in blocks.Block:
        assert isinstance(block.read_as, blocks.Family), (
            f"{block!r} is read as {block.read_as!r}, which is not a family"
        )


def test_the_families_partition_the_registry():
    covered = [b for f in blocks.Family for b in blocks.declared_as(f)]
    assert sorted(covered) == sorted(blocks.Block)
    assert len(covered) == len(set(covered)), "a block in two families"


def test_declared_order_is_the_order_a_section_says_them_in():
    """A family's running order lives in the registry, because the second
    list is the one that goes stale. Pinned rather than described: the
    recognised pattern leads, the recoverability verdicts — which qualify
    whatever came before them — come last."""
    assert [str(b) for b in blocks.declared_as(blocks.Family.ROUTE)] == [
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
    members = blocks.declared_as(blocks.Family.ROUTE)
    with pytest.raises(ValueError, match="no renderer for route block"):
        blocks.bind(blocks.Family.ROUTE, {b: str for b in members[1:]})


def test_a_surface_cannot_bind_a_block_from_another_family():
    """Its output would land in the wrong section, which reads as coverage
    and is not."""
    bound = {b: str for b in blocks.declared_as(blocks.Family.ROUTE)}
    bound[blocks.Block.ASSUMPTION_LEDGER] = str
    with pytest.raises(ValueError, match="which route does not contain"):
        blocks.bind(blocks.Family.ROUTE, bound)


def test_a_block_cannot_be_declared_without_saying_how_it_is_read():
    """A member is a tuple the constructor unpacks, so a declaration short
    of a field never becomes a member: the class body itself raises. Asked
    of the constructor rather than by writing a bad member, because a
    class body that raises cannot be written inside a test that also
    imports the good one."""
    with pytest.raises(TypeError):
        blocks.Block.__new__(blocks.Block, "invented", "nothing", None)


def test_a_block_cannot_be_declared_without_saying_how_it_reaches_a_reader():
    with pytest.raises(TypeError):
        blocks.Block.__new__(
            blocks.Block, "invented", "nothing", blocks.Family.GAP)


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
        str(b) for b in blocks.Block
        if b.carried_by is None and str(b) not in rendered_by_the_report
    )
    assert not unbound, (
        f"{unbound} say a surface renders them and the report does not; "
        f"either bind a renderer there or say what carries them"
    )


WEB = PACKAGE / "web" / "frontend" / "src"
WEB_ANSWER_SURFACE = WEB / "lib" / "verdict.ts"
WEB_COMPONENT = WEB / "components" / "Verdict.tsx"


def _web_rendered_blocks() -> dict[str, list[str]]:
    """``RENDERED_BLOCKS`` as the browser declares it, parsed by name.

    The arrays are spelled as ``as const`` tuples and referenced from the
    map, so both forms are resolved here rather than requiring the web to
    inline them — the order those arrays state is itself checked, and
    naming them twice would be the second telling this registry exists to
    prevent.
    """
    source = WEB_ANSWER_SURFACE.read_text(encoding="utf-8")
    arrays = {
        name: re.findall(r"'([a-z_]+)'", body)
        for name, body in re.findall(
            r"const ([A-Z_]+_ORDER) = \[(.*?)\] as const", source, re.S
        )
    }
    listed = re.search(
        r"RENDERED_BLOCKS: Record<string, readonly string\[\]> = \{(.*?)\n\}",
        source, re.S,
    )
    assert listed, f"{WEB_ANSWER_SURFACE.name} declares no RENDERED_BLOCKS"

    out: dict[str, list[str]] = {}
    for family, value in re.findall(r"^  (\w+): (.+),$", listed.group(1), re.M):
        value = value.strip()
        out[family] = (
            arrays[value] if value in arrays
            else re.findall(r"'([a-z_]+)'", value)
        )
    return out


@pytest.mark.parametrize("family", blocks.Family, ids=str)
def test_the_web_renders_every_family_the_registry_makes_a_surface_render(family):
    """The same question ``bind`` asks the report, asked of the browser.

    ``bind`` cannot reach across a language boundary: ``BOUND`` is keyed by
    the importing Python module, so no ``.ts`` file can ever appear in it,
    and ``carried_by is None`` was therefore checked against exactly one
    surface. The web had a parsed-and-pinned list for ROUTE and nothing for
    the other three families — the same one-of-four the ``read_as`` axis
    had before ``carried_by`` existed — and the consequence was the same
    one, on the other surface: the two blocks holding the whole answer on
    the theta path reached the browser as a single unnamed number, and as
    nothing at all when it was an interval.

    Order is part of it. The foldout and the report section are the same
    section on two surfaces, and a reader who compares them should not have
    to reconcile two orders.
    """
    declared = _web_rendered_blocks()
    assert family in declared, (
        f"{WEB_ANSWER_SURFACE.name} states nothing for the {family} "
        f"family; a family it does not mention is one it can drop silently"
    )
    assert declared[family] == [str(b) for b in blocks.rendered_in(family)]


@pytest.mark.parametrize(
    "name",
    [str(b) for f in blocks.Family for b in blocks.rendered_in(f)],
)
def test_every_block_the_web_must_render_is_read_by_something_there(name):
    """A list is a promise; this asks whether anything keeps it.

    Two mechanisms are accepted, because ``carried_by`` is itself
    two-valued: a name-indexed renderer in the answer surface, or a
    definitional read in the component. The ledger's rows carry severity
    and are JSX, and flattening them into label/value pairs to satisfy one
    uniform shape would make the surface worse to make the check tidier.

    What is NOT accepted is the block's name merely occurring: two of these
    names are also ``query_kind`` labels in the same file, so a probe that
    counted occurrences scored 18 of 18 present while two of them reached
    no reader at all.
    """
    surface = WEB_ANSWER_SURFACE.read_text(encoding="utf-8")
    component = WEB_COMPONENT.read_text(encoding="utf-8")
    assert (
        re.search(rf"^  {name}: \(", surface, re.M)
        or re.search(rf"extensions\??\.{name}\b", component)
    ), (
        f"{name} is listed as rendered by the web and nothing there reads "
        f"it; a renderer in {WEB_ANSWER_SURFACE.name} or a read of "
        f"extensions.{name} in {WEB_COMPONENT.name}"
    )


def test_a_block_naming_a_carrier_names_something_that_exists():
    """The other half. A carrier is a member of a table, not a sentence.

    Either another block — which must reach a reader by its own route, so
    the chain ends — or a top-level field of the result, which the report
    already renders. Both are checked against the thing itself rather than
    against a list kept here.

    The registry refuses at import a carrier that is neither, which is
    what makes a name safe to write as a name. It cannot check the field
    half from inside — the schema is not its to read — so it declares
    ``CARRIER_FIELDS`` and that declaration is held here.
    """
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json")
        .read_text(encoding="utf-8")
    )
    fields = set(schema["properties"])
    invented = sorted(blocks.CARRIER_FIELDS - fields)
    assert not invented, (
        f"themis.blocks.CARRIER_FIELDS names {invented}, which the result "
        f"schema does not declare; a carrier may not be a field that only "
        f"the registry believes in"
    )

    for block in blocks.Block:
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
        blocks.Family.ASSUMPTION,
        {b: str for b in blocks.rendered_in(blocks.Family.ASSUMPTION)},
    )
    assert "assumption_ledger" in blocks.BOUND[__name__]
    assert "themis.output.analysis_report" != __name__


def test_a_surface_cannot_bind_a_block_something_else_carries():
    """Binding one is a second telling — and the first one is the one the
    reader gets, since the carrier is read before the report runs."""
    bound = {b: str for b in blocks.rendered_in(blocks.Family.ASSUMPTION)}
    bound[blocks.Block.MECHANISM_AUDIT] = str
    with pytest.raises(ValueError, match="something else carries it"):
        blocks.bind(blocks.Family.ASSUMPTION, bound)


def test_a_block_is_the_plain_name_once_it_is_data():
    """The registry hands out ``str`` subclasses so a misspelling is an
    AttributeError at import. What lands in the envelope has to be the
    string it always was — a copy or a pickle that came back carrying
    registry metadata would make the envelope depend on this module."""
    import copy
    import json
    import pickle

    envelope = {blocks.Block.CAUSATION: {"pn": 0.5}}
    assert json.loads(json.dumps(envelope)) == {"causation": {"pn": 0.5}}
    assert type(next(iter(copy.deepcopy(envelope)))) is str
    assert type(pickle.loads(pickle.dumps(blocks.Block.CAUSATION))) is str


def test_an_unregistered_block_is_refused_at_the_exit():
    result = {"query_id": "q1", "extensions": {"iv_identification": {}}}
    blocks.check_registered(result)

    result["extensions"]["a_block_nobody_declared"] = {}
    with pytest.raises(ValueError, match="unregistered extension block"):
        blocks.check_registered(result)


def test_a_result_with_no_extensions_is_not_a_violation():
    blocks.check_registered({"query_id": "q1"})
    blocks.check_registered({"query_id": "q1", "extensions": None})


def _shaped_blocks() -> set[str]:
    import json

    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    return set(schema["properties"]["extensions"].get("properties") or {})


def test_the_schema_gives_shapes_only_to_registered_blocks():
    """The result schema carries a full sub-schema for some blocks. It
    predates this registry and is where the drift was first measurable,
    so it must not name a block the registry does not."""
    assert _shaped_blocks() <= set(blocks.Block), sorted(
        _shaped_blocks() - set(blocks.Block))


def test_every_registered_block_has_a_shape_in_the_schema():
    """And the other way, which is the direction that had never been asked.

    A block with no sub-schema is not a block with a loose shape — it is a
    block whose fields have no declared domain anywhere, and the closed
    vocabularies it carries out of the kernel are then spelled by hand at
    each reader. That is measurable rather than theoretical: with this
    direction unasked, eight of eighteen blocks sat outside the schema
    while emitting eight hundred instances over one suite run, two of them
    carrying a field whose sibling block enumerates the SAME field name
    with a set of members that no longer agreed.

    The map itself stays open — a foreign annotation is welcome — but what
    this kernel emits is closed by the registry at the exits, so nothing
    is bought by leaving our own blocks undeclared here.
    """
    unshaped = sorted(set(blocks.Block) - _shaped_blocks())
    assert not unshaped, (
        f"registered but shapeless in query_result.schema.json: {unshaped}; "
        f"declare the block's fields, and give an enum to every field whose "
        f"domain is a fixed set of meanings a reader has to tell apart"
    )


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
            assert key in blocks.Block
