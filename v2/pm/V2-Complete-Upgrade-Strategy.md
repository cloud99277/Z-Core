# Z-Core V2 完整升级战略

> **决策日期：** 2026-04-11  
> **状态：** In-Progress（Phase A 已完成，Phase B/C 待执行）  
> **影响范围：** 产品定位、架构、用户体验、KitClaw 关系

---

## 执行摘要

**核心决策：** Z-Core 应该是 KitClaw 的**完整升级版**（V2），而不是从 KitClaw 提取的"运行时中间件子集"。

**当前问题：** Z-Core 的定位混乱 — README 说"extracted from KitClaw"并且"can be used independently or alongside KitClaw"，这导致：
1. 用户困惑：我该用 KitClaw 还是 Z-Core？
2. 功能分裂：17 个核心 skills 和 RAG 引擎还在 KitClaw，Z-Core 只有运行时框架
3. 维护负担：两个仓库都需要维护，但定位不清

**解决方案：** 将 Z-Core 重新定位为 KitClaw V2，提供完整功能 + 统一 CLI + 更好架构。

---

## 第一部分：问题诊断

### 1.1 原始设想 vs 当前状态

**原始设想（开发者意图）：**
```
KitClaw V1 (旧版)
    ↓ 完整升级
Z-Core V2 (增强版)
    ├── 包含 KitClaw 所有能力
    ├── 新增 10 个引擎
    ├── 统一 zcore CLI
    └── 零依赖架构
```

**当前实际状态（从 README 看）：**
```
KitClaw (原始项目)
    ↓ 提取部分功能
Z-Core (运行时中间件)
    ├── 10 个引擎 ✓
    ├── 统一 CLI ✓
    ├── 零依赖 ✓
    └── 但缺少：
        ├── 17 个核心 skills ✗
        └── RAG 引擎 ✗
```

### 1.2 当前架构的问题

**问题 1：功能分裂**
- Z-Core 有 `SkillRouter` 引擎（框架），但没有具体 skills
- Z-Core 有 `MemoryEngine`（L2 whiteboard），但没有 RAG（L3 知识库）
- 用户需要同时安装 KitClaw 和 Z-Core 才能获得完整功能

**问题 2：定位混乱**
- README 说"can be used independently or alongside KitClaw"
- 这暗示两者是平行关系，不是升级关系
- 用户会问：我到底该用哪个？两者有什么区别？

**问题 3：维护负担**
- KitClaw 和 Z-Core 都需要维护
- 功能重叠（memory, skills, governance）
- 文档需要同步更新

### 1.3 关键证据

**Z-Core README 当前描述：**
> Z-Core was **extracted from** the KitClaw multi-agent infrastructure project as a **standalone runtime**. It can be used **independently or alongside KitClaw**.

**这个描述的问题：**
- "extracted from" → 暗示是子集，不是升级
- "standalone runtime" → 暗示只是基础设施层
- "alongside KitClaw" → 暗示需要配合使用

**开发者的真实意图：**
- Z-Core 应该**完全替代** KitClaw
- 用户只需要安装 Z-Core
- KitClaw 成为历史版本（V1）

---

## 第二部分：解决方案

### 2.1 目标架构

```
┌─────────────────────────────────────────────┐
│           Z-Core V2 (完整系统)               │
├─────────────────────────────────────────────┤
│  核心运行时（零依赖）                        │
│  ├── 10 个引擎                              │
│  ├── 统一 zcore CLI                         │
│  └── 基础 skills 管理                       │
├─────────────────────────────────────────────┤
│  RAG 引擎（可选安装，强烈推荐）              │
│  └── L3 知识库检索                          │
├─────────────────────────────────────────────┤
│  17 个核心 Skills（分步安装）                │
│  ├── 必要内置：memory-manager, l2-capture   │
│  └── 可选安装：其他 15 个                   │
└─────────────────────────────────────────────┘

KitClaw V1 (frozen, archived)
└── 指向 Z-Core V2
```

### 2.2 用户安装体验

```bash
# 1. 安装核心运行时（零依赖）
pip install zcore
zcore init

# 2. 安装 RAG 引擎（强烈推荐，有依赖）
zcore install rag
# 或
pip install zcore[rag]

# 3. 安装 skills（用户选择）
zcore skill install l2-capture          # 单个安装
zcore skill install --core               # 安装全部 17 个核心 skills
zcore skill install --interactive        # 交互式选择

# 4. 验证安装
zcore doctor
zcore status
```

