# RFC：composite confidence 正式语义（v0.2）

**状态**：draft，等 slice 9 开工前定版。

**作用**：为 `themis.runtime.confidence_calc.composite` 从 v0.1 占位（min 规则）升级到 v0.2 正式语义选一条规则并给出实施要求。决策的范围仅限**每条 `QueryResult` 的 composite confidence 字段**；不涉及 Bayesian 后验、置信区间、证据更新等更大话题。

---

## 1. 目标与非目标

### 目标

- 给 Themis 的 `QueryResult.confidence` 一个**一致、可审计、可解释**的正式语义
- 让 `_gather_input_confidences` 有明确的语义要求
- 选定一条规则并把它纳入 v0.2 契约（下一版 scope doc 冻结）

### 非目标

- 不是统计置信区间（不承诺 frequentist 覆盖概率）
- 不是贝叶斯后验（不承诺 P(hypothesis | data) 的语义）
- 不替代 `needs_investigation` 的缺口报告（confidence 不补证据，只描述已接入证据的综合可信度）
- 不引入连续分布假设

---

## 2. "confidence" 在 Themis 里是什么

一个**每条输入附带的、[0,1] 区间的、反映该条输入本身可靠程度**的标量。来源由声明方决定：可以是同行评议、实验重复率、数据采样质量、用户主观判断。Themis 不规定它怎么算出来，只规定它怎么**合成**。

当前 schema 已允许：
- `observation.annotations.confidence`
- `probabilityStatement.annotations.confidence`

Composite confidence 就是：给定一条查询结果，把**所有为这个结果贡献过证据的输入**的 confidence 合并成一个输出标量。

---

## 3. 输入采集（`_gather_input_confidences`）

v0.1 现在返回 `()`。v0.2 需要实打实地收集。按查询类型划分：

| 查询类型 | 证据来源 |
|---|---|
| `cause` | DAG 结构，无 annotation → 空 |
| `assoc` | DAG 结构 + 条件集，无 annotation → 空 |
| `identify` | DAG 结构 → 空（识别本身是纯结构问题） |
| `effect` | 公式引用的**唯一** probability slot 的来源 confidence + 查询实际用到的 observation 的 confidence（见 §3.1 / §3.2） |
| `probability` | 同 effect，但公式更简单（通常就是单条 probability_ref） |

以下两节把 §1 那条"不是模糊的'相关 observation'，而是可审计规则"钉死。

### 3.1 重复来源：按"唯一来源项"合成

**问题**：

1. 公式里同一个 `ProbabilityRefExpr` 可能被多个节点引用（比如后门 + 识别出的同一条件概率被公式里多处使用），不应按节点次数重复计入
2. Theta 里的一个条目可能由**多条**相同 ground 化 `ProbabilityStatement` 语句产生（`theta_builder` 对"同键同值"语句是 idempotent 的），这些语句可以携带**不同的** `annotations.confidence`

**规则**：

对公式里出现过的**每个不同的** `ProbabilityKey` `K`，定义：

```
slot_conf(K) = min(
    stmt.annotations.confidence
    for stmt in ground_probability_statements
    if _key_of(stmt) == K
       and stmt.annotations is not None
       and stmt.annotations.confidence is not None
)
```

- 一个公式节点里**每个 `ProbabilityKey` 只贡献一个 slot**，不按引用次数重复
- 如果同一个 K 对应多条来源语句，**取它们 confidence 的 min**；这保证结果是确定的、可审计的，不给实现留"任取其一"的口子
- 如果 `K` 的所有来源语句都没有 annotation.confidence，则 `K` **不贡献**（不是 0、不是 1、不是 None 占位），换言之"没有意见"就不在合成里发声

### 3.2 Observation 参与条件

**问题**：并非程序里出现的每一条 observation 都和当前查询的答案有关。把无关 observation 也拉进 confidence 合成，等于把"随便写的一条观测"变相加权进用户没问的查询上。

**规则**：只有**同时满足**下面全部条件的 observation 才参与：

