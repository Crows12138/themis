"""S.12.4 wiring e2e — dispatch attaches BoundsResult to effect-query
results that needed_investigation."""
from __future__ import annotations

import themis


def _program(intervention_pred="x", target_pred="y", with_iv=False):
    """Simple bool effect program where backdoor identification fails
    (no observed confounder for X-Y; bidirected to force unidentifiable)."""
    statements = [
        {"kind": "variable", "predicate": target_pred, "domain": [True, False]},
        {"kind": "variable", "predicate": intervention_pred, "domain": [True, False]},
        {
            "kind": "cause",
            "from": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": target_pred,
                   "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        },
        {
            "kind": "bidirected",
            "left": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "right": {"predicate": target_pred,
                      "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        },
    ]
    if with_iv:
        statements.insert(2, {
            "kind": "variable", "predicate": "z", "domain": [True, False],
        })
        statements.append({
            "kind": "cause",
            "from": {"predicate": "z",
                     "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": intervention_pred,
                   "args": [{"type": "const", "name": "me"}]},
            "annotations": {"source": "llm_proposal"},
        })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {
                "atom": {"predicate": intervention_pred,
                         "args": [{"type": "const", "name": "me"}]},
                "value": True,
            },
            "target": {
                "atom": {"predicate": target_pred,
                         "args": [{"type": "const", "name": "me"}]},
                "value": True,
            },
            "given": [],
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


def test_unidentifiable_binary_effect_attaches_manski_bounds():
    """No backdoor + no IV → Manski natural bounds attached."""
    envelope = themis.run(_program())
    result = envelope["results"][0]
    assert result["status"] == "needs_investigation"
    assert result.get("bounds_result") is not None
    bounds = result["bounds_result"]
    assert bounds["method"] in ("manski_natural", "balke_pearl_iv")
    assert bounds["lower_expression"]
    assert bounds["upper_expression"]


def test_manski_bounds_use_actual_predicate_names():
    envelope = themis.run(_program(intervention_pred="aspirin",
                                    target_pred="heart_attack"))
    bounds = envelope["results"][0]["bounds_result"]
    assert "aspirin" in bounds["lower_expression"]
    assert "heart_attack" in bounds["lower_expression"]


def test_solved_query_has_no_bounds():
    """When point identification succeeds, bounds_result is null."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            # No bidirected — backdoor adjustment with empty W is identifiable
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    # Either solved or needs_investigation depending on Theta — but if
    # solved, no bounds_result should be attached
    if result["status"] != "needs_investigation":
        assert result.get("bounds_result") is None


def test_iv_shape_program_triggers_balke_pearl():
    """Phase 12 §S.12.6 patch: when the user supplies an IV-shaped DAG
    (Z→X edge, X↔Y bidirected, no Z→Y), bounds_result picks Balke-Pearl
    even though the kernel's IV identification pass doesn't run on
    ADMG-unidentifiable effect queries."""
    envelope = themis.run(_program(with_iv=True))
    result = envelope["results"][0]
    assert result["status"] == "needs_investigation"
    bounds = result.get("bounds_result")
    assert bounds is not None
    assert bounds["method"] == "balke_pearl_iv"
    # Confirm the detected IV is named in the expressions
    assert "z" in bounds["lower_expression"]
    assert "z" in bounds["upper_expression"]


# ============================================ answer_tier (salience axis)
#
# answer_tier states the strongest answer explicitly, orthogonal to gap
# severity, so a consumer is not misled into reading a blocking
# "unidentifiable" gap as a dead end when an informative interval is in
# hand. Real-usage probe 2026-06-16.


def _tier(envelope):
    return envelope["results"][0]["data_gap_report"]["answer_tier"]


def test_answer_tier_interval_when_unidentifiable_with_iv_bounds():
    """Point ID blocked + informative Balke-Pearl interval → 'interval',
    even though the top gap is severity=blocking."""
    env = themis.run(_program(with_iv=True))
    assert _tier(env) == "interval"
    # The one-line summary leads with answer availability, not the
    # blocking gap, so a prose renderer is not inverted.
    assert env["results"][0]["data_gap_report"]["summary"].startswith(
        "可得区间估计"
    )


def test_answer_tier_interval_when_unidentifiable_with_manski_bounds():
    """No IV, point ID blocked, Manski natural interval → 'interval'."""
    env = themis.run(_program())
    assert _tier(env) == "interval"


def test_answer_tier_point_when_identifiable_even_with_manski_floor():
    """A point-identifiable effect (empty backdoor set) is 'point' even
    though the scheduler also attaches an assumption-free Manski floor —
    bounds presence must NOT be read as point-blocked."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    result = themis.run(program)["results"][0]
    # No unidentifiable gap → point identifiable (data may still be missing).
    assert not any(
        g["kind"] == "unidentifiable_no_admissible_set"
        for g in result["data_gap_report"]["gaps"]
    )
    assert result["data_gap_report"]["answer_tier"] == "point"


def test_answer_tier_none_for_counterfactual_needs_assumption():
    """A counterfactual that stops at NEEDS_ASSUMPTION (no bounds) yields
    neither a point nor an interval → 'none'."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "study", "domain": [True, False]},
            {"kind": "variable", "predicate": "job", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "study",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "job",
                       "args": [{"type": "const", "name": "me"}]},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "counterfactual",
                    "observed": {
                        "atom": {"predicate": "study",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": False,
                    },
                    "counterfactual_intervention": {
                        "atom": {"predicate": "study",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "counterfactual_target": {
                        "atom": {"predicate": "job",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                },
            },
        ],
    }
    result = themis.run(program)["results"][0]
    assert result["status"] == "needs_assumption"
    assert result["data_gap_report"]["answer_tier"] == "none"


def test_iv_bounds_drop_self_contradictory_find_instrument_advice():
    """Real-usage probe 2026-06-15 — when Balke-Pearl IV bounds were
    computed from a declared instrument, the unidentifiable gap must NOT
    still advise "go find an instrument satisfying the IV conditions":
    the interval it points at LITERALLY came from that instrument. The
    boilerplate is replaced by the honest constructive next step (declare
    monotonicity / linearity to tighten the interval to a point estimate).
    """
    result = themis.run(_program(with_iv=True))["results"][0]
    assert result["bounds_result"]["method"] == "balke_pearl_iv"
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "unidentifiable_no_admissible_set"
    )
    alts = gap["alternative_paths"]
    assert not any("找一个满足 IV 条件的工具变量" in a for a in alts), (
        "self-contradictory 'find an instrument' advice survived even "
        "though Balke-Pearl bounds came from a declared instrument"
    )
    # The constructive replacement names the assumption that unlocks a
    # point estimate, and survives scheduler's bounds-hint reconcile pass.
    assert any("monotonicity" in a and "linearity" in a for a in alts)


def test_no_iv_unidentifiable_keeps_find_instrument_advice():
    """Contrast to the test above: with NO instrument (plain bow arc,
    Manski bounds), 'find an instrument' is still legitimate advice and
    must be preserved — the rewrite is gated on balke_pearl_iv."""
    result = themis.run(_program())["results"][0]
    assert result["bounds_result"]["method"] != "balke_pearl_iv"
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "unidentifiable_no_admissible_set"
    )
    assert any(
        "找一个满足 IV 条件的工具变量" in a for a in gap["alternative_paths"]
    )


def test_admg_unidentifiable_emits_unidentifiable_gap():
    """Phase 12 §S.12.6 patch: ADMG-blocked effect queries emit
    `unidentifiable_no_admissible_set` gap_kind via the structure-group
    investigation_request route (target=query:effect_admg)."""
    envelope = themis.run(_program())  # bidirected X↔Y, no IV
    result = envelope["results"][0]
    gap_kinds = [g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", [])]
    assert "unidentifiable_no_admissible_set" in gap_kinds


def test_non_effect_query_no_bounds():
    """Cause / assoc queries don't get bounds (out of scope)."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "x",
                             "args": [{"type": "const", "name": "me"}]},
                    "to": {"predicate": "y",
                           "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    assert result.get("bounds_result") is None


def test_alt_paths_reconciled_with_attached_bounds():
    """Phase 12 §S.12.4 follow-up: when bounds_result is attached, the
    data_gap_report's static "接受 Balke-Pearl bounds" alternative_paths
    text gets rewritten to point at the actually-computed method, and
    actionable_next_steps reflects the rewrite."""
    # Program with no IV → only Manski applies (the Balke-Pearl wording
    # in the static template would be misleading)
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x",
                      "args": [{"type": "const", "name": "me"}]},
             "to":   {"predicate": "y",
                      "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "given": []}},
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    bounds = result.get("bounds_result")
    assert bounds is not None
    method = bounds["method"]
    report = result["data_gap_report"]
    blocking = next(g for g in report["gaps"] if g["severity"] == "blocking")
    alts = blocking["alternative_paths"]
    # Old static "Balke-Pearl bounds" wording must be gone
    assert not any("Balke-Pearl" in a for a in alts)
    # Replaced with concrete reference to the computed method
    assert any(method in a and "bounds_result" in a for a in alts)
    # Subagent real-test caught: bounds pointer must NOT also appear in
    # actionable_next_steps — would duplicate against bounds_result block
    assert not any("bounds_result" in s for s in report["actionable_next_steps"])


def test_unidentifiable_gap_gets_bounds_appended_when_missing():
    """When the blocking gap (e.g. unidentifiable_no_admissible_set)
    has no bounds-flavored alt_path text — its static suggestions are
    purely structural ('measure unmeasured Z', 'do an RCT', 'find an
    IV') — the reconciler should still surface the already-computed
    bounds as a prepended fallback so actionable_next_steps shows it
    ahead of the heavier structural moves."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x",
                      "args": [{"type": "const", "name": "me"}]},
             "to":   {"predicate": "y",
                      "args": [{"type": "const", "name": "me"}]}},
            {"kind": "bidirected",
             "left":  {"predicate": "x",
                       "args": [{"type": "const", "name": "me"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "given": []}},
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    bounds = result.get("bounds_result")
    assert bounds is not None
    method = bounds["method"]
    report = result["data_gap_report"]
    unid = next(
        g for g in report["gaps"]
        if g["kind"] == "unidentifiable_no_admissible_set"
    )
    # Bounds line was *appended* (no original bounds-flavored alt to
    # rewrite) — and prepended so it leads the list
    assert unid["alternative_paths"][0] == (
        f"已计算 bounds（method={method}）— 见 bounds_result"
    )
    # actionable_next_steps stays free of the duplicated pointer (renderer
    # reads bounds_result directly as its own block)
    assert not any("bounds_result" in s for s in report["actionable_next_steps"])


def test_non_binary_outcome_strips_static_bounds_promise():
    """Unbounded continuous outcome (no domain declared): the target
    event ``P(Y=specific_number)`` is degenerate point-mass on a
    continuous distribution, Manski returns None. The static
    "接受 Balke-Pearl bounds 给区间答案" line on missing_distribution
    must be stripped rather than left as a false promise.

    (Discrete-numeric Likert/grid targets DO get Manski now — this
    test specifically pins the unbounded-continuous case.)"""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            # No domain declared = continuous (per nl_to_kernel_ast §2)
            {"kind": "variable", "predicate": "wage"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x",
                      "args": [{"type": "const", "name": "me"}]},
             "to":   {"predicate": "wage",
                      "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "wage",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": 50000},
                 "given": []}},
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    assert result.get("bounds_result") is None
    blocking = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["severity"] == "blocking"
    )
    alts = blocking.get("alternative_paths", [])
    # Critical: no surviving bounds promise
    assert not any("Balke-Pearl" in a or "Manski" in a or "bounds" in a
                   for a in alts)


def test_likert_outcome_gets_manski_bounds():
    """Discrete-numeric outcome (Likert 1-5): the target event
    'engagement=4' IS a non-degenerate probability when domain is
    declared, so Manski natural bounds fire with the same shape as
    the binary case. This was the subagent #1 trip — engagement got
    twisted to bool because Themis used to drop bounds for any
    non-bool target. Continuous bounded outcomes are now in scope."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_1k",
             "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "raise_1k",
                      "args": [{"type": "const", "name": "me"}]},
             "to":   {"predicate": "engagement",
                      "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "raise_1k",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "engagement",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": 4},
                 "given": []}},
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    bounds = result.get("bounds_result")
    assert bounds is not None
    assert bounds["method"] == "manski_natural"
    # Expressions carry the numeric target value verbatim
    assert "engagement=4" in bounds["lower_expression"]
    assert "raise_1k" in bounds["lower_expression"]


def test_target_value_outside_declared_domain_no_bounds():
    """Defensive: target.value=99 with domain=[1,2,3,4,5] is asking
    about an event that isn't in the declared range — fall back to
    'no bounds' rather than emit something the user can't interpret."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "x",
             "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "x",
                      "args": [{"type": "const", "name": "me"}]},
             "to":   {"predicate": "engagement",
                      "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True},
                 "target": {
                     "atom": {"predicate": "engagement",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": 99},
                 "given": []}},
        ],
    }
    envelope = themis.run(program)
    result = envelope["results"][0]
    assert result.get("bounds_result") is None
