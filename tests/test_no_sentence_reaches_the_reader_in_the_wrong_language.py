"""A sentence the kernel writes is written in the reader's language.

There was already a gate for this. Its denominator was three keys of one
block — ``data_gap_report.gaps[].{description, if_provided,
alternative_paths}`` — because that is where the two English producers it
was built for happened to live. ``late_caveat`` was never in it, and so
was never asked: a whole paragraph of English prose printed verbatim into
a Chinese report, and every check still green.

Widening the subject to "prose the reader is handed" needs the other half
of the distinction, which nothing in the contract stated: **not every
string the kernel emits is addressed to the reader.** A symbolic bound, a
citation, and the user's own declaration handed back are all things a
translation would damage, and over the corpus they outnumbered the prose.
So the two tables below are that distinction, written down, one entry
each with the reason.

Only 29 of the 257 string paths a result carries could be a sentence at
all — a string with no space is not one in any language, which is what
drops identifiers, enum members and atom names out without a judgement
call. Classifying 29 paths is a table; classifying 257 would have been a
ritual.

**The rule is on the field, not on the string.** A first version of this
module inverted that — a heuristic over every string, with an exception
list — and its counterexamples came back green: the producers build these
by concatenation, so putting ONE clause back into English leaves the rest
of the CJK in place and "the string contains no CJK" is simply false.
That is not a hole in the heuristic, it is the shape of the real defect:
``precision_target`` reached the reader as an English clause inside the
Chinese template ``n ≥ {min_sample_size}（{precision_target}）``. Hence
``_english_clause_in``, which looks at each CJK-free RUN rather than the
whole string.

A run is prose rather than a formula when it has function words. ``P(y |
do(x)) · P(x)`` is eight words and none of them is "the" — telling those
apart by word count alone flags every formula embedded in a Chinese
sentence, and there are many.

Two more things the failure taught. The corpus is not the denominator
either: the conditional-IV path that carries ``late_caveat`` is not in it,
so a program that reaches it ships with the gate. And the reader is not
only the report — the rendering prompt tells the model to quote
``bounds_results[].notes`` verbatim and interpolates ``precision_target``
into a Chinese sentence, so the prompt is a reader surface too, and both
of those were English.

The first of those two turned out to be the whole story rather than a
caveat. Everything above runs the kernel and looks at what came out, so
its denominator is a corpus — and the arm that was supposed to notice
that, the one asking "is any path unclassified", counts the paths the
same runs produced. A branch no case reaches is not checked and is not
reported as unchecked: the completeness arm reports the completeness of
what it observed. Measured on HEAD after the tables above were green, the
kernel held 823 English clauses outside its documentation, and this arm
had seen none of them, including one on ``cde_status.reason`` — a path
the table above already calls prose.

So the second half of this module works from the source instead. Its
denominator is every string literal in ``themis/``, which no run can
narrow, and the classification is inverted: **the kernel writes the
reader's language, and English needs a reason.** That keeps the table
small and stable — four structural allowances the AST decides by itself,
and a short list of named slots — where a table of producers would have
needed a row per construction site and grown with every new one.

Both the structural rules and the slot names read where a literal SITS,
and neither follows a call. A helper that returns a clause its caller
interpolates into a refusal is therefore outside a channel it is inside,
and needs a row saying where it lands. Four of them do, and what found
them was translating them: a refusal that came out half in one language
is this module's own subject, committed while writing it.
"""
from __future__ import annotations

import ast
import enum
import functools
import json
import pathlib
import re

import pytest

import themis
from themis import language

REPO = pathlib.Path(__file__).resolve().parent.parent
L3 = REPO / "docs" / "l3_simulation"
CJK = re.compile(r"[一-鿿]")
#: Digits and underscores are part of a word, so ``P_rct_50_to_70_pool`` is
#: one identifier rather than a phrase containing "to".
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_'`-]*")
#: What the kernel QUOTES is not what the kernel wrote. The one place this
#: matters is a paper title inside a Chinese sentence, and a title is an
#: English sentence by construction — in double quotes when it is a title
#: proper, in emphasis markup when it is a journal or a short work.
QUOTED = re.compile(r'"[^"]*"|“[^”]*”|\*[^*]*\*')

