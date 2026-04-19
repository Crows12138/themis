# Themis — 因果推理内核 v0.1

基于 Pearl 因果图 + 关系级有限对象域的静态因果推理内核。
核心立意：**语义干净、缺口显式、扩展点清楚**——而不是算法先进。

## 当前能力（一句话）

结构可识别（cause / assoc / 后门 identify）+ 数值可评估（effect / probability，基于用户提供的 Theta）+ 诚实的缺口报告（needs_investigation 四态）+ pgmpy 差分可验证。

完整 scope freeze 见 **[`v0_1_scope.md`](v0_1_scope.md)**。

## 文档

- `v0_1_scope.md` — **v0.1 能力与边界（权威契约）**
- `理论框架_v0_1.md` — 语言与语义形式定义
- `formula_ast_spec_v0_1.md` — 公式子语言规范
- `因果图规则总览.md` — d-sep / 后门 / 调整集教学版
- `ARCHITECTURE.md` — 分层、依赖方向、反模式

## Schema

- `atom.schema.json` — 共享原子 / 项定义
- `kernel_ast.schema.json` — 程序 AST
- `query_result.schema.json` — 查询结果
- `minimal_example_v0_1.json` — 最小示例

## 代码

`themis/` 下分四层 + 一个旁路：

```
input/     parser + syntactic validator + semantic validator (两阶段)
runtime/   instantiation / graph projection / structural solver /
           formula builder / theta builder / numeric estimator /
           confidence calc (v0.1 占位) / scheduler / investigation pusher
oracle/    pgmpy / ananke adapters + differential comparator（开发期）
output/    result orchestrator + explainer
```

各模块实现状态详见 `v0_1_scope.md`。

## 依赖

- 运行期：`networkx`、`jsonschema`、`referencing`
- 开发期（可选）：`pgmpy`、`ananke`、`pytest`

## 版本

- 当前：v0.1（结构层 + 数值层 MVP）
- v0.2 候选范围见 `v0_1_scope.md` 末节
