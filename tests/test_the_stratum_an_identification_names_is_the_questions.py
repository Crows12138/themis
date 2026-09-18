"""The stratum an identification names is the question's.

``extensions.identification`` is the one sentence a reader gets about where
a number came from, and every field of it is re-derived from the graph --
the criterion the pattern names, the adjustment set it needs, the mediators
it goes through. One field cannot be: what a question conditions on is the
question's, not the diagram's. The verifier's own docstring said so and
stopped there, so the field was free. Measured before this file: on an
honest conditional back-door answer, writing another variable, an extra
one, the treatment, the outcome, an empty list, or removing the field
altogether were each taken by both doors, and the leaf was declared
unwitnessed on all eighteen corpus rows that carry it.

What this file holds:

- a block that names a conditioning set names the question's, whether the
  question spells its conditions at a value (an effect question) or as
  variables (an identify question)
- where a reader is shown an identification and the question conditions,
  the sentence names the stratum: a conditional answer whose identification
  is silent describes the question about everybody
- a question that conditions on nothing is named nothing, and a block that
  names a stratum where none was asked is refused as surely as one naming
  the wrong stratum
- the joint block, which carried the only reading of this fact there was,
  reads it through the same one, and is asked the same silence: a joint
  answer's identification IS that block, with no scalar one beside it

WHAT THIS FILE DOES NOT CLAIM. Whether an answer to a conditional question
is owed an identification block AT ALL is not held here or anywhere: the
premise of the second half is a surface a reader is shown, so an answer
that carries no identification is not asked about its stratum. Nor are the
VALUES beside those variables this block's to show --
``numeric_estimate.given`` carries them and ``frame_rules`` holds them,
which is the other half of the same fact one layer down. ``iv_
identification`` is not asked either: it appears only beside the scalar
surface, which is asked.
"""
from __future__ import annotations

import copy
import itertools

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": []}


_ORDER = ["c", "z", "x", "y"]
_PARENTS = {"c": [], "z": [], "x": ["c", "z"], "y": ["x", "c", "z"]}


def _table(parents: list[str], values: list[float]) -> dict:
    keys = list(itertools.product((True, False), repeat=len(parents)))
    assert len(keys) == len(values), (len(keys), len(values))
    return dict(zip(keys, values))


_CPT = {
    "c": _table([], [0.5]),
    "z": _table([], [0.4]),
    "x": _table(["c", "z"], [0.8, 0.6, 0.35, 0.2]),
    "y": _table(["x", "c", "z"], [0.90, 0.85, 0.35, 0.30,
                                  0.20, 0.15, 0.25, 0.20]),
}


def _frame(rows: int = 3000, seed: int = 6960) -> pd.DataFrame:
    rs = np.random.default_rng(seed)
    cols: dict[str, np.ndarray] = {}
    for name in _ORDER:
        parents = _PARENTS[name]
        if parents:
            probs = np.array([_CPT[name][tuple(bool(b) for b in row)]
                              for row in zip(*[cols[p] for p in parents])])
        else:
            probs = np.full(rows, _CPT[name][()])
        cols[name] = rs.random(rows) < probs
    return pd.DataFrame(cols)


def _program(given: dict, kind: str = "effect") -> dict:
    """The model, asked as an effect question or as an identify one.

    The two spell a condition differently -- at a value, and as a bare
    variable -- which is the difference the rule reads across.
    """
    statements: list[dict] = [
        {"kind": "variable", "predicate": name, "domain": [True, False]}
        for name in _ORDER]
    statements += [{"kind": "cause", "from": _atom(parent), "to": _atom(name)}
                   for name in _ORDER for parent in _PARENTS[name]]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": kind,
        "intervention": {"atom": _atom("x"), "value": True},
        "target": ({"atom": _atom("y"), "value": True} if kind == "effect"
                   else _atom("y")),
        "given": [({"atom": _atom(name), "value": value} if kind == "effect"
                   else _atom(name)) for name, value in given.items()],
    }})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


def _answer(given: dict, kind: str = "effect") -> dict:
    out = themis.estimate(_program(given, kind), _frame(), random_state=7,
                          ci_bootstrap=0)
    return out["results"][0]


def _identification(result: dict) -> dict:
    return (result.get("extensions") or {})["identification"]


def _both_doors(program: dict, result: dict) -> None:
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(result))
    themis.verify(copy.deepcopy(program), copy.deepcopy(result))


def test_an_identification_names_the_stratum_the_question_asks() -> None:
    """The honest answer carries the question's own conditioning set."""
    result = _answer({"c": True})
    assert _identification(result)["conditioned_on"] == ["c()"]
    _both_doors(_program({"c": True}), result)


@pytest.mark.parametrize("named,why", [
    (["z()"], "another variable"),
    (["c()", "z()"], "the question's and one more"),
    ([], "nothing, where one was asked"),
    (["x()"], "the treatment"),
    (["y()"], "the outcome"),
])
def test_an_identification_naming_another_stratum_is_refused(
        named: list, why: str) -> None:
    """Every spelling of the wrong stratum, in the producer's own spelling.

    The spelling matters: a forgery written ``c(me)`` is stopped by the
    node lookup and never reaches the question, so these use the labels the
    producer writes and what refuses them is the comparison.
    """
    result = _answer({"c": True})
    _identification(result)["conditioned_on"] = named
    with pytest.raises(VerificationError, match="conditioned_on"):
        _both_doors(_program({"c": True}), result)


