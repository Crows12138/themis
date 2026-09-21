"""The method word is a switch, so the blocks are asked instead.

Eleven rules in the verifier open with ``if estimate.get("method") != X:
return``. That makes the word more than a label: editing it does not
merely misreport which estimator ran, it turns off the rule that would
have re-derived the block that estimator left behind. Measured before
this existed: on three stored answers the word could be rewritten to
``aipw`` -- a method that writes none of those blocks -- and every public
door said yes, two of them with a whole derivation chain beside them.

What is asserted here:

- the table is the gates, read out of the package's own source rather
  than asserted beside it, so a gate added or moved fails here instead of
  quietly leaving a block unguarded
- no stored answer disagrees with it, counted
- every honest answer carrying a guarded block is accepted, and the block
  three methods share is accepted under each of the three
- every method that does not write a present block is refused, swept over
  the whole declared vocabulary rather than sampled
- the rule is reached through the public door, which the sweep above does
  not show because it asks the rule directly
- the silences are exercised at the rule: no estimate, no method word, a
  block no gate guards.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.verifier.errors import VerificationError
from themis.verifier.method_block_rules import (
    WRITTEN_BY,
    verify_a_block_names_the_method_that_wrote_it,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
VERIFIER = HERE.parent / "themis" / "verifier"

#: Every method the contract lets an ESTIMATE name. Read at its own path
#: rather than by looking for the word anywhere in the document: a bounds
#: row names a method too, out of a different vocabulary, and sweeping
#: with those produces forgeries validation refuses before a rule sees
#: them -- which would score as caught while nothing had been asked.
METHODS = frozenset(json.loads(
    (HERE.parent / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8")
)["properties"]["numeric_estimate"]["properties"]["method"]["enum"])


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "value"``, which is how a gate names its own."""
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(
                node.value, ast.Constant) and isinstance(
                    node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value.value
    return found


def _gets(node: ast.AST, name: str) -> bool:
    """Is this ``<something>.get("<name>")``?"""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == name)


def _key(node: ast.AST, constants: dict[str, str]) -> str | None:
    """The key a ``.get`` asks for, spelled out or named by a constant."""
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args):
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return constants.get(arg.id)
    return None


