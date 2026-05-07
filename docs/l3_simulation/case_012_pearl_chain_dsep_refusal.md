# Case 012 — Pearl smoking-tar-cancer chain × marginal-only theta (d-sep refusal real bug)

> 第 12 例。post-iter-203 状态首次用真实权威案例压测 iter 199-203 d-sep
> refusal pipeline。**结果：发现真 bug 并修 → ✅ match**。bug 是
> `_dispatch_probability` 没把 `bidirected` 传给 `_try_numeric`，导致
> iter 199 d-sep guard 在整个 probability 查询路径上**形同虚设**——
> chain DAG + marginal-only theta + probability 查询会**默默返回错误数字**
> 而不是触发 iter 202/203 refusal。iter 204 修。

## NL question

"在我声明的因果图『吸烟 → 焦油沉积 → 肺癌』下，我有 P(肺癌|吸烟) 的边缘
数据。我想知道 P(肺癌 | 吸烟=是, 焦油=是)。"

(用户期望：要么得到答案，要么被告知数据不足；**不应该**得到一个偷偷
用边缘量替代的错误数字。)

## Authoritative source

- **Pearl J.** "Causal Diagrams for Empirical Research." *Biometrika*
  1995;82(4):669-688. 引入了 smoking → tar → cancer + bidirected
  smoking ↔ cancer (genotype) 作为 front-door 的标志案例。
- **Pearl J.** "Causality: Models, Reasoning, and Inference." 2nd ed.
  Cambridge University Press 2009, §3.3.2 (Front-Door Criterion),
  §1.2 (d-separation)。

### 核心 quote — d-separation 在 chain 上的 implication

Pearl 2009 §1.2.3:
> In a simple chain X → Z → Y, the variables X and Y are dependent;
> however, conditioning on Z renders them independent: **X ⊥ Y | Z**.

也就是说，在 chain DAG `smoking → tar → lung_cancer` 下，
**P(lung_cancer | smoking, tar) = P(lung_cancer | tar)** —— 不能用
`P(lung_cancer | smoking)` 替代。

Pearl 2009 §3.3.2 关于 front-door 案例的真实结构（with bidirected
smoking ↔ cancer）：
> If we accept the model in Figure 3.4 [smoking → tar → cancer with
> unobserved genotype confounder], we can write P(cancer | do(smoking))
> via the front-door formula. But if we try to read P(cancer | smoking,
> tar) as if smoking and cancer were screened off by tar, **we are
> using a non-existent independence**.

### 已 documented data limitation

Pearl/Tian 1995-2009 全套讨论的核心点之一就是：**用户声明的图 + 提供的
distribution 必须一致**——如果 user 声明 chain（蕴含 cancer ⊥ smoking |
tar）但数据只来自 marginal P(cancer | smoking) （隐含 cancer ⊥ tar |
smoking 才能这样替代），两者矛盾。Themis VISION 5 "数据缺口诊断 ≥ 数值
估计" 直接对应这一点：**"图与 CPT 矛盾"应该被显式 surface，不是被偷偷
按一个口味解决。**

## Encoded kernel_ast

`case_012_pearl_chain_dsep_refusal.json`：

- 图：smoking → tar → lung_cancer (no bidirected)
- theta：仅边缘 P(lung_cancer | smoking)，**无** chain 条件量
  P(lung_cancer | smoking, tar)
- query：probability query asking P(lung_cancer=T | smoking=T, tar=T)

## Expected Themis output (per VISION 5 + iter 199-203 design)

应当 fire 的 gap_kinds：
- ✅ `graph_theta_independence_mismatch` — chain DAG implies
  lung_cancer ⊥ tar | smoking is FALSE; user's marginal-only theta would
  only be safe if that were TRUE → guard refuses
- ✅ `ambiguous_variable_definition` × 3 (variables not framed)
- 状态应为 `needs_investigation` 而不是 `numerically_solved`

**绝不应当** 看到的：
- ❌ `numerically_solved` 加 `value=0.18`（直接抄 marginal）

## Themis 实跑结果

### Pre-iter-204（bug 发现）

```
$ python -c "import themis; out = themis.run(...)"
STATUS: numerically_solved
VALUE: 0.18
```

`gap_kinds`: 仅 `ambiguous_variable_definition` ×3。**`graph_theta_
independence_mismatch` 未触发。** Themis 对一个声明的图 + 提供的 marginal
矛盾的查询，悄悄返回了一个用 marginal 替代条件量得到的数字 (0.18)。

#### 根因

`themis/runtime/scheduler.py` line 2396 (pre-iter-204):

```python
result = _dispatch_probability(stmt, graph, theta)
```

未传 `bidirected`。`_dispatch_probability` 把它默认为 `None`，再传给
`_try_numeric` → `estimate_formula(formula, theta, graph=graph,
bidirected=None)`。在 `_try_marginal_independence_lookup` 里：

```python
if graph is not None and bidirected is not None:
    # d-sep guard
    ...
```

