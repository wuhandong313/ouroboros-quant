"""vectorbt 回测封装：确定性、固定成本、三段切分。

策略接口约定（种子策略与进化产物必须遵守）：
    策略文件暴露 `generate_signals(df: pd.DataFrame, params: dict) -> pd.Series`
    df 为单标的多列行情（open/high/low/close/volume/amount），
    返回目标仓位序列：-1（做空/空仓）到 1（满仓），A股现货实际为 0~1。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import vectorbt as vbt

from config import Config, load_config
from runner.data import load_symbol


@dataclass
class BacktestResult:
    total_return: float
    sharpe: float
    max_drawdown: float
    n_trades: int
    turnover: float
    equity: pd.Series

    def to_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "n_trades": self.n_trades,
            "turnover": self.turnover,
        }


def run_backtest(
    signals: pd.Series,
    close: pd.Series,
    cfg: Config,
) -> BacktestResult:
    """对单一信号序列回测。signals/close 已按同一索引对齐。"""
    entries = (signals > 0) & (signals.shift(1) <= 0)
    exits = (signals <= 0) & (signals.shift(1) > 0)
    size = signals.clip(0, 1).where(signals > 0, 0)

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        size_type="targetpercent",
        init_cash=cfg.backtest.initial_cash,
        fees=cfg.backtest.fees,
        slippage=cfg.backtest.slippage,
        freq="1D",
    )
    trades = pf.trades.count()
    turnover = float(pf.turnover()) if trades > 0 else 0.0
    return BacktestResult(
        total_return=float(pf.total_return()),
        sharpe=float(pf.sharpe_ratio()) if trades > 0 else float("-inf"),
        max_drawdown=float(pf.max_drawdown()),
        n_trades=int(trades),
        turnover=turnover,
        equity=pf.value(),
    )


def split_close(df: pd.DataFrame, cfg: Config) -> dict[str, pd.DataFrame]:
    """按配置三段切分。评测器专用——策略代码拿不到此切分逻辑。"""
    out = {}
    for name, (start, end) in {
        "train": cfg.split.train, "val": cfg.split.val, "test": cfg.split.test,
    }.items():
        out[name] = df.loc[start:end]
    return out


def evaluate_symbol(
    signal_fn, code: str, segment: str, cfg: Config | None = None
) -> BacktestResult:
    """在指定数据段上评测策略函数。fitness 计算的统一入口。"""
    cfg = cfg or load_config()
    df = load_symbol(code)
    seg_df = split_close(df, cfg)[segment]
    if seg_df.empty:
        raise ValueError(f"{code} 在 {segment} 段无数据")
    signals = signal_fn(seg_df)
    if not isinstance(signals, pd.Series):
        raise TypeError("generate_signals 必须返回 pd.Series")
    signals = signals.reindex(seg_df.index).fillna(0)
    return run_backtest(signals, seg_df["close"], cfg)
