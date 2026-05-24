from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.quality import _classify_nq_gap, build_quality_report
from nq_backtest.resample import resample_ohlcv


DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output" / "data_validation_full"
VENDOR_PATTERN = "nq_continuous_ohlcv_1m_*.csv"
PRICE_COLUMNS = ["open", "high", "low", "close"]
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    vendor_files = sorted(DATA_DIR.glob(VENDOR_PATTERN))
    if not vendor_files:
        raise FileNotFoundError(f"No vendor files found: {DATA_DIR / VENDOR_PATTERN}")

    annual_summary, gap_details, loaded_frames = validate_vendor_files(vendor_files)
    combined_summary, boundary_summary, jump_summary = validate_combined_data(loaded_frames, vendor_files)
    cross_summary, cross_mismatches = cross_validate_tradingview(loaded_frames)

    annual_summary.to_csv(OUTPUT_DIR / "annual_summary.csv", index=False, encoding="utf-8-sig")
    gap_details.to_csv(OUTPUT_DIR / "gap_details.csv", index=False, encoding="utf-8-sig")
    combined_summary.to_csv(OUTPUT_DIR / "combined_summary.csv", index=False, encoding="utf-8-sig")
    boundary_summary.to_csv(OUTPUT_DIR / "year_boundary_summary.csv", index=False, encoding="utf-8-sig")
    jump_summary.to_csv(OUTPUT_DIR / "largest_open_close_jumps.csv", index=False, encoding="utf-8-sig")
    cross_summary.to_csv(OUTPUT_DIR / "tradingview_cross_validation.csv", index=False, encoding="utf-8-sig")
    cross_mismatches.to_csv(
        OUTPUT_DIR / "tradingview_cross_validation_mismatches.csv",
        index=False,
        encoding="utf-8-sig",
    )

    with pd.ExcelWriter(OUTPUT_DIR / "nq_data_validation_report.xlsx", engine="openpyxl") as writer:
        annual_summary.to_excel(writer, sheet_name="annual_summary", index=False)
        combined_summary.to_excel(writer, sheet_name="combined_summary", index=False)
        boundary_summary.to_excel(writer, sheet_name="year_boundaries", index=False)
        jump_summary.to_excel(writer, sheet_name="largest_jumps", index=False)
        gap_details.to_excel(writer, sheet_name="gap_details", index=False)
        cross_summary.to_excel(writer, sheet_name="tv_cross_summary", index=False)
        cross_mismatches.to_excel(writer, sheet_name="tv_cross_mismatches", index=False)

    print(f"Report directory: {OUTPUT_DIR}")
    print("\nCombined summary")
    print(combined_summary.to_string(index=False))
    print("\nAnnual summary")
    print(
        annual_summary[
            [
                "file",
                "rows",
                "start",
                "end",
                "duplicate_datetimes",
                "invalid_ohlc_rows",
                "non_positive_volume_rows",
                "tick_size_invalid_prices",
                "suspicious_gap_events",
                "estimated_missing_minutes_from_suspicious_gaps",
            ]
        ].to_string(index=False)
    )
    print("\nTradingView cross validation")
    print(cross_summary.to_string(index=False))


