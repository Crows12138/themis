# Case 003 — Card 1995 教育经济学：schooling → earnings

> 跨域验证（医学 → 教育经济学）。同时验 Themis 是否能 auto-detect
> IV-shaped 结构 + unmeasured_confounder_risk 的 cross-domain 适用性。

## NL question

"多读书能提高收入吗？"

## Authoritative source

- **Card D.** "Using Geographic Variation in College Proximity to
  Estimate the Return to Schooling." in *Aspects of Labour Market
  Behaviour: Essays in Honour of John Vanderkamp* (1995), University
  of Toronto Press.
- **Card D.** "The Causal Effect of Education on Earnings." in
  *Handbook of Labor Economics* Vol 3, 1999, ch. 30.
- **Angrist & Krueger.** "Instrumental Variables and the Search for
  Identification: From Supply and Demand to Natural Experiments."
  *J Econ Perspect* 2001;15(4):69-85.

### 核心 quote（数据限制）

Card 1999 §6.1：

> Estimates of the return to schooling from observational studies are
> potentially biased by **omitted ability variables**: ability affects
> both the schooling decision and earnings. **Even after controlling
> for measured ability proxies (test scores, family background),
> residual unmeasured ability bias remains a concern**, motivating
> the use of natural experiments such as geographic distance to
> college as instruments.

要点：与 HRT-CVD / vitamin D-CVD 同结构教训——measured 调整之后
**residual unmeasured confounder** 仍然存在，需要 IV / 自然实验来
旁路。

## Encoded kernel_ast

[`case_003_card_schooling_earnings.json`](case_003_card_schooling_earnings.json)

DAG（用户视角，**未**声明 bidirected）：
- `distance → schooling`（距大学越近 → 上学多）
- `ability → schooling`（measured proxy）
- `ability → earnings`（measured proxy）
- `schooling → earnings`（target effect）

注意 `distance` 没到 `earnings` 的 directed edge——这是 IV 的结构特征
（Z→X but no Z→Y）。但用户**没有**声明 bidirected `schooling ↔
earnings`，因此 measured-only 视角。

## Themis 实跑结果

```
status: needs_investigation
explanation:
  ⚠ 答案是 `balke_pearl_iv` 给出的符号区间，不是点估计。
    区间有效性以 iv1_relevance / iv2_exclusion / iv3_independence 为前提。
  ⚠ Backdoor 识别假设你列出的 confounder 已经测全 ……
    [unmeasured_confounder_risk advisory]

data_gap_report.gaps:
  - missing_distribution (blocking)
  - ambiguous_variable_definition × 2 (important)
  - answer_is_bounds_not_point_estimate (informational, IV bounds)
  - unmeasured_confounder_risk (informational)

bounds_result.method: balke_pearl_iv（不是 case 001/002 的 manski_natural！）
```

**关键观察**：Themis 自动检测到 `distance` 是 IV-shaped（Z→X 无 Z→Y），
切换到 Balke-Pearl IV bounds。这是 lightweight structural detection，
不需要用户显式声明 IV 意图。

## 评估：✅ match（双 advisory 协同）

### Themis 命中 ✅

- DAG 有 confounder 模式（ability）+ IV-shaped 模式（distance）
  双重识别
- 自动从 manski_natural 升级到 **balke_pearl_iv bounds**（更紧）
- IV 假设（iv1/iv2/iv3）显式列在 ⚠ caveat 里
- `unmeasured_confounder_risk` 同时 fire——advisory 仍然适用，因为
  user 没把 unmeasured ability 形式化为 bidirected
- 跨域：医学 case 001/002 → 教育经济学 case 003，advisory 措辞
  里的具体例子（HRT/vitamin D/breastfeeding）虽然 medicine-tagged，
  但**核心 message（measured 调整后残留 confounder）domain-agnostic**

### 双 advisory 是否冗余？

不是。它们的 message 互补：
- `iv_identification_assumption_required` (via `answer_is_bounds_not_point_estimate`
  with method=balke_pearl_iv): "IV bounds 的有效性依赖 IV1/IV2/IV3"
- `unmeasured_confounder_risk`: "你的 measured 调整可能不够，需要在
  DAG 里把 latent 形式化"

第二条 actionable next step（"添加 bidirected 边"）正好对应 Card 用
IV 的动机——把 unmeasured ability 显式纳入图。

### 域 portability 注意

advisory 描述里的具体 case（HRT-CVD / vitamin D-CVD / breastfeeding-IQ）
都是 medicine 域。教育经济学家看到这条可能觉得"和我无关"——message
正确但例子不接地。**iter 8+ 候选改进**：让 description 用更通用的
phrasing（"此结构在多个域有 well-documented RCT-vs-observational /
IV-vs-OLS reversal"）或按域插入相应例子（要 KB / domain detection
hint）。

## 历史

- 2026-05-07 iter 7：编码 + 跑 + 评估，✅ match。第三个跨域
  confirmation（医学 × 2 + 教育经济学 × 1）。次要发现：advisory
  domain examples 是 medicine-only，跨域 portability 待 iter 8+ 改进。
