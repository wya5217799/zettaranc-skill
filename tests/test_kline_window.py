"""
回归测试：K 线取数窗口方向

Bug（已修）：strategies.core.get_kline_data 曾用
    ORDER BY trade_date ASC LIMIT ?
取到的是"最早 N 根"而非"最近 N 根"，导致战法信号与持仓诊断
分析的是一年多前的旧数据（indicators 层却用的是最新数据，报告自相矛盾）。

正确行为：取最近 days 根 K 线，且按时间升序返回。
"""

from tests.conftest import (
    write_klines_to_db, write_stock_basic, generate_uptrend_klines,
)

TS = "600519.SH"
TOTAL = 200
WINDOW = 120


def _seed(db_conn, n=TOTAL):
    """写入 n 根连续 K 线，返回原始行（升序）"""
    rows = generate_uptrend_klines(n=n, ts_code=TS, start_date="20250101")
    write_stock_basic(db_conn, ts_code=TS)
    write_klines_to_db(db_conn, rows)
    return rows


class TestStrategiesKlineWindow:
    """strategies.core.get_kline_data（返回 dict）"""

    def test_returns_newest_n_ascending(self, db_conn):
        from modules.strategies.core import get_kline_data
        rows = _seed(db_conn)
        newest = rows[-1]["trade_date"]
        expected_start = rows[TOTAL - WINDOW]["trade_date"]

        fetched = get_kline_data(TS, days=WINDOW)

        assert len(fetched) == WINDOW
        # 升序
        assert fetched[0]["trade_date"] < fetched[-1]["trade_date"]
        # 取的是"最近"窗口（含最新一天），不是最早一天
        assert fetched[-1]["trade_date"] == newest
        assert fetched[0]["trade_date"] == expected_start

    def test_does_not_return_oldest_window(self, db_conn):
        """旧 bug 会让首行 == 全表最早一天"""
        from modules.strategies.core import get_kline_data
        rows = _seed(db_conn)
        oldest = rows[0]["trade_date"]
        fetched = get_kline_data(TS, days=WINDOW)
        assert fetched[0]["trade_date"] != oldest


class TestIndicatorsKlineWindow:
    """indicators.get_kline_data（返回 DailyData）—— 这一支本就正确，锁定不回退"""

    def test_returns_newest_n_ascending(self, db_conn):
        from modules.indicators import get_kline_data
        rows = _seed(db_conn)
        newest = rows[-1]["trade_date"]

        fetched = get_kline_data(TS, days=WINDOW)

        assert len(fetched) == WINDOW
        assert fetched[0].trade_date < fetched[-1].trade_date
        assert fetched[-1].trade_date == newest

    def test_both_twins_agree_on_window(self, db_conn):
        """两个同名取数函数对同一 days 必须返回同一时间窗口"""
        from modules.indicators import get_kline_data as ind_kline
        from modules.strategies.core import get_kline_data as strat_kline
        _seed(db_conn)
        ind = ind_kline(TS, days=WINDOW)
        strat = strat_kline(TS, days=WINDOW)
        assert ind[0].trade_date == strat[0]["trade_date"]
        assert ind[-1].trade_date == strat[-1]["trade_date"]