def validate_vendor_files(
    vendor_files: list[Path],
) -> tuple[pd.DataFrame, pd.DataFrame, list[pd.DataFrame]]:
    annual_rows: list[dict[str, object]] = []
    gap_rows: list[dict[str, object]] = []
    loaded_frames: list[pd.DataFrame] = []

    for path in vendor_files:
        raw = pd.read_csv(path)
        data = load_nq_1min_csv(path, input_timezone="America/New_York").frame
        report = build_quality_report(data, expected_interval="1min")
        loaded_frames.append(data.assign(source_file=path.name))

        tick_invalid_by_column = count_tick_size_violations(data)
        gap_stats, file_gap_rows = collect_gap_details(path.name, data)
        gap_rows.extend(file_gap_rows)

        annual_rows.append(
            {
                "file": path.name,
                "raw_columns": ",".join(raw.columns.astype(str)),
                "symbol_values": ",".join(raw["symbol"].dropna().astype(str).unique())
                if "symbol" in raw.columns
                else "",
                "rows": len(data),
                "raw_rows": len(raw),
                "start": report.start_datetime,
                "end": report.end_datetime,
                "timezone": report.timezone,
                "duplicate_datetimes": report.duplicate_datetime_count,
                "invalid_ohlc_rows": report.invalid_ohlc_count,
                "non_positive_volume_rows": report.non_positive_volume_count,
                "null_open": report.null_counts.get("open", 0),
                "null_high": report.null_counts.get("high", 0),
                "null_low": report.null_counts.get("low", 0),
                "null_close": report.null_counts.get("close", 0),
                "null_volume": report.null_counts.get("volume", 0),
                "tick_size_invalid_prices": sum(tick_invalid_by_column.values()),
                "tick_size_invalid_by_column": tick_invalid_by_column,
                "suspicious_gap_events": report.gap_count,
                "expected_session_gap_events": report.expected_gap_count,
                "total_gap_events": report.total_gap_count,
                "max_gap_minutes": report.max_gap_minutes,
                "estimated_missing_minutes_from_suspicious_gaps": gap_stats[
                    "estimated_missing_minutes"
                ],
                "suspicious_gap_duration_counts": gap_stats["duration_counts"],
                "min_open": float(data["open"].min()),
                "max_high": float(data["high"].max()),
                "min_low": float(data["low"].min()),
                "max_close": float(data["close"].max()),
                "min_volume": int(data["volume"].min()),
                "max_volume": int(data["volume"].max()),
            }
        )

    return pd.DataFrame(annual_rows), pd.DataFrame(gap_rows), loaded_frames


