"""An answer from data reaches its reader twice, and only one copy was
audited.

The derivation's terminal step records what the estimator did, and every
rule in the verifier re-derives the answer from THAT record. Beside it
sits ``numeric_estimate``, which is what a reader, the report and the
browser actually read. They are one run written down twice.

Measured on a stratified-Wald answer by perturbing every leaf under
``numeric_estimate`` and running the public door on each: of forty-two,
thirty-eight passed. The stated confidence level, the sample size, every
cell of the stratum table, every endpoint of the confidence set — a
reader could be shown a set stretched to [-99, 99], or a first stage of
0.1 where the run computed a hundred thousand, and the door said the
answer verified. Only the point estimate and the sensitivity block held.

The rule that closes it needs no knowledge of any estimator: a name that
appears on both sides names the same thing. The nested views take one
step more, because a table rendered for a reader is not the flat columns
the step recorded — a prefix for the confidence sets, a written-out map
for the stratum table, and for the three cells the step never recorded,
the arithmetic that ties them to what it did.

THE ORDER IS THE MEANING. This runs after the derivation rules and not
before. Ahead of them it would answer for a tampered derivation before
the rule that re-derives it ever ran, and those rules would go
unexercised at the public door — which the suite said out loud: twenty-two
tests that tamper the record started failing on the wrong refusal.

WHAT REMAINS, MEASURED. Nothing, on this answer shape. One leaf held out
for a while — the first-stage F was not a copy that disagreed with its
record, it was a number with no record at all — and the last test in this
file is what it turned into once the producer gave it one.

ON OTHER ANSWER SHAPES, THREE THINGS REMAINED, and all three were the
same thing: the two sides spell one fact differently and the joining rule
above does not produce that spelling. A joint contrast's block is called
``joint_effect`` and the step prefixes its fields ``joint_``; a trimming
summary is ``propensity_summary`` beside ``propensity_``. Both are the
prefix shape this module already had, and both were kept out of it by its
requirement that the correspondence be total — which is right for a
confidence set, where a partial record is a hole with nothing saying so,
and wrong for a block carrying leaves the step never produced.

The third was a curve. Descent stops at a list because each entry of a
series is its own subject, and that is true: a curve's fifth point and the
step both say ``ci_lower`` and mean different intervals. What it leaves
out is that ONE of those entries is the step's own, and the step says
which by the point it reports. Measured before it was written: on every
answer carrying both, exactly one row answers to that point, and its
interval is the step's. Those rows all happen to be last, and a rule
written on the position would hold a reordered curve to the wrong
interval, so the rule is written on the number.

What it cost, measured: the point half of each of these triples was
already read — a joint contrast is re-derived from the corners, a curve
level by level — and the interval half, which is what a reader is told
about how sure the number is, was read by nothing.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import json
import pathlib

import themis
from themis.verifier import verify_numeric_display_agrees
from themis.verifier.display_copy_rules import (
    _PARTLY_PREFIXED_VIEWS,
    _THE_ENTRY_THE_STEP_PRODUCED,
    _agree, _spellings, _unambiguous,
)
from themis.verifier.errors import VerificationError

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))


def _recorded(result: dict) -> dict:
    """What the chain wrote down, by name — later steps winning, which is
    the order the rule itself reads them in."""
    out: dict = {}
    for step in (result.get("derivation") or {}).get("steps") or ():
        out.update(step.get("inputs") or {})
    return out


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# w → z, w → y, z → x, x → y, x ↔ y. z is an instrument only once w is
# held fixed, which is what makes the answer a stratified Wald and gives
# the envelope a stratum table to show.
_P_W1 = 0.4
_STRATA = {True: (0.9, 0.3, 0.7, 0.4), False: (0.6, 0.2, 0.5, 0.2)}
_P_Z_GIVEN_W = {True: 0.5, False: 0.1}

PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        *({"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in ("x", "y", "z", "w")),
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": []}},
    ],
}


def _sample(n=40_000, seed=11):
    rng = np.random.default_rng(seed)
    w = rng.random(n) < _P_W1
    z = rng.random(n) < np.where(w, _P_Z_GIVEN_W[True], _P_Z_GIVEN_W[False])
    p_x, p_y = np.empty(n), np.empty(n)
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        m = (w == wv)
        p_x[m] = np.where(z[m], pxz1, pxz0)
        p_y[m] = np.where(z[m], pyz1, pyz0)
    return pd.DataFrame({"w": w, "z": z,
                         "x": rng.random(n) < p_x, "y": rng.random(n) < p_y})


@pytest.fixture(scope="module")
def answer():
    result = themis.estimate(
        PROGRAM, _sample(), ci_bootstrap=0)["results"][0]
    assert result["numeric_estimate"]["method"] == "iv_stratified_wald"
    return result


def _tamper(answer, path, value):
    r = copy.deepcopy(answer)
    node = r["numeric_estimate"]
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return r


# ============================================================ honest first


def test_the_honest_answer_passes(answer):
    """First, or every refusal below proves nothing."""
    themis.verify(PROGRAM, answer)


# ================================================== the sweep, as the gate


def _leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, path + (i,))
    else:
        yield path, node


def _bend(value):
    """A different value of the same species, inside the range the schema
    plausibly allows. A probability nudged out of [0,1] would be caught by
    the contract for the wrong reason, and a duplicated list or a reversed
    pair is an identity under set comparison — either would report a hole
    as closed."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1 if value >= 0 else value - 1
    if isinstance(value, float):
        return value / 2 + 0.01 if 0.0 < value < 1.0 else value * 1.5 + 0.5
    return None


