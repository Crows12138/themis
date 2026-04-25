# Themis 12 板块覆盖地图

> 更新时间：2026-04-25
> 本文档跟踪 Themis 对"因果定量问题全 12 板块"的实际覆盖进度。每完
> 成一个 slice 同步更新。配套 [VISION.md](VISION.md) "扩展愿景" 段 +
> [ROADMAP.md](ROADMAP.md) Phase 6+。

---

## 12 板块与当前覆盖

| # | 板块 | 覆盖 | 现状 / 策略 |
|---|---|---|---|
| 1 | 可观测识别 | **75-80%** | backdoor ✓ / front-door 单 + 多 mediator ✓ / IV ✓ / 完整 ID (Shpitser) ✗ → Phase 6.complete-id（可选）|
| 2 | ADMG / 潜变量 | **80%** | bidirected ✓ / m-sep ✓ / ADMG-backdoor/front-door ✓ / c-factor 推迟 |
| 3 | 反事实（Layer 3） | **20-25%** | **Phase 5 §C 已落地（窄 scope）**：Balke-Pearl 二值单调 bounds + counterfactual query + monotonicity needs_assumption 通道 / ID\* / 连续 ✗ → 长期 |
| 4 | 时序 / 动态 | **30-35%** | **Phase 5 §T 已落地**：atom `time_index` 一等公民 / 时间展开 graph / verifier T1-T3 / case 14 e2e ✓ / g-methods ✗ / 连续时间 ✗ → Phase 9+ |
| 5 | 工具变量 (IV) | **~85%** | **Phase 6.iv + Phase 7.3 全部落地**（basic + conditional + ADMG-aware identification + Wald LATE / 2SLS ATE 数值估计）|
| 6 | 中介分析 | **~70%** | Phase 6.mediation 识别 ✓ / **Phase 7.4 Imai NDE/NIE 数值估计 ✓**（via statsmodels）；CDE 数值 / 多 mediator 链 → 后续 |
| 7 | 选择偏差 | **15-20%** | A1 §3a / A2 refusal pattern ✓ / **kernel V-set 放松** ✓（refusal-only 图返回 `cause=false (no path)`，case 16 e2e ✓）/ 显式 collider conditioning 检测 → Phase 9+ |
| 8 | 测量误差 | **0%** | → Phase 9+（按需）|
| 9 | 转移性 / 泛化 | **25-30%** | **Phase 9 §T9.1 已落地**：单源 + 可观测 S 的 Bareinboim transport identification（schema + types + identify + verifier T9-1/T9-2 + case 29）；只到结构层公式，数值估计 § T9.2 / 多源 §T9.3 / latent S → 后续 |
| 10 | 敏感性分析 | **~30%** | **Phase 8.2 已落地**（VanderWeele E-value 自动附在所有 binary outcome 估计上）；Rosenbaum bounds / 多假设 sensitivity → 可选扩展 |
| 11 | 连续 / 数据驱动估计 | **~50%** | **Phase 7.1-7.4 全部落地**（backdoor + front-door + IV + mediation numeric，4 条识别路径都能给数字 + CI）|
| 12 | 因果发现 | **~40%** | **Phase 8.1 已落地**（PC/FCI/LiNGAM via causal-learn + kernel_ast suggestion path）；NOTEARS / RL discovery → Phase 9+ |

**加权覆盖**：约 **60-70%**。**Phase 7 M2 + Phase 8 M3 + Phase 5 §T/§C + Phase 9 §T9.1** 全部落地——识别 / 估计 / 敏感性 / 发现 / 时序 / 反事实 / 转移性里程碑齐全。Phase 4 上游层端到端 e2e 3/3 通过（cases 14/16/21）；Phase 9 §T9.1 case 29 跑通（跑步×人群转移）。

---

## 元基础设施（不在 12 板块内但是核心价值来源）

这部分 Themis 比任何单一开源库都强——**没有同类**：

