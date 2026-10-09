#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BIM 选题调研报告生成器。

把「调研结果」渲染成可直接交作业/开题的《选题报告》。

三种用法
--------
1) 看库里有什么方向：
     python research_builder.py --list

2) 按方向生成报告草稿（案例从种子库自动带出，其余章节留骨架）：
     python research_builder.py --direction 铀矿工程 --project "X矿采冶工程" -o out/

3) 用检索到的结构化数据渲染正式报告（主路径）：
     python research_builder.py --input research_data.json -o out/

4) 只要一张空白报告模板：
     python research_builder.py --template -o out/

输出：{名称}_选题报告.md + {名称}_选题报告.html（HTML 可直接打印/发群）

设计原则：脚本只负责渲染与结构化，绝不编造案例内容。
所有案例文字均来自 --input 或种子库中带 source/url 的真实记录。
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
LIB_PATH = os.path.join(ASSETS, "case_library.json")
PAT_PATH = os.path.join(ASSETS, "topic_patterns.json")

TODO = "〔待补充〕"


# --------------------------------------------------------------------------
# 载入资源
# --------------------------------------------------------------------------
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_assets():
    lib = load_json(LIB_PATH)
    pat = load_json(PAT_PATH)
    return lib, pat


def resolve_direction(lib, direction):
    """方向名归一化：支持别名（铀矿 / 管廊 / 盾构 …）。"""
    if not direction:
        return None, None
    d = direction.strip()
    dirs = lib.get("directions", {})
    if d in dirs:
        return d, dirs[d]
    for name, data in dirs.items():
        if d == name or d in data.get("aliases", []):
            return name, data
        for a in data.get("aliases", []):
            if a and (a in d or d in a):
                return name, data
    return None, None


# --------------------------------------------------------------------------
# 构造报告数据
# --------------------------------------------------------------------------
def blank_case():
    return {
        "title": TODO, "project": TODO, "year": TODO, "source": TODO,
        "url": "", "problem": TODO, "modeling_points": [TODO], "fit": TODO,
    }


def default_modeling_plan(pat, direction_name):
    by_dir = pat.get("modeling_plan_templates", {}).get("by_direction", {})
    tpl = by_dir.get(direction_name) or pat.get("modeling_plan_templates", {}).get("generic", {})
    return {
        "scope": list(tpl.get("scope", [])),
        "software": list(tpl.get("software", [])),
        "lod": tpl.get("lod", TODO),
        "difficulty": tpl.get("difficulty", TODO),
        "notes": [tpl["extra"]] if tpl.get("extra") else [],
    }


def default_deliverables(pat):
    out = []
    for d in pat.get("deliverable_templates", {}).get("common", []):
        out.append({"item": d.get("item", ""), "metric": d.get("metric", ""), "note": d.get("note", "")})
    return out


def default_team(pat):
    return [dict(x) for x in pat.get("team_role_templates", [])]


def default_schedule(pat):
    return [dict(x) for x in pat.get("schedule_template", [])]


def default_risks(pat):
    return [dict(x) for x in pat.get("risk_templates", [])]


def build_from_direction(lib, pat, direction, project_name, top_n=3):
    """从种子库拉案例，生成草稿数据。"""
    name, data = resolve_direction(lib, direction)
    display_dir = name or direction
    cases = []
    if data:
        for c in data.get("cases", [])[:top_n]:
            cases.append({
                "title": c.get("title", TODO),
                "project": c.get("project", TODO),
                "year": c.get("year", TODO),
                "source": c.get("source", TODO),
                "url": c.get("url", ""),
                "problem": c.get("problem", TODO),
                "modeling_points": list(c.get("modeling_points", [])),
                "fit": c.get("fit_for_topic", ""),
                "data_points": list(c.get("data_points", [])),
            })
    while len(cases) < top_n:
        cases.append(blank_case())

    return {
        "direction": display_dir,
        "direction_in_library": bool(name),
        "project_name": project_name or "〔项目名称〕",
        "topic_name": TODO,
        "alt_titles": [],
        "rationale": {
            "case_support": TODO, "pain_point": TODO,
            "feasibility": TODO, "innovation": TODO,
        },
        "search_log": [],
        "search_note": (
            "本报告的案例来自种子库（均附来源 URL，可复核）。"
            "交付前须按 references/search-playbook.md 做一次联网复核，确认信息时效性并补全检索记录。"
            if name else
            "该方向不在种子库内，必须按 references/search-playbook.md 联网检索后填充案例，禁止凭记忆编造。"
        ),
        "cases": cases,
        "modeling_plan": default_modeling_plan(pat, name),
        "deliverables": default_deliverables(pat),
        "team": default_team(pat),
        "schedule": default_schedule(pat),
        "risks": default_risks(pat),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_mode": "种子库草稿",
    }


