# Phase 16 — Formula-simplification subsystem (unlocks complete Line-7 ID)

> 状态：slice 1（sum-to-one）+ slice 2（extract + fraction 约分）已落地、
> 语义保值已证、全量绿。slice 3-4 待做。这是 Phase 15 明确 defer 的"彻底
> 做全完整通用 nested-ID"的真实门槛——不是 bug，是一个子系统。

## 根因（为什么需要它）

Shpitser-Pearl ID 的嵌套行（尤其 Line 7）产出 `Σ_v ∏_i P(Vi|Ci)` 形式的
边缘化乘积，IDC 再加上它们的比值。**naive 构造、构造步骤之间不做代数化简**，
表达式会在**构造阶段指数爆炸**（5 节点图深度上万，连递归遍历/validate/探针
都爆栈）。这是第一次"完整 Line-7"尝试（`_id_symbolic`）撞墙 revert 的根因。
参考实现（causaleffect / ananke）全部重度依赖一个化简步骤——这个 phase 就是
把它建起来。

## 研究结论（一手来源，2026-06-15 调研）

**核心来源**：Tikka & Karvanen 2017, *"Simplifying Probabilistic Expressions
in Causal Inference"*, JMLR 18(36):1-30（算法 Def 1-5 / Thm 6-7 / Alg 1-6）。
交叉核对 `causaleffect` R 源（`simplify.expression.R`）+ JSS vignette（`probability`
对象字段）+ `ananke`（`one_line.py`）。

**两层架构**（关键）：

1. **便宜的代数消除器**（causaleffect `simplify.expression`，~90 行，**零图查询**）
   ——只用两条恒等式，干掉绝大部分爆炸：
   - **sum-to-one 塌缩**：`Σ_v P(v|C)·R = R`（当 v ∉ C 且 v ∉ free(R)）。R 源
     line 16-21：若 leading factor 的 head 是被求和变量就丢掉它并去掉该 sum。
   - **比值尾部因子约分**：num 与 den 的公共后缀因子相消（line 58-67），仅当
     denominator 的 sumset 已空（Alg 6 line 4 的前提）。
2. **图感知 `simplify`**（JMLR Algorithm 1 + `join` + `insert` + `factorize`，
   需 d-分离）——当要消的因子不是 leading term、需用 d-分离证明"一串条件
   乘积 = 一个 joint 然后 telescoping"时才用。完备层。

**最关键的实操洞察**：**化简要 eagerly 在构造时跑、不是最后跑一次**——"深度
上万"正是因为构造步骤之间从不约分。

**表达式表示**（causaleffect `probability` 对象 → Themis 映射）：
| causaleffect | Themis FormulaExpr |
|---|---|
| atom `P(var\|cond)` | `ProbabilityRefExpr(target, given)` |
| product + sumset | `SumExpr` 嵌套 over `ProductExpr`（每个求和变量一层 Sum） |
| fraction(num/den) | `FractionExpr(numerator, denominator)` |

**ananke 的另一条路（不采用，但要知道）**：ananke `OneLineID.functional()` 用
fixing 算子 Φ / `Q[·]` factor 表示，**根本不展开成 sum-of-products**，所以没有
爆炸可化简——是从"表示"上绕开问题。代价是重写整个 ID 引擎。Themis 现状是
Shpitser-Pearl sum-of-products，所以走 causaleffect 路线（bolt-on 化简）侵入最小；
若反复撞完备性墙，ananke 路线是结构性的替代，但那是另一个大工程。

研究存档（subagent 落在 `C:\Users\12916\`，可能不持久——核心内容已抄进本文）：
`jmlr_simplify.txt` / `jss_causaleffect.txt` / `simplify_expr_extracted.R` /
`ananke_one_line.py`。

## Slice 计划

- **slice 1（已落，本 charter 同批）—— sum-to-one canceller。**
  `themis/runtime/formula_simplify.py`：`simplify_formula(expr)`，纯函数、零图、
  到 fixpoint。只实现 `Σ_v P(v|C)·R = R`（守卫 `v ∉ free(R)` 保值）。
  `tests/test_formula_simplify.py`：结构测试（该触发/不该触发）+ **数值保值测试**
  （归一化 theta 下 `eval(原)==eval(简化)`，多随机 seed）。**保值是后续把它接进
  构造的许可证**。
- **slice 2（已落，本 charter 同批）—— extract + fraction 约分。**
  `_extract_from_sum`：`Σ_v(∏indep·∏dep)=∏indep·Σ_v∏dep`，把不含求和变量的因子提到
  sum 外（只在两边都非空时，否则 `Σ_v 1=|dom|` 不保值）。`_cancel_fraction`：
  `(P·X)/(P·Y)=X/Y`，只消 num/den 的**顶层 plain-conditional 因子**（结构相等、
  不下钻进 sum——sum 把因子耦合到求和变量，不是自由 multiplicand）。仍零图。
  数值保值已证（extract + cancellation 各多 seed）。给 IDC 比值用。
- **slice 3 —— 图感知 `simplify`（Alg 1/2/3）。** `join`/`insert`/`factorize`，
  需 ADMG 上的 d-分离 oracle（Themis 已有 `m_separated`）。完备层；当要消的因子
  不是 leading term 时用。
- **slice 4 —— eagerly 接进 Line-7 构造。** 在 `c_factor` 的 nested-ID 构造里
  每步后 `simplify_formula`，防止中间表达式爆炸。**全程用语义探针验**，只发探针
  确认过的公式，其余 punt。这是真正解锁"完整通用 nested-ID"的一步——也是上次
  爆炸的地方，所以放在 canceller 证明之后、稳着做。

## 不变量 / 纪律

- 化简必须**保值**：每个 slice 先用数值保值测试（多随机归一化 theta）+ 语义探针
  钉死，再接进任何构造路径。改了数字就是 correctness bug。
- 便宜规则有**前提**：sum-to-one 要求被求和变量只作为那一个分布因子的 head 出现
  （`v ∉ free(rest)`）；比值约分要求 sumset 已空。守卫写进代码、测进测试。
- 拓扑序影响复杂度（JMLR §1）：喂给 ID 的变量序会决定便宜层能否成功；记住，必要
  时才上图感知层。
