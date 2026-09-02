"""The two names inside an estimand that arithmetic cannot see.

#545 gave the semantic probe its sight back, and what it could then refuse
it refused: rename a factor's predicate, flip the value a factor conditions
on, and the sampled models disagree. Two names survived every model, and
they survived for the same reason rather than by accident — nothing about
them changes any number.

An atom is a name AND the individual it is about. ``formula_fits`` compared
the formula's PREDICATES against the problem's predicates, so the arguments
reached no comparison at all; and a model asked about an atom it has never
heard of does not fail, it takes the boolean default, so ``P(y(nobody) |
...)`` evaluates to a number and the number agrees. A reader could be shown
an estimand about somebody this problem never mentions.

``SumExpr.over`` is the other. It reaches the evaluator only as
``theta.domain_of(over)`` — the domain to range across — and on a problem
whose variables are all binary every domain is the same tuple. So "sum over
z" may be rewritten to "sum over x" and every number in the answer is
identical, while the reader is told the wrong variable was adjusted for.

Neither is answerable by arithmetic. Both are answerable from the envelope,
because both are recorded twice:

- the graph's nodes are atoms and theta's domains are keyed by atoms, so
  the individual is already carried by both places a name may come from —
  only the comparison threw it away;
- a sum ranges over an atom and binds a variable to it, and the atom its
  body gives that variable to IS the atom it ranges over. This repository
  already says a sum's variable and the references to it are one name; the
  same sentence one level down names the atom.

Measured on the honest corpus before either was written: twenty-three
formulas, none naming an atom the problem does not carry; twenty-five sums,
none whose ``over`` disagrees with what its body binds, none binding
nothing.

And measured while writing it: three of the twenty-three are written over
bare predicates, ``y`` rather than ``y(u)``, so they name no individual and
there is none in them to get wrong. Named below rather than skipped. Which
spelling a producer should use is a question this file does not answer —
that two spellings are in the tree is a finding of its own.

The corpus has since widened to the answers that carry no number, and the
counts below moved with it — twenty-eight formulas, thirty-one sums, and
the same three bare-predicate producers, which is what makes the last of
those a fact about three producers rather than about a corpus size.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

import themis
from tests.answer_corpus import reads, verify_honestly
from themis.types import (
    Atom, BindDecl, ConstTerm, ProbabilityRefExpr, ProductExpr, SumExpr,
    ValuedAtom, VarRef,
)
from themis.verifier.errors import VerificationError
from themis.verifier.semantic_probe import _atom_text, formula_fits
from themis.verifier.serialization import _DECODE_BY_KIND

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

WITH_FORMULA = sorted(
    name for name, pair in SHAPES.items() if "formula" in pair["result"])


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _decode(written: dict):
    return _DECODE_BY_KIND[written["kind"]](written)


def _objects(node, apply, *, only_first=False, done=None):
    """Rewrite the individuals atoms are about, and nothing else.

    An atom's arguments are spelled ``name`` under ``args``, and so are a
    sum's bound variable and the references to it — one key, three
    meanings. Rewriting a bind asks the question the unbound-reference
    check already answers, so this walks into ``args`` and only there.
    Returns how many it moved.
    """
    done = [] if done is None else done
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "args" and isinstance(value, list):
                for term in value:
                    if isinstance(term, dict) and isinstance(
                            term.get("name"), str):
                        if only_first and done:
                            continue
                        term["name"] = apply(term["name"])
                        done.append(term["name"])
            else:
                _objects(value, apply, only_first=only_first, done=done)
    elif isinstance(node, list):
        for value in node:
            _objects(value, apply, only_first=only_first, done=done)
    return len(done)


# ------------------------------------------------- the facts this rests on


def test_every_honest_estimand_names_only_atoms_the_problem_carries():
    """Stated as the measurement the rule is built on, not as a hope.

    Whole atoms, from the two places a name may come from — the graph's
    nodes and theta's declared domains — because neither is complete alone.
    """
    from themis.verifier.semantic_probe import _atoms_and_refs

    checked = 0
    for name in WITH_FORMULA:
        program, result = _pair(name)
        formula = _decode(result["formula"])
        named, _unbound = _atoms_and_refs(formula)
        assert named, name
        objects = {o["name"] for o in program["domain"]["objects"]}
        for atom in named:
            assert {t.name for t in atom.args} <= objects, (name, atom)
        checked += 1
    assert checked == 28, checked


def test_every_honest_sum_ranges_over_the_atom_its_body_binds():
    from themis.verifier.semantic_probe import _bound_to, _sums

    sums = 0
    for name in WITH_FORMULA:
        _program, result = _pair(name)
        for total in _sums(_decode(result["formula"])):
            ranged = _bound_to(total.body, total.bind.name)
            assert ranged == {total.over}, (name, total.over, ranged)
            sums += 1
    assert sums == 31, sums


def test_an_atom_is_written_the_way_a_reader_writes_one():
    u = ConstTerm(name="u")
    assert _atom_text(Atom(predicate="y", args=(u,))) == "y(u)"
    assert _atom_text(Atom(predicate="y", args=())) == "y"
    assert _atom_text(
        Atom(predicate="m", args=(u, ConstTerm(name="v")))) == "m(u, v)"


# ------------------------------------------- an estimand about somebody else


def _has_an_individual(name: str) -> bool:
    _program, result = _pair(name)
    return bool(_objects(result["formula"], lambda n: n))


#: Estimands written over atoms with no arguments at all — ``y`` rather
#: than ``y(u)``. There is no individual in them to name wrongly, so the
#: forgeries below have nothing to move.
ABOUT_NOBODY = sorted(n for n in WITH_FORMULA if not _has_an_individual(n))

#: An answer that took no route carries no derivation, and the door below
#: refuses one before reading a word of it. A refusal made for what an
#: answer IS is not a witness that the forgery was seen, so the row is left
#: out of the forgeries and said out loud in the test beside them.
READ_BY_THE_DOOR = {name for name, pair in SHAPES.items()
                    if reads(pair["result"])}
ABOUT_SOMEBODY = sorted(
    (set(WITH_FORMULA) - set(ABOUT_NOBODY)) & READ_BY_THE_DOOR)


def test_the_estimands_that_name_no_individual_are_named():
    """Declared rather than skipped: a fourth one fails here and somebody
    decides, instead of it disappearing into a skip message.

    Three producers write their estimand over bare predicates while the
    other twenty carry the object through. Which spelling is right is not
    this file's question — that the answer is one of two spellings, and
    that only one of them can be got wrong, is.
    """
    assert ABOUT_NOBODY == ["ctf_conjunction_plugin",
                            "frontdoor_empirical_linear",
                            "measurement_error_correction"], ABOUT_NOBODY


@pytest.mark.parametrize("shape", ABOUT_SOMEBODY)
def test_a_factor_may_not_be_about_an_individual_the_problem_lacks(shape):
    """The forgery a predicate comparison cannot see: every NAME is real
    and the formula is about a different person."""
    program, result = _pair(shape)
    assert _objects(result["formula"], lambda n: n + "_forged")
    with pytest.raises(VerificationError, match="does not declare"):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", ABOUT_SOMEBODY)
def test_one_factor_alone_may_not_be_about_somebody_else(shape):
    """And it is refused when only ONE factor is moved, which is the shape
    a rewrite takes: the rest of the estimand still reads correctly."""
    program, result = _pair(shape)
    assert _objects(result["formula"], lambda n: n + "_forged",
                    only_first=True) == 1
    with pytest.raises(VerificationError, match="does not declare"):
        themis.verify(program, result)


def test_the_message_names_the_atom_and_not_just_its_predicate():
    """A reader of the refusal has to be able to see what moved: ``y(v)``
    against ``y(u)`` says it, ``y`` against ``y`` does not."""
    program, result = _pair("aipw")
    _objects(result["formula"], lambda n: n + "_forged", only_first=True)
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert "(u_forged)" in str(caught.value)
    assert "(u)" in str(caught.value)


# ------------------------------------ a sum that ranges over another variable


def _one_covariate_graph():
    u = (ConstTerm(name="u"),)
    x, y, z = (Atom(predicate=p, args=u) for p in ("x", "y", "z"))
    graph = nx.DiGraph()
    graph.add_edges_from([(z, x), (z, y), (x, y)])
    return graph, x, y, z


def _backdoor_formula(over, bound_atom=None):
    """``Σ_over P(y|x, bound) P(bound)`` — the shape of a back-door
    estimand, with the atom it sums over and the atom its body binds
    settable apart so the two can be made to disagree."""
    _graph, x, y, z = _one_covariate_graph()
    bound_atom = z if bound_atom is None else bound_atom
    bind = BindDecl(name="v")
    ref = VarRef(name="v")
    return SumExpr(
        bind=bind, over=over,
        body=ProductExpr(terms=(
            ProbabilityRefExpr(
                target=ValuedAtom(atom=y, value=True),
                given=(ValuedAtom(atom=x, value=True),
                       ValuedAtom(atom=bound_atom, value=ref))),
            ProbabilityRefExpr(
                target=ValuedAtom(atom=bound_atom, value=ref), given=()),
        )))


def test_a_sum_over_one_variable_that_binds_another_is_refused():
    """The counter-example this exists for. Both names are real, the
    formula is well formed, every number it produces is unchanged — and it
    tells a reader a different variable was adjusted for."""
    graph, x, _y, z = _one_covariate_graph()
    assert formula_fits(graph, _backdoor_formula(over=z)) is None

    verdict = formula_fits(graph, _backdoor_formula(over=x))
    assert verdict is not None and verdict.status == "unfit"
    assert "ranges over and the atom its body binds are one thing" in (
        verdict.detail)
    assert "x(u)" in verdict.detail and "z(u)" in verdict.detail


def test_the_numbers_do_not_change_when_that_name_does():
    """Why no probe can answer it. ``over`` reaches the evaluator only as
    the domain to range across, and both variables are binary, so the
    formula computes the same value either way — which is what makes this
    a question for the envelope's own second record rather than for a
    model."""
    from themis.runtime.numeric_estimator import Theta, ve_estimate_formula

    _graph, x, y, z = _one_covariate_graph()
    theta = Theta(entries={}, domains={a: (True, False) for a in (x, y, z)})
    for atom, given, value in (
            (y, ((x, True), (z, True)), 0.7),
            (y, ((x, True), (z, False)), 0.2),
            (z, (), 0.5)):
        from themis.runtime.numeric_estimator import ProbabilityKey
        for target_value in (True, False):
            theta.entries[ProbabilityKey(
                target_atom=atom, target_value=target_value,
                given=frozenset(given))] = (
                    value if target_value else 1.0 - value)

    honest = ve_estimate_formula(_backdoor_formula(over=z), theta)
    swapped = ve_estimate_formula(_backdoor_formula(over=x), theta)
    assert honest == swapped


def test_a_sum_that_binds_nothing_is_left_alone():
    """A sum whose body never uses its variable is a different complaint,
    and one the unbound-reference check above already has an opinion about.
    Reading it as a disagreement would refuse on a shape this rule has no
    measurement for — twenty-five honest sums, none of them this."""
    graph, _x, y, z = _one_covariate_graph()
    binds_nothing = SumExpr(
        bind=BindDecl(name="v"), over=z,
        body=ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=True), given=()))
    assert formula_fits(graph, binds_nothing) is None


# ------------------------------------------------------ and nothing else moved


def test_every_honest_answer_shape_is_still_accepted():
    """Every shape, including the ones this door will not read: those are
    refused for having no derivation and for nothing else, which is what
    says the rules above added no complaint to them.

    One estimand is on such an answer — a formula reaches a reader whether
    or not a route was taken — so the individual it names is a claim no
    public door asks about. That is the door's precondition and not this
    rule's business, and it is counted where the other door-shaped hole is.
    """
    unread = sorted(set(SHAPES) - READ_BY_THE_DOOR)
    assert sorted(set(WITH_FORMULA) & set(unread)) == [
        "needs_investigation:probability:none"]
    for name in sorted(SHAPES):
        verify_honestly(*_pair(name))
