"""The formula on the envelope, and what used to disagree with it.

``result["formula"]`` is the estimand. The report prints it
(``analysis_report.py`` line 943), the browser shows it to a reader under
识别公式 (``Verdict.tsx`` line 109), and ``analysis_report.py`` line 3767
says every other route's estimand is stated from it. Nothing read it: on
all twenty-three answers that carry one it could be **deleted outright**
and the public door said yes, and its two hundred and sixty-seven leaves —
which predicate each factor is about, which variable the sum binds, which
value of Y the whole thing is for — could each be rewritten. What is left
after each pass is counted by the census gate
(``test_every_answer_shape_is_asked_the_same_question``), which owns that
number; what KIND of thing is left is said here.

The probe that answers this has existed since Phase 15. It samples random
SCMs consistent with the graph and asks whether the formula computes the
true interventional quantity, and it was reachable from one branch of the
query-kind dispatch, where it reads the formula out of the DERIVATION —
which an effect answer's chain does not carry. A check about the answer,
standing where a route is chosen.

Two things had to change together, and neither is enough alone. The probe
now runs on the envelope's formula, outside that dispatch. And its verdict
vocabulary had one word doing two jobs: a formula naming a predicate this
problem never declared cannot be evaluated, so it came back
"inconclusive", which the probe's own documentation says is NOT a
rejection. Renaming one predicate was therefore the cheapest way past a
semantic check — twenty-two of twenty-two forgeries returned it. Whether a
formula is ABOUT this problem is now asked from the formula's own text,
before any SCM is sampled, and answered as a refusal.

Three questions are asked of the estimand and they do not share a
prerequisite. Whether the formula is ABOUT this problem needs only the
names the problem declares, so it is asked of all twenty-three. Whether it
COMPUTES what was asked needs an (X, Y) pair, and a counterfactual
conjunction names none, so it is asked of twenty-two. Binding both to the
second prerequisite is how the first came to be skipped on a shape whose
graph could have answered it. The third is for the questions that have no
X at all: a probability question identifies nothing, so its estimand is
the conditional it names and comparing the two needs no model.

Those names come from two places and neither is complete alone: an
estimation route's graph carries every variable while its theta is empty,
and a probability query's theta carries the variable while its graph —
built from the cause statements — has no nodes at all. Asking only the
graph reads "took part in no edge" as "does not exist", and refused an
honest answer for it.

Measured across the forty-four shapes: twenty-one honest formulas match,
one declines for a reason of its own (an IDC query conditions on something
the probe’s graph does not carry), and one query kind has no (X, Y) pair.
What this does NOT close is written down and counted below.

AND THEN THE PROBE WAS BLIND. The paragraph above about Y's value was
carried out by cutting Y's domain to that one value in the dictionary
handed to the probe — which is the same dictionary the probe samples its
models from. Y became a constant: every probability in every sampled model
was 1.0, the true interventional value was 1.0, and this rule returned
``match`` for every formula on every answer that carried one. Measured
afterwards, twenty-two of the twenty-three reached the probe collapsed and
none reached it live, and a back-door estimand rewritten to ``P(x|x,z)`` —
a formula that is identically one — passed the public door.

Which values of Y a formula is ABOUT and which values Y HAS are two
questions; the first was asked by answering the second wrongly. The probe
now has a parameter for it. A model with no room for the value it is asked
about is the same silence with the other hat on — both sides come back
zero — so what the question names is added to the sampled domains, the
intervened value of X as much as the outcome's; one answer in the corpus
intervenes at ``x=2`` and was vacuous for exactly that reason.

A LIVE PROBE FOUND SOMETHING ELSE, and it is not this rule's to report. A
transported estimand takes its conditional from a source domain and its
covariate marginal from the target and writes neither down — a reference
carries a population and the serializer emits it whenever it is set, and
on the envelope every one of them is unset — so read in one population it
adjusts over a set that does not block the back door. The
sampled models disagreed with nineteen honest transported answers at once.
The defect is real and is the producer's — an untagged reference, not a
miscomputed one — and the probe's model is one population, so this rule
declines where the program declares selection nodes. Declared, not hidden.

WHAT IS LEFT is the names arithmetic cannot see, and they are left because
no sampled model can tell them apart rather than because nobody looked.
An atom's object arguments reach no check — ``formula_fits`` compares
predicates, and an atom the model does not know falls back to the boolean
default rather than failing. And ``SumExpr.over`` is consumed only as the
domain to sum across, so on a problem whose variables are all binary it
may name any node at all. Neither is answerable by arithmetic; both have a
second record — the graph carries whole atoms, and the atom a sum is over
is the one its own body binds — and that is a frontier of its own.

The corpus has since widened to the answers that carry no number, and it
brought one estimand on an answer with no reasoning chain, and two more of
each kind this rule already declines on. It also brought the first shape
on which the swap below is not a forgery — read at the time as a fact
about the construction, which it is and which was not the whole reason. A
probability estimand was not held to the question beside it at all.

It is now, and by comparison rather than by arithmetic. A probability
question identifies nothing, so its estimand is the conditional the
question names and the two can simply be put side by side. That
comparison was already written — in the chain half, against a
``formula_evaluation`` step — so what was held was the chain's account of
what it evaluated and not ``result["formula"]``, which is the copy a
reader is shown.

Every forgery here is put to the strongest door that reads the answer
carrying it. An estimand reaches a reader whether or not a route was
taken, so an estimand on an answer with no chain is asked at the door that
holds what an answer says rather than left out of the count.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.verifier.errors import VerificationError
from themis.verifier.semantic_probe import ProbeResult, formula_fits

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

WITH_FORMULA = sorted(
    name for name, pair in SHAPES.items() if "formula" in pair["result"])

#: An answer that took no route carries no chain, and the door that
#: re-runs chains refuses one before reading a word of it. A refusal made
#: for what an answer IS says nothing about whether a forgery on it was
#: seen — so every forgery below goes to the strongest door that reads the
#: answer carrying it, which for those rows is the door that holds what an
#: answer SAYS. An estimand reaches a reader whether or not a route was
#: taken, so leaving those rows out would leave that reader unheld.
CHAINLESS = [name for name in WITH_FORMULA
             if SHAPES[name]["result"].get("derivation") is None]


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _first(node, key, apply):
    """Rewrite the first ``key`` in document order. True if one was found."""
    if isinstance(node, dict):
        if isinstance(node.get(key), str):
            node[key] = apply(node[key])
            return True
        return any(_first(v, key, apply) for v in node.values())
    if isinstance(node, list):
        return any(_first(v, key, apply) for v in node)
    return False


def _probability_program(given_names) -> dict:
    """The smallest program that asks a conditional on N conditions."""
    def atom(name):
        return {"predicate": name, "args": [{"name": "p", "type": "const"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            *({"kind": "variable", "predicate": name, "domain": [True, False]}
              for name in ("y", "a", "b")),
            {"kind": "cause", "from": atom("a"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": {"atom": atom("y"), "value": True},
                "given": [{"atom": atom(name), "value": True}
                          for name in given_names]}},
        ],
    }


def _swap_target_and_condition(formula) -> None:
    formula["target"], formula["given"][0] = (
        formula["given"][0], formula["target"])


def _flip_a_condition(formula) -> None:
    condition = formula["given"][0]
    condition["value"] = not condition.get("value", True)


def _chain_rules(result) -> list[str]:
    """The rules an answer's chain names; empty where there is no chain."""
    steps = result.get("derivation")
    if isinstance(steps, dict):
        steps = steps.get("steps")
    return [step.get("rule") for step in steps or ()]


