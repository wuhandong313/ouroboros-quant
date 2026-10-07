# Cordis-Evo：基于 dsh/Cordis 的自进化通用 Agent 方案

> 版本：v0.1（2026-10-07）
> 状态：方向已确认，待评审
> 底座：DeepSeek Harness (dsh) + Cordis 插件框架（arXiv 2608.25512）

---

## 1. 定位与核心论点

### 1.1 一句话定义

> **Cordis-Evo 是一个以 Cordis 插件为进化单元的通用 Agent：它把任务经验沉淀为自生成的插件与工作流，能力边界和策略质量随使用持续开放提升。**

### 1.2 为什么是 Cordis（而不是 LangChain / MCP / 自研 loop）

插件化本身不稀缺，稀缺的是**安全的运行时自我修改**。Cordis 论文（北大 × DeepSeek，《A Programming Paradigm for Spatiotemporal Composability》）解决了两个正交问题，恰好都是自进化的工程前提：

| 性质 | 机制 | 对自进化的意义 |
|---|---|---|
| 时间可组合性 | Effect：挂载注册副作用，卸载统一回收 | agent 自生成的插件试错失败后**干净回滚**，不积累脏状态/资源泄漏 |
| 空间可组合性 | Coeffect + inject：声明依赖，随依赖自动启停 | 能力**自我组织**，进化出的新组件无需人工编排加载顺序 |
| 运行时替换 | HMR + ctx.isolate/extend | 候选 agent 在隔离 Context 中整体替换，契约（ctx.llm 等）不变 |

没有这三条，"agent 改写自己"只是 demo；有了这三条，它才能成为可长期运行、可审计的系统。这是本方案区别于 DGM / Voyager / Gödel Agent 的根本立足点。

### 1.3 自进化的优越性（论证主线）

| 维度 | 静态通用 Agent（OpenHands/OpenManus 等） | Cordis-Evo |
|---|---|---|
| 能力上限 | 出厂工具集，长尾任务必死 | 运行时自生成插件，上限开放 |
| 策略质量 | 人工设计 prompt/工作流，天花板=设计者 | 评估驱动的持续搜索，无预设终点 |
| 经验积累 | 每次任务从零开始 | 技能库复利，同类任务成本递减 |
| 改进成本 | 改代码→测试→发版 | 进化闭环自动筛选，失败干净卸载 |
| 可解释性 | 改权重（RL 路线）不可读 | 进化产物全是代码/prompt/配置，**人类可审计、可回滚** |

**作用的明确定义（本方案必须兑现的三件事）：**

1. **长尾任务自救**：遇到没有现成工具的任务，agent 现场生成 Cordis 插件并热装载，而不是直接失败。
2. **经验复利**：每个任务沉淀可复用资产（插件进技能库、工作流入档案），后续同类任务的 token 成本与失败率递减。
3. **安全演进**：失败的能力/策略尝试被 Effect 完整回收；评测采用 sealed 协议，进化不污染运行时、不欺骗自己。

**明确不做的事：**

- 不做权重级进化（不训练/微调模型）——进化产物必须人类可审计。
- L5（harness/agent loop 代码自改写）暂缓——先把双主轴闭环做扎实，作为 M4 之后的选项。

---

## 2. 进化对象：Agent Genome

进化的操作对象是一个可序列化的 **Agent Genome**，本质是一个标准 Cordis bundle + 声明式配置：

```yaml
genome:
  id: g-20261007-0042
  parents: [g-20261006-0017, g-20261006-0023]   # 谱系追踪
  # ── 策略轴 ──
  strategy:
    system_prompt: prompts/p7.md                # 可进化 prompt
    workflow: dag/research_write.yaml           # AFlow 式节点图（plan/act/verify 拓扑）
    model_router: { hard: deepseek-r1, easy: deepseek-chat }
    memory_policy: { episodic: sqlite-vec, compress: summary-v2 }
  # ── 能力轴 ──
  capability:
    base_plugins: [web-search, code-exec, file-io, browser]
    evolved_plugins: [pdf-extract-v2, table-parse-v1]  # 自生成，进技能库
    skill_lib_ref: skills/g-0042/               # 本 genome 可用的技能快照
  meta:
    mutation_log: " grafted table-parse from g-0017; rewrote verify node prompt"
```

