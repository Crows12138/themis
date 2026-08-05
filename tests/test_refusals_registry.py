"""The refusal registry, checked against the system that uses it.

A registry is worth exactly what checks it, and this one replaces two
lists that were never checked against each other: the species an
estimator raised, and the enum the result schema declared. Fifty of the
sixty-four species never reached the enum, so every envelope carrying one
failed Themis's own schema — silently, because validation happened to run
elsewhere.

Five directions can rot. A species can be emitted without being declared
(the two single exits close that on every run, and the exception closes it
at the raise). A species can be declared long after nothing emits it. The
schema can fall behind the registry again, which is the failure this
module exists because of, so it is the one pinned hardest. ``kind``, the
one field a consumer actually branches on, can start being written at the
sites that refuse instead of stamped from here — which would recreate the
same drift one field over. And a refusal can be caught and then never
reach the envelope at all, which is the one failure none of the others
can see: a registry cannot check a species nobody wrote down.

Two of the directions this module used to watch are no longer test-shaped.
The registry was a set gathered from module constants, so a constant left
out of it and two constants sharing one name both had to be asserted; the
registry is an ``enum`` now and both are import-time errors — the class
*is* the collection, and ``@unique`` will not admit an alias. What is left
here is what the language cannot see: the schema, the envelope, and
whether anything still refers to a species at all.
"""
import ast
import json
import pathlib

import pytest

from themis import refusals
from themis.refusals import Refusal, Kind
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
    """Every ``Refusal.<NAME>`` mentioned anywhere outside the registry."""
    used: set[str] = set()
    for _rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Refusal"
            ):
                used.add(node.attr)
    return used


def test_a_species_is_named_the_same_thing_twice():
    """The member's name and the name on the envelope are one decision.

    They were two: a constant in this package and a string in the
    envelope, related only by whoever typed both. A member spelled
    ``EMPTY_OUTCOME = ("emty_outcome", ...)`` would have raised nowhere —
    the schema test below would have caught it, but only by reporting a
    schema that was right."""
    assert [s.name for s in Refusal if s.name.lower() != s.value] == []


def test_every_kind_classifies_something():
    """``kind`` is the whole reason a consumer can act on a refusal. A kind
    nothing is filed under is a distinction that was never real.

    The converse — every species declaring a kind — is the constructor's
    signature now, so there is nothing here to assert about it."""
    for kind in Kind:
        assert any(s.kind is kind for s in Refusal), (
            f"kind {kind!r} classifies nothing")


