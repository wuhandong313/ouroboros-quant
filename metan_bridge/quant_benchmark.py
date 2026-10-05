"""量化策略基准适配器：Ouroboros-Quant ↔ Meta^n 的核心桥接。

接入范式照抄 meta_n/integrations/openevolve.py 的 OpenEvolveBaseAdapter 家族：
- 每个标的（symbol）一个 TaskDescription，solution 是一份定义
  generate_signals(df) -> pd.Series 的 Python 脚本
- evaluate：脚本写临时 .py → run_in_sandbox（受限子进程 + vectorbt 回测）
  → EvalResult（连续分数，硬失败走 -1e9 哨兵）
- score_scale 继承基类：continuous / failure_sentinel=-1e9（被钳位而非平均）
- val 段做进化评测，test 段经 evaluate_test 做最终报告
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
import tempfile
from pathlib import Path

from metan_bridge import ROOT  # 包导入时已注入 references/meta-n 到 sys.path

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config, load_config  # noqa: E402
from runner import tracker  # noqa: E402
from runner.data import symbol_filename  # noqa: E402
from runner.sandbox import run_in_sandbox  # noqa: E402

from meta_n.core.meta_layer import TaskDescription  # noqa: E402
from meta_n.integrations.benchmark import EvalResult  # noqa: E402
from meta_n.integrations.openevolve import OpenEvolveBaseAdapter  # noqa: E402

# Meta^n per-symbol 评测专用配置（min_trades=3，其余同 base.yaml）
METAN_FITNESS_CONFIG = ROOT / "configs" / "metan_fitness.yaml"
EVAL_TIMEOUT = 150  # 单标的沙箱评测总超时（秒）


class QuantAdapter(OpenEvolveBaseAdapter):
    """多标的量化策略适配器（OpenEvolve 家族接入）。

    sharpe 型 fitness 可为负（亏钱策略也是有效样本），但基类的
    ``evaluate`` 用 score>0 判成功、会把无效策略折叠为哨兵——
    这里完全覆写 evaluate/evaluate_test，直接按 sandbox 结果构造
    EvalResult：崩溃/超时/无效（-inf）才是失败，负分数算成功样本。
    """

    def __init__(self, cfg: Config):
        # 基类构造需要 data_dir/timeout；量化场景不用它的目录发现问题逻辑
        super().__init__(data_dir=str(ROOT / "data"), timeout=EVAL_TIMEOUT)
        self.cfg = cfg
        self.symbols = [s["code"] for s in cfg.data.symbols]
        # 任务描述按"实际评测配置"（metan_fitness.yaml）渲染，保证文本口径
        # 与 sandbox 真实计分一致（min_trades 等可能不同于传入的 base cfg）
        self.eval_cfg = load_config(METAN_FITNESS_CONFIG)

    @property
    def name(self) -> str:
        return "ouroboros_quant"

    def score_scale(self) -> dict:
        """连续无界分数（sharpe 型可负），硬失败哨兵 -1e9 须被钳位而非平均。"""
        return {"kind": "continuous", "lo": None, "hi": None, "failure_sentinel": -1e9}

    # --- 任务构造 -------------------------------------------------------

    def _task_description(self, code: str) -> str:
        f = self.eval_cfg.fitness
        val_start, val_end = self.eval_cfg.split.val
        data_path = symbol_filename(code)
        return (
            f"你是量化策略研究员。任务：为 A 股标的 {code} 设计交易策略。\n"
            f"数据：parquet 文件 {data_path}（日线 OHLCV，date 索引，"
            "含 open/high/low/close/volume/amount 列）。\n\n"
            "你的脚本必须定义 generate_signals(df: pd.DataFrame) -> pd.Series，"
            "返回每日目标仓位（-1 到 1，1=满仓做多，0=空仓，负=做空；"
            "A 股现货实际仓位范围 0~1，超出会被截断）。\n\n"
            f"评测：val 段（{val_start} 至 {val_end}）vectorbt 组合回测，"
            "传入的 df 额外包含段开始前 250 根 K 线作为指标预热（不计入回测）。\n"
            f"fitness = sharpe − {f.dd_penalty:g}×max_drawdown − {f.cost_penalty:g}×turnover "
            f"− {f.complexity_penalty:g}×代码行数，分数越高越好。\n"
            f"全段合计 ≥{f.min_trades} 笔交易才有效，否则记硬失败（fitness=-inf）。\n\n"
            "可用 pandas/numpy，禁止网络访问。"
        )

    def load_tasks(self, limit: int | None = None) -> list[TaskDescription]:
        """每个 symbol 一个任务；数据路径写入 metadata 供核查。"""
        tasks = []
        for code in self.symbols:
            data_path = symbol_filename(code)
            if not data_path.exists():
                raise FileNotFoundError(f"标的 {code} 缓存不存在：{data_path}，先运行 python -m runner.data")
            tasks.append(
                TaskDescription(
                    task_id=code,
                    description=self._task_description(code),
                    metadata={
                        "benchmark": self.name,
                        "solution_language": "openevolve",
                        "symbol": code,
                        "data_path": str(data_path),
                        "timeout": EVAL_TIMEOUT,
                        "score_key": "combined_score",
                    },
                )
            )
        return tasks[:limit] if limit is not None else tasks

    # --- 评测 -----------------------------------------------------------

    async def evaluate(self, task: TaskDescription, solution: str) -> EvalResult:
        """val 段评测（进化循环用）。"""
        return await self._evaluate_segment(task, solution, "val")

    async def evaluate_test(self, task: TaskDescription, solution: str) -> EvalResult:
        """test 段评测（最终报告用，orchestrator 经 hasattr 探测）。"""
        return await self._evaluate_segment(task, solution, "test")

    async def _evaluate_segment(self, task: TaskDescription, solution: str, segment: str) -> EvalResult:
        fd, tmp_name = tempfile.mkstemp(suffix=".py", prefix=f"metan_{task.task_id}_")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(solution)
            timeout = int(task.metadata.get("timeout", EVAL_TIMEOUT))
            result = await asyncio.to_thread(
                run_in_sandbox, tmp_path, [task.task_id], segment, timeout,
                str(METAN_FITNESS_CONFIG),
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        if not result["ok"]:
            return EvalResult(
                success=False, score=0.0, raw_score=-1e9,
                feedback=f"评测崩溃：{result.get('error', '')[:500]}",
            )

        fitness = float(result["fitness"])
        if not math.isfinite(fitness):
            # -inf = 无效策略（交易次数不足等），+inf/NaN 同样按硬失败钳位
            reason = result.get("metrics", {}).get("reason", f"fitness={fitness}")
            return EvalResult(
                success=False, score=0.0, raw_score=-1e9,
                feedback=f"无效策略：{reason}",
            )

        m = result.get("metrics", {})
        feedback = (
            f"运行成功：sharpe={m.get('mean_sharpe', float('nan')):.3f}, "
            f"max_drawdown={m.get('mean_max_drawdown', float('nan')):.3f}, "
            f"turnover={m.get('mean_turnover', float('nan')):.3f}, "
            f"trades={m.get('total_trades', 0)}, fitness={fitness:.4f}"
        )
        # 实验追踪（成功样本才入库；路径为临时文件，分数历史为主）
        try:
            tracker.record_run(str(tmp_path), segment, fitness, m, source="metan")
        except Exception:  # noqa: BLE001 —— 追踪失败不影响评测
            pass
        return EvalResult(success=True, score=fitness, raw_score=fitness, feedback=feedback)
