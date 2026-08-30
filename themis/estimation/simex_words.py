"""The reader's word for each token a SIMEX estimate puts on the envelope.

Three closed vocabularies, and none of them is spelled twice. The report
renders from these tables and the browser's are generated from them, which
is the only arrangement under which the two surfaces cannot drift: a word
written once in each place is two words that happen to agree today.

They live beside the estimator rather than in the rendering layer because
that is where their members are declared — :data:`Extrapolant` and
:data:`OutcomeModel` are three tokens and two, and a table kept anywhere
else would be a second record of which tokens exist.
"""
from __future__ import annotations

from .. import language

#: Which model the corrected coefficient lives in — spelled as the quantity
#: rather than as the model's name, because the name is only useful to a
#: reader who already knows what it implies. This is the sentence the whole
#: block hangs on: the same two columns support a linear-probability slope
#: and a log-odds ratio, so which one is on the page is not a detail of how
#: the number was computed but a statement of what it is.
OUTCOME_MODELS: dict[str, language.Words] = {
    "logistic": {"zh": "logistic 结局模型里暴露的系数——真实暴露每增加一个"
                       "单位的条件对数优势比，不是风险差",
                 "en": "the exposure's coefficient in a logistic outcome "
                       "model — a conditional log-odds ratio per unit of "
                       "the true exposure, not a risk difference"},
    "linear": {"zh": "线性结局模型里暴露的系数——真实暴露每增加一个单位的"
                     "条件斜率",
               "en": "the exposure's coefficient in a linear outcome "
                     "model — a conditional slope per unit of the true "
                     "exposure"},
}

#: The declared family fitted through the ladder, written as the formula
#: rather than as its name: the name is this codebase's and the formula is
#: the reader's, and it is the formula that says what the extrapolation
#: will do past the last rung.
EXTRAPOLANTS: dict[str, language.Words] = {
    "rational": {"zh": "有理式 γ0+γ1/(γ2+λ)", "en": "rational γ0+γ1/(γ2+λ)"},
    "quadratic": {"zh": "二次式 γ0+γ1λ+γ2λ²", "en": "quadratic γ0+γ1λ+γ2λ²"},
    "linear": {"zh": "直线 γ0+γ1λ", "en": "linear γ0+γ1λ"},
}

#: Why an interval is absent. A finding, not a gap in the output — in both
#: cases the point stands, and what the reader acts on is which premise
#: failed.
NO_INTERVAL: dict[str, language.Words] = {
    "extrapolated_variance_is_not_positive": {
        "zh": "方差外推到 λ=−1 处不是正数（τ = 各档方差的均值减去重复之间的"
              "方差，这个差本来就可能为负），所以这里没有可报的宽度，而不是"
              "把它压到零再报一个数",
        "en": "the variance extrapolated to λ=−1 is not positive (τ is the "
              "mean of a rung's variances minus the variance across its "
              "replicates, and that difference genuinely permits a negative "
              "answer), so there is no width to report rather than one "
              "clipped into existence",
    },
    "validation_study_reaches_past_the_ladder": {
        "zh": "量 σ²_u 的那次研究只有 {validation_df} 个自由度，它的抽样分布里"
              "有 {share} 落在 σ²_u 大到超过暴露本身观测离散度的那一段——那样的"
              "误差方差，你的数据自己就排除了。被排除的这部分已经比区间端点该"
              "代表的那条尾巴还大，所以这里报的是没有区间，而不是一个在剩下那"
              "部分上截断出来的区间。要么换一份把 σ²_u 量得更准的验证研究，要么"
              "承认这份数据和这个声明对不上",
        "en": "the study that measured σ²_u has {validation_df} degrees of "
              "freedom, and {share} of its sampling distribution sits where "
              "σ²_u would reach the exposure's whole observed spread — an "
              "error variance your own data rules out. That excluded share is "
              "already larger than the tail an endpoint is meant to be, so "
              "what is reported is no interval rather than one truncated onto "
              "what is left. Either the study that measured σ²_u has to pin "
              "it down better, or this data and that declaration disagree",
    },
    "declared_clustering_is_not_in_the_variance": {
        "zh": "梯子上每一档的方差都是模型给的，而模型方差说的是行与行独立；"
              "你声明了簇 {cluster}，也就是说它们不独立。点估计不受影响——"
              "聚类花的是精度，不是识别",
        "en": "every variance on the ladder is the fitter's own, and a "
              "model-based variance is a statement about independent rows — "
              "and you declared the cluster {cluster}. The point is "
              "untouched: clustering costs precision, not identification",
    },
}
