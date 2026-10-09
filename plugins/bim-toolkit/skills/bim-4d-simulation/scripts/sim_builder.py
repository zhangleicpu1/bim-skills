# -*- coding: utf-8 -*-
"""4D 施工模拟方案生成器

用法：
  python sim_builder.py --list
  python sim_builder.py --project 盾构隧道 --name "XX地铁区间" -o out [--goal L2] [--source "Primavera P6"]
  python sim_builder.py --input data.json -o out
  python sim_builder.py --template --name "4D模拟检查清单" -o out
  python sim_builder.py --project 教学楼 --json-only
"""
import argparse
import html as _html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

TODO = "〔待补充〕"
_PLACEHOLDER_RE = re.compile(r"〔待[^〕]*〕")

TASK_TYPE_META = {
    "Construct": ("建造", "ct-construct"),
    "Temporary": ("临时", "ct-temporary"),
    "Demolish": ("拆除", "ct-demolish"),
}

GOAL_KEYS = {"L1": 0, "L2": 1, "L3": 2}


# ----------------------------------------------------------------------
# 载入知识库
# ----------------------------------------------------------------------
def load_assets():
    kb = json.load(open(os.path.join(ASSETS, "simulation_kb.json"), encoding="utf-8"))
    std = json.load(open(os.path.join(ASSETS, "standards.json"), encoding="utf-8"))
    return kb, std


