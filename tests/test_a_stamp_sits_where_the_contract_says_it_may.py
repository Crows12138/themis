"""Where a bootstrap stamp may sit is a question the contract answers.

A stamp says how an interval's replicates were drawn, and ``kind`` says
whether they were whole clusters or independent rows. The difference is the
unit of independence: honour it and the interval widens, drop it and the
interval is anti-conservative while the number on the page looks the same.
So the word is the whole of the disclosure, and on fourteen bounds rows it
was unheld -- the forged spellings were refused by the schema, and the one
lie the contract leaves, ``iid`` in place of ``cluster``, went through every
door.

The module written for exactly this failure was watching somewhere else. It
read ``result["numeric_bounds"]["numeric_cluster"]``, and the result schema
closes its top level and does not declare ``numeric_bounds``: no answer that
passes the door has ever carried one, nothing in the package writes one, and
so the check reading it could not fire. What the producer calls
``_attach_numeric_bounds`` fills a ROW of ``bounds_results``, and
``numeric_cluster`` is declared on that row and on nothing else. The
container was named after a producer's function rather than after the
envelope.

The contract declares a stamp in four places and the corpus carries stamps
in all four. The module walked three.

What closes the fourteen is not a new kind of reading. It is the same two
questions this module already asked of the estimate -- does this block
contradict itself, and does it agree with what the run resolved -- now
asked wherever the contract says a stamp may sit. The first of those is a
biconditional the contract states in prose and cannot carry: an enum beside
a closed object accepts ``iid`` next to a named cluster column either way
round.

One direction does not come along, and it is named in the module rather
than left to be discovered: a bounds row has an ``assumptions`` slot that no
producer fills, so the corroboration this module asks of the estimate has
nothing to ask of a row. Thirteen of the fourteen rows carry ``None`` there
and both of the clustered ones are among them, which is measured below --
requiring the row's own words would refuse the answers this repository
honestly produces today.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.verifier import cluster_inference_rules as _rules
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json")
    .read_text("utf-8"))
DEFS = "$defs"

OTHER = {"iid": "cluster", "cluster": "iid"}


def _stamped_rows():
    """Every stored bounds row carrying a bootstrap stamp."""
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        for index, row in enumerate(result.get("bounds_results") or ()):
            if isinstance(row.get("bootstrap"), dict):
                yield name, index, row


ROWS = tuple(_stamped_rows())
IDS = tuple(f"{name}[{index}]" for name, index, _row in ROWS)
CARRYING = tuple(sorted({name for name, _i, _r in ROWS}))


def _run_cluster(name):
    context = SHAPES[name]["result"].get("estimation_context") or {}
    return context.get("cluster")


def _forge(name, index, mutate):
    """A deep copy of one stored answer with one row's block tampered."""
    result = copy.deepcopy(SHAPES[name]["result"])
    row = result["bounds_results"][index]
    mutate(row, row["bootstrap"])
    return result


def _refused(name, result, pattern=None):
    """Refused by the rule, and refused again through a public door.

    Both, because a rule that refuses while the door that runs it does not
    is a rule nobody reaches. Which door is a fact about the answer -- the
    chain door needs a chain -- so it is chosen by ``the_door_for`` rather
    than picked here.
    """
    program = SHAPES[name]["program"]
    with pytest.raises(VerificationError, match=pattern or "."):
        _rules.verify_cluster_inference(result)
    with pytest.raises(Exception):
        the_door_for(SHAPES[name]["result"])(program, result)


# ==================================================== what is actually here


def test_the_corpus_carries_the_rows_this_gate_is_about():
    """The census, so a later reading of these numbers is a reading of a
    measurement rather than of this gate's memory of one."""
    assert len(ROWS) == 14
    assert len(CARRYING) == 13
    kinds = sorted(row["bootstrap"].get("kind") for _n, _i, row in ROWS)
    assert kinds.count("iid") == 12
    assert kinds.count("cluster") == 2


def test_a_bounds_row_without_a_stamp_reports_no_interval():
    """Why the eighty-two bare rows are not this gate's question, measured
    rather than assumed: the contract says an absent block means no
    bootstrap ran, and every bare row here is a row with no interval."""
    bare = [(name, index, row)
            for name in sorted(SHAPES)
            for index, row in enumerate(
                SHAPES[name]["result"].get("bounds_results") or ())
            if not isinstance(row.get("bootstrap"), dict)]
    assert len(bare) == 82
    assert not [one for one in bare
                if one[2].get("ci_lower") is not None
                or one[2].get("ci_upper") is not None]


