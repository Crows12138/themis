"""Two column lists on one envelope, and only one of them is the answer's.

``estimation_context`` fingerprints what ARRIVED — every predicate the
program declared, including the ones no query estimated. Each numeric
block fingerprints what its own estimator was HANDED. Both are now
spelled ``…data_columns``, both are true, and a reading of "which columns
does this answer stand on" that takes the first says yes for everything.

That is not a hypothetical: it is exactly the defect the scoped gap was
built to fix. A variable declared in the program, supplied out of its
declared range, and used by no query blocked the point estimate of every
query there was — because a reading that says yes for everything hands
every finding the strongest consequence there is.

So these pin the reading against the surface that now makes it easy to
get wrong. The producer declares the columns and then classifies each gap
against its own declaration; the verifier reads the declaration and
checks the classification. Before the declaration existed the two sides
each guessed, identically, and the rule could not fail — so the last two
tests here are failures that were previously unreachable.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _names_this_result_stands_on
from themis.output.analysis_report import build_analysis_report
from themis.verifier import verify_type_reconciliation
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program():
    """Back-door z→x, z→y, x→y, plus ``w``: declared, wired to nothing."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "w", "scale": "discrete",
             "domain": [0, 1]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _frame(n=600, seed=3):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({
        "x": x.astype(bool), "y": y.astype(bool), "z": z.astype(bool),
        # Declared over {0, 1}, supplied with a 2. The declaration is wrong
        # and nothing in the program estimates this column.
        "w": rng.integers(0, 3, n),
    })


def _estimated():
    """A real numeric answer, so the answer-level denominator exists."""
    env = themis.estimate(_program(), _frame(), ci_bootstrap=0)
    return env["results"][0]


def _mismatch_gaps(result):
    gaps = (result.get("data_gap_report") or {}).get("gaps") or []
    return [g for g in gaps if g.get("kind") == "declared_type_data_mismatch"]


# ------------------------------------------------ the two lists differ

def test_the_run_and_the_answer_fingerprint_different_column_sets():
    """If these were the same list there would be nothing here to confuse."""
    result = _estimated()
    arrived = set(result["estimation_context"]["data_columns"])
    used = set(result["numeric_estimate"]["data_columns"])
    assert "w" in arrived
    assert "w" not in used
    assert used == {"x", "y", "z"}


def test_the_answer_is_read_from_its_own_denominator():
    result = _estimated()
    assert _names_this_result_stands_on(result) == {"x", "y", "z"}


def test_what_arrived_cannot_make_a_column_stand():
    """The exclusion is load-bearing, not tidy: this list names everything."""
    result = _estimated()
    result["estimation_context"]["data_columns"].append("invented")
    assert "invented" not in _names_this_result_stands_on(result)


def test_a_name_the_document_merely_mentions_is_not_a_column_it_stands_on():
    """A stated denominator displaces the mention-everything fallback."""
    result = _estimated()
    method = result["numeric_estimate"]["method"]
    assert isinstance(method, str) and method
    assert method not in _names_this_result_stands_on(result)


# ------------------------------------------- and the consequence is scoped

def test_the_unestimated_column_costs_this_answer_nothing():
    gap = _mismatch_gaps(_estimated())[0]
    assert gap["signature"] == "domain_violated"
    assert gap["severity"] == "informational"
    assert gap["blocks"] == "interpretation"


def test_the_verifier_accepts_the_scoped_pair_on_the_data_path():
    verify_type_reconciliation(_estimated())


# --------------- failures the rule could not reach before the declaration

def test_a_classification_that_contradicts_the_declaration_is_refused():
    """The producer says it stands on {x, y, z} and then bills for ``w``."""
    tampered = copy.deepcopy(_estimated())
    gap = _mismatch_gaps(tampered)[0]
    gap["severity"] = "important"
    gap["blocks"] = "point_estimate"
    with pytest.raises(VerificationError, match="does not stand on"):
        verify_type_reconciliation(tampered)


def test_a_declaration_that_contradicts_the_classification_is_refused():
    """The other direction: widen the denominator, leave the gap scoped."""
    tampered = copy.deepcopy(_estimated())
    tampered["numeric_estimate"]["data_columns"].append("w")
    with pytest.raises(VerificationError, match="stands on"):
        verify_type_reconciliation(tampered)


# ------------------------------------ and the reader sees what it covers

def _footer(result):
    report = build_analysis_report(result, program=_program())
    return next(
        line for line in report.splitlines() if line.startswith("*审计*")
    )


def test_the_fingerprint_the_reader_sees_says_what_it_is_of():
    """The footer is the digest's only human surface. Alone it is a hex
    string with nothing to compare against."""
    footer = _footer(_estimated())
    assert "data_hash=`" in footer
    assert "（覆盖 x、y、z）" in footer


def test_the_footer_pairs_the_digest_with_its_own_denominator():
    """Not the run's. Taking one from each container is the confusion the
    second list exists to prevent, and ``w`` is what tells them apart."""
    result = _estimated()
    assert "w" in result["estimation_context"]["data_columns"]
    assert "w" not in _footer(result)
