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
COMPUTES what was asked needs something to compute against, and each kind
of question brings its own. Binding the first question to the second's
prerequisite is how it came to be skipped on a shape whose graph could
have answered it. The third is for the questions that have no X at all: a
probability question identifies nothing, so its estimand is the
conditional it names and comparing the two needs no model.

"Something to compute against" was read for a while as "an (X, Y) pair",
which a counterfactual conjunction does not name — so the arithmetic was
not asked of it here at all. It WAS asked elsewhere, in the rule that
verifies the chain, of ``derivation[-1].inputs["formula"]``: the chain's
copy, not the estimand a reader is shown. So the envelope's could be
replaced by the constant 0.0 and every door said yes, while that probe ran
and answered ``match`` about the other copy. A conjunction names a γ, and
a conditional one a δ, which is exactly something to compute against, so
it is asked here now — of what the envelope shows. Both rules ask it, of
their own copy, because they are two claims: that the engine's output
computes the truth, and that the reader is shown something that does.

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
from tests.answer_corpus import renaming_refusal, the_door_for
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


#: The rows a rename can be tried on at all. A bare constant names
#: nothing — one estimand in the corpus is exactly that, and it is the
#: honest answer to a conjunction whose true probability is zero — so
#: there is no predicate on it to bend, and its arithmetic is held by the
#: conjunction probe instead. Read off the corpus rather than listed, so
#: the next constant estimand joins the right group without being noticed.
NAMES_A_PREDICATE = [name for name in WITH_FORMULA
                     if _names(SHAPES[name]["result"]["formula"])]


def _order_blind(node):
    """The same formula with every ``given`` list put in one order.

    A conditional's conditions are a set wearing a list's clothes:
    ``P(y | a, b)`` and ``P(y | b, a)`` are one quantity written two ways.
    A rename that exchanges two names appearing ONLY as conditions of the
    same conditional therefore produces the formula it started from, and
    a construction that calls that a forgery is measuring its own
    serialisation. Normalising here says so as a computation, which is
    what makes it checkable rather than a reading of the two names.
    """
    if isinstance(node, dict):
        out = {key: _order_blind(value) for key, value in node.items()}
        if isinstance(out.get("given"), list):
            out["given"] = sorted(
                out["given"], key=lambda g: json.dumps(g, sort_keys=True))
        return out
    if isinstance(node, list):
        return [_order_blind(value) for value in node]
    return node


#: Which complaint a renamed predicate earns here is a fact about the
#: PROBLEM, and three gates plant that same forgery — so it is answered in
#: one place, beside the other thing they all need to know about the door.


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


def _probability_program(given_names, declared=None) -> dict:
    """The smallest program that asks a conditional on N conditions.

    ``declared`` states that same conditional as a fact, which is what
    gives the answer a chain: the route evaluates the formula against what
    the program says, no data required.
    """
    def atom(name):
        return {"predicate": name, "args": [{"name": "p", "type": "const"}]}
    target = {"atom": atom("y"), "value": True}
    given = [{"atom": atom(name), "value": True} for name in given_names]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            *({"kind": "variable", "predicate": name, "domain": [True, False]}
              for name in ("y", "a", "b")),
            {"kind": "cause", "from": atom("a"), "to": atom("y")},
            *([{"kind": "probability", "provenance": "observational",
                "target": copy.deepcopy(target),
                "given": copy.deepcopy(given), "value": declared}]
              if declared is not None else ()),
            {"kind": "query", "id": "q", "query": {
                "kind": "probability", "target": target, "given": given}},
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


# ------------------------------------------------- the fact this rests on


def test_the_estimand_is_carried_by_the_answers_that_identify_one():
    """Stated so it cannot drift: which answers carry a formula, and that
    every one of them is a sum, product or fraction over probabilities.

    Some of them are on answers with no chain, and how many is asserted
    below rather than written here, where nothing would check it. An
    estimand reaches a reader whether or not a route was taken, so it is
    asked there too — at the door that holds what an answer says, which is
    what the whole of that answer is. That was ONE answer when this was
    written, and a single case is indistinguishable from an accident; it is
    a large part of the corpus now, which is the same fact about the door
    with the accident reading taken away from it.

    One estimand names no predicate at all — it came back a bare constant,
    which is a formula with nothing in it to be renamed. Counted here so
    that the rewriting tests below, which all work by renaming something,
    are known to be one row short of the whole rather than silently so.
    """
    assert len(WITH_FORMULA) == 104, len(WITH_FORMULA)
    assert len(CHAINLESS) == 40, len(CHAINLESS)
    assert len(NAMES_A_PREDICATE) == len(WITH_FORMULA) - 1
    for name in WITH_FORMULA:
        written = SHAPES[name]["result"]["formula"]
        assert written["kind"] in (
            "sum", "product", "fraction", "probability_ref", "constant"), (
                name, written["kind"])


