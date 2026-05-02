# Phase 14 Charter — Dose-Response Estimator

> 立项日期：2026-04-28
> 状态：**slice a / b / c / b.2 + followups 已落地** (2026-04-28)
> 触发：用户在讨论 Phase 13 时提出"我们也可以做"——意思是既然 Themis
> 已经有 `themis.estimate(prog, df)` 这条 estimator 腿（Phase 7 起接
> sklearn/doubleml），把 dose-response 加入是合理延伸。
> 但这等于把 Themis 从 "validator+diagnostician" 升级为
> **"validator+estimator"**，定位变化要 charter 写明、要决心。

> 历史门槛：Phase 13 (诊断) 已完成并把 dose-response 数据规格打通；
> Phase 14 已在此基础上把 `themis.estimate(...)` 扩到 dose-response
> curve。下文保留立项时的边界与踩坑记录。

---

## 0. 定位变化（要先确认）

Themis 当前公开三个 entry point：
- `themis.run(prog)` — pure symbolic, no IO
- `themis.estimate(prog, df)` — 接 DataFrame，**已 import sklearn/doubleml**
- `themis.verify(prog, result)` — 独立审计

`estimate` 已经在做"binary 干预的 ATE"。Phase 14 = 把同一条腿扩到
"binary/连续干预的剂量响应曲线 + CATE"。

**架构上**：不破坏 audit chain（program-side 仍纯 symbolic），但
**用户画像扩大**——Themis 现在能直接产出曲线，不只产出诊断。

## 1. 范围（草拟）

### 1.1 必须做

- `themis.estimate(prog, df)` 当 query 含 `dose_response_query`
  ambiguity 时，**自动**走 dose-response 估计路径（不强制用户传额外参数）
- 后端：包 EconML 的 `LinearDML.const_marginal_effect` 或
  `CausalForestDML`；defaults 由 prog 的 backdoor 调整集决定
- 输出：`NumericResult` 加 `dose_response_curve` 字段（采样点 + 边际
  效应数组 + CI）
- 自动 cross-fit 与 sandwich SE

### 1.2 应该做

- `themis.estimate` 失败时返回结构化错误（数据缺列 / overlap 不足 /
  模型收敛失败），不抛裸 exception
- 接 Phase 13 的 sampling_points 建议作为 dose-response 评估点

### 1.3 不做

- 自动 hyperparameter 搜索
- DML / DRL / Targeted Learning 多家估计器自动选择
- 跨多个 outcome 联合 dose-response

## 2. 待立项时再写

完整 sub-slices / 估时 / review checklist 等 Phase 13 done + 真痛证据
出现后再扩展本文件。

**估时草估：2-3 天**（estimator 接入 + 序列化 + 测试 + 文档）。

## 已落地：slice a（2026-04-28）

最小可证路径已通：

- `themis/estimation/dose_response.py` — `estimate_dose_response()` 包
  EconML 的 `LinearDML`，输出 `DoseResponseEstimate(curve=...)`
- `themis/estimation/dispatch.py` — 当 program 携带
  `dose_response_query` ambiguity 且 backdoor 可识别时，自动路由到
  dose-response estimator；任何缺路径都 fallback 到 binary
- `themis.estimate(prog, df)` → `numeric_estimate.dose_response_curve =
  [{x, effect, ci_lower, ci_upper}, ...]`，`reference_point` 为最小
  采样点（effect=0）
- 采样点优先用 treatment variable 的 declared numeric domain；缺时退
  回 [10, 25, 50, 75, 90] 分位
- EconML lazy import；缺包返回结构化 `estimator_dependency_missing`
  block 而不抛 traceback
- `tests/test_estimation_dose_response.py` — 7 tests，6 个
  `skipif(not _ECONML_AVAILABLE)`，1 个 dependency-missing 路径

**slice a 的硬限制**（应该等真用过再决定要不要做 b/c）：

- LinearDML 的 PLM 假设 → 预测曲线必为直线（已写进
  `assumptions`）。真有非线性时 caller 要自己换 estimator
- 没接 CausalForestDML / GAM
- 没用 cross-fit 的 sandwich SE（用 EconML 默认）
- schema 没更新——`dose_response_curve` 当前是 free-form dict 字段，正式
  入 schema 等真有外部 consumer 再做（problem 3 = "先 dict 凑合"）

## 已落地：slice b（2026-04-28）

