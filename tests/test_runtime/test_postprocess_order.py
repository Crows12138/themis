"""The order the post-processing passes run in is derived, not written.

Each pass declares the blocks it needs finished and the blocks it may
change; the order falls out of those declarations. That only means
something if the declarations are complete, so the corpus test here does
not check that the computed order is some particular list — it checks that
*every* order the declarations permit gives the same answer. An undeclared
read is a pass that works in one arrangement and not another, which is
exactly what a run in a different valid order exposes and what reading the
table cannot.

The control below forces an order the declarations forbid and shows the
answer changes. Without it these tests would pass just as well on a table
whose edges meant nothing.
"""
from __future__ import annotations

import json
import random

import pytest

import themis
from themis.runtime import postprocess, scheduler


# ---------------------------------------------------------------------------
# Programs that between them touch every block in the table
# ---------------------------------------------------------------------------


def _a(pred: str, obj: str = "me") -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": obj}]}


def _binary(*names: str) -> list[dict]:
    return [
        {"kind": "variable", "predicate": n, "domain": [True, False]}
        for n in names
    ]


def _effect(target: str = "y", treatment: str = "x") -> dict:
    return {
        "kind": "query", "id": "q", "query": {
            "kind": "effect",
            "target": {"atom": _a(target), "value": True},
            "intervention": {"atom": _a(treatment), "value": True},
            "given": [],
        },
    }


def _bounded_by_an_instrument() -> dict:
    """Latent confounding kills point identification; a binary instrument
    and theta for the joint give Balke-Pearl something to compute. Fires
    bounds, the report's bounds classification, the alt-path revision and
    the must-disclose caveat — the four passes whose order is contested."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("z", "x", "y") + [
            {"kind": "cause", "from": _a("z"), "to": _a("x")},
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "bidirected", "left": _a("x"), "right": _a("y")},
            _effect(),
        ],
    }


def _not_transportable() -> dict:
    """A selection node on the outcome: no point, no interval, and a
    refusal the report has to render."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "selection_node", "id": "s_y",
             "source_population": "trial",
             "target_population": "real_world",
             "affects": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target_population": "real_world",
                "target": {"atom": _a("y"), "value": True},
                "intervention": {"atom": _a("x"), "value": True},
                "given": [],
            }},
        ],
    }


def _framed_badly_with_an_ambiguity() -> dict:
    """Under-specified variables plus a declared ambiguity: framing,
    investigation and the ambiguity echo all write, and the report reads
    all three."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {"ambiguities": [
            {"kind": "mediator_choice",
             "note": "两个候选中介，未定"},
        ]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            _effect(),
        ],
    }


def _answerable_from_low_confidence_edges() -> dict:
    """A back-door answer whose edge is flagged low-confidence — the
    confidence trail and the caveat it raises both have to be present."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("c", "x", "y") + [
            {"kind": "cause", "from": _a("c"), "to": _a("x")},
            {"kind": "cause", "from": _a("c"), "to": _a("y")},
            {"kind": "cause", "from": _a("x"), "to": _a("y"),
             "annotations": {"confidence": 0.2, "source": "一篇综述"}},
            _effect(),
        ],
    }


def _sample_restricted_on_a_collider() -> dict:
    """X→Y, X→W, Y→M, M→W, and the sample restricted on W. Only program
    shape that reaches the selection-recovery verdict."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y", "m", "w") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "cause", "from": _a("x"), "to": _a("w")},
            {"kind": "cause", "from": _a("y"), "to": _a("m")},
            {"kind": "cause", "from": _a("m"), "to": _a("w")},
            {"kind": "observation", "atom": _a("w"), "value": True},
            _effect(),
        ],
    }


def _outcome_sometimes_missing() -> dict:
    """A missingness indicator on the outcome, which is the only thing
    that reaches the Mohan-Pearl-Tian verdict."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("c", "x", "y") + [
            {"kind": "cause", "from": _a("c"), "to": _a("x")},
            {"kind": "cause", "from": _a("c"), "to": _a("y")},
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "missingness_indicator", "id": "R_y",
             "missing_var": _a("y"), "caused_by": [_a("c")]},
            _effect(),
        ],
    }


