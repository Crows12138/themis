"""What each kind of question asks for, and what a verdict about it settles.

``structural_result.value`` is a bare boolean. Which proposition it asserts
depends on what was asked: for a ``cause`` query it says a causal influence
exists, and that is the answer; for an ``effect`` query it says the estimand
is identifiable, which is a precondition for the answer and not the answer.

The kernel has always known the difference. ``verify()`` dispatches on
``query_kind`` to four different verifiers — ``verify_cause``,
``verify_assoc``, ``verify_identify``, ``verify_effect_structural`` — each
re-deriving a *different* proposition from the same boolean, because a
verifier that did not know which proposition was claimed could not check it.
No consumer could read that knowledge: it was a chain of ``if`` statements,
not a table.

So each surface guessed, and each guessed differently. Across one suite run
1397 results reached a reader and 271 were answered with the verdict; 81 of
those had asked for a number (78 ``effect``, 3 ``proximal_effect``). Thirty
-four of the 78 carried a ``formula``, which means the sentence they needed
was already written one branch below the one that answered them — the "可识
别，但当前没有数据" line that fired 352 times for results reaching it. The
verdict branch got there first, because a boolean is always present and
nothing asked whether it was the answer. Twelve more were ``False`` and read
as "结论：否", which is not a weak answer to "how large is the effect" but
not an answer at all. Meanwhile the web special-cased three kinds and
defaulted the other seven to 成立 / 不成立; the report's question line tested
for ``"association"``, a string no query kind has, so an ``assoc`` query —
one of the three whose answer IS the verdict — had its question rendered as
``（查询类型：assoc）``; and the prompt's field table described the boolean as
"true / false for cause / assoc", leaving eight kinds unstated.

:attr:`Question.verdict_is_the_answer` is the fact all of them needed and
none had. It is not "cause and assoc": ``identify`` asks whether the estimand
is identifiable, so the very proposition that is scaffolding for an effect
query is the answer for an identify query. That is why probing field names
cannot recover it — the field is identical in both cases and only the
question tells them apart.

The keys are the closed ``query_kind`` enum of ``query_result.schema.json``,
a *required* property of every result, so a reading is always resolvable and
no default is needed. :func:`bind` refuses a renderer set that does not cover
the vocabulary exactly, which is what removes the 成立 / 不成立 fallback:
that fallback was the shape of "this kind has no reading", and a fallback
cannot be distinguished from coverage by reading the code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeVar

R = TypeVar("R")


@dataclass(frozen=True)
class Question:
    """One kind of question, and how a structural verdict about it reads.

    ``settles`` and ``fails`` are the propositions the boolean stands for,
    not ways of saying yes and no. Rendering the bare value is precisely
    what let one sentence serve ten meanings; a surface that states the
    proposition cannot make that substitution silently.

    Both are written from the verifier that audits this kind, so the
    proposition a reader is told is the proposition the kernel checked.
    """

    kind: str
    asks: str
    settles: str
    fails: str
    verdict_is_the_answer: bool

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.kind


# --- the boolean IS the answer ------------------------------------------------
# Three kinds ask a question about the graph. Nothing in the answer slot
# outranks the verdict for them, and that is why the branch could sit low
# for so long without anyone noticing it also caught the other seven.

CAUSE = Question(
    "cause",
    asks="whether one variable causally influences another",
    settles="a directed path carries influence from the source to the target",
    fails="no directed path carries influence from the source to the target",
    verdict_is_the_answer=True,
)
ASSOC = Question(
    "assoc",
    asks="whether two variables are associated in the graph",
    settles="the two are d-connected given the conditioning set",
    fails="the two are d-separated given the conditioning set",
    verdict_is_the_answer=True,
)
IDENTIFY = Question(
    "identify",
    asks="whether the target effect is non-parametrically identifiable "
         "from observational data",
    settles="the effect is identifiable",
    fails="the effect is not identifiable from this graph",
    verdict_is_the_answer=True,
)

# --- the boolean is a precondition for the answer -----------------------------
# Seven kinds ask for a quantity. Their verdict says the estimand can be
# identified, which is worth stating and is not what was asked. Where it is
# true the number's absence has another cause, and the branches below the
# verdict know which; where it is false, "not identifiable" IS the answer,
# and it is the one sentence a bare 否 cannot carry.

EFFECT = Question(
    "effect",
    asks="how large the causal effect of an intervention is",
    settles="the estimand is identifiable",
    fails="the estimand is not identifiable from this graph",
    verdict_is_the_answer=False,
)
PROBABILITY = Question(
    "probability",
    asks="the probability of an event under the model",
    settles="the probability is identifiable",
    fails="the probability is not identifiable from this graph",
    verdict_is_the_answer=False,
)
COUNTERFACTUAL = Question(
    "counterfactual",
    asks="the value of one cell of the counterfactual joint distribution",
    settles="the cell is identifiable, as a point or as bounds",
    fails="the cell is not identifiable from this graph",
    verdict_is_the_answer=False,
)
CAUSATION = Question(
    "causation",
    asks="the probabilities of necessity and sufficiency for an outcome",
    settles="the probabilities of causation are identifiable",
    fails="the probabilities of causation are not identifiable",
    verdict_is_the_answer=False,
)
SCM_COUNTERFACTUAL = Question(
    "scm_counterfactual",
    asks="one unit's counterfactual outcome under a linear structural model",
    settles="abduction-action-prediction determines the unit's value",
    fails="the unit's counterfactual value is not determined",
    verdict_is_the_answer=False,
)
COUNTERFACTUAL_CONJUNCTION = Question(
    "counterfactual_conjunction",
    asks="the probability of several counterfactual events holding together",
    settles="the ID* / IDC* algorithm identifies the conjunction",
    fails="the ID* / IDC* algorithm returns a hedge — not identifiable",
    verdict_is_the_answer=False,
)
PROXIMAL_EFFECT = Question(
    "proximal_effect",
    asks="the effect recovered through proxies for an unmeasured confounder",
    settles="the proximal criterion holds, so the effect is identifiable",
    fails="the proximal criterion does not hold",
    verdict_is_the_answer=False,
)

DECLARED: tuple[Question, ...] = (
    CAUSE,
    ASSOC,
    IDENTIFY,
    EFFECT,
    PROBABILITY,
    COUNTERFACTUAL,
    CAUSATION,
    SCM_COUNTERFACTUAL,
    COUNTERFACTUAL_CONJUNCTION,
    PROXIMAL_EFFECT,
)
BY_KIND: dict[str, Question] = {q.kind: q for q in DECLARED}


class UnknownQueryKind(KeyError):
    """A result names a query kind no reading has been declared for.

    Reachable only past the schema, whose ``query_kind`` enum this module
    covers exactly and which requires the field on every result. Raised
    rather than defaulted: the default is what this module removes, and a
    default here would restore it under a new name.
    """


def reading_of(kind: str | None) -> Question:
    """How to read a structural verdict on a result of this query kind."""
    try:
        return BY_KIND[kind]
    except KeyError:
        raise UnknownQueryKind(
            f"no reading declared for query_kind {kind!r}; add it to "
            f"themis.questions beside the verifier that audits it"
        ) from None


def bind(readings: Mapping[Question, R]) -> dict[Question, R]:
    """One surface's readings, checked against the vocabulary both ways.

    An unbound kind is a question this surface answers by falling back —
    the 成立 / 不成立 shape. A bound kind outside the vocabulary is a
    reading no result can reach.
    """
    missing = sorted(q.kind for q in DECLARED if q not in readings)
    if missing:
        raise ValueError(
            f"no reading for query kind {missing}; a result of that kind "
            f"would reach this surface and be answered by a fallback"
        )
    extra = sorted(str(q) for q in readings if q not in DECLARED)
    if extra:
        raise ValueError(
            f"reading bound for {extra}, which is not a declared query "
            f"kind (themis.questions.DECLARED)"
        )
    return dict(readings)