def _names(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("predicate"), str):
            out.add(node["predicate"])
        for value in node.values():
            _names(value, out)
    elif isinstance(node, list):
        for value in node:
            _names(value, out)
    return out


# ------------------------------------------------- the fact this rests on


def test_the_estimand_is_carried_by_the_answers_that_identify_one():
    """Stated so it cannot drift: which answers carry a formula, and that
    every one of them is a sum, product or fraction over probabilities.

    One of them is on an answer with no chain. An estimand reaches a
    reader whether or not a route was taken, so it is asked there too —
    at the door that holds what an answer says, which is what the whole
    of that answer is.
    """
    assert len(WITH_FORMULA) == 28, WITH_FORMULA
    assert CHAINLESS == ["needs_investigation:probability:none"], CHAINLESS
    for name in WITH_FORMULA:
        written = SHAPES[name]["result"]["formula"]
        assert written["kind"] in (
            "sum", "product", "fraction", "probability_ref", "constant"), (
                name, written["kind"])


# --------------------------------------------------- rewriting the estimand


@pytest.mark.parametrize("shape", WITH_FORMULA)
def test_a_factor_may_not_be_about_a_variable_the_graph_lacks(shape):
    """The cheapest forgery, and the one a semantic check used to answer
    with "no opinion": rename one predicate."""
    program, result = _pair(shape)
    assert _first(result["formula"], "predicate", lambda p: p + "_forged")
    with pytest.raises(VerificationError, match="does not declare"):
        the_door_for(result)(program, result)


