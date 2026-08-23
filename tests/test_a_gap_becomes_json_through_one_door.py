"""A gap entry had two authors, and only one of them knew how to spell absence.

#427. ``data_gap_report.gaps[i].required_data`` is declared ``type: object``
with no null arm — the unambiguous shape #371 settled on. Three hand-built
entries in the estimation layer wrote ``null`` into it anyway, and every
thin-overlap answer had been failing its own schema since:

    SyntacticError data_gap_report/gaps/4/required_data:
        None is not of type 'object'

The root cause is not three forgotten lines. A gap becomes JSON down two
roads. Gaps found BEFORE the run are ``DataGap`` dataclasses and go through
``data_gap_to_dict``, which OMITS the key when the field is ``None``. Gaps
found DURING estimation are filed into a report that is already serialised,
so seven sites hand-built the dict — copying the field list off the dataclass,
and three of them copying its ``None`` along. In the dataclass ``None`` means
"there is none"; in JSON there are two spellings of that and the schema names
only one.

So the second road goes through the first: the estimation layer builds a
``DataGap`` and the one translator turns it into JSON. Which also takes the
closed vocabularies with it — ``kind`` / ``severity`` / ``blocks`` were bare
strings nobody checked until schema validation, which is exactly the check
that was not running.

The reason this survived is the one #371 named as its own honest limit: the
rule is pinned on the DECLARATION, and ``run()`` does not validate its own
output. The contract was right the whole time; nothing asked the traffic.
"""
from __future__ import annotations

import ast
import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _file_gaps
from themis.gaps import Route, occasion, route
from themis.input.syntactic_validator import SyntacticError, validate_result
from themis.output import envelope_glossary
from themis.output.result_orchestrator import data_gap_to_dict
from themis.types import (
    DataGap,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapSeverity,
)
from themis import gaps as _gaps

_OVERLAP = GapKind.PROPENSITY_OVERLAP_VIOLATION.value


def _gap(**kw) -> DataGap:
    fields = {
        "kind": GapKind.PROPENSITY_OVERLAP_VIOLATION,
        "severity": GapSeverity.INFORMATIONAL,
        "blocks": GapBlocks.INTERPRETATION,
        "describes": (_gaps.sentence(
            _gaps.Sentence.THE_FITTED_PROPENSITY_LEAVES_PART_OF_THE_SAMPLE_UNSUPPORTED,
            treatment="x", adjustment="z", outside=3, total=40,
            lower=0.05, upper=0.95, share="8%", low="0.01", high="0.99"),),
        "provenance": (GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK,
                                        ref_id="overlap:x"),),
    }
    fields.update(kw)
    return DataGap(**fields)      # type: ignore[arg-type]


# --- the failure, as it was measured ------------------------------------------


@pytest.fixture(scope="module")
def thin() -> pd.DataFrame:
    """Propensities at both extremes, which is what makes the overlap gap
    fire. Every answer on data this thin carried the malformed entry."""
    rng = np.random.default_rng(4)
    n = 4000
    z = rng.normal(size=n)
    x = rng.random(n) < 1 / (1 + np.exp(-3.2 * z))
    y = rng.random(n) < np.clip(0.2 + 0.3 * x + 0.25 * (z > 0), 0, 1)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


@pytest.fixture(scope="module")
def program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "scale": "continuous"},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }


@pytest.mark.parametrize("estimator", ["gformula", "ipw", "aipw", "tmle"])
def test_an_answer_on_thin_overlap_conforms_to_its_own_schema(
        program, thin, estimator):
    """The whole defect, end to end. ``run()`` does not validate its own
    output, so this asks the question nothing in the pipeline was asking."""
    result = themis.estimate(program, thin, ci_bootstrap=0,
                             ate_estimator=estimator)["results"][0]
    kinds = [g.get("kind")
             for g in (result.get("data_gap_report") or {}).get("gaps") or []]
    # Not vacuous: the entry that used to be malformed is really in here.
    assert _OVERLAP in kinds, kinds
    validate_result(result)


def test_the_entry_as_it_was_written_is_still_refused(program, thin):
    """The counterexample, transcribed rather than described.

    ``required_data: None`` is what the three hand-built sites wrote, and the
    schema rejecting it is not a new rule — it is the rule that was there the
    whole time with nothing asking the traffic about it.
    """
    out = themis.estimate(program, thin, ci_bootstrap=0, ate_estimator="ipw")
    forged = copy.deepcopy(out["results"][0])
    for gap in forged["data_gap_report"]["gaps"]:
        if gap.get("kind") == _OVERLAP:
            gap["required_data"] = None
    with pytest.raises(SyntacticError, match="required_data"):
        validate_result(forged)


