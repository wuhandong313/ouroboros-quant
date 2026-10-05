# Ouroboros-Quant 衔尾蛇

递归自我改进（RSI）的**量化研究** agent 系统：让 AI agent 按专业量化研究流程研发策略，并让"研究员"本身随研究过程持续进化。

## 量化研究流程 × 自进化闭环

系统按业界量化研究流水线组织，进化闭环嵌入其中：

```
① 数据工程 ──► ② 因子/信号研究 ──► ③ 检验与评价 ──► ④ 组合与风控 ──► ⑤ 归因复盘 ─┐
     ▲                ▲                  ▲                                    │
     │                │                  │                                    │
     │   ┌────────────┴──────────────────┴───────────────────┐                │
     └───┤ 自进化闭环（本项目核心）                            │◄───────────────┘
         │ Meta^n 递归 Ω 层叠（arXiv 2608.24735）              │
         │  · 内循环：11 标的=11 任务，进化策略代码             │
         │  · 深层 Ω 层：研究员级策略层（pre_process）          │
         │    + 可复用算子库（code_library：因子/风控工具）     │
         │  · 深度由收敛决定，Archive 沉淀全程谱系             │
         └────────────────────────────────────────────────────┘
```

Meta^n 的关键洞察：自改进系统不应让"生成器"自我修改（会破坏自身），而是保持**固定元操作 Ω** 递归作用于自身产物——每层 Ω 读取下层执行 trace 与代码，写出更高一层（研究策略 + 可调用算子库）。层角色随深度自然涌现：浅层改信号、深层改方法论。

| 环节 | 业界标准 | 本系统实现 | 状态 |
|---|---|---|---|
| ① 数据工程 | 数据清洗/复权/特征库 | `runner/data.py`：akshare→parquet，增量缓存+6 项质量检查 | ✅ |
| ② 因子/信号研究 | 因子假设→信号构造 | 策略=LLM 生成的 Python 函数，Meta^n Ω 层叠挖掘（`metan_bridge/`） | ✅ |
| ③ 检验与评价 | 样本外检验、成本真实性、多重检验校正 | `evaluator/`：train/val/test 三段+费率滑点+换手/复杂度惩罚；IC/IR、walk-forward 待接入 | 🔶 部分 |
| ④ 组合与风控 | 风险模型、组合优化、约束 | 路线图（M3+） | ⏳ |
| ⑤ 归因复盘 | 绩效归因、失败复盘 | Meta^n trace/inspiration 机制天然承载；教训库待接 | 🔶 部分 |

三层进化路线（渐进式）：**L1 提示词+记忆 → L2 研究工作流 → L3 检验管线自身进化**，在 Meta^n 中统一为同一 Ω 递归机制的不同深度。

## 快速开始

```bash
uv sync                          # 安装依赖（含 references/meta-n 引擎）
python -m runner.data            # 下载行情数据到 data/cache/
python -m app eval strategies/seed/ma_cross.py     # 评测种子策略
python -m app evolve-metan --iterations 12         # Meta^n 进化战役（11 标的多任务）
python -m app report             # 查看实验报告
```

旧基线（OpenEvolve 内循环 + EvoAgentX 外循环方案）完整保留在分支 `baseline/openevolve-evoagentx`，`app.py evolve` 命令仍可用作对照实验。

## LLM 配置（进化循环需要）

```bash
export DEEPSEEK_API_KEY=sk-...   # 默认配置，模型名在 configs/openevolve.yaml
# 其他 OpenAI 兼容接口：OPENAI_API_KEY / OPENAI_API_BASE + 修改模型名
```

## 实验基线（2024 验证段，11 标的，费率 3bp+滑点 1bp）

| 策略 | fitness | mean_sharpe | 换手 | 备注 |
|---|---|---|---|---|
| ma_cross | -0.92 | 0.23 | 2.5 | 趋势跟踪 |
| rsi_reversion | -5.65 | 0.39 | 12.2 | 高换手被成本惩罚压制——进化空间大 |
| momentum | -2.84 | -0.12 | 5.7 | 2024 单边行情不利 |
| **rsi_reversion 进化 12 代后** | **-0.22** | **0.93** | **2.1** | Wilder 平滑+信号平滑+连续趋势过滤+软死区 |

## 目录

- `metan_bridge/` Meta^n 引擎桥接层：量化任务适配器（11 标的=11 任务）、per-symbol 评测接线
- `strategies/` 信号/因子基因（Python 文件；Meta^n 下由 LLM 直接生成，种子仅作对照基线）
- `evaluator/` 检验管线：回测封装、适应度（防过拟合设计）、OpenEvolve 评测入口（基线分支用）
- `runner/` 数据管道、沙箱执行、实验追踪
- `research_agent/` 教训记忆库（FTS5 检索）
- `references/meta-n/` Meta^n 官方引擎（本地克隆）
- `papers/` 21 篇 RSI/自进化高影响力论文 + 全中文精读报告（`papers/reports/index.html`）
- `reports/` 阶段报告（HTML）

## 引用的开源与研究

- [Meta^n](https://github.com/minnesotanlp/meta-n)（arXiv 2608.24735, UMN）— **当前全栈进化引擎**：固定 Ω 元操作递归层叠，深度由收敛决定
- [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)（AlphaEvolve 开源实现）— 基线分支内循环引擎
- [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) — 基线分支外循环引擎
- 论文锚点：Meta^n (2608.24735)、Darwin Gödel Machine (2505.22954)、AlphaEvolve (2506.13131)、AFlow (2410.10762)、Promptbreeder (2309.16797) 等 21 篇，完整清单与中文精读见 `papers/reports/index.html`

> 免责声明：本项目仅用于量化研究与教育，不构成投资建议，不接入实盘。
