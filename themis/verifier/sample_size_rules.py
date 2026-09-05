"""How much data a reader is told to go and collect, and from where.

A gap that blocks an answer ends in an instruction: collect this much of
this kind of data, on these variables, from that population. It is the
most expensive advice this system gives — somebody runs a trial on it —
and it was the largest block on the envelope nothing held. Measured: 229
of its leaves on the answer shapes could be rewritten and both public
doors said yes, including every minimum sample size.

THE NUMBER IS NOT A COPY OF ANYTHING, so nothing on the envelope could
have held it. It is a power calculation, and what makes it checkable is
that the calculation's inputs travel beside it: the number arrives with a
statement of what it buys, and that statement's facts are the parameters
it was computed from — Cohen's h, the precision a proportion is pinned to,
how many strata, how many sampling points. So the second authority is the
arithmetic, re-run here.

The closed forms are transcribed rather than imported, for the reason
every numeric end in this package is: the producer lives in
``themis.output``, which no verifier may reach, and a number re-derived by
calling the code that produced it would prove only that the code is
consistent with itself. What is transcribed is the textbook statement of
each design — a two-arm test at α=0.05 two-sided and 80% power, a single
proportion held to a half-width at 95% confidence — and the two quantiles
those need. A token this build has no formula for is passed over in
silence; a test holds the table to the vocabulary, so a precision target
added without a formula here fails there rather than going unheld.

THE REST OF THE BLOCK IS THE PROBLEM'S OWN WORDS, and they are asked of
the problem rather than of the answer: the variables to measure and the
confounders to condition on are predicates it declares, and a population
named to collect from is one it declares as a source or a target domain.

A population may also arrive as a STATEMENT rather than a name, where the
producer had no name to pass on and a characterisation instead. That one
is not held here and is not held anywhere else either — one leaf, and
saying so is the point: a name claims to be a domain the program
declared and can be checked against it, while a characterisation claims
only to describe one, and what would settle it is the words it is built
from rather than the roster this rule reads.

What stays open is ``data_type``. Which shape of data closes a gap is
chosen where the gap is raised, and nothing declares a relation between
it and anything else on the envelope; a table mapping gap kinds to data
types would be this package restating a producer's judgement, which is
the shape a verifier must not take.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import NoReturn

from .errors import VerificationError
from .gap_claim_rules import words_the_problem_uses

_RULE = "required_data_check"

#: The two standard-normal quantiles a design at α=0.05 two-sided with 80%
#: power is written with. Spelt here rather than imported for the reason
#: the module docstring gives; they are properties of the normal
#: distribution rather than of any producer.
_Z_HALF_ALPHA = 1.959964
_Z_POWER = 0.841621


def _reject(says: str) -> NoReturn:
    raise VerificationError(says, step_index=None, rule=_RULE)


def _up_to_50(n: float) -> int:
    """A power analysis is not accurate to one person, and says so."""
    return int(math.ceil(n / 50.0) * 50)


def _two_arm_binary(h: float) -> int:
    """Cohen 1988: n per arm = (z_{α/2} + z_β)² / h², two arms."""
    return _up_to_50(2 * math.ceil((_Z_HALF_ALPHA + _Z_POWER) ** 2 / h ** 2))


def _two_arm_continuous(d: float) -> int:
    """The same design on a mean, where the variance costs a factor of 2."""
    return _up_to_50(
        2 * math.ceil(2 * (_Z_HALF_ALPHA + _Z_POWER) ** 2 / d ** 2))


def _one_proportion(precision: float, p: float) -> int:
    """A proportion held to ± ``precision`` at 95%, at the stated p."""
    return _up_to_50(
        math.ceil(_Z_HALF_ALPHA ** 2 * p * (1 - p) / precision ** 2))


#: What each precision target's number is, as a function of the facts that
#: same target states. A per-token table because each token names a
#: DIFFERENT design, which is what the token is for; what the table holds
#: is arithmetic rather than a vocabulary restated.
_THE_ARITHMETIC: dict[str, Callable[[Callable[[str], float]], int]] = {
    "detect_a_binary_effect":
        lambda f: _two_arm_binary(f("h")),
    "detect_a_continuous_effect":
        lambda f: _two_arm_continuous(f("d")),
    "detect_both_mediation_paths":
        lambda f: _up_to_50(int(_two_arm_binary(f("h")) * f("times"))),
    "detect_the_effect_in_every_stratum":
        lambda f: _up_to_50(_two_arm_binary(f("h")) * int(f("strata"))),
    "pin_the_target_distribution":
        lambda f: _up_to_50(
            _one_proportion(f("precision"), f("p")) * int(f("strata"))),
    "pin_one_proportion":
        lambda f: _one_proportion(f("precision"), f("p")),
    "trace_a_dose_response_curve":
        lambda f: int(f("points")) * int(f("per_point")),
}


def _check_the_number_is_what_its_own_terms_buy(where: str, need: Mapping
                                                ) -> None:
    """Re-run the power calculation the target beside the number states.

    Silent where the ask has no number or no target: a gap may say what
    kind of data closes it without sizing the study, and a size nobody
    stated is not one anybody can be misled by.

    A term the arithmetic needs and the target does not state is refused
    rather than passed over. Every one of the seven producers fills its
    slots at the call site, so a target short of one is claiming a number
    nothing could have arrived at — and this is the edit that would
    otherwise walk through: change which design the target names and the
    terms beneath it no longer fit any formula, which reads as "nothing to
    check" unless silence is spent carefully. Nothing else asks it either:
    the statement carrier holds a token's facts against its holes, and its
    table has no row for this block.
    """
    wanted = need.get("min_sample_size")
    target = need.get("precision_target")
    if wanted is None or not isinstance(target, Mapping):
        return
    arithmetic = _THE_ARITHMETIC.get(str(target.get("token")))
    if arithmetic is None:
        return
    said = target.get("said")
    said = said if isinstance(said, Mapping) else {}

    def stated(key: str) -> float:
        if key not in said:
            _reject(
                f"{where} asks a reader for {wanted} observations to "
                f"{str(target.get('token'))!r}, and that target states no "
                f"{key!r}. The number is a calculation over the terms beside "
                f"it, so a design short of one of them is a size nothing "
                f"could have arrived at")
        try:
            return float(said[key])
        except (TypeError, ValueError):
            _reject(
                f"{where} states {key}={said[key]!r} where the calculation "
                f"behind its sample size needs a number, so the size cannot "
                f"be the one those terms buy whatever it says")

    again = arithmetic(stated)
    if again == wanted:
        return
    _reject(
        f"{where} tells a reader to collect {wanted} observations; the "
        f"target it states beside that number — {target.get('token')!r} on "
        f"{dict(said)} — is bought by {again}. Somebody is being sent to run "
        f"a study of the wrong size, and the terms it would be sized from "
        f"are on the envelope"
    )


def _check_the_sampling_points_agree(where: str, need: Mapping) -> None:
    """The one count this block writes down twice."""
    count = need.get("sampling_point_count")
    said = (need.get("precision_target") or {})
    said = said.get("said") if isinstance(said, Mapping) else None
    said = said if isinstance(said, Mapping) else {}
    if count is None or "points" not in said:
        return
    if str(count) == str(said["points"]) or float(count) == float(
            said["points"]):
        return
    _reject(
        f"{where} says to sample {count} points and the target beside it "
        f"says {said['points']}; a reader designing the study reads one of "
        f"them and the number sizing it was computed from the other"
    )


def _check_the_names_are_the_problems(where: str, need: Mapping,
                                      words: set) -> None:
    """Which variables to measure, asked of the problem rather than the answer."""
    if not words:
        return
    for field in ("variables", "confounders_required"):
        for name in need.get(field) or ():
            if str(name) in words:
                continue
            _reject(
                f"{where} tells a reader to measure {str(name)!r}, which is "
                f"not a name this problem is written in. The list is the "
                f"program's own predicates, and a reader sent after a "
                f"variable nobody declared collects a column that answers "
                f"nothing"
            )


def _declared_populations(context) -> set:
    """The domains a program is about: the one asked for, and the sources."""
    found = set()
    asked = getattr(getattr(context, "query", None), "target_population", None)
    if asked is not None:
        found.add(str(asked))
    for node in getattr(context, "selection_nodes", ()) or ():
        source = getattr(node, "source_population", None)
        if source is not None:
            found.add(str(source))
    return found


def _check_the_population_is_one_the_program_has(where: str, need: Mapping,
                                                 declared: set) -> None:
    """Where to collect from, when the block names one rather than
    characterising it.

    A characterisation travels as a statement and is the statement
    carrier's to hold; only a NAME claims to be a domain this program
    declared. Silent where the program declares none: a one-population
    problem names its population nowhere, so there is nothing to be a
    member of and a membership question with no members refuses honest
    answers.
    """
    population = need.get("population")
    if not isinstance(population, str) or not declared:
        return
    if population in declared:
        return
    _reject(
        f"{where} sends a reader to collect from {population!r}; this "
        f"problem declares {sorted(declared)}. Data from a population the "
        f"question is not about answers a different question"
    )


def verify_required_data(result: Mapping, context) -> None:
    """Hold every ask a gap makes of a reader to the problem and the arithmetic."""
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    words = words_the_problem_uses(context)
    declared = _declared_populations(context)
    for index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, Mapping):
            continue
        need = gap.get("required_data")
        if not isinstance(need, Mapping):
            continue
        where = f"gap {index}'s data ask"
        _check_the_number_is_what_its_own_terms_buy(where, need)
        _check_the_sampling_points_agree(where, need)
        _check_the_names_are_the_problems(where, need, words)
        _check_the_population_is_one_the_program_has(where, need, declared)
