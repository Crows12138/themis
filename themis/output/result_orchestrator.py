"""Serialize a typed QueryResult into the JSON shape described in
query_result.schema.json.

Responsibilities:
- enum -> string
- dataclass -> dict
- omit None-valued optional fields and empty collections
- emit structured formula AST (never stringify it)

v0.1 only implements the serialize direction (``to_dict``). The
deserialize direction (``from_dict``) is reserved for a later slice
and currently raises ``NotImplementedError``. ``syntactic_validator.
validate_result`` can still be used to confirm that a serialized
payload conforms to ``query_result.schema.json``, but reloading it
back into a typed ``QueryResult`` is not part of the v0.1.0 surface.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Sequence

from .. import blocks
from .. import gaps
from .. import intervals, ledger
from . import assumption_glossary
from .assumption_glossary import classify_assumption, layer_of
from ..types import (
    Atom,
    CauseStatement,
    ConstantExpr,
    ConstTerm,
    DataGap,
    DataGapReport,
    FormulaExpr,
    FractionExpr,
    NumericResult,
    ProbabilityRefExpr,
    ProbabilityStatement,
    ProductExpr,
    Program,
    QueryResult,
    StructuralResult,
    SumExpr,
    Term,
    ValuedAtom,
    ValueExpr,
    VarRef,
    VarTerm,
)


def _structural_to_dict(sr: StructuralResult) -> dict:
    d: dict = {"value": sr.value}
    if sr.supporting_paths:
        d["supporting_paths"] = [list(p) for p in sr.supporting_paths]
    return d


def _numeric_to_dict(nr: NumericResult) -> dict:
    d: dict = {"value": nr.value}
    if nr.interval is not None:
        d["interval"] = {"low": nr.interval.low, "high": nr.interval.high}
    if nr.unit is not None:
        d["unit"] = nr.unit
    return d


def _term_to_dict(term: Term) -> dict:
    if isinstance(term, ConstTerm):
        return {"type": "const", "name": term.name}
    if isinstance(term, VarTerm):
        return {"type": "var", "name": term.name}
    raise TypeError(f"unknown term type: {type(term).__name__}")


def _atom_to_dict(atom: Atom) -> dict:
    d: dict[str, object] = {
        "predicate": atom.predicate,
        "args": [_term_to_dict(t) for t in atom.args],
    }
    if atom.time_index is not None:
        d["time_index"] = {"kind": "relative", "value": atom.time_index.value}
    return d


def _value_to_json(v: ValueExpr):
    if isinstance(v, VarRef):
        return {"kind": "var_ref", "name": v.name}
    return v  # bool / int / float / str literal


def _valued_atom_to_dict(va: ValuedAtom) -> dict:
    d: dict = {"atom": _atom_to_dict(va.atom)}
    if va.value is not None:
        d["value"] = _value_to_json(va.value)
    return d


def _formula_to_dict(expr: FormulaExpr) -> dict:
    if isinstance(expr, ConstantExpr):
        return {"kind": "constant", "value": expr.value}
    if isinstance(expr, ProbabilityRefExpr):
        return {
            "kind": "probability_ref",
            "target": _valued_atom_to_dict(expr.target),
            "given": [_valued_atom_to_dict(g) for g in expr.given],
        }
    if isinstance(expr, ProductExpr):
        return {
            "kind": "product",
            "terms": [_formula_to_dict(t) for t in expr.terms],
        }
    if isinstance(expr, SumExpr):
        return {
            "kind": "sum",
            "bind": {"name": expr.bind.name},
            "over": _atom_to_dict(expr.over),
            "body": _formula_to_dict(expr.body),
        }
    if isinstance(expr, FractionExpr):
        return {
            "kind": "fraction",
            "numerator": _formula_to_dict(expr.numerator),
            "denominator": _formula_to_dict(expr.denominator),
        }
    raise TypeError(f"unknown formula node: {type(expr).__name__}")


def to_dict(result: QueryResult) -> dict:
    """Render a QueryResult dataclass as a schema-conformant dict."""
    d: dict = {
        "status": result.status.value,
        "query_kind": result.query_kind.value,
    }
    if result.query_id is not None:
        d["query_id"] = result.query_id
    if result.structural_result is not None:
        d["structural_result"] = _structural_to_dict(result.structural_result)
    if result.numeric_result is not None:
        d["numeric_result"] = _numeric_to_dict(result.numeric_result)
    if result.confidence is not None:
        d["confidence"] = result.confidence
    if result.confidence_sources:
        d["confidence_sources"] = [
            {
                "slot_label": s.slot_label,
                **({"source": s.source} if s.source is not None else {}),
                "confidence": s.confidence,
                "is_weakest": s.is_weakest,
            }
            for s in result.confidence_sources
        ]
    if result.formula is not None:
        d["formula"] = _formula_to_dict(result.formula)
    if result.missing_information:
        d["missing_information"] = [
            {
                "kind": m.kind.value,
                "name": m.name,
                "priority": m.priority.value,
                "gap": m.gap.value,
                **(gaps.carried(m) or {}),
                **(
                    {"observable": {
                        "variables": list(m.observable.variables),
                        **(
                            {"population": m.observable.population}
                            if m.observable.population is not None
                            else {}
                        ),
                    }}
                    if m.observable is not None
                    else {}
                ),
                **(
                    {"superseded_by_estimation": True}
                    if m.superseded_by_estimation
                    else {}
                ),
            }
            for m in result.missing_information
        ]
    if result.investigation_requests:
        out_requests = []
        for r in result.investigation_requests:
            row: dict = {
                "action": r.action.value,
                "target": r.target,
                "priority": r.priority.value,
            }
            if r.note is not None:
                row["note"] = r.note
            if r.group is not None:
                row["group"] = r.group
            if r.items:
                row["items"] = [
                    {
                        "target": it.target,
                        **(gaps.carried(it) or {}),
                        **({"skeleton": it.skeleton} if it.skeleton is not None else {}),
                        "gap": it.gap.value,
                        **(
                            {"superseded_by_estimation": True}
                            if it.superseded_by_estimation
                            else {}
                        ),
                    }
                    for it in r.items
                ]
            out_requests.append(row)
        d["investigation_requests"] = out_requests
    if result.framing_notes:
        d["framing_notes"] = [
            {"predicate": n.predicate, "missing": list(n.missing)}
            for n in result.framing_notes
        ]
    if result.derivation:
        # Lazy import to keep this module's top-level deps narrow; the
        # verifier already owns the canonical derivation encoder.
        from ..verifier.serialization import derivation_to_dict
        d["derivation"] = derivation_to_dict(result.derivation)
    if result.extensions is not None:
        d["extensions"] = result.extensions
    if result.data_gap_report is not None:
        d["data_gap_report"] = data_gap_report_to_dict(result.data_gap_report)
    if result.bounds_results:
        d["bounds_results"] = [
            _bounds_result_to_dict(b) for b in result.bounds_results
        ]
    if result.estimator_failure is not None:
        d["estimator_failure"] = result.estimator_failure
    return d


def _bounds_result_to_dict(b) -> dict:
    out: dict = {
        "method": b.method.value,
        "lower_expression": b.lower_expression,
        "upper_expression": b.upper_expression,
        # Unconditional: the name of the bounded quantity travels with the
        # interval whether or not a numeric end ever fills the endpoints.
        "estimand": b.estimand,
        # And how tight it is, for the same reason (#419). Three methods
        # bracket one estimand on one result and the rows differ in width
        # by 2.4x; without this, "which of these is closest to the truth"
        # and "which of these assumed the most" are one question wearing
        # two answers. Read from the one table that knows rather than
        # carried as a field a producer could forget or contradict.
        "tightness": str(intervals.tightness_of(b.method.value)),
    }
    if b.assumptions:
        out["assumptions"] = list(b.assumptions)
    if b.data_required:
        out["data_required"] = list(b.data_required)
    if b.width_when_uninformative:
        out["width_when_uninformative"] = True
    if b.notes is not None:
        out["notes"] = b.notes
    if b.instrument is not None:
        out["instrument"] = b.instrument
    return out


def data_gap_report_to_dict(report: DataGapReport) -> dict:
    """The report as the keys it takes on an envelope.

    Public for the same reason :func:`data_gap_to_dict` is: gaps found
    DURING estimation arrive at the envelope through the other road, and a
    road that hand-writes the key set is a second author for it. That is
    how a field this report no longer has went on being written after it
    was removed — the dataclass and the schema both said it was gone and
    the hand-written dict was answerable to neither.
    """
    out: dict = {"gaps": [data_gap_to_dict(g) for g in report.gaps]}
    if report.answer_tier is not None:
        out["answer_tier"] = report.answer_tier.value
    return out


def data_gap_to_dict(gap: DataGap) -> dict:
    """The one place a gap becomes JSON, and therefore the one place that
    decides how "there is none" is spelled.

    Public because it has a second caller: a gap FOUND DURING estimation is
    filed into a report that is already serialised, so it cannot be handed
    back as a dataclass the way the ones found before the run are. It can
    still be turned into JSON here, and that is the whole of what #427 was
    about — seven hand-built dicts copied the field list off the dataclass,
    and three copied a ``None`` along with it. In the dataclass ``None`` means
    "there is none"; in JSON ``null`` means "the key is here and its value is
    nothing", and the schema names only one of them as legal. Every
    thin-overlap answer had been failing its own schema.
    """
    out: dict = {
        "kind": gap.kind.value,
        "severity": gap.severity.value,
        "describes": [gaps.sentence_fields(e) for e in gap.describes],
        "blocks": gap.blocks.value,
        "provenance": [
            {"ref_kind": ref.ref_kind.value, "ref_id": ref.ref_id}
            for ref in gap.provenance
        ],
    }
    if gap.signature is not None:
        out["signature"] = gap.signature
    if gap.required_data is not None:
        rd = gap.required_data
        rd_out: dict = {}
        if rd.data_type is not None:
            rd_out["data_type"] = rd.data_type.value
        if rd.population is not None:
            rd_out["population"] = rd.population
        if rd.variables:
            rd_out["variables"] = list(rd.variables)
        if rd.min_sample_size is not None:
            rd_out["min_sample_size"] = rd.min_sample_size
        if rd.precision_target is not None:
            rd_out["precision_target"] = rd.precision_target
        if rd.sampling_point_count is not None:
            rd_out["sampling_point_count"] = rd.sampling_point_count
        # confounders_required: emit always when sampling_point_count is
        # set (i.e. dose-response gap context) so renderer can distinguish
        # 'tried but kernel couldn't extract' (empty array) from 'not
        # applicable' (key absent). Subagent real-test caught this: when
        # absent, the LLM filled in confounders by guessing.
        if rd.sampling_point_count is not None:
            rd_out["confounders_required"] = list(rd.confounders_required)
        elif rd.confounders_required:
            rd_out["confounders_required"] = list(rd.confounders_required)
        if rd.time_window is not None:
            rd_out["time_window"] = rd.time_window
        if rd.sutva_concerns:
            rd_out["sutva_concerns"] = list(rd.sutva_concerns)
        if rd_out:
            out["required_data"] = rd_out
    out.update(gaps.occasion_fields(gap))
    if gap.alternative_paths:
        out["alternative_paths"] = [gaps.route_fields(a)
                                    for a in gap.alternative_paths]
    return out


def from_dict(payload: dict) -> QueryResult:
    """Inverse of ``to_dict``.

    Not implemented in v0.1. Serialized results can be schema-validated
    via ``syntactic_validator.validate_result`` but cannot yet be
    reconstructed into a typed ``QueryResult``. Listed in
    ``v0_1_scope.md`` under out-of-scope; a later slice will add it
    together with the fixtures that need round-trip.
    """
    raise NotImplementedError("from_dict is not part of the v0.1 surface")


# ---------------------------------------------------------------------------
# Fix 3+4 §3.2 — LLM-proposed review surface aggregator (v0.1.5)
# ---------------------------------------------------------------------------


def _atom_repr(atom: Atom) -> str:
    """Short rendered form of an atom for review-surface display."""
    args = ",".join(a.name for a in atom.args)
    return f"{atom.predicate}({args})" if args else atom.predicate


def _probability_statement_key_repr(stmt: ProbabilityStatement) -> str:
    """Render a ProbabilityStatement as a P(...|...) key string for
    the review surface. Mirrors the runtime's format_probability_key
    shape but doesn't go through ProbabilityKey (we want the original
    statement's surface, not a canonicalised key)."""
    target_part = (
        f"{_atom_repr(stmt.target.atom)}={stmt.target.value}"
    )
    if stmt.given:
        given_part = ",".join(
            f"{_atom_repr(va.atom)}={va.value}" for va in stmt.given
        )
        body = f"{target_part}|{given_part}"
    else:
        body = target_part
    prefix = "P" if stmt.population is None else f"P_{stmt.population}"
    return f"{prefix}({body})"


