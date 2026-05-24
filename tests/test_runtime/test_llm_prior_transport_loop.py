"""Fix 3+4 — joint end-to-end tests: the LLM-mediated transport loop.

The user gives:
  - A DAG with S-nodes between source (literature) and target (user
    stratum)
  - Source's interventional conditional P(Y|X,Z) — from literature
  - NO target marginals — Z's distribution in target isn't observed

First themis.run:
  - Identification succeeds (Bareinboim Theorem 1)
  - Numeric evaluation FAILS at the P*(Z, target) factor
  - Stays structurally_solved with an investigation_request naming
    the specific (target-population) missing key

Second turn (apply_patch_and_run):
  - LLM proposes P*(Z) from common knowledge — patch bundle entries
    carry provenance='llm_prior' + non-empty annotations.source reason
  - kernel re-runs → numerically_solved
  - extensions.llm_proposed_review surfaces every llm_prior entry
    with its reason for the user to audit BEFORE trusting the answer

This is the canonical real-world Themis flow for cross-population
questions where target data isn't directly available — most everyday
LLM-Themis use cases.
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _grounded(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _source_only_program() -> dict:
    """Boston RCT → rural India transport setup. Source supplies
    P(Y|X,Z); target marginals deliberately omitted to force the
    Fix 3 propose-prior workflow."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {
                "kind": "selection_node",
                "id": "S_age",
                "affects": _atom("z"),
                "source_population": "boston_rct",
                "target_population": "rural_india",
            },
            # Source only: P(Y | X, Z, boston_rct)
            {
                "kind": "probability",
                "target": _grounded("y", True),
                "given": [_grounded("x", True),  _grounded("z", True)],
                "value": 0.40,
                "population": "boston_rct",
            },
            {
                "kind": "probability",
                "target": _grounded("y", True),
                "given": [_grounded("x", True),  _grounded("z", False)],
                "value": 0.70,
                "population": "boston_rct",
            },
            {
                "kind": "probability",
                "target": _grounded("y", True),
                "given": [_grounded("x", False), _grounded("z", True)],
                "value": 0.20,
                "population": "boston_rct",
            },
            {
                "kind": "probability",
                "target": _grounded("y", True),
                "given": [_grounded("x", False), _grounded("z", False)],
                "value": 0.50,
                "population": "boston_rct",
            },
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": _grounded("y", True),
                "given": [],
                "target_population": "rural_india",
            }},
        ],
    }


