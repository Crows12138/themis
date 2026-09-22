"""The number a reader is shown, and the record it was checked from.

An answer that came from data reaches its reader twice. The derivation's
terminal step records what the estimator did, and every rule in this
package re-derives the answer from THAT record. Beside it sits
``numeric_estimate``, which is what a reader, a report and the browser
actually read. The two are one run written down twice, and only the first
of them is audited.

Measured on a stratified-Wald answer: of forty-two leaves under
``numeric_estimate``, thirty-eight could be edited and still pass the
public door — the stated confidence level, the sample size, the first
stage that decides whether the instrument is weak, every cell of the
stratum table, every endpoint of the confidence set. The point estimate
and the sensitivity block were the four that held.

This module asks the one question that needs no knowledge of any
estimator: **a name that appears on both sides names the same thing**.
``ci_level`` in the step and ``ci_level`` on the estimate are one number
recorded twice, and so are the sample size, the digest, the method and
the endpoints. Where the two sides spell one fact differently — the step
carries an atom, the estimate carries the predicate's name — the spelling
is transcribed here rather than skipped, because a relabelled outcome is
exactly the edit that a shape-mismatch would wave through.

The question is asked at every depth, and NOT only of the envelope's
outermost keys. Asking it of those alone made the rule's reach a fact
about how deep an estimator nests its answer: the probabilities of
causation sit one level in, and every one of their bounds was a number
nobody compared.

Down there the name asked for is the block's own name joined to the
leaf's — ``pn: {lower, upper}`` beside a recorded ``pn_lower`` — which is
a rule about the two shapes rather than a guess about spelling.

And, failing that, the leaf's own name, where nothing else on the envelope
answers to that word. Most of what an answer reports about itself —
``point``, ``ci_lower``, ``ci_upper`` — is vocabulary relative to whichever
answer carries it: ``ps.ci_lower`` is the probability of sufficiency's
interval and the step's ``ci_lower`` is the run's, and comparing them says
a truthful envelope is two different runs. That is true, and reading it as
a rule about DEPTH was what it cost. ``p_y_do_x0``, ``observed_x``, a
counterfactual cell's own ``lower`` — each means one thing on the whole
envelope, each is recorded flat, and each sat behind a spelling no step
would ever carry. Relative or absolute is a question about the envelope
and the envelope answers it: three blocks say ``ci_lower`` and one says
``p_y_do_x0``. See ``_spellings``, which records what each guess cost when
it was measured.

The nested views take one step more, because a table rendered for a
reader is not the flat columns the step recorded. Two shapes cover them:

- A confidence set is the step's own fields under a prefix, so the
  correspondence is the prefix and nothing else, and it is required TOTAL
  — a leaf of the view that the step never recorded is a number nobody
  can check, and the way to be told of one is a refusal rather than a
  skip.
- A stratum table is columnar in the step and row-wise on the envelope,
  and the two spellings differ irregularly (``stratum_weights`` beside
  ``stratum_shift_var_xx``), so the map is written out rather than
  guessed. Three of its cells the step does not record at all — how many
  units a stratum held and how they split by the instrument — and those
  are held to the arithmetic that relates them to what IS recorded: a
  weight is a share of the sample, and the two instrument arms are the
  whole of the stratum.

One leaf held out longer than the rest, and it was never a copy problem.
``first_stage_f_stat`` — the number Stock and Yogo's threshold is applied
to, the one that decides whether a reader treats an instrument as weak —
appeared in NO derivation step, so nothing could re-derive it and nothing
did. It is closed now, and not from here: the producer records the
residualised second moments the statistic is a ratio of, and a rule
re-derives it from them by a route that shares no arithmetic with the
producer's. The step carries the F itself as well, so the same-name check
above holds the reader's copy as a side effect — one key closed the copy,
one set of moments closed the number.

**Independence pin:** this module MUST NOT import from
``themis.estimation`` or ``themis.output``. It compares two records that
the same run wrote, which is not an audit of either — what it is, is the
statement that a reader and an auditor were shown the same run. The
audit of the numbers themselves is the rule that re-derives them from the
step.

Three older members of this species live in ``themis.kernel`` beside the
per-kind dispatch that gates them, holding an ``extensions`` block against
the same terminal step. They read the DECODED derivation; this reads the
JSON as submitted, so a serialisation that lost a field is visible here
and not there.
"""
from __future__ import annotations

