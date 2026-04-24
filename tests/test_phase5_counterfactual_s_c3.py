"""Phase 5 §C / S.C.3: narrow Balke-Pearl bounds primitive."""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.counterfactual import (
    CounterfactualBoundsError,
    balke_pearl_bounds_binary_monotone,
    project_twin_network,
)
from themis.types import (
    Atom,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    Intervention,
    Monotonicity,
    NumericInterval,
    ValuedAtom,
)


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _base_query(
    *,
    monotonicity: Monotonicity | None = Monotonicity.NON_DECREASING,
    x_obs: bool = False,
    x_cf: bool = True,
    y_cf: bool = True,
    factual_y: bool | None = None,
) -> CounterfactualQuery:
    x = _atom("treat")
    y = _atom("recover")
    return CounterfactualQuery(
        observed=ValuedAtom(atom=x, value=x_obs),
        counterfactual_intervention=Intervention(atom=x, value=x_cf),
        counterfactual_target=ValuedAtom(atom=y, value=y_cf),
        assumptions=(
            None
            if monotonicity is None
            else CounterfactualAssumptions(monotonicity=monotonicity)
        ),
        factual_target_known=factual_y,
    )


def _twin(query: CounterfactualQuery):
    x = query.observed.atom
    y = query.counterfactual_target.atom
    g = nx.DiGraph()
    g.add_edge(x, y)
    return project_twin_network(g, frozenset(), query)


def test_sc3_returns_point_interval_by_consistency_when_worlds_match():
    query = _base_query(x_obs=False, x_cf=False, y_cf=True)
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    got = balke_pearl_bounds_binary_monotone(_twin(query), query, joint)

    assert got == NumericInterval(low=0.4, high=0.4)


def test_sc3_returns_point_interval_from_known_factual_target_when_worlds_match():
    query = _base_query(x_obs=False, x_cf=False, y_cf=True, factual_y=True)
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    got = balke_pearl_bounds_binary_monotone(_twin(query), query, joint)

    assert got == NumericInterval(low=1.0, high=1.0)


def test_sc3_non_decreasing_bounds_for_y_true_without_factual_target():
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=False,
        x_cf=True,
        y_cf=True,
    )
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    got = balke_pearl_bounds_binary_monotone(_twin(query), query, joint)

    assert got == NumericInterval(low=0.4, high=1.0)


def test_sc3_non_increasing_bounds_for_y_true_without_factual_target():
    query = _base_query(
        monotonicity=Monotonicity.NON_INCREASING,
        x_obs=False,
        x_cf=True,
        y_cf=True,
    )
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    got = balke_pearl_bounds_binary_monotone(_twin(query), query, joint)

    assert got == NumericInterval(low=0.0, high=0.4)


def test_sc3_returns_complement_interval_for_y_false():
    query = _base_query(
        monotonicity=Monotonicity.NON_DECREASING,
        x_obs=False,
        x_cf=True,
        y_cf=False,
    )
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    got = balke_pearl_bounds_binary_monotone(_twin(query), query, joint)

    assert got == NumericInterval(low=0.0, high=0.6)


def test_sc3_rejects_missing_monotonicity():
    query = _base_query(monotonicity=None)
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.4,
    }

    with pytest.raises(CounterfactualBoundsError, match="monotonicity"):
        balke_pearl_bounds_binary_monotone(_twin(query), query, joint)


def test_sc3_rejects_incomplete_joint_table():
    query = _base_query()
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, True): 0.5,
    }

    with pytest.raises(CounterfactualBoundsError, match="four binary cells"):
        balke_pearl_bounds_binary_monotone(_twin(query), query, joint)


def test_sc3_rejects_joint_table_that_does_not_sum_to_one():
    query = _base_query()
    joint = {
        (False, False): 0.3,
        (False, True): 0.2,
        (True, False): 0.1,
        (True, True): 0.5,
    }

    with pytest.raises(CounterfactualBoundsError, match="sum to 1"):
        balke_pearl_bounds_binary_monotone(_twin(query), query, joint)