# --------------------------------------------------- rewriting the estimand


@pytest.mark.parametrize("shape", NAMES_A_PREDICATE)
def test_a_factor_may_not_be_about_a_variable_the_graph_lacks(shape):
    """The cheapest forgery, and the one a semantic check used to answer
    with "no opinion": rename one predicate.

    Which rule says no is a fact about the problem, not about the forgery.
    Where the problem reports names, "is this formula about this problem"
    is answerable and answers first. Where it reports none — a program
    that causes nothing and carries no data — that question has no content
    and declines, and the estimand is held instead to the question beside
    it, which needs no names from anywhere. Both refuse; asserting only
    the first reason would read the second as a hole.
    """
    program, result = _pair(shape)
    assert _first(result["formula"], "predicate", lambda p: p + "_forged")
    with pytest.raises(VerificationError, match=renaming_refusal(program)):
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


def test_a_conjunctions_estimand_is_held_to_the_number_it_claims():
    """A counterfactual conjunction's estimand, replaced outright.

    The swap above exchanges two names and leaves an expression that is
    still shaped like an estimand. This puts the bluntest forgery there
    is to the same door: the whole estimand becomes a constant. Nothing
    about the chain changes, so the rule that checks the chain's own copy
    still finds it honest — which is the point. What must refuse this is
    the rule that reads what the ENVELOPE shows.

    Both constants are asked. Zero is the one that mattered: a conjunction
    whose ``P(γ)`` really is zero is rendered as the constant 0, and the
    chain rule skips probing that because the rule above it has confirmed
    the engine calls the query inconsistent. Nothing warrants that about
    the envelope's copy, so a zero written there is probed like anything
    else — and on an answer whose truth is not zero, refused.
    """
    conjunctions = sorted(
        name for name, pair in SHAPES.items()
        if pair["result"].get("query_kind") == "counterfactual_conjunction"
        and isinstance(pair["result"].get("formula"), dict))
    assert conjunctions, "no counterfactual conjunction carries an estimand"

    for name in conjunctions:
        honest_program, honest_result = _pair(name)
        the_door_for(honest_result)(honest_program, honest_result)

        truth = honest_result["formula"]
        for value in (0.0, 0.123):
            if truth.get("kind") == "constant" and truth.get("value") == value:
                continue  # writing what is already there forges nothing
            program, result = _pair(name)
            result["formula"] = {"kind": "constant", "value": value}
            with pytest.raises(VerificationError, match="does not compute"):
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

    Of the ones it can be tried on, all but a few are refused, and those
    few are one thing: problems that declare a shift between populations,
    where the arithmetic is deliberately not asked. How many of each is
    asserted below, where a re-collection of the corpus moves it and says
    so, rather than here where it would only go quietly out of date.

    They are sorted by a reason that is COMPUTED, not by name — five times
    now a reason written beside a name here has turned out to be a hole
    rather than a decline, and a name with a story beside it reads exactly
    the same either way. Each row has to land in a bucket whose test it
    passes, and a row that lands in none is a finding. The fifth left this
    list by that route: it landed in no bucket, was recorded with its
    measurement instead of an excuse, and the measurement is what showed
    the repair.
    """
    accepted, single, unchanged = [], [], []
    for shape in WITH_FORMULA:
        program, result = _pair(shape)
        names = sorted(_names(result["formula"]))
        if len(names) < 2:
            # A swap needs two names to exchange. Some estimands name one
            # predicate or none at all — a problem that declares a single
            # variable, and the bare constant a true-zero conjunction is
            # written as — so this construction forges nothing there.
            # Counted rather than passed over, because "the forgery was
            # accepted" and "there was no forgery" print the same.
            single.append(shape)
            continue
        lo, hi = names[0], names[-1]
        before = copy.deepcopy(result["formula"])

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
        if (json.dumps(_order_blind(before), sort_keys=True)
                == json.dumps(_order_blind(result["formula"]),
                              sort_keys=True)):
            # Nothing was forged: the two names exchanged are conditions of
            # one conditional, so the swap rewrote a list's order and not
            # an estimand. Filed before the door is asked, because a door
            # that accepts the formula it was already shown is not a door
            # that missed anything.
            unchanged.append(shape)
            continue
        try:
            the_door_for(result)(program, result)
        except VerificationError:
            continue
        accepted.append(shape)

    # The rows this construction could not put a question to at all, which
    # are a different fact about coverage than the rows it asked and lost.
    # An unasked row is where a hole would sit undisturbed.
    # They are two, and for two different reasons, so the count each one
    # names is asserted rather than just the pair: one estimand is a bare
    # constant naming nothing, and one is about a problem with a single
    # variable in it, where every name in the formula is that variable.
    assert single == [
        "needs_investigation:probability:none#6bdf54",
        "structurally_solved:counterfactual_conjunction:id_star_identification",
    ], single
    assert [len(_names(SHAPES[s]["result"]["formula"])) for s in single] == [
        1, 0]
    # And the rows where it asked nothing because it forged nothing:
    # conditionals whose two extreme names are both conditions, so the swap
    # rewrote the order of a list and not an estimand. Two of them.
    assert len(unchanged) == 2, unchanged
    for shape in unchanged:
        assert SHAPES[shape]["result"]["formula"]["kind"] == "probability_ref"

    # What is left is the remainder that was ASKED and accepted, and it is
    # sorted by a property of the row rather than by a sentence about it.
    #
    # A transporting answer's estimand takes its conditional from a source
    # domain and its marginal from the target; read as a formula in one
    # population it is a back-door adjustment over a set that does not
    # block the back door, so the arithmetic is not asked where the problem
    # declares selection nodes. That decline is written into the rule, and
    # what stands in its place — that a reader is TOLD the factors come
    # from two places — is a different gate's subject.
    declines = [s for s in accepted
                if any(st.get("kind") == "selection_node"
                       for st in SHAPES[s]["program"]["statements"])]
    assert len(declines) == 9, declines

    # And nothing else. There was one more, and how it left is the reason
    # this list is a classification rather than names with stories.
    #
    # A counterfactual conjunction with two names exchanged computed a
    # DIFFERENT number from the honest estimand on every sampled model, and
    # the probe said match. The measurement said no tolerance could fix it:
    # on the two models the probe drew, the forged gaps were 0.0075 and
    # 0.0008, while the largest gap an HONEST formula showed anywhere in
    # this corpus was 0.0103 — the forgery sat closer to the truth than
    # honest sampling error sat elsewhere. Lowering the tolerance could not
    # separate them and drawing more models raised the honest ceiling too.
    #
    # What the measurement was really saying is that the noise was the
    # problem, and the noise was a choice: the truth was sampled because an
    # exact one is exponential in the worst case. This problem's exogenous
    # space is 65,536. It is summed exactly now, in the time the sampling
    # took, and the forgery is refused by arithmetic.
    assert sorted(set(accepted) - set(declines)) == [], sorted(
        set(accepted) - set(declines))


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

    # Which record was held before. Where an answer carries the step the
    # chain half holds against the question, its ENVELOPE copy — the one
    # the report prints and the browser shows — could be forged and still
    # pass that door. An answer with no chain had nothing holding the
    # printed copy at all, and one of these two is each.
    #
    # Counted, not named. WHICH row carries the chain is a fact about the
    # sample this corpus happens to hold — a row is kept for the leaf
    # shapes it brings, not for the chain it carries — so the claim about
    # the SYSTEM is run rather than looked up.
    held = [name for name in probability
            if "formula_evaluation" in _chain_rules(_pair(name)[1])]
    assert len(held) == 1, held
    chained = themis.run(
        _probability_program(["a"], declared=0.42))["results"][0]
    assert "formula_evaluation" in _chain_rules(chained), chained


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

    # A variable that causes nothing is still a variable. Asked of a graph
    # that carries other names this is a stray one; asked of the problem it
    # is not, and a probability query is exactly the shape that has one.
    elsewhere = nx.DiGraph()
    elsewhere.add_node(x)
    lonely = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True), given=())
    assert formula_fits(elsewhere, lonely) is not None
    assert formula_fits(elsewhere, lonely, {y: (True, False)}) is None

    # With NEITHER source carrying a name, the question has no content:
    # the problem has names all the same, this rule was told none of them,
    # and it declines rather than calling every atom there is a stray.
    assert formula_fits(nx.DiGraph(), lonely) is None

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
    estimand, taken from the estimand the probe is asked about.

    Written out here, it agreed with that estimand only by naming the same
    variables. A re-collection of the corpus answered the same question
    from a program that calls its treatment something else, and the graph
    and the formula went on being about two different problems while each
    stayed correct on its own.
    """
    import networkx as nx

    from themis.types import Atom, ConstTerm

    def atom(node):
        return Atom(predicate=node["predicate"],
                    args=tuple(ConstTerm(name=arg["name"])
                               for arg in node["args"]))

    term = SHAPES["aipw"]["result"]["formula"]["body"]["terms"][0]
    y = atom(term["target"]["atom"])
    # The covariate is the one the sum binds — its value in the conditional
    # is a reference to the bound name; the treatment is the one held at a
    # value of its own.
    z = next(atom(g["atom"]) for g in term["given"]
             if isinstance(g["value"], dict))
    x = next(atom(g["atom"]) for g in term["given"]
             if not isinstance(g["value"], dict))
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

    The treatment's own name put in the outcome slot — ``P(x=true | x=true,
    z)`` summed over ``z`` — is identically one, and it is a forgery every
    name in which the problem declares, so only the arithmetic can catch
    it. Asked the old way, with Y's domain cut to the
    single value the formula is about, the probe calls it a match: the
    outcome is a constant in every sampled model, so the formula and the
    truth are both 1.0 and nothing can disagree. Asked with the value
    passed as the value it is, the same model still has an outcome.
    """
    from themis.verifier.semantic_probe import probe_identify_formula

    graph, x, y, _z = _one_covariate_graph()
    honest = _aipw_formula()
    identically_one = _aipw_formula(
        body__terms__0__target__atom__predicate=x.predicate)

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
        body__terms__0__target__atom__predicate=x.predicate)

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


def _a_problem_that_reports_no_names() -> dict:
    """One variable, asked about, causing nothing and carrying no data.

    Both places a problem's names are read from come off the analysis and
    not off the program text: the graph is built from the cause statements
    and the domains come from theta. Declare a variable, cause nothing with
    it, supply no distribution and ask about it, and both are empty while
    the problem plainly still has a name.
    """
    atom = {"predicate": "y", "args": [{"name": "me", "type": "const"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": {"atom": atom, "value": True},
                "given": []}},
        ],
    }


def test_a_problem_that_reports_no_names_is_declined_not_refused():
    """The system's own answer, refused by the system's own door.

    Widening the corpus to the answers that carry no number brought this
    one, and it is not a forgery: the program declares ``y``, the question
    asks about ``y``, the estimand written for a reader says ``P(y(me))``.
    Every atom of it was called a name the problem does not declare,
    because the two places names are read from were both empty and empty
    was read as "the problem has none".

    Whether a formula is ABOUT this problem is a question that needs the
    problem's names; with none reported it has no content, and a rule with
    nothing to judge by declines. The gap-name rule already meets the same
    emptiness and returns; this is that decline one rule along.
    """
    program = _a_problem_that_reports_no_names()
    result = themis.run(program)["results"][0]
    assert result.get("formula"), result
    the_door_for(result)(program, result)


def test_declining_that_question_does_not_decline_the_others():
    """And the answer on that same shape is still held to its question.

    A decline that took the rest of the door with it would buy an honest
    answer through at the price of every forgery on the same shape. The
    estimand a probability question carries is the conditional the question
    names, and comparing the two needs no names from anywhere else.
    """
    program = _a_problem_that_reports_no_names()
    result = themis.run(program)["results"][0]
    assert _first(result["formula"], "predicate", lambda p: p + "_forged")
    with pytest.raises(VerificationError):
        the_door_for(result)(program, result)
