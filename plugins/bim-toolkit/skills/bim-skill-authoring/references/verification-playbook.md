# 验收流程（五步）

每做一个新 Skill，**这五步必须全跑**。跳过任一步都可能带着静默 bug 交付。

```bash
PY="C:/Users/52248/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
SC="D:/Program Files/WorkBuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/skill-creator/scripts"
S="<skill_dir>/scripts/<x>_builder.py"
```

---

## 第 1 步：结构断言

先跑生成，再对 HTML 做结构断言。

```python
import io, re
html = io.open(OUT_HTML, encoding="utf-8").read()

# 1) 章节与卡片数（按设计值改数字）
assert html.count("<h2>") == 6, html.count("<h2>")
assert html.count('class="pagecard"') == 12
assert html.count('class="qa"') == 39
assert html.count('class="err"') == 10

# 2) 表格数：先打印实际值确认设计意图，不要凭感觉写断言
print("表格数:", html.count("<table"))

# 3) 标签开合一致（这类错最难肉眼发现）
for tag in ("div", "table", "ul", "ol", "li", "td", "tr", "span"):
    o = len(re.findall(r"<%s[\s>]" % tag, html))
    c = html.count("</%s>" % tag)
    print(("OK " if o == c else "BAD") + "%s %d/%d" % (tag, o, c))

# 4) 占位符无嵌套 span
nested = len(re.findall(r'<span class="todo">[^<]*<span', html))
assert nested == 0

# 5) 正文无裸露占位符（页脚说明文字除外）
body = html.split("<footer>")[0]
raw = re.findall(r"〔[^〕]*〕", re.sub(r'<span class="todo">[^〕]*</span>', "", body))
assert raw == [], raw
```

**注意**：页脚里可能有意保留一句「标注〔待补充〕的内容必须由你本人填实」——这属正常，所以断言必须排除 `<footer>`。曾因没排除而误判为 bug。

---

## 第 2 步：内容命中抽查

**这一步专治「字段没渲染」这类静默失败**——结构完全正常，但某个字段忘了写进 `build_blocks()`。

```python
keys = [
    ("核心论点句", "<把 meta.core_caveat 里那句原文抄进来>"),
    ("关键提醒1", "..."),
    ("关键提醒2", "..."),
    ("未收录说明", "未收录"),
]
for label, k in keys:
    print(("PASS " if k in html else "FAIL ") + label)
```

关键点：

- **必须抄原文**，不要抄关键词。字段没渲染时关键词也可能偶然命中
- 每个自定义**展示型区块至少断言一条**（`pagecard` 的演讲备注、`qa` 的回答框架、`specpage` 的专属页标题…）
- 三种输出（HTML / 主 MD / 附加 MD）都要抽查

---

## 第 3 步：别名回归

准备 **40+ 用例**，覆盖六种情况：

| 情况 | 例 |
| --- | --- |
| 标准名 | `铀矿巷道` → `uranium_mine` |
| 短别名 | `管廊` → `utility_tunnel` |
| 口语别名 | `地连墙` → `foundation_pit`、`叠拼` → `villa` |
| 长句包含 | `XX铀矿巷道工程的BIM答辩` → `uranium_mine` |
| 未收录 | `桥梁工程` → `None`（应回退） |
| 模式串不误伤 | `盾构隧道管片拼装` → `shield_tunnel`（不是别的） |

```python
import subprocess, json
for q, exp in CASES:
    r = subprocess.run([PY, S, "--direction", q, "--json-only", "-o", OUT],
                       capture_output=True, text=True, encoding="utf-8")
    got = json.loads(r.stdout)["direction_key"]
    print(("PASS" if got == exp else "FAIL") + " %-22s -> %s (期望 %s)" % (q, got, exp))
```

**回归的重点是「模式串不误伤」**：用一串包含多个可能别名的长句，确认命中最长的那个。

---

## 第 4 步：模式覆盖

```bash
# 主参数（每个别名分支都要跑一次）
"$PY" "$S" --direction 铀矿巷道 --project "T" -o out
# 未收录回退
"$PY" "$S" --direction 桥梁工程 --project "T" --json-only -o out
# 时长档位（如适用）
for m in 10 15 20; do "$PY" "$S" --direction 教学楼 --minutes $m --json-only -o out; done
# --input
"$PY" "$S" --input in.json -o out
# 全部 --template
for w in all outline qa prep; do "$PY" "$S" --template $w --name "模板_$w" -o out; done
# --list
"$PY" "$S" --list
```

**`--template all` 必须单独跑**：它会把所有子模板串起来，子模板里的键路径错误会在这里连带暴露。（`defense-ppt` 的 `qb["prep"]["answer_rules"]` 就是这么连着挂了两处。）

### 时间 / 分配类校验（若 Skill 含自动折算）

```python
# 折算合计必须等于目标，且满足硬约束
assert abs(total - goal) < 0.6
assert background_share <= 0.10
assert core_share >= 0.50
```

---

## 第 5 步：官方校验 + 安全审计

```bash
cd "<skill_dir>"
rm -rf scripts/__pycache__          # 必须先删，否则打进 zip

# 结构校验
"$PY" "$SC/quick_validate.py" .

# 打包（会再校验一次）
cd "C:/Users/52248/.workbuddy/skills" && "$PY" "$SC/package_skill.py" <name>

# 安全审计：以下应全部为空
grep -rnE "import (socket|urllib|requests|http|subprocess|shutil)|__import__|eval\(|exec\(|os\.system|os\.remove|os\.unlink|rmtree|os\.popen|pickle\.loads" --include="*.py" .

# 写文件只允许落在 -o 输出目录
grep -n "open(" scripts/*.py
```

### 安全审计通过标准

| 检查项 | 要求 |
| --- | --- |
| 网络 | 无 socket / urllib / requests / http 导入 |
| 执行 | 无 subprocess / os.system / os.popen / eval / exec |
| 删除 | 无 os.remove / os.unlink / shutil.rmtree |
| 写入 | `open(..., "w")` 的路径全部由 `args.outdir` 派生 |
| 读取 | 只读 `assets/` 与 `--input` 指定文件 |

---

## 一次性全跑（推荐）

把五步写进一个 `verify.py`，用 `fails` 计数，最后 `sys.exit(1 if fails else 0)`。这样每次改动后一条命令即可回归：

```bash
"$PY" verify.py && echo "验收通过"
```

`defense-ppt` 的实测基线（可作为新 Skill 的量级参考）：

```
h2 6 | pagecard 12 | qa 39 | spec 2 | err 10 | chips 10
标签开合：div 452/452, table 8/8, ul 45/45, li 158/158, span 406/406
时间折算：10 分钟 → 9.9；15 分钟 → 15.1
别名回归：41/41 通过
```
