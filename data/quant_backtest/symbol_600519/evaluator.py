"""Meta^n 单标的评测器（自包含，OpenEvolve 契约）。

evaluate(program_path) -> dict，combined_score 为唯一排序键。
train 段（2020-2023）vectorbt 回测，段前 250 bar 预热（无未来信息）。
combined_score = sharpe - dd_penalty*max_drawdown - cost_penalty*turnover
                 - complexity_penalty*代码行数
硬失败（异常/零交易/非有限指标）返回 combined_score = -1e9（meta_n 失败哨兵）。
"""
from __future__ import annotations

import importlib.util
import math
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # data/quant_backtest/<sym>/ -> 项目根
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import vectorbt as vbt

from config import load_config
from runner.data import load_symbol

SYMBOL = "600519"
FAILURE_SCORE = -1e9


def _load_program(program_path: str):
    """加载被评测的策略模块，返回 generate_signals 函数。"""
    spec = importlib.util.spec_from_file_location("_quant_program", program_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载策略 {program_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_quant_program"] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_signals"):
        raise AttributeError("策略缺少 generate_signals 函数")
    return module.generate_signals


def evaluate(program_path: str) -> dict:
    try:
        cfg = load_config()
        signal_fn = _load_program(program_path)

        # train 段 + 250 bar 预热（与 evaluator/backtest.evaluate_symbol 同口径）
        df = load_symbol(SYMBOL)
        start, end = cfg.split.train
        seg_df = df.loc[start:end]
        if seg_df.empty:
            raise ValueError(f"{SYMBOL} train 段无数据")
        seg_start = seg_df.index[0]
        warmup = df.loc[:seg_start].iloc[-251:-1]
        signal_df = pd.concat([warmup, seg_df])
        signals = signal_fn(signal_df)
        if not isinstance(signals, pd.Series):
            raise TypeError("generate_signals 必须返回 pd.Series")
        signals = signals.reindex(seg_df.index).fillna(0)

        # vectorbt 回测（与 runner/backtest.run_backtest 同口径）
        target = signals.clip(0, 1).fillna(0)
        pf = vbt.Portfolio.from_orders(
            close=seg_df["close"],
            size=target,
            size_type="targetpercent",
            init_cash=cfg.backtest.initial_cash,
            fees=cfg.backtest.fees,
            slippage=cfg.backtest.slippage,
            freq="1D",
        )
        n_trades = int(pf.trades.count())
        orders = pf.orders.records_arr
        traded_value = float(
            (orders["size"].astype(float) * orders["price"].astype(float)).sum()
        )
        mean_equity = float(pf.value().mean()) or cfg.backtest.initial_cash
        turnover = traded_value / (2.0 * mean_equity)
        sharpe = float(pf.sharpe_ratio()) if n_trades > 0 else float("-inf")
        max_dd = float(pf.max_drawdown())

        # 复杂度代理：源码行数（与 evaluator/fitness.count_params 同思路）
        src = Path(program_path).read_text(encoding="utf-8")
        complexity = len(src.splitlines())

        score = (
            sharpe
            - cfg.fitness.dd_penalty * max_dd
            - cfg.fitness.cost_penalty * turnover
            - cfg.fitness.complexity_penalty * complexity
        )
        finite = all(
            math.isfinite(x) for x in (score, sharpe, max_dd, turnover)
        )
        if not finite or n_trades == 0:
            print(
                f"[evaluator] 硬失败: finite={finite}, n_trades={n_trades}",
                file=sys.stderr,
            )
            return {
                "combined_score": FAILURE_SCORE,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "turnover": turnover,
                "n_trades": n_trades,
            }
        return {
            "combined_score": float(score),
            "sharpe": float(sharpe),
            "max_drawdown": float(max_dd),
            "turnover": float(turnover),
            "n_trades": int(n_trades),
        }
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return {"combined_score": FAILURE_SCORE}
