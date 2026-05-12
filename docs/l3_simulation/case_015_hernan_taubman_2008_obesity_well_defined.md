# Case 015 — Hernán-Taubman 2008 well-defined intervention (obesity → mortality)

> 第 15 例。第一次有意识用真实文献案例测**板块 8 (well-defined
> intervention prerequisite) 第二条形状** —— *intervention 的
> VariableDeclaration 声明 state_vs_event="state" 但没有 time_window*
> （或两者都未声明），按 Hernán & Taubman 2008 是 ill-defined
> intervention 的 canonical shape。结果：✅ 真 gap → 加新
> GapKind + classifier。板块 8 0% → 5-10%；2026-05 retest 又
> 把 trigger 放宽到 absent state_vs_event 也触发（详见 `## 历史`
> 第二条），覆盖率再升一档。

## NL question

"流行病学共识里 obesity 会增加 mortality，请问 do(obese=true) 对
5 年内全因死亡 (death_5yr) 的因果效应是多少？已知混杂 = {age,
smoking}。"

(用户期望：被告知"obesity 本身作为干预 ill-defined —— 减重通过
节食 / 运动 / 手术 / GLP-1 / 代谢疾病等不同路径实现，反事实结果
各不相同；do(obese=state) 没有唯一定义，consistency assumption
被沉默违反"。这是 Hernán & Taubman 2008 整篇 paper 的核心
methodological 点。)

## Authoritative source

- **Hernán MA, Taubman SL.** "Does obesity shorten life? The
  importance of well-defined interventions to answer causal
  questions." *International Journal of Obesity* 2008
  Sep;32(Suppl 3):S8-S14.

  这篇是 epidemiology / causal-inference 文献里关于
  ill-defined intervention 的标志性论文；任何 modern target
  trial / What If §3.4 consistency 讨论都要引这篇。

### 核心 quote — same state value, different counterfactual outcomes

Hernán & Taubman 2008 §2 "The need for well-defined interventions":
> "The causal effect of an intervention is only well defined when
> the intervention is well defined. … For a non-manipulable
> attribute like 'being obese' to support a causal effect estimand,
> we must specify *how* the obese state would be reached or removed
> — gastric bypass surgery, low-calorie diet, exercise regimen,
> pharmacological therapy, metabolic disease — because each of
> these manipulations would have a different effect on mortality."

§3 "Versions of treatment":
> "Different versions of an intervention that all set the
> exposure variable to the same value (e.g. 'not obese') may
> nevertheless lead to *different* counterfactual outcomes. … The
> SUTVA / consistency assumption — that the observed outcome
> under treatment level a equals the counterfactual outcome under
> intervention setting A=a — is then *silently violated*."

### Hernán & Robins *What If* §3.4 平行 quote

> "When the intervention is sufficiently vague that different
> versions yield different counterfactual outcomes, we say the
> intervention is 'ill-defined' and the consistency assumption
> fails. Any causal estimate then mixes together the effects of
> these different versions in unknown proportions."

### 已 documented data limitations 跟 Themis 应当 surface 的对应

1. ✅ **ill-defined intervention** — obesity-as-state has multiple
   structurally-different manipulations producing the same value
2. ✅ **未测混杂** — measured {age, smoking} 不可能闭住所有 backdoor
   path（早期生活环境 / 代谢遗传 etc.）
3. ✅ **变量定义模糊** — death_5yr 缺 observability / direction /
   baseline；obesity 的 BMI≥30 threshold 是软切点
4. ⚠ **bounds not point estimate** — 没数据时 Manski natural
   bounds = [0, 1]

## Encoded kernel_ast

`case_015_hernan_taubman_2008_obesity_well_defined.json`:

- 节点：obese (state_vs_event="state", threshold "BMI≥30",
  **无 time_window**), death_5yr, age, smoking
- 边：obese → death_5yr (evidence: Hernán & Taubman 2008);
  age → obese (common_knowledge); age → death_5yr; smoking →
  death_5yr
