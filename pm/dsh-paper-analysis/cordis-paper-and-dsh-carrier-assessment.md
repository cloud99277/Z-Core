# Cordis 时空可组合性论文深度分析 × Z-Core 载体评估

> 日期：2026-08-14
> 论文：《A Programming Paradigm for Spatiotemporal Composability》（Shi, Zhang / PKU；Cui / DeepSeek-AI，88 页）
> 对象：Z-Core（v3/develop，0.2.0，8,725 行核心 + 3,841 行测试）
> 配套事实报告：`pm/dsh-paper-analysis/zcore-deep-analysis.md`（子代理代码勘察，143 测试实跑 142 passed）

---

## 第一部分：论文深度分析

### 1. 问题：动态组合的两个正交维度

论文把"动态组合"（组件在运行时装载/卸载/重配）拆成两个维度，并用效应/余效应理论分别建模：

| 维度 | 定义 | 静态场景的退化形式 | 动态场景的难点 |
|---|---|---|---|
| **时间可组合性** | 组件移除时，它对共享环境的所有修改必须完整、安全地回退 | 词法作用域（RAII、bracket） | 长生命周期、有状态效应，作用域不再被词法限定 |
| **空间可组合性** | 组件间依赖可声明、可发现、可验证地解析 | 模块 import 解析 | 依赖在运行时出现、消失、更换身份 |

**粗粒度替代方案及其代价**（§1.2.3）：OS 提供进程级时间回退（重启丢状态），容器编排提供服务级空间组合（跨组件调用引入网络开销）。而现代系统在更细粒度上组合——VSCode 插件卸载必须重启宿主（Top 100 插件中 87 个含可执行代码）、deactivate 钩子把效应释放与效应创建分离（违反局部性）；agent harness 的自我进化要求以近乎无人监管的频率替换自身组件，每次重启都不可接受。论文主张"粒度失配"必须由组件同级的组合抽象解决。

### 2. 理论构造：把效应/余效应从编译期抬升为运行时机制

**（1）可回退效应（§3.1）** —— 时间维度的局部保证：

- 每个效应是 `Γ → Γ × (Γ→Γ)`：变换上下文的同时**返回显式逆**，交给运行时追踪。效应上下文 `∂Γ = Γ × (Γ→Γ)`，第二分量是"累加器" φ（至今所有逆的复合）。
- `track` 记录、`recover` 恢复；扭复合幺半群 𝔗Γ 保证逆按反序累加（LIFO）；Theorem 7 的**健全不变量**：任何时刻 `φ(γ) = γ₀`（恢复目标不变）。
- **见证条件** 𝔈∗Γ：逆只需在"效应被应用的那个状态"上真正回退（`g(δ) = γ`），而不是全局逆——这是关键放宽，让"打开文件→关闭句柄"这类只在原地可逆的操作也能建模。
- **效应独立性**（§3.1.3）：两个效应互不干扰的充要条件是变换幺半群 𝔐(e₁)、𝔐(e₂) 交换 + 不扰动对方产生的逆。Corollary 21：独立效应可以**任意顺序**回退——这正是"从运行系统中单独摘掉一个组件"所需要的。单累加器只能 LIFO，独立性才能支撑组件级乱序摘除。

**（2）反应式余效应（§3.2）** —— 空间维度的局部保证：

- 依赖表 Σ 上，`set(k,v)` 被定义为**一个效应**（类型就是 𝔈∗Σ，逆是 `∖k`）——"注册依赖本身是可回退效应"，这是两套机制的融合点。
- 组件声明余效应规范 d ⊆ K；每次上下文变更按 `notify_d(σ, σ′) ∈ {activating, deactivating, neutral}` 分类，满足性翻转驱动激活/去激活。**局部空间可组合性判据**：组件只在 d 被满足的状态激活（永不读到缺失绑定）；每个变更都被分类（损失满足性必被发现）。
- **隔离（realm）**：同一个键在不同上下文解析到不同实现（两层映射 k→r→v）——运行时 ad-hoc 多态，多租户/测试/沙箱的基础。**拦截（intercept）**：依赖访问携带元数据（monoid 合并、右偏、上下文方优先），实现"不改组件就能约束它如何使用依赖"的横切控制。

**（3）统一上下文与观察等价（§3.3）** —— 范式成立的关键：

