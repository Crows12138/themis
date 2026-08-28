"""Folding a proxy is a decision, so it is declared, recorded, and re-run.

Miao's formula (5) inverts a k×k channel, so a proxy observed at more than k
levels has to be recoded before the channel exists. The recoding is sound —
a conditional independence survives any function of the variable it holds
for, so a grouped proxy still satisfies the model-(f) criteria, and in the
population every grouping whose folded channel keeps full rank identifies the
same effect. In a finite sample they do not: a different grouping is a
different matrix and a different number.

That is the whole shape of this cut. Nothing observed says two levels of a
proxy are the same state of a variable nobody measured, so the estimator will
not pick a grouping; it refuses, and until the query had a
``proxy_coarsening`` the refusal had nothing to name. Once declared, the
grouping is the caller's — ``Provenance.CALLER_CHOSE``, which is not
``CALLER_ASSERTED``, because withdrawing it leaves no answer rather than a
wider one — and the verifier re-runs the fold from the per-level counts
rather than reading a folded table somebody already decided about.

The sharpest gate here is the last kind: an envelope whose counts are
untouched and whose GROUPING has one level moved. Every arithmetic identity
still holds, the table is the same table, and only re-running the fold sees
it. That case is why the channel records the fold's inputs and not its
result.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError

_STEP = "numeric_proximal_estimate"

#: The id the estimate declares when a grouping is in force, and the one it
#: declares when there is none. They are alternatives rather than a pair: the
#: second states as a fact ("each proxy has exactly k levels") the thing a
#: coarsened run is not doing.
_CHOSE = ("latent_cardinality_k_correct_and_the_declared_coarsening_"
          "folds_each_proxy_to_k_levels")
_PLAIN = "latent_cardinality_k_correct_and_proxies_have_exactly_k_levels"


# --- the corpus ---------------------------------------------------------------

def _var(p, domain=None):
    return {"kind": "variable", "predicate": p,
            "domain": [True, False] if domain is None else domain}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _program(*, k=2, fine=False, coarsening=None, columns=("z", "w")) -> dict:
    """Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y, with U unobserved."""
    zcol, wcol = columns
    query = {
        "kind": "proximal_effect", "treatment": _atom("x"),
        "outcome": _atom("y"), "latent": _atom("u"),
        "treatment_proxy": _atom(zcol), "outcome_proxy": _atom(wcol),
        "channel": {"kind": "discrete_channel",
                    "latent_cardinality": k},
    }
    if coarsening is not None:
        query["channel"]["proxy_coarsening"] = coarsening
    levels = [0, 1, 2, 3] if fine else None
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x"), _var("y"), _var("u"),
            _var(zcol, levels), _var(wcol, levels),
            _cause("u", "x"), _cause("u", "y"), _cause("u", zcol),
            _cause("u", wcol), _cause(zcol, "x"), _cause(wcol, "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": query},
        ],
    }


def _sample(n: int = 4000, seed: int = 1) -> pd.DataFrame:
    """A latent-U SCM whose proxies are recorded twice over.

    ``zc`` / ``wc`` are the two-level proxies the model is about. ``z`` / ``w``
    are the SAME proxies recorded at four levels, where the extra bit is a
    coin flip carrying nothing about U — so grouping {0,1} and {2,3} recovers
    ``zc`` / ``wc`` exactly, and the estimate through that grouping has an
    answer to be equal to rather than merely a plausible value.
    """
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    zc = rng.random(n) < np.where(u, 0.80, 0.20)
    wc = rng.random(n) < np.where(u, 0.85, 0.25)
    x = rng.random(n) < np.where(u, np.where(zc, 0.80, 0.55),
                                 np.where(zc, 0.50, 0.20))
    y = rng.random(n) < (0.15 + 0.35 * x + 0.25 * u + 0.15 * wc)
    noise_z = rng.random(n) < 0.5
    noise_w = rng.random(n) < 0.5
    return pd.DataFrame({
        "x": x, "y": y,
        "zc": zc, "wc": wc,
        "z": (np.where(zc, 2, 0) + noise_z).astype(int),
        "w": (np.where(wc, 2, 0) + noise_w).astype(int),
    })


#: The grouping that undoes the extra bit — {0,1} is one state, {2,3} the
#: other, which is how ``_sample`` built the four-level columns.
_UNDOES_THE_NOISE = {"treatment_proxy": [[0, 1], [2, 3]],
                     "outcome_proxy": [[0, 1], [2, 3]]}


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return _sample()


@pytest.fixture(scope="module")
def coarsened(frame) -> dict:
    prog = _program(fine=True, coarsening=_UNDOES_THE_NOISE)
    return themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def uncoarsened(frame) -> dict:
    """The same data through the two-level columns, so nothing is folded."""
    prog = _program(columns=("zc", "wc"))
    return themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]


def _step(result: dict) -> dict:
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step
    raise AssertionError(f"no {_STEP} step in this derivation")


def _channel(step: dict) -> dict:
    return step["inputs"]["measurement_channel"]["items"]


def _doctored(result: dict):
    forged = copy.deepcopy(result)
    step = _step(forged)
    return forged, step, _channel(step)


def _regroup(channel: dict, axis: str, groups: list[list[int]]) -> None:
    """Rewrite one axis's grouping in the serialized shape it travels in."""
    channel[f"{axis}_groups"]["items"] = [
        {"kind": "value_tuple", "items": list(g)} for g in groups]


