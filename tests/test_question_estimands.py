"""Which questions name a quantity, and what interval stands in for its point.

Two facts about a question decided how its data-gap report reads, and both
were answered by one hand-written set of three query kinds in
``data_gap_report``: whether ``answer_tier`` — point / interval / none —
means anything, and whether an interval is a genuine fallback when a
distribution the answer needs is missing. They agree on the three kinds the
set named and diverge on the seven that fell to its ``else``.

One instrumented suite run measured the divergence.

* The ``else`` branch fired 226 times and 222 of them were ``causation``,
  told that its quantity is "点可估的，没有 bounds 替代路径" — a sentence
  written for ``probability`` and false of probabilities of causation, whose
  answer is a Tian-Pearl interval whenever monotonicity is not declared.
* The tier suppressed itself on the same seven kinds while the estimation
  layer, which reads no such set, wrote a tier for them from the number it
  had just produced: 17 of 25 causation envelopes carried one, 6 of 17
  scm_counterfactual, 4 of 10 proximal_effect. The same query kind had a
  tier or not depending on which entrance the caller used.
* A twin set for "this kind has no data needs" also listed ``probability``
  and returned before the gap species ran, so a probability query whose
  kernel had raised MISSING_DISTRIBUTION reached the reader with no report
  at all — indistinguishable from a clean bill of health. Measured twice on
  a subset of the suite.

The facts now sit on :class:`themis.questions.Question`, one declaration per
kind, and the tests below hold both halves: the vocabulary says it once, and
each of the three consumers reads it rather than a list of kinds.
"""
from __future__ import annotations

import pytest

import themis
from themis import questions
from themis.output import data_gap_report
from themis.types import QueryKind


# --- the vocabulary says each fact once ---------------------------------------


def test_only_the_two_graph_questions_name_no_estimand():
    """Pinned literally rather than derived: ``cause`` and ``assoc`` ask
    whether a path or a d-connection exists, and nothing about a magnitude
    follows. Every other kind names a quantity — including ``probability``,
    which both hand-written sets excluded, and ``identify``, whose answer is
    the verdict but whose subject is still an estimand."""
    without = {q.kind for q in questions.DECLARED if not q.names_an_estimand}
    assert without == {"cause", "assoc"}


def test_an_interval_stands_in_only_where_a_bounds_procedure_exists():
    """Three kinds have one. Manski / Balke-Pearl for an effect, Tian-Pearl
    for a counterfactual cell and for probabilities of causation. The rest
    have no bounds channel wired, so offering an interval would be a promise
    nothing keeps."""
    with_fallback = {
        q.kind for q in questions.DECLARED if q.interval_fallback is not None
    }
    assert with_fallback == {"effect", "counterfactual", "causation"}


def test_a_question_that_names_no_quantity_has_no_interval_either():
    """Not enforced by the types, and the one pairing that would be
    incoherent: an interval of what?"""
    for q in questions.DECLARED:
        if not q.names_an_estimand:
            assert q.interval_fallback is None, q.kind


def test_the_report_decides_neither_fact_from_a_list_of_query_kinds():
    """The shape of the defect, not just its instances: a module-level
    collection of QueryKind is a second place for a fact the vocabulary
    already states, and its ``else`` is where a newly added kind lands
    without anyone deciding."""
    listed = {
        name: value
        for name, value in vars(data_gap_report).items()
        if isinstance(value, (frozenset, set, tuple, list))
        and any(isinstance(v, QueryKind) for v in value)
    }
    assert not listed, (
        f"{sorted(listed)} decide a per-question fact by listing kinds; "
        f"declare it on themis.questions.Question instead"
    )


# --- consumer 1: a gap's alternative path -------------------------------------


def _atom(p, obj="me"):
    return {"predicate": p, "args": [{"type": "const", "name": obj}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_OBJECTS = {"objects": [{"kind": "object", "name": "me"}]}


def _causation_program(*, monotonic: bool):
    """X → Y confounded by Z: the joint needs theta the program withholds,
    so the query stops at needs_investigation with distribution gaps."""
    return {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            _var("x"), _var("y"), _var("z"),
            _cause("x", "y"), _cause("z", "x"), _cause("z", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "causation",
                "cause": _atom("x"),
                "effect": _atom("y"),
                "monotonic": monotonic,
            }},
        ],
    }


