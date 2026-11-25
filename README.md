# AutoVISA

AutoVISA 是面向实时系统研究者的本地证明工作台。给它一篇调度论文，或直接输入系统模型、分析方法和目标，就可以沿着一项调度保证，追踪它依赖哪些引理、哪些条件尚待补足，以及最终命题是否通过 Rocq 检查。

## 快速开始

安装 Git 和 Node.js，然后在终端运行：

```sh
git clone --branch dev https://github.com/RTS-SYSU/AutoVISA.git
cd AutoVISA
node tools/serve-prototype.cjs
```

打开 [本地工作台](http://127.0.0.1:8769/)，保持终端运行。如果 8769 已被占用，可加 `--port 8773` 指定备用端口。[打开备用端口](http://127.0.0.1:8773/)

## 导入自己的论文

1. 首页点击 **Choose paper PDF**，选择有可复制文字的 PDF。工作台会以文件名创建项目。也可通过 **Create project manually** 新建项目，在 **Documents** 导入 Markdown、TXT、DOCX 或手动录入。
2. 点击 **Extract draft** 生成带出处的草稿。使用自动抽取与推导时，先在 **OpenAI settings** 配置 API Key，或在启动前设置 `OPENAI_API_KEY`。核对模型、假设、分析方法和验证目标，然后点击 **Confirm MSA**。
3. 在 **Derivation** 启动推导，查看支持所选目标的引理和仍需满足的条件。
4. 在 **Proof** 中用 **Formal model** 检查定义。通过后，从 **Lemmas & subgoals** 选择节点，或从 **More actions** 启动完整证明。这条路线需要下文的 Rocq 工具链。
5. **Final theorem · Verified by Rocq** 表示当前形式命题通过了编译和内核检查。若显示 **Needs clarification**，打开 **Review model issues** 查看待处理的定义。**Run details** 提供检查记录，**Expert audit** 可进一步审查模型忠实性、调度语义和目标覆盖。

## 用公开论文复跑验证

样例使用作者公开的 POET 证书，无需 OpenAI API Key。AutoVISA 通过文件 SHA-256 匹配已核对的出版版本。

1. 准备 **Rocq 9.0 和 Prosa 0.6 refinements**，然后启动工作台。[安装工具链与命令行复跑](proofs/papers/poet-2022/README.md)
2. 保存出版社提供的 PDF，在首页点击 **Choose paper PDF** 导入。[ECRTS 2022 原版论文 PDF](https://drops.dagstuhl.de/storage/00lipics/lipics-vol231-ecrts2022/LIPIcs.ECRTS.2022.19/LIPIcs.ECRTS.2022.19.pdf)
3. 等待报告显示 **Published claim verified**。在 **Exact Rocq theorem** 和 **Checker log** 查看命题与内核检查记录。报告定位到第 11 页 Listing 2，验证任务 2 在论文所列假设下的 **60 ms 响应时间上界**与 **100 ms 截止时间**。

如果导入后进入普通草稿流程，核对是否选中了出版社原版 PDF。若显示 **Certificate check failed**，展开 **Checker log** 定位问题，从报告中重跑检查。当前自动证书复核覆盖上述一条声明，其它论文使用普通导入流程。

## 内置 Skills

在工作台的 **Resources** 中可阅读内置 Skill。下表链接到平台实际加载的指令；已有运行保留当时选用的版本。

| 阶段 | 仓库中的内容 |
| --- | --- |
| 提取论文贡献 | [Extract paper contributions](skills/extract-paper-contributions/SKILL.md) |
| 选择证明目标 | [Select proof targets](skills/select-proof-targets/SKILL.md) |
| 正向推导、反向推导、对齐 | [推理指令和版本](skills/builtin-reasoning.json)（`forward`、`backward`、`alignment`） |
| 证明构造与专家审计 | [证明与审计指令](skills/builtin-reasoning.json)（`proof`、`fidelity`、`semantics`、`coverage`） |

## 运行环境

| 使用目的 | 依赖与入口 |
| --- | --- |
| 本地网页 | Node.js；Windows 也可运行 `.\start-prototype.ps1` |
| 普通论文的 Rocq 检查 | Python、opam、匹配版本的 Rocq；Windows 通过 WSL 调用。先核对发行版、opam 根目录和 switch。[工具链配置](configs/toolchain.json) |
| POET 样例证书复核 | Rocq 9.0 与 Prosa 0.6 refinements，支持 Windows 原生 Rocq。[安装说明](proofs/papers/poet-2022/README.md) |
| 后端 MSA 工作台 | Windows、WSL、Python、PostgreSQL 和 Poppler。运行 `.\start-workbench.ps1` 后打开 [MSA 工作台](http://127.0.0.1:8765/msa)。[运行时合同](docs/README.md) |

项目列表和工作区状态存于浏览器，本机 `artifacts/` 保存运行证据和自定义 Skill。调用外部模型时，相应输入会发给配置的服务。仓库发布平台源码、内置 Skill 和运行配置，本地论文、凭据与研究记录保存在各自的工作环境。
