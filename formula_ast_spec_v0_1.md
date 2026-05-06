# 公式子语言规范 v0.1

> **当前版本指针**：本文件是 v0.1（backdoor / 基本公式）阶段的公式
> AST 子语言规范。系统已演化到 0.15.0-dev，公式 AST 实际已扩展支持
> 前门（Phase A6）/ ADMG c-factor（Phase 2.latent §S3.b.2，Tian-Pearl
> Lines 1-6）/ Bareinboim transport / mediation NDE/NIE/CDE 公式形态
> （详见 [`CORE_STATUS.md`](CORE_STATUS.md)）。本文件的 `Sum` /
> `Product` / `ProbabilityRef` / `BindDecl` / `VarRef` 五个核心节点
> 类型在所有扩展中**保持稳定**——新公式形态都是这五类的组合，没有
> 引入新节点类型。schema 权威：[`query_result.schema.json`](query_result.schema.json)
> 的 `formula` 子定义。

本文件规范 `query_result.schema.json` 中 `formula` 字段使用的公式 AST。

公式 AST 是因果内核的一门子语言，用来表达识别查询（`identify`）成功时返回的结构化公式，也可被数值层继续消费（估计、化简、缓存）。

---

## 1. 设计范围

公式子语言只负责表达**识别成功后的数值公式**。

它不包含：

- 干预操作符 `do`（识别成功意味着 `do` 已被消掉）
- 任意观察统计或经验频率
- 动态逻辑、时态算子
- 任何结构层查询（cause、assoc 不返回公式）

识别失败时不应返回公式，应通过 `status` 或 `missing_information` 表达。

---

## 2. 算子集

v0.1 只定义四个算子：

- `constant`：字面数值常量
- `probability_ref`：模型分布中的一个条件概率项引用
- `product`：若干子表达式的乘积
- `sum`：对某原子的取值域做显式求和，并绑定一个值变量

不引入独立的 `condition` 或 `marginalize`：

- `condition` 的功能内嵌于 `probability_ref.given`
- `marginalize` 的功能由 `sum` 提供

---

## 3. 原子与值

### 3.1 原子引用

公式中所有原子引用复用 `atom.schema.json` 中定义的结构化 `atom` 对象，与 kernel_ast 共享命名空间，保持保真性。

### 3.2 值表达式

`valueExpr` 可以是：

- 布尔、数值、字符串三种字面值之一
- 或一个 `varRef`，引用由某个 `sum` 绑定的值变量

### 3.3 带值原子

`valuedAtom = { atom, value? }`。`value` 可缺省。

`probability_ref` 的 `target` 与 `given` 中每一项都必须是 `valuedAtom`。

`value` 缺省时表示该原子的值由外部查询上下文绑定——典型情形是 `identify` 查询返回公式中的 `target` 原子（其值来自查询或后续数值层替换）以及 `given` 原子。这些原子不参与公式内部的形式良好性判定（见 §4.3）。

---

## 4. 绑定与作用域

### 4.1 `sum` 的三要素

```text
sum {
  bind: { name: "z" }   // 新引入的值变量
  over: <ground atom>   // 被求和原子，必须是 ground atom
  body: <expression>    // 引用 z 的子表达式
}
```

### 4.2 `over` 的 ground 约束

`sum.over` 必须是 ground atom，即 `over.args` 中不含 `{type: "var"}` 项。

这是 v0.1 的简化约束。原因：

- 识别算法运行在已实例化的工作图 `G(M)` 上
- 允许 `over` 再含对象变量会引入二次量化，语义复杂度不匹配 v0.1 目标

这条约束**不在 JSON Schema 层强制**（软约束），但 validator 必须检查并在违反时报错。

### 4.3 形式良好性（Well-Formedness）

一个公式 F 是形式良好的，当且仅当 F 中出现的每一个

```text
varRef { name: n }
```

都能在它所在位置向上回溯到一个祖先 `sum` 节点，满足 `sum.bind.name == n`。

**不允许自由值变量。**

注意：下列东西不参与形式良好性判定，它们由查询上下文外部固定：