@pytest.mark.parametrize("shape", WITH_FORMULA)
def test_a_sum_and_the_references_to_it_are_one_name(shape):
    """Rename what the sum binds and its references dangle. Nothing about
    the graph is wrong; the formula has simply stopped being one."""
    program, result = _pair(shape)
    formula = result["formula"]
    if not isinstance(formula.get("bind"), dict):
        pytest.skip("this estimand binds nothing")
    formula["bind"]["name"] = formula["bind"]["name"] + "_forged"
    with pytest.raises(VerificationError, match="binds those"):
        the_door_for(result)(program, result)


def test_a_forgery_that_stays_inside_the_graph_is_refused_wherever_asked():
    """The remainder, counted rather than skipped.

    Swap two variables the formula actually uses. Every name still exists,
    the formula is still about this graph, and the estimand is a different
    one — so the fit gate above has nothing to say and the question falls
    entirely to the sampled models.

    This assertion used to name three, and to explain the twenty it did not
    name: thirteen were "a genuine match", because a back-door sum over one
    binary covariate is nearly symmetric in the two names exchanged. That
    explanation was invented. The probe was answering 1.0 = 1.0 on a model
    where the outcome was a constant, and it would have said match to any
    formula whatever. A remainder that has been EXPLAINED is not a
    remainder that has been MEASURED, and the story was the more convincing
    of the two.

    Twenty-two of twenty-eight are refused now. The six that are not are
    named rather than counted, because each has its own reason — and one
    of those reasons turned out to be a hole rather than a decline, which
    is what naming them instead of counting them is for. It is shut, and
    the probability row still here is the one where this construction
    genuinely forges nothing.
    """
    accepted = []
    for shape in WITH_FORMULA:
        program, result = _pair(shape)
        names = sorted(_names(result["formula"]))
        assert len(names) >= 2, shape
        lo, hi = names[0], names[-1]

        def swap(node):
            if isinstance(node, dict):
                if node.get("predicate") == lo:
                    node["predicate"] = hi
                elif node.get("predicate") == hi:
                    node["predicate"] = lo
                for value in node.values():
                    swap(value)
            elif isinstance(node, list):
                for value in node:
                    swap(value)

        swap(result["formula"])
        try:
            the_door_for(result)(program, result)
        except VerificationError:
            continue
        accepted.append(shape)

    # ``ctf_conjunction_plugin`` is a counterfactual conjunction: it names
    # no (X, Y) pair, so there is no interventional quantity to compare a
    # formula against. The two IDC answers condition on something the
    # probe's graph does not carry, and decline before sampling. The two
    # transporting answers are about two populations while the probe's
    # model is one. Those are declines, and a decline is not an acquittal —
    # each is its own frontier rather than this one's cost.
    #
    # One probability answer is left, and on it this construction forges
    # nothing: the two names it exchanges are both CONDITIONS of one
    # conditional, and P(y | a, b) and P(y | b, a) are one quantity, so
    # the formula after the swap is the formula before it. That reading
    # was once offered for both probability rows, where it was a story
    # rather than a measurement — the other row exchanged the TARGET with
    # a condition, which is a different estimand by anyone's reading, and
    # was accepted because nothing held a probability estimand to the
    # question beside it. Something does now, and it is the same reading:
    # the conditions are compared as a multiset, so the row below stays
    # for the reason it was always said to.
    assert accepted == [
        "ctf_conjunction_plugin",
        "general_id_idc_plugin",
        "numerically_solved:probability:numeric_result",
        "structurally_solved:effect:identify_via_transport",
        "structurally_solved:identify:identify_via_idc",
        "transport_post_stratification",
    ], accepted


