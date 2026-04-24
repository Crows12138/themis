# Phase 7.1 Charter — Backdoor 数值估计 + 数据契约

> 立项日期：2026-04-24
> 状态：**✅ 已落地（2026-04-24）** — S.N.1 – S.N.7 全部完成
> 父 charter：PHASE_7_M2_CHARTER.md
> 目标：打通"数据进来 → backdoor-adjusted ATE 出来"最小闭环
>
> **落地 commit**: 3935b81 (S.N.1) → 6059ed8 (S.N.2) → a42129b (S.N.3)
> → a31bd7e (S.N.4 + partial S.N.5)

## 0. Scope

本 slice 是 Phase 7 的 **入门 slice**——引入整个 Phase 7 的数据契约
+ 第一个估计器。后续 7.2 / 7.3 / 7.4 复用本 slice 的数据契约，只
换估计器。

**必须包含**：
- 数据通过 Python API 注入（`themis.estimate(ast, data)`）
- backdoor 调整的 ATE 估计（二值 X + bool/连续 Y）
- sklearn LogisticRegression / LinearRegression 两个 backend
- 点估计 + bootstrap CI
- deterministic seed
- verifier 松弛审（元数据 + 边界）
- schema 扩展 + eval case + parity

**不包含**：
- front-door / IV / mediation（后续 slice）
- ATE 以外的估计量（CATE / ITE → Phase 8+）
- Doubly-robust / AIPW（Phase 7 可选扩展）
- 连续 X（二值 X only for 首版）

## 1. 数据契约

新 API：

```python
import themis
import pandas as pd

ast = {...}                              # 原有 kernel_ast dict
data = pd.read_csv("patients.csv")       # 列名 = ast 里的 predicate
result = themis.estimate(ast, data)      # -> dict 同 themis.run 格式 + numeric_estimate
```

**数据约定**：
- 列名 = ast 的 predicate 名（`running`, `weight_loss` 等）
- bool 列：True/False 或 0/1
- 连续列：float
- 不允许缺失值（首版）—— 缺失报错 `DataContractError`
- 至少 30 行 —— 样本数 < 30 报 warning，<10 拒绝估计

**data_hash**：对规范化后的数据算 SHA-256，嵌入 `numeric_estimate.data_hash`
供 verifier 审复现性。

## 2. Estimator API

新模块 `themis.estimation.backdoor`:

```python
def estimate_backdoor_ate(
    data: pd.DataFrame,
    treatment: str,             # predicate name
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    model: str = "auto",        # "linear" | "logistic" | "auto"
    ci_bootstrap: int = 500,    # 0 = no CI
    random_state: int = 42,
) -> BackdoorEstimate:
    """Compute E[Y|do(X=1)] - E[Y|do(X=0)] via backdoor adjustment."""
```

`BackdoorEstimate` NamedTuple: point / ci_lower / ci_upper / method /
assumptions / sample_size / data_hash

Auto 模式：outcome 是 bool → logistic；是 float → linear。用户也可
显式指定。

## 3. QueryResult 扩展

```
result.numeric_estimate: {
  point: float,
  ci_lower: float | null,
  ci_upper: float | null,
  ci_level: 0.95,
  method: string,       # "backdoor_logistic" | "backdoor_linear"
  assumptions: [string, ...],
  sample_size: int,
  data_hash: string,
}
```

`status` 用现有的 `numerically_solved`（沿用 effect query 的语义）。

## 4. Verifier

新 rule：`numeric_backdoor_estimate`

Input: adjustment set, treatment, outcome, method, data_hash, point, CI
Check:
- adjustment set matches the identify-step's witness
- method enum 合法（`backdoor_logistic` / `backdoor_linear`）
- point 在 [ci_lower, ci_upper] 内（若 CI 存在）
- data_hash 是有效 SHA-256 十六进制
- sample_size >= 30

Verifier **不重新训练**——估计层引入的随机性（bootstrap / seed）让
bit-for-bit 复现代价过高。

## 5. S 切片

- **S.N.1**：数据契约 + `themis.estimate` API 骨架（2-4 小时）
  - `themis.estimation.contract.DataContract` 验证 shape / dtypes /
    missing
  - `themis.estimate(ast, data)` dispatch 骨架（未估计，返回 skeleton）
  - 10 单元测试覆盖契约验证

- **S.N.2**：`estimate_backdoor_ate` 实现（4-6 小时）
  - sklearn LogisticRegression / LinearRegression wrapper
  - 点估计：fit P(Y|X,Z) → 计算 Σ_z [Ê(Y|X=1,z) - Ê(Y|X=0,z)] · P̂(z)
  - Bootstrap CI（500 iter default）
  - 12 单元测试（linear / logistic / empty adj / edge cases）

- **S.N.3**：scheduler 集成（2-4 小时）
  - `themis.kernel._estimate_dispatch` 在 effect query + data 提供
    下调用 `estimate_backdoor_ate`
  - 复用 M1 识别的结果（adjustment set 来自已跑的 identify），
    不重复识别
  - 6 集成测试

- **S.N.4**：verifier rule `numeric_backdoor_estimate`（2-3 小时）
  - 松弛审（见 §4）
  - byte-code 独立性钉

- **S.N.5**：schema 扩展 `query_result.schema.json.extensions` +
  `numeric_estimate` 顶层字段（1-2 小时）
  - 新字段严格 JSONSchema
  - 现有 numerically_solved 语义复用

- **S.N.6**：eval case + 综合测试（2-4 小时）
  - 新 case 25：有数据的 backdoor 估计真实案例
  - 合成数据 fixture（deterministic）

- **S.N.7**：DoWhy parity（2-3 小时）
  - 对 3-5 个合成数据集跑 Themis vs DoWhy，对比点估计 ≤ 容差
    （eg. 5% 或绝对 0.05）
  - 不对 CI 做严格对比（bootstrap 实现不同）

**总预估**：16-26 小时，约 **2-3 天**实际落地。

## 6. 完成条件

- [ ] 7 个 S 切片全部合并
- [ ] `themis.estimate(ast, data)` 是新顶层 API，可以从 README 直接
      引用
- [ ] 全套回归从 831 pass 不降
- [ ] COVERAGE_MAP 板块 11 0% → ~15%（只是 L1 backdoor）
- [ ] CORE_STATUS 加 Phase 7 section

## 7. 后续 slice 钩子

7.1 完成后可直接启 7.2 front-door numeric（复用 S.N.1 数据契约 +
S.N.3 的 estimate dispatch 模式）。