- 查询的 `target` 原子及其值
- 查询的 `intervention` 原子及其值
- 查询的 `given` 原子及其值

它们出现在 `probability_ref` 中时，是**字面值**或**被查询上下文固定的值**，不是自由变量。

### 4.4 alpha 等价

两个公式在 alpha 重命名后一致，视为等价。

v0.1 实现可以不显式做 alpha 归一化，但规范上保证：**绑定变量名只是占位符，外部观察者不应依赖具体字符串**。

---

## 5. `probability_ref` 的语义

### 5.1 引用范围

`probability_ref` 引用的是**模型分布中的任意条件概率项**，不限于 `Theta` 中的字面条目。

因此：

- `Theta` 决定哪些概率项可以直接取数值
- 识别出的公式中其他条件概率项必须通过边际化、条件化、或其他合法模型推导从 `Theta` 推出

如果一个 `probability_ref` 对应的概率项在当前 `Theta` 下无法取数值，查询状态应降级为 `needs_investigation`，并在 `missing_information` 中报告缺失。

### 5.2 空条件

`given: []` 表示无条件概率 `P(target)`。

渲染层在展示时可省略 `|`，但 schema 层始终保留 `given` 数组字段。

---

## 6. 值域约束（validator 级）

### 6.1 原则

v0.1 的 `atom` 还没有显式类型/值域声明。因此以下约束不在 JSON Schema 层表达，由 validator 在运行时检查：

- `probability_ref.target.value`、`probability_ref.given[*].value` 中的字面值，必须属于其对应 atom 的合法值域
- `varRef` 的值域必须与引入它的 `sum.over` 的值域一致

### 6.2 v0.2 升级路径

v0.2 拟为 `atom` 引入显式类型系统（`atom.schema.json` 扩展），届时这些值域约束可上移到 schema 层。

---

## 7. 完整示例：后门公式

查询：

```text
effect(Cancer(alice) | do(Smokes(alice) = false), given = [])
```

设调整集 `{Stress(alice)}` 堵住唯一后门路径，识别公式为：

```text
P(Cancer(alice)=true | do(Smokes(alice)=false))
  = ∑_z  P(Cancer(alice)=true | Smokes(alice)=false, Stress(alice)=z) · P(Stress(alice)=z)
```

对应 AST：

```json
{
  "kind": "sum",
  "bind": { "name": "z" },
  "over": {
    "predicate": "Stress",
    "args": [{ "type": "const", "name": "alice" }]
  },
  "body": {
    "kind": "product",
    "terms": [
      {
        "kind": "probability_ref",
        "target": {
          "atom": {
            "predicate": "Cancer",
            "args": [{ "type": "const", "name": "alice" }]
          },
          "value": true
        },
        "given": [
          {
            "atom": {
              "predicate": "Smokes",
              "args": [{ "type": "const", "name": "alice" }]
            },
            "value": false
          },
          {
            "atom": {
              "predicate": "Stress",
              "args": [{ "type": "const", "name": "alice" }]
            },
            "value": { "kind": "var_ref", "name": "z" }
          }
        ]
      },
      {
        "kind": "probability_ref",
        "target": {
          "atom": {
            "predicate": "Stress",
            "args": [{ "type": "const", "name": "alice" }]
          },
          "value": { "kind": "var_ref", "name": "z" }
        },
        "given": []
      }
    ]
  }
}
```

---

## 8. v0.1 之外

下列能力显式不进入 v0.1 公式子语言：

- 独立 `condition` / `marginalize` 算子
- 对 `sum.over` 的对象变量量化（即二次量化）
- 公式层的 `do` 节点
- 公式化简规则（如 `P(A|B)·P(B) → P(A,B)`）
- 反事实下标记号（如 `Y_x`）
- 原子值域的 schema 层类型检查

这些将在 v0.2 或更晚版本按需引入。

---

## 9. 一句总纲

```text
公式 AST 是一门只含 constant / probability_ref / product / sum 的最小子语言，其中 sum 显式绑定值变量并在 ground atom 上求和，全公式闭合无自由值变量，probability_ref 指向模型分布中的任意条件概率项。
```
