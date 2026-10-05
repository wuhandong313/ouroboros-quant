"""ouro CLI：进化 / 评测 / 报告 入口。

用法：
    python -m app evolve strategies/seed/ma_cross.py          # OpenEvolve 进化
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