from typing import NoReturn

from .errors import VerificationError

_RULE = "numeric_display_copy_check"

#: How much two recordings of one float may differ. They are the same
#: number written twice, so the only distance allowed is the one JSON
#: round-tripping can introduce.
_TOL = 1e-9

#: Names the two sides spell differently for one fact: the step records a
#: reference to a model variable, the estimate records the variable. Kept
#: as a transcription rather than a skip, because "the shapes differ" is
#: how a relabelled outcome would pass.
_ATOM_KINDS = frozenset({"atom"})

#: Views whose leaves are the step's own fields under a prefix. The
#: correspondence is required total in both directions: every leaf shown
#: is a field recorded, so a view cannot grow a number nobody checks.
_PREFIXED_VIEWS = {
    "anderson_rubin_confidence_set": "ar_",
    "stratified_anderson_rubin_confidence_set": "sar_",
}

#: The same prefix correspondence, where it is PARTIAL. A confidence set
#: is a set: every endpoint of it comes from one record, so a set standing
#: beside half a record is a hole with nothing saying so, and totality is
#: what says so. These two are not sets. A joint contrast's block carries
#: the cells it was taken between and a trimming summary carries the model
#: that was fitted, and the step records neither — measured, on every
#: answer that carries them — because neither is a number the step
#: produced. They are not unheld: the cells are held against the corner
#: risks the contrast was read off, and the model name by the diagnostic
#: that reads it. Requiring totality here would be requiring the record to
#: carry what it never produced.
#:
#: What totality buys for a set, the sweep gate buys here: a leaf of one of
#: these blocks that nothing compares is a leaf the declared remainder
#: names out loud.
_PARTLY_PREFIXED_VIEWS = {
    "joint_effect": "joint_",
    "propensity_summary": "propensity_",
}

#: A series, and the one entry of it that speaks for the run. Descent
#: stops at a list because each entry is its own subject, which is true
#: and is not the whole of it: a terminal step reporting a point reports
#: ONE of those subjects, and the point says which. So the correspondence
#: is the entry whose named field equals what the step reports, and the
#: fields that must then agree with it. Where no single entry answers to
#: that number, this says nothing — a step whose point is not on the curve
#: is not a disagreement about an interval.
_THE_ENTRY_THE_STEP_PRODUCED = {
    "dose_response_curve": ("point", "effect", ("ci_lower", "ci_upper")),
}

#: A stratum row's cells, and the column each was recorded in. Written out
#: because the two spellings do not follow one rule — ``weight`` pluralises
#: and ``shift_var_xx`` does not — and a guessed rule that happened to work
#: on three of six would leave the other three unchecked and silent.
_STRATUM_COLUMNS = {
    "weight": "stratum_weights",
    "outcome_shift": "stratum_outcome_shifts",
    "treatment_shift": "stratum_treatment_shifts",
    "shift_var_yy": "stratum_shift_var_yy",
    "shift_var_xy": "stratum_shift_var_xy",
    "shift_var_xx": "stratum_shift_var_xx",
}

#: The table's own aggregates, and the step's name for each.
_STRATUM_AGGREGATES = {
    "outcome_shift": "aggregate_outcome_shift",
    "treatment_shift": "aggregate_treatment_shift",
}


