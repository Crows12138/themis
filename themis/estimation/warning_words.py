"""What the estimation layer tells a reader without refusing.

The channel beside :mod:`themis.estimation.refusal_words`. Those leave as
exceptions because there is no result to carry them; these ride out on
``estimation_context.data_contract_warnings``, beside an answer that was
produced anyway. A caller sees them and can still read the number.

Until this table existed the field was typed ``array of string``, and a
``string`` field makes every branch the author of its own sentence.
Nothing above a branch knows who is reading, so what each one wrote was
whichever language its author was thinking in — five in Chinese and, in
the same ``if``/``elif`` chain as four of those, one in English. That
last one is the shape of the defect rather than an oversight in it: no
rule was broken, because no rule had been stated.

**Two vocabularies, one field, and that is a finding of its own.** Only
the first of these is about the data contract; the next five are about
which query a dose-response request attached itself to, which is a fact
about the PROGRAM. They share a field because it was the only list of
strings available at the time, and carrying the vocabulary name beside
each token is what makes the split visible to a reader — and to whoever
eventually gives the second family a channel of its own.

The third has a channel of its own already and belongs here for the
subject rather than the field: ``numeric_estimate.four_way_unavailable``
is what this layer says when it computed a decomposition and then judged
it not to hold. A reader shown no split cannot tell "not applicable here"
from "nobody tried", which is the same thing a warning is for one field
over — and the positive case is a structured BLOCK while the negative was
one string, which is how a negative comes to be prose.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Contract(language.Word, vocabulary="data_contract_warning"):
    """What is suspicious about the data, where estimation went ahead.

    The refusals live one door over; the line between the two channels is
    whether a number came out. Below the advisory size one does, and it
    is worth less than a reader would assume from seeing it — which is
    exactly the thing a warning is for.
    """

    SAMPLE_IS_BELOW_THE_ADVISORY = ("sample_is_below_the_advisory", {
        "zh": "样本量 {rows} 低于建议的 {advisory}——估计还是算出来了，"
              "但置信区间会很宽，宽到窄的那一端和宽的那一端往往指向"
              "不同的决定",
        "en": "{rows} rows is below the advisory {advisory} — an estimate "
              "came out, but its confidence interval will be wide enough "
              "that its two ends often point at different decisions",
    })


@unique
class FourWay(language.Word, vocabulary="four_way_unavailable"):
    """Why the difference-scale four-way split was withheld.

    Withheld rather than skipped: the components were computable and do
    not sum to the total effect for data of this shape, so reporting them
    would be reporting four numbers that do not add up. Which of the two
    it was is exactly what a reader needs, and the field carrying it was
    a ``string`` beside a structured block — the block says what the split
    IS and the string had to say what it is not.
    """

    THE_MEDIATOR_IS_CONTINUOUS_UNDER_A_NONLINEAR_OUTCOME = (
        "the_mediator_is_continuous_under_a_nonlinear_outcome", {
            "zh": "差值尺度的四分解已跳过：非线性（logit）结局下的连续中介，"
                  "会把 m∈{{0,1}} 的代入外推到中介取值范围之外。调度改为挂上"
                  "比值尺度（超额相对风险）的 four_way_ratio 块——VanderWeele "
                  "2014 eAppendix §3.3，那才是「连续中介 + 二值结局」该用的工具",
            "en": "the difference-scale four-way split was withheld: with a "
                  "continuous mediator under a nonlinear (logit) outcome, "
                  "plugging in m∈{{0,1}} extrapolates off the mediator's "
                  "support. Dispatch attaches the ratio-scale (excess "
                  "relative risk) four_way_ratio block instead — VanderWeele "
                  "2014 eAppendix §3.3, which is the tool for a continuous "
                  "mediator with a binary outcome",
        })


@unique
class DoseResponse(language.Word, vocabulary="dose_response_routing"):
    """Where a dose-response request went, when it did not go where it said.

    A ``dose_response_query`` names the curve to draw and not the query
    to draw it for, so the layer picks one — and the first five members
    are cases where the pick was not obvious. Four of those end in the
    estimator being skipped, which is the fact a reader has to be handed:
    a curve that is absent because nothing could be routed reads exactly
    like a curve nobody asked for.

    The sixth is the request arriving somewhere real and degenerate. It
    fills two slots on the envelope with ONE statement — the fallback's
    ``reason`` and the warning beside it — because the browser's own
    comment already says those two say the same thing and prints only
    one. Said once, that is a fact the two fields carry; said twice in
    prose, it was a claim in a comment.
    """

    NO_EFFECT_QUERY_TO_ATTACH_TO = ("no_effect_query_to_attach_to", {
        "zh": "程序里有 dose_response_query，却没有任何 effect 查询可以挂靠；"
              "剂量-反应估计量已跳过，缺的东西在数据缺口报告里",
        "en": "the program has a dose_response_query and no effect query to "
              "attach it to; the dose-response estimator was skipped, and "
              "the data-gap report says what is missing",
    })
    EVERY_EFFECT_QUERY_IS_A_MEDIATION = ("every_effect_query_is_a_mediation", {
        "zh": "程序里有 dose_response_query，但每一个 effect 查询都带中介；"
              "剂量-反应曲线要的是一个不带中介的 effect 查询",
        "en": "the program has a dose_response_query and every effect query "
              "names a mediator; a dose-response curve needs an effect "
              "query without one",
    })
    THE_QUERY_ID_MATCHES_NOTHING = ("the_query_id_matches_nothing", {
        "zh": "dose_response_query 的 query_id {named} 对不上任何一个 effect "
              "查询；估计量已跳过，而不是改挂到别的查询上",
        "en": "the dose_response_query's query_id {named} matches no effect "
              "query; the estimator was skipped rather than attached to a "
              "different one",
    })
    THE_QUERY_ID_NAMES_A_MEDIATION = ("the_query_id_names_a_mediation", {
        "zh": "dose_response_query 的 query_id {named} 指向一个带中介的 effect "
              "查询；剂量-反应估计量已跳过",
        "en": "the dose_response_query's query_id {named} points at an "
              "effect query that names a mediator; the dose-response "
              "estimator was skipped",
    })
    NO_QUERY_ID_SO_THE_FIRST_ELIGIBLE_WON = (
        "no_query_id_so_the_first_eligible_won", {
            "zh": "dose_response_query 没有给 query_id，于是排在前面的中介查询 "
                  "{passed_over} 被跳过，曲线画在了 {chosen} 上",
            "en": "the dose_response_query names no query_id, so the "
                  "mediation query {passed_over} that comes before it was "
                  "passed over and the curve was drawn for {chosen}",
        })
    THE_TREATMENT_IS_BINARY = ("the_treatment_is_binary", {
        "zh": "处理 {treatment} 是二值的，剂量-反应曲线在这里退化成两点之间的"
              "一个对比——所以答这个问题的是二值路径",
        "en": "the treatment {treatment} is binary, so a dose-response "
              "curve here degenerates into a contrast between two points — "
              "the binary path is what answered",
    })
