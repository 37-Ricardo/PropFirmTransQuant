from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from engine import BacktestConfig, Backtester
from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.quality import build_quality_report, save_quality_report
from nq_backtest.resample import resample_ohlcv
from reports.export_trades import export_trades_to_excel
from strategies.macd_rsi_prime import KEY_SIGNAL_COLUMNS
from strategies.registry import create_strategy, list_strategies
from strategy.indicators import add_all_indicators


BASIC_SIGNAL_EXPORT_COLUMNS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "final_long_signal",
    "final_short_signal",
    "signal_type",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NQ local data validation, indicator calculation, and strategy signal checks."
    )
    parser.add_argument("--csv", type=Path, help="Path to NQ CSV file.")
    parser.add_argument(
        "--input-timeframe",
        choices=("1min", "5min", "15min", "60min", "1h"),
        default="1min",
        help="Timeframe of the input CSV. Used by data quality gap checks.",
    )
    parser.add_argument(
        "--timeframe",
        choices=("5min", "15min", "60min", "1h"),
        default=None,
        help="Optional target resample timeframe.",
    )
    parser.add_argument(
        "--input-tz",
        default="America/New_York",
        help="Timezone for naive CSV timestamps.",
    )
    parser.add_argument(
        "--datetime-column",
        default=None,
        help="Optional datetime column name. If omitted, common names are auto-detected.",
    )
    parser.add_argument(
        "--output-dir",
        default=Path("output"),
        type=Path,
        help="Directory for cleaned data, resampled data, and quality reports.",
    )
    parser.add_argument(
        "--indicator-check",
        action="store_true",
        help="Calculate strategy indicators and export reports/indicator_check.xlsx.",
    )
    parser.add_argument(
        "--strategy",
        default="macd_rsi_prime",
        help="Strategy name to run. Defaults to macd_rsi_prime.",
    )
    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="Print registered strategies and exit.",
    )
    parser.add_argument(
        "--export-signals",
        action="store_true",
        help="Generate strategy signals and export reports/signal_check.xlsx.",
    )
    parser.add_argument(
        "--run-backtest",
        action="store_true",
        help="Run event-driven backtest and export reports/trades.xlsx.",
    )
    parser.add_argument("--stop-dollar", type=float, default=1900.0, help="Stop loss dollars per trade.")
    parser.add_argument("--target-dollar", type=float, default=3100.0, help="Target dollars per trade.")
    parser.add_argument("--contracts", type=int, default=1, help="Number of contracts.")
    parser.add_argument("--point-value", type=float, default=20.0, help="Dollar value per NQ point.")
    parser.add_argument("--allow-short", action="store_true", help="Allow short trades.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_strategies:
        print("Available strategies")
        for item in list_strategies():
            print(f"- {item['name']}: {item['description']}")
        return

    if args.csv is None:
        raise SystemExit("--csv is required unless --list-strategies is used.")

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_nq_1min_csv(
        csv_path=args.csv,
        input_timezone=args.input_tz,
        datetime_column=args.datetime_column,
    )
    report = build_quality_report(data.frame, expected_interval=args.input_timeframe)
    cleaned = data.frame[~data.frame.index.duplicated(keep="last")].sort_index()

    if args.indicator_check:
        indicators = add_all_indicators(cleaned, {})
        indicator_path = Path("reports") / "indicator_check.xlsx"
        export_indicator_report(indicators, indicator_path)

        print("Indicator check report")
        print(f"- CSV: {args.csv}")
        print(f"- Rows: {len(indicators)}")
        print(f"- Columns: {list(indicators.columns)}")
        print(f"- Excel report: {indicator_path}")
        return

    strategy_frame = resample_ohlcv(cleaned, args.timeframe) if args.timeframe else cleaned
    indicators = add_all_indicators(strategy_frame, {})
    strategy = create_strategy(args.strategy)
    signals = strategy.generate_signals(indicators)

    if args.export_signals:
        signal_path = Path("reports") / "signal_check.xlsx"
        export_signal_report(signals, signal_path, strategy_name=strategy.name)
        print("Signal check report")
        print(f"- Strategy: {strategy.name}")
        print(f"- CSV: {args.csv}")
        print(f"- Rows: {len(signals)}")
        print(f"- Long signals: {int(signals['final_long_signal'].sum())}")
        print(f"- Short signals: {int(signals['final_short_signal'].sum())}")
        print(f"- Excel report: {signal_path}")
        return

    if args.run_backtest:
        config = BacktestConfig(
            point_value=args.point_value,
            contracts=args.contracts,
            stop_dollar=args.stop_dollar,
            target_dollar=args.target_dollar,
            allow_short=args.allow_short,
        )
        trades = Backtester(signals, config).run()
        trades_path = Path("reports") / "trades.xlsx"
        export_trades_to_excel(trades, trades_path)
        print_backtest_summary(trades)
        print(f"- Strategy: {strategy.name}")
        print(f"- Trades Excel: {trades_path}")
        return

    target_timeframe = args.timeframe or "5min"
    resampled = resample_ohlcv(cleaned, target_timeframe)
    cleaned_path = output_dir / f"cleaned_{args.input_timeframe}.csv"
    resampled_path = output_dir / f"resampled_{target_timeframe}.csv"
    report_json_path = output_dir / "data_quality_report.json"
    report_xlsx_path = output_dir / "data_quality_report.xlsx"

    cleaned.to_csv(cleaned_path, index_label="datetime")
    resampled.to_csv(resampled_path, index_label="datetime")
    save_quality_report(report, report_json_path, report_xlsx_path)

    print("Data quality report")
    print(f"- CSV: {args.csv}")
    print(f"- Input timeframe: {args.input_timeframe}")
    print("- Timezone: America/New_York")
    print(f"- Loaded rows: {report.row_count}")
    print(f"- Cleaned rows: {len(cleaned)}")
    print(f"- Resampled rows ({target_timeframe}): {len(resampled)}")
    print(f"- Strategy checked: {strategy.name}")
    print(f"- Long signals: {int(signals['final_long_signal'].sum())}")
    print(f"- Short signals: {int(signals['final_short_signal'].sum())}")
    print(f"- Date range: {report.start_datetime} -> {report.end_datetime}")
    print(f"- Duplicate datetimes: {report.duplicate_datetime_count}")
    print(f"- Suspicious gap count: {report.gap_count}")
    print(f"- Expected session gap count: {report.expected_gap_count}")
    print(f"- Total time gap count: {report.total_gap_count}")
    print(f"- Invalid OHLC rows: {report.invalid_ohlc_count}")
    print(f"- Non-positive volume rows: {report.non_positive_volume_count}")
    print(f"- Null counts: {report.null_counts}")
    print(f"- Cleaned CSV: {cleaned_path}")
    print(f"- Resampled CSV: {resampled_path}")
    print(f"- JSON report: {report_json_path}")
    print(f"- Excel report: {report_xlsx_path}")


def export_indicator_report(indicators: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    export_frame = with_datetime_column(indicators)
    summary = (
        export_frame.drop(columns=["datetime"])
        .describe(include="all")
        .transpose()
        .reset_index(names="column")
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        export_frame.to_excel(writer, sheet_name="indicators", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)


def export_signal_report(signals: pd.DataFrame, path: Path, strategy_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    export_frame = with_datetime_column(signals)
    columns = [column for column in BASIC_SIGNAL_EXPORT_COLUMNS if column in export_frame.columns]
    if strategy_name == "macd_rsi_prime":
        columns.extend(
            column for column in KEY_SIGNAL_COLUMNS if column in export_frame.columns and column not in columns
        )
    else:
        columns.extend(
            column
            for column in ["fast_ma", "slow_ma"]
            if column in export_frame.columns and column not in columns
        )

    summary = pd.DataFrame(
        [
            {
                "strategy": strategy_name,
                "rows": len(signals),
                "long_signals": int(signals["final_long_signal"].sum()),
                "short_signals": int(signals["final_short_signal"].sum()),
            }
        ]
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        export_frame[columns].to_excel(writer, sheet_name="signals", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)


def print_backtest_summary(trades: pd.DataFrame) -> None:
    total_trades = len(trades)
    winning_trades = int((trades["pnl_dollars"] > 0).sum()) if total_trades else 0
    losing_trades = int((trades["pnl_dollars"] < 0).sum()) if total_trades else 0
    win_rate = (winning_trades / total_trades * 100.0) if total_trades else 0.0
    total_pnl = float(trades["pnl_dollars"].sum()) if total_trades else 0.0
    average_pnl = float(trades["pnl_dollars"].mean()) if total_trades else 0.0
    max_profit = float(trades["pnl_dollars"].max()) if total_trades else 0.0
    max_loss = float(trades["pnl_dollars"].min()) if total_trades else 0.0

    print("Backtest summary")
    print(f"- Total trades: {total_trades}")
    print(f"- Winning trades: {winning_trades}")
    print(f"- Losing trades: {losing_trades}")
    print(f"- Win rate: {win_rate:.2f}%")
    print(f"- Total PnL: {total_pnl:.2f}")
    print(f"- Average PnL: {average_pnl:.2f}")
    print(f"- Max profit: {max_profit:.2f}")
    print(f"- Max loss: {max_loss:.2f}")


def with_datetime_column(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if isinstance(result.index, pd.DatetimeIndex):
        datetime_values = result.index
        if datetime_values.tz is not None:
            datetime_values = datetime_values.tz_localize(None)
        result.insert(0, "datetime", datetime_values)
    else:
        result.insert(0, "datetime", result.index)
    return result


if __name__ == "__main__":
    main()
