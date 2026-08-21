"""A citation is not a field of one container.

Six containers on the envelope carry a ``reference``: three extension
blocks (``scm_counterfactual``, ``selection_recovery``,
``missing_data_recovery``) and three parts of ``numeric_estimate``
(``decomposition``, ``four_way_decomposition``, ``four_way_ratio``).
Seven writers between them, and until now not one of the six reached a
reader on either surface.

The shape of the miss is what names its cause. Every rendering table on
both surfaces is keyed by what ONE container holds — the block families,
the answer shapes, the computation details — and in each of the six the
citation is the one field that is not that table's subject. Six
independent and individually reasonable decisions dropped it, without an
exception anywhere, and a decision six writers make the same way was not
theirs to make.

So the renderer walks the envelope instead of joining a table, and the
parameter set below is read out of the schema rather than listed here: a
seventh container that declares a citation is covered the moment it is
declared, and needs nobody to remember this file.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from . import web_source
from themis import kernel
from themis.output.analysis_report import build_analysis_report, _render_route
from themis import language

SCHEMA = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "themis" / "schemas" /
     "query_result.schema.json").read_text(encoding="utf-8"))

SAID = "Author & Coauthor (1999) Theorem 3"
ALSO = "Someone Else (2001) §2"


def _declared_citation_paths(node, path=()):
    """Every place the schema declares a citation, as an envelope path."""
    if not isinstance(node, dict):
        return
    for name, spec in (node.get("properties") or {}).items():
        here = path + (name,)
        if name == "reference" and spec.get("type") == "string":
            yield here
        yield from _declared_citation_paths(spec, here)


CITATION_PATHS = sorted(_declared_citation_paths(SCHEMA))


def _envelope(*cited):
    """A result carrying one citation at each of the given paths."""
    result: dict = {"query_id": "q", "status": "numerically_solved",
                    "query_kind": "effect"}
    for path, text in cited:
        node = result
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = text
    return result


def test_a_citation_lives_in_more_than_one_container():
    """The premise the rest of this file rests on. If citations lived in
    one place, binding a renderer to that place would have been right, and
    what happened here would be an oversight rather than a shape."""
    containers = {path[:-1] for path in CITATION_PATHS}
    assert len(containers) > 1, containers


@pytest.mark.parametrize("path", CITATION_PATHS,
                         ids=[".".join(p) for p in CITATION_PATHS])
def test_a_citation_in_any_container_reaches_the_reader(path):
    said = _render_route(_envelope((path, SAID)), lang=language.DEFAULT)
    assert SAID in said, f"{'.'.join(path)} reaches no reader"
    assert "依据" in said


def test_every_source_is_said_and_a_shared_one_is_said_once():
    """Two containers citing two papers give two lines; two containers
    citing the same paper give one. A reader counting sources should be
    counting sources rather than writers."""
    first, second = CITATION_PATHS[0], CITATION_PATHS[1]
    both = _render_route(_envelope((first, SAID), (second, ALSO)), lang=language.DEFAULT)
    assert SAID in both and ALSO in both
    shared = _render_route(_envelope((first, SAID), (second, SAID)), lang=language.DEFAULT)
    assert shared.count(SAID) == 1


def _joe_program():
    """Pearl's Primer Model 4.1 — the run whose block carries a citation."""
    x = {"predicate": "X", "args": [{"type": "const", "name": "joe"}]}
    h = {"predicate": "H", "args": [{"type": "const", "name": "joe"}]}
    y = {"predicate": "Y", "args": [{"type": "const", "name": "joe"}]}
    statements = [
        {"kind": "cause", "from": x, "to": h, "coefficient": 0.5},
        {"kind": "cause", "from": x, "to": y, "coefficient": 0.7},
        {"kind": "cause", "from": h, "to": y, "coefficient": 0.4},
    ]
    for atom, value in ((x, 0.5), (h, 1.0), (y, 1.5)):
        statements.append({"kind": "observation", "atom": atom, "value": value})
    statements.append({"kind": "query", "id": "q1", "query": {
        "kind": "scm_counterfactual",
        "intervention": {"atom": h, "value": 2.0},
        "target": y}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "joe"}]},
            "statements": statements}


def test_a_real_run_names_the_paper_it_implements():
    """From a producer rather than a hand-built envelope. This path has
    written Pearl's Primer §4.2 into its block on every run since it was
    built, and the section that exists to say how the answer was reached
    said only that a chain had one step."""
    program = _joe_program()
    result = kernel.run(program)["results"][0]
    report = build_analysis_report(result, program=program)
    assert "Pearl, Glymour & Jewell" in report
    how = report.split("## 怎么算出来的", 1)[1].split("\n## ", 1)[0]
    assert "依据" in how, "the citation landed outside the section that asks"


def test_the_browser_walks_the_envelope_rather_than_a_list():
    """Same mechanism, not merely the same output today. A browser that
    listed the six containers would agree with the report on every
    envelope now and drop the seventh exactly as these six were dropped."""
    body = web_source.chunks(web_source.read(web_source.VERDICT))["citations"]
    assert "'reference'" in body
    for container in ("scm_counterfactual", "selection_recovery",
                      "missing_data_recovery", "four_way_decomposition",
                      "four_way_ratio", "decomposition"):
        assert container not in body, (
            f"the browser's citation walk names {container} — binding a "
            f"citation to a container is what this is undoing")


def test_the_browser_says_it_in_the_same_section():
    component = web_source.read(web_source.COMPONENT)
    assert "citations(result)" in component
    assert "依据文献" in component
