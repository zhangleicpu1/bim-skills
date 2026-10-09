#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参数化族创建方案生成器。

把「我要创建 XX 构件的参数化族」转成一份可直接照着做的建族方案 + 可勾选检查清单。

用法
----
1) 看库里支持哪些构件：
     python family_builder.py --list

2) 按构件生成方案（参数清单从知识库带出）：
     python family_builder.py --component 管片 --project "XX地铁区间" -o out/

3) 用自定义参数覆盖/扩展（主路径）：
     python family_builder.py --input family_spec.json -o out/

4) 只要一张空白检查清单：
     python family_builder.py --template -o out/

输出：{名称}_族创建方案.md/.html ＋ {名称}_族创建检查清单.md

设计原则：脚本只做渲染，参数与要点均来自知识库或 --input，不臆造技术内容。
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
LIB_PATH = os.path.join(ASSETS, "component_library.json")
STD_PATH = os.path.join(ASSETS, "family_standards.json")

TODO = "〔待确认〕"

KIND_CLASS = {"类型": "type", "实例": "inst"}

GROUP_ORDER = ["尺寸标注", "材质和装饰", "标识数据", "图形", "结构", "机械",
               "电气", "能量分析", "阶段化", "文本", "常规", "其他"]


# --------------------------------------------------------------------------
def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_assets():
    return load_json(LIB_PATH), load_json(STD_PATH)


def resolve_component(lib, name):
    """构件名归一化，支持别名。

    匹配策略分三级，逐级放宽：
      1) 精确匹配：完全等于构件名或某个别名
      2) 长别名包含：别名长度 ≥2 时才做子串匹配（单字别名如『梁』『柱』做子串会大量误伤，
         例如『桥梁支座』会被『梁』命中）
      3) 按别名长度降序尝试，让更具体的别名优先胜出
    """
    if not name:
        return None, None
    n = name.strip()
    comps = lib.get("components", {})

    # 一级：精确匹配
    if n in comps:
        return n, comps[n]
    for key, data in comps.items():
        if n in data.get("aliases", []):
            return key, data

    # 二级：子串匹配，仅限长度 ≥2 的别名，长别名优先
    candidates = []
    for key, data in comps.items():
        for a in data.get("aliases", []):
            if a and len(a) >= 2 and (a in n or n in a):
                candidates.append((len(a), key, data))
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1], candidates[0][2]

    return None, None


def sort_params(params):
    def key(p):
        g = p.get("group", "其他")
        try:
            gi = GROUP_ORDER.index(g)
        except ValueError:
            gi = 99
        return (gi, 0 if p.get("required") else 1, p.get("name", ""))
    return sorted(params, key=key)


def build_spec(lib, std, comp_name, project_name, overrides=None):
    key, comp = resolve_component(lib, comp_name)
    fb = lib.get("generic_fallback", {})
    matched = bool(key)

    if matched:
        data = {
            "component": key,
            "category": comp.get("category", TODO),
            "family_template": comp.get("family_template", TODO),
            "hosting": comp.get("hosting", TODO),
            "lod": comp.get("lod", TODO),
            "discipline": comp.get("discipline", TODO),
            "geometry_approach": comp.get("geometry_approach", ""),
            "key_points": list(comp.get("key_points", [])),
            "pitfalls": list(comp.get("pitfalls", [])),
            "param_groups": [{"title": "", "params": sort_params(comp.get("parameters", []))}],
            "sub_types": comp.get("sub_types"),
        }
        if data["sub_types"]:
            data["param_groups"] = [
                {"title": st_name, "params": sort_params(st_params)}
                for st_name, st_params in data["sub_types"].items()
            ]
    else:
        data = {
            "component": comp_name or "〔构件名称〕",
            "category": TODO,
            "family_template": fb.get("family_template", TODO),
            "hosting": TODO,
            "lod": TODO,
            "discipline": TODO,
            "geometry_approach": "〔按构件特点描述几何构建思路〕",
            "key_points": list(fb.get("key_points", [])),
            "pitfalls": list(fb.get("pitfalls", [])),
            "param_groups": [{"title": "", "params": sort_params(fb.get("parameters", []))}],
            "sub_types": None,
        }

    data["project_name"] = project_name or "〔项目名称〕"
    data["component_in_library"] = matched
    data["standards"] = std
    data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if overrides:
        for k in ("category", "family_template", "hosting", "lod", "discipline",
                  "geometry_approach"):
            if overrides.get(k):
                data[k] = overrides[k]
        if overrides.get("key_points"):
            data["key_points"] = list(overrides["key_points"])
        if overrides.get("pitfalls"):
            data["pitfalls"] = list(overrides["pitfalls"])
        if overrides.get("parameters"):
            data["param_groups"] = [{"title": "自定义参数", "params": sort_params(overrides["parameters"])}]
        if overrides.get("file_name"):
            data["file_name"] = overrides["file_name"]
    return data