Genome 内容寻址（哈希即 ID），全部谱系、变异日志、评测证据写入 append-only manifest。

## 3. 双主轴自进化机制

### 3.1 能力轴（主）：插件自生成 + 技能库

借鉴 Voyager 技能库与 DGM 代码生成，落在 Cordis 扩展点上：

**触发 → 生成 → 验证 → 入库 的闭环：**

```
任务执行中工具缺失/失败
    │  (tools/post-execute hook 检测 capability gap)
    ▼
LLM 生成候选 Cordis 插件（标准 plugin 结构：provide/inject/effect）
    │
    ▼
静态检查 + ctx.isolate() 隔离 Context 中试运行（合成用例 + 当前任务）
    │  通过 ──────────────► 失败
    ▼                       ▼
挂载到当前 agent scope    Effect 完整卸载，零副作用残留
    │
    ▼
写入技能库（带验收用例、使用统计、来源 genome 谱系）
    │
    ▼
后续 genome 通过 skill_lib_ref 继承 → 经验复利
```

**关键设计：**

- **插件契约**：自生成插件必须实现标准验收接口（自述能力、自带 2+ 测试用例、声明依赖）。不满足契约直接拒绝，不进隔离试运行。
- **技能库分层**：`frozen`（多 genome 验证稳定）→ `candidate`（单 genome 产出）→ `quarantine`（有失败记录，限制使用）。晋升/降级由使用统计驱动。
- **复用收益度量**：每个插件记录 `reuse_count × 平均节省 token`，作为能力轴适应度的组成部分。

### 3.2 策略轴（辅）：prompt + 工作流 + 记忆策略

| 子层 | 进化对象 | 算法来源 | Cordis 落点 |
|---|---|---|---|
| Prompt | system prompt、节点级 prompt、变异 prompt 本身 | Promptbreeder、TextGrad/MIPRO | `agent/pre-step` hook 注入，不动核心 loop |
| 工作流 | plan/act/verify 的 DAG 拓扑与节点配置 | AFlow 搜索空间、EvoAgentX WorkFlow | 工作流即插件配置，isolate 中整体替换 |
| 记忆策略 | 情景记忆压缩、检索策略、技能召回排序 | Voyager curriculum、RAG 经验 | 自定义 `ctx.memory` service，契约不变实现可换 |

**双轴协同关系**：策略轴决定"能不能把现有能力用好"，能力轴决定"现有能力的边界在哪"。
- 工作流进化中发现某节点反复失败且原因是缺工具 → 触发能力轴生成插件；
- 能力轴新增插件后 → 工作流搜索空间自动扩大（新节点类型可用）。
这就是选双主轴而非单轴的核心理由：**两轴互为对方的适应度景观改变者**。

## 4. 进化算法核心

### 4.1 总体循环（内外双层）

```
外循环（genome 进化，跨任务）
│
├── 从档案选亲本（MAP-Elites 格内精英 + 新颖性加权）
├── 变异/交叉生成候选 genome
├── 内循环评估 ─────────────────────────────┐
│   ├── 级联评估（便宜先筛）：              │
│   │   Stage1: 5 题 dev-mini（timeout 60s）│
│   │   Stage2: 20 题 dev（ Successive      │
│   │     Halving 淘汰后 50%）              │
│   │   Stage3: 全 dev 集 + 成本计量        │
│   └── 失败 trial 记 −1e9，不丢弃          │
├── 写入档案（MAP-Elites 分格）             │
└── 周期性岛间迁移（每 N 代）               │
```

### 4.2 档案与多样性：Island MAP-Elites（OpenEvolve 式）

- **行为描述子（分格维度）**：`任务域（GAIA L1/L2/L3 × web/code/file/multimodal）× 成本档 × 工具使用模式`
- **岛模型**：4 个岛独立进化，每 10 代环形迁移 top-2，防止单一适应度景观收敛到局部最优
- **亲本选择**：格内精英 70% + 跨格新颖性采样 30%（quality-diversity，而非纯 greedy）
- **archive admission ≠ champion**：入档只是第一级门，见 §5.3

### 4.3 变异算子库