def _norm(s):
    """归一化：去空白、全角转半角、转小写。"""
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("\u3000", " ").replace(" ", "").replace("\t", "")
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x3000:
            out.append(" ")
        elif 0xFF01 <= o <= 0xFF5E:
            out.append(chr(o - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out).lower()


def resolve_project(kb, name):
    """三级匹配：精确键 → 精确别名 → 最长别名包含（单字别名不参与包含匹配）。

    单字别名不参与子串匹配，是为了避免「梁」这类单字把「桥梁支座」误命中——
    这一条是踩过坑之后加上的。
    """
    if not name:
        return None, None
    n = _norm(name)
    projects = kb.get("projects", {})
    for key, data in projects.items():
        if _norm(key) == n:
            return key, data
    for key, data in projects.items():
        for a in data.get("aliases", []):
            if _norm(a) == n:
                return key, data
    best = (0, None, None)
    for key, data in projects.items():
        for a in [key] + list(data.get("aliases", [])):
            na = _norm(a)
            if len(na) < 2:
                continue
            if na in n or n in na:
                if len(na) > best[0]:
                    best = (len(na), key, data)
    if best[1]:
        return best[1], best[2]
    return None, None


def resolve_goal(kb, goal):
    levels = kb.get("goal_levels", [])
    if not levels:
        return None
    if goal:
        g = _norm(goal).upper()
        if g in GOAL_KEYS and GOAL_KEYS[g] < len(levels):
            return levels[GOAL_KEYS[g]]
        for lv in levels:
            if _norm(goal) in _norm(lv["level"]) or _norm(lv["level"]) in _norm(goal):
                return lv
    return levels[1] if len(levels) > 1 else levels[0]


# ----------------------------------------------------------------------
# 文本工具
# ----------------------------------------------------------------------
def esc(s):
    return _html.escape(str(s if s is not None else ""), quote=True)


def todo_hl(s):
    """把占位符渲染成红色标记（〔待补充〕〔待确认〕等一律标红）。"""
    if s is None:
        return ""
    return _PLACEHOLDER_RE.sub(
        lambda m: '<span class="todo">%s</span>' % esc(m.group(0)), esc(s))


def _blocks_project(proj, name, goal, source, project_key, kb, std, unknown):
    """构造方案书的内容块。HTML 与 Markdown 共用。"""
    B = []
    P = B.append

    tt_count = {}
    for w in proj["wbs"]:
        tt_count[w["task_type"]] = tt_count.get(w["task_type"], 0) + 1

    # ---- 1 项目概况与模拟目标 ----
    P({"t": "h2", "text": "一、项目概况与模拟目标"})
    P({"t": "kv", "pairs": [
        ["项目名称", name],
        ["项目类型", "%s（%s）" % (project_key or "通用（未收录）", proj["category"])],
        ["模拟档位", "%s —— %s" % (goal["level"], goal["use"])],
        ["建议拆分粒度", goal["granularity"]],
        ["任务量参考", goal["typical_tasks"]],
        ["进度计划来源", source],
        ["模拟范围", "〔待确认〕——须与施工方确认本阶段纳入的专业与区域"],
        ["不在范围内", "〔待确认〕——须明确列出本次不做的工作，避免范围蔓延"],
    ]})
    P({"t": "note", "kind": "info", "text": "★以下是整个模拟的第一句话，必须先写下来：**这次模拟要帮项目团队做什么决定？** 用于投标演示、月度计划协调、周计划与机械路径校核，三者需要的拆分深度差一个数量级。目标不清会导致建模团队无限补细节，而计划团队仍只提供一张粗颗粒度横道图。"})
    P({"t": "p", "text": proj["intro"]})
    P({"t": "note", "kind": "ok", "text": "档位说明：%s 建议粒度为「%s」，典型任务量 %s。%s" % (goal["level"], goal["granularity"], goal["typical_tasks"], goal["note"])})

    # ---- 2 施工段划分依据 ----
    P({"t": "h2", "text": "二、施工段划分依据"})
    seg = proj["segment_basis"]
    P({"t": "kv", "pairs": [
        ["主要依据", seg["primary"]],
        ["具体做法", seg["detail"]],
    ]})
    P({"t": "note", "kind": "warn", "text": "**为什么这样划分**：" + seg["why"]})
    if proj.get("pitfalls"):
        P({"t": "h3", "text": "本类型专属陷阱"})
        P({"t": "list", "items": proj["pitfalls"], "kind": "warn"})

    # ---- 3 任务分解表 ----
    P({"t": "h2", "text": "三、任务分解表（WBS）"})
    P({"t": "p", "text": "任务类型对应 Navisworks TimeLiner 的三种内置任务类型：**Construct（建造）**、**Temporary（临时）**、**Demolish（拆除）**。临时设施必须使用 Temporary 或 Demolish，否则它们会永远留在画面里——这是「模拟做成了动画片」的根源。"})
    P({"t": "chips", "items": [
        {"label": "建造 Construct", "value": tt_count.get("Construct", 0), "cls": "ct-construct"},
        {"label": "临时 Temporary", "value": tt_count.get("Temporary", 0), "cls": "ct-temporary"},
        {"label": "拆除 Demolish", "value": tt_count.get("Demolish", 0), "cls": "ct-demolish"},
    ]})
    rows = []
    for w in proj["wbs"]:
        label, cls = TASK_TYPE_META.get(w["task_type"], (w["task_type"], ""))
        task_cell = '<b>%s</b>' % esc(w["task"])
        if w.get("note"):
            task_cell += '<div class="sub">%s</div>' % todo_hl(w["note"])
        rows.append([
            esc(w["code"]),
            task_cell,
            '<span class="chip %s">%s</span>' % (cls, esc(label)),
            todo_hl(w["dur"]),
            esc(w["pred"]),
            esc(w["owner"]),
            todo_hl(w["model_filter"]),
        ])
    P({"t": "table", "head": ["编码", "任务名称 / 要点", "类型", "工期", "前置", "责任班组", "模型挂接过滤器"],
       "rows": rows, "cls": "wbs", "widths": ["5%", "34%", "7%", "11%", "6%", "9%", "28%"]})
    P({"t": "note", "kind": "warn", "text": "★表中断言「★」标记的行为本类型最容易出错的环节，务必逐条核对。「工期」列为建议值或取值方式，必须结合本项目施工组织设计确认后替换为实际工期。"})

    # ---- 4 进度关联方法 ----
    P({"t": "h2", "text": "四、进度计划与模型的关联方法"})
    lk = proj["linkage"]
    P({"t": "kv", "pairs": [
        ["关联策略", lk["strategy"]],
        ["命名规则", lk["naming"]],
        ["主键与 Activity ID", lk["activity_id"]],
    ]})
    P({"t": "h3", "text": "四种关联方式对比"})
    P({"t": "table", "head": ["关联方式", "做法", "优点", "局限", "适用场景", "可维护性"],
       "rows": [[m["method"], m["how"], m["pros"], m["cons"], m["fit"], m["stability"]]
                for m in std["linkage_methods"]], "cls": "norm"})
    P({"t": "note", "kind": "warn", "text": "★**优先用「搜索集」而不是「选择集」**。搜索集是按条件动态生成的，模型更新后仍有效；选择集是静态快照，模型一改就失效，第二版更新时无法说明哪些构件被漏挂。"})
    P({"t": "h3", "text": "颗粒度匹配规则"})
    gr = std["granularity_rule"]
    P({"t": "table", "head": ["情形", "判断", "原因", "处理方式"],
       "rows": [
           [gr["case_bim_finer"]["condition"], gr["case_bim_finer"]["verdict"], gr["case_bim_finer"]["why"], gr["case_bim_finer"]["action"]],
           [gr["case_plan_finer"]["condition"], gr["case_plan_finer"]["verdict"], gr["case_plan_finer"]["why"], gr["case_plan_finer"]["action"]],
       ], "cls": "norm"})
    P({"t": "note", "kind": "info", "text": "经验规则：" + gr["rule_of_thumb"]})

    # ---- 5 TimeLiner 操作步骤 ----
    P({"t": "h2", "text": "五、Navisworks TimeLiner 操作步骤"})
    P({"t": "p", "text": "以下步骤按「准备 → 导入 → 关联 → 配置 → 模拟 → 校核 → 导出」的顺序组织。前四个阶段决定了模拟能不能做准，后三个阶段决定了模拟有没有价值——很多项目只做了后三个阶段，把 4D 当成了动画制作。"})
    for stage in std["timeliner_steps"]:
        P({"t": "h3", "text": stage["phase"]})
        P({"t": "p", "text": "**目标**：" + stage["goal"]})
        P({"t": "steps", "items": [
            {"n": s["step"], "title": s["action"], "detail": s["detail"], "note": s.get("note", "")}
            for s in stage["items"]
        ]})

    # ---- 6 动画输出设置 ----
    P({"t": "h2", "text": "六、模拟动画输出设置"})
    P({"t": "note", "kind": "info", "text": "依据：" + std["export_settings"]["official_reference"]})
    P({"t": "table", "head": ["设置项", "推荐值", "说明"],
       "rows": [[r["item"], esc(r["value"]), todo_hl(r["note"])] for r in std["export_settings"]["recommended"]],
       "cls": "norm", "widths": ["22%", "30%", "48%"]})
    P({"t": "h3", "text": "按用途的动画预设"})
    P({"t": "table", "head": ["用途", "档位", "镜头", "间隔", "时长", "帧率"],
       "rows": [[a["use"], a["goal_level"], a["camera"], a["interval"], a["duration"], a["fps"]]
                for a in std["animation_presets"]], "cls": "norm"})
    P({"t": "h3", "text": "交付格式建议"})
    P({"t": "table", "head": ["用途", "格式", "分辨率", "帧率", "说明"],
       "rows": [[d["use"], d["format"], d["resolution"], d["fps"], d["note"]] for d in std["export_settings"]["delivery_formats"]],
       "cls": "norm"})
    P({"t": "h3", "text": "导出常见故障排查"})
    P({"t": "table", "head": ["现象", "可能原因", "处理办法"],
       "rows": [[t["symptom"], t["cause"], t["fix"]] for t in std["export_settings"]["troubleshooting"]],
       "cls": "norm"})
    P({"t": "note", "kind": "warn", "text": "★" + std["export_settings"]["nwd_delivery_note"]})

    # ---- 6.5 项目日历核对 ----
    P({"t": "h2", "text": "七、项目日历核对（容易被忽略的一步）"})
    cal = std["calendar_checks"]
    P({"t": "p", "text": cal["why"]})
    P({"t": "note", "kind": "warn", "text": "**典型症状**：" + cal["symptom"]})
    P({"t": "table", "head": ["核对项", "要问的问题", "说明"],
       "rows": [[c["item"], c["question"], c["note"]] for c in cal["four_checks"]], "cls": "norm"})
    P({"t": "h3", "text": "校核顺序（用样板任务先验）"})
    P({"t": "list", "items": cal["verify_order"], "ordered": True})

    # ---- 7 风险预警清单 ----
    P({"t": "h2", "text": "八、风险预警清单"})
    P({"t": "h3", "text": "本项目专属风险"})
    P({"t": "table", "head": ["风险", "为什么会出错", "怎么查"],
       "rows": [["<b>%s</b>" % esc(r["risk"]), esc(r["why"]), esc(r["check"])] for r in proj["risks"]],
       "cls": "risk", "widths": ["22%", "46%", "32%"]})
    P({"t": "h3", "text": "4D 模拟通用风险（跨项目类型）"})
    P({"t": "table", "head": ["风险", "为什么会出错", "怎么查"],
       "rows": [["<b>%s</b>" % esc(r["risk"]), esc(r["why"]), esc(r["check"])] for r in kb["generic_fallback"]["risks"]],
       "cls": "risk", "widths": ["22%", "46%", "32%"]})
    P({"t": "h3", "text": "按阶段的风险雷达"})
    P({"t": "table", "head": ["阶段", "风险", "预警信号", "应对"],
       "rows": [[r["stage"], r["risk"], r["signal"], r["action"]] for r in std["risk_radar"]], "cls": "norm"})

    # ---- 8 检查清单 ----
    P({"t": "h2", "text": "九、4D 模拟检查清单"})
    P({"t": "p", "text": "共 %d 节 %d 项。完整可勾选版本另存为 Markdown 文件，可直接打印使用。" % (
        len(std["checklist"]["sections"]), sum(len(s["items"]) for s in std["checklist"]["sections"]))})
    for sec in std["checklist"]["sections"]:
        P({"t": "h3", "text": sec["title"]})
        P({"t": "checks", "items": sec["items"]})

    # ---- 9 交付物 ----
    P({"t": "h2", "text": "十、交付物清单"})
    P({"t": "table", "head": ["交付物", "格式", "说明"],
       "rows": [[d["item"], d["format"], esc(d["note"])] for d in std["deliverables"]], "cls": "norm"})
    P({"t": "note", "kind": "warn", "text": "★关于标准的说明：4D 施工模拟的直接依据是 **GB/T 51235-2017《建筑信息模型施工应用标准》**（第 6 章施工模拟、第 8 章进度管理）。但请注意，Navisworks 的三种任务类型（Construct / Demolish / Temporary）与各类关联规则**是软件功能，不是标准条文**，交付文件中应把两者分开表述，不要把软件操作说成规范要求。"})

    return B


# ----------------------------------------------------------------------
# HTML 渲染
# ----------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 64px;background:#f5f6f8;color:#1a1d21;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
 font-size:14px;line-height:1.75;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto}
