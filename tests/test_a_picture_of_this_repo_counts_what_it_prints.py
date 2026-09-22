"""A drawing of this repository may not print a number nobody measured.

``scripts/build_arch_spec.py`` builds the architecture picture's spec.
Every count on that picture — line counts, species, routes, rule names,
``verify_*`` entries, the highest T10 gate — is measured from the code at
build time rather than typed into the drawing, and the hand-written half
(which boxes exist, which of them an arrow joins) is held to what the
repository can deny.

This file is that holding. Each gate is asked twice: once with the
arrangement the repository actually has, and once with the single thing
the gate exists to catch. A gate only ever asked the first question has
not been shown to be a gate — it may be a function that returns an empty
list.

The sentence on the audit boundary gets the same treatment. It claims no
verifier module imports ``themis.output``. The scan that checks it is
pointed at ``themis/estimation`` as well, where the answer is not empty,
so its silence about the verifier is a measurement rather than an
inability to speak.

The picture itself is committed, under ``docs/架构图/``. A drawing checked
into a repository is a copy of facts that go on changing without it, so
it is held to them here: the committed spec has to equal one built from
the code as it stands, and every word that spec puts on the picture has
to be on the rendered page. Rendering needs a tool that does not live in
this repository, which is exactly why the page is compared to the spec by
its words rather than rebuilt — a page that cannot be rebuilt here can
still be read here.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_arch_spec.py"
PICTURE_SPEC = REPO_ROOT / "docs/架构图/全景图.json"
PICTURE_PAGE = REPO_ROOT / "docs/架构图/全景图.html"

REBUILD = ("图过期了。重跑：python scripts/build_arch_spec.py "
           "docs/架构图/全景图.json，再 node <archify>/bin/archify.mjs "
           "render architecture docs/架构图/全景图.json docs/架构图/全景图.html "
           "--quality showcase --repo-root .（页面要渲染，不要手改）")

#: A path that is not there, built out of one that is.
#:
#: ``test_prose_resolves_at_head`` holds every source file in this
#: repository to naming only paths that exist, which is right and which
#: this file would break by spelling a missing one out. So the missing
#: path is computed rather than written: the literal below resolves, and
#: what the check is handed does not.
GONE = "themis/types.py".replace(".py", "-is-not-a-file.py")


def _load():
    spec = importlib.util.spec_from_file_location("build_arch_spec", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_arch_spec", module)
    spec.loader.exec_module(module)
    return module


ARCH = _load()


# ------------------------------------------------------- 诚实的那一侧

def test_the_tables_agree_with_the_repository():
    assert ARCH.check() == []


def test_the_spec_builds():
    spec = ARCH.build(revision="0" * 40)
    assert spec["diagram_type"] == "architecture"
    assert len(spec["components"]) == len(ARCH.COMPONENTS)
    assert len(spec["connections"]) == len(ARCH.EDGES)
    assert len(spec["boundaries"]) == len(ARCH.BOUNDARIES)


def test_every_number_the_picture_prints_was_measured():
    numbers = ARCH.measure()
    assert ARCH.check_measurements(numbers) == []
    assert all(value > 0 for value in numbers.values()), numbers


def test_no_count_is_typed_into_a_label():
    """A number reaches a label through a placeholder, or it is named.

    A number written straight into a sublabel is a count with no
    declaration site — the thing this script exists to stop. Numbers that
    are not counts (a port, a gate's name, a CORE_STATUS entry number)
    are allowed, but each has to be listed in ``NOT_A_COUNT`` beside the
    reason, so a new one cannot arrive unnoticed.

    Written as a word as well as in digits. A label saying a package has
    eight doors is the same claim as one saying it has 8, and this read
    only the second until a ninth door arrived and the label stayed as it
    was. A word that merely contains such a character is a word, and says
    so in the exemption beside it.
    """
    import re
    offenders = []
    for cid, _t, label, sublabel, tag, _pos, _src in ARCH.COMPONENTS:
        for text in (label, sublabel, tag):
            if not text or text in ARCH.NOT_A_COUNT:
                continue
            if re.search(r"[\d一二三四五六七八九十百千]",
                         re.sub(r"\{[a-z_]+\}", "", text)):
                offenders.append((cid, text))
    assert not offenders, offenders


def test_nothing_is_excused_that_does_not_need_excusing():
    """The other side: a stale exemption is a gate that stopped biting."""
    printed = {text for _c, _t, label, sublabel, tag, _p, _s
               in ARCH.COMPONENTS for text in (label, sublabel, tag) if text}
    stale = set(ARCH.NOT_A_COUNT) - printed
    assert not stale, stale


def test_the_boundary_sentence_is_true_of_the_code():
    assert ARCH.imports_from_output("verifier") == []
    assert ARCH.check_the_claim_on_the_boundary() == []


def test_that_scan_can_say_yes_somewhere_else():
    """Otherwise its silence about the verifier proves nothing."""
    elsewhere = ARCH.imports_from_output("estimation")
    assert elsewhere, "扫描器在任何地方都说不出话，它对 verifier 的沉默就不算数"


def test_every_arrow_kind_is_declared_and_every_declared_kind_is_used():
    used = {edge[2] for edge in ARCH.EDGES}
    assert used <= set(ARCH.VARIANT_OF)
    assert set(ARCH.VARIANT_OF) <= used


def test_the_audit_arrow_is_the_only_emphasised_one():
    spec = ARCH.build(revision="0" * 40)
    emphasised = [(c["from"], c["to"]) for c in spec["connections"]
                  if c.get("variant") == "emphasis"]
    assert emphasised == [("orch", "verify")]


def test_no_box_floats_free_of_the_picture():
    ends = {end for edge in ARCH.EDGES for end in edge[:2]}
    assert {c[0] for c in ARCH.COMPONENTS} == ends


def test_every_box_belongs_to_one_layer_at_most():
    seen: dict[str, str] = {}
    for _kind, label, wraps in ARCH.BOUNDARIES:
        for wrapped in wraps:
            assert wrapped not in seen, (wrapped, seen.get(wrapped), label)
            seen[wrapped] = label


# ------------------------------------------------- 签进来的那份图本身

def _committed_spec() -> dict:
    return json.loads(PICTURE_SPEC.read_text(encoding="utf-8"))


def test_the_committed_picture_is_the_one_this_code_would_draw():
    """The only field exempt is the commit it pins.

    Everything else — every count, every cited path, every box and arrow
    — has to be what building it right now produces. The pin is exempt
    because it moves on its own with each commit, and a comparison that
    reddened for that reason would be teaching people to ignore it.
    """
    committed = _committed_spec()
    pinned = committed["meta"]["repository"]["revision"]
    assert ARCH.build(revision=pinned) == committed, REBUILD


def test_the_commit_the_picture_pins_is_one_this_repository_has():
    committed = _committed_spec()
    pinned = committed["meta"]["repository"]["revision"]
    try:
        kind = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "cat-file", "-t", pinned],
            capture_output=True, text=True)
    except FileNotFoundError:  # pragma: no cover - git absent
        pytest.skip("git 不在 PATH 上")
    assert kind.returncode == 0 and kind.stdout.strip() == "commit", pinned


def _words_the_spec_puts_on_the_picture(spec: dict) -> list[str]:
    words = [spec["meta"]["subtitle"]]
    words += [view["note"] for view in spec["meta"]["views"]]
    for component in spec["components"]:
        words += [component["label"], component.get("sublabel"),
                  component.get("tag")]
    words += [boundary["label"] for boundary in spec["boundaries"]]
    words += [c["label"] for c in spec["connections"] if c.get("label")]
    return [w for w in words if w]


def test_the_page_says_what_the_spec_says():
    """The half a test here cannot rebuild, read instead.

    The renderer lives outside this repository, so the committed page
    cannot be regenerated and compared byte for byte. It can be read: if
    the spec has been rebuilt and the page has not, a count that changed
    is in one file and not the other, and that is visible from here.
    """
    spec = _committed_spec()
    page = PICTURE_PAGE.read_text(encoding="utf-8")
    missing = [w for w in _words_the_spec_puts_on_the_picture(spec)
               if w not in page]
    assert not missing, f"{REBUILD}；页面上找不到：{missing[:6]}"


def test_the_page_names_the_commit_the_spec_pins():
    spec = _committed_spec()
    pinned = spec["meta"]["repository"]["revision"]
    page = PICTURE_PAGE.read_text(encoding="utf-8")
    assert pinned[:7] in page, REBUILD


def test_that_reading_would_notice_a_word_that_is_not_there():
    """Both sides: the reading above has to be able to come back empty."""
    spec = _committed_spec()
    page = PICTURE_PAGE.read_text(encoding="utf-8")
    invented = dict(spec)
    invented["boundaries"] = [{"label": "这句话不在页面上", "kind": "region",
                               "wraps": []}]
    missing = [w for w in _words_the_spec_puts_on_the_picture(invented)
               if w not in page]
    assert "这句话不在页面上" in missing


# --------------------------------------------- 每道闸该说不的那一侧

def _bend_components(**edit):
    """A copy of the component table with one row changed."""
    cid = edit.pop("id")
    out = []
    for row in ARCH.COMPONENTS:
        if row[0] == cid:
            row = list(row)
            for index, value in edit.items():
                row[int(index)] = value
            row = tuple(row)
        out.append(row)
    return out


def test_it_refuses_a_source_that_is_not_in_the_repository():
    bent = _bend_components(
        id="contract", **{"6": [(GONE, "物种声明")]})
    problems = ARCH.check(components=bent)
    assert any("引用的文件不存在" in p for p in problems), problems


def test_it_refuses_two_boxes_in_one_cell():
    bent = _bend_components(id="probe", **{"5": (2, 6)})
    problems = ARCH.check(components=bent)
    assert any("同一格" in p for p in problems), problems


def test_it_refuses_an_arrow_that_ends_nowhere():
    bent = [("orch", "verifyer", "audit", "信封", None)]
    problems = ARCH.check(edges=bent)
    assert any("不是任何方块" in p for p in problems), problems


def test_it_refuses_an_arrow_kind_that_was_never_declared():
    bent = [("orch", "verify", "flow", "信封", None)]
    problems = ARCH.check(edges=bent)
    assert any("没有声明" in p for p in problems), problems


def test_it_refuses_a_boundary_around_a_box_that_does_not_exist():
    bent = [("region", "鬼", ["ghost"])]
    problems = ARCH.check(boundaries=bent)
    assert any("边界圈了不存在" in p for p in problems), problems


def test_it_refuses_a_count_that_came_out_zero():
    assert ARCH.check_measurements({"species": 0}) == ["species 数出来是 0"]


def test_build_refuses_rather_than_drawing_a_spec_it_cannot_stand_behind():
    original = ARCH.COMPONENTS
    try:
        ARCH.COMPONENTS = _bend_components(
            id="contract", **{"6": [(GONE, "物种声明")]})
        with pytest.raises(ARCH.SpecRefused) as refused:
            ARCH.build(revision="0" * 40)
        assert "引用的文件不存在" in str(refused.value)
    finally:
        ARCH.COMPONENTS = original
