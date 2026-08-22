"""What a comment may assume its reader has.

Every explanation in this package is written during a session — a
session has an ordinal, a transcript, a train of thought; the code does
not. So the reference that felt precise while writing ("the iter 145
fix", "pre-iter-207", "board #8") lands at HEAD as a name with nothing
behind it, and it does not read as stale, because it was true. That is
the failure mode: an unresolvable reference looks exactly like a
resolvable one from inside the file that wrote it.

    ONE CRITERION. A reader at HEAD, with no session log, no PR thread
    and no uncommitted draft, must be able to resolve every reference a
    comment makes and check every claim it states.

Resolve means: the thing referred to is reachable from the repository —
a symbol, a file, a test name, a published paper, a numbered entry in a
log this repo carries. It does not mean the reader agrees; it means
they can go and look.

WHAT IS NOT LEAKAGE, so this does not get over-applied:

- A reference that names where it resolves. ``wall.md iter 150`` is
  fine and ``iter 150`` is not; the ordinal was never the problem, the
  missing pointer was. wall.md carries 72 of the 143 ordinals this
  package once cited, so even for those, naming the file is what makes
  the difference.
- A counterfactual regression pin. "Reading ``state.x`` directly here
  gives the enriched atoms literal values instead of bind references"
  is a hazard the reader can construct, and deleting it costs the next
  person the bug.
- A measurement with its provenance. Numbers that settled a decision
  belong beside the decision — a rejected alternative whose measurement
  is absent is an assertion, and the next reader is entitled to
  re-propose it. "Measured over 240 random tables it moves the answer
  on 154 of them" is not narrative; it is the evidence.
- A named external source. Hernán & Taubman 2008, Stock-Yogo, Chinn
  2000 — these resolve outside the repo, which is still resolving.
- A dated note, where the date is part of the claim rather than a
  stand-in for one.

WHAT IS. Change narrative that leaves nothing checkable ("this used to
be X"), decisions attributed to a session rather than to a reason,
plans stated in the future tense after they shipped, and any ordinal
naming a session, a board, a slice or a round with no in-repo target.

The check below covers the one subclass that is mechanically decidable.
The rest is what the criterion is for: whether a reference resolves is
not, in general, something a regex can answer, and a gate that pretends
otherwise would license everything it fails to catch.
"""
from __future__ import annotations

import collections
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
WALL = REPO / "wall.md"

#: A session ordinal: ``iter 145``, ``Iter 145``, ``pre-iter-207``.
_ORDINAL = re.compile(r"[Ii]ter[ -]\d+")

#: A mention of the log, and the clause it governs. Anchored on the file
#: rather than on a list of blessed numbers, because the blessing is
#: exactly "wall.md says what this is", and that is checkable.
#:
#: The span runs to the end of the clause, not to the first ordinal in
#: it: "(see wall.md, entries iter 150 and iter 165, …)" is ONE reference
#: carrying two, and both are anchored by the one mention of the file.
_ANCHORED = re.compile(r"wall\.md[^.;)]{0,100}")


#: Prose that says how the system works NOW: the package, its tests, the
#: prompts it loads at run time, and the tables a reader consults to use
#: it. A prompt is the strictest case — an LLM reads it with access to
#: nothing else at all.
GOVERNED_TREES = (
    ("themis", "*.py"), ("tests", "*.py"), ("scripts", "*.py"),
    ("themis", "*.md"), ("docs", "*.md"),
)
GOVERNED_FILES = ("README.md", "COVERAGE_MAP.md")

#: Not this repository's prose. ``sibling/`` is a separate repo kept
#: alongside (the KB adapter contract says Themis must not vendor it) and
#: ``.claude/worktrees`` holds checkouts of this one.
FOREIGN = ("sibling/", ".claude/")

#: Prose where a session IS the subject, so an ordinal is content rather
#: than a dangling pointer. Excluded deliberately and named here, because
#: an unexplained exclusion is how a rule quietly stops applying.
#:
#: - ``wall.md`` is the log that defines the ordinals; every other
#:   reference in the repository resolves by pointing at it.
#: - ``CORE_STATUS.md`` and the phase charters are dated entries — a
#:   changelog and a set of proposals, not a description of the present.
#: - ``docs/l3_simulation`` and ``docs/trial_reports`` and
#:   ``docs/eval_set`` record particular runs, the way a lab notebook
#:   does.
EXEMPT = ("wall.md", "CORE_STATUS.md", "docs/l3_simulation/",
          "docs/trial_reports/", "docs/eval_set/", "_CHARTER.md")


