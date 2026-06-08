"""
策略回测框架

基于策略信号 + 历史K线，模拟交易并输出统计指标。

用法：
    from modules.backtest import backtest_strategy
    result = backtest_strategy('600487.SH', days=240)
    print(result.summary())

包结构：
- _models.py   : 数据类 + _calc_shares / _calc_stats
- _single.py   : backtest_signals + 纯计算辅助
- _multi.py    : _multi_check_exit / _multi_handle_signal 辅助
- _portfolio.py: _portfolio_* 辅助
- __init__.py  : 入口函数（backtest_strategy / backtest_multi_strategy /
                 backtest_portfolio）+ 全量公开 API + get_kline_data /
                 detect_all_strategies（供 mock patch 使用）
"""

import os
from typing import Any, Dict, List, Optional

# ── 外部依赖（patch 路径 modules.backtest.* 生效的关键）──────────────────
from modules.strategies import get_kline_data, detect_all_strategies  # noqa: F401

# ── 数据模型与共享辅助 ────────────────────────────────────────────────────
from modules.backtest._models import (
    Trade,
    BacktestResult,
    Position,
    PortfolioBacktestResult,
    _calc_shares,
    _calc_stats,
)

# ── 单策略纯计算辅助 ──────────────────────────────────────────────────────
from modules.backtest._single import (
    backtest_signals,
    _signals_check_exit,
    _signals_handle_signal,
    _signals_calc_metrics,
)

# ── 多策略纯计算辅助 ──────────────────────────────────────────────────────
from modules.backtest._multi import (
    _multi_check_exit,
    _multi_handle_signal,
)

# ── 组合纯计算辅助 ────────────────────────────────────────────────────────
from modules.backtest._portfolio import (
    _portfolio_exit_pass,
    _portfolio_signal_pass,
    _portfolio_force_close,
)


# ── 入口函数（含外部 I/O，定义在此处以使 patch 生效）────────────────────

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
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    klines = get_kline_data(ts_code, days)
    signals = detect_all_strategies(ts_code, days)

    return backtest_signals(signals, klines, ts_code, stop_loss_pct, take_profit_pct)


