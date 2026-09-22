"""#326 — a selection diagram belongs to ONE source domain.

Bareinboim & Pearl's object is a SET of selection diagrams over one shared
graph: each names a source population and carries the S nodes saying where
THAT source differs from the target. ``source_population`` is a field of
each declared node, and the kernel used to fold every node into a single
diagram and read the first node's population off it. A two-source program
then produced byte-identical output to a one-source program — same
adjustment set, same source tag, same missing parameter — with the second
domain discarded in silence.

The conformance fixture is two source domains that shift DIFFERENT
variables, so the pre-fix behaviour is not merely incomplete but wrong in
a way a reader could act on: folded into one diagram the admissible set is
{z1, z2}, and the honest answer is {z1} for one domain and {z2} for the
other. Each therefore asks for a different conditional in a different
population, which is what says which source to go and get data from.

Several domains that DO transport are several estimands of one target
quantity. Their agreeing is a restriction the supplied distributions could
have failed; their disagreeing refutes at least one declared diagram, and
because theta is declared rather than estimated the difference cannot be
noise. So the withholding is tested beside the number: reporting either of
two conflicting values would choose which diagram to believe.
"""
from __future__ import annotations

import pytest

import themis
from themis import gaps, language
from themis.input.semantic_validator import SemanticError
from themis.kernel import _premises_of
from themis.output import analysis_report
from themis.types import SelectionNode
from themis.verifier import verify_transport_sources
from themis.verifier.errors import VerificationError


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _grounded(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target: str, target_value, given, value: float,
          population: str) -> dict:
    return {
        "kind": "probability",
        "target": _grounded(target, target_value),
        "given": [_grounded(p, v) for p, v in given],
        "value": value,
        "population": population,
    }


#: Both domains carry P(y=1 | do(x=1)) to exactly 0.50 under their own Z,
#: so the two routes agree and the agreement is a test that passed.
_AGREEING_EU_MARGINAL = 0.5
#: Under this one the EU route lands on 0.34, a spread of 0.16 — far past
#: any floating-point drift, so the only reading is that a diagram is wrong.
_DISAGREEING_EU_MARGINAL = 0.9


