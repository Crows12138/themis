"""The parts an answer is made of, named once.

A result carries two kinds of part. The typed ones are fields of
:class:`~themis.types.QueryResult` — declared in one place, spelled once,
and a misspelling is an ``AttributeError``. The rest live under
``extensions``, an untyped map whose keys are string literals repeated at
every writer and every reader, and a misspelling there is silence: the
reader sees ``None`` and reports whatever it reports when the block is
genuinely absent.

The result schema was already a partial registry of that map — nine of
these blocks have a full sub-schema there — but the map is declared open
for forward compatibility, so eleven more were added over time without
entering it and nothing said so. That is the same shape as everything
else this phase has taken apart: a fact with no first-class representation
degrades into a convention, and a convention that drifts does not raise.

So the names live here, and the parts of the system that reason about
blocks resolve through this module rather than spelling them again:
:mod:`themis.runtime.postprocess` checks its declared reads and writes
against the registry at import, and a test checks the registry against a
running system in both directions — a key nobody registered, and a
registration nothing writes, are both failures.

**This is the result envelope's map, not the program's.** A program
carries its own ``extensions`` side-channel (upstream ambiguities,
discovery metadata, monotonicity declarations), which shares the word and
nothing else. ``ambiguities`` appears in both and means the same thing in
both only because a pass deliberately copies the relevant entries across.

Each block also says how it is READ. The registry grouped itself by
producer from the day it was written — "what the identification layer
concludes", "what the numeric end produces" — and never by consumer, so
the only way to answer "does anyone say this to anyone" was to cross every
block against every surface by hand. That census found ten blocks whose
whole job is to say how the estimand was identified and no place in any
report that says it. A comment cannot be checked; :class:`Family` can,
and :func:`bind` holds a surface to the family it claims to render.

The same axis, asked a second time, emptied a family rather than filling
one: the two blocks that said why a query was refused were answering a
question the result already answers in a top-level field, and they were
there because the identification layer had no way to reach it.

Which question a block answers is not the same as how it gets to whoever
asked, and only the first became a field. The second stayed a comment, one
per family heading — and the guarantee ``read_as`` bought held for ten
blocks of eighteen, because ``bind`` was called once. The guard meant to
notice it asked whether any module *names* the block, which its writer
satisfies. So ``carried_by`` is required too, and the surfaces record what
they bind: a block that claims a renderer is checked against the surfaces,
and a block that names a carrier is checked against the table the carrier
is in.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Mapping, TypeVar

R = TypeVar("R")


@dataclass(frozen=True)
class Family:
    """One of the reader's questions, and the blocks that answer it.

    Not a taxonomy for its own sake: this is the axis the registry was
    missing. Grouped by producer, a block that reached nobody looked
    exactly like a block that reached somebody, because both were listed
    under whoever wrote them.
    """

    name: str
    tells: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


ROUTE = Family(
    "route",
    tells="how the estimand was identified — which pattern the graph was "
          "recognised as, on which set, under which extra premise",
)
ANSWER = Family(
    "answer",
    tells="the quantity itself, on the paths that put it beside the "
          "estimate rather than in it",
)
ASSUMPTION = Family(
    "assumption",
    tells="what has to hold for the answer to stand",
)
GAP = Family(
    "gap",
    tells="what is missing from, or inconsistent in, what was supplied",
)
FAMILIES: tuple[Family, ...] = (ROUTE, ANSWER, ASSUMPTION, GAP)

# There is no refusal family. Why no number came out is a top-level field
# of the result — the schema always said so — and the species and kind
# live in :mod:`themis.refusals`. Two blocks used to hold it for the
# identification layer alone, in bare prose, because ``QueryResult`` had
# no such field and identification, unlike an estimator, has no dispatch
# to catch an exception for it. Neither reached a reader: one was
# rendered by the detachable explainer only, the other by nothing.


class Block(str):
    """One named part of the result envelope.

    A ``str`` subclass, so a block is usable wherever its name was: as a
    dict key, in a comparison, through ``json.dumps``. What it adds is
    that the name exists in exactly one place, and that ``holds`` travels
    with it instead of living in whichever docstring happened to describe
    the writer.

    ``read_as`` is required, so a block cannot be added without saying
    which of the reader's questions it answers. That is the whole guard:
    a new route enters :func:`declared_as` the moment it is declared, and
    the report's :func:`bind` then refuses to import until something
    renders it.

    ``carried_by`` is required for the same reason, on the other axis.
    """

    holds: str
    """What a writer puts in it."""

    read_as: Family
    """Which of the reader's questions it answers."""

    carried_by: "Block | str | None"
    """What re-presents it, or ``None`` when a surface renders it itself.

    Which question a block answers and how it gets to somebody who asked
    are different facts, and only the first one was written down. The
    second lived in three comments over three family headings — one per
    mechanism — and a comment is what this module exists to replace.

    It is per BLOCK, not per family, which is what those comments got
    wrong by sitting where they sat: inside one family the ledger is
    rendered and the two beside it are folded into the ledger first.

    ``None`` is the claim that some surface binds a renderer, and
    :func:`bind` records what the surfaces bound, so the claim is checked
    rather than believed. A name is the claim that something else says
    it — either another block, which must itself reach, or a top-level
    field of the result, which the report already renders. Both are
    members of tables that exist, so neither can be spelled into being.
    """

    def __new__(
        cls,
        name: str,
        *,
        holds: str,
        read_as: Family,
        carried_by: "Block | str | None",
    ) -> "Block":
        block = super().__new__(cls, name)
        block.holds = holds
        block.read_as = read_as
        block.carried_by = carried_by
        return block

    def __repr__(self) -> str:
        return f"Block({str(self)!r})"

    def __reduce__(self):
        """Copies and pickles come back as the plain name.

        A block used as a dict key travels into the envelope, and the
        envelope is data: whoever copies or serializes it must get back
        exactly the string that was always there. What ``holds`` says
        belongs to the registry, not to each place the name appears.
        """
        return (str, (str(self),))


