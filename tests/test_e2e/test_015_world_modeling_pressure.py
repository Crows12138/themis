from __future__ import annotations

from scripts.run_015_world_modeling_pressure import run_all


def test_015_world_modeling_pressure_script_passes():
    results = run_all()

    assert {result.status for result in results} == {"PASS"}
    by_name = {result.name: result for result in results}

    exercise = by_name["exercise_waist_variable_merge"].details
    assert exercise["result_status"] == "needs_investigation"
    assert exercise["introduced_predicates"] == ["waist_reduced"]
    assert exercise["framing_gaps"]["running"] == [
        "direction",
        "baseline",
        "state_vs_event",
    ]
    assert "missing_distribution" in exercise["data_gap_kinds"]
    assert exercise["data_gap_verify"] == "accepted"
    assert (
        exercise["pressure_signal"]
        == "variable_framing_merge_works_but_target_still_underframed"
    )

    late_sleep = by_name["late_sleep_predicate_drift"].details
    assert late_sleep["result_status"] == "structurally_solved"
    assert late_sleep["introduced_predicates"] == [
        "cognitive_slowness",
        "staying_up_late",
    ]
    unmatched = {
        item["source_predicate"]: item
        for item in late_sleep["link_diagnostic"]["unmatched"]
    }
    assert set(unmatched) == {"cognitive_slowness", "staying_up_late"}
    assert (
        unmatched["staying_up_late"]["candidates"][0]["target_predicate"]
        == "stays_up_late"
    )
    assert set(late_sleep["query_predicate_gaps"]) == {
        "feels_tired_next_morning",
        "stays_up_late",
    }
    after_links = late_sleep["after_confirmed_links"]
    assert after_links["introduced_predicates"] == []
    assert after_links["query_predicate_gaps"]["stays_up_late"] == [
        "measurement",
        "direction",
        "baseline",
        "state_vs_event",
    ]
    assert "observability" not in after_links["query_predicate_gaps"][
        "feels_tired_next_morning"
    ]
    assert after_links["verify"] == "accepted"
    assert after_links["data_gap_verify"] == "accepted"
    assert late_sleep["verify"] == "accepted"
    assert late_sleep["data_gap_verify"] == "accepted"
    assert (
        late_sleep["pressure_signal"]
        == "predicate_name_drift_blocks_narrative_framing_reuse"
    )

    coffee = by_name["coffee_latent_edge_gate"].details
    assert coffee["edge_kinds"] == ["bidirected"]
    assert coffee["blocked_by"] == "SemanticError"
    assert "bidirected edges is not yet supported" in coffee["message"]
    assert (
        coffee["pressure_signal"]
        == "admg_assoc_query_needs_scheduler_and_verifier_exposure"
    )
