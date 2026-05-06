# Phase 5 Charter — 时序 / 反事实 两个延伸 fragment

> 立项日期：2026-04-22
> 状态：**✅ 两 fragment 全部已落地** — §T (temporal) 落地 2026-04-22；
> §C (counterfactual) S.C.1-S.C.6 落地 2026-04-22；§T 进一步加 runtime
> 强制（commit `3e79338`，2026-05-06，iter 之外）。详见
> [`CORE_STATUS.md`](CORE_STATUS.md) "Phase 5.temporal" + "Phase 5.counterfactual"
> + "Phase 5 §T runtime 强制" 节。
> 对应 ROADMAP：Phase 5 "更强推理能力" 中的时序 + 反事实分支
> 对应 TaskList：#39

## 0. 本 charter 结构

Phase 5 下有两个独立 fragment，各自承担一类语义扩展：

- **Temporal fragment (§T)** ——让 kernel 能表达 "X 在时刻 t 影响 Y 在时刻
  t+k" 这类带时间索引的因果。窄，语义清楚，eval 案例 14 (`F11 late-
  night_tired_temporal`) 是真实压力。
- **Counterfactual fragment (§C)** ——让 kernel 能回答 Pearl Layer 3 查询
  ("如果当初 X 不同，结果会怎样")。宽，需要更多基础设施，eval 案例 17
  (`F16 career_choice_counterfactual`) 是真实压力。

**推荐顺序**：§T 先落地 → 实战一段时间 → 再开 §C。理由见 §9。

这是对 Themis v1.0 核心冻结面的一次**显式解冻申请**。按 CORE_STATUS.md
"核心冻结 v1.0" 规定，新 AST 语句 / 新语义维度 / 新 rule family 一律
需要先立 charter 再动代码。本文件就是这份 charter。

---

## 1. 动机

### 1.1 眼下 eval 集里的真实压力

两个 fragment 都由 eval 案例直接逼出来——不是假设性需求：

- **Case 14 (F11 temporal)**: 用户 NL "最近连续熬夜，第二天没精神"。
  这个压力已经由 §T 吃掉：A1 v2.2 直接产出带 `time_index` 的 timed AST /
  timed query，不再用 `extensions.ambiguities[kind=temporal]` 压缩降级。
- **Case 17 (F16 counterfactual)**: 用户 NL "如果当初我选的是计算机
  专业，现在收入会更高吗"。这条压力现在已经由窄 §C 吃掉：
  A1 v2.3 直接产出 `counterfactual` query；若 query 未显式给
  monotonicity，则 kernel 返回 `needs_assumption`；若 monotonicity +
  Theta 都齐，则返回 `counterfactual_bounded` / `counterfactual_solved`。

Case 14 已经从“Phase 5 立项动机”变成“Phase 5.temporal 的完成信号”；
Case 17 仍然是 §C 的真实压力来源。

### 1.2 理论 fragment 是否已固化

- **时序**：因果时间建模有教科书级形式 (Dawid 2000; Pearl 2009 ch.10；
  Peters / Janzing / Schölkopf 2017 Structural Causal Models §10)。
  离散时间、马尔可夫链结构、time-indexed DAG 语义都是现成的。
- **反事实**：Pearl Layer 3 + twin network projection (Pearl 2009 ch.7;
  Balke & Pearl 1994) 同样是文献固定形式。Counterfactual 识别定理
  (Shpitser & Pearl 2008) 给出什么可算什么不可算。

两者都满足 ROADMAP "理论 fragment 已清晰定义" 的启动门槛。

### 1.3 对称性论证（和已有 fragment 的区别）

- **和 A6.front-door**：front-door 只是在 DAG 语义下多加一条识别路径，
  不扩语义。本 charter 两个 fragment 都扩语义。
- **和 Phase 2.latent (ADMG)**：ADMG 在 *空间* 维度扩 DAG（加 bidirected
  边表达观测变量间的潜共因）。§T 在 *时间* 维度扩 DAG（加时间索引）。
  §C 扩到 Layer 3。三者正交。
- **和 Phase 2.latent 的 scope 取舍经验**：ADMG charter 后来窄化到
  backdoor/front-door + verifier，不做 generic c-factor。本 charter 也
  从一开始就窄 scope——不一次性把 Pearl 所有反事实文献都塞进来。

---

## 2. §T 时序 fragment

### 2.1 动机段（见 §1.1 case 14）

### 2.2 语言扩展

#### 2.2.1 atom 加可选 `time_index` 字段

```json
{
  "predicate": "stays_up_late",
  "args": [{"type": "const", "name": "me"}],
  "time_index": {"kind": "relative", "value": 0}
}
```

`time_index.kind` 可选值：
- `"relative"`: `value` 是整数（`-3, -2, -1, 0, 1, 2, ...`），表示
  **相对程序全局时间锚点** 的时间步。`0` 是"程序参考时刻"，负数是过去，
  正数是未来。同一个 program 里的所有 atom / cause / query 共用这一
  条相对时间轴；**query 不会重新解释 `0` 的含义**。
- `"absolute"`: `value` 是字符串形式的日期或时刻（`"2026-04-22"`，
  `"session_t0"`）。本 fragment 首版**不实现 absolute**——留给未来
  扩展。

**不带 `time_index` 的 atom 仍然合法**——当成 "无时间约束" 处理，
和现在的 DAG 行为完全一致。老 program 不被破坏。

这意味着：首版 temporal fragment 只有**程序级相对时间语义**，没有
per-query 的时间锚点。如果将来需要 "以每个查询自己的现在为 0" 这种
视角语义，应另立 fragment，而不是复用这里的 `time_index`。

#### 2.2.2 `cause` 的时间约束

`cause` 语句的 `from.time_index` ≤ `to.time_index`（if both present）。
等号允许（同时刻因果），小于号表示滞后。大于号**在 verifier 被拒**
—— 不允许回溯时间的因果。

#### 2.2.3 不引入的

- **不引入** 新 statement kind。时间索引是 atom 上的可选 metadata。
- **不引入** 新 query kind。`effect / cause / assoc / probability /
  identify` 五种保留。
- **不引入** 绝对时间。只做 relative time index（`0`, `-1`, `+1`）。
  真实日期留给未来 fragment。
- **不引入** 连续时间 / 速率 / 微分。只离散 time step。

### 2.3 语义

#### 2.3.1 时间展开图

Graph projection 在原 DAG / ADMG 上做**时间展开**：

- 每个 (predicate, time_index) 对被视作独立节点。
- `cause` 产生相应时间对齐的有向边。
- 无时间索引的 atom 统一挂在一个虚拟 "atemporal" time index 上。

结果是一个 **time-unrolled DAG**。无环性在展开后的 DAG 上验证。

#### 2.3.2 查询语义保持

`effect(Y | do(X))` 的查询不变；当 X 和 Y 带时间索引时，干预施加在
程序级相对时间轴上的指定节点，目标也在对应节点读取。Backdoor
adjustment、front-door 等识别规则在展开后的 DAG 上直接复用——不需要
新规则。

#### 2.3.3 Markov 假设（首版）

首版假定 **1 阶 Markov**：`cause` 的时间跨度 `|t2 - t1| ≤ 1`。
多阶滞后（lag ≥ 2）在首版被 verifier 拒。放宽到任意 lag 留给
未来 fragment。

### 2.4 verifier rule family

新规则族 `temporal_*`：

- `T1_time_monotonicity`: `cause` 的源时间索引 ≤ 目标时间索引
- `T2_lag_bound`: 时间差 ≤ 1（Markov 首版）
- `T3_unroll_acyclic`: 时间展开后的图无环

### 2.5 schema 变更

- `atom.schema.json` 加可选 `time_index` oneOf: `{kind: "relative",
  value: integer}` （本版不加 absolute）
- `kernel_ast.schema.json` 无新 statement kind
- `query_result.schema.json` 的 `supporting_paths` 字符串表示需要
  把 time_index 展示出来（`stays_up_late@t-1 → feels_tired@t`）
- `derivation.schema.json` 加 `temporal_*` rule family 的 witness

### 2.6 §T 的 S 切片

- **S.T.1**: atom schema 扩展 + 加载/序列化
- **S.T.2**: verifier T1-T3 规则
- **S.T.3**: graph projection 时间展开
- **S.T.4**: 现有 `cause / assoc / effect / identify / probability`
  dispatcher 在展开图上复用——证明无需改
- **S.T.5**: e2e case 14 上跑通
- **S.T.6**: A1 prompt v2.2 加时序识别规则（"上个月 X 这个月 Y" →
  `time_index=-1 → 0`）+ 移除 `extensions.ambiguities[kind=temporal]`
  降级通道

### 2.7 §T 完成标志

- Case 14 跑通时不再声明 `temporal` ambiguity（真的能表达了）
- 新增 S.T.1-S.T.6 所有测试通过
- 全 pytest 至少保持不退步
- `CORE_STATUS.md` 列出 temporal 语义解冻段

---

## 3. §C 反事实 fragment

### 3.1 动机段（见 §1.1 case 17）

### 3.2 语言扩展

#### 3.2.1 新 query kind: `counterfactual`

```json
{
  "kind": "query",
  "id": "q_cf",
  "query": {
    "kind": "counterfactual",
    "observed": {
      "atom": {"predicate": "chose_cs_major", "args": [...]},
      "value": false
    },
    "counterfactual_intervention": {
      "atom": {"predicate": "chose_cs_major", "args": [...]},
      "value": true
    },
    "counterfactual_target": {
      "atom": {"predicate": "higher_current_income", "args": [...]},
      "value": true
    },
    "assumptions": {
      "monotonicity": "non_decreasing"
    },
    "factual_target_known": null
  }
}
```

语义："已知实际选择是 false，如果反事实地把它设为 true，target 是
true 的概率是多少？"

`factual_target_known` 可选：如果用户也告诉我们实际的 target 值，
那是 Abduction-Action-Prediction 三步里第一步的约束。

`assumptions.monotonicity` 在 §C 首版里是**显式字段**，不是隐含默认。
可选值首版只支持：

- `"non_decreasing"`
- `"non_increasing"`

缺失时 query 仍可 parse，但 runtime 直接返回 `needs_assumption`，不会
尝试 counterfactual bounds。

#### 3.2.2 不引入的

- **不引入** atom 级 counterfactual labels / twin-world subscripting
  (`Y_{x=0}`) 在表面语法。twin network 的对偶在 projection 里生成，
  表面语法保持单世界形式。
- **不引入** continuous counterfactual；首版只做二值 SCM。
- **不引入** 无限制反事实 ID 算法（ID* / IDC*）。首版只做 **二值 SCM
  + 显式 monotonicity 假设下的 Balke-Pearl bounds**（Balke & Pearl,
  1994）。
- **不引入** 反事实下的多 query 联合分布。首版一次只回答一个 cf
  target。

### 3.3 语义

#### 3.3.1 Twin network projection

给定 ADMG 和一个 counterfactual query：

1. 复制 ADMG 一份，节点改名 `X` → `X'`
2. 对 counterfactual intervention 所在节点 `X'`，切断它的所有入边
   (do-operation in the counterfactual world)