| 算子 | 作用对象 | 说明 |
|---|---|---|
| LLM diff mutation | prompt / 工作流节点 / 插件函数 | OpenEvolve EVOLVE-BLOCK 式区块保护，核心区块不可改 |
| DAG crossover | 工作流 | 两个亲本交换子图（如 A 的 verify 子树 × B 的 plan 子树） |
| 插件嫁接 | 技能库引用 | 把亲本 A 的 evolved_plugins 移植给 B |
| 策略-能力联变 | 双轴 | 新增插件 + 同步改写 workflow 引入对应节点（原子变异） |
| 元变异 | 变异 prompt 本身 | Promptbreeder 式，进化"怎么进化" |

### 4.4 适应度函数

```
fitness(g) = Σ_task score(task, g)  − λ₁ · total_tokens  − λ₂ · wall_time
             − λ₃ · safety_violations  + λ₄ · skill_reuse_gain
```

- per-task score 连续化（GAIA 精确匹配 → 部分分），失败/超时/不可归因 = 哨兵 −1e9
- `skill_reuse_gain`：使用技能库插件带来的 token 节省，显式奖励经验复利
- λ 系数写入 genome meta，本身可作为超参进化（远期）

## 5. 安全与评测协议（TCB 分离）

直接沿用 dsh-self-evolving 项目的纪律（其 AGENTS.md 已是成熟范本）。

### 5.1 TCB（可信计算基，候选 genome 不可写）

- Evaluator service、scorer、数据集与划分、budget controller、safety policy、evidence store
- 全部作为 Cordis **root-context service** 提供；候选 agent 在 `ctx.isolate()` 派生的隔离 Context 中运行，对 TCB 只读

### 5.2 候选运行约束

- 每个候选 genome 在**一次性隔离 Context** 中通过真实 Cordis Loader 启动，进程结束即销毁
- 候选不得装入长期运行的 controller 进程
- 缺失/损坏/超时/不可归因结果默认记失败；仅预先登记的、与 reward 无关的基础设施类失败可重试；**不丢弃失败 trial**

### 5.3 四级门（任何绿灯不可跳级）

```
archive admission → dev champion → sealed promotion → full-set leaderboard
```

- GAIA dev 集反馈可驱动搜索；**sealed/测试集的题目、轨迹、聚合分数在 genome 哈希冻结前不得进入 proposer/selector/archive**
- 揭盲只发生一次；baseline 校准证明协议不可行时 fail closed，不静默缩小协议后宣称达标

### 5.4 证据

- 全部产物 append-only + 内容寻址（模型路由、随机种子、预算、任务集版本、插件哈希写入 run manifest）
- 凭据不进候选、不进日志、不进 prompt、不进证据

## 6. 验证场景：GAIA

**首个 benchmark：GAIA（通用 AI 助理基准）**，理由：

- 任务真实多样（web 浏览、代码、文件处理、多模态、多步推理），工具需求长尾——最能体现能力轴价值
- L1/L2/L3 难度分级天然适合做技能库的"自动课程"（Voyager 式 curriculum：L1 沉淀的技能服务 L2/L3）
- 社区可比性：可直接与 OpenManus、OWL、HuggingFace 等公开通用 agent 结果对比

**种子任务分布**：dev 集按任务域分层抽样，保证 MAP-Elites 各格有初始密度。

## 7. 系统架构总览

```
┌─────────────────────── TCB（root context，不可进化）───────────────────────┐
│  evaluator · scorer · budget · safety-policy · evidence-store · GAIA 数据集  │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────────────── 进化引擎（可信 Cordis bundle）─────────────────────┐
│  proposer（变异算子库）· selector（MAP-Elites+岛）· archive · skill-lib     │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────────────── 候选 agent（isolate context，可进化）──────────────┐
│  genome = 策略(prompt/workflow/memory) + 能力(base+evolved plugins)        │
│  CodeAct 式 agent loop（借鉴 OpenHands 事件流 / SWE-agent ACI）            │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────────────── 底座：dsh + Cordis（不修改上游）───────────────────┐
│  plugin runtime · service 契约 · event/hook · Effect · isolate · HMR       │
└───────────────────────────────────────────────────────────────────────────┘
```

## 8. 借鉴清单（不重造轮子）