### 2.3 仓库结构

```
Z-Core/
├── zcore/                      # Python 包（pip install）
│   ├── __init__.py
│   ├── cli/                    # CLI 入口
│   ├── engines/                # 10 个引擎
│   │   ├── memory.py
│   │   ├── session.py
│   │   ├── router.py
│   │   └── ...
│   ├── rag/                    # RAG 引擎（可选依赖）
│   │   ├── __init__.py
│   │   ├── indexer.py
│   │   └── retriever.py
│   └── builtin_skills/         # 内置 skills（打包到 pip）
│       ├── memory_manager/
│       ├── l2_capture/
│       └── runtime_doctor/
├── skills/                     # Skills 源码（不打包到 pip）
│   ├── core/                   # 17 个核心 skills
│   │   ├── l2-capture/
│   │   ├── knowledge-search/
│   │   ├── conversation-distiller/
│   │   └── ...（14 个）
│   └── extended/               # 扩展 skills（未来）
├── docs/
│   ├── migration-from-kitclaw.md
│   └── ...
├── pyproject.toml
└── README.md
```

### 2.4 依赖管理

```toml
# pyproject.toml
[project]
name = "zcore"
version = "0.2.0"
dependencies = []  # 核心零依赖

[project.optional-dependencies]
rag = [
    "lancedb>=0.5.0",
    "sentence-transformers>=2.0.0",
    "numpy>=1.24.0"
]
dev = ["pytest>=9.0.0", "build>=1.2.0"]
```

---

## 第三部分：实施计划

### Phase 1：文档更新（最快见效）

**优先级：** P0  
**工作量：** 2-4 小时  
**影响：** 立即澄清定位

**任务清单：**
1. ✅ 更新 Z-Core README.md
   - 改为："Z-Core V2 — KitClaw 的完整升级版"
   - 删除："extracted from" 和 "alongside KitClaw"
   - 强调：完全替代 KitClaw V1

2. ✅ 更新 KitClaw README.md
   - 添加顶部警告：⚠️ 此版本不再维护
   - 指向 Z-Core V2
   - 保留 V1 文档供参考

3. ✅ 创建迁移指南
   - 文件：`docs/migration-from-kitclaw.md`
   - 内容：命令对照表、数据兼容性、常见问题

4. ✅ 更新 v2/design/product-strategy.md
   - 反映新的定位决策
   - 更新架构图

### Phase 2：Skills 管理（核心功能）

**优先级：** P0  
**工作量：** 1-2 天  
**依赖：** Phase 1 完成

**任务清单：**
1. ✅ 复制 17 个核心 skills 到 Z-Core
   ```bash
   cp -r ~/projects/kitclaw/core-skills/* ~/projects/Z-Core/skills/core/
   ```

2. ✅ 实现 `zcore skill install` 命令
   - 从 Z-Core/skills/core/ 复制到 ~/.ai-skills/
   - 支持单个安装、批量安装、交互式选择
   - 验证 SKILL.md frontmatter

3. ✅ 实现 `zcore skill list` 命令
   - `--available`：列出可安装的 skills
   - `--installed`：列出已安装的 skills
   - `--json`：结构化输出

4. ✅ 实现 `zcore skill uninstall` 命令
   - 从 ~/.ai-skills/ 删除
   - 安全检查（防止误删用户自定义 skills）

5. ✅ 内置 3 个核心 skills
   - memory-manager
   - l2-capture
   - runtime-doctor
   - 打包到 zcore Python 包，无需安装

### Phase 3：RAG 引擎集成（增强功能）

**优先级：** P1  
**工作量：** 2-3 天  
**依赖：** Phase 2 完成

**任务清单：**
1. ✅ 迁移 RAG 引擎代码
   ```bash
   cp -r ~/projects/kitclaw/rag-engine/* ~/projects/Z-Core/zcore/rag/
   ```

2. ✅ 添加可选依赖
   - 更新 pyproject.toml
   - 测试 `pip install zcore[rag]`

3. ✅ 实现 `zcore install rag` 命令
   - 检查依赖
   - 初始化 RAG 数据库
   - 配置 ~/.zcore/config.toml

4. ✅ 集成到 MemoryEngine
   - 统一接口：`zcore memory search` 同时搜索 L2 + L3
   - 或独立命令：`zcore knowledge search`

