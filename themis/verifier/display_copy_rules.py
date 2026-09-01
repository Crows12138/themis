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
    it comes back unchanged and simply will not equal anything a reader
    is shown.
    """
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


def _same_number(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= _TOL


def _agree(shown, recorded) -> bool:
    """Whether two recordings of one fact say the same thing.

    Numbers compare within the distance JSON round-tripping can introduce;
    containers compare element-wise so a nested tuple inside a mapping is
    reached. One asymmetry is real and not a shape mismatch: where a step
    records only the DISCRIMINATOR of a block the estimate carries whole —
    the reason an interaction could not be reported, say — what the two
    have in common is the kind, and that is what is compared. Silence
    there would let the two names drift apart.
    """
    if isinstance(shown, dict) and isinstance(recorded, str):
        return shown.get("kind") == recorded
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
        return set(shown) == set(recorded) and all(
            _agree(shown[k], recorded[k]) for k in shown)
    return shown == recorded


def _disagree(name, shown, recorded, step_index: int) -> NoReturn:
    raise VerificationError(
        f"numeric_estimate.{name} is {shown!r} and the step that produced it "
        f"recorded {recorded!r}; a reader and an auditor are being shown two "
        "different runs",
        rule=_RULE, step_index=step_index,
    )


def _recorded_anywhere(steps, name: str):
    """Where in the chain this name was recorded, and with what.

    The terminal step alone used to be the whole of the comparison, which
    made the rule's reach a fact about which estimator ran rather than
    about what a reader is shown: a mediator named in the step that
    identified it and nowhere after was a name nobody compared. Later
    steps win, since a chain that names a thing twice is naming its own
    later state, and the estimate sits at the end of the chain.
    """
    for index in range(len(steps) - 1, -1, -1):
        inputs = steps[index].get("inputs")
        if isinstance(inputs, dict) and name in inputs:
            return index, _plain(inputs[name])
    return None


def verify_numeric_display_agrees(result: dict, derivation: dict) -> None:
    """Hold ``numeric_estimate`` to the chain it was recorded from.

    Every name the two share must name the same thing. A result with no
    numeric estimate has no second copy and is nothing to check; one whose
    derivation ends in a step recording no inputs is refused, because the
    estimate then rests on a record nobody can read.
    """
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
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
    for name, shown in estimate.items():
        recorded_at = _recorded_anywhere(steps, name)
        if recorded_at is None:
            continue
        where, recorded = recorded_at
        if not _agree(shown, recorded):
            _disagree(name, shown, recorded, where)

    for view, prefix in _PREFIXED_VIEWS.items():
        _check_prefixed_view(estimate.get(view), inputs, view, prefix, at)
    _check_stratum_table(estimate, inputs, at)


def _check_prefixed_view(view, inputs: dict, name: str, prefix: str,
                         at: int) -> None:
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
    """
    if not isinstance(view, dict):
        return
    if not any(key.startswith(prefix) for key in inputs):
        return
    for leaf, shown in view.items():
        key = f"{prefix}{leaf}"
        if key not in inputs:
            _disagree(f"{name}.{leaf}", shown,
                      f"<nothing: the step records no {key}>", at)
        if not _agree(shown, _plain(inputs[key])):
            _disagree(f"{name}.{leaf}", shown, _plain(inputs[key]), at)


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
    for leaf, key in _STRATUM_AGGREGATES.items():
        if key not in inputs:
            _disagree(f"stratified_wald.{leaf}", table.get(leaf),
                      f"<nothing: the step records no {key}>", at)
        if not _same_number(table.get(leaf), inputs[key]):
            _disagree(f"stratified_wald.{leaf}", table.get(leaf),
                      inputs[key], at)

    rows = table.get("strata") or ()
    columns: dict[str, list] = {}
    for leaf, key in _STRATUM_COLUMNS.items():
        recorded = inputs.get(key)
        items = recorded.get("items") if isinstance(recorded, dict) \
            else recorded
        if not isinstance(items, list):
            _disagree(f"stratified_wald.strata[*].{leaf}", "shown",
                      f"<nothing: the step records no {key}>", at)
        if len(items) != len(rows):
            _disagree("stratified_wald.strata", f"{len(rows)} rows",
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
            _disagree(f"stratified_wald.strata[{index}].values", values,
                      f"one coordinate per conditioning variable "
                      f"{list(order)}", at)
        cell = tuple(values)
        if cell in seen:
            _disagree(f"stratified_wald.strata[{index}].values", list(cell),
                      "a cell no other row of this table already describes",
                      at)
        seen.add(cell)

    sample_size = estimate.get("sample_size")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _disagree(f"stratified_wald.strata[{index}]", row, "an object", at)
        for leaf, items in columns.items():
            if not _same_number(row.get(leaf), items[index]):
                _disagree(f"stratified_wald.strata[{index}].{leaf}",
                          row.get(leaf), items[index], at)
        n_obs = row.get("n_obs")
        high, low = row.get("n_instrument_high"), row.get("n_instrument_low")
        if high is not None and low is not None and n_obs is not None:
            if int(high) + int(low) != int(n_obs):
                _disagree(f"stratified_wald.strata[{index}].n_obs", n_obs,
                          f"{high} + {low} = {int(high) + int(low)}", at)
        if n_obs is not None and isinstance(sample_size, (int, float)) \
                and sample_size:
            if not _same_number(row.get("weight"), n_obs / sample_size):
                _disagree(f"stratified_wald.strata[{index}].weight",
                          row.get("weight"), f"{n_obs}/{sample_size}", at)