def validate_combined_data(
    loaded_frames: list[pd.DataFrame],
    vendor_files: list[Path],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    combined = pd.concat(loaded_frames).sort_index()
    duplicate_count = int(combined.index.duplicated().sum())

    combined_summary = pd.DataFrame(
        [
            {
                "rows": len(combined),
                "start": combined.index.min().isoformat(),
                "end": combined.index.max().isoformat(),
                "duplicate_datetimes": duplicate_count,
                "files": len(vendor_files),
                "min_open": float(combined["open"].min()),
                "max_high": float(combined["high"].max()),
                "min_low": float(combined["low"].min()),
                "max_close": float(combined["close"].max()),
                "min_volume": int(combined["volume"].min()),
                "max_volume": int(combined["volume"].max()),
            }
        ]
    )

    boundary_rows: list[dict[str, object]] = []
    for index in range(len(loaded_frames) - 1):
        current = loaded_frames[index]
        next_frame = loaded_frames[index + 1]
        current_last = current.index.max()
        next_first = next_frame.index.min()
        boundary_rows.append(
            {
                "from_file": vendor_files[index].name,
                "to_file": vendor_files[index + 1].name,
                "from_last_datetime": current_last.isoformat(),
                "to_first_datetime": next_first.isoformat(),
                "gap_minutes": float((next_first - current_last) / pd.Timedelta(minutes=1)),
                "from_last_close": float(current.loc[current_last, "close"]),
                "to_first_open": float(next_frame.loc[next_first, "open"]),
                "open_minus_previous_close": float(
                    next_frame.loc[next_first, "open"] - current.loc[current_last, "close"]
                ),
            }
        )

    close_prev = combined["close"].shift(1)
    jumps = (combined["open"] - close_prev).abs().dropna().sort_values(ascending=False).head(100)
    jump_rows = [
        {
            "datetime": timestamp.isoformat(),
            "abs_open_minus_previous_close": float(value),
            "open": float(combined.loc[timestamp, "open"]),
            "previous_close": float(close_prev.loc[timestamp]),
            "source_file": str(combined.loc[timestamp, "source_file"]),
        }
        for timestamp, value in jumps.items()
    ]

    return combined_summary, pd.DataFrame(boundary_rows), pd.DataFrame(jump_rows)


def cross_validate_tradingview(
    loaded_frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    vendor_1min = pd.concat(loaded_frames).sort_index()
    benchmark_specs = [
        ("TradingView_15min", DATA_DIR / "CME_MINI_NQ1!, 15.csv", "15min"),
        ("TradingView_1h", DATA_DIR / "CME_MINI_NQ1!, 60 (1).csv", "1h"),
        ("TradingView_1min_downloads", Path.home() / "Downloads" / "CME_MINI_NQ1!, 1.csv", "1min"),
        ("TradingView_5min_downloads", Path.home() / "Downloads" / "CME_MINI_NQ1!, 5.csv", "5min"),
    ]

    summary_rows: list[dict[str, object]] = []
    mismatch_rows: list[dict[str, object]] = []

    for name, benchmark_path, timeframe in benchmark_specs:
        if not benchmark_path.exists():
            continue

        benchmark = load_nq_1min_csv(benchmark_path).frame.astype(float)
        if timeframe == "1min":
            vendor = vendor_1min[OHLCV_COLUMNS].astype(float)
        else:
            vendor = resample_ohlcv(vendor_1min, timeframe)[OHLCV_COLUMNS].astype(float)

        joined = vendor.join(benchmark[OHLCV_COLUMNS], how="inner", lsuffix="_vendor", rsuffix="_tv")
        exact_ohlcv = exact_rows(joined, OHLCV_COLUMNS)
        exact_ohlc = exact_rows(joined, PRICE_COLUMNS)

        row = {
            "benchmark": name,
            "benchmark_path": str(benchmark_path),
            "timeframe": timeframe,
            "vendor_rows": len(vendor),
            "benchmark_rows": len(benchmark),
            "overlap_rows": len(joined),
            "exact_ohlcv_rows": int(exact_ohlcv.sum()),
            "exact_ohlc_rows": int(exact_ohlc.sum()),
            "mismatch_ohlcv_rows": int((~exact_ohlcv).sum()) if len(joined) else 0,
            "mismatch_ohlc_rows": int((~exact_ohlc).sum()) if len(joined) else 0,
            "benchmark_start": benchmark.index.min().isoformat(),
            "benchmark_end": benchmark.index.max().isoformat(),
        }
        for column in OHLCV_COLUMNS:
            diff = abs(joined[f"{column}_vendor"] - joined[f"{column}_tv"])
            row[f"{column}_matches"] = int((diff < 1e-9).sum())
            row[f"{column}_max_abs_diff"] = float(diff.max()) if len(diff) else None

        summary_rows.append(row)

        mismatches = joined.loc[~exact_ohlcv].head(500)
        for timestamp, values in mismatches.iterrows():
            item: dict[str, object] = {
                "benchmark": name,
                "timeframe": timeframe,
                "datetime": timestamp.isoformat(),
            }
            for column in OHLCV_COLUMNS:
                item[f"{column}_vendor"] = values[f"{column}_vendor"]
                item[f"{column}_tv"] = values[f"{column}_tv"]
                item[f"{column}_diff_vendor_minus_tv"] = (
                    values[f"{column}_vendor"] - values[f"{column}_tv"]
                )
            mismatch_rows.append(item)

    return pd.DataFrame(summary_rows), pd.DataFrame(mismatch_rows)


def count_tick_size_violations(data: pd.DataFrame) -> dict[str, int]:
    result: dict[str, int] = {}
    for column in PRICE_COLUMNS:
        scaled = data[column].to_numpy(dtype=float) * 4
        result[column] = int((~np.isclose(scaled, np.round(scaled), atol=1e-9)).sum())
    return result


def collect_gap_details(file_name: str, data: pd.DataFrame) -> tuple[dict[str, object], list[dict[str, object]]]:
    duration_counts: Counter[int] = Counter()
    estimated_missing_minutes = 0
    rows: list[dict[str, object]] = []
    index = data.index.sort_values()

    for previous, current in zip(index[:-1], index[1:]):
        gap_minutes = float((current - previous) / pd.Timedelta(minutes=1))
        if gap_minutes <= 1:
            continue

        classification = _classify_nq_gap(previous, current, gap_minutes, 1.0)
        if classification == "suspicious_intraday_gap":
            duration_counts[int(gap_minutes)] += 1
            estimated_missing_minutes += int(gap_minutes) - 1

        rows.append(
            {
                "file": file_name,
                "previous": previous.isoformat(),
                "current": current.isoformat(),
                "gap_minutes": gap_minutes,
                "classification": classification,
            }
        )

    return {
        "duration_counts": dict(duration_counts),
        "estimated_missing_minutes": estimated_missing_minutes,
    }, rows


def exact_rows(joined: pd.DataFrame, columns: list[str]) -> np.ndarray:
    if joined.empty:
        return np.array([], dtype=bool)
    return np.logical_and.reduce(
        [
            (joined[f"{column}_vendor"] - joined[f"{column}_tv"]).abs().to_numpy() < 1e-9
            for column in columns
        ]
    )


if __name__ == "__main__":
    main()