def _sources() -> list[pathlib.Path]:
    """Every governed file, except this one.

    Stating a rule means quoting what breaks it, so the module that holds
    the criterion is the one module guaranteed to violate it — the same
    exemption ``test_no_windows_absolute_paths_in_committed_files`` takes
    for the same reason.
    """
    here = pathlib.Path(__file__).resolve()
    out = [REPO / f for f in GOVERNED_FILES]
    for base, pattern in GOVERNED_TREES:
        out.extend((REPO / base).rglob(pattern))
    return sorted({
        p for p in out
        if "__pycache__" not in p.parts and "node_modules" not in p.parts
        and not any(e in p.relative_to(REPO).as_posix()
                    for e in EXEMPT + FOREIGN)
        and p.resolve() != here
    })


def _unanchored(text: str) -> list[str]:
    """Ordinals left once the clauses naming wall.md are removed."""
    return _ORDINAL.findall(_ANCHORED.sub("", " ".join(text.split())))


def test_no_source_file_cites_a_session_by_ordinal():
    """The decidable subclass: a bare session ordinal.

    It cannot be looked up. wall.md — the only log in the repo that
    carries these — names 72 of the 143 this package once cited, so even
    a citation that happens to be in there resolves only if it says so.
    """
    offenders = {}
    for p in _sources():
        found = _unanchored(p.read_text(encoding="utf-8"))
        if found:
            offenders[str(p.relative_to(REPO))] = sorted(set(found))
    assert not offenders, (
        "these cite a session by ordinal, which a reader at HEAD cannot "
        f"resolve: {offenders}. Either state the defect the ordinal stood "
        "for, or name where it resolves (\"wall.md iter 150\")."
    )


def test_an_ordinal_that_names_wall_md_is_allowed():
    """The reverse boundary, held as a test so it cannot quietly narrow.

    A criterion with no counterexample drifts into "delete every number
    that looks like a session", which would take the pointer out along
    with the dangling reference and lose a real one.
    """
    assert not _unanchored("see wall.md iter 150 for the tracker")
    assert not _unanchored(
        "(see wall.md, entries iter 150 and iter 165, for the tracker)")
    assert _unanchored("the iter 150 tracker") == ["iter 150"]
    assert _unanchored("pre-iter-207 no classifier read it") == ["iter-207"]


#: A repo-relative path named in prose: ``themis/prompts/gap_to_action.md``.
#: Anchored on the top-level directories so ordinary strings ("a/b.py" in
#: an example) are not swept in, and each segment must contain something
#: other than dots — ``benchmarks/.../file.md`` elides a path rather than
#: naming one, and demanding that it exist would be reading an ellipsis
#: as a claim.
_PATH = re.compile(
    r"(?<![\w/.])((?:themis|tests|docs|scripts|benchmarks)"
    r"(?:/(?!\.+/)[\w.\-]+)+\.\w+)"
)

#: Which of those count as a file this repository names. A set beside the
#: pattern rather than an alternation inside it, because an alternation is
#: leftmost-first and not longest-match: with ``ts`` written before ``tsx``
#: every ``.tsx`` path matched as a ``.ts`` one, so the check asked whether
#: a file nobody had ever written was there. The order meant something
#: while nothing said the order meant anything — and the next suffix that
#: extends another would not have failed loudly, it would have quietly
#: shrunk this rule's denominator. Two questions, two mechanisms: the
#: pattern says where a path ends, the set says which endings are ours.
NAMED_SUFFIXES = frozenset({"py", "md", "json", "ts", "tsx", "html"})


def _named_paths(text: str) -> list[tuple[int, str]]:
    """(offset, path) for every repo-relative path the prose names, whole.

    The offset travels with the path because the same path can be named
    twice in one file, and a report that says which line is only useful if
    it says the right one.
    """
    return [(m.start(1), m.group(1)) for m in _PATH.finditer(text)
            if m.group(1).rsplit(".", 1)[-1].lower() in NAMED_SUFFIXES]


def test_no_source_file_names_a_path_that_is_not_there():
    """The second decidable subclass, and the same failure one level over.

    ``test_markdown_cross_links_resolve`` holds this for .md files, which
    left the .py docstrings — where most of this package's prose lives —
    outside it. A whole directory moved and fifteen references kept
    naming the old place, including two that told a reader which file the
    web bridge loads.
    """
    dead = {}
    for p in _sources():
        text = p.read_text(encoding="utf-8")
        for at, named in _named_paths(text):
            if not (REPO / named).exists():
                line = text[:at].count("\n") + 1
                dead.setdefault(str(p.relative_to(REPO)), []).append(
                    f"{line}: {named}")
    assert not dead, f"these name paths that do not exist: {dead}"


