"""A result can be saved to a file and opened again.

What the result view shows lives only in the page: the server keeps no
answer, so a reload loses it, and a model's reply cannot be had again for
the same words. A reader lost one that way. So the view saves what it
shows to a file the reader keeps, and the page opens such a file back into
the workspace it came from (lib/saved.ts, #782).

The browser's code cannot be run from here, so what is held is read off
its source, as the other web tests do:

- what is saved is what is on the screen, re-runs included, and every
  field the view is handed is in the file, so a field added to the view
  later is saved or refused here rather than silently dropped;
- the fields written are the fields read back;
- a file that is not one is refused in the reader's language;
- an opened result goes back to its own workspace, replaces what is
  there, and says when it was saved for as long as it is the one shown.
"""
from __future__ import annotations

import re

from . import web_source

SAVED = web_source.SRC / "lib" / "saved.ts"
VIEW = web_source.SRC / "components" / "ResultView.tsx"
APP = web_source.SRC / "App.tsx"
WORKSPACES = {
    "ask": web_source.SRC / "components" / "AskWorkspace.tsx",
    "build": web_source.SRC / "components" / "BuildWorkspace.tsx",
    "estimate": web_source.SRC / "components" / "EstimateWorkspace.tsx",
}


def _saved() -> str:
    return web_source.read(SAVED)


def _function(name: str, source: str) -> str:
    return web_source.chunks(source)[name]


def test_every_field_the_view_is_handed_is_in_the_file():
    """``savedAt`` is the one field the file gives the view rather than
    takes from it."""
    shown = set(web_source.interface_fields(
        "ResultPayload", web_source.read(VIEW))) - {"savedAt"}
    kept = set(web_source.interface_fields("SavedResult", _saved()))
    assert shown <= kept, sorted(shown - kept)


def test_the_fields_written_are_the_fields_read():
    fields = set(web_source.interface_fields("SavedResult", _saved()))
    written = _function("saveResult", _saved())
    read = _function("openSaved", _saved())
    assert {f for f in fields if not re.search(rf"\b{f}:", written)} == set()
    assert {f for f in fields if f"d.{f}" not in read} == set()


def test_what_is_saved_is_what_is_on_the_screen():
    """The view's own state, not the payload it was first handed: a graph
    edited and re-run, priors filled in, a reply written afterwards are all
    on the screen, and the payload holds none of them."""
    calls = web_source.calls("saveResult", web_source.read(VIEW))
    assert len(calls) == 1
    _, (where, shown) = calls[0]
    assert where.strip() == "workspace"
    for field in ("result", "program", "reply", "naive"):
        assert re.search(rf"(?<![\w.]){field}\b", shown), field
        assert f"payload.{field}" not in shown, field


def test_every_result_view_says_which_workspace_it_is_in():
    """Required rather than optional, so a fourth place that shows a
    result cannot forget to say where it is."""
    assert "  workspace: Workspace\n" in web_source.read(VIEW)
    for name, path in WORKSPACES.items():
        views = re.findall(r"<ResultView\b[^>]*", web_source.read(path))
        assert views, path.name
        assert all(f'workspace="{name}"' in v for v in views), path.name


def test_a_file_that_is_not_one_is_refused_in_the_reader_s_language():
    """The file names what it is, and the reader and the writer name it
    with the same constant; a file saved by a newer page is refused rather
    than half read."""
    saved = _saved()
    written = _function("saveResult", saved)
    read = _function("openSaved", saved)
    assert "kind: KIND" in written and "version: VERSION" in written
    assert "d.kind !== KIND" in read
    assert "d.version > VERSION" in read
    refusals = web_source.words_map("SAYS", saved)
    assert set(refusals) == {"notJson", "notSaved", "newer"}
    for member in refusals:
        assert f"words: SAYS.{member}" in read, member


def test_an_opened_result_goes_back_to_the_workspace_it_came_from():
    app = web_source.read(APP)
    assert "saved.workspace === 'ask' && !offers?.llm ? 'build' : saved.workspace" in app
    for name, path in WORKSPACES.items():
        element = path.stem
        assert re.search(
            rf"<{element} key=\{{openedHere\?\.n \?\? 0\}} "
            rf"opened=\{{openedHere\?\.payload\}}", app), element
        assert "useState<ResultPayload | null>(opened ?? null)" in \
            web_source.read(path), path.name


def test_it_says_when_it_was_saved_while_it_is_the_one_shown():
    """A re-run from an opened result is today's, and a line that went on
    saying it was saved would be saying something false."""
    assert "payload.savedAt && result === payload.result" in \
        web_source.read(VIEW)