5. ✅ 更新文档
   - RAG 安装指南
   - 使用示例
   - 性能优化建议

### Phase 4：内置 Skills（用户体验优化）

**优先级：** P2  
**工作量：** 1-2 天  
**依赖：** Phase 2 完成

**任务清单：**
1. ✅ 将 3 个核心 skills 集成到 zcore 包
   - 作为 Python 模块
   - 提供 CLI 接口和 Python API

2. ✅ 统一命令接口
   ```bash
   # 旧方式（仍然兼容）
   python3 ~/.ai-skills/memory-manager/scripts/search.py --query "test"
   
   # 新方式（推荐）
   zcore memory search --query "test"
   zcore l2 capture --text "decision"
   zcore doctor
   ```

3. ✅ 向后兼容
   - SkillRouter 继续支持 ~/.ai-skills/ 中的 skills
   - 用户现有的 102 个 skills 不受影响

---

## 第四部分：迁移指南要点

### 4.1 命令对照表

| KitClaw V1 | Z-Core V2 | 说明 |
|------------|-----------|------|
| `python3 ~/.ai-skills/memory-manager/scripts/search.py` | `zcore memory search` | 内置命令 |
| `python3 ~/.ai-skills/l2-capture/scripts/l2_capture.py` | `zcore l2 capture` | 内置命令 |
| `python3 ~/.ai-skills/knowledge-search/scripts/search.py` | `zcore knowledge search` | 需要安装 RAG |
| `python3 ~/.ai-skills/runtime-doctor/scripts/doctor.py` | `zcore doctor` | 内置命令 |
| 其他 skills | `zcore run <skill-name>` | 通过 SkillRouter |

### 4.2 数据兼容性

| 数据 | 兼容性 | 说明 |
|------|--------|------|
| `~/.ai-memory/` | ✅ 完全兼容 | L2 whiteboard 格式不变 |
| `~/.ai-skills/` | ✅ 完全兼容 | Skills 目录结构不变 |
| `~/.zcore/` | ✅ 完全兼容 | 配置文件格式不变 |
| `~/.lancedb/knowledge` | ✅ 完全兼容 | RAG 数据库格式不变 |

### 4.3 升级步骤

```bash
# 1. 备份现有数据（可选）
cp -r ~/.ai-memory ~/.ai-memory.bak
cp -r ~/.zcore ~/.zcore.bak

# 2. 安装 Z-Core V2
pip install zcore

# 3. 验证安装
zcore --version
zcore status

# 4. 安装 RAG（如果需要）
pip install zcore[rag]

# 5. 安装核心 skills（如果需要）
zcore skill install --core

# 6. 测试
zcore doctor
zcore memory search --query "test"
```

---

## 第五部分：风险与缓解

### 5.1 技术风险

**风险 1：RAG 依赖冲突**
- **描述：** lancedb 等依赖可能与用户环境冲突
- **缓解：** 使用可选依赖，用户可以选择不安装
- **备选：** 提供 Docker 镜像

**风险 2：Skills 迁移兼容性**
- **描述：** 17 个 skills 可能依赖 KitClaw 特定路径
- **缓解：** 
  - 保持 ~/.ai-skills/ 目录结构不变
  - 测试每个 skill 的兼容性
  - 提供兼容层

**风险 3：零依赖承诺**
- **描述：** 核心包必须保持零依赖
- **缓解：** 
  - RAG 作为可选依赖
  - 内置 skills 只使用标准库

### 5.2 产品风险

**风险 1：用户困惑**
- **描述：** 现有 KitClaw 用户可能不知道要升级
- **缓解：** 
  - 在 KitClaw README 顶部添加醒目警告
  - 提供详细迁移指南
  - 在社区/文档中宣传

**风险 2：功能回退**
- **描述：** Z-Core V2 可能缺少 KitClaw V1 的某些功能
- **缓解：** 
  - 完整审计 KitClaw V1 功能
  - 确保 100% 功能覆盖
  - 保留 KitClaw V1 仓库供参考

### 5.3 维护风险

**风险 1：双仓库维护负担**
- **描述：** 过渡期需要同时维护两个仓库
- **缓解：** 
  - KitClaw 标记为 archived，只读
  - 所有新功能只在 Z-Core 开发

---

## 第六部分：成功指标

### 6.1 技术指标

- ✅ Z-Core 包含 KitClaw 100% 功能
- ✅ 核心包保持零依赖
- ✅ 所有测试通过（50+ 单元测试）
- ✅ 文档完整（安装、使用、迁移）

