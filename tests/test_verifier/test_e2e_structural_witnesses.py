"""What the kernel actually emits must pass the kernel's own verifier.

``test_positive_rules`` builds a witness and its rendered ``supporting_paths``
from one tuple in one order, so the two agree by construction — which is
precisely the disagreement that can exist in the real thing. The runtime sorts
``supporting_paths`` for a canonical render (an order that must not depend on
which query kind asked) but leaves ``inputs.paths`` in traversal order, and
``cause_via_directed_path`` rebuilt the expected labels from a third order and
demanded positional equality. Every cause query over a graph with more than one
directed path — a mediator alongside a direct edge, the commonest shape there
is — produced a ``structurally_solved`` answer its own verifier rejected. Its
open-path twin had been repaired for the same reason and left this one alone,
and nothing put the same question to both.

So the input here is hand-written and nothing else is: the graph is a fixture,
the result and the derivation come from ``themis.run``, and ``themis.verify``
is asked to accept them.
"""
from __future__ import annotations

import pytest

import themis


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _edges(*pairs: tuple[str, str]) -> list[dict]:
    return [{"kind": "cause", "from": _atom(a), "to": _atom(b)} for a, b in pairs]


def _vars(*names: str) -> list[dict]:
    return [{"kind": "variable", "predicate": n, "domain": [True, False]}
            for n in names]


SHAPES = {
    "chain": (_vars("X", "M", "Y"), _edges(("X", "M"), ("M", "Y"))),
    "mediator_and_direct_edge": (
        _vars("X", "M", "Y"), _edges(("X", "M"), ("M", "Y"), ("X", "Y"))),
    "two_disjoint_mediators": (
        _vars("X", "M", "N", "Y"),
        _edges(("X", "M"), ("M", "Y"), ("X", "N"), ("N", "Y"))),
    "three_routes": (
        _vars("X", "A", "B", "Y"),
        _edges(("X", "A"), ("A", "Y"), ("X", "B"), ("B", "Y"), ("X", "Y"))),
    "fork": (_vars("X", "Y", "Z"), _edges(("Z", "X"), ("Z", "Y"))),
    "collider": (_vars("X", "Y", "C"), _edges(("X", "C"), ("Y", "C"))),
    "disconnected": (_vars("X", "Y"), []),
}

QUERIES = {
    "cause": {"kind": "cause", "from": _atom("X"), "to": _atom("Y")},
    "assoc": {"kind": "assoc", "left": _atom("X"), "right": _atom("Y"),
              "given": []},
}

CASES = [(shape, kind) for shape in SHAPES for kind in QUERIES]


def _run(shape: str, kind: str):
    variables, edges = SHAPES[shape]
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [*variables, *edges,
                       {"kind": "query", "id": "q", "query": QUERIES[kind]}],
    }
    return program, themis.run(program)["results"][0]


@pytest.mark.parametrize("shape,kind", CASES, ids=[f"{s}-{k}" for s, k in CASES])
def test_the_verifier_accepts_what_the_runtime_produced(shape, kind):
    program, result = _run(shape, kind)
    themis.verify(program, result)


def test_the_battery_reaches_the_multi_witness_branch():
    """A sweep that only ever proves ``value=False`` never touches the rule
    this module exists for, and is green either way."""
    multi = 0
    for shape, kind in CASES:
        _, result = _run(shape, kind)
        paths = (result.get("structural_result") or {}).get("supporting_paths") or []
        if len(paths) > 1:
            multi += 1
    assert multi >= 6, f"只有 {multi} 个用例给出了不止一条见证路径"
