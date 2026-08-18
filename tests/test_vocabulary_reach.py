"""Which readers a closed vocabulary has to reach, declared once.

A vocabulary is written in one place and restated wherever it has to be
read: a JSON schema that admits the envelope, a prompt an LLM answers
from, a reference table a person opens. Nothing makes a restatement
follow its declaration, so each restatement needs a pin — and pinning
some of them says nothing about the rest.

``tests/test_web_vocabularies.py`` solved that for the browser, and the
shape it used does not carry over. It can ask ``verdict.ts`` "is every
table in this file accounted for", because the file declares its tables
as ``const NAME: Record<...>``. A prompt is prose; it has no declaration
unit to enumerate, so there is nothing to partition. That is why the
browser ended up guarded and the other surfaces did not — the boundary
fell exactly where a surface stopped being enumerable, not where anyone
decided it should.

So this module enumerates the OTHER side. Not "what does this surface
carry" but "what does the kernel declare, and where must each of them
land". Every closed vocabulary in ``themis`` appears below exactly once,
and a new one fails here until it says which readers it reaches — the
same move ``VOCABULARIES`` / ``NOT_VOCABULARIES`` makes for the browser,
one level up.

The browser is not checked here. It has a stronger pin already, and a
weaker duplicate of a stronger check is worth less than nothing: it
reads as coverage while admitting what the real one rejects.
"""
from __future__ import annotations

import enum
import importlib
import json
import pathlib
import pkgutil

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"


# --- the kernel side ---------------------------------------------------------

def _vocabularies() -> dict[str, type[enum.Enum]]:
    """Every closed vocabulary the package declares, keyed by dotted name.

    Found by importing the package and walking ``Enum``'s subclasses
    rather than by reading the source for a list of base names: the
    registries here inherit through ``EnvelopeName`` and a source scan
    for ``StrEnum`` misses all of them, which is the failure this module
    exists to make impossible.

    Members-less classes are the marker bases themselves and are skipped;
    they declare no vocabulary, they declare how one behaves.
    """
    import themis

    for mod in pkgutil.walk_packages(themis.__path__, "themis."):
        if "web.frontend" in mod.name:
            continue
        try:
            importlib.import_module(mod.name)
        except ImportError:
            continue

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return {
        f"{cls.__module__}.{cls.__qualname__}": cls
        for cls in walk(enum.Enum)
        if cls.__module__.startswith("themis") and len(cls) > 0
    }


# --- the schema side ---------------------------------------------------------
#
# An enum site is named by the path to it, so the check is equality with
# THAT site rather than membership in the file's union. Both directions
# matter: a value the schema states and the kernel never emits reads as a
# case somebody handled.

