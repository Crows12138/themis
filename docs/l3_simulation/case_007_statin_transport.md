# Case 007 — Statin RCT 推到 75+ 老年人（transport）

> 第一个 L3-test transport 路径（Bareinboim 2014）。验 Phase 9
> §T9.1 transport identification 三种 advisory 协同触发。

## NL question

"50-70 岁人群的 statin RCT 显示降低 CVD，能不能推到我 75+ 老年患者
群体？"

## Authoritative source

- **Bareinboim E, Pearl J.** "A General Algorithm for Deciding
  Transportability." *Adv Neural Inf Process Syst* 2014;27.
- **USPSTF 2022 Statin Recommendation** (Mangione et al. *JAMA*
  2022;328:746-753): "Evidence is limited for primary prevention
  of CVD in adults aged 76 years or older."
- **Mortensen MB, Falk E.** "Primary Prevention With Statins in the
  Elderly." *J Am Coll Cardiol* 2018;71:85-94. Explicit transport
  framing — RCT pop ≠ ≥75 pop on multiple covariates.

### 核心 quote（数据限制）

USPSTF 2022:
> Most randomized trials of statins for primary prevention enrolled
> participants aged ≤75. **Direct evidence in the population aged
> ≥76 is limited; benefit-risk balance may differ due to higher
> baseline CVD risk, more comorbidities, and altered drug
> metabolism**. Recommendations for this age group rely on
> extrapolation rather than direct trial evidence.

要点：transport bias 通过 age × baseline-risk × comorbidity ×
metabolism 跨人群 shift；直接证据缺，要 transport adjustment。

## Encoded kernel_ast

[`case_007_statin_transport.json`](case_007_statin_transport.json)

DAG：
- `statin_use → cvd_event` (target effect from RCT)
- `age_high → statin_use, age_high → cvd_event` (confounder)
- `selection_node S_age` affects age_high, source=rct_50_to_70_pool,
  target=user_75plus
- query.target_population = "user_75plus"

## Themis 实跑结果

```
status: structurally_solved
GAP KINDS:
  - transport_source_conditional_unknown (blocking)
  - transport_target_distribution_unknown (blocking)
  - ambiguous_variable_definition × 2 (important)
  - transport_identification_assumption_required (informational)
  - unmeasured_confounder_risk (informational)

extensions.transport_identification:
  source: rct_50_to_70_pool
  target: user_75plus
  adjustment_set: [age_high]  ← S_age 正确锁定
```

## 评估：✅ match — 三 advisory 三层互补

### Themis 命中 ✅

- **S-admissibility 结构识别**：S_age 被正确识别为 selection node，
  age_high 进 adjustment_set
- **transport_identification_assumption_required** ⚠ informational：
  提示 S-admissibility 不是 free pass —— selection_nodes 必须真的
  捕获两人群间分布差异
- **transport_target_distribution_unknown** ⚠ blocking：要 P*(age)，
  即 75+ 人群中 age_high 的边际分布
- **transport_source_conditional_unknown** ⚠ blocking：要 RCT 池里
  分层条件分布 P(cvd|do(statin), age)；meta-analysis 通常只汇总成
  一个数，subgroup analysis 才给。**这正是 USPSTF 2022 quote 里的
  "evidence is limited"——meta-analysis 没分层 stratify by age**
- **unmeasured_confounder_risk** ⚠ informational：DAG 没声明
  bidirected → 即使 age 调整了，仍可能漏其他 unmeasured
  confounder（USPSTF 提到的 comorbidities, drug metabolism 等没在
  user 的 DAG 里）

### 三层信息互补，不冗余

- 第一层：identification 结构（transport identification 通过）
- 第二层：identification 假设（S-admissibility advisory）
- 第三层：identification 数据（双 distribution gap + meta-analysis
  subgroup hint）
- 第四层：DAG 完整性（unmeasured_confounder_risk 提醒可能漏 latent）

USPSTF 2022 quote 里的"benefit-risk balance may differ" 正好对应
第四层——age 是 measured confounder，但 comorbidities 和 metabolism
是 user 没声明的 latent。Themis 的 unmeasured_confounder_risk
prompt 用户去思考 DAG 是否完整。

## 历史

- 2026-05-07 iter 15：编码 + 跑 ✅ match。第一个 L3-tested transport
  路径。Phase 9 §T9.1 三 advisory 全部正确触发，加 unmeasured_confounder_risk
  补 DAG 完整性这层。USPSTF 2022 quote 直接支持 Themis 的
  source-conditional unknown finding（meta-analysis subgroup gap）。
