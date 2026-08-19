"""The three closed vocabularies of one assumption-ledger line.

A ledger line says four things about an assumption and three of them are
drawn from closed sets: which part of the answer it holds up, how badly the
conclusion dies without it, and who put it on the list. Only the second had
a table anywhere. The other two were bare strings written by five producers,
which is why the report printed them to the reader untranslated, the browser
dropped them, and the verifier accepted 19 of 21 tampered layers and 8 of 8
tampered provenances — the empty string among them.

What is pinned here:

- the verifier's independently restated rows equal the producer's;
- the schema's three enums equal the three vocabularies;
- ``stamp`` refuses a pair no producer could have assembled, which is the
  check membership alone cannot make: every value is legitimate somewhere;
- no dict literal in the tree writes a ledger entry with a value outside
  the vocabulary, found by SHAPE (a literal carrying both ``layer`` and
  ``severity``) rather than by field name — ``severity`` and ``provenance``
  each name a second, disjoint vocabulary elsewhere in the envelope.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from themis import ledger
from themis.verifier import assumption_ledger_rules as rules

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json").read_text(
        encoding="utf-8"))

_ENTRY = (SCHEMA["properties"]["extensions"]["properties"]["assumption_ledger"]
          ["properties"]["assumptions"]["items"]["properties"])


# --- the vocabularies themselves ---------------------------------------------

@pytest.mark.parametrize("vocabulary,field", [
    (ledger.Layer, "layer"),
    (ledger.Severity, "severity"),
    (ledger.Provenance, "provenance"),
])
def test_the_contract_declares_the_whole_vocabulary(vocabulary, field):
    """The schema is what both surfaces read, so it is where a vocabulary
    that leaves the kernel has to be checkable."""
    assert set(_ENTRY[field]["enum"]) == {str(m) for m in vocabulary}


def test_the_channel_the_ledger_reads_declares_the_same_provenance():
    """``mechanism_audit`` is one of the channels the ledger turns into
    lines, and it carries a ``provenance`` of its own.

    It is the same vocabulary, so it has to be checked against the same
    source rather than against a second copy: the block sat outside the
    schema entirely while every one of its 348 instances in a suite run
    wrote ``default``, and a field that has only ever taken one value is
    exactly the one whose domain nobody notices is unstated.
    """
    audit = (SCHEMA["properties"]["extensions"]["properties"]
             ["mechanism_audit"]["properties"]["mechanisms"]["items"]
             ["properties"])
    assert set(audit["provenance"]["enum"]) == {
        str(m) for m in ledger.Provenance}


@pytest.mark.parametrize("vocabulary", [
    ledger.Layer, ledger.Severity, ledger.Provenance])
def test_every_value_says_something_of_its_own(vocabulary):
    """A member that cannot be told from its neighbours is a member that
    asserts nothing — which is what ``assumption`` was on a ledger of
    assumptions, for nineteen entries."""
    said = [m.zh for m in vocabulary]
    assert len(set(said)) == len(said), f"{vocabulary.__name__} repeats a word"
    for m in vocabulary:
        assert m.zh.strip(), f"{m.name} has no word for the reader"


def test_layer_says_what_the_reader_loses():
    """``breaks`` is the field the severity rule is derived from, so it has
    to be there for every layer and it has to differ."""
    said = [m.breaks for m in ledger.Layer]
    assert len(set(said)) == len(said)
    assert all(m.breaks.strip() for m in ledger.Layer)


def test_provenance_names_who_is_answerable():
    said = [m.answerable for m in ledger.Provenance]
    assert len(set(said)) == len(said)
    assert all(m.answerable.strip() for m in ledger.Provenance)


# --- the producer rows -------------------------------------------------------

def test_the_verifier_restates_the_same_rows():
    """The verifier must not import the producer's table — a ledger
    re-derived from the vocabulary its producer chose is not an independent
    audit — so it restates the rows and this pins them equal."""
    restated = {
        name: (frozenset(layers), frozenset(provs))
        for name, (layers, provs) in rules._ADMISSIBLE_PAIRS.items()
    }
    declared = {
        name: (frozenset(str(x) for x in layers),
               frozenset(str(x) for x in provs))
        for name, (layers, provs) in ledger.ADMISSIBLE.items()
    }
    assert restated == declared


def test_both_sides_know_every_route_that_declares_its_own_premises():
    """The third declaration channel, pinned to the SCHEMA and not to itself.

    An identification route lists what its own claim rests on, in ids the
    glossary translates. The producer folds those into the ledger and the
    verifier demands them there, and each spells the sites itself — so
    pinning the two lists to each other would only say they agree. Pinning
    both to the schema says a route added there and forgotten by either side
    is a failure, which is the shape this channel went missing in: the
    blocks listed their premises for years and no channel read them.
    """
    from themis.output import result_orchestrator

    from .test_no_part_of_a_block_is_silent import PATHS

    declared = {
        tuple(path.split("."))
        for path in PATHS
        if path.endswith(".assumptions")
        and not path.startswith("assumption_ledger.")
    }
    assert declared, "the schema declares no route premises at all"
    assert set(result_orchestrator.ROUTE_PREMISES) == declared
    assert set(rules._ROUTE_PREMISE_SITES) == declared


def test_every_value_is_writable_by_some_producer():
    """The import-time check, asked from the test's side as well: a value no
    row admits is one nothing can write, and it is indistinguishable in the
    source from a value nothing has needed yet."""
    layers = frozenset().union(*(row[0] for row in ledger.ADMISSIBLE.values()))
    provs = frozenset().union(*(row[1] for row in ledger.ADMISSIBLE.values()))
    assert set(ledger.Layer) == set(layers)
    assert set(ledger.Provenance) == set(provs)


def test_stamp_refuses_a_pair_no_producer_assembles():
    """Membership alone cannot catch this: ``identification`` is a real
    layer and ``llm_prior`` a real provenance, and an identification
    assumption relabelled as an LLM prior is a false statement about where
    it came from made entirely out of legitimate values."""
    with pytest.raises(ValueError, match="may not write provenance"):
        ledger.stamp("estimator_assumption", ledger.Layer.IDENTIFICATION,
                     ledger.Provenance.LLM_PRIOR)
    with pytest.raises(ValueError, match="may not write layer"):
        ledger.stamp("theta_prior", ledger.Layer.IDENTIFICATION,
                     ledger.Provenance.LLM_PRIOR)


@pytest.mark.parametrize("bad", ["assumption", "", "not_a_layer_at_all"])
def test_stamp_refuses_a_value_no_vocabulary_holds(bad):
    with pytest.raises(ValueError, match="is not an assumption layer"):
        ledger.stamp("estimator_assumption", bad, ledger.Provenance.INHERENT)


def test_an_unknown_producer_is_refused_rather_than_answered():
    """The empty pair would read as "this producer writes no layer", which
    is the one thing a caller asking cannot tell apart on its own."""
    with pytest.raises(KeyError, match="does not assemble ledger entries"):
        ledger.admissible("some_producer_that_does_not_exist")


# --- nothing in the tree writes outside the vocabulary -----------------------

def _ledger_entry_literals():
    """Every dict literal in the package shaped like a ledger entry.

    Found by SHAPE — carrying both ``layer`` and ``claim`` — and not by
    field name, because those names are taken more than once in this
    envelope: a data gap has a ``severity`` graded ``blocking`` /
    ``important`` / ``informational``, and a gap's ``provenance`` is a list
    of references. A guard keyed on either name alone would fail on all of
    those and say nothing true about any of them.

    The pair used to be ``layer`` and ``severity``, which stopped matching
    anything the day the producers stopped writing a severity — a guard
    whose shape has moved out from under it goes on passing.
    """
    for path in sorted((ROOT / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"layer", "claim"} <= keys:
                yield path, node


def test_every_written_ledger_entry_uses_the_vocabulary():
    found = 0
    for path, node in _ledger_entry_literals():
        found += 1
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(value, ast.Constant)):
                continue
            if not isinstance(value.value, str):
                continue
            vocabulary = {"layer": ledger.Layer, "severity": ledger.Severity,
                          "provenance": ledger.Provenance}.get(key.value)
            if vocabulary is None:
                continue
            assert value.value in {str(m) for m in vocabulary}, (
                f"{path.relative_to(ROOT)}:{value.lineno} writes "
                f"{key.value}={value.value!r}, which is not one of "
                f"{sorted(str(m) for m in vocabulary)}"
            )
    assert found > 30, (
        f"only {found} ledger-entry literals found; the shape this guard "
        f"keys on has moved and it is now checking nothing"
    )


# --- the severity is the layer's, said once ----------------------------------

_GRADES = frozenset(str(m) for m in ledger.Severity)

def _may_name_a_grade(path: pathlib.Path) -> bool:
    """``ledger`` declares the vocabulary; the verifier restates it on
    purpose and must not import it. Asked of the path RELATIVE to the repo,
    so that a checkout under a directory happening to be called ``verifier``
    does not quietly excuse the whole tree."""
    rel = path.relative_to(ROOT)
    return rel.name == "ledger.py" or "verifier" in rel.parts


def test_no_module_outside_the_two_names_a_grade():
    """A grade written anywhere else is a producer deciding one again.

    Not "does this value exist" — every grade exists — but "did anyone
    besides the vocabulary and its independent restatement have to name
    one". Two hundred sites named one before, and each was a chance for the
    two hundred and first to name a different one.
    """
    offenders = []
    for path in sorted((ROOT / "themis").rglob("*.py")):
        if _may_name_a_grade(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in _GRADES):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} {node.value!r}")
    assert not offenders, (
        "these write an assumption severity as a literal instead of asking "
        f"the layer for it: {offenders}"
    )


def test_the_verifier_restates_the_same_grades():
    """The other half of the independence pin: the verifier re-derives a
    severity from what a layer means, so its five rows have to be the five
    the producer stamps — and pinning them here is what makes a difference
    between them a test failure rather than a rejected honest answer."""
    assert rules._SEVERITY_OF_LAYER == {
        str(lay): str(lay.severity) for lay in ledger.Layer
    }
    # And it says why for each, in its own words rather than the producer's.
    assert set(rules._WHY_THAT_SEVERITY) == set(rules._SEVERITY_OF_LAYER)
    for lay in ledger.Layer:
        why = rules._WHY_THAT_SEVERITY[str(lay)]
        assert why.strip() and why != lay.breaks


def test_the_other_column_of_that_row_is_not_the_layers_either():
    """The argument that removed the severity column does not remove the one
    beside it, and this is the difference stated as a test rather than left
    to be re-argued: two assumptions of the same layer genuinely differ on
    whether the reader can go and check them. A layer that turned out to
    fix ``testable`` too would be a layer whose rows say one thing, and the
    honest response would be to move that column as well."""
    from themis.output import assumption_glossary as glossary

    rows = [entry for entry in glossary._EXACT.values()]
    rows += [entry for _, entry in glossary._PREFIX]
    by_layer: dict[str, set[bool]] = {}
    for layer, testable, _ in rows:
        by_layer.setdefault(str(layer), set()).add(bool(testable))
    assert by_layer["identification"] == {True, False}, (
        "every identification assumption now agrees on testable; if that is "
        "real, testable belongs on the layer and not on 146 rows"
    )


def test_stamp_hands_back_the_layers_grade_rather_than_taking_one():
    """A producer says which channel it is and which part of the answer the
    assumption holds up. It is given the grade; there is no argument it
    could pass that would change it."""
    for producer, (layers, provs) in ledger.ADMISSIBLE.items():
        for lay in layers:
            got_layer, got_severity, _ = ledger.stamp(
                producer, lay, sorted(provs)[0])
            assert got_layer is lay
            assert got_severity is lay.severity


def test_the_report_translates_all_three_fields():
    """No identifier the kernel writes reaches the reader as itself."""
    from themis.output import analysis_report

    entries = [
        {"claim": "c", "layer": str(lay), "severity": str(sev),
         "provenance": str(prov), "testable": False}
        for lay, sev, prov in zip(
            list(ledger.Layer) * 3, list(ledger.Severity) * 5,
            list(ledger.Provenance) * 3)
    ]
    out = analysis_report._assumption_ledger(
        {"assumptions": entries, "summary": "s"}, {})
    for vocabulary in (ledger.Layer, ledger.Severity, ledger.Provenance):
        for member in vocabulary:
            assert str(member) not in out, (
                f"the report prints {str(member)!r} to the reader"
            )
            assert member.zh in out, f"the report never says {member.zh}"


# --- who a monotonicity assumption belongs to ---------------------------------


def _causation_program(monotonic: bool) -> dict:
    def _cause(a, b):
        return {"kind": "cause", "from": {"predicate": a, "args": []},
                "to": {"predicate": b, "args": []}}
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *({"kind": "variable", "predicate": v, "domain": [True, False]}
              for v in ("x", "y", "z")),
            _cause("z", "x"), _cause("z", "y"), _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "causation",
                "cause": {"predicate": "x", "args": []},
                "effect": {"predicate": "y", "args": []},
                "monotonic": monotonic}},
        ],
    }


def _monotone_frame():
    """Rank-preserving monotone SCM with an observed confounder Z."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(11)
    n = 4000
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0, y1 = u < np.where(z, 0.5, 0.2), u < np.where(z, 0.8, 0.6)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    return pd.DataFrame({"x": x, "y": np.where(x, y1, y0), "z": z})


def _causation_ledger(monotonic: bool) -> dict:
    import themis

    r = themis.estimate(
        _causation_program(monotonic), _monotone_frame(), ci_bootstrap=0,
    )["results"][0]
    entries = ((r.get("extensions") or {}).get("assumption_ledger") or {}).get(
        "assumptions") or []
    return {e["id"]: e for e in entries if e.get("id")}


_MONO = "monotonicity_x_never_prevents_y_point_identification"


def test_the_monotonicity_that_bought_the_point_is_the_callers():
    """``inherent`` says the method cannot be run without it, and for this one
    that is false: drop it and the same method answers, in intervals. It is on
    the ledger because the caller asked for it, so the reader it names is the
    reader, and what they get back for withdrawing it is a wider answer rather
    than no answer."""
    by_id = _causation_ledger(monotonic=True)
    assert _MONO in by_id, "the monotonicity assumption is not on the ledger"
    assert by_id[_MONO]["provenance"] == str(ledger.Provenance.CALLER_ASSERTED)


def test_withdrawing_it_takes_the_line_away_rather_than_relabelling_it():
    """The other side of the same claim: if the line survived a query that
    never asserted it, calling it the caller's would be decoration."""
    assert _MONO not in _causation_ledger(monotonic=False)
