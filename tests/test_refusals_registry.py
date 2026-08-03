"""The refusal registry, checked against the system that uses it.

A registry is worth exactly what checks it, and this one replaces two
lists that were never checked against each other: the species an
estimator raised, and the enum the result schema declared. Fifty of the
sixty-four species never reached the enum, so every envelope carrying one
failed Themis's own schema — silently, because validation happened to run
elsewhere.

Four directions can rot. A species can be emitted without being declared
(the two single exits close that on every run, and the exception closes it
at the raise). A species can be declared long after nothing emits it. The
schema can fall behind the registry again, which is the failure this
module exists because of, so it is the one pinned hardest. And ``kind``,
the one field a consumer actually branches on, can start being written at
the sites that refuse instead of stamped from here — which would recreate
the same drift one field over.
"""
import ast
import json
import pathlib

import pytest

from themis import refusals
from themis.refusals import EstimatorFailure

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "themis"
REGISTRY = PACKAGE / "refusals.py"


def _sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        if path == REGISTRY:
            continue
        yield str(path.relative_to(REPO)).replace("\\", "/"), path.read_text(
            encoding="utf-8")


def _registry_attributes() -> set[str]:
    """Every ``refusals.<NAME>`` mentioned anywhere outside the registry."""
    used: set[str] = set()
    for _rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "refusals"
            ):
                used.add(node.attr)
    return used


def test_the_registry_declares_what_it_says_it_declares():
    """``ALL`` is collected from the module, not listed again below it."""
    declared = {
        name for name, value in vars(refusals).items()
        if isinstance(value, refusals.Refusal)
    }
    assert {str(s) for s in refusals.ALL} == {
        str(getattr(refusals, name)) for name in declared
    }
    assert len(refusals.ALL) == len(declared), "two names for one species"


def test_every_species_declares_a_kind_and_every_kind_has_species():
    """``kind`` is the whole reason a consumer can act on a refusal. A kind
    nothing is filed under is a distinction that was never real."""
    assert set(refusals.BY_KIND) == set(refusals.KINDS)
    assert sum(len(v) for v in refusals.BY_KIND.values()) == len(refusals.ALL)
    for kind, species in refusals.BY_KIND.items():
        assert species, f"kind {kind!r} classifies nothing"


@pytest.mark.parametrize("species", sorted(refusals.ALL))
def test_every_registered_species_is_referred_to_by_something(species):
    """A registration nothing refers to is a refusal that has been deleted
    everywhere except here — the registry describing a system that no
    longer exists, which is worse than no registry."""
    constant = {
        name for name, value in vars(refusals).items()
        if isinstance(value, refusals.Refusal) and value == species
    }
    assert _registry_attributes() & constant, (
        f"{species!r} is registered but no module names refusals.{constant}"
    )


def test_the_schema_enum_is_exactly_the_registry():
    """The failure this whole module exists because of. The schema used to
    carry its own hand-copied list; it fell fifty species behind and every
    envelope carrying one of those fifty failed validation. The list is
    now a projection of the registry, and this is what holds it there."""
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    enum = schema["properties"]["estimator_failure"]["properties"][
        "failure_type"]["enum"]
    assert set(enum) == set(refusals.BY_NAME), {
        "declared, not in schema": sorted(set(refusals.BY_NAME) - set(enum)),
        "in schema, not declared": sorted(set(enum) - set(refusals.BY_NAME)),
    }
    assert len(enum) == len(set(enum)), "the schema enum repeats a species"


def test_the_schema_kind_enum_is_exactly_the_kinds():
    """``kind`` is the field a consumer branches on, so the envelope's
    contract has to admit exactly the five and no sixth."""
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    enum = schema["properties"]["estimator_failure"]["properties"][
        "kind"]["enum"]
    assert set(enum) == set(refusals.KINDS)
    assert len(enum) == len(set(enum))


def test_the_species_of_a_refusal_is_never_spelled_at_the_raise():
    """The first argument of ``EstimatorFailure`` names the registry — it
    is never a literal and never assembled.

    Assembling is not hypothetical. One site built its species with an
    f-string over a loop variable, which is how ``instrument_not_binary``
    came to exist without appearing in any list, any test, or the schema:
    no sweep for string literals could see it, because it was never
    written down anywhere.
    """
    offenders = []
    for rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(
                func, "id", None)
            if name != "EstimatorFailure":
                continue
            if isinstance(node.args[0], (ast.Constant, ast.JoinedStr)):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, offenders


_GENERIC_FAILURES = {
    "BaseException", "Exception", "RuntimeError", "ArithmeticError",
    "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
    "NotImplementedError", "OSError", "LinAlgError",
}


def _caught_names(node) -> set[str]:
    """Every exception name in one ``except`` clause."""
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    names = set()
    for part in parts:
        if isinstance(part, ast.Attribute):
            names.add(part.attr)
        elif isinstance(part, ast.Name):
            names.add(part.id)
    return names


