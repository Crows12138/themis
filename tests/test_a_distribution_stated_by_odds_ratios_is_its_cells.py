"""A distribution stated by a baseline and odds ratios is the cells it stands for.

A graph whose outcome has k two-valued causes asks for 2^k numbers of one
conditional distribution. Nobody holds that table in their head: a reader,
or a language model, knows how common the outcome is and how much each
cause moves it. ``probability_model`` states the table that way — a
baseline, the probability with every condition at its reference, and one
odds ratio for each other value of each condition — and the kernel expands
it into its cells before anything reads a parameter.

The form is an assumption: each ratio holds whatever the other conditions
are. So where a language model supplied the numbers, the review lists each
of them with its own reason and the ledger states the assumption in a line
of its own; and because the context an audit runs in is rebuilt by the
same expansion, the verifier expands every model again by another route.
"""
from __future__ import annotations

import copy
import math
from itertools import product

import pytest

import themis
import themis.runtime.instantiation as instantiation
from themis.input.semantic_validator import Malformed, SemanticError, validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.instantiation import instantiate
from themis.types import ProbabilityStatement
from themis.verifier.errors import VerificationError


def _atom(p, who="me"):
    return {"predicate": p, "args": [{"type": "const", "name": who}]}


def _cell(t, tv, given, v):
    return {"kind": "probability", "target": {"atom": _atom(t), "value": tv},
            "given": [{"atom": _atom(g), "value": gv} for g, gv in given],
            "value": v}


def _why(text):
    return {"source": text}


def _model(conditions, baseline, *, prior=True, target="y"):
    """``conditions``: (predicate, reference, {value: ratio})."""
    model = {
        "kind": "probability_model", "form": "odds_ratios",
        "target": {"atom": _atom(target), "value": True},
        "given": [{"atom": _atom(p), "value": ref} for p, ref, _ in conditions],
        "baseline": {"value": baseline,
                     **({"annotations": _why("how common y is")} if prior else {})},
        "odds_ratios": [{"atom": _atom(p), "value": v, "odds_ratio": r,
                         **({"annotations": _why(f"{p}={v}")} if prior else {})}
                        for p, _, ratios in conditions for v, r in ratios.items()],
    }
    if prior:
        model["provenance"] = "llm_prior"
    return model


THREE = [("x", False, {True: 2.0}), ("z", False, {True: 1.5}),
         ("w", False, {True: 0.5})]
BASELINE = 0.2