def _two_source_program(
    *,
    eu_marginal: float = _AGREEING_EU_MARGINAL,
    eu_affects: str = "z2",
    with_theta: bool = True,
    eu_target_population: str = "real_world",
    query_target_population: str = "real_world",
) -> dict:
    """z1 and z2 each confound x → y; the US trial shifts z1, the EU one z2.

    Neither domain's S node says anything about the other's variable, which
    is the whole point: "z differs between the target and THIS source" is a
    claim about a pair of populations and is silent about a third.
    """
    statements: list = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z1", "domain": [True, False]},
        {"kind": "variable", "predicate": "z2", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z1"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z1"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z2"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z2"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "selection_node", "id": "S_us", "affects": _atom("z1"),
         "source_population": "rct_us", "target_population": "real_world"},
        {"kind": "selection_node", "id": "S_eu", "affects": _atom(eu_affects),
         "source_population": "rct_eu",
         "target_population": eu_target_population},
    ]
    if with_theta:
        statements += [
            _prob("y", True, [("x", True), ("z1", True)], 0.40, "rct_us"),
            _prob("y", True, [("x", True), ("z1", False)], 0.60, "rct_us"),
            _prob("y", True, [("x", True), ("z2", True)], 0.30, "rct_eu"),
            _prob("y", True, [("x", True), ("z2", False)], 0.70, "rct_eu"),
            _prob("z1", True, [], 0.5, "real_world"),
            _prob("z2", True, [], eu_marginal, "real_world"),
        ]
    statements.append({
        "kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
            "target_population": query_target_population,
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


def _run(program: dict) -> dict:
    out = themis.run(program)
    result = out["results"][0]
    themis.verify(program, result)
    return result


def _block(result: dict) -> dict:
    return result["extensions"]["transport_identification"]


def _audit(program: dict, result: dict) -> None:
    """The rule with the premises the kernel hands it.

    The block is a copy of three documents, so a call that passed it
    alone would be asking a narrower question than the one that runs —
    and every forgery below would be held by a rule reading its own
    subject's word for what it is a copy of.
    """
    _ast, prog, query_stmt, ctx = _premises_of(program, result)
    verify_transport_sources(
        _block(result), ctx.graph,
        [s for s in prog.statements if isinstance(s, SelectionNode)],
        (result.get("derivation") or {}).get("steps") or (),
        query_stmt.query)


def _by_source(result: dict) -> dict[str, dict]:
    return {r["source_population"]: r for r in _block(result)["sources"]}


def _preds(atoms) -> set[str]:
    return {a["predicate"] for a in atoms}


# ---------------------------------------------------------------- the routes


def test_two_sources_are_two_routes_and_neither_is_the_folded_one():
    """The red counterexample: one diagram holding both S nodes admits only
    {z1, z2}, and each domain on its own admits its own single variable."""
    routes = _by_source(_run(_two_source_program()))
    assert set(routes) == {"rct_us", "rct_eu"}
    assert _preds(routes["rct_us"]["adjustment_set"]) == {"z1"}
    assert _preds(routes["rct_eu"]["adjustment_set"]) == {"z2"}


def test_a_route_owns_only_its_own_selection_nodes():
    """Which nodes ride on which route is what the audit holds the producer
    to, and it is the field the pre-fix code could not have got right."""
    block = _block(_run(_two_source_program()))
    owner = {n["id"]: n["source_population"] for n in block["s_nodes"]}
    assert owner == {"S_us": "rct_us", "S_eu": "rct_eu"}
    for route in block["sources"]:
        assert all(owner[i] == route["source_population"]
                   for i in route["s_nodes"])


def test_each_source_asks_for_its_own_population_and_its_own_conditional():
    """With no distributions supplied, two domains raise two different asks.

    This is the defect's inverse. Before #326 a two-source program produced
    ONE missing parameter, tagged with the first-declared source — so a
    reader with EU data was told to go and get US data.
    """
    result = _run(_two_source_program(with_theta=False))
    assert result["status"] == "structurally_solved"
    asked = {m["said"]["key"] for m in result["missing_information"]}
    assert asked == {"P_rct_us(y=True|x=True,z1=True)",
                     "P_rct_eu(y=True|x=True,z2=True)"}
    populations = {m["observable"]["population"]
                   for m in result["missing_information"]}
    assert populations == {"rct_us", "rct_eu"}


# ------------------------------------------------------- agreeing and not


def test_two_agreeing_sources_report_one_number_and_say_how_many_agreed():
    result = _run(_two_source_program())
    assert result["status"] == "numerically_solved"
    numeric = _block(result)["numeric"]
    assert numeric["agreeing_sources"] == 2
    assert numeric["value"] == pytest.approx(0.5, abs=1e-12)
    per_source = {s: r["numeric"]["value"]
                  for s, r in _by_source(result).items()}
    assert per_source["rct_us"] == pytest.approx(0.5, abs=1e-12)
    assert per_source["rct_eu"] == pytest.approx(0.5, abs=1e-12)


def test_two_disagreeing_sources_report_no_number_at_all():
    """Reporting either value would choose which selection diagram to
    believe, and the choice is not the kernel's to make."""
    result = _run(_two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL))
    assert result["status"] == "structurally_solved"
    assert "numeric_result" not in result
    assert "numeric" not in _block(result)


def test_the_disagreement_is_a_falsification_and_names_the_spread():
    result = _run(_two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL))
    item, = result["missing_information"]
    assert item["gap"] == "transport_sources_disagree"
    assert item["kind"] == "assumption"
    assert float(item["said"]["detail"]) == pytest.approx(0.16, abs=1e-9)


