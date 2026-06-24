"""Regression for C-D2: an effect query do(X)->Y where X has no directed
path to Y must report the *supplyable* estimand P(Y), not P(Y|X).

P(Y|X) is numerically equal to P(Y|do(X)) here (X ⊥ Y), but the semantic
validator rejects supplying P(Y|X) because X is not a parent of Y — so a
data-gap report that names P(Y|X) tells the user to collect a distribution
they are forbidden to provide. The fix drops the non-cause intervention from
the back-door conditional in both the producer and the independent verifier.
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _effect_program(statements_between: list[dict]) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            *statements_between,
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }


def _missing_distributions(result: dict) -> list[str]:
    return [
        g["description"]
        for g in (result.get("data_gap_report") or {}).get("gaps", [])
        if g["kind"] == "missing_distribution"
    ]


def test_no_path_effect_reports_marginal_not_conditional():
    """No edge X->Y: estimand and gap name P(Y), and P(Y) appears NOT
    conditioned on X (so the user can actually supply it)."""
    r = themis.run(_effect_program([]))["results"][0]
    # formula is a flat P(Y) with empty `given` (X dropped).
    assert r["formula"]["kind"] == "probability_ref"
    assert r["formula"]["given"] == []
    assert r["formula"]["target"]["atom"]["predicate"] == "y"
    # gap names the supplyable marginal, never P(y|x).
    md = _missing_distributions(r)
    assert any("P(y=True)" == d.removeprefix("缺概率分布 ") for d in md), md
    assert not any("|x" in d for d in md), md


def test_no_path_effect_resolves_from_marginal_and_verifies():
    """Supplying the marginal P(Y) the gap asked for resolves the query
    and the derivation passes the independent verifier."""
    prog = _effect_program([
        {"kind": "probability",
         "target": {"atom": _atom("y"), "value": True}, "given": [], "value": 0.3},
    ])
    r = themis.run(prog)["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == 0.3
    themis.verify(prog, r)  # must not raise


def test_confounder_without_direct_edge_also_drops_intervention():
    """C->X, C->Y, no X->Y: X still has no directed path to Y, so the
    back-door estimand must adjust for C but NOT condition on the non-cause
    X — i.e. Sigma_c P(y|c)P(c), never P(y|x,c)."""
    prog = _effect_program([
        {"kind": "variable", "predicate": "c", "domain": [True, False]},
        {"kind": "cause", "from": _atom("c"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
    ])
    r = themis.run(prog)["results"][0]
    md = _missing_distributions(r)
    # the outcome conditional must be P(y|c), not P(y|x,c).
    assert any("P(y=True|c=True)" in d for d in md), md
    assert not any("|x" in d for d in md), md


def test_direct_effect_still_conditions_on_intervention():
    """Guard against over-dropping: X->Y direct edge means X IS a cause,
    so the estimand keeps X in the conditional."""
    prog = _effect_program([
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
    ])
    r = themis.run(prog)["results"][0]
    md = _missing_distributions(r)
    assert any("P(y=True|x=True)" in d for d in md), md
