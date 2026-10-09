#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BIM 碰撞检测报告整理主程序。

用法：
    python clash_analyzer.py <碰撞报告文件> [-o 输出目录] [--rules 规则文件]
                            [--formats docx,xlsx,md] [--project 项目名称] [--top N]
                            [--min-severity 严重] [--quiet]

示例：
    python clash_analyzer.py report.html
    python clash_analyzer.py report.html -o ./output --formats docx,xlsx,md

输出（默认与源文件同目录）：
    <源文件名>_碰撞分析报告.docx
    <源文件名>_碰撞明细.xlsx
    <源文件名>_碰撞分析摘要.md
    <源文件名>_chart_*.png
并在 stdout 打印一份 JSON 摘要，便于上层流程读取关键结论。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parsers          # noqa: E402
import rules as rules_mod  # noqa: E402
import report_builder   # noqa: E402


def _pair_advice(records: list[dict], rules: dict) -> dict:
    out: dict = {}
    for rec in records:
        pair = rec["discipline_pair"]
        if pair in out:
            continue
        out[pair] = rules_mod.build_suggestion(rec, rules)
    return out


def _rules_explain(rules: dict) -> list[str]:
    th = rules.get("severity_thresholds", {})
    labels = rules.get("severity_labels", {})
    tb = rules.get("clash_type_base", {})
    dm = rules.get("distance_model", {})
    pr = rules.get("discipline_priority", {})
    lines = [
        "判定模型：严重度分值 = 碰撞类型基础分 + 构件专业优先级分（0~4）+ 跨专业协调难度加分 + 距离影响分（0~3）+ 关键区域加分。",
        "碰撞类型基础分：" + "、".join(f"{k} {v:g}" for k, v in tb.items()) + "。",
        "专业优先级（分值越高越关键）：" + "、".join(
            f"{k} {v:g}" for k, v in sorted(pr.items(), key=lambda kv: -kv[1])) + "。",
        f"跨专业协调难度加分：碰撞双方属于不同专业时 +{rules.get('cross_discipline_bonus', 1.5):g}。",
        f"距离影响分（上限 {dm.get('cap', 3):g}）：硬碰撞按穿透深度线性计分，参考值 "
        f"{dm.get('hard_penetration_ref_mm', 30):g}mm；间隙碰撞按净距反向计分，参考值 "
        f"{dm.get('clearance_ref_gap_mm', 50):g}mm（净距越小越严重）；重复项不计距离分。",
        f"关键区域加分：碰撞点所在楼层含「{'、'.join(rules.get('key_level_keywords', []))}」"
        f"等关键词时 +{rules.get('key_level_bonus', 1):g}。",
        "等级阈值：" + "、".join(
            f"{labels.get(k, k)}（{k}）≥ {th.get(k)}" for k in ("P0", "P1", "P2")) + "，其余为低（P3）。",
        "自动化推断说明：碰撞类型优先取源报告的检测方式字段，缺省时按距离符号判断（负值=硬碰撞，正值=间隙碰撞）；"
        "楼层优先取源报告字段，缺省时从轴网与构件路径关键词推断；专业与构件类别依据构件名称/类型/路径的关键词库判定。",
        f"规则版本：{rules.get('version', '1.0')}；规则文件可编辑后重跑，评分与等级将同步更新。",
    ]
    return lines