#: What tells an English clause from a formula. A bound, an estimand and a
#: probability key are full of Latin tokens and contain none of these; a
#: sentence cannot avoid them. Deliberately excludes "do", which is the
#: intervention operator here and appears inside estimands.
FUNCTION_WORDS = frozenset("""
a an the this that these those is are was were be been being
of in on at to for from with within into over under by via as
and or but not no nor so than then when where while because if
it its their there here which who whom what how
we you they he she i
""".split())

#: The kernel talking to the reader. Every string on these paths carries
#: the reader's language, including every clause of it.
PROSE: dict[str, str] = {
    "bounds_results.[].data_required.[]": "what to go and observe",
    "bounds_results.[].notes": "what this method is and what it costs",
    "data_gap_report.actionable_next_steps.[]": "what to do next",
    "data_gap_report.gaps.[].alternative_paths.[]": "the other ways round",
    "data_gap_report.gaps.[].description": "what is missing",
    "data_gap_report.gaps.[].if_provided": "what filling it buys",
    "data_gap_report.gaps.[].required_data.precision_target": "how precise",
    "data_gap_report.gaps.[].required_data.time_window": "over how long",
    "data_gap_report.summary": "the one-line answer to 'what is missing'",
    "explanation": "the answer, in words",
    "extensions.assumption_ledger.assumptions.[].claim": "what is assumed",
    "extensions.iv_identification.late_caveat": "which average this is",
    "extensions.iv_identification.required_assumption": "what it rests on",
    "extensions.mediation_decomposition.numeric.cde_status.reason":
        "why there is no number",
    "extensions.mediation_decomposition.numeric.nde_nie_status.reason":
        "why there is no number",
    "extensions.selection_recovery.failure_reason": "why it is not recoverable",
    "investigation_requests.[].items.[].reason": "why this is being asked for",
    "investigation_requests.[].note": "what the group has in common",
    "missing_information.[].reason": "why this is being asked for",
}

#: NOT the kernel talking. Each is here because translating it would
#: destroy what it is for, and the reason is per-entry because "it is in
#: English" is not one.
VERBATIM: dict[str, str] = {
    # Mathematics. A translated Σ is not one.
    "bounds_results.[].lower_expression": "symbolic bound",
    "bounds_results.[].upper_expression": "symbolic bound",
    "derivation.steps.[].output": "the step's formula",
    "extensions.transport_identification.formula_repr": "the estimand",
    # A citation is a thing you look up, so it keeps the spelling that
    # finds it.
    "extensions.selection_recovery.reference": "citation",
    # The user's own words, handed back. Translating a declaration would
    # show them something they did not write — and one corpus case wrote
    # this field in Chinese and another in English, which is the user's
    # choice in both.
    "extensions.ambiguities.[].description": "declared by the user",
    "investigation_requests.[].items.[].skeleton.existing.threshold":
        "declared by the user",
    "investigation_requests.[].items.[].skeleton.existing.measurement":
        "declared by the user",
    "investigation_requests.[].items.[].skeleton.existing.observability":
        "declared by the user",
    # An identifier that embeds one of those declarations, so it inherits
    # the reason above.
    "data_gap_report.gaps.[].provenance.[].ref_id": "identifier",
}

#: A path that must be observed, or the sweep has quietly stopped looking
#: at the thing this was built for.
MUST_APPEAR = "extensions.iv_identification.late_caveat"


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _gr(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target, tv, given, value) -> dict:
    return {
        "kind": "probability",
        "target": _gr(target, tv),
        "given": [_gr(p, v) for p, v in given],
        "value": value,
    }


