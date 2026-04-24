# Phase 6.iv Charter — 工具变量 (IV) 识别 fragment

> 立项日期：2026-04-24
> 状态：**charter 草案** —— 未动代码
> 对应 ROADMAP：Phase 6 "识别层完整化 (M1)" 下的第一个 slice
> 对应 TaskList：待新建条目
> 对应 VISION：扩展愿景——覆盖 12 板块的第 5 板块（IV）

## 0. Scope 说明

Phase 6 (M1 识别层完整化) 总共包含 4 个 slice：

- **6.iv**（本 charter）：工具变量 IV 识别（IV1/IV2/IV3 + conditional IV）
- **6.mediation**：中介分析 (NDE / NIE / CDE) 识别
- **6.front-door-multi**：多 mediator 链式前门
- **6.complete-id**（可选延至 Phase 6.5）：Shpitser-Pearl 完整 ID 算法

每个 slice **独立 charter + 独立落地 + 独立 verifier**，不捆绑——
这和 Phase 2.latent 把 "ADMG 语义" 和 "c-factor" 拆开的原则一致。

**本 charter 只管 IV 识别**，不涉及其他三个 slice；也不涉及 Phase 7
的 IV 估计（2SLS / LATE / DML-IV）——本 slice 是**识别层**，结论是
"这个图 + query 在 IV 策略下能否识别 + 用什么公式"，**不给数字**。

这是对 Themis v1.0 核心冻结面的一次**显式解冻申请**。按 CORE_STATUS.md
规定，新 rule family 需要先立 charter 再动代码。本文件就是这份 charter。

---

## 1. 动机

### 1.1 战略定位

按 VISION.md "扩展愿景" 段 + ROADMAP Phase 6，Themis 要从"静态因果识
别内核"扩展到"全 12 板块因果推理编排器"。**板块 5 (IV) 是识别层里
最明显的缺口**——没有 IV，Themis 只能处理"backdoor 可调整"的场景，
碰到真实医学 / 经济学应用里的"未观测混杂 + 有工具变量"直接束手无策。

### 1.2 真实压力

**eval 集现状**：目前 20 个 case 里**没有纯 IV 场景**。加 case 21–22
覆盖 IV 是本 slice 的必要部分（not after-thought）——两个 case：

- **IV 有效场景**（孟德尔随机化：基因 → 某蛋白表达 → 疾病，基因作 IV）
- **IV 失败场景**（距离学校 → 教育 → 收入，但"家庭社区经济"导致 IV2
  违反）

用户真实会问的问题类型：

- "我想估 X → Y 因果效应，但担心有未观测混杂。Z 能不能作 IV？"
- "根据 IV 策略，这个 query 能不能识别？"
- "我的 IV 违反了哪条 IV1/IV2/IV3？"

**裸 LLM 在这类问题上错误率高**（见 VISION.md "扩展愿景" 段的 LLM
对比）——会不系统检查 IV1/IV2/IV3，尤其是 IV2 排他性经常被忽略。
Themis 的结构化检查是真实价值。

### 1.3 理论固化度

工具变量法是因果推断教科书级别的成熟工具：

- Wright 1928（线性 IV）
- Bowden & Turkington 1984（IV 的识别条件）
- Angrist, Imbens & Rubin 1996（Rubin 因果框架下的 IV，三假设 +
  monotonicity → LATE 点识别）
- Pearl 2009 ch.8（图论语义下的 IV 准则）

本 slice 基于 Pearl 图论准则（图+ADMG 上的 IV1/IV2/IV3 判定）实现，
不涉及 Rubin 框架下的 monotonicity / LATE。满足 ROADMAP "理论已清晰
定义" 的启动门槛。

### 1.4 对称性论证

和已落地 fragment 的差异：

- **和 A6.front-door**：前门是 backdoor 失败后的**第二条识别路径**；
  IV 是第三条。三者在现有 DAG 语义内正交（不引入潜变量 / 新边类型）。
- **和 Phase 2.latent (ADMG)**：IV 需要**区分观测混杂和潜共因**——
  IV3 "Z 和 Y 没有通过 bidirected 边连通" 的检查直接复用 ADMG
  m-separation 原语。无需新语义原语。
- **和 Phase 5**：Phase 5 §T / §C 扩展了时序 / 反事实语义；本 slice
  不扩展语义面，只加识别规则。

---

## 2. 语言扩展

### 2.1 schema 变更（最小）

**`kernel_ast.schema.json`**：
- `CauseStatement` 没有变化
- 可选 annotation：`annotations.iv_candidate: true`——NL 层 A1 prompt
  可以在用户明确说 "Z 是 IV" 时加这个标注，帮助 identify 路径优先搜
  Z 作为 IV 候选。但**不是必需**——识别算法也可以从图结构自动发现候
  选 IV。

