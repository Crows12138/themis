"""A region's premises are declarations too.

The Anderson-Rubin estimator answers with a set of values rather than a
point, so it reports itself — its method and the premises its set rests on —
in its own block beside the answer instead of in ``numeric_estimate``. The
producer folds both places into the ledger. The audit that holds the ledger
to what was declared read the estimate alone, and returned before asking
anything when that read came back empty.

Measured on the two corpus answers where the region is the only estimator:
10 deletions of a named line, 8 accepted by every door — the exclusion
restriction, instrument independence, a constant effect, and the
homoskedasticity the region's critical value assumes. The two refused were
the linearity line, which the mechanism block holds. And a premise copied in
from AIPW, which these answers never made, was accepted too.

The same module already said where a run reports itself, for the check on a
mechanism: the estimate, else the region. Declarations are read from there
now, whole, and the check asks both of its questions of every ledger. Once
both places are read, no corpus ledger carries a line attributed to an
estimator under an id nobody declared, and 14 of them declare nothing at all.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier.assumption_ledger_rules import _declaration_channels
from themis.verifier.errors import VerificationError

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures" /
                     "answer_shapes.json").read_text(encoding="utf-8"))

ATTRIBUTED = ("inherent", "caller_asserted", "caller_chose")
_RANK = {"invalidating": 0, "distorting": 1, "confidence_only": 2}


def _ledger(result):
    return (((result.get("extensions") or {})
             .get("assumption_ledger") or {}).get("assumptions") or [])


def _region(result):
    return (result.get("extensions") or {}).get("anderson_rubin_region")


REGION = sorted(name for name, pair in SHAPES.items()
                if isinstance(_region(pair["result"]), dict))

#: A ledger whose declarations, read in full, are none.
DECLARES_NOTHING = next(
    name for name in sorted(SHAPES)
    if _ledger(SHAPES[name]["result"])
    and not _declaration_channels(SHAPES[name]["result"]))

DROPS = [pytest.param(name, ident, id=f"{name}-{ident[:24]}")
         for name in REGION
         for ident in _region(SHAPES[name]["result"])["assumptions"]]


def _pair(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


def _a_premise_made_elsewhere(layer, target):
    """A real named line, of this layer, that ``target`` does not carry —
    without the verdict its own run gave it, which would be a claim about a
    check this answer never made and is refused for that first."""
    carried = {e.get("id") for e in _ledger(SHAPES[target]["result"])}
    for name in sorted(SHAPES):
        for entry in _ledger(SHAPES[name]["result"]):
            if (entry.get("id") and entry["id"] not in carried
                    and entry.get("layer") == layer
                    and entry.get("provenance") == "inherent"):
                line = copy.deepcopy(entry)
                line.pop("checked", None)
                return line
    raise AssertionError(f"no {layer} premise to copy onto {target}")


def _with(result, line):
    lines = _ledger(result)
    lines.insert(sum(1 for e in lines
                     if _RANK[e["severity"]] <= _RANK[line["severity"]]), line)
    return result


# ------------------------------------------------- the fact this rests on


def test_every_line_attributed_to_an_estimator_names_a_declared_id():
    """Stated as the measurement the change is built on."""
    ledgers = empty = undeclared = 0
    for pair in SHAPES.values():
        result = pair["result"]
        if not _ledger(result):
            continue
        ledgers += 1
        declared = set(_declaration_channels(result))
        empty += not declared
        undeclared += sum(
            1 for e in _ledger(result)
            if e.get("id") and e.get("provenance") in ATTRIBUTED
            and e["id"] not in declared)
    assert (ledgers, empty, undeclared) == (107, 14, 0), (
        ledgers, empty, undeclared)


def test_a_region_s_premises_are_read_as_declared():
    assert len(REGION) == 2, REGION
    for name in REGION:
        result = SHAPES[name]["result"]
        assert set(_region(result)["assumptions"]) <= set(
            _declaration_channels(result)), name


def test_the_forgeries_start_from_answers_their_door_reads():
    for name in [*REGION, DECLARES_NOTHING]:
        program, result = _pair(name)
        the_door_for(result)(program, result)


# ---------------------------------------------------- the two questions


@pytest.mark.parametrize(("name", "ident"), DROPS)
def test_a_premise_the_region_declared_may_not_be_dropped(name, ident):
    program, result = _pair(name)
    lines = _ledger(result)
    lines[:] = [e for e in lines if e.get("id") != ident]
    with pytest.raises(VerificationError, match="drops estimator-declared"):
        the_door_for(result)(program, result)


@pytest.mark.parametrize("layer", ["identification", "confidence"])
@pytest.mark.parametrize("name", REGION)
def test_a_premise_the_region_never_made_may_not_be_added(name, layer):
    program, result = _pair(name)
    _with(result, _a_premise_made_elsewhere(layer, name))
    with pytest.raises(VerificationError, match="never declared"):
        the_door_for(result)(program, result)


def test_an_answer_that_declares_nothing_may_not_be_given_a_premise():
    """The early return, gone: this is the question it used to skip."""
    program, result = _pair(DECLARES_NOTHING)
    _with(result, _a_premise_made_elsewhere("identification",
                                            DECLARES_NOTHING))
    with pytest.raises(VerificationError, match="never declared"):
        the_door_for(result)(program, result)