### 6.2 用户体验指标

- ✅ 用户可以通过 `pip install zcore` 获得核心功能
- ✅ 用户可以通过 `zcore skill install --core` 获得完整功能
- ✅ 命令行体验统一（所有功能通过 `zcore` 命令）
- ✅ 迁移指南清晰（KitClaw V1 → Z-Core V2）

### 6.3 项目指标

- ✅ KitClaw 仓库标记为 archived
- ✅ Z-Core 成为唯一活跃仓库
- ✅ 文档和代码定位一致
- ✅ 社区理解新的定位

---

## 第七部分：决策记录

### 决策 1：Z-Core 是完整升级版，不是子集

**日期：** 2026-04-11  
**决策者：** 产品负责人  
**理由：** 
- 原始设想是完整升级
- 当前"子集"定位导致混乱
- 用户需要统一的解决方案

**影响：**
- Z-Core 需要包含所有 KitClaw 功能
- KitClaw 成为历史版本
- 文档和代码需要大幅更新

### 决策 2：保持零依赖核心 + 可选增强

**日期：** 2026-04-11  
**决策者：** 架构负责人  
**理由：**
- 零依赖是核心优势
- RAG 需要外部依赖
- 用户应该可以选择

**影响：**
- 核心包保持零依赖
- RAG 作为可选依赖 `pip install zcore[rag]`
- Skills 通过 `zcore skill install` 按需安装

### 决策 3：Skills 保持在 ~/.ai-skills/，由 zcore 管理

**日期：** 2026-04-11  
**决策者：** 架构负责人  
**理由：**
- 用户已有 102 个 skills 在此目录
- 保持兼容性
- 用户可以自定义 skills

**影响：**
- Skills 不打包到 pip
- `zcore skill install` 从仓库复制到 ~/.ai-skills/
- SkillRouter 继续从 ~/.ai-skills/ 加载

### 决策 4：3 个核心 skills 内置

**日期：** 2026-04-11  
**决策者：** 产品负责人  
**理由：**
- memory-manager, l2-capture, runtime-doctor 是最常用的
- 用户应该开箱即用
- 提升用户体验

**影响：**
- 这 3 个 skills 打包到 zcore Python 包
- 提供统一的 CLI 接口
- 其他 14 个 skills 按需安装

---

## 第八部分：下一步行动

### 立即行动（本周）

1. **Phase 1：文档更新**
   - [ ] 更新 Z-Core README.md
   - [ ] 更新 KitClaw README.md
   - [ ] 创建 docs/migration-from-kitclaw.md
   - [ ] 更新 v2/pm/Decision-Log.md

2. **沟通**
   - [ ] 在 Z-Core 仓库创建 issue 说明定位变化
   - [ ] 在 KitClaw 仓库创建 issue 说明 archived 状态

### 短期行动（2 周内）

3. **Phase 2：Skills 管理**
   - [ ] 复制 17 个核心 skills
   - [ ] 实现 `zcore skill install/list/uninstall`
   - [ ] 内置 3 个核心 skills
   - [ ] 测试兼容性

### 中期行动（1 个月内）

4. **Phase 3：RAG 集成**
   - [ ] 迁移 RAG 引擎
   - [ ] 添加可选依赖
   - [ ] 实现 `zcore install rag`
   - [ ] 更新文档

5. **Phase 4：内置 Skills**
   - [ ] 集成 3 个 skills 到 Python 包
   - [ ] 统一命令接口
   - [ ] 向后兼容测试

---

## 附录 A：相关文档

- [v2/design/product-strategy.md](../design/product-strategy.md) - 产品战略（需要更新）
- [v2/design/architecture.md](../design/architecture.md) - 架构设计
- [v2/pm/Decision-Log.md](Decision-Log.md) - 决策日志（需要更新）
- [v2/pm/Current-State.md](Current-State.md) - 当前状态
- [README.md](../../README.md) - 项目 README（需要更新）

## 附录 B：参考资料

- KitClaw V1 仓库：`~/projects/kitclaw/`
- Z-Core V2 仓库：`~/projects/Z-Core/`
- 现有 skills：`~/.ai-skills/` (102 个)
- 现有内存：`~/.ai-memory/` (55 条 whiteboard 记录)

---

**文档版本：** 1.0  
**最后更新：** 2026-04-11  
**维护者：** Z-Core 产品团队