1. 该查询的类型属于 `effect` 或 `probability`（结构查询 §3 表格已说不收）
2. 查询的 `given` 列表里存在一项 `ValuedAtom(a, v)`
3. 程序里存在 ground `ObservationStatement(atom=a, value=v)` **且 atom 和 value 都相等**

额外约束：

- 查询的 `intervention` 原子**永远不参与** observation 合成——`do(·)` 切断入边的语义意味着该变量的外部观测值在反事实条件下无意义
- 同一 `(atom, value)` 组合有多条 `ObservationStatement` 时，`slot_conf = min(其 annotations.confidence)`，规则同 §3.1
- 没有匹配任何给定 `(atom, value)` 的 observation 不参与，无论它在程序里是不是存在

### 3.3 最终输入构造

```
inputs = []
for K in distinct ProbabilityKey referenced in formula:
    c = slot_conf(K)  # §3.1
    if c is not None:
        inputs.append(c)

for (atom, value) in q.given:            # only for effect / probability
    c = observation_slot_conf(atom, value)  # §3.2
    if c is not None:
        inputs.append(c)

composite_confidence = composite(*inputs)  # min rule from §7
```

`composite(*())` → None，和 §4 S4 一致。

---

## 4. 选择规则的评估标准

| 标准 | 说明 |
|---|---|
| S1. 顺序无关 | `composite(a, b) = composite(b, a)` |
| S2. 单调 | 增加一条**更弱**的输入，composite 不升 |
| S3. 恒等 | `composite(c) = c` |
| S4. 空输入 → None | 无证据时诚实地说"不知道" |
| S5. 无独立性假设 | 不要求两条输入独立 |
| S6. 可解释性 | 用户看到数值能口头复述它意味着什么 |
| S7. 计算简单 | 不依赖额外模型参数（权重、先验等） |
| S8. Pipeline 友好 | 下游结果的 confidence 能合理继承 |
| S9. 和 v0.1 占位兼容 | 不让 v0.1.0 标过的结果在 v0.2 里数值大幅跳变 |

---

## 5. 候选规则

### A. **Minimum**（v0.1 占位）

```
composite(c1, ..., cn) = min(ci)
```

| 标准 | A |
|---|---|
| S1 顺序无关 | ✅ |
| S2 单调 | ✅ |
| S3 恒等 | ✅ |
| S4 空→None | ✅（drop None 后为空集返回 None）|
| S5 无独立性 | ✅（纯逐项比较）|
| S6 可解释 | ✅（"最弱的一环"）|
| S7 简单 | ✅ |
| S8 pipeline | ✅（二次 min 仍是 min）|
| S9 兼容 | ✅（原样）|

**缺点**：对证据数量不敏感——两条独立弱证据 (0.5, 0.5) 和一条弱证据 (0.5) composite 相同。如果用户希望"多条佐证能提升整体信心"，min 达不到。

### B. **Product**（假设独立）

```
composite(c1, ..., cn) = ∏ ci
```

| 标准 | B |
|---|---|
| S1 | ✅ |
| S2 | ✅ |
| S3 | ✅ |
| S4 | ✅ |
| S5 | ❌（严格需要独立性）|
| S6 | ⚠️（"所有都对的概率"，但这已经是概率解释，和 §1 的立场冲突）|
| S7 | ✅ |
| S8 | ⚠️（pipeline 中每多一步都在乘，很快衰减到接近 0）|
| S9 | ❌（和 min 差别大）|

**缺点**：
- 独立性假设不可验证，用户证据大概率相关
- 衰减太快——10 条 0.9 → 0.35，会让用户觉得"明明都很可信怎么总体这么低"
- 违反 §1 的"不是概率"立场

### C. **Noisy-OR 互补形式**（独立证据合成）

```
composite(c1, ..., cn) = 1 - ∏(1 - ci)
```

