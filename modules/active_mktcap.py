"""
活跃市值读取器（读 qcore 数据湖中 active_mktcap_daily.parquet）

设计原则（遵循项目铁律「Python 只做数据准备，判断话术交给 LLM / Z 哥」）：
  - 本模块只负责把「已优化好的」活跃市值序列读出来 + 整理近期走势；
  - 不在代码里写死 +4% / -2.3% 多空判定 —— 那是 Z 哥看数据后的话术。

数据来源：
  {QCORE_DATA_DIR}/active_mktcap_daily.parquet
  列：date(datetime), active_mktcap(float)，全市场每日一个数，2019~今。
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - 环境缺依赖时降级
    pd = None  # type: ignore

logger = logging.getLogger(__name__)

ACTIVE_MKTCAP_FILE = "active_mktcap_daily.parquet"


def _resolve_data_dir() -> Path:
    """活跃市值文件所在目录：优先 QCORE_DATA_DIR，回退默认数据湖路径。"""
    return Path(
        os.environ.get(
            "QCORE_DATA_DIR",
            str(Path.home() / "Desktop" / "量化交易" / "data"),
        )
    )


@dataclass(frozen=True)
class DailyPoint:
    """单个交易日的活跃市值点。"""
    date: str          # YYYY-MM-DD
    value: float       # 活跃市值
    pct_chg: float     # 相对前一交易日变化 %


@dataclass(frozen=True)
class ActiveMktcapReading:
    """活跃市值读数（纯数据，不含多空结论）。"""
    available: bool
    latest_date: str = ""
    latest_value: float = 0.0
    recent: tuple[DailyPoint, ...] = ()   # 升序，最后一个为最新
    peak_value: float = 0.0               # recent 窗口内高点
    peak_date: str = ""
    from_peak_pct: float = 0.0            # 最新值相对窗口高点的累计变化 %
    reason: str = ""                      # available=False 时的原因


def get_active_mktcap(days: int = 60) -> ActiveMktcapReading:
    """读取活跃市值最新读数 + 近 `days` 个交易日走势（纯数据，不做多空判定）。"""
    if pd is None:
        return ActiveMktcapReading(available=False, reason="pandas 未安装")

    path = _resolve_data_dir() / ACTIVE_MKTCAP_FILE
    if not path.exists():
        return ActiveMktcapReading(
            available=False,
            reason=f"未找到活跃市值文件: {path}（请确认 QCORE_DATA_DIR 指向数据湖）",
        )

    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001 - 读取失败统一降级返回
        logger.error("读取活跃市值失败 %s: %s", path, e)
        return ActiveMktcapReading(available=False, reason=f"读取失败: {e}")

    required = {"date", "active_mktcap"}
    if df is None or df.empty or not required.issubset(df.columns):
        return ActiveMktcapReading(available=False, reason="活跃市值文件为空或缺少 date/active_mktcap 列")

    df = df.sort_values("date").reset_index(drop=True)
    df["pct_chg"] = df["active_mktcap"].pct_change() * 100
    window = df.tail(max(days, 1))

    points = tuple(
        DailyPoint(
            date=pd.Timestamp(row.date).strftime("%Y-%m-%d"),
            value=float(row.active_mktcap),
            pct_chg=float(row.pct_chg) if pd.notna(row.pct_chg) else 0.0,
        )
        for row in window.itertuples(index=False)
    )

    latest = points[-1]
    peak_idx = max(range(len(points)), key=lambda i: points[i].value)
    peak = points[peak_idx]
    from_peak = (latest.value / peak.value - 1) * 100 if peak.value else 0.0

    return ActiveMktcapReading(
        available=True,
        latest_date=latest.date,
        latest_value=latest.value,
        recent=points,
        peak_value=peak.value,
        peak_date=peak.date,
        from_peak_pct=from_peak,
    )


def format_active_mktcap(reading: ActiveMktcapReading, tail: int = 10) -> str:
    """人类可读的活跃市值数据摘要（CLI 用，纯数据、不下多空结论）。"""
    if not reading.available:
        return f"【活跃市值】不可用 —— {reading.reason}"

    shown = min(tail, len(reading.recent))
    lines = [
        "【活跃市值】(全市场择时标尺 · 数据来自 qcore 数据湖)",
        f"  最新({reading.latest_date}): {reading.latest_value:,.0f}",
        f"  近{len(reading.recent)}日高点({reading.peak_date}): {reading.peak_value:,.0f}",
        f"  最新相对高点累计: {reading.from_peak_pct:+.2f}%",
        f"  最近{shown}个交易日:",
    ]
    for p in reading.recent[-tail:]:
        lines.append(f"    {p.date}  {p.value:>12,.0f}   日变化 {p.pct_chg:+.2f}%")
    lines.append("  (多/空请按 Z 哥 +4% / -2.3% 框架自行判读)")
    return "\n".join(lines)