**`query_result.schema.json`**：
- `derivation` 新 rule names：`iv_criterion_check` / `iv_identification`
- `result.identify.strategy` 加枚举值 `"iv"`（已有 `"backdoor" | "front_door"`）
- `result.identify.instrument` 新字段：记录使用的工具变量 Z
- `result.identify.iv_assumptions`：记录 IV 需要的额外假设（monotonicity 等
  在识别层只是**记录**，不是 enforce——enforce 是 Phase 7 估计层的事）

### 2.2 不引入的

- **不引入** 新 statement kind
- **不引入** 新 query kind
- **不引入** IV 估计（2SLS / LATE / Wald / DML-IV）——Phase 7 L1-L3
  做
- **不引入** many-weak-instruments 理论
- **不引入** 连续 / 类别 outcome 的特殊 IV 公式——首版只做 binary
  outcome + binary intervention 的 IV 识别

---

## 3. 语义

### 3.1 IV 准则形式化

给定 DAG/ADMG G、intervention X、outcome Y。候选工具变量 Z ∈ V \ {X, Y}
满足 IV 当且仅当：

- **IV1 相关性**：G 里存在从 Z 到 X 的有向路径（经过或不经过其他节点）
- **IV2 排他性**：在 G\{X→Y} （删掉 X → Y 的直接边所得子图）中，Z
  和 Y 不 m-connected；换句话说 Z 对 Y 的**所有**影响必须经过 X
- **IV3 独立性**：Z 和 Y 之间不存在 **纯 bidirected 路径**（ADMG 层
  面的未观测共因）；更严格地 Z 和 U（未观测混杂）独立

三个准则都用**图 / ADMG 上的 m-separation**判定，不需要新原语。

### 3.2 Conditional IV

给定观测到的协变量集合 W，Z 是给定 W 的 conditional IV 当且仅当
IV1/IV2/IV3 在**给定 W 条件下**成立：

- IV1 条件：Z → X 的路径存在给定 W 之后仍存在
- IV2 条件：G\{X→Y} 里 Z ⊥ Y | W
- IV3 条件：Z 和 U 在 W 之下独立

实现上 conditional IV 是 basic IV 的泛化——判定函数接受 `W: set[Atom]`
参数，空集时退化为 basic IV。

### 3.3 IV 识别的结果形式

判定成功时返回：

```python
IVIdentifyResult(
    strategy="iv",
    instrument=Z,
    conditioning_set=W,  # 空集 = basic IV
    iv_criterion_checks={
        "iv1_relevance": True,
        "iv2_exclusion": True,
        "iv3_independence": True,
    },
    identification_formula_template=(
        # 首版只做图级别识别，不展开成具体公式字符串
        # 记录 "可识别 via IV" + 所需额外假设
        # 具体公式（Wald / 2SLS）留给 Phase 7
        "P(Y|do(X)) identifiable via IV with additional assumption: "
        "binary-outcome + binary-X + monotonicity (for LATE), "
        "or linearity (for 2SLS ATE)"
    ),
    identification_assumptions=[
        "monotonicity OR linearity (choose one for estimation layer)"
    ],
)
```

**识别层不替用户选假设**——只报告"用 IV 策略可识别，需要额外假设 X
或 Y"。具体假设在哪个成立是 Phase 7 估计时的决定。

### 3.4 识别 vs 估计的界限（明确）

本 slice 只做**图级别可识别判定 + 所需假设清单**：

- ✅ 输入图 + query → 输出"是否 IV-identifiable + 哪个 Z + 需要什么假设"
- ❌ 输入数据 → 输出数值估计（这是 Phase 7 的工作）

这条界限和 Phase 6 整体策略一致：**识别层先完整化，估计层另立 Phase 7**。

### 3.5 多 IV 候选的选择

给定一个 G，可能存在多个满足 IV1/IV2/IV3 的 Z。本 slice 的策略：

1. **枚举所有满足条件的 Z**（basic IV + conditional IV）
2. **按优先级排序**（basic IV 优先于 conditional；少条件集优先于多条件集）
3. **返回第一个**作为 recommended，但 **extensions 里列出所有候选**
4. 用户 / A1 prompt 可以通过 `annotations.iv_preference` 引导选择

### 3.6 与其他识别策略的组合

当 backdoor 失败 + front-door 失败时，scheduler 尝试 IV：

```
_dispatch_identify 流程（扩展后）:
  1. 尝试 backdoor_sets(G, X, Y) → 成功则用
  2. 尝试 front_door_sets(G, X, Y) → 成功则用
  3. 尝试 iv_sets(G, X, Y) → 成功则用（本 slice 新加）
  4. 都失败 → "not identifiable by any standard strategy"
     （Phase 6.complete-id 会扩展到 Shpitser-Pearl ID 算法）
```