def test_the_conflicting_numbers_stay_on_the_block():
    """The spread is a summary; the two values are the evidence for it, and
    a reader deciding which declaration to withdraw needs them."""
    routes = _by_source(
        _run(_two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL)))
    assert routes["rct_us"]["numeric"]["value"] == pytest.approx(0.5)
    assert routes["rct_eu"]["numeric"]["value"] == pytest.approx(0.34)


def test_the_report_and_the_gap_both_say_a_declaration_was_refuted():
    result = _run(_two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL))
    report = analysis_report.build_analysis_report(result)
    assert "0.5" in report and "0.34" in report
    gap, = [g for g in result["data_gap_report"]["gaps"]
            if g["kind"] == "transport_sources_disagree"]
    sentence, = gap["describes"]
    assert sentence["sentence"] == "the_source_domains_contradict_each_other"
    # The why is a sentence inside a sentence, so it travels as one — the
    # shortfall the kernel filed, rather than a rendering of it made where
    # nobody knew who was reading.
    why = sentence["words"]["why"]
    assert why["vocabulary"] == gaps.NEEDED
    for lang in ("zh", "en"):
        assert language.spoke(why, lang), lang
    assert "否掉了至少" in language.spoke(why, "zh")


def test_no_number_means_no_tier_that_promises_one():
    """The gap and the tier have to agree, and they agree here because the
    tier is derived from the gap rather than asserted beside it."""
    result = _run(_two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL))
    report = result["data_gap_report"]
    assert report["answer_tier"] == "none"
    gap, = [g for g in report["gaps"]
            if g["kind"] == "transport_sources_disagree"]
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "point_estimate"


def test_an_agreeing_pair_keeps_its_point_and_raises_no_such_gap():
    """The counterexample the tier change must NOT catch."""
    report = _run(_two_source_program())["data_gap_report"]
    assert report["answer_tier"] == "point"
    assert not [g for g in report["gaps"]
                if g["kind"] == "transport_sources_disagree"]


# --------------------------------------------------------- a blocked source


def test_a_source_that_cannot_carry_the_effect_is_named_and_the_rest_answer():
    """The EU trial's S node sits on the outcome itself, so no adjustment
    set evens it out — and the US trial still answers."""
    result = _run(_two_source_program(eu_affects="y"))
    assert result["status"] == "numerically_solved"
    routes = _by_source(result)
    assert routes["rct_eu"]["transportable"] is False
    assert routes["rct_eu"]["blocked_by"] == "no_s_admissible_set"
    assert "numeric" not in routes["rct_eu"]
    assert routes["rct_us"]["transportable"] is True
    assert _block(result)["numeric"]["agreeing_sources"] == 1


def test_a_blocked_source_reaches_the_reader_in_words():
    result = _run(_two_source_program(eu_affects="y"))
    report = analysis_report.build_analysis_report(result)
    assert "rct_eu" in report and "搬不过来" in report


def test_no_source_transporting_gives_each_domain_its_own_shortfall():
    """Both S nodes on the outcome: neither domain has an admissible set,
    and the reader is told what each one would have needed rather than
    whichever the loop reached first."""
    base = _two_source_program(with_theta=False)
    result = themis.run({
        **base,
        "statements": [
            s for s in base["statements"] if s.get("kind") != "selection_node"
        ] + [
            {"kind": "selection_node", "id": "S_us", "affects": _atom("y"),
             "source_population": "rct_us", "target_population": "real_world"},
            {"kind": "selection_node", "id": "S_eu", "affects": _atom("y"),
             "source_population": "rct_eu", "target_population": "real_world"},
        ],
    })["results"][0]
    assert result["status"] == "needs_investigation"
    named = {m["name"] for m in result["missing_information"]}
    assert named == {"transport:rct_us->real_world",
                     "transport:rct_eu->real_world"}
    assert all(r["blocked_by"] == "no_s_admissible_set"
               for r in _block(result)["sources"])


# ------------------------------------------------------ one target, refused


def test_selection_nodes_disagreeing_on_the_target_population_are_refused():
    """Several diagrams differ in their SOURCE. Differing in their target is
    one program asserting two incompatible things about where the answer is
    for, and no route through it is more right than the other."""
    with pytest.raises(SemanticError, match="target_population"):
        themis.run(_two_source_program(eu_target_population="other_world"))


