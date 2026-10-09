# -*- coding: utf-8 -*-
"""BIM 答辩 PPT 生成器

用法：
  defense_builder.py --list
  defense_builder.py --direction 铀矿巷道 --project "XX铀矿巷道工程" \
      --achievements "巷道全长3.2km|碰撞解决47处|4D优化工期12天" \
      --innovations "自建巷道参数化族|通风与辐射分区联动" --minutes 15 -o out
  defense_builder.py --input data.json -o out
  defense_builder.py --template [all|outline|qa|prep] -o out
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

PRI_CLASS = {"必有": "must", "加分": "plus", "可选": "opt"}


# ---------------------------------------------------------------- 载入
def load_assets():
    kb = json.load(open(os.path.join(ASSETS, "defense_kb.json"), encoding="utf-8"))
    qb = json.load(open(os.path.join(ASSETS, "qa_bank.json"), encoding="utf-8"))
    return kb, qb


def build_alias_index(kb):
    idx = {}
    for k, v in kb["directions"].items():
        for a in [k, v["name"]] + list(v.get("aliases", [])):
            idx.setdefault(a, [])
            if k not in idx[a]:
                idx[a].append(k)
    return idx


def resolve_direction(kb, query):
    """三级匹配：精确 → 长别名包含 → 最长别名优先。单字别名不参与子串匹配。

    返回 (key, data, ambiguous_list)；未命中返回 (None, None, [])
    """
    if not query:
        return None, None, []
    q = query.strip()
    dirs = kb["directions"]
    idx = build_alias_index(kb)

    if q in dirs:
        return q, dirs[q], []
    if q in idx:
        cands = idx[q]
        if len(cands) == 1:
            return cands[0], dirs[cands[0]], []
        return cands[0], dirs[cands[0]], [c for c in cands if c != cands[0]]

    best, best_len = None, 0
    for a, cands in idx.items():
        if len(a) < 2:
            continue
        if a in q and len(a) > best_len:
            best, best_len = a, len(a)
    if best:
        cands = idx[best]
        if len(cands) == 1:
            return cands[0], dirs[cands[0]], []
        return cands[0], dirs[cands[0]], [c for c in cands if c != cands[0]]
    return None, None, []


# ---------------------------------------------------------------- 文本工具
def esc(s):
    return H.escape(str(s if s is not None else ""), quote=False)


def highlight(escaped):
    """占位符标红，且不重复包裹已有标记。"""
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return "\x00%d\x00" % (len(stash) - 1)

    tmp = re.sub(r'<span class="todo">.*?</span>', _stash, escaped, flags=re.S)
    tmp = PLACEHOLDER_RE.sub(lambda m: '<span class="todo">%s</span>' % m.group(0), tmp)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], tmp)


def inline(s):
    t = highlight(esc(s))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    return t.replace("\n", "<br>")


def md_inline(s):
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
        elif t == "tip":
            out.append('<div class="tip"><b>%s</b>%s</div>' % (inline(b.get("title", "提示")), inline(b["text"])))
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
        elif t == "pagecard":
            pri = b.get("pri", "")
            pc = ['<div class="pagecard" id="%s">' % ("pc-" + b["no"].replace("附录", "app"))]
            pc.append('<div class="pc-head"><span class="pc-no">%s</span>'
                      '<span class="pc-title">%s</span>'
                      '<span class="pc-pri %s">%s</span>'
                      '<span class="pc-time">%s</span></div>'
                      % (inline(b["no"]), inline(b["title"]),
                         PRI_CLASS.get(pri, "opt"), inline(pri), inline(b.get("time", ""))))
            pc.append('<div class="pc-role">这一页的任务：%s</div>' % inline(b.get("role", "")))
            pc.append('<div class="pc-grid">')
            pc.append('<div><div class="pc-h">内容要点</div><ul>%s</ul></div>'
                      % "".join("<li>%s</li>" % inline(x) for x in b.get("points", [])))
            pc.append('<div><div class="pc-h note-h">演讲备注</div><ul>%s</ul></div>'
                      % "".join("<li>%s</li>" % inline(x) for x in b.get("notes", [])))
            pc.append("</div>")
            if b.get("must"):
                pc.append('<div class="pc-must">必备：%s</div>'
                          % "、".join(inline(x) for x in b["must"]))
            if b.get("visual"):
                pc.append('<div class="pc-visual">视觉建议：%s</div>' % inline(b["visual"]))
            if b.get("traps"):
                pc.append('<div class="pc-traps"><div class="pc-h trap-h">常见失误</div><ul>%s</ul></div>'
                          % "".join("<li>%s</li>" % inline(x) for x in b["traps"]))
            pc.append("</div>")
            out.append("\n".join(pc))
        elif t == "qa":
            out.append(
                '<div class="qa"><div class="q"><span class="qmark">问</span>%s</div>'
                '<div class="qa-row"><span class="qa-k">提问意图</span><span class="qa-v">%s</span></div>'
                '<div class="qa-row"><span class="qa-k ok">回答框架</span><span class="qa-v">%s</span></div>'
                '%s%s</div>'
                % (inline(b["q"]), inline(b["intent"]), inline(b["answer"]),
                   ('<div class="qa-row"><span class="qa-k warn">陷阱</span><span class="qa-v">%s</span></div>'
                    % inline(b["trap"])) if b.get("trap") else "",
                   ('<div class="qa-row"><span class="qa-k">可能追问</span><span class="qa-v">%s</span></div>'
                    % inline(b["follow"])) if b.get("follow") else ""))
        elif t == "specpage":
            out.append('<div class="spec"><div class="spec-h">%s</div>'
                       '<div class="spec-role">%s</div>'
                       '<div class="spec-body"><div><div class="pc-h">内容要点</div><ul>%s</ul></div>'
                       '<div><div class="pc-h note-h">演讲备注</div><ul>%s</ul></div></div></div>'
                       % (inline(b["title"]), inline(b.get("role", "")),
                          "".join("<li>%s</li>" % inline(x) for x in b.get("points", [])),
                          "".join("<li>%s</li>" % inline(x) for x in b.get("notes", []))))
        elif t == "err":
            out.append('<div class="err"><b>%s</b><div class="err-why">%s</div>'
                       '<div class="err-fix">修正：%s</div></div>'
                       % (inline(b["err"]), inline(b["why"]), inline(b["fix"])))
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
        elif t == "tip":
            out.append("\n> **%s**　%s\n" % (md_inline(b.get("title", "提示")), md_inline(b["text"])))
        elif t == "kv":
            out.append("\n| 项目 | 内容 |\n| --- | --- |\n" +
                       "\n".join("| %s | %s |" % (md_inline(k), md_inline(v).replace("\n", " "))
                                 for k, v in b["rows"]) + "\n")
        elif t == "table":
            out.append("\n| " + " | ".join(md_inline(h) for h in b["head"]) + " |")
            out.append("| " + " | ".join(["---"] * len(b["head"])) + " |")
            for r in b["rows"]:
                out.append("| " + " | ".join(md_inline(c).replace("\n", "<br>") for c in r) + " |")
            out.append("")
        elif t == "chips":
            out.append("\n" + "　".join("`%s`" % md_inline(x) for x in b["items"]) + "\n")
        elif t == "steps":
            out.append("")
            for i, x in enumerate(b["items"], 1):
                out.append("%d. %s" % (i, md_inline(x)))
            out.append("")
        elif t == "pagecard":
            out.append("\n---\n\n### %s %s　【%s】%s\n" % (md_inline(b["no"]), md_inline(b["title"]),
                                                          md_inline(b.get("pri", "")), md_inline(b.get("time", ""))))
            out.append("**这一页的任务**：%s\n" % md_inline(b.get("role", "")))
            out.append("**内容要点**\n")
            out.append("\n".join("- %s" % md_inline(x) for x in b.get("points", [])))
            out.append("\n\n**演讲备注**\n")
            out.append("\n".join("- %s" % md_inline(x) for x in b.get("notes", [])))
            if b.get("must"):
                out.append("\n\n**必备**：%s" % "、".join(md_inline(x) for x in b["must"]))
            if b.get("visual"):
                out.append("\n\n**视觉建议**：%s" % md_inline(b["visual"]))
            if b.get("traps"):
                out.append("\n\n**常见失误**\n")
                out.append("\n".join("- %s" % md_inline(x) for x in b["traps"]))
            out.append("")
        elif t == "qa":
            out.append("\n#### 问：%s\n" % md_inline(b["q"]))
            out.append("- **提问意图**：%s" % md_inline(b["intent"]))
            out.append("- **回答框架**：%s" % md_inline(b["answer"]))
            if b.get("trap"):
                out.append("- **陷阱**：%s" % md_inline(b["trap"]))
            if b.get("follow"):
                out.append("- **可能追问**：%s" % md_inline(b["follow"]))
            out.append("")
        elif t == "specpage":
            out.append("\n### %s\n" % md_inline(b["title"]))
            out.append("> %s\n" % md_inline(b.get("role", "")))
            out.append("**内容要点**\n")
            out.append("\n".join("- %s" % md_inline(x) for x in b.get("points", [])))
            out.append("\n\n**演讲备注**\n")
            out.append("\n".join("- %s" % md_inline(x) for x in b.get("notes", [])))
            out.append("")
        elif t == "err":
            out.append("\n- **%s**\n  - 原因：%s\n  - 修正：%s" %
                       (md_inline(b["err"]), md_inline(b["why"]), md_inline(b["fix"])))
    return "\n".join(out)


CSS = """
:root{--fg:#1a1a1a;--muted:#5c6b7a;--line:#dfe5ec;--bg:#fff;--soft:#f6f8fa;
--accent:#1a5fb4;--warn:#b45309;--danger:#b3261e;--ok:#1a7f4b;--chip:#eef3fb;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}
.wrap{max-width:1040px;margin:0 auto;padding:44px 34px 90px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:19px;margin:46px 0 14px;padding:9px 0 9px 13px;border-left:4px solid var(--accent);
background:var(--soft);border-radius:0 5px 5px 0}
h3{font-size:16px;margin:26px 0 10px;color:#243447}
p{margin:9px 0}
ul,ol{margin:9px 0;padding-left:24px}
li{margin:5px 0}
table{border-collapse:collapse;width:100%;margin:13px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600}
table.kv th{width:150px;background:var(--soft);white-space:nowrap}
tbody tr:nth-child(even){background:#fcfdfe}
.sub{color:var(--muted);font-size:13.5px;margin:0 0 26px}
.todo{color:var(--danger);background:#fdeceb;border-radius:3px;padding:0 3px;font-weight:600}
.note{border-left:3px solid var(--accent);background:#f2f7fd;padding:11px 15px;margin:13px 0;
border-radius:0 5px 5px 0;font-size:14px}
.note.warn{border-color:var(--warn);background:#fdf7ed}
.note.danger{border-color:var(--danger);background:#fdeceb}
.tip{border:1px solid #e3ebf5;background:#fbfdff;border-radius:6px;padding:11px 15px;margin:13px 0;font-size:14px}
.tip b{color:var(--accent);margin-right:6px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}
.chip{background:var(--chip);color:#1a3d63;border-radius:5px;padding:3px 10px;font-size:13px}
.steps{margin:13px 0}
.step{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px}
.step:last-child{border-bottom:none}
.step .no{flex:0 0 25px;height:25px;line-height:25px;text-align:center;background:var(--accent);
color:#fff;border-radius:50%;font-size:12.5px;font-weight:600}
/* ---- 页面卡片 ---- */
.pagecard{border:1px solid var(--line);border-radius:8px;margin:16px 0;overflow:hidden;background:#fff}
.pc-head{display:flex;align-items:center;gap:9px;padding:9px 14px;background:var(--soft);
border-bottom:1px solid var(--line);flex-wrap:wrap}
.pc-no{background:var(--accent);color:#fff;border-radius:5px;padding:2px 9px;font-size:12.5px;font-weight:600}
.pc-title{font-weight:600;font-size:15.5px}
.pc-pri{border-radius:4px;padding:1px 8px;font-size:12px;margin-left:auto}
.pc-pri.must{background:#e7f3ec;color:var(--ok)}
.pc-pri.plus{background:#fdf4e6;color:var(--warn)}
.pc-pri.opt{background:#eef1f4;color:var(--muted)}
.pc-time{font-size:12.5px;color:var(--accent);font-weight:600}
.pc-role{padding:10px 14px 0;font-size:13.8px;color:#3a4a5a}
.pc-grid{display:grid;grid-template-columns:1fr 1fr;gap:0;padding:8px 14px 4px}
.pc-grid>div{padding-right:14px}
.pc-grid>div+div{border-left:1px dashed var(--line);padding-left:14px;padding-right:0}
.pc-h{font-weight:600;font-size:13px;color:var(--accent);margin:6px 0 4px}
.pc-h.note-h{color:var(--ok)}
.pc-h.trap-h{color:var(--danger)}
.pc-grid ul,.pc-traps ul{margin:4px 0;padding-left:20px}
.pc-grid li,.pc-traps li{font-size:13.3px;margin:4px 0}
.pc-must{padding:6px 14px;font-size:13px;color:var(--ok);background:#f4faf6;border-top:1px dashed var(--line)}
.pc-visual{padding:6px 14px;font-size:13px;color:#3a4a5a}
.pc-traps{padding:6px 14px 10px;background:#fdf9f8;border-top:1px dashed #f0d0cd}
/* ---- 方向专属页 ---- */
.spec{border:1px solid #e0e8f2;border-left:4px solid var(--accent);border-radius:0 8px 8px 0;
margin:16px 0;padding:12px 16px;background:#fbfdff}
.spec-h{font-weight:600;font-size:15.5px;color:#123c6b}
.spec-role{font-size:13.3px;color:var(--muted);margin:4px 0 8px}
.spec-body{display:grid;grid-template-columns:1fr 1fr;gap:0}
.spec-body>div{padding-right:14px}
.spec-body>div+div{border-left:1px dashed var(--line);padding-left:14px;padding-right:0}
.spec-body ul{margin:4px 0;padding-left:20px}
.spec-body li{font-size:13.3px;margin:4px 0}
/* ---- 问答卡片 ---- */
.qa{border:1px solid var(--line);border-radius:8px;margin:14px 0;padding:0 0 10px;overflow:hidden}
.qa .q{padding:10px 14px;background:#f4f7fc;font-weight:600;font-size:14.5px;color:#123c6b}
.qa .qmark{background:var(--accent);color:#fff;border-radius:4px;padding:1px 7px;
font-size:12px;margin-right:8px;vertical-align:1px}
.qa-row{display:flex;gap:9px;padding:5px 14px;font-size:13.4px}
.qa-k{flex:0 0 62px;color:var(--muted);font-size:12.5px;padding-top:2px}
.qa-k.ok{color:var(--ok);font-weight:600}
.qa-k.warn{color:var(--danger);font-weight:600}
.qa-v{flex:1}
.err{border-left:3px solid var(--danger);background:#fdf5f4;padding:10px 14px;margin:9px 0;
border-radius:0 5px 5px 0;font-size:13.5px}
.err b{color:var(--danger)}
.err-why{color:#4a3a38;margin-top:2px}
.err-fix{color:var(--ok);margin-top:3px}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
color:var(--muted);font-size:12.5px}
@media print{body{font-size:11.5px}.wrap{padding:0;max-width:100%}h2{page-break-after:avoid}
.pagecard,.spec,.qa,.note,.tip,.err{page-break-inside:avoid}
.pc-grid,.spec-body{grid-template-columns:1fr 1fr}}
"""


def page(title, subtitle, blocks):
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>%s</style></head><body><div class="wrap">
<h1>%s</h1><p class="sub">%s</p>
%s
<footer>本方案由「BIM 答辩 PPT 生成助手」生成。时间分配、提问预案与量化指标均为经验参考，
须结合本校答辩要求、项目实际数据与导师意见复核后使用；标注〔待补充〕的内容必须由你本人填实。</footer>
</div></body></html>""" % (esc(title), CSS, esc(title), inline(subtitle), render_html(blocks))


# ---------------------------------------------------------------- 时间分配
def alloc_time(pages, total_minutes):
    ws = sum(p.get("weight", 0) for p in pages)
    res = {}
    if ws <= 0:
        return res
    for p in pages:
        w = p.get("weight", 0)
        res[p["key"]] = 0.0 if w == 0 else round(w / ws * total_minutes, 1)
    return res


def fmt_min(m):
    if m == 0:
        return "不讲（备查）"
    if m < 1:
        return "%d 秒" % int(round(m * 60))
    return "%.1f 分钟" % m


# ---------------------------------------------------------------- 主体
def parse_list(v):
    if not v:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            out.extend(parse_list(x))
        return out
    parts = re.split(r"[|；;\n]+", str(v))
    return [p.strip() for p in parts if p.strip()]


def select_five(direction, qb):
    """5 个最可能被问的问题：方向高频追问（最多 4 条）+ 通用最高频 1 条"""
    sel = []
    for q in direction.get("hot_questions", [])[:4]:
        sel.append(q)
    # 通用最高频：创新点
    for c in qb["categories"]:
        if c["key"] == "innovation":
            for q in c["questions"]:
                if "创新点" in q["q"]:
                    sel.append(q)
                    break
            break
    # 若不足 5 条，用 reflection 类补齐
    if len(sel) < 5:
        for c in qb["categories"]:
            if c["key"] == "reflection":
                for q in c["questions"]:
                    if len(sel) >= 5:
                        break
                    sel.append(q)
        # 再去 background 补
        for c in qb["categories"]:
            if c["key"] == "background":
                for q in c["questions"]:
                    if len(sel) >= 5:
                        break
                    sel.append(q)
    return sel[:5]


def build_blocks(kb, qb, key, d, project, achievements, innovations, minutes):
    B = []
    A = B.append
    pages = kb["page_library"]
    times = alloc_time(pages, minutes)

    # ---------- 一、答辩定位与时间分配
    A({"t": "h2", "text": "一、答辩定位与时间分配"})
    A({"t": "kv", "rows": [
        ("答辩项目", project or TODO),
        ("项目方向", d["name"]),
        ("所属专业", d.get("discipline", "—")),
        ("汇报时长（本次设定）", "%d 分钟" % minutes),
        ("页面数量", "%d 页（含附录备用页）" % len([p for p in pages if p.get("weight", 0) > 0])),
    ]})
    A({"t": "note", "kind": "danger", "text": kb["meta"]["core_caveat"]})
    A({"t": "h3", "text": "答辩主线（先用这一句话统一全篇）"})
    A({"t": "note", "kind": "info", "text": d["focus"]})

    if achievements or innovations:
        A({"t": "h3", "text": "你提供的项目输入（将注入对应页面）"})
        if achievements:
            A({"t": "p", "text": "**核心成果**：" + "；".join(achievements)})
        if innovations:
            A({"t": "p", "text": "**创新点**：" + "；".join(innovations)})
        A({"t": "note", "kind": "warn",
           "text": "以上为你提供的内容。方案中已把它们放入「创新点与应用价值」页；请确认每条成果都能追溯到具体的页面与截图，"
                   "否则宁可删掉也不要放在台上——**答不出出处的数字，比没有数字更伤**。"})

    A({"t": "h3", "text": "时间分配表（按 %d 分钟自动折算）" % minutes})
    A({"t": "table", "head": ["页序", "页面", "优先级", "建议时长", "占比"],
       "rows": [[p["no"], p["title"], p.get("priority", ""), fmt_min(times.get(p["key"], 0)),
                 ("%.0f%%" % (times.get(p["key"], 0) / minutes * 100)) if times.get(p["key"], 0) else "—"]
                for p in pages]})
    A({"t": "note", "kind": "danger", "text": kb["meta"]["time_rule"]})
    A({"t": "note", "kind": "info",
       "text": "时长按页库权重折算，是**比例参考**而非标准答案。核心是保持这个比例关系："
               "背景 ≤10%，核心应用（模型 / 碰撞 / 4D / 算量）≥50%，创新与反思不可压缩。"})

    # ---------- 二、PPT 大纲总览
    A({"t": "h2", "text": "二、PPT 大纲总览"})
    A({"t": "p", "text": "先看骨架，再看细节。每页只承担一个核心任务——如果一页要讲两件事，说明它该拆成两页。"})
    A({"t": "table", "head": ["页序", "页面", "优先级", "这一页的任务"],
       "rows": [[p["no"], p["title"], p.get("priority", ""), p.get("role", "")]
                for p in pages]})

    # ---------- 三、逐页内容要点与演讲备注
    A({"t": "h2", "text": "三、逐页内容要点与演讲备注"})
    A({"t": "note", "kind": "info",
       "text": "每张卡片左栏是**内容要点**（这一页要放什么），右栏是**演讲备注**（这一页要怎么讲）。"
               "演讲备注不是讲稿，是提醒——真正的讲稿要你自己出声念顺。"})
    for p in pages:
        A({"t": "pagecard",
           "no": p["no"], "title": p["title"], "pri": p.get("priority", ""),
           "time": fmt_min(times.get(p["key"], 0)),
           "role": p.get("role", ""), "points": p.get("points", []), "notes": p.get("notes", []),
           "must": p.get("must", []), "visual": p.get("visual", ""), "traps": p.get("traps", [])})

    # ---------- 四、方向专属加分页
    A({"t": "h2", "text": "四、%s：专属加分页与量化指标" % d["name"]})
    if key is None:
        A({"t": "note", "kind": "warn",
           "text": "「%s」这个方向未收录在本知识库中，以下为**通用回退内容**，必须由你本人补充后才能使用。"
                   "建议先从项目里挑出最能体现能力的 1-2 个深度应用点单独成页。" % (project or "该项目")})
    A({"t": "h3", "text": "专属加分页（在核心应用之外额外增加，用于拉开差距）"})
    for sp in d.get("specialty_pages", []):
        A({"t": "specpage", "title": sp["title"], "role": sp.get("role", ""),
           "points": sp.get("points", []), "notes": sp.get("notes", [])})
    A({"t": "h3", "text": "本项目可以引用的量化指标（核心成果页与创新页用）"})
    A({"t": "table", "head": ["指标", "建议量级 / 取值", "说明"],
       "rows": [[m["name"], m["value"], m["note"]] for m in d.get("metrics", [])]})
    A({"t": "note", "kind": "warn",
       "text": "**指标值必须换成你这个项目的真实数字**。表中给的是「应该准备哪一类指标」与经验量级，"
               "不是可以直接念的答案。报出来的每个数字都要能说出出处。"})
    A({"t": "h3", "text": "本方向必须能脱口而出的术语"})
    A({"t": "chips", "items": d.get("terms", [])})
    A({"t": "note", "kind": "info",
       "text": "评委常用「你能不能把这个词解释一下」来测试你是否真懂。以下术语要能用一句人话解释，不要背定义。"})
    A({"t": "h3", "text": "本方向最容易翻车的地方"})
    A({"t": "ul", "items": d.get("traps", [])})

    # ---------- 五、评委可能提问
    A({"t": "h2", "text": "五、评委可能提问（前 5 个必须准备）"})
    five = select_five(d, qb)
    A({"t": "note", "kind": "danger",
       "text": "以下 5 个问题是结合项目方向筛出的**最可能被问**的问题。每个都要练到能不看稿答出来。"})
    for i, q in enumerate(five, 1):
        A({"t": "h3", "text": "问题 %d" % i})
        A({"t": "qa", "q": q["q"], "intent": q["intent"], "answer": q["answer"],
           "trap": q.get("trap"), "follow": q.get("follow")})

    A({"t": "h3", "text": "提问类型分布（决定你把准备时间花在哪）"})
    A({"t": "table", "head": ["提问类型", "占比（经验）", "典型问法"],
       "rows": [[x["type"], "%d%%" % x["share"], x["typical"]] for x in qb["probe_distribution"]]})
    A({"t": "note", "kind": "warn", "text": qb["probe_distribution_note"]})

    A({"t": "h3", "text": "完整题库（八类）"})
    A({"t": "p", "text": "按类别展开。建议先用「提问类型分布」决定优先级，再逐条口头演练。"})
    for c in qb["categories"]:
        A({"t": "h3", "text": "%s（%d 问）" % (c["name"], len(c["questions"]))})
        A({"t": "note", "kind": "info", "text": c["why"]})
        for q in c["questions"]:
            A({"t": "qa", "q": q["q"], "intent": q["intent"], "answer": q["answer"],
               "trap": q.get("trap"), "follow": q.get("follow")})

    A({"t": "h3", "text": qb["trap_questions"]["title"]})
    A({"t": "note", "kind": "warn", "text": qb["trap_questions"]["note"]})
    A({"t": "table", "head": ["刁钻问题", "应对方式"],
       "rows": [[x["q"], x["how"]] for x in qb["trap_questions"]["items"]]})

    # ---------- 六、答辩准备建议
    A({"t": "h2", "text": "六、答辩准备建议"})
    prep = qb["prep"]

    A({"t": "h3", "text": qb["answer_rules"]["title"]})
    A({"t": "steps", "items": qb["answer_rules"]["steps"]})
    A({"t": "p", "text": "**绝对不要做的事：**"})
    A({"t": "ul", "items": qb["answer_rules"]["forbidden"]})

    A({"t": "h3", "text": prep["time_allocation"]["title"]})
    A({"t": "table", "head": ["时长", "适用场景", "讲法与建议"],
       "rows": [[t["label"], t["minutes"].__str__() + " 分钟", t["advice"]]
                for t in prep["time_allocation"]["tiers"]]})
    A({"t": "note", "kind": "info", "text": prep["time_allocation"]["note"]})

    A({"t": "h3", "text": prep["rehearsal"]["title"]})
    for st in prep["rehearsal"]["steps"]:
        A({"t": "p", "text": "**%s**" % st["phase"]})
        A({"t": "ol", "items": st["items"]})

    A({"t": "h3", "text": prep["materials"]["title"]})
    for g in prep["materials"]["groups"]:
        A({"t": "p", "text": "**%s**" % g["group"]})
        A({"t": "ul", "items": g["items"]})

    A({"t": "h3", "text": prep["fatal_errors"]["title"]})
    for e in prep["fatal_errors"]["items"]:
        A({"t": "err", "err": e["err"], "why": "为什么致命：" + e["why"], "fix": e["fix"]})

    A({"t": "h3", "text": prep["emergency"]["title"]})
    A({"t": "table", "head": ["突发情况", "应对"],
       "rows": [[x["case"], x["how"]] for x in prep["emergency"]["items"]]})

    A({"t": "note", "kind": "info",
       "text": "最后一句实话：答辩的本质是让评委确认「这个人能毕业 / 这个成果是真的」。"
               "大多数评委希望你通过，认真准备、态度端正、数据诚实，基本都能顺利过关。"})
    return B


# ---------------------------------------------------------------- 讲稿卡
def build_cue_md(kb, d, project, minutes):
    pages = kb["page_library"]
    times = alloc_time(pages, minutes)
    L = []
    A = L.append
    A("# %s · 逐页讲稿卡（打印随身版）\n" % (project or "〔项目名称〕"))
    A("> 方向：%s　|　总时长：%d 分钟　|　用法：出声念顺，卡壳处改写成口语\n" % (d["name"], minutes))
    A("---\n")
    for p in pages:
        if p.get("weight", 0) == 0:
            continue
        A("\n## %s　%s　（%s）\n" % (p["no"], p["title"], fmt_min(times.get(p["key"], 0))))
        A("**这一页只讲一件事**：%s\n" % md_inline(p.get("role", "")))
        A("**要放的内容**\n")
        A("\n".join("- %s" % md_inline(x) for x in p.get("points", [])))
        A("\n\n**讲的时候记住**\n")
        A("\n".join("- %s" % md_inline(x) for x in p.get("notes", [])))
        if p.get("traps"):
            A("\n\n**别踩**：" + "；".join(md_inline(x) for x in p["traps"]))
        A("")
    A("\n---\n")
    A("## 收尾提醒\n")
    for x in ["讲完致谢页立刻停下，不要自己找话说",
              "被问不会的：承认 + 给一点思路 + 会后整改，绝不胡编",
              "任何时候都不与评委争辩",
              "全程正片控制在总时长的 90% 以内"]:
        A("- [ ] %s" % x)
    return "\n".join(L)


# ---------------------------------------------------------------- 提问预案 MD
def build_qa_md(kb, qb, d, project, minutes):
    L = []
    A = L.append
    A("# %s · 评委提问预案与答辩准备建议\n" % (project or "〔项目名称〕"))
    A("> 方向：%s　|　汇报时长：%d 分钟\n" % (d["name"], minutes))
    A("\n## 一、最可能要准备的 5 个问题\n")
    for i, q in enumerate(select_five(d, qb), 1):
        A("### 问题 %d：%s\n" % (i, md_inline(q["q"])))
        A("- **提问意图**：%s" % md_inline(q["intent"]))
        A("- **回答框架**：%s" % md_inline(q["answer"]))
        if q.get("trap"):
            A("- **陷阱**：%s" % md_inline(q["trap"]))
        if q.get("follow"):
            A("- **可能追问**：%s" % md_inline(q["follow"]))
        A("")
    A("\n## 二、完整题库（八类 %d 问）\n" % sum(len(c["questions"]) for c in qb["categories"]))
    for c in qb["categories"]:
        A("\n### %s\n" % c["name"])
        A("> %s\n" % md_inline(c["why"]))
        for q in c["questions"]:
            A("- **问：%s**" % md_inline(q["q"]))
            A("  - 意图：%s" % md_inline(q["intent"]))
            A("  - 回答：%s" % md_inline(q["answer"]))
            if q.get("trap"):
                A("  - 陷阱：%s" % md_inline(q["trap"]))
            if q.get("follow"):
                A("  - 追问：%s" % md_inline(q["follow"]))
        A("")
    A("\n## 三、刁钻问题应对\n")
    A("> %s\n" % md_inline(qb["trap_questions"]["note"]))
    for x in qb["trap_questions"]["items"]:
        A("- **%s**\n  - %s" % (md_inline(x["q"]), md_inline(x["how"])))
    A("")
    A("\n## 四、应答黄金五步\n")
    A("\n".join("- %s" % md_inline(x) for x in qb["answer_rules"]["steps"]))
    A("\n\n**绝对不要做：**\n")
    A("\n".join("- %s" % md_inline(x) for x in qb["answer_rules"]["forbidden"]))
    A("")
    A("\n## 五、时间分配\n")
    A("> %s\n" % md_inline(qb["prep"]["time_allocation"]["note"]))
    A("| 时长 | 适用场景 | 讲法建议 |")
    A("| --- | --- | --- |")
    for t in qb["prep"]["time_allocation"]["tiers"]:
        A("| %s | %d 分钟 | %s |" % (md_inline(t["label"]), t["minutes"], md_inline(t["advice"])))
    A("")
    A("\n## 六、演练方法（三阶段）\n")
    for st in qb["prep"]["rehearsal"]["steps"]:
        A("\n### %s\n" % md_inline(st["phase"]))
        A("\n".join("- [ ] %s" % md_inline(x) for x in st["items"]))
    A("")
    A("\n## 七、材料与现场准备\n")
    for g in qb["prep"]["materials"]["groups"]:
        A("\n### %s\n" % md_inline(g["group"]))
        A("\n".join("- [ ] %s" % md_inline(x) for x in g["items"]))
    A("")
    A("\n## 八、致命错误清单\n")
    for e in qb["prep"]["fatal_errors"]["items"]:
        A("- **%s**\n  - 原因：%s\n  - 修正：%s" % (md_inline(e["err"]), md_inline(e["why"]), md_inline(e["fix"])))
    A("")
    A("\n## 九、应急预案\n")
    A("| 突发情况 | 应对 |")
    A("| --- | --- |")
    for x in qb["prep"]["emergency"]["items"]:
        A("| %s | %s |" % (md_inline(x["case"]), md_inline(x["how"])))
    A("")
    A("\n## 十、本方向必背术语\n")
    A("　".join("`%s`" % md_inline(t) for t in d.get("terms", [])))
    A("")
    A("\n## 十一、本方向最容易翻车处\n")
    A("\n".join("- %s" % md_inline(x) for x in d.get("traps", [])))
    A("")
    return "\n".join(L)


# ---------------------------------------------------------------- 模板
def template_blocks(kb, qb, which):
    B = []
    A = B.append
    if which in ("all", "outline"):
        A({"t": "h2", "text": "一、PPT 大纲（空白模板，逐页填写）"})
        A({"t": "note", "kind": "info", "text": kb["meta"]["time_rule"]})
        for p in kb["page_library"]:
            A({"t": "pagecard", "no": p["no"], "title": p["title"], "pri": p.get("priority", ""),
               "time": "", "role": p.get("role", ""), "points": p.get("points", []),
               "notes": p.get("notes", []), "must": p.get("must", []),
               "visual": p.get("visual", ""), "traps": p.get("traps", [])})
    if which in ("all", "qa"):
        A({"t": "h2", "text": "二、提问预案（空白模板）"})
        A({"t": "note", "kind": "info", "text": qb["trap_questions"]["note"]})
        for c in qb["categories"]:
            A({"t": "h3", "text": c["name"]})
            for q in c["questions"]:
                A({"t": "qa", "q": q["q"], "intent": q["intent"], "answer": q["answer"],
                   "trap": q.get("trap"), "follow": q.get("follow")})
    if which in ("all", "prep"):
        A({"t": "h2", "text": "三、答辩准备建议（空白模板）"})
        A({"t": "steps", "items": qb["answer_rules"]["steps"]})
        A({"t": "h3", "text": qb["prep"]["time_allocation"]["title"]})
        A({"t": "table", "head": ["时长", "适用场景", "讲法建议"],
           "rows": [[t["label"], "%d 分钟" % t["minutes"], t["advice"]]
                    for t in qb["prep"]["time_allocation"]["tiers"]]})
        A({"t": "h3", "text": qb["prep"]["fatal_errors"]["title"]})
        for e in qb["prep"]["fatal_errors"]["items"]:
            A({"t": "err", "err": e["err"], "why": "为什么致命：" + e["why"], "fix": e["fix"]})
        A({"t": "h3", "text": qb["prep"]["emergency"]["title"]})
        A({"t": "table", "head": ["突发情况", "应对"],
           "rows": [[x["case"], x["how"]] for x in qb["prep"]["emergency"]["items"]]})
    return B


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="BIM 答辩 PPT 生成器")
    ap.add_argument("--list", action="store_true", help="列出方向库与页面库")
    ap.add_argument("--direction", help="项目方向（支持别名）")
    ap.add_argument("--input", help="自定义 JSON 输入")
    ap.add_argument("--template", nargs="?", const="all", choices=["all", "outline", "qa", "prep"],
                    help="输出空白模板")
    ap.add_argument("--project", default="", help="项目名称")
    ap.add_argument("--achievements", action="append", help="核心成果（可重复；也可用 | 分隔）")
    ap.add_argument("--innovations", action="append", help="创新点（可重复；也可用 | 分隔）")
    ap.add_argument("--minutes", type=int, default=15, help="汇报时长（分钟），默认 15")
    ap.add_argument("--name", default="", help="输出文件名前缀")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--json-only", action="store_true", help="仅输出 JSON 结果")
    args = ap.parse_args()

    kb, qb = load_assets()

    if args.list:
        res = {"ok": True, "directions": len(kb["directions"]),
               "pages": len(kb["page_library"]),
               "items": [{"key": k, "name": v["name"], "discipline": v.get("discipline", "—"),
                          "aliases": len(v.get("aliases", [])),
                          "specialty_pages": len(v.get("specialty_pages", [])),
                          "metrics": len(v.get("metrics", [])),
                          "hot_questions": len(v.get("hot_questions", [])),
                          "terms": len(v.get("terms", []))}
                         for k, v in kb["directions"].items()],
               "generic_fallback": bool(kb.get("generic_fallback")),
               "page_points": sum(len(p.get("points", [])) for p in kb["page_library"]),
               "page_notes": sum(len(p.get("notes", [])) for p in kb["page_library"]),
               "page_traps": sum(len(p.get("traps", [])) for p in kb["page_library"]),
               "qa_categories": len(qb["categories"]),
               "qa_questions": sum(len(c["questions"]) for c in qb["categories"]),
               "trap_questions": len(qb["trap_questions"]["items"]),
               "fatal_errors": len(qb["prep"]["fatal_errors"]["items"]),
               "emergency": len(qb["prep"]["emergency"]["items"])}
        if args.json_only:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("方向库：%d 类（另含通用回退）" % res["directions"])
            for c in res["items"]:
                print("  %-18s %-24s %s | 加分页%d 指标%d 追问%d 术语%d | 别名%d"
                      % (c["key"], c["name"][:24], c["discipline"], c["specialty_pages"],
                         c["metrics"], c["hot_questions"], c["terms"], c["aliases"]))
            print("通用回退：%s" % ("有" if res["generic_fallback"] else "无"))
            print("页面库 %d 页 | 要点 %d 条 | 备注 %d 条 | 失误 %d 条"
                  % (res["pages"], res["page_points"], res["page_notes"], res["page_traps"]))
            print("提问 %d 类 %d 问 + 刁钻 %d 问 | 致命错误 %d 条 | 应急 %d 条"
                  % (res["qa_categories"], res["qa_questions"], res["trap_questions"],
                     res["fatal_errors"], res["emergency"]))
        return 0

    os.makedirs(args.outdir, exist_ok=True)

    # --- 模板模式 ---
    if args.template:
        which = args.template
        tmap = {"all": "BIM 答辩 PPT 全套模板", "outline": "BIM 答辩 PPT 大纲模板",
                "qa": "BIM 答辩提问预案模板", "prep": "BIM 答辩准备建议模板"}
        title = tmap[which]
        base = args.name or title
        B = template_blocks(kb, qb, which)
        h = os.path.join(args.outdir, base + ".html")
        m = os.path.join(args.outdir, base + ".md")
        open(h, "w", encoding="utf-8", newline="\n").write(
            page(title, args.project or "空白模板，待填写", B))
        open(m, "w", encoding="utf-8", newline="\n").write(
            "# %s\n\n> %s\n\n" % (title, md_inline(args.project or "空白模板，待填写")) + render_md(B))
        files = [h, m]
        if args.json_only:
            print(json.dumps({"ok": True, "mode": "template", "which": which, "files": files},
                             ensure_ascii=False, indent=2))
        else:
            print("已生成模板：%s（%d 区块）" % (which, len(B)))
            for f in files:
                print("  ", f)
        return 0

    # --- 确定方向 ---
    achievements, innovations = [], []
    if args.input:
        payload = json.load(open(args.input, encoding="utf-8"))
        dir_query = payload.get("direction", "")
        project = payload.get("project_name") or args.project
        achievements = parse_list(payload.get("achievements"))
        innovations = parse_list(payload.get("innovations"))
        if payload.get("minutes"):
            args.minutes = int(payload["minutes"])
        name = args.name or payload.get("name") or project
    elif args.direction:
        dir_query = args.direction
        project = args.project
        achievements = parse_list(args.achievements)
        innovations = parse_list(args.innovations)
        name = args.name or project or args.direction
    else:
        print("请指定 --direction / --input / --template / --list", file=sys.stderr)
        return 2

    achievements = parse_list(achievements)
    innovations = parse_list(innovations)

    key, d, amb = resolve_direction(kb, dir_query)
    if d is None:
        d = dict(kb["generic_fallback"])
        key = None

    if not name:
        name = project or (d["name"] + "_答辩PPT")

    base = name
    blocks = build_blocks(kb, qb, key, d, project, achievements, innovations, args.minutes)

    title = "%s · 答辩 PPT 大纲" % (project or d["name"])
    sub = "%s　|　方向：%s　|　汇报时长：%d 分钟　|　%s" % (
        project or TODO, d["name"], args.minutes, d.get("discipline", "—"))

    h = os.path.join(args.outdir, base + "_答辩PPT大纲.html")
    m = os.path.join(args.outdir, base + "_答辩PPT大纲.md")
    c = os.path.join(args.outdir, base + "_逐页讲稿卡.md")
    q = os.path.join(args.outdir, base + "_提问预案与准备建议.md")

    open(h, "w", encoding="utf-8", newline="\n").write(page(title, sub, blocks))
    open(m, "w", encoding="utf-8", newline="\n").write(
        "# %s\n\n> %s\n\n" % (title, md_inline(sub)) + render_md(blocks))
    open(c, "w", encoding="utf-8", newline="\n").write(build_cue_md(kb, d, project, args.minutes))
    open(q, "w", encoding="utf-8", newline="\n").write(
        build_qa_md(kb, qb, d, project, args.minutes))
    files = [h, m, c, q]

    if args.json_only:
        print(json.dumps({
            "ok": True,
            "direction": d["name"],
            "direction_key": key,
            "direction_in_library": key is not None,
            "ambiguous_with": [kb["directions"][x]["name"] for x in amb],
            "project": project,
            "minutes": args.minutes,
            "pages": len(kb["page_library"]),
            "specialty_pages": len(d.get("specialty_pages", [])),
            "metrics": len(d.get("metrics", [])),
            "terms": len(d.get("terms", [])),
            "top5_questions": [x["q"] for x in select_five(d, qb)],
            "qa_questions": sum(len(c2["questions"]) for c2 in qb["categories"]),
            "achievements": achievements,
            "innovations": innovations,
            "blocks": len(blocks),
            "files": files,
        }, ensure_ascii=False, indent=2))
    else:
        print("项目：%s" % (project or TODO))
        print("方向：%s%s" % (d["name"], "" if key else "（未收录，已回退通用骨架）"))
        if amb:
            print("  注意：该说法在库中挂多个方向，已取本方向；备选：" +
                  "、".join(kb["directions"][x]["name"] for x in amb))
        print("  答题时长设定：%d 分钟" % args.minutes)
        print("  专属加分页 %d | 量化指标 %d | 术语 %d"
              % (len(d.get("specialty_pages", [])), len(d.get("metrics", [])), len(d.get("terms", []))))
        print("  前 5 问：")
        for i, x in enumerate(select_five(d, qb), 1):
            print("    %d. %s" % (i, x["q"]))
        print("  方案区块 %d" % len(blocks))
        for f in files:
            print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