#: Leaves with no witness on the envelope. Empty, and it was not: the
#: first-stage F used to be here, because it was computed from the raw
#: frame and named in no derivation step. The producer records the moments
#: it is a ratio of now, so it left this set by being closed rather than
#: by being excused — which is the only way anything should leave it.
UNWITNESSED: set = set()


def test_every_leaf_of_the_readers_copy_is_held_to_the_record(answer):
    """The measurement, kept as the gate.

    A list of fields would pass on the day a new one is added beside them;
    this asks the question of whatever the envelope actually carries, so a
    field added without a witness arrives here as a failure with its own
    name in it.
    """
    survived = []
    for path, value in _leaves(answer["numeric_estimate"]):
        bent = _bend(value)
        if bent is None or bent == value:
            continue
        try:
            themis.verify(PROGRAM, _tamper(answer, path, bent))
        except Exception:
            continue
        survived.append(path)
    assert set(survived) == UNWITNESSED, sorted(
        ".".join(map(str, p)) for p in set(survived) ^ UNWITNESSED)


# =========================================== the edits a reader would act on


@pytest.mark.parametrize("path,value", [
    (("ci_level",), 0.5),
    (("sample_size",), 12),
    (("outcome",), "z"),
    (("stratified_anderson_rubin_confidence_set", "lower"), -99.0),
    (("stratified_anderson_rubin_confidence_set", "upper"), 99.0),
    (("stratified_wald", "strata", 0, "weight"), 0.99),
    (("stratified_wald", "outcome_shift"), 0.0),
], ids=["ci_level", "sample_size", "outcome", "set_lower", "set_upper",
        "stratum_weight", "aggregate_shift"])
def test_a_reader_and_an_auditor_are_not_shown_two_different_runs(
        answer, path, value):
    """Seven of the thirty-eight, named because a reader acts on each: the
    confidence level a set is claimed at, the sample it rests on, which
    variable the answer is even about, a confidence set stretched until it
    excludes nothing, a stratum reweighted to nine tenths of the study."""
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, _tamper(answer, path, value))


def test_a_relabelled_stratum_lands_on_a_cell_already_taken(answer):
    """Which cell a row describes is the one thing the step does not
    record, and it says which stratum a reader is looking at. Two rows of
    one table are two different cells, and that survives without a
    record."""
    r = copy.deepcopy(answer)
    rows = r["numeric_estimate"]["stratified_wald"]["strata"]
    rows[0]["values"] = list(rows[1]["values"])
    with pytest.raises(VerificationError, match="already describes"):
        themis.verify(PROGRAM, r)


