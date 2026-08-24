# -*- coding: utf-8 -*-
"""What a reader is led with, assembled the way a reader surface does it.

There is no field on the envelope holding these (#395). A ⚠ line has no
content of its own — it restates a gap — and a restatement is a rendering,
which is made where the reader is known and not while the kernel runs. So
every surface builds its own from the gaps, and a test is one more surface.

This exists so that a test asserting on what the reader is told does not
have to know how the join is spelled. What it is NOT is a second producer:
the sentences are the gaps', the marker is this surface's, and which gaps
are led with is :data:`themis.types.QUALIFIES_THE_ANSWER`'s.
"""
from __future__ import annotations

from themis import gaps as _gaps
from themis import language
from themis.types import QUALIFIES_THE_ANSWER

#: This surface's marker. Each reader surface picks its own; the browser
#: has an icon where this has a glyph.
MARKER = "⚠"


def lines(result: dict, lang: language.Lang | str = language.DEFAULT
          ) -> list[str]:
    """The caveats on this result, in the order its report states them."""
    report = result.get("data_gap_report") or {}
    caveats = {k.value for k in QUALIFIES_THE_ANSWER}
    return [
        f"{MARKER} {_gaps.described(gap, lang)}"
        for gap in (report.get("gaps") or ())
        if gap.get("kind") in caveats
    ]


def text(result: dict, lang: language.Lang | str = language.DEFAULT) -> str:
    """The same, joined — the shape the old envelope field had."""
    return "\n".join(lines(result, lang))
