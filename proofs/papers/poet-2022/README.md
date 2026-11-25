# POET 论文证书复核

- Marco Maida、Sergey Bozhko、Björn B. Brandenburg，*Foundational Response-Time Analysis as Explainable Evidence of Timeliness*，ECRTS 2022。[论文 DOI](https://doi.org/10.4230/LIPIcs.ECRTS.2022.19)
- 出版社 PDF 的 SHA-256 为 `1f44ec4906fb5ffa8ccd9bfd5c24adf7bd140a83b84cd2587263d1ee28d9fb31`。
- 验收目标来自 PDF 第 11 页 Listing 2 第 18–29 和 143–173 行，模型参数也见 Listing 1。任务 1 的 WCET 为 50，优先级为 2，到达曲线前缀为 `(220, [(1,1), (105,2)])`。任务 2 的 WCET 为 10，周期为 30，优先级为 1，截止时间为 100。模型是单个理想处理器上的完全可抢占固定优先级调度。

## 证书来源与检查范围

`task_set.v` 和 `tsk02.v` 使用 [POET 的固定修订](https://github.com/PROSA-Project/POET/tree/bb922e068f1d57731188fd5ba329d6693bb52fcd) 从作者提供的 `examples/paper.yaml` 生成。生成选项为 `-n -o <output> examples/paper.yaml`，生成后只规范了空白。这两个文件所用的许可证随附于 [LICENSE](LICENSE)。

`PaperClaim.v` 用独立写出的类型检查证书定理。它固定任务 2、60 ms 上界、100 ms 截止时间，以及任意到达序列所需的五个前提。AutoVISA 检查两条导出声明的 `Print Assumptions` 输出，然后以 `rocqchk` 复核定理和传递依赖。这里使用公开证书重放，只覆盖 Listing 2 的任务 2 声明。

## 复跑

已有 Rocq 9.0 和 Prosa refinements 0.6 的环境可以直接运行：

```text
node tools/paper-verification.cjs path/to/LIPIcs.ECRTS.2022.19.pdf
node tools/serve-prototype.cjs
```

通过 opam 安装的环境，使用 `opam install rocq-prosa-refinements.0.6`，并在同一 switch 运行 Node。Windows 可以使用 [Rocq Platform 2025.08.3](https://github.com/rocq-prover/platform/releases/tag/2025.08.3) 的 Rocq 9.0.1、MathComp、CoqEAL 和 zify，加上 [Prosa v0.6](https://github.com/PROSA-Project/Prosa/tree/v0.6)。在 Windows 克隆这个版本时，Git 可能会拒绝与此证书无关的 `aux.v` 路径。可使用仅拉取文件、保留依赖的 Linux checkout，或用 Prosa 发布版本的本地构建。

Windows 如果已将平台放入 `%LOCALAPPDATA%\AutoVISA\Rocq-Platform-9.0`，并将编译过的 Prosa 仓库放入 `%LOCALAPPDATA%\AutoVISA\Prosa-0.6`，工作台会自动找到。其它位置可分别设置 `AUTOVISA_PAPER_ROCQ_BIN`（包含 `rocq` 和 `rocqchk`）和 `AUTOVISA_PAPER_PROSA_ROOT`（含已编译模块的 Prosa 源码根目录）。如果 Prosa 还未编译，可以运行 `python tools/prepare-paper-prosa.py <Prosa 根目录> <rocq 可执行文件>`。使用解包的 Windows Platform 时，先按该布局设置 `ROCQLIB` 为平台内的 `lib/coq`，`OCAMLPATH` 为 `lib`。