def test_a_stratum_that_lost_its_units_is_refused(answer):
    """The three cells the step never recorded, held to the arithmetic
    that ties them to what it did: the arms are the whole of the stratum,
    and a weight is that stratum's share of the sample."""
    r = copy.deepcopy(answer)
    row = r["numeric_estimate"]["stratified_wald"]["strata"][0]
    row["n_instrument_high"] = row["n_instrument_high"] + 100
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, r)


# ================================================================ denominator


def test_an_answer_with_nothing_shown_twice_is_left_alone():
    """An answer with no numeric_estimate has no second copy, and a check
    that refused it would refuse everything above for a reason that had
    nothing to do with the copies.

    Asked of the rule rather than through the door, because the door
    declines a derivation-less result before reading any block and the
    shape wanted here is the opposite one: a chain present, a numeric
    estimate absent.
    """
    verify_numeric_display_agrees(
        {"derivation": {"steps": [{"rule": "r", "inputs": {"point": 1.0}}]}},
        {"steps": [{"rule": "r", "inputs": {"point": 1.0}}]})


def test_an_ordinary_backdoor_answer_still_verifies():
    """And the common shape, whose estimate shares half a dozen names with
    its step. A same-name rule that was wrong about any of them would show
    up here rather than on the IV path alone."""
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in ("x", "y", "z")),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }
    rng = np.random.default_rng(3)
    n = 2000
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    frame = pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                          "z": z.astype(bool)})
    res = themis.estimate(prog, frame, ci_bootstrap=0)["results"][0]
    themis.verify(prog, res)
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(prog, _tamper(res, ("outcome",), "z"))


# ================================================= the limit, written down


def test_the_first_stage_f_now_has_a_record_of_its_own(answer):
    """The one leaf this file used to record as unwitnessed.

    The number Stock and Yogo's threshold is applied to was computed from
    the raw frame and named in no derivation step, so nothing had ever
    re-derived it: an F of 0.1 and an F of a hundred thousand were equally
    acceptable. The step records the moments it is a ratio of now, and the
    display copy is held to the record like every other name.
    """
    estimate = answer["numeric_estimate"]
    assert estimate["first_stage_f_stat"] > 10
    inputs = answer["derivation"]["steps"][-1]["inputs"]
    assert {"first_stage_f_stat", "first_stage_s_zz", "first_stage_s_zx",
            "first_stage_s_xx", "first_stage_n_obs",
            "first_stage_n_exog"} <= set(inputs)
    with pytest.raises(VerificationError, match="two different runs"):
        themis.verify(PROGRAM, _tamper(answer, ("first_stage_f_stat",), 0.1))


# ============================================ a name one level in, and its cost


def test_a_bound_inside_a_block_is_held_by_the_blocks_own_name():
    """The question used to be asked of the envelope's outermost keys only,
    which made this rule's reach a fact about how deep an estimator nests
    its answer. Every bound of the probabilities of causation sits one
    level in, and every one of them was a number nobody compared.

    What holds them is the block's name joined to the leaf's — ``pn`` and
    ``lower`` against a recorded ``pn_lower``.
    """
    pair = SHAPES["causation_plugin"]
    block = pair["result"]["numeric_estimate"]["probabilities_of_causation"]
    assert "pn_lower" in _recorded(pair["result"])
    for name in ("pn", "ps", "pns"):
        for leaf in ("lower", "upper"):
            forged = copy.deepcopy(pair["result"])
            forged["numeric_estimate"]["probabilities_of_causation"][
                name][leaf] = block[name][leaf] + 0.05
            with pytest.raises(VerificationError, match="two different runs"):
                themis.verify(pair["program"], forged)


