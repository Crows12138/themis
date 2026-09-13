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

import dataclasses
import re
from typing import Any, Iterator, Mapping

from .. import gaps as _gaps
from ..types import VariableDeclaration
from .errors import VerificationError

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

    Derived from the INDEX rather than from a list of table names, because
    a list of tables is the same kind of claim as the rosters themselves:
    a statement table added beside the others would be outside the space
    while looking like it was inside it. ``BY_SENTENCE``, ``BY_NAME`` and
    ``BY_ROUTE`` are what say which members a report's statements can be —
    what a gap describes, what it needs, and each way past it — and a
    member's text is wherever it is written.

    The ways past were not in it. The space was smaller by exactly what
    only a way past declares, and one of those slots was in no roster:
    the index was a claim about which statements exist, and its range was
    the two kinds its author had in mind.

    Pairs rather than slots, because a slot whose kind is its sentence's
    is owed an answer for each statement that declares it.
    """
    known = {str(member) for member in _gaps.BY_SENTENCE.values()}
    known |= {str(member) for member in _gaps.BY_NAME.values()}
    known |= {str(member) for member in _gaps.BY_ROUTE.values()}
    found: set[tuple[str, str]] = set()
    for name in dir(_gaps):
        table = getattr(_gaps, name)
        if not (name.isupper() and isinstance(table, dict)):
            continue
        for member, words in table.items():
            if str(member) not in known:
                continue
            texts = words.values() if isinstance(words, dict) else [words]
            for text in texts:
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
    "kind": "vocabulary", "source": "vocabulary",
    "algorithm": "vocabulary",
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
    "cut": "expression", "expression": "expression",
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


_bind()

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


def _fields_a_declaration_has(_result: Mapping, _context) -> set[str]:
    """Every operationalisation field a variable declaration can carry.

    Read off the type rather than listed, so a field added to a
    declaration is one a gap may name from that day and not from the day
    somebody remembered to add it here.
    """
    return {field.name for field in dataclasses.fields(VariableDeclaration)}


def _domains_the_program_declares(_result: Mapping, context) -> set[str]:
    """Every population the PROGRAM names, in either role.

    A domain is a name out of the register the name rule does not read —
    its words are the problem's variables by construction — so filing one
    as a name would refuse every transported answer there is. It has a
    roster of its own all the same, and the program is where it lives:
    the query's target, and the source each selection node declares.
    """
    found: set[str] = set()
    target = getattr(getattr(context, "query", None), "target_population",
                     None)
    if target:
        found.add(str(target))
    for node in getattr(context, "selection_nodes", ()) or ():
        source = getattr(node, "source_population", None)
        if source:
            found.add(str(source))
    return found


def _ambiguities_the_caller_flagged(result: Mapping, _context) -> set[str]:
    """Every kind of uncertainty the caller's own side-channel reports."""
    found: set[str] = set()
    carried = (result.get("extensions") or {}).get("ambiguities") or ()
    for row in carried:
        if isinstance(row, Mapping) and row.get("kind"):
            found.add(str(row["kind"]))
    return found


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
#: rendered number (``36.3%`` for 0.363, ``1.089e-229`` for a p-value) is
#: not equal to anything on the envelope, and a coined label (``CDE``) is
#: not a copy of anything at all.
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
    # What a framing gap says a declaration is short of. Not a copy of
    # anything on the envelope: the roster is the declaration's own field
    # names, which are a closed set this package can read off the type.
    (None, "field"): ("the fields a declaration has",
                      _fields_a_declaration_has, False),
    # Two names out of the other register. A population is not a variable,
    # which is why the name rule cannot ask about them — and the program
    # declares every domain there is, as the query's target and as each
    # selection node's source.
    (None, "population"): ("the domains the program declares",
                           _domains_the_program_declares, False),
    (None, "source"): ("the domains the program declares",
                       _domains_the_program_declares, False),
    # What the CALLER flagged, copied onto the envelope beside the gap
    # that reports it. Both copies are the producer's, which is the shape
    # the first three have too.
    (None, "kind"): ("the uncertainties the caller flagged",
                     _ambiguities_the_caller_flagged, False),
    # And the slot whose answer is the sentence's. Under this statement a
    # target is where an answer is being transported TO.
    ("transport_rests_on_s_admissibility", "target"):
        ("the domains the program declares",
         _domains_the_program_declares, False),
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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

    Three keys name a statement, one to a container: a description says
    ``sentence``, a way past says ``route``, a glossed word says
    ``token``. Reading two of them, every way past was a statement with
    no name. A gap's own ``said`` names none, and yields ``None``.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = path + (str(key),)
            if key == "said" and isinstance(value, Mapping):
                spoken = (node.get("token") or node.get("sentence")
                          or node.get("route"))
                yield (".".join(here),
                       str(spoken) if spoken else None, value)
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
    does: two of the rosters are the program's, not the answer's, and a
    population is a name out of the register the name rule cannot read.

    Returns ``None`` on accept, including when there is no report.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    rosters: dict[str, set] = {}
    for where, statement, said in every_said_mapping(report):
        for key, value in said.items():
            entry = (_COPIED_FROM.get((statement, str(key)))
                     or _COPIED_FROM.get((None, str(key))))
            if entry is None:
                continue
            says, build, lists = entry
            if says not in rosters:
                rosters[says] = build(result, context)
            known = rosters[says]
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
    known = words_the_problem_uses(context)
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
