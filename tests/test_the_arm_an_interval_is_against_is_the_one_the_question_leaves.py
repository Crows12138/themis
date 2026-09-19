"""Which arm an interval is reported against is a fact about the question.

A bounds row may carry a ``contrast``: the interval for the difference
between the arm the question asked about and the one it did not. Four of
its five fields are quantities, and :mod:`themis.verifier.bounds_rules`
re-derives every one of them from the recorded counts. The fifth,
``reference_value``, is not a quantity. It is a reference -- it says WHO
the four numbers are about -- and re-deriving a number says nothing about
who it is reported against.

So it was asked in one method's branch and not the other two. Manski-Tamer
compared it against the levels the row itself recorded; Manski natural,
which is thirty-one of the thirty-three stored contrasts, asked nothing;
Balke-Pearl computes its contrast against an arm index and never looks at
the name the row prints beside it. The stored answers said the same thing:
every contrast in the corpus reports the arm it is against, and on every
one of them the arm could be changed to the arm the question DID ask about
and every public door said yes.

Asked once here, before the dispatch, and asked of the question. What the
treatment could have been has two writings -- the levels the program
declares, and, where it declares none, the type of the value asked for,
since a boolean has exactly two values -- and the arm the question leaves
is whichever one of them is not the arm it took.

WHAT IS NOT CLAIMED HERE, and is measured rather than assumed away. Where
neither writing leaves exactly one other value this says nothing: a
three-arm treatment has no single baseline to be against, and refusing a
contrast on one is a claim about the ROW's own arm count that both
branches that made it still make, from their own recorded levels. Moving
that one too would be a second copy of it, not a lifting.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier import bounds_account_rules as account
from themis.verifier import bounds_rules
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

LEAF = "bounds_results.[].contrast.reference_value"


def _the_stored_contrasts():
    """Every contrast in the corpus, by what says which arms there are.

    Split at the source rather than counted in one lump, because the two
    sources are the two halves of the rule and a roster that hid the
    split would pass while one half was never exercised.
    """
    from_program: list = []
    from_type: list = []
    by_method: dict = {}
    for name in sorted(SHAPES):
        rows = SHAPES[name]["result"].get("bounds_results") or ()
        spots = [i for i, row in enumerate(rows)
                 if isinstance(row.get("contrast"), dict)
                 and "reference_value" in row["contrast"]]
        if not spots:
            continue
        ast, _program, statement, _ctx = _premises_of(
            SHAPES[name]["program"], SHAPES[name]["result"])
        intervention = statement.query.intervention
        _names, declared = account._declared(ast)
        levels = declared.get(intervention.atom.predicate)
        side = from_program if isinstance(levels, list) and levels else from_type
        for i in spots:
            side.append((name, i, intervention.value))
            method = rows[i]["method"]
            by_method[method] = by_method.get(method, 0) + 1
    return from_program, from_type, by_method


FROM_PROGRAM, FROM_TYPE, BY_METHOD = _the_stored_contrasts()
SPOTS = FROM_PROGRAM + FROM_TYPE
CARRYING = sorted({name for name, _i, _v in SPOTS})


def _program(levels=(True, False)):
    statements = [{"kind": "variable", "predicate": "y"},
                  {"kind": "variable", "predicate": "x"}]
    if levels is not None:
        statements[1]["domain"] = list(levels)
    return {"statements": statements}


def _query(value=True):
    return {"intervention": {"atom": {"predicate": "x"}, "value": value},
            "target": {"atom": {"predicate": "y"}}}


def _row(reference, method="balke_pearl"):
    return {"method": method,
            "contrast": {"kind": "ace", "reference_value": reference,
                         "lower_value": -0.2, "upper_value": 0.6,
                         "tightness": "sharp"}}


def _ask(row, *, levels=(True, False), value=True):
    account.verify_bounds_account(row, program=_program(levels),
                                  query_dict=_query(value))


# ----------------------------------------------------- the stored corpus

def test_the_roster_is_the_size_it_was_measured_at():
    assert (len(CARRYING), len(SPOTS)) == (31, 33)
    assert (len(FROM_PROGRAM), len(FROM_TYPE)) == (28, 5)
    assert BY_METHOD == {"manski_natural": 31,
                         "manski_tamer_monotonicity": 2}


def test_every_stored_contrast_is_reported_against_the_arm_not_asked():
    """The thing being held, stated over the corpus rather than assumed:
    an honest row's reference arm is the one the question left."""
    for name, i, asked in SPOTS:
        row = SHAPES[name]["result"]["bounds_results"][i]
        assert row["contrast"]["reference_value"] != asked, (name, i)


@pytest.mark.parametrize("name", CARRYING)
def test_an_answer_that_reports_a_contrast_is_still_accepted(name):
    verify_honestly(SHAPES[name]["program"],
                    copy.deepcopy(SHAPES[name]["result"]))


@pytest.mark.parametrize("name,index,asked", SPOTS,
                         ids=[f"{n}:{i}" for n, i, _v in SPOTS])
