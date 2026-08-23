"""A counter whose denominator is "the sites a door can see".

#405, fourth cut of #391. Two gates were watching the refusal block and each
was watching the other's blind spot.

``test_a_refusal_says_one_thing_in_every_language`` counts the filing sites
that still compose the reader's sentence themselves, and it finds a site by
looking for a call to one of three doors. ``test_a_refusal_reaches_the
_envelope_one_way`` counted the sites that went through NO door — seven dict
literals in ``dispatch`` — and held them on a ratchet, as a queue of renames.

They are the same fact from two sides. Every one of the seven wrote its own
``reason``, so the author count said 109 while the true figure was 116; and
five species reached the envelope ONLY that way, which made them read, in the
gate that judges who writes a species' words, as species with no sites at all.
Their wording had never once been inside it.

WHAT THAT COST, MEASURED. The longitudinal refusal picks its ``estimator``
field conditionally — ``longitudinal_ipw_msm`` or ``longitudinal_gformula`` —
and its sentence did not: it said "not identified by the g-formula" and "the
g-formula estimate would be biased" to both. An ``ipw_msm`` run was told a
method it did not run would have been biased. Sequential exchangeability is
what BOTH g-methods need, and which one ran is already a field on the block,
so the sentence now names neither.

SO THE CUT IS THE DOOR, NOT THE RENAMES. There are no hand-built blocks left
and the rule that says so is absolute rather than a count — while a second
door exists, the gate that judges what a refusal says is judging a subset it
cannot name. Five of the seven handed their sentence to their species on the
way through: 116 → 111, measured the same way at both ends.

WHAT WAS DELIBERATELY LEFT, AND WHERE IT WENT. ``invalid_input`` (25 authors)
and ``not_recoverable`` (2, and two different facts — a missing-data pattern
and a selection bias — under one name) still authored at the door when this
module landed. #405 has since split ``invalid_input`` into the sixteen ways an
argument fails its contract, and answered ``not_recoverable`` the cheaper way:
its two facts differ in one word and in the criterion that judges it, so the
word became a slot (``Recovery``) rather than the name becoming two names.
What made either reachable at all is that the counter here can see them.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import themis
from themis import language, refusals
from themis.refusals import Refusal
from tests.test_verify_longitudinal import _LATENT, _gen_dgp, _program

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The sentence the longitudinal refusal used to carry, verbatim. Both halves
#: name the g-formula; the block's ``estimator`` field does not.
WAS = (
    "the time-varying strategy effect is not identified by the g-formula: "
    "sequential exchangeability fails (an unblocked back-door from a treatment "
    "to the outcome given the measured history). No number is produced — the "
    "g-formula estimate would be biased."
)

#: Species that reached the envelope only as a dict literal, and the detail
#: keys the site now hands over instead of a sentence. A table rather than a
#: derivation: what each site can supply is a fact about that site, and the
#: point of the cut is that it is now written where the species can read it.
CAME_THROUGH = {
    Refusal.NOT_IDENTIFIED: {},
    Refusal.EXTERNAL_DATA_REQUIRED: {
        "exposure": "x", "outcome": "y", "needed": "an unbiased sample"},
    Refusal.DIFFERENTIAL_COMBINED_MISCLASSIFICATION_DEFERRED: {
        "exposure": "smoking", "outcome": "cancer"},
    Refusal.MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT: {
        "variable": ["bmi"], "adjustment": ["age", "sex"]},
    Refusal.REQUIRES_A_POINT_ESTIMATE: {
        "exposure": "x", "outcome": "y"},
}


# --- the correction, on a live run --------------------------------------------


@pytest.fixture(scope="module")
def unidentified() -> dict[str, dict]:
    """The same unidentified strategy effect, refused by each g-method."""
    return {
        which: themis.estimate(_program(which, extra=_LATENT), _gen_dgp(),
                               ci_bootstrap=0)["results"][0]
        for which in ("gformula", "ipw_msm")
    }


def test_both_g_methods_refuse_the_same_unidentified_effect(unidentified):
    """The premise. Without both refusing, the sentence below has nothing to
    be wrong about."""
    for which, result in unidentified.items():
        failure = result["estimator_failure"]
        assert failure["failure_type"] == "not_identified", which
    assert unidentified["gformula"]["estimator_failure"]["estimator"] == \
        "longitudinal_gformula"
    assert unidentified["ipw_msm"]["estimator_failure"]["estimator"] == \
        "longitudinal_ipw_msm"


def test_the_sentence_does_not_name_a_method_the_block_contradicts(unidentified):
    """The block says which method ran and the sentence said which method was
    biased, and only one of the two was conditional.

    The fix is not a second conditional. Sequential exchangeability is what
    both g-methods rest on, so the fact is about neither — and which one ran
    is a field the reader already has.
    """
    reasons = {which: result["estimator_failure"]["reason"]
               for which, result in unidentified.items()}
    assert len(set(reasons.values())) == 1, reasons
    said = next(iter(reasons.values()))
    for method in ("g-formula", "gformula", "ipw_msm", "IPW", "MSM"):
        assert method not in said, (method, said)
    assert said == refusals.sentence(Refusal.NOT_IDENTIFIED, {})


def test_the_sentence_it_replaced_named_one_and_would_have_been_wrong():
    """Transcribed, so what was fixed is readable here rather than in a diff:
    the old wording is a claim about the g-formula, and half of the runs that
    got it were not running the g-formula."""
    assert "g-formula" in WAS
    assert WAS.count("g-formula") == 2
    for lang in sorted(language.written()):
        assert WAS != refusals.sentence(Refusal.NOT_IDENTIFIED, {}, lang)


# --- the five now speak, in both languages ------------------------------------


@pytest.mark.parametrize("species", sorted(CAME_THROUGH, key=str),
                         ids=lambda s: str(s))
def test_a_species_that_only_dispatch_filed_now_has_its_own_sentence(species):
    """Each of the five, filled from the details its site supplies.

    The species' sentence being renderable is not the same as its site being
    able to render it — a slot the site never names raises ``KeyError`` at
    the moment the refusal is being written down. Here the details are the
    site's own, so this is the sentence the reader gets.
    """
    details = CAME_THROUGH[species]
    for lang in sorted(language.written()):
        said = refusals.sentence(species, details, lang)
        assert said and "{" not in said, (species, lang, said)


def test_the_species_speaks_when_the_site_hands_over_the_names():
    """One of the five end to end, through the door the sites now use."""
    built = refusals.block(
        estimator="regression_calibration",
        failure_type=Refusal.MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT,
        details={"variable": ["bmi"], "adjustment": ["age", "sex"]},
    )
    assert built["reason"] == refusals.sentence(
        Refusal.MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT,
        built["details"], language.DEFAULT)
    assert "bmi" in built["reason"] and "age" in built["reason"]
    assert built["details"] == {"variable": ["bmi"],
                                "adjustment": ["age", "sex"]}


# --- and the denominator that was wrong ---------------------------------------


def _authored(*, through_a_door_only: bool) -> int:
    """Sites that compose the reader's sentence themselves.

    Two denominators, because that is the finding: reading only the calls is
    what the author-counting gate does, and for as long as a refusal could
    also be a dict literal that reading was a subset with no name.
    """
    total = 0
    for path in sorted((REPO / "themis").rglob("*.py")):
        if path.name == "refusals.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                door = (node.func.id if isinstance(node.func, ast.Name)
                        else getattr(node.func, "attr", ""))
                if door not in ("EstimatorFailure", "IdentificationFailure",
                                "block"):
                    continue
                if len(node.args) >= 2 or any(
                        k.arg in ("message", "reason") for k in node.keywords):
                    total += 1
            elif isinstance(node, ast.Dict) and not through_a_door_only:
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant)}
                if {"failure_type", "reason"} <= keys:
                    total += 1
    return total


def test_the_two_denominators_are_the_same_one_now():
    """With the second door closed they cannot differ, and that is the whole
    point of closing it rather than counting it down: a gate that judges what
    a refusal says now judges every refusal that is said."""
    assert _authored(through_a_door_only=True) == \
        _authored(through_a_door_only=False)


def test_the_wider_count_would_have_seen_what_the_narrow_one_missed():
    """The criterion, shown discriminating on the shape it was blind to."""
    doctored = ast.parse(
        "result['estimator_failure'] = {\n"
        "    'estimator': 'e',\n"
        "    'failure_type': Refusal.UNKNOWN,\n"
        "    'reason': 'because',\n"
        "}\n"
    )
    found = [n for n in ast.walk(doctored) if isinstance(n, ast.Dict)]
    keys = {k.value for k in found[0].keys if isinstance(k, ast.Constant)}
    assert {"failure_type", "reason"} <= keys
    assert not [n for n in ast.walk(doctored) if isinstance(n, ast.Call)]