| 标准 | C |
|---|---|
| S1 | ✅ |
| S2 | ❌（加弱证据会**升高** composite）|
| S3 | ✅ |
| S4 | ✅ |
| S5 | ❌（独立性）|
| S6 | ⚠️（互补累积概率）|
| S7 | ✅ |
| S8 | ⚠️ |
| S9 | ❌ |

**缺点**：违反 S2 单调性——和我们希望"弱证据不帮你"的语气相反。常用于"至少有一条为真"的场景，**和证据合成相反**。剔除。

### D. **Geometric mean**

```
composite(c1, ..., cn) = (∏ ci)^(1/n)
```

| 标准 | D |
|---|---|
| S1 | ✅ |
| S2 | ✅ |
| S3 | ✅ |
| S4 | ✅ |
| S5 | ✅ |
| S6 | ⚠️（"综合几何平均"对非数学用户不直观）|
| S7 | ✅ |
| S8 | ⚠️（几何平均的几何平均 ≠ 几何平均，合成不可结合）|
| S9 | ⚠️（数值会比 min 高，v0.1.0 → v0.2 会有漂移）|

### E. **Harmonic mean**

类似 D，更偏向 min。比 D 更保守，但可解释性仍偏差。

### F. **Weighted average**

```
composite = Σ wi·ci  /  Σ wi
```

需要权重来源。当前 schema 没有权重语义，引入权重是额外设计。

---

## 6. 对比矩阵

| 规则 | S1 顺序 | S2 单调 | S3 恒等 | S4 空→None | S5 无独立 | S6 可解释 | S7 简单 | S8 pipeline | S9 v0.1 兼容 |
|---|---|---|---|---|---|---|---|---|---|
| A. min | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| B. product | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | ⚠️ | ❌ |
| C. noisy-OR | ✅ | ❌ | ✅ | ✅ | ❌ | ⚠️ | ✅ | ⚠️ | ❌ |
| D. 几何平均 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ |
| E. 调和平均 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ⚠️ | ⚠️ |
| F. 加权均值 | 取决 | 取决 | ✅ | ✅ | ✅ | ⚠️ | ❌ | 取决 | ❌ |

---

## 7. 推荐

**采用 A（min）作为 v0.2 的正式规则**，同时把它从"占位"升级为"已确定语义"。

### 理由

1. **唯一满足所有九条标准**。
2. **和 v0.1.0 已经 ship 的数值兼容**——现有 QueryResult 的 confidence 永远是 None（因为 `_gather_input_confidences` 返回空），所以 v0.2 升级不会让老结果数值变。
3. **诚实**——min 不依赖任何我们无法保证的假设（独立性、可加性、分布）。
4. **易解释**——"最弱的一环决定整体"是用户可以复述的心智模型。
5. **保留扩展空间**——若以后有人希望 noisy-OR 风格的累积奖励，可以通过**声明独立性的语句**（v0.3+）让它成为用户可选项，而不是系统强加。

### 保留问题

- min 对证据数量不敏感——这是**特性**不是 bug。Themis 的立场是：多一条弱证据不能替你把信心提上去；真要提升信心，用户需要提供一条更强的证据或声明独立性。
- 如果用户的两条证据都完全可信（confidence=1），composite=1——这是对的。如果一条 0.9 一条 0.3，composite=0.3——意味着整个链路上存在一个值得警惕的薄弱点，这是我们想要的行为。

---

## 8. 实施要求（slice 9 规格）

### 8.1 代码侧

- `confidence_calc.composite` 正式化：docstring 从"v0.1 placeholder"改成"v0.2 rule: minimum of non-None inputs, None if empty"
- 新增 `_probability_source_index(program) -> dict[ProbabilityKey, tuple[ProbabilityStatement, ...]]`：
  - 遍历 ground statements 一次，把每个 `ProbabilityKey` 映射到**所有**产生它的 source 语句元组（不是任一条）
  - 放在 `runtime/theta_builder.py` 或新 helper 模块；scheduler 按 program 构建一次，传给 explainer 不可见（它只消费最终 confidence）
