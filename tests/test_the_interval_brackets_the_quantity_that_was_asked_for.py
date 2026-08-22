"""An ``effect`` query asks for a contrast; the bounds channel bracketed an arm.

Both are honest quantities and they are not the same one. The question line
said "估计 干预 remote=True 对 productive=True 的因果效应" and the answer line
said "干预到所问的那一档之后，目标事件发生的概率" — each correct about itself,
the pair a non-sequitur, and nothing in the system able to notice because only
one of the two quantities existed as data. ``bounds_results[].estimand`` names
what the interval brackets (a one-member enum, ``arm_probability``); what the
question asked for was named nowhere.

So the repair is a computation and not a wording. ``contrast`` was already the
slot for it and already rendered on both reader surfaces — it was filled by one
of the four methods. Manski natural now fills it too, and what it costs to do
so is the second half of these tests: the verifier must be able to re-derive
the number independently, which takes a fourth count on the envelope.

The census at the bottom is the part that outlives this fix. A method that
brackets an arm and stops has answered a narrower question than the one that
was put, and until now nothing said so out loud. Now it is either reported or
named here with the reason.
"""
from __future__ import annotations

import ast as pyast
import inspect
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import bounds_numeric
from themis.estimation.bounds_numeric import evaluate_manski_natural_bounds
from themis.output import analysis_report
from themis.verifier import bounds_rules
from themis.verifier.errors import VerificationError

U = "u"


# ---------------------------------------------------------------------------
# Programmes and data
# ---------------------------------------------------------------------------


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": U}]}