def test_a_probability_estimand_is_held_to_the_question_it_answers():
    """The record a reader is shown, put beside the question it answers.

    ``P(y | a, b)`` rewritten to ``P(a | y, b)`` is a different quantity
    printed under the same heading. An effect answer's estimand is refused
    for it because sampled models disagree; a probability answer's was
    asked nothing but whether its names were real.

    Arithmetic was never what would answer it. A probability question
    identifies nothing, so the estimand IS the conditional the question
    names and the two can simply be compared — and the comparison was
    already written. It stands in the chain half, where
    ``_assert_query_binding`` holds a ``formula_evaluation`` step against
    the query's own reference: what was held is the chain's account of
    what it evaluated, while ``result["formula"]`` — the copy the report
    prints and the browser shows — was held to nothing. One of these two
    answers carries that step, so forging its envelope copy passed the
    same door that refuses a forged step; the other has no chain at all.

    Order is not part of a quantity, and that is asserted here beside the
    forgeries: ``P(y | b, a)`` is the same conditional a reader was
    already shown, so refusing it would be this rule inventing a defect.
    The chain half compares the two verbatim and is right to — what it
    holds is provenance, which is a stricter question than this one.
    """
    probability = sorted(
        name for name, pair in SHAPES.items()
        if pair["result"].get("query_kind") == "probability"
        and pair["result"].get("formula", {}).get("given"))
    assert len(probability) == 2, probability

    for name in probability:
        program, result = _pair(name)
        query = next(s for s in program["statements"]
                     if s.get("kind") == "query")["query"]
        formula = result["formula"]
        # The record this rests on: the honest formula IS the question,
        # and is accepted for being it.
        assert (query["target"]["atom"]["predicate"]
                == formula["target"]["atom"]["predicate"])
        assert ([g["atom"]["predicate"] for g in query.get("given") or []]
                == [g["atom"]["predicate"] for g in formula["given"]])
        the_door_for(result)(program, result)

        # The same conditional written the other way round. Not a forgery.
        _, result = _pair(name)
        result["formula"]["given"].reverse()
        the_door_for(result)(program, result)

        # Two different quantities under the one heading.
        for forge in (_swap_target_and_condition, _flip_a_condition):
            _, result = _pair(name)
            forge(result["formula"])
            with pytest.raises(VerificationError, match="the question asks"):
                the_door_for(result)(program, result)

        # And the way out of a comparison, which is not to be comparable:
        # the same number written as something that is not a conditional.
        _, result = _pair(name)
        result["formula"] = {
            "kind": "product",
            "terms": [dict(result["formula"]),
                      {"kind": "constant", "value": 1.0}]}
        with pytest.raises(VerificationError, match="not written as the"):
            the_door_for(result)(program, result)

    # Which record was held before, measured rather than argued. Exactly
    # one of these two answers carries the step the chain half holds
    # against the question — and it is an answer whose envelope copy was
    # forged and let through. The other carries no chain, so the
    # comparison that existed could not have reached it either way.
    held = [name for name in probability
            if "formula_evaluation" in _chain_rules(_pair(name)[1])]
    assert held == ["numerically_solved:probability:numeric_result"], held


def test_the_route_that_answers_a_probability_question_writes_that_question():
    """What makes the refusal above safe to state as strongly as it is.

    The rule refuses an estimand that is not written as the conditional
    the question names, and that is a claim about what this system
    produces. Asserted, it would be an assumption; here it is run. A
    program that asks a conditional gets that conditional back, whatever
    it conditions on and in whatever order it names them.

    What this does not prove is exhaustiveness — it runs the route rather
    than enumerating the programs. What it does is fail on the day a
    producer starts DERIVING a probability estimand instead of naming it,
    which is the day the refusal above would begin refusing honest work.
    """
    for given in ([], ["a"], ["a", "b"], ["b", "a"]):
        program = _probability_program(given)
        result = themis.run(program)["results"][0]
        formula = result["formula"]
        query = program["statements"][-1]["query"]
        assert formula["kind"] == "probability_ref", (given, formula)
        assert formula["target"] == query["target"], given
        assert formula["given"] == query["given"], given


# ------------------------------------------- a decline is not an acquittal


