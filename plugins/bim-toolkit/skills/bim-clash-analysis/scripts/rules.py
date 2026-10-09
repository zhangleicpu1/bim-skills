# -*- coding: utf-8 -*-
"""碰撞分类与严重程度判级。

输入：parsers.py 产出的原始记录
输出：补全 discipline / category / level / clash_type / severity 的富记录

规则全部来自 assets/severity_rules.json，可由用户直接编辑后重跑。
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parsers as _parsers  # noqa: E402

DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "severity_rules.json",
)

_FALLBACK_RULES = {
    "clash_type_base": {"硬碰撞": 5.0, "间隙碰撞": 3.0, "重复项": 1.0, "未知": 4.0},
    "discipline_priority": {"未知": 5},
    "cross_discipline_bonus": 1.5,
    "distance_model": {"hard_penetration_ref_mm": 30, "clearance_ref_gap_mm": 50, "cap": 3.0},
    "key_level_keywords": ["设备层", "避难层", "地下室", "机房", "屋面", "核心筒", "车库"],
    "key_level_bonus": 1.0,
    "severity_thresholds": {"P0": 13.0, "P1": 10.5, "P2": 7.5},
    "severity_labels": {"P0": "严重", "P1": "高", "P2": "中", "P3": "低"},
    "discipline_keywords": {},
    "category_keywords": {},
    "remediation_rules": [],
    "default_remediation": "建议由相关专业联合复核，确定避让或开洞方案，并在模型更新后重新检测确认。",
}


def load_rules(path: str | None = None) -> dict:
    rules = json.loads(json.dumps(_FALLBACK_RULES))
    target = path or DEFAULT_RULES_PATH
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k.startswith("//") or k.startswith("_"):
                continue
            rules[k] = v
    return rules


# ==========================================================================
# 文本匹配打分
# ==========================================================================
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).lower()


def _score_keywords(text: str, keyword_map: dict) -> tuple[str, float]:
    """对一组 '标签 -> [关键词]' 打分，返回得分最高的标签。

    长关键词命中权重更高，避免 "管" 压过 "风管"。
    """
    t = _norm(text)
    if not t:
        return "", 0.0
    best_label, best_score = "", 0.0
    for label, keywords in keyword_map.items():
        score = 0.0
        for kw in keywords:
            k = _norm(kw)
            if k and k in t:
                score += len(k) * 1.0
        if score > best_score:
            best_label, best_score = label, score
    return best_label, best_score


def classify_discipline(item: dict, rules: dict) -> str:
    """判定构件所属专业。先看名称+类型，再退回路径。"""
    kw = rules.get("discipline_keywords", {})
    label, score = _score_keywords(f"{item.get('name','')} {item.get('type','')}", kw)
    if score > 0:
        return label
    label, score = _score_keywords(item.get("path", ""), kw)
    if score > 0:
        return label
    return "未知"


def classify_category(item: dict, rules: dict) -> str:
    """判定构件类别（梁/柱/管道/风管/桥架 ...）。"""
    label, score = _score_keywords(f"{item.get('name','')} {item.get('type','')}",
                                   rules.get("category_keywords", {}))
    return label if score > 0 else "其他"


_LEVEL_RE = re.compile(
    r"(屋面层?|机房层|设备层|避难层?|夹层|转换层|首层|一层|地下[一二三四五六\d]*层|"
    r"B\d{1,2}|F?\d{1,2}F|F\d{1,2}|-\d{1,2}\.\d{3})",
    re.I,
)


def infer_level(rec: dict, rules: dict) -> str:
    """楼层：优先用报告自带字段，否则从轴网/构件路径里猜。"""
    explicit = rec.get("level") or ""
    if explicit:
        return re.sub(r"\s+", " ", str(explicit)).strip()
    grid = str(rec.get("grid") or "")
    m = _LEVEL_RE.search(grid)
    if m:
        return m.group(1)
    for key in ("item1", "item2"):
        blob = " ".join(str(v) for v in (rec.get(key) or {}).values())
        m = _LEVEL_RE.search(blob)
        if m:
            return m.group(1)
    return "未标注"


# ==========================================================================
# 碰撞类型
# ==========================================================================
_HARD_RE = re.compile(r"硬碰撞|硬撞|hard\s*clash|硬", re.I)
_CLEAR_RE = re.compile(r"间隙|净距|软碰撞|clearance|软", re.I)
_DUP_RE = re.compile(r"重复|重叠|duplicate|dupl|相同", re.I)


def infer_clash_type(rec: dict) -> str:
    """判定硬碰撞 / 间隙碰撞 / 重复项。

    1) 优先用报告显式给出的检测方式（clashmethod / 碰撞类型列）
    2) 其次用碰撞测试名推断
    3) 最后按 Navisworks 距离符号推断：负值=穿透（硬碰撞），正值=净距（间隙碰撞）
    """
    for candidate in (rec.get("clash_type"), rec.get("_clash_test"), rec.get("clash_test")):
        text = str(candidate or "")
        if not text:
            continue
        if _DUP_RE.search(text):
            return "重复项"
        if _CLEAR_RE.search(text):
            return "间隙碰撞"
        if _HARD_RE.search(text):
            return "硬碰撞"

    dist = rec.get("distance_m")
    if dist is None:
        return "未知"
    return "硬碰撞" if dist < 0 else "间隙碰撞"


# ==========================================================================
# 严重程度
# ==========================================================================
def _distance_component(rec: dict, clash_type: str, rules: dict) -> tuple[float, str]:
    dm = rules.get("distance_model", {})
    cap = float(dm.get("cap", 3.0))
    dist = rec.get("distance_m")
    if dist is None:
        return 0.0, "距离未知"

    if clash_type == "重复项":
        return 0.0, "重复项不计距离"

    if clash_type == "间隙碰撞":
        ref = float(dm.get("clearance_ref_gap_mm", 50)) or 50.0
        gap = abs(dist) * 1000.0
        ratio = max(0.0, min(1.0, (ref - gap) / ref))
        return cap * ratio, f"净距 {gap:.1f}mm（参考值 {ref:.0f}mm）"

    ref = float(dm.get("hard_penetration_ref_mm", 30)) or 30.0
    pen = abs(dist) * 1000.0
    ratio = max(0.0, min(1.0, pen / ref))
    return cap * ratio, f"穿透 {pen:.1f}mm（参考值 {ref:.0f}mm）"


def score_record(rec: dict, rules: dict) -> dict:
    """计算严重度分值并给出等级、理由。写回富字段。"""
    d1, d2 = rec.get("item1", {}).get("discipline", "未知"), rec.get("item2", {}).get("discipline", "未知")
    priorities = rules.get("discipline_priority", {}) or {"未知": 5}
    p1 = float(priorities.get(d1, priorities.get("未知", 5)))
    p2 = float(priorities.get(d2, priorities.get("未知", 5)))
    p_all = [float(v) for v in priorities.values()] or [5.0]
    p_min, p_max = min(p_all), max(p_all)
    p_top = max(p1, p2)
    span = (p_max - p_min) or 1.0
    prio_component = (p_top - p_min) / span * 4.0

    clash_type = rec.get("clash_type", "未知")
    type_base = float((rules.get("clash_type_base") or {}).get(clash_type, 4.0))

    known = {"未知", ""}
    cross = (float(rules.get("cross_discipline_bonus", 1.5))
             if d1 not in known and d2 not in known and d1 != d2 else 0.0)

    dist_component, dist_reason = _distance_component(rec, clash_type, rules)

    level = str(rec.get("level") or "")
    key_hit = next((k for k in rules.get("key_level_keywords", []) if k and k in level), "")
    level_component = float(rules.get("key_level_bonus", 1.0)) if key_hit else 0.0

    score = type_base + prio_component + cross + dist_component + level_component
    rec["severity_score"] = round(score, 2)

    thresholds = rules.get("severity_thresholds", {}) or {}
    labels = rules.get("severity_labels", {}) or {}
    grade = "P3"
    if score >= float(thresholds.get("P0", 11.0)):
        grade = "P0"
    elif score >= float(thresholds.get("P1", 8.5)):
        grade = "P1"
    elif score >= float(thresholds.get("P2", 6.0)):
        grade = "P2"
    rec["severity_grade"] = grade
    rec["severity"] = labels.get(grade, grade)

    reasons = [f"碰撞类型：{clash_type}（基础分 {type_base:g}）",
               f"专业组合：{d1} × {d2}（最高优先级 {p_top:g} → {prio_component:.2f}）",
               f"距离影响：{dist_reason} → {dist_component:.2f}"]
    if cross:
        reasons.append(f"跨专业协调难度加分 +{cross:g}")
    if key_hit:
        reasons.append(f"关键区域「{key_hit}」加分 +{level_component:g}")
    rec["severity_reason"] = "；".join(reasons)

    rec["suggestion"] = build_suggestion(rec, rules)
    return rec


def build_suggestion(rec: dict, rules: dict) -> str:
    d1 = rec.get("item1", {}).get("discipline", "未知")
    d2 = rec.get("item2", {}).get("discipline", "未知")
    pair = {d1, d2}
    for rule in rules.get("remediation_rules", []):
        need = set(rule.get("disciplines", []))
        if not need:
            continue
        mode = rule.get("mode", "exact")
        if mode == "any" and (need & pair):
            return rule.get("advice", "").strip()
        if mode != "any" and need <= pair:
            return rule.get("advice", "").strip()
    return rules.get("default_remediation", "").strip()


# ==========================================================================
# 主处理
# ==========================================================================
def enrich(raw_records: list[dict], rules: dict) -> list[dict]:
    enriched = []
    for raw in raw_records:
        rec = dict(raw)
        rec["distance_m"] = _as_float(raw.get("distance_m"))
        if rec["distance_m"] is None:
            rec["distance_m"] = _parsers.parse_distance(raw.get("distance"))
        rec["clash_type"] = raw.get("clash_type") or infer_clash_type(rec)
        if rec["clash_type"] not in ("硬碰撞", "间隙碰撞", "重复项"):
            rec["clash_type"] = infer_clash_type(rec)

        for key in ("item1", "item2"):
            item = dict(rec.get(key) or {})
            item.setdefault("name", "")
            item.setdefault("path", "")
            item.setdefault("type", "")
            item["discipline"] = classify_discipline(item, rules)
            item["category"] = classify_category(item, rules)
            rec[key] = item

        rec["level"] = infer_level(rec, rules)

        discs = sorted({rec["item1"]["discipline"], rec["item2"]["discipline"]})
        rec["discipline_pair"] = " × ".join(discs)
        cats = sorted({rec["item1"]["category"], rec["item2"]["category"]})
        rec["category_pair"] = " × ".join(cats)

        rec["status"] = _norm_status(raw.get("status", ""))
        rec["is_open"] = _is_open(raw.get("status", ""))

        rec["clash_point_str"] = _format_point(raw.get("clash_point"))
        rec["distance_str"] = _format_distance(rec["distance_m"])

        score_record(rec, rules)
        enriched.append(rec)
    return enriched


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _format_point(point) -> str:
    if not isinstance(point, dict):
        return ""
    vals = [point.get("x"), point.get("y"), point.get("z")]
    if all(v is None for v in vals):
        return ""
    return " / ".join("—" if v is None else f"{v:.3f}" for v in vals)


def _format_distance(d) -> str:
    if d is None:
        return "—"
    return f"{d * 1000:.1f} mm"


def _norm_status(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or "未知"


def _is_open(value) -> bool:
    text = str(value or "")
    if not text:
        return True
    if re.search(r"resolved|approved|已解决|已批准|已关闭|已确认|通过|closed|solved|完成|忽略|ignored", text, re.I):
        return False
    return True


# ==========================================================================
# 汇总
# ==========================================================================
def _count_by(records, key_fn, order=None):
    buckets: dict = {}
    for rec in records:
        k = key_fn(rec)
        if k in (None, ""):
            k = "未知"
        buckets[k] = buckets.get(k, 0) + 1
    items = list(buckets.items())
    if order:
        idx = {k: i for i, k in enumerate(order)}
        items.sort(key=lambda kv: (idx.get(kv[0], len(order)), -kv[1]))
    else:
        items.sort(key=lambda kv: -kv[1])
    return [{"key": k, "count": v} for k, v in items]


def summarize(records: list[dict], rules: dict) -> dict:
    labels = rules.get("severity_labels", {})
    grade_order = ["P0", "P1", "P2", "P3"]
    by_grade = _count_by(records, lambda r: r["severity_grade"], order=grade_order)
    for row in by_grade:
        row["label"] = labels.get(row["key"], row["key"])
        row["ratio"] = row["count"] / len(records) if records else 0.0

    by_type = _count_by(records, lambda r: r["clash_type"],
                        order=["硬碰撞", "间隙碰撞", "重复项", "未知"])
    for row in by_type:
        row["ratio"] = row["count"] / len(records) if records else 0.0

    by_pair = _count_by(records, lambda r: r["discipline_pair"])
    disc_counter: dict = {}
    for rec in records:
        for key in ("item1", "item2"):
            d = rec[key]["discipline"]
            disc_counter[d] = disc_counter.get(d, 0) + 1
    by_discipline = [{"key": k, "count": v}
                     for k, v in sorted(disc_counter.items(), key=lambda kv: -kv[1])]

    by_category_pair = _count_by(records, lambda r: r["category_pair"])
    by_level = _count_by(records, lambda r: r["level"])
    by_test = _count_by(records, lambda r: r["_clash_test"] or "未分组")
    by_status = _count_by(records, lambda r: r["status"])

    top_items: dict = {}
    for rec in records:
        for key in ("item1", "item2"):
            name = rec[key]["name"]
            if not name:
                continue
            entry = top_items.setdefault(name, {"name": name, "count": 0,
                                                "discipline": rec[key]["discipline"],
                                                "worst": "P3"})
            entry["count"] += 1
            if grade_order.index(rec["severity_grade"]) < grade_order.index(entry["worst"]):
                entry["worst"] = rec["severity_grade"]
    top_items_list = sorted(top_items.values(), key=lambda e: (-e["count"],
                                                               grade_order.index(e["worst"])))[:15]

    grade_counts = {row["key"]: row["count"] for row in by_grade}
    return {
        "total": len(records),
        "open_count": sum(1 for r in records if r["is_open"]),
        "by_severity": by_grade,
        "severity_counts": grade_counts,
        "by_clash_type": by_type,
        "by_discipline_pair": by_pair,
        "by_discipline": by_discipline,
        "by_category_pair": by_category_pair,
        "by_level": by_level,
        "by_test": by_test,
        "by_status": by_status,
        "top_items": top_items_list,
        "need_action": grade_counts.get("P0", 0) + grade_counts.get("P1", 0),
    }
