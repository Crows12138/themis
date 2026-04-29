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
    exercise_unmatched = {
        item["source_predicate"]: item
        for item in exercise["link_diagnostic"]["unmatched"]
    }
    assert set(exercise_unmatched) == {"waist_reduced"}
    assert (
        exercise_unmatched["waist_reduced"]["candidates"][0]["target_predicate"]
        == "belly_fat_loss"
    )
    assert exercise_unmatched["waist_reduced"]["candidates"][0]["score"] < 0.5
    exercise_after_links = exercise["after_confirmed_links"]
    assert exercise_after_links["introduced_predicates"] == []
    assert exercise_after_links["framing_gaps"]["belly_fat_loss"] == [
        "direction",
        "baseline",
        "state_vs_event",
    ]
    assert "missing_distribution" in exercise_after_links["data_gap_kinds"]
    assert exercise_after_links["data_gap_verify"] == "accepted"
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

    late_sleep_edges = by_name["late_sleep_predicate_links_rewrite_edges"].details
    assert late_sleep_edges["edge_pairs"] == [
        ["stays_up_late", "feels_tired_next_morning"],
    ]
    assert "alias" in late_sleep_edges["ambiguity_kinds"]
    assert late_sleep_edges["result_status"] == "structurally_solved"
    assert late_sleep_edges["structural_value"] is True
    assert late_sleep_edges["verify"] == "accepted"
    assert late_sleep_edges["data_gap_verify"] == "accepted"
    assert (
        late_sleep_edges["pressure_signal"]
        == "confirmed_predicate_links_rewrite_edge_endpoints"
    )

    coffee = by_name["coffee_latent_edge_assoc"].details
    assert coffee["edge_kinds"] == ["bidirected"]
    assert "admg_unobserved_common_cause" in coffee["ambiguity_kinds"]
    assert coffee["result_status"] == "structurally_solved"
    assert coffee["structural_value"] is True
    assert coffee["witness_rule"] == "m_connection_witness"
    assert coffee["verify"] == "accepted"
    assert coffee["data_gap_verify"] == "accepted"
    assert (
        coffee["pressure_signal"]
        == "admg_assoc_query_now_uses_m_connection_witness"
    )

    ice_cream = by_name["ice_cream_refusal_filters_edge"].details
    assert ice_cream["edge_kinds_after_refusal"] == []
    assert "confounder_refusal" in ice_cream["ambiguity_kinds"]
    assert ice_cream["result_status"] == "structurally_solved"
    assert ice_cream["structural_value"] is False
    assert ice_cream["verify"] == "accepted"
    assert ice_cream["data_gap_verify"] == "accepted"
    assert (
        ice_cream["pressure_signal"]
        == "narrative_refusal_filters_question_side_naive_edge"
    )
