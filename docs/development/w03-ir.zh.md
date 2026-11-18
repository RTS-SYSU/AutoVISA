# W03-d 冻结上下文到 Analysis IR / Rocq 目标

2026 年 11 月 11 日

本阶段完成 case_11 已支持合同的形式映射：读取已冻结的核对修订，生成带类型的 Analysis IR、显式 Rocq 目标声明和独立的映射回执。函数、参数、状态字段及数学变量使用英文文档注释；Python 采用 @param / @return / @ivar / @var，JavaScript 采用 JSDoc，生成的 Rocq 文件也保留英文参数说明。

**检查通过表示声明和既有 W01 合同对应，主要目标仍为 unproved。** 本次没有构造 Fig.3 调度充分性的完整证明，也没有调用外部模型 API。验收中的确认来自明确标记的独立夹具，不是用户的实际数学核对。

## 使用方式

在项目根目录启动工作台：

~~~powershell
.\start-workbench.ps1
~~~

完成来源核对与冻结后，在“变更与冻结记录”中点击“生成 Analysis IR / 检查 Rocq 目标”。页面显示映射结果与缺口；点击回执链接可查看完整 JSON，包含 IR、来源、冻结修订和检查材料摘要。刷新页面或查看历史修订后，回执仍按冻结身份恢复。

命令行共用正式本地目录锁，使用前先停止工作台：

~~~powershell
.\map-frozen.ps1 -Freeze '<冻结上下文完整 ID>'
.\map-frozen.ps1 -Receipt '<已有映射回执完整 ID>'
.\map-frozen.ps1 -Check
~~~

前两条在 artifacts/w03/mappings/ 下导出 analysis-ir.json、mapping.json、可生成时的 Mapped.v / Audit.v，以及数据库备份。-Check 使用独立数据库和 objects 目录，不操作正式核对项目。

## 数学内容与映射边界

当前适配器支持已锁定 case_11 来源和整数零星 DM 合同。进入冻结上下文的模型、分析和目标条目，其 summary、normalized、material_role 必须与审核基线一致；所有项目范围陈述也必须一致。源 PDF、规则、合同和 W01 定义通过 SHA-256 固定。

这是有限范围的确定性编译器。它不解析任意修订后的自然语言，也不自动认定两段不同文字数学等价。即使仅改变说明文字，也会产生 semantic_variant，等待后续建立审核过的等价映射。只修正合法引用范围、保留数学字段不变时，可以映射并绑定新来源和新修订。

| IR 部分 | 当前内容与对应 |
|---|---|
| 类型系统 | Nat、Task、TaskSet、Arrivals、Schedule、OptionTask、Prop；检查变量作用域、调用参数和结果类型 |
| 算术表达式 | 自然数加减乘除、最小值、比较、任务前缀、任务求和 |
| 分析定义 | ceil_div、Fig.3 初值、干扰工作量、测试 (1)、测试 (2)、有限接受轨迹 |
| 模型定义 | 对固定 W01 内核定义的带类型引用；同时记录文件、定义行、源码摘要、语义条目和项目选择 |
| 主目标 | 对任务集、合法到达轨迹及调度的全称量化，保留五个前提及全体作业按期完成的结论 |
| 其他所选目标 | 精确性、DM 最优性等全部保留，尚未编码者明确 blocked |

主目标生成的结构如下：

~~~text
forall ts : TaskSet, a : Arrivals, s : Schedule,
  taskset_wf ts ->
  legal_arrivals ts a ->
  bounded_demands ts a ->
  valid_dm_schedule a s ->
  ir_fig3_accepts ts ->
  all_deadlines_met ts a s
~~~

IR 的模型部分引用已锁定的语义内核，并未把整个 Model.v 展开成新的通用语言。内核规定整数时间、从空系统开始、任意合法释放与执行量、0<C≤D≤T、抢占式单处理器 DM、固定任务序号解同截止期平局，以及无阻塞、自挂起和调度开销。任务释放序列不限于同步周期样例。

接受条件使用 W01 的 accepts_from 归纳关系；初值是自身与所有高优先级任务执行上界之和。自然数运算的下取整和截断减法含义由类型与固定定义决定。

## Rocq 检查的含义

1. 从 IR 表达式生成定义和完整量化命题，不以旧目标别名替代新目标。
2. 真实 rocq compile 检查类型，并证明初值、工作量、接受谓词和主目标声明与 W01 定义相等。
3. 将内容寻址的 .vo 复制到另一目录，在不重叠的逻辑路径下运行 rocqchk；检查内核安全摘要、无公理及实际加载模块的允许清单和摘要。
4. 在独立目录编译 Audit.v，核对目标对应引理没有额外假设。

