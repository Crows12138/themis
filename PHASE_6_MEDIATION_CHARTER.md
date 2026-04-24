# Phase 6.mediation Charter — 中介效应分解 (NDE / NIE / CDE) fragment

> 立项日期：2026-04-24
> 状态：**✅ 已落地（2026-04-24）** —— S.M.1 – S.M.7 全部完成
> 对应 ROADMAP：Phase 6 "识别层完整化 (M1)" 下的第二个 slice
> 对应 VISION：扩展愿景——覆盖 12 板块的第 6 板块（Mediation）
> 前置依赖：Phase 6.iv（已落地）；front-door 单 mediator（A6.front-door 已落地）
>
> **落地 commit**: ffb240e (S.M.1) → 01efe1d (S.M.2) → c27b44c (S.M.3)
> → 241e684 (S.M.4) → b56c7da (S.M.5) → 4b7f2b6 (S.M.6) → cff26ea (S.M.7)

## 0. Scope 说明

本 charter **只管中介效应分解的图论识别层**：
- Natural Direct Effect (NDE)
- Natural Indirect Effect (NIE)
- Controlled Direct Effect (CDE)
- 总效应分解恒等式 TE = NDE + NIE\_reverse（Pearl 2001）

**不做**：
- 数值估计（Imai et al. 2010 的参数 / 非参估计器）→ Phase 7 M2
- 敏感性分析（违反 sequential ignorability 时）→ Phase 8 M3
- 多 mediator 链（顺序中介 M1 → M2 → Y）→ 独立 slice 6.front-door-multi
- 交互项 mediator（treatment-mediator interaction 的非参识别）→ Phase 7+

和 A6.front-door 的区别：
- **front-door**：X → M → Y + X ⇄ Y 潜共因，目标是 **识别 P(Y|do(X))**（总效应 TE）
- **mediation (本 slice)**：X → M → Y + 可能 X → Y 直接边，目标是 **分解 TE = NDE + NIE** 或给 CDE

两者都涉及 mediator，但**问题不同**——front-door 解决"能不能估总效应"，mediation 解决"总效应里多少走 M 多少不走 M"。

## 1. 动机

### 1.1 战略定位

板块 6（中介分析）当前覆盖 **0%**。真实用户问题高频：

- "跑步 → 代谢 → 减肥：减肥里有多少是代谢改善、多少是其他路径？"
- "药 → 血压 → 心脏病：药对心脏病的直接效应有多大、通过降血压的间接效应有多大？"
- "教育 → 收入 → 健康：教育对健康的直接通道和通过收入的通道各占多少？"

裸 LLM 的问题：
- 把"总效应 TE"和"直接效应 NDE"混为一谈
- 不清楚 CDE（固定 M 下的直接效应）和 NDE（M 取自然分布的直接效应）的差别
- 完全不知道 Pearl "cross-world independence" 假设

Themis 的增量价值：
- 明确分离 TE / NDE / NIE / CDE 四个量
- 检查识别图论条件（no X-M confounder / no M-Y confounder given X / no intermediate confounder affected by X）
- 把"无法识别 NDE/NIE 只能识别 CDE"这种情况明确返回给用户

### 1.2 理论固化度

中介分析的图论识别成熟：
- Robins & Greenland 1992（direct/indirect 效应的反事实定义）
- Pearl 2001 "Direct and indirect effects"（mediation formula + 识别条件）
- VanderWeele 2015（教科书）
- Shpitser 2013（path-specific effects 的完整识别算法）

本 slice 基于 Pearl 2001 的识别条件（图论版本），不涉及 Shpitser 完整 path-specific ID（留给 Phase 6.complete-id 或 Phase 8）。

### 1.3 对称性论证

和已落地 fragment 的关系：

- **和 A6.front-door**：front-door 识别 TE；本 slice 在 TE 已识别的前提下做分解。可以复用 front-door 的 mediator 检测原语。
- **和 Phase 5.counterfactual**：NDE/NIE 的定义本质是 L3 反事实（`Y(x, M(x'))`），但**识别条件**可以在 L2（intervention）语言下表达（Pearl's mediation formula 只用 do 算子），所以本 slice 不强依赖 Phase 5 反事实 solver。
- **和 6.iv**：IV 解决未观测混杂下的 TE 识别；本 slice 假设 TE 已可识别（backdoor / front-door / IV 任一），然后问 mediation 结构。

---

## 2. 语言扩展

### 2.1 schema 变更