def _conditional_iv_program() -> dict:
    """W → Z → X → Y with W → Y and X ↔ Y latent, monotonicity declared.

    The one path in the system that writes ``late_caveat``, and the L3
    corpus does not contain it. The instrument is valid only GIVEN W,
    which matters: the caveat has a second half that only a conditioning
    set reaches, and a plain Z → X → Y program leaves it unwritten. That
    is not hypothetical — with the plain program here, the counterexample
    that puts that half back into English came out green.
    """
    strata = {True: (0.9, 0.3, 0.7, 0.4), False: (0.6, 0.2, 0.5, 0.2)}
    stmts = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("x", "y", "z", "w")
    ] + [
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("w", True, [], 0.4),
        _prob("w", False, [], 0.6),
    ]
    for wv, (pxz1, pxz0, pyz1, pyz0) in strata.items():
        stmts += [
            _prob("x", True, [("z", True), ("w", wv)], pxz1),
            _prob("x", True, [("z", False), ("w", wv)], pxz0),
            _prob("y", True, [("z", True), ("w", wv)], pyz1),
            _prob("y", True, [("z", False), ("w", wv)], pyz0),
        ]
    stmts.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": _gr("y", True),
            "given": [],
            "assumptions": {"monotonicity": "non_decreasing"},
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def _english_clause_in(text: str) -> str | None:
    """The first run of ``text`` that reads as English prose, or None.

    Per RUN, not per string: these are built by concatenation, and a
    producer that writes one clause in English leaves the rest of the
    sentence's CJK exactly where it was. Per string, that reads as
    Chinese.

    Two function words, and only lowercase ones. A capitalised function
    word belongs to a name or a title — ``Hernán & Robins What If §9`` —
    while one doing grammatical work is lowercase wherever it is not
    starting the sentence. Two rather than one because a title can still
    reach one, and a clause the kernel wrote cannot get through on one.
    The line is drawn where the corpus draws it: every English producer
    this item translated clears it, and every legitimate quotation of a
    name, a reference or a formula does not.
    """
    for run in CJK.split(QUOTED.sub(" ", text)):
        words = WORD.findall(run)
        if len(words) < 4:
            continue
        if sum(1 for w in words if w in FUNCTION_WORDS) >= 2:
            return run.strip()
    return None


def _could_be_a_sentence(text: str) -> bool:
    """A string with no space is not a sentence in any language.

    This is the filter on the CLASSIFICATION denominator, not on the
    language rule — so its errors cost one line in a table rather than a
    wrong verdict.
    """
    return " " in text.strip() and len(WORD.findall(text)) >= 2


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, path + ("[]",))
    elif isinstance(node, str):
        yield ".".join(path), node


@functools.lru_cache(maxsize=1)
def _sweep() -> tuple[tuple[str, str, str], ...]:
    """(source, path, text) for every string the kernel emitted."""
    found: list[tuple[str, str, str]] = []
    sources: list[tuple[str, dict]] = [
        (case.name, json.loads(case.read_text(encoding="utf-8")))
        for case in sorted(L3.glob("case_*.json"))
    ]
    sources.append(("conditional_iv", _conditional_iv_program()))
    for name, program in sources:
        out = themis.run(program)
        for res in out["results"]:
            for path, text in _walk(res):
                found.append((name, path, text))
    return tuple(found)


@functools.lru_cache(maxsize=1)
def _candidates() -> frozenset[str]:
    """Paths that ever carry something that could be a sentence."""
    return frozenset(
        path for _, path, text in _sweep() if _could_be_a_sentence(text))


# --- the rule ----------------------------------------------------------------


def test_no_prose_field_hands_the_reader_an_english_clause():
    """The check no per-vocabulary gate could make.

    A sentence is written once, at the producer, and nothing downstream
    re-reads it — so a producer that writes English ships English to a
    Chinese report and every other check still passes.

    This half sees what a run produced, which is how it catches a
    sentence assembled from parts no literal contains — a template here
    and a clause there — and it is blind to every branch the corpus does
    not reach. The source arm below is the other half.
    """
    wrong = []
    for source, path, text in _sweep():
        if path not in PROSE:
            continue
        clause = _english_clause_in(text)
        if clause is not None:
            wrong.append((path, source, clause[:120]))
    assert not wrong, "\n".join(
        f"{p}  [{s}]\n    {c}" for p, s, c in sorted(set(wrong)))


def test_a_prose_field_is_not_written_entirely_in_the_other_language():
    """The whole-string check the narrow gate made, kept at its strength.

    ``_english_clause_in`` is a heuristic; "this field has no CJK at all"
    is not. A field that is prose by declaration and carries not one
    character of the reader's language is wrong whatever its word count,
    and that is how the three gap keys were guarded before.
    """
    wrong = sorted({
        (path, text[:120])
        for _, path, text in _sweep()
        if path in PROSE and text.strip() and not CJK.search(text)
    })
    assert not wrong, wrong


# --- the classification the rule rests on ------------------------------------


