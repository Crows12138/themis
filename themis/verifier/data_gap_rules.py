"""Phase 10 §10.4 — independent verification of DataGapReport.

Seven rules audit a generated DataGapReport for honesty:

- **T10-1 ``data_gap_provenance_check``** — every ref in every gap's
  provenance array must point at something that is there. What "there"
  means is the ref's own ``ref_kind``, which is why the kind is what makes
  the question askable at all: a derivation step, an investigation
  request, a framing note, a path into this answer, a place in the
  program, or a check this build ran. The last of those points at no
  artifact, so what resolves it is the contract: the check has to be one
  the gap's species declares, and its subject has to be a name that gap
  says it is about or a column the answer stood on.
- **T10-2 ``data_gap_completeness_check``** — every upstream failure
  signal that the schema can detect (failed derivation step / parameter
  investigation / framing note) must be covered by at least one gap.
  And the proposed edges an answer rests on, read on the ground graph it
  was reached on, must be exactly the edges its proposal-edge gaps
  disclose. And the caveats that say the sample is restricted on a
  collider, read on that graph with its bidirected edges, must be exactly
  the ones the answer owes.
- **T10-3 ``data_gap_kind_consistency_check``** — each gap's ``kind`` must
  be coherent with the upstream signal it cites in provenance: every ref
  must point into a space the species declares, at least one must be
  there, and a gap labelled ``unidentifiable_no_admissible_set`` or
  ``missing_iv_candidate`` citing a ``derivation_step`` must reference a
  step that actually failed rather than a successful identification. The
  first of those is the direction nobody asked until #618 — the table was
  read for whether a gap carried AT LEAST ONE acceptable ref, so anything
  could ride along beside one that was.
- **T10-5 ``data_gap_species_check``** — each gap's ``severity`` and
  ``blocks`` must be what its species declares. The few species whose
  value is an occasion's say so in code, and this rule is silent on
  exactly those.
- **T10-6 ``data_gap_required_data_check``** — the shape of data a gap
  asks for must be one its species asks for, and for the one species
  whose shape is an occasion's, the one the statement it was filed for
  needs. That statement is on the item the gap cites, so the ``signature``
  and the ``data_type`` are both held to a second record rather than to
  each other.
- **T10-7 ``data_gap_route_check``** — every way past a gap must be one
  its species declares. What a reader acts on had 84 authors and three
  declarations; the ceiling this holds it to is the species', so two ways
  past of the SAME species stay interchangeable and nothing else does.
- **T10-8 ``data_gap_sentence_check``** — every statement a gap makes
  about itself must be one its species declares. The field a reader reads
  first was typed at 78 sites out of a vocabulary of 88 and declared
  nowhere; a species says between one and ten of them.

**Independence pin:** This module MUST NOT import from
``themis.output.data_gap_report`` or any generator-side module. The audit
is a re-implementation of the failure / coverage logic from scratch so
that bugs in the generator cannot mask themselves in the verifier. A
test in ``tests/test_verifier/test_data_gap_rules.py`` line-scans this
file to enforce the rule.

Reads only from the JSON envelope (dicts), not from typed dataclasses,
so the audit also catches serialization-layer bugs. The exception is the
contract layer's declarations in :mod:`themis.types`, which are not
anything a producer wrote — they are what the words in the envelope mean.
Which edges an answer rests on, and which restrictions are on a collider,
are read from its premises as well: the
program parsed from the caller's own document and the graph projected
from it, which no producer wrote either.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

import networkx as nx

from .. import gaps as _gaps
from .. import language
from ..types import (
    Atom,
    BLOCKS_OF,
    BLOCKS_TURN_ON,
    BidirectedStatement,
    CauseStatement,
    DATA_TYPE_TURNS_ON,
    EffectQuery,
    GapKind,
    GapSeverity,
    NO_SUBJECT,
    ObservationStatement,
    REF_KINDS_OF,
    SEVERITY_OF,
    SEVERITY_TURNS_ON,
    VarTerm,
    atoms_held_by,
    raised_by,
    required_data_type,
)
from .context import VerificationContext
from .errors import VerificationError
from .program_copy_rules import query_of
from .rules import (
    _verifier_build_admg_multigraph,
    _verifier_directed_descendants,
    _verifier_has_arrowhead_at,
)

#: The severity that lets the generic pointer at a computed interval lead a
#: gap, spelled as it travels — see :func:`themis.gaps.ways_past`.
_BLOCKING = GapSeverity.BLOCKING.value


# ============================================ failure detection
#
# The verifier maintains its OWN list of rule names that indicate
# structural failure. It used to be pointed out that this was not
# imported from themis.output.data_gap_report, because bugs in one must
# not hide bugs in the other. There is nothing there to import any more:
# the kernel writes only steps that succeeded, so the producer's copy was
# removed and this one is the last.
#
# It stays because the two sides read different things. The producer
# reads a derivation the kernel just built; this reads one somebody else
# submitted, which may claim a failure no producer would write — and
# recognising that claim is the precondition for checking it.
_VERIFIER_FAILURE_RULE_NAMES: frozenset[str] = frozenset({
    "unidentifiable_via_backdoor",
    "unidentifiable_via_front_door",
    "unidentifiable_via_iv",
    "unidentifiable_via_mediation",
    "unidentifiable_via_transport",
})


def _step_failed(step: dict) -> bool:
    """A step represents structural failure when (a) it explicitly carries
    success=False or (b) its rule name is in the verifier's independent
    failure list."""
    if step.get("success") is False:
        return True
    return step.get("rule") in _VERIFIER_FAILURE_RULE_NAMES


def _step_id_or_rule(step: dict) -> str:
    """Stable identifier for matching provenance refs back to a step."""
    sid = step.get("step_id")
    if sid:
        return sid
    return step.get("rule", "")


# ============================================ T10-1 provenance resolution


def _verify_t10_1_provenance(
    report: dict,
    *,
    derivation_steps: list[dict],
    investigation_requests: list[dict],
    framing_notes: list[dict],
    envelope: dict | None = None,
) -> None:
    """T10-1: every gap.provenance[i].ref_id must resolve where its kind says.

    ``envelope`` is the answer the report came on, needed by the arm that
    follows a path into it. Absent, that arm refuses rather than falls
    silent — the same choice the derivation arm already makes when it is
    handed no chain, and for the same reason: an audit that cannot look is
    not an audit that saw nothing wrong.
    """
    derivation_ids = set()
    for step in derivation_steps:
        derivation_ids.add(_step_id_or_rule(step))
        # Some generators may also use the rule name; accept that too.
        rule = step.get("rule")
        if rule:
            derivation_ids.add(rule)

    investigation_ids: set[str] = set()
    for req in investigation_requests:
        target = req.get("target")
        if target:
            investigation_ids.add(target)
        for item in req.get("items", []) or []:
            it_target = item.get("target")
            if it_target:
                investigation_ids.add(it_target)

    framing_ids = {n.get("predicate") for n in framing_notes if n.get("predicate")}

    for gap_index, gap in enumerate(report.get("gaps", [])):
        for ref_index, ref in enumerate(gap.get("provenance", []) or []):
            ref_kind = ref.get("ref_kind")
            ref_id = ref.get("ref_id")
            if ref_kind == "derivation_step":
                if ref_id not in derivation_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites derivation_step={ref_id!r} which does not "
                        f"appear in the derivation chain",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "investigation_request":
                if ref_id not in investigation_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites investigation_request={ref_id!r} which does "
                        f"not appear in result.investigation_requests",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "framing_note":
                if ref_id not in framing_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites framing_note={ref_id!r} which does not "
                        f"appear in result.framing_notes",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "envelope_path":
                if envelope is None:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites envelope_path={ref_id!r} and this audit was "
                        f"handed no answer to follow it on",
                        step_index=None, rule="data_gap_provenance_check",
                    )
                found, why = _at_path(envelope, ref_id)
                if not found:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites envelope_path={ref_id!r} which this answer "
                        f"does not carry: {why}",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "program_site":
                # The declared range, and the reason is the door rather than
                # the ref: this audit is result-only by contract, so the
                # program a site would be found in is not here to look in.
                # Naming the space is still worth doing — it is what stops a
                # program site from being spelled as a path into the answer,
                # which is how one of these came to name a block that was
                # never on the envelope.
                if not isinstance(ref_id, str) or not ref_id:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"program_site ref_id must be a non-empty string",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "verifier_check":
                # A check, not an artifact: what this names is something
                # this build DID, and the run is over — so what can be
                # asked is not "is it still there" but "is it one this
                # build runs, about something this gap is about".
                if not isinstance(ref_id, str) or not ref_id:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"verifier_check ref_id must be a non-empty string",
                        step_index=None, rule="data_gap_provenance_check",
                    )
                check, _, subject = ref_id.partition(":")
                declared = _checks_of(gap.get("kind"))
                if check not in declared:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"says check={check!r} raised a "
                        f"{gap.get('kind')!r}, which declares "
                        + (f"{sorted(declared)}" if declared
                           else "no check at all"),
                        step_index=None, rule="data_gap_provenance_check",
                    )
                if subject and envelope is None:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"says check={check!r} ran about {subject!r} and "
                        f"this audit was handed no answer to look for it in",
                        step_index=None, rule="data_gap_provenance_check",
                    )
                names = _subject_names(subject)
                about = _about(gap, envelope or {}) if names else frozenset()
                for name in names:
                    if name not in about:
                        raise VerificationError(
                            f"T10-1: gap[{gap_index}]."
                            f"provenance[{ref_index}] says check={check!r} "
                            f"ran about {name!r}, which is not a name this "
                            f"gap is about and not a column this answer "
                            f"stood on",
                            step_index=None,
                            rule="data_gap_provenance_check",
                        )
            else:
                raise VerificationError(
                    f"T10-1: gap[{gap_index}].provenance[{ref_index}] has "
                    f"unknown ref_kind={ref_kind!r}",
                    step_index=None, rule="data_gap_provenance_check",
                )


def _checks_of(species: object) -> frozenset[str]:
    """What the contract says can raise this species.

    An unknown species name gets the empty set and its ref is refused,
    which is the same answer the declaration gives for a species that
    raises no named check — in both cases nothing states that this check
    belongs to this gap, and that is the whole question.
    """
    if not isinstance(species, str):
        return frozenset()
    try:
        return raised_by(GapKind(species))
    except ValueError:
        return frozenset()


#: The names inside a check's subject. Whatever a producer joins them with
#: — a pipe, a comma, an arrow — is not a name character, so this reads the
#: names without presuming the punctuation, which is the producer's to
#: choose and not a second grammar for this side to keep in step.
_SUBJECT_NAME = re.compile(r"[^\W\d][\w.]*")


def _subject_names(subject: str) -> list[str]:
    """Every variable a check says it ran about."""
    return _SUBJECT_NAME.findall(subject.replace(NO_SUBJECT, " "))


def _about(gap: dict, envelope: Mapping) -> set[str]:
    """Every name this gap says it is about, and the columns it stood on.

    Two sources because a check has two kinds of subject. Most name a
    variable the gap's own sentences already name — the intervention whose
    versions are ill-defined, the predicate whose declaration the data
    contradict — and holding the ref to the sentence beside it is what
    makes a forged subject visible. The rest name a column the estimator
    adjusted on, which the gap's sentence renders as prose rather than as
    a name; those are taken from the estimation context, which is the
    answer's own record of what it stood on.

    The range, stated rather than left to be found: this resolves a ref,
    it does not audit whether the producer picked the right variable. The
    sentence and the ref are written at one site, so a site wrong in both
    the same way passes — which is the range every arm of T10-1 has, since
    a derivation_step ref resolves against a chain the same kernel wrote.
    The columns are the half of this pool that is not the producer's, and
    what is pinned is that the ref and the sentence beside it name one
    variable: editing either alone is refused.
    """
    names: set[str] = set()

    def collect(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
        elif isinstance(node, str):
            names.add(node)

    collect(gap.get("said") or {})
    for said in gap.get("describes") or []:
        collect((said or {}).get("said") or {})
    for path in gap.get("alternative_paths") or []:
        collect((path or {}).get("said") or {})
    context = envelope.get("estimation_context") or {}
    if isinstance(context, Mapping):
        names.update(
            column for column in context.get("data_columns") or []
            if isinstance(column, str)
        )
    return names


#: One step of a gap's envelope path: a key, and optionally a pick from what
#: that key holds.
_PATH_STEP = re.compile(r"([^.\[\]]+)(?:\[([^\]]*)\])?")

#: A pick that names a position rather than a kind. ``#`` and then digits
#: and nothing else, so a caller whose ambiguity is of kind ``0`` is still
#: reachable by kind and only one spelling can ever mean the position.
_AT_INDEX = re.compile(r"#(\d+)")


def _at_path(envelope: dict, path: object) -> tuple[bool, str]:
    """Whether a gap's envelope path lands on something, and why not.

    Dotted keys from the answer's root. ``[x]`` picks from what the key
    holds: on a list, the entry whose ``kind`` is ``x`` — which is how a
    report names one member of a block that carries several — and on a
    mapping, the key ``x``. ``[#n]`` picks the n-th entry of a list
    instead, counting from zero.

    **Why a list has two ways to be picked from.** By ``kind`` is an
    address only where kind is unique in that list, and the one block
    this repository addresses by kind is the one block the contract
    leaves open — where nothing says a caller may not flag two
    uncertainties of a kind, and one did. Two entries differing in every
    other field were cited by one path that named neither. Where a list
    is open, an entry's identity is where it is.

    Spelled here rather than imported because this file may not read the
    generator, and a path is followed the same way whoever wrote it.
    """
    if not isinstance(path, str) or not path:
        return False, "the path is empty"
    node: object = envelope
    for part in path.split("."):
        step = _PATH_STEP.fullmatch(part)
        if step is None:
            return False, f"{part!r} is not a step"
        key, pick = step.group(1), step.group(2)
        if not isinstance(node, dict) or key not in node:
            return False, f"nothing named {key!r} there"
        node = node[key]
        if pick is None:
            continue
        if isinstance(node, list):
            at = _AT_INDEX.fullmatch(pick)
            if at is not None:
                index = int(at.group(1))
                if index >= len(node):
                    return False, (f"{key!r} has {len(node)} entries, so "
                                   f"there is no {pick!r}")
                node = node[index]
                continue
            found = next((e for e in node if isinstance(e, dict)
                          and e.get("kind") == pick), None)
            if found is None:
                return False, f"no entry of {key!r} has kind {pick!r}"
            node = found
        elif isinstance(node, dict):
            if pick not in node:
                return False, f"{key!r} has no {pick!r}"
            node = node[pick]
        else:
            return False, f"{key!r} holds nothing to pick from"
    return True, ""


# ============================================ T10-1, the other document
#
# A ``program_site`` ref makes the same claim an ``envelope_path`` ref does
# — "what this gap says comes from THERE" — about the other document. The
# envelope half is followed above and refused where it lands on nothing.
# The program half was the same claim with nothing behind it: the audit
# that reads a report is result-only by contract, so the program a site
# would be found in is not there to look in, and that was written down as
# the reason rather than as a place the check still had to go. It goes
# where the program already is, beside the other rules in ``verify`` that
# ask the problem rather than the answer, and it raises under T10-1's own
# rule name because it is T10-1's other half rather than a rule of its own.


def _statements_of(program: Mapping, kind: str):
    for statement in program.get("statements") or ():
        if isinstance(statement, Mapping) and statement.get("kind") == kind:
            yield statement


def _predicate(end: object) -> object:
    return end.get("predicate") if isinstance(end, Mapping) else None


#: What each kind of edge calls its two ends, and whether swapping them
#: names the same edge. A directed edge is its direction; a bidirected one
#: is a pair, so a ref that spells the pair the other way round names the
#: same statement and refusing it would refuse an honest report.
_THE_ENDS_OF: dict[str, tuple[str, str, bool]] = {
    "cause": ("from", "to", False),
    "bidirected": ("left", "right", True),
}


def _an_edge_with_a_source(program: Mapping, kind: str, spelling: str,
                           arrow: str) -> tuple[bool, str]:
    """An edge of this shape, carrying the annotation the ref names."""
    if arrow not in spelling:
        return False, f"{spelling!r} does not name two ends"
    first, second = spelling.split(arrow, 1)
    one, other, either_way = _THE_ENDS_OF[kind]
    seen = False
    for statement in _statements_of(program, kind):
        ends = (_predicate(statement.get(one)),
                _predicate(statement.get(other)))
        if ends != (first, second) and not (
                either_way and ends == (second, first)):
            continue
        seen = True
        annotations = statement.get("annotations")
        if isinstance(annotations, Mapping) and "source" in annotations:
            return True, ""
    if not seen:
        return False, (f"the program declares no {kind} edge between "
                       f"{first!r} and {second!r}")
    return False, f"that {kind} edge carries no annotations.source"


def _a_variable_field_containing(program: Mapping, rest: str
                                 ) -> tuple[bool, str]:
    """``<predicate>:<field>:contains:<needle>``, read off the declaration."""
    parts = rest.split(":", 2)
    if len(parts) != 3 or not parts[2].startswith("contains:"):
        return False, f"{rest!r} is not a field of a variable"
    predicate, field, needle = parts[0], parts[1], parts[2][len("contains:"):]
    for statement in _statements_of(program, "variable"):
        if statement.get("predicate") != predicate:
            continue
        value = statement.get(field)
        if isinstance(value, str) and needle in value:
            return True, ""
        return False, (f"variable {predicate!r} has no {field!r} saying "
                       f"{needle!r}")
    return False, f"the program declares no variable {predicate!r}"


def _a_variable_threshold(program: Mapping, rest: str) -> tuple[bool, str]:
    predicate, _, cut = rest.partition(":")
    if not cut.startswith("threshold:"):
        return False, f"{rest!r} is not a threshold on a variable"
    wanted = cut[len("threshold:"):]
    for statement in _statements_of(program, "variable"):
        if statement.get("predicate") != predicate:
            continue
        if statement.get("threshold") == wanted:
            return True, ""
        return False, (f"variable {predicate!r} declares no threshold "
                       f"{wanted!r}")
    return False, f"the program declares no variable {predicate!r}"


def _how_many_unmeasured_confounders(program: Mapping) -> int:
    return sum(1 for _ in _statements_of(program, "bidirected"))


def _under_the_programs_extensions(program: Mapping, path: str
                                   ) -> tuple[bool, str]:
    """A dotted place under the program's own extensions.

    Not :func:`_at_path`, and the difference is the document rather than
    the walk. There a member of a list is picked with ``key[kind]``; here
    a site is spelled in dots throughout, so a segment naming no key is
    read as the KIND of a member of the list the last key held — which is
    how a program says which of its declared ambiguities a gap came from.
    Widening the envelope walk to accept that would make the envelope half
    accept paths that do not exist there, and the two documents are not
    obliged to be spelled the same way.
    """
    node: object = program
    for segment in path.split("."):
        if isinstance(node, Mapping) and segment in node:
            node = node[segment]
            continue
        if isinstance(node, list):
            member = next((entry for entry in node
                           if isinstance(entry, Mapping)
                           and entry.get("kind") == segment), None)
            if member is not None:
                node = member
                continue
            return False, f"no entry there has kind {segment!r}"
        return False, f"nothing named {segment!r} there"
    return True, ""


def _resolve_program_site(program: Mapping, ref_id: str) -> tuple[bool, str]:
    """Whether a cited program site is one this program has.

    Seven spellings, and they divide into three questions rather than
    seven. A site names an EDGE and the annotation it carries; or a
    VARIABLE and a field of its declaration; or a place under the
    program's own extensions, followed the way an envelope path is. And
    two of them name no site at all but a SHAPE the program is in — one
    saying it declares an unmeasured confounder and one saying it declares
    none, which are the two sides of a single question about the same
    statements, and both are answered by counting them.

    An unknown spelling is refused rather than passed. A ref nothing can
    follow is the state this whole rule exists to end, and letting one
    through in silence would rebuild it one spelling at a time.
    """
    if ref_id == "program:confounder_pattern:no_bidirected":
        found = _how_many_unmeasured_confounders(program)
        if found:
            return False, (f"the program declares {found} bidirected "
                           f"edge(s), so this is not a graph with no "
                           f"unmeasured confounding")
        return True, ""
    if ref_id == "program:front_door_pattern":
        if not _how_many_unmeasured_confounders(program):
            return False, ("the program declares no bidirected edge, and a "
                           "front-door reading is what a graph with "
                           "unmeasured confounding needs")
        return True, ""
    if ref_id.startswith("program:cause:"):
        return _an_edge_with_a_source(
            program, "cause",
            ref_id[len("program:cause:"):].removesuffix(":annotations.source"),
            "->")
    if ref_id.startswith("program:bidirected:"):
        return _an_edge_with_a_source(
            program, "bidirected",
            ref_id[len("program:bidirected:"):].removesuffix(
                ":annotations.source"),
            "↔")
    if ref_id.startswith("program:variable:"):
        rest = ref_id[len("program:variable:"):]
        if ":threshold:" in rest:
            return _a_variable_threshold(program, rest)
        return _a_variable_field_containing(program, rest)
    if ref_id.startswith("program:extensions."):
        return _under_the_programs_extensions(
            program, ref_id[len("program:"):])
    return False, "no site of the program is spelled this way"


#: The one cited site that is not one. A dispatch conflict names which
#: layer answered and which was skipped, which is a fact about this RUN
#: and not about the problem — so following it into the program is
#: impossible, and refusing it would refuse an honest answer. Exempted
#: here rather than resolved, because what is wrong there is the ref's
#: KIND rather than the ref, and moving a kind moves the contract.
_NOT_A_PROGRAM_SITE_AT_ALL = "query:"


def verify_gap_program_sites(result: object, program: object) -> None:
    """T10-1's other half: a cited program site, found in the program.

    The program is the caller's own document rather than anything parsed
    out of it, and a caller handing over something else is refused rather
    than skipped: a rule that returns quietly on an argument it does not
    recognise reads as a rule that ran, which is how the first draft of
    this one passed every forgery while being wired to a typed object.
    """
    if not isinstance(program, Mapping):
        raise TypeError(
            "verify_gap_program_sites needs the program document itself; "
            f"got {type(program).__name__}")
    if not isinstance(result, Mapping):
        return
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    for gap_index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, Mapping):
            continue
        for ref_index, ref in enumerate(gap.get("provenance") or ()):
            if not isinstance(ref, Mapping):
                continue
            if ref.get("ref_kind") != "program_site":
                continue
            ref_id = ref.get("ref_id")
            if not isinstance(ref_id, str):
                continue
            if ref_id.startswith(_NOT_A_PROGRAM_SITE_AT_ALL):
                continue
            found, why = _resolve_program_site(program, ref_id)
            if not found:
                raise VerificationError(
                    f"T10-1: gap[{gap_index}].provenance[{ref_index}] cites "
                    f"program_site={ref_id!r} which this problem does not "
                    f"have: {why}",
                    step_index=None, rule="data_gap_provenance_check",
                )


# ============================================ T10-1, what the cited edge says
#
# A proposal-edge gap cites the annotation that flagged its edge, and the
# rule above finds that annotation in the program. What the gap then TELLS a
# reader is that statement read aloud, and nothing held the reading to the
# statement: the site is named after ``annotations.source`` and the one
# question asked of that field was whether it is there.

#: The species whose statements are a reading of the edge it cites.
_READS_ITS_CITED_EDGE = GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH.value

#: Per kind of edge: how a program site spells it, the arrow between its two
#: ends there, and the arrow a sentence names it with.
_EDGE_SITES: dict[str, tuple[str, str, str]] = {
    "cause": ("program:cause:", "->", "→"),
    "bidirected": ("program:bidirected:", "↔", "↔"),
}

#: The source a discovery algorithm's edge carries, up to the algorithm's
#: name. Spelled as the program spells it, and restated rather than imported
#: for this module's independence pin — ``orientation_ledger_rules`` reads
#: the same marker the same way.
_LEARNED_BY = "discovery:"


def _the_statements_cited(program: Mapping, ref_id: str) -> list:
    """``(kind, (first, second), annotations)`` of every statement a site
    names and whose source it cites, empty when the site names none.

    Every one, not the first: a site names an edge by its predicates, and
    several statements can be spelt that way -- an edge stated twice, or
    written at two times or for two units."""
    for kind, (prefix, arrow, _named) in _EDGE_SITES.items():
        if not ref_id.startswith(prefix):
            continue
        spelling = ref_id[len(prefix):].removesuffix(":annotations.source")
        if arrow not in spelling:
            return []
        first, second = spelling.split(arrow, 1)
        one, other, either_way = _THE_ENDS_OF[kind]
        cited = []
        for statement in _statements_of(program, kind):
            ends = (_predicate(statement.get(one)),
                    _predicate(statement.get(other)))
            annotations = statement.get("annotations")
            if (ends == (first, second)
                    or (either_way and ends == (second, first))) and (
                    isinstance(annotations, Mapping)
                    and "source" in annotations):
                cited.append((kind, (first, second), annotations))
        return cited
    return []


def _what_the_edge_says(kind: str, ends: tuple, annotations: Mapping) -> list:
    """The statements a proposal-edge gap owes, read off the edge it cites.

    The edge, named with its kind's arrow. Whether a language model proposed
    it or an algorithm learned it, which is whether the source is a
    discovery marker; the algorithm, which is the rest of that source. And
    where the run recorded how often the edge survived resampling, that
    share, as a whole percent.
    """
    edge = f" {_EDGE_SITES[kind][2]} ".join(ends)
    source = str(annotations.get("source") or "")
    if not source.startswith(_LEARNED_BY):
        return [{"sentence": "the_edge_is_an_llm_proposal",
                 "said": {"edge": edge}}]
    owed = [{"sentence": "the_edge_was_learned_by_discovery",
             "said": {"edge": edge,
                      "algorithm": source[len(_LEARNED_BY):].upper()}}]
    share = annotations.get("confidence")
    if isinstance(share, (int, float)) and not isinstance(share, bool):
        owed.append({"sentence": "the_edge_survived_this_share_of_resamples",
                     "said": {"confidence": f"{share:.0%}"}})
    return owed


def _the_edge_named(edge: object) -> object:
    """A sentence's edge as the edge it names rather than as text: a directed
    one in its order, a bidirected one as a pair either way round — the
    reading T10-1 already gives a bidirected site."""
    if not isinstance(edge, str):
        return edge
    for arrow, ordered in (("→", True), ("↔", False)):
        if arrow in edge:
            ends = tuple(part.strip() for part in edge.split(arrow, 1))
            return arrow, (ends if ordered else tuple(sorted(ends)))
    return edge


def _as_read(describes) -> list:
    out = []
    for statement in describes or ():
        if isinstance(statement, Mapping):
            statement = dict(statement)
            said = statement.get("said")
            if isinstance(said, Mapping) and "edge" in said:
                statement["said"] = {**said,
                                     "edge": _the_edge_named(said["edge"])}
        out.append(statement)
    return out


def verify_gap_edge_statements(result: object, program: object) -> None:
    """What a proposal-edge gap says about its edge, against that edge.

    A gap of this species cites the annotation that flagged its edge, and
    :func:`verify_gap_program_sites` finds it in the program. Everything the
    gap then tells a reader is that statement: the edge, in its direction;
    whether a language model proposed it or an algorithm learned it; which
    algorithm; and how often it survived resampling where a run recorded
    that. A reader decides from those words whether to go and get evidence
    for the edge and how much to trust it meanwhile.

    Measured before this was written. A proposal-edge gap rewritten together
    with the ledger line that copies it passed every door: its edge reversed
    on 19 rows of 19, an LLM proposal told as learned by discovery on 18 of
    18, the reverse on 3 of 3, the algorithm on 3 of 3, the share on 2 of 2.
    And every one of the 21 such gaps in the corpus said exactly what the
    edge it cites says.

    A gap citing no edge, or more than one, is refused rather than skipped:
    its sentences are about one edge, and a reading needs a statement to be
    a reading of. A site names its edge by predicates, so several
    statements can stand behind it -- an edge stated twice, or written at
    two times or for two units -- and what the gap says is held to be what
    one of them says. Which of them the answer rests on, and that every
    reading it rests on is told, needs the graph:
    :func:`verify_proposed_edges_are_disclosed` holds that.
    """
    if not isinstance(program, Mapping):
        raise TypeError(
            "verify_gap_edge_statements needs the program document itself; "
            f"got {type(program).__name__}")
    if not isinstance(result, Mapping):
        return
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    for gap_index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, Mapping) or gap.get(
                "kind") != _READS_ITS_CITED_EDGE:
            continue
        cited: list[str] = []
        for ref in gap.get("provenance") or ():
            if isinstance(ref, Mapping) and ref.get("ref_kind") == "program_site":
                ref_id = ref.get("ref_id")
                if isinstance(ref_id, str):
                    cited.append(ref_id)
        edges = [statements for statements in (
            _the_statements_cited(program, ref_id) for ref_id in cited)
            if statements]
        if len(edges) != 1:
            raise VerificationError(
                f"T10-1: gap[{gap_index}] is about one proposal edge, and the "
                f"edge it cites is {len(edges)} edges of this program "
                f"({cited!r}); what it says about an edge has to be a reading "
                f"of one",
                step_index=None, rule="data_gap_provenance_check",
            )
        readings = [_what_the_edge_says(*statement) for statement in edges[0]]
        if all(_as_read(gap.get("describes")) != _as_read(owed)
               for owed in readings):
            raise VerificationError(
                f"T10-1: gap[{gap_index}] says {gap.get('describes')!r}, and "
                f"the edge it cites, {cited[0]!r}, says "
                f"{' or '.join(repr(owed) for owed in readings)}. A reader "
                f"is told from these words who put the edge there and how "
                f"far to trust it, and the program's own annotation of that "
                f"edge is where the words came from",
                step_index=None, rule="data_gap_provenance_check",
            )


# ============================================ T10-2, the edges an answer rests on
#
# The section above holds what a proposal-edge gap says to the edge it
# cites. This holds which edges have one: a gap is how a reader learns that
# an edge the answer needs was never evidence, and the set of them was
# decided by the report's author alone.

#: The source a language model's edge carries. Restated beside the discovery
#: marker above for the same reason: an edge that carries neither came from
#: somewhere a reader can go and look, and owes no disclosure of this kind.
_PROPOSED_BY_A_MODEL = "llm_proposal"

#: Where a route names atoms its answer rests between beyond those the
#: question holds: the instrument an IV route used and what it conditioned
#: on, and a mediation decomposition's mediators and adjustment sets. Spelled
#: as the envelope spells them; this package does not go through the block
#: registry. The first mediation block present is the one read.
_IV_BLOCK = "iv_identification"
_MEDIATION_BLOCKS = (("mediation_decomposition", "mediator"),
                     ("mediation_joint_decomposition", "mediators"))


def _is_a_proposal(annotations: object) -> bool:
    source = getattr(annotations, "source", None)
    return source == _PROPOSED_BY_A_MODEL or (
        isinstance(source, str) and source.startswith(_LEARNED_BY))


def _spelt_as_the_envelope_spells(atom: Atom) -> str:
    args = ",".join(term.name for term in atom.args)
    base = f"{atom.predicate}({args})"
    if atom.time_index is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def _the_atoms_the_blocks_name(extensions: Mapping) -> list[str]:
    named: list[str] = []
    iv = extensions.get(_IV_BLOCK)
    if isinstance(iv, Mapping):
        if iv.get("instrument"):
            named.append(str(iv["instrument"]))
        named.extend(str(one) for one in iv.get("conditioning") or ())
    for key, field in _MEDIATION_BLOCKS:
        block = extensions.get(key)
        if not isinstance(block, Mapping):
            continue
        mediators = block.get(field)
        named.extend(str(one) for one in (
            mediators if isinstance(mediators, list)
            else ([mediators] if mediators else [])))
        for branch in ("nde_nie", "cde"):
            part = block.get(branch)
            if isinstance(part, Mapping):
                named.extend(str(one) for one in part.get("adjustment") or ())
        break
    return named


def _grounds_to(written: Atom, ground: Atom, binding: dict) -> bool:
    """Whether some choice of objects for the statement's variables makes
    ``written`` the atom ``ground``, consistently with ``binding``, which
    this extends."""
    if (written.predicate != ground.predicate
            or written.time_index != ground.time_index
            or len(written.args) != len(ground.args)):
        return False
    for term, value in zip(written.args, ground.args):
        if isinstance(term, VarTerm):
            if binding.setdefault(term.name, value.name) != value.name:
                return False
        elif term.name != value.name:
            return False
    return True


def _statements_behind(program: object, tail: Atom, head: Atom) -> list:
    """Every cause statement the program writes that grounds to this edge.

    All of them, not the one the graph keeps: projection stores a single
    statement per edge and a later one overwrites an earlier, and nothing
    refuses a program that states one edge twice. Stated once as a
    language model's proposal for every unit and once as evidence for one,
    the edge is a proposal the answer rests on whichever came last.
    """
    behind = []
    for statement in getattr(program, "statements", ()):
        if not isinstance(statement, CauseStatement):
            continue
        binding: dict = {}
        if (_grounds_to(statement.from_atom, tail, binding)
                and _grounds_to(statement.to_atom, head, binding)):
            behind.append(statement)
    return behind


def _reached(graph, start: Atom, forward: bool) -> set:
    seen, frontier = {start}, [start]
    step = graph.successors if forward else graph.predecessors
    while frontier:
        for nxt in step(frontier.pop()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def _told(kind: str, ends: tuple, describes: object) -> tuple:
    """An edge and what is said of it, as one key: its kind, its
    predicates, and the statements read the way T10-1 reads them."""
    return kind, ends, json.dumps(_as_read(describes), sort_keys=True,
                                  ensure_ascii=False, default=repr)


def _told_of(kind: str, ends: tuple, annotations: object) -> tuple:
    """What a gap owes an edge one of whose statements is annotated so."""
    return _told(kind, ends, _what_the_edge_says(kind, ends, {
        "source": getattr(annotations, "source", None),
        "confidence": getattr(annotations, "confidence", None)}))


def _the_edges_it_rests_on(result: Mapping, program: object,
                           context: VerificationContext) -> set:
    """Every proposed edge the answer rests on with what one of its
    statements says, as :func:`_told` keys it -- one key per reading.

    On the ground graph the answer was reached on. A directed edge when a
    directed path between two distinct atoms the answer rests on runs
    through it -- in a DAG, exactly when the first reaches its tail and its
    head reaches the second -- or a supporting path on the envelope walks
    it in either direction; a bidirected one when it touches one of those
    atoms.
    """
    graph = context.graph
    spelt = {_spelt_as_the_envelope_spells(node): node for node in graph}
    extensions = result.get("extensions") or {}
    between = set(atoms_held_by(context.query))
    between.update(spelt[text] for text in _the_atoms_the_blocks_name(extensions)
                   if text in spelt)

    present = [atom for atom in between if atom in graph]
    below = {atom: _reached(graph, atom, forward=True) for atom in present}
    above = {atom: _reached(graph, atom, forward=False) for atom in present}
    rested = {(u, v) for u, v in graph.edges
              if any(u in below[s] and v in above[t]
                     for s in present for t in present if s != t)}
    structural = result.get("structural_result")
    for path in (structural.get("supporting_paths") or ()) if isinstance(structural, Mapping) else ():
        nodes = [spelt.get(str(text)) for text in path or ()]
        for u, v in zip(nodes, nodes[1:]):
            if u is not None and v is not None:
                rested.update(edge for edge in ((u, v), (v, u)) if graph.has_edge(*edge))

    owed: set = set()
    for tail, head in rested:
        for statement in _statements_behind(program, tail, head):
            annotations = getattr(statement, "annotations", None)
            if _is_a_proposal(annotations):
                owed.add(_told_of(
                    "cause", (tail.predicate, head.predicate), annotations))
    for statement in getattr(program, "statements", ()):
        annotations = getattr(statement, "annotations", None)
        if not (isinstance(statement, BidirectedStatement)
                and _is_a_proposal(annotations)):
            continue
        if any(_grounds_to(end, atom, {}) for atom in between
               for end in (statement.left, statement.right)):
            owed.add(_told_of("bidirected", tuple(sorted(
                (statement.left.predicate, statement.right.predicate))),
                annotations))
    return owed


def _the_edges_its_gaps_disclose(report: object) -> dict:
    """An edge and what a gap says of it, as :func:`_told` keys them, ->
    the index of the first gap saying it."""
    disclosed: dict = {}
    gaps = report.get("gaps") or () if isinstance(report, Mapping) else ()
    for index, gap in enumerate(gaps):
        if not isinstance(gap, Mapping) or gap.get("kind") != _READS_ITS_CITED_EDGE:
            continue
        for ref in gap.get("provenance") or ():
            ref_id = ref.get("ref_id") if isinstance(ref, Mapping) else None
            if not isinstance(ref_id, str):
                continue
            spelling = ref_id.removesuffix(":annotations.source")
            for kind, (prefix, arrow, _named) in _EDGE_SITES.items():
                if spelling.startswith(prefix) and arrow in spelling:
                    ends = tuple(spelling[len(prefix):].split(arrow, 1))
                    if kind == "bidirected":
                        ends = tuple(sorted(ends))
                    disclosed.setdefault(
                        _told(kind, ends, gap.get("describes")), index)
    return disclosed


def _spelt(told) -> list[str]:
    """Each edge with what is said of it, for a message: every sentence
    and the words it fills in besides the edge."""
    spelt = []
    for kind, ends, words in told:
        said = "; ".join(
            " ".join([str(one.get("sentence"))] + [
                str(value) for slot, value in sorted((one.get("said") or {}).items())
                if slot != "edge"])
            for one in json.loads(words) if isinstance(one, dict))
        spelt.append(f" {_EDGE_SITES[kind][2]} ".join(ends) + f" ({said})")
    return sorted(spelt)


def verify_proposed_edges_are_disclosed(result: object, program: object,
                                        context: VerificationContext) -> None:
    """The proposed edges an answer rests on are the edges its gaps disclose.

    :func:`verify_gap_edge_statements` holds what such a gap says to the
    edge it cites. Which edges have one was decided by the report's author
    alone, and the ledger's copy of the gaps is read off the gaps, so
    nothing held the set itself. Measured on the corpus: each of the 21
    such gaps, removed with the ledger line that copies it, passed every
    door; a gap added for an annotated edge that owes none passed 18 times
    of 18, twelve of them an edge whose source is evidence, told as a
    language model's -- a reading the rule above gives any source that is
    not a discovery marker.

    Held both ways, against a statement made here from the program, the
    question, the ground graph and the two blocks that add atoms to what a
    path must join. On the ground graph and not on the predicates: a first
    version asked reachability between predicates and refused an honest
    answer, a program unrolled in time where ``b`` a step back moves ``a``
    and ``a`` moves ``b`` now, ``a -> b`` on no path the answer rests on,
    while over predicates ``x`` reached ``a`` and ``b`` reached ``y``.
    Reachability rather than an enumeration of paths, since the graph is a
    DAG and a bound on paths is a graph that owes less the larger it is.

    Held as edges together with what is said of them. A gap names its edge
    by predicates, and several statements can stand behind a name -- an
    edge stated twice, or grounded at two times or for two units -- that
    read differently. Each reading among the statements the answer rests
    on is owed once, and a reading of a statement it does not rest on is
    not. Measured: ``x -> y`` written a step back as PC's, now as GES's and
    two steps back as PC's again, asked about ``x`` now, was told as PC's
    and passed every door, the one such edge it rests on being GES's.

    An answer owing a disclosure is refused whether its report lacks the
    gap or lacks the report: an absent report reads as nothing to tell.
    """
    if not isinstance(result, Mapping):
        return
    owed = _the_edges_it_rests_on(result, program, context)
    disclosed = _the_edges_its_gaps_disclose(result.get("data_gap_report"))
    undisclosed = owed - set(disclosed)
    if undisclosed:
        raise VerificationError(
            f"T10-2: the answer rests on {_spelt(undisclosed)}, which a "
            f"language model or a discovery algorithm put in the program, "
            f"and no gap tells the reader so. That sentence is how a reader "
            f"learns an edge the answer needs was never evidence",
            step_index=None, rule="data_gap_completeness_check",
        )
    unowed = set(disclosed) - owed
    if unowed:
        raise VerificationError(
            f"T10-2: gap[{min(disclosed[e] for e in unowed)}] discloses "
            f"{_spelt(unowed)} as a proposal this answer rests on, and it is "
            f"not one: its source is evidence, no path the answer rests on "
            f"runs through it, or no statement of it the answer rests on "
            f"says so. A reader sent to find evidence for an "
            f"edge is sent on this gap's word",
            step_index=None, rule="data_gap_completeness_check",
        )


# ============================================ T10-2, a restriction on a collider
#
# Whether an answer says its sample was restricted on a common effect of the
# intervention and the target. The sentence was checked for what it says and
# nothing held whether it is there.

#: The two caveats that say the effect was estimated inside a restricted
#: sample and that the restriction is on a collider: the question's ``given``
#: conditions on it, or an observation restricts the data to it.
_CONDITIONED_ON_A_COLLIDER = "collider_conditioning_opens_backdoor"
_RESTRICTED_TO_A_COLLIDER = "selection_on_collider_opens_path"


def _opens_a_path_through(graph, bidirected, x, y, conditioning, w) -> bool:
    """Whether some path between ``x`` and ``y``, open given
    ``conditioning``, is open because ``w`` is conditioned on: ``w`` is a
    collider on it or a descendant of one. Paths over the directed and the
    bidirected edges both; an arrowhead of either kind makes a collider."""
    if x == y:
        return False
    mg = _verifier_build_admg_multigraph(graph, bidirected)
    if x not in mg or y not in mg:
        return False
    for edge_path in nx.all_simple_edge_paths(mg, x, y):
        nodes = [x]
        for u, v, _key in edge_path:
            nodes.append(v if nodes[-1] == u else u)
        opened_by_w = False
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            if (_verifier_has_arrowhead_at(mg, edge_path[i - 1], v)
                    and _verifier_has_arrowhead_at(mg, edge_path[i], v)):
                below = {v} | set(_verifier_directed_descendants(graph, v))
                if below.isdisjoint(conditioning):
                    break
                opened_by_w = opened_by_w or w in below
            elif v in conditioning:
                break
        else:
            if opened_by_w:
                return True
    return False


def _reaches_avoiding(graph, start, goal, avoided) -> bool:
    seen, frontier = {start}, [start]
    while frontier:
        for nxt in graph.successors(frontier.pop()):
            if nxt == goal:
                return True
            if nxt != avoided and nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return False


def _a_common_effect(graph, x, y, w) -> bool:
    """A directed path from ``x`` to ``w`` that avoids ``y``, and one from
    ``y`` to ``w`` that avoids ``x`` (Hernán 2004 §3). A chain ``x -> y -> w``
    reaches ``w`` from ``x`` only through ``y``: over-control on a mediator,
    not a restriction on a collider."""
    if w in (x, y) or any(node not in graph for node in (x, y, w)):
        return False
    return _reaches_avoiding(graph, x, w, y) and _reaches_avoiding(graph, y, w, x)


def _the_caveats_it_owes(program: object, context: VerificationContext) -> set:
    """``(kind, collider, value, intervention, target)`` for every caveat
    owed, the names as a gap says them: predicates, and the value rendered
    as a sentence renders it."""
    query = context.query
    if not isinstance(query, EffectQuery):
        return set()
    graph, x, y = context.graph, query.intervention.atom, query.target.atom
    owed: set = set()
    # One estimate, one conditioning set: what the question conditions on
    # and what the sample was restricted to. Restricting a sample is
    # conditioning on it, so both caveats ask the same question of it.
    given = frozenset(item.atom for item in query.given)
    observations = [statement for statement in getattr(program, "statements", ())
                    if isinstance(statement, ObservationStatement)]
    restricted = frozenset(node for statement in observations for node in graph
                           if _grounds_to(statement.atom, node, {}))
    conditioning = given | restricted
    for w in given:
        if w not in (x, y) and _opens_a_path_through(
                graph, context.bidirected, x, y, conditioning, w):
            owed.add((_CONDITIONED_ON_A_COLLIDER, w.predicate, None,
                      x.predicate, y.predicate))
    for statement in observations:
        for node in graph:
            if _grounds_to(statement.atom, node, {}) and node not in (x, y) \
                    and _opens_a_path_through(
                        graph, context.bidirected, x, y, conditioning, node):
                owed.add((_RESTRICTED_TO_A_COLLIDER, node.predicate,
                          language.capped(language.symbols(statement.value)),
                          x.predicate, y.predicate))
    return owed


def _saids(entries: Any) -> list:
    return [entry["said"] for entry in entries or ()
            if isinstance(entry, Mapping) and isinstance(entry.get("said"), Mapping)]


def _the_caveats_it_writes(report: object) -> dict:
    """The same tuple for every such caveat a report writes -> the index of
    the first gap writing it. A caveat whose description names no collider
    is read as naming nothing, which nothing owes.

    Read off every place the gap says it. A caveat is told in its
    description, again in the gap's own occasion, and again in each way
    past that names the collider — "drop `w` from `given`" is the caveat
    as much as the description is, and it is what a reader acts on. Read
    off the description alone, every other place took any variable the
    problem has. A place spells some of the slots and the description
    the rest, so a place that disagrees tells a caveat of its own, and
    nothing owes it.
    """
    written: dict = {}
    gaps = report.get("gaps") or () if isinstance(report, Mapping) else ()
    for index, gap in enumerate(gaps):
        kind = gap.get("kind") if isinstance(gap, Mapping) else None
        if kind not in (_CONDITIONED_ON_A_COLLIDER, _RESTRICTED_TO_A_COLLIDER):
            continue
        described = [said for said in _saids(gap.get("describes"))
                     if "collider" in said] or [{}]
        elsewhere = _saids(gap.get("describes")) + _saids(
            [gap]) + _saids(gap.get("alternative_paths"))
        for place in described + elsewhere:
            said = {**described[0], **place}
            value = said.get("value") if kind == _RESTRICTED_TO_A_COLLIDER else None
            written.setdefault((kind, said.get("collider"), value,
                                said.get("intervention"), said.get("target")), index)
    return written


def _spelt_caveats(caveats) -> list[str]:
    out = []
    for kind, collider, value, intervention, target in sorted(caveats, key=str):
        restriction = collider if kind == _CONDITIONED_ON_A_COLLIDER else f"{collider}={value}"
        how = "conditioning on" if kind == _CONDITIONED_ON_A_COLLIDER else "a sample restricted to"
        out.append(f"{how} {restriction} for the effect of {intervention} on {target}")
    return out


def verify_collider_caveats_are_owed(result: object, program: object,
                                     context: VerificationContext) -> None:
    """The caveats that say a restriction is on a collider are the ones the
    answer owes.

    A reader told nothing is told the estimate is the effect asked for;
    told that it carries selection bias, a reader discounts an estimate that
    does not. Which answers carry one was decided by the report's author
    alone. Measured on the corpus: each of the 7 such caveats, removed,
    passed every door.

    Held both ways, against a statement made here from the program, the
    question and the ground graph with its bidirected edges. On the ground
    graph: the producer asked it of predicates until #631, and over them a
    restriction on an atom no ground path reached was a collider, and one on
    ``x`` now was passed over as the intervention a step back.

    An answer owing a caveat is refused whether its report lacks the gap or
    lacks the report. The report is absent only when it has nothing to
    tell, and a must-disclose caveat keeps it alive.
    """
    if not isinstance(result, Mapping):
        return
    owed = _the_caveats_it_owes(program, context)
    written = _the_caveats_it_writes(result.get("data_gap_report"))
    missing = owed - set(written)
    if missing:
        raise VerificationError(
            f"T10-2: the answer owes a caveat for {_spelt_caveats(missing)}, a "
            f"restriction on a common effect of the intervention and the "
            f"target, and no gap says so. Without it a reader takes an "
            f"estimate carrying selection bias for the effect asked",
            step_index=None, rule="data_gap_completeness_check",
        )
    unowed = set(written) - owed
    if unowed:
        raise VerificationError(
            f"T10-2: gap[{min(written[c] for c in unowed)}] says "
            f"{_spelt_caveats(unowed)} opens a path, and on the graph the answer was "
            f"reached on it does not. A reader discounts an estimate on this "
            f"gap's word",
            step_index=None, rule="data_gap_completeness_check",
        )


# ============================================ T10-2 completeness


# Every investigation group must be cited, with one exemption: framing
# items reach the report as ambiguous_variable_definition gaps carrying a
# framing_note ref, so check 3 already holds them and demanding a second
# citation under a different ref kind would reject correct reports.
#
# Written as an exemption rather than an inclusion list on purpose. The
# inclusion form names the groups that are covered and lets an unnamed
# group pass in silence, which is how this rule sat green while first the
# assumption channel and then the structure and observation channels
# emitted nothing at all.
_UNCITED_GROUPS: frozenset[str] = frozenset({"framing"})


def _verify_t10_2_completeness(
    report: dict,
    *,
    derivation_steps: list[dict],
    investigation_requests: list[dict],
    framing_notes: list[dict],
) -> None:
    """T10-2: every upstream failure signal must be covered by at least
    one gap somewhere in the report.

    Coverage = some gap has a provenance ref pointing back to that
    signal. We check three signal classes (the ones the schema makes
    detectable from the JSON envelope):

    1. Failed derivation steps → at least one gap with provenance
       derivation_step:<step_id_or_rule>.
    2. Investigation_request items → at least one gap with provenance
       investigation_request:<item.target>, for every group except the
       framing exemption noted at ``_UNCITED_GROUPS``.
    3. Framing notes → at least one gap with provenance
       framing_note:<predicate>.

    Check 2 holds the whole channel because an item is the kernel saying
    what it needs, in the one place it says it. Structure items in
    particular carry no derivation step behind them — their producers
    return before any step is recorded — so an uncited one leaves the
    report claiming a clean bill of health for a query that returned
    nothing.
    """
    gaps = report.get("gaps", [])
    # Build inverted index: signal_id → set of gap indices that cite it.
    cited_derivation: set[str] = set()
    cited_investigation: set[str] = set()
    cited_framing: set[str] = set()
    for gap in gaps:
        for ref in gap.get("provenance", []) or []:
            kind = ref.get("ref_kind")
            rid = ref.get("ref_id")
            if kind == "derivation_step":
                cited_derivation.add(rid)
            elif kind == "investigation_request":
                cited_investigation.add(rid)
            elif kind == "framing_note":
                cited_framing.add(rid)

    # 1. Failed derivation steps must be cited.
    for step in derivation_steps:
        if not _step_failed(step):
            continue
        sid = _step_id_or_rule(step)
        rule = step.get("rule", "")
        # Accept either the step_id form OR the bare rule name as
        # citation — the generator may pick either.
        if sid not in cited_derivation and rule not in cited_derivation:
            raise VerificationError(
                f"T10-2: failed derivation step rule={rule!r} "
                f"step_id={sid!r} has no corresponding gap in the report",
                step_index=None, rule="data_gap_completeness_check",
            )

    # 2. Investigation items must be cited, framing aside.
    for req in investigation_requests:
        group = req.get("group")
        if group in _UNCITED_GROUPS:
            continue
        for item in req.get("items", []) or []:
            target = item.get("target")
            if not target:
                # Not "nothing to check". This loop IS the coverage
                # demand, and a falsy target let an item opt out of it by
                # naming nothing — the exemption above, reached without
                # being on the list. Measured: emptying one target was
                # accepted on five of the six answer shapes that carry a
                # citable item.
                raise VerificationError(
                    f"T10-2: {group} investigation_request carries an "
                    f"item with target={target!r}; an item with no name "
                    f"cannot be cited by a gap, and this check is what "
                    f"says it must be",
                    step_index=None, rule="data_gap_completeness_check",
                )
            if target not in cited_investigation:
                raise VerificationError(
                    f"T10-2: {group} investigation_request "
                    f"target={target!r} has no corresponding gap in the report",
                    step_index=None, rule="data_gap_completeness_check",
                )

    # 3. Framing notes must be cited.
    for note in framing_notes:
        pred = note.get("predicate")
        if not pred:
            continue
        if pred not in cited_framing:
            raise VerificationError(
                f"T10-2: framing_note predicate={pred!r} has no "
                f"corresponding gap in the report",
                step_index=None, rule="data_gap_completeness_check",
            )


# ============================================ T10-3 kind consistency


# What space each species' provenance points into moved to
# themis.types.REF_KINDS_OF in #618. It is a statement about the
# species, so the producer has to be able to read it too — here it
# could only ever be read after the fact, which is why every site
# typed the kind again beside the id and nothing compared the two.


def _verify_t10_3_kind_consistency(
    report: dict,
    *,
    derivation_steps: list[dict],
) -> None:
    """T10-3: each gap.kind must be coherent with what the cited
    provenance signals can support.

    Three checks:
    (a) every ref must point into a space the species declares (per
        :data:`themis.types.REF_KINDS_OF`);
    (b) at least one ref has to be there to carry it;
    (c) when an unidentifiable_no_admissible_set / missing_iv_candidate
        gap cites a derivation_step, that step must actually be a failed
        step (else the gap is a phantom).

    (a) is the side that was missing. A declaration has been here since
    this rule was written, but what it was asked was (b) alone — whether
    SOME ref was acceptable — so a second ref of any kind rode along
    beside an acceptable one, and every refusal that looked like this
    rule's work was really T10-1 finding the id would not resolve in the
    space its kind named. That is a refusal about the SPELLING of an id,
    and it says nothing about whose evidence it is.
    """
    # Quick lookup of failure status by step_id / rule name.
    failed_step_ids: set[str] = set()
    for step in derivation_steps:
        if _step_failed(step):
            failed_step_ids.add(_step_id_or_rule(step))
            rule = step.get("rule", "")
            if rule:
                failed_step_ids.add(rule)

    for gap_index, gap in enumerate(report.get("gaps", [])):
        kind = gap.get("kind")
        try:
            species = GapKind(kind)
        except ValueError:
            raise VerificationError(
                f"T10-3: gap[{gap_index}] has unknown kind={kind!r}",
                step_index=None, rule="data_gap_kind_consistency_check",
            ) from None
        accepts = {member.value for member in REF_KINDS_OF[species]}
        provenance = gap.get("provenance", []) or []
        ref_kinds = {ref.get("ref_kind") for ref in provenance}
        stray = sorted(str(one) for one in ref_kinds - accepts)
        if stray:
            raise VerificationError(
                f"T10-3: gap[{gap_index}] kind={kind!r} cites {stray}, "
                f"which it does not declare as a space its provenance "
                f"points into; it may cite {sorted(accepts)}",
                step_index=None, rule="data_gap_kind_consistency_check",
            )
        if not (ref_kinds & accepts):
            raise VerificationError(
                f"T10-3: gap[{gap_index}] kind={kind!r} requires at least "
                f"one provenance ref of {sorted(accepts)}; got "
                f"{sorted(str(one) for one in ref_kinds)}",
                step_index=None, rule="data_gap_kind_consistency_check",
            )
        # Failure-only gap kinds: the cited derivation step must be a
        # failed step, otherwise the gap is fabricated. Exception:
        # ``tian_hedge_witness`` is a SUCCESSFUL step that proves
        # unidentifiability — it's the witness, not a failure record,
        # but downstream consumers see the same blocking gap.
        if kind in (
            "unidentifiable_no_admissible_set",
            "missing_iv_candidate",
        ):
            tian_hedge_step_ids = {
                _step_id_or_rule(s)
                for s in derivation_steps
                if s.get("rule") == "tian_hedge_witness"
            }
            tian_hedge_step_ids |= {"tian_hedge_witness"}
            for ref in provenance:
                if ref.get("ref_kind") != "derivation_step":
                    continue
                rid = ref.get("ref_id")
                # If the gap claims missing_iv_candidate / unidentifiable,
                # at least one cited step must be a failure or a Tian
                # hedge witness. Multiple refs allowed.
                if rid in failed_step_ids or rid in tian_hedge_step_ids:
                    break
            else:
                # No derivation_step ref pointed at a failed step.
                # Allow if the gap also cites an investigation_request —
                # in that path the failure is documented through the
                # missing-information channel, not the derivation chain.
                cited_inv = any(
                    ref.get("ref_kind") == "investigation_request"
                    for ref in provenance
                )
                if not cited_inv:
                    raise VerificationError(
                        f"T10-3: gap[{gap_index}] kind={kind!r} cites "
                        "derivation_step refs but none point at an actual "
                        "failed step (and no investigation_request ref "
                        "documents the failure either)",
                        step_index=None,
                        rule="data_gap_kind_consistency_check",
                    )


# ================================= T10-5 what a gap is worth, and to whom
#
# ``severity`` ranks the list a reader works down and decides which gap
# reaches the headline; ``blocks`` says which of identification, a point, an
# interval, a transport or an interpretation filling this one would buy
# back. Both are acted on, and neither was read by any rule.
#
# Neither could be. Both were typed at all 47 construction sites, and a
# value every site writes is declared nowhere — so the only thing a rule
# could have held them against was the producer's layout, and a verifier
# that restates a producer's layout agrees with it by construction.
#
# They belong to the species, and now say so. :data:`themis.types.SEVERITY_OF`
# and :data:`~themis.types.BLOCKS_OF` hold the species whose value is the
# same on every occasion; :data:`~themis.types.SEVERITY_TURNS_ON` and
# :data:`~themis.types.BLOCKS_TURN_ON` hold the few where it is the
# occasion's, each naming in a sentence what it turns on. The two rows
# partition ``GapKind`` and are checked at import, so every species either
# has a word here to be held to or states in code why it has none — and this
# rule is silent on exactly the second sort, which is the declaration's own
# statement about itself rather than a corner the reading missed.
#
# Imported rather than restated, which is the opposite of every other table
# in this module and for the same reason those are restated. A restatement
# buys independence from the PRODUCER's roster. This is not the producer's
# roster: it is the contract layer's declaration of what the name means —
# the arrangement ``status_rules`` reads ``STATUS_CLAIMS`` under — and the
# producer now fills its own gaps FROM it, so a copy here would not be a
# second reading, only a second thing to drift.

_SPECIES_RULE = "data_gap_species_check"

#: The two things a gap says about its own weight, each with the species
#: that fix it and the species that declare it the occasion's.
_A_GAP_SAYS_OF_ITSELF = (
    ("severity", SEVERITY_OF, SEVERITY_TURNS_ON),
    ("blocks", BLOCKS_OF, BLOCKS_TURN_ON),
)

#: What a reader does with each, so a refusal names what goes wrong rather
#: than which field disagrees.
_WHAT_A_READER_DOES_WITH_IT = {
    "severity": ("ranks the gaps by it and reads the top of that list as "
                 "what stands in the way of an answer"),
    "blocks": "reads it to learn what filling this gap would buy back",
}

_SPECIES_NAMED: dict[str, GapKind] = {kind.value: kind for kind in GapKind}


#: Where the envelope says a feedback loop was reduced to one equation.
#: Restated rather than imported, like every other envelope word in this
#: module, and pinned to the block vocabulary by a test.
_A_LOOP_REDUCED_TO_ONE_EQUATION = ("extensions", "feedback_loop", "reduction")


def _the_occasion_for_an_iv_assumption(envelope: Mapping) -> str:
    """What the assumption under an instrument's answer DOES to the number.

    :data:`themis.types.SEVERITY_TURNS_ON` says this species' weight turns
    on which of two things the assumption does — sit under the instrument
    as a condition on reading the number, or change what quantity the
    number is OF. Two producers build this species accordingly, one per
    occasion, and the second is reached only where a feedback loop was
    reduced to a single equation: there the digits are a structural
    coefficient rather than the interventional contrast that was asked
    for, which is a different quantity and not a caveat on the same one.

    Read off the reduction rather than off the gap's own provenance ref.
    The ref is written at the same site as the severity, so an author who
    got the occasion wrong would have written both wrong and been agreed
    with; the reduction is the identification layer's record of what
    happened to the estimand, which is what the severity is about.
    """
    node: object = envelope
    for step in _A_LOOP_REDUCED_TO_ONE_EQUATION:
        if not isinstance(node, Mapping):
            return "informational"
        node = node.get(step)
    return "informational" if node is None else "important"


#: The occasions this rule reads, one per species whose severity is not its
#: species'. ``declared_type_data_mismatch`` is absent because it is read
#: in :mod:`themis.verifier.type_reconciliation_rules`, against the columns
#: the answer stands on — and a second reading here would be a second thing
#: to drift rather than a second opinion. What holds the SET closed is not
#: this table but a counterexample per member: a species that declares its
#: severity an occasion's and has nothing anywhere that reads the occasion
#: has a field no rule can refuse, which is the arrangement
#: ``SEVERITY_TURNS_ON`` exists to end rather than to license.
_THE_OCCASION_READ_HERE = {
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED:
        _the_occasion_for_an_iv_assumption,
}


def _verify_t10_5_species_properties(
    report: dict, envelope: dict | None = None,
) -> None:
    """Each gap's severity and blocks, against what its species declares."""
    for gap_index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, dict):
            continue
        kind = gap.get("kind")
        species = _SPECIES_NAMED.get(kind) if isinstance(kind, str) else None
        if species is None:
            # Not a species whose declaration could be looked up. A word
            # outside the vocabulary is refused by the schema the door
            # validates against, before any rule here reads it.
            continue
        # Silent where the audit was handed no answer, and that silence is
        # not a way through: a species is here because its occasion is a
        # fact about the answer, so it cites an ``envelope_path``, and T10-1
        # refuses a report audited without the answer that path lands on.
        # Pinned by a counterexample rather than left to this comment.
        reader = _THE_OCCASION_READ_HERE.get(species)
        if reader is not None and envelope is not None:
            owed = reader(envelope)
            shown = gap.get("severity")
            if shown != owed:
                raise VerificationError(
                    f"T10-5: gap[{gap_index}] kind={species.value!r} says "
                    f"its severity is {shown!r}, and on this occasion it is "
                    f"{owed!r}: {SEVERITY_TURNS_ON[species]}. A reader "
                    f"{_WHAT_A_READER_DOES_WITH_IT['severity']}",
                    step_index=None, rule=_SPECIES_RULE,
                )
        for field, fixed, _the_occasion_s in _A_GAP_SAYS_OF_ITSELF:
            declared = fixed.get(species)
            if declared is None:
                continue
            shown = gap.get(field)
            if shown == declared.value:
                continue
            does = _WHAT_A_READER_DOES_WITH_IT[field]
            if shown is None:
                raise VerificationError(
                    f"T10-5: gap[{gap_index}] kind={species.value!r} says "
                    f"nothing about its {field}, and a gap of this species "
                    f"is {declared.value!r} on every occasion; a reader "
                    f"{does}",
                    step_index=None, rule=_SPECIES_RULE,
                )
            raise VerificationError(
                f"T10-5: gap[{gap_index}] kind={species.value!r} says its "
                f"{field} is {shown!r}, and a gap of this species is "
                f"{declared.value!r} on every occasion; a reader {does}",
                step_index=None, rule=_SPECIES_RULE,
            )


