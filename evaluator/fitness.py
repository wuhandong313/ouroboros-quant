"""适应度计算：进化搜索的唯一优化目标（创新点1：防过拟合评测管线）。

fitness = mean(val_sharpe) - dd_penalty * mean(val_mdd)
          - cost_penalty * mean(turnover) - complexity_penalty * n_params

设计要点：
- 只在 val 段计算适应度，test 段只做最终报告（策略代码拿不到 test 数据）
- min_trades 门槛过滤无效策略
- 复杂度惩罚抑制参数堆砌式过拟合
"""
from __future__ import annotations

import inspect
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from config import Config, load_config
from evaluator.backtest import evaluate_symbol


def count_params(signal_fn) -> int:
    """复杂度代理指标：generate_signals 签名中 params dict 的键数由策略自报，
    这里退而求其次统计源码行数作为复杂度代理。"""
    try:
        src = inspect.getsource(signal_fn)
        return src.count("\n") + 1
    except (OSError, TypeError):
        return 0


def load_strategy(path: Path):
    """从策略文件加载 generate_signals 函数。"""
    spec = spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载策略文件 {path}")
    module = module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_signals"):
        raise AttributeError(f"{path} 缺少 generate_signals 函数")
    return module.generate_signals


def compute_fitness(
    strategy_path: Path,
    symbols: list[str],
    segment: str = "val",
    cfg: Config | None = None,
) -> tuple[float, dict]:
    """计算策略在多标的上的适应度。返回 (fitness, 指标明细)。"""
    cfg = cfg or load_config()
    signal_fn = load_strategy(strategy_path)

    sharpe_list, mdd_list, turnover_list, trade_total = [], [], [], 0
    active_codes = []
    for code in symbols:
        result = evaluate_symbol(signal_fn, code, segment, cfg)
        if result.n_trades == 0:
            continue  # 单标的零交易只跳过，不整体判死
        active_codes.append(code)
        trade_total += result.n_trades
        sharpe_list.append(result.sharpe)
        mdd_list.append(result.max_drawdown)
        turnover_list.append(result.turnover)

    # 至少一半标的有效交易，且合计次数过门槛
    if len(active_codes) < max(1, len(symbols) // 2):
        return float("-inf"), {"reason": f"仅 {len(active_codes)}/{len(symbols)} 标的有交易"}
    if trade_total < cfg.fitness.min_trades:
        return float("-inf"), {"reason": f"合计交易 {trade_total} 次 < 门槛 {cfg.fitness.min_trades}"}

    n = len(sharpe_list)
    mean_sharpe = sum(sharpe_list) / n
    mean_mdd = sum(mdd_list) / n
    mean_turnover = sum(turnover_list) / n
    complexity = count_params(signal_fn)

    f = cfg.fitness
    fitness = (
        mean_sharpe
        - f.dd_penalty * mean_mdd
        - f.cost_penalty * mean_turnover
        - f.complexity_penalty * complexity
    )
    metrics = {
        "fitness": fitness,
        "mean_sharpe": mean_sharpe,
        "mean_max_drawdown": mean_mdd,
        "mean_turnover": mean_turnover,
        "total_trades": trade_total,
        "complexity_lines": complexity,
        "per_symbol_sharpe": dict(zip(active_codes, [round(s, 3) for s in sharpe_list])),
    }
    return fitness, metrics
