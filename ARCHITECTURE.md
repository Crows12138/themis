# 架构说明 v0.1

> **当前版本指针**：此文件描述的是 v0.1（静态 DAG 内核）阶段的分层架构。
> 系统已演化到 0.15.0-dev（含 Phase 6-15 + L3 simulation 安全网，详见
> [`CORE_STATUS.md`](CORE_STATUS.md)）。本文件保留作为 v0.1 基线参考——
> 四层划分 / 依赖方向 / Oracle 定位等结构问题在演化中保持稳定。最新
> Phase 解冻列表见 [`COVERAGE_MAP.md`](COVERAGE_MAP.md) 与
> [`ROADMAP.md`](ROADMAP.md) "Phase 9+" 节。

本文件固化因果推理内核的分层、依赖方向与设计意图。

它不讨论算法细节（见 `理论框架_v0_1.md`、`formula_ast_spec_v0_1.md`），只回答下面几个结构问题：

1. 系统分成几层，每层做什么
2. 依赖方向是什么，哪些方向是禁止的
3. Oracle 的定位为什么不是一个普通中间层
4. 哪些模块是 v0.1 的 stub，v0.2 要怎样接入
5. 文件布局是什么样的
6. 哪些是反模式，哪怕为了短期方便也不要做

---

## 1. 四层划分

系统分四层，自上而下：

- **input 层**：把用户输入（文本 DSL 或 JSON）转成合法的 AST
- **runtime 层**：在 AST 上执行结构与数值推理
- **output 层**：把 runtime 的内部结果整理为对外返回的 query_result
- **底层（library 层）**：通用第三方工具

runtime 旁边并列一个**对照位**：

- **oracle 层**：开发期的独立实现对照者，不是运行期依赖

---

## 2. 架构图

> 下面这张是 v0.1 的四层图，手画的，随本文件一起冻结在 v0.1。
> **当前全景图由 `scripts/build_arch_spec.py` 生成**——覆盖 `themis/` 下每个
> 非空包，每个方块钉到真实文件、由 git 在指定 commit 上核验，图上印的每个数
> 都是生成时现场量出来的。判断（哪些方块、算哪一层、谁连谁）仍是手写的，
> 但被 `tests/test_a_picture_of_this_repo_counts_what_it_prints.py` 钉到
> 仓库能否认的那一面。渲染是仓库外的事，仓库里只留必须保持为真的那一半。
>
> 用法 `python scripts/build_arch_spec.py <输出.json>`，再用 archify 渲染：
> `node <archify>/bin/archify.mjs render architecture <输出.json> <输出.html> --quality showcase --repo-root .`。
> 签进仓库的那一页就是这条命令的输出；页面上除了标签还带着 spec 的其他内容（比如它钉的
> commit），所以图过期了要重渲染，不要手改。当前那一份签在 `docs/架构图/` 下，双击 `.html` 就能看。
>
> **签进仓库的图会烂，所以它被钉住了**：套件比对提交的 spec 与现场重建的
> spec，只放过它钉的那个 commit；再逐段比对 spec 上的字是否真出现在渲染出的
> 页面里，免得 spec 更新了而图没有。任何一条对不上就红，修法是重跑上面两步。

```text
┌─────────────────────────────────────────────────────────┐
│  input 层                                               │
│    DSL parser                                           │
│    syntactic validator (JSON Schema 语法校验)           │
│    semantic validator (语义规则校验)                    │
├─────────────────────────────────────────────────────────┤
│  runtime 层（自己写）          │  oracle 层（对照）     │
│    实例化                       │    pgmpy 适配器       │
│    图投影 + DAG 不变量          │    ananke 适配器(v0.2)│
│    结构求解(d-sep / 后门)       │    差分比对器         │
│    公式 AST 构造                │                       │
│    theta 编译                   │                       │
│    数值估计（递归求值）          │                       │
│    composite confidence (min)   │                       │
│    四态调度 + 图级校验          │                       │
│    调查推进                     │                       │
├─────────────────────────────────────────────────────────┤
│  output 层                                              │
│    result orchestrator                                  │
│    explainer                                            │
├─────────────────────────────────────────────────────────┤
│  底层                                                   │
│    networkx / jsonschema / dataclass                    │
└─────────────────────────────────────────────────────────┘
```

