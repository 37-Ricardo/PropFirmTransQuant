from __future__ import annotations

import argparse
from pathlib import Path

from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.quality import build_quality_report, save_quality_report
from nq_backtest.resample import resample_ohlcv


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    第一阶段只做数据入口，所以参数集中在：
    - 输入 CSV 路径；
    - 原始时间戳所属时区；
    - 目标重采样周期；
    - 输出目录。
    """
    parser = argparse.ArgumentParser(
        description="Load NQ 1min CSV data, validate it, convert timezone, and resample."
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Path to NQ 1min CSV file.",
    )
    parser.add_argument(
        "--timeframe",
        choices=("5min", "15min"),
        default="5min",
        help="Target resample timeframe.",
    )
    parser.add_argument(
        "--input-tz",
        default="America/New_York",
        help="Timezone for naive CSV timestamps. Use UTC if the CSV timestamps are UTC.",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 所有运行产物都放到 output_dir，避免污染原始数据目录。
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # 读取 CSV 后会完成三件事：
    # 1. 识别并统一字段名；
    # 2. 将 datetime 转成 America/New_York；
    # 3. 将 OHLCV 转成数值类型，非法值保留为 NaN 供质量报告发现。
    data = load_nq_1min_csv(
        csv_path=args.csv,
        input_timezone=args.input_tz,
        datetime_column=args.datetime_column,
    )

    # 质量报告基于“标准化后的原始数据”生成。
    # 注意：这里先不去重，这样报告才能真实反映重复时间戳问题。
    report = build_quality_report(data.frame)

    # 回测和重采样需要唯一时间索引。重复时间戳保留最后一条，
    # 这是行情 CSV 里较常见的修正记录处理方式。
    cleaned = data.frame[~data.frame.index.duplicated(keep="last")].sort_index()
    resampled = resample_ohlcv(cleaned, args.timeframe)

    cleaned_path = output_dir / "cleaned_1min.csv"
    resampled_path = output_dir / f"resampled_{args.timeframe}.csv"
    report_json_path = output_dir / "data_quality_report.json"
    report_xlsx_path = output_dir / "data_quality_report.xlsx"

    cleaned.to_csv(cleaned_path, index_label="datetime")
    resampled.to_csv(resampled_path, index_label="datetime")
    save_quality_report(report, report_json_path, report_xlsx_path)

    # 命令行输出只放最关键信息；完整明细看 JSON / Excel 报告。
    print("Data quality report")
    print(f"- CSV: {args.csv}")
    print(f"- Timezone: America/New_York")
    print(f"- Loaded rows: {report.row_count}")
    print(f"- Cleaned rows: {len(cleaned)}")
    print(f"- Resampled rows ({args.timeframe}): {len(resampled)}")
    print(f"- Date range: {report.start_datetime} -> {report.end_datetime}")
    print(f"- Duplicate datetimes: {report.duplicate_datetime_count}")
    print(f"- Gap count: {report.gap_count}")
    print(f"- Invalid OHLC rows: {report.invalid_ohlc_count}")
    print(f"- Non-positive volume rows: {report.non_positive_volume_count}")
    print(f"- Null counts: {report.null_counts}")
    print(f"- Cleaned CSV: {cleaned_path}")
    print(f"- Resampled CSV: {resampled_path}")
    print(f"- JSON report: {report_json_path}")
    print(f"- Excel report: {report_xlsx_path}")


if __name__ == "__main__":
    main()
