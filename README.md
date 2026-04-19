# 因果推理内核 v0.1

基于 Pearl 因果图 + 关系级有限对象域的静态因果推理内核。

## 文档

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

`causal_kernel/` 下分四层 + 一个旁路：

```
input/     parser + syntactic validator + semantic validator
runtime/   instantiation / graph projection / structural solver /
           formula builder / numeric estimator (stub) /
           confidence calc (stub) / scheduler / investigation pusher
oracle/    pgmpy / ananke adapters + differential comparator（开发期）
output/    result orchestrator + explainer
```

v0.1 的所有模块目前只是接口签名，实现待后续迭代。

## 依赖

- 运行期：`networkx`、`jsonschema`
- 开发期（可选）：`pgmpy`、`ananke`

## 版本

- 当前：v0.1（结构层）
- 计划 v0.2：数值估计、ID 算法、composite confidence 正式语义、反事实