这些等式只证明翻译对应。测试 (1)/(2) 的公式获得类型检查和来源关联；本阶段没有证明它们各自的调度充分性。Rocq 也不能证明人工语义解释忠实于论文，这仍依赖来源核对和数学审查。

## 来源与修订链

~~~text
PDF 摘要 + 版面抽取身份 + 页码/码点范围/原文
    -> 原始语义快照 semantic_id
    -> 已确认 review_revision（可回溯父修订与修改记录）
    -> freeze
    -> analysis-ir.json
       bindings / kernel_bindings / goal_revision
    -> 映射回执 + 编译器源码 + 基线 + .v/.vo + 检查日志
~~~

每个 bindings 项保留当前核对修订的来源和规范化表达；每个内核绑定同时关联语义条目、项目选择、实际定义文件与源码摘要。只追加的 formal_mappings 表绑定回执和 freeze。旧冻结仍保持原始 mapping_required 字段，由独立回执报告后续结果，不覆盖冻结内容，也不产生 W02 proof attempt。

读取历史回执时校验其内容摘要、数据库索引、所有归档材料和原冻结修订。新修订、新冻结、源码后续变化不会把旧证据自动转移到新目标。

| 回执状态 | 含义 |
|---|---|
| mapped | 所选目标全部支持，声明与对应关系检查成功 |
| partial | 至少一个目标支持且检查成功，其他目标保留缺口 |
| blocked | 无可映射目标，不调用 Rocq |
| failed | 构建、独立检查或依赖校验失败，保留诊断 |

prepare() 的同名状态表示计划覆盖程度；只有 compile() 保存的回执及两个 passed 检查字段才能表示实际编译、复检成功。proof_status 始终单独报告。

## 接口与代码阅读顺序

| 文件 | 职责 |
|---|---|
| configs/case11-ir-profile.json | 明确的语义基线、合同和源码锁 |
| src/platform_core/analysis_ir/case11.py | 分析公式、量化目标和内核对应 |
| src/platform_core/analysis_ir/language.py | 有限类型语言及安全的 Rocq 渲染 |
| src/platform_core/analysis_ir/service.py | prepare、compile、open、history 与来源/修订校验 |
| src/platform_core/analysis_ir/schema.sql | 不可改写的回执索引 |
| tools/map_frozen.py / map-frozen.ps1 | 映射、重开与验收入口 |
| tools/check_w03_ir.py / tests/acceptance/w03_ir_http.py | 真 PDF、真数据库、真 Rocq 和 HTTP 验收 |

HTTP：POST /api/map-preview、POST /api/map，输入为 freeze；GET /api/mapping?id=... 读取完整回执；GET /api/mappings?freeze=... 恢复回执列表。写操作沿用同源令牌与持久化发布规则。

## 本次验证

- 40 项映射验收通过：真实 PDF 到冻结输入、类型检查、Rocq 编译和独立内核检查、来源修正、旧修订保持、部分目标、范围/初值/目标变化、篡改检测、数据库独立恢复，以及 8 项 HTTP 行为。
- 负向检查实际删除了 legal_arrivals 前提；生成命题仍有类型，但 Rocq 拒绝其与原目标的对应等式。
- 原有 46 项 HTTP 来源核对、修订与冻结回归通过。
- 浏览器新增 6 项观察通过：按钮、语义差异、未支持目标、刷新保留回执、未证明标记、无控制台错误。浏览器使用历史变体夹具，展示 blocked；成功编译由上面的真实工具链验收覆盖。

最新映射报告入口：[ir-checks/latest.json](../../artifacts/w03/ir-checks/latest.json)。
Web 回归报告：[20261111T013659Z-227fa792/report.json](../../artifacts/w03/web-checks/20261111T013659Z-227fa792/report.json)。
浏览器记录：[ir-browser-report.json](../../artifacts/w03/web-browser-test/ir-browser-report.json)。

## 后续

本次工程链路已支持进入 W04 的固定合同输入。正式 case_11 的实际人工数学核对仍需由用户完成；其他语义变体和目标需新增经过审核的映射。W04 从回执中读取精确 IR 和目标修订，建立前向推导、后向义务、对齐和桥接检查；完整主目标证明继续作为首版发布门槛。
