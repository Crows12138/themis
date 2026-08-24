"""Regression tests for scheduler dispatch completeness.

The four-state contract says every in-language query must surface a
result. Slice-1 must not silently drop queries whose solver is not
yet implemented.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    Atom,
    CauseStatement,
    ConstTerm,
    IdentifyQuery,
    Intervention,
    MissingKind,
    Program,
    QueryKind,
    QueryStatement,
    ResultStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = PROJECT_ROOT / "minimal_example_v0_1.json"


def test_dispatch_all_returns_one_result_per_query() -> None:
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))

    queries = [s for s in program.statements if isinstance(s, QueryStatement)]
    results = dispatch_all(program, graph)

    assert len(results) == len(queries), (
        "dispatch_all must return one result per query statement, "
        "never silently drop unsupported kinds"
    )

    ids = [r.query_id for r in results]
    assert ids == [q.id for q in queries]


def test_all_query_kinds_surface_results() -> None:
    """Every in-language query produces a result (never silently dropped).

    After slice 6 the numeric dispatch paths consult a real Theta built
    from the program's probability statements. For minimal_example:

    - q_prob_1 asks P(cancer=true | tar=true), which is exactly the
      declared CPT entry → NUMERICALLY_SOLVED with value 0.2.
    - q_effect_1 needs P(cancer=true | smokes=false); Theta has no
      such entry → NEEDS_INVESTIGATION with a precise missing parameter.
    - cause / identify stay structural as before.
    """
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    by_id = {r.query_id: r for r in dispatch_all(program, graph)}

    assert by_id["q_cause_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_cause_1"].query_kind is QueryKind.CAUSE
    assert by_id["q_identify_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_identify_1"].query_kind is QueryKind.IDENTIFY

    r_prob = by_id["q_prob_1"]
    assert r_prob.status is ResultStatus.NUMERICALLY_SOLVED
    assert r_prob.query_kind is QueryKind.PROBABILITY
    assert r_prob.numeric_result is not None
    assert r_prob.numeric_result.value == 0.2

    r_effect = by_id["q_effect_1"]
    assert r_effect.status is ResultStatus.NEEDS_INVESTIGATION
    assert r_effect.query_kind is QueryKind.EFFECT
    assert r_effect.missing_information
    assert any(
        m.name.startswith("parameter:") or m.name.startswith("numeric:")
        for m in r_effect.missing_information
    ), [m.name for m in r_effect.missing_information]


def test_needs_investigation_auto_populates_investigation_requests() -> None:
    """Any needs_investigation result with missing_information should
    carry matching investigation_requests pushed by the runtime."""
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    for r in dispatch_all(program, graph):
        if r.status is ResultStatus.NEEDS_INVESTIGATION and r.missing_information:
            assert r.investigation_requests, (
                f"{r.query_id}: missing_information present but no "
                f"investigation_requests attached"
            )
            assert len(r.investigation_requests) == len(r.missing_information)


def test_missing_parameter_formatter_handles_non_empty_given() -> None:
    """Regression: _missing_parameter_from_key previously projected
    (Atom, value) -> (predicate, value) before sorting and then tried
    to call .predicate on the projected string, crashing with
    AttributeError on any conditional lookup."""
    from themis import gaps
    from themis.runtime.scheduler import _missing_parameter_from_key
    from themis.runtime.numeric_estimator import ProbabilityKey
    from themis.types import Atom, ConstTerm, MissingKind

    y = Atom(predicate="y", args=(ConstTerm(name="a"),))
    x1 = Atom(predicate="x1", args=(ConstTerm(name="a"),))
    x2 = Atom(predicate="x2", args=(ConstTerm(name="a"),))
    key = ProbabilityKey(
        target_atom=y,
        target_value=True,
        given=frozenset({(x1, True), (x2, False)}),
    )
    item = _missing_parameter_from_key(
        key, need=gaps.Need.THETA_ENTRY_MISSING, key="P(...)",
    )
    assert item.kind is MissingKind.PARAMETER
    # Both atoms appear in the formatted name, sorted by predicate.
    assert "x1=True" in item.name
    assert "x2=False" in item.name
    assert item.name.startswith("parameter:P(y=True|")
    # …and beside the rendered name, what measuring would settle it.
    assert item.observable.variables == ("x1", "x2", "y")
    assert item.observable.population is None


def test_a_parameter_ask_says_which_population_would_settle_it() -> None:
    """A key tagged with a population names a different sample.

    The pass that drops the asks a supplied DataFrame answers reads this
    field: the study sample measuring x and y does not settle P*(y|x) on
    the transport target, however many of the variables it holds. Without
    the population travelling with the item, the two asks are
    indistinguishable once the name has been rendered.
    """
    from themis import gaps
    from themis.runtime.scheduler import _missing_parameter_from_key
    from themis.runtime.numeric_estimator import ProbabilityKey
    from themis.types import Atom, ConstTerm

    y = Atom(predicate="y", args=(ConstTerm(name="a"),))
    x = Atom(predicate="x", args=(ConstTerm(name="a"),))
    item = _missing_parameter_from_key(
        ProbabilityKey(
            target_atom=y, target_value=True,
            given=frozenset({(x, True)}), population="target",
        ),
        need=gaps.Need.THETA_ENTRY_MISSING, key="P*(y|x)",
    )
    assert item.observable.variables == ("x", "y")
    assert item.observable.population == "target"


def test_an_unresolved_query_bound_names_nothing_to_measure() -> None:
    """No key, no observation: the formula carried a query-bound atom with
    no value, which no sample repairs. ``observable`` stays None rather
    than becoming an empty variable list — a sample measuring nothing is
    not the same claim as no sample helping."""
    from themis import gaps
    from themis.runtime.scheduler import _missing_parameter_from_key

    item = _missing_parameter_from_key(
        None, need=gaps.Need.QUERY_BOUND_ATOM_UNRESOLVED,
    )
    assert item.name == "numeric:unresolved_query_bound"
    assert item.observable is None


def test_confidence_is_routed_through_composite_for_every_query() -> None:
    """confidence_calc.composite must be on the dispatch path for
    every query. Structural queries contribute no inputs so their
    composite is None; numeric queries that match an annotated source
    inherit the slot confidence per RFC §3.3."""
    from unittest.mock import patch

    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    with patch(
        "themis.runtime.scheduler.confidence_calc.composite",
        wraps=__import__(
            "themis.runtime.confidence_calc",
            fromlist=["composite"],
        ).composite,
    ) as spy:
        results = dispatch_all(program, graph)

    # One call per dispatched query.
    num_queries = sum(
        1 for s in program.statements
        if s.__class__.__name__ == "QueryStatement"
    )
    assert spy.call_count == num_queries

    by_id = {r.query_id: r for r in results}

    # Structural queries always contribute nothing -> None composite.
    assert by_id["q_cause_1"].confidence is None
    assert by_id["q_identify_1"].confidence is None

    # minimal_example_v0_1.json's probability statement carries
    # annotations.confidence = 0.82 on P(cancer=true | tar=true).
    # q_prob_1 asks exactly that conditional, so slice-9 collection
    # feeds 0.82 into composite -> 0.82.
    assert by_id["q_prob_1"].confidence == pytest.approx(0.82)

    # q_effect_1 asks P(cancer=true | do(smokes=false)); the back-door
    # formula references P(cancer=true | smokes=false) which has no
    # source statement in the fixture -> no slot -> None.
    assert by_id["q_effect_1"].confidence is None


def test_identify_invalid_given_descendant_is_not_emitted_as_negative_proof() -> None:
    """Regression for V3: a `given` that violates backdoor
    preconditions (descendant of X) must not surface as a
    structurally-solved negative identify proof, because the verifier
    correctly rejects `unidentifiable_via_backdoor` on that context."""

    def atom(pred: str) -> Atom:
        return Atom(predicate=pred, args=(ConstTerm(name="me"),))

    from themis import gaps

    x = atom("x")
    z = atom("z")
    y = atom("y")
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            CauseStatement(from_atom=x, to_atom=z),
            CauseStatement(from_atom=z, to_atom=y),
            QueryStatement(
                id="q_invalid_given",
                query=IdentifyQuery(
                    target=y,
                    intervention=Intervention(atom=x, value=True),
                    given=(z,),
                ),
            ),
        ),
    )
    graph = project(instantiate(program))
    result = dispatch_all(program, graph)[0]

    assert result.status is ResultStatus.NEEDS_INVESTIGATION
    assert result.query_kind is QueryKind.IDENTIFY
    assert result.derivation == ()
    assert result.structural_result is None
    assert result.missing_information
    assert result.missing_information[0].kind is MissingKind.STRUCTURE
    assert result.missing_information[0].need is (
        gaps.Need.GIVEN_VIOLATES_BACKDOOR)


# ===================================== what an ObservationalJoint may say
#
# The counterfactual and causation doors decide whether they got the
# observational joint by asking ``ObservationalJoint.cells`` — the right
# field, because it is the one they go on to index. What that costs is the
# direction a broken producer fails in: a guard on ``cells`` has an answer
# for the combination that a subscript on ``cells`` did not. The first two
# pin the refusal that buys the direction back, at construction rather
# than at whatever reads the thing next; the third checks that on the live
# producer the reader still gets the names.


def test_a_joint_with_no_cells_must_name_what_it_lacked() -> None:
    """Prevents a needs_investigation that asks for data and names none.

    A producer reporting no cells while naming nothing missing used to
    hand ``None`` downstream and crash there, loudly, at the first
    subscript. Once the doors guard on ``cells`` that same producer sails
    through the guard instead and returns needs_investigation with an
    empty ``missing_information`` — the reader is told to go and measure
    something and never told what, and the causation door emits a gap
    report with no gaps in it. A silent uninformative degradation is
    worse than the crash it replaced, so the combination is refused at
    construction: the failure stays at the producer, which is the last
    place where the name of the missing thing still exists.
    """
    from themis.runtime.scheduler import ObservationalJoint

    with pytest.raises(ValueError, match="no cells"):
        ObservationalJoint(None, (), None)


def test_a_joint_that_carries_cells_must_not_also_name_a_shortfall() -> None:
    """The mirror: this one loses the shortfall rather than the answer.

    On the branch where the cells are present, no door reads ``missing``
    again — so a producer that filled the cells *and* named something it
    lacked would have the door compute an answer over those cells and
    drop the shortfall unread. Both halves of the biconditional are
    refused because both of them turn an incomplete recovery into a
    report that does not admit to being one.
    """
    from themis.runtime.scheduler import ObservationalJoint
    from themis.types import GapKind, MissingItem, Priority

    cells = {
        (x, y): 0.25 for x in (False, True) for y in (False, True)
    }
    shortfall = MissingItem(
        kind=MissingKind.PARAMETER,
        name="parameter:P(y=True|x=True)",
        priority=Priority.HIGH,
        gap=GapKind.MISSING_DISTRIBUTION,
    )
    with pytest.raises(ValueError, match="nothing missing"):
        ObservationalJoint(cells, (shortfall,), None)


def test_a_theta_short_of_the_joint_reaches_both_doors_with_names() -> None:
    """The property the refusal above exists to protect, on the live producer.

    Same graph, same query, a theta holding P(X) and no P(Y|X): the
    honest report is needs_investigation naming the four conditionals
    nobody supplied. Both doors are asked because they are two routes
    onto one quantity, and the counterfactual cell being one of the
    causation door's cells is exactly why a shortfall that reaches one of
    them anonymously would reach the other one anonymously too.
    """
    import themis

    def atom(pred: str) -> dict:
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    def marginal(value: bool, v: float) -> dict:
        return {
            "kind": "probability",
            "target": {"atom": atom("x"), "value": value},
            "given": [],
            "value": v,
        }

    def program(query: dict) -> dict:
        return {
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "cause", "from": atom("x"), "to": atom("y")},
                marginal(False, 0.6),
                marginal(True, 0.4),
                {"kind": "query", "id": "q", "query": query},
            ],
        }

    doors = {
        "counterfactual": {
            "kind": "counterfactual",
            "observed": {"atom": atom("x"), "value": True},
            "counterfactual_intervention": {"atom": atom("x"), "value": False},
            "counterfactual_target": {"atom": atom("y"), "value": False},
            "factual_target_known": True,
        },
        "causation": {
            "kind": "causation", "cause": atom("x"), "effect": atom("y"),
        },
    }

    for door, query in doors.items():
        result = themis.run(program(query))["results"][0]
        assert result["status"] == "needs_investigation", door
        named = {m["name"] for m in result["missing_information"]}
        assert {
            "parameter:P(y=False|x=False)",
            "parameter:P(y=False|x=True)",
            "parameter:P(y=True|x=False)",
            "parameter:P(y=True|x=True)",
        } <= named, (door, sorted(named))
