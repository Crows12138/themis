"""A Chinese sentence is punctuated as Chinese, on every surface.

This is a typographic rule with a structural job. The report and the
browser say many of the same sentences, and neither can import the other:
the browser is TypeScript, the kernel is Python, so the second copy is
written by hand and the suite compares the two as text. Two gates do that
(``test_risk_provenance``, ``test_web_vocabularies``), and both of them
used to run their two sides through a full-width-to-half-width
substitution first.

A substitution in that position is not a helper. It is a list of ways the
two copies are allowed to disagree without anyone noticing — and its
contents had been inferred from the ways they already disagreed, never
decided. So it behaved the way an inferred list behaves: it was shorter
than the thing it described, it got copied when a second gate met the same
difference, and the two copies drifted, which meant a divergence one gate
could catch the other read as agreement. It also carried a belief about
the browser — that it punctuates in half width throughout, as its own
convention. Measured, its Chinese strings ran 42 full width to 42 half;
the whole frontend ran 59 to 58; the kernel ran 361 to 5. The belief came
from the two tables those gates happened to compare, both of which
happened to be half width.

So the allowance is gone and this states the spelling instead: a Chinese
sentence is punctuated as Chinese. With one spelling there is nothing to
normalize, the two gates compare byte for byte, and both got stricter by
losing code.

SCOPE is the two trees the repository speaks in: the package that faces a
reader and the suite that holds it to what it says. ``docs/`` and
``CORE_STATUS.md`` are outside, and the reason is not that they matter
less. They are records — an evaluation case fed in, an LLM run recorded
verbatim, a trial written up, a decision already logged — and a record is
quoted rather than re-punctuated. It shows in what they contain: every
half-width separator between Chinese characters under ``docs/`` sits
inside a list or set literal, where the mark is the notation's own
separator and this rule would be wrong about it. Inside the scope there
is no such case, which is what lets the rule hold with no exception of
any kind. An exception clause — unless it is inside brackets — would be a
hole wide enough to drive the original problem back through.

Parentheses are governed by the byte equality rather than from here. They
differ in width between the two copies of a sentence as well, but only
where two copies exist, and there the equality already says the whole
sentence has to match. A repository-wide rule about them would have to
decide what a parenthesis wraps, which is as often a formula as a clause.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The package that speaks to a reader, and the suite that pins it.
SURFACES = (REPO / "themis", REPO / "tests")

#: Trees the repository does not write. Named rather than filtered by
#: extension, because what disqualifies them is authorship, not language.
NOT_OURS = frozenset({"node_modules", "dist", "__pycache__", ".venv"})

HAN = "一-鿿"

#: A half-width mark that is separating Chinese.
#:
#: A comma or semicolon counts when a Chinese character follows it
#: immediately, whatever precedes — a Chinese clause after the mark makes
#: the sentence Chinese even where the clause before it ended in a bracket,
#: a formula or a closing tag, and requiring Chinese on the left as well
#: silently spares exactly those. What decides it is the space, and that is
#: measured rather than asserted: where the mark is followed by a space and
#: then Chinese, the surrounding sentence is English listing Chinese terms,
#: and there the half-width mark is the correct one.
#:
#: A colon is not the same mark. It introduces a value about as often as it
#: separates a clause, and what it introduces from is as often an
#: identifier or a section number as a word, so it counts only with Chinese
#: standing on both sides.
#:
#: Lookarounds rather than a consuming match. A consuming scan swallows the
#: character on each side, so where a clause carries two separators with a
#: single character between them it reports one and steps over the other —
#: and a fix driven by that count leaves the other behind.
#:
#: Three marks, and the others are absent rather than excused: a half-width
#: full stop, exclamation or question mark between two Chinese characters
#: occurs nowhere in the repository, in any tree, so naming them would be
#: legislating about nothing.
SEPARATOR = re.compile(f"[,;](?=[{HAN}])|(?<=[{HAN}]):(?=[{HAN}])")

#: The same marks written as Chinese, for the vacuity floor below.
_WRITTEN_AS_CHINESE = re.compile(f"[，；](?=[{HAN}])|(?<=[{HAN}])：(?=[{HAN}])")


def _carried() -> list[tuple[pathlib.Path, str]]:
    """Every text file under the surfaces, with its contents."""
    out = []
    for root in SURFACES:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or NOT_OURS & set(path.parts):
                continue
            try:
                out.append((path, path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    return out


def _violations(text: str) -> list[int]:
    return [m.start() for m in SEPARATOR.finditer(text)]


def test_every_chinese_sentence_is_punctuated_as_chinese():
    """No half-width mark separating Chinese, anywhere the repository
    speaks. ``SEPARATOR`` says which marks and on what evidence.

    The message names the line and shows the clause, because the fix is to
    read the sentence and widen one character, and a count would send the
    reader looking for it.
    """
    found = []
    for path, text in _carried():
        for at in _violations(text):
            line = text[:at].count("\n") + 1
            clause = text[max(0, at - 26):at + 26].replace("\n", " ")
            found.append(
                f"{path.relative_to(REPO).as_posix()}:{line}  …{clause}…")
    assert not found, (
        f"{len(found)} Chinese sentence(s) punctuated in half width:\n  "
        + "\n  ".join(found)
    )


def test_the_sweep_reads_the_repository():
    """A walk that stops finding files passes the check above in silence.

    Both floors are far under what the repository carries and neither is a
    target: the point is that a scan reading nothing, or reading files with
    no Chinese in them, fails here instead of reporting a clean sweep.
    """
    carried = _carried()
    assert len(carried) > 300, f"the walk found {len(carried)} files"
    written = sum(len(_WRITTEN_AS_CHINESE.findall(t)) for _, t in carried)
    assert written > 400, f"the walk found {written} Chinese separators"


def test_a_half_width_separator_before_chinese_is_caught():
    """The rule's teeth, built rather than written.

    Assembled from the marks so this file does not have to contain the
    thing it forbids — a gate whose own source violates it would either
    fail itself or need an exemption, and an exemption is what this whole
    item removed.

    The second case is the one the narrower reading loses: the clause
    before the mark ended in a bracket, so a rule wanting Chinese on both
    sides reads a Chinese sentence as none of its business.
    """
    for mark in ",;:":
        assert _violations(f"前半句{mark}后半句"), mark
    for mark in ",;":
        assert _violations(f"退化到 [0,1]{mark}诚实但无从分辨"), mark


def test_a_separator_the_rule_does_not_claim():
    """Where a half-width mark is the correct one.

    An English sentence lists Chinese terms with English punctuation, and
    the space after the mark is what says so. A colon after an identifier
    or a section number introduces rather than separates, and the thing it
    introduces from is written in the other language. A rule that widened
    those would be a rule about the wrong subject, and would be argued
    with until someone switched it off.
    """
    for text in ("estimand:因果效应", "见 §4:调整集", "因果效应: 0.31",
                 "P(X,Y|Z) 的分布", "取值 1,2,3 之间",
                 "supernatural premises: 星座, 命理, 风水",
                 "scales: 收缩压, 体重, 年龄"):
        assert not _violations(text), text
