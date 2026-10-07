"""A graph too big for its box is shown in a bigger box, not shrunk.

#822. The reader opened a twenty-variable graph and pressed the button
drawn as ⛶, expecting the graph to be shown larger. It was shown smaller:
that button was the library's "fit view", which scales the graph into the
box, and the box is a fixed 320 px tall, so a graph taller than it can
only be fitted by shrinking. The page had no way to make the box bigger.

The canvas now has its own controls, titled in the reader's language —
zoom in, zoom out, fit the whole graph in the box, and view the graph
full screen — and the last one takes the canvas itself full screen
through the Fullscreen API, fitting the graph to the size the box has
once it changes. The library's three English-titled buttons are gone.
"""
from __future__ import annotations

import re

from tests import web_source

CANVAS = web_source.read(web_source.SRC / "components" / "CausalCanvas.tsx")
STYLES = web_source.read(web_source.SRC / "styles.css")


def test_the_library_s_own_buttons_are_not_shown():
    assert re.search(r"<Controls\s+showZoom=\{false\}\s+showFitView=\{false\}\s+showInteractive=\{false\}", CANVAS)
    assert "<Controls showInteractive={false} />" not in CANVAS


def test_the_canvas_can_be_taken_full_screen_and_back():
    assert "canvas.current?.requestFullscreen()" in CANVAS
    assert "document.exitFullscreen()" in CANVAS
    assert "document.fullscreenEnabled" in CANVAS, "hidden where the browser has no full screen"
    assert "'fullscreenchange'" in CANVAS


def test_the_graph_is_fitted_to_the_box_once_the_box_changes_size():
    """#823: as the library measures the box, not as the fullscreen event
    reports it — the event fires before the new size is measured, and a
    fit then is a fit to the old box, which a reader saw as the graph not
    centred nor filling the screen."""
    assert "const width = useStore((s) => s.width)" in CANVAS
    assert "const height = useStore((s) => s.height)" in CANVAS
    assert "if (width > 0 && height > 0) void fitView({ padding })" in CANVAS
    assert "}, [width, height, padding, fitView])" in CANVAS
    assert "requestAnimationFrame" not in CANVAS
    assert "const padding = full ? 0.08 : FIT.padding" in CANVAS


def test_a_fit_may_zoom_out_far_enough_to_fit():
    """The library's floor of 0.5 left twenty variables clipped by the box
    with nothing saying so (#823)."""
    assert "minZoom={0.1}" in CANVAS


def test_every_control_is_titled_in_the_readers_language():
    words = web_source.words_map("SAYS", CANVAS)
    for key in ("zoomIn", "zoomOut", "fitAll", "fullscreen", "leaveFullscreen"):
        assert set(words[key]) == {"zh", "en"}, key
        assert f"SAYS.{key}" in CANVAS, key
    # Every title is filled for the reader's language, none written raw.
    tools = CANVAS.split("function Tools(", 1)[1].split("function GraphNode(", 1)[0]
    assert tools.count("<ControlButton") == tools.count("title={fill(") == 4


def test_full_screen_the_box_is_the_page_s_surface():
    assert ".dagview__canvas:fullscreen" in STYLES
    assert "background: var(--surface)" in STYLES.split(".dagview__canvas:fullscreen", 1)[1].split("\n", 1)[0]
