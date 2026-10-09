# -*- coding: utf-8 -*-
"""Navisworks 碰撞报告解析器。

支持格式：
  - HTML : Clash Detective 导出的 .html / .htm 报告（主路径）
  - XML  : Clash Detective「导出到 XML」(batchtest/clashtest/clashresult)
  - CSV  : 导出的平整表格 .csv / .tsv / .txt
  - XLSX : 导出的 .xlsx（逐 Sheet 当作平整表处理）

对外接口：
    parsed = parse_report(path)
    parsed["records"] -> [ {canonical_key: str|dict, ...}, ... ]

产出的是"原始字典"（字段已归一到规范键，但未做专业分类 / 判级）。
专业分类与判级由 rules.py 完成。
"""

from __future__ import annotations

import csv
import io
import os
import re
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# 字段别名表：canonical_key -> 该字段可能出现的标签写法
# 匹配时按标签长度倒序，避免 "Name" 抢先匹配 "Clash Test Name" 之类的长标签
# --------------------------------------------------------------------------
FIELD_ALIASES: dict[str, list[str]] = {
    "name": ["clash name", "碰撞名称", "碰撞点名", "名称", "编号", "name", "id", "碰撞点"],
    "status": ["status", "状态", "结果", "处理状态"],
    "distance": ["distance", "距离", "净距", "穿透深度", "最小距离", "间距"],
    "clash_point": ["clash point", "碰撞点坐标", "碰撞位置", "位置", "坐标", "point", "clashpoint"],
    "grid": ["grid location", "grid", "轴网", "轴网位置", "轴线", "网格", "定位"],
    "level": ["level", "楼层", "所在楼层", "标高", "层"],
    "clash_test": [
        "clash test name", "clash test", "test name", "碰撞测试名", "碰撞测试",
        "测试项名称", "测试项", "检测项", "测试名称", "碰撞检测项",
    ],
    "clash_type": ["clash type", "碰撞类型", "检测类型", "检测方式", "clashmethod"],
    "item1": ["item 1", "item1", "selection a", "项目 1", "项目1", "构件 1", "构件1",
              "对象 1", "对象1", "元素 1", "元素1", "模型 a"],
    "item2": ["item 2", "item2", "selection b", "项目 2", "项目2", "构件 2", "构件2",
              "对象 2", "对象2", "元素 2", "元素2", "模型 b"],
    "assigned_to": ["assigned to", "assigned", "责任人", "负责人", "分配至", "处理人"],
    "comment": ["comments", "comment", "备注", "说明", "注释", "描述"],
    "image": ["image", "image path", "图片", "截图", "图片路径"],
}

# 记录内的 item 子字段
ITEM_SUB_LABELS = {
    "name": {"name", "名称"},
    "path": {"path", "路径", "源文件", "文件路径", "层级", "file"},
    "type": {"type", "类型", "构件类型", "类别", "category", "element type"},
}

TOP_LEVEL_FIELDS = {
    "name", "status", "distance", "clash_point", "grid", "level",
    "clash_test", "clash_type", "item1", "item2", "assigned_to", "comment", "image",
}

# 用于"开始一条新记录"的字段（同一字段第二次出现即视为新记录）
RECORD_BOUNDARY_FIELDS = ("name", "status")

_STATUS_OPEN = re.compile(
    r"new|active|新建|新|活动|激活|待处理|未处理|open|conflict|冲突|已复核|reviewed|审阅", re.I
)
_STATUS_CLOSED = re.compile(
    r"resolved|approved|已解决|已批准|已关闭|已确认|通过|closed|solved|完成|忽略|ignored", re.I
)


# ==========================================================================
# 通用工具
# ==========================================================================
def clean_text(text: str) -> str:
    """保留换行的文本清洗：去 NBSP、去行首尾空白、压掉空行。"""
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def clean_inline(text) -> str:
    """单行字段清洗：换行压成空格。"""
    if text is None:
        return ""
    if isinstance(text, dict):
        return " ".join(str(v) for v in text.values() if v)
    return re.sub(r"\s+", " ", str(text)).strip()