单向数据流：

```text
text / json
   │
   ▼
parse → AST
   │
   ▼
syntactic validate          (schema)
   │
   ▼
semantic validate [pre]     (dict-level rules)
   │
   ▼
instantiate → ground
   │
   ▼
project → G(M)
   │
   ▼
semantic validate [post]    (graph-level rules; e.g. probability_parents)
   │
   ▼
build theta
   │
   ├─────────────────────┐
   ▼                     ▼
runtime             oracle (可选)
   │                     │
   └──────┬──────────────┘
          ▼
    差分比对（可选）
          │
          ▼
       result
          │
          ▼
     orchestrator
          │
          ▼
       explainer
          │
          ▼
        用户
```

---

## 3. 依赖方向规则

下面是**强制约束**。违反任何一条都会让系统失去当前分层带来的好处。

### 3.1 基本方向

- input 层 → runtime 层：允许
- runtime 层 → output 层：允许
- 任何层 → 底层：允许
- output 层 → runtime 层：禁止（output 是被动整理，不能回调 runtime 做推理）
- runtime 层 → input 层：禁止
- **runtime 层 → oracle 层：禁止**
- **input / output → oracle 层：禁止**

### 3.2 关于 oracle

- oracle 从 input 层拿到 AST（和 runtime 同一份输入）
- oracle 产出和 runtime 同构的结果
- 差分比对器是一个独立模块，从两边各取结果做比对
- **oracle 从不回写 runtime，也从不参与生产路径**

### 3.3 结果

- 任何发布二进制 / 部署环境：只需 runtime + input + output + 底层
- oracle 层和所有 pgmpy / ananke 依赖是**开发/测试期工件**
- 用户没装这些依赖时系统必须照常工作，仅失去差分校验

---

## 4. Oracle 的定位

### 4.1 Oracle 不是下游，不是上游，是**平行对照者**

`runtime` 和 `oracle` 是两个独立系统，各自读取同一份 AST，各自产出同构的结果，由差分比对器判断是否一致。

```text
   AST
    ├─────────────────────┐
    ▼                     ▼
 runtime              oracle
    │                     │
 my_result          oracle_result
    └─────────┬───────────┘
              ▼
           差分比对
```

### 4.2 为什么不能用 oracle 做真推理

如果 runtime 直接调用 oracle 的推理结果（比如"d-sep 这一步我调 pgmpy 算吧"），就会出现：

- 生产部署必须带上 oracle 的依赖（pgmpy 不是小包）
- oracle 数据模型渗透进 runtime（pgmpy 的 BayesianNetwork 不认识我们的 atom）
- 失去差分校验能力（自己和自己比永远一致）
- 换 oracle 时改动会蔓延

所以 oracle **只承担对照职责**，runtime 必须自己写一份哪怕粗糙但独立的实现。

### 4.3 Oracle 的主要用途

- 开发期差分测试：每条查询跑两遍结果比对
- 回归测试：新特性不破坏对经典场景的一致性
- 算法调试：runtime 出错时反查"标准答案"是什么

---

## 5. 模块清单

### 5.1 input 层

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `parser` | 把 DSL 文本或 JSON 转成 AST dict | str / bytes | dict |
| `syntactic_validator` | 用 JSON Schema 校验 AST 语法 | dict | dict（不变）或抛错 |
| `semantic_validator` | 校验语义规则（两阶段） | dict / (ground, graph) | Program 对象 / 无返回（仅断言） |

**语义校验分两阶段**：

