"""种子策略 2：RSI 均值回归。"""
# === EVOLVE_BLOCK_START: params ===
PARAMS = {"window": 14, "lower": 30, "upper": 70}
# === EVOLVE_BLOCK_END ===


def generate_signals(df, params=None):
    params = {**PARAMS, **(params or {})}
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(params["window"]).mean()
    loss = (-delta.clip(upper=0)).rolling(params["window"]).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - 100 / (1 + rs)
    # 超卖买入、超买卖出，区间外线性减仓
    signal = ((params["upper"] - rsi) / (params["upper"] - params["lower"])).clip(0, 1)
    return signal
