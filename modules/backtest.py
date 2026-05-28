#!/usr/bin/env python3
"""
策略回测框架

基于策略信号 + 历史K线，模拟交易并输出统计指标。

用法：
    from modules.backtest import backtest_strategy
    result = backtest_strategy('600487.SH', days=240)
    print(result.summary())
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


@dataclass
class Trade:
    """单笔交易记录"""
    ts_code: str
    entry_date: str
    entry_price: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    exit_reason: str = ""  # 'signal', 'stop_loss', 'take_profit', 'end_of_data'


@dataclass
class BacktestResult:
    """回测结果"""
    ts_code: str
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    avg_return: float = 0.0
    avg_hold_days: float = 0.0
    total_return: float = 0.0
    trades: List[Trade] = field(default_factory=list)

    def summary(self) -> str:
        """格式化回测摘要"""
        lines = [
            f"{'='*60}",
            f"回测结果: {self.ts_code}",
            f"{'='*60}",
            f"总交易次数: {self.total_trades}",
            f"盈利次数:   {self.win_trades}",
            f"亏损次数:   {self.loss_trades}",
            f"胜率:       {self.win_rate:.1%}",
            f"盈亏比:     {self.profit_factor:.2f}",
            f"最大回撤:   {self.max_drawdown:.1%}",
            f"平均收益:   {self.avg_return:.2%}",
            f"平均持仓:   {self.avg_hold_days:.1f}天",
            f"总收益率:   {self.total_return:.2%}",
            f"{'='*60}",
        ]

        if self.trades:
            lines.append("最近5笔交易:")
            for t in self.trades[-5:]:
                status = "🟢" if t.pnl > 0 else "🔴" if t.pnl < 0 else "⚪"
                lines.append(
                    f"  {status} {t.entry_date}→{t.exit_date or '持有中'} "
                    f"{t.pnl_pct:+.2f}% ({t.exit_reason})"
                )

        return "\n".join(lines)


def backtest_signals(
    signals: List[Any],
    klines: List[Dict[str, Any]],
    ts_code: str,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> BacktestResult:
    """
    基于策略信号进行回测

    Args:
        signals: 策略信号列表（StrategySignal），按日期升序
        klines: 历史K线数据，按日期升序
        ts_code: 股票代码
        stop_loss_pct: 止损比例（默认7%）
        take_profit_pct: 止盈比例（默认15%）

    Returns:
        BacktestResult
    """
    result = BacktestResult(ts_code=ts_code)

    if not klines:
        return result

    # 构建日期 -> 信号 映射
    signal_map: Dict[str, Any] = {}
    for sig in signals:
        signal_map[sig.trade_date] = sig

    # 当前持仓
    current_trade: Optional[Trade] = None
    entry_high: float = 0.0

    # 按日期升序遍历 K 线（确保每天都检查止损/止盈）
    for k in klines:
        date = k['trade_date']
        price = k['close']
        day_high = k['high']
        day_low = k['low']

        # 检查止损/止盈（如果持有中）
        if current_trade is not None:
            entry_high = max(entry_high, day_high)

            # 止损
            if day_low <= current_trade.entry_price * (1 - stop_loss_pct):
                current_trade.exit_date = date
                current_trade.exit_price = current_trade.entry_price * (1 - stop_loss_pct)
                current_trade.pnl = current_trade.exit_price - current_trade.entry_price
                current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
                current_trade.exit_reason = 'stop_loss'
                result.trades.append(current_trade)
                current_trade = None
                continue

            # 止盈
            if day_high >= current_trade.entry_price * (1 + take_profit_pct):
                current_trade.exit_date = date
                current_trade.exit_price = current_trade.entry_price * (1 + take_profit_pct)
                current_trade.pnl = current_trade.exit_price - current_trade.entry_price
                current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
                current_trade.exit_reason = 'take_profit'
                result.trades.append(current_trade)
                current_trade = None
                continue

        # 处理当天信号
        sig = signal_map.get(date)
        if sig is None:
            continue

        # 买入信号
        if sig.action == 'BUY' and current_trade is None:
            current_trade = Trade(
                ts_code=ts_code,
                entry_date=date,
                entry_price=price,
            )
            entry_high = price

        # 卖出信号
        elif sig.action == 'SELL' and current_trade is not None:
            current_trade.exit_date = date
            current_trade.exit_price = price
            current_trade.pnl = price - current_trade.entry_price
            current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
            current_trade.exit_reason = 'signal'
            result.trades.append(current_trade)
            current_trade = None

    # 数据末尾强制平仓
    if current_trade is not None and klines:
        last = klines[-1]
        current_trade.exit_date = last['trade_date']
        current_trade.exit_price = last['close']
        current_trade.pnl = last['close'] - current_trade.entry_price
        current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
        current_trade.exit_reason = 'end_of_data'
        result.trades.append(current_trade)

    # 计算统计指标
    if result.trades:
        result.total_trades = len(result.trades)
        result.win_trades = sum(1 for t in result.trades if t.pnl > 0)
        result.loss_trades = sum(1 for t in result.trades if t.pnl < 0)
        result.win_rate = result.win_trades / result.total_trades

        total_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        result.avg_return = sum(t.pnl_pct for t in result.trades) / result.total_trades
        result.avg_hold_days = sum(t.hold_days for t in result.trades) / result.total_trades

        # 最大回撤
        peak = 0.0
        drawdown = 0.0
        cumulative = 0.0
        for t in result.trades:
            cumulative += t.pnl_pct
            peak = max(peak, cumulative)
            drawdown = max(drawdown, peak - cumulative)
        result.max_drawdown = drawdown

        # 总收益率（复利）
        result.total_return = 1.0
        for t in result.trades:
            result.total_return *= (1 + t.pnl_pct)
        result.total_return -= 1.0

    return result


def backtest_strategy(
    ts_code: str,
    days: int = 240,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> BacktestResult:
    """
    对单只股票进行策略回测（便捷函数）

    Args:
        ts_code: 股票代码
        days: 回测天数
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例

    Returns:
        BacktestResult
    """
    from modules.strategies import detect_all_strategies, get_kline_data

    # 取消代理
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    klines = get_kline_data(ts_code, days)
    signals = detect_all_strategies(ts_code, days)

    return backtest_signals(signals, klines, ts_code, stop_loss_pct, take_profit_pct)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='策略回测')
    parser.add_argument('ts_code', help='股票代码')
    parser.add_argument('--days', type=int, default=240, help='回测天数')
    parser.add_argument('--stop-loss', type=float, default=0.07, help='止损比例')
    parser.add_argument('--take-profit', type=float, default=0.15, help='止盈比例')

    args = parser.parse_args()

    result = backtest_strategy(
        args.ts_code,
        days=args.days,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )
    print(result.summary())
