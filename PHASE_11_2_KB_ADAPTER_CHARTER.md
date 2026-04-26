# Phase 11.2 Charter — KB Adapter Contract + Reference Implementation

> 立项日期：2026-04-27
> 母 charter：[`PHASE_11_AGENT_LOOP_CHARTER.md`](PHASE_11_AGENT_LOOP_CHARTER.md)
> 状态：**待确认范围 / 未开始**
> 触发：S.11.1 prompt-only 闭环已落地 + 验证可用；下一步把 LLM 那
> 一头的 "WebSearch 字符串" 升级成结构化 KB lookup 接口

## 0. 总策略：adapter-first

母 charter 提议先做 PrimeKG（1.5w），由具体 KB 驱动抽象。但那条路径
在做完 PrimeKG 后到 SciGraph / SemMedDB 时大概率要重构 — 因为
PrimeKG-shaped 抽象会被偏倚。

**S.11.2 改走 adapter-first**：
- 先定 `KBAdapter` 接口 + `KBQuery` / `KBResult` / `KBProvenance`
  schema + cache 骨架 + 一个 reference 适配器
- reference 适配器**包装现有 WebSearch 路径**（gap_to_action.md 已经
  在 prompt 层用 WebSearch 跑闭环了，本阶段把它结构化）
- 之后 PrimeKG / SciGraph / SemMedDB 各 ~3 天插件式接入（S.11.3+）

总工作量预计减少 50%（一次性搭骨架 vs 每个 KB 重新做）。

## 1. VISION 边界（不能越）

- ❌ **Themis 自己不发网络请求**。adapter 实现在客户端 / 第三方 repo
  里，Themis 只提供契约
- ❌ **不内建 agent runtime**（母 charter §4 已约定）
- ❌ **不调外部 LLM 完成 fetch**
- ✅ **Themis 提供 schema + translator + 可选 cache**
- ✅ **adapter 调用结果通过 `apply_patch_and_run` 喂回**，仍走 verifier

也就是说本阶段**仍然没有任何网络代码进入 Themis**。Themis 是被动
的契约定义者，不是主动的数据获取器。

## 2. 交付物（按文件）

### 2.1 Schema 层 `themis/kb/schemas.py`

三个 dataclass + 对应 JSON schema：

```python
@dataclass
class KBQuery:
    kb_name: str               # "primekg" / "semmeddb" / "websearch_pubmed" / ...
    query_kind: Literal[       # 来自 gap_kind 的映射
        "marginal_distribution",
        "conditional_distribution",
        "stratified_subgroup",
        "iv_candidate",
        "mediator_distribution",
        "target_population_marginal",
    ]
    target: dict               # {predicate, args, value} or {predicate, given: [...]}
    population: str | None     # 人群标签，匹配 transport population
    constraints: dict          # {time_window, age_range, sex, ...}
    raw_string: str | None     # 客户端的自由形式 query string（fallback）

@dataclass
class KBProvenance:
    source_kb: str             # adapter 名
    query_used: KBQuery        # 完整问 KB 的查询
    retrieved_at: str          # ISO 8601
    raw_response_hash: str     # 原始返回的哈希（reproducibility）
    citation: str              # PMID / DOI / URL / dataset+row
    confidence_grade: Literal[ # KB 自己声明的证据等级
        "rct_meta_analysis",
        "single_rct",
        "cohort",
        "case_control",
        "expert_opinion",
        "unknown",
    ]
    notes: str | None

@dataclass
class KBResult:
    query: KBQuery             # 重复 query 方便审计
    success: bool
    value: float | None        # 数值（对 distribution-类查询）
    interval: tuple[float, float] | None   # CI / IQR
    sample_size: int | None
    population_in_source: str | None
    provenance: KBProvenance
    failure_reason: str | None # 失败时填
```

JSON schema mirrors live in `themis/schemas/kb_*.schema.json`。

### 2.2 Adapter 契约 `themis/kb/contract.py`

抽象基类 + 注册机制：

```python
class KBAdapter(ABC):
    name: str                  # 唯一标识

    @abstractmethod
    def query(self, q: KBQuery) -> KBResult:
        """同步调用；要异步在客户端外面包装"""

    @classmethod
    def supports(cls, q: KBQuery) -> bool:
        """adapter 是否能处理这个 query（kb_name 匹配 + query_kind 在能力范围）"""
        return q.kb_name == cls.name


class KBRegistry:
    def register(self, adapter: KBAdapter) -> None: ...
    def find(self, q: KBQuery) -> KBAdapter | None: ...
    def list(self) -> list[str]: ...
```

注意：**Themis 不实例化任何具体 adapter**。`KBRegistry` 是一个
client-side 容器，Themis 只提供它的形状定义。这保持 "Themis 不发
网络请求" 的不变量。

### 2.3 Translator `themis/kb/translator.py`

两个纯函数（确定性、无 IO）：

```python
def gap_to_kb_query(gap: DataGap, kb_hint: str | None = None) -> KBQuery:
    """从 data_gap_report 的一个 gap 推一个结构化 KB 查询。
    kb_hint 让客户端选 KB（如果 None 则按 gap_kind 默认）。"""

def kb_result_to_patch(
    result: KBResult,
    gap: DataGap,
) -> ParameterFillBundle | None:
    """把 KBResult 转成 apply_patch_and_run 接受的 patch；
    失败 / dtype 不匹配返回 None（按 gap_to_action.md 的 Q3）。
    构造的 patch.annotations.source 来自 result.provenance.citation。"""
```

