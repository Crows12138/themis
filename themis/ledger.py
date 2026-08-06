"""What one line of the assumption ledger says, and in whose words.

The ledger is the surface both the report and the browser lead with:
everything the answer takes on faith, worst first. One line of it carries
five fields, and three of them are closed vocabularies —

- :class:`Layer` — which part of the answer stops being true if this is false;
- :class:`Severity` — how badly the conclusion dies when it does;
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
It asks :func:`themis.output.assumption_glossary.answerable`, keyed on the
assumption's id, because the answer is a property of the assumption and not
of the channel that carried it. Both channels carrying an estimator's
assumptions — the structured identification spec and the flat declaration
list — used to name themselves in this field, which is why one id could sit
under two provenances at once: ``consistency_of_potential_outcomes`` was
``inherent`` 191 times and ``estimator_declared`` 92 times in one suite run,
the same sentence with two different answers to what the reader could do
about it. Two names for one thing is how that happens, so there is one.

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

from .types import EnvelopeName


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
    """What the reader loses. The verifier's one severity rule is derived
    from this and not from a convention: if identification failing means
    the number is not the causal effect at all, then an identification
    entry ranked anything but ``invalidating`` is incoherent."""

    zh: str
    """The reader's word, printed beside the claim."""

    def __new__(cls, value: str, breaks: str, zh: str):
        layer = str.__new__(cls, value)
        layer._value_ = value
        layer.breaks = breaks
        layer.zh = zh
        return layer

    IDENTIFICATION = (
        "identification",
        "the number is not the causal effect at all — a different quantity "
        "was computed, and no amount of data fixes it",
        "识别",
    )
    FUNCTIONAL_FORM = (
        "functional_form",
        "the estimand is right and the fitted shape is not, so magnitude "
        "and curvature move while the average often survives",
        "函数形式",
    )
    STRUCTURAL_EDGE = (
        "structural_edge",
        "an edge the answer path runs through is unestablished, so the "
        "path itself may not exist",
        "图上的边",
    )
    PARAMETER = (
        "parameter",
        "one numeric input was supplied rather than measured, so the "
        "answer moves with it",
        "参数取值",
    )
    CONFIDENCE = (
        "confidence",
        "only the interval moves; the point estimate stands",
        "区间",
    )


