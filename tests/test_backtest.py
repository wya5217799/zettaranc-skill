"""
回测框架测试
"""

import pytest
from modules.backtest import backtest_signals, BacktestResult, Trade


class TestBacktestSignals:
    def test_empty_signals(self):
        result = backtest_signals([], [], 'TEST')
        assert result.total_trades == 0
        assert result.win_rate == 0.0

    def test_single_buy_sell(self):
        """简单买入卖出，盈利"""
        signals = [type('S', (), {'trade_date': '20260110', 'action': 'BUY'})(),
                   type('S', (), {'trade_date': '20260115', 'action': 'SELL'})()]
        klines = [
            {'trade_date': '20260110', 'close': 100.0, 'high': 101.0, 'low': 99.0},
            {'trade_date': '20260111', 'close': 102.0, 'high': 103.0, 'low': 101.0},
            {'trade_date': '20260115', 'close': 110.0, 'high': 111.0, 'low': 109.0},
        ]

        result = backtest_signals(signals, klines, 'TEST')
        assert result.total_trades == 1
        assert result.win_trades == 1
        assert result.loss_trades == 0
        assert result.win_rate == 1.0
        assert result.trades[0].pnl_pct == pytest.approx(0.10, rel=1e-3)

    def test_stop_loss(self):
        """触发止损"""
        signals = [type('S', (), {'trade_date': '20260110', 'action': 'BUY'})()]
        klines = [
            {'trade_date': '20260110', 'close': 100.0, 'high': 101.0, 'low': 99.0},
            {'trade_date': '20260111', 'close': 92.0, 'high': 93.0, 'low': 90.0},  # 跌破止损
        ]

        result = backtest_signals(signals, klines, 'TEST', stop_loss_pct=0.07)
        assert result.total_trades == 1
        assert result.loss_trades == 1
        assert result.trades[0].exit_reason == 'stop_loss'
        assert result.trades[0].pnl_pct == pytest.approx(-0.07, rel=1e-3)

    def test_take_profit(self):
        """触发止盈"""
        signals = [type('S', (), {'trade_date': '20260110', 'action': 'BUY'})()]
        klines = [
            {'trade_date': '20260110', 'close': 100.0, 'high': 101.0, 'low': 99.0},
            {'trade_date': '20260111', 'close': 120.0, 'high': 120.0, 'low': 115.0},  # 突破止盈
        ]

        result = backtest_signals(signals, klines, 'TEST', take_profit_pct=0.15)
        assert result.total_trades == 1
        assert result.win_trades == 1
        assert result.trades[0].exit_reason == 'take_profit'
        assert result.trades[0].pnl_pct == pytest.approx(0.15, rel=1e-3)

    def test_end_of_data_force_close(self):
        """数据末尾强制平仓"""
        signals = [type('S', (), {'trade_date': '20260110', 'action': 'BUY'})()]
        klines = [
            {'trade_date': '20260110', 'close': 100.0, 'high': 101.0, 'low': 99.0},
            {'trade_date': '20260111', 'close': 105.0, 'high': 106.0, 'low': 104.0},
        ]

        result = backtest_signals(signals, klines, 'TEST')
        assert result.total_trades == 1
        assert result.trades[0].exit_reason == 'end_of_data'

    def test_no_double_position(self):
        """不会重复开仓"""
        signals = [
            type('S', (), {'trade_date': '20260110', 'action': 'BUY'})(),
            type('S', (), {'trade_date': '20260111', 'action': 'BUY'})(),  # 重复买入，应忽略
            type('S', (), {'trade_date': '20260115', 'action': 'SELL'})(),
        ]
        klines = [
            {'trade_date': '20260110', 'close': 100.0, 'high': 101.0, 'low': 99.0},
            {'trade_date': '20260111', 'close': 102.0, 'high': 103.0, 'low': 101.0},
            {'trade_date': '20260115', 'close': 110.0, 'high': 111.0, 'low': 109.0},
        ]

        result = backtest_signals(signals, klines, 'TEST')
        assert result.total_trades == 1


class TestBacktestResult:
    def test_summary_format(self):
        result = BacktestResult(ts_code='TEST', total_trades=5, win_trades=3, loss_trades=2)
        summary = result.summary()
        assert 'TEST' in summary
        assert '5' in summary
        assert '胜率' in summary
