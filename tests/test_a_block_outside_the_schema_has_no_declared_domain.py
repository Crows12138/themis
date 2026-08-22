"""What a block carries out of the kernel, and where its domain is stated.

The registry made the block's NAME first-class and checked it both ways.
What a block CARRIES was never asked about at all, and the only place those
domains were ever written down was the result schema, populated block by
block by whoever remembered. Measured over one suite run: eighteen blocks
declared, ten with a sub-schema, and the eight without emitting 829
instances between them. Two of those eight carried a field whose sibling
block enumerates the same field name with members that no longer agreed —
``joint_identification.pattern`` against ``identification.pattern`` (the two
sets are disjoint, and both reader surfaces branch on ``joint_general_id``
by spelling the literal), and ``mediation_joint_decomposition.strategy``,
whose only observed value in the whole corpus is ``nde_nie+cde``, the one
member its single-mediator twin's enum has no room for.

What is pinned here:

- the two producers really emit those blocks, and what they emit validates;
- every enum the eight entries declare is REACHED by validation rather than
  merely written — the silent failure is an enum sitting under a nesting or
  a ``$ref`` that never applies, which reads exactly like a domain that is
  being enforced;
- the divergences are stated as facts, so a later tidying that merges two
  vocabularies sharing a field name fails here;
- the display copies are references, not second statements;
- and ``ambiguities`` stays open, because what it carries is authored
  upstream by a caller and enumerating it would make the kernel the
  authority on which ambiguities a caller may report — the one block for
  which that is true, which is now asked of every block rather than said
  in prose about the fixtures above. It was said here first and went
  unchecked, and while it did, four blocks were open and one of them had
  accumulated a field with a writer, no reader, and no declaration.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import blocks
from themis.input.syntactic_validator import SyntacticError, validate_result

SCHEMA = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "themis" / "schemas" /
     "query_result.schema.json").read_text(encoding="utf-8"))
EXT = SCHEMA["properties"]["extensions"]["properties"]


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _wrap(name, body):
    return {"query_id": "q", "status": "structurally_solved",
            "query_kind": "effect", "extensions": {name: body}}


def _rejects(name, body) -> bool:
    try:
        validate_result(_wrap(name, body))
    except SyntacticError:
        return True
    return False


# --- the two producers whose vocabularies had drifted -------------------------


@pytest.fixture(scope="module")
def joint_result():
    """do(a, b) on a graph where one set blocks both back doors."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in ("a", "b", "z", "y")
        ] + [
            {"kind": "cause", "from": _atom("z"), "to": _atom("a")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("b")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("a"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("b"), "to": _atom("y")},
            {"kind": "query", "id": "qj", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("a"), "value": True},
                "extra_interventions": [{"atom": _atom("b"), "value": True}],
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }
    return themis.run(program)["results"][0]


@pytest.fixture(scope="module")
def mediation_joint_result():
    """Two parallel mediators taken as one block."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in ("x", "m1", "m2", "y")
        ] + [
            {"kind": "cause", "from": _atom("x"), "to": _atom("m1")},
            {"kind": "cause", "from": _atom("m1"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m2")},
            {"kind": "cause", "from": _atom("m2"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": [],
                "mediators": [_atom("m1"), _atom("m2")]}},
        ],
    }
    return themis.run(program)["results"][0]


def test_the_joint_route_emits_the_pattern_no_one_had_declared(joint_result):
    block = (joint_result.get("extensions") or {}).get("joint_identification")
    assert block is not None
    assert block["pattern"] == "joint_backdoor"
    validate_result(joint_result)


def test_the_mediator_set_route_claims_both_arms(mediation_joint_result):
    """The member the single-mediator vocabulary cannot express, from the
    producer rather than from the schema — a set can have both arms
    identifiable, and saying so is the whole reason this field differs."""
    block = (mediation_joint_result.get("extensions") or {}
             ).get("mediation_joint_decomposition")
    assert block is not None
    assert block["strategy"] == "nde_nie+cde"
    validate_result(mediation_joint_result)


# --- the domains, and whether validation reaches them -------------------------

TRANSPORT = {
    "kind": "transport_identification",
    "source_population": "trial",
    "target_population": "user",
    "s_nodes": [{"id": "s_z", "affects": _atom("z")}],
    "adjustment_set": [_atom("z")],
    "formula_repr": "P*(y | do(x)) = Σ_{z} P(y | do(x), z) · P*(z)",
}
JOINT = {
    "pattern": "joint_backdoor",
    "treatments": ["a(me)", "b(me)"],
    "adjustment_set": ["z(me)"],
    "interaction": "difference_scale",
}
ARM = {"identifiable": True, "adjustment": [], "failed_condition": None,
       "assumptions": []}
MEDIATION_JOINT = {
    "mediators": ["m1(me)", "m2(me)"],
    "mediator_set_valid": True,
    "strategy": "nde_nie+cde",
    "nde_nie": copy.deepcopy(ARM),
    "cde": copy.deepcopy(ARM),
}
PROXIMAL = {
    "method": "proximal_matrix", "treatment": "x()", "outcome": "y()",
    "latent": "u()", "treatment_proxy": "z()", "outcome_proxy": "w()",
    "latent_cardinality": 2, "data_conditions": "rank: P(W|Z,x) invertible",
}
CELL = {
    "observed_x": True, "counterfactual_x": False, "target_y": False,
    "factual_y": True, "monotonicity": None,
    "interventional_risk_provenance": "backdoor_adjustment",
    "observational_joint": {"p_x1_y1": 0.38, "p_x1_y0": 0.13,
                            "p_x0_y1": 0.14, "p_x0_y0": 0.35},
    "lower": 0.0, "upper": 1.0,
    # Said, not left out: this cell has no instrument, no arm and no point,
    # and the container answers each of those questions rather than letting
    # a missing key stand in for the answer.
    "instrument": None, "p_y_do_x_cf": None,
    "point": None, "ci_lower": None, "ci_upper": None,
}
MECHANISM = {
    "mechanisms": [{"target": "y", "form": "linear", "method": "backdoor_linear",
                    "provenance": "default",
                    "assumptions": ["linear_outcome_regression"]}],
    "summary": "这个数字依赖假设出来的函数形式",
}
TYPES = {
    "checks": [{
        "predicate": "x", "declared_scale": "binary",
        "declared_domain": [True, False], "observed_scale": "continuous",
        "n_unique": 37, "observed_values": None, "dtype_kind": "float",
        "verdict": "domain_violated", "detail": "declared binary, 37 levels",
    }],
}
AMBIGUITIES = [{"kind": "llm_declared_ambiguity",
                "description": "two candidate mediators, undecided"}]

HAND_BUILT = {
    "transport_identification": TRANSPORT,
    "joint_identification": JOINT,
    "mediation_joint_decomposition": MEDIATION_JOINT,
    "proximal_estimand": PROXIMAL,
    "counterfactual_cell": CELL,
    "mechanism_audit": MECHANISM,
    "ambiguities": AMBIGUITIES,
    "type_reconciliation": TYPES,
}


@pytest.mark.parametrize("name", sorted(HAND_BUILT))
def test_the_shape_the_entry_declares_is_one_a_producer_can_fill(name):
    """The other half of every rejection test below: a schema that says no
    to everything says nothing."""
    validate_result(_wrap(name, HAND_BUILT[name]))


# (block, path to the field, a value outside its domain, what it means)
OUT_OF_DOMAIN = [
    ("transport_identification", ("kind",), "transport"),
    ("joint_identification", ("pattern",), "backdoor"),
    ("joint_identification", ("interaction",), "ratio_scale"),
    ("mediation_joint_decomposition", ("strategy",), "nde_nie+cde+none"),
    ("mediation_joint_decomposition", ("nde_nie", "failed_condition"), "C1"),
    ("mediation_joint_decomposition", ("cde", "failed_condition"), "M1"),
    ("counterfactual_cell", ("monotonicity",), "increasing"),
    ("counterfactual_cell", ("interventional_risk_provenance",), "guessed"),
    ("mechanism_audit", ("mechanisms", 0, "provenance"), "estimator_declared"),
    ("type_reconciliation", ("checks", 0, "declared_scale"), "ordinal"),
    ("type_reconciliation", ("checks", 0, "observed_scale"), "ordinal"),
    ("type_reconciliation", ("checks", 0, "dtype_kind"), "datetime"),
    ("type_reconciliation", ("checks", 0, "verdict"), "ok"),
]


@pytest.mark.parametrize("name,path,value", OUT_OF_DOMAIN)
def test_a_value_outside_the_domain_is_refused(name, path, value):
    """Reached, not merely written.

    An enum under a nesting validation never visits reads exactly like a
    domain that is being enforced, and the two arms below are why this is
    asked one field at a time: they share a shape and a producer but not a
    vocabulary, so a reference to the wrong one still validates everything
    the corpus happens to contain.
    """
    body = copy.deepcopy(HAND_BUILT[name])
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert _rejects(name, body), (
        f"{name}.{'.'.join(str(p) for p in path)} accepted {value!r}")


@pytest.mark.parametrize("name", ["transport_identification",
                                  "proximal_estimand", "mechanism_audit",
                                  "type_reconciliation"])
def test_a_field_the_block_promises_cannot_be_dropped(name):
    body = copy.deepcopy(HAND_BUILT[name])
    required = EXT[name]["required"]
    for field in required:
        missing = {k: v for k, v in body.items() if k != field}
        assert _rejects(name, missing), f"{name} shipped without {field!r}"


# --- the divergences, stated so a tidying cannot quietly undo them ------------


def test_the_two_pattern_vocabularies_are_not_one():
    """Same field name, disjoint domains, and that is correct: a joint
    back-door and a back-door are not the same sentence to a reader, and
    the report and the browser say different things for them."""
    single = set(EXT["identification"]["properties"]["pattern"]["enum"])
    joint = set(EXT["joint_identification"]["properties"]["pattern"]["enum"])
    assert single and joint
    assert not (single & joint)


def test_the_set_route_can_say_what_the_single_route_cannot():
    single = set(EXT["mediation_decomposition"]["properties"]["strategy"]["enum"])
    joint = set(
        EXT["mediation_joint_decomposition"]["properties"]["strategy"]["enum"])
    assert "nde_nie+cde" in joint
    assert "nde_nie+cde" not in single
    assert single < joint


@pytest.mark.parametrize("pointer,field", [
    ("#/properties/numeric_estimate/properties/counterfactual_cell",
     ("counterfactual_cell",)),
    ("#/properties/extensions/properties/mediation_decomposition/properties/nde_nie",
     ("mediation_joint_decomposition", "properties", "nde_nie")),
    ("#/properties/extensions/properties/mediation_decomposition/properties/cde",
     ("mediation_joint_decomposition", "properties", "cde")),
    ("#/properties/extensions/properties/mediation_decomposition/properties/numeric",
     ("mediation_joint_decomposition", "properties", "numeric")),
])
def test_a_display_copy_is_a_reference_and_not_a_second_statement(pointer, field):
    """One dict is written into both places, and one evaluator fills both
    numerics. A second statement of the same shape is how the same field
    name came to carry ``general_id_plug_in`` in one place and not in its
    neighbour."""
    node = EXT
    for key in field:
        node = node[key]
    assert node.get("$ref") == pointer


# The blocks whose map is open, and the argument for each. This used to
# be the sentence below rather than a check, and while it went unchecked
# four blocks were open: what came in through one of those openings was
# ``scm_counterfactual.estimated_from_data``, one writer, no reader, no
# declaration. A block open to anything cannot report a field nobody
# decided to carry, which is exactly the field it will accumulate.
OPEN_ON_PURPOSE = {
    "ambiguities": "authored upstream by a caller, so enumerating it would "
                   "make the kernel the authority on which ambiguities a "
                   "caller may report",
}


def test_every_block_we_emit_is_closed_but_the_one_that_argues_for_it():
    """Blocks that are a ``$ref`` are excluded rather than exempt: their
    shape is stated where they point, and
    ``test_a_display_copy_is_a_reference_and_not_a_second_statement``
    holds them to pointing there."""
    open_now = {
        name for name, spec in EXT.items()
        if "$ref" not in spec and spec.get("additionalProperties") is not False
    }
    assert open_now == set(OPEN_ON_PURPOSE), (
        f"open without an argument: {sorted(open_now - set(OPEN_ON_PURPOSE))}; "
        f"closed while claiming one: "
        f"{sorted(set(OPEN_ON_PURPOSE) - open_now)}")


def test_the_block_authored_upstream_stays_open():
    """The counterexample this gate has to keep saying yes to.

    Every other block got a closed shape. This one must not: its entries
    are copied across from the program's own side-channel, where a caller
    or a language model wrote them, and a kernel that enumerated ``kind``
    would be deciding which ambiguities a caller is allowed to report.
    """
    entry = EXT["ambiguities"]
    assert entry["items"].get("additionalProperties") is not False
    assert "enum" not in entry["items"]["properties"]["kind"]
    exotic = [{"kind": "something_this_kernel_never_heard_of",
               "whatever": {"nested": True}}]
    validate_result(_wrap("ambiguities", exotic))


def test_every_block_the_registry_declares_now_has_a_domain_to_check():
    """The premise the rest of the file rests on, from the registry rather
    than from the list above."""
    assert set(blocks.Block) == set(EXT)
