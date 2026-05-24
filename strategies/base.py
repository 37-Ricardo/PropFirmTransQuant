from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

import pandas as pd


REQUIRED_SIGNAL_COLUMNS = ["final_long_signal", "final_short_signal", "signal_type"]


class BaseStrategy(ABC):
    """所有策略的统一基类。

    策略只负责根据已经准备好的 DataFrame 生成信号列，不读取文件、
    不导出报表，也不执行回测。
    """

    name: str = ""
    description: str = ""
    required_columns: list[str] = []
    default_config: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = self.merge_config(config)

    def merge_config(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = deepcopy(self.default_config)
        if config:
            merged.update(config)
        return merged

    def validate_data(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("Strategy input must be a pandas DataFrame")

        missing = [column for column in self.required_columns if column not in df.columns]
        if missing:
            raise ValueError(
                f"Strategy '{self.name}' is missing required columns: {missing}. "
                "Run the required indicator pipeline before generating signals."
            )

    def validate_signals(self, df: pd.DataFrame) -> None:
        missing = [column for column in REQUIRED_SIGNAL_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"Strategy '{self.name}' did not output signal columns: {missing}")

    @abstractmethod
    def generate_signals(
        self,
        df: pd.DataFrame,
        config: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """返回包含 final_long_signal、final_short_signal、signal_type 的 DataFrame。"""
