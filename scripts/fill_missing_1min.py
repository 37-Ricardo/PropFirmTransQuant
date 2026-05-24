from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nq_backtest.data_loader import load_nq_1min_csv
from nq_backtest.quality import _classify_nq_gap


DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "processed"
REPORT_DIR = PROJECT_ROOT / "output" / "filled_data"
INPUT_PATTERN = "nq_continuous_ohlcv_1m_*.csv"
OUTPUT_SUFFIX = "_filled.csv"
PRICE_COLUMNS = ["open", "high", "low", "close"]
OUTPUT_COLUMNS = [
    "datetime",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "is_filled",
    "fill_reason",
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    source_files = sorted(DATA_DIR.glob(INPUT_PATTERN))
    if not source_files:
        raise FileNotFoundError(f"No source files matched: {DATA_DIR / INPUT_PATTERN}")

    summary_rows: list[dict[str, object]] = []
    all_gap_rows: list[dict[str, object]] = []

    for source_path in source_files:
        print(f"Processing {source_path.name} ...")
        filled, summary, gap_rows = fill_one_file(source_path)

        output_path = OUTPUT_DIR / source_path.name.replace(".csv", OUTPUT_SUFFIX)
        write_filled_csv(filled, output_path)

        summary["source_file"] = source_path.name
        summary["output_file"] = output_path.name
        summary_rows.append(summary)
        all_gap_rows.extend(gap_rows)

        print(
            f"  original={summary['original_rows']} "
            f"filled={summary['filled_rows_added']} "
            f"final={summary['final_rows']}"
        )

    summary_df = pd.DataFrame(summary_rows)
    gaps_df = pd.DataFrame(all_gap_rows)
    summary_df.to_csv(REPORT_DIR / "fill_summary.csv", index=False, encoding="utf-8-sig")
    gaps_df.to_csv(REPORT_DIR / "filled_gap_details.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(REPORT_DIR / "fill_missing_1min_report.xlsx", engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        gaps_df.to_excel(writer, sheet_name="filled_gaps", index=False)

    print(f"\nFilled CSV directory: {OUTPUT_DIR}")
    print(f"Report directory: {REPORT_DIR}")
    print(summary_df.to_string(index=False))


def fill_one_file(source_path: Path) -> tuple[pd.DataFrame, dict[str, object], list[dict[str, object]]]:
    raw = pd.read_csv(source_path)
    symbol = infer_symbol(raw)

    # 供应商数据已通过交叉验证确认应按 America/New_York 交易所时间解释。
    data = load_nq_1min_csv(source_path, input_timezone="America/New_York").frame.sort_index()
    original = data.copy()
    original["symbol"] = symbol
    original["is_filled"] = False
    original["fill_reason"] = "original"

    fill_frames: list[pd.DataFrame] = []
    gap_rows: list[dict[str, object]] = []

    index = data.index
    for previous, current in zip(index[:-1], index[1:]):
        gap_minutes = int((current - previous) / pd.Timedelta(minutes=1))
        if gap_minutes <= 1:
            continue

        classification = _classify_nq_gap(previous, current, float(gap_minutes), 1.0)
        if classification != "suspicious_intraday_gap":
            continue

        missing_index = pd.date_range(
            start=previous + pd.Timedelta(minutes=1),
            end=current - pd.Timedelta(minutes=1),
            freq="1min",
        )
        if missing_index.empty:
            continue

        previous_close = float(data.loc[previous, "close"])
        fill_frame = pd.DataFrame(index=missing_index)
        for column in PRICE_COLUMNS:
            fill_frame[column] = previous_close
        fill_frame["volume"] = 0
        fill_frame["symbol"] = symbol
        fill_frame["is_filled"] = True
        fill_frame["fill_reason"] = "filled_previous_close_volume_0"
        fill_frames.append(fill_frame)

        gap_rows.append(
            {
                "source_file": source_path.name,
                "previous": previous.isoformat(),
                "current": current.isoformat(),
                "gap_minutes": gap_minutes,
                "filled_rows": len(missing_index),
                "fill_price": previous_close,
                "classification": classification,
            }
        )

    if fill_frames:
        filled = pd.concat([original, *fill_frames]).sort_index()
    else:
        filled = original.sort_index()

    duplicate_after_fill = int(filled.index.duplicated().sum())
    if duplicate_after_fill:
        raise ValueError(f"Duplicate datetimes after fill in {source_path.name}: {duplicate_after_fill}")

    summary = {
        "original_rows": len(data),
        "filled_rows_added": int(filled["is_filled"].sum()),
        "final_rows": len(filled),
        "start": filled.index.min().isoformat(),
        "end": filled.index.max().isoformat(),
        "duplicate_datetimes_after_fill": duplicate_after_fill,
        "filled_gap_events": len(gap_rows),
    }
    return filled, summary, gap_rows


def infer_symbol(raw: pd.DataFrame) -> str:
    if "symbol" not in raw.columns:
        return "NQ"
    values = raw["symbol"].dropna().astype(str)
    if values.empty:
        return "NQ"
    return values.mode().iloc[0]


def write_filled_csv(frame: pd.DataFrame, output_path: Path) -> None:
    output = frame.copy()

    # 写回无时区的 America/New_York 墙钟时间，保持和供应商原始 CSV 一致。
    output.insert(0, "datetime", output.index.tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"))
    output = output[OUTPUT_COLUMNS]
    output.to_csv(output_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
