"""How the one input a counterfactual answer borrowed was licensed.

PN/PS/PNS and a counterfactual cell are computed from two things: the
observational joint P(X, Y), which the data or theta hands over directly,
and one or two INTERVENTIONAL risks P(Y=1 | do(X=x)), which observation
does not contain. Everything that separates an audited answer from a
plausible one is in how that second input was got — so the answer carries
``interventional_risk_provenance`` beside the number, and that value is
the whole licence.

A licence has to be checkable, or it certifies itself. That is why each
value here declares what it ASSERTS: a sentence a verifier can go and
re-derive from the query and the graph, without asking the producer.
``not_required`` asserts the two worlds coincide; ``user_experimental``
asserts the caller supplied the arm; ``backdoor_adjustment`` asserts a
set on the graph blocks every back-door path. None of them is a note.

**Why this file exists.** The vocabulary was a bare ``str`` and was
listed eleven times — three schema enums, a producer constant, a verifier
constant, an inline literal in a second verifier rule, a stale trailing
comment, three Chinese maps, and a two-branch ``if/else`` over a
four-value domain — with no two listings naming the same set. That is not
drift: the sets genuinely differ, because the admissible values depend on
WHICH DERIVATION RULE wrote them. What was missing is any statement of
that dependence, and the cost was not cosmetic. A value nobody wrote a
branch for asserts nothing, and asserting nothing is indistinguishable
from having been checked: ``user_experimental`` was the gate that skips
the identification re-check in three of the four rules, and no rule
re-derived it, so relabelling a back-door-standardised estimate as
experimental made its adjustment set stop being audited.

So the rows of :data:`ADMISSIBLE` are derivation rules, because that is
the thing the domain actually depends on. Every other listing is a union
or a projection of these four rows, and the tests say which.

**What is deliberately NOT here.** Each value also implies assumptions,
and those already have first-class names in
:mod:`themis.output.assumption_glossary`. They are not folded in, because
the assumption is a function of the value AND the estimand, not of the
value alone: probabilities of causation need both arms to be licensed and
a cell needs only the one it asks about, which is why the glossary
carries a plural id and a singular one. Collapsing them would make one of
those two claims wrong on the surface that reads it.

**The verifier does not import this.** It re-declares the same four rows,
and a test pins them equal. Re-deriving an answer from a vocabulary the
producer chose is not an independent check; catching drift with a test is
the discipline this package already uses for the same reason.
"""
from __future__ import annotations

from enum import unique

from .types import EnvelopeName


@unique
class RiskProvenance(EnvelopeName):
    """One named licence for the interventional risk behind an answer.

    ``asserts`` is what a verifier must re-derive; ``zh`` is what the
    reader is told. They are separate because they answer different
    questions — one is "how do I know this is not a story", the other is
    "where did this number come from" — and because ``zh`` has to be true
    on BOTH paths. The same licence reaches a reader from theta and from
    data, so a sentence saying "computed from the data" would be a lie
    half the time it is printed.
    """

    uses_risk: bool
    """Whether an interventional risk was an input at all. Three licences
    are precisely the claim that none was needed, and they are the
    strongest claims in the table for exactly that reason: they say the
    answer owes nothing to a quantity observation cannot supply."""

    can_refute_a_premise: bool
    """Whether this route confronts a declared premise with something the
    data could contradict — which is what makes an assumption it carries
    TESTABLE. Not the same question as ``uses_risk``, though the two agreed
    for as long as the consistency identity was the only solver and its one
    refutable input was the risk. A route that fits a polytope to the data
    can refute a declared monotonicity while consuming no risk at all, and a
    route that pins the answer FROM that monotonicity can refute nothing."""

    asserts: str
    """The checkable claim. Written for whoever adds the next licence: if
    a new value cannot be given a sentence a verifier could re-derive,
    it is a note about the producer's mood, not a licence."""

    zh: str
    """The reader's sentence — true whether the answer came from theta or
    from data."""

    def __new__(
        cls, value: str, uses_risk: bool, can_refute_a_premise: bool,
        asserts: str, zh: str,
    ):
        licence = str.__new__(cls, value)
        licence._value_ = value
        licence.uses_risk = uses_risk
        licence.can_refute_a_premise = can_refute_a_premise
        licence.asserts = asserts
        licence.zh = zh
        return licence

    # --- no interventional risk was used at all -------------------------------
    NOT_REQUIRED = (
        "not_required",
        False,
        False,
        "the intervened value equals the observed one, so the two worlds "
        "coincide and consistency answers the cell outright",
        "两个世界重合，一致性直接给出答案，没有用到任何干预风险",
    )
    PINNED_BY_MONOTONICITY = (
        "pinned_by_monotonicity",
        False,
        False,
        "no interventional risk is obtainable, and the declared "
        "monotonicity determines this cell on its own",
        "干预风险无从获得，本格完全由所声明的单调性钉死",
    )
    INSTRUMENT_RESPONSE_POLYTOPE = (
        "instrument_response_polytope",
        False,
        True,
        "no interventional risk is point-identified, and the named "
        "instrument is m-separated from the outcome once the treatment's "
        "outgoing edges are cut, so the cell is bounded directly over the "
        "response-type distributions reproducing P(X, Y | Z)",
        "干预风险无法点识别，本格改由工具变量的响应函数多面体直接框住",
    )

    # --- a risk was used, and this is what licensed it ------------------------
    DERIVED_IDENTIFICATION = (
        "derived_identification",
        True,
        True,
        "the risk was produced by the effect-identification subsystem from "
        "theta, which has its own independent verifier",
        "干预风险由识别层从图上导出",
    )
    EXOGENOUS = (
        "exogenous",
        True,
        True,
        "no back-door path runs from cause to effect, so the risk is the "
        "plain conditional probability — re-derivable as the empty "
        "adjustment set being admissible",
        "原因到结果没有后门路径，干预风险即条件概率",
    )
    BACKDOOR_ADJUSTMENT = (
        "backdoor_adjustment",
        True,
        True,
        "the named set is an admissible back-door set on the graph, and "
        "the risk is the standardization over it",
        "干预风险经后门标准化（g-formula）识别",
    )
    GENERAL_ID_PLUG_IN = (
        "general_id_plug_in",
        True,
        True,
        "no adjustment set exists, and the general ID algorithm "
        "point-identifies the asked arm anyway — the recorded estimand is "
        "the one ID derives for that arm",
        "没有可用的调整集，干预风险由 general ID 识别出的估计量求值",
    )
    USER_EXPERIMENTAL = (
        "user_experimental",
        True,
        True,
        "the caller supplied the arm as a randomized-experiment "
        "measurement, so the query itself carries it and nothing on the "
        "graph was used to obtain it",
        "干预风险来自调用方提供的随机实验数据",
    )