def test_every_path_that_could_carry_a_sentence_is_classified():
    """Neither list may be the smaller half of an unasked question.

    This is the arm the gate this replaces did not have. Its denominator
    was three keys chosen by where two bugs happened to be, so a fourth
    key was not a violation — it was invisible.

    Read what this actually says, because it took an audit to notice: the
    paths counted here are the paths the runs above produced, so this
    reports the completeness of what those runs observed. It is not the
    repository's completeness check and cannot be — the test below
    requires every classified path to be produced, so this table cannot
    even name a path no case reaches. Completeness lives on the source
    side.
    """
    unclassified = sorted(
        p for p in _candidates() if p not in PROSE and p not in VERBATIM)
    assert not unclassified, (
        "these paths carry something that could be a sentence and are in "
        f"neither PROSE nor VERBATIM: {unclassified}")


@pytest.mark.parametrize("path", sorted({*PROSE, *VERBATIM}))
def test_every_classified_path_is_still_produced(path):
    """A classification for a path nothing writes is one nobody checked.

    A stale entry lets the next one be added by copying a dead line —
    this refused five paths added on speculation while the module was
    being written.
    """
    assert path in _candidates(), (
        f"{path} is classified but no case produces a string there; "
        f"either the producer is gone or the sweep no longer reaches it")


def test_a_path_is_not_in_both_lists():
    """Prose and verbatim are the two answers, so a path has one."""
    both = sorted(set(PROSE) & set(VERBATIM))
    assert not both, both


def test_the_sweep_still_reaches_the_paragraph_that_started_this():
    """``late_caveat`` is not in the L3 corpus.

    The gate this replaces would have passed on it forever. A sweep that
    silently stops reaching a path reports the same "no violations" as
    one that checked it, so the path is named and its absence fails.
    """
    paths = {path for _, path, _ in _sweep()}
    assert MUST_APPEAR in paths, sorted(
        p for p in paths if p.startswith("extensions.iv_identification"))
    # And that it arrives with its conditioning half written, which only
    # a conditional instrument reaches.
    caveats = [t for _, p, t in _sweep() if p == MUST_APPEAR]
    assert any("`strata`" in t for t in caveats), caveats


# --- the clause detector itself ----------------------------------------------


@pytest.mark.parametrize("text", [
    "P(y=true | do(x=true)) · P(x=true)",
    "P*(cvd_event | do(statin_use)) = Σ_{age_high} P(cvd_event | age_high)",
    "time_window, measurement, observability, direction, baseline",
    "LATE = E[Y(X=treated) − Y(X=control) | 依从者]",
    # A population the user named, which happens to contain "to".
    "缺 P_rct_50_to_70_pool(cvd_event=True|age_high=True,statin_use=True)",
    # A reference inside a Chinese sentence, marked up and bare.
    "见（Hernán & Robins *What If* §3.4）的一致性假设",
    "回归稀释可达 60%；Hernán & Robins What If §9 有讨论",
    # The user's own threshold, quoted inside a Chinese gap description.
    "阈值不一致：bp_systolic_high（“>=140 mmHg systolic OR meaningful "
    "change from baseline (DASH endpoint)”）与 sodium_intake_high 冲突",
    # And one whose quoted title is a full English sentence.
    '参见 Hernán & Taubman 2008 "Does obesity shorten life? The importance '
    'of well-defined interventions" 里的讨论',
])
def test_a_quotation_is_not_an_english_clause(text):
    """Word count alone would flag every one of these.

    They are what a Chinese sentence in this system is full of — a
    formula, an identifier the user chose, a reference — so a detector
    that cannot tell them from prose cannot be used on the fields that
    matter. Each of these was a live false positive.
    """
    assert _english_clause_in(text) is None


@pytest.mark.parametrize("text", [
    "变量 x is declared but missing 6 framing fields",
    "区间宽度 = P(x) — tight when the off-arm mass is small",
    "报出来的数是把 the per-stratum LATEs weighted by their own share 汇总的",
])
def test_an_english_clause_is_found_even_beside_chinese(text):
    """The arm that exists because the first version of this module was
    wrong.

    Its counterexamples came back green: the producers concatenate, so
    putting one clause back into English leaves the rest of the CJK in
    place and a whole-string test sees Chinese.
    """
    assert _english_clause_in(text) is not None


