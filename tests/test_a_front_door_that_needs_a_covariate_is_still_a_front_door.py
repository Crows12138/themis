"""What a reader is told about WHERE the answer came from.

Two losses, both measured before anything was written.

The first: ``front_door_sets`` implemented one of the two front-door criteria
in the literature. Its FD2 asks for no open back-door from X to a mediator
under EMPTY conditioning, so the ordinary epidemiological graph where a
mediator shares an observed cause with the treatment (C → X, C → M) was
rejected outright — even though holding C restores every condition. That is
the generalized front-door criterion (Fulcher, Shpitser, Marealle & Tchetgen
Tchetgen, JRSS-B 2020), and Pearl's textbook one is its C = ∅ face.

The second, larger: the identification PATTERN was attached on the identify
path only. An effect query — the one that returns a number — carried it on no
row but the IV escalation, so the reader holding an answer was never told
which structure produced it. The pattern was encoded implicitly, in which
cascade row fired, and a reader does not read cascade rows.

The oracle for the first is exact rather than structural: the generalized
formula, evaluated on an observational joint with the confounder summed out,
must equal the interventional truth computed from the SCM's own parameters,
while the textbook formula on the same graph must visibly miss.
"""
from __future__ import annotations

import copy
import itertools

import networkx as nx
import numpy as np
import pytest

import themis
from themis.output.analysis_report import build_analysis_report
from themis.runtime import structural_solver as ss
from themis.types import Atom, ConstTerm

# --------------------------------------------------------------------------
# Programs.  One question, asked of three graphs and in two query shapes.
# --------------------------------------------------------------------------


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p: str) -> dict:
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a: str, b: str) -> dict:
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _prob(t: str, tv: bool, given, v: float) -> dict:
    return {
        "kind": "probability",
        "target": {"atom": _atom(t), "value": tv},
        "given": [{"atom": _atom(g), "value": gv} for g, gv in given],
        "value": v,
    }


def _program(statements, kind: str) -> dict:
    if kind == "effect":
        query = {
            "kind": "effect",
            "target": {"atom": _atom("y"), "value": True},
            "intervention": {"atom": _atom("x"), "value": True},
            "given": [],
        }
    else:
        query = {
            "kind": "identify",
            "target": _atom("y"),
            "intervention": {"atom": _atom("x"), "value": True},
            "given": [],
        }
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": list(statements) + [
            {"kind": "query", "id": "q", "query": query},
        ],
    }


#: P(Y=1 | x, m, c) for the covariate graph.
_PY = {
    (True, True, True): 0.9, (True, False, True): 0.4,
    (False, True, True): 0.6, (False, False, True): 0.1,
    (True, True, False): 0.85, (True, False, False): 0.35,
    (False, True, False): 0.55, (False, False, False): 0.05,
}