#: Which licences each derivation rule may write.
#:
#: The rows are derivation rules because the admissible set depends on the
#: rule and on nothing else: a rule fixes both the estimand (how many arms
#: the answer needs) and the source (theta or data), and those two together
#: are what makes a licence available or not. ``derived_identification``
#: cannot appear on a data rule — there is no theta to identify from — and
#: ``general_id_plug_in`` cannot appear on a theta rule, where the risk
#: comes back through the identification subsystem rather than as an
#: estimand to evaluate.
ADMISSIBLE: dict[str, frozenset[RiskProvenance]] = {
    "probabilities_of_causation_tian_pearl": frozenset({
        RiskProvenance.DERIVED_IDENTIFICATION,
        RiskProvenance.USER_EXPERIMENTAL,
    }),
    "numeric_causation_estimate": frozenset({
        RiskProvenance.EXOGENOUS,
        RiskProvenance.BACKDOOR_ADJUSTMENT,
        RiskProvenance.USER_EXPERIMENTAL,
    }),
    "counterfactual_cell_bounds": frozenset({
        RiskProvenance.NOT_REQUIRED,
        RiskProvenance.DERIVED_IDENTIFICATION,
        RiskProvenance.USER_EXPERIMENTAL,
    }),
    "numeric_counterfactual_cell_estimate": frozenset({
        RiskProvenance.NOT_REQUIRED,
        RiskProvenance.PINNED_BY_MONOTONICITY,
        RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE,
        RiskProvenance.EXOGENOUS,
        RiskProvenance.BACKDOOR_ADJUSTMENT,
        RiskProvenance.GENERAL_ID_PLUG_IN,
        RiskProvenance.USER_EXPERIMENTAL,
    }),
}


def _check_every_licence_is_reachable() -> None:
    """A licence no rule may write is one nothing can produce.

    The table above is a whitelist, and a whitelist is silent about what it
    left out — the failure it cannot report is a member that fell out of
    every row, which then looks exactly like a member that was never
    needed. Asking the question from the other side, at import, is the only
    place the answer is cheap.
    """
    written = frozenset().union(*ADMISSIBLE.values())
    orphans = sorted(str(p) for p in RiskProvenance if p not in written)
    if orphans:
        raise RuntimeError(
            f"risk_provenance: {orphans} are declared but no derivation rule "
            f"may write them — either a rule is missing from ADMISSIBLE or "
            f"the licence is dead"
        )


_check_every_licence_is_reachable()


def admissible(rule: str) -> frozenset[RiskProvenance]:
    """The licences ``rule`` may write. Unknown rule names are refused
    rather than answered with the empty set, which would read as "this
    rule writes no provenance" — the one thing a caller asking cannot
    distinguish on its own."""
    try:
        return ADMISSIBLE[rule]
    except KeyError:
        raise KeyError(
            f"risk_provenance: {rule!r} is not a rule that writes an "
            f"interventional-risk provenance; known rules are "
            f"{sorted(ADMISSIBLE)}"
        ) from None


def stamp(rule: str, licence: RiskProvenance) -> RiskProvenance:
    """The one way a licence reaches an answer.

    Producers pick a licence in a branch and carry it to three places —
    the envelope, the derivation step, and the assumption list — and the
    branch that picks it is by construction the one no test took. Passing
    it through here makes the rule and the licence meet once, at the only
    moment both are known, so a licence a rule may not write cannot leave
    the estimator at all.
    """
    if licence not in admissible(rule):
        raise ValueError(
            f"risk_provenance: {rule} may not write {str(licence)!r}; it may "
            f"write {sorted(str(p) for p in admissible(rule))}"
        )
    return licence


BY_NAME: dict[str, RiskProvenance] = {str(p): p for p in RiskProvenance}
"""The licence going by that envelope name, or nothing.

``RiskProvenance(name)`` is the same lookup and is the one to use where an
unknown name is an error. This is for the places where it is a question:
an envelope may have been written by another build, so "is this a licence
we know" has to be answerable with no.
"""


def describe(value) -> str:
    """The reader's sentence for a licence read back off an envelope.

    A name this build does not know renders as its own token rather than
    as silence or a guess: a name a reader has to look up still beats a
    sentence that leaves out where the number came from, and it beats a
    sentence that confidently names the wrong licence.
    """
    licence = BY_NAME.get(str(value))
    return licence.zh if licence is not None else f"`{value}`"


def carried_by(*rules: str) -> frozenset[RiskProvenance]:
    """The union over ``rules`` — what a container fed by all of them may
    hold. The schema's enums are exactly these unions, and the tests name
    which rules feed which container rather than restating the values."""
    return frozenset().union(*(admissible(r) for r in rules))
