"""种子策略 3：动量（过去 N 日收益为正则持有）。"""

# EVOLVE-BLOCK-START
PARAMS = {"lookback": 120, "hold_threshold": 0.0}


def generate_signals(df, params=None):
    params = {**PARAMS, **(params or {})}
    close = df["close"]
    momentum = close.pct_change(params["lookback"])
    signal = (momentum > params["hold_threshold"]).astype(float)
    return signal
# EVOLVE-BLOCK-END
