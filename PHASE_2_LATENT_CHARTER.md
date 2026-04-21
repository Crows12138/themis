# Phase 2.latent Charter — ADMG / 潜变量 / 双向边

> 立项日期：2026-04-21
> 状态：**charter 起草中，未进入实现**
> 对应 ROADMAP：Phase 2 "更强识别能力"中的潜变量 / ADMG / 前门分支
> 对应 TaskList：#38

这是对 Themis v1.0 核心冻结面的一次**显式解冻申请**。按
[CORE_STATUS.md](CORE_STATUS.md) "核心冻结 v1.0" 规定，新 AST
语句类型、新语义维度、新 rule family 一律需要先立 charter 再动代码。
本文档就是这份 charter。

---

## 1. 动机

### 1.1 当前核心缺口

Themis v1.0 的语义面是 **纯 DAG**：所有观测变量之间的关系要么是一条
`cause` 边，要么不存在。现实世界的因果问题经常不能塞进这个框里——
只要存在"两个观测变量之间可能有一个我们看不到的共同原因"这种最基本
的混杂情形，DAG 就已经无法忠实表达。

典型卡点：

- 吸烟 → 肺癌，但还有没观测到的"基因易感性"同时影响两者
- 父母教育 → 孩子学业，但"家庭文化资本"是无法直接测量的共同原因
- 药物使用 → 结局，但"未记录的健康意识"同时影响两者

在当前 DAG 语义下，这类问题的唯一表达方式是**把 U 声明为一个 predicate**，
再加两条 cause 边。问题在于：

1. 如果 U 真的无法观测，声明它会让 A0 / F1 立刻把它的 framing 报成
   缺失，而这些缺失永远补不齐——用户没法告诉你"脑容量测量"怎么做
2. 后门调整集搜索会把 U 当成候选 Z 选进去，但运行时 Theta 里永远
   没有 U 的条目，结果要么误导用户去填 U，要么识别直接失败

真实的表达方式应该是 **"A 和 B 之间有一条双向边"**——承认有一个
U，但不假装它可观测。

### 1.2 启动依据

按 [ROADMAP.md](ROADMAP.md) Phase 2 原则：

> 如果某个跃迁已经被清楚定义为一个新的理论 fragment，并且边界、对象语言、
> 规则集和完成标志都能说清，也可以 theory-first 地启动。

ADMG + Pearl's ID algorithm 在因果推断文献里已经是教科书层级的固定
形式（Tian 2002, Shpitser & Pearl 2006, Bareinboim & Pearl 2016）。
边界和规则集可以一次讲清楚；ROADMAP 允许这种情况下不等真实案例压力就
theory-first 启动。

### 1.3 对称性论证（和 A6.front-door 的区别）

A6.front-door 明确 **不引入潜变量 / 双向边 / ADMG**，因为前门在已有
DAG 语义下就能表达。本 charter 是前门之后真正离开 DAG 的第一步：
A6 是在已有地基上加一条识别路径，本 fragment 是**扩大地基**。

两者互补：A6 覆盖"mediator 可观测"的 U-confounded 场景；ADMG 覆盖
"mediator 不可观测但共同原因可以双向边化"的场景。

---

## 2. 语言扩展

### 2.1 新增语句类型：`bidirected`

```json
{
  "kind": "bidirected",
  "left":  {"predicate": "smoking", "args": [{"type": "const", "name": "me"}]},
  "right": {"predicate": "lung_cancer", "args": [{"type": "const", "name": "me"}]},
  "annotations": {
    "source": "literature",
    "confidence": 0.8
  }
}
```

语义：两个观测变量 A 和 B 之间存在**至少一个未观测的共同原因 U**，且
U 没有被建模为显式 predicate。`bidirected` 是无向的 —— `left`/`right`
只是语法位置，不蕴含方向。

**不允许的写法**：

- 用户不能声明 `predicate: "latent_confounder"` 然后加两条 cause —— 这会被
  A0/F1 报 framing 缺失。charter 明确拒绝这条路径。
- 同一对 (A, B) 上同时有 `cause` 和 `bidirected`——ADMG 允许（混合边），
  charter 首版也允许，但 d-separation / ID 算法都要正确处理。

### 2.2 不引入的语句

- **不引入** `latent_variable` 或类似 statement。ADMG 的 semi-Markov
  表示刻意把潜变量留在语言外；本 fragment 跟随这个选择。