def _probability_program():
    """A probability query and an empty theta — no variable declarations, so
    no framing note fires and the must-disclose channel stays empty. That is
    the state in which the report used to vanish."""
    return {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": {"atom": _atom("coin"), "value": True},
                "given": [],
            }},
        ],
    }


def _gaps_of(result, kind):
    report = result.get("data_gap_report") or {}
    return [g for g in report.get("gaps", []) if g["kind"] == kind]


def test_a_causation_gap_is_offered_the_bounds_that_answer_it():
    """The 222-gap cell. Tian-Pearl, named: Balke-Pearl bounds an effect
    under an instrument, which is not what a probability of causation is."""
    result = themis.run(_causation_program(monotonic=False))["results"][0]
    gaps = _gaps_of(result, "missing_distribution")
    assert gaps, "the confounded causation query raised no distribution gap"
    for gap in gaps:
        assert gap["alternative_paths"] == ["接受 Tian-Pearl bounds 给区间答案"]


def test_a_probability_gap_is_not_told_an_interval_will_save_it():
    """The four gaps the ``else`` branch was written for keep their answer:
    an observational conditional has no bounds substitute, and suggesting
    one would send the reader after an interval that does not exist."""
    result = themis.run(_probability_program())["results"][0]
    gaps = _gaps_of(result, "missing_distribution")
    assert len(gaps) == 1
    (path,) = gaps[0]["alternative_paths"]
    assert "没有区间退路" in path
    assert "bounds" not in path


# --- consumer 2: whether a report is built at all ------------------------------


def test_a_probability_query_keeps_the_gap_its_kernel_raised():
    """The dropped-gap cell. The kernel says P(coin=True) is missing from
    theta; the report used to return before the species pass could say so,
    leaving no report — which reads as nothing missing."""
    result = themis.run(_probability_program())["results"][0]
    assert result["status"] == "needs_investigation"
    assert any(
        m["gap"] == "missing_distribution"
        for m in result.get("missing_information", [])
    )
    report = result.get("data_gap_report")
    assert report is not None, "the kernel raised a gap and the report is gone"
    assert [g["kind"] for g in report["gaps"]] == ["missing_distribution"]


def test_a_graph_question_reports_nothing_when_it_has_nothing_to_report():
    """The half of the early return that was right stays right: a fully
    framed cause query names no quantity, so there is no data it could be
    short of and no report to build."""
    program = {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            dict(_var("x"), **_FRAMED), dict(_var("y"), **_FRAMED),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }
    result = themis.run(program)["results"][0]
    assert result.get("data_gap_report") is None
    assert result["structural_result"]["value"] is True


# Every framing field a variable can be asked for; supplying them all is
# what keeps the ambiguity gap from firing and keeps the case above about
# the query kind rather than about an under-specified variable.
_FRAMED = {
    "time_window": "12 months",
    "measurement": "administrative record",
    "observability": "observed",
    "direction": "higher is more",
    "baseline": "no exposure",
    "state_vs_event": "state",
}


# --- consumer 3: the answer tier ----------------------------------------------


def _tier(result):
    return (result.get("data_gap_report") or {}).get("answer_tier")


@pytest.mark.parametrize("monotonic, expected", [(True, "point"),
                                                 (False, "interval")])
def test_a_withheld_premise_decides_the_shape_before_the_data_arrive(
    monotonic, expected,
):
    """PN/PS/PNS are Tian-Pearl intervals; monotonicity is what collapses
    them to points, and it is declared on the query rather than found in
    the data. So the shape of the eventual answer is known before any of
    it is: ``point`` here would promise a number that cannot arrive."""
    result = themis.run(_causation_program(monotonic=monotonic))["results"][0]
    assert result["status"] == "needs_investigation"
    assert _tier(result) == expected


