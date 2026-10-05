"""全局配置加载。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent  # config.py 位于仓库根目录
CONFIG_PATH = ROOT / "configs" / "base.yaml"
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "experiments.sqlite"


def _load_dotenv() -> None:
    """加载仓库根目录 .env（不覆盖已有环境变量）。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        import os
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass
class DataConfig:
    source: str = "akshare"
    symbols: list[dict] = field(default_factory=list)
    start: str = "2020-01-01"
    end: str = "2025-12-31"
    adjust: str = "qfq"


@dataclass
class SplitConfig:
    train: tuple[str, str] = ("2020-01-01", "2023-12-31")
    val: tuple[str, str] = ("2024-01-01", "2024-12-31")
    test: tuple[str, str] = ("2025-01-01", "2025-12-31")


@dataclass
class BacktestConfig:
    initial_cash: float = 1_000_000
    fees: float = 0.0003
    slippage: float = 0.0001
    min_trade_size: int = 100


@dataclass
class FitnessConfig:
    dd_penalty: float = 1.0
    cost_penalty: float = 0.5
    complexity_penalty: float = 0.01
    min_trades: int = 10


@dataclass
class EvolutionConfig:
    generations: int = 50
    population: int = 8
    llm_primary: str = "gpt-4o"
    llm_secondary: str = "gpt-4o-mini"


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    fitness: FitnessConfig = field(default_factory=FitnessConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = Config()
    for section, klass in [
        ("data", DataConfig),
        ("split", SplitConfig),
        ("backtest", BacktestConfig),
        ("fitness", FitnessConfig),
        ("evolution", EvolutionConfig),
    ]:
        if section in raw:
            values = dict(raw[section])
            if section == "split":
                values = {k: tuple(v) for k, v in values.items()}
            setattr(cfg, section, klass(**values))
    return cfg
