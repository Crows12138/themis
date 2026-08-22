"""Phase 14 slice a — dose-response estimator tests.

Skips when EconML is not installed (it's an optional dependency:
``pip install econml`` or ``pip install themis[estimator]``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.output.assumption_glossary import classify_assumption

try:
    import econml  # noqa: F401
    _ECONML_AVAILABLE = True
except ImportError:
    _ECONML_AVAILABLE = False


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dose_response_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query",
                 "description": "raise vs engagement curve"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "variable", "predicate": "engagement"},
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


def _synth_data(n: int = 400, slope: float = 0.5, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    raise_amount = rng.uniform(0.0, 10.0, size=n)
    noise = rng.normal(0.0, 1.0, size=n)
    engagement = 1.0 + slope * raise_amount + noise
    return pd.DataFrame({
        "raise_amount": raise_amount,
        "engagement": engagement,
    })


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_curve_attached_when_ambiguity_flagged():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    result = out["results"][0]
    assert "numeric_estimate" in result
    ne = result["numeric_estimate"]
    assert ne["method"] == "dose_response_linear_dml"
    assert "dose_response_curve" in ne
    curve = ne["dose_response_curve"]
    assert len(curve) >= 2
    # First point is the reference: effect should be 0
    assert curve[0]["effect"] == pytest.approx(0.0, abs=1e-9)
    # X values must be non-decreasing
    xs = [p["x"] for p in curve]
    assert xs == sorted(xs)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_recovers_linear_slope():
    """Synthetic data has slope 0.5; the curve at x=10 vs x≈0 should
    show an effect near 5.0 (loose tolerance — DML adds noise)."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(slope=0.5), model="linear",
    )
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    last = curve[-1]
    first = curve[0]
    # ΔY ≈ slope × Δx; with quantile sampling first ≈ 1.0, last ≈ 9.0
    expected = 0.5 * (last["x"] - first["x"])
    assert abs(last["effect"] - expected) < 1.5


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_assumptions_name_linearity():
    """The backend's shape choice is declared by id, and the sentence the
    reader gets for that id says the curve is a straight line in T.

    The declaration used to BE the sentence, written where the backend was
    chosen. One list then held ids and prose side by side, and the ledger
    could classify the ids and not the prose — so the prose came back as an
    unrecognised identification assumption, invalidating, beside the same
    fact filed correctly as a functional form."""
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    ne = out["results"][0]["numeric_estimate"]
    assert "linear_in_treatment_partially_linear_dml" in ne["assumptions"]
    said = classify_assumption("linear_in_treatment_partially_linear_dml")
    assert said["layer"] == "functional_form"
    assert "直线" in said["claim"]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_attaches_mechanism_audit():
    """Slice C: the functional form is surfaced as a first-class,
    provenance-tagged mechanism-audit element (parity with the edge /
    theta llm-proposed review), not just buried in ``assumptions[0]``."""
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    result = out["results"][0]
    audit = result["extensions"]["mechanism_audit"]
    mech = audit["mechanisms"][0]
    assert mech["form"] == "linear"
    assert mech["target"] == "engagement"
    assert mech["method"] == "dose_response_linear_dml"
    # The shape assumption is POINTED AT, by an id the estimator also
    # declared flat — so the ledger's one dedup, which is keyed on the id,
    # collapses the pair instead of disclosing it twice. The summary frames
    # it as load-bearing, which is what the reader must audit.
    #
    # ``model="linear"`` above: the caller named the shape, so the line says
    # so. It used to read "default" on the block and "inherent" on the ledger
    # line beside it — the attach point wrote a literal without asking the
    # estimate, and the line asked a table keyed on the id, which cannot know.
    # The answer sits ON the assumption because a family can make more than
    # one shape decision and they need not share an origin.
    assert mech["assumptions"] == [
        {"id": "linear_in_treatment_partially_linear_dml",
         "settled_by": "caller_asserted"},
    ]
    assert {str(a["id"]) for a in mech["assumptions"]} <= set(
        result["numeric_estimate"]["assumptions"])
    assert "审核" in audit["summary"]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_assumption_ledger_ranks_confounding_above_form():
    """Ledger slice: every load-bearing assumption (identification,
    LLM-proposed edge, functional form) aggregates into one
    severity-sorted ledger. The invalidating 'no unmeasured confounding'
    must rank above the merely-distorting functional form — fixing the
    prominence inversion that mechanism_audit alone introduced."""
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    result = out["results"][0]
    ledger = result["extensions"]["assumption_ledger"]
    entries = ledger["assumptions"]
    layers = [e["layer"] for e in entries]
    # all three layers present: identification + the LLM-proposed edge + form
    assert "identification" in layers
    assert "structural_edge" in layers
    assert "functional_form" in layers
    # sorted by severity — the first entry is invalidating
    assert entries[0]["severity"] == "invalidating"
    # no-confounding (identification) ranks above the functional form
    idx_conf = next(i for i, e in enumerate(entries) if e["layer"] == "identification")
    idx_form = next(i for i, e in enumerate(entries) if e["layer"] == "functional_form")
    assert idx_conf < idx_form
    # the LLM-proposed edge is surfaced as load-bearing, provenance kept
    edge = next(e for e in entries if e["layer"] == "structural_edge")
    assert edge["provenance"] == "llm_proposal"
    assert edge["severity"] == "invalidating"
    # functional form is present but only distorting (ranks below)
    form_entry = next(e for e in entries if e["layer"] == "functional_form")
    assert form_entry["severity"] == "distorting"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_ledger_excludes_non_load_bearing_edge():
    """The ledger sources structural edges from the load-bearing analysis
    (data_gap_report), not the flat proposed-edge list — so a proposed
    edge the answer never traverses does NOT show up as invalidating.
    That was the false alarm the flat list produced."""
    prog = _dose_response_program()
    # an extra LLM-proposed edge disconnected from the query path
    prog["statements"][0:0] = [
        {"kind": "variable", "predicate": "coffee"},
        {"kind": "variable", "predicate": "sleep_quality"},
        {"kind": "cause", "from": _atom("coffee"), "to": _atom("sleep_quality"),
         "annotations": {"source": "llm_proposal"}},
    ]
    # the disconnected vars need data columns to clear the data contract,
    # but they stay off the raise_amount -> engagement query path
    data = _synth_data()
    rng = np.random.default_rng(11)
    data["coffee"] = rng.normal(size=len(data))
    data["sleep_quality"] = rng.normal(size=len(data))
    out = themis.estimate(prog, data, model="linear")
    ledger = out["results"][0]["extensions"]["assumption_ledger"]
    claims = " ".join(e["claim"] for e in ledger["assumptions"])
    # the on-path edge is still surfaced as load-bearing ...
    assert "raise_amount" in claims and "engagement" in claims
    # ... but the off-path proposed edge never enters the ledger
    assert "coffee" not in claims and "sleep_quality" not in claims


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_status_flips_to_numerically_solved():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    assert out["results"][0]["status"] == "numerically_solved"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_drops_stale_data_required_gap_after_curve():
    """Once the curve is computed via EconML, the dose_response_data_required
    gap ("Themis 不算曲线（用 EconML / …）") is stale and self-contradictory —
    the reconciliation must drop it so it doesn't ship as blocking next to
    the curve. Real-usage probe 2026-06-16."""
    import json

    res = json.loads(json.dumps(
        themis.estimate(_dose_response_program(), _synth_data(slope=0.5),
                        model="linear")["results"][0]
    ))
    assert res["status"] == "numerically_solved"
    report = res["data_gap_report"]
    kinds = {g["kind"] for g in report["gaps"]}
    assert "dose_response_data_required" not in kinds
    assert report["answer_tier"] == "point"
    themis.verify_data_gap_report(res)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_uses_declared_domain_when_available():
    """When the treatment has a numeric domain, curve uses those exact
    points (not quantiles)."""
    program = _dose_response_program()
    # Replace raise_amount declaration with a discrete domain
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "raise_amount":
            stmt["domain"] = [0.0, 5.0, 10.0]
    out = themis.estimate(program, _synth_data(), model="linear")
    ne = out["results"][0]["numeric_estimate"]
    assert ne["sampling_points"] == [0.0, 5.0, 10.0]