@pytest.mark.parametrize("text", [
    "detect Cohen's h=0.2 at α=0.05 two-sided; two-arm equal allocation",
    "6 items with distinct reasons",
])
def test_terse_english_is_caught_by_the_whole_string_arm_not_this_one(text):
    """Two arms, and this is the division between them.

    Technical English can be too terse for the clause detector — one
    function word in a whole sentence. It does not need to reach it: a
    field written entirely in the other language has no CJK at all, which
    is not a heuristic. The clause detector is only for the mixed case,
    which the other arm cannot see.
    """
    assert _english_clause_in(text) is None
    assert not CJK.search(text)


# =============================================================================
# The other arm: the source, where a sentence is written
# =============================================================================


class Wrote(enum.Enum):
    """Why a run of English in ``themis/`` is allowed to stay English.

    There is no ``PROSE`` member. Prose in the reader's language is not an
    allowance — it is the rule, and a slot that keeps it needs no entry
    anywhere. What needs saying is the exception, so these are the four
    kinds of exception and nothing else.
    """

    QUOTED = "quoted"
    """Not the kernel talking: a citation, an estimand, a shell command.
    The reader-side ``VERBATIM`` table says the same thing about the paths
    these land on."""

    AUDIT = "audit"
    """The audit trail. A verifier finding and an oracle disagreement are
    read by whoever is checking the kernel, and what a person is handed is
    a rendering of the verdict, never this string."""

    HELD = "held"
    """The refusal channel. It does reach the reader, and which language
    it should reach them in is a decision this rule does not get to make.
    Calling it audit would have been convenient and false."""

    UNREAD = "unread"
    """A field with no consumer. Nothing reads it, so no reader's language
    governs it — but it is not documentation either, because it is a value
    and the next person may wire it up. Recorded rather than translated,
    so that wiring it up is what changes the answer."""

    SAID = "said"
    """One thing's word in the language its own key names.

    The rule below reads "the kernel writes the reader's language" off the
    shape of the text, which works while there is one such language and
    stops the moment there are two: a word written for an English reader is
    English, and it is not evidence of anything. What settles it is not the
    string but the slot — the key beside it IS the language — so this is
    decided structurally rather than listed, and a new language needs no
    entry anywhere."""


#: Trees whose every string belongs to the audit trail. A tree rather than
#: a list of modules because that is the actual boundary: everything under
#: ``verifier/`` exists to re-derive and disagree, and everything under
#: ``oracle/`` is a differential harness ``themis.run`` never calls.
AUDIT_TREES = ("themis/verifier/", "themis/oracle/")

#: Modules that are the refusal channel end to end.
HELD_MODULES = ("themis/refusals.py",)

#: The slot label a word gets when it sits under a language key. Derived
#: from the vocabulary rather than written out, so that a language starts
#: being recognised the moment the build has words in it.
LANGUAGE_SLOTS = frozenset(f"dict[{tag}]" for tag in language.written())

#: What an anonymous dict literal is, by what it carries. A dict has no
#: name to be classified under, and keying one by its key alone would put
#: the refusal channel's ``reason`` and the mediation arm's ``reason`` in
#: one row — which is the move this item is about. Subset rather than
#: equality: the same container appears with and without its optional keys.
#: A literal matching two of these gets a label no allowance can hold, so
#: it fails rather than being filed under whichever was written first.
DICT_SHAPES: tuple[tuple[str, frozenset[str]], ...] = (
    ("estimator_failure", frozenset({"estimator", "failure_type"})),
    ("gap", frozenset({"kind", "description"})),
    ("theta_arm_status", frozenset({"status", "reason"})),
    ("estimator_fallback", frozenset({"from", "to", "reason"})),
    ("gap_required_data", frozenset({"data_type", "variables"})),
    ("data_gap_report", frozenset({"gaps", "summary"})),
    ("iv_identification", frozenset({"instrument", "conditioning"})),
    ("assumption_ledger_row", frozenset({"claim", "layer"})),
)


def _dict_shape(keys: frozenset[str]) -> str | None:
    """Which container this is, or a label nothing can be filed under."""
    hit = [name for name, signature in DICT_SHAPES if signature <= keys]
    if len(hit) == 1:
        return hit[0]
    return "/".join(sorted(hit)) if hit else None