def test_a_bare_name_one_level_in_is_not_evidence_of_anything():
    """What the widening cost when it was tried, kept so nobody tries it
    again from first principles.

    Comparing a nested leaf's OWN name against the record refuses honest
    answers, because most of what an answer reports about itself is
    vocabulary relative to whichever answer carries it. Every point of a
    dose-response curve states a ``ci_lower`` that is that dose's, and the
    step records the run's.

    The sharper case is not here and that is the point worth keeping: a
    probability of sufficiency carries its own interval too, and in THIS
    snapshot both sides happen to be absent, so the snapshot approved the
    widening. The answer that refuses lives in the causation wiring tests.
    Forty-four shapes cover shapes, not the values a shape can take.
    """
    curve = SHAPES["dose_response_linear_dml"]
    points = curve["result"]["numeric_estimate"]["dose_response_curve"]
    record = _recorded(curve["result"])
    assert any(p.get("ci_lower") != record.get("ci_lower") for p in points)
    themis.verify(curve["program"], curve["result"])

    causation = SHAPES["causation_plugin"]
    block = causation["result"]["numeric_estimate"][
        "probabilities_of_causation"]
    assert block["ps"]["ci_lower"] is None, (
        "this shape stopped being the reason the snapshot said yes; the "
        "comment above needs rewriting rather than this line deleting")


def test_the_spelling_rule_is_a_join_and_not_a_guess():
    """A variant that also stripped a plural matched ``pns.lower`` to the
    recorded ``pn_lower`` — two different quantities, one refused honest
    answer. The join is a rule about the two shapes, and so is the fallback
    that follows it: the leaf's own name, offered only where nothing else on
    this envelope answers to that word. What is never offered is a spelling
    nobody wrote, because spelling collides."""
    result = SHAPES["causation_plugin"]["result"]
    record = _recorded(result)
    unambiguous = _unambiguous(result["numeric_estimate"])
    assert record["pn_lower"] != record["pns_lower"]
    assert list(_spellings(("probabilities_of_causation", "pns", "lower"),
                           unambiguous)) == ["pns_lower"]
    assert list(_spellings(("sample_size",), unambiguous)) == ["sample_size"]
    assert list(_spellings(("probabilities_of_causation", "p_y_do_x0"),
                           unambiguous)) == [
        "probabilities_of_causation_p_y_do_x0", "p_y_do_x0"]


def test_a_price_computed_after_the_record_is_not_a_second_run():
    """What this rule is about, and where the line is.

    A ``precision_budget`` is arithmetic on two endpoints that are in BOTH
    copies, computed for a reader after the step recorded its output.
    Demanding the record carry it would demand a record of a derived figure,
    and would make this rule's verdict depend on whether a route annotates
    before or after it builds its derivation — an ordering fact, not a fact
    about the answer. Measured: it did, and one dose route recorded its
    curve from the estimator's own object, so the two copies could never
    match once every interval was priced.

    Not unchecked. Every budget on the envelope is re-derived from the
    interval beside it, which is a stronger question than whether two copies
    of it agree — so the numbers INSIDE the annotated block are still held
    here, and only the annotation itself is out of the comparison.
    """
    curve = [{"x": 1.0, "effect": 2.0, "ci_lower": 1.5, "ci_upper": 2.5}]
    priced = [dict(curve[0], precision_budget={"current_ci_half_width": 0.5,
                                               "n_to_halve_ci": 400})]
    assert _agree(priced, curve)
    assert not _agree([dict(priced[0], effect=9.0)], curve)
    assert not _agree([{k: v for k, v in priced[0].items() if k != "x"}],
                      curve)


# --------------------------- the same run, spelled differently on each side


_JOINT_ROWS = ("joint_backdoor_linear", "joint_general_id_plugin")
_PROPENSITY_ROWS = ("aipw", "tmle", "ipw_stabilized")
_CURVE_ROWS = ("dose_response_causal_forest_dml", "dose_response_linear_dml")