def build_llm_proposed_review(program: "Program") -> dict | None:
    """Walk the program's statements and collect every LLM-proposed
    element (cause edges + probability priors) into a single audit
    surface that the user must see before trusting the result.

    Two collection criteria:

    - **Edges** (``CauseStatement``): ``annotations.source`` contains
      "llm" (case-insensitive substring match). Picks up
      ``"llm_proposal"`` (A2 convention) and any variant. Edges
      sourced from evidence (PubMed, KB, user) are excluded — they
      are not LLM-proposed.
    - **Probability priors** (``ProbabilityStatement``):
      ``provenance == "llm_prior"``. Includes the prior value, the
      target/given key, the population label, and the reason
      (``annotations.source``, validated non-empty by F3.1
      ``llm_prior_requires_source``).

    Returns ``None`` when neither category found any entries —
    in that case there's nothing to disclose, and the absence of
    the field keeps single-population non-LLM-prior fixtures byte-
    identical to pre-Fix-3+4 serialisations.

    Summary text gives the user a single sentence to ground the
    audit: "N edges + M probability priors come from LLM common
    knowledge. Themis's math is correct, but the answer hinges on
    these priors being reasonable — please review before using."

    Caller (``kernel._run_typed``) attaches this dict to each result's
    ``extensions.llm_proposed_review``. The review is program-wide so
    multi-query programs see the same review on every result.

    Charter: FIX_3_4_CHARTER_llm_mediated_transport.md §3.2.
    """
    edges: list[dict] = []
    probabilities: list[dict] = []

    for stmt in program.statements:
        if isinstance(stmt, CauseStatement):
            if stmt.annotations is None:
                continue
            source = stmt.annotations.source or ""
            if "llm" not in source.lower():
                continue
            edges.append({
                "from": _atom_repr(stmt.from_atom),
                "to": _atom_repr(stmt.to_atom),
                "source": source,
            })
        elif isinstance(stmt, ProbabilityStatement):
            if stmt.provenance != "llm_prior":
                continue
            reason = (
                stmt.annotations.source
                if stmt.annotations is not None else ""
            ) or ""
            entry: dict = {
                "key": _probability_statement_key_repr(stmt),
                "value": stmt.value,
                "reason": reason,
            }
            if stmt.population is not None:
                entry["population"] = stmt.population
            probabilities.append(entry)

    if not edges and not probabilities:
        return None

    return {"edges": edges, "probabilities": probabilities}


