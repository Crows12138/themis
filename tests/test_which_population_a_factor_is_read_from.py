"""A formula whose factors come from two places, printed as one line.

A transported estimand is not read in one population. The factor carrying
the effect comes from a source domain, where the treatment was randomised;
every other factor is a marginal of the target population, where the
question is asked. ``ProbabilityRefExpr`` has carried a ``population``
since transport was built and the producer sets it — the derivation's
serializer emits it — and on the envelope a reader is shown, both factors
of the corpus's transported answer came through as ``None``.

Two things dropped it and either alone is enough. ``_formula_to_dict`` is
written twice — once in ``themis/verifier/serialization.py`` and once in
``themis/output/result_orchestrator.py`` — and the envelope is written by
the second, which never learned the field. And the envelope's own schema
closes ``probabilityRefExpr`` to four keys it did not have among them, so
a writer that had learned it would have been refused. The reader's copy of
this shape and the derivation's copy are two documents about one thing,
and the field existed in one of them from the day transport did.

The two encoders still disagree about the rest of the dialect — on all
twenty-three answers that carry a formula, and on all fourteen distinct
shapes among them, because the derivation's definitions require a ``kind``
on a valued atom and the envelope's forbid one — so this borrows the
field's definition by ``$ref`` rather than restating it, and leaves the
larger unification declared and counted.

What holds the field is not that somebody wrote it. Which two populations
a transported formula reads from is not a question for a sampled model —
the probe's model is one population, which is why the arithmetic is not
asked here — but it is not a question for a producer either: the source is
re-derived from the selection nodes the program declares, the target from
the question's own ``target_population``, and which factor is which from
the formula's own shape. Where a problem has one population there is
nothing to choose between, and silence names it; naming a population
anyway names something the problem does not have. Asked of all twenty-
three answers that carry a formula, one of which transports.

The corpus has since widened to the answers that carry no number. Twenty-
eight carry a formula now and two of them transport, and the second one
tags its factors the same way without this rule being touched — which is
what a field being the producer's own record, rather than a habit of one
route, looks like from outside.

Making the field visible made a second thing visible with it. A question
may name a target population while declaring no selection node, and then
there is no source domain, because what names one is a selection node —
the identifier reports ``source_population is None`` and calls the case
trivially identifiable. Two ``or "source"`` fallbacks stood in for that
None, and the cost was measured at the commit before this one: no theta
entry is tagged ``source``, so a program carrying every number its answer
needs came back with no value at all.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis.output.result_orchestrator import _formula_to_dict as to_envelope
from themis.types import (
    FractionExpr, ProbabilityRefExpr, ProductExpr, SumExpr,
)
from themis.verifier.errors import VerificationError
from themis.verifier.serialization import (
    _DECODE_BY_KIND, _formula_to_dict as to_derivation,
)

ROOT = pathlib.Path(__file__).parent.parent
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The answer this file's forgeries are built on. Which answers transport
#: at all is a fact about their programs and is read off them below; this
#: is the one whose two factors and two population names are quoted here.
TRANSPORTED = "transport_post_stratification"

WITH_FORMULA = sorted(
    name for name, pair in SHAPES.items() if "formula" in pair["result"])


def _pair(method: str):
    pair = SHAPES[method]
    return copy.deepcopy(pair["program"]), copy.deepcopy(pair["result"])


def _refs(node, out=None):
    """Every probability factor of a written formula, in document order."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get("kind") == "probability_ref":
            out.append(node)
        for value in node.values():
            _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)
    return out


def _decoded_refs(expr, out=None):
    out = [] if out is None else out
    if isinstance(expr, ProbabilityRefExpr):
        out.append(expr)
    elif isinstance(expr, ProductExpr):
        for term in expr.terms:
            _decoded_refs(term, out)
    elif isinstance(expr, SumExpr):
        _decoded_refs(expr.body, out)
    elif isinstance(expr, FractionExpr):
        _decoded_refs(expr.numerator, out)
        _decoded_refs(expr.denominator, out)
    return out