def test_the_clustered_runs_are_four_and_two_of_them_bound_anything():
    """The whole population the run-level half of this rule can speak
    about. Small, and saying so is what keeps 'every bend was refused' from
    reading as broader coverage than it is."""
    clustered = {name for name in SHAPES if _run_cluster(name) is not None}
    assert len(clustered) == 4
    with_rows = {name for name in clustered
                 if SHAPES[name]["result"].get("bounds_results")}
    assert len(with_rows) == 2
    assert sorted(_run_cluster(name) for name in with_rows) == \
        ["clinic", "site"]


# ====================================== where the contract says a stamp may sit


def _declared_stamp_sites(node, path="", seen=frozenset()):
    """Every place the result schema declares a ``bootstrap`` property.

    The test's own reading of the contract, expanded through ``$ref`` --
    written here rather than imported so that the module and the gate do
    not agree by sharing one walk.
    """
    if not isinstance(node, dict):
        return
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.rsplit("/", 1)[1]
        if name not in seen:
            yield from _declared_stamp_sites(
                SCHEMA[DEFS][name], path, seen | {name})
        return
    for key, sub in (node.get("properties") or {}).items():
        if key == "bootstrap":
            yield f"{path}.bootstrap".lstrip(".")
        yield from _declared_stamp_sites(sub, f"{path}.{key}", seen)
    items = node.get("items")
    if isinstance(items, dict):
        yield from _declared_stamp_sites(items, f"{path}.[]", seen)


DECLARED_SITES = frozenset(_declared_stamp_sites(SCHEMA))


def test_the_contract_declares_four_places_a_stamp_may_sit():
    assert DECLARED_SITES == {
        "numeric_estimate.bootstrap",
        "numeric_estimate.acr_decomposition.bootstrap",
        "numeric_estimate.four_way_ratio.bootstrap",
        "bounds_results.[].bootstrap",
    }


def _stamps_in(node, path=""):
    """Every stamp actually present on one answer, by where it sits."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "bootstrap" and isinstance(value, dict):
                yield f"{path}.bootstrap".lstrip(".")
            else:
                yield from _stamps_in(value, f"{path}.{key}".lstrip("."))
    elif isinstance(node, list):
        for value in node:
            yield from _stamps_in(value, f"{path}.[]")


def test_every_place_the_contract_declares_carries_a_stamp_here():
    """None of the four is hypothetical, so none of them is a place the
    module may reach 'in principle' and never be asked about."""
    found = {}
    for name in sorted(SHAPES):
        for where in _stamps_in(SHAPES[name]["result"]):
            found[where] = found.get(where, 0) + 1
    assert set(found) == DECLARED_SITES
    assert found["bounds_results.[].bootstrap"] == 14
    assert sum(found.values()) == 44


def test_the_module_reaches_every_place_the_contract_declares():
    """The gate's own sentence. The walk is asked of every stored answer
    and the places it arrives at are compared with the contract's -- which
    is the check that was missing for as long as the module answered this
    question from a producer's function name."""
    def owner(site):
        """The block a declared site's stamp belongs to."""
        parent = site.split(".")[-2]
        return "bounds_results" if parent == "[]" else parent

    reached = set()
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        for where, block, stamp, _declared in _rules._stamped_blocks(result):
            assert stamp is block["bootstrap"]
            reached.add(where.split("[")[0])
    assert reached == {owner(site) for site in DECLARED_SITES}
    assert len(reached) == 4


# ============================================ the container that was watched


def test_the_container_that_was_watched_is_not_one_the_contract_has():
    """Not 'rare' and not 'absent from the corpus'. The top level is closed
    and this key is not in it, so an answer carrying one cannot pass the
    door at all."""
    assert SCHEMA.get("additionalProperties") is False
    assert "numeric_bounds" not in SCHEMA["properties"]
    assert "bounds_results" in SCHEMA["properties"]
    assert not [name for name in SHAPES
                if "numeric_bounds" in SHAPES[name]["result"]]


def test_the_column_is_declared_on_exactly_one_container():
    """Which is why reading it off the top level found nothing, and why the
    rule reads it where it is PRESENT rather than demanding it of every
    block: an estimate has no such slot to be missing."""
    def containers(node, path=""):
        if isinstance(node, dict):
            if "numeric_cluster" in (node.get("properties") or {}):
                yield path
            for key, sub in (node.get("properties") or {}).items():
                yield from containers(sub, f"{path}.{key}")
            for key, sub in (node.get(DEFS) or {}).items():
                yield from containers(sub, f"{DEFS}.{key}")
            items = node.get("items")
            if isinstance(items, dict):
                yield from containers(items, f"{path}.[]")
    assert sorted(containers(SCHEMA)) == ["$defs.boundsResult"]