def _program(levels=(True, False)):
    """X → Y with an unmeasured common cause: point identification is out, so
    the bounds channel is the only thing that answers."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": U}]},
        "statements": [
            {"kind": "variable", "predicate": "remote", "domain": list(levels)},
            {"kind": "variable", "predicate": "productive",
             "domain": [True, False]},
            {"kind": "cause", "from": _atom("remote"), "to": _atom("productive")},
            {"kind": "bidirected", "left": _atom("remote"),
             "right": _atom("productive")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("remote"), "value": levels[0]},
                "target": {"atom": _atom("productive"), "value": True},
                "given": []}},
        ],
    }


def _confounded(seed=11, n=3000, p_remote_given_u=(0.65, 0.35), effect=0.2):
    """A frame where the treatment and the outcome share a cause, so the naive
    contrast is wrong and the truth is known: ``effect``."""
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    remote = rng.random(n) < np.where(u, *p_remote_given_u)
    productive = rng.random(n) < np.clip(
        0.35 + effect * remote + 0.25 * u, 0, 1)
    return pd.DataFrame({"remote": remote, "productive": productive})


def _row(df, program=None, *, method="manski_natural"):
    out = themis.estimate(program or _program(), df, ci_bootstrap=0)
    rows = [b for b in (out["results"][0].get("bounds_results") or ())
            if b.get("method") == method]
    assert len(rows) == 1, f"expected one {method} row, got {len(rows)}"
    return rows[0]


def _arm(df, x_val, y_val=True):
    """Manski's natural interval for one arm, transcribed from the paper
    rather than from the module under test."""
    joint = float(((df.remote == x_val) & (df.productive == y_val)).mean())
    off = float((df.remote != x_val).mean())
    return joint, joint + off


# ---------------------------------------------------------------------------
# The quantity that was asked for
# ---------------------------------------------------------------------------


def test_an_effect_query_answered_by_bounds_gets_an_interval_on_the_effect():
    row = _row(_confounded())
    assert row["estimand"] == "arm_probability"
    contrast = row.get("contrast")
    assert contrast is not None, (
        "the query asked for a contrast and the only interval on the row "
        "brackets one arm")
    assert contrast["kind"] == "ace"
    assert contrast["reference_value"] is False


def test_the_contrast_is_the_two_arms_intervals_subtracted():
    """Sharp, and by subtraction: the natural bounds assume nothing, so the
    two arms' unobserved masses are disjoint sub-populations with nothing
    tying them together and every pair of points is jointly attainable."""
    df = _confounded()
    lo_1, hi_1 = _arm(df, True)
    lo_0, hi_0 = _arm(df, False)
    contrast = _row(df)["contrast"]
    assert contrast["lower_value"] == pytest.approx(lo_1 - hi_0, abs=1e-12)
    assert contrast["upper_value"] == pytest.approx(hi_1 - lo_0, abs=1e-12)


@pytest.mark.parametrize("seed", [3, 11, 19])
@pytest.mark.parametrize("skew", [(0.65, 0.35), (0.95, 0.9), (0.2, 0.05)])
def test_the_width_is_one_whatever_the_data_look_like(seed, skew):
    """``P(X≠x) + P(X≠x') = 1``. Not a coincidence of one frame and not a
    statement about how much data there is: the effect cannot be pinned
    tighter than half of ``[-1, 1]`` under these assumptions, ever."""
    contrast = _row(_confounded(seed=seed, p_remote_given_u=skew))["contrast"]
    width = contrast["upper_value"] - contrast["lower_value"]
    assert width == pytest.approx(1.0, abs=1e-12)


def test_the_interval_covers_the_effect_it_is_an_interval_on():
    """The bound is only worth reporting if it is one. Truth is +0.2 by
    construction, and the confounder makes the naive contrast miss it."""
    df = _confounded(effect=0.2)
    contrast = _row(df)["contrast"]
    assert contrast["lower_value"] <= 0.2 <= contrast["upper_value"]
    naive = (float(df[df.remote].productive.mean())
             - float(df[~df.remote].productive.mean()))
    assert abs(naive - 0.2) > 0.05, (
        "this frame is supposed to be confounded enough that the naive "
        "contrast is visibly wrong")


def test_an_instrument_buys_a_narrower_interval_on_the_same_quantity():
    """Balke-Pearl and Manski natural now bracket the same two quantities on
    the same run, so they can be read against each other — which is the point
    of naming the quantity rather than the method."""
    rng = np.random.default_rng(23)
    n = 3000
    u = rng.random(n) < 0.5
    z = rng.random(n) < 0.5
    remote = rng.random(n) < np.clip(0.2 + 0.5 * z + 0.2 * u, 0, 1)
    productive = rng.random(n) < np.clip(0.35 + 0.2 * remote + 0.25 * u, 0, 1)
    df = pd.DataFrame({"z": z, "remote": remote, "productive": productive})
    program = _program()
    program["statements"].insert(
        0, {"kind": "variable", "predicate": "z", "domain": [True, False]})
    program["statements"].insert(
        3, {"kind": "cause", "from": _atom("z"), "to": _atom("remote")})
    out = themis.estimate(program, df, ci_bootstrap=0)
    rows = {b["method"]: b for b in out["results"][0]["bounds_results"]}
    natural = rows["manski_natural"]["contrast"]
    iv = rows["balke_pearl_iv"]["contrast"]
    assert natural["lower_value"] <= iv["lower_value"]
    assert iv["upper_value"] <= natural["upper_value"]
    assert (iv["upper_value"] - iv["lower_value"]) < 1.0


# ---------------------------------------------------------------------------
# Where there is no baseline arm
# ---------------------------------------------------------------------------


def test_a_three_level_treatment_has_no_baseline_and_reports_no_contrast():
    """With three or more levels there is no one arm the difference is
    against, and picking one would be the module inventing a question."""
    rng = np.random.default_rng(5)
    n = 3000
    u = rng.random(n) < 0.5
    remote = rng.integers(0, 3, n)
    productive = rng.random(n) < np.clip(0.3 + 0.1 * remote + 0.2 * u, 0, 1)
    df = pd.DataFrame({"remote": remote, "productive": productive})
    row = _row(df, _program(levels=(0, 1, 2)))
    assert row["estimand"] == "arm_probability"
    assert row.get("contrast") is None


def test_a_treatment_nobody_varied_reports_no_contrast():
    """One observed level: the queried arm is the only arm there is, so there
    is nothing for the difference to be against. Asked of the ARMS rather
    than of the declared domain, so a two-level declaration observed at one
    level is answered on what the data hold."""
    n = 400
    df = pd.DataFrame({
        "remote": np.ones(n, dtype=bool),
        "productive": np.arange(n) % 3 == 0,
    })
    nb = evaluate_manski_natural_bounds(
        df, treatment="remote", outcome="productive", ci_bootstrap=0)
    assert nb.contrast is None
    assert nb.sufficient_statistics["n_other_arm"] == 0
    assert nb.sufficient_statistics["n_joint_other_arm"] == 0


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def _answer(result, program):
    text = analysis_report.build_analysis_report(result, program=program)
    start = text.index("## 答案")
    return text[start:text.index("\n## ", start + 1)]


def test_the_answer_line_states_the_effect_and_not_only_the_one_arm():
    program = _program()
    out = themis.estimate(program, _confounded(), ci_bootstrap=0)
    result = out["results"][0]
    contrast = result["bounds_results"][0]["contrast"]
    said = _answer(result, program)
    assert analysis_report._fmt(contrast["lower_value"]) in said
    assert analysis_report._fmt(contrast["upper_value"]) in said
    from themis import language
    assert language.fill(
        analysis_report._BOUNDS_CONTRAST_WORDS["ace"], language.DEFAULT,
    ) in said


# ---------------------------------------------------------------------------
# What the verifier can recompute
# ---------------------------------------------------------------------------


def _query_dict(intervention_val=True):
    return {
        "kind": "effect",
        "target": {"atom": _atom("productive"), "value": True},
        "intervention": {"atom": _atom("remote"), "value": intervention_val},
        "given": [],
    }


def _verify(row):
    bounds_rules.verify_manski_natural_bounds_result(
        row, query_dict=_query_dict())


def _tamper(**changes):
    row = json.loads(json.dumps(_row(_confounded())))
    for key, value in changes.items():
        head, _, tail = key.partition(".")
        if tail:
            if value is None:
                row[head].pop(tail, None)
            else:
                row[head][tail] = value
        elif value is None:
            row.pop(head, None)
        else:
            row[head] = value
    return row


def test_the_verifier_accepts_the_contrast_the_producer_computed():
    _verify(_tamper())


def test_the_verifier_rejects_a_contrast_the_counts_do_not_yield():
    """The constructed no. A contrast nobody recomputes is the least
    supervised number in the block and the one a reader leans on hardest."""
    row = _tamper(**{"contrast.lower_value": -0.05})
    with pytest.raises(VerificationError, match="contrast.lower_value"):
        _verify(row)


def test_the_verifier_rejects_a_contrast_with_no_counts_under_it():
    row = _tamper(sufficient_statistics=None)
    with pytest.raises(VerificationError, match="without the arm counts"):
        _verify(row)


def test_the_verifier_rejects_a_contrast_missing_its_own_count():
    row = _tamper(**{"sufficient_statistics.n_joint_other_arm": None})
    with pytest.raises(VerificationError, match="n_joint_other_arm"):
        _verify(row)


def test_the_verifier_rejects_an_off_arm_joint_count_larger_than_the_off_arm():
    row = _tamper()
    row["sufficient_statistics"]["n_joint_other_arm"] = (
        row["sufficient_statistics"]["n_other_arm"] + 1)
    with pytest.raises(VerificationError, match="off-arm partition"):
        _verify(row)


def test_the_verifier_rejects_a_contrast_outside_the_range_a_difference_has():
    row = _tamper(**{"contrast.lower_value": -1.4, "contrast.upper_value": -0.4})
    with pytest.raises(VerificationError, match=r"\[-1.0, 1.0\]"):
        _verify(row)


def test_a_method_no_rule_can_recompute_may_not_ship_a_contrast():
    """Manski-Tamer's is the exemption declared in the producer; the verifier
    refuses the same row rather than trusting it, so the two halves of the
    decision cannot drift apart silently.

    Aimed at the shared numeric audit, which is where the rule lives and
    which all three per-method rules run. Its own rule would reject this row
    on the expression mismatch first and prove nothing about the contrast.
    """
    row = _tamper()
    with pytest.raises(VerificationError, match="no rule here can"):
        bounds_rules._audit_numeric_bounds(
            row, method="manski_tamer_monotonicity",
            rule="bounds_manski_tamer")


def test_the_same_row_without_the_contrast_passes_that_audit():
    """The other half of the constructed no: what the gate refuses is the
    contrast, not the row."""
    row = _tamper(contrast=None)
    bounds_rules._audit_numeric_bounds(
        row, method="manski_tamer_monotonicity", rule="bounds_manski_tamer")


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------


# Why a method that CAN bracket a contrast does not. Not a to-do list: each
# line is a reason the arm is the only honest thing this method has to say.
_NO_CONTRAST_AND_WHY = {
    "manski_tamer_monotonicity":
        "MTR ties Y(x) and Y(x') together at the unit level, so subtracting "
        "the arm intervals gives a valid but not in general sharp interval — "
        "and there is no polytope here to optimise the difference over the "
        "way Balke-Pearl does. Every other interval this layer reports is "
        "sharp and no field on the envelope says which a row is, so shipping "
        "the first unsharp one unlabelled would be this same defect wearing "
        "the other face.",
}

# Declared symbolically and never evaluated on data, so it has no numeric
# contrast to withhold. Named so that adding a numeric end for it breaks this
# test rather than quietly re-opening the gap.
_SYMBOLIC_ONLY = {"frontdoor_partial"}


def _evaluators() -> dict[str, bool]:
    """{method: does this evaluator ever set a contrast}, read off the source.

    From the source rather than by running them: an evaluator that needs a
    particular shape of frame before it reports one would pass a behavioural
    census by never being given that frame.
    """
    tree = pyast.parse(inspect.getsource(bounds_numeric))
    found: dict[str, bool] = {}
    for node in tree.body:
        if not isinstance(node, pyast.FunctionDef):
            continue
        if not node.name.startswith("evaluate_"):
            continue
        method, says_contrast = None, False
        for call in pyast.walk(node):
            if not isinstance(call, pyast.Call):
                continue
            if getattr(call.func, "id", None) != "NumericBounds":
                continue
            for kw in call.keywords:
                if kw.arg == "method" and isinstance(kw.value, pyast.Constant):
                    method = kw.value.value
                if kw.arg == "contrast":
                    says_contrast = True
        assert method is not None, (
            f"{node.name} builds no NumericBounds naming a method")
        found[method] = says_contrast
    return found


def test_every_numeric_bounds_method_reports_the_asked_quantity_or_says_why_not():
    silent = {m for m, says in _evaluators().items() if not says}
    assert silent == set(_NO_CONTRAST_AND_WHY), (
        "a method that brackets an arm and stops has answered a narrower "
        "question than the effect query put. Report the contrast, or name it "
        "in _NO_CONTRAST_AND_WHY with the reason it cannot be."
    )


def test_the_producers_exemption_is_the_one_the_verifier_refuses():
    """Two halves of one decision. A method the producer stopped reporting for
    while the verifier still accepted one would leave the number the reader
    leans on hardest with nothing behind it."""
    speaks = {m for m, says in _evaluators().items() if says}
    assert speaks == set(bounds_rules._MAY_REPORT_CONTRAST)


def test_the_census_covers_every_method_the_schema_admits():
    schema = json.loads(
        (pathlib.Path(themis.__file__).parent
         / "schemas" / "query_result.schema.json").read_text(encoding="utf-8"))
    declared = set(
        schema["$defs"]["boundsResult"]["properties"]["method"]["enum"])
    assert set(_evaluators()) | _SYMBOLIC_ONLY == declared
