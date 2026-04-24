# Phase 7 (M2) Charter — 数值估计层

> 立项日期：2026-04-24
> 状态：**已批准（2026-04-24）**—— 开工 Phase 7.1
> 关键决策确认：
> - Q1 数据契约：Python API（不污染 JSON）
> - Q2 Imai 非参：**vendor statsmodels 0.14.6**（已验证 5 条 API 允许规则全通过；statsmodels.stats.mediation 内置 Imai 2010 算法 1+2，15+ 年稳定）
> 对应 ROADMAP：M2 数值估计层，紧跟 M1 识别层完整化
> 对应 VISION：扩展愿景——板块 11（连续 / 数据驱动估计），L1 + L2
> 覆盖目标
> 前置依赖：M1 识别层已完整（backdoor / front-door / IV / mediation）

## 0. 立项条件

Phase 7 开工的前提**已全部满足**：

- ✅ 识别层 4 条路径（backdoor / front-door 单+多 / IV basic+conditional
  / NDE-NIE-CDE）都能给出"这个量可以识别 + 用什么公式"
- ✅ 每条路径都有独立 verifier + schema 严格约束
- ✅ eval set 20+ 个 case 覆盖各识别路径
- ✅ Phase 6.mediation 压测通过（NL 层不是阻塞）

**识别层不再是瓶颈**——接下来的价值在**"能不能给数字"**。

## 1. 动机

### 1.1 战略定位

VISION.md 扩展愿景：板块 11（连续 / 数据驱动估计）当前 **0%**。Phase
7 M2 把它提到 **L1 完整（~30%）+ L2 核心场景（~20%）**，合计约 50%
覆盖。

### 1.2 真实用户场景

到目前为止，Themis 只能回答：
- "这个因果量**能不能**识别？" ✓
- "如果能识别，**公式**是什么？" ✓
- "给我**填入** P(Y|X, Z) 的具体数值" → 用户手工填 Theta，繁琐

用户真正想问：
- "我有数据集，**帮我算** ATE / NDE / LATE" ← Phase 7 要解锁

### 1.3 理论固化度

估计层比识别层"脏"得多——每种估计器都有适用条件、鲁棒性、
有限样本表现等。本 Phase 只做**成熟的、有明确理论保证**的估计器：

- 参数化（linear / logistic）：Neyman / Rubin 教科书
- 半参数（IPW / AIPW）：Robins 1994
- 机器学习（Causal Forest 简化版）：可选，留 7.4

**不做**研究级方法（TMLE / DML full 版 / deep causal）——需要真实统
计专家审。

### 1.4 和现有开源生态的差异化

裸用 sklearn / statsmodels / DoWhy / EconML 可以算数值。Themis 的增
量价值：

1. **识别公式驱动估计**：识别层说要算 `Σ_z P(Y|X,z) P(z)`，估计层
   直接照公式实现——不会误用调整集
2. **Verifier 可审**：每一步 fit / predict 都在 derivation 里，带
   训练数据的 hash，结果可复现
3. **NL-native**：用户自然语言说"帮我估"→ 直接出数字 + CI + 敏感
   性警告
4. **ambiguity surfacing**：功能形式假设（linear vs logistic vs
   non-parametric）显式选或 default + 标注

---

## 2. Scope

Phase 7 M2 包含 4 个 slice，按依赖顺序：

### 7.1 — Data ingress + backdoor numeric（必做）

解决"数据进来 + 简单的 backdoor ATE 估计"最小可用场景。

- 新 API `themis.estimate(kernel_ast, data)`（不污染 JSON，数据走
  Python 接口）
- 支持 pandas DataFrame / dict-of-lists / numpy 结构
- Estimator for backdoor: sklearn LogisticRegression (binary) or
  LinearRegression (continuous) for E[Y|X, Z]; outer average over
  P(Z)
- 结果：QueryResult 新增 `numeric_estimate` 字段 {point, ci_lower,
  ci_upper, method, assumptions}
- 7 个 S 切片（S.N.1 – S.N.7）：数据契约 → 估计器 → scheduler 集
  成 → verifier → schema → eval case → parity

### 7.2 — Front-door numeric

扩展 `front_door_formula` 的数值版——fit P(M|X), P(Y|M,X)，按公式
合成。复用 7.1 的数据契约。

### 7.3 — IV numeric

2SLS（linear）+ Wald（binary）+ LATE（monotonicity 下）三种估计器。
标注 "chosen assumption" 到 extensions。

### 7.4 — Mediation numeric

product-of-coefficients（linear）+ Imai 非参（kernel-based）。CDE
via g-formula。NDE/NIE 只在可识别图上给（M4 违反直接 fall back
到 CDE + warning）。

---

## 3. 语义 / 语言扩展

### 3.1 新 statement kind？

**倾向不新增**。数据通过 Python API 注入：

```python
import themis
data = pd.read_csv("my_data.csv")
result = themis.estimate(kernel_ast_dict, data)
```

JSON 层不变——这保持 kernel 的"JSON-in / JSON-out"契约（识别部
分），数据层通过 Python 旁路。

### 3.2 QueryResult 扩展

