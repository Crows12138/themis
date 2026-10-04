"""A result shown under an edited graph says it is the old graph's.

#813. The result page draws the graph an answer was computed from and lets
a reader edit it: add a variable, draw an edge, delete one. Nothing below
moved until "re-run with this graph" was pressed, and nothing said so — an
edited graph sat over the verdict, the ledger and the gaps of the graph as
it had been, and read as if they were about each other.

Re-running on every edit was the other choice and was not taken: a graph
half-edited is often not a program (a variable not yet joined, a name not
yet typed), and a large one takes seconds to answer. So the page says
which it is. The canvas reports what its graph says; the result's graph
compares that with the program the result was computed from; and while the
two differ, what is below is announced as the earlier result, dimmed, and
not operable — each action down there runs the program the result came
from and would put the edited graph back.

The browser cannot be imported, so what is pinned is its source.
"""
from __future__ import annotations

import pathlib

from tests import web_source

SRC = web_source.SRC
GRAPH = SRC / "lib" / "graph.ts"
CANVAS = SRC / "components" / "CausalCanvas.tsx"
RESULT_GRAPH = SRC / "components" / "ResultGraph.tsx"
RESULT_VIEW = SRC / "components" / "ResultView.tsx"


def _code(path: pathlib.Path) -> str:
    return web_source.without_comments(web_source.read(path))


def test_what_a_graph_says_is_its_names_and_edges_and_not_where_they_sit():
    shape = web_source.chunks(_code(GRAPH))["graphShape"]
    assert "position" not in shape
    assert "data.label" in shape
    # A latent confounder has no direction, so its two ends are sorted; a
    # cause keeps its order.
    assert "[a, b].sort()" in shape
    # And a proposed edge redrawn is the reader's own, which re-runs to a
    # different ledger.
    assert "e.data?.proposed ? 'proposed' : 'cause'" in shape


def test_the_canvas_reports_it_only_when_it_changes_and_not_before_seeding():
    canvas = _code(CANVAS)
    assert "onShapeChange?: (shape: string) => void" in canvas
    assert "graphShape(nodes, edges)" in canvas
    assert "shape !== lastShape.current" in canvas
    assert ("seedProgram && lastShape.current === null "
            "&& nodes.length === 0") in canvas


def test_the_results_graph_compares_it_with_the_program_the_result_came_from():
    graph = _code(RESULT_GRAPH)
    assert "programToFlow(program)" in graph
    assert "graphShape(seeded.nodes, seeded.edges)" in graph
    assert "shape !== null && shape !== computedFrom" in graph
    assert "onEdited?.(edited)" in graph
    assert "onShapeChange={setShape}" in graph


def test_everything_computed_from_the_old_graph_is_said_to_be_and_is_inert():
    view = _code(RESULT_VIEW)
    assert "onEdited={setGraphEdited}" in view
    assert "fill(SAYS.graphEdited, lang)" in view
    opened = view.index("inert={graphEdited}")
    closed = view.index("</div>", view.index("SAYS.rawEnvelope"))
    held = view[opened:closed]
    # The verdict and every action that runs the result's own program.
    for inside in ("<Verdict ", "<ProposedReview ", "<SupplyNumbers ",
                   "<GapReport ", "<FramingFill ", "<Recheck ",
                   "<JsonEditor ", "onClick={doAssume}",
                   "onClick={doRender}", "onSendTo('build', program)"):
        assert inside in held, inside
    # The graph itself, with its two buttons, is what stays operable.
    assert view.index("<ResultGraph ") < opened
    words = web_source.read(RESULT_VIEW)
    assert "因果图已改动，下面还是改动前的结果" in words
