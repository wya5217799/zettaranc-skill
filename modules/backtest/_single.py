"""
单策略回测

包含:
- backtest_signals: 基于信号列表的核心回测引擎（纯计算，无外部 I/O）
- _signals_check_exit / _signals_handle_signal / _signals_calc_metrics: 内部辅助

注意: backtest_strategy（需要调用 get_kline_data / detect_all_strategies）
      定义在 modules/backtest/__init__.py，以保证 mock patch 路径正确。
"""

from typing import List, Dict, Any, Optional, Tuple

from modules.backtest._models import Trade, BacktestResult


def _signals_check_exit(
    k: Dict[str, Any],
    current_trade: Trade,
    result: BacktestResult,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Tuple[Optional[Trade], bool]:
    """检查持仓止损/止盈。返回 (current_trade, exited)。"""
    date = k['trade_date']
    day_high = k['high']
    day_low = k['low']

    # 止损
    if day_low <= current_trade.entry_price * (1 - stop_loss_pct):
        current_trade.exit_date = date
        current_trade.exit_price = current_trade.entry_price * (1 - stop_loss_pct)
        current_trade.pnl = current_trade.exit_price - current_trade.entry_price
        current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
        current_trade.exit_reason = 'stop_loss'
        result.trades.append(current_trade)
        return None, True

    # 止盈
    if day_high >= current_trade.entry_price * (1 + take_profit_pct):
        current_trade.exit_date = date
        current_trade.exit_price = current_trade.entry_price * (1 + take_profit_pct)
        current_trade.pnl = current_trade.exit_price - current_trade.entry_price
        current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
        current_trade.exit_reason = 'take_profit'
        result.trades.append(current_trade)
        return None, True

    return current_trade, False


def _signals_handle_signal(
    date: str,
    price: float,
    ts_code: str,
    sig: Any,
    current_trade: Optional[Trade],
    result: BacktestResult,
) -> Optional[Trade]:
    """处理买入/卖出信号。返回更新后的 current_trade。"""
    if sig.action == 'BUY' and current_trade is None:
        return Trade(
            ts_code=ts_code,
            entry_date=date,
            entry_price=price,
        )

    if sig.action == 'SELL' and current_trade is not None:
        current_trade.exit_date = date
        current_trade.exit_price = price
        current_trade.pnl = price - current_trade.entry_price
        current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
        current_trade.exit_reason = 'signal'
        result.trades.append(current_trade)
        return None

    return current_trade


def _signals_calc_metrics(result: BacktestResult) -> None:
    """计算回测统计指标（就地修改 result）。"""
    if not result.trades:
        return

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

        # 检查止损/止盈（如果持有中）
        if current_trade is not None:
            entry_high = max(entry_high, day_high)
            current_trade, exited = _signals_check_exit(
                k, current_trade, result, stop_loss_pct, take_profit_pct
            )
            if exited:
                continue

        # 处理当天信号
        sig = signal_map.get(date)
        if sig is None:
            continue

        current_trade = _signals_handle_signal(
            date, price, ts_code, sig, current_trade, result
        )
        if current_trade is not None and current_trade.entry_date == date:
            entry_high = price

    # 数据末尾强制平仓
    if current_trade is not None and klines:
        last = klines[-1]
        current_trade.exit_date = last['trade_date']
        current_trade.exit_price = last['close']
        current_trade.pnl = last['close'] - current_trade.entry_price
        current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price
        current_trade.exit_reason = 'end_of_data'
        result.trades.append(current_trade)

    _signals_calc_metrics(result)

    return result