#: Slots — a keyword argument, a dict key, or the class a member sits in —
#: whose language is settled by something other than the rule. The label is
#: what the scan reads off the syntax, so a slot that moves keeps its
#: entry only if it keeps its name, which is the point.
ALLOWED_SLOTS: dict[str, tuple[Wrote, str]] = {
    # --- quoted rather than said ---------------------------------------
    "*::dict[reference]": (
        Wrote.QUOTED, "the paper you look up, spelled the way that finds it"),
    "themis/output/bounds.py::attempt_balke_pearl_iv": (
        Wrote.QUOTED,
        "bounds_results[].{lower,upper}_expression, which the reader-side "
        "table above already calls verbatim. This branch writes the "
        "programme in words because a Balke-Pearl bound has no closed "
        "form to write instead — a note in an expression slot, which is a "
        "defect about the slot rather than about the language"),

    # --- the refusal channel, whose language is settled elsewhere -------
    "*::estimator_failure.reason": (
        Wrote.HELD, "the refusal a caller is handed, by the estimator"),
    "themis/runtime/scheduler.py::block.reason": (
        Wrote.HELD, "the same refusal, raised by the scheduler"),
    "themis/estimation/claim.py::BLOCK_REASONS[]": (
        Wrote.HELD, "why a block is absent — the refusal, one per reason"),
    "themis/estimation/outcome_error.py::_WHAT_IT_IS[]": (
        Wrote.HELD,
        "what a missing argument is, interpolated into the refusal that "
        "names it"),
    "themis/estimation/outcome_error.py::_solve[2]": (
        Wrote.HELD, "what the singular matrix was, for the refusal"),
    "themis/input/semantic_validator.py::_LATENT_EXPOSURE[]": (
        Wrote.HELD,
        "why a latent common cause can or cannot move each kind of "
        "answer; the ones that cannot are refused and this is the "
        "sentence the refusal carries"),
    "themis/output/data_gap_report.py::_RaisedElsewhere[0]": (
        Wrote.HELD, "an exception assembled here and raised by its caller"),
    # A helper is not where its sentence lands. These four return a clause
    # their caller interpolates into a refusal, so the syntactic rules —
    # which read where a literal SITS — put them outside a channel they are
    # inside. Translating them is what caught it: it split one refusal
    # across two languages, which is this item's own defect.
    "themis/response_polytope.py::_instrumental_inequality_violation": (
        Wrote.HELD,
        "the witness clause, concatenated into the EstimatorFailure raised "
        "when the response-function LP is infeasible"),
    "themis/estimation/dispatch.py::_outcome_error_unreached": (
        Wrote.HELD, "estimator_failure.reason, one call away"),
    "themis/estimation/dispatch.py::_outcome_error_has_no_beta": (
        Wrote.HELD, "the same, for the design that has a β̂ nobody produced"),
    "themis/estimation/dispatch.py::_THE_POINT_IS_NOT_WHAT_IS_MISSING": (
        Wrote.HELD, "the clause both of those end with"),

    # --- a value with no reader -----------------------------------------
    "themis/answers.py::Shape.carries": (
        Wrote.UNREAD,
        "what an answer shape holds. Nothing reads it — the shape's "
        "identity is its name and the renderers switch on that"),
    "themis/questions.py::Question.asks": (
        Wrote.UNREAD, "one of three readings with no consumer at all"),
    "themis/questions.py::Question.settles": (
        Wrote.UNREAD, "the same, for the true verdict"),
    "themis/questions.py::Question.fails": (
        Wrote.UNREAD, "the same, for the false one"),
    "themis/blocks.py::Block": (
        Wrote.UNREAD,
        "``holds``, what a writer puts in the block. Read by two tests "
        "asserting it is non-empty, and by nothing else"),
    "themis/blocks.py::Family": (
        Wrote.UNREAD, "``tells``, the same, for a family"),
    "themis/ledger.py::Layer": (
        Wrote.UNREAD,
        "``breaks``, what fails when the assumption does. The member's "
        "``zh`` sibling beside it is what a reader is handed, which is "
        "the shape this repository already uses for a vocabulary: one "
        "field for whoever maintains it, one for whoever reads it"),
    "themis/ledger.py::Provenance": (
        Wrote.UNREAD, "``answerable``, the same, beside its own ``zh``"),
    "themis/risk_provenance.py::RiskProvenance": (
        Wrote.UNREAD, "``asserts``, the same, beside its own ``zh``"),
    "themis/estimation/outcome_error.py::OutcomeErrorDesign": (
        Wrote.UNREAD,
        "what the residual is taken around, for whoever adds a design; "
        "the ledger claim a reader gets is written separately"),
    "themis/output/data_gap_report.py::GAP_KINDS_WITH_NO_PRODUCER[]": (
        Wrote.UNREAD,
        "why a gap kind has no producer yet — a note to whoever builds "
        "one, checked by the coverage meta-test and shown to nobody"),
}


