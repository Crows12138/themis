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
NDE_NIE_CONDITION: dict[str, str] = {
    "M1": "X 到 Y 还有调整集挡不住的后门路径",
    "M2": "X 到中介 M 还有调整集挡不住的后门路径",
    "M3": "中介 M 到 Y 还有后门路径 —— 控制了 X 和调整集也挡不住，"
          "而且图里没有任何变量能挡住它",
    "M4": "能挡住那条后门的变量是有的，但它是 X 的后代 —— 控制它会连要测的"
          "那条因果路径一起挡掉（典型是「中间混杂器」：既被 X 影响、"
          "又同时影响 M 和 Y 的变量）",
}

#: The back-door conditions for the controlled direct effect, as
#: ``extensions.mediation_decomposition.cde.failed_condition``. Two rather
#: than four because CDE fixes M by intervention instead of holding it at
#: its natural distribution, so the cross-world conditions do not arise.
CDE_CONDITION: dict[str, str] = {
    "C1": "把 M 固定住之后，X 到 Y 或 M 到 Y 仍有调整集挡不住的后门路径，"
          "而且图里没有任何变量能挡住它",
    "C2": "能挡住那条后门的变量是有的，但它是 X 或 M 的后代 —— 控制它会挡掉"
          "要测的那条路径",
}

#: What a ``framing_notes[].missing`` entry would have pinned down. The
#: members are the optional fields of a variable declaration, so the word
#: has to say what the question loses without it rather than translate the
#: field name — a reader who could act on "缺 time_window" could act on
#: "missing time_window" too.
FRAMING_FIELD: dict[str, str] = {
    "domain": "取值范围（这个变量能取哪些值）",
    "time_window": "时间窗（在多长的时间里测）",
    "measurement": "测量方式（用什么办法测出来的）",
    "threshold": "切点（连续量在哪里被切成两档）",
    "observability": "可观测性（谁、在什么条件下能看到它）",
    "unit": "单位",
    "direction": "方向（数值变大算变好还是变差）",
    "baseline": "基线（跟哪个参照状态比）",
    "state_vs_event": "状态还是事件（持续属性，还是一次性发生的事）",
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
AR_SET_KIND: dict[str, str] = {
    "bounded": "有界区间",
    "disconnected": "两条射线，中间一段被排除",
    "unbounded_below": "向下无界 —— 工具太弱，数据约束不住效应的下限"
                       "（旁边那个 bootstrap 区间会把这件事掩盖掉）",
    "unbounded_above": "向上无界 —— 工具太弱，数据约束不住效应的上限"
                       "（旁边那个 bootstrap 区间会把这件事掩盖掉）",
    "whole_line": "整条实轴 —— 数据对这个效应没有任何约束力",
    "empty": "空集 —— 没有哪个取值能同时满足所有工具的矩条件，"
             "数据在否定这组工具本身",
    "union": "多段（三段以上）",
}

#: The measurement scale a variable declares, and the one its column turned
#: out to have — ``extensions.type_reconciliation.checks[].declared_scale``
#: and ``.observed_scale``. One mapping for both, because a mismatch is read
#: by putting the two side by side and they have to be in the same words.
SCALE: dict[str, str] = {
    "binary": "二值",
    "discrete": "离散",
    "continuous": "连续",
}

#: Which margin a misclassification correction inverted, as
#: ``numeric_estimate.measurement_correction.side``. The word says which
#: variable was mismeasured rather than translating the token, because that
#: is the fact a reader checks against their own study: a correction applied
#: to the wrong margin is not a smaller correction, it is a different one.
MEASUREMENT_SIDE: dict[str, str] = {
    "outcome": "结局被误分类（暴露当作测准了）",
    "exposure": "暴露被误分类（结局当作测准了）",
    "combined": "暴露与结局都被误分类，两个通道各自求逆",
}

#: Which VanderWeele formula the ratio-scale four-way split used, as
#: ``numeric_estimate.four_way_ratio.mediator_scale``. The members are the
#: same two tokens :data:`SCALE` carries, and the vocabularies are not the
#: same: there the word describes a column, here it names which closed form
#: was evaluated, and a reader checking the split against the paper needs
#: the section number rather than the adjective.
FOUR_WAY_MEDIATOR_SCALE: dict[str, str] = {
    "binary": "中介是二值 —— 走 eAppendix §3.4 的闭式",
    "continuous": "中介是连续 —— 走 eAppendix §3.3 的闭式，"
                  "多出一个中介残差方差项",
}


def _describe(table: dict[str, str], value) -> str:
    """The reader's word, or the token itself.

    An unlisted value renders as its own identifier rather than as silence
    or a guess, the way :func:`themis.ledger.layer_zh` does: a name the
    reader has to look up still beats the sentence omitting it, and it beats
    confidently naming the wrong thing. Envelopes are read from other builds
    too, and a build that has never heard of a value must not invent one.
    """
    word = table.get(str(value))
    return word if word is not None else f"`{value}`"


def nde_nie_condition_zh(value) -> str:
    """Which Pearl condition blocks the natural decomposition."""
    return _describe(NDE_NIE_CONDITION, value)


def cde_condition_zh(value) -> str:
    """Which back-door condition blocks the controlled direct effect."""
    return _describe(CDE_CONDITION, value)


def framing_field_zh(value) -> str:
    """What one unset declaration field would have pinned down."""
    return _describe(FRAMING_FIELD, value)


def framing_fields_zh(missing) -> str:
    """The list of what a predicate never said, joined for a sentence."""
    return "、".join(framing_field_zh(m) for m in missing)


def scale_zh(value) -> str:
    """A declared or observed measurement scale."""
    return _describe(SCALE, value)


def ar_set_kind_zh(value) -> str:
    """What shape a weak-instrument-robust confidence set came out in."""
    return _describe(AR_SET_KIND, value)


def measurement_side_zh(value) -> str:
    """Which margin a misclassification correction inverted."""
    return _describe(MEASUREMENT_SIDE, value)


def four_way_mediator_scale_zh(value) -> str:
    """Which closed form the ratio-scale four-way split was evaluated at."""
    return _describe(FOUR_WAY_MEDIATOR_SCALE, value)
