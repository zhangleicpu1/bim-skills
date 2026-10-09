# -*- coding: utf-8 -*-
"""BIM 工程量统计方案生成器

用法：
  quantity_builder.py --list
  quantity_builder.py --component 混凝土 --project "XX项目" --name "XX项目" -o out
  quantity_builder.py --input data.json --name "XX项目" -o out
  quantity_builder.py --template [all|checklist|deviation] -o out
  ... 加 --json-only 输出机器可读结果
"""
import argparse
import html as H
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
TODO = "〔待补充〕"
PLACEHOLDER_RE = re.compile(r"〔[^〕]*〕")

# 歧义别名的默认归属（同一别名出现在多个构件上时）
AMBIGUOUS_DEFAULT = {
    "构造柱": "masonry", "圈梁": "masonry", "过梁": "masonry", "压顶": "masonry",
    "保温层": "waterproof_insulation", "钢支撑": "pile_retaining",
    "钢筋网": "anchor", "阀门": "piping",
}


# ---------------------------------------------------------------- 载入
def load_assets():
    kb = json.load(open(os.path.join(ASSETS, "quantity_kb.json"), encoding="utf-8"))
    std = json.load(open(os.path.join(ASSETS, "standards.json"), encoding="utf-8"))
    return kb, std


def build_alias_index(kb):
    """别名 → 构件 key 列表（含歧义）"""
    idx = {}
    for k, v in kb["components"].items():
        for a in [k] + list(v.get("aliases", [])):
            idx.setdefault(a, [])
            if k not in idx[a]:
                idx[a].append(k)
    return idx


def resolve_component(kb, query):
    """三级匹配：精确 → 长别名包含 → 最长别名优先。单字别名不参与子串匹配。

    返回 (key, data, ambiguous_list)
    """
    if not query:
        return None, None, []
    q = query.strip()
    comps = kb["components"]
    idx = build_alias_index(kb)

    # 1) 精确匹配（key 或别名）
    if q in comps:
        return q, comps[q], []
    if q in idx:
        cands = idx[q]
        if len(cands) == 1:
            return cands[0], comps[cands[0]], []
        # 歧义：用 tiebreak 表
        pick = AMBIGUOUS_DEFAULT.get(q, cands[0])
        if pick not in cands:
            pick = cands[0]
        others = [c for c in cands if c != pick]
        return pick, comps[pick], others

    # 2) 子串匹配：只用长度 >= 2 的别名，取最长者
    best = None
    best_len = 0
    for a, cands in idx.items():
        if len(a) < 2:
            continue
        if a in q:
            if len(a) > best_len:
                best = a
                best_len = len(a)
    if best:
        cands = idx[best]
        if len(cands) == 1:
            return cands[0], comps[cands[0]], []
        pick = AMBIGUOUS_DEFAULT.get(best, cands[0])
        if pick not in cands:
            pick = cands[0]
        others = [c for c in cands if c != pick]
        return pick, comps[pick], others
    return None, None, []


# ---------------------------------------------------------------- 文本工具
def esc(s):
    return H.escape(str(s if s is not None else ""), quote=False)


def highlight(escaped):
    """把占位符包成红色标记，且不重复包裹已有标记。"""
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return "\x00%d\x00" % (len(stash) - 1)

    tmp = re.sub(r'<span class="todo">.*?</span>', _stash, escaped, flags=re.S)
    tmp = PLACEHOLDER_RE.sub(lambda m: '<span class="todo">%s</span>' % m.group(0), tmp)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], tmp)


def inline(s):
    """转义 + 粗体 **x** + 占位符标红 + 换行。"""
    t = highlight(esc(s))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    return t.replace("\n", "<br>")


def md_inline(s):
    """Markdown 版：仅保留粗体，占位符加醒目符号。"""
    t = str(s if s is not None else "")
    t = PLACEHOLDER_RE.sub(lambda m: "**%s**" % m.group(0), t)
    return t


