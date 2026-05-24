"""Fix 5 (v0.1.5, audit follow-up) — Tian-in-effect dispatch wiring.

Yesterday's audit found that ``_dispatch_effect`` ADMG branch dropped
straight to ``needs_investigation`` when backdoor + front-door failed,
not even trying Tian / Shpitser ID — asymmetric with
``_dispatch_identify`` which DOES try Tian as last resort. This commit
wires the symmetric fallback.

Pure Tian-only ADMG cases (backdoor + front-door both STRUCTURALLY
fail but Tian succeeds) are exotic — in nearly every reasonable
ADMG, backdoor or front-door wins structurally. So the bulk of this
test file is wiring verification (helper unit + hedge regression)
rather than a positive end-to-end Tian-numeric showcase. The wiring
will activate transparently when a real Tian-only case surfaces.
"""
from __future__ import annotations

import networkx as nx

import themis
from themis.runtime.formula_builder import bind_target_value
from themis.types import (
    Atom,
    BindDecl,
    ConstTerm,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


def _a(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _va(atom: Atom, value=None) -> ValuedAtom:
    return ValuedAtom(atom=atom, value=value)


# ---------------------------------------------------------------------------
# bind_target_value walker — unit
# ---------------------------------------------------------------------------


def test_bind_target_value_replaces_outer_y_when_value_none():
    """The Tian formula returned by c_factor has Y target.value=None
    so an IdentifyQuery caller can use it. EffectQuery needs the
    concrete value bound; bind_target_value walks the tree and
    rebinds."""
    y, x = _a("y"), _a("x")
    f = ProbabilityRefExpr(target=_va(y, value=None), given=(_va(x, True),))
    bound = bind_target_value(f, y, True)
    assert isinstance(bound, ProbabilityRefExpr)
    assert bound.target.value is True
    assert bound.given == f.given  # unchanged


def test_bind_target_value_leaves_var_ref_bound_inner_atoms_alone():
    """Inner sum-bound Y appearances (target.value = VarRef from an
    enclosing SumExpr) must NOT be rebound — those are summation
    variables, not the outer query target."""
    y, x = _a("y"), _a("x")
    # Sum over Y with Y appearing as VarRef inside
    inner = ProbabilityRefExpr(
        target=_va(y, value=VarRef(name="t_y")),  # VarRef — inner bind
        given=(_va(x, True),),
    )
    f = SumExpr(bind=BindDecl(name="t_y"), over=y, body=inner)
    bound = bind_target_value(f, y, True)
    # Inner VarRef preserved
    inner_after = bound.body
    assert isinstance(inner_after, ProbabilityRefExpr)
    assert isinstance(inner_after.target.value, VarRef)
    assert inner_after.target.value.name == "t_y"


def test_bind_target_value_leaves_other_atoms_alone():
    """Only Y's target.value is rebound; X / Z atoms are untouched
    even if their target.value happens to be None."""
    y, x, z = _a("y"), _a("x"), _a("z")
    f = ProductExpr(terms=(
        ProbabilityRefExpr(target=_va(y, None), given=(_va(x, True),)),
        ProbabilityRefExpr(target=_va(z, None), given=(_va(x, True),)),
    ))
    bound = bind_target_value(f, y, True)
    y_term, z_term = bound.terms
    assert y_term.target.value is True   # Y rebound
    assert z_term.target.value is None   # Z untouched


def test_bind_target_value_preserves_population_tag():
    """Fix 3+4 interaction: when a ProbRef has population set, the
    rebind must preserve it (otherwise we'd accidentally route the
    bound query to the wrong theta partition)."""
    y, x = _a("y"), _a("x")
    f = ProbabilityRefExpr(
        target=_va(y, None),
        given=(_va(x, True),),
        population="rural_india",
    )
    bound = bind_target_value(f, y, True)
    assert bound.population == "rural_india"


# ---------------------------------------------------------------------------
# Hedge regression: Tian fallback doesn't escalate falsely
# ---------------------------------------------------------------------------


def _hedge_program() -> dict:
    """Classic bow arc: X → Y with X ↔ Y. Backdoor + front-door
    structurally fail (no observable Z to block the bidirected); Tian
    returns hedge (unidentifiable). Kernel must stay at
    needs_investigation — NOT escalate to numerically_solved /
    structurally_solved."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "bidirected", "left": atom("x"), "right": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def test_hedge_admg_effect_stays_needs_investigation():
    """Tian-in-effect must not escalate hedge cases to numerically_solved
    — when Tian itself returns identifiable=False (hedge witness), the
    kernel must fall through to needs_investigation just like before
    this fix."""
    out = themis.run(_hedge_program())
    r = out["results"][0]
    assert r["status"] == "needs_investigation"


# ---------------------------------------------------------------------------
# Backdoor-wins regression: Tian must not preempt simpler paths
# ---------------------------------------------------------------------------


def test_backdoor_admissible_admg_effect_still_uses_backdoor():
    """Disjoint-Y c-component (X→Z1→Y, X→Z2→Y, Z1↔Z2): ADMG backdoor
    is structurally trivial (X has no parents → empty adjustment
    works). Tian also identifies, but the kernel must take the SIMPLER
    path (backdoor) — Tian is the last-resort fallback only.

    Regression: a buggy Fix 5 might route through Tian even when
    backdoor wins. Derivation rule set is the canary.
    """
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    def gr(p, v): return {"atom": atom(p), "value": v}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z1", "domain": [True, False]},
            {"kind": "variable", "predicate": "z2", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("z1")},
            {"kind": "cause", "from": atom("x"), "to": atom("z2")},
            {"kind": "cause", "from": atom("z1"), "to": atom("y")},
            {"kind": "cause", "from": atom("z2"), "to": atom("y")},
            {"kind": "bidirected", "left": atom("z1"), "right": atom("z2")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": gr("y", True),
                "given": [],
            }},
        ],
    }
    out = themis.run(program)
    r = out["results"][0]
    # Backdoor wins structurally → formula is the backdoor adjustment
    # form P(Y|X) (empty adjustment, since X has no parents). The
    # final theta is incomplete (no P(Y|X) entry) so status drops to
    # needs_investigation BUT the formula proves backdoor was chosen,
    # not Tian. (Pre-existing _try_numeric quirk: on InsufficientTheta
    # the structural derivation prefix is dropped; orthogonal to Fix 5.)
    assert r["status"] in ("needs_investigation", "numerically_solved")
    formula = r.get("formula")
    assert formula is not None, "backdoor formula should be exposed"
    # Backdoor formula here: flat P(Y=true | X=true) since adjustment_set=()
    assert formula["kind"] == "probability_ref", (
        f"expected flat backdoor conditional; got {formula['kind']}"
    )
    assert formula["target"]["atom"]["predicate"] == "y"
    # Investigation requests should name the missing parameter, NOT
    # a Tian-specific failure — confirming backdoor was the chosen path.
    missing = r.get("missing_information", [])
    assert any(
        "y=" in m.get("name", "") and "x=" in m.get("name", "")
        for m in missing
    ), f"missing should name P(y|x); got {missing}"
