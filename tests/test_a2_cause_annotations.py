"""Slice A2: CauseStatement annotations (provenance + confidence).

Symmetric completion of the annotation channel — ObservationStatement
and ProbabilityStatement already carried ``annotations``; this slice
brings CauseStatement inline so edges can be tagged as llm_proposal
vs evidence-backed without touching reasoning rules.

Pins:
- Schema accepts cause statements with annotations
- Semantic validator threads annotations into the typed Program
- Instantiation preserves annotations across forall expansion
- Reasoning still works (annotations never influence any rule)
"""
from __future__ import annotations

import json
import pathlib

import pytest

import themis
from themis import kernel
from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.output.data_gap_report import _atoms_the_blocks_name
from themis.runtime.graph_projection import atom_label
from themis.runtime.instantiation import instantiate
from themis.types import (
    Annotation,
    Atom,
    CauseStatement,
    ConstTerm,
    Program,
    VarTerm,
)
from themis import gaps as _gaps
from tests import caveats


def _ast_with_annotated_cause(source: str = "llm_proposal",
                                confidence: float | None = None) -> dict:
    ann: dict = {"source": source}
    if confidence is not None:
        ann["confidence"] = confidence
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": ann,
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "running",
                             "args": [{"type": "const", "name": "me"}]},
                    "to": {"predicate": "belly_fat_loss",
                           "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }


# ================================================================= schema

def test_schema_accepts_cause_with_annotations():
    ast = _ast_with_annotated_cause(source="llm_proposal")
    validate_ast(ast)  # must not raise


def test_schema_accepts_cause_with_confidence_only():
    ast = _ast_with_annotated_cause(source="PubMed:12345", confidence=0.85)
    validate_ast(ast)


def test_schema_rejects_cause_annotations_with_unknown_fields():
    ast = _ast_with_annotated_cause()
    ast["statements"][2]["annotations"]["invented_field"] = "x"
    with pytest.raises(SyntacticError):
        validate_ast(ast)


# =============================================================== validator

def test_validator_threads_annotations_into_typed_cause_statement():
    ast = _ast_with_annotated_cause(source="llm_proposal", confidence=0.6)
    prog = validate_program(validate_ast(ast))
    causes = [s for s in prog.statements if isinstance(s, CauseStatement)]
    assert len(causes) == 1
    assert causes[0].annotations is not None
    assert causes[0].annotations.source == "llm_proposal"
    assert causes[0].annotations.confidence == 0.6


def test_validator_leaves_annotations_none_when_absent():
    """Back-compat: every pre-A2 program with no ``annotations`` on its
    cause statements must still land as ``annotations=None``."""
    ast = _ast_with_annotated_cause()
    del ast["statements"][2]["annotations"]
    prog = validate_program(validate_ast(ast))
    causes = [s for s in prog.statements if isinstance(s, CauseStatement)]
    assert causes[0].annotations is None


# ============================================================ instantiation

def test_instantiation_preserves_annotations_across_forall_expansion():
    """``forall`` on a cause statement unrolls per-object — each ground
    copy must carry the original annotation, not drop it."""
    x_arg = (VarTerm(name="X"),)
    running_var = Atom(predicate="running", args=x_arg)
    belly_var = Atom(predicate="belly_fat_loss", args=x_arg)
    prog = Program(
        version="0.1",
        objects=("alice", "bob"),
        statements=(
            CauseStatement(
                from_atom=running_var,
                to_atom=belly_var,
                forall=("X",),
                annotations=Annotation(source="llm_proposal"),
            ),
        ),
    )
    ground = instantiate(prog)
    assert len(ground) == 2
    for s in ground:
        assert isinstance(s, CauseStatement)
        assert s.annotations is not None
        assert s.annotations.source == "llm_proposal"
        assert s.forall == ()


# ================================================================== run()

def test_themis_run_accepts_annotated_cause_and_reasons_identically():
    """Annotations are inert to reasoning — status, structural_result,
    and derivation are identical with vs without the annotation.
    ``data_gap_report`` and (Fix 3+4 v0.1.5)
    ``extensions.llm_proposed_review`` deliberately differ: the
    proposal-edge disclosure is the whole point of provenance, and
    the audit channels are the kernel-side guarantee that the
    disclosure surfaces. Covered separately in
    test_unverified_proposal_edge_* (data_gap_report) and
    test_llm_proposed_review_* (Fix 3+4 review surface).
    """
    ast_with = _ast_with_annotated_cause(source="llm_proposal")
    ast_plain = _ast_with_annotated_cause()
    del ast_plain["statements"][2]["annotations"]

    r_with = themis.run(ast_with)["results"][0]
    r_plain = themis.run(ast_plain)["results"][0]

    # Reasoning fields must match exactly — no rule reads annotations.
    # extensions is EXCLUDED here because Fix 3+4 §3.2 adds
    # llm_proposed_review when the source contains "llm" (the whole
    # point of provenance disclosure). Other extension sub-fields are
    # checked individually below to keep the rest of the contract.
    for field in ("status", "query_kind", "query_id", "structural_result",
                  "derivation", "missing_information",
                  "investigation_requests", "framing_notes",
                  "confidence", "numeric_result"):
        assert r_with.get(field) == r_plain.get(field), field
    assert r_with["query_kind"] == "cause"
    assert r_with["status"] == "structurally_solved"

    # Fix 3+4 §3.2: the annotated-llm version surfaces the review;
    # the plain version doesn't (no llm-tagged elements to disclose).
    assert "llm_proposed_review" in (r_with.get("extensions") or {})
    assert "llm_proposed_review" not in (r_plain.get("extensions") or {})


def test_instantiation_lifts_annotation_from_forall_cause_into_every_ground_copy():
    """End-to-end through themis.run with a forall cause edge carrying an
    annotation — validates that the JSON input path threads annotations
    through parse -> validate -> instantiate without loss."""
    ast = {
        "version": "0.1",
        "domain": {
            "objects": [
                {"kind": "object", "name": "alice"},
                {"kind": "object", "name": "bob"},
            ]
        },
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "running",
                         "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "var", "name": "X"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q_alice",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "running",
                             "args": [{"type": "const", "name": "alice"}]},
                    "to": {"predicate": "belly_fat_loss",
                           "args": [{"type": "const", "name": "alice"}]},
                },
            },
        ],
    }
    # Validate via typed pipeline so we can inspect typed Program
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    ground_causes = [s for s in ground if isinstance(s, CauseStatement)]
    # alice + bob = 2 ground edges
    assert len(ground_causes) == 2
    for gc in ground_causes:
        assert gc.annotations is not None
        assert gc.annotations.source == "llm_proposal"

    # End-to-end still runs cleanly.
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