def norm_label(text: str) -> str:
    """标签归一：小写、去空白、去冒号/星号/特殊符。"""
    t = str(text).strip().lower()
    t = t.replace("：", ":").replace("*", "").replace("_", " ")
    t = re.sub(r"[\(\)\[\]【】\.,;；。、]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_ALIAS_LOOKUP: dict[str, str] = {}
for _canon, _aliases in FIELD_ALIASES.items():
    for _a in _aliases:
        _ALIAS_LOOKUP[norm_label(_a)] = _canon
_SORTED_ALIASES = sorted(_ALIAS_LOOKUP.keys(), key=len, reverse=True)


def alias_to_field(label: str) -> str | None:
    """把表头/标签文本映射到规范字段名。"""
    key = norm_label(label)
    if not key:
        return None
    if key in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[key]
    # 容忍 "命名空间:Name" / "Name (Item 1)" 之类的包裹
    for alias in _SORTED_ALIASES:
        if len(alias) >= 3 and alias in key:
            return _ALIAS_LOOKUP[alias]
    return None


def match_label(text: str) -> tuple[str, str | None] | None:
    """判断一个文本单元是否为 '<标签>: <值>' 或纯 '<标签>'。

    返回 (canonical_field, value_or_None)，不是标签则返回 None。
    """
    t = clean_text(text)
    if not t:
        return None
    first = t.split("\n", 1)[0]
    m = re.match(r"^\s*(.{1,60}?)\s*[:：]\s*(.*)$", first, re.S)
    if m:
        field = alias_to_field(m.group(1))
        if field:
            rest = m.group(2).strip()
            if len(t.split("\n", 1)) > 1:
                rest = (rest + "\n" + t.split("\n", 1)[1]).strip()
            return field, (rest or None)
    field = alias_to_field(first)
    if field and len(t.split("\n", 1)) == 1:
        return field, None
    return None


def parse_distance(value) -> float | None:
    """解析距离字符串 -> 米。Navisworks 默认单位为米，负值表示穿透。"""
    if value is None:
        return None
    t = clean_inline(value)
    if not t:
        return None
    low = t.lower()
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", t.replace(",", ""))
    if not m:
        return None
    val = float(m.group(0))
    if "mm" in low or "毫米" in t:
        val /= 1000.0
    elif "cm" in low or "厘米" in t:
        val /= 100.0
    return val


def parse_point(value) -> dict:
    """解析碰撞点坐标 -> {'x':float|None,'y':...,'z':...}，单位米。"""
    out = {"x": None, "y": None, "z": None}
    if value is None:
        return out
    t = clean_inline(value)
    if not t:
        return out
    scale = 1.0
    if "mm" in t.lower() or "毫米" in t:
        scale = 0.001
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", t.replace(",", " "))
    vals = [float(n) * scale for n in nums[:3]]
    for i, key in enumerate(("x", "y", "z")):
        if i < len(vals):
            out[key] = vals[i]
    return out


_ITEM_LINE_RE = re.compile(
    r"^\s*(name|path|type|名称|路径|类型|源文件|文件路径|层级|类别|category|file)\s*[:：]\s*(.*)$",
    re.I,
)

# 兼容 "构件名 [Path: xxx] [Type: yyy]" 这类行内/方括号内联写法：
# 在标签前插入换行，复用下面的逐行解析逻辑
_ITEM_INLINE_LABEL_RE = re.compile(
    r"\s*[\[\(【]?\s*(name|path|type|名称|路径|类型|源文件|文件路径|层级|类别|category|file)\s*[:：]\s*",
    re.I,
)
_BRACKET_TRIM = "[]【】()（） \t\"'"


def parse_item_cell(value) -> dict:
    """解析单个 Item 单元格。

    Navisworks 常见三种渲染：
      A) 多行文本  "Column 400x400\nPath: ...\nType: ..."
      B) 纯名称    "Column 400x400"
      C) 内联写法  "Column 400x400 [Path: ...] [Type: ...]"
    """
    item = {"name": "", "path": "", "type": ""}
    if value is None:
        return item
    if isinstance(value, dict):
        return {**item, **value}
    text = clean_text(str(value))
    if not text:
        return item
    text = _ITEM_INLINE_LABEL_RE.sub(lambda m: "\n" + m.group(1) + ":", text).strip()

    leftover: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _ITEM_LINE_RE.match(line)
        if not m:
            leftover.append(line)
            continue
        label = norm_label(m.group(1))
        val = m.group(2).strip().strip(_BRACKET_TRIM).strip()
        target = None
        for sub, labels in ITEM_SUB_LABELS.items():
            if label in {norm_label(x) for x in labels}:
                target = sub
                break
        if target:
            if item[target] and val:
                item[target] = f"{item[target]}; {val}"
            elif val:
                item[target] = val
        elif val:
            leftover.append(line)

    if not item["name"] and leftover:
        item["name"] = leftover.pop(0).strip(_BRACKET_TRIM).strip()
    if not item["type"] and leftover:
        item["type"] = leftover.pop(0).strip(_BRACKET_TRIM).strip()
    if not item["name"]:
        item["name"] = text.split("\n")[0].strip()
    return item


# ==========================================================================
# HTML DOM
# ==========================================================================
_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "col", "area", "base",
              "source", "track", "wbr", "embed", "param"}
