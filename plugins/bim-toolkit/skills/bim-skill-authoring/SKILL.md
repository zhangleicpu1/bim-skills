---
name: bim-skill-authoring
description: 制作「BIM 系列 Skill」的元规范与模板。当用户要求新增一个 BIM 系列 Skill（如「再做一个 BIM XXX 助手」「按之前 BIM 系列的规范做一个新 skill」「把 XX 封装成 BIM 助手」），或要求改造/校验已有 bim-* Skill 时使用。提供固定目录结构（scripts/ + assets/JSON 知识库 + references/ + SKILL.md）、纯标准库零依赖的生成脚本骨架（别名归一三级匹配 / 区块式渲染 / 统一 CLI）、知识库设计约定（唯一数据源、未收录回退、量化指标不写成可念答案）、诚实性卡口（红色〔待补充〕、标准与行业惯例区分、能力边界）、五步验收流程（结构断言 / 别名回归 / 模式覆盖 / 官方打包校验 / 安全审计）。已支撑 8 个 bim-* Skill：碰撞分析、专项可视化、选题调研、参数化族、建模框架、4D 模拟、工程量统计、答辩 PPT。
agent_created: true
---

# BIM 系列 Skill 制作规范

## 这个 Skill 解决什么问题

BIM 系列下已有 8 个 Skill，全部遵循同一套约定。**新做一个时必须沿用，否则用户在多个 Skill 之间会感到风格割裂、结果不可预期。**

本 Skill 把「怎么做一个 BIM 系列 Skill」这套流程固化下来：目录结构、脚本骨架、知识库设计约定、诚实性卡口、验收流程、已知踩坑。

## 已有成员（新增时先看一眼现成的）

| Skill | 输入 | 输出侧重 |
| --- | --- | --- |
| `bim-clash-analysis` | Navisworks 碰撞报告 | 分类判级 → 报告（h2 判级模型：类型基础分 + 专业优先级 + 跨专业加分 + 距离分 + 关键区域） |
| `bim-topic-visualization` | 项目类型 × 专项 | 配色 / 图例 / 视图 / 出图规范 |
| `bim-topic-research` | 调研方向 | 案例库（必带来源 URL）→ 选题报告 |
| `bim-family-creation` | 构件类型 | 参数清单 → 建族步骤 → 检查清单 |
| `bim-framework-setup` | 项目类型 | 标高轴网 / 专业拆分 / LOD / 协同（检测 Revit MCP 走双分支） |
| `bim-4d-simulation` | 项目类型 | WBS / 进度关联 / TimeLiner 步骤 / 风险 |
| `bim-quantity-takeoff` | 构件类型 | 明细表 / 提取路径 / 成本关联 / **模型量 ≠ 清单量** |
| `bim-defense-ppt` | 项目 + 方向 + 成果 + 创新点 | 答辩大纲 / 逐页要点与备注 / 提问预案 / 准备建议 |

系列共同使用的 7 类项目 / 构件分类（跨 Skill 保持一致，便于串联）：铀矿巷道、地下综合管廊、教学楼、盾构隧道、基坑支护、双拼别墅、英雄纪念碑。

## 一、固定目录结构

```
~/.workbuddy/skills/<name>/
├── SKILL.md                 # frontmatter: name + description + agent_created: true
├── scripts/
│   └── <x>_builder.py       # 纯标准库，零依赖，单文件
├── assets/
│   ├── <x>_kb.json          # 领域知识库（唯一数据源）
│   └── standards.json       # 通用流程 / 规范 / 检查清单
└── references/
    └── *.md                 # 2-3 份专题文档（供模型按需读取）
```

用 `init_skill.py` 初始化后，**删掉 example.py / example_asset.txt / api_reference.md**。

## 二、脚本骨架（必备六件套）

完整可复制骨架见 `references/script-skeleton.md`。核心是这六块，顺序固定：

### 1. 载入与别名索引

```python
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
TODO = "〔待补充〕"
PLACEHOLDER_RE = re.compile(r"〔[^〕]*〕")
```

### 2. 别名归一：三级匹配 + 单字不参与子串

这是全系列最容易出错的地方。规则：

1. **精确匹配** key 或别名 → 命中即返回
2. **子串匹配**：只使用**长度 ≥ 2** 的别名，取最长者（`if a in q and len(a) > best_len`）
3. **歧义处理**：同一别名挂在多个条目上时，用 tiebreak 表选默认项，并把备选项一起返回供输出提示