def _declared(program: dict) -> tuple[set, set]:
    """The source domains a program declares, and the population it asks
    about."""
    sources = {s["source_population"] for s in program["statements"]
               if s.get("kind") == "selection_node"}
    asked = {s["query"].get("target_population")
             for s in program["statements"] if s.get("kind") == "query"}
    return sources, asked


# ------------------------------------------------- the fact this rests on


#: The answers whose PROGRAM declares a shift between populations, which
#: is what gives this rule something to choose between. Read off the
#: program rather than off the formula's tags, so an answer that should
#: name a population and does not is inside the question rather than
#: outside it.
TRANSPORTING = sorted(
    name for name, pair in SHAPES.items()
    if any(s.get("kind") == "selection_node"
           for s in pair["program"]["statements"]))


def test_the_answers_in_the_corpus_that_read_from_more_than_one():
    """Which answers this rule has something to choose between on."""
    assert TRANSPORTED in TRANSPORTING and len(TRANSPORTING) == 2
    assert len(SHAPES) == 64
    assert len(WITH_FORMULA) == 28


def test_the_two_places_a_transported_estimand_reads_from():
    """The factor carrying the effect names a source domain; the covariate
    marginal names the target. Both are names the program itself uses."""
    program, result = _pair(TRANSPORTED)
    sources, asked = _declared(program)
    assert sources == {"trial"} and asked == {"real_world"}

    refs = _refs(result["formula"])
    assert len(refs) == 2
    conditional, = [r for r in refs if r["given"]]
    marginal, = [r for r in refs if not r["given"]]
    assert conditional["population"] == "trial"
    assert marginal["population"] == "real_world"


def test_every_other_formula_leaves_it_to_the_question():
    """Silence is the whole vocabulary where a problem has one population,
    which is twenty-six of the twenty-eight — and the two that speak are
    the two whose programs declare a shift, so which formulas carry a name
    is decided by the problem rather than by the producer's mood."""
    named = []
    for name in WITH_FORMULA:
        _, result = _pair(name)
        tags = {r.get("population") for r in _refs(result["formula"])}
        if tags == {None}:
            continue
        named.append(name)
        assert None not in tags, (name, tags)
    assert named == TRANSPORTING, named


# ------------------------------------------- the reader's copy of the shape


def test_the_readers_copy_of_a_factor_has_a_place_to_say_it():
    """The envelope's ``probabilityRefExpr`` is closed, so a field it does
    not name cannot be written at all — and it borrows this one's
    definition from the derivation's copy rather than restating it, which
    is the only way two documents about one shape stay one shape."""
    schema = json.loads(
        (ROOT / "themis" / "schemas" / "query_result.schema.json")
        .read_text(encoding="utf-8"))
    shape = schema["$defs"]["probabilityRefExpr"]

    assert shape["additionalProperties"] is False
    assert sorted(shape["properties"]) == [
        "given", "kind", "population", "target"]
    assert shape["required"] == ["kind", "target", "given"]
    assert shape["properties"]["population"]["$ref"] == (
        "derivation.schema.json#/$defs/probability_ref/properties/population")


def test_both_writers_of_a_formula_now_say_where_a_factor_is_read_from():
    """The envelope's encoder and the derivation's are two functions with
    one name. They still disagree about the dialect around this field —
    a valued atom carries a ``kind`` in one document and may not in the
    other — but no longer about whether the field is written."""
    _, result = _pair(TRANSPORTED)
    expr = _DECODE_BY_KIND[result["formula"]["kind"]](result["formula"])

    both = [to_derivation(expr), to_envelope(expr)]
    assert [[r["population"] for r in _refs(w)] for w in both] == [
        ["trial", "real_world"], ["trial", "real_world"]]

    # Declared, not fixed here: the rest of the two dialects, which is
    # every formula in the corpus — the size of what this leaves open is
    # part of what declaring it means.
    apart = [name for name in WITH_FORMULA
             for e in [_DECODE_BY_KIND[SHAPES[name]["result"]["formula"]
                                       ["kind"]](
                 SHAPES[name]["result"]["formula"])]
             if json.dumps(to_derivation(e), sort_keys=True)
             != json.dumps(to_envelope(e), sort_keys=True)]
    assert apart == WITH_FORMULA