- **不引入** 新 query kind。仍然是 `cause / assoc / identify / effect
  / probability` 五种。`identify` 和 `effect` 的返回值空间会因为 ADMG
  扩大（多了 identify-via-c-factor 路径），但语言表面不变。

### 2.3 schema 变更

- `kernel_ast.schema.json` 新增 `bidirectedStatement` $def
- `statement` union 加入对它的引用
- `atom.schema.json` 不变
- `query_result.schema.json` 不变 —— supporting_paths 里可能出现带
  双向边的路径，但 `"string"` 表示即可
- `derivation.schema.json` 需要扩展：新 rule family 的 witness 结构

---

## 3. 语义

### 3.1 ADMG = DAG + bidirected edges

给定一个 Themis program，图投影（`graph_projection.project`）现在产出
一个 ADMG 而不只是 DAG：

- **有向边集** D = 全部 `cause` 语句
- **双向边集** B = 全部 `bidirected` 语句

### 3.2 m-separation

d-separation 在 ADMG 上的推广。一条路径可以包含：

- forward edge (→)
- backward edge (←)
- bidirected edge (↔)

节点 V 在路径上被**阻塞**当且仅当：

- V 不是 collider 且 V ∈ Z（条件集），或
- V 是 collider 且 V 及其有向后代都 ∉ Z

双向边两端都被视为 collider-like 位置（因为概念上对应一个未观测 U
的子节点）。

**交付**：`structural_solver.m_separated(g, X, Y, Z)` 独立实现，不调用
d-separated。m-separation 包含 d-separation 作为子情形（B = ∅ 时一致）。

### 3.3 c-component 分解

把节点集按 bidirected 边的连通分量划分。每个 c-component C_i 对应一个
联合条件分布：

    Q[C_i] = P(C_i | do(V \ C_i))

**Tian 2002 的核心引理**：在 semi-Markov 模型下，Q[C_i] 总可以用观测
分布表示（c-factor 公式）。

**交付**：`structural_solver.c_components(g)` 返回节点集的 c-partition。

### 3.4 可识别性

effect query P(Y | do(X)) 在 ADMG 下**可识别**当且仅当 Pearl's
ID algorithm 能为它产出一个只用观测分布的表达式。本 charter 不实现
complete ID —— 见 §4。

---

## 4. 识别范围（scope vs out-of-scope）

### 4.1 in-scope

- **m-separation** 的结构查询支持（`cause` / `assoc` query 在 ADMG 上
  的直接答复）
- **c-component 分解** + 每个 c-component 的 c-factor 公式构造
- **identify / effect** 查询：
  - 单 intervention（`|intervention| = 1`）
  - 单 target（`|target| = 1`）
  - 空 `given`
  - 目标 ∈ intervention 的有向后代（否则直接 P(Y)）
- **Pearl ID 算法的 c-component sub-case**：
  - 如果 X 和 Y 在同一个 c-component 且存在混淆路径 → unidentifiable
    with c-forest witness
  - 否则用 c-factor 分解 + Tian's identification 公式
- **前门的 ADMG 兼容检查**：A6 前门规则在遇到 bidirected 边时要能
  正确判定 FD3（intervention 到 mediator 的 backdoor-free path 允许
  包含双向边，但不能穿过 Y 的双向后代）

### 4.2 out-of-scope（本期明确不做）

- **complete ID algorithm**（IDC / IDC\* / 多 intervention / 多 target）
- **conditional ID**（非空 `given` 的 identify 查询在 ADMG 下）
- **hedge minimality** 作为 unidentifiable witness 的完整正确性证明
  （本期只要一个 hedge，不要求 minimal）
- **数值求值**：即使结构识别成功，不扩展 Theta 层的数值计算。effect
  结果在 ADMG 可识别路径下停在 `structurally_solved` + formula，不
  往 `numerically_solved` 推
- **双向边置信度聚合**：`annotations.confidence` 先只解析、不参与
  min 聚合路径（confidence RFC 的扩展留作后续 slice）
- **多边平行**：同一对 (A, B) 上多条 bidirected 语句直接视为一条；
  不做加权合并

### 4.3 不触碰的地方

- `cause` / `observation` / `probability` / `query` / `variableDeclaration`
  语法和语义全部不变
- `forall` 实例化规则不变
- A0 / F1 framing 对 `bidirected` 语句无反应（两端的 predicate 如果
  被其他语句引用，framing 照常；bidirected 语句本身不触发新的
  framing_note）
