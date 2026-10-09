#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BIM 专项可视化方案书生成器。

读取 assets/visualization_kb.json，按「项目类型 + 专项内容」匹配方案，
输出：
    <名称>_<专项>_可视化方案.html     —— 自带真实色块的方案书（可直接打开/打印/发给团队）
    <名称>_<专项>_可视化检查清单.md   —— 可勾选的检查清单
并把结构化结论以 JSON 打印到 stdout。

用法：
    python build_scheme.py --project 铀矿工程 --topic 辐射防护分区
    python build_scheme.py --project 地下综合管廊 --topic 管线综合 -o ./out --name XX路管廊
    python build_scheme.py --list
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime

KB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "visualization_kb.json")

# 未收录专项时使用的通用分类色板（色盲友好、12 色以内）
GENERIC_PALETTE = [
    {"name": "类别 A", "hex": "#4472C4", "note": "按项目实际分类替换名称"},
    {"name": "类别 B", "hex": "#ED7D31", "note": ""},
    {"name": "类别 C", "hex": "#70AD47", "note": ""},
    {"name": "类别 D", "hex": "#FFC000", "note": ""},
    {"name": "类别 E", "hex": "#5B9BD5", "note": ""},
    {"name": "类别 F", "hex": "#A5A5A5", "note": ""},
    {"name": "类别 G", "hex": "#7B2D8E", "note": ""},
    {"name": "类别 H", "hex": "#C00000", "note": ""},
    {"name": "重点/异常", "hex": "#D7000F", "note": "用于标注不满足要求的区段"},
]

GENERIC_METHODS = [
    {"name": "分类分色三维轴测图", "how": "按专项分类在模型中分色，输出等轴测视图，整体呈现专项逻辑",
     "output": "专项轴测图，用于汇报"},
    {"name": "分层剖切平面图", "how": "用剖切面逐层剖切出图，避免多层信息叠加",
     "output": "分层平面图，用于报审"},
    {"name": "典型剖面图", "how": "在最不利或最典型位置做横剖，表达竖向关系与关键尺寸",
     "output": "典型剖面图，作为施工依据"},
    {"name": "专项指标校核图", "how": "把规范限值与实际数值对照标注，不满足处用警示色标出",
     "output": "指标校核图，直接回应审图要求"},
]


