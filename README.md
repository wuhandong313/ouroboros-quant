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

## 目录

- `strategies/` 策略基因（Python 文件，EVOLVE_BLOCK 标记可进化区域）
- `evaluator/` 回测封装与适应度（防过拟合管线）
- `runner/` 沙箱执行、数据管道、实验追踪
- `research_agent/` 外循环研究员 agent（M2）
