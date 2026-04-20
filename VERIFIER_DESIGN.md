# Verifier Design

## 目的

这份文档回答一件事：

**Themis 要怎么落实 [VISION.md](C:\Users\12916\Desktop\项目\因果性ai\VISION.md) 里新版的"严格"定义。**

新版"严格"的关键句是：

> 在显式建模假设、变量定义、结构声明和数据来源给定后，
> 系统能够对相关性与因果结论给出**机器可验证的推导链**。

也就是说，Themis 不只是产出答案，还要产出**可以被独立核对的推导**。
独立核对的部分，叫 verifier。

---

## 类比：Lean

- Lean：大块复杂的 elaborator / tactic 代码把人写的证明展开成一个 proof term；
  一个很小、很简单的 **kernel** 只做一件事——检查 proof term 的类型对不对。
- 整个系统的可信度**只依赖 kernel 正确**。elaborator 可以瞎写、可以来自 LLM，
  只要最后 kernel 认可就行。

Themis 对应的拆法：

- **elaborator**：现有的 identifier / formula_builder / scheduler / numeric_estimator。
  它们观察图 + 查询 + Theta，**生成**一条 derivation。
- **verifier**：新层。只读 derivation + 上下文（graph / Theta / query），
  重跑每条命名规则，accept / reject。**不调用 elaborator 的任何函数**。

命名上避开已有的 "kernel"：`kernel_ast.schema.json` 指的是语言核心 AST，
不是可信校验器。新层的实现目录叫 `themis/verifier/`。

---

## 不是什么

Verifier 不负责、也不声称以下任何一件事：

- **不**证明图结构反映现实世界——那是 World Modeling 的职责
- **不**证明 Theta 参数对应真实分布——那是测量 / 数据来源的职责
- **不**证明变量定义得足够清楚——那是 framing（A0）的职责
- **不**替代 elaborator；elaborator 仍然负责解题，只是现在还要交"作业过程"

Verifier 只说一件事：

**在当前前提（graph / Theta / variable spec / query）给定的情况下，
这条 derivation 是否从前提正确推出了所声明的结果。**

---

## 操作定义：严格

满足下面四条，就认为一个查询的答案是"严格的"：

1. QueryResult 除了 `status / structural_result / numeric_result / formula` 之外，
   还带一个可序列化的 `derivation` 字段
2. `derivation` 的每一步都引用一条**命名规则**（见下文规则表）
3. 存在一个 verifier 函数，给定 derivation + 上下文就能机械地重跑每步
   并最终确认声明结果
4. verifier 的实现**不依赖 elaborator** 的内部函数；理想情况下可以用另一种
   语言重写一份来交叉验证

---

## Derivation 对象

### 基本单位

```python
@dataclass(frozen=True)
class DerivationStep:
    rule: str                           # 命名规则的 id，如 "backdoor_criterion"
    inputs: dict[str, Any]              # 该规则的输入
    output: Any                         # 该规则的输出
    step_id: str | None = None          # 可选：供后续步骤引用
```

### 整体结构

一条 derivation 是 `tuple[DerivationStep, ...]`：

- 有序列表
- 每步 `inputs` 只能引用：
  - **上下文对象**：graph / Theta / 原始 query / variable declarations
  - **之前某一步的 output**（通过 step_id）
- 最后一步的 output 必须等于 QueryResult 声明的 structural / numeric 结果
- 禁止引用 elaborator 的内部中间状态（例如 scheduler 的局部变量）

另外，derivation 不仅要“内部自洽”，还必须**绑定到当前 query**：

- 证明中的 `X / Y / given / intervention value`
  必须与 VerificationContext 里的 query 一致
- verifier 不能接受“同一张图上别的 identify 查询”的正确证明
- 否则它验证的就只是“这张图上存在某个 backdoor 证明”，而不是“当前 query 被证明了”

### 可序列化

derivation 要能序列化到 JSON 并再被 verifier 读回。所以：

- `inputs` / `output` 里的复合对象（Atom、FormulaExpr、graph）使用与
  `kernel_ast.schema.json` 和 `query_result.schema.json` 一致的 JSON 表示
- graph 以 `{nodes, edges}` 形式传入，不带 networkx 对象引用

---

## 信任边界

Verifier 的可信度建立在三件事上：

1. **Verifier 本身的实现正确**
   - 代码尽可能小、尽可能简单
   - 每条规则各自独立、不共享可变状态
   - 每条规则都有正反测试