- 新增 `_observation_source_index(program) -> dict[(Atom, AtomValue), tuple[ObservationStatement, ...]]`：
  - 同样一次遍历，按 `(atom, value)` 组合索引所有 ground 化后的 `ObservationStatement`
- `_gather_input_confidences(program, stmt, result, prob_idx, obs_idx)` 按 §3.3 算法返回 `tuple[float, ...]`：
  - cause / assoc / identify → 返回 `()`
  - effect / probability：
    1. walk `result.formula` 收集**去重后**的 `ProbabilityKey` 集合
    2. 对每个 K，在 `prob_idx` 里找所有来源，取 `min(非 None confidence)`；全 None 则跳过该 slot
    3. 对 `stmt.query.given` 里每个 `ValuedAtom(a, v)`，在 `obs_idx[(a, v)]` 中取 `min(非 None confidence)`；无匹配或全 None 则跳过
    4. 不把 `stmt.query.intervention` 纳入 observation 合成
  - scheduler 在 `dispatch_all` 里构建两个 index 一次，然后逐查询传进来

### 8.2 Schema 侧

- 不变（`annotations.confidence` 已在 `kernel_ast.schema.json` 里存在）

### 8.3 文档侧

- `理论框架_v0_1.md` §10.4 和 `ARCHITECTURE.md` §5.2 / §6 里 "v0.1 占位" 的说法改为 "v0.2 规则"
- 在 `v0_2_priorities.md` 里把 slice 9 的 RFC 项标为已决

### 8.4 测试侧

必须加的回归：

**单元层（`test_confidence_calc.py`）**：
- `composite` 在九条标准上逐一断言（S1–S9 每条一个测试）

**采集层（新 `test_gather_input_confidences.py`）**：
- cause / assoc / identify 查询永远返回 `()`
- effect 查询：公式里同一 ProbabilityRefExpr 在多节点出现时，只贡献一个 slot（不按引用次数重复）
- §3.1 重复来源：同一 `(target, value, given)` 由两条同键同值语句产生且 confidence 分别为 0.9 和 0.3 时，`slot_conf` 取 0.3
- §3.1 全无 annotation：该 slot 不出现在 inputs 里，而不是作为 None / 0 / 1 占位
- §3.2 observation 匹配：`given=[Z=true]` + `ObservationStatement(Z, value=true, confidence=0.8)` → 参与；`ObservationStatement(Z, value=false, confidence=0.8)` → 不参与
- §3.2 observation 的 atom 不在 given 里 → 不参与，即使程序里有这条 observation
- §3.2 intervention 原子永不参与：`do(X=x)` + `ObservationStatement(X, x, confidence=0.8)` → 不参与

**端到端**：
- `numeric_backdoor.json` 的所有 probability 语句加 `annotations.confidence=0.9`，期望 `QueryResult.confidence == 0.9`
- 改成一条 0.9、一条 0.3，期望 `0.3`
- 去掉所有 annotation，期望 `confidence is None`（兼容 v0.1.0）

### 8.5 破坏性评估

- **非破坏性**：现有 QueryResult.confidence = None 的结果在 v0.2 仍会是 None，除非 fixture 显式加了 annotation
- **向前兼容**：现有 schema 无变化，新增的只是 runtime 的合成行为

---

## 9. 一句话

```
v0.2 composite confidence = min(收集到的非 None 输入 confidence)，空则 None。
不是概率、不是后验、不假设独立性；它是诚实的"最弱链路"评分。
```

---

## 10. 决策记录

- **提出日期**：2026-04-20
- **状态**：draft，等 slice 9 开工前由用户 sign-off
- **备选轨道**：如果未来 v0.3 引入"独立证据"声明，noisy-OR 可以作为用户**opt-in** 的合成规则加入；不会替代 min 作为默认

### 修订记录

- 2026-04-20 首版 draft
- 2026-04-20 §3 拆分为 §3.1 / §3.2 / §3.3，把"重复来源 → slot min"和"observation 参与条件"的规则钉死；§8.1 / §8.4 同步收紧