# ---------------------------------------------------------------------------
# Mechanism-audit surface (slice C) — functional-form assumption parity
# ---------------------------------------------------------------------------


def build_mechanism_audit(
    *,
    target: str,
    form: str,
    method: str,
    assumptions: Sequence[str],
    form_provenance: str,
    shape_provenance: Mapping[str, str],
) -> dict | None:
    """Disclose the shape an estimate's number was fitted through, as an
    audit surface mirroring ``build_llm_proposed_review``.

    **A mechanism does not introduce an assumption; it points at ones already
    declared.** ``assumptions`` is the estimator's own flat declaration list —
    the same tuple that reaches ``numeric_estimate.assumptions`` — and what is
    kept is the subset the glossary files under
    :attr:`~themis.ledger.Layer.FUNCTIONAL_FORM`. That subset IS the shape
    choice, so the block is a view over a channel that already exists rather
    than a second author beside it.

    Both halves of that sentence were wrong before. The field was one
    hand-written sentence, so it could point at nothing checkable: the ledger
    entry it produced carried no ``id``, the ledger's one deduplication is
    keyed on ``id``, and the same fact therefore arrived twice, in different
    words — and under different layers, because a sentence cannot be asked
    which layer it belongs to, so the ledger hard-coded one. A dose-response
    run showed the pair as ``[invalidating] identification`` and
    ``[distorting] functional_form``, and the summary counted the shape of a
    curve among the assumptions whose failure voids the causal conclusion.

    Reading the flat list is also what makes the pairing total: a sentence had
    to be written per family, and where nobody wrote one the disclosure simply
    did not exist. Selecting by layer cannot forget an assumption — but the
    CALL could still forget a family, and for ten of them it had. What closes
    that is not more call sites: it is
    :func:`augment_assumption_ledger` asking, on the one funnel every numeric
    answer passes through, whether a declared shape was disclosed.

    Returns ``None`` for a form-free estimator, which is a real answer rather
    than a degenerate one. Six families filled the field anyway, with a
    narrative of the route taken — which the derivation chain already carries,
    on the surface built for it — and the ledger filed that narrative as a
    distorting functional-form assumption. A row headed "the functional form
    is …" whose body said that no functional form was assumed, which is the
    shape #344 named.

    The third leg of the SCM triad: structure (``CauseStatement`` edges)
    and parameters (``ProbabilityStatement`` theta) already flow through
    propose -> annotate -> audit; the functional form a continuous
    estimator assumes (linear / forest / drlearner) did not. This lifts
    that assumption out of the flat list into a labelled, provenance-tagged
    element so the renderer can disclose it as a load-bearing choice the
    user must audit — the curve's *shape* is an assumption, not a measured
    quantity.

    ``form_provenance`` is the estimate's own answer to "did anything resolve
    a ``model=`` here, and was the form named or chosen". It is the one fact
    on this block the glossary cannot supply — who settled a form is a
    property of the RUN, not of the id, since the same
    ``logit_outcome_regression`` is the estimator's default in one family and
    the method's definition in the next — and it has no default value on
    purpose. It used to have one, written at fourteen attach points, and a
    constant is not an answer: it said the system had picked the shape even
    for the families where no caller can name another.

    It is spent HERE, per assumption, and is not a field of its own. One
    ``provenance`` on the block was one field for N facts, and measurably
    false as soon as N was 2: a back-door run with a caller's ``model=`` and a
    multi-level covariate declares the resolved shape, which the caller owns,
    beside the design matrix's decision to enter that column as a number,
    which nobody offered them.

    ``shape_provenance`` is the estimate's answer for the ids the outcome
    model did NOT settle, and it exists because the answer above cannot cover
    them and a table here could not either. That table was tried: five ids,
    keyed here, listing which shapes stood outside a run's resolution. It was
    a consumer guessing at a producer's levers, and it missed four — an IPW
    run reported its propensity floor as ``inherent``, an AIPW run reported
    the SAME unchanged floor as ``caller_asserted`` because a ``model=`` had
    been named beside it, and neither reader could act on what they were
    told. Only the estimator knows which of its shapes have a lever, so the
    estimator says so, and this spends what it says.

    Callers are ``estimation.dispatch``'s per-family attach points, which
    put the returned dict on ``result.extensions.mechanism_audit``.
    """
    named = tuple(
        str(a) for a in assumptions
        if layer_of(a) == ledger.Layer.FUNCTIONAL_FORM
    )
    if not named:
        return None
    # Coerced once, and loudly: an estimator that forgot to say who settled
    # its form arrives here with the empty string its dataclass carries, and
    # a block whose origin line is blank is worse than no block.
    resolution = ledger.provenance_named(form_provenance)
    settled = {a: resolution for a in named}
    stray = tuple(a for a in shape_provenance if a not in settled)
    if stray:
        # A builtin, like the coercion above: an origin filed against a shape
        # this estimate never declared reads in the block exactly like one
        # that was asked for, and it can only arrive from a producer naming a
        # lever it does not have.
        raise ValueError(
            f"themis: an origin was supplied for {list(stray)}, which this "
            f"estimate does not declare as a functional form — a shape "
            f"nobody assumed cannot have been settled by anybody"
        )
    settled.update(
        {a: ledger.provenance_named(o) for a, o in shape_provenance.items()})
    mechanism = {
        "target": target,
        "form": form,
        "method": method,
        "assumptions": [{"id": a, "settled_by": settled[a]} for a in named],
    }
    return {"mechanisms": [mechanism]}