2. **命名规则的形式定义正确**
   - 规则定义必须与 `因果图规则总览.md` 和 `理论框架_v0_1.md` 里的形式语义一致
   - 任何规则修改需要同时修改规则定义文档和所有相关测试
3. **上下文对象的序列化无歧义**
   - 同一个 graph / query 的 JSON 表示唯一
   - 不依赖字典遍历顺序等不稳定因素

Verifier **不**依赖：

- identifier / formula_builder 的实现细节
- pgmpy / networkx 之外的第三方库
- 任何运行时状态或缓存

---

## 第一批命名规则（Slice V0 scope）

只覆盖 **identify 查询（结构层）** 所需的最少规则。effect / probability 的
数值部分在 V1 / V2 处理，失败路径在 V3。

### R1. `graph_is_dag`

- **输入**：`graph`（节点集 V、有向边集 E）
- **输出**：`bool`
- **检查**：拓扑排序成功即 True；存在环则 False
- **来源**：`因果图规则总览.md` §1 结构层"确定的、封闭的"

### R2. `d_separation_check`

- **输入**：`graph, X, Y, Z`（X、Y 是节点；Z 是节点集合）
- **输出**：`bool`
- **检查**：按 Pearl d-separation 定义枚举 X–Y 的所有无向路径；
  每条路径上至少存在一个"被 Z 堵住"的节点。堵塞规则：
  - chain `a → b → c` 或 fork `a ← b → c`：b ∈ Z ⇒ 堵住
  - collider `a → b ← c`：b ∉ Z **且** b 的任何后代也不在 Z ⇒ 堵住
- **来源**：`因果图规则总览.md` d-分离相关章节

### R3. `backdoor_criterion`

- **输入**：`graph, X, Y, Z`（Z 是候选后门调整集）
- **输出**：`bool`
- **检查两条**：
  1. Z ⊂ V \ descendants(X)
  2. 在从 X 移除所有出边后的图 G_X̄ 中，Z 满足 R2 的 d_separation_check(X, Y, Z)
- **来源**：Pearl backdoor criterion；`因果图规则总览.md`

### R4. `backdoor_adjustment_formula`

- **输入**：`X, Y, Z`（X 干预值 x，Y 目标值 y，Z 调整集）
- **输出**：`FormulaExpr`，形如 `Σ_z P(Y=y | X=x, Z=z) · P(Z=z)`
- **检查**：输出的 FormulaExpr 在语法上与此模板一致；Z 为空时退化为
  `ProbabilityRefExpr(target=Y=y, given=(X=x,))`
- **前置条件**：必须有前一步 `backdoor_criterion(X, Y, Z) = True`

### R5. `identify_via_backdoor`

- **输入**：`query, graph, formula`
- **输出**：`StructuralResult(value=True, ...)`
- **检查**：存在调整集 Z 使得：
  - `backdoor_criterion(X, Y, Z) = True`（引用 R3 步骤的 output）
  - formula 等于 `backdoor_adjustment_formula(X, Y, Z)` 的输出（引用 R4）
  - `criterion` 必须引用一条真正的 `backdoor_criterion` 步骤
  - `formula` 必须引用一条真正的 `backdoor_adjustment_formula` 步骤
  - 被引用的 `formula` 步骤输出必须是 `FormulaExpr`

也就是说，R5 不接受“随便找一个早期步骤来充当公式见证”。

一条成功的 identify derivation 的典型形状：

```
[
  step_id="s1", rule="graph_is_dag",    output=True
  step_id="s2", rule="backdoor_criterion", inputs={X, Y, Z, graph}, output=True
  step_id="s3", rule="backdoor_adjustment_formula", inputs={X, Y, Z}, output=<formula>
  step_id="s4", rule="identify_via_backdoor", inputs={s2, s3}, output=StructuralResult(True, ...)
]
```

---

## 后续规则（V1 起）

### R6. `probability_ref_lookup`（V1）

- **输入**：`theta, probability_key`
- **输出**：`float`
- **检查**：`theta.entries[key] = output`；key 不在则 reject（对应现有
  `InsufficientTheta`，只是 verifier 角度）

### R7. `formula_evaluation`（V1）

- **输入**：`formula, theta`
- **输出**：`float`
- **检查**：按 FormulaExpr 语义递归重算，expected_output 与 claimed_output 在
  浮点容差内相等。子步骤可展开为 R6 的多个应用，或作为"黑盒评估"单步
  （取决于 derivation 是否需要记录枚举细节）