- **pre-graph**（`validate_program(ast, checks=...)`，作用在 dict AST 上）：
  - `objects`：原子中的对象常量必须在 `D` 中声明
  - `forall_usage`：`forall` 变量必须在原子里被引用
  - `bound_variables`：cause / probability 语句里每个 VarTerm 必须在 forall 中声明
  - `ground_observations`：观察原子不含 VarTerm
  - `ground_queries`：查询原子不含 VarTerm（v0.1 只答 ground 查询）
- **post-graph**（`validate_against_graph(ground, graph, checks=...)`，作用在实例化 + 投影之后）：
  - `probability_parents`：probability.given ⊆ parents(target) in G(M)
- **utility**：
  - `validate_formula(formula)`：公式 AST 里无自由值变量、`sum.over` ground（运行时出公式时自动调用）

### 5.2 runtime 层

| 模块 | 职责 | 状态 |
|---|---|---|
| `instantiation` | 对 forall 声明在 D 上实例化，保留 ValuedAtom 上的具体 value | 已实现 |
| `graph_projection` | 把实例化后的 cause 集合编译成 DAG；强制 DAG 不变量 | 已实现 |
| `structural_solver` | 有向路径 / d-sep / 开放路径 / 后门 / 最小调整集 | 已实现 |
| `formula_builder` | 构造合法的公式 AST（任意 cardinality 的后门调整，链式法则展开） | 已实现 |
| `theta_builder` | 从 ground probability 语句编译 Theta；冲突键报错；按出现值推断 atom 域 | 已实现 |
| `numeric_estimator` | 递归公式求值（constant / probability_ref / product / sum）；缺条目抛 `InsufficientTheta` 携带精确 key | 已实现 |
| `confidence_calc` | 计算 composite confidence（min 规则） | 已实现（v0.2 正式规则，见 confidence_rfc_v0_2.md） |
| `scheduler` | 四态调度 + 图级校验 + 建 Theta + 调 confidence + 调 investigation | 已实现 |
| `investigation_pusher` | 缺失信息转调查请求（按 MissingKind 映射 action） | 已实现 |

### 5.3 oracle 层

| 模块 | 职责 | 状态 |
|---|---|---|
| `pgmpy_adapter` | 把 Program 转成 pgmpy 模型并跑 d-sep / 后门；显式补齐 pgmpy 1.1.0 空调整集怪癖 | 已实现 |
| `ananke_adapter` | 用 ananke 跑 ID 算法 | v0.2 引入 |
| `differential` | 对比 runtime 与 oracle 的结果，三态（agree / disagree / not_applicable） | 已实现 |

### 5.4 output 层

| 模块 | 职责 |
|---|---|
| `result_orchestrator` | 把 runtime 的内部状态拼成 query_result schema 的对象 |
| `explainer` | 生成自然语言解释（路径、缺失项、调查建议） |

### 5.5 workflow 层（v0.2+）

跨多次运行、多步流程的工具化能力；组合既有 input / runtime / output，从不越层操作 runtime 内部。

| 模块 | 职责 |
|---|---|
| `parameter_fill` | 参数回填三步闭环：`extract_skeleton_bundle` / `merge_skeleton_bundle` / `diff_runs`（slice 9.x-C） |

### 5.6 底层

- `networkx`：DAG 表示
- `jsonschema`：syntactic_validator 底座
- Python dataclass：Program / Atom / ValuedAtom / FormulaExpr 等类型

---

## 6. 占位状态

### 6.1 ananke_adapter

- v0.1 不实现；只留入口
- 目录下保留 `# TODO v0.2: wire ananke for ID algorithm` 注释，供将来接 Shpitser-Pearl ID 算法用

### 6.2 已**离开**占位的模块（历史参考）

