# -*- coding: utf-8 -*-
"""BIM 建模框架搭建助手 —— 方案书与说明书模板生成器

用法：
    python framework_builder.py --list
    python framework_builder.py --project 教学楼 --name "XX中学教学楼" -o out
    python framework_builder.py --input my.json --name "XX项目" -o out
    python framework_builder.py --template --name "建模框架说明书" -o out
    python framework_builder.py --project 盾构隧道 --name X --revit-mcp detected --json-only

依赖：仅 Python 标准库。
"""
import argparse
import html as H
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
KB_PATH = os.path.join(ASSETS, "framework_kb.json")
STD_PATH = os.path.join(ASSETS, "standards.json")

TODO = "〔待补充〕"


# ---------------------------------------------------------------- 资源加载

def load_assets():
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    with open(STD_PATH, encoding="utf-8") as f:
        std = json.load(f)
    return kb, std


def resolve_project(kb, name):
    """项目类型归一化。三级匹配：精确键 → 精确别名 → 长别名包含（单字不参与）。"""
    if not name:
        return None, None
    n = name.strip()
    projects = kb.get("projects", {})
    if n in projects:
        return n, projects[n]
    for key, data in projects.items():
        if n in data.get("aliases", []):
            return key, data
    best, best_len = None, 0
    for key, data in projects.items():
        for a in data.get("aliases", []):
            if len(a) < 2:
                continue  # 单字别名不参与子串匹配，避免误伤
            if a in n or n in a:
                if len(a) > best_len:
                    best, best_len = key, len(a)
    if best:
        return best, projects[best]
    return None, None


# ---------------------------------------------------------------- 工具

def esc(s):
    return H.escape(str(s if s is not None else ""))


def hl_todo(s):
    """把「〔待补充〕」渲染成醒目的红色标记。"""
    e = esc(s)
    return e.replace(
        TODO, "<span class='todo'>" + TODO + "</span>"
    ).replace("〔待确认〕", "<span class='todo'>〔待确认〕</span>")


def muted(s):
    return "<span class='muted'>" + esc(s) + "</span>" if s else ""


# ---------------------------------------------------------------- HTML 骨架

