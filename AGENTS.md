# Repository Guidelines

## Project Structure & Module Organization

This Python 3.11+ quant research application keeps its entry point and configuration at the root (`app.py`, `config.py`). `runner/` handles data and experiment tracking; `evaluator/` implements backtests and fitness scoring; `metan_bridge/` connects Meta^n; `research_agent/` stores research memory; and `strategies/seed/` contains baseline strategies. Tests live in `tests/`, YAML settings in `configs/`, benchmark inputs in `data/quant_backtest/`, and summaries in `reports/`. Do not commit generated caches, local engine clones, or experiment outputs.

## Build, Test, and Development Commands

- `uv sync` installs project and development dependencies from the locked environment.
- `uv run python -m runner.data` downloads and caches market data (network required).
- `uv run python -m app eval strategies/seed/ma_cross.py` evaluates one strategy.
- `uv run python -m app evolve-metan --iterations 12` runs a Meta^n evolution experiment and requires a configured model API key.
- `uv run python -m app report` displays experiment results.
- `uv run pytest` runs the test suite. There is no build or coverage command configured.

## Coding Style & Naming Conventions

Use four spaces and standard Python conventions: `snake_case` for modules, functions, and variables; `CapWords` for classes. Keep functions focused, use type hints and helpful docstrings, and follow nearby patterns. Name strategies descriptively (for example, `rsi_reversion.py`). No formatter or linter is configured. Keep credentials and machine-specific paths out of source code.

## Testing Guidelines

Add tests under `tests/` using `test_*.py` files and `test_*` functions. Prefer synthetic inputs and temporary files so tests do not require market-data services or credentials. Run `uv run pytest`; no coverage threshold is defined.

## Commit & Pull Request Guidelines

Recent commits use a short prefix (`feat:`, `refactor:`, `docs:`, `deps:`) and concise summary; Chinese summaries are also used. Keep commits focused. Pull requests should explain the change, note affected strategies/configuration, list validation and outcomes, and link a related issue when applicable. Add screenshots for rendered report changes when useful.

## Security & Configuration

Keep API keys in environment variables (for example, `DEEPSEEK_API_KEY`) or an untracked `.env`; never commit secrets. Review local data and experiment outputs before staging. This repository is for research and education, not live trading.