3. 两个世界共享同一组外生变量 `U`（通过 bidirected 延伸）
4. 在这个 twin network 上做概率推断

#### 3.3.2 Monotonicity 假设

首版**强制要求** monotonicity：intervention 对 target 的影响方向
单调，且该假设必须通过 `query.assumptions.monotonicity` 显式给出。
这收窄识别空间但让 bounds 可计算。缺失时 query 返回
`needs_assumption` + 解释为什么；首版不做“默认按无 monotonicity
也先算一遍 bounds”的宽语义。

#### 3.3.3 可识别性

首版识别只做 **显式 monotonicity 假设下** 的 Balke-Pearl bounds。
如果上下界收缩为同一点，可返回 `counterfactual_solved`；否则返回
`counterfactual_bounded`。没有 monotonicity 假设时不进入 solver，
而是直接返回 `needs_assumption`。

### 3.4 verifier rule family

- `CF1_binary_scm`: 所有 counterfactual query 中的变量都是 bool
- `CF2_monotonic_assumption_stated`: query 需明确声明 monotonicity
  方向，或 fail-fast 报 `needs_assumption`
- `CF3_twin_network_well_formed`: twin-world projection 成功

### 3.5 schema 变更

- `kernel_ast.schema.json` 加 `counterfactual` query kind
- `kernel_ast.schema.json` 为 `counterfactual` query 加
  `assumptions.monotonicity`（`non_decreasing` / `non_increasing`）
