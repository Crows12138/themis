"""Why the bridge between this kernel and a language model came back empty.

Everything here is addressed to somebody sitting in front of the browser.
:mod:`themis.web.app` catches these at four endpoints and hands them to
:func:`themis.web.failure.payload`, which asks the exception whether it
carries its own sentence — so what these species say is what the person
who asked the question is shown, in their language, under the stage
sentence that says which step did not happen.

**They were English f-strings at their raise sites**, on a class that was
a bare ``RuntimeError``: which KIND of thing went wrong and this
occasion's facts were pressed into one string, and the site wrote it. So
they arrived at that door as ``diagnostic`` — the maintainer's channel —
while the reader got only the stage. That is the shape
:mod:`themis.input.semantic_validator` had before its own species existed,
and the door has read the carrier rather than a list of classes since.

**One class, fourteen species, and that is the arrangement rather than a
shortfall.** A caller catches the CHANNEL — this bridge did not produce
what was asked of it — and reads the SPECIES off the exception. Nothing
between here and the endpoint distinguishes them, and nothing should: the
retry loop in ``nl_to_kernel_ast`` retries a parse failure and re-raises a
refusal, and it tells them apart by catching where it calls rather than by
what was raised.

Four audiences run through the fourteen, and naming them is what keeps the
wordings honest rather than uniform. A missing prompt file and an
uninstalled SDK are for whoever runs this; a model that declined the
question is for whoever asked it; a reply that was the wrong shape is for
neither of them and has to say plainly that the model, not the person, is
what did not deliver.

**The fourth audience is whoever has nothing to talk to, and for a long
time it was the only one with no sentence.** Eleven of these describe a
REPLY — it was not JSON, it was a refusal, a prior in it was not a number
— and every one of them is raised where this module reads what came back.
Nothing came back at all is raised by the SDK instead, at the one line
that speaks to it, so it travelled out unworded and a person who had
neither a proxy nor a key was shown the stage sentence: that turning the
question into a causal graph did not succeed, after three attempts. True
of all fourteen, and it reads as a claim about what this project can do
rather than about a socket. The last three are that call's own failures,
split by what the reader does next: start the thing at that address, fix
the credential it refused, or neither because it answered and the answer
was not one. The address is IN the sentence — a proxy on this machine and
an API on the internet fail identically and ask for different things, and
which one it was is the fact that separates them.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Bridge(language.Word, vocabulary="bridge_refusal",
             between=language.BETWEEN_STATEMENTS):
    """What the bridge did not get, said to whoever was waiting for it.

    A model is asked for one of two things here — a program, or a prior
    for each probability the kernel is missing — and each species names
    the step of that ask which did not produce something usable. In the
    order those steps run: the prompt and the SDK this machine needs, then
    reaching a model at all, then what it sent back.
    """

    A_PROMPT_IS_MISSING = ("a_prompt_is_missing", {
        "zh": "这一步要用的提示词文件不在它该在的地方：`{path}`",
        "en": "the prompt file this step reads is not where it should be: "
              "`{path}`",
    })
    THE_SDK_IS_NOT_INSTALLED = ("the_sdk_is_not_installed", {
        "zh": "这台机器上没有装 `{package}`；先 `pip install {package}` "
              "再试一次",
        "en": "`{package}` is not installed on this machine; "
              "`pip install {package}` and try again",
    })
    NOTHING_ANSWERED_AT_THAT_ADDRESS = ("nothing_answered_at_that_address", {
        "zh": "没有连上 `{address}`，那个地址上没有东西应答。这一步需要一个"
              "语言模型：默认走本机的 oauth 代理，先把它跑起来；或者填一把 "
              "`sk-ant-api` 开头的 API key 直接连官方接口",
        "en": "nothing answered at `{address}`. This step needs a language "
              "model: by default that is the oauth proxy on this machine, so "
              "start it — or supply an `sk-ant-api` key and talk to the API "
              "directly",
    })
    THE_CREDENTIAL_WAS_REFUSED = ("the_credential_was_refused", {
        "zh": "`{address}` 收到了这次调用，但不接受它带的凭据：{complaint}",
        "en": "`{address}` received the call and would not accept the "
              "credential it carried: {complaint}",
    })
    THE_CALL_CAME_BACK_WITHOUT_AN_ANSWER = (
        "the_call_came_back_without_an_answer", {
            "zh": "对 `{address}` 的这次调用没有得到回答：{complaint}",
            "en": "the call to `{address}` did not come back with an answer: "
                  "{complaint}",
        })
    THE_REPLY_CARRIES_NO_JSON = ("the_reply_carries_no_json", {
        "zh": "模型的回复里没有 JSON：{reply}",
        "en": "there is no JSON in the model's reply: {reply}",
    })
    THE_JSON_NEVER_CLOSES = ("the_json_never_closes", {
        "zh": "模型回复里的 JSON 括号没有配平，读到末尾都没有合上：{reply}",
        "en": "the braces in the model's JSON never balance, and the reply "
              "ends with it still open: {reply}",
    })
    THE_JSON_DID_NOT_PARSE = ("the_json_did_not_parse", {
        "zh": "模型回复里的 JSON 读不出来（{complaint}）：{payload}",
        "en": "the JSON in the model's reply would not parse ({complaint}): "
              "{payload}",
    })
    THE_MODEL_DECLINED_THE_QUESTION = ("the_model_declined_the_question", {
        "zh": "模型没有把这个问题变成因果图，它给出的理由是：{reason}",
        "en": "the model did not turn this question into a causal graph, and "
              "the reason it gave is: {reason}",
    })
    THE_REPLY_CARRIES_NO_PRIORS = ("the_reply_carries_no_priors", {
        "zh": "模型的回复里没有 `priors` 那份清单：{reply}",
        "en": "the model's reply has no `priors` list in it: {reply}",
    })
    A_PROBABILITY_GOT_NO_PRIOR = ("a_probability_got_no_prior", {
        "zh": "第 {index} 条概率 {probability} 没有拿到先验；缺一条内核就还是"
              "算不出来",
        "en": "no prior came back for probability {index}, {probability}; one "
              "missing is one the kernel is still blocked on",
    })
    A_PRIOR_IS_NOT_A_NUMBER = ("a_prior_is_not_a_number", {
        "zh": "第 {index} 条概率拿到的先验不是一个数：{value}",
        "en": "the prior that came back for probability {index} is not a "
              "number: {value}",
    })
    A_PRIOR_IS_NOT_A_PROBABILITY = ("a_prior_is_not_a_probability", {
        "zh": "第 {index} 条概率拿到的先验是 {value}，不在 0 到 1 之间",
        "en": "the prior that came back for probability {index} is {value}, "
              "which is not between 0 and 1",
    })
    A_PRIOR_CAME_WITH_NO_REASON = ("a_prior_came_with_no_reason", {
        "zh": "第 {index} 条概率 {probability} 拿到了一个数，却没有说它凭"
              "什么；这个数会被标成 AI 估的给你审，而一条没有依据的估计"
              "没什么可审的",
        "en": "probability {index}, {probability}, came back with a number "
              "and nothing to say what it rests on; the number is shown to "
              "you as the model's estimate to review, and an estimate with "
              "no ground under it gives you nothing to review",
    })
