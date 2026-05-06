# Case 005 — 有氧运动 dose-response 对血压（Whelton 2002）

> 第一个 L3-test Phase 13 的 `dose_response_data_required` gap_kind。
> 真实问题不是"做不做运动有 effect"而是"多少分钟降多少血压"，要
> dose-response curve。Themis 不画曲线，但要告诉用户去哪画 + 怎么画。

## NL question

"每周做多少分钟有氧运动能降多少 systolic 血压？"

## Authoritative source

- **Whelton SP et al.** "Effect of Aerobic Exercise on Blood Pressure:
  A Meta-Analysis of Randomized, Controlled Trials." *Annals of
  Internal Medicine* 2002;136(7):493-503. PMID: 11926784
- **Cornelissen VA & Smart NA.** "Exercise training for blood
  pressure: a systematic review and meta-analysis." *J Am Heart
  Assoc* 2013;2(1):e004473. PMID: 23525435
- **AHA 2013 Lifestyle Recommendations** (Eckel et al. *Circulation*
  2014;129(25 Suppl 2):S76-99) — 给 dose-response 推荐量

### 核心 quote（数据规格 ground truth）

Whelton 2002 §Methods：
> Eligible studies were RCTs that compared aerobic exercise (≥4
> weeks) with a no-exercise control. Outcome was change in systolic
> and diastolic BP. **Random-effects meta-regression was used to
> assess dose-response with exercise frequency, intensity, and
> duration as continuous predictors.**
>
> Most included studies measured BP at baseline + post-intervention
> (8-12 weeks); few had multiple post-baseline timepoints. **Median
> sample size per arm: 35** (range 16-178).

要点：
1. RCT design with multiple aerobic-exercise dose arms
2. Dose modeled continuously（频率 × 时长 × 强度），所以单 X 至少
   需要 4-5 dose levels for non-linearity detection
3. 标准时长 4-12 周，baseline + post 测量
4. SUTVA 关注：受试者间分组隔离（避免讨论协调）

## Encoded kernel_ast

[`case_005_exercise_bp_dose_response.json`](case_005_exercise_bp_dose_response.json)

注意：`extensions.ambiguities = [{kind: "dose_response_query", ...}]`
是 A1 prompt 在 NL 解析时设的；本 L3 case 手动设以模拟 NL → kernel
全链路。

## Themis 实跑结果

```
status: needs_investigation
gap_kinds:
  - dose_response_data_required (blocking)  ← 触发 ✓
  - missing_distribution (blocking)
  - ambiguous_variable_definition × 2 (important)
  - answer_is_bounds_not_point_estimate (informational)

dose_response spec:
  data_type: ipd
  min_sample_size: 375 (5 采样点 × 75/点)
  precision_target: K=5 × n=75/点 (Cohen's d=0.5, α=0.05, power=0.80)
  sampling_point_count: 5
  confounders_required: []           ← 见下"次要 finding"
  time_window: "建议 baseline + 4w + 12w（视实际研究问题调整）"
  sutva_concerns: [
    "受试者之间不能讨论 / 协调干预（违反 SUTVA）",
    "若有溢出 / 同侪效应，需登记并在分析中纳入"
  ]
```

## 评估：✅ match（gap 触发 + spec 合理）+ ◐ 次要 finding

### Themis 命中 ✅

- `dose_response_data_required` 正确触发（blocking, point_estimate）
- sampling_point_count=5 与 Whelton 2002 meta-regression 实践一致
  （5 dose levels >= 4 满足 non-linearity 检测下界）
- min_sample_size=375 比 Whelton median (~35/arm × 5 arms = 175)
  保守（power calc 用 d=0.5 是 conservative，运动-血压实际 effect
  size 接近 d=0.4-0.6）
- time_window "baseline + 4w + 12w" 与 Whelton 2002 "8-12 weeks
  intervention" 同范围
- SUTVA concerns 给的两条覆盖了 lifestyle interventions 的标准坑

### 次要 finding（domain-specific opportunity）

**`confounders_required` 是空的**，因为 user encoded DAG 只有 2 节点
（treatment + outcome）。但 Whelton 2002 + AHA 2013 都明确指出
exercise-BP RCT 应控制 age, BMI, baseline BP, sex（baseline BP 尤其
critical 因为 regression-to-mean）。

**这不是 Themis bug**——kernel 信任用户给的 DAG。但 advisory 可以
更 helpful：在 confounders_required 空时，加一条 description
hint："dose-response 分析典型还需控制 baseline outcome（regression-
to-mean）+ age + 可能的 effect modifiers；用户给的 DAG 没声明这些。"

iter 13+ 候选改进：当 confounders_required is empty AND query is
dose-response，加 hint 提示"可能漏了 baseline / age / sex 等 standard
covariates"——但要小心避免变成 domain-specific 的硬编码。可能用
"dose-response 推荐至少声明 baseline outcome + 主要 demographic
covariates"这种 generic 措辞。

## 历史

- 2026-05-07 iter 12：编码 + 跑 ✅ match。第一个 L3-tested 的 Phase
  13 dose-response gap_kind。次要 finding 关于 confounders_required
  empty 时 advisory 可以更 proactive，候选 iter 13+ 推进。
