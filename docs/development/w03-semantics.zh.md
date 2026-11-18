# W03-b case_11 语义抽取

2026 年 11 月 10 日

本阶段从已导入的 case_11 论文中生成带来源的模型条件、分析方法和候选目标清单。输出可保存、重新打开并逐条核对，但仍是语义草稿，不会自动成为推理上下文或形式证明。

当前实现是针对 case_11 六页作者版的本地规则抽取。规则实际匹配 PDF 抽取文字和页面区域；文字关系符由输入捕获，公式解释使用单独标记的已整理模板。本阶段未调用模型 API，不代表任意论文的自动语义识别，也不表示 A24 的通用抽取能力已通过验收。

## 本次结果

真实 case_11 输入产生 15 个条目，共 44 处来源引用。引用数包含不同条目对同一原文的再次引用。

| 分类 | 数量 | 内容 |
|---|---:|---|
| 模型条件与范围 | 8 | 参数关系、DM 优先级、零星释放间隔、零星截止期、周期/零星混合、RM 背景下的抢占与独立性、同步等扩展范围 |
| 分析方法 | 3 | 原文测试 (1)、测试 (2)、Fig.3 迭代算法 |
| 候选目标 | 4 | Fig.3 接受充分性、精确性、DM 最优性、任意固定优先级下的接受充分性 |

所有条目为 needs_review；所有候选目标为 unproved。主目标沿用既有决定 D11 的 Fig.3 接受充分性，其选择记录保存于 project_choices.prior_selection，没有将论文的精确性声明直接变成已证明结果。

整数时间、从空系统开始、合法零星轨迹、稳定同截止期排序和零开销等已确认建模选择，来自独立数学合同，在 project_choices 中记录合同摘要及 D12/D13 决定编号。原文 C≤D≤T 与项目要求 0<C≤D≤T 分开保存。

## 开发者入口

在 autoRTA-platform 项目根目录的 PowerShell 中运行：

~~~powershell
# Extract the reviewed case_11 PDF and render its second physical page.
.\import-paper.ps1 -Semantics -Page 2

# Extract semantics from an existing imported layout.
.\import-paper.ps1 -Extraction '<extraction_id>' -Semantics

# Reopen the exact semantic snapshot returned by extraction.
.\import-paper.ps1 -SemanticSnapshot '<semantic_id>' -Page 4

# Run semantic acceptance in isolated databases.
.\import-paper.ps1 -CheckSemantics

# Re-run the existing PDF import and source-location checks.
.\import-paper.ps1 -Check
~~~

普通命令返回 extraction_id、semantic_id、semantic_items、semantic_status、semantic_issues 和输出目录。来源不全时 semantic_status 为 partial，缺口在 semantic_issues 中列出；完整匹配时仍为 needs_review。

输出目录保留：

- semantics.json：完整数据、引用、规则版本和已有项目选择。
- semantics.md：按模型、分析、目标排列的核对清单，包含原文页码、字符范围及解释标签。
- extraction.json、preview.png：原有版面抽取与页面预览。
- history.dump：包含语义索引的数据库备份。

CLI 复用原有目录锁、数据库恢复和新备份发布流程。新的语义抽取结果保存到原有内容寻址对象目录；相同输入、规则、代码与合同得到同一 semantic_id。规则、代码或合同摘要变化会产生新身份。

## 数据结构与代码阅读顺序

| 文件 | 职责 |
|---|---|
| [models.py](../../src/platform_core/semantics/models.py) | SourceEvidence、SemanticItem、SemanticSnapshot 和稳定诊断异常 |
| [case11.py](../../src/platform_core/semantics/case11.py) | 从实际词记录匹配规则，将搜索结果映射回原始文字，传播缺失依赖 |
| [service.py](../../src/platform_core/semantics/service.py) | extract/open 接口、不可变保存、来源校验和 Markdown 导出 |
| [schema.sql](../../src/platform_core/semantics/schema.sql) | semantic_snapshots 索引与只追加约束 |
| [语义规则](../../configs/case11-semantic-rules.json) | 来源选择、材料角色、公式解释、依赖和核对问题 |
| [项目选择](../../configs/case11-project-choices.json) | 独立项目合同及既有数学范围决定 |
| [验收案例](../../tests/acceptance/w03_semantic_cases.py) | 真实论文、输入扰动、引用完整性与存储边界 |
| [验收运行器](../../tools/check_w03_semantics.py) | 隔离数据库、完整报告及新数据库恢复 |

SourceEvidence 包含选择器名称、prose/formula_region 类型和一个或多个 SourceAnchor。每个引用固定 PDF 摘要、版面抽取身份、物理页码、Unicode 码点范围及精确原文。矩形可通过已有 PaperImporter.resolve(anchor) 获取，供后续 Web 高亮使用。