### R8. `unidentifiable_via_backdoor`（V3）

- **输入**：`query, graph`
- **输出**：`StructuralResult(value=False)`
- **检查**：枚举所有候选 Z ⊂ V \ (descendants(X) ∪ {X, Y})，确认每个 Z 都不满足
  R3；结构上已经穷尽了后门路线

---

## 模块划分

| 现有模块 | 角色 |
|----------|------|
| `themis.input.*` | 前提收集（graph / Theta / declarations） |
| `themis.runtime.structural_solver` | elaborator（d-sep、路径枚举） |
| `themis.runtime.formula_builder` | elaborator（生成公式 AST） |
| `themis.runtime.numeric_estimator` | elaborator（数值求值） |
| `themis.runtime.scheduler` | elaborator（调度各 dispatcher） |
| **`themis.verifier.*`（新）** | **verifier** |

`themis.verifier/` 里预期的文件：

```
themis/verifier/
  __init__.py
  rules.py          # R1..R5 的实现
  verify.py         # 顶层 verify(derivation, context) 入口
  context.py        # VerificationContext 类型
  errors.py         # VerificationError 及子类
```

---

## Elaborator 改动

每个现有 dispatcher 需要在产出 QueryResult 的同时产出 derivation：

- `_dispatch_identify` → 附加 `derivation` 字段到 QueryResult
- `_dispatch_effect` / `_dispatch_probability` → V1 起附加

`QueryResult.derivation: tuple[DerivationStep, ...] = ()` 作为可选字段加入。
老代码不产 derivation 也能正常运行（向后兼容）。

---

## 渐进路线

- **Slice V0**：DerivationStep 类型 + identify dispatcher 产出 derivation
  + R1/R2/R3/R4/R5 规则 + verifier 入口
- **Slice V1**：R6/R7 数值规则；effect / probability 也开始产 derivation
- **Slice V2**：derivation 序列化 schema（`derivation.schema.json`）+ 外部工具可读
- **Slice V3**：失败路径（不可识别 / d-分离）也产 derivation（R8 等）
- **未来**：前门、ID 算法、反事实 等随理论扩展新增命名规则

每一步都要求：

- 所有已有 e2e 测试零改动通过（derivation 是可选字段）
- 新规则有正反两种测试（正确 derivation accept，被篡改的 reject）

---

## 与其他层的边界

| 层 | 职责 | 对严格性的贡献 |
|----|------|----------------|
| World Modeling | 决定图结构和变量定义从何而来 | 给 verifier 提供**可信的前提** |
| Framing（A0） | 检查变量定义是否足够操作化 | 给 verifier 确认**前提已足够明确** |
| Theta / 数据来源 | 决定参数值 | 给 verifier 提供**可信的数值前提** |
| Elaborator（现有 runtime） | 给定前提时生成 derivation | 产出待校验对象 |
| **Verifier（新）** | 检查 derivation 对不对 | **保证"给定前提 → 结论"这一步严格** |

一条明确的话：

**Verifier 让 Themis 严格推出"在这些假设下结论成立"；
它不负责让那些假设本身严格。**

---

## 成本与风险

### 成本

- DerivationStep 类型 + 序列化一次性搭好
- 每个 dispatcher 要改造一次，让它产 derivation
- V0 只覆盖 identify，大约是新增 ~500 行加少量改动；能在一周内跑通

### 风险

- **derivation 膨胀**：数值层的 sum over domain 如果每个 z 都记一条会很冗长；
  对策是 R7 作为"黑盒评估"单步，或提供压缩表示
- **规则定义漂移**：任何规则的形式修改要三处同步：规则实现、规则定义文档、规则测试；
  漂移时测试会失败
- **图投影的序列化**：networkx 图要有稳定 JSON 表示，否则 verifier 跨进程跑时
  可能出现节点顺序差异；对策是给 graph 上显式 `sorted` 规范化

---

## 成功标准

Slice V0 完成时：

- 所有 identify 查询的 QueryResult 都附带非空 derivation
- `verify(derivation, context)` 对所有现有 e2e 测试里的 identify 结果返回 accept
- 故意破坏 derivation（改 Z、改 formula、删一步、换成别的 query、把公式引用指到非公式步骤）→ verify 返回 reject 并说明失败规则
- 现有 234 个测试全绿，新增 V0 规则的单元测试也全绿

---

## 一句话

Verifier 是 Themis 的可信核对层，
它不保证前提真实，但在前提给定后，保证结论是从前提严格推出的。