def test_the_module_no_longer_reads_a_container_it_does_not_have():
    source = pathlib.Path(_rules.__file__).read_text("utf-8")
    assert not hasattr(_rules, "_check_bounds")
    body = source.split('"""', 2)[2]      # past the module docstring
    assert 'get("numeric_bounds")' not in body
    assert "numeric_bounds" in source     # the docstring still says why


# ==================================================== the honest direction


@pytest.mark.parametrize("name", CARRYING)
def test_every_answer_carrying_a_stamped_row_is_still_accepted(name):
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])
    _rules.verify_cluster_inference(SHAPES[name]["result"])


def test_no_stored_answer_is_refused_by_this_rule():
    """Every one, not only the thirteen: a rule that reaches further is a
    rule with more answers to be wrong about."""
    for name in sorted(SHAPES):
        _rules.verify_cluster_inference(SHAPES[name]["result"])


# ============================================================== the bends


def test_the_swap_is_the_only_lie_this_slot_can_tell():
    """Why every bend below is a swap. The contract gives ``kind`` two
    members and closes the block, so a coined spelling is refused by the
    schema before any rule reads it; what is left is the other member."""
    kind = SCHEMA[DEFS]["bootstrapDraws"]["properties"]["kind"]
    assert set(kind["enum"]) == {"iid", "cluster"}
    assert SCHEMA[DEFS]["bootstrapDraws"]["additionalProperties"] is False


def test_the_swap_is_a_word_these_answers_could_honestly_have_written():
    """And why it is worth a rule at all: the swapped word is a legal
    spelling of this slot, so nothing about the forged answer looks wrong
    to a reader of the block's shape."""
    for name, index, row in ROWS:
        forged = _forge(name, index,
                        lambda r, s: s.update(kind=OTHER[s["kind"]]))
        assert forged["bounds_results"][index]["bootstrap"]["kind"] in \
            SCHEMA[DEFS]["bootstrapDraws"]["properties"]["kind"]["enum"]


@pytest.mark.parametrize("name,index,row", ROWS, ids=IDS)
def test_swapping_the_kind_of_a_row_is_refused(name, index, row):
    """The frontier itself, one row at a time."""
    forged = _forge(name, index,
                    lambda r, s: s.update(kind=OTHER[s["kind"]]))
    _refused(name, forged, "")


@pytest.mark.parametrize("name,index,row", ROWS, ids=IDS)
def test_a_row_naming_a_second_different_column_is_refused(
        name, index, row):
    """One loop ran, so one column was resampled. The row's own
    ``numeric_cluster`` and its stamp are two records of that one loop."""
    forged = _forge(name, index,
                    lambda r, s: r.update(numeric_cluster="ward"))
    _refused(name, forged, "")


CLUSTERED_ROWS = tuple(one for one in ROWS
                       if one[2]["bootstrap"].get("kind") == "cluster")
IID_ROWS = tuple(one for one in ROWS
                 if one[2]["bootstrap"].get("kind") == "iid")


@pytest.mark.parametrize(
    "name,index,row", CLUSTERED_ROWS,
    ids=[f"{n}[{i}]" for n, i, _r in CLUSTERED_ROWS])
def test_a_cluster_stamp_that_says_which_column_nowhere_is_refused(
        name, index, row):
    """The contract's prose, in the direction that needs no container
    knowledge: every stamp is a ``bootstrapDraws`` and every
    ``bootstrapDraws`` has this slot."""
    forged = _forge(name, index,
                    lambda r, s: s.pop("cluster_column", None))
    _refused(name, forged, "does not say which column")


@pytest.mark.parametrize(
    "name,index,row", IID_ROWS,
    ids=[f"{n}[{i}]" for n, i, _r in IID_ROWS])
def test_an_iid_stamp_that_still_names_a_column_is_refused(
        name, index, row):
    """The other direction of the same sentence, and a hold this repository
    did not have anywhere: a block saying two things is refused by itself,
    without needing anything else on the answer to disagree with it."""
    forged = _forge(name, index,
                    lambda r, s: s.update(cluster_column="ward"))
    _refused(name, forged, "read both ways")


# ============================ what the rows cannot be asked, said out loud


def test_no_stamped_row_declares_anything_about_its_own_loop():
    """The cost, as a measurement. A bounds row HAS an ``assumptions``
    slot; no producer fills it, so the corroboration this module asks of
    the estimate has nothing to ask of a row."""
    declared = [row.get("assumptions") for _n, _i, row in ROWS]
    assert sum(1 for one in declared if one is None) == 13
    with_words = [(name, index, row) for name, index, row in ROWS
                  if row.get("assumptions")]
    assert len(with_words) == 1
    assert _run_cluster(with_words[0][0]) is None