- confidence `min(non-None)` 规则不变；本期 bidirected.annotations.confidence
  不进入聚合

---

## 5. Verifier 扩展

### 5.1 新增 rule family

| Rule | 类型 | 作用 |
|---|---|---|
| `m_separation_witness` | 结构正见证 | 列出 Z 使 X ⊥_m Y in ADMG |
| `m_connection_witness` | 结构正见证 | 列出开放 m-path |
| `c_component_decomposition` | 结构中间步 | 声明 c-partition 正确 |
| `identify_via_c_factor` | 识别终态 | 单 c-component 内部 ID |
| `unidentifiable_via_c_forest` | 识别终态（负） | hedge 存在见证不可识别 |

### 5.2 独立重实现原则

和 V0–V5 保持一致：verifier 不调用 runtime。`identify_via_c_factor`
规则内独立重实现：

- c-partition 的计算
- c-factor 公式模板
- ID 算法的子集递归

这一点 charter 强调：ID 算法的 runtime 实现和 verifier 实现必须
**独立两份代码**，以免共同 bug 绕过复核。

### 5.3 绑定规则

`verify_identify` 接受以下终态 rule family 之一：

- `identify_via_backdoor`（原）
- `identify_via_front_door`（A6）
- `identify_via_c_factor`（本期）

负向：`verify_identify` 可以以 `unidentifiable_via_backdoor` /
`unidentifiable_via_c_forest` 任一结尾，表示负结果。

---

## 6. 冻结影响与解冻操作

### 6.1 明确破冻

本 charter 触及冻结面的三项：

1. **新 AST 语句类型**：`bidirected` → 触发 "禁止的改动" §3
2. **新语义维度**：潜变量 / 双向边 / ADMG → 触发 §2
3. **新 rule family**：c-component / c-factor / c-forest → 触发 §3

### 6.2 解冻记录

实现该 fragment 时，在 [CORE_STATUS.md](CORE_STATUS.md) "冻结后显式
立项的 fragment" 段新增 §"Phase 2.latent（立项 2026-04-21，落地日期 TBD）"，
格式对齐 A6.front-door。

### 6.3 兼容性保证

- 不含 `bidirected` 语句的旧 program 行为**完全不变**（回归测试全绿）
- schema 扩展是**纯增量**：旧 schema 接受的文档新 schema 仍然接受
- runtime 在看到 `bidirected` 语句前，不进入任何 ADMG 代码路径

---

## 7. 实现阶段

按交付顺序拆成独立 slice，每个 slice 都要求 pytest 全绿才进入下一个：

| Slice | 内容 | 依赖 |
|---|---|---|
| **S1** | AST + schema：`BidirectedStatement` 类型、schema 扩展、serializer、syntactic validator | — |
| **S2** | **solver-only**：`structural_solver.m_separated` + `structural_solver.c_components`。纯算法原语，不挂 scheduler，不影响任何现有 query dispatch | S1 |
| **S3.a** | **front-door made ADMG-aware**：`instantiation` 处理 `BidirectedStatement`；`structural_solver.bidirected_from_ground` 抽取辅助；`front_door_sets` 新增 `bidirected` 形参，FD2 / FD3 检查改用 m-separation；scheduler 把 bidirected 边穿进 front-door；gate 放宽给 identify / effect 查询；**verifier 兼容补丁**：`themis.verify` 在检测到 program 含 bidirected 时抛 `AdmgVerificationPending` 专属错误（不静默通过、不假装验证），消息指向 S4 待办。cause / assoc / probability 查询上的 bidirected 仍被 gate 拒绝 | S2 |
| **S3.b** | `formula_builder.c_factor_formula`：Tian 算法落地，覆盖 front-door 打不到的可识别单 intervention / 单 target / 空 given 场景；scheduler c-factor 回退路径（backdoor + ADMG-aware front-door 都失败时）；仍不打 `identify_via_c_factor` 标签；verify() 仍对这类结果抛 `AdmgVerificationPending` | S3.a |
| **S4** | verifier rules：`m_separation_witness` / `c_component_decomposition` / `identify_via_c_factor` / `unidentifiable_via_c_forest`；`verify_identify` / `verify_numeric` 扩展；scheduler 对外暴露新的 ADMG theorem family —— S3.a / S3.b 的 runtime 结果在这一刻开始带 `identify_via_c_factor` derivation 标签，并接受独立 verifier 复核；`verify` 移除 `AdmgVerificationPending` 路径 | S3.b |
| **S5** | e2e 案例：至少 1 个可识别（经典 front-door-with-hidden-U，由 S3.a 识别）+ 1 个可识别但 front-door 覆盖不到（由 S3.b 识别）+ 1 个不可识别（经典 bow arc）；旧 DAG 案例回归；CORE_STATUS.md 解冻段补全 | S4 |

