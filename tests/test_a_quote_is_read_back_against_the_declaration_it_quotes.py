"""A gap quotes a variable's declaration back, and nothing read the quote.

A gap about measurement error lists, for each variable, which field of its
declaration names a known noise and the noise it names; a gap about a
dichotomised measure lists where the declaration cuts the variable. All
three are facts about the variable the same sentence names, and the record
of each is that variable's declaration. They travel as ``said``, and the
table that reads a fact against the declaration of what its sentence names
was walked over ``words`` alone. Bent to a noise the declaration never
wrote, to another piece of its text, to the same noise in letters it does
not use, to a field that names no noise, to any cut or none — every door
that reads the answer took all of them, and so did the same bend made to the
site the gap cites as well.

And the quote was not a quote. The producer matched a declaration without
regard to case and wrote back its list's own spelling, so ``FFQ`` came back
as ``ffq``, in the sentence and in the cited site. Looked for as written,
the site was not there, and the honest answer was refused. Every declaration
the corpus holds is written in lower case, which is how the two spellings
stayed one.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for, verify_honestly
from tests.test_measurement_error_concern import _make_program
from themis.output import data_gap_report
from themis.verifier import VerificationError
from themis.verifier.gap_claim_rules import (
    _HOW_IT_WAS_MEASURED,
    _KNOWN_NOISES,
    verify_gap_subjects,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

NOISY = "a_field_names_a_known_noise"
CUT = "a_threshold_cut_it_in_two"


def _statements(node, path=()):
    """(path, statement) for every statement of the two, found by its token
    rather than by the walk the rule uses."""
    if isinstance(node, dict):
        if node.get("token") in (NOISY, CUT) and isinstance(
                node.get("said"), dict):
            yield path, node
        for key, value in node.items():
            yield from _statements(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _statements(value, (*path, index))


def _at(node, path):
    for step in path:
        node = node[step]
    return node


def _declaration(program, variable):
    return next(s for s in program["statements"]
                if s.get("kind") == "variable"
                and s.get("predicate") == variable)


def _names(noise, text):
    return noise.lower() in (text or "").lower()


SITES = sorted(
    (name, path, statement["token"])
    for name, pair in SHAPES.items()
    for path, statement in _statements(pair["result"])
)


def test_the_statements_this_speaks_for():
    """The denominator, so a narrowing shows as a number."""
    counts: dict[str, int] = {}
    for _name, _path, token in SITES:
        counts[token] = counts.get(token, 0) + 1
    assert counts == {NOISY: 19, CUT: 2}, counts


def test_the_noises_a_gap_may_name_are_the_producers():
    """Restated, since no verifier may import the output layer, and held
    here: a list of the verifier's own would be judging a claim the gap
    does not make."""
    assert _KNOWN_NOISES == data_gap_report._MEASUREMENT_ERROR_PATTERNS
    assert _HOW_IT_WAS_MEASURED == data_gap_report._HOW_IT_WAS_MEASURED


# ------------------------------------------------- the quote, as written


#: Declarations in the letters people write them in.
_WRITTEN = {
    "an_abbreviation_in_capitals": {
        "intervention_measurement": "smoking via FFQ"},
    "a_capitalised_phrase": {
        "intervention_measurement": "Self-Reported smoking"},
    "all_capitals": {"intervention_measurement": "PROXY"},
    "a_covariate": {"confounder_measurement": "24-Hour Recall"},
    "the_other_measured_field": {
        "intervention_observability": "Single Visit reading"},
    "both_measured_fields": {"intervention_measurement": "Self-Report",
                             "intervention_observability": "via a proxy"},
    "in_chinese": {"intervention_measurement": "自报 吸烟"},
}


@pytest.mark.parametrize("case", sorted(_WRITTEN))
def test_a_noise_is_quoted_in_the_letters_its_declaration_uses(case):
    program = _make_program(**_WRITTEN[case])
    result = themis.run(program)["results"][0]
    stated = [s for _p, s in _statements(result) if s["token"] == NOISY]
    assert stated, case
    cited = {ref["ref_id"] for gap in result["data_gap_report"]["gaps"]
             for ref in gap.get("provenance") or ()}
    for statement in stated:
        said = statement["said"]
        text = _declaration(program, said["variable"])[said["field"]]
        assert said["phrase"] in text, (said, text)
        assert (f"program:variable:{said['variable']}:{said['field']}"
                f":contains:{said['phrase']}") in cited, cited
    verify_honestly(program, result)


# ------------------------------------------- and the quote, read back


def _false_of_the_declaration(program, statement):
    """(slot, value) for each way to make the statement false of the
    declaration it quotes."""
    said = statement["said"]
    declaration = _declaration(program, said["variable"])
    if statement["token"] == CUT:
        yield "cut", f"{said['cut']} or so"
        yield "cut", ""
        return
    text = declaration[said["field"]]
    yield "phrase", next(n for n in _KNOWN_NOISES if not _names(n, text))
    yield "phrase", next(
        text[i:i + 4] for i in range(len(text) - 3)
        if not any(_names(n, text[i:i + 4]) for n in _KNOWN_NOISES))
    if said["phrase"].upper() not in text:
        yield "phrase", said["phrase"].upper()
    for other in _HOW_IT_WAS_MEASURED:
        if other != said["field"] and said["phrase"] not in (
                declaration.get(other) or ""):
            yield "field", other
    yield "field", "time_window"


def test_a_quote_the_declaration_does_not_bear_out_is_refused():
    """Through the door that reads the answer, and by this rule."""
    refused = 0
    for name, path, _token in SITES:
        row = SHAPES[name]
        statement = _at(row["result"], path)
        for slot, value in _false_of_the_declaration(row["program"],
                                                     statement):
            forged = copy.deepcopy(row["result"])
            _at(forged, path)["said"][slot] = value
            with pytest.raises(VerificationError, match="never declared"):
                verify_gap_subjects(forged, row["program"])
            with pytest.raises(VerificationError):
                the_door_for(row["result"])(row["program"], forged)
            refused += 1
    assert refused == 98, refused


def test_the_site_it_cites_bent_with_it_is_no_second_record():
    """The cited site says the text contains the quote, and holds it only to
    that. Bent together to another piece of the text, both copies agree and
    the site is found — so what refuses it has to be the declaration."""
    refused = 0
    for name, path, token in SITES:
        if token != NOISY:
            continue
        row = SHAPES[name]
        said = _at(row["result"], path)["said"]
        text = _declaration(row["program"], said["variable"])[said["field"]]
        piece = next(text[i:i + 4] for i in range(len(text) - 3)
                     if not any(_names(n, text[i:i + 4])
                                for n in _KNOWN_NOISES))
        forged = copy.deepcopy(row["result"])
        _at(forged, path)["said"]["phrase"] = piece
        was = (f"program:variable:{said['variable']}:{said['field']}"
               f":contains:{said['phrase']}")
        moved = 0
        for gap in forged["data_gap_report"]["gaps"]:
            for ref in gap.get("provenance") or ():
                if ref.get("ref_id") == was:
                    ref["ref_id"] = was[:-len(said["phrase"])] + piece
                    moved += 1
        assert moved == 1, (name, was)
        with pytest.raises(VerificationError, match="never declared"):
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 19, refused


def test_a_true_quote_its_producer_did_not_choose_is_accepted():
    """A text can name several known noises, and the producer shows the
    first its list reaches: ``self-reported via questionnaire`` is quoted as
    ``self-report``. The other two are as true of the declaration, and so is
    a second measured field naming the same noise. Refusing them would be
    holding a gap to its producer's order rather than to the declaration."""
    accepted = 0
    for name, path, token in SITES:
        if token != NOISY:
            continue
        row = SHAPES[name]
        said = _at(row["result"], path)["said"]
        declaration = _declaration(row["program"], said["variable"])
        text = declaration[said["field"]]
        others = [("phrase", n) for n in _KNOWN_NOISES
                  if n != said["phrase"] and n in text]
        others += [("field", f) for f in _HOW_IT_WAS_MEASURED
                   if f != said["field"]
                   and said["phrase"] in (declaration.get(f) or "")]
        for slot, value in others:
            forged = copy.deepcopy(row["result"])
            _at(forged, path)["said"][slot] = value
            the_door_for(row["result"])(row["program"], forged)
            accepted += 1
    assert accepted == 13, accepted


def test_the_rule_is_silent_where_the_program_declares_no_such_variable():
    """Nothing to appeal to, and inventing the record out of the gap would
    be reading the authority off the thing being judged."""
    name, path, _token = next(site for site in SITES if site[2] == NOISY)
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    said = _at(forged, path)["said"]
    said["phrase"] = "a noise nobody declared"
    program = copy.deepcopy(row["program"])
    program["statements"] = [
        s for s in program["statements"]
        if not (s.get("kind") == "variable"
                and s.get("predicate") == said["variable"])]
    verify_gap_subjects(forged, program)
    with pytest.raises(VerificationError, match="never declared"):
        verify_gap_subjects(forged, row["program"])
