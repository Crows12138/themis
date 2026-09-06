"""What one line of the assumption ledger says, and in whose words.

The ledger is the surface both the report and the browser lead with:
everything the answer takes on faith, worst first. One line of it carries
five fields, and three of them are closed vocabularies —

- :class:`Layer` — which part of the answer stops being true if this is false;
- :class:`Severity` — how badly the conclusion dies when it does, which is
  the three-way grading of the above and is therefore declared once per
  layer rather than per assumption;
- :class:`Provenance` — what the reader can do about this line: who can
  overrule it, and what they get back if they do.

**Why this file exists.** The three were a bare ``str`` each, written by
five producers and read by two surfaces, and only ``Severity`` had a table
anywhere. The other two had none, so nothing knew the domain: the report
printed both identifiers to the reader untranslated (3169 entries of one
suite run — ``（assumption／来源 inherent／不可检验）``), the browser
dropped both, and the verifier accepted 19 of 21 tampered layers and 8 of
8 tampered provenances, the empty string among them. A vocabulary with no
table is not a small omission on a disclosure surface; it is the reason a
member could be named ``assumption`` on an assumption ledger and say
nothing for nineteen entries before anyone lined the six up.

**The rows of** :data:`ADMISSIBLE` **are producers**, because that is what
the domain depends on. A ledger entry is assembled by one of four: the
estimator's own assumptions, a proposal edge the answer traverses, an LLM
theta prior, an audited mechanism. Each knows a different amount, and the
pair it may write is fixed by which one it is — which is a stronger
statement than membership, and it is the one the verifier can re-derive:
``llm_prior`` belongs to a parameter and nothing else, ``default`` to a
functional form and nothing else. Membership alone would let a back-door
assumption be relabelled an LLM prior.

**A producer may not choose the provenance of an estimator's assumption.**
It asks :func:`themis.assumption_glossary.answerable`, keyed on the
assumption's id, because the answer is a property of the assumption and not
of the channel that carried it. Both channels carrying an estimator's
assumptions — the structured identification spec and the flat declaration
list — used to name themselves in this field, which is why one id could sit
under two provenances at once: ``consistency_of_potential_outcomes`` was
``inherent`` 191 times and ``estimator_declared`` 92 times in one suite run,
the same sentence with two different answers to what the reader could do
about it. Two names for one thing is how that happens, so there is one.

**No producer chooses a severity either**, for a plainer reason: there was
never a second fact to choose. A layer says which part of the answer stops
being true and a severity grades how badly that kills it, so the grade
follows from the layer — and it did, on every one of 3252 entries of one
suite run, on all 146 glossary rows and at all 48 places a structured spec
was written. Two hundred sites restating one fact is not agreement, it is
199 chances to disagree — and a severity restated per assumption had
already been two records of one fact, which is how they disagree. So
:class:`Layer` names its grade once and
:func:`stamp` hands it back. The contrast is in the same glossary row:
``testable`` stays per-assumption, because two identification assumptions
genuinely differ on it.

**The verifier does not import this.** It re-declares the same five rows
and a test pins them equal. Re-deriving a ledger from the vocabulary its
producer chose is not an independent check.

**Not the same vocabulary as** :mod:`themis.risk_provenance`, which also
has a ``provenance``. That one licenses the one interventional risk behind
a counterfactual answer; this one says who is answerable for an assumption
being on a list. Same word, disjoint sets, different objects.
"""
from __future__ import annotations

from enum import unique

from . import registry
from .language import (
    BETWEEN_STATEMENTS, DEFAULT, Lang, Word, Words, fill, gloss, statements,
    token,
)
from .types import EnvelopeName


