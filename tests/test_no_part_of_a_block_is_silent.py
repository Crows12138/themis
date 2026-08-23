"""Every key an extensions block declares, and whether ITS reader says it.

The question "does this part reach a reader" has been asked four times and
each time of one container, one level down from the last accident.
:mod:`themis.blocks` asks it of the eighteen blocks;
:mod:`tests.test_the_answer_has_no_silent_parts` asks it of
``numeric_estimate``'s direct properties; the first version of this file asked
it of every key under ``extensions`` at full depth — and answered it against
EVERY reader surface at once, so a key was covered by being spelled anywhere.

That floor found real omissions and its own weakness at the same time. Asking
the same question BLOCK-QUALIFIED — does the renderer bound to THIS block name
this key — left 77 of 168 leaf names unanswered, and the honest reading of the
77 was not 77 holes. It was that a key reaches a reader through four channels
and only one of them was ever queried: the block's own renderer, the detail
table (whose keys NAME the block, and which the previous census did not know
existed — thirty-four of the seventy-seven), the carrier a block declares, and
"the same fact, said elsewhere", which had no first-class record at all.

So the denominator stays and the numerator narrows. A key is answered when the
block's own reader names it — the renderer :func:`themis.blocks.bind` recorded,
plus the detail renderers keyed under this block, plus whatever re-presents a
carried block — or when a row below says who it is for instead. That gate
implies the floor: if the block's own reader spells it, some surface does.

WHAT THAT IS WORTH. Sound in one direction only: a name absent from a
renderer's whole call closure cannot be being read there, so a failure is
real; a name present may sit in a branch, in a docstring, or in a helper
called for something else. Two weaknesses stay named rather than fixed. A
renderer nobody calls any more still spells every key it ever read — which is
why a row deferring to a reader function is held to that function being
reachable from the report's entry point, and why the pins at the bottom check
sentences and not spellings. And a renderer can read a key and print nothing.

A shape another document records is where the walk stops — ``cross=False``.
``s_nodes[].affects`` and the adjustment sets are ``$ref``s into
``atom.schema.json``; that document is another subject with its own readers,
and pulling it in here would put one vocabulary's completeness under two
files. This is a property of the question, not of the traversal: the question
is whose job it is to say something, and that follows the shape's owner. The
absence rule asks what a payload contains and so has to follow — see
:meth:`tests.schema_walk.Document.walk`.
"""
from __future__ import annotations

import ast
import functools
import json
import pathlib
import re
from dataclasses import dataclass

import pytest

from themis import blocks
from themis.output import analysis_report

from . import schema_walk, web_source
from .test_vocabulary_reach import VOCABULARIES

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))
TOP_LEVEL = frozenset(SCHEMA.get("properties") or {})


# ---------------------------------------------------------------- the schema
EXT = SCHEMA["properties"]["extensions"]

#: Every key path under ``extensions``, EXCEPT the block names themselves.
#:
#: A block name is what a renderer is reached BY, not something it reads, and
#: whether one reaches a reader at all is :func:`themis.blocks.bind`'s
#: subject, checked there in both directions. This file's subject is what is
#: inside a block, which is the level nothing was asking about.
#:
#: The traversal itself lives in :mod:`tests.schema_walk`, because a second
#: gate now asks a different question of the same document and two copies of
#: a ``$ref`` walk are two tables that were once equal.
PATHS: tuple[str, ...] = tuple(
    ".".join(path) for path, _, _ in schema_walk.RESULT.walk(EXT, cross=False)
    if len(path) > 1)


# ------------------------------------------------- what reads a given block
def _reads(name: str) -> re.Pattern:
    """The key as a key: quoted, or reached as an attribute.

    Deliberately NOT the bare ``name:`` form. In a renderer's TypeScript that
    is the row being BUILT — ``{ label: …, value: … }`` — so counting it made
    ``intervention.value`` read as named by every renderer that emits a row,
    which is every one of them.
    """
    n = re.escape(name)
    return re.compile(rf"""["']{n}["']|\.{n}\b""")


_REPORT_SRC = (REPO / "themis" / "output" / "analysis_report.py").read_text(
    encoding="utf-8")
