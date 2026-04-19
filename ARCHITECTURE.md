# 架构说明 v0.1

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

```text
┌─────────────────────────────────────────────────────────┐
│  input 层                                               │
│    DSL parser                                           │
│    syntactic validator (JSON Schema 语法校验)           │
│    semantic validator (语义规则校验)                    │
├─────────────────────────────────────────────────────────┤
│  runtime 层（自己写）          │  oracle 层（对照）     │
│    实例化                       │    pgmpy 适配器       │
│    图投影                       │    ananke 适配器(v0.2)│
│    结构求解(d-sep / 后门)       │    差分比对器         │
│    公式 AST 构造                │                       │
│    数值估计 ★stub v0.1          │                       │
│    composite confidence ★stub   │                       │
│    四态调度                     │                       │
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
syntactic validate
   │
   ▼
semantic validate
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

下面每个模块对应一个 Python 文件。v0.1 阶段只要求接口签名，实现可以是 `raise NotImplementedError`。

### 5.1 input 层

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `parser` | 把 DSL 文本或 JSON 转成 AST dict | str / bytes | dict |
| `syntactic_validator` | 用 JSON Schema 校验 AST 语法 | dict | dict（不变）或抛错 |
| `semantic_validator` | 校验语义规则 | dict | Program 对象 |

**语义规则清单（semantic_validator 的职责）**：

- `probability.given` 是 `target` 结构父集或其子集
- 公式 AST 里无自由值变量
- `sum.over` 是 ground atom
- 原子中的对象常量必须在 `D` 中声明
- `forall` 变量在原子里必须被引用
- 查询引用的原子必须在实例化后出现在 `V` 中

### 5.2 runtime 层

| 模块 | 职责 | v0.1 状态 |
|---|---|---|
| `instantiation` | 对 forall 声明在 D 上实例化 | 必须实现 |
| `graph_projection` | 把实例化后的 cause 集合编译成 DAG | 必须实现 |
| `structural_solver` | d-sep、后门、调整集判定 | 必须实现 |
| `formula_builder` | 构造合法的公式 AST | 必须实现 |
| `numeric_estimator` | 基于 Theta 估算数值 | ★ v0.1 stub |
| `confidence_calc` | 计算 composite confidence | ★ v0.1 stub |
| `scheduler` | 四态调度（结构/数值/调查/语言外） | 必须实现 |
| `investigation_pusher` | 缺失信息转调查请求 | 必须实现 |

### 5.3 oracle 层

| 模块 | 职责 | v0.1 状态 |
|---|---|---|
| `pgmpy_adapter` | 把 Program 转成 pgmpy 模型并跑 d-sep / 后门 | 实现 |
| `ananke_adapter` | 用 ananke 跑 ID 算法 | v0.2 引入 |
| `differential` | 对比 runtime 与 oracle 的结果 | 实现 |

### 5.4 output 层

| 模块 | 职责 |
|---|---|
| `result_orchestrator` | 把 runtime 的内部状态拼成 query_result schema 的对象 |
| `explainer` | 生成自然语言解释（路径、缺失项、调查建议） |

### 5.5 底层

- `networkx`：DAG 表示
- `jsonschema`：syntactic_validator 底座
- Python dataclass：Program / Atom / ValuedAtom / FormulaExpr 等类型

---

## 6. v0.1 的 stub

以下模块在 v0.1 只写签名 + 占位：

### 6.1 numeric_estimator

- 当任何查询需要数值时，直接返回 `needs_investigation` 状态，缺失信息标为"数值估计器未实现"
- 这让 v0.1 能自然跑通"结构可解 + 调查可推进"的闭环，推迟数值能力到 v0.2

### 6.2 confidence_calc

- 输入：若干参与方的 confidence 列表（observation 的、probability 的）
- v0.1 占位实现：取最小值
- 规范注释里必须写"这是占位，composite confidence 的正式语义待 v0.2 定义"

### 6.3 ananke_adapter

- v0.1 不实现
- 目录下留一个 `# TODO v0.2: wire ananke for ID algorithm` 的空文件或注释

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
  causal_kernel/
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
      numeric_estimator.py    # stub v0.1
      confidence_calc.py      # stub v0.1
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
- 数值估计（numeric_estimator 实现）
- composite confidence 正式定义
- 原子类型 / 值域系统（atom.schema.json 扩展）
- 经验统计语句（`empirical_prob`）

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
v0.1 的数值估计和 composite confidence 是 stub，正式语义延后到 v0.2。
```