def build_from_input(lib, pat, payload):
    """用外部 JSON 补全/覆盖默认值。"""
    direction = payload.get("direction", "〔方向〕")
    name, _ = resolve_direction(lib, direction)

    data = {
        "direction": direction,
        "direction_in_library": bool(name),
        "direction_scope": payload.get("direction_scope", ""),
        "direction_why": payload.get("direction_why", ""),
        "project_name": payload.get("project_name", "〔项目名称〕"),
        "topic_name": payload.get("topic_name", TODO),
        "alt_titles": payload.get("alt_titles", []),
        "rationale": payload.get("rationale", {}),
        "search_log": payload.get("search_log", []),
        "search_note": payload.get("search_note", ""),
        "cases": payload.get("cases", []),
        "modeling_plan": payload.get("modeling_plan") or default_modeling_plan(pat, name),
        "deliverables": payload.get("deliverables") or default_deliverables(pat),
        "team": payload.get("team") or default_team(pat),
        "schedule": payload.get("schedule") or default_schedule(pat),
        "risks": payload.get("risks") or default_risks(pat),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_mode": payload.get("source_mode", "联网检索"),
    }
    # rationale 缺失键补 TODO
    r = dict(data["rationale"] or {})
    for k in ("case_support", "pain_point", "feasibility", "innovation"):
        r.setdefault(k, TODO)
    data["rationale"] = r
    while len(data["cases"]) < 3:
        data["cases"].append(blank_case())
    return data


def build_template(pat):
    return {
        "direction": "〔调研方向，如：铀矿工程 / 地下综合管廊 / 盾构隧道 / 基坑支护 / 建筑工程〕",
        "direction_in_library": False,
        "project_name": "〔依托项目名称〕",
        "topic_name": "〔最终选题名称〕",
        "alt_titles": ["〔备选标题 1〕", "〔备选标题 2〕", "〔备选标题 3〕"],
        "rationale": {"case_support": TODO, "pain_point": TODO, "feasibility": TODO, "innovation": TODO},
        "search_log": [],
        "search_note": "按 references/search-playbook.md 填写检索式、来源与筛选过程；每条案例都要能回溯到原始出处。",
        "cases": [blank_case(), blank_case(), blank_case()],
        "modeling_plan": default_modeling_plan(pat, None),
        "deliverables": default_deliverables(pat),
        "team": default_team(pat),
        "schedule": default_schedule(pat),
        "risks": default_risks(pat),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_mode": "空白模板",
    }


# --------------------------------------------------------------------------
# Markdown 渲染
# --------------------------------------------------------------------------
def md_table(headers, rows):
    if not rows:
        return "_（无）_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("\n", " ") for x in r) + " |")
    return "\n".join(out) + "\n"