@unique
class Severity(EnvelopeName):
    """How the conclusion dies if this assumption is false.

    Not the data gap report's ``severity``, which grades how much a MISSING
    INPUT blocks an answer (``blocking`` / ``important`` /
    ``informational``). Two disjoint sets under one field name: one Python
    dict once held all six, which reads correctly and is why the browser
    copied it and took three.
    """

    rank: int
    """Worst first. The renderer leads with the head of the list, so this
    is the order the reader meets them in."""

    zh: str

    def __new__(cls, value: str, rank: int, zh: str):
        sev = str.__new__(cls, value)
        sev._value_ = value
        sev.rank = rank
        sev.zh = zh
        return sev

    INVALIDATING = ("invalidating", 0, "作废级")
    DISTORTING = ("distorting", 1, "扭曲级")
    CONFIDENCE_ONLY = ("confidence_only", 2, "仅影响置信")


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

    zh: str

    def __new__(cls, value: str, answerable: str, zh: str):
        prov = str.__new__(cls, value)
        prov._value_ = value
        prov.answerable = answerable
        prov.zh = zh
        return prov

    INHERENT = (
        "inherent",
        "the estimator — the method cannot be run without this, so the only "
        "way to overrule it is to answer by a different method",
        "方法本身要求",
    )
    CALLER_ASSERTED = (
        "caller_asserted",
        "the caller, who asserted it on the query — withdraw it and the "
        "answer weakens rather than disappearing, typically from a point to "
        "the interval it was pinned out of",
        "你在问题里断言的",
    )
    DEFAULT = (
        "default",
        "nobody — the estimator picked a form because none was specified, "
        "so the caller can specify one and this line changes",
        "估计器默认选择",
    )
    LLM_PROPOSAL = (
        "llm_proposal",
        "the upstream LLM that proposed the edge — confirm or deny the edge "
        "and the path this answer runs through is settled either way",
        "上游 LLM 提议",
    )
    DISCOVERY = (
        "discovery",
        "the causal-discovery algorithm that learned the edge from data — "
        "check it against what is known about the domain",
        "因果发现算法学出",
    )
    LLM_PRIOR = (
        "llm_prior",
        "the upstream LLM that supplied the number as common sense — supply "
        "the measured one and the answer is recomputed from it",
        "LLM 常识 prior",
    )


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
#: The estimator row is a product, so it permits ``(functional_form,
#: caller_asserted)`` and ``(confidence, caller_asserted)``, which nothing
#: writes today. That is headroom rather than a hole — a caller who passes
#: ``model='forest'`` has asserted the shape, and that line would correctly
#: read caller-asserted — but it is two pairs the check does not catch.
ADMISSIBLE: dict[str, tuple[frozenset[Layer], frozenset[Provenance]]] = {
    "estimator_assumption": (
        frozenset({Layer.IDENTIFICATION, Layer.FUNCTIONAL_FORM, Layer.CONFIDENCE}),
        frozenset({Provenance.INHERENT, Provenance.CALLER_ASSERTED}),
    ),
    "proposal_edge": (
        frozenset({Layer.STRUCTURAL_EDGE}),
        frozenset({Provenance.LLM_PROPOSAL, Provenance.DISCOVERY}),
    ),
    "theta_prior": (
        frozenset({Layer.PARAMETER}),
        frozenset({Provenance.LLM_PRIOR}),
    ),
    "audited_mechanism": (
        frozenset({Layer.FUNCTIONAL_FORM}),
        frozenset({Provenance.DEFAULT}),
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
    orphans = sorted(
        [f"Layer.{lay.name}" for lay in Layer if lay not in layers]
        + [f"Provenance.{p.name}" for p in Provenance if p not in provs]
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
    try:
        return ADMISSIBLE[producer]
    except KeyError:
        raise KeyError(
            f"ledger: {producer!r} does not assemble ledger entries; known "
            f"producers are {sorted(ADMISSIBLE)}"
        ) from None


_LAYERS: dict[str, Layer] = {str(x): x for x in Layer}
_SEVERITIES: dict[str, Severity] = {str(x): x for x in Severity}
_PROVENANCES: dict[str, Provenance] = {str(x): x for x in Provenance}


def stamp(producer: str, layer, provenance) -> tuple[Layer, Provenance]:
    """The one way a layer and a provenance reach a ledger entry.

    They are stamped together because neither is checkable alone: every
    member of both vocabularies is legitimate somewhere, and what makes a
    pair wrong is the producer it came from. Passing both through here
    makes the three meet once, at the only moment all three are known.
    """
    layers, provs = admissible(producer)
    lay = _LAYERS.get(str(layer))
    if lay is None:
        raise ValueError(
            f"ledger: {str(layer)!r} is not an assumption layer; the layers "
            f"are {sorted(_LAYERS)}"
        )
    prov = _PROVENANCES.get(str(provenance))
    if prov is None:
        raise ValueError(
            f"ledger: {str(provenance)!r} is not an assumption provenance; "
            f"they are {sorted(_PROVENANCES)}"
        )
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
    return lay, prov


def _describe(table: dict, value) -> str:
    """The reader's word for a value read back off an envelope.

    A name this build does not know renders as its own token rather than as
    silence or a guess: a name the reader has to look up still beats the
    field going missing, and it beats confidently naming the wrong one.
    """
    member = table.get(str(value))
    return member.zh if member is not None else f"`{value}`"


def layer_zh(value) -> str:
    """What part of the answer this assumption holds up, for the reader."""
    return _describe(_LAYERS, value)


def severity_zh(value) -> str:
    """How the conclusion dies if it is false, for the reader."""
    return _describe(_SEVERITIES, value)


def provenance_zh(value) -> str:
    """Who put it on the list, for the reader."""
    return _describe(_PROVENANCES, value)


def rank(value) -> int:
    """Sort key. A severity outside the vocabulary sorts FIRST, not last:
    the renderer leads with the head of the list, so an unrecognised value
    has to surface for someone to fix rather than sink below "only affects
    the interval"."""
    member = _SEVERITIES.get(str(value))
    return member.rank if member is not None else -1
