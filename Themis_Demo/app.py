# -*- coding: utf-8 -*-
"""Themis 统一现场体验 —— 覆盖从普通用户到专业用户的全光谱。

四个标签页，后端全部跑真实 themis：
  1. 问问题（普通用户）   自然语言 → kernel_ast → 答（复用 themis.web.llm_bridge，需 API key）
  2. 选场景（零配置）     预置 6 个因果问题 → themis.run（离线，不翻车）
  3. 编辑 kernel_ast      粘/改 JSON → themis.run（离线，技术向）
  4. 专业：数据→真数字    上传/示例 CSV → themis.estimate → 点估计 + 置信区间 + 敏感性

启动：python app.py  → 浏览器 http://127.0.0.1:7860
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO = Path(r"C:\Users\12916\Desktop\项目\因果性ai")
if REPO.exists() and str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import os  # noqa: E402

import themis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

# --- 本机 Max 代理：① 问问题模式的 LLM 全部走这里，不用按量 key ---
# 可用环境变量 THEMIS_DEMO_PROXY 覆盖；若已设 ANTHROPIC_BASE_URL 则尊重既有值。
# 注意：proxy 必须能从运行 demo 的这台机器访问到（本机即 127.0.0.1:7777）。
PROXY_URL = os.environ.get("THEMIS_DEMO_PROXY", "http://127.0.0.1:7777")
os.environ.setdefault("ANTHROPIC_BASE_URL", PROXY_URL)
os.environ.setdefault("ANTHROPIC_API_KEY", "x")  # 占位；真正鉴权由代理负责

EXAMPLES = REPO / "themis" / "prompts" / "examples"


# ============================================================ 场景 / AST
def _load(fn):
    prog = json.loads((EXAMPLES / fn).read_text(encoding="utf-8"))
    return prog.get("kernel_ast", prog)


def _atom(p, obj="patient"):
    return {"predicate": p, "args": [{"type": "const", "name": obj}]}


def biomed_ast():
    """靶向药 → 肿瘤反应，疾病严重程度是混杂。贯穿场景页 + 专业页。"""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "patient"}]},
        "statements": [
            {"kind": "variable", "predicate": "targeted_drug", "domain": [True, False]},
            {"kind": "variable", "predicate": "tumor_response", "domain": [True, False]},
            {"kind": "variable", "predicate": "disease_severity", "domain": [True, False]},
            {"kind": "cause", "from": _atom("disease_severity"), "to": _atom("targeted_drug"), "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("disease_severity"), "to": _atom("tumor_response"), "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("targeted_drug"), "to": _atom("tumor_response"), "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "target": {"atom": _atom("tumor_response"), "value": True},
                "intervention": {"atom": _atom("targeted_drug"), "value": True}, "given": []}},
        ],
    }


SCENARIOS = [
    {"id": "biomed", "q": "靶向药能让肿瘤缩小吗？（疾病严重程度同时影响“是否用药”和“疗效”——混杂）",
     "tag": "生物医学 · 混杂", "note": "对应 PPT 第 6 页。Themis 要求对混杂做后门调整，给公式但拒绝编数字。", "ast": biomed_ast()},
    {"id": "veggies", "q": "多吃蔬菜能降血压吗？", "tag": "健康", "note": "", "ast": _load("veggies_blood_pressure.json")},
    {"id": "sleep", "q": "经常熬夜会让人变笨（认知下降）吗？", "tag": "健康", "note": "", "ast": _load("sleep_cognition.json")},
    {"id": "exercise", "q": "运动能减小腰围吗？", "tag": "健康", "note": "", "ast": _load("exercise_waist.json")},
    {"id": "cause_late", "q": "熬夜和第二天疲倦之间，因果结构成立吗？", "tag": "结构判定",
     "note": "cause 查询：只问结构，不问数值。", "ast": _load("late_night_tired_temporal.json")},
    {"id": "cf_career", "q": "如果当初选了另一份工作，现在会更幸福吗？（反事实）", "tag": "反事实",
     "note": "Themis 会指出需要补充一个假设。", "ast": _load("career_choice_counterfactual.json")},
]
SCEN_BY_ID = {s["id"]: s for s in SCENARIOS}


# ============================================================ 合成示例数据（专业页）
def _make_sample_csv():
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(0)
    n = 4000
    sev = rng.binomial(1, 0.45, n)                       # 混杂：疾病严重程度
    drug = rng.binomial(1, 0.3 + 0.4 * sev)              # 严重者更可能用药
    p = np.clip(0.2 + 0.35 * drug - 0.25 * sev, 0.02, 0.98)
    resp = rng.binomial(1, p)
    df = pd.DataFrame({
        "targeted_drug": drug.astype(bool),
        "tumor_response": resp.astype(bool),
        "disease_severity": sev.astype(bool),
    })
    return df.to_csv(index=False)


SAMPLE_CSV = _make_sample_csv()


# ============================================================ 渲染辅助
STATUS_CN = {
    "needs_investigation": ("需要进一步调查", "#ED7D31", "结构上可识别（给出识别公式），但缺数据 → 内核拒绝编数字，并列出还缺什么。"),
    "structurally_solved": ("结构上已确立", "#4F8A3A", "因果结构本身成立；是否有数值取决于是否提供数据。"),
    "needs_assumption": ("需要补充假设", "#C0504D", "当前信息下无法回答，需要你显式补一个假设（认识论选择，内核不替你拍板）。"),
    "numerically_solved": ("已算出数值", "#2E7D32", "提供了数据/参数，内核完成识别并算出数值。"),
    "identified": ("已识别", "#4F8A3A", "可识别。"),
}
GAPKIND_CN = {
    "missing_distribution": "缺少所需的概率分布（需要真实数据）",
    "missing_population_distribution": "缺少目标人群的分布",
    "ambiguous_variable_definition": "变量定义不清（需操作化：时间窗/测量/阈值…）",
    "ill_defined_intervention_versions": "干预定义不明确（同一状态可由不同操纵实现）",
    "answer_is_bounds_not_point_estimate": "答案本质是区间，而非一个点估计",
    "unverified_proposal_edge_on_query_path": "查询路径上有“LLM 提出但未经验证”的边",
    "unmeasured_confounder_risk": "存在未测量混杂的风险",
    "missing_iv_candidate": "缺少可用的工具变量",
    "missing_mediator_data": "缺少中介变量的数据",
    "missing_assumption": "缺少一个必要假设",
    "counterfactual_identification_assumption_required": "反事实识别需要补充假设",
}
SEV_COLOR = {"blocking": "#C0504D", "important": "#ED7D31", "info": "#888"}


def _atom_str(a):
    inner = a.get("atom", a)
    pred = inner.get("predicate", "?")
    val = a.get("value", inner.get("value"))
    if val is True:
        return pred
    if val is False:
        return f"¬{pred}"
    if isinstance(val, dict) and val.get("kind") == "var_ref":
        return f"{pred}=z"
    return f"{pred}={val}"


def fmt_formula(node):
    if not isinstance(node, dict):
        return str(node)
    k = node.get("kind")
    if k == "probability_ref":
        tgt = _atom_str(node["target"])
        given = node.get("given", [])
        return f"P({tgt} | {', '.join(_atom_str(g) for g in given)})" if given else f"P({tgt})"
    if k == "sum":
        over = node.get("over", {}).get("predicate", "z")
        return f"Σ_{over} [ {fmt_formula(node.get('body'))} ]"
    if k == "product":
        return " · ".join(fmt_formula(t) for t in node.get("terms", []))
    if k == "fraction":
        return f"( {fmt_formula(node.get('numerator'))} ) / ( {fmt_formula(node.get('denominator'))} )"
    return k or "?"


def _q_atom(a):
    inner = a.get("atom", a)
    p = inner.get("predicate", "?")
    v = a.get("value", inner.get("value"))
    if v is True:
        return p
    if v is False:
        return f"¬{p}"
    if v is None:
        return p
    return f"{p}={v}"


def _query_str(q):
    kind = q.get("kind", "?")
    parts = []
    if "intervention" in q:
        parts.append("do(" + _q_atom(q["intervention"]) + ")")
    if "from" in q:
        parts.append(_q_atom(q["from"]))
    if "target" in q:
        parts.append(_q_atom(q["target"]))
    if "to" in q:
        parts.append(_q_atom(q["to"]))
    body = " → ".join(parts)
    given = q.get("given") or []
    g = ("　给定 " + ", ".join(_q_atom(x) for x in given)) if given else ""
    return f"{kind}：{body}{g}"


def _q_pred(a):
    """取 query 槽里 atom 的 predicate（intervention/target/from/to 等）。"""
    if not isinstance(a, dict):
        return None
    return a.get("atom", a).get("predicate")


def _query_main_edge(q):
    """查询主边 = 用户问的那条因果关系（intervention→target / from→to /
    反事实）。它是问题本身、不是 LLM 假设 —— 签收面板与图着色把它当中性。"""
    src = (_q_pred(q.get("intervention")) or _q_pred(q.get("from"))
           or _q_pred(q.get("counterfactual_intervention")))
    dst = (_q_pred(q.get("target")) or _q_pred(q.get("to"))
           or _q_pred(q.get("counterfactual_target")))
    return {"from": src, "to": dst} if (src and dst) else None


def dag_view(ast):
    """把 kernel_ast 抽成可读的 DAG：变量 / 因果边(带来源) / 查询 / 查询主边。"""
    variables, edges, query, query_edge = [], [], None, None
    for st in ast.get("statements", []):
        k = st.get("kind")
        if k == "variable":
            variables.append(st.get("predicate"))
        elif k == "cause":
            src = (st.get("annotations") or {}).get("source", "") or ""
            edges.append({
                "from": (st.get("from") or {}).get("predicate"),
                "to": (st.get("to") or {}).get("predicate"),
                "source": src,
            })
        elif k == "query":
            qd = st.get("query", {})
            query = _query_str(qd)
            query_edge = _query_main_edge(qd)
    return {"variables": variables, "edges": edges, "query": query,
            "query_edge": query_edge}


def summarize(ast):
    r = themis.run(ast)["results"][0]
    status = r.get("status", "?")
    label, color, blurb = STATUS_CN.get(status, (status, "#555", ""))
    formula_str = None
    if r.get("formula"):
        try:
            formula_str = fmt_formula(r["formula"])
        except Exception:
            formula_str = None
    bounds = r.get("bounds_result")
    bounds_view = {"method": bounds.get("method"), "lower": bounds.get("lower_expression"),
                   "upper": bounds.get("upper_expression")} if bounds else None
    gaps = []
    for g in (r.get("data_gap_report", {}) or {}).get("gaps", []):
        gaps.append({"label": GAPKIND_CN.get(g.get("kind"), g.get("kind")),
                     "severity": g.get("severity", "info"),
                     "sev_color": SEV_COLOR.get(g.get("severity", "info"), "#888"),
                     "desc": (g.get("description") or "")[:220]})
    return {"status": status, "status_label": label, "status_color": color, "status_blurb": blurb,
            "query_kind": r.get("query_kind"), "formula": formula_str,
            "bounds": bounds_view, "gaps": gaps, "dag": dag_view(ast), "full": r}


# ============================================================ FastAPI
app = FastAPI(title="Themis 统一现场体验")


class RunReq(BaseModel):
    scenario_id: str | None = None
    ast: dict | None = None


class AskReq(BaseModel):
    nl: str
    api_key: str | None = None


class EstimateReq(BaseModel):
    csv_text: str | None = None
    scenario_id: str = "biomed"


@app.get("/api/scenarios")
def scenarios():
    return [{"id": s["id"], "q": s["q"], "tag": s["tag"], "note": s["note"]} for s in SCENARIOS]


@app.post("/api/run")
def run(req: RunReq):
    try:
        if req.ast is not None:
            ast = req.ast
        elif req.scenario_id in SCEN_BY_ID:
            ast = SCEN_BY_ID[req.scenario_id]["ast"]
        else:
            return JSONResponse({"ok": False, "error": "未指定有效场景或 AST"}, status_code=200)
        s = summarize(ast)
        return {"ok": True, "summary": {k: v for k, v in s.items() if k != "full"},
                "ast": ast, "full_result": s["full"]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _resolve_key(req_key):
    """走本机 Max 代理（PROXY_URL），不用按量 key、不撞 429、不烧钱。
    anthropic SDK 从 ANTHROPIC_BASE_URL 读代理地址，api_key 给个占位 'x' 即可
    （代理负责真正的鉴权 / 走 Max 套餐）。请求显式传 key 时仍尊重它。"""
    return req_key or "x"


# framing 闸门 = 这些 gap 在；借 LIFEE 追问的"结构化提问"做法，但问题数由 kernel 决定、措辞中性。
FRAMING_KINDS = {"ambiguous_variable_definition", "ill_defined_intervention_versions"}


def _anthropic_json(prompt, key, max_tokens=900):
    """走本机代理调 LLM 解析出 JSON（追问卡生成用）。LLM 偶发吐坏 JSON，重试一次。"""
    import re
    from anthropic import Anthropic
    client = Anthropic(api_key=key or "x")  # base_url 从 ANTHROPIC_BASE_URL 读
    last = None
    for _ in range(2):
        msg = client.messages.create(
            model=os.environ.get("THEMIS_LLM_MODEL", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", None) == "text").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        if not text.startswith("{"):
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                text = m.group(0)
        try:
            return json.loads(text)
        except Exception as e:
            last = e
    raise last


_FRAMING_FIELDS = {"state_vs_event", "time_window", "measurement", "threshold",
                   "observability", "direction", "baseline"}


def _pick_var(desc):
    """从 gap 描述里挑出真正的变量名 —— 跳过 time_window/state_vs_event 这类框架字段名。"""
    import re
    for m in re.finditer(r"[`「]([A-Za-z_]\w*)[`」]", desc):
        if m.group(1) not in _FRAMING_FIELDS:
            return m.group(1)
    return None


# 清掉一个变量的 ambiguous gap 需要这 7 个字段全有值（实测：少一个都不清）。
_FILL_FIELDS = ("time_window", "measurement", "threshold", "observability",
                "direction", "baseline", "state_vs_event")


def _framing_vars(result):
    """从 gap 报告里挑出"缺操作化"的变量（去重，一个变量一项）。"""
    out, seen = [], set()
    for g in (result.get("data_gap_report") or {}).get("gaps", []):
        if g.get("kind") in FRAMING_KINDS:
            v = _pick_var(g.get("description") or "")
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _complete_fields(d):
    """保证 7 个字段都有非空值（缺的用通用默认填上）——确保 patch 后 gap 必清。"""
    base = {
        "time_window": "未指定（默认：研究随访期）",
        "measurement": "未指定（默认：标准测量）",
        "threshold": "未指定（默认：任意可测变化）",
        "observability": "observable",
        "direction": "up",
        "baseline": "未指定（默认：当前状态）",
        "state_vs_event": "state",
    }
    for k in _FILL_FIELDS:
        v = (d or {}).get(k)
        if isinstance(v, str) and v.strip():
            base[k] = v.strip()
    return base


def _fallback_options(predicate):
    """LLM 失败时兜底 —— 一个"标准操作化"，7 字段全填，保证能清 gap。"""
    return [{"label": "采用标准操作化（其余维度用合理默认）", "fields": _complete_fields({})}]


def gen_framing_options(nl, predicate, key):
    """为一个变量生成 3-4 个"完整操作化"选项：每个选项含全部 7 字段值，
    点一下就能 patch 满、清掉该变量的 gap。失败返回 None（上层用 fallback）。"""
    prompt = (
        "你在帮 Themis 把一个因果问题里某个变量/干预的“操作化定义”补全。"
        "请为该变量生成 3-4 个**完整**操作化选项，每个是一个现实场景，并给出它隐含的全部字段值。\n\n"
        f"原问题：{nl}\n要补全的变量：{predicate}\n\n"
        "每个选项必须给全这 7 个字段（都要具体值，次要维度用合理默认）：\n"
        "time_window（时间窗）, measurement（测量方式）, threshold（阈值/切点）, "
        "observability（observable / self-reported / latent）, direction（up / down / mixed）, "
        "baseline（基线）, state_vs_event（state / event）\n\n"
        "规则：label 是短中文场景（≤20字）；中性精确，不寒暄；严格输出 JSON：\n"
        "{\"options\":[{\"label\":\"...\",\"fields\":{\"time_window\":\"...\",\"measurement\":\"...\","
        "\"threshold\":\"...\",\"observability\":\"...\",\"direction\":\"...\",\"baseline\":\"...\","
        "\"state_vs_event\":\"...\"}}]}"
    )
    try:
        d = _anthropic_json(prompt, key, max_tokens=1200)
        out = []
        for o in (d.get("options") or []):
            lab = str(o.get("label", "")).strip()
            if lab:
                out.append({"label": lab, "fields": _complete_fields(o.get("fields") or {})})
        return out or None
    except Exception:
        return None


def build_framing_followup(nl, fvars, key):
    """一变量一题；每题选项是完整操作化（点了 patch 满全部字段，确定性清 gap）。"""
    questions = []
    for pred in fvars:
        opts = gen_framing_options(nl, pred, key) or _fallback_options(pred)
        questions.append({
            "predicate": pred,
            "q": f"请明确「{pred}」具体指什么（选一个完整定义，每项已含全部维度）",
            "options": opts,
        })
    return {
        "intro": "在分析前，先把下面每个变量定义清楚 —— 点一个完整选项即可；想更精确可展开「▾维度」直接改任意字段（预设是起点，不是牢笼）。",
        "questions": questions,
    }


def _answer(ast, nl, extra=None):
    s = summarize(ast)  # 结构化秒出；长 prose 走 /api/render 按需
    out = {"ok": True, "mode": "answer", "ast": ast, "nl": nl,
           "summary": {k: v for k, v in s.items() if k != "full"}}
    if extra:
        out.update(extra)
    return out


def _followup_or_answer(ast, result, nl, key):
    """共用闸门：有 framing gap → 追问卡；否则直接结构化分析。
    （framing 只动节点定义、不动因果结构，所以清零后不再让 LLM 重审边——见对话纪要。）"""
    fvars = _framing_vars(result)
    if fvars:
        fu = build_framing_followup(nl, fvars, key)
        return {"ok": True, "mode": "followup", "followup": fu, "ast": ast, "nl": nl,
                "framing_vars": fvars}
    return _answer(ast, nl)


@app.post("/api/ask")
def ask(req: AskReq):
    """第一轮：中文问 → kernel_ast → run。有 framing 闸门 → 出追问卡（只问、不分析）。"""
    if not req.nl.strip():
        return {"ok": False, "error": "请输入一个问题"}
    try:
        from themis.web.llm_bridge import nl_to_kernel_ast, LLMBridgeError
    except Exception as e:
        return {"ok": False, "error": f"无法加载 LLM 桥接：{e}"}
    key = _resolve_key(req.api_key)
    try:
        ast = envelope = last = None
        for _ in range(3):
            try:
                a = nl_to_kernel_ast(req.nl, api_key=key)
                envelope = themis.run(a)
                ast = a
                break
            except Exception as e:
                last = e
        if ast is None:
            return {"ok": False,
                    "error": f"生成/校验因果图失败（已重试3次）：{type(last).__name__}: {str(last)[:180]}"}
        return _followup_or_answer(ast, envelope["results"][0], req.nl, key)
    except LLMBridgeError as e:
        return {"ok": False, "error": f"LLM 桥接：{e}", "need_key": "key" in str(e).lower()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class ClarifyReq(BaseModel):
    ast: dict
    picks: list[dict]   # [{"predicate": str, "fields": {...7字段...}}]
    nl: str | None = None


def _var_domain(ast, predicate):
    for s in ast.get("statements", []):
        if s.get("kind") == "variable" and s.get("predicate") == predicate:
            return s.get("domain")
    return None


@app.post("/api/clarify")
def clarify(req: ClarifyReq):
    """确定性 patch：把用户选的完整操作化写进对应变量 → apply_patch_and_run →
    若还有 framing 变量 → 继续出卡（循环）；清零 → 给分析。不调 LLM 做 patch。"""
    key = _resolve_key(None)
    patches = []
    for p in (req.picks or []):
        if not p.get("predicate"):
            continue
        f = _complete_fields(p.get("fields") or {})
        # 必须把 domain 也 patch 进去否则 gap 不清；变量没声明 domain 时默认布尔
        dom = _var_domain(req.ast, p["predicate"])
        f["domain"] = dom if dom is not None else [True, False]
        patches.append({"kind": "variable_patch", "predicate": p["predicate"], "fields": f})
    if not patches:
        return {"ok": False, "error": "没有可应用的澄清"}
    bundle = {"version": "0.1", "kind": "framing_skeleton_bundle", "patches": patches}
    try:
        out = themis.apply_patch_and_run(req.ast, [bundle])
        merged = out["merged_program"]
        return _followup_or_answer(merged, out["results"][0], req.nl, key)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class RenderReq(BaseModel):
    ast: dict
    nl: str | None = None


@app.post("/api/render")
def render(req: RenderReq):
    """按需生成 LLM 文字解读（慢，折叠里点了才调）。结构化结果已经秒出，这只是翻译层。"""
    try:
        from themis.web.llm_bridge import render_reply
    except Exception as e:
        return {"ok": False, "error": f"无法加载 LLM 桥接：{e}"}
    key = _resolve_key(None)
    try:
        envelope = themis.run(req.ast)
        reply = render_reply(envelope, nl=req.nl, api_key=key)
        return {"ok": True, "reply": reply}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


try:
    _VIS_JS = (Path(__file__).resolve().parent / "vendor" / "vis-network.min.js").read_text(encoding="utf-8")
except Exception:
    _VIS_JS = ""


@app.get("/vendor/vis-network.min.js")
def vis_network_js():
    return PlainTextResponse(_VIS_JS, media_type="application/javascript")


@app.get("/api/sample_csv", response_class=PlainTextResponse)
def sample_csv():
    return SAMPLE_CSV


@app.post("/api/estimate")
def estimate(req: EstimateReq):
    """专业用户：CSV → themis.estimate → 点估计 + CI + 敏感性，并对比未调整的粗相关。"""
    try:
        import pandas as pd
    except Exception as e:
        return {"ok": False, "error": f"pandas 不可用：{e}"}
    csv_text = req.csv_text if (req.csv_text and req.csv_text.strip()) else SAMPLE_CSV
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        return {"ok": False, "error": f"CSV 解析失败：{e}"}
    ast = SCEN_BY_ID.get(req.scenario_id, SCEN_BY_ID["biomed"])["ast"]
    # 校验列
    need = {"targeted_drug", "tumor_response", "disease_severity"}
    miss = need - set(df.columns)
    if miss:
        return {"ok": False, "error": f"CSV 缺少列：{sorted(miss)}（需要 {sorted(need)}）"}
    try:
        # 转 bool
        for c in need:
            df[c] = df[c].astype(bool)
        # 未调整的粗相关
        a = df[df.targeted_drug].tumor_response.mean()
        b = df[~df.targeted_drug].tumor_response.mean()
        naive = float(a - b)
        res = themis.estimate(ast, df)["results"][0]
        ne = res.get("numeric_estimate")
        if not ne:
            return {"ok": False, "error": "内核未返回数值估计（可能识别失败）"}
        return {"ok": True,
                "naive": round(naive, 4),
                "point": round(float(ne["point"]), 4),
                "ci_lower": round(float(ne["ci_lower"]), 4),
                "ci_upper": round(float(ne["ci_upper"]), 4),
                "ci_level": ne.get("ci_level"),
                "method": ne.get("method"),
                "adjustment": ne.get("adjustment"),
                "n": ne.get("sample_size"),
                "sensitivity": ne.get("sensitivity_analysis"),
                "assumption_ledger": (res.get("extensions") or {}).get("assumption_ledger"),
                "full": ne}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


# ============================================================ 前端
HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Themis · 现场体验</title>
<script src="/vendor/vis-network.min.js"></script>
<style>
:root{--navy:#1F4E96;--accent:#4472C4;--orange:#ED7D31;--green:#2E7D32;--ink:#262626;--gray:#595959;--tint:#EAF0F9;--tint2:#FBEEE4;--line:#dfe4ee}
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft YaHei","微软雅黑",Calibri,sans-serif;color:var(--ink);background:#f4f6fa}
header{background:linear-gradient(100deg,#1a2a52,#1F4E96 55%,#2f5fb0);color:#fff;padding:16px 30px}
header h1{margin:0;font-size:21px}header .sub{margin-top:3px;font-size:13px;color:#cdd9f0}
.banner{display:flex;gap:16px;flex-wrap:wrap;background:#102444;color:#fff;padding:9px 30px;font-size:12.5px}
.banner b{color:#FFD466}
.tabs{display:flex;gap:4px;padding:12px 30px 0;background:#fff;border-bottom:1px solid var(--line)}
.tab{padding:9px 18px;cursor:pointer;border:1px solid transparent;border-bottom:none;border-radius:9px 9px 0 0;font-size:14px;font-weight:600;color:var(--gray)}
.tab:hover{background:var(--tint)}
.tab.active{color:var(--navy);background:var(--tint);border-color:var(--line)}
.wrap{padding:20px 30px;max-width:1240px;margin:0 auto}
.pane{display:none}.pane.active{display:block}
.panel{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:0 2px 10px rgba(120,140,175,.08);margin-bottom:16px}
.panel h2{margin:0 0 12px;font-size:15px;color:var(--navy);border-left:4px solid var(--accent);padding-left:9px}
.row{display:grid;grid-template-columns:360px 1fr;gap:16px}
.scn{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:9px;cursor:pointer;transition:.15s}
.scn:hover{border-color:var(--accent);background:var(--tint)}
.scn.active{border-color:var(--navy);background:var(--tint);box-shadow:0 0 0 2px rgba(68,114,196,.18)}
.scn .tag{display:inline-block;font-size:11px;color:#fff;background:var(--accent);border-radius:20px;padding:1px 9px;margin-bottom:5px}
.scn .q{font-size:13.5px;font-weight:600;line-height:1.35}.scn .note{font-size:12px;color:var(--gray);margin-top:4px}
input[type=text],textarea{width:100%;border:1px solid var(--line);border-radius:8px;padding:9px;font-size:14px;font-family:inherit}
textarea.code{font-family:Consolas,monospace;font-size:12px;height:240px}
.btn{background:var(--navy);color:#fff;border:0;border-radius:9px;padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer}
.btn:hover{background:#163d77}.btn.sec{background:var(--accent)}.btn.ghost{background:#eef2f8;color:var(--navy)}
.badge{display:inline-block;color:#fff;border-radius:20px;padding:3px 13px;font-size:13px;font-weight:600}
.kpt{background:var(--tint);border:1px solid var(--accent);border-radius:10px;padding:11px 13px;margin:11px 0;font-size:14px;line-height:1.5}
.formula{font-family:"Cambria Math",Consolas,serif;background:#0e1c33;color:#dbe7ff;border-radius:8px;padding:12px 14px;font-size:15px;overflow-x:auto}
.gap{display:flex;gap:9px;align-items:flex-start;padding:7px 0;border-bottom:1px dashed var(--line)}
.dot{flex:0 0 auto;width:9px;height:9px;border-radius:50%;margin-top:6px}
.gap .gl{font-size:13.5px;font-weight:600}.gap .gd{font-size:12px;color:var(--gray);line-height:1.4}
.sev{font-size:11px;border-radius:4px;padding:0 6px;color:#fff;margin-left:6px}
details{margin-top:10px;border:1px solid var(--line);border-radius:8px;padding:8px 12px}
summary{cursor:pointer;font-size:13px;color:var(--navy);font-weight:600}
pre{background:#0e1c33;color:#bcd0f0;border-radius:8px;padding:12px;overflow:auto;font-size:12px;max-height:320px;white-space:pre-wrap}
.muted{color:var(--gray);font-size:13px}.h3{font-size:14px;color:var(--navy);margin:16px 0 7px;font-weight:700}
.placeholder{color:#9aa6b8;text-align:center;padding:50px 0;font-size:15px}
.reply{background:#f7faff;border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-size:14.5px;line-height:1.7;white-space:pre-wrap}
.dagbox{background:#f6f9ff;border:1px solid var(--accent);border-radius:10px;padding:11px 14px;margin:8px 0 12px}
.chip{display:inline-block;background:#fff;border:1px solid var(--accent);color:var(--navy);border-radius:14px;padding:1px 10px;font-size:13px;margin:2px 3px;font-weight:600}
.edge{display:inline-block;background:#fff;border:1px solid var(--line);border-radius:7px;padding:2px 9px;font-size:13px;margin:2px 4px}
.tagsm{background:var(--orange);color:#fff;border-radius:4px;padding:0 5px;font-size:10.5px;margin-left:3px}
.signoff{border:1px solid var(--orange);background:#fff7f0;border-radius:10px;padding:11px 13px;margin:0 0 12px}
.so-head{font-size:13.5px;color:#b5510f;font-weight:700;margin-bottom:7px}
.so-row{display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px dashed #f0d9c6}
.so-row:last-of-type{border-bottom:none}
.so-del{color:#C0504D;cursor:pointer;font-size:12.5px;font-weight:600;margin-left:auto;white-space:nowrap}
.so-del:hover{color:#fff;background:#C0504D;border-radius:5px;padding:1px 7px}
.addedge select{font-size:12.5px;padding:2px 6px;border:1px solid var(--accent);border-radius:5px;background:#fff;color:#1a1a1a}
.netbox{height:380px;border:1px solid var(--accent);border-radius:10px;background:#fbfdff;margin:0 0 6px}
.netlegend{font-size:12px;color:var(--gray);margin:0 0 8px;line-height:1.7}
.netlegend .dot-o{color:#ED7D31;font-weight:700}.netlegend .dot-g{color:#2E7D32;font-weight:700}.netlegend .dot-b{color:#4472C4;font-weight:700}
.nettools{margin:0 0 12px}
.vis-network:focus{outline:none}
.qry{font-family:Consolas,monospace;font-size:13px;color:var(--navy);background:#fff;border:1px solid var(--line);border-radius:6px;padding:2px 8px}
.xdel{color:#C0504D;cursor:pointer;font-weight:700;margin-left:7px;font-size:12px}
.xdel:hover{color:#fff;background:#C0504D;border-radius:4px;padding:0 4px}
.btn.mini{padding:5px 13px;font-size:12.5px}
.fq{border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin:9px 0;background:#fafcff}
.fq-q{font-size:14px;font-weight:600;color:var(--navy);margin-bottom:7px}
.opt{display:inline-block;border:1px solid var(--accent);color:var(--navy);background:#fff;border-radius:16px;padding:3px 12px;font-size:13px;margin:3px 5px 5px 0;cursor:pointer}
.opt:hover{background:var(--tint)}
.opt.sel{background:var(--navy);color:#fff;border-color:var(--navy)}
.optrow{margin:2px 0 1px}
.dim-tg{color:var(--gray);font-size:12px;margin-left:7px;cursor:pointer;user-select:none}
.dim-tg:hover{color:var(--navy);text-decoration:underline}
.dimbox{margin:4px 0 9px 4px;padding:8px 11px;background:#fff;border:1px dashed var(--line);border-radius:8px;font-size:12.5px;line-height:1.9;color:#333}
.dimbox b{color:var(--navy);font-weight:600;display:inline-block;min-width:76px;vertical-align:middle}
.dimline{margin:3px 0}
.dim-in{font-size:12.5px;padding:2px 7px;border:1px solid var(--accent);border-radius:5px;color:#1a1a1a;background:#fff;min-width:170px;vertical-align:middle}
.dim-in:focus{outline:none;border-color:var(--navy);box-shadow:0 0 0 2px rgba(31,78,150,.12)}
.fq-write{font-size:13px;margin-top:3px}
.cmp{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0}
.cmp .box{flex:1;min-width:200px;border-radius:10px;padding:14px;text-align:center}
.cmp .big{font-size:30px;font-weight:800;margin:4px 0}
.cmp .lab{font-size:13px}
.keyrow{display:flex;gap:8px;align-items:center;margin-top:8px}
.keyrow input{flex:1}
</style></head><body>
<header><h1>Themis · 现场体验</h1>
<div class="sub">给大模型的因果推理内核 —— 从普通用户提问，到专业用户带数据出真数字。后端全程跑真实 themis。</div></header>
<div class="banner"><span>🔒 内核 <b>不调用 LLM</b></span><span>🚫 <b>不编数字</b>：缺数据就说缺数据</span>
<span>🔍 给 <b>识别公式 + 缺口诊断</b></span><span>📊 有数据 → <b>真点估计 + 置信区间</b></span><span>✅ 输出 JSON，可独立复核</span></div>
<div class="tabs">
  <div class="tab active" data-t="ask">① 问问题（普通用户）</div>
  <div class="tab" data-t="scn">② 选场景（零配置）</div>
  <div class="tab" data-t="pro">③ 专业：数据 → 真数字</div>
</div>
<div class="wrap">

  <!-- ① 问问题 -->
  <div class="pane active" id="pane-ask">
    <div class="panel">
      <h2>用大白话问一个因果问题</h2>
      <p class="muted">中文随便问，比如“我每天跑步，肚子上的肉会瘦下来吗”。系统会把它翻成因果图、跑内核、再用中文如实回答（缺数据就直说，不编）。</p>
      <input type="text" id="ask-nl" placeholder='中文问题，例如：多吃蔬菜真的能降血压吗？'>
      <div class="keyrow">
        <button class="btn" id="ask-btn">问 Themis</button>
        <span class="muted">直接问即可 —— LLM 走本机 Max 代理，无需 API key。</span>
      </div>
    </div>
    <div class="panel" id="ask-res"><div class="placeholder">↑ 输入问题，点“问 Themis”</div></div>
  </div>

  <!-- ② 选场景 -->
  <div class="pane" id="pane-scn">
    <div class="row">
      <div class="panel"><h2>选一个因果问题</h2><div id="scnlist"></div>
        <button class="btn" id="scn-run" style="width:100%;margin-top:4px">▶ 运行 Themis</button></div>
      <div class="panel" id="scn-res"><div class="placeholder">← 选一个问题，点运行</div></div>
    </div>
  </div>

  <!-- ③ 专业 -->
  <div class="pane" id="pane-pro">
    <div class="panel">
      <h2>专业用户：带数据，出真数字</h2>
      <p class="muted">用“靶向药 → 肿瘤反应（疾病严重程度是混杂）”这个例子。上传你的 CSV，或用内置示例数据。
      Themis 会对混杂做<b>后门调整</b>，给出<b>点估计 + 置信区间 + 敏感性分析</b>——数字来自数据，不是编的。</p>
      <p class="muted">CSV 需要三列：<code>targeted_drug, tumor_response, disease_severity</code>（0/1 或 true/false）。</p>
      <div class="keyrow">
        <button class="btn" id="pro-sample">▶ 用内置示例数据跑</button>
        <button class="btn ghost" id="pro-dl">下载示例 CSV</button>
        <label class="btn ghost" style="cursor:pointer">上传 CSV<input type="file" id="pro-file" accept=".csv" style="display:none"></label>
        <span class="muted" id="pro-fname"></span>
      </div>
    </div>
    <div class="panel" id="pro-res"><div class="placeholder">↑ 点“用内置示例数据跑”立即看效果</div></div>
  </div>

</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
// 最后一审 = 显式签收：把结论依赖的 LLM 提议边拎到最顶，逐条可撤（撤→当场重算）
function renderAssumptionSignoff(dag){
  if(!dag) return '';
  const me=dag.query_edge;
  const isMain=(e)=>!!(me&&e.from===me.from&&e.to===me.to);
  const llm=[];
  // 查询主边(你问的关系本身)即使标 llm 也不算"假设"，不进签收
  (dag.edges||[]).forEach((e,i)=>{ if((e.source||'').toLowerCase().includes('llm')&&!isMain(e)) llm.push({e,i}); });
  if(!llm.length){
    return `<div class="kpt" style="border-color:var(--green);background:#e7f3e9">✅ 本结论不依赖任何 LLM 提议的假设 —— 因果边都是你/场景显式给定的。</div>`;
  }
  let h=`<div class="signoff"><div class="so-head">⚠ 本结论建立在这些 LLM 提议的假设上（非已确认事实，请逐条签收）</div>`;
  llm.forEach(({e,i})=>{
    h+=`<div class="so-row"><span class="qry">${esc(e.from)} → ${esc(e.to)}</span>`+
       `<span class="tagsm">LLM 假设</span>`+
       `<span class="so-del" onclick="delEdge(${i})">✕ 撤掉并重算</span></div>`;
  });
  h+=`<div class="muted" style="margin-top:6px">撤任意一条 → 内核当场重算结论；留着 = 你接受这条假设。</div></div>`;
  return h;
}
function renderDagEditable(dag,heading){
  if(!dag) return '';
  let h=`<div class="h3">${heading||'因果图 kernel_ast（可改：删一条边，看内核结果当场怎么变）'}</div><div class="dagbox">`;
  h+=`<div style="margin-bottom:6px"><b>变量：</b>`+(dag.variables||[]).map(v=>`<span class="chip">${esc(v)}</span>`).join('')+`</div>`;
  if((dag.edges||[]).length){h+=`<div style="margin-bottom:6px"><b>因果边：</b>`+
     dag.edges.map((e,i)=>`<span class="edge">${esc(e.from)} → ${esc(e.to)}${(e.source||'').toLowerCase().includes('llm')?'<span class="tagsm">LLM 假设</span>':(e.source||'').toLowerCase().includes('user')?'<span class="tagsm" style="background:var(--green)">你加的</span>':''}<span class="xdel" title="删掉这条边，看结果怎么变" onclick="delEdge(${i})">✕</span></span>`).join('')+`</div>`;}
  if(dag.query)h+=`<div><b>查询：</b><span class="qry">${esc(dag.query)}</span></div>`;
  const vopt=(dag.variables||[]).map(v=>`<option>${esc(v)}</option>`).join('');
  h+=`<div class="addedge" style="margin-top:9px"><b>＋ 加边：</b>`+
     `<select class="addfrom">${vopt}</select> <span style="color:var(--gray)">→</span> `+
     `<select class="addto">${vopt}</select> `+
     `<button class="btn sec mini" onclick="addEdge()">加并重算</button>`+
     `<span class="muted" style="margin-left:7px">在现有变量间加一条你认为成立的边（标“你加的”、不算 LLM 假设）。要加新变量走下面“高级改 JSON”。</span></div>`;
  h+=`<div style="margin-top:9px"><button class="btn ghost mini" onclick="restoreAst()">↺ 还原</button>`+
     `<span class="muted" style="margin-left:8px">点边上的 ✕ 删一条 → 内核当场重算（例：删掉混杂边，看后门调整公式塌成 P(y|x)）</span></div>`;
  h+=`<details style="margin-top:8px"><summary>高级：直接改 JSON 再跑</summary>`+
     `<textarea class="code advjson" spellcheck="false" style="height:170px">${esc(JSON.stringify((window.editCtx&&window.editCtx.ast)||{},null,2))}</textarea>`+
     `<button class="btn sec mini" style="margin-top:6px" onclick="runEditedJson()">重新运行</button></details>`;
  return h+`</div>`;
}
function renderVerdict(s,j){
  let h='';
  h+=`<div><span class="badge" style="background:${s.status_color}">${esc(s.status_label)}</span> <span class="muted">查询类型：${esc(s.query_kind||'-')}</span></div>`;
  h+=`<div class="kpt">${esc(s.status_blurb)}</div>`;
  if(s.formula)h+=`<div class="h3">识别公式（结构上怎么算）</div><div class="formula">${esc(s.formula)}</div>`;
  if(s.bounds)h+=`<div class="h3">区间界（${esc(s.bounds.method||'')}）</div><div class="muted">下界：${esc(s.bounds.lower)}<br>上界：${esc(s.bounds.upper)}</div>`;
  if(s.gaps&&s.gaps.length){h+=`<div class="h3">数据缺口诊断（要得到答案，还缺什么）</div>`;
    s.gaps.forEach(g=>h+=`<div class="gap"><div class="dot" style="background:${g.sev_color}"></div><div><div class="gl">${esc(g.label)}<span class="sev" style="background:${g.sev_color}">${esc(g.severity)}</span></div><div class="gd">${esc(g.desc)}</div></div></div>`);}
  if(j&&j.full_result)h+=`<details><summary>看完整审计输出（内核原始 JSON）</summary><pre>${esc(JSON.stringify(j.full_result,null,2))}</pre></details>`;
  return h;
}
// 把"可编辑 DAG + 判定"渲染进子容器；isEdit=true 保留 base 以便还原
// ===== 真·因果图（vis-network）：图上画边/加删节点 → 当场重跑 themis =====
window.GRAPHS=window.GRAPHS||{};
const VIS_LOCALE={zh:{edit:'编辑',del:'删除选中',back:'返回',addNode:'＋ 加变量',addEdge:'↗ 画边',editNode:'编辑变量',editEdge:'改连接',addDescription:'点画布空白处放一个新变量节点。',edgeDescription:'从一个变量按住拖到另一个变量，画一条因果边。',editEdgeDescription:'拖动端点改连接。',createEdgeError:'这条边不合法。',deleteClusterError:'无法删除。',editClusterError:'无法编辑。',close:'关闭'}};
function clone(o){return JSON.parse(JSON.stringify(o));}
function srcColor(s){s=(s||'').toLowerCase();return s.includes('llm')?'#ED7D31':s.includes('user')?'#2E7D32':'#4472C4';}
function dagToVis(dag){
  const me=dag.query_edge;
  const isMain=(e)=>!!(me&&e.from===me.from&&e.to===me.to);
  const nodes=(dag.variables||[]).map(v=>({id:v,label:v}));
  const edges=(dag.edges||[]).map((e,i)=>{
    const main=isMain(e);
    const c=main?'#4472C4':srcColor(e.source);   // 查询主边=中性蓝(问题本身,不是 LLM 假设)
    return {id:'e'+i,from:e.from,to:e.to,color:{color:c,highlight:c},width:main?3:2,dashes:main?false:(e.source||'').toLowerCase().includes('llm')};
  });
  return {nodes,edges};
}
function initGraph(ast,dag,gid,vid,base,cid){
  const cont=document.getElementById(gid); if(!cont)return;
  if(!window.vis){cont.innerHTML='<div class="placeholder">图库未加载（/vendor/vis-network.min.js）</div>';return;}
  const dv=dagToVis(dag);
  const nodes=new vis.DataSet(dv.nodes), edges=new vis.DataSet(dv.edges);
  const G={gid:gid,vid:vid,cid:cid,ast:clone(ast),base:base?clone(base):clone(ast),nodes:nodes,edges:edges,network:null};
  window.GRAPHS[gid]=G;
  const options={
    layout:{hierarchical:{enabled:true,direction:'UD',sortMethod:'directed',levelSeparation:95,nodeSpacing:150}},
    physics:false,
    nodes:{shape:'box',color:{background:'#EAF0F9',border:'#1F4E96'},borderWidth:1.5,margin:9,font:{face:'Microsoft YaHei',size:14,color:'#1F2A44'}},
    edges:{arrows:{to:{enabled:true,scaleFactor:0.85}},smooth:{type:'cubicBezier'}},
    interaction:{hover:true,selectConnectedEdges:false},
    locale:'zh',locales:VIS_LOCALE,
    manipulation:{enabled:true,initiallyActive:true,
      addNode:function(d,cb){cb(null);graphAddNode(gid);},
      addEdge:function(d,cb){cb(null);graphAddEdge(gid,d.from,d.to);},
      deleteNode:function(d,cb){cb(null);graphDelete(gid,d);},
      deleteEdge:function(d,cb){cb(null);graphDelete(gid,d);}}
  };
  G.network=new vis.Network(cont,{nodes:nodes,edges:edges},options);
}
async function graphApply(gid,newAst,errlabel){
  const G=window.GRAPHS[gid]; if(!G)return false;
  const j=await post('/api/run',{ast:newAst});
  if(!j.ok){alert(errlabel+'：'+j.error);return false;}
  G.ast=newAst;
  const dv=dagToVis(j.summary.dag);
  G.nodes.clear();G.nodes.add(dv.nodes);
  G.edges.clear();G.edges.add(dv.edges);
  const vbox=document.getElementById(G.vid);
  if(vbox)vbox.innerHTML=renderAssumptionSignoff(j.summary.dag)+renderVerdict(j.summary,{ok:true,summary:j.summary,ast:newAst});
  window.editCtx={cid:G.cid,ast:newAst,base:G.base};
  return true;
}
function graphAddNode(gid){
  const G=window.GRAPHS[gid]; if(!G)return;
  const name=(prompt('新变量名（snake_case，字母或下划线开头，如 age）')||'').trim();
  if(!name)return;
  if(!/^[A-Za-z_]\w*$/.test(name)){alert('变量名要 snake_case：字母或下划线开头，只含字母/数字/下划线');return;}
  if((G.ast.statements||[]).some(s=>s.kind==='variable'&&s.predicate===name)){alert('已经有这个变量了');return;}
  const a=clone(G.ast); a.statements.unshift({kind:'variable',predicate:name,domain:[true,false]});
  graphApply(gid,a,'加变量失败');
}
function graphAddEdge(gid,from,to){
  const G=window.GRAPHS[gid]; if(!G)return;
  if(!from||!to)return;
  if(from===to){alert('不能自环（变量指向自己）');return;}
  const a=clone(G.ast);
  if((a.statements||[]).some(s=>s.kind==='cause'&&(s.from||{}).predicate===from&&(s.to||{}).predicate===to)){alert('这条边已经在图里了');return;}
  const obj=astObject(a);
  const edge={kind:'cause',from:{predicate:from,args:[{type:'const',name:obj}]},to:{predicate:to,args:[{type:'const',name:obj}]},annotations:{source:'user'}};
  const qi=(a.statements||[]).findIndex(s=>s.kind==='query');
  if(qi<0)a.statements.push(edge);else a.statements.splice(qi,0,edge);
  graphApply(gid,a,'加边失败（可能成环——因果图不能有回路）');
}
function graphDelete(gid,sel){
  const G=window.GRAPHS[gid]; if(!G)return;
  const a=clone(G.ast);
  (sel.edges||[]).forEach(eid=>{const e=G.edges.get(eid);if(e)a.statements=a.statements.filter(s=>!(s.kind==='cause'&&(s.from||{}).predicate===e.from&&(s.to||{}).predicate===e.to));});
  (sel.nodes||[]).forEach(nid=>{a.statements=a.statements.filter(s=>!(s.kind==='variable'&&s.predicate===nid)&&!(s.kind==='cause'&&((s.from||{}).predicate===nid||(s.to||{}).predicate===nid)));});
  graphApply(gid,a,'删除失败（这个变量可能在查询里、删不得）');
}
function graphRestore(gid){const G=window.GRAPHS[gid];if(G)graphApply(gid,clone(G.base),'还原失败');}
function runEditedJsonGraph(gid){
  const ta=document.getElementById(gid+'-json'); if(!ta)return;
  let a; try{a=JSON.parse(ta.value);}catch(e){alert('JSON 解析失败：'+e.message);return;}
  graphApply(gid,a,'这份 JSON 内核跑不动');
}
// 渲染：真因果图 + 判定（签收/公式/缺口）。图改了走 graphApply 局部刷新；整块重渲走这里
function showResult(j,cid,isEdit){
  const box=document.querySelector(cid); if(!box)return;
  if(!j.ok){box.innerHTML=`<div class="kpt" style="border-color:#C0504D;background:#fbeee4">⚠ ${esc(j.error)}</div>`;return;}
  const base=(isEdit&&window.editCtx)?window.editCtx.base:j.ast;
  const gid=cid.replace('#','')+'-net', vid=cid.replace('#','')+'-verdict';
  box.innerHTML=
    `<div class="h3">因果图（图上「↗画边」拖一条、「＋加变量」放节点、选中「删除选中」 → 当场重跑 themis）</div>`+
    `<div class="netbox" id="${gid}"></div>`+
    `<div class="netlegend">边色：<span class="dot-o">━ LLM 假设</span>　<span class="dot-g">━ 你加的</span>　<span class="dot-b">━ 给定/原始</span></div>`+
    `<div class="nettools"><button class="btn ghost mini" onclick="graphRestore('${gid}')">↺ 还原初始图</button>`+
      ` <details style="display:inline-block;vertical-align:top;margin-left:6px"><summary>高级：直接改 JSON 再跑</summary>`+
      `<textarea id="${gid}-json" class="code advjson" spellcheck="false" style="height:170px">${esc(JSON.stringify(j.ast,null,2))}</textarea><br>`+
      `<button class="btn sec mini" style="margin-top:6px" onclick="runEditedJsonGraph('${gid}')">重新运行</button></details></div>`+
    `<div id="${vid}"></div>`;
  initGraph(j.ast,j.summary.dag,gid,vid,base,cid);
  const vbox=document.getElementById(vid);
  if(vbox)vbox.innerHTML=renderAssumptionSignoff(j.summary.dag)+renderVerdict(j.summary,j);
  window.editCtx={cid:cid,ast:j.ast,base:base};
}
async function post(url,body){return (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();}
async function editRerun(ast){
  const cid=window.editCtx.cid;
  document.querySelector(cid).innerHTML='<div class="placeholder">内核重算中…</div>';
  showResult(await post('/api/run',{ast:ast}),cid,true);
}
function delEdge(i){
  const ast=JSON.parse(JSON.stringify(window.editCtx.ast));
  let c=-1; ast.statements=ast.statements.filter(s=>{if(s.kind==='cause'){c++;return c!==i;}return true;});
  editRerun(ast);
}
function astObject(ast){
  const objs=((ast.domain||{}).objects)||[];
  if(objs[0]&&objs[0].name)return objs[0].name;
  for(const s of (ast.statements||[])){for(const k of ['from','to']){const a=s[k];if(a&&a.args&&a.args[0]&&a.args[0].name)return a.args[0].name;}}
  return 'patient';
}
function addEdge(){
  const cid=window.editCtx.cid;
  const from=document.querySelector(cid+' .addfrom').value;
  const to=document.querySelector(cid+' .addto').value;
  if(!from||!to)return;
  if(from===to){alert('不能加自环（变量指向自己）');return;}
  const ast=JSON.parse(JSON.stringify(window.editCtx.ast));
  const dup=(ast.statements||[]).some(s=>s.kind==='cause'&&(s.from||{}).predicate===from&&(s.to||{}).predicate===to);
  if(dup){alert('这条边已经在图里了');return;}
  const obj=astObject(ast);
  const edge={kind:'cause',from:{predicate:from,args:[{type:'const',name:obj}]},to:{predicate:to,args:[{type:'const',name:obj}]},annotations:{source:'user'}};
  const qi=(ast.statements||[]).findIndex(s=>s.kind==='query');
  if(qi<0)ast.statements.push(edge); else ast.statements.splice(qi,0,edge);
  editRerun(ast);
}
function restoreAst(){ if(window.editCtx) editRerun(JSON.parse(JSON.stringify(window.editCtx.base))); }
function runEditedJson(){ let a; const ta=document.querySelector(window.editCtx.cid+' .advjson');
  try{a=JSON.parse(ta.value);}catch(e){alert('JSON 解析失败：'+e.message);return;} editRerun(a); }
// tabs
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));t.classList.add('active');
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('active'));
  $('#pane-'+t.dataset.t).classList.add('active');
});

// ① ask（带 framing 追问闸门）
let askNl='';
$('#ask-btn').onclick=async()=>{
  const nl=$('#ask-nl').value.trim();if(!nl){alert('先输入问题');return;}
  askNl=nl;
  $('#ask-res').innerHTML='<div class="placeholder">分析中…（翻成因果图 → 跑内核 → 看是否需要先澄清）</div>';
  handleAsk(await post('/api/ask',{nl}));
};
function handleAsk(j){
  if(!j.ok){$('#ask-res').innerHTML=`<div class="kpt" style="border-color:#C0504D;background:#fbeee4">⚠ ${esc(j.error)}${j.need_key?'<br>（本机 Max 代理没在跑？）':''}</div>`;return;}
  if(j.nl) window.askAnswerNl=j.nl;
  if(j.mode==='followup'){renderFollowup(j.followup, j.ast);return;}
  // answer：结构化为主（跟②一致、秒出）+ 一句话结论 + 完整文字解读按需生成
  $('#ask-res').innerHTML=`<h2>内核判定结果</h2>`+
     `<div class="kpt">${esc(j.summary.status_blurb||'')}</div>`+
     `<div id="ask-kernel"></div>`+
     `<details style="margin-top:10px"><summary>看完整文字解读（LLM 翻译，较慢，点了才生成）</summary>`+
     `<div id="ask-prose"><button class="btn sec mini" onclick="loadProse()">生成文字解读</button></div></details>`;
  showResult({ok:true,summary:j.summary,ast:j.ast},'#ask-kernel',false);
}
async function loadProse(){
  $('#ask-prose').innerHTML='<div class="placeholder">生成中…（LLM，十几秒）</div>';
  const ast=(window.editCtx&&window.editCtx.ast)||window.askAnswerAst;
  const j=await post('/api/render',{ast:ast,nl:window.askAnswerNl});
  $('#ask-prose').innerHTML = j.ok ? `<div class="reply">${esc(j.reply)}</div>`
    : `<div class="kpt" style="border-color:#C0504D;background:#fbeee4">⚠ ${esc(j.error)}</div>`;
}
const DIM_LABELS={time_window:'时间窗',measurement:'测量方式',threshold:'阈值/切点',observability:'可观测性',direction:'方向',baseline:'基线',state_vs_event:'状态/事件'};
const DIM_ORDER=['time_window','measurement','threshold','direction','baseline','state_vs_event','observability'];
// schema 里这些 framing 字段全是自由字符串(非 enum)：gap 只看填没填、不校验取值。
// 所以不做下拉锁死，只把各字段 description 里明示的取值挂成 datalist 建议（可自由填别的）。
const DIM_HINTS={observability:['observable','self-reported','latent'],direction:['up','down','mixed'],state_vs_event:['state','event']};
function attr(v){return esc(v).replace(/"/g,'&quot;');}
function dimControl(k,v){
  v=v==null?'':String(v);
  const list=DIM_HINTS[k]?` list="dl-${k}"`:'';
  return `<input class="dim-in" data-field="${k}"${list} value="${attr(v)}">`;
}
function dimRows(f){
  f=f||{};
  return DIM_ORDER.filter(k=>f[k]!=null).map(k=>
    `<div class="dimline"><b>${DIM_LABELS[k]||k}</b>${dimControl(k,f[k])}</div>`).join('');
}
function renderFollowup(fu, ast){
  window.fuQuestions=fu.questions||[];
  window.followupAst=ast;
  const dls=Object.keys(DIM_HINTS).map(k=>`<datalist id="dl-${k}">`+
    DIM_HINTS[k].map(o=>`<option value="${attr(o)}"></option>`).join('')+`</datalist>`).join('');
  let h=dls+`<h2>需要先澄清（framing 闸门）</h2>`+
        `<div class="kpt">${esc(fu.intro||'')}</div>`;
  (fu.questions||[]).forEach((q,qi)=>{
    h+=`<div class="fq"><div class="fq-q">${qi+1}. ${esc(q.q)}</div>`+
       (q.options||[]).map((o,oi)=>
         `<div class="optrow">`+
           `<span class="opt" data-qi="${qi}" data-oi="${oi}" onclick="pickOpt(this)">${esc(o.label)}</span>`+
           `<span class="dim-tg" onclick="toggleDim(this)">▾ 维度</span>`+
           `<div class="dimbox" style="display:none">${dimRows(o.fields)}</div>`+
         `</div>`).join('')+
       `</div>`;
  });
  h+=`<button class="btn" onclick="submitClarify()" style="margin-top:6px">提交澄清，继续分析</button>`+
     `<span class="muted" style="margin-left:9px">选项是起点：点「▾维度」可展开，7 个维度都能直接改（预设里没有你要的组合就自己填）；确定性 patch → 清零才分析</span>`;
  $('#ask-res').innerHTML=h;
}
function pickOpt(el){
  el.closest('.fq').querySelectorAll('.opt').forEach(o=>o.classList.remove('sel'));
  el.classList.add('sel');
}
function toggleDim(el){
  const box=el.parentNode.querySelector('.dimbox'); if(!box)return;
  const open=box.style.display!=='none';
  box.style.display=open?'none':'block';
  el.textContent=open?'▾ 维度':'▴ 维度';
}
async function submitClarify(){
  const picks=[]; const fqs=document.querySelectorAll('.fq');
  for(let qi=0; qi<window.fuQuestions.length; qi++){
    const sel=fqs[qi]?fqs[qi].querySelector('.opt.sel'):null;
    if(!sel){alert('第 '+(qi+1)+' 题还没选一个定义');return;}
    // 从选中项的维度控件读当前值（用户改过就用改后的，没改就是预设）—— 解开"锁死预设组合"
    const row=sel.closest('.optrow'); const fields={};
    row.querySelectorAll('[data-field]').forEach(inp=>{fields[inp.dataset.field]=inp.value;});
    picks.push({predicate:window.fuQuestions[qi].predicate, fields:fields});
  }
  $('#ask-res').innerHTML='<div class="placeholder">应用澄清、内核重算中…（确定性 patch，秒级）</div>';
  handleAsk(await post('/api/clarify',{ast:window.followupAst, picks:picks, nl:window.askAnswerNl||''}));
}

// ② scenarios
let sel=null;
(async()=>{const sc=await (await fetch('/api/scenarios')).json();const box=$('#scnlist');
  sc.forEach((s,i)=>{const d=document.createElement('div');d.className='scn'+(i===0?' active':'');d.dataset.id=s.id;
    d.innerHTML=`<div class="tag">${esc(s.tag)}</div><div class="q">${esc(s.q)}</div>`+(s.note?`<div class="note">${esc(s.note)}</div>`:'');
    d.onclick=()=>{document.querySelectorAll('#scnlist .scn').forEach(e=>e.classList.remove('active'));d.classList.add('active');sel=s.id;};
    box.appendChild(d);});sel=sc[0].id;})();
$('#scn-run').onclick=async()=>{
  $('#scn-res').innerHTML='<h2>内核判定结果</h2><div id="scn-kernel"><div class="placeholder">运行中…</div></div>';
  showResult(await post('/api/run',{scenario_id:sel}),'#scn-kernel',false);};

// ④ pro
let uploadedCsv=null;
$('#pro-file').onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();
  r.onload=()=>{uploadedCsv=r.result;$('#pro-fname').textContent='已载入：'+f.name;};r.readAsText(f);};
$('#pro-dl').onclick=async()=>{const t=await (await fetch('/api/sample_csv')).text();
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'text/csv'}));a.download='示例数据_靶向药.csv';a.click();};
function renderLedger(ledger){
  if(!ledger||!ledger.assumptions)return '';
  // 专业页：展示这个"数字"依赖的估计假设（识别层 + 函数形式 + 参数）。
  // 结构边（含"查询主边"=你问的关系本身）不在这里 —— 那是 DAG / 签收面板的事。
  const items=ledger.assumptions.filter(e=>e.layer!=='structural_edge');
  if(!items.length)return '';
  const SEVCN={invalidating:'致命·假了结论作废',distorting:'扭曲·影响数值',confidence_only:'仅影响置信度'};
  const SEVC={invalidating:'#C0504D',distorting:'#ED7D31',confidence_only:'#888'};
  let h=`<div class="h3">这个数字依赖的假设（按致命程度排序 —— 是假设就该你审核）</div>`;
  items.forEach(e=>{const c=SEVC[e.severity]||'#888';
    h+=`<div class="gap"><div class="dot" style="background:${c}"></div><div>`+
       `<div class="gl">${esc(e.claim)}<span class="sev" style="background:${c}">${esc(SEVCN[e.severity]||e.severity)}</span></div>`+
       `<div class="gd">来源：${esc(e.provenance)}　${e.testable?'可检验（换设定/查数据验证）':'设计上不可证伪'}</div>`+
       `</div></div>`;});
  return h;
}
async function runEstimate(csv){$('#pro-res').innerHTML='<div class="placeholder">在数据上拟合中…</div>';
  const j=await post('/api/estimate',{csv_text:csv,scenario_id:'biomed'});
  if(!j.ok){$('#pro-res').innerHTML=`<div class="kpt" style="border-color:#C0504D;background:#fbeee4">⚠ ${esc(j.error)}</div>`;return;}
  const sv=j.sensitivity||{};
  let h=`<h2>估计结果（在你的数据上算出来的）</h2>`;
  h+=`<div class="cmp">
    <div class="box" style="background:#fbeee4;border:1px solid #ED7D31"><div class="lab">❌ 未调整的粗相关<br>（普通人直接对比会得到的）</div><div class="big" style="color:#ED7D31">${(j.naive*100).toFixed(1)}%</div><div class="muted">把混杂当因果，偏了</div></div>
    <div class="box" style="background:#e7f3e9;border:1px solid #2E7D32"><div class="lab">✅ Themis 后门调整估计<br>（对疾病严重程度做了调整）</div><div class="big" style="color:#2E7D32">${(j.point*100).toFixed(1)}%</div><div class="muted">95% CI：[${(j.ci_lower*100).toFixed(1)}%, ${(j.ci_upper*100).toFixed(1)}%]</div></div>
  </div>`;
  h+=`<div class="kpt">方法：<b>${esc(j.method)}</b>　调整变量：<b>${esc((j.adjustment||[]).join(', '))}</b>　样本量：<b>${esc(j.n)}</b><br>
     这个数字是从数据估计出来的、带置信区间、可被 <code>themis.verify</code> 独立复核——不是 LLM 编的。</div>`;
  h+=renderLedger(j.assumption_ledger);
  if(sv.e_value!=null)h+=`<div class="h3">敏感性分析</div><div class="muted">E-value = <b>${(+sv.e_value).toFixed(2)}</b>：要推翻这个结论，得存在一个与用药、疗效关联强度都达到该倍数的未测量混杂。${esc(sv.note||'')}</div>`;
  h+=`<details><summary>看完整数值估计 JSON</summary><pre>${esc(JSON.stringify(j.full,null,2))}</pre></details>`;
  $('#pro-res').innerHTML=h;}
$('#pro-sample').onclick=()=>runEstimate(null);
document.querySelector('label.btn input#pro-file').closest('label').addEventListener('dblclick',e=>e.preventDefault());
// 上传后自动跑
$('#pro-file').addEventListener('change',()=>{setTimeout(()=>{if(uploadedCsv)runEstimate(uploadedCsv);},200);});
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn, webbrowser, threading
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="warning")