def _refused(forged: dict, program: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program, forged)
    return str(raised.value)


def _gaps(result: dict, kind: str) -> list[dict]:
    report = result.get("data_gap_report") or {}
    return [g for g in report.get("gaps", []) if g["kind"] == kind]


# --- the fold is the same estimator on a recoded column -----------------------

def test_a_coarsened_run_reproduces_the_estimate_on_the_column_it_folds_to(
        coarsened, uncoarsened):
    """The denominator, and the only oracle available for a fold.

    The four-level columns ARE the two-level ones plus a coin flip, so the
    grouping that removes the flip has to give back the number the two-level
    columns give — not approximately, but through the same arithmetic on the
    same rows. A fold that were a new estimator rather than a recoding would
    show up here and nowhere else.
    """
    assert coarsened["status"] == "numerically_solved"
    assert uncoarsened["status"] == "numerically_solved"
    folded = coarsened["numeric_estimate"]
    plain = uncoarsened["numeric_estimate"]
    assert folded["point"] == pytest.approx(plain["point"], abs=1e-12)
    assert folded["do_prob_treated"] == pytest.approx(
        plain["do_prob_treated"], abs=1e-12)
    assert folded["do_prob_control"] == pytest.approx(
        plain["do_prob_control"], abs=1e-12)
    themis.verify(_program(fine=True, coarsening=_UNDOES_THE_NOISE), coarsened)


def test_a_different_grouping_is_a_different_number(frame, coarsened):
    """Why this is a decision and not a detail.

    Grouping {0,2} against {1,3} splits on the coin flip instead of on the
    proxy, which is a legitimate partition of the same four levels and a
    different claim about what was measured. If every grouping gave the same
    answer there would be nothing for the caller to choose and nothing for
    the ledger to attribute to them.
    """
    other = {"treatment_proxy": [[0, 2], [1, 3]],
             "outcome_proxy": [[0, 2], [1, 3]]}
    prog = _program(fine=True, coarsening=other)
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    if out["status"] != "numerically_solved":
        # A grouping that carries nothing about U can fail the rank
        # condition outright, which is the same point said louder.
        assert out["estimator_failure"]["failure_type"] == (
            "rank_condition_violated")
        return
    assert out["numeric_estimate"]["point"] != pytest.approx(
        coarsened["numeric_estimate"]["point"], abs=1e-6)


# --- the refusal now names the field that would unblock it --------------------

def test_a_finer_proxy_with_no_grouping_is_refused_and_the_gap_says_what_to_say(
        frame):
    """The measurement this file exists for.

    Before the field existed, this run produced an honest
    ``proxy_cardinality_mismatch`` and an EMPTY gap report: Themis could say
    the declaration and the data do not match, and could not say what
    declaration would unblock it.
    """
    prog = _program(fine=True)
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    assert out["status"] == "structurally_solved"
    assert out["estimator_failure"]["failure_type"] == (
        "proxy_cardinality_mismatch")
    found = _gaps(out, "proxy_coarsening_undeclared")
    assert len(found) == 1
    gap = found[0]
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "point_estimate"
    assert [r["route"] for r in gap["alternative_paths"]] == [
        "declare_a_proxy_coarsening", "reconsider_the_latent_cardinality"]
    assert [s["sentence"] for s in gap["describes"]] == [
        "the_proxies_are_finer_than_the_declared_cardinality",
        "which_levels_are_one_state_is_not_in_the_data"]
    themis.verify(prog, out)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_errand_reaches_a_reader_of_either_language(frame, lang):
    """A gap whose sentence still has a hole in it is a reader being handed
    a template, and it is invisible from the other language."""
    prog = _program(fine=True)
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    report = themis.build_analysis_report(out, program=prog, lang=lang)
    assert "{" not in report and "}" not in report
    assert "proxy_coarsening" in report