SemanticItem 记录分类、摘要、规范化内容、规范化来源、材料角色、依赖、核对状态和证明状态。SemanticSnapshot 固定全部条目、缺口、配置/代码摘要与项目选择；ready_for_reasoning 在本模块恒为 false。

Python 的模块、类、函数、参数及字段使用英文说明；函数以 @param、@return、@raise 等标记，字段以 @ivar 标记，局部变量旁解释用途、位置映射和身份关系。PowerShell 保留其原生帮助注释规范。

## 来源匹配与解释边界

1. 对原始词记录按页、栏或矩形选择，生成只用于搜索的空白规范化视图；换行连字符可在搜索视图中归并。
2. 搜索字符始终保留到原始词的映射。引文保留原始字符，不以搜索串或数学模板替换。
3. 一条文字规则必须唯一匹配；无匹配或重复匹配会产生诊断并省略该条目。
4. 公式区域必须找到预定标记才能产生候选。标记检查只验证区域存在，不能检测公式的所有数学变化。
5. 参数不等式的关系符来自实际输入。若与当前已审核范围不同，输出保留实际关系符，并阻断关联目标。
6. 缺失条件或算法会使依赖它的目标变成 blocked；目标原有保证声明仍可保留供核对。
7. 从完整原 PDF 保留的资料，与输出候选清单分别处理。本规则只选模型描述、算法定义与保证声明，不将作者论证段落整体送入推理；尚未实现通用材料分类器。

规范化字段分三类：

| normalization_origin | 含义 |
|---|---|
| captured_operators | 关系符从实际原文匹配捕获 |
| rule_interpretation | 由当前规则解释已匹配的自然语言，需人工核对 |
| reviewed_formula_template | 结合已查看的页图与来源记录整理的公式模板，未声称由通用公式解析器自动恢复 |

尤其注意：抢占与独立性语句来自引言的 RM 背景，角色保持 background；不能自动当作 DM 主目标已经确认的论文前提。DM 最优性只保存论文引用的声明，并标注还需核对 Leung 1982 的原定理前提。

## 保存与恢复边界

语义索引引用 W03-a 的原始文件和版面记录；语义清单、规则、代码和数学合同分别保存为带摘要的对象。重新打开时核对索引身份、配置对象、原 PDF 和每处精确引文。原文或规则对象缺失、损坏时拒绝返回结果。

数据库触发器拒绝修改、删除和清空语义历史。新抽取发现项目合同与配置摘要不同会拒绝运行；旧快照仍能以归档合同读取，避免当前工作文件的变化破坏历史查看。

本模块不提供语义确认、目标编辑或推理启动接口。后续确认应创建新修订，不能原地把草稿改成已确认或已证明。

## 验收证据

本次语义验收 46 项通过：

- [机器报告](../../artifacts/w03/semantic-checks/20261110T122640Z-e69b6a5a/report.json)。
- [本次提取草稿](../../artifacts/w03/imports/20261110T122730Z-17cc4cb8/semantics.md) 与 [结构化结果](../../artifacts/w03/imports/20261110T122730Z-17cc4cb8/semantics.json)。
- [第 2 页预览](../../artifacts/w03/imports/20261110T122730Z-17cc4cb8/preview.png) 与 [重开后的第 3 页预览](../../artifacts/w03/imports/20261110T122800Z-0db041d7/preview.png)。
- [原有 PDF 模块回归报告](../../artifacts/w03/checks/20261110T122640Z-23944979/report.json)：40 项通过。

验收包含真实来源与分类、全部引用逐一解析、项目范围分离、输入缺失/重复/关系符变化、公式区域缺失、错误引用与伪造证明状态、历史合同恢复、不可变数据库及源对象破坏。缺失与歧义测试使用明确标记的内存版面扰动，未伪装成另一份真实论文的能力验证。

另外静态检查了 24 个显式函数及其参数文档、数据字段的 @ivar 文档，未发现遗漏。开发阶段查看了生成的来源页图与核对清单；这一检查不替代用户对数学语义的确认。

## W03 后续工作

下一步实现本地 Web 的“原文—抽取字段”核对页面、关键字段修订、候选目标选择和上下文冻结，再把确认后的输入交给 W04。需要建立语义确认记录与模型/目标修订的关联，保持作者证明材料隔离。

更换论文或排版时，需要新的抽取适配器或配置好的模型服务及相应验收材料。当前实现对不支持的论文返回 unsupported_paper；相同标题及布局仅用于选择适配器，不构成语义等价保证。通用公式结构解析、自动理解任意论文与多栏复杂表格仍属后续能力。
