"""Meta^n 引擎桥接层：把 Ouroboros-Quant 的量化策略评测暴露为 Meta^n 任务。

Meta^n 官方库位于 references/meta-n/（只 import，不修改），
本包在导入时把该目录注入 sys.path。模块：

- quant_benchmark：QuantAdapter（每标的一个 TaskDescription，
  evaluate 走 run_in_sandbox/vectorbt 回测）与评测专用 config 路径。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 项目根（metan_bridge/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent

# Meta^n 官方库不在本项目依赖里，用 sys.path 注入（幂等）
_METAN_SRC = ROOT / "references" / "meta-n"
if _METAN_SRC.is_dir() and str(_METAN_SRC) not in sys.path:
    sys.path.insert(0, str(_METAN_SRC))