# ---------- slice b: CausalForestDML backend ----------

def _nonlinear_synth(n: int = 600, seed: int = 11) -> pd.DataFrame:
    """Y = 1 + 0.4·T - 0.03·T² + noise — concave-down dose-response."""
    rng = np.random.default_rng(seed)
    raise_amount = rng.uniform(0.0, 10.0, size=n)
    noise = rng.normal(0.0, 0.5, size=n)
    engagement = 1.0 + 0.4 * raise_amount - 0.03 * raise_amount ** 2 + noise
    return pd.DataFrame({
        "raise_amount": raise_amount,
        "engagement": engagement,
    })


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_forest_backend_via_explicit_model_kwarg():
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(), model="forest",
    )
    ne = out["results"][0]["numeric_estimate"]
    assert ne["method"] == "dose_response_causal_forest_dml"
    assert "linear_in_treatment_with_nonparametric_nuisance" in ne["assumptions"]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_auto_picks_drlearner_when_n_large_and_enough_points():
    """slice b.2: 'auto' now prefers drlearner when n ≥ 200 and
    ≥ 3 sampling points — it's the only backend that recovers T-Y
    non-linearity, so the user's most likely intent is to get one."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=600), model="auto",
    )
    assert out["results"][0]["numeric_estimate"]["method"] == \
        "dose_response_linear_drlearner"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_auto_picks_linear_when_n_small():
    """n=80 < 200 → 'auto' resolves to linear (forest needs the
    sample size for honest splits to behave)."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(n=80), model="auto",
    )
    assert out["results"][0]["numeric_estimate"]["method"] == \
        "dose_response_linear_dml"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_forest_assumption_admits_t_linearity_limit():
    """Forest's nuisance-stage flexibility doesn't extend to the T-Y
    relationship — the final stage is still linear in T. Make sure the
    assumption text says so, so callers don't read the curve as
    non-linear evidence when it isn't."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(), model="forest",
    )
    ne = out["results"][0]["numeric_estimate"]
    assert "linear_in_treatment_with_nonparametric_nuisance" in ne["assumptions"]
    said = classify_assumption(
        "linear_in_treatment_with_nonparametric_nuisance")["claim"]
    assert "直线" in said and "没有" in said


# ---------- slice b.2: LinearDRLearner non-linear curve ----------

@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_drlearner_method_label_and_assumption():
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=600), model="drlearner",
    )
    ne = out["results"][0]["numeric_estimate"]
    assert ne["method"] == "dose_response_linear_drlearner"
    assert "dose_binned_and_effects_estimated_per_bin" in ne["assumptions"]
    said = classify_assumption(
        "dose_binned_and_effects_estimated_per_bin")["claim"]
    assert "档" in said and "非线性" in said


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_drlearner_recovers_concave_shape():
    """Truth: y = 1 + 0.4·T - 0.03·T². Concave-down with peak around
    T≈6.7. With n=800 and 5 sampling points covering [0, 10], the
    drlearner curve must show non-monotonic shape — peak should NOT
    be at the last sampling point."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=800), model="drlearner",
    )
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    effects = [p["effect"] for p in curve]
    peak_idx = effects.index(max(effects))
    assert peak_idx < len(effects) - 1, (
        f"drlearner should bend down at the high end, got monotone curve "
        f"{effects}"
    )


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_drlearner_reference_point_effect_zero():
    """First curve point is the reference bin — effect must be 0 by
    construction (it's compared to itself)."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=600), model="drlearner",
    )
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    assert curve[0]["effect"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_drlearner_overlap_failure_when_bin_empty():
    """If a sampling point falls in a region with no observations,
    its bin is empty after digitization → overlap_insufficient."""
    program = _dose_response_program()
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "raise_amount":
            stmt["domain"] = [0.0, 5.0, 100.0]  # 100 is far outside [0, 10]
    out = themis.estimate(program, _nonlinear_synth(n=600), model="drlearner")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "overlap_insufficient"


# ---------- slice c: structured failures ----------

@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_overlap_insufficient_when_constant_treatment():
    """Treatment with zero variance can't yield any dose-response;
    surface as overlap_insufficient, not a crash."""
    df = _synth_data()
    df["raise_amount"] = 5.0  # collapse to constant
    out = themis.estimate(_dose_response_program(), df, model="linear")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "overlap_insufficient"
    assert "没有变化" in failure["reason"] or "max == min" in failure["reason"]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_overlap_insufficient_when_sampling_point_in_gap():
    """Declared domain includes points outside the observed support;
    those points should fail with sparse_points details."""
    program = _dose_response_program()
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "raise_amount":
            # Observed data is uniform on [0, 10]. Declaring 100 forces
            # a sampling point that's nowhere near any observation.
            stmt["domain"] = [0.0, 5.0, 100.0]
    out = themis.estimate(program, _synth_data(), model="linear")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "overlap_insufficient"
    sparse = failure["details"]["sparse_points"]
    assert any(p["x"] == 100.0 for p in sparse)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_failure_type_field_present_on_all_paths():
    """Every estimator_failure block must carry failure_type so callers
    can branch on it without parsing the reason string."""
    df = _synth_data()
    df["raise_amount"] = 5.0
    out = themis.estimate(_dose_response_program(), df, model="linear")
    failure = out["results"][0]["estimator_failure"]
    # Four legal values: the two pre-fit checks measure the data
    # (overlap_insufficient on the treatment, outcome_does_not_vary on the
    # outcome), and the two backend species are what a fit that ran can do.
    assert failure["failure_type"] in {
        "overlap_insufficient", "outcome_does_not_vary",
        "convergence_failure", "unknown",
    }


# ---------- round-2 subagent-caught regressions ----------

@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_verify_roundtrip_for_dose_response_result():
    """Round-2 subagent caught: themis.verify rejected every dose-response
    result because (1) the schema didn't whitelist the new method names
    or curve fields, and (2) the verifier rule for numeric_backdoor_estimate
    hardcoded the legacy method enum, and (3) the data-gap kind whitelist
    didn't include dose_response_data_required. Without all three fixes
    the entire Phase 14 happy path violates the kernel audit contract."""
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    result = out["results"][0]
    # Must succeed — None means clean
    assert themis.verify(_dose_response_program(), result) is None


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_verify_roundtrip_for_drlearner_result():
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=600), model="drlearner",
    )
    assert themis.verify(_dose_response_program(), out["results"][0]) is None


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_curve_carries_per_point_precision_budget():
    """Each curve point with non-null CI bounds carries a
    precision_budget sub-field telling user n_to_halve_ci. Reference
    point (effect=0 by construction) typically has degenerate CI →
    helper silently skips; non-reference points should have it."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(), model="linear",
    )
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    pb_count = 0
    for point in curve:
        if point.get("ci_lower") is not None and point.get("ci_upper") is not None:
            if point["ci_lower"] != point["ci_upper"]:
                # Non-degenerate CI → expect precision_budget
                assert "precision_budget" in point, (
                    f"non-reference point x={point['x']} missing precision_budget"
                )
                pb_count += 1
    assert pb_count >= 1, "expected at least one curve point with precision_budget"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_uppercase_drlearner_is_honored_not_silently_demoted():
    """Round-2 subagent caught: model='DRLearner' (the natural casing
    matching EconML's class name LinearDRLearner) silently fell to
    'auto', then linear at small n. With normalization, casing typos
    are accepted explicitly."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(n=80), model="DRLearner",
    )
    ne = out["results"][0].get("numeric_estimate")
    failure = out["results"][0].get("estimator_failure")
    if ne is not None:
        assert ne["method"] == "dose_response_linear_drlearner"
    else:
        assert failure is not None  # structured failure is fine


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_unknown_model_string_raises_loudly():
    """Typos like 'forestdml' that don't normalize to a real backend
    should fail loudly, not silently demote to auto."""
    with pytest.raises(ValueError, match="unknown model"):
        themis.estimate(
            _dose_response_program(), _synth_data(), model="forestdml",
        )


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_whitespace_in_model_normalized():
    out = themis.estimate(
        _dose_response_program(), _synth_data(), model="  Linear  ",
    )
    assert out["results"][0]["numeric_estimate"]["method"] == \
        "dose_response_linear_dml"


# ---------- subagent-caught regressions (2026-04-28) ----------

@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_constant_outcome_fails_loudly_not_silently_zero():
    """Subagent caught: constant Y was producing all-zero curves with
    `numerically_solved` status — a confident false-negative. Must now
    surface as estimator_failure(outcome_does_not_vary).

    The species is a DATA refusal, and that is the whole of what this
    check found: it runs before anything is fitted, so nothing can have
    failed to converge. It said ``convergence_failure`` — a BACKEND
    species, which tells the reader nothing was decided about the data —
    while measuring the data and deciding about it.
    """
    df = _synth_data()
    df["engagement"] = 4.0  # collapse outcome
    out = themis.estimate(_dose_response_program(), df, model="linear")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "outcome_does_not_vary"
    assert failure["kind"] == "data"
    assert "engagement" in failure["reason"], failure["reason"]
    # Status must NOT have flipped to numerically_solved
    assert out["results"][0]["status"] != "numerically_solved"


def test_near_constant_outcome_uses_relative_variance_threshold():
    """A1: absolute std threshold leaked near-constant outcomes when
    std was just above 1e-9 on a normal outcome scale. Relative std/scale
    must reject the same degenerate fit before EconML runs."""
    df = _synth_data()
    rng = np.random.default_rng(123)
    df["engagement"] = 4.0 + rng.normal(0.0, 1e-8, size=len(df))

    out = themis.estimate(_dose_response_program(), df, model="linear")

    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "outcome_does_not_vary"
    details = failure["details"]
    assert details["outcome_relative_std"] < 1e-8
    assert "numeric_estimate" not in out["results"][0]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_explicit_drlearner_at_small_n_is_honored():
    """Subagent caught: 'drlearner' was missing from dispatch's
    whitelist — fell to 'auto', which at small n picks 'linear'. So
    asking for drlearner at n=80 silently produced linear results.
    With the fix, n=80 + model='drlearner' must reach drlearner OR
    fail loudly (here: bin-overlap failure since 80/5 bins = 16/bin
    is fine, so the call should succeed with drlearner method)."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(n=80), model="drlearner",
    )
    ne = out["results"][0].get("numeric_estimate")
    failure = out["results"][0].get("estimator_failure")
    # Either succeeded as drlearner, or failed structurally — but never
    # silently fell back to linear.
    if ne is not None:
        assert ne["method"] == "dose_response_linear_drlearner"
    else:
        assert failure is not None  # structured failure is acceptable