- `numeric_estimator`：slice 6 后已是真实的递归公式求值器 + Theta 查表，`effect` / `probability` 查询可返回 `NUMERICALLY_SOLVED`
- `investigation_pusher`：slice 5 后是真实的 `MissingKind → InvestigationAction` 映射
- `confidence_calc`：slice 9 后正式化为 v0.2 min 规则；`_gather_input_confidences` 接入来源索引（`build_probability_source_index` / `build_observation_source_index`），按 `confidence_rfc_v0_2.md` §3 采集 probability slot + observation slot。空输入仍返回 None（保 v0.1.0 兼容）

---

## 7. 反模式（不要做）

### 7.1 不要让 runtime 依赖 oracle

哪怕是"就这一步调 pgmpy 方便"也不行。一旦出现，oracle 就不再独立。

### 7.2 不要让 output 回调 runtime 做推理

explainer 需要路径数据时，应由 runtime 在 result 中预先填好，而不是 explainer 回头再问一次。

### 7.3 不要把语法校验和语义校验糅在一个函数

两者的失败模式、报错信息、用户建议都不一样。`validate(program)` 这个函数不要存在。

### 7.4 不要把 atom 展平成字符串再塞进中间结构

atom 的 predicate 和 args 要保持结构化，直到最后一步渲染。字符串化破坏保真。

### 7.5 不要在 v0.1 假装 confidence 计算已定义

占位必须明文标 stub，不要写"平均值"或"乘积"然后让人误以为这是最终算法。

### 7.6 不要把 schema 文件放到 Python 包里

schema 是跨语言资产，留在项目根的 JSON 文件里，Python 包通过路径加载，不要内嵌。

---

## 8. 文件布局

```text
因果性ai/
  # 规范文件（扁平放项目根）
  atom.schema.json
  kernel_ast.schema.json
  query_result.schema.json
  minimal_example_v0_1.json
  理论框架_v0_1.md
  formula_ast_spec_v0_1.md
  因果图规则总览.md
  ARCHITECTURE.md

  # Python 包
  themis/
    __init__.py
    types.py                  # 共享 dataclass

    input/
      __init__.py
      parser.py
      syntactic_validator.py
      semantic_validator.py

    runtime/
      __init__.py
      instantiation.py
      graph_projection.py
      structural_solver.py
      formula_builder.py
      theta_builder.py
      numeric_estimator.py
      confidence_calc.py      # v0.1 placeholder (min rule)
      scheduler.py
      investigation_pusher.py

    oracle/
      __init__.py
      pgmpy_adapter.py
      ananke_adapter.py       # stub v0.2
      differential.py

    output/
      __init__.py
      result_orchestrator.py
      explainer.py

  # 测试
  tests/
    __init__.py
    test_input/
    test_runtime/
    test_oracle/
    test_output/
    test_e2e/

  README.md
```

---

## 9. 版本演化策略

### 9.1 v0.1 → v0.2 可能加入

- 反事实语义（`counterfactual` 查询类型）
- ID 算法（ananke_adapter 上线）
- composite confidence 正式定义（v0.1 是 min 占位）
- 原子类型 / 值域系统（atom.schema.json 扩展，目前值域靠 theta_builder 从语句里推断）
- 经验统计语句（`empirical_prob`）
- 布尔原子的互补自动补齐（写 `P(y=true|..)=0.2` 不用再手写 `P(y=false|..)=0.8`）

### 9.2 破坏性 vs 非破坏性

- 新增 statement 类型：非破坏（通过 `extensions` 字段或新 version 号）
- 修改已有 $def：破坏，必须升 version
- 新增 query 类型：非破坏，`query.oneOf` 追加一项
- 修改公式算子集：破坏，必须升 formula_ast_spec 版本

### 9.3 版本协商

- kernel_ast 顶层 `version` 字段是硬约束
- 未来 runtime 必须显式声明支持的版本集合
- 不做隐式版本迁移

---

## 10. 一句总纲

```text
input 做校验，runtime 做推理，oracle 做对照，output 做整理；
runtime 不依赖 oracle，oracle 不进入生产路径；
数值估计 + composite confidence 均已接入（slice 6 / slice 9）。
```
