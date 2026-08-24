"""#417 — a column whose levels have no order, and the one place that hears it.

``scale`` could say ``binary`` / ``discrete`` / ``continuous``. Three marketing
channels coded 0/1/2 and a count of visits from 0 to 10 therefore declared
IDENTICALLY, and nominality is not recoverable from the column: the two are the
same bytes. So the missing member was not a convenience — it was the only place
the fact could have come from.

The member alone would have changed nothing, because the decision it feeds did
not exist anywhere. Eight estimators each wrote

    df[list(adjustment)].to_numpy(dtype=float)

which is not a conversion but a claim: every column is a quantity, so the
distance from level one to level three is twice the distance to level two.
Written as a dtype cast it never looked like a claim, which is why all eight
made it and none recorded making it. ``declared.design_terms`` is that decision,
named once; ``design_block`` and ``design_widths`` are its two readings.

The cost is measured here rather than asserted, on a frame built so that no
straight line through 0/1/2 can fit it: the ordered reading does not merely lose
precision, it returns the wrong SIGN.

What this file must be able to say NO to is the state the repository was in
before: a covariate with three levels entering as one term while nothing on the
disclosure surface could be told apart from the honest case. That case is kept
alive below (``discrete`` on the same frame) and is asserted to be both wrong
and DISCLOSED — a gate that only checked the good case would pass on a build
that had quietly stopped expanding anything.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import declared as _declared
from themis.estimation.contract import DataContractError, validate_data
from themis.estimation.declared import (
    SCALES, design_block, design_terms, design_widths,
)
from themis.estimation.sensitivity_ovb import (
    block_partial_r2, estimate_ovb_sensitivity, partial_r2,
)
from themis.language import spoken
from themis.output.assumption_glossary import classify_assumption


ORDERED_ROW = "multi_level_covariates_entered_as_ordered_numbers"
TRUE_ATE = 0.10


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _program(channel_declaration: dict) -> dict:
    """ch → t, ch → y, t → y, asking for the effect of t on y."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "t", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "ch", **channel_declaration},
            {"kind": "cause", "from": _atom("ch"), "to": _atom("t")},
            {"kind": "cause", "from": _atom("ch"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("t"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("t"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _non_monotone_frame(n: int = 30_000, seed: int = 7) -> pd.DataFrame:
    """Three channels, deliberately NON-monotone in both t and y.

    The middle code carries the HIGHEST outcome rate and the LOWEST treatment
    rate, so a single slope through 0/1/2 cannot absorb the confounding — which
    is what makes the ordered reading's error a sign error rather than a small
    one, and what makes the two declarations distinguishable by their answers.
    """
    rng = np.random.default_rng(seed)
    ch = rng.integers(0, 3, n)
    t = rng.random(n) < np.array([0.30, 0.20, 0.70])[ch]
    y = rng.random(n) < np.clip(
        np.array([0.20, 0.60, 0.25])[ch] + TRUE_ATE * t, 0.0, 1.0)
    return pd.DataFrame({"ch": ch, "t": t, "y": y})


def _estimate(declaration: dict, frame: pd.DataFrame) -> dict:
    envelope = themis.estimate(_program(declaration), frame, ci_bootstrap=0)
    return envelope["results"][0]


def _named_assumptions(result: dict) -> list[str]:
    ledger = (result.get("extensions") or {}).get("assumption_ledger") or {}
    return [str(e.get("id")) for e in ledger.get("assumptions") or []]


def _levels(*labels) -> pd.Series:
    return pd.Series(pd.Categorical(labels, categories=sorted(set(labels))))


# ====================================================== the vocabulary


def _schema(name: str) -> dict:
    return json.loads(
        (pathlib.Path(__file__).resolve().parents[1]
         / "themis" / "schemas" / name).read_text(encoding="utf-8"))


def _find(node, key):
    """The first value stored under ``key`` anywhere in a schema."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def test_the_scale_vocabulary_is_written_once():
    scale = _find(_schema("kernel_ast.schema.json"), "scale")
    assert tuple(scale["enum"]) == SCALES


def test_the_observed_side_has_no_such_member():
    """Nominality is a claim about the world, and no column can show it.

    ``observed_scale`` is what was READ off the frame, and three codes and a
    three-visit count read identically — which is the whole reason the declared
    side needed the member. A member on the observed side would be a reading
    nothing can perform.
    """
    schema = _schema("query_result.schema.json")
    observed = _find(schema, "observed_scale")
    assert "nominal" not in observed["enum"]
    declared_side = _find(schema, "declared_scale")
    assert "nominal" in declared_side["enum"]


# ====================================================== the one decision


def test_a_column_with_no_order_becomes_one_term_per_level():
    frame = pd.DataFrame({"ch": _levels("a", "b", "c", "a", "b", "c")})
    terms = design_terms(frame, ["ch"])
    assert [name for name, _ in terms] == ["ch=b", "ch=c"]
    assert design_block(frame, ["ch"]).shape == (6, 2)
    assert design_widths(frame, ["ch"]) == [2]


def test_a_quantity_stays_one_term():
    frame = pd.DataFrame({"dose": [0, 1, 2, 3, 4, 5]})
    assert [name for name, _ in design_terms(frame, ["dose"])] == ["dose"]
    assert design_widths(frame, ["dose"]) == [1]


def test_the_two_readings_of_a_column_cannot_disagree():
    """``design_widths`` and ``design_terms`` read the same fact twice.

    They have to: one is asked before the matrix exists (a caller computing
    where a coefficient sits), the other while building it. Two readings of one
    fact is the shape this whole change is about, so the equality is pinned
    rather than assumed.
    """
    frame = pd.DataFrame({
        "ch": _levels("a", "b", "c", "a", "b", "c"),
        "site": _levels("x", "y", "x", "y", "x", "y"),
        "dose": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5],
    })
    columns = ["ch", "site", "dose"]
    assert sum(design_widths(frame, columns)) == len(design_terms(frame, columns))
    assert design_block(frame, columns).shape[1] == sum(design_widths(frame, columns))


def test_a_level_absent_from_a_draw_still_gets_its_term():
    """Which is why the frame carries a categorical and not a set of values.

    A bootstrap draw that happens to miss a level would otherwise build a
    NARROWER design than the draw beside it, and the two would no longer be
    estimating the same thing. The declaration fixes the width; the sample does
    not get a vote.
    """
    full = pd.DataFrame({"ch": _levels("a", "b", "c", "a", "b", "c")})
    draw = full.iloc[[0, 1, 3, 4]]              # no "c" in these rows
    assert "c" not in set(draw["ch"])
    assert design_widths(draw, ["ch"]) == [2]
    assert design_block(draw, ["ch"]).shape == (4, 2)


def test_no_columns_is_a_block_with_no_columns():
    frame = pd.DataFrame({"a": [1, 2, 3]})
    assert design_block(frame, []).shape == (3, 0)
    assert design_terms(frame, []) == []


# ====================================================== what the reading is worth


def test_the_ordered_reading_gets_the_sign_wrong_and_the_declaration_fixes_it():
    frame = _non_monotone_frame()

    ordered = _estimate({"scale": "discrete", "domain": [0, 1, 2]}, frame)
    unordered = _estimate({"scale": "nominal", "domain": [0, 1, 2]}, frame)

    ordered_point = ordered["numeric_estimate"]["point"]
    unordered_point = unordered["numeric_estimate"]["point"]

    # Not "less precise" — the wrong side of zero, on 30k rows.
    assert ordered_point < 0.0 < TRUE_ATE
    assert abs(unordered_point - TRUE_ATE) < 0.02
    assert abs(ordered_point - TRUE_ATE) > 10 * abs(unordered_point - TRUE_ATE)


def test_the_declaration_is_what_removes_the_assumption():
    frame = _non_monotone_frame(n=4_000)
    ordered = _estimate({"scale": "discrete", "domain": [0, 1, 2]}, frame)
    unordered = _estimate({"scale": "nominal", "domain": [0, 1, 2]}, frame)

    assert ORDERED_ROW in _named_assumptions(ordered)
    assert ORDERED_ROW not in _named_assumptions(unordered)


def test_the_gate_would_fail_on_a_build_that_expanded_nothing():
    """The negative case, kept alive rather than described.

    A build that had quietly stopped expanding anything would still pass every
    assertion above that only looks at the nominal side — the two declarations
    would simply agree. So the ordered side is asserted to be BOTH wrong AND
    disclosed: the pre-fix state is a state this file can still recognise, and
    the two answers must not coincide.
    """
    frame = _non_monotone_frame(n=4_000)
    ordered = _estimate({"scale": "discrete", "domain": [0, 1, 2]}, frame)
    unordered = _estimate({"scale": "nominal", "domain": [0, 1, 2]}, frame)

    assert ORDERED_ROW in _named_assumptions(ordered)
    assert ordered["numeric_estimate"]["point"] != pytest.approx(
        unordered["numeric_estimate"]["point"], abs=0.05)


def test_the_assumption_names_the_declaration_that_removes_it():
    entry = classify_assumption(ORDERED_ROW)
    assert entry["layer"] == "functional_form"
    assert "nominal" in spoken(entry["claim"])


def test_a_two_level_column_needs_no_help():
    """``binary`` already says everything ``nominal`` would add.

    One indicator is saturated over two levels, so there is no ordering left to
    assume and the row must not appear. Which is why the defect was invisible
    on the common case for as long as it was.
    """
    rng = np.random.default_rng(3)
    n = 3_000
    ch = rng.integers(0, 2, n)
    t = rng.random(n) < np.array([0.3, 0.7])[ch]
    y = rng.random(n) < np.clip(np.array([0.2, 0.5])[ch] + TRUE_ATE * t, 0, 1)
    frame = pd.DataFrame({"ch": ch.astype(bool), "t": t, "y": y})
    result = _estimate({"domain": [True, False]}, frame)
    assert ORDERED_ROW not in _named_assumptions(result)


# ====================================================== the role it cannot serve


def test_a_column_with_no_order_cannot_be_read_as_a_number():
    frame = pd.DataFrame({
        "t": _levels("a", "b", "c") .repeat(4).reset_index(drop=True),
        "y": [True, False] * 6,
    })
    with pytest.raises(DataContractError) as raised:
        validate_data(frame, required_columns={"t", "y"},
                      quantity_columns=("t",))
    said = str(raised.value)
    assert "t" in said and "nominal" in said


def test_the_same_column_is_fine_where_nothing_reads_it_as_a_number():
    frame = pd.DataFrame({
        "ch": _levels("a", "b", "c").repeat(4).reset_index(drop=True),
        "y": [True, False] * 6,
    })
    contract = validate_data(frame, required_columns={"ch", "y"},
                            quantity_columns=("y",))
    assert isinstance(contract.data["ch"].dtype, pd.CategoricalDtype)


def test_a_nominal_treatment_is_refused_by_name_rather_than_by_traceback():
    """The failure this member introduced, and the reason it is caught early.

    Left alone, a channel name reaches ``float()`` four frames down and pandas
    says ``could not convert string to float: 'b'`` — true, and about neither
    the column nor the reason.
    """
    rng = np.random.default_rng(1)
    n = 900
    z = rng.integers(0, 2, n).astype(bool)
    arm = rng.choice(["a", "b", "c"], n)
    y = rng.random(n) < 0.3 + 0.2 * z
    frame = pd.DataFrame({"t": arm, "y": y, "z": z})

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "t",
             "scale": "nominal", "domain": ["a", "b", "c"]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("t")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("t"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("t"), "value": "b"},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    with pytest.raises(DataContractError) as raised:
        themis.estimate(program, frame, ci_bootstrap=0)
    assert "t" in str(raised.value)


# ====================================================== conform and the frame


def test_a_value_the_declaration_does_not_list_is_still_refused():
    program = _program({"scale": "nominal", "domain": ["a", "b"]})
    frame = pd.DataFrame({
        "ch": ["a", "b", "c"] * 4,
        "t": [True, False] * 6,
        "y": [True, False] * 6,
    })
    with pytest.raises(DataContractError) as raised:
        _declared.conform(program, frame)
    assert "c" in str(raised.value)


def test_conform_places_the_column_on_its_declared_levels():
    program = _program({"scale": "nominal", "domain": ["c", "a", "b"]})
    frame = pd.DataFrame({
        "ch": ["a", "b", "c"] * 4,
        "t": [True, False] * 6,
        "y": [True, False] * 6,
    })
    out = _declared.conform(program, frame)
    dtype = out["ch"].dtype
    assert isinstance(dtype, pd.CategoricalDtype)
    # The declared order is what fixes the reference level, and it is the
    # program's own order rather than a sorted one.
    assert list(dtype.categories) == ["c", "a", "b"]
    assert design_widths(out, ["ch"]) == [2]


def test_which_level_is_the_reference_changes_the_fingerprint():
    """Two runs that differ only there fitted different matrices.

    The hash exists to say "this answer stands on this data". A drop-first
    design is a choice of reference, and two designs with different references
    are not the same fit, so they must not share a fingerprint.
    """
    labels = ["a", "b", "c"] * 4
    first = pd.DataFrame({"ch": pd.Categorical(labels, categories=["a", "b", "c"])})
    second = pd.DataFrame({"ch": pd.Categorical(labels, categories=["c", "b", "a"])})
    hashes = {
        validate_data(f.assign(y=[True, False] * 6),
                      required_columns={"ch", "y"}).data_hash
        for f in (first, second)
    }
    assert len(hashes) == 2


# ====================================================== downstream readers


def test_the_extra_claim_is_unfalsifiable_so_it_reconciles_as_discrete():
    """A nominal declaration is a discrete one plus something data cannot see.

    So the reconciliation has exactly the discrete verdicts: a column that is
    genuinely continuous still disagrees with it, and one that is genuinely
    three levels still agrees.
    """
    from themis.estimation.dispatch import _reconcile_declared_observed

    agree, _ = _reconcile_declared_observed(
        "c", "nominal", None, "discrete", 3, None)
    disagree, _ = _reconcile_declared_observed(
        "c", "nominal", None, "continuous", 812, None)
    same_for_discrete, _ = _reconcile_declared_observed(
        "c", "discrete", None, "continuous", 812, None)
    assert agree == "ok"
    assert disagree == same_for_discrete != "ok"


def test_a_block_of_coefficients_has_a_partial_r_squared_too():
    """And the scalar form is its one-column case rather than a second formula.

    An OVB benchmark asks "how much does THIS covariate explain", which stopped
    being one coefficient the moment a covariate could be several.
    """
    for t_statistic, dof in [(0.5, 40), (2.0, 100), (7.5, 3_000)]:
        assert block_partial_r2(t_statistic ** 2, 1, dof) == pytest.approx(
            partial_r2(t_statistic, dof))
    assert block_partial_r2(4.0, 0, 100) == 0.0


def test_a_benchmark_reads_the_whole_covariate_and_not_its_first_column():
    """The positional read the expansion would otherwise have broken.

    ``2 + adjustment.index(cov)`` was a position among NAMES being used as a
    position among design columns; with one covariate widened, every benchmark
    after it pointed at a different variable.
    """
    rng = np.random.default_rng(11)
    n = 4_000
    ch = rng.integers(0, 3, n)
    other = rng.normal(size=n)
    d = rng.normal(size=n) + np.array([0.0, 1.5, -1.5])[ch] + 0.4 * other
    y = 0.3 * d + np.array([0.0, 2.0, -0.5])[ch] + 0.7 * other + rng.normal(size=n)
    frame = pd.DataFrame({
        "ch": pd.Categorical(ch, categories=[0, 1, 2]),
        "other": other, "d": d, "y": y,
    })
    sensitivity = estimate_ovb_sensitivity(
        frame, treatment="d", outcome="y", adjustment=("ch", "other"))
    by_name = {b.covariate: b for b in sensitivity.benchmarks}
    assert set(by_name) == {"ch", "other"}
    # ``ch`` genuinely drives both d and y here, so a benchmark that had read
    # only its first indicator — or the column after it — would understate it.
    assert by_name["ch"].r2dxj_x > by_name["other"].r2dxj_x
    assert by_name["ch"].r2yxj_dx > 0.0
