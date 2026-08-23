"""A shape is recorded once, and a validator can reach every record.

Six shapes were written down twice, in three pairs of documents, and one pair
had already drifted — ``kbQuery`` carried a default and two descriptions in
one copy that the other did not have. The cut that found it had to edit both,
and nothing would have spoken if it had edited one.

The mechanism for not copying was already here: documents reference each other
by ``$id``, the registry globs all thirteen, and a hundred-odd references use
it. What was missing is that the mechanism had one entrance. Production went
through :func:`themis.input.syntactic_validator.validator_for`; everywhere else
assembled a registry by naming a document or two, or built a validator with no
registry at all. So adding a reference was never a local edit — the author had
to know which of twenty-odd validators would reach it — while copying a shape
required knowing nothing. The duplication is what that asymmetry produces.

Both halves are gated here, because either alone rots: a deduplication rule
with no entrance rule sends the next author back to copying, and an entrance
rule with no deduplication rule leaves the copies sitting there.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest
from jsonschema.exceptions import ValidationError

from themis.input.syntactic_validator import _load_registry, validator_for

from . import schema_walk

REPO = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "themis" / "schemas"

#: Keys that say what a shape means rather than what it admits. Two records of
#: one shape are two records however differently they are worded.
PROSE = ("description", "title", "$id", "$schema", "$comment", "examples")

#: The one module allowed to build a validator itself — it is what the others
#: are required to call.
THE_ENTRANCE = pathlib.Path("themis") / "input" / "syntactic_validator.py"

#: Names two documents both record, where neither record is a reference to the
#: other, together with why they are different things. A name landing here is a
#: claim someone made on purpose; a name landing here by accident is the drift
#: this file exists to catch, so the table may not name a pair that is gone.
DIFFERENT_THINGS = {
    "atom": "atom.schema.json's is the kernel-AST atom (predicate + args); "
            "derivation.schema.json's is the verifier's kinded node, which "
            "carries a `kind` discriminator and cannot stand in for it.",
    "valuedatom": "query_result's has no `kind` and its value is optional "
                  "(bound by the enclosing query); the other two are kinded, "
                  "and their values differ again — derivation admits a tagged "
                  "object, a verification context admits only a scalar.",
    "assocquery": "the kernel-AST query as written, versus the query as the "
                  "verifier restates it for checking.",
    "causequery": "as assocquery.",
    "counterfactualquery": "as assocquery.",
    "effectquery": "as assocquery.",
    "identifyquery": "as assocquery.",
    "probabilityquery": "as assocquery.",
    "intervention": "as assocquery.",
    "causestatement": "kernel_ast's is an edge as the author declared it; "
                      "orientation_ledger_export's is an edge the ledger "
                      "settled on, which carries how it was settled.",
    "term": "atom.schema.json's is a union of a const and a var term; "
            "derivation.schema.json's is one object with a `type` enum. The "
            "same idea in two encodings, one per language, and neither "
            "validates what the other admits.",
    "query": "both are unions, over different members: kernel_ast's admits "
             "the ten query forms a program may ask, verification_context's "
             "the six the verifier restates. Merging them would let a "
             "context claim a query the verifier cannot check.",
}


# ----------------------------------------------------------------- machinery


def _bare(spec):
    """The shape, with everything that is only wording taken out."""
    if isinstance(spec, dict):
        return {k: _bare(v) for k, v in sorted(spec.items()) if k not in PROSE}
    if isinstance(spec, list):
        return [_bare(v) for v in spec]
    return spec


def _expanded(spec, doc: dict, seen: frozenset[str], depth: int = 0):
    """As :func:`_bare`, but with local references inlined.

    Two copies of one shape can each point at a local definition of their own,
    and then the literal comparison sees ``#/$defs/value`` against
    ``#/$defs/atom_value`` and calls them different. Cross-document references
    are left alone: those are the thing this file is asking for.
    """
    if isinstance(spec, dict):
        ref = spec.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref[len("#/$defs/"):]
            if name in seen or depth > 8:
                return {"$cycle": name}
            target = (doc.get("$defs") or {}).get(name)
            if target is not None:
                return _expanded(target, doc, seen | {name}, depth + 1)
        return {k: _expanded(v, doc, seen, depth + 1)
                for k, v in sorted(spec.items()) if k not in PROSE}
    if isinstance(spec, list):
        return [_expanded(v, doc, seen, depth + 1) for v in spec]
    return spec


def _records(docs):
    """Every named shape in every document: its root, and each ``$def``."""
    for name, spec in docs:
        entries = [(name.replace(".schema.json", ""), spec)]
        entries += sorted((spec.get("$defs") or {}).items())
        for defname, sub in entries:
            if isinstance(sub, dict) and "properties" in sub:
                yield name, defname, sub, spec


def _shipped():
    return [(d.name, d.spec) for d in schema_walk.shipped()]


def _duplicates(docs, key) -> list[list[tuple[str, str]]]:
    """Groups of two-or-more records of one shape, in different documents."""
    seen: dict[str, list[tuple[str, str]]] = {}
    for fname, defname, sub, whole in _records(docs):
        seen.setdefault(key(sub, whole, defname), []).append((fname, defname))
    return [where for where in seen.values()
            if len({f for f, _ in where}) > 1]


def _literal(sub, _whole, _defname):
    return json.dumps(_bare(sub), sort_keys=True)


def _renamed(sub, whole, defname):
    return json.dumps(_expanded(sub, whole, frozenset({defname})),
                      sort_keys=True)


def _independent(docs) -> dict[str, set[str]]:
    """Per bare name, the documents that *record* it rather than borrow it.

    A definition that is a ``$ref`` is not a second record of anything, which
    is the whole point of making it one — so it does not count here, and a
    name shared only that way needs no adjudication.
    """
    out: dict[str, set[str]] = {}
    for fname, spec in docs:
        entries = [(fname.replace(".schema.json", ""), spec)]
        entries += sorted((spec.get("$defs") or {}).items())
        for defname, sub in entries:
            if not isinstance(sub, dict):
                continue
            key = defname.lower().replace("_", "")
            out.setdefault(key, set())
            if "$ref" not in sub:
                out[key].add(fname)
    return out


# ---------------------------------------------------- one shape, one record


def test_no_shape_is_recorded_in_two_documents():
    groups = _duplicates(_shipped(), _literal)
    assert groups == [], (
        "the same shape is written down in more than one document; make one "
        f"of each group a $ref to the other: {groups}"
    )


def test_no_shape_is_recorded_twice_behind_two_local_names():
    """The copy the literal comparison cannot see.

    Two records can be identical except that each points at a local definition
    of its own; expanding those makes the copy visible.
    """
    groups = _duplicates(_shipped(), _renamed)
    assert groups == [], (
        "the same shape, once local definitions are expanded, is written down "
        f"in more than one document: {groups}"
    )


def test_a_document_that_copies_a_shape_is_refused(tmp_path):
    """The counterexample: a second, byte-identical record of a live shape."""
    docs = _shipped()
    source = dict(next(spec for name, spec in docs
                       if name == "derivation.schema.json")["$defs"]["term"])
    copied = [
        (name, {**spec, "$defs": {**(spec.get("$defs") or {}),
                                  "borrowed_term": source}}
         if name == "orientation_common.schema.json" else spec)
        for name, spec in docs
    ]
    assert _duplicates(copied, _literal) != [], (
        "a verbatim second record of derivation's `term` went unnoticed"
    )


def test_a_copy_hiding_behind_a_renamed_local_def_is_refused():
    """The copy the literal rule provably cannot see, so the second rule earns
    its place rather than restating the first.

    Built from scratch, because the disguise has to be exact: the inner
    definition must differ in *name* while agreeing in *shape*, and must
    itself be invisible to the literal rule — which it is here because it has
    no ``properties``, so nothing walks into it. ``derivation.value`` against
    ``verification_context.atom_value`` is this arrangement in the shipped
    documents; they are two different shapes today, and this is what the rule
    would say on the day they stopped being.
    """
    shape = {"type": "object", "properties": {"v": {"$ref": "#/$defs/PLACE"}}}
    pair = [
        ("a.schema.json", {"$defs": {
            "cell": json.loads(json.dumps(shape).replace("PLACE", "val")),
            "val": {"type": ["number", "string"]}}}),
        ("b.schema.json", {"$defs": {
            "cell": json.loads(json.dumps(shape).replace("PLACE", "amount")),
            "amount": {"type": ["number", "string"]}}}),
    ]

    assert _duplicates(pair, _literal) == [], (
        "this counterexample is meant to be invisible to the literal rule; if "
        "that rule already sees it, it is not exercising the other one"
    )
    assert _duplicates(pair, _renamed) != [], (
        "one shape recorded twice behind two local names went unnoticed"
    )


# ----------------------------------------------- and one name, one meaning


def test_a_name_two_documents_both_record_is_adjudicated():
    """Same name, neither a reference to the other: say why, or merge them.

    A shared name is not itself a defect — the same word can honestly mean two
    things. What is a defect is nobody having decided which case it is.
    """
    shared = {name for name, files in _independent(_shipped()).items()
              if len(files) > 1}
    assert shared <= set(DIFFERENT_THINGS), (
        "these names are recorded independently by two documents and nothing "
        f"says whether that is deliberate: {sorted(shared - set(DIFFERENT_THINGS))}"
    )


def test_the_table_names_no_pair_that_is_no_longer_there():
    """The other direction, so the table cannot outlive what it explains."""
    shared = {name for name, files in _independent(_shipped()).items()
              if len(files) > 1}
    assert set(DIFFERENT_THINGS) <= shared, (
        "these names are declared to be two different things, but only one "
        f"document records them now: {sorted(set(DIFFERENT_THINGS) - shared)}"
    )


# ------------------------------------------------------------ one entrance


def _validator_calls(tree: ast.Module) -> list[int]:
    """Lines building a JSON Schema validator anywhere but the one entrance.

    A hand-assembled registry counts as building one, even though it looks
    careful: it names the documents its author knew about, and the reference
    added next year is to a document they did not. That is the same failure as
    passing no registry at all, arriving later. ``validator_for`` globs.
    """
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None)
        if name == "Draft202012Validator":
            bad.append(node.lineno)
        elif (name == "validate" and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "jsonschema"):
            bad.append(node.lineno)      # this one cannot take a registry
    return sorted(bad)


def _sources():
    for base in ("themis", "tests"):
        for path in sorted((REPO / base).rglob("*.py")):
            yield path.relative_to(REPO)


def test_every_validator_is_built_through_the_shared_registry():
    offenders = {}
    for rel in _sources():
        if rel == THE_ENTRANCE:
            continue
        lines = _validator_calls(ast.parse(
            (REPO / rel).read_text(encoding="utf-8")))
        if lines:
            offenders[str(rel)] = lines
    assert offenders == {}, (
        "these build a validator that cannot resolve a reference into another "
        f"document; call validator_for() instead: {offenders}"
    )


def test_a_bare_validator_is_refused():
    """The counterexamples, and the repair, so the rule is shown to discriminate."""
    assert _validator_calls(ast.parse(
        "import jsonschema\njsonschema.validate({}, {})\n")) == [2]

    assert _validator_calls(ast.parse(
        "from jsonschema import Draft202012Validator\n"
        "Draft202012Validator({}).validate({})\n")) == [2]

    # The careful-looking one: a registry, holding the documents its author
    # thought of. This is what four test modules did before this rule.
    assert _validator_calls(ast.parse(
        "registry = Registry().with_resources([('derivation.schema.json', r)])\n"
        "Draft202012Validator(schema, registry=registry)\n")) == [2]

    fixed = ("from themis.input.syntactic_validator import validator_for\n"
             "v = validator_for('query_result.schema.json')\n"
             "v.evolve(schema=v.schema['properties']['x']).validate({})\n")
    assert _validator_calls(ast.parse(fixed)) == []


# ------------------------------------------- and the references still work


#: Where each borrowed shape now lives, and the document that borrows it.
BORROWED = [
    ("query_result.schema.json", "constantExpr",
     "derivation.schema.json#/$defs/constant"),
    ("query_result.schema.json", "varRef",
     "derivation.schema.json#/$defs/var_ref"),
    ("query_result.schema.json", "bindDecl",
     "derivation.schema.json#/$defs/sum_bind"),
    ("verification_context.schema.json", "atom",
     "derivation.schema.json#/$defs/atom"),
    ("verification_context.schema.json", "graph",
     "derivation.schema.json#/$defs/graph"),
    ("verification_context.schema.json", "term",
     "derivation.schema.json#/$defs/term"),
    ("kb_result.schema.json", "kbQuery", "kb_query.schema.json#"),
]


@pytest.mark.parametrize("fname,defname,ref", BORROWED)
def test_each_borrowed_shape_resolves_to_a_real_one(fname, defname, ref):
    """A reference that resolves to nothing reads like one that works.

    Nothing downstream tells an unreachable subschema apart from a subschema
    that an instance happened not to enter — both are silent — so this asks
    the registry to perform the lookup instead of waiting for a payload to.
    """
    doc = validator_for(fname).schema
    assert doc["$defs"][defname]["$ref"] == ref

    registry = _load_registry(str(SCHEMAS))
    resolved = registry.resolver(base_uri=doc["$id"]).lookup(ref).contents
    assert isinstance(resolved, dict) and resolved.get("properties"), (
        f"{fname}#{defname} points at {ref}, which is not a shape"
    )


def test_a_borrowed_shape_is_load_bearing():
    """Break the borrowed shape and the document refuses — so the reference is
    doing the work, not merely sitting there resolving."""
    whole = validator_for("verification_context.schema.json")
    graph = whole.evolve(schema=whole.schema["$defs"]["graph"])

    graph.validate({"kind": "graph", "nodes": [], "edges": []})

    with pytest.raises(ValidationError):
        # `nodes` holds atoms, and that is knowable only through the reference
        # into derivation.schema.json.
        graph.validate({"kind": "graph", "nodes": [{"not": "an atom"}],
                        "edges": []})
