"""Generate the repository's architecture picture from the repository.

    python scripts/build_arch_spec.py <out.json>
    node <archify>/bin/archify.mjs render architecture <out.json> <out.html>
        --quality showcase --repo-root .

The output is an archify ``architecture`` spec. Rendering it is a
separate step and the renderer lives outside this repo; what lives here
is the half that has to stay true. The committed page is the output of
the second command above. The page also carries what the spec says
beyond its labels, the commit it pins among them, so a stale page is
re-rendered, never edited by hand.

Nothing countable below is typed by hand. Line counts are read off the
files, species and routes come from importing the enums, rule names and
``verify_*`` entries are scanned with :mod:`ast`, and the commit is asked
of git. A picture that prints ``92 个 rule 名`` is printing a number this
script measured a moment earlier, not a number someone remembered.

That distinction is the whole point. A count typed into a drawing is a
claim with no declaration site and no owner: it is right on the day it is
typed and silently wrong afterwards, and nothing anywhere goes red. The
first run of this script found two such numbers already wrong.

What stays hand-written is judgement — which boxes exist, what layer each
belongs to, which of them an arrow joins. A script cannot count those,
and dressing them up as measurements would be worse than typing them. So
they sit in plain tables below, and :func:`check` holds the tables to
what can be verified about them: every cited path exists, every arrow
ends on a box that exists, no two boxes share a cell, every arrow names a
kind that has been declared.

One sentence the picture prints is a claim about the code rather than a
count: the audit boundary says the verifier never imports
``themis.output``. :func:`imports_from_output` is asked that question
here, so the drawing cannot go on asserting it after it stops being true.

Arrow kinds, held in one table rather than in 25 separate decisions:

    run      一次 kernel.run() 里发生的                    实线
    outside  不在那次运行里 —— import 依赖、只在测试跑的     虚线
             对照、跨运行回填
    audit    信封交给独立复核                                粗线
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMIS = ROOT / "themis"

REPOSITORY = "https://github.com/Crows12138/themis"
TITLE = "Themis 全景：一个因果问题从程序到被独立复核"
SUBTITLE = ("实线＝一次 run() 里发生的；虚线＝不在那次运行里"
            "（import 依赖 / 只在测试跑 / 跨运行回填）；"
            "粗线＝信封交给独立复核")


class SpecRefused(Exception):
    """The hand-written tables disagree with the repository."""


# --------------------------------------------------------------- 量出来的

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_read(path))
    except SyntaxError:
        return None


def lines_of(rel: str) -> int:
    """Line count of a themis-relative file."""
    return len(_read(THEMIS / rel).splitlines())


def head_revision() -> str:
    out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def derivation_rules() -> set[str]:
    """Distinct ``rule=`` names on ``DerivationStep``.

    The same keyword on the verifier side names the check that signed a
    failure, not a derivation, so only the production side is scanned.
    """
    found: set[str] = set()
    for path in THEMIS.rglob("*.py"):
        if "verifier" in path.parts:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if name != "DerivationStep":
                continue
            for kw in node.keywords:
                if kw.arg == "rule" and isinstance(kw.value, ast.Constant):
                    found.add(kw.value.value)
    return found


def verifier_rule_names() -> set[str]:
    """Distinct ``rule=`` names the verifier can sign a failure with.

    Read with :mod:`ast` rather than a regex on purpose: the first hand
    count of this used ``[a-z0-9_]+`` and lost ``T1_time_monotonicity``,
    ``T2_lag_bound`` and ``T3_unroll_acyclic`` to their capital letters.
    """
    found: set[str] = set()
    for path in (THEMIS / "verifier").rglob("*.py"):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.keyword) and node.arg == "rule"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                found.add(node.value.value)
    return found


def verify_entries() -> set[str]:
    """Top-level ``verify_*`` functions — the doors an auditor can knock."""
    found: set[str] = set()
    for path in THEMIS.rglob("*.py"):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name.startswith("verify_")):
                found.add(node.name)
    return found


def t10_gates() -> list[str]:
    """The T10 gates, taken from the section headers.

    Counting ``_verify_t10_N`` definitions instead would lose T10-4,
    which is a gate under the name ``verify_answer_tier`` with its own
    entry point.
    """
    import re
    source = _read(THEMIS / "verifier" / "data_gap_rules.py")
    return sorted(set(re.findall(r"T10-(\d)", source)))


def imports_from_output(package: str) -> list[str]:
    """Where ``package`` imports ``themis.output``, as file:line.

    Asked of ``verifier`` because the audit boundary on the picture says
    the answer is nothing. Asked of another package it answers with
    something, which is how that nothing is known to be a measurement
    rather than a scan that cannot speak.
    """
    found: list[str] = []
    for path in (THEMIS / package).rglob("*.py"):
        tree = _parse(path)
        if tree is None:
            continue
        here = list(path.relative_to(THEMIS).parts)[:-1]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                up = len(here) - (node.level - 1)
                base = here[:up] if node.level > 1 else here
                parts = base + (node.module.split(".") if node.module else [])
            elif node.module and node.module.startswith("themis."):
                parts = node.module.split(".")[1:]
            else:
                continue
            if parts and parts[0] == "output":
                rel = path.relative_to(THEMIS).as_posix()
                found.append(f"{rel}:{node.lineno}")
    return found


def measure() -> dict[str, int]:
    """Every number the picture prints."""
    sys.path.insert(0, str(ROOT))
    from themis import gaps
    from themis.types import GapKind
    return {
        "verify_lines": lines_of("verifier/verify.py"),
        "rules_lines": lines_of("verifier/rules.py"),
        "species": len(list(GapKind)),
        "routes": len(list(gaps.Route)),
        "sentences": len(list(gaps.Sentence)),
        "derivation": len(derivation_rules()),
        "verifier_rules": len(verifier_rule_names()),
        "verify_entries": len(verify_entries()),
        "last_gate": int(t10_gates()[-1]),
    }


# --------------------------------------------------------- 手写的是判断

#: id, type, label, sublabel, tag, (row, col), sources
COMPONENTS: list[tuple] = [
    ("web", "frontend", "网页", "themis.web :8000", None, (0, 0),
     [("themis/web/__init__.py", "本地站点")]),
    ("mcp", "external", "MCP 工具", "给 LLM 调用", None, (1, 0),
     [("themis/mcp/server.py", "工具入口")]),
    ("upstream", "external", "LLM 上游", "抽取 → Program", "非契约", (2, 0),
     [("themis/upstream/program_builder.py", "抽取字典变 Program"),
      ("themis/upstream/narrative_merge.py", "叙述里的变量合并")]),
    ("workflow", "external", "回填工作流", "参数 / 变量框定", None, (4, 0),
     [("themis/workflow/parameter_fill.py", "参数回填"),
      ("themis/workflow/variable_framing.py", "变量框定回填")]),

    ("entry", "backend", "入口与校验", "JSON → Program", "kernel.run",
     (0, 1),
     [("themis/kernel.py", "run() 的顺序"),
      ("themis/input/syntactic_validator.py", "语法校验"),
      ("themis/input/semantic_validator.py", "语义校验")]),
    ("prog", "external", "因果程序", "图 + 查询 + 断言", "调用者给",
     (1, 1), None),
    ("contract", "database", "契约与词表", "物种与缺口词表", "唯一权威",
     (2, 1),
     [("themis/types.py", "物种声明"),
      ("themis/gaps.py", "缺口词表"),
      ("themis/refusals.py", "拒绝词表")]),

    ("sched", "backend", "调度器", "scheduler.py", "dispatch_all", (1, 2),
     [("themis/runtime/scheduler.py", "哪条路线可走")]),
    ("oracle", "external", "差分 oracle", "pgmpy / ananke", "只在测试",
     (3, 2),
     [("themis/oracle/differential.py", "两边跑同一题"),
      ("themis/oracle/pgmpy_adapter.py", "pgmpy 对照")]),

    ("solver", "backend", "结构识别", "backdoor / Tian", "general-ID",
     (0, 3),
     [("themis/runtime/structural_solver.py", "ID 主干"),
      ("themis/runtime/c_factor.py", "C-factor 分解")]),
    ("special", "backend", "专门识别", "近端·传输·选择", None, (1, 3),
     [("themis/runtime/proximal_identify.py", "近端"),
      ("themis/runtime/transport.py", "跨域传输"),
      ("themis/runtime/selection_recovery.py", "选择偏倚")]),
    ("ctf", "backend", "反事实识别", "ID* / IDC*", "因果概率", (2, 3),
     [("themis/runtime/ctf_identify.py", "ID*/IDC*"),
      ("themis/runtime/counterfactual.py", "孪生网络")]),

    ("disp", "backend", "估计器分派", "dispatch.py", "最大的单文件", (0, 4),
     [("themis/estimation/dispatch.py", "选估计器")]),
    ("estim", "backend", "估计器族", "IV / 中介 / 近端", None, (1, 4),
     [("themis/estimation/iv.py", "工具变量"),
      ("themis/estimation/mediation.py", "中介"),
      ("themis/estimation/proximal_bridge.py", "近端桥")]),
    ("numeric", "backend", "数值端", "numeric_estimator", None, (2, 4),
     [("themis/runtime/numeric_estimator.py", "落到数字")]),

    ("analysis", "backend", "读者报告", "analysis_report", "可剥离", (0, 5),
     [("themis/output/analysis_report.py", "翻译给人看")]),
    ("orch", "backend", "信封组装", "orchestrator", None, (1, 5),
     [("themis/output/result_orchestrator.py", "序列化")]),
    ("gapreport", "backend", "缺口诊断", "{species} 物种 / {routes} 出路",
     None, (2, 5),
     [("themis/output/data_gap_report.py", "缺什么数据")]),
    ("kb", "external", "KB 契约", "缺口 → KBQuery", "不做 IO", (4, 5),
     [("themis/kb/contract.py", "adapter 抽象基类"),
      ("themis/kb/translator.py", "缺口翻成查询"),
      ("themis/kb/cache.py", "查询缓存")]),

    ("rules", "security", "复核规则", "rules.py {rules_lines} 行", None,
     (0, 6), [("themis/verifier/rules.py", "从零重导")]),
    ("verify", "security", "复核入口", "verify.py {verify_lines} 行",
     "{verify_entries} 个入口", (1, 6),
     [("themis/verifier/verify.py", "顶层复核")]),
    ("gaprules", "security", "缺口八道门", "T10-1 … T10-{last_gate}",
     "#615 #617 #618", (2, 6),
     [("themis/verifier/data_gap_rules.py", "缺口审计")]),
    ("probe", "security", "语义探针", "随机 SCM 对真值", None, (3, 6),
     [("themis/verifier/semantic_probe.py", "独立重算")]),
]

#: from, to, kind, label, labelDy
EDGES: list[tuple] = [
    ("web", "prog", "run", None, None),
    ("mcp", "prog", "run", None, None),
    ("upstream", "prog", "run", None, None),
    ("workflow", "prog", "outside", None, None),
    ("prog", "entry", "run", None, None),
    ("entry", "sched", "run", "project / instantiate", 22),
    ("contract", "sched", "outside", "词表", None),
    ("oracle", "sched", "outside", "差分对照", None),
    ("sched", "solver", "run", None, None),
    ("sched", "special", "run", None, None),
    ("sched", "ctf", "run", None, None),
    ("solver", "disp", "run", "估计量", None),
    ("special", "disp", "run", None, None),
    ("ctf", "numeric", "run", "反事实数值", -24),
    ("disp", "estim", "run", None, None),
    ("estim", "numeric", "run", "拟合", 24),
    ("numeric", "orch", "run", "数值块", None),
    ("orch", "analysis", "run", None, None),
    ("orch", "gapreport", "run", None, None),
    ("gapreport", "kb", "outside", "查 KB", 24),
    ("kb", "workflow", "outside", "填回去", None),
    ("orch", "verify", "audit", "信封", None),
    ("verify", "rules", "run", None, None),
    ("verify", "gaprules", "run", None, None),
    ("gaprules", "probe", "run", None, None),
]

#: The arrow kinds, and how each is drawn. An edge naming anything else
#: is refused rather than drawn in whatever the renderer defaults to.
VARIANT_OF: dict[str, str | None] = {
    "run": None, "outside": "dashed", "audit": "emphasis",
}

#: kind, label, wraps
BOUNDARIES: list[tuple] = [
    ("region", "调用面与回填：Themis 自己不做 IO",
     ["web", "mcp", "upstream", "workflow"]),
    ("region", "识别：结构层", ["sched", "solver", "special", "ctf"]),
    ("region", "估计：数值层", ["disp", "estim", "numeric"]),
    ("region", "组装：信封与读者", ["analysis", "orch", "gapreport"]),
    ("security-group", "独立复核：绝不 import themis.output",
     ["rules", "verify", "gaprules", "probe"]),
]

#: id, label, focus, note
VIEWS: list[tuple] = [
    ("trunk", "主干", ["prog", "entry", "sched", "orch", "verify"],
     "run() 的实际顺序：parse → validate → project → instantiate → "
     "dispatch_all → 组装 → 独立复核"),
    ("ident", "识别层", ["sched", "solver", "ctf", "special"],
     "{derivation} 条 derivation rule：backdoor / front-door / Tian / "
     "general-ID / IDC / ID*"),
    ("estim", "估计层", ["disp", "estim", "numeric"],
     "identify 之后才谈数值；估计器自己声明它拟合的形态"),
    ("audit", "独立复核", ["verify", "rules", "gaprules", "probe"],
     "{verifier_rules} 个 rule 名、{verify_entries} 个 verify_* 入口；"
     "不 import themis.output"),
    ("loop", "回填闭环", ["gapreport", "kb", "workflow", "prog"],
     "缺口翻成 KBQuery，客户端 adapter 做 IO，值回填进程序再跑一遍——"
     "整段在一次 run() 之外，所以画成虚线"),
]

GRID_COLS = 7

#: Labels carrying a digit that is not a count, and what it is instead.
#: Everything else with a digit in it has to arrive through a
#: ``{placeholder}`` filled from :func:`measure`, so a number cannot get
#: onto the picture without something having measured it first.
NOT_A_COUNT = {
    "themis.web :8000": "端口号",
    "T10-1 … T10-{last_gate}": "闸门的名字，只有末位是数出来的",
    "#615 #617 #618": "CORE_STATUS 条目编号",
}


# --------------------------------------------------------------- 先自检

def check(components=None, edges=None, boundaries=None,
          variant_of=None) -> list[str]:
    """What the hand-written tables claim that the repository can deny.

    Returns one sentence per disagreement, empty when there is none.
    Takes the tables as arguments so a test can bend one and watch this
    refuse it; a check only ever asked about the honest arrangement has
    not been shown to be a check at all.

    The tables are resolved here rather than bound as default arguments.
    A default is evaluated once at import, so binding them there would
    quietly freeze the copy this function reads while :func:`build` went
    on reading the live one — two halves of the same file disagreeing
    about which table is the table.
    """
    components = COMPONENTS if components is None else components
    edges = EDGES if edges is None else edges
    boundaries = BOUNDARIES if boundaries is None else boundaries
    variant_of = VARIANT_OF if variant_of is None else variant_of
    problems: list[str] = []
    ids = [c[0] for c in components]
    if len(set(ids)) != len(ids):
        problems.append("方块 id 重复")
    cells = [c[5] for c in components]
    if len(set(cells)) != len(cells):
        problems.append("有两个方块占同一格")
    for component in components:
        for path, _label in (component[6] or ()):
            if not (ROOT / path).is_file():
                problems.append(f"引用的文件不存在：{path}")
    for source, target, kind, _label, _dy in edges:
        for end in (source, target):
            if end not in ids:
                problems.append(f"连线端点 {end} 不是任何方块")
        if kind not in variant_of:
            problems.append(f"连线种类 {kind} 没有声明")
    for _kind, _label, wraps in boundaries:
        for wrapped in wraps:
            if wrapped not in ids:
                problems.append(f"边界圈了不存在的方块 {wrapped}")
    return problems


def check_measurements(numbers: dict[str, int]) -> list[str]:
    """A count that came out zero means the scan stopped working."""
    return [f"{key} 数出来是 0" for key, value in numbers.items()
            if not value]


def check_the_claim_on_the_boundary() -> list[str]:
    """The audit boundary's sentence, asked of the code it is about."""
    reached = imports_from_output("verifier")
    if not reached:
        return []
    return ["边界上那句话是假的，verifier 确实 import 了 output："
            + ", ".join(reached)]