def suggest_file_name(data, std):
    """按命名规范给出建议文件名。"""
    codes = {c["name"]: c["code"] for c in std.get("naming", {}).get("file_naming", {}).get("discipline_codes", [])}
    disc = data.get("discipline", "")
    code = "XX"
    for name, c in codes.items():
        if name and name in disc:
            code = c
            break
    comp = data.get("component", "构件").replace("（", "-").replace("）", "")
    return f"{code}-{comp}-〔规格〕-{data.get('lod', 'LOD300')}.rfa"


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def md_table(headers, rows):
    if not rows:
        return "_（无）_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("\n", " ") for x in r) + " |")
    return "\n".join(out) + "\n"


def param_rows(params):
    rows = []
    for p in params:
        req = "**必填**" if p.get("required") else "可选"
        rows.append([p.get("name", ""), p.get("kind", ""), p.get("data_type", ""),
                     p.get("group", ""), p.get("unit", "") or "—", req, p.get("note", "")])
    return rows


def render_markdown(data, std):
    L = []
    A = L.append
    comp = data["component"]

    A(f"# {comp} 参数化族创建方案\n")
    A(f"> 依托项目：{data['project_name']}　|　生成时间：{data['generated_at']}\n")

    # 概览
    A("## 一、构件与族样板\n")
    A(md_table(["项", "内容"], [
        ["构件类型", comp],
        ["族类别", data["category"]],
        ["族样板", data["family_template"]],
        ["宿主关系", data["hosting"]],
        ["目标 LOD", data["lod"]],
        ["专业", data["discipline"]],
        ["建议文件名", data.get("file_name") or suggest_file_name(data, std)],
    ]))
    if not data["component_in_library"]:
        A("> ⚠ 该构件不在知识库内，族样板与参数为通用骨架，**必须按 `references/parameter-design.md` 自行补充构件专属参数**。\n")
    A(f"> **族样板决定类别、剪切行为、宿主关系、标记与明细表字段。选错后期改不回来。**\n")

    # 参数清单
    A("## 二、参数清单\n")
    A("> `类型`=同一规格所有实例共用一个值；`实例`=每个图元可不同。**创建后不可更改，选错只能删除重建。**\n")
    for g in data["param_groups"]:
        title = f"### {g['title']}\n" if g.get("title") else ""
        A(title)
        A(md_table(["参数名", "类型", "数据类型", "分组方式", "单位", "必填", "说明"], param_rows(g["params"])))

    # 几何思路
    A("## 三、几何构建思路\n")
    A(data["geometry_approach"] or TODO)
    A("")

    # 创建步骤
    A("## 四、Revit 创建步骤\n")
    A("> 底层逻辑：**参照平面控制尺寸 → 尺寸控制参数 → 参数控制几何**。顺序不可颠倒。\n")
    for s in std.get("standard_steps", []):
        A(f"**第 {s['no']} 步 · {s['title']}**\n")
        A(f"{s['detail']}\n")
        A(f"- 检查点：{s['checkpoint']}\n")

    # 构件专属要点
    if data["key_points"]:
        A(f"## 五、{comp} 专属要点\n")
        for k in data["key_points"]:
            A(f"- {k}")
        A("")

    # 构件专属陷阱
    if data["pitfalls"]:
        A(f"## 六、{comp} 常见错误提醒\n")
        for p in data["pitfalls"]:
            A(f"- ⚠ {p}")
        A("")

    # 命名规范
    nm = std.get("naming", {})
    A("## 七、命名规范\n")
    A("**族文件命名**\n")
    A(f"格式：`{nm.get('file_naming', {}).get('recommended', '')}`\n")
    A(f"示例：`{nm.get('file_naming', {}).get('example', '')}`\n")
    A("专业代号：\n")
    A(md_table(["代号", "专业"], [[c["code"], c["name"]] for c in nm.get("file_naming", {}).get("discipline_codes", [])]))
    A("**参数命名**\n")
    for r in nm.get("parameter_naming", {}).get("rules", []):
        A(f"- {r}")
    A("")
    ob = nm.get("official_basis", {})
    A(f"**标准依据**：{ob.get('standard', '')}\n")
    A(f"编码结构：{ob.get('structure', '')}　示例：{ob.get('example', '')}\n")

    # 测试方法
    A("## 八、测试方法\n")
    A(md_table(["序号", "测试项", "怎么做", "通过标准"],
                [[t["no"], t["name"], t["how"], t["pass_criteria"]] for t in std.get("testing_methods", [])]))

    # 通用错误
    A("## 九、通用常见错误提醒（Top 14）\n")
    for e in std.get("common_errors", []):
        A(f"**{e['rank']}. {e['error']}**\n")
        A(f"- 现象：{e['symptom']}")
        A(f"- 根因：{e['cause']}")
        A(f"- 处理：{e['fix']}")
        A(f"- 预防：{e['prevent']}\n")

    # 提醒
    A("## 十、发布前提醒\n")
    for r in std.get("reminders", []):
        A(f"- {r}")
    A("")
    A("---\n")
    A(f"_本方案由参数化族创建助手生成于 {data['generated_at']}。_")
    return "\n".join(L) + "\n"