# ---------------------------------------------------------------------------
# Assumption ledger — one severity-ranked view over the scattered channels
# ---------------------------------------------------------------------------

# Severity ordering drives the ledger sort, and the order is the
# vocabulary's own — ``themis.ledger.Severity`` declares it beside what
# each value means, so the sort and the reader's word cannot disagree.


#: Where a ROUTE block states what its own identifiability claim rests on.
#:
#: Two blocks do, at five sites, and every id is one the renderer glossary
#: already translates — the schema says as much beside the field. Nothing
#: read them: :func:`build_assumption_ledger` knew four channels and the
#: identification layer's own was not among them, so a mediation answer
#: reached the reader with "NDE / NIE 可识别" and no mention of the
#: cross-world conditions that "identifiable" is conditional on.
ROUTE_PREMISES: tuple[tuple[str, ...], ...] = (
    ("longitudinal_identification", "assumptions"),
    ("mediation_decomposition", "nde_nie", "assumptions"),
    ("mediation_decomposition", "cde", "assumptions"),
    ("mediation_joint_decomposition", "nde_nie", "assumptions"),
    ("mediation_joint_decomposition", "cde", "assumptions"),
)


def _route_premises(extensions: dict) -> tuple[str, ...]:
    """The ids those sites hold, in declaration order, each said once.

    A mediation block's two arms name the same consistency premise, and a
    reader owed "what has to hold" is owed it once.
    """
    out: list[str] = []
    for path in ROUTE_PREMISES:
        node: object = extensions
        for step in path:
            node = node.get(step) if isinstance(node, dict) else None
        if not isinstance(node, list):
            continue
        for item in node:
            if isinstance(item, str) and item not in out:
                out.append(item)
    return tuple(out)