def test_a_formula_that_does_not_fit_is_refused_rather_than_declined():
    """The two species, asked of the gate that separates them.

    ``formula_fits`` is answered from the formula's own text, before any
    model is sampled — not from an exception raised while evaluating it.
    A verifier that read "could not evaluate: KeyError(...)" as a reason
    would be reading a message, and a message belongs to whoever raises it.
    """
    import networkx as nx

    from themis.types import (
        Atom, ProbabilityRefExpr, SumExpr, ValuedAtom, VarRef, BindDecl,
    )

    x, y = Atom("x", ()), Atom("y", ())
    graph = nx.DiGraph()
    graph.add_nodes_from([x, y])
    graph.add_edge(x, y)

    fits = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),))
    assert formula_fits(graph, fits) is None

    stray = ProbabilityRefExpr(
        target=ValuedAtom(atom=Atom("nowhere", ()), value=True), given=())
    verdict = formula_fits(graph, stray)
    assert isinstance(verdict, ProbeResult) and verdict.status == "unfit"
    assert "does not declare" in verdict.detail

    # A variable that causes nothing is still a variable. Asked of the
    # graph alone this is a stray name; asked of the problem it is not,
    # and a probability query is exactly the shape that has one.
    graphless = nx.DiGraph()
    lonely = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True), given=())
    assert formula_fits(graphless, lonely) is not None
    assert formula_fits(graphless, lonely, {y: (True, False)}) is None

    dangling = SumExpr(
        bind=BindDecl(name="over_x"), over=x,
        body=ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=x, value=VarRef(name="somebody_else")),)))
    verdict = formula_fits(graph, dangling)
    assert verdict is not None and verdict.status == "unfit"
    assert "binds those" in verdict.detail


def test_an_estimand_this_system_cannot_read_is_refused():
    """A formula whose shape is not one this repository writes is a
    refusal, not a shrug: the only reason to carry one is to be read."""
    program, result = _pair(WITH_FORMULA[0])
    result["formula"] = {"kind": "sum", "bind": {"name": "z"}}
    with pytest.raises(Exception):
        themis.verify(program, result)


def test_the_probe_is_told_which_value_of_the_outcome_it_is_about():
    """An effect answer's formula names Y's value where an identify
    query's leaves it open. Asked about the other value it returns the
    same number, and the probe reads that as a mismatch by 1-p — so an
    honest estimand would be refused. Every honest shape passing is what
    holds this, and it is asserted here because the failure it prevents is
    silent everywhere else."""
    for name in WITH_FORMULA:
        program, result = _pair(name)
        the_door_for(result)(program, result)


# ------------------- and the telling does not take the model away with it


def _one_covariate_graph():
    """``z → x → y`` with ``z`` confounding: the shape of a back-door
    estimand, built here so the probe can be asked directly."""
    import networkx as nx

    from themis.types import Atom, ConstTerm

    u = (ConstTerm(name="u"),)
    x, y, z = (Atom(predicate=p, args=u) for p in ("x", "y", "z"))
    graph = nx.DiGraph()
    graph.add_edges_from([(z, x), (z, y), (x, y)])
    return graph, x, y, z


def _aipw_formula(**edit):
    """The back-door estimand of the ``aipw`` shape, optionally bent."""
    from themis.verifier.serialization import _DECODE_BY_KIND

    written = copy.deepcopy(SHAPES["aipw"]["result"]["formula"])
    for path, value in edit.items():
        node = written
        steps = path.split("__")
        for step in steps[:-1]:
            node = node[int(step) if step.isdigit() else step]
        node[steps[-1]] = value
    return _DECODE_BY_KIND[written["kind"]](written)


def test_naming_the_value_must_not_be_said_by_narrowing_the_model():
    """The counter-example the parameter exists for.

    ``P(x=true | x=true, z)`` summed over ``z`` is identically one, and it
    is a forgery every name in which the problem declares — so only the
    arithmetic can catch it. Asked the old way, with Y's domain cut to the
    single value the formula is about, the probe calls it a match: the
    outcome is a constant in every sampled model, so the formula and the
    truth are both 1.0 and nothing can disagree. Asked with the value
    passed as the value it is, the same model still has an outcome.
    """
    from themis.verifier.semantic_probe import probe_identify_formula

    graph, x, y, _z = _one_covariate_graph()
    honest = _aipw_formula()
    identically_one = _aipw_formula(
        body__terms__0__target__atom__predicate="x")

    def ask(formula, **how):
        return probe_identify_formula(
            graph, frozenset(), x=x, x_value=True, y=y, given=(),
            formula=formula, **how).status

    # The shape that was shipped: both come back the same word.
    assert ask(honest, domains={y: (True,)}) == "match"
    assert ask(identically_one, domains={y: (True,)}) == "match"

    # The shape that separates them.
    assert ask(honest, y_values=(True,)) == "match"
    assert ask(identically_one, y_values=(True,)) == "mismatch"