@pytest.mark.parametrize("species", sorted(Refusal))
def test_every_registered_species_is_referred_to_by_something(species):
    """A registration nothing refers to is a refusal that has been deleted
    everywhere except here — the registry describing a system that no
    longer exists, which is worse than no registry."""
    assert species.name in _registry_attributes(), (
        f"{species!r} is registered but no module names Refusal.{species.name}"
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
    assert set(enum) == set(Refusal), {
        "declared, not in schema": sorted(set(Refusal) - set(enum)),
        "in schema, not declared": sorted(set(enum) - set(Refusal)),
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
    assert set(enum) == set(Kind)
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


def test_a_query_that_ends_without_a_number_says_why():
    """A handler that catches a refusal and closes the query must put the
    reason on the envelope.

    ``blocked`` means no later estimator will answer, so whatever the
    handler leaves behind is what the caller gets. Five of them left
    nothing at all: the query came back identified, carrying a formula and
    no number, and neither the envelope nor the gap report recorded that
    an estimator had run and declined. The report then rendered the
    structural verdict in the answer slot, which is how a positivity
    violation reached a reader as a confident "yes".

    Handlers that ``pass`` instead are exempt, and the distinction is the
    point: there the query is still in flight, a later estimator may
    answer it, and a refusal written now would sit on the envelope beside
    that answer as if the two disagreed.
    """
    offenders = []
    for rel, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            if "EstimatorFailure" not in _caught_names(node.type):
                continue
            inner = list(ast.walk(node))
            ends_here = any(
                isinstance(n, ast.Call) and getattr(n.func, "id", None) == "blocked"
                for n in inner
            )
            says_why = any(
                isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "record"
                for n in inner
            )
            if ends_here and not says_why:
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, offenders


def test_a_refusal_carries_the_numbers_it_measured():
    """``details`` is the difference between knowing the shape of a
    problem and knowing its size. The estimator has already paid to
    measure which stratum was empty and how many rows were in it; every
    handler but one used to drop that on the floor."""
    exc = EstimatorFailure(
        Refusal.SAMPLE_TOO_SMALL, "too few rows", n=3, needed=30)
    result = {"query_id": "q"}
    refusals.record(result, estimator="backdoor", exc=exc)
    assert result["estimator_failure"] == {
        "estimator": "backdoor",
        "failure_type": "sample_too_small",
        "reason": "too few rows",
        "details": {"n": 3, "needed": 30},
    }

    # A refusal with nothing to measure does not carry an empty map.
    bare = {"query_id": "q"}
    refusals.record(
        bare, estimator="backdoor",
        exc=EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, "too few rows"))
    assert "details" not in bare["estimator_failure"]


def test_a_terminal_refusal_reaches_the_caller_and_not_only_the_log():
    """The defect this all exists for, end to end.

    A proximal query on data whose (Z, X) table has an empty cell. The
    estimator refuses for a reason it can state precisely; before this,
    the caller received an envelope with no number, no refusal, and an
    empty gap report — the run was indistinguishable from one that had
    never been given data.
    """
    import numpy as np
    import pandas as pd

    import themis

    def var(p):
        return {"kind": "variable", "predicate": p, "domain": [True, False]}

    def cause(a, b):
        return {"kind": "cause", "from": {"predicate": a, "args": []},
                "to": {"predicate": b, "args": []}}

    def atom(p):
        return {"predicate": p, "args": []}

    program = {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            var("x"), var("y"), var("u"), var("z"), var("w"),
            cause("u", "x"), cause("u", "y"), cause("u", "z"),
            cause("u", "w"), cause("z", "x"), cause("w", "y"), cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": atom("x"), "outcome": atom("y"),
                "latent": atom("u"), "treatment_proxy": atom("z"),
                "outcome_proxy": atom("w"), "latent_cardinality": 2}},
        ],
    }
    rng = np.random.default_rng(7)
    n = 3000
    u = rng.random(n) < 0.5
    z = rng.random(n) < np.where(u, 0.80, 0.20)
    w = rng.random(n) < np.where(u, 0.85, 0.25)
    frame = pd.DataFrame(  # X is Z exactly, so two (Z, X) cells are empty
        {"x": z, "y": rng.random(n) < (0.15 + 0.35 * z + 0.25 * u),
         "z": z, "w": w})

    result = themis.estimate(program, frame)["results"][0]

    assert result.get("numeric_estimate") is None
    failure = result["estimator_failure"]
    assert failure["estimator"] == "proximal"
    assert failure["failure_type"] in refusals.BY_NAME
    assert failure["kind"] in set(Kind)
    assert failure["reason"]


def test_a_species_is_the_plain_name_once_it_is_data():
    """The registry hands out enum members so a misspelling is a name that
    does not exist. What lands in the envelope has to be the string it
    always was — a copy or a pickle that came back carrying registry
    metadata would make the envelope depend on this module.

    An enum does not do this by itself: its members are singletons and it
    pickles them by looking them up again here. ``__reduce_ex__`` is what
    holds the boundary, and this is what holds ``__reduce_ex__``."""
    import copy
    import pickle

    block = {"failure_type": Refusal.SINGULAR_CONFUSION_MATRIX}
    assert json.loads(json.dumps(block)) == {
        "failure_type": "singular_confusion_matrix"}
    assert type(copy.deepcopy(block)["failure_type"]) is str
    assert type(pickle.loads(pickle.dumps(Refusal.UNKNOWN))) is str


def test_an_unregistered_species_is_refused_when_the_refusal_is_born():
    """Earlier than the exit, and more precise: the raise site is named in
    the traceback."""
    with pytest.raises(ValueError, match="unregistered failure_type"):
        EstimatorFailure("no_such_reason", "a message")

    exc = EstimatorFailure(Refusal.SAMPLE_TOO_SMALL, "too few rows", n=3)
    assert exc.failure_type == "sample_too_small"
    assert exc.failure_type.kind == Kind.DATA
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
    assert result["estimator_failure"]["kind"] == Kind.DATA

    # The registry is the authority, not whatever was there before.
    result["estimator_failure"]["kind"] = "graph"
    refusals.stamp(result)
    assert result["estimator_failure"]["kind"] == Kind.DATA


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
    assert result["estimator_failure"]["kind"] == Kind.REQUEST

    import jsonschema
    schema = json.loads(
        (PACKAGE / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8")
    )
    jsonschema.validate(
        json.loads(json.dumps(result["estimator_failure"])),
        schema["properties"]["estimator_failure"],
    )
