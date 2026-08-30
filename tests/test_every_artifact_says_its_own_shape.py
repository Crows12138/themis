"""Being an artifact and having a declared shape were two facts, not one.

#387. ``themis.audits.Artifact`` is the closed list of things that leave the
process saying their own name — an envelope, a Markov blanket, the four phases
of interactive orientation. ``themis/schemas/`` described one of them. The two
lists were never linked: ``validate_result`` named its document with a string
literal, so ``query_result`` was described not because it is special but
because it is the one somebody hand-wired. A seventh artifact added tomorrow
would have been undescribed the same way, and nothing could have said so.

WHAT THAT COST, MEASURED. A schema is what every structural gate takes as its
denominator, so an artifact outside the directory is one no gate can reach.
``markov_blanket`` ships a ``data_hash``; #381 built the rule that a digest
travels with the column list it covers, and globbed the schema directory so a
container added tomorrow would be inside the rule the day it was added. It
never reached this one — not because the artifact broke the rule but because
nothing declared the artifact existed. The gate below asserts that it does now.

SO THE FIX IS THE LINK, AND THE FIVE FILES ARE ITS CONSEQUENCE. ``Artifact``
derives its own document name from its value, which already IS the ``kind``;
``validate_artifact`` dispatches on the recogniser the audit layer was already
using; the registry globs instead of naming four of seven. The five producers
then check their output the way ``kernel.py`` has always checked an envelope,
because a schema nothing validates is a description of what somebody believed
the producer emitted.

WHAT THIS DELIBERATELY DOES NOT DO. #371's rule — that "there is none" has one
spelling per key — is still asked only of ``query_result``, because
``schema_walk`` names that document. Nineteen keys in the six other shipped
schemas are optional AND nullable, so widening it is a change with its own
argument to make and its own nineteen decisions; the five new documents are
written to obey the rule regardless, and none of them has such a key.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from themis.audits import Artifact, artifact_of
from themis.estimation.discovery import markov_blanket, markov_blanket_to_dict
from themis.estimation.orientation import (
    orientation_to_dict, propagate_orientations,
)
from themis.estimation.orientation_ledger import orientation_ledger_export
from themis.estimation.orientation_questions import (
    compile_orientation_questions, question_set_to_dict,
)
from themis.estimation.orientation_session import (
    ingest_orientation_answers, session_to_dict, start_orientation_session,
)
from themis.estimation.discovery import discover_graph, notears_fit_to_dict
from themis.estimation.lagged_discovery import (
    discover_lagged_graph, lagged_discovery_to_dict,
)
from themis.input.syntactic_validator import SyntacticError, validate_artifact
from tests.test_a_fingerprint_carries_its_denominator import _pairings

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"

#: The four documents the registry loaded by name before #387, transcribed so
#: the widening is visible rather than asserted. Three of the seven shipped
#: schemas were outside it, which was invisible only because nothing outside
#: the four was ever referenced — and the orientation artifacts reference each
#: other, so a document missing from the registry is a subtree that goes
#: unchecked while reading as checked.
REGISTRY_WAS = (
    "atom.schema.json", "kernel_ast.schema.json",
    "query_result.schema.json", "derivation.schema.json",
)

#: The producers that must run their output past the door, and the function in
#: each that is the door. Every artifact leaves through one of these.
PRODUCERS = (
    ("themis/estimation/discovery.py", "markov_blanket_to_dict"),
    ("themis/estimation/discovery.py", "notears_fit_to_dict"),
    ("themis/estimation/lagged_discovery.py", "lagged_discovery_to_dict"),
    ("themis/estimation/orientation.py", "orientation_to_dict"),
    ("themis/estimation/orientation_questions.py", "question_set_to_dict"),
    ("themis/estimation/orientation_session.py", "session_to_dict"),
    ("themis/estimation/orientation_ledger.py", "orientation_ledger_export"),
)


# --- one live instance of every artifact --------------------------------------


def _blankets() -> list[dict]:
    """Both conditional-independence paths, because the test decides which
    sufficient statistic the artifact records and a schema that had only seen
    one of them would describe half the shape."""
    rng = np.random.default_rng(11)
    n = 1200
    z, w = rng.normal(size=n), rng.normal(size=n)
    x = 0.9 * z + rng.normal(size=n) * 0.5
    y = 0.8 * x + 0.6 * w + rng.normal(size=n) * 0.5
    continuous = pd.DataFrame(
        {"x": x, "y": y, "z": z, "w": w, "q": rng.normal(size=n)})

    dz = rng.random(n) < 0.5
    dx = rng.random(n) < np.where(dz, 0.8, 0.2)
    dy = rng.random(n) < np.where(dx, 0.75, 0.25)
    discrete = pd.DataFrame(
        {"x": dx, "y": dy, "z": dz, "q": rng.random(n) < 0.4})

    return [markov_blanket_to_dict(markov_blanket(continuous, "y")),
            markov_blanket_to_dict(markov_blanket(discrete, "y", alpha=0.01))]


def _orientations() -> dict[str, list[dict]]:
    """A propagation that applies cleanly, one that refuses every kind of
    input it can refuse, and one left open — the third is what produces
    orientation questions with cascades, which the first two have none of."""
    four = ("a", "b", "c", "d")
    clean = propagate_orientations(
        four, directed=(("a", "c"), ("b", "c")),
        undirected=(("c", "d"), ("a", "d")), constraints=(("c", "d"),))
    conflicted = propagate_orientations(
        four, directed=(("a", "c"), ("b", "c")), undirected=(("c", "d"),),
        constraints=(("c", "a"), ("d", "zz")),
        asserted_adjacencies=(("a", "b"), ("a", "zz")),
        asserted_absences=(("a", "c"), ("b", "d")))

    five = ("a", "b", "c", "d", "e")
    open_edges = (("c", "d"), ("d", "e"), ("a", "e"), ("b", "e"))
    open_cpdag = propagate_orientations(
        five, directed=(("a", "c"), ("b", "c")), undirected=open_edges)

    s0 = start_orientation_session(
        four, directed=(("a", "c"), ("b", "c")),
        undirected=(("c", "d"), ("a", "d")),
        asserted_adjacencies=(("a", "b"),))
    s1 = ingest_orientation_answers(s0, [
        {"edge": ["c", "d"], "direction": ["c", "d"],
         "source": "llm_proposal", "note": "文献里 c 在 d 之前"},
        {"edge": ["a", "d"], "adjacency": "absent", "source": "domain_expert"},
    ])
    s2 = ingest_orientation_answers(s1, [
        {"edge": ["a", "c"], "direction": ["c", "a"], "source": "llm_proposal"},
        {"edge": ["a", "b"], "direction": None, "note": "说不准"},
    ])
    s3 = start_orientation_session(
        five, directed=(("a", "c"), ("b", "c")), undirected=open_edges)

    return {
        "orientation_propagation": [
            orientation_to_dict(r) for r in (clean, conflicted, open_cpdag)],
        "orientation_question_set": [
            question_set_to_dict(compile_orientation_questions(r))
            for r in (clean, conflicted, open_cpdag)],
        "orientation_session": [
            session_to_dict(s) for s in (s0, s1, s2, s3)],
        "orientation_ledger_export": [
            orientation_ledger_export(s1, data_source="discovery:pc",
                                      subjects=("u",)),
            orientation_ledger_export(s2, data_source="discovery:ges"),
            orientation_ledger_export(s0),
        ],
    }


def _lagged() -> list[dict]:
    """A VAR whose lag structure is written down above the data that carries
    it, and the same run with a panel identifier — the two alignments, because
    the unit column is what keeps a lag from crossing between subjects and a
    schema that had only seen one of them would describe half the shape."""
    rng = np.random.default_rng(7)

    def series(n: int) -> tuple[np.ndarray, ...]:
        x, y, z = (np.zeros(n) for _ in range(3))
        ex, ey, ez = rng.normal(size=(3, n))
        for t in range(2, n):
            x[t] = 0.5 * x[t - 1] + ex[t]
            y[t] = 0.6 * y[t - 1] + 0.7 * x[t - 1] + ey[t]
            z[t] = 0.4 * z[t - 1] + 0.6 * y[t - 2] + ez[t]
        return x[50:], y[50:], z[50:]

    x, y, z = series(900)
    single = pd.DataFrame(
        {"t": np.arange(len(x)), "x": x, "y": y, "z": z})

    frames = []
    for who in ("a", "b"):
        ux, uy, uz = series(500)
        frames.append(pd.DataFrame({
            "who": who, "t": np.arange(len(ux)),
            "x": ux, "y": uy, "z": uz}))
    panel = pd.concat(frames, ignore_index=True)

    return [
        lagged_discovery_to_dict(
            discover_lagged_graph(single, time="t", max_lag=2)),
        lagged_discovery_to_dict(
            discover_lagged_graph(panel, time="t", unit="who", max_lag=1,
                                  alpha=0.01)),
    ]


def _notears() -> list[dict]:
    """A run whose answer survives standardising and one whose answer does
    not — the scale diagnostic is a per-edge split, and a schema that had
    only seen a fit where every edge survives would describe half the shape.
    A two-column frame comes third: an edgeless fit is where the varsortability
    denominator is zero, and 0.5 over no paths is a different sentence from
    0.5 over many."""
    rng = np.random.default_rng(3)
    n = 1500
    a = rng.normal(size=n)
    b = 1.2 * a + rng.normal(size=n)
    c = 0.8 * a + rng.normal(size=n)
    d = -0.9 * b + 1.1 * c + rng.normal(size=n)
    plain = pd.DataFrame({"a": a, "b": b, "c": c, "d": d})
    tilted = plain * np.array([2.0, 1.4, 0.7, 0.3])
    lone = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    return [
        notears_fit_to_dict(discover_graph(frame, algorithm="notears"))
        for frame in (plain, tilted, lone)
    ]


@pytest.fixture(scope="module")
def artifacts() -> dict[str, list[dict]]:
    out = {"markov_blanket": _blankets(), "lagged_discovery": _lagged(),
           "notears_fit": _notears()}
    out.update(_orientations())
    return out


# --- the link, and its denominator --------------------------------------------


def _undescribed(members, schema_dir=None) -> list[str]:
    """Every artifact whose document is missing, misnamed, or somebody else's.

    One function for the rule and for the counterexample below, so the thing
    shown to fire is the thing that guards. ``QUERY_RESULT`` is exempt from
    the last question only: an envelope carries ``query_kind``, which says
    what was ASKED, and no ``kind`` saying what the dict is — that asymmetry
    is what makes it the fallback the recogniser resolves to.
    """
    schema_dir = schema_dir or SCHEMAS
    missing = []
    for member in members:
        path = schema_dir / member.schema
        if not path.exists():
            missing.append(f"{member}: no {member.schema}")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("$id", "").rsplit("/", 1)[-1] != member.schema:
            missing.append(
                f"{member}: {member.schema} calls itself {doc.get('$id')!r}")
        if member is Artifact.QUERY_RESULT:
            continue
        declared = (doc.get("properties") or {}).get("kind") or {}
        if declared.get("const") != str(member):
            missing.append(
                f"{member}: {member.schema} does not declare kind = "
                f"{str(member)!r}")
    return missing


def test_every_artifact_has_a_document_that_describes_it():
    """The link, stated where it can fire.

    Derived from the member's own value rather than tabled, so a seventh
    artifact is inside this the day it is declared — which is the whole
    difference between this and the five files it produced.
    """
    assert not _undescribed(Artifact)


@pytest.mark.parametrize("break_it", ["delete", "rename", "wrong_kind"])
def test_the_rule_says_no_to_an_artifact_nobody_described(tmp_path, break_it):
    """The counterexample, one per way the link can be broken: no document at
    all, a document that answers to a different ``$id``, and a document that
    describes some other artifact. Run against a copy, because a rule shown
    firing on a doctored directory is a rule shown firing."""
    for src in SCHEMAS.glob("*.schema.json"):
        (tmp_path / src.name).write_bytes(src.read_bytes())

    target = Artifact.ORIENTATION_SESSION
    path = tmp_path / target.schema
    if break_it == "delete":
        path.unlink()
        expected = "no orientation_session.schema.json"
    else:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if break_it == "rename":
            doc["$id"] = "https://example.local/causal-kernel/elsewhere.json"
            expected = "calls itself"
        else:
            doc["properties"]["kind"]["const"] = "orientation_propagation"
            expected = "does not declare kind"
        path.write_text(json.dumps(doc), encoding="utf-8")

    problems = _undescribed(Artifact, tmp_path)
    assert problems, break_it
    assert all(expected in p for p in problems), problems


def test_the_rule_has_a_denominator():
    """Eight artifacts, seven of them standalone. A rule over an empty registry
    passes by saying nothing."""
    assert len(Artifact) == 8, list(Artifact)
    standalone = [a for a in Artifact if a is not Artifact.QUERY_RESULT]
    assert len(standalone) == 7
    assert {a.schema for a in Artifact} <= {
        p.name for p in SCHEMAS.glob("*.schema.json")}


def test_the_registry_no_longer_names_four_of_seven():
    """What the glob replaced. Every shipped document is now reachable by its
    ``$id``, which is what makes a cross-document ``$ref`` resolve to a schema
    instead of to nothing."""
    from themis.input.syntactic_validator import _default_schema_dir

    shipped = sorted(p.name for p in SCHEMAS.glob("*.schema.json"))
    assert set(REGISTRY_WAS) < set(shipped), shipped
    registry = _load_ids(_default_schema_dir())
    assert {a.schema for a in Artifact} <= registry
    assert len(registry) == len(shipped)


def _load_ids(schema_dir: pathlib.Path) -> set[str]:
    return {json.loads(p.read_text(encoding="utf-8"))["$id"].rsplit("/", 1)[-1]
            for p in schema_dir.glob("*.schema.json")}


# --- and every artifact goes through it ---------------------------------------


@pytest.mark.parametrize("name", sorted(str(a) for a in Artifact
                                        if a is not Artifact.QUERY_RESULT))
def test_a_live_artifact_is_recognised_and_accepted(artifacts, name):
    """Traffic, not declaration. The recogniser routes each payload to its own
    document, and the document accepts what the producer actually emits —
    which is the half a schema written from reading the builder can get wrong.
    """
    specimens = artifacts[name]
    assert specimens
    for payload in specimens:
        assert str(artifact_of(payload)) == name
        assert validate_artifact(payload) is payload


def test_an_envelope_is_not_routed_by_a_stray_kind():
    """``validate_result`` names its document rather than dispatching, because
    an envelope carries no ``kind`` of its own: anything that is not a
    standalone artifact resolves to ``query_result``, and a misspelt ``kind``
    must land there rather than silently pass as something else."""
    assert artifact_of({"kind": "markov_blankett"}) is Artifact.QUERY_RESULT
    with pytest.raises(SyntacticError):
        validate_artifact({"kind": "markov_blankett", "target": "y"})


# --- each way of getting one wrong ---------------------------------------------


def _broken(artifacts):
    """Every counterexample, as (label, payload). A declaration that cannot
    say no describes nothing, and each of these is a way a producer has
    actually gone wrong somewhere in this repo: a dropped key, a digest
    without its denominator, a value outside a closed vocabulary, a shape
    from the sibling branch, an extra key nobody declared."""
    mb = artifacts["markov_blanket"][0]
    op = artifacts["orientation_propagation"]
    qs = artifacts["orientation_question_set"][2]
    se = artifacts["orientation_session"][1]
    le = artifacts["orientation_ledger_export"][0]

    def edit(payload, fn):
        out = copy.deepcopy(payload)
        fn(out)
        return out

    conflicted = op[1]
    key = next(k for k in ("constraint", "assertion", "absence")
               if k in conflicted["conflicts"][0])
    other = next(k for k in ("constraint", "assertion", "absence") if k != key)

    return [
        ("a digest with no column list under it",
         edit(mb, lambda d: d.pop("data_columns"))),
        ("a digest that is not a SHA-256",
         edit(mb, lambda d: d.update(data_hash="abc"))),
        ("a fisherz run carrying both sufficient statistics",
         edit(mb, lambda d: d.update(contingency={"levels": [], "counts": []}))),
        ("a fisherz test entry wearing a chi-square statistic",
         edit(mb, lambda d: d["tests"][0].update(statistic=3.0))),
        ("a test role outside the two halves of the definition",
         edit(mb, lambda d: d["tests"][0].update(role="shielded"))),
        ("a conflict reason nobody declared",
         edit(op[1], lambda d: d["conflicts"][0].update(reason="just_because"))),
        ("a conflict claiming two kinds of refused input at once",
         edit(conflicted,
              lambda d: d["conflicts"][0].update({other: ["a", "b"]}))),
        ("an orientation forced by a Meek rule that does not exist",
         edit(op[0], lambda d: d["provenance"][0].update(rule="R5"))),
        ("an edge with three nodes in it",
         edit(op[0], lambda d: d["oriented"].append(["a", "b", "c"]))),
        ("a cascade that does not say what it determines",
         edit(qs, lambda d: d["questions"][0].update(
             detail={"forward": {"answer": ["a", "b"]}}))),
        ("leverage as a word rather than a count",
         edit(qs, lambda d: d["questions"][0].update(leverage="high"))),
        ("an answer that omits the field it should have nulled",
         edit(se, lambda d: d["answers"][0].pop("adjacency"))),
        ("a session status outside the three",
         edit(se, lambda d: d.update(status="pending"))),
        ("a bad rule inside the EMBEDDED propagation",
         edit(se, lambda d: d["propagation"]["provenance"][0].update(rule="R9"))),
        ("a data source that does not say it came from discovery",
         edit(le, lambda d: d.update(data_source="pc"))),
        ("a bad status two artifacts deep",
         edit(le, lambda d: d["session"].update(status="pending"))),
        ("an annotation on a cause statement that nobody declared",
         edit(le, lambda d: d["cause_statements"][0]["annotations"].update(
             confidence=0.9))),
    ]


def test_each_way_of_getting_an_artifact_wrong_is_refused(artifacts):
    survived = []
    for label, payload in _broken(artifacts):
        try:
            validate_artifact(payload)
        except SyntacticError:
            continue
        survived.append(label)
    assert not survived


def test_the_counterexamples_are_not_all_the_same_one(artifacts):
    """Seventeen labels that all failed on a missing ``kind`` would be one
    counterexample seventeen times."""
    broken = _broken(artifacts)
    assert len(broken) >= 15
    assert len({artifact_of(p).schema for _, p in broken}) == 5


# --- the doors are armed, and the embedded artifacts are referenced ------------


@pytest.mark.parametrize("rel,func", PRODUCERS,
                         ids=[f for _, f in PRODUCERS])
def test_every_producer_runs_its_output_past_the_door(rel, func):
    """Read off the source, so a producer that stops validating is caught even
    where no test happens to call it. A schema nothing validates describes what
    somebody believed the producer emitted."""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == func)
    calls = {n.func.id for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "validate_artifact" in calls, sorted(calls)
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns and all(
        isinstance(r.value, ast.Call) and isinstance(r.value.func, ast.Name)
        and r.value.func.id == "validate_artifact" for r in returns), (
        f"{func} returns without going through the door")


def test_a_producer_handed_a_broken_result_refuses_at_the_door():
    """Behaviour rather than source: the two shapes of defect the artifacts
    are most exposed to — a digest that is not one, and a rule outside the
    closure — reach the door through the producer's own public entry."""
    rng = np.random.default_rng(3)
    z = rng.normal(size=200)
    x = z + rng.normal(size=200) * 0.4
    result = markov_blanket(
        pd.DataFrame({"x": x, "y": x + rng.normal(size=200) * 0.4, "z": z}),
        "y")
    with pytest.raises(SyntacticError):
        markov_blanket_to_dict(dataclasses.replace(result, data_hash="nope"))

    prop = propagate_orientations(
        ("a", "b", "c"), directed=(("a", "c"), ("b", "c")))
    bad = dataclasses.replace(
        prop, provenance=({"from": "a", "to": "c", "rule": "R7",
                           "roots": ()},))
    with pytest.raises(SyntacticError):
        orientation_to_dict(bad)