def _plain(value):
    """A step-side value as the plain data it stands for.

    A derivation input is serialised with its type beside it — a tuple, a
    mapping, a model variable, a set of them — while the estimate beside
    it carries the data. Unwrapping is what lets the two be compared at
    all, and doing it rather than skipping on a shape mismatch is the
    whole point: "the shapes differ" is how a relabelled outcome or a
    reordered sampling grid would pass.

    A reference to another step is not data and stands for nothing here;
    it comes back unchanged. Nothing declines it and nothing has to: the
    names such a reference is recorded under are the names of NESTED
    blocks, and a nested block is not offered as a subject. Measured --
    offer them and twenty-four comparisons of the stored answers land
    opposite a pointer, every one of them an honest answer. This said for
    a long time that a named helper declines it. There was no such
    function, and a sentence pointing at a check is how a reader concludes
    a case is handled that nothing handles; what keeps a block from being
    called a pointer is where the walk on the reader's side stops.
    """
    if isinstance(value, list):
        # A sequence of serialised things is one too. Unwrapping stopped at
        # the outer container while the docstring said it did not, so a
        # confounder set recorded one list per time step came back as
        # atom dicts and was compared against the names beside it.
        return [_plain(i) for i in value]
    if isinstance(value, dict):
        if value.get("kind") in _ATOM_KINDS:
            return value.get("predicate")
        # A container is unwrapped by the shape it has rather than by the
        # name it goes under. The wrappers were listed one by one here and
        # the list went a member stale: ``atom_tuple`` was absent, so a
        # mediator set was compared as a wrapper against a list of names,
        # matched nothing, and was skipped for looking different.
        items = value.get("items")
        if isinstance(items, list):
            return [_plain(i) for i in items]
        if isinstance(items, dict):
            return {k: _plain(v) for k, v in items.items()}
    return value


#: Figures the envelope carries that no estimator produced: arithmetic on
#: two numbers already in BOTH copies, computed for a reader after the step
#: recorded its output. Requiring the record to carry them would be
#: requiring it to carry a derived figure — the thing recording sufficient
#: statistics exists to avoid — and it would make this rule's verdict depend
#: on whether a route happens to annotate before or after it builds its
#: derivation, which is an ordering fact and not a fact about the answer.
#: They are not unchecked: ``verify_envelope_arithmetic`` re-derives each
#: one from the interval beside it, wherever it appears, which is a stronger
#: question than whether two copies of it match.
_DERIVED_ANNOTATIONS = frozenset({"precision_budget"})


