"""#395 eighth cut — a recovery verdict names what a negative came back on.

Both recovery blocks could say which theorem carried a POSITIVE verdict
(``criterion``, a four-value closed set) and had no field at all for a
negative — ``criterion`` is null on every one. So the whole of a negative
went into the row's one free-text slot: which condition failed, how far the
search went, and whether the negative is a proof rather than a miss.

Three of those are separable and now are. Which condition is a vocabulary
beside each producer; how far the search went was already ``search_budget``;
whether the negative is a proof is ``complete_criterion``, which is a
property of the criterion and not of this run — it used to be a clause
written into whichever sentence remembered it, in two modules.

The two rows that carried a sentence while ``recoverable`` was TRUE are the
sharpest evidence the slot was answering someone else's question: a field
named ``failure_reason`` saying that nothing failed, in words no reader
could ever see, because both surfaces read it only on a negative.
"""
from __future__ import annotations

import ast
import pathlib

import networkx as nx
import pytest

from themis import language
from themis.input.syntactic_validator import validator_for
from themis.output.analysis_report import build_analysis_report
from themis.output.result_orchestrator import to_dict
from themis.runtime import missing_data, selection_recovery
from themis.types import Atom, QueryKind, QueryResult, ResultStatus

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _validator():
    return validator_for("query_result.schema.json")


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


def _indicator(var: str, caused_by=()):
    return missing_data.MissingnessIndicator(
        id=f"R_{var}", missing_var=A(var),
        caused_by=tuple(A(c) for c in caused_by))


def _graph(edges):
    g = nx.DiGraph()
    for tail, head in edges:
        g.add_edge(A(tail), A(head))
    return g


def _selection_block(**over) -> dict:
    """The block as the scheduler serialises it, with one thing varied."""
    block = {
        "kind": "selection_recovery", "query_kind": "effect",
        "treatment": "x", "outcome": "y", "recoverable": False,
        "criterion": None, "selection_nodes": ["s"], "adjustment_set": [],
        "z_plus": [], "z_minus": [], "recovery_formula": "",
        "external_data_needed": [],
        "failure_reason": language.state(
            selection_recovery.Shortfall.NO_ADMISSIBLE_SELECTION_BACKDOOR_SET),
        "complete_criterion": False,
        "search_budget": 4, "reference": "Bareinboim & Pearl 2012",
    }
    block.update(over)
    return block


def _envelope(block) -> dict:
    return to_dict(QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        extensions={"selection_recovery": block},
    ))


# ------------------------------------------------------- the positive arm

def test_a_negative_verdict_states_which_condition_came_back_empty():
    """Both modules, both languages, and the token never reaching a reader."""
    empty = [
        selection_recovery.recover_effect(
            _graph([("x", "y"), ("y", "s")]), A("x"), A("y"), (A("s"),)),
        selection_recovery.recover_conditional(
            _graph([("x", "y"), ("y", "s")]), A("x"), A("y"), (A("s"),)),
        missing_data.analyze_missing_data(
            _graph([("x", "y")]),
            [_indicator("x", caused_by=("x",))], [A("x")], []),
    ]
    for verdict in empty:
        assert verdict.recoverable is False
        said = verdict.failure_reason
        assert isinstance(said, language.Statement), said
        for lang in sorted(language.written()):
            sentence = language.spoke(said, lang)
            assert sentence, (lang, said)
            assert said["token"] not in sentence, (lang, sentence)


def test_the_envelope_takes_a_negative_from_either_module():
    _validator().validate(_envelope(_selection_block()))


# ------------------------------------------------ a row that did not fail

@pytest.mark.parametrize("verdict", [
    pytest.param(
        lambda: selection_recovery.recover_effect(
            _graph([("x", "y")]), A("x"), A("y"), ()),
        id="no_selection_declared"),
    pytest.param(
        lambda: missing_data.analyze_missing_data(
            _graph([("x", "y")]), [], [A("y")], [A("x")]),
        id="no_missingness_declared"),
])
def test_a_row_that_did_not_fail_files_no_shortfall(verdict):
    """The sentence that used to sit here had nobody who could read it.

    Which row this is was already on it — no selection nodes, mechanism
    ``none`` — so the sentence added no fact either.
    """
    result = verdict()
    assert result.recoverable is True
    assert result.failure_reason is None


# ------------------------------------ the clause that became a field

def test_whether_a_negative_is_a_proof_is_a_fact_and_not_a_clause():
    """Two searches, two answers, and neither said in the sentence.

    The conditional case is an iff, so its negative IS a proof; the
    selection-backdoor criterion is sufficient only, so its negative is
    "not by this criterion". Nothing in either wording says which — a
    reader is told by the field, and a caller choosing what to try next
    can branch on it.
    """
    graph = _graph([("x", "y"), ("y", "s")])
    proof = selection_recovery.recover_conditional(
        graph, A("x"), A("y"), (A("s"),))
    miss = selection_recovery.recover_effect(graph, A("x"), A("y"), (A("s"),))
    assert proof.complete_criterion is True
    assert miss.complete_criterion is False
    for verdict in (proof, miss):
        for lang in sorted(language.written()):
            sentence = language.spoke(verdict.failure_reason, lang)
            assert "不等于" not in sentence and "not \"none exists\"" not in \
                sentence, (lang, sentence)


