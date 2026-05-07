# Case 013 — MacMahon 1990 single-occasion BP → CHD (regression dilution)

> 第 13 例。第一次有意识用真实文献案例测**板块 8 (测量误差) 0%** 状态。
> 选这个不是为了找 silent-wrong，而是因为：MacMahon 1990 *Lancet* 是教科书
> 级单次门诊 BP 测量 → 回归稀释偏差案例，任何流行病学家在该 program shape
> 上 30 秒内会指出它。结果：✅ 真 gap → 加新 GapKind + classifier。
> 板块 8 0% → 5-10%。

## NL question

"在我们的队列研究里，我用基线一次门诊舒张压 (≥90 mmHg) 当『高血压暴露』，
追踪 5-25 年后的冠心病事件。这个 BP→CHD 因果效应识别可靠吗？"

(用户期望：被告知**单次测量** 这个事实本身就是个 documented 偏差源 ——
不需要等到拿到数据后才知道这事。)

## Authoritative source

- **MacMahon S, Peto R, Cutler J, Collins R, Sorlie P, Neaton J, Abbott R,
  Godwin J, Dyer A, Stamler J.** "Blood pressure, stroke, and coronary heart
  disease. Part 1, Prolonged differences in blood pressure: prospective
  observational studies corrected for the regression dilution bias."
  *Lancet* 1990 Mar 31;335(8692):765-74.

  9 prospective observational studies meta-analysis, 420,000 individuals,
  follow-up 5-25 年。

### 核心 quote — regression dilution 是 CONSENSUS 已 documented 的限制

MacMahon 1990 §Methods："Single measurements of blood pressure,
particularly when made in a busy clinic, can substantially over- or
under-estimate the long-term **'usual' blood pressure of an individual**
… If single measurements are used as the explanatory variable in
regression analysis, the slope of the regression line is biased toward
zero — a phenomenon known as **regression dilution bias**."

§Results: "After correction for regression dilution, a long-term
difference of 7.5 mm Hg in usual diastolic BP was associated with at
least 29% (and probably 46%) increased risk of CHD — substantially
**greater** than the 21% suggested by the single-measurement analysis."

→ 单次测量把真效应 **低估约 60%**（原 21% / 校正后 46% × 之间的衰减系数）。

### Hernán & Robins 平行 quote

*Causal Inference: What If* §9 "Measurement Bias":
> "Many observational studies use self-reported smoking, dietary recall,
> or single-occasion measurements. Non-differential misclassification of
> exposure typically biases the estimated effect *toward the null*."

### 已 documented data limitations 跟 Themis 应当 surface 的对应：

1. ✅ **测量误差 (regression dilution)** — single-occasion BP 是 30-50%
   noisy 的 'usual BP' 代理；真斜率被低估 ~60%
2. ✅ **未测混杂** — diet / activity / SES / family history
3. ✅ **变量定义模糊** — DBP "≥ 90 mmHg" 阈值 / CHD 端点定义 / time window
4. ✅ **观察性 vs 实验** — RCT 给的是 *intent-to-treat*，obs 给 dilute 估计

## Encoded kernel_ast

`case_013_macmahon_bp_chd_regression_dilution.json`:

- 图：`bp_diastolic_high → chd_event` + age (混杂) + smoking → chd_event
- 变量声明 `bp_diastolic_high` 显式带 `measurement` 字段：
  `"single-occasion office sphygmomanometer reading at study entry"`
- query：effect query (P(chd | do(bp_diastolic_high)))
- **NOT** declared in `extensions.ambiguities` ——故意不走 case 011 的
  escape-hatch，看 Themis 能否从 program shape 自己发现

## Pre-iter-205 Themis output (the gap)

```
status: needs_investigation

gaps (5):
  missing_distribution (blocking): 缺概率分布 P(chd_event=...)
  ambiguous_variable_definition (important) ×2
  answer_is_bounds_not_point_estimate (informational): manski_natural
  unmeasured_confounder_risk (informational): backdoor 假设 confounder 测全
```

**没有 fire 任何 measurement_error 相关 gap_kind。** Themis 看到了
`bp_diastolic_high.measurement = "single-occasion office..."` —— 这字段
本身就在 schema 里 —— 但当时没有 classifier 读它。MacMahon 1990 那条
"single measurement biases toward zero" 在文献里写了 35 年，Themis 在
板块 8 上是 0% covered 的（COVERAGE_MAP 显式标 0%）。

## Post-iter-205 Themis output (✅ match)

加了 `measurement_error_concern` gap_kind + 新 classifier 后：