def _same_number(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= _TOL


def _predicates(value):
    """A name a reader reads, reduced to the part a step records.

    ``_atom_label_verifier`` spells an atom ``pred(args)``, with ``@t``
    where the program is unrolled. A block about one unit names the unit —
    a counterfactual's target is ``Y(joe)`` because that is whose outcome
    it is — and the step above it records ``Y``, because which unit the
    question is about does not change whether it is identified. Reducing
    rather than skipping is the point: the predicate is what the two
    record in common, and "the strings differ" is how a relabelled target
    would pass.

    Containers reduce element-wise, since a set of treatments is named the
    same way one is.
    """
    if isinstance(value, str):
        return value.split("(")[0] if "(" in value else value
    if isinstance(value, list):
        return [_predicates(v) for v in value]
    return value


def _agree(shown, recorded) -> bool:
    """Whether two recordings of one fact say the same thing.

    Three asymmetries are real and not shape mismatches, and the third is
    the reader's own vocabulary: a block about one unit names the unit and
    the step records the predicate, so where the two differ only by that,
    the predicate is what they have in common. Tried after the direct
    reading fails, so a block that does record the bare name is unaffected.
    """
    if _agree_directly(shown, recorded):
        return True
    reduced = _predicates(shown)
    return reduced != shown and _agree_directly(reduced, recorded)


def _agree_directly(shown, recorded) -> bool:
    """The reading that takes both sides at their word.

    Numbers compare within the distance JSON round-tripping can introduce;
    containers compare element-wise so a nested tuple inside a mapping is
    reached. Two asymmetries are real and not shape mismatches.

    Where a step records only the DISCRIMINATOR of a block the estimate
    carries whole — the reason an interaction could not be reported, say —
    what the two have in common is the kind, and that is what is compared.
    Silence there would let the two names drift apart.

    And where the estimate carries a STRATUM and the step the variables it
    was taken on: an answer within ``c=True`` says which people it is
    about, and the criterion step above it says the question was answered
    conditioning on ``c``, because identification does not depend on which
    value. The names are what the two record in common, and the step's are
    a set — the criterion is about a set of variables — so they are
    compared as one. Comparing the two whole calls every honest
    within-stratum answer two different runs.
    """
    if isinstance(shown, dict) and isinstance(recorded, str):
        return shown.get("kind") == recorded
    if (isinstance(shown, list) and isinstance(recorded, list) and shown
            and all(isinstance(p, list) and len(p) == 2
                    and isinstance(p[0], str) for p in shown)
            and all(isinstance(name, str) for name in recorded)):
        return sorted(p[0] for p in shown) == sorted(recorded)
    if shown is None or recorded is None:
        return shown is None and recorded is None
    if isinstance(shown, bool) or isinstance(recorded, bool):
        return shown == recorded
    if isinstance(shown, (int, float)) and isinstance(recorded, (int, float)):
        return _same_number(shown, recorded)
    if isinstance(shown, list) and isinstance(recorded, list):
        return len(shown) == len(recorded) and all(
            _agree(a, b) for a, b in zip(shown, recorded))
    if isinstance(shown, dict) and isinstance(recorded, dict):
        keys = set(shown) - _DERIVED_ANNOTATIONS
        return keys == set(recorded) - _DERIVED_ANNOTATIONS and all(
            _agree(shown[k], recorded[k]) for k in keys)
    return shown == recorded


#: The block whose own shapes the three checks at the foot of this module
#: are asked of, and the first of :data:`_SUBJECTS`. Named because the two
#: drifted: the refusal below carried this word hard-coded, and once a
#: second subject was added, a disagreement inside THAT block printed a
#: path no answer has. Every caller says which block it is talking about.
_THE_ESTIMATE = "numeric_estimate"


def _disagree(name, shown, recorded, step_index: int) -> NoReturn:
    raise VerificationError(
        f"{name} is {shown!r} and the step that produced it "
        f"recorded {recorded!r}; a reader and an auditor are being shown two "
        "different runs",
        rule=_RULE, step_index=step_index,
    )


def _chain_record(steps) -> dict:
    """Everything the chain recorded, by name, with the step it came from.

    The terminal step alone used to be the whole of the comparison, which
    made the rule's reach a fact about which estimator ran rather than
    about what a reader is shown: a mediator named in the step that
    identified it and nowhere after was a name nobody compared. Later
    steps win, since a chain that names a thing twice is naming its own
    later state, and the estimate sits at the end of the chain.

    Built once. It used to be a search per name, which unwrapped whatever
    it found on every ask — and once the envelope is walked to its leaves
    there are hundreds of asks and some of the things found are moment
    matrices.

    A step's OUTPUT is as much a thing the chain wrote down as its inputs
    are, and it is where a decomposition's numbers live: a joint mediation
    answer records its four controlled effects on the way out, never on
    the way in, so the block a reader reads them from agreed with nothing.
    Read by the marker the serialisation already uses rather than by a
    list of which rules produce mappings: ``items`` as a mapping IS how a
    serialised mapping is spelled here, and an output that is a typed
    VALUE — ``{"kind": "structural_result", "value": true}`` — names
    nothing. Reading such a wrapper's own keys as names was measured: its
    ``kind`` then answers for every block that has one, and twenty-one
    honest bootstrap records were called a different run.
    """
    record: dict = {}
    for index, step in enumerate(steps):
        named: dict = {}
        inputs = step.get("inputs")
        if isinstance(inputs, dict):
            named.update(inputs)
        produced = step.get("output")
        if isinstance(produced, dict) and isinstance(produced.get("items"),
                                                     dict):
            named.update(produced["items"])
        for name, value in named.items():
            record[name] = (index, _plain(value))
    record.update(_joined_names(record))
    return record


def _joined_names(record: dict) -> dict:
    """Each entry of a recorded mapping, under the name it is read by.

    The walk on the reader's side stops at a leaf and asks the record for
    ``f"{parent}_{leaf}"``, which is what a derivation input carries where
    a block is a sub-answer. The expansion above goes one level, so a
    mapping the chain recorded sits here whole and no joined spelling ever
    reached inside it: why a controlled-effect grid was not solved is
    recorded as one mapping and shown as three fields, and not one of them
    was compared with anything.

    Only PREFIXED names are added, and that is the difference between this
    and offering the nested block itself as a subject on the reader's
    side. The other way was measured and is wrong: a nested block's name
    is its role in its parent, so a decomposition's ``cde`` is a table of
    intervals where the step's ``cde`` is the cell values it was
    summarised from, and comparing them calls an honest answer two
    different runs.

    A name the chain really recorded is never displaced by one derived
    here, and a joined name two mappings both produce is dropped rather
    than arbitrated -- an ambiguity is not a disagreement, which is the
    rule the spelling side already follows.

    A typed wrapper is skipped: its keys are ``kind`` and a pointer, and
    ``kind`` is not the name of anything it contains.
    """
    out: dict = {}
    clashed: set = set()
    for name, (index, value) in record.items():
        if not isinstance(value, dict) or "kind" in value:
            continue
        for leaf, inner in value.items():
            joined = f"{name}_{leaf}"
            if joined in record or joined in clashed:
                continue
            if joined in out:
                del out[joined]
                clashed.add(joined)
                continue
            out[joined] = (index, _plain(inner))
    return out


def _named_subjects(estimate: dict, path: tuple = ()):
    """Every leaf of the envelope that speaks about the run as a whole.

    Descent stops at a list. That is the line between the two, and it is
    structural rather than a name: a list is a series, and each entry
    speaks about its own subject. A dose-response curve's fifth point
    carries ``ci_lower``, and so does the step — but the point's is that
    dose's interval and the step's is the run's. Measured on the
    forty-four shapes: comparing them anyway disagrees forty-seven times,
    every one of them an honest answer, which is this rule calling a
    truthful envelope two different runs.

    The envelope's outermost keys are offered whatever shape they hold —
    that is the run's own vocabulary, and a step sometimes records only a
    block's discriminator. Deeper in, only VALUES are offered and not
    blocks: a nested block's name describes its role inside its parent,
    and a role is not the record's vocabulary. Measured — the coefficient
    table under a mediation decomposition holds one entry per mediator
    under the name ``mediators``, and the step records ``mediators`` as
    the list of which mediators there are. One word, a function and its
    domain, and comparing them calls an honest answer two different runs.

    A list is offered whole, because element by element is how a reordered
    sampling grid is caught. Descent stops at it: a series' entries are
    each their own subject, and what a step records under one of their
    field names is the run's. Below a list the correspondence would be to
    a recorded SERIES rather than to a recorded field, which is what
    ``_check_stratum_table`` does with the columns.
    """
    for key, value in estimate.items():
        if not path or not isinstance(value, dict):
            yield path + (key,), value
        if isinstance(value, dict):
            yield from _named_subjects(value, path + (key,))


#: The blocks a reader reads a run's own numbers from. The rule used to
#: name one of them, which made its reach a fact about which block an
#: estimator happened to write into rather than about what a reader is
#: shown — the same mistake this module already records making one level
#: down, when asking only the envelope's outer keys made the reach a fact
#: about how deep an estimator nests.
_SUBJECTS = (_THE_ESTIMATE, "extensions")


def _subjects(result: dict):
    """Each block a reader reads, named."""
    for key in _SUBJECTS:
        block = result.get(key)
        if isinstance(block, dict):
            yield key, block


def _unambiguous(block: dict) -> frozenset:
    """Leaf names this block uses in exactly one place.

    Whether a leaf's own name means anything is not a fact about how deep
    it sits. It is a fact about whether anything else answers to the same
    word.
    """
    claims: dict = {}
    for path, _ in _named_subjects(block):
        claims[path[-1]] = claims.get(path[-1], 0) + 1
    return frozenset(name for name, count in claims.items() if count == 1)


def _claimed_outright(result: dict, block: dict) -> frozenset:
    """Words another block claims as its own, which this one may not take.

    A leaf deep inside a block may be compared under its bare name where
    nothing else answers to that word, and once there is more than one
    block the question "anything else" has to reach across them. Asking it
    as a plain count over both was measured and is wrong in the other
    direction: two blocks show the same run's ``p_y_do_x0``, a count calls
    that ambiguity, and 73 leaves of ``numeric_estimate`` — the
    probabilities of causation among them — stopped being compared at all.

    What tells the two apart is not how often a word appears but whether
    some block claims it OUTRIGHT. A key at a block's top level is that
    block's own vocabulary: ``numeric_estimate.method`` is the method that
    ran, so an estimand's nested ``method`` deeper in another block is a
    different fact wearing the same word. A word no block claims at its
    top level belongs to no block, and a leaf carrying it means the same
    thing wherever it sits.
    """
    out: set = set()
    for _key, other in _subjects(result):
        if other is not block:
            out |= set(other)
    return frozenset(out)


def _spellings(path: tuple, unambiguous: frozenset):
    """What the record may call this leaf.

    At the top level, its own name: that is the run's own vocabulary and
    the record speaks it.

    Inside a block, the block's name joined to it, which is what a
    derivation input carries where a block is a sub-answer: ``pn: {lower,
    upper}`` beside ``pn_lower``. Joining is a rule about the two shapes.
    Guessing at spelling is not, and the difference was measured: a variant
    that also stripped a plural matched ``pns.lower`` to ``pn_lower`` and
    refused an honest answer.

    And, failing that, its own name — but only where it is the only leaf on
    this envelope answering to that word. What made the joined name the
    ONLY deep spelling was the observation that most of what an answer
    reports about itself is vocabulary relative to whichever answer carries
    it: ``ps.ci_lower`` is the probability of sufficiency's interval and
    the step's ``ci_lower`` is the run's, so comparing them calls a
    truthful envelope two different runs. That observation is right, and
    reading it as a rule about DEPTH was what cost: ``p_y_do_x0`` and
    ``observed_x`` and a counterfactual cell's own ``lower`` mean one thing
    on the whole envelope and are recorded flat, and every one of them sat
    unreachable behind a spelling no step would ever carry.

    Relative or absolute is a question about the envelope, and the
    envelope answers it: three blocks say ``ci_lower`` and one says
    ``p_y_do_x0``. Where two leaves claim a word, this asks nothing — an
    ambiguity is not a disagreement, and the sweep gate is what keeps the
    silence visible.
    """
    if len(path) == 1:
        yield path[0]
        return
    yield f"{path[-2]}_{path[-1]}"
    if path[-1] in unambiguous:
        yield path[-1]


def verify_numeric_display_agrees(result: dict, derivation: dict) -> None:
    """Hold what a reader is shown to the chain it was recorded from.

    Every name the two share must name the same thing. The subject is
    every block of :data:`_SUBJECTS` the answer carries, because which of
    them an estimator wrote its numbers into is a fact about the estimator
    and not about what a reader reads: a joint mediation decomposition
    reports four controlled effects under ``extensions``, recorded in the
    step that produced them, and not one of them was compared with
    anything.

    A result with none of those blocks has no second copy and is nothing
    to check; one whose derivation ends in a step recording no inputs is
    refused, because what a reader is shown then rests on a record nobody
    can read.
    """
    blocks = list(_subjects(result))
    if not blocks:
        return
    steps = (derivation or {}).get("steps") or ()
    if not steps:
        raise VerificationError(
            "a numeric_estimate rides on a derivation with no steps; the "
            "number a reader is shown was recorded from nothing",
            rule=_RULE,
        )
    terminal = steps[-1]
    inputs = terminal.get("inputs")
    if not isinstance(inputs, dict):
        raise VerificationError(
            f"the terminal step {terminal.get('rule')!r} records no inputs, "
            "so the numeric_estimate beside it agrees with nothing",
            rule=_RULE, step_index=len(steps) - 1,
        )

    at = len(steps) - 1
    record = _chain_record(steps)
    for key, block in blocks:
        own = _unambiguous(block) - _claimed_outright(result, block)
        for path, shown in _named_subjects(block):
            for name in _spellings(path, own):
                if name not in record:
                    continue
                where, recorded = record[name]
                if not _agree(shown, recorded):
                    _disagree(f"{key}." + ".".join(path), shown, recorded,
                              where)
                break

    # The two nested views are shapes ``numeric_estimate`` has and the
    # other blocks do not; they stay asked of it alone rather than of
    # whatever else happens to carry a key of the same name.
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, dict):
        for view, prefix in _PREFIXED_VIEWS.items():
            _check_prefixed_view(estimate.get(view), inputs, view, prefix, at)
        for view, prefix in _PARTLY_PREFIXED_VIEWS.items():
            _check_prefixed_view(estimate.get(view), inputs, view, prefix, at,
                                 total=False)
        _check_the_entry_the_step_produced(estimate, inputs, at)
        _check_stratum_table(estimate, inputs, at)


