# v0.2 优先级

本文件捕捉 v0.1.0 发布后、基于实际使用案例得到的 v0.2 第一批 slice 排序。

与 [`v0_1_scope.md`](v0_1_scope.md) 的关系：

- `v0_1_scope.md` 是**已冻结**的契约——v0.1.x 补丁内不变
- `v0_2_priorities.md` 是**活文档**——随案例反馈更新；新 slice 完成后，相应条目迁出（移入变更日志或 v0.2 的 scope doc）

---

## 三个使用案例的观察

| 案例 | 暴露的薄弱点 | 所在层 |
|---|---|---|
| 1 | 主链路能算出正确数值 → 后门 + 数值 MVP 本身不是痛点 | —— |
| 2 | 缺参数时系统还不够"会带你往下走" | 证据 / 调查推进 |
| 3 | 识别能做对，但解释把双调整变量说成单变量 | 解释与结果一致性 |

结论：最先磕到的不是"不会识别"，而是**识别成功时解释不忠实**和**缺参数时的引导太薄**。

---

## 优先级（从先到后）

| 顺位 | 主题 | 对应 slice |
|---|---|---|
| 1 | 解释与结果一致性 | Slice 8 |
| 2 | confidence / 数据入口 / 调查推进 | Slice 9 |
| 3 | ID / ananke | Slice 10 |
| 4 | 前门 / 更强识别 | 待定 |

排序的依据是**案例暴露的磕绊顺序**，不是算法理论难度顺序。

---

## Slice 8：解释与结果一致性

**目标**：让 explanation 严格跟上 formula / structural_result / missing_information 的实际内容，不能少说、不能错说、不能在多变量情况下降级成单变量。

具体任务：

- `identify` 解释器正确展示**多变量调整集**（当前只能抓到最外层 SumExpr 的 over，内层的被吃掉）
- 给 `effect` / `probability` 补 explainer（目前这两类查询的 explainer 直接 `NotImplementedError`）
- 确立"解释必须忠实于结构化结果"的不变量：
  - explanation 不能引入 formula / structural_result / missing_information 里不存在的信息
  - explanation 在多变量、嵌套公式、条件化场景下不降级
- `needs_investigation` 的解释要说清三件事：
  1. 缺什么（来自 `missing_information`，具体到原子 / 参数 / 公式项）
  2. 为什么缺（用户 / 模型层面的根因）
  3. 下一步做什么（来自 `investigation_requests`，具体动作）
- 新增差分式测试：explanation ↔ structured fields 的一致性（explanation 里提到的任何结构元素必须能在 structured fields 里找到对应）

**不做**：

- 多语言（v0.1 只出中文，先保持）
- 花哨渲染（仍然是纯文本）

---

## Slice 9：confidence / 数据入口 / 调查推进

**目标**：让"证据层"真正闭合。v0.1 只接了调用链，输入收集和正式语义都延后；slice 9 把这两件事落到位。

具体任务：

- 实现 `_gather_input_confidences`：walk 公式和 `missing_information`，收集相关 `probability` / `observation` 语句的 `annotations.confidence`
- 选定并落实 **composite confidence 正式语义**（候选：加权 / 乘积（假设独立）/ Dempster-Shafer / 证据推理；需要一次单独的 RFC 性决策）
- 数据入口：为 `probability` / `observation` 的 `annotations.source` 引入可引用的结构（URI？DOI？样本 ID？——需要设计）
- `investigation_pusher` 升级：
  - 按 `MissingKind` 分组聚合调查请求（同类合并）
  - 给每条请求附带"为什么这条重要"的结构化优先级理由
  - 当缺的是参数时，自动生成一段合法的 `probability` 语句骨架让用户填

**要先做的 RFC**：在 slice 9 代码动手前，先写 `confidence_rfc_v0_2.md` 对比候选规则，最终选一个。避免实现完才发现规则不适合。

