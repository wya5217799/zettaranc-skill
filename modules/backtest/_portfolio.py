"""
多股票组合回测辅助函数

包含:
- _portfolio_exit_pass / _portfolio_signal_pass / _portfolio_force_close: 内部辅助
  （纯计算，无外部 I/O）

注意: backtest_portfolio（需要调用 get_kline_data / detect_all_strategies）
      定义在 modules/backtest/__init__.py，以保证 mock patch 路径正确。
"""

from typing import Any, Dict, Tuple

from modules.backtest._models import (
    Trade, Position, PortfolioBacktestResult,
    _calc_shares,
)


def _portfolio_exit_pass(
    date: str,
    stock_data: Dict[str, Any],
    result: PortfolioBacktestResult,
    cash: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Tuple[float, set]:
    """止损/止盈出场检查（每日第一遍）。返回 (更新后的 cash, 当日已出场的股票代码集合)。"""
    exited_today: set = set()

    for ts_code, data in stock_data.items():
        pos = data['position']
        if pos is None:
            continue

        kline = data['klines_map'].get(date)
        if not kline:
            continue

        price = kline['close']
        day_high = kline['high']
        day_low = kline['low']
        pos.update_price(price)

        if day_low <= pos.entry_price * (1 - stop_loss_pct):
            exit_price = pos.entry_price * (1 - stop_loss_pct)
            pnl = (exit_price - pos.entry_price) * pos.shares
            cash += pos.shares * exit_price
            result.trades.append(Trade(
                ts_code=ts_code,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                exit_date=date,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=(exit_price - pos.entry_price) / pos.entry_price,
                exit_reason='stop_loss',
            ))
            data['position'] = None
            exited_today.add(ts_code)

        elif day_high >= pos.entry_price * (1 + take_profit_pct):
            exit_price = pos.entry_price * (1 + take_profit_pct)
            pnl = (exit_price - pos.entry_price) * pos.shares
            cash += pos.shares * exit_price
            result.trades.append(Trade(
                ts_code=ts_code,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                exit_date=date,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=(exit_price - pos.entry_price) / pos.entry_price,
                exit_reason='take_profit',
            ))
            data['position'] = None
            exited_today.add(ts_code)

    return cash, exited_today


def _portfolio_signal_pass(
    date: str,
    stock_data: Dict[str, Any],
    result: PortfolioBacktestResult,
    cash: float,
    exited_today: set,
) -> float:
    """处理新信号（买入/卖出，每日第二遍）。返回更新后的 cash。"""
    for ts_code, data in stock_data.items():
        kline = data['klines_map'].get(date)
        if not kline:
            continue

        price = kline['close']
        pos = data['position']
        day_signals = data['signal_map'].get(date, [])

        if not day_signals:
            continue

        day_signals.sort(key=lambda s: s.priority.value if hasattr(s.priority, 'value') else 3)
        top_signal = day_signals[0]

        # 买入（当日已止损/止盈出场的股票跳过，禁止同日再入场）
        if top_signal.action == 'BUY' and pos is None and ts_code not in exited_today:
            total_value = cash + sum(
                (p.current_value if p else 0)
                for p in [s['position'] for s in stock_data.values()]
            )
            max_invest = total_value * data['max_weight']
            invest_amount = min(cash, max_invest)
            shares = _calc_shares(invest_amount, price)

            if shares >= 100:
                cost = shares * price
                cash -= cost
                data['position'] = Position(
                    ts_code=ts_code,
                    entry_date=date,
                    entry_price=price,
                    shares=shares,
                    cost_basis=cost,
                    current_price=price,
                    current_value=cost,
                    high_since_entry=price,
                )

        elif top_signal.action == 'SELL' and pos is not None:
            cash += pos.shares * price
            pnl = (price - pos.entry_price) * pos.shares
            pnl_pct = (price - pos.entry_price) / pos.entry_price
            result.trades.append(Trade(
                ts_code=ts_code,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                exit_date=date,
                exit_price=price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason='signal',
            ))
            data['position'] = None

    return cash


def _portfolio_force_close(
    stock_data: Dict[str, Any],
    result: PortfolioBacktestResult,
    cash: float,
) -> float:
    """数据末尾强制平仓所有持仓。返回更新后的 cash。"""
    for ts_code, data in stock_data.items():
        pos = data['position']
        if pos is None:
            continue

        klines = data['klines']
        if not klines:
            continue

        last = klines[-1]
        exit_price = last['close']
        cash += pos.shares * exit_price
        pnl = (exit_price - pos.entry_price) * pos.shares
        result.trades.append(Trade(
            ts_code=ts_code,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=last['trade_date'],
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=(exit_price - pos.entry_price) / pos.entry_price,
            exit_reason='end_of_data',
        ))
        data['position'] = None

    return cash