---

## 4. Verifier rule family

新规则族 `iv_*`：

### IV1 `iv_relevance_check`

- **Input**：G、Z、X
- **Check**：存在从 Z 到 X 的有向路径
- **Witness**：具体的路径节点序列 `[Z, ..., X]`
- **Negative witness**：若无路径，Z 的后代 / 前辈枚举证明 Z ⊥ X

### IV2 `iv_exclusion_check`

- **Input**：G、Z、X、Y
- **Check**：在 G\{X→Y} 中，Z 和 Y m-separated（或给定 W 时条件 m-sep）
- **Witness**：具体的切断集合（哪些节点 block 了 Z-Y 路径）
- **Negative witness**：未被 block 的 Z-Y 路径

### IV3 `iv_independence_check`

- **Input**：G（含 bidirected）、Z、Y
- **Check**：Z 和 Y 之间无纯 bidirected 路径
- **Witness**：ADMG 上的相关 m-separation 证明
- **Negative witness**：具体的 bidirected 连通路径

### `iv_identification`

- **Input**：G、X、Y、候选 Z、conditioning W
- **Check**：IV1 + IV2 + IV3 全部通过（调用上面三个 rule 作为子规则）
- **Output**：`IVIdentifyResult` 结构
- **Witness**：三个子 check 的 witness 联合

### `identify_via_iv`

- 类似 `identify_via_front_door`——scheduler 发出的 identify 决策见
  证：用 IV 策略，instrument 是 Z，conditioning 是 W

### 独立性钉死

和现有 verifier 一样，**rule 实现与 runtime 分离**——byte-code scan
测试钉死 IV rule 不引用 runtime 代码（参照 Phase 2.latent S4）。

---

## 5. Schema 变更清单

- `kernel_ast.schema.json`：**无新 statement kind**，仅加可选
  `annotations.iv_candidate` / `annotations.iv_preference` 字段
- `query_result.schema.json`：
  - `IdentifyResult.strategy` enum 加 `"iv"`
  - 新字段 `IdentifyResult.instrument` （IV 节点）
  - 新字段 `IdentifyResult.iv_assumptions` （假设清单）
- `derivation.schema.json`：新 rule names `iv_relevance_check` /
  `iv_exclusion_check` / `iv_independence_check` / `iv_identification` /
  `identify_via_iv`
- `verification_context.schema.json`：witness 扩展（路径证明格式）

---

## 6. S 切片

- **S.IV.1**：IV 判定原语
  - `structural_solver.iv_sets(G, X, Y, conditioning_set=frozenset())`
  - 返回满足 IV1/IV2/IV3 的候选 Z 列表（+ 每个 Z 的 conditioning 需求）
  - 支持 ADMG 输入（带 bidirected）
  - ~1-2 天

- **S.IV.2**：Scheduler 集成
  - `_dispatch_identify` / `_dispatch_effect` 在 backdoor + front-door
    都失败时 fall back 到 `iv_sets`
  - 结果包装成 `IdentifyResult` 带 `strategy="iv"`
  - 识别失败的情况 fall through 到 "not identifiable by standard strategies"
  - ~1-2 天

- **S.IV.3**：Verifier 规则族
  - `iv_relevance_check` / `iv_exclusion_check` / `iv_independence_check` /
    `iv_identification` / `identify_via_iv` 五个规则
  - 独立代码（不引用 `structural_solver.iv_sets`），byte-code scan 钉独立性
  - 每规则 3 正例 + 3 反例 + 2 ADMG 情况
  - ~3-4 天

- **S.IV.4**：Schema + result 序列化
  - schema 更新 + 反序列化测试
  - `to_dict` 正确序列化 IV 识别结果
  - ~1 天

- **S.IV.5**：A1 prompt v2.2 + response_rendering 更新
  - A1 识别 "Z 能做 IV 吗 / 我想用 Z 作 IV" 类型问题 → 加
    `annotations.iv_candidate`
  - A1 识别 "担心未观测混杂" 类型 → 尝试提示系统寻找 IV
  - response_rendering 新模板：surface IV 识别结果（包括 "IV2 违反，
    因为 ... 存在后门路径"）
  - ~2 天

- **S.IV.6**：E2E eval case 21 + 22
  - Case 21：IV 有效（孟德尔随机化类场景）
  - Case 22：IV 失败（排他性违反）
  - 跑 sonnet sub-agent + Themis 确认端到端正确
  - ~1-2 天

- **S.IV.7**：DoWhy parity test（dev dependency）
  - 安装 `dowhy` 作为 dev dep（不进 production）
  - 在若干测试图上跑 `dowhy.CausalModel.identify_effect(method='iv')`
  - 对照 Themis 的 IV 识别结果，数字对齐
  - CI 里跑，每次改 IV 代码必验
  - ~1 天

