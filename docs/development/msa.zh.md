# 通用 MSA 与 Prosa：第一条可运行流程

当前已实现来源独立的语义输入、形式映射和有限的实际证明尝试。它是通用平台的第一阶段，不代表任意论文或调度方法都已支持。

## 使用

在 Windows PowerShell 中：

~~~powershell
Set-Location 'C:\Users\zhenghui\Desktop\autoRTA-platform'
.\start-workbench.ps1
~~~

打开 http://127.0.0.1:8765/msa 。旧工作台仍在根地址。终端保持运行，Ctrl+C 后保存退出。

先体验已有证明证据：

~~~powershell
.\start-workbench.ps1 -MsaDemo
~~~

演示使用 artifacts/msa/browser-test，不向正式 artifacts/w03 目录写入验收确认。

1. 选择空白 MSA、导入 JSON，或导入数字版 PDF。两个示例按钮创建待核对输入，不自动确认。
2. 填写变量、单位、模型条件、分析函数及候选目标。自然数表达式可以写成 total_budget(c, interference) <= deadline；复杂结构使用 JSON AST。分析函数参数必须显式声明。
3. 填写手工来源，或在 PDF 页面的原文选中文字，引用到条目。对照页图检查公式、字形、表格和多栏阅读顺序。
4. 为本轮选择目标和主要目标，逐项核对。作者证明材料需明确排除；当前不把它当作独立构造的假设。
5. 预览具体差异，填写核对人及说明后保存。修改后的条目会回到待核对；共享数学条件变化也会使目标重新待核对。保存后再确认条目，直到没有阻碍。
6. 冻结已保存的修订，映射到 Analysis IR。不支持的范围、缺表达式、未知变量、类型错误会保留为缺口。
7. 对已映射目标运行真实 Rocq 检查。每次最多 1–8 个候选检查；每个所选目标最多尝试一次，超出预算的目标保持开放。
8. 打开结果中的原始记录、源码、精确类型、内核、假设和实际依赖日志。新修订和新检查不会替换旧结果。

自然语言说明与结构化表达式的对应需要人工核对。当前单位作为明确元数据保留，尚无自动量纲推导。形式检查只证明生成的精确命题。

## 当前领域能力

| 适配器 | 数学含义 | 当前边界 |
| --- | --- | --- |
| nat_arithmetic_v1 | Nat 全局变量、纯分析函数、显式命题前提和目标 | 有限算术规则；没有内置调度保证 |
| prosa_ceil_v1 | Prosa div_ceil 定义与可选单调性复用 | 自然数输入；零除数遵循库定义，不能自动解释为正周期 |

未知能力、连续时间、额外未编码范围字段均产生缺口，不自动转成整数模型。多目标逐项保留状态；共享前提未映射时阻止所有相关目标进入检查。

执行预算示例证明 c + interference <= deadline → c <= deadline。这不是完整响应时间定理，也不是对干扰预算来源的证明。

## Prosa 适配

复用资源为 Prosa 0.6 的：

- prosa.util.div_mod.div_ceil
- prosa.util.div_mod.div_ceil_monotone1
- MathComp ssrnat.leP，用于把布尔不等式与标准 Nat.le 连接。

平台的表达式使用完全限定的 Nat.le 等运算，避免 Prosa/MathComp 导入改变记号含义。反射桥接由真实 Rocq 编译；目标包装器再次核对精确类型，之后执行独立内核、无公理和实际依赖审计。

独立构造路线不会使用覆盖该资源目标的单调性桥接定理；库复用路线可以使用。实际引用列表从 Print All Dependencies 的声明记录识别，完整日志一并保留，不以导入模块或路线名称冒充实际使用。

toolchain/prosa-ceil-lock.json 锁定该资源检查时加载的 251 个库模块源码/二进制，以及相关包版本。它是一个受控资源适配，不是对全部 Prosa 模块开放导入。旧库配置与旧证据保持原样；每次新检查单独记录环境版本。

## PDF 与模型服务

通用 PDF 路径已能导入另一篇论文 rtss09-yi.pdf，保留 10 页原文、词级坐标、原始提取文件及页图。部分 PDF 的字形映射会产生 XML 不允许的控制字符；新适配器把它显示为 �，明确记录诊断并保留原始字节，不猜测数学符号。旧解析器未修改。

现在 PDF 导入后可手工形成同一份 MSA，**还没有通用自动语义抽取**。模型偏好记录在 configs/model-service.json，为 OpenAI gpt-6.1-sol、reasoning effort high。官方[模型页](https://developers.openai.com/api/docs/models/gpt-6.1-sol)是后续接入依据。当前配置是偏好记录，尚无启用中的 API 客户端；未读取密钥、未发送论文、未产生模型费用。下一阶段实现客户端与调用回执，并在首次真实调用前完成材料范围、凭证和费用上限配置。

## 验证和阅读入口

~~~powershell
.\check-msa.ps1
~~~

主要报告：artifacts/msa/checks/20261112T032611Z-d3a37f6e/report.json，8 项通过。
补充适配检查：artifacts/msa/adapter-check/report.json，3 项通过，仅覆盖已发现的字形问题、库版本不兼容和实际引用显示。
兼容检查：artifacts/msa/legacy-check/report.json，1 项通过，只恢复并读取旧 W06 运行和比较，不重复执行证明。
Web 验证记录：artifacts/msa/browser-test/browser-report.json。

主要 Interface：

- src/platform_core/msa/document.py：输入契约、数学变更分类与核对失效。
- src/platform_core/msa/service.py：创建、修订、冻结、结果与来源历史。
- src/platform_core/msa/mapping.py：领域能力、类型检查、精确命题和来源对应。
- src/platform_core/msa/checker.py、proof.py：库环境、反射桥接、有限证明策略和真实审计。
- src/platform_core/msa/pdf.py：通用 PDF 适配；旧提取配置独立保留。
- web/msa.js：与后端同一工作流的本地界面。

下一阶段依次补充：实际模型服务 → 带引用的 PDF 语义候选 → 更完整的调度领域能力 → 动态双向推理及对齐 → 受预算约束的证明修订循环。当前新 MSA 尚未接入旧 W04/W05 的推导图、反馈与父子运行比较；它们仍服务于原案例路线。