def test_a_query_about_a_population_no_diagram_describes_is_refused():
    with pytest.raises(SemanticError, match="real_world|somewhere_else"):
        themis.run(_two_source_program(
            query_target_population="somewhere_else"))


def test_one_target_population_is_not_refused_for_differing_sources():
    """The counterexample the gate must NOT catch: two sources, one target
    is the case the whole item exists to support."""
    assert _run(_two_source_program())["status"] == "numerically_solved"


# ----------------------------------------------------------------- the audit


def test_the_audit_rejects_a_criterion_step_spanning_two_source_populations():
    """Before #326 both sides of this boundary folded every declared node
    into one diagram, so the duplication was not independence — it was the
    same wrong belief held twice, and an audit cannot catch a mistake it
    shares."""
    program = _two_source_program()
    result = themis.run(program)["results"][0]
    for step in result["derivation"]["steps"]:
        if step["rule"] == "s_admissibility_check":
            step["inputs"]["selection_nodes_ids"] = "S_us,S_eu"
            break
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_the_audit_rejects_a_number_a_transporting_source_contradicts():
    program = _two_source_program()
    result = _run(program)
    _block(result)["sources"][1]["numeric"]["value"] = 0.34
    with pytest.raises(VerificationError, match="refute"):
        _audit(program, result)


def test_the_audit_rejects_a_withheld_number_the_sources_agree_on():
    """The withholding is a claim too, and this is the one that hides a
    number rather than inventing one."""
    program = _two_source_program(eu_marginal=_DISAGREEING_EU_MARGINAL)
    result = _run(program)
    _block(result)["sources"][1]["numeric"]["value"] = 0.5
    with pytest.raises(VerificationError, match="agree"):
        _audit(program, result)


def test_the_audit_rejects_a_miscounted_agreement():
    program = _two_source_program()
    result = _run(program)
    _block(result)["numeric"]["agreeing_sources"] = 3
    with pytest.raises(VerificationError, match="agreeing sources"):
        _audit(program, result)


def test_the_audit_rejects_a_number_credited_to_a_blocked_source():
    program = _two_source_program(eu_affects="y")
    result = _run(program)
    _block(result)["numeric"]["source_population"] = "rct_eu"
    with pytest.raises(VerificationError, match="not one of the sources"):
        _audit(program, result)


def test_the_audit_rejects_a_node_riding_on_another_domains_route():
    program = _two_source_program()
    result = _run(program)
    _block(result)["sources"][0]["s_nodes"] = ["S_us", "S_eu"]
    with pytest.raises(VerificationError, match="belongs to one source"):
        _audit(program, result)


def test_the_audit_rejects_a_blocking_reason_outside_the_vocabulary():
    program = _two_source_program(eu_affects="y")
    result = _run(program)
    _block(result)["sources"][1]["blocked_by"] = "the_data_was_sad"
    with pytest.raises(VerificationError, match="ways a source domain"):
        _audit(program, result)


def test_the_audit_does_not_import_the_producer():
    """The two constants this audit turns on — the tolerance and the two
    ways a domain can be blocked — are transcribed here, because a shared
    constant is a shared belief and this rule exists to hold one."""
    import themis.verifier.verify as verify_mod

    with open(verify_mod.__file__, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith(
                ("from themis.runtime.transport", "from ..runtime.transport",
                 "import themis.runtime.transport")), (
                f"line {lineno}: {stripped!r}"
            )


# --------------------------------------------------------- the closed word


def test_the_browser_holds_a_word_for_every_way_a_source_is_blocked():
    from themis.runtime.transport import TRANSPORT_BLOCKED_KINDS
    from tests import web_source

    table = web_source.words_map("TRANSPORT_BLOCKED_WORDS",
                                 web_source.read(web_source.GENERATED))
    assert set(table) == set(TRANSPORT_BLOCKED_KINDS)
