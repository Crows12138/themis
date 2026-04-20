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

## Slice 10：ID / ananke

**目标**：把"后门不够"的场景真正扩出去。

具体任务：

- `oracle/ananke_adapter.py` 实装：把 Program 转成 ananke 的图模型，调用 ID 算法
- `runtime` 侧决定 ID 算法的 runtime 实现边界：
  - 方案 A：runtime 自己实现（保持 oracle 独立性原则，但要重写一遍复杂算法）
  - 方案 B：只在 runtime 用简化版（前门 / 后门 / 工具变量），完备 ID 留给 oracle 做对照；runtime 识别失败时返回 `outside_language` 或 `needs_investigation`
  - **需要在 slice 10 开头定**
- 识别失败语义重新定义：
  - 目前"无后门调整集"= `structurally_solved: false`
  - 前门 / ID 引入后，"不可识别"的定义要扩展，结果状态也要重新想
- 扩展 `identify` 公式 AST：ID 算法可能输出 division / joint target 等算子（v0.1 未实现）；如果需要，此时再加

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