# ============================== T10-6 what shape of data a gap asks for
#
# ``required_data.data_type`` is the third field to be held this way and the
# first that does not sit on the gap: it lives on the block saying what would
# fill the gap, one object down, which is how a word belonging to the species
# came to have six authors and no declaration. What it costs a reader is the
# whole difference between "someone has to publish one number" and "someone
# has to obtain records", and until now the only sentence about it anywhere
# was the producer's own line.
#
# :data:`themis.types.DATA_TYPE_OF` and
# :data:`~themis.types.DATA_TYPE_TURNS_ON` are imported rather than restated,
# on the terms the T10-5 comment above sets out: a restatement buys
# independence from a PRODUCER's roster, and these are not a producer's
# roster but the contract layer's statement of what the word means.
#
# The one species whose shape is an occasion's is read here from the ask
# itself. That is what makes this more than two fields agreed with each
# other: the gap cites an investigation item, the item carries the statement
# the distribution is missing FROM, and whether that statement conditions on
# anything is a fact about the answer rather than about either word the gap
# wrote. So the same reading holds both — the ``signature`` naming the shape
# and the ``data_type`` naming what would supply it are one fact spelled
# twice, and a gap that gets either one wrong is refused by the ask.

_SHAPE_RULE = "data_gap_required_data_check"

