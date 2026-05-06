# Case 009 — Mediation × Transport 共现 stress test

> 真实场景：smoking cessation 在 US RCT 中通过 placenta 改善 birthweight，
> 推到中国人群。同时是 mediation 又是 transport。**找到 Themis 静默
> dispatch finding。**

## NL question

"美国 RCT 显示孕期戒烟通过改善胎盘功能能降低低出生体重风险。这套
mediation 分析能不能直接用到中国人群（年龄结构跟 RCT 不一样）？"

## Authoritative source

- **VanderWeele TJ.** "Mediation Analysis: A Practitioner's Guide."
  *Annu Rev Public Health* 2016;37:17-32.
- **Bareinboim E, Pearl J.** "A General Algorithm for Deciding
  Transportability." *NeurIPS* 2014.
- **Cole SR, Stuart EA.** "Generalizing evidence from randomized
  trials to target populations: The ACTG 320 trial." *Am J Epidemiol*
  2010;172:107-115. — discusses 联用 mediation + transport 的实际操作

### 联用 best practice

Cole & Stuart 2010 + VanderWeele 2016 §6.2:
> When transporting mediation results across populations, **the
> two operations are performed sequentially**: first compute
> NDE/NIE in the source population (with appropriate identification
> assumptions), then transport each component to the target
> population (with S-admissibility plus mediator-population
> exchangeability). Failing to acknowledge both layers can lead to
> implicit conflation.

要点：mediation + transport 是 sequential operations，不能 simultaneously
dispatch。Themis 应该至少 disclose 哪个 layer 在跑哪个 layer 没跑。

## Encoded kernel_ast

[`case_009_mediation_x_transport.json`](case_009_mediation_x_transport.json)

DAG：smoking_cessation → placental_function → low_birthweight + 直接
edge + age_high 作为 measured confounder + selection_node S_age
（US → China）。

query 同时设 `mediator` 和 `target_population`。

## Themis 实跑结果

```
status: structurally_solved
GAP KINDS:
  - transport_source_conditional_unknown (blocking)
  - transport_target_distribution_unknown (blocking)
  - ambiguous_variable_definition × 2 (important)
  - transport_identification_assumption_required (informational)
  - unmeasured_confounder_risk (informational)

extensions keys: ['transport_identification']  ← 只有 transport，没有 mediation！
mediation_decomposition: 不存在
```

## 评估：◐ partial — 找到 dispatch silence finding

### Themis 命中 ✅

- transport identification 全套触发（4 advisory 层）
- unmeasured_confounder_risk 也 fire（age 是 measured confounder + 没
  bidirected）
- structurally_solved 且 transport 公式构造好

### Themis 错过 ❌（这是 finding）

**Mediation 路径被静默 skip**：
- query 设了 `mediator` 字段
- mediation_decomposition extension 是空的（`mediator_valid` 是 None）
- 没有任何 mediation_identification_assumption_required advisory
- **用户看不到 mediation 没跑**——只看到 transport result，可能误以
  为 NDE/NIE 已经被处理了

scheduler 的 dispatch 优先级里 mediation 比 transport 早，但实际跑
出来 transport 赢了。可能 root cause：当 query.target_population 设
了的时候，dispatcher 优先走 transport 路径，没回头检查 mediator。

### 这是真 bug 还是设计选择？

**Argument for 设计**：mediation × transport 联用本来就是 sequential
ops（先 mediation source，再 transport 到 target）。Themis 不能在一
个 query 里两个都做，**只 dispatch 一个**是合理的。

**Argument for bug**：不告诉用户哪个跑了哪个 skip 了，是 silent
miss。Themis 的"数据缺口诊断器"定位 explicitly 包括"诚实告诉用户没
做什么"。这条 case "我同时给了你 mediator 和 target_population，你
只回了 transport 结果"对应"static silence about un-attempted layer"。

### iter 19+ candidate fix

新 gap_kind：`unattempted_layer_due_to_dispatch_conflict`
- severity: important（不 blocking，但用户应该知道）
- description: "Query 同时设了 mediator 和 target_population。当前
  dispatch 只跑了 transport。Mediation 分析需要单独 query（先在
  source population 跑 NDE/NIE，再 transport 各 component）。详见
  Cole & Stuart 2010 / VanderWeele 2016 §6.2。"
- alternative_paths: [
    "拆成两个 query：先 mediation in source pop，再 transport to target",
    "如果只想要 transport ATE，去掉 mediator 字段",
  ]

trigger 条件：query 有 `mediator` 字段 AND `target_population` 字段
AND result.extensions.mediation_decomposition is None。

## 历史

- 2026-05-07 iter 18：编码 + 跑，**partial：mediation × transport 共
  现时 mediation 被静默 skip**。这是 silent dispatch finding，对应
  VISION "诚实告诉用户没做什么"原则下的 honesty gap。iter 19+ 候选
  fix：新 gap_kind 显式 disclose unattempted layer。
