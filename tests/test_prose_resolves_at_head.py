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
    r"(?:/(?!\.+/)[\w.\-]+)+\.(?:py|md|json|ts|tsx|html))"
)


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
        for m in _PATH.finditer(text):
            if not (REPO / m.group(1)).exists():
                line = text[:m.start()].count("\n") + 1
                dead.setdefault(str(p.relative_to(REPO)), []).append(
                    f"{line}: {m.group(1)}")
    assert not dead, f"these name paths that do not exist: {dead}"


def test_a_moved_path_is_caught():
    """The counterexample, for the same reason the other one has one."""
    assert _PATH.findall("see themis/prompts/response_rendering.md for it")
    assert not _PATH.findall("see prompts/response_rendering.md")
    # An elided path is not a claim that a file is there.
    assert not _PATH.findall("under benchmarks/.../agent_prompt_v1.md")


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