#: What a reader does with the shape, so a refusal names what goes wrong
#: rather than only which word was unexpected.
_WHAT_A_COLLECTOR_DOES_WITH_IT = (
    "reads it as whether one published number closes this, or whether "
    "records have to be obtained"
)

#: What supplies each shape of ask. Two sides of one statement, which is why
#: one reading settles the ``signature`` and the ``data_type`` together.
_WHAT_A_SHAPE_OF_ASK_NEEDS = {
    "conditional": "ipd",
    "marginal": "marginal",
}


def _the_shape_of_the_ask(item: Mapping) -> str | None:
    """Whether the statement this item filed conditions on anything.

    ``None`` where the item stated no probability — an ask with no target
    is a shortfall with nothing behind it, and guessing a shape here would
    invent the fact this rule exists to check against.
    """
    skeleton = item.get("skeleton")
    if not isinstance(skeleton, Mapping):
        return None
    if not isinstance(skeleton.get("target"), Mapping):
        return None
    given = skeleton.get("given")
    return "conditional" if isinstance(given, list) and given else "marginal"


#: The species whose shape is the occasion's, and where that occasion is read.
_THE_ASK_READ_HERE = {
    GapKind.MISSING_DISTRIBUTION: _the_shape_of_the_ask,
}


def _the_ask_a_gap_was_filed_for(
    gap: Mapping, asks: Mapping[str, Mapping],
) -> Mapping | None:
    """The investigation item this gap points at, where it points at one."""
    for ref in gap.get("provenance") or ():
        if not isinstance(ref, dict):
            continue
        if ref.get("ref_kind") != "investigation_request":
            continue
        ref_id = ref.get("ref_id")
        if not isinstance(ref_id, str):
            continue
        item = asks.get(ref_id)
        if item is not None:
            return item
    return None


