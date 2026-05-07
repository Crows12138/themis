# Case 011 — Salt → blood pressure (DASH-Sodium / INTERSALT)

> 第 11 例（post-iter-100 plateau）。第一次有意识用 case mining 测连续治疗
> 路径在 Themis 现有 26 个 gap_kinds 下的覆盖度。**结果：✅ match，没有
> surface 新 pattern**。这是有信号价值的 anti-finding —— 证明 iter 119-128
> 后存量覆盖对连续治疗 + 测量误差经典案例已经足够。

## NL question

"高盐摄入会升高血压吗？"（effect query）

## Authoritative source

- **DASH-Sodium 2001 (NEJM, Sacks et al.)**: RCT n=412, 30-day controlled
  feeding, 3 sodium levels × 2 diet types. 高盐 vs 低盐: SBP +6.7 mmHg
  on control diet, +3.0 mmHg on DASH diet. **Gold standard evidence**:
  随机分配 + 控制喂食消除 measurement error。
- **INTERSALT 1988 (BMJ)**: 52 国 ~10000 adults observational. 24h 尿钠
  作 measurement standard. 弱正相关，比 DASH 实验小，存在 cross-country
  confounding。
- **NEJM 2014 Mente et al.**: U-curve / J-curve at very low sodium 引发
  controversy；归因于 reverse causation（CHF / 健康人主动限盐）+ 测量
  error（FFQ vs urinary）。
- **USPSTF 2017**: 弱推荐，evidence rated B（不是 A）— observational
  vs experimental tension 无法完全解决。

### 核心 quote (Sacks et al 2001 NEJM Discussion):
> "Our findings indicate that the lower the intake of sodium, the lower
> the blood pressure ... Confidence in causal interpretation rests on
> randomized assignment to controlled feeding diets ... Observational
> studies are subject to several biases including [measurement error
> in self-reported sodium intake] and confounding by overall dietary
> patterns."

### 已 documented data limitations:
1. **测量误差**：sodium 自报告（FFQ）系统性低估；urinary sodium 是 gold
   standard 但 observational cohort 罕见
2. **未测混杂**：overall diet quality, physical activity, 社会经济变量
3. **效应异质性**：salt-sensitive 个体 vs salt-resistant，机制未完全明
4. **持续时间**：RCT 短期 (30 天)；长期心血管 outcome 未验证
5. **DASH × sodium 交互**：DASH diet 上 sodium 效应显著小于控制 diet 上

## Expected Themis output

应当 fire 的 gap_kinds：
- ✅ `unmeasured_confounder_risk` — DAG 测了 diet quality / activity 但
  实际可能更多
- ✅ `missing_distribution` — backdoor 公式需要的 P(BP|sodium, Z)
- ✅ `ambiguous_variable_definition` — sodium_intake_high 的具体阈值 +
  测量方式 + 时间窗未定义
- ✅ `llm_declared_ambiguity` — 我在 extensions 显式声明了
  measurement_quality
- ✅ `answer_is_bounds_not_point_estimate` — Manski natural bounds layer

可能会 miss 的（pre-run 假设）：
- ❓ `measurement_error_concern` (假设的)— 不存在该 gap_kind，但
  llm_declared_ambiguity 是 escape hatch
- ❓ `effect_heterogeneity_warning` — Salt-sensitive subpopulation；
  没专门 gap，但跟 `subgroup` investigation_request 重叠

## Themis 实跑结果

```
$ python -c "import json, themis; ..."

status: needs_investigation

gaps (6):
  missing_distribution (blocking): 缺概率分布
    P(bp_systolic_high=True|overall_diet_quality_high=True,
                            physical_activity_high=True,
                            sodium_intake_high=True)
  ambiguous_variable_definition (important): 变量 bp_systolic_high 缺
    操作化定义 (time_window, measurement, observability, direction,
    baseline, state_vs_event)
  ambiguous_variable_definition (important): 变量 sodium_intake_high
    缺操作化定义 (time_window, direction, baseline, state_vs_event)
  answer_is_bounds_not_point_estimate (informational): 答案是
    manski_natural 给出的符号区间
  llm_declared_ambiguity (informational): 上游 LLM 标记了不确定性
    measurement_quality
  unmeasured_confounder_risk (informational): Backdoor 识别假设你列出
    的 confounder 已经测全 —— DAG 里没有声明任何 bidirected ...
```

bounds_result attached: `manski_natural`，lower/upper 符号 expression。

## 评估

### ✅ match

每条 documented limitation 都被对应的 gap_kind 覆盖：

| Authority's limitation | Themis's gap_kind |
|---|---|
| measurement error in self-reported sodium | `llm_declared_ambiguity` (我显式声明) |
| unmeasured confounders (diet, activity beyond declared) | `unmeasured_confounder_risk` |
| sodium / BP threshold ambiguity | `ambiguous_variable_definition` ×2 |
| short RCT vs long-term outcome | `ambiguous_variable_definition` (time_window field) |
| salt-sensitive heterogeneity | `ambiguous_variable_definition` + investigation_request: structure |
| no point estimate without theta | `missing_distribution` (blocking) + `answer_is_bounds_not_point_estimate` |
| RCT vs observational tension | `unmeasured_confounder_risk`（实指 selection bias 在 obs 数据） |

### Anti-finding 价值

iter 100 plateau 假设 "L3 case 11+ 边际收益已显著递减"。case 011 部分
**确认** 这个假设 —— 没 surface 新 gap_kind —— 但**证明现有 26 gap_kinds
对连续治疗 + 测量误差经典案例已足够覆盖**，这是有正向信号价值的：post-
iter-128 状态对实际医学统计文献 documented 的 limitation 类型已基本覆
盖。

### 没 surface 但**应该** surface 的（要不要立项）

1. `measurement_error_explicit` — 现状 llm_declared_ambiguity 是 escape
   hatch，依赖 LLM 主动声明。如果 LLM 没声明，Themis 不会从 program shape
   自动推断"sodium 是 self-reported → measurement error"。
   **判断**：不立项 — board 8 (测量误差) 是 defer-by-design (0%) per
   COVERAGE_MAP。如果未来要立项，需要 board 8 整体破冰。

2. `effect_heterogeneity_potential` — DAG 没编码 salt-sensitive 子群因为
   它是机制问题不是结构问题。investigation_request 可以问，但没专门 gap。
   **判断**：不立项 — heterogeneity 通过 CDE / mediation 路径处理更自然，
   单独 gap_kind 概念太宽。

## 后续 action

✅ match → 当 regression test pin 住（确保后续 iter 不破 case 011 的覆盖
shape）。

L3 corpus 11/11 维持平稳，下一个 case 可以选刻意 stress 现有 gap_kind
覆盖空白的领域（测量误差 / 多源 transport / latent S）— 但这些都是
COVERAGE_MAP 已 documented 的"长期"项，不需要 case 来 surface 必要性。

## 历史

- **2026-05-07 iter 129**: 案例 mining + ✅ match anti-finding。post-iter-100
  plateau 假设的 first deliberate test：用刻意 stress 连续治疗 + 测量误差
  路径的医学经典案例验证 iter 119-128 features 是否够用。结论：够用。
  L3 corpus 10/10 → 11/11，没有触发新 gap_kind 立项。regression test pin
  加入 `tests/test_l3_corpus_regression.py` CASES list。
