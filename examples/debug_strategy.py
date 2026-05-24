from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.strategies import MovingAverageCrossStrategy


def main() -> None:
    """快速调试示例策略。

    这个脚本不会做完整回测，只用于确认：
    - 数据能正常读取；
    - 策略类能正常导入；
    - 策略能基于行情生成信号表。
    """

    data = load_nq_1min_csv("examples/sample_nq_1min.csv").frame
    strategy = MovingAverageCrossStrategy(fast_window=3, slow_window=8)
    signals = strategy.generate_signals(data)

    print(f"Strategy: {strategy.name}")
    print(signals.tail(10))


if __name__ == "__main__":
    main()
