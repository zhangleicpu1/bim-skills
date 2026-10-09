# BIM 系列 Skill 合集

一套面向 **BIM 课程设计 / 毕业设计** 的 AI 助手插件。安装一次，9 个助手全部可用，覆盖从建模到答辩的完整链路。

> 适用客户端：**WorkBuddy** / **CodeBuddy**  
> 安装方式：插件市场（无需下载文件、无需配置环境）

---

## 一、安装（三步，复制粘贴即可）

在 WorkBuddy 对话框里**逐条发送**下面三条命令：

```
/plugin marketplace add <你的老师给你的仓库地址>
```



```
/plugin install bim-toolkit@bim-skills
```

```
/reload-plugins
```

> **第 1 条**里的 `<你的老师给你的仓库地址>` 形如 `zhangsan/bim-skills`（`用户名/仓库名`）。  
> ⚠️ 不要填 `https://github.com/...` 这种完整网址，GitHub 源的写法就是 `用户名/仓库名` 两段式。
>
> **第 3 条** `reload-plugins` 不能省，否则插件不会生效。执行后建议**新开一个对话**。

### 更稳的图形界面方式

如果命令行报错，用界面装：

1. 打开 WorkBuddy 的 **插件页** → 点 **「+ 添加市场」**
2. 填入 `用户名/仓库名`，确认
3. 在市场里找到 **bim-toolkit**，点安装，作用域选 **用户作用域**（默认）
4. 执行 `/reload-plugins`，然后**新开一个对话**

---

## 二、装完你会得到什么

| # | 助手             | 你可以这样说                            |
| - | -------------- | --------------------------------- |
| 1 | **碰撞检测报告分析**   | 「分析这份碰撞报告」（上传 Navisworks 导出的报告文件） |
| 2 | **专项可视化方案**    | 「管线综合专项怎么配色出图」                    |
| 3 | **选题调研**       | 「帮我调研综合管廊方向的 BIM 选题」              |
| 4 | **参数化族创建**     | 「盾构管片族怎么建」                        |
| 5 | **建模框架搭建**     | 「帮教学楼项目定标高轴网」                     |
| 6 | **4D 施工模拟**    | 「我要做基坑项目的 4D 模拟」                  |
| 7 | **工程量统计**      | 「模型量和清单量为什么不一样」                   |
| 8 | **答辩 PPT 生成**  | 「帮我生成 XX 项目的答辩 PPT」               |
| 9 | **Skill 制作规范** | 「按 BIM 系列的规范做一个新 skill」           |

**不需要记命令**，直接用自然语言说要做什么，助手会自动匹配。

---

## 三、推荐使用顺序

这 9 个助手是按真实工作流串起来的，建议按顺序用：

```
选题调研 → 建模框架 → 参数化族 → 专项可视化 → 碰撞检测 → 4D 模拟 → 工程量统计 → 答辩 PPT
                                                                    （Skill 制作规范 可随时查）
```

**几个高频场景：**

**场景 A：还没定题**

> 「帮我调研地下综合管廊方向的 BIM 选题，我们是 4 人小组」

**场景 B：模型建完了**

> 「分析这份碰撞报告，按严重程度排一下整改优先级」（把报告文件拖进来）

**场景 C：要答辩了**

> 「帮我生成 XX 综合管廊项目的答辩 PPT，方向是地下综合管廊，核心成果是……，创新点是……，答辩时间 15 分钟」

---

## 四、常见问题

**Q：提示「市场未找到」或「路径未找到」**  
A：`add` 后面必须是 `用户名/仓库名` 两段式，不能带 `https://github.com/` 前缀。

**Q：`install` 时提示找不到市场名**  
A：市场名可能是 `bim-skills`，也可能是 `用户名-bim-skills`（客户端按来源推导）。先发  
`/plugin marketplace list` 看实际列出的名字，再用  
`/plugin install bim-toolkit@列出来的那个名字`。

**Q：装完没反应**  
A：发 `/reload-plugins`，然后**新开一个对话**。老对话不会加载新插件。

**Q：想确认装没装上**  
A：发 `/plugin`，进「已安装」标签页查看。

**Q：能只装其中几个吗**  
A：本插件是整体安装的。如果只需要某一个能力，装了全套也不影响 —— 助手会按你的话自动匹配，不会乱触发。

---

## 五、更新与卸载

```
/plugin marketplace update bim-skills
```

卸载：

```
/plugin uninstall bim-toolkit
```

> ⚠️ 注意：`/plugin marketplace remove bim-skills` 会把从该市场装的插件一并卸载。

---

## 六、仓库结构

```
bim-skills/
├── .codebuddy-plugin/
│   └── marketplace.json          # 市场清单
├── plugins/
│   └── bim-toolkit/
│       ├── .codebuddy-plugin/
│       │   └── plugin.json       # 插件清单（声明它包含哪些 skill）
│       └── skills/               # 9 个 skill
│           ├── bim-clash-analysis/
│           ├── bim-topic-visualization/
│           ├── bim-topic-research/
│           ├── bim-family-creation/
│           ├── bim-framework-setup/
│           ├── bim-4d-simulation/
│           ├── bim-quantity-takeoff/
│           ├── bim-defense-ppt/
│           └── bim-skill-authoring/
├── LICENSE
└── README.md
```

每个 skill 目录内是固定结构：`SKILL.md`（说明书）+ `scripts/`（生成脚本）+ `assets/`（知识库 JSON）+ `references/`（参考文档）。所有脚本**只用 Python 标准库**，无网络访问、无外部依赖。

---

## 七、重要说明

- 各助手产出的**量化指标、时间比例、提问占比等均为经验参考值**，必须替换为你项目的真实数据后再使用。
- 文档中凡标红的 **〔待补充〕** 就是需要你填实的地方，不要当作结论直接引用。
- 涉及课设/毕设的**规范条文、评分要求**，请以本校本专业的答辩要求与导师意见为准。

---

## 许可

MIT License，可自由用于教学。详见 [LICENSE](./LICENSE)。