_TREE = ast.parse(_REPORT_SRC)
_DECLS: dict[str, ast.AST] = {
    node.name: node for node in ast.walk(_TREE)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
for _node in _TREE.body:
    if isinstance(_node, ast.Assign):
        for _target in _node.targets:
            if isinstance(_target, ast.Name):
                _DECLS.setdefault(_target.id, _node.value)
    elif isinstance(_node, ast.AnnAssign) and isinstance(_node.target, ast.Name):
        if _node.value is not None:
            _DECLS.setdefault(_node.target.id, _node.value)


@functools.lru_cache(maxsize=None)
def _closure(root: str) -> tuple[frozenset[str], frozenset[str]]:
    """(string literals, declarations) transitively reachable from ``root``.

    Names rather than calls, because a renderer table is a name holding
    functions: binding is what puts a renderer on the path, and a walk that
    only followed call syntax would find no renderer at all from the report's
    entry point.
    """
    literals: set[str] = set()
    seen: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        node = _DECLS.get(current)
        if node is None:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                literals.add(inner.value)
            named = (inner.id if isinstance(inner, ast.Name) else
                     inner.attr if isinstance(inner, ast.Attribute) else None)
            if named is not None and named in _DECLS:
                stack.append(named)
    return frozenset(literals), frozenset(seen)


_VERDICT_SRC = web_source.read(web_source.VERDICT)
_TS_DECLS = web_source.chunks(_VERDICT_SRC)

#: Tables holding EVERY block's entry. Following a mention of one of these
#: out of a single entry would make each block's reader the whole surface.
_TS_TABLES = frozenset({
    "ROUTE_RENDERERS", "ANSWER_RENDERERS", "NUMERIC_DETAIL_RENDERERS",
    "ROUTE_ORDER", "ANSWER_ORDER", "NUMERIC_DETAIL_ORDER",
})


def _ts_entries(table: str) -> dict[str, str]:
    """One name-keyed table's entries, by key. Depth 0, like its key scan."""
    body = web_source.literal(table, _VERDICT_SRC)
    out: dict[str, list[str]] = {}
    current, depth = None, 0
    for line in body.splitlines():
        if depth == 0:
            found = re.match(r"\s*'([^']+)'\s*:", line) or re.match(
                r"\s*([A-Za-z_]\w*)\??\s*:", line)
            if found:
                current = found.group(1)
                out.setdefault(current, [])
        if current is not None:
            out[current].append(line)
        depth += (line.count("{") + line.count("[")
                  - line.count("}") - line.count("]"))
    return {key: "\n".join(lines) for key, lines in out.items()}


_TS_RENDERERS: dict[str, str] = {}
for _table in ("ROUTE_RENDERERS", "ANSWER_RENDERERS", "NUMERIC_DETAIL_RENDERERS"):
    for _key, _body in _ts_entries(_table).items():
        _TS_RENDERERS[_key] = _TS_RENDERERS.get(_key, "") + "\n" + _body


def _ts_closure(text: str) -> str:
    """One entry plus the helpers it names, so a helper's reads count too.

    Transitively. A renderer that hands the block to a helper which hands it
    to an assembler is reading the key as surely as one that spells it, and
    stopping at the first hop makes the answer depend on how many times the
    work was factored out — which is a property of the code's shape and not
    of what reaches the reader.
    """
    out = [text]
    seen: set[str] = set()
    frontier = [text]
    while frontier:
        current = frontier.pop()
        for name, body in _TS_DECLS.items():
            if name in seen or name in _TS_TABLES:
                continue
            if re.search(rf"(?<![\w.]){re.escape(name)}\s*\(", current):
                seen.add(name)
                out.append(body)
                frontier.append(body)
    return "\n".join(out)


#: What actually reads a carried block.
#:
#: ``Block.carried_by`` names the CONTAINER the fact ends up in, which is a
#: claim about where a reader meets it. A per-key question needs the code that
#: reads the key, and that is a different fact — one the registry has no place
#: for, because it is per surface and the registry is upstream of every
#: surface.
CARRIER_READER: dict[str, str] = {
    "assumption_ledger": "themis/output/result_orchestrator.py",
    "data_gap_report": "themis/output/data_gap_report.py",
    # The cell is a display copy of ``numeric_estimate``'s own field, and
    # that container is the report's own subject: its answer shapes and its
    # detail table are spread across the file, and one cell arrives as an
    # interval or as a point with a confidence band by different shapes. Per
    # key, that container has its own census in
    # ``test_the_answer_has_no_silent_parts``; naming a single renderer here
    # would be this file claiming to be that one.
    "numeric_estimate": "themis/output/analysis_report.py",
}


@functools.lru_cache(maxsize=None)
def _reader_of(block: str) -> tuple[frozenset[str], str]:
    """Every literal and every source region that renders THIS block."""
    assert block in blocks.BY_NAME, (
        f"the schema declares {block!r} under extensions and "
        f"themis.blocks does not register it"
    )
    known = blocks.BY_NAME[block]
    literals: set[str] = set()
    text: list[str] = []
    for table in (analysis_report._ROUTE_RENDERERS,
                  analysis_report._ANSWER_BLOCK_RENDERERS,
                  analysis_report._ASSUMPTION_RENDERERS):
        bound = table.get(known)
        if bound is not None:
            literals |= _closure(bound.__name__)[0]
    for path, renderer in analysis_report._NUMERIC_DETAIL_RENDERERS:
        if path.startswith(f"extensions.{block}."):
            literals |= _closure(renderer.__name__)[0]
    for key, body in _TS_RENDERERS.items():
        if key == block or key.startswith(f"extensions.{block}."):
            text.append(_ts_closure(body))
    if known.carried_by is not None:
        who = CARRIER_READER[str(known.carried_by)]
        if who.endswith(".py"):
            text.append((REPO / who).read_text(encoding="utf-8"))
        else:
            literals |= _closure(who)[0]
    return frozenset(literals), "\n".join(text)


def _named(path: str) -> bool:
    """Does the block this path belongs to name its last step?"""
    block = path.split(".", 1)[0]
    leaf = path.replace("[]", "").split(".")[-1]
    literals, text = _reader_of(block)
    return leaf in literals or bool(_reads(leaf).search(text))


# ------------------------------------------------------------------ the rows
@dataclass(frozen=True)
class Silent:
    """One declared key the block's own reader does not name, and who it is for.

    Exactly one of the three answers is required, and each is checked rather
    than believed: a consumer that does not consume, a source that is itself
    silent, and a vocabulary row that does not cover this site are all ways
    of writing down an answer that is not one.
    """

    holds: str
    #: A module that re-derives something from it. Held to reading the key.
    consumed_by: str = ""
    #: Where the same fact does reach a reader — another declared path, a
    #: block, a top-level field of the result, or ``analysis_report:<fn>``
    #: for a renderer that says it somewhere other than this block's section.
    said_by: str = ""
    #: A row in :mod:`tests.test_vocabulary_reach` that already decided this
    #: value needs no word, with the reason written there.
    vocabulary: str = ""
    #: A registry that owns this key's SPELLING, which the block's reader
    #: asks instead of reading the key itself. Not the same answer as
    #: ``vocabulary``: that one says no reader needs a word, this one says a
    #: reader gets one and the renderer got it without naming the field. A
    #: literal in a renderer and a lookup through a registry are the same
    #: fact reaching the same reader, and only the first is visible to a
    #: text scan — so what is checked is the other two halves: the registry
    #: really owns the spelling, and this block's reader really goes through
    #: it.
    read_through: str = ""


#: A const restating which block this is. The renderer's own heading says it
#: in the reader's language, so the token is the block name twice.
_RESTATES_ITS_BLOCK = (
    ("iv_identification", "strategy"),
    ("selection_recovery", "kind"),
    ("missing_data_recovery", "kind"),
    ("transport_identification", "kind"),
    ("longitudinal_identification", "estimand"),
    ("proximal_estimand", "method"),
)

#: The query's own parameters, copied into a block by its producer. The
#: question line states the query itself, under the query's names for them.
_FROM_THE_QUESTION = (
    ("selection_recovery", "treatment", "_q_effect"),
    ("selection_recovery", "outcome", "_q_effect"),
    ("selection_recovery", "query_kind", "_q_effect"),
    ("proximal_estimand", "treatment", "_q_proximal_effect"),
    ("proximal_estimand", "outcome", "_q_proximal_effect"),
    ("scm_counterfactual", "intervention", "_q_scm_counterfactual"),
    ("scm_counterfactual", "intervention.variable", "_q_scm_counterfactual"),
    ("scm_counterfactual", "intervention.value", "_q_scm_counterfactual"),
)

SILENT: dict[str, Silent] = {
    # --- evidence for a verifier, not words for a reader ---------------------
    "causation.observational_joint": Silent(
        holds="the four P(X, Y) cells the theta path's PN/PS/PNS were "
              "computed from",
        consumed_by="themis.kernel",
    ),
    **{
        f"causation.observational_joint.{cell}": Silent(
            holds="one cell of that joint",
            consumed_by="themis.kernel",
        )
        for cell in ("p_x1_y1", "p_x1_y0", "p_x0_y1", "p_x0_y0")
    },
    **{
        f"counterfactual_cell.observational_joint{suffix}": Silent(
            holds="the four P(X, Y) cells the bounded counterfactual was "
                  "solved from" if not suffix else "one cell of that joint",
            consumed_by="themis.kernel",
        )
        for suffix in ("", ".p_x1_y1", ".p_x1_y0", ".p_x0_y1", ".p_x0_y0")
    },
    # The whole block is evidence. What a reader acts on is the
    # ``declared_type_data_mismatch`` gap its producer writes beside it; the
    # verifier re-runs the classification and the domain check from these and
    # rejects a verdict they do not support, which is why they are on the
    # envelope at all.
    "type_reconciliation.checks": Silent(
        holds="one reconciliation per column whose declared type and observed "
              "type disagreed",
        consumed_by="themis.verifier.type_reconciliation_rules",
    ),
    **{
        f"type_reconciliation.checks.[].{stat}": Silent(
            holds="one of the column statistics the type verdict was derived "
                  "from",
            consumed_by="themis.verifier.type_reconciliation_rules",
        )
        for stat in ("declared_domain", "declared_scale", "observed_scale",
                     "n_unique", "observed_values", "dtype_kind", "verdict")
    },
    "type_reconciliation.checks.[].detail": Silent(
        holds="the sentence describing this column's mismatch",
        said_by="data_gap_report",
    ),
    "assumption_ledger.assumptions.[].id": Silent(
        holds="the declaration a ledger entry restates, by name",
        consumed_by="themis.output.result_orchestrator",
    ),

    # --- said by something else ---------------------------------------------
    **{
        f"{block}.{key}": Silent(
            holds="a const restating which block this is",
            said_by=block,
        )
        for block, key in _RESTATES_ITS_BLOCK
    },
    **{
        f"{block}.{key}": Silent(
            holds="the query's own parameter, copied in by the producer",
            said_by=f"analysis_report:{fn}",
        )
        for block, key, fn in _FROM_THE_QUESTION
    },
    **{
        f"{block}.reference": Silent(
            holds="the paper this route implements",
            said_by="analysis_report:_render_citations",
        )
        for block in ("scm_counterfactual", "selection_recovery",
                      "missing_data_recovery")
    },
    "iv_identification.required_assumption": Silent(
        holds="the premise a Wald ratio needs; the producer copies it into "
              "`identification` and calls that copy the human surface",
        said_by="identification.required_assumption",
    ),
    # Checked end to end below rather than believed here: writing this row
    # was how the ledger's four channels came to be counted, and the count
    # was three of the two that existed.
    **{
        site: Silent(
            holds="the untestable premises this route's identifiability "
                  "claim rests on, as ids the glossary translates",
            said_by="assumption_ledger",
        )
        for site in (
            "longitudinal_identification.assumptions",
            "mediation_decomposition.nde_nie.assumptions",
            "mediation_decomposition.cde.assumptions",
            "mediation_joint_decomposition.nde_nie.assumptions",
            "mediation_joint_decomposition.cde.assumptions",
        )
    },
    "mediation_decomposition.numeric.e_y_cross_world": Silent(
        holds="the back-compat alias of e_y_cross_treated_outer",
        said_by="mediation_decomposition.numeric.e_y_cross_treated_outer",
    ),
    # The joint block's numeric is a ``$ref`` to the one above, so the alias
    # arrives here too and has the same answer. Two rows rather than one
    # because the denominator is paths and a path is where a reader looks.
    "mediation_joint_decomposition.numeric.e_y_cross_world": Silent(
        holds="the same alias, reached through the joint block's $ref",
        said_by="mediation_joint_decomposition.numeric.e_y_cross_treated_outer",
    ),
    "missing_data_recovery.adjustment_set": Silent(
        holds="the set whose marginal the recovered estimand also needs",
        said_by="missing_data_recovery.estimand.requires",
    ),
    # A string copy of the expression the route produced. Every route writes
    # its estimand to the top-level ``formula`` as an AST, which is what the
    # section renders and what the verifier matches a derivation step
    # against; this is the same expression as prose, and the gap generator
    # parses the treatment and outcome back out of it.
    "transport_identification.formula_repr": Silent(
        holds="the transport formula as a string",
        consumed_by="themis.output.data_gap_report",
    ),
    "transport_identification.s_nodes.[].id": Silent(
        holds="the handle the caller named this selection node by",
        consumed_by="themis.output.data_gap_report",
    ),

    # --- a key whose spelling a registry owns -------------------------------
    # Which of two objects the cell's resampled pair holds. The report says
    # it — "置信区间" or "识别区间的外带", beside the numbers, with what
    # would narrow it under them — and it says it by handing the row to the
    # interval census rather than by reading the field. Three surfaces used
    # to work the same thing out from whether ``point`` was null, which is
    # what the census exists to stop; a renderer spelling the field again
    # would be the fourth (#419).
    "counterfactual_cell.ci_width_is": Silent(
        holds="which of the two objects the ci pair holds on this run",
        read_through="themis.intervals",
    ),

    # --- a closed vocabulary that already decided it needs no word ----------
    "mediation_decomposition.strategy": Silent(
        holds="which decomposition survived",
        vocabulary="mediation_strategy",
    ),
    "mediation_joint_decomposition.strategy": Silent(
        holds="the same, for a mediator set",
        vocabulary="mediation_joint_strategy",
    ),
    "selection_recovery.criterion": Silent(
        holds="which recovery criterion licensed the answer",
        vocabulary="selection_criterion",
    ),
}


def _vocabulary_paths(row) -> set[str]:
    """A vocabulary row's schema sites, as this file's paths.

    A site is spelled from the schema root and threads ``properties`` and
    ``items``; a path here names keys only. Translating in one direction
    rather than storing both is the point — the two files then cannot come to
    disagree about which key a row is about.
    """
    prefix = ("query_result.schema.json", "properties", "extensions",
              "properties")
    out = set()
    for site in row.sites:
        if tuple(site[:len(prefix)]) != prefix:
            continue
        steps = [s for s in site[len(prefix):] if s not in ("properties",)]
        out.add(".".join("[]" if s == "items" else s for s in steps))
    return out


# ----------------------------------------------------------------- the gates
def test_the_schema_still_declares_parts_to_ask_about():
    """A walk that finds nothing satisfies every check below in silence."""
    assert len(PATHS) > 160, len(PATHS)
    assert "mediation_joint_decomposition.numeric.te" in PATHS, (
        "the walk stopped at a $ref; the joint block's numeric subtree "
        "reaches the single-mediator one that way and is the largest thing "
        "this file would then not be asking about"
    )


def test_every_declared_key_is_named_by_its_own_block_or_answered_for():
    """The gate: what a block holds is said where a reader looks for it."""
    unheard = sorted(p for p in PATHS if p not in SILENT and not _named(p))
    assert not unheard, (
        f"declared under extensions and named by nothing that renders the "
        f"block carrying it: {unheard}; render it, or add a row saying who "
        f"it is for"
    )


@pytest.mark.parametrize("path", sorted(SILENT))
def test_a_row_is_about_a_key_the_schema_declares(path):
    """A row for a path that no longer exists is a reason nobody re-read."""
    assert path in PATHS, (
        f"{path} has a row here and the schema does not declare it"
    )


@pytest.mark.parametrize("path", sorted(SILENT))
def test_every_row_says_exactly_one_thing(path):
    row = SILENT[path]
    said = [bool(row.consumed_by), bool(row.said_by), bool(row.vocabulary),
            bool(row.read_through)]
    assert sum(said) == 1, (
        f"{path}: says {sum(said)} of consumed_by / said_by / vocabulary / "
        f"read_through"
    )
    assert row.holds, f"{path}: no row says what a writer puts in it"


@pytest.mark.parametrize("path", sorted(SILENT))
def test_a_row_claiming_silence_is_still_silent(path):
    """Checked in the direction that goes stale.

    The block's own renderer starts naming it and the row still says it does
    not; the reader is then told less than the code says, which is this
    file's own failure pointed the other way.
    """
    assert not _named(path), (
        f"{path} has a row saying the block's own reader does not name it, "
        f"and it does; the row is stale"
    )


@pytest.mark.parametrize("path", sorted(
    p for p, r in SILENT.items() if r.consumed_by))
def test_a_claimed_consumer_reads_the_key(path):
    """Not for a reader is a claim about who it IS for, and that is checkable."""
    module = SILENT[path].consumed_by
    source = REPO / (module.replace(".", "/") + ".py")
    assert source.exists(), f"{path}: no module {module!r}"
    leaf = path.replace("[]", "").split(".")[-1]
    assert _reads(leaf).search(source.read_text(encoding="utf-8")), (
        f"{path}: {module} does not read it, so the row names a consumer "
        f"that does not consume it"
    )


@pytest.mark.parametrize("path", sorted(
    p for p, r in SILENT.items() if r.said_by))
def test_a_claimed_source_reaches_a_reader_itself(path):
    """Deferring to something else only works if that thing arrives.

    Four shapes, because there are four ways one fact is said in another
    place. A renderer is the weakest of them — it is checked for being on
    the report's call graph rather than for spelling this key, because a
    restatement is precisely a fact said under a different name, and the
    failure worth catching there is the renderer nobody calls any more.
    """
    said_by = SILENT[path].said_by
    if said_by.startswith("analysis_report:"):
        fn = said_by.split(":", 1)[1]
        assert fn in _DECLS, f"{path}: the report declares no {fn}"
        assert fn in _closure("build_analysis_report")[1], (
            f"{path}: defers to {fn}, which build_analysis_report never "
            f"reaches; a renderer nobody calls still spells every key it "
            f"once read"
        )
        return
    if said_by in blocks.Block:
        return
    if said_by in TOP_LEVEL:
        assert _reads(said_by).search(_REPORT_SRC), (
            f"{path}: defers to the top-level {said_by!r}, which the report "
            f"does not render"
        )
        return
    assert said_by in PATHS, (
        f"{path}: defers to {said_by!r}, which is neither a registered block, "
        f"a top-level field, a key the schema declares, nor a renderer"
    )
    assert said_by not in SILENT and _named(said_by), (
        f"{path}: defers to {said_by}, which reaches no reader either"
    )


@pytest.mark.parametrize("path", sorted(
    p for p, r in SILENT.items() if r.vocabulary))
def test_a_claimed_vocabulary_row_is_about_this_key(path):
    """The reason lives in one file, and this points at it rather than copying.

    A copied reason is two reasons the moment either is revised, and the one
    revised is not the one the next reader finds.
    """
    name = SILENT[path].vocabulary
    assert name in VOCABULARIES, f"{path}: no vocabulary row {name!r}"
    row = VOCABULARIES[name]
    assert path in _vocabulary_paths(row), (
        f"{path}: vocabulary row {name!r} is about "
        f"{sorted(_vocabulary_paths(row))}"
    )
    assert row.no_gloss, (
        f"{path}: vocabulary row {name!r} does not say the value needs no "
        f"word, so it cannot be the reason this key says nothing"
    )


@pytest.mark.parametrize("path", sorted(
    p for p, r in SILENT.items() if r.read_through))
def test_a_registry_that_owns_a_spelling_is_the_one_the_reader_asks(path):
    """Both halves, because either alone is an assertion rather than a check.

    A registry that does not hold the key is a claim about somebody else's
    module; a reader that never goes through it is the key reaching nobody
    with a sentence in front of it.
    """
    row = SILENT[path]
    leaf = path.replace("[]", "").split(".")[-1]
    module = pathlib.Path(REPO, row.read_through.replace(".", "/") + ".py")
    assert module.exists(), f"{path}: no module {row.read_through}"
    source = module.read_text(encoding="utf-8")
    assert f'"{leaf}"' in source or f"'{leaf}'" in source, (
        f"{path}: {row.read_through} is named as owning the spelling of "
        f"{leaf!r} and does not contain it"
    )
    _, text = _reader_of(path.split(".", 1)[0])
    asked = row.read_through.rsplit(".", 1)[-1]
    assert re.search(rf"(?<![\w.]){re.escape(asked)}\.", text), (
        f"{path}: {row.read_through} owns the spelling and the block's own "
        f"reader never asks it anything"
    )


def test_a_registry_row_still_needs_the_reader_to_get_a_word():
    """The half that separates this answer from ``vocabulary``.

    ``vocabulary`` says nobody needs a word. This says somebody gets one
    without the renderer spelling the field, so the vocabulary row behind it
    has to name what hands the word over.
    """
    for name, row in sorted(SILENT.items()):
        if not row.read_through:
            continue
        covering = [v for v in VOCABULARIES.values()
                    if v.declares.startswith(row.read_through + ".")]
        assert covering, (
            f"{name}: nothing in test_vocabulary_reach declares a vocabulary "
            f"out of {row.read_through}, so no reader is shown to get a word"
        )
        assert all(v.glossed_by for v in covering), (
            f"{name}: {row.read_through} declares a vocabulary that hands no "
            f"reader a word; that is the ``vocabulary`` answer, not this one"
        )


def test_a_registry_that_owns_nothing_is_refused():
    """The new answer, watched saying no in both of its halves.

    Doctored on the real row: a module that does not hold the spelling, and
    a leaf the registry has never heard of. Without this, "the registry owns
    it" would be a sentence checked against a file that happens to be large.
    """
    row = SILENT["counterfactual_cell.ci_width_is"]
    source = pathlib.Path(
        REPO, row.read_through.replace(".", "/") + ".py"
    ).read_text(encoding="utf-8")
    assert '"ci_width_is"' in source
    assert '"ci_width_is_not_a_field"' not in source
    _, text = _reader_of("counterfactual_cell")
    assert re.search(r"(?<![\w.])intervals\.", text)
    assert not re.search(r"(?<![\w.])no_such_registry\.", text)


# ------------------------------------------------- the maps inside the blocks
#: A map whose contents nobody declared, and the reason it is that way.
#: #338 closed the eighteen block maps and stopped there; measured one level
#: down, fourteen more were open and one of them was already carrying two
#: keys nobody had declared — the reference-grid counts on a mediation
#: failure. A container open to anything cannot report a field nobody decided
#: to carry, which is the same sentence one level lower.
OPEN_ON_PURPOSE = {
    "": "the map OF blocks, guarded at both exits by blocks.check_registered "
        "instead: verify() must accept an envelope carrying somebody else's "
        "annotation, which is what an open map is for, and what we EMIT is "
        "closed by that check rather than by this schema",
    "ambiguities.[]": "authored upstream by a caller, so enumerating it would "
                      "make the kernel the authority on which ambiguities a "
                      "caller may report",
}


def _open_maps(spec: dict, path: tuple[str, ...], depth: int = 0):
    """Every object below here that accepts a key nobody declared.

    A schema'd ``additionalProperties`` is not open: it declares what the
    values are, and the keys are data — a variable's name, a mediator's
    value. What this looks for is the map that accepts anything.
    """
    if depth > 8:
        return
    raw, spec = spec, schema_walk.RESULT.resolve(spec, cross=False)
    if not spec:
        return
    if (spec.get("properties") or spec.get("type") == "object") and (
            "$ref" not in raw):
        if spec.get("additionalProperties") not in (False,) and not isinstance(
                spec.get("additionalProperties"), dict):
            yield ".".join(path)
    for name, sub in (spec.get("properties") or {}).items():
        yield from _open_maps(sub, path + (name,), depth + 1)
    items = spec.get("items")
    if isinstance(items, dict):
        yield from _open_maps(items, path + ("[]",), depth + 1)


def test_every_map_inside_a_block_is_closed_but_the_ones_that_argue_for_it():
    """Openness needs a written reason, in the same dict as the name."""
    open_now = set(_open_maps(EXT, ()))
    assert open_now == set(OPEN_ON_PURPOSE), (
        f"open with no recorded reason: "
        f"{sorted(open_now - set(OPEN_ON_PURPOSE))}; "
        f"recorded as open but now closed: "
        f"{sorted(set(OPEN_ON_PURPOSE) - open_now)}"
    )


# --------------------------------------------------- what the reader gets now
#: One envelope per part, and a phrase only a renderer reading it could
#: produce. The rows above check that a key is NAMED; these check that
#: reading it comes out as a sentence, for the parts these two items rendered.
_SAYS: tuple[tuple[str, dict, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "the two Pearl decompositions are both stated, with their arms",
        {"mediation_decomposition": {
            "mediator": "m", "mediator_valid": True,
            "nde_nie": {"identifiable": True, "adjustment": [],
                        "failed_condition": None},
            "cde": {"identifiable": True, "adjustment": [],
                    "failed_condition": None},
            "numeric": {
                "e_y_treated": 0.66, "e_y_control": 0.52,
                "e_y_cross_treated_outer": 0.45,
                "e_y_cross_control_outer": 0.63,
                "te": 0.14, "nde_at_control": -0.07, "nie_at_treated": 0.21,
                "nde_at_treated": 0.03, "nie_at_control": 0.11,
            },
        }},
        ("总效应 TE", "以对照为参照", "以处理为参照", "两条通路方向相反"),
        ("nde_at_control", "e_y_cross_treated_outer"),
    ),
    (
        "a controlled direct effect that flips sign says so",
        {"mediation_decomposition": {
            "mediator": "m", "mediator_valid": True,
            "nde_nie": {"identifiable": False, "adjustment": [],
                        "failed_condition": "M3"},
            "cde": {"identifiable": True, "adjustment": [],
                    "failed_condition": None},
            "numeric": {"cde": {"True": -0.13, "False": 0.10}},
        }},
        ("把中介固定在 True", "变号", "看中介被固定在哪里"),
        ("cde_status",),
    ),
    (
        "an arm the graph allowed and the distribution could not answer",
        {"mediation_decomposition": {
            "mediator": "m", "mediator_valid": True,
            "nde_nie": {"identifiable": True, "adjustment": [],
                        "failed_condition": None},
            "cde": {"identifiable": True, "adjustment": [],
                    "failed_condition": None},
            "numeric": {"nde_nie_status": {
                "status": "insufficient_theta",
                "missing_key": "P(m | x)",
                "need": "theta_entry_missing",
                "said": {"key": "P(m | x)"}}},
        }},
        ("没能算出数", "P(m | x)"),
        ("insufficient_theta",),
    ),
    (
        "the Wald cells the caveat points at are shown",
        {"iv_identification": {
            "strategy": "iv", "instrument": "z", "conditioning": ["w"],
            "required_assumption": "monotonicity", "alternatives_count": 1,
            "numeric": {
                "conditioning_order": ["w"],
                "strata": [{"values": [True], "weight": 0.4,
                            "p_y_given_z_treated": 0.7,
                            "p_y_given_z_control": 0.4,
                            "p_x_given_z_treated": 0.9,
                            "p_x_given_z_control": 0.3}],
                "outcome_shift": 0.3, "treatment_shift": 0.48, "late": 0.625,
            },
        }},
        ("Wald 比值的逐格明细", "w=True", "依从者", "不是各格比值的平均"),
        ("p_y_given_z_treated", "treatment_shift"),
    ),
    (
        "a transported number names both populations",
        {"transport_identification": {
            "kind": "transport_identification",
            "source_population": "nyc", "target_population": "la",
            "s_nodes": [], "adjustment_set": [], "formula_repr": "...",
            "numeric": {"value": 0.31, "source_population": "nyc",
                        "target_population": "la"},
        }},
        ("迁移后的数", "nyc", "la"),
        ("target_population",),
    ),
    (
        "a recovery says what it licenses you to compute",
        {"selection_recovery": {
            "kind": "selection_recovery", "query_kind": "effect",
            "treatment": "x", "outcome": "y", "recoverable": True,
            "criterion": "selection_backdoor", "selection_nodes": ["s"],
            "adjustment_set": ["w"], "z_plus": ["w"], "z_minus": [],
            "recovery_formula": "Σ_w P(y | x, w, S=1) P(w)",
            "external_data_needed": [], "failure_reason": None,
            "reference": "Bareinboim & Pearl 2012",
        }},
        ("恢复式", "Σ_w P(y | x, w, S=1) P(w)", "挡后门路径的是它"),
        ("recovery_formula", "z_plus"),
    ),
    (
        "the half of the adjustment set that blocks nothing says so",
        {"selection_recovery": {
            "kind": "selection_recovery", "query_kind": "effect",
            "treatment": "x", "outcome": "y", "recoverable": True,
            "criterion": "selection_backdoor", "selection_nodes": ["s"],
            "adjustment_set": ["w", "v"], "z_plus": ["w"], "z_minus": ["v"],
            "recovery_formula": "Σ_w [ Σ_v P(y|x,w,v,S)·P(v|x,w) ] · P(w)",
            "external_data_needed": [], "failure_reason": None,
            "reference": "Bareinboim & Pearl 2012",
        }},
        ("Z⁺={w}", "挡后门路径的是它", "Z⁻={v}", "是处理的**后代**",
         "挡不了后门", "重加权"),
        ("z_minus",),
    ),
    (
        "a missingness recovery says which order works",
        {"missing_data_recovery": {
            "kind": "missing_data_recovery", "target": "P(y | x)",
            "mechanism": "MAR", "recoverable": True,
            "partially_observed": ["z"],
            "factorization": [{"factor": "y", "conditioned_on": ["x", "z"]},
                              {"factor": "z", "conditioned_on": []}],
            "recovery_formula": "P(y|x,z)P(z)", "failure_reason": None,
            "reference": "Mohan, Pearl & Tian 2013",
            "adjustment_set": ["z"], "covariate_recovery": None,
            "estimand": {"target": "P(y | do(x))", "recoverable": True,
                         "recovery_formula": "Σ_z P(y|x,z)P(z)",
                         "requires": ["P(y|x,z)", "P(z)"],
                         "failure_reason": None},
        }},
        ("拆成 2 个因子", "P(y | x、z)", "Σ_z P(y|x,z)P(z)",
         "都被观测到的行上估"),
        ("factorization",),
    ),
)


@pytest.mark.parametrize(
    "why,extensions,expected,forbidden", _SAYS,
    ids=[case[0] for case in _SAYS])
def test_the_reader_gets_a_sentence_and_not_the_identifier(
        why, extensions, expected, forbidden):
    from themis.output import analysis_report

    text = analysis_report.build_analysis_report({
        "status": "numerically_solved", "query_id": "q",
        "query_kind": "effect", "extensions": extensions,
    })
    assert "## 怎么算出来的" in text, (
        f"{why}: nothing landed in the section that asks for it"
    )
    for phrase in expected:
        assert phrase in text, f"{why}: the report never says {phrase!r}"
    for token in forbidden:
        assert token not in text, (
            f"{why}: the report prints the identifier {token!r} at the reader"
        )


#: One counterfactual cell per assignment of the four booleans that decide
#: WHICH cell it is, and the sentence each must produce. Not one case: the
#: whole point is that the four are not decoration on one question, and a
#: renderer that read them and printed a fixed sentence would pass a single
#: case.
_CELLS: tuple[tuple[dict, tuple[str, ...]], ...] = (
    ({"observed_x": True, "counterfactual_x": False, "target_y": True,
      "factual_y": True},
     ("实际接受了处理", "且结局发生了", "若当初没接受处理", "结局会发生")),
    ({"observed_x": False, "counterfactual_x": True, "target_y": False,
      "factual_y": None},
     ("实际没接受处理", "若当初接受了处理", "结局不会发生")),
)


@pytest.mark.parametrize("cell,expected", _CELLS,
                         ids=["treated-factual", "untreated-no-factual"])
def test_the_counterfactual_interval_says_which_cell(cell, expected):
    """An interval on a quantity with no name is not checkable by a reader.

    The four booleans are the whole identity of the cell, and both surfaces
    used to open with "该反事实格" — which names none of them, and reads the
    same for every one of the eight questions this block can be asked.
    """
    from themis.output import analysis_report

    text = analysis_report.build_analysis_report({
        "status": "numerically_solved", "query_id": "q",
        "query_kind": "counterfactual",
        "numeric_estimate": {
            "method": "counterfactual_cell_plugin", "sample_size": 900,
            "counterfactual_cell": {
                **cell, "lower": 0.21, "upper": 0.63,
                "interventional_risk_provenance": "backdoor_adjustment",
            },
        },
    })
    for phrase in expected:
        assert phrase in text, f"the report never says {phrase!r}"
    for token in ("observed_x", "counterfactual_x", "target_y", "factual_y"):
        assert token not in text, f"the report prints the identifier {token!r}"


def test_the_refuted_share_of_a_declared_monotonicity_is_stated():
    """The closest thing this system has to a test of an untestable premise.

    Resamples with no feasible solution under the declared monotonicity are
    counted rather than skipped, and the share of them says how close that
    premise is to being refuted by this data. Only the detachable explainer
    said it — the same shape as the blocks that reached a reader through the
    scaffolding and not through the report.
    """
    from themis.output import analysis_report

    text = analysis_report.build_analysis_report({
        "status": "numerically_solved", "query_id": "q",
        "query_kind": "counterfactual",
        "numeric_estimate": {
            "method": "counterfactual_cell_plugin", "sample_size": 900,
            "counterfactual_cell": {
                "observed_x": True, "counterfactual_x": False,
                "target_y": True, "factual_y": True,
                "lower": 0.21, "upper": 0.63, "monotonicity": "mtr_positive",
                "interventional_risk_provenance": "backdoor_adjustment",
                "bootstrap_draws_used": 150,
                "bootstrap_draws_infeasible": 50,
            },
        },
    })
    assert "25% 的重抽样在所声明的单调性下无解" in text, text
    for token in ("bootstrap_draws_used", "bootstrap_draws_infeasible"):
        assert token not in text, f"the report prints the identifier {token!r}"


def test_a_real_theta_mediation_run_states_its_decomposition():
    """End to end, on the case the omission was found with.

    The pins above build an envelope; this one asks the kernel for one. What
    it holds is that the numbers the runtime computes are the numbers the
    reader is shown — a renderer held only to a synthesized envelope can be
    reading a shape the producer stopped writing.
    """
    import themis
    from themis.output.analysis_report import build_analysis_report
    from .test_runtime.test_mediation_numeric import _q1358_program

    result = themis.run(_q1358_program())["results"][0]
    numeric = result["extensions"]["mediation_decomposition"]["numeric"]
    text = build_analysis_report(result)
    for key in ("te", "nde_at_control", "nie_at_treated"):
        shown = f"{numeric[key]:.4g}"
        assert shown in text, (
            f"the report never shows {key}={shown}; the headline is TE alone "
            f"and the arms are the finding"
        )
    assert "两条通路方向相反" in text, (
        "NDE and NIE have opposite signs on this case and the report does "
        "not say so; their sum reads as one direction"
    )


def test_a_route_that_declares_its_own_premises_gets_them_on_the_ledger():
    """The channel that exists when no estimator ran.

    A mediation identification states the cross-world conditions "可识别"
    is conditional on, in ids the glossary already translates, and the
    ledger read four channels of which this was not one. Wherever an
    estimator later ran it declared the same ids flat, so the omission was
    invisible exactly where there was a number.
    """
    import themis
    from themis.output.analysis_report import build_analysis_report
    from .test_runtime.test_mediation_numeric import _q1358_program

    result = themis.run(_q1358_program())["results"][0]
    declared = ((result["extensions"]["mediation_decomposition"]
                 .get("nde_nie") or {}).get("assumptions") or [])
    assert declared, "this case no longer declares its own premises"
    ledger = result["extensions"].get("assumption_ledger") or {}
    carried = {e.get("id") for e in (ledger.get("assumptions") or ())}
    missing = [a for a in declared if a not in carried]
    assert not missing, (
        f"the block declares {missing} and the ledger does not carry them; "
        f"an assumption that never reaches the ledger reads, to every "
        f"consumer, like an assumption nobody makes"
    )
    text = build_analysis_report(result)
    assert "## 假设" in text and "Pearl 2001 中介分解四条件" in text, (
        "the premises are on the ledger and the reader still does not see "
        "them"
    )


def test_both_surfaces_state_the_same_theta_parts():
    """The four paths, on both surfaces, in one order.

    :mod:`tests.test_the_answer_has_no_silent_parts` holds the whole detail
    table equal across the surfaces; this asks only that the theta paths are
    in it, so that a table re-keyed back to one container fails here with the
    reason rather than there with a diff.
    """
    from themis.output import analysis_report

    report = [name for name, _ in analysis_report._NUMERIC_DETAIL_RENDERERS]
    browser = re.findall(r"'([^']+)'", web_source.literal(
        "NUMERIC_DETAIL_ORDER", web_source.read(web_source.VERDICT)))
    theta = [
        "extensions.iv_identification.numeric",
        "extensions.mediation_decomposition.numeric",
        "extensions.mediation_joint_decomposition.numeric",
        "extensions.transport_identification.numeric",
    ]
    for path in theta:
        assert path in report, f"the report no longer states {path}"
        assert path in browser, f"the browser no longer states {path}"