# --- what the one door does with "there is none" ------------------------------


def test_the_translator_spells_absence_by_leaving_the_key_out():
    """Four optional fields, one spelling. ``None`` on the dataclass says the
    concept does not apply; JSON has two ways to write that and the schema
    names one, so the choice is made here rather than at each writer."""
    entry = data_gap_to_dict(_gap())
    for key in ("required_data", "signature", "said", "words",
                "alternative_paths"):
        assert key not in entry, entry
    assert set(entry) == {"kind", "severity", "describes", "blocks",
                          "provenance"}


def test_an_optional_field_that_is_present_is_written():
    """The other half: absent is not the only thing the door can say."""
    entry = data_gap_to_dict(_gap(
        signature="scale_mismatch",
        **occasion(collider="W", scale=envelope_glossary.Scale.BINARY),
        alternative_paths=(route(Route.LOOSEN_THE_ADJUSTMENT_SET),),
    ))
    assert entry["signature"] == "scale_mismatch"
    # The occasion's two halves, each written only where it has something:
    # a value leaves rendered and a word leaves as its set and its token.
    assert entry["said"] == {"collider": "W"}
    assert entry["words"] == {
        "scale": {"vocabulary": "measurement_scale", "token": "binary"}}
    # The route by name, with no ``said`` or ``words`` key: this occasion
    # has no facts to put in the sentence, and "nothing here" has the one
    # spelling the door decides — the same rule the test above pins.
    assert entry["alternative_paths"] == [
        {"route": "loosen_the_adjustment_set"}]


def test_a_gap_outside_the_vocabulary_cannot_be_written_at_all():
    """The vocabularies came along with the dataclass. A bare string reaches
    the door and the door cannot serialise it — which is where a typo used to
    travel all the way to the envelope and wait for a schema check nobody
    ran."""
    with pytest.raises(AttributeError):
        data_gap_to_dict(_gap(kind="propensity_overlap_violaton"))
    with pytest.raises(ValueError, match="not a valid GapBlocks"):
        GapBlocks("interpretaton")


def test_filing_nothing_does_not_invent_a_report():
    """A report that exists and is empty says a gap search ran and found
    something. Five call sites each had to remember this; one has to now."""
    result: dict = {}
    _file_gaps(result, [])
    assert result == {}


def test_a_second_gap_joins_the_report_the_first_one_made():
    result: dict = {}
    _file_gaps(result, [_gap()])
    _file_gaps(result, [_gap(describes=(
        _gaps.sentence(_gaps.Sentence.TIAN_FOUND_A_HEDGE),))])
    report = result["data_gap_report"]
    assert [g["describes"][0]["sentence"] for g in report["gaps"]] == [
        "the_fitted_propensity_leaves_part_of_the_sample_unsupported",
        "tian_found_a_hedge",
    ]


# --- and nothing hand-builds one any more -------------------------------------


_THEMIS = pathlib.Path(themis.__file__).parent

#: A dict literal carrying all of these is a gap entry, whatever it is called.
_GAP_SHAPE = {"kind", "severity", "describes"}


def _hand_built() -> list[tuple[str, int, str]]:
    """Every dict literal in the package shaped like a gap entry, as
    ``(module, line, enclosing function)``."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(_THEMIS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        enclosing: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    enclosing.setdefault(line, node.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if _GAP_SHAPE <= keys and ("blocks" in keys or "provenance" in keys):
                found.append((path.name, node.lineno,
                              enclosing.get(node.lineno, "<module>")))
    return found


def test_the_only_place_that_builds_a_gap_entry_is_the_translator():
    """The structural half, and the reason this cannot come back.

    A dict literal CAN say ``required_data: null``; a ``DataGap`` cannot. So
    the repair is not that the three sites stopped writing it — it is that
    nowhere outside this one function is a gap entry assembled at all, and the
    denominator is every dict literal in the package rather than the sites
    somebody happened to look at.
    """
    assert [(mod, fn) for mod, _line, fn in _hand_built()] == [
        ("result_orchestrator.py", "data_gap_to_dict"),
    ]


def test_the_sweep_would_see_one_if_there_were_one():
    """The criterion discriminates: fed the entry as it used to be written,
    the same walk finds it."""
    tree = ast.parse(
        'gap_entry = {"kind": "weak_iv_instrument", "severity": "informational",\n'
        '             "blocks": "interpretation", "describes": [],\n'
        '             "required_data": None}\n'
    )
    hits = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]
    keys = {k.value for k in hits[0].keys if isinstance(k, ast.Constant)}
    assert _GAP_SHAPE <= keys and "blocks" in keys