- `query_result.schema.json` 加新 status: `counterfactual_solved`
  / `counterfactual_bounded` / `needs_assumption`
- `derivation.schema.json` 加 `cf_*` rule family

### 3.6 §C 的 S 切片

- **S.C.1**: schema 扩展 + parser / serializer
- **S.C.2**: twin network projection primitive
- **S.C.3**: Balke-Pearl bounds solver
- **S.C.4**: monotonicity check + `needs_assumption` channel
- **S.C.5**: e2e case 17 跑通（返回一个 bounded interval 而非点估计）
- **S.C.6**: A1 prompt v2.3 加 counterfactual 识别规则 + 降级通道
  保留（Kernel 不支持时 fallback 到 Layer-2 proxy）

> 落地后补充：当前 `§C` 不再只依赖 `P(X)` + `P(Y|X)` 的最窄 joint 恢复。
> 在无相关 `bidirected` 触碰时，runtime / verifier 会先对 `{X, Y}` 的
> directed ancestral subgraph 做 observational factorization；不适用时再回退
> 到局部链式 / 布尔互补恢复。

### 3.7 §C 完成标志

- Case 17 跑通：若 query 显式给了 monotonicity，则返回 Layer 3 bounds
  （或 bounds 收缩后的 `counterfactual_solved`）；若没给，则返回
  `needs_assumption`
- S.C.1-S.C.6 测试过
- derivation / verifier / context JSON 外部复核已接通
- `CORE_STATUS.md` 列出 counterfactual 语义解冻段