def _verify_t10_6_shape_of_data(
    report: dict, *, investigation_requests: list[dict],
) -> None:
    """What each gap asks a reader to go and get, against its species."""
    asks: dict[str, Mapping] = {}
    for request in investigation_requests:
        if not isinstance(request, dict):
            continue
        for item in request.get("items") or ():
            if isinstance(item, dict) and isinstance(item.get("target"), str):
                asks.setdefault(item["target"], item)

    for gap_index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, dict):
            continue
        kind = gap.get("kind")
        species = _SPECIES_NAMED.get(kind) if isinstance(kind, str) else None
        if species is None:
            continue
        wanted = gap.get("required_data")
        if not isinstance(wanted, dict):
            continue
        shown = wanted.get("data_type")
        allowed = {shape.value for shape in required_data_type(species)}
        if not allowed:
            if shown is not None:
                raise VerificationError(
                    f"T10-6: gap[{gap_index}] kind={species.value!r} asks for "
                    f"{shown!r} data, and this species asks for no particular "
                    f"shape; a collector {_WHAT_A_COLLECTOR_DOES_WITH_IT}",
                    step_index=None, rule=_SHAPE_RULE,
                )
            continue
        if shown not in allowed:
            raise VerificationError(
                f"T10-6: gap[{gap_index}] kind={species.value!r} asks for "
                f"{shown!r} data, and a gap of this species asks for "
                f"{sorted(allowed)}; a collector "
                f"{_WHAT_A_COLLECTOR_DOES_WITH_IT}",
                step_index=None, rule=_SHAPE_RULE,
            )
        reader = _THE_ASK_READ_HERE.get(species)
        if reader is None:
            continue
        # Silent where there is no ask to read — a gap of this species that
        # cites no item, or an item that filed no statement, leaves this rule
        # nothing to hold either word against, and a guess here would be the
        # rule answering a question nobody asked it.
        item = _the_ask_a_gap_was_filed_for(gap, asks)
        shape = _the_shape_of_the_ask(item) if item is not None else None
        if shape is None:
            continue
        owed = _WHAT_A_SHAPE_OF_ASK_NEEDS[shape]
        if shown != owed:
            raise VerificationError(
                f"T10-6: gap[{gap_index}] kind={species.value!r} asks for "
                f"{shown!r} data, and the statement it was filed for is "
                f"{shape}, which needs {owed!r}: "
                f"{DATA_TYPE_TURNS_ON[species][1]}",
                step_index=None, rule=_SHAPE_RULE,
            )
        if gap.get("signature") != shape:
            raise VerificationError(
                f"T10-6: gap[{gap_index}] kind={species.value!r} says its "
                f"signature is {gap.get('signature')!r}, and the statement it "
                f"was filed for is {shape}. The signature and the shape of "
                f"data are one fact spelled twice, and this one is read off "
                f"the statement rather than off either spelling",
                step_index=None, rule=_SHAPE_RULE,
            )


