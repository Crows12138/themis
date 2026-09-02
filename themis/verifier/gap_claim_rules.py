"""What a gap SAYS, against the problem it says it about.

A gap on the envelope carries three things — a ``need`` token, a ``said``
mapping and a ``words`` mapping — and the sentence a reader gets is
``language.assemble(SAYS[need], said, words, lang)``. So ``said`` is not
metadata beside the sentence: it is the facts substituted INTO it. "No
data on ``y``" and "no data on ``y_forged``" are the same gap with
different contents, and only one of them is about this problem.

Nothing read those contents. ``data_gap_rules`` runs three audits and all
three are about the report's SKELETON — whether each provenance ref points
at a real artifact, whether every upstream failure is covered by some gap,
whether a gap's ``kind`` agrees with the signal it cites. Each writes its
own ``for gap in report["gaps"]`` loop, and none of them descends into
what a gap carries: grepping this package for ``describes`` or
``alternative_paths`` returns the English word in prose and nothing else.
Measured before this module existed, on the forty-four answer shapes:
every one of four hundred and sixty-two ``said`` string leaves could be
rewritten and the public door said yes.

The root cause is the DEPTH of a walk, not a missing field, so the walk
here is depth-blind: it finds every ``said`` mapping anywhere under the
report rather than at the three depths that exist today. A fourth nesting
level therefore arrives already asked — and three did, without this file
being touched, when the corpus grew past the answers that carry a number.

THE ROSTER, THOUGH, IS NOT DEPTH-BLIND, and that growth is what showed it.
It is a claim about the whole key space, held by a test that fails on any
key it does not name; but a roster written against answers that reached an
estimator is a statement about estimators, and thirteen keys arrived at
once from answers that reached none. Two of them name variables. The rest
gave the families below the two members they were missing — a claim
written in the notation as well as in the problem's words, and a name from
the other register, which is a population rather than a variable.

WHY NOT SHARE THE NAME SET WITH :func:`formula_fits`. Both ask "is this a
name this problem has", and the two answers differ: a formula names
PREDICATES, while a gap's value is rendered text that carries predicates
and the objects they are applied to (``y``, ``y(u)``, ``{m1(me),
m2(me)}``). Giving both the wider set would let a formula name an object
and pass. They are two questions that read alike, and merging them would
weaken the stricter one.

WHY IDENTIFIERS RATHER THAN A PARSE. One claim is spelled five ways in
the corpus — ``y``, ``y(u)``, ``{m1(me), m2(me)}``, ``a → b``, and
``` `z1`, `z2` ``` — and a rule that parsed spellings would earn a sixth
bug when a sixth appears. Two of those five were found only after this
module was written, by auditing the roster below against the data rather
than trusting it; pulling identifier tokens out and requiring each to be
a word the problem uses needed no change to accept them.
"""
from __future__ import annotations

import re
from typing import Any, Iterator, Mapping

from ..types import VariableDeclaration
from .errors import VerificationError

_RULE = "gap_names_check"

#: A ``said`` key whose value names variables or the objects they are
#: applied to. Kept beside the roster below so that the two together are a
#: statement about the whole key space, not a list of what occurred to
#: whoever wrote them: a test asserts every key any answer shape produces
#: appears in exactly one of them, so a new key cannot arrive unclassified.
_NAMES: frozenset[str] = frozenset({
    "intervention", "variable", "subject", "treatment", "outcome",
    "adjustment", "child", "parent", "instrument", "latent",
    "left", "right", "w", "z", "covariate", "variables",
    # These two read as prose and are not. ``edge`` is a pair of names
    # with an arrow between them and ``instruments`` is a list of them in
    # backticks; both were filed as prose until every identifier in them
    # turned out to be a name this problem declares. A roster is a claim,
    # and this is the one the corpus disagreed with.
    "edge", "instruments",
})

