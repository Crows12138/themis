"""What the scheduler puts in a gap's own hole.

Beside :mod:`themis.runtime.iv_words` and not inside it, because the two
answer to different contracts. Those are FIELDS the envelope's schema
declares and a renderer looks up by name; these go into a HOLE of a
sentence :mod:`themis.gaps` owns, which is the shape that hid them —
the gap's sentence is written in both languages and whatever is dropped
into its hole was written in one, so the defect is invisible from either
end alone. Every reader of the gap sees a bilingual sentence; every
reader of the site sees a sensible string.

Both families also arrived at their hole through a joiner the site
chose: ``f" {note}"`` for the first and ``"；".join(...)`` for the
second. What goes between two sentences, and the space before a clause,
are facts about the language — an ASCII space in front of a Chinese
sentence and a Chinese semicolon between two English ones are the same
mistake twice.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Tried(language.Word, vocabulary="instrument_route_note"):
    """What became of the instrument the response polytope was offered.

    A gap saying "no interventional risk is obtainable" is true and
    unhelpful where an instrument existed and was tried: the reader
    cannot tell a graph with no instrument from one whose instrument the
    polytope could not use, and only the second is worth acting on.
    """

    THETA_GIVES_A_LEVEL_NO_MASS = ("theta_gives_a_level_no_mass", {
        "zh": "工具 {instrument} 本可以经响应型多面体到达这个量，但 theta 给它"
              "的某个取值零质量，P(X, Y | Z) 在那里没有定义，也就没有表可拟合。",
        "en": "the instrument {instrument} could have reached this quantity "
              "through the response polytope, but theta gives one of its "
              "levels no mass, so P(X, Y | Z) is undefined there and there "
              "is no table to fit.",
    })
    THE_PROGRAM_DID_NOT_SOLVE = ("the_program_did_not_solve", {
        "zh": "工具 {instrument} 经响应型多面体可以到达这个量，但线性规划没有"
              "跑通：{refusal}",
        "en": "the instrument {instrument} reaches this quantity through the "
              "response polytope, but the linear program did not solve: "
              "{refusal}",
    })
    THE_POLYTOPE_RULES_NOTHING_OUT = ("the_polytope_rules_nothing_out", {
        "zh": "工具 {instrument} 试过了：在响应型多面体上，所问的每个量都仍可以"
              "落在 [0, 1] 的任何位置，所以它在这里什么也排除不掉。",
        "en": "the instrument {instrument} was tried: on the response "
              "polytope every quantity asked about can still sit anywhere "
              "in [0, 1], so it rules nothing out here.",
    })


@unique
class Feasibility(language.Word, vocabulary="consistency_constraint"):
    """Which consistency inequality a supplied interventional risk broke.

    One member and two occasions, which is what the two sites were: the
    arms differ by which joint cells bound them, and those are notation.
    A second member would be the same sentence with X=1 spelled X=0.
    """

    A_RISK_SITS_OUTSIDE_ITS_BOUND = ("a_risk_sits_outside_its_bound", {
        "zh": "{quantity}={value} 必须落在 {expression} = "
              "[{lower}, {upper}] 之内",
        "en": "{quantity}={value} has to sit inside {expression} = "
              "[{lower}, {upper}]",
    })