# ================================= T10-7 whose way past a gap this route is
#
# ``alternative_paths[].route`` is what a reader ACTS on. It was written at 38
# construction sites and declared for three of them, so nothing anywhere asked
# whether a route belonged to the gap offering it: swapping one for any of the
# other 84 the kernel names left 63 of them unrefused. What did refuse the
# other 21 was ``statement_rules._CARRIERS``, which asks whether the slots a
# sentence names are the ones filled in beside it — so two routes with the same
# slot signature were interchangeable, and a gap could tell a reader to go find
# an instrument where the honest way past was to measure the confounder.
#
# :func:`themis.gaps.ways_past` is imported rather than restated for the reason
# the T10-5 comment gives: it is the contract layer's statement of which ways
# past belong to a species, not a producer's roster. Restating it here would
# make this module the thirty-ninth author.
#
# What it claims is a ceiling. Which of a species' ways past THIS occasion
# offers is the renderer's decision, and a table saying so would be the
# renderer's branches copied — so two routes of the same species remain
# interchangeable here, and that is the rule's stated reach rather than an
# oversight.

_ROUTE_RULE = "data_gap_route_check"

#: What a reader does with a way past, so a refusal says what goes wrong
#: rather than only which word was unexpected.
_WHAT_A_READER_DOES_WITH_A_ROUTE = (
    "acts on it — it is the sentence telling them what to go and do about "
    "this gap, and doing the wrong one costs a study"
)