def test_a_contrast_against_the_arm_the_question_asked_is_refused(
        name, index, asked):
    """The forgery the declaration was about: say the interval is against
    the arm that WAS intervened at, which makes the reported difference a
    difference from itself."""
    program = SHAPES[name]["program"]
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["bounds_results"][index]["contrast"]["reference_value"] = asked
    with pytest.raises(Exception):
        the_door_for(bad)(program, bad)


def test_the_refusal_says_which_arm_the_question_leaves():
    name, index, asked = SPOTS[0]
    program = SHAPES[name]["program"]
    bad = copy.deepcopy(SHAPES[name]["result"])
    bad["bounds_results"][index]["contrast"]["reference_value"] = asked
    with pytest.raises(Exception, match="the only other arm the treatment"):
        the_door_for(bad)(program, bad)


# ------------------------------------------------- asked of every method

def test_an_honest_contrast_passes_on_a_method_with_no_branch_of_its_own():
    _ask(_row(False))


def test_a_wrong_arm_is_refused_on_a_method_with_no_branch_of_its_own():
    """Why it lives before the dispatch. Balke-Pearl re-derives its
    contrast's endpoints against an arm INDEX and never reads the name
    printed beside them, so this row met nothing at all until now."""
    with pytest.raises(VerificationError, match="the only other arm"):
        _ask(_row(True))


def test_the_refusal_quotes_both_arms():
    with pytest.raises(VerificationError, match="intervenes at True"):
        _ask(_row(True))


def test_a_row_with_no_contrast_is_not_asked():
    _ask({"method": "manski_natural"})


def test_a_contrast_that_prints_no_arm_is_not_asked_for_one():
    """Requiring the field is a claim about the SHAPE of the record, which
    the schema makes and this does not."""
    _ask({"method": "balke_pearl",
          "contrast": {"kind": "ace", "lower_value": 0.0,
                       "upper_value": 1.0, "tightness": "sharp"}})


# --------------------------------------------- where the arms are written

def test_the_program_says_which_arms_there_are():
    assert account._the_arm_a_contrast_should_be_against(
        "x", {"x": ["lo", "hi"]}, "lo", "hi") == "hi"


def test_a_boolean_question_needs_no_declared_levels():
    """The second writing: a boolean has two values and that is a fact
    about the type, not about this program's data."""
    assert account._the_arm_a_contrast_should_be_against(
        "x", {}, True, False) is False
    assert account._the_arm_a_contrast_should_be_against(
        "x", {}, False, True) is True


def test_the_program_is_read_before_the_type():
    """Where both say something they agree here, and the order still
    matters: the program is the document that could disagree."""
    assert account._the_arm_a_contrast_should_be_against(
        "x", {"x": [True, False]}, True, False) is False


def test_a_three_arm_treatment_names_no_single_baseline():
    assert account._the_arm_a_contrast_should_be_against(
        "x", {"x": [0, 1, 2]}, 0, 1) is None


def test_a_question_at_a_value_the_program_does_not_declare_names_no_arm():
    assert account._the_arm_a_contrast_should_be_against(
        "x", {"x": ["lo", "hi"]}, "mid", "lo") is None


def test_a_non_boolean_question_with_no_declared_levels_names_no_arm():
    assert account._the_arm_a_contrast_should_be_against(
        "x", {}, "lo", "hi") is None


def test_a_boolean_arm_is_not_the_number_beside_it():
    """``True == 1`` in Python and a boolean domain is not a numeric one;
    this module had already decided that, and the arm is compared the same
    way rather than a second way."""
    assert account._the_arm_a_contrast_should_be_against(
        "x", {"x": [0, 1]}, True, False) is None


def test_an_arm_the_program_does_not_name_is_not_compared():
    """The silence this rule keeps, and the run that measured it. A
    treatment column of 0 and 1 is declared ``[0, 1]``, the question
    intervenes at ``1``, and the envelope reports the reference arm as
    ``False`` because the estimator works on a boolean column. That is
    an honest answer this repository produces today, and it is
    indistinguishable here from a forged arm, so nothing is asked of
    either. An envelope spelling an arm in words its own program does
    not use is a finding of its own."""
    _ask(_row(False), levels=(0, 1), value=1)
    _ask(_row(True), levels=(0, 1), value=1)
    _ask(_row(0), levels=(True, False))


# ------------------------------------------ what is NOT claimed here

def test_nothing_here_refuses_a_baseline_on_a_three_arm_treatment():
    """Stated, not overlooked. With no single other arm there is no
    baseline a difference could be against, and both branches that make
    that claim still make it from their own recorded arm counts. Making
    it here as well would be a second copy of it."""
    _ask(_row(1), levels=(0, 1, 2), value=0)


def test_nothing_here_holds_the_arm_when_the_question_is_not_about_one():
    _ask(_row("control"), levels=None, value="dose")


# ------------------------------------------------- one place, not three

def test_the_deepest_re_derivation_has_no_opinion_about_the_arm():
    """The structural half of the fix. ``bounds_rules`` re-runs the LP,
    re-derives every Manski expression and checks the instrumental
    inequalities -- and now says nothing at all about which arm a
    contrast is reported against, because that claim is asked of every
    method before it is reached."""
    source = pathlib.Path(bounds_rules.__file__).read_text(encoding="utf-8")
    assert "reference_value" not in source
