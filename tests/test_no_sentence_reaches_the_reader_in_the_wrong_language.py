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

That distinction was two tables here, one per answer, until the contract
was asked whether it could hold it — and it turned out to be holding it
already, in prose, at six slots in six wordings that nothing could read.
It is now one declaration per slot, ``x-text``, whose values are
:class:`themis.language.Text`; this module reads it rather than deciding
it (#436). **A container carries the declaration as readily as a leaf**,
and that is what made a declaration possible at all for the slots holding
the caller's own words: every one of those is inside an object the kernel
declares OPEN, because naming its keys would be claiming authority over
what a caller may write. There was no leaf to annotate — openness was the
statement, and unreadable as one.

Only a fraction of the string paths a result carries could be a sentence
at all, which is what drops identifiers, enum members and atom names out
without a judgement call. Declaring those is a page of the schema;
declaring all 243 would have been a ritual.

**That filter was itself written in one language.** It asked for a space
and two Latin words — Chinese uses neither, so every text written only in
it fell out of the denominator and was never asked whose words it was.
Two kernel paragraphs sat outside it, one a whole ledger summary. The two
scripts are asked separately now, which is the same shape as everything
else here.

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
and needs a row saying where it lands. What found the first four was
translating them: a refusal that came out half in one language is this
module's own subject, committed while writing it.

**The second language turns the rule inside out, and it comes back the
same rule.** "The kernel writes the reader's language" is a rule only
while there is one such language; with two, a word written for an English
reader is English and that is evidence of nothing. What the rule was
asking all along is whether a text has its language written BESIDE it —
and asked that way the question does not mention which language the text
is in. So there is one rule here, over every text a reader can be handed:
**it sits under a key that names its own language, or it is debt.** Two
detectors feed it, because Chinese announces itself in the characters
while English has to be told apart from a formula, and that is the only
place the two are treated differently.

Which deleted an allowance. ``HELD`` excused the refusal channel on the
stated ground that "which language it should reach the reader in is a
decision this rule does not get to make" — a name for a question rather
than an answer, and the rule above answers it: every language. Nothing
Chinese stood on it, 123 English runs did, and one of them is
``estimator_failure.reason``, which both reader surfaces print.

And it split one. Every ``raise`` was excused, on the stated ground that
an exception here is "either an invariant a developer reads or a refusal
on its way to the channel". That ``or`` is one name over two facts and
only the first half is unaddressed to a reader. What tells them apart is
what gets raised — this package raises a builtin when it is asserting and
raises something it defined when it is refusing — and 276 refusals were
standing behind the ``or``.

The debt is a list that only shrinks, which is the shape this repository
already uses for the same job in ``mypy.ini``: the rule runs over the
whole package and :data:`STILL_ONE_LANGUAGE` names, per module, exactly
how many texts have not been given their second language yet. Exactly,
rather than as a ceiling, because a ceiling is room to add one more.

**Two surfaces write sentences here, and only one of them is Python.**
The scan above is built on ``ast``, which is a fact about how the rule
reads its subject and not about who the subject is — and a denominator
that stops at a language boundary reports the completeness of one surface
as the completeness of the build. The browser was outside it while every
table in ``verdict.ts`` was given its second language, and nothing could
say what was left beside them. So the denominator is both surfaces, with
one reader each and one debt table between them.
"""
from __future__ import annotations

import ast
import builtins
import collections
import enum
import functools
import json
import pathlib
import re

import pytest

import themis
from themis import language
from tests import web_source

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

#: Whose words a slot holds — read off the contract, not decided here.
#:
#: These were two tables in this module, one per answer, with a phrase of
#: reason on every row. Which made this file the only place that knew, and
#: made the answer a judgement rather than a declaration: the schema was
#: already saying the same thing in prose at six slots, in six wordings, and
#: nothing could read any of them (#436). So the rows moved into the schema
#: as ``x-text``, whose values are :class:`themis.language.Text` and whose
#: reasons are that vocabulary's, said once each instead of once per row.
#:
#: **The declaration sits on a container as readily as on a leaf, and that
#: is not a convenience.** Every slot holding the caller's own text is under
#: an object the kernel declares OPEN — ``ambiguities[]``,
#: ``variablePatch.existing`` — because naming the keys would be claiming
#: authority over what a caller may write. There is no leaf to annotate;
#: openness was the declaration all along, and unreadable as one.
_CONTRACT = "query_result.schema.json"


@functools.lru_cache(maxsize=1)
def _text_slots() -> dict[str, tuple["language.Text", bool]]:
    """Every envelope path the contract says whose words it holds.

    Keyed by the same dotted path :func:`_walk` produces, so a declaration
    and an observation meet without either being translated into the
    other's spelling. A container's key is the container's own path;
    :func:`_whose` walks up to it.
    """
    from themis.input.syntactic_validator import _default_schema_dir

    docs = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in _default_schema_dir().glob("*.schema.json")
    }
    found: dict[str, tuple[language.Text, bool]] = {}

    def resolve(node, doc):
        for _ in range(20):
            if not (isinstance(node, dict) and "$ref" in node):
                return node, doc
            ref = node["$ref"]
            file, _, frag = ref.partition("#")
            doc = file or doc
            target = docs.get(doc)
            if target is None:
                return None, doc
            node = target
            for part in frag.strip("/").split("/"):
                if part:
                    node = (node or {}).get(part)
        return node, doc

    def holds_text(node, doc, depth=0):
        """Whether a string can arrive in this slot.

        Three shapes, and the third is the one this cut is about: a slot
        that says ``string``, an array of them, or an OPEN object — whose
        keys the kernel does not name, because for the caller's own words
        naming them would be claiming authority over what may be written.
        A union is checked branch by branch, which is why this runs where
        the resolver is rather than off the stored node.
        """
        node, doc = resolve(node, doc)
        if not isinstance(node, dict) or depth > 4:
            return False
        types = node.get("type")
        types = types if isinstance(types, list) else [types] if types else []
        if "string" in types:
            return True
        if "object" in types and node.get("additionalProperties") is not False:
            return True
        for sub in (node.get("oneOf") or []) + (node.get("anyOf") or []):
            if holds_text(sub, doc, depth + 1):
                return True
        items = node.get("items")
        return bool(items) and holds_text(items, doc, depth + 1)

    def visit(node, doc, path, open_above):
        """``open_above`` is the node stack: the formula AST and the value
        union are recursive, so a walk that only remembers where it has
        been by PATH never terminates. What must not repeat is a node
        inside itself."""
        # Before resolving, because a ``$ref`` may carry the declaration as
        # a sibling — which is the only way to say it about a slot whose
        # shape is a shared definition, and resolving first drops it.
        here = node.get("x-text") if isinstance(node, dict) else None
        node, doc = resolve(node, doc)
        if not isinstance(node, dict) or (doc, id(node)) in open_above:
            return
        open_above = open_above | {(doc, id(node))}
        member = here if here is not None else node.get("x-text")
        if member is not None:
            found[path] = (language.Text(member), holds_text(node, doc))
        for name, sub in (node.get("properties") or {}).items():
            visit(sub, doc, f"{path}.{name}" if path else name, open_above)
        items = node.get("items")
        if isinstance(items, dict):
            visit(items, doc, f"{path}.[]" if path else "[]", open_above)
        for branch in (node.get("oneOf") or []) + (node.get("anyOf") or []):
            visit(branch, doc, path, open_above)

    visit(docs[_CONTRACT], _CONTRACT, "", frozenset())
    assert found, "no slot declares whose words it holds; the walk is broken"
    return found


def _declared() -> dict[str, language.Text]:
    """Whose words each declared slot holds."""
    return {path: whose for path, (whose, _) in _text_slots().items()}


def _can_hold_text(path: str) -> bool:
    """Whether the slot one declaration sits on can carry a string."""
    return _text_slots()[path][1]


def _whose(path: str) -> language.Text | None:
    """The declaration at this path, or at the nearest container above it."""
    declared = _declared()
    parts = path.split(".")
    while parts:
        hit = declared.get(".".join(parts))
        if hit is not None:
            return hit
        parts.pop()
    return None


def _prose(path: str) -> bool:
    """Whether the kernel wrote this, and it therefore carries a language."""
    whose = _whose(path)
    return whose is not None and whose.translated

#: A path that must be observed, or the sweep has quietly stopped looking
#: at the thing this was built for.
#:
#: It names the TOKEN since #490, and what the gate proves changed with
#: it. The field used to be a string and the sweep asked which language
#: the paragraph in it was written in; the field is a list of statements
#: now, so the same run has to show that the second half — the one only a
#: conditional instrument reaches — arrives as a member and not as a
#: clause somebody appended. A path that stopped being produced would
#: still fail here, which is the whole of what the anchor is for.
MUST_APPEAR = "extensions.iv_identification.late_caveat.[].token"


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
    """Whether a reader could be handed this as words.

    This is the filter on the DECLARATION denominator, not on the language
    rule — so its errors cost one declaration rather than a wrong verdict.

    **It used to be written in one language's shape**: a space, and two
    Latin words. Chinese uses neither, so every text written only in it
    fell out of the denominator and was never asked whose words it was —
    which is this module's own subject, applied to its own arithmetic. Two
    kernel paragraphs sat outside it, one of them a whole ledger summary.

    So the two scripts are asked separately, as they are everywhere else
    here: Latin needs a space and two words, because an identifier has
    neither; CJK needs only to be present, because after the vocabularies
    left the envelope the only Chinese still on it is prose.
    """
    if CJK.search(text):
        return True
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
        if not _prose(path):
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
        if _prose(path) and text.strip() and not CJK.search(text)
    })
    assert not wrong, wrong


# --- the classification the rule rests on ------------------------------------


def test_every_path_that_could_carry_a_sentence_is_declared():
    """No slot may be the unasked half of a question.

    This is the arm the gate this replaces did not have. Its denominator
    was three keys chosen by where two bugs happened to be, so a fourth
    key was not a violation — it was invisible.

    Read what this actually says, because it took an audit to notice: the
    paths counted here are the paths the runs above produced, so this
    reports the completeness of what those runs observed. Completeness
    over the branches no case reaches lives on the source side.
    """
    undeclared = sorted(p for p in _candidates() if _whose(p) is None)
    assert not undeclared, (
        "these paths carry something that could be a sentence and no "
        f"schema slot says whose words they are: {undeclared}")


@pytest.mark.parametrize("path", sorted(_declared()))
def test_every_declaration_sits_on_a_slot_that_can_hold_text(path):
    """A declaration on a slot that holds no string is one nobody checked.

    The table this replaces asked whether a corpus run produced the path,
    which was the strongest thing a hand-kept list could be held to and
    still corpus-bounded: it could not even name a branch no case reaches,
    though the schema declares many. Asked of the schema the question gets
    an answer that no run can narrow — a slot holds text when it says
    ``string``, when it is an array of them, or when it is an open object
    whose contents are what the declaration is about.
    """
    assert _can_hold_text(path), (
        f"{path} declares whose words it holds, and no string can arrive "
        f"there")


def test_the_sweep_still_reaches_the_paragraph_that_started_this():
    """``late_caveat`` is not in the L3 corpus.

    The gate this replaces would have passed on it forever. A sweep that
    silently stops reaching a path reports the same "no violations" as
    one that checked it, so the path is named and its absence fails.
    """
    paths = {path for _, path, _ in _sweep()}
    assert MUST_APPEAR in paths, sorted(
        p for p in paths if p.startswith("extensions.iv_identification"))
    # And that its conditioning half is there, which only a conditional
    # instrument reaches. A member rather than a clause: what used to be
    # checked was the substring "`strata`" inside a paragraph, and the
    # paragraph could hold it in one language only.
    tokens = {t for _, p, t in _sweep() if p == MUST_APPEAR}
    assert "strata_weighted_by_complier_share" in tokens, tokens


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
    """What settles the language of a text, where the rule does not.

    ``SAID`` is the rule met rather than an exception to it, and it is read
    off the syntax, so a slot that keeps the rule needs no entry anywhere.
    The rest are the exceptions. The refusal channel stopped being one —
    it reaches the reader, so the rule reaches it — and ``SOURCE`` arrived
    when the kernel started emitting a file for another toolchain, as
    ``PROMPTED`` did when it started addressing a model.
    """

    QUOTED = "quoted"
    """Not the kernel talking: a citation, an estimand, a shell command.

    The reader side says the same thing about the slots these land in,
    and says it in the contract rather than here: every member of
    :class:`themis.language.Text` but ``KERNEL`` is one of these, named
    at the slot as ``x-text``. Two surfaces, one distinction — a literal
    is judged where it sits, a slot where it is declared."""

    SOURCE = "source"
    """Program text this package writes for another toolchain to compile.

    A comment in it is addressed to whoever opens that file, and what
    settles its language is the language that codebase is written in — the
    same thing that settles the language of the comments around it. No
    reader of a result is ever handed it, and translating it would put a
    second language into a file whose own convention is one."""

    PROMPTED = "prompted"
    """The prompt. Text this package addresses to a MODEL, not to a person.

    It continues a document: a system prompt is one file written in one
    language, and the paragraph wrapped around the payload is the next
    paragraph of it. So what settles the frame's language is that file's,
    the way ``SOURCE``'s is settled by the codebase it is emitted into, and
    translating one would put a second language into a document whose own
    convention is one.

    What separates it from every other member here is that this text is
    written to somebody who will answer in a language it does not say. The
    reader's language is a PARAMETER of the request, named by its own
    endonym — which is what lets one document render every language, and
    what makes the frame's own language nobody's translation debt. A module
    that asks a model for reader text without taking that parameter has no
    claim on this allowance: it is then writing in whatever language its
    author was thinking in, which is the defect and not the exception."""

    AUDIT = "audit"
    """The audit trail. A verifier finding and an oracle disagreement are
    read by whoever is checking the kernel, and what a person is handed is
    a rendering of the verdict, never this string.

    Reached two ways, because the trail has two kinds of text in it. A
    finding is whatever :class:`themis.verifier.VerificationError` is
    raised with, wherever that happens — the class is the role, and seven
    of them are raised from ``kernel.py``. Everything else under the two
    trees is text on its way into one: a helper's message argument, a
    table of expected shapes, neither of them a raise."""

    INVARIANT = "invariant"
    """A sentence that lands only inside a ``raise`` of a builtin.

    The same audience :func:`_unaddressed` excuses with no table at all —
    whoever is reading a traceback — and for the reason given there: an
    invariant that fires is a bug rather than an answer, and the object it
    refused to build never becomes a result. What an entry adds is that
    the sentence may SIT somewhere other than the raise. A reason that
    belongs to a species has to live beside the species, and the message
    quoting it interpolates it; the scan reads where a literal sits, which
    is the right rule and the reason this one cannot be structural.

    An entry has to name where its sentence lands, and it is false the
    moment anything renders that sentence — which is what a reader of the
    entry goes and checks."""

    UNREAD = "unread"
    """A field with no consumer. Nothing reads it, so no reader's language
    governs it — but it is not documentation either, because it is a value
    and the next person may wire it up. Recorded rather than translated,
    so that wiring it up is what changes the answer."""

    SAID = "said"
    """One thing's text in the language its own key names — the rule met.

    What settles it is not the string but the slot: the key beside the text
    IS its language, which is a fact about the syntax and not about the
    words. So this is decided structurally rather than listed, and a
    language added tomorrow needs no entry anywhere."""


#: Trees whose every string belongs to the audit trail. A tree rather than
#: a list of modules because that is the actual boundary: everything under
#: ``verifier/`` exists to re-derive and disagree, and everything under
#: ``oracle/`` is a differential harness ``themis.run`` never calls.
#:
#: Which is where the trail LIVES and not what it IS, and the difference
#: was seven texts. :func:`_findings` reads the role — a raise of the
#: class a finding is made of — so a check that moves between two files
#: keeps its answer. This stays because a tree holds text that is not a
#: raise at all, and that text is on its way into a finding.
AUDIT_TREES = ("themis/verifier/", "themis/oracle/")

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
    ("gap", frozenset({"kind", "describes"})),
    ("theta_arm_status", frozenset({"status", "reason"})),
    ("estimator_fallback", frozenset({"from", "to", "reason"})),
    ("gap_required_data", frozenset({"data_type", "variables"})),
    ("data_gap_report", frozenset({"gaps", "answer_tier"})),
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

    # The refusal channel used to be a section here, twelve entries deep.
    # It is gone: a refusal reaches the reader, so it is held to the rule
    # like anything else the reader is handed, and what those entries said
    # about it is now a count in STILL_ONE_LANGUAGE. The one thing worth
    # keeping is what they were for — a helper is not where its sentence
    # lands, and four of them returned a clause their caller interpolated
    # into a refusal — and that outlives them, because the slot machinery
    # still reads where a literal SITS.

    # --- an invariant, sitting beside the species it is about ------------
    "themis/types.py::SEVERITY_TURNS_ON[]": (
        Wrote.INVARIANT,
        "what a species' severity turns on, quoted by the ValueError "
        "``DataGap`` raises when a gap of that species states none. A gap "
        "that fails to construct never reaches an envelope, and nothing "
        "else reads the table's values — the rule beside it reads the KEYS, "
        "to know which species it must stay silent about"),
    "themis/types.py::BLOCKS_TURN_ON[]": (
        Wrote.INVARIANT,
        "the same, for what a gap of that species stands in the way of"),
    "themis/types.py::RAISED_BY_TURNS_ON[]": (
        Wrote.INVARIANT,
        "what the choice between a species' two checks turns on, quoted by "
        "the ValueError ``raised_by_ref`` raises at a site that named "
        "neither. A ref that fails to construct never reaches an envelope, "
        "and the rule beside it reads the NAMES — the sentence is for "
        "whoever writes the next producer of that species"),
    "themis/estimation/form.py::FITS_TURNS_ON[]": (
        Wrote.INVARIANT,
        "what the choice among a method's shapes turns on — the outcome's "
        "type, the licence a borrowed risk came under, a pair of levers — "
        "quoted by the ValueError ``fits`` raises at an estimator "
        "disclosing a shape its method does not fit. The same arrangement "
        "as the three above: a block that fails to attach never reaches an "
        "envelope, ``FITS`` beside it is read for its VALUES by the check "
        "and this table for the sentence, and the sentence is for whoever "
        "writes the next producer"),
    "themis/estimation/form.py::fits": (
        Wrote.INVARIANT,
        "the clause that introduces the one above, in the same refusal"),
    "themis/estimation/dispatch.py::_LOOPS_UNDER_ITS_OWN_CEILING[]": (
        Wrote.INVARIANT,
        "why one block draws fewer replicates than the run asked for, "
        "quoted by the RuntimeError the epilogue raises at a count nobody "
        "on that envelope decided. Same arrangement as the four above: a "
        "run that fails there reaches no reader, the ceiling beside it is "
        "read for its VALUE by the check and this clause for the sentence, "
        "and the sentence is for whoever writes the next loop that wants "
        "one"),

    # --- a value with no reader -----------------------------------------
    "themis/answers.py::Shape.carries": (
        Wrote.UNREAD,
        "what an answer shape holds. Nothing reads it — the shape's "
        "identity is its name and the renderers switch on that"),
    "themis/questions.py::Question.asks": (
        Wrote.UNREAD, "one of three readings with no consumer at all"),
    "themis/estimation/claim.py::BLOCK_REASONS[]": (
        Wrote.UNREAD,
        "what each reason for declining a query MEANS, and who can change "
        "it — written for whoever adds the ninth. The vocabulary's keys are "
        "consumed: ``blocked`` refuses one that is not here, and the key "
        "travels into ``Evaluation.declined``. The values travel nowhere. "
        "Measured rather than taken from the module's own docstring, which "
        "says the reasons are unconsumed and is half right — what would "
        "make this a reader's sentence is ``declined`` reaching the "
        "envelope, and that is a field this package has not written yet"),
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
    "themis/input/semantic_validator.py::Exposure.evidence": (
        Wrote.UNREAD,
        "why one query kind's latent-exposure verdict is right — the "
        "measurements taken while classifying it, written for whoever "
        "changes the classification. It was position one of a pair, and "
        "the refusal beside it spliced position one into the reader's "
        "sentence; the reader's half is a bilingual species now, so this "
        "field has no consumer and the name says which half it is"),
    "themis/intervals.py::Width": (
        Wrote.UNREAD,
        "``narrows_with``, what actually shrinks this width \u2014 the "
        "question whoever is adding a fourth member has to answer, and the "
        "reason there are three and not one. The reader's half is the "
        "``words`` and ``advice`` beside it, both bilingual"),
    "themis/intervals.py::Endpoints.because": (
        Wrote.UNREAD,
        "why one pair of endpoints is the kind it is \u2014 the census's "
        "own note to whoever adds the next pair. Twenty-six of them, read "
        "by a test asserting each is non-empty and by no renderer"),
    "themis/intervals.py::_point_ci.because": (
        Wrote.UNREAD, "the same field, reached through the helper that "
                      "spells out a point's sampling CI"),
    "themis/intervals.py::_ar_set.because": (
        Wrote.UNREAD, "the same, one helper over"),
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
    "themis/output/data_gap_report.py::_RaisedElsewhere[0]": (
        Wrote.UNREAD,
        "``reason``, why a species is built somewhere else — a note to "
        "whoever reads the renderer table. The pass that meets one skips "
        "it and never opens the field"),
    "themis/output/data_gap_report.py::_MEASUREMENT_ERROR_PATTERNS": (
        Wrote.QUOTED,
        "needles, not sentences. Each is matched against a variable's own "
        "``measurement`` field, so what settles its language is the "
        "PROGRAM's and not the reader's — and both languages sit in one "
        "pool because a declaration written in either has to be "
        "recognized. What reaches the reader is the substring that "
        "matched, quoted back as the user wrote it"),
    "themis/runtime/framing_check.py::_CONTINUOUS_MEASUREMENT_CUES": (
        Wrote.QUOTED,
        "the twin of the pool above, one layer over: cues matched against a "
        "variable's declared ``measurement`` to decide whether a cutpoint "
        "is a meaningful field for it. ``mm`` and ``毫米`` sit side by side "
        "in ONE tuple, which is what a bilingual matcher looks like — not "
        "one text in two languages, but two subjects, since a declaration "
        "written in either has to be recognized. Counting the Chinese half "
        "as owed a translation asked for ``mm``, which is already there"),
    "themis/output/reader_words.py::_HEADER": (
        Wrote.SOURCE,
        "the banner on the TypeScript file this module writes for the "
        "browser. It says what generated the file and how to regenerate "
        "it, to whoever opens it — the same audience, and the same "
        "language, as every other comment in that tree"),

    # --- addressed to a model -------------------------------------------
    #
    # Two functions in one module, and for a while they answered the
    # language question differently — one in English beside its endonym,
    # one in Chinese twenty lines down — because only one of them had ever
    # been told who would read what came back. The one that had not was
    # sourcing the reason printed beside a number the person is asked to
    # review, so the ONE text of the pair that reaches a reader was the one
    # written with no reader in mind. Both take the language now, and both
    # frames are the language of the document they continue.
    "themis/web/llm_bridge.py::render_reply": (
        Wrote.PROMPTED,
        "the paragraph wrapped around the envelope: what the model is "
        "handed, and where the reader's language is named. The document "
        "above it is ``prompts/response_rendering.md`` and this is its "
        "next paragraph"),
    "themis/web/llm_bridge.py::propose_theta_priors": (
        Wrote.PROMPTED,
        "the same frame around a program and the probabilities it is "
        "missing, continuing ``prompts/propose_theta_priors.md``. The "
        "allowance covers the whole function because a frame is assembled "
        "from pieces and no name is bound to it — which is the widest slot "
        "in this table, and the reason the check below pins the pair "
        "against their documents rather than trusting the entry"),
    "themis/refusals.py::Refusal": (
        Wrote.UNREAD,
        "``says``, what a species means to whoever adds the next one "
        "beside it. Its own docstring draws the line — not the reader's "
        "sentence, which belongs to the occasion and is in ``SAYS`` — and "
        "it has one writer and no readers"),
    "themis/gaps.py::Need": (
        Wrote.UNREAD,
        "the same field on the other channel's species, for the same "
        "audience. The reader's sentence is in ``gaps.SAYS`` beside it, "
        "in every language this build writes"),
    "themis/gaps.py::NO_SPECIES_ESCAPE[]": (
        Wrote.UNREAD,
        "why a species settles no route of its own — a note to whoever "
        "adds the next species, and the same shape as "
        "``GAP_KINDS_WITH_NO_PRODUCER`` below. Two claims are made here "
        "and the note is where they are told apart: nothing repairs this "
        "reason, or its routes name variables only the site knows. The "
        "reader is handed neither sentence, only the routes the species "
        "DOES settle, each a ``Route`` with its bilingual line beside it"),
    "themis/gaps.py::NOTHING_FILLS[]": (
        Wrote.UNREAD,
        "why nothing supplied would change this species — the other half "
        "of ``gaps.IF_PROVIDED``, and the same shape as "
        "``GAP_KINDS_WITH_NO_PRODUCER`` above. Written down rather than "
        "left as an absent row so that a species answered by neither is "
        "visible; the reader's fact is that they are shown no such line, "
        "which they learn by not being shown one"),
    "themis/gaps.py::Sentence": (
        Wrote.UNREAD,
        "and again on the statements a gap is MADE of, whose sentences are "
        "in ``gaps.DESCRIBES``. The note says why this statement is its own "
        "rather than a clause of the one above it, which is the question "
        "the next branch to add a fact has to answer"),
    "themis/gaps.py::Route": (
        Wrote.UNREAD,
        "and the same field again on the ways PAST a gap, whose sentences "
        "are in ``gaps.ROUTES``. What the note says here is why a reader "
        "would take this route rather than the one above it, which is a "
        "question for whoever adds the next one"),
    "themis/language.py::Text": (
        Wrote.UNREAD,
        "``says``, why a slot's words are or are not the kernel's, to "
        "whoever classifies the next slot. This vocabulary has no reader "
        "at all: its members are written into the schemas and read back by "
        "the surface that decides what to translate, and the reason beside "
        "each is for the person choosing between them"),
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


def _unaddressed(tree: ast.AST) -> set[int]:
    """Nodes the syntax itself excuses, with no table involved.

    A bare string statement is documentation — module, class, function and
    the PEP 258 attribute kind alike — and documentation is written for
    whoever maintains this, not for whoever asks it a question. A literal
    inside ``raise SomeBuiltin(...)`` is an invariant, read from a
    traceback by that same person: an invariant that fires is a bug rather
    than an answer, and nobody was ever going to be handed it.

    The qualifier is this function's whole content. Every ``raise`` used
    to be excused, on the stated ground that an exception here is "either
    an invariant a developer reads or a refusal on its way to the
    channel" — and the second half of that ``or`` does reach the reader.
    What separates them was already in the syntax: this package raises a
    builtin where it asserts and raises something it defined where it
    refuses. Which is also why an exception class building its own message
    needs no case here. It defined itself, so it is refusing.

    **And "a builtin" was a proxy for that, not the thing itself.** Eight
    sites raised one species — a table in this package asked for a key it
    has no row for — in two conventions: three as a bare ``KeyError``,
    excused here, and five as a named subclass of one, counted as
    refusals. Nothing separated the halves except whether the author had
    needed a name for a test to catch, which is a fact about the test.
    Read through the proxy it came out as a difference in audience, and
    the same sentence sat on both sides of it.

    So the second clause reads what a class SAYS it is rather than
    inferring it from the name at the site. :class:`themis.registry.
    Undeclared` is the declaration and its docstring is the criterion;
    what it costs is that a new one has to be written down, which is the
    intended cost. The proxy stays for everything else, because a bare
    builtin needs no class to say so.
    """
    excused: set[int] = set()
    for node in ast.walk(tree):
        documentation = (isinstance(node, ast.Expr)
                         and _literal(node.value) is not None)
        invariant = isinstance(node, ast.Raise) and _asserts(node)
        if documentation or invariant:
            excused.update(id(sub) for sub in ast.walk(node))
    return excused


def _asserts(node: ast.Raise) -> bool:
    """Whether what is raised is an invariant rather than a refusal.

    Read off the name at the raise site, which is where the two kinds
    differ syntactically for everything that needs no class of its own.
    Anything unrecognised falls to the refusal side, so a construction
    nobody anticipated arrives as debt rather than as an allowance
    nobody wrote.
    """
    name = _raised(node)
    return hasattr(builtins, name) or name in _under("Undeclared")


def _raised(node: ast.Raise) -> str:
    """The name at a raise site, however it was spelled."""
    raised = node.exc
    if isinstance(raised, ast.Call):
        raised = raised.func
    return (raised.attr if isinstance(raised, ast.Attribute)
            else getattr(raised, "id", ""))


@functools.lru_cache(maxsize=None)
def _under(root: str) -> frozenset[str]:
    """Every class this package derives from ``root``, transitively.

    Derived rather than listed, so that the answer is the declaration its
    author wrote and not an entry somebody here had to remember — the
    same reason :data:`LANGUAGE_SLOTS` is derived from the vocabulary.

    Read off the source rather than off imported objects, so a module
    that cannot be imported is still measured and the two arms of this
    file keep the same denominator.
    """
    bases: dict[str, tuple[str, ...]] = {}
    for path in sorted((REPO / "themis").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                bases.setdefault(node.name, tuple(
                    b.attr if isinstance(b, ast.Attribute)
                    else getattr(b, "id", "") for b in node.bases))
    found = {root}
    while True:
        grown = found | {name for name, of in bases.items()
                         if found & set(of)}
        if grown == found:
            return frozenset(found)
        found = grown


def _findings(tree: ast.AST) -> set[int]:
    """Nodes inside a raise of the class the audit trail is made of.

    The second door onto :attr:`Wrote.AUDIT`, and the one that reads the
    ROLE rather than the address. ``AUDIT_TREES`` says everything under
    two directories is audit trail, which is true and is what those trees
    are; what it cannot say is that seven findings are raised from
    ``kernel.py``, where the kernel checks its own display copy against
    the answer it just audited. Those are the same class in the same role
    as the 1039 inside the trees, and a rule reading the path would move
    the debt whenever a check moved between two files.

    Both doors stay. A tree also holds text that is not in a raise at all
    — a helper's message argument, a table of expected shapes — and that
    text is on its way into a finding without being one.
    """
    inside: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and _raised(node) in _under(
                "VerificationError"):
            inside.update(id(sub) for sub in ast.walk(node))
    return inside


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
            if named and named <= language.written():
                # A dict whose every key is a language IS the words, and the
                # key settles what language its value is in. Read before the
                # binding, because no table name can overrule that — and a
                # ``Words`` bound directly to a module-level name would
                # otherwise be filed under the name and lose the one thing
                # about it that decides the question.
                claim(value, f"dict[{key.value}]")
            elif shape is not None:
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


#: What the second language has not reached yet, per module, exactly.
#:
#: Not an allowance. Every line here is a module writing sentences a reader
#: is handed in one language, which is the defect — the number is how many,
#: so that the list can be read as a distance rather than as a decision.
#: The shape is the one ``mypy.ini`` already uses for the same job: the
#: rule covers everything and the exceptions are enumerated and shrinking,
#: which is what makes a module that has been cleaned show up as a line to
#: delete rather than as nothing at all.
#:
#: Exact rather than a ceiling, because a ceiling is room for one more. A
#: module whose count goes up fails as loudly as a module that was never
#: on the list, which is the only way "we are adding the second language"
#: is a claim about the future rather than about the past.
#:
#: What a count cannot see is one text finished and another added in the
#: same module. Pinning which texts instead would pin line numbers, and a
#: rule that fails when a paragraph is reflowed teaches people to stop
#: reading it. Said here rather than left to be discovered, because the
#: cost of the shape is the shape's to declare.
#:
#: TWO OF THESE WENT UP, AND HERE IS THE REASON THE RULE ASKS FOR. The
#: orientation propagation gained a sixth ``OrientationError`` and a clause
#: on its summary note, and the question compiler an eleventh and twelfth
#: conflict prompt (#428). None was given its second language, and the
#: argument is the same for all of them: each is the newest member of a
#: family that speaks one language TOGETHER — five ill-formed-input errors in
#: English, ten adjudication prompts in Chinese — and a family where one
#: member answers differently from the rest reads worse to every reader than
#: one that is uniformly behind. The prompts are also queued to leave the
#: kernel entirely, so a second language written into them here is work that
#: gets undone. Finishing either family is a line to delete, which is what
#: these numbers are for.
#:
#: EIGHT LINES WERE DELETED AT ONCE, AND NOT BY TRANSLATION. #405 gave the
#: two support-boundary species their sentences, and the sites that had been
#: writing "positivity violation: stratum … has no rows" now hand over the
#: cell and the term. ``aipw`` / ``backdoor`` / ``four_way_ratio`` /
#: ``general_id`` / ``longitudinal`` / ``missing_recovery`` / ``proximal`` /
#: ``selection`` had no other English clause in them, so their debt is not
#: smaller — it is gone, which is what a deleted line means here.
#:
#: AND FOUR MORE THE SAME WAY. The measurement-error family is the one whose
#: arguments a caller DECLARES rather than reads off the data — which states
#: the exposure has, which matrix goes with which level, how large the error
#: variance is — so it held the largest concentration of "your declaration is
#: wrong, here is why" prose in the repository. ``bounds_numeric`` /
#: ``measurement`` / ``outcome_error`` / ``regression_calibration`` had
#: nothing else English in them. ``measurement.py`` at 13 was the second
#: largest line in this table.
#:
#: AND FIVE MORE. The last of the self-authored refusals were identification
#: and backend judgements — ``binary_do_risk``, ``causation``,
#: ``dose_response``, ``frontdoor`` and ``response_polytope`` had nothing
#: else English in them. ``dispatch`` 73 → 69 and ``iv`` 9 → 3 are the same
#: cut where the module has other prose too. What this leaves in the table
#: is what it was always meant to leave: rendering, envelope fields and
#: prompts, none of which is a refusal.
#: FOUR LINES WENT AT ONCE, AND THE CUT WAS NOT IN THEM. ``answers``,
#: ``intervals`` (4), ``output/formula_text`` and ``questions`` held one
#: species between them — a table in this package asked for a key it has
#: no row for — and the package was writing it in five wordings and two
#: conventions. ``ledger``, ``routing`` and ``risk_provenance`` raised a
#: bare ``KeyError`` for the same thing and were excused here as
#: invariants; these five raised a named subclass of one and were
#: counted. The only difference was whether the author had needed a name
#: for a test to catch, which is a fact about the test — and read through
#: "is the raised name a builtin" it came out as a difference in
#: audience. :mod:`themis.registry` is the audience written down, and
#: what the eight sites hand over now is three facts and no sentence.
#: AND FIVE MORE LINES, NONE OF THEM TRANSLATED. What each of the five
#: needed was somebody to say what KIND of text it is, and three different
#: answers were already available. ``kernel.py``'s seven are findings, and
#: the allowance covering their 1039 siblings read the tree they live in
#: rather than the class they are. ``claim.py``'s eight are a vocabulary's
#: maintainer half, the shape ``refusals`` and ``gaps`` already use.
#: ``joint.py``'s one is an invariant a loop catches and drops without
#: opening. And ``transport.py``'s and ``counterfactual.py``'s are not
#: prose at all — a ``shape`` is notation, and each had an English
#: connector inside it that reached half the readers mid-sentence.
STILL_ONE_LANGUAGE: dict[str, int] = {
    # Five lines here said the same thing, and #476 closed it in one cut.
    # What was left in each was the refusals of a REQUEST SHAPE — a frame,
    # a stated graph, an answer to a question this layer asked, a panel
    # with a time column — thirty-nine f-strings, each in whichever
    # language its author was thinking in. What kept them was the carrier
    # rather than the sentences: an exception that holds a species and the
    # occasion's facts had been written out twice already, identically,
    # and five more exception classes meant a third through seventh copy,
    # which made writing the sentence at the site the cheap thing to do.
    # It is :class:`themis.language.Voiced` now. ``discovery``,
    # ``orientation``, ``orientation_session`` and ``lagged_discovery``
    # are gone from this table, and what is left below is one WARNING on a
    # ``str`` field of the contract — the only text of the five that never
    # reached its reader as a refusal.
    # contract.py's one went with the six that shared its field. See the
    # dispatch entry below: the field was typed ``string``, and this
    # module's ``warnings`` tuple was typed the same way one level up.
    # 44 before #441. The stratified-Wald fallback wrote its own Chinese
    # sentence for what having the missing strata would buy, which the
    # species already answers — so the sentence did not need translating,
    # it needed deleting.
    #
    # Then 27 before #443, where six went the same way and for a sharper
    # reason: they were headlines for a report field that had already been
    # removed, so each one was a sentence written for nobody.
    # Then 9 after #395. Twelve of them were ⚠ headlines this module
    # composed for a string field on the envelope, each restating a gap it
    # had filed one line above — so the second language they were owed was
    # never written, and does not have to be.
    #
    # Then 3 after #489, and the six that left were one field.
    # ``estimation_context.data_contract_warnings`` was typed ``array of
    # string``, so each of two modules' branches was the author of its own
    # sentence — five in Chinese and, in the same ``if``/``elif`` chain as
    # four of those, one in English. That last one is the shape of the
    # defect and not an oversight in it: nothing had said which language
    # belonged there, so both answers were equally correct. It is a
    # statement slot now, and the two vocabularies arriving in it record
    # the field's other finding — only one of the six was ever about the
    # data contract.
    # Then 0 after #492, and the last three were each an EXPLANATION put in
    # the slot of the thing it explains. Two glued the reading of an
    # unbounded Anderson-Rubin set onto the set's own notation, where
    # `(−∞, +∞)` reads the same to everybody and "so nothing is
    # constrained" does not; the reading is a statement beside the set
    # now. The third put a characterisation of a population in the field
    # that holds a population's NAME.
    # 17 before #432, then 9. Two of the sentences here and in mediation.py
    # below were a requirement plus a route out, and losing the route left a
    # name and four words — below this module's floor for "reads as English
    # prose", which is where it draws the line between a sentence and a
    # citation. The English that is left is still English; what changed is
    # that it is no longer a clause addressed to anybody.
    # joint.py was 2 before #325 and 1 after: the withheld interaction's
    # reason was a Chinese sentence built in the estimator, and it is a
    # two-member vocabulary now. The last one was never a sentence for
    # anybody — the draw loop catches it and drops the draw.
    # mediation.py reached 0 in #492 with its last one, which is the same
    # finding as dispatch.py's above one shape over: the four-way split's
    # PRESENCE is a structured block and its absence was one string. A
    # verdict whose positive is structure and whose negative is prose is
    # how a negative comes to be written in one language.
    # orientation_questions.py was 18, and is gone. Every one of them was a
    # question the tool PUTS TO A PERSON — the interactive surface of the
    # whole equivalence-class feature, in one language — and none was a
    # missing translation. The field they went into is typed ``string`` in
    # the artifact's own schema and documented there as "rendering, not
    # data", so each of twelve branches became the author of a sentence in
    # whichever language that branch was written in. What was missing was
    # the SLOT, and the slot is ``statement.schema.json`` now: the door the
    # six standalone artifacts' ``note`` fields have been owed, and the
    # reason the numbers below are the ones that still say so.
    # intervals.py was 4 and is gone with the registry cut above. Two of
    # the four were the lookups; the other two are the pair this package
    # keeps DISTINCT from a missing row — a row that declares there is no
    # such interval, and a producer that did not write a field its own
    # declaration required — and both are now raised through a class that
    # says whose sentence it is.
    # themis/input/semantic_validator.py was 26, then 28, then 29, and is
    # gone. Every line it ever had said the same thing — ``SemanticError``
    # took a finished string, so each raise site was the author of its own
    # wording and no site knows who is reading. The species vocabulary it
    # has now is the one ``themis.refusals`` uses one layer down, and the
    # web's failure body assembles from it exactly the way it already
    # assembled an estimator's refusal. Its other family went with it: the
    # evidence beside a latent-exposure verdict is the maintainer's, has a
    # name that says so, and is no longer spliced into a reader's sentence.
    # kernel.py was 7, and every one of them was a finding: the kernel
    # checking the display copy in ``extensions`` against the answer it
    # had just audited. Not a translation and not a deletion — the
    # allowance that covers their 1039 siblings was keyed on the tree
    # they live in rather than on the class they are, and ``verify``
    # hands all 1046 to the same reader through the same ``{ok, error}``.
    # The one text ``refusals`` owed moved with the machinery that carried
    # it: the note a truncated sentence ends with, which belongs beside the
    # cap, and the cap lives here now. It is gone, and it was never one
    # sentence: that the text stops here is the reader's, that a value went
    # in raw and where to look is a maintainer's, and ``capped`` takes a
    # string and no language, so it is the one site in the package that can
    # say neither. The reader's half is an ellipsis, which says it in every
    # language and is the character ``describe`` already elides with. The
    # maintainer's half was a diagnosis this site cannot make — two of the
    # three callers cap a value on its way into a hole and the third caps a
    # whole assembled sentence, where nothing was interpolated at all — and
    # a diagnosis stated as fact where it cannot be checked is deleted.
    # Its commonest destination made translating it wrong twice over: a
    # clause dropped into somebody else's hole is a second voice inside a
    # sentence that already has one.
    # themis/output/bounds.py was 8, and is gone. They were the two fields
    # a bounds row holds sentences in — ``notes`` and ``data_required`` —
    # and every clause in them that restated a field beside it (the method,
    # the estimand, the assumption, the instrument) was deleted rather than
    # translated. What was left is what nothing else on the row records,
    # and it is a vocabulary now, in both languages.
    # themis/output/result_orchestrator.py was 10, then 1 after #395's
    # second cut — nine of the ten were the three summaries those blocks
    # carried, and every fact in each was the list beside it counted or
    # read back. The last was the ledger line for a number the language
    # model supplied, written as an f-string because the field it went in
    # held text; the sixth cut made that field a list of statements, so
    # the line is a vocabulary of one member and there is nothing here.
    # themis/output/sample_size.py was 7, then 6, then gone. The seventh
    # was the hint beside the post-hoc n, which stated three numbers the
    # block already carried; the six were what a minimum n BUYS, written
    # by the arithmetic that produced the number. They are a vocabulary
    # now, in both languages, so there is no line to carry here.
    # framing_check.py was 10, and none of them was a debt. They were the
    # Chinese half of ONE tuple of matcher cues — ``mm`` and ``毫米`` side
    # by side — and a matcher's language is settled by what the caller
    # might have written, not by who is reading. Counting them asked for a
    # translation that was already in the tuple two entries along. Not
    # deleted quietly: the allowance above says which kind of text it is,
    # beside the pool one layer over that had said so since #443.
    # missing_data.py is done — the four were a verdict's whole negative
    # written as one sentence, because the row could name the theorem that
    # carried a POSITIVE verdict and nothing that carried a negative. Which
    # factor came back empty is a vocabulary now, whether the negative is a
    # proof is a field, and the estimand's shortfall holds the factors that
    # blocked it in a hole rather than joined with a separator of its own.
    # themis/runtime/proximal_identify.py was 9, then 11, and is gone. Its
    # two families went the same way one cut apart: a refusal's diagnosis
    # was written at the return site, and the data conditions were joined
    # into one string before they left. Both are vocabularies now — the
    # criterion carries the whole sentence and the occasion carries the
    # holes — so what the envelope holds is a token, and the reader's
    # surface says it. The English frame around a Chinese payload that both
    # reader surfaces were printing is gone with them.
    # 51 → 13. The thirty-eight that left were the sentences a shortfall
    # was reported with; they live in themis/gaps.py now, each in both
    # languages beside the species naming which shortfall it is (#435).
    # investigation_pusher (1) and numeric_estimator (5) went to zero the
    # same way, which is what their deleted lines here mean.
    #
    # One more left in #443: a ``reason`` written beside a status word, a
    # count and a cap that already say the whole of it, and read by nothing.
    # A restatement is deleted rather than translated.
    #
    # Then 10: the twelfth was this module writing a sentence onto somebody
    # else's field — the note saying a sharper bound was declined on size,
    # appended to whatever `bounds.py` had written, with a space. It states
    # that through the same door the method does now.
    # Then 5 after #490, and the five that left were the IV block's two
    # ``string`` fields. ``late_caveat`` is the paragraph this module's
    # own first line is about: it was English prose printed verbatim into
    # a Chinese report, somebody translated it, and it became Chinese
    # prose printed verbatim into whatever report was asked for.
    # Translating a sentence written at its site moves which reader it
    # fails. ``required_assumption`` was contested between its four
    # producers — three wrote prose and the fourth wrote a bare token and
    # said why beside itself — which is a field with no shape rather than
    # a disagreement about wording.
    # Then 0 after #491, and the last five were all inside a HOLE of a
    # sentence themis/gaps.py owns. This table counted all five the whole
    # time — what it could not do is collect them, because the four cuts
    # before it were each organised around a FIELD and these belong to no
    # field. Their one shared property is a position. The frame is
    # bilingual and what was dropped into it was written in one language,
    # so the gap end looks right and the site end looks right, and only
    # the seam is wrong. All five also chose
    # their own joiner: an ASCII space in front of a Chinese sentence and
    # a Chinese semicolon between two English ones are one mistake twice,
    # and the separator lives in the template now, where the language is
    # known. One of the five put ``str(exc)`` in the hole, which renders
    # a refusal in the default language; it cites the refusal now.
    # selection_recovery.py is done — its twin, and the same four things:
    # a shortfall vocabulary, `complete_criterion` for the clause that used
    # to end two of the sentences, and the external-data ledger split into
    # the role (a word) and the expression (symbolic, and the same to every
    # reader) that used to be one string with the English glued on.
    # theta_builder.py is done — its three were exception messages written
    # at their raise sites, because the two classes carrying them were bare
    # `ValueError` subclasses and had no notion of a species: which KIND of
    # error and this occasion's facts were pressed into one string, and the
    # site wrote it. Three species over two channels now. The check that
    # raises one of them already took the half of the statement as a
    # `role=` string, so the occasion had been split off for as long as the
    # check existed and only the wording stayed welded — which is exactly
    # what `extraction_refusal` found one layer up, and why forty-nine
    # sites there were sixteen species.
    # transport.py is done — #326 turned its two failure sentences into a
    # two-member vocabulary, and the sentence is made where the reader's
    # language is known.
    # themis/upstream is done — 49 between its two modules, and every one
    # of them an f-string at a raise site, in English, addressed to whoever
    # produced the extraction. What made it forty-nine rather than sixteen
    # is that each helper already took a ``what`` and interpolated the path:
    # the OCCASION had been a slot since the module was written and only
    # the WORDING stayed welded to the site, so the sites differed by the
    # path far more often than by the sentence. Two vocabularies now — the
    # species, and the SHAPE a field was supposed to be, which is a word
    # inside seven of them rather than seven sentences of its own.
    # 4 → 0 in #400. All four were the values ``_FILL_DEFAULTS`` wrote into
    # the program for a framing field left blank, each a sentence reading
    # "not specified" whose only job was to make the gap's ``is None`` test
    # come back false. They were the hardest four in the table to translate
    # and the easiest to delete, because what a program stores is not
    # something a reader's language may touch: the fill loop names the
    # fields it defaulted now, and stores no sentence at all.
    # themis/web/llm_bridge.py was 7, and is gone — the last line in this
    # table. Three families, three answers, and none of them a translation.
    # Three were the exception messages of a bare ``RuntimeError``: which
    # KIND of thing the bridge did not get back and this occasion's facts
    # pressed into one English string, written at the site, arriving at the
    # web edge as ``diagnostic`` while the reader got only the stage. The
    # door has read ``language.Voiced`` since the cut before this one, so
    # the class had a door already open and eleven species to walk through
    # it. Two were the paragraph wrapped around each payload, which is not
    # owed a second language at all: a frame continues the prompt document
    # it is sent with, and the allowance above says so and is checked
    # against the document. The last was the fallback written into
    # ``annotations.source`` when the model returned a number with no
    # reason — a constant that satisfied the checker requiring that field
    # non-empty while disclosing nothing, which is the check defeated
    # rather than met, and the only text here whose reader's language
    # nothing could have chosen. It refuses now.
    #
    # What made the two prompt frames disagree is worth keeping: one had
    # been given the reader's language and one had not, so the second had
    # nothing to write in but its author's own. Both take it now, and the
    # allowance is void without it.
    # themis/workflow/parameter_fill.py was 2 and variable_framing.py 10,
    # and both are gone. The second one's line said what would clear it —
    # "that vocabulary as a whole moving to the species-plus-facts shape",
    # noted when converting only the newest three would have left one
    # module's errors speaking two conventions — and #477 moved it whole.
    # What made it possible was not the sentences: five exception classes
    # across the two modules, two of them the SAME NAME for the same job,
    # and a carrier that had to be written out per class. The envelope
    # those classes guarded is one envelope, so its check is one function
    # now and the class it raises is one class.
    # The browser, counted by the line rather than by the literal — see
    # :func:`_reader_facing_ts` for why the unit differs on this surface.
    # Widening the denominator here found 193 lines across 20 files while
    # every table in ``verdict.ts`` was already bilingual; 19 of those files
    # have since been cleared and their rows deleted, which is what this
    # table's shape is for. The one that remains is not a translation
    # waiting to happen — it is a question about what the text IS.
    #
    # ``verdict.ts``'s eight were one cluster and left together in #400,
    # which is the shape this table was betting on: they were held by
    # ``FRAMING_FIELDS.def``, a value written into the program that the
    # reader's language must not touch, and the ``label`` and
    # ``placeholder`` beside it could not be given their second language
    # while sharing its LINE. Naming what the default answers — rather
    # than writing a sentence in for it — left nothing on those lines but
    # reader text, and reader text becomes ``Words``.
    # These four are the values of ``NOT_FOR_A_READER``, a table whose own
    # comment says nothing there is said to a reader. They are prose to
    # whoever maintains this surface, stored in the shape of data because
    # the keys beside them are data — a reason living in a value slot, not
    # a translation waiting to happen. Counted rather than excused: a
    # second allowance here would be a list, and a list is what the rule
    # above stopped being.
    # Counting them is what made the third answer findable. The four
    # sentences were one fact with three values — WHO each field addresses
    # — and the table's own comment had already named that set while the
    # type held prose. An audience is a token and a reason is prose; and a
    # reason can be written for anything, while picking one of three is a
    # claim that can be wrong, which is what makes it worth stating.
}


def _texts(tree: ast.AST):
    """(node, text) for every literal that no larger literal contains.

    Outermost, so an f-string is one sentence rather than one sentence
    plus each of the pieces it was written in. The pieces are an artefact
    of where the producer's lines wrapped, and counting them would make
    the debt below move when somebody reflows a paragraph.
    """
    claimed: set[int] = set()
    for node in ast.walk(tree):        # breadth-first, so a parent is first
        if id(node) in claimed:
            continue
        text = _literal(node)
        if text is None:
            continue
        claimed.update(id(sub) for sub in ast.walk(node) if sub is not node)
        yield node, text


@functools.lru_cache(maxsize=1)
def _reader_facing() -> tuple[tuple[str, int, str, str, str], ...]:
    """(module, line, slot, allowance, text) for every text a reader can get.

    Allowance is the ``Wrote`` value that settles the text's language, or
    ``""`` when nothing does — which is a text written in one language.

    A literal that is neither Chinese nor an English clause carries no
    language to be missing: an estimand, a column name, a JSON key. That
    is the only judgement here, and it is made by the two detectors rather
    than by a table, because the set of things that are not prose has no
    end to enumerate.
    """
    found: list[tuple[str, int, str, str, str]] = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        module = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        excused, slots = _unaddressed(tree), _slots(tree)
        findings = _findings(tree)
        for node, text in _texts(tree):
            if id(node) in excused:
                continue
            clause = _english_clause_in(text)
            if clause is None and not CJK.search(text):
                continue
            slot = slots.get(id(node), "<module>")
            entry = _allowance_for(module, slot)
            if slot in LANGUAGE_SLOTS:
                allowance = Wrote.SAID.value
            elif module.startswith(AUDIT_TREES) or id(node) in findings:
                allowance = Wrote.AUDIT.value
            elif entry is not None:
                allowance = entry[0].value
            else:
                allowance = ""
            found.append(
                (module, node.lineno, slot, allowance, (clause or text)[:160]))
    return tuple(found)


#: A line of TypeScript that is a comment about the code rather than
#: something a reader is handed. The browser's own prose about itself is in
#: English and is not the subject here.
_TS_COMMENT = re.compile(r"^\s*(//|/\*|\*)")


@functools.lru_cache(maxsize=1)
def _reader_facing_ts() -> tuple[tuple[str, int, str, str, str], ...]:
    """The same rows, for the surface that cannot be parsed as Python.

    The browser is the second place this repository writes sentences at a
    reader, and it was outside the denominator above for one reason: that
    scan is built on ``ast``. Which is a fact about the reader, not about
    the rule — and a rule whose denominator stops at a language boundary
    reports the completeness of one surface as the completeness of the
    build. Every table in ``verdict.ts`` had been made bilingual before
    anything counted what was left beside them.

    What settles the language here is the same thing that settles it over
    there, one level up: a text inside a ``Words`` is keyed by the language
    it is in, and a text outside one is written in whichever language
    somebody typed. So the allowance is membership of a ``Words``, read by
    :func:`tests.web_source.words_literals` — the scan whose own reach is
    pinned in ``test_the_language_is_a_parameter_not_a_name``.

    The unit is the LINE and not the literal, unlike the Python half. JSX
    text is not a literal at all — ``<span>因果验证器</span>`` is three
    nodes and one sentence — so counting literals would report a component
    written entirely in Chinese as holding almost nothing. A line is also
    what a reader of the diff watches move.
    """
    found: list[tuple[str, int, str, str, str]] = []
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        module = path.relative_to(REPO).as_posix()
        for number, allowance, line in _lines_owed(web_source.read(path)):
            found.append((module, number, "<line>", allowance, line))
    return tuple(found)


def _lines_owed(text: str) -> list[tuple[int, str, str]]:
    """(line, allowance, text) for the reader-facing lines of one file.

    Split from its caller so the rule can be shown a snippet rather than
    the tree, which is what the counterexample below needs — the same
    split :func:`_clauses_in` makes on the other surface.
    """
    lines = text.splitlines()
    inside: set[int] = set()
    for start, _ in web_source.words_literals(text, language.written()):
        depth, i = 0, start - 1
        while i < len(lines):
            depth += (lines[i].count("{") + lines[i].count("[")
                      - lines[i].count("}") - lines[i].count("]"))
            inside.add(i + 1)
            if depth <= 0 and i >= start - 1:
                break
            i += 1
    return [
        (number, Wrote.SAID.value if number in inside else "",
         line.strip()[:160])
        for number, line in enumerate(lines, 1)
        if CJK.search(line) and not _TS_COMMENT.match(line)
    ]


def _owed() -> collections.Counter:
    """How many one-language texts each module still holds."""
    return collections.Counter(
        module for module, _, _, allowance, _
        in _reader_facing() + _reader_facing_ts()
        if not allowance)


def test_a_module_not_on_the_debt_writes_every_language():
    """The rule, with the source as its denominator.

    Nothing here runs the kernel, so a branch no case reaches is checked
    exactly like one every case reaches — which is the one thing the arm
    above cannot do.
    """
    wrong = sorted({
        (module, line, slot, text)
        for module, line, slot, allowance, text
        in _reader_facing() + _reader_facing_ts()
        if not allowance and module not in STILL_ONE_LANGUAGE
    })
    assert not wrong, "\n".join(
        f"{m}:{n}  [{s}]\n    {c}" for m, n, s, c in wrong)


#: Modules where no raise site writes its own sentence any more.
#:
#: Not the complement of the debt table, and the difference is what this
#: list is for. The scan above reads a text and asks whether it looks like
#: prose addressed to somebody; a terse one passes — ``f"pool={n}"`` has no
#: function word in it — and the same blind spot is already written into
#: the debt entries above, where a session's ``note`` went uncounted for
#: exactly that reason. So a module that has finished is held to a second
#: rule with no heuristic in it: a raise site may not take a string at all.
#:
#: A roster rather than "every module with no debt", because most of the
#: package raises with a literal on purpose. A verifier's 739 raises are an
#: audit trail addressed to whoever is maintaining the rule, and the shape
#: of a refusal ADDRESSED TO A READER is what this names.
NO_SITE_WRITES_ITS_OWN: tuple[str, ...] = (
    # The LLM-side front door (#470).
    "themis/upstream/narrative_merge.py",
    "themis/upstream/program_builder.py",
    # The estimation layer's five request-shape channels (#476).
    "themis/estimation/contract.py",
    "themis/estimation/declared.py",
    "themis/estimation/discovery.py",
    "themis/estimation/lagged_discovery.py",
    "themis/estimation/orientation.py",
    "themis/estimation/orientation_session.py",
    # The bundle door a surface hands work back through (#477).
    "themis/workflow/bundle.py",
    "themis/workflow/parameter_fill.py",
    "themis/workflow/variable_framing.py",
    # The LLM bridge, whose every refusal is now a species (#495).
    "themis/web/llm_bridge.py",
)


def _raises_with_a_literal(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every ``raise X("...")`` in one module — a site writing its own
    wording, which is what a species removes."""
    out = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(
                node.exc, ast.Call) or not node.exc.args:
            continue
        first = node.exc.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out.append((node.lineno, first.value))
        elif isinstance(first, ast.JoinedStr):
            out.append((node.lineno, "<f-string>"))
    return out


@pytest.mark.parametrize("module", NO_SITE_WRITES_ITS_OWN)
def test_no_raise_site_writes_its_own_sentence(module):
    """The rule, on the source rather than on what a test happens to reach.

    A branch no case exercises is checked here exactly like one every case
    exercises, which is the one thing running the module cannot do.
    """
    assert not _raises_with_a_literal(REPO / module)


def test_a_class_is_an_invariant_only_where_it_says_so():
    """The counterexample the second clause of :func:`_asserts` needs.

    ``EstimatorFailure`` derives from a builtin too, and so does every
    class under it — 404 raise sites, most of them refusals a reader is
    handed. So "derives from a builtin" was never available as the wider
    reading, and the declaration has to be a declaration.
    """
    from themis import registry
    from themis.refusals import EstimatorFailure

    declared = _under("Undeclared")
    assert {"Undeclared", "NoRowDeclared", "WidthNotStated",
            "NothingToBeTight"} <= declared
    assert issubclass(EstimatorFailure, RuntimeError)
    assert "EstimatorFailure" not in declared
    assert not issubclass(EstimatorFailure, registry.Undeclared)


def test_the_audit_door_reads_the_class_and_not_the_neighbour():
    """The role door shown deciding, on two raises in one function.

    A gate that has only ever been run where every raise is a finding is
    a gate nobody has seen say no — and ``kernel.py`` is exactly that
    shape, seven findings among its other raises.
    """
    tree = ast.parse(
        "def f(x):\n"
        "    if x:\n"
        "        raise VerificationError('the copy diverges from the answer')\n"
        "    raise SomethingElse('the copy diverges from the answer')\n")
    marked = _findings(tree)
    said = sorted((node.lineno, id(node) in marked)
                  for node, text in _texts(tree)
                  if text.startswith("the copy"))
    assert said == [(3, True), (4, False)], said


def _reads_the_exception(handler: ast.ExceptHandler) -> bool:
    """Whether this handler's body uses the exception it bound."""
    if handler.name is None:
        return False
    return any(isinstance(n, ast.Name) and n.id == handler.name
               for n in ast.walk(ast.Module(body=handler.body, type_ignores=[])))


def test_nothing_reads_an_invariant_it_caught_on_purpose():
    """What the declaration is worth only if this holds.

    :class:`themis.registry.Undeclared` says the sentence is never handed
    to a reader, and the language rule takes it at its word. What could
    make that false is a handler that catches one BY TYPE and puts its
    text somewhere — which is a handler treating it as control flow, and
    control flow that carries a sentence is a refusal wearing an
    invariant's clothes.

    Named handlers only. A blanket ``except Exception`` reads whatever
    reached it, including a ``ZeroDivisionError``, and that is a crash
    channel rather than a treatment of this species — the same reason a
    bare ``raise KeyError`` has always been excused despite
    :func:`themis.audits.audit` catching one.
    """
    declared, read = _under("Undeclared"), []
    for path in sorted((REPO / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        read += [
            f"{path.relative_to(REPO).as_posix()}:{h.lineno} "
            f"except {ast.unparse(h.type)} as {h.name}"
            for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
            and h.type is not None
            and declared & {n.id for n in ast.walk(h.type)
                            if isinstance(n, ast.Name)}
            and _reads_the_exception(h)
        ]
    assert not read, "\n".join(read)


def test_a_handler_that_did_read_one_would_be_caught():
    """The same gate shown saying no, on a snippet rather than on the
    package — because on the package it has never had anything to say."""
    caught = ast.parse(
        "try:\n    f()\nexcept WidthNotStated as exc:\n    return str(exc)\n")
    quiet = ast.parse(
        "try:\n    f()\nexcept WidthNotStated:\n    return UNSTATED\n")
    handlers = [n for tree in (caught, quiet) for n in ast.walk(tree)
                if isinstance(n, ast.ExceptHandler)]
    assert [_reads_the_exception(h) for h in handlers] == [True, False]


def test_the_raise_rule_would_catch_a_site_that_did():
    """The counterexample, through the same function. A gate only ever run
    against material that passes it is a gate nobody has seen say no."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "m.py"
        p.write_text('def f(x):\n    raise ValueError(f"{x} must be a dict")\n',
                     encoding="utf-8")
        assert _raises_with_a_literal(p)
        p.write_text('def f(x):\n    raise ValueError(Species.IS_NOT, where=x)\n',
                     encoding="utf-8")
        assert not _raises_with_a_literal(p)


def test_the_raise_rule_catches_what_the_scan_above_cannot():
    """Why both rules, measured rather than argued.

    A refusal with no function word in it reads as a formula to
    :func:`_english_clause_in` and is not counted — so on the modules that
    have finished, the scan alone would let one back in.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "m.py"
        p.write_text('def f(pool):\n    raise SomeError(f"pool={len(pool)}")\n',
                     encoding="utf-8")
        assert not _clauses_in(p.read_text(encoding="utf-8"))
        assert _raises_with_a_literal(p)


def test_the_debt_is_exactly_what_it_says():
    """A count rather than a ceiling, so the list can only shrink.

    A ceiling is room to add one more, which is how a list meant to empty
    stops emptying. The cost is that finishing part of a module is an edit
    here as well, and that is the intended cost: the number is what says
    how far the second language has got.

    A loop rather than one case per module, now that there are none. A
    parametrization over an empty table is a skipped test, and a check
    that reads as unfinished is the wrong way for a finished one to look.
    """
    left_over = _owed()
    for module, owed in STILL_ONE_LANGUAGE.items():
        left = left_over[module]
        if not left:
            what = f"{module} is done — delete its line here."
        elif left < owed:
            what = f"{module} is down to {left} — lower the number here."
        else:
            what = (f"{module} has {left} texts in one language, up from "
                    f"{owed}: give the new ones their other language.")
        assert left == owed, what


@pytest.mark.parametrize("entry", sorted(ALLOWED_SLOTS))
def test_every_allowance_is_still_being_used(entry):
    """An allowance for a slot nobody writes to is one nobody checked.

    The same reason the reader-side table pins its paths: a dead entry is
    how the next one gets added, by copying a line that costs nothing.
    """
    where, _, slot = entry.partition("::")
    live = {(module, s) for module, _, s, _, _ in _reader_facing()}
    assert any(s == slot and (where in ("*", module)) for module, s in live), (
        f"{entry} is excused but nothing there writes a sentence any more; "
        f"drop the entry or find where it moved")


#: The two prompt frames, each beside the document it continues. Written
#: down here rather than read off the module because the pairing is the
#: claim ``Wrote.PROMPTED`` makes: a frame is not free-standing text, it is
#: the next paragraph of a file, and which file is what settles it.
PROMPT_FRAMES: tuple[tuple[str, str], ...] = (
    ("render_reply", "themis/prompts/response_rendering.md"),
    ("propose_theta_priors", "themis/prompts/propose_theta_priors.md"),
)

#: The bridge, whose two prompt-writing functions the pairs above name.
BRIDGE = "themis/web/llm_bridge.py"


def _frame(function: str) -> str:
    """Everything :data:`BRIDGE` writes inside one function, joined.

    Every literal rather than the frame alone, because the frame is
    assembled from pieces and nothing binds a name to it — so the widest
    reading is the only one available, and it is the right one anyway: a
    function excused as ``PROMPTED`` should have nothing in it but the
    prompt. Documentation is dropped the way the census drops it, since a
    docstring is written for whoever maintains this.
    """
    tree = ast.parse((REPO / BRIDGE).read_text(encoding="utf-8"))
    excused, slots = _unaddressed(tree), _slots(tree)
    return "".join(text for node, text in _texts(tree)
                   if slots.get(id(node)) == function and id(node) not in excused)


def _in_its_own_voice(prose: str) -> str:
    """A document with its quotations taken out.

    A file is not written in a language because a character of one appears
    in it. ``response_rendering.md`` is 2258 lines of English and cites one
    section of another document by its own title, which is a citation
    spelled the way that finds it — the distinction ``Wrote.QUOTED`` draws
    for a literal, drawn here for a paragraph. Fenced blocks go for the
    same reason and one more: what a worked example holds is a rendering,
    and a rendering is in the reader's language by construction.
    """
    prose = re.sub(r"```.*?```", "", prose, flags=re.DOTALL)
    return re.sub(r"`[^`]*`|\"[^\"]*\"|“[^”]*”", "", prose)


@pytest.mark.parametrize("function,document", PROMPT_FRAMES)
def test_a_prompt_frame_is_in_the_language_of_the_document_it_continues(
        function, document):
    """The rule ``PROMPTED`` states, checked rather than trusted.

    Not "the frame is English": a prompt written in Chinese tomorrow is a
    document with one convention like any other, and its frame should
    follow it there. What is pinned is that the two agree — which is what
    these two did not do, one in English beside its endonym and one in
    Chinese twenty lines down, because nothing had ever said which language
    belonged and both answers were equally defensible.
    """
    prose = _in_its_own_voice((REPO / document).read_text(encoding="utf-8"))
    assert bool(CJK.search(_frame(function))) == bool(CJK.search(prose)), (
        f"{BRIDGE}::{function} writes its prompt in one language and "
        f"{document} is written in the other; a frame is the next paragraph "
        f"of the document it is sent with, not a text of its own"
    )


def test_a_frame_in_the_language_its_document_is_not_would_be_refused():
    """The counterexample, and the near-miss that shaped the measurement.

    The first line is what ``propose_theta_priors`` wrote until this cut,
    against a document in the other language — the case the pair above
    exists for. The second is why the pair does not simply search the file:
    a document that cites one section of another by its title is not
    written in the title's language, and a check that said it was would
    have been failed by 2258 lines of English over two characters.
    """
    english = _in_its_own_voice("The reply, rendered as this document says.")
    assert bool(CJK.search("因果图(kernel program):\n")) != bool(
        CJK.search(english))
    assert not CJK.search(
        _in_its_own_voice('see §"输出 (2)" for the promise this keeps'))


@pytest.mark.parametrize("function,_document", PROMPT_FRAMES)
def test_a_prompt_that_sources_reader_text_takes_the_reader_s_language(
        function, _document):
    """The other half, and the half that makes the allowance honest.

    ``PROMPTED`` excuses a frame from having a second language BECAUSE the
    reader's is a parameter of the request. A function that asks a model for
    text a reader will hold and takes no such parameter is not covered by
    that reason — it is writing for whoever the model guesses, which is the
    defect. This says no to removing ``lang`` from either signature.
    """
    tree = ast.parse((REPO / BRIDGE).read_text(encoding="utf-8"))
    defined = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == function]
    assert len(defined) == 1, f"{function} is not one function in {BRIDGE}"
    takes = {arg.arg for arg in defined[0].args.args + defined[0].args.kwonlyargs}
    assert "lang" in takes, (
        f"{BRIDGE}::{function} asks a model for text a reader is handed and "
        f"never takes their language; the frame's own language is then the "
        f"author's guess rather than the document's convention, and the "
        f"allowance covering it says the opposite"
    )


def _lang_taking_bridge_doors() -> set[str]:
    """The bridge functions whose answer is prose in the reader's language."""
    tree = ast.parse((REPO / BRIDGE).read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and "lang" in {a.arg for a in node.args.args + node.args.kwonlyargs}
    }


def test_a_caller_of_one_of_those_doors_says_who_is_reading():
    """The same rule one layer out, and the layer it was missing on.

    The check above holds the DOOR to taking the reader's language. It says
    nothing about whether anyone walks through it carrying one, and for as
    long as it stood alone nobody did: all four web endpoints called these
    functions without ``lang``, so both prose channels answered every
    reader in the language the site was written in — while the same
    browser rendered every other answer in the language they had picked.

    Every other channel is language-neutral by construction (an artifact
    goes out, this surface renders it), which is why this was the one
    requirement with nothing to state it: the fact that a channel produces
    PROSE, and therefore has to know its reader, is not visible in a type.
    So it is stated here, against the signatures rather than against a list
    of endpoints somebody has to remember to extend.
    """
    doors = _lang_taking_bridge_doors()
    assert doors, f"no function in {BRIDGE} takes the reader's language"
    stray = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        if path.samefile(REPO / BRIDGE):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            named = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
            if named in doors and not any(
                    kw.arg == "lang" for kw in node.keywords):
                stray.append(f"{path.relative_to(REPO)}:{node.lineno} {named}")
    assert not stray, (
        f"{stray} ask a model for text a reader will hold and do not say "
        f"who is reading; the answer is prose and a sentence has its "
        f"language the moment it is written, so there is no later point at "
        f"which a surface can pick one"
    )


def _clauses_in(source: str) -> list[tuple[str, str]]:
    """(slot, allowance) for the reader-facing texts in one snippet."""
    tree = ast.parse(source)
    excused, slots = _unaddressed(tree), _slots(tree)
    out = []
    for node, text in _texts(tree):
        if id(node) in excused:
            continue
        if _english_clause_in(text) is None and not CJK.search(text):
            continue
        slot = slots.get(id(node), "<module>")
        out.append((slot, (_allowance_for("<snippet>", slot) or (None,))[0]))
    return out


def test_a_new_slot_writing_one_language_is_refused():
    """The counterexample: the rule has to say no to something.

    A producer added tomorrow, in the shape the ones this item translated
    were in, and excused by nothing. Once in each language, because a rule
    that only recognised the language it was written against is the defect
    this arm was widened to close.
    """
    assert _clauses_in(
        'DataGap(description="the treatment has no variation in the data")'
    ) == [("DataGap.description", None)]
    assert _clauses_in(
        'DataGap(description="这批数据里处理变量没有变异")'
    ) == [("DataGap.description", None)]


def test_a_browser_sentence_outside_a_words_is_refused():
    """The same counterexample, on the surface that has no ``ast``.

    Three lines, one file: a heading typed straight into the markup, the
    same heading given its languages, and the file's own note to whoever
    maintains it. Only the first is a reader being handed one language,
    and telling the three apart is the whole of this half of the rule.
    """
    owed = _lines_owed("\n".join([
        "// 这一行是写给维护者的注释",
        "const TITLE = { zh: '因果验证器', en: 'Causal verifier' }",
        "const heading = <h2>因果验证器</h2>",
    ]))
    assert [(allowance, line) for _, allowance, line in owed] == [
        (Wrote.SAID.value, "const TITLE = { zh: '因果验证器', en: 'Causal verifier' }"),
        ("", "const heading = <h2>因果验证器</h2>"),
    ]


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


def test_an_invariant_is_not_addressed_to_anybody_who_asked():
    """A builtin raised is a bug report, and a bug report has one reader."""
    assert _clauses_in(
        'raise ValueError("the column set and the frame do not agree")') == []


def test_a_refusal_the_reader_is_handed_is_not_an_invariant():
    """The other side of that split, which is where 276 texts were hiding.

    Same statement, same slot, and the only difference is the name being
    raised — which is the difference the ``or`` in the old rule spanned.
    """
    assert _clauses_in(
        'raise EstimatorFailure(Refusal.INVALID_INPUT, '
        '"the design requires an instrument to make that claim about")'
    ) == [("EstimatorFailure[1]", None)]