- `Γ∞ = μΓ. Γ × (Γ→Γ) × Σ`：当前状态 + 累加器 + 余效应表，递归自相似。Σ 不受限的类型族可以编码**任何**共享可变状态——"组件与环境的一切交互都经过这一个实体"。
- 观察等价 ≃ 由每个键自己的等价关系（键的操作集能区分什么）组装。把"状态相等"放宽到 ≃ 之后：Theorem 7 的恢复保证才真正可达（堆布局、生成名字不可恢复但不可区分）；且交换性（独立性）读作"至 ≃"才可满足。**分解原则**：可交换部分放效应（随便什么顺序），顺序敏感部分放余效应（键非交换 → 顺序必须外部施加：组件内用累加器 LIFO，组件间用依赖声明排序）。

**（4）动态组合演算（§4）** —— 把局部保证提升到整系统：

- 组件 = (d, p, e) 三元组：声明 / 提供 / 见证效应函数。fiber = 组件的一次实例化，携带自己的生命周期状态。注册表按树组织（π 父指针），余效应表由活动 fiber 的提供**导出**而非存储。
- 基础规则：O-Insert/O-Retire/O-Remove（编排输入）+ L-Reload/L-Unload（由 **target view 与 committed view 的比较**驱动——目标视图回答"是否该运行、依赖解析到谁"两个问题）。
- 进行中的迁移（真实运行时的四层扩展）：
  - **撤离（§4.3.1）**：L-Leave 先停止提供（依赖者立即感知）→ 等 **relied 守卫**（所有解析到它的依赖者都退场）→ 才跑累加器。Theorem 63 排序定理：依赖者在依赖期内读到的绑定恒定；提供者撤除晚于所有依赖者。这是论文对"teardown 期间还能用正在撤离的依赖"（如关连接池要把连接还回去）的答案。
  - **迭代（§4.3.2）**：效应迭代器 = **物化定界续延**（对应 yield/generator），每次迭代边界可中断（L-Divert 部分回滚）——激活不是原子的。
  - **异步惯性（§4.3.3）**：一旦迭代启动必须落地，不能取消；只能落完再卸载（reload 与 unload 互相链接）。
  - **失败（§4.3.4）**：L-Raise **先恢复再记录**——错误作为 outcome 落在 fiber 上（`Inactive(ξ)`），已装效应全部回退，失败不波及兄弟组件。
- 元理论四定理（读作"对任意调度都成立"）：
  - **保持性**（Theorem 59）：良构注册表被所有规则保持——relied 守卫保证移除的 fiber 不会被任何 committed view 引用（名字可安全复用）。
  - **时间可组合性 / 恢复精确性**（Theorem 61、Corollary 62）：在成对独立假设下，运行 fiber 的累加器 = 该 fiber 从未运行过的状态（精确到控制字段）。
  - **空间可组合性**（Theorem 63 排序、Theorem 64 解析一致性）：一个迁移只对一个 committed 解析执行；解析中途变更是"落在中途那次迭代之后走卸载"，而不是撕裂。
  - **进展**（Theorem 66）：≺ 无环 + 效应长度有界 → 无死锁、有限终止界、必达静止态。
  - **汇流**（Theorem 73）：**动态历史不留痕迹**——无论激活/去激活如何交错，静止态 = 按依赖拓扑序一次性静态装配的结果。这就是"增量调和 = 全量重建"的等价性（change propagation 的动态组合版）。

**（5）实现 Cordis（§5）与工程化**：

- `ctx.effect`（generator + guard + dispose 前插组合）、`ctx.get/set/isolate/intercept`、fiber 生命周期（refresh/reload/unload 惯性状态机）、**Proxy 属性访问强制依赖声明**（Algorithm 6：沿 fiber 链解析 committed view，未声明访问抛错 = 能力式访问控制）。
- 声明式 loader：entry（id/url/isolate/intercept/config/disabled）→ 增量调和（Theorem 73 背书：调和顺序无关，终态只由最终配置决定）；HMR 三阶段（模块分类 → 陈旧检测 → **事务式重载**，失败回滚缓存与 fiber）。
- Koishi 案例：4000+ 社区插件的聊天机器人框架，服务器端 + Web 控制台两套独立 Cordis 应用，验证表达性与通用性。

**（6）讨论中的可迁移观点（§6）**：