@pytest.mark.parametrize("complete,wanted", [(True, False), (False, True)])
def test_the_reader_adds_the_caveat_exactly_when_the_criterion_is_partial(
        complete, wanted):
    """And it is the READER that adds it, once, in their own language."""
    for lang in ("zh", "en"):
        report = build_analysis_report(
            _envelope(_selection_block(complete_criterion=complete)),
            lang=lang)
        said = "不等于" if lang == "zh" else "not \"none exists\""
        assert (said in report) is wanted, (lang, complete)


# --------------------------------------- a hole that holds several of them

def test_a_blocked_product_holds_its_factors_in_one_hole():
    """The estimand is a product, so its shortfall is a list in a hole.

    The seam between them is the reader's: this was ``"; ".join(...)`` plus
    a full stop, which is a kernel choosing punctuation for a language it
    had not been told.
    """
    graph = _graph([("z", "x"), ("z", "y"), ("x", "y")])
    indicators = [_indicator("z", caused_by=("z",))]
    est = missing_data.analyze_missing_data_estimand(
        graph, indicators, A("y"), A("x"), given=(), z=(A("z"),))
    assert est.recoverable is False
    factors = est.failure_reason["words"]["factors"]
    assert all(isinstance(one, dict) for one in factors), factors
    # Each names the target its OWN row carries, so no second record of it
    # can drift; the pair that used to say this held a literal `P(Y|X,Z)`.
    assert factors[0]["said"]["target"] == est.covariate.target_repr
    seams = {lang: language.spoke(est.failure_reason, lang)
             for lang in ("zh", "en")}
    assert seams["zh"] != seams["en"]


def test_no_surface_is_handed_a_literal_estimand_to_print():
    """`requires` restated two targets the row already carried, in a form
    that was never this program's: `P(Y|X,Z)` with capital placeholders."""
    for path in ("themis/runtime/scheduler.py",
                 "themis/runtime/missing_data.py"):
        source = (ROOT / path).read_text(encoding="utf-8")
        for gone in ('"conditional P(Y|X,Z)"', '"covariate P(Z)"',
                     '"conditional P(Y|X)"'):
            assert gone not in source, (path, gone)


# --------------------------------------------------- the counterexamples

#: Each shape this cut replaced, with a fragment of the error it has to
#: raise. The fragment is what keeps the check honest: two of these are
#: rejected by the same ``oneOf`` and would read alike, so what is asserted
#: is that the validator names THAT value — a counterexample rejected for
#: somebody else's reason proves nothing about its own.
@pytest.mark.parametrize("block,names", [
    pytest.param(
        _selection_block(failure_reason="没找到可用的选择-后门调整集 Z"),
        "没找到可用的选择-后门调整集", id="a_rendered_sentence"),
    pytest.param(
        _selection_block(failure_reason={"token": "no_admissible"}),
        "no_admissible", id="a_statement_with_no_vocabulary"),
    pytest.param(
        {k: v for k, v in _selection_block().items()
         if k != "complete_criterion"},
        "'complete_criterion' is a required property", id="no_such_fact"),
    pytest.param(
        _selection_block(external_data_needed=["unbiased P(z)"]),
        "'unbiased P(z)' is not of type 'object'", id="the_role_glued_on"),
])
def test_the_contract_says_no_to_the_shapes_this_replaced(block, names):
    import jsonschema

    with pytest.raises(jsonschema.ValidationError) as raised:
        _validator().validate(_envelope(block))
    assert names in raised.value.message, raised.value.message


# ------------------------------- and the sets a reader has to hold at all

def test_every_vocabulary_this_build_declares_is_known_after_importing_it():
    """A reader can only state a set some import has registered.

    :data:`themis.language.VOCABULARIES` fills when a producer's class body
    runs, so which sentences a reader could say used to depend on which
    producers somebody happened to import — eight of the twenty below were
    unknown after a bare ``import themis``, and there the reader falls back
    to handing over the token. Which sets can reach a reader is not a
    per-call question and the list was already kept, so importing the
    package answers it.
    """
    import themis  # noqa: F401
    declared = set()
    for path in ROOT.joinpath("themis").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "language.Word, vocabulary=" in line:
                declared.add(line.split('vocabulary="')[1].split('"')[0])
    # The denominator, so a registry that answered nothing would not pass
    # as a registry that answered everything.
    assert len(declared) >= 20, sorted(declared)
    assert declared <= set(language.VOCABULARIES), sorted(
        declared - set(language.VOCABULARIES))


def test_the_package_and_not_an_accident_is_what_registers_them():
    """The counterexample to the test above, held where it can be seen.

    Most of these sets were reachable because the reader imported their
    module for some other reason. This one is not: nothing ``themis``
    imports at the top level reaches ``data_gap_report``, and its
    vocabulary is registered all the same.
    """
    import themis  # noqa: F401

    tree = ast.parse((ROOT / "themis/__init__.py").read_text(encoding="utf-8"))
    reached = {node.module for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module}
    assert not any("data_gap_report" in name for name in reached), reached
    assert "measurement_note" in language.VOCABULARIES