# ---------------------------------------------------------------- 区块渲染
def render_html(blocks):
    out = []
    for b in blocks:
        t = b["t"]
        if t == "h2":
            out.append("<h2>%s</h2>" % inline(b["text"]))
        elif t == "h3":
            out.append("<h3>%s</h3>" % inline(b["text"]))
        elif t == "p":
            out.append("<p>%s</p>" % inline(b["text"]))
        elif t == "ul":
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(x) for x in b["items"]))
        elif t == "ol":
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(x) for x in b["items"]))
        elif t == "note":
            out.append('<div class="note %s">%s</div>' % (b.get("kind", "info"), inline(b["text"])))
        elif t == "err":
            out.append('<div class="err"><b>%s</b>%s<br><span class="fix">修正：%s</span></div>'
                       % (inline(b["title"]), inline(b["symptom"]), inline(b["fix"])))
        elif t == "pitfalls":
            out.append('<div class="pit"><div class="pit-head">%s</div><ol>%s</ol></div>'
                       % (inline(b.get("title", "本构件专属陷阱")),
                          "".join("<li>%s</li>" % inline(x) for x in b["items"])))
        elif t == "kv":
            out.append("<table class='kv'><tbody>%s</tbody></table>" %
                       "".join("<tr><th>%s</th><td>%s</td></tr>" % (inline(k), inline(v))
                               for k, v in b["rows"]))
        elif t == "table":
            head = "<tr>%s</tr>" % "".join("<th>%s</th>" % inline(h) for h in b["head"])
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                           for r in b["rows"])
            cls = " class='%s'" % b["cls"] if b.get("cls") else ""
            out.append("<table%s><thead>%s</thead><tbody>%s</tbody></table>" % (cls, head, body))
        elif t == "chips":
            out.append('<div class="chips">%s</div>' %
                       "".join('<span class="chip">%s</span>' % inline(x) for x in b["items"]))
        elif t == "steps":
            out.append('<div class="steps">%s</div>' % "".join(
                '<div class="step"><span class="no">%d</span><div>%s</div></div>' % (i, inline(x))
                for i, x in enumerate(b["items"], 1)))
        elif t == "bar":
            out.append('<div class="bar" style="--w:%s">%s</div>' % (b.get("w", 0), inline(b["text"])))
    return "\n".join(out)


def render_md(blocks):
    out = []
    for b in blocks:
        t = b["t"]
        if t == "h2":
            out.append("\n## %s\n" % md_inline(b["text"]))
        elif t == "h3":
            out.append("\n### %s\n" % md_inline(b["text"]))
        elif t == "p":
            out.append("\n%s\n" % md_inline(b["text"]))
        elif t == "ul":
            out.append("\n" + "\n".join("- %s" % md_inline(x) for x in b["items"]) + "\n")
        elif t == "ol":
            out.append("\n" + "\n".join("%d. %s" % (i, md_inline(x)) for i, x in enumerate(b["items"], 1)) + "\n")
        elif t == "note":
            out.append("\n> **%s**：%s\n" % (b.get("kind", "提示"), md_inline(b["text"])))
        elif t == "err":
            out.append("\n- **%s**\n  - 现象：%s\n  - 修正：%s" %
                       (md_inline(b["title"]), md_inline(b["symptom"]), md_inline(b["fix"])))
        elif t == "pitfalls":
            out.append("\n**%s**\n" % md_inline(b.get("title", "本构件专属陷阱")))
            out.append("\n".join("%d. %s" % (i, md_inline(x)) for i, x in enumerate(b["items"], 1)))
            out.append("")
        elif t == "kv":
            out.append("\n| 项目 | 内容 |\n| --- | --- |\n" +
                       "\n".join("| %s | %s |" % (md_inline(k), md_inline(v).replace("\n", " ")) for k, v in b["rows"]) + "\n")
        elif t == "table":
            out.append("\n| " + " | ".join(md_inline(h) for h in b["head"]) + " |")
            out.append("| " + " | ".join(["---"] * len(b["head"])) + " |")
            for r in b["rows"]:
                out.append("| " + " | ".join(md_inline(c).replace("\n", " ") for c in r) + " |")
            out.append("")
        elif t == "chips":
            out.append("\n" + "　".join("`%s`" % md_inline(x) for x in b["items"]) + "\n")
        elif t == "steps":
            out.append("")
            for i, x in enumerate(b["items"], 1):
                out.append("%d. %s" % (i, md_inline(x)))
            out.append("")
    return "\n".join(out)


