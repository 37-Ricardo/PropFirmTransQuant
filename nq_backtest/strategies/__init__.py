"""策略模块。

每个策略建议单独放一个文件，例如：
- `moving_average_cross.py`
- `opening_range_breakout.py`
- `mean_reversion.py`

策略文件只负责根据行情数据生成信号，不负责成交撮合和绩效统计。
这样后续接入不同回测引擎时，策略逻辑可以保持相对独立。
"""

from nq_backtest.strategies.base import BaseStrategy, StrategyContext
from nq_backtest.strategies.moving_average_cross import MovingAverageCrossStrategy

__all__ = ["BaseStrategy", "StrategyContext", "MovingAverageCrossStrategy"]