- query: P(death_5yr=true | do(obese=true)) effect query, given=[]
- 故意把 obese 声明为 state-without-duration，触发 Hernán &
  Taubman 2008 的 canonical ill-defined intervention 结构

## Pre-iter-207 Themis output (the gap)

```
status: needs_investigation

gaps (5):
  missing_distribution (blocking)
  ambiguous_variable_definition (important) × 2
  measurement_error_concern (important)
  answer_is_bounds_not_point_estimate (informational)
  unmeasured_confounder_risk (informational)
```

**没有 fire 任何 ill-defined-intervention 相关 gap_kind。** Themis
看到了 program 里 `obese.state_vs_event="state"` 这个字段，schema
也接受这个 value 200+ iters，但**从来没有 classifier 读 state_vs_event
的 VALUE**。这是 iter 205 (measurement value) / iter 206
(ObservationStatement) 同 pattern 的 dead-schema theatre 第三次
浮出。

## Post-iter-207 Themis output (✅ match)

加了 `ill_defined_intervention_versions` gap_kind + 新 classifier
后：

```
status: needs_investigation

gaps (7):
  missing_distribution (blocking)
  ambiguous_variable_definition (important) × 2
  ill_defined_intervention_versions (important):
    intervention 是状态不是事件、且没有指定时间窗：变量 `obese`
    声明了 state_vs_event="state"，但同一变量没有声明 time_window。
    这是 Hernán & Taubman 2008 IJO 32(S3):S8-S14 经典 ill-defined
    intervention 结构 —— 同一个 obese 状态值可以由多种结构上不同
    的操纵路径实现，不同操纵路径会带来不同的反事实结果；
    consistency assumption (Hernán & Robins What If §3.4) 被沉默
    地违反。
  measurement_error_concern (important)
  answer_is_bounds_not_point_estimate (informational)
  unmeasured_confounder_risk (informational)

result.explanation 头部：
  ⚠ intervention 是状态不是事件、且没有指定时间窗 ...
```

`alternative_paths` 给了四条结构性可执行选项:

1. 把 intervention predicate 重新声明为 event-like
   (state_vs_event="event")，比如 "参加为期 12 周减重项目"
2. 把 obese 拆成两个变量：事件类 intervention（如
   prescribed_weight_loss_program）+ 中间状态（如
   bmi_after_12w），走 mediation 路径
3. 用 RCT / 实验性数据 — 实验里 do(.) 的 "compared with
   what" 由随机化协议明确定义
4. 在 extensions.ambiguities 里 opt-in
   `ill_defined_intervention`，接受多估计量混合

## 评估

### ✅ match (post-iter-207)

- ✅ Hernán & Taubman 2008 §2 "intervention must be well-defined"
  直接对应新 gap_kind 的 description
- ✅ alternative_paths[0] 引用 event-encoding —— Hernán & Taubman
  2008 §3 末段的核心建议
- ✅ alternative_paths[1] 引用 mediation split —— Hernán & VanderWeele
  2011 "Compound treatments and transportability" §4 的标准方案
- ✅ alternative_paths[2] 引用 RCT triangulation —— Hernán & Taubman
  2008 §4 强调 "the randomized trial defines the well-defined
  intervention by design"
- ✅ severity = IMPORTANT 而非 INFORMATIONAL：ill-defined
  intervention 是 *estimand-level* 问题（多个估计量被沉默混合），
  不是 estimand 上的 estimate uncertainty
- ✅ alternative_paths 没有"fetch more data" —— 更多 row count
  不能修一个 under-defined 估计量

### 与 ambiguous_variable_definition (iter 88+) 的区分

| 触发条件 | ambiguous_variable_definition | ill_defined_intervention_versions |
|---|---|---|
| 信号源 | 单个 framing field 缺失（threshold/observability/...） | 结构性 ill-defined-intervention 形状 |
| 对应文献 | A0/F1 framing gate (Themis 内部) | Hernán & Taubman 2008 IJO |
| 严重度 | important（per field） | important（per intervention atom） |
| 修法 | 补 framing field | 重新设计 intervention 或 opt-in 多估计量 |
| 关系 | complementary，不互相 suppress | complementary，不互相 suppress |