def render_checklist(data, std):
    L = []
    A = L.append
    A(f"# {data['component']} 参数化族创建检查清单\n")
    A(f"> 依托项目：{data['project_name']}　|　生成时间：{data['generated_at']}")
    A(f"> 用法：逐项勾选。**未全部通过不得发布族。**\n")
    total = 0
    for sec in std.get("checklist_sections", []):
        items = list(sec.get("items", []))
        A(f"## {sec['title']}\n")
        for it in items:
            A(f"- [ ] {it}")
            total += 1
        A("")
    if data.get("pitfalls"):
        A(f"## 10. {data['component']} 专属检查\n")
        for p in data["pitfalls"]:
            A(f"- [ ] 已规避：{p}")
            total += 1
        A("")
    if data.get("key_points"):
        A(f"## 11. {data['component']} 关键点确认\n")
        for k in data["key_points"]:
            A(f"- [ ] 已确认：{k}")
            total += 1
        A("")
    A(f"---\n\n共 {total} 项检查。\n")
    A(f"_由参数化族创建助手生成于 {data['generated_at']}。_")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
 background:#F5F6F8;color:#1F2328;line-height:1.75}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:26px;margin:0 0 8px;color:#1B4D3E;letter-spacing:.5px}
h2{font-size:19px;margin:34px 0 14px;padding-bottom:8px;border-bottom:2px solid #1B4D3E;color:#1B4D3E}
h3{font-size:16px;margin:22px 0 10px;color:#123A2E}
.card{background:#fff;border:1px solid #E3E6EA;border-radius:8px;padding:20px 24px;
 box-shadow:0 1px 3px rgba(0,0,0,.04);margin-bottom:18px}
.head{border-left:4px solid #1B4D3E}
.meta{font-size:13px;color:#5A6472;margin-top:6px}
table{width:100%;border-collapse:collapse;margin:10px 0 16px;font-size:13.5px;background:#fff}
th{background:#EDF4F1;color:#123A2E;font-weight:600;text-align:left;padding:9px 11px;border:1px solid #DDE3E9}
td{padding:9px 11px;border:1px solid #DDE3E9;vertical-align:top}
tbody tr:nth-child(even){background:#FAFBFD}
.tag{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:9px;white-space:nowrap}
.tag.type{background:#E6F1FB;color:#185FA5;border:1px solid #B5D4F4}
.tag.inst{background:#FDF0E3;color:#A85B12;border:1px solid #F2D3AC}
.tag.req{background:#FCE9E9;color:#B02A2A;border:1px solid #F2C4C4}
.tag.opt{background:#F1EFE8;color:#5F5E5A;border:1px solid #D3D1C7}
.tag.warn{background:#FDF0E3;color:#A85B12;border:1px solid #F2D3AC}
.tag.ok{background:#E3F4E8;color:#1B7A3D;border:1px solid #B5E0C4}
ul{margin:8px 0 14px;padding-left:22px}
li{margin:5px 0}
.note{background:#FFF9E8;border-left:4px solid #E0A800;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13.5px;margin:12px 0}
.err{background:#fff;border:1px solid #E3E6EA;border-left:4px solid #E24B4A;border-radius:0 6px 6px 0;padding:12px 16px;margin:12px 0}
.err b{color:#B02A2A}
.err .row{font-size:13.5px;margin:4px 0}
.todo{color:#B02A2A;font-weight:600}
.step{background:#fff;border:1px solid #E3E6EA;border-radius:8px;padding:14px 18px;margin:10px 0}
.step .no{display:inline-block;background:#1B4D3E;color:#fff;font-size:12px;padding:1px 9px;border-radius:9px;margin-right:8px}
.step .t{font-size:14.5px;font-weight:500;color:#123A2E}
.step .d{font-size:13.5px;margin:8px 0 0}
.step .cp{font-size:13px;color:#1B7A3D;margin-top:6px}
.foot{text-align:center;font-size:12.5px;color:#8A94A2;margin-top:26px}
@media print{body{background:#fff;padding:0}.wrap{max-width:none}.card,.err,.step{box-shadow:none;break-inside:avoid}
 h2{break-after:avoid}}
"""


def esc(v):
    return html.escape(str(v if v is not None else ""))


def hl(s):
    return esc(s).replace(esc(TODO), f"<span class='todo'>{esc(TODO)}</span>")


def htable(headers, rows):
    if not rows:
        return "<p style='font-size:13px;color:#5A6472'>（无）</p>"
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def param_table_html(params):
    rows = []
    for p in params:
        k = p.get("kind", "")
        ktag = f"<span class='tag {KIND_CLASS.get(k, 'opt')}'>{esc(k)}</span>"
        rtag = "<span class='tag req'>必填</span>" if p.get("required") else "<span class='tag opt'>可选</span>"
        rows.append([esc(p.get("name", "")), ktag, esc(p.get("data_type", "")),
                     esc(p.get("group", "")), esc(p.get("unit", "") or "—"), rtag,
                     esc(p.get("note", ""))])
    return htable(["参数名", "类型", "数据类型", "分组方式", "单位", "必填", "说明"], rows)


def render_html(data, std):
    comp = data["component"]
    P = []
    A = P.append
    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A(f"<title>{esc(comp)} 参数化族创建方案</title><style>{CSS}</style></head><body><div class='wrap'>")

    status = ("<span class='tag ok'>已命中知识库</span>" if data["component_in_library"]
              else "<span class='tag warn'>未在库内·需自行补参数</span>")
    A("<div class='card head'>")
    A(f"<h1>{esc(comp)} 参数化族创建方案</h1>")
    A(f"<div class='meta'>依托项目：{esc(data['project_name'])}　|　生成时间：{esc(data['generated_at'])}　|　{status}</div>")
    A("</div>")

    # 一、概览
    A("<h2>一、构件与族样板</h2><div class='card'>")
    A(htable(["项", "内容"], [
        ["构件类型", esc(comp)],
        ["族类别", hl(data["category"])],
        ["族样板", hl(data["family_template"])],
        ["宿主关系", hl(data["hosting"])],
        ["目标 LOD", hl(data["lod"])],
        ["专业", hl(data["discipline"])],
        ["建议文件名", hl(data.get("file_name") or suggest_file_name(data, std))],
    ]))
    if not data["component_in_library"]:
        A("<div class='note'>⚠ 该构件不在知识库内。族样板与参数为通用骨架，<b>必须按 <code>references/parameter-design.md</code> 自行补充构件专属参数</b>。</div>")
    A("<div class='note'><b>族样板决定类别、剪切行为、宿主关系、标记与明细表字段。选错后期改不回来。</b></div>")
    A("</div>")

    # 二、参数清单
    A("<h2>二、参数清单</h2><div class='card'>")
    A("<div class='note'>"
      "<span class='tag type'>类型</span> 同一规格所有实例共用一个值，如规格、等级、材质　　"
      "<span class='tag inst'>实例</span> 每个图元可不同，如标高、长度、编号<br>"
      "<b>类型/实例创建后不可更改，选错只能删除参数重建并重新关联几何。</b></div>")
    for g in data["param_groups"]:
        if g.get("title"):
            A(f"<h3>{esc(g['title'])}</h3>")
        A(param_table_html(g["params"]))
    A("</div>")

    # 三、几何思路
    A("<h2>三、几何构建思路</h2><div class='card'>")
    A(f"<p>{hl(data['geometry_approach'] or TODO)}</p></div>")

    # 四、创建步骤
    A("<h2>四、Revit 创建步骤</h2>")
    A("<div class='note'>底层逻辑：<b>参照平面控制尺寸 → 尺寸控制参数 → 参数控制几何</b>。顺序不可颠倒，绝大多数错误都源于破坏了这个顺序。</div>")
    for s in std.get("standard_steps", []):
        A("<div class='step'>")
        A(f"<span class='no'>第 {s['no']} 步</span><span class='t'>{esc(s['title'])}</span>")
        A(f"<div class='d'>{esc(s['detail'])}</div>")
        A(f"<div class='cp'>检查点：{esc(s['checkpoint'])}</div>")
        A("</div>")

    # 五、专属要点
    if data["key_points"]:
        A(f"<h2>五、{esc(comp)} 专属要点</h2><div class='card'><ul>" +
          "".join(f"<li>{esc(k)}</li>" for k in data["key_points"]) + "</ul></div>")

    # 六、专属陷阱
    if data["pitfalls"]:
        A(f"<h2>六、{esc(comp)} 常见错误提醒</h2><div class='card'><ul>" +
          "".join(f"<li><b>⚠</b> {esc(p)}</li>" for p in data["pitfalls"]) + "</ul></div>")

    # 七、命名规范
    nm = std.get("naming", {})
    fn = nm.get("file_naming", {})
    A("<h2>七、命名规范</h2><div class='card'>")
    A(f"<p><b>族文件命名格式</b>：<code>{esc(fn.get('recommended', ''))}</code></p>")
    A(f"<p><b>示例</b>：<code>{esc(fn.get('example', ''))}</code></p>")
    A(htable(["代号", "专业"], [[esc(c["code"]), esc(c["name"])] for c in fn.get("discipline_codes", [])]))
    A("<p><b>参数命名规则</b></p><ul>" +
      "".join(f"<li>{esc(r)}</li>" for r in nm.get("parameter_naming", {}).get("rules", [])) + "</ul>")
    ob = nm.get("official_basis", {})
    A(f"<div class='note'><b>标准依据</b>：{esc(ob.get('standard', ''))}<br>"
      f"编码结构：{esc(ob.get('structure', ''))}　示例：{esc(ob.get('example', ''))}<br>"
      f"{esc(ob.get('note', ''))}</div>")
    A("</div>")

    # 八、测试方法
    A("<h2>八、测试方法</h2><div class='card'>")
    A(htable(["序号", "测试项", "怎么做", "通过标准"],
             [[esc(t["no"]), f"<b>{esc(t['name'])}</b>", esc(t["how"]), esc(t["pass_criteria"])]
              for t in std.get("testing_methods", [])]))
    A("</div>")

    # 九、通用错误
    A("<h2>九、通用常见错误提醒（Top 14）</h2>")
    for e in std.get("common_errors", []):
        A("<div class='err'>")
        A(f"<b>{e['rank']}. {esc(e['error'])}</b>")
        A(f"<div class='row'><b>现象</b>：{esc(e['symptom'])}</div>")
        A(f"<div class='row'><b>根因</b>：{esc(e['cause'])}</div>")
        A(f"<div class='row'><b>处理</b>：{esc(e['fix'])}</div>")
        A(f"<div class='row'><b>预防</b>：{esc(e['prevent'])}</div>")
        A("</div>")

    # 十、提醒
    A("<h2>十、发布前提醒</h2><div class='card'><ul>" +
      "".join(f"<li>{esc(r)}</li>" for r in std.get("reminders", [])) + "</ul></div>")

    A(f"<div class='foot'>本方案由参数化族创建助手生成于 {esc(data['generated_at'])}</div>")
    A("</div></body></html>")
    return "\n".join(P)


# --------------------------------------------------------------------------
def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "族创建方案"


def write_all(data, std, outdir, base):
    os.makedirs(outdir, exist_ok=True)
    md = os.path.join(outdir, f"{base}_族创建方案.md")
    htm = os.path.join(outdir, f"{base}_族创建方案.html")
    ck = os.path.join(outdir, f"{base}_族创建检查清单.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(render_markdown(data, std))
    with open(htm, "w", encoding="utf-8") as f:
        f.write(render_html(data, std))
    with open(ck, "w", encoding="utf-8") as f:
        f.write(render_checklist(data, std))
    return md, htm, ck


def cmd_list(lib):
    comps = lib.get("components", {})
    print(f"构件知识库共 {len(comps)} 类：\n")
    for name, d in comps.items():
        n = len(d.get("parameters", []))
        if d.get("sub_types"):
            sub = " + ".join(f"{k}({len(v)})" for k, v in d["sub_types"].items())
            n = sum(len(v) for v in d["sub_types"].values())
            print(f"● {name}　[{n} 个参数]　子类型：{sub}")
        else:
            print(f"● {name}　[{n} 个参数]")
        print(f"    别名：{'、'.join(d.get('aliases', [])[:8])}")
        print(f"    族样板：{d.get('family_template', '')}")
        print(f"    专属陷阱：{len(d.get('pitfalls', []))} 条 | 关键要点：{len(d.get('key_points', []))} 条")
        print()
    print("◎ 未收录构件：走 generic_fallback 通用骨架，需自行按 parameter-design.md 补参数")


def main():
    ap = argparse.ArgumentParser(description="参数化族创建方案生成器")
    ap.add_argument("--list", action="store_true", help="列出构件知识库")
    ap.add_argument("--component", help="构件名称（支持别名）")
    ap.add_argument("--project", default="", help="依托项目名称")
    ap.add_argument("--name", default="", help="输出文件基础名")
    ap.add_argument("--input", help="自定义规格 JSON（主路径）")
    ap.add_argument("--template", action="store_true", help="只输出空白检查清单")
    ap.add_argument("-o", "--out", default=".", help="输出目录")
    ap.add_argument("--json-only", action="store_true", help="只打印结构化结果")
    args = ap.parse_args()

    lib, std = load_assets()

    if args.list:
        cmd_list(lib)
        return

    if args.template:
        data = build_spec(lib, std, "〔构件名称〕", args.project)
        data["component_in_library"] = False
        base = safe_name(args.name or "参数化族创建检查清单")
        if args.json_only:
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            return
        md, htm, ck = write_all(data, std, args.out, base)
        print(json.dumps({"ok": True, "mode": "template", "markdown": md, "html": htm, "checklist": ck,
                          "checklist_items": sum(len(s["items"]) for s in std["checklist_sections"])},
                         ensure_ascii=False))
        return

    if args.input:
        if not os.path.exists(args.input):
            print(json.dumps({"ok": False, "error": f"输入文件不存在：{args.input}"}, ensure_ascii=False))
            sys.exit(2)
        ov = load_json(args.input)
        data = build_spec(lib, std, ov.get("component", ""), ov.get("project_name", args.project), ov)
    elif args.component:
        data = build_spec(lib, std, args.component, args.project)
    else:
        print(json.dumps({"ok": False, "error": "需要 --list / --component / --input / --template 之一"}, ensure_ascii=False))
        sys.exit(2)

    base = safe_name(args.name or f"{data['component']}_参数化族")
    if args.json_only:
        print(json.dumps({k: v for k, v in data.items() if k != "standards"}, ensure_ascii=False, indent=2))
        return

    md, htm, ck = write_all(data, std, args.out, base)
    nparams = sum(len(g["params"]) for g in data["param_groups"])
    nreq = sum(1 for g in data["param_groups"] for p in g["params"] if p.get("required"))
    print(json.dumps({
        "ok": True, "component": data["component"],
        "component_in_library": data["component_in_library"],
        "params": nparams, "required_params": nreq,
        "param_groups": len(data["param_groups"]),
        "steps": len(std["standard_steps"]),
        "common_errors": len(std["common_errors"]),
        "pitfalls": len(data["pitfalls"]),
        "markdown": md, "html": htm, "checklist": ck,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
