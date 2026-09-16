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
from tests.answer_corpus import the_door_for, verify_honestly
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
#: An answer whose sharp row is taken around an instrument the graph offers.
IV = "iv_acr"


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
    assert len(CARRIERS) == 83
    methods = {r.get("method") for n in CARRIERS
               for r in SHAPES[n]["result"]["bounds_results"]}
    assert methods == {"manski_natural", "balke_pearl_iv",
                       "manski_tamer_monotonicity"}


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        verify_honestly(*_pair(name))


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


def _a_floor_carrying_a_decline():
    """The one shape whose note is an account of a method its row is not.

    At 5×5×2 levels the Balke-Pearl polytope is past the cap, so what is
    reported is the assumption-free floor and it carries the decline of
    the sharper method. The instrument that decline counts over is named
    in the NOTE, because the row it hangs on is a Manski row and has
    none — which is why a count read against the row's roles was read
    against no instrument at all.

    Built from the program rather than taken from the corpus: this is the
    only shape in the corpus that produces it, and a gate that can only be
    asked when a snapshot happens to hold the answer is a gate that goes
    quiet when the snapshot moves.
    """
    from tests.test_e2e.test_phase12_bounds_wiring import _sized_iv_program

    program = _sized_iv_program(5, 5, 2, 2, 2)
    result = themis.run(program)["results"][0]
    return program, result


def test_a_note_is_held_to_the_instrument_it_names_rather_than_the_rows():
    program, result = _a_floor_carrying_a_decline()
    row = _row(result, "manski_natural")
    said = row["notes"][1]["said"]
    assert row.get("instrument") is None and said["instrument"] == "z"
    verify_honestly(program, result)

    said["instrument_levels"] = "3"
    with pytest.raises(VerificationError, match="levels; the program"):
        the_door_for(result)(program, result)


def test_a_note_whose_count_is_pointed_at_a_different_variable():
    """Naming another declared variable must not launder the count.

    ``y`` is declared with five levels, so a note that keeps saying two
    while claiming to be about ``y`` is refused for the same reason — the
    subject and the count are read together or neither is held.
    """
    program, result = _a_floor_carrying_a_decline()
    said = _row(result, "manski_natural")["notes"][1]["said"]
    said["instrument"] = "y"
    with pytest.raises(VerificationError, match="levels; the program"):
        the_door_for(result)(program, result)


def test_a_note_may_not_switch_the_count_off_by_renaming_its_subject():
    """The escape reading the subject off the block opens, and its close.

    A count is read against the declaration its subject names, and the
    rule beside it is silent about a name the program declares no levels
    for — silence that belonged to the asked side while the subject was
    the ROW's. Once the block chooses its own subject, that silence is
    something an answer can arrange: name the instrument something
    unrecognisable and the count beside it goes unread again.

    So claiming how many levels a thing has is claiming it of something
    this program gives levels to. Measured on the corpus before this was
    written: one block names its own instrument, and it names a declared
    one, so nothing honest is refused by asking.
    """
    program, result = _a_floor_carrying_a_decline()
    said = _row(result, "manski_natural")["notes"][1]["said"]
    said.update(instrument="nowhere", instrument_levels="999")
    with pytest.raises(VerificationError, match="declares no levels"):
        the_door_for(result)(program, result)


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

    # Two doors, and each is asked what it is the one to say. Which way
    # the assumption runs is the QUESTION's word, and a reader meets it
    # in four blocks, so through the whole envelope the rule that holds
    # it is the one that walks all four. This row's own door is where
    # the account still speaks: there the word is held to the direction
    # THIS row was verified at, which is the only authority a program
    # declaring it through the older extensions channel has.
    with pytest.raises(VerificationError,
                       match="the question it answers"):
        _verify_with(name, redirect, "manski_tamer_monotonicity")

    program, result = _pair(name)
    redirect(_row(result, "manski_tamer_monotonicity"))
    with pytest.raises(VerificationError, match="row was verified as"):
        themis.verify_bounds_results(program, result)

    def elsewhere(row):
        row["notes"][0]["said"]["to"] = "P(x=true)"

    with pytest.raises(VerificationError, match="tightening it to"):
        _verify_with(name, elsewhere, "manski_tamer_monotonicity")


# ------------------------------------------- what the rule does not reach


def test_the_glossary_keys_are_held_by_the_contract():
    """This was the count of what could not be held, and the count was the
    only true half of it.

    ``token`` and ``vocabulary`` say which sentence a reader is shown and
    which glossary it comes from, and 84 of the 86 leaves here could be
    edited to any word at all. What this test used to say was that there is
    no authority for them on this side, because the words live in
    ``themis.output.reader_words`` and no verifier module may import
    ``themis.output``.

    That was about the wrong side of the boundary. ``verify`` validates
    against the contract before any rule runs, and the contract is where a
    closed set belongs — ``reader_words`` was already reading several of
    its sets back out of the envelope's schema. Both keys are now
    enumerated in the shared statement carrier, and none of the 84
    survives.
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
    assert survived == []


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
