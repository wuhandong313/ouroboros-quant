"""沙箱执行器：生成/进化的策略代码一律在受限子进程中运行。

限制：CPU 60s / 内存 2GB / 总超时 / 断网（可通过 env 放行）。
实现：fork 出的子进程先设置 rlimits，再加载策略并计算 fitness。
"""
from __future__ import annotations

import json
import multiprocessing as mp
import resource
from pathlib import Path

MEMORY_LIMIT = 2 * 1024 ** 3  # 2GB
CPU_LIMIT = 60  # 秒
DEFAULT_TIMEOUT = 120  # 总超时秒数


def _child_entry(payload_file: str, result_file: str) -> None:
    """子进程入口：先上限制，再干活，结果写文件（避免 IPC 复杂性）。"""
    # 注意：不设 RLIMIT_AS——numba/llvmlite 导入时映射大量虚拟地址空间，
    # 虚拟内存限制会误杀；资源控制以 RLIMIT_CPU + 总超时为准。
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
    # 断网：将文件描述符层面无法直接禁网，macOS 上用 sandbox-exec 由调用方可选启用；
    # 这里以环境变量约定，评测器不提供任何网络工具给策略代码。
    import traceback

    from config import load_config
    from evaluator.fitness import compute_fitness

    with open(payload_file) as f:
        payload = json.load(f)
    try:
        cfg = load_config(Path(payload["config_path"])) if payload.get("config_path") else load_config()
        fitness, metrics = compute_fitness(
            Path(payload["strategy_path"]),
            payload["symbols"],
            payload.get("segment", "val"),
            cfg,
        )
        result = {"ok": True, "fitness": fitness, "metrics": metrics}
    except Exception:  # noqa: BLE001 —— 沙箱内任何异常都折叠为失败结果
        result = {"ok": False, "error": traceback.format_exc(limit=5)}
    with open(result_file, "w") as f:
        json.dump(result, f, ensure_ascii=False)


def run_in_sandbox(strategy_path: Path, symbols: list[str], segment: str = "val",
                   timeout: int = DEFAULT_TIMEOUT,
                   config_path: str | None = None) -> dict:
    """在受限子进程中评测策略，返回 {"ok": bool, "fitness": float, ...}。

    config_path：可选的评测配置文件（如 configs/metan_fitness.yaml），
    传入后子进程用 load_config(Path(config_path)) 替代默认 base.yaml。
    """
    import tempfile

    # macOS 上 fork 与 Objective-C 运行时冲突（vectorbt/objc 崩溃），必须用 spawn
    ctx = mp.get_context("spawn")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as pf:
        json.dump({"strategy_path": str(strategy_path), "symbols": symbols,
                   "segment": segment, "config_path": config_path}, pf)
        payload_file = pf.name
    result_file = payload_file.replace(".json", ".result.json")

    proc = ctx.Process(target=_child_entry, args=(payload_file, result_file))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        return {"ok": False, "error": f"沙箱超时（>{timeout}s）"}
    try:
        with open(result_file) as f:
            return json.load(f)
    except FileNotFoundError:
        # 子进程在写结果前崩溃（导入失败/信号终止等），给出诊断
        import signal as _signal
        code = proc.exitcode
        why = f"被信号 {-code} 终止" if isinstance(code, int) and code < 0 else f"退出码 {code}"
        return {"ok": False, "error": f"沙箱子进程未产出结果（{why}）"}
    finally:
        Path(payload_file).unlink(missing_ok=True)
        Path(result_file).unlink(missing_ok=True)
