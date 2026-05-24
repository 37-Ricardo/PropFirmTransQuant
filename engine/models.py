from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BacktestConfig:
    """事件驱动回测配置。

    当前配置以 NQ 为默认品种：1 点 = 20 美元，默认 1 手。
    stop_dollar / target_dollar 会按 point_value 和 contracts 换算成点数。
    """

    point_value: float = 20.0
    contracts: int = 1
    stop_dollar: float = 1900.0
    target_dollar: float = 3100.0
    allow_short: bool = False
    process_orders_on_close: bool = True
    conservative_same_bar: bool = True
    close_session_1m_5m: str = "15:55-16:00"
    close_session_15m: str = "15:45-16:00"
    close_session_1h: str = "15:00-16:00"
    timezone: str = "America/New_York"


@dataclass(frozen=True)
class Trade:
    """单笔交易记录。"""

    trade_id: int
    direction: str
    signal_type: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_points: float
    pnl_dollars: float
    holding_bars: int