# --- ROUTE: how the estimand was identified ---------------------------------
#
# Declaration order is the order a report says them in, so the general
# pattern leads and the recoverability verdicts — which qualify whatever
# came before them — come last.

IDENTIFICATION = Block(
    "identification",
    holds="which pattern the graph was recognised as — back-door, "
          "front-door, Tian — beside the formula it produced",
    read_as=ROUTE,
    carried_by=None,
)
IV_IDENTIFICATION = Block(
    "iv_identification",
    holds="the chosen instrument, the set it is valid conditional on, and "
          "the assumption a Wald ratio rests on",
    read_as=ROUTE,
    carried_by=None,
)
TRANSPORT_IDENTIFICATION = Block(
    "transport_identification",
    holds="the source and target populations, the selection nodes between "
          "them, and the transport formula",
    read_as=ROUTE,
    carried_by=None,
)
JOINT_IDENTIFICATION = Block(
    "joint_identification",
    holds="how a do() over a treatment set was identified, including the "
          "treatment x treatment interaction no sequence of singles recovers",
    read_as=ROUTE,
    carried_by=None,
)
LONGITUDINAL_IDENTIFICATION = Block(
    "longitudinal_identification",
    holds="the time-varying treatment sequence and the g-formula that "
          "identifies it under sequential exchangeability",
    read_as=ROUTE,
    carried_by=None,
)
MEDIATION_DECOMPOSITION = Block(
    "mediation_decomposition",
    holds="natural direct and indirect effects through one mediator, and "
          "their numbers once the numeric end has run",
    read_as=ROUTE,
    carried_by=None,
)
MEDIATION_JOINT_DECOMPOSITION = Block(
    "mediation_joint_decomposition",
    holds="the same decomposition through a mediator SET treated as one "
          "block, which is what makes it identifiable without an ordering",
    read_as=ROUTE,
    carried_by=None,
)
PROXIMAL_ESTIMAND = Block(
    "proximal_estimand",
    holds="the bridge-function estimand proximal identification produces "
          "from two proxies of an unmeasured confounder",
    read_as=ROUTE,
    carried_by=None,
)
SELECTION_RECOVERY = Block(
    "selection_recovery",
    holds="whether the unbiased effect is recoverable from a "
          "selection-restricted sample, and what external data it needs",
    read_as=ROUTE,
    carried_by=None,
)
MISSING_DATA_RECOVERY = Block(
    "missing_data_recovery",
    holds="whether the estimand is recoverable under the declared "
          "missingness mechanism, from the m-graph",
    read_as=ROUTE,
    carried_by=None,
)

