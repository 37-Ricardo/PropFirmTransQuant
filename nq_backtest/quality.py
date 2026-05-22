from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class QualityReport:
    """数据质量检查结果。

    这个对象只保存可序列化字段，便于同时输出 JSON 和 Excel。
    """

    row_count: int
    start_datetime: str | None
    end_datetime: str | None
    timezone: str
    required_columns: list[str]
    missing_columns: list[str]
    null_counts: dict[str, int]
    duplicate_datetime_count: int
    gap_count: int
    max_gap_minutes: float | None
    invalid_ohlc_count: int
    non_positive_volume_count: int
    notes: list[str]


def build_quality_report(frame: pd.DataFrame) -> QualityReport:
    """基于标准化后的 1min 数据生成质量报告。

    这里检查的是第一阶段最关键的几类问题：
    - 必要字段缺失；
    - OHLCV 空值或非数值；
    - 重复时间戳；
    - 大于 1 分钟的时间缺口；
    - OHLC 逻辑错误；
    - 成交量小于等于 0。
    """

    required_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [column for column in required_columns if column not in frame.columns]

    # NaN 可能来自原始空值，也可能来自无法转换成数字的脏数据。
    null_counts = {
        column: int(frame[column].isna().sum()) for column in frame.columns if column in required_columns
    }

    duplicate_datetime_count = int(frame.index.duplicated().sum())
    gap_count, max_gap_minutes = _calculate_time_gaps(frame)
    invalid_ohlc_count = _count_invalid_ohlc(frame)
    non_positive_volume_count = _count_non_positive_volume(frame)
    notes = _build_notes(
        missing_columns=missing_columns,
        null_counts=null_counts,
        duplicate_datetime_count=duplicate_datetime_count,
        gap_count=gap_count,
        invalid_ohlc_count=invalid_ohlc_count,
        non_positive_volume_count=non_positive_volume_count,
    )

    timezone = str(frame.index.tz) if isinstance(frame.index, pd.DatetimeIndex) else "unknown"

    return QualityReport(
        row_count=int(len(frame)),
        start_datetime=_format_timestamp(frame.index.min()) if len(frame) else None,
        end_datetime=_format_timestamp(frame.index.max()) if len(frame) else None,
        timezone=timezone,
        required_columns=required_columns,
        missing_columns=missing_columns,
        null_counts=null_counts,
        duplicate_datetime_count=duplicate_datetime_count,
        gap_count=gap_count,
        max_gap_minutes=max_gap_minutes,
        invalid_ohlc_count=invalid_ohlc_count,
        non_positive_volume_count=non_positive_volume_count,
        notes=notes,
    )


def save_quality_report(
    report: QualityReport,
    json_path: str | Path,
    xlsx_path: str | Path,
) -> None:
    """保存质量报告。

    JSON 方便程序读取和版本对比；Excel 方便人工审查。
    """

    json_path = Path(json_path)
    xlsx_path = Path(xlsx_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)

    payload = asdict(report)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = pd.DataFrame(
        [{"metric": key, "value": _stringify_report_value(value)} for key, value in payload.items()]
    )
    null_counts = pd.DataFrame(
        [{"column": key, "null_count": value} for key, value in report.null_counts.items()]
    )
    notes = pd.DataFrame({"note": report.notes})

    # Excel 拆成几个 sheet，比把所有嵌套结构塞进一个表更容易看。
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        null_counts.to_excel(writer, sheet_name="null_counts", index=False)
        notes.to_excel(writer, sheet_name="notes", index=False)


def _calculate_time_gaps(frame: pd.DataFrame) -> tuple[int, float | None]:
    """统计相邻 K 线时间差大于 1 分钟的缺口。"""

    if len(frame) < 2 or not isinstance(frame.index, pd.DatetimeIndex):
        return 0, None

    diffs = frame.index.to_series().diff().dropna()
    gaps = diffs[diffs > pd.Timedelta(minutes=1)]
    if gaps.empty:
        return 0, None
    return int(len(gaps)), float(gaps.max() / pd.Timedelta(minutes=1))


def _count_invalid_ohlc(frame: pd.DataFrame) -> int:
    """检查 OHLC 是否违反基本价格关系。

    合法 K 线应满足：
    - high >= low；
    - open/close 都在 low 到 high 之间。
    """

    required = {"open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        return 0

    invalid = (
        (frame["high"] < frame["low"])
        | (frame["open"] > frame["high"])
        | (frame["open"] < frame["low"])
        | (frame["close"] > frame["high"])
        | (frame["close"] < frame["low"])
    )
    return int(invalid.fillna(False).sum())


def _count_non_positive_volume(frame: pd.DataFrame) -> int:
    """统计成交量小于等于 0 的行。"""

    if "volume" not in frame.columns:
        return 0
    invalid = frame["volume"] <= 0
    return int(invalid.fillna(False).sum())


def _build_notes(
    missing_columns: list[str],
    null_counts: dict[str, int],
    duplicate_datetime_count: int,
    gap_count: int,
    invalid_ohlc_count: int,
    non_positive_volume_count: int,
) -> list[str]:
    """把指标转换成人能快速读懂的文字提示。"""

    notes: list[str] = []
    if missing_columns:
        notes.append(f"Missing required columns: {missing_columns}")
    if any(count > 0 for count in null_counts.values()):
        notes.append("Some required OHLCV fields contain null or non-numeric values.")
    if duplicate_datetime_count > 0:
        notes.append("Duplicate datetimes were detected.")
    if gap_count > 0:
        notes.append("Time gaps larger than 1 minute were detected.")
    if invalid_ohlc_count > 0:
        notes.append("Invalid OHLC rows were detected.")
    if non_positive_volume_count > 0:
        notes.append("Volume contains zero or negative values.")
    if not notes:
        notes.append("No obvious data quality issues detected.")
    return notes


def _format_timestamp(value: pd.Timestamp) -> str:
    """统一时间输出格式，保留时区信息。"""

    return value.isoformat()


def _stringify_report_value(value: object) -> str | int | float | None:
    """把 list/dict 转成字符串，便于写入 Excel 单元格。"""

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value
