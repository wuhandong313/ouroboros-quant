"""种子策略 1：双均线趋势跟踪。

约定：暴露 generate_signals(df, params) -> pd.Series（目标仓位 0~1）。
EVOLVE-BLOCK 包裹整个可进化区域（对齐 OpenEvolve 官方示例惯例）。
"""

# EVOLVE-BLOCK-START
PARAMS = {"fast": 10, "slow": 60}


def generate_signals(df, params=None):
    params = {**PARAMS, **(params or {})}
    close = df["close"]
    fast = close.rolling(params["fast"]).mean()
    slow = close.rolling(params["slow"]).mean()
    # 金叉满仓、死叉空仓
    signal = (fast > slow).astype(float)
    return signal
# EVOLVE-BLOCK-END
