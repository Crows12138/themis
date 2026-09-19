"""What an answer calls the steps of its chain.

A step's name exists to be pointed at. A later step says "the criterion is
that one"; a gap says "that step is what raised me". A name that exists to
be pointed at has to be checkable by whoever follows the pointer, and the
reader of an answer holds no second record of what its producer liked to
call things — so for a long time the slot took anything. Measured on the
corpus: forging the first step's name left 81 of 178 chains accepted at
every public door, every one of them a chain where nothing else happened
to point at that step, because the only two things ever asked of a name
were that two steps did not share it and that a reference landed
somewhere.

What a reader CAN recompute is where a step sits, and that is what the
name is: :func:`themis.types.step_name` of its place, written by the
encoder and by nobody else. This module is the other half. It reads the
answer, recomputes every name from the chain the answer carries, and
refuses any other — which is the whole of what makes a forged one
refusable, since there is nothing else about a name to be wrong.

Producers keep a private label instead, and a label stops at the
serialization boundary. That is the same claim from the producing side:
nothing downstream has to go on agreeing with a string somebody chose.
"""
from __future__ import annotations

from typing import Iterator

from ..types import step_name
from .errors import StepRefError, VerificationError

_RULE = "step_names"


def _references(node: object) -> Iterator[object]:
    """Every step this node points at, however deeply it is buried."""
    if isinstance(node, dict):
        if node.get("kind") == "step_ref":
            yield node.get("step_id")
            return
        for value in node.values():
            yield from _references(value)
    elif isinstance(node, list):
        for value in node:
            yield from _references(value)


def verify_the_chain_names_its_steps(result: dict) -> None:
    """Every step of this answer's chain is named by where it sits.

    Asked of answers that carry a chain and silent about those that do
    not: an answer whose whole content is a gap diagnosis took no route,
    and there is nothing here to be wrong about.
    """
    payload = result.get("derivation")
    if not isinstance(payload, dict):
        return
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return

    names = [step_name(index) for index in range(len(steps))]
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        given = step.get("step_id")
        if given != names[index]:
            raise VerificationError(
                f"derivation.steps[{index}] calls itself {given!r}; a step "
                f"of an answer is named by the place it sits, so the name "
                f"there is {names[index]!r}",
                step_index=index, rule=_RULE,
            )

    known = set(names)
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        for target in _references(step):
            if target in known:
                continue
            raise StepRefError(
                f"derivation.steps[{index}] points at {target!r}, which is "
                f"no step of this chain; its {len(steps)} steps are named "
                f"{names[0]!r} through {names[-1]!r}",
                step_index=index, rule=_RULE,
            )