CORPUS = {
    "bounded_by_an_instrument": _bounded_by_an_instrument(),
    "not_transportable": _not_transportable(),
    "framed_badly_with_an_ambiguity": _framed_badly_with_an_ambiguity(),
    "low_confidence_edges": _answerable_from_low_confidence_edges(),
    "sample_restricted_on_a_collider": _sample_restricted_on_a_collider(),
    "outcome_sometimes_missing": _outcome_sometimes_missing(),
}


def _answer(program: dict) -> str:
    """The whole result, as the caller sees it."""
    return json.dumps(themis.run(program)["results"][0], sort_keys=True,
                      ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# The declarations decide the order
# ---------------------------------------------------------------------------


def test_every_writer_runs_before_every_pass_that_reads_it():
    """Derived from the table rather than compared against a list, so a
    pass added tomorrow is covered without editing this test."""
    deps = postprocess.dependencies(scheduler.POST_PASSES)
    position = {p.name: i for i, p in enumerate(scheduler.POST_PASSES)}
    for name, required in deps.items():
        for earlier in required:
            assert position[earlier] < position[name], (
                f"{name} runs before {earlier}, which it depends on"
            )


def test_a_pass_with_no_dependencies_keeps_its_declared_place():
    """The tie-break is declaration order, so the sequence is reviewable
    against the table as written instead of being an artifact of how the
    sort happened to walk the graph."""
    passes = tuple(
        postprocess.Pass(
            name=n, run=lambda r, i: r,
            reads=frozenset(), writes=frozenset({w}),
        )
        for n, w in (
            ("third", "explanation"),
            ("first", "confidence"),
            ("second", "formula"),
        )
    )
    assert [p.name for p in postprocess.order(passes)] == [
        "third", "first", "second",
    ]


def test_the_report_is_revised_before_anything_reads_it():
    """``structural_caveats`` reads the gap report; ``reconcile_alt_paths``
    rewrites it. The revision has to land first or the explanation would
    quote a version of the report that never reaches the caller. This is
    the one place the computed order differs from the hand-written chain
    it replaced — the caveat pass used to be a tail call inside the pass
    that builds the report, so it ran before the revision by construction.
    """
    order = [p.name for p in scheduler.POST_PASSES]
    assert order.index("data_gap_report") < order.index("reconcile_alt_paths")
    assert order.index("reconcile_alt_paths") < order.index("structural_caveats")


# ---------------------------------------------------------------------------
# The declarations are complete — checked by running, not by reading
# ---------------------------------------------------------------------------


def _random_valid_orders(passes, seed: int, count: int):
    """Sample orders the declared dependencies permit."""
    deps = postprocess.dependencies(passes)
    by_name = {p.name: p for p in passes}
    rng = random.Random(seed)
    for _ in range(count):
        done: set[str] = set()
        remaining = set(deps)
        sequence = []
        while remaining:
            ready = sorted(n for n in remaining if deps[n] <= done)
            picked = rng.choice(ready)
            sequence.append(by_name[picked])
            done.add(picked)
            remaining.discard(picked)
        yield tuple(sequence)


@pytest.mark.parametrize("case", sorted(CORPUS))
def test_any_valid_order_gives_the_same_answer(case, monkeypatch):
    """If a pass reads a block it did not declare, some permitted order
    runs it before the writer and the answer moves. Twenty samples per
    program, from a fixed seed, so a failure is reproducible."""
    program = CORPUS[case]
    expected = _answer(program)
    for candidate in _random_valid_orders(scheduler.POST_PASSES, seed=7,
                                          count=20):
        monkeypatch.setattr(scheduler, "POST_PASSES", candidate)
        assert _answer(program) == expected, (
            f"order {[p.name for p in candidate]} answers differently"
        )


def test_every_pass_changes_the_result_for_some_program(monkeypatch):
    """A pass that never fires on the corpus has its declarations checked
    by nothing: reordering a no-op cannot move the answer. Two of these
    were no-ops when the corpus was first written, which is why this is a
    guard and not a note — a pass added tomorrow needs a program that
    reaches it, or the order test covers nine of ten."""
    fired: set[str] = set()

    def watched(original):
        def run(result, inputs):
            after = original.run(result, inputs)
            if after != result:
                fired.add(original.name)
            return after
        return postprocess.Pass(
            name=original.name, run=run,
            reads=original.reads, writes=original.writes,
        )

    monkeypatch.setattr(scheduler, "POST_PASSES", tuple(
        watched(p) for p in scheduler.POST_PASSES
    ))
    for program in CORPUS.values():
        _answer(program)

    idle = sorted({p.name for p in scheduler.POST_PASSES} - fired)
    assert not idle, f"no corpus program reaches {idle}"


def test_running_a_reader_before_its_writer_does_change_the_answer(monkeypatch):
    """The control. Force the caveat pass ahead of the pass that builds
    the report — an order the declarations forbid — and the ⚠ lines that
    make bounds-not-a-point visible to the renderer disappear. Without
    this, the test above would pass on a table whose edges meant nothing.
    """
    program = CORPUS["bounded_by_an_instrument"]
    honest = json.loads(_answer(program))
    assert "⚠" in (honest.get("explanation") or ""), (
        "the control program stopped raising caveats — pick another"
    )

    by_name = {p.name: p for p in scheduler.POST_PASSES}
    forced = (by_name["structural_caveats"],) + tuple(
        p for p in scheduler.POST_PASSES if p.name != "structural_caveats"
    )
    monkeypatch.setattr(scheduler, "POST_PASSES", forced)
    early = json.loads(_answer(program))
    assert "⚠" not in (early.get("explanation") or "")


def test_running_framing_before_investigation_loses_every_other_action(
    monkeypatch,
):
    """The second control, and the one the table exists for. Framing adds
    its request to whatever investigation raised; run it first and
    investigation finds a non-empty tuple, concludes the dispatcher
    produced it, and stands down — so every action the refusal's missing
    items would have raised is gone, and what is left reads like a
    complete list."""
    program = CORPUS["bounded_by_an_instrument"]
    honest = json.loads(_answer(program))
    actions = {r["action"] for r in honest["investigation_requests"]}
    assert actions > {"define_variable"}, (
        "the control program stopped raising non-framing actions"
    )

    by_name = {p.name: p for p in scheduler.POST_PASSES}
    forced = (by_name["framing"],) + tuple(
        p for p in scheduler.POST_PASSES if p.name != "framing"
    )
    monkeypatch.setattr(scheduler, "POST_PASSES", forced)
    lost = json.loads(_answer(program))
    assert {r["action"] for r in lost["investigation_requests"]} == {
        "define_variable",
    }


# ---------------------------------------------------------------------------
# What the table refuses at import
# ---------------------------------------------------------------------------


def _pass(name: str, reads: set[str], writes: set[str]) -> postprocess.Pass:
    return postprocess.Pass(
        name=name, run=lambda r, i: r,
        reads=frozenset(reads), writes=frozenset(writes),
    )


def test_a_block_may_not_have_two_producers():
    with pytest.raises(ValueError, match="both produce"):
        postprocess.order((
            _pass("one", set(), {"explanation"}),
            _pass("two", set(), {"explanation"}),
        ))


def test_a_block_may_not_be_revised_twice():
    """Two passes each needing the block and handing it back changed: the
    order between them would come from declaration order, which is what
    the table replaces."""
    with pytest.raises(ValueError, match="both revise"):
        postprocess.order((
            _pass("producer", set(), {"explanation"}),
            _pass("one", {"explanation"}, {"explanation"}),
            _pass("two", {"explanation"}, {"explanation"}),
        ))


def test_a_revision_needs_something_to_revise():
    with pytest.raises(ValueError, match="which no pass produces"):
        postprocess.order((
            _pass("reviser", {"explanation"}, {"explanation"}),
        ))


def test_passes_that_each_need_the_other_are_refused():
    with pytest.raises(ValueError, match="cannot be ordered"):
        postprocess.order((
            _pass("one", {"confidence"}, {"explanation"}),
            _pass("two", {"explanation"}, {"confidence"}),
        ))


def test_a_block_has_to_be_a_field_something_could_hold():
    with pytest.raises(ValueError, match="not a field of QueryResult"):
        postprocess.order((_pass("typo", {"bounds_reslut"}, {"explanation"}),))


def test_the_extensions_map_is_named_by_key():
    """Naming the whole map would put an edge between every pair of passes
    that write a key, which is an ordering that means nothing."""
    with pytest.raises(ValueError, match="name the keys"):
        postprocess.order((
            _pass("whole_map", {"extensions"}, {"explanation"}),
        ))
    postprocess.order((
        _pass("one_key", {"extensions.iv_identification"}, {"explanation"}),
    ))


def test_a_pass_that_leaves_no_block_is_not_a_pass():
    with pytest.raises(ValueError, match="writes nothing"):
        postprocess.order((_pass("observer", {"confidence"}, set()),))