def _check_prefixed_view(view, inputs: dict, name: str, prefix: str,
                         at: int, total: bool = True) -> None:
    """A confidence set beside the fields it was recorded from.

    Total where it applies: once the step records anything under the
    prefix, every leaf of the view must be there, because a view standing
    beside a partial record is a set of numbers with a hole in it and
    nothing saying so.

    Where the step records NOTHING under the prefix, this view is not the
    terminal step's to account for. That is not a hole either: the
    over-identified path records moment MATRICES instead — they do not fit
    the derivation-input serialisation — and its set is re-solved from
    them by ``verify_iv_overid_numeric``, endpoints, kind and critical
    value alike. The condition is written as "the prefix is absent
    entirely" rather than as a list of methods, so a method that starts
    recording half a set is caught by the clause above rather than
    excused by a name.

    ``total=False`` is for the blocks of :data:`_PARTLY_PREFIXED_VIEWS`,
    which carry leaves the step never produced. The comparison itself is
    the same one; what changes is that a leaf the record does not answer
    for is left to whoever re-derives it.
    """
    if not isinstance(view, dict):
        return
    if not any(key.startswith(prefix) for key in inputs):
        return
    for leaf, shown in view.items():
        key = f"{prefix}{leaf}"
        if key not in inputs:
            if not total:
                continue
            _disagree(f"{_THE_ESTIMATE}.{name}.{leaf}", shown,
                      f"<nothing: the step records no {key}>", at)
        if not _agree(shown, _plain(inputs[key])):
            _disagree(f"{_THE_ESTIMATE}.{name}.{leaf}", shown,
                      _plain(inputs[key]), at)