def test_a_declared_grouping_files_no_such_gap(coarsened):
    """The gap is about the ABSENCE of a declaration, so a run that has one
    must not carry it — a reader told to declare what they declared has an
    errand they cannot run."""
    assert _gaps(coarsened, "proxy_coarsening_undeclared") == []


def test_a_grouping_that_is_declared_and_still_wrong_gets_its_own_refusal(
        frame):
    """Two situations, two species. "You have not said" sends the reader to
    write a field; "what you said does not line up" must not."""
    prog = _program(fine=True, coarsening={
        "treatment_proxy": [[0, 1], [2, 3, 7]],
        "outcome_proxy": [[0, 1], [2, 3]]})
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    assert out["estimator_failure"]["failure_type"] == (
        "coarsening_does_not_partition_the_proxy")
    assert _gaps(out, "proxy_coarsening_undeclared") == []


def test_a_grouping_that_leaves_a_level_out_is_refused(frame):
    """The other direction, and the one that would silently drop rows out of
    the channel rather than fail loudly."""
    prog = _program(fine=True, coarsening={
        "treatment_proxy": [[0, 1], [2]],
        "outcome_proxy": [[0, 1], [2, 3]]})
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    assert out["estimator_failure"]["failure_type"] == (
        "coarsening_does_not_partition_the_proxy")


def test_a_grouping_with_the_wrong_number_of_groups_is_refused(frame):
    """The groups ARE the states of the latent, so their count is not free.

    Its own species rather than the cardinality mismatch, because here both
    of the things that disagree are the caller's — the grouping and the k —
    and neither is the data's, so the reader is being asked which of their
    own two statements to move.
    """
    prog = _program(fine=True, coarsening={
        "treatment_proxy": [[0], [1], [2, 3]],
        "outcome_proxy": [[0, 1], [2, 3]]})
    out = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    assert out["estimator_failure"]["failure_type"] == (
        "coarsening_group_count_is_not_k")
    assert _gaps(out, "proxy_coarsening_undeclared") == []


def test_a_group_whose_levels_have_no_rows_in_one_arm_is_refused(frame):
    """Positivity is a property of the strata the formula conditions on.

    A raw level with no rows in an arm is fine — often it is exactly what a
    coarsening was for — but a whole GROUP with none is a column of M the
    sample cannot fill, and the estimator must say so rather than divide by
    zero.
    """
    starved = frame.copy()
    starved.loc[starved["z"].isin([0, 1]), "x"] = True
    prog = _program(fine=True, coarsening=_UNDOES_THE_NOISE)
    out = themis.estimate(prog, starved, ci_bootstrap=0)["results"][0]
    assert out["status"] != "numerically_solved"
    assert out["estimator_failure"]["failure_type"] in {
        "insufficient_support", "rank_condition_violated"}


# --- the ledger says whose the grouping is ------------------------------------

def test_the_grouping_is_recorded_as_the_callers_choice(coarsened):
    """Not ``caller_asserted``: withdrawing an assertion widens the answer,
    withdrawing this one removes it. The two promise a reader different
    things, so they are different attributions."""
    ledger = (coarsened.get("extensions") or {}).get("assumption_ledger") or {}
    lines = {e.get("id"): e.get("provenance")
             for e in ledger.get("assumptions", [])}
    assert lines.get(_CHOSE) == "caller_chose"
    assert _PLAIN not in lines


def test_a_run_that_folded_nothing_claims_no_choice(uncoarsened):
    """The identity grouping is the absence of a decision, not a decision to
    keep everything — so nothing on this envelope is offered to the reader as
    theirs to change."""
    ledger = ((uncoarsened.get("extensions") or {})
              .get("assumption_ledger") or {})
    lines = {e.get("id"): e.get("provenance")
             for e in ledger.get("assumptions", [])}
    assert lines.get(_PLAIN) == "inherent"
    assert _CHOSE not in lines
    assert "caller_chose" not in set(lines.values())


def test_a_choice_line_with_no_recorded_choice_is_refused(uncoarsened):
    """The counterexample for the ledger gate: a line handed to the caller
    that traces to nothing they did.

    Built on the UNCOARSENED envelope so that the derivation is untouched and
    valid, and only the ATTRIBUTION is moved — the id stays one the estimate
    really declared, so the completeness and no-fabrication checks are both
    satisfied and this line's own gate is the only thing between the reader
    and a lever that is not there.
    """
    forged = copy.deepcopy(uncoarsened)
    ledger = forged["extensions"]["assumption_ledger"]
    for entry in ledger["assumptions"]:
        if entry.get("id") == _PLAIN:
            entry["provenance"] = "caller_chose"
            break
    else:
        raise AssertionError(f"no {_PLAIN} line to doctor")
    said = _refused(forged, _program(columns=("zc", "wc")))
    assert "as their choice" in said


