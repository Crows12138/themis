"""A probability model, as the cells it stands for.

A :class:`~themis.types.ProbabilityModel` states one conditional
distribution of a two-valued target by one of its cells — the baseline,
with every condition at its reference value — and, for each other value of
each condition, the factor it multiplies the target's odds by. Under the
one form there is, ``odds_ratios``, the factors multiply whatever the other
conditions are:

    odds(target | c) = odds(baseline) × Π ratio(condition = c_i)

and a probability is its odds over one plus its odds.

Expanded here, once, into the :class:`~themis.types.ProbabilityStatement`
cells it stands for — both values of the target under every combination —
so that everything which reads a parameter reads ordinary cells and none of
it has to know what a model is. The verifier holds the expansion to the
program independently (:mod:`themis.verifier.probability_model_rules`).
"""
from __future__ import annotations

import math
from itertools import product

from ..types import AtomValue, ProbabilityModel, ProbabilityStatement, ValuedAtom


def other_value(model: ProbabilityModel,
                domains: dict[str, tuple[AtomValue, ...]]) -> AtomValue:
    """The target value whose probability is the model's complement."""
    value = model.target.value
    declared = domains.get(model.target.atom.predicate)
    if declared is not None:
        return next(v for v in declared if not (v == value and type(v) is type(value)))
    return not value


def expand(model: ProbabilityModel,
           domains: dict[str, tuple[AtomValue, ...]]) -> tuple[ProbabilityStatement, ...]:
    """Every cell ``model`` stands for, both target values under each
    combination of the conditions' values, in the order ``given`` lists the
    conditions and, within one, its reference and then its ratios.

    ``domains`` are the declared domains by predicate; they decide only
    which value is the target's other one, since a condition's values are
    the model's own (its reference and its ratios') and validation holds
    them to the declaration.
    """
    baseline = model.baseline.value
    odds = baseline / (1.0 - baseline)
    levels = [((g.atom, g.value, 1.0),
               *((r.atom, r.value, r.odds_ratio)
                 for r in model.odds_ratios if r.atom == g.atom))
              for g in model.given]
    other = other_value(model, domains)
    cells: list[ProbabilityStatement] = []
    for combination in product(*levels):
        scaled = odds * math.prod(r for _, _, r in combination)
        # Odds past what a float holds are a probability of one; the
        # quotient of two infinities is not.
        p = 1.0 if math.isinf(scaled) else scaled / (1.0 + scaled)
        given = tuple(ValuedAtom(atom=a, value=v) for a, v, _ in combination)
        for value, probability in ((model.target.value, p), (other, 1.0 - p)):
            cells.append(ProbabilityStatement(
                target=ValuedAtom(atom=model.target.atom, value=value),
                given=given,
                value=probability,
                population=model.population,
                provenance=model.provenance,
            ))
    return tuple(cells)