def _check_the_entry_the_step_produced(estimate: dict, inputs: dict,
                                       at: int) -> None:
    """The one row of a series that is the run the step recorded.

    A series is not offered to the name-joining walk above, and the reason
    measured there holds: a curve's fifth point carries ``ci_lower`` and so
    does the step, and they are two different intervals. What that reason
    leaves out is that one of those points IS the step's — a terminal step
    reporting a point reports one dose, not the curve — and the point it
    reports is what says which.

    So the row is found by the number rather than by its position. On the
    four answers that carry both, the row is the last one; being last is
    where they happen to sit and not what they claim, and a rule written on
    the position would hold a reordered curve to the wrong interval.
    """
    for view, (names_it, named_there, fields) in \
            _THE_ENTRY_THE_STEP_PRODUCED.items():
        series = estimate.get(view)
        if not isinstance(series, list) or names_it not in inputs:
            continue
        wanted = _plain(inputs[names_it])
        found = [row for row in series
                 if isinstance(row, dict) and named_there in row
                 and _agree(row[named_there], wanted)]
        if len(found) != 1:
            continue
        row = found[0]
        where = f"{_THE_ESTIMATE}.{view}[{named_there}={wanted!r}]"
        for field in fields:
            if field not in inputs or field not in row:
                continue
            if not _agree(row[field], _plain(inputs[field])):
                _disagree(f"{where}.{field}", row[field],
                          _plain(inputs[field]), at)


