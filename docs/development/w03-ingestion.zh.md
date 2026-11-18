# W03-a PDF 导入与来源定位

这一阶段实现数字 PDF 的原文件保存、版面文字抽取、来源引用与重开。抽取使用本机 Poppler，存储复用 W02 的 PostgreSQL 连接和内容寻址目录。后续模型条件、算法和候选目标抽取可以引用本阶段提供的稳定片段。

## 数据合同

| 对象 | 主要内容 |
|---|---|
| `Extraction` | 原 PDF 的 SHA-256、字节数、解析器版本与摘要、所有页面、诊断和原始抽取文件。提取身份是整份清单的内容摘要。 |
| `Page` | 从 1 开始的物理页码、可见页面宽高、旋转角度、原始提取文字和词记录。 |
| `Word` | 稳定词 ID、原始文字、页内起止偏移、矩形及 flow/block/line 序号。 |
| `SourceAnchor` | 抽取 ID、PDF 摘要、物理页码、文本范围与精确引文。 |
| `LocatedText` | 经核对的引用及其词级矩形，供页面高亮或来源裁剪使用。 |
| `Issue` | 待核对原因、说明及可选的物理页码。 |

坐标原点是裁剪并旋转后的页面左上角，单位为 PDF point，每点等于 1/72 英寸。文本偏移按 Python Unicode 码点计数，采用左闭右开范围。未来浏览器的 UTF-16 文本选区需要转换为码点偏移。部分词的文本选区使用整个词的矩形。输出文字保持解析器返回的字符，不自动把公式替换为数学表达式。

Poppler 的 XHTML 页面宽高保持旋转前尺寸，词坐标已经旋转。本模块读取逐页旋转数据后调整宽高，验收覆盖 0、90、180、270 度及非零 CropBox 起点。

## 代码入口

- [数据结构](../../src/platform_core/paper_ingestion/models.py) 定义记录字段和引用身份。
- [导入接口](../../src/platform_core/paper_ingestion/service.py) 提供 `import_pdf`、`open`、`locate`、`resolve` 和 `render`。
- [PDF 处理](../../src/platform_core/paper_ingestion/pdf.py) 封装实际进程调用、版面解析、限制和页面渲染。
- [存储表](../../src/platform_core/paper_ingestion/schema.sql) 保存原文件及抽取清单索引，引用 W02 的只追加历史约束。
- [验收](../../tests/acceptance/w03_import_cases.py) 从相同接口验证真实论文、并发导入、错误引用和旋转页面。

全部函数、参数、记录字段与实例属性附英文 Javadoc 风格说明。局部变量附近说明单位、用途或事务顺序。

## 开发者命令

在项目根目录运行：

```powershell
# Import case_11 and save the extraction and the first-page image.
.\import-paper.ps1

# Locate the algorithm caption on physical page four.
.\import-paper.ps1 -Page 4 -Find 'Schedulability Algorithm'

# Import another local digital PDF.
.\import-paper.ps1 -Pdf 'C:\papers\example.pdf'

# Reopen an extraction ID returned by an earlier command.
.\import-paper.ps1 -Extraction '<extraction_id>' -Page 4

# Run isolated acceptance.
.\import-paper.ps1 -Check
```

普通导入返回抽取 ID、页数、诊断和输出目录。目录中的 `extraction.json` 可供开发者查看完整结果，`preview.png` 显示页面或选中文字区域，定位操作另存 `source-reference.json`。所有原始 PDF 与诊断文件按清单内的摘要保存于 `artifacts/w03/objects/`，可以从 `source_sha256` 找回原始字节。

CLI 在私有 PostgreSQL 实例恢复 `artifacts/w03/catalog.json` 指向的备份，操作结束后保存新备份。跨进程锁覆盖恢复到新备份发布，防止并发 CLI 丢失更新。模块本身可接入持续运行的 PostgreSQL，并使用数据库唯一键处理并发重复导入。相同文件改名后沿用相同身份。解析器代码或版本变化会产生新抽取身份。

`-Check` 使用独立测试目录，并在第二个数据库实例恢复引用。它会生成真实页面、来源裁剪和几何样本，供人工核对。

## 运行条件与当前范围

当前使用 WSL Ubuntu 22.04、系统 Python 3.10、W02 已准备的 PostgreSQL/psycopg2 和项目专用 Poppler。新机器先准备 W02 环境，再在 WSL 的项目目录执行 `bash tools/prepare_w03.sh`。该脚本下载 Ubuntu 官方包到项目目录。日常导入和检查仅访问本机数据。

默认限制为 PDF 20 MiB、100 页、每个解析命令 30 秒、抽取 XML 32 MiB。页面预览固定为 144 DPI，上限为 1600 万像素。超过限制返回具体诊断。全部没有文本层的 PDF 返回 `no_text_layer`；有文字和空白页混合的文档保留所有页面，并标注无文字页。

case_11 的公式和多栏文字需要按页图复核。模块保留原始布局、解析诊断，并登记 `semantic_review_required`。原文材料的 `material_role` 为 `unclassified`，后续需核对模型、分析、目标和作者证明的材料角色，再生成推理输入。模型与目标自动识别、语义 IR 和 Web 工作台在 W03 的后续步骤实现。