CSS = """
:root{--fg:#1a1a1a;--muted:#5c6b7a;--line:#dfe5ec;--bg:#fff;--soft:#f6f8fa;
--accent:#1a5fb4;--warn:#b45309;--danger:#b3261e;--ok:#1a7f4b;--chip:#eef3fb;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}
.wrap{max-width:1000px;margin:0 auto;padding:44px 34px 90px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:19px;margin:44px 0 14px;padding:9px 0 9px 13px;border-left:4px solid var(--accent);
background:var(--soft);border-radius:0 5px 5px 0}
h3{font-size:16px;margin:26px 0 10px;color:#243447}
p{margin:9px 0}
ul,ol{margin:9px 0;padding-left:24px}
li{margin:5px 0}
table{border-collapse:collapse;width:100%;margin:13px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600;white-space:nowrap}
table.kv th{width:190px;background:var(--soft)}
tbody tr:nth-child(even){background:#fcfdfe}
.sub{color:var(--muted);font-size:13.5px;margin:0 0 26px}
.todo{color:var(--danger);background:#fdeceb;border-radius:3px;padding:0 3px;font-weight:600}
.note{border-left:3px solid var(--accent);background:#f2f7fd;padding:11px 15px;margin:13px 0;
border-radius:0 5px 5px 0;font-size:14px}
.note.warn{border-color:var(--warn);background:#fdf7ed}
.note.danger{border-color:var(--danger);background:#fdeceb}
.err{border-left:3px solid var(--danger);background:#fdf5f4;padding:10px 14px;margin:9px 0;
border-radius:0 5px 5px 0;font-size:13.5px}
.err b{color:var(--danger)}
.err .fix{color:var(--ok)}
.pit{border:1px solid #f0d0cd;border-left:4px solid var(--danger);background:#fdf7f6;
border-radius:0 6px 6px 0;padding:12px 16px;margin:13px 0}
.pit-head{font-weight:600;color:var(--danger);margin-bottom:4px}
.pit ol{margin:4px 0 0;padding-left:22px}
.pit li{margin:4px 0;font-size:13.8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}
.chip{background:var(--chip);color:#1a3d63;border-radius:5px;padding:3px 10px;font-size:13px}
.steps{margin:13px 0}
.step{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px}
.step:last-child{border-bottom:none}
.step .no{flex:0 0 25px;height:25px;line-height:25px;text-align:center;background:var(--accent);
color:#fff;border-radius:50%;font-size:12.5px;font-weight:600}
.tag{display:inline-block;background:var(--chip);color:#1a3d63;border-radius:4px;
padding:1px 8px;font-size:12.5px;margin-right:5px}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
color:var(--muted);font-size:12.5px}
@media print{body{font-size:11.5px}.wrap{padding:0;max-width:100%}h2{page-break-after:avoid}
table,.err,.note{page-break-inside:avoid}}
"""


