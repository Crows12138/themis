"""Regression for B1: the data-gap report must name EVERY distribution a
multi-factor estimand still needs, not only the first gap the fail-fast
evaluator happened to hit.

Before this fix a front-door effect with no data reported a single missing
distribution (the mediator model P(M|X)) and silently dropped the outcome
model P(Y|M,X) and the exposure marginal P(X) — a consumer collecting exactly
what the report named would gather a third of the requirement and believe the
gap was closed.

The fix keeps cells PRECISE (a partially-filled CPT still reports only the
missing entry, per ``test_missing_parameter_trace``), and respects the
evaluator's own fallbacks so a derivable factor is never reported missing.
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p: str) -> dict:
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _missing_gaps(result: dict) -> list[dict]:
    return [
        g for g in (result.get("data_gap_report") or {}).get("gaps", [])
        if g["kind"] == "missing_distribution"
    ]


def _factor_signatures(result: dict) -> set[tuple[str, frozenset[str]]]:
    """Reduce each missing-distribution gap to (target_pred, {given_preds})
    so a test can assert which *factors* are covered, value-agnostic."""
    sigs: set[tuple[str, frozenset[str]]] = set()
    for g in _missing_gaps(result):
        # description is '缺概率分布 P(target=val|g1=..,g2=..)'
        inner = g["description"].split("P(", 1)[1].rstrip(")")
        target_part, _, given_part = inner.partition("|")
        target_pred = target_part.split("=", 1)[0]
        given_preds = frozenset(
            tok.split("=", 1)[0] for tok in given_part.split(",") if tok
        )
        sigs.add((target_pred, given_preds))
    return sigs


def test_front_door_no_data_names_all_three_factors():
    """Front-door functional Σ_m P(m|x) Σ_x' P(y|m,x') P(x') needs three
    CPTs; all three must surface, not just P(tar|smoking)."""
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _var("smoking"), _var("tar"), _var("cancer"),
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("tar")},
            {"kind": "cause", "from": _atom("tar"), "to": _atom("cancer")},
            {"kind": "bidirected", "left": _atom("smoking"), "right": _atom("cancer")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("cancer"), "value": True},
                "intervention": {"atom": _atom("smoking"), "value": True},
                "given": []}},
        ],
    }
    sigs = _factor_signatures(themis.run(prog)["results"][0])
    assert ("cancer", frozenset({"smoking", "tar"})) in sigs   # outcome model
    assert ("tar", frozenset({"smoking"})) in sigs             # mediator model
    assert ("smoking", frozenset()) in sigs                    # exposure marginal


def test_backdoor_no_data_names_conditional_and_confounder_marginal():
    """Σ_z P(y|x,z) P(z) needs both the outcome conditional and the
    confounder marginal — the marginal used to be silently dropped."""
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _var("med"), _var("rec"), _var("sev"),
            {"kind": "cause", "from": _atom("sev"), "to": _atom("med")},
            {"kind": "cause", "from": _atom("sev"), "to": _atom("rec")},
            {"kind": "cause", "from": _atom("med"), "to": _atom("rec")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("rec"), "value": True},
                "intervention": {"atom": _atom("med"), "value": True},
                "given": []}},
        ],
    }
    sigs = _factor_signatures(themis.run(prog)["results"][0])
    assert ("rec", frozenset({"med", "sev"})) in sigs   # outcome conditional
    assert ("sev", frozenset()) in sigs                 # confounder marginal


def test_partial_fill_still_reports_only_the_missing_cell():
    """Completeness must not cost precision: when every factor of a CPT is
    present except one cell, the report names exactly that cell — not the
    whole table and not the already-supplied factors."""
    def gr(p, v):
        return {"atom": _atom(p), "value": v}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _var("x"), _var("y"), _var("z"),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            # full confounder marginal + one of the two outcome-conditional cells
            {"kind": "probability", "target": gr("z", True), "given": [], "value": 0.4},
            {"kind": "probability", "target": gr("z", False), "given": [], "value": 0.6},
            {"kind": "probability", "target": gr("y", True),
             "given": [gr("x", True), gr("z", True)], "value": 0.7},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": gr("y", True),
                "intervention": gr("x", True),
                "given": []}},
        ],
    }
    gaps = _missing_gaps(themis.run(prog)["results"][0])
    descs = [g["description"] for g in gaps]
    # exactly the one missing cell (z=False branch of the outcome conditional);
    # the supplied z=True cell and the full P(z) marginal are NOT reported.
    assert descs == ["缺概率分布 P(y=True|x=True,z=False)"], descs
