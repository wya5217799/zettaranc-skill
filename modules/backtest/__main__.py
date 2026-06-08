"""
策略回测 CLI 入口

用法：
    python -m modules.backtest single 600487.SH --days 240
    python -m modules.backtest multi  600487.SH --capital 100000
"""

import argparse

from modules.backtest import (
    BacktestResult, PortfolioBacktestResult,
    backtest_strategy, backtest_multi_strategy,
)

parser = argparse.ArgumentParser(description='策略回测')
subparsers = parser.add_subparsers(dest='command')

# 单策略回测
single_parser = subparsers.add_parser('single', help='单策略回测')
single_parser.add_argument('ts_code', help='股票代码')
single_parser.add_argument('--days', type=int, default=240, help='回测天数')
single_parser.add_argument('--stop-loss', type=float, default=0.07, help='止损比例')
single_parser.add_argument('--take-profit', type=float, default=0.15, help='止盈比例')

# 多策略融合回测
multi_parser = subparsers.add_parser('multi', help='多策略融合回测')
multi_parser.add_argument('ts_code', help='股票代码')
multi_parser.add_argument('--days', type=int, default=240, help='回测天数')
multi_parser.add_argument('--capital', type=float, default=100000, help='初始资金')
multi_parser.add_argument('--position', type=float, default=0.3, help='单次仓位比例')
multi_parser.add_argument('--stop-loss', type=float, default=0.07, help='止损比例')
multi_parser.add_argument('--take-profit', type=float, default=0.15, help='止盈比例')

args = parser.parse_args()

if args.command == 'single':
    result: BacktestResult | PortfolioBacktestResult = backtest_strategy(
        args.ts_code,
        days=args.days,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )
    print(result.summary())
elif args.command == 'multi':
    result = backtest_multi_strategy(
        args.ts_code,
        days=args.days,
        initial_capital=args.capital,
        position_pct=args.position,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )
    print(result.summary())
else:
    parser.print_help()