# --- ANSWER: the quantity, on the paths that put it beside the estimate -----
#
# Not answer SHAPES: a shape says how ``numeric_estimate`` came out, and
# the two rendered here are written where there is no ``numeric_estimate``
# at all — the theta path answers from the joint distribution without ever
# calling an estimator. The third is written beside one, and its
# ``carried_by`` says so.

CAUSATION = Block(
    "causation",
    holds="probabilities of necessity and sufficiency, with the "
          "interventional risks they are computed from",
    read_as=ANSWER,
    carried_by=None,
)
COUNTERFACTUAL_CELL = Block(
    "counterfactual_cell",
    holds="one cell of the counterfactual joint distribution, the "
          "attribution layer's finest-grained answer",
    read_as=ANSWER,
    # Its producer calls this a display copy, and measuring it agrees:
    # written only on the path that also produces a ``numeric_estimate``,
    # where the cell is the estimate's own field and an answer shape
    # already renders it.
    carried_by="numeric_estimate",
)
SCM_COUNTERFACTUAL = Block(
    "scm_counterfactual",
    holds="a point counterfactual under a linear SCM, plus the display "
          "copy of the value the audited estimate must agree with",
    read_as=ANSWER,
    carried_by=None,
)

# --- ASSUMPTION: what has to hold ------------------------------------------
#
# One family, two mechanisms — which is why the question is asked of the
# block rather than of the family. A census that asked only "who renders
# this" scored the two channels as unreached and was wrong.

ASSUMPTION_LEDGER = Block(
    "assumption_ledger",
    holds="every load-bearing assumption the answer rests on, ranked by "
          "how the conclusion dies if it is false",
    read_as=ASSUMPTION,
    carried_by=None,
)
MECHANISM_AUDIT = Block(
    "mechanism_audit",
    holds="the functional form the number was computed under, and where "
          "that form came from — the estimator's default or the caller",
    read_as=ASSUMPTION,
    carried_by=ASSUMPTION_LEDGER,
)
LLM_PROPOSED_REVIEW = Block(
    "llm_proposed_review",
    holds="the edges and parameter priors a language model proposed, for "
          "a reader to accept or reject before trusting the number",
    read_as=ASSUMPTION,
    carried_by=ASSUMPTION_LEDGER,
)

# --- GAP: what is missing from, or wrong with, the inputs -------------------
#
# Neither is rendered on its own. The producer writes gap entries beside
# the block, and what stays in the block is the evidence a verifier
# re-derives those entries from.

AMBIGUITIES = Block(
    "ambiguities",
    holds="the upstream naming ambiguities that bear on THIS query, "
          "copied across from the program's own side-channel",
    read_as=GAP,
    carried_by="data_gap_report",
)
TYPE_RECONCILIATION = Block(
    "type_reconciliation",
    holds="what was checked when the declared variable types and the "
          "data's own types disagreed",
    read_as=GAP,
    carried_by="data_gap_report",
)

DECLARED: tuple[Block, ...] = tuple(
    value for value in tuple(globals().values()) if isinstance(value, Block)
)
"""Every block of the result envelope's extensions map, in declaration order.

Collected from this module rather than listed again below it: a block
declared above and forgotten here would be exactly the drift this module
exists to end. The order is kept because a surface that renders a whole
family reads them in it — so the running order of a report section is
this file, not a second list somewhere else.
"""

