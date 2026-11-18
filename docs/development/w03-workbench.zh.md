# W03-c 本地来源核对工作台

2026 年 11 月 10 日

本阶段接通“已有语义草稿或 PDF → 原文核对 → 字段修订 → 目标多选 → 上下文冻结”。页面与验收使用同一个 ReviewWorkspace 模块，校验位于服务端。当前仍使用 W03-b 的 case_11 本地规则适配器。

冻结产物是经过人工核对的语义输入清单。它保留原始来源、修订、项目范围及全部所选目标，证明状态始终为 unproved；formalization_status 为 mapping_required。后续还要把具体修订映射到 Analysis IR / Rocq 声明，不能直接用旧 W01 主目标名替代修改后的数学内容。

## 启动与操作

在项目根目录的 PowerShell 中运行：

~~~powershell
.\start-workbench.ps1
~~~

等待出现 ready 后，在浏览器打开 http://127.0.0.1:8765 。终端保持运行；按 Ctrl+C 停止。换端口可使用 -Port 8767。工作台只监听本机回环地址。

首次使用按以下顺序操作：

1. 点击“导入 / 新建”，选择 case_11 PDF 上传，或选择已保存的语义草稿并创建核对项目。
2. 左侧选择模型条件、分析方法或候选目标。点击每段引用的“定位原文”查看 PDF 页图与词级高亮；也可切换到文字视图。
3. 修订陈述、规范化表达或材料角色。需要补充来源时，在右侧文字视图选中原文，点击“将选中文字补充为来源”；可以移除错误引用，但至少保留一处有效来源。
4. 核对条目中的待处理问题后，将“本次核对结论”设为“已核对”。点击“预览本条修订”，检查前后差异、受影响目标，填写核对说明并确认保存。
5. 在“选择证明目标”中多选目标并登记其中一个为主要目标。原有整数时间等范围选择可在“形式化范围”中查看；已有 D12/D13 决定直接保留，修改它们会要求新的确认。
6. 点击“预览冻结上下文”。仍有待处理条目、未确认依赖或不允许的材料角色时，页面列出原因并禁止冻结。条件满足后核对目标与范围摘要，再确认冻结。

“变更与冻结记录”可下载完整上下文。顶部“修订历史”可查看旧字段、确认记录与差异；历史修订不能编辑或冻结，原文定位仍可使用。后续修改产生新修订，原冻结上下文保持可访问。

核对人是本机填写的归属标签，不是账号认证。工作台面向单机开发与核对，不提供多用户登录或远程共享。

## 核对规则

- 原始 PDF、版面抽取和语义草稿均保持不变。页面编辑的是独立的核对修订。
- 每个候选保留稳定 key、分类和依赖。当前编辑器支持已有候选字段及已有规范化结构的字符串叶子；新增候选类别、改变表达式树结构需扩展抽取/表示模块。
- 引文必须对应当前 PDF、当前版面抽取、同一页的合法 Unicode 码点范围及精确文字。补充引用时服务器重新计算引文和词矩形。
- 原文来源与项目选择分别存储。修改后的项目选择继续保留原合同身份作为基线，新的 statement 与确认记录归属本次修订。
- 进入上下文的模型条件与分析方法，以及每个所选目标，都必须明确确认。依赖条目缺失、排除或未确认时，目标不能冻结。
- background、scope_limit 和 author_proof 角色不能直接进入推导输入；背景和范围说明默认排除。编辑成作者证明角色后，即使选择“已核对”，冻结仍会阻断。
- 模型、分析、来源或项目范围内容变化，以及条目纳入/排除变化，会保守地重新打开目标核对。确认可以绑定同一份具体变更预览。
- 预览没有持久化副作用；保存需要提交同一预览摘要和预期修订。旧标签页不能覆盖新的项目头修订。
- 所选目标只决定冻结清单，不自动获得形式证明。当前不产生 W02 proof attempt 或 proof receipt。

材料角色检查是结构与人工核对门槛，尚不能自动识别任意自然语言中夹带的作者证明步骤。公式仍使用 W03-b 中明确标记的解释模板；“已核对”表示本次记录者确认了来源和解释，不能替代数学有效性证明。

## 数据与接口

| 文件 | 职责 |
|---|---|
| [review/service.py](../../src/platform_core/review/service.py) | 创建项目、打开修订、准备差异、确认保存、冻结及历史完整性检查 |
| [review/schema.sql](../../src/platform_core/review/schema.sql) | 只追加的项目、修订和冻结索引 |
| [review/http.py](../../src/platform_core/review/http.py) | 本机 HTTP、来源页图、引用解析、上传、导出与持久化确认 |
| [web/app.js](../../web/app.js) | 核对编辑器、目标选择、来源高亮、文字选段与确认流程 |
| [web/index.html](../../web/index.html) / [web/style.css](../../web/style.css) | 可访问的页面结构与响应式布局 |
| [tools/workbench.py](../../tools/workbench.py) | 目录恢复、数据库生命周期、备份发布和启动 |
| [tests/acceptance/w03_web_cases.py](../../tests/acceptance/w03_web_cases.py) | 真实 HTTP 与历史/冻结验收 |

模块的主要 Interface：