#: Vocabulary -> the enum sites whose UNION must be exactly its members.
#:
#: A tuple because one vocabulary can be carried by more than one
#: container, each holding a different subset — the licences a
#: counterfactual cell may declare are not the ones a causation block
#: may, because the admissible set depends on the rule that wrote it.
#: Equality against either site alone would pass while half the
#: vocabulary went unstated.
STATED_BY_SCHEMA: dict[str, tuple[tuple[str, ...], ...]] = {
    "themis.kb.schemas.KBConfidenceGrade": (
        ("kb_result.schema.json", "$defs", "kbProvenance", "properties",
         "confidence_grade"),
    ),
    "themis.kb.schemas.KBQueryKind": (
        ("kb_query.schema.json", "properties", "query_kind"),
    ),
    "themis.ledger.Layer": (
        ("query_result.schema.json", "properties", "extensions", "properties",
         "assumption_ledger", "properties", "assumptions", "items",
         "properties", "layer"),
    ),
    "themis.ledger.Provenance": (
        ("query_result.schema.json", "properties", "extensions", "properties",
         "assumption_ledger", "properties", "assumptions", "items",
         "properties", "provenance"),
    ),
    "themis.ledger.Severity": (
        ("query_result.schema.json", "properties", "extensions", "properties",
         "assumption_ledger", "properties", "assumptions", "items",
         "properties", "severity"),
    ),
    "themis.refusals.Kind": (
        ("query_result.schema.json", "properties", "estimator_failure",
         "properties", "kind"),
    ),
    "themis.refusals.Refusal": (
        ("query_result.schema.json", "properties", "estimator_failure",
         "properties", "failure_type"),
    ),
    "themis.risk_provenance.RiskProvenance": (
        ("query_result.schema.json", "properties", "numeric_estimate",
         "properties", "counterfactual_cell", "properties",
         "interventional_risk_provenance"),
        ("query_result.schema.json", "properties", "extensions", "properties",
         "causation", "properties", "interventional_risk_provenance"),
    ),
    "themis.types.AnswerTier": (
        ("query_result.schema.json", "$defs", "dataGapReport", "properties",
         "answer_tier"),
    ),
    "themis.types.BoundsMethod": (
        ("query_result.schema.json", "$defs", "boundsResult", "properties",
         "method"),
    ),
    "themis.types.GapBlocks": (
        ("query_result.schema.json", "$defs", "dataGap", "properties",
         "blocks"),
    ),
    "themis.types.GapKind": (
        ("query_result.schema.json", "$defs", "dataGap", "properties", "kind"),
    ),
    "themis.types.GapRefKind": (
        ("query_result.schema.json", "$defs", "dataGap", "properties",
         "provenance", "items", "properties", "ref_kind"),
    ),
    "themis.types.GapSeverity": (
        ("query_result.schema.json", "$defs", "dataGap", "properties",
         "severity"),
    ),
    "themis.types.InvestigationAction": (
        ("query_result.schema.json", "$defs", "investigationRequest",
         "properties", "action"),
    ),
    "themis.types.MissingKind": (
        ("query_result.schema.json", "$defs", "missingItem", "properties",
         "kind"),
    ),
    "themis.types.Monotonicity": (
        ("kernel_ast.schema.json", "$defs", "effectQuery", "properties",
         "assumptions", "properties", "monotonicity"),
    ),
    "themis.types.Priority": (
        ("query_result.schema.json", "$defs", "missingItem", "properties",
         "priority"),
    ),
    "themis.types.QueryKind": (
        ("query_result.schema.json", "properties", "query_kind"),
    ),
    "themis.types.RequiredDataType": (
        ("query_result.schema.json", "$defs", "dataGap", "properties",
         "required_data", "properties", "data_type"),
    ),
    "themis.types.ResultStatus": (
        ("query_result.schema.json", "properties", "status"),
    ),
}

#: Vocabulary -> why no schema states it. Each of these reaches a reader
#: by some other route or by none, and saying which is the point: an
#: entry here is a claim, not an exemption.
NOT_ON_THE_ENVELOPE: dict[str, str] = {
    "themis.audits.Artifact": (
        "The vocabulary of what an audit is an audit OF, which reaches a "
        "reader through ``themis.audit``'s own output rather than through a "
        "result envelope. Its members are verbatim the ``kind`` their "
        "artifacts carry, so the artifacts' own schemas state them; "
        "query_result.schema.json has no field for it, because an envelope "
        "does not say what kind of dict it is."
    ),
    "themis.estimation.strategy.Estimand": (
        "What a strategy row's number is an estimate of, used to decide "
        "whether one row may answer another's query. It is a fact about the "
        "TABLE, not about any one result: the envelope says which method ran "
        "and what it produced, and a reader who wants the estimand reads the "
        "method. Only ``arm_probability`` reaches the envelope, as "
        "bounds_results[].estimand, which is a one-member enum with its own "
        "anchor in the browser pin."
    ),
    "themis.estimation.strategy.Role": (
        "Whether a strategy row claims the answer or annotates someone "
        "else's. A property of the row, consumed entirely inside the "
        "cascade; no reader is ever handed one."
    ),
    "themis.routing.End": (
        "Which of the two implementations a strategy has — identification "
        "or numeric. Internal to routing; the envelope reports what was "
        "derived and what was computed, never which end of the table did it."
    ),
}


def _at(site: tuple[str, ...]) -> set[str]:
    node = json.loads((SCHEMAS / site[0]).read_text(encoding="utf-8"))
    for step in site[1:]:
        node = node[step]
    return {str(v) for v in node["enum"]}


# --- the prose side ----------------------------------------------------------
#
# A prompt or a reference table has no structure to compare against, so
# what can be asked of it is that it names each member. Backticked, which
# is how all three cite one, and which is what separates naming the kind
# from happening to use the words in a sentence.

#: A derived set, not a whole vocabulary: what has to reach a surface is
#: sometimes a subset, and the subset has to be a declared one. A list
#: written out by hand in the test is drawn from what the surface already
#: says, so it holds the surface against itself — which is how the group
#: below lost two of its six members and nothing failed.
SUBSETS = {
    "themis.types.MIRRORED_INTO_EXPLANATION",
    "themis.types.REACHES_EXPLANATION",
}

