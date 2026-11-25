# AutoVISA

AutoVISA 是面向实时系统研究者的本地证明工作台。给它一篇调度论文，或直接输入系统模型、分析方法和目标，就可以沿着一项调度保证，追踪它依赖哪些引理、哪些条件尚待补足，以及最终命题是否通过 Rocq 检查。

## 快速开始

安装 Node.js 和 Git，然后启动 `dev` 版工作台：

```sh
git clone --branch dev https://github.com/RTS-SYSU/AutoVISA.git
cd AutoVISA
node tools/serve-prototype.cjs
```

打开 [本地工作台](http://127.0.0.1:8769/)，点击 **New project**。仅浏览界面需要 Node.js；自动抽取与推导需要在 **OpenAI settings** 配置模型，实际证明还需安装下方的 Rocq 工具链。

## 第一次运行

1. 在 **Documents** 上传 PDF、Markdown、TXT 或 DOCX，也可以手动录入。核对带出处的草稿，选定一个目标并点击 **Confirm MSA**。
2. 在 **Derivation** 启动推导。选择一个反向子目标，查看哪些正向引理支持它，以及还缺哪些条件。
3. 在 **Proof** 选择 **Formal model** 检查定义。通过后，从 **Lemmas & subgoals** 选择要检查的节点，或在 **More actions** 中启动完整证明。
4. 查看最终结果。**Final theorem · Verified by Rocq** 表示最终命题通过了编译和内核检查。若阶段显示 **Needs clarification**，展开 **Review model issues** 查看需要处理的定义。**Run details** 提供该次尝试的原始记录。

**Expert audit** 可进一步审查模型忠实性、调度语义与目标覆盖。运行审计时可选择维度和轮数。

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
| Rocq 检查 | Python、opam、匹配版本的 Rocq；Windows 通过 WSL 调用。先核对发行版、opam 根目录和 switch。[工具链配置](configs/toolchain.json) |
| 后端 MSA 工作台 | Windows、WSL、Python、PostgreSQL 和 Poppler。运行 `.\start-workbench.ps1` 后打开 [MSA 工作台](http://127.0.0.1:8765/msa)。[运行时合同](docs/README.md) |

项目列表和工作区状态存于浏览器，本机 `artifacts/` 保存运行证据和自定义 Skill。调用外部模型时，相应输入会发给配置的服务。仓库发布平台源码、内置 Skill 和运行配置，本地论文、凭据与研究记录保存在各自的工作环境。