@unique
class Monotonicity(Word, vocabulary="monotonicity",
                   between=BETWEEN_STATEMENTS):
    """Which way the treatment is assumed to be able to move the outcome.

    It lived in :mod:`themis.types` with its words written out here, beside
    it but not on it, on the stated ground that the enum "carries no words
    to read". That absence is what five producers each answered for
    themselves — four interpolating the token into a Chinese sentence
    (``单调性（non_decreasing）``) and one hand-writing a pair of English
    clauses. A table kept beside a vocabulary is what :class:`~themis
    .language.Word` exists to delete, and the last thing keeping it a table
    was that a member had nowhere to go but a rendered string: a hole can
    hold a word now, and a bounds note has one.

    Here rather than in :mod:`themis.types` because a vocabulary carrying
    its own text needs the module that machinery lives in, and that module
    imports ``types``. Beside :class:`Layer` and :class:`Severity` because
    what it names is an assumption's content, which is what this module is
    the registry of.

    The words say what the assumption means before they say how it is
    written, because a reader who does not read ``Y(1) ≥ Y(0)`` is the
    reason this is not the token.
    """

    NON_DECREASING = ("non_decreasing", {
        "zh": "处理只会让结局不变或变大（Y(1) ≥ Y(0)）",
        "en": "treatment can only leave the outcome unchanged or raise it "
              "(Y(1) ≥ Y(0))",
    })
    NON_INCREASING = ("non_increasing", {
        "zh": "处理只会让结局不变或变小（Y(1) ≤ Y(0)）",
        "en": "treatment can only leave the outcome unchanged or lower it "
              "(Y(1) ≤ Y(0))",
    })


@unique
class Severity(EnvelopeName):
    """How the conclusion dies if this assumption is false.

    Three grades over the five layers, so it is a coarsening and not a
    second opinion: the layer says which part of the answer stops being
    true, and this says how much of the answer that costs. Which layer
    falls into which grade is declared on :class:`Layer`, once, because
    that is where the sentence it grades is written.

    Not the data gap report's ``severity``, which grades how much a MISSING
    INPUT blocks an answer (``blocking`` / ``important`` /
    ``informational``). Two disjoint sets under one field name: one Python
    dict once held all six, which reads correctly and is why the browser
    copied it and took three.
    """

    rank: int
    """Worst first. The renderer leads with the head of the list, so this
    is the order the reader meets them in."""

    words: Words
    """The reader's word for this grade, by language."""

    def __new__(cls, value: str, rank: int, words: Words):
        sev = str.__new__(cls, value)
        sev._value_ = value
        sev.rank = rank
        sev.words = words
        return sev

    INVALIDATING = ("invalidating", 0, {"zh": "作废级", "en": "invalidating"})
    DISTORTING = ("distorting", 1, {"zh": "扭曲级", "en": "distorting"})
    CONFIDENCE_ONLY = ("confidence_only", 2, {"zh": "仅影响置信",
                                              "en": "affects the interval only"})


@unique
class Layer(EnvelopeName):
    """Which part of the answer stops being true if this assumption is false.

    The five are a partition of the answer, not a list of topics, which is
    the test a candidate member has to pass: ``breaks`` has to name
    something the reader would still have if the others held. A sixth
    member called ``assumption`` failed it — every line of this ledger is
    an assumption — and what it was reaching for was a provenance.
    """

    breaks: str
    """What the reader loses, in the words the grade beside it is a grading
    of. The two are written together so that a new layer cannot be added
    without saying how badly its failure kills the conclusion, and cannot
    be given a grade its own sentence contradicts."""

    severity: Severity
    """The grade of ``breaks``. Declared here and nowhere else: an
    assumption's severity is not a fact about the assumption, and every
    place that used to state it separately was restating this."""

    words: Words
    """The reader's word, printed beside the claim, by language.

    Not ``breaks``, which is above and has no reader: that sentence is
    written for whoever is deciding whether a candidate member belongs
    here at all, and stays in one language for the same reason a
    docstring does."""

    def __new__(cls, value: str, breaks: str, severity: Severity,
                words: Words):
        layer = str.__new__(cls, value)
        layer._value_ = value
        layer.breaks = breaks
        layer.severity = severity
        layer.words = words
        return layer

    IDENTIFICATION = (
        "identification",
        "the number is not the causal effect at all — a different quantity "
        "was computed, and no amount of data fixes it",
        Severity.INVALIDATING,
        {"zh": "识别", "en": "identification"},
    )
    FUNCTIONAL_FORM = (
        "functional_form",
        "the estimand is right and the fitted shape is not, so magnitude "
        "and curvature move while the average often survives",
        Severity.DISTORTING,
        {"zh": "函数形式", "en": "functional form"},
    )
    STRUCTURAL_EDGE = (
        "structural_edge",
        "an edge the answer path runs through is unestablished, so the "
        "path itself may not exist",
        Severity.INVALIDATING,
        {"zh": "图上的边", "en": "an edge in the graph"},
    )
    PARAMETER = (
        "parameter",
        "one numeric input was supplied rather than measured, so the "
        "answer moves with it",
        Severity.DISTORTING,
        {"zh": "参数取值", "en": "a parameter value"},
    )
    CONFIDENCE = (
        "confidence",
        "only the interval moves; the point estimate stands",
        Severity.CONFIDENCE_ONLY,
        {"zh": "区间", "en": "the interval"},
    )