def _the_gates() -> dict[str, set[str]]:
    """Every method gate in the package, and the block behind it.

    Read out of the source because that is what the table claims to be:
    not a census of what has occurred, but a list of the pairs this
    package is prepared to re-derive. Read as SYNTAX rather than by
    matching text, because the sentence being looked for is also the one
    the rule's own prose quotes, and prose that describes a gate is not
    one.

    The subject has to be the estimate. A bounds row carries a method as
    well, out of its own vocabulary, and a rule that declines to read one
    is declining about something else.
    """
    gates: dict[str, set[str]] = {}
    for path in sorted(VERIFIER.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _string_constants(tree)
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            blocks = {
                key for call in ast.walk(func)
                if (key := _key(call, constants)) in WRITTEN_BY
            }
            if not blocks:
                continue
            for node in ast.walk(func):
                if not (isinstance(node, ast.Compare)
                        and len(node.ops) == 1
                        and isinstance(node.ops[0], ast.NotEq)
                        and _gets(node.left, "method")):
                    continue
                subject = node.left.func.value           # type: ignore[attr-defined]
                if not (isinstance(subject, ast.Name)
                        and subject.id in {"estimate", "ne"}):
                    continue
                said = node.comparators[0]
                if isinstance(said, ast.Constant):
                    method = said.value
                elif isinstance(said, ast.Name):
                    method = constants.get(said.id)
                else:
                    method = None
                assert isinstance(method, str), (path.name, said)
                for block in blocks:
                    gates.setdefault(block, set()).add(method)
    return gates


def test_the_table_is_the_gates_it_restates():
    """Read out of the source, not asserted beside it.

    The table says which methods each guarded block is read under, and
    the gates are where that is decided. Reproducing one from the other
    is what makes the table a restatement rather than a second opinion: a
    gate added without a row here, or a row here for a gate nobody wrote,
    fails this line.

    The count is asserted as well. This finds gates written one way, and
    a gate written another way would be MISSING rather than wrong --
    which reads exactly like a package that has ten of them.
    """
    gates = _the_gates()
    assert {b: frozenset(m) for b, m in gates.items()} == WRITTEN_BY, gates
    assert sum(len(m) for m in gates.values()) == 11, gates


def test_the_block_three_methods_share():
    """The row that decides the shape of this rule.

    A correction to the treatment, one to the exposure and the combined
    route all write ``measurement_correction``, and no one of their three
    gates knows the other two. A check added at each gate would refuse
    the honest exposure answer in the name of the treatment rule, which
    is why the correspondence is stated in one place instead.
    """
    assert WRITTEN_BY["measurement_correction"] == frozenset({
        "measurement_error_correction",
        "exposure_measurement_error_correction",
        "combined_measurement_error_correction",
    })
    assert all(len(m) == 1 for b, m in WRITTEN_BY.items()
               if b != "measurement_correction")
    carried = sorted(
        name for name, pair in SHAPES.items()
        if isinstance((pair["result"] or {}).get("numeric_estimate"), dict)
        and pair["result"]["numeric_estimate"].get(
            "measurement_correction") is not None)
    assert {SHAPES[n]["result"]["numeric_estimate"]["method"]
            for n in carried} == WRITTEN_BY["measurement_correction"], carried
    for name in carried:
        verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


#: (answer, block) for every stored answer carrying a guarded block.
CARRIERS = sorted(
    (name, block)
    for name, pair in SHAPES.items()
    for block in WRITTEN_BY
    if isinstance((pair["result"] or {}).get("numeric_estimate"), dict)
    and (pair["result"]["numeric_estimate"].get(block) is not None)
)


def test_no_stored_answer_disagrees_with_the_table():
    """The honest floor, as a number.

    Twenty-one stored answers carry a guarded block, across all nine of
    them, and every one names a method the table says writes it. A
    producer that starts writing one of these blocks from somewhere else
    breaks this line, where the fact is, rather than arriving as a
    refusal nobody can place.
    """
    assert len(CARRIERS) == 21, CARRIERS
    assert len({b for _, b in CARRIERS}) == 9, sorted({b for _, b in CARRIERS})
    for name, block in CARRIERS:
        method = SHAPES[name]["result"]["numeric_estimate"]["method"]
        assert method in WRITTEN_BY[block], (name, block, method)


@pytest.mark.parametrize("name", sorted({n for n, _ in CARRIERS}))
def test_an_honest_answer_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_method_that_does_not_write_a_present_block_is_refused():
    """Swept over the whole vocabulary, not sampled.

    For each answer carrying a guarded block, every other method the
    contract declares is put in its place. A rule holding only the swaps
    somebody thought of would leave the rest of the vocabulary as a way
    through, and the vocabulary is where a forger picks from -- a name
    outside it is refused by validation and never reaches a rule at all.

    Asked of the rule rather than through the door, so that what is being
    counted is this rule's reach. That it is reached at all is the test
    below.

    The total is arithmetic, not a number read off a run: fourteen of the
    twenty-one carried blocks have one writer and are swept with the
    other forty-eight, and the seven carrying the shared block are swept
    with the other forty-six. A count that stops matching means one of
    those three figures moved.
    """
    assert len(METHODS) == 49, len(METHODS)
    refused = 0
    for name, block in CARRIERS:
        estimate = SHAPES[name]["result"]["numeric_estimate"]
        for method in sorted(METHODS - WRITTEN_BY[block]):
            forged = {**estimate, "method": method}
            with pytest.raises(VerificationError):
                verify_a_block_names_the_method_that_wrote_it(
                    {"numeric_estimate": forged})
            refused += 1
    assert refused == 14 * 48 + 7 * 46 == 994, refused


def test_the_rule_is_reached_through_the_public_door():
    """Wired, which a rule tested only in its own room is not.

    One forgery, through the door a caller actually uses. The sweep above
    says the rule refuses; this says the refusal happens to an answer
    that arrives the ordinary way.
    """
    name, block = "transport_post_stratification", "post_stratification"
    pair = SHAPES[name]
    assert pair["result"]["numeric_estimate"].get(block) is not None
    forged = copy.deepcopy(pair["result"])
    forged["numeric_estimate"]["method"] = "aipw"
    with pytest.raises(VerificationError) as refusal:
        the_door_for(pair["result"])(pair["program"], forged)
    assert "switched off" in str(refusal.value), refusal.value


def test_the_refusal_names_the_block_and_the_word():
    """Not a count: the sentence has to say which two things disagree.

    A reader who gets this cannot tell from the outside whether the block
    was planted or the word was moved, and neither can the rule. What it
    can do is name both and say what the disagreement costs -- the audit
    of that block did not run -- rather than pick one of them to accuse.
    """
    with pytest.raises(VerificationError) as refusal:
        verify_a_block_names_the_method_that_wrote_it(
            {"numeric_estimate": {"method": "aipw",
                                  "measurement_correction": {"form": "x"}}})
    said = str(refusal.value)
    assert "measurement_correction" in said, said
    assert "aipw" in said, said
    for method in sorted(WRITTEN_BY["measurement_correction"]):
        assert method in said, said
    assert "switched off" in said, said


def test_the_silences_this_rule_keeps():
    """Four occasions to say nothing, put to the rule directly.

    A block no gate guards is the one worth exercising: this rule says
    nothing about it, because the table is a list of the pairs the
    package can re-derive and a block nobody has claimed yet is not a
    disagreement. Guessing at one would be inventing a claim out of the
    shape of a key.
    """
    verify_a_block_names_the_method_that_wrote_it({})
    verify_a_block_names_the_method_that_wrote_it({"numeric_estimate": None})
    verify_a_block_names_the_method_that_wrote_it(
        {"numeric_estimate": {"post_stratification": [1]}})
    verify_a_block_names_the_method_that_wrote_it(
        {"numeric_estimate": {"method": "aipw",
                              "dose_response_curve": [1]}})
    assert "dose_response_curve" not in WRITTEN_BY

    with pytest.raises(VerificationError):
        verify_a_block_names_the_method_that_wrote_it(
            {"numeric_estimate": {"method": "aipw",
                                  "post_stratification": [1]}})