def build_assumption_ledger(
    result: dict,
) -> dict | None:
    """Aggregate every load-bearing assumption scattered across the
    result envelope into ONE severity-ranked ledger.

    A VIEW, not a rewrite. It reads the existing channels —
    ``data_gap_report`` (which proposal edges are actually load-bearing,
    i.e. on the answer path — that analysis already ran there),
    ``extensions.llm_proposed_review`` (LLM theta priors),
    ``extensions.mechanism_audit`` (functional form) and
    :data:`ROUTE_PREMISES` (what an identification route says its own
    claim rests on, which is the channel that exists when no estimator
    ran at all) — and re-presents them as
    first-class entries.

    There was a fifth: an ``identification_specs`` argument, a tuple of
    dicts each carrying an id AND that id's sentence, layer and
    testability. Every id it carried also reached the flat list, and the
    three other fields are what this ledger asks the glossary for, keyed
    on that same id — so it was a second author of facts one table
    already held, and the two had drifted: fifteen disagreements about
    whether the reader could go and check a premise, two about which
    layer it sat in, and one sentence written three different ways. The source channels stay untouched; this is the
    single place a channel is turned into a layer, so an assumption's
    prominence tracks how load-bearing it is instead of which channel it
    happened to land in.

    What each channel is about — and so which layer it writes — is the only
    judgement made here. A proposal edge is a structural edge, an LLM theta
    prior is a parameter, an audited mechanism is a functional form, and an
    estimator's own declaration is whatever the glossary says it is. The
    severity follows from the layer and comes back from ``ledger.stamp``
    with it; stating it here as well is how one fact came to have two
    hundred authors.

    Each entry carries ``claim`` / ``layer`` / ``provenance`` /
    ``severity`` / ``testable`` (identification assumptions are
    untestable by design; a form can be probed by switching estimators;
    an edge needs evidence). Returns ``None`` when nothing is assumed.

    Caller (``estimation.dispatch._try_dose_response_estimate``) attaches
    the result to ``result.extensions.assumption_ledger``; the renderer
    leads with it instead of the individual channels.
    """
    extensions = result.get("extensions") or {}
    entries: list[dict] = []

    # 1b) identification premises a ROUTE block declares for itself. The
    #     blocks hold glossary ids — the schema says so — and nothing read
    #     them. Wherever an estimator later ran it declared the same ids
    #     flat, so the omission was invisible exactly where there was a
    #     number; on the structural and theta paths, which are what this
    #     system answers when there is no data, the ledger said nothing
    #     while the block beside it listed the cross-world conditions the
    #     whole decomposition rests on.
    claimed = {str(e["id"]) for e in entries if e.get("id")}
    for premise in _route_premises(extensions):
        if premise in claimed:
            continue
        entry = classify_assumption(premise)
        entry["layer"], entry["severity"], entry["provenance"] = ledger.stamp(
            "identification_premise", entry["layer"], entry["provenance"])
        entries.append(entry)
        claimed.add(premise)

    # 2a) structural edges — ONLY the load-bearing ones. The authoritative
    #     load-bearing analysis already ran in the data_gap_report
    #     generator (supporting_paths + DAG-walk), which emits one
    #     UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH gap per proposal edge the
    #     answer actually traverses. Sourcing from there — not from the
    #     full ``llm_proposed_review`` edge list — means a proposed-but-
    #     unused edge no longer shows up as "invalidating": that was the
    #     false alarm the flat edge list produced. Covers LLM- and
    #     discovery-proposed edges alike (the gap description names which).
    report = result.get("data_gap_report") or {}
    for gap in report.get("gaps") or []:
        if gap.get("kind") != "unverified_proposal_edge_on_query_path":
            continue
        witness = next((gaps.stated(e) for e in gap.get("describes") or ()),
                       None)
        layer, severity, provenance = ledger.stamp(
            "proposal_edge",
            ledger.Layer.STRUCTURAL_EDGE,
            ledger.Provenance.DISCOVERY
            if witness is gaps.Sentence.THE_EDGE_WAS_LEARNED_BY_DISCOVERY
            else ledger.Provenance.LLM_PROPOSAL,
        )
        entries.append({
            "claim": gaps.described(gap),
            "layer": layer,
            "provenance": provenance,
            "severity": severity,
            "testable": True,
        })

    # 2b) LLM theta priors — used in the numeric computation when present,
    #     so they stay in the ledger (magnitude-affecting -> distorting).
    review = extensions.get(blocks.Block.LLM_PROPOSED_REVIEW) or {}
    for prob in review.get("probabilities") or []:
        layer, severity, provenance = ledger.stamp(
            "theta_prior", ledger.Layer.PARAMETER, ledger.Provenance.LLM_PRIOR)
        entries.append({
            "claim": f"{prob.get('key')} = {prob.get('value')}（LLM 常识 prior）",
            "layer": layer,
            "provenance": provenance,
            "severity": severity,
            "testable": True,
        })

    # 3) functional form (curve shape). The block names glossary ids, and
    #    keeping them here is what lets the one dedup below see this channel
    #    at all: it is keyed on ``id``, and an entry assembled out of the
    #    block's own words carried none. So the same shape assumption reached
    #    the reader twice — once from here and once from the estimator's flat
    #    declaration — in two wordings and, because a sentence cannot be asked
    #    which layer it belongs to, under two layers and two severities.
    #
    #    The block's per-assumption ``settled_by`` IS what the entry carries,
    #    and this is the one channel entitled to answer for itself. Who
    #    settled a functional form is a property of the RUN — the same id is
    #    the method's definition under TMLE and the estimator's resolved
    #    default under back-door — so the glossary, which sees only the id,
    #    refuses the question, and the block, which holds the estimate's own
    #    resolution, answers it once per assumption.
    _fold_mechanisms(entries, claimed, extensions)

    return _ledger(entries)


