from __future__ import annotations

import pandas as pd

from engine import BacktestConfig, Backtester


def make_signal_frame(rows: list[dict]) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp(row.pop("datetime"), tz="America/New_York") for row in rows]
    )
    frame = pd.DataFrame(rows, index=index)
    defaults = {
        "final_long_signal": False,
        "final_short_signal": False,
        "signal_type": "",
    }
    for column, value in defaults.items():
        if column not in frame.columns:
            frame[column] = value
        frame[column] = frame[column].fillna(value)
    return frame


def base_config(**overrides) -> BacktestConfig:
    values = {
        "point_value": 1.0,
        "contracts": 1,
        "stop_dollar": 2.0,
        "target_dollar": 3.0,
    }
    values.update(overrides)
    return BacktestConfig(**values)


def test_long_signal_generates_trade() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "final_long_signal": True,
                "signal_type": "test_long",
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 101, "low": 99, "close": 100},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert len(trades) == 1
    assert trades.iloc[0]["direction"] == "long"
    assert trades.iloc[0]["exit_reason"] == "end_of_data"


def test_long_target_exit_reason() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 103.25, "low": 100, "close": 102},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert trades.iloc[0]["exit_reason"] == "target"
    assert trades.iloc[0]["exit_price"] == 103.0


def test_long_stop_exit_reason() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 101, "low": 97.75, "close": 99},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert trades.iloc[0]["exit_reason"] == "stop"
    assert trades.iloc[0]["exit_price"] == 98.0


def test_same_bar_target_and_stop_uses_conservative_stop() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 104, "low": 97, "close": 101},
        ]
    )

    trades = Backtester(frame, base_config(conservative_same_bar=True)).run()

    assert trades.iloc[0]["exit_reason"] == "stop"
    assert trades.iloc[0]["exit_price"] == 98.0


def test_session_close_exit_reason() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 15:54",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 15:55", "open": 100, "high": 101, "low": 99, "close": 100.5},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert trades.iloc[0]["exit_reason"] == "session_close"
    assert trades.iloc[0]["exit_price"] == 100.5


def test_no_new_entry_after_session_close_window_starts() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 16:30",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 16:31", "open": 100, "high": 101, "low": 99, "close": 100},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert trades.empty


def test_trades_dataframe_contains_required_columns() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_long_signal": True,
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 101, "low": 99, "close": 100},
        ]
    )

    trades = Backtester(frame, base_config()).run()

    assert {
        "trade_id",
        "direction",
        "signal_type",
        "entry_time",
        "entry_price",
        "exit_time",
        "exit_price",
        "exit_reason",
        "pnl_points",
        "pnl_dollars",
        "holding_bars",
    }.issubset(trades.columns)


def test_allow_short_false_ignores_short_signal() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_short_signal": True,
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 101, "low": 97, "close": 99},
        ]
    )

    trades = Backtester(frame, base_config(allow_short=False)).run()

    assert trades.empty


def test_allow_short_true_generates_short_trade() -> None:
    frame = make_signal_frame(
        [
            {
                "datetime": "2026-01-02 10:00",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "final_short_signal": True,
                "signal_type": "test_short",
            },
            {"datetime": "2026-01-02 10:01", "open": 100, "high": 101, "low": 96.75, "close": 98},
        ]
    )

    trades = Backtester(frame, base_config(allow_short=True)).run()

    assert len(trades) == 1
    assert trades.iloc[0]["direction"] == "short"
    assert trades.iloc[0]["exit_reason"] == "target"
    assert trades.iloc[0]["exit_price"] == 97.0