def _verify_t10_7_ways_past(report: dict) -> None:
    """Every route a gap offers is one its species declares.

    Silent where the species or the route is not one this build names: an
    unknown kind belongs to T10-3 and an unknown route to the contract's own
    enumeration, and a rule refusing for a reason another authority owns
    reports that authority's coverage as its own.
    """
    for gap_index, gap in enumerate(report.get("gaps", []) or []):
        if not isinstance(gap, dict):
            continue
        kind = gap.get("kind")
        if not isinstance(kind, str):
            continue
        try:
            species = GapKind(kind)
        except ValueError:
            continue
        offered = []
        for path in gap.get("alternative_paths", []) or []:
            if isinstance(path, dict) and isinstance(path.get("route"), str):
                offered.append(path["route"])
        if not offered:
            continue
        allowed = {
            str(route) for route in _gaps.ways_past(
                species, blocking=gap.get("severity") == _BLOCKING)
        }
        named = {route for route in offered if route in _gaps.BY_ROUTE}
        stray = sorted(named - allowed)
        if not stray:
            continue
        if species in _gaps.NO_WAY_PAST:
            raise VerificationError(
                f"T10-7: gap[{gap_index}] kind={species.value!r} offers "
                f"{stray} and this species has no way past at all — "
                f"{_gaps.NO_WAY_PAST[species]}. A reader "
                f"{_WHAT_A_READER_DOES_WITH_A_ROUTE}",
                step_index=None, rule=_ROUTE_RULE,
            )
        raise VerificationError(
            f"T10-7: gap[{gap_index}] kind={species.value!r} offers "
            f"{stray}, and the ways past this species has are "
            f"{sorted(allowed)}. A reader "
            f"{_WHAT_A_READER_DOES_WITH_A_ROUTE}",
            step_index=None, rule=_ROUTE_RULE,
        )


