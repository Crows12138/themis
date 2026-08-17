"""Phase 13 — dose-response data-spec diagnostic.

When the user (via NL→AST) flags `dose_response_query` in
`program.extensions.ambiguities`, the kernel emits a
`dose_response_data_required` gap whose `required_data` block fully
specifies what's needed to fit the curve in EconML / DoubleML / GAM
externally. Themis itself does NOT compute the curve — that's the
Phase 14 estimator territory.
"""
from __future__ import annotations

import themis
from themis.types import GapKind


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dose_response_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {
                    "kind": "dose_response_query",
                    "description": "用户问加薪和敬业度的关系图",
                },
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "cause",
             "from": _atom("raise_amount"), "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {"atom": _atom("raise_amount"),
                                  "value": True},
                 "target": {"atom": _atom("engagement"), "value": 4},
                 "given": []}},
        ],
    }


def test_dose_response_query_ambiguity_triggers_gap():
    out = themis.run(_dose_response_program())
    gaps = out["results"][0]["data_gap_report"]["gaps"]
    kinds = [g["kind"] for g in gaps]
    assert "dose_response_data_required" in kinds


def test_dose_response_gap_is_blocking_point_estimate():
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "point_estimate"


def test_dose_response_bare_x_y_dag_appends_minimality_hint():
    """When the dose-response query has a
    bare X→Y DAG (no declared confounders), the gap description should
    append a generic hint asking the user to confirm minimality is
    intentional. Avoids hardcoding domain-specific covariate names but
    surfaces the typical observational dose-response expectation
    (baseline outcome + demographics)."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "..."},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(program)
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert "minimal" in gap["description"] or "DAG 仅声明" in gap["description"]


def test_dose_response_with_confounder_does_not_append_hint():
    """Symmetric: if user declared at least one extra node (typical
    confounder pattern), the minimality hint should NOT fire."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "..."},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "cause",
                "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(program)
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert "DAG 仅声明" not in gap["description"]


def test_dose_response_required_data_carries_full_spec():
    """The whole point of this gap_kind: fully-spec'd data sheet so
    user can take it elsewhere and fit the curve."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    rd = gap["required_data"]
    # Sampling points: ≥4 per Hill-Tukey for non-linearity detection
    assert rd["sampling_point_count"] >= 4
    # Total sample size: K × per-point n (Cohen's d power calc)
    assert rd["min_sample_size"] >= rd["sampling_point_count"] * 50
    # Cohen's d cited in precision_target
    assert "Cohen" in rd["precision_target"]
    assert "d=" in rd["precision_target"]
    # Time window present
    assert rd.get("time_window")
    # SUTVA concerns enumerated
    assert rd.get("sutva_concerns")
    assert len(rd["sutva_concerns"]) >= 1


def _ga(p: str, value: bool) -> dict:
    return {"atom": _atom(p), "value": value}


def _resolvable_confounded_program() -> dict:
    """Same shape as the hint tests, plus enough theta to answer the query.

    Every other program in this file comes back needs_investigation, so
    its derivation is empty. That is the blind spot: the confounders this
    gap reports are read off the derivation's back-door step, and a
    program with no derivation never reaches the reading.
    """
    def prob(target, given, value):
        return {"kind": "probability", "target": target, "given": given,
                "value": value}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {"ambiguities": [
            {"kind": "dose_response_query", "description": "..."},
        ]},
        "statements": [
            {"kind": "variable", "predicate": "tenure", "domain": [True, False]},
            {"kind": "variable", "predicate": "raise_amount",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "engagement",
             "domain": [True, False]},
            {"kind": "cause", "from": _atom("tenure"), "to": _atom("raise_amount")},
            {"kind": "cause", "from": _atom("tenure"), "to": _atom("engagement")},
            {"kind": "cause", "from": _atom("raise_amount"),
             "to": _atom("engagement")},
            prob(_ga("tenure", True), [], 0.4),
            prob(_ga("raise_amount", True), [_ga("tenure", True)], 0.7),
            prob(_ga("raise_amount", True), [_ga("tenure", False)], 0.3),
            prob(_ga("engagement", True),
                 [_ga("raise_amount", True), _ga("tenure", True)], 0.8),
            prob(_ga("engagement", True),
                 [_ga("raise_amount", True), _ga("tenure", False)], 0.6),
            prob(_ga("engagement", True),
                 [_ga("raise_amount", False), _ga("tenure", True)], 0.5),
            prob(_ga("engagement", True),
                 [_ga("raise_amount", False), _ga("tenure", False)], 0.2),
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "intervention": _ga("raise_amount", True),
                       "target": _ga("engagement", True),
                       "given": []}},
        ],
    }


def test_dose_response_reports_the_adjustment_set_the_derivation_used():
    """``confounders_required`` is the back-door step's own adjustment set.

    Reading it used to name a field ``DerivationStep`` does not have, and
    then look for keys no step has ever written — two mistakes that could
    not surface while every dose-response program in the corpus resolved
    to needs_investigation with an empty derivation. With a derivation
    present the reading ran, and ``themis.run`` raised AttributeError.
    """
    out = themis.run(_resolvable_confounded_program())
    result = out["results"][0]
    rules = [s["rule"] for s in result["derivation"]["steps"]]
    assert "backdoor_criterion" in rules, rules

    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert list(gap["required_data"]["confounders_required"]) == ["tenure"]


def test_dose_response_description_names_external_tools():
    """Headline must say Themis isn't the right tool — point at EconML
    / DoubleML / GAM so the user knows where to go next."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    desc = gap["description"]
    assert "Themis 不算曲线" in desc or "不画曲线" in desc.replace(
        "不算", "不画"
    )
    assert "EconML" in desc or "DoubleML" in desc or "GAM" in desc