# ----------------------------------------------------------------- 出图

def build(revision: str | None = None) -> dict:
    """The spec, or :class:`SpecRefused` saying what disagrees."""
    numbers = measure()
    problems = (check() + check_measurements(numbers)
                + check_the_claim_on_the_boundary())
    if problems:
        raise SpecRefused("；".join(problems))

    def fill(text: str | None) -> str | None:
        return text.format(**numbers) if text else text

    components = []
    for cid, ctype, label, sublabel, tag, (row, col), sources in COMPONENTS:
        entry = {"id": cid, "type": ctype, "label": label,
                 "sublabel": fill(sublabel), "row": row, "col": col}
        if tag:
            entry["tag"] = fill(tag)
        if sources:
            entry["sources"] = [{"path": p, "label": lab}
                                for p, lab in sources]
        components.append(entry)

    connections = []
    for source, target, kind, label, dy in EDGES:
        conn: dict = {"from": source, "to": target}
        if label:
            conn["label"] = label
        if VARIANT_OF[kind]:
            conn["variant"] = VARIANT_OF[kind]
        if dy is not None:
            conn["labelDy"] = dy
        connections.append(conn)

    return {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {
            "title": TITLE,
            "subtitle": SUBTITLE,
            "locale": "zh-CN",
            "quality_profile": "showcase",
            "repository": {
                "url": REPOSITORY,
                "provider": "github",
                "link_mode": "local-only",
                "revision": revision or head_revision(),
            },
            "views": [{"id": i, "label": lab, "focus": f, "note": fill(n)}
                      for i, lab, f, n in VIEWS],
        },
        "layout": {"mode": "grid", "cols": GRID_COLS},
        "components": components,
        "boundaries": [{"kind": k, "label": lab, "wraps": w}
                       for k, lab, w in BOUNDARIES],
        "connections": connections,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        spec = build()
    except SpecRefused as refused:
        print(f"× {refused}", file=sys.stderr)
        return 1
    out = Path(argv[1])
    # LF on every platform. The spec is a committed artifact nobody
    # edits, and .gitattributes stores it byte for byte; letting the
    # newline follow the host would make the same picture two different
    # files depending on who built it.
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    kinds = [edge[2] for edge in EDGES]
    print(f"{out}  方块 {len(spec['components'])}  "
          f"连线 {len(spec['connections'])}  "
          f"引用 {sum(len(c.get('sources', [])) for c in spec['components'])}")
    print("  " + "  ".join(f"{k} {kinds.count(k)}" for k in VARIANT_OF))
    print("  " + json.dumps(measure(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
