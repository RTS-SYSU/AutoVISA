# AutoVISA

AutoVISA 是一个面向实时系统研究者的本地工作台。可以从论文或手动输入开始，选定一项调度保证，查看从模型推出的引理、从目标拆出的子目标，以及 Rocq 对最终命题的检查结果。

## 启动工作台

安装 Node.js，在仓库根目录运行：

```sh
node tools/serve-prototype.cjs
```

打开 [本地工作台](http://127.0.0.1:8769/)，选择 **New project**。Windows 用户也可运行 `.\start-prototype.ps1`。服务绑定本机回环地址。浏览界面只需 Node.js；自动抽取和推理需要在 **OpenAI settings** 配置可访问的模型，机器证明还需要本地检查环境。

## 从论文到证明

1. **Documents**　上传 PDF、Markdown、TXT、DOCX，或手动输入。审核模型、假设和分析方法，选择本次要证明的目标，点击 **Confirm MSA**。
2. **Derivation**　从确认的输入启动双向推导。选择一个反向子目标（B），查看支持它的正向引理（F）、对齐关系和缺口。
3. **Proof**　点击 **Check formal model** 检查模型。模型通过后，可从依赖图选择节点逐项检查，或点击 **Run full proof automatically** 运行整条路线。
4. **Expert audit**　选择审查维度和轮数，检查模型忠实性、调度语义及目标覆盖。**Run details** 保留各次尝试的诊断、证明义务和检查输出。

## 如何读 Proof 页

状态区显示当前尝试所处的阶段、最新一轮检查过的义务数，以及 **Final theorem** 的结果。

| 状态 | 含义及下一步 |
| --- | --- |
| **Proof in progress** | 尝试正在运行。页面自动更新当前阶段和计数。等待生成形式模型时，计数可以保持为零。 |
| **Formal model checked** | 模型已通过类型检查。可以选择引理或启动完整证明。 |
| **Selected checks complete** | 本次所选节点已检查完毕。可从依赖图继续检查最终定理。 |
| **Proof stopped / Proof interrupted / Proof needs attention** | 本次尝试已停止或有未解决项。查看 **Next step** 和本次诊断，再决定修订输入或重试。 |
| **Proof verified** | 最终命题已有 Rocq 编译和内核检查通过的记录。可打开 **Run details** 查看证据。 |

进度条按已返回检查结果的义务数计数，其中可能包含仍开放的义务。判断定理是否完成，请看 **Final theorem · Verified by Rocq**。

## 检查环境和本地数据

- **Rocq**　Windows 通过 WSL 调用 Python、opam 和 Rocq。检查前请核对工具链配置中的发行版、opam 根目录、switch 和软件包版本。Prosa 路线还需要与目标语义匹配的库和适配。见 [工具链配置](configs/toolchain.json)。
- **后端工作台**　需要单独使用 Python、PostgreSQL、Poppler 和 WSL 后端时，在 PowerShell 执行 `.\start-workbench.ps1`，打开 [后端 MSA 工作台](http://127.0.0.1:8765/msa)。运行时读取的数学合同见 [docs](docs/README.md)。
- **数据位置**　浏览器保存项目列表及工作区状态，本机 `artifacts/` 保存运行产物。OpenAI 连接设置保存在用户目录中，Windows 可选择加密保存密钥。使用外部模型时，相应输入会发送给所配置的服务。
- **仓库内容**　仓库分发平台源码、配置和运行所需文档。本地研究项目、上传论文、运行日志、证明记录及凭据请保存在本机。
