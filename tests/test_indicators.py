from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.indicators import (
    add_all_indicators,
    add_atr,
    add_ema,
    add_macd,
    add_pivots,
    add_rsi,
)


def make_ohlcv(rows: int = 120) -> pd.DataFrame:
    index = pd.date_range("2026-01-01 09:30:00", periods=rows, freq="1min")
    base = pd.Series(np.linspace(100.0, 130.0, rows), index=index)
    wave = pd.Series(np.sin(np.arange(rows) / 4.0), index=index)
    close = base + wave
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) + 1.0
    low = pd.concat([open_, close], axis=1).min(axis=1) - 1.0

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.arange(rows) + 1,
        },
        index=index,
    )


def test_ema_not_empty() -> None:
    result = add_ema(make_ohlcv(), 20)
    assert "ema_20" in result.columns
    assert result["ema_20"].notna().any()


def test_macd_columns_exist() -> None:
    result = add_macd(make_ohlcv())
    assert {"macd_line", "macd_signal", "macd_hist"}.issubset(result.columns)


def test_rsi_range_is_0_to_100() -> None:
    result = add_rsi(make_ohlcv(), length=14)
    valid_rsi = result["rsi"].dropna()
    assert not valid_rsi.empty
    assert valid_rsi.between(0, 100).all()


def test_atr_is_non_negative() -> None:
    result = add_atr(make_ohlcv(), length=14)
    valid_atr = result["atr"].dropna()
    assert not valid_atr.empty
    assert (valid_atr >= 0).all()


def test_pivot_columns_exist() -> None:
    result = add_pivots(make_ohlcv(), left=3, right=3)
    assert {"pivot_high", "pivot_low"}.issubset(result.columns)


def test_add_all_indicators_preserves_ohlcv_columns() -> None:
    source = make_ohlcv()
    result = add_all_indicators(source, {"ema_lengths": [10]})
    for column in ["open", "high", "low", "close", "volume"]:
        assert column in result.columns
        pd.testing.assert_series_equal(result[column], source[column])
