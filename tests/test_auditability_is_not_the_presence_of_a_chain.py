"""Whether an answer can be independently re-derived, and whether it carries
a reasoning chain, are two questions.

Thirteen ``verify_*`` entry points re-derive different things and
:mod:`themis.audits` says which apply to a given envelope. The report's
verification section did not ask it — it asked whether ``derivation`` was
present and picked one of two sentences. On 878 of 2803 envelopes in one
suite run those give opposite answers: an interval or a recovered ATE, no
chain, and a registered auditor that recomputes exactly that answer. Each
of those readers was told, directly under the number, that no re-checkable
conclusion had been reached, and sent to the gap-report audit — which is
not an audit of the answer.

The same conflation decided a status (the missing-data route withheld
``numerically_solved`` for want of a chain while its sibling claimed it
without one) and gated the MCP report's stamp.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.audits import AUDITS, Artifact, applicable
from themis.output.analysis_report import build_analysis_report


# ------------------------------------------------------------------ programs


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "p"}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _effect_query():
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "target": {"atom": _atom("y"), "value": True},
        "intervention": {"atom": _atom("x"), "value": True},
        "given": []}}


def _program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "p"}]},
            "statements": statements}


BACKDOOR_PROG = _program([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"), _effect_query(),
])

# X <-> Y: not point-identified, so the answer is a Manski interval and no
# chain is built. The commonest of the shapes that were lied to.
BOUNDS_PROG = _program([
    _var("x"), _var("y"), _edge("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _effect_query(),
])

MISSING_PROG = _program([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
    {"kind": "missingness_indicator", "id": "R_y",
     "missing_var": _atom("y"), "caused_by": [_atom("z")]},
    _effect_query(),
])

SELECTION_PROG = _program([
    _var("x"), _var("y"), _var("m"), _var("w"),
    _edge("x", "y"), _edge("x", "w"), _edge("y", "m"), _edge("m", "w"),
    {"kind": "observation", "atom": _atom("w"), "value": True},
    _effect_query(),
])

# A probability query with no Theta reaches no answer at all — nothing for
# any auditor to recompute. The counterexample the wording has to earn.
NO_ANSWER_PROG = _program([
    _var("x"), _var("y"), _edge("x", "y"),
    {"kind": "query", "id": "q", "query": {
        "kind": "probability",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": True}]}},
])


# --------------------------------------------------------------------- data


def _backdoor_frame(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


def _mar_frame(n=6000, seed=20):
    rng = np.random.default_rng(seed)
    Z = rng.binomial(1, 0.5, n)
    X = rng.binomial(1, 0.3 + 0.4 * Z)
    pY = np.clip(0.2 + 0.2 * X + 0.2 * Z + 0.3 * X * Z, 0, 1)
    Yf = rng.binomial(1, pY)
    R = rng.binomial(1, 0.1 + 0.6 * Z)
    col = Yf.astype(float).copy()
    col[R == 1] = np.nan
    return pd.DataFrame({"x": X.astype(float), "y": col, "z": Z.astype(float)})


def _selection_frame(n, seed):
    rng = np.random.default_rng(seed)
    X = rng.binomial(1, 0.5, n)
    Y = rng.binomial(1, 0.3 + 0.4 * X)
    M = rng.binomial(1, 0.2 + 0.5 * Y)
    W = rng.binomial(1, 0.1 + 0.4 * X + 0.4 * M)
    return pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool),
                         "m": M.astype(bool), "w": W.astype(bool)})


# ---------------------------------------------------------------- envelopes


@pytest.fixture(scope="module")
def backdoor():
    env = themis.estimate(BACKDOOR_PROG, _backdoor_frame(), ci_bootstrap=0)
    return BACKDOOR_PROG, env["results"][0]


@pytest.fixture(scope="module")
def bounds():
    env = themis.estimate(BOUNDS_PROG, _backdoor_frame()[["x", "y"]],
                          ci_bootstrap=0)
    return BOUNDS_PROG, env["results"][0]


@pytest.fixture(scope="module")
def recovered():
    env = themis.estimate(MISSING_PROG, _mar_frame(), ci_bootstrap=0)
    return MISSING_PROG, env["results"][0]


@pytest.fixture(scope="module")
def selection_recovered():
    full = _selection_frame(20_000, seed=12)
    env = themis.estimate(
        SELECTION_PROG, full[full.w].reset_index(drop=True),
        reference_data=_selection_frame(20_000, seed=13), ci_bootstrap=0,
    )
    return SELECTION_PROG, env["results"][0]


@pytest.fixture(scope="module")
def no_answer():
    return NO_ANSWER_PROG, themis.run(NO_ANSWER_PROG)["results"][0]


def _tamper_point(result: dict) -> dict:
    out = copy.deepcopy(result)
    ne = out["numeric_estimate"]
    ne["point"] = float(ne["point"]) + 0.37
    for nested in ("recovered_ate", "selection_recovery_numeric"):
        if isinstance(ne.get(nested), dict) and "point" in ne[nested]:
            ne[nested]["point"] = ne["point"]
    return out


def _tamper_bounds(result: dict) -> dict:
    out = copy.deepcopy(result)
    b = row(out, "manski_natural")
    b["lower_value"] = float(b["lower_value"]) - 0.21
    return out


# =================================== the field says something checkable

ANSWER_ROWS = tuple(row.name for row in AUDITS if row.re_derives_answer)


from tests.bounds_rows import methods, row

def test_the_premise_the_shapes_below_rest_on(backdoor, bounds, recovered,
                                              selection_recovered):
    """Three of these four answers arrive with no chain. Without this the
    tests below would all be about the ordinary back-door envelope."""
    assert "derivation" in backdoor[1]
    for _, result in (bounds, recovered, selection_recovered):
        assert "derivation" not in result


@pytest.mark.parametrize("fixture,tamper", [
    ("backdoor", _tamper_point),
    ("bounds", _tamper_bounds),
    ("recovered", _tamper_point),
    ("selection_recovered", _tamper_point),
])
def test_only_a_row_that_claims_the_answer_goes_red_when_the_answer_is_forged(
    fixture, tamper, request,
):
    """The claim is earned rather than read back off the table.

    Move the answer and ask every applicable audit. A row that catches it
    was auditing the answer; a row that does not catch it was auditing
    something else, and must not have said otherwise.
    """
    program, result = request.getfixturevalue(fixture)
    rows = themis.audit(program, tamper(result))
    failed = {row["audit"] for row in rows if not row["ok"]}
    assert failed, "改坏了答案，却没有一项复核发现"
    assert failed <= set(ANSWER_ROWS), (
        f"{sorted(failed - set(ANSWER_ROWS))} 在答案被改坏时变红，"
        "却没有声明它重算的是答案"
    )


@pytest.mark.parametrize("fixture,tamper", [
    ("backdoor", _tamper_point),
    ("bounds", _tamper_bounds),
    ("recovered", _tamper_point),
    ("selection_recovered", _tamper_point),
])
def test_the_untouched_answer_passes_every_audit(fixture, tamper, request):
    """The other half: without it the test above passes on an auditor that
    refuses everything."""
    program, result = request.getfixturevalue(fixture)
    rows = themis.audit(program, result)
    assert rows and all(row["ok"] for row in rows), \
        [row for row in rows if not row["ok"]]


def test_a_row_that_audits_something_beside_the_answer_says_so():
    """Exactly five envelope rows recompute the answer; a table that
    claimed all of them would make the section useless.

    The five are named and the rest are counted as the rest, because the
    denominator grows: an audit added tomorrow audits something beside
    the answer unless it says otherwise, and a hard-coded complement
    would make adding one look like a failure.

    Four of the five are gated on the thing they re-derive, so for them the
    flag is the whole fact. The fifth is the chainless door, gated on
    nothing, and what it recomputes depends on what the envelope carries —
    which is why nothing reads this flag without also asking the envelope.
    """
    envelope_rows = [r for r in AUDITS if r.artifact is Artifact.QUERY_RESULT]
    claiming = {r.name for r in envelope_rows if r.re_derives_answer}
    assert claiming == {
        "verify", "verify_answer_claims", "verify_bounds_results",
        "verify_selection_recovery_numeric", "verify_missing_data_numeric",
    }
    assert len(envelope_rows) > len(claiming), (
        "every envelope row claims to recompute the answer, which is the "
        "state this test exists to prevent"
    )


# ============================ the section says who can re-derive this answer

@pytest.mark.parametrize("fixture,auditor", [
    ("backdoor", "verify"),
    ("bounds", "verify_bounds_results"),
    ("recovered", "verify_missing_data_numeric"),
    ("selection_recovered", "verify_selection_recovery_numeric"),
])
def test_the_report_names_the_audit_that_recomputes_this_answer(
    fixture, auditor, request,
):
    program, result = request.getfixturevalue(fixture)
    md = build_analysis_report(result, program=program)
    assert "本身可以被独立重算" in md
    assert auditor in md, f"报告没提 {auditor}，而它正是重算这个答案的那一个"
    # and it is not the sentence for a result that reached nothing
    assert "尚未得出可复核" not in md


def test_a_result_that_reached_no_answer_still_says_so(no_answer):
    """The counterexample the wording has to earn: a section that always
    claims re-derivability would pass every test above and be worthless."""
    program, result = no_answer
    assert not result.get("numeric_estimate")
    assert not result.get("bounds_results")
    assert not any(row.re_derives_the_answer_of(result)
                   for row in applicable(result))
    # And the flag alone would have said otherwise: the chainless door
    # applies here and claims to recompute an answer, which on a result
    # that reached none is a claim about nothing.
    assert any(row.re_derives_answer for row in applicable(result))

    md = build_analysis_report(result, program=program)
    assert "没有能重算这个答案本身的复核" in md
    assert "本身可以被独立重算" not in md


def test_every_audit_the_section_lists_is_one_that_applies(recovered):
    """Naming an audit that would refuse this artifact is the failure
    themis.audits exists to end — the caller cannot tell 'not about your
    result' from 'your result failed'."""
    program, result = recovered
    md = build_analysis_report(result, program=program)
    listed = {row.name for row in AUDITS if f"themis.{row.name}(" in md}
    assert listed == {row.name for row in applicable(result)}


