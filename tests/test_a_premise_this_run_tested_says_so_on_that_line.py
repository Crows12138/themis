"""What a check made on THIS run concluded, on the line of the premise it
adjudicates.

``testable`` is a static property of an assumption — could anyone check this,
in principle. It says nothing about whether anybody did, so a premise this run
tested and watched the data refuse reached the reader as the same line as one
nobody has ever looked at: same severity, same claim, same word ``testable``,
no adjudication. The compensating prose went into the gap list several screens
down, where it had to open by saying it was not a gap.

Two things were already carrying the verdict, and both are why this field
exists rather than reasons it does not need to:

- the overlap premise arrived under a SECOND ID where the count contradicted
  it, so the finding travelled inside the name of the thing it was a finding
  about — and the frame where every cell held both arms then said exactly what
  the frame nobody counted said;
- over-identification said it in a gap, and only when rejected.

What is pinned here:

- the verdict a run records is the one its own numbers give, in both
  directions — a producer overstating is caught because the verifier re-reads
  the evidence, and a producer saying nothing is caught because a run holding
  the outcome of a check owes the line a verdict;
- which of the three words a PASS earns is the check's to decide and not the
  call site's: counting cells settles the condition, a hypothesis test that
  did not reject has ruled nothing out;
- a refuted line is read before its unrefuted neighbours of the same severity;
- the verifier's restated table equals the producer's, and neither may name an
  assumption the glossary calls untestable.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import ledger
from themis import assumption_glossary
from themis.output import result_orchestrator
from themis.output.analysis_report import build_analysis_report
from themis.verifier import assumption_ledger_rules as rules
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json").read_text(
        encoding="utf-8"))
_CHECKED = (SCHEMA["properties"]["extensions"]["properties"]
            ["assumption_ledger"]["properties"]["assumptions"]["items"]
            ["properties"]["checked"]["properties"])

OVERID = "overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(nodes, edges, latent=()):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in nodes]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


TWO_INSTRUMENTS = _program(["z1", "z2", "x", "y"],
                           [("z1", "x"), ("z2", "x"), ("x", "y")],
                           latent=[("x", "y")])


def _iv_frame(leak: float, n: int = 6000, beta: float = 1.5) -> pd.DataFrame:
    """Two instruments for one treatment. ``leak`` is z2's direct path to the
    outcome — the exclusion restriction the over-identification test is a
    falsification of."""
    rng = np.random.default_rng(0)
    u = rng.standard_normal(n)
    z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
    x = 0.9 * z1 + 0.7 * z2 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = beta * x + leak * z2 + 2.0 * u + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"z1": z1, "z2": z2, "x": x, "y": y})


@pytest.fixture(scope="module")
def valid():
    return themis.estimate(TWO_INSTRUMENTS, _iv_frame(leak=0.0),
                           ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def refuted():
    return themis.estimate(TWO_INSTRUMENTS, _iv_frame(leak=1.2),
                           ci_bootstrap=0)["results"][0]


def _line(result: dict, assumption_id: str) -> dict:
    entries = (result["extensions"]["assumption_ledger"]["assumptions"])
    return next(e for e in entries if e.get("id") == assumption_id)


# --- what a run records -------------------------------------------------------


def test_the_data_refusing_a_premise_is_on_that_premises_line(refuted):
    """The instruments are over-identified and one of them has a direct path
    to the outcome, so the joint exclusion restriction is refutable and this
    data refutes it. The answer still comes back — 2.11 against a true 1.5 —
    which is exactly why the line has to say so."""
    assert _line(refuted, OVERID)["checked"] == {
        "verdict": "refuted", "by": "robust_hansen_j"}


def test_a_test_that_did_not_reject_has_not_established_anything(valid):
    """The same design with valid instruments. ``not_refuted`` and not
    ``held``: the Hansen J failing to reject rules nothing out, and a ledger
    saying the data established the exclusion restriction would be claiming
    something no over-identification test can give."""
    assert _line(valid, OVERID)["checked"] == {
        "verdict": "not_refuted", "by": "robust_hansen_j"}


def test_the_word_a_pass_earns_belongs_to_the_check(valid):
    """Not to the site that ran it. A producer reports whether its check
    FAILED and nothing else; whether passing SETTLES the premise is declared
    once, on the check, because it is a property of what the check does."""
    assert ledger.checked(ledger.Check.ROBUST_HANSEN_J, False) == (
        ledger.Check.ROBUST_HANSEN_J, ledger.Verdict.NOT_REFUTED)
    assert ledger.checked(ledger.Check.STRATUM_ARM_COUNTS, False) == (
        ledger.Check.STRATUM_ARM_COUNTS, ledger.Verdict.HELD)
    for check in ledger.Check:
        assert ledger.checked(check, True)[1] is ledger.Verdict.REFUTED


def test_a_premise_nothing_checked_says_nothing_rather_than_passing(valid):
    """Exclusion itself is untestable and stays that way. Silence here is the
    honest answer, and it is a different answer from ``not_refuted``."""
    line = _line(valid, "iv2_exclusion_instruments_affect_outcome_only_via_"
                        "treatment")
    assert "checked" not in line
    assert line["testable"] is False


def test_the_refuted_line_leads_its_severity_group(refuted):
    """The ledger is read worst first and the reader meets the head of it, so
    a premise this run's own data refused printed fifth is buried. A second
    sort key and not a severity of its own: what it costs the answer is still
    what its layer costs."""
    entries = refuted["extensions"]["assumption_ledger"]["assumptions"]
    assert entries[0]["id"] == OVERID
    assert entries[0]["severity"] == "invalidating"
    assert entries[1]["severity"] == "invalidating"


# --- what the reader is handed ------------------------------------------------


def test_the_report_says_the_verdict_and_names_the_check(refuted):
    report = build_analysis_report(refuted, program=TWO_INSTRUMENTS)
    assert "这批数据否决了它" in report
    assert "异方差稳健 Hansen J 过度识别检验" in report


def test_the_line_stops_saying_testable_where_it_says_what_happened(refuted):
    """One line cannot usefully carry "somebody could check this" beside
    "somebody did, and here is what they found"; the second says strictly
    more, and printing both leaves the reader to notice they are one fact."""
    report = build_analysis_report(refuted, program=TWO_INSTRUMENTS)
    said = [line for line in report.splitlines() if "过度识别" in line]
    assert said, report
    assert not any("可检验" in line for line in said if line.startswith("- "))


def test_the_lead_line_counts_what_was_adjudicated(refuted):
    """It used to end "whether they hold is yours to audit one by one", which
    was true of every line while nothing could record a check."""
    said = ledger.summary(
        refuted["extensions"]["assumption_ledger"]["assumptions"], "zh")
    assert "其中 1 条这一次已经检验过" in said


def test_a_ledger_with_nothing_checked_still_says_it_is_all_yours():
    entries = [{"severity": "invalidating", "claim": [], "layer":
                "identification", "provenance": "inherent"}]
    assert "逐条审核" in ledger.summary(entries, "zh")
    assert "这一次已经检验过" not in ledger.summary(entries, "zh")


# --- the verifier re-derives it rather than believing it ----------------------


def _tampered(result: dict, change) -> dict:
    bad = copy.deepcopy(result)
    change(bad["extensions"]["assumption_ledger"]["assumptions"])
    return bad


def _find(entries: list, assumption_id: str) -> dict:
    return next(e for e in entries if e.get("id") == assumption_id)


def test_the_honest_ledger_passes(valid, refuted):
    themis.verify_assumption_ledger(valid)
    themis.verify_assumption_ledger(refuted)


def test_softening_a_refutation_is_caught(refuted):
    """The failure that matters most: the numbers say the data refused this
    premise and the line says the data merely did not refuse it."""
    def soften(entries):
        _find(entries, OVERID)["checked"]["verdict"] = "not_refuted"

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(refuted, soften))


def test_claiming_a_refutation_the_numbers_do_not_give_is_caught(valid):
    """The other direction. Moved to the head of its group first, because a
    refuted line sitting below unrefuted ones is a different defect and the
    order check would fire before this one."""
    def overstate(entries):
        line = _find(entries, OVERID)
        line["checked"]["verdict"] = "refuted"
        entries.remove(line)
        entries.insert(0, line)

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(valid, overstate))


def test_claiming_a_pass_established_it_is_caught(valid):
    def overstate(entries):
        _find(entries, OVERID)["checked"]["verdict"] = "held"

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(valid, overstate))


def test_saying_nothing_while_holding_the_outcome_is_caught(refuted):
    """The under-disclosure side, which is the shape this whole module is
    written around: the run tested it, the answer carries what it found, and
    the line reads like one nobody looked at."""
    def silence(entries):
        del _find(entries, OVERID)["checked"]

    with pytest.raises(VerificationError, match="says nothing about it"):
        themis.verify_assumption_ledger(_tampered(refuted, silence))


def test_a_verdict_on_a_line_no_check_addresses_is_caught(refuted):
    """A verdict stamped on the neighbouring premise tells the reader this
    data settled something it never asked about. ``not_refuted`` rather than
    ``refuted`` so the order rule does not answer first — burying a refutation
    is a different defect and has its own test below."""
    def misplace(entries):
        _find(entries, "iv3_independence_instruments_independent_of_latent_"
                       "confounders")["checked"] = {
            "verdict": "not_refuted", "by": "robust_hansen_j"}

    with pytest.raises(VerificationError, match="holds no record"):
        themis.verify_assumption_ledger(_tampered(refuted, misplace))


def test_reporting_the_weaker_of_two_tests_is_caught(refuted):
    """Both statistics are on this answer, and the robust one governs. A line
    attributing its verdict to the homoskedastic Sargan is reporting a test
    the data may not support the assumption of."""
    def weaken(entries):
        _find(entries, OVERID)["checked"]["by"] = "sargan"

    with pytest.raises(VerificationError, match="governs"):
        themis.verify_assumption_ledger(_tampered(refuted, weaken))


def test_a_line_cannot_be_untestable_and_adjudicated_at_once(refuted):
    """Two rules refuse this one edit, and which of them speaks first is not
    something to assert.

    The line names an assumption whose testability its own name settles, so
    the audit of what a name means answers before this coherence check gets
    to. What the door owes is a refusal; the reach of the rule this test is
    about is asked of that rule.
    """
    def contradict(entries):
        _find(entries, OVERID)["testable"] = False

    forged = _tampered(refuted, contradict)
    with pytest.raises(VerificationError):
        themis.verify_assumption_ledger(forged)

    entries = forged["extensions"]["assumption_ledger"]["assumptions"]
    with pytest.raises(VerificationError, match="untestable"):
        rules._check_verdicts(forged, entries)


def test_burying_a_refuted_line_under_its_neighbours_is_caught(refuted):
    def bury(entries):
        line = entries.pop(0)
        entries.insert(3, line)

    with pytest.raises(VerificationError, match="below an unrefuted one"):
        themis.verify_assumption_ledger(_tampered(refuted, bury))


# --- the two tables ------------------------------------------------------------


def test_the_verifier_restates_the_same_checks():
    """It must not import the producer's table: a verdict re-derived from the
    mapping its producer used is not an independent audit. What is NOT shared
    is the pair of readers — each side reaches into the envelope with its own
    code, which is the part that makes the re-derivation mean anything."""
    restated = {name: (frozenset(ids), settles)
                for name, ids, settles, _read in rules._CHECKS}
    declared = {str(check): (frozenset(ids), check.a_pass_settles_it)
                for ids, check, _read
                in result_orchestrator.WHAT_THIS_RUN_CHECKED}
    assert restated == declared


def test_the_two_tables_agree_about_precedence():
    """Later rows win on both sides, so the order is part of the table."""
    assert [name for name, _ids, _s, _r in rules._CHECKS] == [
        str(check) for _ids, check, _r
        in result_orchestrator.WHAT_THIS_RUN_CHECKED]


def test_the_contract_declares_both_whole_vocabularies():
    assert set(_CHECKED["verdict"]["enum"]) == {str(v) for v in ledger.Verdict}
    assert set(_CHECKED["by"]["enum"]) == {str(c) for c in ledger.Check}


def test_no_check_adjudicates_a_premise_the_glossary_calls_untestable():
    """The two fields answer the same question at two strengths, so a check
    against an id marked untestable would be the tree disagreeing with itself
    — and the report drops the ``testable`` word on an adjudicated line on
    the strength of this holding."""
    for ids, check, _read in result_orchestrator.WHAT_THIS_RUN_CHECKED:
        for declaration in sorted(ids):
            row = assumption_glossary._EXACT[declaration]
            assert row[1] is True, (str(check), declaration)


def test_every_verdict_is_one_some_check_can_earn():
    """``held`` is what a check whose pass SETTLES its premise gives back, and
    while no check settled anything the member read in the source exactly like
    a distinction the system draws. The import-time check refuses that; this
    says so where a reader looking for the rule will find it."""
    reachable = {ledger.checked(check, refused)[1]
                 for check in ledger.Check for refused in (True, False)}
    assert reachable == set(ledger.Verdict)