@unique
class Provenance(EnvelopeName):
    """What the reader can do about this line.

    A ledger a reader cannot act on is a ledger of worries. ``answerable``
    is what makes each line actionable, and it is the test a candidate
    member has to pass: name who can overrule this line and what they get
    back if they do. Two members that give the same answer are one member —
    ``estimator_declared`` and ``measurement_declared`` both said "argue
    with the estimator; you cannot overrule this without changing method",
    which is what ``inherent`` says, and they were the names of the two
    channels rather than of anything the reader could act on.
    """

    answerable: str
    """Who can overrule it, and what the reader gets back if they do."""

    words: Words
    """The reader's word for this provenance, by language.

    Not ``answerable``, which is above and has no reader either: it is
    the test a candidate member has to pass, written for whoever adds
    one."""

    def __new__(cls, value: str, answerable: str, words: Words):
        prov = str.__new__(cls, value)
        prov._value_ = value
        prov.answerable = answerable
        prov.words = words
        return prov

    INHERENT = (
        "inherent",
        "the estimator — the method cannot be run without this, so the only "
        "way to overrule it is to answer by a different method",
        {"zh": "方法本身要求", "en": "required by the method itself"},
    )
    CALLER_ASSERTED = (
        "caller_asserted",
        "the caller, who asserted it on the query — withdraw it and the "
        "answer weakens rather than disappearing, typically from a point to "
        "the interval it was pinned out of",
        {"zh": "你在问题里断言的", "en": "you asserted it in the question"},
    )
    CALLER_CHOSE = (
        "caller_chose",
        "the caller, who chose it on the query at a point where the method "
        "needs a choice and cannot make one — choose differently and the "
        "answer is recomputed from that choice; withdraw it and there is no "
        "answer rather than a wider one, which is what separates a choice "
        "from an assertion",
        {"zh": "你在问题里做的选择（方法必须有人选，它自己选不了）",
         "en": "your choice in the question — the method needs one and "
               "cannot make it"},
    )
    DEFAULT = (
        "default",
        "nobody — the estimator picked a form because none was specified, "
        "so the caller can specify one and this line changes",
        {"zh": "估计器默认选择", "en": "the estimator's default choice"},
    )
    LLM_PROPOSAL = (
        "llm_proposal",
        "the upstream LLM that proposed the edge — confirm or deny the edge "
        "and the path this answer runs through is settled either way",
        {"zh": "上游 LLM 提议", "en": "proposed by the upstream LLM"},
    )
    DISCOVERY = (
        "discovery",
        "the causal-discovery algorithm that learned the edge from data — "
        "check it against what is known about the domain",
        {"zh": "因果发现算法学出", "en": "learned by the causal-discovery algorithm"},
    )
    LLM_PRIOR = (
        "llm_prior",
        "the upstream LLM that supplied the number as common sense — supply "
        "the measured one and the answer is recomputed from it",
        {"zh": "LLM 常识 prior", "en": "an LLM's common-sense prior"},
    )


@unique
class Verdict(EnvelopeName):
    """What a check THIS RUN made concluded about one assumption.

    ``testable`` beside it is a static property — could anyone check this,
    in principle. It is silent about whether anybody did, so a premise this
    run tested and found false read on the page exactly like one nobody has
    ever looked at: same severity, same claim, same word ``testable``, no
    adjudication. The compensating prose went into the gap list several
    screens down, where it had to open by saying it was not a gap.

    Three members and not two, because failing to reject is not the same as
    establishing. Which of the two a passing check earns is a property of
    the check — see :class:`Check` — so no producer gets to choose it.
    """

    leads: bool
    """Whether a line carrying this verdict is read before its neighbours of
    the same severity. Only the refuted one is: an answer standing on a
    premise its own data refused is the first thing about that answer, and
    the ledger is ordered worst first."""

    words: Words
    """The reader's word for this verdict, by language."""

    def __new__(cls, value: str, leads: bool, words: Words):
        verdict = str.__new__(cls, value)
        verdict._value_ = value
        verdict.leads = leads
        verdict.words = words
        return verdict

    HELD = ("held", False,
            {"zh": "本次已核对，成立", "en": "checked here, and it holds"})
    NOT_REFUTED = (
        "not_refuted", False,
        {"zh": "本次已检验，这批数据没有否决它 —— 而这不等于证明它成立",
         "en": "tested here and this data did not refute it, which is not "
               "the same as establishing it"})
    REFUTED = ("refuted", True,
               {"zh": "本次已检验，**这批数据否决了它**",
                "en": "tested here, and **this data refutes it**"})


