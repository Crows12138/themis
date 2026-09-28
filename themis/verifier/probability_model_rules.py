"""A probability model, held to the cells an answer was computed from.

A program may state a conditional distribution as a baseline and one odds
ratio per condition (``kind: probability_model``). The kernel expands it
into ordinary probability cells before anything reads a parameter, and
the context an audit runs in is rebuilt by that same expansion — so on
this premise the audit had nothing of its own: an expansion that bent a
cell would be the expansion both sides read.

Held here from the program as the caller submitted it, not from the typed
model. Each model is ground over its ``forall`` again, each cell is
computed again by a different route — the log-odds summed and passed
through the logistic function, where the kernel multiplies odds — and
every cell must be in the parameter store with that value: the target's
value at ``p`` and its other value at ``1 - p``.

**Independence pin:** nothing here imports the runtime. The store is read
by its keys' attributes, as :mod:`themis.verifier.theta_rules` reads it.
"""
from __future__ import annotations

import math
from itertools import product

from .errors import VerificationError

#: Float rounding between two routes to the same number, not leniency.
TOLERANCE = 1e-9


def _logistic(logit: float) -> float:
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    e = math.exp(logit)
    return e / (1.0 + e)


def _literal(value) -> tuple[str, object]:
    """A value with its type: ``True`` and ``1`` are different values of a
    variable, though Python compares them equal."""
    return (type(value).__name__, value)


def _atom(atom: dict, subst: dict) -> tuple:
    """A program atom, ground, as the triple the store's atoms are read as."""
    args = tuple(subst.get(a.get("name"), a.get("name")) if a.get("type") == "var"
                 else a.get("name") for a in atom.get("args") or ())
    time = (atom.get("time_index") or {}).get("value")
    return (atom.get("predicate"), args, time)


def _stored(atom) -> tuple:
    time = getattr(atom, "time_index", None)
    return (atom.predicate, tuple(t.name for t in atom.args),
            None if time is None else time.value)


def _other(value, domain) -> object:
    if domain is not None:
        return next(v for v in domain if _literal(v) != _literal(value))
    return not value


def _cells(stmt: dict, subst: dict, domains: dict):
    """Each cell one ground copy of a model stands for, with its value."""
    atom = _atom(stmt["target"]["atom"], subst)
    value = stmt["target"]["value"]
    other = _other(value, domains.get(atom[0]))
    # The document has passed the schema by now, which requires each number
    # this reads.
    baseline = float(stmt["baseline"]["value"])
    levels = [
        [(_atom(g["atom"], subst), g["value"], 0.0)]
        + [(_atom(r["atom"], subst), r["value"], math.log(float(r["odds_ratio"])))
           for r in stmt["odds_ratios"]
           if _atom(r["atom"], subst) == _atom(g["atom"], subst)]
        for g in stmt["given"]
    ]
    population = stmt.get("population")
    for combination in product(*levels):
        p = _logistic(math.log(baseline) - math.log1p(-baseline)
                      + math.fsum(shift for _, _, shift in combination))
        given = frozenset((a, _literal(v)) for a, v, _ in combination)
        yield (atom, _literal(value), given, population), p
        yield (atom, _literal(other), given, population), 1.0 - p


def verify_models_are_their_cells(ast: dict, theta) -> None:
    """Raise :class:`VerificationError` at the first cell a model stands
    for that the parameter store lacks or holds at another value."""
    statements = [s for s in ast.get("statements") or () if isinstance(s, dict)]
    models = [s for s in statements if s.get("kind") == "probability_model"]
    if not models:
        return
    domains = {s.get("predicate"): tuple(s["domain"]) for s in statements
               if s.get("kind") == "variable" and s.get("domain")}
    objects = [o.get("name") for o in (ast.get("domain") or {}).get("objects") or ()]
    stored = {
        (_stored(k.target_atom), _literal(k.target_value),
         frozenset((_stored(a), _literal(v)) for a, v in k.given),
         k.population): float(p)
        for k, p in theta.entries.items()
    }
    for model in models:
        forall = list(model.get("forall") or ())
        for assignment in product(objects, repeat=len(forall)):
            subst = dict(zip(forall, assignment))
            for key, want in _cells(model, subst, domains):
                have = stored.get(key)
                if have is None or not abs(have - want) <= TOLERANCE:
                    (predicate, _, _), (_, value), given, population = key
                    conditions = ",".join(sorted(
                        f"{a[0]}={v!r}" for a, (_, v) in given))
                    head = "P" if population is None else f"P_{population}"
                    said = ("is not among the parameters" if have is None
                            else f"is {have!r} in the parameters")
                    raise VerificationError(
                        f"probability model: {head}({predicate}={value!r}|"
                        f"{conditions}) is {want!r} by the model's baseline "
                        f"and odds ratios, and {said}")
