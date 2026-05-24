from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class QualityReport:
    """数据质量检查结果。

    这个对象只保存可序列化字段，便于同时输出 JSON 和 Excel。
    gap_count 保留为“可疑缺口数量”，避免把 NQ 的正常休市、隔夜、
    周末或 RTH-only 空档误判成数据错误。
    """

    row_count: int
    start_datetime: str | None
    end_datetime: str | None
    timezone: str
    expected_interval: str
    expected_interval_minutes: float
    required_columns: list[str]
    missing_columns: list[str]
    null_counts: dict[str, int]
    duplicate_datetime_count: int
    gap_count: int
    total_gap_count: int
    expected_gap_count: int
    max_gap_minutes: float | None
    gap_examples: list[dict[str, str | float]]
    invalid_ohlc_count: int
    non_positive_volume_count: int
    notes: list[str]


def build_quality_report(frame: pd.DataFrame, expected_interval: str = "1min") -> QualityReport:
    """基于标准化后的 1min 数据生成质量报告。

    这里检查的是第一阶段最关键的几类问题：
    - 必要字段缺失；
    - OHLCV 空值或非数值；
    - 重复时间戳；
    - 可疑的时间缺口；
    - OHLC 逻辑错误；
    - 成交量小于等于 0。
    """

    expected_delta = pd.Timedelta(expected_interval)
    expected_interval_minutes = float(expected_delta / pd.Timedelta(minutes=1))
    required_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [column for column in required_columns if column not in frame.columns]

    # NaN 可能来自原始空值，也可能来自无法转换成数字的脏数据。
    null_counts = {
        column: int(frame[column].isna().sum()) for column in frame.columns if column in required_columns
    }

    duplicate_datetime_count = int(frame.index.duplicated().sum())
    gap_report = _calculate_time_gaps(frame, expected_delta)
    invalid_ohlc_count = _count_invalid_ohlc(frame)
    non_positive_volume_count = _count_non_positive_volume(frame)
    notes = _build_notes(
        missing_columns=missing_columns,
        null_counts=null_counts,
        duplicate_datetime_count=duplicate_datetime_count,
        suspicious_gap_count=gap_report["suspicious_gap_count"],
        expected_gap_count=gap_report["expected_gap_count"],
        invalid_ohlc_count=invalid_ohlc_count,
        non_positive_volume_count=non_positive_volume_count,
    )

    timezone = str(frame.index.tz) if isinstance(frame.index, pd.DatetimeIndex) else "unknown"

    return QualityReport(
        row_count=int(len(frame)),
        start_datetime=_format_timestamp(frame.index.min()) if len(frame) else None,
        end_datetime=_format_timestamp(frame.index.max()) if len(frame) else None,
        timezone=timezone,
        expected_interval=expected_interval,
        expected_interval_minutes=expected_interval_minutes,
        required_columns=required_columns,
        missing_columns=missing_columns,
        null_counts=null_counts,
        duplicate_datetime_count=duplicate_datetime_count,
        gap_count=gap_report["suspicious_gap_count"],
        total_gap_count=gap_report["total_gap_count"],
        expected_gap_count=gap_report["expected_gap_count"],
        max_gap_minutes=gap_report["max_gap_minutes"],
        gap_examples=gap_report["gap_examples"],
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
    gaps = pd.DataFrame(report.gap_examples)
    notes = pd.DataFrame({"note": report.notes})

    # Excel 拆成几个 sheet，比把所有嵌套结构塞进一个表更容易看。
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        null_counts.to_excel(writer, sheet_name="null_counts", index=False)
        gaps.to_excel(writer, sheet_name="gap_examples", index=False)
        notes.to_excel(writer, sheet_name="notes", index=False)


def _calculate_time_gaps(frame: pd.DataFrame, expected_delta: pd.Timedelta) -> dict[str, Any]:
    """统计并分类相邻 K 线时间差大于期望周期的间隔。

    NQ 期货不是简单的 24 小时连续 1min 序列。数据中经常出现：
    - CME 每日维护休市；
    - 周末或节假日空档；
    - 只使用 RTH 数据时的隔夜空档。

    这些间隔不一定是数据错误，所以这里把 gap 分成 expected 和 suspicious。
    suspicious 才计入 QualityReport.gap_count。
    """

    empty_report: dict[str, Any] = {
        "suspicious_gap_count": 0,
        "expected_gap_count": 0,
        "total_gap_count": 0,
        "max_gap_minutes": None,
        "gap_examples": [],
    }
    if len(frame) < 2 or not isinstance(frame.index, pd.DatetimeIndex):
        return empty_report

    ordered_index = frame.index.sort_values()
    gap_examples: list[dict[str, str | float]] = []
    suspicious_gap_count = 0
    expected_gap_count = 0
    max_gap_minutes: float | None = None
    expected_minutes = float(expected_delta / pd.Timedelta(minutes=1))

    for previous, current in zip(ordered_index[:-1], ordered_index[1:]):
        gap_minutes = float((current - previous) / pd.Timedelta(minutes=1))
        if current - previous <= expected_delta:
            continue

        classification = _classify_nq_gap(previous, current, gap_minutes, expected_minutes)
        if classification == "suspicious_intraday_gap":
            suspicious_gap_count += 1
        else:
            expected_gap_count += 1

        max_gap_minutes = gap_minutes if max_gap_minutes is None else max(max_gap_minutes, gap_minutes)

        # 报告只保留前 20 个样例，避免大文件产生过长的 JSON / Excel。
        if len(gap_examples) < 20:
            gap_examples.append(
                {
                    "previous": _format_timestamp(previous),
                    "current": _format_timestamp(current),
                    "gap_minutes": gap_minutes,
                    "classification": classification,
                }
            )

    return {
        "suspicious_gap_count": suspicious_gap_count,
        "expected_gap_count": expected_gap_count,
        "total_gap_count": suspicious_gap_count + expected_gap_count,
        "max_gap_minutes": max_gap_minutes,
        "gap_examples": gap_examples,
    }


def _classify_nq_gap(
    previous: pd.Timestamp,
    current: pd.Timestamp,
    gap_minutes: float,
    expected_minutes: float,
) -> str:
    """将 NQ 时间间隔分成 expected 或 suspicious。

    这是第一阶段的启发式分类，不替代正式交易日历。后续如果要做到
    节假日、提前收盘、合约特殊时段全覆盖，可以接入 CME 交易日历。
    """

    previous_time = previous.timetz().replace(tzinfo=None)
    current_time = current.timetz().replace(tzinfo=None)
    crossed_date = previous.date() != current.date()

    if crossed_date and (previous.weekday() >= 4 or current.weekday() == 0):
        return "expected_weekend_or_holiday_gap"

    if gap_minutes >= 6 * 60:
        return "expected_long_session_break"

    if crossed_date:
        return "expected_overnight_gap"

    if _is_cme_daily_maintenance_gap(previous_time, current_time, gap_minutes):
        return "expected_cme_daily_maintenance_gap"

    if _is_holiday_early_close_gap(previous_time, current_time, gap_minutes):
        return "expected_holiday_early_close_gap"

    if _is_rth_session_break(previous_time, current_time):
        return "expected_rth_session_break"

    if gap_minutes <= expected_minutes:
        return "expected_regular_bar_interval"

    return "suspicious_intraday_gap"


def _is_cme_daily_maintenance_gap(
    previous_time: time,
    current_time: time,
    gap_minutes: float,
) -> bool:
    """识别 CME 美东 17:00-18:00 附近的每日维护休市空档。"""

    return (
        45 <= gap_minutes <= 90
        and previous_time.hour == 16
        and previous_time.minute >= 45
        and current_time.hour == 18
        and current_time.minute <= 15
    )


def _is_holiday_early_close_gap(previous_time: time, current_time: time, gap_minutes: float) -> bool:
    """识别 CME 节假日提前收盘后到 18:00 重开的空档。

    NQ 在部分美国节假日会于美东 13:00 附近提前收盘，随后到 18:00
    再开下一交易时段。没有接入正式交易日历前，先用时间形态识别。
    """

    previous_near_early_close = previous_time.hour in (12, 13)
    current_near_reopen = current_time.hour == 18 and current_time.minute <= 5
    return 240 <= gap_minutes <= 330 and previous_near_early_close and current_near_reopen


def _is_rth_session_break(previous_time: time, current_time: time) -> bool:
    """识别 RTH-only 数据中常见的日盘收盘到次日开盘空档。

    NQ RTH 常见区间是美东 09:30-16:00。这里留出少量容错，
    用于兼容数据源把收盘或开盘 K 线标在不同端点的情况。
    """

    previous_after_rth_close = previous_time.hour > 15 or (
        previous_time.hour == 15 and previous_time.minute >= 55
    )
    current_near_rth_open = current_time.hour == 9 and current_time.minute <= 35
    return previous_after_rth_close and current_near_rth_open


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
    suspicious_gap_count: int,
    expected_gap_count: int,
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
    if suspicious_gap_count > 0:
        notes.append("Suspicious intraday time gaps were detected.")
    if expected_gap_count > 0:
        notes.append("Expected NQ session gaps were detected and not treated as data errors.")
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