每个 slice 约束：

- 不跨 slice borrow 代码 —— S4 的 verifier 独立重实现不依赖 S2 / S3.a /
  S3.b 的 runtime 函数（`m_separated` / `c_components` /
  `c_factor_formula` 在 verifier 内都要有独立实现）
- 每个 slice 本身有独立的测试集合和 pin
- S2 合格门槛：`m_separated` 在 B=∅ 时和现有 `d_separated` 结果一致
  （回归保证）；`c_components` 覆盖孤立节点 / 全连通 / 多分量三种
- **S3.a 合格门槛**：
  - 至少一个 ADMG 可识别案例（front-door-with-hidden-U）通过 `themis.run`
    返回带 formula 的 `structurally_solved`
  - 至少一个"directed skeleton 假装 front-door 成立、ADMG 实际不成立"的
    反例被正确拒绝（证明 front-door FD2/FD3 确实换成了 m-sep）
  - `themis.verify` 对 ADMG 结果抛 `AdmgVerificationPending`（不静默
    accept、不 False-accept）
  - gate 仍然拒绝 cause / assoc / probability 查询带 bidirected 的程序
  - v1.0 旧案例（exercise_waist 等）走 backdoor 路径回归不变
- **S3.b 合格门槛**：至少一个 front-door 覆盖不到但 c-factor 可识别的
  ADMG 案例返回 `structurally_solved`；`front_door_sets` ADMG-aware 的
  回归保持

---

## 8. Done 标志

本 fragment 视为完成当且仅当：

1. **三个经典 ADMG 案例**跑通（覆盖 S3.a / S3.b / 负例）：
   - front-door-with-hidden-U（X → M → Y, X ↔ Y）：由 S3.a 的 ADMG-aware
     front-door 返回 `structurally_solved` + front-door 形状 formula
   - c-factor 覆盖的可识别正例（front-door 打不到但 Tian 可识别）：
     由 S3.b 返回 `structurally_solved` + c-factor formula；S4 之后
     带 `identify_via_c_factor` derivation，verifier 接受
   - 不可识别负例（如 bow-arc：X → Y + X ↔ Y）：
     S4 之后返回 `unidentifiable_via_c_forest`，verifier 接受
2. **至少 1 个旧 DAG 案例回归不变**（exercise_waist 照旧走 backdoor）
3. **S1–S5 所有 pin 测试绿**（S3 分两拨：S3.a / S3.b），且 pytest 全套绿
4. **verifier 与 runtime 独立**：把 runtime `c_components` 换成故意错误
   的实现，verifier 仍能检测出（对偶覆盖率测试）。S3.a / S3.b 期间
   verifier 对 ADMG 结果抛 `AdmgVerificationPending` 而非 False-accept
5. CORE_STATUS.md 解冻段已写入（S5 完成时一次性写入，S3.a / S3.b
   只在 charter 本文更新 Done 标志进度）

---

## 9. 未决问题（charter 阶段不解决）

这些留给具体 slice 实现时决定，charter 不约束：

- 多段 bidirected 是否支持聚合（默认：否）
- `bidirected` 语句是否允许 `forall` 绑定（默认：是，和 `cause` 对称）
- `supporting_paths` 在含 bidirected 边时的字符串表示（提议：`X <-> Y`
  用 `"<->"`, 方向边用 `"->"`）
- unidentifiable witness 的 hedge 表示是否需要 minimal（charter §4.2
  明示本期不要求 minimal）

---

## 10. 本 charter 不做的事

- 不实现任何代码
- 不修改任何现有 AST / schema / verifier 代码
- 不更新 TaskList 的 #38 状态（由实际开工的 slice 来做）
- 不改 ROADMAP（ROADMAP Phase 2 的触发条件已经覆盖本 charter）

charter 通过后的下一步是 **S1 实现**，且 S1 的第一次 commit 必须
在 commit message 中引用本 charter 路径。
