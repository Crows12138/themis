"""A block reporting no number is still making a claim.

A mediation decomposition says which route was taken and then says what
was computed along it. The second half was audited by one rule, and that
rule hangs off the derivation step that did the evaluating -- so it read
the step's copy of the block and never the envelope's, which is the copy
a report is rendered from. Eight of the thirteen answers this repository
has collected that carry such a block carry NO evaluation step at all:
no arm of them produced a number -- an arm that ran out of theta or one
the graph never identified, which are different reasons for the same
absence -- so the step that would have recorded one was never built.
Their numbers and their account of the shortfall were read by nothing.

And the rule excluded the shortfall by construction. Two lines of it --
``if nde_nie_adj is not None and "nde_nie_status" not in claimed_output``
and its twin -- said that an arm which aborted is an arm with nothing to
check, the abort being "a valid outcome" and its message "metadata for
downstream consumers". But an abort is a claim, and a specific one: THIS
probability was the one theta did not have, THIS reference point is where
the walk stopped, and it was THIS species of shortfall -- a theta holding
nothing, or a theta holding a marginal the declared graph refuses to let
stand in for the conditional demanded. Those are three different things
for a reader to go and do, and each is a fact about the graph and the
theta in front of the verifier.

So the re-derivation moved to where it can serve both copies. One
function knows what the block claims;
:func:`themis.verifier.rules._rule_mediation_numeric_evaluate` calls it
for the step's copy and
:func:`themis.verifier.verify_mediation_decomposition_numeric` for the
envelope's, on the route, where every answer passes whether or not it has
a chain. Two audits on that route and not one widened: whether the
decomposition is IDENTIFIED is a question about the graph, and an audit
handed more premises than its question needs is an audit whose reader
cannot tell which premise a refusal came from.

THE CEILING IS NOT HELD, and that is a decision rather than an oversight.
The grid-cap shape reports the number of reference points it refused to
enumerate and the ceiling it was past. The count is checkable -- it is the
Cartesian product of the mediators' own theta domains -- and so is the
absence of a table beside an abandoned grid. The ceiling is a build
policy with no second witness anywhere in this package, and reading the
producer's constant back would be agreeing with it by construction. It is
in the roster below, with what it would take to close it.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis import gaps
from themis.kernel import _RouteFacts
from themis.verifier import (
    rules as _rules,
    verify_mediation_decomposition_numeric,
)
from themis.verifier.errors import RuleCheckFailed, VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))

#: The two spellings of one block -- singular mediator and mediator set.
BLOCKS = ("mediation_decomposition", "mediation_joint_decomposition")

#: Every lie in the sweep below that this file does NOT catch, and why.
#:
#: A ceiling is what the build would enumerate, not what this answer
#: found, so an answer whose grid is past a SMALLER forged ceiling
#: contradicts nothing it says. Closing it means declaring the ceiling
#: where both layers read it -- the move ``gaps.WORTH`` is -- and the
#: corpus row carrying this shape was collected while a test had lowered
#: the ceiling to 2, so a verifier reading the declared 16 would report
#: that row as an answer no unpatched build gives. Which it is.
SURVIVING = {("cap", 0)}


def _rows():
    """Every stored answer carrying one of these blocks, with the block."""
    for name in sorted(SHAPES):
        pair = SHAPES[name]
        extensions = pair["result"].get("extensions") or {}
        for block_name in BLOCKS:
            block = extensions.get(block_name)
            if isinstance(block, dict):
                yield name, block_name, pair


ROWS = tuple(_rows())
CARRYING = tuple(sorted({name for name, _, _ in ROWS}))


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, path + (index,))
    else:
        yield path, node


def _lies(value):
    """What a lie about this leaf looks like.

    The block's leaves carry no declared vocabulary of their own except
    the two status words, which are bent into each other below by the
    sweep itself -- every other word here is a rendered probability, a
    reference point or a number.
    """
    if isinstance(value, bool):
        return (not value,)
    if isinstance(value, str):
        return (value + "_forged", "")
    if isinstance(value, int):
        return (value + 7, 0)
    if isinstance(value, float):
        return (value * 3.0 + 1.0, 0.0)
    return ()


def _at(node, path):
    for step in path[:-1]:
        node = node[step]
    return node


def _bent(pair, block_name, path, lie):
    forged = copy.deepcopy(pair["result"])
    numeric = forged["extensions"][block_name]["numeric"]
    _at(numeric, path)[path[-1]] = lie
    return forged


def _sweep():
    """Every lie this file asks about, one test each."""
    for name, block_name, pair in ROWS:
        numeric = pair["result"]["extensions"][block_name].get("numeric")
        if not isinstance(numeric, dict):
            continue
        for path, value in _leaves(numeric):
            for lie in _lies(value):
                if lie == value:
                    continue
                yield name, block_name, path, lie


SWEEP = tuple(_sweep())


def _ident(name, block_name, path, lie):
    return f"{name}|{block_name}|{'.'.join(map(str, path))}|{lie!r}"


# ------------------------------------------------------- what is here at all


def test_the_answers_carrying_this_block_are_the_ones_it_was_measured_on():
    """Thirteen answers, one block each -- and the five is the point of
    the file: an audit hung off the evaluation step could reach only five
    of the thirteen, and on the one of those five that aborted it said
    nothing at all."""
    assert len(ROWS) == 13
    assert len(CARRYING) == 13
    with_step = [
        name for name in CARRYING
        if "mediation_numeric_evaluate" in [
            step.get("rule")
            for step in (SHAPES[name]["result"].get("derivation") or {})
            .get("steps") or ()]]
    assert len(with_step) == 5


def test_every_stored_block_is_read_by_the_envelope_audit():
    """Before any lie: the honest answers pass. A door that refuses an
    honest answer witnesses nothing about a forged one."""
    for name, block_name, pair in ROWS:
        program, result = pair["program"], pair["result"]
        themis.verify_answer_claims(program, result)
        assert result["extensions"][block_name] is not None, name


# ---------------------------------------------------------------- the lies


@pytest.mark.parametrize(
    "name,block_name,path,lie", SWEEP,
    ids=[_ident(*row) for row in SWEEP])
def test_a_forged_leaf_of_this_block_is_refused_at_the_door_with_no_chain(
        name, block_name, path, lie):
    """The door that reads an answer without re-running its derivation,
    which is the only door most of these answers have anything to say
    to."""
    pair = SHAPES[name]
    forged = _bent(pair, block_name, path, lie)
    if (path[-1], lie) in SURVIVING:
        themis.verify_answer_claims(pair["program"], forged)
        return
    with pytest.raises(Exception):
        themis.verify_answer_claims(pair["program"], forged)


def test_the_lies_left_uncaught_are_the_ones_the_roster_names():
    """A roster and not a skip: the file says which lie it does not
    catch, so the next reader finds a decision rather than a gap."""
    loose = set()
    for name, block_name, path, lie in SWEEP:
        pair = SHAPES[name]
        forged = _bent(pair, block_name, path, lie)
        try:
            themis.verify_answer_claims(pair["program"], forged)
        except Exception:
            continue
        loose.add((path[-1], lie))
    assert loose == SURVIVING


def test_the_ceiling_is_unheld_only_where_the_answer_says_nothing_about_it():
    """What the ceiling leaf is NOT free to be. A grid of four is past a
    ceiling of two and past a ceiling of zero, and the answer records the
    same refusal either way -- but a grid of four is not past four, and
    an answer claiming it was is refused like anything else."""
    rows = [(name, block_name, pair) for name, block_name, pair in ROWS
            if (pair["result"]["extensions"][block_name].get("numeric") or {})
            .get("cde_status", {}).get("status") == "too_many_reference_points"]
    assert len(rows) == 1
    name, block_name, pair = rows[0]
    numeric = pair["result"]["extensions"][block_name]["numeric"]
    grid = numeric["cde_status"]["reference_point_count"]

    below = _bent(pair, block_name, ("cde_status", "cap"), grid - 1)
    themis.verify_answer_claims(pair["program"], below)

    for past in (grid, grid + 1):
        forged = _bent(pair, block_name, ("cde_status", "cap"), past)
        with pytest.raises(Exception):
            themis.verify_answer_claims(pair["program"], forged)


# ------------------------------------------------- the block's second copy


def _with_a_step():
    for name in CARRYING:
        result = SHAPES[name]["result"]
        for index, step in enumerate(
                (result.get("derivation") or {}).get("steps") or ()):
            if step.get("rule") == "mediation_numeric_evaluate":
                yield name, index


WITH_A_STEP = tuple(_with_a_step())


@pytest.mark.parametrize("name,index", WITH_A_STEP,
                         ids=[f"{n}|{i}" for n, i in WITH_A_STEP])
def test_the_step_s_own_copy_is_read_where_there_is_one(name, index):
    """The same block reaches a reader twice and both copies are claims.
    The step rule held its copy of the NUMBERS all along; what it passed
    over was a copy that reported none."""
    pair = SHAPES[name]
    forged = copy.deepcopy(pair["result"])
    output = forged["derivation"]["steps"][index]["output"]["items"]
    bent = False
    for key in ("cde_status", "nde_nie_status"):
        if key in output:
            output[key]["items"]["status"] = "insufficient_theta_forged"
            bent = True
    if not bent:
        for key in ("cde", "nde_nie"):
            if key in output:
                inner = output[key]["items"]
                first = sorted(inner)[0]
                inner[first] = {"kind": "float", "value": 0.4242}
                bent = True
                break
    assert bent, name
    with pytest.raises(Exception):
        themis.verify(pair["program"], forged)


# ------------------------------------------------------ one auditor, not two


def test_the_g_formulas_are_rebuilt_in_one_place():
    """The defect this file closes was two auditors at two altitudes, so
    what is pinned is that there is now one. Every call of the two
    mediation formula builders sits inside the shared auditor's own
    helpers; a third caller is a third opinion about what the block
    says."""
    source = (ROOT / "themis" / "verifier" / "rules.py").read_text("utf-8")
    tree = ast.parse(source)
    builders = {
        "_verifier_build_mediation_potential_outcome_formula",
        "_verifier_build_mediation_controlled_outcome_formula",
    }
    callers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id in builders):
                callers.add(node.name)
    assert callers == {
        "_verifier_hold_mediation_natural",
        "_verifier_hold_mediation_controlled",
    }, sorted(callers)


def test_the_step_rule_no_longer_decides_what_an_abort_is_worth_checking():
    """The two lines this frontier removed, pinned by their absence. A
    rule that returns early on a status is a rule that cannot see the
    claim the status makes."""
    source = (ROOT / "themis" / "verifier" / "rules.py").read_text("utf-8")
    assert '"nde_nie_status" not in claimed_output' not in source
    assert '"cde_status" not in claimed_output' not in source


def test_the_route_carries_the_parameters_its_audits_need():
    """``theta`` was in hand where these facts are assembled and was not
    passed, which is the whole reason the numeric audit lived on a step.
    """
    assert "theta" in {field.name for field in _RouteFacts.__dataclass_fields__.values()}


# -------------------------------------------------------- what an abort says


def test_the_two_species_of_shortfall_are_told_apart_by_the_theta():
    """A theta holding nothing and a theta holding a marginal the graph
    refuses are different problems with different fixes, and an answer
    files them as different species. Both are in the corpus, so both are
    re-derived rather than accepted."""
    species = set()
    for _name, block_name, pair in ROWS:
        numeric = pair["result"]["extensions"][block_name].get("numeric") or {}
        for key in ("cde_status", "nde_nie_status"):
            need = (numeric.get(key) or {}).get("need")
            if need is not None:
                species.add(need)
    assert species == {
        str(gaps.Need.THETA_ENTRY_MISSING),
        str(gaps.Need.GRAPH_CONTRADICTS_SUPPLIED_MARGINAL),
    }


def test_the_occasion_a_refused_marginal_names_is_four_facts_and_not_a_sentence():
    """What the evaluator hands over when the d-sep guard refused a
    marginal theta does hold. It used to hand over the sentence it had
    built from these, and a sentence is not something an answer's own
    four slots can be compared with."""
    rows = [(block_name, pair) for _n, block_name, pair in ROWS
            if str(gaps.Need.GRAPH_CONTRADICTS_SUPPLIED_MARGINAL) in
            json.dumps(pair["result"]["extensions"][block_name])]
    assert len(rows) == 1
    block_name, pair = rows[0]
    said = (pair["result"]["extensions"][block_name]["numeric"]
            ["nde_nie_status"]["said"])
    assert set(said) == {"key", "have", "variable", "extras", "conditioning"}
    for slot in ("have", "variable", "extras", "conditioning"):
        forged = _bent(pair, block_name, ("nde_nie_status", "said", slot),
                       said[slot] + "_forged")
        with pytest.raises(Exception):
            themis.verify_answer_claims(pair["program"], forged)


def test_a_slot_naming_a_set_is_read_as_the_set_it_names():
    """Both layers join a frozenset with commas, so the order two atoms
    come out in is that run's hashing. Comparing the rendered strings
    would make an honest answer refusable by the seed it was produced
    under."""
    assert (_rules._verifier_names_in("m1,m2")
            == _rules._verifier_names_in("m2,m1")
            == frozenset({"m1", "m2"}))
    assert _rules._verifier_names_in("\u2205") == frozenset()
    assert _rules._verifier_names_in(None) is None


def test_an_arm_the_block_does_not_claim_is_not_asked_for_a_number():
    """An arm reported non-identifiable produced nothing, so there is
    nothing of it to re-derive -- and whether THAT claim is true is the
    sibling audit's question, asked on the graph alone."""
    rows = [(block_name, pair) for _n, block_name, pair in ROWS
            if not (pair["result"]["extensions"][block_name].get("nde_nie")
                    or {}).get("identifiable", True)]
    assert len(rows) == 2
    for block_name, pair in rows:
        numeric = pair["result"]["extensions"][block_name]["numeric"]
        assert "nde_nie_status" not in numeric
        assert "te" not in numeric
        themis.verify_answer_claims(pair["program"], pair["result"])


def test_the_envelope_audit_says_nothing_about_an_answer_with_no_theta():
    """The premises decide what can be asked. Called without theta it
    returns, rather than reporting every number as unverifiable."""
    _name, block_name, pair = ROWS[0]
    block = pair["result"]["extensions"][block_name]
    verify_mediation_decomposition_numeric(block, None, None, None, None)


def test_a_refusal_from_each_altitude_names_where_it_came_from():
    """A step failure carries a step index and an envelope failure does
    not, which is why the shared auditor is handed the refusal rather
    than raising its own."""
    assert issubclass(RuleCheckFailed, Exception)
    assert issubclass(VerificationError, Exception)
    name, block_name, pair = ROWS[0]
    forged = _bent(pair, block_name, ("cde_status", "missing_key"), "P(nope)")
    with pytest.raises(VerificationError) as caught:
        themis.verify_answer_claims(pair["program"], forged)
    assert "mediation_numeric" in str(caught.value)
