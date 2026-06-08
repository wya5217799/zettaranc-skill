"""
数据访问层：DB 连接 / 股票列表 / K线 / 大盘状态
"""

import sqlite3
import os
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from ._models import MarketStatus

# 数据库路径默认值（实际连接时动态读取 DB_PATH 环境变量）
DB_PATH = "data/stock_data.db"


def get_db_connection() -> sqlite3.Connection:
    """获取数据库连接（动态读取 DB_PATH 环境变量，未设置时回退到项目根下默认路径）"""
    path_str = os.getenv("DB_PATH", DB_PATH)
    path = Path(path_str)
    if not path.is_absolute():
        path = (Path(__file__).parent.parent.parent / path_str).resolve()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_stocks() -> List[Dict]:
    """获取所有股票基本信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ts_code, name, industry, market
        FROM stock_basic
        WHERE market IN ('主板', '创业板', '科创板')
        ORDER BY ts_code
    """)
    stocks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stocks


def get_recent_klines(ts_code: str, days: int = 60) -> List[Dict]:
    """
    获取近期"富"K线数据（按日期升序，最近 days 根）。

    取数逻辑已收敛到 modules.kline_data：返回的富 dict 是评分函数所需精简字段的
    超集，且自带 is_beidou/is_suoliang 等派生标志，因此 detect_* 战法检测可直接
    复用同一份数据，无需再二次取数（历史上 thin→rich 的二次取数正是 KeyError 之源）。
    """
    from modules.kline_data import fetch_rich_klines
    return fetch_rich_klines(ts_code, days)


def get_market_status() -> MarketStatus:
    """
    获取大盘状态（简化版，用主要指数代替）
    """
    today = datetime.now().strftime("%Y%m%d")

    # 获取沪深300成分股简单评估
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ts_code FROM stock_basic
        WHERE market IN ('主板')
        LIMIT 100
    """)
    stocks = [row['ts_code'] for row in cursor.fetchall()]

    rise_count = 0
    total_count = 0

    for ts_code in stocks[:20]:
        cursor.execute("""
            SELECT pct_chg FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT 1
        """, (ts_code,))
        row = cursor.fetchone()
        if row:
            total_count += 1
            if row['pct_chg'] > 0:
                rise_count += 1

    conn.close()

    # 计算涨跌家数比
    if total_count > 0:
        rise_ratio = rise_count / total_count
    else:
        rise_ratio = 0.5

    # 大盘状态判断
    if rise_ratio >= 0.6:
        direction = "LONG"
        strength = 75
        reasons = ["上涨家数占优", "市场活跃"]
    elif rise_ratio <= 0.4:
        direction = "SHORT"
        strength = 25
        reasons = ["下跌家数较多", "注意风险"]
    else:
        direction = "NEUTRAL"
        strength = 50
        reasons = ["多空均衡", "观望为主"]

    return MarketStatus(
        trade_date=today,
        is_trading=True,
        market_direction=direction,
        market_strength=strength,
        reasons=reasons
    )
