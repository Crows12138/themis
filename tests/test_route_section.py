"""The report says how the answer was arrived at, not only what it is.

The report had six sections and none of them was that one. Ten blocks
exist to say it — 369 of them across one suite run: ``transport_
identification`` 75, ``identification`` 53, ``mediation_decomposition``
50, ``selection_recovery`` 40, ``missing_data_recovery`` 39,
``iv_identification`` 31, ``mediation_joint_decomposition`` 28,
``joint_identification`` 26, ``longitudinal_identification`` 19,
``proximal_estimand`` 8 — and ``analysis_report`` read exactly one
extensions key, so not one of them ever reached a reader.

The tests below hold both halves. The registry side (which blocks are
routes, that a surface must cover them, and that the browser states the
same ones in the same order) lives in ``test_blocks_registry.py`` beside
the vocabulary it checks; here is what a reader actually gets: every
route says its own identifying facts, the section appears only when there
is a route to state, and it sits where a reader looks for it.
"""
import pytest

from themis import blocks
from themis.output.analysis_report import build_analysis_report, _render_route
from themis import language

# One realistic payload per route, and the facts a reader must not lose.
# Written against the producers' shapes rather than the schema: eleven of
# the twenty blocks have no sub-schema, which is the drift the registry
# exists to end and not something to assert a shape from.
ROUTES = {
    # The reduction is IN the fixture because the block's second line is what
    # it exists for: a reader looking at a Wald ratio on a graph whose
    # back-door set is plainly sitting there has no other way to learn the
    # set was withdrawn rather than overlooked.
    blocks.Block.FEEDBACK_LOOP: (
        {"left": "price", "right": "demand", "treatment": "price",
         "outcome": "demand", "withdrew": ["backdoor"],
         "reduction": "simultaneous_equations"},
        ("price", "demand", "工具变量"),
    ),
    blocks.Block.IDENTIFICATION: (
        {"pattern": "backdoor", "adjustment_set": ["z", "w"]},
        ("后门", "z", "w"),
    ),
    blocks.Block.IV_IDENTIFICATION: (
        {"strategy": "iv", "instrument": "z", "conditioning": ["w"],
         "required_assumption": "monotonicity", "alternatives_count": 3,
         "late_caveat": "Wald 比给的是依从者的 LATE。"},
        ("z", "w", "3", "LATE"),
    ),
    # An instrument that moves nothing is in the fixture on purpose: it is
    # the case the block exists to be able to state, and the one a renderer
    # written from the happy path drops.
    blocks.Block.VECTOR_IV_IDENTIFICATION: (
        {"kind": "vector_iv_identification", "treatments": ["a", "b"],
         "outcome": "y", "instruments": ["z1", "z2"], "conditioning": ["w"],
         "relevance": [{"instrument": "z1", "moves": ["a"]},
                       {"instrument": "z2", "moves": []}],
         "reference": "Anderson & Rubin 1949"},
        ("a", "b", "z1", "z2", "w", "都不移动"),
    ),
    blocks.Block.TRANSPORT_IDENTIFICATION: (
        {"kind": "transport_identification", "target_population": "clinic",
         "s_nodes": [{"id": "s1", "source_population": "trial",
                      "affects": {"predicate": "age"}}],
         "sources": [{"source_population": "trial", "s_nodes": ["s1"],
                      "transportable": True,
                      "adjustment_set": [{"predicate": "age"}],
                      "formula_repr": "…"}]},
        ("trial", "clinic", "age"),
    ),
    blocks.Block.JOINT_IDENTIFICATION: (
        {"pattern": "joint_backdoor", "treatments": ["a", "b"],
         "adjustment_set": ["z"], "interaction": "difference_scale"},
        ("a", "b", "z", "交互"),
    ),
    blocks.Block.LONGITUDINAL_IDENTIFICATION: (
        {"estimand": "time_varying_strategy_contrast",
         "treatments": ["a0", "a1"], "outcome": "y",
         "confounders_by_time": [["l0"], ["l1"]], "identified": True,
         "assumptions": ["sequential_exchangeability"]},
        ("a0", "a1", "y", "l0", "l1"),
    ),
    blocks.Block.MEDIATION_DECOMPOSITION: (
        {"mediator": "m", "mediator_valid": True,
         "nde_nie": {"identifiable": True, "adjustment": ["z"],
                     "failed_condition": None},
         "cde": {"identifiable": False, "adjustment": [],
                 "failed_condition": "no back-door set for M→Y"},
         "strategy": "nde_nie"},
        ("m", "NDE", "CDE", "z", "no back-door set for M→Y"),
    ),
    blocks.Block.MEDIATION_JOINT_DECOMPOSITION: (
        {"mediators": ["m1", "m2"], "mediator_set_valid": True,
         "nde_nie": {"identifiable": True, "adjustment": ["z"],
                     "failed_condition": None},
         "cde": {"identifiable": True, "adjustment": ["z"],
                 "failed_condition": None},
         "strategy": "nde_nie+cde"},
        ("m1", "m2", "NDE", "CDE"),
    ),
    blocks.Block.PROXIMAL_ESTIMAND: (
        {"method": "miao_2018_model_f", "treatment": "x", "outcome": "y",
         "latent": "u", "treatment_proxy": "zp", "outcome_proxy": "wp",
         "channel_kind": "discrete_channel", "latent_cardinality": 2,
         "data_conditions": "P(w|z) invertible"},
        ("u", "zp", "wp", "P(w|z) invertible"),
    ),
    # Both recovery blocks state their prose rather than carrying it, so
    # the strings this expects are the ones the READER assembles from a
    # token and this occasion's facts.
    blocks.Block.SELECTION_RECOVERY: (
        {"kind": "selection_recovery", "recoverable": False,
         "selection_nodes": ["s"], "adjustment_set": [],
         "external_data_needed": [
             {"vocabulary": "unbiased_distribution", "token": "unbiased",
              "said": {"expression": "P(s)"}}],
         "complete_criterion": True,
         "failure_reason": {
             "vocabulary": "selection_recovery_shortfall",
             "token": "outcome_not_separable_from_selection",
             "said": {"treatment": "x", "outcome": "y"}}},
        ("s", "与选择节点不可 d-分离", "P(s)"),
    ),
    blocks.Block.MISSING_DATA_RECOVERY: (
        {"kind": "missing_data_recovery", "mechanism": "MAR",
         "partially_observed": ["y"], "complete_criterion": False,
         "estimand": {"recoverable": True,
                      "requires": [
                          {"vocabulary": "recovery_factor",
                           "token": "adjusted_conditional",
                           "said": {"target": "P(y | x, z)"}},
                          {"vocabulary": "recovery_factor",
                           "token": "covariate_marginal",
                           "said": {"target": "P(z)"}}]}},
        ("MAR", "y", "协变量边缘分布 P(z)"),
    ),
}


