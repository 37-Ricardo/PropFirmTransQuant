from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.registry import create_strategy
from strategy.indicators import add_all_indicators


def make_ohlcv(rows: int = 140) -> pd.DataFrame:
    index = pd.date_range("2026-01-01 09:30:00", periods=rows, freq="1min")
    trend = np.linspace(100.0, 130.0, rows)
    wave = np.sin(np.arange(rows) / 5.0) * 2.0
    close = pd.Series(trend + wave, index=index)
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.5
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.5
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.arange(rows) + 100,
        },
        index=index,
    )


def assert_required_signal_columns(data: pd.DataFrame) -> None:
    assert {"final_long_signal", "final_short_signal", "signal_type"}.issubset(data.columns)


def test_simple_ma_cross_generates_required_signal_columns() -> None:
    strategy = create_strategy("simple_ma_cross")
    signals = strategy.generate_signals(make_ohlcv(), {"fast_len": 5, "slow_len": 20})

    assert_required_signal_columns(signals)
    assert signals["final_long_signal"].dtype == bool
    assert signals["final_short_signal"].dtype == bool
    assert set(signals["signal_type"].unique()).issubset(
        {"", "ma_cross_long", "ma_cross_short"}
    )


def test_macd_rsi_prime_missing_indicators_raises_clear_error() -> None:
    strategy = create_strategy("macd_rsi_prime")

    with pytest.raises(ValueError, match="missing required columns"):
        strategy.generate_signals(make_ohlcv())


def test_macd_rsi_prime_generates_required_signal_columns() -> None:
    strategy = create_strategy("macd_rsi_prime")
    data = add_all_indicators(make_ohlcv(), {})
    signals = strategy.generate_signals(data)

    assert_required_signal_columns(signals)
    assert signals["final_long_signal"].dtype == bool
    assert signals["final_short_signal"].dtype == bool