_SENTENCE_RULE = "data_gap_sentence_check"

#: What a reader does with a gap's description, so a refusal says what goes
#: wrong rather than only which word was unexpected.
_WHAT_A_READER_DOES_WITH_A_DESCRIPTION = (
    "reads it to learn what went wrong — it is the first thing the gap "
    "says about itself, and the wrong one describes another study's problem"
)


def _verify_t10_8_what_it_says(report: dict) -> None:
    """Every statement a gap makes is one its species declares.

    Silent on the same terms as T10-7: an unknown kind belongs to T10-3
    and an unknown statement to the contract's own enumeration, and a rule
    refusing for a reason another authority owns reports that authority's
    coverage as its own.
    """
    for gap_index, gap in enumerate(report.get("gaps", []) or []):
        if not isinstance(gap, dict):
            continue
        kind = gap.get("kind")
        if not isinstance(kind, str):
            continue
        try:
            species = GapKind(kind)
        except ValueError:
            continue
        said = []
        for entry in gap.get("describes", []) or []:
            if isinstance(entry, dict) and isinstance(
                    entry.get("sentence"), str):
                said.append(entry["sentence"])
        if not said:
            continue
        allowed = {str(entry) for entry in _gaps.says_of(species)}
        named = {entry for entry in said if entry in _gaps.BY_SENTENCE}
        stray = sorted(named - allowed)
        if not stray:
            continue
        if not allowed:
            raise VerificationError(
                f"T10-8: gap[{gap_index}] kind={species.value!r} says "
                f"{stray} and nothing in this kernel builds this species, "
                f"so it declares no statement of its own. A reader "
                f"{_WHAT_A_READER_DOES_WITH_A_DESCRIPTION}",
                step_index=None, rule=_SENTENCE_RULE,
            )
        raise VerificationError(
            f"T10-8: gap[{gap_index}] kind={species.value!r} says {stray}, "
            f"and what this species says about itself is {sorted(allowed)}. "
            f"A reader {_WHAT_A_READER_DOES_WITH_A_DESCRIPTION}",
            step_index=None, rule=_SENTENCE_RULE,
        )


# ============================================ public entry


def verify_data_gap_report(
    report: dict,
    *,
    derivation: dict | None = None,
    investigation_requests: list[dict] | None = None,
    framing_notes: list[dict] | None = None,
    envelope: dict | None = None,
) -> None:
    """Run T10-1 / T10-2 / T10-3 / T10-5 / T10-6 / T10-7 against ``report``.

    Inputs are dicts (as serialized in the result envelope) so the audit
    catches serialization bugs in addition to generator bugs.

    Returns ``None`` on accept; raises ``VerificationError`` on reject
    (with rule field set to the offending T10 rule name).

    A ``None`` or empty report short-circuits to accept — the generator
    decided no gaps applied to this query, and T10-2 cannot demand
    coverage for signals that were never reported.
    """
    if report is None:
        return
    if not isinstance(report, dict):
        raise VerificationError(
            f"data_gap_report must be a dict; got {type(report).__name__}",
            step_index=None, rule="data_gap_report",
        )
    derivation_steps: list[dict] = []
    if derivation is not None:
        steps = derivation.get("steps", []) or []
        derivation_steps = list(steps)
    investigation_requests = list(investigation_requests or [])
    framing_notes = list(framing_notes or [])

    _verify_t10_1_provenance(
        report,
        derivation_steps=derivation_steps,
        investigation_requests=investigation_requests,
        framing_notes=framing_notes,
        envelope=envelope,
    )
    _verify_t10_2_completeness(
        report,
        derivation_steps=derivation_steps,
        investigation_requests=investigation_requests,
        framing_notes=framing_notes,
    )
    _verify_t10_3_kind_consistency(
        report,
        derivation_steps=derivation_steps,
    )
    _verify_t10_5_species_properties(report, envelope)
    _verify_t10_6_shape_of_data(
        report, investigation_requests=investigation_requests,
    )
    _verify_t10_7_ways_past(report)
    _verify_t10_8_what_it_says(report)


# ==================================== T10-4: the tier the report announces
#
# ``answer_tier`` is the report's headline: point, interval, or none — the
# strongest answer this question can still get. Every rule above reads the
# gaps; none of them reads the word those gaps add up to, and a word no
# rule reads is an unfalsifiable claim in the place a reader looks first.
#
# It is not a sixth thing the run knows. It is a conclusion drawn from five
# things already on the envelope — the question, the status, the gap
# species, whether an interval is in hand, and which shape the answer came
# out in — plus one on the program. So it is recomputed here rather than
# compared to anything, which is the only form of holding a judgement that
# a judgement cannot satisfy by rewriting its own evidence.
#
# The last of the five is what made recomputing possible at all. The tier
# is one question in two tenses — what came out, and failing that what
# could still be got — and until the answer's shape was readable here the
# second tense was all this could ask, which is wrong on every answer that
# came out in some shape other than a number.

#: Which questions name a quantity an answer could be a tier OF. A tier is
#: what the answer to a question can be, so a question that names no
#: quantity has none — and this is the producer's first line.
#:
#: Restated, not imported, for the reason every table in this package is:
#: a verifier that reads the producer's own roster agrees with it by
#: construction. Pinned to ``themis.questions`` by a test, so a new kind
#: arrives as a red suite rather than as a tier nothing reads.
_NAMES_AN_ESTIMAND = frozenset({
    "effect", "identify", "probability", "counterfactual", "causation",
    "scm_counterfactual", "counterfactual_conjunction", "proximal_effect",
})

#: And which of those have an interval to fall back on when a point is out
#: of reach for a reason the data cannot mend. Same roster, same pin.
_HAS_INTERVAL_FALLBACK = frozenset({"effect", "counterfactual", "causation"})

#: The species that say the POINT is unreachable — not "the data are
#: short", which every gap says. Bounds presence is NOT such a signal: an
#: assumption-free floor is attached to every needs_investigation effect,
#: including ones whose point is perfectly identified and merely missing a
#: parameter.
_POINT_IS_BLOCKED_BY = frozenset({
    "unidentifiable_no_admissible_set", "transport_sources_disagree",
})

#: And the two statuses that say the same thing about themselves.
_POINT_IS_BLOCKED_AT = frozenset({
    "needs_assumption", "counterfactual_bounded",
})

