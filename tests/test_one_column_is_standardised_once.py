"""One column, one standardisation -- and the run has to agree with itself.

A sieve records, per factor, the constants its family fitted. Nothing on the
envelope can recompute one: "the mean of this column" needs the rows, and the
rows are what a record of moments exists to replace. The checks that did read
these designs read them against the QUERY's declaration, and a query that
declares no basis leaves them unread -- which is every stored answer here.

What was never asked is how many times one column was standardised. The
outcome bridge's span and the treatment bridge's moments are both functions
of W; the outcome bridge's moments and the treatment bridge's span are both
functions of Z. A family that fits moments asks the dimension nothing, so
those two records are one measurement of one column written twice, and a
forger who moves one has to move both.

That is a claim about three of the five families and not about all of them.
The two left out place knots, and a knot family honestly records different
numbers for one column at two widths -- so the table below says which is
which, and this file holds it to the contract's own list.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.rules import _CONSTANTS_FIXED_BY_THE_COLUMN

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))

#: The families whose constants are knots: more of them at a wider design, so
#: one column fitted at two widths gives two records and neither is wrong.
_CONSTANTS_FIXED_BY_THE_WIDTH = frozenset({"piecewise_linear", "cubic_spline"})

#: Where in a step's inputs the four designs sit, by the name the record uses.
_DESIGNS = ("w_basis", "z_basis",
            "treatment_bridge.span_basis", "treatment_bridge.moment_basis")


def _channels(result):
    """Every (step index, channel) this answer records, untagged at the top."""
    for index, step in enumerate((result.get("derivation") or {})
                                 .get("steps") or []):
        channel = (step.get("inputs") or {}).get("measurement_channel")
        if isinstance(channel, dict) and isinstance(channel.get("items"), dict):
            yield index, channel["items"]


def _design(channel, label):
    """One design out of a channel, still in the record's own encoding."""
    if label.startswith("treatment_bridge."):
        bridge = channel.get("treatment_bridge")
        if not isinstance(bridge, dict):
            return None
        node = bridge.get("items", {}).get(label.split(".", 1)[1])
    else:
        node = channel.get(label)
    return node.get("items") if isinstance(node, dict) else None


def _factors(design):
    """Every (column, factor, its untagged fields) of one design."""
    for ci, column in enumerate(design or ()):
        for fi, factor in enumerate(column.get("items") or ()):
            fields = factor.get("items")
            if isinstance(fields, dict):
                yield ci, fi, fields


def _constants(fields):
    node = fields.get("constants")
    return tuple(node.get("items") or ()) if isinstance(node, dict) else ()


def _fitted_twice(result):
    """(variable, family) pairs this answer standardised in two designs."""
    seen: dict = {}
    twice = set()
    for _, channel in _channels(result):
        for label in _DESIGNS:
            for _, _, fields in _factors(_design(channel, label)):
                key = (fields.get("variable"), str(fields.get("family") or ""))
                if key in seen and seen[key] != label:
                    twice.add(key)
                seen.setdefault(key, label)
    return twice


TWICE = sorted(name for name, pair in SHAPES.items()
               if _fitted_twice(pair["result"]))
CARRIES = sorted(name for name, pair in SHAPES.items()
                 if any(_design(c, label)
                        for _, c in _channels(pair["result"])
                        for label in _DESIGNS))
ONCE = [name for name in CARRIES if name not in set(TWICE)]

TWICE_ROSTER = 5
CARRIES_ROSTER = 6


def _first_factor(result, label):
    """The factor a bend of this design's constants lands on.

    The declaration asks one leaf per shape, and the shape it walks to is
    the first factor of the first column. Whether that leaf is held is a
    question about THAT factor's column, not about the design's.
    """
    for _, channel in _channels(result):
        design = _design(channel, label)
        for ci, fi, fields in _factors(design):
            if (ci, fi) == (0, 0):
                return fields
    return None


def test_the_rosters_are_the_size_this_file_was_written_against():
    assert len(TWICE) == TWICE_ROSTER, TWICE
    assert len(CARRIES) == CARRIES_ROSTER, CARRIES


def test_a_program_has_no_field_for_the_numbers_a_family_fits():
    """Why the direction that WAS read could never have held these.

    A sieve term is declared as a variable, a family and a width. The
    constants are read off the data, and the program's contract has no
    field for them at all -- so "the query declares no basis" was never the
    accident it looked like, and the check that compares a design to the
    declaration is not a weaker version of this one. It is about something
    else.
    """
    ast = (pathlib.Path(__file__).parent.parent / "themis" / "schemas"
           / "kernel_ast.schema.json").read_text(encoding="utf-8")
    assert "constants" not in ast
    assert "sieveTerms" in ast