| 来源 | 借什么 |
|---|---|
| **dsh + Cordis** | 底座、插件运行时、isolate/Effect/HMR、事件系统 |
| **dsh-self-evolving** (timwhitez) | TCB 分离、四级门、sealed 协议、证据规范、Cordis bundle 组织方式 |
| **OpenHands** | CodeAct 事件流 loop、sandbox 执行接口 |
| **SWE-agent** | Agent-Computer Interface（工具接口对 LLM 友好的设计原则） |
| **OpenManus / OWL** | 通用 agent 的 plan-act 模式、GAIA 任务处理范式 |
| **OpenEvolve** | MAP-Elites 档案、岛模型、diff-based 进化、EVOLVE-BLOCK 保护 |
| **DGM** (SakanaAI) | 轨迹驱动的自我诊断、agent 谱系档案 |
| **AFlow / EvoAgentX** | 工作流搜索空间、TextGrad/MIPRO 优化器 |
| **Voyager** | 技能库、自动课程、经验复利机制 |
| **Promptbreeder** | 变异 prompt 的自进化（元变异） |

## 9. 里程碑路线

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0 底座** | Cordis 环境跑通；静态通用 agent（CodeAct loop + web/code/file/browser 基础插件）；GAIA dev-mini baseline | baseline 分数 + 完整证据链 |
| **M1 策略轴闭环** | prompt + 工作流进化（MAP-Elites 档案、级联评估、四级门协议） | 同预算 dev 集分数显著超 M0 |
| **M2 能力轴闭环** | 插件自生成 → 隔离验收 → 技能库；GAIA L1 课程 | 技能库 ≥20 个冻结插件；长尾任务自救案例 ≥5 |
| **M3 双轴协同** | 策略-能力联变异子、岛模型、reuse_gain 适应度项 | 双轴 > 单轴消融 |
| **M4 优越性实验** | 四臂对比 + sealed 揭盲 + 完整报告 | 见 §10 |

**预算纪律**：每里程碑预设 token/时长预算上限，写入 manifest；超预算 fail closed。

## 10. "自进化优越性"实验设计（M4）

固定总 token 预算，四臂对比：

| 臂 | 配置 | 检验什么 |
|---|---|---|
| (a) 静态 | M0 baseline 不加进化 | 基线 |
| (b) 仅策略轴 | prompt+workflow 进化，插件固定 | 策略轴单独收益 |
| (c) 仅能力轴 | 插件进化，prompt/workflow 固定 | 能力轴单独收益 |
| (d) 双轴 | 完整系统 | 协同收益（假设：d > b+c−a） |

**指标**：

1. GAIA sealed 集总分（主指标，揭盲一次）
2. 单位 token 得分（成本效率）
3. **新任务域冷启动曲线**：held-out 任务域上前 K 题的成功率随题数增长的斜率——自进化的核心卖点是泛化速度，静态 agent 此曲线应为平线
4. 技能库复用率与复利曲线：`reuse_count` 分布、平均任务成本随时间下降趋势

## 11. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| 自生成插件质量噪声大，技能库被污染 | 契约 + 隔离验收 + 分层晋升（frozen/candidate/quarantine） |
| 适应度 hacking（钻 GAIA 评分漏洞） | sealed 协议 + 失败哨兵 + 人工抽检轨迹 |
| 进化搜索 token 成本失控 | 级联评估 + Successive Halving + 预算 fail closed |
| Cordis/dsh 上游 API 漂移 | 上游只读 + 适配层集中 + pin 版本进 manifest |
| GAIA 榜单污染（dev 集过拟合） | 四级门 + held-out 任务域冷启动指标 |

---

## 附：与相关工作的差异化一句话

- **vs DGM**：DGM 改 harness 代码且无安全装卸底座；我们改插件（粒度更安全）且有 Cordis Effect 兜底
- **vs Voyager**：Voyager 限 Minecraft 单域、无正式评测协议；我们面向通用任务 + sealed 四级门
- **vs AFlow/EvoAgentX**：它们只进化工作流/prompt（策略轴）；我们双轴，且能力轴产物是一等公民插件
- **vs dsh-self-evolving**：它优化 coding agent harness（Terminal-Bench）；我们做通用 agent 能力进化（GAIA），协议层直接复用其纪律