def page(title, subtitle, blocks):
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>%s</style></head><body><div class="wrap">
<h1>%s</h1><p class="sub">%s</p>
%s
<footer>本方案由「BIM 工程量统计助手」生成。数值与系数须结合本项目设计文件、合同计量条款与现行规范复核后使用；
标注为「估算量」的内容不得直接用于报价。</footer>
</div></body></html>""" % (esc(title), CSS, esc(title), inline(subtitle), render_html(blocks))


# ---------------------------------------------------------------- 方案主体
PATH_LABEL = {"A": "路径A·Revit直出", "B": "路径B·共享参数+Dynamo",
              "C": "路径C·对接算量软件", "D": "路径D·规则换算表"}


def build_component_blocks(kb, std, key, comp, project, name, ambiguous):
    B = []
    A = B.append

    A({"t": "kv", "rows": [
        ("构件类型", comp["name"]),
        ("所属专业", comp.get("discipline", "—")),
        ("Revit 族类别", " / ".join(comp.get("revit_categories", []))),
        ("明细表类型", comp.get("schedule_type", "—")),
        ("常用别名", "、".join(comp.get("aliases", [])[:16])),
    ]})

    if comp.get("intro"):
        A({"t": "note", "kind": "warn", "text": comp["intro"]})

    if ambiguous:
        names = "、".join(kb["components"][x]["name"] for x in ambiguous)
        A({"t": "note", "kind": "warn",
           "text": "「%s」这个说法在库中同时挂在多个构件类型上（本方案取「%s」）。若你要统计的是：%s，"
                   "请改用该构件的标准名重新生成本方案——不同构件的计量单位与清单口径可能完全不同。"
                   % (name, comp["name"], names)})

    # ---------- 1
    A({"t": "h2", "text": "一、构件定位与统计概要"})
    A({"t": "p", "text": comp.get("bim_vs_boq", "")})
    A({"t": "h3", "text": "本构件需要提供的工程量"})
    A({"t": "table", "head": ["计量项", "单位", "取量来源"],
       "rows": [[q["item"], q["unit"], q["source"]] for q in comp.get("quantity_items", [])]})

    # ---------- 2
    A({"t": "h2", "text": "二、Revit 明细表创建步骤"})
    A({"t": "note", "kind": "info",
       "text": "明细表所做的一切只是「读」模型。模型本身的缺陷（类别错、材质空、房间缺失）无法靠明细表技巧修正——"
               "因此第一阶段的模型条件检查必须在出量前完成。"})
    for ph in std["schedule_steps"]:
        A({"t": "h3", "text": ph["phase"]})
        A({"t": "p", "text": ph["goal"]})
        A({"t": "steps", "items": ph["items"]})

    A({"t": "h3", "text": "本构件的专属明细表配置"})
    A({"t": "table", "head": ["配置项", "内容"], "rows": [
        ("明细表类型", comp.get("schedule_type", "—")),
        ("Revit 族类别", " / ".join(comp.get("revit_categories", []))),
    ]})
    if comp.get("filters"):
        A({"t": "h3", "text": "过滤器设置"})
        A({"t": "ul", "items": comp["filters"]})
    if comp.get("group_sort"):
        A({"t": "h3", "text": "排序与分组"})
        A({"t": "ul", "items": comp["group_sort"]})
    if comp.get("calculated_values"):
        A({"t": "h3", "text": "计算值"})
        A({"t": "table", "head": ["计算值名称", "公式", "说明"],
           "rows": [[c["name"], c["formula"], c["note"]] for c in comp["calculated_values"]]})

    # ---------- 3
    A({"t": "h2", "text": "三、参数字段清单"})
    A({"t": "table", "head": ["字段", "单位", "为什么需要它"],
       "rows": [[f["name"], f["unit"], f["why"]] for f in comp.get("key_fields", [])]})
    A({"t": "note", "kind": "warn",
       "text": "「字段」的顺序就是明细表中列的先后顺序，先加分组键（族与类型），再加主计量字段，最后加辅助核对字段。"})

    # ---------- 4
    A({"t": "h2", "text": "四、工程量提取方法"})
    A({"t": "h3", "text": "本构件的提取要点"})
    A({"t": "steps", "items": comp.get("extraction", [])})
    A({"t": "h3", "text": "四条取量路径对比"})
    A({"t": "table", "head": ["路径", "做法", "优势", "局限", "适用"],
       "rows": [[m["path"], m["how"], m["strength"], m["weakness"], m["fit"]]
                for m in std["extraction_methods"]]})
    A({"t": "note", "kind": "info", "text": std["extraction_methods_note"]})

    # ---------- 5
    A({"t": "h2", "text": "五、成本关联方式"})
    A({"t": "h3", "text": "本构件的关联做法"})
    for c in comp.get("cost_link", []):
        A({"t": "p", "text": "**%s** —— %s" % (c["way"], c["how"]) + ("（%s）" % c["note"] if c.get("note") else "")})
    A({"t": "h3", "text": "五条通用关联路径"})
    A({"t": "table", "head": ["方式", "做法", "前提/要求", "易错点"],
       "rows": [[w["way"], w["detail"], w["requirement"], w["pitfall"]]
                for w in std["cost_linkage_paths"]]})
    A({"t": "note", "kind": "info", "text": std["cost_linkage_note"]})
    A({"t": "h3", "text": "需要建立的共享参数"})
    A({"t": "table", "head": ["参数", "类型", "作用范围", "用途"],
       "rows": [[p["name"], p["type"], p["scope"], p["why"]] for p in std["unit_price_reference"]["parameters"]]})
    A({"t": "note", "kind": "warn", "text": std["unit_price_reference"]["note"]})

    # ---------- 6
    A({"t": "h2", "text": "六、BIM 量 vs 清单量：口径差异"})
    A({"t": "note", "kind": "danger", "text": kb["meta"]["core_caveat"]})
    A({"t": "p", "text": comp.get("bim_vs_boq", "")})
    A({"t": "h3", "text": "本构件对应的计量规则依据"})
    A({"t": "p", "text": comp.get("gb_rule", "—")})
    A({"t": "h3", "text": "标准依据清单（本方案引用的计量规范原文要点）"})
    A({"t": "note", "kind": "info",
       "text": "以下为各规范中与工程量计量直接相关的条款要点。引用规范时必须核到条款，"
               "「按规范计算」而不指明哪一条，在争议中不构成依据。"})
    A({"t": "table", "head": ["标准号", "名称", "覆盖范围", "关键条款要点"],
       "rows": [[b["code"], b["name"], b["covers"],
                 "\n".join("· " + x for x in b["key_points"])]
                for b in std["standards_basis"]]})
    A({"t": "h3", "text": "分类型偏差基准值"})
    A({"t": "table", "head": ["构件类型", "正常", "需关注", "重大", "原因"],
       "rows": [[b["component"], b["normal"], b["warn"], b["critical"], b["reason"]]
                for b in std["deviation_baseline"]]})
    A({"t": "note", "kind": "warn", "text": std["deviation_baseline_note"]})

    # ---------- 7
    A({"t": "h2", "text": "七、常见错误提醒"})
    A({"t": "h3", "text": "本构件专属陷阱"})
    A({"t": "pitfalls", "title": "%s —— 这类构件最常出问题的地方" % comp["name"],
       "items": comp.get("pitfalls", [])})
    for g in std["common_errors"]["groups"]:
        A({"t": "h3", "text": g["group"]})
        for e in g["errors"]:
            A({"t": "err", "title": e["err"], "symptom": "现象：" + e["symptom"], "fix": e["fix"]})
    A({"t": "note", "kind": "info", "text": std["common_errors"]["note"]})

    # ---------- 8
    A({"t": "h2", "text": "八、工程量偏差分析报告模板"})
    A({"t": "note", "kind": "info", "text": std["deviation_template"]["note"]})
    for s in std["deviation_template"]["sections"]:
        A({"t": "h3", "text": "%s. %s" % (s["no"], s["name"])})
        A({"t": "ul", "items": s["fields"]})
        A({"t": "note", "kind": "info", "text": s["hint"]})
    A({"t": "h3", "text": "偏差原因分类（六类）"})
    for c in std["deviation_causes"]:
        A({"t": "table", "head": ["%s · 现象" % c["category"], "偏差方向", "量级", "责任归属", "处理方式"],
           "rows": [[i["phenomenon"], i["direction"], i["magnitude"], i["owner"], i["action"]]
                    for i in c["items"]]})

    # ---------- 9
    A({"t": "h2", "text": "九、检查清单"})
    A({"t": "note", "kind": "info", "text": std["checklist"]["note"]})
    A({"t": "h3", "text": "本构件专属检查点"})
    A({"t": "ol", "items": comp.get("checkpoints", [])})
    for sec in std["checklist"]["sections"]:
        A({"t": "h3", "text": sec["title"]})
        A({"t": "ol", "items": sec["items"]})
    A({"t": "h3", "text": "出量前 QA 检查"})
    A({"t": "ol", "items": std["qa_checklist"]["items"]})

    return B


def build_checklist_md(kb, std, comp, name):
    L = []
    A = L.append
    A("# %s · 工程量统计检查清单\n" % name)
    A("> 构件类型：%s　|　专业：%s\n" % (comp["name"], comp.get("discipline", "—")))
    A("> 使用方式：逐项勾选。第一节是「模型能不能出量」的前提，后面按工作流顺序排列。\n")
    A("## 本构件专属检查点\n")
    for c in comp.get("checkpoints", []):
        A("- [ ] %s" % md_inline(c))
    A("")
    for sec in std["checklist"]["sections"]:
        A("## %s\n" % sec["title"])
        for i in sec["items"]:
            A("- [ ] %s" % md_inline(i))
        A("")
    A("## 出量前 QA 检查\n")
    A("> %s\n" % std["qa_checklist"]["intro"])
    for i in std["qa_checklist"]["items"]:
        A("- [ ] %s" % md_inline(i))
    A("")
    A("## 本构件专属陷阱（提醒用）\n")
    for p in comp.get("pitfalls", []):
        A("- %s" % md_inline(p))
    A("")
    A("## 偏差分析报告必备章节\n")
    for s in std["deviation_template"]["sections"]:
        A("- [ ] %s. %s" % (s["no"], s["name"]))
    A("")
    return "\n".join(L)


# ---------------------------------------------------------------- 模板
def template_blocks(std, which):
    B = []
    A = B.append
    if which in ("all", "checklist"):
        A({"t": "h2", "text": "一、检查清单（空白，逐项勾选）"})
        A({"t": "note", "kind": "info", "text": std["checklist"]["note"]})
        for sec in std["checklist"]["sections"]:
            A({"t": "h3", "text": sec["title"]})
            A({"t": "ol", "items": sec["items"]})
        A({"t": "h3", "text": "出量前 QA 检查（导出前必做）"})
        A({"t": "p", "text": std["qa_checklist"]["intro"]})
        A({"t": "ol", "items": std["qa_checklist"]["items"]})
    if which in ("all", "deviation"):
        A({"t": "h2", "text": "二、工程量偏差分析报告模板（空白待填）"})
        A({"t": "note", "kind": "info", "text": std["deviation_template"]["note"]})
        for s in std["deviation_template"]["sections"]:
            A({"t": "h3", "text": "%s. %s" % (s["no"], s["name"])})
            A({"t": "ul", "items": s["fields"]})
            A({"t": "note", "kind": "info", "text": s["hint"]})
        A({"t": "h3", "text": "附：分类型偏差基准值（判读用）"})
        A({"t": "table", "head": ["构件类型", "正常", "需关注", "重大", "原因"],
           "rows": [[b["component"], b["normal"], b["warn"], b["critical"], b["reason"]]
                    for b in std["deviation_baseline"]]})
        A({"t": "note", "kind": "warn", "text": std["deviation_baseline_note"]})
    return B


def template_md(std, which):
    L = []
    A = L.append
    if which in ("all", "checklist"):
        A("# BIM 工程量统计检查清单（模板）\n")
        A("> %s\n" % std["checklist"]["note"])
        for sec in std["checklist"]["sections"]:
            A("## %s\n" % sec["title"])
            for i in sec["items"]:
                A("- [ ] %s" % md_inline(i))
            A("")
        A("## 出量前 QA 检查\n")
        A("> %s\n" % std["qa_checklist"]["intro"])
        for i in std["qa_checklist"]["items"]:
            A("- [ ] %s" % md_inline(i))
        A("")
    if which in ("all", "deviation"):
        A("\n# 工程量偏差分析报告（模板）\n")
        A("> %s\n" % std["deviation_template"]["note"])
        for s in std["deviation_template"]["sections"]:
            A("## %s. %s\n" % (s["no"], s["name"]))
            for f in s["fields"]:
                A("- [ ] %s" % md_inline(f))
            A("")
            A("> 提示：%s\n" % md_inline(s["hint"]))
        A("\n## 附：分类型偏差基准值（判读用）\n")
        A("> %s\n" % md_inline(std["deviation_baseline_note"]))
        A("| 构件类型 | 正常 | 需关注 | 重大 | 原因 |")
        A("| --- | --- | --- | --- | --- |")
        for b in std["deviation_baseline"]:
            A("| %s | %s | %s | %s | %s |" %
              (md_inline(b["component"]), b["normal"], b["warn"], b["critical"], md_inline(b["reason"])))
        A("")
    return "\n".join(L)


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="BIM 工程量统计方案生成器")
    ap.add_argument("--list", action="store_true", help="列出构件库")
    ap.add_argument("--component", help="构件类型（支持别名）")
    ap.add_argument("--input", help="自定义 JSON 输入")
    ap.add_argument("--template", nargs="?", const="all", choices=["all", "checklist", "deviation"],
                    help="输出空白模板")
    ap.add_argument("--project", default="", help="项目名称")
    ap.add_argument("--name", default="", help="输出文件名前缀")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--json-only", action="store_true", help="仅输出 JSON 结果")
    args = ap.parse_args()

    kb, std = load_assets()

    if args.list:
        res = {"ok": True, "count": len(kb["components"]),
               "core_caveat": kb["meta"]["core_caveat"],
               "components": [{"key": k, "name": v["name"], "discipline": v.get("discipline", "—"),
                               "aliases": len(v.get("aliases", [])),
                               "fields": len(v.get("key_fields", [])),
                               "pitfalls": len(v.get("pitfalls", [])),
                               "checkpoints": len(v.get("checkpoints", []))}
                              for k, v in kb["components"].items()],
               "generic_fallback": bool(kb.get("generic_fallback")),
               "checklist_items": sum(len(s["items"]) for s in std["checklist"]["sections"]),
               "deviation_sections": len(std["deviation_template"]["sections"]),
               "deviation_causes": sum(len(g["items"]) for g in std["deviation_causes"]),
               "common_errors": sum(len(g["errors"]) for g in std["common_errors"]["groups"])}
        if args.json_only:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("构件类型库：%d 类" % res["count"])
            for c in res["components"]:
                print("  %-18s %-24s %s | 字段%2d 陷阱%2d 检查%2d | 别名%d"
                      % (c["key"], c["name"][:24], c["discipline"], c["fields"],
                         c["pitfalls"], c["checkpoints"], c["aliases"]))
            print("通用回退：%s" % ("有" if res["generic_fallback"] else "无"))
            print("检查清单 %d 项 | 偏差报告 %d 章 | 偏差原因 %d 条 | 常见错误 %d 条"
                  % (res["checklist_items"], res["deviation_sections"],
                     res["deviation_causes"], res["common_errors"]))
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    files = []

    # --- 模板模式 ---
    if args.template:
        which = args.template
        if which == "checklist":
            title = "BIM 工程量统计检查清单"
        elif which == "deviation":
            title = "工程量偏差分析报告模板"
        else:
            title = "BIM 工程量统计检查清单与偏差分析报告模板"
        base = args.name or title
        B = template_blocks(std, which)
        h = os.path.join(args.outdir, base + ".html")
        m = os.path.join(args.outdir, base + ".md")
        open(h, "w", encoding="utf-8", newline="\n").write(page(title, args.project or "空白模板，待填写", B))
        open(m, "w", encoding="utf-8", newline="\n").write(template_md(std, which))
        files = [h, m]
        if args.json_only:
            print(json.dumps({"ok": True, "mode": "template", "which": which, "files": files},
                             ensure_ascii=False, indent=2))
        else:
            print("已生成模板：%s（%d 章 / %d 项）" %
                  (which, len(B), sum(len(b.get("items", [])) for b in B)))
            for f in files:
                print("  ", f)
        return 0

    # --- 确定构件与名称 ---
    if args.input:
        payload = json.load(open(args.input, encoding="utf-8"))
        comp_name = payload.get("component", "")
        project = payload.get("project_name") or args.project
        name = args.name or payload.get("name") or (project + "_" + comp_name if project else comp_name)
        key, comp, amb = resolve_component(kb, comp_name)
        if comp is None:
            comp = dict(kb["generic_fallback"])
            for k, v in payload.items():
                if k in comp and isinstance(v, type(comp[k])):
                    comp[k] = v
            key, amb = None, []
    elif args.component:
        key, comp, amb = resolve_component(kb, args.component)
        project = args.project
        if comp is None:
            comp = dict(kb["generic_fallback"])
        name = args.name or (project + "_" + args.component if project else args.component)
    else:
        print("请指定 --component / --input / --template / --list", file=sys.stderr)
        return 2

    title = "%s · 工程量统计方案" % (comp["name"])
    blocks = build_component_blocks(kb, std, key, comp, project, args.component or comp["name"], amb)

    base = name
    h = os.path.join(args.outdir, base + "_工程量统计方案.html")
    m = os.path.join(args.outdir, base + "_工程量统计方案.md")
    c = os.path.join(args.outdir, base + "_工程量统计检查清单.md")
    sub = "%s　|　构件类型：%s　|　专业：%s" % (project or "〔项目名称〕", comp["name"], comp.get("discipline", "—"))
    open(h, "w", encoding="utf-8", newline="\n").write(page(title, sub, blocks))
    open(m, "w", encoding="utf-8", newline="\n").write(
        "# %s\n\n> %s\n\n" % (title, md_inline(sub)) + render_md(blocks))
    open(c, "w", encoding="utf-8", newline="\n").write(build_checklist_md(kb, std, comp, base))
    files = [h, m, c]

    if args.json_only:
        print(json.dumps({
            "ok": True,
            "component": comp["name"],
            "component_key": key,
            "component_in_library": key is not None,
            "ambiguous_with": [kb["components"][x]["name"] for x in amb],
            "discipline": comp.get("discipline", "—"),
            "schedule_type": comp.get("schedule_type", "—"),
            "fields": len(comp.get("key_fields", [])),
            "quantity_items": len(comp.get("quantity_items", [])),
            "extraction": len(comp.get("extraction", [])),
            "cost_link": len(comp.get("cost_link", [])),
            "pitfalls": len(comp.get("pitfalls", [])),
            "checkpoints": len(comp.get("checkpoints", [])),
            "checklist_items": len(comp.get("checkpoints", [])) +
                               sum(len(s["items"]) for s in std["checklist"]["sections"]),
            "deviation_sections": len(std["deviation_template"]["sections"]),
            "blocks": len(blocks),
            "files": files,
        }, ensure_ascii=False, indent=2))
    else:
        print("构件：%s（%s）" % (comp["name"], comp.get("discipline", "—")))
        if amb:
            print("  注意：该说法在库中挂多个构件，已取本构件；备选：" +
                  "、".join(kb["components"][x]["name"] for x in amb))
        print("  字段 %d | 计量项 %d | 提取要点 %d | 计价做法 %d | 陷阱 %d | 检查点 %d"
              % (len(comp.get("key_fields", [])), len(comp.get("quantity_items", [])),
                 len(comp.get("extraction", [])), len(comp.get("cost_link", [])),
                 len(comp.get("pitfalls", [])), len(comp.get("checkpoints", []))))
        print("  方案区块 %d" % len(blocks))
        for f in files:
            print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
