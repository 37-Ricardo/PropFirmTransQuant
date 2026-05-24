# AGENTS.md

## Project Goal

本项目目标是开发一个本地 NQ 期货策略回测系统，用于读取、清洗、重采样、验证 NQ 行情数据，并逐步实现可扩展的策略研究、事件驱动回测、交易记录和绩效分析能力。

## Tech Stack

项目使用以下技术栈：

- Python 3.11
- pandas
- numpy
- openpyxl
- matplotlib

## Backtest Architecture

- 不使用 `backtrader` / `vectorbt`。
- 优先实现自研事件驱动回测框架。
- 回测流程应尽量贴近真实交易顺序：行情推进、信号计算、订单生成、成交模拟、持仓更新、权益统计。
- 回测逻辑必须尽量复刻 TradingView PineScript 的行为，尤其是 K 线收盘确认、信号触发、持仓切换、止盈止损、时间过滤等细节。
- 禁止引入未来函数。任何策略信号、指标、过滤条件都只能使用当前 K 线及历史 K 线已经确认的数据。

## Timezone Rules

- 项目内部统一使用 `America/New_York`。
- 供应商 NQ 1min 数据已按 `America/New_York` 解析和验证。
- TradingView 导出的带时区数据也统一转换到 `America/New_York` 后再比较或使用。
- 新增数据读取、重采样、回测、统计模块时，都必须明确时间索引的时区假设。

## Code Organization

- 不要把所有代码堆到 `main.py`。
- `main.py` 只作为命令行入口，负责解析参数、串联模块和输出结果。
- 每个模块职责必须清晰，避免一个文件同时承担数据读取、策略逻辑、撮合、统计和展示等多种职责。
- 新功能应优先放入合适的包或模块中，例如：
  - `nq_backtest/data_loader.py`: 数据读取与标准化
  - `nq_backtest/resample.py`: OHLCV 重采样
  - `nq_backtest/quality.py`: 数据质量检查
  - `nq_backtest/strategies/`: 策略定义与调试
  - 后续可新增 `engine/`, `broker/`, `orders/`, `portfolio/`, `metrics/`, `plots/` 等模块

## Development Rules

- 修改代码后，必须告诉用户修改了哪些文件。
- 每次修改后，必须提供运行命令和验证方式。
- 不要无关重构，不要顺手改动与当前任务无关的文件。
- 不要覆盖原始行情数据。清洗、补齐、派生数据应输出到 `data/processed/` 或其他明确的派生目录。
- 原始数据、补齐数据、报告数据应保持可追溯。
- 如果新增依赖，必须更新 `requirements.txt`，并说明为什么需要。

## Strategy Rules

- 策略逻辑应独立于数据读取、撮合和绩效统计。
- 策略输入应使用标准 OHLCV 格式：`open/high/low/close/volume`。
- 策略输出应尽量使用明确字段，例如 `signal`, `position`, `entry_price`, `exit_reason`。
- 策略计算不得使用未来数据，例如：
  - 不允许使用未来 K 线的 high/low/close 判断当前入场；
  - 不允许用完整区间最大值/最小值决定过去某一根 K 线的信号；
  - 不允许在当前 K 线未收盘前使用收盘后才知道的数据，除非明确模拟 TradingView 的 intrabar 行为。

## Multi-Strategy Framework Rules

- 所有新策略必须放在 `strategies/` 目录。
- 每个策略必须继承 `BaseStrategy`。
- 每个策略必须定义：
  - `name`
  - `description`
  - `required_columns`
  - `default_config`
- 每个策略必须实现：
  - `generate_signals(df, config=None)`
- 策略不得读取文件。
- 策略不得导出报表。
- 策略不得执行回测。
- 策略只负责生成以下信号列：
  - `final_long_signal`
  - `final_short_signal`
  - `signal_type`
- 新增策略后必须在 `strategies/registry.py` 注册。
- 新增策略必须配套测试。

## Validation Expectations

- 每次功能修改后，应提供至少一种可运行验证方式。
- 数据相关修改应验证：
  - datetime 时区
  - OHLCV 字段
  - 重复时间戳
  - OHLC 逻辑
  - tick size
  - 缺口和补齐规则
- 回测相关修改应验证：
  - 信号是否无未来函数
  - 订单和成交顺序是否符合设计
  - 持仓变化是否可追溯
  - 与 TradingView/PineScript 结果的关键字段是否尽量一致