#: The status that says the question itself does not stand.
_OUTSIDE_LANGUAGE = "outside_language"

_TIER_POINT, _TIER_INTERVAL, _TIER_NONE = "point", "interval", "none"

#: Weakest last. A reader holding several is holding the strongest of them.
_STRONGEST_FIRST = (_TIER_POINT, _TIER_INTERVAL, _TIER_NONE)

#: What a reader is holding once the estimate carries this block. The keys
#: are where each declared answer shape lives on ``numeric_estimate`` and
#: the values are what that shape hands over — the two facts
#: :mod:`themis.answers` declares per shape, restated here for the reason
#: every table in this package is, and pinned to it by a test.
#:
#: Two blocks are not read by presence and are not in here. ``point`` is
#: read for presence rather than truth, because a null effect is an answer
#: and ``0.0`` is one. ``probabilities_of_causation`` is on the envelope
#: whichever way the run went, and what monotonicity buys sits INSIDE each
#: quantity, so the tier turns on the point rather than on the block.
_TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES = {
    "dose_response_curve": _TIER_POINT,
    "decomposition": _TIER_POINT,
    "controlled_direct_effect": _TIER_POINT,
    "joint_effect": _TIER_POINT,
    "counterfactual_cell": _TIER_INTERVAL,
    # A test says whether the treatment does anything and no more, so a
    # reader asking how much is holding nothing.
    "no_effect_test": _TIER_NONE,
}
_A_SINGLE_NUMBER = "point"
_THE_THREE_PROBABILITIES = "probabilities_of_causation"


def _the_tier_the_answer_came_out_as(result: Mapping) -> str | None:
    """What the estimate on this envelope actually hands a reader, or
    ``None`` where no answer this build can name has come out.

    ``None`` is not "no answer". Not every road to a number ends in a
    ``numeric_estimate`` — the structural and plug-in roads write their
    number elsewhere — so this says only that the shape vocabulary has
    nothing to say here, and the question the caller falls back on is the
    forward-looking one: what could still be got.
    """
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, Mapping):
        return None
    carried = {tier for key, tier in _TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES.items()
               if estimate.get(key)}
    if estimate.get(_A_SINGLE_NUMBER) is not None:
        carried.add(_TIER_POINT)
    three = estimate.get(_THE_THREE_PROBABILITIES)
    if isinstance(three, Mapping) and three:
        sharp = (three.get("pn") or {}).get("point") is not None \
            if isinstance(three.get("pn"), Mapping) else False
        carried.add(_TIER_POINT if sharp else _TIER_INTERVAL)
    for tier in _STRONGEST_FIRST:
        if tier in carried:
            return tier
    return None


def _a_premise_the_caller_withheld_blocks_the_point(
    program: Any, query_id: Any,
) -> bool:
    """Whether a premise, rather than absent data, stands in the way.

    Probabilities of causation are intervals; monotonicity is what
    collapses them to a point, and it is declared on the question rather
    than found in the data. Undeclared, no amount of data yields a point,
    so a tier read off the gaps alone would promise a number that cannot
    arrive.
    """
    query = query_of(program, query_id) if isinstance(program, dict) \
        else None
    if not isinstance(query, Mapping):
        return False
    return query.get("kind") == "causation" and not query.get("monotonic")


#: The answers the estimate's own fields had no room for: the ANSWER-family
#: blocks ``themis.blocks`` declares with no carrier. Restated rather than
#: imported, for the reason every table in this package is, and pinned to
#: the declaration by a test.
#:
#: A block whose carrier IS ``numeric_estimate`` is a display copy of
#: something the shape table already reads, so it is not here — the field
#: and the copy would count as two answers where there is one.
_AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR = frozenset({
    "anderson_rubin_region", "causation", "scm_counterfactual",
})


def _an_answer_the_point_is_not(result: Mapping) -> bool:
    """Whether an answer outside the estimate's fields is sitting here, and
    is not one that says of itself that it brackets nothing.

    Only ever asked where the point is out of reach, and there an answer
    that exists anyway is what the reader still has. What it is not is a
    point, because the point is what the envelope has just said is
    unavailable — so what such an answer supports is the interval.

    The one thing that can make it less than that is the answer saying so.
    A confidence region over a coefficient vector is written whether or not
    it closed, and an open region excludes nothing; it says which it is,
    and that word is read rather than assumed.

    This channel is why the tier is readable for a whole road at all. The
    region is a set over k coefficients, so ``numeric_estimate`` — one
    estimand, one number, one interval — has no room for it and no answer
    shape describes it, and a rule reading only the estimate's fields sees
    a blocked point beside nothing and says "no answer available" over the
    interval each coefficient projects onto.
    """
    extensions = result.get("extensions")
    if not isinstance(extensions, Mapping):
        return False
    for key in _AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR:
        block = extensions.get(key)
        if not isinstance(block, Mapping):
            continue
        region = block.get("region")
        if isinstance(region, Mapping) and region.get("bounded") is False:
            continue
        return True
    return False


def _an_interval_is_in_hand(result: Mapping) -> bool:
    """Whether the envelope carries an interval worth calling one.

    Three channels and each is read for the answer's own word about
    itself: the bounds rows an effect question gets, where a row that
    calls its own width uninformative is not one; the interval a bounded
    counterfactual carries on its numeric result, where one spanning the
    whole of [0, 1] excludes nothing and is not one either; and an answer
    the estimate's fields had no room for, which says whether it closed.
    """
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping) and not row.get(
                "width_when_uninformative", False):
            return True
    numeric = result.get("numeric_result")
    interval = numeric.get("interval") if isinstance(numeric, Mapping) \
        else None
    if isinstance(interval, Mapping):
        low, high = interval.get("low"), interval.get("high")
        if (isinstance(low, (int, float)) and isinstance(high, (int, float))
                and not (low <= 0.0 and high >= 1.0)):
            return True
    return _an_answer_the_point_is_not(result)


def _identification_blocks_the_point(result: Mapping) -> bool:
    """Whether the run itself says the POINT is out of reach.

    Two signals and neither is bounds presence: an assumption-free floor
    is attached to every needs_investigation effect, including ones whose
    point is identified and merely missing a parameter.

    Kept apart from the premise below because the two do not answer the
    same question about an interval. Where identification failed, the
    bounds are out of reach too and NONE is the honest word; where only a
    premise is missing, the interval is exactly what is left.
    """
    report = result.get("data_gap_report")
    gaps = report.get("gaps") or () if isinstance(report, Mapping) else ()
    return (
        result.get("status") in _POINT_IS_BLOCKED_AT
        or any(isinstance(gap, Mapping)
               and gap.get("kind") in _POINT_IS_BLOCKED_BY
               for gap in gaps)
    )


def _the_point_is_blocked(result: Mapping, program: Any) -> bool:
    """Whether anything at all says the POINT is out of reach — what the
    run found, or what the question never declared."""
    return _identification_blocks_the_point(
        result) or _a_premise_the_caller_withheld_blocks_the_point(
            program, result.get("query_id"))


def _the_tier_this_envelope_supports(result: Mapping, program: Any) -> str:
    """The strongest answer this envelope actually offers a reader.

    One question asked in two tenses, and which tense applies is decided
    by the envelope rather than chosen here. Where an answer has come out,
    the tier is what it came out as. Where none has, it is what could
    still be got — and that is the only branch the gap species and the
    withheld premise are consulted for, because before there is an answer
    they are all there is to read.

    A number that came out where identification failed is the one place
    the two tenses meet: it is an estimate under an assumption nobody
    granted, so it does not make the estimand's point available and the
    envelope falls back to the interval it does have.
    """
    if result.get("status") == _OUTSIDE_LANGUAGE:
        # Not that the data are short: the quantity is undefined as asked,
        # so neither what is in hand nor what could be got is a claim worth
        # making, and the forward-looking branch would make the second.
        return _TIER_NONE
    identification_blocked = _identification_blocks_the_point(result)
    premise_blocked = _a_premise_the_caller_withheld_blocks_the_point(
        program, result.get("query_id"))
    came_out = _the_tier_the_answer_came_out_as(result)
    if came_out is not None:
        if came_out != _TIER_POINT:
            return came_out
        if not identification_blocked:
            return _TIER_POINT
    elif not identification_blocked and not premise_blocked:
        return _TIER_POINT
    if _an_interval_is_in_hand(result):
        return _TIER_INTERVAL
    if (came_out is None and premise_blocked and not identification_blocked
            and result.get("numeric_result") is None
            and result.get("query_kind") in _HAS_INTERVAL_FALLBACK):
        # Nothing computed, and with the premise the only thing in the way
        # the shape an answer would take is the interval. NONE here would
        # say the data cannot produce an answer, when what they cannot
        # produce is a point.
        return _TIER_INTERVAL
    return _TIER_NONE


def verify_answer_tier(result: Mapping, program: Any) -> None:
    """The report's headline word, held to what the envelope carries.

    Recomputed rather than compared to anything, which is the only form of
    holding a judgement that a judgement cannot satisfy by rewriting its
    own evidence.

    This used to hold two one-sided claims instead — no point past a
    blocking signal, no "none" over an interval — because recomputing the
    identification pass's function refused six honest answers, all of them
    ones the estimation layer had corrected afterwards. The six were not
    six exceptions. They were the interval-in-hand question answered from
    two hard-written channels while three answer shapes carry their
    interval elsewhere, and the estimation layer patching the result per
    site. What made the recomputation possible is that the envelope says
    which shape the answer came out in, so the two tenses of the question
    — what came out, what could still be got — are both readable here.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    if not isinstance(result, Mapping):
        return
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    kind = result.get("query_kind")
    if not isinstance(kind, str):
        return
    shown = report.get("answer_tier")

    # A tier is what the answer to a question can BE, so a question that
    # names no quantity has none. The producer's own first line.
    if kind not in _NAMES_AN_ESTIMAND:
        if shown is not None:
            raise VerificationError(
                f"the report tells a reader the best answer available is "
                f"{shown!r}, and this question names no quantity for an "
                f"answer to be about; a tier here is a promise about "
                f"nothing",
                step_index=None, rule="answer_tier_check",
            )
        return
    if shown is None:
        raise VerificationError(
            f"the report tells a reader nothing about what answer is still "
            f"available, and a {kind!r} question names a quantity an "
            f"answer would be of; the absence reads as 'not applicable' "
            f"where the truth is 'nobody said'",
            step_index=None, rule="answer_tier_check",
        )

    supported = _the_tier_this_envelope_supports(result, program)
    if shown == supported:
        return

    # The two bends a reader is hurt most by, said in their own words.
    if shown == _TIER_POINT:
        raise VerificationError(
            "the report promises a reader a point estimate is still "
            "available, and this envelope carries the signal that the "
            "point is out of reach — an unidentified estimand, sources "
            "that disagree, a premise the question never declared, or an "
            "answer that came out in some other shape. More data cannot "
            "produce what is promised",
            step_index=None, rule="answer_tier_check",
        )
    if shown == _TIER_NONE:
        raise VerificationError(
            "the report tells a reader no answer is available and this "
            "envelope carries one; a reader deciding whether to collect "
            "more data is told to give up on an answer they already have",
            step_index=None, rule="answer_tier_check",
        )
    raise VerificationError(
        f"the report tells a reader the best answer available is "
        f"{shown!r}, and what this envelope carries is {supported!r}",
        step_index=None, rule="answer_tier_check",
    )
