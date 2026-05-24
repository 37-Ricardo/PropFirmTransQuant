from __future__ import annotations

from dataclasses import asdict
from datetime import time
from typing import Any

import pandas as pd

from engine.models import BacktestConfig, Trade


REQUIRED_BACKTEST_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "final_long_signal",
    "final_short_signal",
    "signal_type",
]

TRADE_COLUMNS = [
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
]


class Backtester:
    """通用事件驱动回测器。

    回测器只负责执行交易，不关心策略细节。只要输入 DataFrame 包含
    final_long_signal、final_short_signal 和 signal_type，就可以运行。
    """

    def __init__(self, df: pd.DataFrame, config: BacktestConfig | None = None) -> None:
        self.df = df.copy()
        self.config = config or BacktestConfig()
        self._validate_input()

    def run(self) -> pd.DataFrame:
        """逐根 K 线执行回测，并返回 trades DataFrame。"""

        trades: list[Trade] = []
        position: dict[str, Any] | None = None
        trade_id = 1
        frame = self.df.sort_index()
        timeframe_minutes = self._infer_timeframe_minutes(frame.index)
        close_window = self._select_close_window(timeframe_minutes)

        for bar_number, (timestamp, row) in enumerate(frame.iterrows()):
            if position is not None:
                exit_price, exit_reason = self._get_exit(row, position, timestamp, close_window)
                if exit_reason is not None:
                    trades.append(
                        self._close_trade(
                            trade_id=trade_id,
                            position=position,
                            exit_time=timestamp,
                            exit_price=exit_price,
                            exit_reason=exit_reason,
                            holding_bars=bar_number - int(position["entry_bar"]),
                        )
                    )
                    trade_id += 1
                    position = None

            if position is None and self._can_open_new_position(timestamp, close_window):
                position = self._maybe_open_position(row, timestamp, bar_number)

        if position is not None:
            last_timestamp = frame.index[-1]
            last_close = float(frame.iloc[-1]["close"])
            trades.append(
                self._close_trade(
                    trade_id=trade_id,
                    position=position,
                    exit_time=last_timestamp,
                    exit_price=last_close,
                    exit_reason="end_of_data",
                    holding_bars=len(frame) - 1 - int(position["entry_bar"]),
                )
            )

        return pd.DataFrame([asdict(trade) for trade in trades], columns=TRADE_COLUMNS)

    def _validate_input(self) -> None:
        if not isinstance(self.df, pd.DataFrame):
            raise TypeError("Backtester input must be a pandas DataFrame")
        if not isinstance(self.df.index, pd.DatetimeIndex):
            raise TypeError("Backtester input index must be a pandas DatetimeIndex")

        missing = [column for column in REQUIRED_BACKTEST_COLUMNS if column not in self.df.columns]
        if missing:
            raise ValueError(f"Backtester input is missing required columns: {missing}")

        if self.config.point_value <= 0:
            raise ValueError("point_value must be positive")
        if self.config.contracts <= 0:
            raise ValueError("contracts must be positive")

    def _maybe_open_position(
        self,
        row: pd.Series,
        timestamp: pd.Timestamp,
        bar_number: int,
    ) -> dict[str, Any] | None:
        if bool(row["final_long_signal"]):
            return {
                "direction": "long",
                "signal_type": str(row.get("signal_type", "")),
                "entry_time": timestamp,
                "entry_price": float(row["close"]),
                "entry_bar": bar_number,
            }

        if bool(row["final_short_signal"]) and self.config.allow_short:
            return {
                "direction": "short",
                "signal_type": str(row.get("signal_type", "")),
                "entry_time": timestamp,
                "entry_price": float(row["close"]),
                "entry_bar": bar_number,
            }

        return None

    def _get_exit(
        self,
        row: pd.Series,
        position: dict[str, Any],
        timestamp: pd.Timestamp,
        close_window: tuple[time, time],
    ) -> tuple[float, str | None]:
        direction = str(position["direction"])
        entry_price = float(position["entry_price"])
        stop_points = self.config.stop_dollar / (self.config.point_value * self.config.contracts)
        target_points = self.config.target_dollar / (self.config.point_value * self.config.contracts)

        if direction == "long":
            stop_price = entry_price - stop_points
            target_price = entry_price + target_points
            stop_hit = float(row["low"]) <= stop_price
            target_hit = float(row["high"]) >= target_price
            if stop_hit and target_hit:
                return (stop_price, "stop") if self.config.conservative_same_bar else (target_price, "target")
            if stop_hit:
                return stop_price, "stop"
            if target_hit:
                return target_price, "target"
        else:
            stop_price = entry_price + stop_points
            target_price = entry_price - target_points
            stop_hit = float(row["high"]) >= stop_price
            target_hit = float(row["low"]) <= target_price
            if stop_hit and target_hit:
                return (stop_price, "stop") if self.config.conservative_same_bar else (target_price, "target")
            if stop_hit:
                return stop_price, "stop"
            if target_hit:
                return target_price, "target"

        if self._is_session_close(timestamp, close_window):
            return float(row["close"]), "session_close"

        return float("nan"), None

    def _close_trade(
        self,
        trade_id: int,
        position: dict[str, Any],
        exit_time: pd.Timestamp,
        exit_price: float,
        exit_reason: str,
        holding_bars: int,
    ) -> Trade:
        direction = str(position["direction"])
        entry_price = float(position["entry_price"])
        if direction == "long":
            pnl_points = exit_price - entry_price
        else:
            pnl_points = entry_price - exit_price

        pnl_dollars = pnl_points * self.config.point_value * self.config.contracts
        return Trade(
            trade_id=trade_id,
            direction=direction,
            signal_type=str(position["signal_type"]),
            entry_time=position["entry_time"].to_pydatetime(),
            entry_price=entry_price,
            exit_time=exit_time.to_pydatetime(),
            exit_price=float(exit_price),
            exit_reason=exit_reason,
            pnl_points=float(pnl_points),
            pnl_dollars=float(pnl_dollars),
            holding_bars=int(holding_bars),
        )

    def _infer_timeframe_minutes(self, index: pd.DatetimeIndex) -> float:
        if len(index) < 2:
            return 1.0
        diffs = index.to_series().diff().dropna()
        diffs = diffs[diffs > pd.Timedelta(0)]
        if diffs.empty:
            return 1.0
        return float(diffs.median() / pd.Timedelta(minutes=1))

    def _select_close_window(self, timeframe_minutes: float) -> tuple[time, time]:
        if timeframe_minutes >= 60:
            return self._parse_time_window(self.config.close_session_1h)
        if timeframe_minutes >= 15:
            return self._parse_time_window(self.config.close_session_15m)
        return self._parse_time_window(self.config.close_session_1m_5m)

    def _parse_time_window(self, value: str) -> tuple[time, time]:
        start_text, end_text = value.split("-", maxsplit=1)
        return time.fromisoformat(start_text), time.fromisoformat(end_text)

    def _is_session_close(self, timestamp: pd.Timestamp, close_window: tuple[time, time]) -> bool:
        if timestamp.tzinfo is None:
            local_timestamp = timestamp.tz_localize(self.config.timezone)
        else:
            local_timestamp = timestamp.tz_convert(self.config.timezone)
        current_time = local_timestamp.time()
        start, end = close_window
        return start <= current_time <= end

    def _can_open_new_position(
        self,
        timestamp: pd.Timestamp,
        close_window: tuple[time, time],
    ) -> bool:
        """强平窗口开始后不再开仓，避免产生跨夜持仓。"""

        if timestamp.tzinfo is None:
            local_timestamp = timestamp.tz_localize(self.config.timezone)
        else:
            local_timestamp = timestamp.tz_convert(self.config.timezone)

        current_time = local_timestamp.time()
        close_start, _ = close_window
        reopen_time = time.fromisoformat("18:00")
        return not (close_start <= current_time < reopen_time)
