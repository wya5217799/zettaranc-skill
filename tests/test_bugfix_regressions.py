"""
回归测试：已修复 Bug 的防守性测试

每个测试均为差异测试（differential test）：
  - 变体 (a) 不满足修复条件 → 验证不产生信号
  - 变体 (b) 满足修复条件   → 验证产生预期信号

这样只要 bug 被重新引入，至少一个 assert 会失败。
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from modules.strategies import analyze_kirin_phase, detect_yidong_dilian, StrategySignal
from modules.backtest._models import Position, PortfolioBacktestResult
from modules.backtest._portfolio import _portfolio_exit_pass, _portfolio_signal_pass


# ============================================================
# 辅助函数
# ============================================================

def _make_kline(trade_date: str, close: float, vol: float,
                is_rise: bool = True,
                is_beidou: bool = False,
                is_suoliang: bool = False) -> dict:
    """最小化构造一根 K 线 dict，与 conftest.make_kline_row 字段一致。"""
    return {
        "ts_code": "600519.SH",
        "trade_date": trade_date,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "vol": vol,
        "amount": close * vol,
        "pct_chg": 1.0 if is_rise else -1.0,
        "prev_close": close / (1.01 if is_rise else 0.99),
        "prev_vol": vol,
        "is_rise": is_rise,
        "is_beidou": is_beidou,
        "is_suoliang": is_suoliang,
        "is_jiayin": False,
        "is_yinxian": not is_rise,
        "is_fangliang_yinxian": False,
    }


def _dates(start: str, n: int):
    """生成从 start 起连续 n 天的日期字符串列表。"""
    dt = datetime.strptime(start, "%Y%m%d")
    return [(dt + timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


def _make_signal_mock(trade_date: str, action: str = "BUY", priority_value: int = 2):
    """构造模拟策略信号（与 test_backtest.py 的 _make_signal 相同形式）。"""
    sig = MagicMock()
    sig.trade_date = trade_date
    sig.action = action
    sig.priority = MagicMock()
    sig.priority.value = priority_value
    return sig


# ============================================================
# Bug 1 — kirin.py::analyze_kirin_phase  吸筹 缩量门控
# ============================================================

class TestKirinPhaseShirinkGate:
    """
    修复：len>=60 时，吸筹判断必须满足 is_shrink（近30日均量 < 前30日均量）。
    旧 bug：is_shrink 参与计算但从未进入条件，低位+红肥绿瘦即报吸筹。

    构造思路
    --------
    * 60 根 K 线，使 is_shrink 门控生效
    * 近 30 根：全部阴线（is_rise=False）+ 低价（满足 is_low）+ 红肥绿瘦
      - 为制造"红肥绿瘦"，近 30 根中安插 8 根红线且其均量 >> 绿线均量
    * 变体 (a)：近 30 根成交量 > 前 30 根 → is_shrink=False → 不应报吸筹
    * 变体 (b)：近 30 根成交量 < 前 30 根 → is_shrink=True  → 应报吸筹
    """

    def _build_klines(self, recent_vol: float, prior_vol: float) -> list:
        """
        构造 60 根 K 线：
          前 30 根（-60..-30）：成交量 prior_vol，价格在高位（100），全阳线
          近 30 根（-30..-1） ：成交量由 recent_vol 控制
            - 前 10 根：阴线（绿线，量=recent_vol*0.2）—— 从 90 跌到 75
            - 后 20 根：阳线（红线，量=recent_vol*4.0）—— 从 75 小幅回升

          价格安排保证：
            is_low = min(recent_closes) <= max(recent_closes)*0.85
              → 75/90 = 0.833 < 0.85 ✓
            红肥绿瘦 red_avg > green_avg*1.2
              → red_avg = recent_vol*4, green_avg = recent_vol*0.2 (20× ≫ 1.2×) ✓
            up_days（近30根中 close[i]>close[i-1] 的次数）= 19 >= 10
              → 阻止「回落」阶段覆盖「吸筹」（回落条件需 up_days < 10）✓
        """
        dates = _dates("20250101", 60)
        klines = []

        # 前 30 根：高位 100，全阳线
        for i in range(30):
            klines.append(_make_kline(dates[i], close=100.0, vol=prior_vol, is_rise=True))

        green_vol = recent_vol * 0.2
        red_vol   = recent_vol * 4.0

        # 近30根：前10根阴线（90→75），后20根阳线（75→85）
        # up_days = 19 阻止回落条件（up_days<10）
        for i in range(30, 40):  # 10 根阴线
            price = 90.0 - (i - 30) * 1.5   # 90, 88.5, ..., 76.5
            klines.append(_make_kline(dates[i], close=price, vol=green_vol, is_rise=False))

        for i in range(40, 60):  # 20 根阳线
            price = 75.0 + (i - 40) * 0.5   # 75, 75.5, ..., 84.5
            klines.append(_make_kline(dates[i], close=price, vol=red_vol, is_rise=True))

        return klines

    def test_no_shrink_not_xishou(self):
        """
        变体 (a)：近 30 根均量 > 前 30 根均量 → is_shrink=False → 不报吸筹。
        若 bug 被重新引入（去掉 is_shrink 门控），此测试会失败（变成报吸筹）。
        """
        # prior_vol=1000, recent_vol=2000 → 近期放量，is_shrink=False
        klines = self._build_klines(recent_vol=2000.0, prior_vol=1000.0)
        result = analyze_kirin_phase(klines)
        assert result["phase"] != "吸筹", (
            f"期望非吸筹（近期放量，is_shrink=False），实际 phase={result['phase']}"
        )

    def test_shrink_is_xishou(self):
        """
        变体 (b)：近 30 根均量 < 前 30 根均量 → is_shrink=True → 应报吸筹。
        若 bug 被重新引入，此测试仍能通过（旧行为也报吸筹），
        但与 (a) 结合可确认门控逻辑正常区分两种场景。
        """
        # prior_vol=2000, recent_vol=500 → 近期缩量，is_shrink=True
        klines = self._build_klines(recent_vol=500.0, prior_vol=2000.0)
        result = analyze_kirin_phase(klines)
        assert result["phase"] == "吸筹", (
            f"期望吸筹（低位+红肥绿瘦+缩量），实际 phase={result['phase']}"
        )

    def test_variants_differ(self):
        """差异测试：两个变体必须产生不同结果，否则测试失效。"""
        klines_no_shrink  = self._build_klines(recent_vol=2000.0, prior_vol=1000.0)
        klines_has_shrink = self._build_klines(recent_vol=500.0,  prior_vol=2000.0)
        result_a = analyze_kirin_phase(klines_no_shrink)
        result_b = analyze_kirin_phase(klines_has_shrink)
        assert result_a["phase"] != result_b["phase"], (
            "两个变体应产生不同 phase，否则测试无法区分修复前后行为"
        )


# ============================================================
# Bug 2 — compound_strategies.py::detect_yidong_dilian  回调缩量门控
# ============================================================

class TestYidongDilianSuoliangGate:
    """
    修复：回调期间（不含今日）必须有至少一根缩量 K 线（is_suoliang=True）。
    旧 bug：has_suoliang 计算了却从未作为门槛，回调全部放量也误报买点。

    构造思路
    --------
    * 异动日（is_beidou=True, is_rise=True）位于 index-3
    * 回调期 = index-2, index-1（不含今日）
    * 今日（index）is_suoliang=True
    * 变体 (a)：回调期 is_suoliang=False → 无信号（None）
    * 变体 (b)：回调期 index-2 is_suoliang=True → 有信号（StrategySignal）
    """

    def _build_base_klines(self, pullback_suoliang: bool) -> list:
        """
        index=5 为今日，共 6 根 K 线。
        klines[2]（index-3）：异动日
        klines[3]（index-2）：回调日 1，is_suoliang 由参数控制
        klines[4]（index-1）：回调日 2，is_suoliang=False
        klines[5]（index=5）：今日，is_suoliang=True
        """
        dates = _dates("20260101", 6)
        klines = []

        # 前 2 根：普通 K 线
        klines.append(_make_kline(dates[0], close=100.0, vol=10000.0))
        klines.append(_make_kline(dates[1], close=101.0, vol=10000.0))

        # 异动日（index-3=klines[2]）：放量上涨
        klines.append(_make_kline(
            dates[2], close=105.0, vol=50000.0,
            is_rise=True, is_beidou=True, is_suoliang=False
        ))

        # 回调日 1（index-2=klines[3]）：缩量由参数控制
        klines.append(_make_kline(
            dates[3], close=103.0, vol=5000.0 if pullback_suoliang else 40000.0,
            is_rise=False, is_beidou=False,
            is_suoliang=pullback_suoliang
        ))

        # 回调日 2（index-1=klines[4]）：不缩量
        klines.append(_make_kline(
            dates[4], close=102.0, vol=30000.0,
            is_rise=False, is_beidou=False, is_suoliang=False
        ))

        # 今日（index=5=klines[5]）：地量
        klines.append(_make_kline(
            dates[5], close=101.0, vol=3000.0,
            is_rise=False, is_beidou=False, is_suoliang=True
        ))

        return klines

    def test_no_pullback_suoliang_returns_none(self):
        """
        变体 (a)：回调期无缩量 → detect_yidong_dilian 返回 None。
        若 bug 被重新引入，此处会返回 StrategySignal，测试失败。
        """
        klines = self._build_base_klines(pullback_suoliang=False)
        result = detect_yidong_dilian(klines, index=5)
        assert result is None, (
            f"期望 None（回调期无缩量，不应触发信号），实际 result={result}"
        )

    def test_with_pullback_suoliang_returns_signal(self):
        """
        变体 (b)：回调期有缩量 → detect_yidong_dilian 返回 StrategySignal。
        确认修复后正常信号仍能产生。
        """
        klines = self._build_base_klines(pullback_suoliang=True)
        result = detect_yidong_dilian(klines, index=5)
        assert result is not None, (
            "期望 StrategySignal（异动+回调缩量+今日地量），实际 None"
        )
        assert isinstance(result, StrategySignal)

    def test_variants_differ(self):
        """差异测试：两个变体必须一个返回 None，一个返回信号。"""
        klines_a = self._build_base_klines(pullback_suoliang=False)
        klines_b = self._build_base_klines(pullback_suoliang=True)
        result_a = detect_yidong_dilian(klines_a, index=5)
        result_b = detect_yidong_dilian(klines_b, index=5)
        assert result_a is None and result_b is not None, (
            f"期望 (None, StrategySignal)，实际 ({result_a}, {result_b})"
        )


# ============================================================
# Bug 3 — _portfolio.py  止损/止盈出场后禁止同日再买入
# ============================================================

class TestPortfolioNoSameDayReentry:
    """
    修复：_portfolio_exit_pass 返回 exited_today 集合，
         _portfolio_signal_pass 对集合内股票跳过买入。
    旧 bug：exited_today 从未被传入 signal_pass，止损出场后当日可再次买入。

    测试策略：直接对两个辅助函数进行单元测试，避免需要完整 backtest_portfolio 配置。

    1. 构造一只股票已持仓，且当日 day_low <= entry*(1-stop_loss_pct) → 触发止损
    2. 同时该股票当日有 BUY 信号
    3. 将 exited_today 传入 signal_pass → 断言未被再次买入（position 仍为 None）
    4. 作为对照：空 exited_today 集合 → 断言可以买入（position 不为 None）
    """

    def _build_stock_data(self, entry_price: float, stop_loss_date: str) -> dict:
        """
        构造 stock_data 结构（与 _portfolio.py 期望一致）。
        持仓：entry_price，当日 low = entry * 0.90（触发 7% 止损）。
        同日有 BUY 信号。
        """
        # 持仓
        position = Position(
            ts_code="600519.SH",
            entry_date="20260101",
            entry_price=entry_price,
            shares=100,
            cost_basis=entry_price * 100,
            current_price=entry_price,
            current_value=entry_price * 100,
            high_since_entry=entry_price,
        )

        # 当日 K 线：close 比 entry 低，但 low 跌破止损线
        kline = {
            "trade_date": stop_loss_date,
            "open": entry_price * 0.95,
            "high": entry_price * 0.96,
            "low": entry_price * 0.90,   # < entry * (1 - 0.07) = entry * 0.93
            "close": entry_price * 0.94,
            "vol": 20000.0,
            "amount": entry_price * 0.94 * 20000.0,
            "pct_chg": -6.0,
        }

        # BUY 信号
        buy_signal = _make_signal_mock(stop_loss_date, action="BUY", priority_value=2)

        stock_data = {
            "600519.SH": {
                "klines": [kline],
                "signal_map": {stop_loss_date: [buy_signal]},
                "klines_map": {stop_loss_date: kline},
                "max_weight": 0.5,
                "position": position,
            }
        }
        return stock_data

    def test_stop_loss_prevents_same_day_reentry(self):
        """
        主测试：止损出场后，将 exited_today 传入 signal_pass，
        确认该股票 position 仍为 None（未被再次买入）。
        若 bug 被重新引入（signal_pass 不检查 exited_today），此测试失败。
        """
        entry_price = 100.0
        date = "20260110"
        stock_data = self._build_stock_data(entry_price, date)
        result = PortfolioBacktestResult(initial_capital=100000.0)
        cash = 50000.0

        # 第一遍：出场检查（触发止损）
        cash_after_exit, exited_today = _portfolio_exit_pass(
            date, stock_data, result, cash,
            stop_loss_pct=0.07, take_profit_pct=0.15
        )

        # 确认确实触发了止损
        assert "600519.SH" in exited_today, "止损应将股票加入 exited_today 集合"
        assert stock_data["600519.SH"]["position"] is None, "止损后持仓应为 None"

        # 第二遍：信号处理（传入 exited_today，含当日出场的股票）
        cash_after_signal = _portfolio_signal_pass(
            date, stock_data, result, cash_after_exit, exited_today
        )

        # 断言：该股票 position 仍为 None（未被同日再次买入）
        assert stock_data["600519.SH"]["position"] is None, (
            "止损出场后当日不应重新买入（exited_today 门控失效）"
        )

    def test_no_exit_allows_buy(self):
        """
        对照组：空 exited_today 时，BUY 信号应正常买入（确认测试逻辑本身有效）。
        """
        entry_price = 100.0
        date = "20260110"
        stock_data = self._build_stock_data(entry_price, date)
        result = PortfolioBacktestResult(initial_capital=100000.0)
        cash = 50000.0

        # 手动清空持仓（模拟无持仓状态），这样 signal_pass 会尝试买入
        stock_data["600519.SH"]["position"] = None

        # 传入空的 exited_today → 不阻止买入
        cash_after = _portfolio_signal_pass(
            date, stock_data, result, cash, exited_today=set()
        )

        # 有足够资金且 exited_today 为空，应成功买入
        assert stock_data["600519.SH"]["position"] is not None, (
            "无 exited_today 门控时，BUY 信号应成功买入"
        )

    def test_guard_differentiates_behavior(self):
        """
        差异测试：exited_today 中有该股 vs 无该股 → position 结果不同。
        """
        entry_price = 100.0
        date = "20260110"
        result = PortfolioBacktestResult(initial_capital=100000.0)
        cash = 50000.0

        # 场景 A：exited_today 含该股 → 不买入
        sd_a = self._build_stock_data(entry_price, date)
        sd_a["600519.SH"]["position"] = None  # 已出场，测试信号处理
        _portfolio_signal_pass(date, sd_a, result, cash, exited_today={"600519.SH"})
        pos_a = sd_a["600519.SH"]["position"]

        # 场景 B：exited_today 为空 → 正常买入
        sd_b = self._build_stock_data(entry_price, date)
        sd_b["600519.SH"]["position"] = None
        _portfolio_signal_pass(date, sd_b, result, cash, exited_today=set())
        pos_b = sd_b["600519.SH"]["position"]

        assert pos_a is None, "exited_today 含该股时不应买入"
        assert pos_b is not None, "exited_today 为空时应正常买入"
