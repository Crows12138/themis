"""Phase 7.3 S.IVN.2-4 — IV dispatch + verifier + schema integration."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _iv_ast():
    """Z → X → Y with X ↔ Y latent. IV dispatch fires after backdoor +
    front-door both fail (front-door fails because Z → X → Y is the
    single directed path but Z itself has no backdoor-blocking
    mediator)."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected",
             "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _iv_data(n=3000, seed=0, true_late=1.5):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    p_x = 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u)))
    x = rng.random(n) < p_x
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


# ============================================ dispatch


def test_dispatch_picks_iv_when_backdoor_and_frontdoor_fail():
    df = _iv_data(n=3000, seed=0, true_late=1.5)
    out = themis.estimate(_iv_ast(), df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "iv_wald"
    assert est["instrument"] == "z"
    assert est["conditioning"] == []
    assert abs(est["point"] - 1.5) < 0.4


def test_dispatch_iv_verify_round_trips():
    df = _iv_data(n=500, seed=0)
    ast = _iv_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    themis.verify(ast, out["results"][0])


def test_dispatch_iv_bootstrap_ci():
    df = _iv_data(n=800, seed=0)
    out = themis.estimate(
        _iv_ast(), df, ci_bootstrap=100, random_state=1,
    )
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]


def test_a_dead_instrument_says_so_instead_of_asking_for_monotonicity():
    """The reason has to cross the dispatch boundary, not stop at it.

    With the estimator's refusal dropped, the only advice left on the
    envelope came from the identification layer, which had written — before
    any data was touched — that an instrument alone does not pick an
    estimator and that ``assumptions.monotonicity`` would. Declaring it
    cannot give this instrument a first stage, so the user follows the one
    actionable sentence they were given and arrives back here.
    """
    n = 400
    # E[X|Z=1] and E[X|Z=0] are both exactly 0.5 by construction.
    z = np.array([True, True, False, False] * (n // 4))
    x = np.array([True, False] * (n // 2))
    u = np.random.default_rng(0).standard_normal(n)
    df = pd.DataFrame({"z": z, "x": x, "y": 1.5 * x.astype(float) + 2.0 * u})

    result = themis.estimate(_iv_ast(), df, ci_bootstrap=0)["results"][0]

    failure = result["estimator_failure"]
    assert failure["failure_type"] == "no_first_stage"
    assert failure["kind"] == "data"
    assert failure["estimator"] == "iv_wald"
    assert failure["details"]["denominator"] == 0.0
    assert "first-stage" in failure["reason"]


def _dead_instrument_data(n=400):
    """E[X|Z=1] and E[X|Z=0] are both exactly 0.5 by construction."""
    x = np.array([True, False] * (n // 2))
    u = np.random.default_rng(0).standard_normal(n)
    return pd.DataFrame({
        "z": np.array([True, True, False, False] * (n // 4)),
        "x": x,
        "y": 1.5 * x.astype(float) + 2.0 * u,
    })


def _theta_asks(result):
    return {
        m["name"] for m in result.get("missing_information", [])
        if m["gap"] == "missing_distribution"
    }


def test_a_refused_estimate_does_not_ask_for_the_numbers_it_just_read():
    """A refusal is not a reason to re-ask for what the sample supplied.

    Given monotonicity, the identification pass wants four conditionals
    out of theta and says so. The DataFrame is the other channel those
    come from, and the estimator read them: its refusal reports
    E[x|z=1] = E[x|z=0] = 0.5. Asking to be supplied P(x=True|z=True)
    beside a block quoting its value is the envelope contradicting
    itself within one result.
    """
    ast = _iv_ast()
    ast["statements"][-1]["query"]["assumptions"] = {
        "monotonicity": "non_decreasing",
    }
    asked = themis.run(ast)["results"][0]
    assert _theta_asks(asked) >= {
        "parameter:P(x=True|z=True)", "parameter:P(x=True|z=False)",
    }, "the identification pass no longer asks for the Wald ingredients"

    result = themis.estimate(ast, _dead_instrument_data(), ci_bootstrap=0)["results"][0]

    assert result["estimator_failure"]["failure_type"] == "no_first_stage"
    assert result["estimator_failure"]["details"]["e_treatment_high"] == 0.5
    assert not _theta_asks(result)
    report = result["data_gap_report"]
    assert not [g for g in report["gaps"] if g["kind"] == "missing_distribution"]
    assert not [
        item
        for request in result.get("investigation_requests", [])
        for item in request.get("items", [])
        if item["gap"] == "missing_distribution"
    ]
    themis.verify_data_gap_report(result)


def test_an_iv_point_estimate_leaves_no_blocking_ask_for_its_own_inputs():
    """The tier gate is about the tier, and only about the tier.

    An IV LATE is assumption-laden, so the report rightly stays at the
    interval tier with the bounds framing intact. That verdict used to
    take the θ reconciliation down with it, so a successful IV estimate
    shipped with four ``missing_distribution: blocking`` gaps naming the
    very conditionals it had just computed from.
    """
    ast = _iv_ast()
    ast["statements"][-1]["query"]["assumptions"] = {
        "monotonicity": "non_decreasing",
    }
    result = themis.estimate(ast, _iv_data(), ci_bootstrap=0)["results"][0]

    assert result["status"] == "numerically_solved"
    report = result["data_gap_report"]
    assert report["answer_tier"] == "interval"
    assert not [g for g in report["gaps"] if g["kind"] == "missing_distribution"]
    assert not [
        step for step in report.get("actionable_next_steps", [])
        if step.startswith("补 P(")
    ]


def test_the_admg_reason_names_an_instrument_only_where_one_reaches_it():
    """What the reason claims is what gates it.

    The sentence asserts that an instrumental-variable escalation reaches
    this graph. It used to be emitted whenever any route left any note —
    a condition about the run, not about the assertion — and to carry a
    perishable second half ("could not be run as it stands — see the
    items alongside this one") that survived both the estimator running
    it and the items being answered.
    """
    with_iv = themis.run(_iv_ast())["results"][0]
    reason = with_iv["missing_information"][0]["reason"]
    assert "工具变量升级路线确实到得了它" in reason
    assert "could not be run" not in reason
    assert "items alongside this one" not in reason

    no_iv = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    bare = themis.run(no_iv)["results"][0]["missing_information"][0]["reason"]
    assert "instrumental-variable" not in bare


_MONOTONICITY_ASK = "effect:iv_monotonicity_undeclared"


def _asks_for_monotonicity(result) -> dict:
    """Every surface the ask can still be advertised on."""
    report = result.get("data_gap_report") or {}
    return {
        "items": [
            m for m in result.get("missing_information") or []
            if m["name"] == _MONOTONICITY_ASK
        ],
        "requests": [
            item
            for request in result.get("investigation_requests") or []
            for item in request.get("items") or []
            if item["target"] == _MONOTONICITY_ASK
        ],
        "gaps": [
            g for g in report.get("gaps") or []
            if any(
                ref.get("ref_id") == _MONOTONICITY_ASK
                for ref in g.get("provenance") or []
            )
        ],
        "steps": [
            s for s in report.get("actionable_next_steps") or []
            if "monotonicity" in s
        ],
    }


def test_the_declaration_is_asked_for_only_where_declaring_would_do_it():
    """The kernel refuses to pick an estimator — until it picks one.

    Without data that sentence is the query's one actionable next step and
    it is true: the identification pass will not write the Wald estimand
    until monotonicity is declared. Handed a DataFrame the estimation
    layer runs an IV estimator without consulting the declaration at all,
    which is why the ask travels marked as superseded by that run.
    """
    ask = _asks_for_monotonicity(themis.run(_iv_ast())["results"][0])
    assert ask["items"] and ask["requests"] and ask["gaps"]
    assert ask["items"][0]["superseded_by_estimation"] is True
    assert ask["requests"][0]["superseded_by_estimation"] is True


def test_a_refused_instrument_withdraws_the_advice_that_cannot_help_it():
    """Declaring monotonicity does not give an instrument a first stage.

    Measured both ways: with the declaration supplied, this data produces
    the same ``no_first_stage`` refusal and no number. So the one
    actionable sentence the reader was left with sent them to do
    something that lands them back here.
    """
    result = themis.estimate(
        _iv_ast(), _dead_instrument_data(), ci_bootstrap=0,
    )["results"][0]

    assert result["estimator_failure"]["failure_type"] == "no_first_stage"
    for surface, entries in _asks_for_monotonicity(result).items():
        assert not entries, f"{surface}: {entries}"


def test_a_delivered_late_stops_advertising_the_declaration_it_ran_without():
    """The number is the answer to the ask, not a thing beside it.

    The estimation layer produces the Wald with monotonicity undeclared
    and discloses it in the ledger, at ``invalidating`` severity. Telling
    the reader to declare it to obtain what they are holding is the
    identification pass's pre-data sentence outliving the pass — it
    survived on the gap surface alone, because finalising a number pops
    the item list and the gate that keeps the bounds framing then
    returned before reconciling the gaps.
    """
    result = themis.estimate(_iv_ast(), _iv_data(), ci_bootstrap=0)["results"][0]

    assert result["numeric_estimate"]["method"] == "iv_wald"
    for surface, entries in _asks_for_monotonicity(result).items():
        assert not entries, f"{surface}: {entries}"

    ledger = result["extensions"]["assumption_ledger"]["assumptions"]
    disclosed = {e["id"]: e for e in ledger if e.get("id")}
    assert "monotonicity_first_stage_effect_same_sign_for_all_units" in disclosed
    assert disclosed[
        "monotonicity_first_stage_effect_same_sign_for_all_units"
    ]["severity"] == "invalidating"


def test_dispatch_iv_prefers_backdoor_when_both_available():
    """If backdoor works, IV must not fire (dispatch priority)."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            # Observable confounder Z; backdoor via {z} works
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    n = 500
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    y = 1.0 * z + 2.0 * x.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"z": z, "x": x, "y": y})
    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_linear"


def test_a_conditional_query_gets_no_unconditional_iv_answer():
    """A Wald ratio has no conditional form, so it cannot answer P(Y|do(X), C).

    The identification layer refuses this combination explicitly. The
    estimation layer's guard was written separately and did not: it shipped
    a stratified Wald whose strata are the INSTRUMENT's conditioning set,
    not the query's ``given``. The proof that the number answered neither
    question is that conditioning on c=True and on c=False produced the
    same value to the last bit — so this test asks both, and neither may
    come back as an IV estimate.
    """
    def _ast(c_value):
        return {
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "z", "domain": [True, False]},
                {"kind": "variable", "predicate": "c", "domain": [True, False]},
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "bidirected",
                 "left": _atom("x"), "right": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [{"atom": _atom("c"), "value": c_value}],
                }},
            ],
        }

    rng = np.random.default_rng(0)
    n = 3000
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    c = rng.random(n) < 0.5
    x = rng.random(n) < 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u)))
    y = 1.5 * x.astype(float) + 0.8 * c.astype(float) + 2.0 * u
    df = pd.DataFrame({"z": z, "c": c, "x": x, "y": y})

    for c_value in (True, False):
        result = themis.estimate(_ast(c_value), df, ci_bootstrap=0)["results"][0]
        method = (result.get("numeric_estimate") or {}).get("method", "")
        assert not method.startswith("iv_"), (
            f"given c={c_value} was answered by {method!r}"
        )


def test_dispatch_iv_skips_when_wald_denominator_zero():
    """Pathological data (Z has no effect on X) should make dispatch
    silently skip the IV path rather than crash."""
    ast = _iv_ast()
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "x": np.ones(n, dtype=bool),  # constant X → Wald denom is 0
        "y": rng.standard_normal(n),
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Estimator raised, dispatch caught, no numeric_estimate attached
    assert "numeric_estimate" not in result