def _fold_mechanisms(entries: list[dict], claimed: set[str],
                     extensions: dict) -> None:
    """Fold the audited shape choices onto the ledger, once, from either side.

    Read where the ledger is first built AND again where the estimate's own
    declarations are folded in, because the block is attached AFTER estimation
    and the ledger may have been built before it. A result whose ledger
    predates its estimate would otherwise meet its form assumptions on the
    flat channel — which carries the id and nothing else, and so cannot say
    who settled them.

    Both callers share ``claimed``, so an id folded here is not folded again
    there; the ORDER is what makes that mean the right thing, and it is the
    same order in both: this channel first, because it is the only one holding
    an answer at all.
    """
    mech = extensions.get(blocks.Block.MECHANISM_AUDIT) or {}
    for m in mech.get("mechanisms") or []:
        for named in m.get("assumptions") or []:
            text = str(named["id"])
            if text in claimed:
                continue
            entry = classify_assumption(text)
            entry["layer"], entry["severity"], entry["provenance"] = ledger.stamp(
                "audited_mechanism", entry["layer"], named["settled_by"])
            entries.append(entry)
            claimed.add(text)


def _ledger(entries: list[dict]) -> dict | None:
    """Sort by severity. Shared by the identification-time build and the
    post-estimate augmentation so the two never drift on ordering.

    It also wrote a one-line summary, and every fact in that line was the
    list beside it counted: how many entries, how many of them
    invalidating. A count stored next to the thing counted is a second
    record — one a verifier here had to check by searching the sentence for
    a Chinese substring — so the line is assembled where the reader's
    language is known, by :func:`themis.ledger.summary`.
    """
    if not entries:
        return None

    # A severity outside the vocabulary sorts FIRST, not last: the renderer
    # leads with the head of this list, so an unrecognised value must surface
    # for someone to fix rather than sink below "only affects the interval".
    entries.sort(key=lambda e: ledger.rank(e["severity"]))
    return {"assumptions": entries}