def _allowance_for(module: str, slot: str) -> tuple[Wrote, str] | None:
    """The entry excusing this slot, in this module or in every module.

    Keyed on the module by default, because a slot name is not unique
    across a package and excusing ``Block`` everywhere because
    ``blocks.py`` needs it is how an allowance stops being one. ``*`` is
    for the slots that mean the same thing wherever they appear.
    """
    return (ALLOWED_SLOTS.get(f"{module}::{slot}")
            or ALLOWED_SLOTS.get(f"*::{slot}"))


def _literal(node: ast.AST) -> str | None:
    """The constant part of a literal, including one built by ``+`` or f-string.

    A producer that splits a sentence across adjacent string literals is
    writing one sentence, and reading them apart would let a clause hide
    in the gap.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant)
                       and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        return None if left is None or right is None else left + right
    return None


def _excused(tree: ast.AST) -> set[int]:
    """Nodes the syntax itself excuses, with no table involved.

    A bare string statement is documentation — module, class, function and
    the PEP 258 attribute kind alike — and documentation is written for
    whoever maintains this, not for whoever asks it a question. A literal
    inside a ``raise`` is an exception message, and every exception here is
    either an invariant a developer reads or a refusal on its way to the
    channel above.
    """
    excused: set[int] = set()
    for node in ast.walk(tree):
        documentation = (isinstance(node, ast.Expr)
                         and _literal(node.value) is not None)
        if documentation or isinstance(node, ast.Raise) or _is_super_init(node):
            excused.update(id(sub) for sub in ast.walk(node))
    return excused


def _is_super_init(node: ast.AST) -> bool:
    """``super().__init__(msg)`` — an exception class writing its own message.

    Structurally the same channel as ``raise``: the class exists to be
    raised, and putting its message a line further from the ``raise`` does
    not make it a different kind of string.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "__init__"
            and isinstance(func.value, ast.Call)
            and getattr(func.value.func, "id", None) == "super")


