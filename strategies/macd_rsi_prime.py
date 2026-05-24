from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import BaseStrategy


class MacdRsiPrimeStrategy(BaseStrategy):
    """NQ MACD+RSI 1买2买精选周频补足策略。

    策略只负责根据已有指标列生成信号，不读取文件、不导出报表、
    不执行回测。输入 DataFrame 默认已经由指标模块补齐所需指标列。
    """

    name = "macd_rsi_prime"
    description = "NQ MACD+RSI 1买2买精选周频补足策略"
    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "macd_waterline",
        "macd_zero_zone_upper",
        "macd_zero_zone_lower",
        "macd_in_zero_zone",
        "rsi",
        "atr",
        "pivot_low",
        "ema_20",
        "ema_50",
    ]
    default_config: dict[str, Any] = {
        "rsi_mid": 50.0,
        "rsi_recover_level": 45.0,
        "rsi_near_mid_low": 45.0,
        "rsi_near_mid_high": 58.0,
        "atr_min": 0.0,
        "atr_max": None,
        "divergence_lookback": 20,
        "trend_fast_col": "ema_20",
        "trend_slow_col": "ema_50",
        "chase_lookback": 20,
        "max_close_extension_atr": 1.5,
        "min_volume": 0,
    }

    def validate_data(self, df: pd.DataFrame) -> None:
        """检查固定依赖列和配置中指定的动态趋势列。"""

        config = self.config
        dynamic_columns = [
            str(config["trend_fast_col"]),
            str(config["trend_slow_col"]),
        ]
        original_required = self.required_columns
        try:
            self.required_columns = sorted(set([*original_required, *dynamic_columns]))
            super().validate_data(df)
        finally:
            self.required_columns = original_required

    def generate_signals(
        self,
        df: pd.DataFrame,
        config: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        runtime_config = self.merge_config(config)
        self.config = runtime_config
        self.validate_data(df)

        result = df.copy()

        # 读取配置。后续判断只使用当前 K 线和历史 K 线数据，避免未来函数。
        rsi_mid = float(runtime_config["rsi_mid"])
        rsi_recover_level = float(runtime_config["rsi_recover_level"])
        divergence_lookback = int(runtime_config["divergence_lookback"])
        chase_lookback = int(runtime_config["chase_lookback"])
        max_close_extension_atr = float(runtime_config["max_close_extension_atr"])
        trend_fast_col = str(runtime_config["trend_fast_col"])
        trend_slow_col = str(runtime_config["trend_slow_col"])

        # 第一类买点：MACD 水线向上、柱体转强、RSI 上穿中轴。
        result["water_up"] = result["macd_waterline"] > result["macd_waterline"].shift(1)
        result["macd_bull_turn"] = (result["macd_hist"] > result["macd_hist"].shift(1)) & (
            result["macd_hist"].shift(1) <= result["macd_hist"].shift(2)
        )
        result["rsi_cross_up_mid"] = (result["rsi"] > rsi_mid) & (result["rsi"].shift(1) <= rsi_mid)
        result["rsi_recover"] = (result["rsi"] > rsi_recover_level) & (
            result["rsi"] > result["rsi"].shift(1)
        )

        # pivot_low 已由指标模块写在确认 K 线上，这里的 rolling 不会回看未来。
        result["recent_bull_div"] = result["pivot_low"].notna().rolling(
            window=divergence_lookback,
            min_periods=1,
        ).max().astype(bool)
        result["trend_up"] = result[trend_fast_col] > result[trend_slow_col]

        # 第二类买点：近期触及零轴区域后，MACD 恢复健康状态。
        result["macd_touched_zero_long"] = result["macd_in_zero_zone"].rolling(
            window=divergence_lookback,
            min_periods=1,
        ).max().astype(bool)
        result["macd_healthy_long"] = (result["macd_line"] > result["macd_signal"]) & (
            result["macd_hist"] >= 0
        )
        result["rsi_near_mid"] = result["rsi"].between(
            float(runtime_config["rsi_near_mid_low"]),
            float(runtime_config["rsi_near_mid_high"]),
            inclusive="both",
        )
        result["price_regain_long"] = result["close"] > result["close"].rolling(
            window=divergence_lookback,
            min_periods=1,
        ).mean()
        result["valid_second_state"] = (
            result["macd_touched_zero_long"] & result["macd_healthy_long"] & result["rsi_near_mid"]
        )
        result["htf_bull_ok"] = result["trend_up"]

        # 风控过滤：波动率、追高距离和成交量过滤。
        atr_ok = result["atr"] >= float(runtime_config["atr_min"])
        if runtime_config["atr_max"] is not None:
            atr_ok &= result["atr"] <= float(runtime_config["atr_max"])
        result["atr_ok"] = atr_ok

        rolling_low = result["low"].rolling(window=chase_lookback, min_periods=1).min()
        extension = result["close"] - rolling_low
        result["long_not_chasing"] = extension <= (result["atr"] * max_close_extension_atr)
        result["liquidity_long_ok"] = result["volume"] >= float(runtime_config["min_volume"])

        # 汇总严格 1 买、严格 2 买和周频补足信号。
        result["buy1_strict"] = (
            result["water_up"]
            & result["macd_bull_turn"]
            & result["rsi_cross_up_mid"]
            & result["trend_up"]
            & result["atr_ok"]
            & result["long_not_chasing"]
            & result["liquidity_long_ok"]
        )
        result["buy2_strict"] = (
            result["valid_second_state"]
            & result["rsi_recover"]
            & result["price_regain_long"]
            & result["htf_bull_ok"]
            & result["atr_ok"]
            & result["long_not_chasing"]
            & result["liquidity_long_ok"]
        )
        result["prime_long_signal"] = result["buy1_strict"] | result["buy2_strict"]
        result["weekly_fill_signal"] = result["recent_bull_div"] & result["valid_second_state"]
        result["final_long_signal"] = result["prime_long_signal"] | result["weekly_fill_signal"]

        # 当前阶段只实现做多信号，做空接口先保留。
        result["final_short_signal"] = False
        result["signal_type"] = ""
        result.loc[result["buy1_strict"], "signal_type"] = "buy1_strict"
        result.loc[result["buy2_strict"], "signal_type"] = "buy2_strict"
        result.loc[
            result["weekly_fill_signal"] & (result["signal_type"] == ""),
            "signal_type",
        ] = "weekly_fill_signal"

        self.validate_signals(result)
        return result


KEY_SIGNAL_COLUMNS = [
    "water_up",
    "macd_bull_turn",
    "rsi_cross_up_mid",
    "rsi_recover",
    "recent_bull_div",
    "trend_up",
    "macd_touched_zero_long",
    "macd_healthy_long",
    "rsi_near_mid",
    "price_regain_long",
    "valid_second_state",
    "htf_bull_ok",
    "atr_ok",
    "long_not_chasing",
    "liquidity_long_ok",
    "buy1_strict",
    "buy2_strict",
    "prime_long_signal",
    "weekly_fill_signal",
    "final_long_signal",
    "final_short_signal",
    "signal_type",
]