---

## 4. 显式 Out-of-scope（两 fragment 合并）

以下留给未来独立 charter，**本 charter 不动**：

- 连续时间、速率、微分方程
- 绝对时间（日历日期）作为 time_index
- 任意阶 Markov 滞后（首版固定 1 阶）
- 完整 counterfactual ID（ID* / IDC*）
- 多变量联合反事实分布
- 非二值 counterfactual（类别或连续）
- Counterfactual fairness / policy evaluation

---

## 5. 对 NL 层的影响

A1 prompt v2.2（对应 §T 完成）：
- 识别 "上个月 X / 这个月 Y" 等模式，把 atom 加 `time_index`
- 移除 `extensions.ambiguities[kind=temporal]` 降级通道——不再压缩

A1 prompt v2.3（对应 §C 完成）：
- 识别 "如果当初 / 要是没 / 假如我当时"，emit counterfactual query
- 移除 `extensions.ambiguities[kind=counterfactual_query]` 降级通道

response_rendering v2.2 / v2.3 同步更新，去掉相应 kind 模板（或保留
作 fallback）。

---

## 6. 验证策略

两个 fragment 遵循 Phase 2.latent 的独立 verifier 原则：

- verifier 实现与 runtime 分离（不同模块，不共享中间表示）
- 测试用 byte-code scan (`co_names`) 确认 verifier 不引用 runtime
- 每个新 rule family 至少 3 个正例 + 3 个反例测试

---

## 7. 风险

### 7.1 §T 风险

- **Markov 1 阶太窄**：如果真实 NL 出现 2+ 步时滞（"三年前开始 X，
  现在 Y 了"）会触发 verifier 拒绝。应对：降级通道保留，先跑 lag=1
  版本，声明 "滞后压缩" ambiguity。
- **展开后图爆炸**：如果程序有 10 个 predicate × 10 个 time step =
  100 节点，backdoor 搜索可能慢。应对：首版限 T ≤ 3 time steps；超
  出报 `needs_simplification`。

### 7.2 §C 风险

- **Monotonicity 门槛高**：大部分真实 NL 用户不会声明 monotonicity。
  大量 query 会卡在 `needs_assumption`。应对：NL 层对常见"正向"模式
  （吃药→降 BP，学习→考试高分）可填入显式
  `assumptions.monotonicity`；不常见的场景则显式追问。
- **Layer 3 认知门槛**：用户可能搞不清 bounds 的含义。应对：
  response_rendering 把 bounds 翻译成"根据现有假设，结果在 P=0.3
  和 P=0.7 之间——再给我 X 信息可以收窄"。

---

## 8. 不做事项（charter 承诺）

- 本 charter 不开任何代码；只立项
- §T 和 §C 各自独立解冻；谁先落地不绑定另一个
- 如果 §T 落地后发现某个 S 切片需要更大改动（例如 graph projection
  需要重写），暂停并单开子 charter 讨论，不强行往前推

---

## 9. 推荐执行顺序

**§T 先，§C 后**。理由：

1. §T 的语义更窄、更贴近现有 DAG，风险小
2. §T 的真实压力案例 (14) 比 §C 的 (17) 更普遍——时间索引涉及很多 NL 常见模式
3. §C 需要 SCM 假设和 bounds 推理，是从 Layer 2 到 Layer 3 的真实跨越，
   应该等 §T 的解冻实践积累一段经验
4. §T 完成后如果没有紧迫 §C 压力，可以推迟 §C 启动

建议 §T 落地 + 实际跑 4-8 周 eval 案例后再决定 §C 是否启动。

---

## 10. 本 charter 的完成标志

- §T 和 §C 各自的完成标志都达成
- `CORE_STATUS.md` 同步更新
- TaskList 里 #39 从 pending → completed
- 至少 2 个新 eval case 专门覆盖 §T，1-2 个覆盖 §C

---

## 附录 A — 非目标拒绝清单

明确**不在本 charter 内**的东西（避免 scope creep）：

| 项目 | 拒绝理由 |
|---|---|
| 连续时间 SDE / ODE 因果 | 理论太深；不在 ROADMAP Phase 5 范围 |
| Counterfactual fairness | 应用层，非 core kernel |
| Interventional policy learning | 强化学习交叉，单独立项 |
| Causal representation learning | ML 侧工作，非 kernel |
| Time-varying confounders / g-methods | 需要 §T + 额外工具，推迟 |
| Mediation analysis in counterfactual world | §C 稳定后再考虑 |
| ID* / IDC* 算法 | §C 首版只做 Balke-Pearl |

任何上面列出的主题如果通过真实 eval 案例逼出来，独立立新 charter，
不往本 charter 塞。
