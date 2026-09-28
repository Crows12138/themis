"""What a filler is asked for, and what its answers become.

The kernel lists the probabilities an answer is short of, one skeleton per
cell (``investigation_requests``). Two fillers answer them on this site: a
language model asked for commonsense priors, and a reader typing in numbers
they have. Both are asked the same questions, which this module decides:
each skeleton as the kernel listed it, except that the cells of one
conditional distribution are asked for as a table — a baseline and an odds
ratio for each other value of each condition — wherever that is fewer
numbers than the cells (:func:`tables`). And what either filler answers
becomes the same records: a skeleton filled, or a ``probability_model`` in
the place of the skeletons it states. The records differ in one field,
whether a language model supplied the number.

It lived in the model's bridge while the model was the only filler, and a
reader offered the same table would have been offered it by a second copy
of the rule deciding when a table is fewer numbers. A table is one question
whoever answers it.

Nothing here refuses an answer. What is wrong with a number is said by
whoever received it: the bridge refuses a model's reply in its own words,
and the kernel holds a reader's records to every rule a program is held to.
"""
from __future__ import annotations

import json
from typing import NamedTuple


class Table(NamedTuple):
    """Rows of one conditional distribution, asked for as a model.

    ``given`` holds each condition at its reference value and ``ratios``
    each condition at another, in the order the conditions and their
    declared values come; ``rows`` are the skeletons it answers, and
    ``provenance`` the kind of conditional they say they are, where they
    say one — the same for every row, since it follows from the target and
    the conditions, which the rows share.
    """
    rows: tuple[int, ...]
    target: dict
    given: tuple[dict, ...]
    ratios: tuple[dict, ...]
    population: str | None
    provenance: str | None



# ------------------------------------------------------------ how it reads


def atom_label(atom: dict) -> str:
    """`{"predicate": "veg", "args": [...]}` -> `veg`: the args are dropped,
    since a number is per unit and the predicate is what a filler weighs."""
    return str((atom or {}).get("predicate", "?"))


def valued_label(valued: dict) -> str:
    return f"{atom_label(valued.get('atom', {}))}={valued.get('value')}"


def cell_label(skeleton: dict) -> str:
    """A skeleton as `P(target=v | g1=v1, g2=v2)`, so a filler weighs a
    readable quantity rather than raw JSON."""
    head = valued_label(skeleton.get("target", {}))
    given = skeleton.get("given") or []
    if not given:
        return f"P({head})"
    return f"P({head} | {', '.join(valued_label(g) for g in given)})"


def table_label(t: Table) -> str:
    conditions = ", ".join(atom_label(g.get("atom", {})) for g in t.given)
    return f"P({atom_label(t.target.get('atom', {}))} | {conditions})"


def baseline_label(t: Table) -> str:
    return (f"P({valued_label(t.target)} | "
            f"{', '.join(valued_label(g) for g in t.given)})")


def reference_of(t: Table, ratio: dict) -> dict:
    return next(g for g in t.given if g.get("atom") == ratio.get("atom"))


def ratio_label(t: Table, j: int) -> str:
    ratio = t.ratios[j]
    return (f"OR({valued_label(t.target)} | {valued_label(ratio)}"
            f"/{reference_of(t, ratio).get('value')})")


def numbers(request: dict | Table) -> int:
    """How many numbers a request asks for: a cell is one, a table its
    baseline and each of its ratios."""
    return 1 + len(request.ratios) if isinstance(request, Table) else 1


def shown(i: int, request: dict | Table) -> dict:
    """One request as a filler is shown it, under its index."""
    if isinstance(request, Table):
        return {
            "index": i,
            "table": table_label(request),
            "baseline": baseline_label(request),
            "ratios": [{"ratio": j, "condition": valued_label(r),
                        "against": valued_label(reference_of(request, r))}
                       for j, r in enumerate(request.ratios)],
        }
    return {"index": i, "probability": cell_label(request)}


# ------------------------------------------------------- what is asked


def _reference(domain: list) -> object:
    """The value a condition's ratios are relative to: its absence where it
    is a yes-or-no, and otherwise the first value it declares."""
    return False if any(v is False for v in domain) else domain[0]


