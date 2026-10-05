# Ouroboros-Quant

递归自我改进（RSI）量化策略研发 agent 系统：agent 研发交易策略，同时进化自身的提示词、工作流和策略代码。

## 架构

- **内循环**（OpenEvolve）：进化策略/因子代码，回测指标做适应度
- **外循环**（EvoAgentX）：进化研究员 agent 的 prompt 与工作流
- **经验回流**：失败回测 → 结构化教训 → 注入 prompt/工作流

详见 `configs/base.yaml`（评测基准，策略代码无权修改）与计划文档。

## 快速开始

```bash
uv sync                          # 安装依赖
python -m runner.data            # 下载行情数据到 data/cache/
python -m app eval strategies/seed/ma_cross.py   # 评测种子策略
python -m app evolve strategies/seed/ma_cross.py # 启动进化战役
python -m app report             # 查看实验报告
```

## LLM 配置（进化循环需要）

OpenEvolve 通过 litellm 调用 LLM，任选其一配置环境变量：

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# DeepSeek（OpenAI 兼容接口，需同时改 configs/openevolve.yaml 的模型名）
export DEEPSEEK_API_KEY=sk-...

# 其他 OpenAI 兼容接口
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://your-endpoint/v1
```

模型名在 `configs/openevolve.yaml` 的 `llm.primary_model / secondary_model` 修改，
国内接口示例：`deepseek/deepseek-chat`、`moonshot/moonshot-v1-32k`、`gemini/gemini-2.0-flash`。

## 种子策略基线（2024 val 段，11 标的）

| 策略 | fitness | mean_sharpe | 换手 | 备注 |
|---|---|---|---|---|
| ma_cross | -0.92 | 0.23 | 2.5 | 趋势跟踪 |
| rsi_reversion | -5.65 | 0.39 | 12.2 | 高换手被成本惩罚压制——进化空间大 |
| momentum | -2.84 | -0.12 | 5.7 | 2024 单边行情不利 |

## 目录

- `strategies/` 策略基因（Python 文件，EVOLVE_BLOCK 标记可进化区域）
- `evaluator/` 回测封装与适应度（防过拟合管线）
- `runner/` 沙箱执行、数据管道、实验追踪
- `research_agent/` 外循环研究员 agent（M2）