| 基础设施 | 状态 |
|---|---|
| NL↔JSON 桥（A1 v2.6.1 / A5 / A2 / response_rendering v3.1） | **~100%** |
| 上游层 narrative_merge（变量+边对称合并 + compose_program） | **~100%**（down-payment；ROADMAP 真独立层 → 长期） |
| V0-V5 独立 verifier（byte-code scan 钉独立性） | **~100%** |
| Derivation JSON + 审计字段 | **~100%** |
| 13 种 ambiguity kind 分类体系 | **~100%** |
| Eval set (28 cases / F1-F22) + 真实 LLM 基线 | **~100%** |
| `investigation_request` 报缺 + fill-back | **~100%** |
| Schema 层（atom / kernel_ast / query_result / derivation） | **~100%** |
| Theta 数值层 + confidence 聚合 | **~100%** |
| MCP server 包装（5 tools + 8 resources，stdio） | **~100%** |

---

## 每板块的具体策略

### 自家写（所有 production 代码在 `themis/` 下）

- 板块 1-10、12 的大部分算法
- 见具体板块的 "策略" 列

### 外部库的位置：只作 parity calibration，不作 production backend

开发时 pip install 以下库跑 parity test，**production 依赖里不包含**：

- **DoWhy**：板块 1 (identify) 的 parity 校准
- **EconML**：板块 5 / 6 / 11 的 parity 校准
- **causal-learn**：板块 12 的 parity 校准
- **pgmpy**：板块 2 BN 推理的 parity 校准
- **statsmodels / sklearn**：作为 ML 原语依赖，production 里装

### API 调用的 5 条允许规则

允许接外部 API 作 production backend 的条件（**必须全部满足**）：

1. ✅ 函数是**确定性纯变换**（同输入同输出）
2. ✅ 库有 **5+ 年稳定 track record**（主要 API 未破坏性变更）
3. ✅ **pin 具体版本**（`dowhy==0.11.1`，不用 `>=`）
4. ✅ 配套 **parity test**，每次升级必跑
5. ✅ 结果可 **完整嵌入** derivation JSON（无隐藏状态）

**任何一条不满足就自家写**。

**结论**：估计层（板块 11）的 ML 估计器**永远不接 API**——默认参数
漂移 + 随机性会破坏可审计承诺。识别层的纯算法 API（如 DoWhy.identify）
理论上可接，但因为 Themis 自己也要实现识别层，实际上还是自家写。

### 明确 defer / 不做的

- **C++ 核心方法** (grf 原版 Causal Forests) ——vendor 成本过高 /
  V0-V5 审不到 C++ 层。按需写纯 Python 简化版或 defer
- **SuperLearner TMLE** / 研究级统计方法——需要真实统计专家审
- **NOTEARS 等连续优化因果发现**——有需求再考虑 vendor gCastle
- **连续时间 SDE 因果**——不在 long-term scope 内
- **非因果问题**（预测、相关挖掘、纯 Bayesian 建模、优化）——明确
  不是 Themis 的场景，路由层识别后返回 "out of scope"

---

## 完成节奏目标

| Phase | 对应里程碑 | 完成后覆盖率（估）| 时间预估 |
|---|---|---|---|
| Phase 6 | M1 识别完整化 | ~30% | 4 周（不含 complete ID）|
| Phase 7 | M2 基础估计 | ~55% | 6-8 周 |
| Phase 8 | M3 发现 + 敏感性 | ~70% | 4-6 周 |
| Phase 9+ | 按需扩展 | → 逐步达 85-90% | 按真实压力 |

总计 M1-M3 约 **3.5-4.5 个月**完成核心三个里程碑，剩余部分按真实需
求逐个推进，永远不追求"100% 覆盖"（因为最后几个板块的 ROI 很低）。

---

## 和现有开源生态的差异化

每完成一个 slice 问自己这个问题：
**"Themis 在这个板块比 DoWhy / EconML / causal-learn 多做了什么？"**

答案应该来自 4 个维度：

1. **NL-native 接口**：用户用自然语言描述问题，不是填 API 参数
2. **Ambiguity 显式声明**：用户的歧义被识别 + 分类 + surface
3. **Derivation 可审计**：每一步推导有 rule name + witness
4. **V-verifier 独立审查**：结果不是"信 library"，是"我们重检过"

**如果某 slice 做完只是"复刻了 DoWhy 的算法"，那不是 Themis 想做
的东西**——必须能在上述 4 维之一显示出 Themis 的增量价值。

---

## 更新规则

- 完成一个 slice 后更新对应板块的百分比
- 新加板块或重排策略要先改 VISION / ROADMAP 再同步此文档
- 表格里的数字是主观估计，不是测试覆盖率，但要随着 eval set 扩大
  趋于准确
