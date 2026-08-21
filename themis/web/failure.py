"""What a person is told when something did not work.

Fifteen handlers in :mod:`themis.web.app` each caught ``Exception`` and
handed the browser ``{"error": type(exc).__name__, "message": str(exc)}``.
``str(exc)`` is whatever the raise site wrote, and this package's raise
sites write for more than one reader: an invariant for whoever maintains
it, an argument contract for whoever made the call, a refusal for whoever
asked the question. One catch-all at the edge routed all of them to the
last one — which is why "not addressed to a reader" had no name on this
side of the wire. **A distinction that is not being drawn has nothing to
name.** So it is drawn here, once, and it has two sides.

On one side, a sentence the person can act on, in their language. On the
other, ``str(exc)`` — kept rather than dropped, because a person who hit
an internal error can paste it into a bug report, and named
``diagnostic`` so that nothing downstream mistakes it for the sentence.

The sentence goes out as ``words`` rather than as a finished string. That
is the shape ``/api/audit`` already uses and for its reason: a failure is
an artifact rather than a rendering, and one that had already chosen a
language would make two readers of one failure need two runs. The browser
fills it — see ``errorText`` in ``api.ts``.

**A refusal that already has its own sentence keeps it.** An estimator
that declines carries a species, and the species owns its wording in every
language (:data:`themis.refusals.SAYS`). Wording it a second time here
would be the duplication that table exists to remove.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from .. import language, refusals

#: What failed, said to the person who was waiting for it.
#:
#: Keyed by stage rather than by exception type, because the type is what
#: went wrong inside and the stage is what did not happen for them. The
#: same ``ValueError`` means "your data would not parse" in one endpoint
#: and "the graph was rejected" in another, and a person cannot tell those
#: apart from the type's name.
STAGE: dict[str, language.Words] = {
    "run": {
        "zh": "这份程序没能跑完",
        "en": "this program did not run to completion",
    },
    "verify": {
        "zh": "这次复核没能跑完",
        "en": "this re-check did not run to completion",
    },
    "audit": {
        "zh": "独立复核没能跑完",
        "en": "the independent re-checks did not run to completion",
    },
    "read_data": {
        "zh": "这份数据没能读进来",
        "en": "this data could not be read",
    },
    "empty_data": {
        "zh": "上传的数据没有任何行",
        "en": "the uploaded data has no rows",
    },
    "estimate": {
        "zh": "在这份数据上估计时没能跑完",
        "en": "the estimate did not run to completion on this data",
    },
    "nl_to_kernel_ast": {
        "zh": "把这个问题变成因果图没有成功（已重试三次）",
        "en": "turning this question into a causal graph did not succeed "
              "(after three attempts)",
    },
    "themis_run": {
        "zh": "因果图生成出来了，但 kernel 不接受它（已重试三次）",
        "en": "a causal graph was produced and the kernel would not accept "
              "it (after three attempts)",
    },
    "render_reply": {
        "zh": "结果已经算出来了，把它写成回复这一步没有成功",
        "en": "the result was computed; writing it up as a reply did not "
              "succeed",
    },
    "clarify": {
        "zh": "补完缺口之后重跑没有成功",
        "en": "re-running with the gaps filled in did not succeed",
    },
    "nothing_to_clarify": {
        "zh": "没有可以应用的澄清",
        "en": "there was nothing to apply",
    },
    "nothing_to_assume": {
        "zh": "这个查询没有缺失的概率分布可供估算——可能它已经算得出来，"
              "也可能缺的是结构或定义而不是数值",
        "en": "this query has no missing probability distribution to "
              "estimate — either it is already answerable, or what is "
              "missing is structure or a definition rather than a number",
    },
    "assume": {
        "zh": "应用这些假设没有成功",
        "en": "applying these assumptions did not succeed",
    },
    "propose_theta_priors": {
        "zh": "提议先验没有成功",
        "en": "proposing priors did not succeed",
    },
    "llm_bridge": {
        "zh": "LLM 桥接没能加载",
        "en": "the LLM bridge could not be loaded",
    },
}


def payload(stage: str, exc: BaseException | None = None,
            **extra: Any) -> dict[str, Any]:
    """The body a failed endpoint returns.

    ``stage`` must be one of :data:`STAGE`; an unknown one raises here
    rather than reaching a reader as an empty sentence, which is the
    failure mode a lookup with a fallback would have.
    """
    if stage not in STAGE:
        raise KeyError(
            f"no sentence for stage {stage!r}; declare it in "
            f"themis.web.failure.STAGE, where the endpoint's readers are"
        )
    words: language.Words = STAGE[stage]
    slots: dict[str, Any] = {}
    if isinstance(exc, refusals.EstimatorFailure):
        own = refusals.SAYS.get(str(exc.failure_type))
        if own is not None:
            words, slots = own, dict(exc.details)
    body: dict[str, Any] = {"stage": stage, "words": dict(words)}
    if slots:
        body["slots"] = slots
    if exc is not None:
        # Both of these are the exception's, and neither is the sentence.
        # A stage that refuses without one — nothing to clarify, no rows
        # uploaded — has no class name to give, and ``stage`` already says
        # what happened; naming it twice would make the second name look
        # like a second fact.
        body["error"] = type(exc).__name__
        body["diagnostic"] = str(exc)
    body.update(extra)
    return body


def refused(stage: str, exc: BaseException | None = None, *,
            status: int = 400, **extra: Any) -> JSONResponse:
    """:func:`payload`, as the response an endpoint returns."""
    return JSONResponse(status_code=status,
                        content=payload(stage, exc, **extra))
