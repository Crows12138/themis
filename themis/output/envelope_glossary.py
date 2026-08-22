"""The reader's word for envelope values whose vocabulary owns nothing else.

Three glossaries live in this package. :mod:`derivation_glossary` says what
one derivation rule did; :mod:`assumption_glossary` says what one assumption
id claims. This one holds the vocabularies that reach a reader and have no
home of their own.

**Why a glossary and not a registry.** :class:`themis.ledger.Layer` carries
its ``zh`` on the member because a ledger line's layer is a fact its producer
is held to — the same object also states the severity that grades it and the
producers allowed to write it, so the word had to travel with the rest. The
vocabularies below hang no such fact off a member. A reader needs to know
what ``M3`` names; nothing else in the kernel needs to know anything about
``M3`` beyond the string it emits. Where the word is the only thing anyone
needs, a mapping is the whole object, and a registry would be a class built
to hold one attribute.

**What these have in common is how they were found.** Each is declared as a
JSON schema ``enum`` and by nothing else — no Python enum states them, so the
completeness gate that walked ``enum.Enum`` subclasses never asked who reads
them, and each reached a Chinese sentence as its own identifier.
``tests/test_vocabulary_reach.py`` now enumerates the schemas as well and
points at the mappings here; the equality it checks is against the schema, so
a value added there without a word fails before a reader sees it.
"""
from __future__ import annotations

from .. import language

#: Pearl 2001 Theorem 2 conditions for natural direct / indirect effects,
#: as ``extensions.mediation_decomposition.nde_nie.failed_condition`` (and
#: its ``$ref``-shared twin under ``mediation_joint_decomposition``).
#:
#: Each says which path is still open, because that is what the reader can
#: act on: the condition number identifies the theorem line, and the
#: sentence identifies the graph.
#:
#: A separation condition and a membership condition ask the reader for
#: different things — one for a variable they have not measured, one for an
#: argument about a variable already in their graph — so the sentences have
#: to keep them apart. The intermediate confounder belongs to M4: the
#: variable that would close the back-door is right there and is refused
#: for descending from the treatment.
NDE_NIE_CONDITION: dict[str, language.Words] = {
    "M1": {"zh": "X 到 Y 还有调整集挡不住的后门路径",
           "en": "there is still a back-door path from X to Y that the "
                 "adjustment set does not block"},
    "M2": {"zh": "X 到中介 M 还有调整集挡不住的后门路径",
           "en": "there is still a back-door path from X to the mediator M "
                 "that the adjustment set does not block"},
    "M3": {"zh": "中介 M 到 Y 还有后门路径 —— 控制了 X 和调整集也挡不住，"
          "而且图里没有任何变量能挡住它",
           "en": "there is a back-door path from the mediator M to Y — "
                 "controlling for X and the adjustment set does not block it, "
                 "and no variable in the graph can"},
    "M4": {"zh": "能挡住那条后门的变量是有的，但它是 X 的后代 —— 控制它会连要测的"
          "那条因果路径一起挡掉（典型是「中间混杂器」：既被 X 影响、"
          "又同时影响 M 和 Y 的变量）",
           "en": "a variable that would block that back-door does exist, but "
                 "it is a descendant of X — controlling for it would block the "
                 "causal path being measured along with it (typically an "
                 "intermediate confounder: a variable X affects that in turn "
                 "affects both M and Y)"},
}

#: The back-door conditions for the controlled direct effect, as
#: ``extensions.mediation_decomposition.cde.failed_condition``. Two rather
#: than four because CDE fixes M by intervention instead of holding it at
#: its natural distribution, so the cross-world conditions do not arise.
CDE_CONDITION: dict[str, language.Words] = {
    "C1": {"zh": "把 M 固定住之后，X 到 Y 或 M 到 Y 仍有调整集挡不住的后门路径，"
          "而且图里没有任何变量能挡住它",
           "en": "with M held fixed there is still a back-door path from X to "
                 "Y or from M to Y that the adjustment set does not block, and "
                 "no variable in the graph can block it"},
    "C2": {"zh": "能挡住那条后门的变量是有的，但它是 X 或 M 的后代 —— 控制它会挡掉"
          "要测的那条路径",
           "en": "a variable that would block that back-door does exist, but "
                 "it is a descendant of X or of M — controlling for it would "
                 "block the very path being measured"},
}