def render_markdown(d, pat):
    sec = {s["key"]: s["title"] for s in pat["required_sections"]}
    L = []
    A = L.append
    title = d["topic_name"] if d["topic_name"] != TODO else f"{d['direction']}方向 BIM 选题调研报告"
    A(f"# {title}\n")
    A(f"> 依托项目：{d['project_name']}　|　调研方向：{d['direction']}　|　生成时间：{d['generated_at']}　|　数据来源：{d['source_mode']}\n")
    A("")

    # 一、调研方向
    A(f"## {sec['direction']}\n")
    A(f"**方向**：{d['direction']}")
    if d.get("direction_in_library"):
        A(f"　（已命中种子案例库）")
    A("")
    A("**范围界定**：" + (d.get("direction_scope") or TODO + "（说明本方向包含哪些工程类型、边界在哪，避免选题范围过大）"))
    A("")
    A("**为什么值得做**：" + (d.get("direction_why") or TODO))
    A("")

    # 二、选题名称
    A(f"## {sec['topic_name']}\n")
    A(f"**拟定选题**：{d['topic_name']}\n")
    if d.get("alt_titles"):
        A("**备选标题**：")
        for i, t in enumerate(d["alt_titles"], 1):
            A(f"{i}. {t}")
        A("")
    A("**命名参考**（来自 assets/topic_patterns.json）：\n")
    rows = [[p["pattern"], p.get("example", ""), p.get("difficulty", "")] for p in pat.get("topic_naming_patterns", [])]
    A(md_table(["命名模式", "示例", "难度"], rows))

    # 三、选题理由
    A(f"## {sec['rationale']}\n")
    r = d["rationale"]
    A(f"**1. 案例支撑**：{r['case_support']}\n")
    A(f"**2. 痛点真实**：{r['pain_point']}\n")
    A(f"**3. 可行性**：{r['feasibility']}\n")
    A(f"**4. 创新点**：{r['innovation']}\n")
    A("> 四条论据缺一不可。只有「案例支撑」没有「痛点真实」＝跟风；只有「痛点」没有「可行性」＝空中楼阁。\n")

    # 四、AI 检索记录
    A(f"## {sec['search_log']}\n")
    if d.get("search_note"):
        A(f"> {d['search_note']}\n")
    rows = []
    for i, s in enumerate(d.get("search_log", []), 1):
        rows.append([i, s.get("query", ""), s.get("source", ""), s.get("window", ""),
                     s.get("hits", ""), s.get("kept", ""), s.get("note", "")])
    A(md_table(["序号", "检索式", "检索源", "时间范围", "命中数", "采用数", "筛选说明"], rows))
    A("**证据强度分级**：\n")
    A(md_table(["等级", "说明"], [[g["grade"], g["desc"]] for g in pat.get("search_log_schema", {}).get("evidence_grades", [])]))

    # 五、典型案例
    A(f"## {sec['cases']}\n")
    for i, c in enumerate(d["cases"], 1):
        A(f"### 案例 {i}：{c.get('title', TODO)}\n")
        A(f"- **项目**：{c.get('project', TODO)}")
        A(f"- **年份**：{c.get('year', TODO)}")
        src = c.get("source", TODO)
        url = c.get("url", "")
        A(f"- **来源**：{src}" + (f"　<{url}>" if url else "　〔⚠ 无来源 URL，须补全后再交付〕"))
        A("")
        A(f"**解决了什么问题**\n\n{c.get('problem', TODO)}\n")
        A("**可借鉴的建模点**\n")
        for mp in c.get("modeling_points", []):
            A(f"- {mp}")
        A("")
        if c.get("data_points"):
            A("**可引用的关键数据**\n")
            for dp in c["data_points"]:
                A(f"- {dp}")
            A("")
        if c.get("fit"):
            A(f"**选题适配建议**：{c['fit']}\n")

    # 六、建模设想
    A(f"## {sec['modeling_plan']}\n")
    mp = d["modeling_plan"]
    A("**建模范围**\n")
    for s in mp.get("scope", []):
        A(f"- {s}")
    A("")
    A("**软件路线**：" + "、".join(mp.get("software", [])) if mp.get("software") else "**软件路线**：" + TODO)
    A("")
    A(f"**模型深度**：{mp.get('lod', TODO)}\n")
    A(f"**关键难点**：{mp.get('difficulty', TODO)}\n")
    for n in mp.get("notes", []) or []:
        A(f"> ⚠ {n}\n")

    # 七、预期成果
    A(f"## {sec['deliverables']}\n")
    rows = [[x.get("item", ""), x.get("metric", ""), x.get("note", "")] for x in d["deliverables"]]
    A(md_table(["成果物", "可量化指标", "说明"], rows))
    A("> 指标必须可量化。写「提高效率」等于没写，写「碰撞点从 N 处降至 M 处」才算数。\n")

    # 八、分工与进度
    A(f"## {sec['team_and_schedule']}\n")
    A("### 8.1 小组分工\n")
    A(md_table(["角色", "职责", "人数"], [[x.get("role", ""), x.get("duty", ""), x.get("ratio", "")] for x in d["team"]]))
    A("### 8.2 进度计划\n")
    A(md_table(["阶段", "任务", "阶段成果"], [[x.get("phase", ""), x.get("task", ""), x.get("output", "")] for x in d["schedule"]]))

    # 九、风险与对策
    A(f"## {sec['risks']}\n")
    A(md_table(["类别", "风险", "对策", "等级"], [[x.get("category", ""), x.get("risk", ""), x.get("counter", ""), x.get("level", "")] for x in d["risks"]]))

    A("---\n")
    A(f"_本报告由 BIM 选题调研助手生成于 {d['generated_at']}。案例信息均附来源，引用前请回溯原始出处核验。_")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# HTML 渲染
# --------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
 background:#F5F6F8;color:#1F2328;line-height:1.75}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:26px;margin:0 0 8px;color:#0B4F8A;letter-spacing:.5px}
