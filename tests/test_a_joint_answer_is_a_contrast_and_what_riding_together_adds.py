"""A joint intervention identified by the set-valued ID answers in the same
shape the joint back-door does: the contrast between two corners of the
treatment box, and the K-way interaction across all of them.

It used to answer with the contrast alone, and the reason was in the
representation rather than in the theory. An intervention is an ASSIGNMENT —
which atoms, and what each takes — and ``c_factor`` stored it as a set plus
ONE shared level. A set plus one level can only name a UNIFORM corner
``do(X=v for all X)``; every mixed corner ``do(A=1, B=0)`` was not
unimplemented but unsayable, and the K-way interaction is a finite difference
over 2^K corners of which 2^K − 2 are mixed.

Conformance latent SCM — K independent front doors, each with a latent
treatment↔outcome common cause, so no adjustment set exists::

    X_i → M_i → Y,  X_i ↔ Y   (i = 1..K)
    U_i ~ Bern(.5);  X_i: .85/.15 by U_i;  M_i: .9/.1 by X_i
    Y ~ Bern( c0 + Σ_i c_i·M_i + c_K·∏_i M_i + Σ_i d_i·U_i )

Every coefficient set below keeps that probability inside [0, 1] at every
cell. That is not tidiness: a Bernoulli draw silently clips a probability
past 1, so a mechanism that leaves the unit interval has an ORACLE that
disagrees with its own data, and the estimator gets blamed for the gap.

Because Y's mechanism is additive apart from the single top-order product
term, both oracles are closed forms rather than Monte Carlo::

    E[Y | do(x)] = c0 + Σ_i c_i·p_i(x_i) + c_K·∏_i p_i(x_i) + Σ_i d_i/2
    interaction  = c_K · ∏_i (p_i(hi) − p_i(lo))

with ``p_i(hi) = .9``, ``p_i(lo) = .1`` — so the K-way interaction is
``c_K · 0.8^K`` exactly, and a test that hits it is hitting a number nothing
in the estimator ever sees.
"""
from __future__ import annotations

import itertools

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.general_id import estimate_joint_general_id_ate
from themis.estimation.treatment_box import MAX_JOINT_TREATMENTS
from themis.input.syntactic_validator import validate_result
from themis.runtime import c_factor
from themis.types import Atom, ConstTerm
from themis.verifier import verify_joint_general_id_numeric
from themis.verifier.errors import VerificationError

P_HI, P_LO = 0.9, 0.1