_UNIT_TAGS = {"td", "th", "p", "li", "div", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6"}
_CONTAINER_TAGS = {"td", "th", "p", "li", "div", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
                   "table", "tr", "thead", "tbody", "tfoot", "ul", "ol", "dl",
                   "section", "article", "body", "html", "#root"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "_Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent


class _DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        node = _Node(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag.lower(), dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def _node_text(node) -> str:
    if isinstance(node, str):
        return node
    if node.tag in ("script", "style"):
        return ""
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        else:
            parts.append(_node_text(child))
    return "".join(parts)


def _iter_nodes(node):
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _iter_nodes(child)


def _iter_units(root):
    """按文档顺序产出"叶子文本单元"。"""
    for node in _iter_nodes(root):
        if node.tag not in _UNIT_TAGS:
            continue
        if any(isinstance(c, _Node) and c.tag in _CONTAINER_TAGS for c in node.children):
            continue
        text = clean_text(_node_text(node))
        if text:
            yield node.tag, text


def _nearest_table(node):
    p = node.parent
    while p is not None:
        if p.tag == "table":
            return p
        p = p.parent
    return None


def _iter_tables(root):
    for node in _iter_nodes(root):
        if node.tag == "table":
            yield node


def _table_rows(table) -> list[list[str]]:
    rows = []
    for node in _iter_nodes(table):
        if node.tag != "tr" or _nearest_table(node) is not table:
            continue
        if node.parent is not None and node.parent.tag not in ("table", "thead", "tbody", "tfoot"):
            continue
        cells = []
        for child in node.children:
            if isinstance(child, _Node) and child.tag in ("td", "th"):
                cells.append(clean_text(_node_text(child)))
        if any(c for c in cells):
            rows.append(cells)
    return rows


# ==========================================================================
# 状态机：把叶子文本单元流还原成一条条碰撞记录
# ==========================================================================
_TEST_HEAD_RE = re.compile(
    r"^\s*(?:clash\s*test(?:\s*name)?|test\s*name|碰撞测试(?:名)?|测试项(?:名称)?|检测项)\s*[:：]\s*(.+)$",
    re.I,
)
_TEST_PREFIX_RE = re.compile(r"^\s*(?:clash\s*test|test|碰撞测试|测试项|检测项)\s*[:：]?\s*(.*)$", re.I)

# 明显是汇总表 / 页脚的行，遇到就丢弃
_SUMMARY_NOISE_RE = re.compile(
    r"^(total|subtotal|sum|合计|小计|总计|共)\b|^(page|页码|第\s*\d+\s*页)", re.I
)


class _StateMachine:
    def __init__(self):
        self.records: list[dict] = []
        self.cur: dict = {}
        self.cur_item: str | None = None
        self.pending: str | None = None
        self.cur_test: str = ""
        self.heading_seen = 0
        self.title: str = ""
        self.unknown_labels: dict[str, int] = {}
        self.tests_seen: list[str] = []

    # -- 内部 ------------------------------------------------------------
    def _flush(self):
        if not self.cur:
            return
        rec = dict(self.cur)
        rec["_clash_test"] = self.cur.get("clash_test") or self.cur_test or "未分组"
        if _is_real_record(rec):
            self.records.append(rec)
            if rec["_clash_test"] not in self.tests_seen:
                self.tests_seen.append(rec["_clash_test"])
        self.cur = {}
        self.cur_item = None

    def _assign(self, field: str, value):
        """把值写入 cur（或当前 item 子字典）。"""
        if self.cur_item and field in ("name", "type"):
            sub = self.cur.setdefault(self.cur_item, {"name": "", "path": "", "type": ""})
            if isinstance(sub, dict):
                if not sub.get(field):
                    sub[field] = value
                    return
        if self.cur_item and field == "path":
            sub = self.cur.setdefault(self.cur_item, {"name": "", "path": "", "type": ""})
            if isinstance(sub, dict) and not sub.get("path"):
                sub["path"] = value
                return
        self.cur[field] = value

    def feed(self, unit: str, tag: str = "td"):
        text = clean_text(unit)
        if not text:
            return
        if _SUMMARY_NOISE_RE.match(text):
            self.pending = None
            return

        # 1) 标题 -- 报告标题 / 碰撞测试分组名
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.heading_seen += 1
            if self.heading_seen == 1 and not self.title:
                self.title = re.sub(r"\s+", " ", text)
            else:
                name = _TEST_PREFIX_RE.sub(r"\1", re.sub(r"\s+", " ", text)).strip()
                if name:
                    self._flush()
                    self.cur_test = name
            return

        # 2) 显式 "Clash Test: xxx"
        m = _TEST_HEAD_RE.match(text)
        if m:
            self._flush()
            self.cur_test = m.group(1).strip()
            self.pending = None
            return

        # 3) 多行单元 -> 拆行处理（如 Item 单元格）
        lines = text.split("\n")
        if len(lines) > 1:
            head = match_label(lines[0])
            if head and head[1] is None:
                self._consume(head[0], "\n".join(lines[1:]))
                return

        # 4) 普通标签 / 标签+值
        hit = match_label(text)
        if hit:
            self._consume(hit[0], hit[1])
            return

        # 5) 前一个单元是"纯标签"，本单元是它的值
        if self.pending:
            field, self.pending = self.pending, None
            if field in ("item1", "item2"):
                self.cur_item = field
                self.cur[field] = parse_item_cell(text)
                return
            if self.cur_item and field in ("name", "path", "type"):
                sub = self.cur.setdefault(self.cur_item, {"name": "", "path": "", "type": ""})
                if isinstance(sub, dict) and not sub.get(field):
                    sub[field] = clean_inline(text)
                    return
            self.cur[field] = text if "\n" in text else clean_inline(text)
            if field == "clash_test":
                self.cur_test = clean_inline(text)
            return

        # 6) 无法识别的自由文本，只统计，便于诊断
        key = re.sub(r"\s+", " ", text)[:40]
        if len(key) > 2:
            self.unknown_labels[key] = self.unknown_labels.get(key, 0) + 1

    def _consume(self, field: str, value):
        # clash_test 仅用于分组
        if field == "clash_test":
            if value:
                self.cur_test = clean_inline(value)
                if self.cur.get("name"):
                    self.cur["clash_test"] = self.cur_test
            self.pending = None
            return

        # 新记录边界
        if field in RECORD_BOUNDARY_FIELDS and field in self.cur and len(self.cur) >= 2:
            self._flush()

        if field in ("item1", "item2"):
            self.cur_item = field
            item = parse_item_cell(value) if value else {"name": "", "path": "", "type": ""}
            self.cur[field] = item
            # 标签与值分处两个单元格时，等待下一个单元作为值
            self.pending = None if value else field
            return

        if field in ("status", "distance", "clash_point", "grid", "level",
                     "clash_type", "assigned_to", "comment", "image"):
            self.cur_item = None

        if field == "name" and self.cur_item:
            sub = self.cur.setdefault(self.cur_item, {"name": "", "path": "", "type": ""})
            if isinstance(sub, dict) and not sub.get("name") and value:
                sub["name"] = clean_inline(value)
                self.pending = None
                return

        self._assign(field, value if value else "")
        self.pending = None if value else field

    def finish(self) -> dict:
        self._flush()
        return self.records


def _is_real_record(rec: dict) -> bool:
    """过滤掉汇总表 / 表头产生的伪记录。"""
    has_item = bool((rec.get("item1") or {}).get("name")) or bool((rec.get("item2") or {}).get("name"))
    if has_item:
        return True
    if rec.get("clash_point") and any(v is not None for v in parse_point(rec["clash_point"]).values()):
        return True
    if rec.get("distance") or rec.get("grid"):
        return True
    name = clean_inline(rec.get("name", ""))
    if name and re.search(r"clash|碰撞|冲突", name, re.I) and rec.get("status"):
        return True
    return False


# ==========================================================================
# 平整表格（CSV / XLSX）解析
# ==========================================================================
def records_from_rows(rows: list[list[str]]) -> tuple[list[dict], dict]:
    if not rows:
        return [], {"strategy": "empty"}
    header = [clean_inline(c) for c in rows[0]]
    keys = [alias_to_field(c) for c in header]
    hits = sum(1 for k in keys if k)
    diag = {"strategy": "flat-table", "header_hits": hits, "header": header}
    if hits < 2:
        return [], diag

    records = []
    for row in rows[1:]:
        if not any(clean_inline(c) for c in row):
            continue
        rec: dict = {}
        for i, cell in enumerate(row):
            if i >= len(keys) or not keys[i]:
                continue
            field = keys[i]
            if field in ("item1", "item2"):
                rec[field] = parse_item_cell(cell)
            else:
                rec[field] = clean_text(cell)
        if rec:
            records.append(rec)
    return records, diag


# ==========================================================================
# XML 解析（Navisworks batchtest / clashtest / clashresult / clashobject）
# ==========================================================================
_CLASH_METHOD = {"0": "硬碰撞", "1": "间隙碰撞", "2": "重复项",
                 "hard": "硬碰撞", "clearance": "间隙碰撞", "duplicate": "重复项"}


def _local(tag: str) -> str:
    return tag.split("}")[-1].lower()


def parse_xml(path: str) -> tuple[list[dict], dict, dict]:
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    records: list[dict] = []
    project: dict = {}
    diag: dict = {"strategy": "navisworks-xml"}

    for node in root.iter():
        lt = _local(node.tag)
        if lt == "batchtest":
            project.setdefault("project", node.get("name") or node.get("filename") or "")
            project.setdefault("units", node.get("units") or "")
        if lt != "clashtest":
            continue
        test_name = node.get("name") or "未分组"
        method = _CLASH_METHOD.get(str(node.get("clashmethod", "")).lower(), "")
        tolerance = node.get("tolerance") or ""
        if tolerance:
            project.setdefault("tolerance", tolerance)
        for res in node.iter():
            if _local(res.tag) != "clashresult":
                continue
            rec: dict = {
                "name": res.get("name") or res.get("id") or "",
                "status": res.get("status") or "",
                "distance": res.get("distance") or "",
                "clash_test": test_name,
                "clash_type": method,
                "_clash_test": test_name,
            }
            objects = []
            for child in res.iter():
                lc = _local(child.tag)
                if lc == "clashpoint":
                    pos = child.get("pos3f") or child.get("pos") or ""
                    if pos:
                        rec["clash_point"] = pos
                elif lc == "clashobject":
                    objects.append({
                        "name": child.get("name") or "",
                        "path": child.get("path") or child.get("source") or "",
                        "type": child.get("type") or child.get("category") or "",
                    })
            if objects:
                rec["item1"] = objects[0]
            if len(objects) > 1:
                rec["item2"] = objects[1]
            grid = res.get("grid") or res.get("location")
            if grid:
                rec["grid"] = grid
                lv = re.search(r"\b(B?\d+F?\d*)\b", grid)
                if lv:
                    rec["level"] = lv.group(1)
            records.append(rec)
    return records, project, diag


# ==========================================================================
# 总入口
# ==========================================================================
def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    head = raw[:4000].decode("ascii", "ignore").lower()
    m = re.search(r'charset\s*=\s*["\']?([\w-]+)', head)
    encodings = []
    if m:
        encodings.append(m.group(1))
    encodings += ["utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def parse_report(path: str) -> dict:
    """解析报告文件，返回统一结构。"""
    ext = os.path.splitext(path)[1].lower()
    result: dict = {
        "source": os.path.abspath(path),
        "format": "",
        "project": {},
        "title": "",
        "tests": [],
        "records": [],
        "diagnostics": {},
    }

    if ext in (".xml",):
        records, project, diag = parse_xml(path)
        result.update(format="xml", project=project, diagnostics=diag)

    elif ext in (".csv", ".tsv", ".txt"):
        text = _read_text(path)
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [row for row in csv.reader(io.StringIO(text), dialect)]
        records, diag = records_from_rows(rows)
        result.update(format="csv", diagnostics=diag)

    elif ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        records, diag = [], {"strategy": "xlsx", "sheets": []}
        for ws in wb.worksheets:
            rows = [[("" if c is None else str(c).strip()) for c in row]
                    for row in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(r)]
            if not rows:
                continue
            sheet_records, sheet_diag = records_from_rows(rows)
            if not sheet_records:
                continue
            diag["sheets"].append({"name": ws.title, **sheet_diag})
            for r in sheet_records:
                r.setdefault("_clash_test", ws.title)
                r.setdefault("clash_test", ws.title)
            records.extend(sheet_records)
        result.update(format="xlsx", diagnostics=diag)

    else:  # html 兜底
        text = _read_text(path)
        builder = _DomBuilder()
        builder.feed(text)
        builder.close()
        root = builder.root

        # 策略 A：标准列头表格
        records = []
        used_tables = 0
        for table in _iter_tables(root):
            rows = _table_rows(table)
            if not rows:
                continue
            recs, diag = records_from_rows(rows)
            if recs:
                used_tables += 1
                records.extend(recs)
        if records:
            diag = {"strategy": "flat-table-in-html", "tables": used_tables}
        else:
            # 策略 B：标签/值状态机（Navisworks 默认 HTML 模板）
            sm = _StateMachine()
            for tag, unit in _iter_units(root):
                sm.feed(unit, tag)
            records = sm.finish()
            result["title"] = sm.title
            result["tests"] = sm.tests_seen
            diag = {"strategy": "label-value-state-machine",
                    "unknown_label_samples": sorted(
                        sm.unknown_labels.items(), key=lambda kv: -kv[1])[:15]}
        result.update(format="html", diagnostics=diag)

    # ---- 统一收尾：补 clash_test、补 name、归一化距离与坐标 -------------
    for i, rec in enumerate(records, 1):
        if not clean_inline(rec.get("name", "")):
            rec["name"] = f"Clash {i}"
        rec.setdefault("_clash_test", clean_inline(rec.get("clash_test", "")) or "未分组")
        rec.setdefault("item1", {"name": "", "path": "", "type": ""})
        rec.setdefault("item2", {"name": "", "path": "", "type": ""})
        for k in ("item1", "item2"):
            if not isinstance(rec[k], dict):
                rec[k] = parse_item_cell(rec[k])
            rec[k] = {kk: clean_inline(vv) for kk, vv in
                      {"name": "", "path": "", "type": "", **rec[k]}.items()}
        if not isinstance(rec.get("distance_m"), (int, float)):
            rec["distance_m"] = parse_distance(rec.get("distance"))
        if not isinstance(rec.get("clash_point"), dict):
            rec["clash_point"] = parse_point(rec.get("clash_point"))
        for key in ("grid", "level", "status", "comment", "assigned_to"):
            if key in rec and not isinstance(rec[key], str):
                rec[key] = clean_inline(rec[key])

    if not result["tests"]:
        seen: list[str] = []
        for rec in records:
            t = rec["_clash_test"]
            if t not in seen:
                seen.append(t)
        result["tests"] = seen

    result["records"] = records
    return result
