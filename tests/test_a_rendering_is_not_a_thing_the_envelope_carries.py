# -*- coding: utf-8 -*-
"""A gap says itself once, and the envelope does not say it again.

This file used to be about keeping two stores of one fact in step.
``result.explanation`` held the ⚠ lines — the caveats, rendered into a
string while the kernel ran — and the gap report held the gaps they were
rendered from, so a pass that changed one had not finished until it had
re-derived the other. It did not: a point estimate arriving withdrew
``answer_is_bounds_not_point_estimate`` from the gaps and left its line —
"the answer is a symbolic interval, not a point estimate; the renderer
must state this is bounds rather than a specific number" — on 246 of one
suite run's envelopes, every one of which had just computed a number.

That was fixed by deriving the view again wherever the source changed,
and the fix held. What it did not ask is why the view was stored at all.
A ⚠ line has no content of its own: over one suite run, 4569 of 4857 of
them were a gap's own statement copied verbatim, 45 more were an
estimator's wording of a gap it had just filed one line above, and the
remaining 246 were the stale ones. **A field with no statement of its own
is a rendering**, and a rendering stored on the envelope is one composed
before anyone knew who would read it — in whichever language the build
happened to default to. So the reader could not be asked (#395).

The subject here is therefore what is left: the gaps, and the fact that
nothing restates them. Two of the old file's tests moved across intact,
because withdrawing a contradicted gap is still a behaviour and not a
consequence of the deletion — what changed is that it is now checked on
the gap list alone, there being nowhere else for it to be wrong.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis import gaps as _gaps
from themis.types import (
    ASKS_FOR_SOMETHING,
    QUALIFIES_THE_ANSWER,
    GapKind,
)


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _effect_query(qid: str = "q") -> dict:
    return {
        "kind": "query", "id": qid, "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
        },
    }


def _identifiable_program() -> dict:
    """Z confounds X and Y and is observed, so the back door closes.

    Bounds are attached anyway while theta is missing, which is what puts
    the bounds caveat on the report; supplying data then answers the query
    for real and the caveat has to go.
    """
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            _effect_query(),
        ],
    }


def _unidentifiable_program() -> dict:
    """A latent common cause, so no point is honest however much data
    arrives — the caveat is still true and has to stay."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            _effect_query(),
        ],
    }