- **系统边界**（§6.1）：边界内可独占修改且可恢复 → 可追踪；边界外操作是 idΓ。**获取 vs 发射**两阶段：open/malloc/fork 在界内（记录可回退），write/send 越界（不可回退）。越界恢复只有两条路：**withholding**（输出提交问题：状态确定持久前扣住发射）与**compensation**（补偿动作，LIFO 可复合，但元理论要在更粗等价上重证）。
- **服务多路复用**（§6.2）：独占绑定 vs **服务代理**（broker 吸收 provider 切换的扰动 → 负载均衡、滚动更新、跨进程 RPC 都成为应用层组合模式而非基础设施操作）。
- **访问控制**（§6.3）：声明即能力请求、代理即能力中介；拦截元数据 = 细粒度策略（不改双方代码、不触发重载）；不可信代码仍需语言外沙箱。
- **语言无关条件**（§6.4）：时间维需要闭包 + 模块注册表/动态链接；空间维需要类型化键 + 属性访问中介（JS Proxy、Python 描述符/`__getattr__`）。
- **循环依赖**（§6.5）：循环 = 永久不激活（可预测、可静态报告）；消解靠细粒度拆分（代价是集成组件平方增长）。
- **版本化**（§6.6）：键碰撞与接口漂移；命名空间 / peer deps / 结构兼容三方案与开放问题。
- **结论直接点名方向**：自进化 agent harness——"AI agent 持续生成并替换自身 harness 组件"是论文主张的下一验证场景。**DSH 就是这个场景的参考实现**：本会话运行在 DSH 上，其动态插件（define→approval→run→update→rollback→undefine）、版本化包、HMR、能力审批栈，与论文 §5 的实现一一对应。

---

## 第二部分：Z-Core 现状速览（详见 zcore-deep-analysis.md）

- **定位**：零依赖、无常驻进程的 Python 3.11+ 纯 CLI；给 Claude/Gemini/Codex 等终端 Agent 提供共享记忆（L1/L2/L3）、会话、技能、治理、MCP 注册表、可观测性。
- **规模**：58 文件 / 8,725 行核心；14 个引擎（10 命名 + 4 附加）；56 个 CLI 叶子命令；143 测试实跑 142 passed 1 skipped。
- **架构事实**：`RuntimePaths`（frozen dataclass，21 路径）构造注入；无引擎注册表（`engines/__init__.py` 为空）；CLI 是 1450 行 if/elif 链；引擎间直接 import + 延迟 import 破循环；文件即状态 + 原子写 + fcntl 咨询锁；三个数据化扩展面（SKILL.md 目录式技能、hooks 目录、SourceAdapter ABC）。
- **已识别的结构性局限**（子代理 H1–H14）：引擎/命令/Agent 名单/三层记忆模型/LLM provider 与价格表/知识 provider 枚举全部硬编码；SKILL.md `dependencies` 字段解析但**从不校验**；workflow 无步骤间数据流、无回滚（失败即 partial）；预算只记账不拦截；Windows 下锁失效且 status 谎报；JSONL 追加、收割索引无锁。
- **路线图事实**：V3.1 在做跨 Agent 收割 + sqlite-fts5 搜索；`v2/pm/ideas/Harness-三层架构与V2增量.md` 已确立 **V3 = 主控大脑** 愿景（Planner / Evaluator / Dispatcher 三引擎，经 ACP subprocess 调度 Claude/Codex/Gemini）——**即自建一个 harness**。

---

## 第三部分：DSH 能否作为 Z-Core 的载体？（结论与路线）

### 总体判断

**"载体"成立，但不是"收编"，而是"双向互补集成"。** 理由：

1. **两者服务对象不同**：Z-Core 的价值是为**别的**终端 Agent（Claude/Gemini/Codex）提供跨会话状态，其护城河是"零依赖、纯 CLI、用完即退"（README FAQ Q3 自己论证过，拒绝并入 OpenClaw/Hermes 的理由同样适用于拒绝并入任何常驻宿主）；DSH 是**自己就是 Agent** 的 Cordis 宿主。把 Z-Core 引擎改写为 DSH 插件会同时失去 CLI 接口（其他 Agent 就用不到了）与零依赖卖点。
2. **但两条互补线是真实且现成的**：
   - DSH 有 `ctx.tools` 注册表 + 守卫执行管线 + sandbox + 审批栈——它可以把任何外部 CLI 变成受治理的工具；
   - DSH 有 **Python SDK**（`deepseek-harness-sdk`：pip 安装、子进程 JSON-RPC stdio、`DeepSeekHarness().run(...)`），Z-Core 是 Python 项目——**Z-Core → DSH 的调用路径官方已铺好**；
   - Z-Core 的知识治理刚从 2026-08-07 起转向 `external_readonly`（Z-Core 只读外部 owner 的健康清单、不拥有索引）——这正是为"外部宿主（如 DSH）拥有 L3、Z-Core 提供受治理读取"设计的接口姿态。