def _llm_prior_patch_bundle() -> dict:
    """Simulates the second-turn LLM patch: proposes P*(Z, rural_india)
    from common knowledge with a stated reason. Only K-1 of K supplied
    (true side); kernel's K-1 → K completion via probability axiom
    fills the false side automatically."""
    return {
        "kind": "parameter_fill_bundle",
        "version": "0.1",
        "skeletons": [
            {
                "kind": "probability",
                "target": _grounded("z", True),
                "given": [],
                "value": 0.65,
                "population": "rural_india",
                "provenance": "llm_prior",
                "annotations": {
                    "source": (
                        "Common knowledge: aging-population prevalence "
                        "estimate for rural Indian cohort, no specific "
                        "citation"
                    ),
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Round 1: kernel reports InsufficientTheta with target-population missing key
# ---------------------------------------------------------------------------


def test_round1_source_only_stays_structurally_solved():
    """No target marginals → kernel identifies transport structurally
    but can't evaluate; status stays structurally_solved."""
    out = themis.run(_source_only_program())
    result = out["results"][0]
    assert result["status"] == "structurally_solved"


def test_round1_investigation_request_names_target_population_key():
    """The investigation request must surface the specific missing
    target-population key so the agent knows what to propose."""
    out = themis.run(_source_only_program())
    result = out["results"][0]
    missing_info = result.get("missing_information", [])
    assert any(
        "rural_india" in m.get("name", "") for m in missing_info
    ), (
        f"missing_information should name the target population, "
        f"got {missing_info}"
    )


# ---------------------------------------------------------------------------
# Round 2: apply LLM-prior patch → numerically_solved + review surface
# ---------------------------------------------------------------------------


def test_round2_llm_prior_patch_upgrades_to_numerically_solved():
    """Applying the llm_prior patch closes the target marginal gap;
    transport formula evaluates end-to-end."""
    program = _source_only_program()
    patch = _llm_prior_patch_bundle()
    out = themis.apply_patch_and_run(program, [patch])
    result = out["results"][0]
    assert result["status"] == "numerically_solved", (
        f"expected numerically_solved after llm_prior patch, got "
        f"{result['status']}"
    )


def test_round2_numeric_value_matches_bareinboim_sum():
    """Σ_z P(Y=1|X=1,Z=z,source) · P*(Z=z,target) =
    0.40·0.65 + 0.70·0.35 = 0.505 (K-1 → K completion fills P*(Z=false))."""
    program = _source_only_program()
    out = themis.apply_patch_and_run(program, [_llm_prior_patch_bundle()])
    result = out["results"][0]
    expected = 0.40 * 0.65 + 0.70 * 0.35
    assert abs(result["numeric_result"]["value"] - expected) < 1e-9


def test_round2_review_surface_lists_llm_prior():
    """extensions.llm_proposed_review must enumerate the LLM-proposed
    P*(Z) entry with its reason — that's the audit-trail contract."""
    program = _source_only_program()
    out = themis.apply_patch_and_run(program, [_llm_prior_patch_bundle()])
    result = out["results"][0]
    review = result["extensions"]["llm_proposed_review"]
    assert "edges" in review and "probabilities" in review and "summary" in review

    probs = review["probabilities"]
    assert len(probs) == 1, f"expected 1 llm_prior entry, got {len(probs)}"
    entry = probs[0]
    assert entry["population"] == "rural_india"
    assert entry["value"] == 0.65
    # Reason must be non-empty and substantive (validator enforces).
    assert "common knowledge" in entry["reason"].lower()
    # Summary mentions counts for the user to ground the audit.
    assert "概率参数" in review["summary"] or "probability" in review["summary"].lower()


def test_round2_review_surface_skips_when_no_llm_tagged_elements():
    """The fully-supplied transport program (no llm_prior, no llm
    cause annotations) must NOT have llm_proposed_review in its
    extensions — keeps the audit surface signal-only (presence = a
    real audit obligation, absence = nothing to disclose)."""
    program = _source_only_program()
    # Supply target marginal as a regular structural entry instead of llm_prior
    regular_target = {
        "kind": "probability",
        "target": _grounded("z", True),
        "given": [],
        "value": 0.65,
        "population": "rural_india",
    }
    program["statements"].append(regular_target)
    out = themis.run(program)
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    review = (result.get("extensions") or {}).get("llm_proposed_review")
    assert review is None


def test_round2_verify_round_trip():
    """themis.verify accepts the full Fix 3+4 derivation with
    llm_prior entries in the merged program."""
    program = _source_only_program()
    out = themis.apply_patch_and_run(program, [_llm_prior_patch_bundle()])
    # Verify uses the merged_program returned by apply_patch_and_run.
    themis.verify(out["merged_program"], out["results"][0])


# ---------------------------------------------------------------------------
# llm_prior_requires_source semantic check
# ---------------------------------------------------------------------------


def test_llm_prior_without_source_rejected():
    """A probability statement with provenance='llm_prior' but empty /
    null annotations.source must be rejected at semantic-validation
    time. Empty source on llm_prior would let LLM silently launder
    fabricated numbers — direct contract violation."""
    import pytest

    program = _source_only_program()
    # Append an llm_prior statement WITHOUT annotations.source.
    program["statements"].append({
        "kind": "probability",
        "target": _grounded("z", True),
        "given": [],
        "value": 0.65,
        "population": "rural_india",
        "provenance": "llm_prior",
        # No "annotations" key at all.
    })
    from themis.input.semantic_validator import SemanticError
    with pytest.raises(SemanticError, match="llm_prior"):
        themis.run(program)


def test_llm_prior_with_empty_source_rejected():
    """Whitespace-only source counts as empty (validator strips before
    checking)."""
    import pytest

    program = _source_only_program()
    program["statements"].append({
        "kind": "probability",
        "target": _grounded("z", True),
        "given": [],
        "value": 0.65,
        "population": "rural_india",
        "provenance": "llm_prior",
        "annotations": {"source": "   "},  # whitespace-only
    })
    from themis.input.semantic_validator import SemanticError
    with pytest.raises(SemanticError, match="llm_prior"):
        themis.run(program)
