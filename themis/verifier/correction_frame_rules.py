"""What a correction says it corrected, held to the question that was asked.

Six methods correct a mismeasured variable, and each already has a verifier
that re-derives its number from the block's own sufficient statistics. What
those verifiers read the block FOR is input: which columns the design had,
which values the variable takes, which value the risk is reported for, where
that value sits in the list. Read as an input a label cannot be wrong —
change it and the arithmetic re-derives a different number that agrees with
itself everywhere, and every rule passes on an answer to a question nobody
asked. Measured on the suite's own answers: forty-eight leaves of these
blocks could be edited and still pass the public door, and the ones that
name rather than count could be edited without moving a single number a
reader is shown.

So this module asks the labels a different question. A label here is not an
input but a CLAIM, and each kind of claim has somewhere it can be held:

- a name the envelope already carries — the exposure, the design's columns,
  the adjustment set, the size of the sample;
- a value the program already declares — which values a variable takes,
  which value the query asked about;
- a position in a list lying beside it — the target's index, the exposure's;
- a fact the numbers beside it decide — whether a corrected risk left the
  simplex;
- a property of the object itself — a confusion matrix's columns are
  distributions, and the determinant recorded beside it is that matrix's;
- and, for anything a block writes down twice, the other writing.

That last question is not about corrections and is not written as though it
were. Wherever a block on the envelope carries its own
``sufficient_statistics``, the two are one run written down twice, and every
name they share must name one value. WHICH blocks those are is a fact about
the envelope's shape rather than a list kept here, and that one question
closes nineteen of the forty-eight without knowing what any of them mean.
Twelve blocks carry statistics today and six are corrections; on the other
six the question is asked and finds nothing, because those record their
statistics and nothing else — which is not a skip but an answer, and it
changes to a check the day one of them shows a reader a fact it also
audited.

A claim with nowhere to be held is left alone rather than held to a guess.
Three of these blocks name a functional ``form`` and no mechanism audit
names one back, because a nonparametric standardisation assumes no
functional shape and the audit is right to be silent about it; those three
labels stay unheld, and the sweep gate is what keeps that visible. The same
convention governs a program that declares no domain for a variable: silence
is not a claim, and a correction cannot be contradicted about a value set
nobody wrote down.

**Independence pin:** this module MUST NOT import from ``themis.estimation``.
Everything it compares is on the result or in the program the caller
submitted. It is kin to ``display_copy_rules`` — same species of question,
different pair: that one holds what a reader is shown to what the derivation
recorded, and this one holds what a block says about itself to everything
that already said it.
"""
from __future__ import annotations

from typing import Any, NoReturn

from .errors import VerificationError
from .program_copy_rules import query_of

#: The frame: what the block says it is about.
_RULE = "correction_frame_check"

#: The pair: a block and its own audit record.
_RECORD_RULE = "block_and_its_statistics_check"

#: Two recordings of one number differ by at most what JSON round-tripping
#: can introduce. Nothing here is an estimate of anything.
_TOL = 1e-9

_STATS = "sufficient_statistics"


def _reject(rule: str, message: str) -> NoReturn:
    raise VerificationError(message, rule=rule)


def _same(a: Any, b: Any) -> bool:
    """One value written twice — and ``True`` is not ``1``.

    Python calls a boolean an integer, so a state list of ``[0, 1]`` would
    otherwise read as the declared domain ``[false, true]``, which is
    exactly the frame this module exists to hold.
    """
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if not isinstance(a, bool) and isinstance(a, (int, float)) \
            and not isinstance(b, bool) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= _TOL
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return a == b


def _distinct(values: list) -> bool:
    return not any(_same(values[i], values[j])
                   for i in range(len(values))
                   for j in range(i + 1, len(values)))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ------------------------------------------------------- one run, written twice