**`kernel_ast.schema.json`**：
- 新 query kind `mediation`（或扩展 `effect` 加 `decomposition: "nde_nie" | "cde"` 子字段——倾向后者，最小面）
- `MediationQuery`（如采用独立 kind）字段：
  - `treatment: Atom`（X）
  - `outcome: Atom`（Y）
  - `mediator: Atom | tuple[Atom, ...]`（M，首版只支持单 mediator）
  - `decomposition: "nde_nie" | "cde"`（哪种分解）
  - `reference_value`（对 CDE 是 M=m 的 m；对 NDE/NIE 是 x 和 x' 的参考值）

**倾向**：不新增 query kind，**扩展 EffectQuery** 加可选 `mediation` 子对象。理由：mediation 本质是 effect query 的特例（分解形式的 effect），schema 面最小。

**`query_result.schema.json`**：
- `extensions.mediation_decomposition` 新 sub-schema：
  ```
  {
    "mode": "nde_nie" | "cde",
    "identifiable": bool,
    "required_assumptions": [...],
    "formula_template": str,
    "unidentifiable_reason": str | null
  }
  ```

### 2.2 不引入的

- **不引入** 多 mediator 链（M1 → M2 → Y）——独立 slice
- **不引入** interventional direct/indirect effect（Vansteelandt 2012）——留 Phase 8+
- **不引入** path-specific effect 完整 ID（Shpitser 2013）
- **不引入** 数值分解器（只给识别层公式模板）

---

## 3. 语义

### 3.1 四个效应量的形式定义

给定 DAG/ADMG G，treatment X，outcome Y，mediator M，参考值 x、x\*：

- **TE**：`E[Y|do(X=x)] − E[Y|do(X=x*)]`（总效应）
- **CDE(m)**：`E[Y|do(X=x, M=m)] − E[Y|do(X=x*, M=m)]`（固定 M=m 的直接效应）
- **NDE**：`E[Y|do(X=x, M=M(x*))] − E[Y|do(X=x*)]`（M 取反事实下 x\* 产生的自然值时的直接效应）
- **NIE**：`E[Y|do(X=x*, M=M(x))] − E[Y|do(X=x*)]`（M 被推到 x 的自然值、X 保持 x\* 时的间接效应）

恒等式：**TE = NDE − NIE\_reverse**（Pearl 2001 eq 11）

### 3.2 图论识别条件（Pearl 2001）

**CDE(m)** 识别条件（较弱）：
- C1: 存在集合 Z 使 `Z ⊥ Y | X, M, Z` 在 G\_{X,M} 中（调整 Z 阻断 {X,M} → Y 的所有后门）
- C2: Z 的元素不是 X 或 M 的后代

**NDE / NIE** 识别条件（更强，Pearl 2001 Theorem 2，四条）：
- M1（X-Y 混杂可控）：存在 W 使 `Y ⊥ X | W` 在 G\_{X} 中
- M2（X-M 混杂可控）：存在 W 使 `M ⊥ X | W` 在 G\_{X} 中
- M3（M-Y 混杂可控，给定 X）：存在 W 使 `Y ⊥ M | X, W` 在 G\_{M} 中
- M4（**no intermediate confounder affected by X**）：W 的元素不是 X 的后代

**关键差别**：NDE/NIE 需要 M4，CDE 不需要。这就是为什么有"中间混杂器被 X 影响"时只能识别 CDE。

### 3.3 识别 vs 估计的界限

识别层（本 slice）输出：
- ✅ 四条件 check 结果
- ✅ 可识别 → formula 模板（mediation formula 的图级表达）
- ✅ 不可识别 → 指出哪条违反 + 为什么
- ❌ 不给数字（Phase 7 做）

### 3.4 默认选择策略

用户问 "X 对 Y 通过 M 的间接效应"，scheduler：
1. 先检查 CDE 识别（M1-like 条件）
2. 再检查 NDE/NIE 识别（M1-M4 全满足）
3. 返回最强的可识别形式；若只能 CDE，明确标注"NDE/NIE 不可识别"

---

## 4. Verifier rule family

新规则族 `mediation_*`：

### `mediation_cde_check`
- Input: G、X、Y、M、候选 Z（调整集）
- Check: C1 + C2（CDE 识别条件）
- Witness: m-sep 证明 + 非后代证明

### `mediation_nde_nie_check`
- Input: G、X、Y、M、候选 W
- Check: M1-M4 全部通过
- Witness: 四个 m-sep 证明

### `identify_via_mediation`
- Input: G、X、Y、M、mode ∈ {"nde_nie", "cde"}
- Check: 对应 check 通过 + 输出识别结果
- Witness: 子 check witness 联合

### 独立性钉死

和 IV 规则一样：byte-code scan 钉死 mediation rule 不引用 runtime（复用 Phase 2.latent S4 / Phase 6.iv 的模式）。

---

