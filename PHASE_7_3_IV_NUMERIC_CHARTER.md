# Phase 7.3 Charter — IV 数值估计

> 立项日期：2026-04-25
> 状态：**已批准** — 开工
> 父 charter：PHASE_7_M2_CHARTER.md
> 前置：Phase 7.1 + 7.2 已落地

## 0. Scope

识别层 6.iv 判断"能否用 IV 识别"，本 slice 给**数字**。

**首版**：
- `estimate_iv_ate(data, treatment, outcome, instrument, conditioning=(), ...)`
- 两个 estimator：
  - **Wald**：`(E[Y|Z=1] - E[Y|Z=0]) / (E[X|Z=1] - E[X|Z=0])`，二值 Z + X 下等价于 LATE（monotonicity 假设下）
  - **2SLS**：两阶段最小二乘，sklearn LinearRegression 两次即可；用于连续/线性场景
- 自动选择：Z 和 X 都二值 → Wald；否则 → 2SLS
- Bootstrap CI
- Conditioning（给定 W）的 IV：把 W 塞进每个阶段的回归特征
- 新 method enum：`iv_wald`, `iv_2sls`
- Verifier rule `numeric_iv_estimate`（松弛审）
- Eval case 27

**不做**：GMM / weak-instrument tests / Anderson-Rubin / overid tests → Phase 7.5+

## 1. S 切片

- S.IVN.1: `estimate_iv_ate` 原语（Wald + 2SLS + bootstrap CI）
- S.IVN.2: dispatch 集成（backdoor/front-door 都失败时尝试 IV）
- S.IVN.3: verifier rule `numeric_iv_estimate`
- S.IVN.4: schema 扩展
- S.IVN.5: eval case 27 + DoWhy parity

**总预估**：1-2 天。

## 2. 语义

### 2.1 Wald estimator（binary Z, binary X）

```
ATE_Wald = (E[Y | Z=1] - E[Y | Z=0]) / (E[X | Z=1] - E[X | Z=0])
```

**假设**：IV1/IV2/IV3 + **monotonicity**（Z 对 X 影响方向一致）。

在 monotonicity 下，Wald 恰好恢复 **LATE**（Local Average Treatment
Effect on compliers）。这**不是**人群 ATE——用户必须明白这个局限。

### 2.2 2SLS estimator（continuous Z or X）

```
Stage 1: fit X̂ = f(Z, W)  (linear regression)
Stage 2: fit Y = β·X̂ + γ'W + ε  → β is the ATE
```

**假设**：IV1/IV2/IV3 + **linearity** + **constant treatment effect**.

在线性齐次效应下，2SLS 恢复人群 ATE；在异质效应下，它估的是**效应权
重平均**（本 slice 不做精细区分）。

### 2.3 Conditional IV (W ≠ ∅)

把 conditioning set W 塞进两阶段的回归特征（两阶段都包含 W）。
Verifier 松弛审只检查 W 非空情况下的 mediator 与识别步骤的一致性。

## 3. Verifier 松弛审

同 backdoor / front-door：
- method enum 合法
- point 在 CI 内
- data_hash SHA-256
- sample_size >= 10
- instrument 非空且不在 {treatment, outcome}
- 引用的 `iv_criterion_check` step 的 instrument 匹配

## 4. 完成条件

- [ ] 5 个 S 切片全部合并
- [ ] Wald 和 2SLS 两个路径都端到端跑通
- [ ] DoWhy IV parity
- [ ] 回归保持 909+

## 5. 后续

7.3 完成 → 7.4 mediation numeric（linear + Imai via statsmodels）。