def _unidentifiable_causation(*, with_theta: bool):
    """X → Y with an unobserved common cause: P(Y|do(X)) is not identifiable,
    so PN/PS/PNS have neither a point nor an interval — with or without the
    theta the observational joint would need."""
    theta = [
        {"kind": "probability", "target": {"atom": _atom(t), "value": v},
         "given": [{"atom": _atom(g), "value": gv} for g, gv in given],
         "value": p}
        for t, v, given, p in [
            ("x", True, (), 0.4), ("x", False, (), 0.6),
            ("y", True, (("x", True),), 0.7),
            ("y", False, (("x", True),), 0.3),
            ("y", True, (("x", False),), 0.2),
            ("y", False, (("x", False),), 0.8),
        ]
    ] if with_theta else []
    return {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            _var("x"), _var("y"), _cause("x", "y"),
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            *theta,
            {"kind": "query", "id": "q", "query": {
                "kind": "causation",
                "cause": _atom("x"), "effect": _atom("y"),
                "monotonic": False,
            }},
        ],
    }


@pytest.mark.parametrize("with_theta", [True, False])
def test_the_same_graph_reaches_the_same_verdict_with_or_without_theta(
    with_theta,
):
    """Identifiability is a property of the graph, so the two runs have to
    agree — and they did not. The dispatcher asked theta for the
    observational joint before it asked whether the interventional risks
    were identifiable at all, and returned at the first shortfall it hit.
    Without theta that was the joint, so the query that no data can answer
    was reported as a list of distributions to go and collect."""
    result = themis.run(_unidentifiable_causation(with_theta=with_theta))
    result = result["results"][0]
    assert result["status"] == "needs_investigation"
    kinds = {m["gap"] for m in result["missing_information"]}
    assert "unidentifiable_no_admissible_set" in kinds
    assert _tier(result) == "none"


def test_an_unreachable_interval_is_not_left_on_offer():
    """The tier says no interval is reachable; a gap beside it still
    advising "accept bounds for an interval answer" contradicts it in the
    same breath, and the reader acts on the gap, not the tier."""
    result = themis.run(
        _unidentifiable_causation(with_theta=False)
    )["results"][0]
    report = result["data_gap_report"]
    assert report["answer_tier"] == "none"
    offers = [
        a for g in report["gaps"] for a in (g.get("alternative_paths") or [])
        if "给区间答案" in a
    ] + [s for s in report.get("actionable_next_steps", []) if "给区间答案" in s]
    assert offers == []


def test_the_escape_hatch_says_which_of_its_two_causes_it_is():
    """It fires both when the effect is unidentifiable and when it is
    identifiable but theta is short — opposite repairs. One sentence for
    both sent a reader to change a graph that was already fine."""
    unid = themis.run(
        _unidentifiable_causation(with_theta=True)
    )["results"][0]
    pending = themis.run(_causation_program(monotonic=False))["results"][0]

    def _escape(result):
        return next(
            m for m in result["missing_information"]
            if m["name"] == "causation:interventional_risk_unavailable"
        )

    assert "在这张图上不可识别" in _escape(unid)["reason"]
    assert "可识别，但算不出数" in _escape(pending)["reason"]


def test_causation_states_its_tier_once_it_has_the_numbers():
    """The half of the disagreement that was real. Theta lets the risks be
    derived, the Tian-Pearl bounds come out, and without monotonicity they
    stay bounds — a tier ``themis.estimate`` has always written for the
    same query and ``themis.run`` used to withhold."""
    def prob(target, value, given=(), p=0.5):
        return {"kind": "probability",
                "target": {"atom": _atom(target), "value": value},
                "given": [{"atom": _atom(g), "value": v} for g, v in given],
                "value": p}

    program = {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            _var("x"), _var("y"), _cause("x", "y"),
            prob("x", True, p=0.4), prob("x", False, p=0.6),
            prob("y", True, (("x", True),), 0.7),
            prob("y", False, (("x", True),), 0.3),
            prob("y", True, (("x", False),), 0.2),
            prob("y", False, (("x", False),), 0.8),
            {"kind": "query", "id": "q", "query": {
                "kind": "causation",
                "cause": _atom("x"), "effect": _atom("y"),
                "monotonic": False,
            }},
        ],
    }
    result = themis.run(program)["results"][0]
    assert result["status"] == "counterfactual_bounded"
    assert _tier(result) == "interval"


