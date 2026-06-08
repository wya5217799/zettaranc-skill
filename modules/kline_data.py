"""
K线统一取数层（canonical daily K-line access）

历史背景：日 K 取数逻辑曾在三处重复实现并各自漂移，导致两个静默 bug——
  1. 窗口反转：误用 ``ORDER BY trade_date ASC LIMIT`` 取到“最早 N 根”而非
     “最近 N 根”，战法/诊断分析的是一年多前的旧数据；
  2. 精简/富 dict 形状不一致：把精简 dict 喂给 detect_*（战法检测）抛 KeyError。

本模块把“取最近 N 根、按日期升序、DB_PATH 从环境变量读取”这一不变式收敛为
**单一实现**。三个对外取数入口都委托到这里：
  - ``modules.indicators.data_layer.get_kline_data``  → ``fetch_daily_data``（DailyData）
  - ``modules.strategies.core.get_kline_data``         → ``fetch_rich_klines``（富 dict）
  - ``modules.screener.get_recent_klines``             → ``fetch_rich_klines``（富 dict）

约定（见 CLAUDE.md）：DB_PATH 统一从环境变量动态读取，代码中不硬编码。
"""

import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:  # 仅类型检查期引用，运行期惰性导入，避免 import 环
    from .indicators import DailyData

# 项目根目录：modules/kline_data.py → parent.parent
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_DB = "data/stock_data.db"


def _resolve_db_path() -> Path:
    """动态解析数据库路径（每次调用读取 DB_PATH，相对路径锚定项目根）。"""
    path_str = os.getenv("DB_PATH", _DEFAULT_DB)
    path = Path(path_str)
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path_str).resolve()
    return path


def _connect() -> sqlite3.Connection:
    """获取数据库连接（动态读取 DB_PATH 环境变量）。"""
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# 取最近 N 根 K 线的“窗口 + 排序”骨架：内层按日期倒序取尾部 N 根，外层正序
# 还原时间线。这是“最近 N 根、升序”不变式的**唯一拥有者**——曾经的窗口反转
# bug 就出在这里被各自重写。with_joins 只切换投影列与 LEFT JOIN，不动骨架。
_BASE_COLS = (
    "k.ts_code, k.trade_date, k.open, k.high, k.low, k.close, "
    "k.vol, k.amount, k.pct_chg"
)
_JOIN_COLS = (
    "i.boll_upper, i.boll_mid, i.boll_lower, i.rsi6, i.adx, i.dmi_plus, i.dmi_minus, "
    "m.buy_lg_amount, m.buy_elg_amount, m.sell_lg_amount, m.sell_elg_amount, m.net_mf"
)
_JOIN_CLAUSE = (
    "\n            LEFT JOIN indicator_cache i "
    "ON k.ts_code = i.ts_code AND k.trade_date = i.trade_date"
    "\n            LEFT JOIN moneyflow m "
    "ON k.ts_code = m.ts_code AND k.trade_date = m.trade_date"
)


def _window_sql(with_joins: bool) -> str:
    """构造窗口取数 SQL。with_joins=True 时附带指标缓存 + 资金流 LEFT JOIN。"""
    cols = _BASE_COLS + (", " + _JOIN_COLS if with_joins else "")
    joins = _JOIN_CLAUSE if with_joins else ""
    return f"""
        SELECT * FROM (
            SELECT {cols}
            FROM daily_kline k{joins}
            WHERE k.ts_code = ?
            ORDER BY k.trade_date DESC
            LIMIT ?
        )
        ORDER BY trade_date ASC
    """


def _fetch_window(ts_code: str, days: int, with_joins: bool) -> List[sqlite3.Row]:
    """取最近 ``days`` 根 K 线原始行，按日期升序返回。"""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(_window_sql(with_joins), (ts_code, days))
        return cursor.fetchall()
    finally:
        conn.close()


def fetch_rich_klines(ts_code: str, days: int = 120) -> List[Dict[str, Any]]:
    """
    取最近 ``days`` 根“富”K 线 dict（按日期升序）。

    富 dict = 基础 OHLCV + prev_close/prev_vol + 量价派生标志
    （is_rise/is_beidou/is_suoliang/is_jiayin/is_yinxian/is_fangliang_yinxian）
    + 指标缓存（Bollinger/RSI/DMI/ADX）+ 资金流。这是 detect_*（战法检测）
    与 screener 评分函数共同期望的形状。
    """
    rows = _fetch_window(ts_code, days, with_joins=True)

    data_list: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        prev_close = rows[i - 1]["close"] if i > 0 else row["close"]
        prev_vol = rows[i - 1]["vol"] if i > 0 else row["vol"]

        data_list.append({
            "ts_code": row["ts_code"],
            "trade_date": row["trade_date"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "vol": row["vol"],
            "amount": row["amount"],
            "pct_chg": row["pct_chg"],
            "prev_close": prev_close,
            "prev_vol": prev_vol,
            "is_rise": row["close"] > prev_close,
            "is_beidou": row["vol"] >= prev_vol * 2,
            "is_suoliang": row["vol"] <= prev_vol * 0.5,
            "is_jiayin": row["close"] < row["open"] and row["close"] > prev_close,
            "is_yinxian": row["close"] < prev_close,
            "is_fangliang_yinxian": row["close"] < prev_close and row["vol"] > prev_vol * 1.5,

            # MDC 扩展字段（LEFT JOIN 可能为 NULL，统一 fallback 0）
            "boll_upper": row["boll_upper"] or 0,
            "boll_mid": row["boll_mid"] or 0,
            "boll_lower": row["boll_lower"] or 0,
            "rsi6": row["rsi6"] or 0,
            "adx": row["adx"] or 0,
            "dmi_plus": row["dmi_plus"] or 0,
            "dmi_minus": row["dmi_minus"] or 0,
            "net_mf": row["net_mf"] or 0,
            "large_inflow": (row["buy_lg_amount"] or 0) + (row["buy_elg_amount"] or 0),
            "large_outflow": (row["sell_lg_amount"] or 0) + (row["sell_elg_amount"] or 0),
        })

    return data_list


def fetch_daily_data(ts_code: str, days: int = 100) -> List["DailyData"]:
    """
    取最近 ``days`` 根 K 线为 ``DailyData`` 对象（按日期升序）。

    indicators 层消费此形状。不带指标/资金流 JOIN（保持原查询的精简开销）。
    """
    from .indicators import DailyData  # 惰性导入，避免 import 环

    rows = _fetch_window(ts_code, days, with_joins=False)

    data_list: List["DailyData"] = []
    for i, row in enumerate(rows):
        prev_close = rows[i - 1]["close"] if i > 0 else row["close"]
        data_list.append(DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row["amount"],
            pct_chg=row["pct_chg"],
            prev_close=prev_close,
        ))

    return data_list