def backtest_multi_strategy(
    ts_code: str,
    days: int = 240,
    initial_capital: float = 100000.0,
    position_pct: float = 0.3,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> PortfolioBacktestResult:
    """
    单股票多策略融合回测

    逻辑：
    - 收集所有策略信号，按优先级（CRITICAL > OPPORTUNITY > OBSERVE）排序
    - 每天只执行最高优先级的买入/卖出信号
    - 仓位管理：每次最多使用 position_pct 比例的资金

    Args:
        ts_code: 股票代码
        days: 回测天数
        initial_capital: 初始资金
        position_pct: 单次仓位比例（默认30%）
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例

    Returns:
        PortfolioBacktestResult
    """
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    klines = get_kline_data(ts_code, days)
    signals = detect_all_strategies(ts_code, days)

    result = PortfolioBacktestResult(initial_capital=initial_capital)

    if not klines:
        return result

    # 构建日期 -> [信号列表] 映射
    signal_map: Dict[str, List[Any]] = {}
    for sig in signals:
        signal_map.setdefault(sig.trade_date, []).append(sig)

    cash = initial_capital
    position: Optional[Position] = None

    # 按日期升序遍历
    for k in klines:
        date = k['trade_date']
        price = k['close']

        # 更新持仓市值
        if position is not None:
            position.update_price(price)
            position, cash, exited = _multi_check_exit(
                k, date, ts_code, position, cash, result, stop_loss_pct, take_profit_pct
            )
            if exited:
                result.equity_curve.append((date, cash))
                continue

        # 处理当天信号
        day_signals = signal_map.get(date, [])
        if not day_signals:
            # 无信号，记录当前资产
            total_value = cash + (position.current_value if position else 0)
            result.equity_curve.append((date, total_value))
            continue

        # 按优先级排序（数值越小优先级越高：CRITICAL=1, OPPORTUNITY=2, OBSERVE=3）
        day_signals.sort(key=lambda s: s.priority.value if hasattr(s.priority, 'value') else 3)

        # 取最高优先级信号
        top_signal = day_signals[0]
        position, cash = _multi_handle_signal(
            date, price, ts_code, top_signal, position, cash, position_pct, result
        )

        total_value = cash + (position.current_value if position else 0)
        result.equity_curve.append((date, total_value))

    # 数据末尾强制平仓
    if position is not None and klines:
        last = klines[-1]
        exit_price = last['close']
        cash += position.shares * exit_price
        pnl = (exit_price - position.entry_price) * position.shares
        pnl_pct = (exit_price - position.entry_price) / position.entry_price

        trade = Trade(
            ts_code=ts_code,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=last['trade_date'],
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason='end_of_data',
        )
        result.trades.append(trade)
        position = None
        result.equity_curve[-1] = (last['trade_date'], cash)

    _calc_stats(result, trading_days=len(klines))
    return result


def backtest_portfolio(
    stock_configs: List[Dict[str, Any]],
    days: int = 240,
    initial_capital: float = 100000.0,
    position_pct: float = 0.2,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> PortfolioBacktestResult:
    """
    多股票组合回测

    Args:
        stock_configs: 股票配置列表，每项包含 {'ts_code': 'xxx', 'max_weight': 0.2}
        days: 回测天数
        initial_capital: 初始资金
        position_pct: 单只股票最大仓位比例
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例

    Returns:
        PortfolioBacktestResult
    """
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    result = PortfolioBacktestResult(initial_capital=initial_capital)

    # 为每只股票获取数据和信号
    stock_data = {}
    all_dates: set = set()

    for config in stock_configs:
        ts_code = config['ts_code']
        klines = get_kline_data(ts_code, days)
        signals = detect_all_strategies(ts_code, days)

        if not klines:
            continue

        signal_map: dict = {}
        for sig in signals:
            signal_map.setdefault(sig.trade_date, []).append(sig)

        stock_data[ts_code] = {
            'klines': klines,
            'signal_map': signal_map,
            'klines_map': {k['trade_date']: k for k in klines},
            'max_weight': config.get('max_weight', position_pct),
            'position': None,
        }
        all_dates.update(k['trade_date'] for k in klines)

    if not stock_data:
        return result

    # 按日期升序遍历
    sorted_dates = sorted(all_dates)
    cash = initial_capital

    for date in sorted_dates:
        # 1. 止损/止盈出场（当日已出场的股票进入 exited_today 禁止同日再买入）
        cash, exited_today = _portfolio_exit_pass(
            date, stock_data, result, cash, stop_loss_pct, take_profit_pct
        )

        # 2. 处理新信号（买入/卖出）
        cash = _portfolio_signal_pass(date, stock_data, result, cash, exited_today)

        # 3. 记录当日总资产
        positions_value = sum(
            (p.current_value if p else 0)
            for p in [s['position'] for s in stock_data.values()]
        )
        result.equity_curve.append((date, cash + positions_value))

    # 强制平仓所有持仓
    cash = _portfolio_force_close(stock_data, result, cash)

    if result.equity_curve:
        result.equity_curve[-1] = (result.equity_curve[-1][0], cash)

    _calc_stats(result, trading_days=len(sorted_dates))
    return result


__all__ = [
    # 数据模型
    "Trade",
    "BacktestResult",
    "Position",
    "PortfolioBacktestResult",
    # 共享辅助
    "_calc_shares",
    "_calc_stats",
    # 单策略
    "backtest_signals",
    "backtest_strategy",
    "_signals_check_exit",
    "_signals_handle_signal",
    "_signals_calc_metrics",
    # 多策略
    "backtest_multi_strategy",
    "_multi_check_exit",
    "_multi_handle_signal",
    # 组合
    "backtest_portfolio",
    "_portfolio_exit_pass",
    "_portfolio_signal_pass",
    "_portfolio_force_close",
    # 依赖（供 mock patch 使用）
    "get_kline_data",
    "detect_all_strategies",
]
