"""What each pass over a finished result needs, and what it leaves behind.

A dispatcher answers the query. The passes here fill in everything the
answer is *read with*: the confidence trail, the bounds that stand in when
no point estimate exists, the gap report. Each reads blocks an earlier
pass wrote, so their order is
load-bearing — run the framing pass before the investigation pass and the
investigation pass finds a non-empty request tuple, concludes someone else
produced it, and stands down, dropping every request its own missing items
would have raised.

That order used to be the order of nine calls in a row with the reasons in
a comment above them. Nothing consults a comment, so a pass inserted in
the wrong place is not an error — it is a quietly different answer, and a
pass reading a block before its writer runs sees whatever the dispatcher
left there, which is usually ``None`` and never says that it is early.

Here the order is computed. A pass declares the blocks it needs finished
and the blocks it may change, and :func:`order` sorts them so every writer
precedes every reader. What cannot be sorted is refused at import: a
cycle, a block two passes produce, a block revised twice with nothing to
say which revision comes first.

**A read is the claim that running before that block's writer would change
your answer.** A producer guarding on its own block already existing —
because a dispatcher may have produced it, and several do — is not reading
another pass's work; declaring it would make the block look like one two
passes revise and none produces.

Blocks are named at the granularity that dependencies exist at. A result
field is one block, except ``extensions``, which is a map whose keys are
unrelated to each other: three passes write three of its keys and none of
them is waiting for the others. Naming the map as a whole would put an
edge between every pair of them and read like an ordering that means
something.

Both halves of that name space are checked, and neither is checked here:
a result field is a field of :class:`~themis.types.QueryResult`, and an
extension key is a block of :mod:`themis.blocks`. Sorting ten passes
correctly is worth nothing if all ten read a key nobody writes.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from graphlib import CycleError, TopologicalSorter
from typing import Any, Callable

from .. import blocks
from ..types import QueryResult

_EXTENSION = "extensions."

_RESULT_BLOCKS: frozenset[str] = frozenset(f.name for f in fields(QueryResult))


@dataclass(frozen=True)
class Inputs:
    """Everything a pass may consult besides the result.

    The program and the query it came from, the graph they were solved on,
    and the indices the numeric layer was given. One object rather than
    seven parameters because the passes need different subsets of it and a
    uniform signature is what lets them live in a table at all.
    """

    program: Any
    stmt: Any
    graph: Any
    theta: Any
    prob_index: Any
    obs_index: Any
    bidirected: Any


@dataclass(frozen=True)
class Pass:
    """One post-processor and the data flow it takes part in.

    ``reads`` and ``writes`` are blocks, not parameters. A block in both is
    a revision: the pass needs what is there and hands it back changed.
    """

    name: str
    run: Callable[[QueryResult, Inputs], QueryResult]
    reads: frozenset[str]
    writes: frozenset[str]


def _check_block(block: str, where: str, pass_name: str) -> None:
    """Reject a block name nothing could ever hold."""
    if block.startswith(_EXTENSION):
        key = block[len(_EXTENSION):]
        if not key or "." in key:
            raise ValueError(
                f"pass {pass_name!r} names {block!r} in {where}; an extension "
                f"block is 'extensions.<key>' for exactly one key"
            )
        if key not in blocks.Block:
            raise ValueError(
                f"pass {pass_name!r} names {block!r} in {where}, which is not "
                f"a registered block; a key nothing writes reads as None "
                f"forever and never says that it is missing, so declare it in "
                f"themis.blocks or fix the spelling"
            )
        return
    if block == "extensions":
        raise ValueError(
            f"pass {pass_name!r} names the whole extensions map in {where}; "
            f"name the keys it depends on — the map's keys are independent, "
            f"and an edge to all of them would order passes that have no "
            f"reason to be ordered"
        )
    if block not in _RESULT_BLOCKS:
        raise ValueError(
            f"pass {pass_name!r} names {block!r} in {where}, which is not a "
            f"field of QueryResult; blocks are result fields, or "
            f"'extensions.<key>' for one key of the extensions map"
        )


def dependencies(passes: tuple[Pass, ...]) -> dict[str, frozenset[str]]:
    """For each pass, the passes that must have run before it.

    Every way of ordering the passes that respects this map produces the
    same result — that is what the declarations claim, and the claim is
    only worth anything if something checks it, so this is exposed rather
    than left inside :func:`order`.
    """
    by_name: dict[str, Pass] = {}
    for p in passes:
        if p.name in by_name:
            raise ValueError(f"duplicate pass name {p.name!r}")
        by_name[p.name] = p
        if not p.writes:
            raise ValueError(
                f"pass {p.name!r} writes nothing; a pass that leaves no block "
                f"behind has no place in a chain whose output is the result"
            )
        for block in p.reads:
            _check_block(block, "reads", p.name)
        for block in p.writes:
            _check_block(block, "writes", p.name)

    producers: dict[str, str] = {}
    revisers: dict[str, str] = {}
    for p in passes:
        for block in p.writes:
            if block in p.reads:
                if block in revisers:
                    raise ValueError(
                        f"passes {revisers[block]!r} and {p.name!r} both "
                        f"revise {block!r}; which revision comes first would "
                        f"be decided by declaration order, which is the thing "
                        f"this table replaces"
                    )
                revisers[block] = p.name
            else:
                if block in producers:
                    raise ValueError(
                        f"passes {producers[block]!r} and {p.name!r} both "
                        f"produce {block!r}; one of them is overwriting the "
                        f"other's work, or it means to revise it and should "
                        f"declare it in reads as well"
                    )
                producers[block] = p.name

    for block, reviser in revisers.items():
        if block not in producers:
            raise ValueError(
                f"pass {reviser!r} revises {block!r}, which no pass produces; "
                f"a pass that needs a block and hands it back changed has to "
                f"have something to change"
            )

    predecessors: dict[str, set[str]] = {p.name: set() for p in passes}
    for block, producer in producers.items():
        for p in passes:
            if p.name != producer and (block in p.reads or block in p.writes):
                predecessors[p.name].add(producer)
    for block, reviser in revisers.items():
        # Everyone who only reads the block reads the revised one. A reader
        # placed between the producer and the reviser would be reading a
        # version no consumer of the result ever sees.
        for p in passes:
            if p.name != reviser and block in p.reads and block not in p.writes:
                predecessors[p.name].add(reviser)

    return {name: frozenset(pred) for name, pred in predecessors.items()}


def order(passes: tuple[Pass, ...]) -> tuple[Pass, ...]:
    """The passes in an order where every writer precedes every reader.

    Ties — passes with no dependency between them — keep the order they
    were declared in, so the sequence is reproducible and reviewable
    against the table as written.
    """
    by_name = {p.name: p for p in passes}
    predecessors = dependencies(passes)

    sorter = TopologicalSorter(predecessors)
    try:
        sorter.prepare()
    except CycleError as exc:
        cycle = " -> ".join(exc.args[1])
        raise ValueError(
            f"the passes cannot be ordered: {cycle}; each needs a block the "
            f"next one writes, so no order satisfies all of them"
        ) from None

    index = {p.name: i for i, p in enumerate(passes)}
    ready: list[str] = []
    ordered: list[Pass] = []
    while sorter.is_active():
        ready.extend(sorter.get_ready())
        ready.sort(key=lambda n: index[n])
        name = ready.pop(0)
        ordered.append(by_name[name])
        sorter.done(name)
    return tuple(ordered)


def run(result: QueryResult, passes: tuple[Pass, ...], inputs: Inputs) -> QueryResult:
    """Thread the result through the passes in the order given."""
    for p in passes:
        result = p.run(result, inputs)
    return result