def test_dose_response_ambiguity_only_routes_first_effect_query():
    """Subagent caught: the program-level dose_response_query flag was
    bleeding onto every effect query. With the fix, multi-query
    programs with no explicit query_id only route the FIRST effect
    query through dose-response — others take the binary backdoor
    path."""
    program = _dose_response_program()
    # Add a second, unrelated effect query
    program["statements"].append({
        "kind": "variable", "predicate": "tenure",
    })
    program["statements"].append({
        "kind": "cause",
        "from": _atom("tenure"), "to": _atom("engagement"),
        "annotations": {"source": "llm_proposal"},
    })
    program["statements"].append({
        "kind": "query", "id": "q_tenure",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("tenure"), "value": True},
            "target": {"atom": _atom("engagement"), "value": 4},
            "given": [],
        },
    })
    df = _synth_data()
    df["tenure"] = (df["raise_amount"] > 5).astype(float)
    df["engagement"] = (df["engagement"] > df["engagement"].median()).astype(float)
    out = themis.estimate(program, df, model="linear")
    by_id = {r["query_id"]: r for r in out["results"]}
    # First query (q): dose-response. Second (q_tenure): binary or unset.
    q1_method = by_id["q"].get("numeric_estimate", {}).get("method", "")
    q2_method = by_id["q_tenure"].get("numeric_estimate", {}).get("method", "")
    assert "dose_response" in q1_method
    assert "dose_response" not in q2_method


