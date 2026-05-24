from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import BaseStrategy


class SimpleMaCrossStrategy(BaseStrategy):
    """最简单的均线交叉示例策略。

    这个策略用于演示新策略应该如何继承 BaseStrategy、如何读取配置、
    如何输出统一信号列。它不依赖指标模块，内部直接计算均线。
    """

    name = "simple_ma_cross"
    description = "简单均线交叉示例策略"
    required_columns = ["close"]
    default_config: dict[str, Any] = {
        "fast_len": 20,
        "slow_len": 60,
    }

    def generate_signals(
        self,
        df: pd.DataFrame,
        config: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        runtime_config = self.merge_config(config)
        self.config = runtime_config
        self.validate_data(df)

        # 读取并校验均线参数。
        fast_len = int(runtime_config["fast_len"])
        slow_len = int(runtime_config["slow_len"])
        if fast_len <= 0 or slow_len <= 0:
            raise ValueError("fast_len and slow_len must be positive")
        if fast_len >= slow_len:
            raise ValueError("fast_len must be smaller than slow_len")

        result = df.copy()
        # 示例策略内部直接计算简单移动平均线，不依赖外部指标列。
        result["fast_ma"] = result["close"].rolling(window=fast_len, min_periods=fast_len).mean()
        result["slow_ma"] = result["close"].rolling(window=slow_len, min_periods=slow_len).mean()

        # 上穿生成多头信号，下穿生成空头信号。
        fast_above = result["fast_ma"] > result["slow_ma"]
        fast_above_previous = result["fast_ma"].shift(1) > result["slow_ma"].shift(1)
        result["final_long_signal"] = fast_above & ~fast_above_previous.fillna(False)
        result["final_short_signal"] = ~fast_above & fast_above_previous.fillna(False)
        result["signal_type"] = ""
        result.loc[result["final_long_signal"], "signal_type"] = "ma_cross_long"
        result.loc[result["final_short_signal"], "signal_type"] = "ma_cross_short"

        self.validate_signals(result)
        return result