def test_an_embedded_artifact_is_referenced_and_not_restated():
    """A session embeds a propagation and a question set; an export embeds a
    session. They are those artifacts — the producers call the producers — so
    a second declaration of the same shape would be the pair of tables that
    were once equal."""
    session = json.loads(
        (SCHEMAS / Artifact.ORIENTATION_SESSION.schema).read_text("utf-8"))
    export = json.loads(
        (SCHEMAS / Artifact.ORIENTATION_LEDGER_EXPORT.schema).read_text("utf-8"))
    assert session["properties"]["propagation"]["$ref"] == \
        Artifact.ORIENTATION_PROPAGATION.schema
    assert session["properties"]["question_set"]["$ref"] == \
        Artifact.ORIENTATION_QUESTION_SET.schema
    assert export["properties"]["session"]["$ref"] == \
        Artifact.ORIENTATION_SESSION.schema


# --- and the gate that could not reach an undeclared artifact ------------------


def test_the_digest_rule_now_reaches_the_markov_blanket():
    """#381 globbed the schema directory so a container added tomorrow would
    be inside its rule the day it was added. This artifact shipped a
    ``data_hash`` past it for as long as it existed — not by breaking the
    rule but by being outside every denominator, which is the cost #387 is
    about and the reason it is worth more than five files.
    """
    doc = json.loads(
        (SCHEMAS / Artifact.MARKOV_BLANKET.schema).read_text("utf-8"))
    pairs = _pairings(doc)
    assert [(hash_key, columns_key) for _, _, hash_key, columns_key in pairs] \
        == [("data_hash", "data_columns")]