CSS = """
:root{
  --ink:#1f2329; --ink2:#4e5969; --ink3:#86909c;
  --line:#e5e6eb; --bg:#ffffff; --bg2:#f7f8fa; --bg3:#f2f3f5;
  --brand:#0f6cbd; --brand-l:#e8f3fc; --brand-d:#0a4d87;
  --ok:#00a870; --warn:#ff7d00; --danger:#d7000f; --violet:#6b4ee6;
}
*{box-sizing:border-box}
body{margin:0;background:#f7f8fa;color:var(--ink);
  font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.75;-webkit-font-smoothing:antialiased}
.page{max-width:1180px;margin:0 auto;padding:34px 30px 60px;background:var(--bg);
  box-shadow:0 1px 3px rgba(0,0,0,.06)}

.cover{border-bottom:3px solid var(--brand);padding-bottom:20px;margin-bottom:8px}
.cover .kicker{color:var(--brand);font-size:12.5px;letter-spacing:.16em;font-weight:700}
.cover h1{margin:8px 0 10px;font-size:29px;line-height:1.3;letter-spacing:-.01em}
.cover .sub{color:var(--ink2);font-size:13.5px}
.cover .meta{margin-top:16px;display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--bg3);border-radius:4px;padding:4px 11px;font-size:12.5px;color:var(--ink2)}
.chip b{color:var(--ink);font-weight:600}
.chip.brand{background:var(--brand-l);color:var(--brand-d)}
.chip.brand b{color:var(--brand-d)}

h2{font-size:19px;margin:38px 0 14px;padding-left:12px;border-left:4px solid var(--brand);
  line-height:1.4}
h2 .no{color:var(--brand);font-weight:700;margin-right:8px}
h3{font-size:15px;margin:24px 0 10px;color:var(--ink);font-weight:600}
h3 .dot{display:inline-block;width:6px;height:6px;border-radius:50%;
  background:var(--brand);margin-right:8px;vertical-align:2px}
p{margin:9px 0}
.lead{color:var(--ink2);background:var(--bg2);border-radius:6px;padding:12px 15px;
  border-left:3px solid var(--brand);margin:12px 0 18px}

table{width:100%;border-collapse:collapse;margin:12px 0 6px;font-size:13px}
th{background:var(--bg3);text-align:left;padding:9px 11px;font-weight:600;
  border:1px solid var(--line);color:var(--ink2);white-space:nowrap}
td{padding:9px 11px;border:1px solid var(--line);vertical-align:top}
tbody tr:nth-child(even){background:#fcfcfd}
td.c,th.c{text-align:center}
.mono{font-family:"SFMono-Regular",Consolas,monospace;font-size:12.5px}
.lvl{font-weight:700;color:var(--brand-d);white-space:nowrap}
.val{font-family:"SFMono-Regular",Consolas,monospace;font-weight:600;
  color:var(--brand-d);white-space:nowrap}
.tag{display:inline-block;background:var(--brand-l);color:var(--brand-d);
  border-radius:3px;padding:1px 7px;font-size:11.5px;margin:1px 3px 1px 0;
  font-family:"SFMono-Regular",Consolas,monospace}
.tag.must{background:#ffece8;color:#c4314b;font-weight:600}
.tag.lod{background:#eef0ff;color:#4b53bc;font-weight:600}
.tag.gb{background:#e8f8f0;color:#0a7f56}
.badge{display:inline-block;border-radius:3px;padding:1px 7px;font-size:11.5px;font-weight:600}
.badge.ok{background:#e8f8f0;color:#0a7f56}
.badge.warn{background:#fff3e8;color:#b25f00}
.badge.danger{background:#ffece8;color:#c4314b}

.todo{color:var(--danger);font-weight:600}
.muted{color:var(--ink3);font-size:12.5px}

.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;margin:14px 0}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;background:var(--bg)}
.card .h{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.card .n{background:var(--brand);color:#fff;width:22px;height:22px;border-radius:5px;
  font-size:12px;display:flex;align-items:center;justify-content:center;flex:0 0 auto;font-weight:700}
.card .t{font-weight:600;font-size:14px}
.card .path{font-family:"SFMono-Regular",Consolas,monospace;font-size:11.8px;
  background:var(--bg3);border-radius:4px;padding:5px 8px;color:var(--ink2);margin:7px 0}
.card ul{margin:7px 0 0;padding-left:17px}
.card li{margin:4px 0;color:var(--ink2);font-size:12.8px}
.card .chk{margin-top:9px;padding-top:8px;border-top:1px dashed var(--line);
  font-size:12.3px;color:var(--ok)}
.card .chk b{color:#0a7f56}

.seq{width:100%;border-collapse:collapse}
.seq .arrow{color:var(--ink3);text-align:center;width:26px}

ul.plain{margin:8px 0;padding-left:20px}
ul.plain li{margin:5px 0}
.chkbox{display:inline-block;width:13px;height:13px;border:1.5px solid var(--ink3);
  border-radius:2px;margin-right:8px;vertical-align:-1px}
.clist{list-style:none;padding-left:0;margin:8px 0}
.clist li{margin:6px 0;color:var(--ink2)}

.warnbox{border:1px solid #ffd8bf;background:#fff9f5;border-radius:7px;padding:13px 16px;margin:14px 0}
.warnbox .h{font-weight:600;color:#b25f00;margin-bottom:7px}
.errbox{border:1px solid #ffd6d8;background:#fff6f6;border-radius:7px;padding:13px 16px;margin:14px 0}
.errbox .h{font-weight:600;color:#c4314b;margin-bottom:7px}
.okbox{border:1px solid #b7ebd0;background:#f4fdf8;border-radius:7px;padding:13px 16px;margin:14px 0}
.okbox .h{font-weight:600;color:#0a7f56;margin-bottom:7px}
.infobox{border:1px solid #cfe3f5;background:#f5faff;border-radius:7px;padding:13px 16px;margin:14px 0}
.infobox .h{font-weight:600;color:var(--brand-d);margin-bottom:7px}

.lodbar{display:flex;gap:6px;margin:14px 0;flex-wrap:wrap}
.lodbar .b{flex:1 1 130px;border-radius:6px;padding:10px 12px;background:var(--bg3);
  border-top:3px solid var(--brand)}
.lodbar .b .l{font-weight:700;color:var(--brand-d);font-size:13px}
.lodbar .b .n{font-size:12.5px;color:var(--ink2);margin-top:2px}
.lodbar .b .s{font-size:11.5px;color:var(--ink3);margin-top:4px}

.blank{display:block;min-height:26px;border-bottom:1px solid var(--line);margin:6px 0}
.fieldrow{display:flex;gap:10px;margin:9px 0;align-items:flex-end}
.fieldrow .lbl{flex:0 0 168px;color:var(--ink2);font-size:13px}
.fieldrow .ln{flex:1;border-bottom:1px solid var(--line);min-height:24px}

.foot{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--ink3);font-size:12px;display:flex;justify-content:space-between;gap:12px}
@media print{
  body{background:#fff}
  .page{box-shadow:none;max-width:none;padding:0}
  h2{page-break-after:avoid}
  .card,.warnbox,.errbox,.infobox{page-break-inside:avoid}
  table{page-break-inside:auto}
  tr{page-break-inside:avoid}
}
"""


def page(title, body, subtitle=""):
    return (
        "<!DOCTYPE html>\n<html lang='zh-CN'>\n<head>\n<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>\n"
        "<title>" + esc(title) + "</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n"
        "<div class='page'>\n" + body +
        "\n<div class='foot'><span>由 BIM 建模框架搭建助手 自动生成</span>"
        "<span>" + esc(datetime.now().strftime("%Y-%m-%d %H:%M")) + "</span></div>\n"
        "</div>\n</body>\n</html>\n"
    )


# ---------------------------------------------------------------- 方案书片段