## 5. S 切片

- **S.M.1**：中介识别原语
  - `structural_solver.mediation_sets(G, X, Y, M, mode) -> MediationResult`
  - 返回四条件 check + 可识别 Z/W 集合
  - 支持 ADMG（bidirected）
  - 预估 ~1-2 天
  - **Mode 2（参考开源）**：查 DoWhy `dowhy/causal_estimators/mediation.py` + EconML `CausalMediation`，借鉴图检查逻辑但自写

- **S.M.2**：Scheduler 集成
  - 扩展 `_dispatch_effect` 认识 `mediation` 子字段
  - 调用 `mediation_sets` → 构造 derivation → emit result
  - 预估 ~0.5 天

- **S.M.3**：Verifier rules
  - 实现 `mediation_cde_check` / `mediation_nde_nie_check` / `identify_via_mediation`
  - byte-code scan 独立性测试
  - 预估 ~1 天

- **S.M.4**：Schema + 序列化
  - 扩展 `EffectQuery` 可选 `mediation` 字段
  - 扩展 `query_result.schema.json` `extensions.mediation_decomposition`
  - 更新 `to_dict` 序列化
  - 预估 ~0.5 天

- **S.M.5**：A1 prompt v2.3 + response rendering
  - 新 §3c "Mediation queries"：触发模式、canonical example、encoding 规则
  - response_rendering：`mediation_decomposition` 展示模板
  - 预估 ~0.5 天

- **S.M.6**：Eval cases 23 & 24
  - Case 23: **可识别 NDE/NIE**（跑步 → 代谢 → 减肥，无中间混杂器）
  - Case 24: **只可识别 CDE**（药 → 血压 → 心脏病，有 X 影响的中间混杂器）
  - 更新 failure_modes.md 加 F20（mediation identification）
  - 预估 ~0.5 天

- **S.M.7**：Parity test vs DoWhy / EconML
  - DoWhy `LinearRegressionEstimator` / EconML `CausalMediation` 做简单 DAG 上的结果对比
  - dev-only 依赖
  - 预估 ~0.5 天

**总预估**：4-5 天（比 IV slice 稍多一些，因为 NDE/NIE 的四条件检查比 IV 的三条件复杂）。

---

## 6. 风险 / Open Questions

### 6.1 query kind vs EffectQuery 扩展

决定：**扩展 EffectQuery**（不新增 kind）。复查点：若 mediation 需要的字段多到 `EffectQuery` 塞不下，再回头拆 `MediationQuery`。

### 6.2 反事实语义依赖

NDE/NIE 的 Pearl 定义用反事实 `Y(x, M(x*))`。识别条件可以在 L2 表达（不调 Phase 5 counterfactual solver），但**如果未来要做数值估计**（Phase 7），需要 L3 机械。现阶段 OK——本 slice 只识别。

### 6.3 多 mediator

首版**只支持单 mediator**。多 mediator 链留 6.front-door-multi。decision point：A1 prompt 要不要拒绝多 mediator 问题？初版倾向"降级为单 mediator" + 提示"多 mediator 未支持"。

### 6.4 和 front-door 的重叠

A6.front-door 已有 `front_door_sets`。mediation 和 front-door 共用一些图检查（X → M → Y 存在、M 的后门可控）。实现时**尽量复用**但不强求——两者问题不同，保持清晰比强行共享更重要。

---

## 7. 完成条件

Phase 6.mediation 完成的标志：

- [ ] S.M.1 `mediation_sets` 原语 + 15+ 单元测试
- [ ] S.M.2 scheduler 集成 + 5+ 集成测试
- [ ] S.M.3 verifier rules + 10+ rule 测试 + 独立性 byte-code test
- [ ] S.M.4 schema 扩展 + 8+ schema validation 测试
- [ ] S.M.5 A1 v2.3 §3c + response_rendering + 3 canonical examples
- [ ] S.M.6 eval cases 23 & 24 + F20 taxonomy
- [ ] S.M.7 DoWhy/EconML parity 5+ 对比 case
- [ ] COVERAGE_MAP.md 板块 6 0% → ~50%
- [ ] CORE_STATUS.md Phase 6 section 更新

---

## 8. 后续 slice 提示

完成 6.mediation 后，Phase 6 剩余 slice：
- **6.front-door-multi**：多 mediator 链的前门（扩展 A6.front-door 到链式）
- **6.complete-id**（可选）：Shpitser-Pearl 2006 完整 ID 算法——覆盖图上一切可识别查询

完成以上之后 Phase 6 (M1 识别层完整化) 正式收工，COVERAGE 板块 1+2+5+6 综合 ~60-65%，进入 Phase 7 估计层。
