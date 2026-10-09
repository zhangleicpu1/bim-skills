# Navisworks 碰撞报告格式与解析要点

本文件说明 Clash Detective 各类导出格式的实际结构，以及解析器为什么这样设计。当解析失败或需要支持新模板时读这里。

## 一、HTML 报告（主路径）

导出方式：`Clash Detective → Report → 选择 HTML 模板 → 导出`。

HTML 报告没有统一 schema —— 模板可自定义，不同版本的 Navisworks、不同企业模板输出的 DOM 结构差别很大。实际会遇到两大流派：

### 流派 A：列头表格（flat table）

表头是一行字段名，每个碰撞点占一行：

```html
<table>
  <tr><th>Name</th><th>Status</th><th>Distance</th><th>Grid Location</th>
      <th>Clash Point</th><th>Item 1</th><th>Item 2</th></tr>
  <tr><td>Clash 1</td><td>New</td><td>-0.0234m</td><td>3F / C-3</td>
      <td>X: ...m Y: ...m Z: ...m</td><td>...</td><td>...</td></tr>
</table>
```

解析：`records_from_rows()` 用表头别名命中 ≥ 2 个字段即认定成功，之后按列取值。

### 流派 B：标签 / 值块（默认模板最常见）

每个碰撞点是一小块「标签单元格 + 值单元格」的表格：

```html
<table class="clash">
  <tr><td>Name</td>          <td>Clash 1</td></tr>
  <tr><td>Status</td>        <td>New</td></tr>
  <tr><td>Distance</td>      <td>-0.0234m</td></tr>
  <tr><td>Grid Location</td> <td>3F / C-3</td></tr>
  <tr><td>Clash Point</td>   <td>X: 100.5m, Y: 200.3m, Z: 12.0m</td></tr>
  <tr><td>Item 1</td>        <td>结构柱 KZ1<br>Path: ...<br>Type: Structural Columns</td></tr>
  <tr><td>Item 2</td>        <td>喷淋主管 DN150<br>Path: ...<br>Type: Pipes</td></tr>
</table>
```

解析：`_StateMachine` 把文档按顺序拆成「叶子文本单元」，再跑状态机还原记录。

**状态机的核心规则**（改解析器前先理解这几条）：

1. **记录边界**：`Name` 或 `Status` 字段第二次出现即认为上一条记录结束、新记录开始。Navisworks 每个碰撞点都以 Name 开头，这条规则最可靠。
2. **标签与值可同格也可分格**：`<td>Name: Clash 1</td>` 走「标签+值」一次解析；`<td>Name</td><td>Clash 1</td>` 则先记 `pending=name`，下一个单元作为值。
3. **Item 子块归属**：出现 `Item 1` / `Item 2` 后进入子块状态，随后的 `Name` / `Path` / `Type` 三个标签归属到该 Item；一旦遇到 `Status` / `Distance` / `Clash Point` 等记录级字段就退出子块。
4. **Item 单元格多行解析**：`parse_item_cell()` 先按 `Name:` / `Path:` / `Type:` 前缀切分；没有前缀时，第一行当名称、第二行当类型。
5. **碰撞测试分组**：`<h1>~<h6>` 标题中第一个视为报告标题，其余视为碰撞测试分组名；显式 `Clash Test Name: xxx` 优先。
6. **伪记录过滤**：`_is_real_record()` 要求记录至少含 Item 名称、或碰撞点坐标、或距离/轴网，避免把顶部汇总表和页脚统计当成碰撞点。

### 叶子文本单元的定义

`<td> <th> <p> <li> <div> <dt> <dd> <h1>~<h6>` 中，**内部不含任何块级子元素**的节点才算一个单元。这样 `td` 里套 `table` 时会自动下沉到内层，不会重复计数；`<br>` 转成换行保留多行结构；`<b>/<font>/<a>/<span>` 等行内标签会被吸收进父单元文本。

## 二、XML 报告

导出方式：`Clash Detective → 导出 → XML`。结构稳定，是解析质量最高的格式：

```xml
<exchange xmlns="http://www.navisworks.com/...">
  <batchtest name="项目名">
    <clashtests>
      <clashtest name="结构-vs-机电" clashmethod="0" tolerance="0.01">
        <clashresults>
          <clashresult name="Clash 1" status="New" distance="-0.0234">
            <clashpoint pos3f="1234.5 200.3 12.0"/>
            <clashobjects>
              <clashobject name="柱 KZ1" path="..." type="Structural Columns"/>
              <clashobject name="喷淋管 DN150" path="..." type="Pipes"/>
            </clashobjects>
          </clashresult>
        </clashresults>
      </clashtest>
    </clashtests>
  </batchtest>
</exchange>
```

要点：

- 命名空间随版本变化，解析时用 `_local()` 取本地标签名，不做命名空间硬匹配。
- `clashmethod`：`0`=硬碰撞，`1`=间隙碰撞，`2`=重复项。这是唯一能直接拿到碰撞类型的地方，比 HTML 的距离符号推断可靠。
- `clashpoint@pos3f` 是空格分隔的 "x y z"，单位与 `batchtest` 的 units 一致。
- `clashobject` 只出现 1 个时说明是自碰撞或报告不完整，此时 `item2` 为空。

## 三、CSV / TSV

各列即字段，`records_from_rows()` 按表头别名映射。表头需至少命中 2 个已知字段，否则判定失败（避免把无关 CSV 误当碰撞报告）。

编码按 `utf-8-sig → utf-8 → gb18030 → gbk → latin-1` 顺序尝试，兼容国内常见 GBK 导出。

## 四、XLSX

逐 Sheet 读取，每个 Sheet 当作一张平表独立解析，Sheet 名默认作为碰撞测试分组名。适合企业二次整理的汇总表。

## 五、字段别名表

`parsers.py` 顶部的 `FIELD_ALIASES` 定义了每个规范字段可能出现的写法（中英文）。匹配顺序：

1. 归一化标签（小写、去空白、去冒号括号星号）
2. 先查全等，再按标签长度倒序做子串匹配（避免 `Name` 抢走 `Clash Test Name`）
3. 子串匹配只对长度 ≥ 3 的别名生效，防止单字别名误伤

**新增字段写法时**，直接往对应字段的数组里加字符串即可，不需要改状态机。

## 六、解析诊断

脚本在 JSON 输出的 `diagnostics` 里给出：

| 键 | 含义 |
| --- | --- |
| `strategy` | 实际生效的解析策略 |
| `unknown_label_samples` | 反复出现但未被识别的文本及其出现次数 —— 通常就是漏掉的标签写法 |
| `header_hits` | 平表策略命中的表头字段数 |
| `tables` | HTML 中成功解析的表格数量 |

判定解析是否健康的最低标准：`stats.total` 与源报告自身标注的总数一致，且 `unknown_label_samples` 中不出现明显的字段名。
