"""The bidirected gate's question, and the answers it now has to be given.

The gate used to name the kinds it refused. Its stated reason for
refusing them — that their dispatch path does not read the bidirected
edge set — is a fact about a signature standing in for the fact that
matters, which is whether a latent common cause can move the answer. The
proxy was wrong in both directions on HEAD, and the tests here are the
measurements that say so: two refused kinds answering correctly, and one
admitted kind that the proxy would have refused.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

import themis
from themis.input import semantic_validator as sv
from themis.input.semantic_validator import (
    LatentExposure,
    SemanticError,
    _bind_latent_exposure,
)
from themis.types import QUERY_KIND_OF, QueryKind


# =============================================================== helpers

def _atom(p: str, unit: str = "me") -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": unit}]}


def _program(statements, unit: str = "me") -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": unit}]},
        "statements": list(statements),
    }


_DECLS = [
    {"kind": "variable", "predicate": n, "domain": [True, False]}
    for n in ("x", "m", "y")
]


# ========================================== the vocabulary is complete

def test_every_query_kind_says_what_a_latent_common_cause_does_to_it():
    """The half the old gate never had. It listed the kinds it refused, so
    a kind added afterwards was admitted by saying nothing — which is how
    five of the ten came to be admitted without anyone being asked."""
    assert set(sv._LATENT_EXPOSURE) == set(QueryKind)
    for kind, exposure in sv._LATENT_EXPOSURE.items():
        assert isinstance(exposure.verdict, LatentExposure), kind
        assert exposure.evidence.strip(), kind


def test_every_query_class_has_a_kind_and_every_kind_has_a_class():
    """One link up the chain from the table above.

    The gate reaches its verdict by asking which kind a query is, so an
    unmapped class is a KeyError in front of a user rather than an answer.
    The import-time pin below covers a kind with no verdict; this covers a
    class with no kind, which the same afternoon of work would otherwise
    leave to a runtime crash — the shape this whole item is about.
    """
    from typing import get_args

    from themis.types import Query

    assert set(QUERY_KIND_OF) == set(get_args(Query))
    assert set(QUERY_KIND_OF.values()) == set(QueryKind)


def test_a_kind_nobody_classified_stops_the_module_from_importing():
    """The counterexample the pin above would pass without. Left to a
    runtime check it would be a wrong answer for one user; here it is a
    failure for whoever added the kind."""
    short = {k: v for k, v in sv._LATENT_EXPOSURE.items()
             if k is not QueryKind.PROXIMAL_EFFECT}
    with pytest.raises(AssertionError) as exc:
        _bind_latent_exposure(short)
    assert "proximal_effect" in str(exc.value)

    stale = dict(sv._LATENT_EXPOSURE)
    stale["a_kind_that_was_removed"] = sv.Exposure(LatentExposure.ABSORBED,
                                                   "gone")
    with pytest.raises(AssertionError) as exc:
        _bind_latent_exposure(stale)
    assert "a_kind_that_was_removed" in str(exc.value)


# ================================================ the gate still refuses

def test_a_kind_answered_off_the_directed_edges_alone_is_refused(monkeypatch):
    """What the gate says no to. No kind is declared ``UNREAD`` today, so
    the only way to see the refusal is to declare one — which is also the
    only way to know the gate would refuse the next kind that needs it
    rather than having quietly become a no-op.

    The evidence column is the other half of the same measurement. It is
    written for whoever maintains the table — it argues why this kind got
    this verdict — and a sentence spliced into a refusal is addressed to
    whoever wrote the program, in their language. One string cannot be
    both, so the table's half stays in the table."""
    monkeypatch.setitem(
        sv._LATENT_EXPOSURE, QueryKind.CAUSE,
        sv.Exposure(LatentExposure.UNREAD, "an argument for the maintainer"),
    )
    ast_ = _program([
        *_DECLS,
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "my_query_id", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
    ])
    with pytest.raises(SemanticError) as exc:
        themis.run(ast_)
    assert exc.value.species is sv.Malformed.LATENT_UNREAD_BY_THIS_QUERY
    assert exc.value.details["kind"] == "cause"
    assert exc.value.details["query"] == "my_query_id", (
        "the reader cannot find which query")
    assert "an argument for the maintainer" not in str(exc.value)