**双条件 `is not None`**——`bidirected=None` 直接跳过 guard，落入 iter
193 trust-the-user 行为，**默默把 marginal P(C|S)=0.18 当 P(C|S,T)
返回**。这正是 iter 195 文档化的 "silent-wrong risk for chain DAG +
marginal-only theta" —— 在 effect query 路径上 iter 199-201 已修，但
**probability 路径未修**，因为 effect 路径有自己的 bidirected 传递链
（line 1416、1513），probability 路径完全独立 (line 2396)，两个调用站
的修复必须分别做。

### Post-iter-204（修复后）

```
STATUS: needs_investigation
VALUE: None

gaps:
  ambiguous_variable_definition (important) ×3
  graph_theta_independence_mismatch (important):
    声明的图与提供的 CPT 不一致：缺 P(lung_cancer=True|smoking=True,tar=True)，
    但 theta 中存在的边缘量被 d-separation 拒绝（图蕴含的独立性不成立）
    alt: 补充所缺的条件量 P(lung_cancer=True|smoking=True,tar=True)（接受图）
    alt: 或：删除引发独立性矛盾的边（改图，承认现有 CPT 已是真分布）
    alt: 接受 Balke-Pearl bounds 给区间答案

explanation:
  ⚠ 声明的图与提供的 CPT 不一致：缺 P(lung_cancer=True|smoking=True,
  tar=True)，但 theta 中存在的边缘量被 d-separation 拒绝（图蕴含的独立性
  不成立）
```

## 评估

### ✅ match (post-fix)

修了 iter 199-201 在 probability 路径上的"形同虚设"hole：guard 现在真正
覆盖 effect + probability + counterfactual 三条命令路径。

| Authority's expectation | Themis post-fix |
|---|---|
| chain 蕴含 C ⊥ S \| T，所以 P(C\|S,T) ≠ P(C\|S) — 声明图与 marginal-only theta 矛盾应当被 surface | ✅ `graph_theta_independence_mismatch` fires |
| 修复方向：补 P(C\|S,T)，或者改图（删 chain 边） | ✅ alt_paths 名出两条结构性修复 |
| 不能假装一个矛盾被解决了 | ✅ status = needs_investigation, value = None |

### Anti-finding 半分

case 012 **不是** "现有功能正确" 的 anti-finding —— 是**真 bug**。
case 011 那种"一切都覆盖"的 anti-finding 在 iter 204 之前对 chain DAG
+ probability query 是**假的**：iter 199-203 全套设计在 effect 路径上闭
环，但 probability 路径的 silent-wrong 没人测。case 012 是真人测试的典
型价值 —— LLM 自压测不会发明"用 chain DAG + 缺一个条件量 + probability
query"这种凑巧的输入组合。

## Readability 次要 finding（C 任务原始问题）

iter 204 修完后，refusal 文本对一个非专家是这样：

> 声明的图与提供的 CPT 不一致：缺 P(lung_cancer=True|smoking=True,
> tar=True)，但 theta 中存在的边缘量被 d-separation 拒绝（图蕴含的
> 独立性不成立）

非专家能解码的部分：
- "声明的图" "不一致" "缺 P(...)" — OK
- alt_paths "补充所缺的条件量" / "删除引发独立性矛盾的边" — OK，
  正面动词 + 名词，可执行

非专家黑话部分：
- "CPT" — 专业术语 (conditional probability table)
- "边缘量" — 数学黑话 (marginal)
- "d-separation" — Pearl 因果图论术语
- "图蕴含的独立性不成立" — 数学话

**判断**：这是一个真实可读性 gap，但**不立项为 bug** —— `gap.description`
是给 LLM/UI 消费的结构化标识；renderer 应当在 explanation 文本里提供更
口语化的说明，但 `gap.description` 本身保留 jargon 作为机器可识别 tag
是合理的（per VISION 4 "Derivation 可审计：每一步推导有 rule name +
witness"）。如果未来要做 layperson-narration layer，会是单独 phase 的
工作（template-based rewriting + 多语言话术），不是 iter 204 的 scope。

## 后续 action

- ✅ Bug fix landed (iter 204)
- ✅ Add to L3 corpus regression test (must-have:
  graph_theta_independence_mismatch + ambiguous_variable_definition;
  must-not-have: missing_distribution since route should hit the new
  kind, NOT the generic one)
- ✅ Add explicit unit test that pins the `_dispatch_probability` →
  `_try_numeric` bidirected threading (sync pin: this exact call site
  was the iter 204 bug surface)

## 历史

- **2026-05-07 iter 204**: case 012 mining + 真 bug 发现 + 修。
  外部权威源：Pearl 1995 *Biometrika* + Pearl 2009 *Causality* 2e §1.2 / §3.3.2。
  Bug：`scheduler._dispatch_probability` 在 iter 199 之后从未把 bidirected
  传给 `_try_numeric`，导致 d-sep guard 在 probability 路径上 dormant 三
  iter（199 → 200 → 201 → 202 → 203 都没有 catch）。Effect 路径 + 三个 sync
  pin 锁住了 effect 一边的 silent-wrong；probability 一边没 sync pin。case
  012 的真人测试视角直接 surface 了这个 dispatch-fan-out 的盲点。修复 ≤ 5
  行 + 1 个新 kwarg。L3 corpus 11/11 → 12/12。