PLAIN_STMTS = [
    _var("x"), _var("m"), _var("y"),
    _cause("x", "m"), _cause("m", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _prob("x", True, [], 0.5), _prob("x", False, [], 0.5),
    _prob("m", True, [("x", True)], 0.7),
    _prob("m", False, [("x", True)], 0.3),
    _prob("m", True, [("x", False)], 0.2),
    _prob("m", False, [("x", False)], 0.8),
    _prob("y", True, [("x", True), ("m", True)], 0.9),
    _prob("y", True, [("x", True), ("m", False)], 0.4),
    _prob("y", True, [("x", False), ("m", True)], 0.6),
    _prob("y", True, [("x", False), ("m", False)], 0.1),
]

COVAR_STMTS = [
    _var("c"), _var("x"), _var("m"), _var("y"),
    _cause("c", "x"), _cause("c", "m"), _cause("x", "m"), _cause("m", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    _prob("c", True, [], 0.4), _prob("c", False, [], 0.6),
    _prob("x", True, [("c", True)], 0.7),
    _prob("x", False, [("c", True)], 0.3),
    _prob("x", True, [("c", False)], 0.3),
    _prob("x", False, [("c", False)], 0.7),
    _prob("m", True, [("x", True), ("c", True)], 0.8),
    _prob("m", False, [("x", True), ("c", True)], 0.2),
    _prob("m", True, [("x", False), ("c", True)], 0.3),
    _prob("m", False, [("x", False), ("c", True)], 0.7),
    _prob("m", True, [("x", True), ("c", False)], 0.6),
    _prob("m", False, [("x", True), ("c", False)], 0.4),
    _prob("m", True, [("x", False), ("c", False)], 0.1),
    _prob("m", False, [("x", False), ("c", False)], 0.9),
    *[_prob("y", True, [("x", x), ("m", m), ("c", c)], v)
      for (x, m, c), v in _PY.items()],
]

BACKDOOR_STMTS = [
    _var("c"), _var("x"), _var("y"),
    _cause("c", "x"), _cause("c", "y"), _cause("x", "y"),
    _prob("c", True, [], 0.4), _prob("c", False, [], 0.6),
    _prob("x", True, [("c", True)], 0.7),
    _prob("x", False, [("c", True)], 0.3),
    _prob("x", True, [("c", False)], 0.3),
    _prob("x", False, [("c", False)], 0.7),
    _prob("y", True, [("x", True), ("c", True)], 0.9),
    _prob("y", True, [("x", False), ("c", True)], 0.6),
    _prob("y", True, [("x", True), ("c", False)], 0.4),
    _prob("y", True, [("x", False), ("c", False)], 0.1),
]


def _identification(stmts, kind: str) -> dict:
    result = themis.run(_program(stmts, kind))["results"][0]
    return (result.get("extensions") or {}).get("identification")


# --------------------------------------------------------------------------
# D1: is the criterion the label names actually SOUND?
# --------------------------------------------------------------------------

_STATES = (0, 1)


def _covariate_front_door_scm(seed: int):
    """C → X, C → Z, C → Y, X → Z, Z → Y, U → X, U → Y, with U latent.

    Every parameter is drawn away from the boundary so that no conditional
    is undefined and the two formulas below are both computable.
    """
    rng = np.random.default_rng(seed)

    def draw(*shape):
        return rng.uniform(0.12, 0.88, size=shape or (1,))

    return (float(draw()[0]), float(draw()[0]),
            draw(2, 2), draw(2, 2), draw(2, 2, 2))


def _truth_and_formulas(seed: int) -> tuple[float, float, float]:
    """P(y|do(x=1)) three ways: from the SCM, and from the joint twice."""
    p_c, p_u, p_x, p_z, p_y = _covariate_front_door_scm(seed)

    def pc(c):
        return p_c if c else 1 - p_c

    def pu(u):
        return p_u if u else 1 - p_u

    def px(x, c, u):
        return p_x[c, u] if x else 1 - p_x[c, u]

    def pz(z, x, c):
        return p_z[x, c] if z else 1 - p_z[x, c]

    def py(y, z, u, c):
        return p_y[z, u, c] if y else 1 - p_y[z, u, c]

    # Truth: the SCM with X's own mechanism replaced by x := 1.
    truth = sum(
        pc(c) * pu(u) * pz(z, 1, c) * py(1, z, u, c)
        for c, u, z in itertools.product(_STATES, repeat=3)
    )

    # The observational joint P(c, x, z, y) — U is latent, so summed out.
    joint = np.zeros((2, 2, 2, 2))
    for c, u, x, z, y in itertools.product(_STATES, repeat=5):
        joint[c, x, z, y] += (
            pc(c) * pu(u) * px(x, c, u) * pz(z, x, c) * py(y, z, u, c)
        )

    # Generalized: sum_c P(c) sum_z P(z|x,c) sum_x' P(x'|c) P(y|x',z,c)
    generalized = 0.0
    for c in _STATES:
        p_c_marg = joint[c].sum()
        p_x1_c = joint[c, 1].sum() / p_c_marg
        for z in _STATES:
            inner = 0.0
            for xp in _STATES:
                weight = p_x1_c if xp else 1 - p_x1_c
                inner += weight * (
                    joint[c, xp, z, 1] / joint[c, xp, z].sum())
            generalized += (
                p_c_marg * (joint[c, 1, z].sum() / joint[c, 1].sum()) * inner)

    # Textbook: the same formula with C dropped instead of held.
    marg = joint.sum(axis=0)
    textbook = 0.0
    for z in _STATES:
        inner = sum(
            marg[xp].sum() * (marg[xp, z, 1] / marg[xp, z].sum())
            for xp in _STATES
        )
        textbook += (marg[1, z].sum() / marg[1].sum()) * inner

    return float(truth), float(generalized), float(textbook)


def test_the_generalized_formula_recovers_the_interventional_truth():
    """Sixty SCMs, exact enumeration, no sampling."""
    worst = max(
        abs(truth - generalized)
        for truth, generalized, _ in (_truth_and_formulas(s) for s in range(60))
    )
    assert worst < 1e-12, worst


def test_dropping_the_covariate_instead_of_holding_it_misses():
    """Otherwise the label would be naming a distinction that is not one."""
    gaps = [
        abs(truth - textbook)
        for truth, _, textbook in (_truth_and_formulas(s) for s in range(60))
    ]
    assert max(gaps) > 0.02, max(gaps)


# --------------------------------------------------------------------------
# The criterion, on graphs it must and must not accept.
# --------------------------------------------------------------------------


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


X, Y, M, C, U = (_A(n) for n in ("x", "y", "m", "c", "u"))


def _graph(edges, bidirected=()):
    g = nx.DiGraph()
    g.add_nodes_from({n for e in edges for n in e})
    g.add_edges_from(edges)
    return g, frozenset(frozenset(b) for b in bidirected)


#: (label, directed edges, bidirected edges, is there a front door at all)
CRITERION_CASES = [
    ("textbook", [(X, M), (M, Y)], [(X, Y)], True),
    ("needs a covariate held",
     [(C, X), (C, M), (X, M), (M, Y)], [(X, Y)], True),
    ("a directed edge bypasses the mediator",
     [(X, M), (M, Y), (X, Y)], [(X, Y)], False),
    ("mediator confounded with the outcome, unblockably",
     [(X, M), (M, Y)], [(X, Y), (M, Y)], False),
    ("mediator confounded with the treatment, unblockably",
     [(X, M), (M, Y)], [(X, Y), (X, M)], False),
    ("the only blocker is a descendant of the treatment",
     [(X, C), (C, M), (X, M), (M, Y)], [(X, Y), (X, M)], False),
    ("two parallel mediators, both needed",
     [(X, M), (M, Y), (X, U), (U, Y)], [(X, Y)], True),
]


@pytest.mark.parametrize(
    "label,edges,bidirected,expected",
    CRITERION_CASES,
    ids=[c[0] for c in CRITERION_CASES],
)
def test_the_criterion_says_yes_only_where_it_holds(
    label, edges, bidirected, expected,
):
    g, bi = _graph(edges, bidirected)
    found = ss.generalized_front_door_sets(g, X, Y, bidirected=bi)
    assert bool(found) is expected, (label, found)


@pytest.mark.parametrize(
    "label,edges,bidirected,_expected",
    CRITERION_CASES,
    ids=[c[0] for c in CRITERION_CASES],
)
def test_the_textbook_criterion_is_the_empty_covariate_face(
    label, edges, bidirected, _expected,
):
    """``front_door_sets`` must keep returning exactly what it returned."""
    g, bi = _graph(edges, bidirected)
    classic = ss.front_door_sets(g, X, Y, bidirected=bi)
    face = tuple(
        fd.mediators
        for fd in ss.generalized_front_door_sets(g, X, Y, bidirected=bi)
        if not fd.covariates
    )
    assert classic == face


def test_the_covariate_case_is_named_with_the_fewest_held():
    g, bi = _graph([(C, X), (C, M), (X, M), (M, Y)], [(X, Y)])
    found = ss.generalized_front_door_sets(g, X, Y, bidirected=bi)
    assert found[0].mediators == frozenset({M})
    assert found[0].covariates == frozenset({C})


def test_the_order_does_not_move_between_calls():
    """The pool comes from a set intersection, whose iteration order is
    hash-seeded; the sort is what makes ``front[0]`` a decision."""
    g, bi = _graph(
        [(C, X), (C, M), (X, M), (M, Y), (X, U), (U, Y)], [(X, Y)])
    runs = {
        tuple((tuple(sorted(a.predicate for a in fd.mediators)),
               tuple(sorted(a.predicate for a in fd.covariates)))
              for fd in ss.generalized_front_door_sets(g, X, Y, bidirected=bi))
        for _ in range(5)
    }
    assert len(runs) == 1


# --------------------------------------------------------------------------
# What the envelope carries, and on which query shape.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["effect", "identify"])
def test_a_covariate_front_door_is_named_a_front_door(kind):
    block = _identification(COVAR_STMTS, kind)
    assert block["pattern"] == "front_door"
    assert block["mediator_set"] == ["m(me)"]
    assert block["covariate_set"] == ["c(me)"]


@pytest.mark.parametrize("kind", ["effect", "identify"])
def test_a_textbook_front_door_names_no_covariates(kind):
    """Absent, not empty: nothing needs holding, and an empty list would
    read as a set the reader has to go and find."""
    block = _identification(PLAIN_STMTS, kind)
    assert block["pattern"] == "front_door"
    assert block["mediator_set"] == ["m(me)"]
    assert "covariate_set" not in block


@pytest.mark.parametrize(
    "stmts,pattern",
    [(PLAIN_STMTS, "front_door"), (COVAR_STMTS, "front_door"),
     (BACKDOOR_STMTS, "backdoor")],
    ids=["plain-front-door", "covariate-front-door", "back-door"],
)
def test_an_effect_query_says_where_its_number_came_from(stmts, pattern):
    """The loss that mattered: this block reached no numeric answer at all."""
    block = _identification(stmts, "effect")
    assert block is not None
    assert block["pattern"] == pattern


def test_both_query_shapes_say_the_same_thing():
    for stmts in (PLAIN_STMTS, COVAR_STMTS, BACKDOOR_STMTS):
        assert _identification(stmts, "effect") == \
            _identification(stmts, "identify")


@pytest.mark.parametrize(
    "lang,needle",
    [("zh", "并握住 {c(me)}"), ("en", "holding {c(me)}")],
)
def test_the_reader_is_told_what_to_hold(lang, needle):
    result = themis.run(_program(COVAR_STMTS, "effect"))["results"][0]
    report = build_analysis_report(result, lang=lang)
    assert needle in report


def test_the_reader_of_a_textbook_front_door_is_told_to_hold_nothing():
    result = themis.run(_program(PLAIN_STMTS, "effect"))["results"][0]
    report = build_analysis_report(result, lang="zh")
    assert "经中介 {m(me)}" in report
    assert "握住" not in report


# --------------------------------------------------------------------------
# The verifier: ten forgeries, and the honest article.
# --------------------------------------------------------------------------

FORGERIES = [
    ("nothing to control where a confounder needs controlling",
     BACKDOOR_STMTS, {"pattern": "backdoor", "adjustment_set": []}),
    ("control for the outcome",
     BACKDOOR_STMTS, {"pattern": "backdoor", "adjustment_set": ["y(me)"]}),
    ("the covariate the front door needs held, dropped",
     COVAR_STMTS, {"pattern": "front_door", "mediator_set": ["m(me)"]}),
    ("a non-mediator called the mediator",
     COVAR_STMTS, {"pattern": "front_door", "mediator_set": ["c(me)"],
                   "covariate_set": ["c(me)"]}),
    ("holding the outcome",
     COVAR_STMTS, {"pattern": "front_door", "mediator_set": ["m(me)"],
                   "covariate_set": ["y(me)"]}),
    ("the general solution over a covariate front door",
     COVAR_STMTS, {"pattern": "c_factor"}),
    ("the general solution over a textbook front door",
     PLAIN_STMTS, {"pattern": "c_factor"}),
    ("the general solution over a back door",
     BACKDOOR_STMTS, {"pattern": "c_factor"}),
    ("a variable the graph does not have",
     PLAIN_STMTS, {"pattern": "front_door", "mediator_set": ["q(me)"]}),
    ("a pattern with no name",
     PLAIN_STMTS, {"pattern": "wishful_thinking"}),
]


@pytest.mark.parametrize(
    "label,stmts,forged", FORGERIES, ids=[f[0] for f in FORGERIES],
)
def test_a_forged_pattern_is_rejected(label, stmts, forged):
    program = _program(stmts, "effect")
    result = themis.run(program)["results"][0]
    tampered = copy.deepcopy(result)
    tampered["extensions"]["identification"] = forged
    with pytest.raises(Exception):
        themis.verify(program, tampered)


@pytest.mark.parametrize(
    "stmts", [PLAIN_STMTS, COVAR_STMTS, BACKDOOR_STMTS],
    ids=["plain-front-door", "covariate-front-door", "back-door"],
)
def test_the_untampered_answer_verifies(stmts):
    program = _program(stmts, "effect")
    themis.verify(program, themis.run(program)["results"][0])


def test_an_effect_the_general_id_row_answered_can_be_verified():
    """A separate defect the covariate graph surfaced: ``identify_via_tian``
    read the intervened and outcome atoms through ``IdentifyQuery``'s field
    layout, so the identical c-factor answer verified as an identify query
    and raised as an effect query. Nothing in the suite reached that row
    with a number, so nothing said so.
    """
    program = _program(COVAR_STMTS, "effect")
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved"
    steps = {s["rule"] for s in result["derivation"]["steps"]}
    assert "identify_via_tian" in steps
    themis.verify(program, result)
