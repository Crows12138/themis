"""A "not recoverable" verdict is a claim about the sets that were searched.

Both §S9 recovery routes enumerate candidate sets by size and stop at a
bound. "No admissible Z exists" is therefore never what either one proved:
what it proved is "none of size ≤ k". The bound was a bare ``4`` in four
places — a default on each of the two producers and a matching literal on
each of the two verifiers — and nothing required the four to agree. The
verifier is supposed to be a second, independent derivation of the
producer's claim; with its own copy of the constant it re-derived a claim
that merely shared a number with the one on the block. Had the producer
ever searched wider, the verifier would have confirmed a false negative
instead of catching it, which is the one direction that matters.

``search_budget`` gives the quantifier a slot: the producer records the
range it actually searched, the verifiers re-search to the recorded range,
and both reader faces say the number out loud. The tests below hold each
of those, and the two behavioural ones are counterexamples: the same block
verified against two different recorded ranges gets two different verdicts,
which a verifier holding its own constant could not produce.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
from types import SimpleNamespace

import networkx as nx
import pytest

import themis
from themis import blocks, language
from themis.output.analysis_report import _render_route
from themis.runtime.missing_data import (
    analyze_missing_data,
    analyze_missing_data_estimand,
)
from themis.runtime.scheduler import (
    _serialize_missing_data_recovery,
    _serialize_selection_recovery,
)
from themis.runtime.selection_recovery import recover_conditional, recover_effect
from themis.types import Atom, ConstTerm, MissingnessIndicator, ObservationStatement
from themis.verifier import verify_missing_data_recovery, verify_selection_recovery
from themis.verifier.errors import VerificationError

_ROOT = pathlib.Path(themis.__file__).resolve().parent


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


def _graph(edges) -> nx.DiGraph:
    g = nx.DiGraph()
    for u, v in edges:
        g.add_edge(A(u), A(v))
    return g


def _mi(var: str, caused_by=()) -> MissingnessIndicator:
    return MissingnessIndicator(
        id=f"R_{var}",
        missing_var=A(var),
        caused_by=tuple(A(c) for c in caused_by),
    )


def _query(x="x", y="y", given=()):
    return SimpleNamespace(
        intervention=SimpleNamespace(atom=A(x)),
        target=SimpleNamespace(atom=A(y)),
        given=tuple(SimpleNamespace(atom=A(g)) for g in given),
    )


#: The atom every selection example below restricts the sample on.
_RESTRICTED_ON_S = (ObservationStatement(atom=A("s"), value=True),)


# Two common causes of Y and the selection node. Blocking one leaves the
# other path open, so no single Z d-separates S from Y given X and the
# smallest that does has size 2 — the graph is built so that the answer
# CHANGES between budget 1 and budget 2, which is what makes "whose bound
# was used" observable at all.
_TWO_PATHS_TO_S = [
    ("x", "y"), ("a", "y"), ("a", "s"), ("b", "y"), ("b", "s"),
]

# Two confounders of X and Y, selection on a child of X. Condition (1) of
# the selection-backdoor criterion holds at Z=∅; condition (2) needs both
# confounders, so again size 1 fails and size 2 succeeds.
_TWO_CONFOUNDERS = [
    ("z1", "x"), ("z1", "y"), ("z2", "x"), ("z2", "y"),
    ("x", "y"), ("x", "s"),
]


# =================================================== the producer records it


@pytest.mark.parametrize("budget", [0, 1, 2, 5])
def test_the_selection_producer_records_the_range_it_searched(budget):
    g = _graph(_TWO_PATHS_TO_S)
    for produce in (recover_conditional, recover_effect):
        rec = produce(g, A("x"), A("y"), (A("s"),), max_size=budget)
        assert rec.search_budget == budget


@pytest.mark.parametrize("budget", [0, 1, 3])
def test_the_missing_data_producer_records_the_range_it_searched(budget):
    g = _graph([("x", "y")])
    rec = analyze_missing_data(
        g, [_mi("y", caused_by=("x",))], [A("y")], [A("x")], max_cond=budget)
    assert rec.search_budget == budget
    est = analyze_missing_data_estimand(
        g, [_mi("y", caused_by=("x",))], A("y"), A("x"), max_cond=budget)
    assert est.conditional.search_budget == budget


def test_the_range_travels_on_the_block_and_the_schema_demands_it():
    g = _graph(_TWO_CONFOUNDERS)
    rec = recover_effect(g, A("x"), A("y"), (A("s"),), max_size=3)
    assert _serialize_selection_recovery(rec, A("x"), A("y"))["search_budget"] == 3

    md = analyze_missing_data(
        g, [_mi("y", caused_by=("x",))], [A("y")], [A("x")], max_cond=2)
    assert _serialize_missing_data_recovery(md)["search_budget"] == 2

    schema = json.loads(
        (_ROOT / "schemas" / "query_result.schema.json").read_text(encoding="utf-8"))
    ext = schema["properties"]["extensions"]["properties"]
    for name in ("selection_recovery", "missing_data_recovery"):
        assert "search_budget" in ext[name]["required"], name


# ============================================= the verifier re-searches to it


def test_the_conditional_verifier_re_searches_to_the_recorded_range():
    """Same block, two recorded ranges, two verdicts.

    At |Z| ≤ 1 nothing d-separates S from Y given X, so the negative
    verdict stands. At |Z| ≤ 2 the set {a, b} does, so the same negative
    verdict is now refutable — and the verifier must refute it. A verifier
    carrying its own bound would answer both the same way.
    """
    g = _graph(_TWO_PATHS_TO_S)
    narrow = recover_conditional(g, A("x"), A("y"), (A("s"),), max_size=1)
    assert narrow.recoverable is False
    assert recover_conditional(
        g, A("x"), A("y"), (A("s"),), max_size=2).recoverable is True

    block = _serialize_selection_recovery(narrow, A("x"), A("y"))
    verify_selection_recovery(block, g, _RESTRICTED_ON_S, _query())  # truthful at the range it names

    wider = copy.deepcopy(block)
    wider["search_budget"] = 2
    with pytest.raises(VerificationError, match="not s-recoverable"):
        verify_selection_recovery(wider, g, _RESTRICTED_ON_S, _query())


def test_the_effect_verifier_re_searches_to_the_recorded_range():
    """The selection-backdoor twin: {z1, z2} is admissible, neither alone is."""
    g = _graph(_TWO_CONFOUNDERS)
    narrow = recover_effect(g, A("x"), A("y"), (A("s"),), max_size=1)
    assert narrow.recoverable is False
    assert recover_effect(
        g, A("x"), A("y"), (A("s"),), max_size=2).recoverable is True

    block = _serialize_selection_recovery(narrow, A("x"), A("y"))
    verify_selection_recovery(block, g, _RESTRICTED_ON_S, _query())

    wider = copy.deepcopy(block)
    wider["search_budget"] = 2
    with pytest.raises(VerificationError, match="not SBD-recoverable"):
        verify_selection_recovery(wider, g, _RESTRICTED_ON_S, _query())


def test_the_missing_data_verifier_re_searches_to_the_recorded_range():
    """P(y | x) under MAR needs the factor conditioned on x — one variable.

    Narrowing the recorded range to 0 leaves the verifier no ordering it
    can validate, so the block's positive verdict stops being re-derivable
    and must be reported as such.
    """
    g = _graph([("x", "y")])
    ind = [_mi("y", caused_by=("x",))]
    rec = analyze_missing_data(g, ind, [A("y")], [A("x")], max_cond=1)
    assert rec.recoverable is True

    block = _serialize_missing_data_recovery(rec)
    verify_missing_data_recovery(block, g, ind, _query())

    narrowed = copy.deepcopy(block)
    narrowed["search_budget"] = 0
    with pytest.raises(VerificationError):
        verify_missing_data_recovery(narrowed, g, ind, _query())


@pytest.mark.parametrize("bad", [None, "4", True, -1, 2.0])
def test_a_recovery_block_that_names_no_range_is_refused(bad):
    """Without the quantifier there is no claim to re-derive, and silently
    substituting one is the defect this field exists to end."""
    g = _graph(_TWO_CONFOUNDERS)
    sel = _serialize_selection_recovery(
        recover_effect(g, A("x"), A("y"), (A("s"),)), A("x"), A("y"))
    ind = [_mi("y", caused_by=("x",))]
    md = _serialize_missing_data_recovery(
        analyze_missing_data(g, ind, [A("y")], [A("x")]))

    for block, run in (
        (sel, lambda b: verify_selection_recovery(b, g, _RESTRICTED_ON_S, _query())),
        (md, lambda b: verify_missing_data_recovery(b, g, ind, _query())),
    ):
        tampered = copy.deepcopy(block)
        if bad is None:
            tampered.pop("search_budget")
        else:
            tampered["search_budget"] = bad
        with pytest.raises(VerificationError, match="search_budget"):
            run(tampered)


def test_neither_verifier_holds_a_search_bound_of_its_own():
    """The gate on the boundary the four literals used to straddle.

    Every integer left in these two functions is a loop floor (0 or 1);
    any bound worth writing down is larger, and writing one here would put
    a second copy of the producer's constant back on the far side of the
    trust boundary — where its agreement with the block would once again be
    arithmetic rather than evidence.
    """
    tree = ast.parse((_ROOT / "verifier" / "verify.py").read_text(encoding="utf-8"))
    for name in ("verify_selection_recovery", "verify_missing_data_recovery"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        offenders = {
            (n.value, n.lineno) for n in ast.walk(fn)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, int) and not isinstance(n.value, bool)
            and n.value > 1
        }
        assert not offenders, f"{name} carries its own bound: {sorted(offenders)}"
        assert 'block.get("search_budget")' in ast.unparse(fn).replace("'", '"')


# ================================================= the reader is told the range


def _result_with(block_name, block):
    return {"query_kind": "effect", "status": "identified",
            "extensions": {block_name: block}}


def test_the_report_states_the_range_on_a_negative_verdict():
    g = _graph(_TWO_CONFOUNDERS)
    rec = recover_effect(g, A("x"), A("y"), (A("s"),), max_size=1)
    block = _serialize_selection_recovery(rec, A("x"), A("y"))
    text = _render_route(
        _result_with(blocks.Block.SELECTION_RECOVERY, block),
        lang=language.DEFAULT)
    assert "最多 1 个变量" in text

    md = _serialize_missing_data_recovery(
        analyze_missing_data(
            _graph([("x", "y")]), [_mi("y", caused_by=("y",))],
            [A("y")], [A("x")], max_cond=2))
    assert md["recoverable"] is False
    text = _render_route(
        _result_with(blocks.Block.MISSING_DATA_RECOVERY, md),
        lang=language.DEFAULT)
    assert "最多 2 个变量" in text


def test_the_report_stays_quiet_about_the_range_on_a_positive_verdict():
    """A verdict that exhibits the set it found is not qualified by a bound."""
    g = _graph(_TWO_CONFOUNDERS)
    rec = recover_effect(g, A("x"), A("y"), (A("s"),), max_size=2)
    assert rec.recoverable is True
    text = _render_route(
        _result_with(blocks.Block.SELECTION_RECOVERY,
                     _serialize_selection_recovery(rec, A("x"), A("y"))),
        lang=language.DEFAULT)
    assert "搜索范围" not in text


def test_the_browser_states_the_range_on_the_same_two_verdicts():
    source = (_ROOT / "web" / "frontend" / "src" / "lib" / "verdict.ts").read_text(
        encoding="utf-8")
    for renderer in ("selection_recovery:", "missing_data_recovery:"):
        start = source.index(f"  {renderer} (b, {{ lang }}) => {{")
        end = source.index("\n  },", start)
        body = source[start:end]
        assert "searchRange(b, lang)" in body, renderer
        assert "not_recoverable" in body.split("searchRange")[0], renderer
