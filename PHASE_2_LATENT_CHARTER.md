# Phase 2.latent Charter — ADMG / 潜变量 / 双向边

> 立项日期：2026-04-21
> 最近重定 scope：2026-04-21（A 方案）
> 状态：**✅ 窄 scope 全部已落地** —— S1 / S2 / S3.a / S3.b.1 / S4 / S5
> 全部完成。**扩展 §S3.b.2 Tian / Shpitser ID Lines 1-6** 也已落地
> （2026-05-06，commit `a1d3675`）；Line 7（Q[S'] re-factorization
> recursion）按 charter §0 显式延后，记在 [`themis/runtime/c_factor.py`](themis/runtime/c_factor.py)
> module docstring（iter 39 文档诚实）。详见
> [`CORE_STATUS.md`](CORE_STATUS.md) "Phase 2.latent" 节 + "S3.b.2 Tian" 节。
> 对应 ROADMAP：Phase 2 "更强识别能力"中的潜变量 / ADMG / 前门分支
> 对应 TaskList：#38

## 0. Scope 说明（2026-04-21 重定）

实现到 S3.b.1 时做过一次 scope 检查：

- S3.a（ADMG-aware front-door）+ S3.b.1（ADMG-aware backdoor）事实上
  已经覆盖了我们能枚举出的**所有简单 ADMG 可识别情形**（包括经典
  front-door-with-hidden-U、带 bidirected 的 backdoor adjustment、
  Verma / napkin 等文献典型图）
- **真正 c-factor-only** 的案例（adjustment 和 front-door 都打不到、
  但 Tian c-factor 仍可识别）在我们当前的单 intervention / 单 target
  / 空 given scope 下**构造不出自然示例**—— 多是多 intervention、
  多 target、或需要 hedge 检测的情形，全部在本 charter 的 out-of-scope
  名单里
- 与 ROADMAP "等真实痛点逼出需求"原则一致：没有真实案例逼，就不抢写

所以把本 fragment 的 scope **窄化**到：

1. ADMG 图语义（bidirected statement + m-separation + c-components
   作为 partition 原语，已 done）
2. ADMG-aware backdoor / front-door（已 done）
3. 对应的 verifier rule family 收敛（S4）
4. e2e 案例 + CORE_STATUS 解冻段（S5）

**generic c-factor 形式 formula + Pearl ID 算法子集 + c-forest 不可识别
witness 全部移出本 charter**，等将来遇到真实 ADMG 案例 scope 自然
扩大，或多 intervention / 多 target / conditional ID 有独立立项需求时
再单开 charter。

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

### 3.3 c-component 分解（原语，仅做分区）

把节点集按 bidirected 边的连通分量划分。c-component 分解在本 charter
里只作为 **结构原语**：

- `structural_solver.c_components(g)` 返回节点集的 c-partition
- 用于 m-separation 的 collider 语义检查（双向边两端 collider-like）
- **不**构造 `Q[C_i] = P(C_i | do(V \ C_i))` 形式的 c-factor 公式
- **不**用 Tian ID 算法做可识别性决定

c-factor 公式 + Tian ID 算法是本 charter 明确移出去的那部分（见 §0 /
§4.2）。c_components 原语保留下来，将来扩 scope 时直接复用。

### 3.4 可识别性（本 charter 的定义）

effect query P(Y | do(X)) 在本 charter 下**可识别**当且仅当满足以下
之一：

- ADMG-aware backdoor 存在有效 adjustment set（`minimal_adjustment_sets`
  在 m-separation 验证下返回非空解）
- ADMG-aware front-door 存在有效 mediator set（`front_door_sets` 在
  m-separation 验证 FD2 / FD3 下返回非空解）

以上都不满足时，runtime 返回 `needs_investigation` + `query:identify_admg`
/ `query:effect_admg` 标记（**不**声称 unidentifiable —— 因为 c-factor
可能覆盖，但我们不判）。

---

## 4. 识别范围（scope vs out-of-scope）

### 4.1 in-scope

- **m-separation 原语**（`is_m_connected` / `m_separated`，S2）—
  ADMG-aware 的路径阻塞判定，验证时 verifier 独立重实现
- **c-components 分区原语**（`c_components`，S2）— 双向边连通分量；
  用于 m-separation collider 语义 + 未来扩 scope 时的入口
- **identify / effect 查询** 在 ADMG 下的识别，范围：
  - 单 intervention（`|intervention| = 1`）
  - 单 target（`|target| = 1`）
  - 空 `given`
  - 路径仅限 **ADMG-aware backdoor**（S3.b.1） 或 **ADMG-aware
    front-door**（S3.a）
- **ADMG-aware 判定的复核规则** —— S4 在 verifier 侧独立重实现
  m-separation + 验证 runtime 产出的 backdoor / front-door derivation
  是否真的在 ADMG 下成立

### 4.2 out-of-scope（本期明确不做，移出由 §0 记录）

- **generic c-factor 公式构造**（Tian's identification 公式）
- **Pearl ID 算法的 c-component sub-case 及其递归**
- **c-forest / hedge 作为 unidentifiable witness**
- **complete ID algorithm**（IDC / IDC\* / 多 intervention / 多 target）
- **conditional ID**（非空 `given` 的 identify 查询在 ADMG 下）
- **ADMG 下的 `cause` / `assoc` / `probability` 查询** —— 这些 query
  kind 的 dispatch 路径仍被 S3.a 的 gate 拒绝；要做需要独立立项

  > **2026-08-21（#353）作废**：`assoc` 在 S4 已解门。`cause` /
  > `probability` 的答案**实测本来就是对的**——gate 拒的不是错答。
  > 因此不需要独立立项；需要的是把 gate 的判据从「这条路径读不读
  > bidirected」换成「潜在共因动不动得了这个答案」。度量与理由见
  > CORE_STATUS.md 同日条目。
- **数值求值**：即使结构识别成功，不扩展 Theta 层的数值计算。effect
  结果在 ADMG 可识别路径下停在 `structurally_solved` + formula，不
  往 `numerically_solved` 推
- **双向边置信度聚合**：`annotations.confidence` 先只解析、不参与
  min 聚合路径
- **多边平行**：同一对 (A, B) 上多条 bidirected 语句直接视为一条；
  不做加权合并

**从 out-of-scope 晋升到 in-scope 的触发条件**：出现至少一个真实 ADMG
案例，在 S3.a + S3.b.1 下都打不到但 c-factor 可识别。出现时单开
charter（例如 `PHASE_2_LATENT_EXT_CFACTOR_CHARTER.md`）立项，不走
在本文档里。

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

## 5. Verifier 扩展（窄 scope）

### 5.1 新增 rule family（本 charter 收口）

| Rule | 类型 | 作用 |
|---|---|---|
| `m_separation_witness` | 结构正见证 | 列出 Z 使 X ⊥_m Y in ADMG（验证 backdoor 的 m-block 正确性） |
| `m_connection_witness` | 结构正见证 | 列出开放 m-path（证明一条 path 是打开的） |

以上两条是本 charter 唯一新增的 verifier rule family。它们服务于 S4
对 S3.a / S3.b.1 结果的独立复核：runtime 在 ADMG 下声称某 Z 阻塞了
X 到 Y 的所有 backdoor m-path，verifier 独立重跑 m-separation 看这个
断言是否成立。

### 5.2 不新增 rule family（移出 scope）

以下规则**不**在本 charter 实现，随 generic c-factor 一起延后：

- `c_component_decomposition`（只有 verifier 用 c-factor 时才需要）
- `identify_via_c_factor`（c-factor 识别终态）
- `unidentifiable_via_c_forest`（c-forest 负向见证）

### 5.3 独立重实现原则

和 V0–V5 保持一致：verifier 不调用 runtime。S4 在
`m_separation_witness` / `m_connection_witness` 规则内独立重实现
m-separation 判定算法，不借用 `structural_solver.is_m_connected`。
这样"runtime m-sep 的 bug"和"verifier m-sep 的 bug"需要同时发生才能
绕过复核。

### 5.4 绑定规则（复用已有 identify rule family）

`verify_identify` 继续接受：

- `identify_via_backdoor`（已有）—— 在 ADMG 程序里要求推导链里多一条
  `m_separation_witness` 验证 adjustment set 的 m-block 正确
- `identify_via_front_door`（A6 已有）—— 同上，`m_separation_witness`
  验证 FD2 / FD3
- `unidentifiable_via_backdoor`（已有）—— ADMG 程序里不使用（ADMG
  下不可识别 runtime 返回 `needs_investigation`，不给结构负见证）

**不再引入**新的 identify 终态 rule family —— 本 charter 的 runtime
结果全部可以用现有的 `identify_via_backdoor` / `identify_via_front_door`
derivation 形状 + 新增的 `m_separation_witness` 中间步复核。

### 5.5 verify() AdmgVerificationPending 的移除条件

S3.a 引入的 `AdmgVerificationPending` 在 S4 完成时移除。移除前提：
`verify_identify` 对 ADMG 程序的 backdoor / front-door derivation
能走通，且 `m_separation_witness` 能正确 accept / reject。

---

## 6. 冻结影响与解冻操作

### 6.1 明确破冻

本 charter 触及冻结面的三项：

1. **新 AST 语句类型**：`bidirected` → 触发 "禁止的改动" §3
2. **新语义维度**：潜变量 / 双向边 / ADMG → 触发 §2
3. **新 rule family**：`m_separation_witness` / `m_connection_witness`
   （窄 scope 重定后从 c-factor / c-forest 改为这两条）→ 触发 §3

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

| Slice | 内容 | 依赖 | 状态 |
|---|---|---|---|
| **S1** | AST + schema：`BidirectedStatement` 类型、schema 扩展、serializer、syntactic validator | — | ✅ 落地 |
| **S2** | **solver-only**：`structural_solver.m_separated` + `structural_solver.c_components`。纯算法原语，不挂 scheduler，不影响任何现有 query dispatch | S1 | ✅ 落地 |
| **S3.a** | **front-door made ADMG-aware**：`instantiation` 处理 `BidirectedStatement`；`structural_solver.bidirected_from_ground` 抽取辅助；`front_door_sets` 新增 `bidirected` 形参，FD2 / FD3 检查改用 m-separation；scheduler 把 bidirected 边穿进 front-door；gate 放宽给 identify / effect 查询；**verifier 兼容补丁**：`themis.verify` 在检测到 program 含 bidirected 时抛 `AdmgVerificationPending` | S2 | ✅ 落地 |
| **S3.b.1** | **backdoor made ADMG-aware**：`minimal_adjustment_sets` 新增 `bidirected` 形参，路径阻塞检查改用 m-separation；scheduler 在 ADMG 程序里先试 ADMG-aware backdoor，失败再回退到 S3.a 的 ADMG-aware front-door。formula 复用现有 `backdoor_formula` | S3.a | ✅ 落地 |
| ~~S3.b.2~~ | ~~generic c-factor~~ —— **移出本 charter**（见 §0 / §4.2）。未来有真实案例时单开新 charter | — | ⏸ 延后 |
| **S4** | **窄 verifier**：新增 `m_separation_witness` / `m_connection_witness` rule family（独立重实现 m-separation，不借 `structural_solver`）；scheduler 在 ADMG 程序的 identify / effect derivation 里插入 `m_separation_witness` 中间步；`verify_identify` 接受带 ADMG 见证的 backdoor / front-door derivation；移除 `AdmgVerificationPending` | S3.b.1 | ⏳ 未开工 |
| **S5** | e2e + CORE_STATUS：至少 3 个案例——（1）front-door-with-hidden-U 由 S3.a 识别 + S4 verifier accept；（2）Z→X→Y, W↔Z, W→Y 由 S3.b.1 识别 + S4 verifier accept；（3）bow-arc（X→Y, X↔Y）走到 `needs_investigation`（本 charter 不判 unidentifiable）；旧 DAG 案例回归不变；CORE_STATUS.md 加 "冻结后显式立项的 fragment" §"Phase 2.latent（窄 scope，落地 TBD）" | S4 | ⏳ 未开工 |

每个 slice 约束：

- 不跨 slice borrow 代码 —— S4 的 verifier 独立重实现不依赖 S2 / S3.a /
  S3.b.1 的 runtime 函数（`m_separated` 在 verifier 内有独立实现）
- 每个 slice 本身有独立的测试集合和 pin
- S2 合格门槛：`m_separated` 在 B=∅ 时和现有 `d_separated` 结果一致；
  `c_components` 覆盖孤立节点 / 全连通 / 多分量三种
- **S3.a 合格门槛**：
  - front-door-with-hidden-U 通过 `themis.run` 返回 `structurally_solved`
  - FD2 违反反例被正确拒绝
  - `themis.verify` 对 ADMG 结果抛 `AdmgVerificationPending`
  - gate 仍然拒绝 cause / assoc / probability 查询带 bidirected 的程序
  - v1.0 旧案例回归不变
- **S3.b.1 合格门槛**：
  - 一个 ADMG 案例在 S3.a 下 `needs_investigation`、在 S3.b.1 下
    `structurally_solved`
  - ghost-adjustment 反例正确拒绝
  - S3.a 的 front-door 路径在 backdoor 失败时仍能触发
  - 旧 DAG 案例仍走原 backdoor
- **S4 合格门槛**：
  - `m_separation_witness` 独立实现不引用 `structural_solver.is_m_connected`
  - 一个"m-sep 验证失败"的人工篡改 derivation 被 verifier 拒绝
    （证明复核真的在做事）
  - `themis.verify` 对 S3.a / S3.b.1 的 ADMG 结果直接 accept（不再抛
    `AdmgVerificationPending`）
  - DAG 回归路径不变
- **S5 合格门槛**：三个 e2e 案例 + CORE_STATUS 解冻段就位

---

## 8. Done 标志

本 fragment 视为完成当且仅当：

1. **三个 ADMG 案例**跑通（S3.a / S3.b.1 / "本 charter 不判"的负例）：
   - front-door-with-hidden-U（X → M → Y, X ↔ Y）：由 S3.a 的 ADMG-aware
     front-door 返回 `structurally_solved` + front-door 形状 formula；
     S4 `verify` 独立 accept
   - ADMG-aware adjustment 可识别正例（如 Z→X→Y, W↔Z, W→Y）：由
     S3.b.1 的 ADMG-aware backdoor 返回 `structurally_solved` +
     backdoor 公式；S4 `verify` 独立 accept
   - bow-arc（X → Y + X ↔ Y）：返回 `needs_investigation` +
     `query:identify_admg`（本 charter 不判 unidentifiable；
     generic c-factor / c-forest 不在 scope 内）
2. **至少 1 个旧 DAG 案例回归不变**（exercise_waist 照旧走 backdoor，
   verify 独立 accept）
3. **S1–S5 所有 pin 测试绿**，且 pytest 全套绿
4. **verifier 与 runtime 独立**：把 runtime `is_m_connected` 换成故意
   错误的实现，verifier 的 `m_separation_witness` 规则仍能检测出
   （对偶覆盖率测试）
5. CORE_STATUS.md "冻结后显式立项的 fragment" 段新增 Phase 2.latent
   窄 scope 小节，列出 S3.a / S3.b.1 / S4 的交付
6. `AdmgVerificationPending` 已从 `themis.verify` 的代码路径中移除
   （S3.a 引入时承诺在 S4 收回；到了 done 标志时必须真的没了）

---

## 9. 未决问题（charter 阶段不解决）

这些留给具体 slice 实现时决定，charter 不约束：

- 多段 bidirected 是否支持聚合（默认：否）
- `bidirected` 语句是否允许 `forall` 绑定（默认：是，和 `cause` 对称，
  S3.a 已按此落地）
- `supporting_paths` 在含 bidirected 边时的字符串表示（提议：`X <-> Y`
  用 `"<->"`, 方向边用 `"->"`；S4 实现时钉死）
- 窄 scope 下不涉及 hedge / c-forest minimality —— 这部分连同 generic
  c-factor 一起推到未来 charter

---

## 10. 本 charter 不做的事

- 不实现任何代码
- 不修改任何现有 AST / schema / verifier 代码
- 不更新 TaskList 的 #38 状态（由实际开工的 slice 来做）
- 不改 ROADMAP（ROADMAP Phase 2 的触发条件已经覆盖本 charter）

charter 通过后的下一步是 **S1 实现**，且 S1 的第一次 commit 必须
在 commit message 中引用本 charter 路径。
