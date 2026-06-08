"""
单股票多策略融合回测辅助函数

包含:
- _multi_check_exit / _multi_handle_signal: 内部辅助（纯计算，无外部 I/O）

注意: backtest_multi_strategy（需要调用 get_kline_data / detect_all_strategies）
      定义在 modules/backtest/__init__.py，以保证 mock patch 路径正确。
"""

from typing import Any, Optional, Tuple

from modules.backtest._models import (
    Trade, Position, PortfolioBacktestResult,
    _calc_shares,
)


def _multi_check_exit(
    k: Dict[str, Any],
    date: str,
    ts_code: str,
    position: Position,
    cash: float,
    result: PortfolioBacktestResult,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Tuple[Optional[Position], float, bool]:
    """检查多策略回测持仓的止损/止盈。返回 (position, cash, exited)。"""
    day_high = k['high']
    day_low = k['low']

    if day_low <= position.entry_price * (1 - stop_loss_pct):
        exit_price = position.entry_price * (1 - stop_loss_pct)
        pnl = (exit_price - position.entry_price) * position.shares
        pnl_pct = (exit_price - position.entry_price) / position.entry_price
        cash += position.shares * exit_price
        result.trades.append(Trade(
            ts_code=ts_code,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=date,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason='stop_loss',
        ))
        return None, cash, True

    if day_high >= position.entry_price * (1 + take_profit_pct):
        exit_price = position.entry_price * (1 + take_profit_pct)
        pnl = (exit_price - position.entry_price) * position.shares
        pnl_pct = (exit_price - position.entry_price) / position.entry_price
        cash += position.shares * exit_price
        result.trades.append(Trade(
            ts_code=ts_code,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=date,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason='take_profit',
        ))
        return None, cash, True

    return position, cash, False


def _multi_handle_signal(
    date: str,
    price: float,
    ts_code: str,
    top_signal: Any,
    position: Optional[Position],
    cash: float,
    position_pct: float,
    result: PortfolioBacktestResult,
) -> Tuple[Optional[Position], float]:
    """处理多策略回测的买入/卖出信号。返回 (position, cash)。"""
    if top_signal.action == 'BUY' and position is None:
        invest_amount = cash * position_pct
        shares = _calc_shares(invest_amount, price)
        if shares >= 100:
            cost = shares * price
            cash -= cost
            position = Position(
                ts_code=ts_code,
                entry_date=date,
                entry_price=price,
                shares=shares,
                cost_basis=cost,
                current_price=price,
                current_value=cost,
                high_since_entry=price,
            )
    elif top_signal.action == 'SELL' and position is not None:
        cash += position.shares * price
        pnl = (price - position.entry_price) * position.shares
        pnl_pct = (price - position.entry_price) / position.entry_price
        result.trades.append(Trade(
            ts_code=ts_code,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=date,
            exit_price=price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason='signal',
        ))
        position = None

    return position, cash


