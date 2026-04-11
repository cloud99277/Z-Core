# 任务规格：Z-Core V2 补完 Phase B — RAG 引擎集成

> **所属项目：** Z-Core (`~/projects/Z-Core/`)  
> **执行者：** Codex Agent  
> **上下文：** Z-Core V2 补完计划 (V2-Complete-Upgrade-Strategy) Phase A 已完成，现在由你执行 Phase B。  
> **目标：** 将原 KitClaw V1 的 RAG 代码迁移至 Z-Core 核心框架，并通过可选依赖（`zcore[rag]`）对外暴露，保持核心包的零依赖原则。

## 任务背景

Z-Core 是零依赖的运行时引擎包（`pip install zcore`），但我们需要完整的 L3（外部知识库）能力。这部分强依赖 `lancedb`、`sentence-transformers` 和 `pandas`。
因此，RAG 功能必须以**可选模块**的形式引入，在用户未安装 `zcore[rag]` 依赖时，系统也必须能够正常启动，并在调用时优雅降级（输出明确错误或自动跳过 L3 步骤）。

### 原始资产位置
- `~/projects/kitclaw/rag-engine/knowledge_index.py`
- `~/projects/kitclaw/rag-engine/knowledge_search.py`
- `~/projects/kitclaw/rag-engine/md_chunker.py`
- `~/projects/kitclaw/rag-engine/requirements.txt`

---

## 阶段任务清单

请务必按顺序执行以下任务，且每一步需验证通过后再进入下一步。

### B1 & B2: 代码迁移与外壳包装

1. 创建目录 `Z-Core/zcore/rag/`。
2. 将前述的 3 个 `*.py` 文件复制到该目录下，可重命名为内部模块。
3. 创建 `Z-Core/zcore/rag/__init__.py`，负责对外暴露接口：
   - 内部封装一个懒加载检查机制，在导入或实例化 RAG 功能时检测能否 `import lancedb`。
   - 检测失败时，应抛出含有明确提示的异常（例如 `"RAG dependencies missing. Run 'pip install zcore[rag]' to enable L3 capabilities."`），而绝不允许因为 `import zcore` 就直接崩溃挂掉。

### B3: 配置 `pyproject.toml` 可选依赖

更新 `Z-Core/pyproject.toml`，在 `[project.optional-dependencies]` 中加入：
```toml
[project.optional-dependencies]
dev = ["build>=1.2.0", "pytest>=9.0.0", "twine>=6.0.0"]
test = ["pytest>=9.0.0"]
rag = [
    "lancedb>=0.20.0",
    "sentence-transformers>=3.0.0",
    "python-frontmatter>=1.0.0",
    "pandas>=2.0.0"
]
```

### B7: 配置 `config.toml` 与 RuntimePaths 扩展

1. 核实 `zcore.paths` 与 `zcore.runtime.RuntimePaths` 是否已有关于 `ZCORE_KNOWLEDGE_DB` 的路径定义（当前已默认为 `~/.lancedb/knowledge`，无需大改，只需复用）。
2. 更新默认启动配置（`zcore/config.py` 和对应模板），可以补充一个空骨架供之后配置覆盖。

### B4 & B5: 新增 `knowledge` CLI 子命令

在 `zcore/cli/main.py` 中增加 `knowledge` 二级命令：

```bash
# 搜索知识库
zcore knowledge search --query "<问题>" [--limit 10] [--json]

# 手动触发知识库重载/索引更新
zcore knowledge index [--path /optional/path/to/sync/dir]
```
- 如果捕获到 `ImportError`（依赖缺失），命令行错误信息应友善引导安装。

### B6: MemoryEngine 兼容搜索 L3

修改 `zcore/engines/memory.py` 中的 `search` 方法或新增 `search_all` 接口：
- 当用户执行 `zcore memory search` 时，优先进行现存的 L2（Topic 文件）匹配。
- 探测 `zcore.rag` 模块是否可用：
  - 如果可用，一并调用 RAG 引擎的 search 获取 L3 搜索结果，并且和 L2 的结果合并或分别展示。
  - 如果不可用，优雅地吞掉 L3 的部分，仅返回 L2 结果（可在元数据/Log 里标注 L3 未加载）。

### B8 & B9: 质量收口

1. **写单元测试**：
   新建 `tests/test_rag_integration.py`。
   利用 `@unittest.skipIf` 这类装饰器，若运行时没有 `lancedb` 环境，则跳过测试而不报错。验证依赖不存在时的优雅降级行为。
2. **写文档**：
   新建并编写 `docs/rag-setup.md` 指南，详细说明如何安装以及常用命令；同时更新 `README.md`，添加对于 RAG 扩展包的安装说明。

---

## 执行规约与提示

- 工具链中必须能通过 `python3 -m unittest discover tests -q`
- CLI 测试可借助 `wsl bash -c "python3 -m zcore knowledge search --help"` 和 `... --json` 查看格式情况。
- 所有 RAG 代码内的路径或写死的数据获取逻辑，必须全部重构并对接 Z-Core 的 `RuntimePaths` 以及 `Config` 机制，这可能是迁移中最核心的代码修改点。
- **请勿一次性修改所有文件**。每做完 B1-B3、B4-B6 时可进行阶段性的小规模测试确认。执行结束后，记得自动使用 `log-execution.py` 记录 project-manager/full-cycle-builder 相关的执行足迹。
