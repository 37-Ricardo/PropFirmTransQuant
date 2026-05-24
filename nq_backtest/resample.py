from __future__ import annotations

import pandas as pd


# 第一阶段只开放两个常用回测周期，避免误传 pandas 其他频率字符串。
SUPPORTED_TIMEFRAMES = ("5min", "15min", "60min", "1h")
SUPPORTED_LABELS = ("left", "right")


def resample_ohlcv(
    frame: pd.DataFrame,
    timeframe: str,
    label: str = "left",
    closed: str = "left",
) -> pd.DataFrame:
    """将 1min OHLCV 数据重采样成更大周期。

    聚合规则是行情数据的常规规则：
    - open: 周期内第一根 1min K 线开盘价；
    - high: 周期内最高价；
    - low: 周期内最低价；
    - close: 周期内最后一根 1min K 线收盘价；
    - volume: 周期内成交量求和。

    TradingView 导出的 5min K 线使用左端点时间戳：
    例如 14:45 这根 5min K 线包含 14:45-14:49 的 1min 数据。
    因此这里默认使用 label="left" / closed="left" 来对齐 TradingView。
    """

    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {SUPPORTED_TIMEFRAMES}")
    if label not in SUPPORTED_LABELS:
        raise ValueError(f"Unsupported label: {label}. Supported: {SUPPORTED_LABELS}")
    if closed not in SUPPORTED_LABELS:
        raise ValueError(f"Unsupported closed: {closed}. Supported: {SUPPORTED_LABELS}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("frame index must be a pandas DatetimeIndex")

    aggregation = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    # label / closed 控制 K 线时间戳和区间归属。
    # 默认左端点规则与 TradingView 导出的 5min 图表数据完全一致。
    resampled = frame.resample(timeframe, label=label, closed=closed).agg(aggregation)

    # 如果某个周期没有任何有效价格，open/high/low/close 会是 NaN，
    # 这种空 K 线不应进入后续回测。
    return resampled.dropna(subset=["open", "high", "low", "close"])
