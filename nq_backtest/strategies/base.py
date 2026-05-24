from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategyContext:
    """策略运行上下文。

    这里放一些策略运行时会用到、但不属于行情数据本身的参数。
    第一阶段只保留最基本字段，后续可以继续加入：
    - 合约乘数；
    - 手续费；
    - 滑点；
    - 交易时段；
    - 单笔最大风险等。
    """

    symbol: str = "NQ"
    timeframe: str = "1min"
    timezone: str = "America/New_York"


class BaseStrategy(ABC):
    """所有策略的基类。

    约定：
    - 输入是带 datetime 索引的 OHLCV DataFrame；
    - 输出是与输入索引对齐的信号 DataFrame；
    - 策略只生成信号，不在这里做资金曲线、下单撮合和绩效统计。
    """

    name: str = "base_strategy"
    required_columns: tuple[str, ...] = ("open", "high", "low", "close", "volume")

    def __init__(self, context: StrategyContext | None = None) -> None:
        self.context = context or StrategyContext()

    def validate_input(self, data: pd.DataFrame) -> None:
        """检查策略输入数据是否满足最低要求。"""

        missing = [column for column in self.required_columns if column not in data.columns]
        if missing:
            raise ValueError(f"Strategy input is missing required columns: {missing}")
        if not isinstance(data.index, pd.DatetimeIndex):
            raise TypeError("Strategy input index must be a pandas DatetimeIndex")

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """根据行情数据生成策略信号。

        建议输出字段：
        - signal: 当前 K 线产生的交易动作，1=做多，-1=做空，0=无动作；
        - position: 当前策略期望持仓，1=多头，-1=空头，0=空仓。
        """