def test_a_decoder_reads_a_factor_that_says_nothing():
    """Absent is a value, not an omission — which is what lets the field be
    added to a shape twenty-two honest answers already write."""
    _, result = _pair("backdoor_linear")
    expr = _DECODE_BY_KIND[result["formula"]["kind"]](result["formula"])
    assert [r.population for r in _decoded_refs(expr)] == [None, None]


# --------------------------------------------- what the rule has to refuse


def _forge(result: dict, apply) -> dict:
    """``apply(ref, index)`` over each factor of the written estimand."""
    forged = copy.deepcopy(result)
    for index, ref in enumerate(_refs(forged["formula"])):
        apply(ref, index)
    return forged


@pytest.mark.parametrize("drop", [0, 1, None])
def test_a_transported_factor_that_says_nothing_is_refused(drop):
    """The shape that shipped: both factors untagged, and a reader shown a
    formula whose halves come from two places as if from one. Dropping
    either one alone is refused too — the reader is no better off being
    told about half of it."""
    program, result = _pair(TRANSPORTED)
    forged = _forge(result, lambda ref, i: (
        ref.pop("population", None) if drop in (None, i) else None))

    with pytest.raises(VerificationError, match="is read from None"):
        themis.verify(program, forged)


def test_a_factor_may_not_borrow_the_other_populations_name():
    """Swapped, the formula still names two populations and still names
    both of the right ones — and is a different estimand: the effect read
    off the target and the covariates off the trial."""
    program, result = _pair(TRANSPORTED)
    swap = {"trial": "real_world", "real_world": "trial"}
    forged = _forge(result, lambda ref, i: ref.update(
        population=swap[ref["population"]]))

    with pytest.raises(VerificationError, match="source domain's conditional"):
        themis.verify(program, forged)


def test_a_factor_may_not_name_a_population_the_problem_does_not_have():
    """A name nobody declared, on either half."""
    program, result = _pair(TRANSPORTED)
    for index in (0, 1):
        forged = _forge(result, lambda ref, i: ref.update(
            population="somewhere_else") if i == index else None)
        with pytest.raises(VerificationError, match="somewhere_else"):
            themis.verify(program, forged)


def test_a_one_population_estimand_may_not_name_a_population():
    """Where there is nothing to choose between, a tag is not extra
    information — it is a claim the problem cannot support."""
    program, result = _pair("backdoor_linear")
    forged = _forge(result, lambda ref, i: ref.update(
        population="cohort") if i == 0 else None)

    with pytest.raises(VerificationError, match="the population the question"):
        themis.verify(program, forged)


def _trivially_transporting_program() -> dict:
    """A question about another population, and no declared shift.

    The identifier calls this trivially identifiable — nothing was said to
    differ between the two populations, so the two selection diagrams are
    the same one and the effect transfers as it stands. Everything the
    answer needs is here, and none of it is tagged with a population,
    because no statement names one.
    """
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    def prob(target, given, value):
        return {"kind": "probability",
                "target": {"atom": atom(target), "value": True},
                "given": [{"atom": atom(p), "value": v} for p, v in given],
                "value": value}

    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "x",
                 "domain": [True, False]},
                {"kind": "variable", "predicate": "y",
                 "domain": [True, False]},
                {"kind": "cause", "from": atom("x"), "to": atom("y")},
                prob("y", [("x", True)], 0.40),
                prob("y", [("x", False)], 0.10),
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": atom("x"), "value": True},
                    "target": {"atom": atom("y"), "value": True},
                    "given": [],
                    "target_population": "clinic"}}]}