@unique
class Check(EnvelopeName):
    """What was run against the data, on the occasion it was run.

    A verdict with no check named is a claim the reader cannot go and look
    at, and the checks differ in the one way that decides how much a pass is
    worth: counting the cells of an adjustment set SETTLES whether every one
    of them holds both arms, while a hypothesis test that does not reject
    has ruled nothing out. That difference lives here rather than at the
    call site, so a producer reports only whether its check FAILED and the
    word a pass earns follows from which check it was.
    """

    a_pass_settles_it: bool
    """Whether passing this check establishes the assumption, or only fails
    to refute it."""

    words: Words
    """The reader's name for this check, by language."""

    def __new__(cls, value: str, a_pass_settles_it: bool, words: Words):
        check = str.__new__(cls, value)
        check._value_ = value
        check.a_pass_settles_it = a_pass_settles_it
        check.words = words
        return check

    FITTED_PROPENSITY_RANGE = (
        "fitted_propensity_range", False,
        {"zh": "把处理概率 P(处理|调整集) 拟合出来，看有多少样本落在重叠带之外",
         "en": "fitting P(treatment | adjustment set) and reading how much of "
               "the sample lands outside the overlap band"})
    STRATUM_ARM_COUNTS = (
        "stratum_arm_counts", True,
        {"zh": "逐层清点调整集每个格子里的两个处理臂",
         "en": "counting both treatment arms in every cell of the adjustment "
               "set"})
    SARGAN = ("sargan", False,
              {"zh": "同方差 Sargan 过度识别检验",
               "en": "the homoskedastic Sargan over-identification test"})
    ROBUST_HANSEN_J = (
        "robust_hansen_j", False,
        {"zh": "异方差稳健 Hansen J 过度识别检验",
         "en": "the heteroskedasticity-robust Hansen J over-identification "
               "test"})
    ACR_MARGIN_WEIGHTS = (
        "acr_margin_weights", False,
        {"zh": "各剂量边际的权重符号（有负权重即为反驳）",
         "en": "the signs of the per-margin weights, where a negative one "
               "is a refutation"})


def checked(check: Check, refuted: bool) -> tuple[Check, Verdict]:
    """The verdict this check's outcome earns.

    A producer says whether the check FAILED and nothing else. Which word a
    pass earns is not the run's to decide: a test that did not reject has
    established nothing, and letting the site that ran it write ``held``
    anyway is how a ledger comes to say the data proved something it only
    failed to disprove.
    """
    if refuted:
        return check, Verdict.REFUTED
    return check, (Verdict.HELD if check.a_pass_settles_it
                   else Verdict.NOT_REFUTED)