def test_the_stamp_marks_each_check_rather_than_the_result_as_a_whole(bounds):
    program, result = bounds
    rows = themis.audit(program, result)
    md = build_analysis_report(result, program=program, audited=rows)
    assert f"✓ **{len(rows)} 项独立复核全部通过" in md
    assert md.count("✓ ") >= len(rows)


# ================================ the status rests on the same question

@pytest.mark.parametrize("fixture", ["recovered", "selection_recovered"])
def test_a_recovery_estimate_claims_the_number_it_produced(fixture, request):
    """Both routes produce a point for the query's own estimand, neither
    carries a chain, and each has a registered auditor that recomputes its
    number. They used to disagree about the status anyway."""
    _, result = request.getfixturevalue(fixture)
    assert result["status"] == "numerically_solved"
    assert result["numeric_estimate"]["point"] is not None
    assert "derivation" not in result
    assert any(row.re_derives_answer and row.needs_method
               for row in applicable(result))


def test_the_recovered_estimate_records_the_run_it_came_out_of(recovered):
    """The contract is out of reach on this path — the columns carry NaN —
    but the seed, the resample count and what was hashed are not, and a
    reader who cannot see them cannot tell this number from one estimated
    on different rows."""
    _, result = recovered
    ctx = result["estimation_context"]
    assert ctx["data_hash"] == result["numeric_estimate"]["data_hash"]
    assert ctx["sample_size"] == result["numeric_estimate"]["sample_size"]
    assert ctx["random_state"] == 42
    assert ctx["ci_bootstrap"] == 0


def test_the_recovered_estimate_still_conforms_to_the_envelope_schema(recovered):
    from themis.input.syntactic_validator import validate_result

    validate_result(recovered[1])