def _program(table):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in "xyzw"),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            _cell("z", True, [], 0.4),
            _cell("w", True, [], 0.3),
            _cell("x", True, [("z", True)], 0.7),
            _cell("x", True, [("z", False)], 0.2),
            *table,
            {"kind": "query", "id": "q", "query": {"kind": "effect",
             "intervention": {"atom": _atom("x"), "value": True},
             "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _p(baseline, ratios):
    odds = baseline / (1 - baseline) * math.prod(ratios)
    return odds / (1 + odds)


def _run(program):
    return themis.run(program)["results"][0]


def _without(program, kind, predicate, end="target"):
    """``program`` less every statement of ``kind`` about ``predicate``."""
    def about(s):
        node = s.get(end) or {}
        return (node.get("atom") or node).get("predicate")
    out = copy.deepcopy(program)
    out["statements"] = [s for s in out["statements"]
                         if not (s.get("kind") == kind and about(s) == predicate)]
    return out


def _ledger_tokens(result):
    return [c["token"]
            for e in result["extensions"]["assumption_ledger"]["assumptions"]
            for c in e["claim"]]


# ============================================================ the cells


def test_each_cell_is_the_baseline_odds_times_the_ratios():
    """Every combination of every condition's values, the target's value
    at the model's probability and its other value at the complement —
    here with a three-valued condition, whose reference and two effects
    are its three values."""
    program = _program([])
    program["statements"][:0] = [
        {"kind": "variable", "predicate": "a", "domain": ["low", "mid", "high"]},
        {"kind": "cause", "from": _atom("a"), "to": _atom("y")},
    ]
    program["statements"].append(_model(
        [("a", "low", {"mid": 2.0, "high": 4.0}), ("x", False, {True: 0.5})],
        0.25, prior=False))
    ground = instantiate(validate_program(validate_ast(program)))
    cells = {(s.target.value, tuple(va.value for va in s.given)): s.value
             for s in ground if isinstance(s, ProbabilityStatement)
             and s.target.atom.predicate == "y"}
    ratio_a = {"low": 1.0, "mid": 2.0, "high": 4.0}
    ratio_x = {False: 1.0, True: 0.5}
    assert len(cells) == 2 * 3 * 2
    for a, x in product(ratio_a, ratio_x):
        p = _p(0.25, [ratio_a[a], ratio_x[x]])
        assert cells[(True, (a, x))] == pytest.approx(p, abs=1e-12)
        assert cells[(False, (a, x))] == pytest.approx(1 - p, abs=1e-12)


@pytest.mark.parametrize("domain", [["low", "mid", "high"], None],
                         ids=["three declared values", "none declared"])
def test_a_target_without_one_other_value_is_modelled_at_the_value_it_names(domain):
    """The model gives the probability of one value of its target. Where
    the target has one other value, that one's is the complement and is
    stated too; here it has none, so the model states the cells of the
    value it names and no others — the cells a question about that value
    asks for — and the audit's own expansion agrees."""
    model = _model(THREE, BASELINE)
    model["target"]["value"] = "high"
    program = _program([model])
    declaration = program["statements"][1]
    if domain is None:
        del declaration["domain"]
    else:
        declaration["domain"] = domain
    program["statements"][-1]["query"]["target"]["value"] = "high"
    ground = instantiate(validate_program(validate_ast(program)))
    cells = {(s.target.value, tuple(va.value for va in s.given)): s.value
             for s in ground if isinstance(s, ProbabilityStatement)
             and s.target.atom.predicate == "y"}
    assert {value for value, _ in cells} == {"high"}
    assert len(cells) == 2 ** 3
    for x, z, w in product((True, False), repeat=3):
        want = _p(BASELINE, [2.0 if x else 1, 1.5 if z else 1, 0.5 if w else 1])
        assert cells[("high", (x, z, w))] == pytest.approx(want, abs=1e-12)
    result = _run(program)
    assert result["status"] == "numerically_solved"
    themis.verify(program, result)


def test_every_value_a_model_names_sits_beside_its_atom():
    """What reads the levels a programme names — so a labelled column is
    not coded out from under them — reads them by shape: a value beside the
    atom whose column it is. A model is written that way, a reference in
    ``given`` and a value in each ratio, so its levels are read with no
    list of statement kinds kept in step."""
    from themis.estimation.declared import levels_named
    model = _model([("a", "low", {"mid": 2.0, "high": 4.0})], 0.25, prior=False)
    assert set(levels_named({"statements": [model]})["a"]) == {"low", "mid", "high"}


def test_the_answer_is_the_answer_its_cells_give():
    """A model and the same table written cell by cell are one program:
    one number, and each answer passes the audit."""
    by_model = _program([_model(THREE, BASELINE, prior=False)])
    by_cells = _program([
        _cell("y", True, [("x", x), ("z", z), ("w", w)],
              _p(BASELINE, [2.0 if x else 1, 1.5 if z else 1, 0.5 if w else 1]))
        for x, z, w in product((True, False), repeat=3)])
    modelled, written = _run(by_model), _run(by_cells)
    assert modelled["numeric_result"]["value"] == pytest.approx(
        written["numeric_result"]["value"], abs=1e-12)
    themis.verify(by_model, modelled)
    themis.verify(by_cells, written)
    # Numbers the caller wrote are not a language model's; nothing to review.
    assert "llm_proposed_review" not in (modelled.get("extensions") or {})


def test_a_model_is_ground_once_per_object_and_keeps_its_population():
    """Quantified, a model is one table per object, each keyed in the
    model's population — as a quantified cell is, which until this model
    arrived came out of grounding without its population or provenance."""
    prior = _model([("x", False, {True: 2.0})], 0.3)
    prior["forall"] = ["P"]
    prior["population"] = "trial"
    var = [{"type": "var", "name": "P"}]
    prior["target"]["atom"]["args"] = var
    prior["given"][0]["atom"]["args"] = var
    prior["odds_ratios"][0]["atom"]["args"] = var
    written = {"kind": "probability", "forall": ["P"], "population": "trial",
               "provenance": "llm_prior", "annotations": _why("base"),
               "target": {"atom": {"predicate": "x", "args": var}, "value": True},
               "given": [], "value": 0.4}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": n} for n in ("ann", "bo")]},
        "statements": [
            {"kind": "cause", "forall": ["P"], "from": {"predicate": "x", "args": var},
             "to": {"predicate": "y", "args": var}},
            written, prior,
        ],
    }
    cells = [s for s in instantiate(validate_program(validate_ast(program)))
             if isinstance(s, ProbabilityStatement)]
    assert {s.target.atom.args[0].name for s in cells} == {"ann", "bo"}
    assert len(cells) == 2 * (1 + 2 * 2)
    assert {(s.population, s.provenance) for s in cells} == {("trial", "llm_prior")}


# ============================================================ what a reader is shown


def test_a_language_models_parameters_are_each_a_line_under_review():
    """Each parameter is a number the model estimated on its own, so each
    is a line with its own reason; the model is listed beside them, named
    as a gap names the table it asks for; and the ledger carries each
    number and, once, the form's assumption."""
    program = _program([_model(THREE, BASELINE)])
    result = _run(program)
    review = result["extensions"]["llm_proposed_review"]
    assert review["probabilities"] == [
        {"key": "P(y(me)=True|x(me)=False,z(me)=False,w(me)=False)",
         "value": BASELINE, "reason": "how common y is"},
        {"key": "OR(y(me)=True|x(me)=True/False)", "value": 2.0, "reason": "x=True"},
        {"key": "OR(y(me)=True|z(me)=True/False)", "value": 1.5, "reason": "z=True"},
        {"key": "OR(y(me)=True|w(me)=True/False)", "value": 0.5, "reason": "w=True"},
    ]
    assert review["models"] == [{"distribution": "P(y | w, x, z)",
                                 "form": "odds_ratios",
                                 "conditions": ["x", "z", "w"]}]
    tokens = _ledger_tokens(result)
    assert tokens.count("a_commonsense_prior") == 4
    assert tokens.count("no_interaction") == 1
    themis.verify(program, result)


def test_one_condition_assumes_nothing():
    """A baseline and the ratios of one condition are the table itself, so
    the model is listed and the ledger says no assumption about its form."""
    program = _without(_program([
        _cell("y", True, [("x", x), ("z", z), ("w", w)], 0.5)
        for x, z, w in product((True, False), repeat=3)]), "probability", "x")
    program["statements"].append(
        _model([("z", False, {True: 3.0})], 0.2, target="x"))
    result = _run(program)
    assert result["extensions"]["llm_proposed_review"]["models"] == [
        {"distribution": "P(x | z)", "form": "odds_ratios", "conditions": ["z"]}]
    assert "no_interaction" not in _ledger_tokens(result)
    themis.verify(program, result)


def test_the_forms_line_is_owed_to_the_ledger():
    program = _program([_model(THREE, BASELINE)])
    result = _run(program)
    bent = copy.deepcopy(result)
    ledger = bent["extensions"]["assumption_ledger"]
    ledger["assumptions"] = [
        e for e in ledger["assumptions"]
        if all(c["token"] != "no_interaction" for c in e["claim"])]
    with pytest.raises(VerificationError):
        themis.verify_assumption_ledger(bent)


@pytest.mark.parametrize("edit", [
    lambda r: r.pop("models"),
    lambda r: r["models"][0]["conditions"].pop(),
    lambda r: r["probabilities"][1].update(value=1.0),
    lambda r: r["probabilities"].pop(0),
], ids=["models dropped", "a condition dropped", "a ratio changed",
        "the baseline dropped"])
def test_the_review_is_held_to_the_models_the_program_states(edit):
    program = _program([_model(THREE, BASELINE)])
    result = _run(program)
    bent = copy.deepcopy(result)
    edit(bent["extensions"]["llm_proposed_review"])
    with pytest.raises(VerificationError):
        themis.verify(program, bent)


# ============================================================ the audit's own expansion


def test_an_expansion_that_bends_a_cell_is_refused(monkeypatch):
    """The kernel's expansion is also the one the audit's context is
    rebuilt by, so a bent cell reaches both sides; the verifier's own
    expansion is what refuses it. The pair is moved together, so the
    group still sums to one and only the model can tell."""
    real = instantiation.expand

    def bent(model, domains):
        cells = list(real(model, domains))
        for i, shift in ((0, 0.01), (1, -0.01)):
            c = cells[i]
            cells[i] = ProbabilityStatement(
                target=c.target, given=c.given, value=c.value + shift,
                population=c.population, provenance=c.provenance)
        return tuple(cells)

    program = _program([_model(THREE, BASELINE)])
    monkeypatch.setattr(instantiation, "expand", bent)
    result = _run(program)
    with pytest.raises(VerificationError, match="probability model"):
        themis.verify(program, result)


def test_a_model_survives_the_merged_program():
    """The merged program a patched run hands back is what an auditor
    verifies against, so the model has to come back as a model."""
    program = _without(_program([_model(THREE, BASELINE)]), "probability", "w")
    assert _run(program)["status"] == "needs_investigation"
    out = themis.apply_patch_and_run(program, {
        "kind": "parameter_fill_bundle", "version": "0.1",
        "skeletons": [_cell("w", True, [], 0.3)]})
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    assert [s for s in out["merged_program"]["statements"]
            if s["kind"] == "probability_model"] == [_model(THREE, BASELINE)]
    themis.verify(out["merged_program"], result)


# ============================================================ what a model must say


def _refused(program):
    with pytest.raises(SemanticError) as raised:
        themis.run(program)
    return raised.value.species


def test_a_condition_named_twice_is_refused():
    program = _program([_model(THREE + [("x", False, {True: 3.0})], BASELINE)])
    assert _refused(program) is Malformed.MODEL_CONDITION_TWICE


def test_a_ratio_for_a_condition_with_no_reference_is_refused():
    """A ratio is relative to a reference, and ``given`` is where a
    condition's reference is written."""
    model = _model(THREE, BASELINE)
    model["given"].pop()
    assert _refused(_program([model])) is Malformed.MODEL_RATIO_WITHOUT_REFERENCE


def test_a_condition_no_ratio_names_is_refused():
    model = _model(THREE, BASELINE)
    model["odds_ratios"].pop()
    assert _refused(_program([model])) is Malformed.MODEL_CONDITION_WITHOUT_RATIO


@pytest.mark.parametrize("ratios, domain, species", [
    ({False: 2.0}, [True, False], Malformed.MODEL_CONDITION_VALUES),
    ({True: 2.0}, [True, False, "maybe"], Malformed.MODEL_CONDITION_VALUES),
    ({True: 2.0, "maybe": 1.0}, [True, False], Malformed.VALUE_NOT_IN_DOMAIN),
], ids=["the reference again", "a value with no ratio",
        "a value it does not have"])
def test_a_condition_names_each_of_its_values_once(ratios, domain, species):
    """Its reference and its ratios' values are its values, each once — or
    the model states a cell twice, or leaves one of its table's cells
    unstated. A value the variable does not take is refused as it is
    anywhere a value sits beside its atom."""
    program = _program([_model([("x", False, ratios), *THREE[1:]], BASELINE)])
    program["statements"][0]["domain"] = domain
    assert _refused(program) is species


def test_every_parameter_of_a_language_models_table_carries_its_reason():
    program = _program([_model(THREE, BASELINE)])
    del program["statements"][-2]["odds_ratios"][1]["annotations"]
    assert _refused(program) is Malformed.LLM_PRIOR_PARAMETER_WITHOUT_SOURCE


def test_a_condition_the_target_does_not_depend_on_is_refused():
    """Its cells are CPT entries like any other, and the parent rule holds
    them after the expansion."""
    program = _without(_program([_model(THREE, BASELINE)]), "cause", "w",
                       end="from")
    assert _refused(program) is Malformed.GIVEN_NOT_PARENTS