### 三个具体集成角色（按推荐度排序）

**角色 A｜DSH 作为 Z-Core 管理的第 N 个 Agent（成本最低，立即可行）**
- Z-Core 的 Agent-无关性是数据面的：`session start --agent dsh`、Harvester 加一个 `dsh_adapter`（读 DSH 的 JSONL/SQLite session persistence 目录）、`zcore setup dsh` 注入用法说明、MCP 同步目标加 DSH 配置。对应 H5/H6 两处硬编码的注册表化。
- 价值：DSH 会话从此进入 Z-Core 的跨 Agent 记忆闭环（DSH 里的决策 → L2 候选 → Claude Code 下次会话可见）。论文的 Harvester 正是 Z-Core 的数据前提。

**角色 B｜Z-Core 作为 DSH 的记忆/知识后端（DSH 侧一个小插件，高价值）**
- 在 DSH 里注册一个插件（动态 Cordis Plugin 或正式 package），把 `zcore memory search/write/pending --json`、`zcore session start/end --json`、`zcore knowledge health` 包装为 tools，`zcore` 作为子进程跑（DSH 的 bash/shell 工具天然支持）。
- 这是论文 §6.2 **服务代理模式**的字面实现：Z-Core CLI = broker，DSH 是消费者；Z-Core 文件即状态的持久层无需改动。DSH 的 sandbox + approval 恰好补上 Z-Core 治理"规则引擎而非强制沙箱"的缺口。
- 边界尊重 Z-Core 知识治理契约：L3 归外部 owner（DSH 的 storage 或用户自己的索引），Z-Core 只消费 health manifest——两边哲学（声明式契约 + 只读校验）同构。

**角色 C｜DSH 作为 Z-Core V3"主控大脑"的执行层（决策点，最需要想清楚）**
- V3 规划自建 Planner/Evaluator/Dispatcher = 自建 harness。DSH 已经把 agent-loop、subagent 编排、workflow、goal、ACP 协议（`packages/acp`）、评估与守卫做完了。两条子路线：
  - C1（保守）：Dispatcher 用 `deepseek-harness-sdk` 驱动 DSH 作为执行 Agent——Z-Core 保留"对用户负责的主控"定位，DSH 是最强的"工具人"。协议已存在（JSON-RPC stdio，Python 原生）。
  - C2（激进，但更符合 Z-Core 自己的 FAQ 哲学）：放弃自建 Planner/Dispatcher，Z-Core 收缩为"状态、记忆、适配器、技能包"层，编排交给 DSH。Z-Core 的 SKILL.md/hooks/adapters 三种数据格式可以直接作为 DSH 之上的领域层复用（子代理 8.2 节）。
- 建议：V3.1 先做角色 A（顺手），Planner/Dispatcher 启动前做一个 C1 vs C2 的 make-vs-buy 决策（`v3/pm/Analysis-V3-Make-vs-Buy.md` 已有方法论）。

### 不应做的事

- ❌ 把 Z-Core 引擎整体改写为 DSH 插件并废弃 CLI（丢 Agent 无关性与零依赖护城河）；
- ❌ 在 Z-Core 内嵌一个自写 daemon 去复刻 DSH 的常驻能力（V3.2 dashboard 若需要常驻进程，优先评估复用 DSH 而非自写——这正是"粗粒度替代方案"章节的教训的镜像）。

---

## 第四部分：Z-Core 后续开发可借鉴的 10 条（论文 → 具体代码）

