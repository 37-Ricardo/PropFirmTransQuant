# NQ Futures Backtest

本项目第一阶段提供本地 NQ 期货策略回测系统的数据入口骨架：

- 读取 NQ 1min CSV
- 校验 `datetime/open/high/low/close/volume`
- 将时间统一到 `America/New_York`
- 支持重采样到 `5min` / `15min`
- 输出数据质量检查报告
- 提供 `main.py` 命令行运行入口

## 安装

推荐使用项目内安装脚本。它会把 Python 3.11.9 安装到 `tools/python311/`，再创建 `.venv` 并安装依赖，不修改系统 PATH。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_env.ps1
```

也可以使用你已经安装好的 Python 3.11：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 运行示例

使用示例 CSV：

```powershell
python main.py --csv examples\sample_nq_1min.csv --timeframe 5min
```

使用自己的 NQ 1min CSV：

```powershell
python main.py --csv data\raw\NQ_1min.csv --timeframe 15min --input-tz America/New_York
```

如果 CSV 的时间戳是 UTC：

```powershell
python main.py --csv data\raw\NQ_1min.csv --timeframe 5min --input-tz UTC
```

## CSV 字段要求

默认需要以下字段，大小写不敏感：

```text
datetime, open, high, low, close, volume
```

常见别名也会自动识别：

- `datetime`: `date`, `time`, `timestamp`, `datetime`
- `open`: `open`, `o`
- `high`: `high`, `h`
- `low`: `low`, `l`
- `close`: `close`, `c`, `last`
- `volume`: `volume`, `vol`, `v`

也可以手动指定时间列：

```powershell
python main.py --csv data\raw\NQ_1min.csv --datetime-column timestamp
```

## 输出

运行后默认输出到 `output/`：

- `output/cleaned_1min.csv`
- `output/resampled_5min.csv` 或 `output/resampled_15min.csv`
- `output/data_quality_report.json`
- `output/data_quality_report.xlsx`

## 验证

```powershell
python main.py --csv examples\sample_nq_1min.csv --timeframe 5min
```

看到 `Data quality report`、`Cleaned rows`、`Resampled rows`，并且 `output/` 下生成上述文件，即表示第一阶段骨架可用。