def test_a_program_without_a_latent_is_not_the_gate_s_business():
    """Same query, same kind declared unreadable — but no bidirected
    statement, so nothing about a latent is being claimed."""
    ast_ = _program([
        *_DECLS,
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
    ])
    r = themis.run(ast_)["results"][0]
    assert r["structural_result"]["value"] is True


# ======================================= cause: a latent is not causation

def test_a_latent_common_cause_is_not_causation():
    """x<->y says the two share an unobserved cause. It does not say one
    causes the other, and the answer is read off reachability that cannot
    see the bidirected pair — the atoms enter G(M) as isolated nodes."""
    ast_ = _program([
        *_DECLS,
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
    ])
    r = themis.run(ast_)["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is False
    assert themis.verify(ast_, r) is None


def test_an_arrow_and_a_latent_between_the_same_pair_answer_the_arrow():
    """The mixed case: x->y AND x<->y. One of them is causation and the
    other is not, and the answer is the arrow."""
    ast_ = _program([
        *_DECLS,
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
    ])
    r = themis.run(ast_)["results"][0]
    assert r["structural_result"]["value"] is True
    assert r["structural_result"]["supporting_paths"] == [["x(me)", "y(me)"]]


def test_the_directed_path_is_the_answer_and_the_latent_is_not_in_it():
    ast_ = _program([
        *_DECLS,
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
    ])
    r = themis.run(ast_)["results"][0]
    assert r["structural_result"]["value"] is True
    assert r["structural_result"]["supporting_paths"] == [
        ["x(me)", "m(me)", "y(me)"]
    ]
    assert themis.verify(ast_, r) is None


# ============================ probability: the guard is the load-bearing part

def test_the_conditional_the_user_declared_is_the_one_they_get():
    """A latent common cause cannot move a number the user handed over."""
    ast_ = _program([
        *_DECLS,
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "probability",
         "target": {"atom": _atom("y"), "value": True},
         "given": [{"atom": _atom("x"), "value": True}], "value": 0.7},
        {"kind": "query", "id": "q", "query": {
            "kind": "probability",
            "target": {"atom": _atom("y"), "value": True},
            "given": [{"atom": _atom("x"), "value": True}]}},
    ])
    r = themis.run(ast_)["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.7)
    assert themis.verify(ast_, r) is None


_MARGINAL_ONLY = _program([
    *_DECLS,
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    {"kind": "probability", "target": {"atom": _atom("y"), "value": True},
     "given": [], "value": 0.18},
    {"kind": "query", "id": "q", "query": {
        "kind": "probability",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": True}]}},
])


def test_a_coarser_conditional_is_not_stood_in_when_a_latent_connects_them():
    """The one case where a latent CAN move a probability answer: theta
    has P(y) and the query wants P(y|x). Standing the marginal in asserts
    y ⊥ x, and x<->y is exactly what makes that false."""
    r = themis.run(_MARGINAL_ONLY)["results"][0]
    assert r["status"] == "needs_investigation"
    assert [i["name"] for i in r["missing_information"]] == [
        "parameter:P(y=True|x=True)"
    ]


def test_that_refusal_is_the_guard_and_not_something_else():
    """Withholding the edge set from the guard on the same theta and the
    same query hands back the marginal as though it were the conditional.
    Without this the test above would pass on a path that simply never
    tried the substitution."""
    from themis.runtime import (
        graph_projection, instantiation, structural_solver, theta_builder,
    )
    from themis.runtime.numeric_estimator import (
        ProbabilityKey, _try_marginal_independence_lookup,
    )

    program = sv.validate_program(_MARGINAL_ONLY)
    ground = instantiation.instantiate(program)
    theta = theta_builder.build_theta(ground)
    graph = graph_projection.project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    by_pred = {n.predicate: n for n in graph.nodes}
    key = ProbabilityKey(
        target_atom=by_pred["y"], target_value=True,
        given=frozenset({(by_pred["x"], True)}), population=None,
    )

    withheld = _try_marginal_independence_lookup(
        key, theta, graph=graph, bidirected=None,
    )
    supplied = _try_marginal_independence_lookup(
        key, theta, graph=graph, bidirected=bidirected,
    )
    assert withheld == pytest.approx(0.18)
    assert supplied is None


# ============ scm_counterfactual: the kind the old condition would refuse

_A_XY, _C_UX, _C_UY, _X_STAR = 0.7, 0.9, 1.3, 2.0


def _unit_program(unit, x_obs, y_obs, *, latent: bool):
    x, y = _atom("x", unit), _atom("y", unit)
    stmts = [{"kind": "cause", "from": x, "to": y, "coefficient": _A_XY}]
    if latent:
        stmts.append({"kind": "bidirected", "left": x, "right": y})
    stmts += [
        {"kind": "observation", "atom": x, "value": float(x_obs)},
        {"kind": "observation", "atom": y, "value": float(y_obs)},
        {"kind": "query", "id": "q", "query": {
            "kind": "scm_counterfactual",
            "intervention": {"atom": x, "value": _X_STAR},
            "target": y}},
    ]
    return _program(stmts, unit=unit)


def test_abduction_absorbs_the_latent_into_the_units_own_term():
    """This path is handed no bidirected edge set, so under the gate's old
    stated condition it should have been refused — and it was admitted.
    The condition is what is wrong: the unit's exogenous term is recovered
    wholesale from the factual observation, whatever the latent put into
    it, and do() leaves that term alone.

    Truth here is not another estimator's number. Each unit's latent draw
    is known, so what its outcome would have been under do(X=x*) is known
    in closed form."""
    rng = np.random.default_rng(11)
    worst_latent = worst_plain = 0.0
    for i in range(40):
        u, e_x, e_y = rng.normal(), rng.normal(), rng.normal()
        x_obs = _C_UX * u + e_x
        y_obs = _A_XY * x_obs + _C_UY * u + e_y
        truth = _A_XY * _X_STAR + _C_UY * u + e_y
        for latent in (True, False):
            r = themis.run(
                _unit_program(f"p{i}", x_obs, y_obs, latent=latent)
            )["results"][0]
            assert r["status"] == "counterfactual_solved"
            err = abs(r["numeric_result"]["value"] - truth)
            if latent:
                worst_latent = max(worst_latent, err)
            else:
                worst_plain = max(worst_plain, err)
    assert worst_latent < 1e-9
    assert worst_plain == pytest.approx(worst_latent, abs=1e-15)


# ==================== the half of the table that a signature can still pin

_SCHEDULER = pathlib.Path(themis.__file__).parent / "runtime" / "scheduler.py"


def _dispatch_branches() -> dict[QueryKind, ast.AST]:
    """Each ``isinstance(q, SomeQuery)`` branch of ``dispatch``, by kind."""
    tree = ast.parse(_SCHEDULER.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "dispatch"
    )
    by_class_name = {c.__name__: k for c, k in QUERY_KIND_OF.items()}
    branches: dict[QueryKind, ast.AST] = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Call)
            and getattr(test.func, "id", None) == "isinstance"
            and len(test.args) == 2
            and isinstance(test.args[1], ast.Name)
        ):
            continue
        kind = by_class_name.get(test.args[1].id)
        if kind is not None:
            branches[kind] = node
    return branches


def test_the_dispatch_site_names_every_kind_once():
    """The premise of the test below. If a kind had no branch here the
    check would pass by finding nothing to check."""
    assert set(_dispatch_branches()) == set(QueryKind)


@pytest.mark.parametrize(
    "kind",
    [k for k, (e, _) in sv._LATENT_EXPOSURE.items()
     if e is LatentExposure.CONSULTED],
    ids=lambda k: k.value,
)
def test_every_consulted_kind_is_handed_the_edge_set(kind):
    """``CONSULTED`` claims the path is given the bidirected edge set. A
    path that stops being given it goes on answering, off the directed
    edges, without saying so — so the claim is pinned to the call rather
    than left in prose.

    ``ABSORBED`` is deliberately not pinned this way: handing an edge set
    to a path that cannot be moved by one would be harmless, and refusing
    it here would make the table track signatures again."""
    branch = _dispatch_branches()[kind]
    handed = any(
        kw.arg == "bidirected"
        for node in ast.walk(branch)
        if isinstance(node, ast.Call)
        for kw in node.keywords
    )
    assert handed, (
        f"dispatch does not hand the bidirected edge set to the "
        f"{kind.value} path, which _LATENT_EXPOSURE declares CONSULTED"
    )