def test_a_moved_path_is_caught():
    """The counterexample, for the same reason the other one has one."""
    assert _named_paths("see themis/prompts/response_rendering.md for it")
    assert not _named_paths("see prompts/response_rendering.md")
    # An elided path is not a claim that a file is there.
    assert not _named_paths("under benchmarks/.../agent_prompt_v1.md")
    # A suffix that another suffix is a prefix of arrives whole. Read as an
    # ordered alternation this came back as ``…/Verdict.ts``, and the check
    # then asked whether a file nobody wrote was there.
    assert [p for _, p in _named_paths(
        "themis/web/frontend/src/components/Verdict.tsx")] == [
        "themis/web/frontend/src/components/Verdict.tsx"]
    # And a suffix that is not ours is not a path this rule speaks for.
    assert not _named_paths("themis/web/frontend/src/lib/verdict.ts.orig")


#: A numbered unit of work: ``#358``, ``slice #41``. Two digits or more,
#: so an ordinary "#3" in a citation or a heading is not swept in.
_WORK_ID = re.compile(r"(?<![\w#])#(\d{2,4})\b")


def test_no_source_file_cites_a_numbered_item_that_has_no_entry():
    """The third decidable subclass: an id for work that is not here.

    The backlog these number lives outside the repository, so an id
    resolves only once its entry lands in CORE_STATUS — which means a
    citation of work still open resolves nowhere, and reads exactly like
    a citation of work that shipped. Both were in the tree: one comment
    deferred a live design question to an item number, and three others
    named slices whose numbering nothing here records.
    """
    entries = {
        int(n) for n in _WORK_ID.findall(
            (REPO / "CORE_STATUS.md").read_text(encoding="utf-8"))
    }
    dangling = {}
    for p in _sources():
        text = p.read_text(encoding="utf-8")
        missing = sorted({int(n) for n in _WORK_ID.findall(text)} - entries)
        if missing:
            dangling[str(p.relative_to(REPO))] = missing
    assert not dangling, (
        f"these cite numbered items CORE_STATUS.md does not carry: "
        f"{dangling}. An item still open has no entry, so say the thing it "
        f"stood for instead of deferring to its number."
    )


#: A methodology item where it is DECLARED: the number, then the claim in
#: bold. The same pair is also how one is cited again from a later entry, and
#: the citation says so right after the bold run — see the test below.
_METHODOLOGY_ITEM = re.compile(r"\((\d{2,3})\)\*\*(.*?)\*\*")


def test_no_methodology_item_number_is_declared_twice():
    """A number that means two things is a number that means nothing.

    This has now gone wrong twice, both times the same way: an entry that
    declares two items puts only the FIRST at the head of its
    ``方法论沉淀`` paragraph, so a writer taking ``max`` over the heads reads
    the series as one short and restarts on top of the last entry's second
    item. Nothing said so — a duplicate reads exactly like a fresh number,
    and the collision only surfaces when someone cites one and gets both.

    Re-citations are not declarations and are excluded by what they already
    say: an entry pointing back at an earlier item marks it as recorded
    there. That marker is the difference, so this reads it rather than
    guessing from position.
    """
    text = " ".join((REPO / "CORE_STATUS.md").read_text(encoding="utf-8").split())
    declared: collections.Counter = collections.Counter()
    for m in _METHODOLOGY_ITEM.finditer(text):
        if "已记" in text[m.end():m.end() + 12]:
            continue
        declared[int(m.group(1))] += 1
    assert declared, "no methodology items found; this guard reads nothing"
    twice = sorted(n for n, count in declared.items() if count > 1)
    assert not twice, (
        f"these methodology item numbers are declared more than once: "
        f"{twice}. The series is what a citation resolves through, so take "
        f"the maximum over every declared number rather than over the ones "
        f"that happen to head a paragraph."
    )


def test_the_anchored_ordinals_actually_resolve():
    """Naming wall.md is a promise about wall.md.

    An anchored citation is admitted because the reader can go and look;
    if the entry is not there, the pointer is decoration and the
    reference is as dangling as the bare form it was allowed instead of.
    """
    wall = WALL.read_text(encoding="utf-8")
    known = {int(n) for n in re.findall(r"[Ii]ter[ -](\d+)", wall)}
    missing = {}
    for p in _sources():
        text = " ".join(p.read_text(encoding="utf-8").split())
        for ref in _ANCHORED.findall(text):
            for n in (int(m) for m in re.findall(r"[Ii]ter[ -](\d+)", ref)):
                if n not in known:
                    missing.setdefault(str(p.relative_to(REPO)), []).append(n)
    assert not missing, (
        f"these point at wall.md entries it does not carry: {missing}"
    )