# ====================================== unverified-proposal-edge data gap


def test_unverified_proposal_edge_emits_informational_gap():
    """Real-test caught: rendering layer was the *only* place that read
    `annotations.source = "llm_proposal"` — if the downstream LLM forgot
    to walk `program.statements`, the user got an answer that looked
    independently verified but was actually a self-replay of the LLM's
    own assumption. The gap report now surfaces this as INFORMATIONAL so
    disclosure has a structured signal, not a textual hint."""
    ast = _ast_with_annotated_cause(source="llm_proposal")
    out = themis.run(ast)
    result = out["results"][0]
    report = result["data_gap_report"]
    kinds = [g["kind"] for g in report["gaps"]]
    assert "unverified_proposal_edge_on_query_path" in kinds

    proposal_gap = next(
        g for g in report["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    )
    assert proposal_gap["severity"] == "informational"
    # Description names the actual edge, not a placeholder.
    assert "running" in _gaps.described(proposal_gap)
    assert "belly_fat_loss" in _gaps.described(proposal_gap)

    # Geometric guarantee: the gap is one a reader surface is led with,
    # so a renderer cannot leave it to the bottom of a list.
    assert "running" in caveats.text(result)
    assert "belly_fat_loss" in caveats.text(result)
    assert "llm_proposal" in caveats.text(result)


def test_evidence_backed_edge_does_not_emit_proposal_gap():
    """Companion: edges with a concrete citation (PubMed:..., DOI:...)
    or no annotation at all must not trigger the proposal-edge gap —
    that would muddy the signal and produce false alarms."""
    ast_cite = _ast_with_annotated_cause(source="PubMed:12345")
    ast_plain = _ast_with_annotated_cause()
    del ast_plain["statements"][2]["annotations"]

    for ast in (ast_cite, ast_plain):
        out = themis.run(ast)
        report = out["results"][0].get("data_gap_report")
        kinds = [g["kind"] for g in (report["gaps"] if report else ())]
        assert "unverified_proposal_edge_on_query_path" not in kinds


def test_unverified_proposal_edge_flags_effect_query_via_dag_walk():
    """Effect / identify queries do not expose ``supporting_paths``;
    proposal-edge detection has to walk the program-derived DAG between
    query-relevant predicates instead. Pin: an effect query whose only
    causal pathway is an llm_proposal edge produces the same gap as the
    cause-query case."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "running",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "belly_fat_loss",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert result["query_kind"] == "effect"
    report = result["data_gap_report"]
    kinds = [g["kind"] for g in report["gaps"]]
    assert "unverified_proposal_edge_on_query_path" in kinds


def test_unverified_proposal_edge_flags_mediator_chain():
    """Mediation pathway: X -> M -> Y. Both edges llm_proposal — both
    should be flagged. Mediator predicate enters the relevant set so the
    DFS picks up X→M and M→Y separately."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "m",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "cause",
                "from": {"predicate": "m",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                    "mediator": {"predicate": "m",
                                 "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    report = result["data_gap_report"]
    proposal_gaps = [
        g for g in report["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    ]
    assert len(proposal_gaps) == 2
    descriptions = " ".join(_gaps.described(g) for g in proposal_gaps)
    assert "x" in descriptions and "m" in descriptions and "y" in descriptions


# ============================ an open path, and the arms it walks backward


def _association_through(arms, proposed, given=(), annotations=None):
    """``x`` and ``y`` asked as an association over the cause edges ``arms``,
    the edge ``proposed`` carrying ``annotations``, a language model's unless
    said otherwise."""
    def atom(predicate):
        return {"predicate": predicate,
                "args": [{"type": "const", "name": "me"}]}

    statements: list[dict] = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in sorted({p for arm in arms for p in arm})]
    for a, b in arms:
        statement = {"kind": "cause", "from": atom(a), "to": atom(b)}
        if (a, b) == proposed:
            statement["annotations"] = annotations or {"source": "llm_proposal"}
        statements.append(statement)
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "assoc", "left": atom("x"), "right": atom("y"),
        "given": [atom(p) for p in given]}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


@pytest.mark.parametrize(("arms", "given", "proposed"), [
    pytest.param((("z", "x"), ("z", "y")), (), ("z", "x"),
                 id="fork-arm-the-path-walks-backward"),
    pytest.param((("z", "x"), ("z", "y")), (), ("z", "y"),
                 id="fork-arm-the-path-walks-forward"),
    pytest.param((("z", "a"), ("a", "x"), ("z", "y")), (), ("z", "a"),
                 id="the-far-edge-of-an-arm-the-path-walks-backward"),
])
def test_an_open_path_discloses_every_proposed_edge_it_walks(
        arms, given, proposed):
    """An association found along an open path rests on every edge of it,
    and an open path does not walk them all forward: through a fork it
    walks one arm, however long, against its arrows. The gap matched a
    path's pairs in path order, so a language model's edge there was
    disclosed on one arm and not the other.

    Only edges no directed path between the question's own variables
    carries ask this. An edge into a conditioned-on collider is such a
    path already — the collider is one of the question's variables — and
    was disclosed before the path's direction was read."""
    result = themis.run(_association_through(arms, proposed, given))[
        "results"][0]
    assert result["status"] == "structurally_solved", result["status"]
    assert (result.get("structural_result") or {}).get("supporting_paths"), (
        "the association has to have been found along a path for this to "
        "ask anything")
    cited = [ref["ref_id"]
             for gap in result["data_gap_report"]["gaps"]
             if gap["kind"] == "unverified_proposal_edge_on_query_path"
             for ref in gap["provenance"]
             if ref.get("ref_kind") == "program_site"]
    assert cited == [
        f"program:cause:{proposed[0]}->{proposed[1]}:annotations.source"
    ], cited


# ============================ the graph an answer rests on is the ground one


def _atom_at(predicate, t=None):
    atom = {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _asked(kind, x, y):
    if kind == "cause":
        return {"kind": "cause", "from": x, "to": y}
    return {"kind": "effect", "given": [],
            "intervention": {"atom": x, "value": True},
            "target": {"atom": y, "value": True}}


def _program(statements, names):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": p, "domain": [True, False]}
                for p in sorted(names)] + statements}


def _unrolled(edges, proposed, kind, annotations=None):
    """``x`` a step back and ``y`` now, asked as ``kind``, over cause edges
    ``(a, t_a, b, t_b)``; the edge ``proposed`` carries ``annotations``, a
    language model's unless said otherwise."""
    statements = []
    for a, ta, b, tb in edges:
        statement = {"kind": "cause", "from": _atom_at(a, ta),
                     "to": _atom_at(b, tb)}
        if (a, b) == proposed:
            statement["annotations"] = annotations or {"source": "llm_proposal"}
        statements.append(statement)
    statements.append({"kind": "query", "id": "q", "query": _asked(
        kind, _atom_at("x", -1), _atom_at("y", 0))})
    return _program(statements, {e[0] for e in edges} | {e[2] for e in edges})


def _untimed(edges, proposed):
    """``x`` and ``y`` asked as an effect over plain cause edges."""
    statements = []
    for a, b in edges:
        statement = {"kind": "cause", "from": _atom_at(a), "to": _atom_at(b)}
        if (a, b) == proposed:
            statement["annotations"] = {"source": "llm_proposal"}
        statements.append(statement)
    statements.append({"kind": "query", "id": "q", "query": _asked(
        "effect", _atom_at("x"), _atom_at("y"))})
    return _program(statements, {p for edge in edges for p in edge})


#: ``b`` a step back moves ``a``, which moves ``b`` now: a loop over the
#: predicates, a chain over the ground atoms. The two differ in the ``b``
#: that moves ``y``.
_THROUGH_THE_LOOP = (("x", -1, "b", -1), ("b", -1, "a", -1),
                     ("a", -1, "b", 0), ("b", 0, "y", 0))
_BESIDE_THE_LOOP = (("x", -1, "b", -1), ("b", -1, "a", -1),
                    ("a", -1, "b", 0), ("b", -1, "y", 0))

#: Fifteen atoms beside the direct edge.
_LONG = (("x", "y"), ("x", "n1"),
         *((f"n{i}", f"n{i + 1}") for i in range(1, 13)), ("n13", "y"))

#: Four rungs of three: 81 directed paths nine atoms long, the proposed edge
#: on the last third of them in the order a walk takes them.
_WIDE = (*(("x", f"{c}1") for c in "abc"),
         *((f"{c}{i}", f"j{i}") for i in range(1, 4) for c in "abc"),
         *((f"j{i}", f"{c}{i + 1}") for i in range(1, 4) for c in "abc"),
         *((f"{c}4", "y") for c in "abc"))


def _answer(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _disclosed(result):
    return [ref["ref_id"]
            for gap in (result.get("data_gap_report") or {}).get("gaps") or ()
            if gap["kind"] == "unverified_proposal_edge_on_query_path"
            for ref in gap["provenance"]
            if ref.get("ref_kind") == "program_site"]


@pytest.mark.parametrize("kind", ["cause", "effect"])
def test_a_proposal_on_a_path_through_one_predicate_twice_is_disclosed(kind):
    """The only path from ``x`` to ``y`` passes ``b`` twice, once a step back
    and once now. The edges an answer rests on were looked for among simple
    paths between predicates, where that path is not one: asked as a cause,
    the supporting path on the envelope still named the edge; asked as an
    effect, nothing did."""
    result = _answer(_unrolled(_THROUGH_THE_LOOP, ("a", "b"), kind))
    assert _disclosed(result) == ["program:cause:a->b:annotations.source"]


@pytest.mark.parametrize("kind", ["cause", "effect"])
def test_a_proposal_no_ground_path_runs_through_is_not_disclosed(kind):
    """The same loop with ``y`` moved by ``b`` a step back: ``a -> b`` now
    lies on no path from ``x`` to ``y``. Over the predicates ``x`` still
    reaches ``a`` and ``b`` still reaches ``y``, which is why reachability
    is asked of the ground graph and not of that one."""
    result = _answer(_unrolled(_BESIDE_THE_LOOP, ("a", "b"), kind))
    assert _disclosed(result) == []


@pytest.mark.parametrize(("edges", "proposed"), [
    pytest.param(_LONG, ("n12", "n13"), id="on-a-path-fifteen-atoms-long"),
    pytest.param(_WIDE, ("c1", "j1"), id="on-paths-past-the-thirty-second"),
])
def test_a_proposal_past_any_bound_on_paths_is_disclosed(edges, proposed):
    """The paths were enumerated, at most 32 of them and 12 atoms deep, and
    an edge only a longer or a later path ran through was left off: the
    larger the graph, the fewer edges its answer rested on."""
    result = _answer(_untimed(edges, proposed))
    assert _disclosed(result) == [
        f"program:cause:{proposed[0]}->{proposed[1]}:annotations.source"]


_WEIGHED = {"source": "expert", "confidence": 0.4}


@pytest.mark.parametrize(("program", "weighed"), [
    pytest.param(_association_through((("z", "x"), ("z", "y")), ("z", "x"),
                                      annotations=_WEIGHED),
                 ["edge:z->x"], id="the-arm-an-open-path-walks-backward"),
    pytest.param(_unrolled(_THROUGH_THE_LOOP, ("a", "b"), "effect", _WEIGHED),
                 ["edge:a->b"], id="a-path-through-one-predicate-twice"),
    pytest.param(_unrolled(_BESIDE_THE_LOOP, ("a", "b"), "effect", _WEIGHED),
                 [], id="no-ground-path-runs-through"),
])
def test_a_confidence_is_read_off_the_edges_the_answer_rests_on(
        program, weighed):
    """The confidence an answer is given is the least of those on the edges
    it rests on. That collector walked its own copy of the disclosure's
    paths and carried both of its faults — a supporting path matched in
    path order only, and paths between predicates — so a low confidence on
    such an edge did not reach the answer."""
    result = _answer(program)
    assert [s["slot_label"] for s in result.get("confidence_sources") or ()
            if s["slot_label"].startswith("edge:")] == weighed


def test_every_atom_a_block_names_is_a_node_of_its_graph():
    """An IV route's instrument and what it conditions on, a mediation's
    mediators and adjustment sets, reach the envelope as strings, and what
    an answer rests on reads them back as nodes of the ground graph. One
    spelt so that it matched no node would be an atom the answer silently
    stopped resting on."""
    shapes = json.loads((pathlib.Path(__file__).parent / "fixtures"
                         / "answer_shapes.json").read_text(encoding="utf-8"))
    checked = 0
    for name, shape in sorted(shapes.items()):
        spelt = set(_atoms_the_blocks_name(
            shape["result"].get("extensions") or {}))
        if not spelt:
            continue
        _ast, _prog, _query, ctx = kernel._premises_of(
            shape["program"], shape["result"])
        nodes = {atom_label(node) for node in ctx.graph}
        assert spelt <= nodes, (name, sorted(spelt - nodes))
        checked += 1
    assert checked, "no answer in the corpus names an atom in a block"
