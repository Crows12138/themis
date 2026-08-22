"""Coding the frame left the programme naming levels the frame no longer has.

``declared.conform`` places a labelled column on the positions its declared
domain gives it, so the contract downstream sees numbers. The programme keeps
saying ``"remote"``. For a covariate that is fine — nothing in the programme
names its levels. For a treatment it is not: every arm test compares an int64
column against a string, matches nothing, and the run ends with no bounds, no
estimate, no refusal, and a report saying the data is too thin.

That last sentence is why this is worth ending the run over rather than
letting it degrade. An arm with no rows in it is a LEGAL state — it is what a
genuinely unobserved arm looks like — so no estimator can tell the two apart,
and the one thing this system exists to say correctly is which quantities the
data cannot supply.

The criterion is the AST's own shape rather than a list of query kinds: a
level is written next to the atom whose predicate names its column. The last
test here holds that shape against the schema, so a new query kind carrying a
level is covered by having been written in the same shape as every other, and
one written differently fails here rather than silently.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import declared
from themis.estimation.contract import DataContractError

U = "u"


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": U}]}


def _program(*, where_domain, where_value, with_covariate=False):
    statements = [
        {"kind": "variable", "predicate": "where", "domain": list(where_domain)},
        {"kind": "variable", "predicate": "productive", "domain": [True, False]},
        {"kind": "cause", "from": _atom("where"), "to": _atom("productive")},
        {"kind": "bidirected", "left": _atom("where"),
         "right": _atom("productive")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("where"), "value": where_value},
            "target": {"atom": _atom("productive"), "value": True},
            "given": []}},
    ]
    if with_covariate:
        statements.insert(2, {"kind": "variable", "predicate": "team",
                              "domain": ["sales", "support", "eng"]})
        statements.insert(5, {"kind": "cause", "from": _atom("team"),
                              "to": _atom("where")})
        statements.insert(6, {"kind": "cause", "from": _atom("team"),
                              "to": _atom("productive")})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": U}]},
        "statements": statements,
    }


def _frame(seed=11, n=2000, labelled=True, with_covariate=False):
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    remote = rng.random(n) < np.where(u, 0.65, 0.35)
    prod = rng.random(n) < np.clip(0.35 + 0.2 * remote + 0.25 * u, 0, 1)
    cols = {
        "where": (np.where(remote, "remote", "office") if labelled
                  else remote.astype(int)),
        "productive": prod,
    }
    if with_covariate:
        cols["team"] = np.array(["sales", "support", "eng"])[
            rng.integers(0, 3, n)]
    return pd.DataFrame(cols)


# ---------------------------------------------------------------------------
# Which levels the programme names, and which it does not
# ---------------------------------------------------------------------------


def test_an_intervention_value_is_a_level_the_programme_names():
    named = declared.levels_named(
        _program(where_domain=["office", "remote"], where_value="remote"))
    assert named["where"] == ["remote"]
    assert named["productive"] == [True]


def test_a_covariate_nobody_intervenes_on_names_no_level():
    named = declared.levels_named(_program(
        where_domain=["office", "remote"], where_value="remote",
        with_covariate=True))
    assert "team" not in named


def test_a_probability_statements_number_is_not_a_level():
    """The one ``value`` on the programme that is not one. It sits beside
    ``target`` and ``given`` with no atom of its own, and both of those ARE
    grounded atoms and are found on the way down."""
    program = _program(where_domain=[True, False], where_value=True)
    program["statements"].append({
        "kind": "probability",
        "target": {"atom": _atom("productive"), "value": True},
        "given": [{"atom": _atom("where"), "value": False}],
        "value": 0.42,
    })
    named = declared.levels_named(program)
    assert 0.42 not in named.get("productive", [])
    assert named["productive"].count(True) == 2   # the query's and the target's
    assert False in named["where"]                # the condition


def test_a_counterfactual_event_names_its_level_under_another_key():
    program = _program(where_domain=[True, False], where_value=True)
    program["statements"].append({
        "kind": "query", "id": "q2", "query": {
            "kind": "counterfactual_conjunction",
            "events": [{"variable": _atom("productive"),
                        "subscript": [{"atom": _atom("where"), "value": True}],
                        "value": False}]}})
    assert False in declared.levels_named(program)["productive"]


# ---------------------------------------------------------------------------
# The constructed no
# ---------------------------------------------------------------------------


def test_a_labelled_column_the_programme_names_a_level_of_ends_the_run():
    program = _program(where_domain=["office", "remote"], where_value="remote")
    with pytest.raises(DataContractError) as caught:
        themis.estimate(program, _frame(), ci_bootstrap=0)
    said = str(caught.value)
    assert "where" in said
    assert "remote" in said
    assert "[0, 1]" in said


def test_and_without_the_guard_it_would_have_read_as_too_little_data():
    """The failure this replaces, reproduced one layer down so the claim in
    the module docstring is a measurement rather than an assertion: coded
    frame, uncoded programme, and every arm empty."""
    program = _program(where_domain=["office", "remote"], where_value="remote")
    frame = _frame()
    coded = declared._codes(frame["where"], ("office", "remote"))
    assert coded.dtype == "int64"
    assert not (coded == "remote").any()


def test_a_labelled_covariate_still_goes_through():
    """The case #414 opened, and it is the whole of what coding can reach:
    nothing in the programme names a level of this column."""
    program = _program(where_domain=[True, False], where_value=True,
                       with_covariate=True)
    frame = _frame(labelled=False, with_covariate=True)
    frame["where"] = frame["where"].astype(bool)
    out = themis.estimate(program, frame, ci_bootstrap=0)
    assert out["results"][0].get("status") is not None
    conformed = declared.conform(program, frame)
    assert conformed["team"].tolist()[:3] == [
        ["sales", "support", "eng"].index(v) for v in frame["team"][:3]]


def test_the_same_question_coded_by_hand_is_answered():
    """What the refusal tells the reader to do, done — and it works."""
    program = _program(where_domain=[0, 1], where_value=1)
    out = themis.estimate(program, _frame(labelled=False), ci_bootstrap=0)
    rows = [b["method"] for b in (out["results"][0].get("bounds_results") or ())]
    assert "manski_natural" in rows


# ---------------------------------------------------------------------------
# The shape, against the schema
# ---------------------------------------------------------------------------


def _schema(name):
    return json.loads(
        (pathlib.Path(themis.__file__).parent / "schemas" / name)
        .read_text(encoding="utf-8"))


def test_every_schema_shape_that_carries_a_level_is_the_shape_this_reads():
    """Each ``$defs`` entry with a ``value`` property either sits beside a key
    naming a variable — and is a level — or does not, and is not.

    A new query kind is covered by having been written like the others. One
    written with the level somewhere else fails here, which is the whole
    point: the alternative is a hand-kept list of kinds, and the list is what
    drifts.
    """
    defs = _schema("kernel_ast.schema.json")["$defs"]
    carriers = {name: d for name, d in defs.items()
                if isinstance(d, dict) and "value" in (d.get("properties") or {})}
    assert set(carriers) == {
        "intervention", "observationStatement", "probabilityStatement",
        "counterfactualEvent",
    }
    levels, not_levels = set(), set()
    for name, d in carriers.items():
        props = d["properties"]
        (levels if any(k in props for k in declared._NAMES_A_VARIABLE)
         else not_levels).add(name)
    assert not_levels == {"probabilityStatement"}, (
        "a shape carrying a value with no variable beside it is not a level; "
        "the probability statement's is a number in [0, 1]")
    assert levels == {"intervention", "observationStatement",
                      "counterfactualEvent"}


def test_the_grounded_atom_the_other_shapes_nest_is_read_too():
    atoms = _schema("atom.schema.json")["$defs"]["groundedAtom"]["properties"]
    assert "value" in atoms
    assert any(k in atoms for k in declared._NAMES_A_VARIABLE)
