# Themis Roadmap

## 目的

这份路线图回答三个问题：

1. Themis 现在在哪个阶段
2. 接下来 1 到 2 个阶段该做什么
3. 从当前“推理层”走到未来“语料建模 + 推理”整体系统，中间要跨哪些台阶

它不是 release note，也不是 backlog 清单。  
它是对 [VISION.md](VISION.md) 的工程化展开。  
其中与“上游模型从哪里来”有关的详细设计，单独放在 [WORLD_MODELING.md](WORLD_MODELING.md)。

**核心冻结状态**：自 2026-04-21 起，Themis 核心（语言 / 运行时 / 数值 / verifier
V0–V5 / A0–A1）视为 v1.0 收口。详细冻结范围、允许与禁止的改动见
[CORE_STATUS.md](CORE_STATUS.md) 中
“核心冻结 v1.0”一节。路线图后续阶段在核心之外推进。

**当前开发态**：`0.15.0-dev`（2026-05-07）。Phase 6-15 已经作为
显式立项 fragment / workflow / estimator 扩展落地；本文件保留早期
Phase 0-5 的路线语义，但当前判断以 [CORE_STATUS.md](CORE_STATUS.md)
和 [COVERAGE_MAP.md](COVERAGE_MAP.md)
为准。

---

## 当前阶段

当前 Themis 已经完成了：

- 静态因果推理核心 + derivation verifier
- front-door / ADMG / temporal / counterfactual 的窄 scope fragment
- IV / mediation / transport 等识别扩展
- backdoor / front-door / IV / mediation / dose-response 估计层
- data-gap report / bounds-first / dose-response diagnostic
- variable framing / NL bridge / KB adapter contract / MCP wrapper

当前更准确的定位是：

**“可审计的因果推理编排器 + 数据缺口诊断器 + 受控估计层”**

而不是：

- 完整自动世界建模平台
- 自动世界建模系统
- 通用 AI agent

版本映射：

- **Phase 0 ≈ v0.1.0**（已 tag）
- **core freeze ≈ v1.0 收口面**（早期内核语义冻结）
- **当前开发态 = 0.15.0-dev**（Phase 15 world-modeling pressure harness 已起步）
- **Phase 编号不是稳定发布号**；它记录理论 fragment 与工程 slice 的推进顺序

---

## Phase 0：稳定推理内核

### 状态

已完成。

### 版本映射

**对应 `v0.1.0`**。  
这个阶段的核心成果已经冻结为一个可引用 tag，用来代表“静态推理内核 + 最小数值/调查闭环”的稳定基线。

### 目标

建立一个语义清楚、边界清楚、能在已知结构上稳定推理的内核。

### 已交付

- JSON AST + schema
- 有限对象域 + `forall` 实例化
- DAG 投影
- cause / assoc / identify / effect / probability
- 公式 AST
- Theta
- `needs_investigation`
- skeleton 回填
- confidence 最弱链路规则
- 解释器

### 成果意义

后续所有阶段都建立在这层之上。  
这层一旦不稳定，后面的“更强识别”“语料抽取”“自动建模”都会变成空中楼阁。

---

## Phase 1：真实工作流强化

### 状态

历史阶段，主体已完成并被后续 Phase 3 / Phase 10 / Phase 11 workflow
吸收。

### 版本映射

**早期主要对应 `v0.2`**。
这一阶段不再追求推理语义的大跳跃，而是把已有能力打磨成真实工作流里
顺手、可复用、可审计的系统。当前其主要成果已经进入 parameter /
variable fill-back、framing gate、data-gap report 和 KB/MCP bridge。

### 目标

把现有推理核心从“能算”推进到“能在真实问题里顺手使用”。

### 重点方向

1. **⏳ 试跑与案例积累**
   - 持续跑真实案例
   - 记录第一个痛点
   - 用真实使用决定版本方向

2. **✅ 参数补录工作流**
   - skeleton bundle
   - 回填
   - merge
   - diff
   - 已由 slice `9.x-B / 9.x-C` 打通基本闭环

3. **✅ 解释与结果一致性**
   - 解释必须忠实于公式和数值
   - 缺口说明必须对应真实缺项
   - 已由 slice `8.x` 建立基础一致性

4. **⏳ 证据元数据（按需）**
   - 只有当真实工作流开始需要“来源追踪 / 审计 / 排序”时
   - 才推进 `annotations.source` 结构化

### 完成标志