# --- what the re-derivation says no to ----------------------------------------
#
# One doctored envelope per rule, each edited the way the defect it names
# would arrive, and each asserted to be refused NAMING ITS OWN CASE.

_COARSENED_PROGRAM = _program(fine=True, coarsening=_UNDOES_THE_NOISE)


def test_a_forged_point_under_a_coarsening_is_refused(coarsened):
    """The fold is genuinely re-run, not skipped for coarsened tables."""
    forged, step, _ = _doctored(coarsened)
    moved = round(forged["numeric_estimate"]["point"] + 0.30, 6)
    forged["numeric_estimate"]["point"] = moved
    step["inputs"]["point"] = moved
    assert "re-deriving formula (5)" in _refused(forged, _COARSENED_PROGRAM)


def test_a_level_moved_between_groups_is_refused(coarsened):
    """The case the counts cannot see, and the reason the channel records the
    fold's INPUTS rather than its result.

    Not one number changes here. Every W row still sums to its stratum, the
    strata still cover the sample, the marginal still totals, the table is
    the same table — and the answer moves, because which levels are one
    column of M is a fact only the grouping carries. A rule that checked a
    folded table would find nothing wrong with either version of it.
    """
    forged, step, channel = _doctored(coarsened)
    before = copy.deepcopy(channel["treated"])
    _regroup(channel, "z", [[0, 2], [1, 3]])
    assert channel["treated"] == before
    assert "formula (5)" in _refused(forged, _COARSENED_PROGRAM)


def test_a_grouping_that_names_a_level_twice_is_refused(coarsened):
    """Folding a level into two columns counts its rows twice, and the
    doubled table still balances row by row."""
    forged, step, channel = _doctored(coarsened)
    _regroup(channel, "z", [[0, 1], [1, 2, 3]])
    assert "exactly one group" in _refused(forged, _COARSENED_PROGRAM)


def test_a_grouping_that_names_a_level_that_is_not_there_is_refused(coarsened):
    """An index past the levels recorded is a column of M built out of a
    stratum the table does not hold."""
    forged, step, channel = _doctored(coarsened)
    _regroup(channel, "w", [[0, 1], [2, 9]])
    assert "not one of the" in _refused(forged, _COARSENED_PROGRAM)


def test_an_empty_group_is_refused(coarsened):
    """A column of M with no rows behind it. The arity is still k, which is
    what makes this survive a count of the groups."""
    forged, step, channel = _doctored(coarsened)
    _regroup(channel, "z", [[0, 1, 2, 3], []])
    assert "names no levels" in _refused(forged, _COARSENED_PROGRAM)


def test_a_table_folded_to_a_different_k_than_the_query_asks_for_is_refused(
        coarsened):
    """The one tie between the recorded table and the QUESTION.

    Everything else checked here is the table agreeing with itself, which a
    table folded to the wrong arity would also do — formula (5) inverts the
    channel between the LATENT's states, so three columns answer a question
    about a three-state latent whatever the query said.
    """
    forged, step, channel = _doctored(coarsened)
    _regroup(channel, "z", [[0], [1], [2, 3]])
    _regroup(channel, "w", [[0], [1], [2, 3]])
    said = _refused(forged, _COARSENED_PROGRAM)
    assert "posits" in said and "states for the latent" in said


def test_an_estimate_with_no_grouping_recorded_is_refused(coarsened):
    """The shape of every proximal envelope written before this cut: counts
    and no statement of how they become the columns of M. Kept as a case
    because "the grouping is optional" is the one edit that would quietly
    restore the hole."""
    forged, step, channel = _doctored(coarsened)
    del channel["z_groups"]
    assert "which levels make up each column" in _refused(
        forged, _COARSENED_PROGRAM)


# --- the resampled path walks the same fold -----------------------------------

def test_a_resampled_interval_under_a_coarsening_still_verifies(frame):
    """The bootstrap folds through the same two halves the point does, so a
    draw cannot walk a second transcription that the recorded point is then
    compared against."""
    out = themis.estimate(
        _COARSENED_PROGRAM, frame, ci_bootstrap=40)["results"][0]
    estimate = out["numeric_estimate"]
    assert estimate["ci_lower"] is not None
    assert estimate["ci_lower"] <= estimate["point"] <= estimate["ci_upper"]
    themis.verify(_COARSENED_PROGRAM, out)