def sec_levels(p):
    out = ["<h2><span class='no'>1</span>标高轴网方案</h2>"]
    out.append("<div class='lead'><b>标高体系依据</b>：" + esc(p.get("level_basis", "")) + "</div>")
    out.append("<h3><span class='dot'></span>1.1 建议标高表</h3>")
    out.append("<table><thead><tr><th style='width:24%'>标高名称</th>"
               "<th style='width:15%' class='c'>标高值 (m)</th><th>说明</th></tr></thead><tbody>")
    for lv in p.get("levels", []):
        out.append("<tr><td>" + hl_todo(lv.get("name", "")) + "</td>"
                   "<td class='c'><span class='val'>" + esc(lv.get("value", "")) + "</span></td>"
                   "<td>" + hl_todo(lv.get("note", "")) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>1.2 轴网方案</h3>")
    out.append("<div class='lead'><b>轴网定位依据</b>：" + esc(p.get("grid_basis", "")) + "</div>")
    out.append("<table><thead><tr><th style='width:30%'>轴线 / 控制线</th>"
               "<th style='width:20%' class='c'>间距</th><th>说明</th></tr></thead><tbody>")
    for g in p.get("grids", []):
        out.append("<tr><td><b>" + hl_todo(g.get("axis", "")) + "</b></td>"
                   "<td class='c'><span class='mono'>" + esc(g.get("spacing", "")) + "</span></td>"
                   "<td>" + hl_todo(g.get("note", "")) + "</td></tr>")
    out.append("</tbody></table>")

    gn = p.get("grid_notes", [])
    if gn:
        out.append("<h3><span class='dot'></span>1.3 轴网与标高注意事项</h3>")
        out.append("<ul class='plain'>")
        for x in gn:
            out.append("<li>" + hl_todo(x) + "</li>")
        out.append("</ul>")
    return "\n".join(out)


def sec_disciplines(p):
    out = ["<h2><span class='no'>2</span>专业拆分表</h2>"]
    out.append("<p>各专业的建模范围与接口。接口一栏写的是「谁向谁提资、提什么」，"
               "这是专业拆分里最容易含糊、也最容易在后期引发返工的部分。</p>")
    out.append("<table><thead><tr><th style='width:15%'>专业</th>"
               "<th style='width:43%'>建模范围</th><th>接口关系</th></tr></thead><tbody>")
    for d in p.get("disciplines", []):
        scope = "".join("<span class='tag'>" + esc(s) + "</span>" for s in d.get("scope", []))
        ifs = "<ul class='plain' style='margin:0;padding-left:16px'>" + \
              "".join("<li>" + hl_todo(i) + "</li>" for i in d.get("interfaces", [])) + "</ul>"
        out.append("<tr><td><b>" + esc(d.get("name", "")) + "</b></td>"
                   "<td>" + scope + "</td><td>" + ifs + "</td></tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def sec_lod(p, std):
    out = ["<h2><span class='no'>3</span>LOD 规划表</h2>"]
    info = std["lod_system"]

    out.append("<div class='infobox'><div class='h'>关于 LOD 体系的口径说明（重要）</div>"
               + esc(info["origin_note"]) +
               "<p style='margin-bottom:0'><b>国内对应标准</b>：" +
               esc(info["gb_reference"]["standard"]) + "——" +
               esc(info["gb_reference"]["structure"]) + "。" +
               esc(info["gb_reference"]["relation"]) + "</p></div>")

    out.append("<div class='lodbar'>")
    for lv in info["levels"]:
        out.append("<div class='b'><div class='l'>" + esc(lv["lod"]) + "</div>"
                   "<div class='n'>" + esc(lv["name"]) + "</div>"
                   "<div class='s'>" + esc(lv["stage"]) + "</div></div>")
    out.append("</div>")

    out.append("<h3><span class='dot'></span>3.1 本项目各阶段模型深度</h3>")
    out.append("<table><thead><tr><th style='width:19%'>阶段</th><th class='c' style='width:11%'>LOD</th>"
               "<th class='c' style='width:12%'>国标对照</th>"
               "<th style='width:32%'>建模内容</th><th>交付物</th></tr></thead><tbody>")
    for r in p.get("lod_plan", []):
        out.append("<tr><td>" + esc(r.get("phase", "")) + "</td>"
                   "<td class='c'><span class='tag lod'>" + esc(r.get("lod", "")) + "</span></td>"
                   "<td class='c'><span class='tag gb'>" + esc(r.get("gb", "")) + "</span></td>"
                   "<td>" + hl_todo(r.get("content", "")) + "</td>"
                   "<td>" + hl_todo(r.get("deliverable", "")) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>3.2 各等级几何与信息要求</h3>")
    out.append("<table><thead><tr><th class='c' style='width:9%'>等级</th>"
               "<th style='width:20%'>几何表达</th><th style='width:22%'>信息深度</th>"
               "<th>使用注意</th></tr></thead><tbody>")
    for lv in info["levels"]:
        out.append("<tr><td class='c'><b>" + esc(lv["lod"]) + "</b><br>"
                   "<span class='muted'>" + esc(lv["name"]) + "</span></td>"
                   "<td>" + esc(lv["geometry"]) + "</td>"
                   "<td>" + esc(lv["info"]) + "</td>"
                   "<td>" + hl_todo(lv["warning"]) + "</td></tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def sec_coordination(p):
    out = ["<h2><span class='no'>4</span>协同工作计划</h2>"]

    out.append("<h3><span class='dot'></span>4.1 建模顺序与前置条件</h3>")
    out.append("<table class='seq'><thead><tr><th class='c' style='width:5%'>序</th>"
               "<th style='width:28%'>任务</th><th style='width:13%'>主责专业</th>"
               "<th style='width:22%'>前置条件</th><th>要点</th></tr></thead><tbody>")
    for s in p.get("sequence", []):
        out.append("<tr><td class='c'><b>" + esc(s.get("step", "")) + "</b></td>"
                   "<td><b>" + esc(s.get("task", "")) + "</b></td>"
                   "<td>" + esc(s.get("owner", "")) + "</td>"
                   "<td class='muted'>" + esc(s.get("prerequisite", "")) + "</td>"
                   "<td>" + hl_todo(s.get("note", "")) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>4.2 碰撞检测节点</h3>")
    out.append("<p>按时间顺序排定的核查节点。每个节点都必须有明确的通过标准——"
               "没有标准的核查会变成「看一眼觉得还行」。</p>")
    out.append("<table><thead><tr><th style='width:17%'>节点</th>"
               "<th style='width:15%'>核查时机</th><th style='width:28%'>核查范围</th>"
               "<th>通过标准</th></tr></thead><tbody>")
    for c in p.get("clash_nodes", []):
        out.append("<tr><td><b>" + esc(c.get("node", "")) + "</b></td>"
                   "<td class='muted'>" + esc(c.get("when", "")) + "</td>"
                   "<td>" + esc(c.get("scope", "")) + "</td>"
                   "<td>" + hl_todo(c.get("criteria", "")) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>4.3 模型拆分与工作集</h3>")
    out.append("<table><thead><tr><th style='width:28%'>模型 / 工作集</th>"
               "<th style='width:18%'>工作集命名</th><th>说明</th></tr></thead><tbody>")
    for m in p.get("model_split", []):
        out.append("<tr><td><b>" + esc(m.get("model", "")) + "</b></td>"
                   "<td><span class='mono'>" + esc(m.get("workset", "")) + "</span></td>"
                   "<td>" + hl_todo(m.get("note", "")) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>4.4 交付物清单</h3>")
    out.append("<table><thead><tr><th style='width:34%'>交付物</th>"
               "<th style='width:20%' class='c'>格式</th><th>说明</th></tr></thead><tbody>")
    for d in p.get("deliverables", []):
        out.append("<tr><td>" + esc(d.get("item", "")) + "</td>"
                   "<td class='c'><span class='mono'>" + esc(d.get("format", "")) + "</span></td>"
                   "<td>" + hl_todo(d.get("note", "")) + "</td></tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def sec_revit_steps(std):
    out = ["<h2><span class='no'>6</span>Revit 操作步骤清单</h2>"]
    out.append("<p>" + esc(std["revit_steps"]["intro"]) + "</p>")
    out.append("<div class='cards'>")
    for s in std["revit_steps"]["steps"]:
        out.append("<div class='card'>")
        out.append("<div class='h'><span class='n'>" + str(s["step"]) + "</span>"
                   "<span class='t'>" + esc(s["title"]) + "</span></div>")
        out.append("<div class='path'>" + esc(s["path"]) + "</div>")
        out.append("<ul>")
        for d in s["detail"]:
            out.append("<li>" + hl_todo(d) + "</li>")
        out.append("</ul>")
        out.append("<div class='chk'><b>校验点</b>：" + hl_todo(s["check"]) + "</div>")
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def sec_mcp(std, mode):
    out = ["<h2><span class='no'>7</span>Revit 连接器状态与执行方式</h2>"]
    if mode == "detected":
        d = std["revit_mcp"]["detected"]
        out.append("<div class='okbox'><div class='h'>" + esc(d["title"]) + "</div>"
                   "<p>" + esc(d["prompt"]) + "</p></div>")
        out.append("<h3><span class='dot'></span>可选执行方式</h3>")
        out.append("<table><thead><tr><th style='width:30%'>方式</th><th>说明</th></tr></thead><tbody>")
        for o in d["options"]:
            out.append("<tr><td><b>" + esc(o["label"]) + "</b></td><td>" + esc(o["desc"]) + "</td></tr>")
        out.append("</tbody></table>")
        out.append("<h3><span class='dot'></span>若选择自动创建，执行顺序为</h3>")
        out.append("<ul class='plain'>")
        for x in d["execution_order"]:
            out.append("<li>" + esc(x) + "</li>")
        out.append("</ul>")
        out.append("<div class='warnbox'><div class='h'>安全约束</div><ul class='plain' style='margin:0'>")
        for x in d["safety_rules"]:
            out.append("<li>" + hl_todo(x) + "</li>")
        out.append("</ul></div>")
    else:
        d = std["revit_mcp"]["not_detected"]
        out.append("<div class='warnbox'><div class='h'>" + esc(d["title"]) + "</div>"
                   "<p style='margin-bottom:0'>" + esc(d["message"]) + "</p></div>")
        out.append("<h3><span class='dot'></span>如需后续自动创建</h3>")
        out.append("<ul class='plain'>")
        for x in d["how_to_enable"]:
            out.append("<li>" + esc(x) + "</li>")
        out.append("</ul>")
        out.append("<div class='infobox'><div class='h'>本次交付说明</div>"
                   "本文档为<b>方案文件</b>：第 1—4 节给出应建成的框架内容，第 6 节给出 Revit 中的"
                   "逐项操作路径与校验点。请按第 6 节顺序操作，每步完成后对照校验点自检。</div>")
    return "\n".join(out)


def sec_checklist(std):
    out = ["<h2><span class='no'>8</span>建模框架自检清单</h2>"]
    out.append("<p>" + esc(std["framework_checklist"]["intro"]) + "</p>")
    for s in std["framework_checklist"]["sections"]:
        out.append("<h3><span class='dot'></span>" + esc(s["title"]) + "</h3>")
        out.append("<ul class='clist'>")
        for it in s["items"]:
            out.append("<li><span class='chkbox'></span>" + hl_todo(it) + "</li>")
        out.append("</ul>")
    return "\n".join(out)


def sec_appendix(p, std):
    out = ["<h2><span class='no'>9</span>附录：命名规范与常见陷阱</h2>"]
    out.append("<h3><span class='dot'></span>9.1 命名规范</h3>")
    out.append("<div class='infobox'><div class='h'>规范效力说明</div>"
               + esc(std["naming_convention"]["authority_note"]) + "</div>")
    rows = [
        ("模型文件", "file_model"), ("工作集", "workset"), ("视图", "view"),
        ("图纸", "sheet"), ("构件类型", "component"),
    ]
    out.append("<table><thead><tr><th style='width:16%'>对象</th><th style='width:26%'>规则</th>"
               "<th style='width:26%'>示例</th><th>说明</th></tr></thead><tbody>")
    for label, key in rows:
        v = std["naming_convention"][key]
        out.append("<tr><td><b>" + esc(label) + "</b></td>"
                   "<td class='mono'>" + esc(v["pattern"]) + "</td>"
                   "<td class='mono'>" + esc(v["example"]) + "</td>"
                   "<td>" + hl_todo(v["note"]) + "</td></tr>")
    out.append("</tbody></table>")

    out.append("<h3><span class='dot'></span>9.2 本项目类型专属陷阱</h3>")
    out.append("<div class='errbox'><div class='h'>这些是本类项目最容易犯且代价最高的错误</div>")
    out.append("<ul class='plain' style='margin:0'>")
    for x in p.get("pitfalls", []):
        out.append("<li>" + hl_todo(x) + "</li>")
    out.append("</ul></div>")
    return "\n".join(out)


def build_scheme_html(name, key, p, kb, std, mcp_mode):
    cover = [
        "<div class='cover'>",
        "<div class='kicker'>BIM 建模框架方案</div>",
        "<h1>" + esc(name) + "<br><span style='font-size:19px;color:#4e5969'>"
        "建模框架搭建方案（" + esc(key) + "）</span></h1>",
        "<div class='sub'>项目类型：" + esc(p.get("category", "")) + "　·　"
        + esc(p.get("intro", "")) + "</div>",
        "<div class='meta'>",
        "<span class='chip brand'>项目类型 <b>" + esc(key) + "</b></span>",
        "<span class='chip'>标高 <b>" + str(len(p.get("levels", []))) + "</b> 项</span>",
        "<span class='chip'>轴网 <b>" + str(len(p.get("grids", []))) + "</b> 项</span>",
        "<span class='chip'>专业 <b>" + str(len(p.get("disciplines", []))) + "</b> 个</span>",
        "<span class='chip'>碰撞节点 <b>" + str(len(p.get("clash_nodes", []))) + "</b> 个</span>",
        "<span class='chip'>Revit 步骤 <b>" + str(len(std["revit_steps"]["steps"])) + "</b> 步</span>",
        "</div></div>",
    ]
    toc = ["<h2 style='border-left-color:#86909c'><span class='no' style='color:#86909c'>目录</span></h2>",
           "<table><tbody>"]
    toc_items = [
        ("1", "标高轴网方案"), ("2", "专业拆分表"), ("3", "LOD 规划表"),
        ("4", "协同工作计划"), ("5", "建模框架说明书（另附模板）"),
        ("6", "Revit 操作步骤清单"), ("7", "Revit 连接器状态与执行方式"),
        ("8", "建模框架自检清单"), ("9", "附录：命名规范与常见陷阱"),
    ]
    for no, t in toc_items:
        toc.append("<tr><td style='width:6%;text-align:center'><b>" + no + "</b></td><td>" + t + "</td></tr>")
    toc.append("</tbody></table>")

    note5 = ("<h2><span class='no'>5</span>建模框架说明书</h2>"
             "<div class='lead'>说明书是建模工作的<b>依据文件</b>，由项目组填写并签署后作为后续"
             "建模、校核与交付的判定标准。已按第 1—4 节内容预填大部分字段，"
             "其余需项目组补充。<b>可填写的空白模板见同目录下的"
             "「" + esc(name) + "_建模框架说明书模板.html」</b>。</div>"
             "<table><thead><tr><th style='width:7%' class='c'>序</th>"
             "<th style='width:22%'>章节</th><th>需填写内容</th></tr></thead><tbody>")
    for s in std["manual_template_sections"]["sections"]:
        fields = "".join("<span class='tag'>" + esc(f) + "</span>"
                         for f in s.get("fields", []))
        note5 += ("<tr><td class='c'><b>" + s["no"] + "</b></td><td><b>" + esc(s["title"]) +
                  "</b></td><td>" + fields + "</td></tr>")
    note5 += "</tbody></table>"

    body = "\n".join(
        cover + toc +
        [sec_levels(p), sec_disciplines(p), sec_lod(p, std), sec_coordination(p),
         note5, sec_revit_steps(std), sec_mcp(std, mcp_mode),
         sec_checklist(std), sec_appendix(p, std)]
    )
    return page(name + " · 建模框架方案", body)


def build_scheme_md(name, key, p, kb, std, mcp_mode):
    L = []
    A = L.append
    A("# " + name + "　建模框架方案")
    A("")
    A("- **项目类型**：" + key + "（" + p.get("category", "") + "）")
    A("- **生成时间**：" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("- **说明**：" + p.get("intro", ""))
    A("")
    A("---")
    A("")

    A("## 1. 标高轴网方案")
    A("")
    A("**标高体系依据**：" + p.get("level_basis", ""))
    A("")
    A("### 1.1 建议标高表")
    A("")
    A("| 标高名称 | 标高值 (m) | 说明 |")
    A("| --- | ---: | --- |")
    for lv in p.get("levels", []):
        A("| " + lv.get("name", "") + " | `" + lv.get("value", "") + "` | " + lv.get("note", "") + " |")
    A("")
    A("### 1.2 轴网方案")
    A("")
    A("**轴网定位依据**：" + p.get("grid_basis", ""))
    A("")
    A("| 轴线 / 控制线 | 间距 | 说明 |")
    A("| --- | --- | --- |")
    for g in p.get("grids", []):
        A("| **" + g.get("axis", "") + "** | " + g.get("spacing", "") + " | " + g.get("note", "") + " |")
    A("")
    if p.get("grid_notes"):
        A("### 1.3 轴网与标高注意事项")
        A("")
        for x in p["grid_notes"]:
            A("- " + x)
        A("")

    A("## 2. 专业拆分表")
    A("")
    for d in p.get("disciplines", []):
        A("### " + d.get("name", ""))
        A("")
        A("- **建模范围**：" + "、".join(d.get("scope", [])))
        A("- **接口关系**：")
        for i in d.get("interfaces", []):
            A("  - " + i)
        A("")

    A("## 3. LOD 规划表")
    A("")
    info = std["lod_system"]
    A("> **口径说明**：" + info["origin_note"])
    A(">")
    A("> **国内标准**：" + info["gb_reference"]["standard"] + "，采用"
      + info["gb_reference"]["structure"] + "。" + info["gb_reference"]["relation"])
    A("")
    A("### 3.1 本项目各阶段模型深度")
    A("")
    A("| 阶段 | LOD | 国标对照 | 建模内容 | 交付物 |")
    A("| --- | :-: | :-: | --- | --- |")
    for r in p.get("lod_plan", []):
        A("| " + r.get("phase", "") + " | " + r.get("lod", "") + " | " + r.get("gb", "")
          + " | " + r.get("content", "") + " | " + r.get("deliverable", "") + " |")
    A("")
    A("### 3.2 各等级几何与信息要求")
    A("")
    A("| 等级 | 几何表达 | 信息深度 | 使用注意 |")
    A("| :-: | --- | --- | --- |")
    for lv in info["levels"]:
        A("| **" + lv["lod"] + "**<br>" + lv["name"] + " | " + lv["geometry"] + " | "
          + lv["info"] + " | " + lv["warning"] + " |")
    A("")

    A("## 4. 协同工作计划")
    A("")
    A("### 4.1 建模顺序与前置条件")
    A("")
    A("| 序 | 任务 | 主责专业 | 前置条件 | 要点 |")
    A("| :-: | --- | --- | --- | --- |")
    for s in p.get("sequence", []):
        A("| " + str(s.get("step", "")) + " | **" + s.get("task", "") + "** | " + s.get("owner", "")
          + " | " + s.get("prerequisite", "") + " | " + s.get("note", "") + " |")
    A("")
    A("### 4.2 碰撞检测节点")
    A("")
    A("| 节点 | 核查时机 | 核查范围 | 通过标准 |")
    A("| --- | --- | --- | --- |")
    for c in p.get("clash_nodes", []):
        A("| **" + c.get("node", "") + "** | " + c.get("when", "") + " | " + c.get("scope", "")
          + " | " + c.get("criteria", "") + " |")
    A("")
    A("### 4.3 模型拆分与工作集")
    A("")
    A("| 模型 / 工作集 | 工作集命名 | 说明 |")
    A("| --- | --- | --- |")
    for m in p.get("model_split", []):
        A("| **" + m.get("model", "") + "** | `" + m.get("workset", "") + "` | " + m.get("note", "") + " |")
    A("")
    A("### 4.4 交付物清单")
    A("")
    A("| 交付物 | 格式 | 说明 |")
    A("| --- | :-: | --- |")
    for d in p.get("deliverables", []):
        A("| " + d.get("item", "") + " | `" + d.get("format", "") + "` | " + d.get("note", "") + " |")
    A("")

    A("## 5. 建模框架说明书模板结构")
    A("")
    A("可填写模板见同目录「" + name + "_建模框架说明书模板.html / .md」。章节如下：")
    A("")
    for s in std["manual_template_sections"]["sections"]:
        A("- **" + s["no"] + ". " + s["title"] + "**：" + "、".join(s.get("fields", [])))
    A("")

    A("## 6. Revit 操作步骤清单")
    A("")
    A("> " + std["revit_steps"]["intro"])
    A("")
    for s in std["revit_steps"]["steps"]:
        A("### 步骤 " + str(s["step"]) + "　" + s["title"])
        A("")
        A("`" + s["path"] + "`")
        A("")
        for d in s["detail"]:
            A("- " + d)
        A("")
        A("- **校验点**：" + s["check"])
        A("")

    A("## 7. Revit 连接器状态与执行方式")
    A("")
    if mcp_mode == "detected":
        d = std["revit_mcp"]["detected"]
        A("> **" + d["title"] + "**")
        A(">")
        A("> " + d["prompt"])
        A("")
        A("可选方式：")
        A("")
        for o in d["options"]:
            A("- **" + o["label"] + "**：" + o["desc"])
        A("")
        A("若选择自动创建，执行顺序：")
        A("")
        for x in d["execution_order"]:
            A("- " + x)
        A("")
        A("**安全约束**：")
        A("")
        for x in d["safety_rules"]:
            A("- " + x)
    else:
        d = std["revit_mcp"]["not_detected"]
        A("> **" + d["title"] + "**")
        A(">")
        A("> " + d["message"])
        A("")
        A("如需后续自动创建：")
        A("")
        for x in d["how_to_enable"]:
            A("- " + x)
    A("")

    A("## 8. 建模框架自检清单")
    A("")
    for s in std["framework_checklist"]["sections"]:
        A("### " + s["title"])
        A("")
        for it in s["items"]:
            A("- [ ] " + it)
        A("")

    A("## 9. 附录：命名规范与常见陷阱")
    A("")
    A("### 9.1 命名规范")
    A("")
    A("> " + std["naming_convention"]["authority_note"])
    A("")
    A("| 对象 | 规则 | 示例 | 说明 |")
    A("| --- | --- | --- | --- |")
    for label, key2 in [("模型文件", "file_model"), ("工作集", "workset"), ("视图", "view"),
                        ("图纸", "sheet"), ("构件类型", "component")]:
        v = std["naming_convention"][key2]
        A("| **" + label + "** | `" + v["pattern"] + "` | `" + v["example"] + "` | " + v["note"] + " |")
    A("")
    A("### 9.2 本项目类型专属陷阱")
    A("")
    for x in p.get("pitfalls", []):
        A("- " + x)
    A("")
    A("---")
    A("")
    A("*由 BIM 建模框架搭建助手 自动生成 · " + datetime.now().strftime("%Y-%m-%d %H:%M") + "*")
    return "\n".join(L)


# ---------------------------------------------------------------- 说明书模板

def build_manual_html(name, key, p, std):
    secs = std["manual_template_sections"]["sections"]
    body = []
    body.append("<div class='cover'><div class='kicker'>BIM 建模框架说明书</div>"
                "<h1>" + esc(name) + "</h1>"
                "<div class='sub'>项目类型：" + esc(key) + "　·　"
                "本文件为<b>可填写模板</b>，由项目组填写并签署后作为建模依据</div>"
                "<div class='meta'>"
                "<span class='chip'>章节 <b>" + str(len(secs)) + "</b></span>"
                "<span class='chip'>共 <b>" + str(sum(len(s.get("fields", [])) for s in secs)) + "</b> 个填写项</span>"
                "<span class='chip brand'>签署后即为交付判定标准</span>"
                "</div></div>")

    body.append("<div class='infobox'><div class='h'>填写说明</div>"
                "<p style='margin-bottom:0'>本说明书是建模工作的依据文件。填写完成并签署后，"
                "后续的建模、校核与交付均以本文件为判定标准；如需变更，须在文末变更记录中登记。"
                "第 3、4 节可直接引用《建模框架方案》中的标高表与轴网表。</p></div>")

    for s in secs:
        body.append("<h2><span class='no'>" + s["no"] + "</span>" + esc(s["title"]) + "</h2>")
        for f in s.get("fields", []):
            body.append("<div class='fieldrow'><div class='lbl'>" + esc(f) + "</div>"
                        "<div class='ln'></div></div>")
        if s["no"] in ("3", "4"):
            body.append("<p class='muted'>（本节的标高值与轴网间距请直接引用《" + esc(name)
                        + "_建模框架方案》第 1 节，如与方案不一致须在变更记录中说明原因。)</p>")
        body.append("")

    body.append("<h2><span class='no'>附</span>变更记录</h2>")
    body.append("<table><thead><tr><th class='c' style='width:12%'>序号</th>"
                "<th style='width:16%'>日期</th><th style='width:24%'>变更内容</th>"
                "<th style='width:24%'>变更原因</th><th>提出/批准人</th></tr></thead><tbody>")
    for i in range(4):
        body.append("<tr><td class='c'>" + str(i + 1) + "</td><td></td><td></td><td></td><td></td></tr>")
    body.append("</tbody></table>")

    body.append("<h2><span class='no'>附</span>签署</h2>")
    body.append("<table><tbody>"
                "<tr><td style='width:20%'><b>编制</b></td><td style='height:52px'></td>"
                "<td style='width:20%'><b>日期</b></td><td style='width:20%'></td></tr>"
                "<tr><td><b>校核</b></td><td style='height:52px'></td>"
                "<td><b>日期</b></td><td></td></tr>"
                "<tr><td><b>审核</b></td><td style='height:52px'></td>"
                "<td><b>日期</b></td><td></td></tr>"
                "</tbody></table>")
    return page(name + " · 建模框架说明书", "\n".join(body))


def build_manual_md(name, key, std):
    L = []
    A = L.append
    secs = std["manual_template_sections"]["sections"]
    A("# " + name + "　建模框架说明书")
    A("")
    A("- **项目类型**：" + key)
    A("- **文件性质**：可填写模板，签署后作为建模依据")
    A("- **填写说明**：" + std["manual_template_sections"]["intro"])
    A("")
    A("---")
    A("")
    for s in secs:
        A("## " + s["no"] + ". " + s["title"])
        A("")
        for f in s.get("fields", []):
            A("- **" + f + "**：")
        A("")
    A("## 附. 变更记录")
    A("")
    A("| 序号 | 日期 | 变更内容 | 变更原因 | 提出/批准人 |")
    A("| :-: | --- | --- | --- | --- |")
    for i in range(4):
        A("| " + str(i + 1) + " |  |  |  |  |")
    A("")
    A("## 附. 签署")
    A("")
    A("| 编制 | 日期 | 校核 | 日期 | 审核 | 日期 |")
    A("| --- | --- | --- | --- | --- | --- |")
    A("|  |  |  |  |  |  |")
    A("")
    A("---")
    A("")
    A("*由 BIM 建模框架搭建助手 自动生成 · " + datetime.now().strftime("%Y-%m-%d %H:%M") + "*")
    return "\n".join(L)


# ---------------------------------------------------------------- 主流程

def emit(out_dir, filename, text):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser(description="BIM 建模框架搭建助手")
    ap.add_argument("--list", action="store_true", help="列出知识库覆盖的项目类型")
    ap.add_argument("--project", help="项目类型（如 教学楼 / 盾构隧道 / 铀矿巷道）")
    ap.add_argument("--name", default="〔项目名称〕", help="项目名称，用于文件名与标题")
    ap.add_argument("--out", "-o", default=".", help="输出目录")
    ap.add_argument("--input", help="自定义 JSON（覆盖知识库内容）")
    ap.add_argument("--template", action="store_true", help="只输出空白说明书模板")
    ap.add_argument("--revit-mcp", choices=["detected", "not-detected", "auto"], default="not-detected",
                    help="Revit 连接器状态；auto 表示由调用方判断后传入")
    ap.add_argument("--json-only", action="store_true", help="仅输出 JSON 结果摘要")
    args = ap.parse_args()

    kb, std = load_assets()

    if args.list:
        print("知识库覆盖的项目类型（共 %d 类）:" % len(kb["projects"]))
        for k, v in kb["projects"].items():
            print("  %-8s %-28s 别名 %d 个" % (k, v["category"], len(v.get("aliases", []))))
            print("           标高 %d / 轴网 %d / 专业 %d / LOD %d / 碰撞节点 %d"
                  % (len(v["levels"]), len(v["grids"]), len(v["disciplines"]),
                     len(v["lod_plan"]), len(v["clash_nodes"])))
        print("  %-8s %s" % ("(通用)", kb["generic_fallback"]["category"] + " —— 未收录项目类型的回退骨架"))
        print("")
        print("Revit 步骤：%d 步；框架自检清单：%d 节 %d 条"
              % (len(std["revit_steps"]["steps"]),
                 len(std["framework_checklist"]["sections"]),
                 sum(len(s["items"]) for s in std["framework_checklist"]["sections"])))
        return 0

    # 无项目类型且指定了模板 → 纯空白模板
    if args.template and not (args.project or args.input):
        mh = emit(args.out, args.name + "_建模框架说明书模板.html",
                  build_manual_html(args.name, "（未指定）", None, std))
        mm = emit(args.out, args.name + "_建模框架说明书模板.md", build_manual_md(args.name, "（未指定）", std))
        if args.json_only:
            print(json.dumps({"ok": True, "mode": "template", "files": [mh, mm]},
                             ensure_ascii=False, indent=2))
        else:
            print("已生成空白模板：")
            print("  " + mh)
            print("  " + mm)
        return 0

    # 决定项目类型
    in_library = True
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            payload = json.load(f)
        key = payload.get("project_type") or args.project or ""
        rk, rp = resolve_project(kb, key)
        base = dict(rp) if rp else dict(kb["generic_fallback"])
        in_library = rp is not None
        # 用输入内容覆盖（浅合并 + 列表整体替换）
        for k, v in payload.items():
            if k in ("project_type", "project_name"):
                continue
            base[k] = v
        p = base
        key = key or (rk or "通用")
    else:
        if not args.project:
            print(json.dumps({"ok": False, "error": "缺少 --project 或 --input；用 --list 查看支持的项目类型"},
                             ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        rk, rp = resolve_project(kb, args.project)
        key = rk or args.project.strip()
        in_library = rp is not None
        p = dict(rp) if rp else dict(kb["generic_fallback"])

    mcp_mode = "detected" if args.revit_mcp == "detected" else "not-detected"

    doc_html = build_scheme_html(args.name, key, p, kb, std, mcp_mode)
    doc_md = build_scheme_md(args.name, key, p, kb, std, mcp_mode)
    man_html = build_manual_html(args.name, key, p, std)
    man_md = build_manual_md(args.name, key, std)

    f1 = emit(args.out, args.name + "_建模框架方案.html", doc_html)
    f2 = emit(args.out, args.name + "_建模框架方案.md", doc_md)
    f3 = emit(args.out, args.name + "_建模框架说明书模板.html", man_html)
    f4 = emit(args.out, args.name + "_建模框架说明书模板.md", man_md)

    checklist_items = sum(len(s["items"]) for s in std["framework_checklist"]["sections"])
    result = {
        "ok": True,
        "mode": "scheme",
        "project_type_input": args.project or (args.input and "input"),
        "project_type_resolved": key,
        "in_library": in_library,
        "revit_mcp": mcp_mode,
        "counts": {
            "levels": len(p.get("levels", [])),
            "grids": len(p.get("grids", [])),
            "disciplines": len(p.get("disciplines", [])),
            "lod_plan": len(p.get("lod_plan", [])),
            "sequence": len(p.get("sequence", [])),
            "clash_nodes": len(p.get("clash_nodes", [])),
            "deliverables": len(p.get("deliverables", [])),
            "model_split": len(p.get("model_split", [])),
            "pitfalls": len(p.get("pitfalls", [])),
            "revit_steps": len(std["revit_steps"]["steps"]),
            "checklist_items": checklist_items,
        },
        "placeholders": doc_html.count(TODO),
        "files": [f1, f2, f3, f4],
    }
    if not in_library:
        result["note"] = ("项目类型「%s」未收录，已回退到通用骨架；"
                          "项目特有部分（结构体系、专业构成、标高层级）需人工补充确认。" % key)

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("项目类型：" + key + ("（知识库命中）" if in_library else "（未收录，已回退通用骨架）"))
        print("Revit 连接器：" + ("已检测" if mcp_mode == "detected" else "未检测"))
        print("内容规模：" + "、".join("%s %d" % (k, v) for k, v in result["counts"].items()))
        print("待补充占位：" + str(result["placeholders"]))
        print("")
        print("已生成：")
        for f in result["files"]:
            print("  " + f)
        if not in_library:
            print("")
            print("注意：" + result["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
