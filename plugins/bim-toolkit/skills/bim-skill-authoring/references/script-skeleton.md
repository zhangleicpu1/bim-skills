# 生成脚本骨架（可复制）

把下面骨架整段复制，改掉 `<x>` / 领域字段即可。**保持六块的顺序与函数名，便于跨 Skill 维护。**

```python
# -*- coding: utf-8 -*-
"""<领域>方案生成器

用法：
  <x>_builder.py --list
  <x>_builder.py --component <类型> --project "XX项目" --name "XX项目" -o out
  <x>_builder.py --input data.json --name "XX项目" -o out
  <x>_builder.py --template [all|<子模板>] -o out
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

# 歧义别名的默认归属（同一别名挂在多个条目上时）
AMBIGUOUS_DEFAULT = {}


# ================================================ 1. 载入
def load_assets():
    kb = json.load(open(os.path.join(ASSETS, "<x>_kb.json"), encoding="utf-8"))
    std = json.load(open(os.path.join(ASSETS, "standards.json"), encoding="utf-8"))
    return kb, std


def build_alias_index(kb, group="components"):
    """别名 → 条目 key 列表（含歧义）"""
    idx = {}
    for k, v in kb[group].items():
        for a in [k] + list(v.get("aliases", [])):
            idx.setdefault(a, [])
            if k not in idx[a]:
                idx[a].append(k)
    return idx


def resolve(kb, query, group="components"):
    """三级匹配：精确 → 长别名包含 → 最长优先。**单字别名不参与子串匹配**。

    返回 (key, data, ambiguous_list)；未命中返回 (None, None, [])
    """
    if not query:
        return None, None, []
    q = query.strip()
    items = kb[group]
    idx = build_alias_index(kb, group)

    # 1) 精确匹配
    if q in items:
        return q, items[q], []
    if q in idx:
        c = idx[q]
        if len(c) == 1:
            return c[0], items[c[0]], []
        pick = AMBIGUOUS_DEFAULT.get(q, c[0])
        if pick not in c:
            pick = c[0]
        return pick, items[pick], [x for x in c if x != pick]

    # 2) 子串匹配：只用 len >= 2 的别名，取最长者
    best, best_len = None, 0
    for a, c in idx.items():
        if len(a) < 2:              # ← 关键：单字别名不参与
            continue
        if a in q and len(a) > best_len:
            best, best_len = a, len(a)
    if best:
        c = idx[best]
        if len(c) == 1:
            return c[0], items[c[0]], []
        pick = AMBIGUOUS_DEFAULT.get(best, c[0])
        if pick not in c:
            pick = c[0]
        return pick, items[pick], [x for x in c if x != pick]
    return None, None, []


# ================================================ 2. 文本工具
def esc(s):
    return H.escape(str(s if s is not None else ""), quote=False)


def highlight(escaped):
    """占位符标红，且不重复包裹已有标记（stash 机制，防止嵌套 span）。"""
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return "\x00%d\x00" % (len(stash) - 1)

    tmp = re.sub(r'<span class="todo">.*?</span>', _stash, escaped, flags=re.S)
    tmp = PLACEHOLDER_RE.sub(lambda m: '<span class="todo">%s</span>' % m.group(0), tmp)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], tmp)


def inline(s):
    """HTML：转义 + 标红 + **粗体** + 换行。"""
    t = highlight(esc(s))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    return t.replace("\n", "<br>")


def md_inline(s):
    """Markdown：仅保留粗体，占位符加粗醒目。"""
    t = str(s if s is not None else "")
    return PLACEHOLDER_RE.sub(lambda m: "**%s**" % m.group(0), t)


# ================================================ 3. 区块渲染
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
        elif t == "kv":
            out.append("<table class='kv'><tbody>%s</tbody></table>" %
                       "".join("<tr><th>%s</th><td>%s</td></tr>" % (inline(k), inline(v))
                               for k, v in b["rows"]))
        elif t == "table":
            head = "<tr>%s</tr>" % "".join("<th>%s</th>" % inline(h) for h in b["head"])
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                           for r in b["rows"])
            out.append("<table><thead>%s</thead><tbody>%s</tbody></table>" % (head, body))
        elif t == "chips":
            out.append('<div class="chips">%s</div>' %
                       "".join('<span class="chip">%s</span>' % inline(x) for x in b["items"]))
        elif t == "steps":
            out.append('<div class="steps">%s</div>' % "".join(
                '<div class="step"><span class="no">%d</span><div>%s</div></div>' % (i, inline(x))
                for i, x in enumerate(b["items"], 1)))
        elif t == "err":
            out.append('<div class="err"><b>%s</b><br><span class="fix">修正：%s</span></div>'
                       % (inline(b["title"]), inline(b["fix"])))
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
            out.append("\n" + "\n".join("%d. %s" % (i, md_inline(x))
                                        for i, x in enumerate(b["items"], 1)) + "\n")
        elif t == "note":
            out.append("\n> **%s**：%s\n" % (b.get("kind", "提示"), md_inline(b["text"])))
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
        elif t == "err":
            out.append("\n- **%s**\n  - 修正：%s" % (md_inline(b["title"]), md_inline(b["fix"])))
    return "\n".join(out)


# ================================================ 4. CSS（light 主题 + 可打印）
CSS = """
:root{--fg:#1a1a1a;--muted:#5c6b7a;--line:#dfe5ec;--bg:#fff;--soft:#f6f8fa;
--accent:#1a5fb4;--warn:#b45309;--danger:#b3261e;--ok:#1a7f4b;--chip:#eef3fb;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}
.wrap{max-width:1000px;margin:0 auto;padding:44px 34px 90px}
h1{font-size:27px;margin:0 0 6px}
h2{font-size:19px;margin:44px 0 14px;padding:9px 0 9px 13px;border-left:4px solid var(--accent);
background:var(--soft);border-radius:0 5px 5px 0}
h3{font-size:16px;margin:26px 0 10px;color:#243447}
table{border-collapse:collapse;width:100%;margin:13px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600}
table.kv th{width:190px;background:var(--soft)}
tbody tr:nth-child(even){background:#fcfdfe}
.sub{color:var(--muted);font-size:13.5px;margin:0 0 26px}
.todo{color:var(--danger);background:#fdeceb;border-radius:3px;padding:0 3px;font-weight:600}
.note{border-left:3px solid var(--accent);background:#f2f7fd;padding:11px 15px;margin:13px 0;
border-radius:0 5px 5px 0;font-size:14px}
.note.warn{border-color:var(--warn);background:#fdf7ed}
.note.danger{border-color:var(--danger);background:#fdeceb}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}
.chip{background:var(--chip);color:#1a3d63;border-radius:5px;padding:3px 10px;font-size:13px}
.steps{margin:13px 0}
.step{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px}
.step .no{flex:0 0 25px;height:25px;line-height:25px;text-align:center;background:var(--accent);
color:#fff;border-radius:50%;font-size:12.5px;font-weight:600}
.err{border-left:3px solid var(--danger);background:#fdf5f4;padding:10px 14px;margin:9px 0;
border-radius:0 5px 5px 0;font-size:13.5px}
.err b{color:var(--danger)}
.err .fix{color:var(--ok)}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
color:var(--muted);font-size:12.5px}
@media print{body{font-size:11.5px}.wrap{padding:0;max-width:100%}h2{page-break-after:avoid}
table,.note,.err{page-break-inside:avoid}}
"""


def page(title, subtitle, blocks):
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>%s</style></head><body><div class="wrap">
<h1>%s</h1><p class="sub">%s</p>
%s
<footer>本方案由「<Skill 名>」生成。<经验值/系数/规范复核提醒>。</footer>
</div></body></html>""" % (esc(title), CSS, esc(title), inline(subtitle), render_html(blocks))


# ================================================ 5. 方案主体
def build_blocks(kb, std, key, item, project, name, ambiguous):
    B = []
    A = B.append
    A({"t": "kv", "rows": [
        ("类型", item["name"]),
        ("专业", item.get("discipline", "—")),
        ("常用别名", "、".join(item.get("aliases", [])[:16])),
    ]})
    if item.get("intro"):
        A({"t": "note", "kind": "warn", "text": item["intro"]})
    if ambiguous:
        others = "、".join(kb["components"][x]["name"] for x in ambiguous)
        A({"t": "note", "kind": "warn",
           "text": "「%s」在库中同时挂在多个类型上（本方案取「%s」）。若要处理的是：%s，请改用标准名重新生成。"
                   % (name, item["name"], others)})
    A({"t": "h2", "text": "一、<章节名>"})
    # ... 按 KB 字段铺开各章 ...
    return B


# ================================================ 6. 主流程
def main():
    ap = argparse.ArgumentParser(description="<领域>方案生成器")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--component", help="类型（支持别名）")
    ap.add_argument("--input", help="自定义 JSON 输入")
    ap.add_argument("--template", nargs="?", const="all")
    ap.add_argument("--project", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("-o", "--outdir", default=".")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    kb, std = load_assets()

    if args.list:
        res = {"ok": True, "count": len(kb["components"]),
               "items": [{"key": k, "name": v["name"], "aliases": len(v.get("aliases", []))}
                         for k, v in kb["components"].items()],
               "generic_fallback": bool(kb.get("generic_fallback"))}
        if args.json_only:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            for c in res["items"]:
                print("  %-18s %-24s 别名%d" % (c["key"], c["name"][:24], c["aliases"]))
        return 0

    os.makedirs(args.outdir, exist_ok=True)

    # --- 模板模式（略）---
    # --- 确定条目 ---
    if args.input:
        payload = json.load(open(args.input, encoding="utf-8"))
        query = payload.get("component", "")
        project = payload.get("project_name") or args.project
        name = args.name or payload.get("name") or project
    else:
        query = args.component
        project = args.project
        name = args.name or (project + "_" + query if project else query)

    key, item, amb = resolve(kb, query)
    if item is None:
        item = dict(kb["generic_fallback"])
        key = None

    blocks = build_blocks(kb, std, key, item, project, args.component or item["name"], amb)
    base = name or item["name"]
    h = os.path.join(args.outdir, base + "_<主题>.html")
    m = os.path.join(args.outdir, base + "_<主题>.md")
    sub = "%s　|　类型：%s" % (project or TODO, item["name"])
    open(h, "w", encoding="utf-8", newline="\n").write(page("<主题>方案", sub, blocks))
    open(m, "w", encoding="utf-8", newline="\n").write(
        "# %s\n\n> %s\n\n" % (sub, md_inline(sub)) + render_md(blocks))
    files = [h, m]
    if args.json_only:
        print(json.dumps({"ok": True, "component": item["name"], "component_key": key,
                          "component_in_library": key is not None,
                          "blocks": len(blocks), "files": files}, ensure_ascii=False, indent=2))
    else:
        print("类型：%s" % item["name"])
        for f in files:
            print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 新增展示型区块的写法

以 `defense-ppt` 的页面卡片为例，说明怎么加自定义区块：

1. 在 `render_html()` 里加 `elif t == "pagecard":` 分支，拼 HTML
2. 在 `render_md()` 里加对应分支，拼 Markdown
3. 在 `CSS` 里加该区块的类（如 `.pagecard / .pc-head / .pc-grid`）
4. **print 规则里把它加进 `page-break-inside:avoid`**
5. `build_blocks()` 里 `A({"t": "pagecard", ...})`

**两处渲染必须同步加，否则 HTML 有内容而 MD 没有**（或反之）——验收时的「内容命中抽查」就是用来抓这个的。