ALL: frozenset[Block] = frozenset(DECLARED)

BY_NAME: dict[str, Block] = {str(block): block for block in ALL}


def declared_as(family: Family) -> tuple[Block, ...]:
    """Every block of one family, in declaration order."""
    return tuple(block for block in DECLARED if block.read_as is family)


def rendered_in(family: Family) -> tuple[Block, ...]:
    """The blocks of one family a surface has to render itself.

    The rest of the family reaches its reader through whatever their
    ``carried_by`` names, so demanding a renderer for them would demand a
    second telling of something already said.
    """
    return tuple(b for b in declared_as(family) if b.carried_by is None)


BOUND: dict[str, set[str]] = {}
"""Which surface bound which blocks, filled at import.

``carried_by=None`` is a claim about a surface, and one the registry
cannot check from inside — the surfaces are downstream of it. So the
surfaces record what they bound on their way past, and a test asks the
one question that closes the loop.

By surface, not a flat set. "Somebody rendered it" is the shape of check
that let this go: the two blocks answered from theta were read by the
detachable explainer, which satisfies every reachability question that
does not ask WHICH surface. A test that wants to hold the load-bearing
report to something has to be able to name it.

Plain names rather than blocks, because the answer is compared against
the registry and a set of blocks would carry the registry into its own
audit.
"""


def bind(family: Family, renderers: Mapping[Block, R]) -> dict[Block, R]:
    """One surface's renderers for one family, checked both ways.

    An unbound block is a fact that arrives at this surface and produces
    nothing — the silence the ``read_as`` axis exists to make impossible
    to add. A bound block from outside the family is a renderer whose
    output would land in the wrong section, which reads as coverage and
    is not; so is one whose block said something else carries it, and
    that is why the members here are the rendered ones rather than the
    whole family.

    Which surface this is comes from the caller rather than from an
    argument it would have to spell. The module doing the binding is a
    fact already in hand, and a convention that has to be rewritten at
    every use point is one that gets it wrong somewhere.
    """
    members = rendered_in(family)
    missing = sorted(str(b) for b in members if b not in renderers)
    if missing:
        raise ValueError(
            f"no renderer for {family.name} block(s) {missing}; a result "
            f"carrying one would reach this surface and say nothing"
        )
    extra = sorted(str(b) for b in renderers if b not in members)
    if extra:
        raise ValueError(
            f"renderer bound for {extra}, which {family.name} does not "
            f"contain, or which said something else carries it "
            f"(themis.blocks.rendered_in)"
        )
    surface = sys._getframe(1).f_globals.get("__name__", "?")
    BOUND.setdefault(surface, set()).update(str(b) for b in renderers)
    return dict(renderers)


def check_registered(result: dict) -> None:
    """Refuse to emit a result carrying a block nobody registered.

    The registry is only worth having if it cannot fall behind, and the
    way it fell behind before was silent: the result schema declares the
    extensions map open, so eleven blocks were added over the years
    without an entry and every one of them validated. Checking at the
    two single exits — the structural one and the numeric one — means
    the first test that exercises a new block says so, without anyone
    having to think of writing that test.

    Reading is deliberately not symmetric. ``verify()`` accepts an
    envelope with keys this kernel does not know; refusing there would
    reject somebody else's result for carrying their own annotation,
    which is what an open map is for. What is closed is what we emit.
    """
    extensions = result.get("extensions")
    if not isinstance(extensions, dict):
        return
    unknown = sorted(set(extensions) - set(BY_NAME))
    if unknown:
        raise ValueError(
            f"result {result.get('query_id')!r} carries unregistered "
            f"extension block(s) {unknown}; every part of the envelope is "
            f"declared in themis.blocks, so readers can be checked against "
            f"one list instead of against whatever the writer spelled"
        )
