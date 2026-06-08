"""
回测数据模型与共享辅助函数

包含:
- Trade / BacktestResult / Position / PortfolioBacktestResult 数据类
- _calc_shares: 计算可买股数
- _calc_stats: 计算组合回测统计指标
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional


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


@dataclass
class Position:
    """持仓记录"""
    ts_code: str
    entry_date: str
    entry_price: float
    shares: int = 0           # 持股数量（A股100股为1手）
    cost_basis: float = 0.0   # 总成本
    current_price: float = 0.0
    current_value: float = 0.0
    high_since_entry: float = 0.0

    def update_price(self, price: float) -> None:
        """更新当前价格"""
        self.current_price = price
        self.current_value = self.shares * price
        self.high_since_entry = max(self.high_since_entry, price)

    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏比例"""
        if self.cost_basis == 0:
            return 0.0
        return (self.current_value - self.cost_basis) / self.cost_basis


@dataclass
class PortfolioBacktestResult:
    """组合回测结果（含资金曲线）"""
    initial_capital: float = 100000.0
    final_value: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)

    def summary(self) -> str:
        """格式化回测摘要"""
        lines = [
            f"{'='*60}",
            "组合回测结果",
            f"{'='*60}",
            f"初始资金:   ¥{self.initial_capital:,.0f}",
            f"最终资产:   ¥{self.final_value:,.0f}",
            f"总收益率:   {self.total_return:.2%}",
            f"年化收益:   {self.annualized_return:.2%}",
            f"夏普比率:   {self.sharpe_ratio:.2f}",
            f"最大回撤:   {self.max_drawdown:.1%}",
            f"胜率:       {self.win_rate:.1%}",
            f"盈亏比:     {self.profit_factor:.2f}",
            f"总交易次数: {self.total_trades}",
            f"{'='*60}",
        ]

        if self.trades:
            lines.append("最近5笔交易:")
            for t in self.trades[-5:]:
                status = "🟢" if t.pnl > 0 else "🔴" if t.pnl < 0 else "⚪"
                lines.append(
                    f"  {status} {t.ts_code} {t.entry_date}→{t.exit_date or '持有中'} "
                    f"{t.pnl_pct:+.2f}% ({t.exit_reason})"
                )

        return "\n".join(lines)


def _calc_shares(invest_amount: float, price: float) -> int:
    """计算可买入股数（A股100股为1手）"""
    if price <= 0 or invest_amount <= 0:
        return 0
    shares = int(invest_amount / price / 100) * 100
    return shares


def _calc_stats(result: PortfolioBacktestResult, trading_days: int = 0):
    """计算组合回测统计指标"""
    if not result.equity_curve:
        return

    # 总收益率
    result.final_value = result.equity_curve[-1][1]
    result.total_return = (result.final_value - result.initial_capital) / result.initial_capital

    # 年化收益（按252个交易日/年）
    if trading_days > 0:
        result.annualized_return = (1 + result.total_return) ** (252 / trading_days) - 1

    # 最大回撤 & 日收益率序列
    peak = result.initial_capital
    drawdown = 0.0
    daily_returns = []

    for i, (_date, value) in enumerate(result.equity_curve):
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        drawdown = max(drawdown, dd)

        if i > 0:
            prev_value = result.equity_curve[i - 1][1]
            if prev_value > 0:
                daily_returns.append((value - prev_value) / prev_value)

    result.max_drawdown = drawdown

    # 夏普比率（假设无风险利率为0）
    if daily_returns:
        avg_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)
        std = variance ** 0.5
        if std > 0:
            result.sharpe_ratio = (avg_return / std) * (252 ** 0.5)

    # 交易统计
    if result.trades:
        result.total_trades = len(result.trades)
        win_trades = sum(1 for t in result.trades if t.pnl > 0)
        result.win_rate = win_trades / result.total_trades

        total_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