def _check_stratum_table(estimate: dict, inputs: dict, at: int) -> None:
    """The stratum table a reader is shown, against the columns recorded.

    Two of its aggregates and six of each row's cells were recorded. The
    other three cells — how many units the stratum held, and how they
    split between the instrument's arms — were not, and are held instead
    to the arithmetic that ties them to what was: a weight is that
    stratum's share of the sample, and the two arms are the whole of the
    stratum. Both are relations rather than copies, so both survive a
    forger who edits one number and recomputes nothing.
    """
    table = estimate.get("stratified_wald")
    if not isinstance(table, dict):
        return
    subject = f"{_THE_ESTIMATE}.stratified_wald"
    for leaf, key in _STRATUM_AGGREGATES.items():
        if key not in inputs:
            _disagree(f"{subject}.{leaf}", table.get(leaf),
                      f"<nothing: the step records no {key}>", at)
        if not _same_number(table.get(leaf), inputs[key]):
            _disagree(f"{subject}.{leaf}", table.get(leaf),
                      inputs[key], at)

    rows = table.get("strata") or ()
    columns: dict[str, list] = {}
    for leaf, key in _STRATUM_COLUMNS.items():
        recorded = inputs.get(key)
        items = recorded.get("items") if isinstance(recorded, dict) \
            else recorded
        if not isinstance(items, list):
            _disagree(f"{subject}.strata[*].{leaf}", "shown",
                      f"<nothing: the step records no {key}>", at)
        if len(items) != len(rows):
            _disagree(f"{subject}.strata", f"{len(rows)} rows",
                      f"{len(items)} entries in {key}", at)
        columns[leaf] = items

    # Which cell each row describes is the one thing the step does not
    # record, and it is what says which stratum a reader is looking at.
    # Held to the two facts that survive without a record: a row's
    # coordinates are as long as the conditioning it is over, and two rows
    # of one table are two different cells. A relabelled row lands on a
    # cell that is already taken.
    order = table.get("conditioning_order") or ()
    seen: set = set()
    for index, row in enumerate(rows):
        values = (row or {}).get("values")
        if not isinstance(values, list) or len(values) != len(order):
            _disagree(f"{subject}.strata[{index}].values", values,
                      f"one coordinate per conditioning variable "
                      f"{list(order)}", at)
        cell = tuple(values)
        if cell in seen:
            _disagree(f"{subject}.strata[{index}].values", list(cell),
                      "a cell no other row of this table already describes",
                      at)
        seen.add(cell)

    sample_size = estimate.get("sample_size")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _disagree(f"{subject}.strata[{index}]", row, "an object", at)
        for leaf, items in columns.items():
            if not _same_number(row.get(leaf), items[index]):
                _disagree(f"{subject}.strata[{index}].{leaf}",
                          row.get(leaf), items[index], at)
        n_obs = row.get("n_obs")
        high, low = row.get("n_instrument_high"), row.get("n_instrument_low")
        if high is not None and low is not None and n_obs is not None:
            if int(high) + int(low) != int(n_obs):
                _disagree(f"{subject}.strata[{index}].n_obs", n_obs,
                          f"{high} + {low} = {int(high) + int(low)}", at)
        if n_obs is not None and isinstance(sample_size, (int, float)) \
                and sample_size:
            if not _same_number(row.get("weight"), n_obs / sample_size):
                _disagree(f"{subject}.strata[{index}].weight",
                          row.get("weight"), f"{n_obs}/{sample_size}", at)