h2{font-size:19px;margin:34px 0 14px;padding-bottom:8px;border-bottom:2px solid #0B4F8A;color:#0B4F8A}
h3{font-size:16px;margin:22px 0 10px;color:#153B5C}
.head,.card{background:#fff;border:1px solid #E3E6EA;border-radius:8px;padding:20px 24px;
 box-shadow:0 1px 3px rgba(0,0,0,.04);margin-bottom:18px}
.head{border-left:4px solid #0B4F8A}
.meta{font-size:13px;color:#5A6472;margin-top:6px}
table{width:100%;border-collapse:collapse;margin:10px 0 16px;font-size:13.5px;background:#fff}
th{background:#EEF3F8;color:#153B5C;font-weight:600;text-align:left;padding:9px 11px;border:1px solid #DDE3E9}
td{padding:9px 11px;border:1px solid #DDE3E9;vertical-align:top}
tbody tr:nth-child(even){background:#FAFBFD}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;margin-left:6px;vertical-align:middle}
.tag.ok{background:#E3F4E8;color:#1B7A3D;border:1px solid #B5E0C4}
.tag.warn{background:#FDF0E3;color:#A85B12;border:1px solid #F2D3AC}
.tag.bad{background:#FCE9E9;color:#B02A2A;border:1px solid #F2C4C4}
ul{margin:8px 0 14px;padding-left:22px}
li{margin:5px 0}
.note{background:#FFF9E8;border-left:4px solid #E0A800;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13.5px;margin:12px 0}
.src{font-size:12.5px;color:#5A6472;word-break:break-all}
.todo{color:#B02A2A;font-weight:600}
.alt{color:#5A6472;font-size:13.5px;margin:6px 0 0 0;padding-left:18px}
.foot{text-align:center;font-size:12.5px;color:#8A94A2;margin-top:26px}
@media print{body{background:#fff;padding:0}.wrap{max-width:none}.card,.head{box-shadow:none;break-inside:avoid}
 h2{break-after:avoid}}
"""


def esc(v):
    return html.escape(str(v if v is not None else ""))


def hl_todo(s):
    """把〔待补充〕标红，提醒交付前必须填。"""
    return esc(s).replace(esc(TODO), f"<span class='todo'>{esc(TODO)}</span>")


def html_table(headers, rows):
    if not rows:
        return "<p class='alt'>（无）</p>"
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def render_html(d, pat):
    sec = {s["key"]: s["title"] for s in pat["required_sections"]}
    title = d["topic_name"] if d["topic_name"] != TODO else f"{d['direction']}方向 BIM 选题调研报告"
    P = []
    A = P.append

    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A(f"<title>{esc(title)}</title><style>{CSS}</style></head><body><div class='wrap'>")

    status = ("<span class='tag ok'>已命中种子案例库</span>" if d.get("direction_in_library")
              else "<span class='tag warn'>方向未在库内·需联网检索</span>")
    A("<div class='head'>")
    A(f"<h1>{hl_todo(title)}</h1>")
    A(f"<div class='meta'>依托项目：{esc(d['project_name'])}　|　调研方向：{esc(d['direction'])}{status}"
      f"　|　生成时间：{esc(d['generated_at'])}　|　数据来源：{esc(d['source_mode'])}</div>")
    A("</div>")

    # 一
    A(f"<h2>{esc(sec['direction'])}</h2><div class='card'>")
    A(f"<p><b>方向</b>：{esc(d['direction'])}</p>")
    A(f"<p><b>范围界定</b>：{hl_todo(d.get('direction_scope') or TODO + '（本方向包含哪些工程类型、边界在哪，范围过大会做不完）')}</p>")
    A(f"<p><b>为什么值得做</b>：{hl_todo(d.get('direction_why') or TODO)}</p></div>")

    # 二
    A(f"<h2>{esc(sec['topic_name'])}</h2><div class='card'>")
    A(f"<p><b>拟定选题</b>：{hl_todo(d['topic_name'])}</p>")
    if d.get("alt_titles"):
        A("<p><b>备选标题</b></p><ul>" + "".join(f"<li>{hl_todo(t)}</li>" for t in d["alt_titles"]) + "</ul>")
    rows = [[esc(p["pattern"]), esc(p.get("example", "")), esc(p.get("difficulty", ""))] for p in pat.get("topic_naming_patterns", [])]
    A("<p><b>命名模式参考</b></p>" + html_table(["命名模式", "示例", "难度"], rows))
    A("</div>")

    # 三
    A(f"<h2>{esc(sec['rationale'])}</h2><div class='card'>")
    r = d["rationale"]
    for label, key in [("1. 案例支撑", "case_support"), ("2. 痛点真实", "pain_point"),
                       ("3. 可行性", "feasibility"), ("4. 创新点", "innovation")]:
        A(f"<p><b>{label}</b>：{hl_todo(r.get(key, TODO))}</p>")
    A("<div class='note'>四条论据缺一不可。只有「案例支撑」没有「痛点真实」＝跟风；只有「痛点」没有「可行性」＝空中楼阁。</div>")
    A("</div>")

    # 四
    A(f"<h2>{esc(sec['search_log'])}</h2><div class='card'>")
    if d.get("search_note"):
        A(f"<div class='note'>{esc(d['search_note'])}</div>")
    rows = []
    for i, s in enumerate(d.get("search_log", []), 1):
        rows.append([esc(i), esc(s.get("query", "")), esc(s.get("source", "")), esc(s.get("window", "")),
                     esc(s.get("hits", "")), esc(s.get("kept", "")), esc(s.get("note", ""))])
    A(html_table(["序号", "检索式", "检索源", "时间范围", "命中数", "采用数", "筛选说明"], rows))
    A("<p><b>证据强度分级</b></p>")
    A(html_table(["等级", "说明"], [[esc(g["grade"]), esc(g["desc"])] for g in pat.get("search_log_schema", {}).get("evidence_grades", [])]))
    A("</div>")

    # 五
    A(f"<h2>{esc(sec['cases'])}</h2>")
    for i, c in enumerate(d["cases"], 1):
        A("<div class='card'>")
        A(f"<h3>案例 {i}：{hl_todo(c.get('title', TODO))}</h3>")
        url = c.get("url", "")
        src_txt = esc(c.get("source", TODO))
        if url:
            src_txt += f"　<a class='src' href='{esc(url)}' target='_blank'>{esc(url)}</a>"
        else:
            src_txt += "　<span class='tag bad'>缺少来源 URL·交付前须补全</span>"
        A(f"<p><b>项目</b>：{hl_todo(c.get('project', TODO))}　|　<b>年份</b>：{hl_todo(c.get('year', TODO))}<br>"
          f"<b>来源</b>：{src_txt}</p>")
        A(f"<p><b>解决了什么问题</b></p><p>{hl_todo(c.get('problem', TODO))}</p>")
        A("<p><b>可借鉴的建模点</b></p><ul>" +
          "".join(f"<li>{hl_todo(m)}</li>" for m in c.get("modeling_points", [])) + "</ul>")
        if c.get("data_points"):
            A("<p><b>可引用的关键数据</b></p><ul>" +
              "".join(f"<li>{esc(dp)}</li>" for dp in c["data_points"]) + "</ul>")
        if c.get("fit"):
            A(f"<div class='note'>{esc(c['fit'])}</div>")
        A("</div>")

    # 六
    A(f"<h2>{esc(sec['modeling_plan'])}</h2><div class='card'>")
    mp = d["modeling_plan"]
    A("<p><b>建模范围</b></p><ul>" + "".join(f"<li>{esc(s)}</li>" for s in mp.get("scope", [])) + "</ul>")
    A(f"<p><b>软件路线</b>：{esc('、'.join(mp.get('software', [])) or TODO)}</p>")
    A(f"<p><b>模型深度</b>：{esc(mp.get('lod', TODO))}</p>")
    A(f"<p><b>关键难点</b>：{esc(mp.get('difficulty', TODO))}</p>")
    for n in mp.get("notes", []) or []:
        A(f"<div class='note'>⚠ {esc(n)}</div>")
    A("</div>")

    # 七
    A(f"<h2>{esc(sec['deliverables'])}</h2><div class='card'>")
    A(html_table(["成果物", "可量化指标", "说明"],
                 [[esc(x.get("item", "")), esc(x.get("metric", "")), esc(x.get("note", ""))] for x in d["deliverables"]]))
    A("<div class='note'>指标必须可量化。写「提高效率」等于没写，写「碰撞点从 N 处降至 M 处」才算数。</div></div>")

    # 八
    A(f"<h2>{esc(sec['team_and_schedule'])}</h2><div class='card'>")
    A("<h3>8.1 小组分工</h3>")
    A(html_table(["角色", "职责", "人数"],
                 [[esc(x.get("role", "")), esc(x.get("duty", "")), esc(x.get("ratio", ""))] for x in d["team"]]))
    A("<h3>8.2 进度计划</h3>")
    A(html_table(["阶段", "任务", "阶段成果"],
                 [[esc(x.get("phase", "")), esc(x.get("task", "")), esc(x.get("output", ""))] for x in d["schedule"]]))
    A("</div>")

    # 九
    A(f"<h2>{esc(sec['risks'])}</h2><div class='card'>")
    A(html_table(["类别", "风险", "对策", "等级"],
                 [[esc(x.get("category", "")), esc(x.get("risk", "")), esc(x.get("counter", "")), esc(x.get("level", ""))]
                  for x in d["risks"]]))
    A("</div>")

    A(f"<div class='foot'>本报告由 BIM 选题调研助手生成于 {esc(d['generated_at'])}　·　案例信息均附来源，引用前请回溯原始出处核验</div>")
    A("</div></body></html>")
    return "\n".join(P)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "报告"


def write_outputs(d, pat, outdir, base):
    os.makedirs(outdir, exist_ok=True)
    md_path = os.path.join(outdir, f"{base}_选题报告.md")
    html_path = os.path.join(outdir, f"{base}_选题报告.html")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(d, pat))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(d, pat))
    return md_path, html_path


def cmd_list(lib):
    dirs = lib.get("directions", {})
    print(f"种子案例库共 {len(dirs)} 个方向：\n")
    for name, data in dirs.items():
        aliases = "、".join(data.get("aliases", [])[:6])
        print(f"● {name}（别名：{aliases}）")
        for c in data.get("cases", []):
            print(f"    · [{c.get('year','')}] {c.get('title','')}")
            print(f"      来源：{c.get('source','')}")
            print(f"      {c.get('url','')}")
        print()
    fb = lib.get("generic_fallback", {})
    print(f"◎ 未收录方向：走 generic_fallback 模板联网检索")
    print(f"  典型痛点：{len(fb.get('typical_problem_categories', []))} 类 | 典型建模点：{len(fb.get('typical_modeling_points', []))} 个")


def main():
    ap = argparse.ArgumentParser(description="BIM 选题调研报告生成器")
    ap.add_argument("--list", action="store_true", help="列出种子案例库覆盖的方向与案例")
    ap.add_argument("--direction", help="调研方向（支持别名）")
    ap.add_argument("--project", default="", help="依托项目名称")
    ap.add_argument("--name", default="", help="输出文件基础名，默认取项目名")
    ap.add_argument("--input", help="结构化检索结果 JSON（主路径）")
    ap.add_argument("--template", action="store_true", help="输出空白选题报告模板")
    ap.add_argument("--top", type=int, default=3, help="案例数，默认 3")
    ap.add_argument("-o", "--out", default=".", help="输出目录")
    ap.add_argument("--json-only", action="store_true", help="只打印结构化结果，不写文件")
    args = ap.parse_args()

    lib, pat = load_assets()

    if args.list:
        cmd_list(lib)
        return

    if args.template:
        d = build_template(pat)
        base = safe_name(args.name or "BIM选题报告模板")
        if args.json_only:
            print(json.dumps(d, ensure_ascii=False, indent=2))
            return
        md, htm = write_outputs(d, pat, args.out, base)
        print(json.dumps({"ok": True, "mode": "template", "markdown": md, "html": htm,
                          "sections": len(pat["required_sections"])}, ensure_ascii=False))
        return

    if args.input:
        if not os.path.exists(args.input):
            print(json.dumps({"ok": False, "error": f"输入文件不存在：{args.input}"}, ensure_ascii=False))
            sys.exit(2)
        payload = load_json(args.input)
        d = build_from_input(lib, pat, payload)
    elif args.direction:
        d = build_from_direction(lib, pat, args.direction, args.project, args.top)
    else:
        print(json.dumps({"ok": False, "error": "需要 --list / --direction / --input / --template 之一"}, ensure_ascii=False))
        sys.exit(2)

    base = safe_name(args.name or d.get("project_name") or f"{d['direction']}_选题")
    if args.json_only:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return

    md, htm = write_outputs(d, pat, args.out, base)
    missing = sum(1 for c in d["cases"] if not c.get("url"))
    print(json.dumps({
        "ok": True,
        "mode": d.get("source_mode"),
        "direction": d["direction"],
        "direction_in_library": d.get("direction_in_library"),
        "cases": len(d["cases"]),
        "cases_without_url": missing,
        "sections": len(pat["required_sections"]),
        "markdown": md,
        "html": htm,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