def load_kb(path: str = KB_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_name(text: str) -> str:
    return "".join("_" if c in '\\/:*?"<>|' else c for c in str(text)).strip() or "方案"


def match_topic(kb: dict, topic: str) -> tuple[str | None, dict | None]:
    """按专项名或别名匹配。"""
    topics = kb.get("topics", {})
    key = re.sub(r"\s+", "", topic or "")
    if not key:
        return None, None
    for name, data in topics.items():
        if key == name or key in [re.sub(r"\s+", "", a) for a in data.get("aka", [])]:
            return name, data
    for name, data in topics.items():
        if key in name or name in key:
            return name, data
        for a in data.get("aka", []):
            if key in a or a in key:
                return name, data
    return None, None


def find_combination(kb: dict, project: str, topic: str) -> dict:
    combos = kb.get("combinations", {})
    key = f"{project}|{topic}"
    if key in combos:
        return combos[key]
    for k, v in combos.items():
        p, _, t = k.partition("|")
        if t == topic and (p in project or project in p):
            return v
    return {}


def build_spec(kb: dict, project: str, topic: str) -> dict:
    defaults = kb.get("defaults", {})
    matched_name, topic_data = match_topic(kb, topic)
    topic_data = topic_data or {}
    project_data = kb.get("project_types", {}).get(project, {})
    combo = find_combination(kb, project, matched_name or topic)

    legend = dict(defaults.get("legend", {}))
    legend.update({k: v for k, v in (topic_data.get("legend") or {}).items() if v})

    drawing = dict(defaults.get("drawing", {}))
    drawing.update({k: v for k, v in (topic_data.get("drawing") or {}).items() if v})

    annotations = list(defaults.get("annotation", [])) + list(topic_data.get("annotation", []))

    checklist = [dict(x) for x in defaults.get("checklist_general", [])]
    checklist += [dict(x) for x in topic_data.get("checklist", [])]
    checklist += [dict(x) for x in combo.get("extra_checklist", [])]

    # 注意：知识库中显式给出空 palette 表示「该专项只用连续色阶」，
    # 与「专项未收录」是两种不同情况，必须区分，不能用真值判断。
    if "palette" in topic_data:
        palette = topic_data["palette"]
    elif matched_name:
        palette = []
    else:
        palette = list(GENERIC_PALETTE)

    if "methods" in topic_data:
        methods = topic_data["methods"]
    elif matched_name:
        methods = []
    else:
        methods = list(GENERIC_METHODS)

    view_steps = list(topic_data.get("view_focus", [])) + list(combo.get("extra_view_steps", []))
    if not view_steps:
        view_steps = ["按专项分类建立独立视图样板，避免与其他专业视图互相污染",
                      "用剖切面逐层剖切，避免多层信息叠加",
                      "关闭与专项无关的构件，提高图面可读性"]

    return {
        "project": project,
        "topic": matched_name or topic,
        "topic_matched": bool(matched_name),
        "domain": topic_data.get("domain") or project_data.get("domain", ""),
        "standard": topic_data.get("standard", ""),
        "authority": topic_data.get("authority", "行业惯例"),
        "authority_note": topic_data.get("authority_note", ""),
        "palette": palette,
        "gradient": topic_data.get("gradient"),
        "methods": methods,
        "legend": legend,
        "annotation": annotations,
        "drawing": drawing,
        "view_steps": view_steps,
        "checklist": checklist,
        "pitfalls": topic_data.get("pitfalls", []),
        "focus": combo.get("focus", ""),
        "project_traits": project_data.get("traits", ""),
        "project_notes": project_data.get("notes", []),
        "default_topics": project_data.get("default_topics", []),
    }


# ==========================================================================
# HTML 渲染
# ==========================================================================
CSS = """
:root{--ink:#1a2233;--sub:#5a6a82;--line:#dfe5ee;--accent:#2f6fb5;--bg:#f6f8fb;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",system-ui,sans-serif;
 font-size:14px;line-height:1.75}
.wrap{max-width:1080px;margin:0 auto;padding:32px 28px 64px}
header{background:linear-gradient(135deg,#2f6fb5,#1d4d85);color:#fff;border-radius:14px;
 padding:28px 30px;margin-bottom:24px}
header h1{margin:0 0 6px;font-size:26px;letter-spacing:.5px}
header .sub{opacity:.9;font-size:14px}
header .meta{margin-top:16px;display:flex;flex-wrap:wrap;gap:10px}
header .meta span{background:rgba(255,255,255,.16);border-radius:20px;padding:4px 14px;font-size:12.5px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:22px 26px;margin-bottom:18px}
h2{font-size:18px;margin:0 0 4px;padding-left:12px;border-left:4px solid var(--accent);line-height:1.2}
h2 .en{font-size:11px;color:var(--sub);font-weight:400;margin-left:8px;letter-spacing:.5px}
.hint{color:var(--sub);font-size:12.5px;margin:8px 0 16px}
h3{font-size:14.5px;margin:20px 0 8px;color:#22405f}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}
th{background:#eef3f9;text-align:left;padding:9px 12px;border:1px solid var(--line);
 font-weight:600;color:#22405f;white-space:nowrap}
td{padding:9px 12px;border:1px solid var(--line);vertical-align:top}
tr:nth-child(even) td{background:#fbfcfe}
.sw{display:inline-block;width:46px;height:22px;border-radius:5px;border:1px solid rgba(0,0,0,.14);
 vertical-align:middle}
.hex{font-family:Consolas,Menlo,monospace;font-size:12.5px;color:#3c4d63}
ul,ol{margin:8px 0;padding-left:22px}
li{margin:5px 0}
.tag{display:inline-block;font-size:11.5px;padding:2px 10px;border-radius:12px;
 background:#eaf2fb;color:#2f6fb5;border:1px solid #cfe0f3;margin-right:6px}
.tag.warn{background:#fdf0e8;color:#c05622;border-color:#f5d3bd}
.bar{height:34px;border-radius:6px;border:1px solid rgba(0,0,0,.12);margin:12px 0 4px}
.scale{display:flex;font-size:11.5px;color:var(--sub);margin-bottom:14px}
.scale div{flex:1;text-align:center}
.legend-mock{border:1.2px solid #8a99ad;border-radius:4px;padding:0;display:inline-block;
 min-width:280px;background:#fff;margin-top:6px}
.legend-mock .lt{background:#eef3f9;border-bottom:1.2px solid #8a99ad;padding:5px 12px;
 font-size:12.5px;font-weight:600;text-align:center;color:#22405f}
.legend-mock .lr{display:flex;align-items:center;gap:9px;padding:4px 12px;font-size:12px}
.legend-mock .lr .b{width:26px;height:12px;border:1px solid rgba(0,0,0,.18);border-radius:2px}
.chk{list-style:none;padding:0;margin:6px 0}
.chk li{display:flex;gap:10px;padding:8px 0;border-bottom:1px dashed #e8edf4;margin:0}
.chk li:last-child{border-bottom:none}
.chk .box{flex:0 0 15px;width:15px;height:15px;border:1.4px solid #9aa8bb;border-radius:3px;margin-top:4px}
.chk .t{font-weight:600}
.chk .d{color:var(--sub);font-size:12.5px}
.note{background:#f4f8fd;border-left:3px solid var(--accent);padding:10px 14px;border-radius:0 6px 6px 0;
 font-size:13px;margin:12px 0}
.warnbox{background:#fdf6f0;border-left:3px solid #d9822b;padding:10px 14px;border-radius:0 6px 6px 0;
 font-size:13px;margin:12px 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.grid2{grid-template-columns:1fr}}
footer{color:var(--sub);font-size:12px;text-align:center;padding:18px 0 0}
@media print{body{background:#fff}section{break-inside:avoid}}
"""


def esc(t) -> str:
    return html.escape("" if t is None else str(t))


def render_palette_table(palette: list) -> str:
    if not palette:
        return "<p class='hint'>该专项不使用离散分类色，请见下方连续色阶。</p>"
    rows = []
    for e in palette:
        rows.append(
            "<tr><td><b>{}</b></td><td><span class='sw' style='background:{}'></span></td>"
            "<td class='hex'>{}</td><td>{}</td></tr>".format(
                esc(e.get("name", "")), esc(e.get("hex", "#cccccc")),
                esc(e.get("hex", "")), esc(e.get("note", ""))))
    return ("<table><thead><tr><th style='width:24%'>分区 / 等级 / 类型</th>"
            "<th style='width:12%'>颜色</th><th style='width:14%'>色值</th>"
            "<th>用途说明</th></tr></thead><tbody>{}</tbody></table>".format("".join(rows)))


def render_gradient(g: dict) -> str:
    if not g:
        return ""
    stops = g.get("stops", [])
    labels = g.get("labels", [])
    css = ", ".join(stops)
    scale = "".join(f"<div>{esc(l)}</div>" for l in labels)
    return ("<h3>连续色阶：{}</h3><div class='bar' style='background:linear-gradient(to right,{});'></div>"
            "<div class='scale'>{}</div><div class='note'>{}</div>").format(
        esc(g.get("name", "")), esc(css), scale, esc(g.get("note", "")))


def render_legend_mock(palette: list, gradient: dict | None, title: str) -> str:
    rows = []
    for e in (palette or [])[:8]:
        rows.append("<div class='lr'><span class='b' style='background:{}'></span>"
                    "<span>{}</span></div>".format(esc(e.get("hex")), esc(e.get("name"))))
    if gradient and not rows:
        stops = gradient.get("stops", [])
        for hexv, lab in zip(stops, gradient.get("labels", [])):
            rows.append("<div class='lr'><span class='b' style='background:{}'></span>"
                        "<span>{}</span></div>".format(esc(hexv), esc(lab)))
    if not rows:
        rows.append("<div class='lr'><span class='b' style='background:#4472C4'></span>"
                    "<span>分类 A</span></div>")
    return ("<div class='legend-mock'><div class='lt'>图　例（{}）</div>{}</div>").format(
        esc(title), "".join(rows))


def render_methods(methods: list) -> str:
    rows = []
    for i, m in enumerate(methods, 1):
        rows.append("<tr><td style='text-align:center'>{}</td><td><b>{}</b></td><td>{}</td><td>{}</td></tr>".format(
            i, esc(m.get("name", "")), esc(m.get("how", "")), esc(m.get("output", ""))))
    return ("<table><thead><tr><th style='width:5%'>#</th><th style='width:22%'>表达方法</th>"
            "<th>实现方式</th><th style='width:24%'>交付成果</th></tr></thead><tbody>{}</tbody></table>"
            ).format("".join(rows))


def render_list(items: list) -> str:
    return "<ul>{}</ul>".format("".join(f"<li>{esc(x)}</li>" for x in items)) if items else \
        "<p class='hint'>无</p>"


def render_checklist(items: list) -> str:
    lis = []
    for it in items:
        lis.append("<li><span class='box'></span><span><span class='t'>{}</span><br>"
                   "<span class='d'>{}</span></span></li>".format(
                       esc(it.get("item", "")), esc(it.get("detail", ""))))
    return "<ul class='chk'>{}</ul>".format("".join(lis))


def build_html(spec: dict, project_name: str) -> str:
    topic = spec["topic"]
    auth = spec["authority"]
    auth_cls = "warn" if auth == "行业惯例" else ""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    project_block = ""
    if spec["project_traits"] or spec["project_notes"]:
        notes = render_list(spec["project_notes"]) if spec["project_notes"] else ""
        project_block = ("<h3>项目类型特征：{}</h3><div class='note'>{}</div>{}").format(
            esc(spec["project"]), esc(spec["project_traits"]), notes)

    focus_block = ""
    if spec["focus"]:
        focus_block = ("<h3>本组合的表达重点</h3><div class='note'><b>{}</b><br>{}</div>"
                       ).format(esc(spec["project"] + " × " + topic), esc(spec["focus"]))

    auth_block = ""
    if spec["authority_note"]:
        cls = "warnbox" if auth == "行业惯例" else "note"
        auth_block = "<div class='{}'><b>用色依据说明：</b>{}</div>".format(cls, esc(spec["authority_note"]))

    pitfalls = ""
    if spec["pitfalls"]:
        pitfalls = ("<h3>常见问题规避</h3>" +
                    "".join("<div class='warnbox'>✗ {}</div>".format(esc(p)) for p in spec["pitfalls"]))

    legend_rows = []
    for k, label in (("position", "图例位置"), ("size", "图例尺寸"), ("style", "图例样式"),
                     ("extra", "补充要求")):
        v = spec["legend"].get(k)
        if v:
            legend_rows.append(f"<tr><th style='width:16%'>{label}</th><td>{esc(v)}</td></tr>")
    legend_content = spec["legend"].get("content")
    if legend_content:
        legend_rows.append("<tr><th>必含内容</th><td>{}</td></tr>".format(
            "".join(f"<span class='tag'>{esc(c)}</span>" for c in legend_content)))

    drawing_rows = []
    for k, label in (("scale", "图纸比例"), ("sheet", "图幅"), ("titleblock", "标题栏"),
                     ("lineweight", "线宽与输出"), ):
        v = spec["drawing"].get(k)
        if v:
            drawing_rows.append(f"<tr><th style='width:16%'>{label}</th><td>{esc(v)}</td></tr>")
    if spec["drawing"].get("notes"):
        drawing_rows.append("<tr><th>补充要求</th><td>{}</td></tr>".format(
            "<br>".join("· " + esc(n) for n in spec["drawing"]["notes"])))

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project_name)} {esc(topic)} 专项可视化方案</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
  <h1>{esc(project_name)} · {esc(topic)} 专项可视化方案</h1>
  <div class="sub">BIM 专项可视化表达方案书 —— 颜色映射 · 图例设计 · 视图设置 · 标注要求 · 出图规范 · 检查清单</div>
  <div class="meta">
    <span>项目类型：{esc(spec["project"])}</span>
    <span>专项：{esc(topic)}</span>
    <span>领域：{esc(spec["domain"] or "通用")}</span>
    <span>用色依据：{esc(auth)}</span>
    <span>生成时间：{esc(stamp)}</span>
  </div>