def _result(**extensions) -> dict:
    # ``query_kind`` is required by ``query_result.schema.json`` and the
    # report now reads it (a structural boolean means a different thing per
    # kind of question), so a fixture without one is an envelope that
    # cannot occur.
    return {
        "status": "structurally_solved",
        "query_kind": "effect",
        "structural_result": {"value": True},
        "extensions": dict(extensions),
    }


def test_the_fixtures_cover_the_family():
    """A route added to the registry without a case here would be checked
    by ``bind`` for having a renderer and by nothing at all for what that
    renderer says."""
    assert set(ROUTES) == set(blocks.declared_as(blocks.Family.ROUTE))


@pytest.mark.parametrize("block", sorted(ROUTES), ids=str)
def test_a_route_reaches_the_reader_with_its_identifying_facts(block):
    payload, expected = ROUTES[block]
    text = _render_route(_result(**{block: payload}), lang=language.DEFAULT)
    assert text, f"{block} produced no line"
    missing = [token for token in expected if token not in text]
    assert not missing, f"{block} dropped {missing} from: {text!r}"


@pytest.mark.parametrize("block", sorted(ROUTES), ids=str)
def test_every_route_appears_in_the_assembled_report(block):
    payload, _expected = ROUTES[block]
    report = build_analysis_report(_result(**{block: payload}))
    assert "## 怎么算出来的" in report


def test_a_result_with_no_route_gets_no_empty_section():
    """The section is the answer's provenance; a heading over nothing is a
    promise the envelope did not make."""
    report = build_analysis_report(_result())
    assert "怎么算出来的" not in report
    assert _render_route(_result(), lang=language.DEFAULT) == ""


def test_the_route_sits_between_the_answer_and_the_model():
    """A reader's next question after a number is how it was obtained; the
    graph is the reference material they check that against."""
    payload, _ = ROUTES[blocks.Block.IDENTIFICATION]
    report = build_analysis_report(
        _result(**{blocks.Block.IDENTIFICATION: payload}),
        program={"statements": []},
    )
    assert (report.index("## 答案")
            < report.index("## 怎么算出来的")
            < report.index("## 因果模型"))


def test_routes_are_stated_in_registry_order():
    """Two routes on one result read in the order the registry declares,
    not in whatever order the envelope's dict happened to be built."""
    ident, _ = ROUTES[blocks.Block.IDENTIFICATION]
    missing, _ = ROUTES[blocks.Block.MISSING_DATA_RECOVERY]
    result = _result()
    # Inserted the other way round on purpose.
    result["extensions"][blocks.Block.MISSING_DATA_RECOVERY] = missing
    result["extensions"][blocks.Block.IDENTIFICATION] = ident
    text = _render_route(result, lang=language.DEFAULT)
    assert text.index("识别模式") < text.index("缺失数据")


def test_a_route_does_not_repeat_what_the_line_above_it_already_said():
    """The IV block's instrument is copied into ``identification`` by the
    producer, which calls that copy the human surface. On a real
    structurally-identified IV run with one candidate that left the second
    bullet saying only what the first had: ``- **工具变量**：`z(me)```."""
    ident = {"pattern": "instrumental_variable", "instrument": "z",
             "required_assumption": "monotonicity"}
    iv = {"strategy": "iv", "instrument": "z", "conditioning": [],
          "required_assumption": "monotonicity", "alternatives_count": 1}
    text = _render_route(_result(**{blocks.Block.IDENTIFICATION: ident,
                                    blocks.Block.IV_IDENTIFICATION: iv}), lang=language.DEFAULT)
    assert text.count("工具变量") == 1, text
    assert "\n" not in text.strip(), f"an empty bullet survived: {text!r}"

    # …and the instrument is NOT lost where nothing else states it: the
    # numeric IV path emits the block on its own.
    alone = _render_route(_result(**{blocks.Block.IV_IDENTIFICATION: iv}), lang=language.DEFAULT)
    assert "z" in alone


def test_an_unrecognised_pattern_is_named_rather_than_dropped():
    """The section exists because something said nothing. A name a reader
    has to look up still beats a sentence that omits it."""
    text = _render_route(
        _result(**{blocks.Block.IDENTIFICATION: {"pattern": "some_new_criterion"}})
    , lang=language.DEFAULT)
    assert "some_new_criterion" in text
