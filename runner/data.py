"""数据管道：akshare 下载 → parquet 缓存 → 质量检查。

用法：
    python -m runner.data          # 增量下载全部配置的标的
    python -m runner.data --check  # 仅做数据质量检查
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd

from config import DATA_DIR, load_config

CACHE_VERSION = "v1"  # 复权方式等口径变化时递增，旧缓存自动失效


def symbol_filename(code: str) -> Path:
    return DATA_DIR / "cache" / CACHE_VERSION / f"{code}.parquet"


def fetch_one(code: str, start: str, end: str, adjust: str, is_etf: bool) -> pd.DataFrame:
    """下载单标的日线（前复权），返回标准化的 OHLCV DataFrame。"""
    if is_etf:
        raw = ak.fund_etf_hist_em(
            symbol=code, period="daily",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust=adjust,
        )
    else:
        raw = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust=adjust,
        )
    df = raw.rename(
        columns={
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount",
        }
    )[["date", "open", "high", "low", "close", "volume", "amount"]]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def update_symbol(sym: dict, cfg) -> pd.DataFrame:
    """增量更新：已有缓存则只补最后日期之后的数据。"""
    path = symbol_filename(sym["code"])
    start, end = cfg.data.start, cfg.data.end
    if path.exists():
        cached = pd.read_parquet(path)
        last = cached.index.max()
        if last >= pd.Timestamp(end) - pd.Timedelta(days=7):
            return cached
        start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fresh = fetch_one(sym["code"], start, end, cfg.data.adjust, sym["type"] == "etf")
        df = pd.concat([cached, fresh])
        df = df[~df.index.duplicated(keep="last")].sort_index()
    else:
        df = fetch_one(sym["code"], sym_start(cfg), end, cfg.data.adjust, sym["type"] == "etf")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def sym_start(cfg) -> str:
    return cfg.data.start


def load_symbol(code: str) -> pd.DataFrame:
    path = symbol_filename(code)
    if not path.exists():
        raise FileNotFoundError(f"缓存不存在：{path}，先运行 python -m runner.data")
    return pd.read_parquet(path)


def quality_check(df: pd.DataFrame, code: str) -> list[str]:
    """数据质量检查，返回问题列表。"""
    issues = []
    if df.empty:
        return [f"{code}: 空数据"]
    if df.isna().any().any():
        cols = df.columns[df.isna().any()].tolist()
        issues.append(f"{code}: 缺失值列 {cols}")
    if (df["close"] <= 0).any():
        issues.append(f"{code}: 存在非正价格")
    if not df.index.is_monotonic_increasing:
        issues.append(f"{code}: 索引未排序")
    if df.index.duplicated().any():
        issues.append(f"{code}: 重复日期 {df.index.duplicated().sum()} 条")
    # 长期停牌检测：连续 20 个交易日无成交量
    flat = (df["volume"] == 0).rolling(20).sum().max()
    if flat == 20:
        issues.append(f"{code}: 存在 ≥20 日停牌段")
    # 收益率异常检测（涨跌停外的大跳变可能是复权错误）
    ret = df["close"].pct_change().abs()
    if (ret > 0.21).any():
        issues.append(f"{code}: 存在 >21% 单日收益，疑似复权错误")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="仅质量检查")
    args = parser.parse_args()

    cfg = load_config()
    all_issues = []
    for sym in cfg.data.symbols:
        if args.check:
            path = symbol_filename(sym["code"])
            if not path.exists():
                all_issues.append(f"{sym['code']}: 无缓存")
                continue
            df = pd.read_parquet(path)
        else:
            df = update_symbol(sym, cfg)
        issues = quality_check(df, sym["code"])
        all_issues.extend(issues)
        status = "OK" if not issues else "; ".join(issues)
        print(
            f"{sym['code']} {sym['name']:<6} {df.index.min().date()} ~ "
            f"{df.index.max().date()}  {len(df)} 行  [{datetime.now():%H:%M:%S}]  {status}"
        )
    if all_issues:
        raise SystemExit(f"数据质量检查发现 {len(all_issues)} 个问题")


if __name__ == "__main__":
    main()
