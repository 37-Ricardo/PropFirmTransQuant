from __future__ import annotations

from pathlib import Path

import pandas as pd


TRADE_EXPORT_COLUMNS = [
    "trade_id",
    "direction",
    "signal_type",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "exit_reason",
    "pnl_points",
    "pnl_dollars",
    "holding_bars",
]


def export_trades_to_excel(trades: pd.DataFrame, path: str | Path = "reports/trades.xlsx") -> None:
    """导出交易明细到 Excel。"""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    export = trades.copy()
    for column in TRADE_EXPORT_COLUMNS:
        if column not in export.columns:
            export[column] = pd.Series(dtype="object")
    export = export[TRADE_EXPORT_COLUMNS]
    for column in ["entry_time", "exit_time"]:
        export[column] = export[column].map(_remove_timezone)

    summary = pd.DataFrame(
        [
            {
                "total_trades": len(export),
                "winning_trades": int((export["pnl_dollars"] > 0).sum()) if len(export) else 0,
                "losing_trades": int((export["pnl_dollars"] < 0).sum()) if len(export) else 0,
                "total_pnl": float(export["pnl_dollars"].sum()) if len(export) else 0.0,
                "average_pnl": float(export["pnl_dollars"].mean()) if len(export) else 0.0,
            }
        ]
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        export.to_excel(writer, sheet_name="trades", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)


def _remove_timezone(value: object) -> object:
    """Excel 不支持带时区 datetime，导出前转成无时区时间。"""

    if pd.isna(value):
        return value
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("America/New_York").tz_localize(None)
    return timestamp