**单字别名绝不能参与子串匹配**——否则「梁」会命中「桥梁支座」、「板」会命中「板房」。这是踩过的真实坑。

### 3. 三种文本工具

```python
def esc(s):        # HTML 转义
def highlight(s):  # 占位符标红，且不重复包裹（stash 机制）
def inline(s):     # 转义 + 标红 + **粗体** + 换行，HTML 用
def md_inline(s):  # Markdown 版：占位符加粗，保留粗体
```

`highlight` 必须用 stash 机制：先把已有的 `<span class="todo">…</span>` 抠出来存占位，做完替换再放回。否则嵌套 span 会导致 HTML 结构错乱（踩过）。

### 4. 区块式渲染

统一用「区块列表」驱动渲染，同一个 `blocks` 同时喂给 `render_html()` 与 `render_md()`，保证两种输出内容一致。

通用区块类型：`h2 / h3 / p / ul / ol / note(kind: info|warn|danger) / tip / kv / table / chips / steps / err`

各 Skill 自有的展示型区块（按需加）：

| Skill | 自有区块 |
| --- | --- |
| clash-analysis | `clash_item`（含判级分项） |
| quantity-takeoff | `pitfalls`（陷阱卡）、`bar`（偏差条） |
| defense-ppt | `pagecard`（页面卡片：内容要点 / 演讲备注 双栏）、`qa`（问答卡）、`specpage`（专属页） |

### 5. CSS 与 page()

**统一 light 主题 + 可打印**。核心要求：

- `:root` 定义 `--fg/--muted/--line/--bg/--soft/--accent/--warn/--danger/--ok/--chip`
- `.wrap{max-width:1000~1040px}`，正文 `15px/1.75`，中文字体栈
- `h2` 带左侧 4px 主色竖条 + 浅底
- `.todo{color:var(--danger);background:#fdeceb}` —— 占位符红色标记
- **必须含 `@media print`**：`h2{page-break-after:avoid}`、卡片类 `page-break-inside:avoid`

### 6. 统一 CLI

```
--list                      列出知识库条目与统计
<主参数>（如 --component / --direction / --project-type）
--input data.json           自定义输入（字段名与 KB 结构一致）
--template {all|各子模板}   输出空白模板
--json-only                 输出机器可读 JSON（含 files 列表）
-o / --outdir               输出目录
--name                      文件名前缀
```

输出固定三件套：`<name>_<主题>.html` + `.md` + 一份附加 MD（检查清单 / 偏差模板 / 讲稿卡 / 提问预案）。

## 三、知识库设计约定

### 唯一数据源

**加内容只改 JSON，不动代码。** 需要新构件 / 新方向 / 新页面时，在 KB 对应字典里加一个键即可，渲染与 CLI 自动支持。

### 顶层结构（照此对齐）

```json
{
  "meta":            { "name", "scope", "core_caveat", "authority_legend" 或 "legend", "time_rule" },
  "components"/"directions"/"page_library": { ... },
  "generic_fallback": { ... }     // 未收录内容 → 回退骨架，且标红提示需人工补充
}
```

### 每个条目的字段（以构件类为例）

`name / aliases / discipline / <专属配置字段>… / intro / pitfalls / checkpoints`

### 分块写入，避免截断

KB 超过 ~40 KB 时**不要一次 Write**，会截断（踩过）。做法：拆成 `p1_*.json … p5_*.json` 写到临时目录，再用 `merge.py` 合并 + 校验并打印统计。

**注意**：合并脚本的输出路径要显式指向 `~/.workbuddy/skills/<name>/assets/`，不要用 `dirname(build_dir)`（踩过：资产落到了工作区根目录）。

## 四、诚实性卡口（全系列的灵魂，不可省）

这是 BIM 系列区别于「通用教程」的地方。**三个必须保留的设计**：

1. **红色〔待补充〕**：凡需用户填实的内容（工程规模、量化指标、进度数据）一律用 `〔待补充〕` 并标红。验收时必须检查正文无裸露占位符（页脚说明文字除外）。
2. **量化指标不写成可念的答案**：知识库给的是「应该准备哪一类指标 + 经验量级」，并明确标注**必须换成项目真实数字**、每个数字要能追溯出处。
3. **区分「标准/规范强制」与「行业惯例」**：不把惯例包装成规范（如 LOD 非国标、给水蓝排水绿是惯例）。规范引用必须核到条款号。
4. **写明能力边界**：如 Revit 对国内清单定额支持弱、钢筋/模板/装饰面层是算量弱项、支吊架模型中通常不存在（只能标注估算量）、BIM 不替代岩土计算与沉降预测。