- 至少 **3 个真实案例** 跑通从 JSON 输入到 `diff_runs` 输出的完整闭环
- 其中至少 **1 个案例** 走通“首次缺参 → skeleton 补录 → 重跑变 `NUMERICALLY_SOLVED`”路径
- 在这批案例验证期间，核心 schema（`kernel_ast.schema.json` / `query_result.schema.json` / `atom.schema.json`）**不发生破坏性变更**
- 输出结果已经足够支持下一步动作，而不需要频繁修改核心推理语义

---

## Phase 2：更强识别能力

### 状态

窄 scope 已落地；complete ID / generic c-factor 仍延后。

### 目标

只有在真实案例或清晰 theory-first charter 真正逼出“后门不够”的时候，
才扩展识别能力。当前已经落地的是 front-door、窄 ADMG、IV、mediation、
transport 等可边界化 fragment；complete ID 仍不急。

### 触发条件

出现以下任一类真实需求：

- 后门调整不存在，但理论上仍可识别
- 出现可见中介、不可观测混杂等场景
- 纯 DAG 模型已经无法描述真实问题

### 可能内容

- 潜变量
- 双向边
- ADMG
- 前门
- ID 算法
- ananke / 自实现识别子集

### 原则

这不是“小增强”，而是一次**语义层跃迁**。  
如果启动，应明确作为新阶段，而不是在原有 DAG 内核里偷偷加几条规则。

这里的触发条件不必局限于真实案例。  
如果某个跃迁已经被清楚定义为一个新的理论 fragment，并且边界、对象语言、规则集和完成标志都能说清，也可以 theory-first 地启动。

---

## Phase 3：变量框定与问题充分性检查

### 状态

已落地第一版闭环与 opt-in strict gate。

### 目标

在系统真正推理前，先判断：

- 变量是否定义清楚
- 查询是否操作化
- 问题是否有足够的时间窗口、阈值、测量定义

### 在 VISION 四层图景中的位置

这一层更像是 **构建层与推理层之间的一道 gate**。  
无论上游模型来自：

- 手工编写
- 试跑案例
- 未来的语料抽取/变量构建

都应先通过这道“问题是否被充分框定”的检查，再进入 Themis 的正式推理流程。

这意味着 Phase 3 虽然暂时还在 Themis 周边实现，但在概念上已经属于
[WORLD_MODELING.md](WORLD_MODELING.md)
定义的上游建模职责的一部分。

### 背景

当前系统会把：

- `waist_reduced`
- `exercise_regular`

当成已经定义好的形式变量。  
但从真实使用角度，这可能还远远不够。

### 未来可能的能力

- 变量 metadata
- 时间窗口声明
- 阈值声明
- 测量方法声明
- “问题未正确框定”时拒绝数值推理

### 成果意义

这一层会把 Themis 从“形式上可算”推进到“问题上充分定义后才可算”。

---

## Phase 4：世界建模层

### 状态

长期目标；已有 down-payment，但完整平台未开始。

### 目标

不再要求用户手工把所有变量和关系写好，而是让系统从事实语料中构建候选世界模型。

这一阶段的详细设计基线见：
[WORLD_MODELING.md](WORLD_MODELING.md)

### 典型输入

- 文本记录
- 传感器数据
- 表格
- 用户叙述
- 历史日志

### 典型能力

- 实体抽取
- 事件抽取
- 变量规范化
- 时间窗口对齐
- 候选关系抽取
- 候选因果边 / 相关边生成
- 来源和置信度记录

### 与 Themis 的关系

Themis 不负责“发明世界”，而负责：

- 在上游生成的候选模型上做形式推理
- 指出哪个结构足够、哪个参数缺失、哪个关系仍是未定假设

也就是说：

**世界建模层在 Themis 之前，Themis 是它的推理后端。**

因此，Phase 4 不是“继续往 Themis 里塞功能”，而是把
[WORLD_MODELING.md](WORLD_MODELING.md)
里定义的变量构建、事实抽取、候选关系生成、模型收敛，正式落成独立上游层。

---

## Phase 5：更完整的 AI 推理系统

### 状态

部分启动。

### 目标

把构建层、推理层、行动层接起来，形成一个真正的 AI 推理系统。

### 当前落地状态

- **§T / temporal fragment**：已完成首版窄 scope
  - `Atom.time_index`
  - 程序级相对时间轴
  - 1 阶 Markov 约束
  - 现有 `cause / assoc / identify / effect / probability` 在时间展开图上的复用
  - A1 v2.2 对 clean `t-1 -> t` lag 直接产出 timed AST