- `model='auto'|'linear'|'forest'` kwarg；'auto' 在 n ≥ 200 时选 forest
- CausalForestDML 作为可选 backend（nuisance 阶段非参数）
- assumption 文本如实声明 forest **不能恢复 T-Y 非线性**（CausalForestDML
  在 X 上做异质，对 T 仍线性 — 这是踩坑后改正的）

**slice b 学到的事**：CausalForestDML 给的是"按 X 的异质效应"，不是
"T-Y 非线性曲线"。要真正非线性 dose-response 必须 DRLearner +
T 离散化（或 SparseLinearDML + poly features）。这是 slice b.2 / 未来
工作，不在本次范围。

## 已落地：slice c（2026-04-28）

- `EstimatorFailure(failure_type, message, **details)` 异常类型
- pre-fit overlap check：每个采样点 ±10% T-range 内必须有 ≥5 观测，否
  则 `failure_type='overlap_insufficient'` + `details.sparse_points`
- 数值收敛失败（LinAlgError / FloatingPointError）→
  `failure_type='convergence_failure'`
- dispatch 的 `estimator_failure` block 一律带 `failure_type` 和（可选）
  `details` 字段，caller 不需要解析 reason 字符串

## slice c 没做（charter 1.2 剩余）

- 接 Phase 13 的 `sampling_point_count = K` 自定义值
  （目前 K 固定 = `_DEFAULT_QUANTILES` 的 5 点；想改要传 sampling_points
  kwarg 或在 variable.domain 里写）
- 缺列/dtype 错误的细分（contract.DataContractError 在 estimate 入口
  之外抛 — 要改需要包 estimate_program 顶层）

## 已落地：slice b.2（2026-04-28）

- `model='drlearner'` — LinearDRLearner + T 按相邻采样点中点离散化为 K
  个 bin；每 bin 用 doubly-robust 估计相对参考 bin 的平均效应
- **真正能恢复 T-Y 非线性**（concave / convex / 任意单调或非单调形状）：
  test 验证了 y = 1 + 0.4·T - 0.03·T² 的 concave-down 峰值能被检测到
- `model='auto'` 改为：n ≥ 200 且 ≥ 3 采样点 → drlearner，否则 linear。
  forest 不再是 auto 候选（它不解决 T 非线性问题，留作 explicit opt-in）
- drlearner 自带 overlap check：每 bin 必须 ≥ 5 观测，否则
  `failure_type='overlap_insufficient'` 携带 `sparse_bins`/`bin_counts`
  详情

## 已落地：hardening A/B（2026-05-02）

这轮不是扩 estimator 能力，而是收紧已有 dose-response 行为边界：

- A1：constant-outcome guard 从绝对阈值改成 `std/scale` 与
  `range/scale` 相对阈值，避免正常量纲下近似常数 outcome 漏过 pre-fit
  检查后产出伪曲线。
- A2：program-level `dose_response_query` 不再被第一个 mediation effect
  query 静默吞掉；无显式 `query_id` 时路由到第一个非 mediation effect
  query，并把跳过行为写入 `data_contract_warnings`。
- A3：显式 `query_id` 指向不存在的 query 时，不再静默丢弃；估计输出
  保持普通 effect 路径，同时写入 `data_contract_warnings`。
- A5：dose-response estimator 内部失败继续抛 `EstimatorFailure`，dispatch
  统一转成结构化 `estimator_failure`，不回到旧的 silent fallback 语义。
- B2：只有 `dose_response_query` ambiguity 但没有 effect query 时，输出
  `data_contract_warnings`，并保留 run 层的 `dose_response_data_required`
  gap，避免用户误以为 estimator 已处理。
- B3：boolean treatment 命中 `dose_response_query` 时，不再生成未标记的
  两点曲线；显式 fallback 到 binary effect，并记录 `estimator_fallback`。

## 3. 触发条件（历史）与当前状态

原始触发条件：

- Phase 13 真测后，subagent / 真用户**实际使用 dose-response 数据
  清单后**说"清单很对，但是我没工具跑"
- 至少 3 个独立来源的"我有数据但跑不了"反馈
- 用户决心从 validator+diagnostician 升级为 validator+estimator

当前已经开工并落地到 b.2：Themis 现在确实包含 estimator 腿。后续如果
继续扩，应按真实数据压力单独立项，而不是继续在本 charter 里累加：

- CATE / ITE
- 自动 hyperparameter search
- 多 outcome dose-response
- 更强 overlap / positivity diagnostics
- 估计层 verifier 深化
