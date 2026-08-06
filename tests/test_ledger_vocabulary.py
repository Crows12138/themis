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
        ledger.stamp("flat_channel", ledger.Layer.IDENTIFICATION,
                     ledger.Provenance.LLM_PRIOR)
    with pytest.raises(ValueError, match="may not write layer"):
        ledger.stamp("theta_prior", ledger.Layer.IDENTIFICATION,
                     ledger.Provenance.LLM_PRIOR)


@pytest.mark.parametrize("bad", ["assumption", "", "not_a_layer_at_all"])
def test_stamp_refuses_a_value_no_vocabulary_holds(bad):
    with pytest.raises(ValueError, match="is not an assumption layer"):
        ledger.stamp("flat_channel", bad, ledger.Provenance.ESTIMATOR_DECLARED)


def test_an_unknown_producer_is_refused_rather_than_answered():
    """The empty pair would read as "this producer writes no layer", which
    is the one thing a caller asking cannot tell apart on its own."""
    with pytest.raises(KeyError, match="does not assemble ledger entries"):
        ledger.admissible("some_producer_that_does_not_exist")


# --- nothing in the tree writes outside the vocabulary -----------------------

def _ledger_entry_literals():
    """Every dict literal in the package shaped like a ledger entry.

    Found by SHAPE — carrying both ``layer`` and ``severity`` — and not by
    field name, because both names are taken twice in this envelope: a data
    gap has a ``severity`` graded ``blocking`` / ``important`` /
    ``informational``, and a gap's ``provenance`` is a list of references.
    A guard keyed on the name would fail on all of those and say nothing
    true about any of them.
    """
    for path in sorted((ROOT / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"layer", "severity"} <= keys:
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
