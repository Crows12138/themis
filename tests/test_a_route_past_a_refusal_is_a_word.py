"""The way past a refusal is this occasion's fact, and it travels as a word.

A refusal answers two questions, and until #432 the envelope had a slot for
only one of them. ``kind`` says what a reader is to make of the refusal —
five answers, one per species, declared once beside the sentence. What it
cannot say is the way OUT, because that is not the species' to know:
``overlap_insufficient`` is raised at five sites, and past it lies a column
that has to vary at four of them and a design that manufactures the
contrast at the fifth. One sentence per species cannot hold five answers.

So the sites that knew the way out wrote it themselves, into the free-text
message beside the description — eleven of them, in English, at the end of
a sentence, inside a report that is otherwise the reader's language and
behind no gate that could see it. The description said what was wrong and
the same string went on to say what to do about it, and nothing in the
build distinguished the two.

:class:`themis.refusals.Remedy` is the slot that was missing: a token and,
where the route names something, the occasion's own name for it — a column,
a parameter, an estimator, none of them in any language. The sentence is
assembled where the reader's language is known, on each surface that has
one.

What this module holds is that the two stay apart. A route says as much in
every language and names at most the one thing it names (the first three
checks); every raise site takes its route from the vocabulary rather than
inventing a token (the fourth); and no refusal's own sentence tells a
reader what to do, which is the check that had thirteen answers on the
commit before this one.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import string

import pytest

from themis import language, refusals
from themis.input.syntactic_validator import validator_for
from themis.output import analysis_report
from themis.refusals import EstimatorFailure, Refusal, Remedy

from tests.test_a_refusal_says_one_thing_in_every_language import (
    AUTHORS, DOORS,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
KERNEL = ROOT / "themis"


# --- a route is a sentence with at most one hole ------------------------------


def _slots(template: str) -> frozenset[str]:
    return frozenset(
        name for _lit, name, _spec, _conv in string.Formatter().parse(template)
        if name
    )


@pytest.mark.parametrize("member", sorted(Remedy, key=str))
def test_a_route_says_as_much_in_every_language(member):
    """Not "has text in both" — fills the same hole in both.

    A route whose Chinese names the column and whose English does not is
    two different routes wearing one token, and each renders perfectly on
    its own, so nothing but this would notice. It is also what
    ``takes_object`` claims when it asks *any* language, and a property
    that reads one language to answer for all of them needs the two to
    agree.
    """
    assert set(member.template) == set(language.written()), member
    holes = {lang: _slots(text) for lang, text in member.template.items()}
    assert len(set(holes.values())) == 1, (member, holes)


@pytest.mark.parametrize("member", sorted(Remedy, key=str))
def test_a_route_names_at_most_the_one_thing_it_names(member):
    """``{subject}`` or nothing.

    The occasion hands a route ONE name, so a template with a second hole
    is a template nobody can fill — and it would reach a reader with a
    brace in it, which is the failure mode a sentence assembled far from
    its data has.
    """
    assert _slots(member.template["zh"]) <= {"subject"}, member


@pytest.mark.parametrize("member", sorted(Remedy, key=str))
def test_a_route_renders_in_every_language(member):
    """Both ways it can be read: taken, and named.

    Taken it is :func:`route` and the hole is filled from the occasion.
    Named it is :func:`remedy_word`, which is what a surface holding the
    vocabulary itself gets — the template, hole and all, as the
    outcome-error designs already reach one.
    """
    for lang in sorted(language.written()):
        subject = "col" if member.takes_object else None
        taken = refusals.route(member, subject, lang)
        assert taken and "{" not in taken, (member, lang, taken)
        assert refusals.remedy_word(member, lang) == member.template[
            language.token(lang)]


def test_a_route_that_names_something_is_given_something_to_name():
    """Which of the two a member is belongs to the member.

    Not to the raise site: a site that forgot the object would put a brace
    in a reader's sentence, and a site that supplied one to a route with
    no hole would have it silently dropped. Both are refused where the
    route is built, which is where a mistake can still be attributed.
    """
    with pytest.raises(ValueError):
        refusals.route(Remedy.USE_METHOD)
    with pytest.raises(ValueError):
        refusals.route(Remedy.CHANGE_DESIGN, "anything")
    with pytest.raises(ValueError):
        EstimatorFailure(Refusal.OVERLAP_INSUFFICIENT, "x",
                         remedies=[Remedy.SUPPLY_DATA_VARIATION])


def test_a_route_this_build_never_declared_is_refused_at_the_producer():
    """A token invented at a raise site is a token no surface can render.

    Refused where it is written rather than dropped where it is read: the
    reader would simply never learn there had been a way out.
    """
    with pytest.raises(ValueError):
        EstimatorFailure(Refusal.OVERLAP_INSUFFICIENT, "x",
                         remedies=[("collect_more_data", "n")])


# --- the envelope, and the two surfaces that read it --------------------------


def _refused(**kwargs) -> dict:
    result: dict = {"query_kind": "effect", "status": "refused"}
    exc = EstimatorFailure(Refusal.OVERLAP_INSUFFICIENT, "no contrast.",
                           **kwargs)
    refusals.record(result, estimator="backdoor", exc=exc)
    return result


def test_the_envelope_carries_the_route_as_a_token_and_a_name():
    """Neither part in any language, which is what makes the row portable."""
    block = _refused(remedies=[(Remedy.SUPPLY_DATA_VARIATION, "dose"),
                               Remedy.CHANGE_DESIGN])["estimator_failure"]
    assert block["remedies"] == [
        {"remedy": "supply_data_variation", "subject": "dose"},
        {"remedy": "change_design"},
    ]
    whole = validator_for("query_result.schema.json")
    admits = whole.evolve(schema=whole.schema["properties"]["estimator_failure"])
    assert not list(admits.iter_errors(block))


def test_a_refusal_with_no_way_out_carries_no_key_for_one():
    """An empty list and no list would say the same thing twice, and a
    reader meeting an empty "what you can do" heading learns nothing."""
    assert "remedies" not in _refused()["estimator_failure"]
    assert "remedies" not in _refused(remedies=[])["estimator_failure"]


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_report_says_the_route_in_the_reader_s_language(lang):
    """The occasion's name survives; the words around it are the reader's."""
    result = _refused(remedies=[(Remedy.SUPPLY_DATA_VARIATION, "dose"),
                                Remedy.CHANGE_DESIGN])
    text = analysis_report.build_analysis_report(result, lang=lang)
    for member in (Remedy.SUPPLY_DATA_VARIATION, Remedy.CHANGE_DESIGN):
        assert str(member) not in text, (member, lang)
    assert "dose" in text
    assert refusals.route(Remedy.CHANGE_DESIGN, None, lang) in text


def test_a_route_the_report_has_never_heard_of_is_dropped_rather_than_printed():
    """A result written by a newer build than the one reading it.

    The opposite of what the same report does with a ``kind`` it cannot
    read, and deliberately: an unreadable kind still means a refusal
    happened and the section has to appear, while an unreadable route is
    advice that cannot be given. Printing the token would offer a reader
    an instruction in a language nobody wrote.
    """
    result = _refused(remedies=[(Remedy.SUPPLY_DATA_VARIATION, "dose")])
    result["estimator_failure"]["remedies"].append({"remedy": "buy_a_bigger_n"})
    text = analysis_report.build_analysis_report(result)
    assert "buy_a_bigger_n" not in text
    assert "dose" in text


# --- and no sentence says what a route says -----------------------------------


#: The verbs by which English tells a reader to act.
#:
#: Not a general parser: a clause opening with a bare verb is the one shape
#: an instruction reliably takes, and the vocabulary below is what this
#: repository actually reached for when a raise site wanted to say what to
#: do — read off the thirteen sites #432 converted — together with the
#: verbs its own routes are written with. A route phrased some other way
#: would slip past this, which is why the check below is not the only one:
#: a site with a route to give has :class:`Remedy` to give it through, and
#: this is what stops the sentence from being the easier option.
INSTRUCTS = (
    r"(supply|use|pass|change|set|declare|provide|specify|replace|switch|"
    r"add|drop|remove|re-?run|call|try|choose|give|make|fit|check|see|"
    r"consider|prefer|widen|narrow|report|state|name)\b"
)

#: Where a clause begins: the start of the text, or after a mark that ends
#: one. ``, or `` is included because that is how a second route was joined
#: to a first — "supply data ..., or use a design that creates the contrast".
_HEAD = re.compile(
    r"(?:^|[.;:]\s+|—\s*|,\s+(?:or|then)\s+)" + INSTRUCTS, re.I)


#: Sentences that open with one of the verbs above and are not instructions.
#: Empty, and meant to stay that way: an entry here is a claim that a
#: reader would not read it as being told to do something.
SAID_ANYWAY: dict[str, str] = {}


def _authored_text(node: ast.Call):
    """The sentence a filing site wrote itself, if it wrote one.

    Both doors, and only the sentence: ``details`` and ``recorded`` carry
    the occasion's values and are not addressed to a reader in prose.
    """
    if len(node.args) >= 2:
        return node.args[1]
    return next((kw.value for kw in node.keywords if kw.arg in AUTHORS), None)


def _text_of(node) -> str:
    """One authored sentence, with its interpolations closed up.

    A hole is replaced by a marker rather than deleted: ``f"...{t!r} has a
    single level. Supply..."`` must not become one long clause, and a
    deleted hole would join the two.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_text_of(part) for part in node.values)
    if isinstance(node, ast.FormattedValue):
        return "•"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _text_of(node.left) + _text_of(node.right)
    return ""