def test_the_words_route_would_refuse_the_honest_clustered_rows():
    """Which is why it was not moved onto the rows. Asked directly of the
    two rows whose run really did resolve a column: neither can pass the
    test the estimate is put to, and both are honest."""
    assert len(CLUSTERED_ROWS) == 2
    for name, _index, row in CLUSTERED_ROWS:
        column = _run_cluster(name)
        assert column is not None
        assert not _rules._names(row.get("assumptions"), column)


def test_a_cluster_row_whose_second_copy_is_missing_is_accepted():
    """The one hold the asymmetry costs, pinned so that it stays a decision
    rather than becoming a surprise. Refusing this needs the rule to know
    that a bounds row DECLARES ``numeric_cluster``, which is the table of
    containers this frontier is about not having."""
    name, index, _row = CLUSTERED_ROWS[0]
    forged = _forge(name, index, lambda r, s: r.pop("numeric_cluster", None))
    assert forged["bounds_results"][index]["bootstrap"]["cluster_column"]
    _rules.verify_cluster_inference(forged)


# ============================================================== the readers


def test_the_walk_hands_over_the_block_and_what_describes_it():
    result = {
        "estimation_context": {"cluster": "clinic"},
        "numeric_estimate": {"assumptions": ["ci_via_pairs_cluster_"
                                             "bootstrap_on_clinic"],
                             "bootstrap": {"kind": "cluster",
                                           "cluster_column": "clinic",
                                           "requested": 9, "used": 9}},
        "bounds_results": [{"method": "manski_natural",
                            "numeric_cluster": "clinic",
                            "bootstrap": {"kind": "cluster",
                                          "cluster_column": "clinic",
                                          "requested": 9, "used": 9}}],
    }
    got = list(_rules._stamped_blocks(result))
    assert [where for where, _b, _s, _d in got] == [
        "numeric_estimate", "bounds_results['manski_natural']"]
    assert got[0][3] == ["ci_via_pairs_cluster_bootstrap_on_clinic"]
    assert got[1][3] is None
    assert got[1][1]["numeric_cluster"] == "clinic"


def test_the_walk_is_silent_where_there_is_no_stamp():
    assert list(_rules._stamped_blocks({})) == []
    assert list(_rules._stamped_blocks(
        {"bounds_results": [{"method": "manski_natural"}]})) == []


def _block(kind, *, cluster_column=None, numeric_cluster=None):
    stamp = {"kind": kind, "requested": 9, "used": 9}
    if cluster_column is not None:
        stamp["cluster_column"] = cluster_column
    block = {"bootstrap": stamp}
    if numeric_cluster is not None:
        block["numeric_cluster"] = numeric_cluster
    return block, stamp


@pytest.mark.parametrize("kind,column,beside,run,declared,pattern", [
    ("cluster", None, None, "clinic", None, "does not say which column"),
    ("iid", "clinic", None, None, None, "read both ways"),
    ("iid", None, "clinic", None, None, "read both ways"),
    ("cluster", "clinic", "ward", "clinic", None, "names more than one"),
    ("cluster", "clinic", None, None, None, "no run-level basis"),
    ("cluster", "ward", None, "clinic", None, "but the run resolved"),
    ("cluster", "clinic", None, "clinic", ["nothing about it"],
     "unattributed"),
    ("iid", None, None, "clinic", None, "no declarations of its own"),
])
def test_one_block_is_refused_for_the_reason_it_earns(
        kind, column, beside, run, declared, pattern):
    """Each arm on its own, so that a change to one is visible as a change
    to that one rather than as a count moving somewhere."""
    block, stamp = _block(kind, cluster_column=column,
                          numeric_cluster=beside)
    with pytest.raises(VerificationError, match=pattern):
        _rules._check_one_block("where", block, stamp, run, declared)


@pytest.mark.parametrize("kind,column,beside,run,declared", [
    ("iid", None, None, None, None),
    ("iid", None, None, "clinic", ["ci_not_cluster_robust_ignores_clinic"]),
    ("cluster", "clinic", "clinic", "clinic", None),
    ("cluster", "clinic", None, "clinic",
     ["ci_via_pairs_cluster_bootstrap_on_clinic"]),
])
def test_one_block_is_accepted_where_it_says_what_it_did(
        kind, column, beside, run, declared):
    block, stamp = _block(kind, cluster_column=column,
                          numeric_cluster=beside)
    _rules._check_one_block("where", block, stamp, run, declared)
