"""What a bounds row TELLS a reader, against what it was computed from.

:mod:`bounds_rules` is one of the deepest re-derivations in the
repository: it re-runs the Balke-Pearl response-function LP, re-derives
the Manski expressions, checks the instrumental inequalities, and refuses
an interval that is not what its own arithmetic yields. It verifies the
ANSWER. It has never verified the ACCOUNT of the answer.

A row carries two lists written for a person. ``data_required`` says what
would narrow this interval — "a joint distribution, ``P(y, x)``" — and
``notes`` says where the width came from — "the width is the off-arm
mass, ``P(x=false)``". A reader does not receive the interval; they
receive these. Rewrite one and the reader goes and collects a
distribution over a different variable, while every arithmetic check
still passes. Measured before this module existed: all of it could be
rewritten and the door said yes.

WHY NO TABLE IS NEEDED, WHICH IS THE WHOLE DESIGN. Each claim's contents
are already determined by something beside them:

- A rendered quantity — ``said.expression``, ``said.mass``, ``said.to``
  — is spelled in words that are either names the PROGRAM declares or
  words already in this row's own ``lower_expression`` /
  ``upper_expression``, which :mod:`bounds_rules` re-derives. So the
  expression language's vocabulary is taken from the row's own formulas
  instead of restated here. Twenty-six, twenty-one and one, no
  exceptions, and every edit the census makes is refused.
- A count — ``said.cells``, ``said.types``, ``said.*_levels`` — is the
  number of levels the program declares for the variable it counts, or
  the response-type count :func:`bounds_rules._v_response_types`
  computes from those. The program is the asked side, which an answer
  cannot edit; taking these from the row's own
  ``sufficient_statistics`` instead left two rows with nothing to check.
- The level sets in ``sufficient_statistics`` are those same declared
  domains. They are asked here rather than left for later because the
  counts above are counts OF them: holding a rendering while leaving the
  thing it renders free is the shape the previous frontier removed.

WHAT IS NOT ASKED HERE. ``token`` and ``vocabulary`` — the glossary key
and the glossary it belongs to — have no authority on this side. The
words live in ``themis.output.reader_words``, and no verifier module
imports ``themis.output``; the envelope schema does not enumerate them
either. This is the second block with that exact shape, the assumption
ledger being the first, so what they need is one frontier about reader
words rather than a guess per block.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, NoReturn

from .bounds_rules import _v_response_types
from .errors import VerificationError

_RULE = "bounds_account_check"

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: The ``said`` keys that hold a rendered quantity, and the ones that
#: hold a count of a variable's levels. Not a glossary: the first group
#: is checked against words this row already uses and the second against
#: the program, so what these names decide is only WHICH of the two
#: questions a value is asked — never whether the value is allowed.
_RENDERED = ("expression", "mass", "to")
_LEVEL_COUNTS = {
    "treatment_levels": "treatment",
    "outcome_levels": "outcome",
    "instrument_levels": "instrument",
}


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, step_index=None, rule=_RULE)


def _declared(program: Mapping) -> tuple[set[str], dict[str, list]]:
    """Two different facts a program states, kept apart.

    Every variable it declares is a name, and only some of them declare
    their LEVELS. Reading one set as the other is what a first version
    did: an expression naming ``y`` was refused because ``y`` declares no
    domain, which is a fact about its levels and not about whether it
    exists.
    """
    names: set[str] = set()
    domains: dict[str, list] = {}
    for statement in program.get("statements") or ():
        if not isinstance(statement, Mapping):
            continue
        if statement.get("kind") != "variable":
            continue
        predicate = str(statement.get("predicate"))
        names.add(predicate)
        domain = statement.get("domain")
        if domain is not None:
            domains[predicate] = list(domain)
    return names, domains


def _same_level(one: Any, other: Any) -> bool:
    """Whether two recorded levels are the same level.

    ``[0, 1, 2, 3]`` in a program and ``[0.0, 1.0, 2.0, 3.0]`` on the
    envelope are one declaration that has been through JSON, so numbers
    are compared as numbers. Booleans are not numbers here, because
    ``True == 1`` and a two-level boolean domain must not match a
    numeric one.
    """
    if isinstance(one, bool) or isinstance(other, bool):
        return one is other
    if isinstance(one, (int, float)) and isinstance(other, (int, float)):
        return float(one) == float(other)
    return bool(one == other)


def _same_levels(one: Any, other: Any) -> bool:
    if not isinstance(one, (list, tuple)) or not isinstance(
            other, (list, tuple)):
        return False
    if len(one) != len(other):
        return False
    rest = list(other)
    for value in one:
        for i, candidate in enumerate(rest):
            if _same_level(value, candidate):
                rest.pop(i)
                break
        else:
            return False
    return True


def _roles(row: Mapping, query_dict: Mapping) -> dict[str, str | None]:
    intervention = query_dict.get("intervention") or {}
    target = query_dict.get("target") or {}
    return {
        "treatment": (intervention.get("atom") or {}).get("predicate"),
        "outcome": (target.get("atom") or {}).get("predicate"),
        "instrument": row.get("instrument"),
    }


def _words_this_row_already_uses(row: Mapping,
                                 names: set[str]) -> set[str]:
    """The vocabulary a rendered claim may draw on.

    Two sources, neither of them a list this module keeps: the names the
    program declares, and the words of the formulas beside the claim —
    which are the producer's spelling of the same expression language,
    and are themselves re-derived. An operator table here would be a
    third copy of a rendering decision that is not the verifier's.
    """
    formulas = f"{row.get('lower_expression')} {row.get('upper_expression')}"
    return set(_IDENT.findall(formulas)) | names


def _check_a_rendered_quantity(where: str, key: str, value: Any,
                               vocabulary: set[str]) -> None:
    # Emptiness first and on its own: everything below is a membership,
    # and a membership over no words at all is vacuously satisfied while
    # reading, to a person, as a sentence with a hole in it.
    if not str(value).strip():
        _reject(
            f"{where} tells a reader the {key} it is about and puts "
            f"nothing there"
        )
    stray = sorted(set(_IDENT.findall(str(value))) - vocabulary)
    if stray:
        _reject(
            f"{where} tells a reader about {str(value)!r}, which names "
            f"{stray} — not a variable this program declares, and not a "
            f"word the interval beside it was written with"
        )


def _check_a_level_count(where: str, key: str, value: Any, role: str,
                         predicate: str | None,
                         declared: Mapping[str, list]) -> None:
    if predicate is None or predicate not in declared:
        # The program says nothing about this variable's levels, so
        # there is no count to disagree with. Silence on the ASKED side,
        # which an answer cannot arrange for itself.
        return
    want = len(declared[predicate])
    if not str(value).strip():
        _reject(
            f"{where} tells a reader how many levels the {role} has and "
            f"puts nothing there"
        )
    if str(value) != str(want):
        _reject(
            f"{where} tells a reader the {role} {predicate!r} has "
            f"{str(value)!r} levels; the program declares {want}"
        )


def _check_the_table_size(where: str, value: Any, roles: Mapping,
                          declared: Mapping[str, list], types: bool) -> None:
    sizes = []
    for role in ("treatment", "outcome", "instrument"):
        predicate = roles.get(role)
        if predicate is None or predicate not in declared:
            if role == "instrument":
                continue
            return
        sizes.append(len(declared[predicate]))
    if len(sizes) < 2:
        return
    nx, ny = sizes[0], sizes[1]
    nz = sizes[2] if len(sizes) > 2 else 1
    if types:
        fxs, gys = _v_response_types(nx, ny, nz)
        want = len(fxs) * len(gys)
        what = "response types the polytope enumerates"
    else:
        want = nx * ny * nz
        what = "cells the table it asks for has"
    if not str(value).strip():
        _reject(f"{where} tells a reader how many {what} and puts "
                f"nothing there")
    if str(value) != str(want):
        _reject(
            f"{where} tells a reader there are {str(value)!r} {what}; the "
            f"levels this program declares make {want}"
        )


def verify_bounds_account(row: Mapping, *, program: Mapping,
                          query_dict: Mapping) -> None:
    """Hold one bounds row's reader-facing lists to what it was computed
    from.

    Asked of every method, before the dispatch that knows which one this
    is, because the two lists are the same thing on all three.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` when a row would
    tell a reader to go and collect something other than what would
    narrow it, or would attribute its width to something else.
    """
    names, declared = _declared(program)
    roles = _roles(row, query_dict)
    vocabulary = _words_this_row_already_uses(row, names)
    columns = set(row.get("numeric_data_columns") or ())

    for group in ("data_required", "notes"):
        for i, claim in enumerate(row.get(group) or ()):
            if not isinstance(claim, Mapping):
                continue
            where = f"bounds_results[{row.get('method')!r}].{group}[{i}]"
            said = claim.get("said")
            if not isinstance(said, Mapping):
                continue
            for key in _RENDERED:
                if key in said:
                    _check_a_rendered_quantity(
                        where, key, said[key], vocabulary)
            expression = said.get("expression")
            if expression is not None and columns:
                named = set(_IDENT.findall(str(expression))) & names
                if named != columns:
                    _reject(
                        f"{where} tells a reader the interval would "
                        f"narrow given {str(expression)!r}, over "
                        f"{sorted(named)}; this row was computed from "
                        f"{sorted(columns)}"
                    )
            # Whose account this claim is. A note can be about a method
            # this row is NOT — the assumption-free floor carries the
            # decline of the sharper one that was available — and then the
            # instrument being counted over is named in the block and
            # nowhere on the row, so a count read against the row's roles
            # is read against no instrument at all and goes unasked. Which
            # instrument a CLAIM is about is a fact about the claim, so it
            # is read per claim rather than once per row.
            about = dict(roles)
            subject = said.get("instrument")
            if isinstance(subject, str):
                # And the subject is load-bearing, so it is held too. A
                # count is read against the declaration its subject names,
                # and _check_a_level_count is silent about a name the
                # program declares no levels for — silence that belongs to
                # the ASKED side and that an answer was not able to arrange
                # for itself until the subject became the answer's to
                # choose. Naming something unrecognisable would now switch
                # the count check off, so claiming how many levels a thing
                # has is claiming it of something this program gives levels.
                if "instrument_levels" in said and subject not in declared:
                    _reject(
                        f"{where} tells a reader it is about the instrument "
                        f"{subject!r} and how many levels that has; this "
                        f"program declares no levels for that name"
                    )
                about["instrument"] = subject
            for key, role in _LEVEL_COUNTS.items():
                if key in said:
                    _check_a_level_count(where, key, said[key], role,
                                         about.get(role), declared)
            if "cells" in said:
                _check_the_table_size(where, said["cells"], about, declared,
                                      types=False)
            if "types" in said:
                _check_the_table_size(where, said["types"], about, declared,
                                      types=True)

    statistics = row.get("sufficient_statistics")
    if isinstance(statistics, Mapping):
        for key, role in _LEVEL_COUNTS.items():
            if key not in statistics:
                continue
            predicate = roles.get(role)
            if predicate is None or predicate not in declared:
                continue
            if not _same_levels(statistics[key], declared[predicate]):
                _reject(
                    f"bounds_results[{row.get('method')!r}] says it ran "
                    f"over {statistics[key]!r} for the {role} "
                    f"{predicate!r}; the program declares "
                    f"{declared[predicate]!r}"
                )


def verify_the_mass_a_width_is_laid_to(row: Mapping, *, mass: str) -> None:
    """A Manski row's note says the width IS the off-arm mass, and names
    it. That name is a string the caller has just constructed, so it is
    passed in and compared whole.

    The vocabulary check above cannot reach this: it asks whether the
    words are ones this problem uses, and a bare declared name passes —
    a note claiming the width is ``x`` says something false in words
    that are all real. What tells the two apart is the expression the
    interval was actually built from.
    """
    for i, claim in enumerate(row.get("notes") or ()):
        if not isinstance(claim, Mapping):
            continue
        said = claim.get("said")
        if not isinstance(said, Mapping) or "mass" not in said:
            continue
        where = f"bounds_results['manski_natural'].notes[{i}]"
        shown = said["mass"]
        if not str(shown).strip():
            _reject(f"{where} tells a reader which mass the width is and "
                    f"puts nothing there")
        if str(shown) != mass:
            _reject(
                f"{where} tells a reader the width of this interval is "
                f"{str(shown)!r}; the interval was computed with {mass!r} "
                f"as its width, and a reader is being pointed at the "
                f"wrong quantity to go and reduce"
            )


def verify_the_words_a_tightened_side_uses(
    row: Mapping, *, direction: str, side: str | None,
    tightened_to: str | None,
) -> None:
    """The glossed words a monotonicity note shows a reader.

    Taken as arguments rather than re-derived. Which side a monotonicity
    assumption tightens is precisely what
    :func:`bounds_rules.verify_manski_tamer_bounds_result` works out, and
    that file records why a second derivation would be dangerous rather
    than reassuring: three surfaces once agreed on the wrong side because
    each computed it from the one polarity it held. So the side arrives
    from the place that has both, and ``None`` where the assumption
    tightens neither side to the marginal — in which case there is no
    derived answer to hold the word to, and the caller's own expression
    check is what covers the row.
    """
    for i, claim in enumerate(row.get("notes") or ()):
        if not isinstance(claim, Mapping):
            continue
        where = f"bounds_results['manski_tamer_monotonicity'].notes[{i}]"
        said = claim.get("said")
        if isinstance(said, Mapping) and "to" in said and tightened_to:
            shown = said["to"]
            if not str(shown).strip():
                _reject(f"{where} tells a reader what the assumption "
                        f"tightened the bound to and puts nothing there")
            if str(shown) != tightened_to:
                _reject(
                    f"{where} tells a reader the assumption tightened the "
                    f"bound to {str(shown)!r}; this row was verified as "
                    f"tightening it to {tightened_to!r}"
                )
        words = claim.get("words")
        if not isinstance(words, Mapping):
            continue
        for key, want in (("direction", direction), ("side", side)):
            if want is None:
                continue
            word = words.get(key)
            if not isinstance(word, Mapping) or "token" not in word:
                continue
            shown = word.get("token")
            if not str(shown or "").strip():
                _reject(f"{where} names the {key} it is about and puts "
                        f"nothing there")
            if shown != want:
                _reject(
                    f"{where} tells a reader the {key} is {shown!r}; this "
                    f"row was verified as {want!r}, and a reader weighing "
                    f"the assumption is weighing the wrong one"
                )