def _route_prose(where: pathlib.Path | None = None) -> list[str]:
    """Every refusal sentence in the tree that tells a reader what to do.

    The species' own sentences are read too, and for the same reason: a
    route belongs to the occasion, so one written into the sentence every
    raise site shares is the same defect one level up.
    """
    where = where or KERNEL
    found = []
    for path in sorted(where.rglob("*.py")):
        module = path.relative_to(where.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            door = (node.func.id if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", ""))
            if door not in DOORS:
                continue
            text = _text_of(_authored_text(node))
            if (hit := _HEAD.search(text)) and text not in SAID_ANYWAY:
                found.append(f"{module}:{node.lineno} …{text[hit.start():]!r}")
        if path.name != "refusals.py":
            continue
        for name, words in refusals.SAYS.items():
            for lang, text in words.items():
                if (hit := _HEAD.search(text)) and text not in SAID_ANYWAY:
                    found.append(f"SAYS[{name}][{lang}] …{text[hit.start():]!r}")
    return sorted(found)


def test_a_refusal_does_not_tell_the_reader_what_to_do():
    """The description says what is wrong; the routes say what to do.

    Two things in one string is what put an English instruction into a
    Chinese report — the sentence was the raise site's to write, so the
    route it knew went in beside the fault it had measured, and no gate
    could tell them apart afterwards. They are separable now, and the
    sentence is not where the route goes.
    """
    assert not _route_prose(), (
        "these refusal sentences tell the reader what to do; the route past "
        "one refusal is themis.refusals.Remedy's, on the occasion it was "
        "raised"
    )


def _module(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    (tmp_path / "themis").mkdir(exist_ok=True)
    (tmp_path / "themis" / "estimator.py").write_text(body, encoding="utf-8")
    return tmp_path / "themis"


def test_the_check_sees_a_route_glued_to_a_description(tmp_path):
    """The shape it has to catch, as all thirteen sites wrote it: a fault
    stated, a full stop, and an instruction in the same string."""
    where = _module(tmp_path, (
        "raise EstimatorFailure(\n"
        "    Refusal.OVERLAP_INSUFFICIENT,\n"
        "    f'{t!r} has a single observed level. Supply data with "
        "variation in it.',\n"
        ")\n"
    ))
    assert _route_prose(where)


def test_the_check_sees_a_route_joined_to_another_one(tmp_path):
    """The second half of the shape: two routes in one clause, which is
    how the sentence that had no slot for either of them managed both."""
    where = _module(tmp_path, (
        "raise EstimatorFailure(\n"
        "    Refusal.OVERLAP_INSUFFICIENT,\n"
        "    'no treated units; supply variation, or use an RCT.',\n"
        ")\n"
    ))
    assert _route_prose(where)


def test_the_check_passes_a_sentence_that_only_says_what_is_wrong(tmp_path):
    """The other direction, so the check is not just refusing prose.

    Description is allowed to be long, to name the estimator, and to use
    the same verbs about what the ESTIMATOR did — what it may not do is
    address the reader.
    """
    where = _module(tmp_path, (
        "raise EstimatorFailure(\n"
        "    Refusal.OVERLAP_INSUFFICIENT,\n"
        "    f'the g-formula would extrapolate the absent arm, and the "
        "estimator uses no data outside {a!r}.',\n"
        ")\n"
    ))
    assert not _route_prose(where)


# --- every route is one somebody can be given ---------------------------------


def _remedy_arguments() -> dict[str, list[str]]:
    """Every route named at a raise site, by member, and how it was named."""
    named: dict[str, list[str]] = {}
    for path in sorted(KERNEL.rglob("*.py")):
        module = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            given = next((kw.value for kw in node.keywords
                          if kw.arg == "remedies"), None)
            if given is None:
                continue
            for inner in ast.walk(given):
                if (isinstance(inner, ast.Attribute)
                        and getattr(inner.value, "id", None) == "Remedy"):
                    named.setdefault(inner.attr, []).append(
                        f"{module}:{node.lineno}")
                elif (isinstance(inner, ast.Constant)
                        and isinstance(inner.value, str)
                        and inner.value in refusals.REMEDY_BY_NAME):
                    named.setdefault(f"as a string: {inner.value}", []).append(
                        f"{module}:{node.lineno}")
    return named


def test_a_raise_site_names_its_route_by_the_member():
    """A token spelled out at a raise site is a second record of it.

    The member carries the sentence; the string carries nothing, and a
    typo in one is a route that vanishes at run time rather than at
    import.
    """
    assert not [k for k in _remedy_arguments() if k.startswith("as a string")]


def test_every_declared_route_is_one_some_refusal_offers():
    """A route nobody can be given is a translation of nothing.

    The registry's own rule one level down: what makes a vocabulary worth
    stating is that the envelope can carry every member of it.
    """
    named = set(_remedy_arguments())
    assert {m.name for m in Remedy} <= named, sorted(
        {m.name for m in Remedy} - named)


def test_the_schema_admits_exactly_the_routes_the_kernel_declares():
    """Read off the shipped document rather than the one in memory."""
    doc = json.loads((KERNEL / "schemas" / "query_result.schema.json")
                     .read_text(encoding="utf-8"))
    admitted = set(doc["$defs"]["remedy"]["properties"]["remedy"]["enum"])
    assert admitted == {str(m) for m in Remedy}
