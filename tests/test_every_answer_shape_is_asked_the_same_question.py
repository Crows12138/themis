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
being closed. A leaf that appears in it without being added deliberately is
a new hole, and this test says its name.

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
An instrument that reports a hole honestly is how the hole gets closed;
this is the second one it has found about itself.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

import themis
from themis.verifier import verify_answer_names_its_question
from themis.verifier.errors import VerificationError

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


def _bends(value):
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
    """
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value + 7, 0, value * 2 + 1, -abs(value) - 1]
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return [0.9 if value < 0.5 else 0.1, value / 2 + 0.01, 0.0]
        return [value * 3.0 + 1.0, -value - 1.0, 0.0, value / 2.0]
    if isinstance(value, str):
        return [value + "_forged", "", "x"]
    return []


def _tamper(result, path, value):
    bad = copy.deepcopy(result)
    node = bad
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


def _asked(result):
    """Every leaf this gate puts a question to, once per distinct shape.

    The gate's SCOPE, and the only statement of it: what ``_sweep`` bends
    and what the scope test measures are the same walk, so a narrowing is
    one edit and it fails rather than passes. For twelve frontiers the
    scope was a subscript inside the sweep — ``result["numeric_estimate"]``
    — and nothing anywhere said so.
    """
    seen = set()
    for path, value in _leaves(result):
        shape = _shape_of(path)
        if shape in seen:
            continue
        seen.add(shape)
        yield shape, path, value


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
    asked = {shape for shape, _, _ in _asked(result)}
    doors = _reading_doors(program, result)
    if not doors:
        return sorted(asked), asked

    survived = []
    for shape, path, value in _asked(result):
        for bent in _bends(value):
            if not _is_material(value, bent):
                continue
            bad = _tamper(result, path, bent)
            if any(_refuses(door, program, bad) for door in doors):
                continue
            survived.append(shape)
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
    growing it cannot happen by accident."""
    total = sum(len(v) for v in UNWITNESSED.values())
    assert total == 849, total
    assert len(SHAPES) == 64, len(SHAPES)


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
    "confidence",
    "confidence_sources",
    "estimator_dependency_missing",
    "estimator_fallback",
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
    and an answer with no number was never a row. Eleven of the fifteen
    cases this repository documents come back ``needs_investigation``,
    which is what the data-gap diagnosis IS. Widening the corpus to those
    answers brought two of the seven in, and the five left are blocks no
    answer this suite produces has ever written.
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
    """
    top_level, asked_top = set(), set()
    asked_total = 0
    for pair in SHAPES.values():
        top_level.update(pair["result"])
        shapes = [shape for shape, _, _ in _asked(pair["result"])]
        asked_total += len(shapes)
        asked_top.update(shape.split(".")[0] for shape in shapes)
    assert top_level - asked_top == set(), top_level - asked_top
    assert asked_total == 9046, asked_total


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
