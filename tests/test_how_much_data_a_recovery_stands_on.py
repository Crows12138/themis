"""The counts beside a recovered ATE answer to the tables it was built from.

``verify_missing_data_numeric`` re-derived two g-formula sums and stopped.
Its sufficient statistics are load-bearing -- the point is rebuilt from
them and the marginal counts are already held to summing to their own
total -- so every count printed beside the point had a witness sitting
next to it that nothing was reading. Fourteen declared leaves.

Two of them are what a reader acts on hardest. ``n_total`` against
``n_complete_case`` is how much of the sample went missing, and that is
the whole reason a recovery was run rather than a listwise deletion: on
the stored answers it is 6000 against 3636, two rows in five with no
outcome. Free those two numbers and a recovery standing on three fifths
of its rows reads exactly like one standing on all of them.

Each count answers to the factor it was computed on, which is what the
recoverability argument says: the conditional table is estimated where the
outcome was observed and the marginal table on every row, so the two
differ on an honest block and differ by exactly what went missing.

The three sets the rule declares are a PARTITION of the contract, not a
selection from it, and the last of them is checked rather than asserted:
this file holds that nothing in it sits in the declared remainder, so
"held elsewhere" is a fact about this build instead of a sentence about
somebody else's code.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.missing_numeric_rules import (
    _RECOVERED_ATE_ELSEWHERE,
    _RECOVERED_ATE_HELD,
    _RECOVERED_ATE_READ,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REPO = FIXTURES.parent.parent
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))
BLOCK_SCHEMA = (json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))
    ["properties"]["numeric_estimate"]["properties"]["recovered_ate"])

CARRYING = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair["result"].get("numeric_estimate") or {})
                  .get("recovered_ate"), dict))

ROSTER = 2


def test_the_roster_is_the_size_this_file_was_written_against():
    """An empty parametrisation is a green test that asks nothing."""
    assert len(CARRYING) == ROSTER, CARRYING


def _claims(shape, result):
    """The door these answers open.

    They carry no derivation, so ``themis.verify`` refuses them for what
    they are rather than for what this file forged -- which would make
    every test below pass without asking anything.
    """
    themis.verify_answer_claims(SHAPES[shape]["program"], result)


# ------------------------------------------------- the partition, structural


def test_the_three_sets_partition_the_contract():
    declared = set(BLOCK_SCHEMA["properties"])
    named = _RECOVERED_ATE_READ | _RECOVERED_ATE_HELD | _RECOVERED_ATE_ELSEWHERE
    assert declared == named, declared ^ named
    assert not (_RECOVERED_ATE_READ & _RECOVERED_ATE_HELD)
    assert not (_RECOVERED_ATE_READ & _RECOVERED_ATE_ELSEWHERE)
    assert not (_RECOVERED_ATE_HELD & _RECOVERED_ATE_ELSEWHERE)


def test_what_is_said_to_be_held_elsewhere_is_held_somewhere():
    """The third set's justification, checked instead of asserted.

    A field parked there because nobody wanted to write a rule for it
    would show up in the declared remainder, and this is where that would
    be noticed.
    """
    open_here = {
        leaf.split("recovered_ate.")[-1].split(".")[0]
        for name in CARRYING for leaf in UNWITNESSED.get(name, ())
        if "recovered_ate." in leaf
    }
    assert not (open_here & _RECOVERED_ATE_ELSEWHERE), (
        open_here & _RECOVERED_ATE_ELSEWHERE)


def test_nothing_this_rule_holds_is_left_in_the_remainder():
    """The other half of the same claim."""
    open_here = {
        leaf.split("recovered_ate.")[-1].split(".")[0]
        for name in CARRYING for leaf in UNWITNESSED.get(name, ())
        if "recovered_ate." in leaf
    }
    assert not (open_here & _RECOVERED_ATE_HELD), (
        open_here & _RECOVERED_ATE_HELD)


# --------------------------------------------------------------- the counts


@pytest.mark.parametrize("shape", CARRYING)
@pytest.mark.parametrize("field", [
    "n_total", "n_marginal_rows", "n_conditional_rows",
    "n_complete_case", "n_strata",
])
def test_a_count_is_rebuilt_from_the_table_it_counts(shape, field):
    result = copy.deepcopy(SHAPES[shape]["result"])
    ra = result["numeric_estimate"]["recovered_ate"]
    ra[field] = ra[field] + 7
    with pytest.raises(VerificationError, match=field):
        _claims(shape, result)


@pytest.mark.parametrize("shape", CARRYING)
def test_the_two_row_counts_are_not_one_number(shape):
    """The conditional table and the marginal table are different sizes on
    an honest block, and that difference IS the missing data.

    Setting one to the other is the forgery that hides the whole point of
    running a recovery, and it is not caught by any rule that reads only
    one of them.
    """
    ra = SHAPES[shape]["result"]["numeric_estimate"]["recovered_ate"]
    assert ra["n_conditional_rows"] < ra["n_marginal_rows"], shape
    result = copy.deepcopy(SHAPES[shape]["result"])
    forged = result["numeric_estimate"]["recovered_ate"]
    forged["n_conditional_rows"] = forged["n_marginal_rows"]
    with pytest.raises(VerificationError, match="n_conditional_rows"):
        _claims(shape, result)


def test_a_count_that_is_not_a_count_is_the_contract_s_to_refuse():
    """Measured while writing the rule, and left here as the reason it
    does not check the type twice.

    ``n_strata = True`` never reaches the rule: the schema declares these
    as integers and the syntactic validator refuses the answer first, with
    its own error. A second check inside the rule would be a rule that can
    never fire, which reads from outside exactly like a rule that found
    nothing wrong.
    """
    from themis.input.syntactic_validator import SyntacticError, validate_result

    shape = CARRYING[0]
    result = copy.deepcopy(SHAPES[shape]["result"])
    result["numeric_estimate"]["recovered_ate"]["n_strata"] = True
    with pytest.raises(SyntacticError, match="n_strata"):
        validate_result(result)


# ------------------------------------------------- the list written twice


@pytest.mark.parametrize("shape", CARRYING)
def test_the_covariate_list_is_one_list(shape):
    result = copy.deepcopy(SHAPES[shape]["result"])
    ra = result["numeric_estimate"]["recovered_ate"]
    ra["adjustment"] = ra["adjustment"] + ["a_name_neither_document_uses"]
    with pytest.raises(VerificationError, match="adjustment"):
        _claims(shape, result)


@pytest.mark.parametrize("shape", CARRYING)
def test_a_column_can_only_go_missing_from_the_table_it_is_in(shape):
    result = copy.deepcopy(SHAPES[shape]["result"])
    ra = result["numeric_estimate"]["recovered_ate"]
    ra["missing_columns"] = ["a_column_the_estimate_never_read"]
    with pytest.raises(VerificationError, match="did not read"):
        _claims(shape, result)


@pytest.mark.parametrize("shape", CARRYING)
def test_one_column_is_not_two_columns(shape):
    result = copy.deepcopy(SHAPES[shape]["result"])
    ra = result["numeric_estimate"]["recovered_ate"]
    ra["missing_columns"] = ra["missing_columns"] * 2
    with pytest.raises(VerificationError, match="listed twice"):
        _claims(shape, result)


# ------------------------------------------- what the silences have to stay


def test_a_block_with_no_naive_factor_is_not_asked_about_complete_cases():
    """The suite's hand-built blocks record no naive factor, and the count
    that belongs to it has nothing to answer to there.

    Asked as a fact about the rule rather than left to whichever fixture
    happens to exercise it: this is the ``present on one side`` shape the
    package holds everything else by.
    """
    from themis.verifier.missing_numeric_rules import (
        verify_missing_data_numeric,
    )

    strata = [{"z": [], "arm": 1, "n": 50, "y_sum": 30.0},
              {"z": [], "arm": 0, "n": 50, "y_sum": 20.0}]
    ne = {
        "method": "missing_data_recovery_gformula", "point": 0.2,
        "recovered_ate": {
            "point": 0.2, "naive_listwise_ate": None,
            "adjustment": [], "missing_columns": ["y"],
            "n_total": 100, "n_marginal_rows": 100,
            "n_conditional_rows": 100,
            "n_complete_case": 12345,   # answers to nothing recorded
            "n_strata": 1,
            "sufficient_statistics": {
                "adjustment_vars": [],
                "recovered": {"conditional_strata": strata,
                              "marginal_counts": [{"z": [], "count": 100}],
                              "marginal_total": 100},
                "naive": None,
            },
        },
    }
    verify_missing_data_numeric({"numeric_estimate": ne})

    ne["recovered_ate"]["n_total"] = 12345
    with pytest.raises(VerificationError, match="n_total"):
        verify_missing_data_numeric({"numeric_estimate": ne})


def test_a_block_without_data_columns_is_not_asked_which_went_missing():
    """The same shape one field along: the column list lives on the
    estimate, and a block handed to this rule without one is not a block
    naming a column that does not exist."""
    from themis.verifier.missing_numeric_rules import (
        verify_missing_data_numeric,
    )

    strata = [{"z": [], "arm": 1, "n": 50, "y_sum": 30.0},
              {"z": [], "arm": 0, "n": 50, "y_sum": 20.0}]
    ne = {
        "method": "missing_data_recovery_gformula", "point": 0.2,
        "recovered_ate": {
            "point": 0.2, "naive_listwise_ate": None,
            "adjustment": [], "missing_columns": ["no_such_column"],
            "n_total": 100, "n_marginal_rows": 100,
            "n_conditional_rows": 100, "n_complete_case": 100,
            "n_strata": 1,
            "sufficient_statistics": {
                "adjustment_vars": [],
                "recovered": {"conditional_strata": strata,
                              "marginal_counts": [{"z": [], "count": 100}],
                              "marginal_total": 100},
                "naive": None,
            },
        },
    }
    verify_missing_data_numeric({"numeric_estimate": ne})

    ne["data_columns"] = ["x", "y"]
    with pytest.raises(VerificationError, match="did not read"):
        verify_missing_data_numeric({"numeric_estimate": ne})


# --------------------------------------------------------- nothing else moved


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_is_refused(shape):
    themis.verify_answer_claims(
        SHAPES[shape]["program"], SHAPES[shape]["result"])
