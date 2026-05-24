from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def add_ema(
    df: pd.DataFrame,
    length: int,
    price_col: str = "close",
    out_col: str | None = None,
) -> pd.DataFrame:
    """新增 EMA 指标列，尽量贴近 TradingView 的递归 EMA 行为。

    TradingView 的 `ta.ema` 使用 alpha = 2 / (length + 1) 的递归算法。
    pandas 中 `ewm(adjust=False)` 是最接近的直接实现方式。
    """

    _validate_positive_int(length, "length")
    _require_columns(df, [price_col])

    result = df.copy()
    column_name = out_col or f"ema_{length}"
    result[column_name] = (
        result[price_col].astype(float).ewm(span=length, adjust=False, min_periods=1).mean()
    )
    return result


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """新增 MACD 三列：macd_line、macd_signal、macd_hist。"""

    _validate_positive_int(fast, "fast")
    _validate_positive_int(slow, "slow")
    _validate_positive_int(signal, "signal")
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")
    _require_columns(df, ["close"])

    result = df.copy()
    close = result["close"].astype(float)
    fast_ema = close.ewm(span=fast, adjust=False, min_periods=1).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=1).mean()
    result["macd_line"] = fast_ema - slow_ema
    result["macd_signal"] = result["macd_line"].ewm(span=signal, adjust=False, min_periods=1).mean()
    result["macd_hist"] = result["macd_line"] - result["macd_signal"]
    return result


def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """新增 RSI，使用 Wilder RMA，尽量贴近 TradingView 的 `ta.rsi`。"""

    _validate_positive_int(length, "length")
    _require_columns(df, ["close"])

    result = df.copy()
    delta = result["close"].astype(float).diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = _rma(gain, length)
    avg_loss = _rma(loss, length)

    rsi = pd.Series(np.nan, index=result.index, dtype="float64")
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    loss_zero = (avg_loss == 0) & (avg_gain > 0)
    gain_zero = (avg_gain == 0) & (avg_loss > 0)
    normal = ~(both_zero | loss_zero | gain_zero) & avg_gain.notna() & avg_loss.notna()

    rsi.loc[both_zero] = 50.0
    rsi.loc[loss_zero] = 100.0
    rsi.loc[gain_zero] = 0.0
    rs = avg_gain.loc[normal] / avg_loss.loc[normal]
    rsi.loc[normal] = 100.0 - (100.0 / (1.0 + rs))

    result["rsi"] = rsi.clip(lower=0, upper=100)
    return result


def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """新增 ATR，使用 Wilder RMA，尽量贴近 TradingView 的 `ta.atr`。"""

    _validate_positive_int(length, "length")
    _require_columns(df, ["high", "low", "close"])

    result = df.copy()
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    previous_close = result["close"].astype(float).shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr"] = _rma(true_range, length).clip(lower=0)
    return result


def add_pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    """新增右侧确认的 pivot 列，避免把未来信息回填到历史 K 线。

    TradingView 的 `ta.pivothigh/ta.pivotlow` 只有在右侧 `right` 根 K 线
    收盘后才确认 pivot。为了避免未来函数，本函数把 pivot 值写在确认
    K 线上，而不是写回历史 pivot K 线。
    """

    _validate_positive_int(left, "left")
    _validate_positive_int(right, "right")
    _require_columns(df, ["high", "low"])

    result = df.copy()
    high = result["high"].astype(float).to_numpy()
    low = result["low"].astype(float).to_numpy()
    pivot_high = np.full(len(result), np.nan, dtype="float64")
    pivot_low = np.full(len(result), np.nan, dtype="float64")

    for center in range(left, len(result) - right):
        window_start = center - left
        window_end = center + right + 1
        confirm_index = center + right

        center_high = high[center]
        center_low = low[center]
        if np.isfinite(center_high) and center_high == np.nanmax(high[window_start:window_end]):
            pivot_high[confirm_index] = center_high
        if np.isfinite(center_low) and center_low == np.nanmin(low[window_start:window_end]):
            pivot_low[confirm_index] = center_low

    result["pivot_high"] = pivot_high
    result["pivot_low"] = pivot_low
    return result


def add_macd_waterline(df: pd.DataFrame, water_len: int = 8) -> pd.DataFrame:
    """新增 MACD 柱状图的平滑水线。"""

    _validate_positive_int(water_len, "water_len")
    result = _ensure_macd(df)
    result["macd_waterline"] = (
        result["macd_hist"].astype(float).ewm(span=water_len, adjust=False, min_periods=1).mean()
    )
    return result


def add_macd_zero_zone(
    df: pd.DataFrame,
    zero_scale_len: int = 50,
    zero_zone_pct: float = 0.35,
) -> pd.DataFrame:
    """新增 MACD 零轴附近的动态震荡区间。"""

    _validate_positive_int(zero_scale_len, "zero_scale_len")
    if zero_zone_pct < 0:
        raise ValueError("zero_zone_pct must be non-negative")

    result = _ensure_macd(df)
    scale = (
        result["macd_line"]
        .astype(float)
        .abs()
        .rolling(window=zero_scale_len, min_periods=1)
        .max()
        * float(zero_zone_pct)
    )
    result["macd_zero_zone_upper"] = scale
    result["macd_zero_zone_lower"] = -scale
    result["macd_in_zero_zone"] = result["macd_line"].abs() <= scale
    return result


def add_all_indicators(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """按配置新增一组标准指标。"""

    config = config or {}
    result = df.copy()
    _require_columns(result, OHLCV_COLUMNS)

    ema_lengths = config.get("ema_lengths", [20, 50])
    for length in ema_lengths:
        result = add_ema(result, int(length))

    macd_config = config.get("macd", {})
    if macd_config is not False:
        result = add_macd(result, **macd_config)

    rsi_config = config.get("rsi", {})
    if rsi_config is not False:
        result = add_rsi(result, **rsi_config)

    atr_config = config.get("atr", {})
    if atr_config is not False:
        result = add_atr(result, **atr_config)

    pivot_config = config.get("pivots", {})
    if pivot_config is not False:
        result = add_pivots(result, **pivot_config)

    waterline_config = config.get("macd_waterline", {})
    if waterline_config is not False:
        result = add_macd_waterline(result, **waterline_config)

    zero_zone_config = config.get("macd_zero_zone", {})
    if zero_zone_config is not False:
        result = add_macd_zero_zone(result, **zero_zone_config)

    return result


def _rma(series: pd.Series, length: int) -> pd.Series:
    """TradingView 风格的 Wilder 均线，用于 RSI 和 ATR。"""

    values = series.astype(float)
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    seed = values.rolling(window=length, min_periods=length).mean()
    first_valid_index = seed.first_valid_index()
    if first_valid_index is None:
        return result

    first_position = values.index.get_loc(first_valid_index)
    result.iloc[first_position] = seed.iloc[first_position]
    alpha = 1.0 / length

    for position in range(first_position + 1, len(values)):
        current = values.iloc[position]
        previous = result.iloc[position - 1]
        if pd.isna(current) or pd.isna(previous):
            result.iloc[position] = np.nan
        else:
            result.iloc[position] = (alpha * current) + ((1.0 - alpha) * previous)

    return result


def _ensure_macd(df: pd.DataFrame) -> pd.DataFrame:
    required = {"macd_line", "macd_signal", "macd_hist"}
    if required.issubset(df.columns):
        return df.copy()
    return add_macd(df)


def _require_columns(df: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")


def _validate_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
