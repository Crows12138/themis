"""Themis could represent a lagged graph and estimate through one; it could
not read a time series and say which lagged links are in it.

This is that half — PCMCI (Runge et al. 2019) — and the reason it earns an
audit rather than a wrapper is the same reason the Markov-blanket screen did:
a learned graph is the one output where "re-run it and see" is not a check,
because re-running a search on the same data reproduces its bugs. What CAN be
checked is whether the returned object has the properties it claims, and both
stages here have one.

**Stage 1** claims its parent sets are a fixpoint: every parent dependent on
the target given the OTHER parents, every non-parent independent given ALL of
them. That is why condition selection is grow-shrink rather than the paper's
PC1 — PC1 drops a candidate as soon as SOME subset makes it independent, and
its output has no property a second pass can hold it to.

**Stage 2** claims each MCI test conditioned on the target's parents *and the
driver's own parents shifted back by the lag*. The second half is the paper's
contribution — it is what makes the p-value trustworthy under autocorrelation
— and it is the half that would vanish without trace if a producer dropped
it, leaving an ordinary partial correlation wearing an MCI label. So the
conditioning set is rebuilt from the recorded parents rather than read, and
the counterexample for it is an artifact doctored to be internally consistent
as the weaker thing.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.audits import Artifact, artifact_of
from themis.estimation.lagged_discovery import (
    LaggedDiscoveryError, discover_lagged_graph, lagged_discovery_to_dict,
    lagged_discovery_to_kernel_ast,
)
from themis.input.syntactic_validator import validate_ast
from themis.verifier import VerificationError

#: The system the data below is generated from, written down before it is
#: measured. Each series carries its own past, x drives y one step later, and
#: y drives z two steps later — so a recovered graph has something to be
#: right or wrong about rather than merely plausible.
TRUTH = {
    "x": {("x", 1)},
    "y": {("y", 1), ("x", 1)},
    "z": {("z", 1), ("y", 2)},
}

_MAX_LAG = 2


def _var(n: int, rng) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, y, z = (np.zeros(n) for _ in range(3))
    ex, ey, ez = rng.normal(size=(3, n))
    for t in range(2, n):
        x[t] = 0.5 * x[t - 1] + ex[t]
        y[t] = 0.6 * y[t - 1] + 0.7 * x[t - 1] + ey[t]
        z[t] = 0.4 * z[t - 1] + 0.6 * y[t - 2] + ez[t]
    return x[50:], y[50:], z[50:]


def _series(n: int = 1200, seed: int = 0) -> pd.DataFrame:
    x, y, z = _var(n, np.random.default_rng(seed))
    return pd.DataFrame({"t": np.arange(len(x)), "x": x, "y": y, "z": z})


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return _series()


@pytest.fixture(scope="module")
def learned(frame):
    return discover_lagged_graph(frame, time="t", max_lag=_MAX_LAG, alpha=0.01)


@pytest.fixture(scope="module")
def artifact(learned) -> dict:
    return lagged_discovery_to_dict(learned)


def _doctored(artifact: dict) -> dict:
    return copy.deepcopy(artifact)


def _refused(forged: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify_lagged_discovery(forged)
    return str(raised.value)


def _link(art: dict, driver: str, lag: int, target: str) -> dict:
    for entry in art["links"]:
        if (entry["driver"], entry["lag"], entry["target"]) == (
                driver, lag, target):
            return entry
    raise AssertionError(f"no link {driver}@t-{lag} -> {target}")


def _parents(art: dict, target: str) -> dict:
    for entry in art["parents"]:
        if entry["target"] == target:
            return entry
    raise AssertionError(f"no parent set for {target}")


def _reconcile_parent_tests(art: dict, target: str) -> None:
    """Rewrite one target's recorded tests to agree with its edited parent set.

    A search whose stopping rule is broken does not emit a self-contradictory
    artifact — it emits a coherent one whose parent set simply is not a
    fixpoint. A counterexample aimed at the fixpoint claim therefore has to be
    coherent too, or it gets caught earlier for a reason that says nothing
    about the claim.

    The rebuilt numbers come from the audit's own arithmetic, which is
    deliberate: it makes these two cases a test of the fixpoint claim rather
    than of the partial correlation. The forged-value cases below, whose
    numbers are constants no computation produced, are what hold the
    arithmetic.
    """
    from themis.verifier.lagged_discovery_rules import (
        _fisher_z_pvalue, _index, _partial_corr,
    )

    columns, depth = art["columns"], art["depth"]
    alpha, n = art["alpha"], art["sample_size"]
    position = {name: i for i, name in enumerate(art["variables"])}
    R = np.asarray(art["correlation"], dtype=float)
    kept = {_index(position[p["driver"]], p["lag"], depth)
            for p in _parents(art, target)["parents"]}
    t_idx = _index(position[target], 0, depth)

    for rec in art["parent_tests"]:
        if rec["target"] != target:
            continue
        candidate = _index(position[rec["driver"]], rec["lag"], depth)
        if candidate in kept:
            rec["role"] = "parent"
            cond = tuple(sorted(kept - {candidate}))
        else:
            rec["role"] = "not_a_parent"
            cond = tuple(sorted(kept))
        rec["conditioning_set"] = sorted(columns[x] for x in cond)
        rec["partial_correlation"] = _partial_corr(R, t_idx, candidate, cond)
        rec["p_value"] = _fisher_z_pvalue(R, t_idx, candidate, cond, n)
        rec["passed"] = (rec["p_value"] <= alpha if rec["role"] == "parent"
                         else rec["p_value"] > alpha)


# --- the graph it learns is the graph that was written down -------------------

def test_a_written_down_var_comes_back(learned):
    """The denominator, and the only oracle a discovery algorithm has: the
    data was generated from a structure, so the structure is what recovery
    means. An algorithm that returned everything, or nothing, would pass every
    counterexample below and be useless."""
    found = {target: {(d, lag) for d, lag in ps}
             for target, ps in learned.parents}
    assert found == TRUTH

    detected = {(link["driver"], link["lag"], link["target"])
                for link in learned.links if link["detected"]}
    expected = {(d, lag, t) for t, ps in TRUTH.items() for d, lag in ps}
    assert detected == expected


def test_the_artifact_verifies(artifact):
    """The second denominator. A rule that rejected everything would refuse
    every doctored envelope below and mean nothing by it."""
    themis.verify_lagged_discovery(artifact)


def test_every_candidate_is_recorded_whether_or_not_it_was_found(artifact):
    """A list of only the detected links cannot be checked for having dropped
    one, which is why the non-detected tests travel too."""
    candidates = len(TRUTH) * len(TRUTH) * _MAX_LAG
    assert len(artifact["links"]) == candidates
    assert len(artifact["parent_tests"]) == candidates
    assert sum(1 for link in artifact["links"] if link["detected"]) == sum(
        len(ps) for ps in TRUTH.values())


def test_an_mci_test_conditions_on_the_drivers_own_past(artifact):
    """What separates MCI from an ordinary partial correlation.

    Testing ``y@t-2 -> z`` conditions on z's other parent AND on y's own
    parents moved back two steps — ``x@t-3`` and ``y@t-3``. Without that
    second half the test would be reading z's autocorrelation through y and
    the p-value beside it would not be the p-value it claims.
    """
    link = _link(artifact, "y", 2, "z")
    assert set(link["conditioning_set"]) == {"z@t-1", "x@t-3", "y@t-3"}
    assert link["detected"]


def test_the_design_reaches_twice_the_deepest_candidate(artifact):
    """Why the design is deeper than the links it looks for: a parent at τ'
    behind a driver at τ sits at τ + τ', and a conditioning variable the
    design does not hold is a test that was not the test."""
    assert artifact["depth"] == 2 * artifact["max_lag"]
    assert artifact["columns"][:4] == ["x@t", "x@t-1", "x@t-2", "x@t-3"]


# --- the alignment, which is where a panel goes wrong quietly -----------------

def test_a_lag_never_crosses_from_one_unit_into_another():
    """The seam. Two subjects concatenated into one frame have a boundary
    where the last rows of one sit above the first rows of the other, and
    lagging across it manufactures a link out of two unrelated series.

    Measured against the same data read without the unit column, because "it
    is handled" and "it happens not to matter here" look identical from one
    run: the difference is exactly the rows at the seam.
    """
    rng = np.random.default_rng(3)
    frames, start = [], 0
    for who in ("a", "b"):
        x, y, z = _var(500, rng)
        frames.append(pd.DataFrame({
            "who": who, "t": np.arange(len(x)) + start,
            "x": x, "y": y, "z": z}))
        start += len(x)  # the two subjects' clocks run on: nothing about the
        # times themselves says where one ends and the other begins
    panel = pd.concat(frames, ignore_index=True)

    with_unit = discover_lagged_graph(
        panel, time="t", unit="who", max_lag=_MAX_LAG)
    without = discover_lagged_graph(panel, time="t", max_lag=_MAX_LAG)
    assert without.sample_size - with_unit.sample_size == with_unit.depth


def test_a_panel_whose_units_share_a_clock_is_refused_outright():
    """The other shape of the same mistake, and it cannot be silent: when
    every subject's time restarts at zero, forgetting the unit column makes
    two rows claim the same step, which is not an alignment at all."""
    rng = np.random.default_rng(4)
    frames = []
    for who in ("a", "b"):
        x, y, z = _var(400, rng)
        frames.append(pd.DataFrame({
            "who": who, "t": np.arange(len(x)), "x": x, "y": y, "z": z}))
    panel = pd.concat(frames, ignore_index=True)

    discover_lagged_graph(panel, time="t", unit="who", max_lag=_MAX_LAG)
    with pytest.raises(LaggedDiscoveryError, match="one observation"):
        discover_lagged_graph(panel, time="t", max_lag=_MAX_LAG)


def test_a_hole_in_the_series_is_not_lagged_across(frame):
    """Lags are taken by the VALUE of the time column, so a missing step
    drops the rows that would have straddled it instead of treating the row
    before the hole as the previous step."""
    whole = discover_lagged_graph(frame, time="t", max_lag=_MAX_LAG)
    punched = frame[frame["t"] != 600]
    holed = discover_lagged_graph(punched, time="t", max_lag=_MAX_LAG)
    assert whole.sample_size - holed.sample_size == whole.depth + 1


# --- what the producer will not do -------------------------------------------

def test_a_time_column_that_is_not_a_step_index_is_refused(frame):
    """A lag is a number of steps and only the caller knows what one step is,
    so a timestamp is converted upstream rather than guessed at here."""
    dated = frame.assign(t=frame["t"] * 0.5)
    with pytest.raises(LaggedDiscoveryError, match="integer-valued"):
        discover_lagged_graph(dated, time="t", max_lag=_MAX_LAG)


def test_a_discrete_series_is_refused(frame):
    """The correlation matrix is a complete sufficient statistic for Fisher-Z
    and for nothing else, so a discrete series would produce an artifact whose
    tests cannot be redone — which is the one thing worse than no answer."""
    coded = frame.assign(x=(frame["x"] > 0).astype(int))
    with pytest.raises(LaggedDiscoveryError, match="not continuous"):
        discover_lagged_graph(coded, time="t", max_lag=_MAX_LAG)


def test_a_design_too_wide_to_record_is_refused(frame):
    """The boundary of "record the statistic": past some width the matrix
    stops being a thing that can travel with the answer, and an audit trail
    that cannot ship is one the reader has to take on faith."""
    wide = frame.copy()
    rng = np.random.default_rng(5)
    for i in range(20):
        wide[f"noise{i}"] = rng.normal(size=len(wide))
    with pytest.raises(LaggedDiscoveryError, match="travel with the answer"):
        discover_lagged_graph(wide, time="t", max_lag=4)


def test_too_short_a_series_is_refused(frame):
    """Degrees of freedom are the sample minus the conditioning set, and a
    test with none left is not inconclusive — it is not a test."""
    with pytest.raises(LaggedDiscoveryError, match="every lag"):
        discover_lagged_graph(frame.head(20), time="t", max_lag=_MAX_LAG)


def test_one_series_is_refused(frame):
    """A lagged graph over a single series is an autocorrelation."""
    with pytest.raises(LaggedDiscoveryError, match="at least two series"):
        discover_lagged_graph(frame, time="t", columns=("x",),
                              max_lag=_MAX_LAG)


# --- what the audit says no to ------------------------------------------------
#
# One doctored artifact per rule, each edited the way the defect it names
# would arrive, and each asserted to be refused NAMING ITS OWN CASE.

def test_an_mci_test_stripped_back_to_a_plain_partial_correlation_is_refused(
        artifact):
    """The sharpest case, and the reason the conditioning set is rebuilt
    rather than read.

    A producer that dropped the driver's own parents would leave an artifact
    that is internally consistent — the recorded r and p are the ones that
    smaller set really gives — and every field would still look like an MCI
    result. Nothing about the numbers is wrong; what is wrong is which test
    they are of, and only rebuilding the set from the recorded parents can
    see it.
    """
    from themis.verifier.lagged_discovery_rules import (
        _fisher_z_pvalue, _partial_corr,
    )

    forged = _doctored(artifact)
    R = np.asarray(forged["correlation"], dtype=float)
    n = forged["sample_size"]
    depth = forged["depth"]
    columns = forged["columns"]
    index = {name: i for i, name in enumerate(columns)}

    link = _link(forged, "y", 2, "z")
    weaker = sorted(c for c in link["conditioning_set"] if c == "z@t-1")
    cond = tuple(sorted(index[c] for c in weaker))
    i, j = index["z@t"], index["y@t-2"]
    link["conditioning_set"] = weaker
    link["partial_correlation"] = round(_partial_corr(R, i, j, cond), 12)
    link["p_value"] = _fisher_z_pvalue(R, i, j, cond, n)
    link["detected"] = link["p_value"] <= forged["alpha"]

    assert "conditioning set" in _refused(forged)


def test_a_forged_p_value_on_a_link_is_refused(artifact):
    forged = _doctored(artifact)
    _link(forged, "x", 1, "y")["p_value"] = 0.9
    assert "p-value" in _refused(forged)


def test_a_forged_partial_correlation_is_refused(artifact):
    forged = _doctored(artifact)
    _link(forged, "x", 1, "y")["partial_correlation"] = 0.001
    assert "partial correlation" in _refused(forged)


def test_a_link_flipped_from_found_to_not_is_refused(artifact):
    """The verdict is a comparison against alpha, so it is recomputed rather
    than believed — a producer that reported a link and then dropped it from
    the graph would be telling the reader two things."""
    forged = _doctored(artifact)
    link = _link(forged, "y", 2, "z")
    link["detected"] = not link["detected"]
    assert "detected" in _refused(forged)


def test_a_dropped_link_is_refused(artifact):
    """Coverage. A list short by one entry is how a link stops being reported
    without anything having said so."""
    forged = _doctored(artifact)
    forged["links"] = [
        link for link in forged["links"]
        if (link["driver"], link["lag"], link["target"]) != ("y", 2, "z")
    ]
    assert "one MCI test per candidate" in _refused(forged)


def test_a_parent_set_with_something_added_is_refused(artifact):
    """Nothing addable — the half a search that stops too late gets wrong. An
    added parent is not dependent on the target given the others, and the
    artifact says so about itself once it is made coherent."""
    forged = _doctored(artifact)
    _parents(forged, "z")["parents"].append({"driver": "x", "lag": 2})
    _reconcile_parent_tests(forged, "z")
    assert "not a fixpoint" in _refused(forged)


def test_a_parent_set_with_something_removed_is_refused(artifact):
    """Nothing removable — the half a search that stops too early gets wrong.
    The dropped one is now a non-parent that is still dependent on the target
    given everything left, which is exactly what it means to have missed it."""
    forged = _doctored(artifact)
    block = _parents(forged, "y")
    block["parents"] = [p for p in block["parents"] if p["driver"] != "x"]
    _reconcile_parent_tests(forged, "y")
    assert "not a fixpoint" in _refused(forged)


def test_a_parent_at_a_lag_nobody_looked_for_is_refused(artifact):
    """A parent deeper than max_lag names a link this run never tested, so an
    artifact carrying one is describing a search that did not happen."""
    forged = _doctored(artifact)
    _parents(forged, "z")["parents"].append({"driver": "x", "lag": 9})
    assert "never looked for" in _refused(forged)


def test_a_reordered_design_is_refused(artifact):
    """Every index in every test is read through the layout, so a design in a
    different order is one where each recorded test is about a different pair
    of variables than it says."""
    forged = _doctored(artifact)
    forged["columns"] = list(reversed(forged["columns"]))
    assert "columns are not the design" in _refused(forged)


def test_a_statistic_that_is_not_a_correlation_matrix_is_refused(artifact):
    """The one thing taken on trust is the matrix, so its own shape is
    checked — a matrix no data could have produced cannot be the record of
    any run."""
    forged = _doctored(artifact)
    forged["correlation"][0][1] = 0.9
    assert "symmetric" in _refused(forged)


def test_a_foreign_artifact_is_refused(artifact):
    """"This audit is not about your result" and "your result failed its
    audit" must not be the same event, so the auditor names the kind it is
    for."""
    with pytest.raises(VerificationError, match="not a lagged_discovery"):
        themis.verify_lagged_discovery({"kind": "markov_blanket"})


# --- what a reader and an agent get -------------------------------------------

def test_the_artifact_routes_to_exactly_this_audit(artifact):
    """A caller should never have to tell "not yours" from "failed" by hand,
    which is what the audit table is for."""
    assert artifact_of(artifact) is Artifact.LAGGED_DISCOVERY
    rows = themis.audit(None, artifact)
    assert [row["audit"] for row in rows] == ["verify_lagged_discovery"]
    assert [row["ok"] for row in rows] == [True]


def test_the_suggestion_is_a_program_with_time_indexed_edges(learned):
    """The point of learning a lagged graph inside Themis rather than beside
    it: the edges land in the representation the rest of the kernel already
    reads, so identification and the longitudinal estimators can take them."""
    ast = lagged_discovery_to_kernel_ast(learned)
    validate_ast(ast)
    edges = {
        (s["from"]["predicate"], -s["from"]["time_index"]["value"],
         s["to"]["predicate"])
        for s in ast["statements"] if s["kind"] == "cause"
    }
    assert edges == {(d, lag, t) for t, ps in TRUTH.items() for d, lag in ps}
    for statement in ast["statements"]:
        if statement["kind"] == "cause":
            assert statement["to"]["time_index"] == {
                "kind": "relative", "value": 0}
            assert statement["annotations"]["source"] == "discovery:pcmci_gs"
