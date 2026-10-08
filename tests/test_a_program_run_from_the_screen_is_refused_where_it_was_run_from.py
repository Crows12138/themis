"""A program run from the screen is refused where it was run from.

#826. The reader pressed "re-run with this graph" under an edited
twenty-variable graph and saw nothing happen. The kernel had refused the
graph — too many cells to ask — and the page had said so, in the result
view's error box: below the whole result, after four thousand gap rows,
off the screen the button was on.

A refusal of a program run from the screen is now said beside the
control that ran it: under the graph for the canvas's re-run button, and
under the JSON editor for its own. The error box at the foot keeps the
failures of the actions that live down there.
"""
from __future__ import annotations

from tests import web_source

RESULT_VIEW = web_source.read(web_source.SRC / "components" / "ResultView.tsx")
STYLES = web_source.read(web_source.SRC / "styles.css")


def test_a_run_says_where_it_was_run_from():
    assert "async function doRunJson(prog: Record<string, unknown>, at: 'graph' | 'json')" in RESULT_VIEW
    assert "onRerun={(p) => doRunJson(p, 'graph')}" in RESULT_VIEW
    assert "onRun={(p) => doRunJson(p, 'json')}" in RESULT_VIEW


def test_a_refusal_is_kept_with_where_and_not_in_the_foot_s_box():
    body = RESULT_VIEW.split("async function doRunJson(", 1)[1].split("\n  }\n", 1)[0]
    assert "setRunRefused({ at, said: errorText(e, lang) })" in body
    assert "setRunRefused({ at, said: fill(SAYS.noResult, lang) })" in body
    assert "setError(errorText(e, lang))" not in body


def test_the_graph_s_refusal_is_said_right_under_the_graph():
    after_graph = RESULT_VIEW.split("onEdited={setGraphEdited} /> : null}", 1)[1]
    first = after_graph.split("{graphEdited ? (", 1)[0]
    assert "runRefused?.at === 'graph'" in first
    assert 'className="staleline staleline--refused" role="alert"' in first
    assert "fill(SAYS.rerunRefused, lang)" in first


def test_the_editor_s_refusal_is_said_right_under_the_editor():
    after_editor = RESULT_VIEW.split("onRun={(p) => doRunJson(p, 'json')} /> : null}", 1)[1]
    first = after_editor.split("</div>", 1)[0]
    assert "runRefused?.at === 'json'" in first


def test_the_sentence_exists_in_both_languages_and_is_styled():
    words = web_source.words_map("SAYS", RESULT_VIEW)
    assert set(words["rerunRefused"]) == {"zh", "en"}
    assert ".staleline--refused" in STYLES
