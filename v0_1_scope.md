# v0.1 能力与边界

> **当前版本指针**：本文件固化的是 v0.1 的能力边界（标题"v0.1"已显
> 标）。系统现已演化到 0.15.0-dev——本文件的"v0.2 或更后"中很多项
> 已经实际落地（front-door / IV / mediation / transport / counterfactual
> bounds / dose-response 估计 / data-gap report / KB adapter contract /
> MCP wrapper / 等），详见
> [`CORE_STATUS.md`](CORE_STATUS.md) 与
> [`COVERAGE_MAP.md`](COVERAGE_MAP.md)。本文件保留作为 v0.1 scope 的
> 历史快照——"v0.1 这个查询能不能答"的 single-point query 仍准确，
> 但要回答"系统当前能不能答"请看 CORE_STATUS。

本文件固化 Themis v0.1 的**语言和实现契约**。

把"已完成 / 占位 / 明确不支持"写死的目的：

1. 防止 v0.1 内部的范围蔓延——没在这里列出的能力，**一律属于 v0.2 或更后**
2. 给任何读者一个单点查询——"这个查询在 v0.1 能答吗？能答到什么层级？"
3. 给未来的自己一份免责清单——占位语义和延后能力不是 bug，是 scope 边界

v0.1 → v0.2 的跃迁必须显式声明并走版本号，不能隐式漂移。

---

## ✅ 已完成（stable、可依赖）

### 语言与语义

- 有限对象域 + 关系级谓词
- 四类模型对象：`cause` / `probability` / `observation` / `query`
- 一类查询内嵌操作：`do(·)`（只出现在 effect / identify 查询里）
- 五种查询：`cause` / `assoc` / `effect` / `identify` / `probability`
- 四态结果协议：`structurally_solved` / `numerically_solved` / `needs_investigation` / `outside_language`
- Ground atom / patterned atom 的严格分工：查询和观测必须 ground；模型语句可带 `forall`
- 概率语句语义：`G ⊆ parents(T)`；违反即语义错
- 静态模型：v0.1 不处理时间、动作序列

### 输入层

- JSON parser
- JSON Schema 校验（跨文件 $ref：`atom` / `kernel_ast` / `query_result`）
- 两阶段语义校验：
  - **pre-graph**：`objects` / `forall_usage` / `bound_variables` / `ground_observations` / `ground_queries`
  - **post-graph**：`probability_parents` / `query_atoms_in_V`
- 公式良构校验工具：`validate_formula`（绑定检查 + `sum.over` ground）

### 运行时层

- `forall` 在对象域上实例化；`ValuedAtom` 只替换 atom 部分、保留具体值
- 图投影 + DAG 不变量强制（循环输入直接报错，附循环列表）
- 结构求解器：
  - 有向路径存在性 + 枚举
  - d-separation（链 / 叉 / 碰撞点，后代激活）
  - 开放路径枚举
  - 后门路径枚举
  - 最小后门调整集（非递增 size + 真子集剪枝；支持 `given` 上下文）
- 公式构造器：任意 cardinality 的后门公式，多变量时链式法则嵌套 sum
- Theta 构建：
  - ground probability 语句 → `ProbabilityKey` 条目
  - 冲突键（同 key 不同值）硬报错
  - 值域从语句中出现的 value 自动推断；未出现的 atom 退回布尔默认
- 数值评估器：
  - 递归求值 `constant` / `probability_ref` / `product` / `sum`
  - VarRef 按 sum 绑定代入
  - 缺条目抛 `InsufficientTheta` 携带精确 `ProbabilityKey`
- 四态调度器：所有 in-language 查询必有结果；未实现路径显式 `needs_investigation` 而非静默丢
- 调查请求自动推送：`MissingKind → InvestigationAction` 映射；每条 `needs_investigation` 带对应 request
- 干预语义：`do(X=v)` 切断指向 X 的入边，X 固定为 v

### Oracle 层

- pgmpy 适配器：d-connectivity、后门调整集枚举
- 差分比对器：cause / assoc / identify 三态对比（agree / disagree / not_applicable）
- pgmpy 1.1.0 空调整集怪癖显式补齐

### 输出层

- `QueryResult → dict` 序列化，经 `query_result.schema.json` 往返校验
- 中文解释器：cause / assoc / identify 三类查询有文字输出

### 公式子语言（formula AST）

- 算子集：`constant` / `probability_ref` / `product` / `sum`
- 绑定语义：`sum.bind.name` 新引入变量，body 内通过 `VarRef` 引用
- `sum.over` 必须 ground（validator 级软约束）
- `probability_ref.target` / `given` 可携带字面值、`VarRef` 或 None（查询绑定）
- 无自由值变量；查询上下文原子豁免自由性判定
- 公式中永远不出现 `do`（识别语义上 do 被消掉）

---

## ⚠️ 占位（存在但语义未定，v0.2 会重写）

### confidence_calc