def test_a_source_domain_is_named_by_a_selection_node_or_by_nothing():
    """What stood in when nothing gave a source domain its name.

    Naming a ``target_population`` is what makes the producer transport,
    and a program may name one while declaring no selection node at all.
    There is then no source domain — what names one is a selection node —
    and the identifier says so: ``route.source_population`` is None.

    Two fallbacks stood in for that None with the literal string
    ``"source"``, one on the formula and one on the derivation step it is
    recorded in. Measured at the commit before this one, the cost was not
    a cosmetic name: no theta entry is tagged ``source``, so the factor
    asked for a key nothing has, and a program carrying every number its
    own answer needs came back ``structurally_solved`` with no value. With
    the envelope's encoder repaired — the first half of this frontier —
    the same fallback would also have printed ``P_source(y | x)`` to a
    reader, naming a domain no statement names.

    Refusing the program at the door was tried and is wrong: the
    identifier answers this case, a unit test pins that it does, and the
    rendering prompt tells a reader to caveat it — no difference was
    DECLARED, which is not the same as none existing.
    """
    program = _trivially_transporting_program()
    result = themis.run(program)["results"][0]

    assert "transport_identification" in {
        str(k) for k in (result.get("extensions") or {})}
    assert result["status"] == "numerically_solved"
    assert result["numeric_result"] == {"value": 0.40}
    assert [r.get("population") for r in _refs(result["formula"])] == [None]
    themis.verify(program, result)

    from themis.output import formula_text
    assert formula_text.render(result["formula"]) == "P(y | x)"


def test_declaring_diagrams_does_not_make_every_question_transport():
    """The other side of the same condition. A program may carry selection
    nodes and still be asked an ordinary one-population question, and then
    its estimand is read in one population like any other — demanding a
    source tag from it would be a refusal of an honest answer."""
    import networkx as nx

    from themis.input.semantic_validator import validate_program
    from themis.verifier.context import VerificationContext
    from themis.verifier.verify import _hold_populations

    program, result = _pair(TRANSPORTED)
    for statement in program["statements"]:
        if statement.get("kind") == "query":
            statement["query"].pop("target_population", None)
    parsed = validate_program(program)

    kind = (lambda s, n: s.__class__.__name__ == n)
    query, = [s.query for s in parsed.statements
              if kind(s, "QueryStatement")]
    nodes = tuple(s for s in parsed.statements if kind(s, "SelectionNode"))
    assert nodes and getattr(query, "target_population", None) is None

    graph = nx.DiGraph()
    graph.add_edges_from(
        (s.from_atom, s.to_atom) for s in parsed.statements
        if kind(s, "CauseStatement"))
    context = VerificationContext(
        graph=graph, query=query, selection_nodes=nodes)

    def held(written):
        _hold_populations(_DECODE_BY_KIND[written["kind"]](written), context)

    with pytest.raises(VerificationError, match="the population the question"):
        held(result["formula"])  # it still names two
    held(_forge(result, lambda ref, i: ref.pop("population", None))["formula"])


# ------------------------------------------------- and what a reader sees


def test_the_line_a_reader_is_shown_names_both_populations():
    """The end this was for. Carrying the field to the envelope is not
    telling anyone: the report and the browser both print the estimand,
    and both printed a bare ``P`` on every factor. Side by side, the shape
    that shipped and the shape that says what it is."""
    from themis.output import formula_text
    from themis.output.analysis_report import build_analysis_report

    program, result = _pair(TRANSPORTED)
    said = formula_text.render(result["formula"])
    assert said == "Σ_z [ P_trial(y | x, z) · P_real_world(z) ]"
    assert f"`{said}`" in build_analysis_report(result, program=program)

    shipped = _forge(result, lambda ref, i: ref.pop("population", None))
    assert (formula_text.render(shipped["formula"])
            == "Σ_z [ P(y | x, z) · P(z) ]")


def test_the_browser_reads_the_field_too():
    """The surface that cannot import the table. Held the way this
    repository holds it elsewhere — by reading the file for the name."""
    web = (ROOT / "themis" / "web" / "frontend" / "src" / "lib" /
           "formula.ts").read_text(encoding="utf-8")
    assert "n.population" in web
    assert "`P_${where}`" in web


# ------------------------------------------------------------- honest first


@pytest.mark.parametrize("shape", WITH_FORMULA)
def test_every_answer_that_carries_a_formula_is_still_accepted(shape):
    """Every estimand this repository writes, unaltered, through the
    public door — including the one on an answer that took no route, whose
    single permitted refusal is the door's own precondition."""
    verify_honestly(*_pair(shape))
