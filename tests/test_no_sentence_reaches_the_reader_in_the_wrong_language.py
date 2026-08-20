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
"""
from __future__ import annotations

import functools
import json
import pathlib
import re

import pytest

import themis

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
