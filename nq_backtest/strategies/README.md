# Strategies

这个目录用于保存和调试不同的回测策略。

建议规则：

- 每个策略一个 `.py` 文件；
- 策略类继承 `BaseStrategy`；
- 策略只负责生成信号，不负责撮合、手续费、滑点和绩效统计；
- 输入数据使用项目标准 OHLCV 格式：`open/high/low/close/volume`；
- 输出信号建议包含 `signal` 和 `position`。

## 示例

```python
from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.strategies import MovingAverageCrossStrategy

data = load_nq_1min_csv("examples/sample_nq_1min.csv").frame
strategy = MovingAverageCrossStrategy(fast_window=3, slow_window=8)
signals = strategy.generate_signals(data)

print(signals.tail())
```

## signal / position 约定

`position` 表示策略期望仓位：

- `1`: 多头
- `-1`: 空头
- `0`: 空仓

`signal` 表示当前 K 线发生的仓位变化：

- 正数：仓位增加或转多
- 负数：仓位减少或转空
- `0`: 无变化
