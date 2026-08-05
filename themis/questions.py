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

:attr:`Question.names_an_estimand` and :attr:`Question.interval_fallback` are
the same repair applied to the data-gap report, which answered both from one
hand-written three-element set of query kinds. The set decided (a) whether
``answer_tier`` — point / interval / none — means anything for a result, and
(b) whether an interval is a genuine fallback when a distribution the answer
needs is missing. Those are different questions; they agree on the three
kinds named and diverge on the seven that fell to the ``else``. One suite run
measured the divergence: the ``else`` branch fired 226 times and 222 of them
were ``causation``, told that its quantity is "点可估的，没有 bounds 替代路径"
— a sentence written for ``probability`` and false of probabilities of
causation, whose answer is a Tian-Pearl interval whenever monotonicity is not
declared. The tier gate suppressed itself on the same seven while the
estimation layer, which consults no such set, wrote a tier for them anyway:
one causation query reached a reader with ``answer_tier`` absent through
``themis.run`` and present through ``themis.estimate``. A twin set for "this
kind has no data needs" listed ``probability`` too, and returned before the
gap species ran — so a probability query whose kernel had raised
``MISSING_DISTRIBUTION`` reached the reader with no report at all, which
reads as nothing missing.
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

    ``names_an_estimand`` says the question is about a quantity the kernel
    could in principle put a number on. Two kinds ask about the graph and
    name none, and everything that follows from having a quantity is theirs
    to skip: there is no strongest-answer tier to state, and nothing but
    framing can leave them short of data. It is what makes a tier
    applicable, not what makes one knowable — a result whose kernel has not
    yet decided the shape of its answer still states none.

    ``interval_fallback`` names the bounds procedure whose interval stands
    in when the point is out of reach, and is None where this kernel has no
    interval channel for the question — an inventory fact, so it moves when
    an estimator is added. It is the one thing that decides whether "accept
    an interval instead" is advice or a false promise; leaving it to be
    inferred is how a query kind was told the opposite of its own answer.
    """

    kind: str
    asks: str
    settles: str
    fails: str
    verdict_is_the_answer: bool
    names_an_estimand: bool
    interval_fallback: str | None

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
    names_an_estimand=False,
    interval_fallback=None,
)
ASSOC = Question(
    "assoc",
    asks="whether two variables are associated in the graph",
    settles="the two are d-connected given the conditioning set",
    fails="the two are d-separated given the conditioning set",
    verdict_is_the_answer=True,
    names_an_estimand=False,
    interval_fallback=None,
)
IDENTIFY = Question(
    "identify",
    asks="whether the target effect is non-parametrically identifiable "
         "from observational data",
    settles="the effect is identifiable",
    fails="the effect is not identifiable from this graph",
    verdict_is_the_answer=True,
    # It asks about an estimand even though its answer is the verdict, so
    # the tier applies: 113 identify results reached point and 20 none.
    # No bounds are attempted for it — the scheduler runs them for effect
    # queries only — so an interval is not a fallback it has.
    names_an_estimand=True,
    interval_fallback=None,
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
    names_an_estimand=True,
    # A placeholder as much as a name: the scheduler rewrites this line to
    # whichever procedure actually produced ``bounds_result`` — Manski on a
    # bare graph, the IV bounds when an instrument is declared — and strips
    # it when the attempt returned nothing.
    interval_fallback="Balke-Pearl bounds",
)
PROBABILITY = Question(
    "probability",
    asks="the probability of an event under the model",
    settles="the probability is identifiable",
    fails="the probability is not identifiable from this graph",
    verdict_is_the_answer=False,
    # An observational conditional: a quantity, so it has both a tier and
    # data needs, and point-estimable, so no interval stands in for it.
    # Listed as neither for as long as both facts were hand-written sets.
    names_an_estimand=True,
    interval_fallback=None,
)
COUNTERFACTUAL = Question(
    "counterfactual",
    asks="the value of one cell of the counterfactual joint distribution",
    settles="the cell is identifiable, as a point or as bounds",
    fails="the cell is not identifiable from this graph",
    verdict_is_the_answer=False,
    names_an_estimand=True,
    interval_fallback="Tian-Pearl bounds",
)
CAUSATION = Question(
    "causation",
    asks="the probabilities of necessity and sufficiency for an outcome",
    settles="the probabilities of causation are identifiable",
    fails="the probabilities of causation are not identifiable",
    verdict_is_the_answer=False,
    names_an_estimand=True,
    # The interval is the ordinary answer here, not the consolation:
    # monotonicity is what collapses PN/PS/PNS to points, and it is a
    # premise the caller declares rather than one the data supply.
    interval_fallback="Tian-Pearl bounds",
)
SCM_COUNTERFACTUAL = Question(
    "scm_counterfactual",
    asks="one unit's counterfactual outcome under a linear structural model",
    settles="abduction-action-prediction determines the unit's value",
    fails="the unit's counterfactual value is not determined",
    verdict_is_the_answer=False,
    # Deterministic: given the coefficients and the unit's observations the
    # value is a point, and short of them there is nothing to bound.
    names_an_estimand=True,
    interval_fallback=None,
)
COUNTERFACTUAL_CONJUNCTION = Question(
    "counterfactual_conjunction",
    asks="the probability of several counterfactual events holding together",
    settles="the ID* / IDC* algorithm identifies the conjunction",
    fails="the ID* / IDC* algorithm returns a hedge — not identifiable",
    verdict_is_the_answer=False,
    # ID* answers with a formula or a hedge; no bounds procedure is wired
    # to the hedge, so a refused conjunction has no interval to offer.
    names_an_estimand=True,
    interval_fallback=None,
)
PROXIMAL_EFFECT = Question(
    "proximal_effect",
    asks="the effect recovered through proxies for an unmeasured confounder",
    settles="the proximal criterion holds, so the effect is identifiable",
    fails="the proximal criterion does not hold",
    verdict_is_the_answer=False,
    names_an_estimand=True,
    interval_fallback=None,
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
        return BY_KIND[kind]  # type: ignore[index]  # None must miss too,
        # and be refused by the same sentence as an unknown kind
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
