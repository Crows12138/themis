"""One surface shows a reader a result, and it shows all of them.

Everything the kernel holds the browser to is checked by parsing
``frontend/src`` — the vocabularies it must mirror, the envelope fields it
must account for. That anchor is a path constant, and a path constant
answers "where is the React app", not "which files does a reader see". For
three months the answer to the second question was two: ``/`` served the
built product when a build existed and a 599-line page from the repo's first
web commit when it did not, and nothing anywhere said there were two. The
older page read 8 of the envelope's 21 top-level fields and printed four of
the twelve mirrored vocabularies as raw English ids; none of the seven
rounds of work on the product's wording had reached it, because no scan
looked there.

A page that shows no result is not a surface, and needs no discipline. That
is what ``static/`` holds now, and what these tests keep true — together
with the other half of the same fact: consolidating onto one surface is only
honest if that surface offers everything the server does. The two verify
endpoints were reachable from the old page alone, which meant Themis's own
claim — every answer can be re-derived independently — had no button in the
product it shipped.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from . import web_source

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from themis.web import app as web_app  # noqa: E402


REPO = pathlib.Path(__file__).resolve().parent.parent
STATIC = REPO / "themis" / "web" / "static"
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))
ENVELOPE_FIELDS = sorted(SCHEMA["properties"])

# Every file under static/ is reachable in a browser: the directory is
# mounted at /static. Listing them rather than globbing is the point — a new
# file here is a new thing a reader can open, and adding one should cost a
# line in this test.
SERVED_FROM_STATIC = ["no_build.html"]

client = TestClient(web_app.app)


def _api_routes() -> list[str]:
    return sorted({
        p for p in (getattr(r, "path", "") for r in web_app.app.routes)
        if p.startswith("/api/")
    })


def test_the_directory_that_is_not_a_surface_holds_what_it_says():
    """A scan parametrized over an empty directory is green and says
    nothing; this is the count that scan is worth."""
    assert sorted(p.name for p in STATIC.iterdir()) == SERVED_FROM_STATIC


@pytest.mark.parametrize("name", SERVED_FROM_STATIC)
def test_a_page_served_without_a_build_carries_no_result(name):
    """Not "it renders results correctly" — it renders none.

    Naming a field is the whole of what makes a page a surface: to show a
    reader ``status`` or ``derivation`` is to owe them words they can read.
    A page that never names one owes nothing, and the disciplines can stay
    pointed at the single place that does.
    """
    text = (STATIC / name).read_text(encoding="utf-8")
    named = [f for f in ENVELOPE_FIELDS if re.search(rf"\b{f}\b", text)]
    assert named == [], f"{name} 说出了信封字段 {named}——那就是一个读者面"


def test_without_a_build_the_root_serves_that_page(monkeypatch, tmp_path):
    """The branch, not the file: ``/`` is where the choice is made."""
    monkeypatch.setattr(web_app, "_FRONTEND_DIST", tmp_path / "absent")
    got = client.get("/")
    assert got.status_code == 200
    assert got.content == (STATIC / "no_build.html").read_bytes()


def test_the_root_prefers_the_built_product_when_there_is_one(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><p>built", encoding="utf-8")
    monkeypatch.setattr(web_app, "_FRONTEND_DIST", dist)
    assert client.get("/").content == b"<!doctype html><p>built"


def test_the_endpoint_scan_has_something_to_scan():
    """The count the scan below is worth: parametrized over nothing, it is
    green and says nothing."""
    assert len(_api_routes()) >= 9


@pytest.mark.parametrize("path", _api_routes())
def test_every_endpoint_the_server_offers_is_reachable_from_the_product(path):
    """An endpoint no surface calls is a capability the reader does not
    have, and it looks identical to one they do.

    Both verify endpoints were in this state the moment the older page went
    away — which is the same fact from the other side: the reason removing
    that page was safe to consider at all is that everything it could do,
    the product can do too.

    The whole literal, quotes included: one endpoint's path is another's
    prefix, and a substring search calls ``/api/verify`` reached by nothing
    more than the presence of ``/api/verify_bounds_result``.
    """
    called = re.search(rf"""['"`]{re.escape(path)}['"`]""",
                       web_source.sources_that_could_read())
    assert called, f"{path} 没有任何调用方——服务器提供了它，产品上够不着"