~~~text
create(semantic_id, name)
read(project, revision=None)
prepare(project, expected, patch)
commit(project, expected, patch, token, actor, reason)
preview_freeze(project, expected)
freeze(project, expected, token, actor)
frozen(identity)
~~~

修订清单含 project、parent、完整 state、逐字段 changes、actor 和 reason；数据库另存 generation 与时间。记录身份是清单内容摘要。冻结清单固定 revision、semantic_id、来源身份、模型、分析、所选目标、主要目标、scope、材料策略及未证明状态。

原始抽取的 status / review_issues 保留为来源诊断历史；人工核对状态使用新增 decision 字段。冻结判断只采用当前修订的明确核对结果和依赖检查，不把抽取阶段 needs_review 文本当成新的证明结论。历史读取会核对清单摘要、原始 PDF、来源引文和冻结字段与当时修订的逐字段一致性。

scope_status 为 contract_scope_reference 或 reviewed_variant。对内容编辑采用保守的变体标记，即使改动只是文字解释，也不会自动宣称与旧形式目标完全等价。所有冻结产物仍要求形式编码映射。

Python 函数和参数使用英文 @param / @return / @raise 文档，实例变量使用 @ivar，局部变量说明其用途和身份关系。JavaScript 使用 JSDoc/Javadoc 风格英文函数、参数、返回值及状态字段注释；PowerShell 使用原生帮助注释。

## 本地保存与运行限制

正式目录复用 artifacts/w03/catalog.json 和 objects/。运行时使用私有 PostgreSQL；整个会话持有原有目录锁。每个修改请求在返回成功前，导出新的 web-checkpoints 备份、刷新文件和目录、原子更新 catalog.json。正常停止时再次保存。

备份失败返回明确的 503 诊断，不报告保存成功。数据此时可能已进入运行中的数据库；应保留服务进程并重试，下一次写入先重试发布。正常启动会验证备份摘要后恢复历史。

同一正式目录同时只运行一个工作台。工作台运行期间，使用该目录的普通 import-paper.ps1 命令会等待目录锁；先停止工作台，再运行普通导入 CLI。隔离验收有自己的数据库和目录，可以独立执行。

HTTP 限制 Host 和 Origin，写操作要求同源会话 token，上传限制为 20 MiB，JSON 请求限制为 2 MiB。静态资源采用固定文件清单；不把 URL 当作本地文件路径。浏览器渲染原文和修改值时只写 textContent，不执行论文内容。全部请求访问本机数据，不调用模型 API。

## 验收与证据

~~~powershell
# Real HTTP, PostgreSQL, revision and freeze acceptance.
.\start-workbench.ps1 -Check

# Browser checks with isolated fixture confirmations.
.\start-workbench.ps1 -Testing -Port 8766

# Existing source and semantic regression suites.
.\import-paper.ps1 -CheckSemantics
.\import-paper.ps1 -Check
~~~

本次结果：

| 检查 | 结果 |
|---|---|
| Web/核对模块真实 HTTP 验收 | 46 项通过 |
| 原有语义抽取回归 | 46 项通过 |
| 原有 PDF 导入回归 | 40 项通过 |
| 独立浏览器操作 | 11 项流程观察通过 |
| 文档与语法检查 | 38 个 Python 函数、29 个 JavaScript 函数的显式参数文档无遗漏；JS 语法检查通过 |

HTTP 验收覆盖真实 PDF 上传、页图与引用、预览只读、差异与影响、错误引用、旧修订提交、多目标绑定、冻结门槛、材料角色、历史只追加、备份失败与重试、正常停止，以及第二个全新数据库的恢复。没有调用模型，也没有运行新的形式证明。

浏览器实际操作验证：引用高亮、字段编辑预览与确认、冻结阻断、多目标选择、逐条核对、冻结与下载入口、历史只读、刷新后恢复、文字选段补充引用，以及修改后重新打开目标核对但保留旧冻结记录。浏览器未报告脚本错误。

- [Web 验收报告](../../artifacts/w03/web-checks/20261110T131416Z-66fd7578/report.json)
- [冻结上下文验收样本](../../artifacts/w03/web-checks/20261110T131416Z-66fd7578/frozen-context.json)
- [浏览器验收记录](../../artifacts/w03/web-browser-test/browser-report.json)
- [浏览器冻结截图](../../artifacts/w03/web-browser-test/freeze.jpg)
- [语义回归报告](../../artifacts/w03/semantic-checks/20261110T130821Z-b7bb1882/report.json)
- [PDF 回归报告](../../artifacts/w03/checks/20261110T130821Z-c03db2da/report.json)

自动化与浏览器确认均为标注清楚的隔离工程夹具，保存在 web-checks/ 或 web-browser-test/，不会计作用户对正式项目的数学确认。

## 后续边界

本轮请求的 Web 来源核对、字段修订、目标选择、上下文冻结已接通。W03 的 case_11 人工数学核对和所选修订到形式化 IR 的精确映射仍需作为独立证据补齐；不能把 Web 验收通过等同于 A24 的完整数学验收。完成该映射后，再由 W04 使用同一冻结输入独立构建双向推导与对齐。

当前未实现任意论文理解、通用公式类型检查、W04 推导图、运行管理或目标证明。现有 W01 模型、W02 检查器与证明证据保持独立。
