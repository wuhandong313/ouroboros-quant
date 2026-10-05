"""ouro CLI：进化 / 评测 / 报告 入口。

用法：
    python -m app evolve strategies/seed/ma_cross.py          # OpenEvolve 进化
    python -m app evolve-metan                                # Meta^n 全栈进化
    python -m app eval strategies/seed/ma_cross.py            # 评测单个策略
    python -m app report                                      # 最近实验报告
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from config import load_config

app = typer.Typer(help="Ouroboros-Quant：自进化量化策略研发系统")
console = Console()


@app.command("eval")
def eval_(strategy: str, segment: str = "val"):
    """评测单个策略（沙箱内执行）。"""
    from runner.sandbox import run_in_sandbox
    from runner import tracker

    cfg = load_config()
    symbols = [s["code"] for s in cfg.data.symbols]
    with console.status(f"沙箱评测 {strategy} ..."):
        result = run_in_sandbox(Path(strategy), symbols, segment)
    if not result["ok"]:
        console.print(f"[red]评测失败[/red]\n{result.get('error')}")
        raise typer.Exit(1)
    table = Table(title=f"{strategy} @ {segment}")
    table.add_column("指标"); table.add_column("值")
    for k, v in result["metrics"].items():
        if k != "per_symbol_sharpe":
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
    console.print(table)
    tracker.record_run(strategy, segment, result["fitness"], result["metrics"], source="cli-eval")


@app.command()
def evolve(strategy: str, iterations: int = 0, output_dir: str = "openevolve_output"):
    """OpenEvolve 进化战役。"""
    from config import ROOT

    cfg = load_config()
    n_iters = iterations or cfg.evolution.generations * cfg.evolution.population

    try:
        from openevolve import run_evolution
        import openevolve.process_parallel as _pp
    except ImportError:
        console.print("[red]openevolve 未安装：uv sync[/red]")
        raise typer.Exit(1)

    # 上游 bug 修复（0.4.0）：_serialize_config 漏传 enforce_evolve_blocks，
    # 导致 worker 侧永远关闭 EVOLVE-BLOCK 强制约束
    _orig_serialize = _pp.ProcessParallelController._serialize_config

    def _patched_serialize(self, config):
        d = _orig_serialize(self, config)
        d["enforce_evolve_blocks"] = config.enforce_evolve_blocks
        return d

    _pp.ProcessParallelController._serialize_config = _patched_serialize

    # 评测器必须是独立文件（OpenEvolve 会序列化 callable，闭包引用会丢失）
    evaluator_path = ROOT / "evaluator" / "openevolve_eval.py"
    console.print(f"[green]开始进化：{strategy}，{n_iters} 次迭代[/green]")
    result = run_evolution(
        initial_program=strategy,
        evaluator=str(evaluator_path),
        config="configs/openevolve.yaml",
        iterations=n_iters,
        output_dir=output_dir,
        cleanup=False,
    )
    console.print(f"[bold green]最佳 score：{result.best_score}[/bold green]")
    console.print(f"输出目录：{result.output_dir}")
    best_path = Path(output_dir) / "best_program.py"
    if result.best_code:
        best_path.write_text(result.best_code, encoding="utf-8")
        console.print(f"最佳策略已保存：{best_path}")


@app.command("metan")
def metan(
    iterations: int = typer.Option(10, "--iterations", help="Meta^n 最大迭代次数"),
    beam_width: int = typer.Option(2, "--beam-width", help="每轮选择的父代数 B"),
    output_dir: str = typer.Option("metan_output", "--output-dir", help="输出目录"),
    resume: bool = typer.Option(False, "--resume", help="从 output_dir 的 checkpoint 恢复"),
    limit: int = typer.Option(None, "--limit", help="只跑前 N 个任务（冒烟用）"),
):
    """Meta^n 进化战役（单标的 RSI 策略，DeepSeek 后端）。"""
    from metan_adapter import run_metan

    console.print(
        f"[green]Meta^n 进化开始：iterations={iterations}, "
        f"beam_width={beam_width}, output={output_dir}[/green]"
    )
    result = run_metan(
        max_iterations=iterations,
        beam_width=beam_width,
        output_dir=output_dir,
        resume=resume,
        limit=limit,
    )
    console.print("[bold green]═══ Meta^n 最终摘要 ═══[/bold green]")
    console.print(f"  Iterations: {result.total_iterations}")
    console.print(f"  Archive size: {result.archive_size}")
    console.print(f"  Best chain mean_score: {result.best_mean_score:.3f}")
    console.print(f"  Oracle mean_score: {result.oracle_mean_score:.3f}")
    console.print(f"  Best candidate: {result.best_candidate_id}")
    console.print(f"  Total tokens: {result.total_tokens:,}")


@app.command("evolve-metan")
def evolve_metan(
    iterations: int = typer.Option(12, "--iterations", help="Meta^n 最大迭代次数"),
    patience: int = typer.Option(3, "--patience", help="连续无改善轮数后提前停止"),
    max_depth: int = typer.Option(6, "--max-depth", help="候选链最大深度（递归 Ω 层数）"),
    output_dir: str = typer.Option("metan_output", "--output-dir", help="输出目录"),
    resume: bool = typer.Option(False, "--resume", help="从 output_dir 的 checkpoint 恢复"),
    seed: int = typer.Option(42, "--seed", help="随机种子"),
):
    """Meta^n 全栈进化战役（每个标的一个任务，DeepSeek 后端）。

    装配链照抄 references/meta-n/meta_n/main.py 的编程式装配段，
    无需 OpenEvolve 的 monkey-patch。
    """
    import asyncio
    import os
    from datetime import datetime

    from metan_bridge.quant_benchmark import METAN_FITNESS_CONFIG, QuantAdapter

    cfg = load_config()
    api_key = os.environ.get("DEEPSEEK_API_KEY")  # config.py 导入时已加载 .env
    if not api_key:
        console.print("[red]DEEPSEEK_API_KEY 未设置：请在项目根 .env 中配置[/red]")
        raise typer.Exit(1)

    from meta_n.core.evolutionary_orchestrator import (
        EvolutionaryConfig,
        EvolutionaryOrchestrator,
    )
    from meta_n.core.llm_client import LLMClient, LLMConfig
    from meta_n.core.omega import OmegaEngine
    from meta_n.integrations.openevolve import OpenEvolveExecutor

    llm_client = LLMClient(LLMConfig(
        base_url="https://api.deepseek.com",
        api_key=api_key,
        model="deepseek-chat",
        backend="openrouter",  # 通用 OpenAI 兼容后端
        # daily_budget 故意不设：meta_n 定价表无 deepseek，设置会 KeyError
    ))
    adapter = QuantAdapter(cfg)
    executor = OpenEvolveExecutor(adapter)
    omega = OmegaEngine(llm_client)

    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.mkdir(parents=True, exist_ok=True)

    evo_config = EvolutionaryConfig(
        max_iterations=iterations,
        patience=patience,
        max_depth=max_depth,
        output_dir=str(out_path),
        seed=seed,
        epsilon=0.02,
        beam_width=1,
        beam_candidates=1,
        temperatures=[0.5, 0.7, 0.9],
        consolidate=True,       # 每候选只改一个焦点标的，其余继承最优（防互相拖累）
        regression_guard=True,  # 可部署最优不得低于 base 复采样下限
        eval_repeats=3,         # LLM 生成随机，中位数降噪
        gate_tasks=3,
        parallel=1,
    )
    orch = EvolutionaryOrchestrator(
        llm_client, executor, omega, evo_config,
        solver_language="openevolve",
    )

    tasks = adapter.load_tasks()
    console.print(
        f"[green]Meta^n 全栈进化开始：{len(tasks)} 个标的任务，"
        f"iterations={iterations}, depth={max_depth}, output={out_path}[/green]"
    )

    # 运行 provenance（照 main.py 的 build_base_run_config + evolutionary 块）
    run_config = {
        "project": "ouroboros-quant",
        "benchmark": adapter.name,
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "solver_language": "openevolve",
        "executor": type(executor).__name__,
        "orchestrator": "evolutionary",
        "max_iterations": iterations,
        "patience": patience,
        "max_depth": max_depth,
        "epsilon": 0.02,
        "parallel": 1,
        "seed": seed,
        "consolidate": True,
        "regression_guard": True,
        "eval_repeats": 3,
        "gate_tasks": 3,
        "symbols": adapter.symbols,
        "fitness_config": str(METAN_FITNESS_CONFIG),
        "timestamp": datetime.now().isoformat(),
    }
    result = asyncio.run(orch.run(tasks, resume=resume, run_config=run_config))
    orch.save_results(result, run_config=run_config)

    console.print("[bold green]═══ Meta^n 最终摘要 ═══[/bold green]")
    console.print(f"  Iterations: {result.total_iterations}")
    console.print(f"  Archive size: {result.archive_size}")
    console.print(f"  Best chain mean_score: {result.best_mean_score:.3f}")
    console.print(f"  Oracle mean_score: {result.oracle_mean_score:.3f}")
    console.print(f"  Best candidate: {result.best_candidate_id}")
    console.print(f"  Total tokens: {result.total_tokens:,}")
    if result.convergence_history:
        tail = ", ".join(f"{s:.3f}" for s in result.convergence_history[-5:])
        console.print(f"  Convergence (last 5): {tail}")
    console.print("  Per-task best scores:")
    for tid, score in sorted(result.per_task_best_scores.items()):
        console.print(f"    {tid}: {score:.3f}")
    console.print(f"  输出目录：{out_path}")


@app.command()
def report(limit: int = 20):
    """最近实验报告。"""
    import json

    from runner import tracker

    rows = tracker.recent_runs(limit)
    table = Table(title=f"最近 {len(rows)} 次实验")
    for col in ("id", "strategy", "segment", "fitness", "mean_sharpe", "source"):
        table.add_column(col)
    for r in rows:
        metrics = json.loads(r["metrics_json"]) if r["metrics_json"] else {}
        table.add_row(
            str(r["id"]), Path(r["strategy_path"]).name, r["segment"],
            f"{r['fitness']:.3f}" if r["fitness"] is not None else "-",
            f"{metrics.get('mean_sharpe', float('nan')):.3f}" if metrics else "-",
            r["source"],
        )
    console.print(table)


if __name__ == "__main__":
    app()
