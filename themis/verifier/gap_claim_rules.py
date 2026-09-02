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
level therefore arrives already asked.

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
    "left", "right", "w", "z",
    # These two read as prose and are not. ``edge`` is a pair of names
    # with an arrow between them and ``instruments`` is a list of them in
    # backticks; both were filed as prose until every identifier in them
    # turned out to be a name this problem declares. A roster is a claim,
    # and this is the one the corpus disagreed with.
    "edge", "instruments",
})

#: A ``said`` key whose value is NOT a name, with what it is instead. The
#: reason each is here is the reason it is not checked yet, and both
#: families have their own root cause rather than a missing line here:
#: a vocabulary member needs a table this package would have to restate
#: (and two of these keys hold English prose, which a verifier must not
#: pin in a repository with a language layer), and a number needs the
#: second record that most of them do not have.
_NOT_NAMES: Mapping[str, str] = {
    "missing": "vocabulary", "assumptions": "vocabulary",
    "method": "vocabulary", "methods": "vocabulary",
    "branch": "vocabulary", "field": "vocabulary",
    "kind": "vocabulary", "source": "vocabulary",
    "target": "vocabulary", "phrase": "prose", "rationale": "prose",
    "note": "prose", "test": "prose",
    "count": "number", "total": "number", "outside": "number",
    "share": "number", "high": "number", "low": "number",
    "lower": "number", "upper": "number", "j": "number", "k": "number",
    "df": "number", "bend": "number", "noise": "number",
    "z_levels": "number", "p": "number",
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def every_said(node: Any, path: tuple = ()) -> Iterator[tuple[str, str, Any]]:
    """Every ``(where, key, value)`` this rule puts a question to.

    The rule's SCOPE, and the only place it is stated. Depth-blind on
    purpose: the depths a gap uses are not written down anywhere here, so
    a new one cannot slip past by being new.

    It yields values of EVERY type, including the empty string. A walk
    that skipped those would be deciding they raise no question, in the
    one code shape that makes a decision look like an absence — and the
    decision would have been wrong: an empty name is a gap saying it is
    about nothing, and no honest answer in the corpus has one. Finding is
    this function's job; judging is the caller's.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = path + (str(key),)
            if key == "said" and isinstance(value, Mapping):
                for inner, said in value.items():
                    yield ".".join(here + (str(inner),)), str(inner), said
            else:
                yield from every_said(value, here)
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from every_said(value, path + (str(i),))


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
