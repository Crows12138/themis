"""A structural verdict, against what the same answer already committed.

``structural_result.value`` is one slot carrying ten propositions, and
which one is the question's to say (:mod:`themis.questions`). That is why
auditing it belonged to the route verifiers: only a verifier that knows
which proposition was claimed can re-derive it. But a route is chosen by
the answer's status word and the last rule of its chain, and neither of
those is the question.

Where the verdict IS the answer -- ``cause``, ``assoc``, ``identify`` --
the route always lands somewhere that re-derives it, because that verdict
is what the route exists to produce. Where the verdict is a precondition
for the answer, the route lands wherever the run got to. An effect query
that stopped at ``identify_via_mediation`` reaches
``verify_effect_structural``, which holds the verdict by equating it with
``derivation[-1].output``; the same query with data attached runs three
more steps and reaches ``verify_numeric``, which has no reason to look at
a premise it does not use. So whether a premise is checked depends on how
far the run got past it, which is a fact about the data that happened to
be there.

Measured on the stored answers: of 125 carrying a verdict, thirteen could
be flipped and every door still accepted them. Eleven said the estimand
was identifiable and could be made to say it was not while the number
they report sat untouched beside the denial; two said it was not and
could be made to say it was while their own gap report went on giving the
reason identification had failed. Eight of the thirteen carry the
identifying step that concluded the verdict -- it had simply stopped
being the last one.

The repair is not to widen the structural door, which would make it
accept chains it is not written to read, nor to add the check to each
numeric rule, which is thirty-odd copies and a hole again at the next
estimator. A premise is not held by the route that produced it. It is
held by everything else in the answer that could only be true if it
holds, and that reading needs no route at all.

Three things commit an answer to identification, and each refuses a flip
the others miss:

- the step that concluded it. An ``identify_via_*`` step's output IS a
  verdict, so an answer whose verdict differs from it contradicts its own
  chain. Read wherever the step sits, which is the whole difference: the
  structural door reads the same output and reads it only at the end.
- a gap saying identification failed. ``GapKind`` has one kind for that
  and it covers ten distinct needs, so this is the declared name rather
  than a list of the ways a reason can be spelt.
- a point estimate. Identification is what putting a number on an
  estimand requires, so a verdict denying it is denied by the number.

The last two are about whether a quantity can be got, so they apply to
the questions that ask for one -- :attr:`themis.questions.Question.
names_an_estimand`, the eight whose verdict is that one proposition. The
two that name none are asking about the shape of a graph, where neither a
gap about admissible sets nor a point estimate is a fact about the
answer, and inventing a reading for them here is exactly what declaring
the field made unnecessary.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..gaps import GapKind
from ..questions import BY_KIND
from ..types import Shown
from .errors import VerificationError
# The same reading of "is a point sitting here" the status word is held
# against, not a second one: what counts as a point is a fact about the
# envelope, and two readings of it would be two answers to one question.
from .status_rules import _shown

_RULE = "structural_verdict_check"

#: The gap kind that says identification found nothing to identify with.
#: Read from the declared vocabulary rather than spelt, because the ten
#: needs that raise it spell their reasons ten ways and the kind is the
#: one thing they agree on.
_IDENTIFICATION_FAILED = str(GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET)


def _the_steps_that_identified(result: Mapping) -> list[Mapping]:
    """Every step of the chain whose job was to reach the verdict."""
    derivation = result.get("derivation")
    steps = derivation.get("steps") if isinstance(derivation, Mapping) else None
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        return []
    return [step for step in steps
            if isinstance(step, Mapping)
            and str(step.get("rule", "")).startswith("identify_via_")]


def _its_gaps_say_identification_failed(result: Mapping) -> bool:
    """Whether the answer's own gap report gives a reason it failed."""
    gaps = result.get("missing_information")
    if not isinstance(gaps, Sequence) or isinstance(gaps, (str, bytes)):
        return False
    return any(isinstance(gap, Mapping)
               and gap.get("gap") == _IDENTIFICATION_FAILED
               for gap in gaps)


def verify_structural_verdict(result: Mapping) -> None:
    """Hold a structural verdict to what the rest of the answer commits.

    Outside the query-kind dispatch, for the reason the module says: the
    dispatch is chosen by how far the run got, and a premise whose audit
    depends on that is audited on some runs and not others.

    Nothing here is re-derived. Each witness is a second place the same
    answer commits to identification, so what this rule catches is an
    answer contradicting itself -- which is wrong on its own terms and
    needs neither the graph nor the data to see.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    verdict = result.get("structural_result")
    if not isinstance(verdict, Mapping):
        return
    value = verdict.get("value")
    if not isinstance(value, bool):
        return

    for step in _the_steps_that_identified(result):
        output = step.get("output")
        if not isinstance(output, Mapping) or "value" not in output:
            # What a step's output has to look like is that step's own
            # audit; this rule is about the verdict and says nothing
            # about a chain it cannot read.
            continue
        if output["value"] != value:
            raise VerificationError(
                f"the answer's verdict is {value!r} and {step.get('rule')!r}, "
                f"the step that reached it, concluded {output['value']!r}; a "
                f"verdict is what its derivation arrived at, and a reader "
                f"shown the other one is shown a conclusion this chain does "
                f"not reach",
                rule=_RULE,
            )

    # A kind this build does not carry is passed over: the schema's enum
    # is where membership is asked, and answering it here would be a
    # second, weaker enum check standing in front of the real one.
    kind = result.get("query_kind")
    if not isinstance(kind, str) or (question := BY_KIND.get(kind)) is None:
        return
    if not question.names_an_estimand:
        return

    if value is True and _its_gaps_say_identification_failed(result):
        raise VerificationError(
            "the answer's verdict says the estimand is identifiable and its "
            "own gap report says identification found no admissible set; a "
            "reader is shown one line saying the quantity can be got and "
            "another saying it cannot, and the gap is the half that comes "
            "with a reason",
            rule=_RULE,
        )
    if value is False and Shown.POINT in _shown(result):
        raise VerificationError(
            "the answer's verdict says the estimand is not identifiable and "
            "a point estimate for it is sitting beside the verdict; "
            "identification is what putting a number on an estimand "
            "requires, so a reader is told the run could not reach the "
            "quantity it is being shown",
            rule=_RULE,
        )
