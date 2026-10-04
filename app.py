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


@app.command()
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
def evolve(strategy: str, generations: int = 0):
    """OpenEvolve 进化战役。"""
    import json

    from config import ROOT
    from runner import tracker

    cfg = load_config()
    n_gens = generations or cfg.evolution.generations
    symbols = [s["code"] for s in cfg.data.symbols]

    try:
        from openevolve import OpenEvolve
    except ImportError:
        console.print("[red]openevolve 未安装：uv add openevolve[/red]")
        raise typer.Exit(1)

    # OpenEvolve 需要一个 evaluator 函数：读策略文件 → 沙箱评测 → 返回 fitness
    def evaluator(program_path: str, **kwargs) -> dict:
        result = run_in_sandbox(Path(program_path), symbols, "val")
        if not result["ok"]:
            console.print(f"[yellow]变体评测失败：{result.get('error', '')[:200]}[/yellow]")
            return {"score": float("-inf")}
        tracker.record_run(program_path, "val", result["fitness"], result["metrics"],
                           source="openevolve")
        return {"score": result["fitness"], "metrics": result["metrics"]}

    config_path = ROOT / "configs" / "openevolve.yaml"
    system = OpenEvolve(
        initial_program_path=str(strategy),
        evaluation_function=evaluator,
        config_path=str(config_path) if config_path.exists() else None,
    )
    console.print(f"[green]开始进化：{strategy}，{n_gens} 代[/green]")
    best = system.run(iterations=n_gens * cfg.evolution.population)
    console.print(f"[bold green]最佳 fitness：{best.get('score', best)}[/bold green]")
    console.print(json.dumps(best, ensure_ascii=False, default=str, indent=2))


@app.command()
def report(limit: int = 20):
    """最近实验报告。"""
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
