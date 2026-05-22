from __future__ import annotations

import pandas as pd


# 第一阶段只开放两个常用回测周期，避免误传 pandas 其他频率字符串。
SUPPORTED_TIMEFRAMES = ("5min", "15min")


def resample_ohlcv(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """将 1min OHLCV 数据重采样成更大周期。

    聚合规则是行情数据的常规规则：
    - open: 周期内第一根 1min K 线开盘价；
    - high: 周期内最高价；
    - low: 周期内最低价；
    - close: 周期内最后一根 1min K 线收盘价；
    - volume: 周期内成交量求和。
    """

    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {SUPPORTED_TIMEFRAMES}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("frame index must be a pandas DatetimeIndex")

    aggregation = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    # label="right" / closed="right" 表示 09:31-09:35 的数据标记为 09:35。
    # 这种右端点标记方式更贴近“这根 K 线在该时间点收盘完成”的回测习惯。
    resampled = frame.resample(timeframe, label="right", closed="right").agg(aggregation)

    # 如果某个周期没有任何有效价格，open/high/low/close 会是 NaN，
    # 这种空 K 线不应进入后续回测。
    return resampled.dropna(subset=["open", "high", "low", "close"])