#: Where an ESTIMATOR leaves its own flat ``assumptions`` list.
#:
#: One address for as long as an estimate was a number, because a number
#: lives in ``numeric_estimate``. An answer that is a REGION over k
#: coefficients is not one — that field promises one estimand, one point and
#: one interval — so its estimator writes its declaration beside the region
#: instead, and the fold below looked only at the old address. What reached
#: the reader was a ledger with nothing in it, which reads as "nothing is
#: assumed" for an answer resting on exclusion, linearity and homoskedastic
#: errors.
#:
#: A declared list rather than a walk, for the reason :data:`ROUTE_PREMISES`
#: is one: an address is a decision about where a fact lives, and a walk
#: would also sweep up every OTHER ``assumptions`` key on the envelope —
#: including the route blocks above, which are a different channel with a
#: different provenance.
ESTIMATOR_DECLARATIONS: tuple[tuple[str, ...], ...] = (
    ("numeric_estimate",),
    ("extensions", blocks.Block.ANDERSON_RUBIN_REGION),
)


def _estimator_declarations(result: dict) -> tuple[dict, ...]:
    """Every estimator declaration this result carries, in declaration order."""
    out: list[dict] = []
    for path in ESTIMATOR_DECLARATIONS:
        node: object = result
        for step in path:
            node = node.get(step) if isinstance(node, dict) else None
        if isinstance(node, dict):
            out.append(node)
    return tuple(out)


