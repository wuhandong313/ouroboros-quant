"""RSI 均值回归策略 — Meta^n 进化起点（源自 strategies/seed/rsi_reversion.py）。

接口契约（不得更改）：
    generate_signals(df) -> pd.Series
    df: 单标的 OHLCV DataFrame（列 open/high/low/close/volume/amount，date 索引）
    返回: 目标仓位序列，取值 0~1（0=空仓，1=满仓），索引与输入对齐
"""
import numpy as np
import pandas as pd

# EVOLVE-BLOCK-START
WINDOW = 14
LOWER = 30.0
UPPER = 70.0


def generate_signals(df):
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(WINDOW).mean()
    loss = (-delta.clip(upper=0)).rolling(WINDOW).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - 100 / (1 + rs)
    # 超卖加仓、超买卖出，区间外线性减仓
    signal = ((UPPER - rsi) / (UPPER - LOWER)).clip(0, 1)
    return signal
# EVOLVE-BLOCK-END