- 当前规则：`composite(*inputs) = min(非 None)`
- 调用链**已接通**：每条 `QueryResult` 出口都经过 `_attach_confidence`
- `_gather_input_confidences(program, stmt, result)` 永远返回 `()`——输入收集是延后项
- 所以实际上 `QueryResult.confidence` 在 v0.1 总是 `None`，但不是死代码
- v0.2 会：
  1. 正式定义 composite 规则（Dempster-Shafer？加权？证据推理？——待选）
  2. 实现 `_gather_input_confidences`，walk 公式和相关 probability / observation 的 annotations

---

## ⛔ 明确不支持（v0.1 外，v0.2+ 考虑）

### 识别算法层面

- **完备 ID 算法**（Shpitser-Pearl）：v0.1 只有后门准则。调整集不存在时直接 `structurally_solved: false`，不尝试前门 / do-calculus 三规则
- **前门准则**
- **双向边 / 潜变量 / 不可观测混杂**
- **工具变量识别**
- ananke 对照：oracle 目录保留 stub 文件，v0.2 启用

### 查询类型

- **反事实**（`Y_x | X=x', Y=y'`）
- **条件 effect 的自由 Z**（目前 given 必须是具体值；"给定 Z 一个随机变量"的 effect 需要 v0.2 扩展 AST）
- **时间索引查询**（`Y(t) | do(X(t-1))`）
- **高阶元查询**（关于模型本身的查询）

### 数值能力

- **从观测数据做 MLE / 参数估计**：Theta 必须由 `probability` 语句显式提供
- **连续变量**：Theta 值域只支持离散字面值
- **软证据 / 证据更新**：观测目前只参与值域推断，不触发后验计算
- **采样估计**（MCMC、重要性等）
- **布尔互补自动补齐**：`P(y=true|..)=0.2` 不会自动生成 `P(y=false|..)=0.8`；用户必须显式写全

### 结构扩展

- **原子类型系统**：atom 目前没有声明的值域；`theta_builder` 靠"出现过什么值"推断。正式类型 / 域声明留到 atom.schema 扩展
- **经验概率语句**（`empirical_prob`）：模型分布和样本统计的显式分离待 v0.2 引入
- **动态 forall**：对象域在运行中新增 / 删除不支持
- **无限对象域**

### 语言前端

- **文本 DSL**：v0.1 只吃 JSON
- **LLM 接入 / 自然语言翻译**
- **IDE / language server**

### 持久化 / 往返

- **`result_orchestrator.from_dict`**：v0.1 只实现序列化方向。已落盘的 query_result 可以过 `syntactic_validator.validate_result` 做 schema 合规性检查，但不能反序列化回 `QueryResult` 对象

---

## 一致性承诺（v0.1.x 补丁版本内不会变）

v0.1 的补丁版本（v0.1.1 / v0.1.2 ...）只做 bug 修复和文档同步。**下面这些不会改**：

1. **四态结果协议**：`structurally_solved` / `numerically_solved` / `needs_investigation` / `outside_language` 字符串字面值
2. **五种查询类型**：cause / assoc / effect / identify / probability
3. **公式 AST 算子集**：constant / probability_ref / product / sum
4. **Schema 顶层版本字段**：`"version": "0.1"` 是硬约束
5. **语义校验规则集合**：pre-graph / post-graph 分阶段、已启用的规则名不会改
6. **识别语义**：v0.1 只认后门准则；不存在有效调整集 = 不可识别
7. **Theta 的构建规则**：冲突键硬错；值域从出现的 value 推断；布尔默认
8. **Oracle 独立性**：pgmpy / ananke 永远不会进 runtime 依赖
9. **Python 包名**：`themis`

**会变的**（属于 v0.1.x 正常演进）：

- 文档、注释、测试
- 错误消息的措辞
- 解释器文字输出
- 内部辅助函数命名和组织
- 新增 fixture 和回归测试
- 性能优化

---

## v0.2 候选范围（未承诺、待决定）

按"破坏性从小到大"排序：

| 候选项 | 影响 | 备注 |
|---|---|---|
| 布尔互补自动补齐 | 非破坏（加法） | 降低样板代码 |
| `_gather_input_confidences` 填充 | 非破坏（占位值从 None 变实数） | 触发 v0.2 confidence 正式语义讨论 |
| 经验概率语句 `empirical_prob` | 非破坏（加法） | 模型 / 样本分离 |
| 原子类型声明 | schema 扩展（向后兼容） | 值域从隐式推断升级为显式 |
| ananke + ID 算法 | 非破坏（加法能力） | 不可识别 → 可识别的查询变多 |
| composite confidence 正式规则 | 语义变更 | 依赖上面的输入收集 |
| 前门准则 | 非破坏（加法） | 识别能力扩展 |
| 反事实查询 | 新查询类型 | AST 扩展；可能需要新算子（如 division） |
| 时间 / 动作 | 新语义层 | 最大跃迁 |

---

## 一句话

```
v0.1 = 有限对象域 + 后门可识别 + 数值可评估 + 诚实的缺口报告 + 差分可验证。
v0.1 的核心价值不是算法先进，而是语义干净、缺口显式、扩展点清楚。
```