def test_dose_response_alt_path_offers_binary_fallback():
    """If the user can't collect dose-response data, Themis offers a
    binary contrast as fallback (which it CAN handle)."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    alts = gap["alternative_paths"]
    assert any("二元对比" in a or "binary" in a.lower() for a in alts)


def test_no_ambiguity_no_dose_response_gap():
    """Without the `dose_response_query` ambiguity flag, the kernel
    must NOT emit this gap — the trigger is intentional, not heuristic."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "engagement",
             "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "cause",
             "from": _atom("raise_amount"), "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {"atom": _atom("raise_amount"),
                                  "value": True},
                 "target": {"atom": _atom("engagement"), "value": 4},
                 "given": []}},
        ],
    }
    out = themis.run(program)
    gaps = out["results"][0].get("data_gap_report", {}).get("gaps", [])
    kinds = [g["kind"] for g in gaps]
    assert "dose_response_data_required" not in kinds


def test_gap_kind_enum_includes_dose_response():
    assert GapKind.DOSE_RESPONSE_DATA_REQUIRED.value == (
        "dose_response_data_required"
    )


def test_confounders_required_surfaces_even_when_empty():
    """Subagent real-test caught: when the DAG has no observed
    confounders (empty backdoor set), confounders_required was being
    filtered out of the JSON. The LLM consumer then guessed confounders
    on its own and presented them as Themis output. The contract for
    dose-response gaps: emit confounders_required ALWAYS (empty array
    when nothing extracted) so renderer can distinguish 'kernel tried
    and got nothing' from 'kernel didn't try'."""
    out = themis.run(_dose_response_program())
    gap = next(
        g for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    rd = gap["required_data"]
    # Key must be present (even if empty list — that's the signal)
    assert "confounders_required" in rd
    # Empty for this fixture (no observed confounder declared)
    assert rd["confounders_required"] == []


def test_dose_response_description_renders_predicate_names_for_cause_query():
    """Real-test caught: when the LLM emits a `cause` query (instead
    of `effect`) alongside dose_response_query ambiguity, the gap
    description used to render literal `<intervention>` / `<target>`
    placeholders because the labeller only handled effect queries.
    The fix walks `to_atom` / `from_atom` / `left` / `right` so all
    query kinds resolve to actual predicate names."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "x"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late"},
            {"kind": "variable", "predicate": "prefrontal_function"},
            {"kind": "cause",
             "from": _atom("stays_up_late"),
             "to": _atom("prefrontal_function"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "cause",
                 "from": _atom("stays_up_late"),
                 "to": _atom("prefrontal_function")}},
        ],
    }
    out = themis.run(program)
    desc = next(
        g["description"]
        for g in out["results"][0]["data_gap_report"]["gaps"]
        if g["kind"] == "dose_response_data_required"
    )
    assert "<intervention>" not in desc
    assert "<target>" not in desc
    assert "stays_up_late" in desc
    assert "prefrontal_function" in desc


def test_program_ambiguities_echoed_into_each_result():
    """Real-test caught: the kernel only had a handler for
    dose_response_query — other declared ambiguities (reciprocal,
    mechanism, mediator_choice, ...) were silently swallowed. The fix
    echoes every program-level ambiguity into result.extensions so
    renderers can still see them, even without a per-kind kernel
    handler. Per-query targeting via ambiguity.query_id is preserved."""
    program = _dose_response_program()
    program["extensions"]["ambiguities"].extend([
        {"kind": "reciprocal_causation", "description": "X 反过来影响 Y"},
        {"kind": "mechanism_vs_existence", "description": "想问机制不止存在"},
    ])
    out = themis.run(program)
    ext = out["results"][0].get("extensions") or {}
    kinds = [a["kind"] for a in ext.get("ambiguities", [])]
    assert "dose_response_query" in kinds
    assert "reciprocal_causation" in kinds
    assert "mechanism_vs_existence" in kinds


def test_program_ambiguity_with_query_id_targets_only_that_query():
    """An ambiguity carrying ``query_id`` should attach to that
    specific query result only — not the whole program. Mirrors the
    Phase 14 dose-response per-query routing."""
    program = _dose_response_program()
    # Add a second effect query
    program["statements"].append(
        {"kind": "variable", "predicate": "tenure"})
    program["statements"].append({
        "kind": "cause",
        "from": _atom("tenure"), "to": _atom("engagement"),
        "annotations": {"source": "llm_proposal"}})
    program["statements"].append({
        "kind": "query", "id": "q_tenure",
        "query": {"kind": "effect",
                  "intervention": {"atom": _atom("tenure"), "value": True},
                  "target": {"atom": _atom("engagement"), "value": 4},
                  "given": []}})
    program["extensions"]["ambiguities"].append({
        "kind": "reciprocal_causation",
        "description": "specific to tenure",
        "query_id": "q_tenure",
    })
    out = themis.run(program)
    by_id = {r["query_id"]: r for r in out["results"]}
    q_kinds = [
        a["kind"]
        for a in (by_id["q"].get("extensions") or {}).get("ambiguities", [])
    ]
    q_tenure_kinds = [
        a["kind"]
        for a in (by_id["q_tenure"].get("extensions") or {}).get("ambiguities", [])
    ]
    # q gets only the program-wide dose_response_query
    assert "reciprocal_causation" not in q_kinds
    # q_tenure gets the targeted reciprocal_causation AND the
    # program-wide dose_response_query
    assert "reciprocal_causation" in q_tenure_kinds
