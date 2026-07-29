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
"""
from __future__ import annotations


class Block(str):
    """One named part of the result envelope.

    A ``str`` subclass, so a block is usable wherever its name was: as a
    dict key, in a comparison, through ``json.dumps``. What it adds is
    that the name exists in exactly one place, and that ``holds`` travels
    with it instead of living in whichever docstring happened to describe
    the writer.
    """

    def __new__(cls, name: str, *, holds: str) -> "Block":
        block = super().__new__(cls, name)
        block.holds = holds  # type: ignore[misc]
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


# --- what the identification layer concludes --------------------------------

IDENTIFICATION = Block(
    "identification",
    holds="which pattern the graph was recognised as — back-door, "
          "front-door, Tian — beside the formula it produced",
)
IV_IDENTIFICATION = Block(
    "iv_identification",
    holds="the chosen instrument, the set it is valid conditional on, and "
          "the assumption a Wald ratio rests on",
)
TRANSPORT_IDENTIFICATION = Block(
    "transport_identification",
    holds="the source and target populations, the selection nodes between "
          "them, and the transport formula",
)
JOINT_IDENTIFICATION = Block(
    "joint_identification",
    holds="how a do() over a treatment set was identified, including the "
          "treatment x treatment interaction no sequence of singles recovers",
)
LONGITUDINAL_IDENTIFICATION = Block(
    "longitudinal_identification",
    holds="the time-varying treatment sequence and the g-formula that "
          "identifies it under sequential exchangeability",
)
MEDIATION_DECOMPOSITION = Block(
    "mediation_decomposition",
    holds="natural direct and indirect effects through one mediator, and "
          "their numbers once the numeric end has run",
)
MEDIATION_JOINT_DECOMPOSITION = Block(
    "mediation_joint_decomposition",
    holds="the same decomposition through a mediator SET treated as one "
          "block, which is what makes it identifiable without an ordering",
)
PROXIMAL_ESTIMAND = Block(
    "proximal_estimand",
    holds="the bridge-function estimand proximal identification produces "
          "from two proxies of an unmeasured confounder",
)
CAUSATION_ERROR = Block(
    "causation_error",
    holds="why probabilities of causation were refused — they need binary "
          "treatment and outcome, and the refusal names which was not",
)
COUNTERFACTUAL_ERROR = Block(
    "counterfactual_error",
    holds="why a counterfactual query was refused, in the words of "
          "whatever raised",
)

# --- what the numeric end produces beside the estimate ----------------------

CAUSATION = Block(
    "causation",
    holds="probabilities of necessity and sufficiency, with the "
          "interventional risks they are computed from",
)
COUNTERFACTUAL_CELL = Block(
    "counterfactual_cell",
    holds="one cell of the counterfactual joint distribution, the "
          "attribution layer's finest-grained answer",
)
SCM_COUNTERFACTUAL = Block(
    "scm_counterfactual",
    holds="a point counterfactual under a linear SCM, plus the display "
          "copy of the value the audited estimate must agree with",
)
MECHANISM_AUDIT = Block(
    "mechanism_audit",
    holds="the functional form the number was computed under, and where "
          "that form came from — the estimator's default or the caller",
)
TYPE_RECONCILIATION = Block(
    "type_reconciliation",
    holds="what was checked when the declared variable types and the "
          "data's own types disagreed",
)

# --- what the answer is read with -------------------------------------------

ASSUMPTION_LEDGER = Block(
    "assumption_ledger",
    holds="every load-bearing assumption the answer rests on, ranked by "
          "how the conclusion dies if it is false",
)
LLM_PROPOSED_REVIEW = Block(
    "llm_proposed_review",
    holds="the edges and parameter priors a language model proposed, for "
          "a reader to accept or reject before trusting the number",
)
AMBIGUITIES = Block(
    "ambiguities",
    holds="the upstream naming ambiguities that bear on THIS query, "
          "copied across from the program's own side-channel",
)
SELECTION_RECOVERY = Block(
    "selection_recovery",
    holds="whether the unbiased effect is recoverable from a "
          "selection-restricted sample, and what external data it needs",
)
MISSING_DATA_RECOVERY = Block(
    "missing_data_recovery",
    holds="whether the estimand is recoverable under the declared "
          "missingness mechanism, from the m-graph",
)


ALL: frozenset[Block] = frozenset(
    value for value in tuple(globals().values()) if isinstance(value, Block)
)
"""Every block of the result envelope's extensions map.

Collected from this module rather than listed again below it: a block
declared above and forgotten here would be exactly the drift this module
exists to end.
"""

BY_NAME: dict[str, Block] = {str(block): block for block in ALL}


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
