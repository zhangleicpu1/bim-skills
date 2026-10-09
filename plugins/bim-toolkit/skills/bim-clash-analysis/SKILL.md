---
name: bim-clash-analysis
description: 整理并分析 BIM 碰撞检测报告，把 Navisworks Clash Detective 导出的原始碰撞报告变成可用于整改闭环的分析文档。当用户上传或提到碰撞报告文件（.html/.htm/.xml/.csv/.tsv/.xlsx）、提到「碰撞检测报告」「碰撞点汇总」「碰撞分类」「严重程度分级」「碰撞整改清单」「Clash Detective 报告」「Navisworks 导出」「BIM 碰撞分析」「净高/管线综合碰撞」等，需要按碰撞类型与严重程度分类汇总、生成可交付的分析报告时使用。自动解析报告 → 判定碰撞类型与严重等级 → 输出 Word 分析报告 + Excel 明细表 + Markdown 摘要。
agent_created: true
---

# BIM 碰撞检测报告整理分析

## 用途

把 Navisworks Clash Detective 导出的原始碰撞报告（HTML/XML/CSV/XLSX）自动转成三类成果物：

1. **Word 分析报告** —— 图文并茂，含检测概况、碰撞类型分类汇总、严重程度分级、专业/楼层分布、重点碰撞清单、整改建议、判级规则附录。
2. **Excel 明细表** —— 5 个 Sheet：分析概览、碰撞明细（可筛选/条件着色/带责任人与备注空列）、重点整改清单（可分派）、统计汇总、判级规则说明。
3. **Markdown 摘要** —— 纯文本版结论，便于直接贴进会议纪要或消息。

核心价值在于两件事：**把没有等级字段的原始报告判出 P0/P1/P2/P3**，以及**把散点式的碰撞点聚合成可决策的分布结论**。

## 输入要求

- Navisworks 导出的碰撞报告文件。主路径为 `Clash Detective → Report → HTML`。
- XML（`batchtest/clashtest/clashresult` 结构）、CSV/TSV、XLSX 亦可直接解析。
- 若报告模板特殊导致解析不到记录，脚本会输出 `diagnostics`，依此扩展别名表（见「常见调整」）。

## 执行流程

### 第 1 步：确认 Python 环境

脚本依赖 `openpyxl`（Excel）、`python-docx`（Word）、`matplotlib`（图表，缺失时自动跳过图表）。

优先复用托管环境：

```bash
PY="C:/Users/52248/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
"$PY" -c "import openpyxl, docx; print('ok')"
```

若报 `ModuleNotFoundError`，先创建虚拟环境再安装：

```bash
"C:/Users/52248/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv "C:/Users/52248/.workbuddy/binaries/python/envs/default"
"C:/Users/52248/.workbuddy/binaries/python/envs/default/Scripts/pip.exe" install openpyxl python-docx matplotlib
```

`pip install matplotlib` 耗时较长，用后台方式执行，不要阻塞等待。

### 第 2 步：定位报告文件

确认用户提供的报告路径与格式。若用户只给了目录，先列出候选文件让用户确认。不要猜测文件位置。

### 第 3 步：运行分析

