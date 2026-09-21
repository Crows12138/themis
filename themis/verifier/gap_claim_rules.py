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

THE ROSTER, THOUGH, WAS NOT, and that growth is what showed it. It is a
claim about the whole key space, and it was held by a test that fails on
any key THE ANSWER SHAPES produce — which makes its range the corpus, and
the corpus is where its author was standing. A roster written against
answers that reached an estimator is a statement about estimators, and
thirteen keys arrived at once from answers that reached none. Two of them
name variables. The rest gave the families below the two members they were
missing — a claim written in the notation as well as in the problem's
words, and a name from the other register, which is a population rather
than a variable.

It is bound to the STATEMENTS now, at import: every slot a statement a gap
report can carry declares must be in exactly one of the two rosters, and
thirteen were in neither — none of them reachable by any answer the corpus
holds, and a slot in neither is asked by no rule here at all. What that
binding cannot reach is the vocabularies living in the output layer, which
no verifier may import; a test carries that shortfall as a number.

The binding's first catch was a bug in the READING rather than a hole in
the rosters, and its second was what that bug had already cost. ``{{`` is
how a template writes a brace, so a statement that shows a caller the
shape of an argument declares no slot where it looks like it declares
four; read without stripping the escapes the space is five larger, and
four of those five had been classified — the roster widening to satisfy a
demand a bug had made. A gate is worth what it refuses, and a gate whose
demand is wrong is answered by widening the thing it guards.

AND A SLOT'S MEANING IS ITS SENTENCE'S. The rosters are keyed on the name
alone, which the copy question below could not survive: ``target`` is a
population where an answer is transported and a variable in the
statements about a curve and a collider, so one answer per name is right
about one of them and silent on the others. The walk carries the
statement, and the copy table is keyed on the pair, with a wildcard for
the slots whose answer does not turn on the sentence. The rosters were
still keyed on the slot alone, and ``target`` was what that cost: filed as
a vocabulary member, which it is in no sense it has, so the name rule
skipped every site and the twenty-two where it is a variable were asked
by nothing. A slot like that is in neither roster now. What it holds is
declared per statement, and the name rule asks the pair.

Two things kept that from being a table and nothing more. A way past a
gap names its statement under ``route``, which the walk did not read, so
no pair could address the two ways past where ``target`` is a variable.
And the index the binding holds the rosters to listed sentences and
needs but not routes, so no slot a way past declares was bound at all —
four of them are declared nowhere else, and ``scale`` was in no roster.

A gap's own ``said`` was a statement with no name for the same reason,
one container further out. It is the occasion ``IF_PROVIDED`` speaks —
what having the missing thing would buy — under the gap's ``kind``, and
the statement rule has read it so since that rule was written. The walk
read the spellings its author had listed and the index the names of the
sets its author had listed, so the occasion yielded no statement, the
pairs it declares were bound by nothing, and a role it copies from the
question could not be declared one. Both read what the statement rule
reads now: the spellings its carriers give, and the vocabularies
``themis.gaps`` declares.

AND A NAME CAN HAVE A SECOND RECORD. The name rule asks whether a word is
one this problem is written in, and a gap whose intervention is rewritten
from ``x`` to ``y`` answers yes: both are. Where a slot is named after a
role of the question — ``intervention``, ``treatment``, ``target``,
``outcome`` — its statement is almost always written from the question
itself, and the question is on the program, which no answer can edit.
Those slots are in the copy table beside the non-names, held to the
question's own atom. Almost, not always: a longitudinal failure names
the treatment at the time point that failed, and a declaration per
statement says so, rather than the slot's name deciding it.

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

AND A RENDERING IS NOT A NAME, WHICH SAYS WHICH QUESTION TO ASK AND NOT
THAT THERE IS NONE. The three questions below all ask membership: is this
word one of the records the answer holds, the one the rest of its sentence
points at, the one its own gap writes elsewhere. A slot filed as an
expression holds no word for membership to be about — it holds a whole
sentence, assembled by a producer out of a record that is still on this
envelope. Classifying it said the NAME rule cannot read it, and it was
read as saying nothing can: the stratified conditional a transport gap
sends a reader after could be rewritten to any string at all, and every
door took it. The fourth question is not membership. What a producer
printed can be printed AGAIN, from the record it was printed from, and the
two printings compared — which is also how it keeps the rule above, since
a printing that is rebuilt is a printing nobody had to parse.
"""
from __future__ import annotations

import re
from typing import Any, Iterator, Mapping

from .. import gaps as _gaps
from .. import language
from ..types import Atom, VariableDeclaration
from .errors import VerificationError
from .type_reconciliation_rules import _declared_from_scale_domain
from .rules import _atom_label_verifier
from .statement_rules import _CARRIERS

_RULE = "gap_names_check"

#: A slot in a statement's text. ``{{`` and ``}}`` are how a template writes
#: a literal brace, and one of them is a variable name in a counterfactual:
#: ``P(y_x, y'_{{x'}})`` reaches a reader as ``P(y_x, y'_{x'})`` and declares
#: no slot at all. Read without stripping those first, the roster below is
#: asked to classify a slot no statement has, which is the sort of demand a
#: gate makes right before somebody widens the gate to satisfy it.
_SLOT = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)")


def _slots_of(text: str) -> set[str]:
    return set(_SLOT.findall(text.replace("{{", "\0").replace("}}", "\0")))


def statements_and_the_slots_they_declare() -> frozenset[tuple[str, str]]:
    """Every ``(statement, slot)`` a statement a gap report can carry
    declares.

    Derived from the VOCABULARIES rather than from a list of table names,
    because a list of tables is the same kind of claim as the rosters
    themselves: a statement table added beside the others would be
    outside the space while looking like it was inside it. A statement
    is a member of a vocabulary declared to :mod:`themis.language`, and
    every one whose words ``themis.gaps`` holds is one a report's
    statements are spoken from — what a gap describes, what it needs,
    each way past it, what having the missing thing would buy, and the
    words that stand in their holes. A vocabulary's words live in a
    table or on an enum, and both are read.

    It was an index of NAMES until the last of those showed what names
    cannot say. It listed sentences, needs and routes — routes only once
    the space turned out smaller by exactly what a way past declares —
    and read a member's holes out of any table keyed by one of those
    names. A gap's occasion is keyed by the gap's kind, and not every
    table keyed by a kind is spoken: the phrase for what a gap wants
    fills its holes from the gap's provenance, never from a ``said``, so
    adding kinds to the names would have bound a slot nothing carries.
    Which tables are spoken is what a vocabulary is.

    Pairs rather than slots, because a slot whose kind is its sentence's
    is owed an answer for each statement that declares it.
    """
    held = list(vars(_gaps).values())
    found: set[tuple[str, str]] = set()
    for owner in language.VOCABULARIES.values():
        if not any(owner is here for here in held):
            continue
        rows = (owner.items() if isinstance(owner, Mapping) else
                ((member, getattr(member, "words", None))
                 for member in owner))
        for member, words in rows:
            if not isinstance(words, Mapping):
                continue
            for text in words.values():
                if isinstance(text, str):
                    found |= {(str(member), slot)
                              for slot in _slots_of(text)}
    return frozenset(found)


def slots_the_statements_declare() -> frozenset[str]:
    """Every slot a statement a gap report can carry declares."""
    return frozenset(
        slot for _statement, slot in statements_and_the_slots_they_declare())

#: A ``said`` key whose value names variables or the objects they are
#: applied to. Kept beside the roster below so that the two together are a
#: statement about the whole key space, not a list of what occurred to
#: whoever wrote them: :func:`_bind` holds the pair to every slot a
#: statement can declare, so a slot cannot arrive unclassified. What the
#: answer shapes happen to exercise is measured separately, over the wider
#: space that includes the vocabularies this package may not import.
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
    # A wider corpus brought seven more, each of which spells a variable
    # of the problem: the collider a path is blocked at, the candidate
    # weighed for a role, the two proxies a proximal route stands on, the
    # variable a stratum conditions on, the atoms an expression is over,
    # and the features a model was fitted with. They are here because
    # their VALUES are names, not because naming them costs nothing —
    # most of the keys that arrived beside them could also have been
    # added without refusing anything, since a number contains no
    # identifier to be wrong about, and that is a fact about numbers
    # rather than a reason to police one as a name.
    "atoms", "candidate", "collider", "conditioning", "features",
    "outcome_proxy", "treatment_proxy",
    # And four the CORPUS never showed. They are classified from the
    # sentence each belongs to rather than from a value anybody observed,
    # because the roster is bound below to what this build can WRITE and
    # these are statements no answer shape reaches. Each puts its slot in a
    # position a declared name already occupies: the mediator whose
    # distributions a decomposition needs, the variable a framing gap says
    # is short of fields, and the two sets beside ``conditioning`` and
    # ``instrument`` in an independence claim and a LATE. Filing one of
    # these wrongly costs a FALSE REFUSAL rather than a silence, which is
    # why the position has to be read and not guessed.
    "mediator", "predicate", "extras", "given",
})

#: A ``said`` key whose value is NOT a name, with what it is instead.
#:
#: What this roster answers is what KIND of thing fills the slot, and it
#: is worth saying what it does NOT answer, because the two were read as
#: one for a while: a kind is not a reason nothing can hold the value.
#: Three of the keys below have an exact second record on the very same
#: envelope, and :data:`_COPIED_FROM` is where that is now asked. The
#: sentences here describe why each family fails the NAME MEMBERSHIP test
#: this module's first rule applies — nothing more.
#:
#: a VOCABULARY member is not one of the problem's variables (and some of
#: these keys hold English PROSE, which a verifier must not pin in a
#: repository with a language layer); a NUMBER contains no identifier to
#: be wrong about; an EXPRESSION is written in the
#: notation as well as in the problem's words, so the whole-token
#: membership below would refuse an honest one for saying ``P`` or ``do``,
#: and holding it means reading the notation rather than listing a key;
#: and a DOMAIN is a name out of the other register — a population is not
#: a variable, and the words this rule knows are the problem's variables
#: by construction, so filing one as a name refuses every transported
#: answer there is.
#:
#: Two more families arrived with the answers that carry no number. A
#: VALUE is a member of a variable's domain rather than a variable —
#: ``True``, ``0``, ``[False, True]`` — so holding it means reading the
#: declared domains, which is a different table from the problem's words.
#: And a QUOTED word is one the gap is reporting BECAUSE the problem does
#: not have it: ``atom_not_in_graph`` names the offending token so a
#: reader can see which one it was. Filing that as a name would refuse
#: exactly the gap whose whole subject is that the word is not theirs —
#: the membership test would be run against the claim it is reporting.
#:
#: And a DECLARED fragment is a piece of the program's own declaration of
#: the variable its sentence names, read back as it is written there: the
#: known noise a measurement field names, and where a threshold cuts.
#:
#: Both rosters are keyed on the LEAF NAME alone, which is a limit worth
#: stating: ``d`` is Cohen's d under a precision target and would be a
#: variable anywhere a problem declares one, and this table can only hold
#: one answer for the word. Where that limit is met rather than latent the
#: slot is in neither roster, and :data:`_IN_ITS_SENTENCE` says what it
#: holds in each statement that declares it.
_NOT_NAMES: Mapping[str, str] = {
    "missing": "vocabulary", "assumptions": "vocabulary",
    "method": "vocabulary", "methods": "vocabulary",
    "branch": "vocabulary", "field": "vocabulary",
    "kind": "vocabulary",
    "algorithm": "vocabulary",
    "fallback": "vocabulary",
    "phrase": "declared", "rationale": "prose",
    "note": "prose", "test": "prose",
    "count": "number", "total": "number", "outside": "number",
    "share": "number", "high": "number", "low": "number",
    "lower": "number", "upper": "number", "j": "number", "k": "number",
    "df": "number", "bend": "number", "noise": "number",
    "z_levels": "number", "p": "number", "alpha": "number",
    "h": "number", "n": "number", "precision": "number",
    "skew": "number", "strata": "number",
    "formula": "expression", "what": "expression",
    "population": "domain", "source": "domain",
    # Arrived with the wider corpus.
    "bad": "number", "cells": "number", "confidence": "number",
    "control": "number", "d": "number", "f": "number",
    "interval": "number", "level": "number", "level_index": "number",
    "levels": "number", "per_point": "number", "points": "number",
    "statistic": "number", "threshold": "number", "time": "number",
    "treated": "number", "w_levels": "number",
    "drop": "vocabulary", "lost": "vocabulary", "skipped": "vocabulary",
    "wanted": "vocabulary", "winner": "vocabulary", "won": "vocabulary",
    "reason": "prose",
    "cut": "declared", "expression": "expression",
    "quantity": "expression",
    "detail": "domain",
    "arm": "value", "value": "value", "values": "value",
    "atom": "quoted",
    # And nine the corpus never showed, classified from their own sentences
    # for the reason given above the four names. A theta key and the
    # entries theta does hold are written in the notation; the declared
    # domain a column left and the values it left it by are members of a
    # domain; the fields a framing gap is short of and the part of a query
    # an offending atom sits in are vocabulary members; an assumption is
    # the text a reader is asked to settle; and why a route failed, or what
    # an algorithm's assumptions were violated by, is prose.
    #
    # Four more sat here until the escaped brace was read correctly, and
    # came back out. The noisy-measurement statement shows a caller the
    # SHAPE of an argument — ``misclassification={{<name>:
    # {{confusion_matrix, states}}}}`` — which reaches a reader as literal
    # braces and declares no slot at all. Classifying them was this roster
    # widening to satisfy a demand a BUG had made, which is the failure the
    # binding exists to prevent, arriving by way of the binding itself.
    "key": "expression", "have": "expression",
    "domain": "value", "extra": "value",
    "fields": "vocabulary", "part": "vocabulary",
    "assumption": "prose",
    "violations": "prose", "why": "prose",
    # And one only a way past declares, unbound while the index held no
    # routes: the measurement scale a declaration names, a word out of the
    # glossary's vocabulary.
    "scale": "vocabulary",
}

#: A slot whose kind is its STATEMENT'S, declared for each statement.
#:
#: The rosters answer per slot name, and for most slots the name settles
#: it. ``target`` is where it does not. It is the variable an effect is
#: taken on in the two statements about a restriction on a collider, the
#: one about a dose-response curve and the two ways past a conditioned
#: collider; the population an answer is carried to in the statement about
#: transporting it; the name of an ask in the statement about what a
#: mediation decomposition is short of. Filed by name it was a vocabulary
#: member, which it is in none of them, and the name rule asked it in none.
#:
#: So a slot here is in neither roster, and :func:`_bind` holds this table
#: to every statement ``themis.gaps`` declares the slot in: an entry for
#: each, and none for a statement that does not declare it. A statement
#: out of that reach — a gloss written from another layer's vocabulary,
#: where ``target`` can be a distribution — has no entry, and the name
#: rule does not ask it there.
_IN_ITS_SENTENCE: Mapping[tuple[str, str], str] = {
    ("the_conditioning_node_is_a_collider", "target"): "name",
    ("the_sample_is_restricted_on_a_collider", "target"): "name",
    ("the_question_asks_for_a_dose_response_curve", "target"): "name",
    ("ask_the_marginal_effect", "target"): "name",
    ("maybe_it_is_not_a_common_effect", "target"): "name",
    ("transport_rests_on_s_admissibility", "target"): "domain",
    ("the_decomposition_needs_the_mediators_distributions", "target"):
        "expression",
}

_TURNS_ON_THE_SENTENCE: frozenset[str] = frozenset(
    slot for _statement, slot in _IN_ITS_SENTENCE)


def holds_a_name(statement: str | None, slot: str) -> bool:
    """Whether ``slot``, in ``statement``, names a variable of the problem.

    The pair where the slot's kind is its statement's, the roster where it
    is not. A statement with no name, or none this table reaches, gets no
    answer for such a slot, and the name rule does not ask it.
    """
    if slot in _TURNS_ON_THE_SENTENCE:
        return (statement is not None
                and _IN_ITS_SENTENCE.get((statement, slot)) == "name")
    return slot in _NAMES


def _bind() -> None:
    """Every slot this build can write is classified, exactly once.

    The rosters above were held to the keys THE ANSWER SHAPES produce, and
    a roster held to a corpus is a statement about that corpus: its range
    is where its author was standing. Thirteen slots this package can write
    were in neither roster, and a slot in neither is asked by NO rule here
    — the name rule skips what it does not find in the first, and the copy
    rule reads only what it finds in the second, so an unclassified slot is
    silent twice over rather than loudly wrong once.

    Bound to the statements instead. What the answer shapes happen to
    exercise stays worth measuring and a test still measures it, over the
    wider space that includes the vocabularies living in the output layer,
    which no verifier may import. This one covers what can be reached from
    here, and covers it at import: a statement added with a new slot fails
    on the way in.

    And per statement where a slot's kind is its statement's: every
    statement declaring such a slot has an entry saying what it holds
    there, and no entry names a statement that does not declare it.

    And per role: every slot named after a role of the question, in a
    statement that files it as a name, is declared a copy of the
    question or declared not to be one — once, and nothing else is.

    And every stand-in is for a hole a statement declares and copies from
    a record: a stand-in says that record names nothing there, and with no
    record it says nothing anyone can check.
    """
    declared = statements_and_the_slots_they_declare()
    space = {slot for _statement, slot in declared}
    names, not_names = set(_NAMES), set(_NOT_NAMES)
    by_statement = set(_TURNS_ON_THE_SENTENCE)
    unclassified = sorted(space - names - not_names - by_statement)
    if unclassified:
        raise RuntimeError(
            f"slots {unclassified} are declared by a statement a gap report "
            f"can carry and are in no roster, so no rule in this module "
            f"asks about them; say which kind of thing fills each")
    twice = sorted((names & not_names) | (by_statement & (names | not_names)))
    if twice:
        raise RuntimeError(
            f"slots {twice} are filed in more than one roster; the rosters "
            f"answer one question and cannot all be right")
    owed = {pair for pair in declared if pair[1] in by_statement}
    if owed != set(_IN_ITS_SENTENCE):
        raise RuntimeError(
            f"statements {sorted(owed - set(_IN_ITS_SENTENCE))} declare a "
            f"slot whose kind is its statement's and have no entry saying "
            f"what it holds there; entries "
            f"{sorted(set(_IN_ITS_SENTENCE) - owed)} name a statement that "
            f"does not declare it")
    roles = {pair for pair in declared
             if pair[1] in _ROLES and holds_a_name(*pair)}
    copies = {(statement, slot)
              for statement, slots in _COPIES_THE_QUESTION.items()
              for slot in slots}
    either = copies | set(_NOT_THE_QUESTIONS)
    both = sorted(copies & set(_NOT_THE_QUESTIONS))
    if roles != either or both:
        raise RuntimeError(
            f"slots {sorted(roles - either)} are named after a role of the "
            f"question and nothing says whether they copy it; entries "
            f"{sorted(either - roles)} name no such slot; {both} are said "
            f"both ways")
    unread = sorted(pair for pair in _STANDS_IN
                    if pair not in declared or _copied_from(*pair) is None)
    if unread:
        raise RuntimeError(
            f"stand-ins {unread} are for a hole no statement declares, or "
            f"one that copies no record; a stand-in says the record names "
            f"nothing there, and without one it says nothing checkable")


def _methods_the_answer_ran(result: Mapping, _context=None) -> set[str]:
    """Every method this answer says produced a number or an interval."""
    found: set[str] = set()
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping) and row.get("method"):
            found.add(str(row["method"]))
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, Mapping) and estimate.get("method"):
        found.add(str(estimate["method"]))
    return found


def _parameters_the_answer_is_short_of(result: Mapping,
                                       _context=None) -> set[str]:
    """Every parameter this answer's own list of what is missing names.

    Both spellings, because not every channel files a ``key`` — the name
    a row is indexed by ends with it where it does, and a row without one
    is still a row saying which parameter is short.
    """
    found: set[str] = set()
    for row in result.get("missing_information") or ():
        if not isinstance(row, Mapping):
            continue
        said = row.get("said")
        if isinstance(said, Mapping) and said.get("key"):
            found.add(str(said["key"]))
        if row.get("name"):
            found.add(str(row["name"]).split(":")[-1])
    return found


def _assumptions_the_answer_records(result: Mapping,
                                    _context=None) -> set[str]:
    """Every assumption id this answer files, wherever it files it."""
    found: set[str] = set()
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping):
            found |= {str(a) for a in row.get("assumptions") or ()}
    ledger = ((result.get("extensions") or {}).get("assumption_ledger")
              or {}).get("assumptions") or ()
    for row in ledger:
        if isinstance(row, Mapping) and row.get("id"):
            found.add(str(row["id"]))
    return found


#: Where a mediation answer files its branches, and how a caveat spells
#: each. A transcription of the producer's own pair, and the whole of what
#: holding the word costs: a verifier may not import the producer, so it
#: has to be told which key ``CDE`` picks out before it can go looking for
#: that branch's record. Held to the original by test rather than by
#: import. Both extension keys are read because which one a decomposition
#: is filed under is the scheduler's business, not this rule's to assume.
_BRANCH_KEYS: Mapping[str, str] = {"NDE/NIE": "nde_nie", "CDE": "cde"}

_DECOMPOSITIONS: tuple[str, ...] = ("mediation_decomposition",
                                    "mediation_joint_decomposition")


def _the_branch_whose_assumptions_these_are(result: Mapping,
                                            said: Mapping) -> set[str]:
    """The branch of a decomposition whose recorded assumptions are the
    ones this caveat lists.

    Empty where the caveat lists nothing, and empty where no branch on
    this envelope records what it lists -- the record is not there to
    appeal to, and the rule that calls this is silent then. A set rather
    than a word because two branches recording the same premises would be
    two honest answers to the question, and the rule should say so by
    accepting either rather than by picking one.
    """
    listed = str(said.get("assumptions") or "")
    if not listed:
        return set()
    found: set[str] = set()
    for block in _DECOMPOSITIONS:
        branches = (result.get("extensions") or {}).get(block)
        if not isinstance(branches, Mapping):
            continue
        for name, key in _BRANCH_KEYS.items():
            branch = branches.get(key)
            if not isinstance(branch, Mapping):
                continue
            recorded = ", ".join(
                str(one) for one in branch.get("assumptions") or ())
            if recorded and recorded == listed:
                found.add(name)
    return found


def _the_intervals_this_answer_reports(result: Mapping,
                                       _context=None) -> set[str]:
    """How many intervals this answer puts in front of a reader.

    The sentence saying several of them bound one quantity is written out
    of that list -- one caveat per list longer than one -- so the number
    over it and the list under it are one fact. A reader deciding whether
    to go looking for the others is reading this number.
    """
    return {str(len(result.get("bounds_results") or ()))}


def _the_instruments_the_graph_offers(_result: Mapping,
                                      context) -> set[str]:
    """How many variables this graph could offer as an instrument.

    The criterion is the one :func:`themis.verifier.rules
    .unconditional_instrument_holds` states and no more: an edge into the
    treatment, and no open path to the outcome once the treatment's
    outgoing edges are cut. Whether a candidate also has a domain worth
    enumerating is the declaration's business, so a count that disagreed
    with this one would be a count of something else -- which is why the
    set is empty, and the rule silent, for a question whose two ends this
    graph does not both hold.
    """
    from .rules import unconditional_instrument_holds

    graph = getattr(context, "graph", None)
    treatment, outcome = _the_questions_ends(context)
    if graph is None or treatment is None or outcome is None:
        return set()
    if treatment not in graph or outcome not in graph:
        return set()
    bidirected = frozenset(getattr(context, "bidirected", ()) or ())
    return {str(sum(
        1 for candidate in graph.predecessors(treatment)
        if unconditional_instrument_holds(
            graph, bidirected, treatment, outcome, candidate)))}


def _the_target_population_the_question_names(_result: Mapping,
                                              context) -> set[str]:
    """The population the question asks its answer to be carried TO.

    Empty for a question that names none, which is the occasion a
    sentence about it says so with a stand-in rather than a name.
    """
    target = getattr(getattr(context, "query", None), "target_population",
                     None)
    return {str(target)} if target else set()


def _the_source_populations_the_program_names(_result: Mapping,
                                              context) -> set[str]:
    """The populations an answer is carried FROM: the source each
    selection node declares.

    Every selection node names one, so an empty set is a program that
    declared no difference between populations at all — whose one route
    comes from a source nobody named, and whose sentences say so.
    """
    return {str(node.source_population)
            for node in getattr(context, "selection_nodes", ()) or ()
            if getattr(node, "source_population", None)}


def _domains_the_program_declares(result: Mapping, context) -> set[str]:
    """Every population the PROGRAM names, in either role.

    A domain is a name out of the register the name rule does not read —
    its words are the problem's variables by construction — so filing one
    as a name would refuse every transported answer there is. It has a
    roster of its own all the same, and the program is where it lives:
    the query's target, and the source each selection node declares.

    Both at once only where a sentence does not say which a hole is. Where
    it does, the role's own record is asked: read against both, a source
    written as the target and the target as the source was the answer
    carried backwards, and every door took it.
    """
    return (_the_target_population_the_question_names(result, context)
            | _the_source_populations_the_program_names(result, context))


def _ambiguities_the_caller_flagged(result: Mapping, _context) -> set[str]:
    """Every kind of uncertainty the caller's own side-channel reports."""
    found: set[str] = set()
    carried = (result.get("extensions") or {}).get("ambiguities") or ()
    for row in carried:
        if isinstance(row, Mapping) and row.get("kind"):
            found.add(str(row["kind"]))
    return found


#: The two ends of a question, in every spelling a query shape gives them.
#:
#: Read in three places below -- the atom accessors the role roster uses,
#: the pair reader that answers from the program document, and the count
#: of instruments a graph offers -- and written here once, so a shape
#: whose spelling arrives is learnt by all three or by none.
#:
#: The third pair is why this is a list rather than two literals. An
#: effect, an identification and a structural counterfactual say
#: ``intervention``/``target``; a proximal effect says
#: ``treatment``/``outcome``; a counterfactual says
#: ``counterfactual_intervention``/``counterfactual_target`` -- plainly,
#: in its own two fields -- and that pair was in NEITHER reader. The
#: module read the question twice and both copies were blind to the same
#: spelling, so on every counterfactual answer the roster that copies the
#: question answered nothing and said nothing about answering nothing.
_THE_TWO_ENDS: tuple[tuple[str, str], ...] = (
    ("intervention", "target"),
    ("treatment", "outcome"),
    ("counterfactual_intervention", "counterfactual_target"),
)


def _the_questions_atom(context, fields: tuple[str, ...]) -> set[str]:
    """The atom the question keeps under the first of ``fields`` it has,
    spelled both ways a gap spells an atom; empty for a question with none.

    Which fields those are is :data:`_THE_TWO_ENDS`. Both SPELLINGS of the
    atom are the producer's -- most statements carry the predicate, and
    the ones about a declared loop carry the atom as the scheduler labels
    it, ``x()`` for a variable applied to nothing.
    """
    query = getattr(context, "query", None)
    for field in fields:
        part = getattr(query, field, None)
        atom = getattr(part, "atom", part)
        if isinstance(atom, Atom):
            return {atom.predicate, _atom_label_verifier(atom)}
    return set()


def _the_questions_intervention(_result: Mapping, context) -> set[str]:
    """The variable the question intervenes on."""
    return _the_questions_atom(context, tuple(a for a, _b in _THE_TWO_ENDS))


def _the_questions_target(_result: Mapping, context) -> set[str]:
    """The variable the question asks the effect on."""
    return _the_questions_atom(context, tuple(b for _a, b in _THE_TWO_ENDS))


def _the_questions_ends(context):
    """The two atoms themselves, for a reader that walks the graph.

    The accessors above answer in the spellings a gap writes, which is
    what a roster compares against. A graph is keyed by the atoms, so a
    rule that has to walk one needs them rather than their names.
    """
    query = getattr(context, "query", None)
    for first, second in _THE_TWO_ENDS:
        one, two = getattr(query, first, None), getattr(query, second, None)
        one, two = getattr(one, "atom", one), getattr(two, "atom", two)
        if isinstance(one, Atom) and isinstance(two, Atom):
            return one, two
    return None, None


def _the_questions_members(context, field: str) -> set[str]:
    """Every atom the question keeps under ``field``, one or a set, in
    both spellings; empty for a question with no such field."""
    found = getattr(getattr(context, "query", None), field, None)
    atoms = ((found,) if isinstance(found, Atom) else
             tuple(found) if isinstance(found, (tuple, list, frozenset))
             else ())
    return {spelt for atom in atoms if isinstance(atom, Atom)
            for spelt in (atom.predicate, _atom_label_verifier(atom))}


def _the_questions_latent(_result: Mapping, context) -> set[str]:
    """The confounder a proximal question declares nobody measured."""
    return _the_questions_members(context, "latent")


def _the_questions_treatment_proxies(_result: Mapping, context) -> set[str]:
    """The proxies a proximal question puts on the treatment's side."""
    return _the_questions_members(context, "treatment_proxy")


def _the_questions_outcome_proxies(_result: Mapping, context) -> set[str]:
    """The proxies a proximal question puts on the outcome's side."""
    return _the_questions_members(context, "outcome_proxy")


def _the_conditional_as_printed(y: str, x: str, names: str) -> str:
    """The stratified conditional a transporting source is asked for."""
    return f"P({y} | do({x}), {names})"


def _the_transport_formula_as_printed(y: str, x: str, names: str) -> str:
    """How a transporting route prints its own formula, in this
    package's second hand.

    Written here rather than taken from the runtime that printed the
    string on the envelope. Two hands printing one record is a
    comparison; one hand printing it twice agrees with itself whatever it
    says. What a second hand costs is that it can stop recognising the
    first one's work without saying so — a printer that no longer agrees
    goes SILENT rather than loud — and what answers that is a test
    failing when the corpus stops being recognised, not a comment.
    """
    return (f"P*({y} | do({x})) = Σ_{{{names}}} "
            f"{_the_conditional_as_printed(y, x, names)} · P*({names})")


def _the_conditional_this_source_prints(result: Mapping, context,
                                        said: Mapping) -> set[str]:
    """The stratified conditional the source THIS SENTENCE names prints
    for itself, and nothing where there is no such printing to appeal to.

    The sentence says which source it is about, and that word is held to
    the populations the program declares, so which route to read is not
    the answer's to choose. The route carries what it adjusts for and the
    formula it prints over that; the question carries the two ends, which
    no answer can edit. Printed from those and compared to the route's
    own printing: coming out the same is what says the record was read
    the way its producer wrote it, and the conditional inside it is then
    the quantity this gap is short of.

    Silent where it does not come out the same. What a route shows a
    reader rests on a step in the chain, and the rule that holds it there
    is the one to speak when it does not — refusing here would be
    refusing a gap's sentence for a fault in the thing it quotes.
    """
    intervention, target = _the_questions_ends(context)
    if intervention is None or target is None:
        return set()
    y, x = target.predicate, intervention.predicate
    extensions = result.get("extensions")
    block = (extensions.get("transport_identification")
             if isinstance(extensions, Mapping) else None)
    routes = block.get("sources") if isinstance(block, Mapping) else None
    population = str(said.get("population"))
    for route in routes or ():
        if not isinstance(route, Mapping) or not route.get("transportable"):
            continue
        if str(route.get("source_population")) != population:
            continue
        names = ", ".join(
            str(atom.get("predicate"))
            for atom in route.get("adjustment_set") or ()
            if isinstance(atom, Mapping))
        if not names:
            continue
        if _the_transport_formula_as_printed(y, x, names) == route.get(
                "formula_repr"):
            return {_the_conditional_as_printed(y, x, names)}
    return set()


#: The slot names that are roles of the question, and the role each one
#: copies wherever its statement copies one.
_ROLES: Mapping[str, tuple[str, Any]] = {
    "intervention": ("the question's intervention",
                     _the_questions_intervention),
    "treatment": ("the question's intervention",
                  _the_questions_intervention),
    "target": ("the question's target", _the_questions_target),
    "outcome": ("the question's target", _the_questions_target),
    # A proximal question's other three: the confounder nobody measured,
    # and the proxies standing in for it on each side. A proxy role is a
    # set, and a slot naming a proxy names a member of it.
    "latent": ("the question's latent confounder", _the_questions_latent),
    "z": ("the question's treatment-side proxies",
          _the_questions_treatment_proxies),
    "w": ("the question's outcome-side proxies",
          _the_questions_outcome_proxies),
}

#: The statements whose role slots are copies of the question, and which.
#:
#: Read off the producers rather than off the corpus. A caveat about a
#: collider, a dose-response curve and the two ways past a conditioned
#: collider are written from the effect query; the four about whether an
#: intervention is a state or an event, from the query they are about; the
#: loop family from the treatment and outcome of the occasion, which are
#: the question's; the proximal family from the proximal query; and the
#: two diagnostics of a fitted estimate from the columns it was fitted
#: for, which are the question's too. Two of the loop statements are
#: reached by no answer shape, and are written from the same occasion as
#: the rest of their family.
_COPIES_THE_QUESTION: Mapping[str, tuple[str, ...]] = {
    "the_conditioning_node_is_a_collider": ("intervention", "target"),
    "the_sample_is_restricted_on_a_collider": ("intervention", "target"),
    "ask_the_marginal_effect": ("intervention", "target"),
    "maybe_it_is_not_a_common_effect": ("intervention", "target"),
    "the_question_asks_for_a_dose_response_curve": (
        "intervention", "target"),
    "the_intervention_says_neither_state_nor_event": ("intervention",),
    "the_intervention_is_a_state_with_no_time_window": ("intervention",),
    "declare_the_intervention_an_event": ("intervention",),
    "split_the_intervention_in_two": ("intervention",),
    "a_cyclic_model_need_not_have_this_quantity": ("treatment", "outcome"),
    "adjustment_cannot_remove_a_feedback": ("treatment", "outcome"),
    "feedback_loop_needs_an_instrument": ("treatment", "outcome"),
    "feedback_loop_outside_the_simultaneous_case": ("treatment", "outcome"),
    "name_an_instrument_for_the_treatment": ("treatment", "outcome"),
    "resolve_the_loop_in_time": ("treatment", "outcome"),
    "the_number_is_a_single_equations_coefficient": (
        "treatment", "outcome"),
    "the_treatment_is_inside_a_declared_loop": ("treatment", "outcome"),
    "a_test_of_the_null_is_what_is_left": ("treatment", "outcome", "latent"),
    "the_discrete_contrast_needs_two_arms": ("treatment", "outcome"),
    "the_fitted_treatment_bridge_went_negative": ("treatment", "outcome"),
    "the_fitted_treatment_bridge_went_negative_at_a_level": (
        "treatment", "outcome"),
    "the_penalty_moved_it_further_than_noise_did": ("treatment", "outcome"),
    "the_proxies_show_fewer_states_than_the_latent_has": (
        "treatment", "outcome", "latent", "z", "w"),
    "the_proxy_channel_is_singular": ("latent", "z", "w"),
    "the_proxies_are_finer_than_the_declared_cardinality": (
        "latent", "z", "w"),
    "which_levels_are_one_state_is_not_in_the_data": ("z",),
    "declare_a_proxy_coarsening": ("z", "w"),
    "enrich_a_proxy_to_get_a_number": ("z",),
    "use_a_bridge_channel_for_more_than_two_arms": ("treatment",),
    "the_fitted_propensity_leaves_part_of_the_sample_unsupported": (
        "treatment",),
    "the_outcome_model_is_quasi_separated": ("outcome",),
    # And two gaps' own occasions, written from the same value as the
    # statements each carries: the intervention an ill-defined one is
    # about, and the treatment and outcome of a loop that wants an
    # instrument.
    "ill_defined_intervention_versions": ("intervention",),
    "missing_iv_candidate": ("treatment", "outcome"),
}

#: Slots named after a role that are NOT the question's, and what each is
#: instead. The slot's name does not decide it; these are why.
_NOT_THE_QUESTIONS: Mapping[tuple[str, str], str] = {
    ("sequential_exchangeability_fails", "treatment"):
        "the treatment at the time point where the strategy failed",
    ("sequential_exchangeability_fails", "outcome"):
        "the outcome the longitudinal specification declares",
}


#: What a ``said`` value is a COPY OF, and where the record it was copied
#: from lives on the same envelope.
#:
#: The second question, and the reason it is a roster of its own. The two
#: above ask what KIND of thing a value is, and the kind was being read as
#: the answer to whether anything could hold it — "a vocabulary member
#: needs a table this package would have to restate". Measurement says
#: otherwise for three of them: a gap quoting the method an interval came
#: from is quoting ``bounds_results[].method``; the parameter it says is
#: missing is the key ``missing_information`` files it under; the
#: assumptions it lists are the ones that interval records. No table is
#: restated and no membership is tested — these are equalities between two
#: copies of one fact, and the copy a reader is shown is the one nothing
#: was checking.
#:
#: Whether a value can be held is not a fact about its kind. It is a fact
#: about whether a second record of it exists, which has to be asked of
#: each key rather than inferred from what sort of word it is. The keys
#: that stay unheld are the ones where the answer is genuinely no: a
#: RENDERED number (``36.3%`` for 0.363, ``1.089e-229`` for a p-value) is
#: not equal to anything on the envelope, because a rendering puts a
#: formatting step between the value and its spelling and an equality
#: would have to re-derive the producer's format.
#:
#: That reason belongs to the rendering and not to the number, and the
#: sentence was read as though it belonged to the number. A ``count`` is
#: not a rendering. It is ``str`` of a length, and the thing it is the
#: length OF is on the same envelope: the intervals this answer reports,
#: the instruments its graph offers. Asked the way the paragraph above
#: says to ask -- of each key -- both are records.
#:
#: A coined label sat in that sentence too -- "and ``CDE`` is not a copy of
#: anything at all" -- and the half of it that is true was doing the work
#: of the half that is not. No record on the envelope holds the STRING
#: ``CDE``. Three hold what it MEANS: the branch key its gap's provenance
#: cites, and the assumptions the same breath lists, which are one
#: branch's list and never the other's. The record to go looking for is a
#: record of what a value means, and a roster that can only ask after the
#: value reports the difference as no record at all.
#:
#: :data:`_LOCATES` is that second question, and the reason it is a table
#: of its own rather than a row in this one.
#:
#: ``lists`` says the slot spells several at once, comma-separated, and
#: every one of them must be a record.
#:
#: Keyed on (STATEMENT, slot), with ``None`` for a slot whose answer does
#: not turn on which sentence it is in. The first three below are of that
#: kind and were written when this table was keyed on the name alone —
#: which was the limit this module already named, "a key filed by its
#: commonest meaning is unchecked in its other". ``target`` is the
#: instance: a population where an answer is transported, a variable in
#: the statements about a curve and a collider. One answer per name
#: is right about one of those and silent on the rest.
_COPIED_FROM: Mapping[tuple[str | None, str], tuple[str, Any, bool]] = {
    (None, "method"): ("the methods it ran", _methods_the_answer_ran, False),
    (None, "what"): ("the parameters it says it is short of",
                     _parameters_the_answer_is_short_of, False),
    (None, "assumptions"): ("the assumptions it records",
                            _assumptions_the_answer_records, True),
    # The plural of the first, and the one the roster was built without.
    # It says which of the methods a reader already HAS answer this gap,
    # and its producer builds it out of ``bounds_results[].method`` — the
    # same list the singular is read against, joined with commas.
    (None, "methods"): ("the methods it ran", _methods_the_answer_ran, True),
    # Two names out of the other register. A population is not a variable,
    # which is why the name rule cannot ask about them — and the program
    # declares every domain there is, as the query's target and as each
    # selection node's source. Which of the two a hole holds is its
    # sentence's, so it is read against that role; ``population`` falls
    # back to both only in a sentence that does not say.
    (None, "population"): ("the domains the program declares",
                           _domains_the_program_declares, False),
    (None, "source"): ("the source populations the program declares",
                       _the_source_populations_the_program_names, False),
    ("the_source_populations_stratified_conditional_is_missing",
     "population"): ("the source populations the program declares",
                     _the_source_populations_the_program_names, False),
    ("the_target_populations_covariate_distribution_is_missing",
     "population"): ("the target population the question declares",
                     _the_target_population_the_question_names, False),
    # What the CALLER flagged, copied onto the envelope beside the gap
    # that reports it. Both copies are the producer's, which is the shape
    # the first three have too.
    (None, "kind"): ("the uncertainties the caller flagged",
                     _ambiguities_the_caller_flagged, False),
    # And the two counts, each read against the list it counts. Keyed on
    # the sentence, because a count is a count OF something and which
    # something is the sentence's to say: one is the intervals in front of
    # a reader, the other the instruments the graph admits.
    ("several_intervals_bound_the_same_quantity", "count"):
        ("the intervals it reports", _the_intervals_this_answer_reports,
         False),
    ("iv_monotonicity_undeclared", "count"):
        ("the instruments this graph offers",
         _the_instruments_the_graph_offers, False),
    # And the slot whose answer is the sentence's. Under this statement a
    # target is where an answer is being transported TO.
    ("transport_rests_on_s_admissibility", "target"):
        ("the target population the question declares",
         _the_target_population_the_question_names, False),
    # And the slots that copy the QUESTION. That record is on the program
    # rather than the envelope, and it is the one no answer can edit. The
    # slots are names as well, which the name rule asks; being one was
    # never what said whether a second record exists.
    **{(statement, slot): (*_ROLES[slot], False)
       for statement, slots in _COPIES_THE_QUESTION.items()
       for slot in slots},
}

#: What a copied hole holds where the record it copies names nothing: the
#: word its sentence puts there instead, which a reader is shown in place
#: of a name ("<source population>").
#:
#: A hole is one fact whichever half it travels in, and this is the one
#: occasion a producer writes it as a word. Read only where it travels as
#: a ``said``, every copied hole could have its name replaced by any word
#: and a stand-in by another, and the door took each. Read off the
#: producers and held to them by test. Which word stands in is the
#: SENTENCE'S rather than the slot's: a target is the target population in
#: the statement about transporting and the outcome in the one about a
#: curve. A copied hole with no entry is never left to a stand-in.
_STANDS_IN: Mapping[tuple[str, str], Any] = {
    ("transport_rests_on_s_admissibility", "source"):
        _gaps.Unnamed.SOURCE_POPULATION,
    ("transport_rests_on_s_admissibility", "target"):
        _gaps.Unnamed.TARGET_POPULATION,
    ("the_source_populations_stratified_conditional_is_missing",
     "population"): _gaps.Unnamed.POPULATION,
    ("the_target_populations_covariate_distribution_is_missing",
     "population"): _gaps.Unnamed.POPULATION,
    ("the_question_asks_for_a_dose_response_curve", "intervention"):
        _gaps.Unnamed.INTERVENTION,
    ("the_question_asks_for_a_dose_response_curve", "target"):
        _gaps.Unnamed.OUTCOME,
}


def _copied_from(statement: str | None,
                 slot: str) -> tuple[str, Any, bool] | None:
    """The record a hole copies IN THIS STATEMENT, or the general one."""
    return (_COPIED_FROM.get((statement, slot))
            or _COPIED_FROM.get((None, slot)))


#: What a ``said`` value NAMES, where the record it names is the one the
#: rest of its claim was read off.
#:
#: The question the roster above cannot put. Its readers are handed the
#: answer and asked what a slot could legally say, and a locator has no
#: such answer: what the word has to be is whatever the record it picks
#: out says, so it does not exist until the slot BESIDE it has been read.
#: A reader here takes that ``said``, which the walk has been carrying all
#: along and saying so.
#:
#: A branch word is the one this arrived for. ``CDE`` over a caveat says
#: the premises under it are the premises of the controlled direct effect,
#: and the roster above could hold it only by membership in the two words
#: there are -- which refuses a forgery and takes the swap, the one lie
#: this word can tell that reads as honest. Held this way it also holds the
#: list
#: beside it to ONE branch's, where the roster above asks only that each
#: premise be one this answer records somewhere, and both branches' are.
#:
#: Read only where the fact travels as a ``said``. What a locator picks
#: out is the envelope's own spelling of a key, and the other half is
#: where a fact goes to be said in the reader's language.
#:
#: Keyed like the other, with ``None`` for a slot whose answer does not
#: turn on which sentence it is in.
_LOCATES: Mapping[tuple[str | None, str], tuple[str, Any]] = {
    (None, "branch"): ("the branch whose assumptions it lists",
                       _the_branch_whose_assumptions_these_are),
}


def _locates(statement: str | None, slot: str) -> tuple[str, Any] | None:
    """The record a hole NAMES in this statement, or the general one."""
    return _LOCATES.get((statement, slot)) or _LOCATES.get((None, slot))


#: What a ``said`` value is a PRINTING of, where what it prints is a
#: record still on this envelope.
#:
#: The fourth question, and the one the three around it cannot put. All
#: three ask membership — of a roster, of the record another slot names,
#: of what this gap writes elsewhere — and a slot classified as an
#: expression holds no word for membership to be about. It holds a
#: sentence a producer assembled, and what was assembled can be assembled
#: again.
#:
#: Which is also why this lives here rather than beside the block it
#: prints. The frontier that read a fitted diagnostic's sentence put that
#: reading in the module owning the block, because the correspondence it
#: needed — which block speaks which sentence — was already declared
#: there. The correspondence needed here is (statement, slot) to a
#: record, which is what the three tables around this one are, and the
#: word saying WHICH record is the population in the same sentence, held
#: by the first of them.
#:
#: Keyed like the others, with ``None`` for a slot whose answer does not
#: turn on which sentence it is in.
_PRINTED_FROM: Mapping[tuple[str | None, str], tuple[str, Any]] = {
    ("the_source_populations_stratified_conditional_is_missing", "formula"):
        ("what that source's own transport formula prints",
         _the_conditional_this_source_prints),
}


def _printed_from(statement: str | None,
                  slot: str) -> tuple[str, Any] | None:
    """The record this hole is a printing of, in this statement."""
    return (_PRINTED_FROM.get((statement, slot))
            or _PRINTED_FROM.get((None, slot)))


#: What a ``said`` value is a second spelling of ON ITS OWN GAP.
#:
#: The third question, and the one the two above cannot put. Both of them
#: ask whether a value is one of the records the ANSWER holds, and for
#: these the record is not somewhere else on the answer. It is on this
#: gap. A gap is written once and SPEAKS several times — its own occasion,
#: each description, each way past — and a producer with a value in hand
#: puts it in every sentence that needs it. Four measured families, each
#: read off the producer rather than off values that happened to match: a
#: dispatch conflict names two routes and writes each of them as an id and
#: as the trigger that put it there, across seven slots; a proxy
#: coarsening writes the declared cardinality into three sentences; a weak
#: instrument writes the level and the rendered set into two; a treatment
#: with too many arms writes how many into two.
#:
#: Keyed on the statement and never on the slot alone, which is the
#: mistake this module already named: ``level`` is a confidence level in
#: the sentence about an Anderson-Rubin set and a dose in the one about a
#: bridge going negative, and a table filed by a slot's commonest meaning
#: is unchecked in its other -- here it would be worse than unchecked, it
#: would refuse the other outright.
#:
#: The VALUE is the fact and the slot names are where else it is spelt, so
#: one entry covers a fact that travels under two names. What this does
#: not refuse is a SWAP between two slots of one family, and the reason it
#: is not worth more machinery today is measured: none of these slots has
#: a declared vocabulary, so the sweep tells three gross lies about each
#: -- a forged spelling, an empty string, a name neither document uses --
#: and a roster read off the gap refuses all three. The day one of them
#: gains a vocabulary this has to become a pairing, which is what
#: :data:`_LOCATES` exists to hold.
_SPELT_AGAIN_ON_THE_GAP: Mapping[tuple[str, str], tuple[str, frozenset]] = {
    # A dispatch conflict names two routes. Each of them reaches a reader
    # as an id and as the trigger that put it there, and the two ways past
    # say which one they keep and which they drop.
    ("unattempted_layer_due_to_dispatch_conflict", "won"):
        ("the layer that ran", frozenset({"won", "drop"})),
    ("unattempted_layer_due_to_dispatch_conflict", "lost"):
        ("the layer that did not", frozenset({"lost", "drop"})),
    ("only_one_declared_layer_was_run", "won"):
        ("the layer that ran", frozenset({"won", "drop"})),
    ("only_one_declared_layer_was_run", "lost"):
        ("the layer that did not", frozenset({"lost", "drop"})),
    ("only_one_declared_layer_was_run", "winner"):
        ("the route that answered", frozenset({"winner", "wanted"})),
    ("only_one_declared_layer_was_run", "skipped"):
        ("the route that did not", frozenset({"skipped", "wanted"})),
    ("the_result_reflects_one_layer_only", "winner"):
        ("the route that answered", frozenset({"winner", "wanted"})),
    ("the_result_reflects_one_layer_only", "skipped"):
        ("the route that did not", frozenset({"skipped", "wanted"})),
    ("drop_the_other_layer", "wanted"):
        ("the route this way past keeps",
         frozenset({"winner", "skipped", "wanted"})),
    ("drop_the_other_layer", "drop"):
        ("the layer this way past drops", frozenset({"won", "lost", "drop"})),
    ("joint_with_mediation_or_transport", "drop"):
        ("the layer this way past drops", frozenset({"drop"})),
    # The cardinality the caller declared for the latent, in every
    # sentence that has to say it.
    ("the_proxies_are_finer_than_the_declared_cardinality", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    ("which_levels_are_one_state_is_not_in_the_data", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    ("declare_a_proxy_coarsening", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    ("the_proxies_show_fewer_states_than_the_latent_has", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    ("the_proxy_channel_is_singular", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    ("enrich_a_proxy_to_get_a_number", "k"):
        ("the cardinality the caller declared", frozenset({"k"})),
    # A weak instrument's region: the level it was built at and the set
    # itself, said once and offered once.
    ("the_anderson_rubin_set_is_this", "level"):
        ("the level the set was built at", frozenset({"level"})),
    ("the_anderson_rubin_set_is_this", "interval"):
        ("the set itself", frozenset({"interval"})),
    ("use_the_ar_set", "level"):
        ("the level the set was built at", frozenset({"level"})),
    ("use_the_ar_set", "interval"):
        ("the set itself", frozenset({"interval"})),
    # And how many arms the treatment turned out to take.
    ("the_discrete_contrast_needs_two_arms", "levels"):
        ("how many arms the treatment takes", frozenset({"levels"})),
    ("use_a_bridge_channel_for_more_than_two_arms", "levels"):
        ("how many arms the treatment takes", frozenset({"levels"})),
}


def _spelt_again(statement: str | None,
                 slot: str) -> tuple[str, frozenset] | None:
    """Where else on its gap this hole's fact is written, if anywhere."""
    return _SPELT_AGAIN_ON_THE_GAP.get((statement or "", slot))


def _the_gap_also_writes(gap: Mapping, at: tuple, slots: frozenset,
                         here: tuple[str, str]) -> set[str]:
    """Every value this gap writes under one of ``slots``, bar this one."""
    return {str(value)
            for where, _statement, said in every_said_mapping(gap, at)
            for key, value in said.items()
            if str(key) in slots and (where, str(key)) != here}


def _the_question_asked(program: Mapping) -> tuple[str | None,
                                                   str | None]:
    """The predicate intervened on and the predicate asked about.

    Both or neither: a query shape that spells only one of the two is
    a question this reader cannot answer from, and answering from
    half of it would make every variable that is not the half it
    found into one the question gives no role — which is a claim, and
    the wrong one.
    """
    for statement in program.get("statements") or ():
        query = statement.get("query") if isinstance(
            statement, Mapping) else None
        if not isinstance(query, Mapping):
            continue
        for first, second in _THE_TWO_ENDS:
            intervention = ((query.get(first) or {})
                            .get("atom") or {}).get("predicate")
            target = ((query.get(second) or {})
                      .get("atom") or {}).get("predicate")
            if intervention and target:
                return str(intervention), str(target)
    return None, None


def _the_role_the_question_gives(program: Mapping,
                                name: str) -> set[str] | None:
    """Which side of the question that variable is on.

    The question decides exactly two of this set's words and decides
    them completely: the predicate it intervenes on IS the exposure
    and the one it asks about IS the outcome, so a gap calling either
    of them anything else is telling a reader about a variable that
    is missing nothing. The other two words are properties of the
    GRAPH rather than of the question, so for any other name what the
    question says is that it is neither of its own two.
    """
    intervention, target = _the_question_asked(program)
    if intervention is None or target is None:
        return None
    if name == intervention:
        return {_EXPOSURE}
    if name == target:
        return {_OUTCOME}
    return {str(member) for member
            in language.VOCABULARIES[_QUERY_ROLE]} - {_EXPOSURE,
                                                      _OUTCOME}


def _the_scale_that_column_was_declared_at(
        program: Mapping, column: str) -> set[str] | None:
    """What the PROGRAM declares that column is measured on.

    The answer records the same fact, in the reconciliation check the
    way past was written from, and reading it there would have made
    this rule speak whenever the RECORD was the forgery — pointing at
    the gap, which is honest in that case, and standing in front of
    the stronger reason, which is that the record is not what the
    program declared. The program is the copy no answer can edit, and
    the block is held equal to it elsewhere.

    Resolved rather than read: a declaration says a scale or says a
    domain, and which of the two it said is not a fact about the
    column. The resolution is the reconciliation rule's own, asked
    here of the same pair.
    """
    declaration = _declarations(program).get(column)
    if declaration is None:
        return None
    scale = _declared_from_scale_domain(declaration.get("scale"),
                                       declaration.get("domain"))
    return {scale} if scale else None


#: The fields of a declaration that say how its variable was measured, and
#: the noises a measurement is known to carry. Restated from the producer,
#: which no verifier may import, and held equal to it by test: what a gap
#: may call a known noise is the producer's list, and a list of this
#: module's own would be judging a claim the gap does not make.
_HOW_IT_WAS_MEASURED: tuple[str, ...] = ("measurement", "observability")
_KNOWN_NOISES: tuple[str, ...] = (
    "self-report",
    "self report",
    "self-reported",
    "self reported",
    "questionnaire",
    "ffq",
    "food-frequency",
    "food frequency",
    "24h recall",
    "24-h recall",
    "24 hour recall",
    "24-hour recall",
    "dietary recall",
    "single-occasion",
    "single occasion",
    "single visit",
    "single measurement",
    "single reading",
    "office reading",
    "proxy",
    "surrogate",
    "自报告",
    "自我报告",
    "自报",
    "回忆",
    "问卷",
    "单次",
    "单次测量",
    "代理",
)


def _known_noises_written_in(text: object) -> set[str]:
    """Every known noise a declared text names, spelt as the text spells it.

    Matched without regard to case, as the producer matches, and read back
    in the text's own letters: a quotation is what the user wrote, and
    ``FFQ`` is not ``ffq``. Every one the text names, rather than the first
    the list happens to reach — which of several true quotations a gap
    shows is its producer's choice, and refusing the others would refuse a
    true sentence.
    """
    if not isinstance(text, str):
        return set()
    return {found.group(0) for noise in _KNOWN_NOISES
            for found in re.finditer(re.escape(noise), text, re.IGNORECASE)}


def _the_fields_that_name_a_known_noise(program: Mapping,
                                        column: str) -> set[str] | None:
    """Which of the fields saying how that column was measured name a
    known noise."""
    declaration = _declarations(program).get(column)
    if declaration is None:
        return None
    return {field for field in _HOW_IT_WAS_MEASURED
            if _known_noises_written_in(declaration.get(field))}


def _the_noises_that_field_names(program: Mapping, column: str,
                                 field: str) -> set[str] | None:
    """The known noises that field of that column's declaration names.

    Empty for a field that does not say how the column was measured: a
    ``proxy`` in its time window is not a noisy measurement.
    """
    declaration = _declarations(program).get(column)
    if declaration is None:
        return None
    if field not in _HOW_IT_WAS_MEASURED:
        return set()
    return _known_noises_written_in(declaration.get(field))


def _the_cut_that_column_was_declared_with(program: Mapping,
                                          column: str) -> set[str] | None:
    """Where that column's declaration cuts it, as the declaration says."""
    declaration = _declarations(program).get(column)
    if declaration is None:
        return None
    cut = declaration.get("threshold")
    return {str(cut)} if cut else set()


#: What a fact about the thing its own sentence NAMES is read against: the
#: program's record filed under that name.
#:
#: The table above asks whether a second record of a value exists. It
#: was only ever asked of ``said``, and which half a fact travels in
#: is decided by the fact's own type — a value rendered the same in
#: every language goes in one, a value that is itself a token in the
#: other — which says nothing at all about whether anything records
#: it. So a fact that happened to need translating fell out of every
#: audit here: 21 answers say which scale a column should be measured
#: on and every one of them could say a different one.
#:
#: Indexed rather than global, which is the difference between this
#: table and the one above. A fact here is about the thing its own
#: sentence already NAMES, so the record to read it against is the
#: one filed under that name — the second element says which ``said``
#: keys carry it, in the order the reader takes them. The unindexed
#: version would pass on this corpus, every answer's reconciliation
#: block declaring exactly one scale, and it would be passing because
#: of the corpus rather than because of the record.
#:
#: And read in both halves, which this table was not either. Written for
#: the words, it was walked over the words, and the same kind of fact
#: travelling as a ``said`` was read by nothing that knew which variable it
#: was about: the known noise a measurement field names and where a
#: threshold cuts could each be anything, and the field naming the noise
#: was held only to being a field some declaration can have. The half a
#: fact travels in decides nothing here, from either side.
_QUERY_ROLE = "query_role"
_EXPOSURE = "exposure"
_OUTCOME = "outcome"

#: A row here was held at import against the slots :func:`_bind` knows,
#: and that space answers a different question: it keeps the vocabularies
#: whose words live in ``themis.gaps``, which is where the WORDS are and
#: not what decides whether a report carries the statement. Measured, a
#: gap report carries seventeen vocabularies and that space sees four of
#: them — so "no statement this build can write has that slot" was said
#: of a slot nineteen answers carry. Whether a row is reached is asked of
#: the answers instead, by test, which is the question it was always.
_ABOUT_WHAT_IT_NAMES: Mapping[tuple[str | None, str],
                              tuple[str, tuple[str, ...], Any]] = {
    (None, "scale"): ("the scale that column was declared at",
                      ("variable",),
                      _the_scale_that_column_was_declared_at),
    (None, "role"): ("the role the question gives it",
                     ("variable",), _the_role_the_question_gives),
    # A noisy-measurement gap lists one of these per variable: which field
    # of its declaration names a known noise, and the noise, quoted.
    ("a_field_names_a_known_noise", "field"): (
        "the fields saying how it was measured that name a known noise",
        ("variable",), _the_fields_that_name_a_known_noise),
    ("a_field_names_a_known_noise", "phrase"): (
        "the known noises that field names, as it writes them",
        ("variable", "field"), _the_noises_that_field_names),
    # And a dichotomised measure, where its declaration cuts it.
    ("a_threshold_cut_it_in_two", "cut"): (
        "the threshold it was declared with",
        ("variable",), _the_cut_that_column_was_declared_with),
}

_bind()

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


#: The field a statement is named by in each container under a report:
#: the spellings the statement rule's carriers give there, and the
#: generic ``token`` a glossed word names itself by. ``kind`` last, being
#: the one spelling other blocks use for something else.
_NAMED_BY: tuple[str, ...] = ("token",) + tuple(sorted(
    {spelling for path, (spelling, _vocabulary) in _CARRIERS.items()
     if path.startswith("data_gap_report.")},
    key=lambda spelling: (spelling == "kind", spelling)))


def _every_statement(
    node: Any, path: tuple = (),
) -> Iterator[tuple[str, str | None, Mapping]]:
    """Every statement under a report, its name, and where it sits.

    The walk the questions below share. A statement is recognised by
    carrying either half — a fact that needs translating travels as a
    word and one that does not travels as a said, and a statement is
    no less a statement for having only one kind of fact this time.
    """
    if isinstance(node, Mapping):
        if any(isinstance(node.get(half), Mapping)
               for half in ("said", "words")):
            spoken = next((node.get(spelling) for spelling in _NAMED_BY
                           if node.get(spelling)), None)
            yield (".".join(path),
                   str(spoken) if spoken else None, node)
        for key, value in node.items():
            if key != "said":
                yield from _every_statement(value, path + (str(key),))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _every_statement(value, path + (str(i),))


def every_said_mapping(
    node: Any, path: tuple = (),
) -> Iterator[tuple[str, str | None, Mapping]]:
    """Every ``said`` mapping under a report, which statement it belongs to,
    and where it sits.

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

    And it yields the statement's own name, which was in hand at every
    yield here and was being thrown away. That is why the rosters below
    could only ever be keyed on a slot's NAME, and the module said so:
    "a key filed by its commonest meaning is unchecked in its other". A
    slot's meaning is its sentence's. ``target`` is a population in the
    statement about transporting an answer and a variable in the five
    about a dose-response curve and a collider, and one answer per name
    can only be right about one of those. Carried, a rule may key on the
    pair; and a slot whose meaning does not turn on the sentence is
    written once, against no sentence at all.

    Which key names a statement is the statement rule's to say, and it
    says it for every container under a report: a description names its
    ``sentence``, a way past its ``route``, a gap's own occasion its
    ``kind``, and a glossed word names itself by ``token``. Read off a
    list of this walk's own, two of those went missing in turn — every
    way past a statement with no name, then every occasion — so the
    spellings are read off the carriers. A ``said`` beside none of them
    yields ``None``.
    """
    for where, spoken, statement in _every_statement(node, path):
        said = statement.get("said")
        if isinstance(said, Mapping):
            yield f"{where}.said" if where else "said", spoken, said


def every_word_mapping(
    node: Any, path: tuple = (),
) -> Iterator[tuple[str, str | None, Mapping, Mapping]]:
    """The same walk, for the half a fact travels in when it is a word.

    Hands over the ``said`` beside it as well, because a word here is
    about the thing the same sentence names and the name is in the
    other half. The two are one claim, and a walk that yielded either
    alone could not put them together.
    """
    for where, spoken, statement in _every_statement(node, path):
        words = statement.get("words")
        if isinstance(words, Mapping):
            said = statement.get("said")
            yield (f"{where}.words" if where else "words", spoken,
                   words, said if isinstance(said, Mapping) else {})


def every_said(node: Any, path: tuple = ()) -> Iterator[tuple[str, str, Any]]:
    """Every ``(where, key, value)`` the name rule puts a question to.

    It yields values of EVERY type, including the empty string. A walk
    that skipped those would be deciding they raise no question, in the
    one code shape that makes a decision look like an absence — and the
    decision would have been wrong: an empty name is a gap saying it is
    about nothing, and no honest answer in the corpus has one. Finding is
    this function's job; judging is the caller's.
    """
    for where, _statement, said in every_said_mapping(node, path):
        for inner, value in said.items():
            yield f"{where}.{inner}", str(inner), value


def names_said(report: Any) -> Iterator[tuple[str, Any]]:
    """Every ``(where, value)`` under a report whose statement files the
    slot as a name — the leaves the name rule asks, and only those."""
    for said_at, statement, said in every_said_mapping(report):
        for key, value in said.items():
            if holds_a_name(statement, str(key)):
                yield f"{said_at}.{key}", value


def _the_problems_atoms(context) -> set:
    atoms = set(context.graph.nodes)
    if context.theta is not None:
        atoms |= set(context.theta.domains)
    for pair in getattr(context, "bidirected", ()) or ():
        atoms |= set(pair)
    return atoms


def words_the_problem_uses(context) -> set[str]:
    """Every word the verifier knows this problem is written in.

    Predicates and the objects they are applied to, from every source the
    context has: an estimation route's graph carries the variables while
    its theta is empty, a probability query's theta carries them while its
    graph — built from the cause statements — has no nodes at all, and a
    latent pair may name an atom that is in neither. Asking one source
    reads "took part in no edge" as "does not exist".
    """
    words: set[str] = set()
    for atom in _the_problems_atoms(context):
        words.add(atom.predicate)
        for term in getattr(atom, "args", ()) or ():
            name = getattr(term, "name", None)
            if name:
                words.add(str(name))
    return words


def words_its_names_are_spelt_with(context) -> set[str]:
    """Every word a name this problem has is written with.

    A name is an atom as the envelope spells it, and on a program
    unrolled in time the spelling says when: ``m(me)@t-1``. So the words
    of the names are the problem's words and the notation for a time.
    Kept apart from :func:`words_the_problem_uses` rather than folded into
    it, because its other reader asks for a variable to measure, and
    ``t`` is not a variable.
    """
    return {word for atom in _the_problems_atoms(context)
            for word in _IDENT.findall(_atom_label_verifier(atom))}


def verify_gap_quotes(result: Mapping, context) -> None:
    """Every fact a gap QUOTES back at a reader, against the record it
    was read from.

    The sentence rule holds a statement's slot NAMES to the holes its own
    token declares, so a fact with nowhere to go and a hole with no fact
    are both caught. Neither question is about what is IN the slot, and
    the slot is the whole of what a reader sees: the sentence arrives
    assembled, with ``manski_natural`` and ``P(survival=False|treatment=
    False)`` already substituted in. A gap could name the method of an
    interval this answer never computed, or say it is short of a
    parameter its own list of missing things does not have, and every key
    still lined up.

    Silent where the record is not there to appeal to. That is not a
    convenience: a report can name a method on an answer that carries no
    interval block at all, and inventing the roster out of the gap
    sentences would be reading the authority off the thing being judged.

    Asked of the STATEMENT a fact belongs to, not of the slot's name
    alone. A slot's meaning is its sentence's, and a table with one answer
    per name is right about a slot's commonest sentence and silent in the
    others. Takes the context for the same reason ``verify_gap_names``
    does: some rosters are the program's, not the answer's — a population
    is a name out of the register the name rule cannot read, and the
    variable a statement copies from the question is the question's.

    And asked of the hole whichever half it travels in. Where the record
    names nothing, a producer writes the hole as a WORD, the stand-in its
    sentence says instead; a walk over ``said`` alone read every hole
    except the ones written that way, so any name could become a stand-in
    and any stand-in another. A word in a copied hole is accepted only as
    the stand-in its sentence declares, and only where the record names
    nothing.

    And then asked of the GAP, which is the third question and the one the
    walk had to widen for. ``every_said_mapping`` yields the mapping and
    not its leaves so that a caller asking about one key can see the keys
    beside it -- and the keys beside it stopped at the edge of the
    sentence, while a gap speaks several times. Its own occasion, each
    description, each way past: a producer with one value in hand puts it
    in every one that needs it, and nothing compared the copies. So this
    question is asked of each gap in turn, which is also what says what it
    is about: the record being appealed to is not somewhere on the answer,
    it is this gap. Silent where the gap says a thing only once, for the
    reason the paragraph above gives -- there is nothing to appeal to, and
    a rule that refused there would be refusing a sentence for being
    alone.

    And asked of a slot that holds no word at all. A hole can arrive
    filled with a whole RENDERING — an estimand assembled out of the
    question's two ends and what a route adjusts for — and the three
    questions above are membership, which such a slot has no word to
    answer. It is read by printing the record again and comparing the
    printings, and the sentence itself says which record: the population
    beside it, held to the ones the program declares by the first of
    them. Silent where the printing does not come out as the record's
    own, for the reason the paragraph above gives.

    Returns ``None`` on accept, including when there is no report.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    rosters: dict[str, set] = {}

    def recorded(entry: tuple[str, Any, bool]) -> set:
        says, build, _lists = entry
        if says not in rosters:
            rosters[says] = build(result, context)
        return rosters[says]

    for where, statement, said in every_said_mapping(report):
        for key, value in said.items():
            names = _locates(statement, str(key))
            if names is not None:
                says, read = names
                picked = read(result, said)
                if picked and str(value) not in picked:
                    raise VerificationError(
                        f"a gap says {value!r} where it names {says} (at "
                        f"{where}.{key}), and the record the rest of its "
                        f"sentence was read off is {sorted(picked)}'s. This "
                        f"word is the only part of the sentence that says "
                        f"which record the rest of it came from, so a "
                        f"reader taking the sentence for what it says "
                        f"takes it for the wrong one",
                        step_index=None, rule=_RULE,
                    )
            printing = _printed_from(statement, str(key))
            if printing is not None:
                says, printer = printing
                again = printer(result, context, said)
                if again and str(value) not in again:
                    raise VerificationError(
                        f"a gap sends a reader after {value!r} (at "
                        f"{where}.{key}), and {says} is {sorted(again)}. "
                        f"The sentence reaches them with that estimand "
                        f"already assembled, so what they are told to go "
                        f"and get is not the quantity this answer would "
                        f"use if they came back with it",
                        step_index=None, rule=_RULE,
                    )
            entry = _copied_from(statement, str(key))
            if entry is None:
                continue
            says, _build, lists = entry
            known = recorded(entry)
            if not known:
                continue
            spelt = ([p.strip() for p in str(value).split(",")] if lists
                     else [str(value)])
            for one in spelt:
                if one in known:
                    continue
                raise VerificationError(
                    f"a gap tells a reader about {one!r}, and {says} are "
                    f"{sorted(known)} (at {where}.{key} = {value!r}). The "
                    f"sentence reaches them with that word already "
                    f"substituted in, so they are sent after something "
                    f"this answer never did",
                    step_index=None, rule=_RULE,
                )
    for index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, Mapping):
            continue
        at = ("gaps", str(index))
        for where, statement, said in every_said_mapping(gap, at):
            for key, value in said.items():
                also = _spelt_again(statement, str(key))
                if also is None:
                    continue
                about, under = also
                elsewhere = _the_gap_also_writes(gap, at, under,
                                                 (where, str(key)))
                if not elsewhere or str(value) in elsewhere:
                    continue
                raise VerificationError(
                    f"a gap says {about} is {value!r} at {where}.{key}, and "
                    f"says it is {sorted(elsewhere)} in another of its own "
                    f"sentences. One occasion is being described more than "
                    f"once, from one value the producer had in hand, and a "
                    f"reader who reads two of those sentences is reading "
                    f"one fact twice",
                    step_index=None, rule=_RULE,
                )
    for where, statement, words, _said in every_word_mapping(report):
        for key, word in words.items():
            entry = _copied_from(statement, str(key))
            if entry is None:
                continue
            says = entry[0]
            stand_in = _STANDS_IN.get((statement or "", str(key)))
            if stand_in is None or word != language.state(stand_in):
                owed = ("" if stand_in is None
                        else f", which here is {str(stand_in)!r}")
                raise VerificationError(
                    f"a gap puts the word {word!r} where it quotes {says} "
                    f"(at {where}.{key}). That hole holds a name out of the "
                    f"record, or the one word its sentence says when the "
                    f"record names nothing{owed}",
                    step_index=None, rule=_RULE,
                )
            known = recorded(entry)
            if known:
                raise VerificationError(
                    f"a gap tells a reader the {key} here has no name, and "
                    f"{says} are {sorted(known)} (at {where}.{key}). A "
                    f"reader is handed a placeholder where the answer had "
                    f"the name",
                    step_index=None, rule=_RULE,
                )


def verify_gap_names(result: Mapping, context) -> None:
    """Every name a gap says must be a name this problem has.

    Two questions live here and they do not share a prerequisite. Whether
    the slot was filled in AT ALL is about the value and nothing else.
    Whether what fills it is one of THIS problem's names needs the
    problem's names, and a problem may report none — it declares its
    variables, causes nothing and carries no data — leaving nothing for a
    word to be a member of.

    So the decline is written on the second question rather than above
    both. Guarding the pair with one early return let an emptied name
    through on every problem that reports no names, while the refusal it
    escaped says in its own words that an empty name is a claim about the
    value: nothing in that sentence was ever about the problem's
    vocabulary.

    Which slots name a variable is asked of the statement a slot sits in,
    as the copy rule asks it. ``target`` names one in five statements and
    not in the other two, and read by its name alone it was asked in none.

    Returns ``None`` on accept, including when there is no report. Raises
    ``VerificationError`` naming the leaf and the word.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    known = words_its_names_are_spelt_with(context)
    for where, value in names_said(report):
        if not isinstance(value, str) or not value.strip():
            raise VerificationError(
                f"a gap says which variable it is about and says nothing "
                f"there: {where} = {value!r}. An empty name is not an "
                f"absent claim — the sentence a reader gets has a hole "
                f"where the variable goes",
                step_index=None, rule=_RULE,
            )
        if not known:
            continue
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

    And every other fact a statement gives about the variable it names —
    the scale to measure it on, the side of the question it is on, which
    field of its declaration names a known noise and the noise, where a
    threshold cuts it — against the program's declaration of that
    variable, in whichever half the fact travels. See
    :data:`_ABOUT_WHAT_IT_NAMES`.

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
        for where, _statement, said in every_said_mapping(gap):
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

    for where, statement, carried in _every_statement(report):
        held = carried.get("said")
        said = held if isinstance(held, Mapping) else {}
        words = carried.get("words")
        facts = [("said", key, value) for key, value in said.items()]
        if isinstance(words, Mapping):
            facts += [("words", key, one.get("token"))
                      for key, one in words.items()
                      if isinstance(one, Mapping)]
        for half, key, value in facts:
            row = (_ABOUT_WHAT_IT_NAMES.get((statement, str(key)))
                   or _ABOUT_WHAT_IT_NAMES.get((None, str(key))))
            if row is None:
                continue
            says, named_by, read = row
            about = [name for name in (said.get(k) for k in named_by)
                     if isinstance(name, str) and name]
            if len(about) != len(named_by):
                continue
            known = read(program, *about)
            if known is None:
                continue
            spelt = "" if value is None else str(value)
            if spelt in known:
                continue
            at = f"{where}.{half}.{key}" if where else f"{half}.{key}"
            raise VerificationError(
                f"a gap tells a reader {spelt!r} about "
                f"{'.'.join(about)!r}; {says}: {sorted(known)} (at {at}). "
                f"It is not a label beside the sentence — it is assembled "
                f"into it — so a reader is told something about that column "
                f"the program never declared",
                step_index=None, rule=_SUBJECT,
            )