#: Which ``(layer, provenance)`` pairs each producer of a ledger entry may
#: write, as ``layers x provenances``.
#:
#: The rows are producers because a producer is exactly what fixes the
#: pair. One of them assembles entries out of an estimator's own words and
#: may therefore say any of the three things an estimator's assumptions can
#: be about; the other three each read one channel that is about one thing,
#: and so write one layer apiece.
#:
#: The structured identification spec and the flat declaration list are ONE
#: producer here, not two. A spec IS the flat declaration said in better
#: words — the code that folds them says so and keys the fold on the shared
#: id — so a row per channel could only have differed by naming the channel,
#: which is the mistake this table exists to make impossible.
#:
#: The estimator row does NOT carry ``functional_form``, and the narrowing is
#: the point rather than an oversight. That channel carries an id and nothing
#: else, and who settled a shape cannot be read off an id; while the row
#: permitted the layer, the pair it wrote was ``(functional_form, inherent)``
#: for every form assumption in the system, including the ones a caller had
#: named on the command line. The row below is the only one that may write the
#: layer, because it is the only one holding the run's own answer.
#:
#: It DOES carry ``parameter``, and the narrowing above is the reason that
#: is consistent rather than an exception to it. What disqualified
#: ``functional_form`` was that a shape's author cannot be read off its id;
#: a numeric input's author can, because there are two ids and the choice
#: each one names is checked against this answer's own record — the same
#: discipline ``caller_chose`` is already held to, run in both directions.
#: ``default`` joins for the same reason and only for ids that declare where
#: "nobody chose this" is recorded.
#:
#: The estimator row is still a product, so it permits ``(confidence,
#: caller_asserted)``, which nothing writes today. That is headroom rather
#: than a hole — but it is one pair the check does not catch.
ADMISSIBLE: dict[str, tuple[frozenset[Layer], frozenset[Provenance]]] = {
    "estimator_assumption": (
        frozenset({Layer.IDENTIFICATION, Layer.CONFIDENCE, Layer.PARAMETER}),
        frozenset({Provenance.INHERENT, Provenance.CALLER_ASSERTED,
                   Provenance.CALLER_CHOSE, Provenance.DEFAULT}),
    ),
    # A ROUTE block's own premises. Narrower than the estimator row and not
    # a second name for it: this channel is read where no estimator ran, so
    # it can only be about whether the estimand was identified at all, and
    # the premises are the theorem's rather than anybody's assertion.
    "identification_premise": (
        frozenset({Layer.IDENTIFICATION}),
        frozenset({Provenance.INHERENT}),
    ),
    "proposal_edge": (
        frozenset({Layer.STRUCTURAL_EDGE}),
        frozenset({Provenance.LLM_PROPOSAL, Provenance.DISCOVERY}),
    ),
    "theta_prior": (
        frozenset({Layer.PARAMETER}),
        frozenset({Provenance.LLM_PRIOR}),
    ),
    # The shape choice, pointed at by the mechanism audit — and the only
    # producer of a functional-form line, for the reason above. Every
    # provenance a caller or an estimator can reach, because who settled a
    # form is a property of the RUN and not of the id: the same
    # ``logit_outcome_regression`` is the method's definition where the
    # method takes no ``model=``, the estimator's own pick where it does and
    # was told nothing, and the caller's where they named one. No table
    # keyed on the id holds a value true of all of those, so the id is not
    # asked: the block carries the estimate's own resolution and answers per
    # assumption, and this row is what those answers are checked against.
    #
    # Both caller members, and the difference between them is what the
    # reader does next rather than a shade of the same thing. ASSERTED is a
    # form the estimator could have resolved without them, so withdrawing it
    # falls back rather than stopping. CHOSE is a form nothing but the
    # caller can supply — where the data cannot distinguish two estimands,
    # naming which one is wanted is not an assertion about the world but the
    # question itself, and withdrawing it leaves no answer here rather than
    # a wider one. A row that admitted only the first would have forced the
    # second to arrive wearing its name, and the ledger would then have told
    # a reader they could drop it and keep the number.
    "audited_mechanism": (
        frozenset({Layer.FUNCTIONAL_FORM}),
        frozenset({Provenance.INHERENT, Provenance.DEFAULT,
                   Provenance.CALLER_ASSERTED, Provenance.CALLER_CHOSE}),
    ),
}