def _typed(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# ============================================ the conformance SCM


def _frontdoor_graph(names):
    """X_i → M_i → Y with X_i ↔ Y — K front doors, K latent confounders."""
    g = nx.DiGraph()
    y = _typed("y")
    bidirected = set()
    for n in names:
        x, m = _typed(n), _typed(f"m{n}")
        g.add_edge(x, m)
        g.add_edge(m, y)
        bidirected.add(frozenset({x, y}))
    return g, frozenset(bidirected)


def _frontdoor_ast(names):
    stmts = []
    for v in list(names) + [f"m{n}" for n in names] + ["y"]:
        stmts.append({"kind": "variable", "predicate": v,
                      "domain": [True, False]})
    for n in names:
        stmts.append({"kind": "cause", "from": _atom(n), "to": _atom(f"m{n}")})
        stmts.append({"kind": "cause", "from": _atom(f"m{n}"),
                      "to": _atom("y")})
        stmts.append({"kind": "bidirected", "left": _atom(n),
                      "right": _atom("y")})
    stmts.append({"kind": "query", "id": "qj", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom(names[0]), "value": True},
        "extra_interventions": [
            {"atom": _atom(n), "value": True} for n in names[1:]],
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _risk(mediators, latents, *, base, main, top, conf):
    """Y's mechanism: additive but for the single top-order product term."""
    p = base + sum(c * m.astype(float) for c, m in zip(main, mediators))
    prod = np.ones(len(mediators[0]), dtype=float)
    for m in mediators:
        prod = prod * m.astype(float)
    p = p + top * prod
    for d, u in zip(conf, latents):
        p = p + d * u.astype(float)
    return p


def _draw(names, *, n, seed, base, main, top, conf):
    rng = np.random.default_rng(seed)
    latents = [rng.random(n) < 0.5 for _ in names]
    treatments = [rng.random(n) < np.where(u, 0.85, 0.15) for u in latents]
    mediators = [rng.random(n) < np.where(t, P_HI, P_LO) for t in treatments]
    p = _risk(mediators, latents,
              base=base, main=main, top=top, conf=conf)
    assert p.min() >= 0.0 and p.max() <= 1.0, (p.min(), p.max())
    y = rng.random(n) < p
    frame = {"y": y}
    for name, t, m in zip(names, treatments, mediators):
        frame[name] = t
        frame[f"m{name}"] = m
    return pd.DataFrame(frame)


def _oracle_corner(mask, *, base, main, top, conf):
    """``E[Y | do(corner)]`` in closed form — the mediators are independent
    given the intervention, so the product term factors."""
    ps = [P_HI if hi else P_LO for hi in mask]
    return (base + sum(c * p for c, p in zip(main, ps))
            + top * float(np.prod(ps)) + sum(d * 0.5 for d in conf))


def _oracle_interaction(k, *, top):
    """``c_K · ∏_i (p_i(hi) − p_i(lo))`` — every lower-order term is
    annihilated by the alternating sum."""
    return top * (P_HI - P_LO) ** k


#: K=2, with a genuine two-way interaction. A zero oracle would not tell a
#: computed interaction from a returned constant, so this one is 0.16.
_TWO = dict(base=0.05, main=(0.15, 0.12), top=0.25, conf=(0.10, 0.08))
#: The same DGP with the product term removed: the interaction is exactly 0,
#: and an estimator that invented one would be caught here rather than by
#: the sign of a number it happened to get right.
_TWO_ADDITIVE = dict(_TWO, top=0.0)
#: K=3, with a genuine THREE-way interaction (0.2 · 0.8³ = 0.1024). The
#: pairwise structure is absent, so this isolates the top order.
_THREE = dict(base=0.05, main=(0.10, 0.09, 0.08), top=0.20,
              conf=(0.08, 0.07, 0.06))


# ============================================ the interaction is the answer


def test_the_two_way_interaction_hits_its_closed_form():
    """K=2 against a latent-SCM oracle nothing in the estimator can see.

    The contrast was reachable before; the interaction was not, because
    ``do(a=1, b=0)`` had no way to be said.
    """
    names = ("a", "b")
    ast = _frontdoor_ast(names)
    df = _draw(names, n=300_000, seed=1, **_TWO)
    r = themis.estimate(ast, df, ci_bootstrap=40, random_state=1)["results"][0]
    assert r["status"] == "numerically_solved", r
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_general_id_plugin"

    joint = ne["joint_effect"]
    want_joint = (_oracle_corner((True, True), **_TWO)
                  - _oracle_corner((False, False), **_TWO))
    assert abs(joint["point"] - want_joint) < 0.02, (joint["point"], want_joint)
    assert joint["ci_lower"] <= joint["point"] <= joint["ci_upper"]

    inter = ne["interaction"]
    want_inter = _oracle_interaction(2, top=_TWO["top"])
    assert abs(inter["point"] - want_inter) < 0.02, (inter["point"], want_inter)
    assert inter["order"] == 2 and inter["scale"] == "difference"
    assert inter["ci_lower"] <= inter["point"] <= inter["ci_upper"]

    validate_result(r)
    themis.verify(ast, r)


def test_an_additive_mechanism_has_no_interaction_to_find():
    """The same graph with the product term removed. The interaction is 0
    exactly, and the estimate has to say so rather than report the residue
    of whatever it did instead."""
    names = ("a", "b")
    df = _draw(names, n=300_000, seed=2, **_TWO_ADDITIVE)
    g, bi = _frontdoor_graph(names)
    est = estimate_joint_general_id_ate(
        df, graph=g, bidirected=bi,
        treatment_atoms=tuple(_typed(n) for n in names),
        outcome_atom=_typed("y"), ci_bootstrap=0,
    )
    assert abs(est.interaction_point) < 0.02, est.interaction_point
    # And the contrast is emphatically not zero, so "≈0" above is a fact
    # about the interaction rather than about the whole estimate.
    want_joint = (_oracle_corner((True, True), **_TWO_ADDITIVE)
                  - _oracle_corner((False, False), **_TWO_ADDITIVE))
    assert abs(est.joint_point - want_joint) < 0.02


def test_the_three_way_interaction_is_not_the_two_way_one_repeated():
    """K=3 isolates the TOP order: the mechanism has a triple product and no
    pairwise terms, so the 3rd finite difference is 0.2·0.8³ while every
    pairwise interaction in it is zero."""
    names = ("a", "b", "c")
    df = _draw(names, n=600_000, seed=3, **_THREE)
    g, bi = _frontdoor_graph(names)
    est = estimate_joint_general_id_ate(
        df, graph=g, bidirected=bi,
        treatment_atoms=tuple(_typed(n) for n in names),
        outcome_atom=_typed("y"), ci_bootstrap=0,
    )
    want = _oracle_interaction(3, top=_THREE["top"])
    assert abs(est.interaction_point - want) < 0.02, (
        est.interaction_point, want)
    assert len(est.corner_risks) == 8


def test_every_corner_of_the_box_is_evaluated_and_two_of_them_are_mixed():
    """The box is what the interaction is built from, so the box is what the
    envelope carries. Each corner is checked against its own closed form —
    and two of the four are the mixed corners the old representation could
    not name at all."""
    names = ("a", "b")
    df = _draw(names, n=300_000, seed=4, **_TWO)
    g, bi = _frontdoor_graph(names)
    est = estimate_joint_general_id_ate(
        df, graph=g, bidirected=bi,
        treatment_atoms=tuple(_typed(n) for n in names),
        outcome_atom=_typed("y"), ci_bootstrap=0,
    )
    got = {tuple(v for _, v in c.cell): c.risk for c in est.corner_risks}
    assert set(got) == set(itertools.product((True, False), repeat=2))
    for mask, risk in got.items():
        want = _oracle_corner(mask, **_TWO)
        assert abs(risk - want) < 0.02, (mask, risk, want)
    mixed = {(True, False), (False, True)}
    assert mixed <= set(got)


# ============================================ the representation itself


def test_a_mixed_corner_is_expressible_and_differs_where_it_should():
    """The discriminating witness for the representation change: the mixed
    corner is a call that can be MADE, and its estimand differs from the
    uniform one in exactly the do-literal that differs.

    Under the old signature — a treatment SET plus one shared level — the
    first of these two calls could not be written down.
    """
    names = ("a", "b")
    g, bi = _frontdoor_graph(names)
    a, b, y = _typed("a"), _typed("b"), _typed("y")

    mixed = c_factor.identify_via_tian_joint(g, bi, {a: True, b: False}, y)
    uniform = c_factor.identify_via_tian_joint(g, bi, {a: True, b: True}, y)
    assert mixed.identifiable and uniform.identifiable
    assert mixed.formula is not None and uniform.formula is not None
    assert mixed.formula != uniform.formula

    from themis.output import formula_text
    from themis.verifier.serialization import _formula_to_dict

    said = {name: formula_text.render(_formula_to_dict(res.formula))
            for name, res in (("mixed", mixed), ("uniform", uniform))}
    # b's mediator is conditioned on b's OWN level, and only that changes.
    assert "P(mb | ¬b)" in said["mixed"]
    assert "P(mb | b)" in said["uniform"]
    assert said["mixed"].replace("P(mb | ¬b)", "P(mb | b)") == said["uniform"]


def test_one_treatment_is_the_assignment_of_size_one():
    """The single-treatment entry point is the |X|=1 case of the joint one,
    not a separate algorithm: on a graph the compact shortcut expresses,
    both produce the same estimand."""
    g, bi = _frontdoor_graph(("a",))
    a, y = _typed("a"), _typed("y")
    single = c_factor.identify_via_tian(g, bi, a, y, True)
    joint = c_factor.identify_via_tian_joint(g, bi, {a: True}, y)
    assert single.identifiable and joint.identifiable
    assert single.formula == joint.formula


# ============================================ withholding, with a species


def _shared_mediator():
    """``A → M ← B, M → Y, M ↔ Y`` — a shared mediator confounded with the
    outcome. The set-valued ID gives ``Σ_m P(m | a, b) · P(y | a, b, m)``,
    whose every factor is read at the corner's OWN cell.

    That separability is why this graph and not the K front doors: there the
    estimand carries ``Σ_a' Σ_b' P(a')·P(b')·P(y | a', b', m)``, a term
    identical across corners, so a cell it needs is a cell EVERY corner needs
    and the contrast falls with the interaction. Corner support is a property
    of the estimand's shape, not of the box.
    """
    g = nx.DiGraph()
    g.add_edges_from([(_typed("a"), _typed("m")), (_typed("b"), _typed("m")),
                      (_typed("m"), _typed("y"))])
    return g, frozenset({frozenset({_typed("m"), _typed("y")})})


def _never_apart(n=8000, seed=0, together=True):
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    a = rng.random(n) < np.where(u, 0.85, 0.15)
    b = a.copy() if together else (rng.random(n) < 0.5)
    um = rng.random(n) < 0.5
    m = rng.random(n) < (0.05 + 0.35 * a + 0.35 * b + 0.2 * um)
    y = rng.random(n) < (0.05 + 0.4 * m + 0.15 * u + 0.2 * um)
    return pd.DataFrame({"a": a, "b": b, "m": m, "y": y})


@pytest.mark.parametrize("together", [False, True])
def test_an_empty_corner_withholds_the_interaction_and_names_which(together):
    """A and B moving together leaves the two mixed corners with no rows.
    The contrast's own corners are observed, so it stands; the interaction
    is withheld under the species that says the box WAS walked and came up
    short, and names the cells it came up short on.

    The pair is the point: when the same DGP lets A and B vary apart, all
    four corners are there and the interaction is reported — so the withheld
    case is the estimator finding an empty cell rather than a route that
    never produces an interaction.

    Estimator-level rather than end to end, and that is a fact about the
    graph: an estimand separable enough for one corner to fail alone has no
    unblockable back-door path either, so dispatch reaches the adjustment
    route first and answers there. The species itself crosses to the reader
    from that route, which ``test_joint_k_treatment`` holds.
    """
    g, bi = _shared_mediator()
    est = estimate_joint_general_id_ate(
        _never_apart(together=together), graph=g, bidirected=bi,
        treatment_atoms=(_typed("a"), _typed("b")),
        outcome_atom=_typed("y"), ci_bootstrap=0,
    )
    assert isinstance(est.joint_point, float)
    if not together:
        assert est.interaction_point is not None
        assert est.interaction_unavailable is None
        assert len(est.corner_risks) == 4
        return
    assert est.interaction_point is None
    assert est.interaction_unavailable == "corner_unsupported"
    assert est.interaction_cap is None
    assert [dict(c) for c in est.interaction_unsupported_cells] == [
        {"a": True, "b": False}, {"a": False, "b": True},
    ]
    # The two that stand are exactly the contrast's own.
    assert {tuple(v for _, v in c.cell) for c in est.corner_risks} == {
        (True, True), (False, False)}


def test_a_withheld_interaction_is_a_block_the_audit_accepts():
    """The counterpart to the forged excuses below: a ``corner_unsupported``
    block naming exactly the corners the box is missing has to pass, or the
    three rejections would only be telling us the rule rejects everything."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    del ne["interaction"]
    ne["corner_risks"] = [c for c in ne["corner_risks"]
                          if c["cell"]["a"] == c["cell"]["b"]]
    ne["interaction_unavailable"] = {
        "kind": "corner_unsupported", "order": 2,
        "unsupported_cells": [{"a": True, "b": False}, {"a": False, "b": True}],
    }
    verify_joint_general_id_numeric(ne)
    validate_result(r)


def _plain_dag(names):
    """X_1..X_K → Y with nothing latent: the set-valued ID identifies
    ``P(y | do(x))`` as ``P(y | x)``, which makes the box affordable at K
    large enough to reach the enumeration cap."""
    g = nx.DiGraph()
    y = _typed("y")
    for n in names:
        g.add_edge(_typed(n), y)
    return g, frozenset()


def _plain_draw(names, n=8000, seed=0):
    rng = np.random.default_rng(seed)
    cols = {name: rng.random(n) < 0.5 for name in names}
    p = 0.2 + 0.5 * np.mean([c.astype(float) for c in cols.values()], axis=0)
    cols["y"] = rng.random(n) < p
    return pd.DataFrame(cols)


@pytest.mark.parametrize("k", [MAX_JOINT_TREATMENTS,
                               MAX_JOINT_TREATMENTS + 1])
def test_the_cap_withholds_the_interaction_and_never_the_contrast(k):
    """At the cap the box is walked and the interaction is reported; one
    treatment past it, the walk is not taken and the interaction says so —
    while the contrast, which needs two corners however wide the box is,
    comes back either way.

    The pair is the point: a cap that refused the whole estimate, or one
    that silently reported nothing, would each pass half of this.
    """
    names = tuple("abcdefg"[:k])
    df = _plain_draw(names)
    g, bi = _plain_dag(names)
    est = estimate_joint_general_id_ate(
        df, graph=g, bidirected=bi,
        treatment_atoms=tuple(_typed(n) for n in names),
        outcome_atom=_typed("y"), ci_bootstrap=0,
    )
    assert isinstance(est.joint_point, float)
    if k <= MAX_JOINT_TREATMENTS:
        assert est.interaction_point is not None
        assert est.interaction_unavailable is None
        assert len(est.corner_risks) == 2 ** k
    else:
        assert est.interaction_point is None
        assert est.interaction_unavailable == "order_above_cap"
        assert est.interaction_cap == MAX_JOINT_TREATMENTS
        # Only the contrast's own corners were ever identified.
        assert len(est.corner_risks) == 2
        assert est.interaction_unsupported_cells == ()


# ============================================ the audit re-derives, not re-reads


def _answered(seed=5):
    names = ("a", "b")
    ast = _frontdoor_ast(names)
    df = _draw(names, n=120_000, seed=seed, **_TWO)
    r = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)["results"][0]
    return ast, r


def test_the_audit_recomputes_both_numbers_from_the_recorded_corners():
    ast, r = _answered()
    ne = r["numeric_estimate"]
    risks = {tuple(c["cell"][t] for t in ne["treatments"]): c["risk"]
             for c in ne["corner_risks"]}
    assert ne["joint_effect"]["point"] == pytest.approx(
        risks[(True, True)] - risks[(False, False)])
    alternating = sum(
        (-1.0 if sum(1 for v in key if not v) % 2 else 1.0) * risk
        for key, risk in risks.items())
    assert ne["interaction"]["point"] == pytest.approx(alternating)
    verify_joint_general_id_numeric(ne)


@pytest.mark.parametrize("tamper", ["contrast", "interaction", "a_corner"])
def test_a_number_that_no_longer_follows_from_the_corners_is_rejected(tamper):
    """Each tamper leaves the block internally plausible — a number inside
    its own interval — and each stops following from the box the same result
    reports. That gap is what the corner risks exist to close."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    if tamper == "contrast":
        ne["joint_effect"]["point"] += 0.05
    elif tamper == "interaction":
        ne["interaction"]["point"] += 0.05
    else:
        ne["corner_risks"][1]["risk"] = min(
            1.0, ne["corner_risks"][1]["risk"] + 0.05)
    with pytest.raises(VerificationError):
        verify_joint_general_id_numeric(ne)


def test_an_interaction_over_an_incomplete_box_is_rejected():
    """The K-way interaction is a difference over ALL 2^K corners. A block
    reporting one while recording fewer is claiming a quantity it did not
    have the corners for."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    ne["corner_risks"] = ne["corner_risks"][:3]
    with pytest.raises(VerificationError):
        verify_joint_general_id_numeric(ne)


def test_the_two_slots_are_exclusive():
    """One says the number, the other says why there is none. A block
    holding both has not decided which it is."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    ne["interaction_unavailable"] = {"kind": "order_above_cap", "order": 2,
                                     "cap": MAX_JOINT_TREATMENTS}
    with pytest.raises(VerificationError):
        verify_joint_general_id_numeric(ne)


def test_a_forged_cap_excuse_is_rejected():
    """``order_above_cap`` is a claim about K, and K is on the same block.
    Two treatments are not past a cap of five."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    del ne["interaction"]
    ne["interaction_unavailable"] = {"kind": "order_above_cap", "order": 2,
                                     "cap": MAX_JOINT_TREATMENTS}
    with pytest.raises(VerificationError):
        verify_joint_general_id_numeric(ne)


def test_a_corner_claimed_unsupported_but_recorded_is_rejected():
    """``corner_unsupported`` names cells the estimator could not stand on.
    A cell that is in the recorded box was evaluable after all."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    del ne["interaction"]
    ne["corner_risks"] = ne["corner_risks"][:3]
    ne["interaction_unavailable"] = {
        "kind": "corner_unsupported", "order": 2,
        "unsupported_cells": [dict(ne["corner_risks"][0]["cell"])],
    }
    with pytest.raises(VerificationError):
        verify_joint_general_id_numeric(ne)


def test_the_derivation_terminal_demands_the_species_when_the_number_is_gone():
    """Absence has to be declared on the derivation too: a terminal that
    simply drops the interaction point looks exactly like one whose box was
    short."""
    ast, r = _answered()
    for st in r["derivation"]["steps"]:
        if st["rule"] == "numeric_joint_general_id_estimate":
            del st["inputs"]["interaction_point"]
    with pytest.raises(VerificationError):
        themis.verify(ast, r)


def test_the_terminal_is_the_joint_one_and_not_the_single_treatment_one():
    """Routing is on the derivation's terminal, so a joint answer has to
    reach it under its own rule — sharing the single-treatment terminal
    would make ``point`` and ``joint_point`` two spellings of one slot."""
    _ast, r = _answered()
    rules = [st["rule"] for st in r["derivation"]["steps"]]
    assert rules == ["general_id_criterion",
                     "numeric_joint_general_id_estimate"], rules


# ============================================ what the reader is handed


def test_the_report_says_the_interaction_and_both_ways_it_can_be_missing():
    from themis.output import analysis_report

    _ast, r = _answered()
    said = themis.build_analysis_report(r)
    assert "阶交互" in said

    for kind, expect in (("corner_unsupported", "站得住"),
                         ("order_above_cap", "枚举")):
        block = {"kind": kind, "order": 2,
                 "unsupported_cells": [{"a": True, "b": False}],
                 "cap": MAX_JOINT_TREATMENTS}
        line = analysis_report._interaction_missing(block, lang="zh")
        assert expect in line, (kind, line)
        # Both sentences carry both slots; the one the species does not use
        # has to be gone rather than standing there empty. (A cell renders
        # with braces of its own, so the check is on the slot NAMES.)
        assert "{cells}" not in line and "{cap}" not in line, line


def test_the_browser_holds_both_species():
    from tests import web_source

    table = web_source.words_map(
        "INTERACTION_UNAVAILABLE_WORDS",
        web_source.read(web_source.GENERATED))
    assert set(table) == {"corner_unsupported", "order_above_cap"}, table
    verdict = web_source.read(web_source.VERDICT)
    assert "interaction_unavailable_kind" in verdict
    assert "num.interaction_unavailable" in verdict


def test_the_shape_declared_is_the_shape_produced():
    """``themis.answers`` says what a method can answer in; this route said
    POINT while a contrast plus an interaction sat in the block."""
    from themis import answers

    _ast, r = _answered()
    ne = r["numeric_estimate"]
    assert answers.SHAPES_OF["joint_general_id_plugin"] == (
        answers.JOINT_CONTRAST,)
    assert answers.shape_of(ne) is answers.JOINT_CONTRAST
    assert "point" not in ne


def test_both_answers_carry_what_it_would_take_to_halve_them():
    """The schema has declared a precision budget inside both joint slots
    since the block existed, and neither joint route had ever filled one:
    the flat helper reads ``numeric_estimate.point``, which a contrast does
    not have."""
    _ast, r = _answered()
    ne = r["numeric_estimate"]
    for key in ("joint_effect", "interaction"):
        assert ne[key]["ci_lower"] is None or "precision_budget" in ne[key], key