def analyze(path: str, rules_path: str | None = None) -> dict:
    rules = rules_mod.load_rules(rules_path)
    parsed = parsers.parse_report(path)
    records = rules_mod.enrich(parsed["records"], rules)
    summary = rules_mod.summarize(records, rules)

    return {
        "source": parsed["source"],
        "format": parsed["format"],
        "project": parsed.get("project") or {},
        "title": parsed.get("title") or "",
        "tests": parsed.get("tests") or [],
        "records": records,
        "summary": summary,
        "diagnostics": parsed.get("diagnostics") or {},
        "rules_version": rules.get("version", "1.0"),
        "rules_explain": _rules_explain(rules),
        "pair_advice": _pair_advice(records, rules),
        "default_remediation": rules.get("default_remediation", ""),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BIM 碰撞检测报告整理")
    ap.add_argument("input", help="Navisworks 导出的碰撞报告（html/xml/csv/xlsx）")
    ap.add_argument("-o", "--outdir", default=None, help="输出目录，默认与源文件同目录")
    ap.add_argument("--rules", default=None, help="自定义规则 JSON 路径")
    ap.add_argument("--formats", default="docx,xlsx,md",
                    help="输出格式，逗号分隔，可选 docx,xlsx,md（默认全部）")
    ap.add_argument("--project", default=None, help="项目名称（覆盖报告内解析结果）")
    ap.add_argument("--min-severity", default=None, choices=["严重", "高", "中", "低"],
                    help="仅保留不低于该等级的碰撞（影响明细输出）")
    ap.add_argument("--top", type=int, default=30, help="重点清单条数，默认 30")
    ap.add_argument("--no-charts", action="store_true", help="不生成图表")
    ap.add_argument("--json-only", action="store_true", help="只输出 JSON，不生成文档")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print(json.dumps({"ok": False, "error": f"文件不存在：{args.input}"}, ensure_ascii=False))
        return 2

    out_dir = args.outdir or os.path.dirname(os.path.abspath(args.input)) or "."
    os.makedirs(out_dir, exist_ok=True)

    analysis = analyze(args.input, args.rules)
    if args.project:
        analysis["project"]["project"] = args.project

    if args.min_severity:
        keep = {"严重": {"P0"}, "高": {"P0", "P1"}, "中": {"P0", "P1", "P2"},
                "低": {"P0", "P1", "P2", "P3"}}[args.min_severity]
        analysis["records"] = [r for r in analysis["records"] if r["severity_grade"] in keep]
        analysis["summary"] = rules_mod.summarize(analysis["records"], rules_mod.load_rules(args.rules))

    if not analysis["records"]:
        print(json.dumps({
            "ok": False,
            "error": "未能从文件中解析出碰撞记录，请确认导出格式或提供报告样例以扩展解析规则。",
            "format": analysis["format"],
            "diagnostics": analysis["diagnostics"],
        }, ensure_ascii=False, indent=2))
        return 3

    requested = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    outputs: dict[str, str] = {}
    charts: list[str] = []

    if not args.json_only and not args.no_charts:
        charts = report_builder.make_charts(analysis, out_dir, report_builder._stem(analysis))

    if not args.json_only:
        if "md" in requested:
            outputs["markdown"] = report_builder.build_markdown(analysis, out_dir)
        if "xlsx" in requested or "excel" in requested:
            outputs["excel"] = report_builder.build_excel(analysis, out_dir)
        if "docx" in requested or "word" in requested:
            outputs["word"] = report_builder.build_docx(analysis, out_dir, charts)

    s = analysis["summary"]
    rank = {"P0": 0, "P1": 1}
    keyed = sorted([r for r in analysis["records"] if r["severity_grade"] in rank],
                   key=lambda r: (rank[r["severity_grade"]], -r["severity_score"]))
    result = {
        "ok": True,
        "source": analysis["source"],
        "format": analysis["format"],
        "outputs": outputs,
        "charts": charts,
        "stats": {
            "total": s["total"],
            "open": s["open_count"],
            "severity": {r["label"]: r["count"] for r in s["by_severity"]},
            "clash_type": {r["key"]: r["count"] for r in s["by_clash_type"]},
            "top_discipline_pairs": [{"pair": r["key"], "count": r["count"]}
                                     for r in s["by_discipline_pair"][:8]],
            "levels": [{"level": r["key"], "count": r["count"]} for r in s["by_level"][:8]],
            "need_action": s["need_action"],
        },
        "top_issues": [{
            "name": r["name"], "severity": r["severity"], "score": r["severity_score"],
            "clash_type": r["clash_type"], "pair": r["discipline_pair"], "level": r["level"],
            "item1": r["item1"]["name"], "item2": r["item2"]["name"],
            "distance": r["distance_str"], "suggestion": r["suggestion"],
        } for r in keyed[:args.top]],
        "diagnostics": analysis["diagnostics"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