def _check_every_value_is_reachable() -> None:
    """A layer or provenance no producer may write is one nothing can write.

    ADMISSIBLE is a whitelist, and a whitelist is silent about what it left
    out: a member that fell out of every row looks exactly like a member
    nothing needed. Asking from the other side, at import, is the only
    place the answer is cheap — and it is the check that would have made
    ``estimator_default`` visible as a spelling of ``default`` that no
    producer ever wrote.
    """
    layers = frozenset().union(*(row[0] for row in ADMISSIBLE.values()))
    provs = frozenset().union(*(row[1] for row in ADMISSIBLE.values()))
    grades = frozenset(lay.severity for lay in Layer)
    # A verdict is reached through a check rather than through a producer, so
    # its denominator is the checks that exist: `held` is what a check whose
    # pass SETTLES its premise earns, and while no check settled anything the
    # member read in the source exactly like a distinction the system draws.
    verdicts = frozenset(checked(check, refuted)[1]
                         for check in Check for refuted in (True, False))
    orphans = sorted(
        [f"Layer.{lay.name}" for lay in Layer if lay not in layers]
        + [f"Provenance.{p.name}" for p in Provenance if p not in provs]
        # A grade no layer falls into cannot be stamped on an entry, and
        # reads in the source exactly like a grade nothing has needed yet.
        + [f"Severity.{s.name}" for s in Severity if s not in grades]
        + [f"Verdict.{v.name}" for v in Verdict if v not in verdicts]
    )
    if orphans:
        raise RuntimeError(
            f"ledger: {orphans} are declared but no producer may write them "
            f"— either a producer is missing from ADMISSIBLE or the value "
            f"is dead"
        )


_check_every_value_is_reachable()


def admissible(producer: str) -> tuple[frozenset[Layer], frozenset[Provenance]]:
    """What ``producer`` may write. An unknown name is refused rather than
    answered with the empty pair, which would read as "this producer writes
    no layer" — the one thing a caller asking cannot tell on its own."""
    return registry.row_for(
        ADMISSIBLE, producer, named="themis.ledger.ADMISSIBLE")


_LAYERS: dict[str, Layer] = {str(x): x for x in Layer}
_SEVERITIES: dict[str, Severity] = {str(x): x for x in Severity}
_PROVENANCES: dict[str, Provenance] = {str(x): x for x in Provenance}


def provenance_named(value) -> Provenance:
    """That word as the member it names, or a refusal that lists the words.

    Callers outside a ledger entry need this too — a disclosure block records
    who settled a choice without going through :func:`stamp`, and calling the
    enum directly is both unreadable to a type checker and silent about what
    the alternatives were.
    """
    member = _PROVENANCES.get(str(value))
    if member is None:
        raise ValueError(
            f"ledger: {str(value)!r} is not an assumption provenance; "
            f"they are {sorted(_PROVENANCES)}"
        )
    return member


def stamp(producer: str, layer, provenance) -> tuple[Layer, Severity, Provenance]:
    """The one way a layer, a severity and a provenance reach a ledger entry.

    The layer and the provenance are stamped together because neither is
    checkable alone: every member of both vocabularies is legitimate
    somewhere, and what makes a pair wrong is the producer it came from.
    Passing both through here makes the three meet once, at the only moment
    all three are known.

    The severity is not asked for. It comes back with them because it is
    the layer's grade and a producer has nothing to add to it — which is
    also what stops the next producer from restating it differently.
    """
    layers, provs = admissible(producer)
    lay = _LAYERS.get(str(layer))
    if lay is None:
        raise ValueError(
            f"ledger: {str(layer)!r} is not an assumption layer; the layers "
            f"are {sorted(_LAYERS)}"
        )
    prov = provenance_named(provenance)
    if lay not in layers:
        raise ValueError(
            f"ledger: producer {producer} may not write layer {str(lay)!r}; "
            f"it may write {sorted(str(x) for x in layers)}"
        )
    if prov not in provs:
        raise ValueError(
            f"ledger: producer {producer} may not write provenance "
            f"{str(prov)!r}; it may write {sorted(str(x) for x in provs)}"
        )
    return lay, lay.severity, prov


_LAYER_WORDS: dict[str, Words] = {k: v.words for k, v in _LAYERS.items()}
_SEVERITY_WORDS: dict[str, Words] = {
    k: v.words for k, v in _SEVERITIES.items()
}
_PROVENANCE_WORDS: dict[str, Words] = {
    k: v.words for k, v in _PROVENANCES.items()
}



def layer_word(value, lang: Lang | str = DEFAULT) -> str:
    """What part of the answer this assumption holds up, for the reader."""
    return gloss(_LAYER_WORDS, value, lang)


def severity_word(value, lang: Lang | str = DEFAULT) -> str:
    """How the conclusion dies if it is false, for the reader."""
    return gloss(_SEVERITY_WORDS, value, lang)


def provenance_word(value, lang: Lang | str = DEFAULT) -> str:
    """Who put it on the list, for the reader."""
    return gloss(_PROVENANCE_WORDS, value, lang)


