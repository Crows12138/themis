"""Every leaf of the envelope, asked whether anything holds it.

The sweep that produced #515 ran on one answer shape out of forty-four, so
this file was written to run it on all of them: each estimator writes its
own blocks, and one stratified-Wald answer has none of a propensity
summary's leaves, or a dose-response curve's, or a four-way split's. That
fixed the rows.

It did not fix the columns, and for twelve frontiers nobody noticed,
because a scope is invisible in a passing test. The sweep read
``result["numeric_estimate"]`` while its name said "no leaf a reader is
shown" and this paragraph said "whatever the envelope carries": **1560 leaf
shapes of the 7568 the envelope then had**. A reader is shown the bounds
rows, the gap report, the
assumption ledger, the investigation requests and the audit footer, and the
run records its own inference inputs so that a verifier can reason about
reproducibility — none of it had been bent even once. So the declared
remainder, whose entire value is that it is not the producer's word, was a
statement about one block wearing the clothes of a statement about the
answer. And every frontier picked from its output was necessarily a
frontier inside that block: the instrument had been steering the work.

Asked of the whole envelope, 1671 leaf shapes survived that first sweep.
Among them the identification formula — which could then be deleted
outright on every answer carrying one — the run's own sample size and draw
count, whether a bounds row calls itself uninformative, whether a ledger
premise calls itself testable, and which intervention a data gap says it
is about.

That is not a list of bugs this file fixes. It is a denominator this file
makes impossible to lose: the remainder is declared in
``fixtures/unwitnessed_leaves.json``, and a leaf leaves that file only by
being closed or by being gone — the field deleted, because the fact it
recorded is already recorded where a rule and a reader reach it. A leaf
that appears in it without being added deliberately is a new hole, and
this test says its name.

What the remainder is right now is not written here. It is written in that
file, and asserted once below — a count restated in prose is a copy that
states no relationship to the thing it copies, and this repository has
already found what that costs. The SCOPE is asserted beside it, for the
reason this paragraph exists: a narrowing is a passing test.

WHAT THIS TEST TRUSTS, and what each piece of trust cost when it was
examined.

The snapshot: sixty-four (program, result) pairs harvested from the suite
by ``harvest_answer_shapes.py``. A snapshot is a copy, so it states a
relationship to what it copies — every pair is verified honestly before it
is swept, and a producer that has moved away from the snapshot fails there
rather than quietly sweeping a fossil.

There were forty-four, and the missing twenty are the same defect as the
columns above, one axis over. The collector watched ``kernel.estimate``
and keyed a row by ``numeric_estimate.method``, so "answer shape" had
quietly meant "answer that carries a number" ever since — while the
answers this repository documents most, the ones that come back
``needs_investigation``, ARE the gap diagnosis and carry no estimate at
all. The paragraph above about rows says "run it on all of them", and
"all" was every estimator; an envelope with no estimator was never a row.
Those answers are collected from ``run`` and kept on the rule this file
already uses on leaves — a row earns its place by carrying a leaf shape no
kept row carries — so the corpus stops growing when shapes stop being new
rather than when somebody stops adding producers.

The bend set. This asked each leaf ONE kind of lie, so "held" was in part a
fact about which lie was chosen — a rule that catches that edit and no
other reports the leaf as held, and the declared remainder is then a lower
bound wearing the clothes of a measurement. Asked several kinds, eight more
leaves survive. What that concealed was not only arithmetic: a joint
effect's point estimate was held by nothing but a ratio computed from it,
and a point of exactly zero walked through the ratio's denominator guard.
A coverage claim is only as wide as the question that was asked.

That the lie is one the contract permits, which is the same sentence one
level down. The three lies told to a string are all ONE lie to a leaf whose
contract declares a vocabulary — "I am not one of these words" — and
validation refuses that before a rule reads it. The sweep counts a refusal
as a catch, correctly; the consequence was that every such leaf scored held
without anything ever asking WHICH member it is, and a leaf that scores
held never reaches the declared file where somebody would look at it again.
So the instrument read zero in the place it could not see. Reading the
domain out of the contract instead, the answer's own ``status`` can be
changed from bounded to solved on a row that carries neither an estimate
nor an interval, and a gap's ``severity`` from important to blocking. What
that costs the declared file is in the file.

That the door reads the answer at all. The sweep counts an exception as a
catch, and ``themis.verify`` raises on an answer it will not open — one
with no derivation, which is what every gap diagnosis is. Refused and
unread are the same word from outside and opposite facts about coverage,
so a row nothing reads now reports every leaf of it as unwitnessed rather
than as held by a rule that never ran.

That measurement is what showed the precondition was standing in front of
the wrong half of ``verify``, and ``verify_answer_claims`` is the door
that came of it: twenty-six of the leaves this file declared unwitnessed
were the variable a gap says it is about, what it says is missing, and the
predicates of the estimand and the patch on the five answers nothing read.

That one occurrence of a shape stands for the rest of them, which is the
same sentence a fourth time and the one that hid a live defect. A row's
gaps are a list of records of different species, and which rule decides a
gap's severity depends on its species: the first gap's is fixed by its
species and refused by the table that fixes it, so the shape scored held —
while the fourth gap's severity was an occasion's, nothing read the
occasion, and no question was ever put to it. The unit is now the SORT of
record, told apart by the words the record takes from a declared
vocabulary, and the names of the sorts that were never asked are added
beside the shapes rather than replacing them, so what the declared file
already says still means what it said. Eleven percent more questions cost
twenty-three percent more wall clock: the sorts nobody was asking sit on
the gap list, and a leaf there is put to more doors than the average one.
What a widening costs is priced in doors, not in questions.

An instrument that reports a hole honestly is how the hole gets closed;
these are the ones it has found about itself, and they are one sentence: a
coverage number is a fact about the question that was asked — of which
rows, of which leaves, of which of them, and in which words.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

import themis
from themis import language
from themis.verifier import verify_answer_names_its_question
from themis.verifier.errors import VerificationError

from . import schema_walk

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
#: This module's tests may go to any worker. Nothing here is shared and
#: built once — every test reads the same two JSON files — and the census
#: walk below is most of the suite's wall clock, so keeping it together
#: keeps it serial for no benefit. See ``conftest.py``.
SPREAD_ACROSS_WORKERS = True

UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, path + (index,))
    else:
        yield path, node


def _shape_of(path) -> str:
    """A leaf's name with list positions collapsed.

    The fifth dose point on a curve carries the same leaves as the first,
    and asking the door about all five says what asking about one says.
    Collapsing is what keeps this gate at a minute rather than five.
    """
    return ".".join("[]" if isinstance(p, int) else p for p in path)


#: Two numbers are the same number unless they differ by more than this.
#: Every comparison in this system is numerical and every numerical
#: comparison has a floor, so a bend inside the floor is not a lie any rule
#: was written to catch — counting it as a survivor reports a correct
#: tolerance as a hole. Declared here, wider than any tolerance the rules
#: state, because this gate must decide materiality without reading them.
_ATOL = 1e-6
_RTOL = 1e-5


def _is_material(old, new) -> bool:
    """Is the bend a different value, or the same value written again?

    Asked of the DIFFERENCE, not of the recipe that produced it. A recipe
    cannot stay honest across magnitudes: replacing a value with ``0.0`` is
    a replacement at 0.5 and a nudge at 1e-229, and it was exactly that
    degeneration — a Hansen p-value of 1.09e-229 shown as zero — that this
    gate reported as a hole in a rule that is correct.
    """
    if isinstance(old, bool) or isinstance(new, bool):
        return old != new
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return abs(new - old) > _ATOL + _RTOL * abs(old)
    return old != new


#: What the contract says a leaf may hold WHERE THAT IS A FACT ABOUT ITS
#: PATH. Read from the document the door validates against, keyed by the
#: spelling ``_shape_of`` already produces, so a leaf's domain is a lookup
#: and not a second table that has to be kept in step with the first.
#:
#: Half the question, and the half a table can answer. A statement carries
#: its set beside its token, so the domain of the two leaves it is made of
#: is carried too: which members ``token`` may hold depends on the
#: ``vocabulary`` next to it, and the slot a statement sits in inside
#: ``words`` is named after the sentence's hole, so the contract writes
#: ``additionalProperties`` and there is no path to key on at all. 1096
#: word slots on 61 leaves are in that position, and this table has an
#: entry for none of them. :func:`_the_domain_of` is where both halves are
#: asked; this stays what it was.
_DOMAIN: dict[str, tuple] = {}
for _path, _sub, _container in schema_walk.RESULT.walk():
    _members = schema_walk.RESULT.resolve(_sub).get("enum")
    if isinstance(_members, list) and len(_members) > 1:
        _DOMAIN[".".join(_path)] = tuple(_members)

#: How many lies one leaf is told. Unchanged by the domain reading below:
#: what changed is where the three come FROM, not how many there are.
_PER_LEAF = 3


def _from_domain(value, members) -> list:
    """Lies drawn from inside the leaf's own vocabulary.

    Spread across the declared order rather than taken from beside the
    value. Adjacent members are often the two that mean nearly the same
    thing, and a sweep that only ever asked about the neighbour would
    report a whole vocabulary as held on the strength of its least
    consequential swap.
    """
    others = [m for m in members if m != value]
    if len(others) <= _PER_LEAF:
        return others
    step = len(others) / _PER_LEAF
    return [others[int(i * step)] for i in range(_PER_LEAF)]


def _the_domain_of(result, path, shape):
    """What this leaf may hold, HERE.

    A domain is a fact about a leaf's path only where the contract states
    it by path. A statement's two halves are the case where it does not:
    the set travels beside the token because a token alone does not say
    which set it came from, so what the token may be is decided by a
    SIBLING, and a table keyed by the shape cannot express that — the
    shape is the same for every set the carrier holds. That was written
    down as a limit of this instrument and this is it being lifted.

    The members come from the registry a producer fills rather than from
    the contract, and the lie is still one the contract permits: for the
    sets it enumerates, ``test_a_listed_set_is_enumerated_as_the_kernel
    _has_it`` holds the two equal, and for the rest it enumerates nothing,
    so every string is permitted and a member is a string. Reading the
    registry is also the only way to reach the second kind: a set whose
    members the envelope's schema does not restate.
    """
    if len(path) >= 2 and path[-1] in ("token", "vocabulary"):
        statement = _at(result, path[:-1])
        if (isinstance(statement, dict) and "token" in statement
                and isinstance(statement.get("vocabulary"), str)):
            if path[-1] == "vocabulary":
                return tuple(sorted(language.VOCABULARIES))
            owner = language.VOCABULARIES.get(statement["vocabulary"])
            if owner is not None:
                return tuple(str(member) for member in owner)
    return _DOMAIN.get(shape)


def _at(result, path):
    """The node at ``path``, or None where the walk cannot land."""
    node = result
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def _a_name_neither_document_uses(program, result) -> str:
    """A name the answer cannot be read as already saying.

    The third kind of lie about a string is "some other name", and it was
    the literal ``"x"`` — a name the variables in this corpus actually
    have. A rule may accept two spellings of one variable on purpose:
    ``_atom_spellings`` in the verifier documents doing exactly that,
    because the two producers of the block it reads key on different
    things and insisting on one would refuse the other's honest answer.
    Handed ``"x"`` for ``"x(p9)"``, such a rule is being told the truth it
    already tells, accepts it correctly, and the leaf is scored a hole.

    The third sentence of one principle, whose other two are written where
    they are enforced: a lie has to be one the contract permits
    (:func:`_bends`), a lie has to be a different value
    (:func:`_is_material`) — and a lie has to be a LIE. A bend whose
    envelope is still true tests nothing, and counting its acceptance as a
    hole reports a correct rule as one.

    Both documents, because either alone leaves the other free to have the
    name: an answer spells the variables a program declares, and the rules
    that matter here read the two against each other. Derived rather than
    guessed, which is the whole of the fix — ``"x"`` was a guess that the
    name was free.
    """
    said = {value for _, value in _leaves(program) if isinstance(value, str)}
    said |= {value for _, value in _leaves(result) if isinstance(value, str)}
    name = "x"
    while name in said:
        name += "z"
    return name


def _bends(value, members, stranger):
    """Several KINDS of lie per leaf, not one.

    This returned a single value, and "held" was then partly a fact about
    which edit happened to be chosen. Measured: eleven leaves the one-edit
    sweep called held survive a different edit — among them a joint effect's
    point estimate, which was held only by a ratio computed from it, and a
    point of exactly zero walked through the division guard.

    Kinds, and only kinds. Whether any of them lands far enough away to be
    a lie is ``_is_material``'s question, asked of the two numbers rather
    than of the recipe. Strings are bent too: the leaves naming the
    treatment, the outcome and the mediator are strings, and skipping them
    would report the most consequential edits as impossible.

    A LIE HAS TO BE ONE THE CONTRACT PERMITS. The three lies below are all
    the same sentence to a leaf with a closed vocabulary — "I am not one of
    these words" — and that sentence is refused by validation before any
    rule reads it. The sweep counts a refusal as a catch, correctly, so
    every such leaf was scored held while nothing had ever asked WHICH
    member it is: the gate was measuring the validator and reporting it as
    coverage. Where a domain is declared, the lies come out of it instead,
    and :func:`_the_domain_of` is asked what this leaf may hold here —
    which for the two leaves a statement is made of is carried beside them
    rather than fixed by where they sit.

    AND A LIE HAS TO BE A LIE. The name the third kind uses comes from
    :func:`_a_name_neither_document_uses` rather than from a literal,
    because a literal is a guess that no variable is called that, and on
    this corpus the guess was wrong.
    """
    if members is not None and value in members:
        return _from_domain(value, members)
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value + 7, 0, value * 2 + 1, -abs(value) - 1]
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return [0.9 if value < 0.5 else 0.1, value / 2 + 0.01, 0.0]
        return [value * 3.0 + 1.0, -value - 1.0, 0.0, value / 2.0]
    if isinstance(value, str):
        return [value + "_forged", "", stranger]
    return []


def _tamper(result, path, value):
    bad = copy.deepcopy(result)
    node = bad
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


def _the_records_this_leaf_sits_in(result, path):
    """Every list element above a leaf, outermost first, with its path.

    A list element is where a record begins: an answer's gaps, its ledger
    lines, its bounds rows. Everything above that is the envelope's
    furniture, which one row has one of.

    A record inside a record is inside BOTH, and this returned only the
    innermost. A way past sits in its own entry and in the gap offering
    it; the word that decides which ways past are even available is the
    GAP's kind, one level out. Reading the nearest record only, that word
    was not part of the leaf's identity, so every way past in an answer
    was one sort and the first one asked stood for all of them.
    """
    node = result
    records = []
    for depth, step in enumerate(path):
        if isinstance(node, list) and isinstance(node[step], dict):
            records.append((node[step], path[:depth + 1]))
        node = node[step]
    return records


def _the_words_that_say_which_sort(result, path) -> tuple:
    """What the records a leaf sits in take from a closed vocabulary,
    minus the leaf itself.

    The identity this gate needs and did not have. Two records in one list
    are the same SORT of record exactly when every word they take from a
    declared vocabulary agrees — a gap of one kind and a gap of another are
    two sorts, and the rule that reads one of them may not be the rule that
    reads the other. Read off the contract's own domains rather than a list
    of field names kept here, so a record that grows a vocabulary field is
    told apart by it without anybody remembering to say so.

    ASKED OF EVERY ENCLOSING RECORD, not the innermost. The innermost was
    the same defect ``_asked`` records one level up: a unit that stops
    short lets one record stand for others that no rule reads the same
    way. Measured on this corpus, 1541 (shape, sort) pairs existed that
    nothing ever asked — a gap's ``describes[].sentence`` and its
    ``provenance[].ref_kind`` worst of all, then the ways past it offers.

    The leaf's own field is excluded, or the sort would be the value under
    test and every value would be its own sort — and only where the leaf
    IS that field of this record, since a field of the same name deeper
    inside it is a different field and describes the sort as much as any
    other word does.
    """
    words = []
    for record, record_path in _the_records_this_leaf_sits_in(result, path):
        itself = path[-1] if len(path) == len(record_path) + 1 else None
        words.extend(
            (key, value) for key, value in sorted(record.items())
            if key != itself and isinstance(value, str)
            and _shape_of(record_path + (key,)) in _DOMAIN
        )
    return tuple(words)


def _named(shape: str, words: tuple) -> str:
    """What the declared file calls one asked leaf.

    Additive on purpose. The first record of a shape keeps the bare shape
    it has always had, so every line already in the file means what it
    meant; only the sorts that were never asked take a name of their own,
    and the remainder therefore moves by what this finds rather than by
    what it renamed.
    """
    return shape + "@" + ",".join(f"{k}={v}" for k, v in words)


def _asked(result):
    """Every leaf this gate puts a question to, once per sort of record.

    The gate's SCOPE, and the only statement of it: what ``_sweep`` bends
    and what the scope test measures are the same walk, so a narrowing is
    one edit and it fails rather than passes. For twelve frontiers the
    scope was a subscript inside the sweep — ``result["numeric_estimate"]``
    — and nothing anywhere said so.

    ONCE PER SHAPE was the same defect one level down, and it hid a live
    one. A row's gaps are a list of records of different species, and the
    severity of the first says nothing about the severity of the fourth:
    the first was refused by the table that fixes its species' weight, the
    shape scored held, and the fourth — whose weight is an occasion's and
    whose occasion nothing read — was never asked at all. So the unit is
    the sort of record, and a shape is asked once per sort that appears.

    And the sort itself stopped one level short for the same reason: it
    was read from the nearest enclosing record, so a leaf inside a record
    inside a record — a way past inside a gap, a sentence inside a gap —
    took its identity from the inner one, where the word that decides its
    vocabulary sits in the outer one. See
    :func:`_the_words_that_say_which_sort`.

    Yields the NAME to report under and the SHAPE to bend by, which are no
    longer the same string: the vocabulary a leaf's lies must come out of
    is the shape's, and a name qualified by the record's other words would
    find no domain and fall back to lies the validator refuses — which is
    the sweep measuring the validator and reporting it as coverage.
    """
    seen_shape: set[str] = set()
    seen_sort: set[tuple] = set()
    for path, value in _leaves(result):
        shape = _shape_of(path)
        words = _the_words_that_say_which_sort(result, path)
        if (shape, words) in seen_sort:
            continue
        seen_sort.add((shape, words))
        if shape in seen_shape:
            yield _named(shape, words), shape, path, value
            continue
        seen_shape.add(shape)
        yield shape, shape, path, value


#: The places a door has to look, and there is no fourth. A door is handed
#: the program and the answer; the DATA is not one of them, which is why a
#: leaf whose truth is a fact about the sample can be shown to a reader and
#: held by nothing.
#:
#: Read from strongest to weakest, because a leaf answering to more than
#: one is named by the strongest. A second writing under the SAME FIELD
#: NAME is one fact written twice and a comparison can hold it; the same
#: value under another name is a coincidence until somebody says which two
#: fields are one fact — measured, and the reason the distinction is drawn
#: here: a run that asked for 500 replicates also has 500 sitting in a
#: graph's edge list, on 73 rows, and no rule follows from that.
_ANSWER_ALIKE = "another field of the answer, named alike"
_PROGRAM_ALIKE = "a field of the program, named alike"
_ANSWER_OTHERWISE = "somewhere in the answer, named otherwise"
_PROGRAM_OTHERWISE = "somewhere in the program, named otherwise"
_NOTHING = "nothing either document writes"
_EVERY_READING_MATCHES = "a flag or an absence, which every reading matches"

#: Ordered as the reading returns them, so a split printed in this order
#: reads from "a rule could hold this" to "nothing here can".
_WHERE = (_ANSWER_ALIKE, _PROGRAM_ALIKE, _ANSWER_OTHERWISE,
          _PROGRAM_OTHERWISE, _NOTHING, _EVERY_READING_MATCHES)


def _the_field(shape: str) -> str:
    """What a leaf is CALLED, which is not where it sits.

    A position in a list is not part of a name — the third gap's severity
    and the first's are the same field — so the collapsed segments are
    dropped and the last real one is the name.
    """
    parts = [p for p in shape.split(".") if p != "[]"]
    return parts[-1] if parts else shape


def _comparable(value) -> bool:
    """Whether identity of value says anything about identity of fact.

    A boolean matches every other boolean and an absence matches every
    other absence, so finding one "elsewhere" is not finding anything.
    Excluded rather than counted, because counting them would report the
    weakest possible evidence as the strongest available.
    """
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _writings(document) -> dict:
    """Every comparable value a document writes, and the fields it is at."""
    out: dict = {}
    for path, value in _leaves(document):
        if _comparable(value):
            out.setdefault(value, set()).add(_shape_of(path))
    return out


def _where_the_truth_of(program, result) -> dict:
    """For each leaf this gate asks about, where a door could find it.

    The gate says WHICH leaves nothing holds and has never said where
    their truth is, so a leaf that can be held by writing a rule and a
    leaf that nothing in either document determines read exactly alike in
    the declaration. A frontier picked off that file cannot tell how far
    zero is, and a leaf nothing can hold gets revisited until somebody
    works out again that nothing can hold it.

    WHAT THIS DOES AND DOES NOT SAY. ``_NOTHING`` says no COMPARISON can
    hold the leaf: there is no second writing to compare it against. It
    does not say the leaf cannot be held at all — a rule that recomputes a
    number from sufficient statistics holds it without any second writing
    — and reading it as "impossible" would retire holes that are merely
    harder. The other way round is the stronger claim and the one that is
    safe: a leaf with a second writing under its own name is one a
    comparison CAN be written for.

    Computed rather than stored. A classification kept in a file beside
    the thing it classifies is a copy that states no relationship to it,
    which is the defect this repository keeps finding; re-read every run,
    it cannot drift from the corpus it is about.

    Keyed by the name ``_asked`` reports under, so the answer lines up
    with the declaration without anybody parsing the declaration's names.
    """
    in_answer = _writings(result)
    in_program = _writings(program)
    out: dict = {}
    for name, shape, _path, value in _asked(result):
        if not _comparable(value):
            out[name] = _EVERY_READING_MATCHES
            continue
        word = _the_field(shape)
        answer = in_answer.get(value, set()) - {shape}
        program_side = in_program.get(value, set())
        if any(_the_field(s) == word for s in answer):
            out[name] = _ANSWER_ALIKE
        elif any(_the_field(s) == word for s in program_side):
            out[name] = _PROGRAM_ALIKE
        elif answer:
            out[name] = _ANSWER_OTHERWISE
        elif program_side:
            out[name] = _PROGRAM_OTHERWISE
        else:
            out[name] = _NOTHING
    return out


def _the_remainder_by_where_its_truth_is() -> dict:
    """The whole declaration, split by the reading above.

    Over the corpus rather than per row, because the question it answers
    is about the remainder and not about any answer: how much of what is
    left could be held by writing a rule against something already
    written down, and how much waits on something nobody has written at
    all.
    """
    split: dict = {where: 0 for where in _WHERE}
    for name, leaves in UNWITNESSED.items():
        pair = SHAPES[name]
        where = _where_the_truth_of(pair["program"], pair["result"])
        for leaf in leaves:
            split[where[leaf]] += 1
    return split


def _doors() -> tuple[str, ...]:
    """Every public entry point an answer can be held to.

    For twelve frontiers this gate asked one of them. ``themis.verify`` is
    the door that re-runs the derivation, and it is also the one door that
    RAISES rather than reads when an answer has none — which is what every
    gap diagnosis is. Read off the package rather than listed, so a door
    added tomorrow is asked; the set is pinned below so that one is
    noticed too.
    """
    return tuple(sorted(
        name for name in dir(themis)
        if name.startswith("verify") and callable(getattr(themis, name))))


_TAKES_PROGRAM: dict[str, bool] = {}


def _ask(door: str, program, result) -> None:
    """Put one answer to one door, in the shape that door takes."""
    fn = getattr(themis, door)
    if door not in _TAKES_PROGRAM:
        params = list(inspect.signature(fn).parameters)
        _TAKES_PROGRAM[door] = params[:2] == ["program", "result"]
    if _TAKES_PROGRAM[door]:
        fn(program, result)
    else:
        fn(result)


def _reading_doors(program, result) -> tuple[str, ...]:
    """The doors that open THIS envelope as it stands.

    A door that refuses the honest answer witnesses nothing: it refuses
    the bent one for the reason it refused the honest one — this is not
    the kind of answer it reads — and counting that as a catch would
    report every leaf as held by a rule that never looked. Refused and
    unread are the same word from outside and opposite facts about
    coverage.

    ``verify`` is asked first because it catches nearly everything and the
    others are then only asked about what it misses, which is what keeps
    this gate at minutes rather than hours.
    """
    reading = []
    for door in _doors():
        try:
            _ask(door, program, result)
        except Exception:
            continue
        reading.append(door)
    reading.sort(key=lambda door: door != "verify")
    return tuple(reading)


def _sweep(program, result):
    """A leaf is held only if EVERY kind of lie about it is refused.

    Refused by SOME door that read the answer. Where none does, nothing
    about this envelope is witnessed and every leaf of it says so.
    """
    asked = {name for name, _, _, _ in _asked(result)}
    doors = _reading_doors(program, result)
    if not doors:
        return sorted(asked), asked

    survived = []
    stranger = _a_name_neither_document_uses(program, result)
    for name, shape, path, value in _asked(result):
        for bent in _bends(value, _the_domain_of(result, path, shape),
                           stranger):
            if not _is_material(value, bent):
                continue
            bad = _tamper(result, path, bent)
            if any(_refuses(door, program, bad) for door in doors):
                continue
            survived.append(name)
            break
    return survived, asked


def _refuses(door: str, program, result) -> bool:
    try:
        _ask(door, program, result)
    except Exception:
        return True
    return False


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_snapshot_is_of_answers_this_build_still_gives(name):
    """First, because a forgery refused by a stale fixture proves nothing
    and a hole found in one proves less.

    Held to every door that opens the row. ``themis.verify`` is the strong
    one — it re-runs the whole derivation — and it is asked of every row
    that HAS a derivation; a row without one is what a gap diagnosis is,
    and ``verify`` raises on it rather than reading it. A row no door at
    all reads is a row this gate cannot measure, and it says so here
    rather than reporting every leaf of it as a hole.
    """
    pair = SHAPES[name]
    doors = _reading_doors(pair["program"], pair["result"])
    assert doors, f"{name}: no public door reads this answer"
    if pair["result"].get("derivation"):
        assert "verify" in doors, (
            f"{name}: this build no longer verifies the snapshot")


@pytest.mark.parametrize("method", sorted(SHAPES))
def test_no_leaf_a_reader_is_shown_goes_unasked(method):
    """The measurement, kept as the gate, across every shape.

    A leaf that survives the public door and is not in the declared file is
    a hole opened since it was written. A leaf in the file that no longer
    survives has been closed, and belongs out of it — removing it is the
    only way anything should leave.

    One row per test, because the rows are independent and this walk is
    most of the suite's wall clock: what a row's own leaves survive is a
    fact about that row and about the doors, and about nothing else in
    this file. See ``conftest.py`` for what makes that mean anything.
    """
    pair = SHAPES[method]
    survived, _ = _sweep(pair["program"], pair["result"])
    declared = set(UNWITNESSED.get(method, ()))
    new = sorted(set(survived) - declared)
    gone = sorted(declared - set(survived))
    assert not new, (
        "leaves a reader is shown that no rule holds, and that nobody "
        f"declared: {json.dumps({method: new}, ensure_ascii=False, indent=1)}")
    assert not gone, (
        "leaves declared unwitnessed that are now held — take them out of "
        f"fixtures/unwitnessed_leaves.json: "
        f"{json.dumps({method: gone}, ensure_ascii=False, indent=1)}")


def test_the_doors_this_gate_asks_are_the_ones_the_kernel_opens():
    """The gate's other scope, and the same reason the first one is
    asserted: for twelve frontiers this asked ``themis.verify`` alone, and
    a narrowing is invisible in a passing test. A public entry point added
    tomorrow fails here until somebody has decided whether an answer
    should be held to it."""
    assert _doors() == (
        "verify",
        "verify_answer_claims",
        "verify_assumption_ledger",
        "verify_bootstrap_draws",
        "verify_bounds_results",
        "verify_cluster_inference",
        "verify_data_gap_report",
        "verify_fingerprints_agree",
        "verify_lagged_discovery",
        "verify_latent_lagged_discovery",
        "verify_markov_blanket",
        "verify_missing_data_numeric",
        "verify_notears_fit",
        "verify_one_row_count",
        "verify_orientation_ledger_export",
        "verify_orientation_propagation",
        "verify_orientation_questions",
        "verify_orientation_session",
        "verify_outcome_error",
        "verify_refusal",
        "verify_selection_recovery_numeric",
    )


def _statement_leaves():
    """Every leaf that is one of a statement's two halves, with the
    statement it belongs to."""
    for name, pair in sorted(SHAPES.items()):
        for path, _value in _leaves(pair["result"]):
            if path[-1] not in ("token", "vocabulary"):
                continue
            statement = _at(pair["result"], path[:-1])
            if (isinstance(statement, dict) and "token" in statement
                    and isinstance(statement.get("vocabulary"), str)):
                yield name, pair["result"], path, statement


def test_the_lies_a_statement_is_told_come_from_where_its_set_is_named():
    """The instrument's reach over the half a path cannot key.

    This gate recorded, for two frontiers, that it could not ask a word
    slot which member it held: the domain is conditioned on the sibling
    ``vocabulary``, and a shape is the same for every set the carrier
    holds. So the only lie it told there was one validation refuses, and
    every such leaf read as held while nothing had asked. Asserted here
    because losing it again would look exactly like coverage.
    """
    asked = 0
    for _name, result, path, statement in _statement_leaves():
        shape = _shape_of(path)
        domain = _the_domain_of(result, path, shape)
        assert domain, (shape, statement["vocabulary"])
        asked += 1
        if path[-1] == "vocabulary":
            assert set(domain) == set(language.VOCABULARIES), shape
        else:
            owner = language.VOCABULARIES[statement["vocabulary"]]
            assert set(domain) == {str(m) for m in owner}, shape
    assert asked == 2248, asked


def test_no_statement_leaf_has_a_domain_its_path_could_have_given_it():
    """Why the lookup above exists, said as a measurement.

    A word slot is keyed by the sentence's hole, so the contract writes
    ``additionalProperties`` and there is no path for the table to hold;
    and where a statement IS reached by named properties, the set it may
    be from is enumerated in the shared statement schema, which the
    table resolves in the wrong document. Neither is visible from a leaf
    that passes, so both are counted.
    """
    shapes = {_shape_of(path) for _n, _r, path, _s in _statement_leaves()}
    assert shapes and not (shapes & set(_DOMAIN)), sorted(
        shapes & set(_DOMAIN))


def test_a_door_that_will_not_read_the_answer_witnesses_nothing():
    """Refused and unread are the same word from outside.

    Eleven of the twenty doors read an ordinary numeric answer and
    ``themis.verify`` is one of them; the other nine refuse it for what it
    IS — "not a notears_fit result" — and would refuse every bent copy for
    the same reason. Counting that as a catch would report every leaf of
    every answer as held, by nine rules that never looked at one.

    The same word the other way round: ``themis.verify`` raises on an
    answer with no derivation, which is what every gap diagnosis is, and
    an envelope no door at all reads holds nothing.
    """
    program, result = SHAPES["backdoor_linear"].values()
    reading = _reading_doors(program, result)
    assert reading[0] == "verify"
    assert "verify_notears_fit" in _doors()
    assert "verify_notears_fit" not in reading
    assert _refuses("verify_notears_fit", program, result)

    unread = copy.deepcopy(result)
    del unread["derivation"]
    assert "verify" not in _reading_doors(program, unread)

    # Reading is not the same as having anything to say: the doors that
    # own a block accept an envelope that does not carry one, vacuously.
    # They are still not witnesses, because a witness is a door that
    # REFUSES the bent copy — so an envelope nothing holds reports every
    # leaf, whichever doors opened it.
    nothing = {"query_id": "q", "status": "structurally_solved",
               "framing_notes": ["a note"]}
    assert "verify" not in _reading_doors(program, nothing)
    survived, asked = _sweep(program, nothing)
    assert asked and sorted(survived) == sorted(asked)


def test_two_records_of_different_species_are_two_questions():
    """The unit, on the row that showed it was wrong.

    ``iv_2sls`` carries four gaps of three species. Its first gap's
    severity is fixed by its species and refused by the table that fixes
    it; the fourth gap's severity is an occasion's. One question per shape
    put that question to the first gap only, so the shape scored held and
    the fourth was never asked at all.
    """
    result = SHAPES["iv_2sls"]["result"]
    severities = [
        (name, path) for name, shape, path, _ in _asked(result)
        if shape == "data_gap_report.gaps.[].severity"]
    kinds = {gap["kind"] for gap in result["data_gap_report"]["gaps"]}
    assert len(kinds) == len(severities) > 1
    named = {name for name, _ in severities}
    assert "data_gap_report.gaps.[].severity" in named
    assert any("iv_identification_assumption_required" in name
               for name in named)


def test_the_name_of_a_sort_is_added_beside_the_shape_never_instead_of_it():
    """What keeps the declared remainder a comparable number.

    Every line already in the declared file names a bare shape, so the
    first sort of every shape must keep that bare name; a qualified name
    is only ever a question that was not being asked before. A change that
    renamed the existing lines would move the remainder by its own
    bookkeeping and there would be no reading of the two numbers that
    meant anything.
    """
    for pair in SHAPES.values():
        first: set[str] = set()
        for name, shape, _, _ in _asked(pair["result"]):
            if shape not in first:
                first.add(shape)
                assert name == shape
            else:
                assert name.startswith(shape + "@")
    declared = {name for names in UNWITNESSED.values() for name in names}
    assert declared, "nothing declared; this check is measuring nothing"


def test_a_sort_is_told_apart_by_the_words_its_own_contract_declares():
    """Read off the domains rather than a list of field names kept here,
    and the leaf's own field left out of its own identity — otherwise
    every value would be its own sort and every leaf would be asked once
    per value it happens to take."""
    result = SHAPES["iv_2sls"]["result"]
    path = next(
        p for p, _ in _leaves(result)
        if _shape_of(p) == "data_gap_report.gaps.[].severity")
    words = dict(_the_words_that_say_which_sort(result, path))
    assert "severity" not in words
    assert words.get("kind") in {gap["kind"]
                                 for gap in result["data_gap_report"]["gaps"]}
    for field in words:
        assert f"data_gap_report.gaps.[].{field}" in _DOMAIN


def test_a_leaf_inside_two_records_is_asked_once_per_outer_sort():
    """The unit, at the level it used to stop short of.

    A way past sits in its own entry and in the gap that offers it. The
    entry's own words cannot tell two of them apart — the route is the
    leaf under test and the rest of the entry is free text — so under the
    old unit every way past in an answer was ONE sort, and whichever gap
    happened to come first stood for all the others. Which ways past are
    even available is the gap's kind, one level out.

    Built from the corpus rather than asserted at the implementation: a
    row carrying two gaps of different kinds that both offer a way past.
    """
    shape = "data_gap_report.gaps.[].alternative_paths.[].route"
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        report = result.get("data_gap_report")
        if not isinstance(report, dict):
            continue
        kinds = {gap.get("kind") for gap in report.get("gaps") or []
                 if gap.get("alternative_paths")}
        if len(kinds) < 2:
            continue
        sorts = {words for asked, _, path, _ in _asked(result)
                 for words in [_the_words_that_say_which_sort(result, path)]
                 if _shape_of(path) == shape}
        assert len(sorts) >= 2, (name, sorts)
        assert all(dict(words).get("kind") in kinds for words in sorts), sorts
        return
    raise AssertionError(
        "no corpus row offers ways past on two kinds of gap; this gate is "
        "measuring nothing")


def test_the_sort_of_a_leaf_names_no_record_it_is_not_inside():
    """The other side. A sort that grew to every record above it would be
    just as wrong the other way: the words have to come from records this
    leaf actually sits in, and from the fields the contract gives a
    vocabulary to."""
    result = SHAPES["iv_2sls"]["result"]
    for path, _ in _leaves(result):
        words = _the_words_that_say_which_sort(result, path)
        if not words:
            continue
        inside = _the_records_this_leaf_sits_in(result, path)
        for key, value in words:
            assert any(record.get(key) == value for record, _ in inside), (
                path, key, value)


def test_what_this_sweep_calls_a_lie_is_asked_of_the_difference():
    """The gate's own assumption, pinned where it can be argued with.

    A Hansen p-value in these fixtures is 1.09e-229. Shown as ``0.0`` it is
    the same number to every reader and every rule, and the sweep reported
    the rule that accepts it as a hole — because materiality had been
    written as a recipe ("do not nudge") rather than as a question about
    the two numbers. The same recipe is a replacement one magnitude up.
    """
    tiny = SHAPES["iv_2sls_overid"]["result"]["numeric_estimate"][
        "over_identification"]["hansen_p_value"]
    assert abs(tiny) < _ATOL
    assert not _is_material(tiny, 0.0)
    assert not _is_material(500.0, 500.001)
    assert _is_material(16.43, 0.0)
    assert _is_material(0.5, 0.9)
    assert _is_material("a", "a_forged")


def test_the_declared_remainder_is_what_it_is():
    """The number itself, so that shrinking it is visible in a diff and
    growing it cannot happen by accident.

    It grew by 2806 when the sweep started telling a leaf with a declared
    vocabulary a lie from inside that vocabulary. None of those leaves
    became unheld that day; they had never been asked, because the only
    lie available to them was one validation refuses. A remainder that
    goes up on the day the question widens is the instrument working, and
    the families read out of the wider question have taken 1620 back off.

    It also went up by four once, and that was the same instrument.
    Closing a family can make the producer emit MORE: the route beside a
    declared loop names the loop's two variables where it used to name
    nothing, and the shortfall about a joint intervention beside a
    decomposition names the layer it collided with rather than offering a
    reader who declared one of two the pair. Four facts came to exist to
    be lied about that had not existed to be lied about. A gate that
    quietly dropped them would be reporting a smaller envelope as a better
    one.

    ``status`` took 121 of its 160 off when the envelope beside it was
    read, and 8 more when the question it answers was. The 31 that stay
    are relabellings neither can tell apart: a word a refusal leaves is
    open to every question, and where a question's answer may lead with
    either of two words that both say a quantity arrived, the envelope
    shows the same thing for both.

    Three of the 31 were briefly off and were given back on purpose. The
    rule that took them asked a word which SHAPE its quantity had, and a
    shape is readable only by enumerating the keys a shape can sit under —
    the reading that refused thirteen honest confidence-region answers.
    A promise held over less than a total reading buys leaves here by
    spending them at the door.

    An investigation item's ``gap`` took 98 of its 107 off, and a gap's own
    ``kind`` 28 more with it — a species is now referenced from the ask
    side, so moving it orphans whatever points at it. The 9 that stay are
    asks whose forged species is another one the report DOES carry: a
    reference held to its referent cannot tell a reader that the right gap
    is on the envelope but the wrong one is being pointed at, which is the
    same limit ``provenance[].ref_id`` has had since T10-1.

    The counterfactual world a reader is shown took 277 off in one pass —
    the four fields restating which counterfactual it is, and every
    per-variable key of ``abducted_noise`` and ``counterfactual_values``
    with them, because a display copy is now held against the world the
    verifier re-derived rather than only at the one number the chain
    carries.

    Its ``intervention.variable`` kept 41, and they are not a hole. The
    third lie this sweep tells a string is the literal ``"x"``, which on
    those rows is the BARE SPELLING of the variable the block names in
    full — the same variable with less of its name, and the rule accepts
    it on purpose so that the path keying on fitted columns is not refused
    outright. A synonym is not a lie, and nothing should hold it. The
    sweep cannot see that, so it is written down here instead.

    ``bounds_results[].numeric_uninformative`` took all 56 off at once.
    That flag is a route rather than a description — a reader is sent to
    "the data cannot constrain this" and the interval stops being shown as
    an answer — and it is now held to the two endpoints beside it, against
    the span the method's own declared range gives.

    A missing parameter's ``name`` and the variables to observe for it took
    52 off between them. The row renders one fact three ways, and the name
    is additionally the key ``investigation_requests`` is indexed by — so
    moving it used to switch off the agreement check for the ask pointing
    at it, on top of going unnoticed itself. What stays is the rows short
    of something that is not a parameter: they carry no key, and nothing on
    such a row settles a name.

    A counterfactual step's own account of what it was given took 215 off
    in one pass — the two atoms, their arguments, and the value. The rule
    auditing that step was handed those in a parameter called ``inputs``
    and never opened it: it re-ran the theorem from the query and compared
    one number, so the entries saying which counterfactual this even is
    were free while the check agreed with itself.

    ``s_admissibility_check``'s outcome then took 20 more, on both the
    predicate and the arguments at once, because holding the whole atom to
    the question catches either half moving. That one was worse than
    unchecked: an outcome the diagram had no node for skipped every
    selection node through a guard it shared with them, so admissibility
    was confirmed having tested nothing.

    Then 127 went at once when every atom a step names had to be a node of
    the graph. An atom is its arguments as much as its predicate, and the
    estimate audits compared only predicates, so ``x(u)`` and ``x(nobody)``
    were the same variable to them. Eleven paths moved, and the ones that
    are not ``treatment`` or ``outcome`` are why the walk recurses:
    ``adjustment.items[]``, ``cde_adjustment.items[]``,
    ``intervention.atom`` and a criterion step's ``x`` and ``y`` are atoms
    inside containers, and a gate reading only the fields whose value IS an
    atom would have left every one of them exactly as free.

    The same sentence then took 55 off the block a reader ACTS on: an
    investigation item's skeleton names the variables somebody goes and
    measures, and its units were free. Neither obvious roster works there
    — the graph is empty for a question that declares no edges, and the
    predicate roster cannot tell ``x(u)`` from ``x(nobody)``, which is the
    whole of what the leaf is about. What holds is the problem's own
    variables with the quantified positions grounded at the constants it
    names, which is the grounding the graph itself performs.

    The value beside those variables then took 76 off, and it needed two
    authorities rather than one. The program's DECLARED DOMAIN says which
    levels a variable has; it reaches 143 of the 193 asks and no further,
    because a problem written entirely out of cause edges declares nothing
    while naming everything. The item's OWN NAME reaches all of them,
    because ``parameter:P(y=True|x=True)`` is the same ask as the skeleton
    beneath it. Neither is the other written twice: only the domain sees a
    value moved in both places at once, and only the name sees one real
    variable swapped for another real one. That second case is why 21 of
    the 76 are predicates rather than values — the third lie this sweep
    tells a string is literally ``"x"``, which the grounded roster accepts
    because ``x`` is a variable the problem really has, and which the name
    refuses because the ask is filed as ``y``.

    Then 36 went off a block no verifier had ever opened, and they came off
    a rule already written. A refusal's ``failure_type`` is a token of a
    declared vocabulary, and the sentence rule holds every statement to the
    holes its own token declares — but the gate deciding WHICH sites that
    rule covers kept only the vocabularies its carrier table already named,
    so the instrument measuring coverage had its range set by what was
    already covered. Unfiltered it finds twelve sites where the table held
    ten, and misses none of the ten. The second of the two buys nothing and
    is written down as buying nothing: ``measurement_scale`` has no hole in
    any of its four sentences and sits on a closed record with nowhere to
    put a fact, so that carrier can never speak, and this sweep's numbers
    say so by not moving for it.

    Then 103 came off the facts a gap QUOTES back at a reader. The rule
    sorting a gap's ``said`` keys into names and non-names carried a
    reason per family for the second half — a vocabulary member "needs a
    table this package would have to restate" — and that reason answers
    the name-membership question while being read as answering a
    different one: whether anything at all could hold the value. Three
    keys tell the two apart. None is a variable, and each has an exact
    second record on the same envelope: the method an interval came from,
    the parameter ``missing_information`` is short of, the assumptions
    that interval rests on. No table restated, no membership tested — two
    copies of one fact, compared. Two of the 103 are the same slot under
    ``alternative_paths``, which the walk reaches because it is
    depth-blind about where a ``said`` hangs.

    The rest of that block stays open on purpose and the shape of what is
    left is why: 41 of its honest values live nowhere else on the
    envelope, being either a RENDERED number (36.3% for 0.363) or a
    COINED label (CDE). A rule demanding every quoted fact be findable
    refuses all 41, so those need a comparison with a tolerance — a
    different authority.

    Then 201 came off the block that stands where a number would have
    been. Every ``needs_investigation`` answer IS that block, and the rules
    beside it read it without holding it: the sentence rule asks whether a
    refusal's SLOTS match its species' holes, and the status rules read an
    outcome OFF the kind rather than compare it. What made it holdable is
    that one function assembles it and already declares every relation in
    it — the kind is stamped from the registry, the recorded facts and the
    sentence's facts are two halves of one mapping, and each fact is
    written twice. Nothing is restated: the rendering is imported from
    where the producer calls it.

    That comparison had to be corrected by measuring, and the correction
    is worth more than the leaves. Recomputing the sentence's half from
    the recorded half and comparing strings called one honest answer a
    liar, because a mapping's key order is not something an envelope
    fixes — a JSON object is unordered, and this file's own corpus is
    written through a sorting serializer, which reorders the recorded half
    while the rendered half keeps the order its producer wrote in. So the
    order is taken from the sentence and every value from the record.

    What stays open there is measured too. The ``estimator`` is 36 of it
    and has no second record on 31 of its 36, no roster to be a member of
    — the contract types it a string where it gives the species a full
    enum — and forty raise sites writing the word as a literal, which is
    the table a verifier must not become. ``recorded`` is the occasion's
    half its own producer names as the one that was measured and NOT said,
    so there is no second rendering of it to compare with.

    Then 136 came off the most expensive advice this system gives: how much
    data to go and collect, of what kind, on which variables, from which
    population. The minimum sample size is a copy of nothing, so no copy
    rule could ever have reached it — it is a power calculation, and what
    makes it checkable is that the calculation's own inputs travel beside
    it, in the target that says what the number buys. The authority is the
    arithmetic, re-run from a second transcription of the textbook closed
    forms.

    What stays under that block is 76 leaves and every one of them is a
    silence that was chosen. ``data_type`` is 34: which SHAPE of data closes
    a gap is decided where the gap is raised, nothing on the envelope states
    a relation between that and anything else, and a table from gap kinds to
    data types would be this package restating a producer's judgement. The
    other 42 are a statement's ``token`` — the design a precision target
    names, a time window, a population characterised rather than named.
    Which tokens exist is declared in the output layer, which no verifier
    may import, so a token this build has no arithmetic for may be another
    build's member as easily as a forgery. The rule that should reach them
    is the statement carrier, whose own table has no row for this block —
    which is a frontier of its own rather than a reason to look away here.

    Then 95 came off the pre-flight diagnostic, and they came off a rule
    that had been auditing that block since the block existed. It re-derives
    the observed scale, the verdict and the attached gaps — all of it FROM
    the recorded declared scale and declared domain, which made those two
    premises of the audit rather than results of it. A verdict re-derived
    from a rewritten declaration agrees with the rewritten declaration,
    exactly as it agreed with the real one. The declaration is the
    PROGRAM's, and the rule had never been handed the program.

    Three more relations came with it, each one its producer already
    states: the sentence the block carries is a rendering OF the statement
    on the gap beside it, said so in a comment and never compared; a column
    cannot hold more distinct values than the run records rows; and the
    recorded value set is a SET, in the order it was sorted into, of the
    type its own dtype family reads out as — only its length had been asked,
    and a length says nothing about what is in the list.

    23 stay and both silences are deliberate. ``dtype_kind`` is 19: a
    program declares what a variable MEANS and never how it was stored,
    nothing on the envelope records it twice, and every lie this sweep tells
    it is another member of its own vocabulary. The other 4 are a value
    swapped for another value of the same type, which is the same case one
    level down — the column's contents are written once. Both are accepted
    on purpose and a test pins the acceptance, because refusing them would
    mean inventing an authority.

    Then 88 came off what a gap SAYS, and they came off a walk that has
    read those slots for two rounds. What decides WHICH of them it reads is
    a pair of rosters, and their coverage was held to the keys the answer
    shapes produce — a claim about this corpus, whose range is where its
    author was standing. They are bound to the statements now, at import,
    and thirteen slots this build can write were in neither: silence rather
    than refusal, because a slot neither roster classifies is asked about
    by no rule in that module at all.

    What opened is a second record its producer already states in every
    case — the methods an answer ran, the field names a declaration has,
    the populations the PROGRAM declares. That last is a register the name
    rule cannot read: the words it knows are the problem's variables by
    construction, so a population filed as a name would refuse every
    transported answer there is.

    And a slot's meaning is its sentence's, which one word settles.
    ``target`` is a population where an answer is transported and a
    variable under a dose-response curve, so a table holding one answer per
    NAME is right about one of them and silent on the other. The copy table
    is keyed on the pair now. The rosters are not, and the 22 sites where
    ``target`` is a variable are what that still costs.

    Then 215 came off the report's headline word — every leaf it had —
    and 19 more came off ``status`` beside it. The rule there held two
    one-sided claims because recomputing the producer's function refused
    six honest answers, and the six were not exceptions: a tier is one
    question in two tenses, what came out and failing that what could
    still be got, and the second tense was all a rule could ask while the
    answer's shape was unreadable here. It is readable — every method
    declares which shapes its estimate comes out in — and a shape is a way
    of answering, so it says whether that way is a point, an interval or
    neither. The 19 come with it because a recomputation reads the status,
    so a status two rules could not tell apart is told apart by what the
    tier would have to become.

    Then 366 came off what a gap is WORTH: its severity and what it blocks,
    two fields a reader acts on that were typed at all 47 construction
    sites and declared nowhere. A value every site writes is declared
    nowhere, so a rule holding it could only restate the producer's layout.
    They belong to the species, and the species now says so — with the few
    whose value really is an occasion's saying that instead, in a sentence
    naming what it turns on. ``blocks`` closed entirely; ``severity`` kept
    106, all but four of them on rows carrying a gap for a variable with no
    operational definition, whose severity that round declared an
    occasion's. Twelve ``kind`` leaves came with them: bending a kind now
    contradicts the two words its own species declares.

    That declaration was wrong, and finding out is what the next round was.
    The severity of a gap for an under-defined variable was computed from
    whether the query names the variable, and the quiet branch could not be
    entered at all: a framing note is MADE from the predicates the query
    names, so no note exists for it to be about. What kept an unreachable
    branch looking alive is that the two sides read "which predicates does
    this query name" through two different functions. There is one reading
    now, and the species owns its severity like every other.

    The corpus was NOT re-collected in that round, and what decided it is a
    measurement rather than a preference. A wider reading names more
    variables, so a row that gains a note gains leaf shapes, and a
    structural row's name is a digest of the shapes that earned it its
    place — refreshing by name cannot express that, which leaves a full
    re-collection as the only other move. That collection was made and then
    discarded: it carried exactly the leaf shapes this one carries, 3763
    with none gained and none lost, while filing a different run's answer
    under 41 of the 42 method names — a numeric row is kept as the FIRST
    envelope seen for its method, and the suite's order moves. Zero
    coverage bought, a whole repository's tests re-pinned to another
    sample.

    So this file sweeps a corpus that under-states the new reach: 49 of
    these rows would now be answered with a framing note their recorded
    answer does not carry. Every one of those is another instance of a
    shape already covered here, which is what makes the trade a measured
    one rather than a hope.

    Then 82 came off whether a reader can go and CHECK a premise. A ledger
    line's ``testable`` says whether there is anything they could do about
    the assumption, which is a fact about the assumption and not about the
    run, and nothing had ever asked: all 529 ledger lines in this corpus
    could say the opposite of the truth and every door said yes. A
    declaration did exist — one table, keyed on the assumption's name — but
    it lived under ``themis/output/``, which no verifier may read, so the
    only written statement of what an id MEANS was one an audit was
    forbidden to look at. What closed these was moving that table to
    ``themis.assumption_glossary``; copying it into the verifier would have
    been transcription rather than verification, and the audit had said so
    itself. The 19 rows that keep the leaf are the ones carrying a line
    that names no assumption, which a table keyed on names cannot be right
    or wrong about.

    Then two came off where a gap says what raised it, and the smallness is
    the finding rather than a disappointment. A gap's provenance ref names
    something, and ``ref_kind`` exists to say WHERE that something is — but
    one member named no space at all, and 479 of the corpus's 966 refs wore
    it while addressing three different things, so the arm reading them
    could only ask that the string was not empty. Two of those spaces have
    members now, and a path into the answer is followed on the answer. This
    leaf still needs every ref in a row refused before it closes, and one
    space is still unreachable from here: a place in the PROGRAM, which this
    door is result-only by contract and never sees. So two rows close — the
    ones whose refs are all paths — and what the change is actually worth is
    on the envelope instead: a species citing ``extensions.discovery_metadata``
    was naming a block no answer carries, which its own producer's docstring
    says two lines above the site, and nothing could say so while the kind
    it wore asked nothing.
    Then 101 came off when a check that raised a gap was held to the checks
    this build runs, and only 52 of those are the leaf that was aimed at.
    Fourteen species say what raised them by naming a check and what it ran
    about, and both halves were literals at seventeen construction sites and
    declared nowhere, so the arm reading them could ask nothing. The name
    belongs to the species — ten of the fourteen write one at every site —
    and the subject to the answer, being a variable the gap's own sentence
    names or a column the estimator stood on.

    The other 49 are every row left of a gap's own ``kind``, and that is the
    declaration doing what a declaration does: naming the check per species
    binds the two fields to each other, so a gap relabelled as another
    species carries a check that species does not declare. Relabelling used
    to pass because the arm reading these refs took any of them for anyone.
    A rule aimed at one leaf closing a second is not a windfall — it is what
    it means for a fact to be stated once and read from both sides.

    Ten rows stay at the ref, all leading with a place in the program, which
    is the range T10-1 declares for that space and not an omission here.

    Then 51 came off the shape word a mechanism was fitted through. Three
    of the block's four fields were held — the method against the estimate
    that ran, each named assumption against the estimate's declaration, the
    target against the question — and ``form``, the field the block exists
    for, took any string at all. Nothing held it because which shapes a
    build can fit was decided in every estimator and written down in none:
    the refusals are there, and one of them even lists its five, but a set
    that lives in control flow is a set no reader downstream can look
    anything up in.

    The rows came from watching the whole suite produce them rather than
    from this corpus, and that distinction is the finding. The note this
    closed said ``form`` is a function of ``method`` "across the corpus",
    and the qualifier was load-bearing: ``tmle`` fits the logit link for a
    bool outcome and the line otherwise, and only one of the two is
    recorded here. A table assembled from these 243 rows would have closed
    the same 51 leaves and refused honest runs, which is why the families
    that spell the form into their method name are declared the way the
    producer builds them.

    Then 33 came off the count of replicates an interval stands on, which
    is 34 closed and one opened. What holds the 34 is the run's own record
    of what it asked for, sitting on the same envelope the whole time: the
    family is 120 rows, and the other 86 hold no second record — 72 asked
    for no bootstrap and correctly carry none, 12 report an analytic
    interval — so by the rule this file is built on they are honest
    remainders rather than holes.

    The one that OPENED is worth more than the 34, and it is not the fix:
    refreshing the rows took ``longitudinal_ipw_msm`` from a clustered run
    where the stored one had none, because the harvest proves sameness with
    the data digest and the sample size and a cluster column is a third
    input neither sees. On the row that arrived, bending ``bootstrap.kind``
    from ``cluster`` to ``iid`` is refused by no reading door — the stamp
    check returns early on a kind that is not ``cluster``, while the
    estimator's own declaration still names the column. The old row could
    not have shown that. A remainder that goes up because the corpus can
    finally ask a question is the instrument working.

    Then 3 came off that same leaf, on three rows rather than the one that
    exposed it. The two records of one loop are now held BOTH ways: the
    three checks that module had all begin at the stamp, so a stamp saying
    LESS than the estimator declared was corroborated by nobody and refused
    by nobody. Two of the three rows were never the reason the leaf opened
    — a corpus row shows a hole where it happens to sit, and the rule that
    closes it is about the envelope.

    Then 56 came off the word a caller wrote for the shape, and the second
    record was on the envelope the whole time — as it was for the replicate
    count above, which is now twice. ``mechanism_audit`` says who settled
    each shape and ``estimation_context.model_preference`` says what the
    caller asked for, and comparing them was not possible while the block
    merged the form's origin with the origins of levers no ``model=`` names.
    Reading a ``caller_asserted`` there as the caller's word is sound only
    while no other shape lever can be written at the public entry, and that
    premise is measured rather than assumed — the scan is in
    ``test_the_word_on_the_context_and_the_form_on_the_block_are_one_fact``,
    and wiring one of those levers through turns it red.

    Two of the 58 rows that carry a block do NOT close, and they are the
    price of an exemption rather than an oversight. ``iv_overidentified``
    accepts ``2sls`` by BEING the two-stage fit: nothing receives the word,
    so its block truthfully claims no caller, and a rule asking every named
    word for a block refused that honest answer. Both ``iv_2sls_overid``
    rows therefore still declare the leaf. The exemption is read off the
    strategy table — the only row whose vocabulary is neither the
    do-nothing word alone nor one of the three families' — so a second such
    row is a red suite rather than a quiet second.

    Nothing here needed the corpus refreshed, and that was the choice. The
    first repair un-merged the fact into a field on the block; a required
    field invalidates every stored pair, and one full re-collection changed
    75 of the 189 kept rows, 44 of them coming back as a different RUN at
    another sample size. The remainder would have moved for two reasons at
    once — which is the same lesson the opened row above teaches from the
    other side, and the reason this number is worth anything.

    And it went up by 272 on the day the unit stopped being the shape and
    became the SORT of record, which is this file's fourth report about its
    own reach and the largest. Not one of those leaves became unheld: they
    had never been asked, because the first record of a shape was standing
    for records of other species that other rules decide. Every line the
    file already had is untouched — the first sort of a shape keeps the
    bare name it has always had, and only the sorts nobody was asking take
    a qualified one — so the two numbers are the same measurement widened
    rather than a new instrument reading its own scale.

    What that widening found is one already-registered hole at nine times
    the size it was registered at, and three that were not. 88 of the 272
    are a gap's ``provenance[].ref_id`` where the ref is a ``program_site``
    — a ref kind whose referent is the program rather than anything on the
    envelope, filed as ten slices because ten was how many the old unit
    could see. 41 are the ``gap`` an investigation item points at when the
    ask is for framing fields nobody filled. 24 are a ledger line's
    ``provenance``, told apart by the layer and severity of the line it
    sits on. 30 are the two endpoints and the reference value of a
    Balke-Pearl bounds row, whose sort is its method and its sharpness.
    The rest are a long tail across the words a gap quotes back.

    Then 97 of those 272 went straight back off, and the two numbers that
    went with them are the same hole measured in two units. A gap's ref
    saying "this came from THERE" is followed onto the answer by T10-1 and
    refused where it lands on nothing; the same ref pointing into the
    PROBLEM was followed by nobody, because the audit that runs T10-1 is
    result-only by contract. Following it where the program already is
    closes 87 of the qualified slices and the 10 bare ones at once — 10
    was what the old unit could see of it and 88 what the new one could,
    and they close together because they were never two things. The one
    qualified slice that stays cites a dispatch conflict: its kind says
    program and its content is about this run, so there is nothing in the
    problem to find, and refusing it would refuse an honest report.

    Then 50 more went the same way, and so did the sentence above them.
    An investigation item's ``gap`` was held to the report's own list —
    the species must be one this answer found — and an ask pointed at
    another gap the report really does carry passed, which this file had
    written down as the limit of holding a reference to its referent. It
    was not the limit. The item says what was NEEDED, and the contract
    declares on each need the channel that repairs it, so which species an
    ask may point at was settled all along. 41 qualified slices and the 9
    bare ones close together, which is the second time in two rounds that
    a hole was being counted twice under two units.

    Then 77, and this file was counting one hole as two families. What
    shape of data a gap asks for was typed at every construction site that
    has one and declared nowhere, so the only thing a rule could hold it
    against was the producer's layout; and for the one species whose shape
    is an occasion's, the gap's ``signature`` and its ``data_type`` are
    that occasion spelled twice. Both are now read off the statement the
    gap was filed for, which the item it cites carries, so all 50 of one
    and all 27 of the other leave together.

    Then 105, and they left by the CONTRACT rather than by a rule, which is
    worth saying plainly. A statement carries which closed set it is from
    beside the token, and the shared schema has stated the members of a set
    since #544 — for eight of them. The gate holding that list to the kernel
    asked only whether every listed set was one the kernel owns, never
    whether every set the kernel owns was listed, and the kernel owns 35. So
    the 26 that were missing are now enumerated and a bent token is refused
    before any rule reads it.

    What this sweep was therefore NOT asking about those leaves: whether
    the token is the right member. That limit was written here, and it is
    lifted — see the last paragraph. Its diagnosis was right about the
    shape and narrow about the cause: a ``closedSets`` enum is conditioned
    on the sibling ``vocabulary``, which a shape path cannot express, AND
    the unconditional enum beside it — the 57 sets themselves — was lost
    as well, at 20 paths carrying 898 leaves, because the table resolved
    every reference in the envelope's own document while the walk recurses
    in the document each shape came from. A domain is not always a fact
    about a path, and both ways of assuming it is were costing coverage.

    Then 26, and they are the fifth value typed at every construction site
    and declared nowhere. A way past a gap is a member of a closed
    vocabulary of 85, and which of them a gap may offer was declared for
    three species — ``gaps.ESCAPES`` is keyed by the fine-grained need
    while the envelope carries the coarse species, so the other 27 obeyed
    nothing. ``gaps.ROUTES_OF`` now holds one row per species, folded from
    the declarations that already existed, and the type refuses a route its
    species does not offer before any rule reads it.

    What that closure is a measurement OF: three swaps per leaf, spread
    across those 85 members. The rule accepts any route the SAME species
    could offer — 137 of the 42 x 85 pairs, every one of them the carrier's
    own — so a swap landing on a sibling is not refused, and three swaps
    drawn from across the vocabulary land on one only by chance. The family
    reads closed because the lies this instrument asks are refused, not
    because every lie in it is.

    Then it went UP by 36, and nothing got worse. The sort a leaf is asked
    under was read from the nearest enclosing record, so a leaf inside a
    record inside a record took its identity from the inner one — and the
    word that decides its vocabulary sits in the outer one. Every way past
    in an answer was one sort and the first stood for the rest. Reading
    every enclosing record instead: 25 of the 36 are a shape a row had
    never had asked of it at all, and 11 are a shape already open on its
    row that turns out to be several sorts.

    Of the 25, twenty-one are a gap's ``describes[].sentence`` — which
    sentences a species may say is typed at every site and declared
    nowhere, the same disease this file has now watched close four times
    and which is open here rather than closed quietly. Three are the
    expression a Balke-Pearl row says it needs. The last one is the
    CEILING declared in the paragraph above, measured at last: on
    ``iv_estimand_fallback_to_linear`` the bend landed on
    ``coarsen_the_conditioning_set``, which is that species' own other way
    past, and nothing refuses it because nothing should. A ceiling written
    only in prose is one the next reader takes for a floor; this line is
    it in the remainder, where it can be counted.

    Then 21 back off, and they are the same 21. Which statements a species
    may make about itself was typed at 78 sites out of a vocabulary of 88
    and declared nowhere — the fifth time this file has watched that
    shape, and the first time it watched one open and close in
    consecutive rounds. Nothing else moved and nothing opened, which is
    what a declaration closing exactly the leaves it was written for looks
    like.

    Then 14 go, across three rows, and nothing here was rewritten to let
    them: they are ``extensions.counterfactual_cell``, the reader's copy
    of a block that also sits under ``numeric_estimate``, and this file
    had them listed as unheld from the day it was written. What changed
    is on the other side. The rule that could have priced them walked
    ``numeric_estimate`` and returned when there was none, because it
    carried a second claim — an absent budget means an endpoint is
    missing — that is only true across the subtree whose producer
    promises one. One traversal, two claims, and the narrower claim's
    scope became the other's boundary. Five leaves per row, two of them
    the interval's own endpoints: a priced interval cannot have an
    endpoint moved, because the half width beside it stops agreeing.

    Then 8 more, on one row, and they are a formula the contract writes
    out in prose beside the fields it is about. A stratified Wald block
    states an aggregate next to the rows it aggregates; one of the two
    routes that reach that table keeps a derivation record and a rule
    executes the formula against it, and the other keeps none, so on its
    envelope nothing executed the formula anywhere. Eight is every
    component of the table and the two sums over it. What stays are the
    two the identity does not read — the conditioning atoms and each
    stratum's assignment of them — and they stay because a leaf leaves
    this file by being closed and never by being tidied.

    Then 111, the widest single leaf after the seed, and the disease this
    file has watched most often, in a new place. Who can overrule an
    assumption is declared once, keyed on the assumption's name, and the
    producer reads it from there; the audit read the other two things that
    row says and not this one, leaving it to checks that only ask of a
    line CLAIMING a caller's input — so a line relabelled as nobody's to
    withdraw claimed nothing, and nothing asked. 87 of the 111 are the
    plain leaf, and 87 is the 106 shapes that carry a ledger less the 19
    that still carry a loose line. Those 19 stay, and the reason is the
    table's range rather than a gap in it: their loose lines name no
    assumption at all — a proposed edge, a supplied prior — and a table
    keyed on a name has nothing to say about a line that gives none.

    Then 87 more, and most of them are the family the paragraph
    above left open. The loose lines on those 19 shapes name no
    assumption, and the audit counted them — at least as many lines of a
    layer as the answer had records, and nothing at all where it had none.
    Each such line is a copy of one record on the same answer: a
    proposal-edge gap's statements, whose proposal read off the first of
    them, or a supplied prior's key and value. On all 19 shapes the lines
    were exactly their records' before anything asked. Held to that, 79
    are the lines' own fields, and 6 are the gap's side of the same copy —
    an edge, an algorithm, a confidence the gap states and its line
    repeats — which close because the two copies must now agree. Agreeing
    is all they must do: whether the edge is the program's is the gap's
    question, and a gap rewritten together with its line is still accepted
    by every door it was put to.

    The other 2 were not predicted, and they are a named line becoming an
    unnamed one. Erasing a confidence line's id passed on two rows: an id
    of "" is no id, every check keyed on one stepped aside, and nothing on
    those answers owes that line by name. Now it reads as what it has
    become, a line naming no assumption that no record owes.

    Then 4 more, on the two answers whose estimator answers with a
    region. That estimator declares its premises in its own block, and
    the audit read declarations at ``numeric_estimate`` alone and asked
    nothing once it found none there. The block's premise list was a
    list nobody held, and the ledger's id could be bent every way —
    the record of which ids this run emitted was that same unread list.
    Both close together, 2 on each answer.

    The sampling caveat above still holds and is worth repeating here
    rather than left two paragraphs up: three swaps per leaf out of 88
    members, and a species says between one and ten of them, so a swap
    landing on a statement the SAME species also makes is chance. What
    closed is that a gap can no longer describe itself as another
    species' failure.

    Then 16 came off the two caveats that say a sample was restricted on
    a collider, on the seven rows carrying one: the collider on six, the
    target on all seven, the value a selection caveat names on three.
    Whether an answer owed such a caveat was its report's author's to say,
    so the target and the value took any string at all, and the collider
    took the name of a variable the problem really has: ``"x"``, the
    intervention on those six. Each caveat is now held, as a whole, to the
    one the program and the graph the answer was reached on owe, and every
    bend that used to pass is refused by that rule and no other.

    Then 8 came off the cost named further up, the sites where ``target``
    is a variable and the rosters could file it only by its name: 7 under
    the dose-response statement and 1 under a way past a collider. What
    holds them is the name rule, asked now of the statement a slot sits
    in. The seven rows that keep the leaf keep it for the third lie,
    ``"x"``, which is a variable those problems really have. Whether the
    target is THIS name is not a question a membership test can ask.

    Then 27 came off with the second record that question needed. Where a
    statement names a role of the question — the intervention, the
    treatment, the target, the outcome — it copies the question, which is
    on the program, and the rule holding quoted facts to their records
    holds these to it. The seven targets above are 7 of them; 17 are
    outcomes on the loop, instrument, proximal and estimator rows, and 3
    are interventions on a row whose intervention is neither a state nor
    an event. Each had kept its leaf for ``"x"``, a variable those
    problems have and not the one the question is about.

    Then 2 more, the same leaf one container further out. A gap's own
    ``said`` is the occasion its kind names, and the walk reading
    statements gave it no name, so the intervention an ill-defined one
    is about and the outcome of a loop that wants an instrument could not
    be declared copies of the question. Named, they are.

    Then 27 came off the two caveats about a collider, on the six rows
    carrying one in more than its description. What a report writes was
    read off the description alone, and the gap says the collider again
    in its own occasion and in the ways past that name it, and a selection
    caveat says its value there too. The collider took ``"x"``, a
    variable those problems have, and the value took anything. Each
    place now spells the caveat it tells, held to the caveat owed.

    Then 12 came off the proximal rows, where a statement names the
    confounder nobody measured and the proxies standing in for it. Those
    are roles of the question as much as its treatment is, and they were
    missing from the roles a copy could be declared of, so each kept its
    leaf for ``"x"``, a variable those problems have.

    Then 2 came off the selection block on the row that could not recover
    from its restricted sample: the outcome and the selection nodes. The
    verifier read every name on that block back to a node by predicate
    alone, so ``"x"`` in either was a variable the problem has, and a
    negative verdict re-searched about the wrong nodes still came out
    negative. Both are named by the premises -- the question and the
    observations -- and are read from there now.

    Then the count went up by 22 and no rule changed. A species was added
    to the vocabulary an ask's need is drawn from, second in its declared
    order, and the lies a vocabulary leaf is told are spread across that
    order, so the second and the third lie each moved by one member. On
    18 rows the second now tells an ask whose effect is reachable only by
    an instrument, or is not identified, that what it needed was a joint
    effect identified: a need repaired through the same gap, so the
    species check passes, and no other record disagrees. A request's
    note is compared with nothing, and an item only with a
    missing_information row of its own name, which an answer reached by
    an instrument does not have. 26 leaves are declared for that. On 3
    rows a lie moved off a need nothing held, and 4 leave. Which need an
    ask names where the answer writes it once is the question still open.

    Then 69 came off the missing-data block, on the seven rows
    carrying one. The verifier re-derived its mechanism, its verdict and,
    where the verdict was positive, its formula, and a report shows a
    reader more than those: the partially observed variables, the
    factors a recovery is assembled from and what each is conditioned
    on, the target each stands for, the adjustment set, the covariate
    half, the factors the estimand requires, the targets a negative
    verdict names as blocked, a formula written where nothing recovers,
    and whether the ordered factorization was said to be complete. Each
    took any value. Each is re-derived now from the search the verdict
    came from, in the block's own spelling. The search budget stays
    where it was: it is read off the block on purpose, because a
    verifier holding a bound of its own would agree with the producer
    by arithmetic.

    Then 90 came off the list a reader is told to fill. 79 were
    under a request's note, which is what the asks under it share,
    written out of them by the function that writes the target and the
    priority. The verifier held those two and not the note, and on an
    answer the number path finished, with no missing_information, the
    note was the ask's only other record of what was needed. The other
    11, on 11 rows, are fields of an ask that its note copies,
    and one copy told alone now disagrees with the other. Told the same
    in both, a need is still held only by its kind and its holes; which
    need an ask names is the question still open.

    Then 8 came off the 3 answers carrying a selection-recovery
    block. Its verifier re-derived the verdict and the witness behind it,
    and not the rest of what the block tells a reader: whether the
    criterion is complete, the adjustment set beside its halves, and on a
    negative the empty witness and the formula. Which theorem it
    re-derived was the block's own word too, and
    is the question's now. Each block's search_budget stays: the verifier
    re-searches to the range a negative names and bounds a positive's
    witness by it, so a range that passes is a true statement about the
    graph, whichever one it is.

    Then 2 came off the 2 answers whose estimate writes back the
    stratum a conditional question names. The values a numeric block
    shows back were held to the question field by field, and the stratum
    had no row: another stratum re-derived to itself from its records.

    Then 18 left with the intervals they were on, from six answers.
    Their Balke-Pearl interval was taken around a node that is not an
    instrument with nothing conditioned, which the producer no longer
    does, and the refresh took the interval and the sentence about it
    off each row. Nothing here is newly held; what those rows say is less.

    Then 29 came off the word a caller writes to choose an estimator or
    a shape. Each of those rows answers through a route with no shape
    lever at all, so the field said ``auto`` and could be rewritten to
    say the caller had asked for 2SLS or for a link function. The
    producer already refuses to answer with a word the answering row
    does not accept; what was missing was the verifier's half, and it
    was missing because it sat inside a check that returns when an
    answer discloses no fitted shape — which is every one of these 29.

    Then 50 came off the two halves a statement carries.
    A statement travels as the SET and the MEMBER, both beside it,
    because a token alone does not say which set it came from — so
    neither half is fixed by the position, and both authorities that
    asked about membership asked by position. The enumerations sit on
    the field each set was first written at and follow it to no other,
    so a gap's own reason for itself, four levels inside ``words``,
    could be rewritten to any word at all on 42 answers, and at the two
    sites typed as open objects the set NAME could be too. What asks
    now is the statement walk, which was already total over the
    envelope and was returning where it could not find the word.

    Then 474 came ON, from this instrument starting to ask a
    statement the question it had recorded itself as unable to ask:
    which MEMBER, and which SET. A statement carries both beside it, so
    neither domain is a fact about a path — the slot a statement sits in
    inside ``words`` is named after the sentence's hole, so the contract
    writes ``additionalProperties`` and there is no path to key on, and
    which members the token may hold is decided by the set named next to
    it. So for 1096 word slots on 61 leaves the only lie ever told was
    "not a word at all", which validation refuses — the gate measuring
    the validator, in the one place it had said so.

    What the new lies found, in two families. 414 of them on 140 rows
    were the SET half, one hole told over and over: relabel any
    statement to the single set whose ids another layer coins, keep the
    token, and nothing objected — membership is not asked of an open
    set, by design. Those 414 then came off, because an open set is
    open about WHO coins a word and not about whether anything says it
    exists: the layer that coins one files its own record beside the
    statement, and the rule that read that record ran only inside the
    ledger while the label travelled anywhere. The other 60, on 58
    rows, were the MEMBER half, and 40 of those came off next: what a
    word says about the thing its own sentence names is said a second
    time by the record filed under that name — the scale a column was
    declared at (21), the side of the question a variable is on (19).
    Both were unheld because the audit that asks whether a value has a
    second record was only ever asked of the half a fact travels in
    when it needs no translating. Then the largest 8 of what was left,
    which were about no statement in particular: the two ways a design
    can break SUTVA are named in a LIST, and either of them could be
    written where the other belongs. Every audit above is about one
    statement, and being one of several is not a property a statement
    has, so the pair was nobody's question — a list is a claim of its
    own, these are the sentences a reader gets here and they are
    different sentences, and the statement walk asks it now. Whole
    statements are compared and not tokens, because four honest lists
    say one token twice with different facts beside it.

    Then those four: which way a monotonicity assumption runs, in a
    ledger claim, in what an IV answer says it rests on, and in the gap
    that tells a reader so. That word is the QUESTION's — thirteen
    answers are for a question spelling it, ten sentences repeat it, all
    ten as spelt — and one rule ever read the declaration. The bounds
    verifier takes it to work out which side tightens and hands the word
    to that row's own account, so it was held at the position it was
    first written at and nowhere else, which is the shape this file
    keeps finding.

    Then 3 more of that shape with a different authority: which premise
    an instrument's answer rests on, which decides whether its number is
    a LATE or one equation's coefficient. The derivation records which
    estimator ran, nine sentences across three blocks name the premise
    that estimator needs, and the one check reading the word held two of
    its copies to each other — so every copy agreeing on the wrong premise
    was one consistent sentence, and the gap a reader reads was not among
    the copies at all. What is left of the member half is five entries
    over five leaves, each the only one of its kind.

    Then 4 off an E-value block with no number. Which of four conditions
    stopped the conversion, and the value that decided it, is the other
    branch of the conditions the numbers are computed under, from the same
    recorded inputs. The one audit re-derived only the branch that yields
    a number, so on a block with none its only check was two absences
    agreeing: the reason, the rate in it, the baseline that decided it and
    the path that says which input was read were all unread.

    Then 3 by removal rather than by closing. Two refusals copied the
    reason the identification layer files on its own block into
    ``recorded``, which is for what the estimator measured. Nothing read
    the copy, the only check it met was the shape of its sentence, and
    the verdict it copied is re-derived where it was filed. What is left
    of the member half is two entries over two leaves.

    Then 1: the word a gap puts in a hole whose record names nothing. A
    hole copying a population or a role of the question travels as a
    value where the record names one and as a stand-in word where it does
    not, and the rule holding copies walked only the values — so a
    stand-in could become another, and any name a stand-in. The same
    rule read a population hole against every population the program
    names, so a source written as the target was one of them too. What
    is left of the member half is one entry over one leaf.

    Then 2, and the member half with them: which part of the program a
    structural refusal says writes a name the graph lacks, and the name.
    The kind was filed with the claims the data settles, so no list said
    it owed a witness, and its four copies on an answer were held to each
    other and nothing else -- bent together, a part that writes no such
    name and a name the graph holds both passed. Both are asked of the
    program now, at every copy.

    Then 21 where a gap quotes a variable's declaration back: the known
    noise a measurement field names (19) and where a threshold cuts (2).
    The rule that reads a fact against the declaration of what its sentence
    names was walked over the words and not over ``said``, so both could be
    anything. Rehearsed beyond the corpus, the quote turned out not to be
    one: written in the list's spelling rather than the declaration's
    letters, it was refused on every answer whose declaration says ``FFQ``.

    Then 6: the detail a structural refusal carries about its question --
    the conditioned atoms that break the back door, the edge whose
    coefficient is missing, the declaration a joint question has to drop.
    The other seven structural species had no witness, because what they
    claim is about the question and the graph and not carried whole in
    their own facts; their copies were held to each other and nothing else.
    Each species is asked of the question and the graph now, and the
    detail with it.

    Then 3 by a row that had become a fossil. A question naming a population
    no selection node separates was answered with the transport formula's
    source factor, which asserts that nothing confounds the treatment; it
    is answered in its one population now, and the row that kept the old
    answer still verified, so it was measuring an envelope nobody writes.
    Refreshed from the test that produces it, the leaves of the transport
    chain and its number are gone with the chain, and the answer it gives
    leaves three in families other rows already declare.

    Then 11 more, by a refresh that brought shapes rather than holes. An
    identify query conditioning on a descendant of the treatment was refused
    before the identifier was asked, and the row keeping that refusal kept a
    need the schema no longer has. The identifier answers such questions
    now, and a question conditioning on its own treatment or outcome is
    refused alike in both spellings. Collected again from the tests that ask
    them, eight rows bring shapes no row carried, and the twelve leaves they
    leave are in families other rows declare: the stratum an identification
    pattern says it conditioned on (seven), what a refusal's item is named
    and ranked, where an ask's annotation comes from. The fossil row's one
    leaf went with it.

    Then 15 more, by one row bringing a shape no row carried. A
    decomposition asked within a stratum is evaluated within it, and the
    numeric step records the stratum it conditioned on, which no stored
    step did. The fifteen leaves the row leaves are the ones the same answer
    asked of no stratum already declares, leaf for leaf.

    Then 18 fewer, the first way: closed. The stratum an identification
    names is the question's, which the criterion cannot check and so
    nothing checked. It is held now, on every row that names one, and six
    of those rows -- the identifications of a conditional estimand -- had
    that leaf and no other, so they leave this list entirely.

    Then 147 fewer, by neither way: they had been closed the whole time
    and this gate was wrong about them. The third kind of lie it tells
    about a string was the literal ``"x"``, and a rule that reads a
    variable's name may accept more than one spelling of it on purpose, so
    the bend handed such a rule the truth it already told. 34 families over
    101 rows -- the counterfactual's intervened variable, the slots where a
    gap names the treatment, the instrument, the outcome it is about, the
    expression a bound needs data for. The name comes from
    :func:`_a_name_neither_document_uses` now, and a lie has to be a lie.

    Then 23 fewer, closed. A column a number was read off has to be a name
    the program states. One rule already read that list and asked whether a
    column stood for several of the program's nodes; it could not ask
    whether a column stood for any, because it builds its table by looking
    each column up and a column matching none puts nothing in it. The 23
    are every row that states a column list and ran no estimator: where one
    ran, the list is held by the arithmetic that consumed it, and where
    none did, nothing in the answer had touched the caller's list at all.
    """
    total = sum(len(v) for v in UNWITNESSED.values())
    assert total == 1702, total
    assert len(SHAPES) == 252, len(SHAPES)


def _contract_blocks() -> frozenset[str]:
    """Every top-level block a reader may be shown.

    Read from ``query_result.schema.json``, which closes the object, so
    this is the whole of what an answer can carry — and it is the one
    statement of that fact that does not come from the corpus.
    """
    schema = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "themis"
         / "schemas" / "query_result.schema.json").read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False
    return frozenset(schema["properties"])


#: Blocks the contract admits that no row in the corpus carries, so no
#: leaf of them has ever been asked a question. Declared here the way the
#: leaf remainder is declared in a fixture: a block leaves this list by
#: being covered, and one that appears in it without being put there is a
#: corpus that has stopped covering what it used to.
UNCARRIED_BLOCKS = (
    "berkson_error",
)


def test_the_corpus_carries_the_blocks_the_contract_admits():
    """The gate's rows, measured against something that is not the rows.

    The scope test below asserts that every top-level key ANY ANSWER
    CARRIES is asked about — and read its list of keys from the corpus, so
    both sides came from the same place and a block no row carries could
    not register as missing. Twenty-two blocks are declared by the
    contract; the corpus carried fifteen.

    That is the same failure this file records one axis over: the sweep
    read one block while its prose said the envelope. Here it read the
    answers that carry a number, because the collector watches
    ``kernel.estimate`` and keys each row on ``numeric_estimate.method``,
    and an answer with no number was never a row.

    Widening the corpus to the answers that take no route closed four of
    the five that were left: ``confidence``, ``confidence_sources``,
    ``estimator_dependency_missing`` and ``estimator_fallback`` are all
    things an answer says when it could NOT do what was asked, so the
    rows that carry them are precisely the rows a number-keyed collector
    could never file. Twenty-one of the twenty-two blocks are covered now,
    and the coverage came from fixing which answers are collected rather
    than from writing a case per block — which is the difference between
    a denominator and a to-do list.
    """
    carried = set()
    for pair in SHAPES.values():
        carried.update(pair["result"])
    assert carried <= _contract_blocks(), carried - _contract_blocks()
    assert sorted(_contract_blocks() - carried) == sorted(UNCARRIED_BLOCKS)


def test_the_sweep_asks_about_the_whole_envelope():
    """The denominator, stated where narrowing it fails rather than passes.

    This gate spent twelve frontiers reading ``result["numeric_estimate"]``
    while its name and its prose said the envelope — 1560 leaf shapes of
    the 7568 the envelope then had, and every frontier it produced was
    therefore a frontier inside one block. A scope is not visible in a
    passing test, so it is asserted: every top-level key any answer carries
    is asked about, and the count of asked shapes is the envelope's own —
    which moves when the envelope grows a field, as it does here.

    What a corpus does not carry is the other half, and it is asserted
    against the contract rather than against the corpus, above.

    It also moves when a refresh changes what the rows carry, and both
    directions once happened at once: eight rows were re-collected, six of
    them picked up a framing note and a gap their producer had grown since
    they were stored, and two mediation rows lost every interval endpoint
    they had — the callers producing them ask for no bootstrap, and the day
    that ask began to be honoured the endpoints stopped being reported at
    all rather than being reported equal to the point.

    And it moves when the UNIT moves, which is what happened here: 27988
    was one question per shape per row, and a row's gaps are records of
    different species whose weights are decided by different rules. Asking
    one sort per shape instead makes it 31149 — 3161 questions that were
    never put, at eleven percent more of this gate's wall clock.

    Then 32690, and it is the same correction one level further in. A sort
    was read from the nearest record a leaf sits in, so a leaf inside a
    record inside a record — a way past inside a gap, a sentence inside a
    gap — was one sort however many gaps the answer held. Reading every
    enclosing record puts 1541 more questions, and this gate's share of
    the suite's wall clock rises with them.

    Then 32694, by a refresh again: the one stored framing request over a
    single ask gained the note every other channel writes, and with it a
    need and three words about its occasion to ask about.

    Then 32514, by a refresh the other way: six answers lost a
    Balke-Pearl interval taken around a node that is not an instrument
    with nothing conditioned, and the sentence about it.

    Then 32585: the joint general-ID answer records the estimand each
    corner of its box was read off, and the refresh that stored it also
    picked up what its producer had grown since the row was kept: a
    framing note and a gap about the second treatment's definition, and
    the bootstrap premise on its ledger.

    Then 32584, downwards and not by a refresh: the IPW answer's
    ``stabilized`` was deleted rather than closed. Which weights the
    number was taken over is already the ``method``'s own two members,
    the derivation step that produced it, the mechanism audit's record
    of the fit and the estimator's own declaration — and the boolean was
    the one of the five no door read and no reader saw. A leaf leaves
    this gate by being closed or by being gone, and the second way is
    why this count is asserted rather than derived.

    Then 32577, the second way again: two refusals stopped carrying a
    copy of the reason the identification layer files on its own block.
    Seven leaves were the copy, and nothing read them.

    Then 32575, by a refresh: a question naming a population nothing
    separates is answered in its one population, so its row carries the
    back-door chain and the identification pattern (17 questions) where it
    carried the transport chain, the transport block's number and a
    structural value (19).

    Then 33678, by the refresh that let the identifier answer an identify
    query conditioning on a descendant of the treatment. Eight rows bring
    1142 questions -- five such identifications, two effect answers
    conditioning on a stratum, and the refusal of an effect question
    conditioning on its own outcome -- and the fossil row took 39.

    Then 33838: that decomposition asked within a stratum, 160 questions.
    """
    top_level, asked_top = set(), set()
    asked_total = 0
    for pair in SHAPES.values():
        top_level.update(pair["result"])
        names = [name for name, _, _, _ in _asked(pair["result"])]
        asked_total += len(names)
        asked_top.update(name.split(".")[0] for name in names)
    assert top_level - asked_top == set(), top_level - asked_top
    assert asked_total == 33921, asked_total


@pytest.mark.parametrize("method,leaf", [
    ("backdoor_linear", "outcome"),
    ("mediation_linear_imai", "mediator"),
    ("proximal_bridge", "outcome_proxy"),
    ("causation_plugin", "treatment"),
])
def test_the_answer_cannot_rename_the_question_it_answers(method, leaf):
    """What closed first, and why it is the sharpest of the 420 this sweep
    started from: renaming the outcome changes not one number on the
    envelope and changes every one of them into an answer to a question
    nobody asked."""
    pair = SHAPES[method]
    estimate = pair["result"]["numeric_estimate"]
    shown = estimate[leaf]
    bent = [s + "_forged" for s in shown] if isinstance(shown, list) \
        else shown + "_forged"
    where = ("numeric_estimate", leaf)
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], _tamper(pair["result"], where, bent))


def test_a_sequence_written_into_one_field_is_declined_not_guessed():
    """The longitudinal path writes its whole treatment course into
    ``treatment`` — "A0,A1" where the query's single atom says "A1". That
    is a different estimand spelled a different way, and the rule declines
    it rather than compare. Declining leaves the leaf unheld, which is why
    it is in the declared file: the alternative was refusing an honest
    answer, and #517 is what that costs. Asked of the rule directly,
    because at the door this particular field turns out to be held by the
    chain comparison instead — which is the arrangement working, not the
    rule being unnecessary."""
    pair = SHAPES["longitudinal_gformula"]
    estimate = pair["result"]["numeric_estimate"]
    query_id = pair["result"]["query_id"]
    assert "," in estimate["treatment"]
    verify_answer_names_its_question(
        estimate, pair["program"], query_id=query_id)

    single = dict(estimate, treatment="something_else")
    with pytest.raises(VerificationError, match="question asked about"):
        verify_answer_names_its_question(
            single, pair["program"], query_id=query_id)
