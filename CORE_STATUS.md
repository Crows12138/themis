# Themis Core Status

> 更新时间：2026-04-21

这份文档只回答一件事：

**当前 Themis 核心到底完成到了什么程度。**

它不是愿景文档，也不是长期路线图。  
长期目标看 [VISION.md](C:\Users\12916\Desktop\项目\因果性ai\VISION.md)，阶段路线看
[ROADMAP.md](C:\Users\12916\Desktop\项目\因果性ai\ROADMAP.md)，上游建模层看
[WORLD_MODELING.md](C:\Users\12916\Desktop\项目\因果性ai\WORLD_MODELING.md)。

---

## 一句话结论

**Themis 作为“已知模型下的静态因果推理内核”，已经基本成型。**

更具体地说：

- 已经能在给定结构、给定参数时，对 `cause / assoc / identify / effect / probability`
  做结构推理、公式构造、数值求值、缺口报告和最小工作流闭环
- 已经开始具备“严格推导”的形态：核心结果可附带 derivation，由独立 verifier 复核
- 还没有完成上游世界建模、完整变量框定闭环、时序语义、潜变量 / ADMG / ID 这些更大层次

所以当前最准确的定位是：

**一个可运行、可验证、可补录的静态因果推理内核。**

---

## 当前核心范围

当前核心范围只包含：

1. **已知变量、已知结构、已知/部分已知参数** 下的推理
2. 因果与相关的**静态 DAG** 语义
3. 结构查询、数值查询、缺参数闭环
4. 结果解释、confidence、以及 derivation verifier

当前核心范围明确**不包含**：

- 自动从语料构建变量和关系
- 时间 / 动作序列语义
- 潜变量 / 双向边 / ADMG
- 前门 / 完备 ID
- 反事实
- 通用 agent 行为

---

## 已完成能力

### 1. 语言与输入

- JSON AST + schema
- 有限对象域
- `forall` 实例化
- `cause / probability / observation / query`
- `variableDeclaration`（predicate 层 metadata，opt-in）

### 2. 结构推理

- DAG 投影
- `cause`
- `assoc`
- `identify`
- 后门调整集
- 条件 identify（`given`）
- 路径 / 开放路径 / supporting_paths

### 3. 数值层

- `Theta`
- `probability` 查询数值求值
- `effect` 查询通过后门公式数值求值
- 布尔与分类值域
- 缺参数时精确报缺，不瞎算

### 4. 工作流层

- `needs_investigation`
- investigation grouping
- parameter skeleton
- skeleton bundle 提取
- 回填 merge
- 重跑 diff

### 5. 解释与 framing

- 中文 explanation
- 解释与公式/结果的一致性
- `framing_notes`
- A0：问题定义不充分的 advisory 检查

### 6. confidence

- 正式规则：`min(non-None inputs)`
- 结果上可输出 `confidence`
- 解释文本中可呈现 confidence

### 7. 严格推导层（verifier）

已完成到：

- **V0**：`identify` 结构证明
- **V1**：`effect / probability` 数值证明
- **V2**：derivation JSON round-trip
- **V3**：负结构 witness
- **V4**：正结构 witness
- **V5**：context JSON round-trip

也就是说，当前已经能把：

- derivation
- graph
- query
- theta

都序列化出来，然后由 verifier 独立 accept / reject。

---

## V0..V5 当前状态

### V0：Identify Derivation

状态：**完成**

已具备：

- `backdoor_criterion`
- `backdoor_adjustment_formula`
- `identify_via_backdoor`
- verifier 绑定到当前 query
- 真实公式见证约束

### V1：Numeric Derivation

状态：**完成**

已具备：

- `probability_ref_lookup`
- `formula_evaluation`
- `numeric_result`
- `effect / probability` 数值证明与 query/formula 绑定

### V2：Derivation Serialization

状态：**完成**

已具备：

- `derivation.schema.json`
- derivation round-trip
- malformed derivation 统一报 `DerivationSerializationError`

### V3：Negative Structural Witnesses

状态：**完成**

已具备：

- `unidentifiable_via_backdoor`
- `d_separated`
- `no_directed_path`
- theorem family 绑定

### V4：Positive Structural Witnesses

状态：**完成**

已具备：

- `cause_via_directed_path`
- `d_connected_via_open_path`
- supporting path 集合完整性检查

### V5：VerificationContext Serialization

状态：**完成**

已具备：

- `context_to_dict / context_from_dict`
- graph + query + theta JSON 化
- malformed context 统一报 `DerivationSerializationError`
- `effect / probability` query value 只允许字面量

---

## 基本完成但还不算“更大系统完成”的部分

### 1. Framing 只到 advisory

当前有：

- `variableDeclaration`
- `framing_notes`

当前没有：

- 变量定义补录 workflow
- “问题没框清就拒绝 effect/probability”的强 gate

### 2. 真实案例已经能跑，但还没有变成系统上游

当前有：

- `exercise_waist`
- `sleep_focus`
- `tutoring_exam`

当前没有：

- 从真实语料自动构变量
- 从事实语料自动产候选关系

### 3. Confidence 已经是正式语义，但证据来源追踪还没完成

当前有：

- numeric confidence
- explanation 中的 confidence 文案

当前没有：

- 完整 source 结构化
- 最弱证据来源追踪

---

## 还没有开始或明确延后的部分

### 1. 上游世界建模

包括：

- 变量框定器完整闭环
- 事实抽取
- 候选关系生成
- 模型收敛

这部分是
[WORLD_MODELING.md](C:\Users\12916\Desktop\项目\因果性ai\WORLD_MODELING.md)
定义的上游层，不是 Themis 当前核心的一部分。

### 2. 更强识别能力

包括：

- 潜变量
- 双向边
- ADMG
- 前门
- 完备 ID

当前明确延后，等待真实案例逼出需求。

### 3. 时序语义

当前还没有真正的：

- 时间索引
- 时间一致性检查
- 动作序列
- 动态因果过程

### 4. 强问题 gate

当前系统还没有做到：

- 变量定义不充分时自动拒绝数值推理

现在只有 advisory 提示，不会拦住求值。

---

## 现在可以认为“收口”的部分

如果只看 Themis 核心，这一批内容已经可以视为当前收口面：

- 静态 DAG 推理语义
- `cause / assoc / identify / effect / probability`
- 结构结果与数值结果
- parameter fill-back workflow
- confidence
- framing advisory
- derivation verifier V0..V5

这意味着：

**接下来如果继续改 Themis 核心，应该优先是小修小补和边界澄清，不应再随意扩大语义面。**

---

## 当前建议

当前更合理的节奏不是继续膨胀核心，而是：

1. 把当前 Themis 核心视为**稳定收口候选**
2. 继续拿真实案例试跑
3. 让下一阶段需求从真实痛点里长出来

也就是说：

- 如果真实痛点落在“变量定义补录”，就推进 Variable Framer workflow
- 如果真实痛点落在“来源追踪”，就推进 source metadata
- 如果真实痛点落在“后门不够”，才进入更强识别阶段

---

## 最短版本

```text
Themis 核心已经基本成型：
它能在已知模型下做静态因果推理、数值求值、缺参数补录和机器可验证推导。

但它还不是完整世界建模系统；
变量框定闭环、时序语义、潜变量/ADMG、自动语料建模都还在核心之外。
```