def test_an_honest_refusal_is_not_caught_beside_a_crash():
    """Declining and crashing must not share a branch.

    Nine clauses in dispatch caught ``EstimatorFailure`` together with
    ``ValueError`` and ``NotImplementedError``, so a bug in an estimator
    produced exactly what an honest refusal produces: no number, no
    message, a structural answer that looks deliberate. They were written
    that way because before this registry there was no reliable way to
    tell the two apart, so tolerating the whole exception type was the
    safe move.

    Instrumenting all nine and running the suite recorded 127 catches,
    every one of them an ``EstimatorFailure``: the wider types were never
    reached. A named domain exception may still be caught beside a
    refusal — some estimators raise their own — but a generic one may
    not, because that is the basket the two fell into.
    """
    offenders = []
    for rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            names = _caught_names(node.type)
            if "EstimatorFailure" not in names:
                continue
            generic = names & _GENERIC_FAILURES
            if generic:
                offenders.append(f"{rel}:{node.lineno} also catches {sorted(generic)}")
    assert not offenders, offenders


def test_a_species_is_the_plain_name_once_it_is_data():
    """The registry hands out ``str`` subclasses so a misspelling is an
    AttributeError at import. What lands in the envelope has to be the
    string it always was — a copy or a pickle that came back carrying
    registry metadata would make the envelope depend on this module."""
    import copy
    import pickle

    block = {"failure_type": refusals.SINGULAR_CONFUSION_MATRIX}
    assert json.loads(json.dumps(block)) == {
        "failure_type": "singular_confusion_matrix"}
    assert type(copy.deepcopy(block)["failure_type"]) is str
    assert type(pickle.loads(pickle.dumps(refusals.UNKNOWN))) is str


def test_an_unregistered_species_is_refused_when_the_refusal_is_born():
    """Earlier than the exit, and more precise: the raise site is named in
    the traceback."""
    with pytest.raises(ValueError, match="unregistered failure_type"):
        EstimatorFailure("no_such_reason", "a message")

    exc = EstimatorFailure(refusals.SAMPLE_TOO_SMALL, "too few rows", n=3)
    assert exc.failure_type == "sample_too_small"
    assert exc.failure_type.kind == refusals.KIND_DATA
    assert exc.details == {"n": 3}


def test_an_unregistered_species_is_refused_at_the_exit():
    """Dispatch writes the block by hand at some thirty sites, where there
    is no constructor to check. This is what covers those."""
    result = {"query_id": "q1", "estimator_failure": {
        "estimator": "e", "failure_type": "overlap_insufficient",
        "reason": "r"}}
    refusals.stamp(result)

    result["estimator_failure"]["failure_type"] = "a_reason_nobody_declared"
    with pytest.raises(ValueError, match="unregistered failure_type"):
        refusals.stamp(result)


def test_the_exit_is_where_the_kind_comes_from():
    """The site that refuses says which species; the registry says what to
    do about it. A site that answered both would be the second copy."""
    result = {"query_id": "q1", "estimator_failure": {
        "estimator": "e", "failure_type": "overlap_insufficient",
        "reason": "r"}}
    refusals.stamp(result)
    assert result["estimator_failure"]["kind"] == refusals.KIND_DATA

    # The registry is the authority, not whatever was there before.
    result["estimator_failure"]["kind"] = "graph"
    refusals.stamp(result)
    assert result["estimator_failure"]["kind"] == refusals.KIND_DATA


def test_the_kind_of_a_refusal_is_never_written_where_it_is_refused():
    """Thirty-odd sites build the block by hand, each knowing its own
    occasion. None of them knows anything about the kind that the species
    has not already said, so none of them writes it — the exit stamps it.
    A site that spelled it out would be a second copy of the registry,
    free to disagree with it, which is the shape of the original defect.
    """
    offenders = []
    for rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            if "failure_type" in keys and "kind" in keys:
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, offenders


def test_a_result_that_refuses_nothing_is_not_a_violation():
    refusals.stamp({"query_id": "q1"})
    refusals.stamp({"query_id": "q1", "estimator_failure": None})


def test_a_real_refusal_reaches_the_caller_as_a_registered_species():
    """The exit check, reached the way a caller reaches it — and the
    envelope's own schema, applied to what came back."""
    import numpy as np
    import pandas as pd

    import themis

    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "u"}]}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": v} for v in ("w", "x", "y")
        ] + [
            {"kind": "cause", "from": atom("w"), "to": atom("x")},
            {"kind": "cause", "from": atom("w"), "to": atom("y")},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": []}},
        ],
    }
    rng = np.random.default_rng(3)
    n = 400
    w = rng.normal(size=n)
    x = 0.5 * w + rng.normal(size=n)
    frame = pd.DataFrame(
        {"w": w, "x": x, "y": 0.8 * x + w + rng.normal(size=n)})

    result = themis.estimate(
        program, frame, measurement_error={"x": {"error_variance": -1.0}},
    )["results"][0]

    species = result["estimator_failure"]["failure_type"]
    assert species in refusals.BY_NAME
    # The kind reached the caller, who is where it has to be: a reader of
    # the envelope has no registry to look the species up in.
    assert result["estimator_failure"]["kind"] == refusals.KIND_REQUEST

    import jsonschema
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    jsonschema.validate(
        json.loads(json.dumps(result["estimator_failure"])),
        schema["properties"]["estimator_failure"],
    )