def test_dose_response_ambiguity_with_explicit_query_id_targets_only_that():
    """When an ambiguity carries query_id, only that query gets the
    treatment — even if it's not the first effect query."""
    program = _dose_response_program()
    program["extensions"]["ambiguities"][0]["query_id"] = "q_tenure"
    program["statements"].append({
        "kind": "variable", "predicate": "tenure",
    })
    program["statements"].append({
        "kind": "cause",
        "from": _atom("tenure"), "to": _atom("engagement"),
        "annotations": {"source": "llm_proposal"},
    })
    program["statements"].append({
        "kind": "query", "id": "q_tenure",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("tenure"), "value": True},
            "target": {"atom": _atom("engagement"), "value": 4},
            "given": [],
        },
    })
    df = _synth_data()
    df["tenure"] = df["raise_amount"]  # tenure also continuous
    out = themis.estimate(program, df, model="linear")
    by_id = {r["query_id"]: r for r in out["results"]}
    q1_method = by_id["q"].get("numeric_estimate", {}).get("method", "")
    q_tenure_method = by_id["q_tenure"].get("numeric_estimate", {}).get(
        "method", "",
    )
    # Only q_tenure (named in query_id) should be dose-response now.
    assert "dose_response" not in q1_method
    assert "dose_response" in q_tenure_method


