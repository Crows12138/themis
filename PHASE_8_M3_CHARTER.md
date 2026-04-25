# Phase 8 (M3) Charter — 因果发现 + 敏感性分析

> 立项日期：2026-04-25
> 状态：**已批准** — 开工 8.1
> 前置：M1 (识别) + M2 (估计) 全部落地
> 对应 VISION：板块 10（敏感性）+ 板块 12（因果发现）

## 0. Scope

到目前为止 Themis 假设**用户给定 DAG**。Phase 8 解决"图从哪来"
（discovery）和"图错了怎么办"（sensitivity）。

**8.1 因果发现**（板块 12，0% → ~40%）
- 包装 causal-learn 的 PC + FCI + LiNGAM 三个算法作 production backend
- 输入数据 → 输出建议的 DAG / CPDAG / ADMG
- 用户可以接受 / 修改 / 拒绝建议图，再传给识别 + 估计

**8.2 敏感性分析**（板块 10，0% → ~30%）
- E-value（VanderWeele 2017）：一个公式，告诉用户"未观测混杂要多强才
  能解释掉这个估计"
- Rosenbaum bounds（可选）：观察性研究的稳健性下界
- 用法：在已得到 numeric_estimate 后，问 "假设违反到什么程度，结论翻
  转？"

**8.3 Shpitser 完整 ID**（可选 / 推迟）
- 完整识别算法，覆盖所有可识别图
- 真实压力出现再做，按需启动

## 1. 战略定位

到 Phase 7 为止，Themis 的能力链是：
```
NL → 用户给图 → 识别 → 估计 → 数字 + CI
```

Phase 8 闭环：
```
NL + 数据 → 发现图（建议）→ 识别 → 估计 → 敏感性分析 → 鲁棒结论
```

最大用户价值：**用户不再需要自己懂图论才能用因果系统**。

## 2. 5 条 API 允许规则审计

### 8.1 causal-learn（PC + FCI + LiNGAM）

- ✅ 确定性纯变换（同数据同 hyperparameters 同输出）
- ✅ track record：基于 Tetrad 算法，causal-learn 4+ 年（接近 5 年门
  槛但不到；活跃维护，Sun 实验室持续投入）
- ✅ pin 版本（已装 0.1.4.5）
- ✅ parity test 可对 R 的 pcalg
- ✅ 输出可嵌入 derivation（adjacency matrix + edges list）

**结论**：可作 production backend，**但要写 wrapper 解释 PC vs FCI 的
适用条件**——用户必须知道 PC 假设无潜变量、FCI 容许潜变量。

### 8.2 E-value / Rosenbaum bounds

- 公式简单（E-value 是 closed form），自写不需要外部库
- 不涉及训练 / 随机性 / 优化器
- 直接 production

## 3. Slice 计划

- **8.1.1** discovery 原语 wrapper（PC / FCI / LiNGAM）
- **8.1.2** discovery → kernel_ast suggestion（输出 LLM 友好的图建议）
- **8.1.3** schema + verifier 松弛审（discovered_graph_suggestion）
- **8.1.4** A1 prompt v2.4：当用户给数据但没图时，调用 discovery
- **8.1.5** eval case 28（无图建图）+ parity vs causal-learn ground truth

- **8.2.1** E-value 公式实现 + 单元测试
- **8.2.2** dispatch 集成：所有 numeric_estimate 自动附 E-value
- **8.2.3** schema 扩展（sensitivity_analysis 子字段）
- **8.2.4** A1 v2.5 + response_rendering 解释 E-value
- **8.2.5** eval case 29（敏感性回答）

每个子 slice 1-2 天。**总预估**：8.1 约 4-5 天，8.2 约 2-3 天。

## 4. 不做的（明确推迟）

- NOTEARS / DAG-GNN / RL-discovery（连续优化方法）
- TMLE / DML 全套（研究级估计需统计专家审）
- Bayesian 因果模型（先验选择是非结构问题）
- 选择偏差 (selection bias) 数值估计
- 测量误差校正

## 5. 完成条件

- [ ] 8.1 落地：PC/FCI/LiNGAM 三个算法可调，产出格式与 kernel_ast
      兼容
- [ ] 8.2 落地：每个 numeric_estimate 自动带 E-value
- [ ] COVERAGE 板块 10 + 12 显著上升
- [ ] 总测试 944 不降

## 6. 后续

完成 Phase 8 后整体覆盖率约 55-65%，VISION 12 板块的"硬骨头"主要剩
反事实（Layer 3 全套）+ 时序 g-methods，进 Phase 9+ 按需。