def _slots(tree: ast.AST) -> dict[int, str]:
    """Where each node sits, named by whatever will carry its value.

    Deeper wins: a call inside a call's argument claims its own arguments
    afterwards, so the innermost name is the one that sticks.
    """
    slots: dict[int, str] = {}

    def claim(node: ast.AST, label: str) -> None:
        for sub in ast.walk(node):
            slots[id(sub)] = label

    def entries(node: ast.Dict, bound_to: str | None) -> None:
        named = frozenset(k.value for k in node.keys
                          if isinstance(k, ast.Constant)
                          and isinstance(k.value, str))
        shape = _dict_shape(named)
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant)
                    and isinstance(key.value, str)):
                # Keyed by an enum member rather than a string. Still a
                # table, and still one row.
                if bound_to is not None:
                    claim(value, f"{bound_to}[]")
                continue
            if shape is not None:
                claim(value, f"{shape}.{key.value}")
            elif bound_to is not None:
                # A table filed per entry grows a row every time someone
                # adds an entry, and the language of a table is a property
                # of the table.
                claim(value, f"{bound_to}[]")
            else:
                claim(value, f"dict[{key.value}]")

    def descend(node: ast.AST, enclosing: str, bound_to: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            here, binding = enclosing, None
            if isinstance(child, (ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef)):
                here = child.name
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = (child.targets if isinstance(child, ast.Assign)
                           else [child.target])
                first = targets[0] if targets else None
                binding = first.id if isinstance(first, ast.Name) else None
                if binding is not None and isinstance(node, ast.Module):
                    # A class body's assignments are rows of the table the
                    # class is, and belong to it. A module body is not a
                    # table, so nothing larger owns the value and the name
                    # bound to it is the slot -- "<module>" names nothing.
                    here = binding
            elif isinstance(child, ast.Call):
                func = child.func
                who = (func.attr if isinstance(func, ast.Attribute)
                       else getattr(func, "id", "?"))
                for keyword in child.keywords:
                    if keyword.arg:
                        claim(keyword.value, f"{who}.{keyword.arg}")
                for index, arg in enumerate(child.args):
                    claim(arg, f"{who}[{index}]")
            elif isinstance(child, ast.Dict):
                entries(child, bound_to)
            slots.setdefault(id(child), here)
            descend(child, here, binding)

    descend(tree, "<module>", None)
    return slots


@functools.lru_cache(maxsize=1)
def _kernel_english() -> tuple[tuple[str, int, str, str, str], ...]:
    """(module, line, slot, allowance, clause) for every English run written.

    Allowance is the ``Wrote`` value that excuses it, or ``""`` when
    nothing does — which is the violation.
    """
    found: list[tuple[str, int, str, str, str]] = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        module = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        excused, slots = _excused(tree), _slots(tree)
        for node in ast.walk(tree):
            text = _literal(node)
            if text is None or id(node) in excused:
                continue
            clause = _english_clause_in(text)
            if clause is None:
                continue
            slot = slots.get(id(node), "<module>")
            if slot in LANGUAGE_SLOTS:
                allowance = Wrote.SAID.value
            elif module.startswith(AUDIT_TREES):
                allowance = Wrote.AUDIT.value
            elif module in HELD_MODULES:
                allowance = Wrote.HELD.value
            elif _allowance_for(module, slot) is not None:
                allowance = _allowance_for(module, slot)[0].value
            else:
                allowance = ""
            found.append((module, node.lineno, slot, allowance, clause[:160]))
    return tuple(found)


def test_the_kernel_writes_the_readers_language_unless_it_says_why():
    """The rule, with the source as its denominator.

    Nothing here runs the kernel, so a branch no case reaches is checked
    exactly like one every case reaches — which is the one thing the arm
    above cannot do.
    """
    wrong = sorted({
        (module, line, slot, clause)
        for module, line, slot, allowance, clause in _kernel_english()
        if not allowance
    })
    assert not wrong, "\n".join(
        f"{m}:{n}  [{s}]\n    {c}" for m, n, s, c in wrong)


@pytest.mark.parametrize("entry", sorted(ALLOWED_SLOTS))
def test_every_allowance_is_still_being_used(entry):
    """An allowance for a slot nobody writes to is one nobody checked.

    The same reason the reader-side table pins its paths: a dead entry is
    how the next one gets added, by copying a line that costs nothing.
    """
    where, _, slot = entry.partition("::")
    live = {(module, s) for module, _, s, _, _ in _kernel_english()}
    assert any(s == slot and (where in ("*", module)) for module, s in live), (
        f"{entry} is excused but nothing there writes an English clause any "
        f"more; drop the entry or find where it moved")


def _clauses_in(source: str) -> list[tuple[str, str]]:
    """(slot, allowance) for the English runs in one snippet of source."""
    tree = ast.parse(source)
    excused, slots = _excused(tree), _slots(tree)
    out = []
    for node in ast.walk(tree):
        text = _literal(node)
        if text is None or id(node) in excused:
            continue
        if _english_clause_in(text) is None:
            continue
        slot = slots.get(id(node), "<module>")
        out.append((slot, (_allowance_for("<snippet>", slot) or (None,))[0]))
    return out


def test_a_new_slot_writing_english_is_refused():
    """The counterexample: the rule has to say no to something.

    A producer added tomorrow, in the shape the ones this item translated
    were in, and excused by nothing.
    """
    found = _clauses_in(
        'DataGap(description="the treatment has no variation in the data")')
    assert found == [("DataGap.description", None)]


def test_documentation_is_not_a_sentence_the_kernel_writes():
    """And it has to say yes to the thing it is not about.

    Both kinds in one snippet: the function's own docstring and the PEP
    258 attribute kind, which is how every enum member here is described
    and which a check on "the first statement" would have missed.
    """
    source = "\n".join([
        "def f():",
        '    "This explains the function to whoever maintains it."',
        "    return 1",
        "",
        "X = 1",
        '"This explains the attribute to the same person."',
    ])
    assert _clauses_in(source) == []


def test_a_message_on_its_way_to_the_refusal_channel_is_held():
    """The exception channel is a decision this rule does not make."""
    assert _clauses_in(
        'raise EstimatorFailure(Refusal.INVALID_INPUT, '
        '"the design requires an instrument to make that claim about")') == []
