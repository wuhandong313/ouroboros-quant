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
    """对单一目标仓位序列回测。signals/close 已按同一索引对齐。

    使用 from_orders + targetpercent：每根 bar 下单调整到目标仓位，
    天然支持 0~1 连续信号，费用与滑点按实际成交计。
    """
    target = signals.clip(0, 1).fillna(0)
    pf = vbt.Portfolio.from_orders(
        close=close,
        size=target,
        size_type="targetpercent",
        init_cash=cfg.backtest.initial_cash,
        fees=cfg.backtest.fees,
        slippage=cfg.backtest.slippage,
        freq="1D",
    )
    n_trades = int(pf.trades.count())
    # 换手率 = 总成交额 / (2 × 平均权益)，双边各计一半
    orders = pf.orders.records_arr
    traded_value = float((orders["size"].astype(float) * orders["price"].astype(float)).sum())
    mean_equity = float(pf.value().mean()) or cfg.backtest.initial_cash
    turnover = traded_value / (2.0 * mean_equity)
    sharpe = float(pf.sharpe_ratio()) if n_trades > 0 else float("-inf")
    return BacktestResult(
        total_return=float(pf.total_return()),
        sharpe=sharpe,
        max_drawdown=float(pf.max_drawdown()),
        n_trades=n_trades,
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
    """在指定数据段上评测策略函数。fitness 计算的统一入口。

    给策略提供段前 250 根 bar 作为指标预热（都是历史数据，无未来信息），
    但只在段内交易：信号重索引回段内索引，预热期仓位视为 0。
    """
    cfg = cfg or load_config()
    df = load_symbol(code)
    seg_df = split_close(df, cfg)[segment]
    if seg_df.empty:
        raise ValueError(f"{code} 在 {segment} 段无数据")
    # 预热窗口：段开始前的历史 bar
    seg_start = seg_df.index[0]
    warmup = df.loc[:seg_start].iloc[-251:-1]  # 不含段首本身
    signal_df = pd.concat([warmup, seg_df])
    signals = signal_fn(signal_df)
    if not isinstance(signals, pd.Series):
        raise TypeError("generate_signals 必须返回 pd.Series")
    signals = signals.reindex(seg_df.index).fillna(0)
    return run_backtest(signals, seg_df["close"], cfg)