#: A ``said`` key whose value is NOT a name, with what it is instead. The
#: reason each is here is the reason it is not checked yet, and every
#: family has its own root cause rather than a missing line here:
#:
#: a VOCABULARY member needs a table this package would have to restate
#: (and some of these keys hold English PROSE, which a verifier must not
#: pin in a repository with a language layer); a NUMBER needs the second
#: record that most of them do not have; an EXPRESSION is written in the
#: notation as well as in the problem's words, so the whole-token
#: membership below would refuse an honest one for saying ``P`` or ``do``,
#: and holding it means reading the notation rather than listing a key;
#: and a DOMAIN is a name out of the other register — a population is not
#: a variable, and the words this rule knows are the problem's variables
#: by construction, so filing one as a name refuses every transported
#: answer there is.
_NOT_NAMES: Mapping[str, str] = {
    "missing": "vocabulary", "assumptions": "vocabulary",
    "method": "vocabulary", "methods": "vocabulary",
    "branch": "vocabulary", "field": "vocabulary",
    "kind": "vocabulary", "source": "vocabulary",
    "target": "vocabulary", "algorithm": "vocabulary",
    "fallback": "vocabulary",
    "phrase": "prose", "rationale": "prose",
    "note": "prose", "test": "prose",
    "count": "number", "total": "number", "outside": "number",
    "share": "number", "high": "number", "low": "number",
    "lower": "number", "upper": "number", "j": "number", "k": "number",
    "df": "number", "bend": "number", "noise": "number",
    "z_levels": "number", "p": "number", "alpha": "number",
    "h": "number", "n": "number", "precision": "number",
    "skew": "number", "strata": "number",
    "formula": "expression", "what": "expression",
    "population": "domain",
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def every_said_mapping(node: Any, path: tuple = ()) -> Iterator[tuple[str, Mapping]]:
    """Every ``said`` mapping under a report, and where it sits.

    The SCOPE of both questions in this module, stated once and in one
    place. A ``said`` is a ``said`` wherever it hangs — a gap's own top
    level, a ``describes`` entry, an ``alternative_paths`` entry, a
    ``words`` variable all carry one today — and a walk that named those
    containers would be a walk about where its author happened to be
    standing rather than about the shape of a report. Depth-blind for the
    same reason: a fifth container arrives already asked.

    Yields the mapping rather than its leaves, so that a caller asking
    about one key can see the keys beside it. The second question needs
    that: which fields a gap says are unset is a claim about the variable
    named in the SAME breath, and a walk that had already flattened them
    apart could not put the two together.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = path + (str(key),)
            if key == "said" and isinstance(value, Mapping):
                yield ".".join(here), value
            else:
                yield from every_said_mapping(value, here)
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from every_said_mapping(value, path + (str(i),))


def every_said(node: Any, path: tuple = ()) -> Iterator[tuple[str, str, Any]]:
    """Every ``(where, key, value)`` the name rule puts a question to.

    It yields values of EVERY type, including the empty string. A walk
    that skipped those would be deciding they raise no question, in the
    one code shape that makes a decision look like an absence — and the
    decision would have been wrong: an empty name is a gap saying it is
    about nothing, and no honest answer in the corpus has one. Finding is
    this function's job; judging is the caller's.
    """
    for where, said in every_said_mapping(node, path):
        for inner, value in said.items():
            yield f"{where}.{inner}", str(inner), value


def words_the_problem_uses(context) -> set[str]:
    """Every word the verifier knows this problem is written in.

    Predicates and the objects they are applied to, from every source the
    context has: an estimation route's graph carries the variables while
    its theta is empty, a probability query's theta carries them while its
    graph — built from the cause statements — has no nodes at all, and a
    latent pair may name an atom that is in neither. Asking one source
    reads "took part in no edge" as "does not exist".
    """
    atoms = set(context.graph.nodes)
    if context.theta is not None:
        atoms |= set(context.theta.domains)
    for pair in getattr(context, "bidirected", ()) or ():
        atoms |= set(pair)
    words: set[str] = set()
    for atom in atoms:
        words.add(atom.predicate)
        for term in getattr(atom, "args", ()) or ():
            name = getattr(term, "name", None)
            if name:
                words.add(str(name))
    return words


def verify_gap_names(result: Mapping, context) -> None:
    """Every name a gap says must be a name this problem has.

    Returns ``None`` on accept, including when there is no report. Raises
    ``VerificationError`` naming the leaf and the word.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    known = words_the_problem_uses(context)
    if not known:
        return
    for where, key, value in every_said(report):
        if key not in _NAMES:
            continue
        if not isinstance(value, str) or not value.strip():
            raise VerificationError(
                f"a gap says which variable it is about and says nothing "
                f"there: {where} = {value!r}. An empty name is not an "
                f"absent claim — the sentence a reader gets has a hole "
                f"where the variable goes",
                step_index=None, rule=_RULE,
            )
        for token in _IDENT.findall(value):
            if token not in known:
                raise VerificationError(
                    f"a gap says it is about {token!r}, which this problem "
                    f"does not name; the words it is written in are "
                    f"{sorted(known)} (at {where} = {value!r})",
                    step_index=None, rule=_RULE,
                )


# ------------------------------------------- and WHICH of those names


_SUBJECT = "gap_subject_check"


def _declarations(program: Mapping) -> dict[str, Mapping]:
    return {
        str(statement.get("predicate")): statement
        for statement in program.get("statements") or ()
        if isinstance(statement, Mapping)
        and statement.get("kind") == "variable"
    }


def verify_gap_subjects(result: Mapping, program: Mapping) -> None:
    """Not whether a gap's words are names, but whether they are ITS names.

    The rule above asks a question about VOCABULARY: is this a word the
    problem is written in. Every honest gap passes it, and so does a
    forgery that swaps one real variable for another — a gap about ``y``
    rewritten to be about ``x`` sends a reader to fill in a variable that
    is missing nothing, in words that are all real. The previous frontier
    met the same thing on a bounds row claiming its width was ``x``:
    holding a value to "is a real name" is not holding it to "is THIS
    one".

    The answer was already on the gap. A gap carries ``provenance``, and
    T10-1 holds every ref in it to something that exists, so the ref is
    the one part of a gap that cannot be quietly rewritten. Across the
    corpus the variable a gap is about appears in its own refs a hundred
    and two times out of a hundred and two, in all three of the
    containers that carry the key. The skeleton was verified, the
    contents were verified, and nothing had joined them.

    ``missing`` is anchored on the other side entirely: the fields a gap
    says are unset are fields the PROGRAM does not set, which is the
    asked side and not the answer's to arrange. Seventy-five of the
    seventy-seven are exactly the unfilled fields of the patch the
    investigation block offers for the same variable — the fact the last
    frontier anchored — and the other two are unset in the declaration
    too.

    WHOLE TOKENS, NOT SUBSTRINGS. A ref id is a structured string with
    names inside it, so asking whether the subject occurs IN one accepts
    names the ref never mentions: a gap about ``m`` rides on
    ``program:front_door_pattern`` and one about ``y`` on
    ``propensity_overlap:x|z``, forty-eight such rides in this corpus.
    Pulling the identifiers out of the ref and asking for membership
    costs nothing on the honest side — all hundred and two hold either
    way — and refuses every one of them.

    Returns ``None`` on accept, including when there is no report.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    declared = _declarations(program)
    for gap in report.get("gaps") or ():
        if not isinstance(gap, Mapping):
            continue
        raised_by = {
            token
            for ref in gap.get("provenance") or ()
            if isinstance(ref, Mapping) and ref.get("ref_id") is not None
            for token in _IDENT.findall(str(ref["ref_id"]))
        }
        for where, said in every_said_mapping(gap):
            subject = said.get("variable")
            if raised_by and isinstance(subject, str) and subject.strip():
                stray = [t for t in _IDENT.findall(subject)
                         if t not in raised_by]
                if stray:
                    raise VerificationError(
                        f"{where}.variable says this gap is about "
                        f"{subject!r}, and the gap it belongs to was raised "
                        f"by something that never mentions {stray[0]!r}; a "
                        f"reader is sent to a variable this gap is not about",
                        step_index=None, rule=_SUBJECT,
                    )
            missing = said.get("missing")
            if missing is None or subject not in declared:
                continue
            # Emptiness first: everything below is a membership, and a
            # blank passes every membership while telling a reader that
            # nothing is missing about a variable that raised a gap.
            if not str(missing).strip():
                raise VerificationError(
                    f"{where}.missing says which fields {subject!r} is "
                    f"missing and names none; the gap exists because some "
                    f"are",
                    step_index=None, rule=_SUBJECT,
                )
            declaration = declared[subject]
            for field in _IDENT.findall(str(missing)):
                # Two different ways to be wrong, and the first is why a
                # raw statement dict is not enough on its own: an absent
                # key reads as "unset", so a field the declaration has no
                # place for is indistinguishable from one it leaves
                # empty. The TYPE says which fields exist.
                if not hasattr(VariableDeclaration, field):
                    raise VerificationError(
                        f"{where} tells a reader {subject!r} is missing "
                        f"{field!r}, which is not something a variable "
                        f"declaration says at all; a reader cannot supply "
                        f"it and would not know why",
                        step_index=None, rule=_SUBJECT,
                    )
                if declaration.get(field) is not None:
                    raise VerificationError(
                        f"{where} tells a reader {subject!r} is missing "
                        f"{field!r}; the program declares it as "
                        f"{declaration.get(field)!r}, and a reader is "
                        f"asked for something they already gave",
                        step_index=None, rule=_SUBJECT,
                    )