**总计**：~10-14 天（~2-3 周），比 ROADMAP 预估的 "~1 周" 更现实。

---

## 7. 完成标志

- S.IV.1 – S.IV.7 所有测试通过
- 全 pytest 至少保持不退步（当前基线 ~730 测试）
- 新增 ≥ 15 个 IV-specific 测试（S.IV.3 的规则族 + S.IV.1 的原语）
- Eval case 21 + 22 端到端跑通（case 21 识别成功，case 22 正确拒绝）
- DoWhy parity test 绿（所有测试图上结果一致）
- `CORE_STATUS.md` 列出 Phase 6.iv 解冻段
- `COVERAGE_MAP.md` 板块 5 (IV) 从 0% → ~60%（basic IV + conditional IV
  + ADMG-aware 完成；剩 40% 是多 IV 联合、结构方程模型下 IV 等）

---

## 8. 风险

### 8.1 IV2 排他性检查的微妙之处

排他性 (Z 对 Y 的影响只通过 X) 要求在 G\{X→Y} 中 Z 和 Y 不 m-connected。
这里的"删边"操作对 ADMG 情况要仔细——**删有向边但保留 bidirected**。
如果 X ↔ Y 存在 bidirected，IV 识别会被阻止（因为 Y 和 X 的潜共因
可能也是 Z 对 Y 的间接影响路径）。

**应对**：在 S.IV.1 里详细处理 ADMG 情况，测试覆盖 Z-Y 之间有 / 没有
bidirected 的 8 种组合。

### 8.2 候选 IV 枚举爆炸

对大图（> 30 节点）枚举所有候选 Z × 所有可能 W 条件集是 O(n · 2^n)。

**应对**：限制搜索深度（|W| ≤ 3 首版）；超过阈值报 `needs_simplification`，
让用户手动指定候选 Z。

### 8.3 DoWhy parity 可能不完全对齐

DoWhy 的 IV 实现可能和 Pearl 原版准则有实现细节差异（例如
conditioning set 的定义、bidirected 处理）。

**应对**：不追求 100% parity，**允许 "解释性差异"**——当 Themis 和
DoWhy 结果不同时，在 parity test 里记录差异原因（是我们错还是理论
选择不同）。只要 IV1/IV2/IV3 判定逻辑严格符合 Pearl 2009 即可。

---

## 9. 不做事项（charter 承诺）

### 9.1 本 slice 不做的

- **IV 估计**（2SLS / LATE / Wald / DeepIV / DML-IV）——Phase 7
- **连续 outcome 的 IV**——binary outcome 首版
- **Many-weak-instruments**——研究级
- **Compliance-type LATE 语义**（Always-taker / Never-taker / Complier）
  ——这是 Rubin 框架下的概念，Pearl 图论 IV 不涉及
- **Proxy instruments**（proxy 变量作 IV 的推广）——future work

### 9.2 本 charter 不改的

- Phase 0-5 的任何已落地代码（除了 `_dispatch_identify` 的顺序扩展）
- V0-V5 已有规则（新规则是**加**，不是改）
- 现有 schema 语义（只加 optional 字段）

### 9.3 和 Phase 6 其他 slice 的关系

- **6.mediation** 独立 charter，独立落地
- **6.front-door-multi** 独立 charter，独立落地
- **6.complete-id** 独立 charter，独立落地（可选延至 Phase 6.5）

本 charter 不预设其他 slice 的顺序或依赖，IV 应当能独立先跑通。

---

## 10. 附录 A — 非目标拒绝清单

明确不在本 charter 内的东西（防止 scope creep）：

| 项目 | 拒绝理由 |
|---|---|
| 2SLS / Wald 数值估计 | Phase 7 的地盘 |
| DeepIV / DML-IV | Phase 7 L3 |
| LATE / Monotonicity enforcement | 识别层只记录假设不 enforce |
| IV invalidity diagnostics (Sargan 检验等) | Phase 7 或单独立项 |
| Proxy variable IV | Future work |
| 非线性 IV | Future work |
| Weak-instrument 理论 | 研究级，long-term defer |
| C++ 性能加速 | Python 实现够用，大图走 `needs_simplification` |

任何上述主题通过真实 eval 案例逼出来，独立立新 charter。

---

## 11. 下一步

Charter 确认后：

1. 起新任务（TaskList 上新增 #43 = Phase 6.iv IV slice）
2. 按 S.IV.1 → S.IV.7 顺序实施
3. 每个 S 切片单独 commit，可独立 review
4. 全部完成后：
   - 更新 `COVERAGE_MAP.md` 板块 5 状态
   - 写 Phase 6.mediation charter 作为下个 slice
