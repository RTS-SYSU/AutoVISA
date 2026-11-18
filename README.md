# AutoVISA Platform

在项目根目录运行 `node tools/serve-prototype.cjs`，打开 <http://127.0.0.1:8769/> 即可体验当前的 AutoVISA 可点击原型。输入草稿和运行比较保存在当前浏览器。带后端的开发工作台使用下文的 `start-workbench.ps1` 单独启动。

面向实时系统分析方法构建、双向推导、语义对齐和形式证明的工具平台。

首版从本地 Web 工作台导入数字版论文 PDF，提取模型、分析方法和目标，独立开展双向推理、语义对齐、证明与反馈修订。当前已完成 W01 形式模型、W02 证据检查与修订存储、W03 的 PDF 来源抽取到冻结及形式映射、W04 本地规则双向推导，以及 W05 的反馈提案、关键数学确认、采用、关联运行与版本比较。主要目标的完整证明继续推进。

## 通用输入：现在可以试用

2026-11-12 增加了独立 MSA 工作台和第一组可扩展数学能力：

- 手工创建 / JSON 导入，编辑模型、分析定义、目标、单位与来源；修订预览、逐项核对、冻结和历史导出。
- 支持的数字版 PDF 导入、原文与页图核对、来源选区引用；不继承 case_11 的数学条件。
- 从结构化表达式生成目标，分别进行真实 Rocq 检查；当前适配自然数算术子问题与 Prosa 向上取整资源。
- 独立构造与库复用分开记录，保留实际依赖、环境、失败和开放义务。

**范围说明：** 通用模型驱动 PDF 语义抽取、任意调度模型适配和动态双向证明搜索还未完成；case_11 主调度目标仍开放。模型偏好已记录为 OpenAI gpt-6.1-sol / high，本轮模型调用为 0。

在项目根目录运行：

~~~powershell
.\start-workbench.ps1
~~~

打开 <http://127.0.0.1:8765/msa>。想先查看包含真实证明证据的隔离演示，使用 -MsaDemo 参数。详细操作和验收见 [MSA 与 Prosa 使用说明](docs/development/msa.zh.md)。

## 当前进展

W01 已通过真实 Rocq 编译、边界样例、正确/错误证明夹具以及独立目录内核重检。主要目标已编码并通过类型检查，完整证明仍未完成。

- [W01 完成记录](docs/reports/w01-20261105.zh.md) 汇总实际结果、日志和适用限制。
- [W01 开发与复现说明](docs/development/w01.zh.md) 给出运行方式、合同映射和库策略。
- [最近一次机器报告位置](artifacts/w01/latest.json) 指向最新运行，应同时检查其中的 passed/failed 状态。

- [W02 完成记录](docs/reports/w02-20261106.zh.md) 记录 PostgreSQL、真实证明检查及修订失效的验收结果。
- [W02 开发与复查说明](docs/development/w02.zh.md) 给出代码阅读顺序、运行命令和回执字段。

- [W03-a PDF 导入与来源定位](docs/development/w03-ingestion.zh.md) 给出数据结构、导入命令和支持范围。
- [W03-b 语义抽取](docs/development/w03-semantics.zh.md) 已从 case_11 提取 8 项模型条件与范围、3 项分析方法、4 个候选目标。使用本地规则和显式标记的公式解释模板，全部等待核对。

- [W03-c 本地 Web 核对工作台](docs/development/w03-workbench.zh.md) 给出启动方式、核对流程、冻结规则和验收证据。
- [W03-d 形式映射](docs/development/w03-ir.zh.md) 将支持的冻结合同映射为带类型 IR 和 Rocq 目标；保留来源、修订及独立检查回执。

- [W04 双向推导与对齐](docs/development/w04.zh.md) 已接通两侧图、实例化、联合前提、路线选择与真实证明证据，取得 4 个局部完整证明。
- [W05-b 确认、采用与关联运行](docs/development/w05b.zh.md) 已接通精确数学决定、独立预算、证据继承与重检、部分结果及父子运行历史。
- [W05-c 父子运行比较](docs/development/w05c.zh.md) 固定两侧路线版本，展示模型、目标、图、证据、开放义务和用量差异，并跳转原始记录。

## 本地运行

在 Windows PowerShell 中执行：

```powershell
Set-Location 'C:\Users\zhenghui\Desktop\autoRTA-platform'
.\check.ps1
```

入口使用已有 WSL Ubuntu 和配置的 opam switch，不自动安装工具，也不调用模型 API。每次运行保留独立源码副本、日志、工具版本与文件摘要。W01 检查成功与主要目标是否证明分别报告。

W02 在同一项目根目录运行：

```powershell
.\check-w02.ps1
.\check-w02.ps1 -Goal joint-demo
```

第一条生成证据及数据库备份，第二条恢复最近一次成功运行并查询目标修订、尝试、缺口和旧证据失效原因。

W03-a 可导入 PDF，保存词级来源位置，并裁剪查看所选文字：

```powershell
.\import-paper.ps1 -Page 4 -Find 'Schedulability Algorithm'
.\import-paper.ps1 -Check
```

W03-b 可生成带原文引用的语义核对清单：

~~~powershell
.\import-paper.ps1 -Semantics -Page 2
.\import-paper.ps1 -CheckSemantics
~~~