#: What a ``framing_notes[].missing`` entry would have pinned down. The
#: members are the optional fields of a variable declaration, so the word
#: has to say what the question loses without it rather than translate the
#: field name — a reader who could act on "缺 time_window" could act on
#: "missing time_window" too.
FRAMING_FIELD: dict[str, language.Words] = {
    "domain": {"zh": "取值范围（这个变量能取哪些值）",
               "en": "the range of values (which values this variable can "
                     "take)"},
    "time_window": {"zh": "时间窗（在多长的时间里测）",
                    "en": "the time window (over how long it is measured)"},
    "measurement": {"zh": "测量方式（用什么办法测出来的）",
                    "en": "the measurement (how it was actually measured)"},
    "threshold": {"zh": "切点（连续量在哪里被切成两档）",
                  "en": "the cut point (where a continuous quantity is split "
                        "into two)"},
    "observability": {"zh": "可观测性（谁、在什么条件下能看到它）",
                      "en": "observability (who can see it, and under what "
                            "conditions)"},
    "unit": {"zh": "单位", "en": "the unit"},
    "direction": {"zh": "方向（数值变大算变好还是变差）",
                  "en": "the direction (whether a larger number is better or "
                        "worse)"},
    "baseline": {"zh": "基线（跟哪个参照状态比）",
                 "en": "the baseline (what state it is being compared against)"},
    "state_vs_event": {"zh": "状态还是事件（持续属性，还是一次性发生的事）",
                       "en": "state or event (a standing property, or "
                             "something that happens once)"},
}

#: The shape an Anderson-Rubin confidence set came out in, as
#: ``numeric_estimate.{,stratified_,robust_}anderson_rubin_confidence_set.kind``.
#: One table for all three, because the shape means the same thing whichever
#: moment was inverted — and the two that report ``union`` and the four that
#: cannot are the same vocabulary either way.
#:
#: The word carries the consequence rather than only the geometry. An
#: unbounded AR set is not a wide interval; it is the statement that the
#: instrument is too weak for the data to bound the effect at all, and the
#: bootstrap interval printed beside it will look finite and reassuring. A
#: reader told only "向上无界" has been told the shape and not the finding.
AR_SET_KIND: dict[str, language.Words] = {
    "bounded": {"zh": "有界区间", "en": "a bounded interval"},
    "disconnected": {"zh": "两条射线，中间一段被排除",
                     "en": "two rays with a stretch between them ruled out"},
    "unbounded_below": {"zh": "向下无界 —— 工具太弱，数据约束不住效应的下限"
                       "（旁边那个 bootstrap 区间会把这件事掩盖掉）",
                        "en": "unbounded below — the instrument is too weak "
                              "for the data to constrain how small the effect "
                              "could be (the bootstrap interval beside it "
                              "hides exactly this)"},
    "unbounded_above": {"zh": "向上无界 —— 工具太弱，数据约束不住效应的上限"
                       "（旁边那个 bootstrap 区间会把这件事掩盖掉）",
                        "en": "unbounded above — the instrument is too weak "
                              "for the data to constrain how large the effect "
                              "could be (the bootstrap interval beside it "
                              "hides exactly this)"},
    "whole_line": {"zh": "整条实轴 —— 数据对这个效应没有任何约束力",
                   "en": "the whole real line — the data constrain this effect "
                         "not at all"},
    "empty": {"zh": "空集 —— 没有哪个取值能同时满足所有工具的矩条件，"
             "数据在否定这组工具本身",
              "en": "empty — no value satisfies every instrument's moment "
                    "condition at once, so the data are rejecting this set of "
                    "instruments"},
    "union": {"zh": "多段（三段以上）", "en": "several pieces (three or more)"},
}

#: The measurement scale a variable declares, and the one its column turned
#: out to have — ``extensions.type_reconciliation.checks[].declared_scale``
#: and ``.observed_scale``. One mapping for both, because a mismatch is read
#: by putting the two side by side and they have to be in the same words.
SCALE: dict[str, language.Words] = {
    "binary": {"zh": "二值", "en": "binary"},
    "discrete": {"zh": "离散", "en": "discrete"},
    "continuous": {"zh": "连续", "en": "continuous"},
    # Said of a declaration and never of a column: the word names
    # what the levels are NOT (ordered), and a column cannot show
    # the absence of an order.
    "nominal": {"zh": "名义（档之间无大小）",
                "en": "nominal (levels with no order)"},
}

#: Which margin a misclassification correction inverted, as
#: ``numeric_estimate.measurement_correction.side``. The word says which
#: variable was mismeasured rather than translating the token, because that
#: is the fact a reader checks against their own study: a correction applied
#: to the wrong margin is not a smaller correction, it is a different one.
MEASUREMENT_SIDE: dict[str, language.Words] = {
    "outcome": {"zh": "结局被误分类（暴露当作测准了）",
                "en": "the outcome is misclassified (the exposure is taken as "
                      "measured correctly)"},
    "exposure": {"zh": "暴露被误分类（结局当作测准了）",
                 "en": "the exposure is misclassified (the outcome is taken as "
                       "measured correctly)"},
    "combined": {"zh": "暴露与结局都被误分类，两个通道各自求逆",
                 "en": "both the exposure and the outcome are misclassified, "
                       "and each channel is inverted on its own"},
}