header{background:#fff;border:1px solid #e3e6eb;border-radius:14px;padding:28px 32px;margin-bottom:20px}
header .eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#0f6fff;font-weight:700;margin-bottom:8px}
header h1{margin:0 0 6px;font-size:25px;line-height:1.35;letter-spacing:-.01em}
header .meta{color:#5c6470;font-size:13px}
header .meta b{color:#1a1d21;font-weight:600}
section{background:#fff;border:1px solid #e3e6eb;border-radius:14px;padding:24px 30px 28px;margin-bottom:18px}
h2{font-size:19px;margin:0 0 16px;padding-bottom:10px;border-bottom:2px solid #eef0f4;letter-spacing:-.01em}
h3{font-size:15px;margin:24px 0 10px;color:#0b3d91}
h3:first-child{margin-top:0}
p{margin:9px 0}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;table-layout:fixed}
th{background:#f2f4f8;text-align:left;padding:9px 10px;border:1px solid #e3e6eb;font-weight:600;color:#2c3340;vertical-align:top}
td{padding:9px 10px;border:1px solid #e6e9ee;vertical-align:top;word-break:break-word}
tbody tr:nth-child(even) td{background:#fafbfc}
td .sub{color:#6b7280;font-size:12px;margin-top:3px;line-height:1.6}
.align-r{text-align:right}
.kv{display:grid;grid-template-columns:150px 1fr;gap:0;border:1px solid #e3e6eb;border-radius:10px;overflow:hidden;margin:12px 0}
.kv .k{background:#f7f8fa;padding:10px 12px;font-weight:600;color:#2c3340;border-bottom:1px solid #eaedf1;font-size:13px}
.kv .v{padding:10px 12px;border-bottom:1px solid #eaedf1;font-size:13px}
.kv .k:last-of-type,.kv .v:last-of-type{border-bottom:none}
.note{border-left:4px solid #0f6fff;background:#f2f7ff;padding:11px 14px;border-radius:0 8px 8px 0;margin:12px 0;font-size:13px}
.note.warn{border-color:#d7000f;background:#fff5f5}
.note.ok{border-color:#00a651;background:#f2fbf6}
.note.info{border-color:#7a8290;background:#f7f8fa}
.note b{font-weight:700}
ul,ol{margin:10px 0;padding-left:22px}
li{margin:5px 0}
ul.warn li::marker{color:#d7000f}
.chip{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}
.ct-construct{background:#e8f1ff;color:#0b4fc4;border:1px solid #c3dbff}
.ct-temporary{background:#fff3e0;color:#a85b00;border:1px solid #ffdca8}
.ct-demolish{background:#ffeceb;color:#b0000c;border:1px solid #ffc9c5}
.counts{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.count{flex:1 1 150px;border:1px solid #e3e6eb;border-radius:10px;padding:11px 13px;background:#fbfcfd}
.count .num{font-size:21px;font-weight:700;line-height:1.2}
.count .lbl{font-size:12px;color:#5c6470;margin-top:2px}
.step{display:grid;grid-template-columns:52px 1fr;gap:12px;padding:11px 0;border-bottom:1px dashed #e8ebef}
.step:last-child{border-bottom:none}
.step .n{font-weight:700;color:#0f6fff;font-size:13px;padding-top:1px}
.step .t{font-weight:600;margin-bottom:3px}
.step .d{color:#3d444f;font-size:13px}
.step .nn{color:#b0000c;font-size:12.5px;margin-top:4px;line-height:1.6}
.todo{color:#d7000f;font-weight:700;background:#fff0ef;padding:0 4px;border-radius:3px}
.ck{list-style:none;padding-left:0;margin:10px 0}
.ck li{position:relative;padding-left:26px;margin:6px 0;font-size:13px}
.ck li::before{content:"";position:absolute;left:0;top:4px;width:13px;height:13px;border:1.5px solid #b6bcc6;border-radius:3px;background:#fff}
ul.warn{list-style:none;padding-left:0}
ul.warn li{padding-left:22px;position:relative}
ul.warn li::before{content:"▲";position:absolute;left:0;color:#d7000f;font-size:10px;top:3px}
footer{color:#8b919c;font-size:12px;text-align:center;padding:18px 0 0}
@media print{
 body{background:#fff;padding:0;font-size:11.5pt}
 section,header{border:none;border-radius:0;padding:0 0 12px;margin-bottom:14px;break-inside:auto}
 h2{break-after:avoid} table{break-inside:auto} tr{break-inside:avoid}
 .note{break-inside:avoid}
 header{border-bottom:2px solid #1a1d21;padding-bottom:14px}
}
"""


def render_html(blocks, title, subtitle, unknown_note=""):
    out = []
    A = out.append
    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    A("<title>%s</title>" % esc(title))
    A("<style>%s</style></head><body><div class='wrap'>" % CSS)
    A("<header><div class='eyebrow'>4D 施工模拟方案</div>")
    A("<h1>%s</h1>" % esc(title))
    A("<div class='meta'>%s</div></header>" % subtitle)
    if unknown_note:
        A("<section><div class='note warn'>%s</div></section>" % unknown_note)
    for b in blocks:
        t = b["t"]
        if t == "h2":
            A("<h2>%s</h2>" % esc(b["text"]))
        elif t == "h3":
            A("<h3>%s</h3>" % esc(b["text"]))
        elif t == "p":
            A("<p>%s</p>" % _inline(b["text"]))
        elif t == "kv":
            A("<div class='kv'>")
            for k, v in b["pairs"]:
                A("<div class='k'>%s</div><div class='v'>%s</div>" % (esc(k), todo_hl(v)))
            A("</div>")
        elif t == "table":
            A("<table class='%s'>" % b.get("cls", ""))
            if b.get("widths"):
                A("<colgroup>%s</colgroup>" % "".join("<col style='width:%s'>" % w for w in b["widths"]))
            A("<thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % esc(h) for h in b["head"]))
            for row in b["rows"]:
                A("<tr>%s</tr>" % "".join("<td>%s</td>" % _cell(c) for c in row))
            A("</tbody></table>")
        elif t == "list":
            tag = "ol" if b.get("ordered") else "ul"
            A("<%s class='%s'>" % (tag, b.get("kind", "")))
            for it in b["items"]:
                A("<li>%s</li>" % _inline(it))
            A("</%s>" % tag)
        elif t == "checks":
            A("<ul class='ck'>")
            for it in b["items"]:
                A("<li>%s</li>" % esc(it))
            A("</ul>")
        elif t == "note":
            A("<div class='note %s'>%s</div>" % (b.get("kind", ""), _inline(b["text"])))
        elif t == "chips":
            A("<div class='counts'>")
            for c in b["items"]:
                A("<div class='count'><div class='num %s'>%s</div><div class='lbl'>%s</div></div>"
                  % (c.get("cls", ""), esc(c["value"]), esc(c["label"])))
            A("</div>")
        elif t == "steps":
            for s in b["items"]:
                A("<div class='step'><div class='n'>%s</div><div>" % esc(s["n"]))
                A("<div class='t'>%s</div>" % _inline(s["title"]))
                A("<div class='d'>%s</div>" % _inline(s["detail"]))
                if s.get("note"):
                    A("<div class='nn'>%s</div>" % _inline(s["note"]))
                A("</div></div>")
    A("<footer>本方案由 4D 施工模拟助手生成 · 工序、工期与搭接关系须结合本项目施工组织设计确认后使用</footer>")
    A("</div></body></html>")
    return "\n".join(out)


def _inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = s.replace("\n", "<br>")
    return s


_TODO_TOKEN = "\x00TK"


def _highlight_html(s):
    """对「已含 HTML 标签」的字符串做占位符高亮，跳过已经高亮过的部分。

    上游若已用 todo_hl 处理过，这里不能再套一层，否则会产生嵌套 span
    （曾实际出现 10 处嵌套，是踩过的坑）。
    """
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return "%s%d\x00" % (_TODO_TOKEN, len(stash) - 1)

    s = re.sub(r'<span class="todo">[^<]*</span>', _stash, s)
    s = _PLACEHOLDER_RE.sub(
        lambda m: '<span class="todo">%s</span>' % esc(m.group(0)), s)
    return re.sub(re.escape(_TODO_TOKEN) + r"(\d+)\x00",
                  lambda m: stash[int(m.group(1))], s)


def _cell(c):
    """单元格：若已含标签（由上游拼好），不再转义；否则按纯文本转义。"""
    s = str(c)
    if "<b>" in s or "<span" in s or "<div" in s or "<br>" in s:
        return _highlight_html(s)
    return _inline(s)


# ----------------------------------------------------------------------
# Markdown 渲染
# ----------------------------------------------------------------------
def render_md(blocks, title, subtitle, unknown_note=""):
    out = []
    A = out.append
    A("# " + title)
    A("")
    A("> " + subtitle)
    A("")
    if unknown_note:
        A("> ⚠️ " + re.sub(r"<[^>]+>", "", unknown_note))
        A("")
    for b in blocks:
        t = b["t"]
        if t == "h2":
            A("## " + b["text"]); A("")
        elif t == "h3":
            A("### " + b["text"]); A("")
        elif t == "p":
            A(b["text"]); A("")
        elif t == "kv":
            for k, v in b["pairs"]:
                A("- **%s**：%s" % (k, str(v).replace("\n", " ")))
            A("")
        elif t == "table":
            A("| " + " | ".join(b["head"]) + " |")
            A("|" + "|".join([" --- "] * len(b["head"])) + "|")
            for row in b["rows"]:
                cells = [re.sub(r"<[^>]+>", "", str(c)).replace("|", "\\|").replace("\n", " ") for c in row]
                A("| " + " | ".join(cells) + " |")
            A("")
        elif t == "list":
            for i, it in enumerate(b["items"], 1):
                pre = ("%d. " % i) if b.get("ordered") else "- "
                A(pre + str(it))
            A("")
        elif t == "checks":
            for it in b["items"]:
                A("- [ ] " + str(it))
            A("")
        elif t == "note":
            A("> " + str(b["text"]).replace("\n", " "))
            A("")
        elif t == "chips":
            A(" · ".join("%s：%s" % (c["label"], c["value"]) for c in b["items"]))
            A("")
        elif t == "steps":
            for s in b["items"]:
                A("**%s %s**" % (s["n"], s["title"]))
                A("")
                A(str(s["detail"]))
                A("")
                if s.get("note"):
                    A("> " + str(s["note"]))
                    A("")
    A("---")
    A("")
    A("*本方案由 4D 施工模拟助手生成 · 工序、工期与搭接关系须结合本项目施工组织设计确认后使用*")
    return "\n".join(out)


def render_checklist_md(std, title, subtitle):
    out = []
    A = out.append
    A("# " + title + "（4D 施工模拟检查清单）")
    A("")
    A("> " + subtitle)
    A("")
    total = sum(len(s["items"]) for s in std["checklist"]["sections"])
    A("共 %d 节 %d 项。建议打印后逐项勾选，交付前完成自检。" % (len(std["checklist"]["sections"]), total))
    A("")
    for sec in std["checklist"]["sections"]:
        A("## " + sec["title"])
        A("")
        for it in sec["items"]:
            A("- [ ] " + it)
        A("")
    A("---")
    A("")
    A("**按阶段的风险雷达**")
    A("")
    A("| 阶段 | 风险 | 预警信号 | 应对 |")
    A("| --- | --- | --- | --- |")
    for r in std["risk_radar"]:
        A("| %s | %s | %s | %s |" % (r["stage"], r["risk"], r["signal"], r["action"]))
    A("")
    A("**标准依据**")
    A("")
    sb = std["standard_basis"]["primary"]
    A("- %s %s（%s）" % (sb["code"], sb["name"], sb["issued"]))
    for c in sb["chapters"]:
        A("  - " + c)
    A("- " + std["standard_basis"]["honest_note"])
    return "\n".join(out)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def build_from_project(kb, std, project_key, proj, name, goal, source):
    unknown = ""
    if proj is None:
        proj = kb["generic_fallback"]
        unknown = ("**该项目的 4D 模拟框架未收录在库。** 以下内容为通用骨架，可用于组织模拟工作，"
                   "但项目特有的<b>施工段划分依据、关键工序、时空约束</b>必须由使用者补充确认后再使用。"
                   "建议先与施工方确认现场按什么单元组织流水——这一步决定了后续所有关联能否成立。")
    blocks = _blocks_project(proj, name, goal, source, project_key, kb, std, unknown)
    subtitle = ("项目类型：%s ｜ 模拟档位：%s ｜ 进度来源：%s" % (
        project_key or "通用（未收录）", goal["level"], source))
    return blocks, subtitle, unknown


def build_from_input(kb, std, payload):
    project_key, proj = resolve_project(kb, payload.get("project_type", ""))
    name = payload.get("project_name") or "〔项目名称〕"
    goal = resolve_goal(kb, payload.get("goal_level", ""))
    source = payload.get("schedule_source") or "微软 Project / 甲方提供的进度计划"

    if proj is None:
        proj = dict(kb["generic_fallback"])
    else:
        proj = json.loads(json.dumps(proj))  # 深拷贝，避免污染知识库

    # 允许用输入数据覆盖/补充
    if payload.get("segment_basis"):
        proj["segment_basis"] = dict(proj["segment_basis"])
        proj["segment_basis"]["primary"] = payload["segment_basis"]
        if payload.get("segment_detail"):
            proj["segment_basis"]["detail"] = payload["segment_detail"]
        if payload.get("segment_why"):
            proj["segment_basis"]["why"] = payload["segment_why"]
    if payload.get("wbs"):
        proj["wbs"] = payload["wbs"]
    if payload.get("risks"):
        proj["risks"] = payload["risks"]
    if payload.get("pitfalls"):
        proj["pitfalls"] = payload["pitfalls"]
    if payload.get("linkage"):
        proj["linkage"] = {**proj["linkage"], **payload["linkage"]}
    if payload.get("temp_facilities"):
        proj["temp_facilities"] = payload["temp_facilities"]

    unknown = ""
    if project_key is None:
        unknown = ("**该项目的 4D 模拟框架未收录在库。** 以下内容为通用骨架 + 你提供的数据，"
                   "项目特有的施工段划分依据、关键工序与时空约束须补充确认后再使用。")
    blocks = _blocks_project(proj, name, goal, source, project_key, kb, std, unknown)
    subtitle = ("项目类型：%s ｜ 模拟档位：%s ｜ 进度来源：%s" % (
        project_key or "通用（未收录）", goal["level"], source))
    return blocks, subtitle, unknown


def write_outputs(blocks, subtitle, unknown, name, outdir):
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, name)
    title = "%s 4D 施工模拟方案" % name
    files = []

    hp = base + "_4D模拟方案.html"
    with open(hp, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_html(blocks, title, subtitle, unknown))
    files.append(hp)

    mp = base + "_4D模拟方案.md"
    with open(mp, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(blocks, title, subtitle, unknown))
    files.append(mp)

    return files


def write_checklist(std, name, outdir, subtitle="未收录项目类型 · 通用检查清单"):
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, name + "_4D模拟检查清单.md")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_checklist_md(std, name, subtitle))
    return p


def cmd_list(kb, std):
    print("4D 施工模拟知识库 · 支持的项目类型")
    print("=" * 74)
    for k, v in kb["projects"].items():
        tt = {w["task_type"] for w in v["wbs"]}
        mark = ""
        if {"Construct", "Demolish", "Temporary"} <= tt:
            mark = "✓三类型齐"
        else:
            mark = "缺:%s" % ",".join(sorted({"Construct", "Demolish", "Temporary"} - tt))
        print("  %-10s %-16s WBS %2d 条 | 风险 %d 条 | 临设 %d 项 | %s" % (
            k, v["category"], len(v["wbs"]), len(v["risks"]), len(v["temp_facilities"]), mark))
        print("     别名：%s" % "、".join(v.get("aliases", [])))
    print("-" * 74)
    print("  通用回退 generic_fallback：通用风险 %d 条（未收录项目类型自动使用）"
          % len(kb["generic_fallback"]["risks"]))
    print()
    print("模拟档位（--goal）：")
    for g in kb["goal_levels"]:
        print("  %-16s %-28s 粒度：%s" % (g["level"], g["use"], g["granularity"]))
    print()
    print("TimeLiner 操作步骤：%d 个阶段 / %d 步"
          % (len(std["timeliner_steps"]), sum(len(s["items"]) for s in std["timeliner_steps"])))
    print("检查清单：%d 节 / %d 项"
          % (len(std["checklist"]["sections"]), sum(len(s["items"]) for s in std["checklist"]["sections"])))
    print("风险雷达：%d 条 | 关联方法：%d 种 | 交付物：%d 项"
          % (len(std["risk_radar"]), len(std["linkage_methods"]), len(std["deliverables"])))


def main():
    ap = argparse.ArgumentParser(description="4D 施工模拟方案生成器")
    ap.add_argument("--list", action="store_true", help="列出知识库覆盖情况")
    ap.add_argument("--project", help="项目类型（铀矿巷道/地下综合管廊/教学楼/盾构隧道/基坑支护/双拼别墅/英雄纪念碑，支持别名）")
    ap.add_argument("--name", default="4D模拟", help="项目名称，用于标题与文件名")
    ap.add_argument("--goal", default="L2", help="模拟档位：L1 宏观演示 / L2 月度协调 / L3 周计划与机械路径")
    ap.add_argument("--source", default="微软 Project", help="进度计划来源（微软 Project / Primavera P6 / Excel CSV / Asta Powerproject）")
    ap.add_argument("--input", help="输入 JSON（自定义数据渲染成品）")
    ap.add_argument("--template", action="store_true", help="输出空白检查清单模板")
    ap.add_argument("--checklist-only", action="store_true", help="同时输出检查清单 Markdown")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--json-only", action="store_true", help="只打印 JSON 摘要")
    a = ap.parse_args()

    kb, std = load_assets()

    if a.list:
        cmd_list(kb, std)
        return 0

    if a.template:
        files = [write_checklist(std, a.name, a.outdir, "通用模板 · 适用任意项目类型")]
        # 空白模板也用通用回退生成一份骨架方案
        blocks, subtitle, unknown = build_from_project(
            kb, std, None, None, a.name, resolve_goal(kb, a.goal), a.source)
        files = write_outputs(blocks, subtitle, unknown, a.name, a.outdir) + files
        if a.json_only:
            print(json.dumps({"ok": True, "mode": "template", "files": files}, ensure_ascii=False))
        else:
            print("[模板] 已生成通用 4D 模拟方案骨架与空白检查清单")
            for f in files:
                print("   ", f)
        return 0

    if a.input:
        payload = json.load(open(a.input, encoding="utf-8"))
        blocks, subtitle, unknown = build_from_input(kb, std, payload)
        key, proj = resolve_project(kb, payload.get("project_type", ""))
        name = payload.get("project_name") or a.name
        goal = resolve_goal(kb, payload.get("goal_level", a.goal))
    else:
        if not a.project:
            ap.error("需要 --project 或 --input（或使用 --list / --template）")
        key, proj = resolve_project(kb, a.project)
        name = a.name
        goal = resolve_goal(kb, a.goal)
        blocks, subtitle, unknown = build_from_project(kb, std, key, proj, name, goal, a.source)

    files = write_outputs(blocks, subtitle, unknown, name, a.outdir)
    if a.checklist_only:
        files.append(write_checklist(std, name, a.outdir, subtitle))

    n_tables = sum(1 for b in blocks if b["t"] == "table")
    n_steps = sum(len(b["items"]) for b in blocks if b["t"] == "steps")
    n_checks = sum(len(b["items"]) for b in blocks if b["t"] == "checks")
    todos = sum(str(b).count(TODO) for b in blocks)

    summary = {
        "ok": True,
        "project": name,
        "project_type": key or "通用（未收录）",
        "in_library": key is not None,
        "goal_level": goal["level"],
        "schedule_source": a.source,
        "sections": sum(1 for b in blocks if b["t"] == "h2"),
        "tables": n_tables,
        "timeliner_steps": n_steps,
        "checklist_items": n_checks,
        "todos": todos,
        "files": files,
    }
    if a.json_only:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print("=" * 74)
    print("4D 施工模拟方案已生成")
    print("=" * 74)
    print("  项目名称  :", name)
    print("  项目类型  :", summary["project_type"], "" if key else "（未收录，已回退通用骨架）")
    print("  模拟档位  :", goal["level"], "—", goal["use"])
    print("  进度来源  :", a.source)
    print("  章节数    :", summary["sections"], "| 表格数:", n_tables)
    print("  TimeLiner :", n_steps, "步 | 检查清单:", n_checks, "项")
    if todos:
        print("  待补充项  :", todos, "处（渲染为红色标记，交付前须补全）")
    print("-" * 74)
    for f in files:
        print("   ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
