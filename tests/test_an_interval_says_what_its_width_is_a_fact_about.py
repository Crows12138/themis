"""#419 — two numbers and a comma look the same however they were arrived at.

One result carries an ``iv_wald`` estimate at ``[0.326, 0.426]`` whose
``precision_budget`` says N≈16000 halves it, a Manski row at
``[0.348, 0.852]`` that no amount of data narrows, and a Balke-Pearl row at
``[0.552, 0.759]`` whose 2.4× over Manski is bought entirely by declaring an
instrument. Three intervals, one screen, and nothing to ask which is which.

The fact was recovered rather than stated: the report's causation renderer
probes ``point is not None`` and says so in a comment ("one pair of CI keys,
two meanings"), the explainer probes it again for a counterfactual cell,
``verdict.ts`` a third time, ``types.ts`` states it a fourth in prose, and
``numeric_result.interval`` carries ``{low, high}`` with nothing at all to
recover it from.

Four, not the three the entry was registered with. The fourth was not found
by reading — its leaf names collide with keys every renderer holds, so a
scan for them hits everywhere. What found it was the new field having no
reader in the block that carries it, which is why the gate for it is below
beside the browser's.

What makes it a missing FIELD rather than a missing sentence is that it was
stopping code from being written: ``evaluate_manski_tamer_bounds`` declined a
contrast it could compute, because the result was believed to be an outer
bound rather than a sharp one and no row could say so. The field arrived, the
belief was re-derived, and it was wrong — the contrast is sharp and is now
reported (#424). The field is what let that be settled instead of avoided.

The census below is the gate. Every pair of endpoints the schema can carry
is walked out of the schema and held equal to :data:`themis.intervals.DECLARED`
in both directions, so a pair added without an answer to "what is this the
width of" fails here instead of joining the ones a reader has to guess at.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from themis import intervals, registry
from themis.intervals import Endpoints, Tightness, Width

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "themis"
          / "schemas" / "query_result.schema.json")

#: The spellings this repository uses for one interval's two ends, paired.
#: Read off the schema rather than assumed: three different conventions are
#: live at once, and which one a slot uses says nothing about what it holds.
_PAIRS = (("lower", "upper"), ("low", "high"), ("ci_lower", "ci_upper"),
          ("lower_value", "upper_value"))


def _walk(node, path: str, out: list[tuple[str, str, str]]) -> None:
    """Every ``(container, lower, upper)`` the schema declares.

    Container paths are the dotted route to the object that OWNS the pair —
    a ``$defs`` name where the shape is shared through a ``$ref``, because
    that is the single place such a pair is declared and therefore the
    single place a new one can be added.
    """
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        for lo, hi in _PAIRS:
            if lo in props and hi in props:
                out.append((path or "<root>", lo, hi))
        for key, child in props.items():
            _walk(child, f"{path}.{key}" if path else key, out)
    for key in ("$defs", "definitions"):
        if isinstance(node.get(key), dict):
            for name, child in node[key].items():
                _walk(child, f"$defs.{name}", out)
    if isinstance(node.get("items"), dict):
        _walk(node["items"], f"{path}[]", out)
    for key in ("oneOf", "anyOf", "allOf"):
        for child in node.get(key) or ():
            _walk(child, path, out)


def _schema_pairs() -> set[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    _walk(json.loads(SCHEMA.read_text(encoding="utf-8")), "", found)
    assert found, "the walker found no endpoint pairs at all"
    return set(found)


# ====================================================== the census


def test_every_pair_the_envelope_can_carry_has_been_classified():
    """The direction that matters: a slot with no answer to "what is this
    the width of" is a slot whose reader is guessing, and the ``ci_`` prefix
    is exactly the guess that is wrong on three of the pairs wearing it."""
    missing = _schema_pairs() - set(intervals.BY_PAIR)
    assert not missing, (
        f"these endpoint pairs are on the envelope and unclassified: "
        f"{sorted(missing)}")


def test_no_pair_is_classified_that_no_result_can_carry():
    """The other direction, so the census cannot quietly describe a shape
    the schema stopped having."""
    extra = set(intervals.BY_PAIR) - _schema_pairs()
    assert not extra, (
        f"these are declared and the schema declares no such pair: "
        f"{sorted(extra)}")


def test_the_three_kinds_are_all_present_in_the_census():
    """Sanity on the classification itself: a census that put everything in
    one member would pass both directions above and say nothing."""
    seen = {e.width for e in intervals.DECLARED if e.width is not None}
    assert seen == set(Width), sorted(str(w) for w in set(Width) - seen)


def test_the_prefix_is_not_the_answer():
    """The measured fact this module exists for. Of the pairs spelled
    ``ci_lower`` / ``ci_upper``, not all are a point's confidence interval:
    one is an outer band on an identified set, and two are whichever of the
    two the run produced."""
    ci_pairs = [e for e in intervals.DECLARED if e.lower == "ci_lower"]
    assert ci_pairs
    not_sampling = [e for e in ci_pairs if e.width is not Width.SAMPLING]
    assert not_sampling, "the prefix would then be a sufficient answer"


# ====================================================== the two shapes


def test_a_pair_either_declares_a_width_or_names_what_settles_it():
    for e in intervals.DECLARED:
        assert (e.width is None) != (e.settled_by is None), str(e)
        assert e.because.strip(), str(e)


def test_a_pair_that_does_neither_is_refused():
    """The gate saying no. A pair with neither is a pair whose reader is
    back where this started; a pair with both is two records of one fact."""
    with pytest.raises(ValueError, match="exactly one of the two"):
        Endpoints("x", "lower", "upper", None, None, because="…")
    with pytest.raises(ValueError, match="exactly one of the two"):
        Endpoints("x", "lower", "upper", Width.SAMPLING,
                  intervals.CI_WIDTH_FIELD, because="…")


def test_a_run_decided_pair_reads_its_width_off_the_row():
    pair = intervals.pair_at("$defs.causationEstimate", "ci_lower", "ci_upper")
    assert pair.width is None
    assert intervals.width_of(
        pair, {intervals.CI_WIDTH_FIELD: "sampling"}) is Width.SAMPLING
    assert intervals.width_of(
        pair, {intervals.CI_WIDTH_FIELD: "outer_band"}) is Width.OUTER_BAND


def test_a_run_decided_pair_with_nothing_said_is_refused():
    """Not read as the common case, and not recovered from ``point``.

    Recovering it would be correct today and would be the second record of
    the fact that this module removes — the producer saw whether a point
    came out, and it is the one that has to say.
    """
    pair = intervals.pair_at("$defs.causationEstimate", "ci_lower", "ci_upper")
    with pytest.raises(intervals.WidthNotStated):
        intervals.width_of(pair, {"point": 0.3, "lower": 0.2, "upper": 0.9})


def test_a_word_outside_the_vocabulary_is_refused_by_listing_the_words():
    """The lookups name the alternatives.

    A producer writing a fourth spelling is how a closed vocabulary quietly
    becomes an open one, and the enum called by value would have said only
    that this was not a member — not which members there were to pick from.
    """
    with pytest.raises(ValueError, match=r"'ci'.*identification"):
        intervals.width_named("ci")
    with pytest.raises(ValueError, match=r"'tight'.*outer"):
        intervals.tightness_named("tight")


def test_a_slot_nobody_classified_is_refused_by_name():
    with pytest.raises(registry.NoRowDeclared) as caught:
        intervals.pair_at("numeric_estimate.something_new", "lower", "upper")
    named, key, _ = caught.value.args
    assert named == "themis.intervals.DECLARED"
    assert key == ("numeric_estimate.something_new", "lower", "upper")


# ====================================================== what a reader gets


def test_every_width_tells_the_reader_what_would_narrow_it():
    """The half a bare pair of numbers cannot carry, and the half that
    decides what someone does next: "collect more" is right for one member,
    wrong for the second, and half-right for the third."""
    for width in Width:
        assert width.narrows_with.strip(), str(width)
        for lang in ("zh", "en"):
            assert width.words[lang].strip(), f"{width}/{lang}"
            assert width.advice[lang].strip(), f"{width}/{lang}"


def test_the_three_pieces_of_advice_are_three_different_sentences():
    """A vocabulary whose members say the same thing is a vocabulary with
    one member and a longer spelling."""
    for lang in ("zh", "en"):
        said = {w.advice[lang] for w in Width}
        assert len(said) == len(Width), lang


def test_every_tightness_says_whether_a_better_procedure_would_help():
    for tight in Tightness:
        for lang in ("zh", "en"):
            assert tight.words[lang].strip(), f"{tight}/{lang}"
            assert tight.advice[lang].strip(), f"{tight}/{lang}"


def test_a_surface_that_misses_a_width_is_refused():
    with pytest.raises(ValueError, match="no rendering for interval width"):
        intervals.bind({Width.SAMPLING: "x"})


def test_a_surface_cannot_bind_something_outside_the_vocabulary():
    with pytest.raises(ValueError, match="not a declared interval width"):
        intervals.bind({w: "x" for w in Width} | {"made_up": "x"})


# ====================================================== tightness per method


def test_tightness_is_asked_per_pair_and_not_per_method():
    """The key is a (method, pair) because the two are different questions:
    Balke-Pearl runs a SECOND optimisation for the contrast rather than
    subtracting the arm's endpoints, so one word could not answer for both.

    No method's two pairs differ today. Manski-Tamer's was the entry that
    did, at "no contrast at all", and the reasoning behind it did not survive
    being re-derived (#424) — which leaves the SHAPE as what this pins: a
    pair the table does not carry is refused naming the pair, never answered
    from the method's other one.
    """
    assert intervals.tightness_of("manski_tamer_monotonicity", "arm") \
        is Tightness.SHARP
    assert intervals.tightness_of("manski_tamer_monotonicity", "contrast") \
        is Tightness.SHARP
    with pytest.raises(intervals.NothingToBeTight, match="reports no contrast"):
        intervals.tightness_of("frontdoor_partial", "contrast")
    with pytest.raises(registry.NoRowDeclared) as caught:
        intervals.tightness_of("manski_natural", "median")
    assert caught.value.args[1] == ("manski_natural", "median")


def test_the_methods_with_no_tightness_are_the_ones_with_no_producer():
    """Held against the other place the same fact is written, so the two
    cannot drift: the kernel's bounds verifier dispatches by method and
    raises for the one that has no producer."""
    from themis import kernel

    source = pathlib.Path(kernel.__file__).read_text(encoding="utf-8")
    unbuilt = {m for (m, pair), t in intervals.TIGHTNESS_OF.items()
               if t is None and pair == "arm"}
    assert unbuilt == {"frontdoor_partial"}, unbuilt
    for method in unbuilt:
        assert f'"{method} bounds verifier is not yet implemented ' in source, (
            f"{method} is declared to have no producer here and the kernel "
            f"does not say so")


def test_the_bounds_methods_are_the_schemas_own_vocabulary():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    declared = set(schema["$defs"]["boundsResult"]["properties"]["method"]["enum"])
    classified = {m for m, _pair in intervals.TIGHTNESS_OF}
    assert classified == declared

# ====================================================== what re-derives it


def test_the_verifier_keeps_its_own_answer_and_refuses_a_wrong_one():
    """A field nobody re-derives is a claim, and this one steers a decision.

    Sharpness is invisible in the endpoints: an outer bound and the
    identified set are both valid intervals over the same quantity, and
    which one a row is depends entirely on the procedure. So the bounds
    verifier holds its own table, the way it holds its own estimand table,
    and refuses a row that says the wrong word or no word at all — the
    second because "unstated" is a rendering fallback for old envelopes,
    not a licence for a producer to omit.
    """
    from themis.verifier import bounds_rules
    from themis.verifier.errors import VerificationError

    row = {"method": "manski_natural", "estimand": "arm_probability",
           "tightness": "sharp", "lower_value": 0.2, "upper_value": 0.8}
    bounds_rules._audit_numeric_bounds(
        row, method="manski_natural", rule="probe")

    for wrong in ("outer", None):
        bad = dict(row)
        if wrong is None:
            bad.pop("tightness")
        else:
            bad["tightness"] = wrong
        with pytest.raises(VerificationError, match="tightness"):
            bounds_rules._audit_numeric_bounds(
                bad, method="manski_natural", rule="probe")


def test_the_verifier_does_not_read_the_table_it_is_checking():
    """Independence, held rather than assumed.

    Two tables saying the same thing is the shape this module exists to
    remove — except across the verifier boundary, where it is the whole
    design: a check that read :data:`themis.intervals.TIGHTNESS_OF` would
    agree with the producer by construction, including when that table is
    what is wrong.
    """
    from themis.verifier import bounds_rules

    source = pathlib.Path(bounds_rules.__file__).read_text(encoding="utf-8")
    for reach in ("themis.intervals", "from ..intervals", "from .. import"):
        assert reach not in source, reach
    for (method, pair), tight in intervals.TIGHTNESS_OF.items():
        mine = bounds_rules._TIGHTNESS_BY_METHOD.get((method, pair))
        assert mine == (None if tight is None else str(tight)), (
            f"{method}/{pair}: the two independent tables disagree "
            f"({mine!r} vs {tight!r}); one of them is wrong and the point "
            f"of keeping two is that this is where it shows"
        )


# ====================================================== the browser's copy


def _web(table: str, field: str = "") -> dict[str, dict[str, str]]:
    """One browser table, as member -> language -> what it says.

    Out of both files the browser answers from: one of these two tables is
    the kernel's word for a member and is generated, the other is the
    advice beside it and is the browser's own. What this module asks is the
    same question of both, which is why it does not care which is which.
    """
    from tests import web_source

    said = web_source.words_map(table, web_source.vocabularies())
    assert said, f"the browser declares no {table}"
    return said


@pytest.mark.parametrize("table,attr", [
    ("INTERVAL_WIDTH_WORDS", "words"),
    ("INTERVAL_WIDTH_ADVICE", "advice"),
])
def test_the_browser_says_the_kernels_words_for_a_width(table, attr):
    """String by string, not key by key.

    The browser cannot import Python, so it keeps a copy; what stops the
    copy drifting is that it is held equal, which is the axis a key-set pin
    leaves open. This surface used to hold its own two-member table AND
    derive which member applied, so a third value could not have been added
    to the vocabulary without the browser silently answering with one of
    its two.
    """
    assert _web(table) == {
        str(w): dict(getattr(w, attr)) for w in Width
    }


@pytest.mark.parametrize("table,attr", [
    ("TIGHTNESS_WORDS", "words"),
    ("TIGHTNESS_ADVICE", "advice"),
])
def test_the_browser_says_the_kernels_words_for_a_tightness(table, attr):
    assert _web(table) == {
        str(x): dict(getattr(x, attr)) for x in Tightness
    }


def test_a_drifted_browser_copy_would_be_caught():
    """The gate shown refusing. ``CI`` is what this table said before the
    vocabulary existed, and it is a claim about a point on a row that has
    none."""
    drifted = dict(_web("INTERVAL_WIDTH_WORDS"))
    drifted["outer_band"] = {"zh": "CI", "en": "CI"}
    assert drifted != {str(w): dict(w.words) for w in Width}


def test_the_explainer_no_longer_settles_the_width_from_the_point():
    """The fourth working-out, gone from the source.

    It had its own two names for the two objects, and one of them was a
    fourth spelling of what the vocabulary calls an outer band.
    """
    source = (pathlib.Path(__file__).resolve().parent.parent / "themis"
              / "output" / "explainer.py").read_text(encoding="utf-8")
    assert "_CELL_CONFIDENCE_BAND" not in source
    assert "_CELL_INTERVAL_SAMPLING_BAND" not in source
    assert "width_or_unstated" in source


#: Which chunk of each reader surface SAYS a run-decided pair's width word.
#: Classified and said are two different things, and the census above only
#: asked the first: the counterfactual cell's pair was declared here, given a
#: word by the estimator that saw which object came out, printed by the report
#: — and dropped by the browser, which showed the identified interval and
#: nothing at all about the resampling (#425).
#:
#: Keyed by the pair rather than by the container, and its keys are held equal
#: to the run-decided pairs below, so a third bimodal object cannot arrive with
#: one surface silent.
SAYS_THE_WIDTH: dict[tuple[str, str, str], tuple[str, str]] = {
    ("$defs.causationEstimate", "ci_lower", "ci_upper"): (
        "_render_causation", "ANSWER_RENDERERS"),
    ("numeric_estimate.counterfactual_cell", "ci_lower", "ci_upper"): (
        "_render_counterfactual_cell_bounds", "answerRows"),
}


def _run_decided() -> set[tuple[str, str, str]]:
    return {(e.container, e.lower, e.upper) for e in intervals.DECLARED
            if e.settled_by == intervals.CI_WIDTH_FIELD}


def _report_body(name: str) -> str:
    source = (pathlib.Path(__file__).resolve().parent.parent / "themis"
              / "output" / "analysis_report.py").read_text(encoding="utf-8")
    body = source.split(f"def {name}(", 1)
    assert len(body) == 2, f"analysis_report declares no {name}"
    return body[1].split("\ndef ", 1)[0]


def _browser_chunk(name: str) -> str:
    from tests import web_source

    chunks = web_source.chunks(web_source.read(web_source.VERDICT))
    assert name in chunks, f"verdict.ts declares no {name}"
    return chunks[name]


#: What each surface reaching the word looks like in its own source. Named so
#: the checks below and the refusals beside them ask the same question of the
#: same text, which is the only way a "shown refusing" test proves anything
#: about the check it sits next to.
_REPORT_ASKS = "width_or_unstated"
_BROWSER_ASKS = "pointOrSet("


def test_every_run_decided_pair_names_a_reader_on_both_surfaces():
    """The denominator is the vocabulary's, not this table's."""
    assert _run_decided() == set(SAYS_THE_WIDTH), (
        "a pair whose width is settled by the run and named on no surface is "
        "the field of #419 arriving with nobody to say it")


def test_a_third_bimodal_pair_with_nobody_to_say_it_is_refused():
    """The constructed no for the denominator. A pair enters this table from
    the vocabulary, so one added there and not here fails rather than being
    classified and never said."""
    arrived = _run_decided() | {("numeric_estimate.some_new_cell",
                                 "ci_lower", "ci_upper")}
    assert arrived != set(SAYS_THE_WIDTH)


@pytest.mark.parametrize("pair,names", sorted(SAYS_THE_WIDTH.items()))
def test_the_report_reads_the_width_off_the_row_for_that_pair(pair, names):
    """Not "the module mentions it": the renderer for THAT pair has to ask
    :func:`themis.intervals.width_or_unstated`, which is the only function
    that turns the field into words."""
    assert _REPORT_ASKS in _report_body(names[0]), (
        f"{names[0]} renders {pair[0]}'s band without asking what its width "
        f"is a fact about")


@pytest.mark.parametrize("pair,names", sorted(SAYS_THE_WIDTH.items()))
def test_the_browser_says_the_width_for_that_pair(pair, names):
    """The browser's side of the same question. It reaches the word through
    the one renderer the shape has, so what is checked is that this chunk
    goes through it rather than printing a bare pair of numbers."""
    assert _BROWSER_ASKS in _browser_chunk(names[1]), (
        f"{names[1]} shows {pair[0]}'s interval without going through the "
        f"renderer that says which of the two objects the band is around")


#: What the browser's counterfactual cell printed before #425, verbatim: the
#: identified interval, and nothing about the resampling its own route
#: description promises. Kept as the counterexample rather than described,
#: because a gate that has never been shown the shape it exists to refuse is a
#: gate nobody has run.
_THE_BARE_PAIR = """
    const rows = [
      {
        label: counterfactualCellQuestion(cell, lang),
        value: `[${fmtNum(cell.lower)}, ${fmtNum(cell.upper)}]`,
      },
    ]
"""


def test_the_surface_this_replaced_would_be_refused():
    """The constructed no, on the text that actually shipped."""
    assert _BROWSER_ASKS not in _THE_BARE_PAIR
    assert _BROWSER_ASKS in _browser_chunk(SAYS_THE_WIDTH[(
        "numeric_estimate.counterfactual_cell", "ci_lower", "ci_upper")][1])


def test_the_shape_has_one_renderer_and_it_is_the_one_that_says_the_word():
    """The root cause, as a gate.

    ``band`` is built around a POINT and returns nothing without one, so an
    answer that is a SET had no renderer and every site had to write its own —
    which made writing it optional, and one of the two sites skipped it. The
    pin is that the point-or-set renderer is where the word is said, so a
    third site cannot reach the shape without reaching the word.
    """
    from tests import web_source

    source = web_source.read(web_source.VERDICT)
    chunks = web_source.chunks(source)
    assert "pointOrSet" in chunks
    assert "intervalWidthLabel(" in chunks["pointOrSet"]
    assert source.count("intervalWidthLabel(q.ci_width_is") <= 1, (
        "a second site reading the field directly is a second chance to say "
        "it differently, which is what this renderer replaced")


def test_the_browser_no_longer_settles_the_width_from_the_point():
    """The derivation this replaces, gone from the source.

    It was correct. It was also the third independent working-out of one
    fact, and the report and ``types.ts`` were the other two.
    """
    from tests import web_source

    source = web_source.read(web_source.VERDICT)
    assert "w.outer_band" not in source
    assert "ci_width_is" in source