#: Which VanderWeele formula the ratio-scale four-way split used, as
#: ``numeric_estimate.four_way_ratio.mediator_scale``. The members are the
#: same two tokens :data:`SCALE` carries, and the vocabularies are not the
#: same: there the word describes a column, here it names which closed form
#: was evaluated, and a reader checking the split against the paper needs
#: the section number rather than the adjective.
FOUR_WAY_MEDIATOR_SCALE: dict[str, language.Words] = {
    "binary": {"zh": "中介是二值 —— 走 eAppendix §3.4 的闭式",
               "en": "the mediator is binary — the eAppendix §3.4 closed form"},
    "continuous": {"zh": "中介是连续 —— 走 eAppendix §3.3 的闭式，"
                  "多出一个中介残差方差项",
                   "en": "the mediator is continuous — the eAppendix §3.3 "
                         "closed form, which carries one extra "
                         "mediator-residual variance term"},
}


#: How much unmeasured confounding a result could absorb, as
#: ``numeric_estimate.sensitivity_analysis.interpretation_band``.
#:
#: The word carries the consequence rather than the tier: "substantial" on
#: its own is a rank in a scale the reader was never shown, and what they
#: can act on is what it would take to explain the result away.
EVALUE_BAND: dict[str, language.Words] = {
    "fragile": {"zh": "很脆弱——很小的未测混杂就足以解释掉这个结果",
                "en": "fragile — a small amount of unmeasured confounding is "
                      "already enough to explain this result away"},
    "moderate": {"zh": "中等强度——一个强度一般的混杂就足以解释掉这个结果",
                 "en": "moderate — a confounder of ordinary strength is "
                       "enough to explain this result away"},
    "substantial": {"zh": "比较稳健——混杂要相当大才解释得掉",
                    "en": "substantial — the confounding would have to be "
                          "sizeable to explain this result away"},
    "very_robust": {"zh": "非常稳健——需要一个强到不合常理的混杂才解释得掉",
                    "en": "very robust — it would take a confounder strong "
                          "enough to be implausible"},
}

#: Which of the two E-values the band above was read off, as
#: ``numeric_estimate.sensitivity_analysis.band_basis``.
#:
#: Printed beside the band rather than kept for an audit trail. The two
#: E-values answer different questions, and a reader told only the verdict
#: has to know which question was asked before they can tell whether it was
#: the one they meant.
EVALUE_BAND_BASIS: dict[str, language.Words] = {
    "ci_bound": {"zh": "按置信区间靠近零的那一端判的——这一端问的是"
                       "「结论还在不在」",
                 "en": "read off the end of the interval nearer the null — "
                       "that end asks whether the finding survives"},
    "point": {"zh": "按点估计判的——这次没有可用的区间端点",
              "en": "read off the point estimate — no interval bound was "
                    "available this time"},
}


def nde_nie_condition_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """Which Pearl condition blocks the natural decomposition."""
    return language.gloss(NDE_NIE_CONDITION, value, lang)


def cde_condition_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """Which back-door condition blocks the controlled direct effect."""
    return language.gloss(CDE_CONDITION, value, lang)


def framing_field_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """What one unset declaration field would have pinned down."""
    return language.gloss(FRAMING_FIELD, value, lang)


def framing_fields_word(
        missing, lang: language.Lang | str = language.DEFAULT) -> str:
    """The list of what a predicate never said, joined for a sentence."""
    return "、".join(framing_field_word(m, lang) for m in missing)


def scale_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """A declared or observed measurement scale."""
    return language.gloss(SCALE, value, lang)


def ar_set_kind_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """What shape a weak-instrument-robust confidence set came out in."""
    return language.gloss(AR_SET_KIND, value, lang)


def evalue_band_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """How much unmeasured confounding this result could absorb."""
    return language.gloss(EVALUE_BAND, value, lang)


def evalue_band_basis_word(
        value, lang: language.Lang | str = language.DEFAULT) -> str:
    """Which of the two E-values that reading was taken from."""
    return language.gloss(EVALUE_BAND_BASIS, value, lang)


def measurement_side_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """Which margin a misclassification correction inverted."""
    return language.gloss(MEASUREMENT_SIDE, value, lang)


def four_way_mediator_scale_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """Which closed form the ratio-scale four-way split was evaluated at."""
    return language.gloss(FOUR_WAY_MEDIATOR_SCALE, value, lang)