### 每个 Skill 要有一个「反常识核心论点」

这是知识库有观点、不像说明书的关键。已有例子：

| Skill | 核心论点 |
| --- | --- |
| clash-analysis | 判级要让「间隙碰撞」不进 P0（否则真问题被淹没） |
| framework-setup | 轴网由功能模数反推，不是从图纸抄 |
| 4d-simulation | 三类任务类型必须齐全，缺一类模拟就不成立 |
| quantity-takeoff | **模型量 ≠ 清单量**，口径差不是算错 |
| defense-ppt | 答辩 PPT 是一条能被反复追问的主线，不是成果堆砌 |

新增 Skill 时，**先想清楚这一句，再写 KB**。

## 五、验收流程（五步，一步都不能省）

详细命令与断言见 `references/verification-playbook.md`。

1. **结构断言**：`h2` 章节数、卡片数、表格数、各类标签开合一致（`div/table/ul/ol/li/td/tr/span`）、占位符无嵌套 span、正文无裸露占位符
2. **内容命中抽查**：逐个断言核心论点句出现在输出里（防止「字段没渲染」这类静默失败）
3. **别名回归**：准备 40+ 用例，覆盖每个条目的标准名 / 短别名 / 长句包含 / 未收录回退 / 模式串不误伤
4. **模式覆盖**：`--list`、每个主参数、`--input`、全部 `--template`、三种时长档（如适用）逐个跑通
5. **官方校验 + 安全审计**：
   - `quick_validate.py` 与 `package_skill.py`（skill-creator 自带）
   - 安全审计：扫描无网络（socket/urllib/requests/http）、无执行（subprocess/eval/exec/os.system）、无删除（remove/unlink/rmtree），写文件仅限 `-o` 输出目录
   - **打包前删掉 `scripts/__pycache__`**

## 六、已知踩坑清单

| 踩坑 | 现象 | 规避 |
| --- | --- | --- |
| 单字别名参与子串匹配 | 「梁」命中「桥梁支座」 | 子串匹配只用 `len(a) >= 2` 的别名 |
| JSON 一次写太长 | 文件被截断，`json.load` 报错 | >40KB 拆块写 + merge.py 合并 |
| heredoc 过长 | shell 解析失败 | 长内容一律用独立脚本文件，不用 heredoc |
| 合并脚本输出路径 | 资产落到工作区而非 skill/assets | 显式写绝对路径到 `skills/<name>/assets/` |
| 字段键路径想当然 | `qb["prep"]["answer_rules"]` 实际在 `qb["answer_rules"]`，一处错会连带模板分支一起挂 | **写代码前先 `--list --json-only` 打印真实键路径** |
| 占位符嵌套 span | HTML 结构错乱 | `highlight()` 用 stash 机制 |
| 占位符高亮正则漏 `〔待确认〕` | 只匹配了 `〔待补充〕` | 用 `〔[^〕]*〕` 通配，非硬编码 |
| 自相矛盾 | generic_fallback 缺了某类必备内容 | 回退骨架也要满足「必备项」约束 |
| 验收断言过严 | 表格数预期与实际不符导致误判失败 | 断言前先打印实际值，确认是设计如此再改断言 |
| 打包残留 `__pycache__` | 打进 zip | 打包前 `rm -rf scripts/__pycache__` |

## 七、交付前自检

- [ ] `SKILL.md` 的 description 含全部触发词与能力清单（用户靠它判断能不能用）
- [ ] 目录无 example 残留、无 `__pycache__`
- [ ] 知识库为唯一数据源，加内容不需要改代码
- [ ] 三段诚实性卡口齐全（标红占位符 / 指标非答案 / 规范核到条款）
- [ ] 有一个明确的反常识核心论点，且写进了 `meta.core_caveat`
- [ ] 核心论点句在生成输出中被断言命中（结构断言 + 内容断言都跑过）
- [ ] 别名回归 40+ 用例通过
- [ ] 五步验收全过，`quick_validate` + `package_skill` 通过
- [ ] 安全审计通过（无网络 / 无执行 / 无删除，仅写 `-o`）
- [ ] 工作日志已追加到 `.workbuddy/memory/YYYY-MM-DD.md`
