"""
screener.py 选股测试
"""

import pytest
from modules.screener import (
    StockScore, MarketStatus,
    calculate_ma, calculate_vol_ma, calculate_kdj, calculate_bbi,
    is_perfect_pattern, score_b1_opportunity, score_trend,
    score_volume_pattern, score_risk,
)
from tests.conftest import generate_uptrend_klines, generate_downtrend_klines


class TestStockScore:
    def test_rating_excellent(self):
        s = StockScore(ts_code="600519.SH", score=85)
        assert "★" in s.rating

    def test_rating_poor(self):
        s = StockScore(ts_code="600519.SH", score=10)
        assert "★" in s.rating


class TestMarketStatus:
    def test_defaults(self):
        ms = MarketStatus(trade_date="20260428")
        assert ms.is_trading is True
        assert ms.market_direction == "NEUTRAL"


class TestCalculateMA:
    def test_basic(self):
        assert calculate_ma([1, 2, 3, 4, 5], 5) == 3.0

    def test_insufficient(self):
        assert calculate_ma([1], 5) == 0


class TestCalculateVolMA:
    def test_basic(self):
        assert calculate_vol_ma([100, 200, 300, 400, 500], 5) == 300.0

    def test_insufficient(self):
        assert calculate_vol_ma([100], 5) == 0


class TestCalculateKDJ:
    def test_returns_tuple(self):
        klines = generate_uptrend_klines(n=20)
        k, d, j = calculate_kdj(klines)
        assert isinstance(k, float)

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        k, d, j = calculate_kdj(klines)
        assert (k, d, j) == (50, 50, 50)


class TestCalculateBBI:
    def test_basic(self):
        klines = generate_uptrend_klines(n=30)
        bbi = calculate_bbi(klines)
        assert bbi > 0

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert calculate_bbi(klines) == 0


class TestIsPerfectPattern:
    def test_uptrend_perfect(self):
        klines = generate_uptrend_klines(n=50)
        is_perfect, reasons = is_perfect_pattern(klines)
        assert isinstance(is_perfect, bool)
        assert isinstance(reasons, list)

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        is_perfect, reasons = is_perfect_pattern(klines)
        assert is_perfect is False
        assert "数据不足" in reasons


class TestScoreB1Opportunity:
    def test_uptrend_low_score(self):
        klines = generate_uptrend_klines(n=50)
        score, reasons = score_b1_opportunity(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, reasons = score_b1_opportunity(klines)
        assert score == 0
        assert "数据不足" in reasons


class TestScoreTrend:
    def test_uptrend(self):
        klines = generate_uptrend_klines(n=50, daily_pct=1.0)
        score, direction = score_trend(klines)
        assert 0 <= score <= 100
        assert direction in ("上升", "下降", "震荡")

    def test_downtrend(self):
        klines = generate_downtrend_klines(n=50)
        score, direction = score_trend(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, direction = score_trend(klines)
        assert score == 50
        assert direction == "震荡"


class TestScoreVolumePattern:
    def test_basic(self):
        klines = generate_uptrend_klines(n=20)
        score, reasons = score_volume_pattern(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        score, reasons = score_volume_pattern(klines)
        assert score == 50
        assert "数据不足" in reasons


class TestScoreRisk:
    def test_uptrend_low_risk(self):
        klines = generate_uptrend_klines(n=70)
        score, warnings = score_risk(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, warnings = score_risk(klines)
        assert score == 50
        assert "数据不足" in warnings


_ALL_CRITERIA = [
    "b1", "perfect", "oversold", "breakout",
    "super_b1", "changan", "b2_breakout", "b3_consensus",
    "build_wave", "xishou", "safe",
]


class TestScreenStocksIntegration:
    """回归：_filter_stock 对战法类 criteria（super_b1 / b2_breakout / changan /
    b3_consensus）曾用 get_recent_klines 的精简 dict 调 detect_*，抛
    KeyError('is_beidou' / 'is_suoliang')。现改用 strategies.core 的富 K 线。
    覆盖全部 criteria，断言不抛异常且返回 list。"""

    @pytest.mark.parametrize("criteria", _ALL_CRITERIA)
    def test_criteria_no_crash(self, db_conn, criteria):
        from modules.screener import screen_stocks
        from tests.conftest import (
            write_klines_to_db, write_stock_basic, generate_b1_scenario,
        )
        write_stock_basic(db_conn, ts_code="600519.SH")
        write_klines_to_db(db_conn, generate_b1_scenario(ts_code="600519.SH"))

        results = screen_stocks(criteria=criteria, max_stocks=5, use_parallel=False)
        assert isinstance(results, list)


class TestCmdScreenWiring:
    """回归：cmd_screen 曾构造空的 StockScore dataclass 并读取不存在的属性
    （is_b2 / sb1_score / is_perfect_pattern / total_score），异常被
    except 吞掉 → 永远 0 命中。现应映射到 screen_stocks 真正引擎并能跑通。"""

    @pytest.mark.parametrize(
        "strategy",
        ['B1', 'B2', '完美图形', '超级B1', '建仓波', '吸筹', '安全'],
    )
    def test_cmd_screen_runs(self, db_conn, strategy, capsys):
        from argparse import Namespace
        from modules.cli import cmd_screen
        from tests.conftest import (
            write_klines_to_db, write_stock_basic, generate_b1_scenario,
        )
        write_stock_basic(db_conn, ts_code="600519.SH")
        write_klines_to_db(db_conn, generate_b1_scenario(ts_code="600519.SH"))

        # 不应抛异常（旧 bug 下战法类策略会静默吞异常 / 0 命中）
        cmd_screen(Namespace(strategy=strategy, limit=5, scan=5))
        out = capsys.readouterr().out
        assert "筛选条件" in out
        assert "命中" in out
