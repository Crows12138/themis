# Phase 7.2 Charter — Front-door 数值估计

> 立项日期：2026-04-25
> 状态：**已批准** — 开工
> 父 charter：PHASE_7_M2_CHARTER.md
> 前置依赖：Phase 7.1 已落地（数据契约 + dispatch + schema + verifier 基础）

## 0. Scope

当 backdoor 不可识别但 front-door 可以时，`themis.estimate` 应能给
数值 ATE。这是 7.1 的直接延伸——大部分基础设施复用，只加一个
estimator。

**必须包含**：
- `estimate_frontdoor_ate(data, treatment, outcome, mediators, ...)`
- 单 mediator：Pearl 2009 Eq 3.29（`∑_z P(z|x) ∑_x' P(y|x',z) P(x')`）
- 多 mediator：复用 7.1 的 chain-rule factoring（6.front-door-multi 已验证）
- sklearn Linear / Logistic fits for each conditional
- Bootstrap CI
- 新 method enum 值：`frontdoor_linear` / `frontdoor_logistic`
- Verifier rule `numeric_frontdoor_estimate`（与 backdoor 同级松弛审）
- Schema 扩展
- Eval case 26 + DoWhy parity

**不包含**：
- 连续 treatment（binary only）
- Interaction-aware mediator fits
- Sequential g-formula（Phase 7.5+）

## 1. S 切片

- S.FDN.1: `estimate_frontdoor_ate` 原语（2-3 小时）
  - 参考：DoWhy `CausalEstimator.estimate_effect(method="frontdoor.two_stage_regression")`
  - 自写：两阶段 + g-formula 合成（同样确定性 + seed）
- S.FDN.2: dispatch 集成（1 小时）
  - 扩展 `_estimate_effect_queries`：backdoor 失败则尝试 `front_door_sets` + fit
- S.FDN.3: verifier rule `numeric_frontdoor_estimate`（1-2 小时）
  - 复用 `numeric_backdoor_estimate` 的松弛审模板
- S.FDN.4: schema + method enum 扩展（30 分钟）
- S.FDN.5: eval case 26 + synthetic DGP + parity（2 小时）

**总预估**：6-9 小时，约 **1-1.5 天**。

## 2. 语义

Pearl Eq 3.29（单 mediator）：

    P(Y | do(X=x)) = ∑_z P(Z=z | X=x) · ∑_{x'} P(Y | X=x', Z=z) · P(X=x')

ATE = E[Y | do(X=1)] - E[Y | do(X=0)]

实现：
1. Fit `P(Z | X)` — linear or logistic depending on Z's dtype
2. Fit `P(Y | X, Z)` — linear or logistic depending on Y's dtype
3. Compute empirical `P(X)` — sample mean/proportion
4. Evaluate outer sum: for each z in Z's domain (bool: {0,1};
   continuous: empirical quantile grid), weight by P(Z=z|X=x),
   marginalize the inner g-formula, diff do(X=1) vs do(X=0).

多 mediator 同样通过 chain-rule：`P(Z1,Z2|X) = P(Z1|X) · P(Z2|Z1,X)`。

## 3. Verifier 松弛审

同 `numeric_backdoor_estimate`：
- method enum 合法（新增 `frontdoor_linear` / `frontdoor_logistic`）
- point 在 CI 内
- data_hash 格式
- sample_size >= 10
- mediator 集合非空
- 引用的 `front_door_criterion` step 的 z 等于 numeric 步骤的 mediators

## 4. 完成条件

- [ ] 所有 5 个 S 切片落地
- [ ] 端到端：已知 front-door ADMG 上恢复真值 ATE 在容差内
- [ ] DoWhy parity 至少 3 个案例
- [ ] 回归保持 889+ 通过

## 5. 后续

完成 7.2 → 7.3 IV numeric（2SLS/Wald/LATE）。
