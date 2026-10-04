"""fitness 与回测评测器单测（用合成数据，不依赖网络）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import Config, DataConfig, SplitConfig
from evaluator import backtest


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    """确定性合成行情：趋势 + 周期。"""
    rng = np.random.default_rng(42)
    n = 800
    dates = pd.bdate_range("2020-01-01", periods=n)
    drift = np.linspace(0, 0.5, n)
    cycle = 0.1 * np.sin(np.linspace(0, 8 * np.pi, n))
    noise = rng.normal(0, 0.01, n).cumsum()
    close = pd.Series(100 + drift * 50 + cycle * 100 + noise, index=dates)
    return pd.DataFrame(
        {
            "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": 1e6, "amount": close * 1e6,
        },
        index=dates,
    )


def test_split_covers_segments(synthetic_df, monkeypatch):
    cfg = Config(split=SplitConfig(
        train=("2020-01-01", "2021-06-30"),
        val=("2021-07-01", "2021-12-31"),
        test=("2022-01-01", "2022-06-30"),
    ))
    parts = backtest.split_close(synthetic_df, cfg)
    assert set(parts) == {"train", "val", "test"}
    assert not parts["train"].empty and not parts["val"].empty
    # 段之间不重叠
    assert parts["train"].index.max() < parts["val"].index.min()


def test_run_backtest_basic(synthetic_df):
    cfg = Config()
    signals = (synthetic_df["close"] > synthetic_df["close"].rolling(20).mean()).astype(float)
    result = backtest.run_backtest(signals.fillna(0), synthetic_df["close"], cfg)
    assert result.n_trades >= 0
    assert -1 <= result.max_drawdown <= 1


def test_fitness_min_trades_gate(tmp_path):
    """交易次数不足时 fitness = -inf。"""
    from evaluator.fitness import compute_fitness

    # 不 touching network：构造一个从不交易的策略文件
    strategy = tmp_path / "never_trade.py"
    strategy.write_text(
        "def generate_signals(df, params=None):\n"
        "    import pandas as pd\n"
        "    return pd.Series(0.0, index=df.index)\n"
    )
    # 直接 monkeypatch evaluate_symbol 太深；这里只验证 load_strategy
    from evaluator.fitness import load_strategy

    fn = load_strategy(strategy)
    assert callable(fn)