```bash
"C:/Users/52248/.workbuddy/binaries/python/envs/default/Scripts/python.exe" \
  "<skill_dir>/scripts/clash_analyzer.py" "<报告文件路径>" -o "<输出目录>"
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `-o/--outdir` | 输出目录，默认与源文件同目录 |
| `--rules` | 指定自定义规则 JSON，默认用 `assets/severity_rules.json` |
| `--formats` | 输出格式，逗号分隔，可选 `docx,xlsx,md`（默认三者全出） |
| `--project` | 覆盖项目名称（源报告里没有项目名时使用） |
| `--min-severity` | 只保留不低于该等级的碰撞（`严重`/`高`/`中`/`低`） |
| `--top` | 重点清单条数，默认 30 |
| `--no-charts` | 不生成图表 |
| `--json-only` | 只输出 JSON 不生成文档，用于快速查看统计口径 |

脚本把结构化结论以 JSON 打印到 stdout（`stats` / `top_issues` / `diagnostics`），先读它确认解析正确再交付文档。

### 第 4 步：核对解析质量（关键步骤，不可跳过）

读 stdout JSON 中的这几项，异常就修：

- `stats.total` —— 是否与源报告标注的总数一致？差距大说明解析漏行。
- `stats.top_discipline_pairs` —— 若出现大量 `未知`，说明专业关键词库没覆盖该项目的构件命名，需扩充 `discipline_keywords`。
- `diagnostics.strategy` —— `flat-table` 命中表头；`label-value-state-machine` 为标签值模板；两种都不对时要看 `unknown_label_samples`。
- `diagnostics.unknown_label_samples` —— 列出了反复出现的未识别文本，通常就是漏掉的字段标签，把它们的写法补进 `parsers.py` 的 `FIELD_ALIASES`。

### 第 5 步：按用户诉求微调

- 用户有企业分级标准 → 改 `assets/severity_rules.json` 的 `severity_thresholds` 与 `discipline_priority`，重跑。
- 用户关注某个专业或某个楼层 → 用 `--min-severity` 收窄，或用 `--top` 放大重点清单。
- 用户只要结论 → `--formats md`。
- 用户要能直接发出去分派整改 → 重点交付 Excel 的「重点整改清单」Sheet。

### 第 6 步：交付

用 `present_files` 把生成的 `.docx` / `.xlsx` / `.md` 一并呈现（Word 放最前）。在回复里直说关键数字：总数、严重+高等级数量、最集中的专业组合、最该先处理的三类问题。不要复述文档目录结构。

## 判级口径（需要向用户解释时引用）

严重度分值 = 碰撞类型基础分 + 构件专业优先级分(0~4) + 跨专业加分 + 距离影响分(0~3) + 关键区域加分。

- 碰撞类型基础分：硬碰撞 5、间隙碰撞 3、重复项 1。
- 专业优先级：结构/给排水消防 10，暖通 9，设备 8.5，电气 8，幕墙 7，建筑 6，智能化 5.5，未知 5，景观 3。
- 距离影响分：硬碰撞按穿透深度线性计分（参考 30mm 满分）；间隙碰撞按净距**反向**计分（净距越小越严重，参考 50mm）；重复项不计。
- 等级阈值：严重 P0 ≥ 13.0，高 P1 ≥ 10.5，中 P2 ≥ 7.5，其余为低 P3。

碰撞类型的自动推断顺序：源报告显式字段 → 碰撞测试名关键词 → 距离符号（负值=硬碰撞，正值=间隙碰撞）。

完整模型说明见 `references/severity-model.md`。

## 常见调整

| 场景 | 改哪里 |
| --- | --- |
| 报告里出现新的字段标签（如「碰撞体」「检测点位置」） | `scripts/parsers.py` → `FIELD_ALIASES` |
| 项目构件命名特殊，专业识别成「未知」 | `assets/severity_rules.json` → `discipline_keywords` |
| 企业有自己的严重度分级 | `assets/severity_rules.json` → `severity_thresholds` / `discipline_priority` |
| 想改整改建议话术 | `assets/severity_rules.json` → `remediation_rules`（`mode: exact` 需两个专业都命中，`any` 命中其一即可） |
| 报告格式完全解析不出来 | 用 `--json-only` 看 `diagnostics`，必要时让用户提供报告片段 |

## 故障排查

| 现象 | 原因与处理 |
| --- | --- |
| 退出码 2 | 输入文件不存在，检查路径与引号转义 |
| 退出码 3 | 未解析到记录。看 `diagnostics`：若 `unknown_label_samples` 有内容，说明是标签别名缺失；若为空，可能是报告为纯图片/扫描件或加密 HTML |
| 专业大量判为「未知」 | 扩充 `discipline_keywords`，把项目里出现的构件命名习惯加进去 |
| 楼层全为「未标注」 | 报告无楼层字段，且构件路径中不含楼层关键词，可在 `rules.py` 的 `_LEVEL_RE` 里补充项目命名规则 |
| 图表未生成 | `matplotlib` 未安装或系统缺中文字体。报告正文仍完整，只是少两张图 |
| Word 中文字体异常 | 脚本已显式写入 `w:eastAsia=微软雅黑`；若目标机器无该字体，可改 `report_builder.py` 的 `CN_FONT` |

## 配套文件

- `scripts/clash_analyzer.py` —— 命令行入口，编排解析→判级→汇总→出文档。
- `scripts/parsers.py` —— HTML/XML/CSV/XLSX 解析器与字段别名表。
- `scripts/rules.py` —— 专业/类别分类、碰撞类型推断、严重度评分、汇总统计。
- `scripts/report_builder.py` —— 图表、Excel、Word、Markdown 生成。
- `assets/severity_rules.json` —— 可编辑的判级规则与整改话术库。
- `references/navisworks-formats.md` —— Navisworks 各导出格式的结构与解析要点。
- `references/severity-model.md` —— 判级模型的完整推导与调参指南。