```
result.numeric_estimate: {
  point: float,
  ci_lower: float | null,
  ci_upper: float | null,
  ci_level: float,                # 0.95 default
  method: string,                 # "backdoor_logistic" | "2sls" | ...
  assumptions: [string, ...],     # chosen functional form assumptions
  sample_size: int,
  data_hash: string,              # for verifier to pin reproducibility
}
```

### 3.3 Verifier 扩展

新 rule family `numeric_estimate_*`：
- `numeric_fit_model`: 记录用哪个 estimator 在哪个数据子集上拟合
- `numeric_predict_avg`: 外层 expectation（Σ_z P(Y|X,z)·P(z)）
- `identify_via_numeric_backdoor`: 聚合器

Verifier **不重新训练**（训练可能贵/有随机性）——只检查：
- data_hash 匹配
- formula 和 estimator 的组合合法
- point 在 [ci_lower, ci_upper] 内
- method 字符串在允许枚举里

这是对识别层验证的松弛版：全量复现 numerically 不现实，只做"结构
/ 元数据 / 边界"审。

### 3.4 确定性 vs 随机性

估计层**必然**引入随机性（train/test split, bootstrap CI, optimizer
seed）。所以默认 estimator 必须支持 **deterministic seed**——每次
run 同数据同 seed 输出相同 point + CI。

---

## 4. 不做的

- **Deep learning 估计器**（VAE-based counterfactual, neural TMLE）
- **连续时间 / 动态随机过程**估计
- **自动机器学习**（AutoML for causal）
- **协方差 estimator**（causal discovery 的 PC/FCI etc.）——Phase 8
- **研究级半参**（TMLE full / DML full）——需要真统计审
- **多尺度** / **层级模型**（hierarchical / multi-level）
- **贝叶斯估计**（先验选择是非结构问题）

---

## 5. 开源参考（按 5 条 API 允许规则）

按 CLAUDE.md 的"做大块代码先查开源"原则：

| Slice | 参考 | 使用方式 |
|---|---|---|
| 7.1 backdoor | sklearn LinearRegression / LogisticRegression | **vendor / 直接依赖**（sklearn 5+ 年稳定）|
| 7.1 backdoor | DoWhy estimate_effect | **parity calibration**（不 production 接入）|
| 7.2 front-door | 自写公式 + sklearn 基础估计器 | production |
| 7.3 IV | linearmodels.iv.IV2SLS | **vendor 候选**（需评估稳定性）|
| 7.3 IV | DoWhy IVEstimator | parity only |
| 7.4 mediation (linear) | 自写（几十行教科书公式）| production |
| 7.4 mediation (Imai 非参)| **statsmodels.stats.mediation** | **vendor / production backend** |
| 7.4 mediation | DoWhy LinearRegressionEstimator mediation | parity only |

**5 条 API 允许规则**（参考 VISION.md / feedback_reference_open_source）：
- sklearn ✅（确定性 + 5+ 年稳定 + pin 版本 + parity test 可行）
- linearmodels 需评估（3 年稳定 track record，要升级频率评估）
- DoWhy/EconML 只作 dev-only parity，不作 production backend

---

## 6. 完成条件

Phase 7 (M2) 完成的硬指标：

- [ ] 7.1 落地：backdoor numeric 端到端 + 15 单元测试 + 5 集成 + 5
  parity
- [ ] 7.2 落地：front-door numeric 端到端
- [ ] 7.3 落地：IV numeric（至少 2SLS 和 Wald 两种）
- [ ] 7.4 落地：mediation numeric（至少 CDE 可数值化；NDE/NIE 线性
  版可选）
- [ ] COVERAGE_MAP 板块 11 0% → ~50%
- [ ] A1 prompt 可选 v2.4 §4 "When user has data"（可选）
- [ ] 回归：每 slice 落地不破已有 831 pass / 143 skip

---

## 7. 时间预估

- 7.1 backdoor: 2-3 天（数据契约 + estimator + verifier + parity）
- 7.2 front-door: 1-2 天（复用 7.1 的大部分）
- 7.3 IV: 2-3 天（2SLS / Wald / LATE + verifier）
- 7.4 mediation: 2-3 天（product-of-coefs + Imai Python 重实现）

总计 **7-11 天**实际落地。比 Phase 6 整体（已花 ~2 天）更重——
识别 >> 估计 在复杂度上，但估计更"脏"、更多 edge cases。

---

## 8. 非目标 / 明确推迟

- Phase 7.5（可选）：Causal Forest Python 简化版
- Phase 7.6（可选）：TMLE 基础版
- Phase 8 M3：敏感性分析 + 因果发现
- Phase 9+：按需扩展

---

## 9. 后续 slice 启动顺序

完成本 charter → 正式开工：

1. **先立 PHASE_7_1_BACKDOOR_NUMERIC_CHARTER.md**（子 charter，
   镜像 6.iv/6.mediation 粒度）
2. S.N.1: 数据契约 + `themis.estimate` API
3. S.N.2: backdoor numeric estimator
4. S.N.3: scheduler 集成
5. S.N.4: verifier rules
6. S.N.5: schema 扩展
7. S.N.6: eval cases（有数据的 case）
8. S.N.7: DoWhy parity

完成 7.1 → 7.2 follows → 7.3 → 7.4 → Phase 7 收工。