def test_dose_response_invalid_explicit_query_id_warns_not_silent():
    """A3: explicit query_id that points nowhere used to disappear.
    The estimator should leave the normal effect path alone but surface
    a data_contract_warning naming the bad query_id."""
    program = _dose_response_program()
    program["extensions"]["ambiguities"][0]["query_id"] = "no_such_query"
    df = _synth_data()
    df["raise_amount"] = df["raise_amount"] > 5.0
    df["engagement"] = df["engagement"] > df["engagement"].median()

    out = themis.estimate(program, df, model="linear")

    result = out["results"][0]
    warnings = result["estimation_context"]["data_contract_warnings"]
    assert any("no_such_query" in warning for warning in warnings)
    method = result.get("numeric_estimate", {}).get("method", "")
    assert "dose_response" not in method


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_implicit_dose_response_skips_leading_mediation_query():
    """A2: a leading mediation effect query must not consume an
    unqualified dose_response ambiguity. Route to the next plain effect
    query and emit a warning about the skip."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "curve"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "m"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "variable", "predicate": "engagement"},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("raise_amount"), "to": _atom("engagement")},
            {
                "kind": "query",
                "id": "q_med",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                    "mediator": _atom("m"),
                },
            },
            {
                "kind": "query",
                "id": "q_curve",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("raise_amount"), "value": True},
                    "target": {"atom": _atom("engagement"), "value": 4},
                    "given": [],
                },
            },
        ],
    }
    df = _synth_data(n=120)
    rng = np.random.default_rng(5)
    df["x"] = rng.random(len(df)) < 0.5
    df["m"] = rng.random(len(df)) < 0.5
    df["y"] = rng.random(len(df)) < 0.5

    out = themis.estimate(program, df, model="linear")

    by_id = {r["query_id"]: r for r in out["results"]}
    assert "dose_response" not in by_id["q_med"].get("numeric_estimate", {}).get(
        "method", "",
    )
    assert "dose_response" in by_id["q_curve"]["numeric_estimate"]["method"]
    warnings = by_id["q_curve"]["estimation_context"]["data_contract_warnings"]
    assert any("q_med" in warning and "q_curve" in warning for warning in warnings)


def test_no_effect_query_with_dose_response_ambiguity_warns_and_keeps_gap():
    """B2: if dose_response_query exists but there is no effect query,
    estimation must not be silent. The run layer already emits the
    dose_response_data_required gap; estimate adds a contract warning."""
    program = _dose_response_program()
    program["statements"] = [
        stmt for stmt in program["statements"]
        if stmt.get("kind") != "query"
    ]
    program["statements"].append({
        "kind": "query",
        "id": "q_cause",
        "query": {
            "kind": "cause",
            "from": _atom("raise_amount"),
            "to": _atom("engagement"),
        },
    })

    out = themis.estimate(program, _synth_data(n=80), model="linear")

    result = out["results"][0]
    gaps = result["data_gap_report"]["gaps"]
    assert any(gap["kind"] == "dose_response_data_required" for gap in gaps)
    warnings = result["estimation_context"]["data_contract_warnings"]
    assert any("没有任何 effect 查询" in warning for warning in warnings)


def test_bool_treatment_dose_response_falls_back_to_marked_binary_effect():
    """B3: bool T plus dose_response used to return an unmarked
    two-point curve. Prefer the binary effect estimator and mark the
    fallback explicitly."""
    df = _synth_data(n=200)
    rng = np.random.default_rng(33)
    df["raise_amount"] = rng.random(len(df)) < 0.5
    p = 0.2 + 0.4 * df["raise_amount"].astype(float)
    df["engagement"] = rng.random(len(df)) < p

    out = themis.estimate(_dose_response_program(), df, model="linear")

    result = out["results"][0]
    fallback = result.get("estimator_fallback")
    assert fallback is not None
    assert fallback["from"] == "dose_response"
    assert fallback["to"] == "binary_effect"
    method = result["numeric_estimate"]["method"]
    assert "dose_response" not in method
    warnings = result["estimation_context"]["data_contract_warnings"]
    assert any("二值" in warning for warning in warnings)


def test_no_dose_response_ambiguity_keeps_binary_path():
    """Without the ambiguity flag, dispatch must NOT route to the
    dose-response estimator — it falls through to the standard binary
    backdoor path. Used as a regression guard."""
    program = _dose_response_program()
    program.pop("extensions", None)
    # Force outcome to bool so the binary path can fit
    df = _synth_data()
    df["engagement"] = (df["engagement"] > df["engagement"].median())
    df["raise_amount"] = (df["raise_amount"] > 5.0)
    out = themis.estimate(program, df)
    ne = out["results"][0].get("numeric_estimate", {})
    assert ne.get("method") != "dose_response_linear_dml"


def test_missing_econml_surfaces_structured_error(monkeypatch):
    """If EconML isn't importable, dispatch attaches an
    ``estimator_dependency_missing`` block instead of crashing."""
    import sys
    # Hide econml from the import system for this test only
    real_econml = sys.modules.pop("econml", None)
    real_econml_dml = sys.modules.pop("econml.dml", None)
    monkeypatch.setitem(sys.modules, "econml", None)
    try:
        out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
        result = out["results"][0]
        # Either dependency-missing block is set, or the binary
        # fallback ran (also acceptable — both paths surface
        # structurally, neither crashes)
        if "estimator_dependency_missing" in result:
            block = result["estimator_dependency_missing"]
            assert block["package"] == "econml"
            assert "pip install" in block["install_hint"]
    finally:
        if real_econml is not None:
            sys.modules["econml"] = real_econml
        if real_econml_dml is not None:
            sys.modules["econml.dml"] = real_econml_dml
