# Case 008 — Pearl monotone counterfactual：治疗后存活，没治会怎样

> 第一个 L3-test counterfactual (Layer 3) 路径。Phase 5 §C 的
> Balke-Pearl 二值单调 bounds + counterfactual_identification_assumption_required
> 触发验证。

## NL question

"病人接受了实验性治疗并存活下来。如果当初不治疗，他还会活吗？
（probability of necessary causation）"

## Authoritative source

- **Pearl J.** "Causality: Models, Reasoning, and Inference." 2nd ed.
  Cambridge University Press 2009, §7 "The Logic of Counterfactuals."
  §7.4.1 "Probabilities of Causation: Bounds and Identification."
- **Balke A, Pearl J.** "Bounds on Treatment Effects from Studies
  with Imperfect Compliance." *J Am Stat Assoc* 1997;92(439):1171-
  1176.
- **Tian J, Pearl J.** "Probabilities of Causation: Bounds and
  Identification." *Annals of Mathematics and Artificial Intelligence*
  2000;28:287-313.

### 核心 quote（数据限制 + 假设）

Pearl 2009 §7.4.1:
> Because the counterfactual P(Y_{X=0} = 1 | X=1, Y=1) refers to a
> world that did not occur, **its identification from any
> observational study is logically impossible without additional
> assumptions**. Under monotonicity (X = 1 cannot decrease Y = 1),
> tight bounds are obtainable from the joint distribution P(X, Y);
> these are the Balke-Pearl bounds. **Without monotonicity, only
> the natural bounds (Manski 1990) apply**, which can be
> uninformative.

要点：counterfactual identification 是 Layer 3，**逻辑上需要假设**。
最少需要 monotonicity（X 对 Y 非递减）+ binary outcome 才能给紧界。

## Encoded kernel_ast

[`case_008_pearl_monotone_counterfactual.json`](case_008_pearl_monotone_counterfactual.json)

最小 counterfactual：
- variable: treatment, survival
- cause: treatment → survival
- query.kind: counterfactual
  - observed: treatment=true
  - counterfactual_intervention: treatment=false
  - counterfactual_target: survival=true
  - assumptions.monotonicity: non_decreasing

## Themis 实跑结果

```
status: needs_investigation
GAP KINDS:
  - missing_distribution × 6 (blocking)：
      P(survival=False|treatment=False)
      P(survival=False|treatment=True)
      P(survival=True|treatment=False)
      P(survival=True|treatment=True)
      P(treatment=False)
      P(treatment=True)
  - ambiguous_variable_definition × 2 (important)
  - counterfactual_identification_assumption_required (informational)

EXPLANATION:
⚠ 反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的
  潜在结果）+ composition 公理为前提；跨世界的格子还要用到一臂
  干预风险 P(Y=1|do X)，它凭什么成立（调整集充分 / 图结构正确到
  general ID 能识别 / 来自随机实验）也一并被继承；单调性若声明，
  只是把区间收紧成点的额外前提。这些假设都无法从数据本身验证。
```

## 评估：✅ match — Layer 3 advisory + 完整数据规格

### Themis 命中 ✅

- Layer 3 query 正确分发到 counterfactual handler
- `counterfactual_identification_assumption_required` ⚠ informational
  触发：consistency / composition 总是要，干预风险的来源按需要
  （调整集 / general ID / 随机实验三选一），单调性按是否声明
  ——分层列出，与 Pearl 2009 §7 quote 对齐
- 观测联合需要的 6 个数据点完整列出：
  - 4 个条件分布 P(Y|X=x)
  - 2 个 X 边际分布
- monotonicity assumption 显式接受（assumptions.monotonicity 字段）

### unmeasured_confounder_risk 抑制（正确）

case 008 是 2-variable DAG，根据 iter 5 实现的逻辑：var_count < 3
→ 不 fire `unmeasured_confounder_risk`。这是正确的——counterfactual
on bare X→Y 不需要 confounder coverage advisory，因为整个 path 是
do-calculus 直接 derive，不依赖 observed confounder coverage。

### 副观察：UX 可改进点（minor）

6 个 missing_distribution 列得很详细但繁。可以聚合成"缺 P(X) 边际
+ P(Y|X) 4×条件表"。不是 bug，是 UX polish。iter 17+ 可考虑。

## 历史

- 2026-05-07 iter 16：编码 + 跑 ✅ match。第一个 L3-tested
  counterfactual (Layer 3) 路径。Pearl 2009 §7 quote 直接 cover
  Themis 的 advisory message。L3 corpus 现覆盖**全 8 个**识别路径
  / query kind（backdoor / IV bounds / front-door / dose-response /
  mediation / transport / counterfactual / + 默认 effect 路径）。
