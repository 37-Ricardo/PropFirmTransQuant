from __future__ import annotations

import numpy as np
import pandas as pd

from nq_backtest.strategies.base import BaseStrategy, StrategyContext


class MovingAverageCrossStrategy(BaseStrategy):
    """简单均线交叉示例策略。

    这个策略主要用于演示策略文件的写法，不代表可直接实盘使用：
    - 快均线上穿慢均线：期望持有多头；
    - 快均线下穿慢均线：期望持有空头；
    - 均线未形成前：空仓。
    """

    name = "moving_average_cross"

    def __init__(
        self,
        fast_window: int = 5,
        slow_window: int = 20,
        context: StrategyContext | None = None,
    ) -> None:
        super().__init__(context=context)
        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("MA windows must be positive integers")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

        self.fast_window = fast_window
        self.slow_window = slow_window

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(data)

        signals = pd.DataFrame(index=data.index)
        signals["close"] = data["close"]
        signals["fast_ma"] = data["close"].rolling(self.fast_window).mean()
        signals["slow_ma"] = data["close"].rolling(self.slow_window).mean()

        # position 是策略“希望持有什么仓位”，不是成交后的真实持仓。
        signals["position"] = np.where(
            signals["fast_ma"] > signals["slow_ma"],
            1,
            np.where(signals["fast_ma"] < signals["slow_ma"], -1, 0),
        )

        # signal 只在 position 发生变化时出现，方便后续回测模块识别开平仓动作。
        signals["signal"] = signals["position"].diff().fillna(0)
        signals.loc[signals["fast_ma"].isna() | signals["slow_ma"].isna(), ["position", "signal"]] = 0

        return signals
