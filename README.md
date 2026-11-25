# AutoVISA

AutoVISA 是一个实时系统分析与形式证明工作台。可以录入模型、分析方法和目标，核对来源，查看双向推导、开放义务和 Rocq 检查结果。

## 浏览界面原型

安装 Node.js 后，在项目根目录运行 `node tools/serve-prototype.cjs`，打开 <http://127.0.0.1:8769/>。原型中的草稿和运行比较保存在当前浏览器。

## 启动后端工作台

后端使用 Windows、WSL Ubuntu、Python 3、PostgreSQL 和 Poppler；形式检查还需要匹配的 Rocq、opam 环境和所选路线的证明库。工具链参数见 [configs/toolchain.json](configs/toolchain.json)。

在 PowerShell 中运行 `.\start-workbench.ps1`，打开 <http://127.0.0.1:8765/msa>。从空白项目手动录入、导入自己的 MSA JSON，或选择本地数字版 PDF。数学能力目前覆盖部分算术、Prosa 向上取整适配及 case_11 的单处理器 DM 分析；完整调度主定理仍有开放义务。

数学合同及其用途见 [运行所需文档](docs/README.md)。


## 论文框架在工作台中的入口

普通项目从已确认的 MSA 进入 Derivation。选中 B 子目标即可查看支持它的 F 引理与推导依据。

在 **Proof** 点击 **Start proof**，平台按依赖顺序尝试证明局部引理和最终命题。最终命题通过 Rocq 编译和内核检查后，页面显示 **Proof verified**。遇到阻塞时，**View blocker** 打开该次尝试的记录。

在 **Expert audit** 选择 1 到 3 轮，点击 **Start audit**。审计使用选定的模型检查模型忠实性、调度语义和目标覆盖，支持审查部分证明。Resources 管理可复制的 Skill，两个页面的 settings 选择本次使用的修订。**Runs → Proof & audit** 保留每次尝试的 Skill、模型、检查输出、开放义务和审计发现。