```
status: needs_investigation

gaps (6):
  missing_distribution (blocking)
  ambiguous_variable_definition (important) ×2
  measurement_error_concern (important):
    测量误差风险：识别路径上有变量声明了高噪声测量方式 —
    bp_diastolic_high (measurement: 含 "single-occasion")。
    经典文献：MacMahon 1990 Lancet 单次门诊 BP 测量因 within-person
    变异导致 BP→CHD 斜率被 regression dilution 向 0 衰减约 60%；
    Hernán & Robins What If §9 自报告 / 问卷暴露的 non-differential
    mis-classification 同样使估计值低估真效应；Fuller 1987
    Measurement Error Models 给出 attenuation theorem 的形式定义。
    Themis 仅做结构性识别 + 数据缺口诊断，不做去衰减估计。
  answer_is_bounds_not_point_estimate (informational)
  unmeasured_confounder_risk (informational)

result.explanation 头部：
  ⚠ 测量误差风险：识别路径上有变量声明了高噪声测量方式 ...
```

`alternative_paths` 给了三条结构性可执行行动:
1. 用 RCT 数据（消除自报告 / 单次测量）
2. test-retest 子样本做 reliability + regression calibration
3. attenuation factor 范围（Rosner 1989 regression calibration upper bound）

## 评估

### ✅ match (post-iter-205, 与 case 011 anti-finding 互补)

- ✅ MacMahon 1990 quote "single measurement biases toward zero" 直接对应
  新 gap_kind 的 description
- ✅ provenance ref 准确指出哪个变量、哪个字段、命中哪个模式
- ✅ severity = IMPORTANT 而非 INFORMATIONAL：regression dilution 是
  identification-impacting (估计值 magnitude 被低估)，不是只是 caveat
- ✅ suppression 行为对：case 011 已经有 `measurement_quality` ambiguity
  在 extensions.ambiguities，新 classifier 退让，不双发；case 013 没声
  明，从 program shape 直接 fire

### Anti-finding 与 Real-finding 的边界

case 011 (iter 129) 看上去刻意没立这个 gap_kind —— 它的逻辑是
"用户已经声明了 measurement_quality (via llm_declared_ambiguity escape
hatch)，dragon 已被命名"。case 011 的判断是**正确的对那个特定输入**。

**但当用户没声明时**呢？case 013 的输入 `measurement="single-occasion
office sphygmomanometer reading at study entry"` —— 这是**变量 schema 自己
admit 了** 高噪声模态。Themis 要做的事不是 "等用户在 ambiguity 字段里写下
来"，而是 **从用户已经填的字段值结构性识别**。这是 case 011 anti-finding
当时未触及的部分。两个 case 因此互补：
- case 011: extensions.ambiguities 路径 → llm_declared_ambiguity 已覆盖
- case 013: variable.measurement / .observability 路径 → 新
  measurement_error_concern 覆盖

### 范围 honesty

板块 8 的 COVERAGE_MAP 描述从 **0%** 调到 **5-10%**：
- ✅ 加：从 program shape 结构性 surface 测量误差风险
- ✅ 加：suppression 不和 case 011 escape hatch 冲突
- ❌ 没做：去衰减估计 (regression calibration / SIMEX 数值)
- ❌ 没做：differential mis-classification 检测
- ❌ 没做：从 NL 自动 surface "BP 是单次还是 ABPM" 这种 framing

那两个 ❌ 是 Phase 9+ 工作（去衰减估计需要重测子样本 + 新数值估计器；
NL surfacing 是 A1 prompt 增强）。当前 iter 只破冰板块 8 = 0% 这个状态。

## 后续 action

- ✅ Bug fix landed (iter 205 — 是新 capability，不是 bug fix)
- ✅ Add to L3 corpus regression test（must-have:
  measurement_error_concern + missing_distribution + ambiguous_variable_definition;
  must-not-have: graph_theta_independence_mismatch / weak_iv_instrument）
- ✅ 加 unit test pin classifier 触发 + suppression 两个分支
- ✅ Update GAP_KINDS_REFERENCE / response_rendering / gap_to_action 同步
- ✅ COVERAGE_MAP 板块 8 行 + 元基础设施 row gap_kind 数 27 → 28

## 历史

- **2026-05-07 iter 205**: Real-finding via L3 simulation methodology。
  外部权威源：MacMahon 1990 *Lancet* 335:765 + Hernán & Robins *Causal
  Inference: What If* §9 + Fuller 1987 *Measurement Error Models*。Bug：
  Themis 板块 8 (测量误差) 是 documented 0% — variable 的 `measurement` /
  `observability` 字段在 schema 里是一等公民，但没有任何 classifier 读它们。
  case 013 用 single-occasion BP 这个最经典 case surface gap → 加新
  `measurement_error_concern` GapKind + program-shape classifier，
  suppression 兼容 case 011 (declared via extensions.ambiguities 的 escape
  hatch)。L3 corpus 12/12 → 13/13。