def _one_run_written_twice(node: Any, path: str) -> None:
    """Every name a block shares with its own sufficient statistics.

    The statistics are what an auditor re-derives the answer from, so they
    are held by that re-derivation; the block's own copy of the same fact is
    what a READER is shown, and until now nothing held the two together. A
    block was free to re-derive perfectly from a design it never showed, and
    show a design it never used.

    Asked of the whole envelope at every depth, because carrying one's own
    sufficient statistics is a shape and not a family. Which names the two
    sides happen to share is likewise not decided here: whatever they both
    say, they must say once.
    """
    if isinstance(node, dict):
        stats = node.get(_STATS)
        if isinstance(stats, dict):
            for key in sorted(set(node) & set(stats) - {_STATS}):
                if not _same(node[key], stats[key]):
                    _reject(
                        _RECORD_RULE,
                        f"{path}.{key} is {node[key]!r} and the same block's "
                        f"{_STATS}.{key} is {stats[key]!r}; the number was "
                        f"re-derived from one of them and a reader is shown "
                        f"the other")
        for key, value in node.items():
            _one_run_written_twice(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _one_run_written_twice(value, f"{path}[{index}]")


# ------------------------------------------- names the envelope already carries


def _the_names(estimate: dict, block: dict, where: str) -> None:
    treatment = estimate.get("treatment")
    adjustment = estimate.get("adjustment")

    exposure = block.get("exposure")
    if isinstance(exposure, str) and isinstance(treatment, str) \
            and exposure != treatment:
        _reject(
            _RULE,
            f"{where} says it corrected {exposure!r} and the answer is about "
            f"{treatment!r}; a correction applied to another variable leaves "
            f"the reported one uncorrected and says it was corrected")

    design = block.get("design_vars")
    if isinstance(design, list) and design and isinstance(treatment, str) \
            and isinstance(adjustment, list):
        lead = str(design[0])
        if lead != treatment:
            _reject(
                _RULE,
                f"{where}.design_vars leads with {lead!r} and the answer is "
                f"about {treatment!r}; the correction is written for the "
                f"exposure's own column")
        # The tail as a SET. That the covariates are the adjustment set is a
        # claim; the order they were fitted in is not one the envelope makes
        # anywhere, and requiring it would be requiring two lists nobody
        # promised to keep in step.
        rest, declared = {str(v) for v in design[1:]}, {str(a) for a in adjustment}
        if rest != declared:
            _reject(
                _RULE,
                f"{where}.design_vars adjusts for {sorted(rest)} and the "
                f"answer tells its reader it adjusted for {sorted(declared)}; "
                f"the number is then for a different comparison than the one "
                f"on the page")

    stats = block.get(_STATS)
    if not isinstance(stats, dict):
        return
    covariates = stats.get("adjustment_vars")
    if isinstance(covariates, list) and isinstance(adjustment, list):
        got, want = {str(v) for v in covariates}, {str(a) for a in adjustment}
        if got != want:
            _reject(
                _RULE,
                f"{where}.{_STATS}.adjustment_vars is {sorted(got)} and the "
                f"answer adjusts for {sorted(want)}; the audit trail is over "
                f"a different stratification than the answer claims")

    n, size = stats.get("n"), estimate.get("sample_size")
    if isinstance(n, int) and not isinstance(n, bool) and isinstance(size, int):
        if n != size:
            _reject(
                _RULE,
                f"{where}.{_STATS}.n is {n} and the answer was computed on "
                f"{size} rows; whichever is right, the precision a reader "
                f"reads off one of them belongs to the other")


# ---------------------------------------------- values the program declares


def _declared_domains(program: Any) -> dict[str, list]:
    """Predicate to the values the program says it takes.

    A program that declares none says nothing, and nothing is not a claim to
    be contradicted.
    """
    out: dict[str, list] = {}
    if not isinstance(program, dict):
        return out
    for stmt in program.get("statements") or ():
        if isinstance(stmt, dict) and stmt.get("kind") == "variable" \
                and isinstance(stmt.get("domain"), list):
            out[str(stmt.get("predicate"))] = list(stmt["domain"])
    return out


def _asked_value(program: Any, query_id: Any) -> Any:
    """Which value of the outcome the question was about.

    ``verify_answer_names_its_question`` holds the answer's variable NAMES to
    the query. A question is not only its variables: an effect query names a
    value of the target, and a discrete correction reports the risk of that
    value. The name half was held and the value half was not.
    """
    query = query_of(program, query_id) if isinstance(program, dict) else None
    if not isinstance(query, dict) or query.get("kind") != "effect":
        return None
    target = query.get("target")
    return target.get("value") if isinstance(target, dict) else None


def _the_values(estimate: dict, block: dict, where: str,
                domains: dict[str, list], asked: Any) -> None:
    for field, subject in (("states", estimate.get("treatment")),
                           ("outcome_states", estimate.get("outcome"))):
        values = block.get(field)
        if not isinstance(values, list):
            continue
        if not values or not _distinct(values):
            _reject(
                _RULE,
                f"{where}.{field} is {values!r}; a correction is indexed by "
                f"these, so two of them being one value is a row of the "
                f"confusion matrix standing for two states at once")
        declared = domains.get(str(subject))
        if declared is None:
            continue
        stray = [v for v in values
                 if not any(_same(v, d) for d in declared)]
        if stray:
            _reject(
                _RULE,
                f"{where}.{field} includes {stray!r} and the program says "
                f"{subject!r} takes {declared!r}; the correction is over "
                f"states the variable does not have")

    # Which value the risk is OF is a claim about the outcome, so it is read
    # against the outcome's states where the block distinguishes them and
    # against its only list where it does not.
    outcome_states = block.get("outcome_states") or block.get("states")
    if "target_value" in block:
        target = block["target_value"]
        if asked is not None and not _same(target, asked):
            _reject(
                _RULE,
                f"{where}.target_value is {target!r} and the query asked "
                f"about {asked!r}; every risk beside it is then the risk of "
                f"something else")
        if isinstance(outcome_states, list) \
                and not any(_same(target, s) for s in outcome_states):
            _reject(
                _RULE,
                f"{where}.target_value is {target!r} and the states it is "
                f"reported over are {outcome_states!r}; the risk is of an "
                f"outcome this correction never had a column for")

    # And how many risks there are is a claim about the exposure: one arm
    # per state it takes.
    arms = block.get("states")
    if isinstance(arms, list):
        for field in ("risks", "naive_risks"):
            row = block.get(field)
            if isinstance(row, list) and len(row) != len(arms):
                _reject(
                    _RULE,
                    f"{where}.{field} has {len(row)} entries and the exposure "
                    f"takes {len(arms)} states; a reader matching them up "
                    f"reads each risk against the wrong arm")


# -------------------------------------------- positions in the list beside them


def _the_positions(block: dict, where: str) -> None:
    stats = block.get(_STATS)
    if not isinstance(stats, dict):
        return
    for field, values, names in (
        ("target_index", block.get("outcome_states") or block.get("states"),
         "target_value"),
        ("exposure_index", block.get("design_vars"), "exposure"),
    ):
        index = stats.get(field)
        if index is None or not isinstance(values, list):
            continue
        if isinstance(index, bool) or not isinstance(index, int) \
                or not 0 <= index < len(values):
            _reject(
                _RULE,
                f"{where}.{_STATS}.{field} is {index!r} and there are "
                f"{len(values)} to point at; the correction was re-derived "
                f"through a position that is not one")
        if names in block and not _same(values[index], block[names]):
            _reject(
                _RULE,
                f"{where}.{_STATS}.{field} points at {values[index]!r} and "
                f"the block's {names} is {block[names]!r}; the arithmetic ran "
                f"on one and a reader is told the other")


# ------------------------------------------- a fact the numbers beside it decide


def _the_flags(block: dict, where: str) -> None:
    """Whether the correction left the simplex, against what it returned.

    A one-sided flag: shown, it tells a reader the inversion produced
    something that is not a probability and the answer should be distrusted;
    withheld, it says there is nothing to disclose. Both directions are
    asked, because both are lies a reader cannot see through.

    Asked only where the risks are ON the block. One route flags without
    showing them — the per-cell differential correction reports the verdict
    and not the numbers it is about — and there this rule has nothing to
    compare and says so by leaving the leaf where the sweep can see it.
    """
    if "out_of_simplex" not in block:
        return
    risks = block.get("risks")
    if not isinstance(risks, list) or not risks:
        return
    numbers = [_num(r) for r in risks]
    if any(n is None for n in numbers):
        return
    outside = [n for n in numbers if n is not None
               and not -_TOL <= n <= 1.0 + _TOL]
    flagged = bool(block["out_of_simplex"])
    if flagged and not outside:
        _reject(
            _RULE,
            f"{where}.out_of_simplex says the correction left the simplex and "
            f"every risk it returned is a probability: {risks!r}; a reader is "
            f"told to distrust a number for a reason the block disproves")
    if outside and not flagged:
        _reject(
            _RULE,
            f"{where} returned {outside!r}, which are not probabilities, and "
            f"out_of_simplex is false; the one disclosure that would tell a "
            f"reader the inversion failed is the one that was withheld")


# ---------------------------------- a property of the object the block carries


def _determinant(matrix: list) -> float:
    """By elimination, which shares no line with however it was recorded."""
    rows = [[float(v) for v in row] for row in matrix]
    size, sign = len(rows), 1.0
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-300:
            return 0.0
        if pivot != column:
            rows[column], rows[pivot] = rows[pivot], rows[column]
            sign = -sign
        for r in range(column + 1, size):
            factor = rows[r][column] / rows[column][column]
            for c in range(column, size):
                rows[r][c] -= factor * rows[column][c]
    product = sign
    for i in range(size):
        product *= rows[i][i]
    return product


def _is_matrix(value: Any) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(row, list) and len(row) == len(value)
                    and all(_num(v) is not None for v in row)
                    for row in value))


