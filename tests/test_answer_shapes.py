"""An estimate says its answer in its own shape, or says it has none.

Before this vocabulary existed the answer slot recovered an estimate's shape
by probing field names in order, and the last branch of that chain was the
structural verdict — which always has a value. One instrumented suite run
measured the consequence: 459 estimates, 93 with no ``point``, and 84 of those
rendered to the reader as ``结论：是`` while their numbers sat in the same
block under ``dose_response_curve`` (29), ``decomposition`` (29),
``joint_effect`` (17) and ``counterfactual_cell`` (11).

The tests below hold the two halves of the repair: the vocabulary covers the
declared method enum exactly and every surface covers the vocabulary exactly
(so a new shape or method fails at import), and an estimate in each shape
reaches the reader as that shape rather than as a claim about the graph.
"""
import json
import pathlib

import pytest

from themis import answers
from themis.output.analysis_report import _render_answer

SCHEMA = json.loads(
    (pathlib.Path(__file__).resolve().parent.parent
     / "themis" / "schemas" / "query_result.schema.json").read_text(encoding="utf-8")
)


def _schema_methods() -> set[str]:
    defs = SCHEMA.get("$defs", {})
    node = SCHEMA["properties"]["numeric_estimate"]
    if "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return set(node["properties"]["method"]["enum"])


# --- the vocabulary is closed in both directions -----------------------------


def test_every_declared_method_has_an_answer_shape():
    """A method with no shape is an estimate that reaches a surface and says
    nothing — the silence measured above, one method at a time."""
    missing = sorted(_schema_methods() - set(answers.SHAPES_OF))
    assert not missing, (
        f"{missing} can be emitted but declares no answer shape"
    )


def test_no_shape_is_declared_for_a_method_that_cannot_be_emitted():
    """A shape for a method outside the enum is a renderer no estimate can
    reach: dead copy that reads like coverage."""
    extra = sorted(set(answers.SHAPES_OF) - _schema_methods())
    assert not extra, (
        f"{extra} declare answer shapes but are not in the method enum"
    )


def test_a_surface_that_misses_a_shape_is_refused_at_import():
    with pytest.raises(ValueError, match="no renderer for answer shape"):
        answers.bind({s: str for s in answers.ALL if s is not answers.POINT})


def test_a_surface_that_binds_a_shape_nobody_declares_is_refused():
    stray = answers.Shape("invented", carries="nothing", lives_in="nowhere")
    with pytest.raises(ValueError, match="not a declared answer shape"):
        answers.bind({**{s: str for s in answers.ALL}, stray: str})


def test_an_undeclared_method_is_loud_rather_than_defaulted():
    with pytest.raises(answers.UnknownMethod):
        answers.shape_of({"method": "no_such_estimator", "point": 1.0})


def test_the_sharper_shape_wins_when_monotonicity_supplied_one():
    """Both bimodal methods declare the point first: it answers the same
    question the bounds do, only sharply."""
    for method in ("causation_plugin", "counterfactual_cell_plugin"):
        shapes = answers.SHAPES_OF[method]
        assert len(shapes) == 2 and shapes[0] is answers.POINT, method


# --- an estimate in each shape reaches the reader as that shape --------------


def _result(estimate: dict) -> dict:
    """An estimate beside a structural verdict — the arrangement that made
    the substitution possible. Every case below carries the ``True`` that
    used to be rendered in the answer's place."""
    return {
        "status": "structurally_solved",
        "numeric_estimate": {"sample_size": 100, "ci_level": 0.95, **estimate},
        "structural_result": {"value": True},
    }


def _band(point):
    return {"point": point, "ci_lower": point - 0.1, "ci_upper": point + 0.1}


SHAPED = {
    "dose_response_linear_dml": (
        {"dose_response_curve": [{"x": 1.0, "effect": 0.25,
                                  "ci_lower": 0.2, "ci_upper": 0.3}],
         "reference_point": 0.0},
        "0.25",
    ),
    "mediation_linear_imai": (
        {"decomposition": {"te": _band(0.5), "nde": _band(0.2),
                           "nie": _band(0.3),
                           "proportion_mediated": _band(0.6)}},
        "0.3",
    ),
    "joint_backdoor_linear": (
        {"joint_effect": {**_band(1.5), "treated": {"a": True, "b": True},
                          "control": {"a": False, "b": False}},
         "interaction": {**_band(0.4), "order": 2, "scale": "difference"}},
        "1.5",
    ),
    "counterfactual_cell_plugin": (
        {"counterfactual_cell": {"lower": 0.1, "upper": 0.4,
                                 "adjustment": ["z"]}},
        "0.4",
    ),
    "causation_plugin": (
        {"probabilities_of_causation": {
            "pn": {"lower": 0.2, "upper": 0.6},
            "ps": {"lower": 0.1, "upper": 0.5},
            "pns": {"lower": 0.05, "upper": 0.3}}},
        "0.6",
    ),
}


@pytest.mark.parametrize("method", sorted(SHAPED))
def test_an_answer_shape_is_not_rendered_as_a_claim_about_the_graph(method):
    estimate, expected = SHAPED[method]
    line = _render_answer(_result({"method": method, **estimate}))
    assert not line.startswith("结论："), (
        f"{method} rendered the structural verdict in the answer slot"
    )
    assert expected in line, f"{method} rendered no number: {line!r}"


@pytest.mark.parametrize("method", sorted(SHAPED))
def test_every_shape_carries_the_lines_a_point_estimate_carries(method):
    """Method and sample size travel with every shape. The four that used to
    render nothing had, by construction, none of this either."""
    line = _render_answer(_result({"method": method, **SHAPED[method][0]}))
    assert f"`{method}`" in line and "N=100" in line


def test_a_point_estimate_still_leads_with_its_number():
    line = _render_answer(_result(
        {"method": "backdoor_linear", "point": 0.31,
         "ci_lower": 0.2, "ci_upper": 0.4},
    ))
    assert line.startswith("**0.31**")


def test_an_estimate_with_no_answer_says_so_instead_of_borrowing_the_verdict():
    """The one case the table cannot rule out: a block in a declared shape's
    method that carries none of it. It must not fall to the verdict below."""
    line = _render_answer(_result({"method": "backdoor_linear"}))
    assert not line.startswith("结论：")
    assert "没有任何可呈现的答案" in line


def test_a_structural_query_still_reads_as_its_verdict():
    """The verdict is the answer where the question was about the graph; it
    lost only the estimates it was standing in for."""
    line = _render_answer({
        "status": "structurally_solved",
        "structural_result": {"value": True},
    })
    assert line.startswith("结论：")


# --- the surface that cannot import the table ---------------------------------


WEB_ANSWER_SURFACE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "themis" / "web" / "frontend" / "src" / "lib" / "verdict.ts"
)


@pytest.mark.parametrize("shape", answers.ALL, ids=lambda s: s.name)
def test_the_web_reads_every_shape_the_kernel_can_answer_in(shape):
    """The browser renders from TypeScript and cannot bind to the table, so
    the vocabulary is checked against it by name instead.

    This is the weaker of the two guarantees and is stated as such: ``bind``
    proves the report has a renderer, this proves only that the web names the
    key. It is still the difference between the four shapes that reached the
    browser as a single em-dash and four that do not.
    """
    source = WEB_ANSWER_SURFACE.read_text(encoding="utf-8")
    assert shape.lives_in in source, (
        f"answer shape {shape.name} lives in numeric_estimate."
        f"{shape.lives_in}, which {WEB_ANSWER_SURFACE.name} never reads"
    )
