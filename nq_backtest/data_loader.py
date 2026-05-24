from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd


# 标准化后的行情字段。第一阶段只要求 OHLCV，datetime 会作为索引。
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")

# 常见 CSV 时间字段名。不同数据源命名不一致，所以这里做一层自动识别。
DATETIME_CANDIDATES = ("datetime", "timestamp", "date_time", "date", "time")

# 字段别名映射：目标标准字段 -> 可接受的原始字段名。
# 例如某些数据源用 O/H/L/C/V，读取后会统一成 open/high/low/close/volume。
COLUMN_ALIASES: Mapping[str, tuple[str, ...]] = {
    "datetime": DATETIME_CANDIDATES,
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c", "last"),
    "volume": ("volume", "vol", "v"),
}


@dataclass(frozen=True)
class LoadedMarketData:
    """读取并标准化后的行情数据及其元信息。

    frame:
        以 America/New_York 时区 datetime 为索引的 OHLCV DataFrame。
    column_map:
        记录标准字段对应的原始 CSV 字段，方便排查数据源差异。
    """

    frame: pd.DataFrame
    source_path: Path
    input_timezone: str
    datetime_column: str
    column_map: dict[str, str]


def load_nq_1min_csv(
    csv_path: str | Path,
    input_timezone: str = "America/New_York",
    datetime_column: str | None = None,
) -> LoadedMarketData:
    """读取 NQ 1min CSV，并转换成项目内部统一格式。

    参数
    ----
    csv_path:
        原始 1 分钟 CSV 文件路径。
    input_timezone:
        当 CSV 时间戳没有自带时区信息时，按这个时区解释。
        例如数据源给的是 UTC 时间，就传入 ``UTC``。
    datetime_column:
        手动指定时间字段名；不传时会从常见字段名里自动识别。
    """

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    raw = pd.read_csv(path)
    if raw.empty:
        raise ValueError(f"CSV file is empty: {path}")

    column_map = _build_column_map(raw.columns, datetime_column)

    # 先把原始字段名统一成项目内部标准字段名。
    # 后续模块只依赖标准字段，避免每个模块都处理不同数据源命名。
    normalized = raw.rename(columns={source: target for target, source in column_map.items()})

    missing = [column for column in ("datetime", *REQUIRED_COLUMNS) if column not in normalized.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns after normalization: {missing}")

    frame = normalized[["datetime", *REQUIRED_COLUMNS]].copy()

    # 所有时间统一到美东时间，方便按 CME/Nasdaq 交易时段做后续逻辑。
    frame["datetime"] = _parse_datetime_to_new_york(frame["datetime"], input_timezone)

    # errors="coerce" 会把无法解析的价格/成交量转成 NaN。
    # 这里不直接删除，让质量报告能统计这些问题。
    for column in REQUIRED_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # datetime 无效的行无法参与时间序列处理，因此在加载阶段丢弃。
    # 价格/成交量 NaN 暂时保留，由质量检查报告负责暴露。
    frame = frame.dropna(subset=["datetime"]).sort_values("datetime").set_index("datetime")
    frame.index.name = "datetime"

    return LoadedMarketData(
        frame=frame,
        source_path=path,
        input_timezone=input_timezone,
        datetime_column=column_map["datetime"],
        column_map=column_map,
    )


def _build_column_map(columns: pd.Index, datetime_column: str | None) -> dict[str, str]:
    """建立“标准字段名 -> 原始字段名”的映射。"""

    # 做大小写不敏感匹配，同时保留原始字段名用于 pandas rename。
    available = {str(column).strip().lower(): column for column in columns}
    column_map: dict[str, str] = {}

    if datetime_column is not None:
        key = datetime_column.strip().lower()
        if key not in available:
            raise ValueError(f"Specified datetime column not found: {datetime_column}")
        column_map["datetime"] = available[key]
    else:
        column_map["datetime"] = _find_first_column(available, COLUMN_ALIASES["datetime"], "datetime")

    for target in REQUIRED_COLUMNS:
        column_map[target] = _find_first_column(available, COLUMN_ALIASES[target], target)

    return column_map


def _find_first_column(
    available: Mapping[str, str],
    candidates: tuple[str, ...],
    target_name: str,
) -> str:
    """从候选别名中找出第一个存在于 CSV 的字段。"""

    for candidate in candidates:
        if candidate in available:
            return available[candidate]
    raise ValueError(f"CSV is missing required column: {target_name}. Tried aliases: {candidates}")


def _parse_datetime_to_new_york(series: pd.Series, input_timezone: str) -> pd.Series:
    """解析时间字段，并统一转换到 America/New_York。

    CSV 时间可能有两类：
    - 已带时区：直接转换到美东；
    - 不带时区：先按 input_timezone 本地化，再转换到美东。

    夏令时切换附近可能出现不存在或歧义时间：
    - ambiguous="NaT"：歧义时间标成 NaT，避免猜错；
    - nonexistent="shift_forward"：不存在时间向前移动到最近合法时间。
    """

    text_values = series.dropna().astype(str).str.strip()
    has_explicit_timezone = text_values.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)

    # TradingView 导出的时间通常类似 2026-05-19T14:45:00-04:00。
    # 对带显式时区的时间戳，先用 utc=True 解析，可以稳妥处理跨夏令时
    # 时同时存在 -04:00 / -05:00 偏移的情况。
    if has_explicit_timezone.any():
        if not has_explicit_timezone.all():
            raise ValueError("Datetime column mixes timezone-aware and naive values.")
        parsed_with_utc = pd.to_datetime(series, errors="coerce", utc=True)
        return parsed_with_utc.dt.tz_convert(ZoneInfo("America/New_York"))

    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.dt.tz is None:
        localized = parsed.dt.tz_localize(
            ZoneInfo(input_timezone),
            ambiguous="NaT",
            nonexistent="shift_forward",
        )
    else:
        localized = parsed
    return localized.dt.tz_convert(ZoneInfo("America/New_York"))