两类 gap 在同一 program 上**并行 fire** —— 一个标"single field 没说"，
一个标"intervention shape 本身 ill-defined"。

### 与 measurement_error_concern (iter 205) 的区分

iter 205 处理 *estimate-level* bias（测量误差让 estimand 估
"歪"）；iter 207 处理 *estimand-level* bias（不同干预版本产生
不同 estimand，所谓"effect"是这些 estimand 的混合）。

### 范围 honesty

板块 8 的 COVERAGE_MAP 从 **0%** 调到 **5-10%**：

- ✅ 加：iter 207 explicit shape + 2026-05 inferred shape 共同
  覆盖 well-defined intervention prerequisite 的两条 trigger 路径
- ❌ 没做：target trial emulation framework (Hernán 2017 AJE 188:67
  完整流程)
- ❌ 没做：compound treatment decomposition (Hernán & VanderWeele
  2011 数值层)
- ❌ 没做：multi-version sensitivity analysis（不同 manipulation
  下 estimand 范围的 bounds）

那三个 ❌ 是 Phase 4+ 工作。当前 iter 只破冰板块 8 第一条 + 第二条
shape detection。

## 后续 action

- ✅ Bug fix landed (iter 207 — 是新 capability，不是 bug fix)
- ✅ Add to L3 corpus regression test（must-have:
  ill_defined_intervention_versions + missing_distribution +
  ambiguous_variable_definition + unmeasured_confounder_risk;
  must-not-have: collider_conditioning_opens_backdoor /
  selection_on_collider_opens_path /
  graph_theta_independence_mismatch / weak_iv_instrument）
- ✅ 加 unit test pin classifier 触发 (explicit + inferred) + 多个
  suppression / negative 分支
- ✅ Update GAP_KINDS_REFERENCE / response_rendering / gap_to_action
  同步
- ✅ COVERAGE_MAP 板块 8 行 + 元基础设施 row gap_kind 数 29 → 30

## 历史

- **2026-05-11 iter 207**: Real-finding via L3 simulation methodology。
  外部权威源：Hernán MA, Taubman SL 2008 *Int J Obesity*
  32(Suppl 3):S8-S14 + Hernán & Robins *Causal Inference: What If*
  §3.4。Bug：板块 8 (well-defined intervention prerequisite) 从
  未被 surface —— variable schema 的 state_vs_event 字段 200+ iters
  前就 admit "state"/"event" values，但**从未有 classifier 读这字段的
  VALUE**。Dead-schema theatre 第三次浮出（iter 205 measurement /
  iter 206 ObservationStatement / iter 207 state_vs_event）。case 015
  用 Hernán & Taubman 2008 经典 obesity → 5yr mortality 编码
  surface 这个 gap → 加新 `ill_defined_intervention_versions`
  GapKind + 新 classifier。L3 corpus 14/14 → 15/15。

- **2026-05-12 retest**: Q3 agent retest after MCP restart 暴露
  iter 207 trigger 的 UX 缺陷 —— 只在 LLM 显式声明
  state_vs_event="state" 时触发。NL-derived program 几乎从不显式
  声明 state_vs_event（它是 optional schema），所以 trigger 对
  自然 LLM 输出**不可达**。把"spot the methodology trap"的责任
  推回 LLM 本身，违背 Themis "catch what LLM didn't think to flag"
  定位。Fix：放宽 trigger 到 `absent state_vs_event + absent
  time_window` 也触发（同 IMPORTANT 严重度，description / provenance
  ref_id 区分 explicit vs inferred）。Opt-out 仍便宜：显式声明
  state_vs_event="event" 关掉警告。L3 corpus 仍 15/15，新增
  3 inferred-path pin 测试。
