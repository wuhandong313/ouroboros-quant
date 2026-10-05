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
         │ 内循环 OpenEvolve：进化信号/因子代码（AlphaEvolve 范式）│
         │ 外循环 EvoAgentX：进化研究员的假设生成与研究工作流      │
         │ 经验回流：失败实验 → 结构化教训 → 注入研究 prompt      │
         └────────────────────────────────────────────────────┘
```

| 环节 | 业界标准 | 本系统实现 | 状态 |
|---|---|---|---|
| ① 数据工程 | 数据清洗/复权/特征库 | `runner/data.py`：akshare→parquet，增量缓存+6 项质量检查 | ✅ |
| ② 因子/信号研究 | 因子假设→信号构造 | 策略=可进化 Python 函数（EVOLVE-BLOCK），OpenEvolve 自动挖掘 | ✅ |
| ③ 检验与评价 | 样本外检验、成本真实性、多重检验校正 | `evaluator/`：train/val/test 三段+费率滑点+换手/复杂度惩罚；IC/IR、walk-forward 待接入 | 🔶 部分 |
| ④ 组合与风控 | 风险模型、组合优化、约束 | 路线图（M3+） | ⏳ |
| ⑤ 归因复盘 | 绩效归因、失败复盘 | 教训库 `research_agent/memory.py`（失败→结构化教训→FTS5 检索） | 🔶 部分 |

三层进化路线（渐进式）：**L1 提示词+记忆 → L2 研究工作流 → L3 检验管线自身进化**，共享同一套档案/评测/沙箱基础设施。

## 快速开始

```bash
uv sync                          # 安装依赖
python -m runner.data            # 下载行情数据到 data/cache/
python -m app eval strategies/seed/ma_cross.py   # 评测种子策略
python -m app evolve strategies/seed/ma_cross.py # 启动信号进化战役
python -m app report             # 查看实验报告
```

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

- `strategies/` 信号/因子基因（Python 文件，EVOLVE-BLOCK 标记可进化区域）
- `evaluator/` 检验管线：回测封装、适应度（防过拟合设计）、OpenEvolve 评测入口
- `runner/` 数据管道、沙箱执行、实验追踪
- `research_agent/` 外循环研究员 agent 与教训记忆库
- `papers/` 20 篇 RSI/自进化高影响力论文（本地）
- `reports/` 阶段报告（HTML）

## 引用的开源与研究

- [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)（AlphaEvolve 开源实现）— 内循环引擎
- [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) — 外循环引擎（M2 接入）
- 论文锚点：Darwin Gödel Machine (2505.22954)、AlphaEvolve (2506.13131)、AFlow (2410.10762)、A Survey of Self-Evolving Agents (2507.21046) 等，完整清单见 `papers/`

> 免责声明：本项目仅用于量化研究与教育，不构成投资建议，不接入实盘。