def test_the_table_names_every_family_the_contract_declares():
    """A family split between neither column reaches the rule at all."""
    schema = json.loads(
        (pathlib.Path(__file__).parent.parent / "themis" / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    # The families are an enum on the term record a sieve is declared as.
    declared = None
    for node in _walk(schema):
        if (isinstance(node, dict) and isinstance(node.get("enum"), list)
                and "polynomial" in node["enum"]):
            declared = set(node["enum"])
            break
    assert declared is not None, "the contract stopped declaring the families"
    assert (_CONSTANTS_FIXED_BY_THE_COLUMN | _CONSTANTS_FIXED_BY_THE_WIDTH
            == declared), declared ^ (_CONSTANTS_FIXED_BY_THE_COLUMN
                                      | _CONSTANTS_FIXED_BY_THE_WIDTH)
    assert not (_CONSTANTS_FIXED_BY_THE_COLUMN & _CONSTANTS_FIXED_BY_THE_WIDTH)


def _walk(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


# ------------------------------------------------- the two records must agree


@pytest.mark.parametrize("shape", TWICE)
def test_a_column_fitted_for_two_designs_is_fitted_once(shape):
    """Move one design's constant and the other design is still the witness."""
    pair = SHAPES[shape]
    twice = _fitted_twice(pair["result"])
    moved = 0
    for label in _DESIGNS:
        result = copy.deepcopy(pair["result"])
        for _, channel in _channels(result):
            design = _design(channel, label)
            for ci, fi, fields in _factors(design):
                key = (fields.get("variable"), str(fields.get("family") or ""))
                if key not in twice:
                    continue
                fields["constants"]["items"][0] += 0.25
                moved += 1
                with pytest.raises(VerificationError, match="standardised as"):
                    themis.verify(pair["program"], result)
                return
    assert moved, shape


@pytest.mark.parametrize("shape", TWICE)
def test_the_scale_is_held_as_well_as_the_centre(shape):
    """Both constants, because a forged spread is a forged basis just as much."""
    pair = SHAPES[shape]
    twice = _fitted_twice(pair["result"])
    result = copy.deepcopy(pair["result"])
    for _, channel in _channels(result):
        for label in _DESIGNS:
            for _, _, fields in _factors(_design(channel, label)):
                key = (fields.get("variable"), str(fields.get("family") or ""))
                if key not in twice or len(_constants(fields)) < 2:
                    continue
                fields["constants"]["items"][1] *= 2.0
                with pytest.raises(VerificationError, match="standardised as"):
                    themis.verify(pair["program"], result)
                return
    pytest.fail(f"{shape}: no twice-fitted factor with two constants")


@pytest.mark.parametrize("shape", TWICE)
def test_the_two_designs_agree_on_the_honest_answer(shape):
    """The premise, stated rather than assumed: they do agree today."""
    pair = SHAPES[shape]
    twice = _fitted_twice(pair["result"])
    recorded: dict = {}
    for _, channel in _channels(pair["result"]):
        for label in _DESIGNS:
            for _, _, fields in _factors(_design(channel, label)):
                key = (fields.get("variable"), str(fields.get("family") or ""))
                if key in twice:
                    recorded.setdefault(key, set()).add(_constants(fields))
    assert recorded, shape
    for key, seen in recorded.items():
        assert len(seen) == 1, (shape, key, seen)


def test_every_regime_is_read_the_same_way():
    """The check sits above the split, not on one side of it.

    Three rules read a proximal channel -- the matrix plug-in, the two
    bridge regimes behind one entry point, and the null test -- and the
    answer to "which designs does this record hold" is the same one for all
    of them. A check on one side of a regime split audits the regime rather
    than the record, which is how a sibling thirty lines down came to read a
    different set of fields than its neighbour.
    """
    blob = (pathlib.Path(__file__).parent.parent / "themis" / "verifier"
            / "rules.py").read_text(encoding="utf-8")
    assert blob.count("_one_column_one_standardisation(") == 4, blob.count(
        "_one_column_one_standardisation(")


# --------------------------------------------------------- the declared silence


SURVIVORS = 6


def test_every_constant_still_declared_is_a_column_fitted_once():
    """The other half, as a property rather than a list.

    A leaf survives exactly where the factor the declaration walks to --
    the first of the first column -- expands a column no other design
    expanded in the same family. There is then no second writing, and
    recomputing it needs the rows a record of moments exists to replace.
    What would hold it is a consumer, and the envelope has none yet.
    """
    survivors = 0
    for shape, leaves in UNWITNESSED.items():
        result = SHAPES[shape]["result"]
        twice = _fitted_twice(result)
        for leaf in leaves:
            if "_basis" not in leaf or "constants" not in leaf:
                continue
            survivors += 1
            label = next(d for d in _DESIGNS
                         if leaf.endswith(f"{d.split('.')[-1]}.items.[].items."
                                          f"[].items.constants.items.[]"))
            fields = _first_factor(result, label)
            assert fields is not None, (shape, leaf)
            key = (fields.get("variable"), str(fields.get("family") or ""))
            assert key not in twice, (shape, leaf, key)
    assert survivors == SURVIVORS, survivors


def test_a_run_with_no_second_design_is_the_shape_that_leaves_them():
    """And that shape is what the survivors have in common, stated once."""
    assert ONCE, "every answer now carries a second design; re-read this file"
    for shape in ONCE:
        for _, channel in _channels(SHAPES[shape]["result"]):
            bridge = channel.get("treatment_bridge")
            assert bridge is None or not isinstance(bridge.get("items"), dict), (
                f"{shape} has a treatment bridge after all")


# ----------------------------------------------------------- nothing else moved


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_is_refused(shape):
    themis.verify_answer_claims(
        SHAPES[shape]["program"], SHAPES[shape]["result"])
