"""A bounds row's account of itself, which nothing had ever read.

``bounds_rules`` is one of the deepest re-derivations in the repository:
it re-runs the Balke-Pearl response-function LP, re-derives every Manski
expression, checks the instrumental inequalities, and refuses an interval
its own arithmetic does not yield. It verifies the ANSWER.

A reader does not receive the answer. They receive two lists: what would
narrow this interval (``data_required`` — "a joint distribution,
``P(y, x)``") and where the width came from (``notes`` — "the width is
the off-arm mass, ``P(x=false)``"). Measured before this file existed,
all 207 leaves the census asks about could be rewritten and the door said
yes. Rewrite one and a reader collects a distribution over the wrong
variable while every arithmetic check still passes.

No table is restated to fix it. A rendered quantity may use only names
the program declares and words already in the row's own re-derived
formulas; a count is the number of levels the program declares; and the
two quantities that a rule elsewhere has already CONSTRUCTED — the
off-arm mass, and the marginal a monotonicity assumption tightens to —
are passed in and compared whole rather than built a second time.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.bounds_account_rules import (
    _declared, _same_levels, verify_bounds_account,
)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(n for n in SHAPES if SHAPES[n]["result"].get(
    "bounds_results"))

MANSKI = "aipw"
IV = "general_id_plugin"


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _row(result, method=None):
    for row in result.get("bounds_results") or []:
        if method is None or row.get("method") == method:
            return row
    raise AssertionError(f"no {method} row")


def _verify_with(name, mutate, method=None):
    program, result = _pair(name)
    mutate(_row(result, method))
    themis.verify(program, result)


# ------------------------------------------------- the facts this rests on


def test_a_bound_is_carried_by_half_the_answers():
    assert len(CARRIERS) == 21
    methods = {r.get("method") for n in CARRIERS
               for r in SHAPES[n]["result"]["bounds_results"]}
    assert methods == {"manski_natural", "balke_pearl_iv",
                       "manski_tamer_monotonicity"}


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        program, result = _pair(name)
        themis.verify(program, result)


def test_a_declared_name_and_a_declared_domain_are_different_facts():
    """The distinction a first version collapsed.

    Every variable a program declares is a NAME; only some of them
    declare their LEVELS. Reading the second set as the first refused ten
    honest answers, because an expression naming ``y`` was held against a
    map that only contained variables with a domain.
    """
    program, _ = _pair(MANSKI)
    names, domains = _declared(program)
    assert names and set(domains) < names
    assert all(isinstance(v, list) for v in domains.values())


def test_levels_are_compared_as_levels_not_as_json():
    """``[0, 1, 2, 3]`` and ``[0.0, 1.0, 2.0, 3.0]`` are one declaration
    that has been through JSON. ``True`` and ``1`` are not."""
    assert _same_levels([0, 1, 2, 3], [0.0, 3.0, 2.0, 1.0])
    assert _same_levels([True, False], [False, True])
    assert not _same_levels([True, False], [1, 0])
    assert not _same_levels([0, 1], [0, 1, 2])


# ------------------------------------------------------------- the gate


def test_a_row_that_asks_a_reader_for_the_wrong_distribution():
    """The counter-example this exists for: still a real distribution
    over real variables, just not the one that would narrow this."""
    def wrong(row):
        row["data_required"][0]["said"]["expression"] = "P(y, z)"

    with pytest.raises(VerificationError, match="this row was computed from"):
        _verify_with("backdoor_linear", wrong, "manski_natural")


def test_a_row_that_names_a_variable_the_problem_does_not_have():
    def stranger(row):
        row["data_required"][0]["said"]["expression"] = "P(y, appetite)"

    with pytest.raises(VerificationError, match="not a variable this program"):
        _verify_with(MANSKI, stranger, "manski_natural")


def test_a_width_laid_to_a_mass_the_interval_was_not_built_with():
    """The bare-name forgery the vocabulary check cannot see.

    ``x`` is a name this problem declares, so every word in the claim is
    real; what is false is that the width is that. Only the expression
    the interval was actually built from tells the two apart.
    """
    for value in ("x", "P(x=true)"):
        with pytest.raises(VerificationError, match="wrong quantity"):
            _verify_with(MANSKI, lambda r, v=value: r["notes"][0]["said"]
                         .update(mass=v), "manski_natural")


def test_a_width_laid_to_nothing_at_all():
    with pytest.raises(VerificationError, match="puts nothing there"):
        _verify_with(MANSKI, lambda r: r["notes"][0]["said"].update(mass="  "),
                     "manski_natural")


def test_a_row_that_miscounts_the_table_it_asks_for():
    def miscount(row):
        row["data_required"][0]["said"]["cells"] = "12"

    with pytest.raises(VerificationError, match="cells the table"):
        _verify_with(IV, miscount, "balke_pearl_iv")


def test_a_row_that_miscounts_the_polytope_it_solved():
    def miscount(row):
        row["notes"][0]["said"]["types"] = "8"

    with pytest.raises(VerificationError, match="response types"):
        _verify_with(IV, miscount, "balke_pearl_iv")


def test_a_row_that_misreports_how_many_levels_a_variable_has():
    for key in ("treatment_levels", "outcome_levels", "instrument_levels"):
        with pytest.raises(VerificationError, match="levels; the program"):
            _verify_with(IV, lambda r, k=key: r["notes"][0]["said"]
                         .update({k: "3"}), "balke_pearl_iv")


def test_a_row_that_says_it_ran_over_levels_the_program_does_not_declare():
    def relevel(row):
        row["sufficient_statistics"]["treatment_levels"] = [False, True, None]

    with pytest.raises(VerificationError, match="the program declares"):
        _verify_with(IV, relevel, "balke_pearl_iv")


def test_a_monotonicity_note_that_names_the_other_side():
    """The side is passed from the rule that derived it, never derived
    again — the file it comes from records three surfaces agreeing on a
    wrong side because each computed it from the one polarity it held.
    """
    name = next(n for n in CARRIERS
                if any(r.get("method") == "manski_tamer_monotonicity"
                       for r in SHAPES[n]["result"]["bounds_results"]))

    def flip(row):
        row["notes"][0]["words"]["side"]["token"] = "upper"

    with pytest.raises(VerificationError, match="row was verified as"):
        _verify_with(name, flip, "manski_tamer_monotonicity")

    def redirect(row):
        row["notes"][0]["words"]["direction"]["token"] = "non_increasing"

    with pytest.raises(VerificationError, match="row was verified as"):
        _verify_with(name, redirect, "manski_tamer_monotonicity")

    def elsewhere(row):
        row["notes"][0]["said"]["to"] = "P(x=true)"

    with pytest.raises(VerificationError, match="tightening it to"):
        _verify_with(name, elsewhere, "manski_tamer_monotonicity")


# ------------------------------------------- what the rule does not reach


def test_the_glossary_keys_are_declared_not_held():
    """Counted, so that "we closed the bounds block" cannot be said.

    ``token`` and ``vocabulary`` say which sentence a reader is shown and
    which glossary it comes from. There is no authority for them on this
    side: the words live in ``themis.output.reader_words``, no verifier
    module imports ``themis.output``, and the envelope schema does not
    enumerate them. The envelope carries 134 leaves of this shape across
    four blocks — 86 here, 36 in the gap report, 6 in the assumption
    ledger (only the ones with no id; the rest were closed by its
    id-prefix rule) and 2 in the IV block — so what this needs is one
    frontier about reader words, not a guess per block.
    """
    survived = []
    for name in CARRIERS:
        for group in ("data_required", "notes"):
            for key in ("token", "vocabulary"):
                for bend in ("_forged", "", "x"):
                    program, result = _pair(name)
                    claims = _row(result).get(group) or []
                    if not claims or key not in claims[0]:
                        continue
                    claims[0][key] = (str(claims[0][key]) + bend
                                      if bend == "_forged" else bend)
                    try:
                        themis.verify(program, result)
                    except Exception:
                        continue
                    survived.append((name, group, key))
                    break
    assert len(survived) == 84
    assert {(g, k) for _, g, k in survived} == {
        ("data_required", "token"), ("data_required", "vocabulary"),
        ("notes", "token"), ("notes", "vocabulary"),
    }


def test_the_uninformative_flag_is_declared_because_it_is_never_true():
    """Every row in the corpus records ``False``. A rule for when it may
    be ``True`` would be invented from twenty-one examples of the other
    case, which is how a table built from a corpus refused an honest
    answer two frontiers ago. Its own frontier, once a ``True`` exists.
    """
    values = [r.get("numeric_uninformative") for n in CARRIERS
              for r in SHAPES[n]["result"]["bounds_results"]]
    assert set(values) == {False, None}


def test_the_rule_is_silent_where_there_are_no_bounds_to_read():
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        assert not result.get("bounds_results")
        verify_bounds_account({}, program=program, query_dict={})