</header>

<section>
  <h2>一、专项可视化方案<span class="en">VISUALIZATION APPROACH</span></h2>
  <div class="hint">依据规范：{esc(spec["standard"] or "暂无强制性规范，按行业通行做法执行")}</div>
  {project_block}
  {focus_block}
  <h3>推荐表达方法</h3>
  {render_methods(spec["methods"])}
</section>

<section>
  <h2>二、颜色映射表<span class="en">COLOR MAPPING</span></h2>
  <div class="hint">同一专项的颜色在平面、剖面、三维视图与图例中必须完全一致，不得同物异色。</div>
  {auth_block}
  {render_palette_table(spec["palette"])}
  {render_gradient(spec["gradient"])}
</section>

<section>
  <h2>三、图例设计方案<span class="en">LEGEND DESIGN</span></h2>
  <table>{''.join(legend_rows)}</table>
  <h3>图例样式示意</h3>
  {render_legend_mock(spec["palette"], spec["gradient"], topic)}
</section>

<section>
  <h2>四、视图设置步骤<span class="en">VIEW SETUP</span></h2>
  <div class="hint">Revit 与 Navisworks 的通用操作细则详见 references/view-setup.md，以下为本专项的针对性要点。</div>
  {render_list(spec["view_steps"])}
  <div class="note">通用原则：先建立独立视图样板 → 再做可见性与过滤器设置 → 最后定型视角并保存视图，避免反复调整导致各图不一致。</div>