| # | 论文机制 | Z-Core 现状（缺口证据） | 可落地的借鉴 |
|---|---|---|---|
| 1 | **可回退效应 + 累加器**（§3.1） | `workflow.py:96-146` 步骤失败即 `partial`，已完成的步骤**无补偿**；`session.end`（`session.py:43-94`）多步写（gzip→compact→extract→meta→index）中途崩溃留半态 | WorkflowStep 增加 `compensate` 逆操作；Engine 多步写按"每步返回逆 + 逆序回退"重构，崩溃恢复 = 重放逆 |
| 2 | **L-Raise 先恢复再记录**（§4.3.4） | `session.end` 中 `extract_from_conversation` 抛错时已写入的 `context.md`/`memories.json` 不回退 | 失败路径先撤销已落盘产物再记录 error outcome（而非留 partial 文件） |
| 3 | **依赖声明 + 满足性驱动激活**（§3.2.2） | `models/skill.py:44-55` 解析 `dependencies`，`router.py:150-206` 执行时**从不校验** | `skill match/run` 前检查依赖（所需 skill / MCP server / 配置键）满足性；缺失时返回 `inactive(missing=[...])` 而非运行到一半报错 |
| 4 | **relied 守卫 / 撤除排序**（§4.3.1） | `mcp.py:166-173` 向各 Agent 配置**整体覆盖写**，无依赖顺序、无回滚 | 同步前先记录被覆盖配置的逆（备份已存在，补齐"失败时逐 Agent 恢复"）；依赖 Agent 配置的 hook 先于提供者撤除 |
| 5 | **拦截元数据 / 能力式访问**（§3.2.3、§5.1.4） | `governance.py:59-84` 是全局正则黑名单；`shared-rules.yaml` 是全量注入 | 权限升级为 per-skill 元数据（SKILL.md `permissions` 已有字段），执行器按"组件声明 ⊕ 上下文元数据（右偏）"裁决；注入改为可 diff 的拦截合并 |
| 6 | **隔离 realm**（§3.2.3） | Harvester 三 Adapter 靠类继承分派（`harvester.py:112-122` 硬编码二元组） | 同一逻辑键 `sessions:<agent>` 用 realm 表解析到不同 adapter 实现——多租户/测试隔离顺带解决 |
| 7 | **版本化不可变包 + 审批 + 回滚**（DSH 动态插件模型） | `router.py:293-335` 安装 = `copytree/git clone`，覆盖即毁旧版 | Skill 安装引入 manifest 版本 + 备份 + `rollback`；安装动作进审计（Observability 已有 JSONL） |
| 8 | **观察等价 / 键级等价关系**（§3.3.2） | `memory.py:249-266` dedup 三重启发式，阈值 0.85 拍脑袋 | 把"两条记忆是否同一事实"形式化为键的等价关系 + 可区分测试（正常化文本/语义嵌入），去重与合并有可辩护的语义 |
| 9 | **汇流 + 调和**（Theorem 73、§5.2.1） | `session.py` 索引 vs 目录**双事实来源**无对账（崩溃窗口失配）；`SearchEngine` 线性扫描无索引 | 增加 `zcore doctor --reconcile`：从目录重建索引 = 论文"静止态只由最终配置决定"的文件系统版；V3.1 的 sqlite-fts5 索引用同一对账思想（索引 = 可重建的导出，不是事实源） |
| 10 | **系统边界：获取 vs 发射**（§6.1） | GhostAgent `generate()` 直接发射 HTTP（`ghost_agent.py:217-220`）；预算只记账（`observability.py:161-162`） | 预算从"事后记账"改为发射前 **withholding**（余额不足先扣住请求）；API 调用按"获取（request 构造，可回退）→ 发射（发送，不可回退）"分两阶段建模，重试/超时语义落在界内 |

**给 V3.2+ 的元建议**：Z-Core 的"文件即状态 + 原子写 + 咨询锁"本质上已经是论文汇流定理的一种实现（每次 CLI 调用 = 一次调和，静止态由最终配置决定）。真正缺的不是常驻进程，而是**三样东西**：① 多步操作的事务性（借鉴 #1/#2）；② 声明与实现的强制校验（借鉴 #3/#5）；③ 索引与目录的对账（借鉴 #9）。若 V3.2 dashboard 确实需要常驻宿主，先做 make-vs-buy：内嵌 `deepseek-harness-sdk` 驱动 DSH 作为执行与 Web 层，比自写 daemon + 自写编排引擎划算一个数量级——这也正是 Z-Core 自己对 OpenClaw/Hermes 采取的"上层分发器甩 JSON 任务给 Z-Core"策略的镜像应用。

---

## 附：一句话对照

> **Z-Core 把"可插拔"做在数据与文件格式层（SKILL.md/hooks/adapters 已是数据化扩展面），Cordis/DSH 把"可插拔"做在运行时与服务层（注册表/生命周期/热更新）。** 两者的业务逻辑与文件格式可直接互操作（角色 A/B/C），需要重构的是 Z-Core 那 14 处"import 即注册 / if-elif 即分发 / 枚举即事实"的代码接缝；而在 Z-Core 独立演进的路线上，论文最值得抄的并非框架本身，而是"多步操作的事务性、声明即校验、可对账的导出状态"三条纪律——它们恰好填上当前代码里已指认的三个缺口。