#: (what must be named, why this surface needs it, the surfaces).
NAMED_IN_PROSE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "themis.types.GapKind",
        "every gap kind has a row a person can read",
        ("docs/GAP_KINDS_REFERENCE.md",),
    ),
    (
        "themis.types.MIRRORED_INTO_EXPLANATION",
        "the renderer has to know which caveats are already prepended to "
        "explanation, or it says them a second time",
        ("themis/prompts/response_rendering.md",),
    ),
    (
        "themis.types.REACHES_EXPLANATION",
        "the orchestrator pre-screens every kind that reaches explanation, "
        "and one with no rule is one it has to improvise about — mirrored "
        "or estimator-time makes no difference from there",
        ("themis/prompts/gap_to_action.md",),
    ),
)


def _members(name: str) -> set[str]:
    if name in SUBSETS:
        import themis.types
        return {k.value for k in getattr(themis.types, name.rsplit(".", 1)[1])}
    return {str(m.value) for m in _vocabularies()[name]}


# --- the checks --------------------------------------------------------------

def _unaccounted(declared: set[str], stated: set[str], excused: set[str]):
    """The three ways the two tables and the package can disagree."""
    return (
        sorted(declared - (stated | excused)),   # said nothing about itself
        sorted((stated | excused) - declared),   # a row for something gone
        sorted(stated & excused),                # said both things
    )


def test_every_vocabulary_says_whether_the_envelope_carries_it():
    """The partition. Adding a closed vocabulary fails here until it says.

    All three directions: a vocabulary with no row is the failure this
    module exists for; a row for a vocabulary the package no longer
    declares is a check on nothing, which is how a table starts
    describing a repository that has moved on.
    """
    silent, stale, both = _unaccounted(
        set(_vocabularies()), set(STATED_BY_SCHEMA), set(NOT_ON_THE_ENVELOPE))
    assert not silent, (
        f"{silent} are closed vocabularies that have not said which readers "
        f"they reach; add them to STATED_BY_SCHEMA with their enum site, or "
        f"to NOT_ON_THE_ENVELOPE with the reason"
    )
    assert not stale, f"{stale} are named here and no longer declared"
    assert not both, f"{both} say both things about themselves"


def test_a_vocabulary_that_says_nothing_about_itself_is_caught():
    """The counterexample. Without it the partition could hold vacuously —
    an ``accounted`` set built from ``declared`` would pass forever."""
    assert _unaccounted({"a", "b"}, {"a"}, set()) == (["b"], [], [])
    assert _unaccounted({"a"}, {"a"}, {"gone"}) == ([], ["gone"], [])
    assert _unaccounted({"a"}, {"a"}, {"a"}) == ([], [], ["a"])


@pytest.mark.parametrize("name", sorted(STATED_BY_SCHEMA))
def test_the_declared_sites_state_exactly_the_vocabulary(name):
    """Union over the declared sites, equal to the members.

    Equality rather than containment, because a value the schema admits
    and the kernel never emits is a case a reader believes was handled.
    """
    stated: set[str] = set()
    for site in STATED_BY_SCHEMA[name]:
        stated |= _at(site)
    members = _members(name)
    assert stated == members, (
        f"{name}: the schema states {sorted(stated - members)} which the "
        f"kernel does not emit, and omits {sorted(members - stated)}"
    )


@pytest.mark.parametrize(
    "name,why,surface",
    [(n, w, s) for n, w, files in NAMED_IN_PROSE for s in files],
)
def test_the_prose_surface_names_every_member(name, why, surface):
    """Backticked containment — the whole of what prose admits being asked."""
    text = (REPO / surface).read_text(encoding="utf-8")
    missing = sorted(m for m in _members(name) if f"`{m}`" not in text)
    assert not missing, f"{surface} does not name {missing} — {why}"


def test_a_vocabulary_the_schema_states_incompletely_is_caught():
    """The counterexample, without which the checks above could be vacuous.

    Reads a real site and drops a member from the comparison, so what is
    exercised is the equality itself rather than a hand-written pair.
    """
    site = STATED_BY_SCHEMA["themis.types.GapSeverity"][0]
    stated = _at(site)
    assert stated == _members("themis.types.GapSeverity")
    assert (stated - {next(iter(stated))}) != _members("themis.types.GapSeverity")