def test_a_probability_query_states_its_tier():
    """Point, and only ever point — it is an observational conditional."""
    assert _tier(themis.run(_probability_program())["results"][0]) == "point"


def test_a_graph_question_states_no_tier():
    """Lifting the gate onto every kind would have handed cause and assoc a
    tier of ``point``: 105 results in one suite run, each claiming a number
    is one dataset away from a question that asks for no number."""
    program = {
        "version": "0.1",
        "domain": _OBJECTS,
        "statements": [
            _var("x"), _var("y"), _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }
    result = themis.run(program)["results"][0]
    assert result["data_gap_report"] is not None   # framing notes keep it
    assert _tier(result) is None


# --- the kinds the estimation layer was already tiering ------------------------


def _scm_counterfactual_program():
    """Pearl's Joe (Primer §4.2), with the H→Y coefficient dropped so the
    SCM is under-specified and the query stops before the numbers."""
    X = _atom("X", "joe")
    H = _atom("H", "joe")
    Y = _atom("Y", "joe")
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "joe"}]},
        "statements": [
            {"kind": "cause", "from": X, "to": H, "coefficient": 0.5},
            {"kind": "cause", "from": X, "to": Y, "coefficient": 0.7},
            {"kind": "cause", "from": H, "to": Y},
            {"kind": "observation", "atom": X, "value": 0.5},
            {"kind": "observation", "atom": H, "value": 1.0},
            {"kind": "observation", "atom": Y, "value": 1.5},
            {"kind": "query", "id": "q", "query": {
                "kind": "scm_counterfactual",
                "intervention": {"atom": H, "value": 2.0},
                "target": Y,
            }},
        ],
    }


def _proximal_program():
    """Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y, U unobserved."""
    def var(p):
        return {"kind": "variable", "predicate": p, "domain": [True, False]}

    def edge(a, b):
        return {"kind": "cause", "from": {"predicate": a, "args": []},
                "to": {"predicate": b, "args": []}}

    def atom(p):
        return {"predicate": p, "args": []}

    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            var("x"), var("y"), var("u"), var("z"), var("w"),
            edge("u", "x"), edge("u", "y"), edge("u", "z"), edge("u", "w"),
            edge("z", "x"), edge("w", "y"), edge("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": atom("x"), "outcome": atom("y"),
                "latent": atom("u"), "treatment_proxy": atom("z"),
                "outcome_proxy": atom("w"), "latent_cardinality": 2,
            }},
        ],
    }


def _conjunction_program():
    """X → Y, γ = (Y_{X=1} = 1): identified, so ID* returns a formula."""
    def var(p):
        return {"kind": "variable", "predicate": p, "domain": [True, False]}

    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            var("x"), var("y"),
            {"kind": "cause", "from": {"predicate": "x", "args": []},
             "to": {"predicate": "y", "args": []}},
            {"kind": "query", "id": "q", "query": {
                "kind": "counterfactual_conjunction",
                "events": [{
                    "variable": {"predicate": "y", "args": []},
                    "subscript": [{"atom": {"predicate": "x", "args": []},
                                   "value": True}],
                    "value": True,
                }],
            }},
        ],
    }


@pytest.mark.parametrize("name, program", [
    ("scm_counterfactual", _scm_counterfactual_program()),
    ("proximal_effect", _proximal_program()),
    ("counterfactual_conjunction", _conjunction_program()),
])
def test_the_kinds_an_estimator_would_tier_are_tiered_without_one(name, program):
    """Cross-entrance agreement, which is what the suppressed gate broke:
    ``themis.estimate`` wrote a tier for these kinds from the number it
    produced while ``themis.run`` left the field off the same query."""
    result = themis.run(program)["results"][0]
    assert result["query_kind"] == name
    assert _tier(result) is not None