def augment_assumption_ledger(result: dict) -> None:
    """Fold the estimator's own ``numeric_estimate.assumptions`` into the
    ledger, creating the ledger when the result has none.

    ``build_assumption_ledger`` reads the channels that exist at
    identification time. That leaves the flat ``assumptions`` list — the
    oldest channel, and the only one EVERY estimator populates — outside the
    ledger unless something folds it in. The ledger is
    the surface both ``analysis_report`` and ``response_rendering.md`` treat as
    the lead disclosure, so an estimator that did not opt in produced an answer
    whose assumptions were nowhere on that surface — silently, and silently
    again for the next estimator added.

    Called from the one funnel every numeric answer passes through, so the
    floor holds for estimators that exist today and for those added later.

    **A declaration is folded unless some entry has claimed it by id.** An
    estimator that supplies structured identification specs has said some of
    these things in better words, and the spec names which one it restates,
    so the structured wording wins and nothing else goes missing.

    That was a guess until it was a declaration, and the guess was "if the
    ledger carries any identification entry, the whole flat list is its
    unstructured twin". Nineteen estimator families took that branch, and
    what it dropped was everything they declare BESIDES identification:
    which weights an IPW used, that a TMLE is a targeted substitution
    estimator, that an interval is cluster-robust, that proximal rests on
    Miao's model f, that a causation answer came back as bounds because no
    monotonicity was assumed. The verifier, written independently, had
    reached for the same escape hatch — so nothing on either side saw it.
    """
    estimates = _estimator_declarations(result)
    if not estimates:
        return
    declared: list[str] = []
    for estimate in estimates:
        for item in estimate.get("assumptions") or ():
            if str(item) not in declared:
                declared.append(str(item))
    measured = _outcome_error_premises(result)
    if not declared and not measured:
        return

    extensions = result.setdefault("extensions", {})
    existing = extensions.get(blocks.Block.ASSUMPTION_LEDGER)
    if existing is not None:
        entries = list(existing.get("assumptions") or ())
    else:
        # No ledger yet — the other three channels have never been read for
        # this result either, so read them all rather than shipping a ledger
        # that discloses the estimator's assumptions and hides the audited
        # mechanism sitting next to them.
        entries = list((build_assumption_ledger(result) or {}).get("assumptions") or ())

    # Before anything is folded: a shape assumed with no block to read is a
    # question the flat channel below cannot answer, and the reject naming the
    # unwired family is more use than a KeyError on one of its ids.
    for estimate in estimates:
        _check_the_shape_was_disclosed(estimate, extensions)

    for item in measured:
        entry = classify_assumption(item)
        entry["layer"], entry["severity"], entry["provenance"] = ledger.stamp(
            "estimator_assumption", entry["layer"], entry["provenance"])
        entries.append(entry)

    claimed = {str(e["id"]) for e in entries if e.get("id")}
    _fold_mechanisms(entries, claimed, extensions)
    for item in declared:
        text = str(item)
        if text in claimed:
            continue
        entry = classify_assumption(text)
        if "provenance" not in entry:
            raise ValueError(
                f"themis: {text!r} is a functional-form assumption and no "
                f"mechanism_audit entry says who settled it, so the ledger "
                f"line beside it would have to guess — which is what it did "
                f"for as long as the answer was read off the id. The block is "
                f"built from this same list, so an id here and not there "
                f"means it was built from a different one."
            )
        entry["layer"], entry["severity"], entry["provenance"] = ledger.stamp(
            "estimator_assumption", entry["layer"], entry["provenance"])
        entries.append(entry)
        claimed.add(text)

    built = _ledger(entries)
    if built is not None:
        extensions[blocks.Block.ASSUMPTION_LEDGER] = built


def _check_the_shape_was_disclosed(estimate: dict, extensions: dict) -> None:
    """A shape assumed but not disclosed is a family that was never wired.

    The ledger line and the mechanism block say different things about the
    same assumption: the line says a functional form is being assumed, the
    block says WHICH one, through what method, and who settled it. A family
    that declares the assumption and attaches no block gives the reader the
    warning without the thing to audit — and, before this, gave it silently:
    the disclosure was a per-family call, so a family nobody wired was
    indistinguishable from a family with no shape to disclose.

    Checked here because this is the one funnel every numeric answer passes
    through, and raised rather than repaired because the fix is a line of
    wiring in the family that produced this, which cannot be written from
    here — the shape and its origin live on the estimate object, and by this
    point only the envelope is left.
    """
    if extensions.get(blocks.Block.MECHANISM_AUDIT) is not None:
        return
    shapes = [
        str(a) for a in (estimate.get("assumptions") or ())
        if layer_of(a) == ledger.Layer.FUNCTIONAL_FORM
    ]
    if not shapes:
        return
    raise ValueError(
        f"themis: {estimate.get('method')!r} declares functional-form "
        f"assumptions {shapes} and attaches no mechanism_audit block, so the "
        f"reader is told a shape was assumed and never told which. Call "
        f"``_attach_mechanism_audit(result, estimate, target=...)`` where "
        f"this family writes its numeric_estimate."
    )


def _outcome_error_premises(result: dict) -> tuple[str, ...]:
    """The premises declared by an outcome measurement-error assessment."""
    block = result.get("outcome_error")
    if not isinstance(block, dict):
        return ()
    return tuple(
        a for a in (block.get("assumptions") or ()) if isinstance(a, str)
    )
