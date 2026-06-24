"""Textbook-conformance suite: Themis's verdict on canonical graphs must match
the verdict STATED in the authoritative literature — the textbook is the
oracle, not our own re-derivation.

This guards against the failure mode that bit us in the adversarial round: a
plausible-but-wrong theory interpretation. Here the answer is whatever the
cited source says, full stop. Each case carries its citation.

Sources used so far:
- Tian & Shpitser (2009), "On Identifying Causal Effects", in *Heuristics,
  Probability and Causality: A Tribute to Judea Pearl* (downloaded:
  references/, faculty.sites.iastate.edu/jtian). Figure 1, Theorems 6/8/9.
- Pearl (2000) / Shpitser & Pearl (2006): the bow arc is the canonical
  un-identifiable hedge.

To extend: append a dict to CONFORMANCE_CASES with its source citation.
"""
from __future__ import annotations

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p: str) -> dict:
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a: str, b: str) -> dict:
    return {"kind": "cause", "from": _atom(a), "to": _atom(b),
            "annotations": {"source": "common_knowledge"}}


def _bi(a: str, b: str) -> dict:
    return {"kind": "bidirected", "left": _atom(a), "right": _atom(b),
            "annotations": {"source": "common_knowledge"}}


def _identify(target: str, intervention: str) -> dict:
    return {"kind": "query", "id": "id", "query": {
        "kind": "identify", "target": _atom(target),
        "intervention": {"atom": _atom(intervention), "value": True},
        "given": []}}


def _effect(target: str, intervention: str) -> dict:
    return {"kind": "query", "id": "eff", "query": {
        "kind": "effect",
        "target": {"atom": _atom(target), "value": True},
        "intervention": {"atom": _atom(intervention), "value": True},
        "given": []}}


def _program(nodes, edges, query) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [_var(n) for n in nodes] + list(edges) + [query],
    }


# ----------------------------------------------------------------- the cases

# Each case: name, source citation, program, and the textbook verdict.
CONFORMANCE_CASES = [
    {
        "name": "front_door_smoking_tar_cancer",
        "source": "Tian-Shpitser 2009, Fig 1(c) + Thm 8 (Pearl 1995 front-door)",
        # X=smoking → Z=tar → Y=cancer, with X↔Y (unobserved genotype U).
        "program": _program(
            ["smoking", "tar", "cancer"],
            [_cause("smoking", "tar"), _cause("tar", "cancer"),
             _bi("smoking", "cancer")],
            _identify("cancer", "smoking"),
        ),
        "identifiable": True,
        "pattern": "front_door",
        "set_key": "mediator_set",
        "set_predicates": {"tar"},
        # Thm 8 / Eq(12): estimand needs P(z|x), P(y|x,z), P(x).
        "effect_factors": {
            ("tar", frozenset({"smoking"})),
            ("cancer", frozenset({"smoking", "tar"})),
            ("smoking", frozenset()),
        },
    },
    {
        "name": "backdoor_confounded_treatment",
        "source": "Tian-Shpitser 2009, Thm 6 (Pearl 1995 back-door criterion)",
        # L confounds A→Y: L→A, L→Y, A→Y. Adjust for L.
        "program": _program(
            ["l", "a", "y"],
            [_cause("l", "a"), _cause("l", "y"), _cause("a", "y")],
            _identify("y", "a"),
        ),
        "identifiable": True,
        "pattern": "backdoor",
        "set_key": "adjustment_set",
        "set_predicates": {"l"},
        # Thm 6 / Eq(10): Σ_l P(y|a,l)P(l).
        "effect_factors": {
            ("y", frozenset({"a", "l"})),
            ("l", frozenset()),
        },
    },
    {
        "name": "m_bias_collider_not_a_confounder",
        "source": "Tian-Shpitser 2009, Thm 9 (Tian-Pearl 2002a): no bidirected "
                  "path X→children in G_An(Y); Z is not an ancestor of Y",
        # X→Y, X↔Z, Z↔Y. The only back-door is collider-blocked → identifiable.
        "program": _program(
            ["x", "z", "y"],
            [_cause("x", "y"), _bi("x", "z"), _bi("z", "y")],
            _identify("y", "x"),
        ),
        "identifiable": True,
        "pattern": "backdoor",
        "set_key": "adjustment_set",
        "set_predicates": set(),  # empty adjustment: P(y|do(x)) = P(y|x)
        "effect_factors": {("y", frozenset({"x"}))},
    },
    {
        "name": "bow_arc_unidentifiable_hedge",
        "source": "Pearl 2000 / Shpitser-Pearl 2006: the bow arc is the "
                  "canonical un-identifiable hedge",
        # X→Y, X↔Y. NOT identifiable.
        "program": _program(
            ["x", "y"],
            [_cause("x", "y"), _bi("x", "y")],
            _identify("y", "x"),
        ),
        "identifiable": False,
    },
]


def _ids(case):
    return case["name"]


def _factor_signatures(result: dict) -> set:
    sigs = set()
    for g in (result.get("data_gap_report") or {}).get("gaps", []):
        if g["kind"] != "missing_distribution":
            continue
        inner = g["description"].split("P(", 1)[1].rstrip(")")
        target_part, _, given_part = inner.partition("|")
        target_pred = target_part.split("=", 1)[0]
        given_preds = frozenset(
            tok.split("=", 1)[0] for tok in given_part.split(",") if tok
        )
        sigs.add((target_pred, given_preds))
    return sigs


@pytest.mark.parametrize("case", CONFORMANCE_CASES, ids=_ids)
def test_identify_verdict_matches_textbook(case):
    """Themis's identifiability verdict (and pattern + adjustment/mediator set)
    must match the cited source."""
    r = themis.run(case["program"])["results"][0]
    val = r["structural_result"]["value"]
    assert val is case["identifiable"], (
        f"{case['name']}: Themis says identifiable={val}, "
        f"{case['source']} says {case['identifiable']}"
    )
    # Independent verifier must accept the derivation either way.
    themis.verify(case["program"], r)

    if case["identifiable"]:
        ident = (r.get("extensions") or {}).get("identification") or {}
        assert ident.get("pattern") == case["pattern"], (
            f"{case['name']}: pattern {ident.get('pattern')} != {case['pattern']}"
        )
        labels = ident.get(case["set_key"], [])
        preds = {lbl.split("(", 1)[0] for lbl in labels}
        assert preds == case["set_predicates"], (
            f"{case['name']}: {case['set_key']} {preds} != {case['set_predicates']}"
        )


@pytest.mark.parametrize(
    "case", [c for c in CONFORMANCE_CASES if c.get("effect_factors")], ids=_ids,
)
def test_effect_data_gap_names_textbook_estimand_factors(case):
    """For identifiable cases, the effect query's data-gap report must name the
    exact distributions the textbook estimand is built from — no more, no
    less (modulo per-value cells)."""
    # swap the identify query for an effect query on the same graph
    prog = dict(case["program"])
    prog["statements"] = [
        s for s in prog["statements"] if s.get("kind") != "query"
    ]
    intervention = case["program"]["statements"][-1]["query"]["intervention"]["atom"]["predicate"]
    target = case["program"]["statements"][-1]["query"]["target"]["predicate"]
    prog["statements"].append(_effect(target, intervention))

    r = themis.run(prog)["results"][0]
    sigs = _factor_signatures(r)
    assert sigs == case["effect_factors"], (
        f"{case['name']}: data-gap factors {sigs} != textbook estimand "
        f"{case['effect_factors']} ({case['source']})"
    )
