"""A probability model, as the cells it stands for.

A :class:`~themis.types.ProbabilityModel` states the probability of one
value of a target under every combination of its conditions by one of
those cells — the baseline, with every condition at its reference value —
and, for each other value of each condition, the factor it multiplies the
odds of that value by. Under the one form there is, ``odds_ratios``, the
factors multiply whatever the other conditions are:

    odds(target | c) = odds(baseline) × Π ratio(condition = c_i)

and a probability is its odds over one plus its odds.

Expanded here, once, into the :class:`~themis.types.ProbabilityStatement`
cells it stands for — the value it names under every combination, and
where the target takes one other value, that value at the complement — so
that everything which reads a parameter reads ordinary cells and none of it
has to know what a model is. The verifier holds the expansion to the
program independently (:mod:`themis.verifier.probability_model_rules`).
"""
from __future__ import annotations

import math
from itertools import product

from ..types import AtomValue, ProbabilityModel, ProbabilityStatement, ValuedAtom


def complement_values(model: ProbabilityModel,
                      domains: dict[str, tuple[AtomValue, ...]]) -> tuple[AtomValue, ...]:
    """The target value whose probability is the model's complement, as a
    tuple of it or of nothing. It is the target's other value when the
    target declares two, or declares none and is a yes-or-no; a target with
    three values or more has no one value the rest of the probability
    belongs to.
    """
    value = model.target.value
    declared = domains.get(model.target.atom.predicate)
    if declared is not None:
        others = tuple(v for v in declared
                       if not (v == value and type(v) is type(value)))
        return others if len(others) == 1 else ()
    return (not value,) if isinstance(value, bool) else ()


def expand(model: ProbabilityModel,
           domains: dict[str, tuple[AtomValue, ...]]) -> tuple[ProbabilityStatement, ...]:
    """Every cell ``model`` stands for — the value it names and, where
    there is one, the complement's (:func:`complement_values`) — under each
    combination of the conditions' values, in the order ``given`` lists the
    conditions and, within one, its reference and then its ratios.

    ``domains`` are the declared domains by predicate; they decide only
    whether the target has an other value and which, since a condition's
    values are the model's own (its reference and its ratios') and
    validation holds them to the declaration.
    """
    baseline = model.baseline.value
    odds = baseline / (1.0 - baseline)
    levels = [((g.atom, g.value, 1.0),
               *((r.atom, r.value, r.odds_ratio)
                 for r in model.odds_ratios if r.atom == g.atom))
              for g in model.given]
    others = complement_values(model, domains)
    cells: list[ProbabilityStatement] = []
    for combination in product(*levels):
        scaled = odds * math.prod(r for _, _, r in combination)
        # Odds past what a float holds are a probability of one; the
        # quotient of two infinities is not.
        p = 1.0 if math.isinf(scaled) else scaled / (1.0 + scaled)
        given = tuple(ValuedAtom(atom=a, value=v) for a, v, _ in combination)
        for value, probability in ((model.target.value, p),
                                   *((o, 1.0 - p) for o in others)):
            cells.append(ProbabilityStatement(
                target=ValuedAtom(atom=model.target.atom, value=value),
                given=given,
                value=probability,
                population=model.population,
                provenance=model.provenance,
                llm_prior=model.llm_prior,
            ))
    return tuple(cells)
