"""A prompt instructs; it does not demonstrate.

``nl_to_kernel_ast.md`` made this call once already and wrote down why.
The three worked NL→AST pairs it used to inject all shared one graph
shape, and "as concrete demonstrations they outweighed the prose, pulling
nearly every answer toward that same triangle". What a demonstration
teaches is everything about itself, including the parts nobody meant to
teach.

``response_rendering.md`` had the same shape against a different axis.
251 of its lines were finished replies quoted under the rules they
illustrated, and every one of them was in Chinese — so "answer in the
reader's language" was not a request that file could carry, whatever its
title said. Retitling would not have helped: an instruction contradicted
by the evidence underneath it loses.

So the rule here is structural rather than linguistic, because the defect
was structural. A blockquote in a prompt may be the file's opening
statement of what it is for — the ones that have such a block put it
above the first section, addressed to whoever opens the file. It may not
sit under a rule as an illustration of that rule, because that is the
shape a reader copies wholesale.

**Where this stops.** A demonstration written as running prose, or inside
a fenced block among the schemas and formulas, passes here untouched. The
denominator is one syntax and not the whole idea — and a gate read as
covering more than it does is worth less than no gate, because the belief
is what stops anyone looking.
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
PROMPTS = REPO / "themis" / "prompts"
PROMPT_FILES = sorted(PROMPTS.glob("*.md"))


def _illustrations(text: str) -> list[tuple[int, str]]:
    """Blockquote lines sitting below a section heading.

    Fenced blocks are skipped: a ``>`` inside one belongs to whatever the
    fence holds — a diff, a transcript, an email — and is not a quote of
    the document's own making.
    """
    found: list[tuple[int, str]] = []
    fenced = False
    under_a_section = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("##"):
            under_a_section = True
        elif under_a_section and line.lstrip().startswith(">"):
            found.append((number, line.strip()[:100]))
    return found


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.name)
def test_a_prompt_quotes_nothing_under_a_rule(path):
    found = _illustrations(path.read_text(encoding="utf-8"))
    assert not found, (
        f"{path.name} illustrates a rule with a quoted block at "
        f"{[n for n, _ in found]}. State what the block demonstrates; a "
        f"reader copies the demonstration, not the rule above it — "
        f"first: {found[0][1]}"
    )


def test_the_prompts_are_a_real_denominator():
    """A parametrised test over an empty glob passes by finding nothing."""
    assert len(PROMPT_FILES) >= 7, [p.name for p in PROMPT_FILES]


def test_an_opening_purpose_block_is_still_allowed():
    """The floor from the other side.

    Without this the rule could tighten to "no blockquote anywhere" and
    nothing would notice, because the prompts would still pass — they
    would just have lost the one use of a quote this permits.
    """
    opens_with_one = [
        path.name for path in PROMPT_FILES
        if any(line.lstrip().startswith(">")
               for line in path.read_text(encoding="utf-8").splitlines())
    ]
    assert opens_with_one, (
        "no prompt states its purpose in a quote block — the rule now "
        "permits nothing, which is not what it says"
    )


def test_an_illustration_under_a_rule_is_refused():
    """The counterexample, built by spoiling a real file.

    A hand-written pair of strings would exercise the regex. Putting the
    quote under a real heading of the real document exercises the walk
    that has to notice it.
    """
    text = (PROMPTS / "response_rendering.md").read_text(encoding="utf-8")
    assert not _illustrations(text)

    heading = "## Reading the JSON"
    assert heading in text
    spoiled = text.replace(
        heading, f"{heading}\n\n> A finished reply, quoted under a rule.\n", 1)
    assert _illustrations(spoiled)


def test_a_quote_inside_a_fence_is_not_an_illustration():
    """The other side of the same walk: a prompt that documents a format
    whose own syntax uses ``>`` has not thereby illustrated anything."""
    fenced = "# T\n\n## S\n\n```\n> quoted inside a fence\n```\n"
    assert not _illustrations(fenced)