- **§C / counterfactual fragment**：`S.C.1–S.C.6` 已以窄 scope 落地，
  当前包含 runtime + derivation/verifier + context/JSON 外部复核，
  并支持在适用时用 directed ancestral factorization 恢复观测 joint

也就是说，Phase 5 不再是“完全远期”；它已经落地了 temporal 和窄
counterfactual 两条子线，但还远没有形成完整的 Phase 5 体系。

### 可能包含

- 反事实
- 时间 / 动作
- 策略序列
- 主动调查与实验设计
- 从结果反推需要收集什么证据
- 交互式建模

### 说明

这一阶段里的语义跃迁需要**逐 fragment 显式立项**。  
当前已经落地的是 `§T` 与窄 `§C`；更宽的时间 / 动作 / 策略系统以及更强的
counterfactual ID 仍应按独立 charter 推进，而不是顺手往核心里塞。

---

## Phase 6：识别层完整化（= M1，2026-04-24 立项）

### 状态

**已大部分落地**。IV、mediation、多 mediator front-door 已完成；complete
ID 延后。

### 目标

把 Themis 识别层扩到 Pearl 因果识别文献 90% 以上的覆盖，成为**识别
能力比 DoWhy 更完整**的纯自家实现。这是扩展愿景（见 VISION.md "扩展
愿景"段）的第一个里程碑。

### 包含的 slice

- **IV 识别**：satisfies IV1/IV2/IV3 的工具变量搜索 + 公式构造 +
  conditional IV（~1 周）
- **中介识别**：NDE / NIE / CDE 三种效应的 identification + 对应公式
  + cross-world 假设显式声明（~2 周）
- **多 mediator 前门**：链式 P(Z1..Zk|X) 分解（~1 周）
- **Complete ID 算法**：Shpitser-Pearl 2006 实现（可选，~1-3 个月）
  ——如果时间有限，可延到 Phase 6.5

### 不包含

- 板块 11（数据驱动估计）——Phase 7 做
- 板块 12（因果发现）——Phase 8 做
- C++ 性能核心方法（Causal Forests / grf）——按需独立立项
- 研究级 SuperLearner TMLE 等 L4 方法——long-term defer

### 执行原则

- 完全自家写（sklearn 之上），**不接外部因果库作为 production backend**
- DoWhy 仅作 parity calibration（dev dependency，测试时用）
- V0-V5 verifier 配套扩展新 rule family：`iv_*`、`mediation_*`、`id_*`
- 每个 slice 配套 charter（仿 Phase 2.latent / Phase 5 格式）

### 完成标志

- IV + 中介 + 多 mediator 前门三个 slice 全部落地
- 所有新功能有对应 verifier rule + 独立重检
- eval set 至少 3 个新案例专门覆盖新识别策略
- DoWhy identify 的 parity test 全绿
- `CORE_STATUS.md` 列出 Phase 6 解冻段

### 时间预估

~4 周（不含 complete ID 算法；如含则 2-4 个月）

---

## Phase 7：数据驱动估计（= M2，2026-04-24 立项）

### 状态

**已落地第一版**。backdoor / front-door / IV / mediation 数值估计已完成，
Phase 14 又扩展到 dose-response estimator。

### 目标

让 Themis 从"给公式"升级到"给数字"——覆盖 70% 现实因果估计问题。

### 包含的 slice

**L1 基础估计器**（4 周）：
- IPTW / IPCW
- G-computation
- 2SLS（线性 IV 估计）
- 简单回归调整
- Heckman selection correction

**L2 现代估计器**（6-8 周）：
- DML (ATE)
- DR-Learner（constant effect）
- TMLE 基础版
- R-Learner（Nie-Wager 简化版）

### 不包含

- L3b C++ 核心的 Causal Forests / grf 原版——单独立项或 defer
- L4 SuperLearner TMLE 等研究级方法

### 执行原则

- 全部自家写，sklearn 之上
- 每个估计器配套 parity test，对照 EconML / CausalML 数字一致
- 新增 V6 级 verifier 规则族——审核估计过程的不变性（propensity 范
  围、cross-fitting 正确性、残差正交性等）

### 完成标志

- 9 个 L1-L2 估计器全部落地，每个有 DGP 测试 + parity test
- V6 verifier 规则族收敛
- 端到端 demo："给 Themis DAG + CSV 数据 + query，它返回带 CI 的效应
  数字 + 完整 derivation"