def tables(program: dict, skeletons: list[dict]) -> dict[int, Table]:
    """The rows asked for as tables, keyed by the first row of each.

    One conditional distribution — one target under the same conditions in
    one population — is asked for as a baseline and an odds ratio for each
    other value of each condition, rather than cell by cell, when it can
    be: the model's cells are its rows, because the rows ask one value of
    the target, or the target takes two values and the other's is the
    complement; each condition has two values or more to give a ratio
    between; the program states none of its cells, since a model states
    every cell and one already written would then be stated twice; and it
    is fewer numbers than the rows are. The rows are counted by the
    combinations of conditions they are asked at, which is how many numbers
    they are when the two values of a target come in one combination, and
    a table is not asked for at as many numbers or more: the cells say the
    same without assuming how the conditions combine. With one condition
    it never is fewer, and a few rows of a large table are fewer cells than
    the table's numbers.

    A condition's values are the ones it declares, where it declares them,
    since the model is held to a declaration. Where it declares none, one
    asked at true or false is a yes-or-no, as an undeclared target is read
    — which matters for a condition the question sets: the kernel asks the
    table under do(x) at x's one value, and x is still a condition with
    two. Otherwise they are the values the kernel asks the table at, which
    are the values it reads it at.

    That is what a person knows of such a table — how common the target
    is, and how much each condition moves it — and it is k + 1 numbers
    where the cells are 2^k. What it assumes is said beside the answer.
    """
    statements = [s for s in program.get("statements") or ()
                  if isinstance(s, dict)]
    declared = {s.get("predicate"): list(s["domain"]) for s in statements
                if s.get("kind") == "variable" and s.get("domain")}

    def values(atom: dict, asked: list) -> list:
        """The values of the condition ``atom``, asked at ``asked``."""
        predicate = atom_label(atom)
        if predicate in declared:
            return declared[predicate]
        if asked and all(isinstance(v, bool) for v in asked):
            return [True, False]
        return asked

    def asked_at(rows: list[int], atom: object) -> list:
        return list(dict.fromkeys(
            g.get("value") for i in rows for g in skeletons[i].get("given") or ()
            if g.get("atom") == atom))

    def which(record: dict) -> tuple:
        atom = json.dumps((record.get("target") or {}).get("atom"),
                          sort_keys=True)
        given = frozenset(json.dumps(g.get("atom"), sort_keys=True)
                          for g in record.get("given") or ())
        return atom, given, record.get("population")

    stated = {which(s) for s in statements
              if s.get("kind") in ("probability", "probability_model")}
    groups: dict[tuple, list[int]] = {}
    for i, sk in enumerate(skeletons):
        groups.setdefault(which(sk), []).append(i)
    found: dict[int, Table] = {}
    for key, rows in groups.items():
        first = skeletons[rows[0]]
        target = first.get("target") or {}
        given = list(first.get("given") or ())
        asked = {json.dumps((skeletons[i].get("target") or {}).get("value"))
                 for i in rows}
        target_values = declared.get(atom_label(target.get("atom", {})))
        two_valued = (len(target_values) == 2 if target_values is not None
                      else isinstance(target.get("value"), bool))
        answered = len(asked) == 1 or two_valued
        domains = [values(g.get("atom") or {}, asked_at(rows, g.get("atom")))
                   for g in given]
        combinations = {
            frozenset((json.dumps(g.get("atom"), sort_keys=True),
                       json.dumps(g.get("value")))
                      for g in skeletons[i].get("given") or ())
            for i in rows}
        count = 1 + sum(len(d) - 1 for d in domains)
        if (key in stated or not answered or any(len(d) < 2 for d in domains)
                or count >= len(combinations)):
            continue
        references = [_reference(d) for d in domains]
        found[rows[0]] = Table(
            rows=tuple(rows),
            target={"atom": target.get("atom"), "value": target.get("value")},
            given=tuple({"atom": g.get("atom"), "value": ref}
                        for g, ref in zip(given, references)),
            ratios=tuple({"atom": g.get("atom"), "value": v}
                         for g, d, ref in zip(given, domains, references)
                         for v in d
                         if not (v == ref and type(v) is type(ref))),
            population=first.get("population"),
            provenance=first.get("provenance"),
        )
    return found


def requests(program: dict, skeletons: list[dict]) -> list[dict | Table]:
    """What a filler is asked for, in the order the kernel listed the
    skeletons: the skeletons a table answers give way to the table, where
    the first of them was, and every other skeleton is asked for itself."""
    found = tables(program, skeletons)
    tabled = {i for t in found.values() for i in t.rows}
    return [found.get(i, sk) for i, sk in enumerate(skeletons)
            if i in found or i not in tabled]


def cells(table: Table, skeletons: list[dict]) -> list[int]:
    """The rows of a table at the value it names, which are the table cell
    by cell: where the kernel also asked the other value of a two-valued
    target, the kernel completes that one from these."""
    named = json.dumps(table.target.get("value"))
    return [i for i in table.rows
            if json.dumps((skeletons[i].get("target") or {}).get("value"))
            == named]


# ------------------------------------------------- what an answer becomes


def cell_record(skeleton: dict, value: float, *, llm_prior: bool,
                source: str | None) -> dict:
    """The skeleton filled: its value, whether a language model supplied
    it, and the ground given for it. What the kernel wrote — the key, and
    the kind of conditional it asked for — is kept as written, because the
    statement that settles an ask is the one the kernel keyed it to. Its
    placeholder source is not: the ground a number stands on is whoever
    supplied it's to give, or there is none."""
    out = {k: v for k, v in skeleton.items() if k != "annotations"}
    out["value"] = value
    if llm_prior:
        out["llm_prior"] = True
    if source:
        out["annotations"] = {"source": source}
    return out


def model_record(table: Table, baseline: float, ratios: list[float], *,
                 llm_prior: bool, sources: dict | None = None) -> dict:
    """The ``probability_model`` a table's answer states. ``sources`` maps
    ``"baseline"`` and each ratio's index to the ground given for it."""
    sources = sources or {}

    def grounded(fields: dict, key: object) -> dict:
        source = sources.get(key)
        return {**fields, "annotations": {"source": source}} if source else fields

    model: dict[str, object] = {
        "kind": "probability_model",
        "form": "odds_ratios",
        "target": table.target,
        "given": list(table.given),
        "baseline": grounded({"value": baseline}, "baseline"),
        "odds_ratios": [grounded({**r, "odds_ratio": v}, j)
                        for j, (r, v) in enumerate(zip(table.ratios, ratios))],
    }
    if llm_prior:
        model["llm_prior"] = True
    if table.population is not None:
        model["population"] = table.population
    if table.provenance is not None:
        model["provenance"] = table.provenance
    return model