def _det_name(key: str) -> str:
    """What the determinant of this matrix is called beside it.

    One convention, not a table: ``confusion_matrix`` is answered by ``det``
    and ``confusion_matrix_exposure`` by ``det_exposure``, and a row of a
    per-level list spells its matrix ``matrix`` and its determinant ``det``.
    """
    if key.startswith("confusion_matrix"):
        return "det" + key[len("confusion_matrix"):]
    return "det"


def _the_matrices(node: Any, where: str) -> None:
    """Every matrix that claims to be a misclassification channel.

    Two properties, and each is the whole of what makes the correction mean
    anything. Its columns are distributions — column ``j`` is where a unit
    whose true state is ``j`` was recorded, and those probabilities are over
    somewhere — so a column that does not sum to one is not a channel and
    the inversion beside it is not a correction. And the determinant
    recorded beside it is the one a reader would compute: it is what the
    ledger's invertibility premise is judged on, and how near zero it sits
    is how much the inversion multiplies the sampling noise.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if (key == "matrix" or key.startswith("confusion_matrix")) \
                    and _is_matrix(value):
                _check_channel(value, f"{where}.{key}")
                recorded = node.get(_det_name(key))
                theirs = _num(recorded)
                if theirs is not None:
                    ours = _determinant(value)
                    if abs(ours - theirs) > _TOL * max(1.0, abs(ours)):
                        _reject(
                            _RULE,
                            f"{where}.{_det_name(key)} is {recorded!r} and the "
                            f"matrix beside it has determinant {ours!r}; the "
                            f"premise a reader accepts on that figure is "
                            f"about a different matrix")
            else:
                _the_matrices(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _the_matrices(value, f"{where}[{index}]")


def _check_channel(matrix: list, where: str) -> None:
    for index, row in enumerate(matrix):
        for column, value in enumerate(row):
            number = _num(value)
            if number is None or not -_TOL <= number <= 1.0 + _TOL:
                _reject(
                    _RULE,
                    f"{where}[{index}][{column}] is {value!r}, which is not a "
                    f"probability; the entries of a misclassification channel "
                    f"are P(recorded | true)")
    for column in range(len(matrix)):
        total = sum(float(row[column]) for row in matrix)
        if abs(total - 1.0) > 1e-8:
            _reject(
                _RULE,
                f"{where} column {column} sums to {total!r}; a unit whose true "
                f"state is that column was recorded as something, so the "
                f"column is a distribution and the inversion is only a "
                f"correction while it is one")


def _the_levels(block: dict, where: str, domains: dict[str, list]) -> None:
    """Which cell each per-level channel belongs to.

    A differential channel is one matrix per cell of the variables the error
    is differential BY, so a level is as long as that list, its coordinates
    are values those variables take, and two rows of the table are two
    different cells. A relabelled row lands on a cell that is already taken.
    """
    by = block.get("differential_by")
    if not isinstance(by, list):
        return
    for field in ("confusion_matrices", "confusion_matrices_by_level"):
        rows = block.get(field)
        if not isinstance(rows, list):
            continue
        seen: list = []
        for index, row in enumerate(rows):
            level = (row or {}).get("level") if isinstance(row, dict) else None
            if not isinstance(level, list) or len(level) != len(by):
                _reject(
                    _RULE,
                    f"{where}.{field}[{index}].level is {level!r} and the "
                    f"error is differential by {by!r}; a channel whose cell "
                    f"is not a cell was applied to some set of units nobody "
                    f"can name")
            for position, value in enumerate(level):
                declared = domains.get(str(by[position]))
                if declared is not None \
                        and not any(_same(value, d) for d in declared):
                    _reject(
                        _RULE,
                        f"{where}.{field}[{index}].level names {value!r} for "
                        f"{by[position]!r}, which the program says takes "
                        f"{declared!r}")
            if any(_same(level, other) for other in seen):
                _reject(
                    _RULE,
                    f"{where}.{field}[{index}].level is {level!r} and another "
                    f"row of the same table already describes that cell; one "
                    f"cell then has two channels and another has none")
            seen.append(level)


# --------------------------------------- the run's own words about the run


def _the_form_the_audit_named(result: dict, estimate: dict) -> None:
    """A block's name for what it did, and the audit's name for the same.

    ``extensions.mechanism_audit`` exists so a functional-form choice is an
    auditable object rather than a word in a string. Where a block also
    names its form, the two are one choice recorded twice.

    Where the audit names none, nothing is claimed and nothing is compared:
    a nonparametric standardisation assumes no shape, so its block's form is
    a description of a route and the audit is right to be silent. That
    leaves those forms unheld, which the sweep gate reports rather than
    hides.
    """
    audit = (result.get("extensions") or {}).get("mechanism_audit")
    if not isinstance(audit, dict):
        return
    named = {m["form"] for m in audit.get("mechanisms") or ()
             if isinstance(m, dict) and isinstance(m.get("form"), str)}
    shown = {b["form"] for b in estimate.values()
             if isinstance(b, dict) and isinstance(b.get("form"), str)}
    if not named or not shown:
        return
    if named != shown:
        _reject(
            _RULE,
            f"the answer's blocks say they were produced by {sorted(shown)} "
            f"and the mechanism audit a reader judges the shape assumption "
            f"on says {sorted(named)}; the premise on the ledger belongs to "
            f"a model other than the one that ran")


def _the_seed(result: dict, estimate: dict) -> None:
    """The seed a simulation says it used, against the seed the run declares.

    Where an answer is produced by simulation, the seed is the whole of what
    makes it reproducible. A block showing one the run did not use sends a
    reader who reruns it to a different ladder, and the number they get back
    disagreeing with the number on the page tells them nothing about either.
    """
    declared = (result.get("estimation_context") or {}).get("random_state")
    if declared is None:
        return
    for name, block in estimate.items():
        if not isinstance(block, dict) or "random_state" not in block:
            continue
        shown = block["random_state"]
        if shown is not None and not _same(shown, declared):
            _reject(
                _RULE,
                f"{name}.random_state is {shown!r} and the run was seeded "
                f"{declared!r}; a reader who reruns it draws a different "
                f"simulation and cannot tell a disagreement from a bug")


# ------------------------------------------------------------------- the door


def verify_correction_frame(result: Any, program: Any, *, query_id: Any
                            ) -> None:
    """Hold every block's account of itself to what already said it.

    Takes the whole result, because two of the questions are about things
    that are not on the estimate: the seed the run declares, and the shape
    the mechanism audit says was assumed.

    Raises ``VerificationError`` when a block names a variable, a value set,
    a position or a matrix that the program, the envelope, the audit or the
    block's own record contradicts. Returns ``None`` for a result carrying
    no numeric estimate, which has made no such claim.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return

    _one_run_written_twice(estimate, "")

    domains = _declared_domains(program)
    asked = _asked_value(program, query_id)
    for name, block in estimate.items():
        if not isinstance(block, dict):
            continue
        _the_names(estimate, block, name)
        _the_values(estimate, block, name, domains, asked)
        _the_positions(block, name)
        _the_flags(block, name)
        _the_matrices(block, name)
        # Asked of the block and of its own record separately: the two spell
        # the per-cell table differently — ``confusion_matrices`` beside
        # ``confusion_matrices_by_level`` — so the question that holds a
        # block to its statistics cannot pair them, and each answers for its
        # own copy.
        _the_levels(block, name, domains)
        stats = block.get(_STATS)
        if isinstance(stats, dict):
            _the_levels(stats, f"{name}.{_STATS}", domains)

    _the_form_the_audit_named(result, estimate)
    _the_seed(result, estimate)
