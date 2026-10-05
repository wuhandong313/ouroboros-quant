"""Meta^n 接入层（第一层）：QuantAdapter + 编程式装配入口 run_metan。

装配链照抄 references/meta-n/meta_n/main.py 的编程式装配段：
    LLMConfig -> LLMClient -> QuantAdapter -> OpenEvolveExecutor
    -> OmegaEngine -> EvolutionaryConfig -> EvolutionaryOrchestrator
    -> adapter.load_tasks() -> orch.run(tasks)

量化场景要点：
- 策略 fitness（sharpe 型）可为负，覆写 _eval_success：非哨兵失败即 success
- 覆写 _failure_score 返回 0.0，与 meta_n 钳位语义一致（哨兵 -1e9 不进均值）
- eval_repeats=1：vectorbt 回测确定性高，无需重复评测降噪
- consolidate=True：每个候选只改一个焦点标的，其余继承最优（防多标的互相拖累）
- DeepSeek 配置从 .env（config.py 启动时加载）的 DEEPSEEK_API_KEY 读取；
  不设 daily_budget（meta_n 定价表无 deepseek，设了会 KeyError）
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config  # noqa: E402  （导入即加载 .env）

from meta_n.core.evolutionary_orchestrator import (  # noqa: E402
    EvolutionaryConfig,
    EvolutionaryOrchestrator,
)
from meta_n.core.llm_client import LLMClient, LLMConfig  # noqa: E402
from meta_n.core.omega import OmegaEngine  # noqa: E402
from meta_n.integrations.openevolve import (  # noqa: E402
    OpenEvolveBaseAdapter,
    OpenEvolveExecutor,
)

DATA_DIR = ROOT / "data" / "quant_backtest"


class QuantAdapter(OpenEvolveBaseAdapter):
    """单标的量化策略适配器：负分数支持（参照 SymbolicRegressionAdapter）。"""

    @property
    def name(self) -> str:
        return "quant_backtest"

    def _eval_success(self, raw_score: float, is_sentinel_failure: bool) -> bool:
        """成功 = 正常运行而非崩溃：sharpe 型 fitness 可为负（亏钱策略也是
        有效样本），只要不是 -1e9 硬失败哨兵就不应被 Ω 当失败样本剔除。"""
        return not is_sentinel_failure

    def _failure_score(self) -> float:
        """硬失败/崩溃在 score 通道记 0.0（钳位下限），哨兵 -1e9 绝不进均值。"""
        return 0.0

    def load_tasks(self, limit: int | None = None) -> list:
        from meta_n.core.meta_layer import TaskDescription

        problems = self._discover_problems()
        if not problems:
            raise RuntimeError(
                f"未发现问题目录（{self.data_dir}）：每个任务目录需含 "
                "evaluator.py + initial_program.py + config.yaml"
            )
        tasks = [self._make_task(p) for p in problems]
        return tasks[:limit] if limit is not None else tasks


def run_metan(
    max_iterations: int = 10,
    beam_width: int = 2,
    output_dir: str = "metan_output",
    resume: bool = False,
) -> "object":
    """编程式入口：装配 Meta^n 全栈并对 quant_backtest 任务集跑进化。

    resume=True 时 output_dir 必须指向上次运行的目录（checkpoint 就地恢复）。
    返回 EvolutionaryResult。
    """
    cfg = load_config()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY 未设置：请在项目根 .env 中配置后重试"
        )

    llm_config = LLMConfig(
        base_url="https://api.deepseek.com",
        api_key=api_key,
        model="deepseek-chat",
        backend="openrouter",
        # daily_budget 故意不设：meta_n 定价表无 deepseek，设置会 KeyError
    )
    llm_client = LLMClient(llm_config)

    adapter = QuantAdapter(data_dir=str(DATA_DIR), timeout=600)
    tasks = adapter.load_tasks()
    if not tasks:  # pragma: no cover — load_tasks 空时已抛 RuntimeError
        raise RuntimeError(f"未发现问题目录（{DATA_DIR}）")
    executor = OpenEvolveExecutor(adapter)
    omega = OmegaEngine(llm_client)

    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.mkdir(parents=True, exist_ok=True)

    evo_config = EvolutionaryConfig(
        max_iterations=max_iterations,
        beam_width=beam_width,
        beam_candidates=max(2, beam_width),
        patience=5,
        epsilon=0.02,
        max_depth=10,
        output_dir=str(out_path),
        parallel=1,
        eval_repeats=1,       # 回测确定性高，无需重复评测
        consolidate=True,     # 每候选只改一个焦点标的，其余继承最优
        regression_guard=True,
    )

    orchestrator = EvolutionaryOrchestrator(
        llm_client,
        executor,
        omega,
        evo_config,
        solver_language="openevolve",
    )

    run_config = {
        "project": "ouroboros-quant",
        "adapter": "quant_backtest",
        "solver_language": "openevolve",
        "executor": "OpenEvolveExecutor",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "symbols": [s["code"] for s in cfg.data.symbols[:3]],
        "train_segment": list(cfg.split.train),
    }
    return asyncio.run(orchestrator.run(tasks, resume=resume, run_config=run_config))