def _frame(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.4
    x = rng.random(n) < (0.3 + 0.4 * z)
    y = rng.random(n) < (0.2 + 0.3 * x + 0.3 * z)
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _gap_list(result: dict) -> list[dict]:
    return list(((result.get("data_gap_report") or {}).get("gaps") or []))


def _kinds(result: dict) -> set[str]:
    return {g.get("kind") for g in _gap_list(result)}


def _strings(node, path: str = ""):
    """Every string on an envelope, with the path it sits at."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _strings(value, f"{path}.[{i}]")
    elif isinstance(node, str):
        yield path, node


def _said_lines(result: dict) -> set[str]:
    """What this result's gaps say, as the sentences a surface would join.

    Rendered at the default, which is the whole point: if a second copy of
    one of these is anywhere on the envelope, it was composed here too,
    and in this language.
    """
    out: set[str] = set()
    for gap in _gap_list(result):
        for entry in gap.get("describes") or ():
            said = _gaps.describe(entry)
            if said:
                out.add(said)
    return out


# --------------------------------------------------------------- the table


def test_every_gap_kind_says_which_of_the_two_it_is():
    """The two rows partition the enum. The import-time check enforces it;
    this states it where someone adding a kind will read it."""
    assert QUALIFIES_THE_ANSWER | ASKS_FOR_SOMETHING == frozenset(GapKind)
    assert not (QUALIFIES_THE_ANSWER & ASKS_FOR_SOMETHING)


def test_what_an_estimator_found_is_a_caveat_like_any_other():
    """These six were a set of their own while the estimator wrote its own
    wording of them into the envelope. Who found a condition is a fact
    about when, and a reader is led with it either way."""
    assert {
        GapKind.WEAK_IV_INSTRUMENT,
        GapKind.OVERIDENTIFICATION_REJECTED,
        GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR,
        GapKind.PROPENSITY_OVERLAP_VIOLATION,
        GapKind.OUTCOME_MODEL_QUASI_SEPARATION,
        GapKind.DECLARED_TYPE_DATA_MISMATCH,
    } <= QUALIFIES_THE_ANSWER


# ------------------------------------------------- nothing restates a gap


@pytest.mark.parametrize(
    "make_program", [_identifiable_program, _unidentifiable_program],
    ids=["identifiable", "unidentifiable"],
)
def test_no_gap_of_this_result_is_restated_anywhere_on_it(make_program):
    """The gate the deletion leaves behind.

    A gap states itself in one place. Any second copy of that statement is
    a rendering the kernel composed, and a rendering the kernel composed is
    one made in a language nobody chose — which is the whole of what was
    wrong with the field this file used to be about.
    """
    program = make_program()
    for result in (themis.run(program)["results"][0],
                   themis.estimate(program, _frame())["results"][0]):
        said = _said_lines(result)
        assert said, "a fixture whose gaps say nothing proves nothing here"
        elsewhere = {
            (path, line.strip())
            for path, text in _strings(result)
            if not path.startswith("data_gap_report")
            for line in text.split("\n")
        }
        restated = [(p, ln) for p, ln in elsewhere
                    if ln in said or ln.lstrip("⚠ ").strip() in said]
        assert not restated, restated


def test_the_gate_rejects_the_field_this_file_used_to_be_about():
    """The counterexample, built the way the deleted pass built it.

    Without this the test above passes on a build that never had the
    defect and on one that has it again, since both look the same from
    inside a corpus that happens not to contain it.
    """
    result = themis.run(_identifiable_program())["results"][0]
    said = _said_lines(result)
    assert said
    result["explanation"] = "\n".join(f"⚠ {line}" for line in sorted(said))

    elsewhere = {
        line.strip()
        for path, text in _strings(result)
        if not path.startswith("data_gap_report")
        for line in text.split("\n")
    }
    assert any(ln.lstrip("⚠ ").strip() in said for ln in elsewhere)


# ------------------------------------------------------- the live behaviour


def test_a_point_estimate_withdraws_the_bounds_gap_it_contradicts():
    program = _identifiable_program()

    structural = themis.run(program)["results"][0]
    assert GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE.value in _kinds(
        structural), "fixture no longer produces the gap this is about"

    solved = themis.estimate(program, _frame())["results"][0]
    assert solved["status"] == "numerically_solved"
    assert solved["numeric_estimate"]["point"] is not None
    assert GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE.value not in _kinds(
        solved)


def test_the_gaps_a_number_does_not_contradict_stay():
    """The withdrawal is targeted. An answer that came out of data does
    not make the intervention well defined, or the DAG complete."""
    program = _identifiable_program()
    structural = themis.run(program)["results"][0]
    solved = themis.estimate(program, _frame())["results"][0]

    survived = _kinds(solved) & _kinds(structural)
    assert len(survived) >= 2, (
        "fixture no longer carries gaps that outlive the estimate"
    )
    assert survived < _kinds(structural)


def test_an_unidentifiable_query_keeps_its_bounds_gap():
    """No amount of data licenses a point here, so the gap is still true.
    The reconciliation reads the unidentifiable verdict; this holds it to
    leaving the bounds gap alone."""
    program = _unidentifiable_program()
    bounds = GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE.value
    assert bounds in _kinds(themis.run(program)["results"][0])

    df = _frame()
    solved = themis.estimate(program, df[["x", "y"]])["results"][0]
    assert bounds in _kinds(solved), (
        "the honest answer is still an interval; the gap may not be dropped"
    )