_VERDICTS: dict[str, Verdict] = {str(x): x for x in Verdict}
_CHECKS: dict[str, Check] = {str(x): x for x in Check}
_VERDICT_WORDS: dict[str, Words] = {k: v.words for k, v in _VERDICTS.items()}
_CHECK_WORDS: dict[str, Words] = {k: v.words for k, v in _CHECKS.items()}


def verdict_word(value, lang: Lang | str = DEFAULT) -> str:
    """What this run's check concluded, for the reader."""
    return gloss(_VERDICT_WORDS, value, lang)


def check_word(value, lang: Lang | str = DEFAULT) -> str:
    """What was run against the data, for the reader."""
    return gloss(_CHECK_WORDS, value, lang)


def rank(value) -> int:
    """Sort key. A severity outside the vocabulary sorts FIRST, not last:
    the renderer leads with the head of the list, so an unrecognised value
    has to surface for someone to fix rather than sink below "only affects
    the interval"."""
    member = _SEVERITIES.get(str(value))
    return member.rank if member is not None else -1


def leads(entry) -> int:
    """Within one severity, a refuted line comes first.

    Second key rather than a severity of its own: what a refuted assumption
    costs the answer is still whatever its layer costs, and a grade that
    said otherwise would be a second opinion about the same failure. What
    changes is the order the reader meets them in.
    """
    verdict = _VERDICTS.get(str((entry.get("checked") or {}).get("verdict")))
    return 0 if verdict is not None and verdict.leads else 1


#: The line a ledger is led with, and the two counts inside it.
#:
#: These were a field on the ledger, and both counts were the list beside
#: that field counted. A count stored next to the thing counted is a second
#: record: the verifier could only check this one by searching the sentence
#: for ``依赖 {n} 条假设`` — a rule that reads one language, over a field the
#: kernel wrote in one language, which is the same fact twice rather than a
#: check.
SUMMARY: Words = {
    "zh": "这个结论依赖 {total} 条假设：{parts}。下面按严重度从高到低列出 "
          "—— Themis 的计算在这些假设下是对的，{audit}",
    "en": "this conclusion rests on {total} assumptions: {parts}. They are "
          "listed worst first — Themis's arithmetic is right under them, "
          "{audit}",
}
SUMMARY_INVALIDATING: Words = {
    "zh": "{n} 条一旦不成立、整条因果结论作废",
    "en": "{n} of them take the whole causal conclusion with them if false",
}
SUMMARY_OTHER: Words = {
    "zh": "{n} 条影响形状 / 量级或置信度",
    "en": "{n} bear on the shape, the magnitude or the confidence",
}
#: How the lead line ends, and the reason it is a hole.
#:
#: It ended "whether they hold is yours to audit one by one", which was true
#: of every line while nothing here could record a check. It stopped being
#: true the moment one could: a run that tested a premise and watched this
#: data refuse it was still telling the reader the auditing was all theirs.
AUDIT_ALL_OF_THEM: Words = {
    "zh": "但假设本身的真假需要你逐条审核。",
    "en": "but whether they hold is yours to audit one by one.",
}
AUDIT_THE_REST: Words = {
    "zh": "而其中 {n} 条这一次已经检验过（结论标在那一行上）；其余的真假需要"
          "你逐条审核。",
    "en": "and {n} of them were checked on this run, with the verdict on the "
          "line; whether the rest hold is yours to audit one by one.",
}


def summary(entries, lang: Lang | str = DEFAULT) -> str:
    """The one line a ledger is led with, assembled where the reader is."""
    entries = list(entries or ())
    if not entries:
        return ""
    invalidating = sum(1 for e in entries
                       if str(e.get("severity")) == str(Severity.INVALIDATING))
    parts = []
    if invalidating:
        parts.append(fill(SUMMARY_INVALIDATING, lang, n=invalidating))
    if len(entries) - invalidating:
        parts.append(fill(SUMMARY_OTHER, lang, n=len(entries) - invalidating))
    adjudicated = sum(1 for e in entries if e.get("checked"))
    audit = (fill(AUDIT_THE_REST, lang, n=adjudicated) if adjudicated
             else fill(AUDIT_ALL_OF_THEM, lang))
    return fill(SUMMARY, lang, total=len(entries),
                parts=statements(*parts, lang=lang), audit=audit)
