"""OpenEvolve 评测入口（独立模块，OpenEvolve 按文件路径加载执行）。

注意：OpenEvolve 会把传入的 callable 序列化到临时文件，闭包引用会丢失；
因此评测器必须是自包含文件，自行完成所有 import 与配置加载。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config  # noqa: E402
from runner.sandbox import run_in_sandbox  # noqa: E402

_cfg = load_config()
SYMBOLS = [s["code"] for s in _cfg.data.symbols]


def evaluate(program_path: str) -> dict:
    """OpenEvolve 评测接口：返回纯 float 指标（MAP-Elites 需要）。"""
    from runner import tracker

    result = run_in_sandbox(Path(program_path), SYMBOLS, "val")
    if not result["ok"]:
        print(f"[sandbox-fail] {result.get('error', '')[:300]}", file=sys.stderr)
        return {"combined_score": -1e9}
    metrics = result["metrics"]
    tracker.record_run(program_path, "val", result["fitness"], metrics,
                       source="openevolve")
    return {
        # combined_score 是 OpenEvolve 的唯一排序依据（否则它会把所有指标平均，
        # total_trades 这类大数值会污染分数）
        "combined_score": float(result["fitness"]),
        "mean_sharpe": float(metrics["mean_sharpe"]),
        "mean_max_drawdown": float(metrics["mean_max_drawdown"]),
        "mean_turnover": float(metrics["mean_turnover"]),
        "total_trades": float(metrics["total_trades"]),
        "complexity": float(metrics["complexity_lines"]),
    }
