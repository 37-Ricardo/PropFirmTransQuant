from __future__ import annotations

import pandas as pd
import pytest

from strategies.base import BaseStrategy


class DummyStrategy(BaseStrategy):
    name = "dummy"
    description = "Dummy strategy for base tests"
    required_columns = ["close", "missing_col"]
    default_config = {}

    def generate_signals(self, df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
        self.validate_data(df)
        result = df.copy()
        result["final_long_signal"] = False
        result["final_short_signal"] = False
        result["signal_type"] = ""
        return result


def test_base_strategy_missing_required_columns_raises_clear_error() -> None:
    strategy = DummyStrategy()
    data = pd.DataFrame({"close": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="missing required columns"):
        strategy.validate_data(data)
