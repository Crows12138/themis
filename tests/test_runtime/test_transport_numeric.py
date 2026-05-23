"""Fix 3+4 §T9.2 — end-to-end transport numeric evaluation tests.

Drives full ``themis.run`` on transport programs (cross-population
EffectQuery with target_population set) and verifies the kernel
computes the Bareinboim formula numerically when both source and
target theta entries are supplied.

The headline scenario: Boston RCT (source) → rural India (target),
with age as the S-shifted adjustment variable. Both populations'
distributions are supplied; expected output is the standard
transport sum.

Without theta: stays structurally_solved (existing Phase 9 §T9.1
behaviour, regression-checked here).
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _grounded(p: str, value, population: str | None = None) -> dict:
    """ProbabilityStatement target/given dict shape (groundedAtom)."""
    return {"atom": _atom(p), "value": value}


def _prob(
    target_pred: str, target_v, given_pairs: list,
    value: float, population: str | None = None,
) -> dict:
    stmt: dict = {
        "kind": "probability",
        "target": _grounded(target_pred, target_v),
        "given": [_grounded(p, v) for p, v in given_pairs],
        "value": value,
    }
    if population is not None:
        stmt["population"] = population
    return stmt


def _boston_to_india_program(supply_target_marginals: bool) -> dict:
    """Source = boston_rct (P(Y|X,Z) supplied). Target = rural_india
    (P*(Z) supplied or omitted). DAG: Z → X, Z → Y, X → Y. Z is age
    cohort; the S-node lives on age (mechanism differs between source
    and target populations)."""
    statements: list = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        # DAG: Z confounds X→Y in source; Z's distribution shifts in
        # target (S-node on Z).
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
        # Source: P(Y | X, Z, source)
        _prob("y", True, [("x", True),  ("z", True)],  0.40, "boston_rct"),
        _prob("y", True, [("x", True),  ("z", False)], 0.70, "boston_rct"),
        _prob("y", True, [("x", False), ("z", True)],  0.20, "boston_rct"),
        _prob("y", True, [("x", False), ("z", False)], 0.50, "boston_rct"),
    ]
    if supply_target_marginals:
        # Target: P*(Z, rural_india) — only true side; K-1 → K
        # auto-completion fills the false side.
        statements.append(_prob("z", True, [], 0.65, "rural_india"))

    statements.append({
        "kind": "query", "id": "q1", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
            "target_population": "rural_india",
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ---------------------------------------------------------------------------
# Numeric success path
# ---------------------------------------------------------------------------


def test_transport_with_complete_theta_resolves_numerically():
    """Both populations' entries supplied → status upgrades from
    structurally_solved to numerically_solved (Fix 3+4 §T9.2)."""
    out = themis.run(_boston_to_india_program(supply_target_marginals=True))
    result = out["results"][0]
    assert result["status"] == "numerically_solved", (
        f"expected numerically_solved, got {result['status']}"
    )


def test_transport_numeric_value_is_bareinboim_sum():
    """The numeric output equals Σ_z P(Y=1|X=1,Z=z,source) · P*(Z=z,target).

    Source: P(Y=1|X=1,Z=1)=0.40, P(Y=1|X=1,Z=0)=0.70
    Target: P*(Z=1)=0.65, P*(Z=0)=0.35 (via K-1 → K completion)
    Expected: 0.40·0.65 + 0.70·0.35 = 0.26 + 0.245 = 0.505
    """
    out = themis.run(_boston_to_india_program(supply_target_marginals=True))
    result = out["results"][0]
    expected = 0.40 * 0.65 + 0.70 * 0.35
    assert abs(result["numeric_result"]["value"] - expected) < 1e-9, (
        f"transport numeric expected {expected}, got "
        f"{result['numeric_result']['value']}"
    )


def test_transport_extensions_block_carries_numeric():
    """extensions.transport_identification.numeric exposes the value
    plus population labels for downstream renderers (matches
    mediation_decomposition.numeric pattern)."""
    out = themis.run(_boston_to_india_program(supply_target_marginals=True))
    ext = out["results"][0]["extensions"]["transport_identification"]
    assert "numeric" in ext
    assert ext["numeric"]["source_population"] == "boston_rct"
    assert ext["numeric"]["target_population"] == "rural_india"
    assert "value" in ext["numeric"]


# ---------------------------------------------------------------------------
# Theta-incomplete fallback path
# ---------------------------------------------------------------------------


def test_transport_without_target_marginals_stays_structurally_solved():
    """Source theta only, no target marginals → kernel cannot evaluate
    the outer Σ_z P*(Z=z, target) sum → stays structurally_solved
    with a specific missing-key investigation request naming the
    target-population key."""
    out = themis.run(_boston_to_india_program(supply_target_marginals=False))
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    # Investigation request must surface the missing target-population key
    requests = result.get("investigation_requests", [])
    assert len(requests) >= 1, (
        "expected an investigation_request naming the missing target P*(Z)"
    )
    # The missing key string should include 'rural_india' or 'target'
    missing_info = result.get("missing_information", [])
    assert any(
        "rural_india" in m.get("name", "") for m in missing_info
    ), (
        f"missing_information should name the target population key, got "
        f"{missing_info}"
    )


# ---------------------------------------------------------------------------
# Verifier round-trip
# ---------------------------------------------------------------------------


def test_transport_numeric_themis_verify_round_trip():
    """The independent verifier must accept the full transport numeric
    derivation: identify_via_transport as identification witness +
    formula_evaluation + numeric_result closing chain."""
    program = _boston_to_india_program(supply_target_marginals=True)
    out = themis.run(program)
    themis.verify(program, out["results"][0])