def test_a_model_is_given_room_for_the_value_it_is_asked_about():
    """The same silence with the other hat on.

    Ask a boolean model about ``y=4`` and the truth is zero because that
    outcome cannot occur; the formula agrees, for the same reason, and the
    probe reads two zeros as agreement. Intervening at a value the model
    has no room for does it too — ``den = P(x=2) = 0`` — and one answer in
    the corpus intervenes at ``x=2``. So the values the question names are
    added to the domains the models are sampled from, and then the same
    forgery is caught at ``y=4`` and at ``x=2`` as it is at ``y=true``.
    """
    from themis.verifier.semantic_probe import (
        _room_for, probe_identify_formula,
    )

    graph, x, y, _z = _one_covariate_graph()
    identically_one = _aipw_formula(
        body__terms__0__target__atom__predicate="x")

    def ask(*, x_value, y_value):
        return probe_identify_formula(
            graph, frozenset(), x=x, x_value=x_value, y=y, given=(),
            formula=identically_one, y_values=(y_value,)).status

    assert ask(x_value=True, y_value=True) == "mismatch"
    assert ask(x_value=True, y_value=4) == "mismatch"
    assert ask(x_value=2, y_value=True) == "mismatch"

    # Room is made, not taken: a declared domain keeps its own values and
    # gains only what it was missing, in order and without repeats.
    assert _room_for((True, False), (True,)) == (True, False)
    assert _room_for((True, False), (4,)) == (True, False, 4)
    assert _room_for((0, 1, 2), (2, 5)) == (0, 1, 2, 5)


# ------------------ and the one place the question does not apply at all


def _transporting_program(*, with_theta: bool = True) -> dict:
    """Two covariates confound x → y and two trials each shift one.

    The smallest program that makes the point: read in one population the
    transported estimand adjusts over ``z1`` alone, which does not block
    the back door ``z2`` opens. Written here rather than borrowed from the
    transport suite because what this file needs is a counter-example, not
    that fixture.
    """
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    def prob(target, given, value, population):
        return {"kind": "probability",
                "target": {"atom": atom(target), "value": True},
                "given": [{"atom": atom(p), "value": v} for p, v in given],
                "value": value, "population": population}

    statements: list = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("x", "y", "z1", "z2")
    ] + [
        {"kind": "cause", "from": atom(a), "to": atom(b)}
        for a, b in (("z1", "x"), ("z1", "y"), ("z2", "x"), ("z2", "y"),
                     ("x", "y"))
    ] + [
        {"kind": "selection_node", "id": "S_us", "affects": atom("z1"),
         "source_population": "rct_us", "target_population": "real_world"},
        {"kind": "selection_node", "id": "S_eu", "affects": atom("z2"),
         "source_population": "rct_eu", "target_population": "real_world"},
    ]
    if with_theta:
        statements += [
            prob("y", [("x", True), ("z1", True)], 0.40, "rct_us"),
            prob("y", [("x", True), ("z1", False)], 0.60, "rct_us"),
            prob("y", [("x", True), ("z2", True)], 0.30, "rct_eu"),
            prob("y", [("x", True), ("z2", False)], 0.70, "rct_eu"),
            prob("z1", [], 0.5, "real_world"),
            prob("z2", [], 0.5, "real_world"),
        ]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": atom("x"), "value": True},
        "target": {"atom": atom("y"), "value": True},
        "given": [],
        "target_population": "real_world"}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def test_a_transported_estimand_is_declined_rather_than_refused():
    """What a live probe found, and why reporting it here would be wrong.

    A transported estimand takes its conditional from a source domain,
    where the treatment was randomised, and its covariate marginal from
    the target. It writes neither down — every reference leaves
    ``population`` unset — so read in one population it is a back-door
    adjustment over a set that does not block the back door, and the
    sampled models disagree with it by a wide margin.

    That is a true statement about the ENVELOPE and a wrong place to make
    it: the defect is an untagged reference, not a miscomputed one, and it
    is the producer's. The probe's model is one population, so on a program
    that declares selection nodes this rule declines. The cost is stated:
    a transported estimand is unheld by this rule, and the census counts
    what that leaves open.

    The condition is the PROGRAM's, not the supplied data's — the second
    program below supplies no distributions at all and transports just the
    same — which a first version got wrong by reading the populations off
    theta.
    """
    for supplied in (True, False):
        program = _transporting_program(with_theta=supplied)
        result = themis.run(program)["results"][0]
        assert (result.get("extensions") or {}).get("transport_identification")
        themis.verify(program, result)

    # The half that does not need one population is still asked there.
    program = _transporting_program()
    result = themis.run(program)["results"][0]
    assert _first(result["formula"], "predicate", lambda p: p + "_forged")
    with pytest.raises(VerificationError, match="does not declare"):
        themis.verify(program, result)