这两个函数是 S.11.2 的**核心**：让客户端不用每次重新推查询形状 +
每次重新构 patch。

### 2.4 Cache `themis/kb/cache.py`

SQLite 单表缓存：

```python
class KBCache:
    def __init__(self, db_path: Path | str = ":memory:"): ...
    def get(self, q: KBQuery) -> KBResult | None: ...
    def put(self, q: KBQuery, r: KBResult) -> None: ...
    def stats(self) -> dict: ...
```

key = (kb_name, sha256(json.dumps(q, sort_keys=True)))。值是 KBResult
的 JSON 序列化 + 时间戳。**不带 TTL**（fact-style 数据不该失效；客户
端要 refresh 自己 .delete + .put）。

### 2.5 Reference adapter — `themis/kb/adapters/websearch_proxy.py`

最小实现：包装一个签名 `(query: str) -> str` 的 callable（客户端注入
真实 WebSearch / 任何文本检索）。

```python
class WebSearchProxyAdapter(KBAdapter):
    name = "websearch_proxy"

    def __init__(self, search_fn: Callable[[str], str]):
        self._search = search_fn

    def query(self, q: KBQuery) -> KBResult:
        # 把 KBQuery 渲染成自然语言搜索词 → 调 search_fn → 返回 KBResult
        # 解析失败时 result.success=False, failure_reason=...
```

这是 reference 实现，不替代未来真正的 PrimeKG / SemMedDB adapter，
只是验证契约形状能跑。

### 2.6 MCP 暴露

新增 3 项：

- 新 resource：`themis://schemas/kb_query.json`
- 新 resource：`themis://schemas/kb_result.json`
- 新 prompt：`docs/prompts/kb_lookup.md` —— 教 LLM 怎么用结构化
  KBQuery 替代自由 WebSearch 字符串，以及怎么把返回的 KBResult 喂回
  `apply_patch_and_run`

不新增 MCP tool —— Themis 不执行 lookup，所以没什么可暴露给 LLM 调
的。LLM 看到 schema + prompt 就能自己组装。

### 2.7 文档

- `PHASE_11_2_KB_ADAPTER_CHARTER.md`（本文档）
- `themis/kb/README.md` —— 给 adapter 实现者的 quickstart
- `gap_to_action.md` 微调：把 §"Patch shapes" 那段升级为"用
  `gap_to_kb_query` + `kb_result_to_patch` 替代手工构造 patch（如
  果客户端有 KBAdapter；没有则保留 fallback 路径）"
- COVERAGE_MAP / CORE_STATUS 同步状态

## 3. Sub-slices（建议交付顺序）

| Sub | 内容 | 估时 |
|---|---|---|
| **S.11.2.1** | schemas.py + JSON schema + tests | 3h |
| **S.11.2.2** | contract.py + registry + tests | 2h |
| **S.11.2.3** | translator.py（gap→query, result→patch） + tests | 4h |
| **S.11.2.4** | cache.py SQLite + tests | 2h |
| **S.11.2.5** | websearch_proxy reference adapter + tests | 2h |
| **S.11.2.6** | MCP resource 注册 + kb_lookup.md prompt | 2h |
| **S.11.2.7** | gap_to_action.md 集成更新 + subagent 真测 | 2h |

总 ~17h 净写代码 / 文档时间 + 真测。

## 4. 验收

### 必须
- 1171 baseline tests 不降级
- 新增 ≥ 80 tests 覆盖 schemas / contract / translator / cache /
  reference adapter
- subagent 真测：用 reference adapter（mock search_fn）跑一遍闭环
  ——给一个 missing_distribution gap → translator 生成 KBQuery →
  adapter 返回 KBResult → translator 转成 patch → apply_patch_and_run
  接受
- T10 verifier 仍通过（patch 带的 annotations.source 必须可解析回
  KBProvenance）

### 应该
- README 让外部开发者能在 30 分钟内写出第一个 PrimeKG 适配器
- 一个 worked example 文档：从 NL question → kernel_ast → run →
  data_gap_report → KBQuery → mock KBResult → patch → re-run →
  numerically_solved，全链路 JSON 都贴出来

## 5. 显式 Out-of-scope（本阶段不做）

- ❌ 真实 PrimeKG / SciGraph / SemMedDB / Wikidata adapter（S.11.3+）
- ❌ 冲突解决（S.11.7：多 KB 给不同结论时怎么加权）
- ❌ KB 自动 refresh / TTL
- ❌ Themis 内置任何 HTTP client / 数据库 driver
- ❌ Async adapter（先做同步契约；async 如有真实需求再加）

## 6. 永远不做

- 把 KBAdapter 实例 vendor 进 themis package（违反 VISION "no LLM /
  no network IO"）
- 在 Themis 里跑 LLM 解析 KB 自由文本返回（LLM 在客户端，结果以结构
  化 KBResult 喂回）
- 通过 KB lookup 旁路 verifier（所有 KB 取数都走 patch → verify 链路）

## 7. Review checklist（用户答）

1. ☐ Adapter-first 这个判断是否成立？还是直接做 PrimeKG（charter 原序）？
2. ☐ Reference adapter 用 WebSearch proxy 是否合适？还是不做
   reference adapter，让客户端自己实现第一个？
3. ☐ Cache 一开始就上 SQLite，还是先内存 dict 跑通再说？
4. ☐ 7 个 sub-slice 是否合理？是否要合并？
5. ☐ kb_lookup.md prompt 是否新建，还是合进 gap_to_action.md？