- `CORE_STATUS.md` 列出 Phase 7 解冻段

### 时间预估

~6-8 周

---

## Phase 8：发现 + 敏感性（= M3，2026-04-24 立项）

### 状态

**已落地第一版**。PC / FCI / LiNGAM discovery 与 E-value sensitivity
已经进入系统。

### 目标

补齐"从数据反推 DAG"和"结论对假设的鲁棒性"这两项——这是真实因果推
理应用里经常被要求的能力。

### 包含的 slice

**因果发现**（3-4 周）：
- PC 算法（constraint-based）
- FCI 算法（允许潜变量）
- LiNGAM（非高斯性 + 线性）
- 上游与 A1 prompt 集成（发现出的 DAG 作为候选给 LLM 确认）

**敏感性分析**（2-3 周）：
- E-value（VanderWeele 2017）
- Rosenbaum bounds
- Tipping-point analysis
- 对所有 Phase 7 估计器加 sensitivity hook

### 不包含

- NOTEARS 等深度学习因果发现——按需 vendor gCastle 或 defer
- 转移性（板块 9）——Phase 9+ 独立立项

### 完成标志

- PC / FCI / LiNGAM 三个发现算法落地
- E-value / Rosenbaum 两个敏感性方法落地
- 和 causal-learn 的 parity test 全绿
- 发现结果能无缝输入 Phase 6 识别层

### 时间预估

~4-6 周

---

## Phase 9+：按需扩展

完成 M1-M3（Phase 6-8）后，剩余板块按真实压力 / 用户需求独立立项：

- **板块 8 测量误差**：只有真实用户场景要求时启动
- **板块 9 转移性 / 泛化**：S-admissibility / selection diagrams
- **L3b 深度方法**：Causal Forests Python 重写（若用户追求 CATE 且可
  接受 Python 性能）
- **连续反事实**：§C 扩展
- **多 intervention / multi-target ID**：Phase 2.latent 里延后的方向

已落地的 Phase 9+ 主要扩展：

- **Phase 9 transport**：单源 selection-diagram transport identification
- **Phase 10 data-gap report**：把 failure / request / framing 转成结构化数据缺口
- **Phase 11 prompt / KB adapter**：gap_to_action prompt 与 KB adapter contract
- **Phase 12 bounds-first**：识别失败时优先给可审计 bounds
- **Phase 13 dose-response diagnostic**：识别 dose-response 问句并输出数据规格
- **Phase 14 dose-response estimator**：`themis.estimate(...)` 支持 dose-response curve
- **Phase 15 world-modeling pressure harness**：用 prompt examples 固定上游建模链路的真实卡点
- **L3 simulation 数据缺口诊断器压测**（2026-05-07）：10 cases 跨 7
  域真权威源压测 data_gap_report；过程修两个真 bug（front-door
  derivation-empty fallback / unattempted_layer_due_to_dispatch_conflict
  silent skip）+ 加一新 gap_kind `unmeasured_confounder_risk` 完整 lifecycle。
  详见 [docs/l3_simulation/README.md](docs/l3_simulation/README.md) 与
  `wall.md` plateau update。L3 价值层"真用户验证"仍待外部 recruitment unblock。

---

## 当前优先级原则

未来一段时间内，优先级按下面顺序排：

1. **当前范围内的理论闭合与工作流阻塞点**
2. **解释与可用性**
3. **参数补录与证据追踪**
4. **变量与问题充分性**
5. **显式立项的语义跃迁**
6. **自动世界建模**

也就是说：

- 先解决真实案例里“用起来不顺”的问题
- 再决定是否需要更强理论能力
- 不是反过来

---

## 现在最该做的事

不是再扩理论，而是先把当前 `0.15.0-dev` 状态收口，持续回答这三个问题：

1. 文档、版本、README、CORE_STATUS 是否准确描述当前代码？
2. 当前试跑案例里，第一个真正卡住的点是什么？
3. 这个卡点属于：
   - 工作流
   - 解释
   - 证据
   - 识别能力
   - 估计可靠性
   - 上游世界建模

只有当答案稳定重复出现，下一阶段才应该真正启动。

---

## 一句话版本

```text
先把 Themis 当前的推理、诊断、估计、KB/MCP bridge 状态说清楚；
再用真实案例压测，不要让文档继续停留在 v0.1 时代。
```
