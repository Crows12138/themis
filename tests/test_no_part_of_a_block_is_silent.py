"""Every key an extensions block declares, and who it reaches.

The question "does this part reach a reader" has been asked three times and
each time of ONE container's own properties. :mod:`themis.blocks` asks it of
the eighteen blocks, because a block name is a string literal repeated at
every writer and every reader and a misspelling there is silence.
:mod:`tests.test_the_answer_has_no_silent_parts` asks it of
``numeric_estimate``'s direct properties, because hanging the reader's
question on the spelling registry had given it a denominator drawn for a
different question. Both lines were moved by hand, after something was found,
and both moved by exactly one level.

What sat below the second line was a whole answer. Four ROUTE blocks carry a
``numeric``: the theta path evaluates a query against a declared joint
distribution rather than estimating it from rows, and it writes what it
computed into the block that identified the estimand. Every renderer is bound
to a container and states that container's question, so a route renderer
states how the estimand was identified — which is not what a number is. On
CLadder Q1358 that meant a report saying "0.1387" and "可识别，无需调整" over
a decomposition whose direct arm was −0.0725 against an indirect arm of
+0.2112: the drug helps through the mediator and hurts around it, which is
the entire finding of a mediation analysis. The IV case is the same omission
with the contradiction visible in one screen — the block's ``late_caveat`` is
printed at the reader in full, saying the value "aggregates the per-stratum
LATEs in ``strata``" and that ``treatment_shift`` is the complier share, and
neither field was rendered anywhere.

That is not one bug repeated. Of the thirty-nine paths this file first found
unreached, some were a family mismatch (an answer hanging off a route block),
some were a renderer that stopped early (a recovery verdict without the
formula it licenses), some were sufficient statistics that never wanted a
reader. Three unrelated causes, one outcome — which is what says the cause is
not on any of them but in there being no denominator at this depth.

WHAT THIS CHECKS. Every key path the schema declares under ``extensions``, at
every depth, is spelled by at least one reader surface — or a row below says
who it is for instead.

WHAT THAT IS WORTH. The check is sound in one direction only: a name no
surface spells cannot be being read, so a failure here is real. The converse
is not true — ``outcome`` spelled in some other renderer counts as coverage
here, a renderer can read a key and print nothing, and a renderer nobody
calls any more still spells every key it ever read. That last one is not
hypothetical: unbinding the counterfactual-cell question and leaving the
function in place passes this check and changes what the reader sees, which
is why the pins at the bottom exist beside it. This is a floor rather
than a guarantee, and the honest measure of the gap is that asking the same
question BLOCK-QUALIFIED — does this block's own bound renderer name this
key — left 77 of 168 leaf names unanswered, most of them legitimately (a
field copied into a sibling block, a citation rendered by the envelope walk,
a key restating the block's own name). Making that measure a gate needs the
renderers to declare what they read; it is registered rather than done.

The atom shape is where the walk stops. ``s_nodes[].affects`` and the
adjustment sets are ``$ref``s into ``atom.schema.json``, which is another
document's subject with its own readers, and pulling it in here would put one
vocabulary's completeness under two files.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass

import pytest

from . import web_source
from .test_vocabulary_reach import VOCABULARIES

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))
DEFS = SCHEMA.get("$defs", {})


# ---------------------------------------------------------------- the schema
def _resolve(spec: dict) -> dict:
    """Follow ``$ref`` while it stays inside this document.

    Both spellings appear: ``#/$defs/name`` and a JSON pointer into
    ``properties``. The joint mediation block reaches the single-mediator
    one that way, and a walk that stopped at the ``$ref`` would leave its
    whole numeric subtree out of the denominator — which is the shape of
    omission this file exists to catch.
    """
    seen = 0
    while isinstance(spec, dict) and "$ref" in spec and seen < 20:
        ref = spec["$ref"]
        if not ref.startswith("#/"):
            return {}
        node: object = SCHEMA
        for step in ref[2:].split("/"):
            if not isinstance(node, dict) or step not in node:
                return {}
            node = node[step]
        spec, seen = node if isinstance(node, dict) else {}, seen + 1
    return spec if isinstance(spec, dict) else {}


def _walk(spec: dict, path: tuple[str, ...], depth: int = 0):
    if depth > 8:
        return
    spec = _resolve(spec)
    for name, sub in (spec.get("properties") or {}).items():
        yield path + (name,)
        yield from _walk(sub, path + (name,), depth + 1)
    items = spec.get("items")
    if isinstance(items, dict):
        yield from _walk(items, path + ("[]",), depth + 1)


EXT = SCHEMA["properties"]["extensions"]
PATHS: tuple[str, ...] = tuple(".".join(p) for p in _walk(EXT, ()))


# -------------------------------------------------------------- the surfaces
def _reads(name: str) -> re.Pattern:
    """The key as a key: quoted, reached as an attribute, or an object key."""
    n = re.escape(name)
    return re.compile(rf"""["']{n}["']|\.{n}\b|(?<![\w.]){n}\?*\s*:""")


def _surfaces() -> dict[str, str]:
    """Every file a reader's words can come out of.

    Three of them, because there are three: the report, the browser, and the
    static page a running server serves when the built bundle is absent.
    ``types.ts`` is excluded — it declares the envelope's shape rather than
    reading it, so counting it would let a field be "reached" by being
    declared.
    """
    out: dict[str, str] = {}
    for path in sorted((REPO / "themis" / "output").rglob("*.py")):
        out[f"output/{path.name}"] = path.read_text(encoding="utf-8")
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        if path.name == "types.ts" or "node_modules" in path.parts:
            continue
        out[f"web/{path.name}"] = path.read_text(encoding="utf-8")
    static = REPO / "themis" / "web" / "static" / "index.html"
    if static.exists():
        out["static/index.html"] = static.read_text(encoding="utf-8")
    return out


SURFACES = _surfaces()


def _spelled(path: str) -> list[str]:
    leaf = path.replace("[]", "").split(".")[-1]
    pattern = _reads(leaf)
    return sorted(f for f, text in SURFACES.items() if pattern.search(text))


# ------------------------------------------------------------------ the rows
@dataclass(frozen=True)
class Silent:
    """One declared key no reader surface spells, and who it is for.

    Exactly one of the three answers is required, and each is checked rather
    than believed: a consumer that does not consume, a source that is itself
    silent, and a vocabulary row that does not cover this site are all ways
    of writing down an answer that is not one.
    """

    holds: str
    #: A module that re-derives something from it. Held to reading the key.
    consumed_by: str = ""
    #: Another declared path, or a block, carrying the same fact to a reader.
    said_by: str = ""
    #: A row in :mod:`tests.test_vocabulary_reach` that already decided this
    #: value needs no word, with the reason written there.
    vocabulary: str = ""


SILENT: dict[str, Silent] = {
    # --- for a verifier, not for a reader -----------------------------------
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
        f"type_reconciliation.checks.[].{stat}": Silent(
            holds="one of the column statistics the type verdict was derived "
                  "from",
            consumed_by="themis.verifier.type_reconciliation_rules",
        )
        # The verdict is what a reader acts on and the report states it; these
        # are what the verifier re-derives it from, which is why they are on
        # the envelope at all. It re-runs the classification and the
        # domain check from them and rejects a verdict they do not support.
        for stat in ("declared_domain", "n_unique", "observed_values",
                     "dtype_kind")
    },

    # --- said by something else ---------------------------------------------
    "iv_identification.strategy": Silent(
        holds="a const restating that this block is the IV route",
        said_by="iv_identification",
    ),
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
    **{
        f"counterfactual_cell.observational_joint{suffix}": Silent(
            holds="the four P(X, Y) cells the bounded counterfactual was "
                  "solved from" if not suffix else "one cell of that joint",
            consumed_by="themis.kernel",
        )
        for suffix in ("", ".p_x1_y1", ".p_x1_y0", ".p_x0_y1", ".p_x0_y0")
    },

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
    assert len(PATHS) > 180, len(PATHS)
    assert "mediation_joint_decomposition.numeric.te" in PATHS, (
        "the walk stopped at a $ref; the joint block's numeric subtree "
        "reaches the single-mediator one that way and is the largest thing "
        "this file would then not be asking about"
    )


def test_every_declared_key_is_spelled_by_a_reader_or_answered_for():
    """The floor: nobody can be reading what nobody spells."""
    unheard = sorted(p for p in PATHS if p not in SILENT and not _spelled(p))
    assert not unheard, (
        f"declared under extensions and named by no reader surface: "
        f"{unheard}; render it, or add a row saying who it is for"
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
    said = [bool(row.consumed_by), bool(row.said_by), bool(row.vocabulary)]
    assert sum(said) == 1, (
        f"{path}: says {sum(said)} of consumed_by / said_by / vocabulary"
    )
    assert row.holds, f"{path}: no row says what a writer puts in it"


@pytest.mark.parametrize("path", sorted(SILENT))
def test_a_row_claiming_silence_is_still_silent(path):
    """Checked in the direction that goes stale.

    Somebody renders it and the row still says nobody does; the reader is
    then told less than the code says, which is this file's own failure
    pointed the other way.
    """
    where = _spelled(path)
    assert not where, (
        f"{path} has a row saying no surface names it, but {where} do; "
        f"the row is stale"
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
    """Deferring to something else only works if that thing arrives."""
    from themis import blocks

    said_by = SILENT[path].said_by
    if said_by in blocks.BY_NAME:
        return
    assert said_by in PATHS, (
        f"{path}: defers to {said_by!r}, which is neither a registered block "
        f"nor a key the schema declares"
    )
    assert said_by not in SILENT and _spelled(said_by), (
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
    raw, spec = spec, _resolve(spec)
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
#: One envelope per theta-path part, and a phrase only a renderer reading it
#: could produce. The rows above check that SOME surface spells the key;
#: these check that reading it comes out as a sentence, for the parts this
#: item rendered.
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
                "reason": "the cross-world formula needs it"}},
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
        ("恢复式", "Σ_w P(y | x, w, S=1) P(w)"),
        ("recovery_formula",),
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