输出目录中的 semantics.md 供核对，semantics.json 保留完整身份与引用。可通过 -SemanticSnapshot '<semantic_id>' 重开既有草稿。

W03-c 在浏览器核对来源、修订字段、选择目标并冻结上下文：

~~~powershell
.\start-workbench.ps1
~~~

看到 ready 后打开 http://127.0.0.1:8765 ，终端保持运行，按 Ctrl+C 停止。使用 -Check 运行隔离 Web 验收。正式目录的导入 CLI 与工作台共用目录锁，使用普通 CLI 前先停止工作台。

冻结后可在“变更与冻结记录”生成 Analysis IR 并检查 Rocq 目标。停止工作台后也可运行：

~~~powershell
.\map-frozen.ps1 -Freeze '<冻结上下文完整 ID>'
.\map-frozen.ps1 -Check
~~~

支持的声明及其对应关系通过真实 Rocq 检查；范围变化和未编码目标保留缺口。主目标继续标记未证明。

W04 可启动推导及查看独立演示：

~~~powershell
.\derive.ps1 -Check
.\start-workbench.ps1 -W04Demo
~~~

正式工作台从检查通过的映射进入“双向推导”；演示使用独立验收目录。详见 [W04 使用说明](docs/development/w04.zh.md)。

W05-a 已接通“反馈 → 修订提案 → 差异与影响”。在双向推导页面点击节点或对齐的反馈入口，可形成提案、查看所选路线影响，并刷新重开历史。当前使用本地规则。运行隔离验收：

~~~powershell
.\check-w05a.ps1
~~~

详见 [W05-a 使用与实现说明](docs/development/w05a.zh.md)。

W05-b 可在提案下记录具体数学决定、采用方案并开启关联运行。原运行和回执保留，新运行逐项说明证据继承与重检原因：

~~~powershell
.\check-w05b.ps1
.\start-workbench.ps1 -W05bDemo
~~~

详见 [W05-b 使用与实现说明](docs/development/w05b.zh.md)。

W05-c 从关联运行的“比较父子运行”入口选择明确版本、保存比较并重开历史：

~~~powershell
.\check-w05c.ps1
.\start-workbench.ps1 -W05cDemo
~~~

详见 [W05-c 使用与实现说明](docs/development/w05c.zh.md)。

W06 已推进服务界证明：六个通用服务引理和原服务上界获得真实 Rocq 回执；任务级工作量到逐作业容量见证的联系仍开放，主要目标尚未闭合。

~~~powershell
.\check-w06.ps1
.\start-workbench.ps1 -W06Demo
~~~

在已拆分上下界的运行中选择“推进服务上下界证明”，建议为首次重检设置 24 次预算。见 [W06 证明进展与使用说明](docs/development/w06.zh.md)。

## 已确认的首版范围

采用 case_11 的整数时间零星 DM 模型，主要目标为 Fig.3 迭代测试接受充分性。允许使用基础定义和通用引理，现成 RTA 主定理及包装隔离。用户可以纠正输入与目标、提交自然语言反馈，并从部分结果开启关联运行。

数据本地保存，允许配置外部模型 API；提供方与费用限额在首次真实调用前设置。关键数学决策由用户确认。

- [软件设计书](docs/design/software-design.zh.md)
- [首版功能与验收规格](docs/requirements/first-release.zh.md)
- [验收案例与证据](docs/requirements/acceptance-cases.zh.md)
- [数学合同](docs/contracts/case11-integer-dm-soundness.zh.md)
- [领域术语](GLOSSARY.md)
- [论文来源与范围](examples/papers/case_11/README.md)

## 代码与配置

- proofs/ 保存模型、分析测试、主要目标和形式样例。
- tools/check_w01.py 执行 W01 固定夹具检查。
- tests/fixtures/ 保存正确证明及应被拒绝的反例。
- configs/ 固定工具环境、目标元信息和库材料策略。
- toolchain/ 保存基础库摘要、最小 opam 规格与安装元数据。
- artifacts/ 保存每次运行产物，默认不纳入版本控制。

## 下一项工作

[实施计划](docs/plans/first-development-slice.zh.md) 中的 W01、W02 已完成。W03-d 已接通冻结合同到 Analysis IR / Rocq 目标的精确映射，40 项映射验收、46 项 Web 回归及 6 项新增浏览器观察通过。W04 本地规则版已通过 55 项集成验收，完成双向图、对齐与证据组合；W02 39 项、W03 映射 40 项、Web 核对 46 项回归通过。W05-a 已完成反馈提交、具体提案、差异与影响展示及历史恢复。W05-b 已通过 64 项验收及实际浏览器流程观察，W02 的 39 项、W05-a 的 67 项和 W03 Web 的 46 项回归通过。W05-c 已通过 70 项版本比较验收，W05-a 67 项和 W03 Web 46 项回归通过。W06 已完成六个通用服务引理与服务上界的真实检查，继续证明任务工作量到逐作业容量见证的联系，再形成独立重检的主要目标证据包。W06 整体和主要目标仍未完成。

项目使用 mattpocock-skills 的领域建模与模块设计方法。插件项目级配置尚未执行。设计书中的后续接口、目录与排期仍按实际工作包逐步验证。