def _corpus(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


def _display_refuses(result):
    with pytest.raises(VerificationError):
        verify_numeric_display_agrees(result, result.get("derivation"))


def _terminal_inputs(result):
    return result["derivation"]["steps"][-1]["inputs"]


@pytest.mark.parametrize("name", _JOINT_ROWS)
@pytest.mark.parametrize("side", ("step", "view"))
@pytest.mark.parametrize("endpoint", ("ci_lower", "ci_upper"))
def test_a_joint_interval_that_disagrees_with_its_record_is_refused(
        name, side, endpoint):
    """The endpoints a reader is shown for a joint contrast, against the
    ones the step recorded. Neither copy moves the point, and the point is
    what the corners re-derive — so this is the half of the block that had
    no reader at all."""
    _, result = _corpus(name)
    verify_numeric_display_agrees(result, result["derivation"])
    if side == "step":
        _terminal_inputs(result)[f"joint_{endpoint}"] += 0.25
    else:
        result["numeric_estimate"]["joint_effect"][endpoint] += 0.25
    _display_refuses(result)


@pytest.mark.parametrize("name", _PROPENSITY_ROWS)
@pytest.mark.parametrize("field", ("floor", "n_trimmed", "raw_max", "raw_min"))
def test_a_trimming_summary_that_disagrees_with_its_record_is_refused(
        name, field):
    """How much of the sample was Winsorized away, and between which
    bounds. A reader who is told a floor the run did not use is told the
    estimate rests on a different amount of the data than it does."""
    _, result = _corpus(name)
    verify_numeric_display_agrees(result, result["derivation"])
    step = _terminal_inputs(result)
    if f"propensity_{field}" not in step:
        pytest.skip("this route records no such field")
    step[f"propensity_{field}"] = (
        step[f"propensity_{field}"] + 1
        if isinstance(step[f"propensity_{field}"], int) else 0.5)
    _display_refuses(result)


@pytest.mark.parametrize("name", _CURVE_ROWS)
@pytest.mark.parametrize("endpoint", ("ci_lower", "ci_upper"))
def test_the_curve_row_the_step_produced_is_held_to_its_record(name, endpoint):
    _, result = _corpus(name)
    verify_numeric_display_agrees(result, result["derivation"])
    _terminal_inputs(result)[endpoint] += 0.25
    _display_refuses(result)


@pytest.mark.parametrize("name", _CURVE_ROWS)
def test_the_row_is_found_by_the_point_and_not_by_its_place(name):
    """Reversing the curve changes which row is last and changes nothing
    about which row the step produced."""
    _, result = _corpus(name)
    result["numeric_estimate"]["dose_response_curve"].reverse()
    verify_numeric_display_agrees(result, result["derivation"])

    row = next(r for r in result["numeric_estimate"]["dose_response_curve"]
               if r["effect"] == _terminal_inputs(result)["point"])
    row["ci_lower"] -= 0.25
    _display_refuses(result)


def test_a_leaf_the_step_never_produced_is_not_demanded():
    """What the partial rosters are for, said as the measurement that put
    them there: on every answer carrying these blocks, the step records
    none of these leaves, and each is held by whoever re-derives it."""
    assert set(_PARTLY_PREFIXED_VIEWS) == {"joint_effect",
                                           "propensity_summary"}
    never = {"joint_effect": {"control", "treated"},
             "propensity_summary": {"model"}}
    carried = {view: 0 for view in never}
    for name, pair in SHAPES.items():
        result = pair["result"]
        estimate = result.get("numeric_estimate")
        steps = (result.get("derivation") or {}).get("steps") or ()
        if not isinstance(estimate, dict) or not steps:
            continue
        inputs = steps[-1].get("inputs") or {}
        for view, leaves in never.items():
            block = estimate.get(view)
            if not isinstance(block, dict):
                continue
            carried[view] += 1
            prefix = _PARTLY_PREFIXED_VIEWS[view]
            for leaf in leaves & set(block):
                assert f"{prefix}{leaf}" not in inputs, (name, view, leaf)
    assert all(count for count in carried.values()), carried


def test_the_series_roster_says_what_names_the_entry():
    """One series, and the pair that says which of its entries the step
    produced — kept as data so a second series arrives as a row rather
    than as a branch."""
    assert set(_THE_ENTRY_THE_STEP_PRODUCED) == {"dose_response_curve"}
    names_it, named_there, fields = \
        _THE_ENTRY_THE_STEP_PRODUCED["dose_response_curve"]
    assert (names_it, named_there) == ("point", "effect")
    assert set(fields) == {"ci_lower", "ci_upper"}