</section>

<section>
  <h2>五、标注要求<span class="en">ANNOTATION</span></h2>
  {render_list(spec["annotation"])}
</section>

<section>
  <h2>六、出图规范<span class="en">DRAWING STANDARDS</span></h2>
  <table>{''.join(drawing_rows)}</table>
</section>

<section>
  <h2>七、专项可视化表达检查清单<span class="en">CHECKLIST</span></h2>
  <div class="hint">共 {len(spec["checklist"])} 项。逐项核对后再提交出图，可避免绝大多数返工。</div>
  {render_checklist(spec["checklist"])}
</section>

<section>
  <h2>八、常见问题规避<span class="en">PITFALLS</span></h2>
  {pitfalls or "<p class='hint'>暂无</p>"}
</section>

<footer>本方案由「BIM 专项可视化助手」生成 · 用色依据等级：{esc(auth)} · 请结合项目既有制图标准与现行规范复核后使用</footer>
</div></body></html>"""


# ==========================================================================
# Markdown 检查清单
# ==========================================================================
def build_markdown(spec: dict, project_name: str) -> str:
    lines = [
        f"# {project_name} · {spec['topic']} 专项可视化表达检查清单",
        "",
        f"- 项目类型：{spec['project']}",
        f"- 专项：{spec['topic']}",
        f"- 用色依据：{spec['authority']}",
        f"- 规范依据：{spec['standard'] or '行业通行做法'}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 颜色映射表",
        "",
        "| 分区 / 等级 / 类型 | 颜色 | 色值 | 用途说明 |",
        "| --- | --- | --- | --- |",
    ]
    for e in spec["palette"]:
        lines.append(f"| {e.get('name','')} | ⬛ | `{e.get('hex','')}` | {e.get('note','')} |")
    if not spec["palette"]:
        lines.append("| （本专项使用连续色阶） | — | — | — |")

    if spec["gradient"]:
        g = spec["gradient"]
        lines += ["", f"### 连续色阶：{g.get('name','')}", "",
                  "| 分级 | 色值 |", "| --- | --- |"]
        for hexv, lab in zip(g.get("stops", []), g.get("labels", [])):
            lines.append(f"| {lab} | `{hexv}` |")
        lines += ["", f"> {g.get('note','')}"]

    lines += ["", "## 检查清单", ""]
    for i, it in enumerate(spec["checklist"], 1):
        lines.append(f"- [ ] **{it.get('item','')}** —— {it.get('detail','')}")

    if spec["pitfalls"]:
        lines += ["", "## 常见问题规避", ""]
        for p in spec["pitfalls"]:
            lines.append(f"- ✗ {p}")

    if spec["view_steps"]:
        lines += ["", "## 视图设置要点", ""]
        for v in spec["view_steps"]:
            lines.append(f"- {v}")

    if spec["annotation"]:
        lines += ["", "## 标注要求", ""]
        for a in spec["annotation"]:
            lines.append(f"- {a}")

    lines += ["", "## 出图规范", ""]
    for k, label in (("scale", "图纸比例"), ("sheet", "图幅"), ("titleblock", "标题栏"),
                     ("lineweight", "线宽与输出")):
        if spec["drawing"].get(k):
            lines.append(f"- **{label}**：{spec['drawing'][k]}")
    for n in spec["drawing"].get("notes", []):
        lines.append(f"- {n}")

    lines += ["", "---", "",
              f"_由「BIM 专项可视化助手」生成 · 用色依据等级：{spec['authority']} · "
              f"请结合项目既有制图标准与现行规范复核后使用_", ""]
    return "\n".join(lines)


# ==========================================================================
# main
# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BIM 专项可视化方案书生成器")
    ap.add_argument("--project", default="", help="项目类型，如 铀矿工程 / 地下综合管廊 / 基坑支护")
    ap.add_argument("--topic", default="", help="专项内容，如 辐射防护分区 / 管线综合 / 疏散路线")
    ap.add_argument("--name", default="", help="项目名称，用于文件命名与标题（默认用项目类型）")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--kb", default=KB_PATH, help="知识库文件路径")
    ap.add_argument("--list", action="store_true", help="列出知识库覆盖的项目类型与专项")
    args = ap.parse_args(argv)

    kb = load_kb(args.kb)

    if args.list:
        print(json.dumps({
            "ok": True,
            "project_types": list(kb.get("project_types", {}).keys()),
            "topics": list(kb.get("topics", {}).keys()),
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.project or not args.topic:
        print(json.dumps({
            "ok": False,
            "error": "需要同时提供 --project 与 --topic（或使用 --list 查看已收录内容）",
        }, ensure_ascii=False, indent=2))
        return 2

    spec = build_spec(kb, args.project, args.topic)
    project_name = args.name or args.project
    os.makedirs(args.outdir, exist_ok=True)

    stem = safe_name(project_name)
    topic_file = safe_name(spec["topic"])
    html_path = os.path.join(args.outdir, f"{stem}_{topic_file}_可视化方案.html")
    md_path = os.path.join(args.outdir, f"{stem}_{topic_file}_可视化检查清单.md")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(spec, project_name))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown(spec, project_name))

    print(json.dumps({
        "ok": True,
        "project": spec["project"],
        "topic": spec["topic"],
        "topic_in_kb": spec["topic_matched"],
        "authority": spec["authority"],
        "standard": spec["standard"],
        "palette_count": len(spec["palette"]),
        "has_gradient": bool(spec["gradient"]),
        "methods": [m.get("name") for m in spec["methods"]],
        "checklist_count": len(spec["checklist"]),
        "view_step_count": len(spec["view_steps"]),
        "pitfalls": spec["pitfalls"],
        "files": {"html": os.path.abspath(html_path), "markdown": os.path.abspath(md_path)},
        "note": "" if spec["topic_matched"] else
                "该专项未收录在知识库中，已使用通用分类色板与通用表达方法，建议按项目实际扩充 assets/visualization_kb.json",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