→ **状态（2026-04-20）**：Slice 9 代码实施已完成。`confidence_calc.composite` 正式化为 v0.2 min 规则；`_gather_input_confidences` 按 RFC §3 采集 probability slot + observation slot；两张来源索引 `build_probability_source_index` / `build_observation_source_index` 在 `dispatch_all` 里一次构建复用。端到端验证 + 单元 + 采集层测试共 9 条新增（总 169 passed）。

剩余（slice 9 外）：
- `annotations.source` 的可引用结构（DOI / 样本 ID / URI 等）
- `investigation_pusher` 的分组聚合 + 结构化优先级理由 + 自动生成 probability 骨架
- 这些不改变语义，属于工具性升级，可单独作为 slice 9.x 或延后到 slice 10 之后

---

## Slice 10 — **不再存在于 v0.2**

**决策（2026-04-20）**：调研发现在纯 DAG（v0.1/v0.2 语义层）里，后门准则始终够用（parents(X) 是合法调整集）。前门 / 完备 ID 的独立价值几乎全部建立在**潜变量 / 双向边 / ADMG** 之上，而 v0.1 scope 已经显式把它们排除。

所以原 slice 10 的目标拆到两个不同时间层：

### 短期（v0.2）——由 9.x 系列完成

用户在实际使用中真正的痛点，其实不是识别能力不够，而是：

- 参数补录体验（slice 9.x-B）
- 调查推进工具化（slice 9.x-B）
- 结果解释继续完善（slice 8 系列已覆盖，必要时迭代）

这些都是**人机接口层**的工作，不需要扩语言。

### 长期（v0.3 候选）——等真正需要潜变量时再打开

- `latent_confounding`：schema 层引入不可观测变量概念
- `bidirected_edges`：ADMG（Acyclic Directed Mixed Graph）表示
- `ID 算法 / front-door / ananke`：建立在上面两条之上，此时完备 ID 才真正有独立价值
- 同步扩展 formula AST（可能需要 division）

**这组变更会构成 v0.3 的主跃迁，不应拆成 v0.2 内部 slice**。

### 旁注：纯 DAG 里前门仍可能有用

理论上在纯 DAG 里前门也不是完全无价值——当用户手工提供 Theta 时，某条替代公式可能更符合已有参数的 shape，能省得用户补额外条件概率。但这属于**"参数友好的公式选择"**，不是识别能力升级。如果未来要做，应按选择优化定位，不要包装成"完备识别"。

---

## 当前进行中

- ✅ **9.x-B**：investigation 分组聚合 + probability 语句骨架自动生成（commit fa2414b）
- ✅ **9.x-C**：参数回填工作流——extract / merge / diff 三步闭环
- ⏳ **9.x-A**：`annotations.source` 结构化——待真实使用中出现"来源追踪 / 出处审计"的具体卡点再启动

---

## 待定（进入 v0.2 前要看情况）

| 候选 | 说明 |
|---|---|
| 前门准则 | 独立能力，但比 ID 小；可能在 slice 10 顺手做 |
| 布尔互补自动补齐 | 降低样板；非破坏；案例里没磕到，优先级低 |
| 反事实查询类型 | 新语义层；放后面 |
| 经验概率语句 `empirical_prob` | 和 slice 9 的数据入口设计挂钩，可能在 slice 9 里顺手做 |
| 原子类型 / 值域声明 | 目前靠 theta_builder 从值推断，够用；痛点出来再提 |
| 时间 / 动作 | 最大跃迁；暂不排队 |

---

## 如何更新本文件

- 完成一条 slice → 把它从"优先级"表里摘掉，在文末或变更日志里留下一行完成记录
- 新案例冒出新痛点 → "三个使用案例的观察"表下追加行，如果改变排序就更新"优先级"表
- v0.2 发布时 → 定版，转成 `v0_2_scope.md`（仿 `v0_1_scope.md` 的契约结构）

---

## 一句话

```
v0.2 从"缺参数怎么办"和"识别完怎么说清"这两件事补起，
先把人机接口层稳住，再谈更强的识别能力。
```