def test_an_identification_naming_a_stranger_is_refused() -> None:
    """A name the graph does not have is not a stratum anything can check."""
    result = _answer({"c": True})
    _identification(result)["conditioned_on"] = ["nobody()"]
    with pytest.raises(VerificationError, match="not a node in the graph"):
        _both_doors(_program({"c": True}), result)


def test_a_conditional_answer_whose_identification_is_silent_is_refused(
) -> None:
    """Silence here reads as the answer about everybody, which it is not."""
    result = _answer({"c": True})
    _identification(result).pop("conditioned_on")
    with pytest.raises(VerificationError, match="names no conditioning set"):
        _both_doors(_program({"c": True}), result)


def test_a_question_conditioning_on_nothing_names_nothing() -> None:
    """The silence a question with no stratum is owed, and is held to."""
    result = _answer({})
    assert "conditioned_on" not in _identification(result)
    _both_doors(_program({}), result)


def test_a_stratum_named_where_none_was_asked_is_refused() -> None:
    """The same rule, read the other way: a conditioning set nobody asked
    for describes a narrower question than the one answered."""
    result = _answer({})
    _identification(result)["conditioned_on"] = ["c()"]
    with pytest.raises(VerificationError, match="conditioned_on"):
        _both_doors(_program({}), result)


def test_an_identify_question_spells_its_condition_as_a_variable() -> None:
    """An identify query conditions on variables, not on values, and the
    same rule reads it: the block names those variables or it is refused."""
    result = _answer({"c": True}, kind="identify")
    assert _identification(result)["conditioned_on"] == ["c()"]
    _both_doors(_program({"c": True}, kind="identify"), result)

    forged = copy.deepcopy(result)
    _identification(forged)["conditioned_on"] = ["z()"]
    with pytest.raises(VerificationError, match="conditioned_on"):
        _both_doors(_program({"c": True}, kind="identify"), forged)


# --- the joint block, which is the whole of a joint answer's sentence ------
#
# Two treatments with a common cause and a covariate ``w`` the question
# conditions on. A joint answer carries ``joint_identification`` and no
# scalar surface, so both halves have to be asked of it or a joint
# conditional answer says nothing about its stratum and nothing minds.

_JOINT_ORDER = ["c", "w", "a", "b", "y"]
_JOINT_PARENTS = {"c": [], "w": [], "a": ["c"], "b": ["c"],
                  "y": ["a", "b", "c"]}
_JOINT_CPT = {
    "c": _table([], [0.5]),
    "w": _table([], [0.5]),
    "a": _table(["c"], [0.75, 0.3]),
    "b": _table(["c"], [0.7, 0.35]),
    "y": _table(["a", "b", "c"], [0.95, 0.6, 0.8, 0.45,
                                  0.5, 0.3, 0.35, 0.15]),
}


def _joint_frame(rows: int = 3000, seed: int = 6964) -> pd.DataFrame:
    rs = np.random.default_rng(seed)
    cols: dict[str, np.ndarray] = {}
    for name in _JOINT_ORDER:
        parents = _JOINT_PARENTS[name]
        if parents:
            probs = np.array([_JOINT_CPT[name][tuple(bool(b) for b in row)]
                              for row in zip(*[cols[p] for p in parents])])
        else:
            probs = np.full(rows, _JOINT_CPT[name][()])
        cols[name] = rs.random(rows) < probs
    return pd.DataFrame(cols)


def _joint_program(given: dict) -> dict:
    statements: list[dict] = [
        {"kind": "variable", "predicate": name, "domain": [True, False]}
        for name in _JOINT_ORDER]
    statements += [{"kind": "cause", "from": _atom(parent), "to": _atom(name)}
                   for name in _JOINT_ORDER
                   for parent in _JOINT_PARENTS[name]]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("a"), "value": True},
        "extra_interventions": [{"atom": _atom("b"), "value": True}],
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom(name), "value": value}
                  for name, value in given.items()],
    }})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


def _joint_answer(given: dict) -> dict:
    out = themis.estimate(_joint_program(given), _joint_frame(),
                          random_state=7, ci_bootstrap=0)
    return out["results"][0]


def test_a_joint_answer_names_the_stratum_in_its_own_block() -> None:
    """The joint answer's identification is this block and only this block."""
    result = _joint_answer({"w": True})
    blocks = result.get("extensions") or {}
    assert "identification" not in blocks
    assert blocks["joint_identification"]["conditioned_on"] == ["w()"]
    _both_doors(_joint_program({"w": True}), result)


def test_a_joint_block_naming_another_stratum_is_refused() -> None:
    """The reading the two blocks share, exercised on the other one."""
    result = _joint_answer({"w": True})
    result["extensions"]["joint_identification"]["conditioned_on"] = ["c()"]
    with pytest.raises(VerificationError, match="conditioned_on"):
        _both_doors(_joint_program({"w": True}), result)


def test_a_joint_answer_silent_about_its_stratum_is_refused() -> None:
    """Silence in the only sentence there is."""
    result = _joint_answer({"w": True})
    result["extensions"]["joint_identification"].pop("conditioned_on")
    with pytest.raises(VerificationError, match="names no conditioning set"):
        _both_doors(_joint_program({"w": True}), result)
